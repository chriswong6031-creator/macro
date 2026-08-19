# CN-F — Sector Clock Census

**Lane:** GROK-CN-F (Sector Clock Census)
**Date:** 2026-08-19
**Reconciliation pin:** `origin/main` @ `12f60066e324` (probe tree `e76e0d0c8ab5`; ff-only before commit, no collector/engine drift in the window)
**Authority of this document:** NONE. Research census only. No production scoring, no Prophet change, no new store, no collector.
**Parent:** specialist-lobe bar in the user commission; US analog lobes are BioCatalyst and Defense/Government Revenue. China native-data prior art: `research/china_native_data/`. Sibling lanes CN-B (entity resolver), CN-C (SOE demand), CN-D (project EIA source map) are in flight and are owners to adopt, not to duplicate.

Claim tags: **PRIMARY SOURCE VERIFIED** · **CODE VERIFIED** · **INFERRED** · **UNKNOWN**.

---

## 0. One-sentence finding

Two of six candidate specialist lobes pin an earlier unique clock this session — **Bio/Medtech (CDE/CTR)** and **EV/Auto (MIIT vehicle-catalog batches)**. Grid and Materials share one MEE project-EIA tape that CN-D is already mapping; that is one project clock, not two lobes. Semis' earlier unique clock is the US BIS/Federal Register tape the house already owns. AI/Software and Games do not pin a dated public event tape this session, so they do not earn a lobe.

**Stop rule honored:** a sector with no earlier unique clock does not earn a lobe.

---

## 1. Required row

| sector | early source | event | known-at quality | lead mechanism | issuer mapping | history | rights | existing Mastermind overlap | first useful user workflow | **lobe?** |
|---|---|---|---|---|---|---|---|---|---|---|
| Bio/Medtech | CDE `cde.org.cn` (home 200 this session); China CTR `chinadrugtrials.org.cn` (home 200). NMPA portal `nmpa.gov.cn` **412 WAF**. List/API pages on CDE/CTR returned **HTTP 202 JS-challenge** from this egress. PRIMARY SOURCE VERIFIED (homes + CDE IA). | CDE homepage names five dated clocks: 受理品种信息, 审评任务公示, 优先审评公示, 临床试验默示许可, 上市药品信息. CTR is the China analog of ClinicalTrials.gov registration/status. | **Source exists; list tape not retrieved this session.** House clocks if built: `source_available_at` = CDE/CTR publish date; `observed_at` = first house fetch (WAF may lag). Analog of BioCatalyst `effective_at ≤ known_at ≤ observed_at` (CODE VERIFIED `engine/biocatalyst/operational_store.py`). | Acceptance / implied clinical license / priority-review listing precedes NMPA approval and revenue. Same shape as US PDUFA/IND/approval, different regulator. | Sponsor/MAH name → A-share/HK ticker. **No house map.** CN-B is the in-flight resolver. Dual-listed CN names already appear on US ClinicalTrials.gov (BioCatalyst overlap, not NMPA). | CDE has published 受理/默示许可 for years (INFERRED from numbered IA; **row contents not pulled this session**). | Official PRC disclosure. Derived-signals posture (same as `china_official`). | US BioCatalyst owns FDA/openFDA/ClinicalTrials.gov only (CODE VERIFIED `collectors/openfda.py`, `collectors/clinicaltrials.py`, `collectors/biocatalyst/`, program `biocatalyst`). **Zero NMPA/CDE/CTR collectors.** XLV→CN pharma weekly confirmer is a *read-through*, not a China clock (`reports/c-hc-readthrough-phase0.md`). `china_official` organs do not include CDE. | Watch: this MAH just printed CDE 受理 / 默示许可 / 优先审评; here are mapped tickers. Display/research only. | **YES** |
| Grid/Power | MEE 建设项目环评 (`mee.gov.cn/ywgz/hjyxpj/jsxmhjyxpj/`) **200**. Three live substages: 项目受理情况, 拟审查项目公示, 已批准项目公告. NEA 政府信息公开 `zfxxgk.nea.gov.cn` **200** but `xmsp.htm` **404**. SGCC e-procurement is a JS SPA. PRIMARY SOURCE VERIFIED. | Project EIA file **accepted** → **proposed-review公示** (10 working-day comment window on the 2026-08-06 acceptance notice) → **approval decision**. This week's acceptance table named 国铁集团 railway + 大唐 700万吨煤矿. Proposed-review tape this session is coal mines, coal-to-olefins, coal-to-liquids, gas storage — energy/materials projects, not grid-equipment tenders. | Dated HTML 公示. Latest acceptance window 2026-07-29–08-04, published 2026-08-06. `source_available_at` = 公示 date. PIT `first_seen` would be house-stamped. | Acceptance/review/approval of a project precedes capex, equipment orders, and earnings. Years of lead, same *shape* as US LBNL interconnection queue. | `建设单位` is in the HTML table (PRIMARY SOURCE VERIFIED). SOE-heavy. Needs CN-B + CN-C, not a new mapper. | Dated archive on the same MEE columns (2025–2026 visible this session). | Official MEE disclosure. | **US** `engine/power_scarcity.py` + `collectors/eia.py` + `collectors/lbnl_queue.py` already own the US physical-capacity clock. `china_official` is policy-language (State Council/PBOC/NDRC/CSRC), not project EIA. **CN-D is the sibling owner of this source map.** | Do **not** mint a Grid lobe. Adopt CN-D's project-EIA map. First workflow if CN-D ships: "this project entered EIA review; owner + supplier names." | **NO** (shared project clock; adopt CN-D) |
| EV/Auto | MIIT 装备工业一司 公告 HTML. Latest: 工业和信息化部公告2026年第21号. PRIMARY SOURCE VERIFIED this session. CPCA `data.cpcadata.com/api/chartlist` **200 JSON** (coincident monthly sales — not a lead clock). | Three numbered catalogs in one 公告: 《道路机动车辆生产企业及产品》第409批; 《享受车船税减免优惠的节能/新能源车型目录》第88批; 《减免车辆购置税的新能源汽车车型目录》第33批. Attachments are `.doc`. | 成文日期 **2026-08-12**; 发布日期 **2026-08-13 09:15**. Hard, dated, official. Index page `/zwgk/zcwj/wjfb/gg/index.html` is a jpaas JS shell (matches `china_official_corpora.py` MIIT-deferred note, CODE VERIFIED); the *article* HTML is complete. | Catalog listing is a 行政许可. A model must be on 产品公告 / 购置税减免目录 **before it can be sold**. That is earlier than CPCA wholesale and earlier than OEM earnings. | OEM names live in the `.doc` attachments, **not** in the HTML stub (UNKNOWN until a rights-safe parse). Mapping is name→ticker; cleaner than bio MAH. | Batch numbers (409 / 88 / 33) imply a long numbered history. Depth not reconstructed this session. | Official MIIT 公告. Attachments are `.doc` (not JSON). Redistribute derived signals, not the Word files. | CPCA cataloged in `research/china_native_data/` (2026-07-25, live JSON) and planned as `collectors/china_cpca.py` — **not built** (CODE VERIFIED: no `china_cpca` collector). CPCA is confirmatory, not the lead. No MIIT catalog collector. | Watch: a new 购置税减免 / 产品公告 batch printed; OEM (and later supplier) exposure. Display/research only. | **YES** |
| Semis / Advanced Manufacturing | No China-native dated tape pinned. US Federal Register / BIS Entity List **already collected**. CODE VERIFIED `collectors/federal_register.py`, `engine/policy_calendar.py` (`_ENTITY_LIST_THEMES` includes `ai_semiconductors`, `semicap_equipment`, `memory_storage`). MEE EIA covers some fab/chemicals projects — **same clock as Grid/Materials**. | US: Entity-List additions and semiconductor-manufacturing export-control rules. CN: occasional 大基金 / NDRC policy language (china_official adjacent, not a unique sector calendar). | FedReg `publication_date` + `_first_seen` already exist. CN policy notices are narrative, not a structured issuer calendar. | US BIS rewires CN semis supply chains *before* CN filings. That is an earlier unique clock — **already owned**. A second CN lobe would duplicate it. | FedReg is agency×term→theme, not CN ticker. CN issuer map would be a consumer of the existing policy calendar, not a new lobe. | FedReg backfill 2015→ (program W0b). | US government public records (already registered). | Thematic Foresight / HBM / CPO / AVGO–NVDA studies; `policy_calendar` Entity-List sub-signal; china-global-theme read-throughs. `DNR:KILL-CN-SUPPLY-ABSORPTION` kills a different construction. | Consume existing policy-calendar Entity-List events into CN names via CN-B. Do not charter a CN semis lobe. | **NO** |
| AI / Software / Games | NPPA `nppa.gov.cn` **200**. CAC `cac.gov.cn` **200**. HuggingFace/GitHub collectors are global activity (coincident). US `collectors/gaming_nj.py` etc. are **monthly revenue ~20–25d after month-end** — coincident/lagging, US-only. | Games: 2018 NPPA 行政许可事项清单 still lists **出版国产网络游戏作品审批** and 境外授权电子出版物（含互联网游戏作品）审批 (PRIMARY SOURCE VERIFIED). **No 2026 dated 版号 batch tape located** on 头条 / 要闻 / 通知公示 / guessed historical paths (those 404). Product query is a *publisher registry*, not a game-ISBN event tape. AI: CAC is a news homepage; no structured 生成式AI备案 calendar retrieved. | 许可 *category* exists. Dated *event tape* **not pinned this session**. china_sector_cycles narrative treats 版号 as a structural driver (INFERRED, not a collector). | 版号 historically precedes launch and revenue. Without a reconstructable dated batch, that mechanism is a story, not a clock. | Publisher/operator name → Tencent/NetEase/etc. Mapping is feasible **if** a batch tape exists. | Historical batches exist in the public record (INFERRED). House has none. | Official if a tape is found. Query portal ToS unread (UNKNOWN). | `china_sector_cycles` 传媒 DNA names 版号 as a driver (narrative, not a feed). US gaming collectors are the wrong market and the wrong clock class (lagging revenue). | None until a dated 版号 / CAC-备案 tape is pinned. Do not charter from narrative DNA. | **NO** |
| Materials / Mining / Chemicals | Same MEE project-EIA tape as Grid (PRIMARY SOURCE VERIFIED). National 排污许可证平台 `permit.mee.gov.cn` **200**. C1 commodity→sector is a **price-transmission** study, not a China project clock. | EIA acceptance/review/approval of mines, coal-chemicals, cement, battery-materials plants. This session's proposed-review list is dominated by 煤矿/选煤厂/煤制烯烃/煤制油. 排污许可 is an operating-permit tape (closer to coincident compliance than to a multi-year lead). | Same as Grid row. | Same project-lead as Grid. Not unique *to materials as a separate lobe*. | Same `建设单位` column. | Same MEE archive. | Same official disclosure. | C1 commodity-sector prereg (Canada/HK ETFs, not CN project EIA). `DNR:KILL-COMMODITY-XSEC-MOM`. SHFE/CZCE/GFEX are positioning tapes (coincident). GACC English trade is macro, not issuer-level. **CN-D owns the EIA source map.** | Adopt CN-D. Do not mint a second materials lobe on the same EIA clock. | **NO** (same clock as Grid; adopt CN-D) |

---

## 2. What "earlier unique clock" meant in this census

Borrowed from the US lobes that already earned their keep, not invented:

- **BioCatalyst:** Drugs@FDA / ClinicalTrials.gov events are dated, sector-specific, and map to sponsors. CODE VERIFIED: openFDA records NEW approval and label-expansion; clinicaltrials records Phase-3 start and halt; BioCatalyst `known_at` is a first-class field.
- **Defense / Government Revenue:** SAM opportunity → USAspending award is a pipeline-before-revenue clock.
- **US Grid:** LBNL interconnection queue is years of physical lead (`engine/power_scarcity.py`).

A **coincident print** (CPCA monthly wholesale, US state gaming revenue, SHFE inventory, China news wire) is unique data. It is not an earlier clock. It does not earn a specialist lobe.

A **shared project clock** (MEE EIA) can earn one organ. It cannot earn two sector lobes.

---

## 3. Egress and access bounds (bind the nulls)

Probes used a browser UA, 15–18s timeout, this machine's egress (same class of bound as `research/china_native_data/SOURCE_CATALOG_MACRO_POLICY_HK.md`: datacenter IP, WAF-sensitive).

| Endpoint | This session | Bound |
|---|---|---|
| CDE home | 200 | List pages 202 JS-challenge — **do not declare CDE dead**; declare list-API gated from this egress |
| CTR home | 200 | Search/list 202 JS-challenge — same |
| NMPA home | 412 | Portal blocked; CDE is the working door |
| MIIT catalog **article** | 200, full 公告 metadata + `.doc` attachments | Index is jpaas shell (prior art, CODE VERIFIED) |
| MEE EIA substages | 200, dated tables | National 项目 only; provincial EIA not probed |
| NPPA home / 通知公示 / 许可清单 | 200 | Dated 版号 batch **not found**; 404 on guessed historical paths |
| NHSA | timeout | NRDL not probed further |
| `sapp.gov.cn` | DNS fail | Do not use |
| `eia.mee.gov.cn` | DNS fail | Use `mee.gov.cn/ywgz/hjyxpj/` |

Studio residential egress may see CDE list pages that this probe did not. That is an access fact, not a clock fact. Re-probe with `scripts/probe_china_sources.py` before any collector design; **do not add CDE/MIIT/MEE/NPPA to that harness as a nightly job** (render-budget law; the existing harness is manual-only, CNH-R3).

---

## 4. What this census authorizes

**Nothing to build.** PASS-0 already froze specialist-adapter *builds* until the Evidence Mesh K1 contract. This census only answers the lobe bar.

Allowed next, after owners adjudicate:

1. Bio: a CDE/CTR source-rights + access probe from the runner that would actually collect, owned as an extension of **BioCatalyst** (China regulator tape), not a second bio program.
2. EV: a MIIT 公告 article parser (HTML metadata is enough to start; `.doc` attachments are a separate rights/parse question), new collector, China-native program — CPCA may confirm, never lead.
3. Grid/Materials: **wait for CN-D**. Do not start a parallel EIA collector in this lane.

Forbidden:

- Six specialist Neural Web lobes.
- A China BioCatalyst fork that copies US stores.
- Treating CPCA, 版号 narrative DNA, or FedReg-already-owned BIS events as new lobe charters.
- Scoring, Prophet, or sizing from any of the above.
