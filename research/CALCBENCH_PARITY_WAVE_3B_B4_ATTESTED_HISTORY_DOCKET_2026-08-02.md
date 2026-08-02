# Calcbench Parity — Wave 3B-B4A Attested History Overlay

**Canonical implementation handoff for Wave 3B-B4A**

**Date:** 2026-08-02

**Status:** implementation complete; focused and CI-reachability gates passed

## Outcome

Wave 3B-B4A adds an immutable `ffqsv2_` overlay above one already-published v1
`ffqs_` query snapshot. It does not mutate, upgrade, or relabel the v1 receipt.
Its only positive claim is deliberately narrow:

> An exact raw `sec-companyfacts` occurrence selected by a frozen v1 query leaf
> was reproduced by the stored `CompanyFactsLedgerConversion` companion and
> corresponded to one exact B3 `ffatt_` Company Facts match whose selected SEC
> member source was freshly replayed during preparation and renewed again in a
> fail-closed preflight immediately before publication.

Coverage is derived for every v1 root cell from its selected raw-fact leaves. A
root with one supported leaf and one uncovered leaf is `partially_attested`,
never broadly “verified.” No snapshot-wide badge may erase that partiality.

```text
ffqs_ frozen root
  -> exact selected raw leaf occurrence_id
  -> full CompanyFactsLedgerConversion companion replay
  -> explicit occurrence binding
  -> exact ffatt_ / ffatt_match_ correspondence
  -> B3 selected-member source replay
```

There is no ticker, CIK, accession, metric-label, value-proximity, or current
endpoint fallback.

## Implemented surface

The implementation is in
`engine/fundamental_forensics/attested_query_snapshots.py` and exposes strict
prepare, publish, load, stored-self-verification, and fresh-source-verification
paths.

The schema is `fundamental_forensics.attested_query_snapshot/v2`; the storage
prefix is `fundamental_forensics/attested-query-snapshots/v2`; identity is
`ffqsv2_<sha256>` over the canonical manifest body excluding `snapshot_id`.
The manifest binds:

- the exact base `ffqs_` ID, query hash, manifest key, manifest digest/length,
  and all four v1 object witnesses;
- policy `ffqsv2_exact_join/v1` and its fixed fingerprint;
- the complete Company Facts conversion receipt;
- sorted B3 attestation projections;
- mechanically derived root-coverage totals;
- query, operator-observation, and publication clocks;
- fixed false nonclaims; and
- four ordered content-addressed v2 object witnesses.

## Exact four-artifact lifecycle

Each prepared overlay contains exactly four canonical JSON artifacts:

1. `attestations_json` — the complete, sorted canonical B3 `ffatt_` records;
2. `companyfacts_conversion_json` — the full conversion ledger, conversion
   occurrence companions, Submissions source witnesses, and conversion receipt;
3. `bindings_json` — sorted exact occurrence -> `ffatt_` -> `ffatt_match_`
   choices plus the sealed Company Facts projection; and
4. `coverage_json` — one complete, canonical root-coverage row for every v1
   matrix root.

The manifest is a fifth immutable storage object but is not one of the four
evidence roles. All reads use `StrictBoundedReadStore`; legacy unbounded strict
reads are not part of this lane. Object length, digest, content type, role
order, combined byte budget, JSON depth/node/text bounds, and canonical bytes
are verified fail closed.

`publish_attested_query_snapshot` requires the exact external
`attestation_materials` and `companyfacts_conversion` again; a caller-constructed
`PreparedAttestedQuerySnapshot` is never publication authority. Before any
write—even an otherwise orphaned content-addressed object—the publisher:

1. bounded-loads and fully verifies the frozen v1 base;
2. renews every supplied B3 source through the exact package, extraction,
   pinned authority, and Company Facts source paths;
3. compares the resulting complete B3 records with `attestations_json`;
4. reserializes and compares the full external conversion with
   `companyfacts_conversion_json` and its manifest receipt;
5. decodes and reproduces every exact occurrence/conversion/B3 match join;
6. recomputes all per-root coverage rows and summary counts; and
7. revalidates the base-query and `operator_verification_observed_at` causal
   clock bindings.

Only after that preflight succeeds does publish write or confirm each immutable
object, read it back, write and read back the immutable manifest, reconstruct
the entire overlay, and advance the v2 pointer last. Publication is idempotent
for the same immutable snapshot and refuses an older or equal-clock different
snapshot that would rewind latest.

The independent pointer schema is
`fundamental_forensics.attested_query_snapshot_pointer/v2`. It binds the v2
snapshot ID, manifest key, base v1 snapshot ID, and publication time. It never
reads or advances `fundamental_forensics/query-snapshots/v1/latest.json`. The
publication contract remains `single_writer_operator_only`: the process lock is
not a distributed lease or CAS primitive.

## Frozen v1 and full conversion replay

Preparation accepts one explicit v1 snapshot ID. Before building the overlay it
bounded-reads the v1 manifest and its four named objects, constructs a frozen
replay store, and runs the existing v1 `verify_query_snapshot` path. It does not
trust the mutable v1 latest pointer and does not rerun the query against current
inputs.

The Company Facts bridge is a concrete, fully validated
`CompanyFactsLedgerConversion`, not a loose receipt projection. The stored
conversion artifact is decoded back into:

- a complete `RawFactLedger`;
- every `CompanyFactsLedgerOccurrence` companion;
- every `SubmissionSourceWitness`; and
- the exact `CompanyFactsLedgerReceipt`.

The conversion's constructor invariants and canonical serialization are rerun
on load. The manifest receipt must equal the payload receipt exactly. A forged
companion index, ledger occurrence, source witness, count, digest, clock, or
receipt cannot be used to publish a pointer.

## Exact leaf binding

For every supplied `AttestedOccurrenceBinding`, B4A requires all of the
following:

1. the occurrence ID names an exact `selected_raw_fact` in a node of the frozen
   v1 matrix and that fact byte-semantically equals the occurrence in the frozen
   v1 ledger;
2. the same occurrence ID names exactly one occurrence companion in the full
   supplied conversion;
3. the selected occurrence is `sec-companyfacts`, keeps
   `dimensions_known=false`, and matches the companion taxonomy, concept,
   period, value, source body, CIK, and accession;
4. the conversion receipt capture, manifest, and CIK exactly bind the supplied
   B3 record;
5. the explicit `ffatt_` and `ffatt_match_` IDs name one stored positive B3
   Company Facts correspondence with exact taxonomy, concept, unit, entry index,
   period, CIK, accession, and canonical decimal value; and
6. the exact B3 package, extraction, pinned source authority, and optional
   Company Facts paths pass `verify_filing_attestation_source` before their
   attestation record is admitted.

Bindings are non-empty, immutable, sorted, and one-to-one. Reusing a selected
occurrence or a B3 match is rejected. Every stored attestation must support at
least one explicit binding. Missing bindings remain visible in coverage; the
builder never guesses them.

## Root coverage contract

Every frozen v1 matrix root appears once in `coverage_json`. Its row contains
the sorted selected leaf occurrence IDs, eligible leaf IDs, attested occurrence
IDs, and one state from this closed catalog:

| Root state | Exact derivation |
| --- | --- |
| `all_leaves_attested` | The root has selected leaves, every leaf is an eligible dimensions-unknown `sec-companyfacts` occurrence, and every leaf has an admitted binding. |
| `partially_attested` | The root has at least one admitted binding but not every selected leaf is both eligible and attested. |
| `not_attested` | The root has at least one eligible selected leaf and none is bound. |
| `not_evaluable` | The root has no selected leaf, or none of its selected leaves is eligible for this exact bridge. |

The manifest summary is recomputed from those rows and uses
`coverage_scope=selected_raw_fact_leaves_only` and
`positive_label=B3_selected_member_companyfacts_row_correspondence_only`.
It reports root counts only; zero coverage cannot become `100%`, and one
positive leaf cannot promote a partial root or the whole query.

## Clock and timestamp honesty

The manifest preserves the v1 query's `source_snapshot_at`, `recorded_at`,
`computed_at`, and `published_at`, then adds:

- `operator_verification_observed_at` — an explicit operator-provided UTC
  observation recorded after the base query, every referenced B3 clock, every
  referenced Company Facts capture/record clock, and every conversion clock;
  it is the only accepted verification-clock input and field name; and
- `published_at` — explicit canonical UTC that cannot precede the operator
  observation.

These are causal application clocks, not proof from a trusted clock. The
canonical artifact permanently carries
`trusted_timestamp_authority=false` and
`verification_time_cryptographically_attested=false`. Therefore
`operator_verification_observed_at` means “the operator says this replay was
observed then,” not “an external authority proves it happened then.” It cannot
backdate attestation to the v1 query's as-of time.

## Load versus renewable source verification

`load_attested_query_snapshot` and `verify_attested_query_snapshot` bounded-read
and reconstruct the v2 manifest, four artifacts, complete conversion, bindings,
coverage, and frozen v1 replay. This establishes canonical stored
self-consistency only.

`verify_attested_query_snapshot_source` is the renewable authority path. It
requires exact external `AttestationMaterial` values and an exact external
`CompanyFactsLedgerConversion`; freshly reruns every B3 source replay, compares
the supplied complete B3 records and full conversion to storage, rebuilds
the exact joins, and reproduces every coverage row. Stored self-consistency is
never described as renewed SEC/source presence.

## Fixed nonclaims

All canonical nonclaim flags remain false. They explicitly deny:

- filing, query-snapshot, Company Facts capture, filing-source-snapshot, or SEC
  universe completeness;
- full taxonomy, relationship, or calculation validation;
- fact-level XBRL identity, known dimensions, signature verification, or
  Company Facts completeness;
- PIT/contemporaneous verification, current source availability/freshness, a
  trusted timestamp authority, or cryptographically attested verification time;
- accounting or restatement correctness and audit-opinion authority; and
- trading, Prophet, Neural Web, investment, or legal authority.

The permitted positive language is **B3 selected-member Company Facts row
correspondence, observed post hoc for the named selected leaf**. It is not
“verified financial history,” “filing validated,” “audited,” or “SEC-certified.”

## Implemented acceptance evidence

`tests/test_fundamental_forensics_attested_query_snapshots.py` currently has
eleven focused adversarial tests covering:

- a real pinned B3/Company Facts conversion path through prepare, publish,
  publication-time renewal, independent pointer load, and later renewable
  source verification;
- duplicate/cross-wired occurrence and match rejection;
- stored object tamper detection and clock-rewind rejection;
- all four exact root states and frozen nonclaims;
- real formula roots with simultaneously all-attested, partially-attested,
  not-attested, and not-evaluable persisted coverage, followed by exact source
  renewal;
- Company Facts source tampering that makes both a new prepare and later source
  verification fail closed;
- conversion-receipt tampering, missing companions, foreign leaves, and unused
  attestation materials;
- self-consistent forged companions that rewrite the selected raw occurrence's
  period or unit;
- mandatory publication-time source replay and caller mutation of a prepared
  snapshot identity during that replay, without an orphan manifest or pointer;
- bounded-only preflight, pointer-last publication, idempotence, monotonicity,
  manifest-write failure, and independent latest resolution;
- missing, corrupt, noncanonical, cross-wired, rejected-write, and corrupted
  read-back v2 pointer behavior, while proving the v1 pointer remains untouched;
- hostile nominal/JSON/depth/float/duplicate-key rejection; and
- forged full-conversion payload rejection during publication preflight, before
  any v2 pointer can be created.

Local release evidence on 2026-08-02:

- **15 passed** in the focused B4A suite; and
- **11 passed** in `tests/test_ci_pack.py` after the suite was added to CI.

The suite is named in `engine-render-guards` in
`.github/ci/legacy-jobs.yml` and is explicitly path-gated in
`.github/workflows/ci.yml`, including test-only changes. These are local
pre-merge gates; merge, hosted CI, and production advancement require the
repository ship loop and are not claimed by this docket.

## Explicitly excluded from B4A

B4A does not add a router, API endpoint, scheduled operator, distributed
publisher, UI component, premium gate, dashboard card, notification, score,
screen, search result, or automated Prophet/Neural Web/trading decision. It does
include the bounded private-store publisher and independent v2 latest pointer
described above; those are internal artifact plumbing, not a served product.

The next lane may add a read-only Verified History API and an honest per-root
provenance waterfall. Any such surface must consume `ffqsv2_`, expose partial
coverage and the unsigned post-hoc clock, and must never manufacture verification
from a client request or a green badge.
