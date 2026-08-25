---
key: MARKET-OS-B1A-IDENTITY-GATE-OWNER-BACKED-CHAIN
question: >
  Is the Market OS B1A identity rider satisfied — can the relation
  "Data OS security SEC:US-XNAS-AAPL ↔ issuer/listing evidence ↔ SEC CIK
  0000320193 ↔ AAPL event_workspace.v1" be proven from existing canonical
  owner-native identity only, without the forbidden dated symbol-directory +
  cik_map compile-time join and without minting new identity authority — or must
  B1A stop with BLOCKED_IDENTITY_BRIDGE?
answer: >
  The gate PASSES for the AAPL golden vertical, via the commission's "exact
  owner-backed chain" clause, instance-scoped and refusal-guarded. The chain:
  security_master.parquet row SEC:US-XNAS-AAPL (active, not superseded,
  issuer_state RESOLVED) → issuer ISS:US-XNAS-AAPL → issuer_master.parquet row
  (cik 0000320193, legal_name Apple Inc., evidence_source sec_company_tickers,
  evidence_snapshot 2026-08-18, era issuer_semantic_correction_v1, receipted,
  zero corrections in the migrations ledgers) → native equality with the event
  workspace's own CIK subject (event_id grammar evt_cik0000320193_*, issuer
  company_id cik:0000320193, filing_key cik). Every link is a committed record
  of a declared canonical identity authority (config/identity_seams.yml lists
  security_master/issuer_master/migrations as master artifacts) read at compile
  time; no ticker→key rendering, no cik_map join, no minting, no generic
  resolver. The B1A compiler re-derives the chain as receipts R1–R9 and refuses
  with typed codes on any failure (superseded tombstone, multi-security CIK,
  migration present, parity mismatch, CIK disagreement); the
  company_identity.v1 PIT-alias leg is corroboration-only (typed DIVERGENT on
  drift, never primary). Inside K1, the earnings evidence recipe stays
  CIK-native (subject cik:0000320193, zero identity_joins — validates against
  the frozen contracts today); the four-owner golden fixture stays REFUSED.
rationale: >
  An independent adversarial analysis (opus, 2026-08-24) executed the proof and
  returned BLOCKED_IDENTITY_BRIDGE on two grounds: no owner supplies a GENERAL
  PIT-correct renderer between the disjoint grammars (company_identity.v1
  xnas:AAPL vs Data OS SEC:US-XNAS-AAPL — naive rendering falsified on 4/5
  drifted master rows, one landing on a live tombstone), and the K1 vocabulary
  carries no issuer_id→cik triple. Both findings are TRUE and are preserved
  here as the dissent — but they answer a wider question than the commission
  asked. The Chairman dispatch explicitly authorizes "an existing canonical
  bridge OR exact owner-backed chain" and explicitly permits narrower
  owner-native-subject K1 recipes "if the top-level AAPL security relation is
  independently proven from existing canonical identity". The master's own
  issuer axis records that relation directly, with SEC-registrant provenance
  and era governance; the falsification cases all die in the compiler's typed
  refusal checks (they are mandatory test fixtures); and the vocabulary-triple
  absence binds K1 recipe declarations, not an out-of-composition proof — the
  same boundary K1's own freeze draws. The analyst's structural findings become
  named repair items for Sol rather than a stop: (1) CIK_LEG_UNOWNED_ACCESS —
  lib.dataos.identity.SecurityIssuerRow omits issuer_cik, so the compiler reads
  the declared master artifacts directly (smallest repair: expose issuer_cik on
  IssuerMaster); (2) NO_GENERAL_NAMESPACE_RENDERER — any universe expansion
  beyond the AAPL golden vertical (B1B/B2) REQUIRES the owner-routed
  ListingAlias→ListingKey renderer + its vocabulary triple as a separately
  frozen contract. The PR ships DRAFT/HOLD-FOR-SOL, so Sol reviews this
  adjudication with the dissent attached before anything deploys.
alternatives:
  - option: Accept BLOCKED_IDENTITY_BRIDGE and return a repair commission to Sol
    why_not: >
      The block rests on requiring a general renderer and an in-K1 triple —
      requirements the commission's own escape-hatch clause relaxes for the
      golden vertical. The instance relation is directly recorded by the
      declared canonical authority; stopping would discard an owner-backed
      proof the dispatch explicitly names as sufficient ("record the proof and
      continue"). The dissent and both structural gaps are preserved for Sol.
  - option: Re-scope B1A's deliverable to a CIK-subject object (analyst OR-5)
    why_not: >
      Delivers no security-keyed product surface — the commission's observable
      mission is the AAPL dossier Decision Spine keyed by canonical security
      identity. The CIK-native shape is retained where it belongs: inside the
      K1 evidence recipe.
  - option: Add a bridge/vocabulary triple to K1 to bless the chain inside composition
    why_not: >
      Forbidden — "Do not modify K1 contracts merely to make B1A green"
      (Chairman dispatch); WS:ALPHA-INTELLIGENCE-INTEGRATION owns those paths;
      the four-owner fixture must stay REFUSED.
evidence:
  - "security_master.parquet SEC:US-XNAS-AAPL row: issuer_id ISS:US-XNAS-AAPL, issuer_state RESOLVED, issuer_cik 0000320193, issuer_evidence_snapshot 2026-08-18, security_state/superseded_by null (read 2026-08-24, byte-identical across branch HEAD 4e7bd95f9045 and macro-main 03471a7)"
  - "issuer_master.parquet ISS:US-XNAS-AAPL row: cik 0000320193, legal_name Apple Inc., n_securities 1, evidence_source sec_company_tickers, evidence_snapshot 2026-08-18, status active, era issuer_semantic_correction_v1; CIK appears in exactly one issuer row"
  - "issuer_migrations (3 rows: FOXA/GOOGL/NWSA) and security_migrations (1 row: VMRK→EQR) contain zero AAPL rows"
  - "live event_workspace.v1 (hash-verified against manifest 2026-08-24): generation 6d56c84a3ac23b8954e59ee7, event evt_cik0000320193_2026q3_results, issuer.company_id cik:0000320193, filing_key.cik 0000320193, sha256 c3b9495028c07e6bf1eb385f520f0b3c57064b84ea430540ba9a0808cd2d14db"
  - "config/identity_seams.yml master block: lib/dataos/identity.py is the master (ADOPT); artifacts list includes issuer_master.parquet + both migrations parquets; issuer axis (V4-D2B1) documents issuer_cik as a master column"
  - "K1 freeze: the forbidden object is the declared consumer route 'dated symbol_directory plus cik_map' (hostile fixture differs from the golden by exactly that one only_via string); provenance of a governed owner column is not the route"
  - "adversarial analyst falsifications preserved as mandatory refusal fixtures: VMRK tombstone (R1), GOOG/GOOGL multi-security CIKs 0001652044/0001754301/0001564708 (R3/R4), drifted tickers ECHO/MRSH/BRK-B (R9 corroboration divergence only)"
  - "PROBE A (analyst-executed): cik-native recipe with zero identity_joins validates against frozen lib/evidence_foundation.py today"
affects:
  - WS:MARKET-OS
  - WS:ALPHA-INTELLIGENCE-INTEGRATION
confidence: medium
reversibility: easy
decided_by: coo-fable-b1a-session-2026-08-24
decided_at: 2026-08-24
---

Adjudication for the Market OS B1A identity rider (Chairman dispatch,
2026-08-24). The independent adversarial verdict (BLOCKED_IDENTITY_BRIDGE) and
this PASS adjudication disagree at the question's altitude, not on the
evidence: both agree R1–R7 hold, both agree no general namespace renderer
exists, both agree the K1 vocabulary has no issuer_id→cik triple, and both
agree a CIK-native K1 recipe validates today. The disagreement — whether the
commission's "exact owner-backed chain" clause admits the master's own issuer
axis as instance proof — is preserved rather than rewritten, and rides to Sol
inside the held B1A PR for final review.

Binding consequences carried into the implementation:

1. The compiler's receipt chain R1–R9 is the proof, re-derived on every
   compile, refusal-first. AAPL passing today is a fact about today's master
   rows, not an assumption baked into code.
2. `identity_proof.disclosures` always prints: CIK_LEG_UNOWNED_ACCESS,
   NO_GENERAL_NAMESPACE_RENDERER, ISSUERMASTER_CURRENT_IDENTITY_ONLY,
   ALIAS_EPOCH_VALID_FROM.
3. Universe expansion beyond the frozen ("AAPL",) allowlist is BLOCKED on the
   owner-routed renderer repair — recorded as the B1B/B2 precondition.
4. K1 contracts, validators, fixtures untouched; the four-owner golden fixture
   remains honestly REFUSED as the adverse contract test.
