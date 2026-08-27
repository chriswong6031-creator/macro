---
workstream: "WS:CI-MERGE-CONTROL-PLANE"
session: codex/ci-p4-main-ref-admission-6351
model: codex
ended_because: ci_handoff
mission: >
  Restore the P3B-B production route after natural post-merge traffic proved
  that GitHub canonicalizes the called reusable workflow's `job.workflow_ref`
  to the full protected-main ref, without widening caller, fork, credential,
  runner-group or visibility authority.
state_before: >
  PR #6505 merged as 4b9c9ece8593a2483997432e25f233bfe7af8779
  after all twelve trusted PC packs and ci-gate passed in run 33070187935.
  The first two post-merge same-repository calls, runs 33074339679 and
  33074386695, both failed the hosted admission job before planner or PC pickup:
  `job.workflow_ref` was the full `@refs/heads/main` value, but the gate expected
  the caller-syntax shorthand `@main`. Neither record-only PR is a P4 product
  acceptance sample.
changed:
  - path: .github/workflows/trusted-ci-executor.yml
    what: >
      Require the same exact full protected-main workflow ref for reusable-call
      and direct-dispatch admission while retaining immutable workflow-SHA proof.
  - path: tests/test_trusted_ci_executor_workflow.py
    what: >
      Model GitHub's production `job.workflow_ref` exactly and refuse shorthand,
      tag, candidate-ref, wrong-caller, fork, base and non-commit mutations.
  - path: agentos/discoveries/DSC-REUSABLE-WORKFLOW-CALL-AND-HOST-HOOK-USE-DIFFERENT-REF-SHAPES.md
    what: Correct the durable GitHub context-shape ruling from live P4 evidence.
  - path: agentos/handoffs/CI-MERGE-CONTROL-PLANE-2026-08-27-p3bb-production-route.md
    what: Reconcile P3B-B to its exact merge and the post-merge admission defect.
  - path: agentos/workstreams/WS-RUNNER-FLEET-RESILIENCE.md
    what: Record that the current stop is hosted admission, not PC capacity.
verified:
  - claim: The natural post-merge failure is a called-ref representation defect.
    command: >
      GitHub Actions runs 33074339679 and 33074386695; completed admission-job
      log 98525641383; official GitHub `job.workflow_ref` context contract
    result: >
      Both production calls supplied the full protected-main ref and failed the
      old shorthand comparison before any PC runner acquired work.
  - claim: The old gate rejects GitHub's observed production value.
    command: >
      python3.12 -m pytest -q tests/test_trusted_ci_executor_workflow.py
      -k accepts_exact_main_called_same_repo_pr
    result: >
      Intended RED: one failure with `called workflow must use the main branch
      definition` before the workflow repair.
  - claim: The narrow repair preserves the complete trust boundary locally.
    command: >
      python3.12 -m pytest -q tests/test_trusted_ci_executor_workflow.py
      tests/test_trusted_ci_production_route.py tests/test_runner_policy.py;
      python3 scripts/check_runner_policy.py
    result: >
      63 passed and the runner-policy guard reported the sole protected-main PC
      executor route; Agent OS validated 867 records with zero errors and
      contract-delta reported 0 introduced / 0 inherited against exact base
      b2e158f5feb255f43cf12684326bd89fc8e8b9ff. Only inherited pytest
      temporary-cleanup warnings remained.
  - claim: The broader Agent OS regression is classified rather than hidden.
    command: >
      python3.12 -m pytest -q tests/test_agentos_schema.py
      tests/test_agentos_status.py tests/test_agentos_compile.py
    result: >
      133 passed; one inherited current-main failure at
      test_cross_repo_path_is_unchecked_when_that_checkout_is_absent because
      WS-CHAIRMAN-CONTROL-ROOM already emits unrelated phantom-artifact warnings.
      This carrier changes neither that workstream nor cross-repository validation.
unverified:
  - claim: The corrected main definition admits a natural product PR and reaches PC execution.
    what_would_verify: >
      Merge this repair without bypass, then observe the next natural ordinary
      same-repository product PR pass admission, hosted/main plan parity, trusted
      PC packs, relayed ci-pack checks and ci-gate.
  - claim: P4 has three qualifying natural product PR receipts.
    what_would_verify: >
      Three post-repair broad, narrow and render-overlap product PR heads with
      exact route, queue, resource, cache and hosted-minute receipts.
unresolved:
  - >
    This repair PR's own pull_request run loads the old main executor and may
    reproduce the known admission red; that is not candidate-code proof and
    must not be bypassed or hidden.
  - >
    Open HOLD carriers #6381 and #6426 already change
    WS-CI-MERGE-CONTROL-PLANE.md. This wave records its receipt in the existing
    discovery, handoff lineage and #6351 instead of creating a third colliding
    workstream-file carrier; those HOLD carriers must reconcile canonical state.
  - Repository visibility remains public and private cutover remains held.
next_actions:
  - Re-pin fresh origin/main and confirm no changed-path overlap before publication.
  - Publish one #6351 repair carrier and conclude all non-inherited gates.
  - Merge only through the existing merge controller's concluded-check/no-overlap law.
  - Count only natural ordinary product PRs after the repair merge toward P4.
do_not_redo:
  - Do not reopen #6505, rerun the two terminal record-only PRs or touch their heads.
  - Do not edit ci.yml, runner-group selection, host hooks, labels or listener count.
  - Do not start pc-ci-4, generic M1, M4 Pro, M4 minis or any render mutation.
  - Do not create a scheduler, queue, retry, proof or lifecycle plane.
danger_areas:
  - >
    `uses: ...@main` is valid caller declaration syntax, but `job.workflow_ref`
    is the canonical full ref. Conflating the two either fails all production
    calls or risks widening called-workflow identity.
  - >
    A green direct dispatch is not a reusable-call production proof. P4 still
    requires natural pull_request traffic after the repair is on main.
---

# P4 protected-main called-ref admission repair

## Observable mission

Make the already-merged trusted PC route start for natural same-repository PRs
by matching GitHub's exact called-workflow context, with no change to the caller,
planner, runner group, semantic evidence, merge controller or hardware fleet.

## Stop condition

Stop this repair after one exact carrier merges without bypass and a natural
post-merge product PR proves the corrected admission. Keep #6351 open until all
three P4 product receipts and the private-cutover packet are accepted. Do not
change repository visibility.
