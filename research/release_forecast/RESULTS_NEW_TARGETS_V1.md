# MRI Track N — Walk-Forward Backtest Results V1

**Generated:** 2026-07-08
**Spec:** research/release_forecast/PREREG_NEW_TARGETS_V1.md (frozen before results)
**Ruling:** MRI-R23 (§11.1 of masterplan)

Anti-mining: spec frozen in PREREG_NEW_TARGETS_V1.md BEFORE this backtest was run.
No model or feature changes may be made after observing these results.

---

## Summary Table

| Target | n_predictions | Full MAE model | Full MAE naive | 2021+ MAE model | 2021+ MAE naive | Kill rule | VERDICT |
|---|---|---|---|---|---|---|---|
| pce_headline | 250 | 0.3151 | 0.4257 | 0.2811 | 0.3514 | PASS | **MODEL** |
| pce_core | 250 | 0.2682 | 0.3386 | 0.3097 | 0.3685 | PASS | **MODEL** |
| ppi_finaldemand | 87 | 0.3260 | 0.4646 | 0.3377 | 0.4696 | PASS | **MODEL** |
| retail_sales | 0 | null | null | null | null | NOT_APPLICABLE | **SCAFFOLD_ONLY_NO_DATA** |

Kill rule: KILLED = model MAE >= naive MAE in BOTH full AND 2021+ -> BENCHMARK_ONLY.
COVID months (2020-03..06) excluded from era stats.

---

## pce_headline

**Verdict: MODEL** (kill rule: PASS)

Full window: MAE model=0.3151 vs naive=0.4257 vs trailing3m=0.4135 vs AR3=0.3351 (n=250)
2021+ era: MAE model=0.2811 vs naive=0.3514 vs trailing3m=0.3019 vs AR3=0.3625 (n=65)

### Era Breakdown

| Era | n | MAE model | MAE naive | MAE t3m | MAE AR3 | RMSE model | RMSE naive | Coverage p10-p90 | Skew HR | Skew CI | Skew n |
|---|---|---|---|---|---|---|---|---|---|---|---|
| full | 250 | 0.3151 | 0.4257 | 0.4135 | 0.3351 | 1.0824 | 1.3906 | 0.7876 | 0.7527 | [0.686,0.809] | 186 |
| pre 2010 | 53 | 0.3981 | 0.6591 | 0.6618 | 0.4771 | 1.4976 | 2.0118 | 0.5862 | 0.8400 | [0.715,0.917] | 50 |
| 2010 2020 | 122 | 0.3091 | 0.3779 | 0.3698 | 0.2651 | 1.0700 | 1.2992 | 0.8197 | 0.7869 | [0.669,0.871] | 61 |
| covid months 2020 03 06 | 4 | 0.1884 | 0.3977 | 0.4571 | 0.3329 | 0.2066 | 0.4181 | 0.5000 | 1.0000 | [0.510,1.000] | 4 |
| 2020 recovery | 6 | 0.1586 | 0.1582 | 0.2887 | 0.2096 | 0.2066 | 0.2356 | 0.8333 | 0.5000 | [0.188,0.812] | 6 |
| 2021 plus | 65 | 0.2811 | 0.3514 | 0.3019 | 0.3625 | 0.7227 | 0.9765 | 0.8308 | 0.6615 | [0.540,0.765] | 65 |

Full p10-p90 coverage: 78.8% (target: ~80%)
2021+ p10-p90 coverage: 83.1% (target: ~80%)

Full skew hit-rate: 75.3% (Wilson 95%: [0.686,0.809], n=186)

---

## pce_core

**Verdict: MODEL** (kill rule: PASS)

Full window: MAE model=0.2682 vs naive=0.3386 vs trailing3m=0.3278 vs AR3=0.2729 (n=250)
2021+ era: MAE model=0.3097 vs naive=0.3685 vs trailing3m=0.3522 vs AR3=0.3712 (n=65)

### Era Breakdown

| Era | n | MAE model | MAE naive | MAE t3m | MAE AR3 | RMSE model | RMSE naive | Coverage p10-p90 | Skew HR | Skew CI | Skew n |
|---|---|---|---|---|---|---|---|---|---|---|---|
| full | 250 | 0.2682 | 0.3386 | 0.3278 | 0.2729 | 0.9706 | 1.2983 | 0.7434 | 0.6129 | [0.541,0.680] | 186 |
| pre 2010 | 53 | 0.3017 | 0.4451 | 0.4255 | 0.3017 | 1.1865 | 1.6734 | 0.6207 | 0.5800 | [0.442,0.706] | 50 |
| 2010 2020 | 122 | 0.2349 | 0.2854 | 0.2732 | 0.2128 | 0.9268 | 1.1658 | 0.8361 | 0.5902 | [0.465,0.705] | 61 |
| covid months 2020 03 06 | 4 | 0.3008 | 0.3538 | 0.3470 | 0.2347 | 0.3606 | 0.3636 | 0.2500 | 0.5000 | [0.150,0.850] | 4 |
| 2020 recovery | 6 | 0.1783 | 0.1461 | 0.2961 | 0.2035 | 0.2427 | 0.2176 | 0.5000 | 0.5000 | [0.188,0.812] | 6 |
| 2021 plus | 65 | 0.3097 | 0.3685 | 0.3522 | 0.3712 | 0.9218 | 1.2790 | 0.6769 | 0.6769 | [0.556,0.778] | 65 |

Full p10-p90 coverage: 74.3% (target: ~80%)
2021+ p10-p90 coverage: 67.7% (target: ~80%)

Full skew hit-rate: 61.3% (Wilson 95%: [0.541,0.680], n=186)

---

## ppi_finaldemand

**Verdict: MODEL** (kill rule: PASS)

**THIN-HISTORY CAVEAT:** PPIFIS vintage history starts 2014-02. After the 60-observation burn-in, the first walk-forward prediction is approximately 2019-02, yielding approximately 90 total predictions and approximately 50-60 in the 2021+ era. Statistics are informative but thin-history confidence is reduced. Kill rule applied as written.

Full window: MAE model=0.3260 vs naive=0.4646 vs trailing3m=0.3625 vs AR3=0.3720 (n=87)
2021+ era: MAE model=0.3377 vs naive=0.4696 vs trailing3m=0.3695 vs AR3=0.3930 (n=65)

### Era Breakdown

| Era | n | MAE model | MAE naive | MAE t3m | MAE AR3 | RMSE model | RMSE naive | Coverage p10-p90 | Skew HR | Skew CI | Skew n |
|---|---|---|---|---|---|---|---|---|---|---|---|
| full | 87 | 0.3260 | 0.4646 | 0.3625 | 0.3720 | 0.4029 | 0.6109 | 0.7619 | 0.7500 | [0.648,0.830] | 84 |
| pre 2010 | 0 | null | null | null | null | null | null | null | null | null | 0 |
| 2010 2020 | 12 | 0.2660 | 0.3662 | 0.2749 | 0.2786 | 0.3115 | 0.4810 | null | 0.7778 | [0.453,0.937] | 9 |
| covid months 2020 03 06 | 4 | 0.5196 | 0.9515 | 0.6546 | 0.5350 | 0.5873 | 1.0727 | null | 1.0000 | [0.510,1.000] | 4 |
| 2020 recovery | 6 | 0.1906 | 0.2830 | 0.2678 | 0.2232 | 0.2212 | 0.3642 | null | 0.8333 | [0.436,0.970] | 6 |
| 2021 plus | 65 | 0.3377 | 0.4696 | 0.3695 | 0.3930 | 0.4167 | 0.6114 | 0.7619 | 0.7231 | [0.604,0.817] | 65 |

Full p10-p90 coverage: 76.2% (target: ~80%)
2021+ p10-p90 coverage: 76.2% (target: ~80%)

Full skew hit-rate: 75.0% (Wilson 95%: [0.648,0.830], n=84)

_Thin-history caveat: PPIFIS vintage history starts 2014-02; first walk-forward prediction approximately 2019-02; expect ~90 total and ~50-60 2021+ predictions._

---

## retail_sales

**Verdict: SCAFFOLD_ONLY_NO_DATA** (kill rule: NOT_APPLICABLE)

SCAFFOLD-ONLY. RSAFS data is absent from disk as of 2026-07-08. No backtest was run. The attempt clock (#1 of 2) has not started. Projection emits `no_data_rsafs_absent`. Machinery ships so that when data accrues the model can be specified and run.

## Notes

- All outputs are display_only=True, authority=False.
- Nulls are printed, not hidden (MRI-R19).
- sticky/median/flex CPI sourced from ALFRED first-prints (PIT fix 2026-07-08); GASREGW declared unrevised in provenance.
- PPI thin history: kill rule applied as written; no relaxation for thin history.
- Round 2 will wire surviving targets into engine/release_forecast.py dispatch.

