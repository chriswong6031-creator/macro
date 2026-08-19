---
key: GD1-LC-EMISSION-LOG-STARTS-BROKEN
claim: >
  data/leadership_crack/forward_log.jsonl contains 15 rows from 2026-07-17
  through 2026-08-18 and the first row is already state=BROKEN. There is no
  emitted pre-break history in this checkout. August 2026 nights 01-04, 06,
  08-11, 14-16 have no LC emission row.
falsifier: >
  python3 -c "import json; from pathlib import Path; rows=[json.loads(l) for l
  in Path('data/leadership_crack/forward_log.jsonl').read_text().splitlines() if
  l.strip()]; print(len(rows), rows[0]['asof'], rows[0]['state'])" printing a
  first asof before 2026-07-17 or a first state other than BROKEN, or n>>15.
so_what: >
  GD-H1 cannot be historically tested from the emission log. A design-era test
  requires a labeled truncate-and-recompute (def_current_cf). Do not treat
  latest.json as intra-day proof. Do not use the 15-row log as mature PIT N.
kind: data
verified_at: 2026-08-19
verified_by: >
  Read data/leadership_crack/forward_log.jsonl: n=15, min asof 2026-07-17
  state=BROKEN dislocation=true; max asof 2026-08-18 state=BROKEN.
scope:
  - macro
  - data/leadership_crack/forward_log.jsonl
  - engine/leadership_crack.py
  - WS:GREY-DEER
confidence: verified
---
