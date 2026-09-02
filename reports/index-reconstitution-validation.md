# Index-reconstitution forced-flow event study

_Generated 2026-09-01 11:16 UTC. Effective-date events 2019-01-01→ from S&P 500/400/600 PIT membership; SPY-relative; month-clustered HAC-t._

- Adds: **1541** · Deletes: **952** (price-covered subset)
- **Verdict: display-only context (effect decayed)**

## ADD events — SPY-relative abnormal return

| Window | n | mean | hit | HAC-t |
|--|--:|--:|--:|--:|
| pre run-up [-10,-1] | 1218 | 0.0203 | 0.561 | 4.36 |
| post [0,5] | 1277 | -0.0005 | 0.475 | 1.27 |
| post [0,10] | 1277 | -0.0061 | 0.412 | 0.55 |
| post [0,21] | 1277 | -0.0081 | 0.437 | -0.34 |

## DELETE events — SPY-relative abnormal return

| Window | n | mean | hit | HAC-t |
|--|--:|--:|--:|--:|
| post [0,5] | 550 | 0.0058 | 0.496 | 2.03 |
| post [0,10] | 550 | 0.0031 | 0.485 | 1.83 |
| post [0,21] | 550 | 0.0077 | 0.5 | 1.39 |

## ADD post-[0,21] by index

| Index | n | mean | HAC-t |
|--|--:|--:|--:|
| sp500 | 152 | -0.0066 | -0.09 |
| sp400 | 282 | 0.0154 | 1.04 |
| sp600 | 843 | -0.0163 | -1.22 |

## ADD announcement-capture window [-5, 0] — pure vs migration, gross vs net

_Buy at announcement (~5 td before effective), hold through the effective close. Cohorts: {'pure': 1140, 'migration': 381, 'readd': 20}. **announce_gross_scored=True · announce_net_scored=False** (net cost assumed {'sp500': 0.002, 'sp400': 0.006, 'sp600': 0.012})._

| Cohort / index | n | mean | median | hit | HAC-t |
|--|--:|--:|--:|--:|--:|
| PURE gross | 874 | 0.0167 | 0.0111 | 0.588 | 4.67 |
| PURE gross recent (2023-01-01+) | 266 | 0.0199 | 0.0198 | 0.662 | 5.02 |
| MIGRATION gross (control) | 339 | 0.0018 | 0.0005 | 0.507 | 1.07 |
| pure sp500 gross | 77 | 0.0115 | 0.0088 | 0.571 | 1.18 |
| pure sp400 gross | 162 | 0.017 | 0.0163 | 0.636 | 2.39 |
| pure sp600 gross | 635 | 0.0172 | 0.0102 | 0.578 | 5.32 |
| pure sp500 NET (−0.2%) | 77 | 0.0095 | 0.0068 | 0.545 | 0.99 |
| pure sp400 NET (−0.6%) | 162 | 0.011 | 0.0103 | 0.593 | 1.86 |
| pure sp600 NET (−1.2%) | 635 | 0.0052 | -0.0018 | 0.483 | 4.22 |

_PURE/net-new ADD announcement→effective [-5,0] run-up is real & recent (+0.0167, t=4.67; recent t=5.02); migrations are ~0 (t=1.07) — so screen to PURE adds. BUT net of small-cap cost the TYPICAL name loses (sp600 net median=-0.0018, hit=0.483) → a NET-OF-COST MIRAGE. Leg ships DISPLAY-ONLY context (fresh pure-add catalysts), scoring gate CLOSED; the net edge lives only in the announcement-overnight gap, which needs intraday opens to validate.._
