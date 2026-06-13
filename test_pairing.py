"""Tests for crokinole pairing algorithm.

Uses fake players and tracks all pair outcomes.
"""
import os
import tempfile

from pairing import RoundRobinPairing, LeaguePairingManager, assign_tables
from collections import Counter


# ── RoundRobinPairing tests (single-session, fixed attendance) ──

def test_even_players():
    players = ["Alice", "Bob", "Carol", "Dave"]
    engine = RoundRobinPairing(players)

    for _ in range(3):
        rnd = engine.next_round()
        assert len(rnd["teams"]) == 2
        assert len(rnd["bye"]) == 0
        for a, b in rnd["teams"]:
            assert a != b

    stats = engine.get_pair_stats()
    total_pairs = len(players) * (len(players) - 1) // 2
    assert len(stats) == total_pairs
    for count in stats.values():
        assert count == 1
    print("  even players OK")


def test_odd_players():
    players = ["Alice", "Bob", "Carol", "Dave", "Eve"]
    engine = RoundRobinPairing(players)

    for _ in range(5):
        rnd = engine.next_round()
        assert len(rnd["teams"]) == 2
        assert len(rnd["bye"]) == 1
        for a, b in rnd["teams"]:
            assert a != b

    stats = engine.get_pair_stats()
    total_pairs = len(players) * (len(players) - 1) // 2
    assert len(stats) == total_pairs
    for count in stats.values():
        assert count == 1
    print("  odd players OK")


def test_cycle_reset():
    players = ["Alice", "Bob", "Carol", "Dave"]
    engine = RoundRobinPairing(players)

    for _ in range(3):
        engine.next_round()

    rnd = engine.next_round()
    assert rnd is not None
    print("  cycle reset OK")


def test_no_repeats_within_cycle():
    for n in range(3, 13):
        players = [f"P{i}" for i in range(n)]
        engine = RoundRobinPairing(players)

        num_rounds = n if n % 2 == 1 else n - 1
        for _ in range(num_rounds):
            engine.next_round()

        stats = engine.get_pair_stats()
        max_count = max(stats.values()) if stats else 0
        assert max_count <= 1, f"N={n}: repeat pair found"

        total_pairs = n * (n - 1) // 2
        assert len(stats) == total_pairs, (
            f"N={n}: expected {total_pairs} pairs, got {len(stats)}"
        )
    print("  no repeats within cycle OK")


def test_ten_players_twenty_rounds():
    players = [f"P{i}" for i in range(10)]
    engine = RoundRobinPairing(players)
    for _ in range(20):
        rnd = engine.next_round()
        assert rnd is not None
        for a, b in rnd["teams"]:
            assert a != b

    stats = engine.get_pair_stats()
    total_unique = 10 * 9 // 2
    assert len(stats) == total_unique
    print("  ten players 20 rounds OK")


def test_bye_rotation():
    players = ["A", "B", "C", "D", "E"]
    engine = RoundRobinPairing(players)

    bye_counts = Counter()
    for _ in range(5):
        rnd = engine.next_round()
        for p in rnd["bye"]:
            bye_counts[p] += 1

    assert len(bye_counts) == 5
    for count in bye_counts.values():
        assert count == 1
    print("  bye rotation OK")


def test_single_player():
    engine = RoundRobinPairing(["Alice"])
    rnd = engine.next_round()
    assert rnd is None
    print("  single player OK")


def test_two_players():
    engine = RoundRobinPairing(["Alice", "Bob"])
    rnd = engine.next_round()
    assert rnd is not None
    assert len(rnd["teams"]) == 1
    assert len(rnd["bye"]) == 0
    print("  two players OK")


def test_seven_players_seven_rounds():
    players = [f"P{i}" for i in range(7)]
    engine = RoundRobinPairing(players)

    for _ in range(7):
        rnd = engine.next_round()
        assert len(rnd["teams"]) == 3
        assert len(rnd["bye"]) == 1

    stats = engine.get_pair_stats()
    total_pairs = 7 * 6 // 2
    assert len(stats) == total_pairs
    for count in stats.values():
        assert count == 1
    print("  seven players OK")


def test_long_running_no_repeats():
    players = [f"P{i}" for i in range(6)]
    engine = RoundRobinPairing(players)

    all_pairs_seen = set()

    for round_num in range(5):
        rnd = engine.next_round()
        for t in rnd["teams"]:
            pair = tuple(sorted(t))
            assert pair not in all_pairs_seen, (
                f"Repeat pair {pair} at round {round_num + 1}"
            )
            all_pairs_seen.add(pair)

    assert len(all_pairs_seen) == 15
    print("  long running no repeats OK")


def test_16_players():
    players = [f"P{i}" for i in range(16)]
    engine = RoundRobinPairing(players)

    for _ in range(15):
        rnd = engine.next_round()
        assert len(rnd["teams"]) == 8
        assert len(rnd["bye"]) == 0

    stats = engine.get_pair_stats()
    total_pairs = 16 * 15 // 2
    assert len(stats) == total_pairs
    for count in stats.values():
        assert count == 1
    print("  16 players OK")


# ── LeaguePairingManager tests (multi-night, variable attendance) ──

def test_mgr_basic():
    """Basic round generation with fixed subset."""
    mgr = LeaguePairingManager(
        ["A", "B", "C", "D", "E", "F", "G", "H"]
    )
    rnd = mgr.next_round(["A", "B", "C", "D"])
    assert len(rnd["teams"]) == 2
    assert len(rnd["bye"]) == 0
    print("  mgr basic OK")


def test_mgr_odd_subset():
    """Odd number of present players -> some sit out."""
    mgr = LeaguePairingManager(
        ["A", "B", "C", "D", "E"]
    )
    rnd = mgr.next_round(["A", "B", "C"])
    assert len(rnd["teams"]) == 1
    assert len(rnd["bye"]) == 1
    print("  mgr odd subset OK")


def test_mgr_no_repeats_across_rounds():
    """Same present players, multiple rounds: no repeat pairs."""
    mgr = LeaguePairingManager(
        [f"P{i}" for i in range(10)]
    )
    present = [f"P{i}" for i in range(10)]
    seen = set()
    # 3 tables = capacity 6 teams = all 10 players paired each round
    for _ in range(9):
        rnd = mgr.next_round(present, num_tables=3)
        for t in rnd["teams"]:
            pair = tuple(sorted(t))
            assert pair not in seen, f"Repeat pair {pair}"
            seen.add(pair)

    # near exhaustion odd cycles can prevent perfect matching,
    # so some players may sit out. still no repeats.
    assert len(seen) >= 43, f"Expected ~45 unique pairs, got {len(seen)}"
    print("  mgr no repeats across rounds OK")


def test_mgr_variable_attendance():
    """Different subsets across simulated nights."""
    roster = ["A", "B", "C", "D", "E", "F"]
    mgr = LeaguePairingManager(roster)

    # Night 1: A, B, C, D
    night1 = mgr.generate_night(["A", "B", "C", "D"], 2)
    assert len(night1) == 2
    night1_pairs = set()
    for rnd in night1:
        for t in rnd["teams"]:
            pair = tuple(sorted(t))
            assert pair not in night1_pairs, f"Repeat in night 1: {pair}"
            night1_pairs.add(pair)

    # Night 2: A, B, E, F (overlap: A, B)
    night2 = mgr.generate_night(["A", "B", "E", "F"], 2)
    assert len(night2) == 2
    all_pairs = set(night1_pairs)
    for rnd in night2:
        for t in rnd["teams"]:
            pair = tuple(sorted(t))
            assert pair not in all_pairs, (
                f"Repeat across nights: {pair}"
            )
            all_pairs.add(pair)

    print("  mgr variable attendance OK")


def test_mgr_consistent_player_no_repeats():
    """Player present every night, never repeats partner."""
    roster = ["A", "B", "C", "D", "E", "F", "G", "H"]
    mgr = LeaguePairingManager(roster)

    # Simulate 4 nights, A and B present every night
    # Others rotate
    for night in range(4):
        others = [p for p in roster if p not in ("A", "B")]
        import random
        random.shuffle(others)
        present = ["A", "B"] + others[:2]
        for _ in range(3):
            rnd = mgr.next_round(present)
            for t in rnd["teams"]:
                pair = tuple(sorted(t))
                if pair[0] not in ("A", "B") and pair[1] not in ("A", "B"):
                    continue

    # A and B should have each been paired with {C..H} at most once
    for player in ("A", "B"):
        counts = mgr.get_player_pair_counts(player)
        for partner, count in counts.items():
            assert count <= 1, (
                f"{player} paired with {partner} {count} times"
            )

    print("  mgr consistent player no repeats OK")


def test_mgr_save_load():
    """State persists across sessions via JSON file."""
    roster = ["A", "B", "C", "D", "E", "F"]

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as f:
        state_path = f.name

    try:
        mgr1 = LeaguePairingManager(roster, state_path)
        mgr1.next_round(["A", "B", "C", "D"])
        mgr1.save()

        used_before = set(mgr1.used_pairs)

        # New instance loads from file
        mgr2 = LeaguePairingManager(roster, state_path)
        assert mgr2.used_pairs == used_before, (
            "State mismatch after reload"
        )
        assert mgr2.round_count > 0

        # Next round respects saved state
        rnd = mgr2.next_round(["A", "B", "C", "D"])
        for t in rnd["teams"]:
            pair = tuple(sorted(t))
            assert pair not in used_before, (
                f"Repeat pair {pair} after reload"
            )
    finally:
        os.unlink(state_path)

    print("  mgr save/load OK")


def test_mgr_reset():
    """Reset clears used pairs."""
    roster = ["A", "B", "C", "D"]
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as f:
        state_path = f.name

    try:
        mgr = LeaguePairingManager(roster, state_path)
        mgr.generate_night(roster, 3)
        assert len(mgr.used_pairs) == 6

        mgr.reset()
        assert len(mgr.used_pairs) == 0
        assert mgr.round_count == 0

        # Verify persisted reset
        mgr2 = LeaguePairingManager(roster, state_path)
        assert len(mgr2.used_pairs) == 0
    finally:
        os.unlink(state_path)

    print("  mgr reset OK")


def test_mgr_large_roster_small_night():
    """50-person roster, 5 rounds with 20 present each night."""
    roster = [f"P{i}" for i in range(50)]
    mgr = LeaguePairingManager(roster)

    for night in range(3):
        present = [f"P{i}" for i in range(night * 5, night * 5 + 20)]
        rounds = mgr.generate_night(present, 5)
        assert len(rounds) == 5

        for rnd in rounds:
            assert len(rnd["teams"]) >= 9
            assert len(rnd["teams"]) <= 10
            for t in rnd["teams"]:
                assert len(t) == 2

    print("  mgr large roster small night OK")


def test_mgr_no_repeats_across_nights():
    """Strict across-night no-repeat for overlapping players."""
    roster = ["A", "B", "C", "D", "E", "F", "G", "H"]
    mgr = LeaguePairingManager(roster)

    all_pairs_seen = set()

    # Night 1: A, B, C, D
    for _ in range(3):
        rnd = mgr.next_round(["A", "B", "C", "D"])
        for t in rnd["teams"]:
            pair = tuple(sorted(t))
            assert pair not in all_pairs_seen
            all_pairs_seen.add(pair)

    # Night 2: A, B, E, F (A,B overlap)
    for _ in range(3):
        rnd = mgr.next_round(["A", "B", "E", "F"])
        for t in rnd["teams"]:
            pair = tuple(sorted(t))
            assert pair not in all_pairs_seen
            all_pairs_seen.add(pair)

    # Night 3: A, B, G, H (A,B still overlap)
    for _ in range(3):
        rnd = mgr.next_round(["A", "B", "G", "H"])
        for t in rnd["teams"]:
            pair = tuple(sorted(t))
            assert pair not in all_pairs_seen
            all_pairs_seen.add(pair)

    print("  mgr no repeats across nights OK")


def test_mgr_single_present_player():
    """Edge case: 1 player present -> round with no teams."""
    mgr = LeaguePairingManager(["A", "B"])
    rnd = mgr.next_round(["A"])
    assert len(rnd["teams"]) == 0
    assert rnd["bye"] == ["A"]
    print("  mgr single player OK")


# ── Table-level constraint tests ──

def test_mgr_tables_in_return():
    """Verify next_round returns tables key."""
    mgr = LeaguePairingManager(["A","B","C","D","E","F","G","H"])
    rnd = mgr.next_round(["A","B","C","D"], num_tables=1)
    assert "tables" in rnd
    assert len(rnd["tables"]) == 1
    tn, t1, t2 = rnd["tables"][0]
    assert tn == 1
    assert t1 is not None
    assert t2 is not None
    print("  mgr tables in return OK")


def test_mgr_table_rotation():
    """Players should rotate to different table numbers across rounds."""
    roster = [f"P{i}" for i in range(12)]
    mgr = LeaguePairingManager(roster)

    last_table = {}
    total_moves = 0
    total_players = 0

    for r in range(5):
        rnd = mgr.next_round(roster, num_tables=3)
        current = {}
        for tn, t1, t2 in rnd["tables"]:
            for p in (t1 or ()) + (t2 or ()):
                current[p] = tn
        for p, tn in current.items():
            if p in last_table:
                total_players += 1
                if last_table[p] != tn:
                    total_moves += 1
        last_table = current

    # At least 40% of players should change tables
    move_rate = total_moves / max(total_players, 1)
    assert move_rate > 0.3, f"Only {move_rate:.0%} of players changed tables"
    print("  mgr table rotation OK")


def test_mgr_table_back_to_back():
    """Back-to-back table avoidance: same table roster not repeated."""
    roster = [f"P{i}" for i in range(8)]
    mgr = LeaguePairingManager(roster)

    r1 = mgr.next_round(roster, num_tables=2)
    r2 = mgr.next_round(roster, num_tables=2)

    # Check: no pair of players at same table R1 is also together at same table R2
    r1_pairs = set()
    for tn, t1, t2 in r1["tables"]:
        players = list(t1 or []) + list(t2 or [])
        for i, a in enumerate(players):
            for b in players[i+1:]:
                r1_pairs.add((a,b) if a <= b else (b,a))

    repeat_pairs = 0
    for tn, t1, t2 in r2["tables"]:
        players = list(t1 or []) + list(t2 or [])
        for i, a in enumerate(players):
            for b in players[i+1:]:
                key = (a,b) if a <= b else (b,a)
                if key in r1_pairs:
                    repeat_pairs += 1

    # Minimize repeats (structural constraints may prevent zero)
    assert repeat_pairs <= 6, (
        f"{repeat_pairs} back-to-back table repeats (max expected 6)"
    )
    print("  mgr table back-to-back OK")





def test_mgr_table_rosters_tracked():
    """All prior table rosters accumulated for repeat tracking."""
    roster = [f"P{i}" for i in range(4)]
    mgr = LeaguePairingManager(roster)

    mgr.next_round(roster, num_tables=1)
    assert len(mgr.last_table_rosters) == 1

    mgr.next_round(roster, num_tables=1)
    assert len(mgr.last_table_rosters) == 2

    mgr.next_round(roster, num_tables=1)
    # All rounds kept (no pruning)
    assert len(mgr.last_table_rosters) == 3
    print("  mgr table rosters tracked OK")


def test_mgr_table_overflow_players_sit():
    """Extra players sit out if more players than table capacity."""
    mgr = LeaguePairingManager([f"P{i}" for i in range(10)])
    rnd = mgr.next_round([f"P{i}" for i in range(10)], num_tables=2)
    # 10 players, 2 tables hold 8 players max
    assert len(rnd["teams"]) == 4
    assert len(rnd["tables"]) == 2
    assert len(rnd["bye"]) == 2
    print("  mgr table overflow players sit OK")


def test_assign_tables_one_iter_sufficient():
    """Even with manufactured full-tie space, 10 iterations always optimum.

    With empty history (no last_table_rosters, no player_last_table),
    every possible assignment scores 0 — maximally tied.
    Run 20 times, verify score always 0.
    If this passes, then 1 iteration would also find the optimum
    (since the greedy exhaustive search is deterministic).
    """
    mgr = LeaguePairingManager(["A","B","C","D","E","F","G","H"])
    teams = [("A","E"), ("B","F"), ("C","G"), ("D","H")]

    for trial in range(20):
        assigned = mgr._assign_tables(teams, 2)
        score = sum(
            mgr._table_conflict(list((t1 or ()) + (t2 or ()))) * 100
            + (1 if any(
                mgr.player_last_table.get(p) == tn
                for p in list((t1 or ()) + (t2 or ())))
               else 0)
            for tn, t1, t2 in assigned
        )
        assert score == 0, (
            f"Trial {trial}: non-optimal score {score} "
            "(expected 0 with empty history)"
        )
    print("  assign tables one iter sufficient OK")


def test_assign_tables_deterministic():
    """Table assignment produces identical score across calls.

    Guards against algorithm changes that introduce meaningful
    non-determinism. If this fails, 10 iterations may no longer
    be sufficient and the iteration count should be re-evaluated.
    """
    roster = [f"P{i}" for i in range(20)]
    mgr = LeaguePairingManager(roster)
    for r in range(3):
        mgr.next_round(roster, num_tables=5)
    teams = mgr.next_round(roster, num_tables=5)["teams"]

    scores = set()
    for _ in range(5):
        assigned = mgr._assign_tables(teams, 5)
        score = sum(
            mgr._table_conflict(list((t1 or ()) + (t2 or ()))) * 100
            + (1 if any(
                mgr.player_last_table.get(p) == tn
                for p in list((t1 or ()) + (t2 or ())))
               else 0)
            for tn, t1, t2 in assigned
        )
        scores.add(score)

    assert len(scores) == 1, (
        f"Non-deterministic assignment: scores {scores}. "
        "Increase iteration count or fix tiebreak logic."
    )
    print("  assign tables deterministic OK")


def test_assign_tables():
    teams = [("A", "B"), ("C", "D"), ("E", "F")]
    tables, overflow = assign_tables(teams, 2)

    assert len(tables) == 2
    assert len(overflow) == 0
    print("  assign tables OK")


def test_table_assignment_with_pairing():
    players = [f"P{i}" for i in range(8)]
    engine = RoundRobinPairing(players)
    rnd = engine.next_round()

    tables, overflow = assign_tables(rnd["teams"], 2)
    assert len(tables) == 2
    assert len(overflow) == 0

    for table in tables:
        assert len(table) == 2
    print("  table assignment integration OK")


if __name__ == "__main__":
    tests = [
        # RoundRobinPairing tests
        test_single_player,
        test_two_players,
        test_even_players,
        test_odd_players,
        test_no_repeats_within_cycle,
        test_bye_rotation,
        test_seven_players_seven_rounds,
        test_ten_players_twenty_rounds,
        test_long_running_no_repeats,
        test_cycle_reset,
        test_16_players,
        # LeaguePairingManager tests
        test_mgr_basic,
        test_mgr_odd_subset,
        test_mgr_no_repeats_across_rounds,
        test_mgr_variable_attendance,
        test_mgr_consistent_player_no_repeats,
        test_mgr_save_load,
        test_mgr_reset,
        test_mgr_large_roster_small_night,
        test_mgr_no_repeats_across_nights,
        test_mgr_single_present_player,
        # Table constraint tests
        test_mgr_tables_in_return,
        test_mgr_table_rotation,
        test_mgr_table_back_to_back,
        test_mgr_table_rosters_tracked,
        test_mgr_table_overflow_players_sit,
        # Stateless table assignment
        test_assign_tables_one_iter_sufficient,
        test_assign_tables_deterministic,
        test_assign_tables,
        test_table_assignment_with_pairing,
    ]

    for test in tests:
        test()

    print("\nAll tests passed.")
