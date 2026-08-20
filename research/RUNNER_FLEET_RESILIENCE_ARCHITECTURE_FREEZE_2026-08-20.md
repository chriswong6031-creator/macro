# Runner Fleet Resilience — architecture freeze and execution program

**Date:** 2026-08-20  
**Authority:** Chairman escalation → Sol architecture freeze  
**Workstream:** `WS:RUNNER-FLEET-RESILIENCE`  
**Decision:** `DEC:RUNNER-FLEET-PHYSICAL-FAILURE-DOMAINS`

## 0. Outcome

Mastermind must be able to ship PRs and complete authoritative nightly production at the
same time. A multi-hour render, collector, or local Git/I/O storm on one physical machine
must not be capable of simultaneously starving production work, the merge arbiter, and
interactive session Git operations.

Done means all four are true in production, not merely configured:

1. **Shipping control is independent of M2 production load.** Merge-control runs outside
   the M2 physical failure domain and continues reconciling armed PRs during a real heavy
   nightly/render window.
2. **Routine full render is independent of M2 production load.** `render.yml` and
   `engine-render.yml` have a healthy PC route; automatic full render no longer defaults to
   the M2.
3. **Owned Mac capacity is actually usable.** The M1 returns through the existing guarded
   service/canary contract before any production label is restored, then contributes
   bounded production/store capacity without recreating the ENOSPC failure.
4. **The fleet is observable as physical hosts.** The system can distinguish “four runner
   processes on one Mac” from “four independent machines/slots” and can surface offline,
   orphaned, or saturated capability before a nightly or merge train depends on it.

No new queue, state store, runner registry database, or merge implementation is authorized.
GitHub Actions remains the scheduler; `.github/runner-policy.yml` remains the checked-in
routing declaration; Agent OS remains organizational memory.

---

## 1. Intent recovery

Chairman symptom: every night, multiple coding sessions report `SHIP LOOP BLOCKED` and PRs
stop merging while the M2 Ultra Mac Studio is audibly busy with collect/render work; the
M1 Studio and PC appear comparatively idle.

The user job is not “make GitHub faster.” It is:

> **A session that has completed correct work should be able to ship while production is
> baking, and production should not lose sessions because a render or control-plane job
> consumed the same physical machine.**

The machine job is to allocate portable work away from scarce/store-bound Mac production
capacity, recover existing owned hardware safely, preserve single owners for each control
plane, and make failure-domain capacity visible.

---

## 2. Verified current state

### 2.1 Production incident proves runner starvation

PR #6089 records the 2026-08-20 incident:

- the `macstudio` runner pool was starved for about **4 hours**;
- multi-hour render runs occupied `mac-builder-light` while short production/intraday lanes
  cycled on `mac-builder-5`;
- one-minute Asia gate jobs waited **15–58 minutes** for a runner;
- the queue delay then triggered a separate gate-classification bug and the settled CN/HK
  builders missed their session.

The gate-classification bug is fixed by #6089. The starvation that exposed it is not.

### 2.2 “Six M2 runners” is not six-machine capacity

`.github/runner-policy.yml` states:

- `macstudio` → `mac-builder-5`, `mac-builder-light`;
- `render-heavy` → `mac-builder-light`;
- `merge-control` → `mac-builder-4`;
- `macstudio-light` → `mac-builder-3`.

Those are logical listeners. `mac-builder-3/4/5/light` are all on the same M2 Ultra
physical Mac. The registry itself explicitly notes that `render-heavy` shares a host with
`macstudio`, so heavy render and production bake contend.

### 2.3 M1 capacity exists but died after ENOSPC

`research/PRIVATE_REPO_RUNNER_STORAGE_ALLOCATION_AUDIT_2026_08_14.md` directly mapped
runner metadata to hardware and found:

- M1 Max Studio: 10 cores / 32 GB;
- three configured runner services, zero listener processes after an Aug-13
  `No space left on device` crash;
- disk later recovered to about 168 GiB free but the old `RunAtLoad` service design did not
  restart the listeners;
- historically `mac-builder-1/2` ran collect, engine, factor-series, collect-tail and other
  nightly work.

The repository now contains the safer replacement contract:

- `ops/runner-host/m1/run_guarded_runner.sh`;
- `ops/runner-host/m1/actions-runner.plist.template` with
  `KeepAlive.SuccessfulExit=false`;
- disk guard and diagnostic-log maintenance;
- `.github/workflows/m1-runner-canary.yml`, which expects three distinct live listener PIDs
  and performs no checkout or secret read.

The M1 return substrate is therefore **built but not production-proven**.

### 2.4 PC render capability is real but current availability is not trustworthy

The Aug-14 fleet audit directly proved four PC/WSL listeners and recent
`engine-render` work. `render.yml` records a measured full render on `pc-render-1` at about
81 minutes. `engine-render.yml` already defaults to `render-linux`.

However the checked-in runner registry was refreshed Aug-17 and records the PC
`render-linux` pool as offline. The static registry is declaration, not live observation.
The Chairman's present observation that the PC is quiet is therefore consistent with an
offline WSL/service state. We must re-prove, not infer.

### 2.5 PR proof is already mostly outside the self-hosted fleet

Macro ordinary PR CI/fences are GitHub-hosted by policy. Terminal CI and Mastermind CI also
run on `ubuntu-latest`. `integration-baseline.yml` was explicitly moved to the Enterprise
hosted pool and documents current hosted pickup as seconds rather than the old saturated
queue regime.

The remaining shipping control-plane exception is Macro `merge-on-green`, which still runs
on `[self-hosted, macOS, ARM64, merge-control]` → `mac-builder-4` on the M2.

### 2.6 M2 local I/O is already a known session hazard

PR #5967 measured a full-worktree `git status --porcelain` taking **161 seconds** under
fleet I/O load. The ship-loop guard had to be hardened against timeout/index-lock damage.
That incident proves the interactive/session Git plane shares meaningful host I/O pressure
with the Actions listeners even when labels differ.

---

## 3. Capability ledger

| Capability | State | Evidence / ruling |
|---|---|---|
| Macro ordinary PR CI on hosted | **PROVEN_LIVE** | `.github/runner-policy.yml`; current `ci.yml` |
| Terminal/Mastermind CI on hosted | **PROVEN_LIVE** | both repositories' `ci.yml` |
| Hosted integration baseline | **PROVEN_LIVE** | `integration-baseline.yml`; Enterprise hosted comments |
| M2 `merge-control` listener | **PROVEN_LIVE** | `merge-on-green.yml`; runner registry |
| Merge-control physically isolated from M2 | **NOT_BUILT** | current route is M2 |
| M2 default full render | **PROVEN_LIVE, REJECTED BY DESIGN AS END-STATE** | works, but #6089 proves contention |
| PC `engine-render` capability | **PROVEN_LIVE historically / DARK_OR_DISCONNECTED now** | Aug-14 audit vs Aug-17 registry |
| PC full `render.yml` capability | **PROVEN_LIVE historically / DARK_OR_DISCONNECTED now** | ~81m measured render; current offline registry |
| M1 guarded launcher + disk/log law | **BUILT_NOT_PROVEN** | `ops/runner-host/m1/*` |
| M1 three-listener no-op canary | **BUILT_NOT_PROVEN** | `m1-runner-canary.yml`; no live `m1-theta` route |
| M1 production labels after guarded recovery | **NOT_BUILT / NOT_AUTHORIZED UNTIL W2 ACCEPTS** | Wave B/C deliberately omitted old labels |
| Live physical-host runner health projection | **NOT_BUILT** | runner registry is hand-maintained static state |
| Physical-failure-domain admission law | **SPEC_ONLY until this M0 merges** | this freeze + DEC |
| Nightly critical-path shortening | **PARTIAL** | Aug-13 compute audit measured plan; separate later wave |

---

## 4. Frozen target topology

### 4.1 GitHub-hosted — portable control/proof plane

Owns:

- ordinary PR CI;
- fences;
- integration baseline;
- liveness/watchdogs;
- **merge-on-green after W1 canary acceptance**.

It does **not** own production collectors or host-local data/capability lanes.

### 4.2 PC/WSL — render/portable Linux compute plane

After W3 recovery proof:

- `engine-render.yml` remains default `render-linux`;
- `render.yml` automatic/default route changes from `render-heavy` to `render-linux`;
- at least two distinct PC render listeners should be available so ordinary render and
  engine-render can overlap without returning to the M2;
- PC CI canary work stays optional; ordinary PR CI remains hosted.

No automatic fallback to M2 is authorized. Manual break-glass dispatch may retain a Mac
fallback while it is explicit and visible.

### 4.3 M1 Max — guarded Mac/store capacity

Return in two stages only:

**Stage A — diagnostic:** three existing guarded service identities online under the
existing canary labels, no production route change.

**Stage B — bounded production after soak:**

- exactly one general `macstudio` production slot may be restored first;
- the real store-bearing runner may regain `theta-m1` only after store presence and the
  existing probe-only laws are verified on that host;
- `codex` returns only if its host-local CLI/auth preflight is independently proven;
- a second M1 general-production slot is a later capacity decision, not implicit in
  restoring three listeners.

The M1 does **not** become the default full renderer in this freeze; the PC already has the
portable render contract and avoids moving long render I/O from one Mac to another.

### 4.4 M2 Ultra — authoritative production and break-glass Mac plane

Retains:

- authoritative nightly/general `macstudio` production capacity;
- `macstudio-light` live/light lanes until a separate measured migration;
- operator/session worktrees;
- explicit break-glass Mac render fallback only.

Retires from routine duty, after their respective gates:

- default `render-heavy` full render;
- `merge-control` arbiter.

Removing a label from the M2 is a host/API action only after no scheduled/default workflow
requires it. Never orphan a scheduled label to “force” migration.

---

## 5. Authority boundaries / no-rebuild law

1. `WS:CI-MERGE-CONTROL-PLANE` keeps semantic authority over `merge-on-green.yml` and
   `scripts/merge_on_green.py`. This fleet program commissions only the runner-environment
   cutover after W1 proof; it does not fork merge logic.
2. `docs/CI_SELFHOSTED_WAVE_BC_RUNBOOK.md` and `ops/runner-host/**` remain the canonical
   self-hosted safety substrate. Do not create another runner installer, cache authority,
   cleanup daemon, or canary protocol.
3. `.github/runner-policy.yml` stays the checked-in routing declaration. A future live
   health projection is observation, not a second mutable registry.
4. GitHub Actions remains the scheduler. No side queue or fleet database.
5. Ship-loop semantics are not changed by this program unless later evidence identifies a
   separate guard bug. The goal is to remove the infrastructure condition it is correctly
   reporting.

---

## 6. Execution waves

### M0 — architecture freeze and work identity — **this PR**

Observable capability: a cold session can distinguish runner-process count from physical
capacity, recover the exact target topology, and commission only the next bounded proof.

Files: Agent OS records + this research document only. No runner/workflow/runtime changes.

Acceptance:

- Agent OS validation and hosted CI/fences green;
- no open-PR path collision on these records;
- no production route or label changes;
- merge establishes the physical-host failure-domain law.

### W1 — hosted merge-control environment canary → cutover

**Mission:** remove PR merge arbitration from the M2 physical failure domain without
changing merge semantics.

Implementation sequence:

1. Add a dispatch-only hosted canary owned by `WS:CI-MERGE-CONTROL-PLANE` that uses the
   same sparse control-plane checkout/dependencies as `merge-on-green`, but has read-only
   permissions and runs environment/test proof rather than merge actions.
2. Run three canaries, including at least one during the nightly/render congestion window.
3. Require hosted runner pickup <60 seconds for each canary and successful sparse checkout,
   PyYAML import, and existing merge-control test suite.
4. In a second PR, change only the real sweeper runner route to `ubuntu-latest` and update
   runner-policy/tests/comments. Do not alter `merge_on_green.py` semantics.
5. Production proof: a real armed PR is merged by the hosted sweeper while the M2 is busy;
   workflow log identifies a GitHub-hosted runner; no extra merge latency >2 minutes after
   the decisive checks conclude, excluding GitHub event-delivery delay already measured by
   the workflow.
6. Rollback: revert the route to `merge-control`; no state migration exists.

**Stop condition:** any hosted canary waits >=60s, flakes on checkout, or lacks dependency
parity. Return to Sol with exact queue/runtime evidence; do not cut over.

### W2 — guarded M1 service restoration, diagnostic only

**Mission:** make all three intended M1 listener services live under the guarded service law
without changing production routing.

Host-side actions are expected and may require a bounded operator/Claude/Codex handoff.
Repository code should not be widened unless the existing guarded contract fails.

Acceptance from `m1-runner-canary.yml`:

- exact M1 hardware identity;
- disk guard healthy;
- three expected service/root/registration mappings;
- three distinct live listener PIDs;
- no historical `macstudio`, `theta-m1`, `codex`, `render-heavy`, or
  `macstudio-light` labels present during diagnostic acceptance;
- kill/restart one diagnostic listener and prove launchd recovers it;
- no ENOSPC/log-growth recurrence during a 12-hour idle/diagnostic soak.

**Stop condition:** guard refusal, listener identity collision, disk below policy floors, or
restart not recovered. No production labels added.

### W3 — PC render recovery + default-render cutover

**Mission:** make routine full render and engine-render execute on PC capacity instead of the
M2.

Acceptance before route change:

- at least two `render-linux` listeners live on the PC;
- one `engine-render` canary/real run completes on PC with cache/zstd parity;
- one scope=all `render.yml` dispatch completes on PC from committed data;
- rendered guard/push path succeeds and output is not truncated;
- PC resource receipt stays within proven memory/disk bounds.

Then change `render.yml` default to `render-linux`; keep explicit Mac fallback only for manual
operator dispatch. Update `.github/runner-policy.yml` from live proof.

Production proof: an automatic template/builder merge triggers `render.yml`, runner log names a
PC listener, and the M2 simultaneously accepts production work without render queueing on its
host.

### W4 — bounded M1 production capacity

**Mission:** add one physically independent Mac production slot after W2 acceptance.

First cut only:

- add `macstudio` to one guarded M1 production listener;
- restore `theta-m1` to the real store-bearing listener only after store probe;
- do not add `render-heavy`;
- do not add `codex` without its separate auth/runtime proof;
- keep the third M1 listener diagnostic/light-only.

Production proof requires at least one natural nightly job executing on the M1 while the M2
executes a sibling, with both completing and no disk-guard/resource breach. A second general M1
slot requires a later measured concurrency decision.

### W5 — remove obsolete M2 roles + live fleet health

After W1/W3/W4 are production-proven:

- remove the M2 `merge-control` role/listener if no rollback soak requires it;
- remove `render-heavy` from the automatic/default route and ultimately from the M2 registry;
- add a hosted, read-only live-fleet health projection if the existing admin token can lawfully
  list runners. It must report physical host, runner name, labels, online/busy and observed
  route health without becoming scheduler state.

Alert conditions include: required production capability zero-live; PC render pool zero-live;
M1 store capability orphaned; a long production/render job queued beyond a defined SLO; or a
label unexpectedly collapsing multiple critical roles onto one physical machine.

### W6 — nightly critical-path reduction

Only after allocation is stable. Reopen the measured Aug-13 compute plan:

- parallelize safe collector host groups;
- preserve per-host rate ceilings and file-write isolation;
- use W2 nightly timings as acceptance;
- split additional engine work only if the post-allocation critical path still warrants it.

This is throughput optimization, not a prerequisite for removing the shipping control-plane
failure domain.

---

## 7. Failure states

- **M1 canary queues forever:** host/registration is not restored; do not add production labels.
- **PC route queues:** `render-linux` is offline; automatic render remains on the last proven
  route until W3 accepts; do not pretend label existence is liveness.
- **Hosted control canary queues:** no cutover; measure current hosted saturation.
- **A route is live but slower:** compare queue wait separately from execution wall time; do not
  infer compute from GitHub run lifetime.
- **Host disk guard refuses:** listener stays offline by design; capacity is unavailable, not
  degraded-green.
- **Static runner policy disagrees with live proof:** live proof wins for incident diagnosis;
  update the checked-in declaration in the same bounded wave.
- **One machine carries multiple listener names:** counts as one physical failure domain in
  capacity/SLO calculations.

---

## 8. Measurement / learning

For every relevant job capture separately:

- workflow created_at;
- job started_at;
- queue wait = started_at - created_at/job-created boundary where available;
- execution wall;
- runner name;
- physical host identity;
- route label;
- outcome;
- host CPU/load/memory/swap/disk extrema for self-hosted canaries.

Primary program metrics:

1. p50 / p95 queue wait by **physical plane**, not runner name;
2. number of `SHIP LOOP BLOCKED` incidents attributable to pending self-hosted merge control;
3. check-conclusion → merge latency for armed PRs;
4. nightly/Asia jobs queued >5m and >15m;
5. M2 hours spent on routine render after W3 (target zero except break-glass);
6. physical hosts live at start of nightly window.

---

## 9. Exact next action

Merge M0 after records/CI review. Then commission **W1 only**: hosted merge-control environment
canary under the existing `WS:CI-MERGE-CONTROL-PLANE` authority. M1/PC host restoration may be
prepared in parallel as read-only/diagnostic work, but no production label or render-default
migration occurs before its wave acceptance.