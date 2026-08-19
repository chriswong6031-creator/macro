---
key: FF-1-RECOVERY-NOT-COMMISSIONED
question: >
  Does PR #5898 own July recovery execution now that index-driven current-quarter
  discovery is the accepted broad FF-1 plane?
answer: >
  No. #5898 fail-closes mode=recovery with reason_code recovery_plan_required
  before any EDGAR index, Submissions, or Company Facts network call and before
  any Research R2 mutation. FF-1R (July recovery engine) is the next separate
  capability, and only after #5898 is merged and its production incremental
  baseline is proven. Do not start FF-1R now. Do not claim #5898 implements
  July recovery.
rationale: >
  The live Q3 2026 master-index canary measured 2560 relevant rows / 2541 unique
  canonical CIKs with filed_on >= 2026-07-12. The unmerged recovery path fetched
  Submissions for every pending CIK before selecting Company Facts, which at
  that population would re-fetch thousands of Submissions across continuation
  runs. Sol accepted the discovery architecture and blocked merge until recovery
  was removed from this PR's claim. Current-quarter discovery remains
  independently useful.
alternatives:
  - option: Keep bounded-tranche recovery execution in #5898
    why_not: Tests proved 8 then 5 then 2 Submissions fetches; that shape does not scale to 2541 CIKs.
  - option: Start FF-1R in the same PR
    why_not: Sol ordered discovery-plane-only repair and explicit fail-close until a later commissioning.
  - option: Delete the workflow_dispatch recovery option
    why_not: The contract must not silently disappear; dispatch still exists and fail-closes.
evidence:
  - DSC:FF-1-Q3-2026-MASTER-INDEX-CANARY
  - "Sol review of 65cd21f: architecture PASS, merge BLOCKED; recovery not acceptable for 2541 CIKs."
  - "Live July recovery index candidates: 2560 rows / 2541 unique CIKs."
affects:
  - WS:FUNDAMENTAL-FORENSICS
  - engine/fundamental_forensics/broad_sec_store.py
  - scripts/run_fundamental_forensics_broad_sec.py
  - .github/workflows/filing-forensics-broad-sec.yml
  - contracts/fundamental_forensics_broad_sec_run.schema.json
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-19
---

Index-driven discovery stays. Recovery execution is NOT_BUILT / NOT_COMMISSIONED
under FF-1R. Previous-quarter weekly reconciliation remains SPEC_ONLY / NOT_BUILT.
FF-2 remains forbidden.
