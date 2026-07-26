# PSS-F1 — Down-volume envelope decay (forced-supply exhaustion on new lows)

Reset-CONFIRMER / exhaustion construction (copy law R-W1T-3). Pre-registered ruler + construction: script header, committed pre-run (prereg commit precedes results commit; measurement amendments M1/M2 disclosed there, both pre-outcome). Entry-timing ruler (§7), NOT hold returns (wrong-ruler check performed). Machinery (metric_arrays / null_stats / bars_for / tool_dates) COPIED from the W1 scripts. Inference: month-cluster bootstrap, NB=1000, seed 20260728. The commissioning session rules the verdict; this reports what was found.

## Coverage census (eligible / excluded, with reasons)

- Universe: 1300 W1-panel names with volume (all 1300 have volume).
- **F1-eligible: 943** (dv_halflife measurable AND ≥3 FIT + ≥3 TEST primary-cell fires with resolvable mae63/prox).
- **Excluded: 357** — few_fires: 352; no_dv_halflife: 5.
- Defensives disposition (expected structural ineligibility, accepted loss): COST→few_fires(fit=0,test=0), MCD→few_fires(fit=0,test=11).
- Defensives that DID qualify: KO, PEP, WMT, JNJ.
- dv_halflife (eligible names): median 46td, deciles [17.0, 46.0, 141.0]. Envelope window W: median 23 new-low bars, range 6–30.
- TEST F1 signals (primary cell, pooled): 15,360; random-new-low null pool (TEST): 76,949.

Panel all-days OOS base rates (median across eligible names): MAE63 -8.94%, within-5%-of-low 15.0%, called-low 8.4%.

## Grid (multiplicity budget: 4 cells) — TEST U_MAE / U_W5, name-level medians, WITH and WITHOUT the C32 gate

No per-name best-of-grid selection (DNR §2). Primary cell = (L=60, k=0.0). Point estimates are panel medians of per-name uplifts; the CI/inference row is the pooled month-cluster bootstrap on the primary cell below.

| cell | n names | U_MAE (no gate) | U_W5 (no gate) | U_MAE (C32 gate) | U_W5 (C32 gate) | n names gated |
|---|---|---|---|---|---|---|
| L=40, k=0.0 | 943 | +0.91pp | +27.20pp | +1.42pp | +25.17pp | 862 |
| L=40, k=0.5 | 941 | +0.69pp | +26.71pp | +1.25pp | +23.20pp | 785 |
| L=60, k=0.0 ★ | 943 | +1.34pp | +28.63pp | +1.32pp | +25.29pp | 857 |
| L=60, k=0.5 | 940 | +1.12pp | +27.47pp | +1.16pp | +24.98pp | 786 |

### Primary cell across eras (full TEST / 2021+ sub-window)

| era | U_MAE (no gate) | U_W5 (no gate) | U_MAE (gate) | U_W5 (gate) |
|---|---|---|---|---|
| full TEST ≥2020-07 | +1.34pp | +28.63pp | +1.32pp | +25.29pp |
| 2021+ ≥2021-01 | +1.47pp | +28.53pp | +1.57pp | +24.85pp |

## Inference — pooled month-cluster bootstrap (primary cell), vs BOTH nulls

U_MAE = median signal mae63 − all-days median (pp; + = shallower adverse = better entry). U_W5 = within-5%-of-low rate − all-days rate. Two nulls: (a) all-DAYS base rate [in the per-name null], (b) random NEW-LOW bars in the same declines (F1 falsifier).

| quantity | full TEST | 2021+ |
|---|---|---|
| F1 U_MAE (vs all-days null), no gate | [-0.03, +2.08] includes 0 | [+0.18, +2.48] excludes 0 ↑ |
| F1 U_W5 (vs all-days null), no gate | [-7.74, -5.96] excludes 0 ↓ | [-7.73, -5.56] excludes 0 ↓ |
| F1 U_MAE, C32 gate | [+0.01, +2.70] excludes 0 ↑ | [+0.29, +3.15] excludes 0 ↑ |
| F1 U_W5, C32 gate | [-7.90, -6.23] excludes 0 ↓ | [-7.94, -5.63] excludes 0 ↓ |
| random-new-low U_MAE (conditional null) | [-0.31, +2.07] includes 0 | [-0.03, +2.35] includes 0 |
| random-new-low U_W5 (conditional null) | [-7.81, -5.34] excludes 0 ↓ | [-7.88, -5.48] excludes 0 ↓ |
| F1 − random-new-low  U_MAE (FALSIFIER) | [-0.35, +0.66] includes 0 | [-0.39, +0.71] includes 0 |
| F1 − random-new-low  U_W5 (FALSIFIER) | [-0.82, +0.48] includes 0 | [-0.68, +0.60] includes 0 |
| F1(gate) − random-new-low  U_MAE | [-0.51, +1.40] includes 0 | [-0.47, +1.56] includes 0 |
| F1(gate) − random-new-low  U_W5 | [-1.21, +0.62] includes 0 | [-1.05, +0.90] includes 0 |

The FALSIFIER rows are the pre-stated kill: if F1 − random-new-low does not exclude 0 (positive) on U_MAE/U_W5, the contracting-envelope new-low bar carries no information beyond an ordinary new-low bar. Printed regardless of outcome.

## 2022-class containment (primary cell fire counts)

Charter prediction: STRUCTURALLY SILENT in H1-2022 (down-volume was elevating into each leg → envelope not contracting), coverage near the 2022-10-13 low. META/NVDA/PG are OFF-PANEL (fell to W1 eligibility) — run from raw OHLCV as named exhibits, flagged.

| name | class | H1-2022 fires | ±21td around 2022-10-13 low | total TEST fires |
|---|---|---|---|---|
| AAPL | mega-cap focus | 2 | 1 | 10 |
| MSFT | mega-cap focus | 0 | 4 | 6 |
| GOOGL | mega-cap focus | 4 | 3 | 9 |
| META (off-panel) | mega-cap focus | 9 | 3 | 14 |
| HD | mega-cap focus | 0 | 2 | 14 |
| JPM | mega-cap focus | 7 | 2 | 9 |
| XOM | mega-cap focus | 0 | 0 | 7 |
| NVDA (off-panel) | expected-FAIL | 0 | 5 | 5 |
| TSLA | expected-FAIL | 0 | 0 | 6 |

Mega-cap focus in-panel: AAPL, MSFT, GOOGL, HD, JPM, XOM. H1-2022 vs near-low counts test the containment claim per name above.

## Earliness vs incumbent (Stoch-RSI<20 cross @ derived rung, SAME names)

td_to_trough: negative = trough BEFORE the fire (late confirmer); positive = fire BEFORE the trough (pre-trough / early). Per-name medians over TEST, then panel median of those.

- Names with both F1 and incumbent TEST fires: 943.
- **F1 median td_to_trough (panel median of name medians): +12.0td** (n_fires median 14/name).
- **Incumbent median td_to_trough: -2.0td** (n median 19/name).
- Per-name (F1 − incumbent) td_to_trough, median: +12.0td (positive = F1 fires earlier / more pre-trough than the incumbent on the same name).

## Product split (descriptive; calls-low vs confirms-reset)

F1 primary-cell TEST fires (n=15,360): called-low (−2..+5td) 31% · confirmed-reset (<−2td) 0% · early (>+5td) 68% · median td_to_trough +13td.

## What was found (no verdict — the commissioning session rules)

- F1 (no gate) U_MAE vs the all-days null on full TEST: [-0.03, +2.08] (includes 0); U_W5 [-7.74, -5.96] (excludes 0 ↓).
- The pre-stated FALSIFIER (F1 − random-new-low): U_MAE [-0.35, +0.66] (includes 0), U_W5 [-0.82, +0.48] (includes 0) on full TEST; 2021+ U_MAE [-0.39, +0.71] (includes 0).
- The C32-gate column pair, the 2022 containment counts, and the earliness-vs-incumbent table above are the pre-registered conditioner reads. All nulls are printed.

## Limitations

- Closes-only MAE/troughs (house shadow-book form); intraday lows are deeper. Comparable across cells, not absolute.
- Survivor tape (data/baskets/ohlcv holds today's listings); per-name own-baseline netting removes level bias, not composition bias.
- Yahoo close is total-return adjusted; the log-slope envelope is level-invariant so the adjustment nets out of the contraction test.
- ±31td proximity window is the §7 pin; long bear legs make 'the low' window-relative. Random-new-low null shares this window (fair test).
- dv_halflife window derivation (M-final) rests on FIT-era down-day ACF; the lag-1 form (charter sketch) was degenerate and re-pinned pre-outcome (M1). W is a bucketed monotone map, not outcome-tuned.
- META/NVDA/PG are off the W1 panel (W1 eligibility); the containment diagnostic runs them as raw-OHLCV exhibits, flagged.
