---
key: FF-1R-BOUNDED-JULY-RECOVERY
question: >
  How may the separately commissioned July recovery acquire missed FF-1
  evidence without turning the 2,541-CIK July candidate population into an
  unbounded issuer crawl or changing current-quarter incremental authority?
answer: >
  Freeze one immutable FF-1R plan from the sha-verified latest-complete anchor
  at recovery_from=2026-07-12T11:23:15Z. The plan binds the anchor receipt,
  canonical universe, EDGAR index snapshot, relevant-set identity and a
  deterministic candidate sequence before any per-issuer network call.
  Advance only a compact cursor through tranches of at most 64 selected CIKs.
  Fetch current Submissions only for those selected CIKs; request historical
  filings.files shards only when their declared date span can contain a planned
  accession, subject to per-issuer, per-run and byte bounds. Preserve the
  current incremental plane: partial recovery never advances latest-complete;
  only a backlog-zero final composition may do so, retaining newer incremental
  evidence and the maximum source clock.
rationale: >
  The live Q3 canary's 2,560 relevant July rows map to 2,541 canonical CIKs,
  far beyond a lawful one-run issuer fanout. Selecting the complete candidate
  set first makes a run's external authority proportional and auditable. A
  digest-bound plan and compact cursor make retries deterministic without
  persisting a second queue or a giant pending list. The recovered evidence can
  be older than the P2R baseline, so publishing an intermediate partial state
  as latest-complete would make a later current incremental snapshot disappear;
  a final composition against current latest-complete is required to retain
  monotonic issuer evidence. This is a recovery capability only, not a prior
  authorization for FF-1R production, previous-quarter reconciliation or FF-2.
alternatives:
  - option: Fetch Submissions for every July candidate and choose Company Facts later
    why_not: It recreates the rejected 8-to-5-to-2 fanout shape at 2,541 CIKs and cannot establish bounded proportional authority.
  - option: Rebuild the candidate population from the live master index on each tranche
    why_not: Mutable current-quarter rows would alter the recovery target and defeat retry identity.
  - option: Publish partial recovery output as latest-complete
    why_not: A partial older recovery snapshot can hide newer current-incremental evidence and falsely declare the backlog complete.
  - option: Add a recovery queue, latest pointer, or all-historical-shard scan
    why_not: These are separate control/data planes or unbounded transports outside the commissioned capability.
evidence:
  - DEC:FF-1-RECOVERY-NOT-COMMISSIONED
  - DSC:FF-1-Q3-2026-MASTER-INDEX-CANARY
  - DSC:FF-1R-RECOVERY-PLAN-EPOCH-IS-FROZEN
  - "engine/fundamental_forensics/broad_sec_store.py:_build_recovery_plan, _load_continuation, _run_recovery_poll"
  - "collectors/edgar_forensics.py:SecForensicsCollector.retrieve_historical_submissions_file"
  - "tests/test_fundamental_forensics_broad_sec.py recovery-plan and bounded-tranche cases"
affects:
  - WS:FUNDAMENTAL-FORENSICS
  - engine/fundamental_forensics/broad_sec_store.py
  - collectors/edgar_forensics.py
  - scripts/run_fundamental_forensics_broad_sec.py
  - .github/workflows/filing-forensics-broad-sec.yml
  - contracts/fundamental_forensics_broad_sec_run.schema.json
  - contracts/fundamental_forensics_broad_sec_recovery_plan.schema.json
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-22
supersedes:
  - DEC:FF-1-RECOVERY-NOT-COMMISSIONED
---

This successor implements the separate commission that the prior decision
required. It does not assert production commissioning: the capability is
BUILT_NOT_PROVEN / HOLD-FOR-SOL until exact-head review, required CI and an
explicit Sol release. Previous-quarter weekly reconciliation remains SPEC_ONLY
/ NOT_BUILT. FF-2 remains forbidden.
