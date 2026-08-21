---
key: RUNNER-FLEET-W2-W3-DIAGNOSTIC-HANDOFF-2026-08-20
program: project-active-build-control
workstream: RUNNER-FLEET-RESILIENCE
owner: ceo-sol
status: ready_for_operator_diagnostics
class: operator_handoff
reversible: true
---

# Runner Fleet W2/W3 Diagnostic Operator Handoff — 2026-08-20

## Observable mission

Produce fresh physical-host receipts for two owned-capacity domains without changing any production route:

1. **W2 / M1 Max:** restore exactly the three existing guarded diagnostic listeners and prove disk safety, registration/root identity, no-op canary execution, one-listener crash recovery, and a 12-hour active-GUI-session soak.
2. **W3 / PC/WSL:** prove current render-fleet state from host + GitHub job evidence, reconcile the stale runner registry, require at least two distinct live `render-linux` listeners, then prove one real `engine-render` and one real `render scope=all` on the PC.

Diagnostics are authorized now because M0 is merged. This handoff does **not** authorize production labels on M1, generic `macstudio` on M1, merge-control cutover, default-render cutover, or hardware purchase.

## Why it matters

The 2026-08-20 incident proved the M2 Ultra is one physical failure domain despite multiple logical runner labels. It carried production/nightly work, default full render, merge control and operator I/O. Historical audits show useful M1 and PC capacity, but current liveness is not trustworthy enough for production routing. The job here is to turn historical capacity into current timestamped receipts before any cutover.

## Authority / precedence

1. `agentos/decisions/DEC-RUNNER-FLEET-PHYSICAL-FAILURE-DOMAINS.md`
2. `research/RUNNER_FLEET_RESILIENCE_ARCHITECTURE_FREEZE_2026-08-20.md`
3. `research/RUNNER_FLEET_RESILIENCE_M0_ADVERSARIAL_AMENDMENT_2026-08-20.md`
4. `docs/CI_SELFHOSTED_WAVE_BC_RUNBOOK.md`
5. `agentos/workstreams/WS-RUNNER-FLEET-RESILIENCE.md`
6. this handoff

The architecture freeze is later/higher authority than older topology commentary where they disagree. In particular, W3 default-render admission requires **at least two live `render-linux` listeners**, even though the older Wave B/C runbook describes one reserved `pc-render-1` slot.

## Verified current state

- M0 #6094 merged as `9dcd4c24a547c11d1205b94da98ae0ff5b401b85`.
- W1-A #6113 merged as `29d52200af45d2a8afe44e8bdf8a29aacc63809c`; it does not change M1/PC routes.
- Current static runner policy is not a liveness authority. It contains known drift between `pc-render.slots` and old `render-linux` carrier declarations.
- Current GitHub connection exposes neither runner-admin inventory nor physical-host process/service state; host receipts are therefore required.

### M1 known diagnostic substrate

Existing main assets:

- `.github/workflows/m1-runner-canary.yml`
- `ops/runner-host/m1/run_guarded_runner.sh`
- `ops/runner-host/m1/runner_disk_guard.py`
- `ops/runner-host/m1/runner_log_maintenance.py`
- `ops/runner-host/m1/actions-runner.plist.template`

Exact intended diagnostic registrations:

| Registration | Runner root | Diagnostic label |
|---|---|---|
| `m1-nightly-1` | `/Users/chriswong/actions-runner-1` | `m1-nightly` |
| `m1-nightly-2` | `/Users/chriswong/actions-runner-2` | `m1-theta` |
| `m1-light-1` | `/Users/chriswong/actions-runner-3` | `m1-light` |

Forbidden during W2: `macstudio`, `theta-m1`, `codex`, `render-heavy`, `macstudio-light`.

Historical incident: the three M1 services stopped after `No space left on device`; disk later recovered, but service recovery was not proven. Current LaunchAgent design proves crash recovery only while the user GUI session is active. **Unattended reboot recovery remains NOT_PROVEN** unless a separate root LaunchDaemon installation/reboot proof is explicitly authorized later.

### PC known historical substrate

Historical roots:

| Registration | Root |
|---|---|
| `pc-render-1` | `/home/longr/actions-runner` |
| `pc-render-2` | `/home/longr/actions-runner-2` |
| `pc-render-3` | `/home/longr/actions-runner-3` |
| `pc-render-4` | `/home/longr/actions-runner-4` |

Historical Aug-14/15 host: Intel Core Ultra 9 285K, 24 logical CPUs, WSL about 31 GiB RAM, ample ext4 space. A later static registry marked PC entries offline. Historical state is not current liveness.

Workflow posture on main:

- `engine-render.yml` targets `render-linux` by default with M2 fallback available.
- `render.yml` still defaults to `render-heavy` on M2; `render-linux` is an explicit operator route only.
- **No default change is authorized in this handoff.**

## Exact scope

### W2 in scope

- read-only host/process/disk/service/`.runner` identity census;
- restore exactly the three existing diagnostic-only M1 services using the existing guarded launcher/plist substrate;
- dispatch the no-op `m1-runner-canary.yml` from `main`;
- prove three distinct listener PIDs/roots/registrations;
- terminate exactly one listener process and prove launchd restores a different PID under the same registration/root;
- 12-hour diagnostic soak and resource/log evidence.

### W3 in scope

- read-only PC/WSL CPU/RAM/swap/disk/process/service/root/registration census;
- query GitHub runner registry if operator credentials permit; otherwise explicitly record lack of registry read authority;
- restore only existing PC runner services/roots if they are down; no fifth runner and no label redesign;
- require at least two distinct live PC listeners eligible for `render-linux`;
- explicitly dispatch one `engine-render` on `render-linux`;
- after that passes, explicitly dispatch one `render scope=all` on `render-linux`;
- collect job runner identity, timings, conclusion, checkout/cache/bootstrap/publication evidence;
- if naturally available, capture M2 production execution overlapping a PC render to prove physical-failure-domain separation.

## Explicit non-goals

Do not:

- add any generic `macstudio` label to M1;
- restore M1 production `theta-m1` or `codex` authority in this wave;
- route render-heavy/macstudio-light to M1;
- change `render.yml` default;
- change `merge-on-green` route or semantics;
- migrate PC to `ci-linux`;
- create new runner roots/count beyond known registrations;
- change WSL memory unless separately authorized after the census;
- buy hardware;
- call M1 unattended-reboot-safe;
- continue from diagnostics into a production cutover without Sol review.

# W2 — M1 diagnostic journey

## W2.1 Read-only preflight

Run on the M1 before starting services:

```bash
set -euo pipefail
hostname
sw_vers
uname -m
sysctl -n hw.ncpu
sysctl -n hw.memsize
df -h /
df -hi /
pgrep -af 'Runner.Listener|Runner.Worker' || true
launchctl list | grep -E 'm1-nightly|m1-light|actions.runner' || true
```

For each known runner root, inspect `.runner` and capture at least `agentName` and work folder. Stop if a root carries a stale/colliding `mac-builder-*` identity or any forbidden production label.

Run the existing M1 disk guard in observation mode. The runbook safety law remains authoritative: warnings around 70%, critical around 80%, data-heavy refusal at 85% or <200 GiB, emergency around 90% or <100 GiB. A guard refusal is a valid stop condition—do not bypass it to obtain a green canary.

## W2.2 Guarded restoration

Use only the existing `ops/runner-host/m1/` launcher/plist design. Preserve:

- direct `Runner.Listener` execution behind guard/log maintenance;
- `RunAtLoad=true`;
- `KeepAlive.SuccessfulExit=false`;
- 60-second restart throttle;
- exact root per registration;
- diagnostic labels only.

Do not invent cron loops, a second supervisor, or generic wrapper.

After restoration, capture `launchctl print`/service evidence and one distinct live `Runner.Listener` PID per registration. Prove there are three distinct PIDs and three intended roots.

## W2.3 No-op production-path canary

```bash
gh workflow run m1-runner-canary.yml \
  --repo mastermindx-market-intelligence/macro \
  --ref main
```

Capture the exact run/job ID and relevant log receipt. Acceptance requires:

- hosted trust gate green;
- M1 job green;
- all three expected service → root → registration mappings;
- three distinct live listener PIDs;
- disk guard green;
- no checkout, secret read, or publication behavior.

## W2.4 Crash-recovery proof

Choose exactly one diagnostic listener. Record PID, terminate that listener process without changing its plist/config, and prove launchd creates a **different** live `Runner.Listener` PID for the same service/root/registration after the configured throttle. Do not kill all three at once.

## W2.5 12-hour soak

Capture start/end timestamps and enough local evidence to prove:

- no ENOSPC recurrence;
- no disk-guard refusal;
- no runaway `_diag`, `_work` or `_temp` growth;
- no identity collision;
- no repeated crash/restart loop.

This proves guarded reliability inside the active GUI session only.

## W2 stop conditions

Stop immediately if:

- disk guard refuses service;
- disk/inode floor violates runbook law;
- registration/root identity is wrong;
- services collide on PID/root;
- crash-recovery proof fails;
- a listener carries a forbidden production label;
- the canary touches checkout/secrets/publication unexpectedly;
- ENOSPC recurs.

## W2 required receipt

Return:

- host identity, CPU/RAM/disk/inode snapshot;
- exact registrations, labels, roots, service identifiers and live PIDs;
- GitHub runner IDs if visible;
- disk-guard output;
- canary run ID/conclusion/key log lines;
- killed PID → recovered PID evidence;
- soak start/end + resource/log findings;
- explicit `unattended_reboot_recovery = NOT_PROVEN` unless separately proven.

# W3 — PC render liveness and real-run proof

## W3.1 Read-only host census

On PC/WSL:

```bash
set -euo pipefail
hostname
uname -a
nproc
free -h
df -h /
pgrep -af 'Runner.Listener|Runner.Worker' || true
systemctl --type=service --all | grep -E 'actions.runner|pc-render' || true
```

Inspect `.runner` in all four historical roots. Map each root to `agentName`, work folder, service unit, listener PID, and labels. Do not infer physical identity from name alone.

If credentials allow runner registry reads, capture online/busy/labels for every `pc-render-*`. If not, record that limitation; host PID + subsequent job `runner_name` receipts become mandatory.

## W3.2 Admission gate

Before real render dispatches require:

- at least **two distinct live PC listeners** eligible for `render-linux`;
- distinct roots and PIDs;
- `pc-render-1` identity reconciled because it is the canonical reserved render root in the older runbook;
- no need to change workflow routes/labels to make them eligible.

If fewer than two are live, repair only existing registrations/services/roots. Do not create a fifth listener, add `ci-linux`, or change workflows.

The observed live map wins for liveness. Any static registry disagreement is preserved as a W5 correction item rather than averaged away.

## W3.3 Engine-render proof

Only after W3.2 passes:

```bash
gh workflow run engine-render.yml \
  --repo mastermindx-market-intelligence/macro \
  --ref main \
  -f scope=all \
  -f force_recompute=false \
  -f runner=render-linux
```

Capture exact run/job IDs. Acceptance requires:

- actual PC `render-linux` runner identity in job metadata/logs;
- expected Linux/x64 environment;
- checkout/cache/zstd/bootstrap contracts complete without early EOF, invalid index-pack, promisor or missing-tool semantic fallback;
- engine/render guards complete;
- publication remains within current workflow semantics;
- no hidden fallback to M2.

## W3.4 Full render proof

After the engine-render proof is accepted:

```bash
gh workflow run render.yml \
  --repo mastermindx-market-intelligence/macro \
  --ref main \
  -f scope=all \
  -f runner=render-linux
```

Capture run/job/runner identity, wall time, conclusion and publication/push receipt. This explicit route is allowed by the current workflow; it is **not** a default cutover.

## W3.5 Physical-failure-domain proof

If naturally available during an accepted PC render, capture a normal M2 production/nightly job executing concurrently. Prove overlap from runner identity + timestamps. Do not manufacture production load just for this proof.

## W3 stop conditions

Stop and do not propose default cutover if:

- fewer than two eligible distinct listeners are live;
- `pc-render-1` identity cannot be reconciled;
- `render-linux` job queues despite apparently live listeners;
- job lands on an unexpected physical host/registration;
- checkout/cache/zstd/bootstrap/publication fails;
- WSL memory/swap posture becomes unsafe;
- completing the render requires a label/route change;
- publication semantics differ from current contract;
- evidence depends only on stale static registry.

## W3 required receipt

Return:

- PC CPU/RAM/swap/disk snapshot;
- current `pc-render-*` registrations, labels, roots, service units and PIDs;
- GitHub registry snapshot if available;
- engine-render run/job ID, runner identity, timestamps, conclusion and key checkout/cache/publication evidence;
- full-render run/job ID, runner identity, timestamps, conclusion and publication evidence;
- M2 concurrency evidence if observed;
- resource maxima / instability / warnings;
- exact registry contradictions requiring W5 correction.

## Deterministic vs observed claims

Deterministic: workflow YAML, service/root/label contracts, disk thresholds, forbidden routes, acceptance/stop rules.

Observed: liveness, online/busy state, PID/service health, queue delay, wall time, resource pressure, restart behavior, publication success. Every observed claim requires timestamped evidence; no LLM judgment substitutes for host/job receipts.

## Failure/correction behavior

Preserve contradictory receipts rather than smoothing them over. A failed observation marks the corresponding capability `BROKEN` or `BUILT_NOT_PROVEN` and stops that wave. Live timestamped process/job evidence wins over stale static documentation for liveness; documentation drift is corrected later under W5.

## Stop condition

This handoff is complete when either:

1. W2 and W3 return the required diagnostic receipts; or
2. a stop condition fires and the exact failure receipt is returned.

Do not continue into production routing.

## Required continuation handoff

Return a compact packet containing:

- commands actually executed;
- before/after service/runner maps;
- all workflow run IDs;
- exact failures/warnings/timestamps;
- what changed on each physical host, if anything;
- rollback performed or still available;
- the single next action recommended.

Sol retains authority for W1-B merge-control cutover, W3 default-render cutover, W4 M1 production capability selection, and W5 live fleet health/retirement.
