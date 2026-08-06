# Pick-class conditional forward distributions — Phase-0 (diagnostic)

**Family** `pick_forward_dist_phase0` · **Program** `advanced-quant-methods-w1` · **Tier** diagnostic — phase-0 measurement; promotes nothing
**Generated** 2026-08-06T03:07:58.082285+00:00 · **Runtime** 321s

Phase-0 measures. It promotes nothing and authorizes nothing: the verdicts below are diagnostic labels for a later adjudication, not a ship decision.

## 0. Headline

| Scheme | Cells | Verdict | G1 coverage | G2 vs B0 | G3 vs B1 | G4 honest |
|---|---|---|---|---|---|---|
| `S1_trend` | 4 | **CALIBRATED_ONLY** | 0.789 PASS | -0.00052 [-0.00187, +0.00102] FAIL | +0.00079 [-0.00121, +0.00291] FAIL | 1.000 PASS |
| `S2_extension` | 4 | **CALIBRATED_ONLY** | 0.788 PASS | -0.00028 [-0.00117, +0.00055] FAIL | +0.00102 [-0.00069, +0.00271] FAIL | 1.000 PASS |
| `S3_vol` | 4 | **GO** | 0.790 PASS | +0.00280 [+0.00126, +0.00444] PASS | +0.00411 [+0.00238, +0.00599] PASS | 1.000 PASS |
| `S4_coil` | 4 | **CALIBRATED_ONLY** | 0.790 PASS | +0.00091 [-0.00005, +0.00191] FAIL | +0.00222 [+0.00079, +0.00374] PASS | 1.000 PASS |
| `S5_trend_vol` | 6 | **GO** | 0.784 PASS | +0.00219 [+0.00043, +0.00417] PASS | +0.00350 [+0.00139, +0.00582] PASS | 1.000 PASS |

Deltas are per-date **baseline minus scheme** mean pinball on the identical cross-section, so a positive number is skill. CI = circular block bootstrap, block = 21 (the outcome overlap), B = 5000, seed = 7.

**Evaluated** 856 sessions (2023-01-03 to 2026-06-02), 3,307,737 name-days, 6,617 distinct names at H=21.

## 1. Baselines (the nulls)

| Arm | Mean pinball H21 | Coverage H21 | H10 cov | H63 cov |
|---|---|---|---|---|
| `B0_pooled` | 0.25611 | 0.794 | 0.796 | 0.769 |
| `B1_ownname` | 0.25742 | 0.786 | 0.793 | 0.740 |

**Read G2 and G3 as an unequal pair.** B1 estimates its quantiles from at most 504 own-name observations; B0 estimates them from the whole pooled cohort, which is millions. The smaller sample is the noisier estimator, so the two gates are not equally hard — here **B0 is the harder baseline** (0.25611 vs 0.25742 mean pinball). A scheme that clears the easier gate and fails the harder one has NOT shown skill; the binding evidence is the harder one. This asymmetry is a property of the pre-registered design, reported rather than repaired.

## 2. Per-scheme detail

### `S1_trend` — CALIBRATED_ONLY

- Cells declared 4, seen at H21 4; above-floor share 1.000
- Mean pinball H21 0.25663 · MAE-p05 tail hit 0.0562 (nominal 0.05)
- Era split vs B0: 2023-24 -0.00060 (502d) · 2025-26 -0.00040 (354d) · sign stable: True
- Breach clustering (report-only, mostly mechanical — see caveats): lag-1 autocorr 0.8749 vs B0's 0.8777, longest run above nominal 32 dates, 0.4661 of dates above nominal
- Raw-percent frame H21 (secondary; double-counts scale — see caveats): coverage 0.796, delta vs B0 +0.00604 [-0.00481, +0.01863]

| H | Coverage | Mean pinball | Δ vs B0 [95% CI] | Δ vs B1 [95% CI] |
|---|---|---|---|---|
| 10 | 0.792 | 0.25385 | -0.00055 [-0.00132, +0.00019] | -0.00051 [-0.00154, +0.00053] |
| 21 (primary) | 0.789 | 0.25663 | -0.00052 [-0.00187, +0.00102] | +0.00079 [-0.00121, +0.00291] |
| 63 | 0.765 | 0.25822 | -0.00078 [-0.00264, +0.00113] | +0.00604 [+0.00275, +0.00971] |

Verdicts are issued at H=21 only; H=10 and H=63 are descriptive rows.

### `S2_extension` — CALIBRATED_ONLY

- Cells declared 4, seen at H21 4; above-floor share 1.000
- Mean pinball H21 0.25639 · MAE-p05 tail hit 0.0562 (nominal 0.05)
- Era split vs B0: 2023-24 -0.00077 (502d) · 2025-26 +0.00040 (354d) · sign stable: False
- Breach clustering (report-only, mostly mechanical — see caveats): lag-1 autocorr 0.8766 vs B0's 0.8777, longest run above nominal 32 dates, 0.4579 of dates above nominal
- Raw-percent frame H21 (secondary; double-counts scale — see caveats): coverage 0.782, delta vs B0 +0.08495 [+0.07523, +0.09536]

| H | Coverage | Mean pinball | Δ vs B0 [95% CI] | Δ vs B1 [95% CI] |
|---|---|---|---|---|
| 10 | 0.792 | 0.25330 | +0.00000 [-0.00035, +0.00033] | +0.00004 [-0.00067, +0.00078] |
| 21 (primary) | 0.788 | 0.25639 | -0.00028 [-0.00117, +0.00055] | +0.00102 [-0.00069, +0.00271] |
| 63 | 0.761 | 0.25874 | -0.00129 [-0.00310, +0.00035] | +0.00553 [+0.00102, +0.01001] |

Verdicts are issued at H=21 only; H=10 and H=63 are descriptive rows.

### `S3_vol` — GO

- Cells declared 4, seen at H21 4; above-floor share 1.000
- Mean pinball H21 0.25330 · MAE-p05 tail hit 0.0615 (nominal 0.05)
- Era split vs B0: 2023-24 +0.00354 (502d) · 2025-26 +0.00176 (354d) · sign stable: True
- Breach clustering (report-only, mostly mechanical — see caveats): lag-1 autocorr 0.8798 vs B0's 0.8777, longest run above nominal 33 dates, 0.4206 of dates above nominal
- Raw-percent frame H21 (secondary; double-counts scale — see caveats): coverage 0.804, delta vs B0 -0.00123 [-0.00820, +0.00644]

| H | Coverage | Mean pinball | Δ vs B0 [95% CI] | Δ vs B1 [95% CI] |
|---|---|---|---|---|
| 10 | 0.791 | 0.25115 | +0.00216 [+0.00084, +0.00345] | +0.00219 [+0.00078, +0.00362] |
| 21 (primary) | 0.790 | 0.25330 | +0.00280 [+0.00126, +0.00444] | +0.00411 [+0.00238, +0.00599] |
| 63 | 0.762 | 0.25456 | +0.00289 [+0.00143, +0.00469] | +0.00971 [+0.00644, +0.01308] |

Verdicts are issued at H=21 only; H=10 and H=63 are descriptive rows.

### `S4_coil` — CALIBRATED_ONLY

- Cells declared 4, seen at H21 4; above-floor share 1.000
- Mean pinball H21 0.25520 · MAE-p05 tail hit 0.0591 (nominal 0.05)
- Era split vs B0: 2023-24 +0.00144 (502d) · 2025-26 +0.00016 (354d) · sign stable: True
- Breach clustering (report-only, mostly mechanical — see caveats): lag-1 autocorr 0.8728 vs B0's 0.8777, longest run above nominal 26 dates, 0.4369 of dates above nominal
- Raw-percent frame H21 (secondary; double-counts scale — see caveats): coverage 0.802, delta vs B0 -0.00072 [-0.00552, +0.00429]

| H | Coverage | Mean pinball | Δ vs B0 [95% CI] | Δ vs B1 [95% CI] |
|---|---|---|---|---|
| 10 | 0.791 | 0.25254 | +0.00076 [-0.00005, +0.00160] | +0.00080 [-0.00022, +0.00186] |
| 21 (primary) | 0.790 | 0.25520 | +0.00091 [-0.00005, +0.00191] | +0.00222 [+0.00079, +0.00374] |
| 63 | 0.764 | 0.25652 | +0.00092 [-0.00027, +0.00221] | +0.00775 [+0.00463, +0.01100] |

Verdicts are issued at H=21 only; H=10 and H=63 are descriptive rows.

### `S5_trend_vol` — GO

- Cells declared 6, seen at H21 6; above-floor share 1.000
- Mean pinball H21 0.25391 · MAE-p05 tail hit 0.0623 (nominal 0.05)
- Era split vs B0: 2023-24 +0.00260 (502d) · 2025-26 +0.00162 (354d) · sign stable: True
- Breach clustering (report-only, mostly mechanical — see caveats): lag-1 autocorr 0.8771 vs B0's 0.8777, longest run above nominal 45 dates, 0.4591 of dates above nominal
- Raw-percent frame H21 (secondary; double-counts scale — see caveats): coverage 0.800, delta vs B0 +0.00450 [-0.00634, +0.01707]

| H | Coverage | Mean pinball | Δ vs B0 [95% CI] | Δ vs B1 [95% CI] |
|---|---|---|---|---|
| 10 | 0.787 | 0.25143 | +0.00188 [+0.00060, +0.00316] | +0.00191 [+0.00049, +0.00337] |
| 21 (primary) | 0.784 | 0.25391 | +0.00219 [+0.00043, +0.00417] | +0.00350 [+0.00139, +0.00582] |
| 63 | 0.759 | 0.25540 | +0.00205 [+0.00002, +0.00436] | +0.00887 [+0.00522, +0.01257] |

Verdicts are issued at H=21 only; H=10 and H=63 are descriptive rows.

## 3. Honest caveats

- SURVIVORSHIP: data/massive_stock_day is the Polygon whole-market store and DOES carry delisted instruments (20,476 parquet files vs ~4-6k currently-listed liquid names), so survivorship bias is bounded — but it is not zero: the store begins 2021-07-06, so anything delisted before that date is invisible, and the store is not a point-in-time listing snapshot.
- SINGLE ERA: the whole panel is 2021-07-06 to 2026-07-02 — one macro regime block (post-COVID melt-up, the 2022 rate shock, the 2023-2026 AI-led advance). There is no independent second era, so the 2023-24 vs 2025-26 split reported here is a within-sample stability read, not an out-of-era replication.
- DIVIDENDS: prices are price-return, not total-return. Forward returns are understated for high-yield names by roughly the dividend paid in the window.
- SPINOFFS: ~8-10 large spinoffs (GE, DD, T, EXC, MMM, DHR, WDC, BKNG) are NOT splits; split_adjust does not repair them and they remain in the panel as one-bar discontinuities.
- INSTRUMENT MIX: the store is instrument-level and this repo holds no whole-market classifier, so ETFs, ADRs and preferred/class shares that clear the liquidity filter are in the universe (103 surviving symbols carry a lowercase character, the Polygon preferred/class-share convention). Read-across to the common-stock Prophet board is therefore approximate.
- G4 WEAKNESS (AM-4): with a cross-section this wide the 400-observation cell floor rarely binds, so G4 as configured is a weak gate. It was kept as pre-registered rather than retuned after the fact.
- OVERLAP: forward windows overlap across adjacent evaluation dates; the block bootstrap (block = horizon) is the correction, not an i.i.d. assumption.
- BACK-ADJUSTMENT IS RATIO-NEUTRAL, NOT LEVEL-NEUTRAL: splits are repaired once over each full series (the standard convention), so every feature and forward return used here is unchanged, but the $5 price floor is applied to the back-adjusted price rather than the price as printed, and the split-print stamp is identified using the whole series. Both only remove observations from the universe and neither touches an outcome — a small hindsight whisker in the universe definition, stated rather than hidden.
- B0's above-floor share is 0 by construction: the pooled unconditional baseline IS the marginal, so that field is meaningful only for a conditioning scheme.
- BREACH CLUSTERING IS MOSTLY MECHANICAL: adjacent evaluation dates share 20 of their 21 forward days, so the per-date breach rate is autocorrelated by construction at daily cadence. A high lag-1 autocorrelation here is therefore NOT by itself evidence of a modelling failure. The statistic is report-only for exactly this reason; comparing it ACROSS arms on the same dates is the only reading it supports.
- THE STANDARDIZER IS PART OF THE HYPOTHESIS, NOT NEUTRAL GROUND: outcomes are scaled by TRAILING realized 20d vol, which is a naive forecast of forward vol — realized vol mean-reverts, so a name whose 20d vol just spiked will realize LESS than one trailing sigma, and one in a vol trough will realize more. Any cell that sorts on vol state (S3_vol, and the vol axis of S5_trend_vol) can therefore earn a pinball gain purely by correcting that known bias in the scale. That is a real and useful correction, but it is a different claim from 'state carries forward-return information'. The decisive follow-up, OUT OF SCOPE for this phase-0: re-run with a HAR forward-vol forecast as the standardizer (engine/vol_forecast.py already ships one, exercised by tests/test_anticipation.py). If a vol-state scheme still beats B0 under that scale, the conditioning carries information; if the edge collapses, the finding is 'use a better vol forecast', not 'condition on vol state'. No verdict below distinguishes these two cases.
- THE RAW-PERCENT FRAME DOUBLE-COUNTS SCALE: in raw percent, a cell that sorts on extension or vol also sorts on return DISPERSION, so a scheme can score a large raw-frame gain purely by predicting width that the vol-standardizer already supplies in the primary frame. Where the raw delta is large and the standardized delta is not, the honest reading is that the scheme is re-deriving the vol scale, not adding information to it. The primary frame is the one the gates read.
- DATA END (AM-1): the readable store ends 2026-07-02, not 2026-07-28 as the worktree's committed manifest claims. A separate lane owns that publish outage.

## 3b. Post-run review addenda (2026-08-06 adversarial review — disclosures only, nothing retuned)

- REVIEW-1 (G1 IS NON-DISCRIMINATING AT THIS DESIGN): the unconditional null itself sits mid-band — B0 covers ~0.794 and B1 ~0.786 against the [0.72, 0.88] gate — so an empirical marginal fitted on a large cohort passes G1 by construction. G1+G4 being structurally weak means 'passes all four gates' really rests on G2/G3, the two gates capable of failing. The pooled coverage number also carries no overlap-corrected test statistic (the HEDGEYE C.4 spec's Kupiec/Christoffersen point about overlapping origins applies); a coverage TEST at non-overlapping origins belongs in the phase-1 harness.
- REVIEW-2 (COHORT RAMP / B1 NON-INDEPENDENCE): the store starts 2021-07-06, so the 504-session window is first full at 2024-10-16 — 52% of evaluation dates ran on a partial cohort — and B1's 252-observation floor is unsatisfiable before 2023-10-16, so early B1 cones degrade to B0 (honest_frac 0.60 overall: ~40% of name-days scored the 'own-name' baseline AS the pooled baseline). G3 is therefore a ~60/40 blend of the own-name test and G2, not a fully independent second gate.
- REVIEW-3 (S5 IS FRAGILE, S3 IS NOT): under a 10-test Bonferroni floor (5 schemes x 2 baselines, 0.005), S5-vs-B0's one-sided p=0.0074 fails while S3 survives at p<0.0002 on both baselines; clustering deltas at the 14 quarterly refits gives S3 t=3.23 (12/14 quarters positive) but S5 t=2.04, under the df=13 critical value. Read S3 as the finding and S5 as suggestive. The CI is stable across block lengths 21-126, so the block choice itself is sound.
- REVIEW-5 (NEGATIVE CONTROL, MEASURED): a state-independent noise partition over an above-floor fixture cohort scores mean delta -0.00054 across 40 seeds (never exactly zero — random cells are noisy subsamples of the marginal, so they price slightly WORSE than it). The harness manufactures no positive edge from partitioning alone, and the two CALIBRATED_ONLY schemes (S1 -0.00052, S2 -0.00028) sit at noise-partition level, which sharpens the S3/S5 contrast. Pinned by test_noise_partition_manufactures_no_edge.
- REVIEW-ORDERING (CONSISTENT WITH THE STANDARDIZER CAVEAT): ranked by delta vs B0 at H=21, every positive scheme is a trailing-vol transform (S3 rvol_z +0.00280, S5 trend x vol +0.00219, S4 range-coil +0.00091) and both non-vol schemes are negative (S2 -0.00028, S1 -0.00052) — exactly the ordering the standardizer-artifact mechanism predicts. This raises the prior on the 'vol-forecast correction' reading; the HAR discriminator decides it.
- REVIEW-7 (sharpe_ci): earlier artifacts annualized the delta-series Sharpe at 365; regenerated at 252. The quantity is a sign-check only.
- REVIEW-9 (SPLIT-STAMP MECHANISM): the ineligibility stamp marks bar i-1 via one-bar-ahead factor information (touched = step | roll(step, -1)). Feature-side removal only (7,554 of 3.69M rows); outcomes are computed on the already-repaired series and never read the stamp.

## 4. Data + universe as actually read

- Store `/Users/chriswong/Documents/Cluade/Macro Dashboard/data/massive_stock_day` — 20,476 parquet files, 20,476 read, 12,078 past the cheap prefilter
- Calendar 2021-07-06 to 2026-07-02 (1254 sessions)
- Panel 3,692,601 eligible observations across 6,852 names
- Splits repaired on 2,015 names; 7,554 split-print bars stamped ineligible
- unadjusted; splits repaired via replay_standout_pipeline.split_adjust; dividends NOT adjusted (price return)

## 5. Frozen pre-registration (verbatim)

```text
Phase-0: pick_forward_dist — state-conditioned forward distributions for the equity
cross-section.

FROZEN PRE-REGISTRATION (written BEFORE any result was computed; any gap is an
amendment recorded in AMENDMENTS below and repeated in the results file)
================================================================================
Family:  pick_forward_dist_phase0
Program: advanced-quant-methods-w1 (wave 1)
Tier:    DIAGNOSTIC. This harness measures; it does not promote. No ship language,
         no authority claim, no gate on any user-facing surface follows from it.

QUESTION
--------
engine/forward_dist.py conditions ONE asset's history on ONE state series and reads
the empirical forward cone; engine/anticipation.py drives it live for 48 configured
cross-asset names. The ~2,900-name Prophet equity board has NO distributional read at
all. Before building one, measure the premise:

  On the real US wide panel, does a POOLED CROSS-SECTIONAL empirical forward
  distribution, conditioned on a name's causal state cell, beat the unconditional
  nulls out-of-sample — and is it calibrated?

"Beat" is scored by mean pinball loss across a fixed quantile grid (a CRPS proxy).
"Calibrated" is scored by realized coverage of the nominal 80% band. Both are
required: a sharper-but-wrong cone is worse than an honest wide one.

The construction is deliberately EMPIRICAL (an analog cohort of comparable name-days),
NOT a fitted quantile regression. Zero fitted weights, so there is nothing to overfit
and empirical quantiles cannot cross. Whether a FITTED quantile model adds anything on
top is a separate, later question and is explicitly out of scope here.

DATA
----
data/massive_stock_day/ — Polygon whole-market daily store, one parquet per instrument,
columns open/high/low/close/volume/transactions. Resolved by ladder:
  --data-root arg  ->  $MACRO_PRIMARY_DATA  ->  <repo>/data/massive_stock_day
  ->  /Users/chriswong/Documents/Cluade/Macro Dashboard/data/massive_stock_day
Read-only; this harness NEVER writes to the store.

PRICES ARE UNADJUSTED. Splits are repaired with the canonical, yahoo-verified
scripts.replay_standout_pipeline.split_adjust (the only sanctioned splitter here). It
adjusts CLOSE only, so the recovered factor is carried onto open/high/low (divide) and
volume (multiply) by engine.pick_forward_dist.carry_split_factor, and the two bars
straddling each applied factor change are stamped ineligible — a split print is not a
clean observation. Known residual: ~8-10 large SPINOFFS (GE, DD, T, EXC, MMM, DHR, WDC,
BKNG) are NOT splits, are not repaired by this splitter, and remain in the panel as
one-bar discontinuities. Dividends are not adjusted either (price return, not total
return). Both are disclosed in the results, not silently carried.

Back-adjustment is applied once over each full series, which is the standard convention
and is RATIO-NEUTRAL: every bar in a trailing window that contains no split is scaled by
the same constant, so every feature and every forward return here — all of them ratios —
is unchanged. It is not level-neutral. Two level-scale quantities therefore carry a
whisker of hindsight: the $5 price floor is applied to the back-adjusted price rather
than the price as printed, and the split-print stamp removes bars identified using the
whole series. Dollar volume is unaffected (the price divides and the share count
multiplies by the same factor). Neither touches an outcome, and both only ever REMOVE
observations from the universe; they are stated here rather than left to be discovered.

UNIVERSE (daily, causal — applies to TRAINING observations as well as evaluated ones)
  close > $5
  20-day MEDIAN dollar volume >= $2,000,000
  >= 300 bars of the name's own history (bar_index >= 300)
  every state feature and the vol scale finite on the bar
No instrument-type filter: the store is instrument-level and this repo holds no
whole-market classifier, so ETFs, ADRs, preferreds and warrants that clear the
liquidity filter are IN the universe. That is a named limitation on read-across to the
common-stock Prophet board, disclosed in the results — not an unregistered filter
invented after seeing a number.

STATE FEATURES (causal; full lag convention in engine/pick_forward_dist.py docstring)
  above_200dma : close > 200d SMA                                          (trend side)
  slope50_up   : 50d SMA > its own value 10 bars ago                      (trend slope)
  ext_pct      : 100 * (close / trailing-252d high - 1)   <= 0             (extension)
  rvol_z       : 20d realized daily vol, z-scored against its own trailing
                 252d mean/std LAGGED ONE BAR                             (vol state)
  coil         : 20d (high-low)/close range over its own trailing 252d
                 median LAGGED ONE BAR; < 1 = compression                 (coil)
A rolling statistic ending at bar t includes bar t (known at that close). Any reference
distribution a bar is scored against is lagged one bar, so no observation sits inside
its own reference. Forward outcomes are LABELS and are never fed back as state.

SCHEMES (exactly these five; no scheme is added, dropped or redefined after results)
  S1_trend      above_200dma x slope50_up                          -> 4 cells
  S2_extension  ext_pct, 4 equal-frequency bands                   -> 4 cells
  S3_vol        rvol_z,  4 equal-frequency bands                   -> 4 cells
  S4_coil       coil,    4 equal-frequency bands                   -> 4 cells
  S5_trend_vol  above_200dma x rvol_z (3 bands)                    -> 6 cells
Band edges are equal-frequency quantiles OF THE TRAINING COHORT ONLY (never the full
sample), refit on the quarterly schedule below. A bar missing any axis is uncodable
(-1) and is never silently pooled into a cell.

OUTCOMES / FRAMES
  Horizons H in {10, 21, 63} trading days, from engine.forward_dist.forward_paths:
    ret = close[t+h]/close[t] - 1, mae = worst dip, mfe = best pop, all in percent.
  PRIMARY FRAME is VOL-STANDARDIZED: (pct/100) / (vol_scale * sqrt(h)), where
    vol_scale = 20d realized daily vol LAGGED ONE BAR, floored at 0.005/day. A cone is
    therefore in "h-day sigmas" and is comparable across a multi-thousand-name
    cross-section; it re-scales to percent per name-date at emit.
  SECONDARY FRAME is the raw percent return, run at H=21 only, reported descriptively.
  Emitted per cell: return quantiles at tau in {0.05, 0.10, 0.25, 0.50, 0.75, 0.90,
    0.95}, MAE quantiles at {0.05, 0.25, 0.50}, MFE median, P(up), n.

COHORT + EMBARGO
  For as-of session t and horizon h, the training cohort is every panel observation
  (name, d) with
        d <= t - h - 1          (embargo: the outcome resolved STRICTLY before t)
    and d >  t - h - 1 - 504    (trailing window, 504 sessions)
  pooled ACROSS NAMES, restricted to the same state cell. Sessions are integer indices
  into the shared trading calendar, so the embargo is exact across holidays and gaps.

MIN-N FLOOR + DEGRADE
  A cell holding fewer than 400 pooled observations does NOT get its own thin
  quantiles: it inherits the pooled marginal and is stamped degraded=True with its own
  honest n preserved. A degraded cell is a null, printed, never a silent conditional.

WALK-FORWARD
  Refit boundaries are QUARTERLY. At the first evaluation session of each calendar
  quarter, band edges and every per-cell cone (and both baselines) are estimated on the
  embargoed cohort as of that session, then HELD FIXED for every evaluation date in the
  quarter. Because the fit is embargoed by h+1 sessions at the quarter start, every
  later evaluation date in that quarter is embargoed by at least that much.
  Evaluation dates: EVERY session from the first session on/after 2023-01-01 (the first
  ~18 months of the store are warm-up for the 252d references and the 504d cohort)
  through the last session with a fully realized H-horizon outcome. A date is skipped
  if its cross-section has fewer than 50 evaluable names.

BASELINES (the nulls that must be beaten; same cohort, same window, same frame)
  B0  pooled unconditional trailing distribution — no cells at all.
  B1  own-name trailing marginal — that name's own observations in the embargoed
      window, minimum 252; a name below that falls back to B0 and is stamped degraded.

METRICS
  pinball loss L_tau(y,q) = tau*(y-q) if y>=q else (tau-1)*(y-q); the score is the mean
    across the seven-tau grid, per observation, then averaged cross-sectionally per
    date (a CRPS proxy).
  coverage    = share of evaluated name-days with q10 <= y <= q90 (nominal 0.80).
  breach-run  = lag-1 autocorrelation of the per-date breach rate + longest run of
    dates above nominal. REPORT-ONLY: it carries no pre-registered null and gates
    nothing.
  MAE-p05 tail hit rate = share of name-days whose realized worst dip was at or beyond
    the predicted p05 dip (nominal 0.05).

STATS
  Skill deltas are formed PER DATE as (baseline mean pinball - scheme mean pinball), so
  a positive delta is skill, on the identical cross-section for both arms. The delta
  series is date-indexed and overlapping (h-day forward windows), so the CI is a
  circular BLOCK bootstrap with block = h (21 at the primary horizon), B = 5000,
  seed = 7, via engine.validation.block_bootstrap_ci; the interval in pinball units
  comes from engine.pick_forward_dist.block_bootstrap_mean_ci with the same settings.
  "Excludes 0" means the 2.5th and 97.5th percentiles of the bootstrap distribution
  fall on the same side of zero.

PRE-REGISTERED GATES (printed PASS/FAIL per scheme, at H=21, vol-standardized frame)
  G1 CALIBRATION   OOS 80%-band coverage in [0.72, 0.88].
  G2 SKILL vs B0   mean-pinball delta vs the pooled unconditional, date-blocked 95% CI
                   excluding 0 on the positive side.
  G3 SKILL vs B1   same, versus the own-name marginal.
  G4 CELL HONESTY  >= 80% of evaluated name-days sit in an above-floor (non-degraded)
                   cell. Below that the scheme is mostly marginal fallback wearing a
                   conditional label.
  Also reported, gating nothing: era-split (2023-24 vs 2025-26) sign stability of the
  G2 delta; n names / name-days / cells; coverage at H=10 and H=63; the raw-return
  frame at H=21; the breach-run statistic; the MAE-p05 tail hit rate.

VERDICT VOCABULARY (one per scheme; precedence top-down, first match wins)
  DEGENERATE       G4 fails — mostly marginal fallback, the cells are not real.
  MISCALIBRATED    G4 passes, G1 fails — the band is the wrong width.
  GO               G1-G4 all pass.
  CALIBRATED_ONLY  G1 and G4 pass, G2 and/or G3 fails — honest width, no measured edge.
These are DIAGNOSTIC verdicts. "GO" here means "this scheme survived phase-0 as
measured"; it authorizes nothing. Promotion to any ranked, sized or gated surface is a
separate adjudication the commissioning session owns.

FALSIFICATION POSTURE
  A failed gate is a RESULT and ships as one. Schemes are not redefined, thresholds are
  not moved, and horizons are not swapped after seeing a number: verdicts are issued
  ONLY at H=21, and H=10/H=63 are descriptive ladder rows that cannot become the
  headline. Nulls are printed.

AMENDMENTS (gaps closed BEFORE any compute; none after)
  AM-1  The commissioning brief states the panel ends 2026-07-28. It does not. The
        worktree's committed manifest claims latest_date 2026-07-28 / 20,677 tickers,
        but the parquets themselves (primary checkout) carry their own manifest reading
        latest_date 2026-07-02 / 19,133 tickers, and 20,476 parquet files. The READABLE
        data ends 2026-07-02; the committed manifest is ahead of the store it
        describes. This harness reports the calendar it actually read. A separate lane
        owns the publish outage; nothing here attempts to refresh or repair it.
  AM-2  Evaluation is at EVERY session, not a weekly subsample. A throughput probe
        (800 random names) measured before this header was frozen put the full panel
        build at ~2 minutes and the walk-forward at a few more, so the runtime budget
        does not force a subsample. Daily evaluation is also what makes block = h the
        correct block length: the dependence horizon is h SESSIONS, which is h
        OBSERVATIONS of the delta series only when the series is daily.
  AM-3  Band edges and cones are refit quarterly, while the module's cohort rule is
        stated "as of t". Quarter-start fitting is the conservative direction: a fit
        frozen at the quarter start is embargoed from every later evaluation date in
        that quarter by MORE than h+1 sessions, never less.
  AM-4  The min-cell floor of 400 pooled observations is unlikely to bind on a
        cross-section this wide (a 504-session cohort across thousands of names is
        millions of observations spread over 4-6 cells), which makes G4 a weak gate in
        THIS configuration. It is kept as pre-registered, and its weakness is stated in
        the results rather than fixed by moving the number after the fact.
  AM-5  B1 is fitted on the same quarterly schedule as everything else, so it is the
        name's own marginal as of the quarter start, not as of each evaluation date.
        That is the like-for-like comparison; giving one arm a fresher fit than another
        would be the confounded one.

Run:    python3 -m scripts.pick_forward_dist_phase0
        python3 -m scripts.pick_forward_dist_phase0 --max-names 400   # smoke
Writes: research/pick_forward_dist_phase0_results.json
        research/PICK_FORWARD_DIST_PHASE0.md
```

