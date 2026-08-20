---
key: GREY-DEER-RISK-INTELLIGENCE
title: Grey Deer Risk Intelligence & Capital Protection System
objective: >
  Separate slow measured market state, transition hazard and capital policy;
  publish one canonical risk envelope across Macro, Prophet, Terminal and
  Mastermind Portfolio; and allow only individually promoted or explicitly
  temporary, scope-bounded, counterfactual-preserving protection rules to affect
  actionability. Done means a real market event reaches real production users and
  authorized machine consumers with PIT clocks, correction receipts and learning.
status: active
program: market-regime-risk
repos: [macro, terminal, mastermind]
owner: coo-fable
class: build
blast_radius: user_facing
ambiguity: scoped
owns_paths:
  - research/grey_deer/
  - engine/risk_envelope.py
  - scripts/build_risk_envelope.py
  - scripts/build_live_risk_envelope.py
  - site/riskdata/risk_envelope.json
  - site/live/risk_envelope.json
  - templates/risk_envelope/
  - tests/test_risk_envelope
  - agentos/handoffs/GREY-DEER-
discoveries:
  - DSC:GD1-LC-EMISSION-LOG-STARTS-BROKEN
  - DSC:GD1-EWY-IS-NOT-KOSPI-CASH
  - DSC:GD1C-PIT-MEMBERSHIP-PREHISTORY-ABSENT
decisions:
  - DEC:RISK-STATE-HAZARD-POLICY-SEPARATION
  - DEC:RISK-ENVELOPE-IS-CANONICAL-DERIVED-PROJECTION
  - DEC:RISK-EPISODES-USE-CHRONICLE-AND-REFLEXES
  - DEC:PROPHET-RANK-PRESERVED-MARKET-ELIGIBILITY-SIDECAR
  - DEC:REPAIR-IS-ORTHOGONAL-AND-FIRST-CLASS
  - DEC:PORTFOLIO-CONSUMES-NOT-RECOMPUTES-MARKET-RISK
  - DEC:SCOPED-REFLEX-CONSTRAINTS-NOT-FUSED-SHIELD
  - DEC:AUTO-EXIT-NOT-IN-GREY-DEER-V1
artifacts:
  - research/grey_deer/GREY_DEER_RISK_INTELLIGENCE_ARCHITECTURE_FREEZE_2026-08-19.md
  - research/grey_deer/GREY_DEER_FABLE_EXECUTION_COMMAND_PACKET_2026-08-19.md
  - research/grey_deer/GREY_DEER_WAVE_GRAPH_AND_PR_ACCEPTANCE_MATRIX_2026-08-19.md
  - research/grey_deer/GD1_GROK_SCIENTIFIC_REPLAY_HANDOFF_2026-08-19.md
landmines:
  - "Collision fence (Sol ruling 2026-08-19): #5925 entry_radar live_pack MERGED but its PRODUCTION PROOF is still outstanding — no Grey Deer edits to engine/entry_radar/** until the Radar owner accepts the proof. Fences for #5928/#5929/#5954/#5948 are RESOLVED (all merged) and removed."
  - "The CI control-plane program's operator grant does NOT extend to Grey Deer: never admin-merge a Grey Deer PR over red main on that precedent."
  - "site/riskdata/ sits under market-regime-risk's implementation roots in config/mastermind_programs.yml — Grey Deer owns only risk_envelope.json inside it; raw regime/market-state artifacts stay with market-regime-risk."
  - "Session worktrees are sparse: site/ and data/ writes require scripts/worktree_sparse.py opt-in before any GD-2+ build touches them."
do_not_redo:
  - "No universal fused risk score in scored/authority paths (see DEC:RISK-STATE-HAZARD-POLICY-SEPARATION; legacy engine/risk_state.py is frozen compatibility, not a template)."
  - "No new event store / forward ledger for risk episodes — Chronicle + Reflex Registry + QLedger own durable history (DEC:RISK-EPISODES-USE-CHRONICLE-AND-REFLEXES)."
  - "No Prophet rank/population mutation, ever — actionability sidecar only (DEC:PROPHET-RANK-PRESERVED-MARKET-ELIGIBILITY-SIDECAR)."
  - "No arming Portfolio brain/posture_decider.py as a shortcut; no LLM probability_rolldown in any authoritative consumer."
  - "No automatic held-position exits in v1 (DEC:AUTO-EXIT-NOT-IN-GREY-DEER-V1)."
waves:
  - id: GD-0A
    title: Durable program landing — freeze, workstream, 8 decisions, handoff, registry, system map
    status: done
    pr: 5963
    # MERGED 2026-08-19T12:24:34Z, squash 705a0ceaa157; proof run 32250586821
    # 14/14 green on the refreshed head after the fleet-wide qledger T9 heal
    # (#5970, 2e13b9a51761). Discoverability verified from origin/main
    # (files + registry key + compile-context bundle).
  - id: GD-1A
    title: PIT prereg + source-clock census (Grok; hash-pinned before outcomes)
    status: done
    pr: 5961
    # MERGED 2026-08-19T14:02:46Z, squash 7676a89d370c. Sol acceptance ruling
    # 2026-08-19 closed GD-1A DONE. Prereg-first commit-verified: 663fb02b500c
    # precedes every outcome-bearing dossier commit AND predates the landed
    # freeze (#5963) — it remains GD-1's operative GD-H freeze; GD-H changes
    # under the landed freeze need a new prereg version.
  - id: GD-1B
    title: Existing-organ replay + Prophet counterfactual (Grok)
    status: done
    pr: 5961
    depends_on: [GD-1A]
    # Sol acceptance ruling 2026-08-19: ACCEPTED_NO_PROMOTION — dossier
    # accepted as research; NO construction cleared the preregistered
    # design-era gate (prereg §10), so ZERO GD-5 promotions issue from GD-1.
    # See DEC:GD1-ACCEPTED-NO-PROMOTION.
  - id: GD-1C
    title: leadership_crack.v1 design-era reconstruction + GD-H1/GD-H2 interaction test (research-only prerequisite for GD-5)
    status: in_progress
    pr: 6038
    # Relayed to the Grok operator 2026-08-19 (Sol: "relay now"; operator
    # carried GROK_GD1C_DESIGN_ERA_RECONSTRUCTION_PACKET_2026-08-19.md into
    # the AionUI session; canonical commission is the in-repo file below).
    depends_on: [GD-1B]
    # Sol-commissioned 2026-08-19; packet:
    # research/grey_deer/commissions/GD-1C_LEADERSHIP_CRACK_DESIGN_ERA_COMMISSION_2026-08-19.md
    # (fresh prereg; already-frozen GD-H1/GD-H2 only; episode-level effective N;
    # current-membership reconstruction labeled def_current_cf; BLOCKED if PIT
    # membership cannot be reconstructed for the primary test; August 2026 may
    # not choose thresholds).
    # Research package completed 2026-08-19 under prereg freeze fce7bfeb8c92:
    # PRIMARY GD-H1=BLOCKED and GD-H2=BLOCKED because PIT cohort membership
    # cannot be reconstructed across 2016-01-04..2026-07-31. The separate
    # def_current_cf lane produced no secondary PASS. Wave stays in_progress
    # until the commissioned Fable scope + prereg-topology acceptance review;
    # ZERO GD-5 promotions and no authority meanwhile.
  - id: GD-2
    title: Settled Risk Envelope + three-answer Macro hero
    status: in_progress
    pr: 6026
    depends_on: [GD-0A]
    # PR #6026 MERGED 2026-08-19T23:15:52Z (e6a3fcd6e094) on a fully green
    # full-manifest re-run; Fable design review PASS. Sol post-merge review
    # 2026-08-19: Gate 8 (production acceptance) is BLOCKED until GD-2R1
    # merges, and then runs on the REPAIRED production render. Birth authority
    # DESCRIPTIVE ONLY unchanged.
  - id: GD-2R1
    title: Semantic-correctness repair of the settled envelope (pre-acceptance)
    status: in_progress
    depends_on: [GD-2]
    # Sol post-merge commission 2026-08-19; packet:
    # research/grey_deer/commissions/GD-2R1_SEMANTIC_CORRECTNESS_REPAIR_2026-08-19.md.
    # (1) LC BROKEN alone -> FRAGILE never TRANSMITTING (transmission needs an
    # independent settled source); (2) stage_since null until a lawful
    # first-observed episode transition — source onset stays in provenance;
    # (3) required-unmappable source nulls the hazard, optional calm can never
    # yield NONE; (4) behavioral stance copy removed while zero policies —
    # descriptive language + "no Grey Deer policy active"; (5) coherence
    # describes market reads only, posture excluded from agreement encoding;
    # (6) 08-18 fixture expectation -> FRAGILE / CONTRADICTORY, stage_since
    # null, raw source states unchanged.
  - id: GD-3
    title: Live provisional envelope + pending escalation
    status: todo
    depends_on: [GD-2]
    # Sol rulings 2026-08-19 (x2): do NOT start GD-3 until Gate 8 passes on
    # the GD-2R1-REPAIRED production render.
  - id: GD-4A
    title: CN/HK forward-ledger liveness repair
    status: in_progress
    pr: 6022
    depends_on: [GD-0A]
    # PR #6022 MERGED (7d203ee2862f); Sol post-merge review 2026-08-19:
    # implementation ACCEPTED pending the real Asia-close production proof
    # (one current CN row + one current HK row, idempotent, zero intraday).
    # Sol-commissioned 2026-08-19 as its own PR; packet:
    # research/grey_deer/commissions/GD-4A_CNHK_LEDGER_REPAIR_COMMISSION_2026-08-19.md.
    # COLLECT_LANE=nightly ONLY on the exact settled forward-ledger advancement
    # steps of the canonical Asia-close lane, never job-wide. Prospective
    # resume only — the July–August gap is NOT backfilled into the canonical
    # forward log. Done needs a real Asia-close production proof: exactly one
    # current CN row + one current HK row, duplicate-date idempotence, zero
    # intraday advancement.
  - id: GD-4B
    title: China Prophet board-health observation (display only)
    status: todo
    depends_on: [GD-0A]
  - id: GD-4C
    title: PBOC liquidity-composition read (display/context)
    status: todo
    depends_on: [GD-0A]
  - id: GD-5A
    title: Long-end duration shock expert (shadow)
    status: todo
    depends_on: [GD-1C]
    # Sol ruling 2026-08-19: GD-5A/B/C may not begin unless the applicable
    # hypothesis clears the promotion gate (GD-1 promoted nothing; GD-1C is
    # the prerequisite).
  - id: GD-5B
    title: Crowded-winner liquidation expert (shadow)
    status: todo
    depends_on: [GD-1C]
  - id: GD-5C
    title: Repair/re-entry expert (shadow)
    status: todo
    depends_on: [GD-1C]
  - id: GD-6A
    title: US Prophet market-eligibility sidecar (shadow)
    status: todo
    depends_on: [GD-2]
  - id: GD-6B
    title: China Prophet market-eligibility sidecar (shadow)
    status: todo
    depends_on: [GD-2, GD-4B]
  - id: GD-7A
    title: Temporary China new-entry protection (Chairman activation required)
    status: todo
    depends_on: [GD-6B]
  - id: GD-8A
    title: Macro alert integration (existing Alert Command Center)
    status: todo
    depends_on: [GD-3]
  - id: GD-8B
    title: Terminal envelope mirror (no local recompute)
    status: todo
    depends_on: [GD-3]
  - id: GD-9A
    title: Portfolio envelope shadow adapter (zero book mutation)
    status: todo
    depends_on: [GD-3]
  - id: GD-10
    title: Portfolio market-truth cutover (Sol + Chairman)
    status: todo
    depends_on: [GD-9A]
  - id: GD-11
    title: Promotion scorecard and learning loop
    status: todo
    depends_on: [GD-5A, GD-6A, GD-8A]
next_action: >
  Merge GD-2R1 (semantic-correctness repair, commissioned); then run Gate 8
  on the repaired production render; verify GD-4A's Asia-close row proof;
  Fable reviews the GD-1C BLOCKED/no-promotion research package and prereg
  topology. GD-3 starts only after Gate 8 passes; GD-5A/B/C remain closed
  because GD-1C cleared no promotion gate.
---

# Grey Deer Risk Intelligence & Capital Protection

The canonical architecture, laws, wave packets, acceptance matrices, collision
fences and research protocol live in `research/grey_deer/` (see its `README.md`
for precedence). This record carries program state only.

**Authority summary:** the Risk Envelope owns no rank/size/gate/execute
authority. Policy authority arrives only per-rule via the frozen promotion
gates (freeze §10) or an explicit `temporary_operator_safety` Chairman grant
(freeze §11). Automatic held-position exit is out of scope for v1.

**Ownership summary:** Macro owns market truth, hazard experts, the envelope
and Prophet eligibility sidecars; Prophet owns raw rank/admission; Terminal
mirrors; Mastermind Portfolio consumes the envelope and owns book-specific
sizing/settlement/execution; LLMs explain and de-escalate only.
