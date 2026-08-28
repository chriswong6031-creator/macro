---
key: CS-V2-W2D-DUAL-DISCOVERY-CLOCK
question: >
  How can Capital Structure observe current SEC filings before nightly index
  publication while keeping one discovery ledger, daily reconciliation
  authority, archive-byte evidence law, and honest horizon truth?
answer: >
  Add the official SEC Latest Filings Atom surface as a provisional same-day
  accession overlay into the existing discovery ledger. Traverse it
  exhaustively and boundedly from the prior durable update watermark, dedupe by
  canonical accession, and fail closed on an unproven boundary or moving source.
  Keep the daily EDGAR form index authoritative for end-of-day reconciliation
  and backfill, and keep SEC Archives complete-submission bytes as the only
  retained filing evidence. Publish separate America/New_York real-time and
  daily-index readiness watermarks. Require each open filing day's Latest
  Filings observation, but require a daily index only after 06:00 ET the next
  calendar day. A daily row reconciles provisional metadata in place without
  rewriting historical evidence or events.
rationale: >
  Natural run 32786919396 asked for August 25 while New York was still on
  August 24 and asked for August 24 before its documented nightly build. A later
  exact-header canary retrieved the August 24 index with a 22:01:43 ET
  Last-Modified while August 25 remained absent and returned XML AccessDenied.
  Official SEC documentation says current-day indexes begin updating around
  22:00 ET and usually complete within a few hours. Latest Filings is the
  official low-latency surface, but a 30-page canary still did not exhaust the
  Aug24/Aug25 boundary and showed material multi-role duplication. The adopted
  clock and traversal rules remove false overdue states without allowing a
  complete prior-day index to masquerade as current same-day observation.
alternatives:
  - option: Change only latest_expected_sec_index_date
    why_not: >
      That avoids the UTC/future-index false positive but leaves today's filing
      stream unobserved and could falsely report current from yesterday's index.
  - option: Read only the first Latest Filings page
    why_not: >
      The live canary required more than 30 full pages and one accession may be
      repeated for multiple roles; one page cannot prove market-wide discovery.
  - option: Treat Latest Filings metadata as filing evidence
    why_not: >
      Metadata is provisional and can be corrected by the daily index. W1 law
      requires retained SEC Archives bytes for evidence identity and events.
  - option: Add a second queue, store, job, or cadence
    why_not: >
      Both official discovery surfaces can reconcile into the existing ledger
      and flow through the existing queue and natural daily carrier.
evidence:
  - "research/CAPITAL_STRUCTURE_W2D_SEC_DISCOVERY_QUALIFICATION_2026-08-25.md"
  - "daily.yml run 32786919396; collect job 97620633216; generation a6ff3b6b47db58ec549ff4508399312311f549a1"
  - "SEC August 24 daily-index canary: HTTP 200, Last-Modified 2026-08-25T02:01:43Z, SHA-256 40b557e6e6782c79084c6d7256d81dff8a498ebf8040d9b65f05cdcaeea7f649"
  - "SEC Latest Filings canary: 30 full pages, 3,000 rows, 2,031 unique accessions, boundary not exhausted"
  - "https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data"
  - "https://www.sec.gov/about/developer-resources"
  - "https://www.sec.gov/about/rss-feeds"
affects:
  - "WS:CAPITAL-STRUCTURE-INTELLIGENCE-V2"
  - "collectors/sec_capital_structure.py"
  - "engine/capital_structure/sec_discovery_clock.py"
  - "engine/capital_structure/ingestion_health.py"
  - "contracts/capital_structure_retrieval_queue_receipt.schema.json"
  - "contracts/capital_structure_ingestion_health.schema.json"
confidence: high
reversibility: easy
decided_by: chairman
decided_at: 2026-08-25
review_by: 2026-09-01
---

## Acceptance and reconsideration

W2D remains held for Sol and may not merge before W2C adjudication. After both
waves are accepted and merged, the first natural scheduled chain containing both
must prove complete bounded Latest Filings traversal, required daily
reconciliation, no duplicate discovery/evidence/event identity, and an honestly
current horizon.

Reconsider the 06:00 ET readiness boundary if official SEC publication guidance
changes or natural receipts show a normally published prior-day index remains
incomplete beyond that time. Reconsider the 20,000-row bound if a natural scan
cannot reach its prior durable watermark; that is a return to Sol, not authority
to publish a partial overlay or add a carrier.
