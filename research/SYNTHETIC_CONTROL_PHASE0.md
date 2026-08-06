# Synthetic control for event studies — Phase-0 (wave-2a)

*Run 2026-08-06 · charter `research/ADVANCED_QUANT_METHODS_ADJUDICATION_BY_FABLE.md` §3#5 · frozen pre-registration in `scripts/synthetic_control_phase0.py`*

**DIAGNOSTIC TIER.** This grades an *estimator*, not a signal. No event family here is being scored for tradability; two families whose answers the house already established are used as instruments to measure whether donor-pool synthetic control tells the truth on this panel. Nothing here promotes anything or gates any surface.

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
- Scope 2022-01-01 → panel end; construction diagnostics: `{"raw_adds_all_time": 3286, "cohort_counts": {"pure": 2727, "migration": 503, "readd": 56}, "pure_all_time": 2727, "pure_in_scope_date": 366, "events_usable": 361}`

- Placebo null runs on 357 events (4 had no eligible placebo date and were dropped rather than left at their real session)

| Arm | Window | CAAR (event-wtd) | CAAR (month-wtd) | monthly-NW t | ticker-cluster t | hit rate | placebo mean | placebo SD | empirical p |
|---|---|---|---|---|---|---|---|---|---|
| `matched_k` | [0] | 0.236% | 0.063% | 0.449 | 1.919 | 0.568 | 0.006% | 0.129% | 0.085 |
| `matched_k` | [0,5] | 2.890% | 5.047% | 8.392 | 7.621 | 0.7 | 0.190% | 0.624% | 0.01 |
| `matched_k` | [0,20] | 2.179% | 4.560% | 4.67 | 3.366 | 0.614 | 0.789% | 1.345% | 0.08 |
| `sc_nnls` | [0] | 0.259% | 0.093% | 0.624 | 2.069 | 0.584 | 0.015% | 0.118% | 0.07 |
| `sc_nnls` | [0,5] | 3.015% | 4.907% | 8.291 | 8.354 | 0.696 | 0.197% | 0.614% | 0.01 |
| `sc_nnls` | [0,20] | 2.205% | 4.240% | 4.175 | 3.514 | 0.627 | 0.818% | 1.332% | 0.045 |
| `SPY` | [0] | -0.044% | -0.122% | -0.676 | -0.314 | 0.528 | -0.001% | 0.148% | 0.781 |
| `SPY` | [0,5] | 2.852% | 5.184% | 7.877 | 6.739 | 0.693 | 0.142% | 0.650% | 0.01 |
| `SPY` | [0,20] | 2.342% | 4.409% | 4.812 | 3.247 | 0.614 | 0.685% | 1.399% | 0.07 |

**Reconciliation against the incumbent's exact statistic.** `validate_index_reconstitution.py` scores a SPY-relative PRICE RATIO over [-5,0] — five daily returns, where this study's CAR[0,5] sums six (AM-7). Recomputing the incumbent's own construction on THIS sample gives 2.895% (t=7.183, n=309, 52 months) against the house's 2019→ grade of 1.640% (t=4.63, n=877). The gap is the sample, not the estimator.

## Falsifier — ClinicalTrials Phase-3 starts

- Event day rule: StudyFirstPostDate (first public availability)
- 740 of 744 in-scope events fitted (mean eligible donor pool 4,014 names)
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

- **PC-2 cannot separate an estimator bias from a cohort drift.** It asks whether the SC arms are centred at random dates on these names — but a cohort that genuinely drifts fails it however good the estimator is. The incumbent SPY-CAR arm, which is NOT under test, reads 0.142% on the same draws against the fitted SC's 0.197% and the equal-weight basket's 0.190%, i.e. all three arms are offset the same way. The comparison ACROSS arms is the discriminating statistic and it lives in the table above, not in the gate. Read a PC-2 failure as 'this cohort drifts', not as 'synthetic control invents effects'.
- **PC-1 and PC-3 are the gates that can actually separate the arms**, because both are comparisons: PC-1 against a number the house already graded, PC-3 against the incumbent's own placebo dispersion on identical draws. PC-2 and F-1 are absolute thresholds and inherit whatever the cohort does.
- **PC-2's |t|<2 arm is controlled by the DRAW COUNT, not by the estimator.** That t is the Monte-Carlo standard error of the placebo mean (mean / (sd/sqrt(B))), so for any non-zero cohort drift it grows without bound as B rises — the same estimator passes at B=50 and fails at B=1000. B is frozen at 200 here and the reading is only interpretable at that B. The economic content of PC-2 is carried by its |mean| < 0.3% arm, which is B-invariant.
- **Donor attrition is not symmetric between the real and placebo arms.** Real index events batch on quarterly reconstitution dates, so many donors are simultaneously inside the ±21-session exclusion and are dropped together; placebo dates are uniform and lose far fewer. The real arm therefore fits a systematically smaller — and differently composed — donor pool than the null does. A calendar-matched placebo would remove this and is the sharper design for the next rung.
- The placebo null is drawn uniformly over the store's sessions while the real events cluster (S&P reconstitutions batch quarterly). Market drift differences out of every arm — each is a treated-minus-counterfactual difference — but the calendar composition of the null is not matched to the real events, and a calendar-matched placebo is the sharper design the next rung should use.

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
- Placebo dates are drawn per name with a ±42-session guard around the real event; the real events' donor-contamination map is applied to placebo draws too, which is conservative.
- Placebo draws are the only stochastic element and are seeded; every other number here is deterministic given the store.
- Monthly clustering keys on the EVENT day (effective − 5 sessions) while the incumbent keys on the effective date, so a handful of events fall in a different month than they would there; the estimator is the same, the month partition is not identical.
- Empirical p carries the (1+k)/(B+1) permutation correction, so its floor is 1/(B+1) and it can never print 0. The null it tests is 'effect equals the placebo mean', not 'effect equals zero'.

---
*Results JSON: `data/experiments/synthetic_control_phase0_results.json` · trial ledger family `synthetic_control_phase0` · runtime 5646s · seed 20260806 (placebo draws are the only stochastic element).*
