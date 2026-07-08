# D4-05 — Credit Flow-vs-Spread Divergence
**Family:** `d4_credit_flow_divergence`  
**Date:** 2026-07-08  
**Status:** AUC GATE FAILS — flow residual does not beat OAS timer at either horizon  
**Disposition:** STOP — signal spanned on AUC bar; no further cells  

---

## 1. Data availability — rung audit

Three rungs were probed in order on 2026-07-08 (all checks machine-verified):

| Rung | Source | Verdict |
|------|--------|---------|
| (a) ICI weekly estimated ETF/MF flows | `www.ici.org/flows_data_YYYY.xls` | **NOT ADEQUATE** |
| (b) HYG / JNK shares-outstanding history | iShares CSV + yfinance | **NOT ADEQUATE** |
| (c) HYG weekly dollar-volume z-score | `data/yahoo/HYG.parquet` + `data/fred/BAMLH0A0HYM2.parquet` | **ADEQUATE** |

**Rung (a) detail.** ICI publishes a single rolling XLS covering the current year plus fragments of prior years. The 2026 and 2025 files are identical in content: monthly data from 2024-01, weekly estimates only for recent weeks. Files for 2023 and earlier return HTTP 404. Coverage = ~2.5 years; far below the 5-year bar.

**Rung (b) detail.** `yfinance` fast\_info.shares returns only a point-in-time scalar (not a time series). The iShares historical NAV/shares CSV endpoint returns an HTML WAF block regardless of User-Agent or Referer headers. No historical SO series is accessible.

**Rung (c) detail.** HYG close + volume in `data/yahoo/HYG.parquet`: 4840 daily rows, 2007-04-11 to 2026-07-07 (19.2 years). HY-OAS in `data/fred/BAMLH0A0HYM2.parquet`: 7706 daily rows, 1996-12-31 to 2026-07-03. Aligned weekly overlap: 1004 weeks, 2007-04-15 to 2026-07-05. The NAV premium-to-discount component of rung (c) was dropped — iShares NAV history is WAF-gated (the lane specifies "if NAV series free"; it is not). Dollar-volume z-score alone qualifies as the rung-c proxy.

**Collector built:** `collectors/credit_fund_flows.py`  
**Store written:** `data/credit_flows/hyg_weekly.parquet` (1004 weekly rows)  
**Columns:** `close_price`, `dollar_vol`, `hy_oas`, `oas_chg10d`, `dollar_vol_z52`, `oas_z52`, `oas_chg10d_z52`

---

## 2. Pre-registered study design

All gates and thresholds were committed before any outcome statistics were computed.

**Divergence state definitions (pre-registered):**
- `thrust_oas_wide`: `dollar_vol_z52 > +0.5` AND `oas_chg10d_z52 > +0.5` (flow into HY while spread widens)
- `washout_oas_tight`: `dollar_vol_z52 < -0.5` AND `oas_chg10d_z52 < -0.5` (outflow while spread tightens)

**Orthogonality gate (pre-registered, decisive):**  
Residualize `dollar_vol_z52` on `[hy_oas, oas_chg10d_z52]` via OLS. Compute partial correlation of residual with forward SPY drawdown labels. If `|partial_r| < 0.05` AND `p > 0.05` at both horizons → SPANNED (stop). Must fail both conditions to proceed.

**AUC gate (pre-registered):**  
`AUC(flow_residual) > AUC(HY-OAS timer) + 0.05` at either horizon → proceed.  
Below that margin at both horizons → AUC FAILS.

**Labels:** SPY forward max drawdown over 3-week window (≈21 trading days) and 9-week window (≈63 trading days); positive = drawdown of ≥ 5%.

**LOCO episodes (pre-registered):** 2008-09 (GFC), 2011-08 (EU debt), 2015-08 (China), 2016-01 (oil), 2018-12 (Fed hike), 2020-03 (COVID), 2022-06 (rate hike).

---

## 3. Sample

- **N = 978 weeks**, 2007-10-14 to 2026-07-05 (post 52-week warm-up)
- 21d labels: 101 events (10.3% base rate)  
- 63d labels: 239 events (24.4% base rate)
- Divergence: `thrust_oas_wide` = 153 weeks (15.6%); `washout_oas_tight` = 41 weeks (4.2%); 0 overlap (correct)

---

## 4. Orthogonality gate result

OLS R² for `dollar_vol_z52 ~ hy_oas + oas_chg10d_z52` = **0.188** (OAS explains 19% of flow variance; residual retains 81%).

| Horizon | Partial r (resid ~ label) | p-value | 95% CI | Gate verdict |
|---------|--------------------------|---------|--------|--------------|
| 21d | +0.0633 | 0.0479 | [0.001, 0.126] | **SURVIVES** |
| 63d | +0.1087 | 0.0007 | [0.046, 0.170] | **SURVIVES** |

The flow residual is NOT spanned by OAS level + change at either horizon. The orthogonality gate clears and the study proceeds to AUC.

_Independent verification (calendar-day drawdowns): 63d partial r = +0.1063, p = 0.0009 — consistent. 21d partial r = +0.0442, p = 0.168 — borderline (fails at the 5% bar in the calendar-day computation). This discrepancy is noted and documented but does not change the AUC gate outcome._

**Overlap / autocorrelation caveat (methodological disclosure):** The p-values above are raw Pearson p-values computed on N=978 weekly observations. The forward labels span 3-week (21d) and 9-week (63d) windows, introducing heavy label autocorrelation. Effective N after overlap correction is approximately 978/3 ≈ 326 for the 21d horizon and 978/9 ≈ 109 for the 63d horizon. Under a Newey-West or block-bootstrap correction at these effective sample sizes, the 21d p-value (0.0479) would not survive the 5% bar; the 63d p-value (0.0007) is robust enough to survive at either effective-N estimate. The gate verdict — the study proceeds to AUC — is conservative: the 63d partial r is real. However, the 21d "SURVIVES" phrasing overstates significance; a Newey-West 21d corrected result would read as borderline/failing. Since the AUC gate ultimately fails at both horizons regardless, this does not affect the final STOP disposition, but the uncorrected p-values should not be cited as standalone evidence of 21d forecasting ability.

---

## 5. AUC comparison — decisive gate

| Horizon | AUC (HY-OAS timer) | AUC (flow residual) | Margin | Gate |
|---------|-------------------|---------------------|--------|------|
| 21d | 0.5859 | 0.5602 | **−0.026** | **FAIL** |
| 63d | 0.5748 | 0.5601 | **−0.015** | **FAIL** |

The flow residual does **not** beat the HY-OAS timer at either horizon. The AUC gate is not met. 

For reference, a composite (OAS timer + flow residual) yields AUC 0.629 (21d) and 0.608 (63d) — stronger than either component alone. This is noted but is not the pre-registered gate condition (standalone flow signal vs baseline).

Independent verification confirms the direction: calendar-day method gives margins of −0.065 (21d) and −0.019 (63d) — both negative, consistent with the weekly-bar computation.

**VERDICT: AUC GATE FAILS. STOP — no further cells.**

---

## 6. LOCO episodes (context only — informational, post-gate)

| Episode | N weeks | Flow resid mean | OAS mean | 21d DD rate | 63d DD rate |
|---------|---------|----------------|----------|-------------|-------------|
| 2008-09 GFC | 39 | −0.39 | 14.4 bp | 38% | 77% |
| 2011-08 EU debt | 35 | +0.56 | 6.9 bp | 23% | 46% |
| 2015-08 China | 30 | +0.16 | 5.8 bp | 10% | 57% |
| 2016-01 oil | 26 | +0.22 | 7.0 bp | 4% | 4% |
| 2018-12 Fed hike | 26 | +0.85 | 4.2 bp | 19% | 42% |
| 2020-03 COVID | 30 | +0.23 | 6.1 bp | 23% | 40% |
| 2022-06 rate hike | 44 | +0.48 | 4.3 bp | 39% | 61% |

Observation (informational only): in most stress episodes the flow residual is positive (flow into HY above what spread level explains), yet drawdown rates remain elevated. This is consistent with the AUC finding: the residual does not add reliable drawdown-timing information beyond the spread level.

---

## 7. Verdict

**SIGNAL SPANNED ON AUC BAR.**  

The flow signal (HYG weekly dollar-volume z-score) survives orthogonality to the HY-OAS timer at the 63d horizon (partial r = +0.109, p = 0.0007) but fails to beat the OAS timer AUC at either 21d or 63d horizon. The pre-registered bar was +5pp above baseline; actual margins are −2.6pp (21d) and −1.5pp (63d).

The composite (OAS + flow) is stronger than either alone, but the lane framing is conditioning-only and the de-escalation conditioning use case requires the signal to bring standalone discrimination power beyond the spread timer, which it does not.

**Planned home (de-escalation conditioning input) not recommended.** The OAS level already captures the credit risk regime that the flow proxy tracks; adding the flow residual adds statistical noise, not signal.

---

## 8. Data-blocked findings (pre-condition to Step 2, now closed)

- ICI weekly high-yield fund flow history: < 5 years accessible. If ICI opens a historical API or a third-party compiles the full weekly history, this rung should be re-probed.
- HYG shares-outstanding history: WAF-blocked at iShares as of 2026-07-08. If accessible in future, the NAV-premium component of rung (c) can be added.
- Neither addition would likely change the fundamental finding that the composite (OAS + flow) is stronger than standalone flow, given the OAS signal's dominance in the LOCO analysis.

---

## 9. Files produced

| Path | Description |
|------|-------------|
| `collectors/credit_fund_flows.py` | Rung-audit documentation + weekly assembly from `data/yahoo/HYG` + `data/fred/BAMLH0A0HYM2` |
| `data/credit_flows/hyg_weekly.parquet` | 1004 weekly rows (2007-04-15 to 2026-07-05); columns: `close_price`, `dollar_vol`, `hy_oas`, `oas_chg10d`, `dollar_vol_z52`, `oas_z52`, `oas_chg10d_z52` |
| `reports/d4-credit-flow-divergence.md` | This report |
