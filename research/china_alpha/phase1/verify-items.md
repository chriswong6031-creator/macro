# China A-share Pipeline Verify Items — Phase 1 Audit
**Generated:** 2026-07-03  
**Worktree:** lucid-knuth-523979  
**Pages audited:** china_stocks.html, sector_central_china.html, baskets_china.html  
**Auditor note:** All claims are cited to file:line or to a command run with its output. Where live data was read from the worktree's own `data/` directory, this is noted; the worktree's `data/china_search/closes.parquet` exists and is current to 2026-07-02.

---

## V1: rev_z COVERAGE — Does the validated edge reach the full board?

### Claim to verify
The validated A-share edge is within-sector reversal. `reversal_watch` is called with `top_n=16`. The question is whether the conviction SELECTION AXIS (CN branch, `0.55*rev_z`) reads a full-universe `rev_z` or only the 16 watch names.

### Trace: how rev_z enters conviction_profile

**Step 1 — reversal_watch output (`engine/china_reversal.py`)**

`reversal_watch()` returns two coverage modes (lines 103–111):
- `watch`: the top-N=16 display list (sorted by `rev_z` descending)
- `rev_z_all`: a dict `{ticker: rev_z}` covering the ENTIRE screened universe (every name with a valid `rev_z` after ST/mktcap/thin-sector screens)

The comment at `engine/china_reversal.py:104–108` is explicit:
> `watch` is the top-N DISPLAY list; `rev_z_all` is the FULL screened map so the conviction SELECTION axis (CN = 0.55·rev_z) is populated for every name — not just the 16 shown. Before this, ~800 names fell back to residual momentum (alpha), the signal the engine itself labels "not a validated A-share edge", silently breaking the reversal-led CN rank.

**Step 2 — build_china_library.py uses rev_z_all (`scripts/build_china_library.py:793–802`)**

```python
rev_z_by: dict[str, float] = {}
try:
    _rev = compute_china_reversal() or {}
    # rev_z_all covers the WHOLE screened universe (the fix)
    rev_z_by = dict(_rev.get("rev_z_all") or {})
    for _r in _rev.get("watch", []):            # back-compat: ensure the display names are in too
        if _r.get("ticker") and _r.get("rev_z") is not None:
            rev_z_by.setdefault(_r["ticker"], _r["rev_z"])
    log.info("china reversal-z: populated for %d names (was top-16 only)", len(rev_z_by))
```

**Step 3 — rev_z is passed to normalize_rec per name (`scripts/build_china_library.py:966`)**

```python
norm = stock_score.normalize_rec(
    rec, "CN", rev_z=rev_z_by.get(ticker), basket=basket_tw.get(ticker))
```

**Step 4 — normalize_rec passes it through (`engine/stock_score.py:1398–1423`)**

`normalize_rec()` accepts `rev_z` as a keyword argument and places it at `rec["rev_z"]` (line 1423). This is then consumed by `_axis_selection` (CN branch, lines 344–358):
```python
if m == "CN":
    z = _f(rec.get("rev_z"))                  # validated A-share reversal
    a = _f(rec.get("alpha"))                  # residual momentum: light context
    rev = _f(rec.get("revision_z"))
    legs: list[tuple[float, float]] = []
    if z is not None:
        legs.append((z, 0.55)); present.append("rev_z")
    ...
```
The `rev_z` leg receives weight 0.55 (the dominant SELECTION weight in the CN branch). If `rev_z` is None, the CN selection axis falls back to alpha (weight 0.20) only — the non-validated leg.

### Live data measurement

**Command run (worktree data, `data/china_search/closes.parquet` as of 2026-07-02, 1506 tickers):**

```
reversal_watch result:
  Total screened universe n: 1478
  Watch list (top_n=16): 16 names
  rev_z_all coverage: 1478 names
  Screened: {'st': 1, 'illiquid': 0}
  As of: 2026-07-02
```

```
OLD coverage (top-16 watch list): 16 names
NEW coverage (rev_z_all): 1478 names
Improvement factor: 92x

Board tickers that would have had rev_z under OLD path: 2/110
Board tickers that would have FALLEN BACK under OLD path: 108/110
```

**Board coverage check (nbcard tickers in site/china_stocks.html vs rev_z_all):**
```
nbcard tickers: 110
Board tickers with rev_z: 110 / 110
Board tickers WITHOUT rev_z: 0
Missing: []
```

### V1 Verdict: FIXED — validated edge NOW reaches the full board

The fix is in place. The `rev_z_all` key (added at `engine/china_reversal.py:108`) populates rev_z for the entire 1,478-name screened universe. All 110 standout-board names carry a real `rev_z` value. Under the old top-16-only path, 108/110 board names (98%) would have fallen back to residual alpha — the non-validated leg — as the dominant selection signal.

The comment in the source code confirms this was a known fix: "Before this, ~800 names fell back to residual momentum (alpha), the signal the engine itself labels 'not a validated A-share edge', silently breaking the reversal-led CN rank."

**One residual concern:** `rev_z_all` is populated from the `china_search/closes.parquet` close plane (the wide search-universe panel), not the deeper `china_stocks/` per-ticker OHLC store. The leakage harness (`scripts/shadow_pit_china.py`) explicitly measures this as the "PLANE tax" — replaying washout-2W on the wrong plane flips ~5% of rows. The same plane mismatch applies to rev_z computation (rev_z is computed off `china_search/closes.parquet`), but since rev_z uses a 63-day window (not a 2-week resample), the plane-induced bucket-phase shift is smaller. This is not a coverage gap but a measurement-precision note.

---

## V2: LEAKAGE HARNESS coverage — Does it cover the live china_stocks feature path?

### Claim to verify
Commit db8fae90ef shipped a W1 leakage-tax harness. Does it cover the live `china_stocks` feature path (rev_z, washout-2W, cascade freshness)?

### What was shipped

**Primary harness: `scripts/shadow_pit_china.py`**

The script's own docstring (lines 1–27) states:
> W1 (engine/pit.py, scripts/shadow_pit_regime.py) covers the US FRED/ALFRED macro legs and ZERO of the china board path. This harness ports the truncated-replay discipline (template: tests/test_vector_pit.py) to the live board's own features.

Three measured taxes:
1. **PLANE tax** — feature replay on the correct vs wrong price plane (washout-2W flag flip rate, seed ~5%)
2. **BUCKET-COMPLETENESS tax** — washout-2W flag flips when the current 2W bucket is incomplete vs completed (seed ~8.3%/day)
3. **PRICE-VINTAGE tax** — close revision rate between git-committed panel vintages (seed 0.7% at >0.4% band)

Additionally `measure_revz_causality()` (lines 304–331) measures screened-set membership churn for `rev_z` specifically.

**Tests: `tests/test_shadow_pit_china.py`**

Four tests:
- `test_washout_2w_is_point_in_time_on_its_own_plane` — PIT guarantee for washout-2W
- `test_bucket_end_is_within_the_panel` — bucket_end < asof
- `test_completed_bucket_flag_differs_or_matches_but_is_defined` — completeness comparison computable
- `test_plane_tax_reproduces_ledger_on_correct_plane` — correct-plane replay reproduces live ledger >=0.9

**Existing regime-side harness: `scripts/shadow_pit_regime.py` / `engine/pit.py`**  
Covers the US FRED/ALFRED macro legs ONLY. Zero China board path coverage (confirmed by the docstring at `scripts/shadow_pit_china.py:6–7`).

**Output artifact: `calibration/leakage_tax_china.json`** (written on run; not present in the worktree as a pre-committed artifact).

### Feature path coverage analysis

| Feature path | Covered by harness | Notes |
|---|---|---|
| `rev_z` (3m within-sector return, screened) | YES — `measure_revz_causality()` measures screened-set churn | rev_z values are causally clean (both ends observed closes); the fragility is membership churn, not value leakage |
| `washout_2w` (2W StochRSI reclaim) | YES — plane tax + bucket-completeness tax explicitly measure this | The harness identifies two distinct PIT risks for this feature |
| Cascade freshness (T1-T4 FRESH_TICKS=2) | NO — the harness measures the plane and bucket-completeness of the washout flag; it does NOT replay the confluence_tiers cascade across time or measure how freshness grades evolve as ticks accumulate | Gap: cascade freshness at as-of is not explicitly measured |
| Price-vintage stability | YES — vintage tax measures close revision rate |

### V2 Verdict: PARTIAL COVERAGE — rev_z and washout-2W are measured; cascade freshness is not

The W1 harness exists and is non-trivial. It covers the two features with the highest PIT risk on the China board (washout-2W bucket repaint, plane mismatch). `rev_z` causality is confirmed clean (the fragility is membership churn, not value leakage per se).

**Gap: cascade freshness is not covered.** The confluence_tiers cascade (T1–T4, FRESH_TICKS=2) grants a fresh-fire label for up to 2 ticks after a cross; whether that "fresh" label as of any given asof is reproducible by truncated replay is not measured. Wiring it would require:
1. Reading the per-name confluence output at a historical asof (either from a committed board ledger or by re-running `signal_gate.gate()` on a truncated panel)
2. Comparing the T1/T2/T3/T4 grade and `is_fresh` flag between the live and the reproduced run
3. The `calibration/provisional_replay.json` artifact (referenced in the rendered HTML for T3 flip rates) provides partial coverage — it tracks 4-session vanish rates for fresh T3 fires — but it is a forward-grading product, not a point-in-time replay harness

The existing harness is sufficient to quantify the two largest taxes; the cascade-freshness gap is a known "next wave" item.

---

## V3: BASKET PERF PLANE — raw vs adjusted closes, exact store name

### Claim to verify
Where is the basket 20d rel perf computed for `engine/baskets_china.compute_china_baskets`, and does it run on raw or dividend-adjusted closes?

### Trace

**Step 1 — `engine/baskets_china.py:65–76`**

`compute_china_baskets()` calls:
```python
closes = _closes()
bench = store.read("china", mem.get("benchmark", BENCHMARK_DEFAULT))
return compute_region_baskets(closes, mem, bench,
                              lambda s: store.read("china", s), name_key="name_zh")
```

**Step 2 — `_closes()` at `engine/baskets_china.py:51–62`**

```python
def _closes() -> pd.DataFrame | None:
    """Wide [Date × ticker] adjusted closes for the china_search universe (~800 names, ~5y)."""
    p = config.data_dir() / "china_search" / "closes.parquet"
```

The docstring explicitly says "adjusted closes". This is the same `data/china_search/closes.parquet` wide panel.

**Step 3 — `engine/baskets_region.py:103`**

The per-member 20d return is computed at `compute_region_baskets()` line 103:
```python
r20 = float(tc.iloc[-1] / tc.iloc[-21] - 1.0) if len(tc) > 21 else None
```
where `tc = closes[t].dropna()` — using the same wide `closes` DataFrame passed in.

The basket-level 20d perf (used for the `perf["20d"]["rel"]` sort key and the headline story) is computed at `engine/baskets_region.py:85`:
```python
perf = _perf(lvl, bench, idx, ytd_anchor, mtd_anchor)
```
where `lvl = _ew_level(rets, members, idx)` and `rets = closes.pct_change(fill_method=None)`.

**Step 4 — Confirm auto_adjust=True in the collector (`collectors/china_universe.py:191`)**

```python
df = yf.download(batch, period=period, auto_adjust=True, ...)
```

The collector (`collectors/china_universe.py`) explicitly passes `auto_adjust=True` to yfinance. The docstring confirms: "data/china_search/closes.parquet — wide [date x ticker] **adjusted** closes". The merge logic is also seam-free for re-adjusted series (`_overwrite_overlap()` at `collectors/china_universe.py:53`).

### V3 Verdict: DIVIDEND-ADJUSTED, exact store is `data/china_search/closes.parquet`

The basket 20d relative performance is computed entirely off `data/china_search/closes.parquet` — the wide dividend/split-ADJUSTED total-return close panel (yfinance `auto_adjust=True`). No raw price store is involved. Both the member-level 20d return and the basket-level EW-level perf use the same adjusted plane.

The benchmark is `store.read("china", "510300.SS")` (CSI 300 ETF, also from the `data/china/` store which is yfinance `auto_adjust=True` per `collectors/china_prices.py:82`). All perf is therefore relative to an equally-adjusted benchmark — consistent.

---

## V4: What does site/china_stocks.html read at page load?

### Claim to verify
Which artifact(s) does `site/china_stocks.html` actually read at page load?

### Analysis of the rendered file

**No network fetches in `china_stocks.html`:**

Grep for `fetch(`, `XMLHttp`, `chinastockdata`, or `.json'` in `site/china_stocks.html` returns zero results for network fetches. The file contains no `fetch()` calls.

**All data is INLINE:**

1. **`<script type="application/json" id="sb-data">`** (line 11781) — Contains the full stock-screener JSON with three arrays: `alpha` (16 names), `lowvol` (16 names), `reversal` (16 names). This is a large inline JSON block committed into the HTML at render time. The JS at line 11786 reads it:
   ```javascript
   DATA = JSON.parse(document.getElementById('sb-data').textContent);
   ```

2. **`<script type="application/json" id="sb-seczh">`** (line 11782) — Inline sector-to-Chinese-name map. Read at line 11787.

3. **All 110 standout cards** (lines 1207–~7800) are fully rendered as static HTML at build time by `scripts/build_china_library.py`. The conviction profile bars (`SEL`/`ENT`/`TWD`/`QUAL`), the sparkline SVGs, the cascade tier badges (T1/T2/T3/T4), and the entry gauge blocks are all pre-computed inline. Zero client-side fetches for the card strip.

4. **Live price ticker** — `data-sym` attributes on `<span class="nb-px">` elements (e.g., line 1212: `data-sym="600267.SS" data-mkt="cn"`) appear to support a live-price overlay, but this is driven by the shared `theme.js` WebSocket/polling layer, not by any JSON file specific to `china_stocks.html`.

**The per-stock detail (china_lookup.html) does fetch:**
`site/china_lookup.html` (line 864, 922) fetches from `chinastockdata/calibration.json` and `chinastockdata/<TICKER>.json`. But `china_stocks.html` is the board page, not the lookup page — it makes no such fetches.

### V4 Verdict: ALL DATA IS FULLY INLINE — no external JSON fetches at page load

`site/china_stocks.html` reads zero external files at page load. All rendered content (110 standout cards + the stock-screener tables) is committed directly into the HTML at build time. UI work targeting the standout board must modify the **build script** (`scripts/build_china_library.py`) and/or the **template** (`templates/china_stocks.html`), not any runtime JSON. The per-stock detail fetches (`chinastockdata/*.json`) belong to `site/china_lookup.html`, not to `china_stocks.html`.

---

## Summary table

| Item | Status | Key finding |
|---|---|---|
| V1 (rev_z coverage) | FIXED | `rev_z_all` in `engine/china_reversal.py:108` covers 1,478 names; all 110 board names carry real rev_z. Old top-16 path would have missed 108/110 (98%). |
| V2 (leakage harness) | PARTIAL | `scripts/shadow_pit_china.py` covers rev_z causality + washout-2W plane/bucket taxes. Cascade freshness (T1-T4 FRESH_TICKS) is NOT covered. |
| V3 (basket perf plane) | CONFIRMED | 20d rel perf computes off `data/china_search/closes.parquet` — yfinance `auto_adjust=True` dividend-adjusted. Benchmark 510300.SS also adjusted. |
| V4 (page data sources) | CONFIRMED | All data inline in the committed HTML. Zero external JSON fetches. UI work targets `scripts/build_china_library.py` / `templates/china_stocks.html`. |
