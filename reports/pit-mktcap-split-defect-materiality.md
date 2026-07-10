# PIT mktcap split defect — materiality assessment (2026-07-10)

**Verdict: MATERIAL — build the PIT share-basis fix.** The defect flips the deep IC
scorecard's headline result (payout loses its lone BH-FDR badge), moves the two
contaminated legs' mean ICs by −21% / −34%, and those two legs currently carry ~69%
of the weight in the LIVE `composite_rank` (audit #25 firewall reads this scorecard).
Registries checked before proposing: no kill in `research/DO_NOT_REBUILD.md`, no open
lane in `docs/ACTIVE_BUILD_MAP.md` (PR #2120 is the adjacent *price-side* cache-seam
fix — complementary, disjoint files).

## The defect

`engine/equity_factors.py::compute_factors(asof=...)` builds `mktcap = price × shares`
where prices come from yfinance `auto_adjust` close caches (back-adjusted **today** for
all later splits) and shares come from `collectors/edgar.py::as_of_cross_section`
(as-filed cover-page counts, unadjusted). The #2101 Polygon reconcile is deliberately
live-only (`asof is None`, `equity_factors.py:511-514`) to avoid look-ahead — correct
call, but it leaves every PIT rebalance with a share basis mismatched to the price
basis by the cumulative **future** split factor.

Spot checks on the rebuilt deep panel (true caps from contemporaneous records):

| name @ date | computed PIT cap | true cap | error |
|---|---|---|---|
| NVDA @ 2016-06-30 | $0.62B | ~$25B | **40×** (value z = +1.55: a nano-cap "deep value" stock) |
| AAPL @ 2013-06-30 | $11.4B | ~$380B | 33× |
| AMZN @ 2018-06-30 | $41B | ~$825B | 20× |
| MSFT @ 2015-06-30 (no splits) | $312B | ~$356B | 1.1× (dividend-adjust residual — control) |

## Contamination channels

1. **value** (ni/mc, equity/mc, revenue/mc, cfo/mc) and **payout** (net yield /mc) — direct.
2. **Style basis**: `factor_ic_scorecard._style_basis` uses `log(mktcap_bn)` as the size
   loading → **every** factor's incremental (style-neutralized) IC is residualized
   against a corrupted size axis.
3. **Live board**: `_rank_leg_weights` weights = positive `mean_ic` with a 1.5× FDR
   bonus. Current scorecard → payout 0.037, value 0.018, profitability 0.014, quality
   0.004: **~69% of the live `composite_rank` ordering weight sits on the two
   contaminated legs**, with payout's weight resting on an FDR badge the correction
   removes (below).

Directionality is not noise: names that later split are disproportionately past
winners with strong continued forward returns in this sample (NVDA/AAPL/AMZN/AVGO/
CMG…), and the error marks them as hyper-cheap — i.e. the defect **inflates** the
value/payout ICs.

## Census (split events confirmed against actual split histories)

Detector: consecutive-FY cover-page share-count ratios in `fundamentals_panel.parquet`,
snapped to canonical split factors, each event confirmed against the name's actual
(yfinance) split history; 578 flagged tickers checked, 0 fetch failures, snap-vs-actual
agreement 94.6%. 433 candidate events **rejected** (pre-IPO share restatements, merger
issuance — e.g. WBD 2022 —, REIT scale-ups, panel unit artifacts): confirming a raw
jump-detector would mis-correct real issuance ~2/3 of the time.

- **223 confirmed split events on 195 tickers**, plus 5 post-last-filing tails
  (CRWD 4:1 2026-07-02, KLAC 10:1 2026-06-12, **DD 1:3 reverse 2026-06-24**,
  MLI 2:1 2026-07-01, SF 3:2 2026-02-27) — the stale-cover-page tail is live and
  ongoing, not just the #2101 trio.
- On the 61-date quarterly deep grid (2011-03..2026-03): **4,555 contaminated
  name×date cells ≥1.8× (mean 75/date, 6.6% of the cross-section), 2,187 cells ≥4×,
  616 cells ≥10×.** Contamination is worst early (2011-2013: ~12-15% of names) and
  decays toward the present.

## Materiality experiment — does the IC ranking move?

Twin scorecard runs on the identical 61-rebalance deep grid, horizon 63d, median
universe 1,321 (deep close panel rebuilt via the `sue_deep_phase0` recipe — the
original runner-local artifact no longer exists on the box; recent dates byte-match
the live breadth cache). Baseline = shipped code; corrected = `as_of_cross_section`
wrapped to forward-adjust shares by the cumulative confirmed future split factor.
Non-mc legs are untouched controls.

| factor | baseline meanIC (t_HAC) | corrected meanIC (t_HAC) | Δ | BH-FDR 10% |
|---|---|---|---|---|
| **payout** | +0.0302 (3.20), q=0.015 | +0.0238 (2.26), q=0.26 | **−21%** | **survives → FAILS** |
| **value** | +0.0124 (1.50) | +0.0082 (0.92) | **−34%** | fails → fails |
| profitability | +0.0166 (0.95) | +0.0166 (0.95) | 0 (control ✓) | — |
| quality / accruals / investment / low_vol / low_beta / sue | unchanged (controls ✓) | | | |

- **After correction, NO factor survives BH-FDR(10%) raw on deep history.** The
  scorecard's sole survivor badge was resting in part on the split artifact.
- Cross-check against the *committed* scorecard numbers (payout t=2.72): applying the
  measured t-delta (−0.94) gives t≈1.9, p≈0.06, BH q≈0.5 across the 11-factor panel —
  the badge flips there too, so the finding is not an artifact of universe drift
  between my rebuild (1,498 names) and the June build (~1,154 median).
- Rank-leg weights move from `{payout .0453, profitability .0166, value .0124,
  quality .0037}` to `{payout .0238, profitability .0166, value .0082, quality .0037}`
  — payout drops from ~58% to ~45% of the live ordering weight (loses the 1.5× FDR
  bonus), and profitability overtakes value as the #2 leg.

Per the measurement-lens protocol: this is **estimator-broken**, not mechanism-false —
payout/value stay positive after correction (payout t=2.26 is respectable, just not
FDR-clearing on an 11-factor panel). The correction *changes the ruler*, it does not
kill the factors.

## Recommended build (separate lane)

1. **Dated split-event store** (nightly accrual, off render path): yfinance `actions`
   (free, keyless) or Polygon splits for the S&P1500 universe →
   `data/reference/split_events.parquet`.
2. **Per-(ticker, fy) unit-basis factor table**: reconcile panel share-count boundaries
   against the dated events (the detector+confirmation logic above — needed because
   panel cover counts can lead the actual split date by ~1y via CY-frame quirks, e.g.
   NVDA fy2020 is already post-4:1 two months before the split). Do NOT apply raw
   dated factors to filing dates; reconcile against the panel's own boundaries.
3. **PIT path**: `compute_factors(asof=...)` multiplies as-filed shares by the
   cumulative confirmed factor from the row's basis to today. No look-ahead: split
   history is a matter of record, not a forecast (same class as the NYSE calendar).
4. **Regen + re-adjudicate**: deep scorecard rerun, `_rank_leg_weights` re-derived;
   payout's FDR badge and the 1.5× bonus must be re-adjudicated on the corrected
   ruler (authority-tier input — gauntlet applies).

## Caveats and residuals (shared by both runs; do not affect the delta)

- Deep panel remains survivorship-biased (yahoo serves listed names only) — same
  caveat as the committed scorecard.
- `auto_adjust` also folds **dividend** back-adjustment into prices: caps of high-yield
  names are understated ~1.1-1.4× at decade horizons (MSFT control above). A
  splits-only price basis (or split-only share adjustment vs unadjusted closes) would
  remove it; worth folding into the same build.
- **Panel share-unit artifacts** (separate defect, both runs affected): e.g. ED's
  fy2010-2015 cover counts are ~13× low vs reality; pre-IPO rows carry preferred-stock
  counts. These corrupt PIT mktcap for the affected rows regardless of splits —
  flagged as follow-up work, not blocking this fix.
- 3:2 splits are included where confirmed; unconfirmed soft-band (1.4-1.8×) jumps are
  left uncorrected (conservative).

## Reproduction

Deep panel: `python -m scripts.sue_deep_phase0` recipe (batched yfinance, period=max,
auto_adjust, >252 rows). Experiment scripts + per-date IC series + split audit JSONs
archived at `/tmp/mktcap_pit/` on the Mac Studio (session artifacts; the build lane
should productionize the detector+confirmation into `collectors/`). Scorecard math
replicated verbatim from `scripts/factor_ic_scorecard.py` (rank_ic → ic_summary →
BH-FDR), no writes to `data/` or `reports/` from the harness.
