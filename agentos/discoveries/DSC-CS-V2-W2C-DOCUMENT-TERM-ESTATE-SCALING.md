---
key: CS-V2-W2C-DOCUMENT-TERM-ESTATE-SCALING
claim: >
  Capital Structure job 97654020902 crossed the 76.5-minute warning because
  the direct-document compiler's post-compile source-authority path scaled with
  the full historical document-term estate. The job used 4,712 of 4,843 seconds
  there. It extracted 63 dirty roots but reread 670 retained roots totaling
  4.043 GiB and re-derived 3,505 observations; 607 roots and 3,190 rows were
  unchanged. All 63 new roots came from accepted HISTORICAL spill, while the
  remaining 131 seconds proves checkout/setup/runner overhead was not dominant.
falsifier: >
  Show provider logs or a reproducible stage trace in which unchanged roots are
  not read/re-derived, the direct-document step is not 4,712 seconds, fewer
  than 607 roots or 3,190 rows are unchanged, the 63 dirty roots are not all
  HISTORICAL_BACKFILL, or non-document work materially explains the 80.3-minute
  wall.
so_what: >
  Keep W2B scheduling frozen. Make nightly document-term cost scale with exact
  dirty dependencies using the existing canonical ledger; retain the full
  source gate for new/corrected/parser-invalidated roots and the whole-ledger
  --rebuild audit. Do not treat a retrieval slot as permission to change
  downstream spill capacity or runtime limits.
kind: runtime
verified_at: 2026-08-25
verified_by: >
  GitHub run/job APIs and logs for 32671784885/97292842139 and
  32786919396/97654020902; git-show/pandas audit of generations 8a3628f1c2bb
  and a6ff3b6b47db; code-path count through compile_from_disk,
  _compile_document_term_records_core, source authority, and R2 get_bytes;
  production-ledger no-read replay over 8,757 manifests and 3,505 observations.
scope:
  - macro
  - capital-structure-intelligence
  - engine/capital_structure/document_terms.py
  - scripts/compile_capital_structure_document_terms.py
confidence: verified
---

This is a runtime attribution, not a W2 closure receipt. W2D discovery remains
separate, W3/W4 remain held, and natural proof is owed after both accepted
repairs merge.
