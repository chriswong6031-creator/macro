# Sector-Rotation Alert System — Problem Audit & Framework (for Fable)

*Digest of the operator's 2026-07-04 brain dump ("most important thing I've written this week"), organized into build-ready frameworks and reconciled against what the repo already runs + already falsified. This is the AUDIT/BRIEF; Fable produces the `SECTOR_ROTATION_ALERTS_MASTERPLAN_BY_FABLE.md`.*

**Verbatim objective.** A comprehensive alert system across `baskets.html`, `subsector_rotation.html`, `subsectors.html`, `sector_central.html` whose primary job is to **identify large shifts in trend across Sector ETFs, Thematic Baskets, and Subsectors and proactively front-run sector rotations.** The operator's proposed mechanism: detect the *confluence of velocity-of-change across a group of interconnected subsectors/themes* while an *opposite (risk-wise) group rotates the other way* (e.g. semis + memory + AI-complex + AI-buildout rolling out **while** healthcare rotates in), escalate major shifts as a **banner** (like the White House alert), send a **directive to Mastermind**, and let it **admit stocks into the Top Standout board on rotational flow** (which it does not clearly do today).

---

## 0. The one reframe that governs everything (read before designing)

The operator's *detection* instinct is sound and under-exploited. The operator's *framing of the payoff* — "front-run rotations" read as **directional return-alpha** — collides head-on with this repo's own pre-registered evidence. This is surfaced per the operator's explicit invitation ("whether you think we should implement it or a better version would be even better"), not as a veto.

**What the repo has already tested and FALSIFIED — do not rebuild it:**
- **Front-running rotation for directional alpha is a coin-flip everywhere tested.** `research/SECTOR_ROTATION_CONTINUATION.md` (blueprint `SECTOR_ROTATION_NEURAL_WEB.md`): *"the edge is drawdown-control + regime-classification + rotation-timing, NOT front-running alpha / directional pinpointing (coin-flip everywhere tested). Build to refuse, by construction, what failed the gates."*
- **The operator's exact two-sided example is falsified as a leading signal.** `research/DEFENSIVE_ROTATION.md` pre-registered and adversarially tested "defensives bottoming while tech rolls over → leads a vol shock." **Every variant fails the OOS gate.** V4 (XLV / healthcare — the operator's literal example) posts **negative** lift (−0.012 @N10); the only place an edge appears (V1) is a *rates-fell* confound, not money rotating. `flow_velocity.py` already carries the CN per-name fund-flow null (rank-IC ≈ −0.008) as an in-code honesty gate.
- **Hard sector/group gates on stock admission HURT.** `[[china-subsector-gate-falsified]]`: gating names by subsector state underperformed flat. Group leadership may **modulate/order**, never **gate**.

**What IS validated, and is exactly what the operator described from the other side:**
- The **coincident risk-router / drawdown lever**: route a cyclical BUY to WAIT during a *concurrent* flight-to-safety; **lead with "what to EXIT"** (promote AVOID/TOPPING to the loudest output). This is `SECTOR_ROTATION_CONTINUATION.md` **P0 — "the validated, safe first build."** The US absolute-trend gate is validated *as a drawdown control* (`sector_central.py`: `thematic_rotation_phase0.json` region=us, `gate_helps=true`, max-DD −0.24 gated vs −0.49 buy-hold), **not** as a return forecast (US relative-momentum rank-IC ≈ 0).

**Therefore the honest product is not a rotation *oracle*; it is a rotation *risk-and-exposure router*.** The operator's own sentence already contains the validated half: *"raise cash… as well as getting rid of the weakening (previous leaders) categories."* The **exit / de-risk / raise-cash** side is the validated, loud, safe primary output. The **buy-the-incomer** side ships **display-only with the measured base-rate/lift/lead-time printed on the page** until a forward ledger clears Phase-0 — the repo's standing house law. Framed this way the system is genuinely valuable *and* trustworthy with real money; framed as a directional oracle it repeats a failure the repo has already paid to discover.

> Design consequence, stated once: every alert names the **quantity it leads** (drawdown / 63d-excess-dispersion / exit-timing), never bare "direction," because lead-lag tests put these signals at **k≈0 (coincident)**. A "front-run" claim is allowed only for the divergence cell (money-arriving-before-narrative) and only as a **forward-graded** row, never an asserted one.

---

## 1. What already exists (inventory — so Fable extends, never rebuilds)

| Capability | Where | State | Gap vs the vision |
|---|---|---|---|
| Per-subsector RRG velocity: `rs_ratio`, `rs_mom`, `accel` (1W pace − 3M pace), `emerging_score`, quadrant (leading/weakening/lagging/improving); theme rollup; 268 subsectors / 40 themes / 8 horizons | `engine/subsector_rotation.py` | LIVE, display/context (rides Finviz broad universe; names we hold no prices for) | Per-name only. No **grouping** into interconnected risk clusters; no **two-sided** confluence; no **breadth-of-rotation** aggregate. |
| Per-subsector rotate-IN / rotate-OUT alert (`rotation_emerging` / `rotation_fading`), cross-run state-diff, silent seed, idempotent id | `engine/subsector_rotation_alerts.py` → wired `scripts/build_subsector_rotation.py:71`; ingested `engine/alert_triage.py:471` (`source="rotation"`) | LIVE, CONTEXT-ONLY (no validated forward edge, in its own words) | Fires one event per *subsector* crossing its *own* boundary. Cannot see "a **group** rotated, and its **opposite** rotated too." |
| Per-basket flow **fingerprint**: `accel` (RS-accel vs SPY), `broadening` (%>50dMA change), **`cohesion`** (mean pairwise corr + change), `persistence`; stage **EMERGING→CONFIRMED→EXHAUSTED**; **`_cluster_map`** (cross-group co-movement: absorption, dominant_cluster, tightest pair); VIX-regime gate | `engine/group_flow.py` → wired `scripts/build_baskets.py:111` | LIVE but **DISPLAY-ONLY, NEVER scored; Phase-0 OPEN** (`scripts/group_flow_phase0.py`; `data/group_flow/validation_meta.json`) | This is 70% of the operator's mechanism already built. Missing: composing cluster + cohesion + two-sided accel into a **rotation-regime event**, and clearing its Phase-0. |
| Per-theme **institutional holdings flow**: `conviction_pp` (ETF holdings-change), accumulating/distributing, **`divergence`** (flow<0 while price holds — the "A4 tell") | `engine/theme_flow_rollup.py` | LIVE, DISPLAY-ONLY, coverage-sparse | A *different* flow lens (reported holdings, 1–5d lag) than price-velocity. Both belong in the composite; keep them distinct. |
| Sector-ETF **flow kinetics** (SSGA shares-outstanding-derived flows, `data/flows/*.parquet` since 2026-06-09) | `collectors/sponsors.py SectorFlowAdapter`; kinetics wrap = W2c of the institutional program | Collector LIVE; velocity/accel wrap PLANNED, display-only, **immature until ~80 obs (~Sep 2026)** — `min_obs` gate + "accruing" watermark | The native funds-flow indicator the operator wants — but statistically not trustworthy yet; must ship with the accruing watermark. |
| **Shared sector-rotation bus**: per-theme pulse row (lifecycle, rank/score+deltas, rel-perf, breadth, heat tier); `for_ticker()`; `write_pulse → site/basketdata/sector_pulse.json`; explicitly *"any engine — Mastermind bot, Terminal, downstream scorers — can import"* | `engine/sector_pulse.py` | LIVE | **This is the integration bus.** The unified rotation-state object should extend/join this, not invent a parallel one. |
| **Sector Central fuser**: cycle-state LEAD → macro-regime + absolute-trend GATE (validated DD lever) → momentum/heat/crowding CONFIRM; conviction tier + 0–100 score + reasoning trace; every call graded | `engine/sector_central.py` + `sector_central_grader.py` | LIVE, graded | The natural home for the sector-level rotation-regime read + the "what to exit" primary output. |
| **Site-wide banner** engine: LLM significance gate (`min_importance 60`), `banner_title`, `banner_days` 1–7, ≤6 live banners, bilingual, dedup/lifespan | `engine/whitehouse_brain.py` | LIVE but **news/policy-only** ("nothing in the scoring path imports it") | No rotation→banner path exists. Major rotations currently reach only the alert center, not a banner. |
| Alert center: Triage Priority 0–100 over all `*_alerts` sources | `engine/alert_triage.py` → `alerts.html` | LIVE | Rotation events already land here. This is where **minor/medium** rotation alerts belong; banner is for **major** only. |
| **Buy Board 2.0** (Top Standout, objective #4): dual gate — WHAT (composite_z floor **modulated by group leadership, never hard-gated**) + WHEN (`signal_gate.is_buyable`, MACD-2D×StochRSI-3D T1–T4, HARD); ordering = **group-leadership desc → edge-pctile desc**; flip-to-live gated on a forward ledger | `scripts/build_stock_board_v2.py` → `us_standouts_v2.json` | **SHADOW** (not live) | Objective #4 is *already built the correct (soft) way* and is waiting on its ledger. The operator likely hasn't seen it because it's shadow. Do not rebuild — **surface it, mature its ledger, flip when it clears.** |
| Scored promotion seam for any theme signal | `spotlight.theme_tilt()/blend() → stock_score._axis_tailwind` (`engine/stock_score.py:844`, weight 0.10, over-extension-clamped) | LIVE contract (institutional program R5) | The dark-until-validated path by which a rotation tilt reaches individual stock scores. Use it; don't fork it. |
| LLM allocation brain with a **rotation slot**: `regime_read`, **`rotation_check`**, evaluates a "working rotation thesis," reads targeted-vs-starved capital rotation; instructed to **temper conviction, not flip it** | `engine/master_brain.py` | LIVE | The correct consumer of a "Mastermind directive." NB: `engine/masterminds.py` is a cross-**asset** GTAA (SPY/QQQ/bonds/gold/copper/BTC) that **holds no sector ETFs** — "buy the strengthening sector" does not map onto it. |
| Adjacent active program on the same pages | `research/INSTITUTIONAL_SECTOR_INTELLIGENCE_MASTERPLAN_BY_FABLE.md` (#1153, W0+W1 shipped) — Narrative-to-Money **Divergence board** with a **hidden-opportunity (money↑ / narrative quiet) front-run cell**, forward-graded; hidden→confirmed transition alert. First live read: cybersecurity, robotics_automation. | ACTIVE | The "front-run" claim already has a graded home. Coordinate; do not duplicate the divergence board. |

**Net:** ~70–80% of the *primitives* exist (velocity, cohesion, cluster map, flow, bus, banner, standout-soft-modulation, promotion seams). What is genuinely missing is the **composition layer** (turn primitives into a two-sided, breadth-aware rotation-regime object), the **escalation layer** (regime → banner + Mastermind directive), and the **validation** that lets any of it touch sizing.

---

## 2. Genuine gaps (the actual build surface)

1. **No multi-category confluence object.** Everything is per-name (per-subsector, per-basket). Nothing answers *"is a **coherent group** of interconnected categories rotating, and is its **risk-opposite** group rotating the other way, and how **broad** is it?"* — the operator's core idea.
2. **No group taxonomy.** There is a *data-derived* cluster map (`group_flow._cluster_map`) but no *named, risk-signed* map of interconnected complexes (AI-compute stack: semis→memory→AI-infra→power/grid; defensive complex: staples/utilities/healthcare; long-duration-growth vs short-duration-value; etc.). Deriving clusters from correlation **and** reconciling to a small named backbone is unbuilt.
3. **No rotation-breadth / regime aggregate.** No "N of M complexes turning, dispersion widening, leadership narrowing" top-of-book state that distinguishes a one-name blip from a market-wide rotation.
4. **No banner escalation for rotations.** `whitehouse_brain` is news-only; nothing promotes a major, breadth-confirmed rotation to a site-wide banner.
5. **No structured rotation directive to the allocation brain.** `master_brain.rotation_check` exists but is fed no structured rotation-regime vector; it currently reasons from narrative.
6. **Standout board rotation-admission is shadow, not live, and unproven.** Objective #4 is built correctly (soft) but gated on a ledger that hasn't matured/flipped.
7. **Four pages, four slices, no shared spine.** The 4 target pages each render a different lens; none reads one canonical rotation-state object, so they can (and do) disagree.

---

## 3. The framework — four layers, each mapped to existing code

```
        L0  HONEST OBJECTIVE  ── risk/exposure router (validated) not oracle (falsified)
             │
        L1  ROTATION STATE  ──────────────────────────────────────────────  DETECT
             group taxonomy → two-sided confluence → breadth/regime aggregate
             [extends: subsector_rotation + group_flow(_cluster_map,cohesion) + sector_pulse]
             │
        L2  ARTICULATION  ────────────────────────────────────────────────  SURFACE
             (a) per-page panels on the 4 pages  (read the L1 object)
             (b) alert-center events  [theme_alerts→alert_triage — existing pipe]
             (c) BANNER escalation for MAJOR regime shifts  [generalize whitehouse_brain]
             │
        L3  PROPAGATION  ─────────────────────────────────────────────────  ACT
             (a) Mastermind DIRECTIVE → master_brain.rotation_check  (de-risk / temper only)
             (b) Stock desk → spotlight.theme_tilt → _axis_tailwind (soft, clamped, DARK)
                 + flip Buy-Board-2.0 group-leadership ordering to LIVE once ledger clears
             │
        XC  VALIDATION CONSTITUTION + FALSIFICATION REFUSALS  (gates every promotion)
```

### L1 — Rotation State (the net-new compute; the heart of the ask)
The one new engine — call it `engine/rotation_state.py` — that **composes existing primitives** into a single canonical object per run. Proposed shape (all legs already computable from code cited in §1):

- **Group taxonomy (`rotation_groups`).** A small **named, risk-signed backbone** of interconnected complexes (e.g. `ai_compute` = semis+memory+AI-infra+power/grid; `defensives` = staples+utilities+healthcare; `long_duration_growth`; `short_duration_value`; `commodity_cyclicals`; `financials/rates-beta`…), each mapped to its member subsectors/themes/baskets. Cross-checked against the **data-derived** `group_flow._cluster_map` every run: when the empirical dominant cluster and the named backbone disagree, **surface the divergence** (that disagreement is itself signal), never silently overwrite. *(Pattern: compute factual context first, then reconcile — never let a hand map override the tape.)*
- **Per-group velocity confluence.** Aggregate member `accel` / `rs_mom` (subsector_rotation) + `cohesion`/`broadening`/stage (group_flow) into a group-level **rotation vector**: {direction (in/out), speed (accel-z), cohesion (is it coordinated or one name), breadth (% members participating), stage}. Cohesion is the guard against calling a single mega-cap a "complex rotation."
- **Two-sided read (`opposition`).** The operator's key insight, made explicit: pair each group with its **risk-opposite**; flag a **two-sided rotation** only when a group accelerates OUT *and* its opposite accelerates IN *with cohesion on both legs*. This is stricter (and more meaningful) than either leg alone. **Print the measured base-rate** for two-sided events — do not assert they lead.
- **Breadth / regime aggregate (`rotation_regime`).** Top-of-book: how many complexes are turning, is cross-sector dispersion widening, is leadership narrowing/broadening, VIX/liquidity regime (reuse `group_flow._vix_regime`, the 21d-capped liquidity overlay from `SECTOR_ROTATION_CONTINUATION.md` P1). This is what distinguishes MAJOR (banner-worthy) from minor.
- **Output = one JSON on the `sector_pulse` bus** so all four pages + the alert engine + the directive + the promotion seam read the *same* object. Severity tiers drive L2.

> Boring-baseline gate (§4.2): the dumbest version is "z-score the mean group accel and threshold it." Build that first as the control; the cluster/cohesion/two-sided machinery only earns its place if it beats the boring aggregate on the forward-graded ledger. Ship the aggregate either way.

### L2 — Articulation (surfaces; mostly wiring, one new escalation)
- **(a) Per-page panels.** Each of the 4 pages renders the relevant slice of the L1 object (no new pages elsewhere — R7 anti-fork): `sector_central.html` = the regime + "what to exit" primary; `subsector_rotation.html` = the group/two-sided view (its RRG already the natural canvas); `subsectors.html` = complex-level confluence feeding its Double-Confluence lane; `baskets.html` = per-basket stage + group membership.
- **(b) Alert-center events.** Reuse the **existing** `theme_alerts → alert_triage` pipe (mirror `subsector_rotation_alerts.py`'s idempotent schema and silent-seed). New event types: `group_rotation` (a named complex turns), `two_sided_rotation` (opposition confirmed), `leadership_rollover` (a leader complex → weakening — the loud EXIT event), `regime_shift` (breadth aggregate crosses). Idempotency: `id = type + group + boundary + date-bucket`.
- **(c) Banner escalation (net-new).** For **major** regime shifts only, generalize the `whitehouse_brain` significance→banner contract to accept a **rotation-significance** event (or a thin sibling emitter writing the same banner feed). The LLM writes the banner prose but is **barred from the calibrated key** (`SECTOR_ROTATION_CONTINUATION.md`: Opus is context-only, **de-escalate-only**, trial-taxed) — it may *narrate and downgrade* a rotation the deterministic L1 aggregate already declared major; it may **never manufacture or upgrade** one. Banner lifespan scales to breadth/durability; bilingual; ≤6 live cap inherited.

### L3 — Propagation (act — the two consumers, wired to their honest ceilings)
- **(a) Mastermind directive → `master_brain.rotation_check`.** Emit a structured `rotation_directive` (the L1 regime vector + named turning complexes + the loud EXIT list) into the brain's existing `rotation_check`/thesis slot as **context that tempers conviction and can raise cash / trim rolling-over leaders** — the *validated, de-risk* action. It must **not** synthesize a directional BUY for the incoming complex, and it does **not** touch the cross-asset quant book (`masterminds.py` holds no sectors). If a sector-tilt into the quant book is ever wanted, that is a **separate, universe-expansion decision** with its own Phase-0 — flag, don't smuggle.
- **(b) Stock desk.** Two moves: (i) route the group-rotation tilt through the **existing** dark seam `spotlight.theme_tilt → _axis_tailwind` (bounded [-1,1], weight 0.10, clamped), shipped **config-gated OFF** with the two-sided regression test (flag-off byte-identical; flag-on fixture shifts `_axis_tailwind` by the expected clamped amount) — flips on only when its forward ledger clears Phase-0. (ii) **Surface and mature Buy Board 2.0** (`us_standouts_v2.json`): its group-leadership *soft* modulation + rotation ordering is exactly objective #4 done correctly; the work is proving its ledger and flipping shadow→live, **not** adding a hard rotation gate (falsified).

### XC — Validation Constitution (non-negotiable; from `SECTOR_ROTATION_CONTINUATION.md`)
Apply to **every** new predictive claim, in lethality order: GATE-0 PIT-survivorship → **incremental-IC-beyond-VIX** (most lethal; every VIX-correlated leg) → 2020+ era holdout → FWER/BH-FDR with registered trial count → **lead-lag k=0 ⇒ label it coincident, name the quantity it leads** → deflated Sharpe + purged/embargoed CV → forward-outcome log + FP budget + a standing WRONG-condition in CI → leak checks (causal/PIT). **Anything that doesn't clear ships display-only with the null printed on the page** — a legitimate, expected outcome here. Compute deterministic context FIRST, then narrate + adversarially verify against the numbers — never let an agent guess a rotation.

---

## 4. Recommended Wave-0 for Fable (smallest validated first build; my verdict)
Do **P0-equivalent first** — it is the validated, safe, high-value core and needs no new data:
1. **`engine/rotation_state.py` v0 = the boring aggregate + the EXIT-side router.** Named group taxonomy (reconciled to `_cluster_map`), per-group velocity/cohesion, the two-sided `opposition` flag, the breadth `rotation_regime`. Primary output = **"what to exit"** (leadership rollover, loud) + the coincident risk-router that down-weights cyclical buys during concurrent risk-off. Published on the `sector_pulse` bus. **Display-only**, base-rates printed, forward ledger seeded day 1.
2. **Alert events + one banner path** on the L1 object via the existing triage pipe; banner de-escalate-only.
3. **Mastermind de-risk directive** into `master_brain.rotation_check` (context/temper only).
4. **Surface Buy Board 2.0**; keep the scored `_axis_tailwind` tilt **dark** behind its two-sided test.
Then, and only then: **W1** matures the ledgers, runs the two-sided event's Phase-0 (incremental-IC-beyond-VIX + 2020+ holdout — expect it to be hard, per DEFENSIVE_ROTATION), and flips whatever clears from display→scored.

## 5. Open questions for Fable's reassessment
- **Group taxonomy provenance:** how much hand-named backbone vs pure data-derived clustering, and how is the disagreement surfaced (not silently resolved)?
- **Does the two-sided confluence beat the one-sided EXIT signal** on the forward ledger, after the VIX/rates confound controls that already killed DEFENSIVE_ROTATION? If not, ship the one-sided router and print the two-sided null.
- **Banner threshold calibration:** what breadth/durability makes a rotation "major" enough for a site-wide banner without spam? (Mirror `whitehouse_brain` strictness + the vector-alerts commit-only-on-state-change discipline.)
- **Multi-region:** `subsector_rotation_china.py` exists; is CN/HK in scope for v1 or US-first? (CN per-name flow null is already documented — display-only there regardless.)
- **Relationship to the institutional program's divergence board** (hidden-opportunity front-run cell): merge the "money arriving before narrative" claim into that graded ledger rather than a second front-run claim here.

## 6. Falsification refusals (build to refuse these by construction)
- No alert asserts a **directional** forward edge for the incoming complex (coin-flip; DEFENSIVE_ROTATION).
- No **hard** sector/group gate on stock admission (China falsification) — modulation/ordering only.
- No banner or directive **manufactured or upgraded** by an LLM beyond the deterministic aggregate (Opus de-escalate-only, barred from the calibrated key).
- No sector-ETF flow-kinetics leg treated as thesis before ~80 obs (~Sep 2026) — accruing watermark, `min_obs` gate, CN null on the panel.
- No new orphan page/board — sections on the four named pages + the existing triage/banner/`sector_pulse`/`spotlight` rails only.

## 7. Key in-tree refs
`engine/{subsector_rotation,subsector_rotation_alerts,group_flow,theme_flow_rollup,sector_pulse,sector_central,sector_central_grader,whitehouse_brain,master_brain,masterminds,alert_triage,theme_alerts,flow_velocity,spotlight,stock_score}.py` · `scripts/{build_subsector_rotation,build_baskets,build_stock_board_v2,group_flow_phase0,defensive_rotation_phase0,sector_rotation_context}.py` · `data/{subsector_rotation/state.json, group_flow/validation_meta.json, sector_cycles/leg_context.json, flows/*.parquet, basketdata/sector_pulse.json}` · `research/{SECTOR_ROTATION_CONTINUATION,SECTOR_ROTATION_NEURAL_WEB,DEFENSIVE_ROTATION,INSTITUTIONAL_SECTOR_INTELLIGENCE_MASTERPLAN_BY_FABLE}.md`

---
*Status: 2026-07-04 — Audit/brief authored (Opus 4.8) from the operator's brain dump + a grounded read of the live engines and the three governing validation docs.*
*2026-07-04 (later) — **Superseded in part by [ORACLE_MASTERPLAN_BY_FABLE.md](ORACLE_MASTERPLAN_BY_FABLE.md)** after operator pushback was adjudicated: §0's use of DEFENSIVE_ROTATION as a general falsification of rotation-following was scope-inflated (it falsified the vol-shock outcome only) and is retracted there; the momentum-null bar and the hard-group-gate/LLM-de-escalate refusals stand; the L2/L3 rails (alerts/banner/directive/standout wiring) carry forward into Oracle O4 unchanged.*
