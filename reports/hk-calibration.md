# Hong Kong / Hang Seng Dashboard — Calibration

Honest, split-half measurement before any UI is built — the same gate used for the
US, China and Bitcoin Vector dashboards. House rule: a signal is shipped with its **measured**
forward-return record; no measured edge -> it ships as *context, not a signal*.

- Confident-regime sample: **2000-04-21 -> 2026-08-21** (6742 days, confidence>0).
- Ladder panel: **161 instruments** (curated constituents + indices + ETF proxies).
- Caveats: the HK macro read piggybacks on China fundamentals (PMI/CPI/PPI/M2), monthly
  back to ~2006-08 (shorter + more regime-unstable than the US); HSI itself is the regional
  risk-on/off proxy, so the THREE-LEG engine here is quad (growth×inflation) + dual liquidity
  (PBoC + Fed-via-peg) + the global risk overlay — the third leg is the one to scrutinise.

## 1. Regime quad -> forward return of the market index (Hang Seng Index)

**Full sample**

| quad_name    |    n |   f21_mean% |   f21_hit% |   f63_mean% |   f63_hit% |
|:-------------|-----:|------------:|-----------:|------------:|-----------:|
| Goldilocks   | 1471 |        1.41 |       57.5 |        4.11 |       65   |
| Growth-scare | 1126 |        0.2  |       55.2 |        2.28 |       56.2 |
| Reflation    | 1644 |        0.23 |       52.8 |       -0.51 |       46.9 |
| Stagflation  | 1038 |       -0.76 |       45.5 |       -2.13 |       42.7 |

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
| Goldilocks   | 654 |        0.73 |       55.2 |        1.43 |       56.6 |
| Growth-scare | 603 |        0.47 |       57.5 |        1.6  |       50.2 |
| Reflation    | 837 |        0.4  |       51.4 |        0.48 |       51.1 |
| Stagflation  | 676 |       -0.15 |       46.6 |        0.38 |       43.7 |

## 2. Liquidity overlay (dual: PBoC stance + Fed-via-peg + southbound flow) -> forward return

| liquidity   |    n |   f21_mean% |   f21_hit% |   f63_mean% |   f63_hit% |
|:------------|-----:|------------:|-----------:|------------:|-----------:|
| contracting |  868 |       -0.74 |       45.5 |       -3.68 |       33.4 |
| expanding   | 3053 |        0.76 |       57.2 |        1.62 |       56.6 |
| neutral     | 2385 |        0.17 |       51.4 |        1.91 |       56.6 |
| unknown     |  436 |        0.86 |       60.3 |        0.84 |       56   |

## 3. Global risk overlay (risk-on/off) -> forward return

_The KEY HK test: HK is the regional risk-on/off proxy, so does the global risk state
differentiate HSI forward returns?_

| risk_state   |    n |   f21_mean% |   f21_hit% |   f63_mean% |   f63_hit% |
|:-------------|-----:|------------:|-----------:|------------:|-----------:|
| Neutral      | 2487 |       -0.12 |       49.8 |        0.34 |       50   |
| Risk-off     | 1616 |        0.42 |       54.8 |        0.8  |       53.5 |
| Risk-on      | 2639 |        0.8  |       57.1 |        1.84 |       57.6 |

## 4. Cycle ladder (deep HK panel) — endpoint return + forward drawdown

|                          |     n |   hit_pct |   avg_fwd_pct |   dd_med_pct |   dd_p10_pct |   dd_bad_pct |
|:-------------------------|------:|----------:|--------------:|-------------:|-------------:|-------------:|
| DECLINE                  | 10245 |      54   |          1.45 |        -4.82 |       -18.22 |         26.8 |
| BOTTOM WATCH             |  5084 |      48.9 |        128.24 |        -4.06 |       -15.74 |         21.5 |
| TURN SIGNALED            | 17817 |      50.8 |          1.47 |        -4.34 |       -14.47 |         21   |
| FRESH BUY                |  3908 |      52.8 |          1.56 |        -4.07 |       -13.97 |         19.4 |
| RALLY ON                 |  3760 |      53.8 |          1.75 |        -3.92 |       -14.11 |         19.2 |
| TOP WATCH                | 10363 |      52.1 |          1.74 |        -4.35 |       -14.83 |         21.5 |
| ROLLING OVER             |   346 |      51.4 |          1.48 |        -4.6  |       -15.69 |         23.4 |
| COUNTERTREND BOUNCE      | 16885 |      51.1 |          1.07 |        -4.51 |       -16.05 |         23.6 |
| BOTTOM WATCH +early-bull |   179 |      50.3 |          1.27 |        -3.93 |       -13.4  |         20.1 |
| BOTTOM WATCH no-early    |  4905 |      48.8 |        132.87 |        -4.06 |       -15.78 |         21.6 |

## Reading this
- Quad rows whose sign/ranking flips between the two halves are **regime-unstable** ->
  frame as risk context, never a standalone allocation rule.
- The ladder's value is the DRAWDOWN columns (dd_*): scary states with shallow typical
  dips are the asymmetric setups; the avg_fwd alone is U-shaped/misleading (macro D43).
