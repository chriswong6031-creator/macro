# CI C1 Zero-Compute Quiescence V2 Implementation Plan

> **Operation:** `ci-quiescence-v2-20260829-sol-001`
>
> **Canonical carrier:** Macro issue #6379 and its bound Slack thread
>
> **Execution owner:** CTO-FORGE / native task `01a04bdf-7a7b-7f63-9abd-9a7c13e944c0`
>
> **Initial RED base:** `3ed822213caa096b8665b21ce9c3c3f5c860064f`

**Goal:** Keep logical delivery ownership in the same session while a healthy external CI wait consumes one model-facing entry receipt and no further frontier-model turns until a mechanically observable material event.

**Architecture:** Extend the existing ship-loop session ledger and its existing quota/watcher boundary. A quiescence receipt is valid only for the exact clean pushed PR head, a successful bounded preflight, no builder-owned red, and one live PR condition watcher whose process identity is atomically reserved in that session's ledger. The admitted native `gh pr checks` command remains one owner but is rewritten within the same hook lifecycle to observe the union of exact head, checks, hold comments, and review authority. Repeated unchanged Stop or task-notification observations read the local ledger/process marker and return silently without GitHub access. Watcher exit, head/hold/release drift, or a concluded check state atomically claims one wake and re-enters the existing route exactly once; later Stop boundaries revalidate the material-event key so a distinct same-head event remains visible.

**Non-goals:** No watcher database, daemon, scheduler, queue, retry service, second lifecycle/control plane, new worker identity, `ci.yml` or trusted-executor change, merge-controller rewrite, product code, or prose-derived authority.

**Existing-carrier boundaries:**

- PR #6381 is read-only donor evidence at exact head `277b758315177dc394bec9ede7f917a37c3a4a08`; selectively port lawful atomic one-watcher, process-identity, terminal-latch, and no-successor mechanisms and tests only.
- PR #6626 is the tactical HOLD subset at exact head `89adf1491121226c3e04f9e0a01d48af3284dd01`; it later merged as `a4c4160e0024fe196225eed5ff3285a9f7be76b2`. Reconcile its exact landed bytes before the final documentation/wrapper step; never silently fork them.
- Preserve all foreign worktree locks and active CI watchers. This lane never reruns, cancels, closes, or mutates #6626.

---

## Task 1: Establish donor RED tests without production changes

**Files:**

- Modify: `tests/test_ship_loop_guard.py`
- Modify: `tests/test_gh_quota_guard.py` if the current quota test surface exists; otherwise add focused coverage to the existing quota-guard test module named by the repository.

1. Apply only the donor test hunks that cover atomic ledger writes, one-watcher reservation, PID plus process-start identity, duplicate waiter coalescing/refusal at 2/5/14 concurrency, session isolation, watcher exit with no unchanged successor, and terminal PARKED behavior.
2. Add a quota-boundary RED showing that a denied hot-watch reason cannot leave a phantom watcher reservation.
3. Run only the new node IDs and record the expected failures against unchanged production code.
4. Do not weaken assertions to match current behavior.

## Task 2: Add the V2 acceptance and negative-control RED matrix

**Files:**

- Modify: `tests/test_ship_loop_guard.py`
- Modify: `tests/test_ship_loop_hold_wrapper.py` only after #6626 resolves and its exact bytes are reconciled.

Add discriminating tests for:

1. First exact-head pending wait enters mechanically derived `CI_QUIESCENT` only when the clean/pushed/preflight/no-own-red/live-watcher predicates all hold.
2. One hundred identical Stop/task-notification observations produce one GitHub observation, one model-facing receipt, and no 10/15 narration ladder.
3. Green, builder-owned red, inherited-main red, infrastructure/missing-proof red, head drift, and valid hold/release drift each break the old quiescence exactly once and route to the required owner.
4. Builder-owned red never enters or remains in quiescence.
5. Inherited-main and infrastructure red route to #6351 without authorizing product-code repair.
6. Two, five, and fourteen duplicate waiters coalesce/refuse for one session while a distinct session/worktree remains isolated.
7. Ordinary `claude/*` HOLD WAITING/CHECKS RED behavior is unchanged without a lawful watcher; a valid watcher can quiesce a pending hold; malformed/ambiguous hold fails closed; existing PARKED semantics remain terminal for the current session.
8. Free-form model prose, hook input text, or a manually edited non-authoritative field cannot mint quiescence, green, merged, shipped, or terminal truth.
9. Mutation control: disable the local quiescence fast path and prove the 100-observation fixture returns to repeated polling/narration.

Run the focused node IDs and retain the RED output before touching production hooks.

## Task 3: Port the lawful atomic watcher/ledger substrate

**Files:**

- Modify: `.claude/hooks/ship_loop_guard.py`
- Modify: `.claude/settings.json`
- Modify: `.claude/hooks/gh_quota_guard.py`

1. Selectively port #6381's atomic ledger read-modify-write and compare-and-reserve watcher mechanism into the existing per-session ledger.
2. Preserve the current quota guard; port only the pure canonical `hot_watch_reason(raw)` normalization needed so quota denial and watcher reservation use the same mechanical reason.
3. Bind watcher ownership to session key, PR number, exact head, check/route fingerprint, PID, and process-start identity. Refuse a stale/reused PID and refuse multiple live watchers for the same session; do not affect other session ledgers.
4. Preserve the existing native GitHub watcher admission and configured hook lifecycle. For PR waits, keep exactly one owner but evaluate checks and hold/review authority in that process so metadata changes are observable. No detached timer, background polling service, second watcher, or successor watcher after unchanged exit.
   Clamp the union process to an aggregate-safe cadence and paginate comment/review
   authority through a small explicit fail-closed bound; prove the worst-case
   request count for fourteen isolated sessions remains below the shared REST pool.
5. Run donor atomicity/isolation/PARKED tests green before adding V2 state transitions.

## Task 4: Implement mechanically derived CI quiescence

**Files:**

- Modify: `.claude/hooks/ship_loop_guard.py`
- Modify: relevant focused tests from Tasks 1-2

1. Add a versioned `ci_quiescence` record inside the existing session ledger. Its authoritative fields are derived only from Git/GitHub/check/watcher observations and exact local state.
2. Gate entry on exact pushed clean head, successful fast preflight checks, no builder-owned red, pending external checks, and one confirmed live watcher bound to the same PR/head/fingerprint.
3. On first entry, atomically persist the record and emit one concise `CI_QUIESCENT` system receipt. Do not emit `decision:block`, schedule a Stop retry, or create a successor task.
4. On identical Stop/task-notification observations, validate only the local exact-head/process marker and return silently before any GitHub command.
   Ensure the configured HOLD wrapper delegates ordinary-mode material re-entry
   without clearing the canonical quiescence record first.
5. On watcher exit or local head/hold marker drift, atomically claim a single re-entry token. Exactly one observer may perform the next GitHub classification; duplicates remain silent.
6. Route concluded states through existing ownership law: green to release/Sol, own red to the builder, inherited-main or infrastructure/missing-proof red to #6351. Never let quiescence hide or cheaply escape own red.
7. Clear or replace stale quiescence records on material state change; never infer merged/shipped/deployed/terminal state from watcher exit.
8. Run the entire focused V2 matrix green.

## Task 5: Reconcile #6626 and document the law

**Files:**

- Modify after exact reconciliation: `AGENTS.md`
- Modify after exact reconciliation: `CLAUDE.md`
- Modify after exact reconciliation only if required: `scripts/ship_loop_hold_wrapper.py`
- Modify after exact reconciliation only if required: `tests/test_ship_loop_hold_wrapper.py`

1. Wait for the live #6626 carrier to conclude without a second watcher, rerun, cancel, close, or mutation.
2. Refresh `origin/main`; if #6626 landed, merge fresh main into this branch and inspect the exact four-file result. If it did not land or moved incompatibly, stop for same-carrier adjudication.
3. Preserve #6626 ordinary HOLD WAITING/CHECKS RED and malformed-hold fail-closed behavior. Add only the minimum wrapper integration needed for the authoritative local quiescence fast path.
4. Update `AGENTS.md` and `CLAUDE.md` together: logical delivery ownership remains; active model occupancy does not. State explicitly that `CI_QUIESCENT` is not merged, shipped, deployed, an Executive Job/Attempt/Worker state, or new authority.

## Task 6: Prove the mechanism, records, and held delivery

**Files:**

- Modify unless a current exact-path carrier exists: `agentos/workstreams/WS-CI-MERGE-CONTROL-PLANE.md`
- Add: a dated `agentos/handoffs/CI-MERGE-CONTROL-PLANE-2026-08-29-*.md`
- Do not edit generated Agent OS views.

1. Run focused hook/quota/wrapper tests, the relevant CI-pack validation, and repository contract/fence checks proportionate to the changed hook surfaces.
2. Run deterministic long-wait proof across multiple nominal poll intervals and report watcher-process count, GitHub-observation count, model-facing receipt/turn count, and wake count.
3. Run mutation proof by disabling/bypassing the quiescence transition in the test harness and confirm repeated poll/narration returns.
4. Run `python3 scripts/agentos.py validate` after updating the workstream/handoff.
   If another current PR owns the workstream record, leave that shared file
   untouched and record the collision plus this bounded wave in the new handoff.
5. Refresh `origin/main`, reconcile collisions, inspect exact changed files, commit, push, and open one fresh current-main PR.
6. Return the PR as `PARKED / HOLD-FOR-SOL`: exact head pushed, local worktree clean, draft PR, no `merge-on-green`, auto-merge null, explicit Sol authority/release condition. Do not merge or claim live deployment before Sol adjudication.
7. Post exact-head `RESULT` or governed `BLOCKED` on the canonical Slack carrier with RED/GREEN/mutation/long-wait evidence, current CI, watcher/model-turn counts, exact files, and durable Agent OS handoff. Re-arm every nonterminal return.
