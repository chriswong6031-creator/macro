---
key: CS-INSTRUMENT-AND-LIFECYCLE-COMPILERS-NOT-NIGHTLY
claim: >
  scripts/compile_capital_structure_instrument_candidate_terms.py and
  scripts/compile_capital_structure_registration_lifecycles.py exist on main
  and are not invoked by .github/workflows/daily.yml. The nightly CS job
  compiles events and direct document terms only, so candidate instruments and
  registration lifecycles are BUILT_NOT_PROVEN rather than live.
falsifier: >
  Show a daily.yml step running either module, or show production parquet or
  JSON artifacts from those compilers in data/capital_structure/ selected by
  the Git generation. Search daily.yml for
  compile_capital_structure_instrument and compile_capital_structure_registration.
so_what: >
  Do not describe instrument overhang or remaining shelf capacity as live.
  Wave 4 and Wave 5 wire these compilers; do not rewrite them as a second
  lifecycle store. Share-count materialize remains separately gated
  CAPITAL_STRUCTURE_SHARE_COUNT_PUBLICATION_ENABLED default false.
kind: dead_code
verified_at: 2026-08-18
verified_by: >
  Glob scripts/*capital_structure* at 791148b2b7d5 lists both compilers.
  Search of .github/workflows/daily.yml for those two module names is empty.
  daily.yml does run compile_capital_structure_events and
  compile_capital_structure_document_terms. Share-count step is gated on
  vars.CAPITAL_STRUCTURE_SHARE_COUNT_PUBLICATION_ENABLED == true.
scope:
  - macro
  - capital-structure-intelligence
  - scripts/compile_capital_structure_instrument_candidate_terms.py
  - scripts/compile_capital_structure_registration_lifecycles.py
  - .github/workflows/daily.yml
confidence: verified
---

Sophisticated unused infrastructure is not PROVEN_LIVE. The W3 docket already
sequenced candidate terms before capacity. V2 extends that owner rather than
replacing it.
