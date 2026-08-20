---
key: CN-TERMINAL-LICENSE-FORBIDS-MASTERMIND-DISPLAY
claim: >
  Public 2026-08-19 licences for the commercial PRC supply-chain and registry
  vendors that expose readable terms grant internal research or internal
  compliance use and do not grant Mastermind the right to persist a graph,
  build derived features, and display those derived outputs to customers.
falsifier: >
  A fetched vendor ToS or executed commercial agreement that, in operative
  language, grants a named Macro/Mastermind contracting entity (a) bulk local
  persist, (b) derived-feature construction, and (c) customer-facing derived
  display of disclosure-graph edges. The current QCC ToS §§6.1 and 8.1, the
  TuShare doc_id=405 personal-use clause, and the CNRDS academic-only
  registration copy would have to be superseded or carved out.
so_what: >
  Do not treat a Wind / Choice / iFinD / CSMAR / CNRDS / QCC / Tianyancha seat
  or campus login as a product data source. Do not design CN supply-chain
  features that assume a licensed graph. Keep work on the public CNInfo 年报
  floor and the CN-B identity layer until a written OEM grant exists.
kind: constraint
confidence: verified
verified_at: 2026-08-19
verified_by: >
  web_fetch https://www.qcckyc.com/terms-conditions?type=1 (§§6.1, 8.1);
  web_fetch https://tushare.pro/document/2?doc_id=405 (§2(二)5);
  web_search/crawl of https://www.cnrds.com/ registration copy;
  web_fetch https://www.wind.com.cn/mobile/WDS/sapi/zh.html;
  web_fetch https://www.tianyancha.com/data (US geo-block);
  collectors/china_filings.py:3-6
scope: [macro, china-system]
---

The expensive object is the display right, not the table. QCC is the only
vendor whose full commercial ToS was readable this session; it is an explicit
ban. The others either hide the click-wrap behind a terminal or market
internal-system embedding only. Campus academic panels are a separate hard no.
