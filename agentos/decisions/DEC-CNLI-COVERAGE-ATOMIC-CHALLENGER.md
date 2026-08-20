---
key: CNLI-COVERAGE-ATOMIC-CHALLENGER
question: >
  When a CN-Limit challenger order cannot produce a valid value for some rows
  of the frozen comparison population, may the comparison fall back to the
  incumbent's value for those rows?
answer: >
  No. A challenger order exists only when every member of the frozen
  comparison population has a valid prediction under one definition. One
  unavailable challenger row makes the entire comparison session unavailable
  — coverage is atomic, and per-row champion/challenger mixing is forbidden.
rationale: >
  Per-row incumbent fallback mixed with challenger values creates incomparable
  scales and selection bias: the challenger is scored only where it happens to
  be computable, which is correlated with exactly the data conditions being
  tested. Coverage atomicity forces missingness to be visible as an
  unavailable comparison instead of leaking into the performance delta. This
  extends the same law already ruled for the champion side in
  DEC:CN-PROPHET-V4-COVERAGE-ATOMIC-ORDER to the challenger lane.
alternatives:
  - option: Per-row fallback to the incumbent where the challenger is null
    why_not: >
      Mixes two scoring scales inside one ranking; converts coverage gaps into
      silent selection bias; makes the shelf counterfactual unattributable.
  - option: Drop uncovered rows from both arms and compare the remainder
    why_not: >
      Changes the frozen candidate population after the fact; featured-shelf
      counterfactuals are only meaningful on the full frozen set under the
      same admission rules and caps.
evidence:
  - "research/cn_limit/CN_LIMIT_R6_FINAL_ARCHITECTURE_FREEZE_2026-08-19.md §8.6, §12"
  - "DEC:CN-PROPHET-V4-COVERAGE-ATOMIC-ORDER"
affects:
  - "WS:CN-LIMIT-ALPHA"
  - "research/cn_limit/"
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-19
---

Sol R6 final architecture freeze, challenger-side counterpart of the standing
champion-side coverage-atomicity ruling.
