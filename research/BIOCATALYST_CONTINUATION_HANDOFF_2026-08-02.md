# BioCatalyst continuation handoff — B4E activation control

Canonical continuation note for the B4E release. Deployment of these controls
does not itself activate a collector, create live evidence, or authorize
prospective accrual. Keep the clean-room rule: use public or properly licensed
source material only; never use, retain, or transmit competitor credentials.

## What this release provides

B4E replaces the prospective lane's former
`BIOCATALYST_R2_RETENTION_CONFIRMED=1` authority with a root-sealed activation
gate plus a fresh root-written heartbeat. The old boolean is accepted only as
deprecated evidence with strict `0`/`1` parsing; it cannot authorize a B4D
prospective run.

- `engine/biocatalyst/activation.py` provides read-only Cloudflare preflight,
  conditional-create plus exact-readback R2 receipt sealing, and a read-only
  heartbeat recheck. None collect source data, accrue a ledger, or advance a
  pointer.
- `scripts/biocatalyst_activation.py` exposes `check`, `seal`, `heartbeat`,
  and no-I/O local target-binding `validate` modes. The worker validates only
  root-controlled gate and heartbeat artifacts; it never receives the
  control/auditor token.
- `scripts/biocatalyst_worker.py` performs that validation before an attempt
  directory, source collector, or R2 store exists. Any gate, heartbeat,
  receipt, binding, ownership, or freshness failure quarantines the attempted
  B4D run and preserves the last valid pointer.
- `app/deploy/biocatalyst-setup.sh`,
  `app/deploy/biocatalyst-secure-paths.py`, and the root heartbeat units create
  the split environment and fixed root-controlled activation paths. Both
  `macro-biocatalyst.timer` and
  `macro-biocatalyst-activation-heartbeat.timer` are installed disabled.
- The canonical operator procedure and exact modes/owners now live in
  `docs/biocatalyst_operations_runbook.md`, section 14.

## Verification expected before any operator arm

The worker environment is `/etc/macro-biocatalyst.env` (`root:root`, `0600`).
The separate root-only control environment is
`/etc/macro-biocatalyst-control.env` (`root:root`, `0600`). The latter contains
the Cloudflare control/auditor token and is loaded only by the root heartbeat
service. The fixed activation directory and its two artifacts are
`root:macro-biocatalyst`: directory `0750`, `gate.json` `0440`, and
`heartbeat.json` `0440`.

When B4D is enabled, the worker environment must also name the exact R2 account
and an explicit `BIOCATALYST_R2_JURISDICTION` of `default`, `eu`, or `fedramp`;
the no-I/O local validator binds that account, jurisdiction, endpoint, bucket,
and worker credential identity to both artifacts.

An operator must independently confirm the dedicated bucket has an active
worker token with exactly the bucket-scoped `Workers R2 Storage Bucket Item
Write` permission, an enabled `Indefinite` R2 lock covering every key under
`biocatalyst/`, no enabled lifecycle deletion rule overlapping that namespace,
and an immutable conditional preflight receipt with byte-for-byte readback.
The lock may use the exact prefix or any ancestor, including the empty
bucket-wide prefix. Any bucket-wide, ancestor, exact, or nested lifecycle
deletion prefix is disqualifying. The separate gate TTL is fixed at 86,400
seconds and the heartbeat TTL at 7,200 seconds; the heartbeat is also bounded
by gate expiry.

Use the runbook's ordered procedure exactly: root `check`, root `seal` and
atomic gate install, root heartbeat service, local `validate`,
`biocatalyst-setup.sh --verify-prereqs`, then explicitly arm the heartbeat
timer before the worker timer. Re-run the root heartbeat service and local
validation after every new gate; reseal before the 24-hour gate expiry.

Relevant focused checks are:

```bash
pytest -q tests/test_biocatalyst_activation.py tests/test_biocatalyst_worker.py tests/test_biocatalyst_deploy.py
# Run only inside the runbook's disposable root subshell after its no-eval loader.
cd /opt/macro
/opt/macro-biocatalyst/current/bin/python -m scripts.biocatalyst_activation --mode validate \
  --gate-file /var/lib/macro-biocatalyst/activation/gate.json \
  --heartbeat-file /var/lib/macro-biocatalyst/activation/heartbeat.json
/opt/macro/app/deploy/biocatalyst-setup.sh --verify-prereqs
```

The latter two are VPS operator checks and require the reviewed root-owned
files, isolated runtime, and sealed artifacts; do not treat a local fixture
test as evidence that Cloudflare retention is configured.

## Explicitly not done

- No external Cloudflare configuration was changed: no token was created or
  narrowed, no lock was added, and no lifecycle rule was changed.
- No VPS setup, environment population, gate seal, heartbeat start, or timer
  arming was performed.
- Shipping the B4E code and service definitions does not arm either timer.
  Production remains dark until the separate operator sequence succeeds; no
  live collection, public-pointer advance, or prospective baseline is asserted
  by this release alone.

## Authority and rights fences

B1/B2/B4D remain source-fact evidence lanes. A registry record change may be
displayed as context or explanation only; it is not a protocol assertion,
clinical conclusion, issuer exposure, security conclusion, materiality score,
ranking, selection, sizing, gating, or trade instruction. B4E changes none of
those boundaries.

NCT ID remains the only identity here. Corporate Intelligence retains the
point-in-time issuer/security, asset, ticker, economics, and rights bridge.
Neural Web receives facts/context only. Prophet remains blocked until that PIT
issuer/security bridge and a private transport are reviewed and operating; it
has no origination, confidence, geometry, ranking, or trading authority from
BioCatalyst evidence.

## Next product slice: Trial Protocol Peer Matrix

Start the Trial Protocol Peer Matrix only after the B4E operator path is
separately reviewed and, if desired, properly armed. Build it as a bounded
facts-only comparison of entitled, pointer-bound trial records: explicit NCT
cohorts, current-field/milestone comparisons, and Record History or
first-observed availability labels. Do not invent a parallel cohort store,
backfill a change clock, resolve issuer/security identity, or convert protocol
fields into a catalyst, probability, peer rank, or trade signal. Keep raw
evidence, receipt keys, and private hashes out of the surface.
