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
      The terminal 12-hour listener soak is accepted: 73 hourly samples from
      2026-08-21T08:07:28Z through 2026-08-21T20:07:56Z preserved exactly three
      intended guarded listeners with no lightweight-guard or ENOSPC failures.
      Close W2 only after the independently guarded Chrome-clone recovery completes,
      checksum parity is exact, and a fresh disk guard proves at least 200 GiB free
      and less than 85 percent used. W4 remains blocked until that final guard.
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
      HELD / NOT_ADMITTED. The current census found 50 generic macstudio jobs across
      33 workflows plus 18 macstudio-light jobs, with heterogeneous secrets, local
      stores and 5-300 minute runtime envelopes; generic macstudio remains forbidden.
      theta-m1 has historical success but no fresh bounded resource-extrema proof, and
      runner-group membership could not be read with the current credential. Admit no
      M1 production label or route until Sol accepts one exact capability-specific lane.
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
  - DSC:PERSISTENT-RUNNER-TEMP-PACKS-CAN-BREACH-THE-HOST-DISK-GUARD
artifacts:
  - research/RUNNER_FLEET_RESILIENCE_ARCHITECTURE_FREEZE_2026-08-20.md
  - research/RUNNER_FLEET_RESILIENCE_M0_ADVERSARIAL_AMENDMENT_2026-08-20.md
  - research/PRIVATE_REPO_RUNNER_STORAGE_ALLOCATION_AUDIT_2026_08_14.md
  - docs/CI_SELFHOSTED_WAVE_BC_RUNBOOK.md
  - .github/workflows/merge-control-hosted-canary.yml
  - agentos/discoveries/DSC-PRIVATE-CI-HOSTED-MINUTES-REQUIRE-TWO-LEVER-CUTOVER.md
  - agentos/discoveries/DSC-PERSISTENT-RUNNER-TEMP-PACKS-CAN-BREACH-THE-HOST-DISK-GUARD.md
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
  12-hour listener soak is accepted, but its closeout remains pending exact checksum
  verification of the guarded storage recovery and a fresh full-work disk guard.
  W4 is HELD / NOT_ADMITTED after the current consumer census; W5 remains unstarted.
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

## W2 terminal soak and guarded storage recovery — 2026-08-24 (in progress)

The W2 listener soak is accepted independently of the storage closeout. Receipt
`/Users/chriswong/runner-recovery-receipts/20260821-w2w3/m1-soak-20260821T080442Z`
contains 73 hourly samples from `2026-08-21T08:07:28Z` through
`2026-08-21T20:07:56Z`; `soak.log` has SHA-256
`b5baf6044615328e8fed16319234d71738cb7f0542cd42b9f6d8f620dd925293`. All 73
samples contained exactly the three intended guarded listener PIDs. All 219 guard
records had `lightweight_allowed=true`, and neither the soak nor the guards recorded
an ENOSPC/no-space marker. The existing no-op canary and one-listener active-GUI crash
recovery remain valid diagnostic receipts; unattended reboot recovery remains
**NOT_PROVEN**.

TerraMaster is qualified only as disposable, rebuildable, non-secret scratch. The
physical TerraMaster TDAS exposes a Lexar EQ790 4-TB NVMe at APFS UUID
`7EE5D196-8BB6-4E6D-B1D7-AFEA5DEB172A`; SMART was verified, an 8-GiB probe measured
1.268 GB/s write and 1.688 GB/s read, and a checksum marker survived a controlled
unmount/remount while the mount failed closed. APFS ownership could not be enabled,
so it is not approved for canonical Git objects, runner configuration/registration,
secrets, Agent OS state, publication state, databases, or any source of truth.

The M1 storage source is the inactive portion of
`/private/var/folders/sb/h3rq5rvj1b3_r18p6w9swyp80000gn/X/com.google.Chrome.code_sign_clone`.
The active clone `code_sign_clone.Vy0wWV` is excluded and preserved. A first guarded
copy moved 72,218,204 KiB of the fixed 153,192,948-KiB inactive set before the M2
resource guard paused it at `2026-08-24T08:41Z`; the source remains untouched and the
partial scratch destination is resumable. The expected interruption receipt is four
rsync exit-130 markers for partial directories. The continuation remained paused when
the serialized W3 window closed blocked: at `2026-08-24T12:10:14Z`, M2 runner-4 still
had an active `Runner.Worker`, a pytest process remained active, and host load was
22.91/24.02/23.97. W2 does not close until a single low-priority continuation finishes
after all production listeners drain, parent-level `rsync -aHcni --delete` reports
exact parity, only verified inactive source directories are recovered, and the
post-recovery guard proves at least 200 GiB free and less than 85 percent used.

W4 is **HELD / NOT_ADMITTED**. The current consumer census proves the broad M1 aliases
unsafe: 50 generic `macstudio` jobs across 33 workflows and 18 `macstudio-light` jobs
span heterogeneous secret, local-store and runtime requirements. No current workflow
consumes `theta-m1`; its historical M1 successes do not include fresh resource extrema,
and current authority cannot read the required organization runner-group membership
without `admin:org`. No label, runner group, workflow route, runner policy, M2 route or
M4 host changed. A future W4 may admit at most one exact capability-specific lane after
fresh proof and Sol acceptance; generic `macstudio` remains forbidden.

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
