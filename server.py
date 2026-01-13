import socket
import struct
import time
import threading
import random

# =========================
# Protocol Constants
# =========================

# Magic cookie used to validate all packets according to the hackathon protocol
MAGIC_COOKIE = 0xabcddcba

# UDP port used for broadcasting game offers
UDP_PORT = 13122

# TCP port (0 means the OS will choose an available port automatically)
TCP_PORT = 0

# Team name advertised to clients
TEAM_NAME = "badaboom_sapir_batel"


def get_card():
    """
    Generates and returns a random playing card.

    Returns:
        tuple[int, int]:
            - rank: integer in range [1..13]
            - suit: integer in range [0..3]
    """
    return random.randint(1, 13), random.randint(0, 3)


def card_value(rank):
    """
    Converts a card rank into its Blackjack numeric value.

    Rules:
        - Ace (rank 1) counts as 11
        - Face cards (10, 11, 12, 13) count as 10
        - Other cards count as their rank

    Args:
        rank (int): Card rank in range [1..13]

    Returns:
        int: Blackjack value of the card
    """
    if rank == 1:
        return 11
    if rank >= 10:
        return 10
    return rank


def handle_client(conn, addr):
    """
    Handles a single connected TCP client.
    Runs a full Blackjack session consisting of multiple rounds.
    """
    try:
        # Set timeout to prevent blocking forever on disconnected clients
        conn.settimeout(10.0)

        # Read the fixed-size request packet safely
        # TCP does not guarantee receiving the full packet in one recv call
        data = b""
        while len(data) < 38:
            try:
                chunk = conn.recv(38 - len(data))
            except socket.timeout:
                # Client might still be choosing number of rounds
                continue
            if not chunk:
                return
            data += chunk

        # Unpack the request packet:
        # magic cookie | message type | number of rounds | team name
        magic, m_type, rounds, name = struct.unpack('!IBB32s', data[:38])

        # Validate protocol fields
        if magic != MAGIC_COOKIE or m_type != 0x3:
            return

        # Extract team name from null-padded byte field
        client_team = name.decode().strip('\x00')
        print(f"Starting {rounds} rounds with team: {client_team}")

        # Run the requested number of rounds
        for r in range(rounds):
            print(f"\n--- Round {r + 1} started ---")

            # Deal initial cards
            player_cards = [get_card(), get_card()]
            dealer_cards = [get_card(), get_card()]
            print("Dealing initial cards")

            # Send player's initial two cards
            for rank, suit in player_cards:
                conn.sendall(struct.pack('!IBB HB', MAGIC_COOKIE, 0x4, 0, rank, suit))
                time.sleep(0.1)

            # Send dealer's visible card only
            conn.sendall(
                struct.pack('!IBB HB', MAGIC_COOKIE, 0x4, 0, dealer_cards[0][0], dealer_cards[0][1])
            )

            # Player decision loop
            while True:
                # Calculate player's current total
                p_sum = sum(card_value(c[0]) for c in player_cards)

                # Player bust condition
                if p_sum > 21:
                    print("Player busts")
                    break

                # Notify client it's their turn
                conn.sendall(struct.pack('!IBB HB', MAGIC_COOKIE, 0x4, 0, 0, 0))

                # Receive player's decision (Hit / Stand)
                decision_data = b""
                while len(decision_data) < 10:
                    try:
                        chunk = conn.recv(10 - len(decision_data))
                    except socket.timeout:
                        continue
                    if not chunk:
                        return
                    decision_data += chunk

                magic2, m_type2, decision = struct.unpack('!IB5s', decision_data)

                # Validate decision packet
                if magic2 != MAGIC_COOKIE or m_type2 != 0x4:
                    continue

                # Handle player action
                if decision == b"Hittt":
                    print("Player chose HIT")
                    new_c = get_card()
                    player_cards.append(new_c)
                    conn.sendall(
                        struct.pack('!IBB HB', MAGIC_COOKIE, 0x4, 0, new_c[0], new_c[1])
                    )
                    time.sleep(0.1)
                else:
                    print("Player chose STAND")
                    break

            # Calculate final sums
            p_sum = sum(card_value(c[0]) for c in player_cards)
            d_sum = sum(card_value(c[0]) for c in dealer_cards)

            # Dealer draws until reaching at least 17
            if p_sum <= 21:
                while d_sum < 17:
                    new_c = get_card()
                    dealer_cards.append(new_c)
                    d_sum = sum(card_value(c[0]) for c in dealer_cards)

            # Determine round result
            res = 0x1  # Default: TIE
            if p_sum > 21:
                res = 0x2  # Player loss
            elif d_sum > 21 or p_sum > d_sum:
                res = 0x3  # Player win
            elif d_sum > p_sum:
                res = 0x2  # Player loss

            outcome = {1: "TIE", 2: "LOSS", 3: "WIN"}
            print(f"Round {r + 1} result: {outcome[res]}")

            # Send round result to the client
            conn.sendall(struct.pack('!IBB HB', MAGIC_COOKIE, 0x4, res, 0, 0))
            time.sleep(0.5)

        print(f"Finished session with {client_team}")

    except Exception as e:
        # Catch and log unexpected session errors
        print(f"Session error with {addr}: {e}")

    finally:
        # Ensure the connection is always closed
        conn.close()


def start_server():
    """
    Starts the Blackjack server.
    Listens for TCP connections and broadcasts UDP offers.
    """
    server_ip = socket.gethostbyname(socket.gethostname())
    print(f"Server started, listening on IP address {server_ip}")

    # Create TCP server socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp:
        tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        tcp.bind(('', TCP_PORT))
        tcp.listen(5)

        # Retrieve the actual TCP port assigned by the OS
        actual_port = tcp.getsockname()[1]

        def broadcast():
            """
            Periodically broadcasts server offers via UDP.
            """
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
                udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

                # Offer packet structure:
                # magic cookie | message type | TCP port | team name
                packet = struct.pack(
                    '!IBH32s',
                    MAGIC_COOKIE, 
                    0x2,
                    actual_port,
                    TEAM_NAME.encode().ljust(32, b'\x00')
                )

                while True:
                    udp.sendto(packet, ('255.255.255.255', UDP_PORT))
                    time.sleep(1)

        # Start UDP broadcast thread
        threading.Thread(target=broadcast, daemon=True).start()

        # Accept incoming TCP connections indefinitely
        while True:
            conn, addr = tcp.accept()
            threading.Thread(
                target=handle_client,
                args=(conn, addr),
                daemon=True
            ).start()


if __name__ == "__main__":
    # Server entry point
    start_server()
