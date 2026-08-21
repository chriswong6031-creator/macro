---
workstream: WS:TUSHARE-ENTITLEMENT
session: grok/cn-a-tushare-entitlement
model: local
ended_because: complete
mission: >
  GROK-CN-A — determine which China P0 Tushare datasets Mastermind already
  has contractual/access rights to, what is missing, what each missing right
  costs, and which commercial-use questions need vendor confirmation. No
  buy, no secrets written, no collectors, no rights inferred from API success.
state_before: >
  Token-gated Tushare plane exists (forecast/chips/金股/moneyflow/margin).
  Operator 2026-08-09 claimed 常规无上限 + 特色 300/min + minutes/premarket/auction.
  License machinery in collectors is closed. No P0 purchase/rights matrix.
  TUSHARE_INTEGRATION.md still said ¥500/5000.
changed:
  - {path: research/TUSHARE_P0_ENTITLEMENT_RIGHTS_MATRIX_2026-08-19.md, what: "new — single P0 purchase/rights matrix (OWNED / MISSING / UNKNOWN_RIGHTS / NOT_NEEDED)"}
  - {path: agentos/discoveries/DSC-TUSHARE-TOKEN-IS-NOT-A-COMMERCIAL-GRANT.md, what: "new — token/probe/closed-license-machinery is not a commercial grant"}
  - {path: agentos/workstreams/WS-TUSHARE-ENTITLEMENT.md, what: "new — done one-wave census workstream"}
verified:
  - {claim: "GitHub secret TUSHARE_TOKEN exists; updated_at 2026-08-08T08:08:40Z; value unread", command: "gh api repos/mastermindx-market-intelligence/macro/actions/secrets --paginate --jq '.secrets[] | select(.name==\"TUSHARE_TOKEN\") | {name, updated_at}'", result: "name TUSHARE_TOKEN, updated_at 2026-08-08T08:08:40Z"}
  - {claim: "this session env has no TUSHARE_TOKEN", command: "python3 -c \"import os; print('SET' if os.environ.get('TUSHARE_TOKEN') else 'UNSET')\"", result: "UNSET"}
  - {claim: "official personal prices and 10x institutional footnote are on doc 290", command: "web fetch https://tushare.pro/document/1?doc_id=290", result: "5000=¥500 常规无上限; 10000=¥1000 特色 300/min; table-2 公告¥1000 / 互动易¥500 / 研报库¥500; 机构=个人10倍"}
  - {claim: "doc 405 is personal non-commercial view-only", command: "web fetch https://tushare.pro/document/1?doc_id=405", result: "个人的、不可转让的、非商业用途、仅可用作个人查看使用"}
  - {claim: "no repo collector for stk_surv / fund_portfolio / anns_d / irm_qa_* / hm_detail / top10_holders / stk_holdertrade", command: "grep those api_names under collectors/ and research/", result: "empty for those endpoint names as collectors"}
unverified:
  - {claim: "the live account is at 10000积分 with the 2026-08-09 add-on SKUs still lit", what_would_verify: "operator screenshot of tushare.pro/weborder/#/user/privilege with token redacted"}
  - {claim: "hm_detail unlocks automatically at 10000积分", what_would_verify: "privilege page or a vendor note; doc 290 特色 sentence does not name 游资"}
unresolved:
  - "No written vendor/institutional grant is in the repository. Commercial display of any Tushare-derived widget stays blocked on a vendor letter (matrix §3 five questions)."
next_actions:
  - "Operator opens the privilege page and diffs it against matrix §1.2 (常规 / 特色 / minutes / premarket / auction). Do not paste a token."
  - "If the product is commercial, send Tushare the five questions in matrix §3. Do not buy table-2 SKUs first."
  - "Do not charter collectors for anns_d, irm_qa_*, or research_report. Native paths already cover those P0 planes."
do_not_redo:
  - "Do not infer commercial rights from a 200 / non-empty DataFrame."
  - "Do not buy anns_d, irm_qa_sz/irm_qa_sh, or research_report to fill announcement / Q&A / sell-side planes already collected from CNInfo / SSE / SZSE / Eastmoney."
  - "Do not treat TUSHARE_INTEGRATION.md ¥500/5000 as current."
  - "Do not reopen license-machinery gates inside collectors (2026-08-09 ruling 3). Rights questions go to a vendor letter, not a new env flag."
danger_areas:
  - "Mastermind data_layer/tushare_feed.py posts to http://api.tushare.pro (plaintext). Macro collectors/tushare_client.py uses HTTPS and refuses redirects. Do not copy the Mastermind client."
  - "cyq_chips collector exists but is not scheduled. Arming it is a quota decision, not a purchase."
  - "tushare_client still throttles report_rc to 1/hour even if 10000积分 has no official daily cap. That is a local conservative, not a rights fact."
discoveries:
  - DSC:TUSHARE-TOKEN-IS-NOT-A-COMMERCIAL-GRANT
---

Cold-stranger continuation is the matrix itself:
`research/TUSHARE_P0_ENTITLEMENT_RIGHTS_MATRIX_2026-08-19.md`.
