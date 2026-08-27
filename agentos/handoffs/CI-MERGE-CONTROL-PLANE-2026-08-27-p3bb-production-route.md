---
workstream: "WS:CI-MERGE-CONTROL-PLANE"
session: codex/ci-p3bb-production-route-6351
model: codex
ended_because: ci_handoff
mission: >
  Route only ordinary same-repository PR pack execution through the exact
  protected-main trusted executor while keeping the hosted planner, stable
  ci-pack-N anchors, semantic gate, fork path, fences and merge controller.
state_before: >
  P3B-A PR #6496 merged as 904863dabc490ee95ac50153048c25dee048d90b.
  The exact main-owned executor accepted a zero-input same-repository PR call,
  but ci.yml still ran every pack fully hosted. Exact-head run 33035115527 spent
  about 180.7 hosted pack-minutes across twelve successful pack jobs.
changed:
  - path: .github/workflows/ci.yml
    what: >
      Add one zero-input same-repository call to the exact main executor; retain
      full hosted fork execution; turn existing hosted ci-pack-N jobs into
      trusted-fragment relays after exact hosted/main plan-SHA parity.
  - path: .github/workflows/trusted-ci-executor.yml
    what: >
      Distinguish valid reusable-call `@main` identity from direct-dispatch
      `@refs/heads/main`; do not claim job `env` is visible to the pre-job hook.
  - path: .github/ci/legacy-jobs.yml
    what: Name the route suite in the existing runner-policy/canary contract step.
  - path: .github/runner-policy.yml
    what: >
      Declare P3B-B production routing for same-repository PR execution only;
      preserve public visibility, hosted forks and all protected hosted routes.
  - path: scripts/check_runner_policy.py
    what: >
      Permit only the exact protected-main call and enforce no inputs/secrets,
      hosted anchors, fork-only heavy candidate steps, semantic relay identity,
      three-slot executor bound and sole runner-group consumer.
  - path: ops/runner-host/common/runner_admission.py
    what: >
      Extend the existing PC hook with the exact same-repository PR merge ref,
      ci.yml caller and trusted-pack job; derive same-repository/main-base facts
      from GitHub's event payload while preserving every hostile refusal.
  - path: ops/runner-host/common/runner_admission_hook.js
    what: Forward `GITHUB_EVENT_PATH`, the default variable available before job steps.
  - path: tests/test_trusted_ci_production_route.py
    what: >
      Pin the production call, hosted anchor/fork split, unchanged gate and
      declaration contract.
  - path: tests/test_runner_policy.py
    what: >
      Prove the guard rejects candidate refs, caller inputs, candidate checkout
      in same-repository anchors, fork rerouting and extra group consumers.
  - path: tests/test_trusted_ci_executor_workflow.py
    what: Reconcile the already-proven executor contract to activated P3B-B routing.
  - path: tests/test_ci_canary_tools.py
    what: Execute the exact allowed PR hook facts and hostile ref/fork/base/SHA mutations.
  - path: agentos/decisions/DEC-TRUSTED-CI-MAIN-DEFINED-EXECUTOR-BOUNDARY.md
    what: Record the frozen P3B-B relay and fork-isolation boundary.
  - path: agentos/workstreams/WS-CI-MERGE-CONTROL-PLANE.md
    what: Record P3B-A acceptance, hosted amplification and P3B-B continuation.
  - path: agentos/workstreams/WS-RUNNER-FLEET-RESILIENCE.md
    what: Reconcile the fleet ledger to P3B-A acceptance without changing M1 admission.
  - path: agentos/handoffs/CI-MERGE-CONTROL-PLANE-2026-08-27-p3bb-production-route.md
    what: Preserve exact scope, local proof and the production/P4 continuation.
  - path: agentos/discoveries/DSC-REUSABLE-WORKFLOW-CALL-AND-HOST-HOOK-USE-DIFFERENT-REF-SHAPES.md
    what: Record GitHub's caller/called/start-hook ref-shape distinction and repair.
verified:
  - claim: Current main lacked the P3B-B route.
    command: python3.12 -m pytest -q tests/test_trusted_ci_production_route.py
    result: >
      Four intended red failures: trusted-ci absent, ci-pack lacked the trusted
      dependency/relay, hosted checkout was unguarded, and policy remained P3B-A.
  - claim: The implemented workflow and runner-policy boundary is green locally.
    command: >
      python3.12 -m pytest -q tests/test_trusted_ci_executor_workflow.py
      tests/test_runner_policy.py tests/test_trusted_ci_production_route.py
    result: >
      84 passed under Python 3.12.13 across workflow, route, runner-policy,
      host-admission and stable-pack-contract coverage; three inherited
      temp-cleanup warnings.
  - claim: The checked-in guard accepts the exact P3B-B route.
    command: python3 scripts/check_runner_policy.py
    result: >
      OK: only same-repository PR execution routes through the protected-main PC
      executor; hosted anchors/forks and the sole group consumer remain pinned.
  - claim: The invalid first call failed before any job or PC work.
    command: GitHub Actions run 33038617258 and signed-in annotation inspection
    result: >
      Zero jobs. GitHub rejected `@refs/heads/main` because a reusable call must
      name a branch, tag or commit. The carrier now uses `@main`; the trust gate
      separately binds called `job.workflow_ref` and immutable `job.workflow_sha`.
  - claim: The resolved call initially lacked the called workflow's read permission.
    command: GitHub Actions run 33039188648 and signed-in annotation inspection
    result: >
      GitHub resolved the exact main workflow and graph, then stopped with zero
      jobs because pull-requests read was requested by the called workflow but
      absent from the caller. The call job now grants only contents read and
      pull-requests read; no write or secret permission is introduced.
  - claim: All three drained PC roots run identical P3B-B admission bytes.
    command: >
      GitHub org runner census; systemd/Worker drain; exact SHA-256 install;
      installed allowed/fork-refused decisions; service/listener/runner re-census
    result: >
      The first production pickup, run 33039532309, failed closed before steps
      because job `env` is unavailable to the hook; its contract-delta also
      found the new route suite unwired. The repaired drained deployment uses
      Python hash 69faac248f755829a39f6821f17015382788056991f6d1ff9046b1842e86a002
      and wrapper hash d55f046e6a6a758f55e311ed73b921e007c8570cc0aba11e0cafdc31cef06dee.
      Both persisted after restart; three listeners returned online/idle; exact
      same-repo/main passed and fork returned exit 77. Dated root backups exist.
  - claim: The route introduces no contract-delta defect.
    command: python3.12 scripts/check_contract_delta.py --base dc5d8f995c1a310e245b1bee19b9daaa6c86d0fc
    result: "contract-delta: 0 introduced, 0 inherited."
  - claim: The broad planner/policy battery is classified, not hidden.
    command: >
      python3.12 -m pytest tests/test_ci_pack.py tests/test_ci_canary_tools.py
      tests/test_ci_canary_workflows.py tests/test_runner_policy.py
      tests/test_trusted_ci_executor_workflow.py
      tests/test_trusted_ci_production_route.py -q
    result: >
      216 passed; one inherited current-main startability failure at
      defense-rail-laws:engine/*.py; three temp-cleanup warnings. This carrier
      changes neither ci.yml trigger paths nor that job's scope.
unverified:
  - claim: The P3B-B carrier itself executes its selected packs on pc-ci-1/2/3.
    what_would_verify: >
      Publish the carrier from current main and observe the called main workflow,
      exact plan parity, PC receipts, trusted fragment relays and green ci-gate.
  - claim: Three ordinary product PRs avoid long hosted checkout/materialization.
    what_would_verify: >
      After merge, record three natural P4 PRs with trusted PC jobs, tiny hosted
      anchors, final gate, queue/resource/cache receipts and no repeated retries.
unresolved:
  - P3B-B is not production-proven until its own PR run concludes on the PC fleet.
  - P4 and post-cutover hosted-minute projection remain outstanding.
  - >
    M1 W2 storage is closed with about 201 GiB internal and 378 GiB external free,
    but W4 remains unadmitted; OptionsHub/Theta/MarketDesk coexistence and the
    225 GiB admission margin still forbid generic M1 CI.
next_actions:
  - Re-pin origin/main and reconcile any overlap before updating PR #6505.
  - Run focused policy/workflow/host-admission/Agent OS validation on the exact head.
  - Push only the corrected same carrier and use one mechanical CI watcher.
  - Accept only exact PC execution, plan/fragment parity, hosted anchors and green gate.
  - Merge without bypass, then collect P4 on three natural product PRs.
do_not_redo:
  - Do not rerun P1, P2, P3A, P3A-R or P3B-A.
  - Do not move hosted planner/gate/fork/fences/merge control to home hardware.
  - Do not let the caller supply SHA, base, plan, route inputs or inherited secrets.
  - Do not create a scheduler, queue, retry, lifecycle or semantic-proof plane.
  - Do not admit generic M1/macstudio or recruit M4 hardware in this wave.
danger_areas:
  - >
    Candidate-authored ci.yml may request the main call but cannot define the
    trusted jobs. github.workflow_ref binds the caller while job.workflow_ref and
    job.workflow_sha bind the called main definition.
  - >
    A green trusted executor is insufficient if the hosted and main-derived plan
    SHAs diverge; every anchor must fail before relaying a mismatched fragment.
  - >
    Skipped reusable jobs change needs semantics. ci-pack uses always() so forks
    retain hosted execution, but same-repository anchors require trusted success.
---

# P3B-B trusted-CI production route

## Observable mission

Eliminate long hosted checkout/materialization for ordinary same-repository PR
packs by executing the exact main-derived plan on the accepted three-slot PC
pool, without granting candidate-authored workflow code direct runner access.

## Acceptance boundary

- Exact caller syntax: `mastermindx-market-intelligence/macro/.github/workflows/trusted-ci-executor.yml@main`.
- Runner-group selected-workflow policy remains pinned separately to `@refs/heads/main`.
- No `with`, no inherited secrets and no direct group/label use in `ci.yml`;
  the call grants only contents read and pull-requests read.
- Same-repository PR: trusted executor plus tiny hosted `ci-pack-N` relays.
- Fork PR: existing complete hosted pack implementation.
- Hosted planner SHA must equal trusted planner SHA and fragment `plan_sha256`.
- Existing artifact names, `ci-gate`, contract delta, fences and merge controller remain.
- Called executor remains the only `macro-home-canary` group consumer and stays
  capped at three `ci-linux` jobs.

## Stop condition

Stop P3B-B after its exact PR tree proves the real PC route and merges without
bypass. Do not call the program complete: P4 still owes three natural product PR
proofs, post-cutover hosted-minute/resource/amplification telemetry and the
private-cutover acceptance packet. Repository visibility remains unchanged.
