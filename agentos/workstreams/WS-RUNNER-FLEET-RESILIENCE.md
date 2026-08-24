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
    status: done
    depends_on: [M0]
    next_action: >
      W3 was Sol-accepted on 2026-08-22 after natural production run 32592219809 /
      job 97079244558 completed on pc-render-1 through scope=all render, strict guards,
      R2 publication and generated site commit/push. Preserve the render-linux default
      and the M2 as rollback-only; do not reopen W3 absent new production evidence.
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
discoveries:
  - DSC:PRIVATE-CI-HOSTED-MINUTES-REQUIRE-TWO-LEVER-CUTOVER
artifacts:
  - research/RUNNER_FLEET_RESILIENCE_ARCHITECTURE_FREEZE_2026-08-20.md
  - research/RUNNER_FLEET_RESILIENCE_M0_ADVERSARIAL_AMENDMENT_2026-08-20.md
  - research/PRIVATE_REPO_RUNNER_STORAGE_ALLOCATION_AUDIT_2026_08_14.md
  - docs/CI_SELFHOSTED_WAVE_BC_RUNBOOK.md
  - .github/workflows/merge-control-hosted-canary.yml
  - agentos/discoveries/DSC-PRIVATE-CI-HOSTED-MINUTES-REQUIRE-TWO-LEVER-CUTOVER.md
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
  W3 is Sol-accepted and closed. Keep the overall workstream active: W2's terminal
  12-hour soak receipt remains independently outstanding and W4 stays blocked on W2.
  The private-readiness baseline in
  DSC:PRIVATE-CI-HOSTED-MINUTES-REQUIRE-TWO-LEVER-CUTOVER proves that moving packs
  alone cannot meet the 50,000-minute allowance; after PC and cutover acceptance,
  measure and reduce the complete hosted estate without weakening its protected
  control/untrusted boundary. W4/W5 remain unstarted; do not enter either wave without
  fresh Chairman intent and a current authority load.
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

## W3 Sol acceptance — 2026-08-22

Acceptance operation: `sol:runner-fleet:w3-acceptance:2026-08-22:32592219809`.

W3 is **DONE**. The first natural post-cutover production attempt, run `32585314359` /
job `97060684686`, correctly remained preserved as a failed receipt: the PC render itself
completed, but the strict dead-reference guard found scanner-visible `src = 'candidates'`
in inline JavaScript emitted into `site/us_stocks.html`, so R2 publication and site push
were blocked. Natural successor `32586474354` reproduced the same deterministic defect
before the repair reached its persisted runtime checkout. The six ticker-universe gaps
reported by both runs were warning-only churn and were not the fatal condition.

The owner-emitter repair stayed bounded to PR #6249: `templates/dashboard.html.j2` renamed
the local JavaScript identifier `src` to `mode`, and
`tests/test_p0_prophet_candidate_board.py` added rendered-output regression coverage using
the production guard matcher. The dead-reference guard, allowlists, runner routing,
workflow defaults and publication semantics were not changed or softened. Exact repair
head `f71675b4ebe8e4475ddbe5ac8a2b52331530e349` passed authoritative CI run
`32590964800` (15/15), fence run `32590964724`, and top-level authority run
`32590962835`; PR #6249 squash-merged as
`87e65fcdb7616335b4380803e180967f73370d39`.

The required natural production proof is render run `32592219809` / job
`97079244558`, triggered by the repair merge on `main`. GitHub admitted the job to
`[self-hosted, render-linux]`; runner `pc-render-1` on machine `winpc` reported
`profile=pc-render`. Automatic scope selection chose `all`. Render, ticker dossier and
stock-dossier integrity completed; the inline-JS guard and both strict dead-reference
guards completed cleanly apart from the same six explicitly nonfatal ticker-universe
warnings; market-state coherence completed successfully.

R2 publication completed on attempt 1 with 2,890 uploaded, 58 unchanged and 0 failed.
The generated-site push preserved a real non-fast-forward failure on attempt 1, performed
the existing guarded rebase and post-rebase reference/coherence/sync checks, and pushed
successfully on attempt 2 through generated commit
`380e9e32ce74a713e9455802ea04157cfdc2b980`. The acceptance packet's live production
verification measured the pushed Git object and cache-busted public
`https://mastermind-x.com/us_stocks.html` at the identical SHA-256
`c8df9856f702e3a7ac03168cbde2eb029ce9c74d0a5e44866cc7aa7eaa3a9a25`.

Sol independently re-read the raw production job log and current GitHub authority before
acceptance. Post-proof `main` drift through
`af7f4af9a86c67885e13dd2bcf80b9932e3c399a` did not alter W3's render route, repaired
emitter, dead-reference guard, regression surface, or R2/site publication semantics.
Therefore the production receipt remains current enough to close W3. This ruling does
not close the overall runner-fleet workstream and does not authorize W4 or W5.

## Private-repository hosted-minute baseline — 2026-08-24

The current GitHub enhanced-billing report makes the remaining private-cutover gap
quantitative. Macro used 74,489 gross hosted Linux minutes over the latest three
complete days, a 744,890-minute 30-day projection. A complete 2026-08-23 `ci.yml`
jobs census attributes 20,400 billed-equivalent minutes to packs, 1,148 to planning,
1,275 to contract-delta and 279 to the final gate. The same date's billing item is
28,135 minutes total.

Even moving every pack and applying PR #6286's proven sub-minute plan leaves a
6,878-minute/day counterfactual when the non-CI remainder is held constant, or
206,340 minutes per 30 days. Therefore PC pack capacity is necessary but cannot by
itself justify private readiness. The accepted cutover must preserve hosted authority,
fences, merge control and untrusted independence while also reducing execution
amplification or other avoidable hosted work, then re-measuring the billing API with
explicit headroom below the allowance. See
DSC:PRIVATE-CI-HOSTED-MINUTES-REQUIRE-TWO-LEVER-CUTOVER.
