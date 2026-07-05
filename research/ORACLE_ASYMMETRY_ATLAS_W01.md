# Oracle Asymmetry Atlas — W0.1

**Program:** Oracle Turn Asymmetry | Wave W0.1 — Asymmetry Re-Grade
**Date:** 2026-07-05
**Nature:** DESCRIPTIVE measurement only. No new signals. No claim language.
**Grading basis:** close-to-close approximation; intraday H/L unwired (W0.2)
**Routing tables:** n≤12 descriptive only.

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

*Detection lag (exhaust_date − accel_flip_date): n=356 mean=13.2d p50=5.0d p75=20.0d p90=39.0d. Exhaust-exit R-multiples are a FLOOR vs reflex exits.*

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

*Detection lag (exhaust_date − accel_flip_date): n=356 mean=13.2d p50=5.0d p75=20.0d p90=39.0d. Exhaust-exit R-multiples are a FLOOR vs reflex exits.*


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

*Detection lag (exhaust_date − accel_flip_date): n=390 mean=6.8d p50=2.0d p75=9.0d p90=19.1d. Exhaust-exit R-multiples are a FLOOR vs reflex exits.*

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

*Detection lag (exhaust_date − accel_flip_date): n=390 mean=6.8d p50=2.0d p75=9.0d p90=19.1d. Exhaust-exit R-multiples are a FLOOR vs reflex exits.*


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

n=608, immature=1, matured n=607

| State | N | % |
|---|---|---|
| STOPPED | 96 | 15.8% |
| DEAD_MONEY | 369 | 60.8% |
| CUSHIONED | 0 | 0.0% |
| CLEAN_LIFTOFF | 142 | 23.4% |

**Policy R-multiple (rot21):** p10=-1.00 p25=-0.37 p50=0.25 p75=0.80 p90=1.23 mean=0.23

**MFE_R@21d:** p10=0.07 p25=0.29 p50=0.60 p75=0.96 p90=1.40 mean=0.69
**MAE_R@21d:** p10=-1.34 p25=-0.78 p50=-0.30 p75=-0.07 p90=0.00 mean=-0.55
**MFE_R@63d:** p10=0.23 p25=0.57 p50=1.11 p75=1.88 p90=2.64 mean=1.33
**MAE_R@63d:** p10=-2.25 p25=-1.42 p50=-0.60 p75=-0.21 p90=0.00 mean=-0.96

**% never touch −1R (close basis):** 84.2%

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 23.4%

**Era strata (rot21):**
| Era | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| 1999-2014 | 338 | 0.17 | 0.18 | 22.5% |
| 2015-2019 | 108 | 0.31 | 0.21 | 18.5% |
| 2020-2022 | 76 | 0.55 | 0.40 | 26.3% |
| 2023-2026 | 85 | 0.39 | 0.29 | 30.6% |

**Regime strata:**
| Regime | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| High VIX (≥0.6) | 275 | 0.35 | 0.28 | 24.4% |
| Low VIX (<0.6) | 327 | 0.20 | 0.20 | 22.9% |
| SPY above 200d | 377 | 0.29 | 0.27 | 24.4% |
| SPY below 200d | 230 | 0.23 | 0.16 | 21.7% |

**Per-node strata:**
| Node | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| XLB | 57 | 0.39 | 0.29 | 19.3% |
| XLC | 17 | 0.20 | 0.11 | 17.6% |
| XLE | 67 | 0.17 | 0.16 | 17.9% |
| XLF | 68 | 0.15 | 0.23 | 26.5% |
| XLI | 66 | 0.28 | 0.36 | 28.8% |
| XLK | 68 | -0.02 | 0.15 | 23.5% |
| XLP | 59 | 0.36 | 0.22 | 23.7% |
| XLRE | 22 | 0.40 | 0.22 | 27.3% |
| XLU | 57 | 0.51 | 0.31 | 21.1% |
| XLV | 61 | 0.15 | 0.20 | 27.9% |
| XLY | 65 | 0.24 | 0.18 | 21.5% |

**Exit variant comparison (washout_p8 | rot21):**
| Exit | N matured | Median R | Mean R | Win% |
|---|---|---|---|---|
| Fixed horizon | 1246 | 0.26 | 0.23 | 23.8% |
| Accel-flip exit | 1246 | 0.04 | 0.10 | n/a |

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

n=608, immature=11, matured n=597

| State | N | % |
|---|---|---|
| STOPPED | 198 | 33.2% |
| DEAD_MONEY | 112 | 18.8% |
| CUSHIONED | 172 | 28.8% |
| CLEAN_LIFTOFF | 115 | 19.3% |

**Policy R-multiple (pos63):** p10=-1.00 p25=-1.00 p50=0.31 p75=1.26 p90=2.10 mean=0.39

**MFE_R@21d:** p10=0.07 p25=0.28 p50=0.60 p75=0.95 p90=1.40 mean=0.69
**MAE_R@21d:** p10=-1.37 p25=-0.78 p50=-0.31 p75=-0.07 p90=0.00 mean=-0.56
**MFE_R@63d:** p10=0.23 p25=0.57 p50=1.11 p75=1.88 p90=2.64 mean=1.33
**MAE_R@63d:** p10=-2.25 p25=-1.42 p50=-0.60 p75=-0.21 p90=0.00 mean=-0.96

**% never touch −1R (close basis):** 66.7%

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 48.1%

**Era strata (pos63):**
| Era | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| 1999-2014 | 338 | 0.23 | 0.38 | 48.5% |
| 2015-2019 | 108 | 0.44 | 0.36 | 44.4% |
| 2020-2022 | 76 | 0.39 | 0.35 | 48.7% |
| 2023-2026 | 75 | 0.47 | 0.53 | 50.7% |

**Regime strata:**
| Regime | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| High VIX (≥0.6) | 268 | 0.36 | 0.37 | 47.8% |
| Low VIX (<0.6) | 324 | 0.30 | 0.43 | 49.1% |
| SPY above 200d | 373 | 0.40 | 0.48 | 51.5% |
| SPY below 200d | 224 | 0.22 | 0.25 | 42.4% |

**Per-node strata:**
| Node | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| XLB | 56 | 0.21 | 0.35 | 53.6% |
| XLC | 16 | -0.21 | 0.06 | 43.8% |
| XLE | 66 | 0.47 | 0.41 | 47.0% |
| XLF | 68 | 0.22 | 0.42 | 42.6% |
| XLI | 65 | 0.36 | 0.38 | 50.8% |
| XLK | 67 | 0.23 | 0.36 | 46.3% |
| XLP | 58 | 0.26 | 0.44 | 50.0% |
| XLRE | 21 | 0.47 | 0.33 | 42.9% |
| XLU | 57 | 0.62 | 0.62 | 57.9% |
| XLV | 59 | 0.42 | 0.27 | 40.7% |
| XLY | 64 | 0.41 | 0.38 | 48.4% |

**Exit variant comparison (washout_p8 | pos63):**
| Exit | N matured | Median R | Mean R | Win% |
|---|---|---|---|---|
| Fixed horizon | 1226 | 0.30 | 0.39 | 48.1% |
| Accel-flip exit | 1226 | 0.03 | 0.09 | n/a |


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

n=259, immature=2, matured n=257

| State | N | % |
|---|---|---|
| STOPPED | 34 | 13.2% |
| DEAD_MONEY | 133 | 51.8% |
| CUSHIONED | 0 | 0.0% |
| CLEAN_LIFTOFF | 90 | 35.0% |

**Policy R-multiple (rot21):** p10=-1.00 p25=-0.12 p50=0.43 p75=0.99 p90=1.46 mean=0.41

**MFE_R@21d:** p10=0.12 p25=0.43 p50=0.83 p75=1.24 p90=1.65 mean=0.87
**MAE_R@21d:** p10=-1.10 p25=-0.66 p50=-0.28 p75=-0.02 p90=0.00 mean=-0.47
**MFE_R@63d:** p10=0.36 p25=0.81 p50=1.39 p75=2.23 p90=3.01 mean=1.59
**MAE_R@63d:** p10=-1.90 p25=-1.01 p50=-0.49 p75=-0.14 p90=0.00 mean=-0.76

**% never touch −1R (close basis):** 86.8%

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 35.0%

**Era strata (rot21):**
| Era | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| 1999-2014 | 138 | 0.51 | 0.38 | 32.6% |
| 2015-2019 | 43 | 0.33 | 0.38 | 27.9% |
| 2020-2022 | 38 | 0.44 | 0.54 | 42.1% |
| 2023-2026 | 38 | 0.44 | 0.44 | 44.7% |

**Regime strata:**
| Regime | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| High VIX (≥0.6) | 176 | 0.40 | 0.29 | 29.0% |
| Low VIX (<0.6) | 81 | 0.72 | 0.67 | 48.1% |
| SPY above 200d | 124 | 0.54 | 0.52 | 37.1% |
| SPY below 200d | 133 | 0.41 | 0.31 | 33.1% |

**Per-node strata:**
| Node | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| XLB | 45 | 0.62 | 0.44 | 37.8% |
| XLE | 43 | 0.42 | 0.36 | 32.6% |
| XLF | 52 | 0.39 | 0.39 | 34.6% |
| XLI | 35 | 0.88 | 0.58 | 48.6% |
| XLK | 32 | 0.42 | 0.34 | 25.0% |
| XLP | 11 | 0.43 | 0.43 | 36.4% |
| XLRE | 9 | 0.60 | 0.75 | 44.4% |
| XLU | 14 | 0.48 | 0.44 | 35.7% |
| XLV | 16 | 0.19 | 0.06 | 18.8% |

**Exit variant comparison (a15 | rot21):**
| Exit | N matured | Median R | Mean R | Win% |
|---|---|---|---|---|
| Fixed horizon | 2614 | 0.43 | 0.41 | 31.8% |
| Accel-flip exit | 2614 | 0.08 | 0.16 | n/a |

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

n=259, immature=2, matured n=257

| State | N | % |
|---|---|---|
| STOPPED | 66 | 25.7% |
| DEAD_MONEY | 45 | 17.5% |
| CUSHIONED | 72 | 28.0% |
| CLEAN_LIFTOFF | 74 | 28.8% |

**Policy R-multiple (pos63):** p10=-1.00 p25=-1.00 p50=0.62 p75=1.67 p90=2.54 mean=0.71

**MFE_R@21d:** p10=0.12 p25=0.43 p50=0.83 p75=1.24 p90=1.65 mean=0.87
**MAE_R@21d:** p10=-1.10 p25=-0.66 p50=-0.28 p75=-0.02 p90=0.00 mean=-0.47
**MFE_R@63d:** p10=0.36 p25=0.81 p50=1.39 p75=2.23 p90=3.01 mean=1.59
**MAE_R@63d:** p10=-1.90 p25=-1.01 p50=-0.49 p75=-0.14 p90=0.00 mean=-0.76

**% never touch −1R (close basis):** 74.3%

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 56.8%

**Era strata (pos63):**
| Era | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| 1999-2014 | 138 | 0.58 | 0.66 | 56.5% |
| 2015-2019 | 43 | 0.62 | 0.65 | 53.5% |
| 2020-2022 | 38 | 0.78 | 0.48 | 57.9% |
| 2023-2026 | 38 | 0.61 | 1.19 | 60.5% |

**Regime strata:**
| Regime | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| High VIX (≥0.6) | 176 | 0.56 | 0.55 | 51.1% |
| Low VIX (<0.6) | 81 | 1.19 | 1.07 | 69.1% |
| SPY above 200d | 124 | 0.70 | 0.86 | 63.7% |
| SPY below 200d | 133 | 0.56 | 0.57 | 50.4% |

**Per-node strata:**
| Node | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| XLB | 45 | 0.53 | 0.70 | 62.2% |
| XLE | 43 | 0.57 | 0.72 | 60.5% |
| XLF | 52 | 0.27 | 0.35 | 46.2% |
| XLI | 35 | 0.50 | 0.88 | 62.9% |
| XLK | 32 | 0.94 | 0.81 | 56.2% |
| XLP | 11 | 0.75 | 1.03 | 54.5% |
| XLRE | 9 | 1.10 | 1.04 | 55.6% |
| XLU | 14 | 1.19 | 1.18 | 64.3% |
| XLV | 16 | 0.35 | 0.53 | 50.0% |

**Exit variant comparison (a15 | pos63):**
| Exit | N matured | Median R | Mean R | Win% |
|---|---|---|---|---|
| Fixed horizon | 2608 | 0.58 | 0.63 | 52.9% |
| Accel-flip exit | 2608 | 0.08 | 0.15 | n/a |


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

n=52, immature=2, matured n=50

| State | N | % |
|---|---|---|
| STOPPED | 12 | 24.0% |
| DEAD_MONEY | 21 | 42.0% |
| CUSHIONED | 0 | 0.0% |
| CLEAN_LIFTOFF | 17 | 34.0% |

**Policy R-multiple (rot21):** p10=-1.00 p25=-0.56 p50=0.22 p75=0.91 p90=1.24 mean=0.19

**MFE_R@21d:** p10=0.01 p25=0.35 p50=0.71 p75=1.19 p90=1.50 mean=0.76
**MAE_R@21d:** p10=-1.61 p25=-0.99 p50=-0.48 p75=-0.15 p90=0.00 mean=-0.70
**MFE_R@63d:** p10=0.31 p25=0.51 p50=1.30 p75=1.94 p90=2.90 mean=1.44
**MAE_R@63d:** p10=-2.25 p25=-1.20 p50=-0.60 p75=-0.22 p90=-0.08 mean=-1.04

**% never touch −1R (close basis):** 76.0%

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 34.0%

**Era strata (rot21):**
| Era | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| 1999-2014 | 21 | -0.19 | -0.08 | 19.0% |
| 2015-2019 | 8 | 0.20 | 0.13 | 25.0% |
| 2020-2022 | 14 | 0.79 | 0.38 | 42.9% |
| 2023-2026 | 7 | 0.45 | 0.67 | 71.4% |

**Regime strata:**
| Regime | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| High VIX (≥0.6) | 39 | 0.21 | 0.19 | 33.3% |
| Low VIX (<0.6) | 11 | 0.32 | 0.19 | 36.4% |
| SPY above 200d | 25 | 0.32 | 0.13 | 40.0% |
| SPY below 200d | 25 | 0.21 | 0.25 | 28.0% |

**Per-node strata:**
| Node | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| XLB | 14 | -0.19 | 0.10 | 35.7% |
| XLE | 17 | 0.14 | 0.03 | 23.5% |
| XLRE | 11 | 0.83 | 0.49 | 45.5% |
| XLU | 8 | 0.45 | 0.25 | 37.5% |

**Exit variant comparison (a9 | rot21):**
| Exit | N matured | Median R | Mean R | Win% |
|---|---|---|---|---|
| Fixed horizon | 488 | 0.32 | 0.26 | 26.4% |
| Accel-flip exit | 488 | 0.03 | 0.05 | n/a |

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

n=52, immature=2, matured n=50

| State | N | % |
|---|---|---|
| STOPPED | 18 | 36.0% |
| DEAD_MONEY | 7 | 14.0% |
| CUSHIONED | 15 | 30.0% |
| CLEAN_LIFTOFF | 10 | 20.0% |

**Policy R-multiple (pos63):** p10=-1.00 p25=-1.00 p50=0.30 p75=1.16 p90=2.38 mean=0.44

**MFE_R@21d:** p10=0.01 p25=0.35 p50=0.71 p75=1.19 p90=1.50 mean=0.76
**MAE_R@21d:** p10=-1.61 p25=-0.99 p50=-0.48 p75=-0.15 p90=0.00 mean=-0.70
**MFE_R@63d:** p10=0.31 p25=0.51 p50=1.30 p75=1.94 p90=2.90 mean=1.44
**MAE_R@63d:** p10=-2.25 p25=-1.20 p50=-0.60 p75=-0.22 p90=-0.08 mean=-1.04

**% never touch −1R (close basis):** 64.0%

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 50.0%

**Era strata (pos63):**
| Era | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| 1999-2014 | 21 | 0.01 | -0.07 | 28.6% |
| 2015-2019 | 8 | 0.00 | 0.41 | 50.0% |
| 2020-2022 | 14 | 1.11 | 0.78 | 64.3% |
| 2023-2026 | 7 | 0.57 | 1.29 | 85.7% |

**Regime strata:**
| Regime | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| High VIX (≥0.6) | 39 | 0.29 | 0.24 | 48.7% |
| Low VIX (<0.6) | 11 | 0.52 | 1.12 | 54.5% |
| SPY above 200d | 25 | 0.52 | 0.45 | 52.0% |
| SPY below 200d | 25 | 0.29 | 0.43 | 48.0% |

**Per-node strata:**
| Node | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| XLB | 14 | 0.15 | 0.25 | 35.7% |
| XLE | 17 | 0.09 | 0.06 | 41.2% |
| XLRE | 11 | 1.17 | 1.20 | 63.6% |
| XLU | 8 | 0.53 | 0.51 | 75.0% |

**Exit variant comparison (a9 | pos63):**
| Exit | N matured | Median R | Mean R | Win% |
|---|---|---|---|---|
| Fixed horizon | 488 | 0.20 | 0.33 | 46.9% |
| Accel-flip exit | 488 | 0.03 | 0.05 | n/a |


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

n=50, immature=2, matured n=48

| State | N | % |
|---|---|---|
| STOPPED | 9 | 18.8% |
| DEAD_MONEY | 24 | 50.0% |
| CUSHIONED | 0 | 0.0% |
| CLEAN_LIFTOFF | 15 | 31.2% |

**Policy R-multiple (rot21):** p10=-1.00 p25=-0.40 p50=0.42 p75=0.89 p90=1.25 mean=0.29

**MFE_R@21d:** p10=0.21 p25=0.46 p50=0.78 p75=1.09 p90=1.46 mean=0.80
**MAE_R@21d:** p10=-1.64 p25=-0.82 p50=-0.37 p75=-0.12 p90=0.00 mean=-0.67
**MFE_R@63d:** p10=0.41 p25=0.63 p50=1.20 p75=1.96 p90=2.90 mean=1.45
**MAE_R@63d:** p10=-2.20 p25=-1.12 p50=-0.61 p75=-0.21 p90=-0.04 mean=-1.00

**% never touch −1R (close basis):** 81.2%

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 31.2%

**Era strata (rot21):**
| Era | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| 1999-2014 | 21 | 0.14 | 0.12 | 19.0% |
| 2015-2019 | 7 | 0.18 | 0.08 | 14.3% |
| 2020-2022 | 14 | 0.79 | 0.43 | 42.9% |
| 2023-2026 | 6 | 0.84 | 0.79 | 66.7% |

**Regime strata:**
| Regime | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| High VIX (≥0.6) | 38 | 0.46 | 0.31 | 31.6% |
| Low VIX (<0.6) | 10 | 0.11 | 0.22 | 30.0% |
| SPY above 200d | 24 | 0.38 | 0.30 | 37.5% |
| SPY below 200d | 24 | 0.44 | 0.28 | 25.0% |

**Per-node strata:**
| Node | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| XLB | 13 | 0.05 | 0.20 | 30.8% |
| XLE | 16 | 0.32 | 0.18 | 18.8% |
| XLRE | 11 | 0.83 | 0.51 | 45.5% |
| XLU | 8 | 0.73 | 0.35 | 37.5% |

**Exit variant comparison (a17 | rot21):**
| Exit | N matured | Median R | Mean R | Win% |
|---|---|---|---|---|
| Fixed horizon | 310 | 0.43 | 0.31 | 30.3% |
| Accel-flip exit | 310 | 0.07 | 0.05 | n/a |

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

n=50, immature=2, matured n=48

| State | N | % |
|---|---|---|
| STOPPED | 13 | 27.1% |
| DEAD_MONEY | 11 | 22.9% |
| CUSHIONED | 14 | 29.2% |
| CLEAN_LIFTOFF | 10 | 20.8% |

**Policy R-multiple (pos63):** p10=-1.00 p25=-1.00 p50=0.50 p75=1.23 p90=2.32 mean=0.55

**MFE_R@21d:** p10=0.21 p25=0.46 p50=0.78 p75=1.09 p90=1.46 mean=0.80
**MAE_R@21d:** p10=-1.64 p25=-0.82 p50=-0.37 p75=-0.12 p90=0.00 mean=-0.67
**MFE_R@63d:** p10=0.41 p25=0.63 p50=1.20 p75=1.96 p90=2.90 mean=1.45
**MAE_R@63d:** p10=-2.20 p25=-1.12 p50=-0.61 p75=-0.21 p90=-0.04 mean=-1.00

**% never touch −1R (close basis):** 72.9%

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 50.0%

**Era strata (pos63):**
| Era | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| 1999-2014 | 21 | 0.31 | 0.15 | 28.6% |
| 2015-2019 | 7 | -0.12 | 0.31 | 42.9% |
| 2020-2022 | 14 | 1.11 | 0.76 | 64.3% |
| 2023-2026 | 6 | 0.76 | 1.68 | 100.0% |

**Regime strata:**
| Regime | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| High VIX (≥0.6) | 38 | 0.45 | 0.34 | 47.4% |
| Low VIX (<0.6) | 10 | 1.22 | 1.34 | 60.0% |
| SPY above 200d | 24 | 0.57 | 0.71 | 54.2% |
| SPY below 200d | 24 | 0.30 | 0.38 | 45.8% |

**Per-node strata:**
| Node | N | Median R | Mean R | Win% |
|---|---|---|---|---|
| XLB | 13 | 0.29 | 0.33 | 30.8% |
| XLE | 16 | 0.49 | 0.31 | 43.8% |
| XLRE | 11 | 1.17 | 1.20 | 63.6% |
| XLU | 8 | 0.55 | 0.48 | 75.0% |

**Exit variant comparison (a17 | pos63):**
| Exit | N matured | Median R | Mean R | Win% |
|---|---|---|---|---|
| Fixed horizon | 310 | 0.33 | 0.41 | 48.1% |
| Accel-flip exit | 310 | 0.07 | 0.05 | n/a |


## Family: routing_6

### routing_6 | rot21
**n≤12 descriptive only** | close-to-close approximation; intraday H/L unwired (W0.2)

n=565, immature=11, matured n=554

| State | N | % |
|---|---|---|
| STOPPED | 138 | 24.9% |
| DEAD_MONEY | 233 | 42.1% |
| CUSHIONED | 0 | 0.0% |
| CLEAN_LIFTOFF | 183 | 33.0% |

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
**n≤12 descriptive only** | close-to-close approximation; intraday H/L unwired (W0.2)

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
