---
workstream: WS:TERMINAL-GITHUB-CANONICALIZATION
session: sol/terminal-agentos-duplicate-reconcile-20260902
model: sol
ended_because: ci_handoff
mission: >
  Restore one canonical Agent OS identity for Terminal GitHub issue #483 so organizational
  continuation and the Linear Project compiler no longer treat one deployment/canonicalization
  program as two active workstreams.
state_before: >
  Macro main contained WS:TERMINAL-GITHUB-CANONICAL-DEPLOYMENT and
  WS:TERMINAL-GITHUB-CANONICALIZATION as separate active records. Both claimed the same canonical
  operation and mastermind-terminal#483 carrier. They landed through #6674 and #6681 about ten
  seconds apart, while the later canonicalization record carried the complete current six-wave
  frontier and the earlier deployment record retained stale W0 and next-action state.
changed:
  - path: agentos/workstreams/WS-TERMINAL-GITHUB-CANONICAL-DEPLOYMENT.md
    what: >
      Converted the earlier duplicate into a parked historical compatibility redirect, dropped its
      duplicate waves and routed every continuation to WS:TERMINAL-GITHUB-CANONICALIZATION.
  - path: agentos/decisions/DEC-TERMINAL-483-ONE-CANONICAL-AGENTOS-WORKSTREAM.md
    what: >
      Recorded the sole-owner ruling, alternatives, exact evidence and downstream Linear-census consequence.
  - path: agentos/handoffs/TERMINAL-GITHUB-CANONICALIZATION-2026-09-02.md
    what: >
      Added this bounded reconciliation handoff and the exact post-merge continuation sequence.
verified:
  - claim: Both active records identify the same canonical Terminal operation and GitHub carrier.
    command: >
      GitHub.fetch_file on agentos/workstreams/WS-TERMINAL-GITHUB-CANONICAL-DEPLOYMENT.md and
      agentos/workstreams/WS-TERMINAL-GITHUB-CANONICALIZATION.md at Macro@dae473ed625e1e1a8a8bfb273ed7b5199c703fac.
    result: >
      Both name mastermindx-market-intelligence/mastermind-terminal#483 as canonical and describe
      overlapping source-audit, exact-SHA deployment, repository authority and production-proof work.
  - claim: The duplicate records were introduced by near-concurrent independent PRs.
    command: >
      GitHub.fetch_issue and commit-history reads for Macro #6674/#6681 and paths
      agentos/workstreams/WS-TERMINAL-GITHUB-CANONICAL-DEPLOYMENT.md and
      agentos/workstreams/WS-TERMINAL-GITHUB-CANONICALIZATION.md.
    result: >
      #6674 merged as acd1d79ab575007ed7e3485e14d47ae804a28ecb at 2026-09-03T00:13:59Z;
      #6681 merged as 1240c0da32ee5232677df8ef9819f413e0b187da at 2026-09-03T00:14:09Z.
  - claim: The canonicalization record is the complete current durable owner.
    command: >
      GitHub.fetch_file agentos/workstreams/WS-TERMINAL-GITHUB-CANONICALIZATION.md at
      Macro@dae473ed625e1e1a8a8bfb273ed7b5199c703fac.
    result: >
      It contains W0-W5, current PR carriers, DEC:TERMINAL-GITHUB-OWNS-IMPLEMENTATION-TRUTH,
      DSC:TERMINAL-PRODUCTION-SOURCE-CLEAN-PLAIN-COPY, landmines, do-not-redo law and two dated handoffs.
  - claim: Parking the older record removes it from the deterministic Project-plan active set.
    command: >
      GitHub code read of scripts/linear_portfolio_plan.py and scripts/agentos.py on current Macro main.
    result: >
      The Project compiler includes active/blocked/awaiting_ci/awaiting_review and proposed records;
      parked is explicitly excluded and is a valid Agent OS workstream status.
unverified:
  - claim: The three-record candidate passes current Macro Agent OS and repository CI.
    what_would_verify: >
      Push the immutable branch head, let the normal exact-head fences and full semantic CI become
      terminal, and require the owning Agent OS validation pack plus aggregate gate to succeed.
  - claim: An independent reviewer agrees that no live Terminal responsibility was lost or split incorrectly.
    what_would_verify: >
      One non-author immutable-head review must verify exact same-carrier overlap, canonical record
      completeness, parked redirect semantics and absence of a hidden second workstream.
  - claim: The corrected Agent OS census is sufficient to freeze the next Linear Initiative epoch.
    what_would_verify: >
      After this correction lands on current Macro main, rerun the deterministic Project compiler
      against the complete direct workstream set and classify every newly eligible record exactly once.
unresolved:
  - The correction branch still requires terminal exact-head CI, independent review and Sol acceptance before merge.
  - The 58-row Linear Initiative source is stale and must be amended only after this Agent OS correction lands.
  - Current new active workstreams, including Flow Observatory V2, Code Intelligence Fabric and Executive Attention Economics, still require explicit Initiative classification in the next protected source epoch.
next_actions:
  - Run current exact-head Agent OS validation and full repository CI on the bounded three-path branch.
  - Obtain one non-author immutable-head review and merge only after current-main reconciliation remains path-disjoint.
  - Re-census current Macro main after merge and amend existing Mastermind PR #366 to the exact complete Initiative epoch rather than opening a competing source PR.
  - Update the existing Macro #6658 compiler to that protected epoch, then perform one bounded live Linear apply and exact readback.
do_not_redo:
  - Do not create another Terminal Agent OS workstream or new GitHub carrier for issue #483.
  - Do not delete the historical deployment record; keep it parked as the compatibility redirect.
  - Do not reactivate, assign a Linear Project to or map an Initiative membership for the parked duplicate.
  - Do not widen this organizational reconciliation into Terminal implementation, deployment, CI reliability or repository-setting work.
  - Do not merge or apply the stale 58-row Linear source merely because its own current-base CI passes.
danger_areas:
  - Parking the wrong record would discard the richer current six-wave frontier; canonicalization is the survivor.
  - A parked compatibility record must not retain in-progress/todo waves that appear executable.
  - Generated Agent OS state is compiler-owned and must not be hand-edited as part of this correction.
  - Macro main moves rapidly; use exact-path collision and history-preserving current-base reconciliation before release.
  - Linear is a projection. Do not hide Agent OS duplicates by assigning both records to one Initiative.
decisions:
  - DEC:TERMINAL-483-ONE-CANONICAL-AGENTOS-WORKSTREAM
---

## Continuation boundary

This correction changes organizational identity only. It creates no Terminal source change, deploy,
runtime lifecycle, Linear object or production proof. After it is protected, the next independent
capability is a fresh complete Initiative-source census, not more Terminal work under this carrier.
