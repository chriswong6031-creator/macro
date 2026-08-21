---
key: CNLI-PROPHET-LAB-FENCED-ADJACENCY
question: >
  Is the post-R5 Prophet Operator Lab (app/prophet_lab.py and its US/Radar
  read-only projections) a CN-Limit owner path, storage seam, grader, or
  ontology source?
answer: >
  None of those. The lab is fenced adjacency: a fixture-based, all-false-
  authority US/Radar product owned by the Prophet US/Radar program. It is not
  a China candidate plane, not an exact-event grader, not a CN-Limit sidecar,
  and its detector vocabulary does not become the CN-Limit ontology. No
  CN-Limit wave touches its owner paths; a later read-only CN-Limit consumer
  inside any lab requires a separate product/owner decision after the
  canonical CN-Limit records exist.
rationale: >
  The lab landed after the R5 pin, is fixture-based rather than live-wired,
  and carries its own detector ontology. Automatic reuse would blur two
  programs' ownership, import an unproven vocabulary into a frozen ontology,
  and create a storage shortcut around the canonical China candidate/grade
  planes — the exact duplicate-plane hazard DEC:CNLI-ONE-CANONICAL-PROPHET-CHAIN
  forbids. Verified 2026-08-19: app/prophet_lab.py contains zero references to
  China candidate/rank/standout/cn_limit paths.
alternatives:
  - option: Use the lab as the CN-Limit research surface/store
    why_not: >
      Wrong owner, wrong ontology, fixture-based authority; bypasses the
      canonical candidate plane and the referential sidecar contract.
evidence:
  - "research/cn_limit/CN_LIMIT_R6_FINAL_ARCHITECTURE_FREEZE_2026-08-19.md §11.1, §12"
  - "grep -n -i 'china|cn_limit|prophet_rank|standout' app/prophet_lab.py → no matches (2026-08-19)"
  - "DSC:PROPHET-LAB-OWNS-NO-CN-LIMIT-PATHS"
affects:
  - "WS:CN-LIMIT-ALPHA"
  - "app/prophet_lab.py"
  - "research/cn_limit/"
confidence: high
reversibility: easy
decided_by: ceo-sol
decided_at: 2026-08-19
---

Sol R6 final architecture freeze (§11.1, an R6 synthesis ruling). Reversal is
`easy` in the narrow sense that a later product decision may add a read-only
consumer; the ownership fence itself stands until superseded.
