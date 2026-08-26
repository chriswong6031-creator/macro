---
key: CNLI-CALENDAR-PARTITION-YEAR-LEAKED-ACROSS-LOOPS
claim: >
  `TushareAShareSpineCollector.collect_calendars` in
  collectors/china_tushare_spine.py wrote EVERY trade_cal unit into a single
  wrong year partition, because its second loop
  (`for _, _, exchange, segment_start, segment_end in sorted(work)`) never
  unpacked `year` and silently reused the value left bound by the first
  loop — which `_year_segments` (ascending) always leaves at the LAST year
  of the requested range. The verifier `_expected_unit_partition_path`
  independently derives the correct partition from the unit itself
  (`_parse_date(compact_start).year`), so `_set_unit` raised
  `trade_cal/<unit> partition path disagrees with its unit` — but only AFTER
  `_upsert_partition` had already written the rows into the wrong file.
  Measured in the live private store on 2026-08-26:
  `reference/trade_calendar/year=2024.parquet` held 369 rows spanning years
  [2023, 2024] — SSE-2023's 365 rows plus the 4 legitimate 2024-01-01..02
  rows for SSE+SZSE — after canary run 32921678076. The stray 8-space
  over-indentation of that loop body is the fingerprint of the refactor that
  dropped the unpack.
falsifier: >
  Run `python3 -m pytest tests/test_china_tushare_spine.py -q -k
  collect_calendars_writes_each_unit_to_its_own_year_partition` against a
  tree where `collect_calendars` derives its partition from a loop-carried
  `year` rather than `segment_start.year`: it must fail with the
  "partition path disagrees with its unit" SpineError. If that test passes
  on such a tree, this record's mechanism is wrong.
so_what: >
  Two reusable lessons. (1) A writer and its verifier must derive a
  destination from the SAME source of truth; here the fix was to compute
  `_calendar_partition(self.store, segment_start.year)` — the unit's own
  segment, exactly what the verifier parses — which structurally removes the
  defect class rather than patching one instance. (2) A fail-closed
  artifact check that fires during `_set_unit` catches the disagreement but
  does NOT prevent the corrupt write that precedes it: `_upsert_partition`
  had already merged foreign-year rows into the file. So after any
  "partition path disagrees" failure, the store needs repair, not just a
  code fix — the affected partition must be deleted so the corrected code
  rebuilds it (trade_cal is a cheap whole-range fetch, not a paid per-ticker
  leaf, so a rebuild costs ~1 request per exchange-year). Deferred-work
  patterns (`build a work list, sort it, then process`) are where this class
  hides: a name bound by the collection loop stays visible in the processing
  loop and Python raises nothing.
scope:
  - macro
  - collectors/china_tushare_spine.py
  - WS:CN-LIMIT-ALPHA
kind: landmine
confidence: verified
verified_at: 2026-08-26
verified_by: >
  Canary run 32921678076 failed with the exact SpineError raised at
  collectors/china_tushare_spine.py:973 (`_unit_artifact_receipt`) via
  `_set_unit`; the polluted partition was read directly from the live store
  (369 rows, years [2023, 2024]) with
  `python3 -c "import pandas as pd; print(pd.read_parquet('reference/trade_calendar/year=2024.parquet'))"`;
  the fix and its discriminating tests landed in #6446.
---

# trade_cal partition year leaked across loops

Found while driving the CN-Limit bounded canary under
`DEC:CNLI-FABLE-COO-AUTONOMOUS-EXECUTION`. Related to
[[CNLI-TUSHARE-DELISTED-DUMP-CARRIES-NONCANONICAL-LEGACY-CODES]] only by
discovery route — both were latent defects the first real canary exposed
stage by stage, not a shared mechanism.
