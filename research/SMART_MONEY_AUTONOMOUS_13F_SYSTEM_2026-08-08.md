# Autonomous 13F system assessment — 2026-08-08

## Decision

The apparent outage was not a total SEC ingestion failure. The repository had
already collected every Q2 2026 original filed by the featured roster: Aquamarine
(2026-07-10), Egerton (2026-07-21), and Polen (2026-08-04). The defect was that the
page's hard-coded/modal-quarter language hid those arrivals while mixed-quarter
aggregates treated pending managers as if they held zero positions.

The production contract is now two-state:

1. Before a strict majority reports, canonical consensus, crowding, trend, flow,
   and initiation boards stay on the last complete baseline quarter. Incoming
   filings appear only in the reporter-by-reporter Filing Season Live radar.
2. After a strict majority reports, canonical boards switch to the incoming
   reporters and compare them only with those same managers' prior books. Coverage
   and `cohort_basis=paired_reporters` remain explicit until completion.

An unfiled manager is missing, never zero. An exit exists only after that manager
files the incoming quarter and omits the security.

## What was automated already

- `collectors/edgar_13f.py` polls every configured CIK and writes an unseen period
  immediately; it never waits for the deadline.
- The broad nightly workflow then rebuilds the tracker, desk payload, fund pages,
  and HTML.
- Historical originals are period-keyed immutable Parquets; amendments are retained
  separately.

That was rolling in data mechanics but fragile in operations: discovery depended on
a multi-hour nightly lane, so an unrelated failure could delay a filing that the SEC
had already published.

## Autonomous operating contract added

- `.github/workflows/smart-money-filings.yml` polls the featured roster six times per
  US business day during open filing windows. It no-ops outside the window, rebuilds
  only after a new accession, and leaves forward-ledger advancement to the nightly
  lane.
- An all-CIK SEC submissions failure now raises instead of producing a false-green
  50-fund heartbeat.
- Accession-keyed receipts retain originals, amendments, and 13F-NT notices with
  acceptance time, source index, and first-observed time. Newly downloaded snapshots
  also carry accession, acceptance-aware available date, source URL/SHA-256, fetch
  time, and parser version.
- Notice-only filers are displayed as a separate transition state; a 13F-NT never
  becomes a zero-position book, an exit, or an incoming-quarter consensus member.
- The reported market value is retained separately from normalized dollars. A
  conservative compatibility detector flags post-2023 filings that still exhibit
  the legacy thousands-unit shape; old repository snapshots are corrected at read
  time without rewriting the immutable filing evidence.
- `data/quality/smart_money_freshness.json` reports collector heartbeat, filing
  coverage, receipt count, canonical period, and post-deadline exceptions.
- Deadline math rolls weekends and US federal holidays to the next business day.
- The five existing forward ledgers now mature previously-null horizons exactly once
  instead of discarding recomputed natural keys forever.
- `data/smart_money/manager_history.parquet` freezes settled decision-weighted
  60-calendar-day manager excess, hit rate, cohort rank, and descriptive outcome
  grade under a versioned public-availability methodology, including the exact
  roster count and roster hash used for each recorded cohort.

All ranking remains descriptive/context-only. It is not wired into Neural Web,
Prophet, allocation, or a buy signal.

## Why the live radar is worthwhile

Early filing is unusual for the current featured cohort but common enough across the
market to be valuable:

- In the prior complete season, 43 of 50 active featured managers filed on the
  deadline; only one filed at least five days early.
- The current three reporters were 35, 24, and 10 days ahead of the Q2 deadline,
  respectively, so this window is exceptional for the curated desk.
- The SEC's official Q1 2026 bulk data contains 8,741 original holdings filers; 55.3%
  were public at least five calendar days before the deadline.

The radar ranks *disclosure importance*, not expected return: action type, reported
book weight, share-count change, position rank, and the manager's descriptive grade.
Earliness is metadata and never adds score. One card is retained per reporter so a
large filing cannot exhaust the global event-wire cap and hide smaller early filers.

## Universe decision: census and research roster must be separate

The 50 active managers represent roughly 0.57% of the 8,741 original Q1 2026 holdings
filers in the official SEC dataset. Expanding `config.smart_money.funds` to thousands
would be the wrong architecture: that roster fans into expensive dossiers,
followability calculations, company sidecars, and other curated-manager consumers.
It would also mix banks, insurers, pensions, passive indexers, custodians, market
makers, and hedge funds as if they expressed comparable discretionary conviction.

Build four explicit tiers instead:

1. **Universal evidence plane** — every `13F-HR`, amendment, `13F-NT`, and included-
   manager relationship; accession-keyed immutable raw evidence.
2. **Normalized institutional census** — parent/affiliate deduplication plus
   passive, quant, custody, and strategy classifications. This powers broad ownership
   breadth, crowding, and market-wide buy/sell aggregates.
3. **Research-eligible managers** — approximately 500–1,000 entities with adequate
   point-in-time identity, history, resolution coverage, interpretable turnover, and
   priced decisions.
4. **Featured desk** — approximately 50–150 managers with full dossiers, alerts,
   acceptance-aware grades, and sufficient out-of-sample evidence.

Use SEC quarterly bulk Form 13F datasets for historical backfill/reconciliation and
daily/master indexes for universal rolling discovery. Store the roughly tens of
millions of multi-quarter information-table rows in partitioned Parquet/object
storage, not thousands of Git directories. Freeze roster membership by quarter and
use shrinkage/sample thresholds so selecting today's best-looking filer does not
manufacture survivorship or multiple-testing winners.

## Source references

- SEC Form 13F FAQ: https://www.sec.gov/rules-regulations/staff-guidance/division-investment-management-frequently-asked-questions/frequently-asked-questions-about-form-13f
- SEC Form 13F datasets: https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets
- SEC EDGAR APIs: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- SEC accessing EDGAR data: https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data
