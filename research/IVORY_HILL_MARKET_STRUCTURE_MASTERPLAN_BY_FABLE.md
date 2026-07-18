# Market Structure & Systematic Positioning (MSP) — Ivory Hill Gamma Report intake, adjudicated plan of record

Status: **CHARTERED** by operator order 2026-07-18 (screenshot docket "New Folder With Items 36.zip",
31 captures of Ivory Hill's Gamma Report, spanning ~2026-05-29 → 2026-07-17, + Codex research docket
`IVORY_HILL_GAMMA_REPORT_SITE_FEATURE_SUMMARY.md`).
Adjudicated by Fable (main loop) against `docs/ACTIVE_BUILD_MAP.md` (2026-07-18, no file collisions),
`research/DO_NOT_REBUILD.md`, and three deep repo surveys (options/Terminal infra, NW context-lobe
anatomy, overlapping surfaces). Rulings are MSP-R1..R10; waves are MSP-W1..W6.

**Program in one sentence:** absorb the Gamma Report's four lenses (options pricing, mechanical
flows, participation, portfolio translation) as *display-tier surfaces + one new NW context lobe*,
reusing the deep options infrastructure we already run (687-name GEX stack, ThetaData 2012+ store,
COR-family since 2006) — and reject the one lens (composite regime → tactical ETF allocation) that
duplicates our authority chain and violates the positioning-fusion law.

---

## 0. The headline finding of the intake audit

Ivory Hill's data plane is a strict subset of ours. We already collect or compute ~70% of what
their dashboard shows — much of it deeper (per-strike GEX for 687 names vs their SPX/SPY blend;
COR1M **and** COR3M/DSPX since 2006; ThetaData chains to 2012; a whole-market dealer surface with a
2017→2026 backfill merged **yesterday**, #2787). What they have and we lack is almost entirely
**(a) two cheap deterministic engines** (vol-control proxy, CTA proxy — both derivable from closes,
therefore backcastable decades deep, which their charts cannot do), and **(b) display surfaces** —
we have engines with no renderer (options_surface W2, COR1M, VIX futures curve, gamma-flip history)
where they have renderers with shallower engines. This intake is therefore mostly a *rendering and
context-wiring* program, not a data program. That is the cheapest kind of win we get.

---

## 1. Feature-by-feature verdicts

Verdict vocabulary: **BUILD** (new engine/surface) · **UPGRADE** (existing surface gains the idiom)
· **RENDER-GAP** (engine exists, page missing — build display only) · **REJECT-REDUNDANT** (already
built or in flight) · **KILL** (forbidden; registry row appended).

| # | Ivory Hill feature | Verdict | Disposition |
|---|---|---|---|
| 1 | Expected-move dashboard (per-ticker ±1σ/±2σ daily+weekly bands) | **UPGRADE** | Data fully exists (`expected_move` in all 687 `site/gex/*.json`). Build the band *visual*: Terminal per-ticker EM panel (W6) + `gex.html` EM band hero (W6). |
| 2 | Live price vs EM levels w/ level toggles + gamma flip overlay | **UPGRADE** | Terminal build consuming existing `options_hub/gex/<ROOT>.json` + `levels.v1` named-level board (#2710 — built for exactly this; do NOT invent a second level feed). |
| 3 | SPX weekly EM card ("locked Friday, held through week") | **BUILD** (small) | "SPX Week Map" panel: weekly EM bands + flip + event markers, locked-at-close semantics disclosed. Home: `market_structure.html` hero strip + `gex.html`. |
| 4 | Dealer gamma flip (level + history vs spot) | **RENDER-GAP** | Flip computed nightly and *stored daily* in `data/cboe/gex_SPX.parquet` (spot, flip, net_gex, IV30 per row). Chart it (W2). |
| 5 | Net GEX history ($B bars, regime-colored) | **RENDER-GAP** | Two feeds already exist: `data/cboe/gex_<SYM>.parquet` + `engine/options_surface.py` W2 aggregates (20 roots, 2017→2026 via #2787) — **no page renders either**. The new page is that renderer (W2). |
| 6 | Realized-vol regime (RV21 vs RV63 crossover) | **BUILD** (display chip only) | Trivial from closes. Display-tier chip + history sparkline. NEVER a scored leg — `vol_regime`'s gauntleted composite (ts_slope/MOVE/VRP) is the authority read; the crossover is a plain-words context frame (MSP-R4). |
| 7 | Vol-control exposure `AUM×min(1, 10%/max(RV21,RV63))` + daily flow | **BUILD** | New `engine/systematic_flows.py`. Deterministic from SPX closes → full multi-decade backcast on day one (they can't). Honest model-estimate framing per Design Law 5. |
| 8 | CTA positioning (vol-normalized 20/50/100/200d trend) + daily flow | **BUILD** | Same engine, same honesty. Representative-model disclosure on Tier 2. |
| 9 | Systematic Positioning Index (CTA+VC fused z-score) | **BUILD-MODIFIED** | No fused numeric composite is exported anywhere (MSP-R3). Ship the two models side-by-side + a plain-word **agreement state** (`aligned_adding / split / aligned_cutting`). |
| 10 | Breadth % >200dma with 60/40 thresholds | **REJECT-REDUNDANT** | Full overlap: `collectors/breadth.py` + `engine/advanced_breadth.py` + `advanced.html`. No build. |
| 11 | Short-dated vol term structure (≤22 DTE) w/ event overlay | **BUILD** | "Event-Vol Map": per-expiry SPX ATM IV/straddle from ThetaData EOD store, event markers joined from Release Radar. Display-only under RIC-R3 (W4). |
| 12 | Econ event calendar × per-event option IV / priced move / P/C | **UPGRADE** | RIC W4 EVW (#2780) already owns the event-window read; Release Radar owns the calendar. Add the missing column: options-priced ±move for the event-date expiry (ATM straddle). Lands on `radar.html` release cards + Event-Vol Map (W4). |
| 13 | Cboe COR1M implied correlation (regime, 1y change, percentile) | **RENDER-GAP** | COR1M/COR3M/DSPX collected since 2006; used as radar Tier-B leg (`corr_floor_break`) but **zero display surface**. Dispersion panel on the new page (W2). Do not re-derive the radar leg (MSP-R5). |
| 14 | Sector rotation scatter (11 SPDRs, quadrants + trail arrows) | **UPGRADE** | RRG scatter component already shipped twice (`intl.html`, `subsector_rotation.html`). Add a Rotation Map *view* to `sector_central.html` over the 11 SPDRs, colored by XSR fast-lens states (W5). NOT a schedule surface — the `sector_rotation_schedule.v1` kill (registry §1) is about parallel rotation-*timing* surfaces; this is a same-page display re-projection of data the page already ranks. |
| 15 | Momentum universe (~500-stock 1d×5d scatter, search, top-N) | **BUILD** | Data = breadth closes cache (all S&P constituents). Canvas scatter on `us_stocks.html` with ticker search + Terminal deep-links per dot (W5). |
| 16 | Index impact tables (return × weight contributors) | **BUILD** | Nothing like it exists. "What moved the index" duo-table: `us_stocks.html` panel + one-line movers chip on `macro.html`. Weight = float-cap approximation, disclosed Tier 2 (W5). Concentration *context* stays display; MLC program owns leadership authority. |
| 17 | Composite regime scorecard + tactical ETF allocation (SPLV/SPHB/SPXL) | **KILL** | Duplicates the `risk_radar → market_state → regime_vector` authority chain (deepest-engineered part of the repo) and the strategy layer (SPVector maps regime→SPY allocation with a real backtest). Fusing gamma/positioning keys into a regime score restates the Signal-Commons **positioning-fusion ILLEGAL** ruling. Registry row appended (MSP-R2). |

---

## 2. Rulings (MSP-R1..R10)

- **MSP-R1 — Program frame.** All MSP output ships display-tier + context under the standing
  epistemics law: nulls never block building or accrual; the gauntlet applies only at promotion to
  rank/size/gate authority. Every MSP artifact carries `display_only: true`,
  `tier: display`, `horizon_role: context`, all five authority booleans false.
- **MSP-R2 — Composite-regime/tactical-allocation clone KILLED.** No MSP surface may fuse gamma +
  vol + flow + breadth into a regime verdict, and no MSP surface maps any regime to ETF
  allocations. The US risk band has one owner (`engine/risk_radar.py` → `market_state`); allocation
  translation has one home (strategies layer). Row appended to `research/DO_NOT_REBUILD.md` §1.
- **MSP-R3 — No fused positioning score, anywhere.** The Systematic Positioning Index is absorbed
  as *two* separate model reads plus a categorical agreement enum. No combined numeric z is
  exported in any artifact key, NW lobe, or page (a chart may show both lines; it may not print a
  blended number). This keeps the display honest and makes accidental future fusion grep-able.
- **MSP-R4 — Vol-control/CTA/RV-crossover are model-estimate context, not signals.** Tier-1 copy
  must frame them as estimates of *mechanical* behavior ("machine money", "autopilot funds"), with
  the assumption receipt (AUM, target, windows) on Tier 2. Promotion of any MSP construction to a
  radar leg requires a fresh prereg through the RSR/RIC lanes; the shadow ledgers of W3 exist to
  make that prereg cheap later, not to imply authority now.
- **MSP-R5 — No re-derivation of existing authority legs.** COR1M floor-break is already a
  gauntleted Tier-B radar leg; GEX regime already feeds `gex_confirm`; breadth thresholds already
  live in `advanced_breadth`. MSP renders these; it never recomputes or re-thresholds them.
- **MSP-R6 — Event surfaces stay calendar-agnostic on the risk path (RIC-R3 restated).** The
  Event-Vol Map and priced-move column are display context only. No MSP output may gate, dampen, or
  escalate any risk channel by calendar window.
- **MSP-R7 — One level feed.** Terminal/site EM-band and gamma-level displays consume
  `levels.v1` (#2710) and existing `options_hub`/`site/gex` payloads. Building a second
  named-level or expected-move feed is forbidden — extend the existing publishers.
- **MSP-R8 — Deterministic engines only.** VC/CTA/RV/impact/momentum computations are pure price
  arithmetic. No LLM touches any MSP number (LLMs may only de-escalate calibrated keys — house law).
- **MSP-R9 — Full-history backcast at birth.** Because W1 engines derive from closes, the builder
  must emit the complete history series (SPX closes reach decades back), not forward-accrue-only.
  This is our structural advantage over the intake source; don't waste it. (OI-dependent series —
  GEX/flip — remain accrual-bound to their stores; disclose series birth on Tier 2.)
- **MSP-R10 — Forward ledgers are lane-gated at birth.** Any MSP state ledger (gamma-regime days,
  VC/CTA flow states, EM-band breaches) uses the canonical `COLLECT_LANE` writer gate from day one
  (#2598/#2712 class). Nightly is the sole advancer; render/intraday lanes read only.

---

## 3. Placement map

**New page — `market_structure.html` ("Market Structure"), Options & Flow nav submenu (W2).**
The market-*level* structure surface the repo lacks (gex.html is per-ticker). Panels:

1. **Hero — the absorb/amplify read.** State-keyed aurora hero: gamma regime in plain words
   (Tier 1: "Dealers are absorbing moves — dips tend to get bought by hedging flows" /
   "Dealers are amplifying moves — swings can run further than usual"), distance to flip,
   days-in-regime, one stance line. Mechanics + 70/30 SPX/SPY-style detail → hover.
2. **Dealer gamma history.** Net GEX $B bars (regime-colored) + SPX-vs-flip line chart — the
   `options_surface` W2 renderer (2017→2026 depth) with the `cboe/gex_SPX` daily series.
3. **Systematic flows desk.** VC exposure vs SPX (full backcast), CTA positioning vs SPX, the two
   daily-flow bar charts (5/10/20/30/90d toggles, IH's best idiom — theirs to steal), agreement
   chip. Plain-word framing: "Machine money: adding / split / cutting".
4. **Dispersion & correlation.** COR1M with regime band + 1y delta + percentile, COR3M/DSPX
   companions, "one-stock market vs stock-picker's market" plain-word frame.
5. **Vol weather annex.** RV21-vs-RV63 crossover chip + VIX futures curve (M1–M6, accruing feed,
   honest young-series disclosure) + link out to the gauntleted vol_regime read on gex.html.
6. **SPX Week Map.** Weekly EM bands + flip + event markers, locked-Friday semantics.
7. **Event-Vol Map** (W4 panel): ≤22-DTE SPX term structure with event overlays + priced-move table.

**Existing-page placements:**

| Surface | Gets | Wave |
|---|---|---|
| `radar.html` (Release Radar cards) | options-priced ±move chip per high-impact event | W4 |
| `us_stocks.html` | Momentum Universe canvas scatter + Index Movers impact duo-table | W5 |
| `macro.html` | one-line "what moved the index" movers chip (links to us_stocks table) | W5 |
| `sector_central.html` | Rotation Map scatter view (11 SPDRs, XSR-state-colored, trails) | W5 |
| `gex.html` | per-ticker EM band visual on the detail panel + flip-history sparkline | W6 |
| **Terminal** (charting-app repo) | per-ticker Expected Move panel (bands over intraday price, level toggles, flip from levels.v1) on ticker search | W6 |

**Neural Web:** new context lobe `market_structure` (below), plus wiring the existing-but-orphaned
`market_gamma` engine read into world_state through it.

---

## 4. New NW context lobe — `market_structure`

Follows the 12-file checklist from the transmission/fx precedents (engine module → builder →
`config/daily.yml` step → synapse.yml entry → SIGNAL_BUS regen + pin bump → world_state
`_compose_market_structure()` → mastermind LOBE_SUMMARIZERS + `_LOBE_TO_ARTIFACT_IDS` → brief block
+ `_SLA_HOURS` → confluence `_MACRO_SUBTYPES` node → lobe prose + `nw_lobe_desc_audit.py --update`).

- Artifact: `data/market_structure/latest.json`, schema `market_structure_context.v1`,
  `asof_field: asof`, cadence `daily-engine`, SLA 30h, `tier: display`, `horizon_role: context`,
  `weights: none`, `scored_path_surfaces: []`, `external_consumers: [mastermind:context]`.
- Keys (all display-only): `gamma` {regime, net_gex_bn, net_gex_pctile, dist_to_flip_pct,
  days_in_regime}; `systematic` {vc_alloc_pct, vc_flow_5d_bn, vc_state, cta_z, cta_flow_5d,
  cta_state, agreement}; `dispersion` {cor1m, cor1m_regime, cor1m_1y_delta, cor1m_pctile_2y,
  dspx}; `vol` {rv21, rv63, rv_cross_state, vix_curve_slope}; `event_vol` {next_event,
  event_priced_move_pct} (W4); `state_changes` (≤6 diffs, same-day-idempotent prev_state pattern);
  `is_context_only: true`.
- Per MSP-R3 there is **no** fused positioning key. Per MSP-R5 the lobe re-projects
  `market_gamma`/`cboe` stores — it does not recompute radar legs.
- Standing-law constant added in `mastermind_context.py`: positioning keys are context;
  fusion into any score is ILLEGAL (Signal Commons restated).
- Dedupe note: existing `options_weather` lobe = per-root *entry-timing* aggregates over 30 sector
  ETFs; `market_structure` = market-level dealer/flow/dispersion state. Disjoint jobs; both cite
  each other in synapse notes to keep future sessions from merging or duplicating them.

---

## 5. Signals & modeling derivation (display-first; promotion via prereg only)

Accrual/ledger work that makes future preregs cheap (all lane-gated per MSP-R10, all shadow):

- **L-1 Gamma-regime ledger** — days-in-regime, regime flips, SPX forward returns stamped at flip
  (context for a future "amplification window" prereg; GEX Tier-B radar leg already exists — any
  new construction goes through RSR lanes).
- **L-2 Systematic-flow ledger** — daily VC/CTA state + agreement enum + forward returns. The
  interesting prereg-shaped question: does `aligned_cutting` during negative gamma lead drawdown
  extension at the registered radar horizon? Not testable without accrual → accrue now.
- **L-3 EM-band breach ledger** — daily closes outside ±1σ/±2σ (band computed from prior-day IV):
  breach frequency by vol regime is a calibration read on the options market itself, and a natural
  fragility context frame. Display: "moves have been running past what options priced N of last 20
  days".
- **L-4 Event priced-vs-realized ledger** (W4) — per release: options-priced ±move vs realized
  move. Feeds MRI's surprise-anatomy work; display: "the market paid for a big CPI move and got a
  small one, 4 of the last 5 times".

Explicit non-goals (already killed or owned elsewhere): options DOI family (DEAD), skew-decel
(UNSUPPORTED), charm narratives (KILLED), calendar-gated risk legs (RIC-R3), rotation×cycle
confluence (DON'T-TEST), any tactical-allocation surface (MSP-R2).

---

## 6. Design directives (binding on W2/W4/W5/W6 builders)

`docs/DESIGN_DOCTRINE.md` is law; this section is its application plus what the intake screenshots
are worth stealing.

**Steal from Ivory Hill (their genuinely good idioms):** the NET BUYER / BULLISH / UPTREND badge
stack on flow charts (state words, not numbers, at the top); formula-as-subtitle transparency
(`AUM × min(1, 10% / max(RV21, RV63))` printed small under the title — ours goes in the `?`
hover); per-level toggle chips on EM charts; locked/held timestamp semantics ("Locked Fri 16:27 ET
· held through Friday close"); window toggles (5/10/20/30/90d) on flow bars; regime-colored bars.

**Surpass them (our design language, applied):** aurora-glass panels + state-keyed hero glow
(macro/vector family conventions); breathing accents scoped to active elements only (compositor
law from the nav work); bilingual dual-span everywhere with `data-tip-en/zh` (never `title=`);
plain-word Tier-1 stance lines on every panel (their dashboard has zero stances — that is our
single biggest UX edge over them); light/dark parity from day one; mobile-first grid collapse;
localStorage-persisted per-panel window/level preferences ("customizable"); hover receipts with
assumption disclosure. Charts are hand-rolled SVG (site convention — Plotly is retired, #2823) and
**canvas** for the 500-dot momentum universe (SVG will not survive 500 labeled nodes + hover on
mobile; use a quadtree hit-test + top-N labeling like the heatmap family).

**Trap sheet for builders (all recurred ≥2× in repo history):** no `t()`/`td()` spans inside
`<svg><text>` (renders empty — the svg-span-breakout LETHAL class); no bilingual markup in
`title=`/`placeholder` attributes; new JS files ship with `?v=` cache-busters and bump on every
content change; `.stf-*` class prefix is owned by stocktable.js; paired template/site plain-copy
assets need `python -m scripts.check_template_site_sync --fix`; builders producing >32k output die
— split page builds into sections; `selectattr`-on-null Jinja crashes abort build_site — guard
every new context read; ZH tint/color conventions (红涨绿跌) apply to any new gauge; keep new-page
body top padding (nav-gap CI).

**Tier-1 vocabulary pre-clearance** (Law 2): "dealer gamma", "GEX", "z-score", "vol-control",
"CTA", "COR1M", "±1σ" are all Tier-2/3 words. Tier-1 equivalents to use: "shock absorbers on/off",
"expected daily range", "machine money adding/cutting", "one-stock market vs stock-picker's
market", "the range options paid for". EN/ZH pairs to be finalized in W2 copy review.

---

## 7. Waves (PR map)

| Wave | Scope (one PR each unless split noted) | Depends on |
|---|---|---|
| **W1 — Data spine** | `engine/systematic_flows.py` (VC + CTA + RV crossover + agreement enum, config-parameterized, full backcast per MSP-R9) + `scripts/build_market_structure.py` → `data/market_structure/latest.json` + `history.parquet`; readers for `cboe/gex_SPX` flip/GEX history, COR family, vix_curve; ledgers L-1..L-3 (lane-gated); dag.yml + tests. No UI. | — |
| **W2 — The page** | `market_structure.html` (panels 1–6 of §3) + nav registration (Options & Flow, aurora-glass conventions) + bilingual copy + mobile + light/dark; template↔site sync; render-guard tests. | W1 |
| **W3 — NW lobe** | 12-file checklist for `market_structure` lobe (§4): synapse entry + pin bump + SIGNAL_BUS regen, world_state compose, mastermind summarizer + standing-law constant, brief block + SLA, confluence macro node, lobe prose `--update`. | W1 |
| **W4 — Event-Vol Map** | theta-ops-lane builder: per-expiry SPX ATM IV/straddle (≤22 DTE) + Release Radar event join → Event-Vol panel on `market_structure.html` + priced-move chip on `radar.html` cards + L-4 ledger + `event_vol` lobe key. Display-only per MSP-R6. | W1, W2 |
| **W5 — Participation pack** | Momentum Universe canvas scatter + Index Movers tables (`us_stocks.html`) + `macro.html` movers chip + Rotation Map view on `sector_central.html` (XSR-colored, reuse RRG component). Splittable into 2 PRs (us_stocks vs sector_central). | — (parallel) |
| **W6 — Expected-move surfaces** | `gex.html` per-ticker EM band visual + flip-history sparkline + SPX Week Map card; **cross-repo lane**: Terminal per-ticker Expected Move panel (charting-app repo) consuming `options_hub/gex` + `levels.v1` (MSP-R7). | W1 (Week Map); Terminal lane independent |

Render-budget note: every W1 compute is pandas-on-closes (seconds); the only heavy join (W4
ThetaData straddles) runs on the theta-ops lane off the render path, committing a small artifact.
Page renders add ~1 template each. No R2 dependencies beyond payloads Terminal already reads.

Ops note: `data/cboe/gex_SPX.parquet` daily-summary depth and the #2787 surface backfill differ in
span; W2 charts must join honestly (series-birth disclosure on Tier 2, no silent splice).

---

## 8. Registry action

Appended to `research/DO_NOT_REBUILD.md` §1 in this PR (per append convention, with regenerated
compiled blocklists): Ivory-Hill-style composite market-regime scorecard + tactical ETF allocation
surface — REJECT-REDUNDANT + forbidden fusion path (MSP-R2).
