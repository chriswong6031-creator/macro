---
workstream: "WS:CI-MERGE-CONTROL-PLANE"
session: codex/ci-plan-working-tree-containment-w3-20260822
model: codex
ended_because: ci_handoff
mission: >
  Execute Sol W3 only: reduce authoritative ci-plan working-tree
  materialization below the 60-second production SLO while preserving current
  changed-file, selection, partition, and semantic-plan identity exactly; hold
  the resulting draft PR unmerged for Sol review.
state_before: >
  Exact-head production run 32600863041 job 97098803879 spent about 283 seconds
  materializing 76,951 tracked files before a roughly two-second planner. PR
  #6261 was closed unmerged and REJECTED_BY_DESIGN because its progressive
  parent1/parent2 ancestry acquisition solved a measured non-bottleneck and
  imposed a historical merge-base dependency the current parent1...merge diff
  does not need.
changed:
  - path: .github/workflows/ci.yml
    what: >
      Make only ci-plan use a non-cone sparse checkout that includes every
      unknown/new top-level path and omits data, site, mockups, and
      verify_shots; retain fetch-depth 0 and add one runner-temp exact-tree path
      inventory producer/consumer handle. ci-pack checkout is unchanged.
  - path: scripts/ci_scope_dependencies.py
    what: >
      Add the ephemeral ci.tracked_paths.v1 writer, strict exact-tree validator,
      planner-scoped membership context, tracked file/directory existence
      helpers, and a loud content-materialization refusal. The payload is NUL
      delimited, SHA-256 bound, count bound, checkout-SHA bound, and compared
      byte-for-byte with a fresh git ls-tree of the exact tested commit.
  - path: scripts/run_ci_pack.py
    what: >
      Accept a planner-only bounded tracked-path handle, activate it only around
      manifest validation and scope derivation, and consult it only for the two
      existing ownership-existence questions. Selection, partitioning,
      changed-file semantics, pack execution, and semantic schemas are
      unchanged; invalid inventory reaches the existing full-suite fallback.
  - path: tests/test_ci_pack.py
    what: >
      Add hostile depth-two ancestry proof, inventory missing/malformed/wrong
      tree/missing-path/checkout-drift mutations, omitted-existence and
      required-content mutations, fallback and architecture-boundary tests, and
      field/byte-identical full-versus-sparse replay coverage.
  - path: tests/test_ci_plan_workflow.py
    what: >
      Pin the exact four-tree sparse profile and the single bounded exact-tree
      inventory route from identity through the planner command.
  - path: agentos/handoffs/CI-PLAN-WORKING-TREE-CONTAINMENT-2026-08-22-codex-implementation.md
    what: >
      Preserve the mechanical census, design boundaries, local parity receipts,
      production acceptance procedure, and HOLD-FOR-SOL continuation law.
verified:
  - claim: >
      The pre-profile mechanical census counted the complete tested tree and
      froze the four-tree omission boundary before workflow implementation.
    command: >
      git ls-tree -r -l -z HEAD | python3 -c '<group path count and blob bytes by
      top-level tree; total omitted versus kept>'
    result: >
      tested tree a990d05df2505ae3929172d38c6e248d627fec4d has 77,374
      tracked files and 5,241,389,763 blob bytes; data/site/mockups/verify_shots
      account for 66,066 files and 4,749,559,321 bytes; the conservative kept
      profile accounts for 11,308 files and 491,830,442 bytes.
  - claim: >
      The real planner content census identified every byte-read top-level
      surface before the profile was frozen, while separately recording
      existence-only probes and opaque traversal roots.
    command: >
      instrument Path.is_file/exists/is_dir/read_text/glob/rglob/iterdir around
      load_legacy_jobs(.github/ci/legacy-jobs.yml, gate=code) and
      build_plan(changed=['engine/inputs.py']) on the full checkout
    result: >
      4,241 unique content reads across .claude/.github/admin/app/collectors/
      engine/lib/mockups/ops/research/scripts/tests/ux-evidence; 11,956 unique
      existence-only probes; 1,184 opaque dependency findings. Existing
      audit_unrun_tests Git-object recovery supplies the two non-suite mockups
      mutation instruments when mockups is wholly omitted.
  - claim: >
      The sparse profile itself removes only the four measured heavy trees and
      materializes cleanly without changing tracked status.
    command: >
      /usr/bin/time -p git sparse-checkout set --no-cone '/*' '!/data/'
      '!/site/' '!/mockups/' '!/verify_shots/' && git status --short
    result: >
      16.16 seconds locally; all four omitted trees had zero materialized files,
      engine/tests remained present, and git status stayed clean before edits.
  - claim: >
      The owning workflow, pack, and sparse-suite files pass together after the
      initial implementation and discriminating mutations.
    command: >
      python3 -m pytest tests/test_ci_plan_workflow.py tests/test_ci_pack.py
      tests/test_audit_unrun_tests.py -q
    result: "184 passed in 627.04 seconds"
  - claim: >
      The full-tree current planner and sparse/oracle candidate serialize the
      complete authoritative plan identically across the required eight-case
      replay corpus on the same tested tree/head/base and workflow identity.
    command: >
      run one cached full-tree build_plan corpus from macro-main and one cached
      sparse build_plan corpus from the candidate, canonical-json serialize all
      plan.to_dict() documents, and require byte equality
    result: >
      complete_plan_json_byte_identical=true; tested tree
      a990d05df2505ae3929172d38c6e248d627fec4d; corpus SHA-256
      35dee6461f3781c964f476f3936f78a6fd8d1cda7eed115e510f3281b6f7e612.
      Cases cover test-only, ordinary Python, site asset, ordered old/new pair,
      global invalidator, omitted tracked literal owner, opaque data traversal,
      and passive narrative. Changed-file count/order/digest, eligible/skipped
      order, reason/summary, matrix, packs/weights, semantic IDs/digests,
      authority_changed, full JSON, and plan_sha256 are therefore identical.
  - claim: >
      The rejected parent-pair history dependency is unnecessary even at hostile
      depth two.
    command: >
      python3 -m pytest tests/test_ci_pack.py -q -k depth_two_merge
    result: >
      Synthetic merge and both direct parents are present; merge-base(parent1,
      parent2) exits 1 beyond the shallow boundary; merge-base(parent1, HEAD)
      equals parent1; changed_files(parent1) returns the exact feature path.
  - claim: >
      Inventory doubt and sparse content doubt cannot silently narrow a plan,
      and the existence oracle stays inside planner/scoping code.
    command: >
      python3 -m pytest tests/test_ci_pack.py tests/test_ci_plan_workflow.py -q
      -k 'inventory or virtual_existence or depth_two_merge or sparse_profile or
      bounded_exact_tree or partial_clone_keeps_history or full_and_sparse'
    result: "10 passed, 120 deselected in 6.44s"
unverified:
  - claim: >
      The final exact PR head completes all binding checks and at least three
      ci-plan production observations below 60 seconds.
    what_would_verify: >
      Push one final clean head, obtain the initial ci run plus same-head reruns,
      and record runner pickup, checkout/materialization step, planner step, and
      total ci-plan job durations for at least three successful observations.
      Put those volatile receipts in one PR comment so the commit SHA remains
      unchanged across all measurements.
  - claim: >
      The implementation is accepted by Sol.
    what_would_verify: >
      Sol review on the exact held PR head explicitly releases or supersedes
      DEC:SOL-HOLD-IS-A-MERGE-BARRIER. Until then the PR remains draft and
      unmerged with no merge-on-green label and native auto-merge null.
unresolved:
  - >
    Ordinary narrow-change scope inference remains the unchanged expensive
    static census (87.38 seconds on the local Mac candidate versus 72.40 seconds
    full-tree baseline). W3's production acceptance head changes global
    invalidators and therefore measures the targeted checkout bottleneck with a
    roughly three-second planner; changing scope algorithms or adding a durable
    index would be a separate authority decision and is not smuggled into W3.
  - >
    Git commit contents cannot cite production runs of their own final SHA
    without changing that SHA. The final exact-head run/job/attempt/timing and
    binding-check receipts therefore live in the held PR comment; this handoff
    records the immutable method and requires that comment before parking.
next_actions:
  - >
    Run the final owning suites, workflow validators, compile/diff checks, and
    AgentOS validation; resolve only genuine W3 regressions.
  - >
    Commit and push one clean exact head, open one DRAFT HOLD-FOR-SOL PR with no
    merge-on-green label and native auto-merge null, and post the Sol-controlled
    release condition.
  - >
    Preserve the same candidate head while collecting at least three successful
    production ci-plan observations; record pickup, checkout, planner, and total
    job durations plus exact run/job/attempt IDs in the PR.
  - >
    Require binding CI, packs, contract-delta, ci-gate, and fences concluded
    green; then report PARKED / HOLD-FOR-SOL once and stop without merging.
do_not_redo:
  - >
    Do not reopen, cherry-pick, repair, or revive PR #6261 or its progressive
    parent1/parent2 ancestry acquisition. Current changed_files(parent1) uses
    parent1...merge and requires no parent-pair merge base.
  - >
    Do not make ci-pack sparse or change its checkout; that materialization is
    W4 only after Sol accepts W3.
  - >
    Do not change merge-on-green, runner routing, pack topology/count/weights,
    contract-delta, ci-gate, semantic schemas, or product/data surfaces.
  - >
    Do not introduce a cached/durable scope store, second planner, second path
    authority, or different selection result in the name of speed.
danger_areas:
  - >
    A sparse-missing tracked file is not repository absence. All planner
    existence checks must stay behind the tested-tree oracle; content-bearing
    Python analysis must still have actual bytes or raise into full-suite
    fallback.
  - >
    Inventory validation is deliberately redundant: schema/tree/count/digest
    checks do not replace the byte-for-byte git ls-tree comparison. Removing the
    latter lets a self-consistent but incomplete inventory silently narrow.
  - >
    The sparse pattern's include-all first row keeps unknown/new top-level trees
    materialized by default. Replacing it with an allowlist turns profile drift
    into possible proof narrowing.
  - >
    The held PR is not shipped, deployed, or live. Do not arm, mark ready,
    auto-merge, manually merge, or continue polling after the ratified hold state
    is proven.
decisions:
  - "DEC:SOL-HOLD-IS-A-MERGE-BARRIER"
discoveries:
  - "DSC:CI-CHANGED-FILES-ENV-HAS-AN-EXECVE-CEILING"
---

## 0. State

W3 implementation and local parity/mutation proof are complete on a fresh
current-main branch. Production exact-head timing and binding-check proof must be
attached to the one draft PR before the session enters PARKED / HOLD-FOR-SOL.

## 1. Mechanical profile law

The pre-implementation census is the profile authority. The checkout includes
everything and subtracts only `data/`, `site/`, `mockups/`, and `verify_shots/`.
The exact tested tree still contributes all tracked paths through one ephemeral
runner-temp inventory. No inventory bytes become outputs, environment payloads,
artifacts, caches, or selection authority.

## 2. Proof law

The old full-tree planner is the oracle for W3 parity. The candidate must produce
the same changed-file bytes and order, selected/skipped order, scope diagnostics,
matrix, pack allocation, weights, semantic identities/digests, authority flag,
canonical plan document, and plan hash. Any doubt raises into the existing
full-suite fallback. Faster-but-different is failure.

## 3. Sol hold law

The terminal state is draft/open/unmerged, exact pushed clean head, concluded
binding green checks, no `merge-on-green`, native auto-merge null, and a title,
body, and comment naming Sol as the sole review/release authority. Production
timing receipts are intentionally written to the PR comment after the final head
exists. Once those facts are verified, stop; do not merge.
