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
  multi-Sol/fleet acceptance. ACF-1 uses one Executive Runtime Event command domain per terminal-
  return revision; competing actors and CONTINUE/REPAIR/STOP/ESCALATE proposals collide rather
  than minting parallel directives. Runtime revalidates the current target/actor and constructs the
  closed machine decision body from canonical state. The current target may correct its own
  unconsumed directive only under the same binding generation with downstream effect NONE;
  Chairman may supersede any unconsumed directive with current authority and effect NONE. The
  existing COO cycle consumes the effective Event and downstream mutation in one existing
  transaction, using its ordinary Event as the consumption receipt. Consumed, applied, or
  effect-unknown work requires reconciliation rather than post-consumption reversal. Keep ACF-2
  through ACF-6 evidence-gated after the golden root and extend only their existing owners.
rationale: >
  Mastermind already has target selection and transport semantics, but those are not decision
  convergence. Live W3C and C2 carriers demonstrated conflicting or stale action-looking Sol
  instructions. Slack ordering cannot atomically reject an observer Sol, old target, changed
  decision, or CONTINUE/STOP race. A command key containing actor, target generation, or decision
  semantics would be unsafe because rivals could mint parallel IDs. Requiring Chairman for a
  current Sol's pre-effect correction would preserve routine Chairman labor, while allowing a
  consumed directive to be overwritten would risk duplicate or contradictory effects. The
  smallest coherent repair is one return-revision key, Runtime-derived body, immutable directive
  Event, bounded pre-consumption correction, and existing-COO transactional consumption.
alternatives:
  - option: Finish every existing component independently and integrate later
    why_not: >
      Locally correct components can still accept conflicting decisions, duplicate downstream action,
      or require Chairman precedence repair.
  - option: Build a new generic autonomy/orchestration platform
    why_not: >
      It would duplicate Executive lifecycle, event, routing, retry, identity, and state owners.
  - option: Treat the latest Slack instruction as the effective decision
    why_not: >
      Slack is transport, may arrive out of order, and cannot bind exact return, actor or consumption.
  - option: Include actor, target generation, or decision in the idempotency key
    why_not: >
      Rival proposals would derive different command IDs and could all commit.
  - option: Make the model author the machine decision body
    why_not: >
      Free-form model output would become an undeclared command language; Runtime must derive the body
      from the closed decision and canonical state.
  - option: Require Chairman for every pre-consumption correction
    why_not: >
      The current exact target can safely correct its own unconsumed same-generation directive when
      downstream effect is proven NONE; forcing Chairman involvement would defeat the autonomy goal.
  - option: Let later prose reverse a consumed directive
    why_not: >
      Consumed, applied, or effect-unknown work requires downstream reconciliation first.
evidence:
  - "Mastermind issue #437 records the Chairman-approved architecture exception and ACF-1 contract."
  - "Mastermind PR #438 is the exact three-path records-only source candidate on protected base 7022e70640637a4fa07f073442dc693301290e2a."
  - "Final F0 head e3d049052a7c7f163ed90bde212d835a9bf3306e binds the return-revision conflict key, Runtime-derived body, same-generation target self-correction, downstream transactional consumption, and post-consumption reconciliation."
  - "Mastermind PR #427 merged W3C-I1 source as a945e76befb34d15d0ab0e369b4197901883bb16 and remains default-disarmed."
  - "Mastermind PR #415 remains the active C2-R1A Runtime writer and gates ACF-1 implementation."
  - "Mastermind PR #326 remains the active Control Room writer and gates later directive projection."
  - "Mastermind issue #400 is closed duplicate; issue #386 remains canonical."
  - "Protected-source search found no existing Event/consumer binding return + target + actor + revision + consumption."
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

## Owner boundary

- Executive Runtime owns conflict identity, directive commit and lifecycle truth.
- SessionTargetRegistry / RuntimeBinding / Stage B own the current target.
- terminal-return owns source completion evidence.
- W3C / Wake / Agent Relay own attention and delivery.
- Agent Dialogue owns transport.
- Runtime derives the closed decision body; model prose is not command authority.
- the existing COO cycle owns one directive-bound downstream mutation and Event receipt.
- Control Room later projects state but never authors it.
- Agent OS records why and next action; GitHub records code/proof.

ACF-2 through ACF-6 may start only when golden-root or installed-fleet evidence proves a concrete
existing-owner gap. This decision is not standing implementation authority.
