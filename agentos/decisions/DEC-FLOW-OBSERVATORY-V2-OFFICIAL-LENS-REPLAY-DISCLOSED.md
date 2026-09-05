---
key: FLOW-OBSERVATORY-V2-OFFICIAL-LENS-REPLAY-DISCLOSED
question: >
  Does the official-sector lens refuse all historical replay before membership accrual
  covers the window (masterplan §9's freeze wording), or may it render replayed history
  under an explicit current-membership disclosure?
answer: >
  Disclosed replay is the ratified design (shipped in W6, PR #6812): every group history
  — official sectors included — renders a 60-session causal replay under the pinned
  caption "Replayed under today's method and today's membership — not what was published
  historically. Published record accrues from {seed_date}." The refusal that survives is
  narrower and real: no PUBLISHED-record claim, no revision markers, and no
  published-tier ticks before actual ledger accrual; the official lens additionally
  keeps its accrual-gated published-sparkline suppression and the "current membership;
  history accrues from {seed}" label. Masterplan §9's blanket-refusal sentence is
  superseded by this record.
rationale: >
  The §9 freeze predates W6's replay-honesty architecture. Once W6 introduced the
  labeled replay-vs-published split (with the caption as a REQUIRED element, tested and
  mutation-checked), a blanket refusal for one lens would have made the official lens
  the only group without investigable context while communicating LESS than the
  disclosure does — the caption states exactly the hindsight limitation §9 was
  protecting against. The final-acceptance reviewer (2026-09-04) confirmed the shipped
  form is honest and flagged only the missing decision record; this record closes that
  gap rather than reverting a better design.
alternatives:
  - option: "Enforce §9 literally — official-sector history panels refuse until accrual
      covers 60 sessions (~2027-03)"
    why_not: "Communicates less than the disclosed replay; makes one lens
      un-investigable for months while the identical hindsight limitation applies to
      curated themes, which §9 never gated."
  - option: "Silently keep the shipped behavior without a record"
    why_not: "A frozen ruling was reversed in practice; supersession must be on the
      record (the review's M1 finding)."
evidence:
  - "Final-acceptance packet 2026-09-04 (M1): live page renders the official-lens replay
    under the pinned caption; W6_SPEC.md §1 mandates the caption; mutation M1 proves the
    caption is load-bearing"
  - "templates/flow_velocity.html.j2 history drawer caption (EN/ZH); PR #6812"
affects:
  - WS:FLOW-OBSERVATORY-V2
  - research/FLOW_OBSERVATORY_V2_MASTERPLAN_BY_FABLE.md
confidence: high
reversibility: easy
decided_by: coo-fable
decided_at: 2026-09-04
---

# Official-lens replay: disclosed, not refused

Supersedes masterplan §9's blanket-refusal sentence; the §9 label + accrual-gated
published tier survive unchanged.
