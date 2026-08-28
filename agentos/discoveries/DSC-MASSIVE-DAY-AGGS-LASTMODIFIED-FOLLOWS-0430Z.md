---
key: MASSIVE-DAY-AGGS-LASTMODIFIED-FOLLOWS-0430Z
claim: >
  Massive S3 objects us_stocks_sip/day_aggs_v1/YYYY/MM/YYYY-MM-DD.csv.gz for US
  equity session D become HEAD-able with LastModified clustered on calendar day
  D+1 at 03:44–05:37 UTC (almost entirely 04:24–04:54), not at the house-doc
  ~11:00 ET / 15:00 UTC T+1 mark; 7 of 24 weekday sessions 2026-07-17..08-19
  had LastModified after 04:45 UTC D+1.
falsifier: >
  Re-run boto3 head_object on files.massive.com for keys
  us_stocks_sip/day_aggs_v1/YYYY/MM/YYYY-MM-DD.csv.gz over the next 10 weekday
  sessions and observe a median LastModified at or after 15:00 UTC on D+1, or
  observe 0 of 10 with LastModified after 04:45 UTC D+1. Either result
  revises the distribution used by DEC:W2C-M0B-V1-SOURCE-WINDOW-UNACHIEVABLE.
so_what: >
  Do not schedule same-session W2C admission, massive_stock_day incremental, or
  technical capture on the assumption that the stocks day_aggs file is a next-
  morning 11:00 ET product, and do not treat the 22:30 UTC nightly collect as
  able to see session D — that job always starts ~6 hours before this object's
  LastModified. Do not infer first availability from when a collector happened
  to look; HEAD the object.
kind: data
verified_at: 2026-08-20
verified_by: >
  boto3 head_object against files.massive.com at 2026-08-20T09:48:17Z and
  09:49:16Z for 24 weekday keys 2026-07-17 through 2026-08-19 plus 2026-08-20
  (403). Exact LastModified table in
  agentos/handoffs/MARKET-MEMORY-W2C-2026-08-20-m0b.md. Contrasts
  research/MASSIVE_ADVANCED_INTEGRATION_MASTERPLAN_BY_FABLE.md §1.1
  "prior-day file ready ~11:00 ET" and collectors/massive_flatfiles.py
  latest_available docstring "T+1 cadence".
scope:
  - macro
  - collectors/massive_flatfiles.py
  - collectors/massive_stock_day.py
  - "WS:MARKET-MEMORY-W2C"
confidence: verified
---

# Stocks day_aggs LastModified is a 04:30Z-band clock

This is the availability clock W2C v1 was not measured against before activation.
The 11:00 ET figure remains possibly true for other Massive products (trades,
quotes, options aggregates). It is false for `us_stocks_sip/day_aggs_v1`.
