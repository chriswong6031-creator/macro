# BUILD-READY SPEC — P1b HK Southbound-vs-Price Divergence Chip (DISPLAY-ONLY)

## 1. Goal / Scope

A **display-only** conditioning chip on `hk.html` that contrasts the **southbound-net flow trend** (mainland money buying HK shares) against the **HK price trend** (`^HSI`) and labels the relationship as one of a small neutral set: **confirms / diverges / mixed / insufficient-data**. It is descriptive context ("flows and price are pulling the same way" vs "flows are leaving while price holds up"), NOT a buy/sell call.

Hard constraints (shared rules):
- **Zero new collector.** Both inputs are already live on disk: southbound via `collectors/china_connect.py` → `store.read("china_connect", "southbound")` (columns `net`, `hold_mktcap`; `_LEGS["southbound"]="006"`, `_FIELDS` at `china_connect.py:39-44`), and price via `store.read("hk", "^HSI")["close"]` (`config.yml:1838` `market_index: "^HSI"`; on-disk file `data/hk/_HSI.parquet`, 1986→ — confirmed live).
- **Not wired into scoring.** The chip must NOT touch `engine/hk_axes.py`, `engine/hk_regime.py:liquidity_overlay()` (the southbound-into-regime path), or any MRS/regime composite. It is a view-model field rendered in the template only. A separate Phase-0 (§4) runs in parallel and could LATER promote it — never assume it passes.
- Placement: beside the existing southbound / HKMA-peg-funding context panels in `templates/hk.html.j2`.

## 2. Compute

New deterministic leaf in `engine/china_internals.py` (where `southbound_flow()` already lives, `china_internals.py:76-103` — keeps the southbound-reading code co-located and reuses the module-level `from lib import store` import at `china_internals.py:19`). It re-reads the same store, so it is self-contained and None-safe.

```python
# engine/china_internals.py — append after southbound_flow() (after line 103)

def southbound_price_divergence(window: int = 63) -> dict | None:
    """DISPLAY-ONLY context chip: is the southbound-net FLOW trend pulling the same
    way as the HSI PRICE trend over a ~quarter window?  Descriptive, not a signal —
    NOT wired into hk_axes / hk_regime / MRS.  z-trend of window-cumulative southbound
    net vs window HSI return.  Returns None if either series is missing/too short."""
    sb = store.read("china_connect", "southbound")
    if sb is None or sb.empty or "net" not in sb.columns:
        return None
    net = sb["net"].dropna()
    px = store.read("hk", "^HSI")          # store sanitizes "^HSI" -> data/hk/_HSI.parquet
    if px is None or "close" not in px.columns:
        return None
    close = px["close"].dropna()
    # need a full window plus a baseline for the z, on BOTH series
    if len(net) < window + 20 or len(close) < window + 5:
        return {"state": "insufficient", "n_flow": int(len(net)), "n_px": int(len(close))}

    # FLOW trend: window-cumulative southbound net, z-scored vs its own 1y history
    cum = net.rolling(window).sum()
    base = cum.dropna().tail(252)
    if len(base) < 30:
        return {"state": "insufficient", "n_flow": int(len(net)), "n_px": int(len(close))}
    mu, sd = float(base.mean()), float(base.std() or 1.0)   # `or 1.0` zero-sigma guard, per southbound_flow()
    flow_z = (float(cum.iloc[-1]) - mu) / sd                # >0 = flows accelerating IN

    # PRICE trend: window return of HSI
    px_ret = float(close.iloc[-1] / close.iloc[-window] - 1.0)   # >0 = price up

    # deterministic neutral bands (z and pct both with a dead-zone to avoid flicker)
    Z_HI, RET_HI = 0.5, 0.02
    flow_up = flow_z >= Z_HI
    flow_dn = flow_z <= -Z_HI
    px_up   = px_ret >= RET_HI
    px_dn   = px_ret <= -RET_HI

    if (flow_up and px_up) or (flow_dn and px_dn):
        state = "confirms"          # flow and price agree (both up or both down)
    elif (flow_up and px_dn) or (flow_dn and px_up):
        state = "diverges"          # flow and price disagree
    else:
        state = "mixed"             # one or both in the dead-zone

    return {
        "state": state,             # confirms | diverges | mixed | insufficient
        "flow_z": round(flow_z, 2),
        "px_ret_pct": round(px_ret * 100, 1),
        "window_d": window,
    }
```

Notes:
- **Reuses the exact z-construction idiom** already in `southbound_flow()` (`china_internals.py:83-89`: tail-window mean/std, `or 1.0` zero-sigma guard), so it matches the repo's existing southbound semantics. NOTE: `southbound_flow()` z-scores the SINGLE-day `net` vs a 252d window; this chip z-scores the WINDOW-CUMULATIVE net vs its own 252d history — same idiom, different object; this is intentional (a trend, not a one-day spike).
- **Neutral chip states only** — `confirms`/`diverges`/`mixed`/`insufficient`. No green-good / red-bad color implied at compute time; the template (§3) picks a neutral accent. A `diverges` state is explicitly NOT "bearish" — it could be flows-out-while-price-up OR flows-in-while-price-down; the descriptive copy says which via the two numbers.
- **Guards:** missing store / missing column → `None` (panel drops, mirroring the `if sb:` pattern in `build_hk.py:_internals_vm` at `:306-311`); too-short data → explicit `{"state": "insufficient", ...}` so the template can show a muted "not enough history" line rather than vanishing.
- Default `window=63` (~one quarter) matches the 63d forward horizon tested in Phase-0; the constant is a kwarg so calibration could later sweep it without a schema change.

## 3. Template + Build Wiring

**Build wiring** — `scripts/build_hk.py:_internals_vm()` (`build_hk.py:299-320`; it already does `from engine import china_internals as ci` and `sb = ci.southbound_flow()` at `:306`, then `vm["southbound"] = sb` at `:311`). Add one None-safe block alongside:

```python
# scripts/build_hk.py:_internals_vm — after the `vm["southbound"] = sb` block (after line 311)
    div = ci.southbound_price_divergence()
    if div:
        vm["sb_divergence"] = div
```

No chart helper needed — it is a text/number chip, so no `_panel_line` call.

**Template** — `templates/hk.html.j2`. The southbound panel runs `hk.html.j2:632` (`{% if internals and internals.southbound %}`) through its closing `{% endif %}` at **line 644**; the next peer is the HKMA-peg-funding panel, whose unique anchor comment is `<!-- ===================== HKMA PEG FUNDING ===================== -->` at **line 646** (gated by `{% if funding %}` at `:647`). Insert the new panel **between** line 644 and 646. Anchor the Edit on the unique HKMA comment string, NOT a bare line number (parallel sessions may shift lines). Render it as its own minimal `span6` panel (parallel to the existing southbound `span6` at `hk.html.j2:633`). Bilingual via in-template `t(en, zh)` pairs (the i18n stack: `t`/`td`/`tr` return `Markup` safe under autoescape; LEX in `engine/i18n.py`, e.g. `"Southbound": "南向资金"` at `:206`, `"Hang Seng Index": "恒生指数"` at `:224`).

```jinja2
  <!-- ===== SOUTHBOUND vs PRICE DIVERGENCE (display-only context) ===== -->
  {% if internals and internals.sb_divergence %}{% set d = internals.sb_divergence %}
  <div class="panel span6">
    <h2>{{ t('🔀 Southbound vs price', '🔀 南向 vs 价格') }} <span class="note" style="text-transform:none">· {{ t('flow trend vs HSI trend', '资金趋势 vs 恒指趋势') }}</span>
      {{ help("Context only, not a buy/sell call: does the ~quarter southbound-net FLOW trend pull the same way as the Hang Seng PRICE trend? 'Confirms' = both up or both down; 'Diverges' = flow and price disagree (read the two numbers for which way). Descriptive conditioning, NOT scored into the regime.", "仅供参考，非买卖信号：约一个季度的南向净流入趋势是否与恒生指数价格趋势方向一致？「同向」＝同涨同跌；「背离」＝资金与价格方向相反（看两个数字判断方向）。描述性背景，不计入周期评分。") }}</h2>
    {% if d.state == 'insufficient' %}
    <div class="note">{{ t('Not enough history to compare.', '历史数据不足，暂无法比较。') }}</div>
    {% else %}
    <div class="stat-row">
      <div><span class="v">{{ t('Confirms','同向') if d.state=='confirms' else (t('Diverges','背离') if d.state=='diverges' else t('Mixed','中性')) }}</span><div class="note">{{ t('flow vs price', '资金 vs 价格') }} · {{ d.window_d }}{{ t('d', '日') }}</div></div>
      <div><span class="v {{ 'pos' if d.flow_z>=0 else 'neg' }}">{{ '%+.1f'|format(d.flow_z) }}σ</span><div class="note">{{ t('southbound flow trend', '南向资金趋势') }}</div></div>
      <div><span class="v {{ 'pos' if d.px_ret_pct>=0 else 'neg' }}">{{ '%+.1f'|format(d.px_ret_pct) }}%</span><div class="note">{{ t('HSI', '恒指') }} {{ d.window_d }}{{ t('d', '日') }}</div></div>
    </div>
    {% endif %}
  </div>
  {% endif %}
```

i18n notes:
- The state word uses inline `t()` ternaries (matching the existing `pos/neg` ternary idiom on `hk.html.j2:637-638`) rather than `td()`, because the three states (`confirms`/`diverges`/`mixed`) are NOT in `engine/i18n.py:LEX`. `td()` IS available and used on this page (e.g. `td(gv.peg.state)` at `:315`, `td(latest.liquidity_overlay)` at `:263`); if you prefer `td()` for consistency, add `"Confirms": "同向"`, `"Diverges": "背离"`, `"Mixed": "中性"` to the HK vocabulary block in `engine/i18n.py` (near `:206-224`) and switch to `{{ td(d.state|capitalize) }}` — but inline `t()` keeps the diff to one file. **[VERIFY: exact LEX insertion point / casing convention for new HK terms in `engine/i18n.py`.]**
- `flow_z`/`px_ret_pct` get the existing `pos`/`neg` CSS classes for neutral sign coloring; the STATE word itself is left class-neutral (`class="v"` only) so `diverges` is not painted red — it is directional-agnostic by design.

## 4. Phase-0 Harness — `scripts/hk_southbound_phase0.py` (NEW)

Pre-registered question: **Does the southbound-vs-price divergence read add INCREMENTAL predictive content for forward HSI returns (21d / 63d) over the named incumbent — HK breadth (`pct_above_50`) + southbound net LEVEL — after orthogonalizing the divergence signal against that incumbent?** Honest prior = **DISPLAY-ONLY** (mirrors the HK residual-alpha kill documented in `scripts/hk_residual_alpha_phase0.py:1-25`, and the fact southbound is ALREADY folded into `liquidity_overlay`).

This is a **single-asset time-series** test (HSI level, not a cross-section), so it uses the time-series primitives in `engine/validation.py` (`newey_west_tstat` at `:322`, `block_bootstrap_ci` at `:201`, `deflated_sharpe` at `:132`, `benjamini_hochberg` at `:362`, `dsr_verdict` at `:162`) — the same import surface as `scripts/insider_phase0.py:46-47` — NOT the `rank_ic` (`:312`) / quintile cross-sectional stack (there is no HK cross-section here).

**There is NO shared incremental-over-incumbent helper** — the orthogonalization is ad-hoc per signal (per the repo's documented Phase-0 culture). Construct it explicitly:

```
Data (all already on disk, daily; ALL read via store.read, NOT raw parquet paths):
  flow   = store.read("china_connect","southbound")["net"]            # 2014→ (Connect era)
  hold   = store.read("china_connect","southbound")["hold_mktcap"]    # for the LEVEL incumbent
  hsi    = store.read("hk","^HSI")["close"]                           # 1986→ ; align to flow window
  brth   = store.read("hk_breadth","breadth")["pct_above_50"]         # 2000-03-10→2026-06-12, 6542 rows
           (NOTE: read via store, not pd.read_parquet — _breadth() at build_hk.py:175 uses
            store.read("hk_breadth","breadth"); cols confirmed:
            n_members,pct_above_50,pct_above_200,nh,nl,adv,dec,ad_line)

Binding window = the OVERLAP of all three ≈ Connect-era 2014→2026 on a daily grid.
[VERIFY] effective n after the overlap intersection (~2,900 trading days) — read at
harness-build time and flag low power LOUDLY in the report, exactly as
hk_residual_alpha_phase0.py:11-13 did for the 3y cache (~23 rebalances = no power), and
degrade the verdict to "underpowered → DISPLAY" rather than a spurious GO. Flag if n < ~1,500.

Forward targets:  fwd21 = hsi.shift(-21)/hsi - 1 ;  fwd63 = hsi.shift(-63)/hsi - 1   (overlapping)

Predictors (z-scored on a rolling 252d basis, no look-ahead — shift(1) the z params):
  X_incumbent = [ breadth_z (pct_above_50, level + 20d slope — the diff(20) used at
                             build_hk.py:185 and hk_regime.py:85) ,
                  sb_level_z (window-cum southbound net z — the SAME flow_z used in §2) ]
  X_div       = divergence signal as a CONTINUOUS interaction:
                  sgn(flow_z) * sgn(px_ret) (sign-agreement), OR (flow_z * px_ret) (magnitude);
                  test both as separate "trials".

Incremental test (the crux — no shared helper, build it here):
  1. Regress fwd_h on X_incumbent (OLS, expanding/per-fold) → residual e_h.
  2. Test whether X_div explains e_h: Newey-West t on the slope, lags≈21 (overlap),
     via engine.validation.newey_west_tstat on the per-step contribution series.
     -> reports the INCREMENTAL t / p, not the raw univariate one.
  3. Family-FDR across the panel of trials {div-sign·21d, div-sign·63d, div-mag·21d,
     div-mag·63d} via engine.validation.benjamini_hochberg(pvals, alpha=0.10).
  4. Strategy realization (overlay, honest): long-HSI when divergence=='confirms' & flow_up,
     flat on 'diverges'/'mixed', daily-rebalanced EXCESS vs buy-and-hold.
       - deflated_sharpe(sr_daily, ret.skew(), ret.kurt(), T=len(ret),
                         n_trials=len(trials))   # n_trials = the count of configs tried
       - block_bootstrap_ci(strategy_returns, block=21, ann=252)
       - dsr_verdict(dsr)   # SURVIVES≥0.95 / MARGINAL≥0.90 / FAILS<0.90

GO bar (must clear ALL, else DISPLAY-ONLY):
  - INCREMENTAL Newey-West p < 0.05 for ≥1 horizon AND that trial survives BH-FDR (q≤0.10),
  - overlay DSR ≥ 0.90 with n_trials honestly = number of configs swept,
  - block-bootstrap sharpe_gt0_prob ≥ ~0.90 and max-DD not worse than buy-and-hold,
  - effect present in BOTH split-halves of the overlap window (split-half robustness).

Output: reports/hk-southbound-divergence-phase0.md  (table {trial, incr_t, incr_p, q, dsr,
sharpe_ci, maxdd_ci, n} + a one-paragraph human verdict via dsr_verdict()).  No commit,
no site build — pure harness, mirroring china_reversal_phase0.py's main()/render()/verdict() shape.
```

Named incumbent restated: **HK breadth (`pct_above_50` via `store.read("hk_breadth","breadth")`, also surfaced by `scripts/build_hk.py:_breadth()` at `:174-185` and consumed in `engine/hk_regime.py:84-85` from the assembled frame `f`) + southbound net LEVEL z** (the level already feeds `liquidity_overlay` at `engine/hk_regime.py:54-58` via `f["southbound_cum"].diff(lcfg["roc_window_d"])`). The divergence chip must beat that combination **incrementally**, not in isolation — divergence is a derived interaction of two things the incumbent already contains, so the realistic expectation is near-zero incremental content → ship as display.

## 5. Tests — `tests/test_hk_southbound_divergence.py` (NEW)

Mirror the repo's pattern of synthetic-store + truth-table + render tests. Use monkeypatch/stub on `china_internals.store.read` to inject deterministic frames (no network).

1. **Divergence truth table** — parametrize `(flow_z_sign, px_ret_sign) → expected state` by constructing synthetic `net`/`close` series that force each band:
   - flow↑ & price↑ → `confirms`; flow↓ & price↓ → `confirms`
   - flow↑ & price↓ → `diverges`; flow↓ & price↑ → `diverges`
   - flow in dead-zone (|z|<0.5) OR price in dead-zone (|ret|<2%) → `mixed`
2. **Chip shape** — when state ∈ {confirms,diverges,mixed}, dict has exactly keys `{state, flow_z, px_ret_pct, window_d}`, all JSON-serializable (float/int/str), `window_d == 63`.
3. **Guard / insufficient** — short `net` (< window+20) → `{"state":"insufficient", ...}`; missing `"close"` column → `None`; missing southbound store → `None`.
4. **Display-only invariant** (the load-bearing test, per shared rules) — assert the symbol is NOT used by the scoring path: a `grep`-style assertion that the source text of `engine/hk_axes.py` and `engine/hk_regime.py` does NOT contain `southbound_price_divergence`, and that the imported `engine.hk_axes` / `engine.hk_regime` modules expose no attribute named `southbound_price_divergence`. This pins the "never wired into scoring" rule as a regression guard.
5. **Bilingual render** — render the panel with a stub `internals.sb_divergence` for each state under EN and ZH; assert EN output contains `Southbound vs price` and `Confirms`/`Diverges`/`Mixed`, ZH output contains `南向 vs 价格` and `同向`/`背离`/`中性`, and the `insufficient` branch renders the muted note (`Not enough history` / `历史数据不足`). **[VERIFY: the in-repo template-render test helper and the lang/context-var name the HK template's `t()`/`td()` reads — confirm against an existing passing HK/template render test (candidates: the first-render harness in `tests/test_advanced_page.py` per memory advanced-page-pct-fix, or any existing `tests/test_*hk*` render fixture) and match it rather than hand-rolling a Jinja `Environment`.]**

## 6. Effort, Gotchas, [VERIFY]

**Effort:** ~Small. One leaf function (~35 LOC) + 2-line build hook + one template panel + one new harness script + one test file. No new collector, no schema change, no CI change (the chip rides the existing `daily`/`weekly` HK build; the harness is run-on-demand and writes only to `reports/`). Net-new files: `scripts/hk_southbound_phase0.py`, `tests/test_hk_southbound_divergence.py`. Edited files: `engine/china_internals.py`, `scripts/build_hk.py`, `templates/hk.html.j2`.

**Gotchas:**
- **Race-safety.** `templates/hk.html.j2` and `site/*.html` are concurrently edited by parallel sessions. Work in a worktree, commit ONLY your own paths, never `git add -A`, never commit regenerated `site/hk.html` (`pages.yml` is upload-only). Verify the template edit via `grep -n "Southbound vs price" templates/hk.html.j2` + `pytest`, NOT live preview (per memory us-standout-setup-score: concurrent sessions race shared HTML).
- **Insertion line drifts.** The southbound panel's closing `{% endif %}` is `hk.html.j2:644` and the HKMA anchor `<!-- ===================== HKMA PEG FUNDING ===================== -->` is `:646` TODAY; a parallel session may shift them. Anchor the Edit on the unique HKMA comment string, NOT a bare line number.
- **Breadth & HSI are STORE reads, not raw parquet paths.** Use `store.read("hk_breadth","breadth")` (as `_breadth()` does at `build_hk.py:175`) and `store.read("hk","^HSI")` — do NOT `pd.read_parquet("data/hk_breadth/breadth.parquet")` / `"data/hk/_HSI.parquet"` directly in either the leaf or the harness; the store layer owns key→file sanitization.
- **`store.read("hk", "^HSI")` symbol literal.** The store key is the literal ticker `"^HSI"`; the on-disk file is `data/hk/_HSI.parquet` (the `^` is sanitized to `_` by the store layer), so pass `"^HSI"` not `"_HSI"`, matching `_benchmark_card()` at `build_hk.py:158-159`. (NOTE: `data/hk/_HSIL.parquet` also exists — a DIFFERENT series; do not confuse it with `_HSI`.)
- **Autoescape / `Markup`.** Keep all user-facing strings inside `t()`/`td()` (they return `Markup`); do not concatenate raw `str + Markup` or build attribute strings by hand (memory: `&`/`str+Markup` autoescape footgun; the `t()`-in-title-attr bug from us-standout-setup-score).
- **Overlap window is the binding power constraint, not name count** — southbound only exists post-2014 (Connect launch, per `china_connect.py:9`), so the Phase-0 effective n ≈ ~2,900 daily obs / ~12y of overlap. This is the exact trap that made the first HK residual-alpha read inconclusive (`hk_residual_alpha_phase0.py:11-13`). Report n loudly; an underpowered result must degrade to DISPLAY, never a spurious GO.
- **Divergence is derived from incumbent inputs** — flow_z and price-trend are both already inside the breadth+southbound-level incumbent (`liquidity_overlay` uses southbound sign at `hk_regime.py:54-58`; the cycle tag uses `pct_above_50` at `:84-86`). The incremental test is therefore expected to be ~null; that's the honest prior, and the chip ships as display regardless.
- **Northbound caveat (not used here but adjacent):** `china_connect.py:51` notes northbound "may be permanently null going forward" (regulator-curtailed Aug-2024, per `:12-15`). This chip uses ONLY southbound, so it is unaffected — but `southbound_flow()` itself reads northbound for `nb_turnover` (`china_internals.py:98-102`); do NOT replicate that, and never pull `northbound` for the trend.

**[VERIFY] open items:**
- [VERIFY] Effective overlap `n` after intersecting southbound (2014→) ∩ HSI ∩ breadth (2000→) on a common daily grid — read at harness-build time; flag if < ~1,500.
- [VERIFY] The in-repo template-render test helper for the bilingual render test, and the `lang`/context-var name the HK template's `t()`/`td()` reads for ZH (the macros read a thread-local or context flag) — confirm against an existing passing HK/template render test before writing the bilingual assertions.
- [VERIFY] Whether to add the three state words to `engine/i18n.py:LEX` (HK block near `:206-224`) for `td()` use vs the inline-`t()` approach in §3 — inline keeps the diff single-file; `td()` is the page's prevailing idiom (`td(gv.peg.state)`:315, `td(latest.liquidity_overlay)`:263).

**Real file/symbol anchors used:** `engine/china_internals.py:19` (`from lib import store`), `:76-103` (`southbound_flow`, z-idiom + None-guard + northbound `nb_turnover` read), `collectors/china_connect.py:9-15` (Connect-era start + northbound-curtailed note), `:37` (`_LEGS["southbound"]="006"`), `:39-44` (`_FIELDS` net/hold_mktcap), `:51` (`stale_after_days=6` northbound-null note), `scripts/build_hk.py:155-171` (`_benchmark_card`, `store.read("hk","^HSI")["close"]`), `:174-185` (`_breadth`, `store.read("hk_breadth","breadth")`, `pct_above_50`, `diff(20)`), `:299-320` (`_internals_vm`, `sb=ci.southbound_flow()`:306, `vm["southbound"]=sb`:311), `config.yml:1838` (`market_index: "^HSI"`), `templates/hk.html.j2:632-644` (southbound panel) & `:646` (HKMA-peg anchor comment) & `:263,315` (`td()` usage idiom), `engine/hk_regime.py:54-58` (southbound-into-liquidity), `:84-86` (`pct_above_50` cycle tag), `engine/hk_axes.py` (scoring path — must NOT reference the new leaf), `engine/i18n.py:206` (`南向资金`), `:224` (`恒生指数`), `engine/validation.py:132` (`deflated_sharpe`), `:162` (`dsr_verdict`), `:201` (`block_bootstrap_ci`), `:312` (`rank_ic`), `:322` (`newey_west_tstat`), `:345` (`ic_summary`), `:362` (`benjamini_hochberg`), `scripts/insider_phase0.py:46-47,136,141` (TS-primitive import + DSR/bootstrap call pattern), `scripts/china_reversal_phase0.py` (harness main/render/verdict shape), `scripts/hk_residual_alpha_phase0.py:1-25` (HK power-constraint + honest-kill precedent), `data/hk_breadth/breadth.parquet` (via store; cols `n_members,pct_above_50,pct_above_200,nh,nl,adv,dec,ad_line`; 2000-03-10→2026-06-12, 6542 rows), `data/hk/_HSI.parquet` (via `store.read("hk","^HSI")`; `_HSIL.parquet` is a distinct series — do not use).
