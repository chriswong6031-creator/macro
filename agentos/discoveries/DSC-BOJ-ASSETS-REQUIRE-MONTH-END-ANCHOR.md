---
key: BOJ-ASSETS-REQUIRE-MONTH-END-ANCHOR
claim: >
  FRED JPNASSETS is a monthly end-of-period Bank of Japan total-assets statistic
  whose stored index is labelled on the first day of its month, so using that
  index directly makes the economic value and its FX conversion available roughly
  one month too early; July 2026 must reference 2026-07-31, not 2026-07-01.
falsifier: >
  Run `python3 -c "from lib import store; print(store.read('fred','JPNASSETS').tail())"`
  and inspect https://fred.stlouisfed.org/series/JPNASSETS; disprove the claim by
  showing that the statistic is not end-of-period or by reproducing the
  repository's 2026-07-01 row from an official release available on or before
  2026-07-01 rather than the update published after July month-end.
so_what: >
  Any causal consumer of data/fred/JPNASSETS.parquet must first convert the
  provider label to calendar month-end, sample USDJPY on or before that economic
  date, and then apply its release lag. Do not reuse engine/global_liquidity.py's
  direct-index bank_usd/asof path in a backtest until that module is separately
  repaired under its own display contract.
kind: landmine
verified_at: 2026-08-22
verified_by: >
  `python3 -c "from lib import store; print(store.read('fred','JPNASSETS').tail())"`
  shows the latest value indexed 2026-07-01; FRED series JPNASSETS metadata says
  monthly, end of period, and records the July observation as updated 2026-08-04;
  tests/test_global_liquidity_transmission.py::test_boj_monthly_label_is_anchored_to_month_end_before_release pins the causal correction.
scope:
  - macro
  - data/fred/JPNASSETS.parquet
  - engine/global_liquidity.py
  - engine/global_liquidity_transmission.py
confidence: verified
---

This does not assert that the stored BoJ values are full vintage truth. The new
kernel fixes economic-date and availability alignment while continuing to mark
the source `revision_risk: medium` because the repository has no complete BoJ
vintage archive.
