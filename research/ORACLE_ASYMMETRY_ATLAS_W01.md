# Oracle Asymmetry Atlas — W0.1

**Program:** Oracle Turn Asymmetry | Wave W0.1 — Asymmetry Re-Grade
**Date:** 2026-07-05
**Nature:** DESCRIPTIVE measurement only. No new signals. No claim language.
**Grading basis:** close-to-close approximation; intraday H/L unwired (W0.2)
**Routing tables:** DESCRIPTIVE ONLY — broad-sweep enumeration over full history (NOT restricted to p3b placebo-survivor fires; actual n reported per table).

> IMPORTANT: The word "validated" does not appear in this document per Oracle Constitution §II.
> Every table carries the close-only honesty label and n + immature count.
> routing_6 tables are additionally marked "n≤12 descriptive only."

---



## Family: ep_onset_in

### ep_onset_in | rot21
close-to-close approximation; intraday H/L unwired (W0.2)

n=357, immature=2, matured n=355

| State | N | % |
|---|---|---|
| STOPPED | 37 | 10.4% |
| DEAD_MONEY | 231 | 65.1% |
| CUSHIONED | 0 | 0.0% |
| CLEAN_LIFTOFF | 87 | 24.5% |

*Note: CUSHIONED=0 is expected for rot21. Because rot21 sets k=1 (cushion_mult = liftoff_mult = 1+σ), liftoff triggers on the same bar that cushion would — CUSHIONED is unreachable by construction, not due to market behavior.*

**Policy R-multiple (rot21):** p10=-1.00 p25=-0.21 p50=0.31 p75=0.76 p90=1.25 mean=0.28

**MFE_R@21d:** p10=0.13 p25=0.36 p50=0.62 p75=0.99 p90=1.53 mean=0.75
**MAE_R@21d:** p10=-1.05 p25=-0.52 p50=-0.18 p75=-0.01 p90=0.00 mean=-0.39
**MFE_R@63d:** p10=0.22 p25=0.57 p50=1.17 p75=1.78 p90=2.53 mean=1.30
**MAE_R@63d:** p10=-2.32 p25=-1.26 p50=-0.47 p75=-0.11 p90=0.00 mean=-0.94

**% never touch −1R (close basis):** 89.0%

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 24.5%

**Era strata (rot21):**
| Era | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| 1999-2014 | 180 | 0.32 | 0.31 | 18.3% |
| 2015-2019 | 60 | 0.31 | 0.32 | 33.3% |
| 2020-2022 | 63 | 0.23 | 0.14 | 28.6% |
| 2023-2026 | 52 | 0.37 | 0.31 | 30.8% |

**Regime strata:**
| Regime | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| High VIX (≥0.6) | 162 | 0.32 | 0.29 | 18.5% |
| Low VIX (<0.6) | 191 | 0.31 | 0.28 | 29.8% |
| SPY above 200d | 217 | 0.26 | 0.26 | 27.6% |
| SPY below 200d | 138 | 0.34 | 0.31 | 19.6% |

**Per-node strata:**
| Node | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| XLB | 38 | 0.12 | 0.13 | 21.1% |
| XLC | 9 | 0.26 | -0.16 | 11.1% |
| XLE | 38 | 0.26 | 0.39 | 26.3% |
| XLF | 41 | 0.27 | 0.19 | 19.5% |
| XLI | 35 | 0.39 | 0.36 | 37.1% |
| XLK | 39 | 0.47 | 0.37 | 23.1% |
| XLP | 31 | 0.40 | 0.40 | 38.7% |
| XLRE | 17 | 0.07 | 0.20 | 23.5% |
| XLU | 36 | 0.24 | 0.25 | 13.9% |
| XLV | 37 | 0.23 | 0.18 | 27.0% |
| XLY | 34 | 0.43 | 0.44 | 20.6% |

**Exit variant comparison (ep_onset_in | rot21):**
| Exit | N matured | Median R | Mean R | Win% |
|---|---|---|---|---|
| Fixed horizon | 355 | 0.31 | 0.28 | 24.5% |
| Exhaust exit (FLOOR label) | 355 | 0.16 | 0.30 | n/a |
| Accel-flip exit | 355 | 0.16 | 0.25 | n/a |

*Detection lag (exhaust_date − accel_flip_date): n=355 mean=9.4d p50=3.0d p75=14.0d p90=27.0d. Exhaust-exit R-multiples are a FLOOR vs reflex exits.*

### ep_onset_in | pos63
close-to-close approximation; intraday H/L unwired (W0.2)

n=357, immature=7, matured n=350

| State | N | % |
|---|---|---|
| STOPPED | 112 | 32.0% |
| DEAD_MONEY | 68 | 19.4% |
| CUSHIONED | 107 | 30.6% |
| CLEAN_LIFTOFF | 63 | 18.0% |

**Policy R-multiple (pos63):** p10=-1.00 p25=-1.00 p50=0.37 p75=1.25 p90=2.13 mean=0.39

**MFE_R@21d:** p10=0.12 p25=0.36 p50=0.62 p75=1.00 p90=1.53 mean=0.74
**MAE_R@21d:** p10=-1.06 p25=-0.53 p50=-0.20 p75=-0.01 p90=0.00 mean=-0.40
**MFE_R@63d:** p10=0.22 p25=0.57 p50=1.17 p75=1.78 p90=2.53 mean=1.30
**MAE_R@63d:** p10=-2.32 p25=-1.26 p50=-0.47 p75=-0.11 p90=0.00 mean=-0.94

**% never touch −1R (close basis):** 67.1%

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 48.6%

**Era strata (pos63):**
| Era | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| 1999-2014 | 180 | 0.58 | 0.57 | 52.8% |
| 2015-2019 | 60 | 0.58 | 0.57 | 56.7% |
| 2020-2022 | 63 | -1.00 | -0.18 | 34.9% |
| 2023-2026 | 47 | 0.00 | 0.28 | 40.4% |

**Regime strata:**
| Regime | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| High VIX (≥0.6) | 157 | 0.50 | 0.39 | 48.4% |
| Low VIX (<0.6) | 191 | 0.15 | 0.41 | 49.2% |
| SPY above 200d | 213 | 0.30 | 0.42 | 47.9% |
| SPY below 200d | 137 | 0.45 | 0.35 | 49.6% |

**Per-node strata:**
| Node | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| XLB | 38 | 0.46 | 0.30 | 36.8% |
| XLC | 8 | -1.00 | -0.16 | 25.0% |
| XLE | 38 | 0.40 | 0.61 | 52.6% |
| XLF | 40 | 0.32 | 0.21 | 50.0% |
| XLI | 35 | 0.74 | 0.57 | 57.1% |
| XLK | 38 | 0.56 | 0.50 | 52.6% |
| XLP | 31 | 0.22 | 0.47 | 58.1% |
| XLRE | 16 | -1.00 | -0.08 | 25.0% |
| XLU | 36 | 0.14 | 0.28 | 50.0% |
| XLV | 37 | 0.28 | 0.44 | 43.2% |
| XLY | 33 | 0.74 | 0.55 | 54.5% |

**Exit variant comparison (ep_onset_in | pos63):**
| Exit | N matured | Median R | Mean R | Win% |
|---|---|---|---|---|
| Fixed horizon | 350 | 0.37 | 0.39 | 48.6% |
| Exhaust exit (FLOOR label) | 350 | 0.15 | 0.30 | n/a |
| Accel-flip exit | 350 | 0.16 | 0.24 | n/a |

*Detection lag (exhaust_date − accel_flip_date): n=350 mean=9.4d p50=3.0d p75=14.0d p90=27.0d. Exhaust-exit R-multiples are a FLOOR vs reflex exits.*


## Family: ep_onset_out

### ep_onset_out | rot21
**SHORT-SIDE** | close-to-close approximation; intraday H/L unwired (W0.2)

n=392, immature=4, matured n=388

| State | N | % |
|---|---|---|
| STOPPED | 96 | 24.7% |
| DEAD_MONEY | 148 | 38.1% |
| CUSHIONED | 0 | 0.0% |
| CLEAN_LIFTOFF | 144 | 37.1% |

*Note: CUSHIONED=0 is expected for rot21. Because rot21 sets k=1 (cushion_mult = liftoff_mult = 1+σ), liftoff triggers on the same bar that cushion would — CUSHIONED is unreachable by construction, not due to market behavior.*

**Policy R-multiple (rot21):** p10=-1.00 p25=-1.00 p50=-0.19 p75=0.55 p90=1.40 mean=0.05

**MFE_R@21d:** p10=0.10 p25=0.33 p50=0.79 p75=1.35 p90=2.26 mean=1.09
**MAE_R@21d:** p10=-1.40 p25=-1.01 p50=-0.53 p75=-0.24 p90=0.00 mean=-0.66
**MFE_R@63d:** p10=0.14 p25=0.45 p50=1.05 p75=2.10 p90=3.84 mean=1.70
**MAE_R@63d:** p10=-2.50 p25=-1.95 p50=-1.28 p75=-0.60 p90=-0.22 mean=-1.38

**% never touch −1R (close basis):** 74.5%

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 37.1%

**Era strata (rot21):**
| Era | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| 1999-2014 | 191 | -0.13 | 0.00 | 38.2% |
| 2015-2019 | 64 | -0.35 | -0.14 | 29.7% |
| 2020-2022 | 61 | 0.26 | 0.69 | 45.9% |
| 2023-2026 | 72 | -0.45 | -0.19 | 33.3% |

**Regime strata:**
| Regime | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| High VIX (≥0.6) | 250 | -0.18 | 0.08 | 38.8% |
| Low VIX (<0.6) | 136 | -0.18 | 0.01 | 34.6% |
| SPY above 200d | 246 | -0.18 | 0.09 | 36.6% |
| SPY below 200d | 142 | -0.20 | -0.01 | 38.0% |

**Per-node strata:**
| Node | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| XLB | 38 | 0.02 | 0.05 | 36.8% |
| XLC | 10 | -0.29 | 0.07 | 30.0% |
| XLE | 42 | 0.23 | 0.45 | 38.1% |
| XLF | 37 | -0.28 | -0.01 | 32.4% |
| XLI | 40 | -0.17 | -0.02 | 35.0% |
| XLK | 40 | -0.28 | 0.07 | 37.5% |
| XLP | 40 | -0.43 | -0.09 | 25.0% |
| XLRE | 18 | -0.36 | -0.05 | 44.4% |
| XLU | 41 | -0.16 | -0.06 | 39.0% |
| XLV | 40 | -0.40 | -0.10 | 32.5% |
| XLY | 42 | 0.03 | 0.18 | 54.8% |

**Exit variant comparison (ep_onset_out | rot21):**
| Exit | N matured | Median R | Mean R | Win% |
|---|---|---|---|---|
| Fixed horizon | 388 | -0.19 | 0.05 | 37.1% |
| Exhaust exit (FLOOR label) | 388 | -0.15 | 0.04 | n/a |
| Accel-flip exit | 388 | -0.08 | 0.09 | n/a |

*Detection lag (exhaust_date − accel_flip_date): n=388 mean=4.9d p50=2.0d p75=7.0d p90=14.0d. Exhaust-exit R-multiples are a FLOOR vs reflex exits.*

### ep_onset_out | pos63
**SHORT-SIDE** | close-to-close approximation; intraday H/L unwired (W0.2)

n=392, immature=8, matured n=384

| State | N | % |
|---|---|---|
| STOPPED | 215 | 56.0% |
| DEAD_MONEY | 24 | 6.2% |
| CUSHIONED | 54 | 14.1% |
| CLEAN_LIFTOFF | 91 | 23.7% |

**Policy R-multiple (pos63):** p10=-1.00 p25=-1.00 p50=-1.00 p75=0.17 p90=1.58 mean=-0.21

**MFE_R@21d:** p10=0.10 p25=0.33 p50=0.77 p75=1.35 p90=2.26 mean=1.09
**MAE_R@21d:** p10=-1.40 p25=-1.01 p50=-0.53 p75=-0.24 p90=0.00 mean=-0.66
**MFE_R@63d:** p10=0.14 p25=0.45 p50=1.05 p75=2.10 p90=3.84 mean=1.70
**MAE_R@63d:** p10=-2.50 p25=-1.95 p50=-1.28 p75=-0.60 p90=-0.22 mean=-1.38

**% never touch −1R (close basis):** 42.2%

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 37.8%

**Era strata (pos63):**
| Era | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| 1999-2014 | 191 | -1.00 | -0.14 | 38.2% |
| 2015-2019 | 64 | -1.00 | -0.48 | 26.6% |
| 2020-2022 | 61 | -0.63 | 0.20 | 54.1% |
| 2023-2026 | 68 | -1.00 | -0.51 | 32.4% |

**Regime strata:**
| Regime | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| High VIX (≥0.6) | 247 | -1.00 | -0.18 | 43.3% |
| Low VIX (<0.6) | 135 | -1.00 | -0.25 | 28.1% |
| SPY above 200d | 243 | -1.00 | -0.24 | 35.4% |
| SPY below 200d | 141 | -1.00 | -0.16 | 41.8% |

**Per-node strata:**
| Node | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| XLB | 37 | -1.00 | -0.30 | 29.7% |
| XLC | 10 | -0.38 | 0.27 | 60.0% |
| XLE | 41 | -0.91 | 0.71 | 46.3% |
| XLF | 37 | -1.00 | -0.27 | 32.4% |
| XLI | 40 | -1.00 | -0.42 | 27.5% |
| XLK | 40 | -1.00 | -0.19 | 45.0% |
| XLP | 40 | -1.00 | -0.45 | 32.5% |
| XLRE | 18 | -1.00 | -0.60 | 27.8% |
| XLU | 39 | -1.00 | -0.42 | 41.0% |
| XLV | 40 | -1.00 | -0.48 | 32.5% |
| XLY | 42 | -0.95 | -0.06 | 50.0% |

**Exit variant comparison (ep_onset_out | pos63):**
| Exit | N matured | Median R | Mean R | Win% |
|---|---|---|---|---|
| Fixed horizon | 384 | -1.00 | -0.21 | 37.8% |
| Exhaust exit (FLOOR label) | 384 | -0.15 | 0.04 | n/a |
| Accel-flip exit | 384 | -0.08 | 0.10 | n/a |

*Detection lag (exhaust_date − accel_flip_date): n=384 mean=5.0d p50=2.0d p75=7.0d p90=14.0d. Exhaust-exit R-multiples are a FLOOR vs reflex exits.*


## Family: washout_p8

### washout_p8 | rot21 | dedup=raw (appendix — reconciles to ledger)
close-to-close approximation; intraday H/L unwired (W0.2)

n=641, immature=2, matured n=639

| State | N | % |
|---|---|---|
| STOPPED | 101 | 15.8% |
| DEAD_MONEY | 383 | 59.9% |
| CUSHIONED | 0 | 0.0% |
| CLEAN_LIFTOFF | 155 | 24.3% |

*Note: CUSHIONED=0 is expected for rot21. Because rot21 sets k=1 (cushion_mult = liftoff_mult = 1+σ), liftoff triggers on the same bar that cushion would — CUSHIONED is unreachable by construction, not due to market behavior.*

**Policy R-multiple (rot21):** p10=-1.00 p25=-0.35 p50=0.26 p75=0.81 p90=1.24 mean=0.24

**MFE_R@21d:** p10=0.07 p25=0.29 p50=0.61 p75=1.00 p90=1.41 mean=0.70
**MAE_R@21d:** p10=-1.28 p25=-0.78 p50=-0.30 p75=-0.07 p90=0.00 mean=-0.55
**MFE_R@63d:** p10=0.23 p25=0.59 p50=1.13 p75=1.89 p90=2.66 mean=1.35
**MAE_R@63d:** p10=-2.29 p25=-1.41 p50=-0.60 p75=-0.21 p90=0.00 mean=-0.97

**% never touch −1R (close basis):** 84.2%

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 24.3%

**Era strata (rot21):**
| Era | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| 1999-2014 | 354 | 0.17 | 0.18 | 22.6% |
| 2015-2019 | 115 | 0.32 | 0.23 | 20.0% |
| 2020-2022 | 79 | 0.57 | 0.42 | 29.1% |
| 2023-2026 | 91 | 0.48 | 0.31 | 31.9% |

**Regime strata:**
| Regime | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| High VIX (≥0.6) | 287 | 0.36 | 0.29 | 24.4% |
| Low VIX (<0.6) | 347 | 0.21 | 0.21 | 24.5% |
| SPY above 200d | 397 | 0.30 | 0.28 | 25.7% |
| SPY below 200d | 242 | 0.24 | 0.17 | 21.9% |

### washout_p8 | rot21 | dedup=first21 (headline)
close-to-close approximation; intraday H/L unwired (W0.2)

n=577, immature=1, matured n=576

| State | N | % |
|---|---|---|
| STOPPED | 91 | 15.8% |
| DEAD_MONEY | 353 | 61.3% |
| CUSHIONED | 0 | 0.0% |
| CLEAN_LIFTOFF | 132 | 22.9% |

*Note: CUSHIONED=0 is expected for rot21. Because rot21 sets k=1 (cushion_mult = liftoff_mult = 1+σ), liftoff triggers on the same bar that cushion would — CUSHIONED is unreachable by construction, not due to market behavior.*

**Policy R-multiple (rot21):** p10=-1.00 p25=-0.38 p50=0.25 p75=0.80 p90=1.23 mean=0.22

**MFE_R@21d:** p10=0.07 p25=0.29 p50=0.60 p75=0.95 p90=1.40 mean=0.69
**MAE_R@21d:** p10=-1.34 p25=-0.78 p50=-0.31 p75=-0.07 p90=0.00 mean=-0.55
**MFE_R@63d:** p10=0.23 p25=0.58 p50=1.10 p75=1.87 p90=2.64 mean=1.33
**MAE_R@63d:** p10=-2.33 p25=-1.43 p50=-0.62 p75=-0.21 p90=0.00 mean=-0.98

**% never touch −1R (close basis):** 84.2%

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 22.9%

**Era strata (rot21):**
| Era | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| 1999-2014 | 323 | 0.17 | 0.18 | 22.3% |
| 2015-2019 | 101 | 0.29 | 0.22 | 17.8% |
| 2020-2022 | 70 | 0.57 | 0.43 | 27.1% |
| 2023-2026 | 82 | 0.32 | 0.23 | 28.0% |

**Regime strata:**
| Regime | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| High VIX (≥0.6) | 261 | 0.35 | 0.26 | 22.6% |
| Low VIX (<0.6) | 310 | 0.21 | 0.21 | 23.5% |
| SPY above 200d | 359 | 0.29 | 0.27 | 24.2% |
| SPY below 200d | 217 | 0.23 | 0.15 | 20.7% |

**Per-node strata:**
| Node | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| XLB | 53 | 0.41 | 0.29 | 18.9% |
| XLC | 17 | 0.20 | 0.11 | 17.6% |
| XLE | 65 | 0.19 | 0.18 | 18.5% |
| XLF | 66 | 0.15 | 0.21 | 25.8% |
| XLI | 62 | 0.25 | 0.35 | 27.4% |
| XLK | 63 | -0.04 | 0.13 | 22.2% |
| XLP | 54 | 0.37 | 0.21 | 22.2% |
| XLRE | 22 | 0.40 | 0.22 | 27.3% |
| XLU | 56 | 0.51 | 0.27 | 19.6% |
| XLV | 56 | 0.18 | 0.24 | 30.4% |
| XLY | 62 | 0.23 | 0.18 | 21.0% |

**Exit variant comparison (washout_p8 | rot21):**
| Exit | N matured | Median R | Mean R | Win% |
|---|---|---|---|---|
| Fixed horizon | 1215 | 0.26 | 0.23 | 23.6% |
| Accel-flip exit | 1215 | 0.04 | 0.10 | n/a |

### washout_p8 | pos63 | dedup=raw (appendix — reconciles to ledger)
close-to-close approximation; intraday H/L unwired (W0.2)

n=641, immature=12, matured n=629

| State | N | % |
|---|---|---|
| STOPPED | 208 | 33.1% |
| DEAD_MONEY | 118 | 18.8% |
| CUSHIONED | 177 | 28.1% |
| CLEAN_LIFTOFF | 126 | 20.0% |

**Policy R-multiple (pos63):** p10=-1.00 p25=-1.00 p50=0.30 p75=1.29 p90=2.14 mean=0.39

**MFE_R@21d:** p10=0.07 p25=0.29 p50=0.60 p75=0.97 p90=1.41 mean=0.70
**MAE_R@21d:** p10=-1.31 p25=-0.78 p50=-0.31 p75=-0.07 p90=0.00 mean=-0.55
**MFE_R@63d:** p10=0.23 p25=0.59 p50=1.13 p75=1.89 p90=2.66 mean=1.35
**MAE_R@63d:** p10=-2.29 p25=-1.41 p50=-0.60 p75=-0.21 p90=0.00 mean=-0.97

**% never touch −1R (close basis):** 66.6%

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 48.2%

**Era strata (pos63):**
| Era | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| 1999-2014 | 354 | 0.21 | 0.37 | 47.7% |
| 2015-2019 | 115 | 0.41 | 0.32 | 45.2% |
| 2020-2022 | 79 | 0.34 | 0.35 | 49.4% |
| 2023-2026 | 81 | 0.54 | 0.59 | 53.1% |

**Regime strata:**
| Regime | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| High VIX (≥0.6) | 280 | 0.36 | 0.38 | 47.9% |
| Low VIX (<0.6) | 344 | 0.24 | 0.41 | 49.1% |
| SPY above 200d | 393 | 0.39 | 0.47 | 51.7% |
| SPY below 200d | 236 | 0.21 | 0.25 | 42.4% |

### washout_p8 | pos63 | dedup=first21 (headline)
close-to-close approximation; intraday H/L unwired (W0.2)

n=577, immature=11, matured n=566

| State | N | % |
|---|---|---|
| STOPPED | 190 | 33.6% |
| DEAD_MONEY | 108 | 19.1% |
| CUSHIONED | 160 | 28.3% |
| CLEAN_LIFTOFF | 108 | 19.1% |

**Policy R-multiple (pos63):** p10=-1.00 p25=-1.00 p50=0.28 p75=1.25 p90=2.10 mean=0.38

**MFE_R@21d:** p10=0.07 p25=0.28 p50=0.59 p75=0.94 p90=1.40 mean=0.68
**MAE_R@21d:** p10=-1.37 p25=-0.80 p50=-0.32 p75=-0.08 p90=0.00 mean=-0.56
**MFE_R@63d:** p10=0.23 p25=0.58 p50=1.10 p75=1.87 p90=2.64 mean=1.33
**MAE_R@63d:** p10=-2.33 p25=-1.43 p50=-0.62 p75=-0.21 p90=0.00 mean=-0.98

**% never touch −1R (close basis):** 66.3%

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 47.3%

**Era strata (pos63):**
| Era | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| 1999-2014 | 323 | 0.20 | 0.36 | 47.4% |
| 2015-2019 | 101 | 0.46 | 0.37 | 44.6% |
| 2020-2022 | 70 | 0.46 | 0.39 | 50.0% |
| 2023-2026 | 72 | 0.07 | 0.46 | 48.6% |

**Regime strata:**
| Regime | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| High VIX (≥0.6) | 254 | 0.31 | 0.34 | 45.7% |
| Low VIX (<0.6) | 307 | 0.30 | 0.43 | 49.5% |
| SPY above 200d | 355 | 0.39 | 0.46 | 51.3% |
| SPY below 200d | 211 | 0.20 | 0.23 | 40.8% |

**Per-node strata:**
| Node | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| XLB | 52 | 0.21 | 0.39 | 53.8% |
| XLC | 16 | -0.21 | 0.06 | 43.8% |
| XLE | 64 | 0.54 | 0.45 | 48.4% |
| XLF | 66 | 0.21 | 0.39 | 40.9% |
| XLI | 61 | 0.36 | 0.37 | 49.2% |
| XLK | 62 | 0.15 | 0.26 | 43.5% |
| XLP | 53 | 0.22 | 0.41 | 49.1% |
| XLRE | 21 | 0.47 | 0.33 | 42.9% |
| XLU | 56 | 0.58 | 0.59 | 57.1% |
| XLV | 54 | 0.32 | 0.24 | 40.7% |
| XLY | 61 | 0.40 | 0.38 | 47.5% |

**Exit variant comparison (washout_p8 | pos63):**
| Exit | N matured | Median R | Mean R | Win% |
|---|---|---|---|---|
| Fixed horizon | 1195 | 0.30 | 0.38 | 47.8% |
| Accel-flip exit | 1195 | 0.03 | 0.09 | n/a |


## Family: a15

### a15 | rot21 | dedup=raw (appendix — reconciles to ledger)
close-to-close approximation; intraday H/L unwired (W0.2)

n=2367, immature=10, matured n=2357

| State | N | % |
|---|---|---|
| STOPPED | 247 | 10.5% |
| DEAD_MONEY | 1369 | 58.1% |
| CUSHIONED | 0 | 0.0% |
| CLEAN_LIFTOFF | 741 | 31.4% |

*Note: CUSHIONED=0 is expected for rot21. Because rot21 sets k=1 (cushion_mult = liftoff_mult = 1+σ), liftoff triggers on the same bar that cushion would — CUSHIONED is unreachable by construction, not due to market behavior.*

**Policy R-multiple (rot21):** p10=-1.00 p25=-0.11 p50=0.43 p75=0.91 p90=1.45 mean=0.41

**MFE_R@21d:** p10=0.15 p25=0.39 p50=0.72 p75=1.15 p90=1.63 mean=0.83
**MAE_R@21d:** p10=-1.03 p25=-0.61 p50=-0.26 p75=-0.03 p90=0.00 mean=-0.42
**MFE_R@63d:** p10=0.34 p25=0.74 p50=1.27 p75=2.00 p90=2.84 mean=1.49
**MAE_R@63d:** p10=-1.87 p25=-1.03 p50=-0.46 p75=-0.14 p90=0.00 mean=-0.74

**% never touch −1R (close basis):** 89.2%

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 31.4%

**Era strata (rot21):**
| Era | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| 1999-2014 | 1345 | 0.39 | 0.39 | 28.8% |
| 2015-2019 | 343 | 0.45 | 0.44 | 27.4% |
| 2020-2022 | 365 | 0.42 | 0.39 | 32.6% |
| 2023-2026 | 304 | 0.59 | 0.50 | 46.4% |

**Regime strata:**
| Regime | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| High VIX (≥0.6) | 1578 | 0.35 | 0.31 | 24.1% |
| Low VIX (<0.6) | 779 | 0.67 | 0.61 | 46.3% |
| SPY above 200d | 1154 | 0.54 | 0.51 | 39.3% |
| SPY below 200d | 1203 | 0.34 | 0.31 | 23.9% |

### a15 | rot21 | dedup=first21 (headline)
close-to-close approximation; intraday H/L unwired (W0.2)

n=197, immature=1, matured n=196

| State | N | % |
|---|---|---|
| STOPPED | 31 | 15.8% |
| DEAD_MONEY | 93 | 47.4% |
| CUSHIONED | 0 | 0.0% |
| CLEAN_LIFTOFF | 72 | 36.7% |

*Note: CUSHIONED=0 is expected for rot21. Because rot21 sets k=1 (cushion_mult = liftoff_mult = 1+σ), liftoff triggers on the same bar that cushion would — CUSHIONED is unreachable by construction, not due to market behavior.*

**Policy R-multiple (rot21):** p10=-1.00 p25=-0.23 p50=0.43 p75=1.00 p90=1.46 mean=0.38

**MFE_R@21d:** p10=0.12 p25=0.46 p50=0.87 p75=1.26 p90=1.67 mean=0.88
**MAE_R@21d:** p10=-1.33 p25=-0.73 p50=-0.34 p75=-0.04 p90=0.00 mean=-0.53
**MFE_R@63d:** p10=0.41 p25=0.81 p50=1.43 p75=2.25 p90=3.00 mean=1.62
**MAE_R@63d:** p10=-1.98 p25=-1.09 p50=-0.50 p75=-0.18 p90=0.00 mean=-0.79

**% never touch −1R (close basis):** 84.2%

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 36.7%

**Era strata (rot21):**
| Era | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| 1999-2014 | 105 | 0.55 | 0.36 | 34.3% |
| 2015-2019 | 33 | 0.29 | 0.37 | 36.4% |
| 2020-2022 | 29 | 0.47 | 0.61 | 41.4% |
| 2023-2026 | 29 | 0.23 | 0.25 | 41.4% |

**Regime strata:**
| Regime | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| High VIX (≥0.6) | 140 | 0.34 | 0.28 | 30.7% |
| Low VIX (<0.6) | 56 | 0.74 | 0.65 | 51.8% |
| SPY above 200d | 90 | 0.59 | 0.49 | 41.1% |
| SPY below 200d | 106 | 0.39 | 0.30 | 33.0% |

**Per-node strata:**
| Node | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| XLB | 33 | 0.56 | 0.32 | 42.4% |
| XLE | 34 | 0.41 | 0.30 | 32.4% |
| XLF | 41 | 0.37 | 0.33 | 34.1% |
| XLI | 26 | 0.88 | 0.61 | 46.2% |
| XLK | 21 | 0.47 | 0.42 | 23.8% |
| XLP | 11 | 0.43 | 0.43 | 36.4% |
| XLRE | 6 | 1.13 | 0.91 | 66.7% |
| XLU | 10 | 0.40 | 0.47 | 50.0% |
| XLV | 14 | 0.20 | 0.07 | 21.4% |

**Exit variant comparison (a15 | rot21):**
| Exit | N matured | Median R | Mean R | Win% |
|---|---|---|---|---|
| Fixed horizon | 2553 | 0.43 | 0.41 | 31.8% |
| Accel-flip exit | 2553 | 0.08 | 0.15 | n/a |

### a15 | pos63 | dedup=raw (appendix — reconciles to ledger)
close-to-close approximation; intraday H/L unwired (W0.2)

n=2367, immature=16, matured n=2351

| State | N | % |
|---|---|---|
| STOPPED | 597 | 25.4% |
| DEAD_MONEY | 521 | 22.2% |
| CUSHIONED | 687 | 29.2% |
| CLEAN_LIFTOFF | 546 | 23.2% |

**Policy R-multiple (pos63):** p10=-1.00 p25=-1.00 p50=0.57 p75=1.47 p90=2.40 mean=0.62

**MFE_R@21d:** p10=0.15 p25=0.39 p50=0.72 p75=1.15 p90=1.63 mean=0.83
**MAE_R@21d:** p10=-1.03 p25=-0.61 p50=-0.26 p75=-0.03 p90=0.00 mean=-0.42
**MFE_R@63d:** p10=0.34 p25=0.74 p50=1.27 p75=2.00 p90=2.84 mean=1.49
**MAE_R@63d:** p10=-1.87 p25=-1.03 p50=-0.46 p75=-0.14 p90=0.00 mean=-0.74

**% never touch −1R (close basis):** 74.1%

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 52.4%

**Era strata (pos63):**
| Era | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| 1999-2014 | 1345 | 0.55 | 0.61 | 50.3% |
| 2015-2019 | 343 | 0.65 | 0.66 | 55.4% |
| 2020-2022 | 365 | 0.56 | 0.33 | 55.6% |
| 2023-2026 | 298 | 0.58 | 0.99 | 55.0% |

**Regime strata:**
| Regime | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| High VIX (≥0.6) | 1572 | 0.46 | 0.47 | 48.0% |
| Low VIX (<0.6) | 779 | 0.95 | 0.93 | 61.5% |
| SPY above 200d | 1154 | 0.62 | 0.75 | 57.1% |
| SPY below 200d | 1197 | 0.55 | 0.50 | 48.0% |

### a15 | pos63 | dedup=first21 (headline)
close-to-close approximation; intraday H/L unwired (W0.2)

n=197, immature=1, matured n=196

| State | N | % |
|---|---|---|
| STOPPED | 53 | 27.0% |
| DEAD_MONEY | 29 | 14.8% |
| CUSHIONED | 56 | 28.6% |
| CLEAN_LIFTOFF | 58 | 29.6% |

**Policy R-multiple (pos63):** p10=-1.00 p25=-1.00 p50=0.61 p75=1.66 p90=2.57 mean=0.70

**MFE_R@21d:** p10=0.12 p25=0.46 p50=0.87 p75=1.26 p90=1.67 mean=0.88
**MAE_R@21d:** p10=-1.33 p25=-0.73 p50=-0.34 p75=-0.04 p90=0.00 mean=-0.53
**MFE_R@63d:** p10=0.41 p25=0.81 p50=1.43 p75=2.25 p90=3.00 mean=1.62
**MAE_R@63d:** p10=-1.98 p25=-1.09 p50=-0.50 p75=-0.18 p90=0.00 mean=-0.79

**% never touch −1R (close basis):** 73.0%

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 58.2%

**Era strata (pos63):**
| Era | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| 1999-2014 | 105 | 0.49 | 0.65 | 56.2% |
| 2015-2019 | 33 | 0.83 | 0.74 | 57.6% |
| 2020-2022 | 29 | 0.87 | 0.56 | 69.0% |
| 2023-2026 | 29 | 0.58 | 0.98 | 55.2% |

**Regime strata:**
| Regime | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| High VIX (≥0.6) | 140 | 0.57 | 0.58 | 54.3% |
| Low VIX (<0.6) | 56 | 1.11 | 1.02 | 67.9% |
| SPY above 200d | 90 | 0.74 | 0.87 | 65.6% |
| SPY below 200d | 106 | 0.51 | 0.56 | 51.9% |

**Per-node strata:**
| Node | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| XLB | 33 | 0.47 | 0.64 | 60.6% |
| XLE | 34 | 0.53 | 0.71 | 58.8% |
| XLF | 41 | 0.26 | 0.31 | 48.8% |
| XLI | 26 | 1.20 | 1.01 | 65.4% |
| XLK | 21 | 0.84 | 0.82 | 61.9% |
| XLP | 11 | 0.75 | 1.03 | 54.5% |
| XLRE | 6 | 1.14 | 1.22 | 66.7% |
| XLU | 10 | 1.19 | 1.16 | 70.0% |
| XLV | 14 | 0.35 | 0.39 | 50.0% |

**Exit variant comparison (a15 | pos63):**
| Exit | N matured | Median R | Mean R | Win% |
|---|---|---|---|---|
| Fixed horizon | 2547 | 0.58 | 0.63 | 52.9% |
| Accel-flip exit | 2547 | 0.08 | 0.15 | n/a |


## Family: a9

### a9 | rot21 | dedup=raw (appendix — reconciles to ledger)
close-to-close approximation; intraday H/L unwired (W0.2)

n=446, immature=8, matured n=438

| State | N | % |
|---|---|---|
| STOPPED | 67 | 15.3% |
| DEAD_MONEY | 259 | 59.1% |
| CUSHIONED | 0 | 0.0% |
| CLEAN_LIFTOFF | 112 | 25.6% |

*Note: CUSHIONED=0 is expected for rot21. Because rot21 sets k=1 (cushion_mult = liftoff_mult = 1+σ), liftoff triggers on the same bar that cushion would — CUSHIONED is unreachable by construction, not due to market behavior.*

**Policy R-multiple (rot21):** p10=-1.00 p25=-0.26 p50=0.32 p75=0.80 p90=1.29 mean=0.26

**MFE_R@21d:** p10=0.08 p25=0.33 p50=0.65 p75=1.02 p90=1.44 mean=0.72
**MAE_R@21d:** p10=-1.21 p25=-0.72 p50=-0.40 p75=-0.17 p90=0.00 mean=-0.57
**MFE_R@63d:** p10=0.21 p25=0.49 p50=1.25 p75=1.89 p90=2.83 mean=1.34
**MAE_R@63d:** p10=-1.88 p25=-1.08 p50=-0.59 p75=-0.24 p90=-0.02 mean=-0.90

**% never touch −1R (close basis):** 84.7%

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 25.6%

**Era strata (rot21):**
| Era | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| 1999-2014 | 193 | 0.05 | 0.10 | 16.6% |
| 2015-2019 | 54 | 0.11 | 0.05 | 24.1% |
| 2020-2022 | 127 | 0.51 | 0.41 | 26.8% |
| 2023-2026 | 64 | 0.64 | 0.66 | 51.6% |

**Regime strata:**
| Regime | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| High VIX (≥0.6) | 323 | 0.32 | 0.25 | 22.9% |
| Low VIX (<0.6) | 115 | 0.38 | 0.30 | 33.0% |
| SPY above 200d | 189 | 0.49 | 0.34 | 36.5% |
| SPY below 200d | 249 | 0.24 | 0.20 | 17.3% |

### a9 | rot21 | dedup=first21 (headline)
close-to-close approximation; intraday H/L unwired (W0.2)

n=46, immature=2, matured n=44

| State | N | % |
|---|---|---|
| STOPPED | 12 | 27.3% |
| DEAD_MONEY | 17 | 38.6% |
| CUSHIONED | 0 | 0.0% |
| CLEAN_LIFTOFF | 15 | 34.1% |

*Note: CUSHIONED=0 is expected for rot21. Because rot21 sets k=1 (cushion_mult = liftoff_mult = 1+σ), liftoff triggers on the same bar that cushion would — CUSHIONED is unreachable by construction, not due to market behavior.*

**Policy R-multiple (rot21):** p10=-1.00 p25=-1.00 p50=0.22 p75=0.93 p90=1.23 mean=0.17

**MFE_R@21d:** p10=0.01 p25=0.33 p50=0.76 p75=1.23 p90=1.48 mean=0.77
**MAE_R@21d:** p10=-1.70 p25=-1.04 p50=-0.53 p75=-0.14 p90=0.00 mean=-0.74
**MFE_R@63d:** p10=0.16 p25=0.63 p50=1.39 p75=1.93 p90=2.90 mean=1.44
**MAE_R@63d:** p10=-2.65 p25=-1.38 p50=-0.64 p75=-0.22 p90=-0.03 mean=-1.13

**% never touch −1R (close basis):** 72.7%

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 34.1%

**Era strata (rot21):**
| Era | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| 1999-2014 | 17 | -0.19 | -0.07 | 23.5% |
| 2015-2019 | 8 | 0.20 | 0.13 | 25.0% |
| 2020-2022 | 13 | 0.79 | 0.35 | 38.5% |
| 2023-2026 | 6 | 0.45 | 0.50 | 66.7% |

**Regime strata:**
| Regime | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| High VIX (≥0.6) | 35 | 0.21 | 0.20 | 34.3% |
| Low VIX (<0.6) | 9 | 0.32 | 0.07 | 33.3% |
| SPY above 200d | 23 | 0.32 | 0.07 | 39.1% |
| SPY below 200d | 21 | 0.21 | 0.27 | 28.6% |

**Per-node strata:**
| Node | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| XLB | 12 | -0.07 | 0.18 | 41.7% |
| XLE | 14 | 0.09 | -0.03 | 21.4% |
| XLRE | 10 | 0.53 | 0.37 | 40.0% |
| XLU | 8 | 0.45 | 0.25 | 37.5% |

**Exit variant comparison (a9 | rot21):**
| Exit | N matured | Median R | Mean R | Win% |
|---|---|---|---|---|
| Fixed horizon | 482 | 0.32 | 0.25 | 26.3% |
| Accel-flip exit | 482 | 0.03 | 0.05 | n/a |

### a9 | pos63 | dedup=raw (appendix — reconciles to ledger)
close-to-close approximation; intraday H/L unwired (W0.2)

n=446, immature=8, matured n=438

| State | N | % |
|---|---|---|
| STOPPED | 123 | 28.1% |
| DEAD_MONEY | 111 | 25.3% |
| CUSHIONED | 119 | 27.2% |
| CLEAN_LIFTOFF | 85 | 19.4% |

**Policy R-multiple (pos63):** p10=-1.00 p25=-1.00 p50=0.20 p75=1.08 p90=1.96 mean=0.32

**MFE_R@21d:** p10=0.08 p25=0.33 p50=0.65 p75=1.02 p90=1.44 mean=0.72
**MAE_R@21d:** p10=-1.21 p25=-0.72 p50=-0.40 p75=-0.17 p90=0.00 mean=-0.57
**MFE_R@63d:** p10=0.21 p25=0.49 p50=1.25 p75=1.89 p90=2.83 mean=1.34
**MAE_R@63d:** p10=-1.88 p25=-1.08 p50=-0.59 p75=-0.24 p90=-0.02 mean=-0.90

**% never touch −1R (close basis):** 70.8%

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 46.6%

**Era strata (pos63):**
| Era | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| 1999-2014 | 193 | 0.09 | 0.07 | 30.1% |
| 2015-2019 | 54 | 0.87 | 0.44 | 55.6% |
| 2020-2022 | 127 | 0.40 | 0.55 | 52.8% |
| 2023-2026 | 64 | 0.50 | 0.51 | 76.6% |

**Regime strata:**
| Regime | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| High VIX (≥0.6) | 323 | 0.12 | 0.15 | 42.7% |
| Low VIX (<0.6) | 115 | 0.56 | 0.78 | 57.4% |
| SPY above 200d | 189 | 0.47 | 0.49 | 57.1% |
| SPY below 200d | 249 | 0.12 | 0.19 | 38.6% |

### a9 | pos63 | dedup=first21 (headline)
close-to-close approximation; intraday H/L unwired (W0.2)

n=46, immature=2, matured n=44

| State | N | % |
|---|---|---|
| STOPPED | 18 | 40.9% |
| DEAD_MONEY | 3 | 6.8% |
| CUSHIONED | 15 | 34.1% |
| CLEAN_LIFTOFF | 8 | 18.2% |

**Policy R-multiple (pos63):** p10=-1.00 p25=-1.00 p50=0.35 p75=1.16 p90=2.34 mean=0.38

**MFE_R@21d:** p10=0.01 p25=0.33 p50=0.76 p75=1.23 p90=1.48 mean=0.77
**MAE_R@21d:** p10=-1.70 p25=-1.04 p50=-0.53 p75=-0.14 p90=0.00 mean=-0.74
**MFE_R@63d:** p10=0.16 p25=0.63 p50=1.39 p75=1.93 p90=2.90 mean=1.44
**MAE_R@63d:** p10=-2.65 p25=-1.38 p50=-0.64 p75=-0.22 p90=-0.03 mean=-1.13

**% never touch −1R (close basis):** 59.1%

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 52.3%

**Era strata (pos63):**
| Era | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| 1999-2014 | 17 | -1.00 | -0.11 | 35.3% |
| 2015-2019 | 8 | 0.00 | 0.41 | 50.0% |
| 2020-2022 | 13 | 1.07 | 0.72 | 61.5% |
| 2023-2026 | 6 | 0.55 | 0.98 | 83.3% |

**Regime strata:**
| Regime | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| High VIX (≥0.6) | 35 | 0.29 | 0.22 | 51.4% |
| Low VIX (<0.6) | 9 | 0.52 | 0.98 | 55.6% |
| SPY above 200d | 23 | 0.52 | 0.33 | 52.2% |
| SPY below 200d | 21 | 0.29 | 0.43 | 52.4% |

**Per-node strata:**
| Node | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| XLB | 12 | 0.15 | 0.30 | 41.7% |
| XLE | 14 | -1.00 | -0.07 | 42.9% |
| XLRE | 10 | 1.06 | 1.00 | 60.0% |
| XLU | 8 | 0.53 | 0.51 | 75.0% |

**Exit variant comparison (a9 | pos63):**
| Exit | N matured | Median R | Mean R | Win% |
|---|---|---|---|---|
| Fixed horizon | 482 | 0.20 | 0.32 | 47.1% |
| Accel-flip exit | 482 | 0.03 | 0.05 | n/a |


## Family: a17

### a17 | rot21 | dedup=raw (appendix — reconciles to ledger)
close-to-close approximation; intraday H/L unwired (W0.2)

n=268, immature=6, matured n=262

| State | N | % |
|---|---|---|
| STOPPED | 48 | 18.3% |
| DEAD_MONEY | 135 | 51.5% |
| CUSHIONED | 0 | 0.0% |
| CLEAN_LIFTOFF | 79 | 30.2% |

*Note: CUSHIONED=0 is expected for rot21. Because rot21 sets k=1 (cushion_mult = liftoff_mult = 1+σ), liftoff triggers on the same bar that cushion would — CUSHIONED is unreachable by construction, not due to market behavior.*

**Policy R-multiple (rot21):** p10=-1.00 p25=-0.27 p50=0.43 p75=0.89 p90=1.46 mean=0.31

**MFE_R@21d:** p10=0.18 p25=0.39 p50=0.72 p75=1.10 p90=1.66 mean=0.81
**MAE_R@21d:** p10=-1.66 p25=-0.74 p50=-0.41 p75=-0.14 p90=0.00 mean=-0.65
**MFE_R@63d:** p10=0.25 p25=0.58 p50=1.22 p75=1.96 p90=2.79 mean=1.40
**MAE_R@63d:** p10=-1.95 p25=-1.16 p50=-0.58 p75=-0.22 p90=0.00 mean=-0.90

**% never touch −1R (close basis):** 81.7%

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 30.2%

**Era strata (rot21):**
| Era | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| 1999-2014 | 117 | 0.11 | 0.14 | 22.2% |
| 2015-2019 | 29 | -0.55 | -0.13 | 24.1% |
| 2020-2022 | 79 | 0.59 | 0.47 | 34.2% |
| 2023-2026 | 37 | 0.82 | 0.87 | 51.4% |

**Regime strata:**
| Regime | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| High VIX (≥0.6) | 198 | 0.46 | 0.29 | 29.8% |
| Low VIX (<0.6) | 64 | 0.35 | 0.37 | 31.2% |
| SPY above 200d | 112 | 0.54 | 0.41 | 35.7% |
| SPY below 200d | 150 | 0.31 | 0.24 | 26.0% |

### a17 | rot21 | dedup=first21 (headline)
close-to-close approximation; intraday H/L unwired (W0.2)

n=44, immature=2, matured n=42

| State | N | % |
|---|---|---|
| STOPPED | 9 | 21.4% |
| DEAD_MONEY | 20 | 47.6% |
| CUSHIONED | 0 | 0.0% |
| CLEAN_LIFTOFF | 13 | 31.0% |

*Note: CUSHIONED=0 is expected for rot21. Because rot21 sets k=1 (cushion_mult = liftoff_mult = 1+σ), liftoff triggers on the same bar that cushion would — CUSHIONED is unreachable by construction, not due to market behavior.*

**Policy R-multiple (rot21):** p10=-1.00 p25=-0.41 p50=0.42 p75=0.91 p90=1.23 mean=0.27

**MFE_R@21d:** p10=0.22 p25=0.45 p50=0.78 p75=1.10 p90=1.43 mean=0.80
**MAE_R@21d:** p10=-1.73 p25=-0.95 p50=-0.46 p75=-0.14 p90=0.00 mean=-0.72
**MFE_R@63d:** p10=0.39 p25=0.68 p50=1.25 p75=1.94 p90=2.86 mean=1.44
**MAE_R@63d:** p10=-2.76 p25=-1.28 p50=-0.63 p75=-0.23 p90=-0.01 mean=-1.09

**% never touch −1R (close basis):** 78.6%

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 31.0%

**Era strata (rot21):**
| Era | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| 1999-2014 | 17 | 0.14 | 0.14 | 23.5% |
| 2015-2019 | 7 | 0.18 | 0.08 | 14.3% |
| 2020-2022 | 13 | 0.79 | 0.40 | 38.5% |
| 2023-2026 | 5 | 0.80 | 0.61 | 60.0% |

**Regime strata:**
| Regime | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| High VIX (≥0.6) | 34 | 0.46 | 0.32 | 32.4% |
| Low VIX (<0.6) | 8 | 0.06 | 0.08 | 25.0% |
| SPY above 200d | 22 | 0.38 | 0.25 | 36.4% |
| SPY below 200d | 20 | 0.44 | 0.29 | 25.0% |

**Per-node strata:**
| Node | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| XLB | 11 | 0.32 | 0.30 | 36.4% |
| XLE | 13 | 0.18 | 0.10 | 15.4% |
| XLRE | 10 | 0.65 | 0.39 | 40.0% |
| XLU | 8 | 0.73 | 0.35 | 37.5% |

**Exit variant comparison (a17 | rot21):**
| Exit | N matured | Median R | Mean R | Win% |
|---|---|---|---|---|
| Fixed horizon | 304 | 0.43 | 0.31 | 30.3% |
| Accel-flip exit | 304 | 0.07 | 0.05 | n/a |

### a17 | pos63 | dedup=raw (appendix — reconciles to ledger)
close-to-close approximation; intraday H/L unwired (W0.2)

n=268, immature=6, matured n=262

| State | N | % |
|---|---|---|
| STOPPED | 72 | 27.5% |
| DEAD_MONEY | 65 | 24.8% |
| CUSHIONED | 65 | 24.8% |
| CLEAN_LIFTOFF | 60 | 22.9% |

**Policy R-multiple (pos63):** p10=-1.00 p25=-1.00 p50=0.31 p75=1.17 p90=2.04 mean=0.38

**MFE_R@21d:** p10=0.18 p25=0.39 p50=0.72 p75=1.10 p90=1.66 mean=0.81
**MAE_R@21d:** p10=-1.66 p25=-0.74 p50=-0.41 p75=-0.14 p90=0.00 mean=-0.65
**MFE_R@63d:** p10=0.25 p25=0.58 p50=1.22 p75=1.96 p90=2.79 mean=1.40
**MAE_R@63d:** p10=-1.95 p25=-1.16 p50=-0.58 p75=-0.22 p90=0.00 mean=-0.90

**% never touch −1R (close basis):** 71.0%

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 47.7%

**Era strata (pos63):**
| Era | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| 1999-2014 | 117 | 0.19 | 0.12 | 31.6% |
| 2015-2019 | 29 | -1.00 | -0.10 | 34.5% |
| 2020-2022 | 79 | 0.97 | 0.75 | 59.5% |
| 2023-2026 | 37 | 0.56 | 0.80 | 83.8% |

**Regime strata:**
| Regime | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| High VIX (≥0.6) | 198 | 0.25 | 0.22 | 44.9% |
| Low VIX (<0.6) | 64 | 0.57 | 0.86 | 56.2% |
| SPY above 200d | 112 | 0.47 | 0.49 | 54.5% |
| SPY below 200d | 150 | 0.28 | 0.30 | 42.7% |

### a17 | pos63 | dedup=first21 (headline)
close-to-close approximation; intraday H/L unwired (W0.2)

n=44, immature=2, matured n=42

| State | N | % |
|---|---|---|
| STOPPED | 13 | 31.0% |
| DEAD_MONEY | 7 | 16.7% |
| CUSHIONED | 14 | 33.3% |
| CLEAN_LIFTOFF | 8 | 19.0% |

**Policy R-multiple (pos63):** p10=-1.00 p25=-1.00 p50=0.50 p75=1.16 p90=2.26 mean=0.49

**MFE_R@21d:** p10=0.22 p25=0.45 p50=0.78 p75=1.10 p90=1.43 mean=0.80
**MAE_R@21d:** p10=-1.73 p25=-0.95 p50=-0.46 p75=-0.14 p90=0.00 mean=-0.72
**MFE_R@63d:** p10=0.39 p25=0.68 p50=1.25 p75=1.94 p90=2.86 mean=1.44
**MAE_R@63d:** p10=-2.76 p25=-1.28 p50=-0.63 p75=-0.23 p90=-0.01 mean=-1.09

**% never touch −1R (close basis):** 69.0%

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 52.4%

**Era strata (pos63):**
| Era | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| 1999-2014 | 17 | 0.29 | 0.14 | 35.3% |
| 2015-2019 | 7 | -0.12 | 0.31 | 42.9% |
| 2020-2022 | 13 | 1.07 | 0.70 | 61.5% |
| 2023-2026 | 5 | 0.57 | 1.39 | 100.0% |

**Regime strata:**
| Regime | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| High VIX (≥0.6) | 34 | 0.45 | 0.31 | 50.0% |
| Low VIX (<0.6) | 8 | 1.22 | 1.23 | 62.5% |
| SPY above 200d | 22 | 0.57 | 0.61 | 54.5% |
| SPY below 200d | 20 | 0.21 | 0.35 | 50.0% |

**Per-node strata:**
| Node | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| XLB | 11 | 0.29 | 0.39 | 36.4% |
| XLE | 13 | 0.42 | 0.18 | 46.2% |
| XLRE | 10 | 1.06 | 1.00 | 60.0% |
| XLU | 8 | 0.55 | 0.48 | 75.0% |

**Exit variant comparison (a17 | pos63):**
| Exit | N matured | Median R | Mean R | Win% |
|---|---|---|---|---|
| Fixed horizon | 304 | 0.32 | 0.40 | 48.4% |
| Accel-flip exit | 304 | 0.07 | 0.05 | n/a |


## Family: routing_6

### routing_6 | rot21
**DESCRIPTIVE ONLY — broad-sweep enumeration (NOT the p3b placebo-survivor set; n is the full-history onset sweep, not the ~10-12 p3b survivor fires per cell)** | close-to-close approximation; intraday H/L unwired (W0.2)

n=565, immature=11, matured n=554

| State | N | % |
|---|---|---|
| STOPPED | 138 | 24.9% |
| DEAD_MONEY | 233 | 42.1% |
| CUSHIONED | 0 | 0.0% |
| CLEAN_LIFTOFF | 183 | 33.0% |

*Note: CUSHIONED=0 is expected for rot21. Because rot21 sets k=1 (cushion_mult = liftoff_mult = 1+σ), liftoff triggers on the same bar that cushion would — CUSHIONED is unreachable by construction, not due to market behavior.*

**Policy R-multiple (rot21):** p10=-1.00 p25=-1.00 p50=0.22 p75=0.93 p90=1.51 mean=0.19

**MFE_R@21d:** p10=0.00 p25=0.28 p50=0.74 p75=1.19 p90=1.66 mean=0.80
**MAE_R@21d:** p10=-1.66 p25=-1.02 p50=-0.46 p75=-0.08 p90=0.00 mean=-0.70
**MFE_R@63d:** p10=0.22 p25=0.66 p50=1.29 p75=2.21 p90=2.99 mean=1.53
**MAE_R@63d:** p10=-2.55 p25=-1.66 p50=-0.80 p75=-0.23 p90=0.00 mean=-1.13

**% never touch −1R (close basis):** 74.4%

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 33.0%

**Era strata (rot21):**
| Era | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| 1999-2014 | 296 | 0.13 | 0.15 | 33.8% |
| 2015-2019 | 134 | 0.27 | 0.28 | 35.1% |
| 2020-2022 | 73 | -0.09 | -0.03 | 20.5% |
| 2023-2026 | 51 | 0.54 | 0.49 | 41.2% |

**Regime strata:**
| Regime | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| High VIX (≥0.6) | 554 | 0.22 | 0.19 | 33.0% |
| Low VIX (<0.6) | 0 | n/a | n/a | n/a |
| SPY above 200d | 246 | 0.29 | 0.27 | 36.6% |
| SPY below 200d | 308 | 0.12 | 0.13 | 30.2% |

**Per-node strata:**
| Node | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| XLB | 82 | 0.31 | 0.19 | 40.2% |
| XLE | 82 | 0.03 | 0.16 | 30.5% |
| XLF | 160 | 0.13 | 0.16 | 27.5% |
| XLK | 230 | 0.32 | 0.22 | 35.2% |

**Exit variant comparison (routing_6 | rot21):**
| Exit | N matured | Median R | Mean R | Win% |
|---|---|---|---|---|
| Fixed horizon | 554 | 0.22 | 0.19 | 33.0% |
| Accel-flip exit | 554 | 0.08 | 0.05 | n/a |

### routing_6 | pos63
**DESCRIPTIVE ONLY — broad-sweep enumeration (NOT the p3b placebo-survivor set; n is the full-history onset sweep, not the ~10-12 p3b survivor fires per cell)** | close-to-close approximation; intraday H/L unwired (W0.2)

n=565, immature=12, matured n=553

| State | N | % |
|---|---|---|
| STOPPED | 229 | 41.4% |
| DEAD_MONEY | 53 | 9.6% |
| CUSHIONED | 126 | 22.8% |
| CLEAN_LIFTOFF | 145 | 26.2% |

**Policy R-multiple (pos63):** p10=-1.00 p25=-1.00 p50=0.25 p75=1.54 p90=2.51 mean=0.44

**MFE_R@21d:** p10=0.00 p25=0.28 p50=0.74 p75=1.19 p90=1.66 mean=0.80
**MAE_R@21d:** p10=-1.66 p25=-1.02 p50=-0.46 p75=-0.09 p90=0.00 mean=-0.70
**MFE_R@63d:** p10=0.22 p25=0.66 p50=1.29 p75=2.21 p90=2.99 mean=1.53
**MAE_R@63d:** p10=-2.55 p25=-1.66 p50=-0.80 p75=-0.23 p90=0.00 mean=-1.13

**% never touch −1R (close basis):** 58.2%

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 49.0%

**Era strata (pos63):**
| Era | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| 1999-2014 | 296 | -0.06 | 0.37 | 47.0% |
| 2015-2019 | 134 | 0.37 | 0.44 | 50.0% |
| 2020-2022 | 73 | -0.83 | 0.23 | 47.9% |
| 2023-2026 | 50 | 0.72 | 1.13 | 60.0% |

**Regime strata:**
| Regime | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| High VIX (≥0.6) | 553 | 0.25 | 0.44 | 49.0% |
| Low VIX (<0.6) | 0 | n/a | n/a | n/a |
| SPY above 200d | 245 | 0.36 | 0.50 | 51.4% |
| SPY below 200d | 308 | 0.01 | 0.39 | 47.1% |

**Per-node strata:**
| Node | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| XLB | 82 | 0.29 | 0.49 | 52.4% |
| XLE | 82 | 0.09 | 0.30 | 43.9% |
| XLF | 160 | -0.28 | 0.28 | 42.5% |
| XLK | 229 | 0.38 | 0.58 | 54.1% |

**Exit variant comparison (routing_6 | pos63):**
| Exit | N matured | Median R | Mean R | Win% |
|---|---|---|---|---|
| Fixed horizon | 553 | 0.25 | 0.44 | 49.0% |
| Accel-flip exit | 553 | 0.07 | 0.05 | n/a |
