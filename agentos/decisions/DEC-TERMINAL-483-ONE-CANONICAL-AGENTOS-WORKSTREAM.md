---
key: TERMINAL-483-ONE-CANONICAL-AGENTOS-WORKSTREAM
question: Which Agent OS workstream owns Terminal GitHub issue #483 after concurrent records created two active identities for the same program?
answer: >
  WS:TERMINAL-GITHUB-CANONICALIZATION is the sole active durable Agent OS workstream for
  mastermindx-market-intelligence/mastermind-terminal#483. WS:TERMINAL-GITHUB-CANONICAL-DEPLOYMENT
  is parked as a historical compatibility redirect and must not receive independent work, Linear
  Project identity, Initiative membership, lifecycle state or continuation authority.
rationale: >
  Both records identify the same Chairman program, the same canonical operation and the same GitHub
  issue #483, and their outcomes substantially overlap. The canonicalization record carries the
  newer six-wave frontier, governing decision, production discovery, current handoffs and exact
  implementation carriers; the deployment record is an earlier, shallower snapshot. Keeping both
  active would duplicate organizational identity, make the Agent OS Project compiler and Linear
  portfolio count one program twice, and force future sessions to choose between contradictory next
  actions. Parking rather than deleting the older record preserves provenance and old links without
  creating a second execution or memory plane.
alternatives:
  - option: Keep both records active and assign them to the same Initiative.
    why_not: >
      That preserves a duplicate Project/workstream identity and makes one program consume two
      portfolio slots. Shared Initiative membership does not reconcile lifecycle or next-action authority.
  - option: Keep both records active but place deployment beneath canonicalization as a dependency.
    why_not: >
      The records are not independent bodies of work: both claim the same operation and GitHub
      carrier and overlap across source audit, deployment, repository authority and production proof.
      A dependency edge would disguise rather than remove the duplicate authority.
  - option: Delete WS:TERMINAL-GITHUB-CANONICAL-DEPLOYMENT.
    why_not: >
      Deletion would break historical links and erase the present explanation for how the duplicate
      arose. A parked redirect is sufficient and correction-safe.
evidence:
  - "Macro PR #6674 created WS:TERMINAL-GITHUB-CANONICAL-DEPLOYMENT and merged as acd1d79ab575007ed7e3485e14d47ae804a28ecb."
  - "Macro PR #6681 created WS:TERMINAL-GITHUB-CANONICALIZATION and merged as 1240c0da32ee5232677df8ef9819f413e0b187da about ten seconds later."
  - "Both records name mastermindx-market-intelligence/mastermind-terminal#483 as the canonical carrier and deny creating a second operation."
  - "WS:TERMINAL-GITHUB-CANONICALIZATION contains six current waves, DEC:TERMINAL-GITHUB-OWNS-IMPLEMENTATION-TRUTH, DSC:TERMINAL-PRODUCTION-SOURCE-CLEAN-PLAIN-COPY and dated continuation handoffs; the deployment record contains only the earlier five-wave snapshot."
  - "The deterministic Linear Project compiler includes active workstreams and excludes parked workstreams; leaving both active invalidates the Initiative source census."
affects:
  - "WS:TERMINAL-GITHUB-CANONICALIZATION"
  - "WS:TERMINAL-GITHUB-CANONICAL-DEPLOYMENT"
  - terminal-charting
  - agentos/workstreams/WS-TERMINAL-GITHUB-CANONICALIZATION.md
  - agentos/workstreams/WS-TERMINAL-GITHUB-CANONICAL-DEPLOYMENT.md
  - docs/superpowers/specs/2026-09-02-linear-initiative-portfolio-v1-current-epoch-source-consolidation.md
confidence: high
reversibility: easy
decided_by: ceo-sol
decided_at: 2026-09-02
---

## Consequences

1. All Terminal #483 continuation, evidence review and future Agent OS updates resolve through
   `WS:TERMINAL-GITHUB-CANONICALIZATION`.
2. The parked compatibility record remains searchable and preserves its Git provenance, but the
   Project compiler and Linear Initiative plan exclude it.
3. No Terminal implementation, GitHub issue, runtime Job, deployment controller, queue or history is
   copied or migrated. This is an organizational identity correction only.
4. The Linear Initiative source must be regenerated from a fresh post-merge Agent OS census; it may
   classify the canonical workstream once and must never compensate for the duplicate by mapping both.
5. A later session may reverse this ruling only with new evidence that the records own genuinely
   independent operations, carriers and observable outcomes. Title differences alone are insufficient.
