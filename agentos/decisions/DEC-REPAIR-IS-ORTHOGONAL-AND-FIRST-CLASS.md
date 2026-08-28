---
key: REPAIR-IS-ORTHOGONAL-AND-FIRST-CLASS
question: >
  When a support event appears during an active hazard (issuer buyback, policy
  action, sharp rebound), does it de-escalate the hazard state, or is repair a
  separate first-class state with its own lifecycle?
answer: >
  Repair is orthogonal and first-class: repair_state ∈
  NONE | IMPULSE | BROADENING | CONFIRMED | FAILED, carried alongside — never
  inside — hazard_stage. A support event creates repair_state=IMPULSE, not
  green/all-clear; a market can lawfully be BREAKDOWN + REPAIR_IMPULSE. Repair
  lifts only the policy that owns it, and only after its frozen lift contract
  is met (for the first temporary policy: repair CONFIRMED, two settled
  sessions, fresh critical evidence, candidate requalification under Prophet's
  own availability rules). One buyback or a green future can create IMPULSE,
  never CONFIRMED.
rationale: >
  The single most dangerous UX failure in a drawdown is premature all-clear:
  one supported mega-cap can bounce an index while breadth stays broken, and a
  blended state would read that bounce as de-escalation. Making repair its own
  graded lifecycle lets the product say "repair attempt underway — not yet all
  clear," keeps failed repairs (retests) from minting fake new episodes, and
  makes repair calls gradeable in GD-11 (repair false-start rate) instead of
  invisible inside hazard flapping.
alternatives:
  - option: Repair as hazard de-escalation (support events lower hazard_stage)
    why_not: >
      Repaints hazard green on issuer-specific bounces; conflates "the
      mechanism stopped" with "someone is fighting the mechanism"; destroys
      the falsifiable record of failed repairs.
  - option: No repair representation until hazard resolves on its own
    why_not: >
      The user watching a violent bounce gets no honest read; policies could
      only lift via expiry, making protection needlessly sticky and the
      false-alarm cost higher than it must be.
  - option: Repair confirmation on a single strong session
    why_not: >
      The freeze requires persistence (no trigger expert still TRIGGERING+,
      contagion not rising, two settled sessions out of breakdown, fresh
      critical sources) — single-session confirmation is exactly how failed
      repairs get promoted.
evidence:
  - "research/grey_deer/GREY_DEER_RISK_INTELLIGENCE_ARCHITECTURE_FREEZE_2026-08-19.md §2.1, §7 (REPAIR_* compositions), §8.6 (re-entry)"
  - "research/grey_deer/GREY_DEER_FABLE_EXECUTION_COMMAND_PACKET_2026-08-19.md §5 law 12, §11 GD-5C (IMPULSE never CONFIRMED from one event)"
  - "research/grey_deer/GD1_GROK_SCIENTIFIC_REPLAY_HANDOFF_2026-08-19.md §17 (SK Hynix repair-analysis protocol)"
affects:
  - "WS:GREY-DEER-RISK-INTELLIGENCE"
  - "engine/risk_envelope.py (future)"
  - "config/reflexes.yml (policy lift contracts, future)"
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-19
---

## Grounds

Sol architecture freeze 2026-08-19. The August 2026 episode contains a live
exemplar (issuer capital-return support during an active breakdown) that GD-1
replays under GD-H7 (repair impulse versus durable repair).

## What would reopen this

Sol-level architecture change only. GD-1B/GD-5C evidence about repair
dynamics tunes expert constructions and lift thresholds within this shape; it
does not merge repair back into hazard.
