# Synthetic control for event studies — Phase-0 (wave-2a)

*Run 2026-08-06 · charter `research/ADVANCED_QUANT_METHODS_ADJUDICATION_BY_FABLE.md` §3#5 · frozen pre-registration in `scripts/synthetic_control_phase0.py`*

**DIAGNOSTIC TIER.** This grades an *estimator*, not a signal. No event family here is being scored for tradability; two families whose answers the house already established are used as instruments to measure whether donor-pool synthetic control tells the truth on this panel. Nothing here promotes anything or gates any surface.

**Run MANUALLY, off the render path.** This study is not wired into `daily.yml`, `render.yml` or `config/dag.yml` and must not be: a full run is ~111 minutes against the whole 20k-file store, comfortably more than the entire nightly render budget (HOUSE-U6). It is re-run by hand when the estimator or the event families change.

## Verdict: `ESTIMATOR_BIASED`

Failing gate(s): **PC2_estimators_unbiased**

| Gate | Result | Reading |
|---|---|---|
| PC-1 positive control survives | **PASS** | sc_nnls S&P pure-add CAAR[0,5]=3.015% event-weighted / 4.907% month-weighted, monthly-NW t=8.291 (need both >0 and t>2) |
| PC-2 estimators unbiased | **FAIL** | sp_pure_adds/matched_k mean=0.190% t=4.316 FAIL; sp_pure_adds/sc_nnls mean=0.197% t=4.535 FAIL; phase3_start/matched_k mean=0.143% t=15.429 FAIL; phase3_start/sc_nnls mean=0.137% t=15.431 FAIL (need |mean|<0.3% and |t|<2 on BOTH families) |
| PC-3 SC not noisier | **PASS** | sc_nnls placebo SD=0.614% vs SPY-CAR placebo SD=0.650% (need SC <= incumbent) |
| F-1 falsifier holds | **PASS** | phase3 sc_nnls CAAR[0,20]=0.496% monthly-NW t=1.662 empirical p=0.731 (need |t|<2 and p>0.05) |

## Panel

- Store: `/Users/chriswong/Documents/Cluade/Macro Dashboard/data/massive_stock_day` — 20,476 parquet files, 15,244 names kept after the removal-only prefilter
- Calendar: 2021-07-06 → 2026-07-02 (1,254 sessions)
- Split repairs applied to 2,298 names (`scripts.replay_standout_pipeline.split_adjust`, close-only, factor carried onto volume)
- Pre-window 120 sessions ending t−6; donor exclusion ±21 sessions; coverage ≥90%; 20d median dollar volume ≥ $2,000,000; close > $5

## Positive control — S&P pure adds

- Event day rule: effective_date - 5 sessions (announce proxy)
- 303 of 361 in-scope events fitted (mean eligible donor pool 3,975 names)
- **58 of 361 events (16.1%) produced no estimate** and are absent from every number in this table: 58 because the treated name has a hole in its own 120-session fitting window, 0 for a donor pool below the pre-screen width, 0 for a short pre-screen. The dominant cause is SYMBOL DISCONTINUITY, not illiquidity: `massive_stock_day` keys by CURRENT symbol, so a renamed or merged company carries history only under the symbol it holds today (PARA, ELV, GEHC, WBD, BALL, RVTY, WTW in this window; even META shows a multi-month hole). The headline is therefore computed on SURVIVORS. PC-1's verdict is robust to this — it would take an implausible reversal among the dropped events to overturn a t of this size — but the point estimate is a survivor statistic and is not directly comparable to the incumbent's, which fetches prices per-ticker and keeps them.
- **Cohort labelling inherits a house defect.** `engine.index_changes.classify_cohort` calls an add "pure" when it finds no prior PIT membership row, which also catches ticker RENAMES and SPIN-OFFS — entities that were already inside the S&P universe under another symbol and therefore DO have an offsetting forced seller (roughly seven such names in the 2022+ window). Reproducing the incumbent's construction faithfully was the point of this control, so the defect is disclosed here and deliberately NOT fixed in this PR; fixing it would change the family and break the comparison it exists to make.
- Ticker-clustered t is **not reported** for this family: 361 tickers across 361 events means clusters are effectively singletons, and the estimator collapses to the plain iid t the pre-registration itself calls invalid here.
- Scope 2022-01-01 → panel end; construction diagnostics: `{"raw_adds_all_time": 3286, "cohort_counts": {"pure": 2727, "migration": 503, "readd": 56}, "pure_all_time": 2727, "pure_in_scope_date": 366, "events_usable": 361}`

- Placebo null runs on 357 events (4 had no eligible placebo date and were dropped rather than left at their real session)

| Arm | Window | CAAR (event-wtd) | CAAR (month-wtd) | monthly-NW t | ticker-cluster t | hit rate | placebo mean | placebo SD | empirical p |
|---|---|---|---|---|---|---|---|---|---|
| `matched_k` | [0] | 0.236% | 0.063% | 0.449 | None | 0.568 | 0.006% | 0.129% | 0.085 |
| `matched_k` | [0,5] | 2.890% | 5.047% | 8.392 | None | 0.7 | 0.190% | 0.624% | 0.01 |
| `matched_k` | [0,20] | 2.179% | 4.560% | 4.67 | None | 0.614 | 0.789% | 1.345% | 0.08 |
| `sc_nnls` | [0] | 0.259% | 0.093% | 0.624 | None | 0.584 | 0.015% | 0.118% | 0.07 |
| `sc_nnls` | [0,5] | 3.015% | 4.907% | 8.291 | None | 0.696 | 0.197% | 0.614% | 0.01 |
| `sc_nnls` | [0,20] | 2.205% | 4.240% | 4.175 | None | 0.627 | 0.818% | 1.332% | 0.045 |
| `SPY` | [0] | -0.044% | -0.122% | -0.676 | None | 0.528 | -0.001% | 0.148% | 0.781 |
| `SPY` | [0,5] | 2.852% | 5.184% | 7.877 | None | 0.693 | 0.142% | 0.650% | 0.01 |
| `SPY` | [0,20] | 2.342% | 4.409% | 4.812 | None | 0.614 | 0.685% | 1.399% | 0.07 |

**Reconciliation against the incumbent's exact statistic.** `validate_index_reconstitution.py` scores a SPY-relative PRICE RATIO over [-5,0] — five daily returns, where this study's CAR[0,5] sums six (AM-7). Recomputing the incumbent's own construction on THIS study's event list gives 2.895% (t=7.183, n=309, 52 months). The house publishes 1.640% (t=4.63, n=877) on 2019→ and 1.990% (t=5.02, n=266) on its recent cut.

The recent cut is the nearest published comparator to this window, and **0.905% of the difference is not explained by the sample period**. Index mix is ruled out (both are pure adds across the same three indices) and the constructions agree, so the residual is a coverage/construction gap — most plausibly the event-list attrition disclosed above, which drops symbol-discontinuous names the incumbent's own price fetch keeps. It is stated here rather than absorbed into the word "sample".

## Falsifier — ClinicalTrials Phase-3 starts

- Event day rule: StudyFirstPostDate (first public availability)
- 740 of 744 in-scope events fitted (mean eligible donor pool 4,014 names)
- **4 of 744 events (0.5%) produced no estimate** and are absent from every number in this table: 4 because the treated name has a hole in its own 120-session fitting window, 0 for a donor pool below the pre-screen width, 0 for a short pre-screen. The dominant cause is SYMBOL DISCONTINUITY, not illiquidity: `massive_stock_day` keys by CURRENT symbol, so a renamed or merged company carries history only under the symbol it holds today (PARA, ELV, GEHC, WBD, BALL, RVTY, WTW in this window; even META shows a multi-month hole). The headline is therefore computed on SURVIVORS. PC-1's verdict is robust to this — it would take an implausible reversal among the dropped events to overturn a t of this size — but the point estimate is a survivor statistic and is not directly comparable to the incumbent's, which fetches prices per-ticker and keeps them.
- Scope 2022-01-01 → panel end; construction diagnostics: `{"raw_rows": 1656, "uniq_nct": 1593, "phase3_rows": 1656, "ticker_date_cells_all_time": 1461, "cells_in_scope_date": 831, "sponsors": 19, "events_usable": 744}`

| Arm | Window | CAAR (event-wtd) | CAAR (month-wtd) | monthly-NW t | ticker-cluster t | hit rate | placebo mean | placebo SD | empirical p |
|---|---|---|---|---|---|---|---|---|---|
| `matched_k` | [0] | -0.028% | -0.041% | -0.696 | -0.629 | 0.508 | 0.023% | 0.056% | 0.348 |
| `matched_k` | [0,5] | 0.164% | 0.129% | 0.9 | 1.162 | 0.507 | 0.143% | 0.131% | 0.876 |
| `matched_k` | [0,20] | 0.588% | 0.677% | 1.86 | 1.755 | 0.528 | 0.421% | 0.257% | 0.527 |
| `sc_nnls` | [0] | -0.038% | -0.042% | -0.79 | -0.697 | 0.497 | 0.023% | 0.054% | 0.299 |
| `sc_nnls` | [0,5] | 0.132% | 0.084% | 0.631 | 0.793 | 0.492 | 0.137% | 0.126% | 0.975 |
| `sc_nnls` | [0,20] | 0.496% | 0.567% | 1.662 | 1.371 | 0.541 | 0.406% | 0.240% | 0.731 |
| `SPY` | [0] | -0.046% | -0.055% | -0.731 | -0.844 | 0.5 | -0.009% | 0.065% | 0.602 |
| `SPY` | [0,5] | 0.015% | 0.112% | 0.513 | 0.096 | 0.495 | -0.015% | 0.154% | 0.811 |
| `SPY` | [0,20] | 0.164% | 0.435% | 0.677 | 0.427 | 0.505 | -0.099% | 0.302% | 0.388 |
| `XLV` | [0] | 0.008% | -0.008% | -0.135 | 0.139 | 0.523 | 0.029% | 0.056% | 0.741 |
| `XLV` | [0,5] | 0.283% | 0.173% | 1.073 | 1.915 | 0.518 | 0.172% | 0.123% | 0.393 |
| `XLV` | [0,20] | 0.902% | 0.889% | 2.771 | 2.191 | 0.568 | 0.536% | 0.231% | 0.134 |

## What the numbers mean

**Positive control.** Over the announce window the incumbent SPY-adjusted CAR reads 2.852% (t=7.877), the equal-weight donor basket 2.890% (t=8.392), and the fitted synthetic control 3.015% (t=8.291). The house's graded number for this family is +1.64% at t=4.63 on the full 2019→ sample; this run is restricted to 2022-01-01→ by the store's 2021-07 start, so the samples differ — the comparison is directional, not a replication.

**Power.** Under the null the fitted SC's aggregate estimate has placebo dispersion 0.614%, the equal-weight basket 0.624%, the incumbent 0.650% (0.94× the incumbent). A counterfactual that is not tighter than SPY under the null has bought nothing, whatever it does to the point estimate — that is what PC-3 grades.

**Centring.** At random dates on the same names the arms read 0.197% (fitted SC), 0.190% (equal-weight) and 0.142% (incumbent SPY-CAR). The fitted SC is offset MORE than the incumbent, so the offset is the estimator's own and not merely the cohort's — the donor pool is not spanning these names, and the weights are buying a systematic shortfall rather than removing one. The harness itself manufactures nothing: on a synthetic no-effect panel the same code path returns zero within sampling error (tests/test_synthetic_control.py::test_placebo_machinery_returns_zero_on_a_no_effect_panel), so this offset is in the data, not in the estimator's arithmetic.

**Falsifier.** On Phase-3 starts the fitted SC reads 0.496% over [0,20] with monthly-NW t=1.662 and empirical p=0.731 against its own random-date placebo; day 0 is -0.038% (t=-0.79). The house verdict on record for this family is NULL — placebo-explained — and F-1 asks only that SC not overturn it.

**Pre-registered verdict: `ESTIMATOR_BIASED`** — failing PC2_estimators_unbiased. A failed gate is a result: it says where this estimator may and may not be trusted, and nothing here promotes it into any scored path.

## Gate honesty — what these gates can and cannot discriminate

*Written after running them, deliberately kept out of the frozen pre-registration so the gates were not retro-fitted to the answer.*

- **PC-2 mixes an estimator question with a cohort question, and the two families answer differently.** Every arm drifts in the same direction at random dates, including the incumbent SPY-CAR arm that is NOT under test — so direction alone settles nothing. The discriminating comparison is MAGNITUDE against the incumbent, on identical draws: S&P pure adds: fitted SC 0.197% (t=4.535), equal-weight 0.190%, incumbent SPY-CAR 0.142% (t=3.084) — SC is 1.39x the incumbent's offset; Phase-3 starts: fitted SC 0.137% (t=15.431), equal-weight 0.143%, incumbent SPY-CAR -0.015% (t=-1.394) — SC is 9.06x the incumbent's offset. On S&P pure adds and Phase-3 starts the fitted SC is offset MORE than the incumbent it is supposed to improve on, so on those families the offset is NOT merely the cohort's — the donor pool is not spanning these names and the weights are buying a systematic shortfall rather than removing one. Note also that the incumbent arm is not uniformly worse: where it clears the t-arm that the SC arms fail, PC-2 is separating estimators rather than describing the cohort. Read the per-arm table, not the gate flag.
- **PC-1 and PC-3 are the gates that can actually separate the arms**, because both are comparisons: PC-1 against a number the house already graded, PC-3 against the incumbent's own placebo dispersion on identical draws. PC-2 and F-1 are absolute thresholds and inherit whatever the cohort does.
- **PC-2's |t|<2 arm is controlled by the DRAW COUNT, not by the estimator.** That t is the Monte-Carlo standard error of the placebo mean (mean / (sd/sqrt(B))), so for any non-zero cohort drift it grows as sqrt(B) without bound. Across the four arm x family cells: B=50: |t| 2.16–7.72 (FAIL) · B=200: |t| 4.32–15.43 (FAIL) · B=1000: |t| 9.65–34.50 (FAIL). So the arm does NOT flip at a plausible B — it would take B <= 3 for every cell to clear |t|<2, which is far too few draws to estimate a null distribution at all. The honest statement is that this arm is guaranteed to fail at ANY usable draw count once the cohort drift is non-zero, which makes it a test of 'is the drift exactly zero', not a test of the estimator. The economic content of PC-2 is carried entirely by its |mean| < 0.3% arm, which IS B-invariant and which every cell passes.
- **Neither the donor pool nor the TREATED set is matched between the real and placebo arms.** Real index events batch on quarterly reconstitution dates, so many donors sit inside the ±21-session exclusion simultaneously and are dropped together; placebo dates are uniform and lose far fewer. On the treated side the real statistic fits 303 events while each placebo draw fits about 348 (range 339–354) out of 357 re-datable names — a placebo date is free to land where the name's window is clean, whereas the real date is not. So the null is estimated on a slightly LARGER and easier treated set than the statistic it is judging, which if anything understates the null's dispersion. A calendar-matched placebo drawn only from dates where the real event would also have fitted removes both asymmetries and is the sharper design for the next rung.
- **PC-3 is registered as a bare point comparison and passes by a margin inside its own uncertainty.** The dispersion ratio is 0.944 (SC 0.614% vs incumbent 0.650%) with a paired-bootstrap 95% CI of [0.804, 0.975] over 200 draws and a paired variance-difference t of -3.677. The gate's PASS is real but should be read as 'SC is not noisier', not as 'SC is materially tighter'.
- **The unfitted estimator wins PC-1.** The equal-weight `matched_k` basket carries t=8.392 on the announce window against the fitted `sc_nnls`'s t=8.291. PC-1 is registered on sc_nnls alone, so this does not change the gate — but a zero-parameter basket matching or beating the fitted counterfactual is the relevant signal about how much the fitting is actually buying here.
- The placebo null is drawn uniformly over the store's sessions while the real events cluster (S&P reconstitutions batch quarterly). Market drift differences out of every arm — each is a treated-minus-counterfactual difference — but the calendar composition of the null is not matched to the real events, and a calendar-matched placebo is the sharper design the next rung should use.

## Amendments to the frozen pre-registration

*AM-1..AM-6 were recorded while wiring, before any compute. AM-7..AM-11 came out of an adversarial review of the first full run; that run was DISCARDED and re-run under these corrections, so no number below was produced under the defective forms.*

- **AM-1 announce source.** `data/sp_index_changes/changes.parquet` holds 50 rows (4 sp500 adds) and is not the store the house's +1.64% grade came from; the family is rebuilt from `sp1500_pit_membership.parquet` exactly as `scripts/validate_index_reconstitution.py` does.
- **AM-2 sector arm.** Not derivable for index adds (`data/sector_holdings` covers 236 S&P 500 names = 6.2% of in-scope adds). Phase-3 keeps its XLV arm.
- **AM-3 universe floor.** The house $5 price floor is applied to donors; the charter's donor rules named coverage, liquidity and event exclusion but no price floor.
- **AM-4 donor pre-screen.** The fitted solver receives the top-50 by pre-window correlation, not all ~4,000 eligible names. M=50 and k=20 were frozen before any result and are not tuned.
- **AM-5 instrument type.** No whole-market security-type classifier exists here, so ETFs/ADRs/preferreds clearing the liquidity floor are admissible donors.
- **AM-6 Phase-3 cells.** Multiple NCTs posted by one sponsor on one day are ONE event, matching the prior study's `ticker_date_cells` construction.
- **AM-7 window.** `CAR[0,5]` is NOT byte-identical to the incumbent's announce window: the incumbent scores a five-return price ratio, this sums six. The prereg's "spans exactly" is withdrawn; `incumbent_reconciliation` computes the incumbent's exact statistic on this sample instead.
- **AM-8 charter matching.** The charter specifies matching on path/vol/beta/sector/size/liquidity. SECTOR and SIZE are NOT matched on — no whole-market classifier exists. Correlation matching subsumes path and, for a returns fit, beta; sector exposure is recovered only implicitly.
- **AM-9 PC-1 estimand.** PC-1 requires BOTH the event-weighted and month-weighted CAAR to be positive. `monthly_nw` pairs an event-weighted mean with a month-weighted t, and with quarterly-batched reconstitutions the two can disagree in sign. Strictly stronger than the registered single-mean form.
- **AM-10 placebo band.** ASYMMETRIC `[s−20, s+125]`, not the symmetric ±42 first written. A placebo at s' fits on `[s'−125, s'−6]`, so `s' ∈ [s+42, s+125]` passed the old guard while FITTING on a window containing the real treatment — 9.6% of eligible dates, contaminating only the SC arms and therefore biasing PC-3 specifically.
- **AM-11 price floor is PIT.** The $5 floor reads the close AS PRINTED, not the back-adjusted close. `split_adjust` back-multiplies prior bars by a factor detected later in the series, which is not PIT and inverts the selection: a raw $0.60 name that later reverse-splits 1:10 reads as $6.00 and would be admitted.

## Caveats carried forward

- DIAGNOSTIC tier — this grades an estimator, not a signal. No promotion, no surface, no ranked path, no fused composite of the two estimators anywhere.
- Store starts 2021-07-06, so events are restricted to 2022-01-01→ and the sample is NOT the one the house's +1.64%/t=4.63 index grade was computed on (2019→, n=877). The positive control is directional, not a replication.
- AM-1: data/sp_index_changes/changes.parquet holds 50 rows (4 sp500 adds) and is too thin to carry the control; the graded family is rebuilt from sp1500_pit_membership.parquet exactly as scripts/validate_index_reconstitution.py does, with the announce day taken as effective − 5 sessions.
- AM-2: the sector-ETF arm is NOT derivable for index adds — data/sector_holdings covers S&P 500 constituents only (236 tickers, 6.2% of in-scope adds, which are mostly sp400/sp600). Phase-3 keeps its XLV arm.
- Donor contamination is screened against the IN-SCOPE events of the treated family only. Three classes of index event are therefore invisible to it and can sit inside a donor pool: S&P DELETIONS (negative drift, inflates tau), MIGRATION and RE-ADD cohorts (excluded from the treated set by classify_cohort but still index events), and PURE ADDS BEFORE 2022-01 (outside the study scope but inside some pre-windows). Each is a known, unremoved bias rather than an absent one; the top-50 correlation screen keeps the expected per-event contribution small.
- The contamination map is NOT point-in-time — it uses donors' future event dates to exclude them. That is correct for a retrospective diagnostic (it is donor hygiene, not a tradable rule) but it would not be available live.
- Phase-3 biases carry over from the prior study unchanged: collector truncation (pageSize=100, no pagination, sort by LastUpdatePostDate) and only 19 sponsor clusters, all mega-cap pharma and heavily time-overlapping.
- Prices are split-repaired but NOT dividend-adjusted (price return, not total return). The whisker applies to treated and donors alike and very largely differences out of tau.
- AM-5: no security-type classifier exists here, so ETFs/ADRs/preferreds clearing the liquidity floor are admissible donors.
- Missing donor prints inside the fitting window are filled with a zero return (for a buy-and-hold donor a non-trading day IS a zero return); the ≥90% coverage rule caps this at 12 of 120 sessions.
- Placebo dates are drawn per name outside the ASYMMETRIC exclusion band [s−20, s+125] sessions around the real event s — asymmetric because a placebo at s' scores forward over [s', s'+20] but FITS backward over [s'−125, s'−6], so the two windows sit on opposite sides of the event day (AM-10). An earlier symmetric ±42 guard let 9.6% of eligible dates fit on a window containing the real treatment. The real events' donor-contamination map is applied to placebo draws too, which is conservative.
- Placebo draws are the only stochastic element and are seeded; every other number here is deterministic given the store.
- Cohort labelling inherits an incumbent defect: `classify_cohort` calls an add "pure" whenever it finds no prior PIT membership row, which also catches ticker RENAMES and SPIN-OFFS — entities already inside the S&P universe under another symbol, which therefore DO have an offsetting forced seller. Reproducing the incumbent's construction faithfully was the point of the positive control, so this is disclosed and deliberately not fixed here.
- Events whose treated name has a hole in its own fitting window produce no estimate and are absent from every reported number; the dominant cause is symbol discontinuity in a store keyed by CURRENT ticker, so the headline is a survivor statistic. Counts and reasons are in `drop_reasons`.
- Monthly clustering keys on the EVENT day (effective − 5 sessions) while the incumbent keys on the effective date, so a handful of events fall in a different month than they would there; the estimator is the same, the month partition is not identical.
- Empirical p carries the (1+k)/(B+1) permutation correction, so its floor is 1/(B+1) and it can never print 0. The null it tests is 'effect equals the placebo mean', not 'effect equals zero'.

---
*Results JSON: `data/experiments/synthetic_control_phase0_results.json` · trial ledger family `synthetic_control_phase0` · runtime 6683s · seed 20260806 (placebo draws are the only stochastic element).*
