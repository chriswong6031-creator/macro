---
key: REVIEW-HOLD-PROSE-IS-NOT-FAIL-CLOSED
claim: >
  A PR body saying "Do not merge", the absence of merge-on-green, and a
  disabled GitHub native auto-merge request together do not create a
  fail-closed Sol-review-required state: PR #5837 still squash-merged on
  2026-08-17T16:08:09Z while its own squash message said the work was held
  for Sol review.
falsifier: >
  GitHub showing PR #5837 was not merged, or a machine-readable review-hold
  state that every sweeper, native auto-merge path, and ship-loop release
  contract refused before that squash.
so_what: >
  DSC:PR-HOLD-REQUIRES-NATIVE-AUTOMERGE-DISARM is incomplete. Architecture-
  review PRs need a separate CI-control-plane correction that creates one
  canonical machine-readable hold (for example sol-review-required) respected
  by every merge path. Do not treat PR-body prose, label removal, or
  --disable-auto as sufficient. Do not mix that control-plane work into
  FIF-1R3.
kind: landmine
verified_at: 2026-08-18
verified_by: >
  PR #5837 closed/squash-merged as fb66ea51c4dc6db223555413c2d71eee98fba178
  at 2026-08-17T16:08:09Z. PR body and squash message both said do not merge /
  held for Sol review. Actor not proven from available evidence; cause not
  invented.
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

The house default still tells ordinary PRs to arm merge-on-green. That default
collides with major-program architecture review unless a mechanical exception
exists.

## What a future session must do

FIF packet-contract PRs: do not arm merge-on-green; disable native auto-merge;
leave a hold comment; stay until Sol accepts. That is still only a convention.

The fail-closed queue is a separate program. Do not build it inside FIF-1R3.
