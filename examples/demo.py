"""Crokinole pairing demo — 24 players, 6 tables, 5 rounds."""

from pairing import LeaguePairingManager, visualize_round

ROSTER = [
    "Alice",  "Bob",    "Carol",  "Dave",
    "Eve",    "Frank",  "Grace",  "Henry",
    "Ivy",    "Jack",   "Kate",   "Leo",
    "Mia",    "Noah",   "Olivia", "Paul",
    "Quinn",  "Riley",  "Sam",    "Tara",
    "Uma",    "Vince",  "Wendy",  "Xander",
]

NUM_TABLES = 6
NUM_ROUNDS = 5


def main():
    mgr = LeaguePairingManager(ROSTER)

    print(f"Roster: {len(ROSTER)} players")
    print(f"Tables: {NUM_TABLES}  ({len(ROSTER)//4} default)")
    print(f"Rounds: {NUM_ROUNDS}")
    print()

    rounds = mgr.generate_night(ROSTER, NUM_ROUNDS, NUM_TABLES)
    for rnd in rounds:
        visualize_round(rnd)
        print()


if __name__ == "__main__":
    main()
