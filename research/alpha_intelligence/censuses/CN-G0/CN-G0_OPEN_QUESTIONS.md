# CN-G0 — Open questions (China)

**Lane id:** `CN-G0`. **Not** US GROK-G0 (canonical: `research/earnings_intelligence/g0/G0_OPEN_QUESTIONS.md`, PR #5955; the #5953 rival copy was withdrawn). Do not file these as answers to the US G0 open questions.
**Lane:** GROK-CN-G0 · **Date:** 2026-08-19 · **Pin:** `6353b77f5aaa`
**None of these unblocks writing this census.** They unblock a later Earnings OS E-wave after E2.

---

| ID | Question | Why it matters | Who answers | Default if unanswered |
|---|---|---|---|---|
| GQ1 | What is `company_id` for an A-share issuer that has no EDGAR CIK? | `company_id_for_cik` is the only mint path today. | Earnings OS + Stock Identity / Data OS | Refuse to mint. Typed absence, never a ticker-padded fake CIK. |
| GQ2 | Is an A+H issuer one `company_event` or two? | Dual-list law already says one issuer, many securities. HKEX and CNInfo clocks differ. | Earnings OS (same law as GOOG/GOOGL `do_not_redo`) | One issuer event; reactions attach per listing. |
| GQ3 | Is 业绩预告 the same `event_type=earnings_results` or a distinct `event_type`? | Identity is `(company_id, fiscal_period, event_type)`. A second type forks 预告 from the formal print. | Earnings OS contract wave | **Same event**, vintages on the lifecycle (`completed_partial` → `complete`). Matches "id never sees a revision number". |
| GQ4 | Is a post-print 问询函 the same event (`corrected`) or a sibling (`event_type=exchange_inquiry`)? | Inquiry can be about the print or about something else (减持, 重组). Title-keyword cannot always tell. | Earnings OS + filings category | Default sibling. Join as `related_event` only when the letter title names the same fiscal period (heuristic later; not this census). |
| GQ5 | Which 预告 tape is primary — Eastmoney or Tushare? | Two stores, one derived `guidance_score`. | Earnings OS after a rights/coverage check | Eastmoney keyless tape as document primary; Tushare hist as validation substrate only. |
| GQ6 | May workspace Q&A cite IRM/e互动 **text**, or only metadata? | Collectors store answer text as an input plane, "not a display surface". | Earnings OS + rights | Metadata + typed "body not licensed" until a rights verdict. Same spirit as US consensus `unlicensed`. |
| GQ7 | Does #5822's `china_corporate_event.v1` get renamed as an alias or refused? | Duplicate event truth. | RESOLVED 2026-08-19 (c0g seat + canonical #5953 masterplan: refused — `DEC:ALPHA-INTEL-EARNINGS-EVENT-TRUTH-IS-VENUE-NEUTRAL`) | Refuse the schema name; harvest field list. |
| GQ8 | Is there an in-tree `stk_surv` / institutional-visit collector? | #5822 P0-A. This session did not find one. | China program / B-lane | Treat as **absent**. Not a G blocker. |
| GQ9 | Production depth of `preliminary.parquet` and IRM shards? | Sparse worktree omits `data/`. | Next E-wave with `worktree_sparse.py add data` or live replica | UNKNOWN. Census treats the **contracts** as verified, not the row counts. |
| GQ10 | Should QLedger `cn_special_sits` ever register 预告/快报? | Today only inquiry + large unlock, direction=0. | Eval OS + Earnings OS | No, until an event_id exists. Registering off ticker+date would fork identity. |
| GQ11 | Client-side days-to-disclosure vs server `asof` | Page countdown is computed in the browser so JSON does not stale. | Product, not G | Keep. Adapter must not replace it with a scored "event risk". |
| GQ12 | HK earnings / HKEX news vs CN? | Sister market, different filing clock. | Out of this G0 unless Earnings OS expands | Stay China A-share. Do not silently include HK. |

---

## Closed by this census (do not re-open)

| Item | Answer |
|---|---|
| Does Earnings OS own China event truth? | Yes, as product/contract owner. China-system owns the source planes. `DEC:EARNINGS-INTELLIGENCE-PROGRAM-OWNERSHIP`. |
| Is there an independent G build lane? | No. |
| May E2 be broadened to a China flagship? | No. |
| Is `china_event_calendar` the issuer clock? | No. It is NBS/PBoC/LPR date arithmetic. |
| Is 快报 missing? | No. It is collected and unused. |
| Is Q&A missing? | No. Two collectors exist; the product and the event join are missing. |
| Is a China options reaction tape available at name level? | No. QVIX is index IV. US options reaction is also `not_joined`. |
