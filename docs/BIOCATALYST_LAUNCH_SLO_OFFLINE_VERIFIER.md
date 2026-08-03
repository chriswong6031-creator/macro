# BioCatalyst launch-SLO offline verifier

`verify_biocatalyst_launch_slo_evidence(...)` is the only BC-O2a path that can
recompute a claimed `soak_complete_passed` result. It is an offline reader:
it has no network client, timer, writer, source activation, product endpoint,
Prophet action, or Neural Web authority.

The generic contract paths remain intentionally stricter for a pass claim:
`validate_contract(...)` and `ContractRegistry.issues(...)` always emit
`launch_slo.trusted_evidence_verifier_unavailable`. A caller must explicitly
select the offline verifier and provide an approved evidence root; a
`repo_root` never substitutes for evidence.

## Store layout

The caller supplies an absolute, non-symlink directory containing:

```text
<evidence-root>/.biocatalyst_launch_slo_offline_store.v1
<evidence-root>/manifests/<scheduled-manifest-content-sha256>.json
<evidence-root>/artifacts/<artifact-content-sha256>.json
<evidence-root>/recovery_input/<content-sha256>.json
<evidence-root>/recovery_readback/<content-sha256>.json
```

The sentinel file contains exactly
`biocatalyst_launch_slo_offline_store.v1` followed by one newline. Every JSON
file must be canonical JSON bytes. The verifier never trusts a relative path
from an artifact: it derives the local filename from the SHA-256 declared in
the content-addressed/frozen manifest and requires the R2 reference to be exactly
`r2://biocatalyst-soak/<kind>/<sha256>.json`.

The verifier rejects a missing root/sentinel, relative path, symlink, hardlink,
FIFO or other non-regular file, path escape, oversized file, byte-count/hash mismatch,
non-canonical or duplicate-key JSON, excessive scalar/depth/node count, and a
file that changes while being read. It opens the absolute root component by
component with `O_DIRECTORY|O_NOFOLLOW`, pins that root directory descriptor,
and traverses every parent and leaf with descriptor-relative `openat` calls.
Every leaf is opened with `O_NONBLOCK` before `fstat`, so a FIFO cannot block
the verifier before the regular-file check.
It therefore keeps reading the approved tree if a pathname is renamed or
replaced after a descriptor is opened; all descriptors close deterministically.

The verifier freezes one internal system-UTC clock reading for the complete
verification. Callers cannot inject this clock. The soak must already have
ended, and artifact captures, recovery input/start/completion/readback/capture,
and CI start/completion/capture may not claim future instants.

## Required evidence and recomputation

For every launch-critical source, the manifest must resolve exactly one
`raw_telemetry`, `correction_replay`, and `rollback_restore` artifact. There
must be exactly one aggregate `telemetry_generation` and `ci_validation`
artifact. All five types use
`biocatalyst_launch_slo_evidence_artifact.v1`, bind the exact scheduled
predecessor manifest ID/content digest/window/source/generation, and have
distinct content digests.

Artifact payloads are mutually exclusive by kind. A telemetry-generation
payload can contain only its raw-telemetry digest set; a raw-telemetry payload
can contain only observations; recovery payloads can contain only the typed
recovery procedure/timing/input/readback/check fields; and a CI payload can
contain only its run/commit/workflow/timing/check-outcome fields. Artifacts are
not eligible until their canonical capture time is at or after the soak end and
no later than the frozen trusted UTC instant. Correction and rollback drill IDs
are conditionally bound to their respective artifact kind prefixes.

Recovery is not accepted from a bare `result: passed`. For each recovery role,
the verifier resolves a `recovery_input` and `recovery_readback` object by its
own fixed digest-addressed path, verifies their bytes/schema/bindings, and
derives the result from: the input's expected digest, the readback's exact
input digest and observed digest, readback verification, operation/source/
generation bindings, and four typed verification checks. The input and
readback cannot be supplied as an arbitrary external path. Their chronology is
strictly recomputed as `soak end <= input capture <= start <= completion <=
readback capture <= artifact capture <= trusted now`.

The CI role likewise derives its result from typed outcomes for contract
validation, evidence integrity, and source recomputation; it binds an exact
lowercase Git `commit_oid` plus `git-sha1` or `git-sha256` hash algorithm.
This accepts real 40-character Git SHA-1 OIDs and 64-character Git SHA-256
OIDs while rejecting short, uppercase, and algorithm-length-mismatched values.

The predecessor must already have been `soak_scheduled`; its frozen source
policy, source-registry binding, authority denial, and exact 14-day window must
match the claimed completed manifest. This rejects post-hoc threshold,
exclusion, source, and cadence edits.

Raw telemetry must contain exactly one observation for every frozen UTC
schedule opening—no omissions, extras, or duplicates. Every row carries
canonical `attempted_at` and `completed_at` fields. The verifier parses both
frozen window offsets and requires `window open <= attempted_at <= completed_at
<= window close`; a miss may complete exactly at the inclusive close. BC-O2a recomputes all
stage counts, end-to-end successes/misses, upstream outage count, consecutive
misses, nearest-rank p95 freshness, minimum completeness/prior-scope ratios,
critical failures, per-source pass, and all-source aggregate pass. It then
requires every claimed result field to equal that recomputation. Recovery and
CI evidence must also pass; they cannot be covered by a weighted aggregate.

This sublane deliberately does not create a 14-day result. The currently
committed source remains pre-soak/unarmed until a separately governed O2
operator workflow writes real evidence and calls this verifier.

BC-O2a does not yet provide a cryptographic runner attestation, remote
object-store signature, or an operational action endpoint. Its proof is a
deterministic local recomputation over an explicitly approved offline evidence
root; those stronger provenance/operations controls remain separate,
non-authorizing O2 work.
