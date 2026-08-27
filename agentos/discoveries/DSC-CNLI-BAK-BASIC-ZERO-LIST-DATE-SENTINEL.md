---
key: CNLI-BAK-BASIC-ZERO-LIST-DATE-SENTINEL
claim: >
  TuShare's `bak_basic` returns the string "0" for an unpublished `list_date`,
  where `stock_basic` returns an empty string. `_iso` already recognised None,
  NaN, "", "none", "nan" and "nat" as null spellings but not the zero sentinel,
  so "0" fell through to `_parse_date` and raised
  `SpineError: invalid date '0'; expected YYYYMMDD or YYYY-MM-DD` out of
  `normalise_bak_basic`. One descriptive field on one row killed the entire
  `bak_basic` unit and therefore the whole canary run. Measured 2026-08-26: the
  offending row is `603361.SS` 浙江国祥, an approved-but-never-listed name whose
  float_share, total_share, holder_num, bvps and eps are all 0 as well.
falsifier: >
  `python3 -m pytest tests/test_china_tushare_spine.py -q -k "zero_sentinel or zero_list"`.
  Falsified if `spine._iso("0")` raises rather than returning None, if a
  zero-heavy but genuine date such as "20001010" returns None instead of
  "2000-10-10", or if a malformed date ("202401", "0000-00-00", "20241301")
  stops raising — the last would mean the sentinel branch had widened into a
  swallow-everything catch.
so_what: >
  The fix is fail-CLOSED and must stay that way. A null date is an EXPECTED
  state the callers already model: the `stock_basic` normaliser sets
  `effective_from = None` for exactly this case, commenting that such a row
  "remains in the master but cannot enter a historical eligible universe". So
  nulling the sentinel NARROWS eligibility, while inventing a date would have
  widened it. The test is an ALL-ZERO run rather than a substring or a
  try/except, because every real date carries a non-zero digit in its year — that
  is what makes the branch incapable of swallowing a real date, and it is why a
  merely malformed date still raises. Two wider lessons: a shared date coercer
  needs the null vocabulary of EVERY endpoint that feeds it, not just the first
  one that was wired; and a per-field parse failure should never be able to
  discard a whole unit's source accounting — the surrounding law says no row may
  disappear, and this defect could destroy 5,344 of them over one field.
scope:
  - macro
  - collectors/china_tushare_spine.py
  - WS:CN-LIMIT-ALPHA
kind: constraint
confidence: verified
verified_at: 2026-08-26
verified_by: >
  Canary runs 32949563978, 32949667737, 32949769416 and 32949874632 all failed
  with `SpineError: invalid date '0'` traced through collect_pit_universe ->
  normalise_bak_basic -> _iso -> _parse_date while all 66 trade_cal units were
  already terminal; after the fix, run 32950379014 on the same window advanced
  past the crash to stage `pit_universe_incomplete`, and the retained quarantine
  payload for 603361.SS shows `"list_date":"0"` verbatim.
---

# A vendor null spelled "0"

Fourth defect surfaced by first real vendor contact, and the first inside
`pit_universe` — a stage that had never executed against TuShare until Sol's
post-epoch rebuild reached it. Same family as
[[CNLI-TUSHARE-DELISTED-DUMP-CARRIES-NONCANONICAL-LEGACY-CODES]] and
[[CNLI-CALENDAR-PARTITION-YEAR-LEAKED-ACROSS-LOOPS]]: green tests, broken
reality, invisible until real data arrived.

Fixing it did not unblock the stage — it revealed the real gate underneath,
[[CNLI-BAK-BASIC-PIT-ROWS-ABSENT-FROM-STOCK-BASIC-WITNESS]].
