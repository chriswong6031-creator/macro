---
key: BIOCATALYST-RECOVERY-V2
title: BioCatalyst Recovery V2 — production hydration recovery
objective: >
  Restore the existing paid BioCatalyst product to a truthful, usable production
  journey before any post-P0 parity, alpha, asymmetry or Prophet expansion. Done for
  the recovery program = the production authenticated BioCatalyst journey reads one
  valid current generation within the serving budget, paints typed locked/empty/
  source_outage/integrity states correctly, and passes real entitled browser/API
  acceptance without weakening source, provenance, integrity or soak law.
status: active
program: biocatalyst
repos: [macro]
owner: coo-fable
class: build
blast_radius: user_facing
ambiguity: specified
owns_paths:
  - research/biocatalyst_recovery_v2/**
  - app/biocatalyst.py
  - engine/biocatalyst/**
  - templates/biocatalyst.js
  - site/biocatalyst.js
  - tests/test_biocatalyst_api.py
  - tests/test_biocatalyst_security.py
waves:
  - id: V2-FREEZE
    title: Recovery V2 masterplan and PR-by-PR execution law
    status: done
    pr: 5788
    next_action: >
      Done. The eight-part repository masterplan is canonical. Do not replace it
      with a new recovery architecture while P0 remains open.
  - id: P0-A
    title: Production caller-binding repair
    status: done
    pr: 5793
    depends_on: [V2-FREEZE]
    next_action: >
      Done. Production-shaped authenticated identity binds to the stable user id
      after site_full enforcement; incidental display tier is not authority.
  - id: P0-B
    title: Deployment restart-path decoupling
    status: done
    pr: 5804
    depends_on: [P0-A]
    next_action: >
      Done. The normal updater can perform the verified macro-api restart before an
      unrelated Market Memory owner-replay failure; this workstream does not own the
      shared deploy control plane and must not widen that change.
  - id: P0-C1
    title: Typed client hydration states
    status: done
    pr: 5810
    depends_on: [P0-B]
    next_action: >
      Done. locked / empty / source_outage / integrity_block / normal remain distinct;
      strict payload validators were not weakened. P0 remained incomplete.
  - id: P0-C2-DIAG
    title: Entitled generation-read failure isolation and causal profile
    status: done
    pr: [5906, 5927]
    depends_on: [P0-C1]
    next_action: >
      Done. Entitlement completed; pointer-bound _read_bundle routes timed out. The
      profile identified deep validation amplification rather than auth as the
      primary serving-path mechanism.
  - id: P0-C2R1
    title: Request-local single-generation validation seam
    status: done
    pr: 5934
    depends_on: [P0-C2-DIAG]
    next_action: >
      Done/merged. One logical product-bundle read performs one generation load and
      remains request-local; no process-lifetime cross-request cache was introduced.
  - id: P0-C2R2
    title: Retain admitted generation artifacts request-locally
    status: done
    pr: 6052
    depends_on: [P0-C2R1]
    next_action: >
      Separately adjudicated PASS by a Chairman/Sol-commissioned COO review on
      2026-08-20. The author hold was released, exact repair accepted, required CI/
      fences completed, and #6052 merged as 427d676de1a3ba086e4b63480018ecd733dd666e.
      Do not reopen a ContractRegistry/bootstrap optimization before production proof.
  - id: P0-C2-PROD-ACCEPT
    title: Entitled production hydration acceptance
    status: todo
    depends_on: [P0-C2R2]
    next_action: >
      Deploy the merged #6052 repair through the normal macro-update path so the
      engine/biocatalyst/*.py change restarts the real macro-api process. Then run the
      real entitled P0-C2 browser/API acceptance across health, Trial Screen, facets,
      milestones, Change Tape, first-seen/prospective state and dossier. Capture the
      served process/commit identity, route timings, typed failure states, browser
      paint and console/network errors. A local or pre-deploy timing result is not
      acceptance. If production still fails or 524s, stop and return with the first
      failing edge; do not start P1 or a speculative bootstrap/ContractRegistry PR.
decisions:
  - DEC:BIOCATALYST-RECOVERY-V2-CORE-NOT-JV-OR-BCI
discoveries: []
landmines:
  - >-
    The B1S2c / launch-SLO source experiment, source roster, collector cadence,
    fixed-cohort membership, freshness budget and related activation law are an
    independent truth program. Serving recovery must not mutate collectors/biocatalyst,
    scripts/biocatalyst_worker.py or source/launch registries merely to make P0 green.
  - >-
    WS:BPC-JV-RECON is a separate finite JV snapshot archaeology/onboarding program.
    It is not the owner of core BioCatalyst production hydration and must not be used
    as a catch-all for this recovery chain.
  - >-
    Draft PR #5821 / Biopharma Cycle Intelligence is not merged authority for core
    recovery. Even its proposed federation preserves BioCatalyst clinical/regulatory
    truth and independent production recovery. Do not absorb P0 into BCI.
  - >-
    Do not print, persist, commit or reconstruct bearer/JWT/session credentials while
    proving entitled production. Use an existing authorized browser/operator session
    and record only bounded status/receipt facts.
  - >-
    A faster local/off-process read is not production acceptance. Edge timeout,
    deployed process identity, authenticated request behavior and actual browser paint
    must be proven on the live path.
  - >-
    No process-lifetime or cross-request cache may silently replace per-read integrity
    proof without a separate architecture/security ruling.
  - >-
    The #6052 hold was a review barrier and has been explicitly released by a separate
    commissioned review. Do not resurrect that stale hold; the current gate is real
    production acceptance. Equally, merge/review PASS is not production acceptance.
do_not_redo:
  - "Do not redo the P0-A user-id vs display-tier caller-binding diagnosis; #5793 settled it."
  - "Do not redo why unrelated W2C owner replay stranded app/*.py restarts; #5804 settled the deployment ordering repair."
  - "Do not collapse client integrity mismatch into source outage; #5810 made the failure classes explicit."
  - "Do not reopen the entitlement-vs-generation discriminator; #5906 proved entitlement completed before the timed-out generation read."
  - "Do not redo the R0 deep-validation amplification profile; #5927 recorded the causal serving cost."
  - "Do not treat #5934 or #6052 merge as P0 production acceptance; the real entitled deployed journey is still owed."
  - "Do not restart a ContractRegistry/bootstrap optimization before proving the accepted #6052 path in production."
  - "Do not start parity/alpha/asymmetry/Prophet expansion while core P0 hydration remains unaccepted."
artifacts:
  - research/biocatalyst_recovery_v2/README.md
  - research/biocatalyst_recovery_v2/BIOCATALYST_RECOVERY_AND_ALPHA_ENGINE_MASTERPLAN_V2_PART_01.md
  - research/biocatalyst_recovery_v2/BIOCATALYST_RECOVERY_AND_ALPHA_ENGINE_MASTERPLAN_V2_PART_02.md
  - research/biocatalyst_recovery_v2/BIOCATALYST_RECOVERY_AND_ALPHA_ENGINE_MASTERPLAN_V2_PART_03.md
  - research/biocatalyst_recovery_v2/BIOCATALYST_RECOVERY_AND_ALPHA_ENGINE_MASTERPLAN_V2_PART_04.md
  - research/biocatalyst_recovery_v2/BIOCATALYST_RECOVERY_AND_ALPHA_ENGINE_MASTERPLAN_V2_PART_05.md
  - research/biocatalyst_recovery_v2/BIOCATALYST_RECOVERY_AND_ALPHA_ENGINE_MASTERPLAN_V2_PART_06.md
  - research/biocatalyst_recovery_v2/BIOCATALYST_RECOVERY_AND_ALPHA_ENGINE_MASTERPLAN_V2_PART_07.md
  - research/biocatalyst_recovery_v2/BIOCATALYST_RECOVERY_AND_ALPHA_ENGINE_MASTERPLAN_V2_PART_08.md
next_action: >
  Finish P0 through production proof: deploy merged #6052 via the normal macro-update
  path, verify the served macro-api process/commit, then immediately run the real entitled
  P0-C2 browser/API acceptance. If it passes, record the production receipt and only then
  adjudicate post-P0 continuation. If it fails, stop on the first causal edge. Do not start
  P1, ContractRegistry/bootstrap work, parity, alpha, asymmetry or Prophet first.
---

## Context

The Recovery V2 program existed and executed for several days without an Agent OS workstream
row. That work-identity gap caused Linear to mis-map P0-C2R2 execution to the unrelated BPC JV
snapshot workstream. This record repairs organizational identity and preserves the latest exact
execution state; it does not create a new product, source plane or post-P0 authority.

## Recovery chain at identity repair landing

- #5788 — canonical V2 masterplan merged.
- #5793 — P0-A caller binding merged.
- #5804 — shared deploy restart ordering repair merged.
- #5810 — P0-C1 typed hydration states merged.
- #5906 — entitled P0-C2 generation-read hang evidence merged.
- #5927 — R0 deep-validation amplification profile merged.
- #5934 — R1 request-local single-generation-load repair merged.
- #6052 — R2 retained-artifact repair separately reviewed PASS and merged as
  `427d676de1a3ba086e4b63480018ecd733dd666e`.

The next product capability owed is the same one the program always targeted: a real authenticated
production BioCatalyst journey that works truthfully and quickly enough on the served path. The
new workstream makes that obligation durable and correctly owned; it does not convert merged code
into production acceptance.
