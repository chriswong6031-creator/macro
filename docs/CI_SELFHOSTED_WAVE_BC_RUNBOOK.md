# Self-hosted CI Wave B/C runbook

## Current posture

This wave keeps the repository public and leaves ordinary PR CI, `ci-plan`,
`ci-gate`, and every fence on GitHub-hosted runners. The only PC CI entry point is
the dispatch-only `infrastructure-selfhosted-ci-canary` workflow. The M1 entry point
is the no-checkout, no-secret `infrastructure-m1-runner-canary` workflow. Neither is
merge authority and neither publishes a required check name.

PR #5465 is measurement evidence, not a merge carrier. Its compute result remains
useful (6–14 minutes per pack on the PC versus 11–37 hosted), while its checkout
topology is explicitly retired: independent `blob:none` workspaces requested one
large missing pack from GitHub, hit the 37–77 minute transfer wall, and discarded the
truncated pack after `early EOF` / `invalid index-pack`.

## Pool topology

| Physical host | Slot | Required labels | Role |
|---|---|---|---|
| PC/WSL | `pc-ci-1` | `self-hosted,ci-linux-canary`; add `ci-linux` only after one-slot acceptance | initial CI canary |
| PC/WSL | `pc-ci-2..3` | disabled/pending during one-slot; `self-hosted,ci-linux` after acceptance | bounded CI capacity |
| PC/WSL | `pc-ci-4` | **not registered.** Code-pending only; see "Fourth slot" below | pending capacity |
| PC/WSL | `pc-render-1` | `self-hosted,Linux,X64,render-linux` | render-reserved; never gets a CI label |
| M1 Max | `m1-nightly-1` | `self-hosted,m1-nightly` | diagnostic-only in this wave |
| M1 Max | `m1-nightly-2` | `self-hosted,m1-theta` | no-op M1 canary |
| M1 Max | `m1-light-1` | `self-hosted,m1-light` | diagnostic-only in this wave |

The M1 registrations intentionally omit the old `macstudio`, `theta-m1`, `codex`,
`render-heavy`, and `macstudio-light` labels. Returning the listeners online therefore
cannot change any existing production route.

## PC shared-object checkout

The root-owned bare cache is `/var/cache/mastermind-ci/macro.git`. Its initial object
estate is peer-seeded from the M2 Macro object database over Tailscale; no working
tree or uncommitted state is copied. Before seeding, the source was proven to contain
all 68,481 blobs in the current `origin/main` tree with lazy fetching disabled.

The cache owner is `root`; the `macroci-cache-readers` group has read/traverse only.
CI users cannot mutate it. `/usr/local/libexec/mastermind-ci-cache-update` serializes
the only mutation with `flock`, advances only `refs/heads/main`, runs a connectivity
check, and never prunes, repacks, or runs GC during migration.

The peer source was a partial clone, so the cache is shallow-bound at the audited
bootstrap main commit. Integrity checks enumerate and verify every object reachable
from that maintained shallow `main`; they do not claim that unreachable historical
promisor fragments form complete history. Full current-tree checkout with lazy fetch
disabled is the materialization acceptance boundary.

Before candidate materialization, the root-owned prewarm program:

1. validates the cache owner, modes, identity marker, bare-repository state, origin,
   and frozen base commit/tree;
2. refuses with exit 66 if any of those checks fail;
3. writes only the runner workspace's `objects/info/alternates`;
4. creates `refs/cache/main`, so fetch negotiation advertises the local base;
5. materializes the frozen base locally with lazy fetching disabled; and
6. hands the prepared repository to a credential-free, filtered fetch of the exact
   immutable candidate SHA using normal Git negotiation; the job then detaches that
   SHA and asserts `HEAD` exactly.

There is no direct-origin fallback. The live negative-control job passes an absent
cache and requires exit 66 before `.git` exists.

## PC isolation and refusal

The CI runner account has no login shell and no sudo. Its systemd units have no
capabilities, enable `NoNewPrivileges`, use a read-only system view and private `/tmp`,
hide `/mnt/c`, `/mnt/d`, `/home/longr`, and `/root`, and expose the shared cache
read-only. The runner application/configuration root is also read-only to a job; only
that slot's `_work` and `_diag` are writable, preventing candidate code from replacing
the next listener. The runner is registered with updates disabled because binaries
are sealed and updated only by the host operator.

The runtime admission boundary is the organization-owned `macro-home-canary` runner
group. GitHub restricts that group server-side to this public repository and exact
workflow paths pinned to `refs/heads/main`; a pull-request workflow version cannot
request the group. PC CI accepts only the main-defined `selfhosted-ci-canary.yml`, M1
accepts only the main-defined no-op canary, and the render listener accepts only the
two main render workflows. Repository lint and the host start hook are independent
defense-in-depth checks, not substitutes for that server-side boundary.

The start hook performs admission only and never mutates the workspace GitHub has
already prepared. Each PC CI listener uses the runner's one-job `--once` mode. After
the job and all post-actions finish, the listener exits; systemd tears down the whole
service cgroup, including an intentionally abandoned child, then starts a fresh
listener. The wrapper scrubs every entry under that slot's `_work`, recreates empty
private `_temp` and HOME directories, and clears the unit's private `/tmp`/`/var/tmp`
before the listener can accept another job. This also recovers a killed or crashed
job. `_diag` remains writable for runner diagnostics and is outside the candidate-state
cleanliness claim. The design trades action/tool cache warmth for a clean next-job
boundary; Git objects remain fast because the shared alternate is outside candidate
write authority.

The pre-start resource guard keeps the listener offline at 85% disk use or below
100 GiB free, below 4 GiB available memory, or under combined high swap/low-memory
pressure. A refusal waits five minutes before returning to systemd, bounding an
unsafe-host retry loop without rate-limiting normal one-job listener turnover. It
never kills unrelated Windows/GPU work.

WSL was measured at 24 logical CPUs and about 31 GiB despite 64 GiB physical RAM.
The Wave B candidate is 44 GiB / 16 CPUs / 8 GiB swap: 44 rather than 48 GiB leaves
20 GiB physical headroom because the live Windows census found substantial non-WSL
resident services. Apply only after all Actions jobs drain, then prove mounts,
Tailscale, storage, render, and runner recovery.

## M1 service and disk law

Each owner LaunchAgent has `RunAtLoad=true`, `KeepAlive.SuccessfulExit=false`, and a
60-second throttle. The guarded launcher executes `Runner.Listener` directly, so a
listener death becomes a launchd state transition instead of being hidden inside the
runner's nested Node supervisor.

This proves crash recovery inside the active GUI session. It does not prove unattended
reboot recovery: FileVault is off, but automatic login is unset and the current user
cannot install root LaunchDaemons non-interactively. Administrator installation of the
same guarded listener definitions as LaunchDaemons remains an explicit host action.

The guard reports free bytes, percentage, inodes, `_work`, `_temp`, and `_diag`.
Warnings start at 70% used, critical at 80%, full/data-heavy work is refused at 85%
or below 200 GiB free, and emergency refusal starts at 90% or below 100 GiB free.
A narrow no-op listener may remain online between the full-work and emergency floors;
no production label can route to it.

Inactive diagnostics are compressed after one day. Normal logs retain 14 days,
incident-bearing logs retain 30, and normal archives yield first at the roughly 1 GiB
soft cap. The sole ENOSPC evidence was copied to the owner-only recovery backup before
maintenance.

## Dispatch and acceptance

One-slot parity:

```bash
gh workflow run selfhosted-ci-canary.yml --ref main \
  -f pr_number=<same-repository-open-pr> -f slots=1
```

The hosted planner resolves and freezes the exact GitHub PR merge ref, base SHA,
changed-file handle, plan hash, and the currently heaviest non-empty pack. Hosted and
self-hosted jobs run the same candidate tree, logical job list, dependency contract,
and pack script. The comparison accepts red/red only when the failure sets agree; it
does not require a semantically green candidate.

One-slot acceptance requires:

- exact tested SHA and plan hash agreement;
- executed logical set and failed set parity;
- no early EOF, invalid index-pack, or promisor failure;
- bounded local prewarm and small origin fetch;
- cache byte count unchanged by the job;
- cache-disabled refusal before checkout; and
- a second different exact tree on the same sole canary listener with clean status,
  no sentinel, lock, monitor process, Windows-home visibility, or cache write access.

After that proof only, label/start all three CI slots and dispatch with `slots=3`.
The three currently heaviest packs execute concurrently while the read-only
`render-reservation-probe` must independently acquire `pc-render-1`. Resource JSONL is
reduced to CPU, load, memory, swap, and disk extrema; raw packet traces are never
published.

M1 service acceptance is dispatched separately:

```bash
gh workflow run m1-runner-canary.yml --ref main
```

It reports only runner name, hostname, architecture, OS, CPU count, memory, disk,
runner root, disk-guard status, and the three exact service-to-root-to-registration
mappings with distinct live listener PIDs. It performs no checkout, reads no secret,
and publishes nothing.

## Fourth slot and the aggregate CI resource envelope

Capability state: **`FOURTH_SLOT_CODE_SUBSTRATE = BUILT_NOT_HOST_PROVEN`.**

Read that literally. The repository now contains everything needed to run four PC
CI candidates inside one enforced envelope, and **none** of it is installed. There
is no `pc-ci-4` registration, no `/opt/mastermind-ci/runner-4` on disk, no
`mastermind-ci.slice` unit on the host, and no fourth listener. Live capacity is
still exactly three slots, production trusted execution is still `max-parallel: 3`,
and `ci-linux` is still carried by exactly `pc-ci-1..3`.

### What "pending" means in policy

`.github/runner-policy.yml` splits live inventory from pending architecture:

```yaml
pool_topology:
  pc-ci:
    slots: 3                      # live and routable
    pending_slots: 1              # architecture only
    pending_carriers: [pc-ci-4]
    pending_labels: [self-hosted, Linux, X64]
```

Rule **R14** in `scripts/check_runner_policy.py` enforces the split and fails CI on
every way it could quietly collapse: a fifth slot, an invented carrier name, a
pending block on any other pool, a pending label outside platform identity (so
`ci-linux` cannot be pre-declared), and — the activation act itself — `pc-ci-4`
appearing in any `carried_by` roster. `pending_labels` deliberately omits `ci-linux`
so the fourth runner can be bootstrapped **online but unroutable**.

### The envelope

`ops/runner-host/pc/mastermind-ci.slice.template`:

| Directive | Value | Meaning |
|---|---|---|
| `CPUQuota` | `800%` | eight vCPU-equivalents of the 16-vCPU guest |
| `CPUQuotaPeriodSec` | `100ms` | enforcement granularity |
| `MemoryHigh` | `10G` | reclaim/throttle threshold — shows up as PSI, not as a kill |
| `MemoryMax` | `12G` | hard ceiling of the 44-GiB guest |
| `MemorySwapMax` | `2G` | swap ceiling |

`AllowedCPUs`, `CPUWeight`, `IOWeight` and `TasksMax` are deliberately unset in this
wave; their counters are receipted so a later carrier can set them from evidence.
**Changing any frozen value above requires a new measured carrier, not an edit.**
The WSL guest allocation (16 CPU / 44 GiB / 8 GiB swap) is unchanged by this wave.

### Render is outside the slice

This is the property the whole design exists to preserve. `pc-render-1` and every
remote render roster entry keep their own service, labels, cgroup and resource
semantics. The slice sets no `KillMode`, so CI's `KillMode=control-group` cannot
leak onto a render unit. `tests/test_ci_canary_tools.py` proves from source that
`actions-runner-ci.service.template` is the *only* checked-in unit carrying
`Slice=mastermind-ci.slice`, and the canary's `render-reservation-probe` runs for
both `slots=3` and `slots=4` so a four-wide run must still show the renderer
independently routable.

### Evidence, and what refuses

`scripts/monitor_ci_host_resources.py` derives each candidate's own cgroup from
`/proc/self/cgroup` and binds it to `/mastermind-ci.slice/<unit>.service` by exact
path component. A candidate in `system.slice`, in a look-alike slice, or with
unreadable files yields `refused`/`degraded` **with no metric values at all**. It
never substitutes host-global numbers for slice numbers, because a green produced
from the wrong cgroup reads downstream as proof. `slice_metrics()` in
`scripts/capture_ci_canary_receipt.py` reports aggregate numbers only when every
sample in the window was cleanly bound. Absent kernel fields stay `null` and are
never collapsed to `0`; `memory.peak` is reported as
`memory_peak_bytes_cgroup_lifetime` because it is a cgroup-lifetime high-water mark,
not a run-local peak.

Guard thresholds are versioned separately from the slice ceilings
(`mastermind.ci_resource_guard_thresholds.v1`) so retuning a refusal threshold never
reads as a change to the measured envelope. `--preflight-profile four-slot-canary`
adds the stricter pre-diagnostic gate: `MemAvailable >= 20 GiB`, swap `<= 512 MiB`,
memory/IO PSI `full avg10 < 0.10`. Steady state for `pc-ci-1..3` is unchanged.

The memory floor stays a **guest-wide** `MemAvailable` read on purpose: the renderer
lives outside the slice, so a slice-local read would show a nearly idle cgroup while
the guest was starved, and would admit a CI job that then starves render.

Note the cumulative-vs-delta distinction, which is a real trap: `memory.events`
counters are cumulative over the slice lifetime, and `high` counts `MemoryHigh`
reclaim working as designed. The prestart guard therefore refuses only on real kills
(`max`/`oom`/`oom_kill`). Refusing on cumulative `high` would mean that once CI ever
touched 10G, **every** later listener start refuses forever and the slot is stranded
permanently. The plan's "zero `high`/`max`/`oom`/`oom_kill` delta" is an acceptance
criterion over one run window, and is the receipt reducer's job, not the gate's.

### The security-sensitive stop

Installation is **not** in this carrier and must not be performed from an unmerged
branch. The first security-sensitive act is the organization runner registration and
group membership for `pc-ci-4`, which requires explicit Chairman/Sol confirmation.
Never request, paste, print or store a registration token in a PR, issue, receipt,
terminal transcript or chat; the operator performs any native authorization ceremony.

The later host carrier installs `/etc/systemd/system/mastermind-ci.slice`, replaces
the `pc-ci-1..3` units from their exact pre-change snapshot at a natural drain,
creates the sealed `/opt/mastermind-ci/runner-4` root, and registers `pc-ci-4` with
platform/architecture labels **only** — no `ci-linux` — so roster, service, PID, root
and cgroup can be proved online but unroutable. Adding `ci-linux` and moving the live
inventory to four is one separately audited activation act gated on GitHub reporting
the exact runner online/idle. Only after that is accepted may a further carrier
change trusted-executor `max-parallel` from 3 to 4.

### Rollback for this code carrier

Nothing to roll back on any host: this carrier installs nothing. Reverting the
commits restores the three-slot policy declaration, the `slots=1|3` canary input,
the host-global-only monitor, and the three-root cleanup allowlist. Because
`pc-ci-4` was never registered and the slice was never installed, no runner, unit,
cgroup, cache, credential or render lane is touched by the revert either.

## Rollback

- Stop/disable `pc-ci-*`; the old `pc-render-2..4` roots and owner-only service/config
  backups remain intact during this wave.
- Remove `ci-linux` from all registrations; `pc-render-1` remains the independent
  render lane.
- Disable the cache-update timer; the cache is disposable acceleration, never source
  of truth.
- On M1, boot out the new LaunchAgents and restore the owner-only plist/config backup.
  Existing production workflows remain on M2 because no production label changes in
  this wave.
- Select no self-hosted diagnostic route: ordinary CI already remains hosted, so no
  workflow rollback is required to keep merging safely.

Do not start Wave D/E/F/G from this runbook. Capacity soak, default trusted-CI
migration, M1 production migration, and private-repository cutover require separate
evidence and authorization gates.
