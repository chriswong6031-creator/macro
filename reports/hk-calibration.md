# Hong Kong / Hang Seng Dashboard — Calibration

Honest, split-half measurement before any UI is built — the same gate used for the
US, China and Bitcoin Vector dashboards. House rule: a signal is shipped with its **measured**
forward-return record; no measured edge -> it ships as *context, not a signal*.

- Confident-regime sample: **2000-04-21 -> 2026-09-04** (6752 days, confidence>0).
- Ladder panel: **162 instruments** (curated constituents + indices + ETF proxies).
- Caveats: the HK macro read piggybacks on China fundamentals (PMI/CPI/PPI/M2), monthly
  back to ~2006-08 (shorter + more regime-unstable than the US); HSI itself is the regional
  risk-on/off proxy, so the THREE-LEG engine here is quad (growth×inflation) + dual liquidity
  (PBoC + Fed-via-peg) + the global risk overlay — the third leg is the one to scrutinise.

## 1. Regime quad -> forward return of the market index (Hang Seng Index)

**Full sample**

| quad_name    |    n |   f21_mean% |   f21_hit% |   f63_mean% |   f63_hit% |
|:-------------|-----:|------------:|-----------:|------------:|-----------:|
| Goldilocks   | 1482 |        1.4  |       57.3 |        4.11 |       65   |
| Growth-scare | 1125 |        0.2  |       55.2 |        2.28 |       56.2 |
| Reflation    | 1644 |        0.23 |       52.8 |       -0.51 |       46.9 |
| Stagflation  | 1038 |       -0.76 |       45.6 |       -2.09 |       43   |

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
| Goldilocks   | 665 |        0.7  |       54.8 |        1.43 |       56.6 |
| Growth-scare | 602 |        0.47 |       57.5 |        1.6  |       50.2 |
| Reflation    | 837 |        0.4  |       51.5 |        0.48 |       51.1 |
| Stagflation  | 676 |       -0.15 |       46.7 |        0.39 |       44.2 |

## 2. Liquidity overlay (dual: PBoC stance + Fed-via-peg + southbound flow) -> forward return

| liquidity   |    n |   f21_mean% |   f21_hit% |   f63_mean% |   f63_hit% |
|:------------|-----:|------------:|-----------:|------------:|-----------:|
| contracting |  878 |       -0.74 |       45.4 |       -3.62 |       34   |
| expanding   | 3053 |        0.76 |       57.2 |        1.62 |       56.6 |
| neutral     | 2385 |        0.17 |       51.4 |        1.91 |       56.6 |
| unknown     |  436 |        0.86 |       60.3 |        0.84 |       56   |

## 3. Global risk overlay (risk-on/off) -> forward return

_The KEY HK test: HK is the regional risk-on/off proxy, so does the global risk state
differentiate HSI forward returns?_

| risk_state   |    n |   f21_mean% |   f21_hit% |   f63_mean% |   f63_hit% |
|:-------------|-----:|------------:|-----------:|------------:|-----------:|
| Neutral      | 2489 |       -0.11 |       49.9 |        0.34 |       50.1 |
| Risk-off     | 1616 |        0.42 |       54.8 |        0.8  |       53.5 |
| Risk-on      | 2647 |        0.79 |       57   |        1.83 |       57.6 |

## 4. Cycle ladder (deep HK panel) — endpoint return + forward drawdown

|                          |     n |   hit_pct |   avg_fwd_pct |   dd_med_pct |   dd_p10_pct |   dd_bad_pct |
|:-------------------------|------:|----------:|--------------:|-------------:|-------------:|-------------:|
| DECLINE                  | 10306 |      54   |          1.44 |        -4.83 |       -18.26 |         26.9 |
| BOTTOM WATCH             |  5219 |      48   |        124.93 |        -3.93 |       -15.7  |         21.2 |
| TURN SIGNALED            | 17972 |      50.8 |          1.48 |        -4.34 |       -14.52 |         21   |
| FRESH BUY                |  3941 |      52.9 |          1.56 |        -4.08 |       -13.97 |         19.4 |
| RALLY ON                 |  3794 |      53.7 |          1.75 |        -3.95 |       -14.07 |         19.1 |
| TOP WATCH                | 10416 |      52   |          1.73 |        -4.36 |       -14.83 |         21.7 |
| ROLLING OVER             |   347 |      51.9 |          1.55 |        -4.6  |       -15.66 |         23.3 |
| COUNTERTREND BOUNCE      | 16998 |      51   |          1.05 |        -4.52 |       -16.07 |         23.7 |
| BOTTOM WATCH +early-bull |   192 |      46.4 |          0.99 |        -3.52 |       -12.39 |         18.2 |
| BOTTOM WATCH no-early    |  5027 |      48   |        129.66 |        -3.94 |       -15.78 |         21.3 |

## Reading this
- Quad rows whose sign/ranking flips between the two halves are **regime-unstable** ->
  frame as risk context, never a standalone allocation rule.
- The ladder's value is the DRAWDOWN columns (dd_*): scary states with shallow typical
  dips are the asymmetric setups; the avg_fwd alone is U-shaped/misleading (macro D43).
