---
workstream: WS:CN-SOE-DEMAND
session: grok/cn-c-soe-demand-source-map
model: local
ended_because: complete
mission: >
  GROK-CN-C: first-party source map for the Government/SOE Demand vertical
  (Grid/Power default) and one bounded pilot where intention→tender→
  candidate→award→contract has the least first-party ambiguity.
state_before: >
  No collector, census, or agentos record for China government/SOE procurement.
  Closest patterns: US GovRev (WS:DEFENSE-PROCUREMENT-V3) and
  research/china_native_data source catalogs. Sibling lanes CN-B (entity
  resolver) and CN-D (project/EIA) exist as worktrees, not as consumed contracts.
changed:
  - path: research/china_alpha/censuses/CN-C/CN-C_GOV_SOE_DEMAND_SOURCE_MAP.md
    what: >
      Source registry (CCGP, GGZY, SGCC ECP, CSG bidding, provincial hubs,
      selected central-SOE portals, third-party do-not-ingest) plus the
      CSG-GD-货物-90d pilot recommendation and flip conditions
  - path: research/china_alpha/censuses/CN-C/CN-C_PROBE_RECEIPTS_2026-08-19.md
    what: HTTP receipts and field extracts from this egress
  - path: agentos/workstreams/WS-CN-SOE-DEMAND.md
    what: research workstream, C0 done, C1 gated
  - path: agentos/discoveries/DSC-CN-CSG-HTML-VS-SGCC-ECP-SPA.md
    what: CSG public HTML vs ECP packed SPA
  - path: agentos/handoffs/CN-SOE-DEMAND-2026-08-19.md
    what: this handoff
verified:
  - claim: origin/main fast-forwarded in macro-main before the worktree was cut
    command: git fetch origin && git merge --ff-only origin/main && git rev-parse origin/main
    result: Already up to date; 620acf86f242
  - claim: CSG tender HTML carries 项目编号 CG… and a same-day 发布时间
    command: GET https://www.bidding.csg.cn/zbgg/1200439658.jhtml
    result: 200; 项目编号 CG1500022002349952; 发布时间 2026-08-19 11:15:24
  - claim: CSG 公示公告 folder publishes 中标结果, not only 候选人
    command: GET https://www.bidding.csg.cn/zbhxrgs/1200439681.jhtml
    result: 200; title 中标公告; 采购编号 CG0000022002324473; 中标人 named
  - claim: CSG /contract/ is a login portal, not a public contract tape
    command: GET https://www.bidding.csg.cn/contract/index.jhtml
    result: 200; 供货商协同 / 立即登录 chrome
  - claim: State Grid ECP public document is a packed SPA with no notice text
    command: GET https://ecp.sgcc.com.cn/ecp2.0/portal/ and the dated config.js
    result: 200 8–9KB shell; zero 招标/中标 tokens; login /isc/newlogin.html 200
  - claim: CCGP award notices have a structured 公告概要 and search rate-limits
    command: GET t20260819_27163657.htm ; second bxsearch query
    result: 200 with 总中标金额 + 供应商 table; second search title 频繁访问
  - claim: Jiangsu CCGP details shell names the full legal stage list including 合同公告
    command: GET …/js_cggg/details.html?gglb=gkzb&ggid=5a5424043b67413f9c63707d8e300470
    result: 200; 公告进度 includes 采购意向公开 … 合同公告; 不得转载
  - claim: new records validate
    command: python3 scripts/agentos.py validate
    result: exit 0; 230 records, 0 errors, 14 pre-existing warnings
unverified:
  - claim: Beijing GGZY really publishes 招标计划 through 合同公示 for 电网工程项目
    what_would_verify: GET ggzyfw.beijing.gov.cn from an egress whose TLS accepts the cert
  - claim: ECP 中标（成交）结果公告 rows are public without login
    what_would_verify: hydrate the SPA from Studio egress and capture one result notice
  - claim: CSG 采购编号 dual-publishes onto a provincial GGZY 合同公示
    what_would_verify: one CG… key found on ygp.gdzwfw.gov.cn or a sibling 合同公示
unresolved:
  - Whether Studio residential egress changes ECP/国能e招/北京 GGZY from shell/DEAD to hydrated
  - CN-B resolver contract for 中标人 legal names (sibling lane, not consumed)
  - Rights read of CSG footer 服务条款 (hrefs were ###)
next_actions:
  - Adjudicate CSG-GD-货物-90d (accept → C1 display-tier adapter; reject → write the flip)
  - Re-probe ECP and 北京 GGZY from Studio egress before any second rail
  - Do not start C1 from this handoff
do_not_redo:
  - Do not invent a CCGP JSON API — there isn’t one; search is rate-limited HTML
  - Do not treat national GGZY as the notice ledger
  - Do not ingest third-party bid mirrors because ECP is hard
  - Do not log into CSG gmp or ECP isc for 中标通知书
  - Do not call CSG 寻源 a 采购意向
danger_areas:
  - CCGP 502/频繁访问 under even light search
  - Writing into omitted data/ on this sparse worktree
  - Building a second GovRev store or a Grid score
  - 江苏 不得转载 if anyone copies that node
---

C0 is the map. C1 is not started.
