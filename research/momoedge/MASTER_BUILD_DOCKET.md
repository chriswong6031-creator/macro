# MASTER BUILD DOCKET — MomoEdge-parity Options Terminal + Prophet

> **NAMING RULING (operator, 2026-07-06):** our pick/trade-lifecycle desk is named **PROPHET** — never "Oracle", which is reserved for (a) the existing rotation lobe (`ORACLE_CONSTITUTION.md`) and (b) MomoEdge's product when discussed as the competitor. All our schemas/keys use `prophet.*` / `prophet/` (see `research/OPTIONS_SENSOR_CONTRACT.md`). "Oracle" below refers to MomoEdge's product unless it names the rotation lobe.

**Author:** Opus (synthesis pass), 2026-07-07
**Inputs read (all of `/tmp/momoedge_specs/`):** source-RE specs (`flow_spec`, `chain_heat_spec`, `gex_spec`, `gex_ui_spec`, `structural_spec`, `prism_spec`, `heatmap_spec`, `oracle_spec`, `alerts_infra_spec`, `tutorial_spec`); screenshot specs (`flow/gex/heatmap/oracle/prism/tutorial_FEATURE_SPEC`); our-stack maps (`our_terminal_map`, `our_data_contracts`); prior study `research/MOMOEDGE_ORACLE_COMPETITIVE_FEATURE_STUDY_FOR_FABLE.md`.
**Scope:** competitive parity docket driving multi-session builds. Charting-app = `/Users/chriswong/Documents/Cluade/charting-app` (Terminal, Next.js). Engines = `/Users/chriswong/Documents/Cluade/Macro Dashboard` (Macro Dashboard).

---

## 0. EXECUTIVE SUMMARY (the load-bearing findings)

1. **MomoEdge's moat is integration + a per-trade tape we do not own, not math we lack.** Their GEX engine (`gex_spec.md`), PRISM matrix (`prism_spec.md`), and structural detector (`structural_spec.md`) are re-implementations of exactly the formulas already in our `engine/gex_engine.py` / `gex_model.py` (net GEX = `oi·γ·S²·0.01`, wall = `argmax(OI·γ)`, flip = signed-GEX zero-crossing, magnet, max pain, regime). We can match all of it on the data we already produce. The **one thing we structurally cannot match** is their `trade_dir` "buy/sell" per print — it requires NBBO trade signing; our tick-rule net-sign recovery is 0.41 (coin-flip-plus), documented in `our_data_contracts.md §4`.

2. **The single highest-value net-new build is the Oracle trade-management layer, and it needs ZERO paid tape.** `oracle_spec.md` reverse-engineers their entire live-confidence engine (V1 9-factor, V2 phase-aware weighted). It scores the *state of an existing trade* (pre-trigger → triggered → T1 → T2 → overtime → invalidated) from price + geometry + macro — all inputs we have. We own none of this today. It is the biggest legible-complexity win and the cleanest to gauntlet (forward outcome ledger already a house pattern).

3. **Chain Heat is the highest-value Flow feature for our data profile.** `chain_heat_spec.md`: contract-day accumulation ≥ $3M aggregated across sub-threshold prints. It sidesteps the single-print signing problem entirely — it is a magnitude/persistence read (RELIABLE family), not a direction read. Build it from our EOD/minute aggregates.

4. **Honest-but-thinner presentation is a first-class design constraint, not a footnote.** MomoEdge asserts direction as fact (`sent`=BULLISH/BEARISH colored green/red on every card; flow "empirically predictive"). We must present the same surfaces with `direction_reliability` demoted to a caveat and **magnitude as the headline**. PRISM already gives us the honest template verbatim — their own copy says *"Sign is an assumption, not a fact. Magnitude is the reliable read."* (`prism_FEATURE_SPEC.md §4`). Adopt that framing across Flow/GEX/PRISM.

5. **Data bridge: one shared R2 options contract, two readers.** Terminal already reads `live_flow/*` and `options_hub/*` from R2 via `/api/flow` (`our_terminal_map.md §2`). A future Oracle (in Macro Dashboard, rendered to `site/`) consumes the **same** artifacts plus new `options_structure/*` state files. No second pipeline — the Neural Web ingests options-structure state as gated context sensors.

6. **Build order is right, with one amendment.** Flow → Heatmap → GEX → PRISM → Tutorial → Oracle is sound because each stage stands alone as a Terminal tab and Oracle depends on all the sensors below it. **Amendment:** land a tiny `options_event.v1` / `options_structure.v1` contract (Package A) *before* Flow, so every later surface reads one schema. It is ~1 session and prevents four divergent readers.

**Verdict on doctrine:** every new surface ships **display-only** first; LLM (Ask-Oracle / Momo) may only *narrate/de-escalate*, never originate a score; direction stays soft without NBBO; index GEX and single-name GEX are separated with the regime passport preserved; each claimed edge writes a forward ledger before any authority escalation. This is enforceable and non-negotiable per `CLAUDE.md` house laws.

---

## 1. PARITY MATRIX

Legend for gap class:
- **NOW** = buildable now on data we already produce (RELIABLE families).
- **NOW‑SOFT** = buildable now but a *direction* element is soft; ship magnitude-forward, direction caveated.
- **NEW‑DATA** = needs a new (free/cheap) pipeline we can fund at $0 or near-$0 (e.g. IV backfill via massive BS-invert, OI-prev snapshots we already store).
- **PAID‑TAPE** = requires NBBO trade signing (Databento TBBO or equivalent); a product decision, not a prerequisite.

### 1A. FLOW (live options tape)

| MomoEdge feature (source) | What we already have | Gap class | Notes |
|---|---|---|---|
| Per-trade flow cards, newest-first (`flow_spec §1`) | `live_flow/feed_current.json events[]` (poller, RTH 120s); `site/flow/<SYM>.json large_prints[]` EOD | NOW | Cadence 120s not tick; label as such. |
| `trade_dir` BUY/SELL per print, green/red (`flow_spec §4`) | `signing.direction_reliable:false`, tick-rule net recovery 0.41 (`our_data_contracts §1A/§4`) | PAID‑TAPE | **Cannot match honestly.** Present execution-context lean, not asserted side. |
| Conviction score 0–100, tiers ELITE/STRONG/HIGH/MED/LOW (`flow_spec §2`) | none (we have raw fields); grades computable | NOW‑SOFT | Build transparent `flow_score_v1` from magnitude/OI/fresh/DTE/GEX-proximity; direction component low-weight. Tiers OK; do not claim backtested per-tier edge until gauntleted. |
| Whale/Sweep/Block/Cluster/Multileg badges (`flow_spec §3`) | live poller has `sweep_clusters`; `fresh_contracts` (vol>OI) | NOW (sweep/cluster/whale-by-$), PAID‑TAPE (true Lee-Ready aggressor) | Whale=premium gate (our `large_prints`); Cluster=our chain-heat; Sweep=multi-exchange needs tape → heuristic only, label. |
| Full filter taxonomy (type/dir/score/DTE/moneyness/premium/exec/side/OI/IV/badges) (`flow_spec §6`) | all underlying fields present in `site/flow` + `options_hub` | NOW | Pure client-side filter model; `flow-filters.js` schema is a good target shape. |
| Smart Money Radar (rank by rel-activity/soi/score-prem) (`flow_spec §8`) | `feed_current.unusual_names[]` (prem_z vs 252d baseline) | NOW | Our z-score ranking is honest; adopt their weight blend as display ranking. |
| Flow Gauge (call/put prem, P/C) (`flow_spec §9`) | `site/flow/<SYM>.json` call_vol/put_vol/pc_ratio/premium_mn | NOW | Direct map. |
| Watchlist rail w/ best daily score (`flow_spec §7`) | none in Terminal; Supabase auth exists | NOW | Supabase table + localStorage mirror; our own scores. |
| Ask Oracle per-row explainer (`flow_spec §10`) | `/api/ask` exists in NW; deterministic fields all present | NOW (deterministic) | LLM narrates facts; **may not originate a score or direction**. |
| Score-expectations (per-tier hit rates) (`flow_spec §2.6`) | forward ledgers are a house pattern | NEW‑DATA (accrual) | Requires our own forward outcome accrual; display "accruing" until n≥ gate. |

### 1B. CHAIN HEAT (contract-day accumulation)

| MomoEdge feature (`chain_heat_spec`) | What we have | Gap | Notes |
|---|---|---|---|
| Contract-day campaigns ≥$3M across sub-threshold prints | minute/day aggregates + OI snapshots (`options_hub`, `data/thetadata_eod`) | NOW | Magnitude+persistence read — **signing-free**. Best data-fit feature we have. |
| side = BOUGHT/SOLD/MIXED→CONTESTED | ask/bid share available intraday; net-sign soft | NOW‑SOFT | Emit `accumulation`/`distribution`/`contested` from ask_share, not asserted side. |
| 2-min pg_cron refresh | live poller 120s cadence already matches | NOW | Same cadence; write `live_flow/chain_heat_current.json`. |

### 1C. HEATMAP (dual-layer price/flow treemap)

| MomoEdge feature (`heatmap_spec`) | What we have | Gap | Notes |
|---|---|---|---|
| Price treemap (sector-grouped, cap-sized, 1D/1W/1M/YTD) | US stock universe + OHLC in Macro Dashboard / Terminal | NOW | Sector map concepts exist repo-wide. |
| Flow layer (premium-sized, sentiment-colored) | `site/flow/index.json` per-name (net_premium_mn, pc, gamma_flow) | NOW‑SOFT | Sentiment color = soft; size by premium (RELIABLE) is the honest headline. |
| Price/flow divergence badge | both layers available | NOW | Our differentiator too: compute `price up / flow put-heavy` sign mismatch (magnitude-anchored). |
| Detail panel (sweeps/whales/unusual/IV/OI/divergence) | `site/flow/<SYM>` + `options_hub/vol` | NOW / NOW‑SOFT | Whale=premium count (NOW); aggressor sweeps heuristic. |
| Server view `heatmap_view` / `heatmap_flow_agg` | we'd build the agg in nightly render | NEW‑DATA (builder) | A new `site/heatmap/*.json` builder; no new *market* data. |
| Since-open snapshot / flips | intraday poller archive (48h) | NOW | We have hourly archive; compute flips client-side. |

### 1D. GEX (dealer gamma structure)

| MomoEdge feature (`gex_spec`,`gex_ui_spec`) | What we have | Gap | Notes |
|---|---|---|---|
| Per-strike net GEX bars, call/put split | `site/gex/<SYM>.json profile[]` + `options_hub/gex` | NOW | Same formula. |
| Gamma flip (profile-scan ±10% + cumulative fallback) | `gamma_flip`, `dist_to_flip_pct` (`gex_engine.py`) | NOW | We have flip; add profile-scan method if not present (cheap). |
| Call wall / put support (OI·γ hysteresis) | `call_wall`/`put_wall` + strength/band | NOW | Direct. |
| HVL/magnet, max pain, IV30, P/C OI | `magnet_up/down`, `max_pain`, `iv30`, `put_call_oi_ratio` | NOW | Direct. |
| Regime PIN/DRIFT/RANGE/TRANSITION/TREND/CASCADE (stability ratio) | `regime` long/short + `regime_passport` | NOW (extend) | We have 2-state; extend to 6-state named regime + `stability_pct`. **Keep passport.** |
| Gravity, pin prob, cascade/upside trigger, dealer bands | partial (`tilt`, `vol_hole`) | NOW (extend) | Add `gex_structure_state.v1` fields (Package C). |
| Snapshot diff (level shifts, OI Δ clusters, liquidity flow) | `data/cboe/gex_*.parquet` day-over-day; OI[t-1] law | NOW | We already store per-name daily GEX summary. **OI timing law already enforced** (`our_data_contracts §1D`). |
| Dealer-sign convention (calls +, puts −) | **assumption-signed**, passport, single-name fragility flagged | NOW‑SOFT | We are MORE honest here; keep display-only until GEX→forward-vol gate (~Sept 2026). |
| Market-state card + Ask-Oracle chips | none in Terminal | NOW | UI build; reads our state JSON. |

### 1E. PRISM (strike × expiration matrix)

| MomoEdge feature (`prism_spec`) | What we have | Gap | Notes |
|---|---|---|---|
| GEX lens (net $γ/1% per cell) | per-strike/expiry data in `gex_model.py surface[]` / `options_hub/gex by_strike` | NOW | Direct. |
| OI lens (call/put OI by strike×exp) | OI parquets `data/thetadata_eod/oi` | NOW | Direct. |
| VOL lens (today volume by cell) | volume in EOD store | NOW | Direct. |
| Δ-OI lens (day-over-day) | OI[t-1] snapshots (`oi_prev`) | NOW | **Our doctrine-aligned lens** — add it; MomoEdge folds this into OI Movers. |
| UNUSUAL lens (vol vs 30d per-strike median, 3× thresh) | needs trailing per-strike volume median | NEW‑DATA | Buildable from EOD store history; honest "NO HIST" fallback until baseline. |
| VEX/vanna lens (DTE-weighted) | greeks path exists but stability uncertain | NEW‑DATA / EXPERIMENTAL | Defer or label experimental (matches our `our_data_contracts §5` caution). |
| Heat Seeker pick (gates: minTotalOI 5000, ratio 1.2–1.5, DTE penalty, confidence) | none | NOW | Descriptive standout cell; **"not a recommendation"** copy (their own disclaimer). |
| OI Movers rail (new strikes ≥500 OI, |Δ|≥200) | `options_hub/oi_movers.json` already produced | NOW | We already ship this artifact. |
| Confluence SPX/SPY/QQQ (%-from-spot grid, flip/wall align) | index GEX for SPX/NDX/RUT/SPY/QQQ/IWM (`options_hub/context.json`) | NOW | Index-only = our stronger data; good fit. |
| Historical GEX scrubber (snapshot, GEX-locked) | `data/cboe/gex_*.parquet` history + `gex/<SYM> history` | NOW | We accrue this; lens-lock to GEX honest. |

### 1F. ORACLE (managed-trade signal desk)

| MomoEdge feature (`oracle_spec`) | What we have | Gap | Notes |
|---|---|---|---|
| Base signal rows (asset/thesis/entry/inval/targets/horizon) | Neural Web produces candidates; no `prophet_trade_plan` envelope | NOW (define) | Define `prophet_trade_plan.v1`. **NW originates; Oracle does not re-originate.** |
| V2 phase-aware live confidence (7 phases, weighted components) | none | NOW | **Zero paid tape.** Price+geometry+macro only. Biggest net-new win. |
| Trade-at-a-glance geometry rail (STOP/ENTRY/LIVE/T1/T2, R-units) | none | NOW | Pure geometry from plan + live price. |
| V2 diagnostics (validity/progress/pace/retention/overlay bars + change reason) | none | NOW | Legibility layer over the confidence score. |
| Tranche system (1→2 on trigger) | none | NOW | State machine. |
| Performance dashboard (equity curve, monthly/quarterly, closed alerts) | track-record artifacts exist repo-wide | NOW | Build outcome-close schema first (house rule: schema before authority). |
| Option recommendation card (OCC symbol, live premium P&L) | `options_hub` marks; OCC construction trivial | NOW‑SOFT | Live premium is delayed/EOD-ish, not NBBO — label freshness. |
| Macro regime orb (bull/neutral/bear) | strong macro/regime machinery repo-wide | NOW | Presentation win; wire our regime → orb. |
| Flow-signal auto-logging (7-gate, admin) | signing gates + `flow_signals` concept | NOW‑SOFT | Score gate uses soft direction — keep as shadow/log, not authority. |

### 1G. ALERTS

| MomoEdge feature (`alerts_infra_spec`) | What we have | Gap | Notes |
|---|---|---|---|
| Alert type matrix (13 types) + severity | none in Terminal | NOW | Supabase-backed prefs; in-app first. |
| Channels: in-app/sound/push/SMS/email | Supabase auth; push/SW buildable | NOW (in-app/sound/push), NEW‑DATA (SMS Twilio) | Email/SMS after opt-in + rate caps (their own gating is a good template). |
| Presets (focused/standard/max/critical) | none | NOW | Copy structure. |
| Quiet hours, rate caps, dedup by alertId | none | NOW | Adopt their dedup key shape. |
| Structural/flow/whale/score-90 alerts | gated on sensors below | NOW (after sensors) | Alerts can exist as display before ranking authority (house rule). |

### 1H. TUTORIAL

| MomoEdge feature (`tutorial_spec`) | What we have | Gap | Notes |
|---|---|---|---|
| 6-module guided course (coach engine, spotlight, checks, free-explore) | none | NOW | Pure client; static fixtures. |
| Per-tab lessons (Oracle/Flow/Signals/GEX/Heatmap/Risk) | maps to our tabs | NOW | Fixtures mirror our data shapes. |
| Ask-Momo AI tutor | `/api/ask` exists | NOW (deterministic-first) | LLM narrates lesson; no origination. |
| Progress gating + server completion flag | Supabase profiles | NOW | Course-before-terminal gate optional for us. |
| Preview overlays (DEFERRED in their build) | n/a | SKIP | They shipped it disabled; we can skip v1. |

---

## 2. DATA BRIDGE DESIGN — the shared R2 options contract

### 2.1 How the Terminal reads options data TODAY (verified `our_terminal_map §2`)

- Route `/api/flow?f=<param>` (`terminal/app/api/flow/route.ts`) with a 3-tier fallback: local Python (`127.0.0.1:8000`, normally down) → **R2 CDN** → local fixtures.
- R2 base: `https://pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev`.
- Live keys: `live_flow/feed_current.json`, `heat_current.json`, `meta.json`, `tide_current.json`, `dte_tide_current.json`, `tickers/<ROOT>.json`.
- Nightly keys: `options_hub/vol/<ROOT>.json`, `gex/<ROOT>.json`, `oi_movers.json`, `hot_contracts.json`, `context.json`, `oi_confirmed.json`, `tickers_ctx/<ROOT>.json`.
- Producers (Macro Dashboard, `our_data_contracts`): `live_flow_poller.py` (RTH, launchd, → R2 direct), `build_options_hub_nightly.py` (nightly CI on Mac Studio → R2 direct), `build_gex_board.py`/`build_options_flow.py` (→ `site/`, git-tracked).
- Auth: Supabase (`fsldfzlxyavsuwqbceod`); `/data/` and R2 are public (proxy matcher excludes them).

### 2.2 How a future Oracle consumes the SAME artifacts

Oracle lives in **Macro Dashboard** (rendered to `site/`, deployed via `pages.yml`), because that is where the Neural Web, forward ledgers, and validation gates already live — and because nightly is the sole advancer of forward ledgers (house law). The Terminal is the *interactive* reader; the Oracle/NW is the *sensor consumer + ledger writer*. Both read the **same R2/`site` objects**; neither forks the pipeline.

```
                          ┌──────────────────────── Macro Dashboard (engines) ─────────────────────────┐
ThetaData/Cboe/massive ──▶│ options_flow.py · gex_engine.py · options_hub.py · live_flow_poller.py      │
                          │ + NEW: options_structure.py (gex_state, chain_heat, structural detector)    │
                          └───────────┬───────────────────────────────────────────────┬────────────────┘
                                      │ writes                                          │ writes
                          ┌───────────▼────────────┐                      ┌─────────────▼──────────────┐
                          │ R2  live_flow/*         │                      │ site/  (git-tracked)        │
                          │ R2  options_hub/*       │                      │ site/gex/*  site/flow/*     │
                          │ R2  options_structure/* │◀── NEW shared        │ site/options_structure/*    │
                          └───────────┬────────────┘    contract           └─────────────┬──────────────┘
                                      │ read (public)                                     │ read (nightly)
                     ┌────────────────▼─────────────────┐              ┌──────────────────▼───────────────┐
                     │ Terminal (charting-app) /api/flow │              │ Neural Web / Oracle (site/)       │
                     │  Flow · Heatmap · GEX · PRISM tabs │              │  gated context sensors + ledgers  │
                     └───────────────────────────────────┘              └───────────────────────────────────┘
```

### 2.3 New R2 keys + JSON schemas (the shared contract — Package A)

Register in `config/synapse.yml` (Signal Bus). All carry `authority_tier ∈ {display, shadow, confirmer, scored}` and reliability flags, mirroring `site/flow` conventions.

**`options_structure/gex_state/<ROOT>.json`** — schema `options_structure.gex_state/v1`
```json
{
  "schema": "options_structure.gex_state/v1",
  "asof": "2026-07-07T20:05:00-04:00",
  "root": "SPY", "spot": 543.2,
  "net_gex_bn": 1.8, "gamma_regime": "RANGE",          // 6-state: PIN|DRIFT|RANGE|TRANSITION|TREND|CASCADE
  "stability_pct": 71, "gamma_flip": 539.0, "dist_to_flip_pct": 0.77,
  "call_wall": 550.0, "put_wall": 535.0, "magnet": 542.0, "max_pain": 541.0,
  "pin_probability": 0.34, "gravity_direction": "up", "gravity_up_pct": 63,
  "cascade_trigger": null, "upside_trigger": 548.0,
  "oi_delta_clusters": { "new_oi": [{"strike":550,"delta":4200}], "exit_oi": [] },
  "regime_passport": { "basis":"dealer-short-assumption", "structurally_constant":false,
                       "is_index_product":true, "verdict":"robust-assumption", "note":"..." },
  "authority_tier": "display",
  "reliability": { "levels":"display-only-until-gate", "regime":"assumption-signed" }
}
```

**`live_flow/chain_heat_current.json`** — schema `options_flow.chain_heat/v1` (Package B)
```json
{
  "schema": "options_flow.chain_heat/v1",
  "asof": "...", "session_date": "2026-07-07",
  "campaigns": [{
    "option_symbol": "SMH...530P", "ticker": "SMH", "type": "PUT", "strike": 530,
    "expiry": "2026-06-18", "dte": 20,
    "total_premium_mn": 11.97, "alert_count": 29, "span_minutes": 91,
    "first_seen": "...", "ask_share": 0.91,
    "lean": "accumulation",           // accumulation | distribution | contested  (NOT asserted BOUGHT/SOLD)
    "direction_reliability": "soft",  // ask_share-derived, not NBBO
    "authority_tier": "display"
  }]
}
```

**`options_structure/matrix/<ROOT>.json`** — schema `options_structure.matrix/v1` (Package E, PRISM)
```json
{
  "schema":"options_structure.matrix/v1","asof":"...","root":"NVDA","spot":844.8,
  "expiries":["2026-07-07","2026-07-18"], "strikes":[...],
  "cells":[{"strike":850,"expiry":"2026-07-18",
            "gex":34.1e6,"call_oi":12000,"put_oi":800,"call_vol":4200,"put_vol":300,
            "delta_oi":{"call":1200,"put":0},
            "unusual":{"ratio":3.4,"samples":22,"side":"unusual"}}],
  "levels":{"call_wall":900,"put_support":800,"hvl":850,"gamma_flip":840,"max_pain":845},
  "heat_seeker":{"strike":850,"expiry":"2026-07-18","lens":"GEX","standout_ratio":1.7,
                 "confidence":0.23,"note":"descriptive — not a recommendation"},
  "authority_tier":"display"
}
```

**`options_structure/structural/<ROOT>.json`** — schema `options_structure.structural/v1` (Package D)
```json
{
  "schema":"options_structure.structural/v1","asof":"...","root":"NVDA",
  "squeeze_state":"BUILDING","cascade_state":"NONE",       // NONE|BUILDING|ACTIVE
  "top_relevance_score":72,"contributing_flows":4,
  "flow_near_flip":true,"flow_near_wall":false,"dealer_regime":"TRANSITION",
  "explanation":"bullish accumulation near gamma flip in transition regime",
  "vol_ladder_suppressed":false,
  "authority_tier":"shadow","allowed_authority":"context-only-until-gauntlet"
}
```

**`prophet/trade_plan/<ID>.json`** — schema `prophet.trade_plan/v1` (Package G, Oracle)
```json
{
  "schema":"prophet.trade_plan/v1","id":"...","asof":"...",
  "asset":"NVDA","direction":"BULL","thesis":"...","source_engines":["neural_web"],
  "trigger":910,"entry":905,"invalidation":870,"targets":[950,980,1050],
  "horizon_days":90,"min_hold_days":14,"tranche":1,
  "option_contract":{"type":"CALL","strike":910,"expiry":"2026-09-19","entry_premium":5.1},
  "management":{  // computed each tick, NOT in the plan file — see prophet/state
    "ref":"prophet/state/<ID>.json"
  }
}
```
**`prophet/state/<ID>.json`** — schema `prophet.management_state/v1` (live, EMA-smoothed)
```json
{
  "schema":"prophet.management_state/v1","id":"...","asof":"...",
  "phase":"triggered_pre_t1","management_confidence":72.2,"raw_confidence":73.1,
  "delta_vs_base":6.2,"recommended_action":"hold",   // wait|enter|hold|trim|trail|exit|invalidated
  "components":{"validity":81,"progress":40,"pace":66,"retention":50,"overlay":55},
  "geometry":{"dist_to_stop_r":1.6,"dist_to_t1_r":0.8,"horizon_pct_used":41},
  "change_reason":"Trigger Confirmed",
  "confidence_ceiling":92,          // honest uncertainty cap, mirror MomoEdge
  "authority":"trade-management-only-NOT-pick-rank"
}
```

### 2.4 Terminal wiring for new keys
Per `our_terminal_map §3`: add each new `f` param to `isValidF()`/`backendPath()`/`r2Key()` in `terminal/app/api/flow/route.ts`, add a fixture, add a tab to the `TabKey` union in `OptionsHubView.tsx` (or a new `/heatmap`, `/prophet` page + `AppNav.tsx` entry). Reuse existing chart primitives (`GexStrikeLadder`, `TideChart`, `Sparkline`).

---

## 3. BUILD SEQUENCE

Order (operator-stated, amended): **[A contract] → Flow → Heatmap → GEX → PRISM → Tutorial → Oracle.**
Model routing per `CLAUDE.md`: **Sonnet builds** each package; **Opus reviews** stats/gates; **Fable (main loop) adjudicates** authority escalations. Every workflow spawn passes `model:` explicitly.

### Package A — Options Sensor Contract *(prereq, ~1 session, Sonnet)*
- **Scope:** define the five schemas in §2.3; register in `config/synapse.yml`; add example payloads derived from existing `site/flow/*.json`; add `authority_tier` + reliability fields everywhere.
- **Files (Macro Dashboard):** `config/synapse.yml` (rows), `research/OPTIONS_SENSOR_CONTRACT.md`, `engine/options_structure.py` (skeleton + dataclasses), fixtures under `site/options_structure/` + `terminal/public/data/`.
- **Consumes:** existing `site/flow`, `site/gex`, `options_hub` shapes.
- **Net-new engine:** the contract module only (no compute yet).
- **Guardrail:** contract carries reliability + tier; no scoring.

### Package 1 — FLOW tab *(Sonnet build; Opus review of score design)*
- **Scope:** three-pane Flow (watchlist rail · feed · inspector), transparent `flow_score_v1`, tiers, badges, full filter model, Smart Money Radar, Flow Gauge, Chain Heat rail (Package B folded in or immediately after), deterministic Ask-Oracle.
- **Files (charting-app):** new tab in `terminal/components/OptionsHubView.tsx` (`TabKey` += `"flow2"` or extend existing `tape`), inspector sub-component, `terminal/lib/flowScore.ts` (transparent components), `terminal/lib/i18n.ts` (EN/ZH labels — no translated `title=`), fixtures `terminal/public/data/chain_heat_fixture.json`. API: add `chainheat` `f` param to `route.ts`.
- **Consumes:** `live_flow/feed_current.json`, `site/flow/<SYM>.json`, `options_hub/vol`, `live_flow/chain_heat_current.json`.
- **Net-new engine (Macro Dashboard):** `flow_score_v1` computation in `options_flow.py` (magnitude percentile, vol/OI, fresh-positioning, DTE relevance, GEX-proximity, IV regime, **direction_reliability penalty**); Chain Heat aggregation (Package B) writing `live_flow/chain_heat_current.json` from minute/day aggregates + OI snapshots.
- **HONEST-BUT-THINNER:** MomoEdge colors every card green/red by asserted side; **we color by magnitude/tier and show direction as a low-confidence lean with a "soft — no NBBO" tooltip.** Score's directional component gets the smallest weight; `flow_score_reliability` field ("high for magnitude/OI, low for direction"). Badges: Whale=premium gate (RELIABLE), Cluster=chain-heat (RELIABLE), Sweep=heuristic (labeled), no asserted aggressor.
- **Ask-Oracle guardrail:** LLM summarizes deterministic facts (contract, premium, DTE, vol/OI, OI-Δ, GEX proximity, rarity, reliability) — **may not originate a score or a directional call.**

### Package 2 — HEATMAP page *(Sonnet build; Opus review of divergence stat)*
- **Scope:** dual-layer treemap (price + flow), sector grouping, cap/equal/premium sizing, 1D/1W/1M/YTD, MAP/TABLE, divergence badges, since-open flips, detail panel.
- **Files (charting-app):** new page `terminal/app/heatmap/page.tsx`, `terminal/components/HeatmapView.tsx` (squarified treemap SVG), `AppNav.tsx` entry + icon. API: `heatmap` `f` param.
- **Consumes:** `site/flow/index.json` (per-name premium/pc/sentiment), OHLC universe, `options_hub/vol` (IV).
- **Net-new engine (Macro Dashboard):** `scripts/build_heatmap.py` → `site/heatmap/price.json` + `site/heatmap/flow.json` (sector-agg, per-name flow premium, badge counts, divergence flag). Nightly render lane.
- **HONEST-BUT-THINNER:** size by premium (RELIABLE) is the headline; sentiment color is soft — dead-zone it aggressively (like their `|sent|<0.08` dead zone) and lead the divergence read with **magnitude** ("$X premium against a +Y% move") not asserted bull/bear.

### Package 3 — GEX tab *(Sonnet build; Opus review of regime extension)*
- **Scope:** per-strike bars, flip line, walls, magnet, 6-state regime market-state card, gravity/pin/cascade, snapshot diff, Ask-Oracle chips. Embeddable (iframe or native tab).
- **Files (charting-app):** extend GEX tab in `OptionsHubView.tsx` (reuse `GexStrikeLadder`, `GexExpiryBars`), market-state card component; or native `/gex` page mirroring MomoEdge's embed pattern.
- **Consumes:** `site/gex/<SYM>.json`, `options_hub/gex/<ROOT>.json`, `options_structure/gex_state/<ROOT>.json`.
- **Net-new engine (Macro Dashboard, Package C):** extend `gex_engine.py`/`gex_model.py` to emit `options_structure.gex_state/v1`: 6-state regime + `stability_pct` (posGex/(posGex+|negGex|) within ±20% spot), gravity, pin probability, cascade/upside triggers, dealer bands, snapshot diff clusters. Profile-scan flip method if not already present.
- **HONEST-BUT-THINNER:** **preserve `regime_passport`.** Single-name GEX regime is a near-constant product attribute (`structurally_constant`), NOT a time-varying signal — say so in the card. Index GEX (SPX/SPY/QQQ) gets the "robust assumption" treatment; single names get the fragility caveat. All levels **display-only until GEX→forward-vol gate (~Sept 2026)**; the card shows "levels map, not validated forecast."

### Package 4 — PRISM tab *(Sonnet build; Opus review of Heat Seeker gates + UNUSUAL baseline)*
- **Scope:** strike×expiry matrix, lenses GEX/OI/VOL/Δ-OI (+ UNUSUAL when baseline ready; VEX experimental/deferred), Heat Seeker pick, OI Movers rail, max pain, index Confluence, historical scrubber.
- **Files (charting-app):** new tab/page, matrix component (distribution-aware tier ramp per `prism_spec §4`), Heat Seeker gate logic client-side, `LENS_KEYS` shortcuts.
- **Consumes:** `options_structure/matrix/<ROOT>.json`, `options_hub/oi_movers.json` (already produced), `options_hub/context.json` (index GEX for Confluence), `site/gex history` (scrubber).
- **Net-new engine (Macro Dashboard, Package E):** `options_structure.py` matrix builder from EOD store (strike×expiry GEX/OI/VOL/Δ-OI cells); UNUSUAL requires a **trailing per-strike 30d volume median** (NEW‑DATA, buildable from EOD history) with honest `NO HIST` fallback and `MIN_SAMPLES`; Heat Seeker gates (minTotalOI 5000, standout ratio 1.2–1.5, DTE penalty, confidence=(ratio−1)/3).
- **HONEST-BUT-THINNER:** adopt MomoEdge's *own* honest copy verbatim as our doctrine: **"Sign is an assumption, not a fact. Magnitude is the reliable read."** and **"descriptive — not a recommendation."** Δ-OI lens is our most doctrine-aligned (measured, signing-free) — feature it. Defer VEX or mark EXPERIMENTAL (greeks-path stability unproven, per `our_data_contracts §5`).

### Package 5 — TUTORIAL *(Sonnet build; low review need)*
- **Scope:** 6-module guided course (coach engine, spotlight, checks, free-explore), lessons mirroring our tabs, deterministic-first Ask-Momo, progress + completion flag. Skip the DEFERRED preview overlay.
- **Files (charting-app):** `terminal/app/learn/page.tsx`, `terminal/lib/coach.ts` (`coach.start/say/check/forceNext/unlockNext`), `terminal/lib/learnFixtures.ts` (static data mirroring OUR shapes), per-lesson components. Supabase `user_onboarding` completion column.
- **Consumes:** static fixtures only (zero live endpoints — matches their design).
- **Net-new engine:** none.
- **HONEST-BUT-THINNER:** rewrite lesson copy to OUR epistemics — GEX lesson teaches "levels map, sign assumed"; Flow lesson teaches "magnitude reliable, side soft"; keep the confidence-pillar lesson (progress/pace/retention/market) since that maps to the Oracle we build next. Ask-Momo narrates; never originates.

### Package 6 — ORACLE + ALERTS *(Sonnet build core; Opus review of confidence model + bounds; Fable adjudicates authority)*
- **Scope (Oracle):** `prophet_trade_plan.v1` envelope; V2 phase-aware management confidence (7 phases, weighted components, phase bounds, EMA smoothing, ceiling 92); trade-at-a-glance geometry rail; V2 diagnostics bars + change-reason; tranche 1→2; performance dashboard + outcome-close schema; option card w/ live premium; macro orb.
- **Scope (Alerts, Package H):** 13-type matrix, in-app/sound/push channels, presets, quiet hours, rate caps, dedup by alertId. Structural/flow/whale/score-90 alerts as **display**, not ranking authority.
- **Files:** Macro Dashboard `engine/prophet_management.py` (V2 confidence, writes `prophet/state/<ID>.json`), `scripts/build_prophet.py` (nightly plan + performance ledger); charting-app Oracle page + alert-prefs UI + Supabase alert tables.
- **Consumes:** Neural Web candidates (plan origination), live price, macro/regime, all options-structure sensors from Packages B–E as **context/risk overlays**.
- **Net-new engine (Macro Dashboard):** the whole management-confidence engine (no paid tape); forward outcome ledger (schema-before-authority).
- **HONEST-BUT-THINNER / doctrine:** **This is a trade-MANAGEMENT score, explicitly NOT a Neural-Web pick rank** (their own split; preserve it). LLM/Oracle **may not originate a signal or escalate** — NW originates candidates, Oracle manages, LLM narrates. Options-flow/GEX/structural sensors enter as **context-only → confirmer → filter → rank-contributor**, each step gated by a pre-registered forward ledger (house law). Confidence ceiling preserved (uncertainty is honest). Performance dashboard ships its outcome schema **before** the surface is labeled "authority" — never a track record without a pre-registered ledger.

---

## 4. EPISTEMICS GUARDRAILS (apply to every package)

Where MomoEdge asserts confidence we can't back, the honest alternative:

| MomoEdge claim | Our honest alternative | House-law basis |
|---|---|---|
| `trade_dir` = definitive BUY/SELL, green/red per print; "flow empirically predictive" | Direction is a **soft lean** (tick-rule recovery 0.41); headline = **magnitude/OI/premium** (RELIABLE). `direction_reliability` field + tooltip on every card. | `our_data_contracts §4`; direction soft without NBBO. |
| Conviction score with backtested per-tier edge (bullish predictive) | Transparent `flow_score_v1` with **component bars**; tiers descriptive; **no per-tier edge claim until a forward ledger passes** ("accruing" state). "Validated" is CI-enforced — never use it pre-gate. | `scripts/check_validated_claims.py`; display-only until gauntleted. |
| GEX regime as live directional signal (single names) | GEX **levels map, display-only** until GEX→forward-vol gate (~Sept 2026); single-name regime = `structurally_constant` product attribute, not a signal; **regime passport preserved**; index vs single-name separated. | `our_data_contracts §1B/§4`; index-vs-single-name GEX. |
| Oracle picks stocks + manages, one score | **Two scores, kept separate:** NW originates pick-rank; Oracle computes management-confidence. LLM narrates only — **may not originate signals, scores, or escalations.** | LLMs may only de-escalate calibrated keys; NW ownership of origination. |
| Heat Seeker "pick" reads like a recommendation | Descriptive standout cell; ship **their own** disclaimer: "descriptive — not a recommendation." | display-only doctrine. |
| Same-day OI in computations | **OI[t-1] only** (OPRA t-1 parquet); Δ-OI features point-in-time; entry decisions use latest fully-available snapshot. | `our_data_contracts §1D` OI timing law. |
| Live per-print sweep/aggressor | Sweep = labeled heuristic; true Lee-Ready aggressor = PAID‑TAPE only, not claimed. | intraday direction soft. |
| Confidence can approach certainty | Preserve the **ceiling (92)**; nulls printed not hidden; each new sensor writes a forward ledger before any positive rank authority. | pre-registered gates; nulls printed. |
| New surface = authority | New surfaces ship **display → shadow → confirmer → scored**, each transition gated; nightly is the sole ledger advancer; intraday lanes discard `data/` writes. | authority tiers; ledger law. |

Bilingual (EN/ZH) UI required; **no translated text in `title=` attributes** (CI-guarded). Every new artifact registered in `config/synapse.yml` with tier + reliability before a reader consumes it.

---

## 5. OPEN QUESTIONS FOR THE OPERATOR

1. **Paid tape decision.** Databento TBBO for a focused universe (~$0 under signup credit per `our_data_contracts §5 gaps`) would upgrade Flow direction from soft to reliable and unlock true sweep/aggressor. Fund it now for a **narrow validation use case** (does signed direction add forward edge?), or stay EOD-honest indefinitely? Everything in this docket ships without it — this only affects whether Flow direction ever graduates from "soft."

2. **Oracle candidate origination.** The Oracle management layer needs base trade plans. Confirm: **Neural Web is the sole originator** (Oracle never re-picks), and NW already emits enough structure (entry/inval/targets/horizon) to populate `prophet_trade_plan.v1` — or do we need an NW change to emit that envelope? This gates Package 6 scope.

3. **Terminal vs Macro Dashboard home for Prophet UI.** Engines + ledgers live in Macro Dashboard (nightly, `site/`). The interactive Prophet *desk* could render there (`site/prophet.html`) OR as a Terminal tab reading R2. Recommend: **engine + ledger in Macro Dashboard; UI as a Terminal tab** (consistent with Flow/GEX). Confirm.

4. **UNUSUAL lens baseline funding.** The PRISM UNUSUAL lens + Flow rarity scores need a **trailing 30d per-strike volume median** built from EOD history (NEW‑DATA, $0 but a build). Priority — ship PRISM with GEX/OI/VOL/Δ-OI first and add UNUSUAL when the baseline accrues, or block PRISM on it? Recommend: **ship without UNUSUAL, add later** (their own "NO HIST" fallback is the honest pattern).

5. **Alerts channel scope for v1.** In-app + sound + web-push are $0. SMS = Twilio (cost + consent/verification flow). Email = deferred (they shipped it disabled). Confirm v1 = **in-app/sound/push only**, SMS/email as a later opt-in package.

6. **Watchlist / account scope.** Flow watchlist + alert prefs + course completion all want Supabase tables. Confirm we extend the existing Terminal Supabase project (`fsldfzlxyavsuwqbceod`) rather than standing up new infra.

7. **Chain Heat threshold.** MomoEdge uses a flat ≥$3M contract-day gate. For our thinner universe, a **liquidity-adjusted percentile gate** (per-symbol) may surface more without noise. Flat $3M for v1, or percentile from the start? (Reversible; recommend flat $3M v1 for legibility.)

---

*End of docket. Full per-surface detail lives in the source specs; this document is the sequencing + contract + guardrail spine that drives the multi-session build.*
