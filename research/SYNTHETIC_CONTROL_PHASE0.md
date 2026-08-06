# Synthetic control for event studies — Phase-0 (wave-2a)

*Run 2026-08-06 · charter `research/ADVANCED_QUANT_METHODS_ADJUDICATION_BY_FABLE.md` §3#5 · frozen pre-registration in `scripts/synthetic_control_phase0.py`*

**DIAGNOSTIC TIER.** This grades an *estimator*, not a signal. No event family here is being scored for tradability; two families whose answers the house already established are used as instruments to measure whether donor-pool synthetic control tells the truth on this panel. Nothing here promotes anything or gates any surface.

## Verdict: `MIXED`

Failing gate(s): **PC2_estimators_unbiased, PC3_sc_not_noisier, F1_falsifier_holds**

| Gate | Result | Reading |
|---|---|---|
| PC-1 positive control survives | **PASS** | sc_nnls S&P pure-add CAAR[0,5]=2.971% monthly-NW t=2.726 (need >0 and t>2) |
| PC-2 estimators unbiased | **FAIL** | sp_pure_adds/matched_k mean=0.671% t=1.871 FAIL; sp_pure_adds/sc_nnls mean=0.525% t=1.416 FAIL; phase3_start/matched_k mean=0.171% t=1.487; phase3_start/sc_nnls mean=0.148% t=2.181 FAIL (need |mean|<0.3% and |t|<2) |
| PC-3 SC not noisier | **FAIL** | sc_nnls placebo SD=0.742% vs SPY-CAR placebo SD=0.711% (need SC <= incumbent) |
| F-1 falsifier holds | **FAIL** | phase3 sc_nnls CAAR[0,20]=0.424% monthly-NW t=1.996 empirical p=0.0 (need |t|<2 and p>0.05) |

## Panel

- Store: `/Users/chriswong/Documents/Cluade/Macro Dashboard/data/massive_stock_day` — 3,002 parquet files, 2,217 names kept after the removal-only prefilter
- Calendar: 2021-07-06 → 2026-07-02 (1,254 sessions)
- Split repairs applied to 337 names (`scripts.replay_standout_pipeline.split_adjust`, close-only, factor carried onto volume)
- Pre-window 120 sessions ending t−6; donor exclusion ±21 sessions; coverage ≥90%; 20d median dollar volume ≥ $2,000,000; close > $5

## Positive control — S&P pure adds

- Event day rule: effective_date - 5 sessions (announce proxy)
- 61 of 66 in-scope events fitted (mean eligible donor pool 556 names)
- Scope 2022-01-01 → panel end; construction diagnostics: `{"raw_adds_all_time": 3286, "cohort_counts": {"pure": 2727, "migration": 503, "readd": 56}, "pure_all_time": 2727, "pure_in_scope_date": 366, "events_usable": 66}`

| Arm | Window | CAAR | monthly-NW t | ticker-cluster t | hit rate | placebo mean | placebo SD | empirical p |
|---|---|---|---|---|---|---|---|---|
| `matched_k` | [0] | 0.256% | 1.344 | 0.991 | 0.59 | -0.079% | 0.194% | 0.0 |
| `matched_k` | [0,5] | 2.965% | 3.026 | 3.655 | 0.754 | 0.671% | 0.717% | 0.0 |
| `matched_k` | [0,20] | 0.780% | 0.86 | 0.549 | 0.557 | 1.868% | 0.844% | 0.25 |
| `sc_nnls` | [0] | 0.357% | 1.906 | 1.509 | 0.541 | -0.152% | 0.172% | 0.0 |
| `sc_nnls` | [0,5] | 2.971% | 2.726 | 3.969 | 0.705 | 0.525% | 0.742% | 0.0 |
| `sc_nnls` | [0,20] | 1.536% | 1.114 | 1.129 | 0.623 | 1.627% | 0.953% | 0.75 |
| `SPY` | [0] | 0.131% | 1.147 | 0.463 | 0.59 | -0.100% | 0.367% | 0.5 |
| `SPY` | [0,5] | 2.498% | 2.741 | 2.632 | 0.689 | 0.581% | 0.711% | 0.0 |
| `SPY` | [0,20] | 1.089% | 1.186 | 0.712 | 0.525 | 1.123% | 0.949% | 1.0 |

## Falsifier — ClinicalTrials Phase-3 starts

- Event day rule: StudyFirstPostDate (first public availability)
- 263 of 264 in-scope events fitted (mean eligible donor pool 551 names)
- Scope 2022-01-01 → panel end; construction diagnostics: `{"raw_rows": 1656, "uniq_nct": 1593, "phase3_rows": 1656, "ticker_date_cells_all_time": 1461, "cells_in_scope_date": 831, "sponsors": 19, "events_usable": 264}`

| Arm | Window | CAAR | monthly-NW t | ticker-cluster t | hit rate | placebo mean | placebo SD | empirical p |
|---|---|---|---|---|---|---|---|---|
| `matched_k` | [0] | 0.016% | 0.397 | 0.252 | 0.51 | 0.025% | 0.051% | 1.0 |
| `matched_k` | [0,5] | 0.416% | 2.357 | 1.908 | 0.54 | 0.171% | 0.229% | 0.25 |
| `matched_k` | [0,20] | 0.686% | 2.812 | 1.85 | 0.525 | 0.207% | 0.351% | 0.25 |
| `sc_nnls` | [0] | -0.025% | -0.257 | -0.467 | 0.494 | 0.024% | 0.058% | 0.5 |
| `sc_nnls` | [0,5] | 0.341% | 1.694 | 1.492 | 0.532 | 0.148% | 0.135% | 0.25 |
| `sc_nnls` | [0,20] | 0.424% | 1.996 | 0.992 | 0.49 | -0.054% | 0.371% | 0.0 |
| `SPY` | [0] | -0.105% | -0.961 | -1.53 | 0.487 | -0.046% | 0.079% | 0.25 |
| `SPY` | [0,5] | 0.085% | 1.311 | 0.389 | 0.487 | -0.103% | 0.264% | 0.5 |
| `SPY` | [0,20] | -0.259% | 0.558 | -0.54 | 0.471 | -0.614% | 0.449% | 0.5 |
| `XLV` | [0] | 0.016% | 0.453 | 0.239 | 0.551 | 0.025% | 0.043% | 0.75 |
| `XLV` | [0,5] | 0.401% | 1.811 | 2.022 | 0.54 | 0.174% | 0.138% | 0.0 |
| `XLV` | [0,20] | 0.622% | 1.87 | 1.381 | 0.525 | 0.291% | 0.409% | 0.25 |

## What the numbers mean

**Positive control.** Over the announce window the incumbent SPY-adjusted CAR reads 2.498% (t=2.741), the equal-weight donor basket 2.965% (t=3.026), and the fitted synthetic control 2.971% (t=2.726). The house's graded number for this family is +1.64% at t=4.63 on the full 2019→ sample; this run is restricted to 2022-01-01→ by the store's 2021-07 start, so the samples differ — the comparison is directional, not a replication.

**Power.** Under the null the fitted SC's aggregate estimate has placebo dispersion 0.742%, the equal-weight basket 0.717%, the incumbent 0.711% (1.04× the incumbent). A counterfactual that is not tighter than SPY under the null has bought nothing, whatever it does to the point estimate — that is what PC-3 grades.

**Centring.** At random dates on the same names the arms read 0.525% (fitted SC), 0.671% (equal-weight) and 0.581% (incumbent SPY-CAR). Every arm is offset in the same direction and the fitted SC is the LEAST offset, so the offset is a property of the COHORT rather than of the estimator: names that were being added to an S&P index drifted up against any counterfactual over this window, and SC removes more of that drift than the incumbent does. This matters for how the announce effect itself should be read — part of what a benchmark-adjusted CAR attributes to the announcement is cohort drift that a random date reproduces. The harness itself manufactures nothing: on a synthetic no-effect panel the same code path returns zero within sampling error (tests/test_synthetic_control.py::test_placebo_machinery_returns_zero_on_a_no_effect_panel), so this offset is in the data, not in the estimator's arithmetic.

**Falsifier.** On Phase-3 starts the fitted SC reads 0.424% over [0,20] with monthly-NW t=1.996 and empirical p=0.0 against its own random-date placebo; day 0 is -0.025% (t=-0.257). The house verdict on record for this family is NULL — placebo-explained — and F-1 asks only that SC not overturn it.

**Pre-registered verdict: `MIXED`** — failing PC2_estimators_unbiased, PC3_sc_not_noisier, F1_falsifier_holds. A failed gate is a result: it says where this estimator may and may not be trusted, and nothing here promotes it into any scored path.

## Gate honesty — what these gates can and cannot discriminate

*Written after running them, deliberately kept out of the frozen pre-registration so the gates were not retro-fitted to the answer.*

- **PC-2 cannot separate an estimator bias from a cohort drift.** It asks whether the SC arms are centred at random dates on these names — but a cohort that genuinely drifts fails it however good the estimator is. The incumbent SPY-CAR arm, which is NOT under test, reads 0.581% on the same draws against the fitted SC's 0.525% and the equal-weight basket's 0.671%, i.e. all three arms are offset the same way. The comparison ACROSS arms is the discriminating statistic and it lives in the table above, not in the gate. Read a PC-2 failure as 'this cohort drifts', not as 'synthetic control invents effects'.
- **The [0,20] window carries no event signal at all for the index family.** The random-date placebo mean (1.627%) EXCEEDS the realized CAAR (1.536%), so whatever the 21-day post-announcement window measures, a date drawn at random on the same names reproduces more of it. Any 'post-announcement drift' read off that window would be cohort drift. This is a statement about the window and the cohort, not about the estimator — every arm shows it.
- **PC-1 and PC-3 are the gates that can actually separate the arms**, because both are comparisons: PC-1 against a number the house already graded, PC-3 against the incumbent's own placebo dispersion on identical draws. PC-2 and F-1 are absolute thresholds and inherit whatever the cohort does.
- The placebo null is drawn uniformly over the store's sessions while the real events cluster (S&P reconstitutions batch quarterly). Market drift differences out of every arm — each is a treated-minus-counterfactual difference — but the calendar composition of the null is not matched to the real events, and a calendar-matched placebo is the sharper design the next rung should use.

## Caveats carried forward

- DIAGNOSTIC tier — this grades an estimator, not a signal. No promotion, no surface, no ranked path, no fused composite of the two estimators anywhere.
- Store starts 2021-07-06, so events are restricted to 2022-01-01→ and the sample is NOT the one the house's +1.64%/t=4.63 index grade was computed on (2019→, n=877). The positive control is directional, not a replication.
- AM-1: data/sp_index_changes/changes.parquet holds 50 rows (4 sp500 adds) and is too thin to carry the control; the graded family is rebuilt from sp1500_pit_membership.parquet exactly as scripts/validate_index_reconstitution.py does, with the announce day taken as effective − 5 sessions.
- AM-2: the sector-ETF arm is NOT derivable for index adds — data/sector_holdings covers S&P 500 constituents only (236 tickers, 6.2% of in-scope adds, which are mostly sp400/sp600). Phase-3 keeps its XLV arm.
- Donor contamination is screened against the treated family's OWN events only. S&P DELETIONS are not in the index event list, so a donor being deleted (a negative-drift name) can enter a pool and inflate tau. With ~25 deletions a year against a donor pool in the thousands and a top-50 correlation screen, the expected contribution is small — but it is a known, unremoved bias, not an absent one.
- Phase-3 biases carry over from the prior study unchanged: collector truncation (pageSize=100, no pagination, sort by LastUpdatePostDate) and only 19 sponsor clusters, all mega-cap pharma and heavily time-overlapping.
- Prices are split-repaired but NOT dividend-adjusted (price return, not total return). The whisker applies to treated and donors alike and very largely differences out of tau.
- AM-5: no security-type classifier exists here, so ETFs/ADRs/preferreds clearing the liquidity floor are admissible donors.
- Missing donor prints inside the fitting window are filled with a zero return (for a buy-and-hold donor a non-trading day IS a zero return); the ≥90% coverage rule caps this at 12 of 120 sessions.
- Placebo dates are drawn per name with a ±42-session guard around the real event; the real events' donor-contamination map is applied to placebo draws too, which is conservative.
- Placebo draws are the only stochastic element and are seeded; every other number here is deterministic given the store.

---
*Results JSON: `data/experiments/synthetic_control_phase0_results.json` · trial ledger family `synthetic_control_phase0` · runtime 22s · seed 20260806 (placebo draws are the only stochastic element).*
