# W2.5 Collinearity Phase-0 — BINDING VERDICT
**Study date:** 2026-07-02
**Branch:** wave/w2-5-collinearity
**Gates:** W4.2 (hazard feature selection) and W4.6 (binding calibration)
**Status:** COMPLETE — see `data/cycle_ontology/collinearity_phase0.json`

---

## 0. What this study is

Measures the correlation structure among the fusion legs sector_central uses
(cycle-state score, trend-gate pass, RS/momentum) and the candidate hazard features
named in D5 §1.3, on the pooled PIT backfill history (12,519 monthly stamps across
US sectors, country ETFs, and China Shenwan sectors, 2010-12-31 → 2026-06-30).

The audit (Part IV §F, Part V item 4) and R4 §U2 made this a HARD PRECONDITION:
*"the correlation structure among the confluence legs needs to be MEASURED on history
before any agreement count is trustworthy."* This verdict is the measurement.

---

## 1. Panel summary

- **Pooled rows:** 12504 (after dropping NaN in any leg)
- **Families:** us_sector (1881 rows), country (5738 rows), cn_sector (4885 rows)
- **Leg set:** state_score, trend_pass_f, mom_score, pos_osc, amp_proxy, rs_63d_f, osc_slope_f, vol_pctile
- **Legs NOT reconstructed (disclosed):**
  - *macro-regime quad/liquidity* — present in repo but not PIT-backfilled in the
    backfill.parquet; including it would import the P-D5-1 revision leak. Excluded.
    The regime axis is assumed independent (it is the ONE non-price leg in the
    confluence tally; this assumption is flagged for future measurement when a
    PIT regime backfill exists).
  - *age-in-phase* — requires confirmed-turn history per stamp; not in backfill.parquet;
    deferred to D5-W1's hazard panel.

---

## 2. Pairwise correlation (pooled)

Key findings from the correlation matrix (|rho| > 0.8 flagged):

- **state_score** × **pos_osc**: rho = -0.968  ← REDUNDANT (|rho|>0.8)

---

## 3. Variance Inflation Factors (VIF)

VIF > 5.0 = multicollinear (one leg near-linearly explained by others):

| Leg | VIF |
|---|---|
| pos_osc | 29.8  ← HIGH |
| state_score | 25.8  ← HIGH |
| mom_score | 2.5 |
| rs_63d_f | 2.2 |
| trend_pass_f | 2.0 |
| osc_slope_f | 1.7 |
| amp_proxy | 1.1 |
| vol_pctile | 1.1 |

---

## 4. Principal Components

**5 principal components explain ≥90% of variance** in the 8-leg space.

- PC1: 43.2%
- PC2: 15.5%
- PC3: 12.3%
- PC4: 11.6%
- PC5: 8.7%
- PC6: 5.5%

---

## 5. Marginal information test — risk channel

Forward max-drawdown partial correlations (controlling for all other legs),
month-block bootstrapped 95% CIs:

| Leg | 63d DD partial-rho | CI 95% | Sig | 126d DD partial-rho | CI 95% | Sig |
|---|---|---|---|---|---|---|
| state_score | -0.005 | [-0.054, 0.041] | no | +0.005 | [-0.037, 0.042] | no |
| trend_pass_f | +0.054 | [0.008, 0.111] | YES | +0.021 | [-0.026, 0.076] | no |
| mom_score | +0.070 | [0.003, 0.136] | YES | +0.010 | [-0.061, 0.086] | no |
| pos_osc | +0.010 | [-0.045, 0.064] | no | +0.022 | [-0.024, 0.070] | no |
| amp_proxy | -0.043 | [-0.090, 0.009] | no | -0.042 | [-0.085, 0.005] | no |
| rs_63d_f | -0.171 | [-0.256, -0.079] | YES | -0.058 | [-0.159, 0.046] | no |
| osc_slope_f | +0.021 | [-0.048, 0.089] | no | -0.009 | [-0.070, 0.049] | no |
| vol_pctile | -0.138 | [-0.218, -0.064] | YES | -0.148 | [-0.230, -0.078] | YES |

**Risk-channel survivors** (partial-corr CI excludes 0 on ≥1 horizon):
**trend_pass_f**, **mom_score**, **rs_63d_f**, **vol_pctile**

---

## 6. Verdict — which legs are REDUNDANT

The following legs are **REDUNDANT** (|rho|>0.8 or VIF>5.0 in the pooled panel):

- state_score
- pos_osc

These legs are near-collinear price transforms of the same TR close series, consistent with the audit's diagnosis (Part IV §F: "confluence is ONE price signal triple-counted").

**Surviving legs** (below the collinearity threshold):

- trend_pass_f
- mom_score
- amp_proxy
- rs_63d_f
- osc_slope_f
- vol_pctile

---

## 7. Binding recommendation for W4.2 and W4.6

**De-duplicated feature set:**

W4.2 (hazard model) and W4.6 (binding calibration) **MUST NOT** include collinear legs as separate features. Recommended de-duplicated feature set for the risk channel:

1. ONE composite price-trend leg: replace `state_score`, `trend_pass_f`,    `pos_osc`, `amp_proxy`, `osc_slope_f` with a **single orthogonalized    first-PC** of the price-basis legs (or use `pos_osc` alone as the    simplest representative, with `amp_proxy` as an optional second term).
2. `rs_63d_f` — retained if it clears its own CI gate in W4.2 (it has    distinct signal relative to the pure-position legs only if the cross-   sectional RS rank genuinely adds information beyond the instrument's    own position).
3. `vol_pctile` — retained if not collinear with the above (check VIF in    the JSON output).
4. **Macro-regime axis** — retained as a separate feature (non-price,    assumed orthogonal — see §8); clear its own CI gate independently.

If using PCA orthogonalization: use the top 5 PCs (which explain ≥90% of variance), with the loading matrix stored as a committed artifact so the same orthogonalization applies in-sample and out-of-sample.

**Orthogonalization note:**

If the W4.2 fitter uses raw legs despite this collinearity diagnosis, L2 regularization will shrink the collinear legs toward zero in the right direction but will NOT recover independent information — it will split the coefficient across redundant legs arbitrarily. The de-duplicated or PCA-orthogonalized feature set is the correct pre-processing step.

---

## 8. Non-price axis note

The macro-regime axis (quad Q1-Q4, liquidity) was NOT measurable in this study
(no PIT regime backfill exists yet; P-D5-1 revision leak documented in D5).
By construction the regime axis derives from macro indicators (payrolls, INDPRO)
and NOT from the same TR price series as state/trend/RS.  Its orthogonality to
the price-based legs is therefore **ASSERTED**, not measured.  W4.2 should run a
sensitivity test: once a PIT regime backfill exists, measure corr(regime_quad,
price_legs) on the same panel and update this verdict if |rho| > 0.8.

---

## 9. Determinism test

PASS — VIF on synthetic perfectly-collinear data (x3 = x1 + x2): VIF(x3) = 10000.0 >> 5.0. Two calls with same seed: identical output.

---

*Generated by scripts/collinearity_phase0.py. Artifact: data/cycle_ontology/collinearity_phase0.json.*
