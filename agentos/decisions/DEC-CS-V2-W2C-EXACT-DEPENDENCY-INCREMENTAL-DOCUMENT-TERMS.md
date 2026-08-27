---
key: CS-V2-W2C-EXACT-DEPENDENCY-INCREMENTAL-DOCUMENT-TERMS
question: >
  How may the existing Capital Structure job return below its 76.5-minute
  warning without changing W2B capacity, spill, validation strength, runtime
  limits, or canonical truth?
answer: >
  Reuse the existing immutable document-term ledger only when each row remains
  bound to the exact same canonical manifest/evidence identity, retained-source
  SHA-256, filing/source fields, closed observation contract, and released
  parser version. Validate those dependencies every run without reading source
  bytes. Fully read, parse, and source-validate every new, corrected,
  missing-dependency, or parser-invalidated root before append. Preserve
  --rebuild as the deliberate whole-ledger retained-byte audit and require it
  to produce semantically and byte-identical output when no correction exists.
rationale: >
  Debt-closure job 97654020902 spent 4,712 of 4,843 seconds in direct document
  terms. Only 63 roots required extraction, while the post-compile authority
  path reread 670 roots / 4.043 GiB and re-derived 3,505 rows; 607 roots and
  3,190 observations were unchanged. Exact production-ledger replay under the
  new law reused all 670 roots with zero source reads in 9.071 seconds and
  returned the identical 3,505 observations. New evidence and parser changes
  remain dirty by construction, so the optimization removes repetition without
  weakening the source gate or creating a second cache/truth plane.
alternatives:
  - option: Raise the 90-minute cap or move the 76.5-minute warning
    why_not: Hides the structural estate-scaling defect and is explicitly unauthorized.
  - option: Reduce the 500 LIVE reserve or cap HISTORICAL spill
    why_not: Changes accepted W2B scheduling and downstream capacity policy rather than repairing unchanged-root work.
  - option: Add a cache or second compiled-root store
    why_not: Duplicates canonical truth; the existing immutable observation ledger already carries the dependency identity required for safe reuse.
  - option: Skip source validation for newly selected roots
    why_not: Breaks W1 evidence and direct-term source authority; every dirty root must retain the full byte gate.
evidence:
  - "research/CAPITAL_STRUCTURE_W2C_INCREMENTAL_DOCUMENT_TERMS_QUALIFICATION_2026-08-25.md"
  - "daily.yml run 32671784885; Capital Structure job 97292842139"
  - "daily.yml run 32786919396; Capital Structure job 97654020902"
  - "generation a6ff3b6b47db58ec549ff4508399312311f549a1"
affects:
  - "WS:CAPITAL-STRUCTURE-INTELLIGENCE-V2"
  - "engine/capital_structure/document_terms.py"
  - "scripts/compile_capital_structure_document_terms.py"
  - "tests/test_capital_structure_document_terms.py"
  - "docs/CAPITAL_STRUCTURE_INTELLIGENCE_CONTRACT.md"
confidence: high
reversibility: easy
decided_by: codex
decided_at: 2026-08-25
review_by: 2026-09-01
---

This decision changes no parser semantics, observation schema, historical row,
collector reservation, spill, carrier, job, warning, timeout, projection, or
authority. Natural production runtime remains unproven until Sol accepts and
merges both W2C and W2D and the first scheduled chain containing both completes.
