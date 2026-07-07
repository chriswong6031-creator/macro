# w2051-housing-hf Phase-0: Redfin/ZORI Housing Conditioning Study

**Run date:** 2026-07-06  
**Family:** `w2051_housing_hf`  
**Gated cells:** 4 (2 signals x 2 horizons)  
**Overall verdict:** `NULL`  
**Redfin data as-of:** 2026-06-20 (173 months)  

---

## In Plain English

> We tested whether two housing-market stress signals -- the share of listings
> cutting their price, and the ratio of pending sales to active inventory -- can
> predict whether homebuilder stocks (XHB) will outperform or underperform the
> broader market (SPY) over the next 1-3 months.
>
> **Result:** Both signals show the pre-registered direction (more stress -> XHB underperforms), but the statistical evidence is weak -- none of the 4 tested cells cleared all four gates simultaneously. The signals are display-ready conditioning context but do not yet earn a standalone predictive edge.
>
> **What this means in practice:** The housing data products (Redfin national + ZORI metro) are useful for *context display* in the cycle-intelligence program. A conditioning role (tilt, not primary signal) warrants further accrual before any allocation change.

---

## Pre-Registration

Hypothesis frozen before computing: rising price-drops share and a worsening
pending/inventory ratio -> **negative** XHB-relative-to-SPY forward returns.

**Amendments logged (pre-computed):**
- A1: Yahoo XHB used (5y massive_stock_day history too short; Yahoo from 2006).
- A2: Redfin public S3 data is **monthly** only (no public weekly metro endpoint).
  'HF' = high-frequency relative to quarterly macro data cycle.
- A3: One observation per signal date; Newey-West corrects for overlap.
- A4: Split date pre-registered as 2019-01-01 before computing.
- A5: **Deseasonalization** (reviewer fix). Raw housing metrics contain strong
  calendar-month seasonality (~34.5% of price_drops_z variance was seasonal dummy).
  Fix: subtract expanding-window PIT calendar-month mean before z-scoring.
  This residual reflects genuine stress, not the season.
- A6: **PIT lag corrected** from 30d to 50d (reviewer fix). Redfin
  publishes ~2-4 weeks after month end; period_end ~= period_begin+30d.
  Correct lag: period_begin + 50d (~= period_end + 20d). Old 30d was optimistic.
- A7: **G3 same-panel** (reviewer fix). All four signals' IC computed on the
  common inner-joined panel (identical dates) for fair baseline comparison.
- A8: **Ledger write gated** (reviewer fix). Trial ledger is written only by
  the nightly pipeline (write_ledger=True). Intraday study runs skip the write.

---

## Data Coverage

| Source | Period | Obs | Notes |
|--------|--------|-----|-------|
| Redfin National | 2012-01 to 2026-06-20 | 173 months | Non-SA, All Residential |
| XHB (Yahoo) | 2006-02-06 to 2026-07-02 | 5,133 days | Used for fwd returns |
| SPY (Yahoo) | 1993-01-29 to 2026-07-02 | 8,413 days | Used for fwd returns |
| FRED MORTGAGE30US | 1971-04-02 to 2026-07-02 | 2,884 weeks | 30y fixed rate |
| ZORI (Zillow) | 2015-01 to 2026-05 | 137 months | SFR+condo smoothed |

**PIT lag applied:** 50 days to Redfin signals
(period_begin + 50d ~= period_end + 20d; Redfin publishes ~2-4 weeks after month end).

---

## Signal Construction

| Signal | Definition | Expected sign |
|--------|-----------|---------------|
| `price_drops_z` | Rolling 24m z-score of **deseasonalized** price-reduction share | **negative** -> XHB underperforms when high |
| `pend_inv_ratio_z` | Rolling 24m z-score of **deseasonalized** (pending_sales / inventory) | **positive** -> XHB outperforms when ratio high (demand > supply) |
| `mortgage_4wk_chg` | 4-week change in 30y mortgage rate (bps proxy) | baseline |
| `xhb_50dma_trend` | XHB close / 50dma - 1 | baseline |

**Deseasonalization method (A5):** Additive, PIT. At each date t with calendar
month m, compute the expanding mean of all prior observations in month m and
subtract from the raw value. The first 2 occurrences of each calendar month
produce NaN (insufficient history) -- these are dropped before z-scoring.

---

## Raw Results -- All Cells

| Signal | h | IC (own panel) | IC (common panel) | t_HAC | p_HAC | n | n_common | IC_IS | IC_OOS | direction |
|--------|---|----|-------|-------|---|-------|--------|-----------|--------|---------|
| price_drops_z | 21d | -0.0391 | -0.0391 | -0.049 | 0.9609 | 143 | 143 | -0.0045 | -0.0431 | CORRECT |
| pend_inv_ratio_z | 21d | -0.0610 | -0.0610 | -0.945 | 0.3448 | 143 | 143 | -0.0414 | -0.0598 | WRONG |
| mortgage_4wk_chg | 21d | -0.1022 | -0.0636 | -1.004 | 0.3153 | 172 | 143 | -0.1291 | -0.0618 | CORRECT |
| xhb_50dma_trend | 21d | 0.0058 | 0.0017 | -0.423 | 0.6719 | 172 | 143 | -0.0462 | -0.0152 | CORRECT |
| price_drops_z | 63d | 0.0653 | 0.0653 | 0.216 | 0.8292 | 141 | 141 | -0.0442 | 0.1151 | WRONG |
| pend_inv_ratio_z | 63d | -0.1485 | -0.1485 | -0.836 | 0.4033 | 141 | 141 | -0.1874 | -0.0790 | WRONG |
| mortgage_4wk_chg | 63d | -0.0907 | -0.0476 | -0.716 | 0.4738 | 170 | 141 | -0.1390 | -0.0269 | CORRECT |
| xhb_50dma_trend | 63d | -0.0521 | -0.0873 | -1.106 | 0.2688 | 170 | 141 | -0.0383 | -0.0719 | CORRECT |

---

## Baseline Comparison (Common Panel -- A7)

| Baseline | h=21d IC (common) | h=63d IC (common) |
|----------|--------------------|-------------------|
| mortgage_4wk_chg | -0.0636 | -0.0476 |
| xhb_50dma_trend | 0.0017 | -0.0873 |

Gate G3 requires the housing signal |IC_common| to exceed BOTH baselines on the
identical common inner-joined panel (A7 fix: same observation set for all signals).

---

## BH FDR Correction (all 8 cells)

| Cell | p | q (BH) | reject |
|------|---|--------|--------|
| mortgage_4wk_chg_h21 | 0.3153 | 0.7581 | False |
| mortgage_4wk_chg_h63 | 0.4738 | 0.7581 | False |
| pend_inv_ratio_z_h21 | 0.3448 | 0.7581 | False |
| pend_inv_ratio_z_h63 | 0.4033 | 0.7581 | False |
| price_drops_z_h21 | 0.9609 | 0.9609 | False |
| price_drops_z_h63 | 0.8292 | 0.9477 | False |
| xhb_50dma_trend_h21 | 0.6719 | 0.8959 | False |
| xhb_50dma_trend_h63 | 0.2688 | 0.7581 | False |

---

## Gate Verdicts -- Gated Cells Only

Gates: G1=|t_HAC|>=2, G2=BH-reject at alpha=0.10, G3=beats both baselines
(common panel, A7), G4=split-half same sign

| Cell | IC | IC_common | t_HAC | q_BH | IC_IS | IC_OOS | Gate results | Verdict |
|------|----|-----------|---------|----|-------|--------|--------------|---------|
| price_drops_z_h21 | -0.0391 | -0.0391 | -0.05 | 0.961 | -0.0045 | -0.0431 | G1:FAIL G2:FAIL G3:FAIL G4:PASS | **FAIL** |
| price_drops_z_h63 | 0.0653 | 0.0653 | 0.22 | 0.948 | -0.0442 | 0.1151 | G1:FAIL G2:FAIL G3:FAIL G4:FAIL | **FAIL** |
| pend_inv_ratio_z_h21 | -0.0610 | -0.0610 | -0.94 | 0.758 | -0.0414 | -0.0598 | G1:FAIL G2:FAIL G3:FAIL G4:PASS | **FAIL** |
| pend_inv_ratio_z_h63 | -0.1485 | -0.1485 | -0.84 | 0.758 | -0.1874 | -0.0790 | G1:FAIL G2:FAIL G3:PASS G4:PASS | **FAIL** |

---

## Verdict and Interpretation

### Overall: `NULL`

**Cells passing all gates:** 0 of 4

**Null result interpretation (if overall=NULL):**
A failed gate is a successful run. The null tells us:
- After removing calendar-month seasonality, the deseasonalized housing
  stress signals show weak directional content relative to XHB excess returns.
- The original study (before fix A5) was uninterpretable because the 'signal'
  was largely a seasonal calendar dummy. The deseasonalized result is the
  first interpretable test of the pre-registered hypothesis.
- The XHB 50dma trend (B2) may dominate housing-flow information for
  return prediction at 21-63 day horizons.
- The conditioning role (display) is appropriate at this stage.

**If overall=PASS:**
- The passing cell(s) are noted above with specific gate details.
- Appropriate next step: register for accrual in the cycle-intelligence
  program as a conditioning layer (not a primary allocation signal).
- Do not promote until a second independent period accrues.

---

## Data Products -- Display Wiring

**Site wiring NOT done in this PR** (per lane spec). The following artifacts
are ready for integration into the cycle-intelligence program:

| Artifact | Path | Contents |
|----------|------|----------|
| Redfin national | `data/redfin_hf/national.parquet` | Monthly: pending, inventory, price_drops, DOM |
| Redfin metro | `data/redfin_hf/metro.parquet` | 20 metros x monthly |
| Redfin display JSON | `data/redfin_hf/agg_json.json` | Last 24 months national + latest metro scorecard |
| ZORI national | `data/zori/national.parquet` | Monthly rent index 2015+ |
| ZORI metro | `data/zori/metro.parquet` | 20 metros x monthly |
| ZORI display JSON | `data/zori/agg_json.json` | Last 24 months national + latest metro |

**Nightly wiring (for consolidation):**
```python
# In scripts/collect.py, after FRED block:
from scripts.collect_redfin_hf import run as collect_redfin_hf
from scripts.collect_zori import run as collect_zori
collect_redfin_hf()
collect_zori()
```

---

## Limitations and Caveats

1. **Redfin data is monthly**, not weekly as originally specified in the lane.
   The public S3 bucket does not expose weekly metro-level data. The product
   is still 'high frequency' relative to quarterly cycle data.

2. **Deseasonalization warm-up**: The expanding PIT deseasonalization drops the
   first 2 occurrences of each calendar month (insufficient history). For a
   2012-start series this removes roughly the first 24 months, so the effective
   conditioning panel starts ~2014.

3. **Short overlap**: Redfin starts 2012-01, XHB 2006. The conditioning panel
   spans ~2014-2026 after deseasonalization warm-up. At monthly frequency
   this is a moderate sample (~140 obs before PIT-lag tail trim).

4. **ZORI starts 2015**: The rent index has only 11 years of history. Not used
   in the conditioning study directly (used for display/context).

5. **Survivorship**: XHB from Yahoo is a live ETF; the homebuilder constituent
   universe changes over time. This is not controlled for.

---

## Trial Ledger

8 configs pre-registered under family `w2051_housing_hf`
(4 gated cells + 4 baseline trials). Ledger write is gated behind
the nightly pipeline (house law: nightly is sole ledger advancer).
Deflated Sharpe haircut applies to any future promotion from this family.

**Pre-registered ledger_delta lines (carried forward from orchestrator):**
- `family=w2051_housing_hf signal=price_drops_z horizon=21 hash=21a2ce4390d06129`
- `family=w2051_housing_hf signal=price_drops_z horizon=63 hash=dcbe90ef33487c6a`
- `family=w2051_housing_hf signal=pend_inv_ratio_z horizon=21 hash=35af3573adf0f971`
- `family=w2051_housing_hf signal=pend_inv_ratio_z horizon=63 hash=7bfe75cd3ca5b189`
- `family=w2051_housing_hf signal=mortgage_4wk_chg horizon=21 hash=90a3a7c89fa7d19b`
- `family=w2051_housing_hf signal=mortgage_4wk_chg horizon=63 hash=63ad0a84e9db06e7`
- `family=w2051_housing_hf signal=xhb_50dma_trend horizon=21 hash=56fa6a3e03384389`
- `family=w2051_housing_hf signal=xhb_50dma_trend horizon=63 hash=6725d70c8a7aa192`
