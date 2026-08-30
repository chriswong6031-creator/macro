---
key: CXI-GOV-PRECISION-GATE-IS-TRUE-PRECISION
question: >
  The CXI benchmark gate labelled "Governance A0/A1 precision" was computed as
  governance-family row pass-rate (a recall-like number its own docstring
  admitted was mislabeled). Repair it to actual precision, or rename/freeze the
  old metric?
answer: >
  Repair. From eval run v6 (2026-08-28) the >=95% governance gate binds to TRUE
  micro-averaged precision of high-authority results: for each governance-family
  row, every top-10 result with authority_class A0/A1 counts TP if it
  path-matches the row's required or acceptable sources, else FP;
  precision = TP/(TP+FP), gate NOT-MET when zero A0/A1 results are returned.
  The old row-pass-rate number is retained, renamed "Governance recall (row
  pass-rate)", and reported as an ungated informational line. A second explicit
  gate "Negative-control (no-answer) accuracy >=90%" is added in the same pass.
  Historical runs v1-v5 are untouched (append-only); their "precision" numbers
  are readable as recall via this record.
rationale: >
  Sol's C0 commission (macro-context-index-completion-20260828-sol-001) requires
  the measurement contract to be true before retrieval changes, and the C3
  promotion gates name "true governance A0/A1 precision >=95%". A pass-rate
  labelled precision inflates apparent governance quality: v5 reported 70%
  "precision" while the true precision measured on the same corpus class is
  37.7% (v7) — retrieval floods governance answers with weakly relevant
  high-authority chunks, exactly the failure the relevance-before-authority
  freeze clause names. Renaming alone would have left the promotion gate
  unmeasured; freezing would have left C3 without its named metric.
alternatives:
  - option: Rename the old metric to "governance recall" and add no precision gate
    why_not: >
      C3's promotion gate explicitly requires true governance A0/A1 precision
      >=95%; without the repaired metric the gate is unmeasurable and promotion
      claims stay dishonest.
  - option: Freeze the metric as-is with a disclaimer
    why_not: >
      Disclosing a mislabel is not repairing it — the number would keep steering
      sessions (and the org has already ruled that disclosure without
      enforcement is not repair).
  - option: Row-level precision (fraction of governance rows whose top-1 A0/A1 result is relevant)
    why_not: >
      Discards the per-result evidence the packet already carries;
      micro-averaging over all returned A0/A1 results measures the actual
      pollution rate a consumer experiences in the top-10.
evidence:
  - "scripts/context_index_eval.py: compute_governance_true_precision(); tests/test_context_index_eval.py (22 passed)"
  - "research/context_index/BENCHMARK_RESULTS.md eval run v6/v7 (2026-08-28): true precision 38.2% shared / 37.7% full vs informational recall 72.7%"
  - "research/context_index/README.md v1.6 amendment log entry"
  - "research/MACRO_CONTEXT_INDEX_COMPLETION_MASTERPLAN_BY_SOL.md §C0, §C3"
affects:
  - "WS:MACRO-CONTEXT-INDEX"
  - "research/context_index/**"
  - "scripts/context_index_eval.py"
confidence: high
reversibility: easy
decided_by: coo-fable (session claude/macro-context-index-c0-20260828)
decided_at: 2026-08-28
---

## Context

The defect was admitted in the evaluator's own docstring ("Reported as
'precision' in the gate label per README convention, but computed as row
pass-rate"). C0's audit made the repair unavoidable: the truthful full-scope
baseline (run v7) shows 61 A0/A1 results returned across 11 governance rows with
only 23 relevant — a 37.7% true precision hiding behind a 72.7% pass-rate. Any
C1+ retrieval work graded on the old number would have optimized the wrong
quantity. Sol reviews this ruling with the C0 head; if Sol re-rules, supersede
this record — do not edit it.
