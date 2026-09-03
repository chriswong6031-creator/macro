---
key: TERMINAL-GITHUB-CANONICALIZATION-IS-SOLE-WORKSTREAM
question: >
  Which Agent OS workstream is canonical for Terminal GitHub source, deployment and
  repository reliability after Macro PRs #6674 and #6681 created parallel records for the
  same Terminal issue #483?
answer: >
  WS:TERMINAL-GITHUB-CANONICALIZATION is the sole active organizational workstream.
  WS:TERMINAL-GITHUB-CANONICAL-DEPLOYMENT is retained only as a parked compatibility
  tombstone and has no independent portfolio, execution, deployment or release authority.
rationale: >
  Both records name program terminal-charting, owner ceo-sol, the same canonical GitHub
  issue #483 and substantially the same outcome. The canonicalization record is the
  complete surviving owner: it carries the accepted source-authority decision, production
  topology discovery, two continuation handoffs and the current six-wave frontier. Keeping
  both active would double-count one organizational program in the deterministic Project
  compiler and force a false extra Initiative membership. Deleting the earlier record would
  conceal the correction lineage. Parking it preserves historical identity while restoring
  one canonical workstream.
alternatives:
  - option: Keep both workstreams active and assign both to the same Initiative
    why_not: >
      This legitimizes a duplicate organizational identity and makes portfolio counts depend
      on an accidental pair of path-disjoint records PRs.
  - option: Delete WS:TERMINAL-GITHUB-CANONICAL-DEPLOYMENT
    why_not: >
      Deletion hides the historical alias and makes older links and receipts harder to
      reconcile. A parked tombstone is correction-safe and reversible.
  - option: Park the canonicalization record and continue the deployment record
    why_not: >
      The deployment record lacks the governing decision, discovery, continuation handoffs
      and current program frontier already attached to the canonicalization identity.
evidence:
  - "Macro PR #6674 merged acd1d79ab575007ed7e3485e14d47ae804a28ecb from base 3738980971dfc5268796b533e165f4c605b9201f and created only WS-TERMINAL-GITHUB-CANONICAL-DEPLOYMENT for Terminal issue #483."
  - "Macro PR #6681 merged 1240c0da32ee5232677df8ef9819f413e0b187da ten seconds later from the same base and created WS-TERMINAL-GITHUB-CANONICALIZATION plus DEC, DSC and two handoffs for the same issue #483."
  - "Current Macro main dae473ed625e1e1a8a8bfb273ed7b5199c703fac contains both records as status active."
  - "Default-branch code search found the deployment key only in its own file; the canonicalization key is referenced by its workstream, governing decision and continuation handoffs."
  - "Fresh open-PR searches found no current writer touching either workstream identity."
affects:
  - WS:TERMINAL-GITHUB-CANONICAL-DEPLOYMENT
  - WS:TERMINAL-GITHUB-CANONICALIZATION
  - terminal-charting
  - agentos/workstreams/WS-TERMINAL-GITHUB-CANONICAL-DEPLOYMENT.md
  - agentos/workstreams/WS-TERMINAL-GITHUB-CANONICALIZATION.md
  - mastermind-project-workroom-fabric-20260829-sol-001
confidence: high
reversibility: easy
decided_by: ceo-sol
decided_at: 2026-09-02
---

# Sole Terminal GitHub organizational identity

This decision changes organizational projection only. It does not merge GitHub carriers, alter
Terminal source, modify production, create an Executive operation, or grant any deployment,
review, release or Initiative-apply authority.
