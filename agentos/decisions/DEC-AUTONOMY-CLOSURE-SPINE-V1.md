---
schema: agentos.decision.v1
key: AUTONOMY-CLOSURE-SPINE-V1
question: >
  How should Mastermind close the remaining autonomy-composition gap without replacing existing
  lifecycle, action-target, Wake, dialogue, capacity, COO, Control Room, or Agent OS owners?
answer: >
  Adopt Autonomy Closure Spine v1 and preserve the W3C -> C2 -> MAT-S1 -> Stage-B1 -> Control Room
  -> golden-root train. Authorize only ACF-1 before fleet proof. ACF-1 uses one Executive Runtime
  command domain per terminal-return revision; accepts only the existing ACTION_TARGET authority
  through control_plane.sol_action_target.require_sol_action_authority; validates an exact bounded
  CONTINUE/REPAIR/STOP/ESCALATE body; canonicalizes through the existing
  control_plane.wake_events.canonical_json_bytes owner; performs replay lookup before current actor
  revalidation so no-effect readback survives target rotation; and lets the existing COO cycle
  consume the Event once in the same transaction as the downstream mutation. STOP closes only the
  returned source-child boundary; root terminalization remains existing COO/Runtime law. ACF-2
  through ACF-6 remain evidence-gated.
rationale: >
  Target identity and transport truth do not establish which semantic decision became effective.
  Live W3C and C2 carriers demonstrated conflicting or stale action-looking instructions. Slack
  ordering cannot reject an observer, stale target, changed body, or CONTINUE/STOP race. Actor,
  target-generation, or decision entropy in the command key would create parallel commands. A
  free-form body would create model-authored executable authority. Requiring current actor authority
  to read back an already-committed effect after target rotation would strand effect reconciliation.
  Allowing STOP to mean either child or root would make the machine transition ambiguous. The
  smallest lawful repair uses existing owners and makes both boundaries exact.
alternatives:
  - option: Finish each existing component independently
    why_not: Locally correct components can still accept conflicting semantic decisions.
  - option: Build a new autonomy platform
    why_not: It duplicates Executive lifecycle, Event, routing, retry, identity, and state owners.
  - option: Latest Slack message wins
    why_not: Slack is transport and cannot bind exact return, conflict, or consumption.
  - option: Include actor, target, or decision in command identity
    why_not: Rival proposals would derive different command IDs and could all commit.
  - option: Require current actor authority for no-effect readback
    why_not: Target rotation after a lost response would make a known committed Event unrecoverable.
  - option: Let STOP choose child or root at consumption time
    why_not: The directive would not be a closed deterministic command; root lifecycle has an existing owner.
evidence:
  - "Mastermind issue #437 is the single Chairman-approved architecture carrier."
  - "Mastermind PR #438 remains the exact three-path F0 source carrier on protected base 7022e70640637a4fa07f073442dc693301290e2a."
  - "Current F0 head f0c5cacab01ae5de7f09c9462fb16d2f2a210fe7 uses wake_events canonical JSON, replay-first readback, and source-child-only STOP semantics."
  - "The sole v1 actor owner is mastermind.sol_action_target.v1 / SolActionTargetResolution.evidence_digest."
  - "REPAIR uses normalized CommissionRef; STOP and ESCALATE use closed enums; body maximum is 4096 canonical UTF-8 bytes."
  - "Mastermind PR #427 protected W3C source through a945e76befb34d15d0ab0e369b4197901883bb16."
  - "Mastermind PR #415 remains the active C2-R1A Runtime writer and gates ACF-1 implementation."
  - "Mastermind PR #326 remains the active Control Room writer."
  - "Issue #400 is closed duplicate; issue #386 remains canonical."
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
No implementation worker, branch, Runtime Event, provider action, deployment, or canary exists.

## Existing-owner boundary

- Executive Runtime owns command conflict, Event commit/readback, and lifecycle truth.
- `control_plane.sol_action_target` owns the sole v1 actor authority.
- `control_plane.wake_events.canonical_json_bytes` owns canonical JSON bytes.
- `common.commission_ref` owns immutable REPAIR source identity.
- terminal-return owns source completion evidence.
- W3C/Wake/Agent Relay own attention and delivery; Agent Dialogue owns transport.
- the existing COO cycle owns transactional consumption and the ordinary downstream Event receipt.
- root terminalization remains existing COO/Runtime authority; ACF-1 STOP is source-child-only.
- Control Room may later project state but never author it.

Exact existing Event readback is no-effect reconciliation and remains available after target rotation.
Consumed, applied, or effect-unknown work cannot be reversed by later prose. ACF-2 through ACF-6 may
start only when golden-root evidence proves a concrete existing-owner gap.
