# Calcbench Parity — Wave 3B-B3 Sealed Filing Attestation

**Canonical implementation handoff for Wave 3B-B3**

**Date:** 2026-08-02

**Status:** implementation complete; pre-merge release gates passed

## Outcome

Wave 3B-B3 adds the first controlled-source authority above the immutable
`ffpkg_` filing package and `ffxbrl_` parser artifact. Its `ffatt_` record makes
one deliberately narrow, time-scoped statement:

> At the recorded readback time, one pinned `ffsecsrc_` source snapshot
> contained the exact filing manifest, archive-index receipt/object, and
> selected filing-member receipt/object; replaying the pinned parser over those
> selected bytes reproduced the sealed extraction. When Company Facts evidence
> is supplied, named source rows correspond to named extracted facts only under
> the exact mapping profile recorded by this artifact.

This is stronger than a content hash and narrower than general XBRL semantic
validation. The source store remains a controlled internal authority, not an
SEC signature, timestamping service, taxonomy engine, calculation validator, or
claim that the SEC universe is complete.

## Three-address storage law

An attestation must never use a package member's `storage_key` directly as an
R2 key. The system has three distinct addresses:

1. the local archive-relative gzip path, content-addressed by the uncompressed
   SEC bytes;
2. the local archive-relative canonical receipt path, content-addressed by the
   receipt identity; and
3. the `source_sync` outer object key, content-addressed by the bytes of the
   local gzip or JSON file itself.

The pinned `ffsecsrc_` manifest is the only valid map between an archive-relative
path and its outer object key. B3 reads that immutable manifest with a bounded,
fail-closed primitive, rejects duplicate paths, verifies the outer byte length
and SHA-256, and then validates the inner receipt and uncompressed SEC bytes.
It never resolves `latest.json` and never converts an outage, 403, timeout,
malformed response, corrupt body, or oversize object into an authoritative
absence.

## Source evidence required for a positive selected-member claim

The builder must source-read and verify all of the following from the same
explicit source snapshot:

1. the canonical filing manifest at the path derived by
   `manifest_storage_key(manifest)`;
2. the archive-index receipt sidecar and gzip object;
3. the selected member's receipt sidecar and gzip object; and
4. the exact source-snapshot entries and outer objects that back each of those
   relative paths.

Both gzip reads are bounded by their trusted uncompressed receipt length plus
one byte. Both receipts must equal the retrieval evidence embedded in the
package. The recovered index bytes must equal the package's embedded raw index
witness. The recovered selected member bytes must pass
`verify_ixbrl_extraction_source`, which reparses the bytes and compares the
complete stable extraction semantics.

The v1 scope is intentionally `archive_index_plus_selected_member`. It does not
read every stored inventory member and therefore cannot upgrade package-wide or
filing-wide presence/completeness claims.

## Exact Company Facts correspondence

Company Facts matching is optional. A positive match requires strict readback
of one immutable Company Facts manifest, its exact capture receipt, and its
bounded raw response object from the same pinned source snapshot. The raw
response digest/length and the canonical decoded payload digest/length are
separate authorities and both must match their manifest/capture fields.

The matcher considers only available non-nil numeric facts with:

- an exact SEC CIK entity scheme and matching normalized CIK;
- a supported instant or duration period;
- complete, empty segment and scenario dimensional scope;
- one exact URI in the versioned namespace catalog; and
- one exact unit representation in the versioned unit catalog.

There is no suffix matching, prefix inference, custom-taxonomy guessing,
rounding tolerance, or arbitrary duplicate pairing. A positive binding exists
only when exactly one eligible extracted fact and exactly one Company Facts row
share the full accession, concept, period, unit, and canonical decimal value
projection. Duplicate candidates are `ambiguous`; unsupported namespaces,
units, dimensions, values, or period shapes are `not_evaluable`.

Company Facts is a current endpoint projection without XBRL context IDs or
dimension metadata. Therefore a match is a capture-scoped row correspondence,
not taxonomy validation, Company Facts completeness, filing completeness, or
proof that the source row was dimensionless.

## Artifact identity and clocks

The schema is `fundamental_forensics.filing_attestation/v1`; identity is
`ffatt_<sha256>` over the canonical body excluding `attestation_id`. The record
binds:

- `ffpkg_`, `ffxbrl_`, filing-manifest, selected-document, and source-snapshot
  identities;
- bounded readback witnesses for each source file;
- the parser profile/version/fingerprint and selected-member replay result;
- optional exact Company Facts row bindings and categorized nonmatches;
- causal source, acquisition, assembly, extraction, readback, and attestation
  clocks; and
- fixed coverage and nonclaim fields.

The attestation clock is sampled internally after successful source reads. A
caller cannot backdate it. Deserialization verifies canonical shape,
derivations, and content identity only; it does not re-establish store
presence. A later verification must perform fresh reads of the same immutable
snapshot.

## Required nonclaims

The v1 artifact must keep all of these false:

- external or SEC signature authority;
- full filing, SEC universe, or source-snapshot universe completeness;
- all package members present;
- Inline Document Set validation;
- taxonomy, presentation, relationship, or calculation validation;
- Company Facts completeness or dimension identity;
- Submissions source presence, acceptance-clock, raw-ledger, or PIT authority;
- legal, trading, Prophet, or Neural Web authority.

The positive UI label for this layer is **selected-member source replayed** or
**receipt-bound subset attested**, never “filing validated” or “XBRL semantic
validation.”

## Acceptance gates

The release suite must prove:

- strict bounded local and R2 reads, including close discipline;
- authoritative not-found versus 403, timeout, malformed response, and outage;
- pinned snapshot-only resolution, canonical manifest identity, duplicate-path
  rejection, and exact archive-relative to outer-key mapping;
- independent raw-byte, gzip-file, and outer-object digest verification;
- receipt-sidecar equality, bounded gzip inflation, and raw digest/length
  verification for the index and selected member;
- filing manifest/package/extraction identity and clock binding;
- mandatory selected-member parser replay and forged-artifact rejection;
- exact unique Company Facts match, decimal spelling equivalence, value
  mismatch, no row, ambiguity, dimensions, unsupported namespace/unit, wrong
  CIK/accession/period, and corrupt manifest/capture/response behavior;
- canonical `ffatt_` JSON, content-derived IDs, hostile mappings/subclasses,
  caps, internally sampled clocks, and explicit nonclaims; and
- CI reachability from implementation, test-only, and fixture-only changes.

## Pre-merge release evidence

The completed implementation passed all local release gates on 2026-08-02:

- **120 passed** in the focused attestation, Company Facts, source-sync,
  strict-store, and SEC-document-spine suite;
- **502 passed** in the broader filing parser, filing package, iXBRL,
  attestation, Company Facts, ledgers, query/snapshot, source-sync, and
  strict-store regression suite;
- **159 passed** in a clean Python 3.12 environment containing only the
  collector-registry lane's declared minimal dependencies;
- **271 passed** in the Research Vault lane's declared minimal dependency
  environment, including the strict-store suite;
- **11 passed** in `tests/test_ci_pack.py`;
- Python compilation and `git diff --check` completed cleanly; and
- an independent hostile review issued a ship verdict after a real pinned
  source snapshot built, canonical-restored, and fresh-replayed an attestation
  containing one exact Company Facts match.

These are implementation and pre-merge CI-reachability claims. Production
advancement remains governed by the repository ship loop and must be verified
against the deployed commit; this docket does not manufacture that evidence in
advance.

## Exact next lane

Wave 3B-B4 introduces `ffqsv2_`: immutable historical query snapshots whose
displayed cells can cite exact `ffatt_` dependencies. Only after that provenance
contract is sealed should the Verified History API and premium comparison UI
expose filing-backed status, source/as-of clocks, coverage boundaries, and a
per-cell provenance waterfall.

No v1 `ffqs_` snapshot may be relabeled as attested history, and no downstream
engine may infer broad filing authority from a selected-member B3 attestation.
