# w5_trade_size_capitulation — Phase-0 Report

**Date:** 2026-07-06  |  **Family:** w5_trade_size_capitulation  |  **Program:** durable-bottom
**VERDICT: PARTIAL**

---

## In plain English

We asked: when small/mid-cap stocks near their 52-week lows show an unusually
SMALL average trade size (volume ÷ number of transactions per day) — a sign that
trading activity is fragmented into tiny clips rather than the panic block-selling
typical at selling climaxes — do they bounce more than comparable stocks also near
their lows that lack this pattern?

The 'collapse' pattern (avg_trade_size z-score < -1 AND dollar-volume below its
trailing norm) is meant to capture slow accumulation: demand absorbing supply in
small increments. If real, names showing this should bounce 2-10% more than
matched near-low peers over the next 21-63 trading days.

The AVOID variant (V2) tests the opposite: big-trade expansion near a low as a
signal of continued distribution. The control (V3) uses only dollar-volume decline
to isolate how much of any V1 edge comes from the trade-size component specifically.

---

## PIT Assumptions

- **Data:** `data/massive_stock_day` (Polygon, nested path: `massive_stock_day/massive_stock_day/<T>.parquet`)
- **Coverage:** 2021-07-06 to 2026-07-02 (~5 years). Trailing 252d windows require 63d min;
  events begin from ~2022-07. This 5-year window is honest and limits statistical power.
- **transactions column:** Present and non-null in all examined tickers.
- **Survivorship:** The store contains current+recent tickers. Delisted names before 2021 absent.
  Relative (cohort-matched) returns reduce but do not eliminate this bias.
- **Fill rule:** fwd_21 = close[t+22]/close[t+1]-1; fwd_63 = close[t+64]/close[t+1]-1.
  No same-bar fill. Events within 21/63 bars of end-of-data excluded.

---

## Data Coverage

- Tickers in store: 18,009
- Tickers ever in universe (price>$2, dvol $0.5M-$50M, near 52w low): 10,313

---

## Event Counts

| Signal | Events | Tickers | Definition |
|--------|--------|---------|------------|
| V1 | 14,361 | 5,097 | ats_z<-1 AND dvol_z<0 (collapse+interaction) |
| V2 | 20,413 | 7,025 | ats_z>+1 AND dvol_z>0 (expansion/AVOID) |
| V3 | 17,963 | 5,176 | dvol_z<-1 only (volume-control) |

---

## Results by Horizon

### 21-day horizon

| Signal | N events | N dates | Raw mean | Raw NW-t | Raw p | Rel mean | Rel NW-t | Rel p | BH q | BH reject |
|--------|----------|---------|----------|----------|-------|----------|----------|-------|------|-----------|
| V1 | 14094 | 1137 | 0.01% | 0.03 | 0.98 | -0.09% | -0.42 | 0.67 | 0.67 | False |
| V2 | 19868 | 1154 | 0.75% | 2.32 | 0.02 | 0.66% | 2.38 | 0.02 | 0.04 | True |
| V3 | 17662 | 1139 | 1.02% | 2.04 | 0.04 | 0.93% | 2.10 | 0.04 | 0.05 | True |

### 63-day horizon

| Signal | N events | N dates | Raw mean | Raw NW-t | Raw p | Rel mean | Rel NW-t | Rel p | BH q | BH reject |
|--------|----------|---------|----------|----------|-------|----------|----------|-------|------|-----------|
| V1 | 13595 | 1095 | 1.34% | 1.66 | 0.10 | 1.28% | 1.88 | 0.06 | 0.07 | True |
| V2 | 19015 | 1112 | 4.10% | 4.88 | 0.00 | 4.04% | 5.54 | 0.00 | 0.00 | True |
| V3 | 17121 | 1097 | 3.12% | 2.77 | 0.01 | 3.07% | 3.02 | 0.00 | 0.01 | True |

---

## Gate Results

| Gate | Status | Description |
|------|--------|-------------|
| G1 (BH FDR) | **PASS** | V1 relative bounce survives BH q<=0.10 on ≥1 horizon |
| G2 (split-half) | **FAIL** | V1 same-sign in both calendar halves |
| G3 (ex-2022-H2) | **PASS** | V1 holds excluding 2022-H2 bear |
| G4 (V1>V3) | **FAIL** | V1 rel bounce > V3 on both horizons |

### Split-Half Detail (G2)

**21d:** first_half_years=[np.int32(2021), np.int32(2022), np.int32(2023)] mean=-0.00728 t=-2.895 p=0.0038
  second_half_years=[np.int32(2024), np.int32(2025), np.int32(2026)] mean=0.00499 t=1.597 p=0.1102
  same_sign: False

**63d:** first_half_years=[np.int32(2021), np.int32(2022), np.int32(2023)] mean=-0.00967 t=-1.509 p=0.1313
  second_half_years=[np.int32(2024), np.int32(2025), np.int32(2026)] mean=0.03496 t=3.127 p=0.0018
  same_sign: False

### Ex-2022-H2 Robustness (G3)

**21d:** n_events=12313 mean=-0.00105 t=-0.483 p=0.6293 (full-sample mean=-0.00087)
**63d:** n_events=12313 mean=0.011 t=1.479 p=0.139 (full-sample mean=0.01283)

### V1 vs V3 Control (G4)

**21d:** V1 mean=-0.00087 | V3 mean=0.00932 | V1 beats V3: False
**63d:** V1 mean=0.01283 | V3 mean=0.0307 | V1 beats V3: False

---

## BH FDR Table (full 6-test family, q<=0.10)

| Test | p | q | reject |
|------|---|---|--------|
| V1_21 | 0.6729 | 0.6729 | False |
| V1_63 | 0.0607 | 0.0728 | True |
| V2_21 | 0.0175 | 0.035 | True |
| V2_63 | 0.0 | 0.0 | True |
| V3_21 | 0.0358 | 0.0537 | True |
| V3_63 | 0.0025 | 0.0075 | True |

---

## VERDICT: PARTIAL

G1 (BH FDR) passed but robustness gates failed. The signal shows a significant
pattern but insufficient robustness for production. Null printed; signal does not
advance. The specific failing gate(s) are documented above.

---

## Nightly Wiring (for consolidation — only if PASS verdict)

If this signal is promoted, the following changes are required:
1. **Standalone collector** (`scripts/collect_trade_size_signals.py`) — never edit
   `scripts/collect.py` (HOUSE RULES §6). Computes `ats_z`, `dvol_z` per ticker nightly.
2. **Engine module** (`engine/trade_size_signals.py`) — compute avg_trade_size features.
3. **Registry** — register under `w5_trade_size_capitulation` in species_registry.py.
4. **Display chip** — US standout cards (separate bilingual PR).

---

## Leak Audit Checklist

- [x] ats_z: trailing 252d distribution lagged 1 bar before rolling (causal)
- [x] dvol_z: same causal construction
- [x] near_52w_low: rolling(252).min() on historical bars only
- [x] Universe filters applied per-day before event selection
- [x] Event deduplication: 21-bar min gap, first bar of each collapse run
- [x] fwd_21: close[t+22]/close[t+1]-1 (fill at t+1, no same-bar fill)
- [x] fwd_63: close[t+64]/close[t+1]-1 (fill at t+1, no same-bar fill)
- [x] Cohort: excludes event ticker, excludes collapse names (ats_z<-1 AND dvol_z<0)
- [x] NW on DATE-collapsed series (not event-index), preventing spurious N inflation
- [x] BH correction applied simultaneously across all 6 test series
- [x] All z-score thresholds are pre-registered, not full-sample quantiles
- [x] Ledger logged BEFORE compute (at generation, not at selection)
