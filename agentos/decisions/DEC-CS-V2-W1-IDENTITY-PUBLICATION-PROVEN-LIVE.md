---
key: CS-V2-W1-IDENTITY-PUBLICATION-PROVEN-LIVE
question: >
  After Sol accepted and merged W1B #6044, does the first natural collector →
  Capital Structure chain close the W1 identity/publication production-proof
  hold, and what is the next wave?
answer: >
  Yes. W1B is done. The W1 identity and publication foundation is PROVEN_LIVE.
  The W1 production-proof hold is cleared. W2 (LIVE_TAIL / RECOVERY /
  HISTORICAL_BACKFILL plus horizon health) is the exact next action and must
  not auto-start in this closeout. Horizon remains 2026-07-31 because the
  queue is still oldest-first; that is W2's job, not a W1 defect.
rationale: >
  Sol accepted head 3ba55c6d6877 and #6044 merged as ec388d963190. The first
  natural 22:30Z daily whose collect event SHA contains that merge is run
  32426513915. Collect retrieved real SEC bytes through W1/W1A/W1B code;
  199 complete submissions and 531 children were appended as one closed-bundle
  generation; children are coordinate-bound; historical occurrence+bytes kept
  stable evidence_ids; the compiler emitted 199 new events, 0 corrections, 0
  compile failures; document terms, projection, and health share compiler
  as_of 2026-08-21T01:25:35Z; latest.json is byte-identical to projection.json;
  prophet_authority remains false; the whole-generation append-only fence
  checked origin/main and published. No second daily was dispatched.
  DEC:CS-V2-W1B-SOL-ACCEPTED-NATURAL-PROOF-GATE required exactly this receipt
  before W1B could close.
supersedes:
  - DEC:CS-V2-W1B-SOL-ACCEPTED-NATURAL-PROOF-GATE
alternatives:
  - option: Keep W1B in_progress until a later nightly whose overall workflow is green
    why_not: >
      Collect and capital_structure already succeeded and published. Waiting on
      an unrelated cancelled later job would leave a proven chain unrecorded.
  - option: Start W2 implementation in the same closeout
    why_not: >
      Sol ordered return after proof and explicitly forbade beginning W2 in
      this closeout.
  - option: Dispatch another daily because the 22:30 run later cancelled
    why_not: >
      The accepted contract forbids a second daily. The CS jobs on that run
      already completed.
evidence:
  - "GitHub Actions run 32426513915 collect job 96609474282 / capital_structure job 96637756516"
  - "event SHA 50577f18c5fb is a descendant of merge ec388d963190"
  - "data/capital_structure generation 3ba28993b741"
  - "DSC:CS-V2-W1B-NATURAL-CHAIN-PROVEN-LIVE"
affects:
  - WS:CAPITAL-STRUCTURE-INTELLIGENCE-V2
  - DEC:CS-V2-W1B-SOL-ACCEPTED-NATURAL-PROOF-GATE
confidence: high
reversibility: easy
decided_by: cursor-grok-4.6
decided_at: 2026-08-21
---

This record closes the W1 production-proof hold. It does not commission W2.
