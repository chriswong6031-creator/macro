---
key: PUBLIC-BOUNDARY-FROZEN-SETS-ARE-OFF-THE-MERGE-GATE
claim: >
  PR #6141 moved only ONE of the three public-access boundary guards onto the
  merge gate. tests/test_regwall_json_gate.py got the new `gate: code` job
  `regwall-boundary`; the two FROZEN-SET guards did not. The frozen set in
  tests/test_site_access_boundary.py still runs only in `tier-gate` and the one
  in tests/test_unsubscribe_page.py
  (test_nothing_else_became_public_as_a_side_effect) runs only in
  `support-email-spine` — both `gate: data`, and ci.yml packs `--gate code`, so
  neither can red a pull request. Measured consequence: that unsubscribe guard
  sat red on main from 2026-08-20 to 2026-08-21 while three PRs (#6105, #6109,
  #6141) merged past it, and #6141's own body describes the identical failure
  mode it was closing for the sibling guard.
falsifier: >
  `grep -n "gate:" .github/ci/legacy-jobs.yml` at the `tier-gate` (~1224) and
  `support-email-spine` (~5723) job headers reporting `gate: code`, or ci.yml
  packing `--gate data` anywhere — either would mean the frozen sets are gate
  -binding after all. Also refuted if a `gate: code` job elsewhere runs
  test_site_access_boundary.py or test_unsubscribe_page.py by name.
so_what: >
  Do NOT read #6141 as "the public-access boundary is now merge-gated" — it
  closed the Caddyfile<->policy cross-check only. A path can still be promoted
  in config/site_access.yml and merge with both frozen sets red, which is the
  precise regression class those sets exist to catch. Two practical rules until
  this is closed: (1) any PR touching config/site_access.yml should run
  test_site_access_boundary.py and test_unsubscribe_page.py locally, because CI
  will not object; (2) when one of these frozen sets is found red on main, it is
  evidence of an unratified widening, never of a flake. Closing it means giving
  both suites a `gate: code` home — and note that scope INFERENCE cannot reach
  them, because both name config/site_access.yml as segment literals
  (ROOT / "config" / "site_access.yml") with no `/` in any segment, so the job
  needs `scope: exclusive` + explicit `paths:` exactly as regwall-boundary did.
kind: architecture
verified_at: 2026-08-21
verified_by: >
  .github/ci/legacy-jobs.yml — tier-gate header L1224-1226 `gate: data`,
  support-email-spine header L5723-5725 `gate: data` running
  test_unsubscribe_page.py at L5801; .github/workflows/ci.yml `--gate code` at
  L4453/L4748/L4771; .github/workflows/data-health.yml `--gate data` at L115.
  Red reproduced on origin/main @0c097d0f9621 and healed in PR #6176.
scope:
  - macro
  - .github/ci/legacy-jobs.yml
  - config/site_access.yml
  - tests/test_unsubscribe_page.py
  - tests/test_site_access_boundary.py
confidence: verified
---

## Why the drift got in three times

The promotion of a path to public has to be argued in three places: `app/deploy/Caddyfile` (what the edge serves), `config/site_access.yml` (the reviewed policy), and the two frozen sets (the review checkpoints). Only the first-to-second cross-check is now merge-gated.

- #6109 edited the Caddyfile alone → policy disagreed → caught by `test_regwall_json_gate.py`, which was `gate: data`, so it merged anyway. This is the case #6141 fixed.
- #6105 edited the policy and the `test_site_access_boundary.py` frozen set, but not the `test_unsubscribe_page.py` one → merged red.
- #6141 edited the policy and neither frozen set → merged red.

The pattern is not carelessness; it is that the third checkpoint is invisible at merge time. A guard nobody is shown is a guard nobody updates.

## What this is NOT

Not an argument that these suites are wrong to be strict. The frozen sets are deliberately absolute (`exact == PUBLIC_EXACT`, no diffing against a moving branch) and that design is sound — it is what forces a widening to be argued file by file. The defect is purely that the argument is not *required* before merge.
