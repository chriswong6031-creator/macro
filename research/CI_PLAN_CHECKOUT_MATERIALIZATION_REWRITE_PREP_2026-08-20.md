# CI plan checkout materialization — bounded rewrite prep

**Date:** 2026-08-20  
**Authority:** `WS:CI-MERGE-CONTROL-PLANE` / `W-REWRITE`  
**Prepared by:** Sol  
**Status:** prepared_not_commissioned  

## Observable mission

Remove the merge-critical `ci-plan` checkout/materialization tax without changing semantic job selection, plan identity, exact-base causality, fail-safe widening, pack partitioning, or `ci-gate` authority.

This is a CI-control-plane optimization, not a runner-fleet routing change. It must be built/reviewed under `WS:CI-MERGE-CONTROL-PLANE` authority after the current runner-fleet W1-A acceptance is no longer consuming the proof plane.

## Why this matters

The runner-fleet resilience program repeatedly exposed a second, independent shipping bottleneck on GitHub-hosted runners:

- repaired `fence-pack` now checks out a bounded sparse surface in seconds;
- `ci-plan` still uses a full-history checkout and materializes the large repository before a plan computation that itself is fast;
- full-suite PRs then launch twelve `ci-pack` jobs, each of which independently materializes the full tree before executing its assigned semantic jobs.

This is not M2 self-hosted starvation. It is hosted Git transport / working-tree materialization cost in the canonical CI control plane.

## Verified current state

Current main's owning contract test is `tests/test_ci_plan_workflow.py`.

It contains `test_ci_plan_checks_out_full_history_for_the_base_diff()`, which requires exactly one planner checkout with `fetch-depth: 0` and treats full history as the mechanism that guarantees the synthetic merge's ancestry is available.

The semantic requirement is narrower than “fetch every ref/history,” but a fixed shallow depth is **not** automatically sufficient. A controlled Git topology reproduction proved both sides:

- a depth-2 clone of a two-parent synthetic merge contained both immediate parents but could **not** resolve their merge-base when the branch point was outside the shallow boundary;
- increasing depth happened to recover the merge-base in the small fixture, but that number depended on branch history and therefore is not a general production law.

So `fetch-depth: 0` is not itself the semantic invariant, but replacing it with a guessed constant such as depth 2 would be unsafe. The repair must establish the exact immutable ancestry actually needed for the diff, using bounded/targeted acquisition and a fail-closed proof that the merge-base is present.

The real invariant is:

1. the exact synthetic merge commit under test is present;
2. it has exactly two immutable parents;
3. parent 1 is the exact tested base and parent 2 is the subject head;
4. the true merge-base needed for the PR feature delta is available and verified;
5. the planner computes the same changed-file set / scope from those immutable objects;
6. failure to establish that ancestry widens or fails closed exactly as current law requires;
7. the emitted plan hash/evidence is unchanged for the same tested tree/base/head/manifest.

## Architecture freeze for the repair

### In scope — first slice only

- planner checkout/history acquisition in `.github/workflows/ci.yml`;
- the stale mechanism-level full-history assertion in `tests/test_ci_plan_workflow.py`;
- a minimal topology fixture proving immediate-parent presence is not enough and proving the chosen bounded/targeted method supplies the true merge-base;
- before/after timing and plan-identity receipts.

### Explicit non-goals

- no edit to `scripts/merge_on_green.py`;
- no merge-on-green runner-route change;
- no change to `run_ci_pack.py` selection semantics;
- no change to pack count or pack weighting;
- no change to code-vs-data gate split;
- no change to contract-delta semantics;
- no `ci-gate` bypass or renamed authority context;
- no pack checkout optimization in the same PR;
- no runner migration;
- no new CI workflow/control plane.

The twelve `ci-pack` full-tree checkouts are a separate follow-on slice. Their filesystem needs must be mechanically censused before any sparse checkout is attempted because execution jobs may read arbitrary repository subjects.

## Required implementation method

1. Start from current main and inspect the exact `ci-plan` checkout + identity steps.
2. Replace the current test's mechanism assertion (`fetch-depth: 0`) with a behavioral ancestry contract: exact synthetic merge, both immutable parents, true merge-base available, and exact feature delta derivable.
3. Include a negative topology where depth 2 has both parents but lacks the merge-base; the test must kill any implementation that mistakes immediate-parent presence for sufficient ancestry.
4. Design the minimum **bounded or targeted ancestry acquisition** that satisfies that contract. Do not hardcode a shallow depth merely because it passes a small fixture.
5. Preserve the existing identity step's parent-count checks and exact SHA binding.
6. Run the planner against representative PR diffs and compare:
   - tested tree SHA;
   - tested base SHA;
   - subject head SHA;
   - changed-files SHA256/count;
   - selected job IDs;
   - matrix;
   - plan SHA.
   All must match the old planner for the same synthetic merge.
7. Exercise deliberately insufficient ancestry and prove it fails safe rather than silently narrowing.
8. Production proof on the PR itself: planner checkout materially improves while `contract-delta`, all selected semantic packs and `ci-gate` remain authoritative and green.

## Acceptance

The first slice is accepted only if:

- the PR changes only the planner checkout/history contract and its owning tests/record;
- plan identity is byte/field-equivalent for representative same-tree comparisons;
- a missing-merge-base / insufficient-ancestry mutation cannot produce a green narrowed plan;
- exact-head PR fences, contract-delta and `ci-gate` are green;
- checkout timing is materially lower than the repeated full-history baseline;
- no merge, runner, pack-execution, or semantic authority behavior changes.

## Stop condition

Stop and revert the optimization if the bounded/targeted method cannot establish the exact synthetic parent pair **and true merge-base**, if changed-file selection differs for the same tested merge, or if any plan/evidence identity field changes for reasons other than the expected workflow commit SHA.

## Continuation

Only after this planner slice is production-proven may `ci-pack` materialization be investigated. That second slice requires a consumer/filesystem census per logical job family; do not infer that the fence sparse surface is sufficient for pack execution.
