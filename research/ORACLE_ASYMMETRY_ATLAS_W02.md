# Oracle Asymmetry Atlas — W0.2

**Program:** Oracle Turn Asymmetry | Wave W0.2 — Intraday-True Pass
**Date:** 2026-07-05
**Nature:** DESCRIPTIVE calibration of W0.1. No new signals. No claim language.
**Grading basis:** unadjusted OHLC (auto_adjust=False); dividend drag unmodeled per W0_2_SPEC §2; intraday H/L barrier race — stop=low touch (longs) / high touch (shorts)
**Population:** Exactly the event rows committed in W0_1_events_graded.csv (no re-enumeration).
**σ20:** frozen from W0_1 row (not recomputed).

> IMPORTANT: The word "validated" does not appear in this document per Oracle Constitution §II.
> Every table carries the intraday honesty label and n + excluded count.

---


## CONCORDANCE — Close vs Intraday State Changes (Headline Deliverable)

> Per family: % events whose terminal state changed close→intraday (esp. DEAD/CLEAN→STOPPED), Δ stop-touch rate, Δ win rate, Δ median policy R, MAE understatement distribution (mae_R_hl_21 − mae_R_21).

> **unadjusted OHLC (auto_adjust=False); dividend drag unmodeled per W0_2_SPEC §2; intraday H/L barrier race — stop=low touch (longs) / high touch (shorts)**
> Every table: n + excluded count. The word 'validated' does not appear per Oracle Constitution §II.
> W0.2 calibrates W0.1; concordance delta is the headline deliverable, not a new event study.

> **BASIS NOTE — MAE understatement column:** `mae_R_hl_21` (intraday leg) is computed from unadjusted OHLC lows; `mae_R_21` (close leg, inherited from W0.1) is computed from dividend-adjusted closes (data/yahoo/). The delta therefore includes a small dividend-drag component (~0.2–0.5% over 21d per spec §2) in addition to the true intraday-vs-close excursion effect. The overstatement of understatement is bounded by dividend drag and is second-order vs σ21 (5–12%).
> **POLICY R NOTE — Median R (intraday stop-overlay):** STOPPED rows use R=−1; all other rows carry the close-basis policy_R from W0.1 as the best available proxy. ΔR therefore measures the effect of added intraday stops only — not a full intraday recomputation of winner R.

| Family | Param | n | State-changed% | Dead/Clean→Stopped% | Δ Stop-touch% | Δ Win% | Δ Median R (stop-overlay) | MAE Δ p50 (mixed-basis†) |
|---|---|---|---|---|---|---|---|---|
| ep_onset_in | rot21 | 355 | 6.8% | 3.1% | +3.1% | +2.8% | -0.003 | -0.0889 |
| ep_onset_in | pos63 | 350 | 8.3% | 4.6% | +4.3% | -1.1% | -0.114 | -0.0886 |
| ep_onset_out | rot21 | 388 | 17.0% | 4.1% | +1.0% | +11.3% | -0.047 | -0.1226 |
| ep_onset_out | pos63 | 384 | 10.4% | 3.1% | +1.3% | +1.3% | +0.000 | -0.1226 |
| washout_p8 | rot21 | 1215 | 8.1% | 4.4% | +4.3% | +2.9% | -0.015 | -0.0987 |
| washout_p8 | pos63 | 1195 | 10.4% | 6.6% | +6.3% | -3.8% | -0.135 | -0.0977 |
| a15 | rot21 | 2553 | 7.4% | 3.5% | +3.4% | +3.1% | -0.013 | -0.0927 |
| a15 | pos63 | 2547 | 10.8% | 6.7% | +6.4% | -2.5% | -0.105 | -0.0925 |
| a9 | rot21 | 482 | 6.8% | 2.7% | +2.5% | +2.9% | -0.001 | -0.1012 |
| a9 | pos63 | 482 | 10.8% | 7.1% | +7.0% | -1.9% | -0.042 | -0.1012 |
| a17 | rot21 | 304 | 8.9% | 3.6% | +3.3% | +3.3% | -0.020 | -0.1073 |
| a17 | pos63 | 304 | 10.9% | 5.9% | +5.9% | -1.3% | -0.035 | -0.1073 |
| routing_6 | rot21 | 554 | 11.4% | 6.1% | +6.1% | +4.9% | -0.058 | -0.1291 |
| routing_6 | pos63 | 553 | 9.9% | 7.4% | +6.9% | -4.3% | -0.561 | -0.1292 |

† MAE Δ p50: intraday leg (unadjusted OHLC lows) minus close leg (div-adjusted W0.1). Overstatement of understatement bounded by dividend drag (~0.2–0.5%). See BASIS NOTE above.

### Per-Family Detail

**ep_onset_in | rot21** (n=355)
- Stop-touch rate: close=10.4% → intraday=13.5% (Δ=+3.1%)
- Win rate: close=24.5% → intraday=27.3% (Δ=+2.8%)
- Median policy R (intraday stop-overlay): close=0.312 → stop-overlay=0.309 (Δ=-0.003). [STOPPED rows: R=−1; others: close-basis proxy from W0.1]
- MAE understatement (mae_R_hl [unadj] − mae_R_close [div-adj]): p25=-0.1710 p50=-0.0889 p75=-0.0392 [mixed-basis; see BASIS NOTE]

**ep_onset_in | pos63** (n=350)
- Stop-touch rate: close=32.0% → intraday=36.3% (Δ=+4.3%)
- Win rate: close=48.6% → intraday=47.4% (Δ=-1.1%)
- Median policy R (intraday stop-overlay): close=0.371 → stop-overlay=0.257 (Δ=-0.114). [STOPPED rows: R=−1; others: close-basis proxy from W0.1]
- MAE understatement (mae_R_hl [unadj] − mae_R_close [div-adj]): p25=-0.1719 p50=-0.0886 p75=-0.0394 [mixed-basis; see BASIS NOTE]

**ep_onset_out | rot21** (n=388)
- Stop-touch rate: close=24.7% → intraday=25.8% (Δ=+1.0%)
- Win rate: close=37.1% → intraday=48.5% (Δ=+11.3%)
- Median policy R (intraday stop-overlay): close=-0.190 → stop-overlay=-0.237 (Δ=-0.047). [STOPPED rows: R=−1; others: close-basis proxy from W0.1]
- MAE understatement (mae_R_hl [unadj] − mae_R_close [div-adj]): p25=-0.1846 p50=-0.1226 p75=-0.0651 [mixed-basis; see BASIS NOTE]

**ep_onset_out | pos63** (n=384)
- Stop-touch rate: close=56.0% → intraday=57.3% (Δ=+1.3%)
- Win rate: close=37.8% → intraday=39.1% (Δ=+1.3%)
- Median policy R (intraday stop-overlay): close=-1.000 → stop-overlay=-1.000 (Δ=+0.000). [STOPPED rows: R=−1; others: close-basis proxy from W0.1]
- MAE understatement (mae_R_hl [unadj] − mae_R_close [div-adj]): p25=-0.1840 p50=-0.1226 p75=-0.0651 [mixed-basis; see BASIS NOTE]

**washout_p8 | rot21** (n=1215)
- Stop-touch rate: close=15.8% → intraday=20.1% (Δ=+4.3%)
- Win rate: close=23.6% → intraday=26.5% (Δ=+2.9%)
- Median policy R (intraday stop-overlay): close=0.255 → stop-overlay=0.240 (Δ=-0.015). [STOPPED rows: R=−1; others: close-basis proxy from W0.1]
- MAE understatement (mae_R_hl [unadj] − mae_R_close [div-adj]): p25=-0.1764 p50=-0.0987 p75=-0.0486 [mixed-basis; see BASIS NOTE]

**washout_p8 | pos63** (n=1195)
- Stop-touch rate: close=33.3% → intraday=39.6% (Δ=+6.3%)
- Win rate: close=47.8% → intraday=44.0% (Δ=-3.8%)
- Median policy R (intraday stop-overlay): close=0.298 → stop-overlay=0.164 (Δ=-0.135). [STOPPED rows: R=−1; others: close-basis proxy from W0.1]
- MAE understatement (mae_R_hl [unadj] − mae_R_close [div-adj]): p25=-0.1772 p50=-0.0977 p75=-0.0484 [mixed-basis; see BASIS NOTE]

**a15 | rot21** (n=2553)
- Stop-touch rate: close=10.9% → intraday=14.3% (Δ=+3.4%)
- Win rate: close=31.8% → intraday=34.9% (Δ=+3.1%)
- Median policy R (intraday stop-overlay): close=0.426 → stop-overlay=0.413 (Δ=-0.013). [STOPPED rows: R=−1; others: close-basis proxy from W0.1]
- MAE understatement (mae_R_hl [unadj] − mae_R_close [div-adj]): p25=-0.1702 p50=-0.0927 p75=-0.0375 [mixed-basis; see BASIS NOTE]

**a15 | pos63** (n=2547)
- Stop-touch rate: close=25.5% → intraday=31.9% (Δ=+6.4%)
- Win rate: close=52.9% → intraday=50.4% (Δ=-2.5%)
- Median policy R (intraday stop-overlay): close=0.575 → stop-overlay=0.470 (Δ=-0.105). [STOPPED rows: R=−1; others: close-basis proxy from W0.1]
- MAE understatement (mae_R_hl [unadj] − mae_R_close [div-adj]): p25=-0.1705 p50=-0.0925 p75=-0.0374 [mixed-basis; see BASIS NOTE]

**a9 | rot21** (n=482)
- Stop-touch rate: close=16.4% → intraday=18.9% (Δ=+2.5%)
- Win rate: close=26.3% → intraday=29.3% (Δ=+2.9%)
- Median policy R (intraday stop-overlay): close=0.318 → stop-overlay=0.317 (Δ=-0.001). [STOPPED rows: R=−1; others: close-basis proxy from W0.1]
- MAE understatement (mae_R_hl [unadj] − mae_R_close [div-adj]): p25=-0.1678 p50=-0.1012 p75=-0.0425 [mixed-basis; see BASIS NOTE]

**a9 | pos63** (n=482)
- Stop-touch rate: close=29.3% → intraday=36.3% (Δ=+7.0%)
- Win rate: close=47.1% → intraday=45.2% (Δ=-1.9%)
- Median policy R (intraday stop-overlay): close=0.202 → stop-overlay=0.159 (Δ=-0.042). [STOPPED rows: R=−1; others: close-basis proxy from W0.1]
- MAE understatement (mae_R_hl [unadj] − mae_R_close [div-adj]): p25=-0.1678 p50=-0.1012 p75=-0.0425 [mixed-basis; see BASIS NOTE]

**a17 | rot21** (n=304)
- Stop-touch rate: close=18.8% → intraday=22.0% (Δ=+3.3%)
- Win rate: close=30.3% → intraday=33.6% (Δ=+3.3%)
- Median policy R (intraday stop-overlay): close=0.427 → stop-overlay=0.407 (Δ=-0.020). [STOPPED rows: R=−1; others: close-basis proxy from W0.1]
- MAE understatement (mae_R_hl [unadj] − mae_R_close [div-adj]): p25=-0.1770 p50=-0.1073 p75=-0.0403 [mixed-basis; see BASIS NOTE]

**a17 | pos63** (n=304)
- Stop-touch rate: close=28.0% → intraday=33.9% (Δ=+5.9%)
- Win rate: close=48.4% → intraday=47.0% (Δ=-1.3%)
- Median policy R (intraday stop-overlay): close=0.322 → stop-overlay=0.286 (Δ=-0.035). [STOPPED rows: R=−1; others: close-basis proxy from W0.1]
- MAE understatement (mae_R_hl [unadj] − mae_R_close [div-adj]): p25=-0.1770 p50=-0.1073 p75=-0.0403 [mixed-basis; see BASIS NOTE]

**routing_6 | rot21** (n=554)
- Stop-touch rate: close=24.9% → intraday=31.0% (Δ=+6.1%)
- Win rate: close=33.0% → intraday=37.9% (Δ=+4.9%)
- Median policy R (intraday stop-overlay): close=0.216 → stop-overlay=0.158 (Δ=-0.058). [STOPPED rows: R=−1; others: close-basis proxy from W0.1]
- MAE understatement (mae_R_hl [unadj] − mae_R_close [div-adj]): p25=-0.2519 p50=-0.1291 p75=-0.0592 [mixed-basis; see BASIS NOTE]

**routing_6 | pos63** (n=553)
- Stop-touch rate: close=41.4% → intraday=48.3% (Δ=+6.9%)
- Win rate: close=49.0% → intraday=44.7% (Δ=-4.3%)
- Median policy R (intraday stop-overlay): close=0.247 → stop-overlay=-0.314 (Δ=-0.561). [STOPPED rows: R=−1; others: close-basis proxy from W0.1]
- MAE understatement (mae_R_hl [unadj] − mae_R_close [div-adj]): p25=-0.2521 p50=-0.1292 p75=-0.0590 [mixed-basis; see BASIS NOTE]


---

## Coverage Table

### Coverage Table (rows excluded per node)

| Node | Total rows | Excluded (no OHLC) | Included |
|---|---|---|---|
| XLB | 1960 | 0 | 1960 |
| XLC | 106 | 0 | 106 |
| XLE | 2028 | 0 | 2028 |
| XLF | 1798 | 0 | 1798 |
| XLI | 1098 | 0 | 1098 |
| XLK | 1528 | 0 | 1528 |
| XLP | 562 | 0 | 562 |
| XLRE | 686 | 0 | 686 |
| XLU | 938 | 0 | 938 |
| XLV | 678 | 0 | 678 |
| XLY | 418 | 0 | 418 |


---

## Vendor Cross-Check Results (yahoo H/L vs massive_stock_day)

> 2021-07-06+ overlap. % of bars with |Δ|>0.2% per ticker.
> Divergence >2% of bars on any ticker = STOP and report (spec §2).

```
    XLK: n_overlap=1254 [level-ratio≈0.50=split; returns-based OK] HIGH_ret_div>0.2%=0.1% LOW_ret_div>0.2%=0.1%
    XLV: n_overlap=1254 HIGH_ret_div>0.2%=0.0% LOW_ret_div>0.2%=0.0%
    XLF: n_overlap=1254 HIGH_ret_div>0.2%=0.0% LOW_ret_div>0.2%=0.0%
    XLY: n_overlap=1254 [level-ratio≈0.50=split; returns-based OK] HIGH_ret_div>0.2%=0.1% LOW_ret_div>0.2%=0.1%
    XLI: n_overlap=1254 HIGH_ret_div>0.2%=0.0% LOW_ret_div>0.2%=0.0%
    XLP: n_overlap=1254 HIGH_ret_div>0.2%=0.0% LOW_ret_div>0.2%=0.0%
    XLE: n_overlap=1254 [level-ratio≈0.50=split; returns-based OK] HIGH_ret_div>0.2%=0.1% LOW_ret_div>0.2%=0.1%
    XLU: n_overlap=1254 [level-ratio≈0.50=split; returns-based OK] HIGH_ret_div>0.2%=0.1% LOW_ret_div>0.2%=0.1%
    XLB: n_overlap=1254 [level-ratio≈0.50=split; returns-based OK] HIGH_ret_div>0.2%=0.1% LOW_ret_div>0.2%=0.1%
    SPY: n_overlap=1254 HIGH_ret_div>0.2%=0.2% LOW_ret_div>0.2%=0.2%
```


---

## Intraday-True Terminal State Tables


### Family: ep_onset_in

### ep_onset_in | rot21 — INTRADAY H/L
> **unadjusted OHLC (auto_adjust=False); dividend drag unmodeled per W0_2_SPEC §2; intraday H/L barrier race — stop=low touch (longs) / high touch (shorts)**
> Every table: n + excluded count. The word 'validated' does not appear per Oracle Constitution §II.
> W0.2 calibrates W0.1; concordance delta is the headline deliverable, not a new event study.

n_covered=357, n_excluded_no_ohlc=0, n_matured=355

| State (intraday H/L) | N | % |
|---|---|---|
| STOPPED | 48 | 13.5% |
| DEAD_MONEY | 210 | 59.2% |
| CUSHIONED | 0 | 0.0% |
| CLEAN_LIFTOFF | 97 | 27.3% |

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 27.3%

**MFE_R_HL@21d:** p10=0.20 p25=0.41 p50=0.69 p75=1.06 p90=1.61 mean=0.82
**MAE_R_HL@21d:** p10=-1.20 p25=-0.68 p50=-0.31 p75=-0.12 p90=-0.03 mean=-0.52
**MFE_R_HL@63d:** p10=0.20 p25=0.41 p50=0.69 p75=1.06 p90=1.61 mean=0.82
**MAE_R_HL@63d:** p10=-1.20 p25=-0.68 p50=-0.31 p75=-0.12 p90=-0.03 mean=-0.52

### ep_onset_in | pos63 — INTRADAY H/L
> **unadjusted OHLC (auto_adjust=False); dividend drag unmodeled per W0_2_SPEC §2; intraday H/L barrier race — stop=low touch (longs) / high touch (shorts)**
> Every table: n + excluded count. The word 'validated' does not appear per Oracle Constitution §II.
> W0.2 calibrates W0.1; concordance delta is the headline deliverable, not a new event study.

n_covered=357, n_excluded_no_ohlc=0, n_matured=350

| State (intraday H/L) | N | % |
|---|---|---|
| STOPPED | 127 | 36.3% |
| DEAD_MONEY | 57 | 16.3% |
| CUSHIONED | 101 | 28.9% |
| CLEAN_LIFTOFF | 65 | 18.6% |

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 47.4%

**MFE_R_HL@21d:** p10=0.20 p25=0.40 p50=0.68 p75=1.06 p90=1.61 mean=0.81
**MAE_R_HL@21d:** p10=-1.21 p25=-0.69 p50=-0.31 p75=-0.12 p90=-0.03 mean=-0.52
**MFE_R_HL@63d:** p10=0.30 p25=0.63 p50=1.20 p75=1.83 p90=2.56 mean=1.34
**MAE_R_HL@63d:** p10=-2.69 p25=-1.40 p50=-0.65 p75=-0.23 p90=-0.07 mean=-1.12


### Family: ep_onset_out

### ep_onset_out | rot21 — INTRADAY H/L
> **unadjusted OHLC (auto_adjust=False); dividend drag unmodeled per W0_2_SPEC §2; intraday H/L barrier race — stop=low touch (longs) / high touch (shorts)**
> Every table: n + excluded count. The word 'validated' does not appear per Oracle Constitution §II.
> W0.2 calibrates W0.1; concordance delta is the headline deliverable, not a new event study.

n_covered=392, n_excluded_no_ohlc=0, n_matured=388

| State (intraday H/L) | N | % |
|---|---|---|
| STOPPED | 100 | 25.8% |
| DEAD_MONEY | 100 | 25.8% |
| CUSHIONED | 0 | 0.0% |
| CLEAN_LIFTOFF | 188 | 48.5% |

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 48.5%

**MFE_R_HL@21d:** p10=0.26 p25=0.53 p50=0.95 p75=1.56 p90=2.29 mean=1.18
**MAE_R_HL@21d:** p10=-1.57 p25=-1.14 p50=-0.66 p75=-0.34 p90=-0.17 mean=-0.79
**MFE_R_HL@63d:** p10=0.26 p25=0.53 p50=0.95 p75=1.56 p90=2.29 mean=1.18
**MAE_R_HL@63d:** p10=-1.57 p25=-1.14 p50=-0.66 p75=-0.34 p90=-0.17 mean=-0.79

### ep_onset_out | pos63 — INTRADAY H/L
> **unadjusted OHLC (auto_adjust=False); dividend drag unmodeled per W0_2_SPEC §2; intraday H/L barrier race — stop=low touch (longs) / high touch (shorts)**
> Every table: n + excluded count. The word 'validated' does not appear per Oracle Constitution §II.
> W0.2 calibrates W0.1; concordance delta is the headline deliverable, not a new event study.

n_covered=392, n_excluded_no_ohlc=0, n_matured=384

| State (intraday H/L) | N | % |
|---|---|---|
| STOPPED | 220 | 57.3% |
| DEAD_MONEY | 14 | 3.6% |
| CUSHIONED | 41 | 10.7% |
| CLEAN_LIFTOFF | 109 | 28.4% |

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 39.1%

**MFE_R_HL@21d:** p10=0.26 p25=0.53 p50=0.95 p75=1.56 p90=2.29 mean=1.18
**MAE_R_HL@21d:** p10=-1.56 p25=-1.14 p50=-0.66 p75=-0.34 p90=-0.17 mean=-0.79
**MFE_R_HL@63d:** p10=0.32 p25=0.66 p50=1.22 p75=2.14 p90=3.37 mean=1.65
**MAE_R_HL@63d:** p10=-2.85 p25=-2.25 p50=-1.39 p75=-0.67 p90=-0.30 mean=-1.57


### Family: washout_p8

### washout_p8 | rot21 | dedup=raw (appendix) — INTRADAY H/L
> **unadjusted OHLC (auto_adjust=False); dividend drag unmodeled per W0_2_SPEC §2; intraday H/L barrier race — stop=low touch (longs) / high touch (shorts)**
> Every table: n + excluded count. The word 'validated' does not appear per Oracle Constitution §II.
> W0.2 calibrates W0.1; concordance delta is the headline deliverable, not a new event study.

n_covered=641, n_excluded_no_ohlc=0, n_matured=639

| State (intraday H/L) | N | % |
|---|---|---|
| STOPPED | 128 | 20.0% |
| DEAD_MONEY | 339 | 53.1% |
| CUSHIONED | 0 | 0.0% |
| CLEAN_LIFTOFF | 172 | 26.9% |

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 26.9%

**MFE_R_HL@21d:** p10=0.15 p25=0.36 p50=0.68 p75=1.06 p90=1.50 mean=0.77
**MAE_R_HL@21d:** p10=-1.46 p25=-0.90 p50=-0.45 p75=-0.18 p90=-0.05 mean=-0.68
**MFE_R_HL@63d:** p10=0.15 p25=0.36 p50=0.68 p75=1.06 p90=1.50 mean=0.77
**MAE_R_HL@63d:** p10=-1.46 p25=-0.90 p50=-0.45 p75=-0.18 p90=-0.05 mean=-0.68

### washout_p8 | rot21 | dedup=first21 (headline) — INTRADAY H/L
> **unadjusted OHLC (auto_adjust=False); dividend drag unmodeled per W0_2_SPEC §2; intraday H/L barrier race — stop=low touch (longs) / high touch (shorts)**
> Every table: n + excluded count. The word 'validated' does not appear per Oracle Constitution §II.
> W0.2 calibrates W0.1; concordance delta is the headline deliverable, not a new event study.

n_covered=577, n_excluded_no_ohlc=0, n_matured=576

| State (intraday H/L) | N | % |
|---|---|---|
| STOPPED | 116 | 20.1% |
| DEAD_MONEY | 310 | 53.8% |
| CUSHIONED | 0 | 0.0% |
| CLEAN_LIFTOFF | 150 | 26.0% |

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 26.0%

**MFE_R_HL@21d:** p10=0.15 p25=0.36 p50=0.68 p75=1.03 p90=1.46 mean=0.76
**MAE_R_HL@21d:** p10=-1.47 p25=-0.90 p50=-0.46 p75=-0.19 p90=-0.06 mean=-0.68
**MFE_R_HL@63d:** p10=0.15 p25=0.36 p50=0.68 p75=1.03 p90=1.46 mean=0.76
**MAE_R_HL@63d:** p10=-1.47 p25=-0.90 p50=-0.46 p75=-0.19 p90=-0.06 mean=-0.68

### washout_p8 | pos63 | dedup=raw (appendix) — INTRADAY H/L
> **unadjusted OHLC (auto_adjust=False); dividend drag unmodeled per W0_2_SPEC §2; intraday H/L barrier race — stop=low touch (longs) / high touch (shorts)**
> Every table: n + excluded count. The word 'validated' does not appear per Oracle Constitution §II.
> W0.2 calibrates W0.1; concordance delta is the headline deliverable, not a new event study.

n_covered=641, n_excluded_no_ohlc=0, n_matured=629

| State (intraday H/L) | N | % |
|---|---|---|
| STOPPED | 248 | 39.4% |
| DEAD_MONEY | 102 | 16.2% |
| CUSHIONED | 152 | 24.2% |
| CLEAN_LIFTOFF | 127 | 20.2% |

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 44.4%

**MFE_R_HL@21d:** p10=0.15 p25=0.36 p50=0.67 p75=1.05 p90=1.50 mean=0.77
**MAE_R_HL@21d:** p10=-1.47 p25=-0.90 p50=-0.45 p75=-0.18 p90=-0.05 mean=-0.68
**MFE_R_HL@63d:** p10=0.30 p25=0.65 p50=1.16 p75=1.93 p90=2.70 mean=1.38
**MAE_R_HL@63d:** p10=-2.57 p25=-1.57 p50=-0.84 p75=-0.33 p90=-0.12 mean=-1.18

### washout_p8 | pos63 | dedup=first21 (headline) — INTRADAY H/L
> **unadjusted OHLC (auto_adjust=False); dividend drag unmodeled per W0_2_SPEC §2; intraday H/L barrier race — stop=low touch (longs) / high touch (shorts)**
> Every table: n + excluded count. The word 'validated' does not appear per Oracle Constitution §II.
> W0.2 calibrates W0.1; concordance delta is the headline deliverable, not a new event study.

n_covered=577, n_excluded_no_ohlc=0, n_matured=566

| State (intraday H/L) | N | % |
|---|---|---|
| STOPPED | 225 | 39.8% |
| DEAD_MONEY | 94 | 16.6% |
| CUSHIONED | 136 | 24.0% |
| CLEAN_LIFTOFF | 111 | 19.6% |

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 43.6%

**MFE_R_HL@21d:** p10=0.15 p25=0.35 p50=0.67 p75=1.02 p90=1.44 mean=0.75
**MAE_R_HL@21d:** p10=-1.47 p25=-0.91 p50=-0.46 p75=-0.19 p90=-0.06 mean=-0.69
**MFE_R_HL@63d:** p10=0.30 p25=0.64 p50=1.13 p75=1.89 p90=2.66 mean=1.36
**MAE_R_HL@63d:** p10=-2.60 p25=-1.58 p50=-0.85 p75=-0.33 p90=-0.13 mean=-1.19


### Family: a15

### a15 | rot21 | dedup=raw (appendix) — INTRADAY H/L
> **unadjusted OHLC (auto_adjust=False); dividend drag unmodeled per W0_2_SPEC §2; intraday H/L barrier race — stop=low touch (longs) / high touch (shorts)**
> Every table: n + excluded count. The word 'validated' does not appear per Oracle Constitution §II.
> W0.2 calibrates W0.1; concordance delta is the headline deliverable, not a new event study.

n_covered=2367, n_excluded_no_ohlc=0, n_matured=2357

| State (intraday H/L) | N | % |
|---|---|---|
| STOPPED | 326 | 13.8% |
| DEAD_MONEY | 1221 | 51.8% |
| CUSHIONED | 0 | 0.0% |
| CLEAN_LIFTOFF | 810 | 34.4% |

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 34.4%

**MFE_R_HL@21d:** p10=0.22 p25=0.45 p50=0.78 p75=1.21 p90=1.72 mean=0.90
**MAE_R_HL@21d:** p10=-1.16 p25=-0.74 p50=-0.39 p75=-0.16 p90=-0.03 mean=-0.54
**MFE_R_HL@63d:** p10=0.22 p25=0.45 p50=0.78 p75=1.21 p90=1.72 mean=0.90
**MAE_R_HL@63d:** p10=-1.16 p25=-0.74 p50=-0.39 p75=-0.16 p90=-0.03 mean=-0.54

### a15 | rot21 | dedup=first21 (headline) — INTRADAY H/L
> **unadjusted OHLC (auto_adjust=False); dividend drag unmodeled per W0_2_SPEC §2; intraday H/L barrier race — stop=low touch (longs) / high touch (shorts)**
> Every table: n + excluded count. The word 'validated' does not appear per Oracle Constitution §II.
> W0.2 calibrates W0.1; concordance delta is the headline deliverable, not a new event study.

n_covered=197, n_excluded_no_ohlc=0, n_matured=196

| State (intraday H/L) | N | % |
|---|---|---|
| STOPPED | 39 | 19.9% |
| DEAD_MONEY | 76 | 38.8% |
| CUSHIONED | 0 | 0.0% |
| CLEAN_LIFTOFF | 81 | 41.3% |

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 41.3%

**MFE_R_HL@21d:** p10=0.21 p25=0.53 p50=0.93 p75=1.30 p90=1.78 mean=0.96
**MAE_R_HL@21d:** p10=-1.59 p25=-0.89 p50=-0.50 p75=-0.19 p90=-0.03 mean=-0.68
**MFE_R_HL@63d:** p10=0.21 p25=0.53 p50=0.93 p75=1.30 p90=1.78 mean=0.96
**MAE_R_HL@63d:** p10=-1.59 p25=-0.89 p50=-0.50 p75=-0.19 p90=-0.03 mean=-0.68

### a15 | pos63 | dedup=raw (appendix) — INTRADAY H/L
> **unadjusted OHLC (auto_adjust=False); dividend drag unmodeled per W0_2_SPEC §2; intraday H/L barrier race — stop=low touch (longs) / high touch (shorts)**
> Every table: n + excluded count. The word 'validated' does not appear per Oracle Constitution §II.
> W0.2 calibrates W0.1; concordance delta is the headline deliverable, not a new event study.

n_covered=2367, n_excluded_no_ohlc=0, n_matured=2353

| State (intraday H/L) | N | % |
|---|---|---|
| STOPPED | 750 | 31.9% |
| DEAD_MONEY | 428 | 18.2% |
| CUSHIONED | 616 | 26.2% |
| CLEAN_LIFTOFF | 559 | 23.8% |

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 49.9%

**MFE_R_HL@21d:** p10=0.22 p25=0.45 p50=0.78 p75=1.21 p90=1.72 mean=0.90
**MAE_R_HL@21d:** p10=-1.16 p25=-0.74 p50=-0.39 p75=-0.16 p90=-0.03 mean=-0.54
**MFE_R_HL@63d:** p10=0.39 p25=0.78 p50=1.30 p75=2.04 p90=2.87 mean=1.53
**MAE_R_HL@63d:** p10=-2.08 p25=-1.22 p50=-0.61 p75=-0.27 p90=-0.08 mean=-0.91

### a15 | pos63 | dedup=first21 (headline) — INTRADAY H/L
> **unadjusted OHLC (auto_adjust=False); dividend drag unmodeled per W0_2_SPEC §2; intraday H/L barrier race — stop=low touch (longs) / high touch (shorts)**
> Every table: n + excluded count. The word 'validated' does not appear per Oracle Constitution §II.
> W0.2 calibrates W0.1; concordance delta is the headline deliverable, not a new event study.

n_covered=197, n_excluded_no_ohlc=0, n_matured=196

| State (intraday H/L) | N | % |
|---|---|---|
| STOPPED | 62 | 31.6% |
| DEAD_MONEY | 25 | 12.8% |
| CUSHIONED | 53 | 27.0% |
| CLEAN_LIFTOFF | 56 | 28.6% |

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 55.6%

**MFE_R_HL@21d:** p10=0.21 p25=0.53 p50=0.93 p75=1.30 p90=1.78 mean=0.96
**MAE_R_HL@21d:** p10=-1.59 p25=-0.89 p50=-0.50 p75=-0.19 p90=-0.03 mean=-0.68
**MFE_R_HL@63d:** p10=0.45 p25=0.83 p50=1.44 p75=2.25 p90=2.91 mean=1.65
**MAE_R_HL@63d:** p10=-2.33 p25=-1.26 p50=-0.71 p75=-0.35 p90=-0.10 mean=-0.98


### Family: a9

### a9 | rot21 | dedup=raw (appendix) — INTRADAY H/L
> **unadjusted OHLC (auto_adjust=False); dividend drag unmodeled per W0_2_SPEC §2; intraday H/L barrier race — stop=low touch (longs) / high touch (shorts)**
> Every table: n + excluded count. The word 'validated' does not appear per Oracle Constitution §II.
> W0.2 calibrates W0.1; concordance delta is the headline deliverable, not a new event study.

n_covered=446, n_excluded_no_ohlc=0, n_matured=438

| State (intraday H/L) | N | % |
|---|---|---|
| STOPPED | 78 | 17.8% |
| DEAD_MONEY | 234 | 53.4% |
| CUSHIONED | 0 | 0.0% |
| CLEAN_LIFTOFF | 126 | 28.8% |

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 28.8%

**MFE_R_HL@21d:** p10=0.21 p25=0.42 p50=0.72 p75=1.15 p90=1.53 mean=0.80
**MAE_R_HL@21d:** p10=-1.43 p25=-0.82 p50=-0.53 p75=-0.26 p90=-0.07 mean=-0.69
**MFE_R_HL@63d:** p10=0.21 p25=0.42 p50=0.72 p75=1.15 p90=1.53 mean=0.80
**MAE_R_HL@63d:** p10=-1.43 p25=-0.82 p50=-0.53 p75=-0.26 p90=-0.07 mean=-0.69

### a9 | rot21 | dedup=first21 (headline) — INTRADAY H/L
> **unadjusted OHLC (auto_adjust=False); dividend drag unmodeled per W0_2_SPEC §2; intraday H/L barrier race — stop=low touch (longs) / high touch (shorts)**
> Every table: n + excluded count. The word 'validated' does not appear per Oracle Constitution §II.
> W0.2 calibrates W0.1; concordance delta is the headline deliverable, not a new event study.

n_covered=46, n_excluded_no_ohlc=0, n_matured=44

| State (intraday H/L) | N | % |
|---|---|---|
| STOPPED | 13 | 29.5% |
| DEAD_MONEY | 16 | 36.4% |
| CUSHIONED | 0 | 0.0% |
| CLEAN_LIFTOFF | 15 | 34.1% |

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 34.1%

**MFE_R_HL@21d:** p10=0.23 p25=0.46 p50=0.82 p75=1.28 p90=1.55 mean=0.85
**MAE_R_HL@21d:** p10=-1.83 p25=-1.09 p50=-0.62 p75=-0.27 p90=-0.02 mean=-0.87
**MFE_R_HL@63d:** p10=0.23 p25=0.46 p50=0.82 p75=1.28 p90=1.55 mean=0.85
**MAE_R_HL@63d:** p10=-1.83 p25=-1.09 p50=-0.62 p75=-0.27 p90=-0.02 mean=-0.87

### a9 | pos63 | dedup=raw (appendix) — INTRADAY H/L
> **unadjusted OHLC (auto_adjust=False); dividend drag unmodeled per W0_2_SPEC §2; intraday H/L barrier race — stop=low touch (longs) / high touch (shorts)**
> Every table: n + excluded count. The word 'validated' does not appear per Oracle Constitution §II.
> W0.2 calibrates W0.1; concordance delta is the headline deliverable, not a new event study.

n_covered=446, n_excluded_no_ohlc=0, n_matured=438

| State (intraday H/L) | N | % |
|---|---|---|
| STOPPED | 156 | 35.6% |
| DEAD_MONEY | 87 | 19.9% |
| CUSHIONED | 104 | 23.7% |
| CLEAN_LIFTOFF | 91 | 20.8% |

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 44.5%

**MFE_R_HL@21d:** p10=0.21 p25=0.42 p50=0.72 p75=1.15 p90=1.53 mean=0.80
**MAE_R_HL@21d:** p10=-1.43 p25=-0.82 p50=-0.53 p75=-0.26 p90=-0.07 mean=-0.69
**MFE_R_HL@63d:** p10=0.32 p25=0.58 p50=1.31 p75=1.91 p90=2.79 mean=1.38
**MAE_R_HL@63d:** p10=-2.12 p25=-1.31 p50=-0.73 p75=-0.36 p90=-0.13 mean=-1.07

### a9 | pos63 | dedup=first21 (headline) — INTRADAY H/L
> **unadjusted OHLC (auto_adjust=False); dividend drag unmodeled per W0_2_SPEC §2; intraday H/L barrier race — stop=low touch (longs) / high touch (shorts)**
> Every table: n + excluded count. The word 'validated' does not appear per Oracle Constitution §II.
> W0.2 calibrates W0.1; concordance delta is the headline deliverable, not a new event study.

n_covered=46, n_excluded_no_ohlc=0, n_matured=44

| State (intraday H/L) | N | % |
|---|---|---|
| STOPPED | 19 | 43.2% |
| DEAD_MONEY | 2 | 4.5% |
| CUSHIONED | 12 | 27.3% |
| CLEAN_LIFTOFF | 11 | 25.0% |

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 52.3%

**MFE_R_HL@21d:** p10=0.23 p25=0.46 p50=0.82 p75=1.28 p90=1.55 mean=0.85
**MAE_R_HL@21d:** p10=-1.83 p25=-1.09 p50=-0.62 p75=-0.27 p90=-0.02 mean=-0.87
**MFE_R_HL@63d:** p10=0.37 p25=0.71 p50=1.48 p75=2.04 p90=2.81 mean=1.49
**MAE_R_HL@63d:** p10=-2.95 p25=-1.59 p50=-0.85 p75=-0.39 p90=-0.15 mean=-1.32


### Family: a17

### a17 | rot21 | dedup=raw (appendix) — INTRADAY H/L
> **unadjusted OHLC (auto_adjust=False); dividend drag unmodeled per W0_2_SPEC §2; intraday H/L barrier race — stop=low touch (longs) / high touch (shorts)**
> Every table: n + excluded count. The word 'validated' does not appear per Oracle Constitution §II.
> W0.2 calibrates W0.1; concordance delta is the headline deliverable, not a new event study.

n_covered=268, n_excluded_no_ohlc=0, n_matured=262

| State (intraday H/L) | N | % |
|---|---|---|
| STOPPED | 56 | 21.4% |
| DEAD_MONEY | 117 | 44.7% |
| CUSHIONED | 0 | 0.0% |
| CLEAN_LIFTOFF | 89 | 34.0% |

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 34.0%

**MFE_R_HL@21d:** p10=0.28 p25=0.49 p50=0.82 p75=1.21 p90=1.74 mean=0.89
**MAE_R_HL@21d:** p10=-1.73 p25=-0.87 p50=-0.55 p75=-0.25 p90=-0.03 mean=-0.77
**MFE_R_HL@63d:** p10=0.28 p25=0.49 p50=0.82 p75=1.21 p90=1.74 mean=0.89
**MAE_R_HL@63d:** p10=-1.73 p25=-0.87 p50=-0.55 p75=-0.25 p90=-0.03 mean=-0.77

### a17 | rot21 | dedup=first21 (headline) — INTRADAY H/L
> **unadjusted OHLC (auto_adjust=False); dividend drag unmodeled per W0_2_SPEC §2; intraday H/L barrier race — stop=low touch (longs) / high touch (shorts)**
> Every table: n + excluded count. The word 'validated' does not appear per Oracle Constitution §II.
> W0.2 calibrates W0.1; concordance delta is the headline deliverable, not a new event study.

n_covered=44, n_excluded_no_ohlc=0, n_matured=42

| State (intraday H/L) | N | % |
|---|---|---|
| STOPPED | 11 | 26.2% |
| DEAD_MONEY | 18 | 42.9% |
| CUSHIONED | 0 | 0.0% |
| CLEAN_LIFTOFF | 13 | 31.0% |

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 31.0%

**MFE_R_HL@21d:** p10=0.37 p25=0.54 p50=0.86 p75=1.24 p90=1.50 mean=0.89
**MAE_R_HL@21d:** p10=-1.85 p25=-1.01 p50=-0.59 p75=-0.29 p90=-0.00 mean=-0.86
**MFE_R_HL@63d:** p10=0.37 p25=0.54 p50=0.86 p75=1.24 p90=1.50 mean=0.89
**MAE_R_HL@63d:** p10=-1.85 p25=-1.01 p50=-0.59 p75=-0.29 p90=-0.00 mean=-0.86

### a17 | pos63 | dedup=raw (appendix) — INTRADAY H/L
> **unadjusted OHLC (auto_adjust=False); dividend drag unmodeled per W0_2_SPEC §2; intraday H/L barrier race — stop=low touch (longs) / high touch (shorts)**
> Every table: n + excluded count. The word 'validated' does not appear per Oracle Constitution §II.
> W0.2 calibrates W0.1; concordance delta is the headline deliverable, not a new event study.

n_covered=268, n_excluded_no_ohlc=0, n_matured=262

| State (intraday H/L) | N | % |
|---|---|---|
| STOPPED | 88 | 33.6% |
| DEAD_MONEY | 53 | 20.2% |
| CUSHIONED | 55 | 21.0% |
| CLEAN_LIFTOFF | 66 | 25.2% |

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 46.2%

**MFE_R_HL@21d:** p10=0.28 p25=0.49 p50=0.82 p75=1.21 p90=1.74 mean=0.89
**MAE_R_HL@21d:** p10=-1.73 p25=-0.87 p50=-0.55 p75=-0.25 p90=-0.03 mean=-0.77
**MFE_R_HL@63d:** p10=0.38 p25=0.66 p50=1.31 p75=2.04 p90=2.80 mean=1.45
**MAE_R_HL@63d:** p10=-2.21 p25=-1.33 p50=-0.74 p75=-0.35 p90=-0.08 mean=-1.06

### a17 | pos63 | dedup=first21 (headline) — INTRADAY H/L
> **unadjusted OHLC (auto_adjust=False); dividend drag unmodeled per W0_2_SPEC §2; intraday H/L barrier race — stop=low touch (longs) / high touch (shorts)**
> Every table: n + excluded count. The word 'validated' does not appear per Oracle Constitution §II.
> W0.2 calibrates W0.1; concordance delta is the headline deliverable, not a new event study.

n_covered=44, n_excluded_no_ohlc=0, n_matured=42

| State (intraday H/L) | N | % |
|---|---|---|
| STOPPED | 15 | 35.7% |
| DEAD_MONEY | 5 | 11.9% |
| CUSHIONED | 11 | 26.2% |
| CLEAN_LIFTOFF | 11 | 26.2% |

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 52.4%

**MFE_R_HL@21d:** p10=0.37 p25=0.54 p50=0.86 p75=1.24 p90=1.50 mean=0.89
**MAE_R_HL@21d:** p10=-1.85 p25=-1.01 p50=-0.59 p75=-0.29 p90=-0.00 mean=-0.86
**MFE_R_HL@63d:** p10=0.50 p25=0.74 p50=1.27 p75=2.11 p90=2.75 mean=1.50
**MAE_R_HL@63d:** p10=-3.00 p25=-1.56 p50=-0.84 p75=-0.38 p90=-0.14 mean=-1.27


### Family: routing_6

### routing_6 | rot21 — INTRADAY H/L
> **unadjusted OHLC (auto_adjust=False); dividend drag unmodeled per W0_2_SPEC §2; intraday H/L barrier race — stop=low touch (longs) / high touch (shorts)**
> Every table: n + excluded count. The word 'validated' does not appear per Oracle Constitution §II.
> W0.2 calibrates W0.1; concordance delta is the headline deliverable, not a new event study.

n_covered=565, n_excluded_no_ohlc=0, n_matured=554

| State (intraday H/L) | N | % |
|---|---|---|
| STOPPED | 172 | 31.0% |
| DEAD_MONEY | 172 | 31.0% |
| CUSHIONED | 0 | 0.0% |
| CLEAN_LIFTOFF | 210 | 37.9% |

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 37.9%

**MFE_R_HL@21d:** p10=0.15 p25=0.40 p50=0.82 p75=1.29 p90=1.69 mean=0.88
**MAE_R_HL@21d:** p10=-2.00 p25=-1.19 p50=-0.62 p75=-0.25 p90=-0.04 mean=-0.87
**MFE_R_HL@63d:** p10=0.15 p25=0.40 p50=0.82 p75=1.29 p90=1.69 mean=0.88
**MAE_R_HL@63d:** p10=-2.00 p25=-1.19 p50=-0.62 p75=-0.25 p90=-0.04 mean=-0.87

### routing_6 | pos63 — INTRADAY H/L
> **unadjusted OHLC (auto_adjust=False); dividend drag unmodeled per W0_2_SPEC §2; intraday H/L barrier race — stop=low touch (longs) / high touch (shorts)**
> Every table: n + excluded count. The word 'validated' does not appear per Oracle Constitution §II.
> W0.2 calibrates W0.1; concordance delta is the headline deliverable, not a new event study.

n_covered=565, n_excluded_no_ohlc=0, n_matured=553

| State (intraday H/L) | N | % |
|---|---|---|
| STOPPED | 267 | 48.3% |
| DEAD_MONEY | 39 | 7.1% |
| CUSHIONED | 106 | 19.2% |
| CLEAN_LIFTOFF | 141 | 25.5% |

**Win rate (CUSHIONED+CLEAN_LIFTOFF):** 44.7%

**MFE_R_HL@21d:** p10=0.15 p25=0.40 p50=0.82 p75=1.29 p90=1.69 mean=0.88
**MAE_R_HL@21d:** p10=-2.00 p25=-1.20 p50=-0.62 p75=-0.25 p90=-0.04 mean=-0.87
**MFE_R_HL@63d:** p10=0.28 p25=0.71 p50=1.38 p75=2.23 p90=3.04 mean=1.58
**MAE_R_HL@63d:** p10=-3.23 p25=-1.99 p50=-0.97 p75=-0.40 p90=-0.07 mean=-1.40
