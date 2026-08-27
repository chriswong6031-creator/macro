---
key: K2C-SECURITY-BINDING-IS-OWNER-NATIVE-CUSIP
question: >
  When the K2-C institutional adapter binds a 13F holdings row to a "requested
  canonical security identity", what identity plane is lawful, given that the
  repo has no authoritative CUSIP→Data OS security_id resolution surface?
answer: >
  The pilot's requested canonical security identity is the owner-native CUSIP,
  which is already a first-class K1 subject_key_type. The adapter proves
  row.cusip equals the requested CUSIP exactly (grammar ^[0-9A-Z]{9}$) inside a
  manifest-bound catalog row, and carries the Data OS axis as a typed unresolved
  field (dataos_security_id null, dataos_resolution
  "unresolved_no_authoritative_cusip_plane"). No CUSIP alias space is fabricated
  and no display-tier map is promoted to identity authority.
rationale: >
  Verified at pickup (main 13b9660f): the security master's vendor-alias spaces
  are yahoo/membership/ledger/yahoo_fetch/store/theme_graph_native — no cusip
  space; engine/entity_resolver.resolve_cusip is documented context-only;
  engine/institutional_census/aggregate.load_ticker_map is documented
  display-only. The commission forbids creating a second identity plane and
  forbids new Data OS/Stock Identity planes, so the only lawful positive path is
  the owner-native identifier that K1's vocabulary already recognizes as a
  subject key type ("cusip"). Typed unresolved on the Data OS axis keeps the gap
  visible instead of silently bridged, and keeps every K2-C receipt honest about
  what was and was not proven.
alternatives:
  - option: Add a "cusip" vendor space to the security master within the K2-C wave
    why_not: >
      That is a Data OS identity-plane widening explicitly out of K2-C scope; it
      also needs its own rights/lineage design (CUSIP redistribution rights,
      reuse-after-delisting) and belongs to a Data OS commission.
  - option: Resolve via entity_resolver.resolve_cusip or aggregate.load_ticker_map
    why_not: >
      Both are documented context/display-tier; promoting them to K1-grade
      identity authority violates the display-vs-authority epistemics law and
      would silently rewrite history through timeless current-name maps.
  - option: Return the wave blocked on the missing identity plane
    why_not: >
      The mission is achievable without it: K1 already admits cusip subjects, the
      13F owner's native security identity IS the CUSIP, and the Data OS gap is
      carried as typed unresolved rather than being load-bearing.
evidence:
  - "scripts/build_security_master.py vendor constants: yahoo, membership, ledger, yahoo_fetch, store, theme_graph_native — no cusip space."
  - "engine/entity_resolver.py module docstring: LEAF · CONTEXT-ONLY; layer-5 CUSIP map promoted from smart_money."
  - "engine/institutional_census/aggregate.py load_ticker_map: bounded OpenFIGI CUSIP map used only for display resolution."
  - "contracts/evidence_foundation/vocabulary.v1.json subject_key_types includes cusip and institutional_catalog_generation_id."
  - "Design freeze: research/alpha_intelligence/K2C_INSTITUTIONAL_ADAPTER_PILOT_2026-08-27.md §3."
affects:
  - "WS:ALPHA-INTELLIGENCE-INTEGRATION"
  - "research/alpha_intelligence/K2C_INSTITUTIONAL_ADAPTER_PILOT_2026-08-27.md"
confidence: high
reversibility: easy
decided_by: fable
decided_at: 2026-08-27
---

## Supersession path

A future Data OS commission that ships a rights-clean, time-scoped CUSIP alias
space in the security master supersedes the typed-unresolved carriage here: the
adapter's dataos_resolution value "alias_table_resolved" is already reserved for
that world, so K2-C receipts upgrade without a contract break. Until then, any
session tempted to "just map" a CUSIP through a display-tier surface must treat
this record as the refusal.
