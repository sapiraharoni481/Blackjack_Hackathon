import socket
import struct
import time
import threading
import random

MAGIC_COOKIE = 0xabcddcba
UDP_PORT = 13122
TCP_PORT = 5000
TEAM_NAME = "badaboom_sapir_batel"


def get_card():
    return random.randint(1, 13), random.randint(0, 3)


def card_value(rank):
    if rank == 1: return 11
    if rank >= 10: return 10
    return rank

def handle_client(conn, addr):
    """
    Manages the Blackjack game session for a connected TCP client.
    Includes robust data reading to prevent timeouts and handles multiple rounds.
    """
    try:
        # Excellence: Set network timeout to prevent hanging connections
        conn.settimeout(10.0)

        # 1. Receive Request: Ensure all 38 bytes of the request are read
        data = b""
        while len(data) < 38:
            chunk = conn.recv(38 - len(data))
            if not chunk:
                return
            data += chunk

        # Unpack request: Magic(4), Type(1), Rounds(1), TeamName(32)
        magic, m_type, rounds, name = struct.unpack('!IBB32s', data[:38])
        if magic != MAGIC_COOKIE or m_type != 0x3:
            return

        client_team = name.decode().strip('\x00')
        print(f"Starting {rounds} rounds with team: {client_team}")

        # 2. Main Game Loop for the requested number of rounds
        for r in range(rounds):
            player_cards = [get_card(), get_card()]
            dealer_cards = [get_card(), get_card()]

            # Send initial player cards and dealer's visible card
            for rank, suit in player_cards:
                conn.sendall(struct.pack('!IBB HB', MAGIC_COOKIE, 0x4, 0, rank, suit))
                time.sleep(0.1)  # Stability delay
            conn.sendall(struct.pack('!IBB HB', MAGIC_COOKIE, 0x4, 0, dealer_cards[0][0], dealer_cards[0][1]))

            # 3. Player's Turn: Continue until Stand or Bust
            while True:
                p_sum = sum(card_value(c[0]) for c in player_cards)
                if p_sum > 21:
                    break

                # Signal client to make a decision (Rank=0, Res=0)
                conn.sendall(struct.pack('!IBB HB', MAGIC_COOKIE, 0x4, 0, 0, 0))

                # Technical Fix: Ensure exactly 11 bytes are read for the decision payload
                # Read exactly 10 bytes: Magic(4) + Type(1) + Decision(5)
                decision_data = b""
                while len(decision_data) < 10:
                    try:
                        chunk = conn.recv(10 - len(decision_data))
                    except socket.timeout:
                        continue
                    if not chunk:
                        return
                    decision_data += chunk

                # Unpack decision: total 10 bytes
                magic2, m_type2, decision = struct.unpack('!IB5s', decision_data)

                # Validate payload header
                if magic2 != MAGIC_COOKIE or m_type2 != 0x4:
                    continue

                if decision == b"Hittt":
                    new_c = get_card()
                    player_cards.append(new_c)
                    conn.sendall(struct.pack('!IBB HB', MAGIC_COOKIE, 0x4, 0, new_c[0], new_c[1]))
                    time.sleep(0.1)
                else:
                    break

            # 4. Dealer's Turn: Hit until sum >= 17
            p_sum = sum(card_value(c[0]) for c in player_cards)
            d_sum = sum(card_value(c[0]) for c in dealer_cards)
            if p_sum <= 21:
                while d_sum < 17:
                    new_c = get_card()
                    dealer_cards.append(new_c)
                    d_sum = sum(card_value(c[0]) for c in dealer_cards)

            # 5. Determine Result
            res = 0x1  # Tie
            if p_sum > 21:
                res = 0x2  # Loss (Bust)
            elif d_sum > 21 or p_sum > d_sum:
                res = 0x3  # Win
            elif d_sum > p_sum:
                res = 0x2  # Loss

            # Send final round result
            conn.sendall(struct.pack('!IBB HB', MAGIC_COOKIE, 0x4, res, 0, 0))
            time.sleep(0.5)  # Wait for client to process statistics

        print(f"Finished session with {client_team}")
    except Exception as e:
        print(f"Session error with {addr}: {e}")
    finally:
        conn.close()


def start_server():
    server_ip = socket.gethostbyname(socket.gethostname())
    print(f"Server started, listening on IP address {server_ip}")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp:
        tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        tcp.bind(('', TCP_PORT))
        tcp.listen(5)

        # Start UDP thread
        def broadcast():
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
                udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                packet = struct.pack('!IBH32s', MAGIC_COOKIE, 0x2, TCP_PORT, TEAM_NAME.encode().ljust(32, b'\x00'))
                while True:
                    udp.sendto(packet, ('255.255.255.255', UDP_PORT))
                    time.sleep(1)

        threading.Thread(target=broadcast, daemon=True).start()
        while True:
            conn, addr = tcp.accept()
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()


if __name__ == "__main__":
    start_server()