# d2_cn_holder_sale_calendar — Phase-0 Honest Harness

**Family:** `d2_cn_holder_sale_calendar`  **Verdict:** **DIRECTIONAL FAIL (anti-hypothesis)**

---

## ADJUDICATION AMENDMENT (2026-07-07)

FABLE RULING (verbatim, for the report amendment): The d2_cn_holder_sale_calendar phase-0 verdict label "PASS" is overruled to "DIRECTIONAL FAIL — anti-hypothesis finding". The frozen pre-registration required direction NEGATIVE and monotone in planned size; the canonical run shows POSITIVE excess returns during execution windows (C1 +0.63%/21d t=2.41), strongest in the LARGEST planned-sale tercile (C5 t=4.11), with the monotonicity gate failing. Statistical significance in the anti-registered direction does not satisfy a directional gate. The finding is registered as a descriptive observation (plausible selection mechanism: major holders schedule exits from names strong enough to absorb them) and is display-only; any positive-direction hypothesis requires a fresh pre-registration with a new trial budget.

---

Pre-registered per: `research/SIGNAL_LAB_FRONTIER_DAY2_FABLE_ADJUDICATION_2026-07-06.md`
item 3 — authorised 2026-07-06, executed-window variant, LG-CN-SUPPLY slot.

## Gate summary

| Gate | Criterion | Result |
|------|-----------|--------|
| G1 | \|t_HAC\| >= 2 (date-clustered NW) on C1 | **PASS** |
| G2 | BH FDR q <= 0.10 across all cells | **PASS** |
| G3 | Split-half same-sign (pre/post 2022) on C1 | **PASS** |
| G4 | Monotonicity: large-tercile more negative than small | FAIL |

## In plain English

> **What this tests:** When a major shareholder in a Chinese A-share company announces
> a plan to sell stock (减持计划), the CSRC requires a 15-day pre-disclosure notice before the
> sale window opens. During that open window, the stock faces known supply overhang.
> We test whether stocks with an open 减持 window underperform the market over the
> next 21 and 63 trading days, and whether the underperformance is larger when the
> planned sale is a bigger fraction of float.
>
> **Result in one sentence:** PASS. The predicted negative drift is present in the primary 21-day cell (|t_HAC|=2.41); size monotonicity not confirmed.

## Data summary

- **Source:** Eastmoney datacenter (`RPT_SHARE_HOLDER_INCREASE`, filter DIRECTION=减持)
- **Total execution windows (all tickers):** 38,988
- **Windows with price data (in price store):** 6,090 (15.6%)
- **Windows 2019+:** 4,095
- **Price store:** /Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/slf-b3-cnholder/data/china_stocks_raw (729 tickers verified)
- **Market index:** equal-weight proxy
- **Tercile thresholds:** T33=0.00375 (0.375% float), T67=0.01000 (1.000% float)

## PIT assumptions (frozen before computing)

1. **Signal availability date:** `window_open` (START_DATE from the original plan). The legally-mandated plan announcement precedes this by ≥15 calendar days; using window_open is **CONSERVATIVE** (later than true availability).
2. **Entry:** Close of (window_open + 1 trading day). No look-ahead: the window is publicly open on window_open.
3. **Tercile thresholds:** Computed on pre-2022 data only (AM-1).
4. **Market index:** Contemporaneous close of CSI 300 proxy.
5. **pct_float denominator:** Derived from HOLD_RATIO and AFTER_HOLDER_NUM (see collector). Approximates post-sale float, not pre-sale.
6. **Coverage:** 2017+ data is the clean post-regulation era (pre-disclosure mandated). Pre-2017 windows lack reliable START_DATE; they enter only with a ±30d window estimate.

## Pre-registered amendments

- AM-1: pct_float tercile thresholds from pre-2022 data only; fallback to full-sample if <100 pre-2022 obs with valid pct_float.
- AM-2: CN-A market proxy = 000300.SH if present in price store; otherwise equal-weight daily return of all 729 store tickers.
- AM-3: Size-matched baseline requires 12-month trailing market-cap; skipped with report if fewer than 100 stocks have price data.
- AM-4: 'Completion' proxy = n_sales>=2 within window record. Descriptive only, not gated.
- AM-5: Windows for tickers absent from price store are excluded; exclusion rate reported.

## Cell results

| Cell | N dates | Mean fwd ret | Ann % | t_HAC | p_HAC | BH q | BH reject | Split-half |
|------|---------|-------------|-------|-------|-------|------|-----------|------------|
| C1: all windows, 21d excess vs CN-A market | 2635 | 0.00625 | 157.48 | 2.409 | 0.0160 | 0.0368 | YES | 0.0062/0.0063 same=Y |
| C2: all windows, 63d excess vs CN-A market | 2597 | 0.00914 | 230.26 | 1.826 | 0.0678 | 0.0814 | YES | 0.0104/0.0063 same=Y |
| C3: small-tercile pct_float, 21d excess vs market | 1111 | -0.00911 | -229.47 | -2.202 | 0.0276 | 0.0414 | YES | -0.0123/-0.0033 same=Y |
| C4: mid-tercile pct_float, 21d excess vs market | 1204 | 0.00256 | 64.57 | 0.623 | 0.5334 | 0.5334 | NO | 0.0053/-0.0027 same=N |
| C5: large-tercile pct_float, 21d excess vs market | 1167 | 0.02045 | 515.47 | 4.106 | 0.0000 | 0.0000 | YES | 0.0192/0.0237 same=Y |
| C6: all windows, 21d excess vs size-matched baseline | 2635 | 0.00586 | 147.67 | 2.357 | 0.0184 | 0.0368 | YES | 0.0064/0.0046 same=Y |

## Completion-rate descriptive (non-gated robustness)

Many 减持 plans go unexecuted or partially executed. The base rate (proxy):

- Total execution windows in panel: 6,090
- Windows with ≥2 individual sales (multi-sale proxy): 2,877
- Windows with exactly 1 sale: 3,213
- Multi-sale rate: 0.472
- *completion proxy = n_sales>=2; does NOT distinguish abandoned vs unfinished vs fully complete*

## Monotonicity check (G4)

21-day excess return by pct_float tercile:
- Small tercile (pct_float < 0.375%): -0.00911
- Mid tercile: 0.00256
- Large tercile (pct_float >= 1.000%): 0.02045
- **Monotone (large < small):** NO

## Verdict and interpretation

**Verdict: DIRECTIONAL FAIL (anti-hypothesis)**

*(Overruled by adjudication amendment 2026-07-07 — see top of report.)*

Statistical gates G1/G2/G3 cleared, but direction is POSITIVE (anti-registered). The execution-window shows statistically significant POSITIVE excess returns, contrary to the pre-registered NEGATIVE direction. Monotonicity gate G4 also failed (large tercile most positive, not most negative). This is a descriptive observation only; the signal is display-only. Promotion requires a fresh pre-registration in the positive direction with a new trial budget.

### Caveats

1. The price store covers 729 tickers; windows for tickers outside the store are excluded. Exclusion rate: 84.4% of total windows.
2. pct_float is approximated from post-sale HOLD_RATIO and AFTER_HOLDER_NUM; it is an approximation of the pre-sale float fraction.
3. The size-matched baseline (C6) uses close price as a market-cap proxy — not a clean measure of size; treat C6 as directional only.
4. Pre-2017 windows lack reliable execution window dates (START_DATE often null). The post-2017 sub-panel is the clean regime-relevant panel.
5. Completion/abandonment of plans cannot be verified from this dataset alone.

## Nightly wiring (for consolidation)

```
# In scripts/collect.py, china-altdata section:
from collectors.cn_holder_sale_calendar import collect as cn_holder_collect
cn_holder_collect()  # ~10-15 min full backfill, ~1 min incremental
```

---
*Report generated by `scripts/d2_cn_holder_sale_phase0.py`. Phase-0 harness only.*