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

The provider token is loaded only through:

```text
LoadCredential=massive-option-oi-api-key:/etc/macro-market-memory-options/massive-option-oi-api-key
```

The capture process reads the fixed file below `$CREDENTIALS_DIRECTORY`. It has
no application environment-variable fallback and accepts no key path/value on
argv. The prereq helper can rebind the already private VPS Massive/Polygon token
from `/opt/macro/.env` or `/etc/macro-api.env` into this process-specific,
root-owned mode-0400 credential source without logging it. This isolates process
access; it does not claim the underlying provider subscription key is unique to
this canary.

For an out-of-band rotation, update the canonical root-owned, group/world-dark
operator source (`/opt/macro/.env`, preferred, or `/etc/macro-api.env`) and let
the next updater tick replace the derived mode-0400 systemd credential. A manual
edit to the derived credential is intentionally overwritten while a valid
canonical source exists. Do not paste tokens into Git, issues, PRs, command
arguments, or journal messages.

The committed `research/licenses/MASSIVE_ENTITLEMENT_RECORD.md` is the reviewed
in-repo legal record for this private internal capture. It changes no evidence
or authority rule.

## Deployment behavior

`api-setup.sh` and every `macro-update` tick:

1. verify/create only the static identity needed for unit validation;
2. verify/install the API, service, and timer units;
3. restart `macro-api` into the non-optional option-root and credential-source
   deny namespace and seal a runtime fence marker only after its PID changes;
4. only behind that fence, provision the disjoint root and validate/rebind the
   fixed systemd credential source;
5. run once immediately when a credential and a new/changed contract are
   present; and
6. enable the weekday timer only while the units, credential, and API fence are
   all current.

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
