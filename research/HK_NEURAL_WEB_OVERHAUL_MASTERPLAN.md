# Hong Kong Dashboard — Neural Web Overhaul Masterplan (v1, orchestrator)

**Author:** Claude (Opus 4.8, orchestrator/planner role) · 2026-07-08
**Trigger:** missed the 2026-07-08 Alibaba (+12.5%) / HK-tech multi-day rebound on both the macro page (`hk.html`) and the stock board (`hk_stocks.html`).
**Inputs digested:** Codex handoff `HK_MARKET_STRUCTURE_AND_NEURAL_WEB_UPGRADE_FOR_FABLE.md`; the resolved `HK_CANADA_STOCKS_MASTERPLAN_BY_FABLE.md` (Fable, 07-03); `HK_DATA_AUDIT.md`; a 13-agent verify+research+red-team workflow (inventory of all 18 HK engines, staleness root-cause via git forensics, HK microstructure + data-feasibility web research, adversarial review).
**Status:** display-tier plan for review. No edits shipped. This corrects, keeps, and extends the Codex plan; it does not rubber-stamp it.

---

## 0. TL;DR verdict on the Codex study

**Codex's diagnosis is ~1/3 sound and 2/3 mis-premised.** It correctly identified that the page was serving stale data and correctly refused to "lower the Alibaba threshold" — but it fused a **proven, recurring OPS bug** with a speculative **12-engine DESIGN buildout** under a "Neural Web" banner, letting one N=1 event license the scope. Three independent lanes (git forensics, diagnosis red-team, organ red-team) reached the same verdict: **July 8 broke on an ops bug + one narrow design gap, not on missing engines.**

**The single biggest correction:** Codex's most load-bearing factual claim — *"Alibaba 9988.HK is omitted from the tech fingerprint / is not tracked"* — **is false.** 9988.HK is in `config.hk.names`, the Internet & Tech basket, and four data stores (`hk_stocks/9988.HK.parquet`, `hk_search/closes_deep.parquet`, `hk_valuation/by_name.parquet`). It didn't appear on 07-08 because the data was frozen at 2026-07-02 **and** because the risk-off overlay boarded every name out (`eligible: 0`). Not because it was untracked.

**What the overhaul actually is:** a **truth/ops fix + low-cost engine deltas** as the spine, then a **broad, data-first buildout** of the context organs (ADR overnight bridge, washout-ignition detection, CBBC leverage map, scheduled-catalyst calendar, HKEXnews filing bus, narrative) — all shipping display-tier and accruing forward ledgers from day one so the brain has labeled data to learn from. The episode-unit pre-registration (§9) is the **promotion exit gate for actionable signals — not a gate on building**.

## 0.5 Operator doctrine (2026-07-08) — build first, gauntlet at promotion only

Binding steer from the operator, correcting a pattern that repeatedly obstructed prior sessions:

- **Collect data + build infrastructure FIRST; study later.** The Neural Web becomes intelligent by amassing a whole universe of contextual data points from which patterns/confluences later emerge. A brain with no accrued data has nothing to study, compare, or find confluence in. Prior Fable/Opus sessions failed by rushing to premature failed studies instead of building the contextual substrate.
- **The gauntlet is a PROMOTION gate, never a build gate.** Every organ here ships display-tier freely. Nulls never block building or accrual.
- **Confluence retention.** A factor that is null as a *standalone* signal is **kept as a confluence input** — it can help confirm other signals when they align. Non-standalone ≠ worthless.
- **Kills are construction-specific; the ranking goal stays open.** "No residual HK stock-selection alpha" bounds the *tested constructions*, not the objective. We keep generating new constructions and we will find a way to rank it.
- **Ignition tuning = aggressive early calls** (operator's choice): fire early bottom-ignition calls, accept more false starts, log every one to the forward ledger. The falling-knife demote gate stays as a *risk chip* on the card, not a silencer.

Encoded in `CLAUDE.md` §House-laws/Epistemics and memory `context-accrual-fundamental-goal`.

---

## 1. The corrected diagnosis — why July 8 was missed

### 1.1 Root cause is an OPS bug (git-forensic, confirmed on `origin/main`)

Two stacked pipeline defects froze the HK data at **2026-07-02** while the page rendered as if live:

1. **`data/hk_breadth/_closes_cache.parquet` is in `.gitignore` (line 46) yet is *tracked* in git.** So `git add data/` stages it on every run regardless of currency. `daily.yml` restores this cache (+ `data/hk_stocks/`) from the GitHub Actions cache at job start (lines 60–81) before running the non-Asia group.
2. **`git pull --rebase -X theirs` on both the daily data-collect and daily engine-output push steps.** In rebase semantics `-X theirs` means *our (local, stale) patch wins on conflict*. The daily engine step pushes ~08:39 UTC — after asia-close starts (08:30 UTC) — and the stale 07-02 cache, staged as a patch, overwrites the fresh 07-07/08 asia data.

**Evidence chain (verbatim commits):** `38dc031b11 "data: daily collection 2026-07-07"` reverted `9988.HK.parquet` (68299→68187 bytes) and `_closes_cache.parquet` back to 07-02; `cc8cc59189 "render: site re-render 2026-07-08"` (08:18 UTC, *before* asia-close) shows `hk_standouts.json` `as_of=2026-07-02`. The stale cache poisons everything downstream via `_closes_cache → compute_hk_global_betas → betas["as_of"] → scoreboard["as_of"] → standouts["as_of"]`.

This is the **same recurring failure class** the shop already has memory of: `asia-close staging-gap freezes data`, `render resurrects stale site text` (`-X theirs`), and the `price-store freshness gate #1917` — **which only covers US `SPY`, not HK `^HSI`.**

### 1.2 One narrow DESIGN gap: the `eligible: 0` blackout

Even with fresh data, the board would still have been silent on Alibaba: in a Risk-off regime the overlay applies `stress=0.7` and gates **every** name out of the standouts board (`eligible: 0`). No surviving watchlist means no downstream organ can surface anything. This is a design gap — **but it is not one of Codex's 12 organs.**

### 1.3 A second design gap: no pre-confirmation middle state

The per-name state machine (`engine/cycles.py`) is a lagging ladder: a deep-decline name is hard-excluded from the bottoming-alignment strip (`_ALIGN_BAD_STATES` @ `cycles.py:1934`) and from board assembly (`_entry_ok` @ `build_hk_library.py:1141`, `if c.get("cycle_blocked"): return False`). The only route out of `DECLINE` is `swing low → BOTTOM WATCH → TURN SIGNALED → FRESH BUY`, each a **1–5 day lag** after the price inflection. There is no state that fires on *washout depth + external capitulation evidence* **before** the daily cycle turns. That is the real "can't front-run the bottom" hole.

> **Codex got the label wrong here too:** it claimed Alibaba read *"Extended — wait for a pullback"* on 07-03. That is an **overbought-TOP** label (`stock_score.py:1082`, RSI≥70). A declining name gets `DECLINE/DOWNTREND`. Codex conflated the downside-block with the upside-block — opposite gates.

### 1.4 The honest frame (for the operator)

The way you actually front-run an HK-tech turn is **not** a better stock-selection ranker — the shop's own red-teamed gauntlet killed HK selection alpha (0 GO; §12). Web microstructure research confirms it: **the genuine antecedents of a July-8-class move are exogenous** — a US-session ADR move and a policy/regulatory catalyst — while endogenous HK microstructure (southbound, A/H, breadth) mostly *describes the move as it propagates.* So the honest "front-run" product is three mechanical/dated things: **(a) the ADR overnight tape** (BABA closed +12.5% in the US *before* HK opened — the one feed that would have literally shown it), **(b) washout-ignition detection** (catch the turn 1–2 days before the lagging ladder), and **(c) a dated scheduled-catalyst calendar.** Everything else is context that earns its keep only through a forward ledger.

---

## 2. What already exists (correcting Codex's inventory)

Codex inventoried ~8 HK engines; the repo has **18**, plus mature data stores. Eight engines Codex never mentioned:

| Existing engine (unmentioned by Codex) | What it already does |
|---|---|
| `hk_liquidity_regime.py` | **Peg-liquidity conditioner** (EASY/TIGHT/NEUTRAL from AggBal percentile; −21% vs −49% maxDD). This is Codex's "funding pulse" — already built, ACCRUE-graded. |
| `hk_market_drivers.py` | **8-driver cross-asset attribution engine** with per-driver evidence legs, confidence, invalidation, append-only grade-back log. This is Codex's "force stack" backbone. |
| `hk_signal_stack.py` | Consolidated cross-subsystem signal stack (regime+risk+liquidity+peg+RORO+drawdown+drivers) with scored-vs-context tiers. |
| `hk_stock_signals.py` | **Full per-name conviction engine** (southbound accum_z + A/H value z + beta-neutral RS + regime-fit + SFC short chip). Codex treats per-name signals as greenfield. |
| `hk_global_beta.py` | Per-stock Vasicek-shrunk global-risk beta, regime-conditioned (amplifier/cushion/exposed/favored). |
| `hk_fundamentals.py` | Per-name Piotroski/quality/consensus/archetype profile. |
| `hk_event_calendar.py` | Tri-plane macro event calendar (HK/US/CN) with `high_impact_strip()`, `imminent_line()`. |
| `hk_property.py` | Centaline CCL residential cycle context. |

**Data feeds Codex called "missing" that already exist:** SH/SZ southbound channel split (`data/hk_connect/southbound_{sh,sz}.parquet`, nightly), per-stock southbound holdings (`data/hk_southbound/holdings.parquet`), US real yields (`data/fred/DFII10.parquet`), USDJPY (`data/intl/USDJPY_X.parquet`), ADR/ETF inputs (`data/yahoo/{BABA,KWEB,FXI}.parquet` — engine wiring is the only gap), CNH (`data/china/CNH_F.parquet`). The stock board already shipped (Fable 07-03): the **hard freshness gate** on basket tailwinds, the **ripe-list contract** (entry-open / setting-up groups + entry windows), the **placement/dilution demote gate** (`data/hk_placements/events.parquet`), the **A/H matched-pair panel** (25 pairs), **SFC shorts** (153/157 coverage), the **HSCI expanded universe** (537 names), and the **falling-knife demote gate**.

**Genuinely absent (Codex correct):** intraday fast path; company-level HKEXnews event bus (only 3 placement categories captured today); news/GDELT sentiment; HKEX IPO telemetry; a **HK trading calendar** (`lib/hk_calendar.py` does not exist — `lib/nyse_calendar.py` is the template).

---

## 3. Design principles (binding)

Inherited from `HK_CANADA_STOCKS_MASTERPLAN` §2 + house laws, plus this program's additions:

1. **Truth before cleverness.** No organ ships until the freshness/ops bug is fixed and a page cannot render stale silently.
2. **Extend before build.** 5 of 6 "partial" organs are a thin sub-layer on existing code (reuse maps in §6). Build-new only where nothing exists.
3. **Two products, named.** `hk.html` (macro regime page) and `hk_stocks.html` (stock board) are distinct render-modes of one template. Every organ states which product it serves.
4. **Exogenous-lead honesty.** Instrument the mechanical/dated leads (ADR tape, catalyst calendar); treat endogenous flow/breadth as context that describes, not predicts.
5. **Build display-tier freely; gauntlet only at promotion (§0.5).** Every organ ships display-tier and accrues a forward ledger from day one — the ledger is how the brain gets labeled data, not a gate on building. The episode-unit pre-registration (§9) binds only when an organ is *promoted* to authority (rank/size/gate). No `validated` language (CI-enforced). LLMs classify/summarize/de-escalate only — never originate a score or escalation.
6. **Kills are construction-specific; retain nulls as confluence.** The resolved HK program (§11) nulled specific *standalone-selection* constructions. Those factors are **retained as confluence inputs** to the context stack, and the ranking goal stays open — we keep generating new constructions. Only rule: don't re-run the *identical* failed construction as a standalone edge and call it new.
7. **Fail-closed freshness in code, not cadence** (inherited): any organ whose input is >2 HK-sessions staler than the page's own price is suppressed with a visible reason.

---

## 4. The layered architecture

Six layers, bottom-up. Each is a thin set of deterministic organs feeding a compact command panel — reusing the existing `hk_market_drivers` attribution engine and `hk_signal_stack` as the backbone, not replacing them.

```
LAYER 0 — TRUTH / FRESHNESS      hk_freshness_sentinel + lib/hk_calendar + ops-bug fix
                                  (cross-store render gate; the thing that actually broke 07-08)
LAYER 1 — IGNITION DETECTION      WASHOUT WATCH middle state + eligible:0 carve-out
                                  + per-name bellwether impulse strip  (the "front-run the bottom" organ)
LAYER 2 — OFFSHORE / CROSS-MKT    ADR overnight gap bridge (the literal 07-08 fix)
                                  + A/H×ADR triangulation + A-share pre-open impulse
LAYER 3 — FLOW & FUNDING          southbound accel/divergence + SH/SZ skew (extend existing)
                                  · funding-transition surfaced from hk_liquidity_regime (DROP new build)
LAYER 4 — CATALYST / NARRATIVE    hk_hkexnews_filing_bus (one collector, N classifiers)
                                  + scheduled-catalyst calendar · GDELT sentiment (context-tier, last)
LAYER 5 — HK STRUCTURE (net-new)  CBBC/warrant leverage map · turnover/liquidity thrust · quota pulse
LAYER 6 — COMMAND PANEL UI        force stack + event tape + Bottom-Watch/Chase-Watch scorecards
                                  (wires Layers 0–5; built LAST; reuses committee.html synapse map)
```

---

## 5. Engine roster — tiered (the answer to "what do we build")

Tiering from the adversarial review (rev2), reconciled with data feasibility (res1) and the resolved kills (§12). **T1 = build first (high value, low cost, verifiable). T2 = valuable, data/UI-dependent. T3 = context-only, clutter-risk. DROP = redundant.**

| # | Organ | Tier | Build verdict | Serves | Reuse / note |
|---|---|---|---|---|---|
| 0 | **hk_freshness_sentinel** + `lib/hk_calendar.py` | **T1** | BUILD-NEW (~70% reuse) | both | Copy `check_price_store_freshness.py` shell; `nyse_calendar.py` → HKEX mirror (+typhoon one-offs); `tushare_freshness.staleness_badge()` verbatim. **The only thing that actually broke 07-08.** |
| 0b | **Ops fix** (untrack `_closes_cache`; kill `-X theirs`; git-add scope) | **T1** | FIX | pipeline | 1-line untrack + rebase-strategy change. Correctness, not research. |
| 1 | **hk_bottom_ignition** (`WASHOUT WATCH` middle state) | **T1** | BUILD (btc_impulse_radar UP-gauge maps directly) | stock board | New pre-confirmation state between `DECLINE` and the lagging ladder; fires on washout-depth pctile + external capitulation (southbound reversal, ADR lead, VHSI fade) *without* requiring the daily MACD cross. Display-only watch-strip. **The "front-run the bottom" organ.** |
| 1b | **eligible:0 carve-out** | **T1** | FIX | stock board | Risk-off overlay must leave a surviving watch-tier, or every organ is silenced. |
| 2 | **hk_tech_bellwether_impulse** (per-name strip) | **T1** | EXTEND `hk_market_drivers` (~50% reuse) | macro | Per-name z-scored impulse ("Alibaba +Nσ, Meituan +Mσ") on top of the existing `tech_internet_leadership` fingerprint. Add 9988 to the fingerprint legs. |
| 3 | **hk_adr_overnight_bridge** | **T1** | BUILD (ephemeral, no `data/` write) | both | BABA/BIDU/JD ADR + KWEB/FXI close vs prior HK close → implied HK open + gap-follow/gap-fade flag. **The one feed that would have shown +12.5% before HK open.** Display the gap; assert no fade edge. |
| 4 | **hk_ah_adr_triangulation** (ADR leg only) | **T1** | EXTEND `hk_ah.py` | both | A/H engine + 25-pair panel exist; add ADR lead-lag leg. Build on H3 (the one near-GO edge, DSR 0.879). |
| 5 | **hk_southbound_flow_acceleration** | **T1** | EXTEND `hk_conditions`/`hk_market_drivers` | macro | Add `southbound_cum.diff(3)` z + SH/SZ channel skew (data exists). **Not** flow-vs-price divergence as a selection edge (killed §12) — as market-level context only. |
| 6 | **hk_scheduled_catalyst_calendar** (A2) | **T2** | EXTEND `hk_event_calendar` | both | Index rebalance (HSI/HSTECH quarterly 8% cap), Connect fast-entry eligibility, MSCI/FTSE reviews, PCAOB/HFCAA dates. **Deterministic dated leads** — high feasibility. |
| 7 | **hk_hkexnews_filing_bus** + classifiers | **T2** | BUILD (mirror `china_intel_bus`) | both | ONE collector feeding company-level catalyst / national-team-buyback / placement-overhang classifiers. Scrape-based (no API); ToS-bounded to 1yr. |
| 8 | **hk_cbbc_warrant_leverage_map** (A1) | **T2** | BUILD-NEW (flagship gap) | structure page | HKEX daily CBBC/DW reports (free EOD, keyless). Call-level magnet clusters (forced issuer hedging on breach), bull/bear ratio froth, knockout cascades. **Most HK-distinctive organ; Codex missed it entirely.** |
| 9 | **hk_top_exit_exhaustion** (chase-risk) | **T2** | BUILD (btc DOWN-gauge maps) | both | Secondary to bottom-catch; asymmetric grading (§9). |
| 10 | **hk_asia_fast_overlay** (intraday) | **T2** | BUILD-NEW (~60% reuse) | both | Yahoo 15m post-close; ephemeral JSON, **never** writes `data/` or advances ledgers (house law). yfinance 60d/rate-limit risk — ephemeral only. |
| 11 | **Command panel UI** (`hk_command.html`) | **T2** | BUILD LAST | macro | Wires Layers 0–5; reuses `.sstack-grid`, `.alert`, `.chip`, `committee.html` synapse map. |
| 12 | **hk_narrative_sentiment** (GDELT) | **T3** | BUILD-NEW (highest cost/risk) | context | GDELT feed easy but MID entity resolution → needs ticker-map layer; unfalsifiable at low-n. Context-tier, no promotion pretense. |
| 13 | **hk_ipo_smallcap_frenzy** | **T3** | DEFER (data-blocked) | context | HK IPO subscription lives in unstructured allotment PDFs — hardest feed; no selection-alpha hook. |
| 14 | **hk_funding_peg_pulse** | **DROP** | REDUNDANT | — | Fully covered across `hk_liquidity_regime`, `hk_global`, `hk_conditions`, `hk_alerts`, `hk_market_drivers`. **Surface** the existing EASY/TIGHT transition on the command panel; build nothing. |

**Secondary legs (fold, don't standalone):** Connect quota pulse (High feasibility), turnover/liquidity thrust (reuse `hk_liquidity_regime`), ETF create/redeem offshore-demand (extend `etf_flows.py`), national-team/SOE footprint (into the filing bus), dividend/buyback-blackout calendar (pairs with catalysts), ADR implied-vol transfer (reuse options infra), dual-counter HKD/RMB divergence (thin data).

---

## 6. Reuse blueprint (so we don't reinvent)

| Need | Proven repo pattern (file) | Adaptation |
|---|---|---|
| Freshness sentinel | `check_price_store_freshness.py` shell + `tushare_freshness.staleness_badge()` + `lib/nyse_calendar.py` | HKEX-calendar swap; read `_closes_cache`/`^HSI`; state → existing `.health-banner` |
| Ignition & chase gauges | `btc_impulse_radar.py` two-gauge threshold→decay→**ladder** (`quiet/coiled/warning/trigger`) | UP-gauge→bottom, DOWN-gauge→top; replace legs with `risk_off_washout` / `tech_internet_leadership` fingerprints; **act-tier gate reused verbatim** (context alone caps at `coiled` — anti-permanently-on) |
| Forward ledger | `btc_impulse_ledger.py` `stamp()/grade()/load()` | copy verbatim → `hk_impulse_ledger.py` → `data/hk_impulse/`. **House-law precondition to any gate.** |
| Attribution / force stack | `hk_market_drivers.py` (8 fingerprints, live) + `hk_signal_stack.py` | wire impulse states into `signal_stack.legs`; the `.sstack-grid` panel *is* the force stack |
| Event tape | `hk_alerts.Alert` dataclass (bilingual `message`/`message_zh`) + `.alert` CSS | add catalyst/ignition rules |
| Command graph | `committee.html.j2` Canvas synapse map (`{nodes,edges,asof}`) | embed as collapsible sub-panel; new `/api/hk_context_graph`, no JS rewrite |
| Freshness UI | `committee.html` `.stale-ok/.stale-warn/.stale-old` + `hk.html.j2` `.health-banner` | `staleness_badge` state → chip class; mirror banner at page top |
| Sentiment dial | `fear_greed.py` 0-100 gated composite + `young_tiles` honest exclusion | narrative leg excluded until ≥252 obs |
| Degraded contract | `quad_vector.py` missing→widen-toward-neutral | any missing organ widens, never sharpens |

---

## 7. The stock-board revamp (co-equal track)

The operator's verdict: the stock board "can't predict anything" and couldn't front-run the bottom. Honest decomposition and fix:

- **It was blind (ops).** Same `_closes_cache` freeze → Layer 0 fixes it.
- **It boarded everything out (design).** `eligible: 0` risk-off blackout → §5 #1b carve-out leaves a surviving watch-tier.
- **It has no pre-confirmation state (design).** → §5 #1 `WASHOUT WATCH` middle state, surfaced on a watch-strip with explicit "unconfirmed, high-risk" framing; catches ignition 1–2 days before the lagging ladder.
- **It hides the edges it *does* have.** The A/H near-GO tilt (H3, DSR 0.879), the peg-liquidity conditioner (H5), southbound accumulation, SFC short context — all built, all suppressed when `eligible:0`. Surface them on surviving watch-tier cards.
- **It has no offshore bridge.** → §5 #3 ADR overnight tape on the stock board hero, so a BABA +12.5% ADR close is visible on the HK card that night.

**What it becomes:** a **better bottom-detection and context map that accrues a real scoreboard**, surfacing the whole ladder from "washout, watching" → "igniting, unconfirmed — here's the entry" instead of a silent "AVOID." The standing "no residual HK selection alpha" verdict bounds the *tested rankers*, not the goal — every context factor here (southbound, A/H, beta, washout, ADR) is retained as a **confluence input**, and we keep generating new ranking constructions (§0.5, §11). Operator setting: **aggressive early calls** — fire early, log every call to the forward ledger, keep the falling-knife demote as a visible risk chip, not a silencer.

---

## 8. Information architecture (lobe / pages / scorecards)

One lobe — **"HK Neural Web"** — surfaced as:

| Surface | Type | Purpose |
|---|---|---|
| `hk_command.html` | **Page** (new, macro-mode section or standalone) | Force stack + event tape + the two twin scorecards below. The daily "is this tape becoming combustible?" answer. |
| `hk_structure.html` | **Page** (new) | CBBC/warrant magnet map (A1), Connect quota, turnover thrust, dual-counter — the HK-microstructure lens. |
| `hk_catalysts.html` | **Page** (new) | Scheduled-catalyst calendar (A2) + HKEXnews filing bus (buybacks / placements / national-team). |
| **Bottom-Anticipation** scorecard | Card | washout depth + southbound reversal + ADR gap-down + CBBC call-out + VHSI fade; forward-ledgered (episode unit). |
| **Chase-Risk** scorecard | Card | extension + CBBC bull-skew + ADR gap-fade + placement overhang + funding-tightening; forward-ledgered. |
| **Offshore-Bridge** scorecard | Card | ADR implied-open + KWEB/FXI + freshness; **non-scored context — the literal 07-08 fix.** |
| **Flow** scorecard | Card | southbound accel + SH/SZ skew + quota + ETF create/redeem + national-team. |

Existing pages (`hk.html`, `hk_stocks.html`, `hk_lookup.html`, `baskets_hk.html`) are upgraded in place (freshness banner, washout-watch strip, ADR tape, surfaced edges), not replaced.

---

## 9. Measurement & governance (non-negotiable)

**This protocol is the PROMOTION exit gate, not a build gate (§0.5).** Organs ship and accrue freely; the arithmetic below binds only when an organ is moved to authority (rank/size/gate). It is here now because the ledgers must be *shaped correctly from day one* — a badly-designed ledger accrues unusable data, and the whole point of building first is that the accrued data is later gauntlet-ready. The red-team verdict on the Codex plan: **naive-dangerous** — it describes the *shape* of rigor without the *arithmetic*, and leaves the shop's documented **lethal** class unguarded (ticker-cluster time-confound, DT-R14). Binding protocol at promotion:

1. **Anchor exclusion.** July 8 is a design fixture: `is_anchor_event=true, graded=false, reason=fit_case`. It motivates existence; it never counts toward promotion.
2. **Retro-census before forward accrual.** Pre-register a numeric definition of a "comparable HK-tech washout→rebound," enumerate 2015→2026 *before* looking. Expected reference class ≈ **6 episodes/decade → promotion clocks in YEARS.**
3. **Threshold freeze under `param_hash`.** Any change resets the forward clock.
4. **FDR across the whole family.** One `HYPOTHESIS_REGISTRY.yml` row per (organ, label, direction, horizon); frozen K (~96 hypotheses); Benjamini–Hochberg q=0.10 across the family, not per-organ. Nulls printed with raw p + "FAILED FDR."
5. **Episode is the unit of analysis (DT-R14).** Collapse same-week/same-complex fires into ONE `episode_id`. Every hit-rate/CI carries `n_episodes` beside `n_name_days`; `n=40` without `n_episodes` is rejected on sight. **Time-preserving (stationary-block) bootstraps only; ticker-cluster bootstrap BANNED.**
6. **Force-stack fence.** Composite may not be graded until ≥2 legs individually pass FDR; **no fitted weights** (unweighted vote / fixed equal weights) — data-fit fusion is illegal (mirrors "positioning fusion illegal", "no fused score").
7. **Overlap correction.** Declare one horizon per label; non-overlapping episode windows preferred; long horizons excess-vs-HSI.
8. **Asymmetric grading.** `bottom_arming` graded as ignition-capture (`MFE_capture − λ·MAE_pain − μ·|timing_error|`, weights frozen) with a wrong-way hard-miss penalty (fired then fresh low). `chase_risk` graded as avoided-drawdown (`P(fwd_drawdown>thr | fired)` vs base rate). Symmetric win-rate is the wrong ruler.

**Ship in the same PR as organ #0/#1:** `hk_impulse_ledger.py` (`hk_organ_ledger.v1` schema with `episode_id`, `param_hash`, `asof_freshness{}` — a stale fire is INVALID not graded), `HYPOTHESIS_REGISTRY.yml`, `RETRO_CENSUS.json`. Otherwise the whole stack re-runs the DT-R14 error.

---

## 10. Phasing & build-lane routing (subagent teams)

Model routing per CLAUDE.md: **Sonnet builds, Opus reviews, main-loop (me) plans/adjudicates/merges.** Every wave = builder lane(s) (sonnet `builder`) + a review gate (opus `reviewer`). Each lane works in its own worktree off fresh `origin/main`.

| Wave | Deliverable | Build lane (sonnet) | Review gate (opus) |
|---|---|---|---|
| **W0 — Truth & ops** | untrack `_closes_cache`; kill `-X theirs`; `lib/hk_calendar.py`; `hk_freshness_sentinel` cross-store render gate (extend #1917 to ^HSI); page-top health banner; **`eligible:0` carve-out** | 1 builder (calendar+sentinel), 1 builder (ops/CI) | ops red-team (CI blast-radius: daily.yml/asia-close.yml are load-bearing) |
| **W1 — Ignition spine** | `WASHOUT WATCH` middle state (btc UP-gauge port); per-name bellwether impulse strip (+9988 in fingerprint); `hk_impulse_ledger` + `HYPOTHESIS_REGISTRY.yml` + `RETRO_CENSUS.json` | 1 builder (state machine), 1 builder (impulse+ledger) | stats reviewer (rev3 protocol compliance) + retro-census adjudication (me) |
| **W2 — Offshore bridge** | `hk_adr_overnight_bridge` (ephemeral); ADR leg on `hk_ah` triangulation; A-share pre-open impulse | 1 builder | reviewer (ephemeral/no-data-write law) |
| **W3 — Flow/funding surface** | southbound accel + SH/SZ skew (extend); surface EASY/TIGHT transition on command panel (no new engine) | 1 builder | reviewer |
| **W4 — Catalyst layer** | `hk_scheduled_catalyst_calendar` (extend); `hk_hkexnews_filing_bus` + classifiers (mirror `china_intel_bus`) | 1 builder (calendar), 1 builder (filing bus) | reviewer (scrape ToS + source-class audit) |
| **W5 — HK structure** | `hk_cbbc_warrant_leverage_map` (flagship); turnover thrust; quota pulse | 1 builder | reviewer (magnet-cluster methodology) |
| **W6 — Command panel UI** | `hk_command.html` + Bottom/Chase/Offshore/Flow scorecards; synapse map embed; stock-board revamp UI (watch-strip, ADR tape, surfaced edges) | 1 builder (macro panel), 1 builder (stock-board) | reviewer (bilingual, 375px dual-mode CSS regression, no `title=` translation) |
| **W7 — Chase-risk + narrative (deferred)** | `hk_top_exit_exhaustion`; GDELT narrative (context-tier); asia_fast_overlay | 1 builder | reviewer |

**Data-first sequencing (§0.5):** W0 (truth/ops) ships first because it makes all collected data trustworthy. Immediately after, a **data-plane wave** builds the collectors for every net-new organ in parallel — ADR/ETF bridge feed, HKEX CBBC/warrant daily reports, scheduled-catalyst calendar, HKEXnews filing bus, GDELT — so the contextual substrate starts accruing *before* any study. Organs then consume the flowing data display-tier. Per operator, **all four net-new organs (ADR, CBBC, catalyst calendar, GDELT) are in the priority set**; GDELT ships context-tier (no promotion pretense) but is built now to accrue. Every wave writes a forward ledger from day one; first matured episode read is **years** out per §9 — the accrual is the point, and it is the honest scoreboard stated on-page.

---

## 11. Prior kills — retained as confluence, not re-run as standalone edges

From the resolved `HK_CANADA_STOCKS_MASTERPLAN` §6.1 (Fable, 07-03). Per §0.5, these factors are **kept as confluence inputs** to the context stack and their data keeps accruing; the ranking goal stays open. The only prohibition is re-running the *identical failed construction* as a standalone selection edge and calling it validated:

- **HK residual/selection momentum** — KILL (fails DSR, IC≈0).
- **Southbound holding-Δ as a name ranker** — NO-GO (render lag eats it). *Southbound accel as market-level context is a distinct, freshly-pre-registered organ — allowed.*
- **Southbound flow-vs-price divergence** — on the do-not-build list. Do not resurrect as a signal.
- **COILED / cohort-washout durable-bottom detector** — KILLED on HK. The new `WASHOUT WATCH` is market/name-timing context on a fresh pre-registration, **not** the killed cohort-washout.
- **Reversal (deepest-loser buy)** — KILL, wrong sign with power → the existing falling-knife demote gate stays. Ignition ≠ buying the deepest loser.
- **`hk_funding_peg_pulse` as a new engine** — DROP (redundant). Surface the existing conditioner.

The one surviving near-GO edge — **A/H discount (H3, DSR 0.879, accruing to 2027-01)** — is the gold; the ADR triangulation builds on it.

---

## 12. Operator decisions (resolved 2026-07-08)

1. **Ignition aggressiveness:** **aggressive early calls** — fire early, accept false starts, log every call; falling-knife demote stays as a risk chip not a silencer (§7, §0.5).
2. **Build scope:** **build out**, data/infrastructure first (§0.5). Start with W0 truth/ops, then the data-plane collector wave.
3. **Priority net-new organs:** **all four** pulled into the priority set — ADR overnight bridge, CBBC/warrant leverage map, scheduled-catalyst calendar, GDELT narrative (GDELT shipped context-tier, built now to accrue).
4. **Doctrine:** build-first / gauntlet-at-promotion-only / confluence-retention / construction-specific-kills — encoded in `CLAUDE.md` + memory.

---

## 13. Status log

- 2026-07-08 — v1 authored (orchestrator). 13-agent verify+research+red-team workflow complete. Codex diagnosis corrected: OPS root cause (`_closes_cache` tracked-but-gitignored + `-X theirs` clobber, frozen at 2026-07-02) + `eligible:0` blackout, not an engine-coverage failure. 12 organs → tiered to ~5 T1 + expansion. Stock-board revamp folded in as co-equal track.
- 2026-07-08 — operator doctrine set (§0.5): build-first / gauntlet-at-promotion-only / confluence-retention / construction-specific-kills, encoded in `CLAUDE.md` + memory `context-accrual-fundamental-goal`. Decisions resolved (§12): aggressive ignition; build out data-first; all four net-new organs prioritized. **W0a** (freshness sentinel + `lib/hk_calendar` + untrack `_closes_cache`) dispatched to a builder+review lane. **W0b** (`-X theirs` rebase-strategy fix) held for careful scoping + operator review given nightly-pipeline blast radius.
