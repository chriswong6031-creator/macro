# Index-reconstitution forced-flow event study

_Generated 2026-06-21 13:57 UTC. Effective-date events 2019-01-01→ from S&P 500/400/600 PIT membership; SPY-relative; month-clustered HAC-t._

- Adds: **1541** · Deletes: **952** (price-covered subset)
- **Verdict: display-only context (effect decayed)**

## ADD events — SPY-relative abnormal return

| Window | n | mean | hit | HAC-t |
|--|--:|--:|--:|--:|
| pre run-up [-10,-1] | 1254 | 0.0204 | 0.559 | 4.5 |
| post [0,5] | 1309 | -0.0001 | 0.477 | 0.81 |
| post [0,10] | 1309 | -0.0053 | 0.413 | 0.63 |
| post [0,21] | 1305 | -0.0073 | 0.438 | -0.53 |

## DELETE events — SPY-relative abnormal return

| Window | n | mean | hit | HAC-t |
|--|--:|--:|--:|--:|
| post [0,5] | 563 | 0.0081 | 0.508 | 2.14 |
| post [0,10] | 563 | 0.0069 | 0.501 | 2.11 |
| post [0,21] | 560 | 0.0139 | 0.511 | 1.75 |

## ADD post-[0,21] by index

| Index | n | mean | HAC-t |
|--|--:|--:|--:|
| sp500 | 151 | -0.0079 | -0.41 |
| sp400 | 288 | 0.0161 | 1.09 |
| sp600 | 866 | -0.0151 | -1.27 |

## ADD announcement-capture window [-5, 0] — pure vs migration, gross vs net

_Buy at announcement (~5 td before effective), hold through the effective close. Cohorts: {'pure': 1140, 'migration': 381, 'readd': 20}. **announce_gross_scored=True · announce_net_scored=False** (net cost assumed {'sp500': 0.002, 'sp400': 0.006, 'sp600': 0.012})._

| Cohort / index | n | mean | median | hit | HAC-t |
|--|--:|--:|--:|--:|--:|
| PURE gross | 902 | 0.0161 | 0.0108 | 0.582 | 4.59 |
| PURE gross recent (2023-01-01+) | 270 | 0.0204 | 0.0201 | 0.663 | 5.05 |
| MIGRATION gross (control) | 348 | 0.0023 | 0.0006 | 0.509 | 1.09 |
| pure sp500 gross | 77 | 0.0119 | 0.0088 | 0.571 | 1.24 |
| pure sp400 gross | 164 | 0.0192 | 0.0164 | 0.64 | 2.48 |
| pure sp600 gross | 661 | 0.0158 | 0.0092 | 0.569 | 5.22 |
| pure sp500 NET (−0.2%) | 77 | 0.0099 | 0.0068 | 0.545 | 1.05 |
| pure sp400 NET (−0.6%) | 164 | 0.0132 | 0.0104 | 0.598 | 1.96 |
| pure sp600 NET (−1.2%) | 661 | 0.0038 | -0.0028 | 0.477 | 4.13 |

_PURE/net-new ADD announcement→effective [-5,0] run-up is real & recent (+0.0161, t=4.59; recent t=5.05); migrations are ~0 (t=1.09) — so screen to PURE adds. BUT net of small-cap cost the TYPICAL name loses (sp600 net median=-0.0028, hit=0.477) → a NET-OF-COST MIRAGE. Leg ships DISPLAY-ONLY context (fresh pure-add catalysts), scoring gate CLOSED; the net edge lives only in the announcement-overnight gap, which needs intraday opens to validate.._
