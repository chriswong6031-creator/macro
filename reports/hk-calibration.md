# Hong Kong / Hang Seng Dashboard — Calibration

Honest, split-half measurement before any UI is built — the same gate used for the
US, China and Bitcoin Vector dashboards. House rule: a signal is shipped with its **measured**
forward-return record; no measured edge -> it ships as *context, not a signal*.

- Confident-regime sample: **2000-04-21 -> 2026-08-07** (6738 days, confidence>0).
- Ladder panel: **162 instruments** (curated constituents + indices + ETF proxies).
- Caveats: the HK macro read piggybacks on China fundamentals (PMI/CPI/PPI/M2), monthly
  back to ~2006-08 (shorter + more regime-unstable than the US); HSI itself is the regional
  risk-on/off proxy, so the THREE-LEG engine here is quad (growth×inflation) + dual liquidity
  (PBoC + Fed-via-peg) + the global risk overlay — the third leg is the one to scrutinise.

## 1. Regime quad -> forward return of the market index (Hang Seng Index)

**Full sample**

| quad_name    |    n |   f21_mean% |   f21_hit% |   f63_mean% |   f63_hit% |
|:-------------|-----:|------------:|-----------:|------------:|-----------:|
| Goldilocks   | 1444 |        1.31 |       57.3 |        4.02 |       65   |
| Growth-scare | 1158 |        0.39 |       56   |        2.45 |       57.2 |
| Reflation    | 1663 |        0.32 |       53   |       -0.39 |       47.4 |
| Stagflation  | 1010 |       -1.02 |       43.8 |       -2.4  |       40.9 |

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
| Goldilocks   | 627 |        0.47 |       54.9 |        1.18 |       56.5 |
| Growth-scare | 635 |        0.79 |       58.7 |        1.96 |       52.3 |
| Reflation    | 856 |        0.58 |       52   |        0.74 |       52.3 |
| Stagflation  | 648 |       -0.52 |       44   |       -0.01 |       41   |

## 2. Liquidity overlay (dual: PBoC stance + Fed-via-peg + southbound flow) -> forward return

| liquidity   |    n |   f21_mean% |   f21_hit% |   f63_mean% |   f63_hit% |
|:------------|-----:|------------:|-----------:|------------:|-----------:|
| contracting |  849 |       -0.79 |       44.8 |       -3.71 |       33.5 |
| expanding   | 3059 |        0.77 |       57.3 |        1.64 |       56.7 |
| neutral     | 2394 |        0.17 |       51.4 |        1.91 |       56.6 |
| unknown     |  436 |        0.86 |       60.3 |        0.84 |       56   |

## 3. Global risk overlay (risk-on/off) -> forward return

_The KEY HK test: HK is the regional risk-on/off proxy, so does the global risk state
differentiate HSI forward returns?_

| risk_state   |    n |   f21_mean% |   f21_hit% |   f63_mean% |   f63_hit% |
|:-------------|-----:|------------:|-----------:|------------:|-----------:|
| Neutral      | 2491 |       -0.12 |       49.7 |        0.36 |       50.1 |
| Risk-off     | 1616 |        0.42 |       54.8 |        0.8  |       53.5 |
| Risk-on      | 2631 |        0.8  |       57.1 |        1.85 |       57.6 |

## 4. Cycle ladder (deep HK panel) — endpoint return + forward drawdown

|                          |     n |   hit_pct |   avg_fwd_pct |   dd_med_pct |   dd_p10_pct |   dd_bad_pct |
|:-------------------------|------:|----------:|--------------:|-------------:|-------------:|-------------:|
| DECLINE                  | 10298 |      53.9 |          1.44 |        -4.84 |       -18.27 |         26.9 |
| BOTTOM WATCH             |  5210 |      47.9 |        125.13 |        -3.93 |       -15.74 |         21.3 |
| TURN SIGNALED            | 17896 |      50.8 |          1.48 |        -4.34 |       -14.5  |         21   |
| FRESH BUY                |  3916 |      52.9 |          1.56 |        -4.09 |       -13.98 |         19.5 |
| RALLY ON                 |  3756 |      53.7 |          1.74 |        -3.95 |       -14.09 |         19.2 |
| TOP WATCH                | 10399 |      52   |          1.73 |        -4.37 |       -14.85 |         21.7 |
| ROLLING OVER             |   345 |      51.6 |          1.45 |        -4.61 |       -15.72 |         23.5 |
| COUNTERTREND BOUNCE      | 16851 |      51   |          1.04 |        -4.54 |       -16.16 |         23.8 |
| BOTTOM WATCH +early-bull |   193 |      45.6 |          0.96 |        -3.52 |       -12.39 |         18.1 |
| BOTTOM WATCH no-early    |  5017 |      48   |        129.91 |        -3.94 |       -15.82 |         21.4 |

## Reading this
- Quad rows whose sign/ranking flips between the two halves are **regime-unstable** ->
  frame as risk context, never a standalone allocation rule.
- The ladder's value is the DRAWDOWN columns (dd_*): scary states with shallow typical
  dips are the asymmetric setups; the avg_fwd alone is U-shaped/misleading (macro D43).
