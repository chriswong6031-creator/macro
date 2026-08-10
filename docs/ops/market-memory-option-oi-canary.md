# Market Memory option-OI availability canary

## Scope

W1B.5 is a private, future-only source-availability probe. It performs exactly
one credentialed request for the first bounded SPY option-chain page:

```text
GET https://api.massive.com/v3/snapshot/options/SPY?limit=250
```

It stores the exact response body and its reviewed config/license inputs under
`/var/lib/macro-market-memory-options/options-v1`. The body may contain vendor
tickers, OI values, and a continuation URL; those bytes remain private. The
typed projection exposes only page/OI-presence counts and whether a continuation
was present.

This lane does **not** follow pagination or claim a complete or atomic chain. It
does not infer a measurement date/session from a calendar or capture clock,
interpret omitted contracts as zero, normalize OCC identity, assume a contract
multiplier, compute totals/GEX, feed replay or options episodes, train a model,
or grant rank/gate/size/trade authority. `available_at` is only the response-body
completion clock; the private store seals a distinct `first_observed_at` after
bundle validation and never resamples it on crash recovery or idempotent retry.

## Isolation and credential

The oneshot runs as the static, non-login
`macro-market-memory-options` identity. Its private root is deliberately outside
the existing root-owned `/var/lib/macro-market-memory` tree. The parent is
`root:macro-market-memory-options` mode `0710` so the service cannot replace its
profile with a symlink; only `options-v1` is service-owned mode `0700`. Both
families deny each other in their systemd mount namespaces. `macro-api` also has
a non-optional deny mount for the option root and exposes no option-OI route.
Because the legacy API still runs as root, these deny mounts prevent accidental
pathname access inside the shared host trust domain; they are not represented
as a containment boundary against a compromised root API. Moving that API to a
dedicated unprivileged identity remains separate platform hardening.

The provider token is loaded only through:

```text
LoadCredential=massive-option-oi-api-key:/etc/macro-market-memory-options/massive-option-oi-api-key
```

The capture process reads the fixed file below `$CREDENTIALS_DIRECTORY`. It has
no application environment-variable fallback and accepts no key path/value on
argv. The prereq helper can rebind the already private VPS Massive/Polygon token
from `/opt/macro/.env`, `/etc/macro-api.env`, or the existing root-private
`/etc/macro-live.env` into this process-specific, root-owned mode-0400
credential source without logging it. This isolates process
access; it does not claim the underlying provider subscription key is unique to
this canary.

For an out-of-band rotation, update the canonical root-owned, group/world-dark
operator source (`/opt/macro/.env`, then `/etc/macro-api.env`, then
`/etc/macro-live.env` in precedence order) and let the next updater tick replace
the derived mode-0400 systemd credential. A manual
edit to the derived credential is intentionally overwritten while a valid
canonical source exists. If none of the canonical sources contains a valid
private token, the helper removes the derived file and disarms the lane rather
than silently retaining stale credential state. Do not paste tokens into Git, issues,
PRs, command arguments, or journal messages.

The committed `research/licenses/MASSIVE_ENTITLEMENT_RECORD.md` is the reviewed
in-repo legal record for this private internal capture. It changes no evidence
or authority rule.

## Deployment behavior

`api-setup.sh` and `macro-update` reconcile the lane as follows:

1. manual setup disarms immediately; the frequent updater first performs a
   read-only preflight, leaves a healthy active timer untouched, and disarms
   before any required identity, unit, API, credential, or state mutation;
2. verify/create the static identity and empty root-owned deny anchors needed
   for unit validation, without creating `options-v1` or a credential file;
3. verify/install the API, service, and timer units;
   migrate the one byte-exact reviewed legacy API Ollama drop-in into the
   canonical API unit, while rejecting any unknown override or metadata drift;
4. restart `macro-api` into the non-optional option-root and credential-source
   deny namespace and seal its exact MainPID plus systemd InvocationID in a
   runtime receipt only after both effective units and the reciprocal writers
   are re-attested;
5. only behind that fence, provision the disjoint root and validate/rebind the
   fixed systemd credential source;
6. run once immediately when a credential and a new/changed contract are
   present; and
7. re-enable the weekday timer only while the exact loaded units (including all
   five reciprocal writers), credential, and API fence are current. Any fatal
   exit after option reconciliation or an option-related mutation begins
   disarms it; an earlier fetch/preflight failure leaves an otherwise healthy
   timer untouched.

Both the timer and oneshot require the API and reciprocal runtime receipts, and
the oneshot's `ExecCondition` rechecks their ownership, exact loaded fragments,
absence of drop-ins, current API MainPID, and current InvocationID before every
credentialed request. Because `/run` is cleared on reboot, an enabled timer
remains unable to start until an updater has restarted and re-attested the API
deny namespace. A healthy three-minute no-op updater does not stop or restart
the active nonpersistent timer, so it cannot erase that day's randomized
calendar firing.

The first rollout has an explicit predecessor bridge: the old updater already
invokes the newly checked-out `codex-runtime-setup.sh` before it installs the
new API unit, and that helper creates only the empty deny anchors while no
option unit exists. Operators must still preflight those two paths before merge;
if either is unsafe, use a two-phase rollout instead of allowing the old updater
to attempt the nonoptional mounts.

Without a credential, the root and reviewed units are still installed so all
non-optional deny mounts remain closed, but the timer is disabled. No request or
empty receipt is emitted.

The weekday 08:20 America/New_York timer is an operational retry cadence only.
It is not provider measurement, publication, session, or freshness evidence,
and `Persistent=false` forbids catch-up/backfill semantics.

## Read-only verification

```bash
systemctl status macro-market-memory-options.service --no-pager
systemctl status macro-market-memory-options.timer --no-pager
journalctl -u macro-market-memory-options.service -n 50 --no-pager
sudo stat -c '%U:%G %a %n' \
  /var/lib/macro-market-memory-options \
  /var/lib/macro-market-memory-options/options-v1
sudo find /var/lib/macro-market-memory-options/options-v1 \
  -maxdepth 2 -type f -printf '%m %p\n' | sort
```

A process starts by scanning bounded prepared records and resumes any fully
durable pending capture from private CAS before opening the credential or making
a request. A successful recovery or idempotent retry returns the same capture,
sealed first-observation clock, and generation and does not rewrite `HEAD.json`.
Any transport, credential, Git pin, schema, raw-byte, tamper, permission, or
partial-write failure exits nonzero and leaves the prior active generation
intact.

The raw CAS and receipts are private evidence. Never copy them into `site/`, the
API-readable Market Memory tree, logs, CI artifacts, or support messages.
