---
workstream: "WS:CI-MERGE-CONTROL-PLANE"
session: claude/ci-plan-ancestry-history-20260822
model: codex
ended_because: ci_handoff
mission: >
  Implement and production-prove only the ci-plan ancestry/history slice authorized by
  Sol, then park one draft PR for Sol review without merging it.
state_before: >
  ci-plan checked out the exact GitHub synthetic merge with filter=blob:none and
  fetch-depth:0. The exact tested tree and parent identities were authoritative, but the
  checkout acquired unbounded history before planning. Sol authorized a planner-only
  experiment that preserved every existing plan identity and selection contract.
changed:
  - path: .github/workflows/ci.yml
    what: Give ci-plan a depth-2 initial checkout and an explicit fail-closed ancestry acquisition/proof step before the unchanged planner invocation.
  - path: tests/test_ci_plan_workflow.py
    what: Add hostile shallow-topology, progressive acquisition, full-history fallback, fail-closed fetch, and workflow-order contract tests.
  - path: tests/test_ci_pack.py
    what: Update one stale duplicate planner-history assertion while retaining the ci-pack depth-1/full-working-tree boundary.
  - path: agentos/handoffs/CI-PLAN-ANCESTRY-MATERIALIZATION-2026-08-22.md
    what: Record the exact correctness proof and the adverse production timing for Sol adjudication.
decisions:
  - "DEC:SOL-HOLD-IS-A-MERGE-BARRIER"
verified:
  - claim: New and old planner mechanisms emit byte-identical authoritative plans for the same synthetic merge and fixed identity inputs.
    command: run the old fetch-depth-0 and candidate depth-2-plus-ancestry mechanisms against synthetic tested tree ad3eab2c0a411d1089f49cb227dc6ffcc0b8b178, then compare the complete plan JSON and changed-file payload.
    result: both plan JSON documents are identical; plan_sha256 is 1780ec0e99586b09072edcebd7e46a8043fe16e1377f4f24ab653d6154881af3; all 127 eligible jobs, all 12 packs, weights, semantic digests, identities, and changed-file bytes match.
  - claim: Hostile shallow topology does not mistake immediate parent availability for merge-base availability, and bounded acquisition recovers the exact true branch point.
    command: python3 -m pytest tests/test_ci_plan_workflow.py tests/test_ci_pack.py::test_ci_pack_partial_clone_stays_separate_from_planner_ancestry -q
    result: 29 passed; includes depth-2 insufficiency, progressive deepen, full-history fallback, and total-fetch-failure controls.
  - claim: The surrounding CI semantic, merge-control, and ship-loop contract suites remain green locally.
    command: python3 -m pytest tests/test_ci_pack.py tests/test_ci_pack_semantic.py tests/test_ci_semantic_proof.py tests/test_merge_on_green_semantic.py tests/test_ship_loop_semantic.py -q
    result: 261 passed in 532.43 seconds; only three macOS pytest temporary-directory cleanup warnings.
  - claim: Workflow parsing, workflow self-tests, legacy job inventory, and Agent OS validation pass for the candidate.
    command: python3 scripts/check_workflow_yaml.py && python3 scripts/check_workflow_yaml.py --selftest && python3 scripts/run_ci_pack.py --workflow .github/ci/legacy-jobs.yml --validate-only && python3 scripts/agentos.py validate
    result: 93 workflows parse; 4 controls pass; 200 legacy jobs validate; Agent OS reports 0 errors and 16 pre-existing warnings on the original candidate tree.
  - claim: Production ancestry acquisition itself became materially faster, but total ci-plan latency regressed and therefore fails acceptance.
    command: compare candidate run 32599285180 job 97095030118 logs with full-history baseline runs 32593017581 job 97079951827 and 32598310326 job 97092605916.
    result: candidate shallow fetch was about 1.2 seconds and ancestry proof used deepen-32 in 1 second, versus 10.8-13.1 seconds for baseline full-history fetch; candidate checkout was 297 seconds and total job 316 seconds versus baseline checkouts of 128-129 seconds and jobs of 268/147 seconds because blob-backed working-tree materialization dominated and regressed.
  - claim: The exact-head PR's ci-pack-8/ci-gate red is reproduced independently on simultaneous main run 32599352598.
    command: inspect PR run 32599285180 jobs 97095649222/97097454251 and main run 32599352598 job 97095456409.
    result: both runs fail self-mod-fence on the pre-existing Prophet handoff model enum; PR 6263 is the already-open main-red repair and this PR does not absorb it.
unverified:
  - claim: Any ancestry-only checkout strategy can meet the less-than-60-second planner SLO while retaining a full working tree on the current hosted runner/storage path.
    what_would_verify: a separately authorized mechanism that addresses the observed working-tree materialization bottleneck without changing planner filesystem semantics.
  - claim: The candidate latency regression is stable across a larger sample.
    what_would_verify: Sol-authorized repeated exact-head trials; this wave intentionally preserves the first adverse sample rather than selecting a favorable run.
unresolved:
  - The candidate is correctness-proven but PERFORMANCE ACCEPTANCE FAILED. Sol must decide whether to reject the patch, authorize a different bounded experiment, or explicitly accept a non-latency reason to retain it.
  - The exact final held head must receive concluded binding checks after the independent main-red repair lands; no merge is authorized even if those checks green.
next_actions:
  - Sol reviews PR 6261, its exact-head checks, and the adverse timing receipt.
  - If Sol rejects the candidate, close it without merge; do not quietly revive it in a pack-materialization wave.
  - If Sol commissions another experiment, define a new bounded slice around the measured working-tree materialization bottleneck.
do_not_redo:
  - Do not report the 1.2-second ancestry fetch as a planner latency success; checkout and total job time are the acceptance surfaces and both regressed.
  - Do not rerun merely to replace the adverse sample with a favorable one.
  - Do not add ci-pack sparse materialization, change selection semantics, or touch merge-on-green, runners, contract-delta, pack topology, or ci-gate in this PR.
  - Do not merge, arm merge-on-green, or enable native auto-merge; this is HOLD-FOR-SOL.
danger_areas:
  - A green final CI run will prove correctness/containment only; it cannot convert the measured latency failure into acceptance.
  - The PR synthetic merge can change as main advances. Bind every check receipt to both the subject head and the tested synthetic merge.
  - The branch contains a technically correct fallback mechanism whose production cost was worse than the old path; do not infer commercial or operational value from code correctness alone.
---

# CI planner ancestry/history implementation receipt

## Verdict

The bounded ancestry/history implementation is complete and correctness-equivalent, but
the production latency acceptance **failed**. PR #6261 is therefore a review artifact,
not an accepted optimization. It must remain draft and unmerged until Sol adjudicates it.

## Frozen implementation candidate

- branch: `claude/ci-plan-ancestry-history-20260822`
- implementation commit: `fa73101f9153775cace19f1d17b4df27c85df66b`
- implementation base: `af7f4af9a86c67885e13dd2bcf80b9932e3c399a`
- PR: `#6261`
- scope: ci-plan checkout/ancestry plus owning tests only

The workflow still checks out the exact event SHA with `filter: blob:none`. Its initial
history is depth 2 only to expose the synthetic merge and its two immediate parents. The
existing two-parent identity step remains load-bearing. A new PR-only ancestry step then:

1. tests the exact parent-1/parent-2 merge-base;
2. progressively deepens the exact tested-tree history by 32, 128, 512 and 2048;
3. tests after every acquisition rather than assuming a numeric depth is enough;
4. falls back explicitly to complete history if bounded acquisition is insufficient;
5. fails before the unchanged planner invocation if the true merge-base still cannot be
   proved.

No planner filesystem sparsity was introduced.

## Same-tree equivalence receipt

The old and candidate mechanisms were run against the same fixed synthetic merge:

- tested tree: `ad3eab2c0a411d1089f49cb227dc6ffcc0b8b178`
- tested base: `af7f4af9a86c67885e13dd2bcf80b9932e3c399a`
- subject head: `fa73101f9153775cace19f1d17b4df27c85df66b`
- plan SHA: `1780ec0e99586b09072edcebd7e46a8043fe16e1377f4f24ab653d6154881af3`
- eligible logical jobs: 127, identical and in the same order
- skipped logical jobs: identical and in the same order
- non-empty packs: all 12, identical

The entire plan JSON and changed-file payload matched, including tree/head/base identities,
changed-file digest and count, pack jobs/weights, matrix indices, semantic job/proof IDs,
execution digests and `authority_changed`.

## Production timing receipt

| Mechanism | Run / job | Checkout | Plan step | Total ci-plan job |
|---|---|---:|---:|---:|
| full-history baseline | `32593017581 / 97079951827` | 128s | 123s | 268s |
| full-history baseline | `32598310326 / 97092605916` | 129s | 1s | 147s |
| depth-2 + exact ancestry candidate | `32599285180 / 97095030118` | 297s | 1s | 316s |

Inside the baseline checkout, unbounded history fetch took about 10.8-13.1 seconds. In the
candidate, the shallow exact-SHA fetch took about 1.2 seconds and merge-base acquisition
used deepen-32 in 1 second. The candidate then spent roughly 271 seconds before file update
began. The measured bottleneck is therefore full working-tree/blob materialization, and the
new shallow partial-clone path made that phase materially worse on this runner sample.

This is an adverse/null result: ancestry transport improved, but the user-visible planner
decision did not. The candidate misses the less-than-60-second SLO and is slower than both
named checkout baselines.

## Independent red-main receipt

The first exact-head PR run `32599285180` concluded with `ci-pack-8` and `ci-gate` red.
`ci-pack-8` reported `self-mod-fence`; the simultaneous main run `32599352598` failed the
same job because
`agentos/handoffs/PROPHET-US-V4-RECOVERY-2026-08-22-FLAGSHIP-INTELLIGENCE-FANOUT.md`
used the pre-existing unadmitted `model: sol` enum. PR #6263 is the existing
`main-red repair` for that condition. This planner PR did not edit the Prophet record,
Agent OS schema, self-mod-fence, pack selection, or ci-gate.

## Sol review boundary

This state is intentionally separated:

- implementation: complete;
- local correctness/equivalence proof: complete and green;
- production timing proof: complete and adverse;
- performance acceptance: failed;
- PR: draft, HOLD-FOR-SOL;
- merge/deploy/live: not performed and not authorized.
