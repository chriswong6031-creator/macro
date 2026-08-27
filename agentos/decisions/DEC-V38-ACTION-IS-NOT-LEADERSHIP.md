---
schema: agentos.decision.v1
key: V38-ACTION-IS-NOT-LEADERSHIP
question: >
  Should Stock Dashboard V3.7 continue to hide the owner-native group-action
  workflow inside Expanded Leadership and let Leadership carry both trend-rank
  and action semantics, or should Mastermind separate the two user jobs in V3.8?
answer: >
  Separate them. V3.8 restores a compact owner-native What to Act On Now surface
  at rest above Prophet and reserves Leadership & Rotation for explicitly named
  trend/relative-strength/theme ranking. Numeric ranks require a canonical rank
  owner and visible rank basis; lane traversal order is never rank. The existing
  V3.7 Prophet, Evidence, Research, quote/no-LIVE and authority laws remain
  controlling. V3.7 production proof remains historically valid; V3.8 is the next
  product-completeness target, not a rollback.
rationale: >
  Chairman production review exposed a high-frequency customer-job regression.
  HK V3.7 is semantically honest but visually collapses orthogonal axes: its
  01..08 values come from the owner Sector Rotation RS-vs-HSI rank while the
  colored stance comes from the owner Act-Now cycle/entry board. Thus RS #1 can
  correctly be Reduce/Avoid while a lower-RS sector is Buy Now. Hiding the direct
  action map in Expand Leadership forces users to infer that distinction instead
  of seeing both truths. Canada also reveals a related presentation-authority
  problem: sector `rank` in the V3.7 composer is assigned by Act-Now lane traversal
  (`out.length + 1`), not by a sector-rank owner. The old China What to Act On Now
  workflow remains valuable but is too dense; the correct response is to compress
  its rows, not remove the workflow.
alternatives:
  - option: Keep V3.7 and add explanatory copy to Sector Leadership
    why_not: >
      Explaining a conflated information architecture does not restore the buried
      high-frequency action job. It also leaves Canada presentation-owned sector
      numbering intact.
  - option: Restore the old giant China/US/HK action boards verbatim
    why_not: >
      Those boards solve the right job but carry too much at-rest detail. V3.8
      restores the job in a capped, low-density component while moving diagnostics
      and performance evidence into Leadership expansion / group research.
  - option: Derive What to Act On Now from Leadership rank
    why_not: >
      Trend leadership and entry/action timing are independent owner axes. Deriving
      one from the other would create a new presentation-owned recommendation rule.
evidence:
  - "HK current source: templates/hk.html.j2 #sector-rotation describes sectors as ranked by relative strength vs HSI over 20/60d; #act-now publishes Buy Now/In Favour/Bottoming Watch/Reduce-Avoid separately."
  - "HK V3.7 source: site/hk-stock-v36.js collectRotationRanks() reads the owner rank while collectLaneSectors() reads Act-Now stance; collectSectors() joins them; renderLeading() explicitly notes current rank-1 Healthcare can be Reduce/Avoid."
  - "Canada V3.7 source: site/canada-stock-v36.js collectSectors() walks LANE_DEFS and assigns rank=out.length+1; canadabasketdata/sector_pulse_canada.json separately publishes real ranked Themes."
  - "Chairman 2026-08-26 product review: What to Act On Now is a fan-favorite immediate focus workflow; China version is over-dense, US version better but still reducible."
affects:
  - "WS:PROPHET-HK-CA-REVAMP presentation lane"
  - "site/hk-stock-v36.js"
  - "site/canada-stock-v36.js"
  - "future China stock-dashboard follower"
  - "research/STOCK_DASHBOARD_V38_ACTION_LEADERSHIP_ARCHITECTURE.md"
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-26
supersedes: []
---

# Action is not Leadership

This decision supersedes only narrow V3.7 **placement/presentation clauses**. It does not supersede `DEC:V37-SUPERSEDES-V36-ACCEPTANCE` as a historical record and does not revoke Canada/HK V3.7 `PROVEN_LIVE` receipts.

Binding architecture is `research/STOCK_DASHBOARD_V38_ACTION_LEADERSHIP_ARCHITECTURE.md`.

The next regional presentation sequence is HK reference correction -> production proof -> Canada follower correction -> production proof. China remains a separate later carrier after a fresh producer/collision census. US remains decoupled and unauthorized for this work.
