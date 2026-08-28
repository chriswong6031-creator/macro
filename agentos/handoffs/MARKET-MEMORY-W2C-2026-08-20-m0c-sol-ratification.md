---
workstream: WS:MARKET-MEMORY-W2C
session: sol/w2c-m0c-ratification
model: local
ended_because: complete
prs: [6078, 6083]
decisions:
  - DEC:W2C-M0C-SOL-RATIFIED-REST-SUCCESSOR
discoveries: []
mission: >
  Adjudicate the complete M0C REST successor freeze after both the original
  source decision and the later hybrid price/activity scope correction landed,
  then establish the exact M0D authority boundary without widening the program.
state_before: >
  PR #6078 made M0C source qualification canonical/done but intentionally left
  WS:MARKET-MEMORY-W2C awaiting Sol review. While the first ratification branch
  was in CI, PR #6083 landed a semantic correction: the chosen single-ticker
  REST object's price rungs are XNYS regular-session while its activity counters
  are full-market-day, so the original shorthand raw_unadjusted_rth_daily_aggregate
  was too broad. Main therefore still awaited Sol on both the source object and
  the corrected hybrid technical profile; M0D remained TODO and unauthorized.
changed:
  - path: agentos/decisions/DEC-W2C-M0C-SOL-RATIFIED-REST-SUCCESSOR.md
    what: >
      Ratifies both M0C decisions: keep the single-ticker REST source and 04:30Z
      window, but use the corrected hybrid RTH-price/full-day-activity technical
      profile. Authorizes only M0D with the natural-session availability probe as
      a fail-closed gate.
  - path: agentos/workstreams/WS-MARKET-MEMORY-W2C.md
    what: >
      Removes the answered needs_ceo block, marks the workstream active, records
      the Sol ratification, and makes the already-frozen hybrid-aware M0D packet
      the exact next action.
verified:
  - claim: M0C source qualification is canonical on main.
    command: Read Macro main and PR #6078 merge state.
    result: PR #6078 merged as 36da0a3c7d8e30bfee0c7dcd0a6ef2a974627c1b.
  - claim: The hybrid price/activity correction is canonical on main and changes M0D semantics.
    command: >
      Read agentos/decisions/DEC-W2C-M0C-V2-HYBRID-PRICE-ACTIVITY-SCOPE.md,
      agentos/handoffs/MARKET-MEMORY-W2C-2026-08-20-v2-slice.md and PR #6083.
    result: >
      PR #6083 merged as 987bc63d4ff79a76d1ed7d0da8d639b5ff6728c4;
      v2 profile is market_memory.private.spy_rth_price_fullday_activity_daily_aggregate.v2,
      with RTH price rungs and full-day activity counters; source remains single-ticker REST.
  - claim: The direct workstream still awaited Sol and M0D was unauthorized immediately before this ruling.
    command: Read agentos/workstreams/WS-MARKET-MEMORY-W2C.md on current main.
    result: >
      status=awaiting_review, M0C=done, M0D=todo, needs_ceo asks for ratification
      of both the source and hybrid-scope decisions.
  - claim: The ratification does not broaden into v1 repair, public R2 or D-class coherence.
    command: Read the original M0C, addendum and v2-slice handoffs.
    result: Those boundaries are explicit and remain re-pinned here.
unverified:
  - claim: M0D succeeds under the frozen 04:30Z window.
    what_would_verify: >
      Run the bounded M0D implementation and next-natural-session evening probe.
      If the single-ticker REST bar first appears only in the old 04:24-04:54Z
      race band, stop and return before admission.
  - claim: Any v2 opportunity is admitted prospectively.
    what_would_verify: >
      M0D source-owner/technicals-v2/registration-v2/experience-v2 production
      proof followed by a lawful natural prospective window; no replay/backfill.
unresolved:
  - "Natural-session first-availability N remains limited and M0D must extend it explicitly."
  - "The separately parked D-class massive_stock_day coherence lane remains outside M0D."
  - "The public SPY R2 publisher remains held and unnecessary for M0D."
next_actions:
  - "Dispatch exactly agentos/handoffs/MARKET-MEMORY-W2C-2026-08-20-v2-slice.md as M0D."
  - "Implement the hybrid profile exactly: RTH price rungs, full-day activity counters; do not revert to the superseded all-RTH shorthand."
  - "Keep v1 registration, technicals and experience bytes isolated/unchanged."
  - "If the evening probe falsifies first-availability, stop and return to Sol before any prospective admission."
do_not_redo:
  - "Do not re-litigate v1's class-A source-window classification."
  - "Do not call all REST daily fields RTH; the hybrid scope is now canonical."
  - "Do not switch the sealed source to grouped daily."
  - "Do not reuse v1 experience/technicals roots for v2."
  - "Do not repair historical v1 abstentions with v2 evidence."
  - "Do not move the 04:30Z window inside M0D to manufacture success."
danger_areas:
  - "Single-ticker bar.t is not session identity; request date D is."
  - "REST request_id/raw HTTP body is not source identity; digest parsed results[]."
  - "A successful REST call before one close is not stable first-availability proof across sessions."
  - "v1 trusted reader pin budget and the v2 04:32 stagger are load-bearing constraints in the current M0D packet."
---

# Return point

M0C is ratified **including** the PR #6083 hybrid-scope correction. Start only
M0D from the current v2-slice handoff. The source object remains single-ticker
REST, the technical profile is RTH-price/full-day-activity, and the first natural
availability probe remains a hard stop before prospective admission.
