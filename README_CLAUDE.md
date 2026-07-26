# Crokinole Pairing Algorithm — Firebase Integration

Drop-in pairing engine for crokinole league apps running on Firebase. No-repeat teammates across nights, real-time sync via Firestore, variable attendance, auto-detected guest support.

## Migration Guide for AI Agent

If the app already has a pairing algorithm, follow these steps to evaluate and replace it:

### Step 1: Find the existing algorithm

Search the codebase for:

- **Team/match pairing logic**: look for functions that take a list of players and return pairs. Search for patterns like `pair`, `match`, `team`, `round`, `schedule`, `roster`, `bye`. Check both the client app code and any server/cloud functions.
- **State persistence**: look for saved pairing history — arrays of player pairs, round numbers, table assignments. Search for `used_pairs`, `pair_history`, `match_history` in Firestore collections, local storage, or JSON files.
- **Guest handling**: search for `guest`, `visitor`, `drop_in`, `temporary` in pairing context.

### Step 2: Compare correctness

| Criterion | This algorithm | Questions to ask about existing |
|-----------|----------------|---------------------------------|
| No-repeat teammates | Hard constraint via Edmonds blossom + `used_pairs` | Does existing prevent repeats across nights? How? |
| Guest no-repeat within night | Hard constraint via `_night_guest_pairs` | Does existing handle guests at all? |
| Cycle reset | When all roster pairs exhausted, clear + reshuffle | Does existing get stuck when all pairings used? |
| Back-to-back table avoidance | Soft constraint, weight 100 | Does existing consider table assignments? |
| Variable attendance | Handles any subset each night | Does existing require fixed attendance? |
| Singles mode | Same engine, `mode="singles"` | Does existing support singles vs doubles? |
| Crash recovery | All state in Firestore each round | Does existing risk losing night state? |

### Step 3: Compare performance

Run the existing algorithm with the stress test pattern in
`examples/stress_test.py`. Compare ms/round at 50, 100, 200 present.
If existing is slower or fails at scale, replace with this engine.

### Step 4: Swap implementation

The `FirebasePairingManager` class below is the drop-in replacement.
It wraps `LeaguePairingManager` and syncs state+rounds to Firestore.

**Integration pattern:**
1. Collect the roster (all league members) once at construction.
2. For each round, call `next_round(present_players, num_tables)`.
3. For a full night, call `generate_night(present_players, num_rounds)`.
4. Guests auto-detected — just include them in `present_players`.
5. Everything persisted to Firestore automatically.

**Data flow:**
```
App UI  →  FirebasePairingManager.next_round(present)
              ↓
         LeaguePairingManager.next_round(present)
              ↓
         get_state() → Firestore state document
         round result → Firestore rounds/{n} document
              ↓
         App reads round result from Firestore (or return value)
```

**To preserve existing history:**
If the old algorithm has pairing history, convert it to the
`used_pairs` format (`[["Alice","Bob"], ...]`) and pass it via
`set_state()` before generating rounds:
```python
mgr = FirebasePairingManager(roster, league_id="...")
mgr._mgr.set_state({"used_pairs": existing_history})
# Or merge: load from Firestore, add old pairs, write back
```

If the old algorithm cannot export history, reset and start fresh.

### Step 5: Verify

Run `python3 -m pytest tests/` (51 tests covering both modes,
guests, persistence, edge cases). The core engine has zero
dependencies -- only `firebase-admin` is needed for cloud sync.

---

## Capacity

| Metric | Min | Typical | Max | Note |
|--------|-----|---------|-----|------|
| Present per round | 2 | 8–32 | ~400 | Blossom O(n³) bottleneck; 400 present ~800ms/r fresh |
| Roster players | 2 | 8–50 | unlimited | No impact on match speed |
| Teams per round | 1 | 2–8 | `num_tables × 2` | |
| Tables per round | 1 | 2–6 | present // 4 | Default: `max(1, len(present)//4)` |
| Rounds per night | 1 | 3–6 | indefinite | |

Players beyond `num_tables × 2` teams sit out (bye).

**Benchmarked performance (doubles, MacBook M-series):**

| Present | Fresh (ms/r) | Sparse (ms/r) |
|---------|-------------|---------------|
| 20 | 0.2 | 0.0 |
| 50 | 2.1 | 1.6 |
| 100 | 14.8 | 14.0 |
| 200 | 109 | — |
| 300 | 353 | — |
| 400 | 801 | — |

Singles ~3x faster than doubles (half the players per table).

## Architecture

```
┌──────────────────────┐       ┌──────────────────────┐
│  Admin Phone         │       │  Viewer Phone        │
│  generates pairings  │       │  displays pairings   │
│         │            │       │         ▲            │
│         ▼            │       │         │            │
│  LeaguePairingManager│       │  on_snapshot( )      │
│         │            │       │         │            │
│         ▼            │       │         │            │
│  FirestoreAdapter    │       │  FirestoreAdapter    │
│  writes state+round  │       │  listens for changes │
└────────┬─────────────┘       └─────────┬────────────┘
         │                               │
         └───────────────┬───────────────┘
                         ▼
                 ┌───────────────┐
                 │   Firestore   │
                 │  /leagues/    │
                 │  {leagueId}/  │
                 │   state       │
                 │   rounds/{n}  │
                 └───────────────┘
```

Only one device generates pairings (admin). All others subscribe to Firestore and display updates in real time.

## Firestore Data Model

```
leagues/{leagueId}/
  state: {
    used_pairs: [["Alice","Bob"], ...],
    last_table_rosters: [
      [["Alice","Bob","Carol","Dave"], ["Eve","Frank","Grace","Henry"]],
      ...
    ],
    player_last_table: {"Alice": 1, "Bob": 2, ...},
    round_count: 5,
    night_bye_counts: {"Alice": 1, "Bob": 2},
    night_guest_pairs: [["GuestX", "Alice"]],
    table_share_counts: [[["Alice","Bob"], 1], [["Carol","Dave"], 1]],
    present: ["Alice","Bob","Carol","Dave","Eve","Frank","Grace","Henry"],
    num_tables: 2,
    updated_at: Timestamp
  }

  rounds/{round_number}/
    teams: [["Alice","Bob"], ["Carol","Dave"]],
    tables: [
      [1, ["Alice","Bob"], ["Carol","Dave"]],
      [2, ["Eve","Frank"], ["Grace","Henry"]]
    ],
    bye: [],
    mode: "doubles",
    created_at: Timestamp
  }

### Singles mode sample

```
leagues/{leagueId}/
  state: {
    used_pairs: [["Alice","Bob"], ...],
    last_table_rosters: [[{"Alice","Bob"}, {"Carol","Dave"}], ...],
    player_last_table: {"Alice": 1, "Bob": 2, ...},
    round_count: 5,
    mode: "singles",
    night_bye_counts: {"Alice": 1},
    night_guest_pairs: [],
    table_share_counts: [[["Alice","Bob"], 1]],
    present: ["Alice","Bob","Carol","Dave"],
    num_tables: 2,
    updated_at: Timestamp
  }

  rounds/{round_number}/
    matches: [["Alice","Bob"], ["Carol","Dave"]],
    tables: [
      [1, ["Alice","Bob"], None],
      [2, ["Carol","Dave"], None]
    ],
    bye: [],
    mode: "singles",
    created_at: Timestamp
  }
```

## Firebase Adapter

```python
import firebase_admin
from firebase_admin import credentials, firestore
from pairing import LeaguePairingManager


class FirebasePairingManager:
    """Wraps LeaguePairingManager with Firestore sync.

    Zero local files.  State loads from Firestore on init,
    pushes to Firestore after each round.
    Round results stored as separate documents for history.

    Crash-safe: all state (including bye counts, guest pairs,
    table share counts) persisted to Firestore every round
    via get_state().  No in-memory-only fields.

    Performance: Greedy table assignment proven optimal with default
    `num_tables = len(present) // 4`. Only 1 iteration needed.
    400 present completes in ~800ms (doubles) / ~250ms (singles).
    """

    def __init__(self, roster, league_id, cred_path=None, mode="doubles"):
        if not firebase_admin._apps:
            cred = credentials.Certificate(cred_path) if cred_path else None
            firebase_admin.initialize_app(cred)

        self.db = firestore.client()
        self.state_ref = self.db.collection("leagues").document(league_id)
        self.rounds_ref = self.state_ref.collection("rounds")

        self._mgr = LeaguePairingManager(roster, state_path=None, mode=mode)

        doc = self.state_ref.get()
        if doc.exists:
            self._mgr.set_state(doc.to_dict())

    def next_round(self, present_players, num_tables=None, mode=None):
        rnd = self._mgr.next_round(present_players, num_tables, mode=mode)
        self._push_to_firestore(rnd, present_players, num_tables)
        return rnd

    def generate_night(self, present_players, num_rounds, num_tables=None, mode=None):
        rounds = self._mgr.generate_night(present_players, num_rounds, num_tables, mode=mode)
        for rnd in rounds:
            self._push_to_firestore(rnd, present_players, num_tables)
        return rounds

    def reset(self):
        self._mgr.reset()
        self.state_ref.delete()
        for doc in self.rounds_ref.stream():
            doc.reference.delete()

    def _push_to_firestore(self, rnd, present, num_tables):
        is_singles = "matches" in rnd
        match_key = "matches" if is_singles else "teams"
        denom = 2 if is_singles else 4
        self.rounds_ref.document(str(rnd["round"])).set({
            match_key: [list(t) for t in rnd[match_key]],
            "tables": [
                [tn,
                 list(t1) if t1 else None,
                 list(t2) if t2 else None]
                for tn, t1, t2 in rnd["tables"]
            ],
            "bye": rnd["bye"],
            "mode": "singles" if is_singles else "doubles",
            "created_at": firestore.SERVER_TIMESTAMP,
        })

        state = self._mgr.get_state()
        state["present"] = present
        state["num_tables"] = num_tables or max(1, len(present) // denom)
        state["updated_at"] = firestore.SERVER_TIMESTAMP
        self.state_ref.set(state)
```

## App Lifecycle

### Admin device (generates pairings)

```python
roster = ["Alice","Bob","Carol","Dave","Eve","Frank","Grace","Henry"]

# Doubles (default)
mgr = FirebasePairingManager(roster, league_id="summer-league-2026")
rnd = mgr.next_round(present_players)
# rnd["teams"] -> [["Alice","Bob"], ...]

# Singles
mgr_s = FirebasePairingManager(roster, league_id="summer-league-2026", mode="singles")
rnd_s = mgr_s.next_round(present_players)
# rnd_s["matches"] -> [["Alice","Bob"], ...]

# Guests: auto-detected (not in roster), no-repeat within night enforced
rnd = mgr.next_round(["Alice","Bob","Carol","GuestX"])
# GuestX won't pair with same roster member twice in one night
# unless GuestX has paired with every roster member present
```

### Viewer devices (read-only)

```python
import firebase_admin
from firebase_admin import firestore

db = firestore.client()
state_ref = db.collection("leagues").document("summer-league-2026")

def on_round_update(doc_snapshot, changes, read_time):
    data = doc_snapshot[0].to_dict() if doc_snapshot else None
    if not data:
        return
    print(f"Round {data['round_count']}")
    print(f"Teams: {data['teams']}")  # Display in UI
    print(f"Tables: {data['tables']}")

state_ref.collection("rounds").on_snapshot(on_round_update)
```

Or subscribe to the `state` document directly:

```python
def on_state_change(doc_snapshot, changes, read_time):
    data = doc_snapshot[0].to_dict() if doc_snapshot else None
    if data:
        current_round = data["round_count"]
        # Fetch latest round document
        round_doc = state_ref.collection("rounds").document(
            str(current_round)
        ).get()
        if round_doc.exists:
            display_round(round_doc.to_dict())

state_ref.on_snapshot(on_state_change)
```

## Concurrency Safety

If two admin devices could generate rounds simultaneously, use a Firestore transaction:

```python
from google.cloud.firestore import transactional

@transactional
def generate_round_transaction(transaction, state_ref, mgr, present):
    snapshot = state_ref.get(transaction=transaction)
    if not snapshot.exists:
        return None
    mgr._mgr.set_state(snapshot.to_dict())
    rnd = mgr._mgr.next_round(present)
    mgr._push_to_firestore(rnd, present, None)
    return rnd
```

For most leagues, a single admin device is sufficient. Transactions only needed if multiple phones could generate simultaneously.

## Usage

```python
# One admin generates
mgr = FirebasePairingManager(roster, league_id="league-1")

# Results pushed to Firestore automatically
round1 = mgr.next_round(["Alice","Bob","Carol","Dave"])
round2 = mgr.next_round(["Alice","Bob","Carol","Dave"])

# Or generate a full night
night = mgr.generate_night(["Alice","Bob","Carol","Dave"], 5)
```

## Requirements

```
pip install firebase-admin
```

## Constraints

| Rule | Hard/Soft | Detail |
|------|-----------|--------|
| No teammate repeats | **Hard** | Won't repeat until all `n(n-1)/2` roster pairs exhausted |
| Guest no-repeat within night | **Hard** | Guest won't repeat roster partner unless all present roster exhausted |
| Table capacity | **Hard** | At most `num_tables * 2` teams; excess sit out |
| Cycle reset | **Hard** | All roster-roster pairs exhausted → clear and reshuffle |
| Back-to-back avoid | **Soft** | Penalty 100 per repeat table-share pair |
| Table rotation | **Soft** | Penalty 1 per table-number repeat |

## File Structure

```
pairing.py               Core engine (no Firebase dependency)
tests/test_pairing.py    51 tests
examples/demo.py         24-player / 5-round demo
README_CLAUDE.md         This file
README.md                Algorithm deep-dive for engineers
SPEC.md                  Full specification
```

## Tests

```bash
python3 -m pytest tests/
```

Core engine has zero external dependencies. Firebase integration adds `firebase-admin` only.
