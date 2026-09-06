---
key: EXECUTIVE-ATTENTION-AUTHORITY-TARGET-SERVICEABILITY-LAW
question: >
  May EAF model reconciliation/target conflict as an exclusive replacement for urgency, or must
  authority class, attention pressure and current action serviceability remain separate so urgent
  but unsafe-to-act demand stays visible without granting authority?
answer: >
  Keep three orthogonal axes. `authority_requirement` answers which lawful authority class owns the
  decision; `attention_class` answers when scarce cognition matters and uses INTERRUPT_NOW,
  FOCUS_NOW, BATCH_NEXT, AUTONOMOUS_CONTINUE, VALID_WAIT or NON_ACTIONABLE; `serviceability`
  independently reports READY, BLOCKED, UNKNOWN or NOT_APPLICABLE with exact source-backed reasons.
  Root-cause/compaction relation is separate again. This supersedes F0's mutually-exclusive
  RECONCILE_FIRST and COVERED_BY_BUNDLE attention classes. An urgent demand whose authority, effect
  or exact Sol action target is conflicted/unavailable remains visibly urgent but blocked; urgency
  never permits action, retry, failover, sister-Sol promotion or Chairman escalation.
rationale: >
  Protected Mastermind 28d365c introduced the storeless Stage-A exact Sol action-target resolver.
  Its states make a previously implicit distinction unavoidable: an urgent Sol-class demand can
  coexist with an unavailable/conflicted/unknown exact action target, or the current observing Sol
  can be non-authoritative while another exact target is resolved. Replacing urgency with a generic
  reconcile bucket would hide executive pressure; letting urgency override target integrity would
  violate one-carrier/action-authority law. Orthogonal axes preserve both truths.
alternatives:
  - option: Keep RECONCILE_FIRST as exclusive attention disposition
    why_not: Can remove a source-backed emergency from interrupt/congestion counts simply because its action path is unsafe.
  - option: Treat high urgency as authority to select/promote another Sol
    why_not: Protected sol_action_target explicitly refuses sister-Sol promotion and owns no target transfer.
  - option: Use workstream owner as fallback exact action target
    why_not: Protected resolver requires exact root-job/CEO alias and deliberately does not consult seat/workstream defaults.
  - option: Treat protected Stage-A code as proof of live action-target availability
    why_not: Protected commit explicitly remains BUILT_NOT_PROVEN / PRODUCTION_INERT; live end-to-end use stays separately gated.
evidence:
  - "Mastermind@28d365cceaef6efb0a26e0ac9af51ead44695d60 control_plane/sol_action_target.py — exact root-job/CEO target + current RuntimeBinding resolution, observer-only behavior, fail-closed unavailable/unknown/conflict states, no target transfer."
  - "Mastermind F0F Authority, Action-Target & Serviceability Law — controlling three-axis correction and adversarial cases 35-42."
  - "Mastermind F0A concurrent-demand law — all independent interrupts remain visible after exact fan-in."
affects:
  - WS:EXECUTIVE-ATTENTION-ECONOMICS
  - WS:CHAIRMAN-CONTROL-ROOM
  - mastermind:control_plane/sol_action_target.py
  - mastermind:research/MASTERMIND_EXECUTIVE_ATTENTION_ECONOMICS_F0F_AUTHORITY_TARGET_SERVICEABILITY_LAW_2026-08-30.md
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-30
---

## Canonical correction

The final V1 information model is **authority × pressure × serviceability**, plus projection relation.
`RECONCILE_FIRST` may survive as human-facing copy but is not the canonical exclusive disposition.
`COVERED_BY_BUNDLE` is a projection relation, not proof the member ceased to be urgent.

For Sol-class demand, consume the protected exact-target contract when the source path is actually
available. Missing/unknown/conflicted target evidence blocks action but never permits fallback to a
sister Sol, a workstream owner, or Chairman. Stage-A implementation existence alone is not live proof.
