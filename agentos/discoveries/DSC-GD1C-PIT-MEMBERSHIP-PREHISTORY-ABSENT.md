---
key: GD1C-PIT-MEMBERSHIP-PREHISTORY-ABSENT
claim: >
  The tracked Leadership Crack cohort membership lineage begins on 2026-06-14,
  while the four current baskets were curated in 2026 and expose no first-known
  per-member membership clocks spanning the 2016-01-04..2026-07-31 design era;
  their retrospective added dates therefore cannot establish a PIT cohort.
falsifier: >
  git log --reverse --format='%H|%cI|%s' -- data/baskets/membership.json plus
  jq reads of the four current basket member records would disprove this claim
  if they showed a tracked pre-2016 lineage or date-effective available_at /
  observed_at membership receipts covering additions, removals, renames and
  delistings across the design era.
so_what: >
  Any historical leadership_crack.v1 run using the current membership file must
  remain labeled def_current_cf. Do not use it for a GD-H1/GD-H2 promotion or a
  GD-5 build. Recover a first-known membership lineage, then freeze a new
  preregistration before rerunning a primary PIT test.
kind: data
verified_at: 2026-08-19
verified_by: >
  git log --reverse --format='%H|%cI|%s' -- data/baskets/membership.json printed
  29721d07084c0332e1c2b5387a32addc1863c395 at 2026-06-14 as the earliest
  tracked receipt; jq of ai_semiconductors, ai_infra, memory_storage and
  semicap_equipment showed 2026 curation with retrospective added fields and no
  per-member availability clock.
scope:
  - macro
  - data/baskets/membership.json
  - engine/leadership_crack.py
  - research/grey_deer/gd1c/
  - WS:GREY-DEER-RISK-INTELLIGENCE
confidence: verified
---

# GD-1C PIT membership prehistory is absent

The current 42-name union is usable only for the explicitly labeled
`def_current_cf` lane. Price depth does not repair missing membership identity.
The current definition also retains current-member denominator behavior for
pre-IPO missing rows, another reason not to market the reconstruction as an
emitted historical organ.

Evidence and the minimum lawful substitute are content-addressed in
`research/grey_deer/gd1c/GD1C_RECONSTRUCTION_MANIFEST.json` and adjudicated in
`research/grey_deer/gd1c/GD1C_RESULTS_AND_ADJUDICATION.md`.
