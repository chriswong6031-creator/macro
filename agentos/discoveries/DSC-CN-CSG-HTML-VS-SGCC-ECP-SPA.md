---
key: CN-CSG-HTML-VS-SGCC-ECP-SPA
claim: >
  China Southern Grid’s public bidding notices on www.bidding.csg.cn are
  server-rendered HTML with a business key `采购编号`/`项目编号` (`CG…`) and
  same-day 发布时间; State Grid ECP 2.0 at ecp.sgcc.com.cn is a JS-packed SPA
  whose public document contains no 招标/中标 text and whose purchase flows
  sit behind /isc/newlogin.html.
falsifier: >
  A same-day GET of a /zbgg/{id}.jhtml or /zbhxrgs/{id}.jhtml page that is a
  JS shell without 项目编号/中标人, or a GET of ecp.sgcc.com.cn/ecp2.0/portal/
  whose HTML already contains a 招标采购公告 or 中标（成交）结果公告 row
  without executing the webpack bundles.
so_what: >
  The first Grid/Power adapter reads CSG public HTML. Do not start the vertical
  with an ECP headless/packer project. Do not treat CSG /contract/ as a public
  contract tape — that path is the login 供货商协同 portal.
kind: data
verified_at: 2026-08-19
verified_by: >
  GET https://www.bidding.csg.cn/zbgg/1200439658.jhtml → 200, 项目编号
  CG1500022002349952, 发布时间 2026-08-19 11:15:24; GET
  https://www.bidding.csg.cn/zbhxrgs/1200439681.jhtml → 200, 中标结果公告,
  采购编号 CG0000022002324473, 中标人 named; GET
  https://ecp.sgcc.com.cn/ecp2.0/portal/ → 200, 8–9 KB shell, zero 招标/中标
  tokens, scripts include SM.js and main.*.bundle.js dated 202608131954;
  GET …/isc/newlogin.html → 200.
scope: [macro, china-system]
confidence: verified
---

Receipts: `research/china_alpha/censuses/CN-C/CN-C_PROBE_RECEIPTS_2026-08-19.md`.
Egress was a US datacenter IP; the CSG-vs-ECP *shape* (HTML vs packed SPA) is
what a future session should re-check, not the 200/404 of any one path.
