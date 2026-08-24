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

## 4. Sol proof refresh after planner-manifest movement (2026-08-23)

Sol reviewed implementation head
`0cafd0777d8f876802e6d11f6be8e2ae33e00b98` and passed the W3 architecture,
implementation boundary, fail-closed inventory semantics, oracle confinement,
mutations, and measured latency mechanism. The release hold remained because
main advanced after tested base
`659e33daed36739b5614531ef3b65d3fbfc7c19d` and changed the direct planner input
`.github/ci/legacy-jobs.yml`.

The existing carrier was refreshed without changing any W3 implementation file.
The six-path collision gate was empty before synchronization. The authoritative
parity snapshot below is pinned to:

- refreshed W3 carrier tree:
  `dc0ea3ab2c3840e4424ccd46bd938d0d74990e30`;
- merged current-main parent:
  `1e7d9f5030fd7c7c06fb03f022857510c5d0f9ed`;
- code-gate manifest population: 128 logical jobs;
- exact tested-tree inventory: 77,613 tracked paths, NUL-payload SHA-256
  `2520712631773dc37f8dd0470eec59d6d50725726c8650c1f26e1c46a417e4d1`.

The real-repository full checkout and production sparse/oracle checkout each
serialized the same eight complete `ci.pack_plan.v2` documents. Both canonical
corpus files are 294,034 bytes and have SHA-256
`397e425a02fe351f5d3c75264a11893e6e72481c888aedb2c8cf286fb7924ca6`;
`cmp` returned zero. The case receipts are:

| case | eligible / skipped | plan SHA-256 |
|---|---:|---|
| narrow test-only | 2 / 126 | `d0e5cf94d91838628d9d15289f5a85b36d9551111027bc41ecb4ac5af2522eda` |
| ordinary product Python | 72 / 56 | `ea45641fa32bcdacfe65ceebf066df2bde686a9b27317b596e49e2808acb12bb` |
| site asset | 77 / 51 | `2d67059783be102440b047b67e7e18b483bae9df49a0cdfb10b6edf775d3ffe0` |
| ordered rename/copy pair | 78 / 50 | `caa0ac81686e9eb7e89b4f6ed74e47cf8e63f207bb17cffa80b1dbd34a49b79f` |
| CI global invalidator | 128 / 0 | `d735f63aa35579c087a627a9e380d3c2829775fb0100c3c6e374ce6328cce6a0` |
| omitted tracked literal owner | 2 / 126 | `e6978ae8ee3a2734e349186f86d8a51fdd4580c86ffbbb41dd78c0b9adb446b4` |
| opaque data traversal | 80 / 48 | `fca0931e4193416fb84618db650e0f7e0e2c68eb8cf30020b02e6a17dd94ea45` |
| passive narrative | 2 / 126 | `4e2d0b608ed7861ef5224324b609eb7e056858bd5f49ed1d371424089b67e055` |

This equality covers every serialized field: changed-path bytes/order/digest,
eligible and skipped order, scope summary/reason, matrix/nonempty packs, pack
jobs and weights, semantic job/proof identities and execution digests,
`authority_changed`, complete plan JSON, and `plan_sha256`. Full-tree wall time
was 126.825 seconds and sparse/oracle wall time was 117.121 seconds; those are
local parity-census measurements, not production `ci-plan` SLO claims.

The focused fail-closed packet was rerun after synchronization:

```text
python3 -m pytest tests/test_ci_pack.py tests/test_ci_plan_workflow.py -q \
  -k 'inventory or virtual_existence or depth_two_merge or sparse_profile or bounded_exact_tree or partial_clone_keeps_history or full_and_sparse'
10 passed, 120 deselected, 3 unrelated temporary-cleanup warnings in 4.81s
```

The commit containing this addendum is the new production subject. Its exact SHA,
synthetic merge/base identity, three same-head hosted timing job IDs, authoritative
plan digest, and concluded binding-check packet are necessarily written to the
existing PR #6286 receipt comment after that immutable subject exists. Embedding
those future identifiers in their own commit would change the subject SHA and
invalidate them. The draft `HOLD-FOR-SOL` barrier remains binding throughout.

## 5. Current-main reconciliation and reproof (2026-08-24)

The sole existing PR #6286 carrier was reconciled by merge only; it was never
rebased, reset, widened, or replaced. The frozen current-manifest code tree is
`9a194a30e428856c4c986db93c967d4a2e6cf1f1`, with parents
`1b68259be59e88e9bd740b675fc27d0e42514e5c` and current main
`7424670ebe92e0324f6922563f03f48f347ebbdd`. Earlier completed proofs were
discarded when direct planner inputs moved on main; this is the required final
current-manifest proof cycle. This handoff correction is receipt-only.

The four frozen W3 implementation/test blobs are byte-identical before and
after each reconciliation:

```text
scripts/ci_scope_dependencies.py  1be36fb466d4c044018145c87d596a1ae3d7b154
scripts/run_ci_pack.py            fda27bd3293b50cb72deaae62e24865b84d346a8
tests/test_ci_pack.py             bb0005e2127f4cee8b7352e1a68ccfbacc009d35
tests/test_ci_plan_workflow.py    14b4f81ad5386ef41c39f77cc3105929766a2195
```

Local reproof on the reconciled current manifest:

```text
python3 -m pytest tests/test_ci_plan_workflow.py tests/test_ci_pack.py tests/test_audit_unrun_tests.py -q
184 passed, 3 temporary-cleanup warnings, 838.51s

python3 -m pytest tests/test_ci_pack.py tests/test_ci_plan_workflow.py -q \
  -k 'inventory or virtual_existence or depth_two_merge or sparse_profile or bounded_exact_tree or partial_clone_keeps_history or full_and_sparse'
10 passed, 120 deselected, 3 temporary-cleanup warnings, 13.41s

python3 scripts/check_workflow_yaml.py
OK: 93 workflow file(s) parse with on: + jobs: blocks.
python3 scripts/check_workflow_yaml.py --selftest
SELFTEST OK: 4 cases.
python3 scripts/run_ci_pack.py --workflow .github/ci/legacy-jobs.yml --pack-index 0 --pack-count 12 --validate-only
Validated 202 legacy jobs; 202 in scope.
```

Before push, fetch and compare fresh `origin/main` against the frozen candidate
at least for `.github/workflows/ci.yml` and `.github/ci/legacy-jobs.yml` plus
the W3 preserved inputs. Movement in those relevant inputs requires another
merge-and-reproof. Unrelated main movement is recorded as `DIRTY` and does not
alter the frozen candidate or this proof. After the handoff commit, push only
this carrier, obtain three same-head successful `ci-plan` observations under
60 seconds, wait for the concluded binding packet, write the volatile receipts
to PR #6286, and leave it `OPEN / DRAFT / HOLD-FOR-SOL` with no labels and
native auto-merge null. Do not merge.
