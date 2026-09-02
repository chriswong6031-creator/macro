---
workstream: "WS:RUNNER-FLEET-RESILIENCE"
session: "Codex:/root/c3ra_false_proof_repair (detached worktree c3ra-merged-substrate-full-repair-01a05fa8)"
model: codex
ended_because: complete
mission: >
  Operation ci-c3ra-merged-substrate-full-repair-20260901-sol-001 on existing
  PR #6728 and branch claude/ci-c3ra-slice-path-hierarchy-fix. Preserve the
  valid hierarchy/aggregate-parent corrections at pickup head
  04d30860e1309d427e160319072c6cb150f35e47; repair every false-proof family in
  exact review 5085372259 under RED-first tests; history-preservingly join
  current main; and return the exact head DRAFT / HOLD-FOR-SOL without host,
  runner, registration, credential, dispatch, cache, render or production effect.
state_before: >
  PR #6718 had merged as b260d28a6efbfb4593dfcc453731f71703252ac0
  while review 5084468618 remained CHANGES_REQUESTED. Its real-host staging
  attempted only pc-ci-1, which refused for about 96 seconds and was restored;
  pc-ci-2/3 were untouched. PR #6728 head 04d30860e1309d427e160319072c6cb150f35e47
  correctly represented systemd's /mastermind.slice/mastermind-ci.slice hierarchy
  and read aggregates from the parent node, but review 5085372259 found the
  six remaining release blockers. Production still had exactly three ci-linux
  carriers and trusted-executor max-parallel 3.
changed:
  - path: ops/runner-host/pc/mastermind_ci_resource_guard.py
    what: >
      Requires exactly one direct service below the real systemd slice chain;
      resolves canonical candidate and parent cgroup nodes; records both
      device/inode identities; and, for every --require-slice invocation, refuses
      unless all four parent limits exactly match the frozen envelope. Strict
      four-slot memory and I/O PSI must be present, finite, non-negative and below
      (not equal to) the frozen threshold.
  - path: scripts/monitor_ci_host_resources.py
    what: >
      Mirrors exact-direct membership and canonical-node refusal, preserves the
      candidate service separately from the aggregate parent, records both stable
      identities, and carries the exact parent-limit tuple in the existing sample.
  - path: scripts/capture_ci_canary_receipt.py
    what: >
      Validates and freezes candidate cgroup, aggregate cgroup, both identities and
      the exact parent limits. Missing slice endpoints, non-monotonic timestamps,
      identity/limit changes, and any decreasing CPU, memory-event, pids-event or
      PSI cumulative counter poison the window and clear all numeric acceptance
      fields.
  - path: .github/workflows/selfhosted-ci-canary.yml
    what: >
      Adds one slots=4-only, no-checkout, root-owned four-slot-canary preflight and
      makes the matrix require its success. Slots 1 and 3 preserve their prior
      journey, labels and fanout behavior.
  - path: ops/runner-host/common/runner_cleanup.py
    what: >
      Refuses a symlinked or noncanonical allowlisted runner root, a symlinked
      _work, or a resolved _work outside the sealed root before deleting anything.
  - path: scripts/check_runner_policy.py
    what: >
      R14 validates list and string types before comparison and requires the exact
      ordered pending-label identity [self-hosted, Linux, X64]. R6 admits only the
      exact source-defined four-slot-preflight tuple without changing live topology.
  - path: tests/test_ci_canary_tools.py
    what: >
      Adds RED-first mutants for direct membership, every parent limit, strict PSI,
      identity/time/counter reset, missing endpoints, exact receipt limits, and
      symlinked cleanup roots.
  - path: tests/test_ci_canary_workflows.py
    what: >
      Pins the strict preflight as slots=4-only, blocking, no-checkout and upstream
      of fanout while preserving the slots 1/3 route.
  - path: tests/test_runner_policy.py
    what: >
      Adds malformed R14 pending-label cases covering subset, duplicate, scalar,
      non-string and nested values without traceback.
  - path: docs/CI_SELFHOSTED_WAVE_BC_RUNBOOK.md
    what: >
      Replaces the old false-proof statements with exact candidate/parent evidence,
      limit, PSI, workflow and invalid-window semantics; records #6718's 96-second
      contained incident and #6728's DRAFT / HOLD-FOR-SOL boundary.
  - path: agentos/workstreams/WS-RUNNER-FLEET-RESILIENCE.md
    what: >
      Records the merged-substrate review/repair and keeps capability state at
      BUILT_NOT_PROVEN / RELEASE_BLOCKED pending exact-head gates and C3R-B.
  - path: agentos/handoffs/WS-RUNNER-FLEET-RESILIENCE-2026-09-02.md
    what: This exact continuation receipt.
verified:
  - claim: "All three C3R-A suites pass after the RED-first false-proof repairs."
    command: "python3 -m pytest -q tests/test_ci_canary_tools.py tests/test_ci_canary_workflows.py tests/test_runner_policy.py"
    result: "200 passed, 176 inherited pytest temporary-cleanup warnings in 23.98s"
  - claim: "Runner policy and direct policy unit tests accept the repaired source boundary."
    command: "python3 -m pytest -q tests/test_runner_policy.py && python3 scripts/check_runner_policy.py"
    result: "60 passed; policy checker rc=0"
  - claim: "The final exact candidate preserves the pickup head as ancestor and current main by a history-preserving merge."
    command: "git merge-base --is-ancestor 04d30860e1309d427e160319072c6cb150f35e47 HEAD && git merge-base --is-ancestor 10a34bf76269dd5933783df4415a41b61b8944b7 HEAD"
    result: "both rc=0"
unverified:
  - claim: >
      The repaired exact source head passes all repository CI checks on GitHub.
    what_would_verify: Current-head PR #6728 checks conclude green after the single lawful push.
  - claim: >
      The exact envelope, cgroup identities and four-candidate aggregate deltas are
      truthful on the real WSL guest under natural four-slot load.
    what_would_verify: >
      The separately authorized C3R-B privileged carrier installs the reviewed
      bytes, proves every service/PID/root/cgroup/limit identity, and runs the
      bounded real-host acceptance. No source-only test can supply this proof.
unresolved:
  - >
    Review 5085372259 stays CHANGES_REQUESTED until its reviewer/Sol decides the
    exact repaired head. Worker tests and another principal's source review must not
    dismiss or overwrite that binding review.
  - >
    C3R-B remains unstarted. It is the only carrier that may perform installation,
    pc-ci-4 registration, cgroup/systemd changes or real four-slot acceptance.
next_actions:
  - >
    Sol reviews the exact held PR #6728 head plus concluded CI and independent
    adversarial result, then explicitly accepts or returns another repair. The
    worker does not mark ready, arm merge, merge, or dismiss CHANGES_REQUESTED.
  - >
    Only after Sol releases this hold may the separately commissioned C3R-B perform
    a fresh host/runner/effect census and privileged real-host proof.
  - >
    Only after C3R-B acceptance may another promotion carrier add pc-ci-4 to the
    live ci-linux roster or move trusted-executor max-parallel from 3 to 4.
do_not_redo:
  - >
    Do not restore the flat /mastermind-ci.slice path or read aggregate metrics from
    a candidate service. systemd expands the unit to the hierarchical parent and the
    frozen envelope lives on that parent node.
  - >
    Do not treat stable path strings as stable cgroup identity. Candidate and parent
    device/inode identities both freeze the window; recreation poisons it.
  - >
    Do not turn missing/malformed PSI, limits, sample endpoints or cumulative
    counters into zero. Unavailable evidence cannot satisfy a strict acceptance gate.
  - >
    Do not register the fourth preflight in live pool topology. The exact diagnostic
    job is source-defined so pending architecture cannot look routable before C3R-B.
  - >
    Do not revive the terminal ci-pc-fourth-slot-recovery-20260901-sol-001 carrier,
    mint a replacement branch/PR/watcher/control plane, or reuse its worktree.
danger_areas:
  - >
    monitor_ci_host_resources.py remains stdlib-only because the trusted workflow
    copies it alone outside the candidate checkout.
  - >
    The no-checkout preflight executes the installed root-owned helper, not candidate
    source. It is deliberately a machine gate but remains dark until C3R-B installs
    the exact reviewed helper and slice.
  - >
    The live three services do not currently pass --require-slice. Adding that flag
    without the exact parent slice is a bootstrap refusal; installation and unit
    rollout must remain one staged, rollback-ready C3R-B act.
prs: [6728]
---

# Summary

The repaired source rejects every false-green shape named by exact review
`5085372259` while preserving #6728's valid systemd hierarchy and aggregate-parent
corrections. The strongest invariant is now end to end: one exact direct candidate
service proves membership, one canonical parent proves the complete envelope, and
the reducer emits numbers only for a strictly ordered monotonic window whose two
identities and four limits never changed.

This is still source, not capacity. PR #6728 remains DRAFT / HOLD-FOR-SOL;
production remains exactly three `ci-linux` carriers at `max-parallel: 3`; and no
host, runner, registration, label, cgroup, service, cache, credential, render,
dispatch or production effect occurred in this operation.
