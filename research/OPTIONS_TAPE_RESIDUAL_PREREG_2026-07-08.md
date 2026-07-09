# W5-B Options Tape Residual — Formal Pre-Registration

**Family:** `w5b_tape_residual`
**Pre-registered:** 2026-07-08 (before any test computation)
**Horizon:** auto-trigger gated (earliest ~Q1-2027; see §6)
**Status:** FROZEN — no results; no post-hoc modifications permitted

---

## §0 Why this exists

This document is the **full specification** of the W5-B tape-residual signal, written and committed before any cross-sectional IC or return analysis is computed. Every degree of freedom is named here. The auto-trigger law (§6) prevents any earlier test run from inflating the claimed event set. No result numbers appear in this document; any file adding them to this section without a co-registered amendment is a protocol violation.

---

## §1 Data source

**Store:** `data/options_tape_signed/<UNDERLYING>.parquet`

One file per underlying. Schema authority: `scripts/options_tape_signed_pilot.py` (the build script that writes these files).

**Fields used in this construct:**

| Column | Type | Description |
|---|---|---|
| `underlying` | str | Ticker symbol |
| `date` | datetime64 | Trading date |
| `buy_premium` | float | Sum(price × size × 100) for BUY-classified trades (simple quote rule: price ≥ ask) |
| `sell_premium` | float | Sum(price × size × 100) for SELL-classified trades (price ≤ bid) |
| `net_premium` | float | buy_premium − sell_premium (positive = net buy pressure in dollar-premium terms) |
| `buy_delta_proxy` | float | Sum(delta_proxy × size) for BUY trades; delta_proxy is UNSIGNED moneyness-bucket magnitude |
| `sell_delta_proxy` | float | Sum(delta_proxy × size) for SELL trades; delta_proxy is UNSIGNED moneyness-bucket magnitude |
| `exclusion_rate` | float | Fraction of raw trades excluded (midpoint / missing NBBO / crossed market) |

**Signing rule (inherited from pilot, stated for completeness):** simple quote rule (NOT Lee-Ready tick-test). Price ≥ ask → BUY; price ≤ bid → SELL; midpoint excluded.

**Delta proxy note (Amendment A2 from pilot):** `delta_proxy` is an **unsigned** moneyness-magnitude proxy (ITM deep=0.90, ITM=0.70, NTM/ATM=0.50, OTM=0.30, deep-OTM=0.10). It does NOT carry put/call sign. `net_delta_proxy` = `buy_delta_proxy − sell_delta_proxy` is therefore NOT a delta-adjusted directional indicator; sign derives from BUY/SELL classification only.

**Pilot coverage at pre-registration:** 20 underlyings × approximately 120 trading days. Auto-trigger requires 100 underlyings × 250 trading days (§6).

---

## §2 Signed net-delta construction

Because `net_delta_proxy` from the store is unsigned-delta-weighted, this construct computes a **signed net-delta proxy** as:

```
signed_net_delta_proxy(t) = buy_delta_proxy(t) − sell_delta_proxy(t)
```

This is algebraically identical to `net_delta_proxy` in the store (since the store defines `net_delta_proxy = buy_delta_proxy − sell_delta_proxy`), but the pre-registration explicitly states the sign convention:

- **Positive** = net buy-side delta-weighted volume (buyers absorbed more delta-equivalent gamma than sellers)
- **Negative** = net sell-side delta-weighted volume

No further sign transformation is applied.

---

## §3 Dealer-positioning proxy

**Definition:** the cumulative sum of `net_premium` over the trailing 20 trading days, computed per underlying, using only dates where `exclusion_rate ≤ 0.50`.

```
dealer_proxy(i, t) = Σ_{s=t-19}^{t} net_premium(i, s)    [exclusion_rate(s) ≤ 0.50]
```

**Sign convention:** positive = persistent net buy pressure accumulated by the market as a whole. Under the dealer-absorption hypothesis, sustained positive net-premium flow implies dealers are net short (they sold options to buyers), creating a negative-gamma positioning in the underlying. A positive dealer_proxy therefore implies dealer buying of the underlying to hedge (supportive flow). The sign is pre-registered as part of the residualization input, not as a directional forecast by itself.

**Trailing window:** 20 trading days. Fixed; not optimized.

**Missing-data treatment:** if fewer than 10 of the 20 days have `exclusion_rate ≤ 0.50`, the dealer_proxy observation is marked missing for that (underlying, date) and the row is dropped from the cross-section.

---

## §4 Residual construct

### 4.1 Raw signal

Daily **signed net-premium** per underlying:

```
raw_flow(i, t) = net_premium(i, t)
```

Only days where `exclusion_rate(i, t) ≤ 0.50` are retained (see §5.4).

### 4.2 Cross-sectional residualization

On each date `t`, regress `raw_flow(i, t)` cross-sectionally on three controls:

| Control | Definition |
|---|---|
| `dealer_proxy(i, t)` | As defined in §3 |
| `log_dollar_volume(i, t)` | log(dollar trading volume in the underlying equity on date t), sourced from `data/massive_stock_day/<UNDERLYING>.parquet` field `volume × close` |
| `own_return_5d(i, t)` | Cumulative return of the underlying equity over the prior 5 trading days (t−5 to t−1, inclusive), PIT-safe (no day-t data) |

Estimation: **pooled OLS with date fixed effects**. Date fixed effects are absorbed as dummy variables for each calendar date in the pooled panel; they remove cross-date mean shifts in flow magnitude. Standard errors are not the primary output — the regression is used solely to extract residuals.

```
raw_flow(i, t) = α(t) + β₁·dealer_proxy(i, t) + β₂·log_dollar_volume(i, t)
                       + β₃·own_return_5d(i, t) + ε(i, t)
```

The residual `ε(i, t)` is the tape-residual for date `t`, underlying `i`.

**Calendar collapse before NW:** pooled OLS is fit on the full panel; date-FE are date dummies, not a time-series regression. This satisfies the calendar-collapse-before-NW law because individual date effects are absorbed in the estimation step, and Newey-West HAC (§5.2) is applied at the monthly IC level, not on the raw panel residuals.

### 4.3 Signal aggregation

The daily residual is smoothed to a 5-trading-day rolling mean per underlying:

```
signal(i, t) = mean(ε(i, s) : s ∈ [t−4, t])
```

This is the **W5-B tape-residual signal**. Evaluated at month-end dates for IC computation.

---

## §5 Test specification

### 5.1 Estimand

Cross-sectional rank-IC of `signal(i, t)` vs forward returns, evaluated at month-end dates.

**Horizons:** 5 trading days and 21 trading days.

**Return definition:** total return of the underlying equity, log-return, from close of date `t` to close of date `t+h` (h = 5 or 21). Sourced from `data/massive_stock_day/<UNDERLYING>.parquet`.

**Cross-section:** all underlyings with valid signal on that month-end date (exclusion-rate gate applied, dealer_proxy non-missing, own_return_5d non-missing).

### 5.2 Overlap correction

21-day returns overlap across consecutive monthly IC observations (monthly observation frequency = ~21 trading days; 21-day horizon = 100% overlap between adjacent months). Newey-West HAC standard errors with lag = 2 months are applied to the IC time series at both horizons to correct for overlap-induced autocorrelation.

5-day returns at monthly frequency have no meaningful overlap; NW lag = 1 (standard) is still applied for consistency.

### 5.3 Primary gate

Benjamini-Hochberg (BH) FDR correction across the 2 IC tests (5d, 21d). Gate: BH q ≤ 0.10.

**Both horizons must pass the BH gate for the signal to proceed.** A pass on one horizon alone is a null.

### 5.4 Exclusion-rate filter

Any (underlying, date) row where `exclusion_rate > 0.50` is dropped before computing `raw_flow`, `dealer_proxy`, or any downstream quantity. This filter is a data-quality gate, not a signal filter; it is applied identically across all horizons and is not tuned post-hoc.

### 5.5 Split-half stability check

In addition to the primary gate, the full time series of IC observations is split at the midpoint (by date). Mean IC and its sign must agree across the two halves. A sign disagreement in the split-half is a failure even if the pooled IC passes BH.

### 5.6 Pre-registered sign

**Positive.** Buy-pressure residual (positive `signal`) is pre-registered to predict positive forward drift. A statistically significant negative IC constitutes an anti-hypothesis result (not a re-specification opportunity).

### 5.7 Trailing-PIT thresholds

All lookback windows (20d dealer proxy, 5d own-return, 5d signal smoothing) use only data strictly available at date `t` with no look-ahead. The `own_return_5d` window is `[t−5, t−1]`, not `[t−4, t]`, to ensure the current day's return is excluded.

---

## §6 Auto-trigger condition

**No test is run before this condition is met.**

**Trigger:** `data/options_tape_signed/` store reaches **≥ 100 underlyings × ≥ 250 trading days** of coverage per underlying.

**Current state at pre-registration (2026-07-08):** approximately 20 underlyings × 120 trading days. Earliest realistic trigger: ~Q1-2027, consistent with program receipts.

**How to verify coverage:** count the number of `.parquet` files in `data/options_tape_signed/` (excluding `_backfill_state.json`) and the minimum row count across those files. Both thresholds must be satisfied simultaneously.

---

## §7 Name-expansion request — next-80 schedule

To reach 100 underlyings from the current pilot 20, the backfill state machine must be initialized with the following 80 additional names. This list is **frozen at pre-registration** so the universe definition is not a post-hoc choice.

Selection criterion: next-most-liquid US options underlyings by average daily options volume (ADOV), excluding the 20 pilot names already in the store.

### Proposed next-80 list

**Index ETFs & macro**
IWM, DIA, EEM, GLD, TLT, HYG, LQD, XLF, XLE, XLK, XLV, XLI, XLU, XLY, XLP, XLRE, XLB, XLC, ARKK, SMH

**Large-cap single names (tech/semis)**
INTC, MU, QCOM, AVGO, TSM, ARM, MRVL, NOW, CRM, ORCL, ADBE, SNOW, PLTR, UBER, LYFT, SHOP, SPOT, NET, DDOG, ZS

**Large-cap single names (financials/energy/industrials)**
C, WFC, MS, BLK, AXP, COF, USB, PNC, TFC, GE, HON, BA, CAT, DE, LMT, RTX, NOC, SLB, HAL, OXY

**Large-cap single names (healthcare/consumer/discretionary)**
PFE, ABBV, MRK, LLY, BMY, AMGN, GILD, CVS, CI, HUM, COST, TGT, LOW, SBUX, MCD, NKE, F, GM, RIVN, LCID

**Total proposed additions:** 80

**Note:** TSM (Taiwan Semiconductor, NYSE-listed ADR) is included because its US options market is among the most liquid for non-US companies; ThetaTerminal covers NYSE/NASDAQ listed names.

**Universe is frozen.** Any deviation from this list at trigger time must be registered as a pre-trigger amendment with the reason stated before coverage reaches the 100-name threshold.

---

## §8 Trial ledger registration

Family: `w5b_tape_residual`
Kind: `prereg` (no results; no config_hash from a grid; this row marks the pre-registration event)

One row is logged to `data/trial_ledger.jsonl` with:
- `family = "w5b_tape_residual"`
- `kind = "prereg"`
- `note` = this document's filename and the frozen construct summary

The ledger write is performed by the build script accompanying this pre-registration. `git checkout -- data/trial_ledger.jsonl` is called immediately after logging so the ledger is not committed as part of this pre-registration PR (consistent with house rules: no forward-ledger writes in intraday lanes).

---

## §9 Amendments

Amendments must be pre-registered (written and committed) before any results that the amendment affects are computed. Post-hoc amendments that widen the gate or change the sign are protocol violations. Gap amendments (pre-registered coverage gaps) are acceptable and must appear as new sections here before the trigger condition is met.

---

## §10 Gaps pre-registered at time of writing

**GAP-W5B-01:** The 80-name expansion list (§7) assumes ThetaTerminal covers all listed names with sufficient daily trade volume to produce valid `buy_premium`/`sell_premium` aggregates. Coverage has not been verified for all 80 names at pre-registration. A coverage pre-check must be run before the trigger date and any names with fewer than 50% exclusion-rate-passing days in the first 30 days of collection must be removed from the universe before the trigger count is applied. This is a coverage filter, not a signal filter; its application does not require an amendment.

**GAP-W5B-02:** `log_dollar_volume` sourced from `data/massive_stock_day/` uses EOD close × volume. If a name is missing from that store on a given date, the row is dropped from the cross-section on that date. The minimum cross-section size for an IC observation is 20 underlyings; dates with fewer than 20 valid underlyings are excluded from the IC series.

**GAP-W5B-03:** The split-half stability check (§5.5) requires at least 12 monthly IC observations per half (24 total). If the trigger fires before 24 monthly observations are available, the split-half check is deferred until 24 observations exist. The BH gate (§5.3) remains operative from the first 12 observations onward.

---

*Pre-registration sealed 2026-07-08. Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>*
