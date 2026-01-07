import socket
import struct

# Constants based on the hackathon protocol
MAGIC_COOKIE = 0xabcddcba
UDP_PORT = 13122
TEAM_NAME = "badaboom_sapir_batel"

# Prettier rank and suit mapping
RANK_NAMES = {1: "Ace (11 pts)", 11: "Jack (10 pts)", 12: "Queen (10 pts)", 13: "King (10 pts)"}
SUIT_ICONS = {0: "Hearts ❤️", 1: "Diamonds ♦️", 2: "Clubs ♣️", 3: "Spades ♠️"}

# Statistics counter
stats = {"wins": 0, "losses": 0, "ties": 0}


def get_card_value(rank):
    """Face cards = 10, Ace = 11"""
    if rank == 1: return 11
    if rank >= 10: return 10
    return rank


def start_client():
    # Ask user for number of rounds
    try:
        num_rounds = int(input("How many rounds would you like to play? "))
    except:
        num_rounds = 1

    print("\n" + "=" * 40)
    print("      ♣️  BADABOOM BLACKJACK CLIENT  ❤️")
    print("=" * 40)
    print("Client started, listening for offer requests...")  #

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
        udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        udp.bind(('0.0.0.0', UDP_PORT))

        while True:
            data, addr = udp.recvfrom(1024)
            try:
                # Unpack Offer: Magic(4), Type(1), Port(2), Name(32)
                magic, m_type, port, srv_name = struct.unpack('!IBH32s', data[:39])
                if magic == MAGIC_COOKIE and m_type == 0x2:
                    offered_name = srv_name.split(b'\x00', 1)[0].decode(errors='ignore')
                    print(f"\nReceived offer from {addr[0]} ({offered_name})")
                    if offered_name != TEAM_NAME:
                        continue
                    play_game(addr[0], port, num_rounds)

                    # Excellence: Print statistics
                    print(
                        f"\n--- TOTAL STATS: {stats['wins']} Wins, {stats['losses']} Losses, {stats['ties']} Ties ---")
                    print("\nReturning to the lobby...")
                    print("Client started, listening for offer requests...")
            except:
                continue


def play_game(ip, port, num_rounds):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp:
            tcp.settimeout(10)
            tcp.connect((ip, port))
            request_packet = struct.pack('!IBB32s', MAGIC_COOKIE, 0x3, num_rounds,
                                         TEAM_NAME.encode().ljust(32, b'\x00'))
            tcp.sendall(request_packet)

            for r in range(num_rounds):
                player_sum = 0
                cards_received = 0
                while True:
                    data = b""
                    while len(data) < 9:
                        chunk = tcp.recv(9 - len(data))
                        if not chunk:
                            raise ConnectionError("Server closed the connection")
                        data += chunk

                    magic, m_type, res, rank, suit = struct.unpack('!IBB HB', data)

                    if magic != MAGIC_COOKIE or m_type != 0x4:
                        continue

                    if rank > 0:
                        cards_received += 1
                        name = RANK_NAMES.get(rank, str(rank))
                        icon = SUIT_ICONS.get(suit % 10, "Unknown")
                        if cards_received <= 2:
                            player_sum += get_card_value(rank)
                            print(f" YOUR Card: {name} of {icon}")
                        elif cards_received == 3:
                            print(f" DEALER'S Visible Card: {name} of {icon}")
                            print(f"💰 Your Starting Total: {player_sum}")
                        else:
                            player_sum += get_card_value(rank)
                            print(f"New Card for YOU: {name} of {icon}")
                            print(f"💰 Updated Total: {player_sum}")

                    if res == 0 and rank == 0:
                        print(f"\n--- YOUR TURN (Total: {player_sum}) ---")
                        while True:
                            choice = input(" Hit (h) or Stand (s)? ").lower().strip()
                            if choice in ['h', 's']: break
                            print(" Invalid input! Type 'h' or 's'.")
                        msg = "Hittt" if choice == 'h' else "Stand"
                        tcp.sendall(struct.pack('!IB5s', MAGIC_COOKIE, 0x4, msg.encode()))
                    elif res != 0:
                        outcomes = {1: "TIE", 2: "LOSS", 3: "WIN"}
                        print(f"\n🏁 Result: {outcomes.get(res, 'Round Over')}")
                        if res == 1:
                            stats["ties"] += 1
                        elif res == 2:
                            stats["losses"] += 1
                        elif res == 3:
                            stats["wins"] += 1
                        break
    except Exception as e:
        print(f" Error: {e}")


if __name__ == "__main__":
    start_client()