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
status: done
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
      Done. The eight-part repository masterplan is canonical recovery history.
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
      Done. The normal updater can restart macro-api before unrelated Market Memory
      owner-replay failures; this workstream does not own the shared deploy plane.
  - id: P0-C1
    title: Typed client hydration states
    status: done
    pr: 5810
    depends_on: [P0-B]
    next_action: >
      Done. locked / empty / source_outage / integrity_block / normal remain distinct;
      strict payload validators were not weakened.
  - id: P0-C2-DIAG
    title: Entitled generation-read failure isolation and causal profile
    status: done
    pr: [5906, 5927]
    depends_on: [P0-C1]
    next_action: >
      Done. Entitlement completed before the timed-out pointer-bound product read; the
      causal profile isolated deep validation amplification rather than auth.
  - id: P0-C2R1
    title: Request-local single-generation validation seam
    status: done
    pr: 5934
    depends_on: [P0-C2-DIAG]
    next_action: >
      Done. One logical product-bundle read performs one generation load and remains
      request-local; no process-lifetime cross-request cache was introduced.
  - id: P0-C2R2
    title: Retain admitted generation artifacts request-locally
    status: done
    pr: 6052
    depends_on: [P0-C2R1]
    next_action: >
      Done. Separately adjudicated PASS by a Chairman/Sol-commissioned COO review;
      author hold released; #6052 merged as
      427d676de1a3ba086e4b63480018ecd733dd666e.
  - id: P0-C2-PROD-ACCEPT
    title: Entitled production hydration acceptance
    status: done
    pr: 6090
    depends_on: [P0-C2R2]
    next_action: >
      PASSED 2026-08-20. Macro #6090 records the real entitled production matrix on
      macro-api MainPID 2529475 serving #6052 commit 427d676de1a: health 200/fresh,
      Trial Screen 200 with four real NCT rows, facets 200, lawful empty milestones,
      Change Tape 200, lawful baseline_not_established prospective state, covered
      dossier 200, peer-set resolution 200, unsigned 401, invalid-sort 400, no 524 and
      no 5xx. Entitled product routes completed roughly 4.5-7.9s, inside the ~30s edge
      budget. This closes the recovery objective; it does not prove product parity.
decisions:
  - DEC:BIOCATALYST-RECOVERY-V2-CORE-NOT-JV-OR-BCI
discoveries: []
landmines:
  - >-
    The B1S2c / launch-SLO source experiment, source roster, collector cadence,
    fixed-cohort membership, freshness budget and related activation law are an
    independent truth program. Recovery completion does not transfer ownership of
    collectors/biocatalyst, scripts/biocatalyst_worker.py or source/launch registries.
  - >-
    WS:BPC-JV-RECON remains separate finite JV snapshot archaeology/onboarding. It is
    not the owner of core BioCatalyst product recovery or any future parity program.
  - >-
    Draft PR #5821 / Biopharma Cycle Intelligence remains non-authoritative for this
    recovery. Any future federation requires a separate Sol architecture ruling.
  - >-
    Do not print, persist, commit or reconstruct bearer/JWT/session credentials in
    future production proof. #6090 used an existing entitled browser session and
    recorded only bounded receipt facts.
  - >-
    No process-lifetime or cross-request cache may silently replace per-read integrity
    proof without a separate architecture/security ruling. P0 passed without one.
  - >-
    P0 hydration PROVEN_LIVE is not BioPharmCatalyst parity. The accepted production
    workbench remains the current ClinicalTrials.gov four-NCT cohort; broader truth,
    parity, alpha/asymmetry and Prophet integration are separate product decisions.
do_not_redo:
  - "Do not redo the P0-A user-id vs display-tier caller-binding diagnosis; #5793 settled it."
  - "Do not redo why unrelated W2C owner replay stranded app/*.py restarts; #5804 settled it."
  - "Do not collapse client integrity mismatch into source outage; #5810 settled the typed state split."
  - "Do not reopen the entitlement-vs-generation discriminator; #5906 proved entitlement completed before the timed-out generation read."
  - "Do not redo the R0 deep-validation amplification profile; #5927 recorded the causal serving cost."
  - "Do not call #5934/#6052 merge the proof; #6090 is the production acceptance receipt."
  - "Do not start a ContractRegistry/bootstrap optimization merely because it was once hypothesized; P0 passed without it."
  - "Do not extend this completed recovery workstream into parity/alpha/asymmetry/Prophet work; open a separately ruled continuation instead."
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
  - research/biocatalyst_recovery_v2/P0_C2R2_PRODUCTION_ACCEPTANCE_2026-08-20.md
next_action: >
  Recovery program complete. Preserve #6090 as the production proof and close this
  workstream rather than using it as an implementation catch-all. Post-P0 continuation
  is a separate Sol CEO adjudication (Linear MAS-74): recover the larger V2 product
  thesis against current production, then either commission a distinct parity/truth/
  alpha/Prophet workstream with one bounded first vertical or explicitly park further
  expansion. No post-P0 implementation is authorized by this closeout.
---

## Closure

BioCatalyst Recovery V2 is complete as a recovery program.

The chain is now:

- #5788 — canonical V2 recovery masterplan;
- #5793 — P0-A caller binding;
- #5804 — deploy restart-path decoupling;
- #5810 — typed hydration states;
- #5906 / #5927 — entitlement completed, deep-validation amplification isolated;
- #5934 — request-local single-generation-load repair;
- #6052 — retained validated artifacts, independently reviewed PASS;
- #6090 — real entitled production acceptance, `BIOCATALYST P0 — PROVEN_LIVE`.

#6090 is the decisive receipt: the served process on the #6052 code completed the
entitled primary API/browser journeys without a 524 or 5xx, while unsigned and invalid
requests continued to fail closed. That satisfies the objective frozen on this workstream.

What remains is **not unfinished recovery**. Product parity, wider clinical/regulatory
coverage, alpha/asymmetry intelligence, Prophet integration and any BCI federation are
new product/intelligence programs. They may reuse this proven truth plane, but they require
a new Sol ruling and work identity rather than silently reopening this completed row.
