---
key: SOL-HOLD-IS-A-MERGE-BARRIER
question: >
  Two same-day incidents (PR #5953, PR #5974, both 2026-08-19) saw PRs carrying an
  explicit CEO/Sol hold ("do NOT merge / held for Sol adversarial review") merged
  anyway by shared automation paths. Is a recorded hold binding on every merge path,
  and does conditional merge authority granted for one PR extend to any other?
answer: >
  A Sol/CEO/operator STOP or HOLD-FOR-SOL recorded on a specific PR (body or comment)
  is a MERGE BARRIER binding EVERY merge path — the merge-on-green sweeper, any
  blanket-arming session, and manual `gh pr merge` alike — regardless of label state.
  Enforcement is state, not intent: a held PR must carry no `merge-on-green` label,
  have `autoMergeRequest` null, be converted to DRAFT, and carry a hold comment naming
  the authority and the release condition (ratifying the
  DSC:CHINA-ALPHA-HOLD-MERGE-INCIDENT protocol into the decision plane). A session
  arming any PR it did not open must first grep its title+body+comments for hold
  language. Conditional merge authority granted for one PR (e.g. Sol's #5872
  finalization conditions) NEVER transfers to a sibling or successor PR — each PR's
  merge authority is granted individually or not at all.
rationale: >
  Label-based holds do not bind the merge path: the sweeper selects candidates by
  label only, blanket-arming sessions have twice overridden deliberate review freezes
  (4 of 6 armed 08-19 carried explicit holds), and #5974 merged 16:04Z against an
  explicit body hold while unarmed. The hold must therefore live in the states the
  merge paths actually consult (label absence, draft status, auto-merge state) AND be
  a named prohibition on the actors that bypass them. The non-transfer clause exists
  because #5974's merge followed immediately after #5872's authorized merge — adjacent
  authority is exactly the momentum a barrier must stop.
alternatives:
  - option: Keep the DSC protocol as a standing mitigation without a decision record
    why_not: the DSC self-flags as provisional ("until a stronger control ships"); Sol ordered the rule made durable in the decision plane after the second incident
  - option: Build a hook-enforced hold label before recording the rule
    why_not: the enforcement wave is separate reviewed work; the governing rule must bind sessions now, not after a build
  - option: Treat merge authority as session-scoped (one grant covers the session's PRs)
    why_not: that is the failure mode observed — authority bleed from an authorized PR onto a held sibling
affects:
  - "WS:ADVANCED-DATA-OPTIONS"
  - .github/workflows/merge-on-green.yml (behavioral contract, not edited here)
  - CLAUDE.md / AGENTS.md merge-discipline sections (one-line durable amendment in the same PR)
evidence:
  - "PR #5974: body 'Held for Sol adversarial review — do NOT merge' vs merged 2026-08-19T16:04:26Z (d5ebb5d9b3db) by shared automation identity"
  - "DSC:CHINA-ALPHA-HOLD-MERGE-INCIDENT (PR #5953, same day) — the 4-step hold protocol ratified here"
  - "memory blanket-arming-merges-prs-held-for-review (08-19): 4 of 6 blanket-armed PRs carried explicit holds"
  - "Sol handoff AD-1C0.1 §1 (2026-08-19/20): 'A Sol STOP / HOLD-FOR-SOL on a specific PR is a merge barrier. Conditional merge authority granted for one PR does not transfer to a subsequent PR.'"
confidence: high
reversibility: easy
decided_by: ceo-sol
decided_at: 2026-08-20
---

Scope note: this record governs merge AUTHORITY. It does not change when a merge is
technically clean (DEC:MERGE-ON-CONCLUDED-CHECKS-ONLY) or the sweeper's normal
handoff contract (DEC:DEFAULT-FINISH-HANDS-WAIT-TO-SWEEPER) — a held PR is simply
outside both until the holding authority releases it. A future hook-enforced hold
label supersedes the procedural protocol here when it ships through its own reviewed
wave.
