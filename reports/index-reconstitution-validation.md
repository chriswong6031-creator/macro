# Index-reconstitution forced-flow event study

_Generated 2026-06-21 11:50 UTC. Effective-date events 2019-01-01→ from S&P 500/400/600 PIT membership; SPY-relative; month-clustered HAC-t._

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

_the pre-effective ADD run-up is still significant (+0.0204, t=4.5), but it is front-run INTO the effective date and REVERSES after — so a surfaced (already-effective) add has no tradeable post-effective edge. → leg DORMANT (would need an announcement feed to trade the run-up)._
