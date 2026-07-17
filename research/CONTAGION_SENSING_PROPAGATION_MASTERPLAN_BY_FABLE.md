# Contagion Sensing & Propagation (CSP) — Program Masterplan

**Chartered by operator order 2026-07-17** ("Need to conduct deep reasoning and audit on how we can create improvements, upgrades, and changes in all our system parts and engines and models so that it's better able to anticipate, as well as react").
**Adjudicator:** Fable (main loop). **Method:** 6-lane census (sector-reco pipeline, rotation/contagion organs, Neural-Web/LLM context, Mastermind feed, program map + kill registry, cadence/latency map) → 24 Opus-generated improvement candidates across three domains (anticipation / reaction / AI-context) → Opus adversarial red-team per domain against `research/DO_NOT_REBUILD.md`, hindsight-overfit, duplication, and engineering realism → Fable adjudication. Census and verdicts are preserved in the session transcript of 2026-07-17.

---

## 0. Scope and relationship to sibling programs

CSP owns the **wiring and honesty layer** exposed by the 2026-07-13→16 memory-unwind contagion (Korea → semis/memory → tech → Mag 7 → index): getting already-computed truth to (a) the surfaces that decide, (b) the AI consumers that advise, and (c) doing so at a cadence and freshness that matches how contagion moves.

CSP explicitly does **not** re-charter detection work owned elsewhere. Cross-references (owners unchanged):

| Owned elsewhere | Owner / wave | CSP's interest |
|---|---|---|
| Dispersion-regime state (COR1M/DSPX + SPY-vs-QQQ 20d RV spread) | XSR-W4 | the one verified ~6-week precursor; build ticket urged |
| Receiving-sector breadth detector (first `sector_breadth.parquet` consumer) | XSR-W3 | ~6-week in-sample lead, dead-wire today |
| Cross-sector pair registration (`step_pairs()` cross-sector tuples, Turn Desk Family-D fold) | XSR-W2 (RC-owned) | tech→defensives currently *unrepresentable* |
| US intraday fast lane (China #2549 splice template) | XSR-W6 | CSP-W3 rides it for the contagion key |
| Fast-lens board rail + split-view stance copy on the conviction board | XSR-W1 completion, MLC ownership per XSR-R9 | fixes XLV "Cautious 39 at RS#2" visibility |
| Sector-conviction ontology repair (`(50−pos)/50` buy-the-laggard term) | S-XSR-3 prereg per XSR-R10 | the only true F3 fix; study, never a patch |
| Intl→US radar legs (c3b local-index breadth, c3c intl-radar alert breadth) | RRI-S4 (ratified, builders pending) | the authority-path complement to CSP's context path |
| leadership_crack / deterioration_cascade organs | RSR-W2/W3 (shipped #2752) | CSP-W1 re-projects them into the AI plane |

## 1. Event evidence (established 2026-07-17; full receipts in session forensics)

Three blind planes, each independently sufficient to produce the operator-observed failure ("Leadership Board: Mag 7 — Running — narrow" on 2-day-old data while Mag 7 broke down; no US surface recommending XLV/XLP; AI consumers unaware of the unwind):

**Anticipation.** What led and where each lead died: COR1M 1st pctile / DSPX 98th pctile (06-03, never scored); healthcare member-breadth crossover above tech (06-04/05, `sector_breadth.parquet` has zero rendered-site consumers); XLV RS onset (05-19/06-10, conviction formula reads outperformance as danger — XLV Cautious 39 at RS#2, cannot mechanically reach Constructive before ~mid-Nov); AI-hardware crack replayed z_vel −3.36 (07-02) / BROKEN since 07-07 (organ shipped only 07-17); oracle rollovers across the semis complex incl. the mag7 basket (07-05, alert-triage "watch" ceiling; `oracle/rotation_directive.json` still printed `rolling_over_leaders: []`); semis subsector short-bias + memory/ai-semis baskets → avoid (07-13, no path to Mag 7 verdict or buy gates).

**Reaction.** Judgment surfaces are nightly-only (8–14h): sector states, mag7 regime, buy-board membership, intl radar alerts. The live lane *computed* MIXED/50 at 15:56 ET on 07-16 during the acute selloff and the symmetric 2-tick debounce swallowed it — displayed band stayed RISK_ON the whole session, while the heatmap's Polygon splice showed the carnage live. The 07-16-close nightly then had `collect` cancelled while all downstream jobs ran (`if: always()`, deliberate), republishing on 07-15 stores with no board-level staleness disclosure and no ledger-freeze alarm.

**AI context.** `world_state.global_regimes` covers only us/cn/hk/ca; `mastermind_context._MARKET_ORDER=("us","cn","hk","ca")` silently drops kr/tw/jp although `site/riskdata/scorecard.json` carries them; MM `intl_spillover` plane is an unimplemented stub; cortex committee DEGRADED since ~07-13 (OAuth 403, zero tool calls) and causal LLM lane dead since 07-14 (`auth_invalid_all`); no committed LLM-facing artifact named Korea/Taiwan/memory-unwind at any point in the event. MM decision spine: `macro_risk` dwell machine risk_on 14 straight sessions (fragility 0.1575 < 0.35), its inputs (VIX/credit/frozen flow.json) never carry the radar caution; `market_view` shows 5-of-7 planes risk_off yet `consensus=None` (aggregation not computing); the sev-3 derisk tripwire clips *queued* targets only, never held books.

## 2. Waves

All waves ship **display-tier + forward-ledgered where stateful** (house epistemics: detection ships freely; authority needs prereg at promotion). Promotion reviews align with the RSR-R2 clock (earliest 2026-10-17).

### CSP-W1 — Neural-Web contagion context (BUILD-NOW)
Engines originate one deterministic contagion block; every AI consumer reads it.
- `engine/neuralweb/world_state.py`: `_compose_contagion_regime(root)` — pure re-projection of shipped organs: `data/deterioration_cascade/latest.json` (state, n_alert, d3_alert, n_mature, immature list), `data/leadership_crack/latest.json` (state, z_vel, med_dd, state_since), `data/intl_risk/latest.json` `two_tier.state`, per-market last-row alert list from `data/risk_radar_intl/*_forward_log.jsonl` (maturity-annotated). Emits `world_state.contagion_regime = {state, origin_complex, intl_markets_in_alert, leadership_state, us_spillover, asof, degraded[]}`. Fail-soft on absent sources (nulls, never crash; pre-#2752 stores may be missing on some lanes).
- `engine/neuralweb/brief_context.py`: `_block_contagion(ws)` inserted into `_MACRO_DROP_ORDER` after `global_regimes` (~0.6 KB budget); deterministic numeric text; carries the #2752 honesty phrasing ("accruing — unproven; does not change the score").
- `engine/neuralweb/mastermind_context.py`: `_MARKET_ORDER` → dynamic from `scorecard.json` keys (us/cn/hk/ca first, then remaining sorted — additive-only #2687 pattern; never a second hardcoded list); add `_summarize_contagion` lobe reading `world_state.contagion_regime`.
- Registry: synapse.yml registration for any new artifact ids + `SIGNAL_BUS.md` regen + pin bump if counts change; `check_synapse_registry.py` / `check_synapse_reads.py` green.
- Law: all fields engine-originated, `is_context_only=True`; LLM consumers read, never emit (CSP-R4).

### CSP-W2 — Mastermind `contagion_state.v1` contract (BUILD-NEXT, repo-side only)
Publish `data/risk_radar/contagion_state.json`: `{schema: "contagion_state.v1", asof, built_at_utc, state, intl_alert_count, leadership_state, ttl_minutes, stale_after_utc, source_lanes[]}`. Transport already exists (MM vendor sparse cone includes `data/risk_radar/`, 3h refresh). **Fail-safe semantics are the contract:** consumers must treat `now > stale_after_utc` as feed-ABSENT — staleness fails toward caution, never complacency. The MM-side binding that moves gross_cap is **out of scope here** and requires its own prereg in the Mastermind repo (CSP-R6).

### CSP-W3 — Fastpath contagion refresh (AFTER W1)
Price-only recompute of the `contagion_state` `state` field on the existing `macstudio-light` fastpath ticks (~30s/tick against documented headroom), behind the same debounce discipline as risk_state; nightly stays sole ledger advancer; intraday `data/` writes discarded per house law.

### CSP-W4 — Glance-tier contagion chip (AFTER W1)
One hero chip reading `contagion_regime`, plain-word stance ("Tech stress spreading across Asia — watch, don't chase"), technicals in hover receipt, STEADY → hidden, bilingual, #2739/#2752 chip idiom, DESIGN_DOCTRINE-compliant.

### CSP-W5 — Board staleness honesty + pending-buy expiry (BUILD-NOW)
- Board-level staleness: `us_standouts.json` gains `staleness: {price_through, age_days, delayed}` from the underlying ohlcv max-date; when delayed, the standout board renders "BOARD DELAYED — priced {date}" (bilingual) and demotes assertive verbs; register `site/factordata/us_standouts.json` in `check_surface_freshness._ARTIFACTS`.
- Pending-buy expiry: anticipation sub=pending entries whose buy fired > 3 trading sessions before board asof without confirmation advance drop from the buy shelf to watch with "confirmation expired" copy. Demotion-toward-caution only; adds no fresh-buy edge (FRESH-BUY-refuted respected). US first; CN/HK/CA parity follow-up.

### CSP-W6 — Forward-ledger heartbeat (BUILD-NOW)
Post-publish check (`scripts/check_ledger_advance.py`): on trading days where the site republished, assert each registered forward ledger's newest asof advanced vs the prior nightly; on stall, append `type_=ledger_stall` to the #2738 fail-streak ledger + health.json warn, escalating on streak. New check ⇒ dag.yml declaration + house-law registry entry (standing trap). This is the lawful form of the collect-cancel impulse (CSP-R1): detection and disclosure, never fail-dark.

### CSP-W7 — Spread clock (LATER, descriptive-only)
Ordered timeline of dated states (crack `state_since`, rotation `day_n`, cascade `d3_alert`, per-market alert dates) as a glance surface for "the unwind is spreading". Hard-labeled descriptive/untested; **any** predictive hop-order claim requires its own prereg (does observed hop-order lead US sector pressure OOS — era-split, permutation) before authority. Ship only with an owner surface agreed in advance (F4 dead-end #17 risk is real).

## 3. Rulings

| ID | Ruling |
|---|---|
| **CSP-R1** | Hard-gating nightly downstream jobs on the collect job's result is FORBIDDEN — it reverts the ratified `if: always()` resilience law ("partial output beats shipping nothing"; the 07-16 push-race already has its salvage-push fix). Staleness is handled by disclosure (W5) + heartbeat detection (W6), never by fail-dark. |
| **CSP-R2** | 1-tick asymmetric escalation flips of the live risk-band debounce are KILLED (single noisy print flips the authoritative band; whipsaw → operator mutes it). The lawful form is the **pending-escalation badge**: the band keeps its 2-tick debounce; the in-progress escalation is surfaced the same tick it computes. |
| **CSP-R3** | News-intel / thematic-desk LLM contagion tagging of theme rows is KILLED — NAR-R4-adjacent surface with near-zero marginal value; the engine-originated contagion key (W1) + glance chip (W4) supersede. |
| **CSP-R4** | Contagion context keys are engine-originated only. LLM consumers (master_brain, cortex, thematic desk, MM strategist) read them as `is_context_only`; no LLM may originate, escalate, or numerically weight them. Restates house law for this family. |
| **CSP-R5** | Any live/intraday intl-cascade count must carry the deterioration_cascade maturity guard (≥5 prior rows per market) and be framed **coincident** — no lead claims. Precedents: RSR-R6b (TW log born 07-16 ⇒ zero lead) and the JP radar de-escalating into the 07-16 crash (safe-haven FX self-defeat). |
| **CSP-R6** | The MM-side exposure binding (contagion/caution state → gross_cap axis weight) requires its own pre-registered gauntlet in the Mastermind repo against the SPY-pullback-calibrated forward_log. This repo publishes calibrated state only (W2); it never sets MM exposure. Complies with PRD-R1/R2 (no held-risk engine here). |

## 4. Ops orders (no epistemics burden; execute independently)

1. **Cortex/causal lane restoration** — `CORTEX_ANTHROPIC_API_KEY` on the runner (dead since ~07-13; same death killed causal_llm_lane). Operator-held secret.
2. **MM `market_view` consensus bug** — 5-of-7 planes risk_off with `consensus=None`; the tilt aggregation is not computing. Mastermind-repo fix.
3. **MM pending-target review** — as of 07-17 06:20Z the flagship queue holds an SMH increase to 0.25 while the derisk tripwire reads sev-3. Operator action; flagged 2026-07-17, not a dashboard change.
4. **`oracle/rotation_directive.json` empty-leaders investigation** — printed `rolling_over_leaders: []` through the largest complex rollover of the year; the directive assembler is not reading what oracle_alerts recorded.
5. **Sector-strip label build-order fix** — `build_site` bakes us_stocks RS-strip conviction tooltips one nightly stale (runs before `build_sector_central`); reorder or re-render the fragment (respect dag.yml; #2728 class).

## 5. Ledgers, promotion, and honesty

Every stateful CSP organ ships with a forward ledger gated on `ledger_lane_armed` (asia-close arming trap noted: no COLLECT_LANE there — arm inline). Nulls print. Nothing in CSP ranks, gates, sizes, or escalates any authority surface pre-gauntlet. The word "validated" is not used on any CSP surface. Promotion reviews no earlier than 2026-10-17, jointly with RSR-W6.
