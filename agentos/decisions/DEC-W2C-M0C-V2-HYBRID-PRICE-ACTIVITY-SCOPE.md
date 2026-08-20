---
key: W2C-M0C-V2-HYBRID-PRICE-ACTIVITY-SCOPE
question: >
  After REST↔flat-file parity and minute reconstruction, should W2C v2's
  versioned technical contract claim a single session scope (full-market-day or
  RTH), and should the frozen source object change from single-ticker REST daily?
answer: >
  Keep the source object from DEC:W2C-M0C-V2-REST-SINGLE-TICKER-DAILY
  (GET /v2/aggs/ticker/SPY/range/1/day/{D}/{D}?adjusted=false). Version the
  technical contract as a hybrid: price rungs XNYS regular session, activity
  counters full-market-day. Profile
  market_memory.private.spy_rth_price_fullday_activity_daily_aggregate.v2.
  Basis massive_rest_day_aggs_unadjusted_rth_price_fullday_activity.
  regular_session_close_authenticated=true. Keep feature key
  price.raw_close_ratio_20_sessions. Do not switch to grouped daily. Do not
  reuse v1's single source_session_scope scalar.
rationale: >
  34/34 overlapping parquet sessions match REST adjusted=false on OHLC and n;
  volume is parquet floor(REST). Grouped matches single-ticker OHLCV/n (only t
  differs). Minute reconstruction on five sessions shows daily O/H/L/C equal
  RTH extremes and the close never equals the after-hours last print, while
  daily n tracks full-day minute n (~1.00×) and daily volume is 1.21–1.32× the
  RTH minute sum. A single "RTH daily aggregate" or "full-market-day" label
  would repeat v1's false scalar. Grouped is unbounded (~12k rows) for one
  ticker; close-pass already uses it as a cross-check, not as the sealed W2C
  object.
alternatives:
  - option: Keep M0C's shorter name raw_unadjusted_rth_daily_aggregate
    why_not: >
      True for close, false for volume and n. M0D would mint a contract that
      mislabels the activity counters.
  - option: Switch the sealed source to grouped daily
    why_not: >
      Same SPY numbers, whole-market download and quota. Timing receipts that
      used src=massive_grouped remain the availability witness, not the v2
      source object.
  - option: Reuse v1 technical_profile and transport policy
    why_not: >
      v1 pins public R2 ETag/If-Match and us_stocks_sip/day_aggs_v1. REST
      cannot satisfy that transport. Sharing technicals-v1 would flip remaining
      v1 abstentions to missed.
evidence:
  - "DSC:SPY-DAILY-AGG-IS-RTH-PRICE-FULLDAY-ACTIVITY"
  - "DSC:SPY-REST-UNADJUSTED-DAILY-MATCHES-FLATFILE-OHLC"
  - "DEC:W2C-M0C-V2-REST-SINGLE-TICKER-DAILY"
  - >
    python3 field-equality over 34 parquet sessions 2026-07-01..2026-08-18;
    python3 1-minute reconstruction 2026-08-13/14/17/18/19.
affects:
  - "WS:MARKET-MEMORY-W2C"
  - "DEC:W2C-M0C-V2-REST-SINGLE-TICKER-DAILY"
  - config/market_memory_technical_price_basis.v1.json
  - agentos/handoffs/MARKET-MEMORY-W2C-2026-08-20-v2-slice.md
confidence: high
reversibility: easy
decided_by: coo-fable
decided_at: 2026-08-20
review_by: 2026-08-21
---

# v2 versions the hybrid bar; source object stays single-ticker REST

Does not mutate v1. Does not authorize the M0D writer in this session.
