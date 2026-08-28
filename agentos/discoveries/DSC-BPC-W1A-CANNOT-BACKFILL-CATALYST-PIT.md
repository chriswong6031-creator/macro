---
key: BPC-W1A-CANNOT-BACKFILL-CATALYST-PIT
claim: >
  Market Memory W1A is a go-forward operational_pit store and cannot supply
  point-in-time prices for past catalyst events; date-keyed daily OHLCV is the
  honest approximation and must be labeled non-W1A.
falsifier: >
  rg -n "operational_pit|historical PIT|backfill" engine/market_memory agentos/workstreams/WS-MARKET-MEMORY-W2C.md
  shows a documented as-of price API for arbitrary past calendar dates with
  receipts, not only go-forward captures.
so_what: >
  Price at Catalyst Date, Catalyst Price Movement, IPO first-day close, and JPM
  Price at Start/End may use dated daily OHLCV as MASTERMIND_DERIVED. They must
  not be claimed as W1A PIT. Current Price/IV/OI/EM remain poison on historical
  rows regardless.
kind: constraint
verified_at: 2026-08-18
verified_by: >
  WS:MARKET-MEMORY-W2C (W1A go-forward operational_pit); engine/live_quotes.py
  latest-only Polygon/Yahoo; no equity NBBO plane; census packet Market options
  estate 2026-08-18
scope:
  - macro
  - biocatalyst
  - "WS:MARKET-MEMORY-W2C"
  - "WS:ADVANCED-DATA-OPTIONS"
  - "WS:BPC-JV-RECON"
confidence: verified
---

## Notes

Export-time overlay fields (live quotes, nightly IV/OI/EM from Polygon EOD) are
a separate poison list. This discovery is specifically about *historical*
as-of prices for past events, which W1A does not backfill.
