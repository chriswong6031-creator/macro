---
workstream: "WS:CI-MERGE-CONTROL-PLANE"
session: sol/ci-plan-ancestry-materialization-handoff-20260822
model: sol
ended_because: ci_handoff
mission: >
  Reduce merge-critical ci-plan checkout/history acquisition toward the <60s planner SLO
  without changing semantic job selection, exact-base causality, plan identity, pack
  partitioning, contract-delta, or ci-gate authority.
state_before: >
  Production merge-control is already GitHub-hosted (runner-fleet W1 done), and the
  ship-loop HOLD precedence defects are closed. Hosted CI capacity is healthy, but live
  PR runs still spend minutes in repository checkout/materialization. Current ci-plan
  checks out the exact synthetic merge with filter=blob:none and fetch-depth:0. Current
  ci-pack jobs are shallow fetch-depth:1 but materialize the full working tree. The
  planner rewrite prep was frozen on 2026-08-20 while runner W1 proof occupied the plane;
  that blocker is now gone.
changed:
  - path: agentos/handoffs/CI-PLAN-ANCESTRY-MATERIALIZATION-2026-08-22.md
    what: Current-main implementation handoff for the bounded planner-only rewrite.
decisions:
  - DEC: no planner sparse-working-tree change in this slice; scope inference depends on
      real filesystem existence across first-party roots including data/ and site/.
  - DEC: fetch-depth:0 is a mechanism, not the semantic invariant; the invariant is the
      exact synthetic merge, exact immutable parents, true PR merge-base, exact changed
      file inventory, and identical plan/evidence identity.
  - DEC: immediate parent availability is insufficient proof of ancestry. A shallow
      topology can contain both synthetic-merge parents while their true merge-base is
      still outside the shallow boundary.
verified:
  - claim: Current ci-plan is hosted and uses filter=blob:none plus fetch-depth:0 on github.sha.
    command: inspect .github/workflows/ci.yml on main
    result: verified on current main lineage before this handoff.
  - claim: ci-plan identity derives parent 1 as tested_base_sha and requires parent 2 to equal the signed event head.
    command: inspect ci-plan 'bind the exact tested tree and base' step
    result: verified; exact two-parent synthetic merge remains load-bearing.
  - claim: planner scope inference reads the checkout filesystem and treats omitted files as nonexistent.
    command: inspect scripts/ci_scope_dependencies.py direct_reads/_resolve/_SCAN_ROOTS
    result: verified; _SCAN_ROOTS includes app, admin, collectors, config, content, contracts, data, docs, engine, lib, ops, research, scripts, site, templates, tests, tools, worker and Path.is_file() participates in ownership derivation.
  - claim: pack checkout waste is separate from planner history acquisition.
    command: inspect current ci-pack checkout and live #6251 CI run 32593017581
    result: packs use fetch-depth:1/full working tree; all 12 hosted jobs were assigned but spent minutes independently materializing the repository before test payloads.
unverified:
  - claim: Targeted ancestry acquisition can meet the <60s planner SLO on production PRs.
    what_would_verify: exact-head PR run with named checkout/ancestry timings and unchanged plan receipt.
  - claim: A specific deepen/fetch strategy is optimal.
    what_would_verify: controlled topology tests plus production timing; do not freeze a guessed constant shallow depth.
unresolved:
  - The workflow patch itself is NOT BUILT in this handoff. This record is SPEC_ONLY until an operator patches ci.yml and its owning tests.
  - Pack-specific sparse manifests remain a separate follow-on only after this planner slice is production-proven.
next_actions:
  - Execute the bounded implementation sequence below from fresh current main.
  - Stop if any same-tree plan identity field or selected-job set differs.
do_not_redo:
  - Do not restore or cherry-pick the stale claude/ci-traffic-jam-structural-fix or claude/ci-pack-path-selection branches; both are thousands of commits behind and predate current semantic-proof contracts.
  - Do not call fetch-depth:2 sufficient merely because both immediate parents exist.
  - Do not sparse-thin ci-plan in this PR; omitted filesystem subjects can alter inferred scope.
  - Do not edit merge-on-green, runner routing, pack count/weights, gate code/data split, contract-delta semantics, or ci-gate authority.
danger_areas:
  - A speedup that silently narrows selected jobs is a correctness regression even if CI is green.
  - A PR merge SHA is synthetic evidence; mutable branch tips or event base refs are provenance only, never substitutes for exact tested parents.
  - Main moves frequently via publishers and concurrent product PRs; acceptance must bind the exact candidate head and tested synthetic merge, not an earlier local comparison.
---

# Observable mission

Make `ci-plan` stop paying for an unbounded full-history checkout when the planner only
needs exact immutable ancestry and the current working tree. The user-visible/machine
outcome is a faster first authoritative CI decision: sessions learn which semantic packs
are required sooner, while the same jobs and same `ci.semantic_evidence.v1` authority
remain binding.

**Target:** `ci-plan` <60 seconds p95 for ordinary PRs, or a material step toward that
SLO with named production timing receipts. This slice is not accepted on local speed
alone.

# Authority and precedence

1. Current `WS:CI-MERGE-CONTROL-PLANE` and the semantic-proof contracts already on main.
2. `research/CI_PLAN_CHECKOUT_MATERIALIZATION_REWRITE_PREP_2026-08-20.md` — the newer,
   narrower Sol freeze for this exact planner-history repair.
3. `research/CI_LATENCY_AND_AUTONOMOUS_HEALING_MASTERPLAN.md` — program SLOs and later
   W4 pack-materialization objective.

If a convenience conflicts with exact semantic identity, exact identity wins.

# Verified current production state

Current `ci-plan` is the sole selection/partition authority. Its checkout is:

- `ref: ${{ github.sha }}`
- `filter: blob:none`
- `fetch-depth: 0`

The identity step then requires:

- local HEAD equals `GITHUB_SHA`;
- PR `GITHUB_SHA` is exactly one two-parent synthetic merge;
- parent 2 equals `github.event.pull_request.head.sha`;
- parent 1 becomes `tested_base_sha`;
- PR planning uses `--changed-from tested_base_sha`;
- plan artifact binds tested tree, subject head, tested base, changed-files digest/count,
  selected logical jobs, pack allocation, semantic execution digests and plan SHA.

`run_ci_pack.py` performs scope inference against files that actually exist in the
working tree. `ci_scope_dependencies.py` calls `Path.is_file()` while resolving imports,
path literals and traversals, and its scan-root vocabulary includes `data/` and `site/`.
Therefore a sparse planner checkout is NOT equivalent unless a separate consumer/filesystem
census first proves it. That is outside this PR.

# Exact scope

Repository: `mastermindx-market-intelligence/macro`.

Allowed implementation files:

- `.github/workflows/ci.yml` — **ci-plan checkout/ancestry acquisition only**;
- `tests/test_ci_plan_workflow.py` — replace mechanism-level full-history pin with
  behavioral ancestry contract;
- one narrowly named topology helper/test file if needed to construct shallow Git
  fixtures. Prefer the existing test file unless a helper materially improves clarity.
- update this handoff/AgentOS state only after production proof.

# Explicit non-goals

Do not modify:

- `scripts/merge_on_green.py` or merge authority/routing;
- `scripts/run_ci_pack.py` selection semantics;
- pack count, weights, matrix semantics or job ownership;
- code-vs-data gate split;
- contract-delta semantics;
- `ci-gate` authority/name;
- ci-pack checkout/materialization in this PR;
- runner policy or any M1/PC route;
- semantic evidence schemas;
- any product/data surface.

# Deterministic method

No model/LLM/statistical runtime logic is involved. This is deterministic Git topology
and byte/field identity validation.

The implementation must separate **working-tree materialization** from **ancestry
availability**:

1. Checkout the exact event SHA with blob filtering and a deliberately shallow initial
   history sufficient to materialize the current tree and expose the immediate synthetic
   parents. Do not claim the chosen initial depth proves merge-base ancestry.
2. Run the existing exact two-parent identity checks before publishing any identities.
3. For a PR, prove both parent objects are present and keep parent 1/parent 2 meanings
   unchanged.
4. Establish the **true merge-base of tested_base_sha and subject_head_sha**. If Git
   cannot answer because the repository is shallow, acquire more ancestry from immutable
   SHAs/refspecs in a bounded, observable sequence. A safe implementation may use
   progressive deepening and/or exact-SHA fetches; the algorithm must test the merge-base
   after each acquisition rather than assume a numeric depth is enough.
5. If the bounded targeted path cannot establish the true merge-base, use an explicit
   correctness fallback that acquires sufficient history and records that fallback in the
   log. The fallback may cost the old latency; it may never produce a narrowed plan.
6. Only after ancestry proof succeeds, run the existing planner unchanged.

**Do not make `fetch-depth: 2` the law.** A fixture must prove that a synthetic merge can
have both immediate parents locally while `git merge-base parent1 parent2` still fails
because their common ancestor is outside the shallow boundary.

# Data / contract / time / null / correction behavior

- `tested_tree_sha`: exact synthetic merge SHA; never null on a successful plan.
- `tested_base_sha`: exact parent 1; never replaced with a mutable main tip.
- `subject_head_sha`: exact parent 2; must equal signed event head.
- true PR merge-base: must be computable before scoped planning is authoritative.
- changed-file list: exact current production semantics and ordering/digest rules.
- planner uncertainty: fail closed or take the current full-history correctness fallback;
  never reinterpret missing ancestry as an empty/smaller diff.
- main/workflow_dispatch: preserve the current one-tree/head/base identity and no
  `--changed-from` behavior.
- no wall-clock heuristic may decide correctness. Timings are observability only.
- if main advances during the PR, GitHub's regenerated synthetic merge is the new proof
  candidate; do not reuse an earlier plan as if it were current.

# Failure states

The implementation must fail or safely fall back on all of these:

1. checked-out HEAD != event SHA;
2. PR event SHA is not exactly two-parent;
3. parent 2 != signed event head;
4. either parent object missing;
5. true parent1/parent2 merge-base unavailable after targeted acquisition;
6. targeted fetch/deepen command fails or is rate/network refused;
7. changed-file digest/count differs from the old planner on the same tested tree;
8. eligible/skipped logical job IDs differ;
9. pack matrix/jobs/weights differ;
10. semantic job execution digests differ;
11. plan SHA differs for the same workflow_run_id/tree/head/base/manifest inputs;
12. contract-delta or ci-gate changes behavior.

A latency miss is not permission to weaken any of these.

# Ordered implementation sequence

1. Start from fresh current `main`; record base SHA.
2. Re-read the exact `ci-plan` checkout and identity step; do not transplant stale branch
   implementations.
3. Add the hostile Git-topology regression first:
   - create base history long enough that the PR branch point lies outside depth 2;
   - create divergent base/head commits;
   - create a synthetic two-parent merge;
   - shallow clone/fetch so merge + both parents exist;
   - prove `git cat-file -e` succeeds for both parents while `git merge-base` cannot yet
     resolve;
   - acquire the required ancestry with the proposed helper/commands;
   - prove the exact true merge-base then resolves.
4. Replace `test_ci_plan_checks_out_full_history_for_the_base_diff` (or its current
   equivalent) with behavioral assertions. The test must no longer bless
   `fetch-depth: 0` as the invariant; it must bless exact ancestry and fail-safe fallback.
5. Patch only `ci-plan` checkout/history acquisition. Preserve identity step outputs and
   planner invocation byte-for-byte unless a tiny shell helper is strictly required.
6. Run the planner twice on representative fixed synthetic merges: old mechanism vs new
   mechanism. Compare all acceptance fields below.
7. Exercise deliberately insufficient ancestry and forced targeted-fetch failure. It must
   fail/fallback, never emit a narrowed authoritative plan.
8. Open one PR. Do not mix pack sparse manifests or preflight work into it.
9. Require exact-head `fences`, `contract-delta`, all selected semantic packs and
   aggregate `ci-gate` green.
10. Record production timings from the PR's own `ci-plan` job. Compare checkout start/end
    and total planner wall time to named recent full-history baselines.
11. Only if correctness and timing both pass, merge normally and record merged-main
    containment.

# Acceptance tests

For identical tested inputs, old and new planner must have identical:

- `tested_tree_sha`;
- `tested_base_sha`;
- `subject_head_sha`;
- `changed_files_sha256`;
- `changed_files_count`;
- eligible logical job IDs in order;
- skipped logical job IDs in order;
- `pack_jobs`;
- `pack_weights`;
- emitted matrix/non-empty pack indices;
- semantic job IDs/proof IDs/execution digests;
- `authority_changed`;
- `plan_sha256` (holding workflow_run_id and other identity inputs constant in the
  comparison harness).

Mutation/negative controls:

- depth-2 immediate-parent-only topology must NOT count as sufficient ancestry;
- wrong parent-2 head must fail;
- missing merge-base after bounded acquisition must fail/fallback;
- a forced fetch failure must not yield `changed=[]` or a smaller job set;
- main/workflow_dispatch full-suite identity must remain unchanged.

# Production proof

Do not accept on green CI alone. The PR must show:

- exact candidate head and synthetic merge under test;
- `fences` success;
- `contract-delta` success;
- every selected `ci-pack-*` success;
- `ci-gate` success;
- no semantic-evidence infrastructure finding;
- named `ci-plan` checkout/ancestry duration and total job duration;
- comparison against a recent production `ci-plan` full-history baseline;
- no runner-route or merge-control diff.

Target is <60 seconds p95 for planner; for this first production PR, require a material
improvement and no correctness drift even if the single sample does not establish p95.

# Stop condition

STOP and revert the optimization if any plan/evidence identity differs for the same tested
inputs, if true merge-base cannot be established without an unsafe assumption, if a
failure path can emit a smaller changed-file set, or if exact-head semantic CI becomes
less authoritative.

Do not paper over a failed topology test with a larger guessed shallow depth.

# Required continuation handoff

After this planner slice is merged and production-proven, hand off **W4 pack
materialization** separately. That continuation must mechanically census the filesystem
consumer set for each logical job/pack before producing planner-signed sparse manifests.
Do not infer pack needs from the fence sparse checkout or from import closure alone: legacy
commands may read arbitrary fixtures, contracts, templates, data and site subjects.
