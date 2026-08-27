---
key: FUND-NEXT-DATE-HAS-THREE-PRODUCERS
claim: >
  Terminal's `fund.earnings.next_date` is emitted by THREE independent producers, not one:
  `ingest/gen_fund_us.py` (at TWO sites - `build_earnings`, and `build_estimates` where the
  date drives the `q0`/`q1` estimate column labels), `ingest/gen_fund_hk.py`, and
  `ingest/gen_fund_cn.py`. On 2026-08-26 all three were simultaneously violating the
  "next means future" contract in production: KRUS served `2026-07-07` (50 days past),
  9988.HK served `2026-08-20` (6 days past), and 600519.SS served the literal string
  `'nan'`. The CN path is structurally the worst of the three - it PREFERS the tushare
  disclosure feed's `actual_date`, which is by definition the day a report was already
  filed and therefore always past, and it separately CARRIED `next_date` FORWARD from the
  previous artifact whenever the live source went quiet, so once a past date entered it
  survived indefinitely. A fourth site, `ingest/collect_cn_hk_fund.py`, truncated the
  vendor calendar to `str(eds[0])` at COLLECT time, discarding later candidates before any
  emitter could see them - so HK could never satisfy "mixed past/future -> earliest future"
  no matter what the emitter did. Issue mastermind-terminal#474 named only the US
  `build_earnings` site.
falsifier: >
  `grep -rnE '"next_date":|next_date =|"next_earnings"\]' ingest/` in
  mastermind-terminal returning sites in only one emitter, or any of
  `curl -s https://app.mastermind-x.com/data/{KRUS,9988.HK,600519.SS}.fund.json | jq .earnings.next_date`
  returning a date earlier than the UTC day after that family's nightly has run.
so_what: >
  Never scope a `next_date` repair to the emitter named in the bug report - a US-only fix
  cannot make a past date impossible to publish, which is what the mission actually asks.
  Repairs belong in the shared `ingest/earnings_calendar.py` selector that all four sites
  now call, and the CN carry-forward plus the HK collect-time truncation are separate
  failure modes that a selector alone does not reach. Consumers must ALSO fail closed:
  artifacts refresh on per-family nightlies, so a fixed producer leaves stale past dates
  served for hours to days.
kind: architecture
verified_at: 2026-08-26
verified_by: "mastermindx-market-intelligence/mastermind-terminal PR #477; production payloads read from app.mastermind-x.com/data/*.fund.json on 2026-08-26"
scope:
  - mastermind-terminal
  - mastermind-terminal:ingest/gen_fund_*.py
  - mastermind-terminal:ingest/collect_cn_hk_fund.py
confidence: verified
---

Production state that motivated this, read from the real served artifacts on 2026-08-26 UTC:

| family | ticker | served `earnings.next_date` | |
|---|---|---|---|
| US | `KRUS` | `2026-07-07` | 50 days past — the reported bug |
| HK | `9988.HK` | `2026-08-20` | 6 days past |
| CN | `600519.SS` | `'nan'` | malformed string |
| US | `AAPL` | `2026-10-29` | valid future — must survive a repair |
| US | `NVDA`, `CRM` | `2026-08-26` | **today** — an exclusive `> today` deletes real events |

The last row is the boundary that makes "today is valid" load-bearing rather than pedantic: a
date-only source cannot prove a same-day report has already been filed, and two real tickers sat
exactly on it the day the fix was written.
