---
workstream: "WS:CI-MERGE-CONTROL-PLANE"
session: codex/ci-p3ba-call-capability-6351
model: codex
ended_because: ci_handoff
mission: >
  Make the existing main-selected trusted-ci-executor reusable by exactly one
  ordinary same-repository pull_request caller while production ci.yml remains
  GitHub-hosted. This is the prerequisite boundary for the separate P3B-B
  production-route carrier, not the cutover itself.
state_before: >
  P1/P2 proved one and three sealed PC CI slots plus an independent render slot.
  P3A-R PR #6487 merged as ac3f8a888e2ece7a15f37180c19dc247227a3098
  and direct-main proof run 33030976647 passed on pc-ci-3 against PR #6390.
  The selected main-owned executor still required a caller-supplied pr_number and
  refused workflow_call. Production ci.yml and every ordinary PR route were hosted.
changed:
  - path: .github/workflows/trusted-ci-executor.yml
    what: >
      Remove reusable-call inputs, bind exact event/caller/called-workflow identity
      in a hosted gate, expose derived plan identities, retain one-pack dispatch,
      and permit production-mode use of the P2-accepted three-slot matrix.
  - path: .github/runner-policy.yml
    what: >
      Advance the declaration to P3B-A with call_enabled true and
      production_enabled false while keeping ordinary same-repo and fork routes hosted.
  - path: scripts/check_runner_policy.py
    what: >
      Enforce the zero-input call contract, exact hosted trust refusals, main-owned
      plan routing, three-slot bound, sole runner-group consumer and inert ci.yml.
  - path: tests/test_trusted_ci_executor_workflow.py
    what: >
      Execute the real trust shell across admitted direct/called contexts and
      hostile event, ref, fork, base, caller, input and control-SHA mutations.
  - path: tests/test_runner_policy.py
    what: >
      Pin the P3B-A declaration and prove policy rejection of weakened trust
      refusals, caller inputs, early routing and extra group consumers.
  - path: agentos/decisions/DEC-TRUSTED-CI-MAIN-DEFINED-EXECUTOR-BOUNDARY.md
    what: Record the frozen P3B-A call boundary and separate P3B-B stop line.
  - path: agentos/workstreams/WS-CI-MERGE-CONTROL-PLANE.md
    what: Record P3A-R acceptance evidence and the exact P3B-A/P3B-B sequence.
  - path: agentos/handoffs/CI-MERGE-CONTROL-PLANE-2026-08-27-p3ba-call-capability.md
    what: Preserve exact state, proof, non-goals and continuation instructions.
verified:
  - claim: Current main lacked the frozen zero-input P3B-A call capability.
    command: >
      python3.12 -m pytest -q
      tests/test_trusted_ci_executor_workflow.py::test_p3ba_executor_is_call_capable_but_production_route_stays_inert -vv
    result: >
      RED as intended because workflow_call still required pr_number; the failure
      was the missing production capability, not a harness or syntax error.
  - claim: The implemented trust and runner-policy contract is green locally.
    command: >
      python3.12 -m pytest -q tests/test_trusted_ci_executor_workflow.py
      tests/test_runner_policy.py
    result: >
      52 passed under Python 3.12.13. Three inherited pytest temporary-directory
      cleanup warnings were non-failing.
  - claim: Hostile reusable-call contexts fail before producing admission outputs.
    command: >
      python3.12 -m pytest -q
      tests/test_trusted_ci_executor_workflow.py::test_p3ba_refuses_untrusted_call_contexts
    result: >
      Push, candidate-defined called ref, rogue caller, fork, non-main base,
      wrong merge ref/PR number, supplied dispatch identity and malformed called
      SHA all returned nonzero with no outputs.
unverified:
  - claim: P3B-A exact-head hosted CI and adversarial review are green.
    what_would_verify: Reconcile to current main, publish one #6351 carrier and conclude all checks.
  - claim: GitHub accepts the main-owned reusable context bindings on the merged workflow.
    what_would_verify: >
      Merge P3B-A, then have the separate P3B-B carrier make the exact main call;
      its own PR event must pass the hosted gate and acquire only the declared PC jobs.
unresolved:
  - Production remains hosted until the separate P3B-B carrier proves its own exact-tree call.
  - M1 W2/W4 admission remains open and unsafe; its ThetaData/OptionsHub/MarketDesk workloads are untouched.
next_actions:
  - Re-pin origin/main and rebase if a CI/trust/owned path moved.
  - Complete focused static, policy, semantic and Agent OS validation on the reconciled head.
  - Publish one P3B-A PR linked to #6351 and use exactly one mechanical CI watcher.
  - Review and merge without bypass only if exact-head checks and trust review pass.
  - Start P3B-B on a new carrier from accepted main and prove that carrier's exact PR route.
do_not_redo:
  - Do not rerun P1, P2, P3A or P3A-R receipts.
  - Do not edit or route ci.yml, change required checks or add a group consumer in P3B-A.
  - Do not accept caller-supplied SHA, base, plan or route identity.
  - Do not create a scheduler, queue, lifecycle, retry or semantic-proof plane.
  - Do not touch M1 workloads or recruit M4 hardware in this wave.
danger_areas:
  - >
    github.workflow_ref is caller context while job.workflow_ref and
    job.workflow_sha identify the called main workflow; confusing them erases
    either caller binding or main-owned control identity.
  - >
    The candidate manifest/files remain the execution subject while the control
    implementation remains main-owned; substituting either side creates false proof.
  - >
    P3B-A call_enabled is not production_enabled. Editing ci.yml in this carrier
    would collapse two independently useful authority waves into one.
---

# P3B-A main-owned trusted executor call capability

## Observable mission

Make the existing main-selected `trusted-ci-executor.yml` reusable by exactly
one ordinary same-repository `pull_request` caller while production `ci.yml`
remains GitHub-hosted. This is the prerequisite boundary for the separate
P3B-B production-route carrier; it is not the cutover itself.

## Why it matters

Hosted `ci-pack` jobs repeatedly spend tens of minutes to more than an hour in
independent repository checkout/materialization before tests begin. P1/P2 proved
one and three sealed PC CI slots plus an independent render slot. P3A-R proved
the full main-owned planner/control bundle on a real PC pack. P3B-A closes the
remaining call boundary without allowing PR-authored workflow code or caller
inputs to choose self-hosted identity, plan or route.

## Authority and precedence

1. Chairman direction and issue #6351 sequence.
2. `DEC:TRUSTED-CI-MAIN-DEFINED-EXECUTOR-BOUNDARY`.
3. Current `.github/runner-policy.yml` and the server-side
   `macro-home-canary` selected-workflow restriction.
4. Existing semantic plan/fragment/ci-gate and merge controller.

No new scheduler, queue, retry, proof, lifecycle or runner database is created.
GitHub Actions remains the scheduler.

## Verified predecessor state

- P1 accepted: run 32957250432, one PC slot, exact hosted/self-hosted parity.
- P2 accepted: runs 32960314514 and 32964925696, three concurrent PC CI slots,
  independent render acquisition, exact parity and safe resources.
- P3A-R PR #6487 merged as
  `ac3f8a888e2ece7a15f37180c19dc247227a3098`.
- P3A-R proof run 33030976647 passed on `pc-ci-3` against PR #6390 with exact
  tested merge `078bdb7d212a3bcabea9df6ba06a6ef7bcf5ee07`, plan
  `1ad0b428cac9e81481545358f9e30b151c3fdffe88d28ed7bc99be8d5ac7e720`,
  stable shared cache and a safe resource envelope.
- Runner group `macro-home-canary` is workflow-restricted and selects the exact
  main path `.github/workflows/trusted-ci-executor.yml@refs/heads/main`.

## P3B-A contract

- `workflow_call` accepts zero inputs and exposes only plan identity outputs.
- Hosted trust gate admits only:
  - direct `workflow_dispatch` of the exact main-owned executor; or
  - a same-repository PR targeting `main`, running on its exact merge ref, whose
    caller workflow ref is exactly `.github/workflows/ci.yml` at that same merge
    ref and whose called workflow/job ref is the executor on `refs/heads/main`.
- Forks, push, non-main base, mismatched PR ref/number, rogue caller path,
  candidate-defined called workflow, malformed called-workflow SHA and any
  caller-supplied dispatch identity fail closed before PC acquisition.
- The called workflow independently resolves the event PR, checks out the exact
  called-workflow control commit, freezes the existing semantic plan and exact
  candidate, and passes no secrets to the PC.
- Direct dispatch selects one diagnostic pack. Production mode may execute the
  complete main-planned matrix with `max-parallel: 3`.
- `ci.yml` remains unchanged and all ordinary PR jobs remain hosted.
- `.github/runner-policy.yml` records `call_enabled: true` and
  `production_enabled: false`.

## Changed paths

- `.github/workflows/trusted-ci-executor.yml`
- `.github/runner-policy.yml`
- `scripts/check_runner_policy.py`
- `tests/test_trusted_ci_executor_workflow.py`
- `tests/test_runner_policy.py`
- `agentos/decisions/DEC-TRUSTED-CI-MAIN-DEFINED-EXECUTOR-BOUNDARY.md`
- `agentos/workstreams/WS-CI-MERGE-CONTROL-PLANE.md`
- this handoff

## Local proof at implementation head

- TDD red proved current main still required a caller-supplied `pr_number`.
- Focused Python 3.12.13 suite:
  `tests/test_trusted_ci_executor_workflow.py tests/test_runner_policy.py`:
  52 passed. The three warnings were inherited pytest temporary-directory
  cleanup warnings and not test failures.

Exact branch head/base, complete validation set, PR number, Actions run IDs and
main merge identity remain intentionally unverified until carrier publication.

## Non-goals and stop condition

Do not edit or route production `ci.yml`, change required checks, add another
runner-group consumer, expose forks/untrusted work, touch M1 workloads, recruit
M4 hardware, or change repository visibility in P3B-A. Stop this carrier after
merge/exact-main call-boundary proof. Begin P3B-B only on a new carrier from that
accepted main.

## Required continuation

1. Re-pin `origin/main`; rebase if any CI/trust/owned path moved.
2. Run the focused policy/workflow/semantic/AgentOS validation set on the exact
   reconciled head.
3. Publish one P3B-A PR linked to #6351 and use exactly one mechanical CI watcher.
4. Review and merge without bypass only if exact-head checks and trust review pass.
5. Open the separate P3B-B carrier from merged main; route only ordinary
   same-repository PR execution through the exact main-owned workflow while
   keeping hosted planner/anchors, `ci-gate`, forks and merge control independent.
6. P3B-B must prove itself on its own exact PR tree before P4 begins.
