---
schema: agentos.decision.v1
key: AUTONOMY-CLOSURE-SPINE-V1
question: >
  How should Mastermind close the remaining autonomy-composition gaps without replacing the
  existing Executive OS, RuntimeBinding, Wake, dialogue, capacity, Control Room, or Agent OS
  owners and without delaying the current golden-path source train?
answer: >
  Adopt Autonomy Closure Spine v1. Preserve the existing W3C -> C2 -> MAT-S1 -> Stage-B1 ->
  Control Room -> golden-root train, and add only ACF-1 Semantic Directive Convergence before
  multi-Sol/fleet acceptance. ACF-1 uses one Executive Runtime Event command domain per exact
  terminal-return revision. Runtime accepts exactly one actor class, ACTION_TARGET, through the
  existing control_plane.sol_action_target.require_sol_action_authority owner; current Chairman
  intent continues through the human/session layer and the then-current action target submits any
  revision N+1. The directive body is an exact bounded discriminated union for CONTINUE, REPAIR,
  STOP, or ESCALATE, with immutable CommissionRef for REPAIR and closed reason enums for STOP and
  ESCALATE. The existing COO cycle consumes the effective Event exactly once and binds its ordinary
  downstream Event as the consumption/effect receipt. Unconsumed same-generation correction is
  allowed only with downstream effect NONE; consumed, applied, or effect-unknown work requires
  reconciliation. Keep ACF-2 through ACF-6 evidence-gated after the golden root.
rationale: >
  Mastermind already has target selection and transport semantics, but those are not decision
  convergence. Live W3C and C2 carriers demonstrated conflicting or stale action-looking Sol
  instructions. Slack ordering cannot atomically reject an observer, stale target, changed body, or
  CONTINUE/STOP race. Including actor, target generation, or decision in the command key would let
  rivals mint parallel command IDs. A free-form decision body would create an undeclared model-authored
  command language. A direct CHAIRMAN Runtime actor would fabricate an authority owner that does not
  currently exist. The smallest lawful repair reuses the exact action-target owner, one return-revision
  conflict key, one closed body union, one immutable Runtime Event, and one existing-COO consumer.
alternatives:
  - option: Finish every existing autonomy component independently and integrate later
    why_not: >
      Locally correct components could still accept conflicting decisions or duplicate downstream work.
  - option: Build a new generic autonomy platform
    why_not: >
      It would duplicate Executive lifecycle, Event, routing, retry, identity, and state owners.
  - option: Treat latest Slack prose as the effective decision
    why_not: >
      Slack is transport and cannot bind exact return, actor generation, command conflict, or consumption.
  - option: Include actor, target generation, or decision in the command identity
    why_not: >
      Rival proposals would derive different command IDs and could all commit.
  - option: Let the model author an arbitrary machine decision body
    why_not: >
      Free-form model content would become an unreviewed command language.
  - option: Add a direct machine-authenticated Chairman actor in v1
    why_not: >
      No existing protected Runtime principal/receipt owner supports it; Chairman intent remains the
      human/session authority that directs the current exact action target.
evidence:
  - "Mastermind issue #437 is the single Chairman-approved architecture carrier."
  - "Mastermind PR #438 remains the exact three-path F0 source carrier on protected base 7022e70640637a4fa07f073442dc693301290e2a."
  - "Current F0 head 8d52eb61a2ef88d301382dd1f56131dd777bf0b9 is a same-carrier RED test -> design -> plan repair implementing PR comment 5535576267."
  - "The current contract reuses mastermind.sol_action_target.v1 and SolActionTargetResolution.evidence_digest as the sole v1 actor authority receipt."
  - "The current body schema is mastermind.executive_semantic_directive_body/v1 with exact CONTINUE/REPAIR/STOP/ESCALATE variants and 4096-byte canonical ceiling."
  - "Mastermind PR #427 protected W3C source through merge a945e76befb34d15d0ab0e369b4197901883bb16."
  - "Mastermind PR #415 remains the active C2-R1A Runtime writer and gates ACF-1 implementation."
  - "Mastermind PR #326 remains the active Control Room projection writer."
  - "Issue #400 is closed as duplicate; issue #386 remains canonical."
affects:
  - WS:CHAIRMAN-CONTROL-ROOM
  - WS:EXECUTIVE-CAPACITY-FABRIC
  - Mastermind#386
  - Mastermind#437
  - Mastermind#438
confidence: high
reversibility: easy
decided_by: chairman
decided_at: 2026-09-03
---

# Autonomy Closure Spine v1

ACF-1 is the only newly authorized pre-fleet closure layer and remains
`WAITING_ARCHITECTURE_PROTECTION / WAITING_RUNTIME_PATH_RELEASE / needs_placement`.
No implementation worker, branch, provider action, Runtime effect, or production canary exists.

## Existing-owner boundary

- Executive Runtime owns command conflict, directive Event commit, readback, and lifecycle truth.
- `control_plane.sol_action_target` plus SessionTargetRegistry/RuntimeBindingSnapshot owns the sole
  v1 ACTION_TARGET actor authority.
- terminal-return owns exact source completion evidence.
- W3C/Wake/Agent Relay own attention and delivery; Agent Dialogue owns transport.
- `common.commission_ref` owns immutable REPAIR source identity.
- the existing COO cycle owns once-only directive consumption and downstream Event receipt.
- Control Room may later project current directive state but never author it.
- Agent OS records the ruling; GitHub records implementation and evidence.

ACF-2 through ACF-6 may start only when a golden-root or installed-fleet falsifier proves a concrete
existing-owner gap. This decision grants no standing authority to implement them.
