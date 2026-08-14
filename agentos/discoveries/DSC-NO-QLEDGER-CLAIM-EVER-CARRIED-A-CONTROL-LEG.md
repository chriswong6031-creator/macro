---
key: NO-QLEDGER-CLAIM-EVER-CARRIED-A-CONTROL-LEG
claim: >
  Zero of the 46,630 live qledger claims declare a `control` ticker, and zero of the
  59,929 grade rows carry a non-null `control_ret` — while all 59,929 carry `bench_ret`.
  So `promotion_check(..., control_only=True)` has never once evaluated a matched control:
  every control-only verdict ever published fell through to the primary bench-relative
  `hit` and was labelled as if it were control-relative. The "matched-control excess"
  that research/MASTERMIND_INTELLIGENCE_EVALUATION_ARCHITECTURE.md and the 2026-08-12
  situation report describe as existing infrastructure exists in CODE ONLY and has never
  run on live data.
falsifier: >
  A single live claim with a non-null `control`, or any grade row with a non-null
  `control_ret`. Re-run:
  `python3 -c "import json;c=[json.loads(l) for l in open('data/qledger/claims.jsonl') if l.strip() and not l.startswith('#')];g=[json.loads(l) for l in open('data/qledger/grades.jsonl') if l.strip() and not l.startswith('#')];print(sum(1 for x in c if x.get('control')), sum(1 for x in g if x.get('control_ret') is not None))"`
  Non-zero on either number refutes this. (Counts grow nightly — the CLAIM is "zero",
  which any append can falsify; that is the point, not a defect in the record.)
so_what: >
  Do not describe the promotion gate as control-matched, in a doc, a PR body, a sitrep,
  or an external claim, until a producer actually populates `control`. Two live
  consequences a future session must not rediscover the hard way: (1) the P0c-1
  direction-correctness fix (PR #5573) repaired a LATENT bug, not an active one — the
  control branch never fired, so no published number was ever inverted by it, and
  reporting it as a live correction would be false; (2) after #5573, all 17 graded
  (family, horizon) cells move from a computed Wilson ci_low to None, which is the honest
  state and NOT a regression to be "fixed" by restoring the bench fallback. The design
  question — wire `control_for_sector()` at registration, or stop claiming a control arm
  — is a CEO decision, raised in research/EVAL_OS_SITREP_2026-08-14.md §11.
kind: dead_code
verified_at: 2026-08-14
verified_by: >
  Orchestrator-run count over origin/main's data/qledger/{claims,grades}.jsonl at
  46,630 claims / 59,929 grades; independently re-derived after the P0c-1 builder
  reported it. Also engine/qledger.py::promotion_check control_only branch, whose
  `elif hit: hits += 1` fallback is the path every live verdict actually took.
scope:
  - macro
  - engine/qledger.py
  - scripts/grade_qledger.py
  - data/qledger/**
confidence: verified
---

## Why this was invisible for so long

`make_claim()` accepts `control=`, `control_for_sector()` exists and is exported, and
`grade_claim()` prices a control leg when one is present. Every layer is built. The gate
reads `control_only=True` in both production call paths (`emit_ladder_states`,
`scripts/grade_qledger.compute_promotion_readiness`). Nothing anywhere asserts that a
control leg was actually supplied — and the branch that handles its absence falls back to
the bench-relative hit **silently**, producing a plausible number rather than a null.

A guard that produces a plausible number when its subject is absent is
indistinguishable from a working guard, which is why four months of verdicts read as
control-matched. The direction-blindness bug (PR #5573) was found first only because it
was a visible arithmetic error in the same branch; the missing control leg is the larger
finding and was found *by measuring the fix's effect* rather than by reading the code.
