# D2 China Export-Share Nowcast — Phase-0 Study

**Family:** `d2_cn_export_share_nowcast`
**Date:** 2026-07-07
**Verdict: NULL — all three gates fail or were not reached**

---

## In plain English

We asked: when Chinese export volumes in a product line surge more than usual, do the 2-3 dominant A-share producers in that line outperform the broad Chinese market over the following 21 trading days?

The honest answer is no — at least not at any statistical threshold that would justify using this as an actionable signal. The mean excess return is +3.3% on positive-surprise months, which sounds interesting, but with t=1.47 (p=0.14) it is indistinguishable from noise given the sample size (39 pooled date-observations). All per-line results are also null. We treat this as a successful null: the study ran cleanly with proper publication-lag controls, and the signal simply is not there in this data.

---

## Pre-registered gaps (locked before computation)

| Gap | Description |
|---|---|
| G1 | Small N: 3 HS lines × 34–72 non-null months = 270 issuer-month observations; pooled positive-surprise events = 39 unique dates |
| G2 | Deseasonalization: CNY combined Jan+Feb convention removes seasonal shift; structural trend shifts (pandemic, policy cycles) may remain in the residual |
| G3 | Publication lag: Comtrade monthly data lags ~3 months; entry dated to day 20 of M+3 (reference month + 3 months) |
| G4 | Issuer share: equal-weight across 2-3 issuers per line; no PIT per-period share weighting available |
| G5 | Price coverage: STAR-board tickers (688223.SS) shorter history; all tickers confirmed loaded with n>100 days |
| G6 | CSI300 benchmark: broad-market index, not sector-specific |
| G7 | Overlap: 21-day forward windows overlap; NW HAC lag=2 monthly lags used throughout |
| G8 | Split-half: ~19-20 event dates per half; t-stats reported as supplementary evidence only |
| G9 | 854141 short history: solar cells mono only available from 2022-01; 34 non-null months |

**Amendment A1 (pre-registered before computation):**
HS lines 854160 (Solar modules) and 850440 (Solar inverters) are EXCLUDED because the sum of mapped-name shares does not clear the >50% national-export-share threshold:
- 854160: LONGi 20% + Trina 12% + JA 11% = **43%** (FAIL; prior top_n_combined_pct=72% cited global shipment share of top-4, not the 3 named tickers vs national exports)
- 850440: Sungrow 30% + Ginlong 12% + GoodWe 8% = **50%** (FAIL; criterion requires strictly >50%)

Retained lines: 854141 (63% CN cell capacity), 850760 (58% global usage/dominated by CN), 870380 (BYD 52% of listed NEV exports alone).

---

## PIT assumptions per series

| Series | Source | Publication lag | Entry convention | PIT clean? |
|---|---|---|---|---|
| Comtrade HS tape | Comtrade/GACC monthly | ~3 months | Day 20 of M+3 | YES — verified by PIT check in run log |
| CSI300 daily close | Saved parquet, daily | Same-day | First trading day on/after entry date | YES |
| Issuer daily close | china_stocks/ parquet | Same-day | Same as CSI300 | YES |

PIT check output from run:
```
ref_month=2019-12 -> entry_date=2020-03-20 [+3mo lag ok: OK]
ref_month=2020-04 -> entry_date=2020-07-20 [+3mo lag ok: OK]
ref_month=2020-05 -> entry_date=2020-08-20 [+3mo lag ok: OK]
```

---

## Price-store coverage (all tickers)

All 8 active tickers loaded from `china_stocks/` parquet (primary store). No PRICE MISS.

| Ticker | Name | Days | Coverage |
|---|---|---|---|
| 002074.SZ | Gotion High-tech | 4,790 | 2006-10 → 2026-07 |
| 002459.SZ | JA Solar | 3,856 | 2010-08 → 2026-07 |
| 002594.SZ | BYD | 3,641 | 2011-06 → 2026-07 |
| 300750.SZ | CATL | 1,953 | 2018-06 → 2026-07 |
| 600104.SS | SAIC Motor | 7,092 | 1997-11 → 2026-07 |
| 600438.SS | Tongwei | 5,457 | 2004-03 → 2026-07 |
| 601633.SS | Great Wall Motor | 3,579 | 2011-09 → 2026-07 |
| 688223.SS | Jinko Solar | 1,071 | 2022-01 → 2026-07 |

---

## Data summary

- **Export tapes loaded:** 3/3 active HS lines (854141, 850760, 870380)
- **Tape coverage:** 2018-01 → 2026-06 (102 months; non-null: 34/51/72 per line)
- **CNY combination applied:** Jan rows set to NaN, Feb = mean(Jan,Feb) for each year
- **Event panel:** 270 issuer-month rows total (all surprise signs)
- **Positive-surprise events:** 126 issuer-month rows, 39 unique release dates (pooled)
- **Events with valid 21d forward return:** 126 (100% coverage — CSI300 and issuer prices cover full window)

---

## Results

### Cell 1: Pooled positive-surprise → 21d excess return

| Metric | Value |
|---|---|
| n_events (issuer-month) | 126 |
| n_dates (unique pooled dates) | 39 |
| Mean 21d excess return | +3.33% |
| NW t-stat (lag=2mo) | 1.475 |
| p-value (two-tailed) | 0.1403 |
| Gate 1 (|t|≥2.0) | **FAIL** |

### Cell 2: Per-HS-line

| HS code | Label | n_events | n_dates | Mean ret | t (NW, 2mo) | p | Gate |
|---|---|---|---|---|---|---|---|
| 854141 | Solar cells mono | 30 | 10 | +2.96% | 0.629 | 0.529 | FAIL |
| 850760 | Li-ion batteries | 30 | 10 | -0.79% | -0.224 | 0.823 | FAIL |
| 870380 | EV passenger cars | 66 | 19 | +3.92% | 1.352 | 0.177 | FAIL |

### Cell 3: Split-half consistency

| Half | n_dates | Mean ret | t (NW, 2mo) | Sign |
|---|---|---|---|---|
| First (earlier) | 19 | +4.67% | 1.306 | Positive |
| Second (later) | 20 | +2.05% | 0.790 | Positive |

Same sign: **YES** → Gate 3: **PASS**

Note: With NW_LAG=2 monthly lags and n=19/20, the HAC estimate is well-posed (lag << n). The original script used lag=21 daily bars on a monthly series, which was degenerate (over-smoothed ~42% of the sample). The corrected t-stats are lower and properly calibrated to the monthly series.

### Cell 4: Magnitude (top vs bottom tercile)

| Tercile | n | Mean ret | t (NW) |
|---|---|---|---|
| Top (large surprise) | 13 | +3.88% | 1.036 |
| Bottom (small surprise) | 13 | +3.71% | 0.998 |

Monotone (top > bottom): **True**, but Gate 4 requires |t_top|≥2.0 → **FAIL**

### BH-FDR correction (alpha=0.10)

| Cell | p_raw | p_adj | Rejected |
|---|---|---|---|
| C1_pooled | 0.1403 | 0.3530 | False |
| C2_854141 | 0.5294 | 0.7059 | False |
| C2_850760 | 0.8230 | 0.8230 | False |
| C2_870380 | 0.1765 | 0.3530 | False |

Any BH-FDR rejected: **No** → Gate 2: **FAIL**

---

## Gate sequence

| Gate | Criterion | Result |
|---|---|---|
| Gate 1 | \|t\|≥2.0 on pooled NW-HAC (lag=2mo) | **FAIL** (t=1.475) |
| Gate 2 | BH-FDR any reject (q≤0.10) | **FAIL** (min p_adj=0.353) |
| Gate 3 | Split-half same-sign | **PASS** (both positive) |

**FINAL VERDICT: NULL**

All three gates must pass for PROMOTE. Gates 1 and 2 fail.

---

## Fixes applied vs prior version

| Issue | Prior state | Fixed state |
|---|---|---|
| PIT lookahead | Entry dated to YYYY-MM-01 (reference month start) — before data exists | Entry dated to day 20 of M+3 (~Comtrade release date); verified in run log |
| Frozen criterion violation | 854160 (43%) and 850440 (50%) included with incorrect 72%/76% global figures | Both excluded via Amendment A1; CSV updated with component-level shares |
| Deseasonalization | Plain month/month-12 YoY; Jan and Feb treated independently | CNY combined-month convention: Jan=NaN, Feb=mean(Jan,Feb) per year, then YoY |
| Shared-file write | TrialLedger written to MAIN_DATA/trial_ledger.jsonl (main checkout) | TrialLedger written to worktree-local data_local/trial_ledger.jsonl |
| HAC units | NW lag=21 daily bars on monthly event series (degenerate) | NW lag=2 monthly lags (series units); split-half t-stats properly calibrated |
| info_cutoff mismatch | "2024-12-31" (tapes run through 2026-06) | "2026-06-30" |
| Unused import | `register_trials` imported but never called | Removed |

---

## Nightly wiring (for consolidation)

This is a standalone research script. It has no nightly pipeline dependency. The export tape collector (`collectors/cn_export_comtrade.py` or equivalent) should be run before this study to refresh the tapes. The study itself can be re-run at any time from:

```bash
python3 scripts/d2_cn_export_share_nowcast_phase0.py
```

TrialLedger output is written to `data_local/trial_ledger.jsonl` (worktree-local; not committed to repo). The shared `data/trial_ledger.jsonl` is NOT modified by this script.

---

## Summary

The China export-share nowcast signal is NULL at phase-0 under PIT-clean conditions. The +3.3% mean excess return on positive-surprise months is economically plausible but statistically insignificant (t=1.47, p=0.14) across 39 pooled date-observations. Per-line results range from -0.8% (Li-ion, null) to +3.9% (EV cars, null). The null is expected given: (a) small N driven by Comtrade's ~3-month lag reducing actionable event dates, (b) the 3-month entry delay means the market likely has already priced much of the surprise by the time a trade is entered, and (c) CSI300 is a coarse benchmark that may not capture sector-specific alpha. A corrected, later entry only weakens an already-weak signal — the reviewer's prediction is confirmed.

This is a successful null. The pre-registered hypothesis is not supported in this data.
