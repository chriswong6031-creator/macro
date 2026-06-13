# China A-share Dashboard — Calibration (Phase-2 checkpoint)

Honest, split-half measurement before any UI is built — the same gate used for the
US and Bitcoin Vector dashboards. House rule: a signal is shipped with its **measured**
forward-return record; no measured edge -> it ships as *context, not a signal*.

- Confident-regime sample: **2008-01-01 -> 2026-06-12** (4814 days, confidence>0).
- Ladder panel: **105 instruments** (curated constituents + indices + sector ETFs).
- Caveats: China macro history is monthly back to ~2006-08 (shorter + more regime-unstable
  than the US — 2007/2015 bubbles); the 16 sector ETFs are only ~5y so their RS is
  display-grade, while the ladder is calibrated on the DEEP stock/index panel.

## 1. Regime quad -> forward return of the market index (Shanghai Composite)

**Full sample**

| quad_name    |    n |   f21_mean% |   f21_hit% |   f63_mean% |   f63_hit% |
|:-------------|-----:|------------:|-----------:|------------:|-----------:|
| Goldilocks   | 1669 |        0.81 |       52.3 |        2.45 |       45.8 |
| Growth-scare |  700 |        1.24 |       55   |        6.09 |       71.3 |
| Reflation    | 1871 |       -0.71 |       49.6 |       -2.85 |       42.7 |
| Stagflation  |  574 |       -0.77 |       49.1 |       -1.17 |       53.3 |

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
| Goldilocks   | 750 |        0.16 |       47.1 |        0.09 |       42.4 |
| Growth-scare | 529 |        1.25 |       56.7 |        5.07 |       71.7 |
| Reflation    | 925 |       -0.01 |       55   |       -0.63 |       48.9 |
| Stagflation  | 522 |        0.29 |       54.1 |        1.12 |       58.9 |

## 2. Liquidity overlay (PBoC stance via M2 direction) -> forward return

| liquidity   |    n |   f21_mean% |   f21_hit% |   f63_mean% |   f63_hit% |
|:------------|-----:|------------:|-----------:|------------:|-----------:|
| contracting | 2225 |        0.26 |       50.6 |        0.59 |       48.6 |
| expanding   | 1740 |        0.48 |       54.7 |        1.71 |       53.5 |
| neutral     |  786 |       -0.21 |       49.3 |       -0.17 |       45.7 |
| unknown     |   63 |      -12.52 |        5.1 |      -25.24 |        0   |

## 3. Cycle ladder (deep A-share panel) — endpoint return + forward drawdown

|                          |    n |   hit_pct |   avg_fwd_pct |   dd_med_pct |   dd_p10_pct |   dd_bad_pct |
|:-------------------------|-----:|----------:|--------------:|-------------:|-------------:|-------------:|
| DECLINE                  | 6984 |      53   |          1.8  |        -4.44 |       -14.61 |         21.1 |
| BOTTOM WATCH             | 7193 |      46.2 |          1.23 |        -3.97 |       -15.05 |         20.6 |
| TURN SIGNALED            | 8935 |      50   |          1.74 |        -4.72 |       -14.75 |         22.2 |
| FRESH BUY                | 2759 |      51.5 |          2.48 |        -4.64 |       -14.03 |         20.7 |
| RALLY ON                 | 6303 |      51.5 |          1.68 |        -4.21 |       -14.83 |         20.6 |
| TOP WATCH                | 4261 |      52.2 |          2.22 |        -4.33 |       -14.97 |         22.6 |
| ROLLING OVER             | 1652 |      44.4 |          0.16 |        -4.91 |       -16.27 |         24.9 |
| COUNTERTREND BOUNCE      | 5847 |      52.2 |          1.43 |        -4.27 |       -14.71 |         21.3 |
| BOTTOM WATCH +early-bull |  304 |      44.1 |          0.49 |        -5    |       -15.84 |         27.3 |
| BOTTOM WATCH no-early    | 6889 |      46.3 |          1.27 |        -3.94 |       -14.99 |         20.3 |

## Reading this
- Quad rows whose sign/ranking flips between the two halves are **regime-unstable** ->
  frame as risk context, never a standalone allocation rule.
- The ladder's value is the DRAWDOWN columns (dd_*): scary states with shallow typical
  dips are the asymmetric setups; the avg_fwd alone is U-shaped/misleading (macro D43).
