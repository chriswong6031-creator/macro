---
workstream: "WS:CI-MERGE-CONTROL-PLANE"
session: codex/CTO-FORGE/01a04bdf-7a7b-7f63-9abd-9a7c13e944c0
model: codex
ended_because: ci_handoff
mission: >
  Make a healthy 30-45 minute external CI wait consume one entry receipt and
  zero new frontier-model turns until one material event, without changing
  logical delivery ownership or creating a second lifecycle/control plane.
state_before: >
  The Stop guard polled GitHub and narrated the same pending state on every
  observation. PR #6381 held a closed-unmerged donor implementation at exact
  head 277b758315177dc394bec9ede7f917a37c3a4a08. PR #6626 held the compatible
  ordinary claude/* HOLD WAITING/CHECKS RED correction at exact head
  89adf1491121226c3e04f9e0a01d48af3284dd01. Its exact commit was first
  reconciled with -x after its sole native watcher exited on a transport reset;
  when #6626 later merged as a4c4160e0024fe196225eed5ff3285a9f7be76b2,
  current origin/main was merged normally and the one wrapper conflict resolved
  by preserving both the merged WAITING/CHECKS RED subset and V2 quiescence.
  The final publication tree is reconciled with Macro main
  f77ff8669618b1604ddc0b3ae2d06e112245e9f1; the intervening main movement was
  nightly/data-only and touched none of the twelve successor paths.
changed:
  - path: .claude/hooks/gh_quota_guard.py
    what: >
      Expose one canonical pure hot-watcher classifier so watcher reservation
      and quota denial cannot disagree or leave a phantom claim; apply the
      same 60-second floor to the PR watcher's real ten-second default.
  - path: .claude/hooks/ship_loop_guard.py
    what: >
      Add atomic per-session transactions, exact native watcher identity and
      one-watcher admission, ci_quiescence.v1 derivation/local fast path,
      a single PR condition process covering checks plus hold/review authority,
      bounded three-page authority reads, an aggregate-safe 180-second cadence,
      single material-event routing, and fail-closed red ownership boundaries.
  - path: scripts/ship_loop_hold_wrapper.py
    what: >
      Reconcile PR #6626 with the donor's one-time PARKED latch and bind lawful
      pending holds to the same quiescence ledger and watcher boundary. Preserve
      ordinary-mode records for canonical material re-entry and bind paginated
      comment plus review authority into the hold fingerprint.
  - path: .claude/settings.json
    what: >
      Put the existing watcher gate on Bash PreToolUse as well as the quota
      boundary; retain the same Stop wrapper and canonical delegate.
  - path: tests/test_ship_loop_guard.py
    what: >
      Pin 100-observation zero-poll behavior, deterministic 45-minute proof,
      mutation control, material transitions, malformed-state refusal,
      candidate-owned red, central red routing, and 2/5/14 atomicity/isolation.
  - path: tests/test_ship_loop_hold_wrapper.py
    what: >
      Pin the reconciled HOLD WAITING/CHECKS RED behavior, shared pending wait,
      one-time PARKED receipt, concurrent ledger preservation, outage refusal,
      and material route ownership.
  - path: AGENTS.md
    what: Record the cross-account zero-compute quiescence law.
  - path: CLAUDE.md
    what: Record the same zero-compute quiescence law for Claude sessions.
  - path: .cursor/rules/ship-loop-terminal-states.mdc
    what: Record the same mechanical state and negative controls for Cursor.
  - path: docs/superpowers/plans/2026-08-29-ci-zero-compute-quiescence-v2.md
    what: Preserve the RED-first implementation and verification plan.
  - path: agentos/handoffs/CI-MERGE-CONTROL-PLANE-2026-08-29-ci-quiescence-v2.md
    what: Preserve the durable successor evidence and continuation boundary.
verified:
  - claim: >
      The deterministic long-wait control yields one CI_QUIESCENT receipt,
      one remote snapshot, one watcher identity and 100 silent unchanged
      observations over a simulated 2,700-second wait.
    command: >
      python3 -m pytest -q
      tests/test_ship_loop_guard.py::test_one_hundred_identical_stop_and_task_wakes_do_not_repoll_or_renarrate
      tests/test_ship_loop_guard.py::test_deterministic_forty_five_minute_wait_keeps_one_watcher_and_one_receipt
      tests/test_ship_loop_guard.py::test_mutation_bypassing_quiescence_reintroduces_one_hundred_poll_blocks
    result: 3 passed in the deterministic long-wait/mutation selection.
  - claim: >
      Lawful pending holds reuse ci_quiescence.v1; PARKED narrates once; red,
      release, outage and concurrent watcher/latch changes fail in the safe direction.
    command: python3 -m pytest -q tests/test_ship_loop_hold_wrapper.py
    result: 41 hold-wrapper tests passed inside the current focused joint run.
  - claim: The cross-account standing law requires the identical zero-turn boundary.
    command: >
      python3 -m pytest -q
      tests/test_ship_loop_guard.py::test_quiescence_standing_law_matches_zero_turn_amendment
    result: Passed on the current-main reconciled tree.
  - claim: >
      Guard, hold-wrapper and quota boundaries are jointly green after merging
      current main and the landed #6626 subset.
    command: >
      PYTHONDONTWRITEBYTECODE=1 python3 -B -m pytest -q
      tests/test_ship_loop_guard.py tests/test_ship_loop_hold_wrapper.py
      tests/test_gh_quota_guard.py
    result: 557 passed, 1 skipped; three pytest temp-cleanup warnings only.
  - claim: >
      The independent review's nine negative controls fail on the pre-review
      head and pass after binding authority wake, routed-event revalidation,
      owned control-check failure, quota, PID/start, dead-before-entry and
      local hold-probe ambiguity.
    command: >
      python3 -m pytest -q
      tests/test_gh_quota_guard.py::test_gh_pr_checks_watch_uses_its_real_ten_second_default_and_same_floor
      tests/test_ship_loop_guard.py::test_pr_condition_watcher_exits_on_hold_change_while_checks_remain_pending
      tests/test_ship_loop_guard.py::test_quiescence_requires_complete_pid_start_marker_binding
      tests/test_ship_loop_guard.py::test_dead_confirmed_watcher_before_entry_routes_missing_evidence_once
      tests/test_ship_loop_guard.py::test_inherited_main_and_infrastructure_routes_name_canonical_ci_owner
      tests/test_ship_loop_guard.py::test_candidate_caused_control_check_failure_stays_with_builder
      tests/test_ship_loop_guard.py::test_routed_receipt_does_not_hide_a_later_same_head_builder_red
      tests/test_ship_loop_hold_wrapper.py::test_local_git_unanswerability_preserves_existing_hold_state
    result: 9 failed before the correction and 9 passed after it.
  - claim: >
      The configured wrapper preserves ordinary-mode material re-entry, comment
      and review authority are bounded and page-complete, and fourteen isolated
      watchers fit the declared REST budget.
    command: >
      python3 -m pytest -q
      tests/test_ship_loop_guard.py::test_authority_loader_reads_page_two_and_refuses_a_full_cap
      tests/test_ship_loop_guard.py::test_union_watcher_declares_a_safe_fourteen_session_request_budget
      tests/test_ship_loop_guard.py::test_union_snapshot_normal_cycle_uses_five_rest_requests
      tests/test_ship_loop_guard.py::test_configured_hold_wrapper_preserves_ordinary_material_reentry
      tests/test_ship_loop_hold_wrapper.py::test_ordinary_quiescence_is_never_cleared_by_the_hold_wrapper
      tests/test_ship_loop_hold_wrapper.py::test_hold_probe_uses_paginated_comments_including_page_two
    result: 4 failed and 2 passed before the correction; all 6 passed after it.
  - claim: >
      A bounded HOLD authority outage cannot be misclassified as a release-side
      authority change: the configured wrapper and canonical guard share one
      fingerprint shape and route exactly one missing-evidence event to #6351.
    command: >
      python3 -m pytest -q
      tests/test_ship_loop_guard.py::test_union_watcher_declares_a_safe_fourteen_session_request_budget
      tests/test_ship_loop_guard.py::test_configured_hold_wrapper_routes_unanswerable_authority_once
      tests/test_ship_loop_hold_wrapper.py::test_hold_probe_constructs_comments_endpoint_when_pull_omits_it
    result: All 3 failed before the final-review correction and passed after it.
unverified:
  - claim: Hosted CI is green on the successor pull request's exact head.
    what_would_verify: Concluded binding checks on the fresh successor PR head.
unresolved:
  - >
    Repository hooks control hook output, GitHub observations, and watcher
    admission; the external client decides whether a task notification creates
    a model turn. The healthy single PR condition watcher has no unchanged completion, and
    the deterministic proof therefore establishes zero model-facing outputs
    after entry, not authority over an arbitrary client's scheduler.
  - >
    PR #6626 is now merged on main as a4c4160e0024fe196225eed5ff3285a9f7be76b2.
    This successor reconciled that main commit through a normal same-branch merge
    and did not reopen, rebase, mutate, or independently merge #6626.
  - >
    Open HOLD PR #6426 edits agentos/workstreams/WS-CI-MERGE-CONTROL-PLANE.md.
    To avoid a records collision, this successor records the bounded wave in
    this new handoff and leaves that shared workstream file untouched.
next_actions:
  - Keep the successor pull request DRAFT, disarmed and unmerged for explicit Sol review.
  - Treat any later head, authority or hosted-check change as a new material observation; do not infer acceptance from this handoff.
  - After Sol releases or rejects the hold, continue only on the canonical #6379 carrier under that explicit edge.
do_not_redo:
  - Do not reopen, rebase or merge donor PR #6381.
  - >
    Do not silently fork or mutate PR #6626; its landed commit is reconciled
    through the recorded current-main merge.
  - Do not create a watcher database, daemon, scheduler, queue, retry service,
    second lifecycle/control plane, successor watcher, or new session identity.
  - >
    Do not claim the repo hook can prevent an arbitrary external client from
    instantiating a model turn; require zero new model turns while external state
    is unchanged through the one non-completing condition watcher and silent hook path.
danger_areas:
  - >
    A manually planted partial quiescence dictionary is not authority. The full
    versioned record, exact local head/dirt, confirmed watcher digest, PID and
    process-start marker must all revalidate before any silent pass.
  - >
    One infrastructure symptom beside a candidate-owned failure must not route
    the whole red away; every concluded red must be central/inherited before
    #6351 owns it.
  - >
    PARKED and CI_QUIESCENT are distinct: PARKED is a fully green Sol-controlled
    terminal hold; quiescence is a nonterminal pending wait that retains delivery
    ownership and wakes on one material event.
  - >
    The union watcher clamps admitted 60-second commands to 180 seconds and
    bounds comments/reviews at three 100-record pages each. Cap exhaustion is
    missing evidence, never permission to infer unchanged authority.
  - >
    HOLD wrapper, union watcher and canonical guard must use the same bounded
    authority snapshot/fingerprint. An unanswerable snapshot routes once to
    #6351 as missing evidence; it is never a release-side authority change.
---

# CI C1 zero-compute quiescence V2

## Observable contract

The exact clean pushed head may enter `CI_QUIESCENT` only after deterministic
fast preflight is green, no binding builder red exists, and one PR condition watcher is
mechanically confirmed for the same PR/head. The first observation emits one
receipt. Repeated Stop/task-notification observations consult only local ledger,
head/dirt, and process identity, producing zero new model turns while external
state is unchanged. The one watcher observes checks plus hold/review authority.
Its internal cadence is at least 180 seconds; one snapshot is bounded to 12 REST
requests, so fourteen isolated first-hour watchers consume at most 3,528. Comment
and review authority is page-complete through three 100-record pages and fails
closed if the bound is exhausted.
One material green/red/head/hold/watcher change wakes exactly once and routes by
mechanical ownership; later Stop boundaries revalidate the material-event key so
a distinct same-head event cannot be hidden by the first receipt.

## Architecture boundary

This is an extension of the existing ship-loop ledger and watcher/quota hook.
There is no second data store, daemon, scheduler, queue, retry lane, lifecycle,
control plane, session identity, or prose-authored terminal state. Logical
delivery ownership never leaves the session merely because active model
occupancy is released during the external wait.
