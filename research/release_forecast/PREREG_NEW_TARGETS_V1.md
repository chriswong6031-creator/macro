# Pre-Registration V1 — MRI New Targets (PCE Headline, PCE Core, PPI Final Demand, Retail Sales Scaffold)

**Frozen:** 2026-07-08 (written BEFORE any backtest was run)
**Program:** Macro Release Intelligence (MRI), PR-N (Round 1 science)
**Branch:** claude/mri-w10-track-n
**Spec attempt:** #1 of 2 for pce_headline, pce_core, ppi_finaldemand; scaffold-only for retail_sales
**Ruling:** MRI-R23 (new-target charter) per §11.1 of research/MACRO_RELEASE_INTEL_MASTERPLAN_BY_FABLE.md
**Status:** FROZEN — no model spec changes after this commit

Anti-mining commitment: this document is committed BEFORE the backtest is run (before
`backtest_new_targets_v1.py` produces any output). No hyperparameters, feature weights, kill-rule
interpretations, or feature set changes may be made after results are observed. Per §6 of the
masterplan: if attempt #1 fails a target's kill rule, a second attempt (#2 of 2) requires a
program-level adjudication before it can begin. The attempt clock for retail_sales does NOT start
until RSAFS parquet and release calendar entries accrue on disk.

---

## 0. Scope and Governing Rules

Track N adds four new release targets to the Macro Release Intelligence system:

1. **pce_headline** — PCE Price Index (PCEPI) MoM SA, ridge model, attempt #1 of 2
2. **pce_core** — PCE Price Index ex Food & Energy (PCEPILFE) MoM SA, ridge model, attempt #1 of 2
3. **ppi_finaldemand** — PPI Final Demand (PPIFIS) MoM SA, ridge model, attempt #1 of 2
4. **retail_sales** — Retail & Food Services (RSAFS) MoM SA, SCAFFOLD-ONLY (no model this round)

All outputs are **display_only=True, authority=False**. Nothing here conditions scoring, sizing,
allocation, or any mechanical decision. See masterplan §3.1 (MRI-R1, MRI-R2, MRI-R3, MRI-R4).

The governing common protocol (unchanged from PREREG_V2.md / §11.1 common protocol):

- Ridge regression, lambda=1.0 (closed-form numpy, no sklearn/statsmodels/scipy.stats)
- Z-scored features, complete-case per prediction row
- Expanding-window walk-forward, MIN_TRAIN_OBS=60
- Empirical residual quantiles, MIN_QUANTILE_OBS=24
- COVID months (2020-03..2020-06) excluded from era stats (printed separately)
- Targets = ALFRED first prints (pit_vintage via vintages.parquet)
- Non-vintaged legs declared per leg in provenance
- Kill rule (frozen): model MAE >= naive_prior MAE in BOTH the full window AND the 2021+ slice
  -> that target ships benchmark_only; max 2 spec attempts per target

---

## 1. Data Sources

### 1.1 PCEPI (PCE Price Index, headline)

**Series:** PCEPI
**Source:** ALFRED vintages at `data/fred_vintage/vintages.parquet` (series column = 'PCEPI')
**Format:** index levels, seasonally adjusted monthly
**Vintage coverage:** 2000-07 through latest (311 rows as of 2026-07-08 inventory)
**Revision status:** ALFRED-vintaged; initial prints used via `knowable_series` PIT filter
**Period coverage for model:** 2000-07 onward (usable MoM from 2000-08)

### 1.2 PCEPILFE (PCE Price Index ex Food & Energy, core)

**Series:** PCEPILFE
**Source:** ALFRED vintages (same parquet)
**Format:** index levels, seasonally adjusted monthly
**Vintage coverage:** 2000-07 through latest (311 rows as of 2026-07-08 inventory)
**Revision status:** ALFRED-vintaged; initial prints via `knowable_series`
**Period coverage for model:** 2000-07 onward (usable MoM from 2000-08)

### 1.3 PPIFIS (PPI Final Demand, total)

**Series:** PPIFIS
**Source:** ALFRED vintages (same parquet)
**Format:** index levels, seasonally adjusted monthly
**Vintage coverage:** 2014-02 through latest (148 rows as of 2026-07-08 inventory)
**Revision status:** ALFRED-vintaged; initial prints via `knowable_series`
**THIN-HISTORY CAVEAT:** PPIFIS vintage history begins 2014-02. After the MIN_TRAIN_OBS=60
burn-in, the first walk-forward prediction is at approximately 2019-02, yielding fewer than
~90 total predictions over the full window, and the 2021+ era will have approximately 50-60
predictions. This is too few for high-confidence statistics; all PPI tables are printed with
this caveat and the kill rule is applied as written (no relaxation for thin history).

### 1.4 PPIFES (PPI Final Demand ex Food & Energy, services proxy)

**Series:** PPIFES
**Source:** ALFRED vintages (same parquet)
**Format:** index levels, seasonally adjusted monthly
**Vintage coverage:** 2014-02 through latest (148 rows as of 2026-07-08 inventory)
**Revision status:** ALFRED-vintaged; initial prints via `knowable_series`
**Usage:** used as a momentum feature for pce_core and ppi_finaldemand (own lags
via `_last_n_mom_lags`)

### 1.5 Sticky / Median / Flexible CPI (Atlanta/Cleveland Fed series)

**Series:** STICKCPIM157SFRBATL, MEDCPIM158SFRBCLE, FLEXCPIM157SFRBATL
**Source:** ALFRED vintages at `data/fred_vintage/vintages.parquet` (same parquet as own-series)
**Coverage in vintages:** 2014-02 onward (148–149 rows as of 2026-07-08)
**Revision status:** ALFRED-vintaged; initial prints used via `knowable_series` PIT filter.
This is the same path the CPI champion uses in `build_cpi_features` via the injected
`last_n_mom_lags_fn`. Walk-forward steps before 2014-02 will receive None for these features
(correct: the series did not exist / was not published then).

**AMENDMENT (2026-07-08, PIT fix — Opus review):** The original implementation read from
`data/fred/*.parquet` (latest-revised values). This was a data-source correctness error: the
CPI champion sourced these same series from ALFRED vintages. The fix moves all three to
`knowable_series` / `_last_n_mom_lags` on the vintages parquet. This is a bug fix, not a
new spec attempt; the feature set and lambda are unchanged.
**Usage:** momentum lag-1 for pce_headline and pce_core (identical series to CPI champion)

### 1.6 PPIFIS momentum (via vintages)

**Usage for pce_headline:** own 1-lag PPIFIS MoM from vintages (PIT-safe, ALFRED-vintaged)
**Usage for ppi_finaldemand:** own lags 1-3 of PPIFIS MoM from vintages

### 1.7 PPIFES momentum (via vintages)

**Usage for pce_core:** PPIFES 1-lag MoM from vintages
**Usage for ppi_finaldemand:** PPIFES 1-lag MoM from vintages

### 1.8 Gasoline (GASREGW, weekly reference price)

**Source:** `data/fred/GASREGW.parquet`
**Coverage:** 1990-08 through latest (weekly, column 'gasoline_regular_weekly')
**Revision status:** NOT revised (EIA survey data); declared `unrevised_legs`
**Usage:** reference-month average vs prior-month average MoM for pce_headline and ppi_finaldemand.
PIT alignment: only weeks strictly within [ref_month_start, ref_month_end) are used; same
implementation as the CPI champion `build_cpi_features`.

### 1.9 RSAFS (Retail & Food Services Sales — SCAFFOLD ONLY)

**Series:** RSAFS
**Status:** DATA ABSENT. `data/fred/RSAFS.parquet` does not exist as of 2026-07-08 and RSAFS
is not in `data/fred_vintage/vintages.parquet`. The series and release calendar entries are
expected to accrue from the 2026-07-08 nightly (per MRI-R23).
**Treatment:** retail_sales scaffold emits `benchmark_only` / `no_data` projection (AHE
pattern). The attempt clock (#1 of 2) does NOT start until RSAFS parquet and release
calendar entries are on disk. The machinery ships so that when the data appears, the
model can be specified and run.

---

## 2. Frozen Model Specs (transcribed verbatim from §11.1 of masterplan)

### 2.1 pce_headline

**Target:** PCEPI MoM SA (% change from levels using initial ALFRED prints)
**Vintage start:** 2000-07 onward
**Feature panel (ordered; own lags first per walk-forward contract):**

```
pce_hl_mom_lag1        — own MoM lag 1 (PCEPI initial prints via knowable_series)
pce_hl_mom_lag2        — own MoM lag 2
pce_hl_mom_lag3        — own MoM lag 3
sticky_mom_lag1        — Sticky CPI MoM lag 1 (STICKCPIM157SFRBATL, ALFRED-vintaged, first-print)
median_mom_lag1        — Median CPI MoM lag 1 (MEDCPIM158SFRBCLE, ALFRED-vintaged, first-print)
flex_mom_lag1          — Flexible CPI MoM lag 1 (FLEXCPIM157SFRBATL, ALFRED-vintaged, first-print)
ppifis_mom_lag1        — PPI Final Demand MoM lag 1 (PPIFIS vintages, PIT-safe)
gasoline_mom           — Gasoline reference-month average MoM (GASREGW, unrevised)
```

**Model:** Ridge, lambda=1.0, z-scored, complete-case, expanding walk-forward, MIN_TRAIN_OBS=60
**Quantiles:** empirical residual quantiles, MIN_QUANTILE_OBS=24
**Kill rule:** model MAE >= naive_prior in BOTH full AND 2021+ -> benchmark_only

### 2.2 pce_core

**Target:** PCEPILFE MoM SA (% change from levels using initial ALFRED prints)
**Vintage start:** 2000-07 onward
**Feature panel (ordered; own lags first):**

```
pce_core_mom_lag1      — own MoM lag 1 (PCEPILFE initial prints via knowable_series)
pce_core_mom_lag2      — own MoM lag 2
pce_core_mom_lag3      — own MoM lag 3
sticky_mom_lag1        — Sticky CPI MoM lag 1 (STICKCPIM157SFRBATL, ALFRED-vintaged, first-print)
median_mom_lag1        — Median CPI MoM lag 1 (MEDCPIM158SFRBCLE, ALFRED-vintaged, first-print)
flex_mom_lag1          — Flexible CPI MoM lag 1 (FLEXCPIM157SFRBATL, ALFRED-vintaged, first-print)
ppifes_mom_lag1        — PPI Final Demand ex Food & Energy MoM lag 1 (PPIFES vintages, PIT-safe)
```

**Model:** Ridge, lambda=1.0, z-scored, complete-case, expanding walk-forward, MIN_TRAIN_OBS=60
**Quantiles:** empirical residual quantiles, MIN_QUANTILE_OBS=24
**Kill rule:** model MAE >= naive_prior in BOTH full AND 2021+ -> benchmark_only

### 2.3 ppi_finaldemand

**Target:** PPIFIS MoM SA (% change from levels using initial ALFRED prints)
**Vintage start:** 2014-02 onward (THIN — see §1.3 caveat)
**Feature panel (ordered; own lags first):**

```
ppi_hl_mom_lag1        — own MoM lag 1 (PPIFIS initial prints via knowable_series)
ppi_hl_mom_lag2        — own MoM lag 2
ppi_hl_mom_lag3        — own MoM lag 3
gasoline_mom           — Gasoline reference-month average MoM (GASREGW, unrevised)
ppifes_mom_lag1        — PPI ex Food & Energy MoM lag 1 (PPIFES vintages, PIT-safe)
```

**Model:** Ridge, lambda=1.0, z-scored, complete-case, expanding walk-forward, MIN_TRAIN_OBS=60
**Quantiles:** empirical residual quantiles, MIN_QUANTILE_OBS=24
**Kill rule:** model MAE >= naive_prior in BOTH full AND 2021+ -> benchmark_only
**THIN-HISTORY NOTE:** First walk-forward prediction approximately 2019-02 (after 60-obs burn-in
from 2014-02 start). Expect ~90 total predictions, ~50-60 in 2021+. Results printed with explicit
caveat; statistics are informative but not high-confidence.

### 2.4 retail_sales (SCAFFOLD ONLY)

**Target:** RSAFS MoM SA
**Status:** SCAFFOLD-ONLY. Data absent as of 2026-07-08. Machinery emits no_data projection.
**Planned feature panel (for future attempt #1 when data accrues):** TBD at adjudication
**Attempt clock:** does NOT start until RSAFS parquet and release calendar entries are on disk
**Output:** `{"release": "retail_sales", "point": None, ..., "pit_provenance": {"reason": "no_data_rsafs_absent"}}`

---

## 3. PIT Protocol (unchanged from PREREG_V1.md / PREREG_V2.md)

For each target, the walk-forward proceeds as:

1. Collect all initial ALFRED prints for the own series (PCEPI, PCEPILFE, or PPIFIS) via
   `knowable_series(vintages, series, date(2099,1,1))` — the "all-time" view for building
   the sequence of records.
2. For each record row at index i (representing the actual target print for period P_i):
   - `step_asof` = day before `realtime_start` of that print (PIT decision date)
   - Build features using only data knowable at `step_asof`
   - ALFRED-vintaged features: use `knowable_series(vintages, series, step_asof)` PIT filter;
     includes sticky/median/flex (STICKCPIM157SFRBATL, MEDCPIM158SFRBCLE, FLEXCPIM157SFRBATL)
     which are present in vintages.parquet from 2014-02 onward (PIT fix 2026-07-08)
   - Non-vintaged features (GASREGW only): take latest values up to
     `step_asof` from the FRED parquet; declared as unrevised
3. Walk-forward: train on records 0..i-1, predict record i, once i >= MIN_TRAIN_OBS.
4. Residuals: `actual - predicted` accumulated in order.
5. Quantile intervals: empirical quantiles of residuals from strictly prior predictions
   (using result_pos, not idx, to avoid future-residual leakage — see backtest V1 fix).

---

## 4. Era Classification (unchanged from PREREG_V1.md)

- pre_2010: periods before 2010-01 (excluded from PPI evaluation due to thin history)
- 2010_2020: 2010-01 through 2020-02
- covid: 2020-03 through 2020-06 (printed separately, excluded from era stats)
- 2020_recovery: 2020-07 through 2020-12
- 2021_plus: 2021-01 onward

For PPI (thin history starting 2014-02): pre_2014 era will be empty by construction.
Pre-2019 rows exist but are almost entirely consumed by burn-in; only a small number
of predictions land in 2019-2020.

---

## 5. Kill Rule (verbatim from §11.1 / PREREG_V1.md)

Model is killed (benchmark_only) if and only if:

  `mae_model_full >= mae_naive_full` AND `mae_model_2021plus >= mae_naive_2021plus`

Both conditions must hold simultaneously. A model that beats naive in the full window
but not 2021+ (or vice versa) is NOT killed. On kill, the target emits a benchmark
projection (naive_prior, trailing_3m, ar3) without a model point.

PPI thin history note: "full" for PPI is "all available walk-forward predictions"
(approximately 2019-02 onward). The kill rule applies to this reduced window.

---

## 6. Non-Modelled Outputs

All four targets emit the same schema as the CPI/NFP champion projections:

```json
{
  "release": "pce_headline",
  "asof": "YYYY-MM-DD",
  "point": <float or null>,
  "p10": <float or null>,
  "p25": <float or null>,
  "p50": <float or null>,
  "p75": <float or null>,
  "p90": <float or null>,
  "confidence": <float or null>,
  "confidence_components": {"interval_rank": <float or null>, "input_completeness": <float>},
  "input_completeness": <float>,
  "benchmark_set": {
    "naive_prior": <float or null>,
    "trailing_3m": <float or null>,
    "ar_model": <float or null>
  },
  "surprise_skew": {"sigma": <float or null>, "sigma_scale_pp": <float or null>,
                    "tag": <str or null>, "inline_band": 0.35},
  "pit_provenance": {...},
  "display_only": true,
  "authority": false
}
```

retail_sales scaffold emits all nulls with `pit_provenance.reason = "no_data_rsafs_absent"`.

---

## 7. Amendment Protocol

Amendments to this document are allowed only for bug fixes (e.g., implementation errors that
do not constitute a new spec attempt) and must be clearly labeled as AMENDMENT with date and
rationale. No amendment may change: the feature set, the lambda, the kill rule threshold, or
the era definitions.
