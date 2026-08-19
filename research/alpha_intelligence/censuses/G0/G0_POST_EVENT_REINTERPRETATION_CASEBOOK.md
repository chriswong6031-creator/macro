# G0 — Post-event reinterpretation casebook (China)

**Lane:** GROK-CN-G0 · **Date:** 2026-08-19 · **Pin:** `e9800a01fd63`
**Rule:** cases are repo artifacts or documented production objects, not invented stories.

---

## Case C1 — Disclosure booking already *is* a reinterpretation chain

**What happened in the system:** `collectors/china_earnings.py` fetches Eastmoney `stock_yysj_em` and keeps four booked-date columns plus `实际披露时间`. The collector then **collapses** them: latest revision wins, engine `earnings_calendar()` emits only `{next_date, last_date}`.

**Why it is reinterpretation:** an A-share issuer may book, then change the date three times, then file. That is `scheduled → rescheduled → complete` in Earnings OS language.

**What the product sees:** a countdown. The revision history is discarded before the page.

**Delta:** stop collapsing at the adapter. Do not rebuild the collector.

**Evidence:** `collectors/china_earnings.py:7-14, 34-36`; `engine/china_extras.py:107-128`.

---

## Case C2 — 快报 is collected and then thrown away

**What happened:** `china_preannounce` writes both `forecast.parquet` (业绩预告) and `preliminary.parquet` (业绩快报). Special Situations `_preannounce_block` reads only `forecast.parquet`.

**Why it is reinterpretation:** 快报 is the first *actual* number after the *guided* range. Formal 年报/季报 is the second actual. PEAD-style work and any "did they walk the 预告" question need both vintages.

**What the product sees:** type counts and "biggest movers" on 预告 only.

**Delta:** the missing consumer is an Earnings OS completeness slot (`release` / `completed_partial`), not a second parquet.

**Evidence:** `collectors/china_preannounce.py:4-13, 30-31`; `engine/china_special_situations.py:550-552`. Grep of `preliminary.parquet` outside the collector: empty.

---

## Case C3 — Inquiry letter and reply are siblings, not a correction of the print

**What happened:** filings categorize `问询函/监管函/关注函` as `inquiry_letter` and sub-kind `letter` / `reply` / `attachment`. QLedger registers `inq_{secCode}_{announce_date}` once. A reply is a new `announcementId` (keep-FIRST), so it cannot correct the letter row.

**Why it is reinterpretation:** exchange Q&A after a print is the A-share analog of a follow-up 8-K or an amended exhibit — it often forces the issuer to restate or clarify the earnings narrative.

**What the product sees:** an inquiry queue on Special Situations, salience-only QLedger claims, no bind to the fiscal-period earnings event.

**Landmine:** UTC vs CST date keys. Sidecar checks ±1 day only for event dates `<= 2026-07-06`. Applying that window later would suppress distinct consecutive-day letters.

**Evidence:** `collectors/china_filings.py:138-178`; `engine/china_special_situations.py:1103-1112, 1241-1266`.

---

## Case C4 — 互动易 / e互动 already implement document-level correction

**What happened:** both Q&A collectors are append-only with keep-LAST on the exchange's question id. An unanswered row is later overwritten when the 董秘 answers. `first_seen` is preserved; `fetched_at` moves.

**Why it is reinterpretation:** the **question** is the first print; the **answer** is the correction. This is the China-native transcript/Q&A plane (there is no US-style conference-call tape for most A-shares).

**What the product sees:** nothing. Both legs are pending-tier inventory on `china_altdata` (`engine/china_signal_lab.py`). #5822 §7.4 wants response-delay / refuse / contradiction features on this tape.

**Delta:** treat IRM/e互动 as the `transcript` / Q&A completeness slot for a China `event_workspace`, with typed absence when the issuer is not on that exchange's platform.

**Evidence:** `collectors/china_irm.py:35-41`; `collectors/china_einteraction.py:42-48`.

---

## Case C5 — Two forecast planes, one pending score-shaped number

**What happened:** Eastmoney 预告 (keyless, special-sits) and Tushare `forecast` (gated, `guidance_score` in [-1,1], `china_validation` family `guidance` with `sign_expected +1` post-announcement drift) both exist. `report_rc` accrues per-analyst EPS/target for a future revision-momentum leg and is not surfaced.

**Why it is reinterpretation:** a later sell-side revision is an expectations change, not a restatement of the issuer event. #5822 §7.2 says fuse-without-collapsing.

**Collision:** deriving `guidance_score` inside the collector is already a stance-shaped transform. Earnings OS must consume the **exchange type + range**, not the signed score, if it ever binds 预告 into a workspace.

**Evidence:** `collectors/tushare_forecast.py:1-18, 42-51`; `engine/china_validation.py:18-20, 681-686`; `engine/china_signal_lab.py:187-188`.

---

## Case C6 — AAPL workspace shows the US hole the China program must not copy blindly

**What happened:** E1P live object `evt_cik0000320193_2026q3_results` has Exhibit 99.1 + transcript, `questions_count` typed absence (empty analyst role), `consensus` unlicensed, `reaction not_joined`, slides absent (E1P handoff, 2026-08-17).

**Why it belongs in a China casebook:** "post-event reinterpretation" is unbuilt on the **flagship US event** too. China's missing join is not a reason to mint `china_corporate_event.v1` while E2 is still the frozen next_action.

**Evidence:** `agentos/handoffs/EARNINGS-INTELLIGENCE-OS-2026-08-17.md` verified payload; `research/earnings_intelligence/E2_IMPLEMENTATION_HANDOFF.md`.

---

## Case C7 — #5822 names the ontology and must not become the store

**What happened:** open research PR #5822 §8 specifies `china_corporate_event.v1` with `event_id`, `listing_id`, `corrected_from`, `contradiction_refs[]`, and a one-corpus-many-families extraction method. Status in that packet: `Full announcement event ontology = NOT_BUILT`.

**Why it is a collision, not a case of missing code:** Earnings OS already froze `company_event.v1` + `event_workspace.v1` with a correction-stable id that "never sees a call date, a document hash, or a revision number" (`events.py:11-14`). A second canonical event object for China would split event truth — the exact prohibition in `DEC:EARNINGS-INTELLIGENCE-PROGRAM-OWNERSHIP`.

**Delta:** #5822's *fields* (listing_id, contradiction_refs, novelty, time_to-impact) are adapter-payload candidates. The *schema name* is not.

**Evidence:** `git show refs/tmp/pr5822:…` §7.5 / §8; `DEC:EARNINGS-INTELLIGENCE-PROGRAM-OWNERSHIP`.

---

## Case C8 — Flow after the print is a different object

**What happened:** LHB (seat-level, ~5d window), Connect (northbound net retired 2024-08-16), QVIX (index IV), 千股千评 attention hist all exist as context sensors. None is joined to a fiscal-period event.

**Why it is not the G delta:** US `reaction not_joined` is already the frozen optional source on `event_workspace.v1`. Joining LHB to an earnings event would be a **reaction** slot, display-only, after the document vintages exist. `DNR:KILL-CN-SUPPLY-ABSORPTION` forbids treating post-event price absorption as a scored family.

**Evidence:** `collectors/china_lhb.py` header; `collectors/china_connect.py:14-21`; `DNR:KILL-CN-SUPPLY-ABSORPTION`.

---

## Coverage note (adjudication gate)

These eight cases are the motivating exemplars for a China G-wave. A future rule that only handles US 8-K amendments, or only handles 预告 type labels, **refuses this casebook** and is not the answer.
