# Index-reconstitution forced-flow event study

_Generated 2026-08-01 08:31 UTC. Effective-date events 2019-01-01→ from S&P 500/400/600 PIT membership; SPY-relative; month-clustered HAC-t._

- Adds: **1541** · Deletes: **952** (price-covered subset)
- **Verdict: display-only context (effect decayed)**

## ADD events — SPY-relative abnormal return

| Window | n | mean | hit | HAC-t |
|--|--:|--:|--:|--:|
| pre run-up [-10,-1] | 1223 | 0.0202 | 0.559 | 4.43 |
| post [0,5] | 1279 | -0.0003 | 0.477 | 1.27 |
| post [0,10] | 1279 | -0.0058 | 0.412 | 0.63 |
| post [0,21] | 1279 | -0.0074 | 0.436 | -0.25 |

## DELETE events — SPY-relative abnormal return

| Window | n | mean | hit | HAC-t |
|--|--:|--:|--:|--:|
| post [0,5] | 547 | 0.0069 | 0.503 | 2.13 |
| post [0,10] | 547 | 0.0055 | 0.492 | 2.04 |
| post [0,21] | 547 | 0.0118 | 0.505 | 1.63 |

## ADD post-[0,21] by index

| Index | n | mean | HAC-t |
|--|--:|--:|--:|
| sp500 | 151 | -0.0065 | -0.07 |
| sp400 | 283 | 0.0152 | 1.04 |
| sp600 | 845 | -0.0151 | -1.08 |

## ADD announcement-capture window [-5, 0] — pure vs migration, gross vs net

_Buy at announcement (~5 td before effective), hold through the effective close. Cohorts: {'pure': 1140, 'migration': 381, 'readd': 20}. **announce_gross_scored=True · announce_net_scored=False** (net cost assumed {'sp500': 0.002, 'sp400': 0.006, 'sp600': 0.012})._

| Cohort / index | n | mean | median | hit | HAC-t |
|--|--:|--:|--:|--:|--:|
| PURE gross | 877 | 0.0164 | 0.0108 | 0.587 | 4.63 |
| PURE gross recent (2023-01-01+) | 266 | 0.0199 | 0.0198 | 0.662 | 5.02 |
| MIGRATION gross (control) | 341 | 0.0025 | 0.0007 | 0.51 | 1.08 |
| pure sp500 gross | 76 | 0.0112 | 0.0075 | 0.566 | 1.13 |
| pure sp400 gross | 163 | 0.017 | 0.0164 | 0.638 | 2.43 |
| pure sp600 gross | 638 | 0.0169 | 0.0102 | 0.577 | 5.32 |
| pure sp500 NET (−0.2%) | 76 | 0.0092 | 0.0055 | 0.539 | 0.95 |
| pure sp400 NET (−0.6%) | 163 | 0.011 | 0.0104 | 0.595 | 1.89 |
| pure sp600 NET (−1.2%) | 638 | 0.0049 | -0.0018 | 0.481 | 4.22 |

_PURE/net-new ADD announcement→effective [-5,0] run-up is real & recent (+0.0164, t=4.63; recent t=5.02); migrations are ~0 (t=1.08) — so screen to PURE adds. BUT net of small-cap cost the TYPICAL name loses (sp600 net median=-0.0018, hit=0.481) → a NET-OF-COST MIRAGE. Leg ships DISPLAY-ONLY context (fresh pure-add catalysts), scoring gate CLOSED; the net edge lives only in the announcement-overnight gap, which needs intraday opens to validate.._
