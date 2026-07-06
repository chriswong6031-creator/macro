# DISP-GATE-1 — Dispersion Regime Descriptive Readout

**Vintage:** 2026-07-06T14:40Z
**Bound by:** `research/dispersion/L3_PREREG.md` (frozen design)
**Status:** DEFER
**Framing:** Display-only, fire-tape counterfactual. No held-position ledger exists.
  All outcomes attach to replay-tape fire events; no live position tracking implied.

> **HARD CONSTRAINT (RUL-F3.7):** `gross_mult_live` is and remains 1.0 regardless
> of this readout. This study can only enable a display flag; no sizing change is
> authorized by any outcome of this batch.

---

## MANDATORY DISCLOSURE: Panel Survivorship

> **PANEL SURVIVORSHIP (structural limitation):**
> PANEL SURVIVORSHIP DISCLOSED: breadth/_closes_deep.parquet is today's surviving universe backfilled through history. All tickers are currently active (zero delisted/inactive in last 365d). Per-date non-null name count rises monotonically from sparse early history to today's full universe. The expanding-window percentile denominator (CSD history since inception) is therefore computed against a survivor-biased distribution: surviving stocks carry lower historical idiosyncratic dispersion (they include no Enron-style blowups, M&A-departed names, or delisted tickers that blew up cross-sectional variance). This biases the regime percentile level — surviving-universe CSD is understated at early dates — which may shift lean_in/lean_out state assignments relative to a full-universe panel. Because all fires are 2022+ and the panel universe is largest and most stable in recent years, the bias is lowest in the fire population window. However, the CSD percentile denominator reaches back to 1962 under the expanding basis and the early-history survivor-only distribution inflates the denominator, potentially understating the true percentile rank of recent CSD values. All regime state assignments carry this caveat. The trailing-252d sensitivity basis (using only 252-day rolling CSD) is less affected since it avoids the 60-year survivor-only denominator. NO delisted/inactive correction has been applied. This is a structural limitation of the panel; results are descriptive and should not be used for formal inference without a delisted-inclusive universe.

---

## MANDATORY DISCLOSURE: Episode-Clustering

> **CLUSTERING METHOD (prereg compliance):**
> PREREG DEVIATION CORRECTED (PR-A2 fix): Original build used TICKER_YYYY-Www per-ticker ISO-week clustering. This deviated from L3_PREREG.md Standing Notes lines 122-124 which freeze clustering as 'contiguous blocks within ±30d'. The original scheme (a) gave different cluster IDs to different tickers on the same macro-shock date (missing cross-ticker tape correlation) and (b) could split fires 2-3 days apart across an ISO-week boundary. This build uses the prereg-spec BLOCK_<YYYYMMDD> scheme: fires within 30 calendar days of a block's start share one cluster ID regardless of ticker. This narrows n_clusters and widens CIs relative to the original build (fewer, larger clusters = more conservative).

---

## In plain English

We looked at whether stock-picking fires from our system perform differently
depending on the market's 'dispersion regime' — whether individual stocks are
moving independently (lean_in, good for selection) or all moving together in a
macro-driven tape (lean_out, where selection historically earns little). We
reconstructed what the regime indicator would have shown at the time of each
fire, then measured how often fires ended in a painful drawdown (stop5 = drew
down 5%+ in 21 days) or went nowhere (dead_money = returned less than ±2%).
This is a descriptive readout only — no sizing changes and no promotion gates
are evaluated here.
Note: the panel used to compute historical CSD percentiles is a survivor-only
universe (today's active stocks backfilled). See survivorship disclosure above.

---

## 1. Feasibility Gate (printed before any statistic)

- Total fires in population: **49,939**
- Fires excluded (< 252 prior panel bars): **0** (0.0%)
- Fires included in analysis: **49,939**
- Episode clusters (TICKER_YYYY-Www): **41**

### Panel coverage

- Panel range: 1962-01-02 .. 2026-07-02
- Total panel dates: 16,233
- Total panel tickers: 1,504

Per-year date counts (data-quality column):

| Year | Trading dates |
|------|--------------|
| 1962 | 252 |
| 1963 | 251 |
| 1964 | 253 |
| 1965 | 252 |
| 1966 | 252 |
| 1967 | 251 |
| 1968 | 226 |
| 1969 | 250 |
| 1970 | 254 |
| 1971 | 253 |
| 1972 | 251 |
| 1973 | 252 |
| 1974 | 253 |
| 1975 | 253 |
| 1976 | 253 |
| 1977 | 252 |
| 1978 | 252 |
| 1979 | 253 |
| 1980 | 253 |
| 1981 | 253 |
| 1982 | 253 |
| 1983 | 253 |
| 1984 | 253 |
| 1985 | 252 |
| 1986 | 253 |
| 1987 | 253 |
| 1988 | 253 |
| 1989 | 252 |
| 1990 | 253 |
| 1991 | 253 |
| 1992 | 254 |
| 1993 | 253 |
| 1994 | 252 |
| 1995 | 252 |
| 1996 | 254 |
| 1997 | 253 |
| 1998 | 252 |
| 1999 | 252 |
| 2000 | 252 |
| 2001 | 248 |
| 2002 | 252 |
| 2003 | 252 |
| 2004 | 252 |
| 2005 | 252 |
| 2006 | 251 |
| 2007 | 251 |
| 2008 | 253 |
| 2009 | 252 |
| 2010 | 252 |
| 2011 | 252 |
| 2012 | 250 |
| 2013 | 252 |
| 2014 | 252 |
| 2015 | 252 |
| 2016 | 252 |
| 2017 | 251 |
| 2018 | 251 |
| 2019 | 252 |
| 2020 | 253 |
| 2021 | 252 |
| 2022 | 251 |
| 2023 | 250 |
| 2024 | 252 |
| 2025 | 250 |
| 2026 | 125 |

---

## 2. Basis Reconciliation

- Flip rate (expanding vs trailing-252): **0.3141** (15686 of 49939 fires flip state)
- 15% NON-STATIONARITY flag triggered: **True**

---

## 3. Arm Summaries

*Thresholds: lean_in = pctile >= 0.66; lean_out = pctile <= 0.33. Matches `engine/dispersion.py`.*

### Basis: expanding

| State | N fires | N clusters | stop5 rate | stop5 CI 90% | dead_money rate | dead_money CI 90% | mean ret_21d |
|-------|---------|-----------|-----------|--------------|----------------|-----------------|-------------|
| lean_in | 10,586 | 17 | 35.8% | sparse — descriptive only | 19.4% | sparse — descriptive only | 2.49% |
| neutral | 28,887 | 39 | 37.2% | [32.1%, 43.2%] | 17.9% | [16.1%, 20.0%] | 2.56% |
| lean_out | 10,466 | 20 | 49.3% | sparse — descriptive only | 18.6% | sparse — descriptive only | -0.40% |

**lean_out vs lean_in stop5 gap:** +13.5pp  (directional; >=5pp)

### Basis: trailing_252

| State | N fires | N clusters | stop5 rate | stop5 CI 90% | dead_money rate | dead_money CI 90% | mean ret_21d |
|-------|---------|-----------|-----------|--------------|----------------|-----------------|-------------|
| lean_in | 17,428 | 26 | 36.9% | [28.5%, 46.9%] | 18.7% | [16.1%, 21.8%] | 2.60% |
| neutral | 14,421 | 34 | 38.0% | [32.4%, 45.0%] | 18.8% | [16.9%, 20.7%] | 2.36% |
| lean_out | 18,090 | 28 | 43.0% | [37.6%, 49.3%] | 17.8% | [16.0%, 19.6%] | 0.93% |

**lean_out vs lean_in stop5 gap:** +6.1pp  (directional; >=5pp)

---

## 4. Covariate Splits (descriptive — not verdict cells)

*SPY 21d backward return terciles (contemporaneous tape backdrop):*
*   spy_down: SPY_21d < -5% | spy_flat: -5% .. +5% | spy_up: > +5%*
*Realized vol terciles: low/mid/high (data-driven boundaries).*

### Basis: expanding — SPY tercile splits

| SPY tercile | N | lean_in stop5 | neutral stop5 | lean_out stop5 |
|------------|---|--------------|--------------|----------------|
| spy_down (n=3050) | | 44.4% | 35.0% | 57.1% |
| spy_flat (n=39271) | | 33.3% | 38.1% | 48.8% |
| spy_up (n=7618) | | 42.7% | 34.4% | 50.1% |

### Basis: expanding — realized vol tercile splits
*(vol boundaries: p33=12.1%, p66=16.6% annualized)*

| Vol tercile | lean_in stop5 | neutral stop5 | lean_out stop5 |
|-------------|--------------|--------------|----------------|
| vol_low | 35.5% | 40.5% | 47.8% |
| vol_mid | 39.0% | 35.3% | 47.7% |
| vol_high | 33.9% | 36.0% | 59.5% |

### Basis: trailing_252 — SPY tercile splits

| SPY tercile | N | lean_in stop5 | neutral stop5 | lean_out stop5 |
|------------|---|--------------|--------------|----------------|
| spy_down (n=3050) | | 44.2% | 37.8% | 40.4% |
| spy_flat (n=39271) | | 35.1% | 40.8% | 42.9% |
| spy_up (n=7618) | | 43.0% | 28.2% | 45.4% |

### Basis: trailing_252 — realized vol tercile splits
*(vol boundaries: p33=12.1%, p66=16.6% annualized)*

| Vol tercile | lean_in stop5 | neutral stop5 | lean_out stop5 |
|-------------|--------------|--------------|----------------|
| vol_low | 42.1% | 40.4% | 43.5% |
| vol_mid | 31.1% | 41.9% | 47.2% |
| vol_high | 39.9% | 30.2% | 38.9% |

---

## 5. Overall Verdict

**DEFER**

Defer reasons:
- flip_rate=31.4% > 15% — NON-STATIONARITY flag
- basis=expanding: cluster floor not met (lean_in=17, lean_out=20, floor=25)

---

## 6. Standing Notes

- Cumulative pooled replay trial count: **31** cells declared
  (15 exit_grid_v1 + 10 wait_grid_v1 + 6 disp_gate_v1 = 31)
- TrialLedger max()-basis: 15 (largest single declared budget)
- Both semantics disclosed per §0.5.6 of gap-map adjudication
- This study is display-only per US_BOARD_MEASUREMENT §Study 3
- `gross_mult_live = 1.0` HARD CONSTRAINT (RUL-F3.7)
- Nulls printed, not hidden. DEFER is a valid result.
- Episode-clustered bootstrap CIs where n_clusters >= 25; otherwise sparse note printed.
- **PANEL SURVIVORSHIP:** All CSD percentile assignments carry survivor-only bias.
  See mandatory disclosure at top of report. Trailing-252d sensitivity basis is
  less affected (avoids 60-year survivor-only denominator).
- **CLUSTERING:** Uses prereg-spec contiguous ±30d BLOCK clusters (cross-ticker),
  NOT the original per-ticker ISO-week scheme. CIs are wider (more conservative).
