import json
import os
import random

def _pair_key(a, b):
    return (a, b) if a <= b else (b, a)


class RoundRobinPairing:
    """Generates crokinole tournament pairings using circle method.

    Guarantees no two players repeat as teammates until all
    possible pairings are exhausted.

    For N players: N-1 rounds (even N) or N rounds (odd N)
    before full reset.

    Use for single-session tournaments with fixed attendance.
    """

    def __init__(self, players):
        self.players = list(players)
        self.n = len(self.players)
        self.used_pairs = set()
        self.total_pairs = self.n * (self.n - 1) // 2
        self.round_count = 0
        self.history = []

    def _build_schedule(self):
        """Generate one full cycle of pairings via circle method."""
        p = self.players
        n = self.n
        if n < 2:
            return

        has_bye = n % 2 == 1
        idx = list(range(n)) + ([-1] if has_bye else [])
        m = len(idx)

        for _ in range(m - 1):
            teams = []
            bye = []
            for i in range(m // 2):
                a, b = idx[i], idx[m - 1 - i]
                if a == -1:
                    bye.append(p[b])
                elif b == -1:
                    bye.append(p[a])
                else:
                    teams.append((p[a], p[b]))
            yield teams, bye

            idx = [idx[0]] + [idx[-1]] + idx[1:-1]

    def next_round(self):
        if self.n < 2:
            return None

        if len(self.used_pairs) >= self.total_pairs:
            self.used_pairs = set()
            random.shuffle(self.players)

        schedule = list(self._build_schedule())
        if not schedule:
            return None

        for teams, bye in schedule:
            team_pairs = {_pair_key(*t) for t in teams}
            if not team_pairs & self.used_pairs:
                self.used_pairs |= team_pairs
                self.round_count += 1
                rnd = {"round": self.round_count, "teams": teams, "bye": bye}
                self.history.append(rnd)
                return rnd

        teams, bye = schedule[0]
        self.used_pairs |= {_pair_key(*t) for t in teams}
        self.round_count += 1
        rnd = {"round": self.round_count, "teams": teams, "bye": bye}
        self.history.append(rnd)
        return rnd

    def get_pair_stats(self):
        stats = {}
        for rnd in self.history:
            for t in rnd["teams"]:
                key = _pair_key(*t)
                stats[key] = stats.get(key, 0) + 1
        return stats



class LeaguePairingManager:
    """Pairing tracker for recurring league nights with variable attendance.

    Tracks both team-level and table-level pairings.
    Persists state across sessions via JSON file.
    Supports doubles (2 teams per table) and singles (1 match per table).

    Usage:
        mgr = LeaguePairingManager(roster, "state.json")
        r1 = mgr.next_round(["Alice","Bob","Carol","Dave"], num_tables=1)

        # Singles mode
        mgr2 = LeaguePairingManager(roster, mode="singles")
        r = mgr2.next_round(["Alice","Bob","Carol","Dave"], num_tables=2)
        # Returns: {"round": 1, "matches": [("Alice","Bob"), ...], "tables": [...], "bye": []}

        # Singles
        mgr = LeaguePairingManager(roster, mode="singles")
        r1 = mgr.next_round(["Alice","Bob","Carol","Dave"], num_tables=2)
    """

    def __init__(self, all_players, state_path=None, mode="doubles"):
        self.all_players = sorted(all_players)
        self.used_pairs = set()
        self.last_table_rosters = []
        self.player_last_table = {}
        self.round_count = 0
        n = len(self.all_players)
        self.total_possible = n * (n - 1) // 2
        self.state_path = state_path
        self.mode = mode
        self._night_bye_counts = {}
        if state_path and os.path.exists(state_path):
            self._load()

    def _load(self):
        try:
            with open(self.state_path) as f:
                content = f.read().strip()
                if not content:
                    return
                data = json.loads(content)
            self.used_pairs = {tuple(p) for p in data.get("used_pairs", [])}
            self.last_table_rosters = [
                [{str(q) for q in t} for t in r]
                for r in data.get("last_table_rosters", [])
            ]
            self.player_last_table = {
                str(k): v for k, v in data.get("player_last_table", {}).items()
            }
            self.round_count = data.get("round_count", 0)
        except (json.JSONDecodeError, OSError):
            self.used_pairs = set()
            self.last_table_rosters = []
            self.player_last_table = {}
            self.round_count = 0

    def save(self):
        if not self.state_path:
            return
        os.makedirs(os.path.dirname(self.state_path) or ".", exist_ok=True)
        data = self.get_state()
        data["mode"] = self.mode
        with open(self.state_path, "w") as f:
            json.dump(data, f, indent=2)

    def get_state(self):
        return {
            "used_pairs": [list(p) for p in sorted(self.used_pairs)],
            "last_table_rosters": [
                [list(t) for t in r] for r in self.last_table_rosters
            ],
            "player_last_table": dict(self.player_last_table),
            "round_count": self.round_count,
            "mode": self.mode,
        }

    def set_state(self, data):
        self.used_pairs = {tuple(p) for p in data.get("used_pairs", [])}
        self.last_table_rosters = [
            [{str(q) for q in t} for t in r]
            for r in data.get("last_table_rosters", [])
        ]
        self.player_last_table = {
            str(k): v for k, v in data.get("player_last_table", {}).items()
        }
        self.round_count = data.get("round_count", 0)

    def reset(self):
        self.used_pairs = set()
        self.last_table_rosters = []
        self.player_last_table = {}
        self.round_count = 0
        self._night_bye_counts.clear()
        if self.state_path:
            self.save()

    # ── Team matching ──

    def _find_matching(self, players, max_teams=None):
        """Maximum matching avoiding used_pairs.

        Uses Edmonds' blossom algorithm for general graphs,
        guaranteeing correct maximum matching even with odd cycles.

        Args:
            players: list of player names to match.
            max_teams: max teams to form. None = unlimited.

        Returns (teams, unpaired_players).
        """
        n = len(players)
        if n < 2:
            return [], list(players)

        used = self.used_pairs

        # Build adjacency: edge exists if pair not yet used
        adj = [[] for _ in range(n)]
        for i in range(n):
            pi = players[i]
            for j in range(i + 1, n):
                if ((pi, players[j]) if pi < players[j] else (players[j], pi)) not in used:
                    adj[i].append(j)
                    adj[j].append(i)

        # ── Edmonds' blossom algorithm ──────────────────────────
        mate = [-1] * n

        def lca(a, b, base, p):
            seen = [False] * n
            while True:
                a = base[a]
                seen[a] = True
                if mate[a] == -1:
                    break
                a = p[mate[a]]
            while True:
                b = base[b]
                if seen[b]:
                    return b
                b = p[mate[b]]

        def mark_path(match, base, blossom, p, v, b, children):
            while base[v] != b:
                blossom[base[v]] = blossom[base[match[v]]] = True
                p[v] = children
                children = match[v]
                v = p[match[v]]

        def find_augment(root):
            used = [False] * n
            p = [-1] * n
            base = list(range(n))
            q = [root]
            used[root] = True

            while q:
                v = q.pop(0)
                for to in adj[v]:
                    if base[v] == base[to] or mate[v] == to:
                        continue
                    if to == root or (mate[to] != -1
                                      and p[mate[to]] != -1):
                        curbase = lca(v, to, base, p)
                        blossom = [False] * n
                        mark_path(mate, base, blossom, p, v, curbase, to)
                        mark_path(mate, base, blossom, p, to, curbase, v)
                        for i in range(n):
                            if blossom[base[i]]:
                                base[i] = curbase
                                if not used[i]:
                                    used[i] = True
                                    q.append(i)
                    elif p[to] == -1:
                        p[to] = v
                        if mate[to] == -1:
                            return p, to
                        used[mate[to]] = True
                        q.append(mate[to])
            return None, -1

        def augment(p, v):
            while v != -1:
                pv = p[v]
                ppv = mate[pv]
                mate[v] = pv
                mate[pv] = v
                v = ppv

        for i in range(n):
            if mate[i] == -1:
                p_path, v = find_augment(i)
                if p_path is not None:
                    augment(p_path, v)
        # ── end blossom ─────────────────────────────────────────

        teams = [
            (players[i], players[mate[i]])
            for i in range(n)
            if mate[i] != -1 and i < mate[i]
        ]

        if max_teams and len(teams) > max_teams:
            excess_players = []
            for t in teams[max_teams:]:
                excess_players.extend(t)
            teams = teams[:max_teams]
            unpaired = [p for p in players if not any(
                p in t for t in teams
            )]
            return teams, unpaired

        unpaired = [players[i] for i in range(n) if mate[i] == -1]
        return teams, unpaired

    # ── Table assignment ──

    def _table_conflict(self, players_at_table):
        """Repeated table-neighbor pairs across all prior rounds.

        Each prior round where this pair shared a table adds 1
        to the conflict count.  All rounds weighted equally so
        that frequent repeaters are penalized increasingly.
        """
        if not self.last_table_rosters:
            return 0
        conflicts = 0
        for rosters in self.last_table_rosters:
            for i, a in enumerate(players_at_table):
                for b in players_at_table[i + 1:]:
                    for table_set in rosters:
                        if a in table_set and b in table_set:
                            conflicts += 1
                            break
        return conflicts

    def _assign_tables(self, items, num_tables, mode="doubles"):
        """Assign teams (doubles) or matches (singles) to tables.

        Doubles: pick best remaining team-pair per table (4 players).
        Singles: assign each match to a table (2 players).

        Returns list of (table_num, item1|None, item2|None).
        """
        m = len(items)
        if m == 0:
            return [(i + 1, None, None) for i in range(num_tables)]

        def _table_score(item_indices, tn):
            players = []
            for ii in item_indices:
                players.extend(items[ii])
            c = self._table_conflict(players) * 100
            t = 1 if any(
                self.player_last_table.get(p) == tn for p in players
            ) else 0
            return c + t

        if mode == "singles":
            # Each table holds one match (2 players).
            # Greedy: assign highest-conflict match first for fairness.
            scored = [
                (i, _table_score([i], tn))
                for tn, i in enumerate(range(m))
            ]
            scored.sort(key=lambda x: -x[1])  # worst first
            assigned = []
            for idx, (match_idx, _) in enumerate(scored):
                tn = idx + 1
                assigned.append((tn, items[match_idx], None))
            for tn in range(len(assigned) + 1, num_tables + 1):
                assigned.append((tn, None, None))
            return assigned

        # Doubles: pick best remaining team-pair per table (4 players).
        remaining = set(range(m))
        assigned = []

        for tn in range(1, num_tables + 1):
            if not remaining:
                assigned.append((tn, None, None))
                continue
            rlist = list(remaining)

            if len(remaining) >= 2:
                bp = None
                bp_score = float("inf")
                for i in range(len(rlist)):
                    for j in range(i + 1, len(rlist)):
                        s = _table_score(
                            [rlist[i], rlist[j]], tn
                        )
                        if s < bp_score:
                            bp_score = s
                            bp = (rlist[i], rlist[j])
                assigned.append((tn, items[bp[0]], items[bp[1]]))
                remaining.remove(bp[0])
                remaining.remove(bp[1])
            else:
                solo = next(iter(remaining))
                assigned.append((tn, items[solo], None))
                remaining.remove(solo)

        return assigned

    # ── Main API ──

    def next_round(self, present_players, num_tables=None, mode=None):
        """Generate next round for given present players.

        Args:
            present_players: list of player names present this round.
            num_tables: number of tables.
                Doubles defaults to len(present) // 4.
                Singles defaults to len(present) // 2.
            mode: "doubles" or "singles".  Falls back to
                  self.mode set at construction.

        Returns dict:
          Doubles: {round, teams, tables, bye}
            Each table has 2 teams (4 players).
            tables: [(tn, team_tuple|None, team_tuple|None)]
          Singles: {round, matches, tables, bye}
            Each table has 1 match (2 players).
            tables: [(tn, (a,b)|None, None)]
        """
        mode = mode or self.mode
        present = sorted(present_players, key=lambda p: -self._night_bye_counts.get(p, 0))

        if num_tables is None:
            denom = 2 if mode == "singles" else 4
            num_tables = max(1, len(present) // denom)

        if self.total_possible > 0 and len(self.used_pairs) >= self.total_possible:
            self.used_pairs = set()
            random.shuffle(self.all_players)

        self.round_count += 1
        max_teams = num_tables * (1 if mode == "singles" else 2)
        pairs, unpaired = self._find_matching(present, max_teams)

        for p in pairs:
            self.used_pairs.add(_pair_key(*p))

        tables = self._assign_tables(pairs, num_tables, mode=mode)

        # Record table rosters for back-to-back avoidance
        roster = []
        for tn, m1, m2 in tables:
            players_at = set()
            if m1 is not None:
                players_at.update(m1)
            if m2 is not None:
                players_at.update(m2)
            roster.append(players_at)
            for p in players_at:
                self.player_last_table[p] = tn
        self.last_table_rosters.append(roster)

        if self.state_path:
            self.save()

        for p in unpaired:
            self._night_bye_counts[p] = self._night_bye_counts.get(p, 0) + 1

        result = {
            "round": self.round_count,
            "tables": tables,
            "bye": unpaired,
        }
        if mode == "singles":
            result["matches"] = pairs
        else:
            result["teams"] = pairs
        return result

    def generate_night(self, present_players, num_rounds, num_tables=None, mode=None):
        """Generate multiple rounds for one league night."""
        self._night_bye_counts.clear()
        return [
            self.next_round(present_players, num_tables, mode=mode)
            for _ in range(num_rounds)
        ]

    def get_player_pair_counts(self, player):
        counts = {}
        for a, b in self.used_pairs:
            if a == player:
                counts[b] = counts.get(b, 0) + 1
            elif b == player:
                counts[a] = counts.get(a, 0) + 1
        return counts


def assign_tables(teams, num_tables):
    """Quick table assignment without tracking (stateless).

    Returns (tables, overflow) where tables is list of team tuples
    and overflow is list of unplaced teams.
    """
    shuffled = list(teams)
    random.shuffle(shuffled)

    tables = []
    i = 0
    for _ in range(num_tables):
        if i + 1 < len(shuffled):
            tables.append((shuffled[i], shuffled[i + 1]))
            i += 2
        elif i < len(shuffled):
            tables.append((shuffled[i],))
            i += 1
        else:
            tables.append(())
    overflow = shuffled[i:]

    return tables, overflow



