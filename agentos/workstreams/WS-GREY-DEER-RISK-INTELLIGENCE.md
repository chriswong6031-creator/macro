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
  - "Open-PR collision fences (2026-08-19): #5925 entry_radar live_pack, #5929 radar transport, #5928 Prophet Lab API, #5954 CI legacy-jobs manifest, #5948 backfill workflow — no Grey Deer edits to those paths until resolved/reconciled."
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
    status: awaiting_ci
    pr: 5961
    # Prereg-first commit-verified: 663fb02b500c ("freeze ... prereg before
    # outcomes") precedes every outcome-bearing dossier commit on the branch.
    # NOTE: the prereg predates the landed Sol freeze (#5963) — it remains the
    # operative GD-H freeze for GD-1; changes under the landed freeze need a
    # new prereg version.
  - id: GD-1B
    title: Existing-organ replay + Prophet counterfactual (Grok)
    status: awaiting_ci
    pr: 5961
    depends_on: [GD-1A]
    # Artifacts land with #5961; the wave is NOT done at merge — the packet's
    # adversarial acceptance review (independent reviewer + Fable final, Sol on
    # architecture implications) is still owed on the dossier's conclusions.
  - id: GD-2
    title: Settled Risk Envelope + three-answer Macro hero
    status: todo
    depends_on: [GD-0A]
  - id: GD-3
    title: Live provisional envelope + pending escalation
    status: todo
    depends_on: [GD-2]
  - id: GD-4A
    title: CN/HK forward-ledger liveness repair
    status: todo
    depends_on: [GD-0A]
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
    depends_on: [GD-1B]
  - id: GD-5B
    title: Crowded-winner liquidation expert (shadow)
    status: todo
    depends_on: [GD-1B]
  - id: GD-5C
    title: Repair/re-entry expert (shadow)
    status: todo
    depends_on: [GD-1B]
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
  Merge #5961 (GD-1 artifacts + canonical-identity reconciliation); then run
  the GD-1B adversarial acceptance review (independent reviewer + Fable final,
  Sol on architecture implications); author the GD-2 build packet from the
  2026-08-19 archaeology (settled-envelope seam, live seam, CN/HK ledger root
  cause) reconciled against the freeze.
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
