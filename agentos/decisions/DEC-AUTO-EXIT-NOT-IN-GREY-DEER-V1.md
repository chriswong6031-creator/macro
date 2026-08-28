---
key: AUTO-EXIT-NOT-IN-GREY-DEER-V1
question: >
  May Grey Deer v1 automatically exit or liquidate held positions when market
  hazard becomes severe?
answer: >
  No. Grey Deer v1's action ceiling for held exposure is advisory review:
  new-entry restriction (NO_CHASE, REDUCE_SUGGESTED_SIZE, SUPPRESS_NEW_ENTRY,
  NO_NEW_LONG_RISK), size constraints, NO_ADD, PROTECTION_REVIEW and
  EXIT_REVIEW. Automatic held-position liquidation (AUTO_EXIT) is excluded
  from v1 across every surface — Macro, Prophet, alerts, Terminal, Portfolio.
  Any future automatic exit requires a separate Chairman-approved,
  user-opt-in, forward-only gauntlet with its own architecture ruling; it is
  not an extension of any v1 gate.
rationale: >
  Selling a user's held position is the highest-blast-radius action the system
  could take: it realizes losses, cannot be undone by a rollback, and carries
  user capital authority that no market-level signal has earned. v1's
  protection value (stopping exposed NEW risk during a breakdown) is available
  at a fraction of that risk. Exits also have a categorically worse
  false-alarm cost profile — a wrong SUPPRESS_NEW_ENTRY forgoes upside, a
  wrong AUTO_EXIT destroys realized capital and user trust. EXIT_REVIEW
  additionally requires name-level invalidation evidence, keeping human/user
  authority in the loop where it belongs in v1.
alternatives:
  - option: Include auto-exit behind the same promotion gauntlet as new-entry authority
    why_not: >
      The new-entry gauntlet measures suppression counterfactuals, not
      realized-liquidation outcomes; exits need forward-only prospective
      evidence, user opt-in, and Chairman approval as a separate act — reusing
      the gate would smuggle the highest-stakes authority through a gate
      calibrated for the lowest.
  - option: Emergency auto-exit only at extreme hazard states
    why_not: >
      An extreme-state carve-out is still automatic liquidation, triggered
      exactly when data quality is worst and false-positive cost is highest;
      EMERGENCY_REDUCTION under user-opt-in portfolio control already covers
      the lawful shape of drastic action.
  - option: No exit-related output at all in v1
    why_not: >
      Overshoots: EXIT_REVIEW with name-level invalidation receipts is
      valuable, bounded, and preserves user authority — removing it would
      leave breakdown states with no reviewable path for held exposure.
evidence:
  - "research/grey_deer/GREY_DEER_RISK_INTELLIGENCE_ARCHITECTURE_FREEZE_2026-08-19.md §6 (AUTO_EXIT exclusion), §9 (authority matrix row 'Auto-exit'), §10 (automatic exit not eligible)"
  - "research/grey_deer/GREY_DEER_FABLE_EXECUTION_COMMAND_PACKET_2026-08-19.md §5 law 15, §12 (promotion thresholds; auto-exit not eligible), §20 (adding automatic exits to V1 is an escalation trigger)"
affects:
  - "WS:GREY-DEER-RISK-INTELLIGENCE"
  - "portfolio-desk"
  - "prophet"
confidence: high
reversibility: one_way
decided_by: ceo-sol
decided_at: 2026-08-19
---

## Grounds

Sol architecture freeze 2026-08-19, commissioned by Chairman Chris. The
exclusion is stated identically in the freeze (§6, §9, §10), the command
packet (laws, thresholds, stop conditions) and the wave matrix (authority
checkpoints) so no wave can inherit exit authority by omission.

## What would reopen this

Only a new Chairman-approved architecture ruling establishing the separate
user-opt-in, forward-only auto-exit gauntlet. No incident severity, replay
result, or operator urgency inside Grey Deer v1 reopens it — reversibility is
marked one_way because v1 itself can never grow this authority; a future
program with its own ruling must.
