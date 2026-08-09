# CN TuShare full-A-share spine contract — 2026-08-08

Status: code-complete substrate; no live bulk backfill was run in this wave.
Authority: `context_only` — universe/data infrastructure, not a signal or promotion.
Collector: `collectors/china_tushare_spine.py`
Manifest schema: `contracts/cn_tushare_a_share_spine_manifest.v1.schema.json`

## Purpose

The existing raw A-share cache covers a curated subset, so it cannot support a
survivorship-honest full-market verdict. This collector builds the point-in-time
security and daily spine needed to measure all SH/SZ/BJ names, including current,
delisted, paused, not-yet-trading, ST and suspended securities.

It does not change any microstructure ranker and does not claim that collecting a
larger universe creates alpha. It makes the construction space measurable.

The event-authoritative plane is the joined pair of TuShare's unadjusted `daily`
quotes and vendor-published `stk_limit` bounds. A calculated limit is a validator,
never a substitute for the source bound.

## Official TuShare contracts pinned here

All URLs are official TuShare documentation, verified 2026-08-08.

| Endpoint | Official contract used | Published access/limit facts relevant to this collector |
|---|---|---|
| `stock_basic` | <https://tushare.pro/document/2?doc_id=25> | Current/listed/delisted/paused/approved status, exchange, market, list/delist dates; 2,000 points; 6,000 rows/call; 50 calls/minute. Collector splits by 3 exchanges × 4 statuses. |
| `bse_mapping` | <https://tushare.pro/document/2?doc_id=375> | BSE old code → new 920 code; 2,000 points; 1,000 rows/call and documented total under 300. |
| `trade_cal` | <https://tushare.pro/document/2?doc_id=26> | Calendar date, open flag and previous trade date; 2,000 points. Published exchange list includes SSE/SZSE but not BSE. |
| `namechange` | <https://tushare.pro/document/2?doc_id=100> | Effective name intervals, announcement date and reason. Used for effective-dated names and explicitly partial ST-name inference. |
| `daily` | <https://tushare.pro/document/2?doc_id=27> | Unadjusted OHLC, ex-rights `pre_close`, volume in lots and amount in thousand CNY; suspended periods have no row; 6,000 rows/call and 500 calls/minute at the base lane. Official guidance says whole-market history should loop by date. |
| `daily_basic` | <https://tushare.pro/document/2?doc_id=32> | Daily turnover, float/share and valuation fields; 6,000 rows/call; 2,000 points, with published no-total-limit status at 5,000 points. |
| `stk_limit` | <https://tushare.pro/document/2?doc_id=183> | Exact daily pre-close/up-limit/down-limit; includes A/B shares and funds; 5,800 rows/call; 2,000 points. A response at the cap is rejected as potentially truncated. |
| `suspend_d` | <https://tushare.pro/document/2?doc_id=214> | Date, `S`/`R` type and intraday timing. Empty successful days are checkpointed, while an unavailable call is not. |
| `stock_st` | <https://tushare.pro/document/2?doc_id=397> | Exact daily historical ST membership; 3,000 points; 1,000 rows/call; official history starts 2016-01-01. |

`pro_bar` is an SDK convenience path, not the direct REST endpoint used here.
The collector chooses nominal `daily` because price-limit reconstruction requires
nominal OHLC. It names the untested adjusted `pro_bar` construction in every ore
ledger.

## Official quote-tick and rounding contract

The current [SZSE Trading Rules (2026)](https://docs.static.szse.cn/www/lawrules/rule/trade/current/W020260424690713155663.pdf)
state in 3.3.11 that the A-share minimum quote increment is CNY 0.01. Rule 3.3.19
requires limit/range results to use 四舍五入 at that increment, then requires a
one-tick move when the rounded result differs from the reference by less than one
tick, and floors any bound below the minimum increment at one tick. The current
[SSE Trading Rules (2026)](https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/exchange/c/c_20260424_10816482.shtml)
are pinned alongside it; the rule page identifies the text as current and effective
2026-07-06.

`a_share_limit_price_bounds()` implements that arithmetic with `Decimal` and
`ROUND_HALF_UP`, returns both Decimal yuan and integer cents, and rejects an
off-tick previous close. Python `round` and NumPy `round` are forbidden for this
purpose because they use ties-to-even over binary floating-point values. The
canonical event rows still use vendor `stk_limit` upper/lower prices; the calculated
function is `validator_only_never_event_authority`, because effective-dated no-limit,
ST, board and historical rule states must not be guessed from a generic ratio.

## Frozen identity contract

- Repository ticker: `600519.SS`, `000001.SZ`, `920163.BJ`.
- Vendor-observed code remains in `source_ts_code` (`600519.SH`; an old BSE
  observation can remain `838163.BJ`).
- Stable venue-qualified ID: `CN-XSHG-600519`, `CN-XSHE-000001`,
  `CN-XBSE-920163`.
- BSE old codes are aliases, never separate companies. Historical rows emitted as
  `838163.BJ` join the canonical `920163.BJ` security while retaining the observed
  old source code.
- Board comes from exchange plus code family: SH 688/689 = STAR; SZ 300/301/302 =
  ChiNext; BJ = BSE; remaining A-share codes = main.
- Security lifecycle starts at `list_date`, except BSE eligibility cannot precede
  the exchange launch on 2021-11-15. `delist_date` is the inclusive effective end.

## Frozen session and volume contracts

The canonical clock is not a union of observed stock prints. Calendar collection
starts at the fixed 1991-01-01 anchor, queries SSE and SZSE by bounded year segment,
requires every calendar day, verifies `pretrade_date` adjacency, and fails unless
the two exchanges have exactly equal open-session sets. BSE inherits that attested
consensus from its launch date because TuShare's published `trade_cal` exchange list
does not advertise BSE.

Every endpoint row must land on that clock and carries
`market_session_position`. Cross-session consumers use the clock, not “previous row.”

`daily.vol` is stored as `volume_lots`; `positive_volume` is exactly
`volume_lots > 0`. Zero-volume source rows are retained rather than silently erased.
A consumer claiming a traded/listing session must filter `positive_volume`. Other
endpoints must join daily on `(trade_date, ticker)` before making that claim.

Every non-null A-share quote in `daily` and every source price in `stk_limit` must
sit exactly on the CNY 0.01 quote tick. Canonical price columns are stored as integer
cents (`open_cents`, `high_cents`, `low_cents`, `close_cents`, `pre_close_cents`,
`up_limit_cents`, `down_limit_cents`) rather than treated as binary floats. A
positive-volume row requires complete positive OHLC/pre-close quotes and coherent
OHLC ordering. A `stk_limit` row must publish both upper/lower bounds or neither,
and its upper/pre-close/lower ordering must be coherent.

`event_daily` is the materialized one-to-one join. It fails closed if any daily key
lacks `stk_limit`, if the two endpoints disagree on previous close, or if a quote is
off tick. Touch/seal flags compare integer-cent nominal highs/lows/closes directly
with the vendor's integer-cent source limits.

## ST provenance

- 2016-01-01 onward: `stock_st`, exact daily membership.
- Earlier history: `namechange` effective intervals plus conservative name-prefix
  inference (`ST`, `*ST`, `SST`, `S*ST`, `PT`). This is explicitly partial and is
  never relabeled as exact daily membership.
- `suspend_d` is separate from ST. Only a full-day suspension (`S` with no timing
  window) explains a missing daily row; an intraday halt does not.

The premium `st` event/reason endpoint (6,000-point lane) is not required by v1.
It can enrich reasons later, but it cannot repair the documented pre-2016 daily
membership gap by itself without a separate completeness proof.

## Resumability and store layout

```text
data/china_tushare_spine/
  reference/source_stock_basic/{SSE,SZSE,BSE}_{L,D,P,G}.parquet
  reference/source_bse_mapping.parquet
  reference/security_master.parquet
  reference/identity_aliases.parquet
  reference/trade_calendar/year=YYYY.parquet
  reference/market_sessions.parquet
  name_history/year=YYYY.parquet
  {daily,daily_basic,stk_limit,suspend_d,stock_st}/year=YYYY/month=MM/part.parquet
  event_daily/year=YYYY/month=MM/part.parquet
  coverage/daily_security_coverage.parquet
  collection_state.json
  completeness_manifest.json
```

Writes use a same-directory temporary file plus `os.replace`. Existing unreadable
Parquet or state is fatal; it is never overwritten as though absent. Monthly
daily partitions replace the entire successfully fetched source day—including an
empty suspension/ST tombstone—so omitted vendor rows cannot survive as ghosts.
Calendar/name reference partitions upsert their keys. All outputs sort
deterministically. The state file records successful empty event sessions, complete
row-bearing sessions and failed attempts separately. Unattempted units run before
retries so an old entitlement or coverage gap cannot starve newer dates.

The store is single-writer. Atomic replacement prevents torn files, but v1 does not
carry a cross-process/distributed lock; do not run two collectors against the same
store concurrently.

Default collection is capped at 50 calls per invocation. A zero/unlimited or
greater-than-100 call budget requires explicit `--allow-bulk`. `--dry-run` makes no
network calls and writes nothing. There is no CLI token argument; the existing
client reads only `TUSHARE_TOKEN` from the environment. Transport is HTTPS-only and
redirects are disabled. Request failures log only an exception class or sanitized
numeric code—never vendor response text, payload or token. Every file is scanned for
the configured token bytes before any receipt hash is computed; a match aborts the
manifest without printing the credential.

Example bounded accrual:

```bash
python -m collectors.china_tushare_spine \
  --start 20110101 \
  --end 20260807 \
  --max-requests 50
```

Re-run the same command until the manifest closes. Do not use `--allow-bulk` until
the account's live entitlements and provider limits have been observed under a
supervised pilot.

## Completeness verdict

`completeness_manifest.json` is complete only when:

1. every required reference source unit is complete or a proven successful empty;
2. the security master, alias map, name history and exact market clock have hashes;
3. every requested open session for each selected daily endpoint is complete (with
   `stock_st` explicitly not-applicable before its documented start);
4. no partition has duplicate keys;
5. every lifecycle-eligible security missing from `daily` is explained by a
   full-day suspension, and no unexpected security appears; and
6. the manifest carries file SHA-256, semantic SHA-256, row/date arithmetic, state
   hash, incomplete-unit samples, known gaps and an ore ledger; and
7. the canonical `event_daily` join of unadjusted nominal quotes to exact vendor
   limits closes without missing keys, off-tick prices or previous-close conflicts.

A code-0 empty event response is different from an error because the shared TuShare
client now supports `_return_empty=True` without changing its legacy default. A
failed/auth/entitlement response stays `None`, remains pending, and cannot close a
receipt.

## Remaining data/licensing gaps

- Exact daily ST membership before 2016 is unavailable from `stock_st`; name history
  is only an inferential partial bridge.
- Direct BSE calendar provenance is absent from the published `trade_cal` exchange
  list; v1 uses the explicitly labeled SSE=SZSE consensus.
- `stk_limit` includes non-A instruments and has a 5,800-row cap. v1 filters against
  the A-share master but fails closed if the raw response reaches that cap. If live
  responses hit it, a vendor-supported pagination/partition entitlement is needed;
  do not bless the truncated result.
- Same-key vendor corrections replace the local materialization. A bitemporal raw
  response/revision ledger is not built in v1.
- No minute, auction, first-seal, order-book, float pre-open, chip or fillability
  history is collected here.
- This wave did not exercise the credential, purchased add-ons, live throughput or a
  bulk backfill. Those remain operationally unverified until a supervised bounded
  pilot produces a real manifest.
- The account's rights to retain, redistribute or publish a bulk TuShare cache were
  not adjudicated here. Keep live backfill artifacts local/private until the operator
  confirms the applicable vendor terms; do not commit them by default.
- The current Wave-0 limit artifact is incompatible with exact legal-limit claims:
  `collectors/_stock_ohlc.py` explicitly documents that its so-called raw plane is
  still split-adjusted, while `engine/china_microstructure.py` reconstructs bounds
  with Python `round`. The existing 71,692-event artifact must remain quarantined
  from exact-limit strategy verdicts and be rebuilt from this TuShare substrate.

## Ore ledger

Constructed: lifecycle/status × exchange, BSE alias identity, exact calendar,
nominal daily/positive-volume state, daily-basic, exact price limits, suspensions,
daily ST, effective names, per-session universe reconciliation, integer-cent quote
invariants and an exact-source canonical event join.

Not tested: adjusted `pro_bar`, pre-2016 exact ST membership, direct BSE calendar,
minute/auction/order-book/seal-time/fillability histories, live bulk throughput and
add-on entitlement. A future null must name which of those constructions remained
outside the tested ore rather than treating “full A-share” as one exhausted space.
