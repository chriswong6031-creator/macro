---
key: SPY-REST-UNADJUSTED-DAILY-MATCHES-FLATFILE-OHLC
claim: >
  Massive/Polygon GET /v2/aggs/ticker/SPY/range/1/day/{D}/{D}?adjusted=false
  matches public R2 massive_stock_day SPY.parquet on open, high, low, close, and
  transactions for all 12 sessions 2026-08-03 through 2026-08-18 present in that
  parquet; parquet volume is the integer truncation of the REST float; REST daily
  close equals /v1/open-close close and not afterHours on 2026-08-19.
falsifier: >
  Re-fetch those 12 sessions and find any OHLC or n mismatch against the same
  SPY.parquet vintage, or find a session where REST daily close equals open-close
  afterHours rather than close.
so_what: >
  W2C v2 may use the REST unadjusted daily close as the same numeric close-ratio
  input the flat-file SPY rows produced, but must version the contract: v1 did
  not authenticate RTH close; REST daily close is the official close, not the
  last after-hours print. Preserve exact REST floats in source bytes; do not
  silently inherit parquet int64 volume.
kind: data
verified_at: 2026-08-20
verified_by: >
  Live REST 2026-08-20T11:03Z plus public R2 SPY.parquet Last-Modified
  Wed, 19 Aug 2026 22:53:53 GMT latest_date=2026-08-18. Open-close 08-19
  close=769.06 afterHours=770.01.
scope:
  - macro
  - "WS:MARKET-MEMORY-W2C"
  - engine/neuralweb/market_memory_technical_observation.py
  - config/market_memory_technical_price_basis.v1.json
confidence: verified
---

# REST unadjusted daily SPY matches the v1 parquet close

The quantity is the same on this sample. The authentication claim is not.
