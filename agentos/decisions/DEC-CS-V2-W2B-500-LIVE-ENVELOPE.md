---
key: CS-V2-W2B-500-LIVE-ENVELOPE
question: >
  After W2A proved honest class scheduling but a structural cap deficit, what
  one capacity envelope can the existing natural collector safely support while
  preserving recovery, history, W1 identity, W2A horizon truth, and SEC pacing?
answer: >
  Set the one canonical reservation map to LIVE_TAIL 500, RECOVERY 20, and
  HISTORICAL_BACKFILL 20, and derive the global 540 ceiling from its sum.
  Preserve every W2A classification, precedence, newest-session, lane-fairness,
  oldest-debt, and deterministic-spill law. Arrival overflow remains
  max(0, current-run LIVE arrivals minus effective LIVE capacity), while
  live_tail_unserved_after_selection continues to expose inherited debt.
  Preserve the existing daily carrier, 0.12-second SEC pacing, retries, storage
  fallback, timing ledger, 85-percent tripwire, identities, append-only fence,
  projection binding, and prophet_authority=false.
rationale: >
  The latest nine conservative capacity-census cohorts are 334, 353, 446, 485,
  217, 190, 229, 199, and 202; no completed session exceeds 500. Natural cap-200
  collection took 994.2 seconds attributable to sec_capital_structure and 126.0 minutes
  end-to-end. A deliberately conservative projection based on the slowest of
  the latest three cap-200 SEC bands and the largest recent non-CS collect
  remainder puts cap 540 at 184.6 minutes: 19.4 minutes below the existing
  204-minute warning line and 55.4 minutes below the 240-minute hard cap. The
  adapter remains serial, so the cap changes duration rather than request rate.
  The observed dedicated-store 403 is an R2 AccessDenied with a sub-second
  existing fallback, not an SEC pacing response. Zero SEC 429s were observed.
  Hostile review replayed the materially unbalanced raw maximum cohort with its
  full preceding discovery anchors: 484 of 485 rows were policy-eligible and
  all 484 were selected by the unchanged scheduler. The one excluded issuer row
  had no registration anchor and was never an admitted LIVE arrival. A contrary
  reduced-discovery replay was rejected because removing historical anchors
  changed policy eligibility rather than testing capacity.
alternatives:
  - option: Keep 200 and wait for inherited debt to drain
    why_not: >
      Recent policy-discovery and admitted-arrival censuses repeatedly exceed
      the effective 180 LIVE slots,
      so natural runs can create fresh debt faster than they drain old debt.
  - option: Raise the cap above 540 or the LIVE envelope above 500
    why_not: >
      No completed-session evidence supports a larger commissioned envelope;
      more than 500 is an explicit falsifier that must return to Sol.
  - option: Add Latest Filings, RSS, submissions JSON, a second daily, or a dedicated carrier
    why_not: >
      W2A proved discovered, retained, compiled, completed, and expected
      horizons equal. The measured defect is capacity, and W2B has no discovery
      or carrier authority.
  - option: Hide inherited LIVE debt once current arrivals fit
    why_not: >
      It would turn a capacity change into a freshness redefinition. Zero
      arrival overflow and nonzero unserved inherited LIVE debt are distinct,
      simultaneously valid facts.
evidence:
  - "research/CAPITAL_STRUCTURE_W2B_CAPACITY_QUALIFICATION_2026-08-23.md"
  - "daily.yml run 32603557988; collect job 97105275976; capital_structure job 97119200594"
  - "data/ops/nightly_timings/collect.jsonl cap-200 rows for runs 32426513915, 32534736736, and 32603557988"
  - "DSC:CS-V2-W2A-NATURAL-CHAIN-PROVEN-LIVE"
  - "DEC:CS-V2-W2A-CLASS-RESERVES-AND-HORIZON-FRESHNESS"
  - "Independent Sol anchor-correct replay of the raw 2026-08-14 485-row seven-lane cohort"
affects:
  - "WS:CAPITAL-STRUCTURE-INTELLIGENCE-V2"
  - "collectors/sec_capital_structure.py"
  - "tests/test_sec_capital_structure.py"
  - "tests/test_capital_structure_ingestion_health.py"
confidence: high
reversibility: easy
decided_by: chairman
decided_at: 2026-08-23
review_by: 2026-08-30
---

## Acceptance and reconsideration

The first natural scheduled chain after merge is the production proof; no
duplicate daily may be dispatched. If its admitted LIVE arrivals are at most
500, arrival overflow must be zero and inherited LIVE backlog must decrease,
while populated RECOVERY and HISTORICAL service retain 20 slots each. A horizon
may remain `degraded_capacity` solely because inherited LIVE debt remains.

Reconsider this decision if an admitted cohort exceeds 500, unchanged SEC pacing
produces a rate-limit response, the qualified runtime budget is breached, or the
natural chain fails a W1/W2A invariant. Reconsideration belongs to Sol and does
not itself authorize a larger cap or a new carrier.
