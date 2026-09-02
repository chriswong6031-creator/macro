---
key: BSC-E1-PR-SCOPE-FENCE-BECAME-FLEET-WIDE
claim: >
  Three BSC-E1 tests intended to prove PR #363's exact release scope became
  fleet-wide false-red assertions after merge because they recomputed
  merge-base(master, HEAD)..HEAD for whichever later pull request ran the full
  repository suite, rather than binding the immutable BSC-E1 release commit.
falsifier: >
  Read protected Mastermind
  tests/test_mastermind_executive_app_static_fences.py at
  24fa9bc4acfbffb77f09193dd50d1ee8f90bcbf8 and RET1 run
  `gh run view 33607594076 --job 100175040544`; then run the three historical
  scope tests on an unrelated branch that changes control_plane/executive_service.py.
  This discovery is false if they remain scoped to the immutable BSC-E1 release
  or the unrelated branch does not fail solely those three assertions.
so_what: >
  Historical PR-scope evidence must pin the immutable accepted release commit
  and exact parent, while reusable safety invariants may continue to run on
  current source. Protect Mastermind PR #373 before retrying RET1 #352; never
  waive the full test gate or weaken the BSC-E1 static import/source fences.
kind: landmine
verified_at: 2026-09-02
verified_by: >
  Protected Mastermind file
  tests/test_mastermind_executive_app_static_fences.py at
  24fa9bc4acfbffb77f09193dd50d1ee8f90bcbf8; GitHub Actions run 33607594076,
  job 100175040544; repair PR #373 head
  035ada3baf3a203faec8d3a1d3828439e5c3d58d.
scope:
  - WS:SOL-CAPABILITY-FABRIC
  - mastermind:tests/test_mastermind_executive_app_static_fences.py
  - mastermind:pull/352
  - mastermind:pull/373
confidence: verified
---

# Evidence

BSC-E1 PR #363 correctly rejected the original vacuous `git diff HEAD` tests.
Its repair changed the scope checks to compare the merge base of current master
and current HEAD. That was valid while evaluating PR #363 itself. Once the test
file entered protected master, the same computation no longer described the
historical BSC-E1 carrier; it described every later pull request.

RET1 PR #352 was current-based, preserved its four semantic paths and held two
independent approvals. Its full repository run failed exactly three assertions
from the protected BSC-E1 static-fence file because RET1 legitimately modifies
`control_plane/executive_service.py` and adds terminal-return paths. The
remaining repository suite and current security analyses were green. This was a
CI-owner defect, not a RET1 product defect.

# Repair boundary

PR #373 retains every reusable static import and source-safety fence. It changes
only the historical release-scope proof to bind:

```text
BSC-E1 release parent  162af533a4bcf380125895d225b6962987c3c582
BSC-E1 release commit  24fa9bc4acfbffb77f09193dd50d1ee8f90bcbf8
```

The tests require both commit objects and the exact parent relation, then prove
the exact ten added paths, complete eleven-path release, the sole
`control_plane/ceo_request.py` delta and zero
`control_plane/executive_service.py` delta. They do not consult a later PR's
HEAD or merge base.

# Consequence

Do not repair downstream carriers by excluding these tests, changing allowed
paths, or waiving the required repository check. Release the one-file owner
repair first, then recompose and retest downstream carriers on current
protected source.
