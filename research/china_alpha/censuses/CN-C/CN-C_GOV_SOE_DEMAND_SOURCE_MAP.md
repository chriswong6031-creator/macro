# GROK-CN-C — Government / SOE Demand source map

**Lane:** GROK-CN-C · **Date:** 2026-08-19 · **Pin:** `origin/main` @ `620acf86f242`  
**Vertical:** first Government / SOE Demand map. Default candidate = Grid / Power.  
**Authority:** NONE. This census authorizes no collector, no score, and no Prophet family.  
**Egress this session:** `104.36.50.55` (AS203020 HostRoyale, geolocated New York). Datacenter IP — re-probe from the Studio before treating any DEAD/UNSTABLE row as globally dead. Method matches `research/china_native_data/SOURCE_CATALOG_MACRO_POLICY_HK.md`.

Claim tags: **VERIFIED** (HTTP body seen this session) · **INFERRED** (official page or legal text, not re-fetched as a data row) · **UNVERIFIED** · **DEAD/UNSTABLE from this egress**.

Adopt, do not rebuild: US GovRev is the sibling *pattern* (`engine/government_revenue/`, `WS:DEFENSE-PROCUREMENT-V3`) — award events, typed source states, PIT receipts. Do not fork that store onto China. Entity resolution belongs to the CN-B PRC resolver lane, not a second name matcher here.

---

## Verdict

**Pilot one rail: China Southern Grid’s public notice HTML on `www.bidding.csg.cn`, bounded to 广东电网 × 货物, keyed by `采购编号` (`CG…`).**

That is the only first-party Grid/Power surface this session where tender → candidate/award → cancellation is HTML, has stable IDs, and does not require unpacking a 国密 SPA. Intention and contract are **not** first-party public on that site; print those stages as typed gaps (`INTENTION_NOT_PUBLIC`, `CONTRACT_NOT_PUBLIC`) rather than scraping the login portal.

State Grid ECP (`ecp.sgcc.com.cn`) is the higher-alpha object (headquarters batch awards) and the **second** rail, not the first: it is a JS-packed portal with login-gated purchase flows. CCGP is the complete *legal* government-procurement spine and the wrong economic object for transformers and GIS. National GGZY is an aggregator index, not a ledger.

---

## How the two legal spines differ

| Spine | Statute | Typical publisher | Grid/Power content | 5-stage public completeness |
|---|---|---|---|---|
| Government procurement | 政府采购法 + 实施条例 + 财库〔2020〕10号 采购意向公开 | 中国政府采购网 and provincial CCGP nodes | Office, IT, services, some construction supervision. Core grid equipment almost never. | Intention + tender + award + amendment/cancel + **contract** are legally required. Central CCGP hosts intention behind a captcha; contract often lives on the provincial node. |
| SOE / engineering bidding | 招标投标法 + 国资委央企采购办法 | SOE e-procurement portals; dual-publish onto provincial GGZY / 中国招标投标公共服务平台 | State Grid and CSG material and engineering batches. This is the demand that moves listed electrical-equipment names. | Tender + candidate + award are usually public. Intention is a 采购计划/寻源, not 采购意向. **Contract texts are typically login-gated.** |

Do not merge the two spines into one row type. A CCGP `项目编号` and a CSG `采购编号` are different objects even when the buyer name contains 电网.

---

## Registry

Status: **PILOT** = start here · **CANDIDATE** = first-party, not first build · **INDEX** = aggregator, join-only · **DO NOT INGEST** = third-party / ToS · **DEAD this egress**.

| Source | Official owner | Endpoint / search | Lifecycle stages seen | IDs | Timestamps | Buyer / supplier | Value / qty / product | Amendment / cancel | History | Anti-bot / terms | Machine access | Rec |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| China Southern Grid 供应链统一服务平台 | 中国南方电网有限责任公司 / 南方电网供应链集团有限公司 | `https://www.bidding.csg.cn/` HTML lists: `/zbgg/` 招标, `/zbhxrgs/` 公示 (候选人 **and** 中标结果), `/fzbgg/` 非招标, `/fbgg/` 流标, `/zzgg/` 中止, `/lxcggg/` 零星, `/xygg/` 寻源 (stale). Filters: 货物/工程/服务 + 网省. | Tender VERIFIED. Candidate+award mixed in 公示公告 VERIFIED (titles: 中标公示 / 中标公告 / 成交结果公告). 流标 and 中止 first-class. Intention: 寻源 is **not** a live 采购意向 (latest items 2023–24, including a refund letter). Contract: `/contract/` is a **login** 供货商协同 portal, not a notice list. | URL numeric ` /zbgg/1200439658.jhtml`. Business key `项目编号`/`采购编号` `CG1500022002349952` / `CG0000022002324473`. | `发布时间： 2026-08-19 11:15:24` on a tender fetched the same day. | 招标人 (e.g. 南方电网科学研究院有限责任公司); 中标人 legal name on award. 网省 filter includes 广东电网, 深圳供电局, 超高压, 储能. | Tender table: 标的/标包, 预计采购金额（万元）, 最高投标限价, 最大中标数量, 工期. Award: 标的/标包/中标人. Quantity units vary by 标包. | 流标 `/fbgg/`, 中止 `/zzgg/`, 二次招标 in titles. No separate 更正 folder found. | Download-center item dated 2020-02-29 (`/down/1200251437.jhtml`). Guessed low IDs 404. Public list pages show only the current page of IDs (~10). History = what we snapshot + whatever CMS keeps. | No `robots.txt` fetched (not probed as 200). Footer 法律声明/服务条款 are `###` placeholders. Login at `:9090/gmp/login.html` (200). | **Best machine access in the Grid set.** Server-rendered `.jhtml`, no packer, no captcha on public lists this session. | **PILOT** |
| State Grid 新一代电子商务平台 (ECP 2.0) | 国家电网有限公司 | `https://ecp.sgcc.com.cn/` → `…/ecp2.0/portal/#/`. Config (`assets/js/config.202608131951.js`) : `baseUrl=/ecp2.0/`, login `/isc/newlogin.html`, purchase `#/main/bidding{1,2,3}/purchasebidfile/`, CMS hint `ecp_wcm_core=/ecp2.0/ecpwcmcore/` (that path 404 on bare GET). Corporate `www.sgcc.com.cn` **timed out** this egress. `mall.sgcc.com.cn` NXDOMAIN. | Official section names (INFERRED from 2026-08-13 crawl of the public portal chrome, not from a parsed row this session): 招标采购公告 · 推荐中标候选人公示 · 中标（成交）结果公告 · 资质能力核实 · 不良行为 · 绩效评价. Contract/bid-file purchase is login. | Unknown until a notice row is parsed. Batch language in the wild: 2026年第N批 + 包号. | Unknown this session (SPA shell has no notice text). | Buyer = 国网总部 or a provincial 电力公司. Supplier on 中标结果. | Centralized material batches carry 品类 + 数量 + 金额 on the result notice **when** the SPA hydrates — UNVERIFIED this session. | 更正/终止 exist as notice types on mirrors; not parsed first-party here. | Multi-year batches exist in the industry press. First-party history depth UNVERIFIED. | Shell loads SM.js (国密), `EcpSecureRandom`, `encrytrans`, webpack `main.*.bundle.js` dated `202608131954`. `robots.txt` 404. Login HTML 200. Config `isEncrypt:false` today — do not assume it stays false. | **Poor.** HTML shell only (8–9 KB). Zero 招标/中标 tokens in the document. Needs browser + likely session cookies. | **CANDIDATE (rail 2)** |
| 中国政府采购网 | 财政部国库司. 网站标识码 `bm14000002`. 唯一指定政府采购信息网络发布媒体. | Site `https://www.ccgp.gov.cn/` (also http). Channels: `/cggg/zygg/gkzb/` 公开招标, `/zbgg/` 中标, `/gzgg/` 更正, `/cjgg/` 成交, `/fbgg/` 废标, `/qtgg/` 其他. Search `http://search.ccgp.gov.cn/bxsearch` (https search 502 this session). Intention `http://cgyx.ccgp.gov.cn/cgyx/pub/pubSearch` (captcha). | Tender VERIFIED. Award VERIFIED (公告概要 table + 供应商 table + 得分表). 更正 list VERIFIED. 成交 VERIFIED. 废标 list 200 then 502. Intention search **requires 验证码**. Central `/cggg/zygg/htgg/` 404 — contract is not a central channel. 终止 `/zzgg/` 502. | URL `tYYYYMMDD_27163657.htm`. Body 项目编号. Award supplier rows are ordinal, not a stable supplier ID. | `公告时间 2026年08月19日 14:54` and list `发布时间： 2026-08-19 15:33`. | 采购单位, 代理机构, 供应商名称, 行政区域. | 预算金额 on tender; 总中标金额 + 货物名称/品牌/型号/数量/单价 on award (often “详见附件”). 品目 is the official catalog path. | 更正公告 channel. 废标公告 channel. Titles include （第三次）/重新招标. | Site copyright 1999–. Dated URL scheme is deep; a 2020 month index 502’d and a guessed 2020 file 404’d. Do not claim a backfill floor. | `robots.txt` 404. Search rate-limit: second query returned `频繁访问!` + this IP. Some `/cggg/zygg/` paths 502 via CDN nodes `PS-KHH` / `PS-SIN` / `PS-HND`. No published API. | **Good on static notices, hostile on search.** HTML 公告概要 is parseable. Do not poll `bxsearch`. | **CANDIDATE (gov spine, not Grid core)** |
| 江苏政府采购网 (CCGP 分网) | 江苏省财政厅 / 江苏省政府采购中心. Self-description: 中国政府采购网江苏分网, 省级唯一发布媒体. | `http://www.ccgp-jiangsu.gov.cn/`. Notice: `/jiangsu/js_cggg/details.html?gglb=<stage>&ggid=<uuid>`. Search `/jiangsu/cggg_search.html`. | **The only first-party 5-stage progress UI verified this session:** 采购意向公开 · 单一来源公示 · 资格预审 · 采购（征集）公告 · 更正 · 废标（终止） · 结果（入围） · 成交结果汇总 · **合同公告** · 验收 · 其他. Contract template fields (合同编号, 甲乙方, 标的数量/单价, 合同金额, 签订日期, 公告日期) are in the page shell. | `ggid` UUID. `gglb` stage code (`gkzb`, `jzcs`, …). | `发布时间` on the shell. | 采购人 / 供应商 in the contract template. | Contract template has 数量, 单价, 合同金额. Live values are JS-filled — row contents UNVERIFIED. | 更正 and 废标 are named stages on the same `ggid`. | UNVERIFIED. | **Explicit republication ban** on the details page: 未经书面许可其他任何网站和个人不得转载. Nav stages are `javascript:;` (XHR). | SPA-ish details. Complete *legal* spine, **not Grid/Power**. | **METHOD REFERENCE only** |
| 全国公共资源交易平台 | 国家发展改革委牵头的国家级公共服务平台 (homepage links NDRC / 财政部 / 国资委). | `https://www.ggzy.gov.cn/`. Query ` /deal/dealList.html?HEADER_DEAL_TYPE=` 01 工程建设 … 02 政府采购 …. History ` /history/dealList.html` (“一年前数据”). `platform.js` is a **provincial platform registry**, not a notice API. `deal.ggzy.gov.cn` NXDOMAIN. CEB `cebpubservice.com` / `ctbpsp.com` **405 + 访问被阻断** this egress. | Vue templates expose 招标/资审公告, 开标记录, 交易结果公示, 招标/资审文件澄清. Homepage “今日公告数量” rendered as 0 (JS). One CSG project was indexed here and cited `www.bidding.csg.cn` as the publication venue (web index 2026-08-07). | Provincial platform IDs in `platform.js` (e.g. `12341700793567866N`). Notice IDs UNVERIFIED (list body is `{{ item.time }}`). | Template `item.time`. | UNVERIFIED first-party. | UNVERIFIED. | Clarification type in the query UI. | History view exists as a separate route. Depth UNVERIFIED. | `robots.txt` 404. No recovered REST this session. | **Index, not a ledger.** Use to *discover* a provincial URL, then read the provincial first party. | **INDEX** |
| 广东省公共资源交易平台 | 广东省公共资源交易中心 (政务服务网 ygp). | `https://ygp.gdzwfw.gov.cn/` → `/ggzy-portal/` Vue shell (hashed CSS only; 5 hrefs). `ggzy.gd.gov.cn` NXDOMAIN. | Full engineering lifecycle is the *family* pattern (see 北京 below). **This host’s notice types were not hydrated this session.** | UNVERIFIED. | UNVERIFIED. | UNVERIFIED. | UNVERIFIED. | UNVERIFIED. | UNVERIFIED. | SPA. | Shell only from this egress. | **CANDIDATE provincial join** |
| 北京市公共资源交易服务平台 | 北京市公共资源交易中心 | `https://ggzyfw.beijing.gov.cn/` — **SSL BAD_ECPOINT this egress.** Nav from a 2026-08-18 index crawl (not a TLS-verified body this session): 招标计划 · 招标公告 · 更正 · 合格申请人 · 中标候选人 · 拟定中标人 · 中标结果 · 终止 · **合同公示** · 变更 · 决算. IDs like `S110000A001043870003`. | If the crawl is right, this is the cleanest *engineering* 5-stage public chain in the set (计划 → 公告 → 候选人 → 结果 → 合同). | `S110000…` style. | Dated paths `/jyxxggjtbyqs/20260818/…`. | District tags 【朝阳区】 etc. | UNVERIFIED. | 更正 / 终止 / 变更. | UNVERIFIED. | TLS failed here. | **UNVERIFIED this egress** | **CANDIDATE if Studio TLS works** |
| 江苏省公共资源交易网 | 江苏省公共资源交易中心 | `http://jsggzy.jszwfw.gov.cn/` 200. Server `epoint-httpserver`. | Homepage is a hub (links 国家公共资源交易平台 + 江苏省政府采购网). Notice schema not parsed. | UNVERIFIED. | UNVERIFIED. | UNVERIFIED. | UNVERIFIED. | UNVERIFIED. | UNVERIFIED. | Reachable HTML. | Hub. Pair with 江苏 CCGP, do not duplicate. | **CANDIDATE hub** |
| 中国三峡集团电子采购平台 | 中国长江三峡集团有限公司 | `https://eps.ctg.com.cn/` 200, title 中国三峡集团电子采购平台. Linked from `www.ctg.com.cn` (旧站 `epp.ctg.com.cn` untested). | UNVERIFIED notice types (SPA/js-injected CSS). | UNVERIFIED. | UNVERIFIED. | UNVERIFIED. | UNVERIFIED. | UNVERIFIED. | UNVERIFIED. | `robots.txt` 404. | Structured SOE portal, **hydro/generation**, not grid T&D. | **CANDIDATE other-SOE** |
| 国能e招 | 国家能源集团 | `https://www.chnenergybidding.com.cn/` 200 with **151-byte empty body**. Subpaths 404. Corporate `www.chnenergy.com.cn` 200 and names 国能e招 / e购 / e商 / e电 / e链. | Industry chrome (INFERRED, not this body): 招标 / 资格预审 / 变更 / 候选人 / 中标 / 终止 / 拟单一来源 / 招标计划. | UNVERIFIED. | UNVERIFIED. | UNVERIFIED. | UNVERIFIED. | UNVERIFIED. | UNVERIFIED. | Empty shell = JS or WAF. | Not buildable from this egress. | **UNSTABLE** |
| 易派客 epec.com | 中国石化体系 (not a grid owner) | `https://www.epec.com/` 200, title 易派客-让采购更专业. Login/register, 我要投标/招标. | Marketplace + tender, not a public 5-stage notice HTML. | UNVERIFIED. | UNVERIFIED. | Member accounts. | 电工材料专区 exists as a mall category — **not** a State Grid award tape. | UNVERIFIED. | UNVERIFIED. | Cookie set. | Wrong owner for this vertical. Listed so nobody “discovers” it as Grid. | **OUT OF VERTICAL** |
| 华能 ECP / 华电 / 国电投 bidding | 各发电集团 | `ecp.chng.com.cn`, `www.chng.com.cn` NXDOMAIN/timeout. `www.chd.com.cn` and `www.spic.com.cn` are corporate sites (encoding-broken titles), no bidding host recovered. | — | — | — | — | — | — | — | — | Not found this session. | **UNVERIFIED** |
| Third-party bid aggregators (dlnyzb.com, chinabidding.com.cn, toobiao.com, ccpc360 mirrors) | Private publishers | They scrape or retype ECP/CSG/CCGP. | Derivative. | Their own. | Their own. | Their own. | Their own. | Unauditable. | Convenient, not ours. | Typical 转载 / paid walls. | **DO NOT INGEST.** Same class as Dataroma-for-13F. |

---

## Recommended pilot (bounded)

### What to build

**Name:** CSG-GD-货物-90d  
**Source:** `https://www.bidding.csg.cn/` only.  
**Buyer filter:** 网省 = 广东电网公司 (one additional 网省 is a scope expansion, not a fix).  
**Class:** 货物.  
**Window:** notices with `发布时间` in the last 90 days (forward snapshot; no backfill claim).  
**Event key:** `采购编号` / `项目编号` (`CG…`). URL numeric id is a locator, not the join key (候选人 and 中标结果 share `/zbhxrgs/` and the numeric id is per *notice*, not per *project*).  
**Stages in v0:**

| Stage | How | Typed null if absent |
|---|---|---|
| Intention | Do **not** use `/xygg/` (verified non-intention / stale). | `INTENTION_NOT_PUBLIC` |
| Tender | `/zbgg/{id}.jhtml` | skip row |
| Candidate | `/zbhxrgs/{id}.jhtml` whose title contains 候选人 | `CANDIDATE_NOT_SEPARATE` (many projects jump to 中标公示) |
| Award | `/zbhxrgs/{id}.jhtml` whose title contains 中标公告 / 中标公示 / 成交结果 | skip if neither candidate nor award |
| Contract | Do **not** log into `:9090/gmp`. Optional later join: same 采购编号 on a provincial GGZY 合同公示. | `CONTRACT_NOT_PUBLIC` |
| Cancel | `/fbgg/`, `/zzgg/`, or title 二次招标 / 终止 | supersedes live tender |

**Fields to keep (only if present in HTML):** 发布时间, 招标人, 采购编号, 标的, 标包, 预计采购金额, 最高投标限价, 中标人, 网省, 货物/工程/服务, notice URL, sha of fetched bytes, `known_at` = our fetch clock.  
**Identity:** 中标人 legal name → listed ticker is **CN-B’s job**. This lane emits the legal name only.  
**Rights:** public notice pages, retain receipts. No bid-file download, no login, no 三公信箱. Footer 服务条款 were unresolvable (`###`) — treat as unofficial HTML until Legal/Data OS reads a real terms URL.  
**Failure states (reuse GovRev vocabulary, do not fork the store):** `CURRENT` / `PARTIAL` / `STALE` / `EMPTY_VALID` / `SOURCE_UNAVAILABLE` / `RIGHTS_BLOCKED`.

### Why this, not the obvious alternatives

1. **Not State Grid ECP first.** Highest economic signal (总部集中招标 of 变压器 / 组合电器 / 电缆 / 电表), worst machine access. Config and login are real; a notice row is not. Building ECP first is a scraper-of-a-packer project, not a lifecycle project.  
2. **Not CCGP first.** 公告概要 is the cleanest structured HTML in the set, and the legal 5-stage spine is real — but a day’s 中标公告 is 消防标识制作 and 食堂餐饮. That is not Grid/Power demand. Search cannot be used as the filter (`频繁访问` on query 2).  
3. **Not national GGZY first.** `platform.js` is a directory of other people’s systems. The list page does not contain rows without JS.  
4. **Not 江苏政采 as the vertical pilot.** It is the method reference for intention→contract on one `ggid`, and it **forbids republication**. Use it later to design a government-procurement adapter, not to learn whether 许继/平高/南瑞 won a batch.  
5. **Not 国能e招 / 华能 / 三峡 as the first Grid rail.** Generation SOEs are a later sibling vertical. 三峡 EPS is reachable; 国能e招 is an empty shell here.

### Flip conditions

- Flip the first rail to **ECP** if a Studio-egress session retrieves a hydrated 中标（成交）结果公告 with 招标编号 + 包号 + 中标人 + 金额 without login.  
- Flip the first rail to **北京/广东 GGZY 工程建设** if Studio TLS works and a 广东电网 变电站/线路 project shows 招标计划 + 合同公示 on one official id. That would be the least-ambiguous *construction* 5-stage, still not the equipment-batch tape.  
- Do **not** flip to a third-party mirror because ECP is hard.

### What this pilot is not

Not a score. Not a Prophet family. Not a second GovRev. Not a scrape of bid files. Not a join onto USAspending patterns beyond the *event* vocabulary. Not permission to hit `search.ccgp.gov.cn` on a cron.

---

## Suggested next wave (not this PR)

1. CSG-GD-货物-90d display-tier adapter + receipts.  
2. CN-B name resolver for the 中标人 roster (hand-curated listed electrical names only).  
3. ECP notice-row reconnaissance from Studio egress (one hydrated result page, then stop).  
4. Optional GGZY join for CSG construction projects that already dual-publish.  
5. Government-procurement adapter only after a rights read of 江苏’s 不得转载 clause — and only if the economic object is 政府采购, not Grid equipment.
