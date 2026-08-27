---
workstream: "WS:CI-MERGE-CONTROL-PLANE"
session: codex/ci-p3a-trusted-executor-6351
model: codex
ended_because: ci_handoff
mission: >
  Close #6351 P2 from exact receipts and implement P3A: one main-owned,
  dispatch-provable but production-inert trusted PC executor, without changing
  production ci.yml, hosted control/fork routes, required check names, merge
  semantics or repository visibility.
state_before: >
  P1 was accepted. P2 had three concurrent PC packs and an independent render
  receipt, but the first wrapper was cancelled by a redundant hosted comparator
  checkout. PR #6479 removed that compare-only checkout and merged as
  c7aff16358865c177d85e68ca7d1f803ab4e7bad. Production ci.yml remained hosted.
changed:
  - path: .github/workflows/trusted-ci-executor.yml
    what: >
      New reusable/dispatch workflow. P3A refuses workflow_call and any indirect
      caller by requiring the exact direct-dispatch workflow_ref, accepts only a
      main dispatch with a numeric same-repository PR, freezes one exact pack on
      hosted control, then runs it on the selected macro-home-canary/ci-linux route
      through the root-owned cache and emits existing receipt/fragment artifacts.
  - path: .github/runner-policy.yml
    what: >
      Declares the exact main-pinned executor workflow, P2-live PC labels and an
      explicit production_enabled=false P3A route while ordinary/fork PR CI stays
      hosted.
  - path: scripts/check_runner_policy.py
    what: >
      Adds mapping-form group+label parsing and R13 hostile enforcement for the
      inert executor, including exact executable event/ref/workflow-ref predicates,
      a one-field input surface and refusal of early production wiring.
  - path: ops/runner-host/common/runner_admission.py
    what: >
      Extends only the pc-ci root-owned job-start allowlist with the exact direct
      main workflow_dispatch trusted-pack tuple. workflow_call, PR refs, forks,
      alternate workflow paths/jobs, M1 and render profiles remain refused.
  - path: scripts/run_ci_pack.py
    what: >
      Adds trusted-ci-executor as the second exact main-owned diagnostic workflow
      allowed to mint/consume pr_head/workflow_dispatch plans. The global role/event
      set stays closed and every PR identity invariant remains unchanged.
  - path: tests/test_trusted_ci_executor_workflow.py
    what: >
      Locks direct-dispatch-only P3A runtime admission, the single pr_number input,
      hosted planning, selected runner group, negotiated credential-free
      materialization, single-plan consumption, evidence publication and absence
      of secrets/generic M1/render routes.
  - path: tests/test_ci_canary_tools.py
    what: >
      Locks the exact PC host-admission tuple and hostile workflow_call, main-caller,
      PR-ref, fork, alternate-job and alternate-workflow refusals.
  - path: tests/test_runner_policy.py
    what: >
      Adds discriminating mutations that neutralize each executable P3A trust
      predicate or add caller-supplied identity input and require R13 to fail.
  - path: agentos/decisions/DEC-TRUSTED-CI-MAIN-DEFINED-EXECUTOR-BOUNDARY.md
    what: Main-defined executor trust-boundary freeze and P3A/P3B split.
verified:
  - claim: P2 exact three-pack parity and PC capacity are accepted.
    command: >
      gh api actions/runs/32960314514/jobs and actions/runs/32964925696/jobs;
      gh run download 32964925696; compare pack 0/1/9 receipt identities,
      cache/resource fields and semantic-fragment bytes with cmp and SHA-256
    result: >
      Run 32960314514 completed three PC packs concurrently and the independent
      pc-render-4 reservation. Run 32964925696 made all three checkoutless
      comparators green on tested SHA 39d1e635fa621ef04991c7b8694a2e5359d22238
      and plan c813cfcca942208c86b4cc203843e9ab34354df0f92327a93fb5df9915d357a3.
      PC wall time was 164.689-216.668s versus hosted 680.467-2050.9s; all three
      fragments were byte-identical; cache bytes were unchanged; resource floor
      was 42,649,702,400 bytes available memory and 878,784,360,448 bytes free disk.
  - claim: P3A targeted policy, workflow and canary tests are green.
    command: >
      python3.12 -m pytest -q tests/test_trusted_ci_executor_workflow.py
      tests/test_runner_policy.py tests/test_ci_canary_workflows.py
      tests/test_ci_canary_tools.py --maxfail=10
    result: 80 passed with 3 inherited pytest temp-cleanup warnings.
  - claim: The closed semantic admission remains covered.
    command: >
      python3.12 -m pytest -q tests/test_ci_pack.py --maxfail=10
    result: >
      112 passed; one inherited current-main failure in
      test_derived_scopes_are_startable_by_the_ci_workflow for untouched
      defense-rail-laws engine/*.py. The branch has no diff from origin/main in
      .github/ci/legacy-jobs.yml or .github/workflows/ci.yml.
  - claim: Static policy and whitespace validation are clean.
    command: python3.12 scripts/check_runner_policy.py; git diff --check
    result: PASS.
unverified:
  - claim: Exact-head hosted CI/fences and merge acceptance.
    what_would_verify: Push one PR carrier, conclude authoritative checks, then merge.
  - claim: The organization runner group accepts the new exact main workflow path.
    what_would_verify: >
      After merge, add only trusted-ci-executor.yml@refs/heads/main to the existing
      macro-home-canary selected-workflow list and re-read the saved server state.
  - claim: All three PC CI roots run the merged root-owned admission bytes.
    what_would_verify: >
      After merge and while jobs are drained, deploy
      ops/runner-host/common/runner_admission.py to
      /usr/local/libexec/runner_admission.py on pc-ci-1/2/3, verify the same SHA-256
      on all three roots, and re-read one allowed and hostile refused tuple per root.
  - claim: One real P3A pack succeeds on main and emits a cache-stable receipt.
    what_would_verify: >
      Dispatch trusted-ci-executor.yml on main for a same-repository PR after the
      selected-workflow update; inspect the exact receipt and host resources.
unresolved:
  - >
    P3B is forbidden until P3A merges, the server-side path is verified and the
    one-pack dispatch proof is accepted. Production ci.yml remains hosted.
  - >
    The full semantic suite's inherited defense-rail-laws scope gap is not absorbed
    into this authority carrier; it is unrelated to every changed P3A path.
next_actions:
  - Complete adversarial review, exact-head CI and merge of the P3A carrier.
  - Drain pc-ci-1/2/3; deploy the merged runner_admission.py bytes to all three
    root-owned hook paths; re-read identical SHA-256 plus one accepted and one
    hostile-refused decision on every root.
  - Add only the exact workflow path to the existing runner group, re-read its
    selected-workflow state, dispatch one real proof pack and post the receipt to
    issue #6351.
  - Only then implement P3B on a separate current-main carrier.
do_not_redo:
  - Do not wire production ci.yml in P3A or dismiss workflow_call refusal early.
  - Do not grant the runner group all-workflow access or a PR branch ref.
  - Do not execute fork/untrusted work, secrets or generic M1/render jobs here.
  - Do not create a parallel scheduler, queue, semantic proof or retry plane.
danger_areas:
  - >
    The called workflow inherits the caller GitHub context. In P3A the exact
    github.workflow_ref equality deliberately distinguishes direct dispatch from
    every caller and makes workflow_call inert. P3B must replace that direct-only
    predicate with an explicit same-repository caller authority contract; do not
    mistake the caller workflow_ref for the called workflow identity.
  - >
    Do not accept candidate-supplied tested SHA, base SHA, plan hash or workflow
    path in P3B. Resolve the same-repository PR again inside the main-defined
    workflow and preserve exact synthetic-merge parent checks.
  - >
    Updating .github/runner-policy.yml does not mutate the organization runner
    group. The exact saved server-side selected-workflow state needs its own receipt.
---
