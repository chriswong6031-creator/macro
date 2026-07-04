# CORTEX — The Central Brain & Nervous System — Brainstorm by Fable

**Question posed (operator, 2026-07-04).** Should we build a central brain for the dashboard — reactive, live, able to learn — that also serves as the communication hub letting engines talk to each other? Two sub-questions: (1) will our engines ever truly cross-communicate (today it's "messy and undocumented"); (2) can engines stop being batch gears and become "breathing" pieces?

**Status: BRAINSTORM at operator STOP. Nothing dispatched.**

---

## 0. In plain English

The dashboard already has a brain — it's just scattered across the floor. There are ~482 engine modules that compute signals, about two dozen JSON files they use to pass results to each other, a 67-minute batch job that runs everything in order, several small "live" subsystems that already react to events in real time, and a decision-making Claude (the Brain, in Mastermind) that already deliberates over engine output. What's missing is not intelligence — it's a **nervous system**: documented wiring between the parts, the ability to react to one event without recomputing the whole world, and one place where every prediction gets remembered and graded so the system actually learns.

The version of "central brain" worth building is that nervous system. The version NOT worth building is a sci-fi autonomous agent that generates signals and acts on its own judgment — everything this repo has validated says edge comes from deterministic, backtestable, gated computation, and an LLM improvising live decisions is none of those things.

**Verdict: build it — as connective tissue, not as a new organ.** Formalize the bus, make recomputation incremental and event-triggered, consolidate the learning ledgers, and give the deliberative Brain a constitution-bounded seat on top. Roughly 70% of the parts already exist as proven one-off prototypes; the program is unification, not invention.

---

## 1. Census — what exists today (the "messy undocumented web," documented)

### 1a. How engines cross-communicate NOW (they do — four channels)

| Channel | Examples | Properties |
|---|---|---|
| **Direct imports** (215 of 482 modules import another engine module) | `indicators.pct_rank_window` (13×), `technicals.rsi`, `regime.apply_hysteresis`, `market_state` internals, `ai_desk._level_asof` | Mostly leaf *utility* reuse — fine, this is a library, not messaging |
| **JSON artifacts** (the de facto bus) | `site/basketdata/`: `sector_pulse.json`, `radar.json`, `narrative_brain.json`, `flow.json`, `foresight_cascade.json`, `member_context*.json`, `theme_extension*.json`, `vol_sentiment.json`, `bottleneck.json`… + `data/*.json` (`run_status.json`, strategy verdicts, validation_meta) | **No schema registry, no producer/consumer manifest, no freshness stamps, no validation-tier tags.** Reader discovers writer by grep. This is the messy web |
| **Shared parquet stores** | `data/yahoo/`, `data/massive_stock_day/`, breadth PIT spine, forward logs, `data/oracle/panel_*.parquet` | R2-backed heavy plane; well-managed but consumers are equally undocumented |
| **Semantic pipelines** (signal → decision) | breadth → `master_brain`; Risk Radar → macro.html Market-State override; `theme_alerts → alert_triage` → Alert Command Center; whitehouse feed → `whitehouse_brain` → banner; planned: `oracle_state.json` → alerts/banner/Mastermind/spotlight | The real cross-communication — each hand-built, each with its own contract style |

### 1b. The already-living organs (proof each piece of a "live brain" works here)

1. **Reflex arc, shipping**: White House RSS → Opus brain → ticker banner. Event-driven, LLM-in-loop, constitution-bounded (LLM may only de-escalate the calibrated key). This IS the central-brain pattern at n=1.
2. **Live senses**: `live_overlay.py` / `live_quotes.py` — slow/fast/event intraday tiers over Polygon.
3. **Pain receptors**: data-health circuit breaker (`run_status.json`, half-open recovery) + end-of-collect audit gate (`scripts/audit_*`).
4. **Deliberative cortex**: the Mastermind Brain — Claude Agent SDK, in-process MCP tools, deterministic decision matrix it may not override upward, Brier-scored thesis ledger. Already reads vendored engine output.
5. **Learning loops**: calibration hub, forward logs, signal-gate freshness, admin Experiments tracker (106 experiments with come-back dates), Oracle P7's walk-forward retraining design.
6. **Memory**: the Obsidian brain vault (memory + research symlink view) — institutional memory with typed frontmatter, already consumed by Fable sessions.
7. **Monitoring shell**: admin console (Umami/Supabase/VPS/services).

### 1c. The constraints that bind any design (house law + physics)

- **Render budget is law**: ~67 min, 4-core CPU-bound Mac; heavy artifacts → R2, off the render path.
- **PIT / determinism religion**: every validated claim in the repo exists because runs are replayable. The Time Machine (Oracle O5) is only possible because engines are deterministic.
- **LLM containment**: calibrated keys are deterministic; LLMs narrate and may only de-escalate (whitehouse contract, badge-passport ratchet lesson).
- **Display-only until validated**: failed gauntlets ship with the null printed.
- **Known failure modes to design against**: render race ships stale HTML; btc-vector override laundering (a human override hidden inside `allocation()`); silent feature death via blanket `except`; membership cache drift.

---

## 2. The core reframe — what should be alive, what must stay dead

The operator's instinct ("engines are just gears, not breathing") is half right, and the half that's right is the *orchestration*, not the engines.

**Biology sorts this cleanly.** A body does not put a brain in its reflexes. Reflexes are fast, deterministic, testable — spinal, not cortical. Cognition sits ABOVE reflexes, routing attention, synthesizing, remembering, deciding what deserves a reaction. The dashboard's engines are reflexes, and their gear-ness is **the moat, not the flaw**: determinism is what makes validation, PIT replay, the gauntlets, and the Time Machine possible. A "living" engine whose output can't be replayed can't be trusted with money — the repo's entire epistemic architecture (Phase-0s, FDR gates, forward ledgers) presumes dead, replayable computation.

So the right decomposition of "make it breathe":

| Layer | Today | Should it live? |
|---|---|---|
| **Computation** (the 482 engines) | Dead, batch | **Stay dead.** Determinism = validatability |
| **Sensing** (what changed in the world) | Mostly cron-polled | **Alive.** Event tiers already exist; extend |
| **Routing** (what to recompute, when) | Monolithic 67-min conductor | **Alive.** This is the big unlock — see §4 |
| **Communication** (engine↔engine) | Undocumented file drops | **Formalized**, not alive — a bus with schemas/provenance |
| **Learning** (do we get better?) | Scattered ledgers, manual come-backs | **Alive on a slow clock** — consolidated outcome spine, scheduled retrains |
| **Deliberation** (judgment, synthesis, narrative) | Mastermind Brain (portfolio-scoped) + per-page LLM briefs | **Alive, constitution-bounded** — one cortex, dashboard-wide senses |

"Breathing" = the system notices an event at 10:47, recomputes the ~9 affected engines in 3 minutes, updates the affected panels/alerts, and the Brain gets pinged to deliberate *if a deterministic threshold says it matters*. Not: 482 daemons with opinions.

---

## 3. Should we build it? — the honest case

**Yes, with conviction — but for the unglamorous version.** Three arguments and one warning.

**Argument 1 — the marginal cost is low because the prototypes exist.** Seven organs above already work in production. The program is: promote one-off patterns into shared infrastructure. That's the cheapest kind of ambitious project.

**Argument 2 — the epistemic payoff compounds.** Every past program (BTC overrides, foresight desk, engine-fix audit) spent its first wave *discovering* the undocumented wiring. A bus registry with provenance turns that recurring archaeology cost into a lookup. It also mechanically prevents the worst bug class we've shipped: display-only signals silently hardening into allocation inputs (§4a, provenance propagation).

**Argument 3 — it's the SaaS moat's missing half.** Oracle gives one lobe (rotation) a memory and a replay UI. CORTEX generalizes: "our system remembers every claim it made, shows you its grade, and reacts to events in minutes" is a product sentence no retail competitor can say. The Brain-activity feed (already a beloved Mastermind panel) becomes a site-wide "what is the system thinking" surface.

**The warning — what kills this if we're careless.** The failure mode is building the *homunculus*: an always-on agent loop that reads the tape and "decides things" with LLM judgment. Everything validated in this repo says: ranking-by-vibes is dead (momentum nulls), machine-generated hypotheses flood FDR (Oracle adjudication #2), and LLM latitude on calibrated outputs degrades them (badge ratchet). The brain's authority must be **routing, synthesis, vigilance, and de-escalation — never signal generation.** If a live-brain proposal can't state its deterministic trigger and its bounded action space, it doesn't ship.

---

## 4. Architecture — the CORTEX web (C0–C5)

### C0 — Synapse: the signal bus made real (registry + provenance)
Not new transport — the file-drop bus is fine (boring wins; no Kafka on a 4-core Mac). What's new:
- **`config/bus_registry.yml`** — one entry per artifact: producer module, schema (versioned), freshness SLA, **validation tier** (`validated` / `display_only` / `noise` / `experimental`), authorized consumers, R2-vs-git placement.
- **Envelope stamps** on every bus artifact: `produced_by`, `produced_at`, `inputs_hash`, `validation_tier`, `staleness_horizon`.
- **CI gate** (generalizing `validate_signals.py` §7): a consumer on the *allocation/alert path* may not read a `display_only` key — the exact laundering the BTC-override audit caught, made structurally impossible. Unregistered cross-engine reads fail CI.
- **`docs/SIGNAL_BUS.md`** auto-generated from the registry: the documented web, finally. Plus a rendered graph (who feeds whom) — the operator's "messy web" becomes an inspectable diagram.

### C1 — The Blackboard: one world-state snapshot
`data/cortex/world_state.json`, written once per run head: regime quad, VIX percentile, market state + risk-radar level (with the override resolved), liquidity state, breadth aggregates, rotation state (Oracle O4's payload slots in here), active alert count, data-health status. Engines READ the blackboard instead of each recomputing/importing regime context (today `raw_quad`/hysteresis is re-derived in 4+ places). One computation, one truth, one place to stamp provenance. This is the classic blackboard architecture — the cheapest 80% of "engines knowing what each other are doing."

### C2 — The Conductor: DAG-ify the render (the reactive unlock)
The single biggest change, and the one that makes the system "live" without touching engine internals. Engines (or initially, just the top ~50 bus producers) declare inputs/outputs — C0's registry provides this almost for free. Then:
- **Incremental recompute**: only the dirty subgraph reruns. A Finviz-tree change touches ~a dozen engines, not 482. Scoped renders in minutes, not 67.
- **Event-triggered scoped runs**: the event tiers (C3) can say "recompute the vol_regime→radar→banner chain now."
- **Race extinction**: the render-race-ships-stale-HTML class dies when runs are subgraph-scoped and input-hashed.
- Honest cost: this is the program's long pole. Mitigation: DAG the *bus producers* first (the ~50 modules that matter for cross-communication); the tail of 400 leaf display engines can stay on the daily batch forever.

### C3 — The Reflex Arcs: the event daemon (generalizing whitehouse)
One small always-on supervisor on the Mac (launchd; the Mastermind uvicorn pattern proves always-on works here): watches event sources (RSS feeds, live-quote thresholds, circuit-breaker trips, calendar events, R2 store updates), maps each to a **registered reflex** = (deterministic trigger, scoped DAG subgraph, bounded output: alert/banner/directive/page-patch). The whitehouse pipeline becomes reflex #1, unchanged; Oracle's rotation-onset detector becomes reflex #2; vol-regime flips, breadth thermals, data-health incidents follow. Every reflex firing is logged to the outcome spine (C4) — reflexes are graded too.

### C4 — The Outcome Spine: what "learning" honestly means here
Not online learning — at n = hundreds of episodes and dozens of signals, continuous weight updates are overfitting with a heartbeat. Learning here means **every claim is remembered, graded, and feeds scheduled recalibration**:
- One consolidated prediction ledger (union of: forward logs, Brier theses, alert precision, reflex firings, experiment come-backs) with a common grading schema.
- Scheduled metabolisms: monthly walk-forward retrains (Oracle P7 pattern), quarterly edge-stability refresh, experiment come-back dates auto-surfaced.
- The self-model: the system can answer "what is my hit rate on X in regime Y" — which is also what the Brain reads before deliberating, and what the SaaS page prints as track record. Base rates + calibration ARE the learned brain, in the only form this data volume can support.

### C5 — The Cortex: one Brain, dashboard-wide senses
Recommendation: **extend the Mastermind Brain rather than birthing a second brain** (two brains = split memory, split Brier ledger, eventual contradiction on a public page). It already has the SDK/MCP plumbing, the deterministic-matrix-may-not-override-upward discipline, and the Brier ledger. Give it: read access to the bus + blackboard + outcome spine + Obsidian vault (its senses), a **nightly deliberation** (synthesize the day: what fired, what's anomalous, what deserves operator attention → Brain feed on the site + morning brief), and **event deliberations** invoked by C3 reflexes above a threshold. Constitution (hard, in code): reads everything; writes only narrative keys + de-escalations + attention flags; never originates a calibrated signal, an allocation, or a banner escalation. The existing Brain-activity panel pattern becomes the site-wide "system is thinking" surface.

**Where Oracle fits:** Oracle is a lobe; CORTEX is the tissue. No dependency inversion — Oracle P5's `oracle_state.json` simply lands as Synapse citizen #1 with the envelope stamps, and its O4 propagation rails (alerts/banner/Mastermind/spotlight) become the first fully-registered pipeline. Build order stays Oracle-first; CORTEX W0 can run in parallel without touching Oracle's critical path.

---

## 5. What NOT to build (pre-registered rejections)

1. **Microservice zoo / message broker** — a 4-core Mac serving a static site does not need Kafka. Files + registry + envelopes win.
2. **The homunculus** — any LLM loop that originates trades, signals, or escalations. Constitution violation by construction.
3. **Online/continuous learning** — scheduled, gated retrains only. n is small; drift monitors, not gradient streams.
4. **482 live engines** — liveness lives in the conductor and the reflex daemon. Engines stay pure functions.
5. **A second brain** — one cortex, one ledger, one memory.
6. **Intraday everything** — event *tiers* exist for a reason; EOD remains the validated substrate (options-alpha program is explicitly EOD). Liveness is for reaction latency on discrete events, not for streaming recomputation of everything.

## 6. Benefits, stated as falsifiable outcomes

- **Reaction latency**: event → affected panels/alerts updated in ≤5 min (today: next 67-min render, up to ~24h).
- **Archaeology cost**: next program's "discover the wiring" wave drops from ~a session to a registry lookup.
- **Bug-class extinction**: display-only→allocation laundering becomes a CI failure; stale-render races die with input-hashed scoped runs.
- **Compute**: incremental DAG *reduces* Mac load (scoped reruns replace some full renders).
- **Product**: Brain feed + track-record self-model = differentiated SaaS surfaces no free dashboard has.
- **Operator leverage**: nightly cortex brief replaces some manual Fable sessions for triage.

## 7. Phase sketch (sized, sequenced; each phase independently shippable)

| Phase | What | Cost guess | Notes |
|---|---|---|---|
| **W0 — Census + Synapse registry** | bus_registry.yml over existing artifacts; envelope stamps on top ~25 producers; auto-generated SIGNAL_BUS.md + graph; CI read-gate (warn-mode first) | 2–3 sessions | Zero behavior change; pure documentation+guardrail. Do this regardless of everything else |
| **W1 — Blackboard** | world_state.json; migrate the 4+ regime re-derivations to read it | 1–2 sessions | First de-duplication payoff |
| **W2 — Conductor** | DAG over the ~50 bus producers; input-hash dirty detection; scoped-run CLI | the long pole, 4–6 sessions | Top-50 first; the 400-leaf tail stays batch |
| **W3 — Reflex daemon** | launchd supervisor; whitehouse migrated as reflex #1; reflex registration schema; firing ledger | 2–3 sessions | Requires W2 scoped runs |
| **W4 — Outcome spine** | ledger consolidation + grading schema + scheduled metabolisms + self-model query | 2–3 sessions | Feeds C5 and SaaS track-record pages |
| **W5 — Cortex** | Mastermind Brain gets dashboard senses + nightly deliberation + Brain feed page + constitution enforcement in code | 2–3 sessions | After W0/W1/W4 exist to be read |
| **W6 — The visible nervous system** | site page: live bus graph, reflex firings, Brain feed, self-model track records | 1–2 sessions | The SaaS showcase; pairs with Oracle's Time Machine |

Dependency shape: W0 → W1 → W2 → W3; W4 parallel after W0; W5 after W1+W4; W6 last. Oracle P1–P6 continues untouched in parallel; its P5 wiring lands on whatever Synapse tier exists by then.

## 8. STOP list — operator decisions

- **D1 — Build verdict**: adopt CORTEX as a program (recommended: yes, W0 immediately — it's cheap, irreversible-loss-free, and every future program benefits).
- **D2 — One brain or two**: extend Mastermind Brain as the single cortex (recommended) vs a new dashboard-native brain. Implication: the Brain's repo gains a dashboard-senses contract.
- **D3 — Transport**: stay on file+registry (recommended) vs sqlite event log vs redis. Boring wins until proven otherwise.
- **D4 — Liveness ambition**: event-tier reactions only (recommended) vs intraday streaming recompute of top signals.
- **D5 — Sequencing vs Oracle**: W0 in parallel with Oracle P2 (recommended — different files, no contention) vs strictly after Oracle P3.
- **D6 — Name**: CORTEX for the program, Synapse for the bus? (Any name; the registry key prefix should be chosen once and never migrated.)

## 9. Status log
- 2026-07-04 — Brainstorm authored (Fable) from operator prompt; grounded in bus census (this session), ORACLE_MASTERPLAN_BY_FABLE.md, and the seven living-organ precedents. **At operator STOP — no wave dispatched.**
