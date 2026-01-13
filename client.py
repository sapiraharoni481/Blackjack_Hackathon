import socket
import struct

# =========================
# Protocol Constants
# =========================

# Magic cookie used to validate all packets according to the hackathon protocol
MAGIC_COOKIE = 0xabcddcba

# UDP port used for receiving offer broadcasts from servers
UDP_PORT = 13122

# Team name sent to the server when accepting an offer
TEAM_NAME = "badaboom_sapir_batel"

# =========================
# Card Display Helpers
# =========================

# Human-readable card rank names with Blackjack values
RANK_NAMES = {
    1: "Ace (11 pts)",
    11: "Jack (10 pts)",
    12: "Queen (10 pts)",
    13: "King (10 pts)"
}

# Unicode symbols for card suits
SUIT_ICONS = {
    0: "Hearts ❤️",
    1: "Diamonds ♦️",
    2: "Clubs ♣️",
    3: "Spades ♠️"
}

# =========================
# Game Statistics
# =========================

# Keeps track of the player's performance during a session
stats = {"wins": 0, "losses": 0, "ties": 0}


def get_card_value(rank):
    """
    Converts a card rank into its Blackjack numeric value.
    Ace is treated as 11 points.
    Face cards are worth 10 points.
    """
    if rank == 1:
        return 11
    if rank >= 10:
        return 10
    return rank


def start_client():
    """
    Starts the Blackjack client.
    Listens for UDP offer messages and connects to a matching server.
    """

    # Intro banner for better user experience
    print("\n" + "=" * 40)
    print("      ♣️  BADABOOM BLACKJACK CLIENT  ❤️")
    print("=" * 40)
    print("Client started, listening for offer requests...")

    # Create a UDP socket to receive broadcast offers
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
        udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        udp.bind(('0.0.0.0', UDP_PORT))

        # Client runs indefinitely and waits for new offers
        while True:
            data, addr = udp.recvfrom(1024)

            try:
                # Parse the UDP offer packet
                magic, m_type, port, srv_name = struct.unpack('!IBH32s', data[:39])

                # Validate packet structure and type
                if magic == MAGIC_COOKIE and m_type == 0x2:
                    offered_name = srv_name.split(b'\x00', 1)[0].decode(errors='ignore')
                    print(f"\nReceived offer from {addr[0]} ({offered_name})")

                    # Ignore offers not matching our team name
                    if offered_name != TEAM_NAME:
                        continue

                    # Ask the user how many rounds to play
                    try:
                        num_rounds = int(input("\nHow many rounds would you like to play? "))
                    except:
                        num_rounds = 1

                    # Reset statistics for the new session
                    stats["wins"] = 0
                    stats["losses"] = 0
                    stats["ties"] = 0

                    # Start the Blackjack game over TCP
                    play_game(addr[0], port, num_rounds)

                    # ===== Required by assignment =====
                    # Print summary statistics at the end of the session
                    win_rate = (stats["wins"] / num_rounds) * 100 if num_rounds > 0 else 0
                    print(f"\nFinished playing {num_rounds} rounds, win rate: {win_rate:.2f}%")
                    # =================================

                    # Display detailed statistics
                    print(
                        f"--- TOTAL STATS: {stats['wins']} Wins, {stats['losses']} Losses, {stats['ties']} Ties ---"
                    )

                    # Return to listening mode
                    print("\nReturning to the lobby...")
                    print("Client started, listening for offer requests...")

            except Exception:
                # Ignore malformed or irrelevant packets
                continue


def play_game(ip, port, num_rounds):
    """
    Connects to the Blackjack server over TCP and plays the specified number of rounds.
    """

    try:
        # Create a TCP socket for the game session
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp:
            tcp.settimeout(10)
            tcp.connect((ip, port))

            # Build and send the request packet to start the game
            request_packet = struct.pack(
                '!IBB32s',
                MAGIC_COOKIE,
                0x3,
                num_rounds,
                TEAM_NAME.encode().ljust(32, b'\x00')
            )
            tcp.sendall(request_packet)

            # Play the requested number of rounds
            for r in range(num_rounds):
                player_sum = 0
                cards_received = 0

                # Each round continues until a result is received
                while True:
                    data = b""

                    # Ensure a full message is received
                    while len(data) < 9:
                        chunk = tcp.recv(9 - len(data))
                        if not chunk:
                            raise ConnectionError("Server closed the connection")
                        data += chunk

                    # Parse the game message
                    magic, m_type, res, rank, suit = struct.unpack('!IBB HB', data)

                    # Validate incoming packet
                    if magic != MAGIC_COOKIE or m_type != 0x4:
                        continue

                    # Handle card reception
                    if rank > 0:
                        cards_received += 1
                        name = RANK_NAMES.get(rank, str(rank))
                        icon = SUIT_ICONS.get(suit % 10, "Unknown")

                        # First two cards belong to the player
                        if cards_received <= 2:
                            player_sum += get_card_value(rank)
                            print(f" YOUR Card: {name} of {icon}")

                        # Third card is the dealer's visible card
                        elif cards_received == 3:
                            print(f" DEALER'S Visible Card: {name} of {icon}")
                            print(f"💰 Your Starting Total: {player_sum}")

                        # Additional cards go to the player
                        else:
                            player_sum += get_card_value(rank)
                            print(f"New Card for YOU: {name} of {icon}")
                            print(f"💰 Updated Total: {player_sum}")

                    # Player decision phase
                    if res == 0 and rank == 0:
                        print(f"\n--- YOUR TURN (Total: {player_sum}) ---")

                        # Ask player for action until valid input is provided
                        while True:
                            choice = input(" Hit (h) or Stand (s)? ").lower().strip()
                            if choice in ['h', 's']:
                                break
                            print(" Invalid input! Type 'h' or 's'.")

                        # Send player's decision to the server
                        msg = "Hittt" if choice == 'h' else "Stand"
                        tcp.sendall(struct.pack('!IB5s', MAGIC_COOKIE, 0x4, msg.encode()))

                    # End-of-round result received
                    elif res != 0:
                        outcomes = {1: "TIE", 2: "LOSS", 3: "WIN"}
                        print(f"\n🏁 Result: {outcomes.get(res, 'Round Over')}")

                        # Update statistics
                        if res == 1:
                            stats["ties"] += 1
                        elif res == 2:
                            stats["losses"] += 1
                        elif res == 3:
                            stats["wins"] += 1
                        break

    except Exception as e:
        # Handle network errors and unexpected disconnections
        print(f" Error: {e}")


if __name__ == "__main__":
    # Entry point of the client application
    start_client()
