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
    if rank == 1:
        return 11
    if rank >= 10:
        return 10
    return rank


def handle_client(conn, addr):
    """
    Handles a single connected TCP client and runs a Blackjack session.
    """
    try:
        # Excellence: Set network timeout to prevent hanging connections
        conn.settimeout(10.0)

        # Read the fixed-size request packet reliably (TCP can split messages across recv calls)
        data = b""
        while len(data) < 38:
            try:
                chunk = conn.recv(38 - len(data))
            except socket.timeout:
                # Client may still be entering number of rounds – keep waiting
                continue
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
            print(f"\n--- Round {r + 1} started ---")
            player_cards = [get_card(), get_card()]
            dealer_cards = [get_card(), get_card()]
            print("Dealing initial cards")

            for rank, suit in player_cards:
                conn.sendall(struct.pack('!IBB HB', MAGIC_COOKIE, 0x4, 0, rank, suit))
                time.sleep(0.1)

            conn.sendall(struct.pack('!IBB HB', MAGIC_COOKIE, 0x4, 0, dealer_cards[0][0], dealer_cards[0][1]))

            while True:
                p_sum = sum(card_value(c[0]) for c in player_cards)
                if p_sum > 21:
                    print("Player busts")
                    break

                conn.sendall(struct.pack('!IBB HB', MAGIC_COOKIE, 0x4, 0, 0, 0))

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

                if magic2 != MAGIC_COOKIE or m_type2 != 0x4:
                    continue

                if decision == b"Hittt":
                    print("Player chose HIT")
                    new_c = get_card()
                    player_cards.append(new_c)
                    conn.sendall(struct.pack('!IBB HB', MAGIC_COOKIE, 0x4, 0, new_c[0], new_c[1]))
                    time.sleep(0.1)
                else:
                    print("Player chose STAND")
                    break

            p_sum = sum(card_value(c[0]) for c in player_cards)
            d_sum = sum(card_value(c[0]) for c in dealer_cards)

            if p_sum <= 21:
                while d_sum < 17:
                    new_c = get_card()
                    dealer_cards.append(new_c)
                    d_sum = sum(card_value(c[0]) for c in dealer_cards)

            res = 0x1
            if p_sum > 21:
                res = 0x2
            elif d_sum > 21 or p_sum > d_sum:
                res = 0x3
            elif d_sum > p_sum:
                res = 0x2

            outcome = {1: "TIE", 2: "LOSS", 3: "WIN"}
            print(f"Round {r + 1} result: {outcome[res]}")

            conn.sendall(struct.pack('!IBB HB', MAGIC_COOKIE, 0x4, res, 0, 0))
            time.sleep(0.5)

        print(f"Finished session with {client_team}")

    except Exception as e:
        print(f"Session error with {addr}: {e}")
    finally:
        conn.close()


def start_server():
    """
    Starts the Blackjack server.
    """
    server_ip = socket.gethostbyname(socket.gethostname())
    print(f"Server started, listening on IP address {server_ip}")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp:
        tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        tcp.bind(('', TCP_PORT))
        tcp.listen(5)

        actual_port = tcp.getsockname()[1]

        def broadcast():
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
                udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
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

        threading.Thread(target=broadcast, daemon=True).start()

        while True:
            conn, addr = tcp.accept()
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()


if __name__ == "__main__":
    start_server()
