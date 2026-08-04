# Wave 9: Manual R2 concurrent-writer witness

## Canonical deliverables

The implementation handoff is the new-file-only Wave 9 set:

- `engine/capital_structure/share_count_r2_concurrency.py` — reviewed protocol, receipt, and closed failure taxonomy.
- `scripts/probe_capital_structure_share_count_r2_concurrency.py` — credential/operator boundary and spawned-worker topology.
- `contracts/capital_structure_share_count_r2_concurrency_receipt.schema.json` — closed artifact shape.
- `.github/workflows/capital-share-count-r2-concurrency.yml` — manual, `main`-only protected-environment runner.
- `tests/test_capital_structure_share_count_r2_concurrency.py` — semantic and hostile protocol tests.
- `tests/test_capital_structure_share_count_r2_concurrency_operator.py` — operator, capability, schema, and workflow tests.

This document does not activate or dispatch the workflow, provision an
environment, or authorize production use. As of 2026-08-03, no provider receipt
exists and no concurrent R2 behavior has been proven.

## What the witness establishes

For eight precommitted fresh object keys, two persistent spawned OS children use independent boto sessions and clients. Each race starts from a common future monotonic release time and sends exactly one conditional `PutObject` per worker with standard retry mode and `total_max_attempts=1`.

For each round the protocol requires:

1. An exact typed 404 HEAD before genesis.
2. One exact HTTP 200 and one base `ClientError` `PreconditionFailed` HTTP 412, with one `before-send` event, one `needs-retry` event at attempt 1, and response retry count 0 for each writer.
3. Strict overlap of the two measured transport intervals.
4. HEAD plus bounded conditional ranged GET verification of the unique genesis object E0.
5. A successor race whose per-round commitment binds E0's redacted ETag hash and both precommitted successor candidates.
6. The same verifier check for E1, with E1 different from E0.
7. A parent/verifier stale `IfMatch=E0` PUT that receives the exact typed 412 and leaves E1 unchanged after a final bounded read.

Candidate keys, bytes, hashes, and global plan commitment are fixed before the first race. Receipts retain hashes and normalized response evidence, never raw keys, ETags, bucket names, credentials, or request IDs.

## Fail-closed boundary

An HTTP 409, untyped exception, unexpected status, hidden retry, repeated send, non-overlapping intervals, two successes, two refusals, malformed readback, stream-close failure, stale token, or post-hoc rewrite is not a pass. It produces only a closed failed/inconclusive classification when no write might remain in flight.

If a worker response is missing or malformed while a PUT could still be active, the wrapper terminates and joins/kills both children, raises `R2ConcurrencyInFlight`, and intentionally writes neither a semantic receipt nor a remote readback. The absence of an artifact is the fail-closed result for that case.

## Operating lane and deferred action

The workflow is `workflow_dispatch` only, accepts an explicit boolean, requires `refs/heads/main`, uses the existing `capital-share-count-r2-conformance` concurrency mutex and protected environment, and exposes only the same five isolated R2 values used by Wave 7. It creates a fresh hash-locked Python 3.12 environment from `capital-share-r2-conformance-macos-arm64-py312.lock`, source-attests a minimal archive, smoke-tests it without credentials, then uploads a local review artifact.

The workflow must remain dormant until a maintainer confirms the existing protected environment has the required reviewed secrets and deliberately dispatches it from `main`. No schedule, push trigger, storage provisioning, policy change, or production share-count integration belongs in this Wave 9 lane.

The probe never lists or deletes objects and performs no cleanup. A completed or
ambiguous run can therefore leave at most eight small disposable objects in the
isolated bucket. Lifecycle or operator cleanup is outside this receipt and must
not be claimed.

## Explicit exclusions

The witness is not a provider security, linearizability, durability, availability, retention, credential-authentication, server-simultaneity, multi-key atomicity, production-configuration, share-count-source, publication, trading, or investment proof. It is transport evidence for this exact bounded manual probe only.

## Operator continuation

After the exact merged bytes receive independent review, an operator may
separately confirm/provision the protected Environment and dedicated disposable
bucket credential, review the exact `main` commit, and deliberately dispatch
with `run_concurrency=true`. Preserve the Actions URL and downloaded receipt,
validate it against both the JSON Schema and the normative Python semantic
validator, inspect all eight rounds, and record a separate activation ruling.
A passing receipt cannot toggle a publication or migration flag and does not
replace the Wave 7 sequential receipt.
