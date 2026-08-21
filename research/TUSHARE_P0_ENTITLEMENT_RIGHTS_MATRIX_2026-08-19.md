# GROK-CN-A — Tushare P0 entitlement / rights matrix (2026-08-19)

Status: **PURCHASE/RIGHTS CENSUS, NOT AUTHORITY.** No SKU was bought. No secret
value was read or written. No collector was built. No API call was made against
the live token. Access is never inferred from a successful probe.

Clock: official Tushare docs fetched 2026-08-19. Repo evidence is
`origin/main` at `620acf86f242` plus the GitHub Actions secret *metadata*
(name + `updated_at` only).

---

## 0. How to read this matrix

Four statuses, mutually exclusive per row:

| Status | Means |
|---|---|
| **OWNED** | A documented on-account SKU (operator 2026-08-09 entitlement claim ∩ official price table) already feeds a Macro collector. This is **access ownership**, not a commercial grant. |
| **MISSING** | Official docs list a **separate paid permission** that is **not** on the 2026-08-09 entitlement list. Buying is a new commercial act. |
| **UNKNOWN_RIGHTS** | The 积分 bundle *probably* already covers the endpoint (so do not buy a new SKU), but there is no collector and/or no written vendor grant for commercial / redistribution / derived-display use. |
| **NOT_NEEDED** | A native keyless source already covers the P0 need under house redistribution posture. Do not buy the Tushare SKU. |

Two rights columns are independent of status:

- **Raw redistribution** — republish vendor rows, PDF bodies, Q&A text, report abstracts.
- **Derived model/display** — store locally, score internally, show an aggregate / stance on a commercial dashboard.

A token, a working probe, or an operator "license topic is closed" ruling is **not** a
vendor commercial grant. The spine contract still says this in so many words
(`research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md`: "a token or boolean is
not permission"). The 2026-08-09 wiring takeover closed *license machinery* inside
collectors (`research/TUSHARE_WIRING_TAKEOVER_2026-08-09.md` ruling 3). It did not
create a written institutional contract.

---

## 1. What the account actually has (access evidence, not rights)

### 1.1 Secret metadata (no values)

| Surface | Evidence | Finding |
|---|---|---|
| GitHub Actions secret `TUSHARE_TOKEN` | `gh api repos/mastermindx-market-intelligence/macro/actions/secrets --paginate` filtered to that name | **Present.** `updated_at` = **2026-08-08T08:08:40Z**. Value unread. |
| Injected into | `.github/workflows/asia-close.yml`, `daily.yml`, `tushare-spine-backfill.yml` as `${{ secrets.TUSHARE_TOKEN }}` | Nightly / spine-backfill lanes can see the token. |
| This session's process env | `os.environ.get("TUSHARE_TOKEN")` | **UNSET** (so this session could not have probed even if it had tried). |
| Mastermind gitignored `.env` | `grep -l TUSHARE_TOKEN` on that path (names only) | Key **name** is present. Value unread. Mastermind `data_layer/tushare_feed.py` uses it for A-share `daily` marks only. |

Earlier note in `research/TUSHARE_INTEGRATION.md` that the secret was last written
2026-07-02 is **stale**. The 2026-08-08 timestamp matches the 2026-08-09 probe
witness: the 40101 outage was followed by an operator refresh, then TP-0 probes
returned rows. That is access-at-a-point-in-time, not a rights grant.

### 1.2 Operator-stated SKU list (2026-08-09)

From `research/TUSHARE_WIRING_TAKEOVER_2026-08-09.md` (operator, driver's seat):

1. 常规数据无上限
2. 特色数据 300次/分钟 — scope pinned to official 特色 bundle (盈利预测, 每日筹码和胜率, 筹码分布, 券商每月金股)
3. A股历史分钟 (`stk_mins`, doc 370)
4. 盘前股本 (`stk_premarket`, doc 329)
5. 集合竞价 trio (`stk_auction_o`, `stk_auction_c`, `stk_auction`)

This is an **operator claim about the account**, not a vendor invoice. It was not
re-checked against `https://tushare.pro/weborder/#/user/privilege` in this session
(that page requires a login this session does not have).

### 1.3 Official personal price table (doc 290, fetched 2026-08-19)

Source: <https://tushare.pro/document/1?doc_id=290>

**积分 interfaces (table 1)**

| 积分 | Personal ¥/year | Rate | Daily cap | What it unlocks |
|---|---|---|---|---|
| 120 | 0 | 50/min | 8,000 | Unadjusted daily only |
| 2000+ | 200 | 200/min | 100,000 / API | Per-endpoint 积分 floors |
| 5000+ | 500 | 500/min | 常规数据无上限 | Regular interfaces at their floors |
| **10000+** | **1000** | 500/min regular; **特色 300/min** | 常规无上限 | 特色: 盈利预测, 每日筹码和胜率, 筹码分布, 券商每月金股 |
| 15000+ | 1500 | 500/min | 特色无总量限制 | Same 特色, uncapped |

**Separate permissions (table 2) — not included in 积分**

| SKU | Personal ¥/year | Institutional (10×, same page) | Rate | History |
|---|---|---|---|---|
| A-share historical minutes | 2000 | 20000 | 500/min, 8000 rows | from 2009 |
| 盘前股本 `stk_premarket` | 500 | 5000 | 500/min | ~2 years |
| 集合竞价 realtime `stk_auction` | 500 | 5000 | 500/min | same-day 09:25 window |
| **公告信息** (titles + PDF URLs) | **1000** | **10000** | 500/min | 10+ years |
| **上证e互动 + 深证互动易** | **500** | **5000** | 500/min, no volume cap | SZ ~25y; SH ~2y |
| **券商研报库** | **500** | **5000** | 500/min | from 2017-01-01 |
| News / policy / HK-US / realtime minutes | various | 10× | see doc 290 | not P0 |

Doc 290 footnote, verbatim: personal prices above; **公司机构费用为个人的 10 倍**;
no refunds (fees go to Aliyun).

### 1.4 Default contract (doc 405, fetched 2026-08-19)

Source: <https://tushare.pro/document/1?doc_id=405>

The click-through grant is **personal, non-transferable, non-commercial, revocable,
time-limited, non-exclusive**, "仅可为非商业目的使用，并仅可用作个人查看使用."
Opening a personal SKU "以营利、经营等非个人使用的目的" is an explicit breach.

So:

- **Raw redistribution:** UNKNOWN as a written yes; the default ToS reads as **no**.
- **Derived commercial display / model use:** UNKNOWN as a written yes; the default
  ToS reads as **personal view-only**. Institutional pricing exists (10×) but **no
  institutional receipt is in this repository**. The full-A spine allowlist is
  intentionally empty (`china_tushare_spine.py` + contract §Authorization receipt gate).

Minutes doc 234 adds a second, endpoint-specific ban: "数据只供策略研究和学习使用，
不允许作为商业目的."

### 1.5 Documentation drift inside this repo (do not treat as a third SKU)

| Source | Claim | Treat as |
|---|---|---|
| `research/TUSHARE_INTEGRATION.md` | ¥500/yr · 5000积分 | **Stale.** Predates the 2026-08-09 10000/特色 claim. |
| `collectors/tushare_client.py` header | ¥1000 / 10000积分 | Matches official 10000 row. |
| `tushare_client._THROTTLE["report_rc"] = 3600` | 1 call/hour | Matches the **8000-积分 trial/formal** wording in older notes, **not** the 10000 "无总量限制" row. Do not treat the throttle as a rights fact. |
| `research/TUSHARE_PROBE_WITNESS_2026-08-09.md` | six add-on probes returned rows | **Access observed 2026-08-09.** Not a rights grant. Not re-run this session. |

---

## 2. The purchase / rights matrix

Prices below are **official personal / official institutional (10×)**. They are
list prices, not quotes. "Do not buy" is the standing non-goal of this session
and the recommended action unless a later vendor letter changes a rights cell.

### 2.1 Institutional visits / research

| Field | Value |
|---|---|
| **Status** | **UNKNOWN_RIGHTS** |
| Endpoint | `stk_surv` — [doc 275](https://tushare.pro/document/2?doc_id=275) |
| Entitlement evidence | 5000积分 floor (official). That floor sits inside the operator's "常规数据无上限" claim. **No collector exists** (repo grep for `stk_surv` is empty). Never probed this session. |
| History | Date-range `start_date`/`end_date`; official page does not state a start year. Single call cap **400** rows. |
| Publication / known-at | `surv_date` (调研日期). No vendor `known_at`. `content` is optional / not default-displayed. |
| Rate limits | Regular 积分 pool. At 5000+: 500/min, 常规无上限. Cap 400 rows/call. |
| Personal / institutional price | Included in 5000 (¥500) or 10000 (¥1000) 积分 SKU / 10× if the account is re-issued as institutional. **No extra SKU on table 2.** |
| Raw redistribution | UNKNOWN. Default ToS = personal view-only. `content` is interview text. |
| Derived model/display | UNKNOWN. Confirm with vendor before any commercial dashboard of visitor lists or themes. |
| **Recommended action** | **Do not buy.** Confirm on the privilege page that 积分 ≥ 5000. Ask vendor in writing: (1) may we retain `stk_surv` locally, (2) may a commercial product display *derived* visit intensity / named-institution counts, (3) is `content` in-scope or a separate restriction. Native 巨潮调研 is not collected today. |

### 2.2 Fund portfolio

| Field | Value |
|---|---|
| **Status** | **UNKNOWN_RIGHTS** |
| Endpoint | `fund_portfolio` — [doc 121](https://tushare.pro/document/2?doc_id=121) |
| Entitlement evidence | Official: 5000积分, 200/min; 8000积分, 500/min. Inside the 常规 bundle. **No collector.** `fund_basic` is referenced only as a spine out-of-scope witness. |
| History | Quarterly holdings; `period` = quarter-end date. Official page does not pin a start year. |
| Publication / known-at | `ann_date` (公告日期) + `end_date` (报告期). Availability assumption if collected: `ann_date`, never `end_date`. |
| Rate limits | 200/min at 5000; 500/min at 8000+. |
| Personal / institutional price | Included in 5000/10000 积分 SKU / 10× institutional. No table-2 SKU. |
| Raw redistribution | UNKNOWN. Holdings are public-fund disclosures, but Tushare's ToS is still personal. |
| Derived model/display | UNKNOWN. Confirm commercial use of *derived* crowding / overlap scores. |
| **Recommended action** | **Do not buy.** Privilege-page confirm 积分 ≥ 5000. Vendor letter before any product display of named-fund holdings. Existing `china_fund_issuance` is issuance, not portfolio. |

### 2.3 Announcements

| Field | Value |
|---|---|
| **Status** | **NOT_NEEDED** (metadata) / **MISSING** only if someone later wants Tushare PDF URLs |
| Endpoint | `anns_d` — [doc 176](https://tushare.pro/document/2?doc_id=176) |
| Entitlement evidence | **Table-2 separate permission.** Not on the 2026-08-09 list. |
| History | Official: 10+ years. Cap 2000 rows/call. Fields: `ann_date`, `title`, `url` (PDF), `rec_time`. |
| Publication / known-at | `ann_date` + optional `rec_time`. |
| Rate limits | 500/min (table 2). |
| Personal / institutional price | **¥1000 / ¥10000 per year.** |
| Raw redistribution | UNKNOWN / ToS-hostile. House law already forbids PDF bodies (`collectors/china_filings.py`: "No PDF bodies are ever fetched"). |
| Derived model/display | UNKNOWN for Tushare-sourced titles. CNInfo titles are already collected. |
| Existing native | `collectors/china_filings.py` → CNInfo `hisAnnouncement/query`, keep-first on `announcementId`, last-7-day forward window, metadata only. Inquiry letters ride the same store (`china_inquiry.py` is deprecated). |
| **Recommended action** | **Do not buy.** CNInfo already covers the P0 announcement plane under the house metadata-only posture. Buy `anns_d` only if a later wave needs Tushare's 10y PDF-URL backfill **and** a vendor letter allows commercial derived use of titles (never bodies). |

### 2.4 e互动 / 互动易

| Field | Value |
|---|---|
| **Status** | **NOT_NEEDED** |
| Endpoints | `irm_qa_sz` — [doc 367](https://tushare.pro/document/2?doc_id=367); `irm_qa_sh` — [doc 366](https://tushare.pro/document/2?doc_id=366) |
| Entitlement evidence | **One table-2 SKU covering both.** Not on the 2026-08-09 list. |
| History | Official table 2: SZ ~25 years (doc 367: from 2010-10); SH from **2023-06**. Daily update. Cap 3000 rows/call. |
| Publication / known-at | `trade_date`, `pub_time` (reply time), plus `pub_start`/`pub_end` filters. |
| Rate limits | 500/min, no volume cap (table 2). |
| Personal / institutional price | **¥500 / ¥5000 per year** for the pair. |
| Raw redistribution | UNKNOWN / ToS-hostile. These interfaces return full Q&A **text**. House collectors already stamp the plane as input-only, not a display surface. |
| Derived model/display | UNKNOWN. |
| Existing native | `collectors/china_irm.py` (SZ, `irm.cninfo.com.cn`, keyless) and `collectors/china_einteraction.py` (SH, `sns.sseinfo.com`, keyless). Append-only + `first_seen`. Shard ≤40 names/night. Forward-only, not a 25-year backfill. |
| **Recommended action** | **Do not buy.** Native keyless sources are the house path (CNH-R2). Revisit only if a 25-year SZ / 2-year SH backfill is chartered **and** the vendor confirms commercial derived use of Q&A text (counts/tone, never republished answers). |

### 2.5 Broker reports

Split on purpose. Structured forecast tape ≠ full-report library.

#### 2.5a Structured sell-side forecasts (already collected)

| Field | Value |
|---|---|
| **Status** | **OWNED** (access) + commercial rights still **unknown** |
| Endpoint | `report_rc` — [doc 292](https://tushare.pro/document/2?doc_id=292) |
| Entitlement evidence | Official: 2000积分 trial (10 calls/day); 8000 formal (100,000/day); **10000+ no daily cap**. Inside the operator 特色 claim. Collector: `collectors/tushare_forecast.py` → `data/tushare/report_rc.parquet`, keep-first since #5614. |
| History | From **2010**. Nightly 19:00–22:00 update. Collector currently pulls a trailing ~30d window. |
| Publication / known-at | `report_date`. Store `asof` is capture time, not vendor publication (`CN_INTEL_DATA_READINESS_MATRIX` §3). `create_time` exists on the vendor row and is not the product `known_at`. |
| Rate limits | Official depends on 积分 (see above). Client still sleeps **3600s** between calls — a local conservative throttle, not a vendor receipt. |
| Personal / institutional price | Included in 10000 特色 (¥1000) / 10× institutional. |
| Raw redistribution | UNKNOWN. House posture already: machine fields only; never report bodies. |
| Derived model/display | UNKNOWN for a *commercial* product. Internal display-tier accrual is already how the house uses it. |
| **Recommended action** | **Do not buy.** Confirm 积分 ≥ 10000 on the privilege page so the 1/hour client throttle is optional rather than load-bearing. Vendor letter before any customer-facing revision widget. |

#### 2.5b Full broker-report library (not on the account)

| Field | Value |
|---|---|
| **Status** | **MISSING** |
| Endpoint | `research_report` — [doc 415](https://tushare.pro/document/2?doc_id=415) |
| Entitlement evidence | **Table-2 separate permission.** Not on the 2026-08-09 list. Returns `abstr`, `title`, `url`. |
| History | From **2017-01-01**. Two increments/day. Cap 1000 rows/call. |
| Publication / known-at | `trade_date` = 研报发布时间. |
| Rate limits | 500/min (table 2). |
| Personal / institutional price | **¥500 / ¥5000 per year.** |
| Raw redistribution | UNKNOWN / ToS-hostile. Abstracts + PDF URLs. House CNH-R6: never republish sell-side text. |
| Derived model/display | UNKNOWN. |
| Existing native | `collectors/china_reports.py` → Eastmoney `reportapi.eastmoney.com/report/list` (rating / target / EPS event tape; `pdfUrl` never fetched). |
| **Recommended action** | **Do not buy.** Eastmoney already supplies the structured event tape. A Tushare PDF library would be a new commercial SKU *and* a redistribution problem. Buy only after a vendor letter that derived counts/revisions (not abstracts) may ship in a commercial product, and only if Eastmoney coverage is proven insufficient. |

### 2.6 Named hot-money actors

Split: unnamed LHB tape vs named 游资 roster.

#### 2.6a Unnamed LHB seats

| Field | Value |
|---|---|
| **Status** | **NOT_NEEDED** (Tushare `top_list` / `top_inst` are optional mirrors) |
| Endpoints | `top_list` — [doc 106](https://tushare.pro/document/2?doc_id=106) (2000积分, from 2005, 20:00); `top_inst` — [doc 107](https://tushare.pro/document/2?doc_id=107) (5000积分, 10000-row cap) |
| Existing native | `collectors/china_lhb.py` → Eastmoney `stock_lhb_detail_em` + `stock_lhb_jgmmtj_em`. Append-only. Seats are **not** mapped to 游资 names. |
| **Recommended action** | **Do not buy.** Do not add a Tushare LHB mirror unless Eastmoney breaks. 积分 already covers these if the 10000 claim holds. |

#### 2.6b Named 游资 (the actual P0 gap)

| Field | Value |
|---|---|
| **Status** | **UNKNOWN_RIGHTS** |
| Endpoints | `hm_list` — [doc 311](https://tushare.pro/document/2?doc_id=311) (5000积分, roster); `hm_detail` — [doc 312](https://tushare.pro/document/2?doc_id=312) (**10000积分**, daily named-actor tape from **2022-08**) |
| Entitlement evidence | 积分 floors, not a table-2 SKU. `hm_detail`'s 10000 floor matches the operator 特色 tier **numerically**, but doc 290's 特色 sentence names 盈利预测 / 筹码 / 金股 — **not** 游资. So 10000 may be necessary and still not automatically "特色-included." **No collector.** Never probed. |
| History | Roster: current, <500 rows. Detail: from 2022-08. Cap 2000 rows/call. |
| Publication / known-at | `trade_date` only. Names/orgs are Tushare's classification, not an exchange field. |
| Rate limits | Regular 积分 pool; `hm_detail` requires 10000. |
| Personal / institutional price | No extra SKU if 积分 ≥ 10000 actually unlocks `hm_detail`. If the privilege page shows `hm_detail` locked, that is a **MISSING** convert — still do not buy until the vendor confirms named-actor commercial use. |
| Raw redistribution | UNKNOWN / high-risk. Named 游资 labels + seat maps are Tushare editorial content. |
| Derived model/display | UNKNOWN. A commercial "赵老哥 is in this name" chip needs an explicit vendor yes. |
| **Recommended action** | **Do not buy a new SKU yet.** Privilege-page check: is `hm_detail` already lit at current 积分? Vendor letter before any named-actor display. Eastmoney LHB stays the unnamed tape. |

### 2.7 Holder / top-holder / director trades

| Field | Value |
|---|---|
| **Status** | **UNKNOWN_RIGHTS** (Tushare copies) with **NOT_NEEDED** overlays where Eastmoney already runs |
| Endpoints | `top10_holders` — [doc 61](https://tushare.pro/document/2?doc_id=61) (2000积分; `ann_date`, `end_date`, named holders); `stk_holdernumber` — [doc 166](https://tushare.pro/document/2?doc_id=166) (2000积分; `ann_date`, `end_date`, `holder_num`); `stk_holdertrade` — [doc 175](https://tushare.pro/document/2?doc_id=175) (2000积分, 19:00, cap 3000; `ann_date`; `holder_type` C/P/**G高管**; `in_de` IN/DE) |
| Entitlement evidence | All 积分-gated, inside 常规. **No Tushare collector** for any of the three (repo grep empty). |
| History | Official pages do not pin a start year for holders / holdertrade. `stk_holdernumber` is "不定期." |
| Publication / known-at | `ann_date` is the public stamp. `end_date` is the reporting period, **not** known-at. `stk_holdertrade` also has `begin_date`/`close_date` for the trade window. |
| Rate limits | Regular 积分 pool; 5000+ "无明显限制" on `stk_holdertrade`. |
| Personal / institutional price | Included in 5000/10000 积分 / 10× institutional. No table-2 SKU. |
| Raw redistribution | UNKNOWN. Named holders and 高管 trades are public-disclosure derived; Tushare ToS still personal. |
| Derived model/display | UNKNOWN. |
| Existing native | `china_holder_counts.py` (Eastmoney `RPT_HOLDERNUMLATEST`, PIT class A); `cn_holder_sale_calendar.py` (Eastmoney `RPT_SHARE_HOLDER_INCREASE`, 减持 windows; **NOTICE_DATE is post-sale**, not the 15-day plan announcement). No top-10 named-holder collector. No dedicated 高管-only tape. |
| **Recommended action** | **Do not buy.** Privilege-page confirm 积分 ≥ 2000 (trivially true if the 10000 claim holds). Do **not** replace Eastmoney 户数 / 减持. If a later wave wants named top-10 or 高管 IN/DE, that is a collector charter on an already-paid 积分 endpoint — still needs a vendor letter for commercial named-holder display. |

### 2.8 Existing premium features (forecast / chips / golden stocks)

These are the 特色 bundle the operator already claimed.

| Sub-feature | Endpoint | Doc | Collector | Status | History / known-at | Rate (official) | Price | Raw / derived | Action |
|---|---|---|---|---|---|---|---|---|---|
| Earnings guidance | `forecast_vip` (whole-market) / `forecast` (per-name) | [45](https://tushare.pro/document/2?doc_id=45) | `tushare_forecast.py` → `forecast.parquet` + `forecast_hist.parquet` | **OWNED** | Full history; `ann_date` + `first_ann_date`; hist keep-last on (ticker, ann_date) | 2000 per-name; **5000** for `forecast_vip` | In 5000/10000 积分 | Raw UNKNOWN; derived UNKNOWN | Do not buy. Already accruing. |
| Chip summary / 胜率 | `cyq_perf` | [293](https://tushare.pro/document/2?doc_id=293) | `tushare_chips.py` + `tushare_history.py` | **OWNED** | From **2018**; `trade_date`; 18:00–19:00 | 特色 300/min at 10000 | In 10000 特色 ¥1000 / ¥10000 inst. | UNKNOWN / UNKNOWN | Do not buy. |
| Chip distribution | `cyq_chips` | [294](https://tushare.pro/document/2?doc_id=294) | `tushare_chips_distribution.py` (**not scheduled**, class D) | **OWNED** SKU, dormant collector | From **2018**; `trade_date`; 18:00–19:00 | 5000: 200/min, 20k/day; 10000: 200k/day; 15000: uncapped | Same 特色 SKU | UNKNOWN / UNKNOWN | Do not buy. Arming is a quota decision, not a purchase. |
| 券商金股 | `broker_recommend` | [267](https://tushare.pro/document/2?doc_id=267) | `tushare_broker.py` | **OWNED** | Month-keyed; "1–3 days into the month." Doc 267 says 6000积分; doc 290 lists it under 10000 特色. | Cap 1000 rows | In 特色 ¥1000 / ¥10000 | UNKNOWN / UNKNOWN | Do not buy. PIT: `known_at` only when vendor month = collection month. |
| Structured 盈利预测 | `report_rc` | 292 | see §2.5a | **OWNED** | From 2010; `report_date` | see §2.5a | In 特色 | UNKNOWN / UNKNOWN | Do not buy. |

Also already collected on the same token, **not P0 of this brief but part of the paid plane**:
`moneyflow_dc` / `moneyflow_ind_dc`, `daily_basic`, `margin_detail`. Same commercial-rights
hole. Add-ons already claimed (minutes / premarket / auction) are **OWNED as access**
and **out of this P0 list**; minutes carry an extra "research/study only" sentence
(doc 234).

---

## 3. One-page scoreboard

| P0 family | Status | Buy? | Personal ¥/yr if bought | Inst. ¥/yr | Vendor must confirm before product use |
|---|---|---|---|---|---|
| Institutional visits `stk_surv` | UNKNOWN_RIGHTS | No | 0 extra (积分) | 0 extra if already inst. | Local retention; derived visit intensity; `content` text |
| Fund portfolio `fund_portfolio` | UNKNOWN_RIGHTS | No | 0 extra | 0 extra | Named-fund holdings vs derived crowding only |
| Announcements `anns_d` | NOT_NEEDED | No | 1000 if someone insists | 10000 | Would also violate house "no PDF bodies" |
| e互动 / 互动易 `irm_qa_*` | NOT_NEEDED | No | 500 | 5000 | Q&A text in a commercial product (native path exists) |
| Broker reports `report_rc` | OWNED | No | 0 extra | 0 extra | Customer-facing revision widget |
| Broker reports `research_report` | MISSING | No | 500 | 5000 | Abstracts / PDF URLs — default answer is do not buy |
| Unnamed LHB | NOT_NEEDED | No | 0 extra | 0 extra | — |
| Named 游资 `hm_list` / `hm_detail` | UNKNOWN_RIGHTS | No | 0 extra **if** 10000 unlocks it | 0 extra | Named-actor labels on a commercial surface |
| Top holders / 户数 / 增减持 | UNKNOWN_RIGHTS | No | 0 extra | 0 extra | Named holders / 高管 trades commercially |
| forecast / chips / 金股 | OWNED | No | 0 extra (already on 特色) | 10× if account is re-cut as institutional | Any customer-facing chip / 金股 / guidance widget |

**Cash outlay implied by this census: ¥0.** The only SKUs that would cost new money
are table-2 items this census marks NOT_NEEDED or "do not buy."

**Rights outlay implied: one vendor letter**, covering at least:

1. Is the current account **personal** or **institutional**?
2. May Mastermind **retain** 积分-tier rows locally (bulk, append-only, multi-year)?
3. May a **commercial** dashboard show *derived* signals (counts, intensity, stance)
   built from those rows?
4. Is **raw** redistribution (PDF, Q&A text, report abstracts, named 游资 labels,
   named holders) forbidden? (Default reading: yes, forbidden.)
5. If the product is commercial, what is the **institutional** contract and price
   (list = 10× personal) and what written scopes does it add?

Until that letter exists, every OWNED row is **access-owned, rights-unknown**.

---

## 4. What this session did not do

- Did not log into `tushare.pro/weborder/#/user/privilege`.
- Did not call `api.tushare.pro`.
- Did not read a token value from GitHub, Mastermind `.env`, or the process env.
- Did not treat `research/TUSHARE_PROBE_WITNESS_2026-08-09.md` as a rights grant.
- Did not buy, rotate, or write any secret.
- Did not open a collector.

Falsifier for the whole matrix: a privilege-page screenshot (redact token) showing a
different 积分 tier or a lit/unlit table-2 SKU, or a written vendor/institutional
grant whose scopes contradict a rights cell. Either artifact updates the row;
neither is in this repository today.
