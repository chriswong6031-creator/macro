# Risk State + Early-Drawdown Layer + Opus Risk Overlay — Design Doc

**Status:** design (incremental build in progress on `feat/risk-layer`)
**Author:** risk-layer initiative, 2026-06-23
**Trigger:** On 2026-06-23 a memory/semiconductor bubble unwound (SMH −7%, DRAM −14%,
Nasdaq −3%). The dashboard's headline risk read stayed *green* into the peak, and the
downstream Mastermind Opus Brain books — which take their data, signals, baskets,
narrative-rotation and stock recommendations directly from this dashboard — stayed long.
The signals that *should* have warned were either absent, buried, or never reached the brain.

---

## 1. The failure, precisely

This dashboard is **rich in risk *components* but poor in risk *loudness*, and the one
top-level gauge it owns is structurally blind to a price/positioning/vol blow-off.**

Three independent facts, all verified in the source:

1. **The only top-level risk gauges are credit/recession-weighted.**
   `macro_risk_score` (`engine/conditions.py:714`, weights `engine/conditions.py:657`) and
   `drawdown_risk` (`engine/conditions.py:284`, components hard-coded to
   `recession_risk, nfci, ebp, hy_oas`) contain **zero** breadth, vol-term-structure,
   dealer-gamma, extension/parabolicity or positioning legs. A narrow, complacent,
   extended, dealer-long-gamma-pinned market with calm credit scores **low** on the
   headline. This is the root cause of "the risk signals were too weak."

2. **The correct detectors already exist — but are orphaned.** They are computed,
   then explicitly marked *"DISPLAY-ONLY, never scored,"* rendered as mid-page chips,
   and **not passed to the brain in actionable form**:
   - `conditions.complacency` (`engine/conditions.py:598-631`) literally computes the
     2026-06-23 setup: a **calm surface** (cheap VIX + steep contango) over **weakening
     internals** (index near 1y high while `%>200dma` is in a low percentile) plus **HY
     credit quietly widening** → `state="hidden_fragility"`, `warning=True`. No alert, never scored.
   - `advanced_breadth.divergence` / `tier_gap` (`engine/advanced_breadth.py:178,254`)
     emit `bearish_div` / `narrowing`. *"DISPLAY-ONLY, never scored."*
   - Dealer gamma — the literal mechanism that turns a −2% into a −7% — is computed
     (`engine/gex_engine.py:_gamma_flip`, `engine/gex_model.py:gamma_profile`,
     `volatility_hole`) but lives only on `gex.html`, raises a single `warn` alert, and
     **`master_brain` never ingests it**.
   - Per-name `parabolic` / `cohort_stretch` (`engine/extension.py:58,169`) — display chips.

3. **The only loud top-of-page banner fires too late.** `engine/dislocation.py` floats a
   banner (`#dislocation{order:-1}`) only when a dislocation is *already live* — VIX panic,
   >10% drawdown, VRP extreme, or backwardation already printing. It is a falling-knife
   *filter*, not a pre-warning. On 2026-06-23 it would have lit up *as* the crash, not before.

**Net:** the dashboard didn't lack the signals — `complacency.state="hidden_fragility"`,
`breadth_div`, per-name `parabolic`, and (on gex.html) a deteriorating gamma posture were
all likely printing. They failed because **none of them (a) feed a top-level risk state,
(b) raise a loud alert, or (c) reach the Opus brain.** The fix is **fusion + loudness +
brain-wiring**, not mostly new math.

### Audit table

| Dimension | Exists? | Module | How loud (1–5) | Reaches brain? | Verdict on 2026-06-23 |
|---|---|---|---|---|---|
| Complacency / hidden-fragility | ✅ | `conditions.py:598` | 2 (mid-page chip) | partial (1 leg) | **was firing, inaudible** |
| Breadth divergence / narrowing | ✅ | `advanced_breadth.py:178,254` | 2 | ❌ | **was firing, inaudible** |
| Dealer gamma flip / short-gamma / vol-hole | ✅ | `gex_engine.py`, `gex_model.py` | 3 (separate page) | ❌ | **firewalled from brain** |
| Extension / parabolicity (per name) | ✅ | `extension.py:58,169` | 2 | ❌ | was firing, inaudible |
| VIX term structure (contango→backwardation) | ✅ | `conditions.py:531` | 3 | partial | coincident (silent pre-peak) |
| VRP / SKEW (vol complacency) | ✅ | `conditions.py:518,534` | 2 | partial | maybe, never escalates |
| HY OAS spike / 21d widening | ✅ | `conditions.py:338`, `alerts.py` | 4 (act on spike) | partial | lags an equity-led peak |
| HYG−TLT credit-ETF momentum | ❌ | — | — | ❌ | **MISSING** |
| Net liquidity / real rates / DXY | ✅ | `regime.py`, `conditions.py` | 3 | partial | slow tide; not the tell |
| Funding stress (SOFR/repo) | ✅ | `funding_stress.py` | 1–2 | ❌ | calm; not the tell |
| VVIX / vol-of-vol | ⚠️ shallow | `data/yahoo/_VVIX` (~26 rows) | — | ❌ | **MISSING (deep)** |
| Within-equity concentration (top-N share) | ❌ | — | — | ❌ | **MISSING** |
| **Top-level equity-internal RISK STATE** | ❌ | — | — | ❌ | **MISSING — the keystone gap** |
| Top-level macro risk (credit/recession) | ✅ | `conditions.py:714,284` | 3–4 | ✅ | **stayed green (blind to blow-off)** |
| Dislocation banner (post-hoc) | ✅ | `dislocation.py` | 5 | ✅ | fires *as* the crash, not before |

---

## 2. Design principles

1. **Don't touch the validated quad.** The growth/inflation regime model, `macro_risk`,
   and `drawdown_risk` are calibrated/split-half-validated. We add a **new, additive,
   parallel layer**, never re-weight the validated gauges. (House rule; also the
   AVGO/NVDA-override post-mortem lesson.)
2. **Fuse what exists before building new.** The keystone (`risk_state`) is mostly a
   *fusion* of already-computed, currently-orphaned detectors. New collection is the
   exception (HYG−TLT ratio, deep VVIX), not the rule.
3. **Early > coincident.** Weight **leading/positioning** legs (complacency conjunction,
   vol complacency, breadth divergence, dealer short-gamma, extension/parabolicity)
   heavily; weight **slow/credit/recession** legs lightly. This composite must *lead* the
   existing credit-weighted gauge, not echo it.
4. **Loud by construction.** A top-level RISK STATE with a flashing/loud banner that fires
   *before* a dislocation, plus alerts, plus a brain-visible field. The current failure
   mode is subtlety; the antidote is a single unmissable state.
5. **Brain-visible, but honest.** Unlike most leaves here (`is_context_only:true`), the
   risk state is *meant* to change brain behavior — that is the whole point. But we are
   honest leg-by-leg about what is **measured** vs **heuristic**, and we keep selection
   alpha out of it (the brain's de-risk response is sizing, not stock-picking).
6. **Sizing, not selection, for the de-risk response.** Per the validated
   narrative-rotation finding (basket momentum rank-IC≈0; the edge is the absolute-trend
   *drawdown* gate), an elevated risk state routes to **de-grossing / de-risk / "down-size,
   don't fade the leader"**, never to a new selection score.
7. **Never fatal.** Every new leaf returns plain data or `None` and never raises; the
   daily CI build must not break. LLM passes are gated, default-off, and degrade to a
   `degraded_reason` artifact when no key is present.

---

## 3. Architecture overview

```
                          data/ (parquet) + site/*.json
                                     │
   ┌─────────────────────────────────┼──────────────────────────────────────┐
   │ engine.run()  → data/regime/latest.json                                  │
   │   conditions / dislocation / turning_point / cross_asset_confirm /       │
   │   macro_risk  (UNCHANGED validated gauges)                               │
   │                         │                                                 │
   │   ▼ NEW  engine/risk_state.py  ── fuses the orphaned detectors ──▶        │
   │        latest["risk_state"] = {score, state, drivers, legs, alert, ...}   │
   └─────────────────────────────────┼──────────────────────────────────────┘
                                      │
   ┌──────────────────────────────────┼─────────────────────────────────────┐
   │ NEW engine/mtf_monitor.py  (Phase 3)                                     │
   │   monthly/weekly/daily/4h technical grid over indexes + asset classes +  │
   │   all 11 sector ETFs → site/riskdata/mtf_monitor.json; feeds a           │
   │   "technical breakdown count" leg back into risk_state (one-build lag)    │
   └──────────────────────────────────┼─────────────────────────────────────┘
                                      │
   ┌──────────────────────────────────┼─────────────────────────────────────┐
   │ NEW engine/risk_brain.py  (Phase 4, Opus, gated, default-off)            │
   │   reads the deterministic evidence pack (risk_state + mtf_monitor + GEX  │
   │   + breadth + extension + narrative_rotation + baskets + stock wobbles)  │
   │   → risk narrative + can SUGGEST turning/retiring signals/themes/        │
   │   narratives + domino/contagion flags → site/riskdata/risk_brain.json    │
   │   + a risk_directive folded into the Mastermind handoff                  │
   └──────────────────────────────────┼─────────────────────────────────────┘
                                      │
   ┌──────────────────────────────────┼─────────────────────────────────────┐
   │ Surfacing (Phase 2): templates/dashboard.html.j2 loud RISK banner +      │
   │   engine/alerts.py new rules (risk_state_elevated, hidden_fragility,     │
   │   gex_short_gamma, breadth_divergence)                                   │
   │ Consumers (Phase 5): baskets / narrative_rotation de-gross overlay;      │
   │   standout entry-quality (coordinate w/ in-flight MACD-bottom work)      │
   └─────────────────────────────────────────────────────────────────────────┘
```

The **contract the Mastermind brain reads** is extended in three places:
1. a new top-level `risk_state` object in `data/regime/latest.json` (the file
   `master_brain._macro_summary`/`_macro_backdrop` already reads) — the loud, early state;
2. `site/riskdata/mtf_monitor.json` — the multi-timeframe technical grid + `technical_intensity`;
3. `site/riskdata/risk_brain.json` — the daily Opus risk read + the CODE-clamped de-risk
   `directive` (sizing posture, never selection), graded forward via `data/risk_brain/theses.jsonl`.

---

## 4. Phase 1 — `engine/risk_state.py` (the keystone)

A fused, **equity-internal, positioning/vol/breadth-led** market risk state that *leads*
the existing credit/recession gauge. Pure function of already-lagged fields + a couple of
cheap parquet reads. Never raises.

### 4.1 Legs

Each leg returns an **intensity in [0,1]** (0 = benign, 1 = max stress) plus an
`available` flag and a short human `detail`. Legs are combined as a renormalized weighted
mean (same `_combine_legs` idiom as MRS), then mapped to 0–100.

| Leg | Source (already in `latest` unless noted) | Intensity definition | Class |
|---|---|---|---|
| `complacency` | `conditions.complacency.state` | hidden_fragility→1.0, watch→0.6, calm→0.25, neutral→0 | **leading** |
| `breadth_div` | `conditions.complacency.breadth_div` (+ `advanced_breadth` if available) | True→1.0 (index near highs, weak %>200dma) | **leading** |
| `vol_structure` | `conditions.risk_appetite` | backwardation→1.0; else complacency: (VRP rich & VIX pctile low)→0.5; SKEW pctile high→+0.25 (capped) | mixed |
| `dealer_gamma` | `site/gex/index.json` SPY/SPX (prior build, one-build lag) | short-gamma/negative net-GEX→1.0; spot below flip→0.7; vol-hole→+0.2 | **leading** |
| `credit` | `conditions.complacency.hy_oas_chg_21d_bp` + NEW HYG−TLT ratio 20d roll | HY 21d widening→0.5; HYG/TLT ratio rolling-down→+0.5 | coincident |
| `extension` | `engine/extension.cohort_stretch` over the standout board (read published board, one-build lag) OR NEW market-froth read | `stretched`→1.0, `elevated`→0.5 | **leading** |
| `turning_point` | `latest.turning_point.state` | active turn → 0.6 modifier | confirm |
| `cross_asset` | `latest.cross_asset_confirm.caution_flags` | each caution flag → small add | confirm |
| `macro_backdrop` | `latest.macro_risk.score` (the validated credit/recession gauge) | score (0–1) × **low weight** | slow/anchor |

**Weights** (config-driven, `engine.risk_state.weights`): leading legs dominate. Default
sketch: `complacency 1.0, breadth_div 0.9, dealer_gamma 0.9, extension 0.8, vol_structure
0.7, credit 0.6, turning_point 0.4, cross_asset 0.3, macro_backdrop 0.3`. Tunable; the
*shape* (leading ≫ slow) is the design commitment.

### 4.2 Output schema (`risk_state.v1`)

```json
{
  "schema": "risk_state.v1",
  "asof": "2026-06-23",
  "score": 0-100,                       // higher = more drawdown risk
  "state": "risk-on|neutral|caution|elevated|risk-off",
  "label": "Elevated drawdown risk",
  "headline_en": "Calm surface, fragile internals: …",
  "headline_zh": "…",                   // bilingual (house convention)
  "drivers": [ {"key","label","intensity","weight","detail"} ],  // sorted by contribution
  "legs": { "complacency": {...}, "vol_structure": {...}, ... },
  "alert": true,                        // → loud banner + alert rule
  "n_legs": 7,
  "reader_contract": "De-gross / favor entries over chasing leaders / honor stops.",
  "is_context_only": false,             // this one is MEANT to move the brain
  "disclaimer": "Conjunction-based early-warning composite; legs vary in validation — see RISK_LAYER_DESIGN.md §8."
}
```

### 4.3 State bands

`risk-on <20 · neutral 20–40 · caution 40–60 · elevated 60–80 · risk-off ≥80`
(config `engine.risk_state.bands`). `alert=True` at `elevated`+. The banner copy escalates
with the state; drivers list the specific firing legs so the warning is *legible*, not just a color.

### 4.4 Wiring

- Insert in `engine/run.py` immediately after the `macro_risk` block (after the
  `latest["macro_risk"]=…` assignment, before `playbook`), same `try/except … never fatal`
  idiom, so `playbook` and downstream consumers can read it and it is written into
  `latest.json` at the existing `open(p/"latest.json","w")`.
- Config block `engine.risk_state` (weights, bands, thresholds) added to `config.yml`
  — additive, never touches existing keys.
- Tests: `tests/test_risk_state.py` — synthetic `latest` dicts exercising each leg, the
  2026-06-23-shaped fixture (calm+fragile→elevated/risk-off), graceful degradation when
  legs missing, monotonicity (more firing legs → higher score), and the band/label map.

### 4.5 Honesty (carried into the doc and the UI tooltip)

This is a **conjunction-based early-warning composite**, not a validated alpha. Leg status:
- **Measured:** `drawdown_risk`-style macro stress (the anchor leg) and HY-OAS spike.
- **Heuristic / context:** complacency (low VIX is persistent and ~neutral on forward
  returns *alone* — the value is the *conjunction* with weak breadth + widening credit),
  vol-structure complacency, extension. The composite earns its keep by (a) firing the
  conjunction loudly and early, and (b) routing the response to **sizing/de-risk**, where
  the trend-gate edge is real — not to a new selection score.
The UI states this; the brain receives it as a *risk posture*, not a buy/sell list.

---

## 5. Phase 2 — Loud surfacing (banner + alerts)

- **Top banner** in `templates/dashboard.html.j2`: an early RISK-STATE banner that floats
  above the hero (like the dislocation banner's `order:-1`) and pulses/flashes when
  `risk_state.state` ≥ `elevated`, with the drivers list inline. Distinct from — and fires
  *before* — the dislocation falling-knife banner. Color + intensity scale with the state.
  (Avoid the known DOM gotcha: never put i18n `t()`/`nm()`/`help()` macros inside HTML
  attributes — use the attribute-safe `td()`/`tr()` fns.)
- **New alert rules** in `engine/alerts.py` (registered in the `evaluate` list):
  - `risk_state_elevated` (act-tier) — `risk_state.score` crosses into `elevated`/`risk-off`.
  - `hidden_fragility` (warn→act) — promotes the orphaned `conditions.complacency` warning.
  - `gex_short_gamma` (warn) — dealer regime flips to short-gamma / spot below flip.
  - `breadth_divergence` (warn) — `advanced_breadth.divergence` bearish + `tier_gap` narrowing.
- A compact RISK-STATE chip on the other regional hubs (china/hk) reading their own
  conditions where available, or the US read as a global-risk backdrop.

---

## 6. Phase 3 — `engine/mtf_monitor.py` (multi-timeframe technical grid)

Reuse the **existing leak-aware MACD/MTF toolkit in `engine/cycles.py`** — do *not*
re-implement MACD:
- `mtf_snapshot(close, kind)` → `{D, 3D, W, M}` per-timeframe MACD/RSI/StochRSI flags.
- `_tf_turning_up(s)` → per-TF MACD-histogram-bottom detector (and its inverse for tops).
- `bottom_confidence(...)`, `entry_quality(...)`, `washout(...)` for confluence.
- Asset-class ladders already exist: `basket_mtf.py`, `btc_mtf.py`, `commodity_mtf.py`,
  `forex_mtf.py`. The `4h` index-ETF intraday infra exists (claude/4h-index-etfs lineage).

**Universe:** major indexes (SPY/QQQ/IWM/DIA), asset classes (BTC, Gold=`GC=F`, Oil=`CL=F`,
Rates via TLT + DGS10, USD via DXY), and **all 11 sector ETFs** (XLB…XLY).
**Timeframes:** monthly / weekly / daily / 4h (half-daily) where intraday is available.
**Detects:** breakdowns (loss of weekly/monthly support, MA cross-down), bearish
divergences (price higher-high vs MACD/RSI lower-high), and momentum *rolls* (MACD
histogram rolling over from a peak on the higher timeframes) — i.e. the **top** mirror of
the existing bottom detector.

**Outputs:** `site/riskdata/mtf_monitor.json` (a grid the dashboard renders as a
heat-table: rows = symbols, cols = timeframes, cell = state/warning) + a scalar
`breakdown_count` / `rolling_count` summary that feeds a **technical** leg into
`risk_state` on the next build (one-build lag, documented). Display-first; the scalar feed
is bounded and additive.

---

## 7. Phase 4 — `engine/risk_brain.py` (Opus daily risk overlay)

Modeled on `engine/narrative_brain.py` (the cleanest Claude/Opus example): OAuth-first
client, model `claude-opus-4-8`, prompt-cached stable rubric, tolerant JSON parse
(`catalyst_tone._extract_json`), a **CODE clamp** the prompt cannot override, gated +
default-off, never raises, output is **falsifiable + logged** to a JSONL ledger for later grading.

**Job:** a daily Opus pass that performs explicit **risk analysis** on top of the engines
and can **change / suggest / retire** signals, themes and narratives *on turns*:
- Inputs (deterministic evidence pack, evidence-id'd, no holdings): `risk_state`,
  `mtf_monitor`, GEX posture, breadth internals, extension/froth, narrative_rotation +
  baskets (what's crowded/extended), macro/credit/liquidity reads, options/GEX, momentum
  impulses, and **individual stocks wobbling** (the standout board + per-name flags) with
  **domino/contagion** reasoning (e.g. memory→broad semis→AI capex→Nasdaq).
- Outputs (context for the human + a bounded directive for the brain):
  `{risk_read, state_change, themes_to_retire[], narratives_to_turn[], contagion_chain[],
  risk_directive, theses[] (falsifiable, logged)}`. The `risk_directive` is the only field
  that touches the brain, and it is a **posture** (de-gross %, favor entries, avoid chasing
  X), clamped in code, never a stock list.
- Wiring: `site/riskdata/risk_brain.json` + a `risk_directive` summary folded into
  `data/regime/latest.json.risk_state.brain` and the allocation `ai_handoff`, so the
  Mastermind books "are run daily by Opus with clear risk analysis," not only by engines.
- New step in `daily.yml`'s engine job (copy the `narrative_brain` step block, default-off
  until the config flag + `CLAUDE_CODE_OAUTH_TOKEN`/`ANTHROPIC_API_KEY` are set).

---

## 8. Phase 5 — Reduce wrong signals + better entries

**Problem:** baskets are ranked purely by 20-day relative return vs SPY
(`engine/baskets.py:262`) and narrative rotation by momentum + an absolute-trend gate
(`engine/narrative_rotation.py`). Both systematically **buy strength and chase leaders**;
there is no oversold/pullback ranking pathway, and the standout board ranks by `alpha_z`
(residual momentum) within urgency tiers (leader-favoring). This feeds the brain into
chasing crowded sector leaders.

**Changes (sizing/de-risk, not selection — per the validated finding):**
1. **Risk-state de-gross overlay** on baskets + narrative rotation: when `risk_state` ≥
   `elevated`, the rotation/basket cards surface a de-risk message and a smaller suggested
   gross (route `risk_state.score` into the existing `basket_alloc`/`gross_overlay`
   sizing path), and the "accumulate the leader" verdicts down-size rather than escalate.
   "Cap it, don't fade it" stays — but the cap tightens with risk state.
2. **Crowding/extension made loud at the basket level**: surface `theme_crowding` +
   `theme_extension` as a visible *fragility* tag on the rotation leaders (not just a
   buried chip), so "only AI is rising" reads as *concentration risk*, not just leadership.
3. **Better entries / reuse the MERGED MACD-bottom alignment engine.** The
   "combined weekly + 3-day + 1-day MACD bottoms" standout rework is **already merged to
   main** as **macro#474 (`69810dca6`)** — `engine/cycles.mtf_alignment` (weekly
   not-falling + 3-day nearing-cross + daily just-crossed/imminent/early) + `ladder.alignment`
   + `engine/setups.alignment_gate` + `rank_setups(align_map=)`, gating all four standout
   strips (us/china/hk/ca) so they stop surfacing falling knives. We **do not** rewrite or
   duplicate this. We:
   - **Reuse `engine/cycles.mtf_alignment`** as the canonical entry-quality / bottoming
     read everywhere we need one (the `extension`/froth leg's *inverse*, the
     `mtf_monitor` cells, the basket entry surfacing) — there is no `combined_macd_bottom`
     to write; it exists.
   - Ensure the **entry-quality / alignment** read is *surfaced* on baskets and the
     act-now desk, so cheap/good-entry single stocks appear alongside leaders.
   - Keep selection out of `risk_state`; risk routes to sizing only.

**Coordination note:** the standout *ranking key* and the alignment engine
(`engine/setups.py`, `engine/cycles.mtf_alignment`, `scripts/build_site.py` standout
block, per-country library builders + their templates/JSON) are **already on main** (#474)
— reuse, don't touch. This initiative stays in:
`engine/risk_state.py`, `engine/mtf_monitor.py`, `engine/risk_brain.py`, `engine/alerts.py`
(new rules), `engine/run.py` (one insertion), `templates/dashboard.html.j2` (banner),
`config.yml` (additive blocks), and a *thin, opt-in* de-gross hook in the basket/rotation
sizing path. Before editing any standout/basket ranking file, re-check
`git log origin/main..` and active worktrees for collisions.

---

## 9. Data inventory & gaps

**Buildable now (deep history):** VIX + term (VIX3M/VIX9D) + ratio, SKEW, MOVE, full credit
OAS, HYG/LQD/TLT, net liquidity (WALCL/RRP + `data/treasury/tga.parquet`), SOFR/repo, DXY,
real rates (DFII10), full UST curve, breadth (all tiers), sector ETFs (XL*), BTC, Gold
(`GC=F` futures — *no GLD*), Oil (`CL=F`), OFR FSI + NFCI, NAAIM, COT, GEX summary
(`site/gex/index.json`).

**Gaps to fill (in priority order, each its own small PR):**
1. **HYG−TLT ratio momentum** — trivial derived series from existing parquet; new
   `risk_state` credit leg + a panel. *(Phase 1/5.)*
2. **Deep VVIX** — only ~26 shallow rows; implement the config-specified CBOE collector
   (mirror `CboeSkewAdapter`). Enables a vol-of-vol complacency leg. *(later.)*
3. **Within-equity concentration** — top-N mega-cap share of index / breadth-weighted
   divergence. New light metric; strengthens the breadth leg. *(later.)*
4. **Put/call depth** — current series is thin/forward-accruing; lower priority.

GEX per-strike *history* is not backfillable (point-in-time OI) — accept the daily
summary + one-build lag for the dealer-gamma leg.

---

## 10. Validation & honesty plan

- Keep the validated quad / `macro_risk` / `drawdown_risk` **byte-identical**.
- `risk_state` ships as **decision-support**, loud and brain-visible, with a leg-by-leg
  measured-vs-heuristic disclosure in the doc and UI. We do **not** claim it is validated alpha.
- Backtest the composite honestly where data allows: does `risk_state ≥ elevated` precede
  elevated forward drawdown (P(≥X% / N-day) vs base rate, with CIs and the
  survivorship/look-ahead caveats already standard here)? Use the existing
  `engine/validation.py` machinery. Publish the result in `reports/`. If a leg fails to
  add lift, it stays as *display* and drops out of the *score* (FDR-style discipline).
- The Opus overlay's theses are logged to a JSONL ledger and graded forward, like the
  other desks — its track record is accountable, not assumed.

---

## 11. Build / rollout order

1. **Phase 1** — `engine/risk_state.py` + tests + `engine/run.py` wiring + `config.yml`
   block. (Keystone; everything else consumes it.) ← *start here*
2. **Phase 2** — loud banner in `dashboard.html.j2` + new `alerts.py` rules. (Makes it visible.)
3. **Phase 3** — `engine/mtf_monitor.py` + `site/riskdata/mtf_monitor.json` + a grid panel
   + the technical leg back into `risk_state`.
4. **Phase 5 (sizing parts)** — de-gross overlay on baskets/rotation; surface
   crowding/extension fragility; shared `combined_macd_bottom` helper; entry-quality
   surfacing (coordinated, non-colliding).
5. **Phase 4** — `engine/risk_brain.py` Opus overlay + `daily.yml` step (default-off) +
   Mastermind `risk_directive` handoff. (Last, because it consumes 1–3 and 5.)
6. Data gaps (HYG−TLT first, then VVIX, concentration) interleaved as each leg needs them.

Each phase is its own PR, fully tested, green suite, and verified in the preview where it
renders. Work on `feat/risk-layer` off `origin/main` in a clean worktree; always
`git diff origin/main` before committing (avoid the detached/behind-checkout gotcha).
Remember: merge ≠ live — generated HTML refreshes only when the daily `engine` job commits
its outputs.
