---
key: CNLI-STK-LIMIT-ZERO-PRE-CLOSE-SENTINEL
claim: >
  TuShare's `stk_limit` publishes rows for instruments that did not trade the
  session, and spells their absent previous close as `0` rather than null.
  `normalise_daily_endpoint` coerces that field through
  `_quote_price_cents(item.get("pre_close"), field="stk_limit.pre_close")` with
  `allow_missing` defaulting to False, so a non-positive value raises
  `SpineError: stk_limit.pre_close must be positive`. The exception escapes
  `normalise_daily_endpoint`, the unit is marked `daily_contract_failed` with
  `quarantined_unknown_row_count` set to the WHOLE frame as a bookkeeping device,
  and the exception is re-raised, killing the run. Measured 2026-08-27 on canary
  run 33026983388 for 2018-01-02: the `stk_limit` unit failed with 3,466 source
  rows and 0 landed.
falsifier: >
  Compare the landed `daily` partition against the `stk_limit` source count for
  the same session:
  `python3 -c "import pathlib,pandas as pd;
  S=pathlib.Path.home()/'.local/share/macro-dashboard/china_tushare_spine';
  d=pd.read_parquet(S/'daily/year=2018/month=01/part.parquet');
  d=d[d.trade_date.astype(str)=='2018-01-02'];
  print(len(d), int((d.pre_close_cents<=0).sum()), int(d.pre_close_cents.isna().sum()))"`.
  Falsified if `daily` for that session contains rows with a non-positive or null
  `pre_close_cents` (which would mean zero is a general vendor spelling rather
  than a non-trading marker), or if the `stk_limit` and `daily` row counts match
  (which would mean the extra rows are not the explanation).
so_what: >
  Measured evidence that the zero is a NON-TRADING marker, not corrupt data:
  `daily` for 2018-01-02 landed 3,282 rows with `pre_close_cents` spanning
  115..69,749, ZERO of them non-positive and ZERO null, and every row
  positive-volume. `stk_limit` for the same session returned 3,466 rows — 184
  MORE. Those 184 are instruments with no trade and therefore no previous close,
  and the vendor writes `0` for them.

  This is the SAME defect family as
  `DSC:CNLI-BAK-BASIC-ZERO-LIST-DATE-SENTINEL` — a shared coercer meeting an
  endpoint whose null vocabulary it was never taught — and it is the second
  instance, so the shape should now be treated as a class rather than a one-off:
  before an endpoint's first live run, audit every field the shared coercers
  touch for a vendor zero-as-null spelling.

  It is also the second time one descriptive field has destroyed a whole unit's
  source accounting. The surrounding law says no row may disappear, yet a single
  non-positive `pre_close` discards 3,466 rows and aborts the run.

  Any repair must stay fail-CLOSED and must not be assumed trivial. A row whose
  `pre_close` is absent carries no anchor for its own limit band, so it cannot
  support the existing invariant `up_limit_cents > pre_close_cents >=
  down_limit_cents`. Under `DEC:CNLI-HISTORICAL-PIT-IS-SOURCE-UNION` such a row
  is non-event-eligible anyway, because `event_eligible = positive_volume AND
  source_limits_present` and a non-trading instrument has no positive volume. The
  open question a fix must answer is what to do when the vendor publishes
  `up_limit`/`down_limit` WHILE `pre_close` is zero: that is a genuine
  contradiction (a band with no anchor) and should keep blocking rather than be
  silently accepted.
scope:
  - macro
  - collectors/china_tushare_spine.py
  - WS:CN-LIMIT-ALPHA
kind: constraint
confidence: verified
verified_at: 2026-08-27
verified_by: >
  Canary run 33026983388 (mode=canary, max_requests=12, 2018-01-02, ref
  claude/cn-limit-pit-source-union) failed with `SpineError: stk_limit.pre_close
  must be positive` raised from `collect_daily` ->
  `normalise_daily_endpoint`; the private store records the stk_limit 20180102
  unit as status failed / reason daily_contract_failed with source_row_count
  3466 and landed_a_row_count 0. The landed daily partition for the same session
  holds 3,282 rows with no non-positive and no null pre_close_cents.
---

# A vendor null spelled 0, again — this time in a price field

Found driving Sol's post-ruling acceptance canary under
`DEC:CNLI-HISTORICAL-PIT-IS-SOURCE-UNION`. `stk_limit` had never executed against
the live vendor before this run.

The sibling `DSC:CNLI-BAK-BASIC-ZERO-LIST-DATE-SENTINEL` was a DATE field where a
null narrows eligibility and is therefore safe. This one is a PRICE field that
anchors a legal limit band, so the same reflex — "treat zero as null and land the
row" — is not automatically safe here and needs the contradiction case decided
explicitly.

The preceding handoff had already recorded this shape as a standing danger:
"a per-field parse failure could discard a whole unit's source accounting... the
shape remains wherever a shared coercer meets an endpoint whose null vocabulary
it was never taught." That prediction was confirmed within hours.
