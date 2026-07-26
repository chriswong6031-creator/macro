# PSS-F3 — Idiosyncratic residual reset (beta-stripped own-flush exhaustion)

Reset-CONFIRMER / idiosyncratic-capitulation construction (copy law R-W1T-3 — no 'bottom caller' / 'calls bottoms'). Pre-registered ruler + construction: script header, committed pre-run (prereg commit precedes results commit in git history; the sector-mapping source re-pin is disclosed there, pre-outcome). Entry-timing ruler (§7), NOT hold returns (wrong-ruler check performed; motive #1458). Machinery (metric_arrays / null_stats / bars_for / tool_dates / _name_uplift per-name-first / c32_gate) COPIED from the W1 + F1 + F2 scripts. Inference: month-cluster bootstrap, NB=1000, seed 20260730. The commissioning session rules the verdict; this reports what was found.

## Coverage census (eligible / excluded, with reasons)

- Universe: 1300 W1-panel names. Sector-ETF mapping = data/breadth/ticker_sectors.parquet (ticker→GICS→SPDR sector ETF); ETF price = data/yahoo/{ETF} (TR-adj); name price = data/baskets/ohlcv (TR-adj, same convention).
- **F3-eligible: 381** (sector-ETF resolvable AND codex rung measurable AND ≥3 FIT + ≥3 TEST primary-cell (z=-2.0, betawin=120) fires with resolvable mae63/prox).
- **Excluded: 919** — no_sector_map: 501; few_fires: 418.
  - `no_sector_map` = not in the GICS ticker→sector table (NOT defaulted to SPY — that would change the mechanism to idiosyncratic-vs-market; a market-residual SECONDARY is noted separately). `few_fires` INCLUDES the high-R²/index-like names that stay STRUCTURALLY SILENT — that silence is the FEATURE (systemic names have no residual to lead the price), reported as correctly-silent, not as a miss.
- Eligible-name ETF distribution: XLF:97, XLI:53, XLY:48, XLK:41, XLV:35, XLB:29, XLRE:24, XLE:22, XLP:18, XLU:14.
- Per-name residual ACF-decay half-life (FIT): median 79td, deciles [35.0, 79.0, 250.0]. Residual rho@3D median -0.024, @1W -0.029, @2W -0.023.
- Per-name sector-beta drift |β_FIT − β_TEST|: median 0.17 (β_FIT median 0.97, β_TEST median 1.02).
- TEST F3 signals (primary cell, pooled): 6,708; raw-return-analog fires (TEST, pooled): 15,993.

Panel all-days OOS base rates (median across eligible names): MAE63 -7.54%, within-5%-of-low 17.2%, called-low 8.4%.

## Grid (multiplicity budget: 4 cells) — TEST U_MAE / U_W5, name-level medians (no gate)

No per-name best-of-grid selection (DNR §2). Primary cell = (z=-2.0, betawin=120). Point estimates are panel medians of per-name uplifts; the CI/inference rows are the pooled month-cluster bootstrap on the primary cell below.

| cell | n names | U_MAE | U_W5 | median OOS fires/name |
|---|---|---|---|---|
| z=-1.5, betawin=60 | 381 | +0.19pp | +10.51pp | 30 |
| z=-1.5, betawin=120 | 381 | +0.24pp | +10.92pp | 25 |
| z=-2.0, betawin=60 | 380 | +0.15pp | +12.09pp | 23 |
| z=-2.0, betawin=120 ★ | 381 | +0.39pp | +12.91pp | 15 |

### Primary cell across eras (full TEST / 2021+ sub-window), no gate

| era | U_MAE | U_W5 |
|---|---|---|
| full TEST ≥2020-07 | +0.39pp | +12.91pp |
| 2021+ ≥2021-01 | +0.56pp | +11.75pp |

## Gate variants on the primary cell (pre-stated column pair: RAW / +C32), name-level medians

RAW = no terminality gate. +C32 = decline-deceleration terminality gate (roc20 stopped making new lows while close ≤ 60d low + rolling-low slope flattening; copied verbatim from pss_f1_downvol).

| variant | U_MAE OOS | U_W5 OOS | U_MAE 2021+ | U_W5 2021+ | n names OOS |
|---|---|---|---|---|---|
| RAW (no gate) | +0.39pp | +12.91pp | +0.56pp | +11.75pp | 381 |
| +C32 | +2.19pp | +35.07pp | +2.28pp | +33.18pp | 190 |

## Inference — month-cluster bootstrap (primary cell), vs BOTH nulls

Per-name-first collapse then cross-name median (matches the F1/F2/W1-T machinery — the F1 E1 sign-flip bug is NOT repeated): within each month-cluster draw, U_MAE = name-median mae63 − name all-days median, U_W5 = name signal-day within-5%-of-low rate − name all-days rate, THEN the cross-name median. Two nulls: (a) all-DAYS base rate [inside the per-name uplift], (b) the RAW-RETURN ANALOG (identical construction on raw returns/drawdown — the residualization-adds-nothing mirror placebo). The F3 − raw-analog diff is PAIRED on the same resampled month-clusters.

Self-check (F1 E1 guard): direct per-name-median U_W5 = F3 +12.91pp / raw-analog +0.48pp; the bootstrap point estimates below must match these within bootstrap noise.

| quantity | full TEST | 2021+ |
|---|---|---|
| F3 U_MAE (vs all-days null), no gate | [-0.76, +1.37] includes 0 | [-0.59, +1.49] includes 0 |
| F3 U_W5 (vs all-days null), no gate | [+6.68, +15.60] excludes 0 ↑ | [+6.06, +14.68] excludes 0 ↑ |
| F3 U_MAE, +C32 | [+0.17, +3.64] excludes 0 ↑ | [+0.08, +3.69] excludes 0 ↑ |
| F3 U_W5, +C32 | [-6.64, +65.86] includes 0 | [-7.58, +62.92] includes 0 |
| raw-return-analog U_MAE (residualization-adds-nothing null) | [+0.15, +2.43] excludes 0 ↑ | [+0.25, +2.52] excludes 0 ↑ |
| raw-return-analog U_W5 (residualization-adds-nothing null) | [-2.69, +2.22] includes 0 | [-2.95, +2.51] includes 0 |
| F3 − raw-analog  U_MAE (FALSIFIER, paired) | [-2.00, +0.02] includes 0 | [-2.01, -0.02] excludes 0 ↓ |
| F3 − raw-analog  U_W5 (FALSIFIER, paired) | [+7.28, +15.55] excludes 0 ↑ | [+6.19, +14.29] excludes 0 ↑ |

The FALSIFIER rows are the pre-stated kill: if F3 − raw-return-analog does NOT exclude 0 (positive) on U_MAE/U_W5, beta-stripping the residual carries no incremental information over the raw-price analog, and F3 dies as a standalone construction. Printed regardless of outcome.

## Overlap / disjointness census — F3 vs raw-return analog (primary cell, TEST)

The whole F3 claim is that the residual turns up WHILE the raw price is still falling — so F3 fires are NOT a subset of raw-turn days; the placebo is a matched-construction counterfactual, not a disjoint complement.

- BOTH F3 & raw-analog: 0 · F3-only (raw price still ≤ recent high at fire): 6,708 (100% of F3 fires) · raw-analog-only: 15,993.
- F3-only share reflects how often the residual leads before the raw price turns (the pre-registered mechanism); the raw analog is a genuine matched counterfactual, not a subset.

## Mechanism test — F3 fire concentration across the name's own R² terciles (charter falsifier prong 4)

PRE-STATED: residual-lead should CONCENTRATE in the LOWER (idiosyncratic) R² tercile. If fires cluster in the HIGH-R² (systemic) tercile, the mechanism is dead. R² = trailing name–sector regression R² (PIT) at each fire; terciles cut per name on that name's own valid-day R² distribution, then summed across names.

| R² tercile (per name) | F3 fires | share |
|---|---|---|
| LOW R² (idiosyncratic) | 1,609 | 24% |
| MID R² | 2,272 | 34% |
| HIGH R² (systemic) | 2,827 | 42% |

Names with a resolvable tercile split: 381. The pre-stated direction is LOW-tercile concentration; the observed split is above (reported regardless of outcome).

## Earliness — F3 vs incumbent (Stoch-RSI<20 @ derived rung) AND vs raw-return analog (SAME names)

td_to_trough: negative = trough BEFORE the fire (late confirmer); positive = fire BEFORE the trough (pre-trough / early). Per-name medians over TEST, then panel median of those. Charter hard requirement: F3 median td_to_trough must be STRICTLY earlier than BOTH the incumbent AND the raw-analog, else the 'pre-trough' claim is RETRACTED to at/post.

| comparison | n names | F3 median tdt | other median tdt | F3 − other (per-name median) | strictly earlier? |
|---|---|---|---|---|---|
| vs incumbent | 381 | +5.0td | -1.5td | +4.5td | YES |
| vs raw-analog | 297 | +7.0td | -2.0td | +8.0td | YES |

### MAE-to-trough vs incumbent (charter falsifier prong 3: F3 must be SHALLOWER)

- F3 median mae63 (TEST, 381 names): -7.26% · incumbent median mae63: -7.47% · F3 − incumbent (per-name median): +0.32pp (positive = F3 SHALLOWER adverse excursion = better entry; the pre-stated requirement).
- vs raw-analog: F3 − raw-analog median mae63 (per-name median, 297 names): -1.45pp.

## 2022-class containment (primary cell fire counts): RAW / +C32

Charter STRUCTURAL claim: F3 CANNOT fire the 2022 pattern BY CONSTRUCTION (2022 mega-cap troughs were SYSTEMIC — high R², residual not leading — so the disagreement gate stays shut). PREDICTION: H1-2022 fires ≈ 0 on the systemic names (KO, PG, MSFT in macro flushes). META/NVDA/PG are OFF-PANEL (W1 eligibility) — run from raw OHLCV, flagged. `H1 R²` = median trailing name–sector R² at the H1-2022 fires (high → systemic regime, the mechanism-off condition).

| name | class | H1-2022 (raw / +C32) | ±21td 2022-low (raw / +C32) | H1 R² | name R² (TEST med) |
|---|---|---|---|---|---|
| TSLA (XLY) | idiosyncratic | 7 / 0 | 2 / 0 | 0.63 | 0.57 |
| NVDA (off-panel) (XLK) | idiosyncratic | 8 / 2 | 2 / 0 | 0.83 | 0.65 |
| META (off-panel) (XLC) | idiosyncratic | 0 / 0 | 0 / 0 | — | 0.69 |
| JNJ (XLV) | idiosyncratic | 0 / 0 | 1 / 0 | — | 0.36 |
| UNH (XLV) | idiosyncratic | 0 / 0 | 0 / 0 | — | 0.34 |
| PG (off-panel) (XLP) | idiosyncratic | 7 / 0 | 0 / 0 | 0.78 | 0.63 |
| KO (XLP) | systemic (expected silent) | 0 / 0 | 0 / 0 | — | 0.60 |
| MSFT (XLK) | systemic (expected silent) | 0 / 0 | 0 / 0 | — | 0.68 |

If F3 fires heavily into H1-2022 on the systemic names, the by-construction containment claim is FALSE (reported regardless).

## Product split (descriptive; calls-low vs confirms-reset)

F3 primary-cell TEST fires (n=6,708): near-low (−2..+5td) 14% · confirmed-reset (<−2td) 37% · early (>+5td) 48% · median td_to_trough +4td.

## What was found (no verdict — the commissioning session rules)

- F3 (no gate) U_MAE vs the all-days null on full TEST: [-0.76, +1.37] (includes 0); U_W5 [+6.68, +15.60] (excludes 0 ↑).
- The pre-stated FALSIFIER (F3 − raw-return analog, residualization-adds-nothing): U_MAE [-2.00, +0.02] (includes 0), U_W5 [+7.28, +15.55] (excludes 0 ↑) on full TEST; 2021+ U_MAE [-2.01, -0.02] (excludes 0 ↓), U_W5 [+6.19, +14.29] (excludes 0 ↑).
- The mechanism R²-tercile concentration table, the +C32 gate column, the earliness-vs-incumbent AND earliness-vs-raw-analog tables, the MAE-to-trough-vs-incumbent read, and the 2022 containment counts above are the pre-registered conditioner / falsifier reads. All nulls are printed. The earliness claim is graded honestly; if F3 is not strictly earlier than BOTH the incumbent and the raw-analog, the 'pre-trough' claim is retracted (strictly-earlier? = NO in the earliness table).

## Limitations

- Closes-only MAE/troughs (house shadow-book form); intraday lows are deeper. Comparable across cells/variants, not absolute.
- Name (baskets/ohlcv) and sector ETF (yahoo) are BOTH total-return adjusted, so the beta regression is on a consistent scale (log returns are level-invariant); the two series are inner-joined on common trading dates before differencing.
- XLRE (from 2015-10) and XLC (from 2018-06) have short FIT-era history; names mapped there have fewer FIT-era residual bars — a coverage matter, reflected in the census, not silently defaulted.
- Sector mapping is the CURRENT GICS membership (ticker_sectors); a name that changed GICS sector historically is mapped by its current sector (the top-20 sector_holdings snapshot agrees on shared names). A name with no GICS map is excluded, never defaulted to SPY (that is the market-residual SECONDARY, a different mechanism).
- Survivor tape (data/baskets/ohlcv holds today's listings); per-name own-baseline netting removes level bias, not composition bias.
- ±31td proximity window is the §7 pin; long bear legs make 'the low' window-relative. The raw-return analog shares this window (fair test).
- The residual is beta-stripped vs the sector ETF; residual mean-reversion (residual rho ladder) is the measurement axis, not an event fit.
- META/NVDA/PG are off the W1 panel (W1 eligibility); the containment diagnostic runs them as raw-OHLCV exhibits, flagged.
