# TuShare purchased add-ons — provenance-first collector foundation

**As of:** 2026-08-09 Asia/Shanghai

**Authority:** `context_display_only`

**Execution state:** foundation and synthetic verification only; no live access probe
and no bulk backfill were run. Live execution is enabled now.

## What this foundation admits

The runnable surface contains exactly three operator-reported purchases:

| Endpoint | Official contract captured | Bounded pilot | Initial access context |
|---|---|---|---|
| `stk_mins` | [股票历史分钟行情, doc 370](https://tushare.pro/document/2?doc_id=370) | one ticker, one exchange session, one of `1min/5min/15min/30min/60min` | operator-reported purchase; not vendor-attested and not a license grant |
| `stk_premarket` | [股本情况（盘前）, doc 329](https://tushare.pro/document/2?doc_id=329) | one SSE/SZSE ticker and one exchange session | operator-reported purchase; not vendor-attested and not a license grant |
| `stk_auction` | [当日集合竞价, doc 369](https://tushare.pro/document/2?doc_id=369) | one SSE/SZSE ticker in the current Shanghai session, during 09:26–09:29 | operator-reported purchase; not vendor-attested and not a license grant |

`stk_auction_o` and `stk_auction_c` are **blocked pending written entitlement
confirmation**. Their existence in documentation is not evidence that this account
bought their separate permissions. They are not CLI choices and the workflow cannot
call them.

The endpoint contracts pin the documented field lists, row cap (8,000), official
document URL, capture date, units, normalized Arrow schema, and a contract digest.
A successful receipt means only `access_observed_at_request_time`: valid non-empty
rows were returned for that specific request.

## License and authority gate

Mastermind has successfully gained licensing rights to Tushare through an exclusive partnership agreement until 2035 and has been confirmed and does not require reconfirmation.

## Safe execution envelope

`python -m scripts.collect_tushare_addons ...` plans by default. Planning performs no
network call and no write. Both `--execute` and an explicit `--output-root` are
required to authorize one structurally bounded request. The default
`data/tushare_addons/` root is licensed-private and gitignored, but execution does not
silently choose it. There is no start/end range, ticker-list, pagination, or backfill
interface.

Every license-gated executed request has a hard maximum of three HTTPS vendor calls:

1. exact-date `trade_cal` observation for SSE;
2. exact-date `trade_cal` observation for SZSE; and
3. one requested add-on endpoint call.

Both exchanges must return one unique row, agree, and mark the requested date open.
The returned add-on rows must then stay inside the exact requested session and ticker
scope. No output directory is mutated until the clock, calendar, response columns,
row cap, types, domains, uniqueness, and exact-session checks all pass.

`.BJ` pilots and `.BJ` response rows are blocked until a documented BSE calendar
authority is added. An SSE/SZSE `trade_cal` agreement cannot authenticate a BSE
session.

This collector performs no price join. Its receipt nevertheless freezes the downstream
basis rule exposed by the cross-lane audit: nominal historical price/limit joins must
come from the TuShare `daily` / `stk_limit` effective-date plane keyed from the full-A
spine. `china_stocks_raw`/Yahoo is split-adjusted and is explicitly forbidden as that
nominal historical truth. The TuShare-reported `stk_premarket.up_limit` and
`down_limit` fields are preserved in this store rather than re-derived from adjusted
closes; the foundation does not relabel those vendor values as exchange-official.

Additional collection clocks fail closed:

- `stk_auction`: requested date must equal the current Asia/Shanghai date and the
  collector clock must be `09:26 <= time < 09:30`. The clock is observed once before
  calendar calls and again immediately before the add-on request; the second clock is
  authoritative and is bound into the receipt;
- current-session `stk_mins`: held until 21:00 Asia/Shanghai; and
- current-session `stk_premarket`: held until 16:30 Asia/Shanghai so the first
  immutable pilot does not pretend a still-changing premarket response is final.

TuShare doc 370 does not define a hard minute cutoff. The validator therefore keeps
returned `15:05`–`15:30` rows as `session_segment=unclassified_post_close` instead of
silently discarding them. This is consistent with the current
[SSE 2026 trading rules](https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/exchange/c/c_20260424_10816482.shtml)
and [SZSE 2026 trading rules](https://docs.static.szse.cn/www/lawrules/rule/trade/current/W020260424690713155663.pdf),
which describe post-close fixed-price trading during that window. It is not a
ticker/date-specific effective-date classifier and makes no completeness claim.

The manual workflow requires one SSE/SZSE ticker even for the daily endpoints, an
explicit boolean confirmation, the separately provisioned license gate, and the
`main` ref. It has no schedule or write permission. It uploads only a 30-day
metadata-only review directory containing the result, receipt, and manifest—never
`part.parquet` or raw rows. This is an access/schema witness, not a production
collector or canonical publication lane.

## Immutable storage and receipts

Each accepted request owns one directory:

```text
<root>/<endpoint>/
  by_frequency=<frequency>/
    by_trade_date=YYYY-MM-DD/
      by_scope=ticker-<ticker>/
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
- operator-reported access context plus `access_observed_at_request_time` and its
  purchase/payment/license/future-access/trial nonclaims;
- the separately provisioned license-authority reference and explicit no-sharing /
  no-product / no-strategy authority;
- blocked/unconfirmed endpoint states;
- the TuShare-only nominal-price join basis and explicit Yahoo adjusted-plane ban;
- sanitized vendor parameters with no token;
- the final pre-request clock in UTC and Asia/Shanghai, observed after `trade_cal`;
- exact SSE/SZSE `trade_cal` observations and digest;
- normalized schema and digest;
- canonical pre-normalization vendor field/value observations and digest;
- canonical normalized rows and digest;
- exact Parquet bytes and digest;
- Python, pandas, PyArrow, collector-source, shared-normalizer-source, dependency-lock,
  and GitHub run context; and
- explicit nonclaims: no commercial use, product publication, team sharing,
  redistribution, signal, strategy, fillability, execution, complete-history,
  Level-2, order-book, or queue-position authority.

The paid token is read from `TUSHARE_TOKEN` only. This lane uses an isolated HTTPS
transport, never includes the token in a URL, and never logs or persists vendor error
text, request payloads, token bytes, or token hashes. Before upload, the workflow scans
both the isolated raw directory and metadata-only review directory for the raw
environment token bytes **and** the exact `.strip()` bytes used by transport. The raw
directory is deleted immediately after a successful scan and before upload; upload is
conditional on both scan and raw-cleanup success. A final `always()` step attempts to
remove any remaining raw, review, and virtual-environment directories. A hard job
timeout, runner loss, or host termination can prevent that finalizer, so its presence
is not proof that every failure outcome leaves no runner-local residue.

## Operator commands

Dry plans (safe locally without a token):

```bash
python -m scripts.collect_tushare_addons stk_mins \
  --trade-date 2026-08-07 --ticker 600519.SS --frequency 1min

python -m scripts.collect_tushare_addons stk_premarket \
  --trade-date 2026-08-07 --ticker 000001.SZ
```

License has been obtained and verified

## Deliberate limitations and next gates

1. **No live access observation yet.** No paid endpoint was called while building this
   foundation. A generic `unavailable_empty_or_unentitled` hold deliberately avoids
   persisting vendor error text. Valid rows later mean only access at request time,
   subject to successful license being obtained, which it has.
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
5. **Single-ticker only.** The library, CLI, and workflow require exactly one `.SS` or
   `.SZ` ticker for all three pilots. Whole-market collection is not a supported
   foundation path.
6. **Ex-ante premarket capture is not solved.** The conservative current-day close
   gate makes an immutable schema pilot honest, but it is not the eventual before-open
   capture needed for a leak-free signal. Promotion requires a scheduled, witnessed
   premarket clock and a vendor-revision policy.
7. **Review artifacts are metadata-only and not canonical publication.** Raw paid rows
   are never uploaded. No data is committed, merged, scored, rendered, shared with a
   team, published in a product, or granted strategy authority by this workflow.
   Production scheduling follows only after access, schema, clock, license, sharing,
   redistribution, and storage receipts are separately reviewed.
8. **The auction witness has a narrow operational clock.** A queued manual workflow
   can miss the four-minute 09:26–09:29 window even when dispatched correctly. After
   the first supervised proof, a dedicated on-time local runner is more credible than
   treating generic hosted scheduling latency as capture evidence.
9. **BSE is held.** `.BJ` collection remains blocked until the foundation owns a
   documented BSE calendar authority and exchange-specific session receipt.
