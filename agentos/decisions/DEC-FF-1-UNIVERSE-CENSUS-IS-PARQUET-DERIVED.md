---
key: FF-1-UNIVERSE-CENSUS-IS-PARQUET-DERIVED
question: >
  After FF-1P2R commissioning, is the literal 2,837 observation in
  DEC:FF-1-UNIVERSE-BIND-CAP-4000 the operating FF-1 universe, or is the
  universe derived from the canonical parquet at each execution identity?
answer: >
  The FF-1 universe is data/edgar/fundamentals.parquet at the execution
  identity, and its count is derived evidence rather than a frozen constant.
  This decision replaces DEC:FF-1-UNIVERSE-BIND-CAP-4000 as the complete
  AgentOS statement of the universe law. Its only substantive change is to
  retire the older decision's frozen 2,837 observation. It expressly carries
  forward the 4,000 hard bind cap, canonical-parquet identity and validation,
  rows == unique tickers == unique CIKs == expected == observed, immutable
  provenance, no shrink or filter of the parquet, no increase to
  MAX_AFFECTED_ISSUERS or the Company Facts byte budget, no removal of the hard
  cap, no July recovery authorization, and no FF-2 start.
rationale: >
  2,837 was a point-in-time measurement that proved 2,500 was too low; it was
  never a hand-maintained product universe. Independent producer commit
  f1e356f684ec988925718ceb3970a4fafaae3eb9 advanced the canonical parquet
  before #5898's tested production state. Run A then bound a coherent
  2,841/2,841/2,841 census with expected == observed and zero failures; Run B
  independently repeated that identity while proving the quiet incremental
  path. 2,841 is the accepted Run A census, not a permanent future
  requirement. The 4,000 cap remains a fail-closed safety bound, not a target
  census or permission to crawl every EDGAR issuer.
alternatives:
  - option: Keep 2,837 as the operational universe statement
    why_not: >
      It turns a dated observation into a stale contract and conflicts with
      the canonical-parquet universe law.
  - option: Revert or specially reconcile the four additional issuers
    why_not: >
      The movement came from an independent canonical producer, was already in
      the tested base, and produced a coherent census with zero FF failures.
  - option: Remove the 4,000 hard cap after commissioning
    why_not: >
      A malformed or wrong input must not become an unbounded SEC crawl.
  - option: Change recovery limits or begin FF-1R or FF-2 here
    why_not: >
      This is census semantics only. Recovery commissioning and FF-2's
      dependency boundary remain binding.
evidence:
  - >
    SOL RULING — RUN A ACCEPTED / RUN B RELEASED (2026-08-22): accepts the
    2,841 Run A census, replaces the frozen-count requirement with the
    parquet-derived law, releases one incremental Run B, and preserves the
    no-recovery and no-FF-2 boundaries
  - DEC:FF-1-UNIVERSE-BIND-CAP-4000
  - "Producer commit f1e356f684ec988925718ceb3970a4fafaae3eb9"
  - "PR #5898 squash merge 21f51a1ecfed778a738b048bd7e5efd30b1d9336"
  - "Run A 32604043860 / run_4e7970fb7cb841b6671d: 2,841 canonical issuers, complete baseline"
  - "Run B 32605564919 / run_8583eb7ce7476290c0b2: 2,841 canonical issuers, complete quiet incremental"
affects:
  - WS:FUNDAMENTAL-FORENSICS
  - engine/fundamental_forensics/broad_sec_store.py
  - scripts/run_fundamental_forensics_broad_sec.py
confidence: high
reversibility: easy
decided_by: ceo-sol
decided_at: 2026-08-22
supersedes:
  - DEC:FF-1-UNIVERSE-BIND-CAP-4000
---

AgentOS supersession is record-wide: this is the active successor and the old
record is no longer independently active. The only rule changed is the frozen
`2,837` premise. Every other rule named above is re-adopted here without
expansion, including the 4,000 cap, fail-closed behavior, canonical-parquet
identity and validation, immutable provenance, affected-issuer and byte bounds,
recovery limits, recovery commissioning boundary, and FF-2 prohibition.
