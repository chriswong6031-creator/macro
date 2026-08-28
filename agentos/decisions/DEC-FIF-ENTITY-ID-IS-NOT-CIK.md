---
key: FIF-ENTITY-ID-IS-NOT-CIK
question: >
  Before freezing financial_intelligence_packet.v1, must Mastermind
  entity_id equal the SEC CIK, and may FIF rewrite source-native SEC
  identity to prove they differ?
answer: >
  No. Canonical issuer identity and source-native filing identity are
  separate dimensions connected by an explicit binding. packet.entity.entity_id
  is Mastermind's issuer ID. packet.entity.cik is the claimed SEC CIK.
  For SEC facts, RawFactLedger SourceIdentity.entity_id and XBRL
  FactContext.entity_identifier remain the filer CIK with scheme
  http://www.sec.gov/CIK. EntityInput.source_entity_id is the bounded
  typed binding from canonical issuer to that source filer. FIF must not
  rewrite occurrence IDs or source-native identity merely to mint a
  Mastermind issuer ID. They may be equal in synthetic FIP1, but equality
  is not contract law. Source Registry is not built in this wave.
rationale: >
  Sol's source review of merged #5837 found that FIF-1R2 accidentally froze
  entity_id == cik because the synthetic fixture used CIK for both. FIF-1R3
  first proved independence by stuffing mmx.issuer.fip1 into source/XBRL
  identity, which is the wrong abstraction: a SEC filing still belongs to
  the SEC filer. The packet may identify Mastermind issuer X while proving
  numbers through SEC filer CIK Y. Isolation keys on the explicit source
  binding, not on rewriting the ledger.
alternatives:
  - option: Keep entity_id == cik as packet-contract law
    why_not: >
      It silently makes an SEC identifier Mastermind's canonical issuer ID.
      The masterplan already anticipates a separate identity plane.
  - option: Prove independence by rewriting SourceIdentity/XBRL context to the Mastermind ID
    why_not: >
      Source-native SEC identity must remain the filer CIK. Rewriting it
      forges the filing rather than binding issuer to filer.
  - option: Build Source Registry in FIF-1R3
    why_not: Sol scoped this wave to an explicit bounded binding, not the identity plane.
  - option: Bind via ticker lookup or string equality
    why_not: Hidden matching is not a typed contract and will not survive ticker changes.
evidence:
  - Sol FIF-1R2 source review 2026-08-18: blocker 3, entity_id == cik
  - Sol FIF-1R3 source review of PR #5889: canonical issuer vs source-native CIK
  - engine/fundamental_forensics/financial_intelligence_packet.py EntityInput.source_entity_id
  - tests/test_fundamental_forensics_financial_intelligence_packet_r3.py::test_canonical_issuer_binds_to_source_native_cik_without_rewriting_raw_identity
affects:
  - WS:FINANCIAL-INTELLIGENCE-FABRIC
  - engine/fundamental_forensics/financial_intelligence_packet.py
  - contracts/financial_intelligence_packet.schema.json
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-18
---

Mastermind canonical issuer identity is separate from source-native filing
identity. For SEC facts, the raw filer and XBRL identifier remain CIK. FIF
carries an explicit canonical→source binding rather than rewriting source
identity. Synthetic FIP1 may still set them equal as a fixture convenience.
