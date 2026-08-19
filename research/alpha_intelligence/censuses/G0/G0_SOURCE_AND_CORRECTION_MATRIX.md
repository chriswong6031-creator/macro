# G0 — Source and correction matrix (China)

**Lane:** GROK-CN-G0 · **Date:** 2026-08-19 · **Pin:** `e9800a01fd63`

---

| Source | Rights / access | Store | Dedup / correction | Body policy | What a later restatement does | Fit as event_workspace source |
|---|---|---|---|---|---|---|
| Eastmoney 预约披露 `stock_yysj_em` | Keyless akshare | `data/china_earnings/calendar.parquet` | Latest booked column wins; actual overrides when present | Dates only | New booked date replaces `next_date`; history of prior bookings dropped at engine | **Schedule / reschedule** plane. Keep revision columns in the adapter. |
| Eastmoney 业绩预告 `stock_yjyg_em` | Keyless | `data/china_preannounce/forecast.parquet` | Quarter-window refresh | Type + range, no PDF | Later 预告 for same ticker+quarter overwrites if refresh replaces the slice (INFERRED) | **completed_partial** facts. Use exchange `预告类型` verbatim, not `guidance_score`. |
| Eastmoney 业绩快报 `stock_yjkb_em` | Keyless | `data/china_preannounce/preliminary.parquet` | same | Preliminary actuals | Formal report should `correct` this vintage — **no consumer today** | **completed_partial / corrected**. Highest-leverage unused tape. |
| Tushare `forecast` | Token 2000积分, gated | `data/tushare/forecast*.parquet` | `(ticker, ann_date)` keep-last on hist | Type + p_change range | keep-last on same announcement date | Duplicate of Eastmoney 预告 if both bound. Prefer one primary; other as receipt. |
| Tushare `report_rc` | Token 8000积分, 1 call/h | `data/tushare/report_rc.parquet` | first-seen on analyst-report key | Machine fields | First row wins — later vendor edit is **not** applied | Expectations family, not issuer event. |
| Eastmoney 研报 list | Keyless; **no PDF** | `data/china_reports/reports.parquet` | `infoCode` keep-LAST | Machine fields only (redistribution limit) | Same-day re-pull corrects; `first_seen` preserved | Expectations / revision tape. |
| Eastmoney 盈利预测 snapshot | Keyless | `data/china_analyst/forecast.parquet` | Daily overwrite | Coverage counts + EPS | No history of the snapshot itself | Consensus slot (analog of US unlicensed consensus). |
| CNInfo `hisAnnouncement/query` | Keyless public; metadata only | `data/china_filings/filings.parquet` | **keep-FIRST** `announcementId` | Title, category, URL, `publish_ts` | A title fix at the exchange **never updates** the row | Document index. Category is title-keyword, not ontology. |
| CNInfo inquiry (legacy collector) | Retired | `data/china_inquiry/` archaeology | n/a | metadata | Do not revive | Filings plane is the owner. |
| 深交所互动易 | Keyless; shard ≤40 names/night | `data/china_irm/qa.parquet` | `indexId` keep-LAST | Q&A text stored as input, not displayed | Answer arrival **corrects** the question row | China `transcript` / Q&A slot (SZ). Coverage is sharded — typed absence is honest. |
| 上证e互动 | Keyless; uid_map + shard | `data/china_einteraction/qa.parquet` | `feed_id` keep-LAST | same | same | China Q&A slot (SS). New listings can be uncovered 30d. |
| LHB Eastmoney | Keyless | `data/china_lhb/detail.parquet` | daily aggregate | seats / 净额 | Next day is a new asof, not a correction | Reaction / attention only. |
| Stock Connect Eastmoney | Keyless | connect parquets | daily | flows | Northbound net **permanently retired** 2024-08-16 | Not an issuer event. |
| QVIX optbbs | Keyless; single host | `china_qvix` | session | IV | Degrade to missing | Index vol, not name options. |
| US EDGAR 8-K / transcript | Existing Earnings OS | R2 event_workspaces nest | same event id, new generation, `corrected` | Exhibit + Terminal transcript | E1P proven on AAPL | **Do not reuse CIK ids for A-shares.** |
| #5822 proposed full announcement corpus (`anns_d` or licensed) | **Not in tree**; rights not adjudicated | none | proposed | #5822 wants bodies for extraction | n/a | Capture build is **out of G0**. Needs source-rights + Data OS + off-render R2 (PASS-0 §8 pattern). Current filings tape is metadata-only on purpose (RUL-4). |

---

## Correction behaviors, classified

| Pattern | Used by | Safe for event identity? |
|---|---|---|
| keep-FIRST (immutable row) | china_filings | Yes for documents. Bad for "the letter was answered" — answer is a new row. |
| keep-LAST (mutate in place, preserve `first_seen`) | IRM, e互动, china_reports | Yes for **document** correction. Must not be the **event** id. |
| latest-column-wins collapse | china_earnings engine view | Loses the reschedule history the lifecycle needs. |
| first-seen-wins accrual | tushare report_rc | Preserves original asof; later vendor fix is invisible. |
| generation_id + `corrected` | event_workspace.v1 | **The pattern G should adopt.** Same event, new generation. |
| QLedger once-per-event_key sidecar | cn_special_sits | Salience registration, not document truth. UTC/CST landmine documented. |

---

## Rights riders (binding on any later capture)

- Do not fetch 研报 / announcement **PDF bodies** from the current Eastmoney/CNInfo collectors; they are machine-fields-only by contract.
- Do not route a bulk China filings history around whatever rights freeze #5822's P0 "full corpus" still needs. G0 does not open that capture.
- Tushare legs stay gated; absence is `accruing`, not a hard fail.
- LHB / Connect are not document sources and must not be "corrected into" an earnings workspace.
