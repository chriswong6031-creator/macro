# NFP Decomposition + AHE/AWH Backtest (PR-H)

**Run date:** 2026-07-07
**Spec:** research/release_forecast/PREREG_NFP_DECOMP_V1.md (frozen before run)

## AHE MoM % — Ridge Model (Attempt 1)

**Status:** no_data
**Total predictions:** 0
**Kill rule:** NOT triggered -> active

---
## AWH Level — Persistence-Only (No Skill Claim)

**Status:** no_data
**n steps:** 0
**MAE (persistence):** null hrs/wk
**RMSE (persistence):** null hrs/wk
**Coverage p10-p90:** None

*Model IS the naive baseline. No skill claim. Published as labor-demand context.*

---
## NFP Decomposition Sanity

**NFP walk-forward steps used:** 293

### Birth-Death Prior 12-Month Profile — 2026 View (trailing 5yr mean of actual−predicted, k jobs)

*Window: 2021-2026. COVID window 2020-03..06 is outside this cutoff (excluded by year, not Amendment A).*

| Month | BD Prior (k jobs) |
|-------|-------------------|
| Jan | +58.9 |
| Feb | +226.9 |
| Mar | +173.8 |
| Apr | -151.7 |
| May | +129.7 |
| Jun | +37.3 |
| Jul | +78.5 |
| Aug | +17.4 |
| Sep | +102.0 |
| Oct | -80.6 |
| Nov | +132.3 |
| Dec | -89.4 |

### Birth-Death Prior 12-Month Profile — 2023 View (demonstrates Amendment A COVID fix)

*Window: 2018-2023. Without Amendment A, April would inherit the 2020-04 residual (~-19,956k), producing ~-4,000k prior. With Amendment A (COVID exclusion 2020-03..06), April uses only 2018, 2019, 2021, 2022, 2023 residuals — the large negative artifact is removed.*

| Month | BD Prior (k jobs) |
|-------|-------------------|
| Jan | +263.8 |
| Feb | +48.7 |
| Mar | +57.5 |
| Apr | -99.6 |
| May | +96.1 |
| Jun | +75.3 |
| Jul | +94.4 |
| Aug | -146.4 |
| Sep | -123.6 |
| Oct | -122.0 |
| Nov | -168.4 |
| Dec | -9.3 |

### Decomposition Spot-Checks (last 5 NFP walk-forward steps)

| Period | Model | Private | Govt | BD Prior | Residual | Recon Err | Absent |
|--------|-------|---------|------|----------|----------|-----------|--------|
| 2026-01-01 | -26.0 | null | null | 245.2 | -271.2 | 0.0000 | private_trend,government_trend |
| 2026-02-01 | -899.0 | null | null | 124.7 | -1023.7 | 0.0000 | private_trend,government_trend |
| 2026-03-01 | -161.0 | null | null | 142.2 | -303.2 | 0.0000 | private_trend,government_trend |
| 2026-04-01 | 171.0 | null | null | -167.6 | 338.6 | 0.0000 | private_trend,government_trend |
| 2026-05-01 | 99.0 | null | null | 122.5 | -23.5 | 0.0000 | private_trend,government_trend |

*Reconstruction error: arithmetic identity check — residual is defined as model_point minus the sum of the present parts, so |sum(parts) + residual − model_point| is identically zero by construction when all parts are present. This does NOT demonstrate decomposition quality; private and government components are absent from the data and the residual is a plug term, not an independently estimated quantity.*

---
## Notes

1. AHE vintages (CES0500000003) begin 2006-03. pre-2010 era may have fewer than 60 obs → first predictions may start later.
2. AWHAETP/JTSJOL vintages similarly begin 2006-03 → legs absent for early periods.
3. AWH model is persistence-only with explicit no-skill-claim disclosure (persistence_only=True in output).
4. BD prior uses only prior walk-forward steps (result_pos PIT law). No future residuals used.
5. Decomposition spot-checks use approximate asof dates; live projection uses exact T-1 dates from the event calendar.
6. All outputs display_only=True, authority=False.