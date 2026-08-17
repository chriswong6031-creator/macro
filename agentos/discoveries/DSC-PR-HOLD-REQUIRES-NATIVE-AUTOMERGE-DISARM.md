---
key: PR-HOLD-REQUIRES-NATIVE-AUTOMERGE-DISARM
claim: >
  Removing the custom merge-on-green label does not disable GitHub native
  auto-merge; PR #5809 still squash-merged after the custom label was removed
  because native auto-squash remained armed.
falsifier: >
  GitHub showing that PR #5809 had no autoMergeRequest at merge time, or the
  merge being performed by merge-on-green.yml rather than native auto-squash
  after 2026-08-17T05:43:30Z.
so_what: >
  A review hold must remove merge-on-green AND explicitly disable GitHub
  native auto-merge, then verify the PR reports no active auto-merge request.
  Do not treat label removal as a merge hold.
kind: landmine
verified_at: 2026-08-17
verified_by: >
  PR #5809: custom merge-on-green removed 2026-08-17T05:43:30Z with a hold
  comment; session never ran `gh pr merge`; squash-merge still landed at
  2026-08-17T07:12:55Z by account chriswong6031-creator. Sweeper log after
  that mentioned PR #5818, not #5809. Squash message carried extra
  Co-authored-by: Oracle post-heal audit.
scope:
  - macro
  - .github/workflows/merge-on-green.yml
  - WS:FINANCIAL-INTELLIGENCE-FABRIC
confidence: verified
---

## What was measured

FIF-1R on PR #5809 was held for operator review. The session disarmed the
custom `merge-on-green` label at 05:43:30Z and left a hold comment. It did
not run `gh pr merge`. At 07:12:55Z the PR squash-merged anyway.

GitHub native auto-squash had been armed separately from the house sweeper.
Removing the custom label does not clear `autoMergeRequest`.

## What a future session must do

Before announcing a PR held for review:

1. `gh pr edit N --remove-label merge-on-green` if present
2. Disable native auto-merge (`gh pr merge N --disable-auto` or equivalent)
3. Verify `autoMergeRequest` is null
4. Leave a hold comment naming the review owner

Do not redesign CI in the same change unless that is the assigned mission.
