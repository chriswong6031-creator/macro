---
key: CS-V2-W2A-CLASS-RESERVES-AND-HORIZON-FRESHNESS
question: >
  Under the unchanged 200-filing collector cap, which deterministic class
  reserves and spill law should W2A use, and what may the public projection call
  fresh when the compiler clock is recent but filing horizons are behind?
answer: >
  Reserve 160 slots for LIVE_TAIL, 20 for RECOVERY, and 20 for
  HISTORICAL_BACKFILL. Classify from persisted completed SEC index sessions and
  queue attempts: a latest-open storage_deferred, transient_error, or
  stored_parser_deferred attempt in the latest 20 completed sessions takes
  RECOVERY precedence; otherwise the latest five completed sessions are
  LIVE_TAIL and the remainder is historical. Within each existing lane,
  LIVE_TAIL serves newest filing sessions first and uses current-run arrival as
  the same-session tie-break; RECOVERY and historical debt retain oldest-first
  service.
  Transfer unused class reservations deterministically in donor order
  LIVE_TAIL, RECOVERY, HISTORICAL_BACKFILL to recipient priority LIVE_TAIL,
  RECOVERY, HISTORICAL_BACKFILL, excluding the donor. Preserve lane fairness
  inside each final class allocation. This is a bounded fairness policy, not a
  claim that 160 live slots satisfy current all-policy arrivals. Canonical health
  separately reports current, lagging, degraded_capacity,
  degraded_discovery, or unavailable from discovered, eligible-retained, and
  compiled filing horizons. Public freshness is fresh only for a generation-
  bound current horizon; compiler age remains separate generation telemetry.
rationale: >
  On exact implementation-base ledgers, eight recent completed SEC sessions had
  all-policy daily arrivals p50 281.5, p95 471.4, and max 485, so no partition of
  the fixed 200 cap can both clear the full tail and preserve recovery and
  history. The 160/20/20 split gives live work 80 percent of guaranteed capacity
  while keeping independently observable ten-percent drains for failed retries
  and historical debt. Unused reserves spill, so an empty recovery class does
  not waste throughput. Latest eligible-retained and compiled filing dates were
  both 2026-07-31 against discovered 2026-08-20; a recent compiler clock cannot
  truthfully make that information horizon fresh. The existing daily-index
  pipeline recovered 2026-08-20 after a prior retry, so the remaining 2026-08-21
  retry is degraded-discovery evidence, not evidence that a second source is
  necessary.
alternatives:
  - option: Reserve 180 LIVE_TAIL, 10 RECOVERY, and 10 HISTORICAL_BACKFILL
    why_not: >
      It still cannot satisfy observed live arrivals and leaves too little
      protected capacity to observe recovery and historical lane fairness.
  - option: Reserve 140 LIVE_TAIL, 30 RECOVERY, and 30 HISTORICAL_BACKFILL
    why_not: >
      Recovery was empty in the measured recent-session window, so this would
      unnecessarily reduce guaranteed live service before deterministic spill.
  - option: Raise the 200 cap or add a current-submissions overlay in W2A
    why_not: >
      The commission preserves the cap and requires proof that daily-index is
      inadequate before a source expansion. One-day index recovery is proven;
      capacity and retry degradation must be measured first.
  - option: Continue deriving freshness from telemetry.as_of
    why_not: >
      It labels a 2026-07-31 filing horizon fresh on 2026-08-22 and confuses
      successful compilation with current source knowledge.
evidence:
  - "research/CAPITAL_STRUCTURE_W2A_QUEUE_CENSUS_2026-08-21.md"
  - "DEC:CS-V2-LIVE-TAIL-SEPARATE-FROM-BACKLOG"
  - "DSC:CS-THROUGHPUT-HEALTHY-HORIZON-STALE"
  - "implementation base 33d70f5ce4b36329e8acfb285557f4c9d3c72589"
affects:
  - "WS:CAPITAL-STRUCTURE-INTELLIGENCE-V2"
  - "collectors/sec_capital_structure.py"
  - "engine/capital_structure/ingestion_health.py"
  - "engine/capital_structure/projection.py"
  - "scripts/build_capital_structure_projection.py"
confidence: high
reversibility: easy
decided_by: codex
decided_at: 2026-08-21
review_by: 2026-08-28
---

The reserved split deliberately exposes rather than hides the structural
capacity deficit. A future cap or source change needs new measured evidence and
its own Sol review; it is not implicit in this W2A decision.
