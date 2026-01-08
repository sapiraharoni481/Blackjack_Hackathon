import socket
import struct
import time
import threading
import random

MAGIC_COOKIE = 0xabcddcba
UDP_PORT = 13122
TCP_PORT = 0
TEAM_NAME = "badaboom_sapir_batel"


def get_card():
    """
    Generates and returns a random playing card.

    Returns:
        tuple[int, int]: (rank, suit) where rank is in [1..13] and suit is in [0..3].
    """
    return random.randint(1, 13), random.randint(0, 3)


def card_value(rank):
    """
    Converts a card rank to its Blackjack value.

    Rules:
        - Ace (1) is worth 11
        - Face cards (10, 11, 12, 13) are worth 10
        - Other ranks are worth their numeric value

    Args:
        rank (int): Card rank in [1..13].

    Returns:
        int: Blackjack value for the given rank.
    """
    if rank == 1: return 11
    if rank >= 10: return 10
    return rank


def handle_client(conn, addr):
    """
    Handles a single connected TCP client and runs a Blackjack session.

    Responsibilities:
        - Reads and validates the client's request packet (magic cookie + type + rounds + team name).
        - Runs the requested number of rounds.
        - Sends game payload messages to the client (cards, decision prompts, and final round result).
        - Receives and validates the client's decision messages (Hittt/Stand).
        - Closes the connection when the session ends or on errors.

    Args:
        conn (socket.socket): Connected TCP socket to the client.
        addr (tuple): Client address tuple (ip, port).
    """
    try:
        # Excellence: Set network timeout to prevent hanging connections
        conn.settimeout(10.0)

        # Read the fixed-size request packet reliably (TCP can split messages across recv calls)
        data = b""
        while len(data) < 38:
            chunk = conn.recv(38 - len(data))
            if not chunk:
                return
            data += chunk

        # Request packet format: magic cookie + message type + rounds + team name
        magic, m_type, rounds, name = struct.unpack('!IBB32s', data[:38])
        if magic != MAGIC_COOKIE or m_type != 0x3:
            return

        # Team name is null-padded in a fixed 32-byte field
        client_team = name.decode().strip('\x00')
        print(f"Starting {rounds} rounds with team: {client_team}")

        for r in range(rounds):
            # Deal initial hands (2 cards each)
            player_cards = [get_card(), get_card()]
            dealer_cards = [get_card(), get_card()]

            # Send player's two cards first, then dealer's visible card (the "up-card")
            for rank, suit in player_cards:
                conn.sendall(struct.pack('!IBB HB', MAGIC_COOKIE, 0x4, 0, rank, suit))
                time.sleep(0.1)  # Stability delay
            conn.sendall(struct.pack('!IBB HB', MAGIC_COOKIE, 0x4, 0, dealer_cards[0][0], dealer_cards[0][1]))

            # Player decision loop: keep asking until Stand or Bust
            while True:
                # Compute current player sum from the ranks already dealt
                p_sum = sum(card_value(c[0]) for c in player_cards)
                if p_sum > 21:
                    break

                # Decision prompt is encoded as a normal payload message with rank=0, suit=0, res=0
                conn.sendall(struct.pack('!IBB HB', MAGIC_COOKIE, 0x4, 0, 0, 0))

                # Read the fixed-size decision message (10 bytes)
                decision_data = b""
                while len(decision_data) < 10:
                    try:
                        chunk = conn.recv(10 - len(decision_data))
                    except socket.timeout:
                        # If client is slow, keep waiting (socket timeout prevents permanent blocking)
                        continue
                    if not chunk:
                        return
                    decision_data += chunk

                # Decision format: magic cookie + type + 5-byte ASCII command ("Hittt"/"Stand")
                magic2, m_type2, decision = struct.unpack('!IB5s', decision_data)

                # Ignore unexpected packets (wrong magic/type)
                if magic2 != MAGIC_COOKIE or m_type2 != 0x4:
                    continue

                if decision == b"Hittt":
                    # Deal one additional card to the player and send it as a normal payload
                    new_c = get_card()
                    player_cards.append(new_c)
                    conn.sendall(struct.pack('!IBB HB', MAGIC_COOKIE, 0x4, 0, new_c[0], new_c[1]))
                    time.sleep(0.1)
                else:
                    # Any non-"Hittt" command is treated as Stand
                    break

            # Dealer plays only after player stands or busts
            p_sum = sum(card_value(c[0]) for c in player_cards)
            d_sum = sum(card_value(c[0]) for c in dealer_cards)

            # Dealer hits until reaching at least 17 (standard Blackjack rule)
            if p_sum <= 21:
                while d_sum < 17:
                    new_c = get_card()
                    dealer_cards.append(new_c)
                    d_sum = sum(card_value(c[0]) for c in dealer_cards)

            # Compare final hands and encode result in the "res" field
            res = 0x1  # Tie
            if p_sum > 21:
                res = 0x2  # Loss (player bust)
            elif d_sum > 21 or p_sum > d_sum:
                res = 0x3  # Win
            elif d_sum > p_sum:
                res = 0x2  # Loss

            # End-of-round marker: payload with rank=0,suit=0 and res set to WIN/LOSS/TIE
            conn.sendall(struct.pack('!IBB HB', MAGIC_COOKIE, 0x4, res, 0, 0))
            time.sleep(0.5)  # Wait for client to process statistics

        print(f"Finished session with {client_team}")
    except Exception as e:
        print(f"Session error with {addr}: {e}")
    finally:
        conn.close()


def start_server():
    """
    Starts the Blackjack server.

    Behavior:
        - Opens a TCP listening socket on an OS-assigned port (TCP_PORT = 0).
        - Broadcasts offer messages over UDP (port 13122) once per second with the chosen TCP port.
        - Accepts incoming TCP connections and spawns a dedicated thread per client.

    Notes:
        - The offer packet includes the magic cookie, message type, TCP port, and team name.
        - The server runs indefinitely until the process is terminated.
    """
    server_ip = socket.gethostbyname(socket.gethostname())
    print(f"Server started, listening on IP address {server_ip}")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp:
        tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # Bind to port 0 to let the OS pick an available TCP port automatically
        tcp.bind(('', TCP_PORT))
        tcp.listen(5)

        # Discover the actual port chosen by the OS so we can advertise it in the offer
        actual_port = tcp.getsockname()[1]

        # Start UDP thread
        def broadcast():
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
                udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

                # Offer packet format: magic cookie + offer type + tcp port + server name
                packet = struct.pack('!IBH32s', MAGIC_COOKIE, 0x2, actual_port, TEAM_NAME.encode().ljust(32, b'\x00'))
                while True:
                    # Broadcast offer so any client on the local network can discover the server
                    udp.sendto(packet, ('255.255.255.255', UDP_PORT))
                    time.sleep(1)

        threading.Thread(target=broadcast, daemon=True).start()

        while True:
            # Accept a new TCP connection, then serve it in its own thread so multiple clients can play
            conn, addr = tcp.accept()
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()


if __name__ == "__main__":
    start_server()
