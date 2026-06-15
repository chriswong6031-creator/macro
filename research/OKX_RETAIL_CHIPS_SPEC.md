# BUILD-READY SPEC — P1a: OKX Retail Positioning Chips (DISPLAY-ONLY)

Branch `quant-factor-expansion`. All file:line refs verified against the working tree 2026-06-14. `[VERIFY]` flags mark anything not confirmable from current code (live endpoint behaviour, history depth).

---

## 1. Goal / Scope

Add two **display-only** crypto positioning chips to the Bitcoin Vector leverage card on `vector.html`, sourced from OKX's free/keyless `rubik` retail-sentiment endpoints:

- **Retail long/short account ratio** — `# accounts net long ÷ # accounts net short` for BTC. This is OKX's *account-count* ratio (breadth of retail positioning), distinct from the *funding rate* (price of leverage, `funding_z`) and *OI* (notional, `oi_mcap_pctile`) we already show.
- **Taker buy/sell volume ratio** — aggressive market-buy vs market-sell taker flow. A short-horizon order-flow imbalance gauge.

Both render as `mini` chips inside the existing **Leverage state** card (`templates/vector.html.j2` h3 at line 726; the chips run lines 727–736; the card's footnotes are lines 737/741/742), immediately after the funding chip (line 731), beside the existing OI (line 730) / funding (731) / CME-basis (734) / OI-divergence (736) positioning chips. The DVOL chip (line 697) lives one card up in the separate options/vol card — referenced only for the render-pattern, not adjacency.

**Hard scope rules (display-only conditioning chip):**
- ZERO scoring. Not added to `engine/btc_signals.py::allocation` (line 338) or `compute_all` (line 1059); not to any axis weight in `engine/axes.py`; not to `leverage_stress` (the `parts`/`weights` block, `btc_signals.py:626–632`); not to `engine/regime.py::classify` (line 137) or MRS. Display columns only.
- The *neutral lean* framing: extreme retail-long-skew is labeled **crowded / contrarian-caution**, NOT a buy. Extreme retail-short-skew labeled **crowded shorts / capitulation context**. This is the same *contrarian* posture the existing funding chip's `composite_context` enum takes (template line 365), though that enum's states are `'crowded_short'` / `'froth'` — the new chip carries its OWN independent enum (§3c) and is a SEPARATE chip, not merged into `composite_context`. Labels are CONTEXT, never a directional trigger.
- A SEPARATE Phase-0 script (§5) runs in parallel and only *later* could promote to scored — never assume it passes. Honest prior = stays display.

`[VERIFY: the upstream fact-sheet claimed an existing F&G positioning chip on vector.html. This is FALSE — fear_greed is loaded at engine/btc_inputs.py:104 (`_col("sentiment_crypto", "fear_greed")`) but is NOT a rendered positioning mini-chip; it appears only in the sources footnote at templates/vector.html.j2:951. The new chips are placed beside the verified funding (line 731) chip, NOT beside any F&G chip.]`

---

## 2. Collector additions — `collectors/okx.py`

The adapter already exists (`OkxAdapter`, lines 23–82) with `name="okx"`, `group="okx"`, `stale_after_days = 3`. Both rubik endpoints are keyless and US-reachable (module docstring lines 1–2 confirms OKX works from US while Binance/Bybit are geo-blocked 451/403). **Keep `stale_after_days = 3`** (matches funding/OI cadence; rubik daily series update once per UTC day). The base `Adapter.http_get` (collectors/base.py:70) and `validate` (base.py:47–57, which dedups + `.sort_index()` at line 53) are reused as-is; the runner persists each returned series via `store.upsert(adapter.group, series_name, df)` (base.py:112).

### 2a. Config — `config.yml` okx block (verified lines 499–503)

Add two URLs after `oi_url` (line 501):

```yaml
okx:
  funding_url: https://www.okx.com/api/v5/public/funding-rate-history
  oi_url: https://www.okx.com/api/v5/rubik/stat/contracts/open-interest-volume
  ls_ratio_url: https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio
  taker_url: https://www.okx.com/api/v5/rubik/stat/taker-volume
  inst_id: BTC-USDT-SWAP
  retries: 3
```

`[VERIFY: confirm exact rubik path + response array order against live OKX v5 docs before coding. OKX has renamed rubik endpoints historically. Expected: long-short-account-ratio rows = [ts_ms, ratio]; taker-volume rows = [ts_ms, sellVol, buyVol] — VERIFY column order, it is easy to flip buy/sell. The parse below assumes [ts, sellVol, buyVol]; if live order differs, fix the DataFrame columns= list.]`

### 2b. New fetch methods (mirror `_open_interest`, lines 72–82 — single GET, `period: "1D"`, ts-normalize, dropna+sort)

`collectors/okx.py` currently imports only `time` and `pandas` — **add `import numpy as np` at top** for the divide-by-zero guard. Add two private methods and wire them into `fetch()` (lines 31–41):

```python
def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
    out = {}
    fr = self._funding(full_history)
    if fr is not None:
        out["funding_rate"] = fr
    oi = self._open_interest()
    if oi is not None:
        out["open_interest"] = oi
    lsr = self._ls_account_ratio()
    if lsr is not None:
        out["ls_account_ratio"] = lsr
    tk = self._taker_volume()
    if tk is not None:
        out["taker_volume"] = tk
    if not out:
        raise ValueError("okx returned nothing")
    return out

def _ls_account_ratio(self) -> pd.DataFrame | None:
    r = self.http_get(self.cfg["ls_ratio_url"], retries=self.cfg["retries"],
                      params={"ccy": "BTC", "period": "1D"}, timeout=30)
    data = r.json().get("data", [])
    if not data:
        return None
    # rows: [ts_ms, ratio]   ratio = #accounts long / #accounts short
    df = pd.DataFrame(data, columns=["ts", "ls_ratio"])
    df["date"] = pd.to_datetime(pd.to_numeric(df["ts"]), unit="ms").dt.normalize()
    df["ls_ratio"] = pd.to_numeric(df["ls_ratio"], errors="coerce")
    return df.set_index("date")[["ls_ratio"]].dropna().sort_index()

def _taker_volume(self) -> pd.DataFrame | None:
    r = self.http_get(self.cfg["taker_url"], retries=self.cfg["retries"],
                      params={"ccy": "BTC", "instType": "SPOT", "period": "1D"}, timeout=30)
    data = r.json().get("data", [])
    if not data:
        return None
    # rows assumed [ts_ms, sellVol, buyVol] -> taker_buy_ratio = buy/(buy+sell)
    df = pd.DataFrame(data, columns=["ts", "sell_vol", "buy_vol"])
    df["date"] = pd.to_datetime(pd.to_numeric(df["ts"]), unit="ms").dt.normalize()
    buy = pd.to_numeric(df["buy_vol"], errors="coerce")
    sell = pd.to_numeric(df["sell_vol"], errors="coerce")
    df["taker_buy_ratio"] = buy / (buy + sell).replace(0, np.nan)
    return df.set_index("date")[["taker_buy_ratio"]].dropna().sort_index()
```

(The trailing `.sort_index()` mirrors `_open_interest`; the base `validate()` also sorts+dedups at base.py:53, so this is belt-and-suspenders, intentionally consistent with the existing OI method.)

**Store keys** — `store.upsert(self.group, name, df)` keys on the `fetch()` dict KEY (the series_name), not the DataFrame column (this is why `funding_rate` is stored at `data/okx/funding_rate.parquet` even though its column is `funding_rate_okx`):
- `data/okx/ls_account_ratio.parquet` (column `ls_ratio`)
- `data/okx/taker_volume.parquet` (column `taker_buy_ratio`)

No registration change needed — `OkxAdapter` is already in the `scripts/collect.py` registry as `("okx", "collectors.okx", "OkxAdapter")` and `fetch()` simply returns more series. `[VERIFY: the upstream fact-sheet placed this registry entry at scripts/collect.py:75 — confirm the line; it is non-load-bearing (registry is a flat list, exact line is cosmetic).]`

`[VERIFY: rubik taker-volume needs instType — SPOT vs SWAP gives different series. SWAP taker flow is the leveraged-positioning read and is more on-thesis for a "leverage/positioning" card; SPOT is broader. Prefer SWAP if available for BTC; the example above uses SPOT as the safe default. Confirm rubik history depth: these endpoints typically return only a SHALLOW recent window (weeks–months), like _open_interest (docstring line 8: "recent window only"). That shallow depth is the binding Phase-0 constraint — see §5.]`

---

## 3. Engine read + chip compute

### 3a. Input load — `engine/btc_inputs.py::load_all` (dict built lines 73–126)

Add two `_col()` loads near the existing OKX/derivatives block (the `_col(group, name, col=None)` helper at lines 24–31 reads → reindexes to the price index → ffills). Insert beside `"open_interest"` (line 98):

```python
"okx_ls_ratio": _col("okx", "ls_account_ratio"),     # OKX retail account long/short breadth
"okx_taker_buy": _col("okx", "taker_volume"),        # taker buy / (buy+sell) flow ratio
```

(`_col` selects the first/only numeric column of the parquet, so no explicit `col=` arg is needed for these single-column frames.)

### 3b. Signal transform — `engine/btc_signals.py::leverage` (lines 584–638)

Add the chip computations at the END of `leverage()`, after the `leverage_stress` block (lines 633–637) and before `return out` (line 638). Reuse the module's `_zscore(s, n)` (lines 43–45) and `_pctile(s, lookback)` (lines 39–40; returns a 0–1 fraction → multiply by 100). **Do NOT append these to `parts`/`weights` (lines 626–632) — that block IS `leverage_stress`, which is scored.** Display columns only:

```python
lsr = inputs.get("okx_ls_ratio")
if lsr is not None:
    s = lsr.reindex(idx).ffill(limit=3)
    out["okx_ls_ratio"] = s
    # rubik depth is shallow -> short rolling windows (new cfg keys, .get() with defaults)
    out["okx_ls_ratio_pctile"] = _pctile(s, cfg.get("okx_pctile_lookback_d", 180)) * 100
    out["okx_ls_ratio_z"] = _zscore(s, cfg.get("okx_z_window_d", 90))

tk = inputs.get("okx_taker_buy")
if tk is not None:
    s = tk.reindex(idx).ffill(limit=3)
    out["okx_taker_buy"] = s
    out["okx_taker_buy_pctile"] = _pctile(s, cfg.get("okx_pctile_lookback_d", 180)) * 100
```

Add config under the `vector:` (line 1258) → `leverage:` (line 1417) block in `config.yml`, beside the verified incumbent keys `pctile_lookback_d: 730` (1425) and `funding_z_window_d: 180` (1427):

```yaml
    okx_pctile_lookback_d: 180   # rubik history is shallow -> shorter rolling window
    okx_z_window_d: 90
```

(The compute uses `cfg.get(..., default)`, so a missing/renamed key will NOT crash the build — safe even if the YAML path drifts. NB the incumbent funding window key is `funding_z_window_d`, not `z_window_d`; the new keys are deliberately namespaced `okx_*` to avoid collision.)

### 3c. View-model — `scripts/build_vector.py`, the `"leverage"` dict (verified lines 1485–1497)

Add to the `"leverage"` dict (uses the existing `_r(v, n=2)` rounding helper, defined at line 1209). Insert after `"funding_z"` (line 1489):

```python
"okx_ls_ratio": _r(last.get("okx_ls_ratio"), 2),
"okx_ls_pctile": _r(last.get("okx_ls_ratio_pctile"), 0),
"okx_ls_z": _r(last.get("okx_ls_ratio_z"), 1),
"okx_taker_buy": _r(last.get("okx_taker_buy"), 3),
"okx_taker_pctile": _r(last.get("okx_taker_buy_pctile"), 0),
# neutral lean label computed server-side from the z (contrarian framing)
"okx_ls_lean": ("crowded_long" if pd.notna(last.get("okx_ls_ratio_z")) and last["okx_ls_ratio_z"] > 1.5
                else "crowded_short" if pd.notna(last.get("okx_ls_ratio_z")) and last["okx_ls_ratio_z"] < -1.5
                else "balanced"),
```

**Neutral-lean semantics** (its own independent enum — NOT the funding `composite_context` states): `crowded_long` ⇒ contrarian-caution (NOT a buy); `crowded_short` ⇒ capitulation context; `balanced` ⇒ no edge. Same contrarian posture as the funding chip's `composite_context` (template line 365, whose own states are `crowded_short`/`froth`), but a SEPARATE chip with its own field. The label is CONTEXT, never sized.

---

## 4. Template + build wiring — `templates/vector.html.j2`

Insert two `mini` chips in the **Leverage state** card, immediately after the funding chip (line 731), before the CME-basis block (line 732). Mirror the exact `mini`/`lab`/`faint` structure of funding (line 731) and OI (line 730). Bilingual via the in-template `t(en, zh)` macro (defined line 5):

```jinja2
{% if leverage.okx_ls_ratio is not none %}
<div class="mini"><div class="lab"><span>{{ t('OKX retail long/short (accounts)','OKX 散户多空比（账户数）') }}</span><span><b style="color:{{ 'var(--r3)' if leverage.okx_ls_lean=='crowded_long' else ('var(--blue)' if leverage.okx_ls_lean=='crowded_short' else 'var(--ink)') }}">{{ '%.2f'|format(leverage.okx_ls_ratio) }}</b>{% if leverage.okx_ls_pctile is not none %} <span class="faint">({{ leverage.okx_ls_pctile }}%ile{% if leverage.okx_ls_z is not none %} · z {{ leverage.okx_ls_z }}{% endif %})</span>{% endif %}
{% if leverage.okx_ls_lean=='crowded_long' %} <span class="faint" style="color:var(--r3)">· {{ t('crowded longs (contrarian caution, not a buy)','多头拥挤（反向警示，非买入信号）') }}</span>{% elif leverage.okx_ls_lean=='crowded_short' %} <span class="faint" style="color:var(--blue)">· {{ t('crowded shorts (capitulation context)','空头拥挤（投降式背景）') }}</span>{% endif %}</span></div></div>{% endif %}
{% if leverage.okx_taker_buy is not none %}
<div class="mini"><div class="lab"><span>{{ t('OKX taker buy/sell flow','OKX 主动买卖盘占比') }}</span><span><b>{{ '%.0f'|format(100*leverage.okx_taker_buy) }}%</b> <span class="faint">{{ t('buy share','主动买占比') }}{% if leverage.okx_taker_pctile is not none %} ({{ leverage.okx_taker_pctile }}%ile){% endif %}</span></span></div></div>{% endif %}
```

Append a one-line honesty caveat as a new `sub faint` after the existing leverage-card footnotes (lines 741/742), mirroring the CME-basis honesty caveat at line 742:

```jinja2
<div class="sub faint" style="margin-top:6px;font-size:12px">{{ t('OKX retail long/short & taker flow are DISPLAY-ONLY positioning context (rubik free data, shallow history) — shown as crowding context, never wired into the allocation or scored. Extreme retail-long = crowded/contrarian, not a buy.', 'OKX 散户多空比与主动买卖盘为仅展示的持仓背景（rubik 免费数据，历史较浅）— 仅作拥挤度背景，不参与仓位或评分。散户极度看多 = 拥挤/反向，而非买入信号。') }}</div>
```

**No `td()`/`tr()` LEX keys needed** — all labels are free strings via the in-template `t(en,zh)` macro (line 5). The lean enum (`crowded_long`/`crowded_short`/`balanced`) is resolved to bilingual copy inline in the `{% if %}` branches above, NOT through `engine/i18n.py` LEX, so no `i18n.py` edit is required.

CSS vars `var(--ink)` / `var(--r3)` / `var(--blue)` are confirmed present in the template's inline `:root` (lines 20–21) and used throughout this page.

**Race-safety:** `templates/vector.html.j2` and `site/*.html` are concurrently edited by parallel sessions. Work in a worktree; commit ONLY `collectors/okx.py`, `engine/btc_inputs.py`, `engine/btc_signals.py`, `scripts/build_vector.py`, `templates/vector.html.j2`, `config.yml`, `scripts/okx_retail_phase0.py`, and the new test file. **Never commit regenerated `site/vector.html`** (pages.yml is upload-only, rebuilt at build time). Verify via `grep` + `pytest`, NOT live preview.

---

## 5. Phase-0 harness — `scripts/okx_retail_phase0.py` (NEW)

**Honest prior: stays DISPLAY.** Two-fold reason: (a) rubik retail/taker history is shallow (likely weeks–months, like `_open_interest`), so the sample is tiny; (b) the same single-asset-timing trap that flipped the carry signal ([[commodity-carry-validation]]) and the CME basis (template line 742, "rank-IC ~0, 2021→") applies here. Crowding is a *fragility/context* read, not a directional edge.

**This is a SINGLE-ASSET TIME-SERIES test, not cross-sectional.** Do NOT copy the panel rank-IC structure of `scripts/insider_phase0.py` (that's a stock cross-section). The correct precedent is `scripts/calibrate_vector.py` (single BTC series; local `forward_returns(close, horizons)` at line 54: `close.shift(-h)/close - 1`). Use `engine/validation.py` primitives directly:

```
scripts/okx_retail_phase0.py
  load: btc_inputs.load_all() -> btc_signals.compute_all()  (aligned daily frame on price index)
  signals tested (display columns, NOT scored):
      S1 = okx_ls_ratio_z          (retail long/short breadth, z-scored)
      S2 = okx_taker_buy           (taker buy share)
  forward returns: fwd = forward_returns(close, [21, 63])   # calibrate_vector.py:54 (local helper)
  NAMED INCUMBENT (must beat INCREMENTALLY): funding_z (btc_signals.leverage line 624,
      CONFIRMED — template line 737: "funding-z below -1 preceded +18%/90d at 70% hit")
      + oi_mcap_pctile (line 609, CONTEXT). These are the existing crypto positioning incumbents.

  Step A — STANDALONE skill:
    for h in (21, 63):
        per-window rank_ic(S, fwd[h])   (validation.py:312)  over overlapping windows
        ic_summary(ics, periods_per_year=252//h)   (validation.py:345) -> mean IC, IC-IR, hit
        newey_west_tstat(window_ic, lags=4)         (validation.py:322) -> HAC t (overlap-robust)

  Step B — INCREMENTAL over incumbent (the key gate):
    There is NO shared incremental-over-VIX/funding helper — do it ad hoc here.
    Pull the incumbent SERIES off the computed frame (sig = compute_all(...)):
        resid = resid_z(sig["okx_ls_ratio_z"],
                        basis=[sig["funding_z"], sig["oi_mcap_pctile"]],   # SERIES, not names
                        win=W, min_p=M)                                     # min_p is REQUIRED
        (validation.py:380 — sequential CAUSAL rolling-OLS residualization, shift(1) betas,
         takes a list of pd.Series and a fixed window; W/M declared, not tuned.)
    Re-run Step A on `resid`. The new chip earns promotion ONLY if the RESIDUAL
    (orthogonal-to-funding+OI) component carries IC the incumbent doesn't.

  Step C — multiplicity + robustness:
    benjamini_hochberg({S1@21, S1@63, S2@21, S2@63, resid@21, resid@63}, alpha=0.10)
        (validation.py:362) -> q-values; require BH-FDR survival.
    Build the simplest tradable proxy (e.g. long when resid in the contrarian band) ->
        bt = backtest_core(close, alloc, cost_bps)            (validation.py:36)
        m = ret_moments(bt["net"])                            (validation.py:115; alias _ret_moments :129)
        deflated_sharpe(m[0], m[1], m[2], m[3], n_trials=N_TRIALS)   (validation.py:132)
        require dsr_verdict(dsr["dsr"]) PASS at DSR >= 0.90   (validation.py:162)
        N_TRIALS = honest count of (signals x horizons x bands) tried here (~6-12),
        matching the insider_phase0 / setup_score_phase0 honest-n_trials discipline.
        block_bootstrap_ci(bt["net"], block=21)              (validation.py:201) -> Sharpe CI.
    split-half: re-run Step A/B on pre/post split (calibrate_vector uses
        pd.Timestamp("2021-01-01"), build_vector.py:279) — BUT rubik depth likely makes a
        pre-2021 half IMPOSSIBLE; if so, split the AVAILABLE window in half and report the
        sample is too short for a stable split (the most likely real outcome -> stays display).

  Verdict print (mirror insider_phase0 main(), scripts/insider_phase0.py:282):
    GO  only if: incremental resid IC survives BH-FDR(10%) AND DSR>=0.90 AND both half-samples
                 same sign.  -> propose promotion in a SEPARATE follow-up (never auto-wire).
    NO-GO/DISPLAY (honest prior): any gate fails -> chip stays display-only, no engine change.
```

The script is **research-only**: it imports `btc_signals`/`btc_inputs`/`validation`, prints a verdict, optionally writes a markdown report under the `reports/` dir (like `insider_phase0` writes `reports/insider-phase0.md` at scripts/insider_phase0.py:340–342). It does NOT modify any engine file or wire anything.

---

## 6. Tests — `tests/test_okx_retail.py` (NEW)

Mirror existing collector/template test patterns. Four required tests:

1. **`test_okx_ls_ratio_parse`** — feed a stubbed rubik `long-short-account-ratio` JSON (`{"data": [["1718000000000","1.85"], ...]}`) through `OkxAdapter._ls_account_ratio` (monkeypatch the instance's `http_get` to return a fake object whose `.json()` yields the stub); assert the returned frame is date-indexed, single column `ls_ratio`, numeric, sorted, deduped. Same for `_taker_volume` with `[ts, sellVol, buyVol]` rows → assert `taker_buy_ratio = buy/(buy+sell)` is computed correctly and bounded [0,1] (catches the buy/sell column-order flip flagged in §2a/2b).

2. **`test_chip_shape`** — drive `btc_signals.leverage(inputs, cfg)` with a fixture inputs dict (incl. `okx_ls_ratio` / `okx_taker_buy` series and a `price` frame), then build the `"leverage"` view-model dict; assert it contains `okx_ls_ratio`, `okx_ls_pctile`, `okx_ls_z`, `okx_taker_buy`, `okx_taker_pctile`, `okx_ls_lean` with correct types; assert `okx_ls_lean ∈ {crowded_long, crowded_short, balanced}` and that z>1.5 ⇒ `crowded_long`.

3. **`test_display_only_invariant`** (the load-bearing guard) — assert the new symbols never touch scoring:
   ```python
   import inspect
   from pathlib import Path
   from engine import btc_signals
   for sym in ("okx_ls_ratio", "okx_taker_buy", "okx_ls_ratio_z"):
       assert sym not in Path("engine/axes.py").read_text()        # axes.py CONFIRMED present
       assert sym not in Path("engine/regime.py").read_text()      # classify() at regime.py:137
   # must NOT be fed into leverage_stress (the parts/weights block, btc_signals.py:626-632)
   lev = inspect.getsource(btc_signals.leverage)
   stress_block = lev.split("parts, weights = [], []")[1].split("return out")[0]
   assert "okx_ls" not in stress_block and "okx_taker" not in stress_block
   ```
   (`engine/axes.py` and `engine/regime.py::classify` both confirmed present on this branch; BTC allocation also lives in `btc_signals.allocation` (line 338) / `compute_all` (line 1059) — the inspect check covers the in-function `leverage_stress` path, the file-read checks cover axes/regime.)

4. **`test_bilingual_render`** — render `templates/vector.html.j2` with a `vm` fixture (reuse the build_vector env setup: `Environment(..., autoescape=True)` with `td`/`tr` globals, build_vector.py:1587–1599) and assert BOTH `OKX retail long/short` (EN) and `OKX 散户多空比` (ZH) appear, and that `crowded longs (contrarian caution, not a buy)` / `多头拥挤（反向警示，非买入信号）` render when `okx_ls_lean=='crowded_long'`. Confirms the contrarian framing and bilingual coverage ship.

`[VERIFY: no existing OKX/Deribit collector test fixture was located in this pass to clone the http_get monkeypatch idiom; if absent, write the monkeypatch fresh (set `adapter.http_get = lambda *a, **k: _Fake(stub_json)`), else model it on whatever tests/test_*okx* or tests/test_*deribit* uses.]`

---

## 7. Effort, gotchas, [VERIFY] flags

**Effort:** ~Small–Medium. ~25 LOC collector + config, ~12 LOC engine input/signal, ~10 LOC view-model, ~6 lines template, ~120 LOC Phase-0 script, ~80 LOC tests. No new dependency, no new data group (reuses `data/okx/`). The adapter, registry entry, store plumbing, validation primitives, and i18n macro all already exist — pattern-replication, not new infrastructure. Estimate: half a day incl. live-endpoint verification + Phase-0 run.

**Gotchas:**
- **Buy/sell column flip** (§2b) — rubik taker-volume row order is `[ts, sellVol, buyVol]` (sell-then-buy); flipping it silently inverts the chip. Test #1 guards this.
- **Shallow rubik history** — these endpoints likely return only a recent window (like `_open_interest`, lines 72–82, "recent window only" per docstring line 8). This is why `okx_pctile_lookback_d` is short (180) and the dominant reason Phase-0's honest prior is "stays display."
- **`leverage_stress` contamination** — the new columns MUST stay OUT of the `parts`/`weights` block (`btc_signals.py:626–632`). Test #3 enforces.
- **`resid_z` takes Series, not names** — `engine/validation.py:380` signature is `resid_z(z, basis, win, min_p)` where `basis` is a list of **pd.Series** (it does `b.reindex(...)`) and `min_p` is REQUIRED (no default). Pass the actual `sig["funding_z"]` / `sig["oi_mcap_pctile"]` series, NOT the string column names (§5 Step B).
- **Jinja missing-key crash** — every chip is gated `{% if leverage.x is not none %}` and the view-model uses `last.get(...)` (never bracket-index a possibly-missing key), avoiding the recurring `Undefined is not none → True → format raises` build-breaker noted in repo memory.
- **Race on shared HTML/templates** — commit own paths only, never `site/vector.html`; verify via grep+pytest.
- **`composite_context` is separate** — the funding crowding label already exists (template line 365, states `crowded_short`/`froth`); keep the new retail-long label visually consistent (red=crowded-long-caution, blue=crowded-short-capitulation) but it is a SEPARATE chip with its own `okx_ls_lean` enum, do NOT merge into `composite_context`.

**[VERIFY] flags (consolidated):**
1. Live rubik endpoint paths + response array column order (`ls_ratio` rows `[ts,ratio]`; taker rows `[ts,sellVol,buyVol]`) — confirm against OKX v5 docs before coding.
2. taker-volume `instType`: SWAP (on-thesis leverage flow) vs SPOT (broader) — confirm BTC availability; example defaults SPOT, prefer SWAP if available.
3. Actual rubik history depth (drives lookback windows + whether a pre/post-2021 split-half is even possible in Phase-0).
4. `scripts/collect.py` registry line for the existing `("okx", "collectors.okx", "OkxAdapter")` entry (non-load-bearing; flat list).
5. Existing OKX/Deribit collector test fixture to clone the `http_get` monkeypatch idiom — none located in this pass.
6. **Corrected upstream facts:** (a) there is NO F&G positioning chip on vector.html — fear_greed is loaded at btc_inputs.py:104 and appears only in the sources footnote at templates/vector.html.j2:951; new chips sit beside the funding chip (line 731). (b) The `vector:`/`leverage:` config block is at config.yml:1258/1417 (keys 1425–1430), NOT "~line 1078" as the upstream fact-sheet claimed. (c) The DSR/moments helper is `ret_moments` (validation.py:115) with legacy alias `_ret_moments` (:129).

**Confirmed-real anchors:** `collectors/okx.py:23-82` (fetch 31-41, _funding 43-70, _open_interest 72-82), `collectors/base.py:47-57,70,112`, `config.yml:499-503` (okx), `config.yml:1258,1417,1425-1430` (vector→leverage), `engine/btc_inputs.py:24-31,98,104`, `engine/btc_signals.py:39-45,338,584-638` (leverage_stress parts/weights 626-632, funding_z 624, oi_mcap_pctile 609), `scripts/build_vector.py:279,1209,1485-1497,1587-1599`, `templates/vector.html.j2:5,20-21,365,697,723-742,951`, `engine/validation.py:36,115,129,132,162,201,312,322,345,362,380`, `scripts/calibrate_vector.py:54`, `scripts/insider_phase0.py:211,282,340-342`, `engine/axes.py` (present), `engine/regime.py:137`.
