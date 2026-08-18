---
key: HK-DEEP-PANEL-SPLICES-ADJUSTMENT-VINTAGES
claim: >
  data/hk_search/closes_deep.parquet splices two dividend-adjustment vintages at the
  collector's rolling 2-month refresh boundary — HkClosesDeepAdapter re-fetches only
  _INCREMENTAL_PERIOD="2mo" with auto_adjust=True and merge-upserts it, so a ticker that
  goes ex-dividend has its trailing ~2 months re-based onto the new anchor while every
  older row keeps the previous basis, leaving a permanent artificial gap of one dividend
  yield at that boundary; the existing split-seam healer cannot see it because
  seam_suspects only flags 1-day ratios outside [0.60, 1.65].
falsifier: >
  Re-fetch any affected column whole (yf.download(ticker, period="max",
  auto_adjust=True)) and compare its return series to the stored column's: if the stored
  panel carries no excess return at the refresh boundary — i.e. the per-row ratio of
  stored to re-fetched is uniform across the whole column rather than a step — the claim
  is false. Equivalently, run tests/test_hk_board_rank.py::TestG1FixtureIsNotStale
  ::test_source_panel_history_is_unchanged and inspect rescale_diagnosis's detail: a
  claim-consistent world reports a suffix re-base whose breakpoint tracks the collection
  date minus two months.
so_what: >
  Do not read a single-day HK return across a refresh boundary as tape, and do not
  "regenerate the fixture" when a frozen HK close window drifts — the drift is the
  collector's, not the fixture's, and re-stamping re-arms the same fleet red on the next
  ex-date. Any HK study that measures gaps, single-session moves, or drawdowns spanning
  the trailing two months of a stored column is reading a ~dividend-yield artifact at one
  date; the durable heal is collector-side (extend the seam detector below split scale,
  or re-base the whole column when the fresh window's overlap shows a uniform rescale),
  which is tracked separately and deliberately NOT done from a PR, because nightly is the
  sole advancer of data/.
kind: data
verified_at: 2026-08-18
verified_by: >
  collectors/hk_closes_deep.py:39 (_INCREMENTAL_PERIOD = "2mo"), :59-62
  (auto_adjust=True), :75-84 (_heal_store_seams docstring naming the same failure for
  splits); collectors/breadth.py:51 (_SEAM_LO, _SEAM_HI = 0.60, 1.65); measured against
  tests/fixtures/hk_board_2026_07_31.json — 1 of 157 columns drifted (2359.HK), 30 of its
  341 frozen rows from 2026-06-18 (collection date minus 2mo) scaled by a uniform
  0.997101, per-row residual against that single factor <= 4e-4 versus the fixture's own
  1e-3 quantum, all 156 other columns byte-identical
scope:
  - macro
  - data/hk_search/closes_deep.parquet
  - collectors/hk_closes_deep.py
  - collectors/breadth.py
confidence: verified
---

## Why the split-seam healer was not enough

`collectors/hk_closes_deep.py` already carries this defect's shape in prose — its
`_heal_store_seams` docstring says plainly that plain `combine_first` leaves "the stored
PRE-window history on the old price basis — a permanent fake ±N00% day at the refresh
boundary". The healer built for it detects by MAGNITUDE: `seam_suspects` flags a column
only when a one-day ratio leaves `[0.60, 1.65]`.

That is the right band for the event it was written for (the KLAC 10:1 split) and the
wrong band for the event that is ~250x more frequent. A routine cash dividend re-bases by
its yield — 0.29% in the measured case — which sits about 200x inside the detector's band
and passes untouched. So the class the healer names is only half-covered: the loud half
heals, the quiet half accumulates one permanent seam per ticker per ex-date.

The reason it stayed invisible is that nothing downstream compares vintages. Every
consumer reads the stored column as if one basis produced it, and a 29bp gap at one date
does not look wrong in isolation. It surfaced only because a frozen test fixture happened
to straddle the boundary — an accidental detector, not a designed one.

Rests on the same vendor mechanism as
[[DSC-BASKET-OHLCV-REWRITES-HISTORY-NIGHTLY]]; the banding remedy follows
[[DEC-SI-LIVE-PLANE-BAND-IS-UNIFORMITY-NOT-LEVEL]].
