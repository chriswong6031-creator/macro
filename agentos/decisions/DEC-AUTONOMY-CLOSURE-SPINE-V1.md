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
  terminal-return revision; competing actors and CONTINUE/REPAIR/STOP/ESCALATE payloads collide
  there rather than minting parallel directives. The current target or Chairman must be
  revalidated in Runtime. The existing COO cycle consumes the effective Event once and binds its
  downstream command/Event as the consumption receipt. Chairman supersession is allowed only
  before consumption with downstream effect proven NONE; consumed, applied, or effect-unknown
  work requires reconciliation rather than post-consumption reversal. Keep ACF-2 through ACF-6
  evidence-gated after the golden root and extend only their existing owners.
rationale: >
  Mastermind already has target selection and transport semantics, but those are not decision
  convergence. Live W3C and C2 carriers demonstrated that multiple action-looking Sol instructions
  can conflict or arrive stale after a valid continuation. Slack ordering and human procedure can
  reconstruct precedence, but cannot atomically refuse an observer Sol, old target generation,
  changed decision, or CONTINUE/STOP race before downstream execution. A command key that includes
  decision or actor semantics would also be unsafe because rivals could mint parallel command IDs.
  The smallest coherent repair is one return-revision conflict key, one Runtime-owned immutable
  directive Event, and one existing-COO consumer. Building a new orchestrator would duplicate
  lifecycle and authority; finishing every component in isolation would leave the split-brain seam.
alternatives:
  - option: Finish every existing autonomy component independently and integrate later
    why_not: >
      Each component can pass locally while the composed system still accepts stale or conflicting
      semantic decisions, duplicates downstream action, or needs Chairman precedence repair.
  - option: Build a new generic autonomy/orchestration platform
    why_not: >
      It would duplicate Executive lifecycle, event, routing, retry, identity, and state owners and
      delay the first useful autonomous loop.
  - option: Treat the latest Slack instruction as the effective decision
    why_not: >
      Slack is transport, may arrive out of order, can be observed by non-authoritative Sols, and
      cannot transactionally bind the exact return, target generation, or downstream mutation.
  - option: Include actor, target generation, or decision payload in the idempotency command key
    why_not: >
      Competing Sols, target generations, CONTINUE and STOP would derive different command IDs and
      could all commit. Those facts belong in the validated payload, not the return-revision key.
  - option: Let a later Chairman message reverse an already-consumed directive
    why_not: >
      Once downstream work is applied or effect-unknown, later prose cannot prove rollback. The
      existing effect owner must reconcile and produce a lawful correction path first.
evidence:
  - "Mastermind issue #437 records the Chairman-approved architecture exception and closed ACF-1 contract."
  - "Mastermind PR #438 contains the exact three-path records-only source candidate on protected base 7022e70640637a4fa07f073442dc693301290e2a."
  - "ACF-1 repair head 9d0447096dcc1232e8d30bb5c25876e3558b07f1 adds the return-revision conflict key, downstream Event consumption receipt, and pre-consumption-only Chairman supersession law."
  - "Mastermind PR #427 merged W3C-I1 source as a945e76befb34d15d0ab0e369b4197901883bb16 and remains default-disarmed."
  - "Mastermind PR #415 remains the active C2-R1A Runtime writer and therefore gates ACF-1 Runtime implementation."
  - "Mastermind PR #326 remains the active Control Room writer and therefore gates any later directive projection."
  - "Mastermind issue #400 is closed with state_reason=duplicate; issue #386 remains the canonical dispatch-consumption incident."
  - "Current protected code search found no existing Executive semantic-directive Event/consumer that binds return + target + actor + revision + downstream consumption."
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

## Immediate consequence

ACF-1 is the only newly authorized pre-fleet closure layer. It remains
`WAITING_ARCHITECTURE_PROTECTION / WAITING_RUNTIME_PATH_RELEASE / needs_placement`.
No implementation worker, branch, provider action, Runtime effect, or production canary is created
by this decision.

## Existing-owner boundary

- Executive Runtime owns directive commit, conflict detection and all lifecycle truth.
- SessionTargetRegistry / RuntimeBinding / Stage B own the current action target.
- terminal-return owns the source completion evidence.
- W3C / Wake / Agent Relay own attention and delivery.
- Agent Dialogue owns transport.
- the existing COO cycle owns one directive-bound downstream mutation and its Event receipt.
- Control Room may later project directive/consumption/reconciliation state but never author it.
- Agent OS records why and next action; GitHub records code and proof.

## Conditional follow-ons

ACF-2 mission-envelope enforcement, ACF-3 useful-progress semantics, ACF-4 truthful production
acceptance, ACF-5 resource finalization, and ACF-6 producer-consumer compatibility may start only
when the golden-root or installed-fleet evidence proves a concrete existing-owner gap. This decision
is not standing authority to implement them.
