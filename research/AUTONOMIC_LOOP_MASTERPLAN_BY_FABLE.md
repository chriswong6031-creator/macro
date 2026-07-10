# The Metabolism — autonomic self-improving loop for Neural Web

**Status:** RATIFIED design; Phase 0 dispatched
**Date:** 2026-07-09
**Owner program:** `autonomic-loop` (the Metabolism)
**Operator directive:** make TIL — then all NW lobes — perpetually self-running and self-improving; give the LLM layer code/GitHub/VPS access under checks-and-balances; full AI handoff. "Bypass the no-LLM-changes rule; we integrate checks and use Fable orchestration."
**Method:** orchestrator adjudication → 5-lens Opus red-team + creative panel (35 designs) → Opus xhigh judge (5 kills, phased docket, 5 operator-ratify risks) → this Fable adjudication.

---

## 0. Executive ruling — no rule is bypassed; the rule becomes the cage

The operator asked to "bypass the no-LLM-changes rule." **We do not, because we do not need to, and bypassing it is the one move that would make this dangerous.** Two facts dissolve the tension:

1. **The LLM-origination ban governs the runtime *signal path*, not code authorship.** The law is "LLMs may never originate signals, scores, or escalations" — an LLM inventing a trading opinion and injecting it into a live score. It has *never* prohibited LLMs from writing code through the PR gauntlet: this entire program (~21 PRs today, and effectively the whole repo) is LLM-authored. Self-improvement = taking the loop that already runs *when the operator prompts* and making it **self-scheduling, self-sensing, self-directing**. The signal path stays deterministic. The gauntlet stays the promotion gate. **The law is the checks-and-balances the operator asked for** — not an obstacle to remove.

2. **The dangerous request — "a lobe that stores all security details" — is replaced, not built.** Secrets in a git-committed NW artifact would be the worst vulnerability we could ship. Instead: secret *values* stay in GitHub Secrets + the runner keychain (where `VPS_DEPLOY_KEY` and `CLAUDE_CODE_OAUTH_TOKEN` already live and are already used by `whitehouse-sentinel.yml`); a **capability broker** lobe stores only the *manifest* (what powers exist, scopes, rotation, allowed lanes/tiers) plus an **append-only audit tape** of every capability use. Full self-knowledge of its powers; never a key byte in data.

> **The organizing principle: build the cage before the tiger.** The loop can, in principle, edit its own fitness graders and its own fences. Therefore the immutability fence, self-modification fence, and capability broker are **Phase 0 prerequisites** — no stage of the loop performs a single autonomous merge until the cage exists and CI enforces it. This reorders the panel's Phase-B fences ahead of the Phase-A pilot (top-risk #1).

## 1. Architecture — the six-stage metabolism

```
      ┌──────────────────────────────────────────────────────────────┐
      ▼   (each stage = a stateless GH-Actions cron on the macstudio runner;              │
          first line of every job: if vars.AUTONOMY_PAUSED != 'true')                     │
1 SENSE      nightly graders + CI/coverage health → per-lobe FITNESS CARD (typed, machine-readable)
2 PROPOSE    scheduled stateless Opus lobe-brain reads fitness card + masterplan + ruling graph
             + DO_NOT_REBUILD + ACTIVE_BUILD_MAP → structured DOCKET (budgeted; each proposal
             registers a pre-committed fitness contract in the trial ledger — spending DSR budget)
3 ADJUDICATE Fable-orchestrator run + Fable-adversary run (two DISTINCT run_ids) rule vs case law;
             T1/T2 require a governance row-PAIR (the "two-key" — NOT a live second session)
4 BUILD      Sonnet worktree builder → Opus adversarial review → fix → gated merge
             (the exact pipeline that shipped 21 PRs today — proven, unchanged)
5 VERIFY     after check_by: re-grade REALIZED fitness delta vs the registered contract.
             Miss → measurement-lens triage (regime vs overfit vs estimator) → revert or operator-tap
6 LEARN      lessons → memory files + ruling graph + quarterly self-assessment → next cycle's priors ─┘
```

**No persistent sessions, ever.** Background sessions die silently on limits (it happened *today*, mid-fix on W8). Every stage is stateless cattle: read git state → act → write git state → die. The organism's entire "mind" is git artifacts (fitness cards, dockets, governance rows, journals, memory). Crash recovery = the workflow-journal resume that recovered W8, generalized. This is a hard law, not a preference (R-AUT-3).

## 2. Rulings (R-AUT-1 … R-AUT-12)

**R-AUT-1 — The signal path stays deterministic; the loop authors CODE, not signals.** No loop-authored change may make an LLM originate a runtime signal/score/escalation. Promotion of any scored path stays behind the gauntlet (T2). The LLM-origination law is unamended and CI-enforced as before.

**R-AUT-2 — The cage precedes the tiger.** No autonomous merge (any tier) executes until Phase 0 ships and CI enforces: the grader-immutability manifest (F1), the self-modification fence (F2), and the capability-broker redline (F3). Until then the loop runs **inert** — it may open DRAFT PRs and write shadow artifacts, but `AUTONOMY_PAUSED` defaults `true` and merge lanes are unarmed.

**R-AUT-3 — Stateless-cattle law.** No loop stage may depend on a persistent/long-lived session. All state in git. Every stage idempotent and journal-resumable. A stage that cannot be made idempotent does not ship.

**R-AUT-4 — Autonomy tiers (the trust ladder).**

| Tier | Scope | Gate |
|---|---|---|
| **T0 auto** | docs, tests, display-tier context organs, bug fixes, coverage, lint | build → Opus review → green → merge, fully autonomous |
| **T1 two-key** | new engines, new themes, collectors, UI, algorithm changes, new lobes | orchestrator **and** adversary governance row-pair, both `approve` |
| **T2 operator-tap** | scored-path/authority promotion, guard/CI/hook changes, secret arm/rotate, spend increase, VPS runtime-signal changes | one-tap operator digest; nothing proceeds without an operator `grant` row |
| **IMMUTABLE** | the graders (F1 set), the fences (F2/F3), `.claude/hooks/**`, `.github/workflows/**`, autonomy/budget/capability config, this tier table | CI **hard-refuses** any loop-authored PR touching these — fail-closed, no exceptions |

**R-AUT-5 — "Loop-authored" is attributed by namespace + trailer, not identity.** The loop and the operator share the same OAuth git identity, so author-email cannot distinguish them (load-bearing correction). Loop PRs use reserved branch prefixes (`metabolism/*`, `claude/loop-*`) and a required `Loop-Authored: <lobe> run=<RUN_ID>` commit trailer. The F2 CI job hard-fails any PR carrying that namespace/trailer that touches the IMMUTABLE set. Backed by branch-protection on those paths and a merge PAT minted **without** `workflows` scope.

**R-AUT-6 — Two-key = row-pairs, not live Fables (operator-ratified substitution).** The state law bans persistent sessions and the routing law reserves Fable for the main loop; "orchestrator + adversary" is therefore realized as `governance.jsonl` / `capability_grants.jsonl` **row-pairs written by two different stateless run_ids** (an orchestrator run and an adversary run, each fresh), never two live Fables disagreeing in real time. The adversary run is a distinct scheduled job with an adversarial system prompt and skin in the game (R-AUT-9).

**R-AUT-7 — The graders are immutable; changing the ruler is a T2 quarantine.** All fitness-producing files (`grade_thematic.py`, `foresight_leadlag.py`, `theme_placebo.py`, `qledger_falsifier.py`, `sample_qledger_placebo.py` + their threshold constants + placebo config) are in a content-hash manifest (mirror `check_house_law_registry.py`). Any loop-authored diff that changes a hash is blocked from T0/T1 and routed to a T2 quarantine that runs OLD-vs-NEW grader over a **frozen replay corpus** and prints the fitness delta on already-merged organs, for operator ratification. Without this the loop can rewrite its own scoreboard (highest-leverage fence).

**R-AUT-8 — Fitness is per-lobe-typed and pre-registered as a DELTA, never a single return-IC ruler.** Each lobe scores on its native sensors (TIL: front-run lead-days, placebo-adjusted hit-rate, falsifier honesty, live-leg quality — never raw coverage alone). Before a fitness-affecting BUILD merges, its docket registers a pre-committed contract in `data/trial_ledger.jsonl` `{sensor, expected sign, magnitude band, check_by, placebo/holdout to beat}`; a sibling of `check_trial_registration.py` hard-fails any such PR with no registered contract. VERIFY grades the realized delta exactly as `qledger_falsifier.py` evaluates `check_by`.

**R-AUT-9 — The adversary has skin in the game.** `data/metabolism/adversary_ledger.jsonl` (append-only) records the adversary run's structured findings + pre-committed tripwire predictions at review time; VERIFY later credits materialized defects it flagged and debits post-merge regressions it missed. A rubber-stamp adversary loses its score. This is the incentive that keeps the second key real.

**R-AUT-10 — Frozen holdout the proposer never sees.** Each sensor corpus is HMAC-partitioned (key in the runner keychain, **never** git) into a PUBLIC score fed to PROPOSE prompts and a SEALED holdout readable only by VERIFY. Promotion and regression-revert decisions use the holdout. Ships only **after** F3's entropy-scan CI is enforcing (else a builder could cache the resolved key into a tracked file — the catastrophic breach, top-risk #4).

**R-AUT-11 — Regime-aware revert (no blind auto-kill).** A build that misses its registered band does **not** get a silent kill-registry row. VERIFY first runs the measurement-lens reassessment protocol (memory `measurement-lens-reassessment-protocol`): separate mechanism-false vs regime-change vs estimator-broken. Clean overfit → auto-revert + `DO_NOT_REBUILD` row. Ambiguous / possible regime change → operator-tap review, revert held. A backtest "FAIL" assumes stationarity; an honest generalizing organ can miss its band in a new regime and must not be auto-killed (top-risk #5).

**R-AUT-12 — Autonomous changes reach the live VPS only via the render tail, never a loop shell.** The loop gets no VPS shell. Changes reach live only through merge → nightly render → the existing push/rsync deploy. Any change to the runtime signal path or a scored surface is fenced behind a T2 `metabolism_live` flag defaulting to shadow/display-tier. Revert-is-rollback (re-render prior-good).

## 3. Capability broker — `neuralweb.capability_broker.v1` (the redline)

`config/capability_manifest.yml` + `engine/neuralweb/capability_broker.py` (sibling of `governance.py`, same NEVER-RAISE contract):
- **Manifest row:** `{capability_id, kind (llm_oauth|github_pat|vps_deploy|api_key), secret_ref (the NAME, e.g. "CLAUDE_CODE_OAUTH_TOKEN"), scope, storage_locus (gh-secret|runner-keychain|env), allowed_lanes, allowed_tiers, rotation_state, kill_state}`. **Never a secret byte.**
- **`resolve(id, lane)`** returns only the ref name + an allowed bool; the caller reads `os.environ[ref]`. The broker never handles the value.
- **Audit tape** `data/neuralweb/capability_audit.jsonl` auto-captures `{run_id, workflow, actor, sha, capability_id, lane, ts}` from the Actions env on every use.
- **Redline CI** (extends `check_validated_claims.py`): high-entropy-string scan + bans any `secrets.*` assignment in the tracked manifest/broker files. **THE REDLINE:** a secret value in a git artifact fails CI hard and is the single unforgivable defect.
- **Break-glass:** `AUTONOMY_PAUSED` repo variable (phone-flippable, no git push, checked at every stage entry AND re-checked late in BUILD) + a secret-revocation runbook + `kill_state` per capability.

## 4. Phase plan (re-sequenced: cage → pilot → generalize)

### Phase 0 — the cage (SHIP FIRST; nothing autonomous runs before this)
| Unit | Size | What |
|---|---|---|
| F0 kill switch + skeleton | S | `AUTONOMY_PAUSED` repo var + one inert stage-cron cloned from `whitehouse-sentinel.yml`, `if: vars.AUTONOMY_PAUSED != 'true'` first line; workflow_dispatch; per-stage timeout |
| F1 grader-immutability manifest | M | content-hash manifest of all fitness files + threshold constants; CI check (mirror `check_house_law_registry.py`); quarantine lane stub |
| F2 self-mod fence | M | namespace+trailer attribution (R-AUT-5) + `self_mod_fence` CI job hard-failing loop-authored diffs to the IMMUTABLE set; branch-protection paths |
| F3 capability broker | M | `capability_manifest.yml` + `capability_broker.py` + audit tape + redline entropy-scan CI (§3) |
| F4 least-privilege lanes | M | per-lane GITHUB_TOKEN permission blocks (PROPOSE = contents:read; BUILD = contents+PR write behind required Opus-review check) + one merge PAT sans `workflows` scope |

### Phase A — the pilot closed loop on TIL (inert until operator arms)
| Unit | Size | What |
|---|---|---|
| A1 workflow-journal + idempotent stages | M | `data/metabolism/journal/<cycle_id>.json` per stage; resume-off-git; orphan-worktree `if: always()` GC |
| A2 OAuth preflight gate | S | `preflight_claude_auth.py` 1-token ping on cheapest tier; corrupt → journaled no-op + `notify.send_telegram` re-place alert (the token corrupted once already) |
| A3 TIL fitness card | M | typed sensor rollup from `grade_thematic` stages + `foresight_leadlag` + `theme_placebo` + `qledger_falsifier` → `data/metabolism/fitness/til.json` |
| A4 PROPOSE lobe-brain (TIL) | M | stateless Opus job: fitness card + masterplan + ruling graph + kill registry → docket with registered trial-ledger contracts; content-hash dedup vs open PRs |
| A5 ADJUDICATE row-pair | M | orchestrator + adversary runs → `governance.jsonl` grant/deny pairs; adversary ledger (R-AUT-9) |
| A6 VERIFY realized-delta grader | M | re-grade vs contract; regime-aware triage (R-AUT-11); revert or operator-tap |
| A7 budget governor + circuit breaker | S | `metabolism_budget.yml` (IMMUTABLE) per-cycle token/spend + docket-size caps; N-consecutive-fail → auto-pause lobe (reuse `healthcheck.py` breaker) |
| A8 operator digest + audit | S | weekly one-page "what the organism did" + phone kill switch surfacing + audit-tape link |

**First autonomous merge is gated on: Phase 0 green AND operator sets `AUTONOMY_PAUSED=false`.** That flip is the one irreducible human act (§6).

### Phase B — hardening (before widening beyond TIL)
Frozen holdout fold (R-AUT-10, post-F3); counter-metrics + coverage-quality Pareto gate; placebo/vocabulary integrity locks; registry merge-race serializer (one write-lane concurrency group + rebase-autostash-retry); approval-rate homeostat (difficulty-weighted quota, anti-trivial-farming); VPS `metabolism_live` canary lane.

### Phase C — generalization + emergence (per-lobe adoption, gated)
Insight Bus (append-only cross-lobe stigmergy, no lobe-to-lobe calls); anomaly-triggered self-directed research sprints (edge-triggered via governance rows); adversarial self-play where *disagreement* is the deliverable; uncovered-domain → auto-charter new lobe (T1/T2 gated); weekly **dream cycle** (counterfactual replay grading the PROPOSER, self-calibration); adversary random audits (independent re-derivation from raw tapes); advisory operator-preference prior (never gate-altering); quarterly self-assessment memo that self-prunes the kill registry.

## 5. Panel kills (recorded)
Curriculum "fixed-ration + priors" (dup cortex metabolism budget + DO_NOT_REBUILD priors); "dedup intake + revert" (dup `research_factory_ingest.py` + VERIFY auto-revert); "quarantined shadow eval" (weaker dup of F1 quarantine); launchd-rsync sub-claim (restates existing ops, no build); "Fable-adversary live key" (mechanism-unsound under state law → remapped to R-AUT-6 row-pairs).

## 6. Operator decisions (the 5 things only you can ratify)
1. **Arming.** Phase 0 + Phase A ship **inert** (draft PRs + shadow artifacts, no auto-merge). The first real autonomous merge happens only when you flip `AUTONOMY_PAUSED=false`. **This is your switch and stays yours.**
2. **Two-key = row-pairs, not live dual Fables** (R-AUT-6) — ratify the substitution (it's the only design compatible with the stateless-cattle law).
3. **Regime-aware revert** (R-AUT-11): a missed band routes ambiguous cases to your tap rather than auto-killing — confirm you want that human-in-the-loop on kills, vs. faster fully-auto reverts.
4. **T0 scope**: docs/tests/display-organs/bugfixes auto-merge without your tap once armed. Confirm that surface, or tighten it.
5. **Spend ceiling**: set the per-cycle token/USD cap in `metabolism_budget.yml` (IMMUTABLE) — the loop physically cannot exceed it.

## 7. Ops
- OAuth: `CLAUDE_CODE_OAUTH_TOKEN` is already a GH secret used by `whitehouse-sentinel.yml`/`asia-close.yml` — the loop mounts the existing secret (operator confirmed placement). A2 preflight guards its health.
- Notify: `scripts/notify.py` `send_telegram`/`send_discord` for alerts + digests.
- Runner: self-hosted macstudio; TCC/virtualized-FS gotchas handled by GH-Actions cron (not launchd) per the ops lens; render budget untouched (loop compute off the render path, heavy jobs → R2).
- Clocks: Phase 0 first; Phase A behind Phase-0-green + arming; TIL fitness cards meaningful after the W6 accrual clocks (first real read 2026-10-15).
