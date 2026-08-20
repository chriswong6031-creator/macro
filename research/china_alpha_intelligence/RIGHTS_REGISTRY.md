# RIGHTS-0 -- China source entitlement / rights registry

**Route:** research - **Program:** WS:CHINA-ALPHA-INTELLIGENCE wave rights0
**Authority:** research/CHINA_ALPHA_INTELLIGENCE_MASTERPLAN.md section 8.1 (audit-first law), section 8.2 (resolver NO-BUY, settled), section 8.3 (supply-chain NO-BUY, settled).
**Consumes, does not re-derive:** CN-A (PR #5945, research/TUSHARE_P0_ENTITLEMENT_RIGHTS_MATRIX_2026-08-19.md, WS:TUSHARE-ENTITLEMENT, DSC:TUSHARE-TOKEN-IS-NOT-A-COMMERCIAL-GRANT), CN-B (PR #5947, research/alpha_intelligence/censuses/CN-B/CN-B_BAKEOFF.md, DSC:PRC-REGISTRY-VENDORS-BLOCK-OVERSEAS), CN-E (PR #5951, research/CN_COMMERCIAL_SUPPLY_CHAIN_DILIGENCE_2026_08_19.md, DEC:CN-NO-SUPPLY-CHAIN-SEAT-PURCHASE, DSC:CN-TERMINAL-LICENSE-FORBIDS-MASTERMIND-DISPLAY).
**Clock:** repo evidence pinned at origin/main b01daaa0188a (branch point 2026-08-20). Public-web citations fetched 2026-08-20 from a US session IP unless dated otherwise.

Status: **PURCHASE/RIGHTS REGISTRY, NOT AUTHORITY.** No secret value was read or printed (TUSHARE_TOKEN referenced by name only). No API call was made against a live token. No collector was built or modified. No ToS was accepted. No robots.txt probe wrote any request beyond a bare GET /robots.txt (diligence, not capture).

---

## 0. How to read this registry

Verdict tags (mutually exclusive per family):

| Tag | Means |
|---|---|
| **OWNED (access)** | A collector exists in this repo today and pulls the family live. Access ownership only -- see the rights columns for whether product use is settled. |
| **NATIVE-COVERED** | A keyless/native collector already covers the P0 need; the Tushare (or vendor) SKU for the same family is NOT_NEEDED. |
| **UNKNOWN_RIGHTS** | Access is plausible or already owned, but commercial/derived-use/redistribution rights are not written down anywhere this session could find. |
| **NO-BUY (settled)** | A prior adjudicated wave (section 8.2 / 8.3) already closed the purchase question; recorded here as inherited, not re-opened. |
| **GAP (no collector)** | Neither a Tushare SKU nor a native collector exists for the family element. |

Evidence tags per cell: **CODE VERIFIED** (repo path:line) / **PRIMARY SOURCE VERIFIED** (named public URL + access date) / **INFERRED** / **UNKNOWN** / **UNKNOWN(operator)** (only the account holder can answer -- never probed).

---

## 1. Family 1 -- Institutional visits / research (机构调研)

**This is the P1-blocking family.**

| Field | Vendor route: Tushare stk_surv | Primary-source route: CNInfo 投资者关系活动记录表 |
|---|---|---|
| Endpoint/page | doc 275 (tushare.pro/document/2?doc_id=275) | www.cninfo.com.cn/new/hisAnnouncement/query (the endpoint collectors/china_filings.py already calls) -- filings whose title is 投资者关系活动记录表, filed as an attachment PDF (e.g. static.cninfo.com.cn/finalpage/...) |
| Access today | **Absent.** grep -rn stk_surv collectors/ engine/ = 0 hits. CODE VERIFIED. | **Half-present.** china_filings.py collects the announcement metadata row (title, announcementId, publish_ts, adjunct_url) for every CNInfo filing, including these -- but CATEGORY_PRIORITY (collectors/china_filings.py:139-150) has no 调研/投资者关系活动记录表 keyword; every such row falls through to category="other", indistinguishable from any other uncategorized filing. CODE VERIFIED (collectors/china_filings.py:139-151). |
| Plan/point requirement | 5000积分 (RMB500/yr) floor -- inside the operator's claimed "常规数据无上限" tier per CN-A section 2.1. UNKNOWN(operator) whether the account is actually >=5000. | None -- CNInfo is keyless. |
| Rate limit | 500/min at 5000+; cap 400 rows/call (CN-A section 2.1). | china_filings.py: 1.5s + jitter/page, 480s/exchange budget (collectors/china_filings.py:49,60). |
| History depth | Official page does not state a start year (CN-A section 2.1). | Whatever CNInfo's own archive holds; china_filings.py currently pulls **forward-only, last 3-7 days** (collectors/china_filings.py:47-48) -- a backfill would need a new date-ranged pull, not a new source. |
| PIT class | surv_date (调研日期) is the vendor's own field; **no separate vendor known_at** -- CN-A already answered this (section 2.1): treat surv_date as both effective and disclosure date absent a second field. | **Y -- true PIT class exists.** publish_ts (CNInfo announcement timestamp) is distinct from the activity date named inside the filing's own title/body (typically an activity that occurred 0-2 trading days earlier per the SZSE self-regulatory guide quoted below). publish_ts is the correct known_at; the in-document activity date is the effective date. CODE VERIFIED for field presence (collectors/china_filings.py:72 publish_ts column); INFERRED for the 0-2-day gap size (see disclosure-timing citation below). |
| Persistence rights | UNKNOWN. Default Tushare ToS = personal, non-commercial, view-only (doc 405, quoted in CN-A section 1.4). | **Y.** CNInfo is house-classified public regulatory disclosure with no MNPI ("simultaneous market release," docs/QUAL_DATA_COMPLIANCE.md section 1.4) and china_filings.py already persists this exact filing stream append-only, metadata-only (collectors/china_filings.py:3-6). |
| Derived-use rights | UNKNOWN. Vendor letter required per CN-A. | **Y for metadata/derived signals** under the house's existing metadata-only posture (title, category, dates, ticker). **UNKNOWN/untested for content** -- i.e., whether the Q&A body inside the PDF attachment may be parsed and displayed; china_filings.py never fetches PDF bodies by house rule (RUL-4, collectors/china_filings.py:3), so this is not yet a live question for the primary route either. |
| Product-display rights | UNKNOWN -- vendor letter needed for any commercial display of visit lists/intensity (CN-A section 2.1 recommended action). | **Y for the metadata plane** (that a visit-category filing exists, when, for which company) under the same public-disclosure legal character CNInfo filings already carry elsewhere on the site. **Full Q&A body display stays out of scope** -- same PDF-body rule as every other CNInfo family. |
| **Verdict tag** | **UNKNOWN_RIGHTS** (inherited from CN-A section 2.1, unchanged -- no new evidence this session) | **NATIVE-COVERED, but the extraction is not built.** Metadata plane is rights-clear today; the category tag that would let a P1 producer find these rows is a repo gap, not a rights gap. |

**Disclosure-timing citation (for the PIT-class row above):** a 2026-08-20 web search over docs.static.szse.cn (深圳证券交易所上市公司自律监管指引) and listed-company IR-management-policy documents (e.g. 苏宁易购集团 IR policy, 2026-01 revision) returned: "上市公司应当在互动易平台披露《投资者关系活动记录表》和相关附件[...]应当包括投资者关系活动类别（如特定对象调研、分析师会议、媒体采访、业绩说明会等）、活动参与人员、时间、地点、形式、交流内容及具体问答记录." PRIMARY SOURCE VERIFIED for the disclosure obligation and content on SZSE; the exact "file within N trading days" clause was not pinned to a specific article number this session (search results named the guide family, not a quotable article text) -- **UNKNOWN(exact day count)**, flag for a follow-up read of the guide PDF if the day count becomes load-bearing. SSE parity (via 上证e互动 / sns.sseinfo.com) is **INFERRED**, not separately verified -- the SSE guide text was not located this session.

**robots.txt posture (diligence, not capture):** www.cninfo.com.cn/robots.txt returned HTTP 404 (no robots.txt present) -- fetched 2026-08-20. PRIMARY SOURCE VERIFIED absence of a robots exclusion at that host.

---

## 2. Family 2 -- Public-fund holdings (基金持仓)

| Field | Vendor route: Tushare fund_portfolio | Native route |
|---|---|---|
| Endpoint | doc 121 (tushare.pro/document/2?doc_id=121) | **None.** grep -rln "fund_portfolio, 基金持仓, fund holding" collectors/ = only collectors/china_fund_issuance.py, which is fund **issuance** (new-fund launch/size), not portfolio holdings. CODE VERIFIED -- no native collector covers this family. |
| Access today | Absent (no collector). CODE VERIFIED. | Absent. |
| Plan/point requirement | 5000积分 (200/min) or 8000积分 (500/min) -- inside operator claim per CN-A section 2.2. | n/a |
| History | Quarterly; no start year stated on the official page (CN-A section 2.2). | n/a |
| PIT class | ann_date (公告日期) vs end_date (报告期/quarter-end) -- **CN-A already answered this**: use ann_date, never end_date, as known_at. | n/a |
| Persistence / derived-use / display | All **UNKNOWN**, vendor letter required (CN-A section 2.2). | n/a |
| **Verdict tag** | **UNKNOWN_RIGHTS** (inherited from CN-A section 2.2, unchanged) | **GAP** -- no native alternative exists at all for this family; unlike visits/announcements/Q&A/holder-counts, there is no keyless fallback in the repo today. |

---

## 3. Family 3 -- Full announcements (公告全文)

| Field | Vendor route: Tushare anns_d | Native route: CNInfo china_filings.py |
|---|---|---|
| Endpoint | doc 176 (tushare.pro/document/2?doc_id=176) | www.cninfo.com.cn/new/hisAnnouncement/query |
| Access today | Absent -- table-2 SKU, not on the 2026-08-09 operator list (CN-A section 2.3). | **OWNED.** collectors/china_filings.py -- metadata-only, keep-FIRST on announcementId, sse+szse, forward 3-7 day window (collectors/china_filings.py:5-6,45-48). CODE VERIFIED. |
| Price | RMB1000 personal / RMB10000 institutional (table 2). | RMB0 -- keyless. |
| History | 10+ years vendor-side (CN-A section 2.3). | Whatever CNInfo's archive holds; **current collector pulls forward-only**, not a 10-year backfill (collectors/china_filings.py:47-48) -- a coverage gap in the collector's window, not in rights. |
| PIT class | ann_date + optional rec_time. | publish_ts (ISO8601, Asia/Shanghai) -- CODE VERIFIED column (collectors/china_filings.py:72). |
| Persistence rights | UNKNOWN/ToS-hostile default (CN-A section 2.3). | **Y** -- public regulatory disclosure (docs/QUAL_DATA_COMPLIANCE.md section 1.4); already persisted. |
| Derived-use rights | UNKNOWN for Tushare-sourced titles. | **Y for metadata** (title/category/date/ticker); **PDF bodies never fetched** by house rule (RUL-4). |
| Product-display rights | UNKNOWN. Would also collide with the house "no PDF bodies" rule if bought. | **Y for the metadata plane** -- this is the exact family the house policy doc already blesses. |
| **Verdict tag** | **NO-BUY (inherited, CN-A section 2.3: NOT_NEEDED)** | **NATIVE-COVERED and OWNED.** No delta from CN-A. |

---

## 4. Family 4 -- Q&A history (互动易 / e互动)

| Field | Vendor route: Tushare irm_qa_sz/irm_qa_sh | Native route: china_irm.py (SZ) + china_einteraction.py (SH) |
|---|---|---|
| Endpoint | doc 367 (SZ) / doc 366 (SH) | SZ: POST irm.cninfo.com.cn/newircs/... (collectors/china_irm.py:25-33). SH: POST sns.sseinfo.com/allcompany.do + .../ajax/userfeeds.do (collectors/china_einteraction.py:29-40). |
| Access today | Absent -- table-2 SKU (CN-A section 2.4). | **OWNED, partial coverage by design.** SZ: <=40 names/night shard, cursor-rotated (collectors/china_irm.py:9-11). SH: same shard cap, plus a resumable directory-map build step (collectors/china_einteraction.py:12-21). Both keyless. CODE VERIFIED. |
| Price | RMB500 personal / RMB5000 institutional for the pair (table 2). | RMB0. |
| History | SZ ~25y, SH from 2023-06, vendor-side (CN-A section 2.4). | **Forward-only from each name's first shard pull**, not a historical backfill -- the native collectors are input-plane accrual, not archive replay. This is a coverage-depth gap versus the vendor SKU, not a rights gap. |
| PIT class | trade_date + pub_time (reply time). | Question timestamp is the platform's own item metadata (china_irm.py stores indexId-deduped rows with fetched_at/first_seen); answer arrival is captured via keep-LAST correction on the same row (collectors/china_irm.py:35-38). CODE VERIFIED for the correction mechanism; the platform's own "asked at" vs "answered at" split was not independently re-verified this session beyond what CN-A already read from the doc pages. |
| Persistence rights | UNKNOWN/ToS-hostile default (CN-A section 2.4). | House posture already treats this as an **input plane, not a display surface** -- both collector docstrings state "CONTEXT / INPUT TIER ONLY... nothing here is scored, ranked or promoted... appears only as a pending-tier inventory row" (collectors/china_irm.py:18-22; collectors/china_einteraction.py:23-26). This is a self-imposed house limit, not evidence of a written SZSE/SSE grant -- see robots.txt finding below. |
| Derived-use rights | UNKNOWN (CN-A section 2.4). | **UNKNOWN written grant**, same as the vendor route -- SZSE/SSE 互动易/e互动 do not publish a data-reuse ToS this session located (only the disclosure-obligation guide language quoted in section 1 above, which governs the company's duty to answer publicly, not a third party's right to bulk-store and derive from it). House mitigates by keeping the plane un-displayed (待验 badge, engine/china_signal_lab.py), not by a rights clearance. |
| **Verdict tag** | **NO-BUY (inherited, CN-A section 2.4: NOT_NEEDED)** | **NATIVE-COVERED (access) / UNKNOWN_RIGHTS (derived display).** Delta from CN-A: CN-A's NOT_NEEDED call was about not buying the Tushare SKU, which stands; this session adds that the native route's own commercial-display rights are also unwritten, currently masked by keeping the plane context-only. If a later wave wants to display Q&A-derived signals (not just accrue them), that still needs the same vendor-letter-class answer CN-A flagged for the Tushare SKU -- the platform, not the delivery mechanism, is the rights question. |

**robots.txt posture:** irm.cninfo.com.cn/robots.txt returned a page-title fragment, not a parseable robots file (fetch tool limitation, not a confirmed absence) -- **UNKNOWN**, re-check with a raw HTTP client if this becomes load-bearing. sns.sseinfo.com/robots.txt returned HTTP 404 (no robots.txt) -- PRIMARY SOURCE VERIFIED, fetched 2026-08-20.

---

## 5. Family 5 -- Full sell-side research (研报全文)

Three planes, not one -- CN-A already split structured-forecast vs full-library; this registry adds the analyst-consensus snapshot as a third.

| Field | report_rc (structured forecast tape, Tushare) | research_report (full-library, Tushare) | china_reports.py (Eastmoney event tape, native) | china_analyst.py (Eastmoney consensus snapshot, native) |
|---|---|---|---|---|
| Access today | **OWNED.** collectors/tushare_forecast.py -> report_rc.parquet (CN-A section 2.5a). | Absent -- table-2 SKU (CN-A section 2.5b). | **OWNED.** reportapi.eastmoney.com/report/list, rating/target/EPS event stream (collectors/china_reports.py:1-35). CODE VERIFIED. | **OWNED.** stock_profit_forecast_em whole-market consensus snapshot (collectors/china_analyst.py:1-19). CODE VERIFIED. |
| Price | Included in 特色 RMB1000/RMB10000. | RMB500/RMB5000. | RMB0. | RMB0. |
| History | From 2010 (CN-A section 2.5a). | From 2017-01-01 (CN-A section 2.5b). | Trailing window (event tape, not archive-deep). | Current snapshot only, refreshed every build (collectors/china_analyst.py:11). |
| PIT class | report_date; store asof != vendor publication (CN-A section 2.5a). | trade_date = 研报发布时间 (CN-A section 2.5b). | Per-report event date, dedup on infoCode keep-LAST, first_seen preserved (collectors/china_reports.py:11-14). CODE VERIFIED. | Snapshot-only; no per-report PIT (by design -- this is an aggregate, not an event tape). |
| Persistence rights | UNKNOWN (CN-A). | UNKNOWN (CN-A). | House posture: machine fields only. | House posture: same. |
| Derived-use / display rights | UNKNOWN for a commercial product; internal display-tier accrual already how house uses it (CN-A section 2.5a). | UNKNOWN; would also collide with house "never republish sell-side text" rule (CN-A section 2.5b). | **REDISTRIBUTION LIMIT stated in-repo**: "machine fields only. pdfUrl/attachments/report bodies are NEVER fetched" (collectors/china_reports.py:26). CODE VERIFIED as a house-imposed limit, not a vendor grant -- Eastmoney's own ToS for this endpoint was not independently located this session (**UNKNOWN** vendor-side). | House posture: "CONTEXT, NOT A SIGNAL... shown as coverage context" (collectors/china_analyst.py:16-18) -- same self-imposed limit pattern, same UNKNOWN vendor-ToS gap. |
| **Verdict tag** | **OWNED (access), UNKNOWN_RIGHTS (commercial display)** -- no delta from CN-A. | **NO-BUY (inherited, CN-A section 2.5b)** | **OWNED (access), UNKNOWN vendor ToS, house-limited to metadata by policy.** | **OWNED (access), UNKNOWN vendor ToS, house-limited to aggregate coverage context by policy.** |

reportapi.eastmoney.com/robots.txt returned HTTP 404 (no robots.txt) -- PRIMARY SOURCE VERIFIED, fetched 2026-08-20. This is an absence-of-restriction finding, not an affirmative grant; Eastmoney's data-API ToS (as opposed to its robots file) was not located this session and stays **UNKNOWN**. The house's own metadata-only self-limit on both native collectors is the operative control regardless of the vendor-ToS gap.

---

## 6. Family 6 -- Named market actor data (游资/机构标签)

| Field | Vendor route: Tushare hm_list/hm_detail | Native route: china_lhb.py (unnamed only) |
|---|---|---|
| Endpoint | doc 311 (roster) / doc 312 (detail) | stock_lhb_detail_em + stock_lhb_jgmmtj_em via akshare/Eastmoney (collectors/china_lhb.py:6-13). |
| Access today | Absent. CODE VERIFIED (grep empty, CN-A section 2.6b). | **OWNED, but unnamed.** Seats are aggregated into 机构吸筹 (institutional accumulation) vs 游资 (retail/hot-money, detail-only-no-inst-seats) -- a **class label**, not a **named actor** (engine/china_extras.py:280, tag logic "机构吸筹" if leading else "游资"). CODE VERIFIED -- this is the exact gap CN-A named: "Seats are not mapped to 游资 names" (section 2.6a). |
| Plan/point requirement | hm_list 5000积分; hm_detail **10000积分**, and CN-A flags this is numerically the same floor as the operator's claimed 特色 tier but the 特色 bundle's own doc-290 sentence names 盈利预测/筹码/金股, not 游资 -- so 10000 may be necessary and still not automatically included (CN-A section 2.6b, UNKNOWN(operator) whether hm_detail is actually lit). | n/a -- keyless. |
| History | Roster current, <500 rows; detail from 2022-08 (CN-A section 2.6b). | ~5 trading days aggregated per collection (collectors/china_lhb.py:15). |
| PIT class | trade_date only -- CN-A already flags this as the weakest PIT field of the whole matrix (no separate announcement stamp; names/orgs are Tushare's own classification, not an exchange field). | stock_lhb_detail_em/jgmmtj_em are whole-market pulls over a start/end window; no additional PIT nuance surfaced this session beyond CN-A's read. |
| Persistence rights | UNKNOWN/high-risk -- "Named 游资 labels + seat maps are Tushare editorial content" (CN-A section 2.6b). | House posture: DISPLAY/CONTEXT, explicitly "not a validated forward edge... never a buy ranking" (collectors/china_lhb.py:20-21). |
| Derived-use / display rights | UNKNOWN. A commercial named-actor chip needs an explicit vendor yes (CN-A section 2.6b). | **N/A for named actors** -- the native collector structurally cannot answer the named-actor question; it only ever emits the two-class label. Displaying the unnamed institutional-vs-hot-money split is already live house practice (engine/china_extras.py), which is a different, already-shipped product surface. |
| **Verdict tag** | **UNKNOWN_RIGHTS (inherited, CN-A section 2.6b -- no delta)** | **NATIVE-COVERED for the unnamed/class-label plane only. GAP for the named-actor plane** -- there is no rights-clear path to a named 游资 roster today: the vendor route is UNKNOWN_RIGHTS-and-possibly-not-even-lit, and no native alternative for names exists (only exchange-published seat numbers, which 龙虎榜 already carries and the collector already ingests). |

---

## 7. Family 7 -- Top-holder / holder-trade data (十大股东/股东户数/增减持)

| Field | Vendor route: Tushare (top10_holders/stk_holdernumber/stk_holdertrade) | Native route: china_holder_counts.py + cn_holder_sale_calendar.py |
|---|---|---|
| Endpoints | doc 61 (named top-10 holders) / doc 166 (holder count) / doc 175 (holder trade IN/DE incl. 高管) | china_holder_counts.py -> RPT_HOLDERNUMLATEST (holder **count**, not named holders) (collectors/china_holder_counts.py:19-21). cn_holder_sale_calendar.py -> RPT_SHARE_HOLDER_INCREASE filtered DIRECTION=减持 (**sale side only**, not IN) (collectors/cn_holder_sale_calendar.py:3-13). |
| Access today | Absent for all three (CN-A section 2.7, grep empty). | **OWNED, partial.** Holder count: full coverage. Holder trade: **减持 (sale/DE) only** -- the increase (增持/IN) leg and the general 高管-only tape are not separately collected. CODE VERIFIED (cn_holder_sale_calendar.py:3-13 names DIRECTION=减持 explicitly). No top-10 **named**-holder collector exists at all. |
| Plan/point requirement | 2000积分 each, inside 常规 (CN-A section 2.7). | Keyless. |
| History | No start year stated for holders/holdertrade (CN-A section 2.7). | china_holder_counts.py: dedup on (code, end_date) keep-LAST, ordered by notice_date -- effectively full disclosed history as Eastmoney serves it (collectors/china_holder_counts.py:27-30). cn_holder_sale_calendar.py: window per the endpoint's own serving depth, not separately re-verified this session. |
| PIT class | ann_date is the public stamp; end_date is reporting period, **not** known_at (CN-A already answered this). stk_holdertrade also has begin_date/close_date for the execution window. | **Two different PIT postures, already documented in-repo and worth flagging as a house-internal inconsistency:** china_holder_counts.py treats notice_date (disclosure date) as the correcting key -- i.e., disclosure-date PIT, matching the vendor route's ann_date convention. cn_holder_sale_calendar.py explicitly does **not** do this: its own docstring states "PIT LAW (pre-registered): We cannot observe the original plan announcement date from this endpoint (NOTICE_DATE is the post-sale filing, not the plan announcement). PIT assumption: the execution window is public on START_DATE" (collectors/cn_holder_sale_calendar.py:28-34). CODE VERIFIED, pre-registered by the collector's own author -- this is a documented, deliberate conservative choice, not a gap, but it means the two "holder" collectors are not interchangeable on PIT semantics. |
| Persistence / derived-use rights | UNKNOWN (CN-A section 2.7). | House posture: context/input tier, no dedicated display surface for holder counts (collectors/china_holder_counts.py:13-16); cn_holder_sale_calendar.py does not carry an equivalent "context only" disclaimer in its header -- **UNKNOWN** whether it is treated as display-eligible; not independently resolved this session (would need to check its consuming engine module, out of this audit's file scope). |
| **Verdict tag** | **UNKNOWN_RIGHTS (inherited, CN-A section 2.7 -- no delta)** | **NATIVE-COVERED for holder-count and sale-side holder-trade. GAP for named top-10 holders and for the increase/高管-only leg of holder-trade** -- same shape as Family 6: the vendor route that would fill the gap is itself UNKNOWN_RIGHTS, so there is no rights-clear path to full holder-trade coverage today, only to the two already-native slices. |

---

## 8. Residual already-consumed families (not P0 of this audit, listed for completeness)

Per CN-A section 2.8, already OWNED as access, rights posture unchanged (UNKNOWN commercial/derived-display, house-limited to internal display-tier accrual): forecast_vip/forecast (earnings guidance, tushare_forecast.py), cyq_perf (chip summary, tushare_chips.py+tushare_history.py), cyq_chips (chip distribution, tushare_chips_distribution.py, dormant/not scheduled), broker_recommend (券商金股, tushare_broker.py), plus out-of-P0 planes moneyflow_dc/moneyflow_ind_dc, daily_basic, margin_detail. No new evidence this session; CN-A's cells stand.

---

## 9. Entity-resolution rights -- vendor route (settled) vs primary-source route (live)

### 9.1 Vendor route -- SETTLED NO-BUY, not re-opened

DNR/DEC posture: masterplan section 8.2 records the CN-B (#5947) bake-off verdict as settled. This registry does not re-run diligence; it restates CN-B's rights cells as the vendor rows of this table, per the commission's instruction.

| Vendor | Access from this seat | Persistence rights | Derived-use rights | Product-display rights |
|---|---|---|---|---|
| Qichacha Open API | Catalog readable; API purchase U (CN-B) | U on Open API terms; agent-platform ToS (2026-06, still posted) forbids overseas store/query entirely | U -- agent ToS forbids derivative/competitive products | U, same ToS bars it |
| Tianyancha | Website geo-blocked from a US IP (DSC:PRC-REGISTRY-VENDORS-BLOCK-OVERSEAS) | N for this seat | N | N |
| GLEIF (free, not PRC-commercial but part of CN-B's resolver stack) | Y, open | **Y** -- CC0 1.0 Universal, PRIMARY SOURCE VERIFIED 2026-08-20 (gleif.org/en/meta/lei-data-terms-of-use, gleif.org/en/about/open-data) | Y under CC0 | Y under CC0 -- but CN-B already flags GLEIF as not a parent graph (PetroChina's own parent link is a NO_KNOWN_PERSON reporting exception) -- a rights-clear source that does not solve the resolution job by itself. |

### 9.2 Primary-source route -- the live rights question (PR-0D's actual inputs)

CN-B's recommended house identity stack ("Recommended house posture") is **USCC + LEI when issued + listing keys**, sourced from CNInfo company-profile pages (ak.stock_profile_cninfo) and exchange holder tables (ak.stock_main_stock_holder, Sina/Eastmoney).

| Source | Persistence rights | Derived-use rights | Product-display rights | Verdict |
|---|---|---|---|---|
| CNInfo company profile (ak.stock_profile_cninfo) | **Y** -- public regulatory disclosure, house-classified no-MNPI (docs/QUAL_DATA_COMPLIANCE.md section 1.4); CN-B already used this live tonight-of-record (110/111 hit rate on the sample). | **Y** for identity fields (legal name, A/H codes, 曾用简称, listing dates) -- these are exactly the fields the house policy doc already blesses for CNInfo. | **Y**, same basis. | **NATIVE-COVERED, rights-clear.** |
| Sina holder tables (ak.stock_main_stock_holder, via akshare) | House classification treats akshare CN sources generally as "published domestic ... aggregates ... no access credentials required" (docs/QUAL_DATA_COMPLIANCE.md section 1.5) -- but that section's named examples are news/attention data, not holder-registry tables; applying it here is **INFERRED by analogy**, not a direct citation. finance.sina.com.cn/robots.txt fetch returned an empty/unparseable body this session -- **UNKNOWN**, not a confirmed absence-of-restriction (unlike the CNInfo/Eastmoney/SSE hosts checked, which returned clean 404s). | **INFERRED** (same analogy) | **INFERRED** (same analogy) | **UNKNOWN_RIGHTS at the margin** -- the identity-layer USE (legal name / group parent as a dated filing fact) is very likely fine under the same public-disclosure logic that already covers CNInfo, but this session did not find a Sina-specific ToS statement or a clean robots.txt read to firm that up. Flag for a follow-up robots.txt re-check with a raw HTTP client (the WebFetch tool returned an empty page for this specific host, not a definitive 404). |
| GLEIF | See section 9.1 -- **Y**, CC0. | **Y** | **Y** | **NATIVE-COVERED, rights-clear**, with the CN-B caveat that it doesn't solve parent/control by itself. |

**No delta from CN-B's no-buy verdict.** This section adds only the persistence/derived-use finding for the primary-source route that CN-B's own scope did not price out in rights language (CN-B answered "does this solve the job", not "what license governs the inputs") -- which is exactly the gap QUESTIONS(4) asks this audit to close.

---

## 10. P1 verdict paragraph

**Can P1 run on Tushare stk_surv?** No -- not today, and not as the first build target. stk_surv is UNKNOWN_RIGHTS (inherited from CN-A section 2.1, unchanged by this session): no collector exists, the account's actual 积分 tier is UNKNOWN(operator), and even at a sufficient tier, retention + commercial display of visit lists/intensity has no written vendor grant. Buying is explicitly not recommended by CN-A and this registry does not change that.

**What P1 should build on instead:** the CNInfo primary-source route (section 1 above) is **rights-clear today** for the metadata plane -- persistence and derived/product display of "a visit-category filing exists, for company X, on date Y" are already covered by the house's standing public-regulatory-disclosure classification, and collectors/china_filings.py already ingests the underlying announcement stream. **The blocker is not rights, it is extraction**: the collector's category normalizer (CATEGORY_PRIORITY, collectors/china_filings.py:139-150) has no keyword bucket for 投资者关系活动记录表/调研/特定对象调研/分析师会议/业绩说明会, so every such filing is currently indistinguishable from other, and the collector's window is forward-only (3-7 days), not a historical backfill. A P1 builder therefore has two concrete, rights-clear tasks and zero purchase decision: (a) add a visit-record category bucket to the existing normalizer (a code change, not a rights change -- in scope for the P1 wave, out of scope for this audit), and (b) decide whether P1 needs a historical backfill window or can accrue forward-only from first light (an engineering/product choice, not a rights question).

**What remains operator-decidable, not resolvable by further research:** (1) whether the Tushare account is actually >=5000/10000 积分 (would only matter if a later wave still wants stk_surv's content field or its different date-range semantics as a cross-check against the primary route -- not required to ship P1); (2) the one vendor letter CN-A already scoped (retention + derived-display + content in/out of scope) if stk_surv is ever reopened; (3) the exact SZSE "file within N trading days" clause (section 1, disclosure-timing citation) if the PIT gap between activity date and publish_ts becomes load-bearing for a freshness SLA -- this session located the disclosure obligation but not a quotable day-count article.

---

## 11. Top-line per-family scoreboard

| # | Family | Vendor-route verdict | Native/primary-route verdict | P0-blocking? |
|---|---|---|---|---|
| 1 | Institutional visits/research | UNKNOWN_RIGHTS (RMB0 to unlock if tier suffices) | NATIVE-COVERED (rights-clear), extraction not built | **Yes -- this is P1's gate; resolved by extraction, not purchase** |
| 2 | Public-fund holdings | UNKNOWN_RIGHTS | **GAP** -- no native alternative exists | Yes, for any P2-class fund-crowding work |
| 3 | Full announcements | NO-BUY (settled, NOT_NEEDED) | NATIVE-COVERED and OWNED | No |
| 4 | Q&A history | NO-BUY (settled, NOT_NEEDED) | NATIVE-COVERED (access) / UNKNOWN_RIGHTS (commercial display) | No for accrual; yes if ever displayed |
| 5 | Full sell-side research | report_rc OWNED/UNKNOWN_RIGHTS; research_report NO-BUY (settled) | NATIVE-COVERED (event tape + consensus snapshot), house-limited to metadata by policy | No |
| 6 | Named market actor data | UNKNOWN_RIGHTS, tier-unlock UNKNOWN(operator) | **GAP** for named actors (only unnamed class labels exist) | Yes, for any named-游资 product surface |
| 7 | Top-holder/holder-trade | UNKNOWN_RIGHTS | NATIVE-COVERED for holder-count + sale-side; **GAP** for named top-10 and increase/高管 leg | Partial |
| -- | Entity resolver (vendor) | NO-BUY (settled, section 8.2) | n/a | No |
| -- | Entity resolver (primary-source, PR-0D's actual route) | n/a | NATIVE-COVERED (CNInfo/GLEIF rights-clear); Sina holder-table rights **UNKNOWN** at the margin (robots.txt read inconclusive) | Coordinate with WS:STOCK-IDENTITY / PR-0D, not this audit |

**Cash outlay this registry recommends: RMB0**, unchanged from CN-A/CN-E. No new purchase is proposed for any of the seven families or the resolver question.

---

## Appendix -- URLs and dates touched this session (2026-08-20)

| URL | Finding |
|---|---|
| https://www.cninfo.com.cn/robots.txt | HTTP 404 -- no robots.txt |
| https://datacenter-web.eastmoney.com/robots.txt | Malformed-request JSON error, not a robots file -- treated as no enforced robots policy at this path |
| https://reportapi.eastmoney.com/robots.txt | HTTP 404 -- no robots.txt |
| https://sns.sseinfo.com/robots.txt | HTTP 404 -- no robots.txt |
| https://irm.cninfo.com.cn/robots.txt | Fetch tool returned a page-title fragment, not a parseable robots file -- UNKNOWN, not a confirmed absence |
| https://finance.sina.com.cn/robots.txt | Fetch tool returned an empty body -- UNKNOWN, not a confirmed absence |
| https://www.gleif.org/en/meta/lei-data-terms-of-use, https://www.gleif.org/en/about/open-data | GLEIF LEI/Golden-Copy data licensed CC0 1.0 Universal |
| Web search: 深圳证券交易所上市公司自律监管指引 + 苏宁易购 IR policy (2026-01 rev) | SZSE disclosure obligation for 投资者关系活动记录表 via 互动易平台, content requirements quoted in section 1; exact day-count article not pinned |
| Web search: 巨潮资讯网 投资者关系活动记录表 | Confirms these records are filed as CNInfo static.cninfo.com.cn PDF attachments (e.g. 顺网科技 2025-11-03, 超达装备 2025-12-23) |

## Appendix -- repo paths this session read (no writes outside this file + the WS wave flip)

collectors/tushare_client.py, collectors/china_irm.py, collectors/china_einteraction.py, collectors/china_lhb.py, collectors/china_reports.py, collectors/china_analyst.py, collectors/china_filings.py, collectors/china_holder_counts.py, collectors/cn_holder_sale_calendar.py, collectors/china_block_trades.py, engine/china_extras.py, docs/QUAL_DATA_COMPLIANCE.md, research/TUSHARE_P0_ENTITLEMENT_RIGHTS_MATRIX_2026-08-19.md, research/alpha_intelligence/censuses/CN-B/CN-B_BAKEOFF.md, research/CN_COMMERCIAL_SUPPLY_CHAIN_DILIGENCE_2026_08_19.md, research/CHINA_ALPHA_INTELLIGENCE_MASTERPLAN.md section 8.1-8.4, agentos/discoveries/DSC-TUSHARE-TOKEN-IS-NOT-A-COMMERCIAL-GRANT.md, agentos/discoveries/DSC-PRC-REGISTRY-VENDORS-BLOCK-OVERSEAS.md, agentos/workstreams/WS-CHINA-ALPHA-INTELLIGENCE.md.
