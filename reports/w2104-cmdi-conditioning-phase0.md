# CMDI Conditioning Phase-0 — w2104_cmdi_conditioning

> **Registered family:** `w2104_cmdi_conditioning`  
> **Run date:** 2026-07-06  
> **Signal lag (PIT):** 2 months (Amendment A1)  
> **Expanding pctile min history:** 24 months (Amendment A2)  
> **3m change:** raw index units, pctile-ranked (Amendment A3)

## In Plain English

The NY Fed publishes a Corporate Bond Market Distress Index (CMDI) as a weekly series (end-of-week Friday, updated continuously). This report tests whether that index can predict when the US equity market (SPY) is about to drop 5% or more within the next 21 calendar days (~14 trading days, ~3 weeks) or 63 calendar days (~42 trading days, ~2 calendar months). We also test whether CMDI is any better than the HY credit spread (OAS) already on disk, and whether the result holds when we remove each major market crisis from the sample one at a time.

CMDI data is available weekly with only a few days of lag. We apply a conservative 2-month lag anyway — this means the signal we use for any given month uses CMDI readings from two months prior, which is verifiably look-ahead free even in fast-moving crises (e.g., 2020-03 signal uses January 2020 CMDI, not the COVID spike). Even with this conservative lag, if CMDI is genuinely informative, high distress readings should cluster before large drawdowns.

## Data Coverage

| Source | Coverage | N |
|---|---|---|
| CMDI weekly (NY Fed) | 2005-01-07 -> 2026-06-19 | 1120 weeks |
| CMDI monthly (resampled) | 2005-01-31 -> 2026-06-30 | 258 months |
| SPY daily (Yahoo) | 1993-01-29 -> 2026-07-02 | 8413 days |
| HY OAS (FRED BAMLH0A0HYM2) | 1999-02-28 -> 2026-07-31 | 330 months |

**Forward label base rates** (SPY drawdown <= -5% within horizon):
- 21d horizon: 53 events / 403 months (13.2%)
- 63d horizon: 108 events / 403 months (26.8%)

## Signal First-Valid Dates (post lag + min-history)

| Signal | First Valid |
|---|---|
| market_level_pctile | 2007-03-31 00:00:00 |
| market_3m_chg_pctile | 2007-08-31 00:00:00 |
| ig_level_pctile | 2007-03-31 00:00:00 |
| ig_3m_chg_pctile | 2007-08-31 00:00:00 |
| hy_level_pctile | 2007-03-31 00:00:00 |
| hy_3m_chg_pctile | 2007-08-31 00:00:00 |

## Pre-Registration

Trial ledger: family=`w2104_cmdi_conditioning`, 12 configs logged at generation, family effective N=12.

## T1 AUC Results — All Signals

Gate: AUC >= 0.60 AND bootstrap 95% CI excludes 0.50.
Horizons: 21 = 21 calendar days (~14 trading days, ~3 weeks); 63 = 63 calendar days (~42 trading days, ~2 calendar months). forward_max_drawdown() uses pd.Timedelta(days=N), so these are calendar-day windows, not trading-day windows.
Overlap: monthly series — each obs is one calendar month, no overlap correction needed.

| Signal | Horizon | N | N_events | AUC | 95% CI lo | 95% CI hi | CI>0.5 | Gate | NW_t | NW_p |
|---|---|---|---|---|---|---|---|---|---|---|
| market_level_pctile | 21d | 232 | 34 | 0.5897 | 0.4652 | 0.7107 | N | **FAIL** | -5.087 | 0.0000 |
| market_3m_chg_pctile | 21d | 227 | 34 | 0.5536 | 0.4490 | 0.6573 | N | (context) | -8.864 | 0.0000 |
| ig_level_pctile | 21d | 232 | 34 | 0.6324 | 0.5214 | 0.7420 | Y | (context) | -5.357 | 0.0000 |
| ig_3m_chg_pctile | 21d | 227 | 34 | 0.5888 | 0.4869 | 0.6951 | N | (context) | -9.372 | 0.0000 |
| hy_level_pctile | 21d | 232 | 34 | 0.5797 | 0.4569 | 0.6970 | N | **FAIL** | -4.930 | 0.0000 |
| hy_3m_chg_pctile | 21d | 227 | 34 | 0.6096 | 0.5144 | 0.7054 | Y | (context) | -8.294 | 0.0000 |
| market_level_pctile | 63d | 232 | 68 | 0.5677 | 0.4799 | 0.6548 | N | **FAIL** | -2.083 | 0.0372 |
| market_3m_chg_pctile | 63d | 227 | 67 | 0.5923 | 0.5121 | 0.6703 | Y | (context) | -3.520 | 0.0004 |
| ig_level_pctile | 63d | 232 | 68 | 0.5895 | 0.5016 | 0.6734 | Y | (context) | -2.426 | 0.0153 |
| ig_3m_chg_pctile | 63d | 227 | 67 | 0.5918 | 0.5089 | 0.6704 | Y | (context) | -3.320 | 0.0009 |
| hy_level_pctile | 63d | 232 | 68 | 0.5518 | 0.4696 | 0.6335 | N | **FAIL** | -2.355 | 0.0185 |
| hy_3m_chg_pctile | 63d | 227 | 67 | 0.5694 | 0.4890 | 0.6445 | N | (context) | -3.597 | 0.0003 |

### HY OAS Baseline (Full Coverage — display only)

These numbers show HY OAS evaluated on its own full date range (back to 1999). They are **not** used for the T2 gate — see T2 section for identical-date comparisons.

| Series | Horizon | N | N_events | AUC | 95% CI lo | 95% CI hi |
|---|---|---|---|---|---|---|
| HY OAS z-score (full) | 21d | 330 | 49 | 0.6731 | 0.5777 | 0.7613 |
| HY OAS z-score (full) | 63d | 330 | 97 | 0.6251 | 0.5586 | 0.6927 |

## T2 — CMDI vs HY OAS Baseline (Gated Cells, Identical Dates)

**Pre-registered requirement:** IDENTICAL labels vs HY-OAS baseline. HY-OAS AUC is computed on the exact same months used for each CMDI cell (the intersection of non-NaN dates from the joined signal+label series). Without this restriction, the HY-OAS baseline covers 1999–2026 (330 months) while CMDI covers only 2007–2026 (232 months), giving HY-OAS the full 2008 run-up window that CMDI cannot see — inflating its unconstrained AUC.

Gate: CMDI beats HY-OAS AUC (identical dates) at >= 1 gated cell.

| Gated Cell | CMDI AUC | HY OAS AUC (identical N) | N identical | CMDI Beats |
|---|---|---|---|---|
| market_level_pctile_21d | 0.5897 | 0.5893 | 232 | YES |
| market_level_pctile_63d | 0.5677 | 0.5399 | 232 | YES |
| hy_level_pctile_21d | 0.5797 | 0.5893 | 232 | NO |
| hy_level_pctile_63d | 0.5518 | 0.5399 | 232 | YES |

**T2 GATE: PASS** (CMDI beats HY-OAS on identical dates at 3/4 gated cell(s))

## T3 — Leave-One-Crisis-Out Stability (Gated Cells)

Gate: each removal produces AUC > 0.50 (same direction). At least one gated cell must be fully LOCO-stable.

### market_level_pctile_21d — LOCO UNSTABLE

| Crisis excised | AUC | > 0.50 |
|---|---|---|
| -2008 | 0.4325 | NO |
| -2011 | 0.6093 | YES |
| -2015-16 | 0.5918 | YES |
| -2020 | 0.5993 | YES |
| -2022 | 0.5921 | YES |
| -2023-03 | 0.5945 | YES |

### market_level_pctile_63d — LOCO UNSTABLE

| Crisis excised | AUC | > 0.50 |
|---|---|---|
| -2008 | 0.4590 | NO |
| -2011 | 0.5812 | YES |
| -2015-16 | 0.5687 | YES |
| -2020 | 0.5787 | YES |
| -2022 | 0.5727 | YES |
| -2023-03 | 0.5691 | YES |

### hy_level_pctile_21d — LOCO UNSTABLE

| Crisis excised | AUC | > 0.50 |
|---|---|---|
| -2008 | 0.4205 | NO |
| -2011 | 0.6052 | YES |
| -2015-16 | 0.5757 | YES |
| -2020 | 0.5815 | YES |
| -2022 | 0.5915 | YES |
| -2023-03 | 0.5831 | YES |

### hy_level_pctile_63d — LOCO UNSTABLE

| Crisis excised | AUC | > 0.50 |
|---|---|---|
| -2008 | 0.4497 | NO |
| -2011 | 0.5718 | YES |
| -2015-16 | 0.5501 | YES |
| -2020 | 0.5561 | YES |
| -2022 | 0.5606 | YES |
| -2023-03 | 0.5567 | YES |

**T3 GATE: FAIL** (no gated cell fully LOCO-stable)

## Gate Summary

| Gate | Result | Details |
|---|---|---|
| T1: AUC>=0.60, CI>0.50 at any gated cell | **FAIL** | Gated cells passing: 0/4 |
| T2: CMDI beats HY-OAS at >=1 gated cell | **PASS** | Cells where CMDI wins: 3/4 |
| T3: LOCO stable (>=1 gated cell) | **FAIL** | Stable cells: 0/4 |

## VERDICT: FAIL — CONTEXT VERDICT (null accepted)

Failed gates: T1, T3. CMDI remains a context signal — high readings are informative for narrative/display but do not meet the de-escalation candidacy bar. Re-test if methodology or lag assumption changes.

## Honest-N

Monthly series, ~232 monthly obs usable (after lag + min-history). Independent 'crisis' events in-sample: 6 excision windows tested in LOCO. AUC CI via bootstrap resampling positives/negatives independently (correct for binary AUC, not block-bootstrap which is for return series). NW lags=6 covers 6-month serial correlation at 63d horizon.

## Nightly Wiring (for consolidation)

### Collector: `scripts/collect_nyfed_cmdi.py`

Standalone collector (ships with this PR). Fetches the NY Fed CMDI Excel file via the interactive data URL, parses Market/IG/HY sub-indices, saves weekly raw and month-end resampled parquets.

**Outputs:**
- `data/nyfed_cmdi/cmdi_weekly.parquet` — weekly raw (end-of-week Friday)
- `data/nyfed_cmdi/cmdi_monthly.parquet` — month-end last reading

**Wiring into nightly collect.py:**
```python
# In scripts/collect.py — add after existing nyfed collectors:
from scripts.collect_nyfed_cmdi import collect_nyfed_cmdi
collect_nyfed_cmdi()  # idempotent; skips if already current
```

**Signal construction (engine/signal_lab.py consumer):**
```python
from scripts.cmdi_phase0 import build_signals, build_monthly
import pandas as pd

monthly = pd.read_parquet('data/nyfed_cmdi/cmdi_monthly.parquet')
sigs = build_signals(monthly, lag=2)  # 2-month PIT lag
# Columns: market_level_pctile, ig_level_pctile, hy_level_pctile,
#          market_3m_chg_pctile, ig_3m_chg_pctile, hy_3m_chg_pctile
```

**Recommended schedule:** Weekly cron (e.g., Wednesday 11am ET) for idempotent refresh. CMDI is a weekly series updated on Fridays; weekly polling picks up the latest reading within days of each week-end. The 2-month lag in signal construction ensures the data remains look-ahead-free regardless of exact collection timing.
