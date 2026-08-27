---
key: E3FMT-STRUCTURAL-SEPARATORS-PROXY-IDENTITY-AND-SOURCE-CONDITIONED-HOLDOUT
question: >
  How must TFG distinguish a real Q&A boundary from mintable questioner identity, and how is
  development/holdout success graded without forcing guesses when held transcript source identity is noisy?
answer: >
  Treat a real named question handoff as a structural separator even when its questioner identity later
  refuses. Direct Operator-name to next-speaker equality is source-supported. A differing full-name next
  speaker is also source-supported only when that speaker's first source utterance explicitly states an
  on-for/sitting-in-for relation to the Operator-named principal; the proxy's affiliation remains unresolved
  unless independently stated. All other name disagreements/placeholders stay separator-only typed refusals.
  Never merge spans across an unresolved separator. Grade TFG against pre-adjudicated source truth: all
  independently source-clean development calls must reconstruct; source-conflicted calls must refuse for
  their frozen identity/conflict reason, not transcript cue dialect. On the unseen holdout, freeze source-only
  adjudication after implementation-head freeze but before compiler output; require at least six of eight
  fixed slots to be source-clean for adequate holdout power, then require compiler success on every clean
  slot. Never replace a dirty/no-QA/mismatched holdout slot.
rationale: >
  The post-freeze 16-call development adjudication found 110 real question handoffs: 95 direct matches,
  six explicit full-name proxy handoffs and nine unresolved questioner handoffs. It also found explicit
  management-role conflicts in ARRY and CTRE. Exactly ten calls are source-clean under the all-or-nothing
  canonicalization law, so the earlier >=12/16 non-empty bar was impossible without guessing identity or
  changing publication semantics. Structural separation preserves transcript geometry while source-conditioned
  grading keeps the method strict and scientifically testable.
alternatives:
  - option: Keep >=12/16 development and >=6/8 holdout outcome bars.
    why_not: Rejected; the development source-clean ceiling is ten calls, so the bar would reward identity invention.
  - option: Drop unresolved handoffs entirely.
    why_not: Rejected; adjacent Q&A spans could be merged across a real but unresolved question boundary.
  - option: Use edit distance or nickname matching for mismatched names.
    why_not: Rejected; transcript-local evidence does not support those corrections.
  - option: Transfer the principal analyst's affiliation to an explicit proxy.
    why_not: Rejected; acting on behalf of a named analyst does not itself source-support the proxy's affiliation.
evidence:
  - research/earnings_intelligence/e3/tfg0_development_boundary_identity_adjudication.json
  - research/earnings_intelligence/e3/TFG0_R1_BOUNDARY_IDENTITY_AND_HOLDOUT_SCORING_AMENDMENT_2026-08-27.md
  - research/earnings_intelligence/e3/tfg0_respondent_identity_feasibility_receipt.json
affects:
  - WS:EARNINGS-EVENT-INTELLIGENCE-COMPILER
  - E3-FMT
  - TFG-1
  - E3-C
confidence: high
reversibility: costly
decided_by: sol
decided_at: 2026-08-27
---

# Closed role comparison law

TFG V1 comparison aliases are exactly `CEO <-> Chief Executive Officer`, `CFO <-> Chief Financial Officer`, and `COO <-> Chief Operating Officer`. There is no open-ended `etc.` and no `CIO` alias. Other roles compare only as exact normalized title components from the same revision. The map is conflict-detection evidence only and never mints a title.

This decision grants no production revision, publication, model, scoring or E3-P authority.
