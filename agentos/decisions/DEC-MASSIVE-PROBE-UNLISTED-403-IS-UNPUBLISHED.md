---
key: MASSIVE-PROBE-UNLISTED-403-IS-UNPUBLISHED
question: >
  When probe_available() gets HTTP 403 on a Massive flat-file key, should it
  abort the lookback as authorization_or_entitlement_failure, or distinguish
  a listed object (grant failure) from an unlisted key (unpublished)?
answer: >
  Distinguish. Listed + 403 is authorization_or_entitlement_failure and still
  aborts immediately so an older readable day cannot launder a dead grant
  (Options minute/day). Unlisted + 403 is unpublished — continue the lookback.
  404 remains unpublished. Do not flatten the resulting AvailabilityProbe.reason
  into massive_stock_day's no_entitled_date; put the sanitized reason (and
  detail) on the blocked result so run_status can tell authorization, absence,
  transport, and configuration apart.
rationale: >
  Production 2026-08-23T02:11:50Z: calendar-today stock_day 403ed with an empty
  listing while 2026-08-21 was HTTP 206. Three nightly collects (~00:30Z) start
  by probing "today", which is not yet LastModified (D+1 ~04:30–05:36Z), so
  abort-on-first-403 froze the store at 2026-08-18. The Chairman source ruling
  keeps Massive canonical for stocks; this is discovery logic, not a source swap.
alternatives:
  - option: Abort on any 403 (pre-repair)
    why_not: >
      Treats unpublished-today as a product-wide grant failure and reports
      no_entitled_date while weekday objects are readable
  - option: Skip weekends / non-trading days before the first GET
    why_not: >
      The 00:30Z weekday nightly also 403s unpublished session D (the Friday
      2026-08-21 00:54Z failure). Trading-day filters do not fix that
  - option: Treat all stock_day 403s as unpublished and keep walking
    why_not: >
      Would hide a true listed-grant regression behind an older readable day
  - option: Substitute ThetaData or REST for the frozen stock plane
    why_not: >
      DEC:AD-OPTIONS-CANONICAL-SOURCE-THETADATA is options-only; Sol forbade
      silent stock-source substitution
evidence:
  - "DSC:MASSIVE-STOCK-DAY-UNPUBLISHED-TODAY-RETURNS-403"
  - "DSC:MASSIVE-OPTIONS-FLATFILE-ENTITLEMENT-REGRESSION"
  - "DEC:AD-OPTIONS-CANONICAL-SOURCE-THETADATA"
  - "collectors/massive_flatfiles.py probe_available listed-vs-unlisted 403 split"
affects:
  - "WS:MASSIVE-STOCK-DAY-R2-COHERENCE"
  - "WS:MARKET-MEMORY-W2C"
  - collectors/massive_flatfiles.py
  - collectors/massive_stock_day.py
confidence: high
reversibility: easy
decided_by: coo-fable
decided_at: 2026-08-23
---

Listed 403 stays a grant failure. Unlisted 403 is "not yet published".
