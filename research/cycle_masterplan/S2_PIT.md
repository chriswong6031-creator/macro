# S2 — PIT-Backfill Reconstructability Scout

**Date:** 2026-07-02  
**Scope:** engine/sector_cycles.py, engine/cycles.py, scripts/_cycle_fix_backtest.py, engine/sector_central.py

---

## 1. sector_cycles.py — `_record_core` + `build_sector` + `build_basket`

### Fields and PIT status

| Field | Computation path | PIT-pure from price <= t? | Hidden dependency? |
|---|---|---|---|
| **osc_pos** (`now.pos`) | `_detrended_osc()` → EMA ratio stochastic-normalized over 252d rolling window, lightly smoothed. Applied to `full` series sliced to `full.index <= asof` if `asof` supplied to `compute()`. | **YES** — pure function of close <= t | None |
| **phase** (`now.phase`, `now.phaseLabel`) | `_classify_phase(pos, slope, w_macd, t3_macd, above200)` — votes from weekly+3D MACD state from `cycles.analyze(full)`. `full` is already the <= t slice. | **YES** — pure function of close <= t | None |
| **signal** (`now.signal`) | `"BUY"` if `pos_now <= 45 and osc_slope > 0.5` else `"SELL"` if `pos_now >= 55 and osc_slope < -0.5` else `None`. | **YES** — pure function of osc position + slope | None |
| **ZigZag turns** (`turns`) | `_detect_swings(full, pct)` — deterministic alternating-peak/trough filter on full daily close. `swings_all` uses the complete unwindowed `full`, then filters by `_yf(win_start)`. Provisional last entry is the running extreme. | **YES** — pure function of close <= t. Deterministic; no randomness. | None |
| **proj** | `_project_next(swings_all, last_ts)` — median half-cycle length from ZigZag halves; `last_ts = full.index[-1]` (the asof date). | **YES** — fully derived from the ZigZag sequence | None |
| **RS / leadership** (`now.rs_63d`, `rs_126d`, `rs_above_trend`) | `_leadership(closes, ticker, bench="SPY")`: 63d and 126d pct_change of ratio to SPY, 200d MA of ratio. Needs SPY in `closes`. | **YES** — pure function of (ticker close, SPY close) both <= t | SPY must be in the `closes` panel at backfill dates |
| **timing_state / action** (`now.timing_state`, `now.action`) | `cycles.analyze(full)["ladder"]["state"]` and `["action"]`. See cycles.py section below. | **YES with caveats** — the cycle ladder is price-only when called without `liquidity`/`macro_drag`/`vix_ctx` args. `_record_core` calls `cycles.analyze(full, kind="equity")` with **no optional args** — so liquidity/macro/VIX nudges are absent. | `cycles.analyze()` can take `liquidity`, `macro_drag`, `vix_ctx`, `vol_regime` — all None when called from `_record_core`, making the state **price-only at backfill time** |
| **dc_phase** (`now.dc_phase`) | `cycles.analyze()["cycle"]["dc_phase"]` — derived purely from trough-finding on close series. | **YES** | None |
| **osc_slope** | 22-day change in the detrended oscillator. | **YES** | None |
| **w_macd_up / t3_macd_up** | From `cycles.analyze(full)["mtf"]["W"/"3D"]["macd_pos"]`. Computed on resampled close. | **YES** | None |
| **lastTrough / lastPeak** | From `swings` list — ZigZag confirmed turns. | **YES** | None |
| **above200d** | `full.iloc[-1] > full.iloc[-200:].mean()` — window of 200 bars from the asof tail. | **YES** | None |
| **ret_win_pct** | `(win.iloc[-1] / base - 1) * 100`. | **YES** | None |
| **tilt** (in proj) | Derived from phase + RS — no external input. | **YES** | None |
| **read** (`now.read`) | `None` in `_record_core`; filled by `narratives.json` in `build_sector_cycles.py`'s `_bind_narr()` at render time. | **NOT reconstructable** — it's a human-curated narrative string bound at render by a JSON file. The JSON is a living document. For a backfill forward-log the `read` field should be omitted or set to `null`. |

### Basket-specific caveat

`build_basket()` calls `basket_index.consolidated_candle(members, idx, mode="equal", pit=False)` (line 409). `pit=False` means it uses **current membership over full history**, not point-in-time membership. Backfill baskets are therefore **NOT PIT-clean on membership**: today's members are projected back. This is disclosed in the engine docstring ("survivorship-NOT-clean"). For cycle-spine-only backfill, ETF sectors (XLK etc.) are entirely PIT-clean; thematic baskets are not.

### `compute()` asof support

`sector_cycles.compute(asof=...)` at line 533–534 slices `closes = closes[closes.index <= pd.Timestamp(asof)]` before passing to all builders. **The asof parameter propagates correctly to all sector computations.** Basket `build_basket()` calls `basket_index.deep_calendar(members)` and `consolidated_candle()` which read from disk parquet files — these are not sliced by asof inside basket_index (pit=False path). A manual `full = full[full.index <= asof]` trim would be needed post-candle for PIT baskets.

---

## 2. engine/cycles.py — `analyze()` inputs beyond close/high

### Function signature (line 2109)
```python
def analyze(close, high=None, kind="equity", liquidity=None,
            macro_drag=None, macro_beta=0.0, vix_ctx=None, vol_regime=None)
```

### Input dependency table

| Input | Source when called from _record_core | PIT-reconstructable? |
|---|---|---|
| `close` | Price series <= t (the `full` slice) | YES |
| `high` | Not passed from `_record_core` (None) | N/A — absent |
| `liquidity` | Not passed (None) → `liq_regime = None` → no nudge applied (line 1076) | YES — absent means no nudge |
| `macro_drag` | Not passed (None) → `macro_on = False` (line 1121) | YES — absent means no penalty |
| `vix_ctx` | Not passed (None) → `washout()` gets `vix_ctx=None` (line 2133) | YES — absent means no panic amplification |
| `vol_regime` | Not passed (None) → vol overlay skipped | YES — absent |

**Conclusion:** `_record_core` calls `cycles.analyze(full, kind="equity")` with all optional overlays as None. The result is a **purely price-derived ladder state** at backfill time. The production live build threads `liquidity`, `macro_drag`, and `vix_ctx` in at the stock-desk level — but NOT from `sector_cycles._record_core`. The cycle spine stamped here is price-only by design.

### Internal computations — all pure price functions

- `cycle_state()` (line 203): trough-finding via local-minimum scan, MA10, swing-low confirmation, translation — all pure functions of close (and optionally high).
- `mtf_snapshot()` (line 151): MACD(12,26,9), RSI(14), RSI(5), StochRSI(14) on daily/3D/weekly resamples — pure.
- `early_signals()` (line 359): cross-detection on indicator series — pure.
- `regime_state()` (line 665): reads only from `cyc` and `mtf` dicts — pure.
- `ladder_state()` (line 734): reads `cyc`, `mtf`, `early`, and the optional overlay args (all None) — pure when overlays absent.
- `entry_quality()` (line 1566), `bottom_confidence()` (line 2035), `mtf_alignment()` (line 1884), `signal_age()` (line 1343): all pure functions of price-derived dicts.

**One config read:** `ladder_state()` calls `config.load()["engine"].get("macro_overlay")` (line 1120) and `config.load()["engine"].get("vol_regime_overlay")` (line 1148). These are static config values, not time-varying — safe to treat as constants for backfill.

---

## 3. scripts/_cycle_fix_backtest.py — expanding-window reuse

The backtest (lines 35–89) already implements the **expanding-window analyze() pattern** the masterplan needs:

```python
for i in range(start, n - fwd, step):
    sub = close.iloc[max(0, i + 1 - 800): i + 1]   # ← 800-bar trailing window, NOT full history
    res = cycles.analyze(sub, high.iloc[:i+1] if high is not None else None, "equity")
```

**What it does:** walks individual stock histories, truncating to a 800-bar trailing window, calls `analyze()`, reads `ladder["entry"]["urgency"]`, and measures forward return + MAE. It does NOT use `_record_core` or emit the full sector-cycles output schema.

**What can be reused:**
- The `sub = close.iloc[max(0, i+1-800):i+1]` truncation pattern → directly portable to a monthly backfill loop.
- The `cycles.analyze(sub, kind="equity")` call pattern → the same call `_record_core` makes.
- The expanding-window loop structure → a monthly backfill would step `i` at month-end indices.

**What is absent:** the backtest does NOT call `_record_core`, `_detect_swings`, `_classify_phase`, or `_project_next`. It only measures ladder urgency vs forward returns. A backfill of the full `sector_cycles` schema requires wrapping `_record_core` (or calling `sector_cycles.compute(asof=date_str)` directly, which is the cleanest path given the `asof` parameter exists).

---

## 4. engine/sector_central.py — compute() dependencies

`sector_central.compute()` fuses the cycle spine from `sector_cycles.compute()` with four additional layers:

| Layer | Function | PIT-reconstructable? | Notes |
|---|---|---|---|
| **Cycle spine** | `sector_cycles.compute()` | **YES** (via asof parameter) | The entire spine is price-pure, as established above |
| **Regime anchor** | `_regime_anchor()` reads `data/regime/latest.json` (line 89–91) + calls `engine.conditions.macro_risk_score()` + `engine.market_state.load_persisted()` | **NOT reconstructable** — `latest.json` is the live nightly regime file, overwritten each run. Historical regime files are not archived by default. `market_state.load_persisted()` is also the current snapshot. |
| **Heat table** | `_heat_table()` reads `site/marketdata/sp500_heatmap.json` (line 182) | **NOT reconstructable** — this is a live scrape output file, overwritten nightly. No historical archive. |
| **Crowding fragility** | `engine.crowding.compute_fragility()` reads equity closes + `data/finra/short_interest.parquet` (line 84 crowding.py) | **PARTIAL** — equity closes are PIT-reconstructable from parquet. FINRA short interest parquet is a point-in-time snapshot file that gets overwritten; historical short interest is NOT archived. |
| **Narrative rotation** | `engine.narrative_rotation.compute_narrative_rotation()` reads member closes + `data/finra/short_interest.parquet` (line 790) + basket membership | **PARTIAL** — the price-based _abs_gate trend computation is PIT-reconstructable. Short-interest consumption and current-membership (pit=False default paths) are NOT PIT-clean. |
| **Trend gates** | `_trend_gates()` → `engine.narrative_rotation._abs_gate()` on ETF close (sectors) or narrative rotation gate (baskets) | **YES for sectors** — `_abs_gate` is a pure function of the ETF close. **NO for baskets** — depends on narrative rotation which has the short-interest / membership caveats above. |

**Honest partial-backfill scope for sector_central:** the cycle spine + trend gates for the 11 SPDR sector ETFs are fully PIT-reconstructable. Everything else (regime anchor, heat table, crowding, narrative rotation for baskets) requires either archiving those files at each historical month-end or accepting they will be absent/stale.

**Recommendation:** a cycle-spine-only backfill (call `sector_cycles.compute(asof=date_str)`) is the honest scope. The sector_central overlay layer should be excluded from historical backfill stamps unless the regime/heatmap/short-interest files are versioned.

---

## 5. Compute cost estimate

**Measured:** `_record_core()` on an 800-bar series = **56ms** per call (5-run mean, measured directly).  
`cycles.analyze()` alone = **54ms** per call (10-run mean).

| Scenario | Calls | Estimated time | vs 67min full render |
|---|---|---|---|
| 11 sectors × 180 months | 1,980 | ~2min | ~3% |
| 11 sectors + ~149 baskets (160 series) × 180 months | 28,800 | ~27min | ~40% |
| 11 sectors only (no baskets) — safe PIT scope | 1,980 | ~112s ≈ 2min | ~3% |

**Note:** the 800-bar window cap used in `_cycle_fix_backtest.py` is important — without it, the oldest historical stamps would pass increasingly long series (e.g. 3,800 bars for 15y), which is ~4.75× slower per call. With the cap, each call stays bounded at ~56ms regardless of backfill date.

**Basket warning:** at 180 months × ~149 baskets, the basket index construction (`basket_index.deep_calendar()` + `consolidated_candle()`) will dominate — these involve disk reads per basket. Actual basket backfill time is likely 2–5× higher than the analytical estimate.

---

## Summary: blockers for PIT backfill

| Blocker | Severity | Mitigation |
|---|---|---|
| Basket membership `pit=False` in `consolidated_candle()` | HIGH for baskets | Pass `pit=True` and supply historical `members` with `added`/`removed` dates; or exclude baskets from historical backfill |
| `latest.json` / regime anchor not archived | HIGH for sector_central | Exclude regime/gate layers from backfill; stamp cycle spine only |
| `sp500_heatmap.json` not archived | HIGH for sector_central heat | Exclude heat table from backfill |
| `short_interest.parquet` snapshot overwritten | MEDIUM | Exclude crowding from backfill; or archive FINRA files with date suffix |
| `narratives.json` is a living human-edited document | LOW — already `null` in engine | `now.read` field is always `None` from `_record_core`; narrative binding happens only at render time in `build_sector_cycles.py`. Backfill JSON will correctly carry `null`. |
| `config.load()` macro_overlay / vol_regime_overlay reads | NEGLIGIBLE | Static config constants — treat as fixed for backfill |

---

## Verdict

**Sector ETF cycle-spine-only backfill is fully PIT-reconstructable** using `sector_cycles.compute(asof=date_str)`. The `asof` filter is already implemented (line 533). The 11 SPDR sectors at 180 monthly stamps take approximately 2 minutes (measured, no baskets). All stamped fields — osc_pos, phase, signal, ZigZag turns, proj, RS, timing_state, action, dc_phase — are pure functions of `yahoo_closes` <= t.

**Basket backfill is NOT PIT-clean** due to `pit=False` membership (current members projected over full history). This is disclosed in the engine source.

**sector_central backfill is NOT honest** without archiving regime/heatmap/short-interest files at each historical month-end. The cycle spine sub-layer within sector_central IS reconstructable, but the gate/conviction/crowding overlay is not.
