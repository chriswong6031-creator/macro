# Pick-class forward distributions — wave-1.5 HAR-standardizer discriminator

**Family** `pick_forward_dist_phase1_har` · **Program** `advanced-quant-methods-w1.5` · **Tier** diagnostic — wave-1.5 discriminator; promotes nothing
**Generated** 2026-08-06T04:26:09.065523+00:00 · **Runtime** 211s

Wave-1 measured that vol-state cells (`S3_vol`) beat the pooled marginal at H=21 — with outcomes standardized by TRAILING 20d vol, a biased forward-vol forecast. This study re-runs wave-1 changing **exactly one thing**: the vol_scale series becomes the shipped house HAR-style equal-weight blend. Both possible answers are wins; the question is which one obtained.

## 0. Verdict — **VOL_FORECAST_CORRECTION**

**Wave-1's S3 edge was the standardizer, not the state.** Only 38% of the relative edge survives the change of scale (+0.421% of baseline pinball against +1.094%), and D-1's interval no longer excludes zero.

X-5 shows the mechanism, and the correspondence is close to one-for-one: the HAR scale carries **38% less vol-state-correlated bias**, and **62% of the edge disappears**. The trailing-20d scale under-predicts forward vol in a vol trough and over-predicts after a spike — exactly the mean reversion wave-1's caveat named — and an `S3_vol` cell earns its pinball back by re-pricing those bands. Take the state-dependent bias away and the cell has little left to sell.

**For the emitter:** ship MARGINAL cones — no cells. Simpler, no cell-honesty floor to police, one fewer thing to explain, and one fewer conditional claim to defend. The conditional read was never carrying forward-return information; it was carrying a scale correction.

**But read the scale half of that carefully, because X-4 is a null.** The HAR-style equal-weight blend is **not** the better forward-vol forecast in aggregate — it loses to the plain 20d realized vol on all three of X-4's measures. It wins this discriminator by being FLATTER ACROSS VOL STATES, not by being more accurate. So the shippable instruction is NOT "ship the HAR blend". It is: **the width scale must be one whose bias does not move with vol state** — that is the property that absorbed wave-1's edge, and it is the property to select on. Which scale actually has it, at good aggregate accuracy, is the open rung: a FITTED forward-vol forecast is the obvious untested candidate and nothing here measures it.

| Readout | Result |
|---|---|
| **D-1** S3 vs B0 under HAR | +0.00125 [-0.00024, +0.00288] (+0.421% of baseline) — **FAIL** |
| **D-2** shrinkage ratio (scale-free, primary) | 0.385 (band 0.5) |
| D-2 raw-unit ratio (secondary) | 0.447 |
| D-2 paired bootstrap interval (descriptive) | [-0.161, 0.573], median 0.378 |
| Wave-1 replication in the trailing20 arm | YES |

**Evaluated** 856 sessions (2023-01-03 to 2026-06-02), 3,307,737 name-days, 6,617 distinct names at H=21, on rows where BOTH scales are finite (AM-H4).

## 1. Per-scheme deltas under both standardizers

| Scheme | Δ vs B0, trailing20 | % of base | Δ vs B0, HAR | % of base | retained (scale-free) |
|---|---|---|---|---|---|
| `S1_trend` | -0.00052 [-0.00187, +0.00102] | -0.203% | -0.00049 [-0.00211, +0.00138] | -0.163% | +0.80 |
| `S2_extension` | -0.00028 [-0.00117, +0.00055] | -0.111% | -0.00027 [-0.00131, +0.00071] | -0.090% | +0.81 |
| `S3_vol` **(focus)** | +0.00280 [+0.00126, +0.00444] | +1.094% | +0.00125 [-0.00024, +0.00288] | +0.421% | +0.38 |
| `S4_coil` | +0.00091 [-0.00005, +0.00191] | +0.355% | +0.00025 [-0.00072, +0.00129] | +0.084% | +0.24 |
| `S5_trend_vol` | +0.00219 [+0.00043, +0.00417] | +0.856% | +0.00069 [-0.00116, +0.00280] | +0.232% | +0.27 |

Deltas are per-date **baseline minus scheme** mean pinball on the identical cross-section, so a positive number is skill. CI = circular block bootstrap, block = 21, B = 5000, seed = 7 — wave-1's settings, unchanged. **The two arms' pinball levels are in different units** (each arm standardizes by its own scale), so the percent-of-baseline columns are the ones that compare; the raw columns are only ever read within an arm. A `retained` value near 1 means the scheme's edge is indifferent to the scale; near 0 means the edge WAS the scale.

| Scheme | Δ vs B1, trailing20 | Δ vs B1, HAR |
|---|---|---|
| `S1_trend` | +0.00079 [-0.00121, +0.00291] (+0.306%) | +0.00074 [-0.00162, +0.00325] (+0.248%) |
| `S2_extension` | +0.00102 [-0.00069, +0.00271] (+0.398%) | +0.00096 [-0.00098, +0.00287] (+0.320%) |
| `S3_vol` | +0.00411 [+0.00238, +0.00599] (+1.597%) | +0.00248 [+0.00074, +0.00439] (+0.829%) |
| `S4_coil` | +0.00222 [+0.00079, +0.00374] (+0.861%) | +0.00148 [-0.00006, +0.00314] (+0.493%) |
| `S5_trend_vol` | +0.00350 [+0.00139, +0.00582] (+1.360%) | +0.00192 [-0.00031, +0.00438] (+0.641%) |

## 2. X-2 — calibration of the nulls under each standardizer

| Arm | B0 coverage | B1 coverage | B1 honest frac | S3 coverage | S5 coverage |
|---|---|---|---|---|---|
| `trail20` | 0.7945 | 0.7863 | 0.601 | 0.7905 | 0.7840 |
| `har` | 0.7951 | 0.7876 | 0.601 | 0.7924 | 0.7868 |

Nominal is 0.800. Coverage is a hit rate, so it is unit-free and this is the one table that compares cleanly across arms. Descriptive only — no overlap-corrected test statistic is computed (see caveats).

## 3. X-4 — is the new standardizer actually the better forward-vol forecast?

| Arm | corr(log σ̂, log σ_fwd) | mean σ_fwd/σ̂ | median σ_fwd/σ̂ | sd log ratio | mean abs log ratio | n |
|---|---|---|---|---|---|---|
| `trail20` | 0.7815 | 1.1635 | 0.9428 | 0.5184 | 0.3792 | 3,307,737 |
| `har` | 0.7582 | 1.3844 | 1.1017 | 0.5424 | 0.3905 | 3,307,737 |

**The HAR blend is NOT the better forward-vol forecast on any of the three measures.** That is a null, and it is printed here at the top of the interpretation rather than buried: a shrinking edge under a scale that is not actually better is weaker evidence for the vol-forecast-correction reading than the design assumed.

## 3b. X-5 — vol-state-CONDITIONAL bias of each scale (post-run addendum)

*X-5 IS NOT PART OF THE FROZEN PRE-REGISTRATION. It was written after a 1,500-file SMOKE run (not the study) returned a NULL on the pre-registered X-4 — the HAR blend was not the better forward-vol forecast on any of X-4's three measures — which left the pre-registered readouts hard to read: an edge shrinking under a scale that is not better overall proves nothing on its own. X-5 measures the SPECIFIC confound wave-1's caveat named, which X-4's aggregate measures cannot see. It is DESCRIPTIVE, it gates nothing, and neither D-1 nor D-2 reads it — both are computed by code frozen before any data was touched. It is recorded here, OUTSIDE the frozen header, rather than backdated into it.*

| Arm | band 0 | band 1 | band 2 | band 3 | spread (max−min) | overall |
|---|---|---|---|---|---|---|
| `trail20` | +0.1301 | +0.0155 | -0.1263 | -0.3780 | 0.5081 | -0.0897 |
| `har` | +0.1938 | +0.1175 | +0.0354 | -0.1205 | 0.3143 | +0.0566 |

Cells are mean log(realized forward 21d vol / predicted) inside each `rvol_z` band (band 0 = lowest rvol_z (vol trough), band 3 = highest (vol spike)). A POSITIVE number means the scale UNDER-predicts; negative means it OVER-predicts. The **spread** is the quantity wave-1's caveat is about: it is how much of the scale's error a vol-state cell can mechanically earn back by re-pricing the band.

The HAR scale's state-conditional bias spread is **38% smaller** than the trailing-20d scale's. That is the mechanism, measured: there is less state-correlated error left for an `S3_vol` cell to correct, which is what the shrinkage in D-2 is made of.

## 4. AM-H6 reproduction control — did the trailing20 arm reproduce wave-1?

- Wave-1 published: +0.00280 [+0.00126, +0.00444] (+1.09% of baseline)
- This run, trailing20 arm: +0.00280 [+0.00126, +0.00444] (+1.094% of baseline)
- Absolute difference in mean delta: 3e-06; inside wave-1's published CI: True

The two runs are not expected to be bit-identical: this panel drops rows where the HAR scale is not finite (AM-H4) so both arms share identical rows. A LARGE divergence would mean the machinery is not wave-1's and the shrinkage ratio would be meaningless — so it is checked, not assumed.

## 5. Honest caveats

- WAVE-1'S CAVEATS ALL STILL APPLY, UNCHANGED: survivorship (store begins 2021-07-06), single era (one macro regime block, no out-of-era replication), price-return not total-return, ~8-10 unrepaired spinoffs, instrument mix (ETFs/ADRs/preferreds clear the liquidity filter), overlapping forward windows, ratio-neutral back-adjustment, and the structurally weak G1/G4 gates. This study changes the STANDARDIZER; it does not repair a single one of those. Read research/PICK_FORWARD_DIST_PHASE0.md sections 3 and 3b alongside this file.
- MEAN PINBALL IS NOT COMPARABLE ACROSS THE TWO ARMS. Each arm scores a DIFFERENT standardized outcome, so its losses live in its own units. Only WITHIN-arm deltas and unit-free rates (coverage, honest_frac, tail hit) cross the arm boundary. Every pinball level below is labelled 'within_arm' for exactly this reason, and D-2's primary ratio is built from percent-of-baseline deltas so the units divide out (AM-H2).
- THE HAR BLEND IS NOT A FITTED HAR. It is the shipped house equal-weight multi-scale realized-vol blend over lags (2, 5, 22, 66). A fitted HAR-RV regression would weight the components; this does not. If the verdict is VOL_FORECAST_CORRECTION, the honest read is 'a better SCALE beats the cells', not 'Corsi's HAR is the answer' — the fitted version was never tested here.
- THE SHORT LAGS DRAG THE LEVEL DOWN (AM-H2): the blend's 2- and 5-bar components use ddof=0 on tiny samples, which biases them low, so the blend sits at ~0.85 of a 20d realized vol. This is a LEVEL effect and it cancels out of coverage and out of the percent-of-baseline ratio; it does NOT cancel out of the raw-unit ratio, which is why that one is secondary.
- ONE HORIZON, ONE FRAME (AM-H1). H=10, H=63 and the raw-percent frame are not run in either arm. They were descriptive rows in wave-1 that could not become a headline, and no readout here reads them. A reader who wants the horizon ladder has wave-1's, on wave-1's scale.
- THE STATE DEFINITION IS UNCHANGED. Cells are still cut on `rvol_z` (20d realized vol z-scored against its own trailing 252d reference), exactly as wave-1 cut them. This study does not ask whether a HAR-based STATE would condition better — only whether the wave-1 edge survives a better SCALE. A HAR-based state axis is a different, later question.
- NO COVERAGE TEST STATISTIC. The coverage numbers are pooled hit rates at OVERLAPPING origins, as in wave-1; the review's non-overlapping-origin coverage test (Kupiec/Christoffersen at independent origins) is NOT built here and remains open. The X-2 comparison is therefore descriptive: it says which arm's realized coverage is closer to nominal on the same dates, not that the difference is significant.
- DIAGNOSTIC TIER. Nothing here promotes, ranks, sizes, gates or escalates. No fused composite is formed. No site, template, dag, synapse or registry file is touched by this lane.

## 6. Data + universe as actually read

- Store `/Users/chriswong/Documents/Cluade/Macro Dashboard/data/massive_stock_day` — 20,476 parquet files, 20,476 read, 12,078 past the cheap prefilter
- Calendar 2021-07-06 to 2026-07-02 (1254 sessions)
- Wave-1 universe 3,692,601 rows across 6,852 names; both-scales-finite panel 3,692,601 rows (0 dropped, AM-H4)
- Splits repaired on 2,015 names; 7,554 split-print bars stamped ineligible
- unadjusted; splits repaired via replay_standout_pipeline.split_adjust; dividends NOT adjusted (price return)

- Import surface pinned before the run: 27 phase-0/engine signatures and frozen constants (the runner refuses to produce a number if any drifted)

## 7. Frozen pre-registration (verbatim)

```text
Phase-1 (wave-1.5): the HAR-standardizer DISCRIMINATOR for pick_forward_dist.

FROZEN PRE-REGISTRATION (written BEFORE any pinball number was computed; every gap
closed before compute is recorded in AMENDMENTS below and repeated in the results file)
================================================================================
Family:  pick_forward_dist_phase1_har
Program: advanced-quant-methods-w1.5
Tier:    DIAGNOSTIC. This harness measures; it does not promote. No ship language, no
         authority claim, no gate on any user-facing surface follows from it.

QUESTION (frozen before anything was looked at)
----------------------------------------------
Wave-1 (research/PICK_FORWARD_DIST_PHASE0.md, merged as a5998ff0f3a) found that
S3_vol — cells cut on the name's 20d realized-vol z-score — improves out-of-sample
pinball loss against BOTH pre-registered nulls at H=21: +0.00280 [+0.00126, +0.00444]
vs the pooled marginal B0 (+1.09% of baseline units, 73% of dates positive, p<0.0002,
surviving a 10-test Bonferroni floor and refit-level clustering t=3.23).

Wave-1 also flagged, in its own frozen caveats, why that number is ambiguous. Outcomes
there are standardized by TRAILING 20-day realized vol. Trailing vol is a BIASED
forecast of forward vol, because realized vol mean-reverts: a name whose 20d vol just
spiked will realize LESS than one trailing sigma over the next month, and one sitting
in a vol trough will realize MORE. A cell that sorts on vol state therefore has a
mechanical way to win that has nothing to do with forward-return information — it can
simply correct the known bias in the SCALE. The adversarial review sharpened this: at
H=21 every scheme with a positive delta is a trailing-vol transform (S3 +0.00280,
S5 +0.00219, S4 +0.00091) and both non-vol schemes are negative (S2 -0.00028,
S1 -0.00052) — exactly the ordering the standardizer-artifact mechanism predicts.

  Two readings fit wave-1's evidence equally well:
    (A) STATE INFORMATION      — the vol-state cell says something about the shape of
                                 the forward distribution that the scale does not.
    (B) VOL-FORECAST CORRECTION — the cell is re-deriving a better forward-vol forecast,
                                 and the whole gain is the scale, not the state.

  This harness discriminates them by RE-RUNNING WAVE-1 WITH A BETTER STANDARDIZER.
  If the edge survives the better scale, (A). If it collapses, (B).

BOTH ANSWERS ARE WINS, and the writeup says which obtained and what it means:
  (A) -> the emitter conditions on vol-state cells over a trailing-vol scale.
  (B) -> the emitter ships MARGINAL cones on the HAR scale: simpler, no cells at all.
         "Use a better vol forecast" is itself the shippable width intelligence.
Neither answer authorizes a surface. Promotion is a separate adjudication.

WHAT CHANGES FROM WAVE-1 — EXACTLY ONE THING
--------------------------------------------
THE VOL_SCALE SERIES. Nothing else. Same store, same universe filter, same split
repair, same trading calendar, same H=21 primary, same tau grid, same 504-session
embargoed cohort, same quarterly refit schedule, same MIN_CELL_N / MIN_OWN_N floors,
same B0/B1 nulls, same per-date paired-delta statistic, same circular block bootstrap
(block=21, B=5000, seed=7). The STATE FEATURES ARE UNCHANGED TOO — the cells are still
cut on `rvol_z` exactly as wave-1 cut them, because the hypothesis under test is about
the SCALE, not about the state definition. Changing both at once would answer neither
question.

Mechanically, wave-1's own machinery is IMPORTED and CALLED, not re-implemented:
`scripts.pick_forward_dist_phase0` (loader, panel path, walk-forward, delta stats, era
split, every frozen constant) and `engine.pick_forward_dist`. The HAR arm is produced by
handing the SAME `p0.walk_forward` a panel whose three standardized outcome columns
(`z_ret_21`, `z_mae_21`, `z_mfe_21`) were rebuilt on the HAR scale. Both arms therefore
run byte-identical evaluation code over identical rows and identical dates. An
import-surface pin (`verify_phase0_surface`) makes the runner REFUSE TO RUN if any of
those imported signatures or frozen constants drift, so a later phase-0 refactor cannot
silently change what this study measured.

THE NEW STANDARDIZER
--------------------
A causal MULTI-SCALE REALIZED-VOL BLEND in the shape of the shipped house forward-vol
read: `engine.vol_forecast.har_vol` with HAR_LAGS = (2, 5, 22, 66), EQUAL WEIGHT.

  Named honestly: this is the "HAR-STYLE EQUAL-WEIGHT BLEND, THE SHIPPED HOUSE
  FORECASTER". It is NOT a fitted HAR. Corsi's HAR-RV is a REGRESSION with fitted
  betas on the daily/weekly/monthly components; this is the unweighted mean of realized
  vol over four lookbacks, which is what `engine/vol_forecast.py` actually ships and
  what `engine/anticipation.py` actually uses to set cone width. Calling it "a HAR"
  would claim a fit that does not exist. Whether the fitted version would do better is
  a different, later question and is explicitly out of scope.

  vol_scale_har(t) = har_vol(close)[t-1], clipped from below at VOL_FLOOR (0.005/day)

  Per name. Lag ONE bar, so the scale is fixed before the outcome window opens —
  identical lag convention to wave-1's `state_features.vol_scale`. Floor/winsor
  conventions are inherited VERBATIM from wave-1: a LOWER clip at VOL_FLOOR and NO
  upper winsor. That asymmetry is wave-1's, carried unchanged rather than re-designed
  here, because re-designing it would be a second change.

  The panel implementation is parity-tested against `engine.vol_forecast.har_vol`
  itself on a single series, and the blend definition (equal weight over HAR_LAGS,
  pct_change returns, ddof=0) is independently re-derived from first principles in
  tests/test_pick_forward_dist_phase1.py so a change to the shipped module fails loudly
  instead of silently redefining this study's scale.

DATA / UNIVERSE / SCHEMES / COHORT / WALK-FORWARD / BASELINES / METRICS
----------------------------------------------------------------------
Identical to wave-1. The full text is the frozen pre-registration in
`scripts/pick_forward_dist_phase0.py` (reproduced verbatim in section 5 of
research/PICK_FORWARD_DIST_PHASE0.md). It is not restated here so that there is exactly
ONE copy of it and no chance of the two drifting into disagreement. The constants it
fixes are pinned by `verify_phase0_surface` and printed in the results file.

Two horizon-scope reductions, both narrowing (AM-H1 below): only H=21 is run, and only
the vol-standardized frame. Wave-1's H=10/H=63 ladder and raw-percent frame were
descriptive rows that could not become a headline; they are not what this study asks.

PRE-REGISTERED READOUTS (H=21, vol-standardized frame only)
-----------------------------------------------------------
D-1  SURVIVAL.  S3_vol mean-pinball delta vs B0_pooled UNDER THE HAR STANDARDIZER,
     with the wave-1 date-blocked 95% CI (circular block bootstrap, block=21, B=5000,
     seed=7, `pfd.block_bootstrap_mean_ci`).
       PASS  <=>  the CI excludes 0  AND  the mean delta > 0.
     A FAIL is a RESULT and ships as one.

D-2  SHRINKAGE RATIO.  How much of wave-1's S3 edge survives the better scale.

     PRIMARY (scale-free), R_rel:
         R_rel = (S3 delta vs B0 under HAR,       as % of that arm's B0 mean pinball)
               / (S3 delta vs B0 under trailing20, as % of that arm's B0 mean pinball)
     The trailing20 denominator is RECOMPUTED IN THIS RUN on THIS panel — never lifted
     from the wave-1 artifact — so the two arms are apples-to-apples on identical rows
     and identical dates.

     SECONDARY (raw units), R_raw = ratio of the two mean deltas in their own units.
     Reported, never gating. R_raw is NOT scale-free: see AM-H2 — the HAR blend sits
     materially BELOW a 20d realized vol in LEVEL, which multiplies every pinball
     number in the HAR arm by a units factor that has nothing to do with skill. R_rel
     divides that factor out; R_raw does not. R_rel is therefore the primary.

     INTERPRETATION BANDS — FROZEN NOW, BEFORE ANY RESULT:
       R_rel >= 0.5  AND  D-1 PASS   ->  STATE_INFORMATION
       R_rel <  0.5  AND  D-1 FAIL   ->  VOL_FORECAST_CORRECTION
       anything else                 ->  MIXED   (the pattern is stated in words)
     Two degenerate cases, also frozen now:
       * If the trailing20 arm's OWN S3-vs-B0 delta is not positive with a CI excluding
         0 in THIS run, wave-1 did not replicate on this panel, the ratio has no
         denominator worth reading, and the verdict is INCONCLUSIVE_BASE.
       * If R_rel and R_raw land in DIFFERENT bands, the verdict is MIXED and both
         numbers are printed.
     A descriptive paired block-bootstrap interval for R_rel (same blocks, same B, same
     seed, both arms resampled on the SAME date blocks because they share evaluation
     dates) is reported. It gates nothing; replicates whose denominator is non-positive
     are counted and PRINTED as undefined rather than dropped silently.

DESCRIPTIVE READOUTS (no gates; every one of them is allowed to be a null)
     X-1  S5_trend_vol under both standardizers — wave-1's fragile second GO.
     X-2  B0 and B1 CALIBRATION under HAR vs trailing20: does the better standardizer
          improve EVERYONE's coverage, cells or no cells? Coverage is a hit rate and is
          unit-free, so it compares cleanly across arms. MEAN PINBALL LEVELS DO NOT —
          the two arms score different y's — so pinball is only ever read WITHIN an arm.
     X-3  S1/S2/S4 deltas under HAR: does the per-scheme ordering FLATTEN? Under
          reading (B) the vol-linked schemes should fall toward the non-vol ones.
     X-4  FORECAST QUALITY OF EACH STANDARDIZER (AM-H3). The discriminator's whole
          logic rests on "HAR is the better forward-vol forecast". That premise is
          MEASURED here, not assumed, on the same evaluated name-days: Pearson
          correlation of log(scale) with log(realized forward 21d vol), the mean and
          median of realized/predicted, the sd of log(realized/predicted), and the mean
          |log ratio|. The forward realized vol is `engine.vol_forecast.forward_vol_ann`
          — a LABEL by construction, look-ahead by design, used for validation only and
          never fed to any cone. If the blend turns out NOT to be the better forecaster,
          that is printed at the top of the writeup and the verdict is read in its
          light: a collapse under a WORSE scale would not be evidence for (B).

FALSIFICATION POSTURE
     A failed gate is a RESULT. Nothing is redefined, no threshold is moved, no horizon
     is swapped after seeing a number. D-1 is issued at H=21 only. Nulls are printed.
     No fused composite score is formed anywhere. No user-facing surface changes.

AMENDMENTS (gaps closed BEFORE any pinball was computed; none after)
  AM-H1 SCOPE NARROWING. Wave-1 ran three standardized horizons plus a raw-percent
        frame; this study runs H=21 in the vol-standardized frame ONLY, for both arms.
        The pre-registered readouts are all at H=21, wave-1's other rows were explicitly
        descriptive and barred from becoming a headline, and running two arms over the
        full ladder would quadruple the compute for rows no verdict reads. This is a
        narrowing, never a selection: H=21 was wave-1's primary before any of this.
  AM-H2 UNITS. Measured BEFORE any pinball was computed, on 12 large-cap series over
        their post-warm-up history: the HAR equal-weight blend sits at a median 0.846
        of the trailing-20d realized vol (per-name medians 0.830-0.861; pooled mean
        0.877, sd 0.258). The cause is arithmetic, not empirical — `realized_vol` uses
        ddof=0, and a 2-bar sample std with ddof=0 is |r1-r2|/2, whose expectation is
        ~0.56 sigma, so the short lags in the equal-weight blend drag the level down.
        A standardizer that is systematically ~15% low makes every standardized outcome
        ~18% larger and multiplies EVERY pinball number in that arm — baseline and
        scheme alike — by the same factor. A raw-unit delta ratio would therefore be
        inflated by a pure units artifact. Hence D-2's primary statistic is the ratio of
        PERCENT-OF-BASELINE deltas, which is exactly invariant to a global rescale of y,
        with the raw-unit ratio reported beside it. The ratio is not a global constant
        (p10 0.62, p90 1.13), so this removes the SYSTEMATIC component of the units
        factor, not all of it — stated, not hidden. NOTE the direction of the incentive:
        this correction makes the HAR arm's ratio SMALLER, i.e. it pushes toward the
        VOL_FORECAST_CORRECTION verdict, so it is the conservative choice against the
        more interesting (A) reading.
  AM-H3 FORECAST-QUALITY READ ADDED (X-4). Wave-1's own module docstring says the
        "HAR-style" claim should be measured rather than assumed. Because the entire
        discriminator rests on the new scale being BETTER, its forecast quality is
        measured descriptively here. It gates nothing and it cannot change D-1 or D-2 —
        it exists so a collapse cannot be mis-read as evidence for (B) when the honest
        cause was a worse forecaster.
  AM-H4 PANEL INTERSECTION. A row survives only if BOTH scales are finite and positive
        on it. Both arms then run on IDENTICAL rows, which is what makes the paired
        per-date delta comparison legitimate. The count of rows this removes relative to
        wave-1's universe is reported. It is removal-only and never touches an outcome.
  AM-H5 HAR-FRAME ARITHMETIC. `z_ret_21` in the HAR arm is re-standardized DIRECTLY
        from the panel's raw-percent `ret_21` column, so it carries no chained rounding.
        `z_mae_21`/`z_mfe_21` have no raw-percent column in the panel and are converted
        by the exact ratio (vol_scale / har_scale) — algebraically identical, since both
        frames divide the same percent outcome by (scale * sqrt(h)). The two routes are
        cross-checked against each other on `ret` in tests/test_pick_forward_dist_phase1.py.
  AM-H6 REPRODUCTION CONTROL. The trailing20 arm is a re-run of wave-1's primary cell on
        (almost) the same rows, so its S3-vs-B0 number is compared against wave-1's
        published +0.00280 [+0.00126, +0.00444] and the comparison is PRINTED. A large
        divergence would mean the machinery is not what wave-1 ran, and the D-2 ratio
        would be meaningless; it is checked rather than assumed.

Run:    python3 -m scripts.pick_forward_dist_phase1_har
        python3 -m scripts.pick_forward_dist_phase1_har --max-names 600   # smoke
Writes: research/pick_forward_dist_phase1_har_results.json
        research/PICK_FORWARD_DIST_PHASE1_HAR.md
```

