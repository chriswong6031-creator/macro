# Standout-grid buy gate — wiring the validated confluence into every country board

> Companion to `CHARTER.md` (read it first) and `CONFLUENCE_TUNING.md`. Honors §2 (risk
> tool, not return engine; detect don't predict), §4 (faithful RSI-MACD + stoch-of-RSI;
> NO standard MACD) and §7 (the chart-marker contract). This is an INTEGRATION, not a new
> signal: it promotes the already-validated buy-filter to the primary grid gate.

## What changed

Every country's **"Standout Top Stocks"** grid (US, China, HK, Canada, Intl) now gates buy
inclusion on the **validated MACD-RSI × StochRSI confluence** (`engine/signal_quality.py`,
the keeper from CHARTER §5 — drawdown −23.7%→−15.5% on 110 held-out US names), via the shared
`engine/signal_gate.py`. The grid shows **only** names the validated signal endorses, and
ranks **confirmed TAKEs above anticipations**.

Before, the boards used unvalidated screens:
- **US** gated on the `engine/cycles.py` ladder — a **standard MACD(12,26,9) + StochRSI**
  construction (CHARTER §4 explicitly forbids standard MACD). That ladder is now display
  context only; the buy gate is the validated confluence.
- **China / Canada / Intl** gated on an `alpha_z ≥ 0.5` floor alone (no entry signal).
- **HK** gated on the conviction composite alone.

## The gate (`engine/signal_gate.py`)

`verdict(analyze_result)` maps a `signal_quality.analyze()` result to a tier:

| tier | sub | meaning | grid |
|---|---|---|---|
| **take** | — | last §7 marker is a buy/rebuy with quality `take`, no sell/cut since (held, buy-filter-endorsed) | included, **ranked first** |
| **anticipation** | `pending` | confluence buy fired on the last 1–2 bars; forward reclaim-and-hold not in yet (§7 `pending`) | included, ranked below takes |
| **anticipation** | `early` | the validated 2D-MACD pre-cross advance-warning (`early_now`) | included, ranked last among eligible |
| *(none)* | — | blocked buy, flat (last marker sell/cut), no signal, or thin history (`analyze()→None`) | **excluded** |

Ranking key = `(tier_rank, −market_score)` so takes sit above anticipations and the existing
per-market score (alpha / conviction / setup) orders names *within* each tier. The alpha
`buy_min` floor is **dropped** where the gate is applied — the confluence gate replaces it.

### Why anticipation is a surfacing exception, not a buy

CONFLUENCE_TUNING.md proved acting on the early leg is *worse* entry quality (deeper drawdown
on ~70% of names). So anticipation only makes a name **eligible to appear**; it is never
treated as a stronger buy than a take, never fed to conviction, never auto-traded (CHARTER
§2/§7). `pending` and `early` carry the §7 contract's exact semantics.

### Anticipation form (a) vs (b) — decided by diagnostic, not assertion

`research/signal_engine/tuning_anticipation.py` measured each candidate form as a SURFACER of
imminent confirmed `base3d` buys on the 110 held-out US names (K=10 bars):

| form | recall of TAKEs | precision | false-alarm | lead | markers/name |
|---|---|---|---|---|---|
| **(a) `early` (from-OS)** | **38.5%** | **32.0%** | 68% | **4.6d** | 10.7 |
| (b) `early_hi` (from-above-OS + 2D cross) | 21.9% | 20.5% | 79.5% | 2.2d | 5.2 |
| union | 55.6% | 28.9% | 71% | 4.1d | 14.5 |

(a) dominates (b) on every axis; (b) alone is mostly false alarms; the union lifts recall but
at lower precision and ~doubled chattiness. So the gate uses **(a) = the in-engine `early_now`**
and does **not** adopt (b) — keeping the §7 contract spec unchanged (CHARTER §3, tiny spec).
Even (a) has a 68% false-alarm rate, which is exactly why anticipations rank strictly below
takes. `m2d_s3d_early_hi` is kept in `tuning_harness.py` as a tested-and-not-adopted variant.

## Coverage (close-only is fine)

`signal_quality` is **close-only by construction** (it stochs the RSI of *close*; it never
needs high/low), so the full confluence runs on every market's close-only store. The only
real constraint is history length (~270 daily closes ≈ 90 3D bars); thinner names degrade
gracefully to "insufficient history" (excluded, never a crash).

| market | grid price store | OHLC? | names with enough history | gate coverage |
|---|---|---|---|---|
| US | `data/stocks/*.parquet` + breadth caches | deep OHLCV (114) / close-only (rest) | ~full | **full** |
| China | `data/china_search/closes.parquet` | close-only, 5y | ~480–640 of ~800 | **full** (close) |
| HK | `data/hk_breadth/_closes_cache.parquet` | close-only, ~3y | all 73 | **full** (close) |
| Canada | `data/canada_search/closes.parquet` | close-only, ~5y | all 219 | **full** (close) |
| Intl | `data/intl_search/closes.parquet` | close-only, 5y | 992 / 1000 | **full** (close) |

If gating would empty a board (degenerate — e.g. analyze() failed for every name) the build
falls back to the prior un-gated board and logs `gate_applied=False`, so a page never goes
blank. Per-build coverage (`scored / eligible / take / anticipation`) is logged.

### Verified first-build coverage (2026-06-27)

Every market built clean (`gate_applied=True`), takes ranked above anticipations, no crashes:

| market | scored | eligible | take | anticipation | buy shown |
|---|---|---|---|---|---|
| US | 1102 | 254 | 193 | 61 | 120 (all takes) |
| China | 1366 | 257 | 149 | 108 | 110 (all takes) |
| Canada | 219 | 45 | 26 | 19 | 45 (26 take + 19 antic) |
| Intl | 992 | 141 | 53 | 88 | 60 (53 take + 7 antic) |
| HK | 73 | 12 | 4 | 8 | 12 (4 take + 8 antic) |

~14–23% of scored names are eligible (a selective risk gate, as intended). Where confirmed
takes exceed the board cap (US, China) the grid is all takes; where takes are thin (Canada,
Intl, HK) the anticipation exception fills the slots *below* the takes — exactly its purpose.
All `site/signals/*.json` (US + non-US, 3864 files / 117k markers) pass `scripts/validate_signals.py`.

## Chart consistency (§7)

Each country build writes the §7 `site/signals/<TICKER>.json` for the names it gates, from the
SAME `analyze()` result. `site/chart.js` defaults `signalsDir='signals'`, so every market's
chart now renders the same buy/sell/cut/rebuy markers (and the dim `early` pre-dots) that the
grid gated on — guaranteed consistent, no schema change, validated by `scripts/validate_signals.py`.
The brain leaf (`mtf_signals_latest.json`, US-only, consumed by `master_brain`) is unchanged.

> US note: for US-deep names `site/signals/<T>.json` is written by BOTH `build_signal_quality.py`
> (the brain-leaf builder, runs first in `daily.yml`) and `build_stock_library.py` (the grid build,
> runs later via `build_site`). Both call the same `analyze()` on the same US store, so the files are
> identical; the grid build writes within its own run so the grid and chart always agree. Intentional,
> harmless overlap — the grid build additionally covers the wider S&P-1500 names the leaf builder skips.
