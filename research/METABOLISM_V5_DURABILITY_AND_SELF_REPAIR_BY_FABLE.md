# Metabolism v5 — Durability, Visibility & Self-Repair (make the breathing loop survive its own mistakes)

**Status:** RATIFIED design + partial build landed 2026-07-11 (this session). Remaining waves ranked for dispatch.
**Owner program:** `autonomic-loop` (extends `METABOLISM_V4_FIRST_BREATH_BY_FABLE.md`).
**Operator directive (2026-07-11):** get the multi-key OAuth infra wired with graceful fail-over; wire the arm/pause switch into the admin panel; then sweep the whole lobe for ways to make it a more robust, durable, self-improving, goal-aware organism that fixes its own mistakes, audits its own errors, and continually improves engines / signals / models / frontend / backend.
**Method:** two adversarial audits (opus) over the armed-loop surface — a durability audit (11 stall/wedge/silent-degrade failure modes) and an intelligence audit (goal-awareness, sensing, prioritization, learning, self-repair, scope) — each finding carrying file:line receipts. This Fable adjudication ranks them and records what shipped.

---

## 0. Executive ruling — v4 installed the nervous system; v5 gives it a body that heals

v4's ruling was "the cage is sound; the tiger was never installed" — it made every stage real and chained, wired memory to authorship, and deepened the eye. This sweep, run against the v4-armed surface, found the loop can now *run* but cannot yet *survive itself*: once armed it would stall silently at the first transient failure, forget its own rate-limit state on every git reset, and — most importantly against the operator's mandate — has **no way to notice or repair a mistake it made**. The intelligence audit confirms the complementary gap: the loop senses its own vitals well but is nearly **blind to the health of the system it is supposed to improve** (CI, render, production data-freshness), and its prioritization has no discipline against monoculture or maintenance-starvation.

The ruling is the same shape as v4: **build the missing organs display-tier and deterministic, keep the pause gate and the fences untouched, let an LLM only de-escalate/rank and never originate.** Nothing here arms the loop; everything is inert until the operator's switch flips.

### What shipped this session (already merged or in-flight)

| Ship | Addresses | PR |
|---|---|---|
| Multi-key OAuth fail-over — pool waterfall (broker-lane-gated, non-cooling-first), 429/529 cooling + fall-through, 403 auth-dead, connection/5xx walk-then-reraise, **build-lane key actually reaches the CLI** (`${!METABOLISM_KEY_REF}` bridge) + retry-with-next-key on key-indicting failures | operator directive #1; audit MAJOR-4 (partial) | #2282 (merged) |
| Admin panel **Metabolism tab** — arm/pause switch on `AUTONOMY_PAUSED` (GitHub Variables API), status hero, key-pool health, recent-runs board, plain-word copy, read-only degrade w/o token | operator directive #2 | #2281 (merged) |
| Learning-wire repair — **lobe threaded into minted contracts** (strategic memory was 100% filtered out), regime-triage flags from `regime_one.json` w/ staleness gate, lesson `lobe` field for recall relevance | intelligence audit §4 (silent break) | #2285 |
| Workflow durability wave — **auto-chain BUILD+MERGE crons** (were dispatch-only → loop dead-ended at adjudicate), adjudicate iterates all pending cycles, drop `-X theirs`, commit `key_ledger.jsonl`, `METABOLISM_MERGE_PAT` wiring, **cron GC** (leaked-worktree reaper), **`if: failure()` operator notify on all 9 workflows**, admin-token VPS delivery | audit BLOCKER-1/3, MAJOR-4/6/8, MINOR-10/11 + visibility | #2287 |
| Always-on `fences.yml` — the 3 required checks report on every PR (path-gated ci.yml copies would wedge non-metabolism PRs if required) | arming Act 2 prerequisite | #2288 |

That closes audit BLOCKER-1, BLOCKER-3, MAJOR-4, MAJOR-6, MAJOR-8, MINOR-10, MINOR-11, the intelligence §4 silent break, and both operator directives. The rest is ranked below.

---

## 1. Rulings (R-V5-1 … R-V5-10)

**R-V5-1 — Failed dispatches must be re-attemptable, not silently dropped (audit BLOCKER-2).** `_journal_dispatch` writes `finish_stage(..., "done")` for *every* terminal record including errors/aborts; `_is_dispatch_done` treats `done` as claimed → a transient build failure (timeout, false foreign-file abort) permanently drops that proposal. Fix: journal a real terminal status — `done` only when `dispatched`, else `failed`; `_is_dispatch_done` treats `running`/`done`/`dispatched` as claimed and allows `failed` to re-attempt under a bounded retry counter (`max_build_attempts` in `config/metabolism_budget.yml`, default 2). A proposal that fails N times becomes an operator-tap insight, never a silent vanish.

**R-V5-2 — `running` markers need a TTL reaper (audit MAJOR-7).** No stale-marker expiry exists; a stage killed mid-run (job timeout, runner reboot, mem-sentinel OOM) leaves `running` forever, and `_is_dispatch_done` treats `running` as claimed → the proposal wedges with no expiry. Fix: `is_stage_done`/`_is_dispatch_done` treat a `running` marker whose `started_at` is older than `2× stage_timeout` as **stale → not claimed** (eligible for re-run); the cron GC additionally rewrites stale `running` → `failed` so the trajectory is honest.

**R-V5-3 — Cooling horizon must be respected (audit MAJOR-5).** `is_cooling` clears *any* cooling (including a 7-day `weekly`) on a single `outcome=="ok"` row, and the build lane writes that `ok` row at pick-time *before* the session runs. So a weekly-exhausted key is re-picked on the very next cycle. Fix: only a same-or-shorter-horizon success clears cooling — a `window` cooling may be cleared by a later `ok`; a `weekly`/`auth` cooling clears only after `reset_hint` passes (or an `ok` recorded *after a confirmed successful completion*, not at pick-time). Move the build lane's `ok` accounting to after `returncode==0`. (Note: the fail-over PR #2282 already records success post-call in the waterfall path; this ruling extends the same discipline to the build-lane subprocess path and the horizon-aware clear.)

**R-V5-4 — SLA maturation must parse dates, not compare strings (audit MAJOR-9).** VERIFY/DREAM decide contract maturation with lexical `check_by <= today_str`; an LLM-authored `check_by` of `"2026-7-15"` or `"2026-07-15T00:00:00Z"` mis-orders (never matures, or matures early) → contracts silently never grade → DREAM never reaches `MIN_CLOSED_CONTRACTS` → calibration permanently `insufficient_data`. Fix: parse `check_by` to a `date` on every read path and validate format at docket-write; a malformed `check_by` is quarantined as an `operator_tap` insight, not a silent lexical mis-order.

**R-V5-5 — Sense the system the loop lives in, not only itself (intelligence audit §2).** Both freshness sensors hard-filter to metabolism-owned artifacts (`if "metabolism" not in op: continue`), and the CI-red detector is dead (its `ci_status_artifact` is null with no producer). The stores whose staleness has repeatedly frozen the pipeline (price, EDGAR, GDELT) are invisible. Fix, display-tier: (a) a deterministic emitter that writes the `ci_status_artifact` the dead `anomaly_monitor` detector already expects (read from the GitHub checks API or a committed CI-status file); (b) relax the metabolism-only filter to an allowlist that includes the price/EDGAR/GDELT freshness SLAs already in `config/synapse.yml`; (c) a render-budget-drift row from the `[timing]` ticks. This is the single biggest sensing-blindness fix and is the pathway for "improve backend robustness."

**R-V5-6 — Prioritization needs anti-monoculture + a maintenance floor (intelligence audit §3).** Anti-repetition is title-hash only — the loop can propose "add a context organ" every cycle with different titles and pass. The 40/40/20 URGENT/NOVEL/RESEARCH split is a docstring, unenforced and absent from the prompt. Fix, deterministic: (a) load the last N dockets, compute per-*kind* proposal frequency, inject a "recently over-proposed kinds" advisory into the orchestrator prompt; (b) reserve ≥1 docket slot for the least-recently-touched bucket (a deterministic explore floor, not an LLM choice); (c) move the split into `config/metabolism_budget.yml` as enforced `min_urgent`/`maintenance_floor` keys. Prevents novel-build monoculture even when sensors are quiet.

**R-V5-7 — The loop must notice when it hurt itself (intelligence audit §5; operator "fix its own mistakes").** There is no pre/post-merge fitness comparison anywhere; a self-caused regression is at best incidentally caught by anomaly_monitor days later with no PR attribution. Fix, display-tier detection only (no auto-revert — the `auto_revert_without_operator` ban stands): after the merge lane fires, snapshot `organism_state` before/after and emit a `self_regression` insight-bus row when a lobe composite drops beyond a band, attributed to the merged `cycle_id`/PR. This closes the "did my merge break me" blindness that makes self-repair impossible today.

**R-V5-8 — Give the revert PLAN an operator-armed executor (intelligence audit §5).** VERIFY already emits a `revert_plan` that its own note calls "a PLAN artifact only"; no executor exists. Fix: a fenced, `AUTONOMY_PAUSED`-gated, two-key executor (mirrors the R-V4-2 build-dispatch fence) that turns a graded clean-overfit `revert_plan` into a **draft revert PR** — never an auto-merge. Turns a dead text artifact into an actionable, gauntlet-consistent repair the operator approves.

**R-V5-9 — Wire the dark feelers into the scheduled cycle (intelligence audit §2/§6).** `scout.scan` (uncovered-domain detection → charter proposals — the loop's lobe-*creation* feeler) and `run_anomaly_monitor` are imported by no scheduled path. Fix: add both to the live SENSE stage (`metabolism-agenda.yml` + the shadow harness). Lobe creation is one of the three mission goals and is structurally unreachable until this lands.

**R-V5-10 — Refused / deferred.** (a) Anything that arms the loop (the operator's switch stays the sole arming act). (b) Any LLM origination of a signal, score, regime flag, or triage class — the regime-triage read (R-V4/learning-wire) is a deterministic JSON field read, and must stay so. (c) Auto-execution of a revert or merge without the two-key + operator gate. (d) The DO_NOT_REBUILD standing kills (rotation×cycle confluence, short-side lobe, CHF-through-metabolism until the 2026-10 clock) are not touched by any ruling here. (e) UI/model/signal *authoring* by the loop expands only after R-V5-5's sensing exists — you cannot improve a surface you cannot see.

---

## 2. Wave plan (ranked by likelihood × blast-radius, cheapest-durable first)

**Wave A — Never-stuck (durability core).** R-V5-1 (re-attemptable dispatches), R-V5-2 (running-marker TTL), R-V5-3 (cooling horizon). All three are the "a transient failure becomes a permanent silent drop" class — the highest-likelihood defects once armed. Pure `scripts/metabolism_build.py` + `engine/neuralweb/key_pool.py` + `scripts/metabolism_journal.py` + `scripts/metabolism_gc.py`, with unit tests. No new surfaces.

**Wave B — Honest maturation.** R-V5-4 (parse `check_by`). Small, self-contained across `verify.py`/`metabolism_verify.py`/`dream.py`; protects the entire learning clock from a single malformed LLM-authored date. Add read-path schema validation.

**Wave C — See the system.** R-V5-5 (pipeline-health sensing). The largest sensing win and the prerequisite for the loop ever improving backend robustness. Display-tier emitters into the existing insight-bus; the dead CI detector is already waiting for its artifact.

**Wave D — Prioritization discipline.** R-V5-6 (anti-monoculture + maintenance floor). Deterministic docket-history read + budget-config enforcement; keeps the armed loop from novel-build monoculture.

**Wave E — Self-repair (the operator's headline ask).** R-V5-7 (merge-scoped regression detection) then R-V5-8 (operator-armed revert executor) then R-V5-9 (scout/anomaly into the cycle). This is the wave that makes the loop able to "notice and fix its own mistakes." E must follow A–B (a self-repair loop on top of a loop that silently drops work would chase phantoms).

Each wave ships behind the pause gate, exercised in the shadow harness first (R-V4-1), verified in CI, one PR per ruling where practical.

---

## 3. Arming status (operator handoff)

The loop remains **paused** (`AUTONOMY_PAUSED=true`, seeded this session so the state is explicit and the admin switch has a variable to toggle). The code/config infrastructure the operator asked for is wired: multi-key fail-over, the admin arm/pause switch, the build-lane key bridge, the auto-chain crons, the fences workflow. The remaining arming acts are **operator credential/access-control steps** (mint the merge PAT, set the OAuth pool secrets, apply the branch-protection ruleset) — these are handed off in the session summary, not performed autonomously, because minting credentials and modifying repo access controls are operator-only actions. Waves A–E above are the durability/intelligence upgrades to build *before* the operator flips the switch, in the ranked order given.
