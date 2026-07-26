"""Stress test pairing algorithm at various scales."""
import time
import sys
sys.path.insert(0, ".")

from pairing import LeaguePairingManager


def run_test(label, roster_size, present_size, num_rounds, mode="doubles", sparse_rounds=0):
    roster = [f"P{i}" for i in range(roster_size)]
    present = roster[:present_size]
    denom = 2 if mode == "singles" else 4
    num_tables = max(1, present_size // denom)

    mgr = LeaguePairingManager(roster, mode=mode)

    # Burn rounds to create sparse graph (late season simulation)
    if sparse_rounds:
        t0 = time.perf_counter()
        for _ in range(sparse_rounds):
            # Use same present pool to burn pairs quickly
            mgr.next_round(present, num_tables)
        burn_time = time.perf_counter() - t0
    else:
        burn_time = 0

    # Timed rounds
    t0 = time.perf_counter()
    for _ in range(num_rounds):
        mgr.next_round(present, num_tables)
    elapsed = time.perf_counter() - t0

    state = "sparse" if sparse_rounds else "fresh"
    rt = elapsed / num_rounds
    teams = present_size // 2 if mode == "singles" else min(num_tables * 2, present_size // 2)
    byes = present_size - teams * (1 if mode == "singles" else 2)
    print(f"  {label:40s}  {present_size:4d} present  {num_rounds}r  {rt*1000:7.1f}ms/r  {teams:3d} teams  {byes:2d} bye  {state}" +
          (f"  (burn {sparse_rounds}r {burn_time*1000:.0f}ms)" if sparse_rounds else ""))


print(f"\n{'Test':40s}  {'Size':>4s}  {'Rnds':>4s}  {'ms/r':>7s}  {'Tm':>3s}  {'Bye':>2s}  {'State':>6s}")
print("-" * 90)

# Fresh graph — Doubles
run_test("Doubles: 20 present", 50, 20, 10, "doubles")
run_test("Doubles: 50 present", 100, 50, 10, "doubles")
run_test("Doubles: 100 present", 200, 100, 5, "doubles")
run_test("Doubles: 200 present", 400, 200, 3, "doubles")
run_test("Doubles: 300 present", 600, 300, 2, "doubles")

# Sparse graph — Doubles (burn 20 rounds to reduce available pairs)
print()
run_test("Doubles: 20 present (sparse)", 50, 20, 10, "doubles", sparse_rounds=20)
run_test("Doubles: 50 present (sparse)", 100, 50, 10, "doubles", sparse_rounds=20)
run_test("Doubles: 100 present (sparse)", 200, 100, 5, "doubles", sparse_rounds=20)

# Singles — Fresh
print()
run_test("Singles: 20 present", 50, 20, 10, "singles")
run_test("Singles: 50 present", 100, 50, 10, "singles")
run_test("Singles: 100 present", 200, 100, 5, "singles")
run_test("Singles: 200 present", 400, 200, 3, "singles")

# Guests
print()
for guest_count in [1, 5, 10]:
    roster = [f"P{i}" for i in range(50)]
    present = [f"P{i}" for i in range(20)] + [f"Guest{g}" for g in range(guest_count)]
    mgr = LeaguePairingManager(roster)
    num_tables = max(1, len(present) // 4)
    t0 = time.perf_counter()
    for _ in range(10):
        mgr.next_round(present, num_tables)
    elapsed = time.perf_counter() - t0
    print(f"  Doubles: 20+{guest_count}g present {' '*24}{len(present):4d} present  10r  {elapsed*100:7.1f}ms/r")

# Large scale single round timing
print()
for size in [50, 100, 200, 300, 400]:
    roster = [f"P{i}" for i in range(size * 2)]
    present = roster[:size]
    mgr = LeaguePairingManager(roster)
    num_tables = max(1, len(present) // 4)
    t0 = time.perf_counter()
    mgr.next_round(present, num_tables)
    elapsed = time.perf_counter() - t0
    print(f"  Single round: {size:4d} present {' '*31}{elapsed*1000:8.1f}ms  fresh")
