---
workstream: "WS:CI-MERGE-CONTROL-PLANE"
session: sol/ci-plan-working-tree-containment-20260822
model: sol
ended_because: ci_handoff
mission: >
  Make authoritative ci-plan stop materializing the full repository working tree and
  reach a byte/field-identical semantic plan within the <60 second planner SLO, without
  changing selection, partition, evidence, contract-delta, or ci-gate authority.
state_before: >
  PR #6261 proved that bounded/shallow ancestry transport is not the latency lever.
  Exact-head run 32600863041 fetched the synthetic merge in under one second and proved
  ancestry in about one second, but actions/checkout spent roughly 283 seconds producing
  a 76,951-file working tree; total ci-plan was 302 seconds. Sol closed #6261 unmerged as
  REJECTED_BY_DESIGN. Current changed_files() computes git diff tested_base_sha...HEAD,
  where tested_base_sha is direct parent 1 of the exact synthetic merge, so recovering
  the deeper parent1/parent2 branch point is not required by the production selector.
changed:
  - path: agentos/handoffs/CI-PLAN-WORKING-TREE-CONTAINMENT-2026-08-22.md
    what: Freeze the replacement W3 implementation and acceptance packet after #6261's adverse proof.
decisions: []
verified:
  - claim: PR #6261 is closed without merge and its exact-head correctness CI was green.
    command: inspect PR #6261 and runs 32600863041 / 32600862998
    result: closed, merged=false; ci and fences succeeded on bcb4decb0e2faf5d32f5872cb524297bc3f1ebb7.
  - claim: The candidate exact shallow fetch and ancestry proof were cheap while working-tree checkout dominated.
    command: inspect ci-plan job 97098803879 decoded log
    result: depth-2 blob:none fetch completed in <1s; git checkout then materialized 76,951 files and consumed ~283s total checkout; ancestry deepen-32 completed in ~1s; planner step completed in ~2s.
  - claim: Current changed-file selection does not require parent1/parent2 branch-point ancestry.
    command: inspect scripts/run_ci_pack.py::changed_files and the PR semantic identity step
    result: changed_files executes git diff tested_base_sha...HEAD; tested_base_sha is parent 1 of the exact synthetic merge and therefore a direct ancestor of HEAD, so the relevant triple-dot merge-base is parent 1 itself.
  - claim: Full-repository filesystem presence currently participates in scope inference.
    command: inspect scripts/ci_scope_dependencies.py, scripts/run_ci_pack.py and scripts/audit_unrun_tests.py
    result: Path.is_file/Path.exists plus suite enumeration are used while deriving ownership; a naive sparse checkout can therefore mistake omitted tracked paths for nonexistent repository paths and silently change selection.
unverified:
  - claim: A sparse planner plus exact tested-tree path inventory can preserve byte-identical selection while bringing ci-plan under 60 seconds.
    what_would_verify: replay-corpus parity plus at least three exact-head production timing samples on one candidate head.
  - claim: The minimum content materialization profile is known.
    what_would_verify: a mechanical planner read/existence census; do not guess the sparse profile before that census.
unresolved:
  - W3 planner latency remains above its <60 second SLO on production.
  - W4 per-pack sparse materialization remains separately NOT BUILT and must not enter this PR.
next_actions:
  - A bounded Codex/Claude operator starts from fresh current main, reads this handoff, performs the mechanical planner filesystem census, implements only W3 working-tree containment, opens one draft HOLD-FOR-SOL PR, obtains parity and production timing proof, and stops for Sol review without merging.
do_not_redo:
  - Do not reopen, merge, cherry-pick, or repair PR #6261; preserve it as the adverse/null receipt.
  - Do not restore progressive parent1/parent2 deepen/full-history fallback merely to support changed_files(); current selector does not consume that deeper ancestry.
  - Do not treat sparse absence as repository absence.
  - Do not create a second scope index, selection engine, scheduler, lifecycle store, or durable path-truth database.
  - Do not modify ci-pack checkout/materialization in this wave; that is W4 after W3 is proven.
  - Do not touch merge-on-green, runner routing, pack count/weights, code-vs-data split, contract-delta semantics, ci-gate, semantic evidence schemas, or product/data behavior.
danger_areas:
  - Scope inference reads both file contents and file existence. Materializing only control files without virtualizing exact tracked-path existence can silently drop owners and produce false green plans.
  - Large data/site blobs are expensive to materialize but their tracked PATH PRESENCE may still affect static ownership. The solution must separate path existence from blob/content reads.
  - A faster plan with any different changed-file bytes, selected jobs, pack allocation, semantic identities or plan SHA on the same tested tree is a correctness regression.
  - CI-global-invalidating changes such as ci.yml force all logical jobs and are useful for correctness but weak for exercising dynamic scope inference; parity corpus must include narrow non-invalidating PRs too.
---

# W3 — ci-plan working-tree containment

## Observable mission

Reduce authoritative `ci-plan` from multi-minute checkout/materialization to the program SLO of
**<60 seconds**, while producing the **same semantic decision** the current full-tree planner
would produce for the same tested synthetic merge.

The machine capability unlocked is faster authoritative pack selection. This wave is not complete
because checkout is technically sparse; it is complete only when the real GitHub `ci-plan` job
meets the timing gate and the plan remains identical.

## Why this is the next lever

PR #6261 falsified the preceding ancestry-history hypothesis and must not be merged. On exact-head
CI run `32600863041`, job `97098803879`:

- Actions fetched the exact synthetic merge with `filter=blob:none`, depth 2 in <1 second.
- `git checkout --force` then attempted to produce **76,951 files**; the checkout step consumed
  roughly **283 seconds**.
- The candidate parent-pair ancestry acquisition completed in about **1 second**.
- The planner itself completed in roughly **2 seconds** on that invalidating diff.
- Total `ci-plan` was about **302 seconds**.

The cost is therefore the blob-backed working tree, not Git history transfer.

## Architecture correction from #6261

The current selector calls `changed_files(tested_base_sha)`, which executes:

`git diff --name-status -z --find-renames --find-copies tested_base_sha...HEAD`

For PR semantic evidence, `tested_base_sha` is exact parent 1 of the GitHub synthetic merge at
`HEAD`. Parent 1 is a direct ancestor of `HEAD`; therefore the merge-base required by this
triple-dot diff is parent 1 itself. Current production selection does **not** require recovering
the historical common ancestor between parent 1 and parent 2.

Add a regression that permanently kills the stale assumption:

1. build a hostile depth-2 synthetic merge where both immediate parents exist but
   `git merge-base parent1 parent2` is unavailable;
2. prove `git merge-base parent1 synthetic_merge == parent1`;
3. prove `git diff parent1...synthetic_merge` succeeds and yields the expected changed paths.

Do not carry #6261's progressive-deepen/full-history ancestry step into this wave.

## Governing authority / precedence

1. Current `WS:CI-MERGE-CONTROL-PLANE` on fresh `main`.
2. `research/CI_LATENCY_AND_AUTONOMOUS_HEALING_MASTERPLAN.md`, especially W3 and its <60s / identical-selection law.
3. This handoff, which supersedes the **mechanism hypothesis only** in
   `CI-PLAN-ANCESTRY-MATERIALIZATION-2026-08-22.md` after #6261's production falsifier.
4. Existing semantic-proof identity, changed-files bounded transport, and fail-closed scoping laws on main.

If current main has advanced in any of these authority surfaces, reconcile before modifying them.

## Current implementation constraints

`ci-plan` owns selection and partition exactly once. Preserve that ownership.

The current dynamic scope inference uses real filesystem operations:

- `scripts/ci_scope_dependencies.py` resolves imports/path literals with `Path.is_file()` and
  walks known code/artifact roots;
- `scripts/run_ci_pack.py` checks command references with `Path.exists()` while validating
  declared scopes;
- `scripts/audit_unrun_tests.py::discover_suites()` supplies the suite census used to build
  scope ownership.

Therefore a naive `sparse-checkout` that simply omits `data/`, `site/`, fixtures, documents, or
other large trees can change the meaning of `exists` and silently change job selection.

## Required design: separate CONTENT from EXISTENCE

The implementation should preserve current selection semantics while avoiding blob materialization.
A safe candidate architecture is:

1. Checkout the exact event SHA as a blobless partial clone with a deliberately bounded sparse
   working tree containing the planner code/config and the source/test text required for static
   scope inference.
2. Derive an **ephemeral exact tracked-path inventory from the tested Git tree**, not the sparse
   filesystem. Example transport shape:
   `git ls-tree -r --name-only -z HEAD > "$RUNNER_TEMP/ci-tracked-paths/..."`.
   This reads tree metadata without materializing omitted blobs.
3. Pass only the bounded **path to that inventory** into the planner process; never put the
   potentially unbounded path list in a job output or environment value.
4. For planner-only existence questions, teach the existing scope code to consult the exact
   tested-tree inventory instead of equating sparse absence with repository absence.
5. Continue reading actual source contents from materialized files. If scope inference needs the
   content of a file omitted by the sparse profile, fail loudly or conservatively widen; never
   silently treat it as absent.
6. Inventory absent, unreadable, malformed, mismatched, or impossible to bind to tested `HEAD`
   must fail closed / visibly widen according to the existing semantic law. It may never narrow.
7. Do **not** create a new selection authority. `build_plan`, `infer_job_scopes`, the manifest,
   and current semantic evidence remain canonical. The inventory is a derived filesystem oracle
   for the exact tested tree, not a new registry or durable truth store.

A different implementation is allowed only if it meets the same correctness/authority boundaries
and proves them more cleanly.

## Mechanical census before changing the sparse profile

Before implementation, instrument or otherwise mechanically census the full-tree planner and
classify every filesystem dependency into:

- **content read** — the planner must materialize/read bytes;
- **tracked-path existence/stat** — can be answered from the exact tested Git tree inventory;
- **suite enumeration** — must retain exact current discoverability semantics;
- **opaque traversal/dynamic edge** — must preserve existing conservative widening.

Freeze the sparse profile from that evidence. Do not guess it from directory size or intuition.

Prefer materializing the textual/code surfaces scope inference genuinely parses while representing
large non-code asset existence from Git tree metadata. This is an optimization hypothesis to prove,
not permission to narrow the proof universe.

## Exact scope

Expected implementation surfaces, only as needed:

- `.github/workflows/ci.yml` — `ci-plan` checkout/materialization and bounded inventory transport;
- `scripts/run_ci_pack.py` — planner existence-oracle plumbing only; no selection-law rewrite;
- `scripts/ci_scope_dependencies.py` — exact tracked-path existence abstraction if required;
- `scripts/audit_unrun_tests.py` — only if required to preserve suite enumeration on the sparse planner;
- owning tests such as `tests/test_ci_plan_workflow.py`, `tests/test_ci_pack.py`,
  `tests/test_ci_scope_dependencies.py`, `tests/test_audit_unrun_tests.py` when their subject changes;
- this handoff / one narrowly relevant discovery record after measured proof.

## Explicit non-goals

- no `ci-pack` sparse checkout or pack manifests — W4 only after W3 passes;
- no fast-preflight/W2 work in this PR;
- no merge-on-green changes;
- no runner/M1/PC routing changes;
- no pack-count, weighting, matrix, or partition changes;
- no changed-file selection semantic changes;
- no contract-delta semantic changes;
- no `ci-gate` or semantic evidence schema changes;
- no product/data changes;
- no cached scope database, precomputed durable index, second planner, or second source of truth;
- no resurrection of #6261's parent-pair ancestry mechanism.

## Deterministic method and data contracts

This wave is deterministic Git/filesystem analysis; no statistical or model-generated output has
authority.

Identity and correction law:

- `tested_tree_sha` remains exact `github.sha` / synthetic merge;
- `tested_base_sha` remains exact parent 1;
- `subject_head_sha` remains exact parent 2 and must equal the signed event head;
- changed-file artifact bytes/order/digest/count remain unchanged;
- tracked-path inventory, if used, is regenerated from the exact tested tree on every run and is
  ephemeral;
- an omitted sparse path that is tracked at `tested_tree_sha` must still answer **exists=true** for
  ownership logic even though no blob is present in the working tree;
- an untracked/nonexistent path must answer false;
- content reads still require actual bytes or an explicit Git-object read whose semantics are
  proven equivalent;
- inventory doubt is never permission to skip a job.

## Required failure states

Prove fail-closed behavior for at least:

1. checkout HEAD != event SHA;
2. exact synthetic parent identity mismatch;
3. tracked-path inventory missing/unreadable/malformed;
4. inventory built from a different tree SHA;
5. a tracked path deliberately removed from the oracle;
6. a planner content dependency omitted from sparse materialization;
7. rename/copy changed-file pair where both old/new paths must remain represented;
8. opaque traversal/dynamic import that current code widens conservatively;
9. unknown/new top-level paths;
10. current global invalidators;
11. any plan parity mismatch.

## Replay-corpus parity acceptance

Before production timing, compare the current full-tree mechanism with the candidate sparse/oracle
mechanism on a representative fixed corpus including:

- narrow test-only change;
- ordinary product Python change;
- data-only or site/asset change;
- rename and copy diff;
- CI global invalidator;
- a scope-owning path literal under a tree the candidate does not materialize;
- an opaque traversal/dynamic-import owner;
- a no-work/passive narrative case if current semantics support it.

For the same workflow-run identity and tested tree/head/base, require identical:

- complete changed-file artifact bytes, order, SHA and count;
- ordered eligible and skipped job IDs;
- scope summary/reason unless a diagnostic-only wording change is separately justified;
- matrix and non-empty pack indices;
- pack jobs and weights;
- semantic logical-job/proof identities and execution digests;
- `authority_changed`;
- complete authoritative plan JSON and `plan_sha256`.

A faster but different plan is a failed experiment.

## Discriminating mutations

Tests must kill these exact regressions:

- sparse omitted-but-tracked asset becomes `exists=false` and removes an owner;
- deleting one path from the tracked inventory silently narrows selection;
- corrupt inventory silently falls back to empty/no paths;
- required Python/text content omitted from sparse checkout silently reduces closure;
- virtual existence oracle is consulted outside planner/scoping and becomes a second product/runtime filesystem law;
- #6261-style requirement for `merge-base(parent1,parent2)` is reintroduced into current changed-file selection.

## Production acceptance

Exact-head GitHub proof is mandatory.

Use at least **three timing observations on the same candidate head** where practical (reruns, not
micro-pushes selected for favorable noise). Record separately:

- runner pickup;
- checkout/materialization step duration;
- planner computation duration;
- total `ci-plan` duration.

Binding target remains the masterplan: **`ci-plan` <60 seconds p95**. For a three-run acceptance
packet, all three should finish below 60 seconds rather than claiming a p95 from an inadequate
sample. If GitHub-hosted variance prevents that, return the complete adverse measurements to Sol;
do not weaken the SLO inside the worker session.

Also require on the exact candidate head:

- `ci-plan` success;
- every selected semantic pack success;
- `contract-delta` success;
- `ci-gate` success with clear semantic evidence;
- fences and binding authority checks success;
- no new same-SHA green→red nondeterminism;
- diff remains within this W3 boundary.

## Stop condition

STOP FOR SOL REVIEW and do not merge if any of these is true:

- same-tree plan identity/selection differs;
- sparse omission can silently narrow ownership;
- a new durable scope/path truth store is introduced;
- `ci-plan` still misses the <60 second gate;
- implementation requires absorbing W4 pack materialization;
- a newer accepted authority change overlaps the modified control-plane surface.

If the experiment is adverse, preserve it honestly as #6261 did; do not rerun until a favorable
sample appears.

## Continuation

Only after Sol accepts and production-proves W3 may W4 begin: planner-produced per-pack
materialization manifests targeting <60 second pack checkout. Do not mix the two.

The operator return must include exact head SHA, base/synthetic merge identity, changed files,
replay-parity receipt, mutation controls, all relevant workflow/run/job IDs, raw checkout and
`ci-plan` timing samples, CI/fence/authority state, discovered collisions, and a HOLD-FOR-SOL stop.
