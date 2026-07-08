# D4-07 Breakout Trade-Size Horse Race

**Date:** 2026-07-08  |  **Family:** w5_trade_size_capitulation  |  **Cell:** D4-07_breakout_tradesize
**VERDICT: NULL_NEGATIVE**

---

## Sibling Context (w5 family amendment)

This cell is a sibling of `w5_trade_size_capitulation` (phase-0 result: PARTIAL).
Key priors from the sibling run:

- **V1 null (#1753):** avg-trade-size collapse AT 52w lows failed G2 (split-half) and G4
  (didn't beat the volume-only control). The mechanism — fragmented-clip accumulation
  at lows — is not reliably separable from general volume decline in this dataset.

- **V2-at-lows insight:** LARGE-trade expansion at 52w lows showed strong 63d outperformance
  (+4.04% relative, t=5.54, BH q≈0). This means elevated avg-trade-size at a low is
  *bullish*, not bearish — consistent with informed buyers stepping in with size.

This cell tests whether that same trade-size dimension carries incremental signal at
BREAKOUT EVENTS (first close ≥ 52w high after ≥60 sessions below), where the mechanism
is different: large trades on the breakout day may confirm institutional conviction
(momentum follows), while small-trade breakouts may be retail-driven and more likely
to fail.

---

## In Plain English

We screened for stocks that had been below their 52-week high for at least 60 sessions
and then closed AT or ABOVE that high (a 'confirmed breakout'). On that breakout day,
we measured whether the average trade was unusually large or small compared to the
stock's own history. Then we asked: after controlling for total volume (which is the
standard momentum signal), does trade SIZE per transaction add any predictive value
for where the stock goes over the next 21 or 63 trading days?

The test is a regression horse race: tradesize_z competes head-to-head with volume_z,
log(size), and log(price) in a single model. The signal lives or dies on the PARTIAL
coefficient of tradesize_z — the extra information it carries that volume alone cannot.

---

## Pre-Registered Gate

PASS: |t_cluster(tradesize_z)| ≥ 2 AND coef > 0 on ≥1 horizon,
      AND BH q ≤ 0.10 across the 2 cells (21d and 63d).

Any significant NEGATIVE tradesize_z coefficient = directional contradiction
(large-trade breakouts underperform) — reported explicitly.

---

## Data Coverage

- Tickers in store: 17,559
- Tickers with ≥1 breakout event: 12,324
- Total breakout events (after 21-bar dedup): 28,355
- Unique event dates: 1,128
- Date range: 2021-12-28 → 2026-07-01

**Below-streak distribution (sessions below 52w-high before breakout):**
- Min: 60
- Median: 183
- Max: 1188

---

## Regression Results (Date-Clustered OLS)

Model: fwd_hz ~ intercept + tradesize_z + volume_z + log_size + log_price
SE: Liang-Zeger date-clustered sandwich with small-sample correction.
Outcomes winsorized at 1st/99th percentile (global, not per-date).

### 21-day horizon

N events: 27,101 | Clusters (unique dates): 1,107

| Covariate | coef | se_cluster | t_cluster | p_cluster | BH q | BH reject |
|-----------|------|------------|-----------|-----------|------|-----------|
| **intercept** | 0.00010 | 0.00528 | 0.018 | 0.9854 | — | — |
| **tradesize_z** | -0.00260 | 0.00084 | -3.099 | 0.0019 | 0.0039 | True |
| **volume_z** | -0.00021 | 0.00016 | -1.307 | 0.1913 | — | — |
| **log_size** | -0.00244 | 0.00036 | -6.830 | 0.0000 | — | — |
| **log_price** | 0.01000 | 0.00156 | 6.428 | 0.0000 | — | — |

### 63-day horizon

N events: 25,101 | Clusters (unique dates): 1,065

| Covariate | coef | se_cluster | t_cluster | p_cluster | BH q | BH reject |
|-----------|------|------------|-----------|-----------|------|-----------|
| **intercept** | -0.00423 | 0.00885 | -0.478 | 0.6324 | — | — |
| **tradesize_z** | -0.00205 | 0.00135 | -1.520 | 0.1284 | 0.1284 | False |
| **volume_z** | -0.00032 | 0.00016 | -1.937 | 0.0527 | — | — |
| **log_size** | -0.00388 | 0.00056 | -6.965 | 0.0000 | — | — |
| **log_price** | 0.01913 | 0.00240 | 7.962 | 0.0000 | — | — |

### Verdict per horizon

| Horizon | tradesize_z coef | t_cluster | BH q | BH reject | Gate |
|---------|-----------------|-----------|------|-----------|------|
| 21d | -0.00260 | -3.099 | 0.0039 | True | **FAIL** |
| 63d | -0.00205 | -1.520 | 0.1284 | False | **FAIL** |

> **DIRECTIONAL CONFLICT DETECTED:** At least one horizon shows a significantly
> NEGATIVE tradesize_z partial coefficient. Large-trade breakouts underperform.
> This is a directional contradiction to the institutional-conviction hypothesis.

---

## Descriptive Split: Institutional vs Retail Tape (Naive Unconditional)

Institutional tape: tradesize_z > 0 (above-norm avg trade size on breakout day).
Retail tape: tradesize_z ≤ 0 (below-norm avg trade size on breakout day).
No controls; descriptive only.

| Horizon | Tape | N | Mean fwd return | Median fwd return |
|---------|------|---|-----------------|-------------------|
| 21d | Institutional (tz>0) | 10,186 | -1.0308% | -0.1401% |
| 21d | Retail (tz≤0) | 17,012 | -0.0910% | 0.1980% |
| 63d | Institutional (tz>0) | 9,451 | -0.8718% | 0.1323% |
| 63d | Retail (tz≤0) | 15,742 | 0.3580% | 0.6602% |

---

## PIT Assumptions and Caveats

- **Data:** `data/massive_stock_day/` (Polygon flat store), 20,476 names, 2021-07-06 to 2026-07-02.
- **Trailing windows:** 252d min_periods=63. First valid breakout events appear ~2022-07.
- **log_size proxy:** log(close × volume) used as size proxy. True market-cap not available.
- **Survivorship:** Store contains current+recent names. Delisted pre-2021 names absent.
  Breakout events on names that later delisted are included up to delisting.
- **Winsorization:** Global 1st/99th pct (not per-date), to reduce outlier influence on OLS.
- **Cluster SE:** Date-clustered (one cluster per calendar date). On days with many
  simultaneous breakouts, same-day returns are correlated; clustering corrects this.
- **transactions coverage:** 100% populated (verified on AAPL, NVDA, GPRO).
- **No size/price universe filter:** Unlike w5, this study includes all prices.

---

## Leak Audit Checklist

- [x] tradesize_z: 20d rolling mean, compared to trailing 252d distribution LAGGED 1 bar
- [x] volume_z: same causal construction
- [x] 52w high: rolling(252).max(), min_periods=63, CAUSAL (computed on history up to bar t)
- [x] below_streak: counts consecutive PRIOR bars below 52w high (no lookahead)
- [x] breakout: close[t] >= 52w_high[t] AND below_streak[t] >= 60
- [x] Event dedup: 21-bar min gap per ticker
- [x] fwd_21: close[t+22]/close[t+1]-1 (fill at t+1; no same-bar fill)
- [x] fwd_63: close[t+64]/close[t+1]-1 (fill at t+1; no same-bar fill)
- [x] Events excluded where fill bar or outcome bar out-of-range
- [x] BH across 2 test cells (21d and 63d), not within a single model
- [x] Ledger logged BEFORE compute
- [x] Outcomes winsorized BEFORE regression

---

## VERDICT: NULL_NEGATIVE

Significant NEGATIVE partial tradesize_z coefficient: large-trade breakouts
UNDERperform. This is a directional contradiction. The hypothesis that institutional
conviction on a breakout day predicts better follow-through is REFUTED in this data.
Null printed. The mechanism may be reversed: large trades on breakout day = distribution
into the breakout, not accumulation.
