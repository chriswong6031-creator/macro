---
workstream: "WS:RUNNER-FLEET-RESILIENCE"
session: codex/private-readiness-baseline-20260824
model: codex
ended_because: blocked
mission: >
  Establish a current hosted-minute and execution-amplification baseline while
  the protected ci.yml carrier, PC capacity and M1 soak remain externally gated,
  without changing a workflow, runner route, label, service or visibility state.
state_before: >
  PR #6286 was parked DRAFT/HOLD-FOR-SOL at exact receipt head
  7fe2a5604f4938161b2630f6f6c15d8d436a3822; the PC was unreachable; M1 W2's
  fixed 12-hour soak was healthy but nonterminal; TerraMaster was unidentified;
  and the Aug-14 audit's 519,805-minute six-day observation was the latest
  durable private-readiness usage receipt.
changed:
  - path: agentos/discoveries/DSC-PRIVATE-CI-HOSTED-MINUTES-REQUIRE-TWO-LEVER-CUTOVER.md
    what: >
      Record the current billing trajectory, complete Aug-23 ci.yml run/job
      census, two-lever feasibility result, falsifier and post-cutover acceptance
      consequence.
  - path: agentos/workstreams/WS-RUNNER-FLEET-RESILIENCE.md
    what: >
      Cite the discovery and make complete hosted-estate measurement an explicit
      private-readiness obligation while preserving every wave status and gate.
  - path: agentos/handoffs/RUNNER-FLEET-RESILIENCE-2026-08-24-private-readiness-baseline.md
    what: >
      Return the cold-start continuation packet without inventing another runner
      registry, scheduler, lifecycle or retry plane.
verified:
  - claim: >
      GitHub's enhanced-billing report returns the current Macro Actions Linux
      daily quantities, including 74,489 minutes over Aug 21-23 and 28,135 on
      Aug 23.
    command: >
      gh api -H 'X-GitHub-Api-Version: 2026-03-10'
      'organizations/mastermindx-market-intelligence/settings/billing/usage?year=2026&month=8'
    result: >
      519,805 minutes Aug 9-14; 342,501 Aug 15-23; 74,489 Aug 21-23;
      Aug-23 quantity 28,135; all Macro / Actions Linux / Minutes.
  - claim: >
      The complete Aug-23 ci.yml execution estate and per-job rounded timing
      decompose the hosted plane rather than relying on the old 95-98 percent
      estimate.
    command: >
      GET the four six-hour partitions of
      repos/mastermindx-market-intelligence/macro/actions/runs?created=2026-08-23,
      then GET actions/workflows/ci.yml/runs and actions/runs/{id}/jobs for all
      291 ci.yml runs; round every started/completed job up independently.
    result: >
      2,433 all-workflow runs; 291 ci.yml runs; 2,703 executed CI jobs;
      packs 20,400 minutes, plan 1,148, contract-delta 1,275, gate 279,
      total 23,102; cancelled CI runs 3,590.
  - claim: >
      The one-day counterfactual proves pack migration plus PR #6286's
      exact-head planner timing is insufficient by itself.
    command: >
      28135 - 20400 - (1148 - 291) = 6878; 6878 * 30 = 206340
    result: >
      6,878 hosted minutes/day and 206,340/30d with every non-CI consumer held
      constant, more than four times the whole allowance before headroom.
  - claim: >
      The existing PC Wave-B/C management path was still unreachable at the
      action-time gate, so no drain, WSL tuning or qualification dispatch was
      entered.
    command: >
      ssh -o BatchMode=yes -o PasswordAuthentication=no
      -o KbdInteractiveAuthentication=no -o ConnectTimeout=12 winpc-wsl true
    result: >
      ssh to 100.121.5.60 port 22 timed out with exit 255. The bounded operator
      stopped before any host or GitHub state change.
  - claim: >
      M1 W2 remained healthy but nonterminal, and its guard still denied full
      work.
    command: >
      Read-only inspection of PID 32929 and
      /Users/chriswong/runner-guard/receipts/W2_M1_12H_SOAK_20260824T091217Z.jsonl
      on host m1.
    result: >
      Twelve successful samples 0-11, zero failures and zero Workers through
      2026-08-24T11:57:16Z; all three exact listener mappings were healthy;
      free_bytes 118974808064, used 75.93 percent, lightweight_allowed true and
      full_work_allowed false. The fixed end is 2026-08-24T21:12:17Z and no
      terminal record existed.
  - claim: >
      No intended TerraMaster scratch identity or safe native M1 reclaim route
      was established.
    command: >
      Bounded visible Finder Network and Disk Utility inspection; local and M1
      non-credentialed SMB/NFS Bonjour discovery; M1 read-only diskutil, APFS
      snapshot, Time Machine snapshot and size-only structural checks.
    result: >
      No TerraMaster-labelled or NFS target appeared. /Volumes/STORAGE is a
      separate 1 TB USB HFS+ volume with about 441 GB used and no disposable
      scratch authority. Data and Time Machine had no reclaimable local
      snapshots; no storage write, purge, move, mount or cleanup was attempted.
unverified:
  - claim: >
      A production trusted-CI cutover actually reduces the billing trajectory by
      the counterfactual amount.
    what_would_verify: >
      Accepted PC capacity, accepted #6286 carrier, production pack cutover and a
      subsequent enhanced-billing report over a representative natural window.
  - claim: >
      The final private-ready projection has meaningful headroom below 50,000.
    what_would_verify: >
      A post-cutover whole-estate monthly projection accepted by Sol, including
      all hosted workflows rather than ci.yml alone.
  - claim: >
      M4 capacity is necessary.
    what_would_verify: >
      Post-optimization PC/M1/M2 queue and resource telemetry demonstrating a
      measured capacity failure. No such evidence exists now.
unresolved:
  - >
    The exact safe second lever is intentionally not selected before #6286 and
    PC acceptance. It must preserve hosted control/untrusted independence and
    current semantic proof, so a blanket move of every hosted job to home runners
    is not an admissible answer.
  - >
    GitHub's billing report supplies a dated usage item but does not document in
    the endpoint schema whether its date is posting time or the exact execution
    UTC day. The same-day comparison is a feasibility bound; post-cutover
    acceptance must use a multi-day natural window so a one-day boundary cannot
    decide the verdict.
next_actions:
  - >
    Wait for Sol to accept, reject or release PR #6286; do not poll or mutate the
    ratified hold in the meantime.
  - >
    When the PC is physically reachable, drain first, then execute one-slot
    exact-tree parity followed by three CI slots plus one independent render slot.
  - >
    Adjudicate the fixed M1 soak after 2026-08-24T21:12:17Z at its terminal
    receipt; keep W4 closed while full_work_allowed is false and no TerraMaster
    scratch identity is qualified.
  - >
    After the accepted production cutover, re-run whole-estate billing and
    workflow amplification measurements before requesting private visibility.
do_not_redo:
  - >
    Do not infer private readiness from ci-pack percentage, green parity or
    self-hosted capacity alone. The whole hosted estate is the billing boundary.
  - >
    Do not weaken or silently self-host authority, fences, merge control, forks
    or other untrusted work to chase the allowance.
  - >
    Do not create a second metrics database, runner registry, scheduler, queue,
    lifecycle, retry plane or CI proof system; GitHub billing/runs and the current
    Agent OS records are sufficient evidence sources.
  - >
    Do not recruit the M4 fleet before post-optimization telemetry proves the
    existing PC/M1/M2 capability envelope fails.
danger_areas:
  - >
    Public-repository Actions minutes are discounted today. The gross quantity,
    not current net spend, is the prospective private-repository risk.
  - >
    GitHub rounds each job independently, so summing workflow wall clocks
    understates private usage when a run fans out across packs.
  - >
    A cancelled workflow is not free: Aug-23 cancelled CI runs consumed 3,590
    billed-equivalent minutes before cancellation concluded.
discoveries:
  - "DSC:PRIVATE-CI-HOSTED-MINUTES-REQUIRE-TWO-LEVER-CUTOVER"
---

## State

The baseline capability is complete locally. It changes knowledge only and
preserves every external gate. The private-cutover program remains active and
nonterminal.

## Exact continuation boundary

The next implementation is not authorized by this handoff. Resume only on an
actual gate change: Sol release/decision for #6286, physical PC reachability, or
the fixed M1 terminal receipt. When production cutovers eventually land, use
this record as the pre-cutover side of the natural telemetry comparison.
