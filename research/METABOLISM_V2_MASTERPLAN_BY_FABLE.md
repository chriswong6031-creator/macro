# Metabolism v2 — the master orchestrator (the governing mind)

**Status:** RATIFIED design; Phase V2-A dispatched
**Date:** 2026-07-10
**Owner program:** `autonomic-loop` (extends `research/AUTONOMIC_LOOP_MASTERPLAN_BY_FABLE.md`)
**Operator directive:** make the orchestrator radically intelligent + autonomous — assess lobes + holistic health/fitness/**trajectory**, hunt cross-cutting bugs/inconsistencies/failures and drive fixes, and manage the **lobe lifecycle** (create/revamp/promote/demote/fix), running perpetually on a sustainable multi-key budget even when the operator is absent.
**Method:** orchestrator adjudication → 6-lens Opus design + red-team (41 ideas) → Opus xhigh judge (7 kills incl. a hard-fence guardrail, phased docket, orchestrator-brain spec, 6 operator-risk flags) → this Fable adjudication. All load-bearing claims verified in-repo by the panel.

---

## 0. Executive ruling — from per-lobe loops to a governing mind

Phase A gave the Metabolism *per-lobe* self-improvement (SENSE→PROPOSE→ADJUDICATE→VERIFY on one lobe). v2 adds the layer that makes it a **brain and not a fleet of crons**: a master orchestrator that reads the *whole organism*, sets the agenda, hunts what no single lobe can see, governs the lobe roster, and grades its own past decisions — all still behind the same cage.

Three framing corrections the design forced:

1. **Fable-mode is VENDORED, not read from home (R-V2-2).** My earlier "embed `~/.claude/skills/fable-mode/SKILL.md`" was operationally wrong: the self-hosted runner is denied reads under `~/` (launchd-TCC + FS-isolation — both in the ops memory). The distilled doctrine (the five commitments + the pre-send gate, ~3–4KB) is **vendored into `config/fable_mode_core.md`** and injected into the orchestrator system prompt whenever the resolved model is **not provably Fable** (i.e. Opus). Losing Fable degrades gracefully; the runner never touches a home path.

2. **The lobe-lifecycle authority has one unmovable chokepoint (R-V2-3).** The operator grants create/revamp/demote — and those are real, autonomous, display-tier T1 powers. But **promotion of any lobe to a scored/authority tier stays T2 + gauntlet + operator, forever.** The panel made this a *kill-on-sight build guardrail*: `lifecycle.py` must refuse to emit any transition whose destination raises a synapse tier to `confirmer|scored`, adds a `scored_path_surface`, or flips a `mastermind_context` authority switch. Demotion is always de-escalation (T1-safe). The gauntlet remains the promotion gate; the mind can prune and charter, never anoint.

3. **The mind reasons; it never originates a signal.** Every orchestrator reasoning pass reads case law (ruling graph, kill registry) as a *hard deterministic floor* and reasons *within* it. R-AUT-1 is unamended: LLMs author code through the gauntlet, never runtime signals.

Everything ships **inert** (`AUTONOMY_PAUSED`), reversible, behind the Phase-0 fences. The arming switch stays the operator's.

## 1. Architecture — the six-stage loop, now with a conductor

```
  ORCHESTRATOR TIER (new — the conductor / prefrontal cortex; stateless, git-state):
    organism_state.json  ← holistic roll-up of every lobe fitness card + health + governance + trajectory
    insight_bus.jsonl    ← append-only stigmergy; deterministic anomaly emitters drop typed rows (no lobe-to-lobe calls)
    agenda/<cycle>.json  ← ranked day-plan: URGENT-FIX / NOVEL-BUILD / DEEP-RESEARCH, budget-split, severity floor
    dream/<week>.json    ← weekly counterfactual replay: grades the PROPOSER, writes advisory preference prior
         │  (all reasoning uses _build_orchestrator_system(model): vendored fable-mode-when-Opus + quoted standing laws)
         ▼
  PER-LOBE LOOP (Phase A, unchanged): SENSE → PROPOSE → ADJUDICATE(two-key) → BUILD → VERIFY → LEARN
         │
  RUNTIME INFRA (new): key-pool dispatcher (3 OAuth keys) · worktree-per-lobe + one serialized merge lane
         ▼
  OPERATOR SURFACE (new): plain-English weekly one-pager · one-decision tap cards · front-page traffic light
```

The orchestrator tier is composed the way `world_state.py` composes macro truth — fail-open roll-up, `is_context_only=True`, raw per-lobe deltas printed beside every rollup. It does not gate or score; it *decides what the loop works on*.

## 2. Rulings (R-V2-1 … R-V2-10)

**R-V2-1 — The orchestrator is a mind, not a cron.** It composes `organism_state` (compounding vs stagnating lobes, trajectory slope, biggest strategic gap), sets a ranked agenda with an explore/exploit/research split, and grades its own past agendas (the dream cycle). It reasons over evidence; it does not merely tabulate. Reuse `world_state`/`health`/`cortex`/`ruling_graph`; do not fork them.

**R-V2-2 — Vendored fable-mode, injected when not-provably-Fable.** `config/fable_mode_core.md` (distilled: five commitments + pre-send gate). `_build_orchestrator_system(model)` prepends it iff `model` is Opus-class. NEVER read `~/` at runtime (TCC/FS-isolation). `config/fable_mode_core.md` joins the IMMUTABLE set.

**R-V2-3 — Lobe lifecycle: prune freely, anoint never.** Charter/revamp/demote/retire of **display-tier** lobes = autonomous T1 two-key. **Promotion to `confirmer|scored`/authority = T2 + gauntlet + operator, unconditionally.** `lifecycle.py` is a deterministic allowed-transition table that *cannot emit* a tier-raising edge (tested against synapse `article2_surfaces`/`scored_path_surfaces` enums). Demotion counts only *logic* failures (health `missing/degraded/stale` excluded — a dead upstream feed ≠ a bad lobe), is regime-aware, and requires an adversary non-veto on any all-inputs-absent case.

**R-V2-4 — Multi-key = capability-broker extension, belief-state accounting.** Three `claude_code_oauth_1|2|3` rows (secret_ref NAMES only). `engine/neuralweb/key_pool.py` (NEVER-RAISE sibling) + append-only `data/metabolism/key_ledger.jsonl` = the loop's *model* of the unobservable quota (Anthropic exposes no exact 5h/weekly counter — estimate from session outcomes + est-token pricing, recalibrate on every 429). `check_capability_redline.py` MUST cover the new rows + ledger schema **before V2-B ships** (the redline surface widens 3×; a token value in any of them is the catastrophic breach).

**R-V2-5 — Write-serialization: worktree-per-lobe + one merge lane.** Each granted proposal builds in its own worktree on `metabolism/build-<lobe>-<cycle>` off fresh `origin/main`; claims its target files to `claims.jsonl` + regenerates `ACTIVE_BUILD_MAP` so colliders sequence to a later cycle; a **single concurrency-grouped merge lane** (rebase --autostash + retry) lands PRs so the shared registries never merge-race. VPS gets **no shell** — code reaches live only via merge → nightly render → the existing deploy tail; any scored-surface change is fenced behind a T2 `metabolism_live` flag.

**R-V2-6 — UX-restraint is a fence, not a preference.** A deterministic screen in `adjudicate.py` fires on **front-page asset diffs only** (never `*_lab`/`committee`/`admin`): `config/ux_simplicity_rules.yml` (IMMUTABLE) — ≤N numbers per view, plain language, no internal-metric jargon, one clear primary action. Dense metrics/diagnostics route to admin/signal-lab/research pages. Front-page real estate is scarce and its changes are tap-gated.

**R-V2-7 — One lobe registry, no second source of truth.** `config/lobe_charters.yml` keyed by the **same `lobe_id` `health.py` already derives from synapse** (tier CI-mirrored from synapse, not re-declared). No parallel `metabolism_lobes.yml`. Roster caps (`max_active_nonscored_lobes`, `max_probation_lobes`) live in the IMMUTABLE `metabolism_budget.yml`; hitting a cap surfaces as a digest ASK (operator raises it), never a silent block.

**R-V2-8 — The mind cannot loosen its own alarms or limits.** New IMMUTABLE configs — `metabolism_anomaly.yml` (thresholds), `metabolism_schedule.yml` (dispatch table), `ux_simplicity_rules.yml`, `fable_mode_core.md`, the roster caps — all join the grader-manifest + self-mod fence. A loop PR editing any of them is CI-refused.

**R-V2-9 — Anomaly detection is robust-stats + honest-null, LLM investigates never declares.** `anomaly_monitor.py` (no LLM, NEVER-RAISE): robust `z = (latest − median)/(1.4826·MAD)` over last K, band-break, sustained slope-flip, artifact-staleness SLA, CI-red streak; fires only when `|z| ≥ thresh AND n ≥ n_min` (else prints "accruing"). The LLM only investigates a fired row; it never originates the anomaly. High-false-positive scanners (dead-code, CI-flakiness) stay **display-tier digest findings for human triage**, not auto-emitted PROPOSE inputs, until calibrated.

**R-V2-10 — Regime-aware human-in-the-loop on ambiguous kills (confirms R-AUT-11).** A build/lobe missing its band routes clean-overfit → auto-revert/demote; ambiguous (regime-change/estimator-broken) → operator tap, revert HELD. Kills stay on the operator's desk when the measurement lens can't rule out a regime. (Operator ratified this posture on 2026-07-09.)

## 3. The orchestrator brain — prompt + memory (the operator-flagged crux)

**`engine/metabolism/orchestrator_brain.py::_build_orchestrator_system(model, role, lobe)`** — one versioned helper imported by every orchestrator-tier reasoner (organism_state pass, agenda, dream) so the persona is consistent. Every part is an **artifact the loop edits**; the template code is fixed. Byte-capped, state-conditioned:

1. **Role + doctrine.** Role line from `config/metabolism_roles.yml`. If model is Opus-class → prepend `config/fable_mode_core.md` (R-V2-2). Default-inject whenever not-provably-Fable.
2. **Standing laws, quote-verified.** The load-bearing constraints pulled *by id* from `config/ruling_graph.yml` (CI quote-guarded — one source of truth; skill text drifts, rulings can't): R-AUT-1 signal ban, gauntlet-is-promotion-gate, UI-restraint, stateless-cattle, retire-one-to-file-one. This is what stops the mind proposing a fenced action.
3. **Organism-state slice.** `organism_state.json` rollup + this lobe's raw deltas beside it, `[:6000]` (mirrors `propose.py` caps).
4. **Relevant case-law slice.** Only ruling rows whose target/tags match the lobe + the whole `DO_NOT_REBUILD.md`. The deterministic screen in `adjudicate.py` stays the HARD floor; this slice only *informs*.
5. **Lobe charter** (`config/lobe_charters.yml` entry) + **recent lessons** (`lessons.jsonl` tail) + **the fitness-contract requirement** (every proposal must register a contract).

**Memory (three append-only git artifacts + anti-rot):** `fitness_history.jsonl` (SENSE appends), `lessons.jsonl` (VERIFY appends verdict + what-worked/failed so PROPOSE stops repeating dead constructions), `agenda_archive/` (past agendas + their graded outcomes). The **weekly dream cycle re-summarizes** to prevent context-rot over months; the summary, not the raw tail, feeds the next cycle when the tail exceeds a byte cap.

## 4. Phase docket (all INERT; each phase = build → independent-Opus-review → fix → merge)

### Phase V2-A — the orchestrator mind (build first; pure read/compute/reason, zero lifecycle authority)
| Unit | Size | What |
|---|---|---|
| Organism-state holistic sensor | M | `engine/metabolism/organism_state.py` → `data/metabolism/organism_state.json`: fail-open roll-up of all lobe fitness cards + `health.json` + cortex memo + governance rates + trial-ledger realized deltas; per-lobe compounding/stagnation/trajectory-slope; context-only |
| Insight bus + deterministic emitters | M | append-only `insight_bus.jsonl` stigmergy; emitters: health transitions, `contradictions.py`, verify FALSIFIER_TRIPPED, synapse freshness-SLA breach, contract-drift, matured come-back clock (folds in the killed cross-audit scanners as emitters) |
| Anomaly-monitor math | S | `anomaly_monitor.py` (R-V2-9); `config/metabolism_anomaly.yml` IMMUTABLE |
| Agenda-setter | M | stateless Opus reasoner (via `_build_orchestrator_system`) over organism_state + insight-bus + ruling_graph + ACTIVE_BUILD_MAP → ranked `agenda/<cycle>.json`, budget-split, severity floor forces high findings in; INERT (writes artifact only) |
| Trajectory + traffic-light data | S | `trajectory.jsonl`; site-wide GREEN/AMBER/RED with a one-line human reason; K-weeks + min-magnitude + regime-tag gate before AMBER/RED (the front-page fragment ships in V2-D behind the UX gate) |

### Phase V2-B — sustainable runtime (multi-key + write-serialization)
Key pool in the broker + `key_ledger.jsonl` (M); LRU/lowest-load dispatcher + `metabolism_schedule.yml` day-spread (M); cooling-state 429 detection + dual-horizon 5h/weekly accounting + `weekly_reserve_pct` (M); all-keys-cooling clean FREEZE + earliest-reset reschedule (S); BUILD stage + single serialized merge lane (L). **Gate: redline scanner covers the new pool rows + ledger before merge (R-V2-4).**

### Phase V2-C — lobe lifecycle authority (the T2 promotion fence is load-bearing)
Lobe charter registry (M); `lifecycle.py` allowed-transition table with the tier-raise refusal (M); fitness-floor demotion ladder, regime-gated, logic-failures-only (M); uncovered-domain scout auto-charter from a *recurring coverage gap*, not a whim (L); revamp-vs-fix adjudicator by failure topology (M); roster-budget governor (S). **Operator ratifies the roster cap number + the residual promotion-launder acceptance before this phase.**

### Phase V2-D — the mind's memory + the operator relationship
Orchestrator-brain prompt engine + vendored fable-mode injection (M); memory engine + anti-rot re-summarization (M); dream cycle (subsumes agenda-review + preference prior) (M); two-tier digest — plain-English weekly one-pager (four fixed headings: *what got better / what's slipping / what I'm about to do / what needs your tap*) with the dense digest demoted to admin-tier (S); T2 tap as a one-decision card with a conservative safe-timeout default (S); UX-simplicity gate + surface-tier router (M).

## 5. Kills recorded (panel §, for the anti-duplication registry)
cross-audit lobe (→ folded into insight-bus emitters); agenda self-critique (→ dream cycle); standalone preference-prior module (→ one artifact from dream); second generalized fitness card + `metabolism_lobes.yml` (→ charter registry is the single registry); triplicate key schedulers (→ one Multi-key build); dead-code/CI-flakiness scanners as *autonomous docket sources* (→ digest-only until calibrated); **any autonomous edge flipping a scored/authority surface (HARD-FENCE — kill-on-sight guardrail in `lifecycle.py`)**.

## 6. Operator decisions (ratify before the phase that needs each)
1. **Roster cap** (V2-C): the number of active display-tier lobes the mind may run, and confirm a hit surfaces as a digest ASK (not a silent block). *Recommend: start at current-roster + 3; surface as ASK.*
2. **Residual promotion-launder acceptance** (V2-C): the tier fence catches synapse-tier raises, but a display lobe a downstream consumer reads *as if* scored is a launder the fence can't see. Accept + add a periodic operator-visible authority audit. *Recommend: accept + quarterly audit in the digest.*
3. **Multi-key placement** (V2-B, ops): operator creates `CLAUDE_CODE_OAUTH_TOKEN_1/2/3` as GH secrets (values operator-only; the loop never sees them). Whether 3 keys is the right number or a 4th is wanted.
4. **Kill posture** (confirmed 2026-07-09): regime-aware, tap-on-doubt (R-V2-10). No new decision unless the operator wants faster fully-auto kills.

## 7. Top risks (operator awareness)
Quota belief-state is unobservable → early-weeks surprise 429s until the ledger calibrates (mitigate: `weekly_reserve_pct`, conservative estimates). Redline surface widens 3× (mitigate: R-V2-4 gate). Roster cap can stall legitimate growth (mitigate: surface as ASK). Autonomous demotion can kill a starved/off-season organ (mitigate: logic-failures-only + regime-aware + adversary veto). The T2 promotion chokepoint is only as good as the "raises authority" definition (mitigate: periodic authority audit). Regime-aware human-in-loop is deliberately slower on kills (operator-confirmed trade).

## 8. Clocks / sequencing
V2-A first (inert, decision-free — pure mind). V2-B next (needs the redline gate + operator key placement). V2-C after operator ratifies §6.1–6.2. V2-D throughout. The whole v2 stays inert under `AUTONOMY_PAUSED`; first meaningful organism-state read tracks the TIL/other-lobe fitness-sensor maturation (~2026-10-15). Arming stays the operator's single act.
