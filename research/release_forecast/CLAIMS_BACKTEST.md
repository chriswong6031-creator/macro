# Claims Walk-Forward Backtest — MRI Package F1

**OUTCOME: BENCHMARK-ONLY MODE SELECTED**

The §6 falsifier was applied mechanically per the frozen decision rule (MRI §6,
one spec, one run, no iteration). The ridge-AR model fails to beat naive_prior in
both the full window AND the 2021+ slice. Claims ships benchmark-only.

---

**Run date:** 2026-07-07  
**Spec:** Frozen before any results were observed (one spec per F1, no iterations).  
**Algorithm:** Ridge (lambda=1.0, numpy closed-form), expanding window, min 60 obs.  
**Target:** ICSA initial print level in thousands (ALFRED initial prints, PIT law).  
**Features:** icsa_lag1, icsa_lag2, icsa_lag3, icsa_trailing_4w, ccsa_lag1, holiday_dummy.  
**Kill rule (§6 falsifier):** model MAE >= naive_prior MAE in BOTH full window AND 2021+ slice → benchmark_only.  
**Trailing baseline:** genuine trailing_4w = mean of last 4 initial prints (thousands). Weekly
releases use 4-print trailing mean, not 3-print (trailing_3m applies to monthly releases only).

---

## Kill Rule Result

| Window | MAE model (k) | MAE naive (k) | Model beats naive? |
|--------|--------------|---------------|-------------------|
| Full (all) | 40.839 | 28.673 | **NO** |
| 2021+ slice | 24.042 | 14.790 | **NO** |

**Kill rule triggered: YES → claims ships in benchmark_only mode.**

The model is replaced by `{"mode": "benchmark_only", "reason": "..."}` in the projection block.
Benchmarks (naive_prior, trailing_4w, ar_model) are still shown and still graded.

---

## Era-Split MAE Table

Units: thousands of initial claims (raw ICSA level / 1000). Note: weekly residuals
have strong autocorrelation (MRI-R9); effective sample size is substantially smaller
than n. The 2010–2019 pre-COVID line is printed for visibility per the task spec.

Numbers are from the single pre-registered run. No hand-typed values — all figures
are machine-computed from data/fred_vintage/vintages.parquet (ICSA series).

| Era | n | MAE model | MAE naive | MAE trailing4w | MAE AR3 | Cov p10-p90 | Skew HR | Wilson 95% CI | Skew n |
|-----|---|-----------|-----------|----------------|---------|-------------|---------|---------------|--------|
| Full (all) | 831 | 40.839 | 28.673 | 45.531 | 35.383 | 76.6% | 0.575 | [0.540, 0.609] | 785 |
| 2010–2020-02 | 502 | 11.265 | 12.167 | 11.780 | 11.182 | 86.6% | 0.632 | [0.587, 0.674] | 467 |
| 2010–2019 (pre-COVID visibility) | 493 | 11.347 | 12.260 | 11.839 | 11.270 | 86.4% | 0.631 | [0.586, 0.674] | 458 |
| COVID (2020-03..06) | 17 | 1134.618 | 686.059 | 1439.912 | 894.590 | 5.9% | 0.647 | [0.413, 0.827] | 17 |
| 2020-07..12 (recovery gap) | 26 | 81.428 | 70.231 | 95.288 | 80.724 | 19.2% | 0.560 | [0.371, 0.733] | 25 |
| 2021+ | 286 | 24.042 | 14.790 | 17.366 | 22.667 | 69.2% | 0.475 | [0.416, 0.533] | 276 |

*No pre-2010 era row: ICSA vintages in data/fred_vintage/vintages.parquet start 2009-05-30;
with MIN_TRAIN_OBS=60 the first walk-forward prediction falls in 2010. Zero pre-2010 predictions
were produced by this run (era counts verified: {2010_2020: 502, covid: 17, 2020_recovery: 26,
2021_plus: 286}).*

*Coverage computed using expanding residual history (only prior-position residuals); null for
eras where fewer than 24 prior predictions exist at the first prediction in the slice.*

---

## S3 — Kill Rule Operationalization and Slice Verdicts

Per masterplan §6: "fails to beat naive over the full era-split table." The applied
operationalization is: model MAE >= naive MAE in BOTH (a) the full window AND (b) the
2021+ slice. This is the pre-registered falsifier.

**Slice verdicts:**

- **Full window (n=831):** model 40.839 vs naive 28.673 → model LOSES. Kill rule arm 1 triggered.
- **2021+ slice (n=286):** model 24.042 vs naive 14.790 → model LOSES. Kill rule arm 2 triggered.
- **2010–2020 slice (n=502):** model 11.265 vs naive 12.167 → model BEATS naive by 0.902k.

The model DOES beat naive on the 2010–2020 stable era. This result is printed, not hidden.
The benchmark_only verdict rests on the full window and 2021+ slice results above, both of
which fail. The 2010–2020 pass does not override the verdict; the kill rule requires both
arms to be non-failing for the model to be active.

---

## Diagnosis

The model fails the kill rule for two structurally different reasons:

1. **COVID distortion (2020-03..06):** MAE model=1135k vs naive=686k. The COVID
   shock caused claims to spike from ~220k to >6,000k in weeks. Any lag-based model
   trained on pre-COVID data catastrophically under-predicts the spike. This alone
   blows up the full-window MAE from ~15k to ~41k.

2. **Post-COVID regime shift (2021+):** Even excluding COVID, the model (24.0k)
   fails to beat naive (14.8k) in 2021+. The inflation-era labor market produced
   unprecedented claims volatility that the expanding-window ridge over-fits to
   historical patterns. AR3 (22.7k) also fails to beat naive in this era.

3. **2010-2019 (stable era):** The model (11.3k) DOES beat naive (12.2k) in the
   pre-COVID stable era. This is where the expanding-window ridge has value. But
   the post-2020 distribution shift (two failure modes above) overrides this.

The naive prior (last week's print) is a near-random-walk benchmark for weekly
claims, and is exceptionally hard to beat due to strong AR(1) structure combined
with structural breaks at COVID and the post-COVID regime. The kill rule is the
right outcome here.

---

## Benchmark-Only Mode Contract

Per MRI §6: the claims card ships with:

```json
{
  "projection": {
    "mode": "benchmark_only",
    "reason": "Walk-forward MAE (40.8k) fails to beat naive_prior (28.7k) on the era-split table (full window) and 2021+ slice (24.0k vs 14.8k). F1 kill rule triggered: benchmark-only mode per MRI §6 falsifier."
  },
  "benchmark_set": {
    "naive_prior": <last week initial print in thousands>,
    "trailing_4w": <mean of last 4 initial prints in thousands>,
    "ar_model": <ridge AR3 on levels in thousands>,
    "cleveland_nowcast": null,
    "market_implied": null
  }
}
```

Benchmarks are still graded on the forward ledger. The scoreboard accumulates
MAE for naive_prior, trailing_4w, and ar_model even in benchmark-only mode.

---

## Notes

- **MRI-R9 (era law):** Weekly claims residuals have strong autocorrelation. The
  effective n for statistical inference is substantially smaller than the row count
  (block-aware errors would be needed for valid CIs). Coverage and skew hit-rates
  should be interpreted with this caveat.
- **Unit:** thousands (ICSA raw / 1000). The naive prior of ~215k means "last
  week's print was 215,000 initial claims."
- **Trailing benchmark:** Uses `trailing_4w` (mean of last 4 prints) not `trailing_3m`
  because claims is weekly. The scoreboard grades this key explicitly.
- **No iteration:** This is the single pre-registered spec run. The result stands.
  Anti-mining law (MRI §6): no spec changes after seeing results.
- **No pre-2010 bucket:** ICSA vintages start 2009-05-30; MIN_TRAIN_OBS=60 means the
  first walk-forward prediction is in 2010. The pre-2010 row does not appear.
- **COVID residuals:** COVID-era residuals (~1000k spikes, 2020-03..06) are included
  un-excluded in quantile bands per prereg. This is currently moot because benchmark_only
  mode suppresses the projection block (no quantile intervals are shown). Must be revisited
  if claims ever exits benchmark_only and quantile bands are re-enabled.
- **Forward gates:** Even in benchmark-only mode, the scoreboard accrues. If n≥12
  forward prints show naive_prior MAE > benchmarks MAE and Wilson LB > 0.5, a
  model-mode re-entry proposal may be adjudicated (new separate program, not this F1).
