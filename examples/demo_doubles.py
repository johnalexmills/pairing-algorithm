"""Crokinole pairing demo — 24 players, 6 tables, 5 rounds."""

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

NUM_TABLES = 6
NUM_ROUNDS = 5


def _box(content_lines, header=None, footer=None):
    """Wrap content lines in double-line box (36-char interior)."""
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


def visualize_round(rnd):
    """Print round as ASCII table layout."""
    teams = rnd.get("teams", [])
    tables = rnd.get("tables", [])
    bye = rnd.get("bye", [])
    rn = rnd.get("round", "?")

    lines = []
    for tn, t1, t2 in tables:
        if t1 and t2:
            a1, a2 = t1
            b1, b2 = t2
            lines.append(f"Table {tn}")
            lines.append(f"  {a1} & {a2}")
            lines.append("  vs")
            lines.append(f"  {b1} & {b2}")
            lines.append("")
        elif t1:
            a1, a2 = t1
            lines.append(f"Table {tn}")
            lines.append(f"  {a1} & {a2}")
            lines.append("  (awaiting opponent)")
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

    header = f"Round {rn}" + (f"  ({len(teams)} teams)" if teams else "")
    print(_box(lines, header=header, footer=footer))


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
