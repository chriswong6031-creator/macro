# GROK-CN-E — Commercial Supply-Chain / Alt-Data Diligence

Status: diligence complete; no purchase recommended.
Authority: `context_only`. Nothing here ranks, gates, sizes, or scores a name.
Date: 2026-08-19.
Program: `china-system`. Workstream: `WS:CN-COMMERCIAL-SUPPLY-DILIGENCE`.
Decision: `DEC:CN-NO-SUPPLY-CHAIN-SEAT-PURCHASE`. Discovery: `DSC:CN-TERMINAL-LICENSE-FORBIDS-MASTERMIND-DISPLAY`.

Accessed 2026-08-19 from a US IP. Markers: `[V]` this-session primary page or repo file; `[C]` in-repo census not re-run; `[I]` inference; `[S]` secondary (forum / library brochure).

---

## 0 · Verdict

**Do not buy a Wind, Choice, or iFinD terminal seat, a CSMAR/CNRDS academic panel, or a Qichacha / Tianyancha / QCC registry graph for Mastermind-derived use.**

The question was not table count. It was whether a license can lawfully persist, cache, derive features, and display those derived outputs to Mastermind customers, and whether that would save more engineering time than parsing the public CNInfo 年报 top-5 customer/supplier tables we already have a metadata collector for.

No public 2026-08-19 license grants that bundle.

- QCC TECH PTE. LTD. (the only named vendor whose public ToS we could read in full) grants use **solely for internal business and compliance** and **forbids** redistribution, derivative datasets, scoring systems, and automated data products (`qcckyc.com/terms-conditions`, §§6.1, 8.1) `[V]`.
- TuShare's ordinary paid token is a **personal, non-commercial, personal-viewing** licence (`tushare.pro/document/2?doc_id=405` §2(二)5) `[V]`. The full-A spine is already gated on a written commercial grant (`research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md`) `[V]`.
- CNRDS registration forbids transfer/sale/third-party disclosure, confines use to a named-author research project, and requires a promise of **academic use only, not commercial** (`cnrds.com` registration copy) `[V]`.
- Wind WDS / Server API and QCC industrial-chain / offline datasets market **internal-system embedding**, not OEM redistribution into a customer-facing SaaS (`wind.com.cn/mobile/WDS/sapi/zh.html`; `qcckyc.com/industrial-chain-intelligence`) `[V]`.
- Choice's quant API is unlocked **inside the Choice terminal** (`quantapi.eastmoney.com`) `[V]`.
- Tianyancha's public site **geo-blocks the United States** (`tianyancha.com/data`, 2026-08-19) `[V]`.

The public-source floor for the *disclosure* graph is the A-share 年报 前五名客户/供应商 table. `collectors/china_filings.py` already collects CNInfo announcement metadata and **never fetches PDF bodies** `[V]`. That is the engineering work. A terminal seat does not do it for us, because we still cannot put the vendor graph on the product.

The only reopen is a **written OEM / WDS-class commercial agreement** that names, in one grant: API access, bulk local persist, derived-feature construction, and customer-facing derived (not raw) display. Until that quote exists, SKIP-ALL (2026-07-05) on paid supply-chain stands.

---

## 1 · What this packet is allowed to decide

**In scope.** Compare commercial providers only where they can cut *normalization debt*: entity resolution of unlisted counterparties, A/H dual-list identity, relationship effective dates, evidence/provenance, historical snapshots, update cadence, API, persist, derived-feature rights, customer-facing derived-display rights, pricing, entity IDs, export/cache.

**Out of scope.** Buying a terminal because it has many tables. Expert networks (Capvision / GLG — `docs/QUAL_DATA_COMPLIANCE.md` §2.2, hard legal line) `[V]`. Card/transaction panels (§2.3). Satellite / mapping-law panels. Social firehoses.

**Two graphs, not one.** Mixing them is how a seat purchase looks useful and is not.

| Graph | What it actually is | Typical vendors | What it does *not* give |
|---|---|---|---|
| Disclosure (供销) | Annual-report top-5 customers/suppliers, often anonymized as 客户A, with amounts and concentration | Wind SDB, CSMAR 供应链研究, CNRDS SCRD | Complete unlisted web; daily updates; named counterparties when the issuer hid them |
| Registry (工商) | Equity, investment, office-holding, UBO, legal-rep | Wind 商业大数据 / GEL, Qichacha, Tianyancha, QCC | Evidence of *trade* flow; PIPL-clean impersonal data |

Mastermind supply-chain signal wants the disclosure graph. CN-B entity resolution wants a *public* identity layer, not a PII-bearing KYC dump.

---

## 2 · In-repo debt (the thing a purchase would have to beat)

Verified this session against the CN-E worktree (HEAD of `origin/main` at branch creation).

| Debt | State | Evidence |
|---|---|---|
| Supplier/customer collector | **None** | `grep` of `collectors/china*.py` for 客户/供应商/前五名: 0 hits `[V]` |
| CNInfo filings | Metadata only; no PDF bodies | `collectors/china_filings.py:3-6` `[V]` |
| Fundamentals | Main-business *description* + financials via akshare; no counterparties | `collectors/china_fundamentals.py:1-17` `[V]` |
| TuShare `mainbz` | Segment mix parquet listed in the catalog, not a supplier graph | `research/MASTERMIND_DATA_SOURCE_CATALOG.md:347` `[C]` |
| TuShare commercial use | Personal token is not permission; spine is foundation-only | `research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md:16-24`; ToS `[V]` |
| Wind / Choice / iFinD integrations | **Zero** | `grep` of `collectors/` for Wind/iFinD/Choice API clients: none. THS concept boards are a public scrape (`collectors/china_ths_concepts.py`) `[V]` |
| A/H | Premium snapshot + reconstructed index; not a company-ID graph | `collectors/hk_ah_official.py:1-28` `[V]` |
| Paid supply-chain | Already CUT under SKIP-ALL 2026-07-05 | `research/LONG_HOLD_THESIS_MASTERPLAN_BY_FABLE.md:27,74,88` `[V]` |
| Qual compliance | Public-source + impersonal aggregates only | `docs/QUAL_DATA_COMPLIANCE.md` §1, §2, §4.4 `[V]` |
| Prior vendor table | Wind/Choice/iFinD already rated **stretch** with redistribution restrictions; prices UNVERIFIED | `research/QUALITATIVE_SIGNAL_CHINA_AUDIT_FOR_FABLE.md:194-197` `[C]` |

**What the public floor already is.** CSRC disclosure rules require A-share issuers to report top-5 customers and suppliers in the annual report. Many names are masked. Amounts and concentration are public the day the report is filed. HKEX annual reports sometimes name major customers but are not a standardized top-5 table. That is the disclosure graph. CSMAR and Wind SDB are, at root, cleaners of that table plus some inferred edges. They do not create a new physical fact.

**Engineering time a seat actually saves**, if and only if the license allows product use: entity-resolving the *named* counterparties onto a bilingual ID, keeping year-vintages, and mapping A/H dual listings to one issuer. That is weeks, not years — and it is the same work CN-B has to do on the public PDFs. A seat that we cannot display does not save those weeks.

---

## 3 · Evaluation matrix

Legend: **Y** = public primary evidence supports; **N** = public primary evidence denies or the product is the wrong graph; **?** = not on a public page this session; **n/a** = not the product.

| Axis | Wind PDB | Wind SDB | Wind WDS/SAPI | Choice 产业链 / API | iFinD 产业链 / API | CSMAR 供应链 | CNRDS SCRD | QCC industrial + offline | Tianyancha / 企查查 onshore |
|---|---|---|---|---|---|---|---|---|---|
| Relationship coverage (disclosure edges) | industry-chain tree `[S]` | supplier/customer + amounts `[S]` | ? (module subscription) | industry-chain UI `[S]` | industry-chain + 工商库 `[S]` | top-5 + distance + concentration `[V]` | named SCRD sub-db `[V]` | industry-chain mapping `[V]` | registry, not 年报 top-5 |
| A/H coverage | PDB claims A/H/US listed `[S]` | ? | WDS covers 港股 `[V]` | ? | ? | A-share filings `[I]` | A-share `[I]` | USCC-centric KYB `[V]` | mainland 工商 |
| Effective dates | ? | transaction amounts imply period `[I]` | ? | ? | ? | report-period `[I]` | ? | incremental updates offered `[V]` | registry change dates `[I]` |
| Provenance | Wind classification + filings `[I]` | 年报 + inferred `[I]` | ? | 东财研究所 `[S]` | 工商 + 产业 `[S]` | 年报 top-5 `[V]` | academic reconstruction `[I]` | registries + licensed 3p `[V]` | NECIPS / 工商 `[I]` |
| Historical snapshots | ? | ? | FileSync persist `[V]` | ? | ? | panel by report period `[I]` | academic panel `[I]` | offline dump + cadence `[V]` | latest-plus-change |
| Update cadence | terminal | terminal | FileSync / API `[V]` | terminal / API | terminal / HTTP API `[V]` | filing season | academic refresh | daily–quarterly offered `[V]` | registry |
| API | Client API (desktop) `[V]` | via terminal/API ? | Server API, quote `[V]` | terminal-bound quant API `[V]` | HTTP API + SDKs `[V]` | campus web `[V]` | campus web | enterprise API + credits `[V]` | open platform (onshore) |
| Persist / cache | Client API = desktop `[I]` | ? | **local DB sync** `[V]` | Excel export from terminal `[V]` | ? | campus download | campus download | **offline CSV/SQL** `[V]` | vendor-controlled |
| Derived-feature rights | ? public ToS | ? | marketed as internal reuse `[V]` | ? | ? | academic `[I]` | **N** academic-only `[V]` | **N** public ToS §8.1(b) `[V]` | ? |
| Customer-facing derived display | ? | ? | marketed as *internal* systems `[V]` | ? | ? | **N** campus | **N** `[V]` | **N** public ToS §8.1(a)(c) `[V]` | ?; US site blocked `[V]` |
| Pricing | quote `[V]` | quote | quote `[V]` | quote; API via account manager `[V]` | quote | academic / commercial quote | academic | credits + Commercial Agreement `[V]` | SECONDARY 包年 figures |
| Entity IDs | Wind code; 中港美 `[V]` | Wind company ID ? | reference DB `[V]` | EM codes | THS codes + 工商 | CSMAR / stock code | CNRDS / stock code | USCC `[V]` | USCC |
| Lawful Mastermind product use on public terms | **No public grant** | **No public grant** | **Internal only, as marketed** | **No public grant** | **No public grant** | **No** (campus) | **No** | **No** | **No** (geo + PIPL) |

---

## 4 · Vendor cards

### 4.1 Wind PDB / SDB (priority)

**Identity `[S]`.** CEIBS library bulletin (Wind product announcement, dated in the libguide as 2024-01-10) names the pair:

- **产业链数据库 (PDB)** — A-share, H-share, US-listed and other overseas listed companies; tree of upstream/downstream industry nodes down to raw materials and end products.
- **供应链数据库 (SDB)** — upstream suppliers and downstream customers, with transaction amounts, custom addable related firms.

Primary pages on `wind.com.cn` market WFT, EDB, Client API, and WDS. They do **not** currently expose a public PDB/SDB landing page with a data dictionary. The CEIBS/Sohu/Xueqiu 2022–2024 announcements are the best public naming evidence; treat coverage counts on those pages as marketing, not a measured edge list.

**API / persist `[V]`.**

- *Client API* (`wind.com.cn/mobile/ClientApi/zh.html`): desktop, six languages, “中港美及全球” fundamentals. This is a terminal-adjacent workstation API, not an OEM feed.
- *WDS database sync* (`…/WDS/database/zh.html`): FileSync pushes files into the customer's SQL Server / Oracle / MySQL. Local persist is the product. Marketed since 1999 to institutions. Module-level subscription.
- *WDS Server API* (`…/WDS/sapi/zh.html`): enterprise API gateway. Copy: “将万得的数据API快速对外输出，使企业可以快速、低成本的集成到自己的**内部业务系统**”; “系统嵌入”; 股权穿透 as a computed indicator they will run for you.

**License `[V]` on marketing, `[?]` on the WFT click-wrap.** Public WDS/SAPI pages describe *internal* business-system embedding. They do not grant a Mastermind subscriber the right to see a derived Wind graph. The footer “使用条款” page was not recoverable as clean text this session (JS). Pricing is “申请试用 / 联系咨询” only.

**Does it cut our debt?** Only under a written WDS/OEM grant that names SDB (disclosure edges) plus persist + derive + display. A WFT seat + Client API does not. Wind 商业大数据 (2亿+ entities, 2.7亿 executives — `WDS/zh.html`) is the *registry* graph and is PIPL-bearing; it is the wrong graph and the wrong compliance class (`QUAL_DATA_COMPLIANCE` §4.4).

**Pricing.** Quote-only `[V]`. The 2026-07 China qual audit's “~RMB 30-40k+/seat” remains **UNVERIFIED** and is not reused as a fact here.

### 4.2 Choice (东方财富)

**Product `[S]/[V]`.** `choice.eastmoney.com/dataservice/industrychain` exists as a Choice 产业链 product URL `[V]` (page is JS-heavy; body not extracted). Baike / university trial notices describe a dual-system industry-chain map and an Excel plugin `[S]`.

**API `[V]`.** `quantapi.eastmoney.com` tells you to install the Choice terminal to unlock the API command generator. A modal: “开通Choice数据量化接口权限请联系您的客户经理或拨打客服热线400-620-1818.” The API is a *terminal entitlement*, not a standalone OEM feed.

**License / display.** No public redistribution grant found. Same shape as every other PRC terminal: research seat ≠ product license.

**Does it cut our debt?** No, on public terms. Choice is a cheaper Wind-shaped terminal. It does not remove CNInfo PDF parsing unless an OEM clause we do not have says so.

### 4.3 iFinD (同花顺)

**Product `[S]/[V]`.** Tsinghua SEM 2025 training lists 产业链中心 and 产业链知识图谱 as iFinD features `[S]`. `quantapi.51ifind.com` documents Python/MATLAB/R/C++/C#/Java SDKs and an HTTP API user manual `[V]`. Beihang 2023 brochure claims a 非上市公司企业库 and 立体产业链数据中心 `[S]`.

**API `[V]`.** Real HTTP API + multi-OS SDKs. Still sold as an iFinD entitlement (`ft.10jqka.com.cn` / 952555), not as an OEM display license.

**License / display.** No public grant for customer-facing derived display found this session.

**Does it cut our debt?** Same as Choice. The 工商库 is the registry graph (PIPL). The 产业链图谱 is an industry taxonomy, not a point-in-time top-5 disclosure panel.

### 4.4 CSMAR 供应链研究数据库

**Coverage `[V]`.** Tsinghua PBC School of Finance library trial (2021-10-09) and BNU Zhuhai trial (2025-04-03): listed-company **top-5 customers and suppliers**, purchase/sales amounts, geographic distance, concentration, network metrics, plus counterparty basic / shareholder / director / investment fields. Access path: 数据中心 → 公司研究系列 → 供应链研究. Official host `data.csmar.com`.

**This is the disclosure graph, already cleaned.** It is exactly the CNInfo 年报 table plus derived distance/network columns.

**License.** Two-track vendor `[V]`: academic/WRDS path sold to universities (`wrds-www.wharton.upenn.edu`, last-updated 2025-08-24 on the one-sheet), and a separate institutional 红楹 line that claims exchange/CSRC provenance and API/loader delivery (`csmar.com` EN + 金融数据服务). Neither public page grants a foreign SaaS the right to persist a derived graph and display it to customers. Campus-IP trials are not a product license. Commercial 红楹 redistribution terms are unpublished — quote-only, assume display is forbidden until a written grant says otherwise. Entity IDs on the public pages are exchange security codes, not a documented USCC join.

**Does it cut our debt?** It would save the PDF-parse if and only if a commercial license allowed persist + derive + display. An academic login does not.

### 4.5 CNRDS SCRD

**Coverage `[V]`.** University catalogs (SCNU, UESTC, Renmin) list **中国上市公司供应链研究数据库-SCRD** as a named CNRDS sub-database.

**License `[V]`.** CNRDS registration copy (`cnrds.com` → `/Home/Login`) publishes 《CNRDS平台数据使用协议》 with three stacked bars: (2) do not transfer, sell, or disclose any part of the data to any third party in any form; (3) use only in a research project on which the registrant is a named author; (4) “承诺只把数据库数据用于学术研究，不用于商业目的.” Unpurchased schools are refused registration. Do not buy, borrow, or tunnel a campus CNRDS login into Mastermind.

### 4.6 QCC (企查查 international) — the one readable commercial ToS

QCC TECH PTE. LTD. (Singapore) is the offshore face of 企查查. `qcckyc.com`, ToS effective **9 July 2026** `[V]`.

**Product `[V]`.** 700M+ entities, 900M+ relationships, USCC-aware KYB, industrial-chain mapping (“upstream suppliers, downstream customers”), featured offline datasets (CSV / Excel / MySQL / SQL Server; daily–quarterly incremental). Section 4.1(g) of the ToS names “curated offline datasets and supply-chain intelligence.”

**License — load-bearing quotes `[V]`.**

> §6.1 Licence: “a limited, non-exclusive, non-transferable, non-sublicensable, revocable licence … **solely for your own internal business and compliance purposes**.”

> §8.1(a) you shall not “**resell, sublicense, redistribute, republish, or otherwise make available to any third party any Outputs**.”

> §8.1(b) you shall not “**aggregate, repackage, or create derivative datasets** from any Outputs, or use any Outputs … to **build, train, evaluate, or improve any product, dataset, model, scoring system, automated data product**, or competing service.”

> §8.1(c) you shall not “provide access to or share any Outputs with any third party other than as reasonably necessary for your own **internal** business operations and compliance processes.”

> §2(d) users must “**not [be] located in China mainland**. The Services are not offered to users located in China mainland.”

> §13.3(b) on termination: delete cached or stored Outputs.

A Commercial Agreement can override (order of precedence §1.3). The *public* terms are a complete bar on Mastermind derived-feature and derived-display use. Offline persist is offered, then clawed back as internal-only.

**PIPL.** Outputs include key personnel, UBO, legal representative. That is personal data. `QUAL_DATA_COMPLIANCE` §4.4 collects impersonal aggregates only. Using QCC as a China supply-chain spine would require a new §5 compliance-ledger entry *and* a Commercial Agreement that carves display — two gates, neither open.

**Does it cut our debt?** It is the wrong graph (KYC / 工商 / industrial taxonomy) sold to the wrong user (internal compliance), under a ToS that forbids the use we would buy it for.

### 4.7 Tianyancha / onshore 企查查

**Tianyancha `[V]`.** `tianyancha.com/data` on 2026-08-19 from a US IP (104.36.50.55): “根据相关法律规定，当前所在地区暂不支持访问 / According to relevant legal regulations, access is temporarily not supported in your current location.” An onshore 工商 API we cannot even open from the operator's default network is not a Mastermind spine.

**Onshore 企查查.** `openapi.qcc.com` redirects to the QCC KYC site `[V]`. Treat onshore open-platform pricing (SECONDARY 包年 figures on aggregator blogs) as irrelevant until a mainland entity can contract and a cross-border persist path survives PIPL / DSL review. That review is not this packet.

### 4.8 Mobile / ecommerce — secondary, optional, and the wrong problem

Wind WDS lists **线上销量** as an alt-data module `[V]`. QuestMobile, 易观, 艾瑞, Sensor Tower / data.ai are attention or app-store panels. They do not resolve A-share counterparties, do not give relationship effective dates, and do not replace 年报 top-5. They do not reduce *this* normalization debt. Do not buy them for GROK-CN-E.

Western FactSet Revere / Bloomberg SPLC: useful on listed-to-listed global edges; thin on unlisted PRC counterparties and on A-share 年报 vintages. One-line contrast only; not a substitute. WRDS lists Revere as a paired catalog item next to CSMAR; that is not a license.

**聚源 / Gildata (恒生聚源).** Official `gildata.com` is a JS SPA; this session extracted no public 供应链 API, data dictionary, or redistribution page. Do not conflate with `go-goal.com` (朝阳永续, earnings-estimate vendor). Treat as UNKNOWN / quote-only; not a reason to buy.

**ImportGenius / Panjiva.** Foreign bill-of-lading graphs (US CBP and selected other countries). ImportGenius self-serve pricing is public (USA Essentials $229/mo; Global Enterprise from $1,999/mo) `[V]` and still does not map GACC microdata onto A-share issuers via USCC. Wrong graph for this debt.

---

## 5 · The license gate (why table count is not the question)

Mastermind is a customer-facing product. `docs/QUAL_DATA_COMPLIANCE.md` §3 (mosaic standing rule) requires a written compliance review before any source that is not simultaneous public release enters the entity-resolved store `[V]`.

A lawful purchase must clear **all four** in one written grant:

1. API or bulk delivery (not a human terminal).
2. Bulk local persist / cache (a nightly store).
3. Derived-feature rights (concentration, graph distance, read-through flags — the thing we would actually ship).
4. Customer-facing *derived* display (subscribers see our features, not the vendor screen).

| Source | 1 API | 2 Persist | 3 Derive | 4 Display |
|---|---|---|---|---|
| Wind WFT + Client API | workstation | no public grant | no public grant | no public grant |
| Wind WDS FileSync / SAPI | yes, quote | yes, internal | marketed internal | no public grant |
| Choice quant API | terminal-bound | Excel | no public grant | no public grant |
| iFinD HTTP API | entitlement | no public grant | no public grant | no public grant |
| CSMAR campus | web extract | campus | academic | no |
| CNRDS | web | campus | **forbidden** | **forbidden** |
| QCC public ToS | yes | then must delete | **forbidden** | **forbidden** |
| Tianyancha from US | site blocked | — | — | — |
| CNInfo 年报 (public) | portal | we already may store metadata; bodies are public disclosure | our own parse is our work | derived display of *public* facts is the mosaic path we already use |

The last row is the boring baseline. It is the only row that is green on rights. It is also the work CN-B / a future CNInfo-body wave already owe.

---

## 6 · What would flip this verdict

A single PDF from Wind (preferred), Choice, iFinD, CSMAR-commercial, or QCC enterprise sales that, in operative language, grants Mastermind (or a named Macro/Mastermind contracting entity):

- SDB-class or 年报-top-5-class disclosure edges (not merely an industry taxonomy);
- A/H and unlisted counterparty IDs with a documented join key (USCC and/or Wind/EM/THS company ID);
- point-in-time vintages (report period, not latest-only overwrite);
- named persist + derive + customer-facing derived-display rights;
- a quote.

Absent that document, do not reopen. A sales deck, a seat trial, or “we have 产业链” is not the document.

---

## 7 · Standing constraints this packet does not reopen

- `docs/QUAL_DATA_COMPLIANCE.md` §2.2 — China expert networks remain a hard legal line.
- §2.3 — card/transaction panels remain excluded.
- §4.4 — impersonal aggregates only; no personnel/UBO spines.
- `research/LONG_HOLD_THESIS_MASTERPLAN_BY_FABLE.md` LH-R9 / SKIP-ALL 2026-07-05 — paid supply-chain stays deferred.
- `research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md` — a token is not a commercial grant. That gate is CN-A's problem, not a reason to buy Wind.
- `DNR:KILL-CN-SUPPLY-ABSORPTION` is a *price-only absorption factor* kill, not a supply-chain-graph kill. Do not cite it as forbidding this diligence; also do not treat this diligence as resurrecting that factor.

---

## 8 · Next actions (ordered)

1. **Do not purchase.** Do not open a Wind / Choice / iFinD / CSMAR / CNRDS / QCC / Tianyancha procurement thread from this packet.
2. **Keep the public disclosure floor.** Any later CNInfo-body wave parses 前五名客户/供应商 from reports we are already allowed to read, stores vintages, and entity-resolves *named* counterparties on the CN-B identity layer. Masked 客户A rows stay masked.
3. **Do not ingest registry PII** (legal reps, UBO, directors) as a supply-chain substitute.
4. **Reopen only** on the written OEM grant in §6. File that grant under the TuShare-style receipt pattern (hashed, allowlisted, seven scope booleans plus a display boolean). Until then this workstream is parked.

---

## Appendix A — Primary URLs touched 2026-08-19

| URL | Role |
|---|---|
| https://ceibs.libguides.com/blogs/cn/news/newresources/home/Wind | PDB/SDB naming (library bulletin) |
| https://www.sohu.com/a/583032903_99992453 | 2022 Wind 产业链/供应链 announcement |
| https://www.wind.com.cn/mobile/WDS/zh.html | WDS overview; 商业大数据; 线上销量 |
| https://www.wind.com.cn/mobile/WDS/database/zh.html | FileSync local persist |
| https://www.wind.com.cn/mobile/WDS/sapi/zh.html | Server API; internal-system embedding |
| https://www.wind.com.cn/mobile/ClientApi/zh.html | Desktop Client API |
| https://choice.eastmoney.com/dataservice/industrychain | Choice 产业链 product URL |
| https://quantapi.eastmoney.com/Cmd/ShowPromotionpage?from=web | Choice API is terminal-bound |
| https://quantapi.51ifind.com/gwstatic/static/ds_web/quantapi-web/download.html | iFinD SDK / HTTP API |
| https://tushare.pro/document/2?doc_id=405 | TuShare personal / non-commercial licence |
| https://data.csmar.com/ | CSMAR host |
| https://lib.tsinghua.edu.cn/finance/info/1198/1952.htm | CSMAR 供应链 trial description |
| https://library.bnuzh.edu.cn/zy/zydt/b43a2582f3dc43aa9490d8cd5b43c2bb.htm | same, 2025 |
| https://www.cnrds.com/ | academic-only click-wrap (no transfer/sale/third-party; named-author research only; no commercial use) |
| https://www.csmar.com/en/index.html | CSMAR EN: Supply Chain Research + Related Party Transaction listed |
| https://www.csmar.com/channels/金融数据服务.html | 红楹 institutional track; unpublished SaaS-display terms |
| https://wrds-www.wharton.upenn.edu/pages/about/data-vendors/china-stock-market-accounting-research-csmar/ | CSMAR academic/WRDS path |
| https://www.gildata.com/ | 聚源 SPA; no public graph API extracted |
| https://www.importgenius.com/pricing | BOL graph; wrong problem; public price band |
| https://www.qcckyc.com/terms-conditions?type=1 | QCC ToS 2026-07-09 |
| https://www.qcckyc.com/industrial-chain-intelligence | QCC industry-chain, internal systems |
| https://www.qcckyc.com/featured-offline-datasets | offline persist, internal |
| https://www.tianyancha.com/data | US geo-block |
| https://www.qcckyc.com/ | QCC KYC home (openapi.qcc.com redirect) |

## Appendix B — Repo paths

- `collectors/china_filings.py` — metadata-only CNInfo.
- `collectors/china_fundamentals.py` — no counterparties.
- `collectors/hk_ah_official.py` — A/H premium, not identity.
- `collectors/china_tushare_spine.py` + `research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md` — commercial-grant gate.
- `docs/QUAL_DATA_COMPLIANCE.md` — public-source / PIPL / mosaic rule.
- `research/LONG_HOLD_THESIS_MASTERPLAN_BY_FABLE.md` — SKIP-ALL paid supply-chain.
- `research/QUALITATIVE_SIGNAL_CHINA_AUDIT_FOR_FABLE.md` §9 — prior stretch rating.
