# Crokinole Pairing Algorithm — Firebase Integration

Drop-in pairing engine for crokinole league apps running on Firebase. No-repeat teammates across nights, real-time sync via Firestore, variable attendance.

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

    Performance: Greedy table assignment proven optimal with default
    `num_tables = len(present) // 4`. Only 1 iteration needed.
    """

    def __init__(self, roster, league_id, cred_path=None):
        if not firebase_admin._apps:
            cred = credentials.Certificate(cred_path) if cred_path else None
            firebase_admin.initialize_app(cred)

        self.db = firestore.client()
        self.state_ref = self.db.collection("leagues").document(league_id)
        self.rounds_ref = self.state_ref.collection("rounds")

        self._mgr = LeaguePairingManager(roster, state_path=None)

        doc = self.state_ref.get()
        if doc.exists:
            self._mgr.set_state(doc.to_dict())

    def next_round(self, present_players, num_tables=None):
        rnd = self._mgr.next_round(present_players, num_tables)
        self._push_to_firestore(rnd, present_players, num_tables)
        return rnd

    def generate_night(self, present_players, num_rounds, num_tables=None):
        rounds = self._mgr.generate_night(present_players, num_rounds, num_tables)
        for rnd in rounds:
            self._push_to_firestore(rnd, present_players, num_tables)
        return rounds

    def reset(self):
        self._mgr.reset()
        self.state_ref.delete()
        for doc in self.rounds_ref.stream():
            doc.reference.delete()

    def _push_to_firestore(self, rnd, present, num_tables):
        self.rounds_ref.document(str(rnd["round"])).set({
            "teams": [list(t) for t in rnd["teams"]],
            "tables": [
                [tn,
                 list(t1) if t1 else None,
                 list(t2) if t2 else None]
                for tn, t1, t2 in rnd["tables"]
            ],
            "bye": rnd["bye"],
            "created_at": firestore.SERVER_TIMESTAMP,
        })

        state = self._mgr.get_state()
        state["present"] = present
        state["num_tables"] = num_tables or max(1, len(present) // 4)
        state["updated_at"] = firestore.SERVER_TIMESTAMP
        self.state_ref.set(state)
```

## App Lifecycle

### Admin device (generates pairings)

```python
roster = ["Alice","Bob","Carol","Dave","Eve","Frank","Grace","Henry"]
mgr = FirebasePairingManager(roster, league_id="summer-league-2026")

# Each round
rnd = mgr.next_round(present_players)
# Round immediately available in Firestore for all devices
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
    # The round_count check ensures no double-generation
    mgr._mgr.round_count = snapshot.get("round_count")
    mgr._mgr.used_pairs = {tuple(p) for p in snapshot.get("used_pairs", [])}
    # ... load full state ...
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
| No teammate repeats | **Hard** | Won't repeat until all `n(n-1)/2` pairs exhausted |
| Table capacity | **Hard** | At most `num_tables * 2` teams; excess sit out |
| Cycle reset | **Hard** | All pairs exhausted → clear and reshuffle |
| Back-to-back avoid | **Soft** | Penalty 100 per repeat table-share pair |
| Table rotation | **Soft** | Penalty 1 per table-number repeat |

## File Structure

```
pairing.py               Core engine (no Firebase dependency)
test_pairing.py          30 tests
demo.py                  24-player / 5-round demo
README_CLAUDE.md         This file
README.md                Algorithm deep-dive for engineers
SPEC.md                  Full specification
```

## Tests

```bash
python3 test_pairing.py
```

Core engine has zero external dependencies. Firebase integration adds `firebase-admin` only.
