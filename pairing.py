import json
import os
import random
from collections import Counter, deque
from itertools import combinations

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

    Guests: any player in present_players but not in all_players is
    treated as a guest.  Within a single night, a guest will not be
    paired with the same roster member twice unless the guest has
    already paired with every roster member present that night.

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
        self._roster_set = set(self.all_players)
        self._night_guest_pairs = set()
        self._table_share_counts = Counter()
        self._roster_pair_count = 0
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
            self._night_bye_counts = dict(data.get("night_bye_counts", {}))
            self._night_guest_pairs = {
                tuple(p) for p in data.get("night_guest_pairs", [])
            }
            self._roster_pair_count = sum(
                1 for p in self.used_pairs
                if p[0] in self._roster_set and p[1] in self._roster_set
            )
            table_counts = data.get("table_share_counts")
            if table_counts is not None:
                self._table_share_counts = Counter({
                    tuple(k): v for k, v in table_counts
                })
            else:
                self._rebuild_table_share_counts()
        except (json.JSONDecodeError, OSError):
            self.used_pairs = set()
            self.last_table_rosters = []
            self.player_last_table = {}
            self.round_count = 0
            self._night_bye_counts = {}
            self._night_guest_pairs = set()
            self._table_share_counts = Counter()
            self._roster_pair_count = 0

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
            "night_bye_counts": dict(self._night_bye_counts),
            "night_guest_pairs": [list(p) for p in sorted(self._night_guest_pairs)],
            "table_share_counts": [
                [list(k), v] for k, v in self._table_share_counts.items()
            ],
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
        self._night_bye_counts = dict(data.get("night_bye_counts", {}))
        self._night_guest_pairs = {
            tuple(p) for p in data.get("night_guest_pairs", [])
        }
        self._roster_pair_count = sum(
            1 for p in self.used_pairs
            if p[0] in self._roster_set and p[1] in self._roster_set
        )
        table_counts = data.get("table_share_counts")
        if table_counts is not None:
            self._table_share_counts = Counter({
                tuple(k): v for k, v in table_counts
            })
        else:
            self._rebuild_table_share_counts()

    def reset(self):
        self.used_pairs = set()
        self.last_table_rosters = []
        self.player_last_table = {}
        self.round_count = 0
        self._night_bye_counts.clear()
        self._night_guest_pairs.clear()
        self._table_share_counts.clear()
        self._roster_pair_count = 0
        if self.state_path:
            self.save()

    def _rebuild_table_share_counts(self):
        """Rebuild table_share_counts from last_table_rosters."""
        counts = Counter()
        for rosters in self.last_table_rosters:
            seen_this_round = set()
            for table_set in rosters:
                players = list(table_set)
                for a, b in combinations(players, 2):
                    key = _pair_key(a, b)
                    if key not in seen_this_round:
                        counts[key] += 1
                        seen_this_round.add(key)
        self._table_share_counts = counts

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
        roster_set = self._roster_set
        present_roster = {p for p in players if p in roster_set}

        # Build guest partner lookup: guest -> set of roster partners this night
        # (only partners present this round)
        guest_partner_map = {}
        if self._night_guest_pairs:
            for g, r in self._night_guest_pairs:
                if r in present_roster:
                    s = guest_partner_map.get(g)
                    if s is None:
                        guest_partner_map[g] = {r}
                    else:
                        s.add(r)

        # Build adjacency: edge exists if pair not yet used
        # and (for guest-roster pairs) not already paired this night
        # unless guest has paired with all present roster members.
        adj = [[] for _ in range(n)]
        for i in range(n):
            pi = players[i]
            for j in range(i + 1, n):
                pj = players[j]
                key = _pair_key(pi, pj)
                if key in used:
                    continue
                if self._night_guest_pairs and key in self._night_guest_pairs:
                    pi_roster = pi in roster_set
                    pj_roster = pj in roster_set
                    if pi_roster != pj_roster:
                        guest = pj if pi_roster else pi
                        if guest_partner_map.get(guest, set()) < present_roster:
                            continue
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
            q = deque([root])
            used[root] = True

            while q:
                v = q.popleft()
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
            teams = teams[:max_teams]
            paired = {p for t in teams for p in t}
            unpaired = [p for p in players if p not in paired]
            return teams, unpaired

        unpaired = [players[i] for i in range(n) if mate[i] == -1]
        return teams, unpaired

    # ── Table assignment ──

    def _table_conflict(self, players_at_table):
        """Repeated table-neighbor pairs across all prior rounds.

        Uses precomputed Counter for O(p²) lookup instead of
        iterating all prior rosters.  p = players_at_table ≤ 4.
        """
        conflicts = 0
        for a, b in combinations(players_at_table, 2):
            conflicts += self._table_share_counts.get(_pair_key(a, b), 0)
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

        if self.total_possible > 0 and self._roster_pair_count >= self.total_possible:
            self.used_pairs = set()
            self._roster_pair_count = 0
            random.shuffle(self.all_players)

        self.round_count += 1
        max_teams = num_tables * (1 if mode == "singles" else 2)
        pairs, unpaired = self._find_matching(present, max_teams)

        for p in pairs:
            key = _pair_key(*p)
            self.used_pairs.add(key)
            a, b = p
            if (a in self._roster_set) != (b in self._roster_set):
                self._night_guest_pairs.add(_pair_key(a, b))
            elif a in self._roster_set:
                self._roster_pair_count += 1

        tables = self._assign_tables(pairs, num_tables, mode=mode)

        # Record table rosters for back-to-back avoidance
        roster = []
        seen_this_round = set()
        for tn, m1, m2 in tables:
            players_at = set()
            if m1 is not None:
                players_at.update(m1)
            if m2 is not None:
                players_at.update(m2)
            roster.append(players_at)
            for p in players_at:
                self.player_last_table[p] = tn
            for a, b in combinations(players_at, 2):
                key = _pair_key(a, b)
                if key not in seen_this_round:
                    self._table_share_counts[key] += 1
                    seen_this_round.add(key)
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
        self._night_guest_pairs.clear()
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



