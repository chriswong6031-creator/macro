# GROK-CN-B — PRC Corporate Entity Resolver Bake-Off

**Lane:** GROK-CN-B · **Date:** 2026-08-19 · **Pin:** `origin/main` @ `620acf86f242`
**Seat:** Grok 4.6 reconnaissance. **Authority:** NONE. This is evidence for Fable/Sol. It does not freeze architecture, rank, or buy anything.
**Workstream:** `WS:ALPHA-INTELLIGENCE-INTEGRATION`
**Rule (commission):** vendor IDs are never Mastermind canonical identity.

---

## Verdict

**NO-BUY Qichacha, Tianyancha, Qixinbao, Aiqicha, or Jinghai as a Mastermind identity layer or as a persisted parent/subsidiary graph.**

Do not wire a collector. Do not store a vendor key as a company id. Do not treat “实际控制人” from a commercial graph as issuer parent.

The job these vendors sell — hostile listed-parent / subsidiary resolution — is exactly the job their contracts, geography, and derived-model fields prevent a non-PRC-domiciled Mastermind from using lawfully. The fields that *are* identity (USCC, legal name, A/H listing keys, 控股股东 as of a filing date) are public records this session already pulled from CNINFO, Sina holder tables, and GLEIF without a commercial registry.

Strongest runner-up: a later **query-time-only** Qichacha (or Qixinbao) pilot, and only if all four flip conditions hold. They do not hold today.

Flip to a paid pilot only if:

1. A PRC-domiciled contracting entity exists and completes 企业认证;
2. Written contract permits the specific use (query-time candidate generation; no raw redistribution; no cross-border store of vendor graph / scores / IDs);
3. The VPS/runtime that would call the API is inside mainland China, or the vendor issues a written overseas-IP exception (Tianyancha’s own about-page and Qichacha’s 2026-06 agent ToS currently forbid overseas subjects and overseas IPs);
4. A 40-name hostile re-run against the frozen sample in `CN-B_SAMPLE_FRAME.json` beats CNINFO+filings on **exact issuer parent with effective dates**, not on USCC lookup.

Until then the house identity stack for PRC names is: **USCC (PRC legal person) + LEI when issued + listing keys as aliases**. Parent/control is a dated filing fact, not an ID.

---

## What was actually measured this session

| Probe | Result | Tag |
|---|---|---|
| House Qichacha / Tianyancha / Qixinbao key names | None in process env, `.env`, `.env.example`, or `config.yml` | CODE VERIFIED |
| House identity today | `engine/entity_resolver.py` is text→ticker only. No USCC store. No parent graph. Tushare plane is moneyflow/valuation, not registry. | CODE VERIFIED |
| Tianyancha website + about page from this session’s US IP `104.36.50.55` | Geo-block page: “当前所在地区暂不支持访问”. Search-indexed official about text: overseas subjects may not register, log in, or access; overseas IP forbidden. | PRIMARY SOURCE VERIFIED |
| Qichacha Open API catalog `https://openapi.qcc.com/dataApi` | Loaded from the same US IP. 167 APIs. Identity-useful priced endpoints exist. Control / penetration / history / group / HK are **面议**. | PRIMARY SOURCE VERIFIED |
| Qichacha 智能体数据平台 user agreement (updated 2026-06, still posted) | Overseas subjects and overseas IPs forbidden. Data obtained through the service must be stored/used **inside the PRC** and must not be transmitted overseas or made queryable by any overseas person. | PRIMARY SOURCE VERIFIED |
| Qichacha Open API ToS `mapi.qcc.com/services/protocol/tos` | HTTP fetch failed this session. Do not infer Open-API ToS from the agent-platform ToS; treat cross-border rights as **UNKNOWN** on the Open API until Legal reads the signed PDF. The agent-platform clause is still the live published Qichacha posture. | UNKNOWN (Open API) / PRIMARY (agent) |
| GLEIF API, PetroChina LEI `529900RPY4YG47TRSV05` | `registeredAs` = USCC `91110000710925462X`. LEI status **LAPSED**. Parent links are reporting exceptions, reason **`NO_KNOWN_PERSON`**. Record carries vendor map field `qcc=QCNUHCT69B`. | PRIMARY SOURCE VERIFIED |
| GLEIF exact-name batch (Tencent, Alibaba, SMIC, NIO, BYD, China Mobile, CATL, WuXi, SAIC, CSSC, Zijin) | Tencent/SMIC/SAIC/CSSC: 0 hits on the obvious English legal name. Alibaba `registeredAs=90722` (Cayman, not USCC). China Mobile Limited `registeredAs=21330874` (HK number). NIO Cayman `294239`. BYD Company Limited resolved to **BYD Electronic** (wrong legal person). Almost every hit: parent = reporting exception. Several records carry a `qcc` field. | PRIMARY SOURCE VERIFIED |
| CNINFO `ak.stock_profile_cninfo` on the sample’s A-share codes | **110 / 111** returned legal name, English name, A/H codes, 曾用简称, setup/list dates. The only miss is delisted 乐视网 `300104`. | PRIMARY SOURCE VERIFIED |
| Sina `ak.stock_main_stock_holder` on a 36-name hostile listed subset | **23 / 36**. All 688 STAR names in the attempt failed. Several “largest holders” are HKSCC / 香港中央结算代理人 or a BVI intermediate, not the group parent. | PRIMARY SOURCE VERIFIED |
| Frozen sample | `CN-B_SAMPLE_FRAME.json` — **150** real entities, stratified. | CODE VERIFIED |

A live 100–200 call bake-off against Qichacha/Tianyancha APIs was **not** run. There is no key, and the published overseas clauses make a US-IP trial the wrong test. Accuracy percentages invented from CSDN/reseller blogs are not used as evidence.

---

## Bake-off table

Scoring is against the **hostile listed-parent / subsidiary job**, not against KYC name-lookup.

Legend: **Y** = documented and usable from this seat · **P** = documented but 面议 / incomplete / model · **N** = blocked, missing, or wrong object · **U** = not verified this session.

| Measure | Qichacha Open API | Tianyancha Open API | Qixinbao | Aiqicha (Baidu) | Jinghai (reseller) | GLEIF (free) | CNINFO + Sina holders (free, used tonight) | GSXT / 国家企业信用信息公示系统 |
|---|---|---|---|---|---|---|---|---|
| Reachable from this session’s US IP | Catalog **Y**; API sale **U** | Website **N** (geo-block) | U | U | U | **Y** | **Y** | Hostile CAPTCHA; no API |
| Overseas subject / overseas IP | Agent ToS **N**. Open-API ToS unread. 企业认证 required. | Official about **N** | Same class (PRC reseller) | Same class | Same class | **Y** | **Y** | Public, but anti-bot |
| Exact **listed issuer** (not opco / not group) | P — search returns a 主体; VIE/red-chip listed issuer is often the Cayman/HK company, which they also index, but the default Chinese-name hit is the PRC opco | P — same shape | P | P | P | P — when the LEI is the listed issuer (Alibaba Cayman yes; Tencent 0-hit tonight) | **Y** for A-shares (110/111). **N** for delisted. HK profile separate. | Y for PRC legal person only |
| Ownership / control | P — 股东 2.00 元; 实际控制人 / 受益所有人 / 集团 **面议**. These are vendor models, not filings. | P — 疑似实际控制人 / 最终受益人 advertised. Secondary price list ~0.15 元 basic, group 0.10–0.50 元 (CSDN 2026-07-01, not official). | P — advertised 12-layer penetration (secondary) | P | P | **N** for the motivating SOE: PetroChina parent = `NO_KNOWN_PERSON` | P — 控股股东 when Sina returns a group name (中煤集团, 国能投, 中核集团). **N** when it returns HKSCC / BVI. STAR **N**. | P — registered shareholders only; no listed-issuer control |
| Effective dates | P — 变更记录 1.00 元; historical shareholder / 工商 **面议** | P — 变更记录 advertised | U | U | U | P — event groups exist; parent exception has null validFrom/validTo | **Y** on holder table 截至日期 / 公告日期 (2026-03-31 / 2026-04-07 / 2026-06-30 observed) | P — change filings, not a clean API |
| Historical legal names | P — 历史工商信息 921 **面议** | P — advertised | U | U | U | P — otherNames empty on PetroChina | **Y** — 曾用简称 (中国船舶 → `中国船舶>> *ST船舶`) | Y (public change log) |
| Unified social credit code | **Y** — 工商信息 410 @ **0.20 元/次**; search 886 @ 0.10 元 | **Y** — baseinfo advertised | **Y** | **Y** | **Y** (example payload tonight showed `creditNumber`) | **Y** when `jurisdiction=CN` and `registeredAs` is 18-char USCC. **N** for Cayman/HK issuers (Alibaba 90722, China Mobile HK 21330874) | **N** — CNINFO profile has no USCC field | **Y** — the issuing register |
| Subsidiaries | P — 对外投资 884 @ 1.00 元; 十层穿透 / 控制企业 **面议** | P — 对外投资 / 集团成员 advertised | P — 12-layer claim (secondary) | P | P | P — children links exist; not used as a PRC project-company census | **N** as a graph. Annual-report notes only. | P — outward investment in annual reports |
| Response consistency | U (no key) | U (blocked) | U | U | U | **N** as a search tool — exact legalName is both 0-hit and 70k-hit; BYD Company Limited → BYD Electronic | **Y** on CNINFO (110 consecutive listed hits). Sina holders inconsistent by board. | U |
| API field provenance | P — descriptions say 国家企业信用信息公示系统 for 股东; 实际控制人 mixes “大数据 / 官方公示 / 疑似” | P — “政府公开等数据” + vendor graph | U | U | U | **Y** — RA000092, `validatedAs` USCC, `FULLY_CORROBORATED` on PetroChina; still LAPSED | **Y** — 巨潮 / 新浪财经 pages | **Y** — the register |
| Cache / persistence rights | **U** on Open API. Agent ToS: no overseas store, no overseas query. Typical commercial stance is no raw redistribution. | **N** for this seat (cannot even load the page). Same class of restriction expected. | U | U | U | **Y** — GLEIF golden copy is published for reuse under GLEIF terms | **Y** — public regulatory / published holder tables. House already treats CNINFO as public disclosure (`docs/QUAL_DATA_COMPLIANCE.md` §1.4). | **Y** — public administrative data |
| Derived-use rights (features, display, models) | **U** until signed contract. Agent ToS forbids derivative / competitive products and overseas use. 企查分 / 科创分 are vendor scores — do not ingest. | U / likely same | U | U | U | **Y** for identity crosswalk | **Y** for display of filing facts | **Y** |
| Vendor ID in the payload | **Y** — “被控制企业主键”; GLEIF already emits `qcc=QCNUHCT69B` on PetroChina | **Y** — 企业 ID advertised as a lookup key | Y | Y | Y (`id` in the CSDN sample) | Emits `qcc`, `spglobal`, `gem` as **mappings**, not as LEI | None | USCC is the official key |
| Cost per **easy** USCC lookup | 0.10–0.20 元 search/工商 | ~0.15 元 (secondary) | ~0.015 元 (secondary) | U | ~0.05 元 advertised (secondary, vendor-promotional page) | 0 | 0 | 0 |
| Cost per **solved hostile entity** (VIE / nominee / SOE pyramid / project JV / rename / delist) | Unbounded from this seat (cannot contract). If contracted: 面议 control APIs + a filing still required, because 实际控制人 ≠ listed issuer parent. | Unbounded (blocked). | Unbounded (same class). | Unbounded. | Unbounded. | Does not solve parent. | 0 when Sina/CNINFO name the group; unsolved when HKSCC/BVI/STAR/delist. Filing PDF still required. | Unbounded in engineering time (no API). |

Secondary prices (Tianyancha / Qixinbao / Jinghai unit costs) come from a 2026-07-01 CSDN comparison that also sells Jinghai. They are **not** official price lists. Official Qichacha menu prices above are from `openapi.qcc.com/dataApi` fetched 2026-08-19.

---

## Hostile-case scorecard (the sample the vendors would have to beat)

Frozen frame: `research/alpha_intelligence/censuses/CN-B/CN-B_SAMPLE_FRAME.json` (n=150).

| Stratum | n in frame | What “correct” means | What broke tonight without a vendor |
|---|---|---|---|
| A/H | 27 | One legal person, two listing keys | CNINFO returns both codes (PetroChina 601857 / 00857; Ping An 601318 / 02318; SMIC 688981 / 00981). |
| Central SOE | 31 | Group parent ≠ SASAC ≠ listed issuer | Sina: 中国神华 → 国家能源投资集团有限责任公司; 中国核电 → 中国核工业集团有限公司; 中国石化 → 中国石油化工集团有限公司. GLEIF: PetroChina parent = NO_KNOWN_PERSON. |
| Local SOE | 2 tagged (under-tagged) | Municipal SASAC / local group ≠ listed 上汽 | House baskets do not flag municipal SOEs. 600104 上海汽车集团股份有限公司 is in the frame as auto only. |
| Project companies | 14 | Unlisted vehicle under a listed or group parent | Not on CNINFO. This is the only stratum a commercial graph *might* buy down — and the one their ToS most clearly keep inside the PRC. |
| Joint ventures | 9 | Two parents, no single issuer | 上汽通用 / 一汽-大众 / 华晨宝马 / 中海壳牌. A single “parent” field is a lie. |
| Historical rename | 6 | USCC stable, names move | CNINFO 曾用简称 on 600150: `中国船舶>> *ST船舶`. 中国中车 is the CNR+CSR merger residue. |
| Delisted / relisted | 4 | Ticker dies, legal person does not | 乐视网 300104: CNINFO empty. PetroChina ADR gone 2022-09-08; A+H remain (HK profile text). |
| Semiconductors | 25 | Listed designer ≠ fab project ≠ national unlisted | SMIC A+H on CNINFO; Sina holders fail on every 688 attempted. YMTC / CXMT / 中芯北方 are unlisted. |
| Pharma | 20 | A/H CXO vs PRC opco | 药明康德 603259 / 02359 on CNINFO. Holder gold not in the 36-cut. |
| Auto | 26 | Listed BYD vs HKSCC nominee vs 上汽 JVs vs Cayman EVs | BYD largest holder = `HKSCC NOMINEES LIMITED`. 蔚来/小鹏/理想 are Cayman issuers. |
| Power | 8 + unlisted groups | 长江电力 / 华能国际 / 中国核电 ≠ 三峡集团 / 华能集团 / 中核集团 | 601985 holder = 中国核工业集团有限公司. Unlisted 国家电网 / 三峡集团 / 华能集团 are in the curated overlay. |
| Mining / chemicals | 25 | Group vs listed | 中国铝业 → 中国铝业集团有限公司; 中国中煤 → 中国中煤能源集团有限公司; 中国神华 → 国能投. |

Three definition collisions any purchased “parent” API will launder unless the house names the object first:

1. **Listed issuer parent** (控股股东 of the listed legal person) — 中国移动香港(BVI)有限公司 for 600941 tonight.
2. **Group parent** — 中国移动通信集团有限公司.
3. **Actual controller** — SASAC / 汇金 / a founder / a VIE contract.

Mastermind needs (1) as a dated filing fact and (2) as a separate edge. (3) is a model. Qichacha’s own 实际控制人 endpoint description admits the mix: “大数据分析数据、官方公示数据、疑似实控人数据”.

---

## Cost sketch (only if the flip conditions later hold)

For the *easy* job (USCC + legal name of a known listed A-share) the house already pays **0**.

For a 2,000-name listed universe, once:

| Path | Approximate cash | What you get |
|---|---|---|
| CNINFO profile + Sina holders | 0 | Legal name, A/H, 曾用简称, 控股股东 when the page is not STAR and not a nominee |
| Qichacha 工商 410 | ~400 元 | USCC + 照面. Not parent. |
| Qichacha 工商详情 735 | ~4,000 元 | Shareholders as registered. Still not “issuer parent” for A/H nominees. |
| Qichacha 实际控制人 643 | 面议 | A model. |
| Tianyancha | Cannot buy from this seat | — |

Cost per **solved hostile entity** is the only cost that matters. Tonight the unsolved set is: every VIE/red-chip, every STAR holder pull, every HKSCC/BVI largest-holder, every unlisted project/JV, every delisted name. A 面议 control API does not retire the annual-report read on those names. It adds a vendor ID and a ToS problem.

---

## Recommended house posture (advice, not a freeze)

1. **Do not buy.** Recorded as the CN-B verdict.
2. **Canonical keys:** USCC for a PRC legal person; LEI when issued and not `DUPLICATE`/`RETIRED`; exchange ticker + venue + ISIN as aliases. Never `qcc` / 企查查主键 / 天眼查企业ID.
3. **Parent/control:** store `(legal_person, role, counterparty, source, as_of, known_at)` from CNINFO / HKEX / annual report. Role ∈ {controlling_shareholder, actual_controller_disclosed, group_parent, jv_parent, nominee}. HKSCC is a nominee, not a parent.
4. **GLEIF:** optional USCC/LEI corroboration. Not a parent graph. Not a name search.
5. **Do not scrape** Qichacha / Tianyancha / GSXT HTML. `docs/QUAL_DATA_COMPLIANCE.md` §2.4 already excludes ToS-adverse scrape panels.
6. **CN-E** (Wind / Choice / iFinD) is a different question: listed-issuer supply-chain tables, not this identity buy.
7. Re-use the frozen sample. Do not mint a second 150.

---

## Files

| Path | What |
|---|---|
| `CN-B_SAMPLE_FRAME.json` | 150-entity frame + CNINFO / Sina gold receipts |
| `CN-B_EMPIRICAL_RECEIPTS.md` | Commands and the observations they produced |
| `build_sample_frame.py` | Re-runner (CNINFO + Sina only) |
| `agentos/discoveries/DSC-PRC-REGISTRY-VENDORS-BLOCK-OVERSEAS.md` | Durable access/rights fact |
