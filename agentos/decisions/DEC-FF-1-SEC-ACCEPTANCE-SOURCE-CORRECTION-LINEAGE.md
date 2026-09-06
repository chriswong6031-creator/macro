---
key: FF-1-SEC-ACCEPTANCE-SOURCE-CORRECTION-LINEAGE
question: >
  May FF-1 replace a historically admitted SEC acceptance timestamp when a
  later Submissions body reports a different UTC instant?
answer: >
  No replacement or generic equivalence is permitted. FF-1 may append one
  provenance correction only when both immutable source bodies bind the same
  filing identity, every non-time fact is equal, and reinterpreting the earlier
  UTC-labelled clock as an unambiguous America/New_York wallclock yields the
  later explicit UTC instant with exactly a 14,400- or 18,000-second delta.
rationale: >
  ROST accession 0000745732-26-000032 demonstrated a historically observed
  four-hour Eastern-wallclock-as-UTC source defect. Preserving both source
  objects, their hashes, byte counts, exact timestamp text, derivation rule,
  and append-only generation makes the correction reproducible without
  weakening the ordinary historical submissions conflict boundary.
alternatives:
  - option: Treat all differing acceptance timestamps as compatible
    why_not: It conceals source substitutions, non-time changes, DST ambiguity, and actual filing conflicts.
  - option: Rewrite the earlier manifest or source object
    why_not: It destroys immutable evidence and breaks source lineage.
  - option: Retain the current manifest without a ledger
    why_not: It cannot prove why the time changed or bind both SEC source bodies.
evidence:
  - "Slack C0BSBM78V1N/1788700453.316539 and forensic predecessor 1788694011.364409 establish the ROST source fact and bounded rule."
  - "tests/test_fundamental_forensics_broad_sec.py::test_incremental_admits_bound_sec_timezone_correction_lineage_and_counts_fetch"
  - "tests/test_fundamental_forensics_broad_sec.py::test_incremental_refuses_unbound_or_nonmechanical_timezone_correction_without_pointer_move"
affects:
  - WS:FUNDAMENTAL-FORENSICS
  - engine/fundamental_forensics/broad_sec_store.py
  - contracts/fundamental_forensics_broad_sec_issuer_manifest.schema.json
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-09-06
---

## Boundary

This decision is source-only and production-inert. It does not authorize a
live SEC request, a pointer mutation outside a poll's existing issuer CAS,
recovery dispatch, FF-2 work, merge, deployment, or a claim that production
data has been corrected. Existing manifests without a correction ledger retain
their historical identity formula unchanged.
