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
  - tests/test_merge_on_green.py
confidence: verified
---

The receipt remained valid historical evidence. The defect was allowing that
historical evidence to decide a different, current composition. The correction
does not convert stale red to green and does not allow a failed current proof to
retry forever.

## Second failure mode in the same seam (2026-09-05)

The ordering defect above is about evidence that is READ but out of date. The
same freshness decision carried a second, structurally identical defect about
evidence that could not be read at all.

`ProofFreshness.pull_files()` answered a bare `None` for five unrelated
conditions — HTTP 4xx/5xx/429, a non-list payload, a malformed row, an
exhausted page cap, and (through `surface_of`) a complete inventory matching no
gate. `stale_for()` mapped every one of them to `True`, and `True` is what makes
the caller run `reprove()` — an update-branch. So a failed GET on
`/pulls/{n}/files` authored a non-GET WRITE against a pull request. #6855/#6854
exposed it.

The correction classifies the observation instead of the answer:
`PR_FILES_COMPLETE`, `PR_FILES_UNAVAILABLE`, `PR_FILES_TRUNCATED_BROAD`. Only a
positively observed transport failure defers (`stale=None`, zero non-GET
effects). A truncated/broad footprint and a complete-but-unmatched surface are
ANSWERS, and both keep their prior conservative reproof unchanged. An inventory
never read through `pull_files` in this sweep also keeps the conservative path,
so nothing silently inherits the new deferral.

Falsifier: run
`python3 -m pytest tests/test_merge_on_green.py -k unreadable_files_inventory -q`
against merge parent `9b47c60d9fc5ca8f0e1b5fe9a5d0693fb141eb6e` and observe
`stale is True` with an update-branch effect for an HTTP 429/500 inventory.

So what: an unreadable proof SURFACE is silence, not staleness. A read that
failed may never author a write. `ProofFreshness` is per-sweep, so this adds no
persistent negative cache and no retry mechanism — the next ordinary sweep simply
re-observes.
