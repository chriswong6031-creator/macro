# Metabolism v4 — First Breath (close the loop, wire the memory, deepen the eye)

**Status:** RATIFIED design; build waves dispatched 2026-07-11.
**Owner program:** `autonomic-loop` (extends `AUTONOMIC_LOOP_MASTERPLAN_BY_FABLE.md`, `METABOLISM_V2_MASTERPLAN_BY_FABLE.md`, `METABOLISM_V3_MEMORY_CONTEXT_BY_FABLE.md`).
**Operator directive (2026-07-11):** full sweep review of NW's intelligence layer + self-improving loop; radically improve the self-looping mechanisms — self-improvement, lobe improvement, lobe creation, freedom to adjust, real working memory of direction — toward an autonomous intelligence that detects market-environment change early, finds patterns/confluences/asymmetries humans miss, and beats human decision-making in signal quality.
**Method:** 9-lane read-only census (sonnet) + 3-lens adversarial assessment (opus: agency, memory/direction, market-intelligence) → this Fable adjudication. All load-bearing claims below were verified in-repo by the panel (file:line receipts in the census record).

---

## 0. Executive ruling — the cage is sound; the tiger was never installed

v1–v3 built a constitutionally excellent cage (fences F0–F3 all CI-wired and fail-closed; origination ban refused before evidence at `constitution.py:302`; two-key denies on shared run_id) around a loop that **cannot run even if armed**. The sweep found five structural breaks, none of which is the INERT gate:

| # | Break (verified) | Consequence |
|---|---|---|
| B1 | BUILD dispatch is a documented stub — `scripts/metabolism_build.py::_dispatch_build_session()` returns `{dispatched:False, stub:True, reason:'v2b_unit6_stub'}` on every path | The loop can never author code. All three mission goals (self-improve, improve lobes, create lobes) route through BUILD. |
| B2 | Cadence severed: only heartbeat/agenda/propose have crons; adjudicate/build/merge are `workflow_dispatch`-only; **no verify or dream workflow exists at all** | A cycle stalls at ADJUDICATE forever; VERIFY/LEARN/DREAM never fire; the loop cannot close. |
| B3 | LEARN is dead: `dream.load_preference_prior()` has **zero callers**; PROPOSE imports none of recall/organism_state/insight_bus/trajectory/preference_prior | The mind writes lessons it never reads at the moment of authorship. Anti-repetition exists only at ADJUDICATE, after the dead idea is already drafted. |
| B4 | Lifecycle proposes into the void: `charter_proposals/` and `lifecycle_docket/` have **no consumer**; PROPOSE is hardcoded to the TIL lobe | Lobe creation/demotion/retirement is structurally unreachable; 96 of 97 chartered lobes are outside the loop entirely. |
| B5 | `memory.append_fitness_history()` writes `data/metabolism/fitness_history.jsonl` (single file); `organism_state._load_fitness_history()` reads `data/metabolism/fitness_history/<lobe_id>.jsonl` (per-lobe dir) | Trajectory slopes silently fall back; the appended history is write-only. Would corrupt the first weeks of armed memory. |

And the intelligence layer itself (the eye the loop is supposed to sharpen) has four capability ceilings, all fixable with **deterministic display-tier organs** that ship on the normal render path, independent of arming:

| # | Ceiling (verified) | Mission cost |
|---|---|---|
| C1 | Confluence is pairwise co-firing lift only (`confluence.py:_build_confirms_edges`); no K-of-N independent-agreement quorum, no numeric confluence strength | The asymmetric-confluence primitive the mission demands cannot be expressed. |
| C2 | No temporal/sequence memory anywhere in the intelligence tier — confluence graph and 9 contradiction pairs are nightly snapshots | "Detect environment change early" is structurally impossible: the system cannot see persistence, strengthening, or decay. |
| C3 | `covariance_spine.py` (200-draw circular-shift independence rail — the single most sophisticated reasoning organ) is a display dead-end | Correlated engines double-count as "confirmation"; true breadth of agreement is never computed. |
| C4 | Contradiction vocabulary frozen at 9 hand-coded pairs; the generative loops (SF, CHF, cortex) are dark/never-fired | The system cannot expand its own cross-signal vocabulary even deterministically. |

Fragmentation finding (F1): five propose-test-learn loops (metabolism, Signal Foundry, CHF, cortex staking, evidence clocks) hold **separate blocklists and separate memories with no cross-read** — a construction killed in one loop is invisible to the others.

**The ruling:** v4 does three things and refuses a fourth. (1) Install the tiger — make every stage of the loop real, chained, and exercisable in shadow while paused. (2) Make memory the steering mechanism — recall, priors, insights, trajectory, and a durable mission self-model reach the authorship prompt. (3) Deepen the eye — independence-discounted confluence strength, a temporal tape, and deterministic vocabulary discovery, all display-tier. (4) **Refused:** anything that arms the loop (operator's switch, untouched), anything that flips kernel regime-pooling before the 2026-10 FDR clock, any confluence routing to a money-path surface, any LLM origination anywhere.

## 1. Rulings (R-V4-1 … R-V4-12)

**R-V4-1 — Shadow-first law.** The loop must be exercisable end-to-end while `AUTONOMY_PAUSED` stays true (R-AUT-2 already permits shadow artifacts + draft PRs). A first-class shadow harness (`scripts/metabolism_shadow_cycle.py`) runs SENSE→AGENDA→PROPOSE→ADJUDICATE→(BUILD dry-run)→VERIFY(seeded)→DREAM against the real repo state and writes **only** under `data/metabolism/shadow/<cycle_id>/` — the real stores stay virgin until arming (the panel's warning: never fabricate memory to make the loop "look alive"). Shadow runs are the arming evidence, not a simulation of it.

**R-V4-2 — The hands are Sonnet, draft-only, and fenced at dispatch.** `_dispatch_build_session()` becomes real: a headless **sonnet-pinned** builder session (never inherits the caller's model), operating in its own worktree off fresh `origin/main`, restricted to the proposal's declared target files, hard-refusing any IMMUTABLE-set path **at dispatch time** (defense-in-depth ahead of the F2 CI fence), producing a **draft PR only**. Armed-gated (`AUTONOMY_PAUSED` re-checked immediately before session launch) and capability-broker-keyed (`claude_code_oauth_N` rows).

**R-V4-3 — Memory must reach authorship.** The PROPOSE prompt context gains five deterministic, freshness-stamped, byte-budgeted blocks: relevance-ranked recall (FAIL-floor preserved), `preference_prior.json` (finally consumed), open insight-bus rows, per-lobe trajectory + strategic gap, and the mission block (R-V4-4). All `is_context_only=True` / informational — the anti-repetition FLAG stays a flag (R-V3-3 unamended); the grant path (deterministic screen + two-key) remains the sole authority.

**R-V4-4 — The mission is a file the loop can read and can never edit.** `config/nw_mission.yml` — the operator's endgame (context-accrual directive, the beat-human-judgement mission, the standing epistemic laws in machine-readable form) plus the program's current strategic posture — **joins the IMMUTABLE set** (the mind may not rewrite its own purpose). It is injected into every orchestrator-tier prompt. Beside it, a deterministic **strategic memory** rollup (`engine/metabolism/mission.py`) accumulates one append-only row per closed contract `{construction, lobe, verdict, measurement_lens_class, cycle_id}` so the mind sees the trajectory of what was tried and how it resolved — the "real working memory of what it's doing and the direction we are going."

**R-V4-5 — One kill-registry, compiled everywhere.** `research/DO_NOT_REBUILD.md` becomes the single source compiled by one deterministic script (`scripts/compile_loop_blocklists.py`) into every loop's blocklist surface (Signal Foundry blocklist, CHF kill-mask/priors, metabolism case-law screen corpus). Hand-curated divergent copies are retired; the compiler runs in CI so drift is a red check, not a silent fork.

**R-V4-6 — Confluence strength = independence-discounted breadth, display-tier, deterministic.** New organ `engine/neuralweb/confluence_strength.py`: for each (symbol/complex, as_of, direction, horizon), the count of **structurally independent** confirming engines — each firing engine discounted by covariance-spine participation-ratio redundancy — emitted as `n_independent_confirming` + a partial-credit strength scalar. Display-tier with the standard `assert_no_authority` walk; any future routing to a ranked/money surface requires its own pre-registered gauntlet. This is explicitly **not** the forbidden fused meta-router (no vetoes, no buy-decisions, no positioning keys) and excludes the rotation×cycle pairing (DON'T-TEST stands).

**R-V4-7 — The temporal tape.** A PIT append-only ledger (`data/neuralweb/confluence_tape.jsonl`, nightly is the sole advancer; intraday lanes discard) records each night's confluence-strength rows and contradiction-pair firings. A deterministic sequence organ (`engine/neuralweb/confluence_sequence.py`) derives persistence streaks ("pair X has fired N consecutive sessions"), strengthening/decay slopes, and regime-stamped episode boundaries. This is the layer that makes early environment-change detection *expressible*. Cheap by construction (append + slopes); render-budget cost measured with `[timing]` ticks before merge.

**R-V4-8 — Vocabulary discovery is a z-scan, and the LLM may only investigate.** `anomaly_monitor`-style robust-stats scan over the tape for engine pairs whose co-occurrence spikes vs their circular-shift null → display-tier `insight_bus` candidate rows for gauntlet/operator review. No LLM declares a pair; no candidate touches organ state (NAR-R4/TI-R1 respected).

**R-V4-9 — Lifecycle gets an applier; every application is still a gauntleted PR.** New `engine/metabolism/applier.py` consumes `charter_proposals/` and `lifecycle_docket/` items, routes them through the normal PROPOSE→ADJUDICATE two-key, and (post-grant, when armed) emits **draft PRs** editing `config/lobe_charters.yml` — display-tier states only. The tier-raise refusal in `lifecycle.py` is untouched and re-asserted in the applier (double fence). In shadow mode the applier writes the would-be PR diff under `shadow/`.

**R-V4-10 — PROPOSE generalizes by charter, not by hardcode.** A lobe becomes loop-manageable when its charter declares `fitness_sensors` (sensor ids resolvable to real graded stores). The PROPOSE system prompt is assembled from the charter; TIL remains the pilot (its sensors are the only mature set until 2026-10-15); lobes without declared sensors get SENSE-only coverage (health/staleness) — **no fabricated fitness, ever**. Accrual clocks are honest: a proposal against an `accruing` fitness card must carry `check_by ≥` the card's maturity date.

**R-V4-11 — Kernel regime-conditioning stays behind its clock.** v4 ships **nothing** that flips kernel pooling to regime-conditional (Signal Commons: FORBIDDEN before the kernel-FDR 2026-10 batch). The tape stamps rows with the current regime bucket (display context); historical spine stamp-backfill is chartered as a **follow-up docket item** with its own scope fence, not built here.

**R-V4-12 — Ops honesty.** The known ops defects ship fixed with the cadence wave: heartbeat's `git add` on a never-created file inverting clean no-ops into red runs (guard-echo law: `if/fi`, never `[ ] && …` as a step's last line); propose's full-depth checkout timing out against nightly contention (shallow fetch + retry + off-peak cron); agenda/propose schedule inversion (SENSE+AGENDA must complete before PROPOSE reads them: agenda 09:15, propose 09:45); `$RUNNER_TEMP` not `/tmp`.

## 2. What v4 does NOT do (refusals of record)

- **No arming.** `AUTONOMY_PAUSED`, secrets (`CLAUDE_CODE_OAUTH_TOKEN_1/2/3`, `ANTHROPIC_API_KEY`, Telegram), branch protection, REQUIRED checks, and the merge PAT are the operator's five acts — v4 delivers `docs/METABOLISM_ARMING_CHECKLIST.md` with exact commands and the shadow-cycle evidence, and stops there.
- **No LLM-originated anything** on any scoring/state path (CONST-ART1/NW-ART1 unamended). Every new construct in this program is a pure function of existing deterministic artifacts.
- **No money-path routing** of confluence strength/tape/quorum without a fresh pre-registered gauntlet (display-first law).
- **No kernel pooling change** (R-V4-11). No re-inclusion of `__unstamped__` cells (the anti-conservative double-count stays dead).
- **No new UI surfaces this wave.** JSON artifacts + admin-tier committee exposure only; public surfaces need `docs/DESIGN_DOCTRINE.md` compliance and their own wave.
- **No embeddings/vector DB** (R-V3-2 stands); no persistent sessions (R-AUT-3); no second lobe registry (R-V2-7).

## 3. Wave docket (each wave = fresh worktree off `origin/main` → sonnet build → opus adversarial review → fix → PR → same-day squash-merge)

| Wave | Lane | Contents | Files (primary) | Depends |
|---|---|---|---|---|
| W0 | masterplan | this document | `research/METABOLISM_V4_FIRST_BREATH_BY_FABLE.md` | — |
| W1 | the hands | real BUILD dispatch (R-V4-2) + dispatch-time immutable refusal + key-pool integration + tests | `scripts/metabolism_build.py`, `tests/` | — |
| W2 | the pulse | `metabolism-verify.yml` + `metabolism-dream.yml` (new), adjudicate cron chain, schedule fix, heartbeat/checkout/RUNNER_TEMP fixes (R-V4-12) | `.github/workflows/metabolism-*.yml` | — |
| W3 | mission + one-registry | `config/nw_mission.yml` (IMMUTABLE), `engine/metabolism/mission.py` strategic memory, `scripts/compile_loop_blocklists.py` + CI drift check (R-V4-4/5) | new files + fence registration | — |
| W4 | the eye | confluence_strength + temporal tape + sequence organ + z-scan discovery (R-V4-6/7/8), synapse registration + SIGNAL_BUS regen, nightly wiring w/ `[timing]` | `engine/neuralweb/confluence_strength.py`, `confluence_sequence.py`, `scripts/` wiring | — |
| W5 | steering memory | wire recall/prior/insight-bus/trajectory/mission into PROPOSE + orchestrator_brain (R-V4-3), fitness-history fork fix (B5), per-lobe trajectory rows, charter-driven PROPOSE (R-V4-10), lifecycle applier (R-V4-9) | `engine/metabolism/*` (single-lane owner of hot files) | W3 |
| W6 | first breath | shadow-cycle harness (R-V4-1) + first committed shadow run + `docs/METABOLISM_ARMING_CHECKLIST.md` | `scripts/metabolism_shadow_cycle.py`, `data/metabolism/shadow/`, docs | W1,W2,W5 |

Build-hygiene laws binding on every wave: new test files added to the ci.yml pytest whitelist; synapse count-pin (`tests/test_signal_bus_doc.py`) regenerated not hand-edited; no bare `git stash`; workflows use `if/fi` guard blocks; every new module NEVER-RAISE with a corrupt-artifact test; new IMMUTABLE entries registered in `check_self_mod_fence.py` + grader manifest in the same PR.

## 4. Follow-up docket (chartered, not built here)

1. **Regime stamp backfill** onto historical spine rows (feeds kernel cells *data*; pooling flip stays behind the 2026-10 clock) — own scope fence, off-render compute.
2. **Cycle-ledger closed loop** — 5,081+ graded CN sector-cycle + 5,769+ country-cycle outcomes have no auto-calibration reader; the `market_state_tune` bounded-deterministic-tuner pattern is the proven legal template. Signal-path change → own pre-registration + adjudication.
3. **Loop-family intake unification** — SF candidates / CHF mechanism cards / cortex stakes as insight-bus emitters into the metabolism agenda (beyond the blocklist unification shipped in W3).
4. **CHF stale lane + TIL earliness-grader empty-summary** — small independent fixes, spun off as standalone tasks.
5. **Committee/operator UI for tape + strength organs** — needs DESIGN_DOCTRINE pass.

## 5. Clocks

- **Now + nightly:** W4 organs accrue tape rows from first merged render.
- **On merge of W6:** first shadow-cycle artifact = the operator's arming evidence; arming checklist live.
- **2026-07-25:** shadow-cycle re-run + review (are dockets sane? adversary vetoing? grounding clean?).
- **2026-10-15:** TIL fitness maturity — first armed cycles become meaningful (unchanged from v1).
- **2026-10:** kernel-FDR batch — regime-conditioning follow-up may be proposed (R-V4-11).
