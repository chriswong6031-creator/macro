---
key: DARK-STEP-VOIDS-THE-WHOLE-MAIN-AGGREGATE
claim: >
  A single main-role semantic step that goes DARK behind an earlier failing step
  in the same job (outcome not_run_prior_failure, and equally timed_out /
  infrastructure_blocked) voided the ENTIRE aggregate semantic-evidence artifact
  for that run — emitted as jobs: [] plus one planner_configuration_failure —
  because reconcile_evidence() stamped classification=main_failure on any
  non-passed main outcome while the aggregate validator requires
  outcome=="failed" for that classification. Since
  ship_loop_guard.py's find_descendant_pass_witness() walks evidence["jobs"],
  jobs: [] means NO session in the fleet can mint a descendant-PASS witness for
  ANY job, so every session with a blocked Stop stays blocked no matter how green
  its own work is. The per-pack fragments still hold the true per-step outcomes;
  nothing reads them.
falsifier: >
  A main ci.yml run that is red on a job with further semantic steps after the
  failing one, whose ci-semantic-evidence-<run> artifact nonetheless carries a
  non-empty jobs list — that would mean the voiding had some other trigger. Or
  find_descendant_pass_witness() gaining a per-pack fragment fallback, which
  would make the aggregate non-load-bearing.
so_what: >
  When the whole fleet is Stop-blocked at once and no session can attribute its
  reds, read the AGGREGATE artifact FIRST and check whether jobs is empty, before
  attributing any red to your own head. An empty jobs list is a classifier fault,
  not a verdict about your work, and no amount of healing your own PR clears it.
  The trigger red is incidental — any main red with downstream steps in the same
  job reproduces it, which at main's ~44% green rate is most nights.
kind: architecture
verified_at: 2026-08-19
verified_by: >
  main run 32231891958 (head 636890c0ff52, concluded 09:01Z). Per-pack artifact
  ci-semantic-pack-32231891958-1 records logical_job_id workflow-yaml with
  "audit_unrun_tests selftest" outcome=passed, then the failing census step, then
  "unrun-census discovery unit tests" outcome=not_run_prior_failure detail "an
  earlier semantic step did not pass"; the aggregate
  ci-semantic-evidence-32231891958 carries jobs: [] and detail "evidence
  classification requires a failure for workflow-yaml/unrun-census discovery unit
  tests". Reproduce with `gh run download 32231891958 -p "ci-semantic-*"`.
  Fix + fail-before-fix regression tests in PR #5964.
scope:
  - macro
  - scripts/ci_semantic_proof.py
  - .claude/hooks/ship_loop_guard.py
confidence: verified
---

## Why it hid for so long

Latent since #5750. The `pr_head` path has always had the correct guard — it
calls `classify_head_failure()` only when `outcome == "failed"` and otherwise
falls through to `unknown`. Only the `main` branch skipped it, so the defect can
never be reproduced from a pull request; it needs a red on main, in a job that
has more semantic steps after the one that failed.

## The blast radius is inverted

The louder symptom (one red check) is the trivial half. The quiet half — an
aggregate artifact that validates itself out of existence — takes down witness
minting for *every job in the repository*, and it does so with an error message
that names one unrelated proof id. A session reading that message reasonably
concludes it has a `workflow-yaml` problem. It does not; it has no evidence
plane at all.

## Not a greening

`unknown` is already a legal main-role classification, and
`semantic_gate_verdict()` still refuses to clear on it. A dark step is honestly
unknown: it never ran, so it neither passed nor failed. Classifying it as a
failure was also wrong for attribution — it invented main failures that the
tape never observed.
