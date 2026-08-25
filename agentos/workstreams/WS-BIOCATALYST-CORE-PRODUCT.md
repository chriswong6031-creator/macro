---
key: BIOCATALYST-CORE-PRODUCT
title: BioCatalyst core product — post-P0 clinical/regulatory expansion
objective: >
  Expand the recovered BioCatalyst product beyond P0 through source-truth
  product projections, the Catalyst Radar container (first lane: Trial
  Milestones), Explorer/dossier-facing workflows, and bounded product APIs.
  Done for a wave = its slice is merged after Sol review, deployed, and
  proven with a real entitled production journey; done for the workstream is
  open-ended product expansion adjudicated wave by wave.
status: parked
program: biocatalyst
repos: [macro]
owner: coo-fable
class: build
blast_radius: user_facing
ambiguity: specified
owns_paths:
  - app/biocatalyst.py
  - engine/biocatalyst/catalyst_events.py
  - templates/biocatalyst.html.j2
  - templates/biocatalyst.js
  - templates/biocatalyst.css
  - site/biocatalyst.js
  - site/biocatalyst.css
  - tests/test_biocatalyst_api.py
  - tests/test_biocatalyst_page.py
  - tests/test_biocatalyst_d0a_design_contract.py
  - tests/test_biocatalyst_d0b_ui.py
  - tests/test_biocatalyst_hydration.py
  - tests/biocatalyst_hydration_harness.js
  - tests/test_biocatalyst_peer_api_contract.py
  - tests/test_biocatalyst_catalyst_radar.py
  - tests/test_biocatalyst_catalyst_radar_api.py
  - research/BIOCATALYST_P1_*
  - agentos/workstreams/WS-BIOCATALYST-CORE-PRODUCT.md
  - agentos/handoffs/BIOCATALYST-CORE-PRODUCT-*
waves:
  - id: P1-1
    title: Catalyst Radar — Trial Milestones first slice
    status: done
    next_action: >
      P1-1 is complete. No next CORE-PRODUCT wave is currently commissioned.
      P1-2 requires a separate explicit Sol ruling. The 2026-08-26T02:00Z
      source/launch-soak boundary remains owned by its source-governance path:
      window end grants no expansion authority; exact evidence must be frozen
      and adjudicated before any successor source/cohort transition.
decisions:
  - "DEC:BIOCATALYST-P1-FIRST-VERTICAL-MILESTONE-RADAR"
  - "DEC:BIOCATALYST-PDUFA-TRUTH-IS-CORPORATE-DISCLOSURE-PLANE"
  - "DEC:BIOCATALYST-CASH-RUNWAY-OWNED-BY-CAPITAL-STRUCTURE"
  - "DEC:BPC-CATALYST-COMPOSES-WITH-COMPANY-EVENT-NOT-FISCAL-WORKSPACE"
  - "DEC:BIOCATALYST-RECOVERY-V2-CORE-NOT-JV-OR-BCI"
landmines:
  - >-
    Ownership is narrow by Sol order (P1-0R review): this workstream does NOT
    own engine/biocatalyst/** or a blanket tests/test_biocatalyst_* claim —
    those globs include source/publication/history/storage/regulatory and
    source-soak surfaces owned elsewhere. Owned tests are the product-facing
    files enumerated in owns_paths only. The P1-1 implementation PR adds the
    exact new engine/biocatalyst/catalyst_events.py and its exact new test
    path to owns_paths when those files actually exist. Reading another
    plane/module never requires owning it.
  - >-
    Explicitly OUT of this workstream (Sol P1-0R charter): P0 recovery
    (WS:BIOCATALYST-RECOVERY-V2 is closed); BPC JV snapshot
    reconstruction/onboarding (WS:BPC-JV-RECON); source-soak governance (the
    launch SLO / source-registry truth program owns it); duplicate
    Company/Stock Identity; Capital Structure/FIF computations (consume,
    never compute — DEC:BIOCATALYST-CASH-RUNWAY-OWNED-BY-CAPITAL-STRUCTURE);
    Options transport; BCI market-episode/analogue intelligence (#5821 stays
    a draft candidate); Neural Web; Prophet/rank/selection/size authority.
  - >-
    No score, probability, materiality, rank, or composite anywhere in any
    BioCatalyst payload or UI — deterministic source facts only
    (authority: facts_and_context_only; also DNR:KILL-PHASE3-START-WEIGHT).
  - >-
    Public wording law (Sol-ratified): "Trial milestone", "Primary
    completion", "Study completion", "days to milestone"; never label a
    registry completion date a "readout", "catalyst date", or market event.
  - >-
    Zero mutation of the frozen soak surface until the post-soak
    successor-registry transition concludes: config/biocatalyst_sources.yml,
    the launch SLO manifest, CT.gov cadence, fixed cohort, freshness budget,
    denominator law, launch verifier. 2026-08-26T02:00Z ends the observation
    window; it grants no expansion authority by itself (soak evidence freeze
    → pass/fail adjudication → successor transition first).
  - >-
    Prospective PDUFA enters only through the Company Intelligence
    disclosure-plane consumer port
    (DEC:BIOCATALYST-PDUFA-TRUTH-IS-CORPORATE-DISCLOSURE-PLANE); never
    duplicate SEC/IR ingest, never manufacture forward dates from Drugs@FDA.
  - >-
    Never mint a local CIK/security map. Identity joins reuse an existing
    canonical PIT Company/Stock Identity read seam when archaeology proves
    one suitable; otherwise surfaces carry a typed
    company_identity_not_joined / ticker_only state.
  - >-
    Browser evidence drill-down exposes only the public-safe pointer-bound
    evidence projection (NCT, source URL, source clocks, generation-safe
    provenance, public record-history versions/revision values) — never
    private worker receipts, R2 keys, filesystem paths, private hashes, or
    credentials; do not widen macro-api filesystem access.
do_not_redo:
  - >-
    Do not re-adjudicate the first vertical; Sol ratified
    Catalyst Radar — Trial Milestones (P1-0R, 2026-08-20).
  - >-
    Do not reopen the completed P0 recovery chain (#5788→#6090) or reuse
    WS:BIOCATALYST-RECOVERY-V2 as an implementation catch-all.
  - >-
    Do not map TERMINATED / WITHDRAWN / SUSPENDED to a generic "cancelled
    catalyst". Preserve the exact trial status; SUSPENDED is paused, not
    terminal; a future milestone may be marked inactive because of trial
    status without inventing an event-cancellation fact.
  - >-
    P1-1 is now PROVEN_LIVE_COHORT_LIMITED on the real current four-NCT
    production cohort. Do not widen that bounded claim into full functional
    parity, production-scale proof, source-soak acceptance, or authority to
    start P1-2. The broader parity ledger remains PARTIAL.
artifacts:
  - research/BIOCATALYST_P1_RECHARTER_AND_FIRST_VERTICAL_ARCHITECTURE_2026-08-20.md
  - research/BIOCATALYST_P1_CONTINUATION_HANDOFF_2026-08-20.md
  - research/BIOCATALYST_P1_1_PRODUCTION_ACCEPTANCE_2026-08-22.md
  - research/BIOCATALYST_P1_1R_PRODUCTION_ACCEPTANCE_2026-08-23.md
next_action: >
  PARKED after completed P1-1. No next CORE-PRODUCT wave is currently commissioned. P1-2
  requires a separate explicit Sol ruling. The 2026-08-26T02:00Z source/launch-soak boundary
  remains owned by its source-governance path: window end grants no expansion authority;
  exact evidence must be frozen and adjudicated before any successor source/cohort transition.
---

## Context

Created by Sol's P1-0R authority-closure ruling (2026-08-20) as the P1
workstream home the recharter's §11.2 asked for. The P0 recovery program
(WS:BIOCATALYST-RECOVERY-V2) is complete and closed; this workstream owns
what comes after: product projections over the proven truth plane, the
Catalyst Radar container whose first lane is Trial Milestones (registry
schedule facts) and whose designed second tenant is Regulatory/PDUFA via the
disclosure-plane port, dossier/Explorer workflows, and bounded product APIs.
It is deliberately not a new semantic program — program stays `biocatalyst`.

Wave P1-1's frozen spec lives in
`research/BIOCATALYST_P1_CONTINUATION_HANDOFF_2026-08-20.md` (as amended by
P1-0R); the architecture constitution is
`research/BIOCATALYST_P1_RECHARTER_AND_FIRST_VERTICAL_ARCHITECTURE_2026-08-20.md`.

## Lifecycle reconciliation — 2026-08-24/25

Sol reconciled the top-level lifecycle from stale `active` to `parked`: P1-1 is complete and
production-proven at its bounded cohort, there is no live carrier or currently commissioned
successor wave, and the record explicitly requires a separate Sol ruling before P1-2. Parked
preserves this open-ended product home without falsely presenting idle future authority as
current execution. This correction changes organizational state only.
