# Prophet US availability ledger — August 2026

Authoritative per-session availability record for the Chairman's 2026-08-27
force-majeure mandate. Verdicts are about what USERS COULD SEE at market open,
with mint-record facts stated separately — the two diverge, and conflating them
is how this month was mis-narrated twice. Governing ruling:
`DEC:PROPHET-US-BACKFILL-IS-TWO-TIER`.

Evidence sources: git history of `site/prophet/index.json` (full walk
2026-07-31→08-27), origination receipts under
`data/prophet/origination_receipts/`, prophet-outage issues #5742/#5920/#6145/
#6366/#6495 (rescue-lane receipts), `research/PROPHET_OUTAGE_2026_08_17_POSTMORTEM.md`,
the VPS service journal, and `data/pit_replay/prophet_live_recovery/_recovery_receipt.json`
(PR #6484). Assembled 2026-08-27 by the CEO-takeover session; forensic packets
in `agentos/handoffs/PROPHET-US-AVAILABILITY-2026-08-27-ceo-takeover.md`.

| session | board at open | board minted for session | live intraday lane | cause / evidence |
|---|---|---|---|---|
| 08-03 Mon | fresh (T-1 normal) | yes — `4cc274f7a415` | dark | live frozen since 07-30 |
| 08-04 Tue | fresh | yes — `9a997e9da3fb` | dark | |
| 08-05 Wed | fresh (pre-08-09 schema, lower confidence) | yes — `1c75d73c361f` | dark | |
| 08-06 Thu | **STALE** (Aug-5 vintage) | late — `2dfebf35dbdf` post-close | dark | unclassified gap, predates known eras |
| 08-07 Fri | fresh | yes | dark; events recovered (#6484) | |
| 08-10 Mon | fresh | yes — `8421e4783f14` | dark | |
| 08-11 Tue | fresh | yes — `93fbaa6364ce` | dark; events recovered (#6484) | |
| 08-12 Wed | **STALE** (Aug-10 picks served) | **NO — the asof-08-11 build never minted; the month's one true mint hole** | dark | Aug-12 force-cancel incident (six cancels) |
| 08-13 Thu | fresh | yes — `f9140631d37c` | dark | |
| 08-14 Fri | fresh | yes — `012fbedc643b` | dark; events recovered (#6484) | issue #5742 era |
| 08-17 Mon | **STALE** (Aug-13 vintage all day) | late — `dedd97dcf832` 23:33Z | dark | GH013 ruleset freeze 08-15→17 (postmortem) |
| 08-18 Tue | fresh | yes — `e8b54f057f58` | dark | issue #5920 |
| 08-19 Wed | fresh | yes — `9d73eaa2c93b` | dark | |
| 08-20 Thu | fresh | yes — `0b0c296f85f3` | dark; events recovered (#6484) | issue #6145 |
| 08-21 Fri | fresh | yes — `028b28b84a12`, 27 plans | dark; events recovered (#6484) | issue #6366 receipts (cohort 27 = healthy) |
| 08-24 Mon | fresh (T-1 weekend-normal) | yes — 11 plans, receipt `32786919396-1` | dark | run-level "cancelled" = tail-job timeouts only; prophet job green |
| 08-25 Tue | fresh | yes — 9 plans, receipt `32908543584-1` | dark; events recovered (#6484) | |
| 08-26 Wed | fresh at open (T-1); **session's own board ~5h LATE** | pending run 33036497832 verification | **LIVE — full session, 84 publishes 13:28:09→20:23:08Z, 180 states, R2==served** | schedule strand (neither DST cron fired until 03:29Z 08-27); rescue STRAND receipt #6495 + dispatch 33032483296 |

## Honest totals (18 NYSE sessions)

- Board fresh at standard time: **14/18**.
- Stale at open / late: **4** (Aug 6, 12, 17, 26) — in each case the board
  eventually minted the same or next day; users were served stale during hours.
- True mint holes: **1** (the asof-2026-08-11 build). Recorded as force-majeure;
  never reconstructed into the graded ledger (DEC two-tier ruling).
- Live intraday lane: **1/18 sessions operating** (Aug-26, its first real
  session ever — the lane was born 2026-07-30 and never provisioned). Seven
  sessions carry journal-recovered genuine events (#6484: Jul-31, Aug-7, 11,
  14, 20, 21, 25); the remaining sessions have no production output to recover.

## The Aug-26 sighting that triggered this program

The ZONE chips reading "Aug 21" over the board were `signal.asof` — a 3-session
bucket OPEN-date label, a board-wide constant, stepping 08-18 → 08-21 → 08-26 —
rendered next to buy-zone prices that in fact moved nightly (101 of 115 common
tickers moved between the Aug-24 and Aug-25 vintages while every card's date
read 08-21). The board underneath was fresh. A date that reads as a freshness
clock but is not one generates false outage reports in both directions — fixed
display-side by PR #6532 ("Data through <as_of>", chip removed, bucket date
demoted to hover, `data-board-asof` for monitors); the measurement clock at
`engine/signal_quality.py:938` was deliberately not touched.

## What now prevents a silent repeat

PR #6534 (permanence net): intake-identity checks in all watchdogs
(lossless/unaccounted/wipeout), a post-publish acceptance alarm inside the
engine job that pages through its own alert type, the sentinel heartbeat graded
from GitHub via the public `/live/staleness.json` (the VPS watcher's own death
becomes loud), hourly rescue wakes, and the template-dereference coverage test
that makes the contract survive mechanism changes. Production proofs §0 of
`research/PROPHET_US_PERMANENCE_NET_2026-08-27.md` remain BUILT_NOT_PROVEN
until observed on natural runs — never dispatch to force them.
