---
key: W2C-M0C-SOL-RATIFIED-REST-SUCCESSOR
question: >
  After M0C qualified the bounded Massive/Polygon single-ticker REST daily
  source and the post-M0C addendum proved that its price fields and activity
  counters have different session scopes, should Sol ratify both freezes and
  authorize the bounded M0D first-v2 vertical slice?
answer: >
  Yes. Ratify DEC:W2C-M0C-V2-REST-SINGLE-TICKER-DAILY together with
  DEC:W2C-M0C-V2-HYBRID-PRICE-ACTIVITY-SCOPE. Keep the sealed source object
  GET /v2/aggs/ticker/SPY/range/1/day/{D}/{D}?adjusted=false and request date D
  as session identity. Keep the 04:30Z / 900s D+1 prospective window. Version
  the v2 technical profile as
  market_memory.private.spy_rth_price_fullday_activity_daily_aggregate.v2:
  XNYS regular-session price rungs, full-market-day activity counters, basis
  massive_rest_day_aggs_unadjusted_rth_price_fullday_activity,
  regular_session_close_authenticated=true, and the existing feature key
  price.raw_close_ratio_20_sessions. Do not switch the sealed source to grouped
  daily and do not reuse v1's single source_session_scope scalar. Authorize only
  the bounded M0D vertical in
  agentos/handoffs/MARKET-MEMORY-W2C-2026-08-20-v2-slice.md. Its next-natural-
  session evening first-availability probe is fail-closed: if the REST bar is
  absent until the same roughly 04:24-04:54Z band that made v1 class-A
  impossible, stop and return to Sol rather than moving the clock, backfilling,
  or silently shipping another impossible prospective window.
rationale: >
  M0C established a bounded source object for exactly SPY, disjoint v1/v2
  lineage and a prospective clock comparable to frozen v1. PR #6083 then
  corrected an important semantic overclaim before implementation: 34/34
  overlapping sessions matched REST adjusted=false on OHLC and transaction
  count, and five-session minute reconstruction showed daily O/H/L/C behave as
  XNYS regular-session price rungs while daily n and volume include materially
  broader activity. Calling the entire object an RTH aggregate would therefore
  mint a false technical contract. The addendum fixes naming and scope without
  changing the chosen source object, clock, feature key or v1 control arm. The
  remaining uncertainty is first-availability on natural future sessions; M0D
  can measure that directly while failing closed before admission.
alternatives:
  - option: Ratify only the original M0C decision and ignore the hybrid-scope addendum
    why_not: >
      That would authorize a writer whose profile name falsely describes volume and
      transaction-count scope. The post-M0C evidence is already canonical and must
      be part of the authority decision.
  - option: Switch the sealed source to grouped daily
    why_not: >
      Grouped reproduces the same SPY values but downloads a whole-market object for
      one ticker. Keep it as an availability/cross-check witness, not the sealed v2
      object.
  - option: Hold M0D until more evening observations accrue
    why_not: >
      M0D's first step is itself the bounded natural-session availability probe and
      cannot admit if that probe falsifies the frozen clock. Waiting adds calendar
      latency without reducing architecture risk.
  - option: Move the v2 decision clock earlier or later before implementation
    why_not: >
      That destroys prospective comparability and converts a measured source question
      into clock retuning. Test the frozen window first.
  - option: Reuse v1 stores or repair v1 abstentions with REST evidence
    why_not: >
      Violates the frozen evidence/control-arm law. v1 remains immutable and disjoint.
  - option: Thin-publish SPY through public R2
    why_not: >
      Public SPY R2 remains separately held and is unnecessary for M0D.
evidence:
  - "agentos/decisions/DEC-W2C-M0C-V2-REST-SINGLE-TICKER-DAILY.md"
  - "agentos/decisions/DEC-W2C-M0C-V2-HYBRID-PRICE-ACTIVITY-SCOPE.md"
  - "agentos/handoffs/MARKET-MEMORY-W2C-2026-08-20-m0c.md"
  - "agentos/handoffs/MARKET-MEMORY-W2C-2026-08-20-m0c-addendum.md"
  - "agentos/handoffs/MARKET-MEMORY-W2C-2026-08-20-v2-slice.md"
  - "agentos/discoveries/DSC-SPY-REST-UNADJUSTED-DAILY-MATCHES-FLATFILE-OHLC.md"
  - "agentos/discoveries/DSC-SPY-DAILY-AGG-IS-RTH-PRICE-FULLDAY-ACTIVITY.md"
  - "agentos/discoveries/DSC-MASSIVE-GROUPED-DAILY-AVAILABLE-AT-XNYS-CLOSE.md"
  - "PR #6078 merged as 36da0a3c7d8e30bfee0c7dcd0a6ef2a974627c1b"
  - "PR #6083 merged as 987bc63d4ff79a76d1ed7d0da8d639b5ff6728c4"
affects:
  - WS:MARKET-MEMORY-W2C
  - agentos/handoffs/MARKET-MEMORY-W2C-2026-08-20-v2-slice.md
confidence: high
reversibility: easy
decided_by: ceo-sol
decided_at: 2026-08-20
---

## Authority consequence

This decision authorizes M0D only, against the **hybrid** v2 technical contract
already frozen on main. It does not authorize v1 mutation, historical backfill,
public SPY R2 publication, the separately parked D-class coherence repair,
broad Market Memory redesign, or any model/rank/signal/trade authority.

M0D must prove its own source clock, immutable source-owner behavior,
technicals-v2/store isolation, registration-v2 bytes, experience-v2 timing and
first natural prospective admission before any later wave can begin.
