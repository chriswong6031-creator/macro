---
key: REVIEW-HOLD-PROSE-IS-NOT-FAIL-CLOSED
claim: >
  A PR body saying "Do not merge", the absence of merge-on-green, and a
  disabled GitHub native auto-merge request together do not create a
  fail-closed Sol-review-required state. PR #5837 squash-merged on
  2026-08-17T16:08:09Z while held for Sol review. PR #6157 squash-merged
  on 2026-08-21T16:08:36Z as 56d1a36caa43ca2a8ea4570808edca75ca2fc334
  while its body and comments still said HOLD FOR SOL / do not merge,
  labels were empty, and autoMergeRequest was null.
falsifier: >
  GitHub showing PR #5837 or PR #6157 was not merged, or a machine-readable
  review-hold state that every sweeper, native auto-merge path, and ship-loop
  release contract refused before those squashes.
so_what: >
  DSC:PR-HOLD-REQUIRES-NATIVE-AUTOMERGE-DISARM is incomplete. Architecture-
  review PRs need a separate CI-control-plane correction that creates one
  canonical machine-readable hold (for example sol-review-required) respected
  by every merge path. Do not treat PR-body prose, label removal, or
  --disable-auto as sufficient. Do not diagnose or repair that control plane
  inside a FIF packet or FIF records PR; it belongs to its existing owner.
kind: landmine
verified_at: 2026-08-21
verified_by: >
  PR #5837 closed/squash-merged as fb66ea51c4dc6db223555413c2d71eee98fba178
  at 2026-08-17T16:08:09Z. PR #6157: body started "HOLD FOR SOL — do not
  merge"; comments 5365329297 (2026-08-21T04:49:09Z) and 5368311316
  (2026-08-21T09:51:05Z) restated the hold and that autoMergeRequest was
  null / merge-on-green unarmed; GraphQL after merge still reports
  autoMergeRequest null and labels []; mergedAt 2026-08-21T16:08:36Z as
  56d1a36caa43ca2a8ea4570808edca75ca2fc334 by chriswong6031-creator.
  Cause not invented.
scope:
  - macro
  - .github/workflows/merge-on-green.yml
  - WS:FINANCIAL-INTELLIGENCE-FABRIC
confidence: verified
---

## What was measured

FIF-1R2 on PR #5837 was held for Sol review. The R2 worker recorded that
removing merge-on-green is insufficient and native auto-merge must also be
disabled. #5837 subsequently merged anyway.

This is the second review-hold incident in the same program after #5809.

FIF-2B on PR #6157 is additional evidence of the same gap. The PR was not
draft. Native auto-merge was null. `merge-on-green` was not authorized.
The body and two hold comments named Sol as the release authority. GitHub
still squash-merged the PR at 2026-08-21T16:08:36Z, before Sol source
review accepted head `55663277a32c12251dbeb80945d0abcf36570b58`. Sol later
accepted that head; the accepted product code was not reverted. This
record does not diagnose the merge actor or repair the control plane.

The house default still tells ordinary PRs to arm merge-on-green. That
default collides with major-program architecture review unless a mechanical
exception exists.

## What a future session must do

FIF packet-contract PRs: do not arm merge-on-green; disable native auto-merge;
leave a hold comment; stay until Sol accepts. That is still only a convention.

The fail-closed queue is a separate program. Do not build it inside a FIF
packet PR, FIF-2C, or a FIF records PR.
