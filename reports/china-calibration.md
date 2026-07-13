# China A-share Dashboard — Calibration (Phase-2 checkpoint)

Honest, split-half measurement before any UI is built — the same gate used for the
US and Bitcoin Vector dashboards. House rule: a signal is shipped with its **measured**
forward-return record; no measured edge -> it ships as *context, not a signal*.

- Confident-regime sample: **2008-01-01 -> 2026-07-10** (4834 days, confidence>0).
- Ladder panel: **105 instruments** (curated constituents + indices + sector ETFs).
- Caveats: China macro history is monthly back to ~2006-08 (shorter + more regime-unstable
  than the US — 2007/2015 bubbles); the 16 sector ETFs are only ~5y so their RS is
  display-grade, while the ladder is calibrated on the DEEP stock/index panel.

## 1. Regime quad -> forward return of the market index (Shanghai Composite)

**Full sample**

| quad_name    |    n |   f21_mean% |   f21_hit% |   f63_mean% |   f63_hit% |
|:-------------|-----:|------------:|-----------:|------------:|-----------:|
| Goldilocks   | 1707 |        0.73 |       52   |        2.3  |       45.5 |
| Growth-scare |  660 |        1.47 |       56   |        6.69 |       73.5 |
| Reflation    | 1902 |       -0.7  |       49.8 |       -2.69 |       43.5 |
| Stagflation  |  565 |       -0.82 |       48.2 |       -1.4  |       52.8 |

**Split-half robustness** (a quad's edge is only trustworthy if it survives both halves)

_Pre-split_

| quad_name    |   n |   f21_mean% |   f21_hit% |   f63_mean% |   f63_hit% |
|:-------------|----:|------------:|-----------:|------------:|-----------:|
| Goldilocks   | 919 |        1.34 |       56.7 |        4.38 |       48.7 |
| Growth-scare | 171 |        1.21 |       49.7 |        9.2  |       70.1 |
| Reflation    | 946 |       -1.38 |       44.3 |       -4.92 |       36.8 |
| Stagflation  |  52 |      -10.93 |        2   |      -22.05 |        1.9 |

_Post-split_

| quad_name    |   n |   f21_mean% |   f21_hit% |   f63_mean% |   f63_hit% |
|:-------------|----:|------------:|-----------:|------------:|-----------:|
| Goldilocks   | 788 |        0.03 |       46.7 |       -0.13 |       41.8 |
| Growth-scare | 489 |        1.56 |       58.1 |        5.81 |       74.7 |
| Reflation    | 956 |       -0.01 |       55.3 |       -0.42 |       50.4 |
| Stagflation  | 513 |        0.29 |       53.3 |        0.98 |       58.6 |

## 2. Liquidity overlay (PBoC stance via M2 direction) -> forward return

| liquidity   |    n |   f21_mean% |   f21_hit% |   f63_mean% |   f63_hit% |
|:------------|-----:|------------:|-----------:|------------:|-----------:|
| contracting | 2225 |        0.25 |       50.5 |        0.6  |       48.7 |
| expanding   | 1743 |        0.48 |       54.7 |        1.71 |       53.5 |
| neutral     |  803 |       -0.21 |       49.5 |       -0.11 |       46.4 |
| unknown     |   63 |      -12.52 |        5.1 |      -25.24 |        0   |

## 3. Cycle ladder (deep A-share panel) — endpoint return + forward drawdown

|                          |     n |   hit_pct |   avg_fwd_pct |   dd_med_pct |   dd_p10_pct |   dd_bad_pct |
|:-------------------------|------:|----------:|--------------:|-------------:|-------------:|-------------:|
| DECLINE                  |  7062 |      52.6 |          1.72 |        -4.48 |       -14.71 |         21.4 |
| BOTTOM WATCH             |  3517 |      44.8 |          1.66 |        -3.56 |       -14.4  |         19.4 |
| TURN SIGNALED            | 11315 |      48.5 |          1.27 |        -4.52 |       -14.73 |         21.5 |
| FRESH BUY                |  2367 |      52.3 |          2.16 |        -4.43 |       -13.7  |         19.3 |
| RALLY ON                 |  2381 |      50.9 |          1.58 |        -4.27 |       -14.24 |         20.8 |
| TOP WATCH                |  6378 |      51.3 |          2.59 |        -4.92 |       -15.69 |         24.5 |
| ROLLING OVER             |   219 |      47   |          0.47 |        -4.53 |       -13.52 |         19.6 |
| COUNTERTREND BOUNCE      | 10904 |      51.7 |          1.32 |        -4.22 |       -15.01 |         21.3 |
| BOTTOM WATCH +early-bull |   132 |      48.5 |          1.8  |        -2.16 |       -13.52 |         20.5 |
| BOTTOM WATCH no-early    |  3385 |      44.6 |          1.66 |        -3.59 |       -14.42 |         19.3 |

## Reading this
- Quad rows whose sign/ranking flips between the two halves are **regime-unstable** ->
  frame as risk context, never a standalone allocation rule.
- The ladder's value is the DRAWDOWN columns (dd_*): scary states with shallow typical
  dips are the asymmetric setups; the avg_fwd alone is U-shaped/misleading (macro D43).
