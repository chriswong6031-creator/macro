# Pre-registration: Release Playbook v1 — Descriptive Transmission Study

**Status:** FROZEN — do not alter after first execution.
**Program:** macro-release-intel, PR-E (W5)
**Ruling basis:** MRI-R1, MRI-R2, MRI-R3, MRI-R6, MRI-R7, MRI-R9
**Registered:** 2026-07-07

> DESCRIPTIVE ONLY (MRI-R1/R2/R3): no signal, no gate, no entry/exit claim;
> announcement-premium and scored-surprise kills stand.

---

## 1. Purpose

Publish a display-only historical record of what macro-release surprises did
to rates, the yield curve, the broad dollar, and equities over short horizons.
The output is regime context for the Neural Web; it informs no entry, exit,
score, or gate.

---

## 2. Events

### 2.1 CPI — CPIAUCSL MoM initial prints

- **Series:** `CPIAUCSL` from `data/fred_vintage/vintages.parquet`
  (long format: series, period, value, realtime_start, realtime_end).
- **Initial print definition:** for each `period`, the row with the
  earliest `realtime_start`. The `realtime_start` date is the event date
  (the release date).
- **Coverage:** 1997-01 period onward (realtime_start 1997-01-14 to present).
- **MoM computation:** value[t] − value[t-1] where both are initial-vintage
  values and t-1 is the prior period's initial print. First period excluded
  (no prior available for MoM).

### 2.2 NFP — PAYEMS MoM-change initial prints

- **Series:** `PAYEMS` from `data/fred_vintage/vintages.parquet`.
- **Initial print definition:** same rule as CPI.
- **Coverage floor:** 2010-01 period onward (aligns with MRI prereg NFP
  floor and era-split boundary). Periods before 2010 are excluded from all
  analysis.
- **MoM computation:** value[t] − value[t-1] (level change, thousands) using
  initial-vintage values.

---

## 3. Surprise construction (PIT)

For each event t in release order:

1. `realized_surprise[t]` = `mom[t]` − `naive_prior[t]`
   where `naive_prior[t]` = `mom[t-1]` (the previous period's initial MoM
   print — a pure PIT naive benchmark).
2. `trailing_sigma[t]` = expanding-window standard deviation of
   `realized_surprise` over the 24 events immediately preceding t
   (events [t-24, t-1], no look-ahead).
3. `standardized_surprise[t]` = `realized_surprise[t]` / `trailing_sigma[t]`.
4. Events where fewer than 24 prior events have accrued are excluded from
   all bucket statistics (the first 26 events per release type are warm-up
   and appear only in descriptive listings, not in the cell table —
   26 rather than 25 because `realized_surprise` is undefined at indices
   0-1, so the first index with 24 non-NaN priors is 26; post-run
   reconciliation, direction conservative: one extra event dropped,
   no look-ahead added).
5. COVID exclusion: events with `period` in 2020-03 through 2020-06 inclusive
   are excluded from bucket statistics and listed separately in the results
   narrative as COVID-disrupted prints.

---

## 4. Buckets (frozen)

| Bucket | Condition |
|---|---|
| hot | standardized_surprise > +0.5 |
| inline | −0.5 ≤ standardized_surprise ≤ +0.5 |
| cold | standardized_surprise < −0.5 |

Thresholds: +0.5σ / −0.5σ, frozen.

---

## 5. Outcomes

### 5.1 Market series

| Outcome | Source | Unit |
|---|---|---|
| DGS10 | `data/fred/DGS10.parquet`, column `us10y` | basis points (×100) |
| T10Y2Y | `data/fred/T10Y2Y.parquet`, column `spread_2s10s` | basis points (×100) |
| DTWEXBGS | `data/fred/DTWEXBGS.parquet`, column `broad_dollar` | percent (×100 / prior) |
| SPY | `data/yahoo/SPY.parquet`, column `close` | percent return |

Date index: `date` for FRED series, `Date` for SPY.

### 5.2 Horizon definitions

- **same_session (h0):** close of the release day vs. prior trading day close.
  CPI and NFP are released at 08:30 ET, before the equity open; the
  release-day close captures the market's reaction.
- **h1:** close of release_day+1 trading session vs. prior close.
- **h5:** close of release_day+5 trading sessions vs. prior close.
- **h21:** close of release_day+21 trading sessions vs. prior close.

All horizons are measured as absolute bp change (rates) or percent change
(USD, SPY). DGS10 and T10Y2Y: outcome = (level[t+h] − level[t-1]) × 100 bp.
DTWEXBGS and SPY: outcome = (price[t+h] / price[t-1] − 1) × 100 pct.

### 5.3 Holiday alignment

If a release date (realtime_start) falls on a day with no market data
(weekend or holiday), the event is aligned to the nearest following trading
session (the next date present in the SPY close series).

### 5.4 Supplementary: regime-conditioned cells

Using `data/regime/regime_history.parquet`, column `quad` (Q1/Q2/Q3/Q4).
Regime label for an event = the `quad` value on the release date (latest-
revised label, NOT PIT — clearly labeled `revision_optimistic`).
Cells: hot-CPI-in-Q1, hot-CPI-in-Q3, etc. Only cells with n ≥ 8 are
reported. Q1=Goldilocks, Q2=Reflation, Q3=Stagflation, Q4=Quad4.

---

## 6. Era splits

### CPI

| Era | Periods |
|---|---|
| pre-2010 | 1997-01 to 2009-12 |
| 2010-2020-02 | 2010-01 to 2020-02 |
| 2021+ | 2021-01 to present |

### NFP

| Era | Periods |
|---|---|
| 2010-2020-02 | 2010-01 to 2020-02 |
| 2021+ | 2021-01 to present |

COVID months (2020-03..2020-06) are excluded from all era-bucket cells and
listed separately.

---

## 7. Statistics

Per (release, bucket, outcome, horizon, era) cell:

- **n:** number of events with a valid outcome measurement.
- **mean:** arithmetic mean of the outcome.
- **median:** sample median.
- **ci_lo, ci_hi:** block bootstrap 95% confidence interval (event-level
  resampling, 800 draws, seed=7 — house convention). Resampling unit = event
  (no time-series blocking required since events are monthly and the h21
  outcome windows of adjacent events may slightly overlap).

**Overlap caveat:** 21-session windows for adjacent monthly CPI/NFP prints
may overlap by approximately 0–5 trading days at month boundaries. In v1 no
correction is applied; this caveat is printed in the results header. Effective
inflation in the CI is small given h21 events are ~21 sessions apart.

**Pure numpy/pandas implementation only** (no scipy, sklearn, statsmodels).

---

## 8. Output contract

### 8.1 Machine-readable: `results/playbook_v1.json`

Array of records, each:

```json
{
  "release": "cpi" | "nfp",
  "bucket": "hot" | "inline" | "cold",
  "outcome": "dgs10_bp" | "t10y2y_bp" | "dollar_pct" | "spy_pct",
  "horizon": "h0" | "h1" | "h5" | "h21",
  "era": "pre2010" | "2010_2020" | "2021plus" | "all",
  "regime": null | "Q1" | "Q2" | "Q3" | "Q4",
  "n": <int>,
  "mean": <float>,
  "median": <float>,
  "ci_lo": <float>,
  "ci_hi": <float>
}
```

### 8.2 Human-readable: `results/RESULTS_PLAYBOOK_V1.md`

Contains full tables per release × era × outcome, the COVID-disrupted event
listing, regime-conditioned cells (n≥8 only), and the descriptive header
banner.

---

## 9. PIT compliance

- The initial-print extraction uses only the first-vintage value for each
  period (earliest `realtime_start` per period).
- The naive prior and trailing sigma use only earlier-period initial prints
  (no look-ahead).
- The regime labels are `revision_optimistic` (declared in all outputs).
- No revised series values are used in surprise construction.

---

## 10. Kill criteria (pre-registered)

This is a descriptive study; there are no kill criteria in the sense of
signal performance gates. If fewer than 8 events populate a (bucket × era)
cell, that cell is suppressed from display (n<8 note shown).
