---
key: MARKET-OS-A1A-MERGED-PRODUCTION-ACCEPTANCE-REQUIRED
question: >
  After Macro PR #6098 merged the A1A Portfolio Population Truth + State
  Authority implementation, should WS:MARKET-OS mark A1A done and open A1B,
  or preserve a separate production-acceptance boundary?
answer: >
  Preserve the boundary. Record #6098 as the merged A1A implementation, but
  keep A1A in_progress / BUILT_NOT_PROVEN until two bounded defects are repaired
  and the complete real-cloud production journey passes: truthful
  insufficient-comparison copy for single-position/cross-book states; removal
  of stale Watchlist-derived Risk Center state after a same-session switch to
  Portfolio; then real authenticated cloud, failure-state, account-transition,
  write/readback and Macro/Terminal conformance proof. A1B Fast Start Import
  remains unauthorized until Sol separately accepts A1A in production.
rationale: >
  #6098 created an independently useful deterministic state-authority seam and
  closed the principal population/fail-open defects: Portfolio membership is no
  longer the Watchlist union, temporary paste stays unsaved, authenticated cloud
  authority cannot fall through to anonymous local state, last-good cloud rows
  are read-only/degraded, save states are separated, mixed sizing and mixed
  basis abstain, and no cluster is invented. The PR also underwent an
  adversarial repair round. But its own return explicitly withheld production
  acceptance and named two user-facing defects. One copy path mislabels an
  insufficient same-book comparison as mixed sizing; a separate Risk Center
  consumer can retain Watchlist-derived percentages after the active authority
  changes to an empty Portfolio. Both violate the promised end state even though
  the core owner is repaired. Green CI and merge therefore prove implementation,
  not the complete product journey. Opening A1B before these are production-
  proven would add a canonical position writer onto a surface that can still
  misstate the active Portfolio.
alternatives:
  - option: Mark A1A done because #6098 merged and its local matrix was broad
    why_not: >
      The PR explicitly says real Supabase/cloud production round-trip was not
      done, and it records the stale cross-mode Risk Center state. Merge is not
      proof that the primary persona completes the task on the served product.
  - option: Treat the two findings as unrelated polish and open A1B now
    why_not: >
      The stale risk state is a direct population-authority violation, not
      polish. The false reason copy is lower blast radius but still makes a
      truthful abstention read as a different factual defect. A1B would magnify
      both by making population changes easier before the reader is trusted.
  - option: Reopen the entire Market OS architecture or rebuild Portfolio state
    why_not: >
      #6098's accepted core is the canonical seam. The remaining work is two
      bounded consumers plus production proof; another store/state machine would
      create the duplicate plane the architecture forbids.
  - option: Authorize A1B conditionally while production proof accrues
    why_not: >
      DEC:MARKET-OS-PORTFOLIO-TRUTH-PRECEDES-FAST-IMPORT makes A1A acceptance a
      hard dependency. Conditional overlap would convert a truth gate into a
      schedule preference and make failures harder to attribute.
evidence:
  - "Macro PR #6098 merged: A1A Portfolio Population Truth + State Authority"
  - "PR #6098 return: production round-trip not done"
  - "PR #6098 gap: cross-book/single-position state can emit false mixed-sizing copy"
  - "PR #6098 gap: Watchlists→Portfolio same-session switch can retain stale Watchlist Risk Center percentages"
  - "research/market_os/MASTERMIND_MARKET_OS_ARCHITECTURE_FREEZE_AND_A1A_COMMISSIONING_2026-08-20.md"
  - "DEC:MARKET-OS-WATCHLIST-PORTFOLIO-SEPARATE-TRUTH-UNIFIED-EXPERIENCE"
  - "DEC:MARKET-OS-PORTFOLIO-TRUTH-PRECEDES-FAST-IMPORT"
affects:
  - WS:MARKET-OS
  - agentos/handoffs/MARKET-OS-2026-08-20-a1a-merge-reconciliation.md
confidence: high
reversibility: easy
decided_by: ceo-sol
decided_at: 2026-08-20
superseded_by: DEC:MARKET-OS-A1A-ACCEPTED-IN-PRODUCTION
---

## Authority consequence

This decision changes records and sequencing only. It does not modify runtime,
accept #6098 in production, authorize A1B, or widen any risk, signal, forecast,
rank, gate, size, trade or model authority.

The only lawful A1A continuation is:

1. repair the truthful insufficient-comparison reason/copy;
2. repair stale cross-mode Risk Center state;
3. execute the complete real production acceptance matrix;
4. return to Sol for A1A acceptance.

Only after that acceptance may A1B become eligible for a separate bounded
commission. It does not auto-start.

## Supersession note — 2026-08-23

This pre-proof decision remains the historical record for the repair and real-production
acceptance boundary. Those bounded repairs and the commissioned authenticated matrix later
passed. For A1A completion only, the successor acceptance decision supersedes this record's
unfinished-gate state and its broad account-transition production-proof clause: later,
more-specific Sol authorities explicitly prohibited sign-out/sign-in Scene 9 while retaining
the merged auth-generation protections and commissioning the remaining matrix. Sol accepted
that matrix without Scene 9. Any future identity-transition production test requires separate
authority and is not hidden A1A debt.
