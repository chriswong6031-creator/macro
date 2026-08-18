---
key: BASKET-OHLCV-REWRITES-HISTORY-NIGHTLY
claim: >
  data/baskets/ohlcv/<TICKER>.parquet is NOT an append-only tape: every collection
  night scripts/fetch_basket_ohlcv.py re-downloads the FULL history from START via
  yf.download(auto_adjust=True) and merges new.combine_first(prior) — where `new`
  covers the whole span, so it wins everywhere — and the vendor's recomputed
  cumulative dividend-adjustment factor rewrites the historical rows. Measured on B
  across the two 2026-08-17 collection commits (59ccb9c774c8 21:01, 93ab221b81dd
  21:21): 8852-9492 of 12688 prefix values moved per night, max 8.63e-07 relative,
  with all four of open/high/low/close in a row scaling by ONE shared factor to
  float64 epsilon (within-row ratio spread 4.44e-16) and the newest bars unmoved —
  the signature of a recomputed cumulative adjustment factor carried at ~7
  significant digits, not noise and not a corporate action. Only the ASOF bar's
  volume settles (+4.33e-04, consolidated tape). Adjusted `close` is exactly
  float32-representable; adjusted open/high/low are NOT (they are close-derived).
falsifier: >
  `git log --format=%H -- data/baskets/ohlcv/B.parquet`, then for two consecutive
  collection commits compare the <=ASOF prefixes: if historical rows are byte-stable
  and only post-ASOF rows appear, this is refuted. Equivalently, grep
  scripts/fetch_basket_ohlcv.py:369,450 for `yf.download(..., auto_adjust=True)` and
  `new.combine_first(prior)`.
so_what: >
  (1) NEVER pin an exact-equality digest on any artifact under data/baskets/ohlcv/ —
  it is a guaranteed fleet red on the next collection night, and a re-stamp buys one
  day (this digest moved twice in 21 minutes; the original pin only survived 3 days
  because of a weekend). Pin a frozen program-owned snapshot instead and compare the
  live plane with a tolerance band. (2) The drift is economically null — one factor
  per row means returns and intraday ratios are preserved to float64 epsilon — so a
  relative-tolerance comparison is the correct semantic, not a quantized re-hash.
  (3) Fixed-decimal quantize-then-hash does NOT work: measured, rounding to 2 dp
  still flips 1 of 12688 values on BOTH consecutive night pairs (3 dp flips 16-24,
  4 dp flips 236-243), converting a certain nightly red into a flaky one. (4) The
  break surfaces as an unattributable fresh-main red blamed on the first PR to hit it.
kind: landmine
verified_at: 2026-08-18
verified_by: >
  scripts/fetch_basket_ohlcv.py:369,450; prefix digests recomputed with
  scripts/stock_identity_build_w1a1.py:_ohlcv_prefix_sha256 over `git show` of
  6d04e9b3100af7afaf834ceb2c9c307a48808f0b (6d8988fc…),
  59ccb9c774c83bdeeaf34d4d32a437b880d9c401 (2f4d9467…) and
  93ab221b81ddd214e67f9c7565524a0d91496ab3 (a77fdc41…); PR #5860
scope:
  - macro
  - data/baskets/ohlcv/
  - scripts/fetch_basket_ohlcv.py
confidence: verified
---

Plane-wide, not a B quirk: the same shape was reported on AAPL (2338 rows changed,
1803 distinct ratios) and A (2327 changed, 1697 distinct).

The economic separation that makes a tolerance band safe: observed churn tops out at
8.63e-07 relative, while the smallest economically real price revision — one cent at
this plane's minimum price of 4.81 — is 2.08e-03. That is a ~2400x gap, so a 1e-5
band sits 11.6x above the noise and 208x below the smallest real revision.

Consumed by [[DEC-SI-REGISTERED-B-PREFIX-IS-A-FROZEN-SNAPSHOT]].
