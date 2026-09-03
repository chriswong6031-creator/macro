---
key: OUTCOME-LEARNING-TWO-DECISION-CANARY-GATE
question: >
  May the Outcome Learning program begin randomized handoff-policy treatment before an
  explicit Agent OS decision authorizes the canary, and may its baseline arm dispatch a
  handoff that has not passed the same current mandatory legality/completeness admission
  as the machine-preflight arm?
answer: >
  No. Require two distinct ordinary Agent OS decisions. A pre-canary DEC may authorize
  one bounded experiment only after independent protocol review and complete treatment,
  legality, eligibility, probability, evidence, privacy, stop and rollback rules are
  frozen. A later post-canary DEC may promote, continue, hold, roll back or reject the
  policy only after terminal and delayed outcomes mature and receive independent review.
  Both arms must first pass the same canonical mandatory handoff admission; the candidate
  adds only the deterministic machine preflight/checksum. No malformed or otherwise
  unlawful handoff may be dispatched as a baseline control.
rationale: >
  Random assignment between organizational procedures is itself a policy intervention,
  not neutral measurement infrastructure. A promotion decision issued after results are
  known cannot retroactively authorize the treatment that generated them. Requiring a
  pre-canary decision preserves authority, prospective design, rollback and participant
  safety, while a separate post-canary decision prevents protocol approval from being
  mistaken for evidence of benefit. Applying the same mandatory legality gate to both
  arms isolates the incremental value of machine preflight among already-lawful handoffs
  and avoids manufacturing contrast by exposing workers or the organization to packets
  that current law forbids. No-effect shadowing and unchanged-policy prospective baseline
  collection remain available before treatment and can establish event integrity,
  missingness, maturity, clustering and feasible canary design without changing behavior.
alternatives:
  - option: Authorize the randomized canary implicitly through the OL-0 architecture merge
    why_not: >
      A records-only architecture decision defines a future method but does not authorize
      a concrete treatment population, assignment probability, evidence envelope, privacy
      boundary, stop threshold or rollback owner on an action-time runtime state.
  - option: Run the canary first and let one OL-6 DEC review and promote it afterward
    why_not: >
      This conflates permission to intervene with interpretation of the observed result,
      invites post-hoc protocol repair, and leaves the first treated assignment without an
      explicit authority and rollback ruling.
  - option: Compare canonically complete candidate handoffs with incomplete baseline handoffs
    why_not: >
      Current handoff law is a mandatory safety and authority floor, not an experimental
      variable. Such a comparison would be unsafe, causally ambiguous and operationally
      irrelevant to the incremental effect of deterministic preflight.
  - option: Require a pre-canary DEC and treat it as automatic permission to promote on success
    why_not: >
      Protocol authorization does not establish benefit. Mature outcomes, corrections,
      uncertainty, Goodhart risk and guardrails require independent post-canary review and
      a separate policy decision.
  - option: Use no-effect shadowing and prospective baseline collection before either DEC
    why_not: >
      This is accepted rather than rejected, provided the worker-visible handoff, recipient,
      carrier, START decision and execution path are unchanged and every output remains
      descriptive/advisory.
evidence:
  - "docs/superpowers/specs/2026-08-30-outcome-learning-policy-calibration-design.md — original first-consumer, authority, canary and completion architecture"
  - "docs/superpowers/plans/2026-08-30-outcome-learning-policy-calibration.md — original OL-5/OL-6 sequence requiring correction"
  - "docs/superpowers/specs/2026-08-30-outcome-learning-policy-calibration-governance-amendment.md — binding two-decision, compliant-arm and real-evidence amendment"
  - "docs/sol_skills/INDEX.md at Mastermind@620263090fb9f272f763e420ba103b0ff8dc5f31 — explicit Chairman intent, one-carrier, owner and no-duplicate authority laws"
  - "docs/EXECUTIVE_CHAT_NATIVE_SOL_HIERARCHY_LAW.md — delivery, ACK, START, execution, result and authority remain distinct"
  - "Canonical Slack carrier C0BSBM78V1N/1788078701.538999 — Chairman outcome requires explicit Sol/Auditor/DEC review, canary/shadow evaluation and rollback rather than automatic self-editing"
affects:
  - organizational-learning
  - docs/superpowers/specs/2026-08-30-outcome-learning-policy-calibration-design.md
  - docs/superpowers/plans/2026-08-30-outcome-learning-policy-calibration.md
  - docs/superpowers/specs/2026-08-30-outcome-learning-policy-calibration-governance-amendment.md
  - agentos/workstreams/WS-OUTCOME-LEARNING-POLICY-CALIBRATION.md
  - mastermind/control_plane/outcome_learning_*.py
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-30
---

## Binding operational consequence

The current sequence is:

```text
OL-4A owner-native expectation capture
-> OL-4B no-effect shadow instrumentation
-> OL-4C unchanged-policy prospective baseline and maturity corpus
-> OL-4D descriptive readiness study
-> independent protocol review
-> PRE-CANARY DEC
-> OL-5B bounded randomized canary
-> terminal and delayed outcome study
-> independent post-canary review
-> DSC consequence
-> POST-CANARY DEC
-> OL-7 owner-native rollout or rollback and delayed production proof
```

The pre-canary DEC choices are:

- `AUTHORIZE_BOUNDED_CANARY`
- `HOLD_FOR_REPAIR`
- `REJECT_CANARY`

The post-canary DEC choices are:

- `PROMOTE_BOUNDED`
- `CONTINUE_CANARY`
- `HOLD`
- `ROLLBACK`
- `REJECT`

No treatment assignment exists before `AUTHORIZE_BOUNDED_CANARY`. No policy promotion exists before the post-canary DEC. A compiler, validator, study recommendation, model-generated explanation, PR merge, or green check grants neither authority.

## Shared arm-admission law

Both baseline and candidate episodes must first satisfy the exact current canonical handoff legality and completeness gate. The baseline then uses the compliant incumbent procedure. The candidate adds the deterministic machine preflight/checksum. Randomization occurs only after legality, study eligibility, source snapshot and assignment probability have been sealed.

If current law, ownership or packet requirements change during the canary, new assignments stop until the protocol is reconciled. Existing episodes remain analyzable under their recorded policy version; they are not silently relabeled.

## No-effect work before authorization

Before the pre-canary DEC, the program may compute hypothetical arms, validate owner references and event identity, test correction/maturity/missingness semantics, and collect unchanged-policy baseline episodes. Such work must not alter the worker-visible packet, recipient, carrier, admission, START or execution path. Its highest causal claim is `DESCRIPTIVE_ONLY`; unsupported questions remain `NOT_IDENTIFIED`.

## Supersession boundary

This decision supersedes only any earlier Outcome Learning wording that places treatment before explicit authorization, treats the baseline as exempt from mandatory handoff law, collapses protocol authorization and policy promotion into one decision, or calls synthetic test fixtures real operating evidence.

It does not supersede the selected federated architecture, canonical owner boundaries, historical-routing causal limitation, privacy rules, correction semantics, no-rebuild law, or the requirement to prove one real bounded improvement with delayed guardrails before program completion.