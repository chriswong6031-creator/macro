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
  - ".github/workflows/merge-control-hosted-canary.yml"
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
    status: done
    next_action: >
      M0 is frozen by PR #6094. Do not widen it; execute the bounded W1 environment
      proof before any merge-control route change.
  - id: W1
    title: Hosted merge-control environment canary and bounded cutover
    status: done
    depends_on: [M0]
    next_action: >
      W1-B merged in PR #6222 as 578b66eb2c469859ab2a6a05cf63d5f235bd01fd.
      Production proof used hosted sweep run 32561159112 / job 97002775355 to merge
      real armed PR #6226 while M2 render job 97001136397 remained active; hosted
      pickup was 2 seconds and decisive-green-to-merge was 28 seconds.
  - id: W2
    title: Guarded M1 three-listener diagnostic restoration
    status: in_progress
    depends_on: [M0]
    next_action: >
      Three guarded diagnostic listeners, the no-op canary and one-listener crash
      recovery are healthy. Obtain the terminal 12-hour soak receipt before closing
      W2; full_work_allowed remains false below the 200 GiB free-space floor, so W4
      production admission remains blocked.
  - id: W3
    title: PC render recovery and default full-render cutover
    status: in_progress
    depends_on: [M0]
    next_action: >
      Merge the route-only render.yml default cutover on exact-head proof, then accept
      W3 only after one natural push-triggered render lands on pc-render-* and completes
      checkout, bootstrap, caches, render, guards, R2 publication and site commit/push.
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
  - .github/workflows/merge-control-hosted-canary.yml
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
  - >
    The static runner-policy PC slot/status/carrier census is known stale against the
    accepted four-listener job receipts. W5 owns coherent live-registry reconciliation;
    do not widen W3's route-only cutover into those liveness fields.
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
  - >
    Do not call the hosted canary a merge controller. It has contents:read, no merge token,
    and must never execute scripts/merge_on_green.py; it proves environment capacity only.
  - >
    Do not cite a canary artifact's accepted:true bit as the <60s pickup proof. Pickup
    is a two-source receipt: GitHub Actions run/job timing metadata plus the uniquely
    named run_id + run_attempt artifact containing job_started_at_observed.
next_action: >
  Land W3's route-only render.yml default cutover, then require one natural push-triggered
  production render on pc-render-* with successful publication before marking W3 done.
  W2's terminal 12-hour soak receipt remains independently outstanding; W4 stays blocked.
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
through `WS:CI-MERGE-CONTROL-PLANE`; W1-A supplies environment/capacity proof only and
W1-B is the separately reviewed route cutover.
