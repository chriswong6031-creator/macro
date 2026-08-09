# TuShare purchased add-ons — provenance-first collector foundation

**As of:** 2026-08-09 Asia/Shanghai

**Authority:** `context_display_only`

**Execution state:** foundation and synthetic verification only; no live entitlement
probe and no bulk backfill were run.

## What this foundation admits

The runnable surface contains exactly three operator-reported purchases:

| Endpoint | Official contract captured | Bounded pilot | Initial entitlement state |
|---|---|---|---|
| `stk_mins` | [股票历史分钟行情, doc 370](https://tushare.pro/document/2?doc_id=370) | one ticker, one exchange session, one of `1min/5min/15min/30min/60min` | reported purchased; unverified until valid rows return |
| `stk_premarket` | [股本情况（盘前）, doc 329](https://tushare.pro/document/2?doc_id=329) | one exchange session, optionally one ticker | reported purchased; unverified until valid rows return |
| `stk_auction` | [当日集合竞价, doc 369](https://tushare.pro/document/2?doc_id=369) | current Shanghai session only, optionally one ticker, during 09:26–09:29 | reported purchased; unverified until valid rows return |

`stk_auction_o` and `stk_auction_c` are **blocked pending written entitlement
confirmation**. Their existence in documentation is not evidence that this account
bought their separate permissions. They are not CLI choices and the workflow cannot
call them.

The endpoint contracts pin the documented field lists, row cap (8,000), official
document URL, capture date, units, normalized Arrow schema, and a contract digest.
A successful receipt means only that valid non-empty rows were observed for that
specific request. It does not attest any other endpoint or future access.

## Safe execution envelope

`python -m scripts.collect_tushare_addons ...` plans by default. Planning performs no
network call and no write. `--execute` is required to authorize one structurally
bounded request. There is no start/end range, ticker-list, pagination, or backfill
interface.

Every executed request has a hard maximum of three HTTPS vendor calls:

1. exact-date `trade_cal` observation for SSE;
2. exact-date `trade_cal` observation for SZSE; and
3. one requested add-on endpoint call.

Both exchanges must return one unique row, agree, and mark the requested date open.
The returned add-on rows must then stay inside the exact requested session and ticker
scope. No output directory is mutated until the clock, calendar, response columns,
row cap, types, domains, uniqueness, and exact-session checks all pass.

This collector performs no price join. Its receipt nevertheless freezes the downstream
basis rule exposed by the cross-lane audit: nominal historical price/limit joins must
come from the TuShare `daily` / `stk_limit` effective-date plane keyed from the full-A
spine. `china_stocks_raw`/Yahoo is split-adjusted and is explicitly forbidden as that
nominal historical truth. The direct `stk_premarket.up_limit` and `down_limit` values
are preserved in this store rather than re-derived from adjusted closes.

Additional collection clocks fail closed:

- `stk_auction`: requested date must equal the current Asia/Shanghai date and the
  collector clock must be `09:26 <= time < 09:30`;
- current-session `stk_mins`: held until 21:00 Asia/Shanghai; and
- current-session `stk_premarket`: held until 16:30 Asia/Shanghai so the first
  immutable pilot does not pretend a still-changing premarket response is final.

The manual workflow requires one ticker even for the daily endpoints, an explicit
boolean confirmation, and the `main` ref. It has no schedule or write permission and
uploads only a 30-day review artifact. This is an entitlement/schema witness, not a
production collector or canonical publication lane.

## Immutable storage and receipts

Each accepted request owns one directory:

```text
<root>/<endpoint>/
  by_frequency=<frequency>/
    by_trade_date=YYYY-MM-DD/
      by_scope=ticker-<ticker>|all-stocks/
        part.parquet
        receipt.json
```

The `by_` prefix prevents Hive partition discovery from colliding with the same
typed `frequency` and `trade_date` columns inside the Parquet file. A partition
bundle may contain exactly those two files. An identical rerun is a byte-preserving
no-op. Revised source rows, a changed exact-session observation, a partial bundle,
unexpected file, altered schema, altered request identity, or hash mismatch raises a
keep-first integrity contradiction and does not overwrite the first evidence.

The receipt binds:

- official endpoint contract and SHA-256;
- operator-reported entitlement plus the observed-valid-row fact;
- blocked/unconfirmed endpoint states;
- the TuShare-only nominal-price join basis and explicit Yahoo adjusted-plane ban;
- sanitized vendor parameters with no token;
- collection clocks in UTC and Asia/Shanghai;
- exact SSE/SZSE `trade_cal` observations and digest;
- normalized schema and digest;
- canonical pre-normalization vendor field/value observations and digest;
- canonical normalized rows and digest;
- exact Parquet bytes and digest;
- Python, pandas, PyArrow, collector-source, shared-normalizer-source, dependency-lock,
  and GitHub run context; and
- explicit nonclaims: no signal, fillability, execution, complete-history, Level-2,
  order-book, or queue-position authority.

The paid token is read from `TUSHARE_TOKEN` only. This lane uses an isolated HTTPS
transport, never includes the token in a URL, and never logs or persists vendor error
text, request payloads, token bytes, or token hashes. The workflow scans the entire
review artifact for the exact token bytes before upload and fails loudly if any are
found.

## Operator commands

Dry plans (safe locally without a token):

```bash
python -m scripts.collect_tushare_addons stk_mins \
  --trade-date 2026-08-07 --ticker 600519.SS --frequency 1min

python -m scripts.collect_tushare_addons stk_premarket \
  --trade-date 2026-08-07 --ticker 000001.SZ
```

The first real probe should be dispatched through
`.github/workflows/tushare-addons-pilot.yml` from `main`, one ticker at a time. Do not
use a local `--execute` run as a substitute for the review artifact and main-ref
receipt.

## Deliberate limitations and next gates

1. **No live entitlement proof yet.** No paid endpoint was called while building this
   foundation. A generic `unavailable_empty_or_unentitled` hold deliberately avoids
   persisting vendor error text; one valid review artifact is needed per endpoint.
2. **No raw microstructure.** `stk_auction` is a documented same-day auction snapshot,
   not order-wall growth, cancellation, replenishment, queue position, tick-by-tick
   trades, or Level-2 depth. It cannot support those claims.
3. **No historical completeness claim.** A non-empty ticker-day minute response may be
   shorter because of suspension or vendor coverage. This foundation authenticates
   exact returned rows; it does not fabricate missing bars or declare a full day.
4. **No bulk data plane.** Historical minute expansion across thousands of tickers and
   years needs a separately reviewed object-store layout, license/redistribution
   ruling, request/rate budget, resumable manifest, coverage ledger, corporate-action
   basis contract, and sampled reconciliation. None is authorized here.
5. **Whole-market pilots remain guarded.** The library can accept a single-session
   whole-market `stk_premarket` or `stk_auction` response but rejects fewer than 1,000
   rows as suspiciously thin. The workflow is narrower and requires one ticker.
6. **Ex-ante premarket capture is not solved.** The conservative current-day close
   gate makes an immutable schema pilot honest, but it is not the eventual before-open
   capture needed for a leak-free signal. Promotion requires a scheduled, witnessed
   premarket clock and a vendor-revision policy.
7. **Review artifacts are not canonical publication.** No data is committed, merged,
   scored, rendered, or granted strategy authority by this workflow. Production
   scheduling follows only after entitlement, schema, clock, license, and storage
   receipts are reviewed.
8. **The auction witness has a narrow operational clock.** A queued manual workflow
   can miss the four-minute 09:26–09:29 window even when dispatched correctly. After
   the first supervised proof, a dedicated on-time local runner is more credible than
   treating generic hosted scheduling latency as capture evidence.
