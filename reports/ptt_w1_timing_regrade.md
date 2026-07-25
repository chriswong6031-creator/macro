# PTT-W1-T — the §7 re-grade: bottom-picking ruler (MAE primary, within-5%-of-low co-primary)

Pre-registered ruler: script header, committed pre-run (charter §7, PR #3430; DNR §3 wrong-ruler law #1458). Panel + fixed arms FROZEN from W1 (1300 names, consistency gate PASSED, head-trims: 0). TEST signals: 109,974. U_MAE = median signal MAE63 − all-days median MAE63 (pp, positive = shallower adverse); U_W5 = signal within-5%-of-low rate − all-days rate (pp). Random-day nulls are per-name per-half per-metric (§7 base-rate guard). Panel all-days OOS base rates (median across names): MAE -8.16%, w5 16.3%, called-low 8.4%.

## A. R1 — fixed W1 arms re-graded (ruler swap on grading alone)

| arm (tools verbatim from W1) | U_MAE OOS | CI | U_W5 OOS | CI | U_MAE 2021+ | U_W5 2021+ |
|---|---|---|---|---|---|---|
| (a) W1a fwd63-audition tools | -0.09pp | [-1.46, +0.84] | -8.97pp | [-10.89, -9.66] | -0.07pp | -9.23pp |
| (a′) W1b-pure structure | +0.22pp | [-0.96, +1.29] | -0.25pp | [-3.47, +0.63] | +0.36pp | -0.44pp |
| (a″) W1b-hybrid | +0.13pp | [-1.15, +1.11] | -7.55pp | [-9.11, -8.01] | +0.27pp | -7.61pp |
| (b) global one-size (S2W) | -0.21pp | [-2.01, +1.41] | -9.66pp | [-12.12, -10.34] | +0.04pp | -9.91pp |
| (c) class (≡ global, degenerate) | -0.21pp | [-2.01, +1.41] | -9.66pp | [-12.12, -10.34] | +0.04pp | -9.91pp |
| (d) random floor | -0.20pp | [-1.52, +0.68] | -6.12pp | [-7.26, -5.68] | -0.09pp | -6.41pp |

## B. R2/R3 — timing-native re-selection (the decisive re-test)

Global-T tool (FIT U_MAE best): **M1W**. W1a_T FIT selections: M2W 360, S2W 224, M1W 216, M3D 169, S1W 167, S3D 164. Class-T cells: v0xt0→M1W, v0xt1→M3D, v0xt2→M2W, v1xt0→M1W, v1xt1→S3D, v1xt2→S3D, v2xt0→M1W, v2xt1→M1W, v2xt2→S2W.

| arm | U_MAE OOS | CI | U_W5 OOS | CI |
|---|---|---|---|---|
| (aT) W1a_T timing-audition | -0.11pp | [-1.42, +0.87] | -8.74pp | [-10.61, -9.31] |
| (a′) W1b-pure (unchanged) | +0.22pp | [-0.96, +1.29] | -0.25pp | [-3.47, +0.63] |
| (a″T) W1b-hybrid_T | +0.02pp | [-1.29, +1.01] | -8.27pp | [-9.68, -8.59] |
| (bT) global_T | -0.20pp | [-1.54, +0.98] | -13.09pp | [-14.38, -13.38] |
| (cT) class_T | -0.16pp | [-1.39, +0.79] | -8.90pp | [-10.21, -9.32] |

### Decision block (U_MAE primary; U_W5 co-primary in parens)

| comparison | U_MAE point | CI | reads | U_W5 point (CI) |
|---|---|---|---|---|
| w1a − random | +0.11pp | [-0.12, +0.42] | includes 0 | -2.85pp [-4.55, -3.18] |
| w1b_pure − random | +0.41pp | [+0.13, +1.16] | excludes 0 ↑ | +5.87pp [+3.51, +6.43] |
| global − random | -0.01pp | [-0.58, +0.91] | includes 0 | -3.54pp [-5.68, -3.87] |
| class − random | -0.01pp | [-0.58, +0.91] | includes 0 | -3.54pp [-5.68, -3.87] |
| w1b_hyb − random | +0.33pp | [+0.15, +0.74] | excludes 0 ↑ | -1.42pp [-2.78, -1.45] |
| w1a − global | +0.12pp | [-0.74, +0.76] | includes 0 | +0.68pp [+0.34, +1.44] |
| w1b_pure − w1a | +0.30pp | [-0.08, +1.03] | includes 0 | +8.72pp [+7.17, +10.88] |
| w1b_pure − global | +0.42pp | [-0.53, +1.51] | includes 0 | +9.40pp [+7.95, +11.79] |
| w1a_T − random | +0.08pp | [-0.12, +0.47] | includes 0 | -2.62pp [-4.25, -2.91] |
| global_T − random | -0.01pp | [-0.40, +0.73] | includes 0 | -6.97pp [-8.27, -6.68] |
| class_T − random | +0.04pp | [-0.20, +0.49] | includes 0 | -2.78pp [-4.03, -2.69] |
| w1b_hyb_T − random | +0.21pp | [+0.04, +0.66] | excludes 0 ↑ | -2.15pp [-3.26, -1.95] |
| w1a_T − global_T | +0.09pp | [-0.58, +0.63] | includes 0 | +4.35pp [+3.22, +4.53] |
| w1a_T − class_T | +0.04pp | [-0.36, +0.41] | includes 0 | +0.16pp [-0.65, +0.28] |
| class_T − global_T | +0.04pp | [-0.60, +0.51] | includes 0 | +4.19pp [+3.63, +4.59] |
| w1b_pure − w1a_T | +0.33pp | [-0.10, +0.98] | includes 0 | +8.49pp [+6.86, +10.47] |
| w1b_pure − global_T | +0.42pp | [-0.43, +1.39] | includes 0 | +12.84pp [+10.47, +14.49] |
| w1b_hyb_T − w1a_T | +0.13pp | [-0.16, +0.51] | includes 0 | +0.48pp [+0.48, +1.39] |

## C. Persistence under the timing ruler

- Per-name Spearman(FIT U_MAE tool ranks, TEST U_MAE tool ranks): median **+0.029**; 51% positive (n=1300; 6-rank granularity — read with top-2).
- FIT-best (by U_MAE) lands in TEST top-2: **35.0%** (chance = 33.3%).

## D. R5 — calls the low vs confirms the reset (descriptive)

| arm tool set | called low (−2..+5td) | confirmed reset (<−2td) | early (>+5td) | median td_to_trough |
|---|---|---|---|---|
| w1b_pure | 8% | 48% | 44% | -2td |
| w1a_T | 5% | 57% | 37% | -5td |
| global | 3% | 66% | 31% | -10td |

Panel all-days called-low base rate (median name): 8.4% — the §7 base-rate trap quantified.

## E. §2d ladder re-graded (S family, full-sample, U_MAE / U_W5)

| vol tercile | 3D | 1W | 2W | 1M | best rung (U_MAE) |
|---|---|---|---|---|---|
| low-vol (n=544) | +0.10 | +0.08 | -0.06 | -0.77 | **3D** |
| mid-vol (n=543) | +0.01 | +0.13 | -0.37 | -0.85 | **1W** |
| high-vol (n=544) | +0.00 | -0.21 | -0.29 | -1.01 | **3D** |

| name | 3D U_MAE (n) | 1W U_MAE (n) | 2W U_MAE (n) | 1M U_MAE (n) | best rung | W1 §2d best (fwd63) |
|---|---|---|---|---|---|---|
| MCD | +0.18 (52) | -0.03 (37) | +0.41 (14) | -0.03 (7) | **2W** | 1W |
| JNJ | +0.56 (62) | +0.42 (34) | +2.32 (13) | +2.73 (6) | **1M** | 1W |
| KO | +0.30 (55) | -0.79 (41) | +0.04 (18) | +1.24 (5) | **1M** | 2W |
| PG | -0.36 (60) | -0.47 (33) | -2.63 (20) | +1.94 (5) | **1M** | 3D |
| PEP | +0.48 (56) | +0.85 (33) | -0.46 (17) | +2.00 (5) | **1M** | 1W |
| WMT | -0.18 (64) | -1.22 (34) | -0.63 (14) | -0.35 (4) | **3D** | 3D |
| COST | +0.23 (54) | +0.33 (35) | -0.41 (20) | +2.83 (8) | **1M** | 1W |

## F. MWR S1-A basket census re-graded (13-signal estate)

Basket all-days nulls: median MAE63 -3.85%, w5 base 14.7%, called-low base 6.8%.

| signal | MAE63 | prox to low | td_to_trough | within 5% | mfe21 | rc21 | label |
|---|---|---|---|---|---|---|---|
| 2016-02-26 | -0.48% | +12.14% | -12td | — | +10.21% | +10.21% | confirmed reset |
| 2018-05-04 | +0.74% | +10.99% | -24td | — | +7.08% | +7.08% | confirmed reset |
| 2019-01-11 | -3.63% | +13.44% | -12td | — | +5.90% | +4.28% | confirmed reset |
| 2020-05-01 | +2.66% | +36.37% | -31td | — | +14.50% | +14.50% | confirmed reset |
| 2021-04-16 | -8.99% | +21.25% | -28td | — | -0.22% | -6.61% | confirmed reset |
| 2021-06-25 | +1.66% | +14.69% | -31td | — | +6.87% | +5.41% | confirmed reset |
| 2022-03-18 | -27.21% | +15.52% | +27td | — | +8.63% | -1.81% | early |
| 2022-06-24 | -8.18% | +10.44% | -5td | — | +5.27% | -2.20% | confirmed reset |
| 2022-11-11 | -15.61% | +18.50% | +31td | — | +1.88% | -1.34% | early |
| 2023-01-20 | +2.58% | +15.96% | -15td | — | +20.75% | +12.55% | confirmed reset |
| 2024-09-13 | -0.69% | +11.00% | -26td | — | +4.95% | +4.35% | confirmed reset |
| 2025-04-25 | -0.64% | +15.09% | -12td | — | +13.58% | +13.58% | confirmed reset |
| 2026-04-10 | +0.88% | +10.34% | -8td | — | +14.16% | +13.99% | confirmed reset |

Signal medians: MAE63 -0.64% (vs base -3.85%), w5 rate 0% (base 14.7%), called-low 0% (base 6.8%).

Per-member (2W-A stoch, own tape): AAPL: U_MAE -0.40pp, w5 16% (base 20%), called-low 5% (n=19) · MSFT: U_MAE -3.43pp, w5 6% (base 24%), called-low 12% (n=16) · NVDA: U_MAE -5.21pp, w5 0% (base 10%), called-low 0% (n=19) · AMZN: U_MAE +0.76pp, w5 11% (base 19%), called-low 0% (n=18) · GOOGL: U_MAE +0.26pp, w5 6% (base 21%), called-low 6% (n=16) · META: U_MAE +1.05pp, w5 7% (base 16%), called-low 7% (n=15) · TSLA: U_MAE +9.43pp, w5 6% (base 8%), called-low 6% (n=17)

(Amendment-2 live-gate HIT/FAIL rules untouched — §7 item 4; this is the additive scorecard read on the census.)

## G. Pre-stated readings → §8 verdict

R1 ruler-robustness · R2 decisive re-test (kill-row disposition) · R3 altitude · R4 engine seat · R5 product split. Adjudication lands in charter §8.

## H. Limitations

- Closes-only MAE/troughs (house shadow-book form); intraday lows are deeper — levels are comparable across arms, not absolute.
- ±31td proximity window is the §7 pin; longer bear legs make 'the low' window-relative.
- Survivor tape, anchor-A 2W bars, FIT-tail spill: as W1.
- U_W5 is a rate on small per-name signal counts (3-15 OOS): per-name values are coarse; panel medians + month-cluster CIs carry the inference.
- Ladder/census re-grades are FULL-SAMPLE frames (matching the estates they re-grade), not persistence tests.
