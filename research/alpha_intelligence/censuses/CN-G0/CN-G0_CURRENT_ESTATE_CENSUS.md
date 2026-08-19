# CN-G0 — Current-estate census (China post-event reinterpretation)

**Lane id:** `CN-G0`. This is **not** the US Alpha Intelligence GROK-G0. The canonical US packet lives at `research/earnings_intelligence/g0/` (PR #5955: academic review, US event-clock census, frontier spec draft, US casebook, reaction-geometry matrix; governing adjudication `C0G_G0_SEAT_ADJUDICATION_2026-08-19.md` on PR #5933). This packet must not occupy that territory.
**Lane:** GROK-CN-G0 (China post-event reinterpretation)
**Date:** 2026-08-19
**Reconciliation pin:** `origin/main` @ `6353b77f5aaa`
**Authority of this document:** NONE. Research census only. No production scoring, no Prophet change, no new store, no E2 change.
**Parent snapshot:** PASS-0 PR #5910 §1-G names the *US* G responsibility. C0 (#5933) recorded US G0 outstanding; canonical US G0 was returned on PR #5955 and adjudicated by the c0g seat packet (#5933) — #5953's rival copy was withdrawn. **This file is the China-program sibling, not a second copy of that return.**
**China program under census:** China Alpha Intelligence (open PR #5953 / closed draft #5822). Not the July `china_alpha/` pick-board program. Not CN-limit-alpha (`DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT`).
**Addressee:** `WS:EARNINGS-INTELLIGENCE-OS` for event/document/claim contract. China source planes stay in `china-system`. There is never an independent G or CN-G build lane.

Claim tags: **CODE VERIFIED** · **PRIMARY SOURCE VERIFIED** · **INFERRED** · **UNKNOWN**.

---

## 0. One-sentence finding

China already has a live **disclosure-booking calendar with revision columns**, a **预告 + 快报 collector**, an **announcement-metadata corpus with inquiry/reply kinds**, **two on-the-record Q&A tapes with keep-LAST answer correction**, a **sell-side report event tape**, a **context-only Special Situations desk**, and **QLedger salience claims for inquiry letters and large unlocks**. What G is missing is not another collector: it is a **single issuer-event identity and multi-vintage lifecycle** that can join those tapes the way `event_workspace.v1` already joins an 8-K and a transcript — and that join is an Earnings OS E-wave after E2, not a China-side store.

---

## 1. Capability table

| Capability | Owner (as coded) | Store / artifact | PIT clock | Correction | Product consumer | Maturity | China-native vs US-ported |
|---|---|---|---|---|---|---|---|
| Earnings OS event workspace | `engine/company_intelligence/event_workspace.py` + `events.py` + `identity.py` | `event_workspace.v1` on `company_intelligence/event_workspaces/` | `observed_at` / `source_available_at`; id is `(company_id, fiscal_period, event_type)` | Same id, new `generation_id`, lifecycle `corrected` | Terminal CI workspace + dossier glance (**E2, not built**) | **US-only live** (AAPL FY2026 Q3, E1P #5841). `company_id` = `cik:` + 10-digit EDGAR CIK (CODE VERIFIED `identity.py`, `events.py:6-11`) | US-ported contract. **No China issuer can mint an id.** |
| A-share disclosure calendar | `collectors/china_earnings.py` → `engine/china_extras.earnings_calendar` | `data/china_earnings/calendar.parquet` | `asof`; `next_date` / `last_date` | Latest of `三次变更日期` / `二次` / `一次` / `首次预约` wins, then `实际披露时间` (CODE VERIFIED collector docstring + `_SCHED_COLS`) | China stock page countdown (client-side days-to) | LIVE display/context | China-native (Eastmoney `stock_yysj_em`). US analog is a point consensus, not a booked-date tape. |
| 业绩预告 (yjyg) | `collectors/china_preannounce.py` | `data/china_preannounce/forecast.parquet` | collector `asof` / quarter-end | Snapshot overwrite per quarter window (INFERRED from refresh shape) | `engine/china_special_situations._preannounce_block` (type counts + top movers) | LIVE context desk | China-native. Exchange-reported `预告类型` verbatim. |
| 业绩快报 (yjkb) | same collector | `data/china_preannounce/preliminary.parquet` | same | same | **NO engine consumer** (CODE VERIFIED: `_preannounce_block` reads only `forecast.parquet` at `china_special_situations.py:552`; repo grep of `preliminary.parquet` hits the collector only) | COLLECTED, ORPHANED | China-native. This is the first restatement vintage after 预告. |
| Tushare 业绩预告 + 卖方预测 | `collectors/tushare_forecast.py` (GATED) | `data/tushare/forecast.parquet`, `forecast_hist.parquet`, `report_rc.parquet` | `ann_date` + `asof`; report_rc first-seen wins | hist dedup `(ticker, ann_date)` keep-last; report_rc first-seen (CODE VERIFIED) | `engine/china_extras.forecast_guidance`; `engine/china_validation` family `guidance`; `engine/china_signal_lab` row `forecast_surprise` pending | ACCRUING / pending validation | China-native, token-gated. Parallel to (does not replace) the keyless Eastmoney 预告 tape. |
| CNInfo announcement metadata | `collectors/china_filings.py` | `data/china_filings/filings.parquet` | `publish_ts` Asia/Shanghai; `_collected_at` | **keep-FIRST** on `announcementId` (CODE VERIFIED header) | `china_special_situations._inquiry_block`; category taxonomy for investigation / inquiry / 预告 / 重组 / 回购 / 减持… | LIVE metadata-only (RUL-4: no PDF bodies) | China-native. Title-keyword categories, not an event ontology. |
| Inquiry letters + replies | filings plane (legacy `collectors/china_inquiry.py` retired; file kept as archaeology) | filings `kind` ∈ {letter, reply, attachment} | CST `publish_ts[:10]` | New announcementId = new row; reply is a **sibling row**, not a mutation of the letter | Special Situations inquiry block; QLedger `cn_special_sits` | LIVE context | China-native. QLedger sidecar has a UTC/CST ±1-day transition cutoff `2026-07-06` (CODE VERIFIED). |
| SZSE 互动易 Q&A | `collectors/china_irm.py` | `data/china_irm/qa.parquet` + `velocity.parquet` | `first_seen` + `fetched_at` | **keep-LAST** on `indexId` — a later pull that now carries the 董秘 answer **corrects** the row (CODE VERIFIED header) | `engine/china_signal_lab` pending inventory only (china_altdata 待验). **No dedicated surface.** | ACCRUING input plane | China-native. No US 8-K analog. |
| SSE 上证e互动 Q&A | `collectors/china_einteraction.py` | `data/china_einteraction/qa.parquet` | same two clocks | **keep-LAST** on `feed_id` (CODE VERIFIED header) | same pending inventory | ACCRUING; uid_map is resumable and can lag new listings 30d | China-native. SS half of the board universe only. |
| Sell-side report event tape | `collectors/china_reports.py` | `data/china_reports/reports.parquet` + `aggregates.parquet` | `first_seen` / `fetched_at`; aggregates by publish DATE | keep-LAST on `infoCode`; `ratingChange` stored RAW, never interpreted (CODE VERIFIED) | signal-lab pending only | ACCRUING input | China-native. Distinct from the consensus **snapshot** in `china_analyst`. |
| Analyst consensus snapshot | `collectors/china_analyst.py` → `engine/china_extras.analyst_consensus` | `data/china_analyst/forecast.parquet` | `asof` | Daily overwrite of current snapshot | China extras / page coverage context | LIVE context | Parallel of HK consensus. Not a revision tape. |
| Special Situations desk | `engine/china_special_situations.py` → `scripts/build_china_special_situations.py` | `site/chinaspecialdata/special.json` schema `china_special_sits.v1` | per-block `asof`; snapshot `data_asof` = oldest block | Independent degrade per block; no composite | `/china_special_situations.html` (Insider+; `config.yml` `china_special_situations`) | LIVE context-only | China-native fusion of unlocks, inquiry, 预告, buybacks, pledge, ST, blocks, goodwill. **Does not fuse a logical earnings event.** |
| QLedger CN special-sits claims | `china_special_situations.register_claims` | `data/china_special_sits/claims_registered.parquet`; QLedger family `cn_special_sits` | event date (inquiry) or first-seen today (unlock); `timestamp_quality=CRAWL_BOUNDED` | once-per-`event_key`; direction=0 salience-only; asia-lane gated | Eval OS / QLedger (no rank) | LIVE salience | China-native. Only inquiry letters + large unlocks (≥5% float). **Not 预告/快报/正式报告.** |
| Macro/PBoC calendar | `engine/china_event_calendar.py` | none (date arithmetic + CY2026 table) | `asof` optional | N/A | glance strip / LLM narration | LIVE display leaf | **Not an issuer event.** Sibling of US `event_calendar`. |
| LHB / 龙虎榜 | `collectors/china_lhb.py` → `engine/china_extras.lhb_inst` | `data/china_lhb/detail.parquet` | session `asof` | daily aggregate | page smart-money context | LIVE context, not scored | Post-event **attention/flow**, not document truth. Do not port into Earnings OS. |
| Stock Connect | `collectors/china_connect.py` | connect history parquet | daily | northbound net/buy/sell **retired 2024-08-16** (CODE VERIFIED header); turnover live; hold_mktcap quarter-end | China flow surfaces | LIVE with documented retirement | Market-wide, not issuer-event. |
| QVIX (A-share IV) | `collectors/china_qvix.py` | `china_qvix` group, 300/50 ETF | session close | N/A | sentiment input | LIVE degrade-to-missing | Index options, not single-name post-print options. |
| #5822 event ontology (proposal) | research PR only | proposed `china_corporate_event.v1` | proposed `event_time` / `published_at` / `known_at` / `ingested_at` / `corrected_from` | proposed `contradiction_refs[]` | proposed dossier / special sits / graphs / GMI | **NOT_BUILT** (PRIMARY SOURCE VERIFIED against PR #5822 text §8) | Must not become a second event store beside `event_workspace.v1`. |

---

## 2. What Earnings OS owns vs what China already built

`DEC:EARNINGS-INTELLIGENCE-PROGRAM-OWNERSHIP` gives Earnings OS **event, document, claim, and earnings product truth**, including the Event Workspace payload. That ownership is **not vacated by China having collectors**.

What China has built is **source planes and a context desk**, not an event product:

- no `canonical_event_id` across 预告 / 快报 / 正式披露 / 问询 / Q&A;
- no completeness object (`filing` / `release` / `transcript` / `consensus` analog);
- no typed-absence grammar;
- no claim-span citations;
- no `read_event_workspace` consumer for an A-share issuer.

`research/earnings_intelligence/` has **zero** China / A-share mentions (CODE VERIFIED this session). The V2 masterplan's only "China" hit is a US topic-monitor example ("China exposure"), not an A-share event lane.

---

## 3. Missing delta (smallest)

One Earnings-OS-owned **China listing-identity adapter** onto the already-frozen `company_event.v1` / `event_workspace.v1` contract, after E2, that:

1. mints `company_id` from Stock Identity / Data OS listing identity, **not** `cik:`;
2. maps the A-share disclosure chain onto existing `EVENT_STATES` (`scheduled` / `rescheduled` / `completed_partial` / `complete` / `corrected`) — those states already exist (CODE VERIFIED `events.py:43-55`);
3. **references** `china_earnings`, `china_preannounce` (both parquets), `china_filings`, `china_irm`, `china_einteraction` — does not copy them into a warehouse;
4. leaves LHB, Connect, QVIX, Special Situations UI, and #5822 vertical lobes in `china-system`.

That is the whole CN-G0 delta. Everything else is either collected or forbidden (new store, score, independent G / CN-G lane, E2 scope change, occupying `censuses/G0/`).

---

## 4. What must remain inside Earnings OS

- Event identity, lifecycle, completeness, typed absences, claim citations, workspace publication/read.
- Any future "reinterpretation" object (first print vs later 快报 vs later 问询 vs later Q&A answer).
- Adjudication of whether `china_corporate_event.v1` is an alias of `company_event.v1` or is refused as a duplicate (`duplicate_control_planes` spirit; `DEC:EARNINGS-INTELLIGENCE-PROGRAM-OWNERSHIP`).

## 5. What must remain inside China-system

- All CN collectors and their rights/pacing/shard budgets.
- Special Situations product page and `china_special_sits.v1` snapshot.
- Signal-lab / `china_validation` (including the `guidance` post-announcement-drift family).
- QLedger `cn_special_sits` salience claims (inquiry + unlock).
- Flow/attention sensors (LHB, Connect, QVIX, 千股千评).
- #5822 P0 families that are **not** events: visits, ownership, named actors, SOE demand, capacity radar.

---

## 6. Non-goals honored

No code. No model. No new event store. No Prophet. No score. No change to E2 (AAPL FY2026 Q3 Terminal + dossier glance, frozen).
