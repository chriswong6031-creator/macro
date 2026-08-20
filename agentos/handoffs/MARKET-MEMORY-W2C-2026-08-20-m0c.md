---
workstream: "WS:MARKET-MEMORY-W2C"
session: claude/market-memory-m0c-source-qual-20260820
model: local
ended_because: complete
mission: >
  Qualify Massive/Polygon REST as the W2C v2 successor source, freeze source
  and coexistence architecture, and stop without implementing the production writer.
state_before: >
  M0A proven. M0B class A on origin/main 98ce1c4ffb1b. v1 frozen evidence arm.
  Sol authorized REST qualification under a new registration. Public SPY R2
  publisher HOLD. Population 3 expected / 3 recorded / 3 abstained / 0 admitted.
changed:
  - path: agentos/handoffs/MARKET-MEMORY-W2C-2026-08-20-m0c.md
    what: Qualification packet with endpoint matrix, finality ledger, lineage, and coexistence freeze.
  - path: agentos/decisions/DEC-W2C-M0C-V2-REST-SINGLE-TICKER-DAILY.md
    what: Froze v2 on single-ticker unadjusted daily REST, 04:30Z window, versioned RTH feature, new source store, no runtime writer.
  - path: agentos/discoveries/DSC-SPY-REST-UNADJUSTED-DAILY-MATCHES-FLATFILE-OHLC.md
    what: 12/12 OHLC and n match vs R2 parquet; REST close is not afterHours.
  - path: agentos/discoveries/DSC-MASSIVE-GROUPED-DAILY-AVAILABLE-AT-XNYS-CLOSE.md
    what: 2026-08-18 close-pass src=massive_grouped at 20:00Z.
  - path: agentos/workstreams/WS-MARKET-MEMORY-W2C.md
    what: Closed M0B needs_ceo, added M0C done and M0D implementation slice waiting on Sol freeze.
  - path: agentos/handoffs/MARKET-MEMORY-W2C-2026-08-20-v2-slice.md
    what: Bounded first vertical-slice implementation handoff. Not executed this session.
  - path: agentos/workstreams/WS-MASSIVE-STOCK-DAY-R2-COHERENCE.md
    what: Separate D-class owning lane. Not repaired this session.
  - path: agentos/handoffs/MASSIVE-STOCK-DAY-R2-COHERENCE-2026-08-20.md
    what: Torn-generation continuation packet for publish_r2 / massive_stock_day.
verified:
  - claim: >
      Capture UTC 2026-08-20T11:03:05Z. REST single-ticker unadjusted SPY daily
      HTTP 200 on api.polygon.io and api.massive.com for 08-17/18/19 with bars,
      and HTTP 200 resultsCount=0 for still-open 08-20.
    command: >
      python3 urllib GET /v2/aggs/ticker/SPY/range/1/day/{D}/{D}?adjusted=false
      using MASSIVE_API_KEY from Macro Dashboard .env (value not printed)
    result: >
      08-17 o=776.18 h=776.775 l=772.51 c=772.67 v=34356577.390915 n=526101
      t=1786939200000 (00:00 ET); 08-18 c=767.45 n=561254; 08-19 c=769.06 n=518426;
      08-20 empty. polygon.io and massive.com bars identical, full-body sha256 differ.
  - claim: >
      Grouped unadjusted SPY matches single-ticker OHLCV/n; bar.t is 16:00 ET.
    command: >
      GET /v2/aggs/grouped/locale/us/market/stocks/{D}?adjusted=false extract T=SPY
    result: >
      08-17/18/19 spy rows identical OHLCV/n; t=1786996800000 for 08-17 (16:00 ET);
      08-20 resultsCount=0 bytes=112.
  - claim: >
      Open-close 08-19 close equals REST daily close and not afterHours.
      Snapshot at 11:03Z has day zeros and prevDay=08-19.
    command: >
      GET /v1/open-close/SPY/2026-08-19?adjusted=false;
      GET /v2/snapshot/locale/us/markets/stocks/tickers?tickers=SPY
    result: >
      open-close close=769.06 afterHours=770.01 preMarket=767.89;
      snapshot day all zeros prevDay c=769.06 updated 2026-08-20T11:03:21Z.
  - claim: >
      12/12 parquet sessions 2026-08-03..08-18 match REST OHLC and n;
      volume parquet int equals int(REST float).
    command: >
      curl public R2 SPY.parquet; compare to REST unadjusted daily
    result: >
      n=12 ohlc_match=12 n_match=12 vol_trunc_match=12;
      parquet latest_date=2026-08-18 Last-Modified Wed, 19 Aug 2026 22:53:53 GMT.
  - claim: >
      08-19 results[] digest is stable across rereads; full HTTP body is not.
    command: >
      three GET 08-19 single-ticker ~8s apart; sha256(results JSON) vs full body
    result: >
      bar-only sha256 7a950a36ab8336be39f44d28a13f8ea2c4ef41d806ed75b7997e76a30f35dc0c
      unchanged; full-body hashes differ with request_id.
  - claim: >
      Studio close-pass 2026-08-18 used massive_grouped at the bell.
    command: >
      read /Users/chriswong/Library/Logs/macro_closepass/launchd.out.log
      and Application Support/macro-closepass/runs/2026-08-18.json
    result: >
      fired_at 2026-08-18T20:00:06Z duration 349.5s src=massive_grouped
      massive=1721 store=3 final=True. 08-19 Studio env keys=0 so not a REST clock.
  - claim: >
      Experience writer is PrivateNetwork and cannot see API keys.
      Technicals unit has no EnvironmentFile. CPI source unit is keyless PrivateNetwork.
    command: >
      read app/deploy/macro-market-memory-experience.service
      macro-market-memory-technicals.service macro-market-memory-source.service
    result: >
      experience PrivateNetwork=true InaccessiblePaths includes /etc/macro-api.env;
      technicals ExecStart capture_market_memory_technicals store-root technicals-v1;
      source ingest_market_memory_sources store-root .../state/sources PrivateNetwork.
unverified:
  - claim: >
      REST single-ticker SPY daily is present by 20:05Z on every session, not only
      that grouped filled 1721 names on 2026-08-18.
    what_would_verify: >
      Poll single-ticker adjusted=false at 20:05Z and 20:30Z on the next XNYS
      close (2026-08-20 20:00Z). Do not replay a closed window.
  - claim: >
      The daily bar never revises between 20:30Z and 04:30Z D+1.
    what_would_verify: >
      Hash results[] at 20:30Z, 00:00Z, and 04:29Z D+1 on that next session.
unresolved:
  - Sol must ratify DEC:W2C-M0C-V2-REST-SINGLE-TICKER-DAILY before a runtime PR.
  - Evening first-availability N is one session until the next natural close probe.
  - D-class torn publication is out of this PR; see WS:MASSIVE-STOCK-DAY-R2-COHERENCE.
next_actions:
  - Sol ratifies or amends the v2 registration candidate in this packet.
  - A later session executes agentos/handoffs/MARKET-MEMORY-W2C-2026-08-20-v2-slice.md.
  - Do not mutate v1. Do not backfill. Do not thin-publish SPY. Do not retune v1 timers.
do_not_redo:
  - Do not treat v1 04:30–04:45Z abstentions as missed or repair them with v2 evidence.
  - Do not call REST the same unauthenticated full-market-day feature without versioning.
  - Do not use snapshot day.c as the v2 source.
  - Do not digest the full REST HTTP body including request_id as source identity.
  - Do not host REST bytes in the CPI ALFRED source store.
  - Do not share technicals-v1 or experience-v1 roots with v2.
  - Do not add a second trusted writer; v2 reads trusted-v1.
danger_areas:
  - accrue_market_memory_spy_experience.py closure list and
    _expected_registration_spec() are v1-hardcoded. A v2 JSON dropped on the
    v1 path will fail closed — parameterize, do not overwrite.
  - MAX_OWNER_GENERATION_CAPTURES=256 is per store root. Sharing technicals-v1
    overflows the v1 cap.
  - bar.t on single-ticker is midnight ET; never derive session date from it.
  - Overlapping publish_r2 still tears the public store; do not weaken the consumer.
---

# M0C — REST qualification and v2 architecture freeze

## Endpoint matrix (2026-08-20T11:03Z)

| Object | Params | 08-17/18/19 | 08-20 (pre-close) | Role |
|---|---|---|---|---|
| `/v2/aggs/ticker/SPY/range/1/day/{D}/{D}` | adjusted=false | 200, 1 bar | 200, 0 results | **v2 source** |
| same on api.massive.com | adjusted=false | identical bars | empty | same account |
| `/v2/aggs/grouped/locale/us/market/stocks/{D}` | adjusted=false | 200, SPY matches single | 0 results | cross-check only |
| `/v1/open-close/SPY/{D}` | adjusted=false | 200, close=REST close, afterHours differs | preMarket only | semantic witness |
| snapshot `tickers=SPY` | — | prevDay=08-19 | day zeros | rejected |

Entitlement: MASSIVE_API_KEY 200 on both hosts for stock daily aggregates. Options snapshot remains a different 403 problem and is out of scope. License record: `research/licenses/MASSIVE_ENTITLEMENT_RECORD.md` (enterprise aggregates; do not quote terms).

## Availability / finality

- Knowable before close: 08-20 REST daily empty at 11:03Z. Session identity holds.
- Knowable at close: 08-18 Studio close-pass `src=massive_grouped` at 20:00:06Z, 1721 names, finalized. ~8.5h before 04:30Z 08-19.
- Knowable by next morning: 08-19 REST bar present at 11:03Z 08-20.
- Stable at T+1 morning: 08-19 `results[]` digest unchanged across three reads. Full body is not a digest key.
- After-hours: daily close did not absorb 08-19 afterHours 770.01.
- 15-minute delayed marketing was not used as a clock.

Keep **04:30:00Z / 900s**. It is slack given 20:00Z availability, and it keeps v1 and v2 comparable.

## Semantic / parity

v1 contract: unauthenticated full-market-day flat-file aggregate.
REST+open-close: official RTH close.
Bytes: 12/12 OHLC and n match parquet; volume encoding differs (float vs int64).

**Version the technical feature.** Do not silently keep `market_memory.private.spy_raw_technical_actual_output.v1`.

Proposed v2 names:

- technical_profile: `market_memory.private.spy_raw_rth_daily_aggregate.v2`
- price_basis: `raw_unadjusted_rth_daily_aggregate`
- regular_session_close_authenticated: true (request date D + close equals open-close `close`, not `afterHours`)
- transform_version: new; do not reuse `market_memory.spy_raw_close_ratio_20_sessions.v1` without pinning the new source object

## Lineage (today vs v2)

Today: Massive S3 day_aggs → nightly massive_stock_day → publish_r2 → public R2 → keyless technicals-v1 → experience-v1.

v2: credentialed source owner → immutable spy-rest source store → keyless technicals-v2 projector → experience-v2. Key never enters experience or public clients. No public SPY R2 publisher.

CPI `state/sources` stays CPI. Clone object→receipt→generation→HEAD; new SOURCE_ID.

## Secret / network boundary

| Unit | Network | Secret | Writes |
|---|---|---|---|
| NEW spy-rest-source | outbound HTTPS | MASSIVE_API_KEY / POLYGON_API_KEY in a dedicated EnvironmentFile | state/sources-spy-rest-v1 |
| NEW technicals-v2 | optional none if it only reads local source store | none | state/technicals-v2 |
| existing technicals-v1 | public HTTPS R2 only | none | technicals-v1 |
| existing experience-v1 | PrivateNetwork | none | experience-v1 |
| NEW experience-v2 | PrivateNetwork | none | experience-v2 |
| trusted canary | unchanged | none | trusted-v1, shared read |

Reuse `engine/close_pass/massive_close.py` KEY_ENVS and DEFAULT_BASE_URL. Do not invent a second general vendor client.

## v1 / v2 coexistence

- v1 registration bytes and 04:30 window stay immutable.
- v2 is a new schema `market_memory.spy_experience_registration.v2` with a new content-addressed `mmspyexpreg_<sha256(spec)>`.
- Disjoint roots: experience-v2, technicals-v2, sources-spy-rest-v1. Shared trusted-v1 **reads only** (trusted store is not registration-scoped; a second trusted writer would consume the 256 cap).
- Opportunity IDs include registration_id in the content address already used by v1; different spec ⇒ different IDs. v2 must not write into experience-v1.
- One framework: parameterize `accrue_market_memory_spy_experience.py` with an explicit registration path and a v2 tracked-closure list. Do not overwrite `_expected_registration_spec()`.
- Two systemd oneshots at 04:30, or one oneshot that iterates two registrations with two roots. Prefer two units so a v2 failure cannot skip v1.
- v2 evidence cannot repair a v1 abstention. Separate population receipts.
- Activation: first XNYS session **on or after** the v2 writer is live. Do not activate on 2026-08-17.

Capacity: v2 technical max 256 on technicals-v2 with its own 126 expected + 32 revision reserve. v1 cap arithmetic unchanged.

## Statistical / product value

v1 vs v2 is a **source/availability control**, not a prediction benchmark:

- evidence-availability rate (v1 ~0 admitted so far; v2 expected high if 20:00Z REST holds)
- lawful abstention rate
- source latency (flat-file LastModified vs REST first 200-with-bar)
- technical-session coverage
- correction burden (results[] revisions after seal)
- usable experience denominator

## Registration candidate semantics (JSON not written)

schema `market_memory.spy_experience_registration.v2`

Keep from v1: subject/SPY identity, calendar_id, same_session_required=true, fallback_allowed=false, window 04:30:00Z / 900s, following_calendar_days=1, authority display/context-only, prospective_only, population one_row_per_expected_session.

Change: profile accrual.v2; technical_profile spy_raw_rth_daily_aggregate.v2; source object and host as above; activation_session = first live session after writer merge; sunset/census recomputed from that activation for a new 126-session pilot (do not share v1's 2027-02-16 sunset unless Sol wants a shorter overlapping control); capacity_preflight technical_future on technicals-v2 only; trusted_future_captures additional = 0.

## Capability ledger

| Capability | v1 | v2 freeze |
|---|---|---|
| Same-session technical at 04:30Z | unachievable from flat file | expected if 20:00Z REST holds; evening N=1 |
| Credential-free technicals | yes (public R2) | yes (reads private source store) |
| Immutable source bytes | vendor S3 / R2 mutable | required in sources-spy-rest-v1 |
| RTH close authenticated | no | yes, versioned |
| Public SPY publisher | n/a | HOLD |
| Runtime writer this session | n/a | **not built** |

## Architecture freeze / no-rebuild

No v1 mutation, no v1 timer/source change, no thin R2 publisher, no generic new market-data platform, no Prophet/Cortex/Neural Web authority, no analogue ranking, no recovery of the first three v1 abstentions.
