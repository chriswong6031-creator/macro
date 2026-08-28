---
key: SPY-DAILY-AGG-IS-RTH-PRICE-FULLDAY-ACTIVITY
claim: >
  Massive/Polygon unadjusted SPY daily aggregates (REST adjusted=false and the
  public R2 massive_stock_day SPY.parquet, which match each other on OHLC and n)
  are a hybrid: open/high/low/close are XNYS regular-session rungs, while volume
  and transaction count are full-market-day. Daily close is never the after-hours
  last print. v1's single source_session_scope scalar
  provider_daily_aggregate_eligible_trades_full_market_day is therefore false for
  O/H/L/C and true for v/n.
falsifier: >
  python3 reconstruction of /v2/aggs/ticker/SPY/range/1/minute/{D}/{D}?adjusted=false
  on five later sessions where daily low equals the full-day (premarket) low, or
  daily close equals the last after-hours minute close, or daily n equals the
  RTH-only minute-bar n sum.
so_what: >
  W2C v2 must version the price-basis contract with two scopes, not one:
  price_rung_session_scope = xnys_regular_session and
  activity_counter_session_scope = provider_daily_aggregate_eligible_trades_full_market_day.
  Do not name the v2 profile as if volume were RTH. Keep feature key
  price.raw_close_ratio_20_sessions because closes are bit-identical to the
  flat file. Do not reuse v1's regular_session_close_authenticated=false.
kind: data
verified_at: 2026-08-20
verified_by: >
  python3 minute-window reconstruction against REST daily adjusted=false for
  sessions 2026-08-13/14/17/18/19: daily open/high/low equal RTH extremes 5/5;
  daily close inside the 16:00 ET minute bar 5/5 and unequal to full-day last
  print 5/5 (08-19 daily c=769.06 vs last print 770.01); daily n / full-day
  minute n = 1.0011–1.0028; daily v / RTH minute v = 1.21–1.32. Field parity
  vs public R2 SPY.parquet: 34/34 OHLC and n exact, volume parquet==floor(REST).
scope:
  - macro
  - "WS:MARKET-MEMORY-W2C"
  - config/market_memory_technical_price_basis.v1.json
  - engine/neuralweb/market_memory_technical_observation.py
confidence: verified
---

# SPY daily bars are RTH prices with full-day activity

The close-ratio number can stay. The session-scope sentence cannot.
