---
key: CN-SOE-DEMAND
title: China Government / SOE Demand source map (Grid/Power first)
objective: >
  First-party source map for the Government/SOE Demand vertical, Grid/Power first.
  Done for C0 = the census and one bounded pilot recommendation exist; no collector,
  no score, no Prophet family.
status: active
program: china-system
repos: [macro]
owner: grok-cn-c
class: research
blast_radius: reversible
ambiguity: scoped
owns_paths:
  - research/china_alpha/censuses/CN-C/
depends_on:
  - WS:DEFENSE-PROCUREMENT-V3
artifacts:
  - research/china_alpha/censuses/CN-C/CN-C_GOV_SOE_DEMAND_SOURCE_MAP.md
  - research/china_alpha/censuses/CN-C/CN-C_PROBE_RECEIPTS_2026-08-19.md
discoveries:
  - DSC:CN-CSG-HTML-VS-SGCC-ECP-SPA
landmines:
  - "Do not fork engine/government_revenue/ onto China. Adopt the event vocabulary only."
  - "Do not ingest dlnyzb / chinabidding / toobiao / other bid aggregators."
  - "Do not cron search.ccgp.gov.cn — it 频繁访问-blocks this egress on the second query."
  - "Do not log into CSG :9090/gmp or ECP /isc/ to fetch 中标通知书 or contracts."
  - "中标人 legal name resolution is CN-B, not a second matcher in this lane."
  - "江苏政府采购网 forbids republication without written permission."
do_not_redo:
  - "Do not rebuild the US GovRev store, SAM rail, or USAspending spine for this vertical."
  - "Do not treat 寻源公告 on bidding.csg.cn as 采购意向 — verified stale/non-intention."
  - "Do not treat national GGZY as a notice ledger — platform.js is a provincial directory."
waves:
  - id: C0
    title: First-party source map + bounded Grid/Power pilot recommendation
    status: done
    next_action: >
      Adjudicate CSG-GD-货物-90d. Do not start an ECP scraper. Do not ingest
      third-party bid aggregators.
  - id: C1
    title: Display-tier CSG Guangdong goods adapter (receipts only)
    status: todo
    depends_on: [C0]
    next_action: >
      Build only after C0 is accepted. Public HTML notices, CG… keys, typed
      INTENTION_NOT_PUBLIC / CONTRACT_NOT_PUBLIC. No login, no score.
next_action: >
  Accept or reject the CSG-GD-货物-90d pilot in CN-C_GOV_SOE_DEMAND_SOURCE_MAP.md.
  If accepted, C1 is a display-tier adapter only.
---

Research workstream for GROK-CN-C. Runtime authority is NONE. C1 does not start from this record.
