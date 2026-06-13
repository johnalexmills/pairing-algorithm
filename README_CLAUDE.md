# Crokinole Pairing Algorithm — Integration Guide

Drop-in pairing engine for crokinole league apps. Avoids teammate repeats across nights, minimizes table-neighbor repeats across rounds, handles variable attendance.

## Quick Start

```python
from pairing import LeaguePairingManager

mgr = LeaguePairingManager(
    ["Alice", "Bob", "Carol", "Dave", "Eve", "Frank", "Grace", "Henry"],
    state_path="league_state.json"
)

rnd = mgr.next_round(["Alice","Bob","Carol","Dave","Eve","Frank","Grace","Henry"])

rnd["teams"]    # [(Alice,Bob), (Carol,Dave), (Eve,Frank), (Grace,Henry)]
rnd["tables"]   # [(1, (Alice,Bob), (Carol,Dave)), (2, (Eve,Frank), (Grace,Henry))]
rnd["bye"]      # players sitting out
```

Run demo: `python3 demo.py`

## API

### `LeaguePairingManager(all_players, state_path=None)`

**`next_round(present, num_tables=None)` → dict**

| Key | Type | Description |
|-----|------|-------------|
| `round` | `int` | 1-based counter |
| `teams` | `[(str,str)]` | Teams formed |
| `tables` | `[(int, tuple\|None, tuple\|None)]` | (table#, team1, team2) per table |
| `bye` | `[str]` | Players sitting out |

`num_tables` defaults to `max(1, len(present) // 4)`. Max teams = `num_tables * 2`.

**`generate_night(present, num_rounds, num_tables=None)` → list[dict]**

**`save()`** — Persist state to JSON.

**`reset()`** — Clear all history (new season).

## App Lifecycle

```
App launch → Create LeaguePairingManager(roster, state_path)
  ↓
Night starts → mgr.next_round(present) for each round
  ↓
Assign tables → use rnd["tables"]: (table#, team1, team2)
  ↓
Night ends → mgr.save()
```

## Cloud State Persistence

State is a small JSON blob (~few KB). Read on launch, write on save. Two options:

### Option 1: Cloud Storage (GCS) — Simplest

```python
from google.cloud import storage
from pairing import LeaguePairingManager

BUCKET = "croke-league-state"
BLOB = "league_state.json"

class CloudPairingManager(LeaguePairingManager):
    def __init__(self, roster):
        self.client = storage.Client()
        self.bucket = self.client.bucket(BUCKET)
        self.blob = self.bucket.blob(BLOB)
        tmp = "/tmp/league_state.json"
        if self.blob.exists():
            self.blob.download_to_filename(tmp)
        super().__init__(roster, state_path=tmp)

    def save(self):
        super().save()
        self.blob.upload_from_filename(self.state_path)
```

**Pricing:** ~$0.02/month. Ops: zero. State defaults to `STANDARD` storage class.

**Setup:** Enable Cloud Storage API, create bucket, grant `storage.objectUser` role to app service account.

**iOS:** Use Firebase Admin SDK or a Cloud Function wrapper if the app can't call GCS directly (iOS). Pattern: Cloud Function receives state, writes to GCS bucket.

### Option 2: Firestore — If app needs multi-device sync

```python
import firebase_admin
from firebase_admin import credentials, firestore
from pairing import LeaguePairingManager

db = firestore.client()
DOC_REF = db.collection("leagues").document("state")

class FirestorePairingManager(LeaguePairingManager):
    def __init__(self, roster):
        doc = DOC_REF.get()
        tmp = "/tmp/league_state.json"
        if doc.exists:
            import json
            with open(tmp, "w") as f:
                json.dump(doc.to_dict(), f)
        super().__init__(roster, state_path=tmp)

    def save(self):
        super().save()
        import json
        with open(self.state_path) as f:
            DOC_REF.set(json.load(f))
```

**Use when:** Two phones need to share pairings simultaneously (e.g., league admin + scorekeeper). Firestore's real-time sync means a save from one device appears instantly on another.

**Pricing:** ~$0.03/month at this data size.

### Option 3: Cloud SQL — Not recommended

Overkill. The state is a single flat JSON document, not relational data.

## Variable Attendance

Players who don't attend don't affect the state. Their used pairs persist; when they return, the algorithm avoids those pairs.

```python
roster = [f"P{i}" for i in range(50)]
mgr = LeaguePairingManager(roster, "league.json")

nights = [
    ["P0","P1","P2","P3","P4","P5","P6","P7","P8","P9",
     "P10","P11","P12","P13","P14","P15","P16","P17","P18","P19"],
    ["P0","P1","P2","P3","P4","P15","P16","P17","P18","P19",
     "P20","P21","P22","P23","P24","P25","P26","P27","P28","P29"],
]
for i, present in enumerate(nights):
    rounds = mgr.generate_night(present, 5)
    mgr.save()
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
pairing.py               Core engine
test_pairing.py          30 tests
demo.py                  24-player / 5-round demo
README.md                This file
README_ENGINEERS.md      Algorithm deep-dive for engineering review
SPEC.md                  Full specification
```

## Algorithm

See `README_ENGINEERS.md` for: blossom matching detail, optimality proof, constraint analysis, edge case handling.

## Tests

```bash
python3 test_pairing.py
```

No external dependencies (stdlib only).
