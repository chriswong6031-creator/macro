---
key: BLOBLESS-CHECKOUT-WITHOUT-SPARSE-MATERIALIZES-THE-WHOLE-TREE
claim: >
  `actions/checkout` with `filter: blob:none` but no sparse-checkout profile does
  not bound working-tree materialization. The fetch begins as a partial clone,
  but the subsequent checkout requests every tracked blob in the selected tree.
  In Macro's trusted hosted planner this can spend the job's entire 30-minute
  timeout in `git checkout --force` before the PC matrix exists.
falsifier: >
  Reproduce the exact protected-main hosted-plan checkout on an ordinary Macro
  pull request and show that an unbounded `filter: blob:none` checkout neither
  requests nor materializes the full tree, or show from the exact #6556 job log
  that the 30-minute terminal event occurred outside the checkout/materialization
  step.
so_what: >
  Keep the hosted planner authoritative, but make materialization explicit. The
  main-control checkout needs only the eleven files copied into the frozen
  control artifact. The immutable candidate checkout must reuse ci-plan's
  established non-cone profile that omits only data, site, mockups and
  verify_shots, then bind omitted-path existence through the existing exact-tree
  tracked-path inventory. Do not add PC, M1 or M4 capacity for a hosted checkout
  bottleneck, and do not add a second planner, cache authority or retry plane.
kind: landmine
verified_at: 2026-08-27
verified_by: >
  Post-#6559 production-route telemetry on PR #6556, CI run 33079426385,
  hosted-plan job 98543493585: the live log reached `/usr/bin/git checkout
  --progress --force 43501928f0a8d45f736a9abb7a47546fe2321cc1`, remained
  there, and the job was cancelled by `timeout-minutes: 30` after 30m03s; no PC
  pack started. Parallel record-only PR #6553, run 33079434682, completed the
  same hosted-plan job in 8m28s, including about 6m03s in the initial main-control
  checkout, then completed trusted packs on pc-ci-1 and pc-ci-2 with ci-gate
  green. Current ci.yml already carries the semantic-safe W3 sparse profile and
  exact tested-tree tracked-path inventory that the trusted hosted planner omitted.
scope: [macro, ".github/workflows/trusted-ci-executor.yml", ".github/workflows/ci.yml", "#6351"]
confidence: verified
---

## Production receipt

PR #6559 merged the reusable-workflow ref-shape repair as
`43501928f0a8d45f736a9abb7a47546fe2321cc1` at 2026-08-27T13:54:10Z. The first
two post-merge record-only PR runs both passed
`trusted-executor-main-admission`, proving that the call reached the protected
main executor. Their next step isolated the remaining latency:

- Run 33079434682 completed the hosted planner, dispatched pack 0 to `pc-ci-2`
  and pack 1 to `pc-ci-1`, relayed both fragments, and concluded `ci-gate`
  success. Pack 0 wall time was 628.296 seconds with 17.41% peak CPU; pack 1 wall
  time was 60.8001 seconds with 7.58% peak CPU. Neither receipt indicates PC
  queue or resource pressure.
- Run 33079426385 passed admission in three seconds but its hosted planner never
  completed the first checkout. The visible log had completed fetch and was
  blocked on the exact `git checkout --force` command when the 30-minute job
  timeout cancelled it. The trusted-pack matrix and hosted relay matrix remained
  pending, so the failure preceded all self-hosted work.

These record-only runs are route telemetry, not P4 product samples. The timeout
invalidates further P4 acceptance until the hosted planner is repaired and the
post-repair clock is reset.

## Repair boundary

The control artifact copies exactly eleven files under `scripts/`; its checkout
does not need any other working-tree blob. Candidate planning still needs source
and test bytes for dependency-closure inference, so an allowlist of only the
manifest would be semantically false. The accepted boundary is the existing W3
non-cone exclusion profile plus `ci_scope_dependencies.py --write-tracked-paths`
for exact-tree existence. Unknown new top-level trees remain materialized, so
profile drift widens cost instead of silently narrowing proof.
