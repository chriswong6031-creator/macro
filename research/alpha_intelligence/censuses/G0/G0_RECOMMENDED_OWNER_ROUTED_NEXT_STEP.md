# G0 — Recommended owner-routed next step

**Lane:** GROK-CN-G0 · **Date:** 2026-08-19 · **Pin:** `e9800a01fd63`
**Addressee:** `WS:EARNINGS-INTELLIGENCE-OS` and FABLE-00 (`WS:ALPHA-INTELLIGENCE-INTEGRATION` wave `c0g`).
**China program in scope:** Institutional Alpha / PR #5822 Corporate Event Intelligence — **not** a new owner.

---

## Verdict

**Do X because Y.** After E2 ships unchanged, Earnings OS opens one later E-wave that freezes a **China listing-identity adapter** onto the existing `company_event.v1` / `event_workspace.v1` contract, sourced from the collectors that already exist. Do not build `china_corporate_event.v1`. Do not start that wave now.

**Strongest runner-up:** leave China events entirely inside `china-system` and have Earnings OS stay US-only forever.

**Single flip condition:** if FABLE-00 (or a superseding DEC) rules that `DEC:EARNINGS-INTELLIGENCE-PROGRAM-OWNERSHIP` does **not** cover A-share issuer events, the runner-up wins and #5822 may own a China event object — still not a G lane, and still not a score.

---

## Why this is the smallest delta

The A-share post-event estate is **collector-rich and identity-poor**.

- Disclosure booking, 预告, 快报, filings metadata, inquiry/reply kinds, two Q&A tapes, a report-revision tape, Special Situations, and QLedger salience claims already exist.
- `EVENT_STATES` already contains `scheduled` / `rescheduled` / `completed_partial` / `complete` / `corrected`.
- The US workspace already knows how to keep one event id across a source-SHA correction.
- What does not exist is a `company_id` that is not a CIK, and a join that holds 预告 + 快报 + 正式 + (optional) 问询/Q&A as vintages of one fiscal-period event.

That join is event-product work. Event-product work is Earnings OS. E2 is the frozen US glance and must finish first.

---

## What the later E-wave is (spec only — not this PR)

Observable acceptance, when it is eventually commissioned:

1. E2 remains green on AAPL; this wave does not edit E2 handoff files or the AAPL nest.
2. `company_id` for a named A-share issuer is minted from Stock Identity / Data OS and is **not** `cik:`.
3. One golden China fiscal period (pick after sparse `data/` opt-in; do not invent the name here) binds:
   - booked/revised/actual dates from `china_earnings` **without collapsing revision history**;
   - 预告 from `forecast.parquet`;
   - 快报 from `preliminary.parquet` or typed absence;
   - formal disclosure date;
   - inquiry/Q&A as related documents or typed absence.
4. Same `canonical_event_id` survives a 快报 arriving after 预告 (`completed_partial` → `corrected` / `complete`), new `generation_id`.
5. No PDF body fetch. No `guidance_score` in the workspace facts. No LHB/Connect in the document slots. No Prophet flag.
6. Special Situations page unchanged. China collectors unchanged except a documented read contract.

Until that wave is commissioned, **next action on Earnings OS stays E2**.

---

## What FABLE-00 should record at `c0g`

- G0 **returned**, China-scoped, addressed to Earnings OS.
- G lane remains **WAIT** on E2 (unchanged from C0).
- #5822 `china_corporate_event.v1` is a **named collision**, not a build license.
- Lane B still reconciles with #5822 on ownership/visits; that is not G.

---

## Explicit non-proposals

- No implementation in this packet.
- No model, score, or Prophet family.
- No new event store.
- No E2 change.
- No independent G build lane.
- No China Earnings OS program key.
