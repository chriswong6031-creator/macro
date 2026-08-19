# CN-G0 — Event-clock matrix (China)

**Lane id:** `CN-G0`. **Not** US GROK-G0 (canonical: `research/earnings_intelligence/g0/G0_EVENT_CLOCK_AND_CONTRACT_CENSUS.md`, PR #5955; governing adjudication: `research/alpha_intelligence/C0G_G0_SEAT_ADJUDICATION_2026-08-19.md`, PR #5933).
**Lane:** GROK-CN-G0 · **Date:** 2026-08-19 · **Pin:** `6353b77f5aaa`
**Parent:** China Alpha Intelligence program (PR #5953; superseded #5822 draft §7.2 / §7.5 / §8). US G0 clocks stay in the US packet.

Four independent clock vocabularies already exist on the China event-adjacent estate. They do not interoperate. Earnings OS `company_event.v1` is a fifth vocabulary that China cannot currently enter.

---

## 1. Clocks that exist

| Clock name | Where | What it means | Unit | Who may write | Who may read as truth |
|---|---|---|---|---|---|
| `ann_date` / `publish_ts` | Tushare forecast; CNInfo filings | Exchange-published announcement calendar date | Asia/Shanghai date | collector | special sits, validation `guidance` family |
| `first_seen` | IRM, e互动, china_reports | House first observation of that row | UTC ISO | collector (carried through corrections) | nobody as a product clock |
| `fetched_at` | same | Last observation | UTC ISO | collector | debugging / freshness chips |
| `asof` (snapshot) | china_analyst, china_comment, china_lhb, china_earnings calendar | Build-day slice | UTC date | collector refresh | extras / page |
| `next_date` / `last_date` | china_earnings calendar | Soonest future booked-or-actual disclosure; most recent actual | exchange date | collector (latest revision wins) | page countdown (client-side) |
| booked / revised / actual columns | china_earnings raw Eastmoney table | `首次预约时间`, `一次/二次/三次变更日期`, `实际披露时间` | exchange date | Eastmoney | collapsed to `next_date` before the engine sees them |
| `observed_at` / `source_available_at` | Earnings OS `company_event.v1` | Consumer observation vs source availability (PIT firewall) | UTC datetime | event spine | `read_event_workspace` |
| `data_asof` | `china_special_sits.v1` | Oldest per-block input asof | date | special sits scan | page staleness chip |
| QLedger `asof` | `cn_special_sits` claims | Inquiry: letter date. Unlock: registration day (`today`) | date | asia-lane `register_claims` | Eval OS |
| proposed `known_at` / `ingested_at` / `corrected_from` | #5822 `china_corporate_event.v1` | House-knowledge vs ingest vs prior event | unspecified | **not built** | — |

---

## 2. Mapping A-share disclosure vintages onto Earnings OS states

`EVENT_STATES` already contains the reinterpretation lifecycle (CODE VERIFIED `engine/company_intelligence/events.py:43-69`):

| A-share vintage | Native tape | Earnings OS state that already fits | Joined today? |
|---|---|---|---|
| 首次预约 | `china_earnings` booked column | `scheduled` | No — collapsed into `next_date` |
| 一次/二次/三次变更 | same | `rescheduled` | No — latest wins, history dropped at engine |
| 业绩预告 (yjyg) | `china_preannounce/forecast.parquet` | `completed_partial` | No event id |
| 业绩快报 (yjkb) | `china_preannounce/preliminary.parquet` | `completed_partial` → later `corrected` when formal files | **Collected, no consumer** |
| 正式报告 / 实际披露 | `china_earnings` `实际披露时间` + filings title | `complete` | Date only, no document bind |
| 问询函 after the print | filings `kind=letter` | sibling event, or `corrected` if it restates the print | Separate `inq_{code}_{date}` QLedger key |
| 回函 / 复函 | filings `kind=reply` | `corrected` on the inquiry, not on the earnings event | Sibling row |
| 互动易 / e互动 answer landing days later | IRM / e互动 keep-LAST | `corrected` on a Q&A document, not on the earnings event | Row mutation, no event id |
| Sell-side revision after the print | `china_reports` tape | not an issuer event (expectations family) | Unjoined |

The US flagship AAPL workspace is itself incomplete on the same axis: `questions_count` is a typed absence, `consensus` unlicensed, `reaction not_joined` (CODE VERIFIED E1P handoff). China is not behind on "having a reaction join"; both venues lack a joined post-event reinterpretation object.

---

## 3. PIT quality by tape

| Tape | Look-ahead risk | Honest as-of | Failure mode if used as event truth |
|---|---|---|---|
| china_earnings `next_date` | Low if treated as a schedule | Exchange booked date | Using `asof` (build day) as if it were the disclosure |
| 预告 forecast snapshot | Medium: windowed refresh can drop older quarters | `ann_date` | Treating current parquet as history |
| 快报 preliminary | Same | unused | Silent hole — later sessions assume 快报 is "not collected" |
| filings keep-FIRST | Low for metadata | `publish_ts` CST | Title recategorization never updates an existing announcementId |
| IRM / e互动 keep-LAST | **Correction is the point** | `first_seen` vs `fetched_at` | Using `fetched_at` as first-print time |
| china_reports keep-LAST | Same | `first_seen` | Interpreting raw `ratingChange` (explicitly unverified) |
| Tushare forecast_hist | Token/gate; hist keep-last on `(ticker, ann_date)` | `ann_date` | Scoring `guidance_score` (derived) as if it were exchange type |
| LHB / Connect / QVIX | Session/daily | session date | Treating flow as a document restatement |
| event_workspace.v1 | High if China forced through CIK | CIK + fiscal period | A guessed CIK / ticker-as-issuer forks dual-listed events |

---

## 4. Interoperability

**None.** No module accepts `(listing_id, fiscal_period, event_type)` and returns the 预告 + 快报 + 正式 + 问询 + Q&A vintages. `china_special_situations._by_ticker_rollup` is a **same-day snapshot join**, not a PIT event join.

PASS-0 already named this class of gap at estate level: four PIT vocabularies, no cross-source event dedup. China's post-event tapes are a **fifth cluster** of the same problem, local to issuer events.

---

## 5. Clock that G must not invent

A sixth timestamp vocabulary (`china_corporate_event.v1`'s `known_at` / `ingested_at` as a parallel spine) is a forbidden duplicate of `observed_at` / `source_available_at`. If those names are useful they become aliases inside the Earnings OS adapter, after E2, not a new schema.
