---
key: FIF-3A1-REUSE-MAP
question: >
  What existing identity, package, parser, and HTTP machinery must
  FIF-3A1 reuse for the AAPL 2025 10-K as-reported statement vertical,
  and what must it newly build?
answer: >
  Reuse Data OS issuer/security/listing identity from
  config/identity_seams.yml (ISS:US-XNAS-AAPL / SEC:US-XNAS-AAPL /
  US-XNAS-AAPL bound to CIK 0000320193). Keep accession
  0000320193-25-000079. Reuse SEC archive URL helpers, the strict
  offline iXBRL parser, metric-registry optional concept aliases, and
  the Forensics private/auth/no-store boundary. Build a minimal
  statement_cell.v1 tree plus presentation/calculation/label linkbase
  walk. Do not mint mmx.issuer.aapl, do not use ticker as durable
  identity, do not make entity_id == CIK a law, do not invent a FIF
  identity registry, do not call SEC at request time, do not write R2,
  and do not mutate attested history.
rationale: >
  Three archaeology passes (identity, package, XBRL) plus main-session
  verification of issuer_master/security_master row 14, B4F
  retain_selected_filing primary-only policy, and absence of any
  presentationArc walker. The binding is unambiguous. No in-repo package
  bytes exist, so FIF-3A1 must capture a bounded real-source fixture
  once, then reconstruct offline. statement_cell.v1 exists only as
  masterplan prose.
alternatives:
  - option: Mint mmx.issuer.aapl to parallel FIP1
    why_not: DEC:FIF-ENTITY-ID-IS-NOT-CIK plus identity_seams.yml forbid a FIF-specific identity.
  - option: Reorder AAPL rows into the 50-metric registry
    why_not: Standardization is optional enrichment, never the row identity.
  - option: Reuse B4F primary-only retention (1 of 93)
    why_not: Statement reconstruction needs schema and linkbases actually referenced.
  - option: Wait for attested-history R2 admission
    why_not: Production issuer service stays NOT_BUILT; the golden fixture is the FIF-3A1 proof.
evidence:
  - "python3 issuer_master/security_master filter cik==0000320193 → one issuer ISS:US-XNAS-AAPL, one security SEC:US-XNAS-AAPL, listing US-XNAS-AAPL, issuer_state RESOLVED"
  - "config/identity_seams.yml master.reader lib/dataos/identity.py"
  - "scripts/seed_fundamental_forensics_attested_history.py retain_selected_filing lines 443-496 primary-only"
  - "research/CALCBENCH_PARITY_WAVE_3B_B4F_FIRST_SEALED_ISSUER_PILOT_2026-08-03.md 93 members / 1 stored"
  - "collectors/sec_filing_parser.py parse_sec_filing_document; LINK namespace defined, no presentationArc walk"
  - "research/MASTERMIND_FINANCIAL_INTELLIGENCE_FABRIC_MASTERPLAN_2026-08-16.md statement_cell.v1"
affects:
  - WS:FINANCIAL-INTELLIGENCE-FABRIC
  - engine/fundamental_forensics/
  - app/forensics.py
  - tests/fixtures/fundamental_forensics/
confidence: high
reversibility: costly
decided_by: coo-fable
decided_at: 2026-08-22
---

Frozen reuse map for FIF-3A1. Binding is BINDING_OK. Golden accession
stays 0000320193-25-000079. Statement graph MUST_BUILD_MINIMAL_STATEMENT_CELL_TREE.
