---
key: CNLI-TUSHARE-SZSE-CALENDAR-STARTS-MID-1991
claim: >
  TuShare's `trade_cal` cannot satisfy the full-A spine contract's fixed
  1991-01-01 calendar anchor for SZSE. Measured 2026-08-26 in canary run
  32933314109: a `trade_cal` request for exchange=SZSE,
  start_date=19910101, end_date=19911231 returned exactly 182 rows, while
  the identical SSE request returned all 365. The collector's exact-range
  binding check (`_validate_response_binding`, "trade_cal response does not
  bind to the exact requested date range") therefore rejects the SZSE 1991
  unit as `rejected_contract`, and because `collect_calendars` computes
  `ready = all(_unit_done(...))` across every exchange-year, the calendar
  stage can never reach ready — which blocks pit_universe, name_history and
  daily collection permanently. 67 of the 68 required exchange-year units
  are terminal; SZSE 1991 is the only one missing. 182 days is arithmetically
  consistent with coverage beginning 1991-07-03 (Jul 3 -> Dec 31 inclusive =
  182), but the returned dates were NOT observed — the response was rejected
  before storage — so the specific start date remains INFERRED, not measured,
  and non-contiguous coverage is not excluded.
falsifier: >
  Land the SZSE 1991 response and read its actual `cal_date` values — the
  exact-range rejection is raised at
  collectors/china_tushare_spine.py:2186, so a bounded diagnostic that
  stores the raw frame before that line runs (or a receipt enriched with
  min/max cal_date) settles it. If the returned dates are contiguous from
  1991-07-03 the inference holds; any other span, or a gapped set,
  falsifies the 1991-07-03 hypothesis while leaving the 182-of-365
  coverage-shortfall claim intact. Re-check the shortfall itself with
  `python3 -c "import json,glob;[print(json.load(open(p))['response_row_count'])
  for p in glob.glob('receipts/requests/trade_cal/*/*.json')
  if json.load(open(p))['response_status']=='rejected_contract']"`
  against the private store: a later SZSE 1991 request returning 365 rows
  falsifies this record.
so_what: >
  This is a coverage-authority and point-in-time-clock question, not an
  implementation defect, and it is NOT resolvable by relaxing the validator.
  research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md states the
  canonical market clock "begins at the fixed 1991-01-01 calendar anchor,
  requires exact SSE/SZSE calendar-day and open-session equality" and
  assigns "one immutable `market_session_position`" from it, and requires of
  `trade_cal` "every requested calendar day". Any repair — moving the
  anchor, making the anchor per-venue, or recording the SZSE pre-coverage
  window as an explicit not-covered state — changes the origin of an
  immutable session ordinal that every downstream horizon, eligibility
  denominator and exact target depends on. Relaxing the exact-range check
  instead would be fail-open: a genuinely truncated response would then
  prove its own truncation legitimate anywhere in the range. The contract
  already contains an analogous but NON-identical rule for a venue absent
  from `trade_cal` ("TuShare does not publish BSE in the documented
  `trade_cal` venue list, so BSE explicitly inherits that consensus from
  launch"); extending that pattern to a venue that IS published but starts
  late is a decision, not a deduction. Escalated to Sol as a hard gate under
  `DEC:CNLI-FABLE-COO-AUTONOMOUS-EXECUTION` return-gate 10 (unresolved
  point-in-time clock / coverage authority no current owner contract
  resolves).
scope:
  - macro
  - collectors/china_tushare_spine.py
  - research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md
  - WS:CN-LIMIT-ALPHA
kind: constraint
confidence: verified
verified_at: 2026-08-26
verified_by: >
  Canary run 32933314109 raised `SpineError: trade_cal response does not
  bind to the exact requested date range` at
  collectors/china_tushare_spine.py:2186; the rejected-call receipt records
  `response_row_count: 182` for params exchange=SZSE/19910101/19911231
  while `reference/trade_calendar/year=1991.parquet` holds 365 SSE rows and
  zero SZSE rows; store state shows trade_cal SSE 34 years vs SZSE 33.
---

# TuShare SZSE calendar cannot meet the 1991-01-01 anchor

Discovered driving the DEP-EXACT bounded canary under
`DEC:CNLI-FABLE-COO-AUTONOMOUS-EXECUTION`. Sibling canary findings:
[[CNLI-TUSHARE-DELISTED-DUMP-CARRIES-NONCANONICAL-LEGACY-CODES]] and
[[CNLI-CALENDAR-PARTITION-YEAR-LEAKED-ACROSS-LOOPS]] — all three were
latent until first real vendor contact, but only this one is an authority
question rather than a defect.
