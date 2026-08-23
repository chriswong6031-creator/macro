---
key: MASSIVE-STOCK-DAY-UNPUBLISHED-TODAY-RETURNS-403
claim: >
  A ranged GET of us_stocks_sip/day_aggs_v1 for an unpublished calendar date
  (today, and weekend dates that are "today") returns HTTP 403 with an empty
  listing, while the same production S3 credential ranged-GETs the latest
  published weekday object as HTTP 206 with gzip bytes. probe_available() used
  to treat that first 403 as product-wide entitlement failure, so
  massive_stock_day.run_incremental() reported no_entitled_date for three nights
  while 2026-08-19/20/21 stock-day objects were readable.
falsifier: >
  With the production MASSIVE_S3_* credential, list+ranged-GET
  us_stocks_sip/day_aggs_v1/2026/08/2026-08-21.csv.gz and observe HTTP 403; or
  probe_available("stock_day", lookback=7) after the unlisted-403 continue
  repair still returns authorization_or_entitlement_failure despite that
  object remaining 206. Either result revises this classification.
so_what: >
  Do not classify a stock-day 403 on calendar-today as a Massive stock
  entitlement regression and do not substitute ThetaData. Continue the
  lookback past unlisted 403s. Listed+403 remains authorization failure
  (the Options flat-file class). Flattening the probe reason into
  no_entitled_date is forbidden; propagate probe.reason into run_status.
kind: runtime
verified_at: 2026-08-23
verified_by: >
  Production-venv probe at 2026-08-23T02:11:50Z using Macro Dashboard .venv
  + closing-bell .env through scripts.close_pass_host_runner.load_env_file
  (values never printed). Sunday 2026-08-23 listed empty / GET 403; Saturday
  2026-08-22 listed empty / GET 404 NoSuchKey; Friday 2026-08-21 listed size
  322582 LastModified 2026-08-22T05:36:24Z / GET 206 gzip; Thursday–Monday
  2026-08-20..17 likewise 206. Options minute and day probes remained
  authorization_or_entitlement_failure HTTP 403 403 (listed grant still dead).
  After the probe repair, the same credential returned reason=available
  available_date=2026-08-21; options minute still 403.
scope:
  - macro
  - collectors/massive_flatfiles.py
  - collectors/massive_stock_day.py
  - "WS:MASSIVE-STOCK-DAY-R2-COHERENCE"
  - "WS:MARKET-MEMORY-W2C"
confidence: verified
workstream: "WS:MASSIVE-STOCK-DAY-R2-COHERENCE"
evidence:
  - "2026-08-23 unlisted GET 403"
  - "2026-08-22 unlisted GET 404 NoSuchKey"
  - "2026-08-21 listed 322582 bytes LastModified 2026-08-22T05:36:24Z GET 206"
  - "2026-08-20 listed 321630 bytes LastModified 2026-08-21T05:23:09Z GET 206"
  - "2026-08-19 listed 323206 bytes LastModified 2026-08-20T04:54:34Z GET 206"
  - "run_status nightly: 2026-08-20 492.8s ok; 2026-08-21/22/23 0.8/0.5/0.9s no_entitled_date"
---

Unpublished stock-day keys 403. That is not the Options listed-grant regression.
