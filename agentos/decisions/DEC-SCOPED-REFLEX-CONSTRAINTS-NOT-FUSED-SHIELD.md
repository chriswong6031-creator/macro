---
key: SCOPED-REFLEX-CONSTRAINTS-NOT-FUSED-SHIELD
question: >
  When protection must act, does Mastermind route decisions through one
  generic shield / weighted veto router, or through separately registered,
  separately promoted, scope-bounded policy rules?
answer: >
  Scoped rules only; no fused shield and no meta-router. Each protection rule
  is individually registered (policy_id, rule_id, rule_version), individually
  promoted or explicitly temporary (authority basis earned |
  temporary_operator_safety | emergency_user_opt_in), scoped by explicit
  market/asset/candidate/lifecycle/exposure predicates, subtract-only in
  action, and printed with its receipts. Policies are never averaged or
  weighted; consumers apply every applicable rule independently and enforce
  the logical intersection, printing every rule ID. A repair rule lifts only
  the rule it owns. No envelope-wide threshold may manufacture a policy.
rationale: >
  A fused shield is a universal score wearing an action mask: its weights are
  unauditable, its false alarms are attributable to nothing, and one bug or
  one stale input silently moves every decision. Independent scoped rules keep
  authority provenance exact (which rule, whose grant, what evidence, when it
  expires), make counterfactual grading per-rule possible (GD-11), and let a
  wrong rule be killed without disturbing the rest. Subtract-only composition
  guarantees that adding a rule can never loosen protection — composition
  stays monotone and order-independent.
alternatives:
  - option: One fused shield score with veto thresholds
    why_not: >
      Opaque universal authority — banned by command packet law 3 and the
      freeze composition law (§6); repeats the legacy fused-composite failure
      with higher stakes because it would gate actions, not just displays.
  - option: A meta-router that arbitrates/weights between policies
    why_not: >
      The router itself becomes the unaudited authority; ordering and weight
      choices change outcomes invisibly. Logical intersection of subtract-only
      constraints needs no arbiter.
  - option: Additive scoring where policies can offset each other
    why_not: >
      A bullish rule could cancel a protection rule — composition must be
      monotone; offsetting reintroduces blending and makes "which rule did
      this" unanswerable.
evidence:
  - "research/grey_deer/GREY_DEER_RISK_INTELLIGENCE_ARCHITECTURE_FREEZE_2026-08-19.md §5.5 (policy fields), §6 (bounded vocabulary + composition law)"
  - "research/grey_deer/GREY_DEER_FABLE_EXECUTION_COMMAND_PACKET_2026-08-19.md §5 laws 2-3, §14 review question 9 (every action tied to a registered policy ID)"
affects:
  - "WS:GREY-DEER-RISK-INTELLIGENCE"
  - "config/reflexes.yml (future policy registrations)"
  - "prophet (eligibility sidecar consumers, future)"
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-19
---

## Grounds

Sol architecture freeze 2026-08-19 (§6). Older fused-authority risk designs
were explicitly ruled non-templates by the command packet's binding
supersession ruling (§2): their sensors are substrate, their universal-fusion
authority is not reused.

## What would reopen this

Sol only. Evidence that independently applied rules materially conflict in
practice (e.g., contradictory scope predicates producing incoherent user
states) escalates as an architecture finding — the answer may refine the
policy vocabulary or scoping grammar, never introduce a weighted arbiter
silently.
