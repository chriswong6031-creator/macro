---
key: W2C-M0C-V2-REST-SINGLE-TICKER-DAILY
question: >
  Which exact Massive/Polygon REST object should W2C v2 use for prospective
  same-session SPY evidence, when is it knowable and stable, does it preserve or
  version the v1 technical semantics, where do credentials terminate, which store
  owns the immutable source bytes, and how do v1 and v2 coexist?
answer: >
  Freeze W2C v2 on GET /v2/aggs/ticker/SPY/range/1/day/{D}/{D}?adjusted=false
  (api.polygon.io; api.massive.com is the same account). Session identity is the
  request date D, never bar.t. Keep the 04:30:00Z / 900s following-calendar-day
  window. Version the technical feature to raw_unadjusted_rth_daily_aggregate
  rather than claiming v1's unauthenticated full-market-day flat-file contract.
  Credentials terminate at a new credentialed source-owner unit. Immutable source
  evidence lives in a new source-family store, not the CPI ALFRED store and not a
  public SPY R2 publisher. v1 stays frozen on its own experience-v1 and
  technicals-v1 roots. Do not implement the writer in M0C.
rationale: >
  Live REST at 2026-08-20T11:03Z returned HTTP 200 bars for sessions 2026-08-17,
  08-18, and 08-19, and HTTP 200 with zero results for still-open 2026-08-20.
  Single-ticker and grouped unadjusted SPY OHLCV and n match each other. Against
  public R2 SPY.parquet, 12/12 recent sessions match OHLC and transactions
  exactly; parquet volume is the integer truncation of the REST float. Open-close
  for 2026-08-19 has close=769.06 equal to the REST daily close and
  afterHours=770.01 not equal, so the daily aggregate close is the official RTH
  close, not the last after-hours print. Snapshot day at 11:03Z is zeros with
  prevDay equal to 08-19 — snapshot is not a same-session source before the bell.
  Production close-pass host log for 2026-08-18 fired 20:00:06Z and published
  src=massive_grouped with 1721 massive fills, finalized=True, duration 349.5s.
  That is 8.5 hours before 04:30Z D+1, so this is not the flat-file 04:30Z race
  moved by a few minutes. Grouped is entitled but unbounded (~12k tickers);
  single-ticker is the bounded object the use case needs. The CPI source store
  and source.service are PrivateNetwork, keyless, CPIAUCSL-only. A public SPY
  R2 publisher remains HOLD. Full HTTP bodies change on every read because of
  request_id; source identity is the canonical digest of results[].
alternatives:
  - option: Grouped US daily /v2/aggs/grouped/locale/us/market/stocks/{D}?adjusted=false
    why_not: >
      SPY OHLCV/n match single-ticker, and 2026-08-18 close-pass already used it.
      It costs a whole-market download and quota for one ticker. Keep as a
      same-host cross-check, not the sealed source object.
  - option: Snapshot day.c
    why_not: >
      Convenient and previously measured as RTH on a completed weekend session
      (DSC:MASSIVE-SNAPSHOT-DAY-IS-RTH-CLOSE). At 2026-08-20T11:03Z, day is zeros
      and prevDay is yesterday. Not finalized. Session identity is a trap.
  - option: /v1/open-close/SPY/{D}
    why_not: >
      Useful semantic witness (exposes afterHours separately). Not the aggregate
      object v1's close-ratio feature compared against, and 08-20 pre-close
      returns only preMarket.
  - option: Keep v1 technical_profile and call REST the same feature
    why_not: >
      v1 contract source_session_scope is provider_daily_aggregate_eligible_trades_full_market_day
      with regular_session_close_authenticated=false. REST daily close equals
      open-close close, not afterHours. Version the authentication claim.
  - option: Thin SPY-only public R2 publisher
    why_not: CEO HOLD. Not the default. Credentials-in-publisher still needed.
  - option: Stuff REST bytes into the CPI Market Memory source store
    why_not: >
      SOURCE_ID, schema, and source.service are CPIAUCSL ALFRED, keyless,
      PrivateNetwork. Different family. Clone the publication protocol, do not
      overload the store.
  - option: Move v2 decision clock to 20:15Z same-session
    why_not: >
      04:30Z remains temporally comparable to v1 and avoids extra overnight
      information. 2026-08-18 grouped existed at 20:00Z, so 04:30Z D+1 is slack,
      not a race. Change the clock only if an evening probe shows REST arriving
      inside the 04:30 window the way the flat file does.
evidence:
  - >
    Live REST 2026-08-20T11:03:05Z MASSIVE_API_KEY present (not printed):
    /v2/aggs/ticker/SPY/range/1/day/{D}/{D}?adjusted=false HTTP 200 on
    api.polygon.io and api.massive.com. 08-17 c=772.67 n=526101;
    08-18 c=767.45 n=561254; 08-19 c=769.06 n=518426; 08-20 resultsCount=0.
  - >
    Grouped unadjusted 08-17/18/19 SPY OHLCV/n identical to single-ticker;
    bar.t differs (single = 00:00 ET, grouped = 16:00 ET).
  - >
    Public R2 SPY.parquet vs REST unadjusted, last 12 parquet sessions
    2026-08-03..08-18: 12/12 OHLC match, 12/12 transactions match, 12/12
    volume int(parquet)==int(REST float).
  - >
    Open-close 08-19: open 770.36 high 772.47 low 768.1 close 769.06
    afterHours 770.01 preMarket 767.89. Snapshot prevDay matches 08-19;
    day all zeros; updated 2026-08-20T11:03:21Z.
  - >
    Bar-only sha256 of 08-19 results[] stable
    7a950a36ab8336be39f44d28a13f8ea2c4ef41d806ed75b7997e76a30f35dc0c;
    full-body hashes differ per request_id.
  - >
    /Users/chriswong/Library/Logs/macro_closepass/launchd.out.log
    2026-08-18T20:00:06Z src=massive_grouped massive=1721 final=True.
    2026-08-19 Studio read 0 env keys so that night is not a REST clock.
  - >
    research/licenses/MASSIVE_ENTITLEMENT_RECORD.md operator-confirmed
    2026-08-09 enterprise aggregates/bars rights. Do not quote commercial terms.
  - >
    engine/neuralweb/market_memory_sources.py SOURCE_ID fred_alfred:CPIAUCSL;
    app/deploy/macro-market-memory-source.service PrivateNetwork keyless;
    technicals.service no EnvironmentFile, public HTTPS only;
    experience.service PrivateNetwork, InaccessiblePaths includes
    /etc/macro-api.env.
affects:
  - "WS:MARKET-MEMORY-W2C"
  - config/market_memory_spy_experience_registration.v1.json
  - engine/neuralweb/market_memory_technical_observation.py
  - engine/neuralweb/market_memory_sources.py
  - engine/close_pass/massive_close.py
confidence: high
reversibility: easy
decided_by: coo-fable
decided_at: 2026-08-20
review_by: 2026-08-21
---

# W2C v2 source freeze — single-ticker REST daily, versioned RTH feature

v1 remains the old-source control arm. This decision does not mutate v1,
does not backfill 2026-08-17/18/19, and does not authorize a runtime writer
in the same session as the qualification.
