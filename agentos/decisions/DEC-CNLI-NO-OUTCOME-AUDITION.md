---
key: CNLI-NO-OUTCOME-AUDITION
question: >
  How many challengers may enter a CN-Limit prospective race, and what happens
  when a challenger's formula, model, calibration, or threshold changes?
answer: >
  Exactly one preregistered challenger per prospective race. Any formula,
  model, calibration, or threshold change mints a new definition hash and
  starts a new prospective era from zero; nothing carries over. Selecting the
  best of several observed challengers after outcomes is forbidden.
rationale: >
  Racing a field of challengers and promoting the best observed one converts
  a prospective test into an in-sample selection: with N challengers the
  winner's edge is an order statistic, not an effect. The program's entire
  claim to honesty is that predictions were written before outcomes under one
  frozen definition; outcome audition destroys that at the design level, which
  is why the same shape is already a standing repository kill
  (DNR:KILL-OUTCOME-AUDITION) in the per-security routing context.
alternatives:
  - option: Race several challenger variants and keep the best performer
    why_not: >
      Winner's-curse selection; invalidates the forward comparison; the
      standing DNR kill exists because this shape already burned the org once.
  - option: Retune the single challenger mid-race without a new era
    why_not: >
      Partial retuning is audition by installments — the served definition no
      longer matches the preregistered one, so the accrued record proves
      nothing.
evidence:
  - "research/cn_limit/CN_LIMIT_R6_FINAL_ARCHITECTURE_FREEZE_2026-08-19.md §8.6, §12"
  - "DNR:KILL-OUTCOME-AUDITION"
affects:
  - "WS:CN-LIMIT-ALPHA"
  - "research/cn_limit/"
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-19
---

Sol R6 final architecture freeze. G6 floors (120 candidate sessions, 2 regimes,
60 exact first-board events, no retuning) are defined in the freeze §7.4.
