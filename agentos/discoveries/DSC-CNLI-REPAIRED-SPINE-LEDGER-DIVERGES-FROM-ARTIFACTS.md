---
key: CNLI-REPAIRED-SPINE-LEDGER-DIVERGES-FROM-ARTIFACTS
claim: >
  Repairing spine partitions in place leaves the collection ledger asserting
  units that no longer have artifacts. Measured 2026-08-26 on the private store
  after the in-place calendar repair shipped in PR #6446: `collection_state.json`
  carries `trade_cal` units `SSE:20240101:20240102` and `SZSE:20240101:20240102`
  with `status: "complete"` and `row_count: 2`, both naming partition
  `reference/trade_calendar/year=2024.parquet`, while that file does not exist —
  the directory holds exactly 33 partitions spanning 1991..2023. The ledger is
  wrong, but the readiness predicate is NOT: `_unit_done` returns False for both
  units and True for the other 65, because its `unit_artifact_receipts` check
  (collectors/china_tushare_spine.py:1337-1346) recomputes receipts against the
  store and fails closed when the artifact is missing. Status alone is therefore
  not evidence a unit landed.
falsifier: >
  Run against a spine store:
  `python3 -c "import json,pathlib,sys; sys.path.insert(0,'.');
  from collectors import china_tushare_spine as sp;
  S=pathlib.Path.home()/'.local/share/macro-dashboard/china_tushare_spine';
  st=json.loads((S/'collection_state.json').read_text());
  print([k for k in st['units']['trade_cal'] if not sp._unit_done(st,S,'trade_cal',k)])"`.
  This record is falsified if every unit whose `status` is `complete` also has a
  readable partition at its recorded path, or if `_unit_done` returns True for a
  unit whose partition is absent — the latter would mean the artifact-receipt
  check is not fail-closed and would be a far more serious finding than this one.
so_what: >
  This is the measured instance behind Sol's instruction to rebuild affected
  private spine partitions cleanly rather than promote a repaired-in-place
  contaminated store. An in-place repair rewrites artifacts without reconciling
  the ledger that describes them, so the two drift silently; a later session
  reading `status` alone — from a summary, a handoff, or a manifest — will
  conclude a unit landed when its bytes are gone. The safe read is
  `_unit_done`, never `status`, and the safe remedy for a contaminated store is
  a clean re-collection, not another patch over the same bytes. It also means
  the `unit_artifact_receipts` comparison is load-bearing rather than
  belt-and-braces: it is the only thing standing between a lying ledger and a
  session clock compiled over missing data, so it must never be weakened into a
  warning or made conditional on status.
scope:
  - macro
  - collectors/china_tushare_spine.py
  - WS:CN-LIMIT-ALPHA
kind: constraint
confidence: verified
verified_at: 2026-08-26
verified_by: >
  On 2026-08-26 the private store's `collection_state.json` reported 67 of 67
  `trade_cal` units with `status: "complete"`, while
  `find <store> -name '*.parquet'` under `reference/trade_calendar` returned 33
  files covering 1991..2023 with no `year=2024.parquet`; evaluating
  `collectors.china_tushare_spine._unit_done` over all 67 units returned False
  for exactly the two 2024 units and True for the remaining 65.
---

# A repaired store's ledger outlives its artifacts

Minted while executing Sol's DEP-EXACT calendar-epoch ruling under
`DEC:CNLI-FABLE-COO-AUTONOMOUS-EXECUTION`. The contamination originates in the
repair for [[CNLI-CALENDAR-PARTITION-YEAR-LEAKED-ACROSS-LOOPS]], and is the
reason the epoch re-anchor ships with a clean rebuild rather than another
in-place fix — see [[CNLI-MAINLAND-CALENDAR-EPOCH-1992-JOINT-COMPLETE]] and
[[CNLI-SESSION-CLOCK-AXIS-IGNORES-REQUESTED-RANGE]].
