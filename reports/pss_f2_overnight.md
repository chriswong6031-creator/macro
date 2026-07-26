# PSS-F2 — Overnight-vs-intraday return decomposition flip (who is selling)

Reset-CONFIRMER / session-accumulation construction (copy law R-W1T-3 — no 'bottom caller' / 'calls bottoms'). Pre-registered ruler + construction: script header, committed pre-run (prereg commit precedes results commit in git history). Entry-timing ruler (§7), NOT hold returns (wrong-ruler check performed; motive #1458). Machinery (metric_arrays / null_stats / bars_for / tool_dates / _name_uplift per-name-first) COPIED from the W1 + F1 scripts. Inference: month-cluster bootstrap, NB=1000, seed 20260729. The commissioning session rules the verdict; this reports what was found.

## Coverage census (eligible / excluded, with reasons)

- Universe: 1300 W1-panel names with OHLC incl. OPEN (rung_derived read per name from data/personality_timing/codex.parquet).
- **F2-eligible: 1288** (codex rung measurable AND ≥3 FIT + ≥3 TEST primary-cell (K=5, q=simple) fires with resolvable mae63/prox).
- **Excluded: 12** — few_fires: 12.
- Defensives that DID qualify: KO, PEP, WMT, COST, MCD, JNJ.
- Per-name overnight/intraday split ratio (|gap|/|session|, FIT): median 0.42, deciles [0.32, 0.42, 0.58] (≫1 = gap-dominated / intraday leg thinner). Baseline intraday-leg vol: median 1.93%.
- Gap-dominated eligible names (split ratio > 1): 23 (2%) — the intraday leg is comparatively thin there (all-gap-class risk carried openly).
- TEST F2 signals (primary cell, pooled): 84,494; net-return-analog fires (TEST, pooled): 218,394.

Panel all-days OOS base rates (median across eligible names): MAE63 -8.19%, within-5%-of-low 16.2%, called-low 8.4%.

## Grid (multiplicity budget: 4 cells) — TEST U_MAE / U_W5, name-level medians (RAW, no gate)

No per-name best-of-grid selection (DNR §2). Primary cell = (K=5, q=simple>0). Point estimates are panel medians of per-name uplifts; the CI/inference rows are the pooled month-cluster bootstrap on the primary cell below. q=simple → median(intraday)>0; q60 → median(intraday) ≥ the name's FIT 60th-pct of positive intraday.

| cell | n names | U_MAE | U_W5 | median OOS fires/name |
|---|---|---|---|---|
| K=3, q=simple | 1288 | -0.23pp | -2.58pp | 65 |
| K=3, q=q60 | 1276 | -0.96pp | -9.32pp | 19 |
| K=5, q=simple ★ | 1288 | -0.27pp | -2.64pp | 62 |
| K=5, q=q60 | 1237 | -1.32pp | -10.89pp | 12 |

### Primary cell across eras (full TEST / 2021+ sub-window), RAW

| era | U_MAE | U_W5 |
|---|---|---|
| full TEST ≥2020-07 | -0.27pp | -2.64pp |
| 2021+ ≥2021-01 | -0.15pp | -2.67pp |

## Gate variants on the primary cell (pre-stated column set: RAW / +ATR-veto / +C32), name-level medians

RAW carries F2's 2022 exposure honestly. +ATR-veto = fire only when ATR14[t] ≤ ATR14[t−21] (non-accelerating trailing range — the incumbent's accelerating-range veto analog). +C32 = decline-deceleration terminality gate (copied from pss_f1_downvol).

| variant | U_MAE OOS | U_W5 OOS | U_MAE 2021+ | U_W5 2021+ | n names OOS |
|---|---|---|---|---|---|
| RAW (no gate) | -0.27pp | -2.64pp | -0.15pp | -2.67pp | 1288 |
| +ATR-veto | -0.25pp | -3.10pp | -0.12pp | -2.79pp | 1288 |
| +C32 | +2.22pp | +37.60pp | +2.59pp | +37.76pp | 571 |

## Inference — month-cluster bootstrap (primary cell), vs BOTH nulls

Per-name-first collapse then cross-name median (matches the F1/W1-T machinery — the F1 E1 sign-flip bug is NOT repeated): within each month-cluster draw, U_MAE = name-median mae63 − name all-days median, U_W5 = name signal-day within-5%-of-low rate − name all-days rate, THEN the cross-name median. Two nulls: (a) all-DAYS base rate [inside the per-name uplift], (b) the NET-RETURN ANALOG (identical construction on net_ret — the decomposition-adds-nothing mirror placebo). The F2 − net-analog diff is PAIRED on the same resampled month-clusters.

Self-check (F1 E1 guard): direct per-name-median U_W5 = F2 -2.64pp / net-analog -6.75pp; the bootstrap point estimates below must match these within bootstrap noise.

| quantity | full TEST | 2021+ |
|---|---|---|
| F2 U_MAE (vs all-days null), RAW | [-1.49, +0.74] includes 0 | [-1.40, +0.91] includes 0 |
| F2 U_W5 (vs all-days null), RAW | [-5.66, -0.98] excludes 0 ↓ | [-5.48, -0.87] excludes 0 ↓ |
| F2 U_MAE, +ATR-veto | [-1.56, +0.69] includes 0 | [-1.50, +0.87] includes 0 |
| F2 U_W5, +ATR-veto | [-6.52, -2.04] excludes 0 ↓ | [-6.24, -1.67] excludes 0 ↓ |
| F2 U_MAE, +C32 | [-0.07, +3.60] includes 0 | [+0.39, +3.87] excludes 0 ↑ |
| F2 U_W5, +C32 | [-4.73, +69.11] includes 0 | [-3.98, +68.92] includes 0 |
| net-return-analog U_MAE (aggregate null) | [-1.06, +0.58] includes 0 | [-1.16, +0.53] includes 0 |
| net-return-analog U_W5 (aggregate null) | [-7.92, -5.73] excludes 0 ↓ | [-8.04, -5.79] excludes 0 ↓ |
| F2 − net-analog  U_MAE (FALSIFIER, paired) | [-0.76, +0.50] includes 0 | [-0.59, +0.68] includes 0 |
| F2 − net-analog  U_W5 (FALSIFIER, paired) | [+1.94, +5.06] excludes 0 ↑ | [+2.20, +5.19] excludes 0 ↑ |
| F2(ATR) − net-analog  U_MAE (paired) | [-0.92, +0.49] includes 0 | [-0.69, +0.71] includes 0 |
| F2(ATR) − net-analog  U_W5 (paired) | [+1.10, +4.15] excludes 0 ↑ | [+1.25, +4.60] excludes 0 ↑ |

The FALSIFIER rows are the pre-stated kill: if F2 − net-return-analog does NOT exclude 0 (positive) on U_MAE/U_W5, the DECOMPOSITION carries no incremental information over just watching close-to-close, and F2 dies as a standalone construction. Printed regardless of outcome.

## Overlap / disjointness census — F2 vs net-return analog (primary cell, TEST)

The whole F2 claim is that the intraday leg flips while net_ret is still negative — so F2 fires are NOT a subset of net-turn days; the placebo is a matched-construction counterfactual, not a disjoint complement.

- BOTH F2 & net-analog: 53,822 · F2-only (net_ret still ≤0 at fire): 30,672 (36% of F2 fires) · net-analog-only: 164,572.
- F2-only share confirms the composition inverts before the net does in 36% of F2 fires (the pre-registered mechanism); the net-analog is broader (218,394 fires) and largely non-overlapping — a genuine matched counterfactual.

## Earliness — F2 vs incumbent (Stoch-RSI<20 @ derived rung) AND vs net-return analog (SAME names)

td_to_trough: negative = trough BEFORE the fire (late confirmer); positive = fire BEFORE the trough (pre-trough / early). Per-name medians over TEST, then panel median of those. Charter hard requirement: F2 (in its required +ATR-veto form) must be STRICTLY earlier than BOTH the incumbent AND the net-analog, else the 'pre-trough' claim is RETRACTED to at/post.

| comparison | n names | F2(+ATR) median tdt | other median tdt | F2 − other (per-name median) | strictly earlier? |
|---|---|---|---|---|---|
| vs incumbent | 1288 | -9.0td | -2.0td | -8.0td | NO |
| vs net-analog | 1288 | -9.0td | -16.0td | +6.0td | YES |
| vs incumbent (RAW F2, context) | 1288 | -9.0td | -2.0td | -9.0td | NO |

## 2022-class containment (primary cell fire counts): RAW / +ATR-veto / +C32

Charter prediction: RAW fires INTO H1-2022 downtrends (F2 is the most 2022-exposed family); the ATR-veto must SUPPRESS that while retaining coverage near the 2022-10-13 low. TSLA/NVDA are the expected-all-gap-FAIL class. NVDA is OFF-PANEL (W1 eligibility) — run from raw OHLCV, flagged.

| name | class | H1-2022 (raw / +ATR / +C32) | ±21td 2022-low (raw / +ATR / +C32) |
|---|---|---|---|
| AAPL | mega-cap focus | 8 / 5 / 0 | 5 / 0 / 0 |
| MSFT | mega-cap focus | 7 / 6 / 0 | 5 / 0 / 0 |
| AMZN | mega-cap focus | 2 / 2 / 0 | 6 / 1 / 1 |
| GOOGL | mega-cap focus | 4 / 3 / 0 | 1 / 1 / 0 |
| UNH | mega-cap focus | 0 / 0 / 0 | 0 / 0 / 0 |
| HD | mega-cap focus | 2 / 2 / 0 | 0 / 0 / 0 |
| COST | mega-cap focus | 6 / 4 / 0 | 0 / 0 / 0 |
| TSLA | expected-FAIL (all-gap) | 4 / 2 / 0 | 0 / 0 / 0 |
| NVDA (off-panel) | expected-FAIL (all-gap) | 9 / 7 / 1 | 2 / 2 / 0 |

## Product split (descriptive; calls-low vs confirms-reset)

F2 primary-cell TEST fires (n=84,494): near-low (−2..+5td) 7% · confirmed-reset (<−2td) 58% · early (>+5td) 35% · median td_to_trough -10td.

## What was found (no verdict — the commissioning session rules)

- F2 (RAW) U_MAE vs the all-days null on full TEST: [-1.49, +0.74] (includes 0); U_W5 [-5.66, -0.98] (excludes 0 ↓).
- The pre-stated FALSIFIER (F2 − net-return analog, decomposition-adds-nothing): U_MAE [-0.76, +0.50] (includes 0), U_W5 [+1.94, +5.06] (excludes 0 ↑) on full TEST; 2021+ U_MAE [-0.59, +0.68] (includes 0), U_W5 [+2.20, +5.19] (excludes 0 ↑).
- The +ATR-veto and +C32 gate columns, the earliness-vs-incumbent AND earliness-vs-net-analog tables, the 2022 containment counts, and the overlap census above are the pre-registered conditioner reads. All nulls are printed. The earliness claim is graded on the +ATR-veto form; if the veto removed the earliness, the 'pre-trough' claim is stated as retracted in the earliness table (strictly-earlier? = NO).

## Limitations

- Closes-only MAE/troughs (house shadow-book form); intraday lows are deeper. Comparable across cells/variants, not absolute.
- Yahoo close is total-return adjusted; the overnight/intraday RATIO split is level-invariant so the adjustment nets out (open is the raw session open on the same adjusted scale — the ratio is unaffected).
- Survivor tape (data/baskets/ohlcv holds today's listings); per-name own-baseline netting removes level bias, not composition bias.
- The primary cell (K=5, q=simple>0) is deliberately loose (median 65 OOS fires/name) — a mild-pullback-with-intraday-resilience condition is common; the decomposition-vs-aggregate falsifier is the test of whether that density carries information beyond the net-return turn.
- ±31td proximity window is the §7 pin; long bear legs make 'the low' window-relative. The net-return analog shares this window (fair test).
- Rung-bar legs take the MEDIAN daily leg within each rung bar (robust to a single outlier day); the split stays a daily-microstructure object with the persistence window at the structure rung.
- NVDA is off the W1 panel (W1 eligibility); the containment diagnostic runs it as a raw-OHLCV exhibit, flagged.
