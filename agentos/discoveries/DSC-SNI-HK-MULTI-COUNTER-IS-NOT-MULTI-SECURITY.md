---
key: SNI-HK-MULTI-COUNTER-IS-NOT-MULTI-SECURITY
claim: >
  The current ticker/listing identity representation is insufficient by itself for the
  Alibaba/Tencent reference twins: Alibaba 9988/89988 and Tencent 700/80700 are currency
  counters of one ordinary-share economic security, while Alibaba BABA is a distinct ADS
  security linked by an official 1 ADS = 8 ordinary shares conversion. A model that treats
  every stock code as an unrelated economic security corrupts issuer facts, cross-counter
  comparison, share units and cross-listing response analysis.
falsifier: >
  Show a current accepted canonical identity contract on Macro main that natively represents
  issuer -> economic security -> venue listing -> trading counter, binds 9988 with 89988 and
  700 with 80700 as the same economic securities, and separately binds BABA as an 8-share ADS
  without requiring an SNI relationship overlay.
so_what: >
  SNI-1 must emit a derived counter/security relationship projection over the canonical
  Company Intelligence identity owner. It must not fork identity or silently redefine
  company_identity.v1. A future owner amendment may absorb the relationship only after the
  reference contract proves the need.
kind: architecture
verified_at: 2026-08-28
verified_by: >
  https://github.com/mastermindx-market-intelligence/macro/blob/0863c549f728c718bbe82cc883e89843c0eb710a/engine/company_intelligence/identity.py ;
  https://github.com/mastermindx-market-intelligence/macro/blob/0863c549f728c718bbe82cc883e89843c0eb710a/engine/hk_adr_bridge.py ;
  https://www.alibabagroup.com/en-US/faqs-investor-information ;
  https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0812/2026081200296.pdf ;
  https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0827/2026082700758.pdf
scope:
  - macro
  - terminal
  - single-name-intelligence
  - engine/company_intelligence/identity.py
  - engine/hk_adr_bridge.py
confidence: verified
---

## Boundary

This discovery does not authorize a new identity database or a rewrite of existing IDs. The
first lawful response is an additive, source-receipted relationship view in the SNI reference
contract, with ambiguous mappings refusing rather than guessing.