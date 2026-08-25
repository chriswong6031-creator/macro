---
key: SEMANTIC-REFUSAL-BYPASSED-PROOFFRESHNESS
claim: >
  At pickup 221f72b4, sweep_pull classified advertised semantic evidence and
  returned its blocked disposition before reaching freshness.stale_for(), so a
  stale unknown/not_run_prior_failure receipt could prevent the canonical
  reproof path from ever running after its tested base had been repaired.
falsifier: >
  Run `python3 -m pytest
  tests/test_merge_on_green_semantic.py::test_stale_6391_semantic_receipt_reproves_before_unknown_can_block
  -q` against pickup 221f72b413ed8250548f6393ecb665ea894ee293 and show that
  freshness.stale_for() and reprove() run before _semantic_gate() or
  mark_blocked(), or inspect that pickup's sweep_pull and show a freshness gate
  on bound semantic-v1 evidence before the semantic blocked return.
so_what: >
  Future merge-controller changes must preserve the sequence physical anchor
  completion, semantic artifact load/binding, ProofFreshness, then semantic
  classification. Tests must discriminate stale from fresh evidence instead of
  mapping failure vocabulary to refresh behavior; legacy_absent and malformed
  evidence must remain fail-closed under their existing laws.
kind: landmine
verified_at: 2026-08-25
verified_by: >
  The focused regression failed on the pickup ordering at mark_blocked with
  `stale semantic receipt gained blocking authority`; source archaeology located
  semantic classification/return before the later freshness.stale_for/reprove
  block in scripts/merge_on_green.py:sweep_pull.
scope:
  - macro
  - ci-merge-control-plane
  - scripts/merge_on_green.py
  - tests/test_merge_on_green_semantic.py
confidence: verified
---

The receipt remained valid historical evidence. The defect was allowing that
historical evidence to decide a different, current composition. The correction
does not convert stale red to green and does not allow a failed current proof to
retry forever.
