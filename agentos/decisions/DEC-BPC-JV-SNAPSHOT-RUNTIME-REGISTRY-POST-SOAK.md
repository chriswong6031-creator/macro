---
key: BPC-JV-SNAPSHOT-RUNTIME-REGISTRY-POST-SOAK
question: >
  May PR #5909 insert biopharmcatalyst_jv_snapshot into the live
  config/biocatalyst_sources.yml and add machine-enforced source-registry tests
  that require that identity while the launch SLO manifest is soak_scheduled?
answer: >
  No. Canonical source identity biopharmcatalyst_jv_snapshot is frozen now in
  the RECON-0 architecture (freeze, DECs, WS:BPC-JV-RECON). Runtime registry
  insertion and its machine-enforced source-registry tests must land through
  the post-soak successor source-registry / successor launch-manifest
  transition. They may not mutate the hash-bound predecessor registry during
  the active soak. The launch-SLO guard that binds
  config/biocatalyst_launch_slo_manifest.yml source_registry_sha256 to the
  predecessor registry bytes is correct. Do not update or re-hash the active
  launch manifest, change its source_registry_sha256, alter the
  2026-08-12→2026-08-26 soak, modify fixed-cohort / launch fixtures to follow
  a new source, or weaken the verifier to hash only launch-critical sources.
  This is a sequencing correction, not a rejection of the accepted BPC JV
  rights architecture.
rationale: >
  Semantic CI on #5909 found a direct pr_regression because the PR mutated
  config/biocatalyst_sources.yml while the soak_scheduled launch manifest still
  pins those exact predecessor bytes. Inserting the accepted identity into the
  live registry during soak would force either a false SLO failure or a soak
  reopen (re-hash, fixture chase, or a weakened verifier). Rights and identity
  stay accepted; only the registration moment moves to the successor transition.
alternatives:
  - option: Keep the live YAML row and re-hash the active launch manifest
    why_not: >
      Sol forbade updating or re-hashing the active launch manifest and forbade
      changing source_registry_sha256 during the soak.
  - option: Weaken the verifier to hash only launch-critical sources
    why_not: >
      The guard is correct. Narrowing the hash would hide exactly the soak-bound
      contract the SLO exists to hold.
  - option: Treat the SLO miss as a rejection of Chairman-confirmed JV rights
    why_not: >
      Rights, distinct identity, corpus laws, and temporal laws remain accepted.
      Only runtime registration is deferred.
evidence:
  - "config/biocatalyst_launch_slo_manifest.yml state soak_scheduled binds source_registry_sha256"
  - "PR #5909 Sol CI RULING soak-safe freeze 2026-08-19"
  - "research/BPC_RECON_0_JV_SNAPSHOT_ARCHAEOLOGY_AND_SOURCE_SYSTEM_RECONSTRUCTION_FREEZE_2026-08-18.md §2 and §14"
  - "DEC:BPC-JV-SNAPSHOT-IS-NOT-BENCHMARK"
  - "DEC:BPC-JV-FINITE-SNAPSHOT-RIGHTS-CHAIRMAN"
affects:
  - "WS:BPC-JV-RECON"
  - "biocatalyst"
  - "config/biocatalyst_sources.yml"
  - "config/biocatalyst_launch_slo_manifest.yml"
confidence: high
reversibility: easy
decided_by: ceo-sol
decided_at: 2026-08-19
---

## Grounds

The soak-bound predecessor registry is an execution lock, not an architecture
lock. Architecture names `biopharmcatalyst_jv_snapshot` now. The live YAML
gains that row only when a successor source-registry and successor launch
manifest move together after soak.

## What would reopen this

Soak end plus an explicit successor-registry / successor-manifest PR that
inserts the frozen identity and its tests. Re-hashing the active soak
manifest, or putting the row back into the predecessor registry before that
transition, would not.
