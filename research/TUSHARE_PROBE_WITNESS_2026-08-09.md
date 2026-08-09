# TuShare add-on live entitlement probes — TP-0 witness (2026-08-09)

**Capture clock:** 2026-08-09 23:00–23:02 Asia/Shanghai, plus one re-run at
2026-08-10 00:37 (see P3). Mac Studio, local `--execute` runs against
`https://api.tushare.pro`.

**Provenance:** operator-ordered wiring, `research/TUSHARE_WIRING_TAKEOVER_2026-08-09.md`.
Execution required a configured `TUSHARE_TOKEN` and nothing else.

**Headline: TP-0 is ANSWERED. All six probes returned rows and every response matched
its pinned contract exactly.** Six immutable partitions were written under a gitignored
root; no raw row, price, or token appears in this document or anywhere in git.

## Per-probe result

| # | Endpoint | Ticker | Session | Access observed | Rows | Schema vs contract |
|---|---|---|---|---|---|---|
| P1 | `stk_mins` (1min) | 600519.SS | 2026-08-07 | **yes** | **241** | conforms |
| P2 | `stk_premarket` | 000001.SZ | 2026-08-07 | **yes** | 1 | conforms |
| P3 | `stk_auction_o` | 000001.SZ | 2026-08-07 | **yes** | 1 | conforms |
| P4 | `stk_auction_o` | 000001.SZ | 2023-03-01 | **yes** | 1 | conforms |
| P5 | `stk_auction_c` | 000001.SZ | 2026-08-07 | **yes** | 1 | conforms |
| P6 | `stk_auction_c` | 000001.SZ | 2023-03-01 | **yes** | 1 | conforms |
| P7 | `stk_auction` (realtime) | — | — | **pending** | — | — |

`conforms` is a strict verdict, not a glance: the collector refuses to write unless the
response column set **exactly equals** the contract's documented field list (no missing
field, no extra field, no duplicate), the row count is inside the documented cap, every
value passes its type/domain check, and every row stays inside the exact requested
session and ticker. A written partition is therefore proof of conformance.

One honest limit on that verdict: the request sends `fields=<contract list>`, so the
vendor returns exactly what was asked for. Conformance proves **every documented field
is served and correctly typed**; it does not prove the endpoint serves no *additional*
undocumented field.

**P1's 241 rows** is a complete A-share session at 1-minute resolution (240 bars plus
the boundary bar) — consistent with a full, unsuspended day for 600519.SS.

**P3 needed one re-run.** Its first attempt held at
`trade_cal_unavailable_empty_or_unentitled`, which fires on the *first* calendar call.
That was transient, not a refusal: P5 issued the identical `trade_cal` request for the
same session seconds later and succeeded, and P4 had already proved `stk_auction_o`
entitled. The single re-run succeeded. No other probe was retried.

**P7 (`stk_auction`, realtime, doc 369) remains pending by clock, not by entitlement.**
It is same-day capture only, inside 09:26–09:29 Asia/Shanghai. Next window is Monday
2026-08-10.

Vendor traffic for this witness: 7 collector runs × 3 calls, minus the run that stopped
at its first calendar call — 19 calls total. Sequential, no retry-hammering.

## o/c history depth — the §8.5 question, ANSWERED

**`stk_auction_o` and `stk_auction_c` both serve deep history.** A 2023-03-01 session
(≈3.4 years back) returned a valid, contract-conforming row for both endpoints, and the
recent 2026-08-07 session did the same. Combined with docs 353/354 accepting
`start_date`/`end_date` and capping at 10,000 rows per request, the backfill shape a
bulk lane needs is confirmed available.

**Consequence for the §8.5 realtime 09:25 collector: `stk_auction_o` supersedes it for
every historical and backfill purpose.** The o/c plane is strictly better evidence for
research — it is published after the close, immutable, auditable, and re-fetchable for
any past session, whereas the realtime snapshot exists only if a collector happened to
be running inside a four-minute window on that specific morning.

What `stk_auction_o` does **not** replace is the realtime need itself: it is
`每天盘后更新` (published after that session's close), so it cannot tell you at 09:27
what the auction is doing *right now*. Retire the §8.5 collector only if the consumer
is research/backfill; keep a realtime path if any consumer needs the read intraday,
before the after-close publication.

## Unit resolution — the 100× hazard is closed

Docs 353/354 give 成交量 and 成交额 with **no unit**, and TuShare is inconsistent across
its own planes (`daily` reports volume in 手, the minute plane in 股), so a guessed unit
is a silent 100× error in any turnover or participation figure.

Resolved empirically by internal consistency — `amount / (vol × vwap)`, a dimensionless
ratio that needs no external reference and exposes no value:

| Partition | n | median `amount/(vol × price)` |
|---|---|---|
| `stk_auction_o` 2026-08-07 | 1 | 0.9995 |
| `stk_auction_o` 2023-03-01 | 1 | 1.0000 |
| `stk_auction_c` 2026-08-07 | 1 | 0.9996 |
| `stk_auction_c` 2023-03-01 | 1 | 1.0001 |
| `stk_mins` 2026-08-07 (control) | 240 | 1.0000 |

**Verdict: `vol` is in shares (股) and `amount` is in CNY (元)** — the same convention as
the minute plane, which serves as the control at exactly 1.0000. Lots (手) would have
produced ~100; 千元 would have produced ~0.01.

The contract deliberately still records `vendor-reported; docs 353/354 state no unit`,
because a contract's job is to state what the **document** specifies, not what we
inferred. The measurement lives here, with its method, so a consuming lane can adopt it
knowingly. Promoting the measured unit into the contract text is a reasonable follow-up
— it would change the contract digest, so it belongs in its own reviewed change.

## Receipt digests

Digests only — no rows, prices, or vendor payloads. Full receipts live beside each
`part.parquet` under the gitignored `data/tushare_addons/` root.

| Endpoint | Session | Rows | `normalized_rows_sha256` | `parquet_sha256` |
|---|---|---|---|---|
| `stk_mins` | 2026-08-07 | 241 | `5e5b39c028809db0…` | `d6ec8b3388587003…` |
| `stk_premarket` | 2026-08-07 | 1 | `8537815f8500531f…` | `c027be4c768c978f…` |
| `stk_auction_o` | 2026-08-07 | 1 | `b833a43c5e864d7f…` | `8091d3c2cea1dc18…` |
| `stk_auction_o` | 2023-03-01 | 1 | `5ad542f5fc1d86ae…` | `c3df5f78dc35555a…` |
| `stk_auction_c` | 2026-08-07 | 1 | `917e594625568e92…` | `1110befb78efa875…` |
| `stk_auction_c` | 2023-03-01 | 1 | `d4499eacd41cab1c…` | `09142b3e986adcd9…` |

Pinned endpoint contracts (field list, row cap, document, units):

| Endpoint | Doc | `contract_sha256` |
|---|---|---|
| `stk_mins` | 370 | `87a30ddbee314da58a16efb50daf96c7cf0ea1a07d6231642e2927904fac6122` |
| `stk_premarket` | 329 | `2c6db4c2fbbe89155911879fc17fff200e9bb28d0642f646c917d19338d33f93` |
| `stk_auction` | 369 | `dde1c22b52869ec3d6fffb5f5bd7479485904c62a1a158c9104a33a64d46b107` |
| `stk_auction_o` | 353 | `0c265b905832052d1eb0bb1d64bd6902ced51dc55acf7d472a191bd3ed2b3297` |
| `stk_auction_c` | 354 | `fb151f3d4b7eb82621c7ce8cadee19af05388fa4384717adb3786c0f238cfa60` |

The o/c field lists were read off the live doc pages
([353](https://tushare.pro/document/2?doc_id=353),
[354](https://tushare.pro/document/2?doc_id=354)) before any probe ran, so the schema
verdict above is a genuine test of the response against an independently sourced
contract — not a contract reverse-engineered from the response.

## Earlier credential outage (resolved)

An earlier pass of these same probes, run 2026-08-09 22:2x–22:41 Asia/Shanghai, was
refused at the credential layer: vendor code **40101** (the AUTH-class "token value
rejected" code documented in `collectors/tushare_client.py`) on the regular-tier
`trade_cal` control as well as on the add-ons. Lane C observed the same signature
account-wide by a disjoint route. The token was refreshed and every probe above then
succeeded. Recorded because the same signature will recur: 40101 on a regular-tier
endpoint means a dead credential, never an entitlement gap, and no amount of retrying
helps.

## What this witness does and does not say

It establishes **access at request time** for five endpoint/session pairs and the
schema conformance of each response. It does not claim future access: a working
credential today is not a guarantee for tomorrow, and the outage above is the proof.

The remaining epistemic limits are unchanged by a successful probe. A non-empty
minute-day may still be short because of suspension or vendor coverage rather than
being complete — P1's 241 rows are evidence for that one ticker-day, not a coverage
guarantee. None of these endpoints carry Level-2, order-book, or queue-position
information. No signal or strategy authority is created by a collector; promotion
happens at the gauntlet.
