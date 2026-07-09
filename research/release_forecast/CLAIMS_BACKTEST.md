# Claims Walk-Forward Backtest — MRI §9.1 Reconciliation

**OUTCOME: BENCHMARK-ONLY MODE SELECTED (both attempts failed)**

The §6 falsifier was applied mechanically per the frozen decision rule (MRI §6,
one spec per attempt, no iteration). Two attempts evaluated; both failed. Per the
anti-mining law, there is no attempt 3 without a program-level adjudication.

---

**Kill rule operationalization:** model MAE >= naive_prior MAE in BOTH (a) the full
window AND (b) the 2021+ slice -> benchmark_only. Both arms must fail for the kill rule
to trigger. (The model beating naive in one slice but not the other would NOT trigger.)

---

## Attempt 1 — Second-lane ridge spec (closed PR #1879)

**Source:** Closed PR #1879 (branch `claude/mri-package-f1`, commits c0aefea142,
9d4c42a899, 235455c4a1). Predated canonical PR #1877.

**Algorithm:** Ridge (lambda=1.0, numpy closed-form), expanding window, min 60 obs.
**Target:** ICSA initial print level in thousands (PIT law — ALFRED initial prints).
**Features:** icsa_lag1, icsa_lag2, icsa_lag3, icsa_trailing_4w, ccsa_lag1, holiday_dummy.
**Trailing baseline:** trailing_4w (mean of last 4 ICSA initial prints, in thousands).
**Note:** Trailing_3m is for monthly releases; weekly claims uses trailing_4w.

### Attempt 1 Kill Rule

| Window | MAE model (thousands) | MAE naive (thousands) | Model beats naive? |
|--------|----------------------|----------------------|-------------------|
| Full (all) | 40.839 | 28.673 | **NO** |
| 2021+ slice | 24.042 | 14.790 | **NO** |

**Kill rule triggered: YES → claims ships benchmark_only (attempt 1).**

### Attempt 1 Era-Split Table

Units: thousands of initial claims.

| Era | n | MAE model | MAE naive | MAE trailing4w | MAE AR3 | Cov p10-p90 | Skew HR | Wilson 95% CI | Skew n |
|-----|---|-----------|-----------|----------------|---------|-------------|---------|---------------|--------|
| Full (all) | 831 | 40.839 | 28.673 | 45.531 | 35.383 | 76.6% | 0.575 | [0.540, 0.609] | 785 |
| 2010–2020-02 | 502 | 11.265 | 12.167 | 11.780 | 11.182 | 86.6% | 0.632 | [0.587, 0.674] | 467 |
| 2010–2019 (pre-COVID visibility) | 493 | 11.347 | 12.260 | 11.839 | 11.270 | 86.4% | 0.631 | [0.586, 0.674] | 458 |
| COVID (2020-03..06) | 17 | 1134.618 | 686.059 | 1439.912 | 894.590 | 5.9% | 0.647 | [0.413, 0.827] | 17 |
| 2020-07..12 (recovery gap) | 26 | 81.428 | 70.231 | 95.288 | 80.724 | 19.2% | 0.560 | [0.371, 0.733] | 25 |
| 2021+ | 286 | 24.042 | 14.790 | 17.366 | 22.667 | 69.2% | 0.475 | [0.416, 0.533] | 276 |

*Attempt 1 table ported from closed PR #1879 (commit 235455c4a1). Numbers machine-computed
from data/fred_vintage/vintages.parquet (ICSA series). No hand-typed values.*

*No pre-2010 era row: ICSA vintages start 2009-05-30; with MIN_TRAIN_OBS=60 the first
walk-forward prediction falls in 2010. Era counts verified: {2010_2020: 502, covid: 17,
2020_recovery: 26, 2021_plus: 286}.*

### Attempt 1 Diagnosis

The ridge model fails the kill rule for two structurally different reasons:

1. **COVID distortion (2020-03..06):** MAE model=1,135 thousand vs naive=686 thousand. Lag-based models
   catastrophically under-predict the COVID spike.
2. **Post-COVID regime shift (2021+):** Even excluding COVID, the ridge model (24.0 thousand)
   fails to beat naive (14.8 thousand) in 2021+. AR3 (22.7 thousand) also fails.
3. **2010-2019 (stable era):** The ridge model (11.3 thousand) DOES beat naive (12.2 thousand). This
   result is printed, not hidden. The verdict rests on full window + 2021+ failure.

---

## Attempt 2 — Canonical IC4WSA spec (PR #1877)

**Source:** PR #1877 (canonical), engine/release_components_nfp.py:project_claims.

**Spec (frozen trivial spec per PREREG_V1.md):**
  - point = last IC4WSA (4-week MA initial print) knowable at decision date
  - comparison: IC4WSA value (level, thousands) vs ICSA actual (level, thousands)
  - This is the exact specification shipped in project_claims (knowable_series_fn on IC4WSA)
  - Walk-forward: for each ICSA initial print, use the IC4WSA value published before it

**Algorithm:** walk-forward using IC4WSA as point prediction (no regression model).
**Target:** ICSA initial print level in thousands (PIT law).
**Baselines:** naive (last ICSA initial print), trailing_4w (mean of last 4), AR3 Ridge on levels.

**Run date:** 2026-07-07
**All numbers are machine-computed from data/fred_vintage/vintages.parquet. Zero hand-typed values.**

### Attempt 2 Kill Rule

| Window | MAE IC4WSA (thousands) | MAE naive (thousands) | Model beats naive? |
|--------|----------------------|----------------------|-------------------|
| Full (all) | 43.855 | 27.914 | **NO** |
| 2021+ slice | 17.685 | 14.755 | **NO** |

**Kill rule triggered: YES → claims remains benchmark_only (attempt 2 confirms attempt 1).**

### Attempt 2 Era-Split Table

Units: thousands of initial claims. IC4WSA = 4-week MA of ICSA, used as point prediction.

| Era | n | MAE IC4WSA | MAE naive | MAE trail4w | MAE AR3 | Cov p10-p90 | Skew HR | Wilson 95% CI | Skew n |
|-----|---|-----------|-----------|-------------|---------|-------------|---------|---------------|--------|
| Full | 890 | 43.855 | 27.914 | 43.717 | 32.992 | 80.8% | 0.612 | [0.579, 0.644] | 845 |
| pre-2010 | 30 | 20.183 | 18.167 | 18.925 | 16.147 | 83.3% | 0.552 | [0.375, 0.716] | 29 |
| 2010–2020-02 | 531 | 12.262 | 12.409 | 12.008 | 11.516 | 87.4% | 0.644 | [0.601, 0.685] | 503 |
| 2010–2019 (pre-COVID visibility) | 522 | 12.311 | 12.500 | 12.068 | 11.602 | 87.2% | 0.644 | [0.601, 0.685] | 494 |
| COVID (2020-03..06) | 17 | 1434.147 | 686.059 | 1439.912 | 808.682 | 5.9% | 0.235 | [0.096, 0.473] | 17 |
| 2020-07..12 (recovery gap) | 26 | 95.221 | 70.231 | 95.289 | 85.504 | 11.5% | 0.500 | [0.314, 0.686] | 24 |
| 2021+ | 286 | 17.685 | 14.755 | 17.510 | 23.399 | 79.4% | 0.592 | [0.533, 0.649] | 272 |

*All numbers machine-computed from this run (backtest_release_forecast.py run 2026-07-07).*

### Attempt 2 Slice Verdicts

- **Full window (n=890):** IC4WSA 43.855 thousand vs naive 27.914 thousand → model LOSES. Kill rule arm 1 triggered.
- **2021+ slice (n=286):** IC4WSA 17.685 thousand vs naive 14.755 thousand → model LOSES. Kill rule arm 2 triggered.
- **2010–2020 slice (n=531):** IC4WSA 12.262 thousand vs naive 12.409 thousand → model beats naive by 0.147 thousand.

The IC4WSA spec DOES beat naive on the 2010–2020 stable era (by 0.147 thousand). This result is printed,
not hidden. The kill rule verdict rests on the full window and 2021+ failures. The 2010–2020 pass
does NOT override the verdict; both arms must be non-failing for the model to be active.

### Attempt 2 Diagnosis

1. **COVID distortion (2020-03..06):** MAE IC4WSA=1,434 thousand vs naive=686 thousand. The IC4WSA 4-week moving
   average cannot adjust fast enough during the COVID spike.
2. **Post-COVID regime shift (2021+):** IC4WSA (17.7 thousand) fails to beat naive (14.8 thousand). The AR1 random-walk
   structure of weekly claims is very hard to beat in the post-COVID inflation era.
3. **Tracking error:** IC4WSA is a lagging MA of ICSA — by construction it cannot outpredict the
   naive prior in a near-random-walk series at most horizons.
4. **2010-2019 (stable era):** IC4WSA (12.3 thousand) barely beats naive (12.5 thousand). The smoothing provides
   minimal benefit in stable periods.

---

## Final Verdict

**Claims ships in benchmark_only mode.** Two specs evaluated (attempt 1 = ridge, attempt 2 = IC4WSA).
Both failed the §6 kill rule. There is no attempt 3 without a program-level adjudication (anti-mining law).

Benchmarks (naive_prior, trailing_4w, ar_model) are graded on the forward ledger regardless.
52 prints/yr of forward ledger velocity is the point — the scoreboard accumulates real evidence.

---

## Benchmark-Only Mode Contract

Per MRI §6, the claims upcoming card ships:

```json
{
  "projection": {
    "mode": "benchmark_only",
    "reason": "Walk-forward MAE (IC4WSA spec attempt 2: 43.9 thousand full, 17.7 thousand 2021+) fails to beat naive_prior..."
  },
  "benchmark_set": {
    "naive_prior": <last ICSA initial print in thousands>,
    "trailing_4w": <mean of last 4 ICSA initial prints in thousands>,
    "ar_model": <AR3 Ridge on ICSA levels in thousands>,
    "cleveland_nowcast": null,
    "market_implied": null
  }
}
```

Point, p10-p90 quantiles, confidence, and skew are null/absent in benchmark_only mode.
The scoreboard grades mae_naive_prior, mae_trailing_4w, mae_ar_model going forward.

---

## Notes

- **MRI-R9 (era law):** Weekly claims residuals have strong autocorrelation. The effective n
  for statistical inference is substantially smaller than the row count. Coverage and skew
  hit-rates carry this caveat.
- **Unit:** thousands (raw ICSA/1000). ~215 = 215,000 initial claims (215 thousand).
- **Trailing benchmark:** trailing_4w (mean of last 4 prints); trailing_3m applies to monthly releases.
- **IC4WSA walk-forward:** point = IC4WSA / 1000 (thousands); actual = ICSA / 1000 (thousands).
  IC4WSA published strictly before each ICSA print (PIT law preserved).
- **No iteration:** Anti-mining law applies. No spec changes after seeing results.
- **Forward gates:** If n>=12 forward prints show a model beating naive with Wilson LB > 0.5,
  a model-mode re-entry proposal may be adjudicated (new separate program, not this §9.1).
