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

Before `actions/checkout`, the root-owned prewarm program:

1. validates the cache owner, modes, identity marker, bare-repository state, origin,
   and frozen base commit/tree;
2. refuses with exit 66 if any of those checks fail;
3. writes only the runner workspace's `objects/info/alternates`;
4. creates `refs/cache/main`, so fetch negotiation advertises the local base;
5. materializes the frozen base locally with lazy fetching disabled; and
6. hands the prepared repository to `actions/checkout@v4` for the exact candidate
   ref.

There is no direct-origin fallback. The live negative-control job passes an absent
cache and requires exit 66 before `.git` exists.

## PC isolation and refusal

The CI runner account has no login shell and no sudo. Its systemd units have no
capabilities, enable `NoNewPrivileges`, use a read-only system view and private `/tmp`,
hide `/mnt/c`, `/mnt/d`, `/home/longr`, and `/root`, and expose the shared cache
read-only. The only writable paths are that runner's root and `/var/lib/macroci`.

The pre-start resource guard refuses a job at 85% disk use or below 100 GiB free,
below 4 GiB available memory, or under combined high swap/low-memory pressure. It
fails the candidate job; it never kills unrelated Windows/GPU work.

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
runner root, disk-guard status, and listener count. It performs no checkout, reads no
secret, and publishes nothing.

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
