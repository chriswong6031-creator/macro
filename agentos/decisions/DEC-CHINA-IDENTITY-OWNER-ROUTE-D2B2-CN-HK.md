---
key: CHINA-IDENTITY-OWNER-ROUTE-D2B2-CN-HK
question: >
  The China Alpha wave pr0d (China exact identity extension) stopped at a two-owner
  collision: its commission pointed the builder at the WS:STOCK-IDENTITY /
  engine/stock_identity/ seam, while canonical identity expansion (D2B2, the
  1,868-object NOT_IN_MASTER queue) is an incumbent program under
  WS:PROPHET-US-V4-RECOVERY wave V4-D2 on the Data OS master, with Sol's 2026-08-18
  Gate-1 amendment already ruling identity = lib/dataos, NOT stock_identity, and
  D2B2 explicitly NOT authorized pending per-child Sol review. Who implements
  China/HK canonical identity expansion, and what does the China lane keep?
answer: >
  OWNER-ROUTE, DO NOT REBUILD (Sol adjudication 2026-08-20). The China product
  outcome is still required, but the China lane is not authorized to implement
  canonical identity expansion itself. The WS:STOCK-IDENTITY / engine/stock_identity/
  builder pointer in the PR-0D commission was a mistaken seam pointer. Canonical
  identity authority is the Data OS master (lib/dataos/identity.py + the canonical
  builder scripts/build_security_master.py + data/reference receipts), with GMI
  consuming it through the existing gmi.identity_resolution/v1 projection (D2A).
  Sol authorizes exactly ONE bounded child: D2B2-CN-HK under
  WS:PROPHET-US-V4-RECOVERY / Data OS identity authority — China/HK objects from
  lawful primary sources only; the full D2B2 US/Canada backlog remains
  unauthorized. Frozen contract:
  research/prophet_v4/d2/D2B2_CN_HK_FROZEN_CONTRACT_2026-08-20.md. China wave
  pr0d stays in_progress encoded OWNER_ROUTED_WAIT / consumer-verifier: it adopts
  the owner result by reference at D2B2-CN-HK merge (BUILT_NOT_PROVEN) and flips
  to done only after a natural production nightly demonstrates real China/HK
  nodes flowing source -> canonical master -> GMI projection, with run ID and
  measured resolution delta recorded. Durable receipts prefer immutable merge
  SHAs, never mutable branch-head SHAs.
rationale: >
  Extending the canonical master for China/HK IS the cn/hk slice of D2B2 — the
  work Sol explicitly gated behind per-child review under the incumbent V4 D2
  program. A China-lane build on the mistaken stock_identity seam would have
  created a rival identity surface against the Data OS master (the exact
  duplicate-plane failure the masterplan §15.5 DNR-class boundary forbids), and a
  China-lane build on the correct seam would have raced the incumbent owner's
  expansion queue without its issuer law, supersession fence, or review gate. The
  collision resolves by adopting the canonical plane through its owner: one
  bounded, source-scoped child under the program that owns the master, with the
  China lane as consumer-verifier of the outcome it needs.
alternatives:
  - option: China lane builds the extension itself on the Data OS seam
    why_not: that is D2B2's cn/hk slice — Sol explicitly gated D2B2 behind per-child review under the incumbent owner; a parallel build races the owner's queue and evidence law
  - option: Adopt the WS:STOCK-IDENTITY / engine/stock_identity/ spine as the commission wrote
    why_not: Sol's 2026-08-18 Gate-1 amendment already ruled exact issuer/security/listing identity = the Data OS spine (lib/dataos), NOT stock_identity; building there mints a rival identity surface
  - option: Authorize the full D2B2 backlog (US + Canada + CN/HK) in one wave
    why_not: Sol bounded the authorization to the China/HK slice only; US/Canada expansion remains unauthorized pending its own review
affects:
  - "WS:CHINA-ALPHA-INTELLIGENCE"
  - "WS:PROPHET-US-V4-RECOVERY"
  - research/china_alpha_intelligence/commissions/PR-0D_china_identity_extension.md
  - research/CHINA_ALPHA_INTELLIGENCE_MASTERPLAN.md
  - research/prophet_v4/d2/D2B2_CN_HK_FROZEN_CONTRACT_2026-08-20.md
evidence:
  - "Sol PR-0D authority adjudication, operator relay 2026-08-20 (this session): OWNER-ROUTE, DO NOT REBUILD; exactly one bounded child D2B2-CN-HK; US/Canada unauthorized"
  - "WS:PROPHET-US-V4-RECOVERY d2 wave record: Sol 2026-08-18 amendment — identity = lib/dataos/identity.py, NOT stock_identity; D2B2 (1,868 NOT_IN_MASTER) NOT authorized yet, Sol reviews per child"
  - "PR-0D builder collision packet (China Alpha activation session 2026-08-20): builder stopped at the D2B2 escalation instead of improvising across the identity owner boundary"
  - "research/prophet_v4/d2/D2A_FROZEN_CONTRACT_2026-08-18.md (#5894 gmi.identity_resolution/v1 seam) + D2B1_FROZEN_CONTRACT_2026-08-19.md (#5965 issuer law) + D2B1_R1_FROZEN_CONTRACT_2026-08-20.md (#6082 supersession fence)"
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-20
---

Scope note: this record corrects an authority seam and routes one bounded child;
it does not rewrite the China Alpha architecture freeze
(`DEC:CHINA-ALPHA-INTELLIGENCE-ARCHITECTURE-FREEZE`) or the V4 D2 recut. The
China-lane requirement (China/HK nodes resolve exactly or refuse typed; GMI
bridge measured before/after) is unchanged — only its implementation home moved
to the canonical owner.
