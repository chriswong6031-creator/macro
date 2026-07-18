# Hong Kong / Hang Seng Dashboard — Calibration

Honest, split-half measurement before any UI is built — the same gate used for the
US, China and Bitcoin Vector dashboards. House rule: a signal is shipped with its **measured**
forward-return record; no measured edge -> it ships as *context, not a signal*.

- Confident-regime sample: **2000-04-21 -> 2026-07-17** (6723 days, confidence>0).
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
| Reflation    | 1663 |        0.28 |       52.8 |       -0.37 |       47.8 |
| Stagflation  |  995 |       -1.1  |       43.4 |       -2.4  |       40.9 |

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
| Reflation    | 856 |        0.51 |       51.5 |        0.79 |       53.1 |
| Stagflation  | 633 |       -0.64 |       43.4 |       -0.01 |       41   |

## 2. Liquidity overlay (dual: PBoC stance + Fed-via-peg + southbound flow) -> forward return

| liquidity   |    n |   f21_mean% |   f21_hit% |   f63_mean% |   f63_hit% |
|:------------|-----:|------------:|-----------:|------------:|-----------:|
| contracting |  843 |       -0.97 |       43.8 |       -3.74 |       34   |
| expanding   | 3059 |        0.77 |       57.3 |        1.64 |       56.7 |
| neutral     | 2385 |        0.17 |       51.4 |        1.91 |       56.6 |
| unknown     |  436 |        0.86 |       60.3 |        0.84 |       56   |

## 3. Global risk overlay (risk-on/off) -> forward return

_The KEY HK test: HK is the regional risk-on/off proxy, so does the global risk state
differentiate HSI forward returns?_

| risk_state   |    n |   f21_mean% |   f21_hit% |   f63_mean% |   f63_hit% |
|:-------------|-----:|------------:|-----------:|------------:|-----------:|
| Neutral      | 2484 |       -0.15 |       49.6 |        0.36 |       50.1 |
| Risk-off     | 1616 |        0.37 |       54.6 |        0.8  |       53.5 |
| Risk-on      | 2623 |        0.8  |       57.1 |        1.87 |       57.9 |

## 4. Cycle ladder (deep HK panel) — endpoint return + forward drawdown

|                          |     n |   hit_pct |   avg_fwd_pct |   dd_med_pct |   dd_p10_pct |   dd_bad_pct |
|:-------------------------|------:|----------:|--------------:|-------------:|-------------:|-------------:|
| DECLINE                  | 10173 |      53.5 |          1.33 |        -4.88 |       -18.35 |         27.2 |
| BOTTOM WATCH             |  5190 |      47.8 |        125.59 |        -3.93 |       -15.74 |         21.3 |
| TURN SIGNALED            | 18020 |      50.9 |          1.49 |        -4.34 |       -14.53 |         21   |
| FRESH BUY                |  3911 |      53   |          1.57 |        -4.08 |       -13.96 |         19.5 |
| RALLY ON                 |  3746 |      53.6 |          1.73 |        -3.97 |       -14.14 |         19.3 |
| TOP WATCH                | 10343 |      51.9 |          1.72 |        -4.37 |       -14.81 |         21.7 |
| ROLLING OVER             |   344 |      51.5 |          1.41 |        -4.6  |       -15.74 |         23.3 |
| COUNTERTREND BOUNCE      | 16725 |      50.8 |          1.02 |        -4.57 |       -16.18 |         23.8 |
| BOTTOM WATCH +early-bull |   188 |      47.3 |          1.07 |        -3.74 |       -12.6  |         18.6 |
| BOTTOM WATCH no-early    |  5002 |      47.8 |        130.27 |        -3.94 |       -15.79 |         21.4 |

## Reading this
- Quad rows whose sign/ranking flips between the two halves are **regime-unstable** ->
  frame as risk context, never a standalone allocation rule.
- The ladder's value is the DRAWDOWN columns (dd_*): scary states with shallow typical
  dips are the asymmetric setups; the avg_fwd alone is U-shaped/misleading (macro D43).
