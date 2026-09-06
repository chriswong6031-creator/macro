---
key: SNI-HK-MULTI-COUNTER-IS-NOT-MULTI-SECURITY
claim: >
  Canonical Data OS listing/security identity is necessary but not sufficient by itself
  for the Alibaba/Tencent reference twins: Alibaba 9988/89988 and Tencent 700/80700 are
  currency counters of one ordinary-share economic security, while Alibaba BABA is a
  distinct ADS security linked by an official 1 ADS = 8 ordinary shares conversion.
  Data OS owns canonical ISS:/SEC:/listing IDs when admitted; SNI must express the
  additional economic-security/counter equivalence as a source-receipted descriptive
  relationship without minting a second canonical identity.
falsifier: >
  Falsified if config/identity_seams.yml and the committed Data OS master it declares
  natively represent economic-security -> venue-listing -> trading-counter relationships
  for these reference names, group 9988 with 89988 and 700 with 80700 as the same economic
  securities, separately bind BABA as an 8-share ADS, and leave no SNI-only relationship
  semantics required.
so_what: >
  SNI-1A must consume Data OS canonical IDs when available, preserve null/unresolved Data
  OS issuer or listing/security state when unavailable, use owner-native/PIT bridges only
  at their accepted precision, and emit an additive relationship record for the
  source-proven counter/conversion facts. It must not fork Data OS identity or silently
  reinterpret company_identity.v1 as the estate-wide master.
kind: architecture
verified_at: 2026-08-28
verified_by: >
  https://github.com/mastermindx-market-intelligence/macro/blob/ed202fbcadce2ca9d0ed85abb3b1178318825653/config/identity_seams.yml ;
  https://github.com/mastermindx-market-intelligence/macro/blob/ed202fbcadce2ca9d0ed85abb3b1178318825653/data/reference/_receipt.json ;
  https://github.com/mastermindx-market-intelligence/macro/blob/ed202fbcadce2ca9d0ed85abb3b1178318825653/contracts/evidence_foundation/README.md ;
  https://www.alibabagroup.com/en-US/faqs-investor-information ;
  https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0812/2026081200296.pdf ;
  https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0827/2026082700758.pdf
scope:
  - macro
  - terminal
  - single-name-intelligence
  - lib/dataos/identity.py
  - config/identity_seams.yml
  - engine/company_intelligence/identity.py
confidence: verified
---

## Boundary

This discovery does not authorize a new identity database, a new canonical issuer/security ID,
or a rewrite of existing Data OS IDs. The lawful first response is an additive relationship view
whose members retain canonical owner IDs when available and typed unresolved state when not. A
future Data OS amendment may absorb the relation only after the canonical owner explicitly accepts
that semantic expansion.
