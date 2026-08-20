---
key: RUNNER-FLEET-RESILIENCE
title: Runner fleet resilience and physical failure-domain separation
objective: >
  Make PR shipping and authoritative nightly production coexist without one physical
  host becoming a shared failure domain. Done means merge control is off the M2,
  routine full render is off the M2, guarded M1/PC capacity is live and proven, and
  fleet health is visible at physical-host rather than runner-process granularity.
status: active
program: project-active-build-control
repos: [macro]
owner: ceo-sol
class: build
blast_radius: reversible
ambiguity: specified
owns_paths:
  - ".github/runner-policy.yml"
  - ".github/workflows/m1-runner-canary.yml"
  - ".github/workflows/selfhosted-ci-canary.yml"
  - ".github/workflows/render.yml"
  - ".github/workflows/engine-render.yml"
  - "ops/runner-host/**"
  - "tests/test_runner_policy.py"
  - "tests/test_ci_canary_tools.py"
  - "tests/test_ci_canary_workflows.py"
depends_on: []
waves:
  - id: M0
    title: Physical failure-domain architecture freeze and work identity
    status: awaiting_ci
    next_action: >
      Review and merge the records-only M0 PR; no production route or runner label
      changes are authorized in M0.
  - id: W1
    title: Hosted merge-control environment canary and bounded cutover
    status: todo
    depends_on: [M0]
    next_action: >
      Commission the hosted environment canary through WS:CI-MERGE-CONTROL-PLANE;
      require three canaries including one congested-window proof before changing
      the real merge-on-green runner route.
  - id: W2
    title: Guarded M1 three-listener diagnostic restoration
    status: todo
    depends_on: [M0]
    next_action: >
      Restore the M1 using the existing ops/runner-host/m1 guarded service contract
      and pass m1-runner-canary with zero production labels.
  - id: W3
    title: PC render recovery and default full-render cutover
    status: todo
    depends_on: [M0]
    next_action: >
      Re-prove at least two render-linux listeners, a real engine-render, and one
      scope=all render on the PC before changing render.yml's default route.
  - id: W4
    title: Bounded M1 production-capacity return
    status: todo
    depends_on: [W2]
    next_action: >
      Census every current macstudio consumer and its memory/local-capability envelope,
      then admit one explicitly selected safe production lane through m1-nightly and
      restore theta-m1 only on the proven store-bearing listener. Do not add the generic
      macstudio label to the M1 in this wave.
  - id: W5
    title: Retire obsolete M2 roles and add live fleet health projection
    status: todo
    depends_on: [W1, W3, W4]
    next_action: >
      Remove routine merge/render roles from the M2 after rollback soak and add a
      hosted read-only fleet liveness projection without creating scheduler state.
  - id: W6
    title: Nightly critical-path reduction after allocation stabilizes
    status: todo
    depends_on: [W5]
    next_action: >
      Reopen the measured Aug-13 collector/engine decomposition plan and reduce the
      critical path using nightly timing receipts; do not mix this with fleet recovery.
decisions:
  - DEC:RUNNER-FLEET-PHYSICAL-FAILURE-DOMAINS
artifacts:
  - research/RUNNER_FLEET_RESILIENCE_ARCHITECTURE_FREEZE_2026-08-20.md
  - research/RUNNER_FLEET_RESILIENCE_M0_ADVERSARIAL_AMENDMENT_2026-08-20.md
  - research/PRIVATE_REPO_RUNNER_STORAGE_ALLOCATION_AUDIT_2026_08_14.md
  - docs/CI_SELFHOSTED_WAVE_BC_RUNBOOK.md
landmines:
  - >
    `parked` is not an exclusion label; positive label matching still routes jobs to
    that listener. See .github/runner-policy.yml.
  - >
    A self-hosted runner name is not a physical-host identity; multiple listeners on
    one M2 share CPU, memory, SSD, filesystem and Git I/O. See
    DEC:RUNNER-FLEET-PHYSICAL-FAILURE-DOMAINS.
  - >
    The M1 old services died after ENOSPC and included stale identity; never restore
    historical labels before the guarded m1-runner-canary passes. See
    research/PRIVATE_REPO_RUNNER_STORAGE_ALLOCATION_AUDIT_2026_08_14.md.
  - >
    The generic macstudio label is a broad capability grant, not a capacity label. On
    the 32-GB M1 it is forbidden until a separate current-consumer/resource census proves
    every macstudio job is lawful there. See the M0 adversarial amendment.
  - >
    `render-linux` being declared in runner-policy does not prove it is online; the
    registry is static operator-maintained state. Re-prove current PC liveness.
do_not_redo:
  - >
    Do not buy hardware before restoring and measuring the existing M1/PC fleet; the
    Aug-14 audit's hardware verdict is BUY NOTHING.
  - >
    Do not create another runner registry, scheduler, queue, or merge implementation;
    GitHub Actions, .github/runner-policy.yml, the Wave B/C runbook and the existing
    merge controller remain canonical.
  - >
    Do not treat PR #6089 as having fixed runner starvation; it fixed Asia-close's
    starvation blindness/classification bug and explicitly left runner starvation
    separate.
  - >
    Do not restore generic macstudio to the M1 merely because mac-builder-1/2 historically
    carried production. Current workload/resource compatibility must be re-proven first.
next_action: >
  Get M0 records green and merged, then execute W1 only: hosted merge-control
  environment canary under WS:CI-MERGE-CONTROL-PLANE. Prepare W2/W3 diagnostic host
  recovery in parallel only if it changes no production labels or default routes.
---

## Current incident

On 2026-08-20 the live `macstudio` pool was starved for about four hours and Asia gate
jobs waited 15-58 minutes for a runner. The primary root is fleet allocation: routine
heavy render and production share the M2, while M1/PC capacity is disconnected or
under-routed and merge-control remains on the same physical M2.

## Authority boundary

This workstream owns fleet topology, host recovery, runner policy, canary substrate, and
render routing. It does **not** own merge semantics. Any edit to
`.github/workflows/merge-on-green.yml` or `scripts/merge_on_green.py` is commissioned
through `WS:CI-MERGE-CONTROL-PLANE`; W1 only supplies the environment/capacity proof and
the physical-failure-domain requirement.