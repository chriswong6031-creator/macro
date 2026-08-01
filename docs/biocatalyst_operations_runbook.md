# BioCatalyst Operations Runbook

Status: B0a contract freeze. No production worker is enabled by this document.

## 1. Scope and ownership

The first live slice is a source-canonical ClinicalTrials.gov Trial Capsule for an explicit NCT canary allowlist. BioCatalyst owns the raw ClinicalTrials.gov response objects, fetch receipts, prospective observations, exact registry-record diffs, read projection, and source health.

Named operational owner: `mastermindx_platform_ops`.

The owner is responsible for source etiquette, service health, watermarks, storage retention, replay, incidents, and disabling publication when completeness cannot be established. Domain interpretation remains outside the worker.

This slice does not own company identity, a security master, SEC or issuer documents, cash/runway, financing, saved queries, watchlists, Neural Web authority, Prophet selection, or Terminal user state. The executable boundaries live in `config/sector_intelligence_ownership.yml`.

## 2. Initial production topology

Planned supervised units:

- `macro-biocatalyst.service`: one-shot canary poll and projection publish;
- `macro-biocatalyst.timer`: hourly trigger with randomized delay; and
- existing `macro-api.service`: read-only authenticated product API.

The worker is disabled by default. Production enablement requires:

1. `BIOCATALYST_ENABLED=1`;
2. a non-empty `BIOCATALYST_CANARY_NCTS` allowlist;
3. a descriptive `BIOCATALYST_USER_AGENT` with an operator contact;
4. object-store credentials scoped to the BioCatalyst prefix only;
5. writable private state and projection directories;
6. schema and replay tests passing; and
7. an initial complete run whose counts reconcile.

The worker is not attached to the nightly GitHub Actions collector, render lane, or intraday forward-ledger jobs. Those lanes cannot satisfy the two-hour source freshness target and must not become a second scheduler.

## 3. Canonical storage

Private immutable object storage:

```text
biocatalyst/raw/clinicaltrials/v2/{nct_id}/{content_sha256}.json
biocatalyst/raw/clinicaltrials/v2/pages/{yyyy}/{mm}/{run_id}/{page_ordinal}/{exact_response_sha256}.json
biocatalyst/receipts/clinicaltrials/{yyyy}/{mm}/{run_id}/{page_ordinal}.json
```

VPS state:

```text
/var/lib/macro-biocatalyst/state/runs/
/var/lib/macro-biocatalyst/state/observations/
/var/lib/macro-biocatalyst/state/watermarks/
/var/lib/macro-biocatalyst/state/dead-letter/
```

Atomic read projection:

```text
/var/lib/macro-biocatalyst/public/trials/{nct_id}.json
/var/lib/macro-biocatalyst/public/changes/{nct_id}.json
/var/lib/macro-biocatalyst/public/health.json
```

Full raw objects, tokens, private object keys, absolute filesystem paths, and credentials never enter the product response. Repository data is limited to bounded synthetic or redacted fixtures.

Public read snapshots carry only opaque source-snapshot IDs and content-addressed source-record IDs; they never carry private storage paths. Each projected fact has an explicit `observed`, `source_null`, `source_missing`, `not_applicable`, `parser_degraded`, or `license_restricted` state; an absent source module can never become an empty list. The projection hash binds those fact states and values to the declared source-snapshot reference and content hash. Before publication, the relational validator loads the private archived page bytes, verifies their byte count and SHA-256 against the exact page receipt, strictly parses unambiguous JSON, checks the raw study count and pagination-token hash, and proves that the declared study index exactly equals the canonical source snapshot. It then requires that source-record ID in the complete run's publication manifest and binds every projected fact to its registered ClinicalTrials.gov path and canonical-source value; a degraded or restricted state cannot hide a present source value.

## 4. Source and version semantics

ClinicalTrials.gov API v2 is treated as a current-state source. The first observation of a study starts transaction-time coverage; an old `LastUpdatePostDate` does not backdate what BioCatalyst knew.

The upstream dataset is generally refreshed once each weekday, while the BioCatalyst canary checks hourly. The two-hour SLO measures our collection pipeline after an observed upstream refresh; it is not a claim that ClinicalTrials.gov itself publishes hourly. Each run preserves the API `/version` `dataTimestamp` exactly as supplied. The current source value carries no explicit UTC offset, so BioCatalyst must not silently append one or use that value for elapsed-time arithmetic. Product projections attribute ClinicalTrials.gov, display the raw processing timestamp with its timezone limitation, identify BioCatalyst's parsing or normalization as a modification, and state that study sponsors or investigators supply the registry information. A registry listing is never rendered as government validation of a study's science or safety.

ClinicalTrials.gov's public product may expose prior study versions, but the B0a API collector is not a historical-version ingest. Until a separately validated historical adapter exists, only changes first observed prospectively by BioCatalyst are in scope.

The worker stores two distinct hashes:

- exact response-body SHA-256 for archive integrity; and
- canonical per-study JSON SHA-256 for source-state identity.

Canonical study hashing sorts object keys and preserves array order. Retrieval time belongs in the receipt, not in the content hash. The exact page-response object retains the original private response bytes so its response hash can be replay-verified; the sanitized receipt stores only pagination-token hashes. An identical source state creates another observation receipt but not a false new version or diff.

Initial coverage is always `current_only`. Poll frequency and elapsed service time never promote a trial to `full_version`. Unsupported historical cutoffs return `unsupported_as_of` rather than today's state or a nearest-record substitute.

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

Each poll is a transaction with an immutable run receipt.

1. Load the prior successful watermark without mutating it.
2. Read and pin the ClinicalTrials.gov `/version` `dataTimestamp`.
3. Build the canonical query manifest and overlapping source interval.
4. Fetch every page while recording sanitized page receipts.
5. Re-read `/version`; quarantine the run if the source dataset changed mid-run.
6. Quarantine repeated tokens, page-cap exhaustion, divergent duplicate NCT bodies, upstream timestamp regression, or conflicting API timestamps.
7. Archive raw bytes and per-study content objects.
8. Build parser-versioned trial projections and prospective observations, binding each source snapshot and observation to the complete run, exact archived page bytes, verified study index, page receipt, query universe, response hash, source timestamp, and transaction chronology.
9. Produce exact add/remove/replace path diffs against the last successfully published source state, then recompute the operations from both referenced snapshots, bind both source snapshots to one NCT, bind the observed interval to the two referenced observation receipts, and reject any mismatch before publication.
10. Call `validate_ctgov_publication_bundle` with the run, ordered receipts, exact raw bytes keyed by every receipt ID, and the complete source-snapshot set. It derives fetched/unique/duplicate counts and the publication manifest from the raw studies, rejects divergent bodies for one NCT, and requires exactly one snapshot for every configured NCT.
11. Publish the current projection by temp-write, fsync, and rename only after raw archive and receipts succeed.
12. Advance the successful watermark only after the whole run is complete.

A partial, failed, or quarantined run cannot advance the watermark or replace a good current projection. Missing from an incremental overlap query is never deletion evidence. Missing from a full reconciliation may be recorded as `not_observed_in_reconcile`, not “trial deleted.”

The standalone snapshot, observation, projection, and diff validators deliberately re-verify the complete raw-page map and are suitable for the bounded B0a canary. Before B1 expands beyond that allowlist, its bulk publisher must add a validated-publication context or batch consumer that reuses the bundle's parsed pages; looping standalone validators across a full universe is prohibited.

## 6. Health and SLO accounting

The health projection must expose, without secrets:

- schema and service version;
- enabled/configured state;
- configured and observed NCT counts;
- last attempt and last successful run;
- upstream `dataTimestamp` raw value and its retrieval time;
- source attribution and the source processing timestamp exposed to consumers;
- successful watermark and overlap window;
- pages attempted/succeeded;
- studies fetched, unique, duplicated, and published, plus change counts derived only from validated observation/diff artifacts;
- run completeness state;
- age and two-hour freshness budget;
- consecutive misses;
- last full reconciliation;
- parser/API schema versions; and
- bounded error codes.

An opportunity is one configured poll window. Success requires terminal pagination, internally consistent upstream timestamps, reconciled counts, durable raw receipts, full configured-universe publication coverage, and an atomic projection publish. The run document is not sufficient evidence on its own: the worker must call the run-to-receipts relational validator, then `validate_ctgov_publication_bundle`. Together they verify the content-bound query manifest, page cap, ordered receipt IDs, receipt-payload hash, non-repeating pagination-token chain, terminal raw token, source version, every response body and transaction time, raw-derived counts, divergent duplicates, indexed study content, and exact one-to-one publication-manifest coverage. “Process exited zero” alone is not a successful opportunity.

Source states:

- `fresh`: last complete opportunity is within budget;
- `stale`: last-good facts remain readable but the age exceeds budget;
- `partial`: the latest opportunity did not complete; last-good projection remains;
- `quarantined`: source inconsistency or invariant failure requires review;
- `disabled`: production flag or canary universe is absent; and
- `unavailable`: no successful projection exists.

## 7. Secrets and least privilege

Runtime configuration is held outside git. The worker receives only:

- `BIOCATALYST_ENABLED`;
- `BIOCATALYST_CANARY_NCTS`;
- `BIOCATALYST_USER_AGENT`;
- BioCatalyst-scoped object-store endpoint, bucket, access key, and secret;
- private state root; and
- public projection root.

The API process gets read access to the public projection only. It must not receive object-store write credentials. Receipts allowlist safe request and response headers and hash pagination tokens; they reject authorization, cookie, API-key, proxy-authorization, and set-cookie fields.

## 8. Replay and correction

Replay reads immutable receipts, exact archived page bytes, and content objects and writes to an isolated staging projection. It must reproduce source snapshots, observations, and diffs byte-for-byte for the pinned parser version before promotion. Projection publication, exact-diff publication, complete-run promotion, and evidence-claim publication must use their cross-document validators with the raw bytes supplied; standalone schema validation does not prove referential integrity.

A parser upgrade creates a new parsed projection version. It does not create a new source snapshot, source observation, or registry-change alert. Corrections append a superseding transaction record and close the prior transaction interval; they never rewrite the raw source object.

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
3. write the failed run receipt and dead-letter references;
4. stop watermark advancement;
5. diagnose against the exact run and page receipt;
6. replay into staging;
7. compare hashes and counts; and
8. resume only after a complete opportunity passes.

Rollback is a pointer change to the prior verified projection generation. Immutable source objects and receipts are never deleted during an incident.

## 10. B0 closure status

B0a may ship because NCT identity is source-canonical and the Trial Capsule needs no company/security join. Full B0 remains open until executable Corporate company identity, complete Market Data security-master, Corporate document/span, and Capital Structure registrations exist. The API and UI must visibly omit those fields rather than synthesize substitutes.
