**RE-CHECK — adjudication pending (Fable). No verdict is changed by this document.**

# EI-RC-1: P1.3 Trials — Within-Month Demeaning + Month-Block Bootstrap

Study date: 2026-07-07  |  Source: P1_3 (2026-07-05)  |  n_boot=5000 seed=11
Date window: 2022-06-30 -> 2025-12-29
Population: 49,939 verdict-grade fires | 22,295 episode clusters
BH family: m=5 (this re-check family only; separate from original m=30)

## Population

- Verdict-grade fires: 49,939
- Episode clusters (unique): 22,295
- Era: 2022-06-30 -> 2025-12-29
- Both-halves split: H1 n=23,984 | H2 n=25,955  (midpoint 2024-04-04)

## Reproduction Gate

All cohort counts within 2% of original P1_3/results.json. Gate: **PASS**.

## Primary Results: Side-by-Side

| Trial | Factor | Mode | H | TS | Orig delta (pp) | Orig perm_p | Orig BH_adj | TC delta (pp) | 95% CI lo | 95% CI hi | exact p (1-sided) | BH_tc | H1_tc (pp) | H2_tc (pp) |
|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| T02 | F1 | HG | 21d | DEAD_MONEY | -13.19 | 0.0002 | 0.0006 | -9.66 | -11.61 | -8.05 | 0.0000 | 0.0000 | -9.38 | -9.96 |
| T09 | F1 | RW | 63d | STOPPED | -4.55 | 0.0002 | 0.0006 | +0.01 | -3.08 | +3.26 | 0.5328 | 0.6626 | -2.63 | +2.49 |
| T18 | F2 | RW | 21d | CUSHIONED | +0.15 | 0.0684 | 0.0933 | +0.42 | -0.58 | +1.35 | 0.1928 | 0.4820 | +0.36 | +0.47 |
| T21 | F3 | HG | 21d | STOPPED | -0.43 | 0.0026 | 0.0060 | +0.82 | -2.69 | +4.45 | 0.6626 | 0.6626 | +0.24 | +1.15 |
| T24 | F3 | HG | 63d | STOPPED | -5.00 | 0.0648 | 0.0933 | +0.04 | -3.66 | +3.27 | 0.5158 | 0.6626 | -3.21 | +3.11 |

Columns: **TC delta** = within-month demeaned A minus B (pp). 95% CI from month-block percentile bootstrap (n_boot=5000, seed=11). **exact p** = one-sided fraction of replicates on the unfavorable side of zero (favorable sign = original shipped delta sign: negative for STOPPED/DEAD_MONEY, positive for CUSHIONED). **BH_tc** = BH-adjusted q-value across m=5 re-check family (separate from original m=30 family).

## Coverage Stamps (episodes per arm per month)

| Trial | N calendar months | Arm A ep/month min/med/max | Arm B ep/month min/med/max |
|---|---|---|---|
| T02 | 43 | 38/190.0/918 | 23/291.0/637 |
| T09 | 43 | 27/166.0/835 | 39/318.0/651 |
| T18 | 43 | 14/216.0/583 | 51/281.0/670 |
| T21 | 43 | 77/483.0/1225 | 0/19.0/126 |
| T24 | 43 | 77/483.0/1225 | 0/19.0/126 |

## Calibration Controls

### C-A: Within-Month Label Permutation (N=2000, DT-R14-matched null)

- Trial used: T02 (internal positive control — large, both-half-stable effect)
- Null mean: +0.0074 pp
- Null 95% CI: [-0.8540, +0.8416] pp (expected: covers 0)
- Observed T02 |delta_tc| = 9.6562 pp, at 100.0th percentile of null |delta_tc|

### C-B: Positive Injection (+2pp arm A on T18, CUSHIONED)

- Injected +0.02 to arm A episode ts_binary; recomputed month demean + bootstrap
- delta_tc after injection: +2.2480 pp
- 95% CI: [+1.2434, +3.1801] pp
- CI excludes 0: **True**  (required: True — detection confirmed)

## Notes

- No verdict from original P1_3 is changed here. This is a re-check under calendar-time controls for Fable adjudication.
- The word validated does not appear in this document (CI-guarded).
- Null results are printed plainly, not hidden.
- Favorable sign: negative delta for STOPPED/DEAD_MONEY (would-pass arm has fewer stops/dead-money outcomes); positive delta for CUSHIONED.
- Original perm_p and BH_adj are from the m=30 trial family. BH_tc is from this m=5 re-check family only.
- Replay MD5: 906175f9eb8caa351ed6d7d5c56265d3
