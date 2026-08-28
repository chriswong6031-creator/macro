---
key: INTRADAY-FLOW-PR4-MERGED-PRODUCTION-ACCEPTANCE-OWED
question: >
  After Macro PR #6105 merged the Intraday Flow live-transport repair, may the
  previously closed WS:INTRADAY-FLOW-P0-RECOVERY remain done, or must it reopen
  until a genuine current-session production cycle proves the restored quote,
  pulse and M1/R2 planes?
answer: >
  Reopen the workstream as active and keep PR-4 in_progress / BUILT_NOT_PROVEN.
  Record #6105 as the merged implementation, but require one exact
  current-session production acceptance: board-scoped quote coverage and source
  freshness; a current-session pulse whose semantic mode and coverage are
  healthy; the existing canonical com.mastermind.liveflow M1/R2 plane advancing
  on the reviewed checkout; /api/status and dead-man semantic health; and a real
  served browser journey whose `live` labels appear only when every required
  gate passes. The retired Studio options fleet remains disarmed. AD-9 long-term
  ownership remains a separate Advanced Data Options ruling.
rationale: >
  The original P0 closeout was correct for its then-scoped outcome: PR-1 restored
  null-safe paint, PR-2 fixed the false OPEX clock, and PR-3 honestly classified
  the live-flow source as DEGRADED without speculative re-arming. A later direct
  operator incident proved that the user-facing outcome had reopened: the board
  rendered, but public quotes covered only 3/116 leaders, pulse bytes were
  generated from an unread `DatetimeIndex(name='ts')` and could be age-fresh
  while `mode=no_data`, and an old M1 checkout kept the live-flow plane stale.
  #6105 repairs those mechanisms using the existing canonical planes and strong
  deterministic tests, but its own return explicitly leaves the first real
  current-session cycle to a separate proof. Treating the prior `done` flag or
  the merge as completion would make infrastructure look healthy without proving
  the trader sees honest live inputs. Conversely, reopening the retired Studio
  fleet would widen the incident into a duplicate options engine and bypass the
  separate AD-9 authority gate.
alternatives:
  - option: Keep the workstream done because PR-1 through PR-3 were already accepted
    why_not: >
      The later incident changed the observable product outcome and the workstream
      itself added PR-4 in_progress. A top-level done state that contradicts its
      own live wave is unusable canonical memory.
  - option: Mark PR-4 done because #6105 merged and fixture coverage reached 116/116
    why_not: >
      Fixture filtering proves code shape, not source freshness, semantic pulse
      health, current M1/R2 operation, served labels, or absence of a stale clone.
      #6105 explicitly separates its production receipt.
  - option: Route all remaining proof/repair to WS:ADVANCED-DATA-OPTIONS
    why_not: >
      AD-9 owns long-term fleet/authority decisions, but this exact PR-4 product
      acceptance belongs to the workstream that shipped the repair. Moving the
      receipt would hide whether the promised vertical actually works.
  - option: Re-arm the retired host-side Studio options fleet as a fallback
    why_not: >
      That would create a second active engine/ownership path and violate both the
      #6105 scope and the existing AD-9 hold. The accepted repair is limited to
      com.mastermind.liveflow plus bounded projections.
evidence:
  - "Macro PR #6105 merged as 364b85973517f459dba937145a040dce93862907"
  - "PR #6105 incident evidence: public quotes 3/116, private full snapshot 116/116"
  - "PR #6105 incident evidence: flow_pulse age-fresh but mode=no_data"
  - "PR #6105 incident evidence: Polygon DatetimeIndex named ts returned zero rows before normalization"
  - "PR #6105 incident evidence: M1 old deploy tree looped on Aug-13 while R2 meta stayed Aug-12"
  - "WS:INTRADAY-FLOW-P0-RECOVERY current contradiction: top-level done, PR-4 in_progress"
  - "DSC:INTRADAY-FLOW-AGE-HEALTH-CAN-HIDE-EMPTY-BOARD"
affects:
  - WS:INTRADAY-FLOW-P0-RECOVERY
  - agentos/handoffs/INTRADAY-FLOW-P0-RECOVERY-2026-08-20-pr4-merge-reconciliation.md
confidence: high
reversibility: easy
decided_by: ceo-sol
decided_at: 2026-08-20
---

## Authority consequence

This decision changes workstream state and proof sequencing only. It does not
modify runtime, accept #6105 in production, authorize a second engine, resolve
AD-9, or grant signal/rank/gate/size/trade authority.

The only lawful continuation is the exact PR-4 production receipt over the
existing quote, pulse, M1/R2, health and browser paths. If the receipt finds a
failure, repair the first causal edge narrowly. Do not reopen PR-1/PR-2, re-arm
the Studio fleet, or reclassify a fresh file as a fresh source.