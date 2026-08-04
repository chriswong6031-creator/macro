# Capital Structure share-count R2 conformance — operator handoff

Status: code-only foundation; locally tested; **not provisioned, never run, no provider proof**

Owner: `capital-structure-intelligence`

Canonical program contract: `docs/CAPITAL_STRUCTURE_INTELLIGENCE_CONTRACT.md`

## 0. Current truth

This wave adds a manual, main-only Cloudflare R2 conformance witness for one
narrow question: can one fresh object be conditionally created, replaced by its
exact ETag, and read back while duplicate/stale conditions fail without mutating
the object?

The code and tests exist. The protected GitHub Environment, isolated R2 bucket,
and dedicated credentials are not provisioned for this workflow. The workflow
has not run, no receipt exists, and R2 CAS behavior is not yet proven. Do not
describe this as provider proof, publication activation, share-count coverage,
or retention readiness.

The reviewed implementation now accepts only botocore `ClientError`, HTTP 412,
and exact `Error.Code=PreconditionFailed` for deliberate duplicate/stale
refusals. Every 409 and unrelated or untyped exception is inconclusive. It also
preserves the core failure's exact stage/category and ordered prefix of proven
witnesses, while wrapper-only failures may conservatively report an empty
prefix. Every owned body receives a close attempt on deadline and
malformed/unexpected-success paths; a close failure is inconclusive. The receipt
also binds reviewed source and dependency hashes. These code gates do not
authorize provisioning or a run;
that remains an explicit operator action against an independently reviewed,
dedicated Environment and bucket.

## 1. Implementation inventory

- `.github/workflows/capital-share-count-r2-conformance.yml`
- `engine/capital_structure/share_count_r2_conformance.py`
- `scripts/probe_capital_structure_share_count_r2.py`
- `contracts/capital_structure_share_count_r2_conformance_receipt.schema.json`
- `tests/test_capital_structure_share_count_r2_conformance.py`
- `tests/test_capital_structure_share_count_r2_operator.py`
- `requirements/capital-share-r2-conformance-macos-arm64-py312.lock`

The workflow executes an exact reviewed source archive from its `main` commit
and installs the hash-locked
`requirements/capital-share-r2-conformance-macos-arm64-py312.lock`. It has no
cron or push trigger, no repository write permission, and no publication step.

The workflow re-hashes and smoke-loads the minimal reviewed archive before any
credentialed step. It runs a narrow boto-only lock with isolated/no-input pip
and invokes Python with `-E -s`. The closed receipt's
`execution_provenance` commits to both archive and lock digests in addition to
the exact GitHub repository/workflow/main-ref/run/commit. Preserve the Actions
run with the receipt during review. This is not a process-security or
self-hosted-runner-integrity attestation.

## 2. Operator boundary

The dispatch gate is:

- workflow: `capital-share-count-r2-conformance`;
- ref: `main` only;
- required input: `run_conformance=true`;
- Environment: `capital-share-count-r2-conformance`, configured with required
  reviewers, restricted to `main`, and preferably preventing self-review;
- workflow timeout: five minutes;
- probe deadline: 90 seconds, with a later 95-second stuck-call process alarm.

Provision exactly five Environment-scoped secrets, all dedicated to the isolated
bucket:

```text
R2_SHARE_COUNT_CONFORMANCE_ENDPOINT
R2_SHARE_COUNT_CONFORMANCE_ACCOUNT_ID
R2_SHARE_COUNT_CONFORMANCE_BUCKET
R2_SHARE_COUNT_CONFORMANCE_ACCESS_KEY_ID
R2_SHARE_COUNT_CONFORMANCE_SECRET_ACCESS_KEY
```

Do not copy production share-count, Research Vault, or generic R2 credentials
into this Environment. The wrapper has no fallback to any other secret name. The
endpoint must be the exact HTTPS Cloudflare R2 global, EU, or FedRAMP account
root for the supplied 32-hex account ID.

The runtime adapter guards the reviewed path to `HeadObject`, `GetObject`, and
`PutObject` for one exact random key:

```text
capital_structure/share_counts/conformance/v1/<32-lowercase-hex>.json
```

The reviewed core invokes no List, Delete, copy, multipart, HMAC, production
selector, share-count receipt, publication, or retention operation. This is not
a process-security capability boundary: the adapter and wrapped boto client are
in the same Python process, so a different imported module could reach the raw
client implementation. Source review plus isolation of the credential and
bucket are the enforceable boundary and remain operator responsibilities.

## 3. What a passing run must prove

The admissible target is this complete ordered witness:

1. `If-None-Match: *` creates payload A.
2. HEAD A plus exact ranged GET A bind A's length, content type, metadata, opaque
   ETag, range, and bytes.
3. A duplicate absent-only PUT returns exact HTTP 412 `PreconditionFailed`; a
   second HEAD and GET prove A is unchanged.
4. `If-Match: <A ETag>` replaces A with different payload B.
5. HEAD B proves B's expected metadata and a different opaque ETag.
6. A ranged GET and a PUT with stale A ETag each return exact HTTP 412
   `PreconditionFailed`.
7. Exact ranged GET B with B's ETag proves the final expected bytes.

Only the complete ordered witness can return `passed`; every transport,
deadline, cleanup, response-shape, status, range, metadata, or byte ambiguity is
non-passing.

This trace is deliberately sequential. It does not run competing clients or
prove concurrent linearizability, winner uniqueness under races, or the retry
semantics of the production share-count head client. The conformance wrapper's
single-attempt SDK configuration is not evidence about production.

Transport ambiguity, deadline, unexpected status, malformed metadata, stale
mutation, byte/range mismatch, extra bytes, or body-close failure is never a
pass. The status is `passed`, `failed`, or `inconclusive`; only `passed` contains
the full eleven-step witness.

## 4. Receipt and residue

The local output filename is
`capital_structure_share_count_r2_conformance_receipt.json`, validated by the
closed `capital_structure.share_count_r2_conformance_receipt/v1` schema. It
redacts admitted bucket/key names and ETags behind SHA-256 commitments and binds
the endpoint host. A failure before configuration admission instead records
`admitted=false`, null endpoint/bucket identity, and the random-key commitment.
Every receipt binds GitHub run/ref/commit plus exact source-archive/dependency-
lock provenance and hard-codes all
publication, retention, share-count, risk, ranking, sizing, entry, trade, and
Prophet authorities false. Core failures preserve a closed stage/category and
the exact ordered prefix of proven witnesses; wrapper-only failures may
conservatively report an empty prefix. Every owned response body receives a
close attempt on normal, deadline, malformed, unexpected-success, and
readback-failure paths, and a close failure is inconclusive. The Python semantic
validator remains normative for relationships and the receipt self-hash that
JSON Schema alone cannot express.

The workflow uploads the receipt as the 90-day review artifact
`capital-share-count-r2-conformance-<run_id>-<attempt>`. It does not write the
receipt to R2, Git, a public page, or a production selector. Upload is
best-effort: checkout, virtual-environment, dependency, archive, timeout, or
cancellation failures can occur before any receipt is written, and the upload
step deliberately warns rather than inventing one. A missing artifact on a
failed run is a non-pass, not a green or empty receipt.

The reviewed probe never deletes its fresh witness object. A run leaves no
object when creation is proven not to have committed, and can leave up to one
small disposable object when creation commits or its outcome is ambiguous. Do
not aim this workflow at a production bucket and do not interpret conformance
residue as a data-plane artifact.

## 5. Synapse ruling

Do not register the expiring review receipt in `config/synapse.yml`. It has no
consumer and the registry has no storage locus for a GitHub Actions artifact.
`gitignored-local` and `r2` would both be false descriptions. The receipt schema
is source code, not a produced artifact. Register only a future durable receipt
plane that has an explicit owner, consumer, storage authority, cadence, and
retention contract.

## 6. What a future passed receipt closes—and what it cannot close

A reviewed `passed` receipt can support only this statement:

> At the recorded GitHub commit, time, endpoint, isolated bucket, and fresh key,
> the observed R2 API responses and exact readbacks satisfied the bounded
> conditional create/update/read protocol.

It cannot establish:

- provider-wide security, durability, or availability;
- credential authenticity or least privilege;
- production head publication or global rollback resistance;
- concurrent-writer linearizability or production adaptive-retry safety;
- share-count facts, issuer coverage, or freshness;
- conditional delete, retention, or safe compaction;
- UI/API readiness, Prophet integration, risk, rank, sizing, entry, or trade
  authority.

Retention remains separately blocked until atomic conditional delete is proven
on an isolated object, the publisher/compactor share an external fence, a
verifier/retention capability cannot write the signed head or receipts, deadline
and race tests pass, and the complete lane is independently re-audited. This
create/CAS/readback probe deliberately cannot satisfy that gate.

Publication activation also remains blocked until the production CAS client is
shown to issue one conditional attempt with hidden SDK retries disabled, or to
perform exact candidate reconciliation after every ambiguous/retried outcome,
and until an independent concurrent-writer race probe passes. A sequential
provider receipt cannot close either requirement.

## 7. Next steps (implementation first; operator provisioning remains deferred)

Obtain a final independent code re-audit of the exact merged bytes. Only after
that gate passes may an operator provision the protected Environment and
dedicated disposable R2 bucket/credential, review the exact `main` commit, and explicitly dispatch with
`run_conformance=true`. Preserve the Actions run URL,
download and schema-validate the receipt, inspect every step witness, and record
an activation ruling separately. A passing run does not itself toggle any
publication or migration variable, and it is insufficient without the
production-retry/reconciliation and concurrent-writer proofs above.
