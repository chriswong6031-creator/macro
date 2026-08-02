# BioCatalyst Operations Runbook

Status: B1 worker implementation is implemented and reviewed but **dark by
default**. No live enablement, product API exposure, Prophet signal, or Neural
Web authority is asserted by this document.

## 1. Scope and ownership

The first operable slice is a source-canonical ClinicalTrials.gov source-state
lane for an explicit NCT canary allowlist. BioCatalyst owns exact raw
ClinicalTrials.gov response objects, sanitized fetch receipts, source snapshots,
an allowlisted read projection, immutable local/R2 retention receipts, and
bounded operational health.

Named operational owner: `mastermindx_platform_ops`.

The owner is responsible for source etiquette, service health, watermarks, storage retention, replay, incidents, and disabling publication when completeness cannot be established. Domain interpretation remains outside the worker.

This slice does not own company identity, a security master, SEC or issuer
documents, cash/runway, financing, saved queries, watchlists, Neural Web
authority, Prophet selection, Terminal user state, observations, or diffs. The
executable boundaries live in `config/sector_intelligence_ownership.yml`.

## 2. B1 topology and arming boundary

The reviewed, operator-installed units are:

- `macro-biocatalyst.service`: one-shot canary poll and projection publish;
- `macro-biocatalyst.timer`: hourly trigger with randomized delay; and
- existing `macro-api.service`: read-only authenticated product API.

The worker is disabled by default. Explicit operator arming requires:

1. `BIOCATALYST_ENABLED=1`;
2. a non-empty `BIOCATALYST_CANARY_NCTS` allowlist;
3. a descriptive `BIOCATALYST_USER_AGENT` with an operator contact;
4. the dedicated `BIOCATALYST_R2_*` credential set scoped to BioCatalyst only;
5. writable worker state and public-generation directories;
6. the isolated `/opt/macro-biocatalyst/current` runtime passing its
   conditional-create capability check; and
7. an initial complete run whose raw pages, receipts, snapshots, and counts
   reconcile.

The worker is not attached to the nightly GitHub Actions collector, render lane, or intraday forward-ledger jobs. Those lanes cannot satisfy the two-hour source freshness target and must not become a second scheduler.

### B1 deployment and arming boundary

The isolated deployment entrypoint is `app/deploy/biocatalyst-setup.sh`. It must
run as root on the VPS. Idempotently it creates the static, non-login
`macro-biocatalyst` user and primary group; makes the top-level state anchor
`root:macro-biocatalyst` mode `0750`; makes only its state and public children
service-owned with mode `0700`; and creates or corrects
`/etc/macro-biocatalyst.env` as `root:root` mode `0600`. The systemd manager
reads that environment file before dropping privileges; the worker identity
cannot open it as a file.

State, public, staging, committed, dead-letter, and environment provisioning is
performed by `app/deploy/biocatalyst-secure-paths.py` through directory-relative
file descriptors with `O_NOFOLLOW`. Every managed anchor must be the expected
directory or regular-file type. A pre-created symlink, a file in place of a
directory, FIFO, socket, or device aborts setup without chmod/chown touching its
target.

The runtime parent is `root:macro-biocatalyst` mode `0750`. Setup calls the
shared `app/deploy/biocatalyst-runtime.sh` transaction: dependencies are built
inside a fresh versioned virtualenv, the botocore `PutObject.IfNoneMatch`
capability is verified, and only then is `/opt/macro-biocatalyst/current`
atomically switched to the candidate. Runtime contents remain root-owned and
group-readable/executable, never service-writable. A failed build or capability
check leaves the last-good `current` target selected. Setup validates the units
with `systemd-analyze verify` when available and installs them, but does **not**
enable or start either unit.

Before root executes a selected runtime, the secure-path helper reopens the
runtime root, version directory, stamp, `bin`, and copied Python executable with
no-follow semantics. It rejects ownership drift, group/world-write bits,
non-regular executable or stamp files, unsafe tree entries, escaping symlinks,
or a changed `current` target. A rejected selected runtime is rebuilt in
staging; it is never executed as root merely because its requirements stamp
matches.

The service runs as `macro-biocatalyst` with no ambient or bounding
capabilities. `ProtectSystem=strict` keeps the host filesystem read-only except
for explicit state and public `ReadWritePaths`; the secret environment file is
inaccessible inside the service mount namespace. Kernel, device, home,
namespace, process-view, realtime, and address-family restrictions further
bound the one-shot worker.

Populate the root-owned env file with the three named worker controls above and
the BioCatalyst-scoped object-store endpoint, bucket, access key, and secret.
Then use `biocatalyst-setup.sh --verify-prereqs`; this check reports only missing
key names, never their values. After the initial complete-run verification, an
operator explicitly arms the hourly timer with:

```bash
systemctl enable --now macro-biocatalyst.timer
```

`app/deploy/update.sh` reconciles reviewed units and the pinned dedicated
runtime only when **both** units and an isolated runtime already exist on the
host. A requirements change uses the same build-verify-atomic-swap transaction;
it never runs pip inside the selected runtime. Unit replacement is gated on a
verified `current` runtime. The updater never creates an absent lane, writes
credentials, enables a timer, or starts the collector. When the timer is already
enabled, it is restarted only to load a reviewed timer-unit change;
worker-level non-blocking locking remains the authority for overlap prevention.

## 3. Canonical storage

Private evidence key namespace mirrored immutably after a reconciled run:

```text
biocatalyst/raw/clinicaltrials/v2/version/{yyyy}/{mm}/{run_id}/{before|after}/{exact_response_sha256}.json
biocatalyst/receipts/clinicaltrials/version/{yyyy}/{mm}/{run_id}/{before|after}.json
biocatalyst/raw/clinicaltrials/v2/pages/{yyyy}/{mm}/{run_id}/{page_ordinal}/{exact_response_sha256}.json
biocatalyst/receipts/clinicaltrials/{yyyy}/{mm}/{run_id}/{page_ordinal}.json
biocatalyst/runs/clinicaltrials/{yyyy}/{mm}/{run_id}.json
biocatalyst/raw/clinicaltrials/v2/{nct_id}/{canonical_content_sha256}.json
biocatalyst/source_snapshots/clinicaltrials/{nct_id}/{source_snapshot_id}.json
biocatalyst/mirror_receipts/{run_id}.json
```

Only a complete, independently revalidated private tree is conditionally
created and read back in the dedicated R2 bucket. A malformed HTTP-200 body is
instead retained under the attempt's local dead-letter tree for bounded
diagnosis, using these hash-addressed evidence keys:

```text
biocatalyst/raw/clinicaltrials/v2/failed-fetch/{yyyy}/{mm}/{run_id}/{endpoint}/{attempt}/{exact_response_sha256}.bin
biocatalyst/incidents/clinicaltrials/{yyyy}/{mm}/{run_id}.failed_fetch_{endpoint}_{attempt}_{digest_prefix}.json
```

Failed-fetch evidence does not mint a successful receipt, enter the reconciled
R2 mirror transaction, or advance the public pointer. B1 therefore makes no
durable-R2 claim for this local diagnostic retention; a future quarantine
mirror requires a separately reviewed lifecycle and access policy.

VPS state:

```text
/var/lib/macro-biocatalyst/state/staging/
/var/lib/macro-biocatalyst/state/committed/{run_id}/private/
/var/lib/macro-biocatalyst/state/committed/{run_id}/incidents/
/var/lib/macro-biocatalyst/state/dead-letter/
/var/lib/macro-biocatalyst/state/biocatalyst_worker.lock
```

The `/var/lib/macro-biocatalyst` anchor is owned by
`root:macro-biocatalyst` with mode `0750`. Its `state` and `public` children and
the managed state subdirectories are owned by
`macro-biocatalyst:macro-biocatalyst` with mode `0700`; no other service gets
write access.

Atomic read projection (the public root contains no raw response, receipt,
snapshot, private object key, absolute filesystem path, or credential):

```text
/var/lib/macro-biocatalyst/public/current.json
/var/lib/macro-biocatalyst/public/generations/{run_id}/manifest.json
/var/lib/macro-biocatalyst/public/generations/{run_id}/source_manifest.json
/var/lib/macro-biocatalyst/public/generations/{run_id}/trials/{nct_id}.json
/var/lib/macro-biocatalyst/public/generations/{run_id}/health.json
/var/lib/macro-biocatalyst/public/health.json
```

`current.json` is the only commit pointer. A complete immutable generation is
installed and revalidated before that pointer advances; the root `health.json`
is mutable operational status and is written only after pointer success.

Full raw objects, tokens, private object keys, absolute filesystem paths, and
credentials never enter the B1 public projection. Repository data is limited to
bounded synthetic or redacted fixtures.

Public source states carry only opaque source-snapshot IDs and content-addressed
source-record IDs. Before publication, the worker independently reloads the
private run, every ordered receipt, exact page body, canonical per-study object,
and source snapshot. It rejects missing or extra private files, validates byte
counts/hashes, pagination, raw-derived counts, snapshot coverage, and the exact
allowlisted public-state fields before any private R2 write or public pointer
advance. Fact-state taxonomies, observations, and diffs are B2 work, not B1.

## 4. Source and version semantics

ClinicalTrials.gov API v2 is treated as a current-state source. B1 stores the
source state it actually retrieved; it does not claim historical coverage or
interpret the registry's `LastUpdatePostDate` as when BioCatalyst knew a fact.

The upstream dataset is generally refreshed once each weekday, while the
BioCatalyst canary checks hourly. The two-hour budget describes worker
operations after a source refresh; it is not a claim that ClinicalTrials.gov
publishes hourly. Each run preserves both exact `/version` response bodies and
sanitized, hash-bound before/after receipts, including the API version and
`dataTimestamp` exactly as supplied. B1 never uses that raw value for elapsed
freshness arithmetic. An
explicit-offset value is checked against the worker clock with a 36-hour future
poisoning guard; an offset-less value is compared only as UTC-shaped civil time
without silently assigning an upstream timezone. ClinicalTrials.gov attribution
and BioCatalyst's normalization disclosure remain on every public source state.

ClinicalTrials.gov's public product may expose prior study versions, but B1 is
not a historical-version ingest. A separately validated historical adapter is
required before any historical-change claim.

The worker stores two distinct hashes:

- exact response-body SHA-256 for archive integrity; and
- canonical per-study JSON SHA-256 for source-state identity.

Canonical study hashing sorts object keys and preserves array order. Retrieval
time belongs in the receipt, not in the content hash. The exact page-response
object retains the original private response bytes so its response hash can be
replay-verified; the sanitized receipt stores only pagination-token hashes. A
malformed HTTP-200 `/version` or `/studies` body is retained as a local private
failed-fetch artifact and bounded incident, never as a successful receipt or
part of the reconciled R2 mirror transaction.

Every live run also records a deterministic digest of the collector parser,
shared CT.gov relational validator, and the schemas that govern the run,
receipt, and source snapshot. The worker and offline replay reject a run whose
digest does not match the executing code surface.

Initial coverage is always `current_only`. Poll frequency and elapsed service
time never promote a trial to `full_version`. Historical cutoffs and change
claims are future B2 capabilities, not B1 fallbacks.

Permitted product language:

> ClinicalTrials.gov's registry record changed; first observed within this interval.

Forbidden from this slice:

- “the protocol changed”;
- “the trial halted on” a registry update date;
- “the site activated” from a newly listed location;
- “enrollment accelerated” from a changed count;
- “complete historical record”; and
- any probability, materiality, ranking, gating, sizing, or trade recommendation.

## 5. Run transaction

Each poll is a bounded transaction with one immutable run receipt.

1. Acquire the non-blocking worker lock and load only a fully validated current
   generation as the prior watermark.
2. Collect the exact CT.gov v2 canary pages and stage private evidence plus a
   collector-public projection outside the real public root.
3. Require `canary_poll`, the exact configured NCT universe, and the exact
   API-root/path/base-query wire binding before any R2 write.
4. Independently reload the run, ordered receipts, exact page bodies, canonical
   per-study objects, and complete source-snapshot set. The worker calls both
   the reusable publication context and `validate_ctgov_publication_bundle`.
5. Reject changed source versions, pagination cycles, page-cap exhaustion,
   divergent duplicates, count mismatch, timestamp regression/future poisoning,
   omitted/substituted canary IDs, missing or extra private files, or any
   snapshot/public-state mismatch.
6. Mirror every exact private file to the dedicated R2 credential plane using
   conditional create plus byte-for-byte readback, then retain the same private
   tree locally under `committed/{run_id}`.
7. Persist a deterministic mirror receipt keyed by the run ID and read it back.
8. Build a sanitized, hash-complete public generation; revalidate it after
   install; advance `current.json` last; then best-effort write mutable health.

A partial, failed, or quarantined run cannot advance the watermark or replace a
good current generation. A post-archive failure leaves a bounded private
incident receipt linking the candidate run, R2 verification state, dead-letter
reference, and prior/observed pointer without exposing paths or secrets.

B2 may later add prospective observations, exact registry diffs, historical
adapters, and product-facing change language. Those artifacts are not emitted
or inferred by B1.

## 6. Health and SLO accounting

The B1 operational health DTO exposes only these bounded fields: schema version,
state, enabled flag, generation ID, configured/observed NCT counts, last attempt,
last success, raw source timestamp, freshness budget, coverage class, and a
bounded error code. It deliberately does **not** claim pages, study changes,
source retrieval time, watermarks, consecutive misses, full reconciliations,
or parser/API versions as public operational fields yet.

Generation-local health is immutable and hash-bound beside its generation. Its
generation ID, configured/observed counts, raw timestamp, and last
attempt/success must match the generation manifest and validated projection. A
failed refresh that retains a prior pointer uses that prior generation's counts
and last-success value rather than fabricating candidate coverage. “Process
exited zero” alone is not a successful opportunity.

The worker persists `fresh`, `partial`, `quarantined`, or `disabled` as
appropriate. `fresh` is not perpetual: every API or product consumer must read
health through `PublicGenerationPublisher.read_operational_health`, which
strictly binds the mutable DTO to the validated current generation and derives
`stale` once the transaction-time `last_success_at` exceeds the 7,200-second
budget. The source's offset-optional `dataTimestamp` is never used for elapsed
freshness. This read-time downgrade does not mutate the retained health file.

An absent, malformed, symlinked, or pointer-divergent health surface fails
closed; consumers must not read `health.json` directly or preserve a cached
`fresh` label. `unavailable` remains reserved for a future authenticated API
adapter that can return a bounded no-generation DTO.

Only explicit transient availability failures are `partial`: HTTP transport or
unexpected status, bounded R2 read/create availability failures, and a pointer
write whose rollback was proven. Provenance, content, immutability, source
poisoning, configuration, and filesystem-boundary failures are `quarantined`.

## 7. Secrets and least privilege

Runtime configuration is held outside git. The worker receives only:

- `BIOCATALYST_ENABLED`;
- `BIOCATALYST_CANARY_NCTS`;
- `BIOCATALYST_USER_AGENT`;
- `BIOCATALYST_R2_ENDPOINT`, `BIOCATALYST_R2_BUCKET`,
  `BIOCATALYST_R2_ACCESS_KEY_ID`, and `BIOCATALYST_R2_SECRET_ACCESS_KEY`; and
- the service-injected fixed state/public roots
  `/var/lib/macro-biocatalyst/state` and `/var/lib/macro-biocatalyst/public`.

The API process gets read access to the public projection only. It must not receive object-store write credentials. Receipts allowlist safe request and response headers and hash pagination tokens; they reject authorization, cookie, API-key, proxy-authorization, and set-cookie fields.

The static worker identity has no login shell, no Linux capabilities, no write
access to application code or its versioned runtime, and no direct file access
to `/etc/macro-biocatalyst.env`. Root remains the only principal that can change
credentials, runtime selection, or systemd policy.

Exact transitive dependency locking and bounded garbage collection for old,
unselected version directories remain deployment follow-ups. Until then,
requirements stay range-pinned and prior verified runtimes are retained for
manual rollback; neither limitation weakens the no-follow or atomic-swap gates.

## 8. Replay and correction

Replay reads immutable receipts, exact archived page bytes, canonical content
objects, and source snapshots into an isolated staging projection. It must
reproduce B1 source states and the public manifest byte-for-byte for the pinned
parser version before a future operator-approved promotion. Standalone schema
validation is insufficient; raw evidence and snapshot relationships are always
rechecked.

A parser upgrade creates a new parsed projection version. It does not rewrite a
raw source object. Observation, correction, supersession, and diff workflows
are explicitly deferred to B2.

## 9. Incident response

Disable publication when any of these occurs:

- repeated pagination token;
- configured page cap reached;
- divergent duplicate body for one NCT in one run;
- upstream timestamp regression outside tolerance;
- raw archive or receipt durability failure;
- projection publish failure;
- count reconciliation failure;
- future source timestamp outside tolerance;
- credentials or private storage coordinates detected in a receipt or response; or
- two consecutive missed opportunities.

Response:

1. leave the last-good projection intact;
2. mark health `partial` or `quarantined` with a bounded code;
3. retain the failed attempt/dead-letter material and, after private archive,
   write a bounded immutable incident receipt with mirror and pointer state;
4. stop watermark advancement;
5. diagnose against the exact run and page receipt;
6. replay into staging;
7. compare hashes and counts; and
8. resume only after a complete opportunity passes.

Rollback is a pointer change to the prior verified projection generation. Immutable source objects and receipts are never deleted during an incident.

## 10. B1 closure and B2 fence

B1 can be operator-armed because NCT identity is source-canonical and the
source-state lane needs no company/security join. It remains a local,
dark-by-default evidence worker until a separately reviewed read API and UI
integration are delivered. Full BioCatalyst intelligence remains open pending
company/security identity, SEC/issuer documents, cash and financing, clinical
outcome labels, regulatory/patent data, market structure, and any Prophet or
Neural Web authority contract. The API and UI must omit those fields rather
than synthesize substitutes.
