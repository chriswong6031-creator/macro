---
key: CS-V2-LIVE-TAIL-SEPARATE-FROM-BACKLOG
question: >
  Ingestion now retains 200 filings per run with a healthy storage verdict, but
  latest_source_filing_date remains 2026-07-31 while ~19k pending rows date to
  August 1. Should V2 raise MAX_FILINGS, or split work classes so live
  dissemination cannot be starved by historical debt?
answer: >
  Independent work classes LIVE_TAIL, RECOVERY, and HISTORICAL_BACKFILL with
  separate quotas and a live-tail freshness SLO. Health must report discovered,
  retained, and compiled material watermarks plus live-tail gap age. Compiler
  generation age is not information horizon. Do not raise MAX_FILINGS as the
  fix. Narrowest source extension is an overlay on the existing daily-index
  collector (evaluate SEC current-submissions/Atom), not a second store.
  Live-tail implementation is Wave 2, after identity Wave 1.
rationale: >
  Oldest-first selection plus a 200-filing cap is a rate budget that currently
  spends entirely on May-July debt. Projection coverage.freshness is already
  'fresh' against a 30h compiler SLA while the filing horizon is 18 days stale.
  Equating those is how the recovered system can claim health and still not
  know today's capital events. A larger cap would still let historical debt
  win every night. Concurrent collect and clocked identity make scaling
  retrieval unsafe until W1.
alternatives:
  - option: Increase MAX_FILINGS until the August backlog clears
    why_not: Burns rate budget, still has no live-tail SLO, and remints if
      identity is unfixed. Throughput is already healthy.
  - option: Drop historical pending rows
    why_not: Coverage debt is real; recovery and backfill remain required
      classes, just not allowed to starve live-tail.
  - option: Stand up a second SEC collector for real-time feeds
    why_not: Forbidden second truth store. Overlay enqueue onto the existing
      collector.
evidence:
  - "data/capital_structure/health.json at freeze: latest_source_filing_date 2026-07-31, latest_source_retrieved_at 2026-08-18T03:33:56Z, pending 19018, selected 200, verdict ok"
  - "data/capital_structure/projection.json coverage.freshness fresh, age_hours 0.66, freshness_sla_hours 30, reason event_state_only"
  - "queue oldest_pending_first_seen 2026-08-01T15:35:40Z"
  - "research/CAPITAL_STRUCTURE_INTELLIGENCE_V2_MASTERPLAN_2026-08-18.md §3.2 §12"
affects:
  - "WS:CAPITAL-STRUCTURE-INTELLIGENCE-V2"
  - "capital-structure-intelligence"
  - "collectors/sec_capital_structure.py"
  - "scripts/check_capital_structure_health.py"
confidence: high
reversibility: easy
decided_by: coo-fable
decided_at: 2026-08-18
review_by: 2026-08-25
---

Wave 2 implements the split. Wave 1 must land first so live-tail re-observation
does not remint evidence identities.
