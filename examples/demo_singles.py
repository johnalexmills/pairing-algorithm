"""Crokinole singles demo — 24 players, 12 tables, 5 rounds (head-to-head)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pairing import LeaguePairingManager

ROSTER = [
    "Alice",  "Bob",    "Carol",  "Dave",
    "Eve",    "Frank",  "Grace",  "Henry",
    "Ivy",    "Jack",   "Kate",   "Leo",
    "Mia",    "Noah",   "Olivia", "Paul",
    "Quinn",  "Riley",  "Sam",    "Tara",
    "Uma",    "Vince",  "Wendy",  "Xander",
]

NUM_TABLES = 12
NUM_ROUNDS = 5


def _box(content_lines, header=None, footer=None):
    W = 36
    sep = "╠" + "═" * W + "╣"
    out = ["╔" + "═" * W + "╗"]
    if header:
        out.append("║ " + header.ljust(W - 2) + " ║")
        out.append(sep)
    for line in content_lines:
        out.append("║ " + line.ljust(W - 2) + " ║")
    if footer:
        out.append(sep)
        out.append("║ " + footer.ljust(W - 2) + " ║")
    out.append("╚" + "═" * W + "╝")
    return "\n".join(out)


def visualize_singles_round(rnd):
    """Print singles round as ASCII table layout."""
    matches = rnd.get("matches", [])
    tables = rnd.get("tables", [])
    bye = rnd.get("bye", [])
    rn = rnd.get("round", "?")

    lines = []
    for tn, m1, _ in tables:
        if m1:
            a, b = m1
            lines.append(f"Table {tn}")
            lines.append(f"  {a} vs {b}")
            lines.append("")
        else:
            lines.append(f"Table {tn}")
            lines.append("  (empty)")
            lines.append("")

    if lines:
        lines.pop()

    footer = None
    if bye:
        footer = f"Bye: {', '.join(bye)}"

    header = f"Round {rn}" + (f"  ({len(matches)} matches)" if matches else "")
    print(_box(lines, header=header, footer=footer))


def main():
    mgr = LeaguePairingManager(ROSTER, mode="singles")

    print(f"Roster: {len(ROSTER)} players")
    print(f"Tables: {NUM_TABLES}  ({len(ROSTER)//2} default)")
    print(f"Rounds: {NUM_ROUNDS}")
    print()

    rounds = mgr.generate_night(ROSTER, NUM_ROUNDS, NUM_TABLES)
    for rnd in rounds:
        visualize_singles_round(rnd)
        print()


if __name__ == "__main__":
    main()
