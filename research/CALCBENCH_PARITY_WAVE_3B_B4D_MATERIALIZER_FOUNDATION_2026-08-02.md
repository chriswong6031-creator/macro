# Calcbench Parity — Wave 3B-B4D Materializer Foundation

**Canonical implementation handoff for Wave 3B-B4D-A**

**Date:** 2026-08-02

**Status:** implementation and local validation complete; independent source and
binding audits returned SHIP. Hosted CI, merge, and production advancement are
not claimed by this document.

## Outcome

B4D-A supplies the three offline seams needed to turn explicitly named,
immutable `ffsecsrc_` evidence into a deterministic B4-ready graph:

1. a pinned filing-package materializer;
2. a pinned Company Facts-to-ledger loader; and
3. a pure selected-leaf-to-B3 binding planner.

It makes B4's upstream inputs reproducible and its incomplete/ambiguous joins
inspectable. It does **not** renew SEC evidence, publish an `ffqsv2_` overlay,
advance a latest pointer, or label history verified.

```text
exact ffsecsrc_ members
  -> offline ffpkg_ materialization
  -> exact Company Facts ledger conversion
  -> sealed B3 ffatt_ records
  -> diagnostic selected-leaf candidate plan
  -> existing B4A prepare/publish + mandatory source replay
```

## Implemented surface

### Pinned filing-package adapter

`engine/fundamental_forensics/filing_package.py` exposes:

- `PinnedFilingPackageDescriptor`; and
- `materialize_filing_package_from_pinned_source(...) -> FilingPackage`.

The descriptor explicitly names one canonical CIK, accession, filing-manifest
identity, archive-index document, and a state for every member named by that
index. The adapter reconstructs an exact `PinnedSourceAuthority`, bounded-reads
the named immutable manifest and archive index, requires exact inventory
coverage, and verifies every stored member's receipt and compressed object.

The adapter performs no discovery, network access, ambient filesystem read,
mutable-`latest` lookup, or clock sampling. The caller supplies the assembly
clock and policy identity. The source snapshot cannot predate manifest
recording; a retrieval receipt cannot postdate the source snapshot; and package
assembly cannot predate the source snapshot. The aggregate retained-byte cap is
checked before any member is decompressed. The source authority also rejects an
index or member whose stored gzip exceeds the conservative envelope implied by
its receipted raw length, so ignored trailing bytes cannot turn a small filing
package into an unbounded read.

### Pinned Company Facts ledger adapter

`engine/fundamental_forensics/companyfacts_ledger.py` exposes:

- `CompanyFactsLedgerConversionConfig`;
- `PinnedSubmissionsSource`;
- `CompanyFactsConversionSourceBundle`;
- `load_companyfacts_ledger_from_pinned_source(...)`; and
- the equivalent `materialize_companyfacts_ledger_from_pinned_source` alias.

The bundle names the Company Facts manifest, capture, response, current
Submissions receipt/object pair, and every declared older Submissions
receipt/object pair. No path is guessed from a CIK. The loader reconstructs all
caller-owned frozen values before its first read, reopens the exact pinned
authority, and verifies the complete manifest -> capture -> response chain,
canonical receipt/object identity, CIK, immutable URL/path bindings, duplicate
and non-finite JSON rejection, and the existing conversion receipt.

Every older file declared by current Submissions must be supplied exactly once.
Per-payload, aggregate-input, occurrence, Submissions-row, older-file, and
revision-evidence ceilings remain explicit. Company Facts clocks and
Submissions retrieval clocks cannot exceed the pinned snapshot. Submissions
retrievals cannot exceed the supplied retention clock, and that retention clock
cannot exceed the snapshot. This is reproducible retention, not a freshness
claim. Compressed source objects are bounded before I/O and both their stored
and decoded bytes are charged to the aggregate read budget.

### Pure B4 binding planner

`engine/fundamental_forensics/attested_history_materializer.py` exposes
`enumerate_attested_binding_candidates(...) -> AttestedBindingReport` plus
immutable candidate, leaf, coverage, and report values.

The planner accepts an exact self-consistent loaded v1 `QuerySnapshot`, one
fully validated `CompanyFactsLedgerConversion`, and exactly one B3 input route:
structurally replay-addressed `AttestationMaterial` values or restored sealed
`FilingAttestation` records. It accepts no store, source path, latest pointer,
network client, or clock.

For every selected raw leaf it preserves:

- all root memberships;
- B4 eligibility (`sec-companyfacts` and `dimensions_known=false`);
- every exact B3 candidate;
- a closed, explicit rejection reason when it cannot bind; and
- an `AttestedOccurrenceBinding` only when the relation is unique on both the
  selected-occurrence and B3-match sides.

The join reuses B4's exact kernel across CIK, accession, Company Facts capture
and manifest identity, response digest, taxonomy, concept, unit, entry index,
period, and canonical decimal value. There is no value tolerance, ticker or
accession-only fallback, candidate tie-break, guessed source path, or discarded
unused B3 record.

Candidate and auto-bound leaves remain separate in the root report. Coverage
uses the same four meanings as B4A: `all_leaves_attested`,
`partially_attested`, `not_attested`, and `not_evaluable`. In this planner those
states are diagnostics, not a newly renewed source-verification statement. A
zero-binding report is valid diagnostic output and is not publishable by B4A.

Before returning a non-empty plan, the planner runs B4's canonical conversion,
attestation, projected-binding, and coverage serializers. It enforces B4's
exact per-artifact and combined wire envelopes, rather than assuming that
count-only limits imply a publishable payload. A hand-built v1 nominal with a
forged snapshot ID or unbound manifest/object witnesses is rejected before a
report can inherit that identity.

## A missing 404 is evidence, not a convenient absence

`collectors/sec_document_spine.py` now persists an observed SEC archive 404 as
canonical JSON at:

```text
missing-receipts/sha256/<digest-prefix>/<digest>.json
```

The sidecar contains the exact document ID, SEC archive URL, normalized
retrieval time, HTTP 404, and fixed reason. It has no synthetic body, receipt
ID, or gzip object. Its canonical bytes are its identity. Duplicate keys,
noncanonical JSON, invalid shapes, unbounded/hostile mappings, and a
cross-wired expected receipt fail closed.

The online collector may repair a corrupt same-key sidecar only while
persisting the freshly observed receipt. Offline package materialization cannot
mint or repair that witness: it bounded-reads the expected sidecar through the
pinned authority and exact-compares its canonical bytes. `not_requested` and
`rejected_by_policy` remain explicit non-byte states and are never converted
into observed absence.

This proves that the exact canonical receipt bytes are members of the trusted
pinned source snapshot. As with retained document receipts, the trusted
collector remains the authority that the HTTP observation occurred; the
sidecar is not an independently signed SEC assertion.

## Relationship to B3 and B4A

B3 remains the layer that makes the narrow selected-member source-replay
statement. B4A remains the layer that freshly replays every supplied B3 source
during preparation and again during publication preflight, writes the immutable
four-artifact `ffqsv2_` overlay, and advances its independent pointer last.

B4D-A changes neither authority. Its candidate list, rejection reasons,
auto-bindings, and coverage rows are an operator-visible plan for those
existing paths. Stored/self-consistent inputs do not become fresh SEC evidence
because the planner matched them.

## Clean-room boundary and fixed nonclaims

This implementation uses independently designed contracts over public
SEC-derived artifacts. It uses no Calcbench data, credentialed endpoint,
protected implementation, copied interface, or reverse-engineered proprietary
behavior.

B4D-A does not claim:

- current SEC availability, freshness, or completeness;
- a complete filing, Company Facts, fact, taxonomy, relationship, or
  calculation universe;
- fact-level XBRL identity or known dimensions;
- point-in-time contemporaneous verification or a trusted timestamp;
- accounting, restatement, audit-opinion, legal, or investment correctness; or
- Prophet, Neural Web, trading, scoring, or autonomous-decision authority.

The current governed metric catalog continues to reject
`dimensions_known=false` Company Facts facts. B4D-A does not weaken that rule or
pretend a test-local future profile is production governance.

## Deliberately excluded from this lane

There is no workflow, cron schedule, CLI operator, API route, UI, notification,
R2 writer, source collector expansion, B3 publisher, B4 publisher invocation,
premium entitlement change, or distributed publication coordinator here.

Direct module imports are intentional for this internal foundation. Before a
separate operator consumes it as a stable public API, the shared B4 projection
validator should be promoted from its private helper contract and common test
fixtures should be extracted.

The next controlled lane needs:

1. acquisition and retention of every explicitly named older Submissions
   source object;
2. a sealed/versioned issuer universe, source-bundle specification,
   conversion configuration, and governed selected profile;
3. operator review of the deterministic diagnostic plan;
4. invocation of B4A prepare/publish with fresh B3 materials and explicit
   operator clocks; and
5. a real distributed writer lease/CAS primitive before multi-host pointer
   publication.

The existing process-local single-writer lock is not a distributed lease.
Neither a candidate plan nor a green-looking coverage row may auto-publish or
be presented to users as renewed verification.

## Acceptance evidence

Observed in the final local worktree:

```text
Full Fundamental Forensics regression surface: 655 passed, 5 known warnings
CI manifest/pack:                           12 passed
Changed Python modules/tests:              py_compile clean
Both CI YAML documents:                    parsed successfully
Git patch:                                 diff --check clean
Independent source/provenance audit:       SHIP
Independent binding/claim-boundary audit:  SHIP
```

The 655-test command includes every `tests/test_fundamental_forensics_*.py`
suite plus SEC document spine, private Forensics API, EDGAR collector, and
context API coverage. The dedicated pre-sweep CI step executes the new
materializers together with the SEC 404 and shared attestation authority
contracts, preventing an unrelated later sweep failure from leaving this lane
dark.

The release closes only after hosted CI, merge, origin ancestry, and production
advancement are also conclusive. Those remote facts belong in the shipping PR
and cannot be pre-claimed here.

Adversarial coverage includes mutable-latest refusal, omitted inventory,
missing/tampered/cross-wired pinned members, fabricated missing-404 claims,
clock causality, retained-byte pre-inflate caps, aggregate input caps, mutated
frozen nominals, ambiguous and absent matches, forged v1 identities, candidate
ceilings, and B4 wire-envelope rejection.
