# P0 Fear↔Euphoria Synthesis Panel — build spec (macro.html)

> Status: **BUILD-READY, NOT BUILT.** Display-only. Zero new data. All symbols verified by grep
> against branch `quant-factor-expansion` (2026-06-14). `[VERIFY]` = confirm at build time;
> `[FACT]` = grep-verified this session. Decision context: [[sentiment-engine-analysis]] P0 item.
> The panel is a *regime/conditioning read, never a scored directional leg* — same posture as
> [[narrative-quant-framework]] (display-only, gate pinned).

---

## 1. Goal & scope

One `panel span12` on `site/macro.html` (id `fear-euphoria`) that synthesizes already-computed
components — the RORO risk-on/off composite (`latest.conditions.risk_appetite.roro`), the
dislocation verdict + Fed-put switch (`latest.dislocation`), and the capitulation gauge
(`latest.conditions.capitulation`) — into a single **0–100 Fear↔Euphoria** regime read, a
**7-leg decomposition**, and a deterministic **"positioning confirms / diverges / mixed"** chip.

It does NOT touch `engine/axes.py`, `engine/regime.py:classify`, or
`engine/conditions.py:macro_risk_snapshot` (`conditions.py:618`, the real MRS surface), or any leg
those score. It **links out** to `site/gex.html` for dealer-gamma rather than re-surfacing it.
`fear_euphoria_synthesis` is a sibling display read passed only as a render kwarg, exactly like the
`conditions`/`dislocation`/`cross_asset` snapshots.

---

## 2. The 0–100 mapping

**Input:** `conditions_frame(f)["roro"]` — the equal-weighted mean of the 7 RORO leg z-scores
(`engine/conditions.py:230-231`). Dimensionless, ~0-centered, **positive = risk-on**.
`latest.conditions.risk_appetite.roro` is the persisted scalar (display only).

```python
from engine.indicators import pct_rank_window     # canonical (indicators.py:65)  [FACT-C1]
from engine.conditions import conditions_frame

roro_series = conditions_frame(f)["roro"]
pct = pct_rank_window(roro_series, 252 * 5).iloc[-1]   # rolling 5y window; valid after ~2.5y
if pct is None or not np.isfinite(float(pct)):         # MANDATORY shallow-cache guard
    return None
fe_score = max(0, min(100, round(100 * float(pct))))   # 0 = extreme fear, 100 = extreme euphoria
```

- `pct_rank_window` = `s.rolling(window, min_periods=window//2).rank(pct=True)` → a **rolling**
  percentile in [0,1], non-NaN after `window//2` obs. Describe as "rolling 5y window (valid after
  ~2.5y)", **not** "5y-anchored" [FACT-C5].
- **NaN guard is load-bearing:** price cache is 2023+ → a 1260-day window may have <630 non-NaN
  `roro` obs → `.iloc[-1]` NaN → bare `round(100*nan)` breaks. Early-return `None` [C5].
- **Sign:** RORO is risk-on-positive → high percentile = euphoria, low = fear. No flip.
- **Why percentile not z:** robust to fat tails / non-stationarity; self-explanatory; matches the
  dashboard's NFCI-percentile convention. Show raw `roro` + `roro_state`
  (`risk-on`/`risk-off`/`neutral`, ±0.35 from `config.yml roro:`) as secondary context.

**Bands** — on the rounded int `fe_score`, half-open intervals:

| Band | Interval | EN | ZH |
|------|----------|-----|-----|
| Panic | `fe < 10` | Panic | 恐慌 |
| Fear | `10 ≤ fe < 35` | Fear | 恐惧 |
| Neutral | `35 ≤ fe < 65` | Neutral | 中性 |
| Greed | `65 ≤ fe < 90` | Greed | 贪婪 |
| Euphoria | `fe ≥ 90` | Euphoria | 欣喜 |

`_fe_band(fe_score:int) -> str` returns the EN key; ZH via `td()`/`t()`.

---

## 3. Per-leg decomposition

7 RORO legs (`engine/conditions.py:214-229`). **6 negated in the composite, copper/gold positive** [FACT]:

| Leg key | Source expr (as appended to `roro_parts`) | EN name | ZH name |
|---------|--------------------------------------------|---------|---------|
| `vix` | `-_z(vix, zw)` | VIX | 波动率 VIX |
| `hy_oas` | `-_z(f["hy_oas"], zw)` | HY credit spread | 高收益信用利差 |
| `skew` | `-_z(skew, zw)` | SKEW (tail pricing) | SKEW 尾部定价 |
| `vix_term` | `-_z(out["vix_term"], zw)` | VIX term structure | VIX 期限结构 |
| `nfci` | `-_z(nfci, zw)` | Financial conditions (NFCI) | 金融条件 NFCI |
| `copper_gold` | `_z(copper_gold, zw)` (**positive**) | Copper/Gold | 铜／金 比 |
| `dxy` | `-_z(dxy.pct_change(20, fill_method=None), zw)` | Dollar (20d %Δ) | 美元（20日 %变动） |

Per leg: signed contribution (the value as it enters the mean) + its rolling-5y percentile +
`lean = "risk-on" if value > 0 else "risk-off"`. High VIX → negative contribution → `risk-off`.

```python
{"key": "vix", "name_en": "VIX", "name_zh": "波动率 VIX",
 "value": <float>,   # latest SIGNED contribution (negated where applicable)
 "pct": <int 0-100>, # rolling-5y percentile of that signed series
 "lean": "risk-off"} # HYPHEN — must match LEX keys i18n.py:281-282 [C10]
```

- **`lean` hyphenated** `risk-on`/`risk-off` and rendered via `td()` — LEX is hyphen-keyed; an
  underscore misses LEX and falls back to English [C9/C10].
- These signed series are **not** in `latest.json`. **Preferred (additive, low-risk):** in
  `conditions_frame` attach each as `out["roro_<key>"]` (already-signed, e.g.
  `out["roro_vix"] = -_z(vix, zw)`) so `mean(roro_*) == roro` — store **signed**, not raw z, or
  lean inverts [C7]. Else recompute inline with the **exact** exprs above, incl.
  `dxy.pct_change(20, fill_method=None)`. `zw = config.yml roro.z_window_d`.

---

## 4. Positioning confirms / diverges read

**Scope [FACT]:** southbound flow is China/HK-only (`china_internals.py`, `hk_regime.py`), NOT in the
US `latest.json` macro.html renders — do NOT reference it here. Available US-macro inputs (zero new data):

- **COT spec positioning** — `store.read("cot","cot_es_spx")["net_spec_pct_oi"]` (S&P leg). The
  washout boolean is **not persisted** (`capitulation.signals_firing` holds only `"VRP extreme"`/
  `"VIX panic"`) [FACT-C3] — recompute, mirroring `conditions.py:262-265`:
  ```python
  cot = store.read("cot", "cot_es_spx")
  ns  = cot["net_spec_pct_oi"].reindex(<index>).ffill(limit=10)
  p   = pct_rank_window(ns, ccfg["cot_pctile_lookback_d"]).iloc[-1]      # lookback 756
  cot_washed_out   = p is not None and np.isfinite(p) and p < ccfg["cot_washout_pctile"]      # 0.10
  cot_crowded_long = p is not None and np.isfinite(p) and p > 1 - ccfg["cot_washout_pctile"]  # >0.90
  ```
  Guard `cot is None` / missing column / NaN → both `False`.

- **Insider Form-4 breadth** — `factordata/insider_signals.json` (per-ticker
  `{"bps","buyers","sellers","net_mn"}`; the field is **`bps`**, NOT `net_mcap_bps` [FACT-C2]).
  ```python
  vals = [v["bps"] for v in sig.values() if v.get("bps") is not None and np.isfinite(v["bps"])]
  insider_breadth = ((sum(b>0 for b in vals) - sum(b<0 for b in vals)) / len(vals)) if vals else 0.0
  insider_buying, insider_selling = insider_breadth > 0.05, insider_breadth < -0.05
  ```

- **Price reference** — `latest.dislocation.inputs.primary_trend` (`"up"`/`"down"`),
  `…inputs.spy_drawdown_pct`.

**Deterministic rule (no scorer):**
```python
price_up = latest["dislocation"]["inputs"]["primary_trend"] == "up"
bullish  = cot_washed_out  or insider_buying
bearish  = cot_crowded_long or insider_selling
lean = "bullish" if (bullish and not bearish) else "bearish" if (bearish and not bullish) else "mixed"
chip = "mixed" if lean == "mixed" else ("confirms" if (lean == "bullish") == price_up else "diverges")
```
Output `positioning: {"chip": ..., "smart_money_lean": ...}`. Descriptive (positioning-vs-price),
explicitly not a buy/sell.

---

## 5. Dislocation + capitulation inline (read from `latest`)

**`latest.dislocation`:** `verdict ∈ {calm, buyable_washout, stand_aside, unknown}`
[FACT — `dislocation.py:220/270/273/278`; **no `falling_knife`** — that's copy only, never emit
`td('falling_knife')`]. Plus `put_state` (`put-present`/`put-absent`), `fed_put` (bool),
`put_reasons` (list, populated only when absent), `inputs.{spy_drawdown_pct,vix,vrp_pctile,vix_term}`,
`capitulation_caveat` (str|None, render verbatim).

**`latest.conditions.capitulation`** [FACT `conditions.py:462-470`]: `score` (0–3 int|None),
`active`, `strong`, `signals_firing` (list), `measured_bounce_pct`, `measured_hit_pct`,
`base_rate_pct`. **`len(signals_firing) ≠ score`** (COT washout is in `score` but not the list) —
render "N/3" from `score`, firing names separately, tolerate empty [C15].

**Link-out (not re-surfaced):**
```jinja2
<a href="gex.html" class="muted" style="font-size:12px;font-weight:400;float:right">{{ t('dealer gamma →','交易商 gamma →') }}</a>
```

**Absorption (optional):** `latest.cross_asset.absorption_ratio` exists ONLY in the populated
branch; the early-returns (`cross_asset.py:104,108`) omit the key [FACT-C4] →
`{% if latest.cross_asset and latest.cross_asset.get('absorption_ratio') is not none %}`. Render
ratio (float [0,1]) + `verdict` (`diversified|converging|concentrated|unknown`) as fragility context.

---

## 6. Data structure & build wiring

New helper in `scripts/build_site.py` (mimic `holdings_rows()`/`accumulation_rows()` ~941-980:
try/except, log + return `None` on failure — additive, never fatal):

```python
def fear_euphoria_synthesis(latest: dict, f: pd.DataFrame) -> dict | None:
    """DISPLAY-ONLY Fear<->Euphoria regime synthesis. Zero new data: maps the existing RORO
    composite to a rolling-5y 0-100 percentile, decomposes its 7 legs, annotates positioning
    confirms/diverges. NEVER scores; NEVER touches axes/regime/macro_risk."""
    from engine.indicators import pct_rank_window
    from engine.conditions import conditions_frame
    try:
        cf = conditions_frame(f)
        if "roro" not in cf:
            return None
        pct = pct_rank_window(cf["roro"], 252 * 5).iloc[-1]
        if pct is None or not np.isfinite(float(pct)):
            return None
        fe = max(0, min(100, round(100 * float(pct))))
        RA = (latest.get("conditions") or {}).get("risk_appetite") or {}
        return {"fe_score": fe, "band": _fe_band(fe), "roro": RA.get("roro"),
                "roro_state": RA.get("roro_state"),
                "legs": _fe_legs(cf), "positioning": _fe_positioning(latest, f)}
    except Exception as e:  # noqa: BLE001 — additive panel, never fatal
        log.warning("fear/euphoria synthesis failed: %s", e)
        return None
```

The template reads dislocation/capitulation/cross_asset directly from `latest`; the dict carries
only net-new synthesized fields.

**Render binding** — one kwarg on the existing `dashboard.html.j2` render call
(~`build_site.py:1502-1531`; `f` and `latest` in scope, build_site.py:1437/1443):
```python
fear_euphoria=fear_euphoria_synthesis(latest, f),
```

**Confirmations:** no new collector; no change to `axes.py` / `regime.py:classify` /
`conditions.py:macro_risk_snapshot` (618, → `latest["macro_risk"]` via `run.py:108-109`); grep finds
no `roro`/`risk_appetite`/`fear_euphoria`/`fe_score` in `axes.py`/`regime.py` [FACT]. Optional engine
touch = additive `out["roro_<key>"]` columns in `conditions_frame` (§3) — columns, never scoring.

---

## 7. Template & insertion

**File:** `templates/dashboard.html.j2` → `site/macro.html`.

**Anchor on names, not line numbers (they drift):** insert AFTER the `#conditions` panel's closing
`{% endif %}` (`<div class="panel span12" id="conditions">`, ~line 833) and BEFORE
`<!-- ===== ACTION BOARD ===== -->` (~line 1073). Narrative order:
regime → time-machine → dislocation → conditions → **fear↔euphoria** → action board.

**i18n mechanics [C8/C9 — load-bearing]:** in-template `t(en, zh)` is a **local macro**
(`dashboard.html.j2:4`) emitting `.l-en`/`.l-zh` spans; `td(en)`/`tr(en)` are **env.globals**
(`build_site.py:1448`) → `engine.i18n.td`/`.tr`. For finite verdict/state/lean vocab use **`td()`**
so it inherits LEX canon. `td('risk-on')`/`td('risk-off')` already render `偏好风险`/`避险`
(`i18n.py:281-282`) — do NOT hardcode conflicting ZH.

**Markup** (copy `#accumulation`/`#holdings` + `#conditions` subpanels): wrapper
`<div class="panel span12" id="fear-euphoria">`; header with `help()` + the gex link; top guard
`{% if fear_euphoria %}…{% else %}<p class="muted">{{ t('Building…','构建中…') }}</p>{% endif %}`;
0–100 gauge reusing `.pgauge`/`.pends` (CSS `dashboard.html.j2:182-187`); per-leg sub-bars with
**neutral fill** `var(--muted)`; chips/bands via `<span class="pill">`/`<span class="badge">`
(no `pos`/`neg`).

**i18n labels (every string EN+ZH; dynamic vocab via `td()`):**

| Element | EN | ZH | Source |
|---------|-----|-----|--------|
| Panel title | Fear ↔ Euphoria: regime synthesis | 恐惧 ↔ 欣喜：周期综合 | `t()` |
| Gauge ends | Fear / Euphoria | 恐惧 / 欣喜 | `t()` |
| Bands | Panic/Fear/Neutral/Greed/Euphoria | 恐慌/恐惧/中性/贪婪/欣喜 | `t()` |
| Leg names | per §3 | per §3 | `t()` |
| Lean | risk-on / risk-off | 偏好风险 / 避险 | **`td()` — do NOT hardcode** |
| Chip | positioning confirms / diverges / mixed | 持仓与价格一致 / 背离 / 混杂 | `t()` |
| Fed put | Fed put present / absent | 美联储托底在位 / 缺失 | `t()` or `td('put-present')` |
| Capitulation | {n}/3 capitulation signals | {n}/3 投降信号 | `t()` |
| Dealer-gamma link | dealer gamma → | 交易商 gamma → | `t()` |

**LEX additions** in `engine/i18n.py` (so `td(dynamic)` resolves). Already present (do NOT re-add):
`unknown` (`i18n.py:65 → 未知`), `risk-on`/`risk-off`. **Add these 8:** `stand_aside→观望`,
`buyable_washout→可买入的错杀`, `put-present→托底在位`, `put-absent→托底缺失`, `calm→平静`,
`diversified→分散`, `converging→趋同`, `concentrated→集中`. Do NOT add `falling_knife`.

---

## 8. Neutrality & caveats

- **Neutralize green/red.** Gauge + per-leg bars use `var(--muted)`, never `pos`/`neg` — euphoria is
  not "good", fear is not "bad"; coloring implies a directional call. (`accumulation` legitimately
  uses pos/neg for weight deltas; this panel must not.)
- **Positioning chip is descriptive** (positioning-vs-price), not a recommendation.
- **UI caveat** (under the gauge, `t()`/`help()`):
  - EN: "Regime read, not a signal. A conditioning lens synthesizing existing risk-appetite,
    dislocation and capitulation components — it does not score direction or size positions.
    'Contrarian at extremes' is regime-dependent: fear is buyable only when the Fed put is present;
    in put-absent regimes extreme fear can be a falling knife."
  - ZH: "这是周期读数，不是信号。它综合已有的风险偏好、错杀与投降指标，提供环境视角——不评分方向、不决定仓位。
    '极端时反向操作'取决于周期：只有在美联储托底在位时，恐惧才可买入；托底缺失时，极端恐惧可能是下跌中的刀子。"

---

## 9. Tests (`tests/test_fear_euphoria.py`, mirror `tests/test_advanced_page.py`)

1. **Mapping monotonicity** — pct 0→0, 0.5→50, 1→100; increasing pct → non-decreasing fe_score.
2. **NaN/short-history guard** — series shorter than `min_periods` → helper returns `None`, no raise.
3. **Clamp** — out-of-range pct clamps to [0,100].
4. **Band cutoffs (half-open)** — `_fe_band`: 9→Panic, 10→Fear, 34→Fear, 35→Neutral, 64→Neutral,
   65→Greed, 89→Greed, 90→Euphoria.
5. **Leg shape** — exactly 7 dicts, keys `{key,name_en,name_zh,value,pct,lean}`, `pct∈[0,100]`,
   `lean∈{"risk-on","risk-off"}` (hyphen), keys == the 7 RORO leg keys.
6. **Lean sign** — synthetic high-VIX → `vix` leg `value<0`, `lean=="risk-off"`; copper/gold up → `risk-on`.
7. **Insider breadth** — mixed pos/neg/`None` `bps` → ignores None/non-finite, `(n_pos−n_neg)/n_valid`;
   all-None → 0.0, no crash.
8. **Divergence truth table** — parametrize per §4: `(washout,F,F,F,down)`→`diverges`;
   `(washout,F,F,F,up)`→`confirms`; `(F,crowded,F,sell,up)`→`diverges`; bullish+bearish→`mixed`.
9. **Display-only invariant (load-bearing)** — `"fear_euphoria" not in regime.classify(f).columns`;
   absent from `score_axis(f,"growth"/"inflation")`; static source-grep: no `fear_euphoria`/`fe_score`
   in `axes.py`, `regime.py`, or the `macro_risk_snapshot`/`_macro_risk_legs` region of `conditions.py`;
   `fear_euphoria_synthesis` imported only by `build_site.py`. (`macro_risk_snapshot` IS real at
   `conditions.py:618` — target it as a surface to stay clear of, don't assert it absent.)
10. **Template render smoke** — render with minimal `latest`+`fear_euphoria`; assert `id="fear-euphoria"`,
    both `l-en`/`l-zh` for title + 5 bands + chip; `fear_euphoria=None` → "Building…", no crash.
11. **Neutrality** — rendered block has no `class="pos"`/`class="neg"`.
12. **LEX completeness** — `td()` returns ZH (not English fallback) for all 8 new keys + `risk-on`/
    `risk-off`/`unknown`.

---

## 10. Effort & gotchas

**Effort:** ~1 focused session — helper + sub-helpers (`_fe_band`, `_fe_legs`, `_fe_positioning`,
~90 LOC), one template section (~70 LOC), 12 tests, 8 LEX additions. No collector, no scoring, no new data.

**Race-safety on macro.html (MANDATORY):** `templates/dashboard.html.j2` and `site/macro.html` are
concurrently edited by parallel sessions. **Verify via `grep` + `pytest`, NOT live preview.** Anchor
insertion on `id="conditions"` / the action-board comment, not line numbers. Do NOT commit regenerated
`site/*.html` (pages.yml is upload-only; HTML rebuilt at build time). Use a worktree or
commit-own-paths-fast to dodge a parallel `git add -A` sweep.

**Build-blockers baked into this spec:** [C1] import `pct_rank_window` from `engine.indicators`;
[C2] insider field is **`bps`** (skip None/non-finite); [C3] COT washout not persisted → recompute
+ symmetric crowded-long; [C4] guard `absorption_ratio` key absent in unknown branch; [C5] NaN
early-return before `round()`; [C9/C10] lean hyphenated via `td()`, no conflicting ZH; [C15] "N/3"
from `score`, firing names separately.

**Verified correct (no change):** dislocation enum `{calm,buyable_washout,stand_aside,unknown}`
(no `falling_knife`); southbound China/HK-only; `latest.conditions.risk_appetite.{roro,roro_state}`;
capitulation shape; `latest.dislocation.inputs.*`; render kwarg scope; `pgauge`/`pends` CSS exists;
display-only invariant; RORO sign convention; config thresholds (`roro` ±0.35,
`cot_washout_pctile` 0.10, `cot_pctile_lookback_d` 756).
