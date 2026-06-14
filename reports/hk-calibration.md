# Hong Kong / Hang Seng Dashboard — Calibration

Honest, split-half measurement before any UI is built — the same gate used for the
US, China and Bitcoin Vector dashboards. House rule: a signal is shipped with its **measured**
forward-return record; no measured edge -> it ships as *context, not a signal*.

- Confident-regime sample: **2000-04-21 -> 2026-06-12** (6692 days, confidence>0).
- Ladder panel: **78 instruments** (curated constituents + indices + ETF proxies).
- Caveats: the HK macro read piggybacks on China fundamentals (PMI/CPI/PPI/M2), monthly
  back to ~2006-08 (shorter + more regime-unstable than the US); HSI itself is the regional
  risk-on/off proxy, so the THREE-LEG engine here is quad (growth×inflation) + dual liquidity
  (PBoC + Fed-via-peg) + the global risk overlay — the third leg is the one to scrutinise.

## 1. Regime quad -> forward return of the market index (Hang Seng Index)

**Full sample**

| quad_name    |    n |   f21_mean% |   f21_hit% |   f63_mean% |   f63_hit% |
|:-------------|-----:|------------:|-----------:|------------:|-----------:|
| Goldilocks   | 1474 |        1.34 |       56.9 |        3.95 |       64.3 |
| Growth-scare | 1105 |        0.29 |       56   |        2.45 |       57   |
| Reflation    | 1645 |        0.24 |       52.9 |       -0.4  |       47.9 |
| Stagflation  | 1005 |       -0.86 |       44.7 |       -2.14 |       42.9 |

**Split-half robustness** (a quad's edge is only trustworthy if it survives both halves)

_Pre-split_

| quad_name    |   n |   f21_mean% |   f21_hit% |   f63_mean% |   f63_hit% |
|:-------------|----:|------------:|-----------:|------------:|-----------:|
| Goldilocks   | 817 |        1.95 |       59.2 |        6.21 |       71.6 |
| Growth-scare | 523 |       -0.11 |       52.6 |        3.05 |       63.1 |
| Reflation    | 807 |        0.05 |       54.2 |       -1.53 |       42.5 |
| Stagflation  | 362 |       -1.89 |       43.4 |       -6.49 |       40.9 |

_Post-split_

| quad_name    |   n |   f21_mean% |   f21_hit% |   f63_mean% |   f63_hit% |
|:-------------|----:|------------:|-----------:|------------:|-----------:|
| Goldilocks   | 657 |        0.57 |       53.9 |        1.15 |       55.3 |
| Growth-scare | 582 |        0.64 |       59.1 |        1.91 |       51.5 |
| Reflation    | 838 |        0.43 |       51.7 |        0.75 |       53.4 |
| Stagflation  | 643 |       -0.27 |       45.5 |        0.41 |       44   |

## 2. Liquidity overlay (dual: PBoC stance + Fed-via-peg + southbound flow) -> forward return

| liquidity   |    n |   f21_mean% |   f21_hit% |   f63_mean% |   f63_hit% |
|:------------|-----:|------------:|-----------:|------------:|-----------:|
| contracting |  913 |       -0.41 |       49.4 |       -2.34 |       42.6 |
| expanding   | 2719 |        0.52 |       54.7 |        1.24 |       53.9 |
| neutral     | 2624 |        0.39 |       53.4 |        2.08 |       58   |
| unknown     |  436 |        0.86 |       60.3 |        0.84 |       56   |

## 3. Global risk overlay (risk-on/off) -> forward return

_The KEY HK test: HK is the regional risk-on/off proxy, so does the global risk state
differentiate HSI forward returns?_

| risk_state   |    n |   f21_mean% |   f21_hit% |   f63_mean% |   f63_hit% |
|:-------------|-----:|------------:|-----------:|------------:|-----------:|
| Neutral      | 2464 |       -0.14 |       49.7 |        0.36 |       50.2 |
| Risk-off     | 1609 |        0.37 |       54.6 |        0.84 |       53.8 |
| Risk-on      | 2619 |        0.84 |       57.3 |        1.9  |       58.1 |

## 4. Cycle ladder (deep HK panel) — endpoint return + forward drawdown

|                          |    n |   hit_pct |   avg_fwd_pct |   dd_med_pct |   dd_p10_pct |   dd_bad_pct |
|:-------------------------|-----:|----------:|--------------:|-------------:|-------------:|-------------:|
| DECLINE                  | 5100 |      55.1 |          1.4  |        -4.27 |       -16.56 |         23.6 |
| BOTTOM WATCH             | 5775 |      51.8 |          1.08 |        -4.03 |       -14.21 |         19.6 |
| TURN SIGNALED            | 7357 |      51.2 |          1.17 |        -3.96 |       -13.57 |         18.1 |
| FRESH BUY                | 2249 |      50.7 |          1.34 |        -4.13 |       -13.33 |         18.1 |
| RALLY ON                 | 5596 |      53.5 |          1.64 |        -3.5  |       -13.56 |         17.8 |
| TOP WATCH                | 3767 |      54.4 |          1.63 |        -3.7  |       -13.17 |         17   |
| ROLLING OVER             | 1436 |      51.3 |          1.13 |        -3.96 |       -14.55 |         19.4 |
| COUNTERTREND BOUNCE      | 4886 |      53.1 |          1.08 |        -3.94 |       -14.46 |         20.7 |
| BOTTOM WATCH +early-bull |  264 |      50.4 |          0.69 |        -4.89 |       -13.91 |         22.3 |
| BOTTOM WATCH no-early    | 5511 |      51.8 |          1.1  |        -4    |       -14.21 |         19.5 |

## Reading this
- Quad rows whose sign/ranking flips between the two halves are **regime-unstable** ->
  frame as risk context, never a standalone allocation rule.
- The ladder's value is the DRAWDOWN columns (dd_*): scary states with shallow typical
  dips are the asymmetric setups; the avg_fwd alone is U-shaped/misleading (macro D43).
