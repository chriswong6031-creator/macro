# EXECUTIVE OS — PHASE 0 INSTITUTIONAL CENSUS

**Date:** 2026-08-11 · **Author:** Fable main-loop adjudication over 5 sonnet census lanes (Mastermind control plane; Mastermind brain/loop/bridges; Macro metabolism+Prophet; Neural Web governance; Macro fleet-governance layer) · **Scope:** Macro Dashboard (`macro`), Mastermind Portfolio (`/Users/chriswong/Documents/Cluade/Mastermind`, branch `master`), cross-repo governance artifacts. Terminal repo touched only where contracts reference it.

**Charter for this doc:** determine what already exists that can become the foundation of the Mastermind Executive Operating System (AI CEO = GPT-5.6 Sol, COO/orchestrator = Fable, execution workers = Claude/Codex instances). Census only — **no production behavior was modified**. Company phase: **PRE-REVENUE MVP CONVERGENCE** — the proposal in §5 is deliberately small and boring.

Liveness key used throughout (receipts in lane reports, spot-checked): **LIVE** = on a scheduled/serving path with real accumulated data · **REFERENCED** = imported, path unclear/manual · **DORMANT** = wired but flag-off/paused · **DEAD** = zero production callers.

---

## §0 Verdict

**The Executive OS mostly already exists; the work is adoption, not construction.** The organization already runs on: a prose constitution cited 118× in code (Charter V2), a fully LIVE nine-module control plane with real decision/run/governance ledgers (Mastermind `control_plane/`, 2,222 LOC), a weekly ranked objectives engine (`brain/improvement_agenda.py`), an experiment registry with a working maturity clock (`brain/experiment_registry.py`), a proven propose-in-sandbox/dispose-in-Python worker contract (per-desk MCP `submit_book`), and a battle-tested fleet-governance layer in Macro (program registry, kill registry, ship-loop guard, merge-on-green sweeper, model-routing guard). `config/agents.yml` already seats `gpt-5.6-sol` at `reasoning_effort: xhigh` — the AI-CEO chair is literally a config row that exists today.

**Genuinely missing** (the only things to create): a machine-readable strategic-state artifact (strategy today is prose no code ingests), a close-the-loop resolve path on the objectives engine (it observes but nothing marks items done), worker-seat authority fields on the existing registry, ~3 new event types on the existing governance ledger, and the CEO↔COO↔worker contract **written down** — the Mastermind repo's own AGENTS.md/CLAUDE.md never mention the control plane that gates their submissions. Total genuinely-new code: **≈300 LOC + one small YAML + prose**. Everything else is KEEP/EXTEND of live machinery.

**Biggest absorb:** Metabolism's autonomous code-writing loop (25.5k LOC, `AUTONOMY_PAUSED=true` since 2026-07-18, never completed one full adjudicate→build→merge cycle even while live). Its governance primitives are excellent and become Executive OS patterns; the autonomous proposer/builder itself must not be restarted as-is or perpetuated as a second work-dispatch system. The org has been running fine on session-driven work the whole time it was paused — that observed reality, not the aspiration, is what the Executive OS should institutionalize.

---

## §1 Component census

Classification vocabulary: **KEEP** (foundation as-is) · **EXTEND** (foundation + small additions) · **REFACTOR** (right concern, needs contained restructuring — never sweeping) · **ABSORB** (function moves into the Executive OS core / another mechanism; standalone form stops being load-bearing) · **DEPRECATE** (no new dependencies; retire when convenient) · **DELETE** (dead; remove in a dedicated cleanup PR). Classifications are recommendations — nothing was deleted or modified by this census.

### 1.1 Constitutions & doctrine

| Component | Liveness | Class | Why |
|---|---|---|---|
| `Mastermind/research/MASTERMIND_CHARTER_V2.md` (P1–P10, 50 lines) | LIVE-as-authority — 118 `charter P<n>` code citations across app/bot/brain/control_plane/portfolio | **KEEP** | The organizational constitution already exists and is actively cited to justify code behavior. Executive OS constitution = amend this (add the CEO/COO/worker seat map), never replace. |
| `Mastermind/DOCTRINE.md` (tactical doctrine, 190 lines) | LIVE-as-prose; numerically distilled into doctrine.yml | **KEEP** (fix drift) | Real drift found: `DOCTRINE.md:49-51` still presents the book theme cap as the load-bearing firebreak while `config/doctrine.yml:34` marks it `LEGACY — DISPLAY-ONLY`, superseded by cluster caps. One-paragraph fix, not a rewrite. |
| `Mastermind/config/doctrine.yml` (815 lines, numeric doctrine) | LIVE — 25+ runtime consumers via `bot/doctrine_config.py`; hashed at every boot by `control_plane/governance.py:273`, `doctrine_changed` events fired 4× in production | **KEEP** | Working parameter constitution with change-detection already wired to the governance ledger. Model for any future executive parameter file. |
| `macro/CLAUDE.md` + `AGENTS.md` (fleet law) | LIVE — indexed as `repo-constitution` in `config/context_index.yml:19-20`; hook/CI-enforced in places | **KEEP** | The worker-facing constitution for the Macro fleet. Already the answer to "how do workers behave"; Executive OS references it, doesn't duplicate it. |
| `Mastermind/AGENTS.md` + `CLAUDE.md` (69/37 lines) | LIVE but incomplete | **EXTEND** | **Finding:** neither mentions `control_plane/`, `DecisionPacket`, `governance.jsonl`, or the A0–A7 ladder — the worker contract is silent on the entire substrate that gates worker submissions. The CEO↔COO↔worker communication contract (§5.10) lands here as prose. |
| `macro/engine/neuralweb/constitution.py` (400 LOC, Articles + A0–A7 authority ladder) | LIVE — A1/A7 origination ban hard-coded (`constitution.py:300-309`); A3 evidence floor coded (Wilson gates); A4–A6 convention + ledger | **KEEP** | The AI-authority constitution for signal work. Its "A7 ORIGINATE permanently banned / LLM proposes, never arms" stance is the same stance the Executive OS needs for the CEO seat. |
| `macro/docs/NEURAL_WEB_CASE_LAW.md` HOUSE-U4 gauntlet law + `research/DO_NOT_REBUILD.md` | LIVE (CI-guarded compiler, PostToolUse regen hook) | **KEEP** | The org's case-law and kill-ledger. Executive decisions that kill topics already have a working, minted-key, CI-enforced home (`DNR:KILL-…` rows). |
| `Mastermind/config/brain.yml` (41 lines) | LIVE-narrow — sole consumer `brain/client.py`, which hardcodes around its stale `deep` value | **ABSORB** → `config/agents.yml` | Duplicates agents.yml's tier declarations; its one historical divergence was patched in code, not in the file. Fold the surviving cost-cap/gate fields into agents.yml when `client.py` is next touched. |
| `macro/DECISIONS.md` (1,607 lines, root) | DEAD-as-ledger — last entry 2026-06-14; unreferenced by CLAUDE.md/AGENTS.md | **DEPRECATE** | Name suggests a decision ledger; content is a stale crypto/Vector-era engineering log superseded by the masterplan + DNR apparatus. Do not build on it; add a header pointing to the live conventions. |

### 1.2 Control plane (Mastermind) — the Executive OS substrate

All nine modules are LIVE with production data. This package is the single most reusable asset in the census.

| Component | Liveness receipts | Class | Why |
|---|---|---|---|
| `control_plane/run_events.py` (138 LOC) → `data/governance/run_events.jsonl` | LIVE — busiest ledger, 7.0 MB, rows through 2026-07-31 | **KEEP** | Append-only telemetry spine. Job-registry events already land here. |
| `control_plane/run_ledger.py` (202 LOC) | LIVE — `app/scheduler.py:69-70` wraps all ~22 scheduled jobs with `start_run/end_run` brackets embedding git SHA + full flag snapshot | **KEEP** | This *is* a job run-ledger: every scheduled job already reports start/finish with provenance. The Executive OS job registry reads it rather than inventing one. |
| `control_plane/governance.py` (331 LOC) → `data/governance/governance.jsonl` | LIVE — boot-time doctrine hash check; 8 production events (`doctrine_changed`×4, `experiment_matured`×4); NW-schema-compatible | **EXTEND** | This is the decision ledger. It needs only new event *types* (§5.4) — not a new store. 4 of its 6 documented event types have never fired; exercise before extending further. |
| `control_plane/decision_packet.py` (663 LOC) → `packet_rejections.jsonl` | LIVE — 245 production rows through 2026-07-31; mechanical substance-floor validation | **KEEP** | Proven "AI proposes a structured, validated decision" schema (v1). Trading-scoped today; the *pattern* (packet → mechanical validation → ledger) is the template for executive decisions, but don't force-generalize the schema in Phase 1. |
| `control_plane/packet_gate.py` (277 LOC) | LIVE, **shadow-only** — wired into all 5 brain books + judgment; 100% of 245 rows shadow; enforce never flipped; masterplan's own review clock (`MASTERMIND_CONTROL_PLANE_MASTERPLAN.md:244-246`, ~2026-07-20) is ~22 days overdue | **KEEP** (flip is an open decision, §6) | The gate exists and works; the org just never took the enforce decision. That decision is the natural first act of an Executive OS governor — a review of 245 shadow rejections, then a recorded ruling. |
| `control_plane/flags.py` (61 known flags) | LIVE — snapshotted at every boot into run events | **KEEP** | Config-state provenance, already embedded in every run bracket. |
| `control_plane/locks.py` | LIVE — every book job + global locks | **KEEP** | Boring and correct. |
| `control_plane/guardrail.py` | LIVE — widest fan-out (bot/portfolio/data_layer/bridge) | **KEEP** | Severity-graded guardrail results with ledger logging. |
| `control_plane/contracts.py` + `config/contracts.yml` (589 lines, 41 artifacts) | LIVE — drives FREEZE-class freshness gating in `data_layer/macro_refresh.py:136` | **KEEP** | The upstream (Macro→Mastermind) data communication contract: per-artifact owner, freshness budget, degradation class, consumers. Extend with new artifacts as needed; the mechanism is done. |
| `Mastermind/config/authority_map.yml` (523 lines, A0 TELEMETRY → A7 FABLE_HUMAN; every `MASTERMIND_*` flag mapped to authority level + allowed_effect) | REFERENCED — **read only by 4 test files; zero runtime readers** ("DOCUMENTATION-AS-CONFIG" by its own header) | **EXTEND** | The governor's rulebook already exists as a CI-conformance spec. The Executive OS governor = giving this file its first runtime reader (§5.9), not writing a new authority model. |
| `Mastermind/config/agents.yml` (54 lines: `pm:opus, deep:opus, analyst:sonnet, scout:haiku`, `codex: {model: gpt-5.6-sol, reasoning_effort: xhigh}`, backend cli/waterfall/codex) | LIVE — consumed by all bot books + 8 brain modules | **EXTEND** | The worker registry seed. Already routes both worker species (Claude in-process SDK, Codex CLI/MCP) and already seats the intended CEO model. Needs per-seat authority + mandate fields (§5.5), nothing structural. |
| `Mastermind/research/MASTERMIND_CONTROL_PLANE_MASTERPLAN.md` (395 lines, R1–R10, MW0–MW6, hand-written status log) | LIVE-as-program-doc | **KEEP** | Program strategic state. Its hand-written status log overlaps governance.jsonl in purpose — going forward, consequential rulings should land as ledger events *and* prose, with the ledger authoritative for "when/what," prose for "why." |
| `Mastermind/scripts/system_census.py` + `data/census/CENSUS.md` (R10 "generated state, authoritative over prose") | LIVE, one defect | **KEEP** (fix) | Self-census generator exists. Defect: reports "0 flags currently set" while `.env` sets 3 — generated without `.env` loaded, so the "authoritative" artifact understates live config. Small fix, high trust payoff. |

### 1.3 Decision & provenance infrastructure (Mastermind brain)

| Component | Liveness | Class | Why |
|---|---|---|---|
| `brain/decision.py` (`brain_decision.v1`; engine derives the falsifier, model authors the thesis) | LIVE — imported by research desk, judgment book, shadow books, phase paths | **KEEP** | Codifies "model proposes, engine derives the escape hatch" — a house invariant worth reusing verbatim. |
| `brain/decision_context.py` (`decision_context.v2` perception contract) | LIVE — freshest artifact in the data tree | **KEEP** | The worker's standard perception input. |
| `brain/decision_provenance.py` (flat per-candidate replay rows fingerprinted by `flags_hash()` over KNOWN_FLAGS) | LIVE — sole writer `bot/phase2.py:331` | **KEEP** | Decision provenance exists and is flag-fingerprinted. Not a linked graph — fine for MVP. |
| `brain/market_view.py` (65KB) | LIVE-as-display-compat only (`decision_context.py:3-4` names it the compatibility artifact) | **DEPRECATE** | Superseded by decision_context.v2 for every AI seat; kept alive for display. No new consumers. |
| `research/mastermind_problem_register.json` (74-item prioritized backlog) | DEAD-as-mechanism — no code reader | **ABSORB** → objectives loop (§5.3) | A hand-built priority backlog nothing ingests. Its live entries become agenda/objectives items; the file retires. |

### 1.4 Officers & learning loops (Mastermind brain)

| Component | Liveness | Class | Why |
|---|---|---|---|
| `brain/cio.py` (weekly seat grading; "deliberately toothless… RECOMMENDATIONS") | LIVE — Sun 10:00 UTC cron; W28/W29 artifacts | **KEEP** | After-the-fact grader with zero enforcement power — exactly the right shape to feed the COO's weekly review. |
| `brain/committee.py` (FORGE/SENTINEL/NEXUS blind bear adversary; subtract-only) | LIVE — armed by default | **KEEP** | The armed adversarial veto. Subtract-only (confirm→trim→drop, never escalate) is the house authority pattern. |
| `brain/gate.py` (material-change cadence gate) | LIVE | **KEEP** | Decides *when* to rebuild — boring, correct. |
| `brain/gate_officer.py` (portfolio-level veto; default OFF; one production run ever, 2026-06-22) | DORMANT | **DEPRECATE** | Duplicate subtract-only veto sibling of committee at portfolio granularity. Its concern merges into the packet-gate enforce decision — two dormant veto layers should not both be revived. |
| `brain/journal.py`, `calibration.py`, `attribution.py`, `benchmark_ledger.py` | LIVE — nightly/maintenance crons, real artifacts | **KEEP** | The working accountability spine (conscience, confidence shrinkage, credit split, bogeys). These feed improvement_agenda; the Executive OS reads their outputs, never reimplements them. |
| `brain/board_learning.py` (shrink-only trust multiplier) | DORMANT — flag default OFF | **KEEP** (dormant) | Harmless, shrink-only, flag-gated; a future arming decision, not machinery to remove. |
| `brain/board_track_record.py` | DORMANT-broken — own docstring "The bot reads NONE of this today"; its source parquet not found | **DEPRECATE** | Reader with no data source. Revisit only if the upstream ledger contract materializes. |
| `brain/distill.py` (CatBoost distillation of Opus decisions) | LIVE-but-starved (`n:0`) | **KEEP** | Correctly built, waiting on data volume. |
| `brain/bottleneck.py` + `bot/phase1.py` | DEAD — phase1 has zero production importers; live path is `bot/daily.py`→`phase2.py` | **DELETE** | Dead precursor pair. Remove in a dedicated cleanup PR with the usual test sweep. |
| `brain/improvement_agenda.py` (1,057 LOC; fuses 10 accountability sources into a ranked, evidence-cited item list; Sun 10:30 UTC; `data/agenda/<date>.json` + `AGENDA.md`) | LIVE writer + real artifacts; **open loop** — items age out via `_carry_forward()`, no built/verified/retired state, no resolve caller | **EXTEND** | **The only ranked priority list in either repo.** The objectives engine already exists; what's missing is the loop closure (§5.3): resolve semantics + a strategic-state input + absorption of the problem register. |
| `brain/experiment_registry.py` (882 LOC; `open→matured→judged` lifecycle; daily `matured()` cron) | LIVE for maturity promotion; **manual-only** for add/resolve (zero production callers); 14 experiments, 4 matured, **0 judged** | **EXTEND** | The experiment registry exists with a working clock. Needs a thin session-facing CLI for add/judge (§5.7) and a worked-off judged backlog — not a new system. |

### 1.5 Worker communication bridges (Mastermind)

| Component | Liveness | Class | Why |
|---|---|---|---|
| `brain/cli_bridge.py` (Claude via `claude_agent_sdk.query()`, in-process MCP tool servers) | LIVE — every book's brain call | **KEEP** | Worker transport #1. |
| `brain/codex_bridge.py` + `codex_mcp_stdio.py` (Codex CLI, read-only sandbox, same typed tools over real MCP stdio) | LIVE | **KEEP** | Worker transport #2 — the identical tool surface exposed to an external model. This dual-transport symmetry is exactly how a third seat (CEO) plugs in without new plumbing. |
| Per-desk MCP modules (`bot_mcp.py` base + `autonomous/etf/heavyweight/china/hk/flagship_desk` ×6): `get_my_book` + reads + exactly one write, `submit_book` → `_pending_decision.json`, re-validated and executed by deterministic Python; cross-book reads denied | LIVE — all six scheduler-confirmed | **KEEP** pattern / **REFACTOR** copies (later) | **This is the CEO↔COO↔worker contract, already in production:** LLM proposes in a sandbox with one write tool; trusted deterministic code disposes. Duplication flag: six copy-paste scaffolds (`hk_mcp.py:1-14` still describes itself as the all-China book). Consolidate into one parameterized module *opportunistically* — contained refactor, not now. |
| `bridge/build_portfolio.py`, `bridge/macro_snapshot.py`, `bridge/nw_feedback.py` (counts/codes-only telemetry pushed into the Macro repo's git tree, 2×/day) | LIVE | **KEEP** | Cross-repo reporting exists, including a worker→HQ status-report precedent (nw_feedback). |
| `bridge/job_runner.py` (file-drop job queue: `jobs/<id>/input.json` → `result.json`) | DEAD — zero callers, `jobs/` absent, one commit ever | **DELETE** | Superseded by the MCP tool-calling path. Do **not** revive file-drop dispatch for the Executive OS. |

### 1.6 Self-improvement machinery (both repos) — the absorb list

| Component | Liveness | Class | Why |
|---|---|---|---|
| **Metabolism** (`macro/engine/metabolism/` 32 modules 19,895 LOC + `scripts/metabolism_*.py` 5,651 LOC + 12 scheduled workflows): AGENDA→PROPOSE→ADJUDICATE (two-key + adversary veto)→BUILD (Opus, draft-PR-only)→AUDIT→VERIFY→MERGE (CI-green + two-key + self-mod fence, no admin bypass) | **DORMANT** — `AUTONOMY_PAUSED=true` since 2026-07-18 (gh variable receipt); last cycle branches 07-18; **no completed adjudicate→build→merge ever**, even during its one live week; V12 masterplan diagnoses root causes (design-blind proposer, budget-gate fail-open, key-pool exhaustion) | **ABSORB** | The flagship archaic machinery. Its governance primitives are the best in the org — immutable budget file (`config/metabolism_budget.yml`), two-key adjudication with adversary veto, draft-PR-only inertness, double pause gate, immune/heartbeat lanes, structural no-self-promotion (`lifecycle.py:9-18`) — and those patterns get absorbed as Executive OS job/experiment governance. The autonomous code-writing loop itself is not restarted as-is and must not become a second work-dispatch path. Empirical proof it isn't needed for MVP: 24 days paused, nothing broke, all improvement shipped via session-driven waves. Keep the code as reference implementation; any Phase-2 revival starts from the V12 diagnosis, not from re-arming. |
| `config/metabolism_attention.yml` `operator_pins` (core/weekly/paused lobe pacing; operator-written, loop-immutable) | LIVE-as-config (loop paused) | **KEEP** | The one real machine-read priorities file in Macro. Pattern feeds §5.3. |
| **Prophet Arena** (champion vs frozen challengers on the identical nightly ruler; ≥20 closed plans → scoreboard → operator ratifies; never auto-flips) + **Prophet Doors** (pre-registered G1–G4 gates; two consecutive FAILs = KILL appended to DNR) | LIVE — nightly-advanced ledgers inside `daily.yml`; promotion strictly session/operator-ratified | **KEEP** | Correctly-designed program-local experiment loops. The Executive OS experiment registry *federates* them (rows pointing at their ledgers), never migrates them. |
| Oracle gauntlet family (`scripts/oracle_gauntlet_p3/p8/compound.py` + options gauntlet, 5,894 LOC) | LIVE program-local | **KEEP** | Same verdict as Prophet: federate, don't centralize. (Duplication noted in §2 — a shared gauntlet library is a someday-consolidation, explicitly out of MVP scope.) |
| `Mastermind/loop/` offline research harness (19 files: iterate/promote/holdout/pbo/factor_zoo/…) | Mostly DEAD-or-manual — nothing scheduler-reachable; engine_backtest/factor_zoo/fundamentals run manually and serve `/api/*` reads | **KEEP** the manual tools; **DEPRECATE** the never-called promote/iterate chain | A human-run research bench, not a loop. The self-promotion chain inside it never ran and duplicates the (also unratified) self_tune path. |
| `Mastermind/brain/self_tune.py` (+ `loop/harness.py` frozen judge) | DEAD-in-practice — zero production callers, `MASTERMIND_SELF_TUNE` default OFF, logs `self_tune: dark`, `data/self_tune/` absent | **DEPRECATE** | Fully-wired self-tuning that was never armed. Same absorb logic as Metabolism: the *pattern* (frozen judge, bounded lanes) is recorded; the mechanism isn't revived for MVP. |
| Nightly `daily.yml` (7,375 lines; sole ledger advancer; DST-paired cron; coalescing express lanes with disjoint commit surfaces) | LIVE | **KEEP** | **The job runner.** One authoritative scheduled advancer + structurally-disjoint express lanes. The Executive OS schedules nothing new; new recurring work becomes a step/lane here or a Mastermind scheduler job. |

### 1.7 Neural Web governance primitives (Macro)

| Component | Liveness | Class | Why |
|---|---|---|---|
| `config/synapse.yml` (18,789 lines, 636 artifacts with owner/tier/freshness/consumers) + `config/lobe_charters.yml` (109 charters, CI-mirrored tier, fitness sensors, lifecycle_state) + CI integrity gates | LIVE | **KEEP** | The registry discipline to imitate for any new registry (schema-versioned YAML + validators + CI). Charter fields missing for org use: mandate/boundaries/assigned-worker — noted for §5.5, added there not here. |
| `engine/neuralweb/_law.py` five authority booleans (`can_add_candidates/raise_size/lower_size/block_entry/force_exit`), published **all-FALSE** in every cross-repo artifact; recursive payload asserter | LIVE (~21 opportunistic call sites) | **KEEP** | The portable "no autonomous execution" stamp. Any executive artifact crossing a repo boundary should carry the same explicit authority booleans. |
| `data/neuralweb/governance.jsonl` (append-only authority-transition ledger, 5–20 events/quarter, minted event vocab) | LIVE | **KEEP** | The genuinely append-only decision-ledger precedent on the Macro side; schema already shared with Mastermind's governance ledger ("NW-schema-compatible"). |
| `engine/neuralweb/brain_gateway.py` + `analyst/` + `doctrine.py` (mtime-reloaded doctrine, leak sentinels, aggregate-never-originate market packet) | LIVE | **KEEP** | Customer-facing comm-contract precedent; not on the Executive OS critical path. |
| `tests/test_constitution.py` (753-line A0–A7 regression suite incl. explicit A7-refusal + Wilson sweep) | **UNWIRED** — zero references in `.github/` (verified this session) | **EXTEND** (wire it) | The constitution's deepest tests run by convention only. Wiring is a known-tricky op (unrun-suite CI traps) — chartered as a side task, see §4. |

### 1.8 Fleet-governance layer (Macro) — the de-facto Executive OS today

| Component | Liveness | Class | Why |
|---|---|---|---|
| `config/mastermind_programs.yml` (3,893 lines: **59 programs**, 6 category-departments, full ontology — kinds, lifecycle states, per-program `owns/does_not_own` + `decision_boundary.authority_class`) + generated `docs/MASTERMIND_SYSTEM_MAP.md` + CI byte-identity test | LIVE | **KEEP** | **Department state already exists here.** Six categories = departments; every program carries lifecycle + authority class. The Executive OS reads this; it does not get a parallel org chart. |
| `docs/ACTIVE_BUILD_MAP.md` + `data/governance/active_builds.json` (nightly regen) + `docs/PROJECT_ACTIVE_BUILD_MAP.md` (three-repo) | LIVE (Macro map nightly; project map session-triggered) | **KEEP** | The job registry at PR granularity, explicitly advisory. Sub-PR task granularity is *not* needed for MVP. |
| `research/DO_NOT_REBUILD.md` + compiled blocklists + drift checker + PostToolUse regen hook | LIVE | **KEEP** | Kill/law/hold ledger with minted keys and CI enforcement — the strongest decision-provenance mechanism in the org. |
| `.claude/hooks/ship_loop_guard.py` (2,465 LOC) + `.github/workflows/merge-on-green.yml` + `.claude/hooks/model_routing_guard.py` + `config/codex_lane.yml` | LIVE | **KEEP** | The worker completion contract (commit→push→PR→merge→live), the account-side merge authority, the model-tier law, and a worker budget cap. These are Executive OS *enforcement* — already built, already hook/CI-mounted. |
| 136 `research/*MASTERPLAN*` + 47 `*HANDOFF*` docs (session-chain convention; §0 acceptance gates; in-place amendment logs) | LIVE | **KEEP** | Distributed strategic/department state. The strategic-state artifact (§5.2) *indexes* the top of this, never replaces it. |
| `macro/engine/experiments_registry.py` + `engine/trial_ledger.py` + `data/trial_ledger.jsonl` | LIVE | **KEEP** | Macro's own experiment registry (signal trials). Two experiment registries exist org-wide (see §2); federate by scope, don't merge. |
| Worker identity (280 worktrees at census, emergent naming; FleetView external; no in-repo session registry) | — | **KEEP** (emergent) | Deliberate non-build: session-level identity tracking is a product/tooling concern (FleetView), not a repo registry. §5.5 registers *seats*, not sessions. |

---

## §2 Duplication register

Explicitly identified per the census charter. None of these get fixed in Phase 0; each is either absorbed by an MVP decision (→§5) or parked with a no-new-dependencies rule.

1. **Two A0–A7 ladders with colliding numbering, different semantics** — Mastermind `authority_map.yml` (A0 TELEMETRY → A7 FABLE_HUMAN, flag-authority) vs NW `constitution.py` (A0 OBSERVE → A7 ORIGINATE-banned, AI-capability). Same names, opposite top rungs (A7 = highest human authority vs A7 = forbidden AI act). Park: do not unify now; the Executive OS governor (§5.9) binds to **Mastermind's** ladder for org actions and must cite it as `authority_map.yml A<n>` (never bare "A<n>") to avoid cross-ladder ambiguity.
2. **Six copy-paste desk MCP scaffolds** (`china_mcp` vs `hk_mcp` residue included) — contained REFACTOR, opportunistic.
3. **committee.py vs gate_officer.py** — two independently-built subtract-only vetoes (name-level armed, portfolio-level dormant). Resolved by §1.4: deprecate the dormant sibling; the portfolio-level veto concern belongs to the packet-gate enforce decision.
4. **agents.yml vs brain.yml** model-tier declarations — absorb brain.yml (§1.1).
5. **Two experiment registries** — Mastermind `brain/experiment_registry.py` (portfolio experiments) and Macro `engine/experiments_registry.py` + trial ledger (signal trials). Different domains, both live. Federate: the Executive OS experiment view (§5.7) lists both; no migration.
6. **Gauntlet logic reimplemented ≥3×** (Oracle P3/P8/compound, Prophet Doors, Prophet Arena) with zero shared code. Park: shared library is post-MVP consolidation; HOUSE-U4 prose stays the single definition.
7. **qual_ladder.yml field-level ladder vs synapse.yml artifact tier** — two overlapping promotion vocabularies in Macro. Park (documented CI mirror covers the charter copy).
8. **market_view.v1 vs decision_context.v2** — display-compat vs live contract. Deprecate path already declared in code comments; enforce by convention (no new consumers).
9. **Decision provenance distributed across four homes** (DNR rows, 52 adjudication docs, masterplan amendments, account-local memory) with no single ledger — the gap §5.4 closes by *convention on existing stores*, not a new store.
10. **Metabolism (machine loop) vs session-driven waves (human/Fable loop)** — both implement propose→gate→ratify. The org demonstrably runs on the second. §5 institutionalizes the second; the first is absorbed.
11. **Control-plane masterplan status log vs governance.jsonl** — prose decision log vs machine ledger recording the same class of events. Resolution in §1.2: ledger authoritative for when/what, prose for why.
12. **bridge/job_runner.py file-drop dispatch vs MCP tool path** — resolved: DELETE the former.

---

## §3 Archaic machinery — absorb/retire summary

**ABSORB** (function survives inside existing/MVP mechanisms; standalone form retires): Metabolism autonomous build loop (governance primitives → §5 patterns) · `mastermind_problem_register.json` (→ objectives) · `config/brain.yml` (→ agents.yml).

**DEPRECATE** (no new dependencies): `gate_officer.py` · `board_track_record.py` · `market_view.py` · `self_tune.py` + loop/ promote-iterate chain · `macro/DECISIONS.md`.

**DELETE** (dead, in a dedicated cleanup PR): `bridge/job_runner.py` · `bot/phase1.py` + `brain/bottleneck.py`.

Everything else in the census is KEEP or EXTEND — the constraint "preserve useful existing mechanisms" is satisfied by construction: of ~45 censused components, 5 are deprecations and 3 are deletions, all with zero production callers or dormant-by-flag status.

---

## §4 Defects surfaced (side findings, not Executive OS work)

1. **Packet gate enforce-review overdue** (Mastermind): 245 shadow rows, 0 enforce, masterplan's own review clock ~22 days past. This is the natural first governor ruling (§5.9) — a review session, then a recorded `governance.jsonl` event either way.
2. **`tests/test_constitution.py` unwired in Macro CI** (verified: zero `.github/` references). Wiring must respect the known traps (an unrun suite can red the trigger-closure guard; wiring during a red main is self-defeating) — needs its own small PR with a clean-main baseline.
3. **Mastermind self-census understates live flags** (`data/census/CENSUS.md` says 0 flags; `.env` sets 3) — census generator runs without `.env` loaded.
4. **DOCTRINE.md theme-cap paragraph** contradicts `doctrine.yml`'s `LEGACY — DISPLAY-ONLY` marking — one-paragraph doc fix.
5. **Mastermind AGENTS.md/CLAUDE.md silent on the control plane** — fixed by §5.10's contract prose, which was needed anyway.

---

## §5 Minimum viable Executive OS

Design stance: **a thin adoption layer over live machinery.** No second control plane (the Mastermind `control_plane/` package *is* the control plane; Macro's fleet-governance layer *is* the fleet law — the Executive OS binds them with ~300 LOC, one YAML file, and prose). No new daemons, no new schedulers, no message bus, no session-tracking service. Every new artifact follows the house registry convention where CI-relevant (schema-versioned `config/*.yml` + loader + drift/conformance test).

| # | Concern | REUSE (exists, adopt as-is) | EXTEND (small additions) | GENUINELY NEW |
|---|---|---|---|---|
| 1 | **Constitution** | Charter V2 (org, P1–P10) · Macro CLAUDE/AGENTS (fleet) · NW constitution.py (AI authority) · DNR/case-law (kills) | Charter V2 gains a §"Executive seats": CEO = strategy/objectives proposals (advisory, packet-shaped); COO = adjudication/merge authority per existing model-routing law; workers = execution under ship-loop. States which constitution governs which domain and that on conflict Charter > doctrine (already its rule). | Prose only (~1 page amendment). |
| 2 | **Strategic state** | 136 masterplans + program registry remain the deep state | — | **`Mastermind/config/strategic_state.yml`** — the one net-new file. Small, schema-versioned: `phase: pre-revenue-mvp-convergence`, horizon, ≤5 standing constraints, ≤7 current objectives (ids + owner seat + review date), pointers into masterplans. Loader ~40 LOC; conformance test asserts referenced owners exist in agents.yml. Machine-read by improvement_agenda (11th fusion source, ~30 LOC). *Not a control plane: no runtime behavior keys off it except agenda ranking.* |
| 3 | **Objectives / priorities** | `improvement_agenda.py` — the only ranked, evidence-cited priority engine in the org; weekly cron; AGENDA.md output | Close the loop: stable item ids + `resolved_by` (PR/ledger-event ref) + explicit retired state (~60 LOC); read strategic_state.yml; absorb the 74-item problem register (one-time triage, live items become agenda sources or registry rows) | Nothing else. The weekly AGENDA.md becomes the COO's standing queue; CEO reviews/reorders it as packets, not edits. |
| 4 | **Decision ledger** | `control_plane/governance.py` + `governance.jsonl` (Mastermind, machine) · DNR registry (Macro, kills) · NW governance.jsonl (AI authority) — all append-only, schema-compatible where it matters | Add ~3 event types: `executive_decision`, `objective_set/retired`, `experiment_judged` (~10 lines + authority_map `events:` rows + conformance test already exists). Convention: every executive event carries a minted key and cites its prose doc; DNR keeps kill authority. | Nothing. **Explicit non-goal: a new unified store.** Unification is a citation convention across three live ledgers. |
| 5 | **Worker registry** | `config/agents.yml` (roles→models→backends; Sol already seated) · codex_lane.yml (budget caps) · emergent session identity (worktrees/PR authorship; FleetView is the product surface) | Per-seat fields: `authority_level` (→ authority_map.yml), `mandate` (one line), `desk` (→ book/program). ~15 yml lines + conformance test vs authority_map. | Nothing. Registers **seats, not sessions** — no live-instance tracking service. |
| 6 | **Job registry** | Scheduled: `app/scheduler.py` ~22 jobs bracketed by `run_ledger` (SHA + flags provenance) · Macro nightly `daily.yml` + coalescing lanes · PR-granular: active_builds.v1 + build maps · completion: ship_loop_guard + merge-on-green | — | Nothing. New recurring work = a scheduler job or nightly step. **Explicit non-goal: task queue / file-drop dispatch (job_runner stays dead).** |
| 7 | **Experiment registry** | Mastermind `brain/experiment_registry.py` (lifecycle + daily maturity clock) · Macro `engine/experiments_registry.py` + trial ledger · Prophet Arena/Doors + Oracle gauntlets as program-local instruments | Thin CLI (`scripts/experiment.py add|judge`, ~80 LOC wrapping existing `add()/resolve()`) so registration stops being out-of-band JSON edits; judge the 4-matured/0-judged backlog; add federation rows pointing at Arena/Doors/gauntlet ledgers | Nothing structural. Promotion authority unchanged: operator/COO ratifies; nothing auto-arms (HOUSE-U4). |
| 8 | **Department state** | `mastermind_programs.yml` 6 categories + 59 programs with lifecycle + authority class (org chart) · per-book ledgers/marks (desks) · masterplans (deep state) · organism/fitness cards → prophet_governor (nascent rollup precedent) | — | Nothing for MVP. A generated per-department rollup doc is a later nice-to-have; the census explicitly declines it now. |
| 9 | **Governor / authority boundaries** | authority_map.yml (the rulebook) · packet_gate (the chokepoint) · subtract-only pattern (committee, calibration, shrink-never-flip) · NW five-boolean all-FALSE stamp · model_routing_guard + ship_loop_guard (fleet side) | Give authority_map its **first runtime reader**: at packet/flag boundaries, log (shadow) any action whose flag flips outside its declared `allowed_effect` — reuse of the existing shadow-then-enforce doctrine (~50 LOC). Then take the overdue packet-gate enforce ruling (§4.1) and record it. | Nothing. The governor is authority_map.yml *enforced*, not a new engine. Cross-repo executive artifacts carry the five authority booleans, all FALSE. |
| 10 | **CEO ↔ COO ↔ worker communication contract** | The production propose/dispose pattern (desk MCP `submit_book` → `_pending_decision.json` → deterministic validation) · dual transports (cli_bridge in-process; codex_bridge/MCP-stdio external) · nw_feedback (worker→HQ telemetry) · handoff-doc session chains · contracts.yml (data planes) | CEO seat = the existing codex path (`gpt-5.6-sol`, read-only sandbox) given **one** desk-MCP-shaped surface: read strategic_state/agenda/ledgers, one write tool `submit_executive_packet` (packet-validated, shadow-first — decision_packet pattern, ~100 LOC). COO = Fable sessions with merge/adjudication authority (already law). Workers = unchanged. | Prose: write the contract into Mastermind AGENTS.md/CLAUDE.md (currently silent on the control plane) + cross-reference in Macro CLAUDE.md. |

**Total genuinely new:** 1 YAML file + ~300 LOC (loader, agenda closure, experiment CLI, shadow authority logger, one executive MCP surface) + ~2 pages of prose. Everything else is adoption of live machinery. Sequencing note (not this session): land items in the order 2→3→10-prose→4→7→9, each as its own small PR through the normal ship loop; the CEO seat's write surface (10) comes **last** and starts shadow-mode like every gate before it.

## §6 What NOT to build (binding non-goals for Phase 1)

1. **No second control plane** — `control_plane/` + the Macro hook/CI layer are it. Any proposal to "generalize" them into a new framework is DNR-shaped work.
2. **No revival of the Metabolism autonomous build loop as-is** — any revival starts from the V12 root-cause list and is its own chartered program.
3. **No worker/session tracking service** — seats in agents.yml; sessions stay emergent (FleetView is the product answer).
4. **No new schedulers, queues, or buses** — scheduler jobs + nightly steps + MCP tools + git are the transports.
5. **No ladder unification, no gauntlet library, no MCP-scaffold rewrite in Phase 1** — parked consolidations (§2) with no-new-dependencies rules.
6. **No auto-arming authority anywhere** — every new surface ships shadow-first with printed rejections, per the packet-gate and HOUSE-U4 precedents; promotion to enforce is a recorded human/COO ruling.
