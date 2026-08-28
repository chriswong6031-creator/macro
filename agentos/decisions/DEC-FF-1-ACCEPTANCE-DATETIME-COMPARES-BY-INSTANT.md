---
key: FF-1-ACCEPTANCE-DATETIME-COMPARES-BY-INSTANT
question: >
  When two canonical duplicate filing rows have every non-time fact equal but
  retain different acceptance_datetime text, may FF-1R reconcile them without
  rewriting either SEC representation?
answer: >
  Yes, but only at canonical duplicate reconciliation and only for two valid
  string acceptance_datetime values whose existing frozen _iso_order_key values
  are equal. Exact equality remains first; every other field and malformed or
  distinct acceptance time remains a fail-closed conflict. The first-bound text
  remains the retained evidence representation.
rationale: >
  The ANGO source adjudication established that 2026-07-14T19:42:40Z and
  2026-07-14T19:42:40.000Z are equal instants under the existing lossless
  comparison key, while the raw bytes and their source identity must not be
  normalized or rewritten. Treating this representational difference as a
  substantive contradiction prevented a lawful bounded recovery outcome;
  treating every acceptance_datetime as compatible would conceal real source
  disagreements. One helper used by _merge_filing_rows preserves both limits,
  and _assert_no_duplicate_filing_conflicts inherits the rule by delegation.
alternatives:
  - option: Require byte-identical acceptance_datetime text
    why_not: >
      It treats equivalent UTC representations as contradictory despite the
      existing frozen order key proving they are the same instant.
  - option: Normalize every stored acceptance_datetime before merging
    why_not: >
      It rewrites immutable source evidence, loses the first-bound SEC text,
      and widens the change beyond duplicate compatibility.
  - option: Accept every differing acceptance_datetime
    why_not: >
      It would conceal malformed values and actual instant disagreements that
      the canonical duplicate guard must continue to reject.
evidence:
  - "DSC:FF-1R-ANGO-ACCEPTANCE-DATETIME-CONFLICT preserves the production conflict and frozen no-dispatch state."
  - "engine/fundamental_forensics/broad_sec_store.py:_iso_order_key preserves raw fractions while trailing zeroes compare equal."
  - "tests/test_fundamental_forensics_broad_sec.py::test_duplicate_filing_acceptance_datetime_compares_by_instant_only"
  - "tests/test_fundamental_forensics_broad_sec.py::test_ff1r_ango_timestamp_representation_reconciles_without_rewriting_legacy_evidence"
affects:
  - WS:FUNDAMENTAL-FORENSICS
  - engine/fundamental_forensics/broad_sec_store.py
  - tests/test_fundamental_forensics_broad_sec.py
confidence: high
reversibility: easy
decided_by: ceo-sol
decided_at: 2026-08-24
---

## Boundary

This is a source-comparison decision only. It does not declare recovery
commissioned, production-proven, dispatched, advanced, merged, or shipped.
The `await source adjudication` clause in
`DSC:FF-1R-ANGO-ACCEPTANCE-DATETIME-CONFLICT` is now satisfied only for this
representational-equivalence handling: valid UTC spellings of the same instant
may reconcile without rewriting evidence. The original production failure and
its frozen no-dispatch state remain true; this decision does not adjudicate any
other source disagreement.
The production recovery state remains frozen at plan
`e252f0a85c193323be128b6de2762c522a0ab86b74d8a2ed15a1f3014695e5a4`,
cursor/completed `0`, backlog `2,571`, and null last-successful recovery receipt.
Previous-quarter reconciliation remains SPEC_ONLY / NOT_BUILT and FF-2 remains
FORBIDDEN / NOT_STARTED.
