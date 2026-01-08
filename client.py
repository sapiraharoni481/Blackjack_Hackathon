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
    """
    Converts a received card rank into its Blackjack value.

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


def start_client():
    """
    Starts the Blackjack client.

    Behavior:
        - Asks the user how many rounds to play.
        - Listens on UDP port 13122 for offer messages.
        - Filters offers by server name (TEAM_NAME).
        - Connects to the offered TCP port and plays the game.
        - Returns to the lobby after finishing a session and keeps listening for offers.
    """
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
            # Wait for an offer packet from any server on the local network
            data, addr = udp.recvfrom(1024)
            try:
                # Offer format: Magic(4) + Type(1) + TCP Port(2) + ServerName(32)
                magic, m_type, port, srv_name = struct.unpack('!IBH32s', data[:39])
                if magic == MAGIC_COOKIE and m_type == 0x2:
                    # Server name is a null-padded fixed field
                    offered_name = srv_name.split(b'\x00', 1)[0].decode(errors='ignore')
                    print(f"\nReceived offer from {addr[0]} ({offered_name})")

                    # Ignore other servers; connect only to the server that matches our TEAM_NAME
                    if offered_name != TEAM_NAME:
                        continue

                    # Connect to the offered TCP port and run the session
                    play_game(addr[0], port, num_rounds)

                    # Excellence: Print statistics
                    print(
                        f"\n--- TOTAL STATS: {stats['wins']} Wins, {stats['losses']} Losses, {stats['ties']} Ties ---")
                    print("\nReturning to the lobby...")
                    print("Client started, listening for offer requests...")
            except Exception:
                # Ignore malformed or irrelevant UDP packets and keep listening
                continue


def play_game(ip, port, num_rounds):
    """
    Connects to the server over TCP and plays the requested number of rounds.

    Protocol:
        - Sends a request packet containing magic cookie, message type, rounds, and TEAM_NAME.
        - Receives fixed-size payload messages (9 bytes) from the server:
            Magic(4) + Type(1) + Res(1) + Rank(2) + Suit(1)
        - When server sends a decision prompt (Res=0, Rank=0), the client asks the user for Hit/Stand
          and responds with a fixed-size decision message (10 bytes):
            Magic(4) + Type(1) + Decision(5)

    Args:
        ip (str): Server IP address taken from the UDP offer source.
        port (int): Server TCP port taken from the UDP offer payload.
        num_rounds (int): Number of rounds requested by the user.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp:
            # Timeout prevents the client from blocking forever on network operations
            tcp.settimeout(10)
            tcp.connect((ip, port))

            # Request format: Magic(4) + Type(1) + Rounds(1) + TeamName(32)
            request_packet = struct.pack(
                '!IBB32s',
                MAGIC_COOKIE,
                0x3,
                num_rounds,
                TEAM_NAME.encode().ljust(32, b'\x00')
            )
            tcp.sendall(request_packet)

            for r in range(num_rounds):
                # player_sum tracks only the player's hand value (dealer sum is handled by the server)
                player_sum = 0
                # cards_received counts how many card payloads we already processed in this round
                cards_received = 0

                while True:
                    # Each server payload message is exactly 9 bytes
                    data = b""
                    while len(data) < 9:
                        chunk = tcp.recv(9 - len(data))
                        if not chunk:
                            raise ConnectionError("Server closed the connection")
                        data += chunk

                    # Payload format: Magic(4) + Type(1) + Res(1) + Rank(2) + Suit(1)
                    magic, m_type, res, rank, suit = struct.unpack('!IBB HB', data)

                    # Ignore packets that are not part of this protocol stream
                    if magic != MAGIC_COOKIE or m_type != 0x4:
                        continue

                    # rank > 0 means this payload carries an actual card
                    if rank > 0:
                        cards_received += 1

                        # Map the rank/suit to a prettier display name
                        name = RANK_NAMES.get(rank, str(rank))
                        icon = SUIT_ICONS.get(suit % 10, "Unknown")

                        # First two cards belong to the player
                        if cards_received <= 2:
                            player_sum += get_card_value(rank)
                            print(f" YOUR Card: {name} of {icon}")

                        # Third card is the dealer's visible card (not counted in player_sum)
                        elif cards_received == 3:
                            print(f" DEALER'S Visible Card: {name} of {icon}")
                            print(f"💰 Your Starting Total: {player_sum}")

                        # Any later cards are additional player cards (after Hit)
                        else:
                            player_sum += get_card_value(rank)
                            print(f"New Card for YOU: {name} of {icon}")
                            print(f"💰 Updated Total: {player_sum}")

                    # Decision prompt: Res=0 and Rank=0 tells the client to choose Hit/Stand
                    if res == 0 and rank == 0:
                        print(f"\n--- YOUR TURN (Total: {player_sum}) ---")
                        while True:
                            choice = input(" Hit (h) or Stand (s)? ").lower().strip()
                            if choice in ['h', 's']:
                                break
                            print(" Invalid input! Type 'h' or 's'.")

                        msg = "Hittt" if choice == 'h' else "Stand"

                        # Decision format: Magic(4) + Type(1) + Decision(5)
                        tcp.sendall(struct.pack('!IB5s', MAGIC_COOKIE, 0x4, msg.encode()))

                    # End-of-round marker: Res != 0 indicates WIN/LOSS/TIE and Rank=0 in this message
                    elif res != 0:
                        outcomes = {1: "TIE", 2: "LOSS", 3: "WIN"}
                        print(f"\n🏁 Result: {outcomes.get(res, 'Round Over')}")

                        # Update statistics for the whole session
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
