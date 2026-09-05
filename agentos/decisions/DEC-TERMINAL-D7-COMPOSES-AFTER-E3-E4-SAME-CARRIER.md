---
key: TERMINAL-D7-COMPOSES-AFTER-E3-E4-SAME-CARRIER
question: >
  What is the disposition of Terminal PR #435 (D7 billing fail-closed), which is
  semantically correct but stale and collides with PR #445 on OnboardingSheet.tsx?
answer: >
  Preserve #435 as the sole D7 carrier — never create a sibling PR. Settle #444 (E-3)
  then #445 (E-4) first; then compose #435 onto their accepted descendant so
  billingTrialStarted requires a non-null verified trial_end AND invalidates the
  canonical entitlement store, and the existing #445 billingAlreadyActive() invalidation
  remains. Rerun the exact targeted tests and all required Terminal checks; merge only
  with an expected-head guard. Do not absorb unrelated repair work into #435.
rationale: >
  Both semantics are required and they touch the same function: D7's verified-receipt
  gate without E-4's invalidation leaves a stale entitlement cache after a genuine
  trial; E-4 without D7 lets a malformed 2xx declare a trial. One logical repair on one
  carrier is house law (one-operation-one-PR); a sibling PR would fork review history
  and guarantee a conflicting double-fix of one gate. Sequencing E-3 → E-4 → D7 follows
  the dependency direction: the canonical store must exist before its invalidation
  semantics, which must exist before D7 composes with them.
alternatives:
  - option: Merge #435 unchanged now and fix the composition later
    why_not: >
      It conflicts semantically with #445 on the same function; merging first forces
      #445 into a rebase that re-litigates D7, and the interim master state would have
      the verified-receipt gate without cache invalidation.
  - option: Close #435 and reimplement D7 inside #445
    why_not: >
      Destroys the existing carrier's review history and violates
      one-logical-operation-one-carrier; #445's charter is freshness, not billing
      receipts.
  - option: Merge all three simultaneously via a stacked mega-branch
    why_not: >
      Removes the per-carrier CI and review gates; a single red check would block all
      three semantics at once.
evidence:
  - "gh pr view 435/444/445 -R mastermindx-market-intelligence/mastermind-terminal (2026-09-04): all OPEN, MERGEABLE; #444 merge-base efb5dab (behind 1), #445 based on current master fadd8b82, #435 merge-base efb5dab (behind 1)"
  - research/commercial_activation/PROJECT_SOL_RETURN_V1_COMMERCIAL_ACTIVATION_20260903.md §2.4 (Terminal collision analysis with the exact composed function body)
  - "2026-09-04 census: required check 'Terminal typecheck + tests' is red on ALL current Terminal PR branches including disjoint lanes — a repo-wide e2e health problem that gates this sequence and is its own repair operation, not part of any of the three carriers"
affects:
  - "WS:COMMERCIAL-ACTIVATION"
  - "WS:ACCOUNT-IDENTITY-HARDENING"
  - terminal/components/onboarding/OnboardingSheet.tsx
confidence: high
reversibility: easy
decided_by: chairman
decided_at: 2026-09-04
---

Ratified by direct Chairman grant to session claude/mmx-commercial-activation-03fe73 on
2026-09-04. The repo-wide e2e CI repair is a separate carrier
(sol/terminal-ci-e2e-health-restore-20260904); none of #435/#444/#445 may absorb it.
