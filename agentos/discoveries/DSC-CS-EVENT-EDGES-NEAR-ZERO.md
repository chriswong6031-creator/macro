---
key: CS-EVENT-EDGES-NEAR-ZERO
claim: >
  The nightly event compiler produces 600 event versions and 1 event edge in
  the freeze generation, so lifecycle relationships (EFFECT, POS AM, amends,
  withdraws) are not a live graph even when an issuer such as LPTH has 44
  classified EFFECT/POS AM events and 44 review items.
falsifier: >
  Show data/capital_structure/telemetry.json counts.event_edges materially
  greater than 1 on a later Git generation compiled from the same 600-class
  spine, or show LPTH projection records with effectuates/amends edges rather
  than review_count 44. Files: telemetry.json, event_edges.parquet,
  projection.json LPTH record.
so_what: >
  Do not treat event_count as lifecycle state. Wave 4 must wire the existing
  registration-lifecycle compiler and emit real edges. Adding more EDGAR rows
  will not tell which statement is effective or remaining. Global edge_count 1
  is the existence proof that the current page is a filing list.
kind: data
verified_at: 2026-08-18
verified_by: >
  data/capital_structure/telemetry.json counts.event_versions 600,
  counts.event_edges 1, counts.review_queue 425 at as_of
  2026-08-18T07:58:19Z. LPTH projection: event_count 44, classified 44,
  review_count 44, latest POS AM 2026-07-22, 22 EFFECT plus 22 POS AM complete
  submissions in source_manifest.jsonl.
scope:
  - macro
  - capital-structure-intelligence
  - data/capital_structure/event_edges.parquet
  - scripts/compile_capital_structure_events.py
confidence: verified
expires: 2026-11-16
---

Dated production count. Re-read telemetry.json before quoting a later number.
The architectural implication (edges are PARTIAL) holds until Wave 4.
