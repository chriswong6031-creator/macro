---
key: CNLI-OUTCOME-VECTOR
question: >
  Is the program's outcome a single first-board probability, or a vector of
  separate outcomes?
answer: >
  A vector of separate outcomes, each forecast and graded independently:
  P(first exact board), P(continuous rerating without board), P(adverse
  breakdown), P(pre-onset access), P(next-open access),
  P(continuation | actual proxy fill), and capacity/queue risk. Event hazard
  and access are never merged into one number.
rationale: >
  A model can predict locked boards yet be commercially useless: board
  probability and achievable expectancy are not interchangeable, because the
  A-share auction and seal mechanics can price an event precisely by removing
  the fills that would monetize it. The program optimizes accessible
  repricing, not board count, so access, continuation, and capacity must be
  modeled and graded separately from event hazard — separate calibration,
  separate floors, separate failure states.
alternatives:
  - option: Single P(first board) headline
    why_not: >
      Hides access destruction; a high-probability unfillable board and an
      accessible rerating grade identically. Featured-shelf allocation and
      commercial value depend on the access components the scalar erases.
  - option: Access-adjusted single expectancy score
    why_not: >
      Pre-multiplies hazard by access inside one opaque number; breaks
      per-component calibration, per-component falsifiers, and the R4/G5
      access-noninferiority gates.
evidence:
  - "research/cn_limit/CN_LIMIT_R6_FINAL_ARCHITECTURE_FREEZE_2026-08-19.md §4.6, §6.1-6.2, §12"
  - "R1 price-limit/liquidity evidence anchors, freeze Appendix B"
affects:
  - "WS:CN-LIMIT-ALPHA"
  - "research/cn_limit/"
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-19
---

Sol R6 final architecture freeze. The product-primary target is
CNLI.TARGET.FIRST_SEALED_UP_H10; the secondary targets and access/capacity
outcomes are enumerated in the freeze §6.2 and the R6 registry.
