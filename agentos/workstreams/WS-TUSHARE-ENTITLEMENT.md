---
key: TUSHARE-ENTITLEMENT
title: Tushare P0 access vs commercial-rights census
objective: >
  Know which China P0 Tushare SKUs the account already has, which cost new
  money, and which commercial-use questions still need a vendor letter.
  Done = a single purchase/rights matrix on origin/main. No purchase, no
  collector, no secret written.
status: done
program: china-system
repos: [macro]
owner: chairman
class: research
blast_radius: reversible
ambiguity: specified
owns_paths:
  - research/TUSHARE_P0_ENTITLEMENT_RIGHTS_MATRIX_2026-08-19.md
discoveries:
  - DSC:TUSHARE-TOKEN-IS-NOT-A-COMMERCIAL-GRANT
do_not_redo:
  - Do not infer Tushare commercial rights from API success or from a live token.
  - Do not buy anns_d / irm_qa_* / research_report to cover planes native collectors already run.
  - Do not treat research/TUSHARE_INTEGRATION.md ¥500/5000 as the current SKU.
next_action: >
  Operator confirms the privilege page (redact token) against the 2026-08-09
  SKU list, then asks Tushare in writing the five commercial questions in
  research/TUSHARE_P0_ENTITLEMENT_RIGHTS_MATRIX_2026-08-19.md §3.
waves:
  - id: GROK-CN-A
    title: Purchase/rights matrix from official docs + secret metadata
    status: done
---

Census home: `research/TUSHARE_P0_ENTITLEMENT_RIGHTS_MATRIX_2026-08-19.md`.
This workstream does not own collectors and does not authorize a purchase.
