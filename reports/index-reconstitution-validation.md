# Index-reconstitution forced-flow event study

_Generated 2026-07-01 14:11 UTC. Effective-date events 2019-01-01→ from S&P 500/400/600 PIT membership; SPY-relative; month-clustered HAC-t._

- Adds: **1541** · Deletes: **952** (price-covered subset)
- **Verdict: display-only context (effect decayed)**

## ADD events — SPY-relative abnormal return

| Window | n | mean | hit | HAC-t |
|--|--:|--:|--:|--:|
| pre run-up [-10,-1] | 1253 | 0.0205 | 0.56 | 4.51 |
| post [0,5] | 1309 | 0.0 | 0.476 | 1.08 |
| post [0,10] | 1309 | -0.0052 | 0.413 | 0.7 |
| post [0,21] | 1308 | -0.0069 | 0.44 | -0.13 |

## DELETE events — SPY-relative abnormal return

| Window | n | mean | hit | HAC-t |
|--|--:|--:|--:|--:|
| post [0,5] | 562 | 0.0077 | 0.505 | 2.06 |
| post [0,10] | 562 | 0.0067 | 0.498 | 2.09 |
| post [0,21] | 560 | 0.0139 | 0.512 | 1.78 |

## ADD post-[0,21] by index

| Index | n | mean | HAC-t |
|--|--:|--:|--:|
| sp500 | 153 | -0.0071 | -0.3 |
| sp400 | 288 | 0.0161 | 1.09 |
| sp600 | 867 | -0.0145 | -0.65 |

## ADD announcement-capture window [-5, 0] — pure vs migration, gross vs net

_Buy at announcement (~5 td before effective), hold through the effective close. Cohorts: {'pure': 1140, 'migration': 381, 'readd': 20}. **announce_gross_scored=True · announce_net_scored=False** (net cost assumed {'sp500': 0.002, 'sp400': 0.006, 'sp600': 0.012})._

| Cohort / index | n | mean | median | hit | HAC-t |
|--|--:|--:|--:|--:|--:|
| PURE gross | 902 | 0.0162 | 0.0108 | 0.583 | 4.58 |
| PURE gross recent (2023-01-01+) | 269 | 0.0204 | 0.0202 | 0.665 | 5.04 |
| MIGRATION gross (control) | 347 | 0.0022 | 0.0005 | 0.507 | 1.08 |
| pure sp500 gross | 77 | 0.0119 | 0.0088 | 0.571 | 1.24 |
| pure sp400 gross | 164 | 0.0192 | 0.0164 | 0.64 | 2.48 |
| pure sp600 gross | 661 | 0.016 | 0.0095 | 0.57 | 5.23 |
| pure sp500 NET (−0.2%) | 77 | 0.0099 | 0.0068 | 0.545 | 1.05 |
| pure sp400 NET (−0.6%) | 164 | 0.0132 | 0.0104 | 0.598 | 1.96 |
| pure sp600 NET (−1.2%) | 661 | 0.004 | -0.0025 | 0.478 | 4.14 |

_PURE/net-new ADD announcement→effective [-5,0] run-up is real & recent (+0.0162, t=4.58; recent t=5.04); migrations are ~0 (t=1.08) — so screen to PURE adds. BUT net of small-cap cost the TYPICAL name loses (sp600 net median=-0.0025, hit=0.478) → a NET-OF-COST MIRAGE. Leg ships DISPLAY-ONLY context (fresh pure-add catalysts), scoring gate CLOSED; the net edge lives only in the announcement-overnight gap, which needs intraday opens to validate.._
