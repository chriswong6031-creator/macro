---
key: CS-THROUGHPUT-HEALTHY-HORIZON-STALE
claim: >
  After PR 5792, a Capital Structure run can select and retain 200 filings,
  advance manifests and event versions, and print health verdict ok with
  projection coverage.freshness fresh, while latest_source_filing_date stays
  2026-07-31 because the queue is oldest-first against about 19k pending rows
  first-seen around 2026-08-01. Throughput is healthy and the information
  horizon is stale.
falsifier: >
  Show health.json at a later generation where latest_source_filing_date
  equals the latest SEC material filing date within the live window, or show
  the queue selecting LIVE_TAIL before HISTORICAL_BACKFILL, or show
  coverage.freshness computed from filing/publication watermarks rather than
  compiler generated_at. Dated files: data/capital_structure/health.json,
  projection.json, retrieval_queue_receipt.json.
so_what: >
  Never equate successful ingestion or compiler-fresh with current knowledge.
  Do not raise MAX_FILINGS as the architecture fix. Wave 2 must split
  LIVE_TAIL / RECOVERY / HISTORICAL_BACKFILL and report live-tail gap age.
  Live row counts are dated observations, not eternal contracts.
kind: runtime
verified_at: 2026-08-18
verified_by: >
  Worktree data/capital_structure at freeze SHA 791148b2b7d5, generation
  as_of 2026-08-18T07:58:19Z: health latest_source_filing_date 2026-07-31,
  latest_source_retrieved_at 2026-08-18T03:33:56Z, selected 200, retained 200,
  pending 19018, parked 403, verdict ok; projection coverage.freshness fresh,
  age_hours 0.66, freshness_sla_hours 30, issuer_count 426, event_count 600.
scope:
  - macro
  - capital-structure-intelligence
  - data/capital_structure/health.json
  - collectors/sec_capital_structure.py
confidence: verified
expires: 2026-11-16
---

Expires because live watermarks will move. The architectural claim (oldest-first
plus compiler-age freshness is the wrong SLO) remains until Wave 2 lands.
Re-verify counts before quoting them.
