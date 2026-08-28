---
key: CNLI-MAINLAND-CALENDAR-EPOCH-1992-JOINT-COMPLETE
claim: >
  1992 is the earliest calendar year for which TuShare `trade_cal` supplies a
  jointly complete SSE+SZSE mainland calendar, and every year from 1992 through
  2023 is jointly complete without exception. Measured 2026-08-26 by an
  outcome-blind census over the 33 landed `reference/trade_calendar/year=*.parquet`
  partitions of the private spine store (SSE 12,053 rows spanning
  1991-01-01..2023-12-31; SZSE 11,688 rows spanning 1992-01-01..2023-12-31):
  for 1992 both exchanges return 366 of 366 unique civil dates with 366 shared
  dates and ZERO open/closed parity mismatches; the same holds for every year
  1993..2023. Across the whole landed series both exchanges show zero
  `pretrade_date` chain violations and zero missing civil dates inside their own
  observed spans, and SSE/SZSE open-session sets are IDENTICAL for 1992+
  (7,806 open sessions each, set equality True). 1991 fails only because SZSE
  contributes zero rows there — see
  [[CNLI-TUSHARE-SZSE-CALENDAR-STARTS-MID-1991]]. Under a 1992-01-01 epoch the
  session axis therefore holds 7,806 open sessions, position 0 = 1992-01-02 and
  position 7805 = 2023-12-29.
falsifier: >
  Re-run `python3 scripts/research/cn_limit_calendar_epoch_census.py` against a
  spine store. The census is network-free and deterministic given a store, and
  prints every year's counts BEFORE applying its decision rule, so the table is
  auditable independently of the verdict. Any of the following falsifies this
  record: a 1992 SSE or SZSE unique-civil-date count other than 366; a non-zero
  `parity_mismatch` for any year 1992..2023; a non-zero `pretrade_date` chain
  violation count; a missing civil date inside either exchange's span; or a
  final line other than `EARLIEST_JOINTLY_COMPLETE_EPOCH: 1992`. A store
  re-collected from the vendor that yields different counts for the same years
  falsifies it and reopens the epoch question.
so_what: >
  This is the measured evidence Sol's calendar-epoch ruling required before the
  epoch could be frozen. That ruling forbids relaxing the exact calendar
  completeness predicate, forbids a dynamic runtime-selected epoch, and requires
  an outcome-blind source census to prove six specific properties (SSE 366 for
  1992, SZSE 366, exact open/closed parity, valid `pretrade_date` chains,
  continuity across adjacent years, and no exchange-specific divergence
  demanding a different architecture) before its preferred first candidate
  1992-01-01 may be frozen. All six pass, so the census does NOT need to advance
  to a later candidate year and the epoch freezes at 1992-01-01. The zero-parity
  result across 32 years is the specific finding that licenses a SINGLE shared
  mainland session axis rather than per-venue axes: SSE and SZSE never disagree
  about whether a shared civil date is open. Pre-epoch history (SSE 1991's 255
  open sessions) is typed `PRE_EPOCH_SOURCE_UNSUPPORTED` and loses its ordinal
  entirely; it is never imputed as closed, and SSE history is never borrowed as
  exact SZSE history.
scope:
  - macro
  - collectors/china_tushare_spine.py
  - scripts/research/cn_limit_calendar_epoch_census.py
  - research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md
  - WS:CN-LIMIT-ALPHA
kind: constraint
confidence: verified
verified_at: 2026-08-26
verified_by: >
  `python3 scripts/research/cn_limit_calendar_epoch_census.py` over the private
  store reports partition purity OK, 0 duplicate (exchange, cal_date) rows,
  years 1991..2023, 1992 SSE=366/SZSE=366/shared=366/parity_mismatch=0, every
  year 1993..2023 jointly complete, SSE and SZSE `pretrade_chain_violations=0`
  and `missing_civil_dates=0`, and the final line
  `EARLIEST_JOINTLY_COMPLETE_EPOCH: 1992`.
---

# The mainland calendar epoch is 1992-01-01

Minted executing Sol's DEP-EXACT calendar-epoch ruling under
`DEC:CNLI-FABLE-COO-AUTONOMOUS-EXECUTION`. The census answers the question the
ruling posed; it does not choose the architecture, which the ruling froze.

Companion findings from the same investigation:
[[CNLI-SESSION-CLOCK-AXIS-IGNORES-REQUESTED-RANGE]] (why moving the anchor
constant alone does not re-anchor the clock) and
[[CNLI-REPAIRED-SPINE-LEDGER-DIVERGES-FROM-ARTIFACTS]] (why the affected
partitions get a clean rebuild rather than an in-place repair).
