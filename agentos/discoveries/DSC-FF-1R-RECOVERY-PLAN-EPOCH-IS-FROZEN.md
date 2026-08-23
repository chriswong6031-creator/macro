---
key: FF-1R-RECOVERY-PLAN-EPOCH-IS-FROZEN
claim: >
  FF-1R can remain deterministic while mainline current-quarter processing
  continues only if the recovery candidate population is derived once from the
  sha-verified latest-complete anchor and its indexed relevant-set snapshot;
  later current-quarter index movement is provenance, not a change to that
  recovery plan.
falsifier: >
  Inspect engine/fundamental_forensics/broad_sec_store.py:_build_recovery_plan,
  _verify_recovery_plan, _load_continuation and _run_recovery_poll; this claim
  is disproved if a resumed recovery obtains a new master index or accepts a
  changed anchor/index/relevant-set/candidate digest before issuer network
  acquisition.
so_what: >
  Future recovery work must retain the plan digest and compact cursor, reject
  anchor or plan mismatch before SEC/R2 mutation, and compose only the final
  backlog-zero recovery result against the then-current latest-complete state.
  Do not implement recovery as a mutable current-index chase or treat an
  intermediate tranche as latest-complete.
kind: architecture
verified_at: 2026-08-22
verified_by: >
  rg -n "_build_recovery_plan|_verify_recovery_plan|_load_continuation|_run_recovery_poll"
  engine/fundamental_forensics/broad_sec_store.py; local implementation review.
scope:
  - macro
  - fundamental-forensics
  - engine/fundamental_forensics/broad_sec_store.py
confidence: verified
---

The plan epoch is part of recovery identity. It is not a second mutable
authority: latest-complete remains the sole complete-state pointer, and the
plan is an immutable receipt-derived artifact.
