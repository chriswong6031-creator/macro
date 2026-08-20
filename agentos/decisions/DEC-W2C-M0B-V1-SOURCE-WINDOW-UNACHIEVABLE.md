---
key: W2C-M0B-V1-SOURCE-WINDOW-UNACHIEVABLE
question: >
  Under the frozen v1 registration (same_session_required=true, fallback_allowed=false,
  following-calendar-day window 04:30:00Z for 900 seconds, technical source = public R2
  massive_stock_day derived from Massive us_stocks_sip/day_aggs_v1), is same-session
  W2C admission physically achievable, and which single M0B causal class is the
  earliest current blocker?
answer: >
  Classify M0B as A — SOURCE_CLOCK_IMPOSSIBLE for the frozen v1 source/window pair.
  Do not change timers, validators, source timestamps, or registration. Do not create
  a substitute source or a second R2 publisher. No runtime PR. Return the clock
  ledger to Sol. Classes B, C, and D occurred historically and remain named; they are
  not the first cause of v1 impossibility.
rationale: >
  Authoritative S3 HEAD LastModified for us_stocks_sip/day_aggs_v1/YYYY/MM/YYYY-MM-DD.csv.gz
  on 24 weekday sessions 2026-07-17 through 2026-08-19 clusters on the FOLLOWING
  calendar day at 03:44–05:37 UTC, almost entirely in the 04:24–04:54 band that is
  the W2C window itself. 7/24 (29%) land after 04:45 UTC (object absent for the
  entire admission window). 8/24 land during 04:30–04:45. 9/24 land before 04:30,
  typically with 16–20 minutes of slack, rarely 48–60. The house-doc "~11:00 ET
  prior-day file ready" figure is false for this product (11:00 ET = 15:00 UTC;
  every measured stocks day_aggs LastModified was hours earlier). The 22:30 UTC
  nightly collect therefore always runs ~6 hours BEFORE the same-session object
  exists, which is why public R2 at 2026-08-20T09:45:14Z still carried
  store.latest_date=2026-08-18. A B-class move of that collector into the 15-minute
  window cannot manufacture time: restore of the canonical 617 MB store already
  takes 4–5 minutes, the incremental writes ~21k per-ticker parquets, publish takes
  35s–3min, and technicals samples at *:53 so the last pre-window capture is 03:53
  (file not yet on S3) and the next is 04:53 (window closed). Session 2026-08-19's
  object itself appeared at 04:54:34Z — nine minutes after deadline — so even an
  instantaneous publisher would have abstained. Chasing B/C against v1 would
  consume more of the frozen 126-session denominator without a lawful admit.
alternatives:
  - option: B — move massive_stock_day collect/publish into the 04:30 window
    why_not: >
      Modal for the 71% of sessions whose S3 object exists by 04:45, but it races a
      vendor clock that IS the window. Restore 4–5 min plus 21k upserts plus publish
      does not fit the remaining minutes; GHA daily 32310821528 has been queued since
      2026-08-19T22:52:54Z. Independently, technicals still would not sample until
      04:53. Not the first cause, and not independently sufficient for admission.
  - option: C — change macro-market-memory-technicals from hourly :53 to in-window
    why_not: >
      Public R2 does not carry the same-session SPY observation before 04:45. A faster
      consumer of a prior-session parquet still produces technical_session_absent.
      Necessary later if Sol changes the source/window; not the current first cause.
  - option: D — repair ticker-count / publish-last torn generations
    why_not: >
      Real and distinct. 2026-08-19 00:54–04:54Z failed closed on 'store ticker count
      does not match the publish manifest' (n_tickers 21340 then 21351/21352 during
      the 08-17→08-18 advance). 2026-08-19 15:04–22:53Z failed on 'publish-last
      manifest predates the SPY parquet' until 22:57Z, when technicals first captured
      session=2026-08-18. That tear delayed coherent 08-18 capture until AFTER the
      08-18 window (04:30Z 08-19) and did not delay 08-19 data past its own deadline
      — 08-19 was not on S3 until 04:54Z 08-20. Do not weaken the consumer.
  - option: Thin SPY-only R2 current publication, or REST grouped-daily as a new source
    why_not: >
      A second publisher or a new market-data source. Forbidden without a Sol
      architecture ruling. Whole-STORE day gaps are illegitimate in
      collectors/massive_stock_day.py. Registration v1 is frozen.
evidence:
  - >
    HEAD us_stocks_sip/day_aggs_v1 via files.massive.com at 2026-08-20T09:48:17Z and
    09:49:16Z (boto3 head_object, credentials present not printed): 2026-08-17
    LastModified=2026-08-18T04:28:45Z; 2026-08-18=2026-08-19T04:28:10Z;
    2026-08-19=2026-08-20T04:54:34Z; 2026-08-20 HTTP 403 (session not yet closed).
    24-session table in agentos/handoffs/MARKET-MEMORY-W2C-2026-08-20-m0b.md.
  - >
    curl -sI https://pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev/massive_stock_day/_manifest.json
    at 2026-08-20T09:45:14Z: Last-Modified Thu, 20 Aug 2026 01:32:46 GMT;
    store.latest_date=2026-08-18; n_tickers=21352; count=21353 (coherent now).
    SPY.parquet Last-Modified Wed, 19 Aug 2026 22:53:53 GMT.
  - >
    git log data/massive_stock_day/_manifest.json: 08-17 first written
    updated_at=2026-08-19T03:44:22Z (commit 63968799); 08-18 at 2026-08-19T21:20:22Z
    then 2026-08-20T00:19:42Z; 08-19 absent from committed processed_days.
  - >
    gh run 32207351396 collect steps: restore massive_stock_day 02:07:35–02:12:59Z
    (~5 min); publish 05:11:16–05:11:51Z (35s). Run 32077948964 restore ~4 min,
    publish 04:04:02–04:07:23Z (~3 min). EDT nightly 32310821528 still queued at
    09:39Z 2026-08-20.
  - >
    journalctl technicals: 2026-08-19 00:54–04:54Z ticker-count mismatch (covers the
    08-18 W2C window); 15:04–22:53Z publish-last predate; 22:57Z first success
    session=2026-08-18; still session=2026-08-18 at 03:54Z and 09:41Z 2026-08-20.
    Timer OnCalendar=*-*-* *:53:00 UTC.
  - >
    Registration frozen:
    config/market_memory_spy_experience_registration.v1.json
    mmspyexpreg_e00ffc1d34b57ce3b011955a8662dae8f7e069b7f5f07417c428a5815c6dd6e3.
affects:
  - "WS:MARKET-MEMORY-W2C"
  - config/market_memory_spy_experience_registration.v1.json
  - collectors/massive_stock_day.py
  - collectors/massive_flatfiles.py
  - engine/neuralweb/market_memory_technical_observation.py
  - app/deploy/macro-market-memory-technicals.timer
confidence: high
reversibility: easy
decided_by: coo-fable
decided_at: 2026-08-20
review_by: 2026-08-27
---

# M0B — v1 same-session admission is not physically achievable

The fork was whether Massive's daily SPY source object is available by 04:45 UTC
on the following calendar day. Authoritative `head_object` LastModified, not the
22:30 UTC collector glance, answers it.

The object arrives in the same fifteen minutes the opportunity is required to
seal, and 29% of the last 24 sessions miss that deadline entirely. That is class
A for frozen v1. Moving the nightly, tightening the technicals timer, or
accepting a torn manifest cannot put an absent S3 object into the window, and
cannot finish a 21k-ticker canonical publish in the minutes that remain when the
object is merely late-inside-window.

Sol owns the next registration or source decision. This session does not spend
another of the 126 frozen opportunities on a runtime repair of v1.
