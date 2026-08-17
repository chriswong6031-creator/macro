---
key: D0R-RED-TEAM-ADJUDICATION-2026-08-17
question: >
  After Sol's PR #5814 review (PASS AS CHECKPOINT; D0R not accepted; D1 not
  authorized), which blocking items are closed in this D0R closure packet versus
  carried into D1+, and do the twelve governing red-team questions still block
  acceptance?
answer: >
  Close in this packet: Workstream I D1–D4 handoffs; five remaining runtime
  lineages plus the existing P00032 lineage; B/E verification receipts; D
  VERIFIED_CASE vs RESEARCH_CANDIDATE   labeling (6 VERIFIED_CASE / 61 RESEARCH_CANDIDATE, not 60 fake
  primaries); G Stock Identity validation and SPR demotion; H D1/D2 target
  HTML compositions; this adjudication. Carry to D1: Radar rehydrate, filmstrip
  copy, agency facets, stale banner, typed Budget/SAM UI (rescue only). Carry
  past D1: P-1/R-1 collection, SAM collector, GE/BWXT reviewed paths, IRDM
  earnings-packet join, Gate 5 PIT studies. D0R remains unaccepted until Sol
  reviews this packet. D1 stays unauthorized.
rationale: >
  The governing D0R contract requires I1–I4 filenames and A2's six lineages
  before closure. Sol's review listed the same blockers. Inventing 60 primary
  sources would fail the citation standard; labeling 6 VERIFIED_CASE and 61
  RESEARCH_CANDIDATE is the honest Gate 5 move. SPR as a live issuer is false
  against Stock Identity and the 2025-12-08 8-Ks. Product rescue is a vertical
  slice; collectors are a different wave.
alternatives:
  - option: Absorb qledger #5816 or fold #5424 into this PR
    why_not: Operator froze isolation; defense20-v1 is not live.
  - option: Start D1 in the same PR because the bugs are known
    why_not: D1 is unauthorized until D0R acceptance. The checkpoint PR stays research/design.
  - option: Mark Gate 5 closed by treating all 64 rows as verified
    why_not: Sol forbade placeholder primaries. That would be a fake close.
  - option: Build P-1/SAM in D1 because Budget/SAM are broken
    why_not: Frozen D1 boundary is typed failure + Radar/filmstrip/agency/banner rescue.
evidence:
  - "https://github.com/mastermindx-market-intelligence/macro/pull/5814 Sol reviews 4948701189 / 4948742089"
  - "research/defense_intelligence/D0R_RUNTIME_LINEAGES.md"
  - "research/defense_intelligence/DEFENSE_D1_PRODUCTION_TRUTH_AND_PRODUCT_RESCUE_HANDOFF.md"
  - "git show HEAD:data/stock_identity/partition/universe_snapshot_v1.parquet — SPR absent; IRDM tape_ended false"
  - "SEC 8-K https://www.sec.gov/Archives/edgar/data/12927/000162828025055825/ba-20251208.htm"
  - "HEAD workspace.json 35 deobligations; mapping_backlog 21; latest.json opportunities unavailable"
affects:
  - WS:DEFENSE-PROCUREMENT-V3
  - research/defense_intelligence/**
  - templates/government_revenue.html.j2
  - templates/government-revenue-candidate-radar.js
confidence: high
reversibility: easy
decided_by: session-d0r-closure
decided_at: 2026-08-17
review_by: 2026-08-18
---

Sol checkpoint stands. This decision records the red-team adjudication the
evidence index also tables. It does not accept D0R and does not authorize D1.
