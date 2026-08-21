---
key: MASSIVE-GROUPED-DAILY-AVAILABLE-AT-XNYS-CLOSE
claim: >
  Massive REST grouped daily (src=massive_grouped, close_finalized=True) filled
  1721 names for session 2026-08-18 during the Studio close-pass that fired at
  2026-08-18T20:00:06Z and finished in 349.5s, 8.5 hours before the v1/v2
  04:30Z D+1 window; the still-open session 2026-08-20 returned REST daily
  resultsCount=0 at 2026-08-20T11:03Z.
falsifier: >
  curl GET /v2/aggs/ticker/SPY/range/1/day/{D}/{D}?adjusted=false at 20:05Z and
  04:30Z D+1 on the next XNYS session: if the bar is absent at 20:30Z and first
  appears inside 04:24–04:54Z D+1, this is the same race as the flat file and
  the claim is false.
so_what: >
  Do not treat REST daily as another 04:30Z LastModified product. Keep the
  04:30Z W2C decision clock for v1/v2 comparability. The first implementation
  slice must still record first-availability at the next natural close because
  evening N is currently one session (2026-08-18); 2026-08-19 Studio close-pass
  had no API key.
kind: runtime
verified_at: 2026-08-20
verified_by: >
  cat "/Users/chriswong/Library/Logs/macro_closepass/launchd.out.log"
  session 2026-08-18 line "close-pass closes: {'store': 3, 'massive': 1721}
  basis=raw_rth_close final=True src=massive_grouped"; host receipt
  fired_at 2026-08-18T20:00:06Z. Live REST 08-20 resultsCount=0 at 11:03Z.
  engine/close_pass/massive_close.py is the src=massive_grouped producer.
scope:
  - macro
  - "WS:MARKET-MEMORY-W2C"
  - engine/close_pass/massive_close.py
  - scripts/close_pass_host_runner.py
confidence: verified
---

# REST grouped daily existed at the 2026-08-18 bell

One production evening, not a marketing 15-minute claim. Widen N at the next close.
