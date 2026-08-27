---
key: CNLI-SESSION-CLOCK-AXIS-IGNORES-REQUESTED-RANGE
claim: >
  `compile_market_sessions(store, start, end)` does NOT build the session axis
  from its requested `start`/`end` range. It uses that range only for a
  per-exchange completeness check, then derives coverage-equality, open-session
  equality and the `market_session_position` ordinal from `all_subset` — every
  row in every landed `year=*.parquet` partition, unfiltered by the requested
  range (collectors/china_tushare_spine.py:1841-1847, and the axis itself at
  :1872-1875 via `all_calendar_dates = sorted(opens["SSE"])`). Measured
  2026-08-26 against the real store: calling it with `start=1992-01-01` still
  raises `SpineError: SSE/SZSE calendar-day coverage differs across landed
  partitions`, because the landed SSE 1991 partition remains in scope even
  though 1991 is outside the requested range. Changing the
  `CALENDAR_HISTORY_START` constant therefore does NOT re-anchor the clock.
falsifier: >
  Run, against a store holding an SSE-only pre-epoch year:
  `python3 -c "import sys,pathlib,datetime as dt; sys.path.insert(0,'.');
  from collectors import china_tushare_spine as sp;
  sp.compile_market_sessions(pathlib.Path.home()/'.local/share/macro-dashboard/china_tushare_spine',
  dt.date(1992,1,1), dt.date(2023,12,31))"`.
  This record is falsified if that call succeeds and returns an axis whose first
  `trade_date` is 1992-01-02, because that would mean the requested range does
  bound the axis. It is also falsified if `opens`/`calendar_dates` are shown to
  be derived from the range-restricted `subset` rather than `all_subset`.
so_what: >
  Sol's ruling requires the exact plane to be re-anchored to a frozen epoch and
  pre-epoch history typed `PRE_EPOCH_SOURCE_UNSUPPORTED`. A session that
  implements that by editing the anchor constant and observing green tests will
  ship a no-op at best: the constant feeds `collect_calendars`, but the axis is
  built from whatever is on disk. Worse, the current fail-CLOSED behavior is
  load-bearing but incidental — today the mismatch raises only because SZSE
  lacks 1991 rows while SSE has them. If a pre-epoch partition were ever landed
  for BOTH exchanges (for example if Sol later authorized a partial SZSE 1991),
  the coverage and open-set equality checks would both pass, the axis would
  silently extend backwards, and EVERY `market_session_position` would shift by
  the number of pre-epoch open sessions (255 for SSE 1991) with no error raised.
  The epoch must therefore be enforced BY DEFINITION inside
  `compile_market_sessions` — pre-epoch rows excluded from `calendar_dates`,
  `opens` and the ordinal, and typed rather than silently dropped — not by
  relying on the absence of a file. This is the same fail-open shape the program
  already refused when it declined to relax the `trade_cal` exact-range check.
scope:
  - macro
  - collectors/china_tushare_spine.py
  - WS:CN-LIMIT-ALPHA
kind: constraint
confidence: verified
verified_at: 2026-08-26
verified_by: >
  Direct execution against the private store on 2026-08-26 with
  `CALENDAR_HISTORY_START = 1991-01-01`: `compile_market_sessions(store,
  1991-01-01, 2023-12-31)` raised `SpineError: calendar is incomplete for SZSE:
  ['1991-01-01', ...]` (the range check at collectors/china_tushare_spine.py:1844),
  while `compile_market_sessions(store, 1992-01-01, 2023-12-31)` raised
  `SpineError: SSE/SZSE calendar-day coverage differs across landed partitions`
  (the unfiltered equality check at collectors/china_tushare_spine.py:1848) —
  two different refusals proving the second is not bounded by the requested range.
---

# Re-anchoring the clock is not a constant edit

Minted executing Sol's DEP-EXACT calendar-epoch ruling under
`DEC:CNLI-FABLE-COO-AUTONOMOUS-EXECUTION`, while establishing
[[CNLI-MAINLAND-CALENDAR-EPOCH-1992-JOINT-COMPLETE]].

Same family as [[CNLI-CALENDAR-PARTITION-YEAR-LEAKED-ACROSS-LOOPS]]: a writer
and a verifier disagreeing about which source of truth bounds a calendar
operation. Here the disagreement is between the requested range and the landed
partition set.
