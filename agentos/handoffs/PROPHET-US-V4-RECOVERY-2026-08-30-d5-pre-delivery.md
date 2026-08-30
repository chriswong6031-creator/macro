---
workstream: WS:PROPHET-US-V4-RECOVERY
session: codex/d5-earnings-20260829-task4a-records
model: codex
ended_because: complete
mission: >
  Execute D5 Task 4A in the existing governed carrier: run the complete focused
  battery and repository-owned changed-path checks, record the exact pre-delivery
  state, and stop before push, PR, merge, deploy, or live acceptance.
state_before: >
  D5 Tasks 1-3 were committed at exact implementation head
  e650dbc412a3746894c8ef4e950e775139f0dd1a on branch
  claude/d5-earnings-20260829. Task-scoped reviews had accepted the bounded pure
  Earnings projection and the single authenticated existing-router endpoint, but the
  program records still described D5 as todo/unbuilt and no integrated Task 4 evidence
  had been recorded.
changed:
  - path: research/prophet_v4/CAPABILITY_LEDGER.md
    what: >
      Corrects Context Vector's D5 disposition to preserve-and-reference, and adds one
      D5 Earnings row at the exact local pre-delivery state without implying main,
      hosted CI, deployment, or production proof.
  - path: agentos/workstreams/WS-PROPHET-US-V4-RECOVERY.md
    what: >
      Advances only wave d5 from todo to in_progress, records the exact local code head
      and focused evidence, and makes the remaining review/delivery/live sequence the
      next action while keeping D6 and all later waves gated.
  - path: agentos/handoffs/PROPHET-US-V4-RECOVERY-2026-08-30-d5-pre-delivery.md
    what: >
      Adds this cold-stranger pre-delivery checkpoint with exact positive and negative
      evidence plus explicit PR/merge/CI/deploy/live placeholders.
prs: []
verified:
  - claim: >
      Task 4A began in the assigned carrier on the exact accepted Task 3 implementation
      head with no tracked dirt.
    command: >
      pwd; git branch --show-current; git rev-parse HEAD; git status --porcelain=v2
      --branch
    result: >
      worktree .claude/worktrees/d5-earnings-20260829; branch
      claude/d5-earnings-20260829; HEAD
      e650dbc412a3746894c8ef4e950e775139f0dd1a; no tracked changes.
  - claim: >
      The complete D5-focused Task 4 battery passes freshly at the exact implementation
      head.
    command: >
      python3 -m pytest -q -p no:cacheprovider --basetemp
      /tmp/d5-task4-identity tests/test_dataos_identity.py; python3 -m pytest -q -p
      no:cacheprovider --basetemp /tmp/d5-task4-workspace
      tests/test_company_intelligence_workspace_chain.py; python3 -m pytest -q -p
      no:cacheprovider --basetemp /tmp/d5-task4-prophet-lab
      tests/test_prophet_lab.py tests/test_prophet_lab_api.py
    result: >
      104 passed; 37 passed; 297 passed with 10 pre-existing deprecation/OpenAPI
      warnings. Total 438 passed, zero failures.
  - claim: >
      Hostile-review fix round 1 repairs all three P1 findings at one exact local code,
      test, and CI-manifest head without widening D5 authority or product scope.
    command: >
      git show --stat --oneline --decorate --no-renames
      1c5ac27a055df357325d7cab47394912aaf37acc; git diff --check
      2460af68cbac027a7d0e56394e279631a3c592bc..1c5ac27a055df357325d7cab47394912aaf37acc
    result: >
      Exact fix head 1c5ac27a055df357325d7cab47394912aaf37acc changes five paths:
      the Earnings projection, its focused/unit and real-reader tests, the code-gate
      routing test, and the existing prophet-lab manifest job. Mixed-clock corrections
      now preserve A7's any-clock complement while requiring generated_at after the cut;
      distinct visible issuer-source hashes emit OBSERVED; and the hermetic real-reader
      suite has a real executing gate:code owner. Diff check exits 0.
  - claim: >
      The repaired D5 focused battery passes freshly at the exact fix head.
    command: >
      python3 -m pytest -q -p no:cacheprovider --basetemp /tmp/d5-fix1-identity
      tests/test_dataos_identity.py; python3 -m pytest -q -p no:cacheprovider
      --basetemp /tmp/d5-fix1-workspace-full
      tests/test_company_intelligence_workspace_chain.py; python3 -m pytest -q -p
      no:cacheprovider --basetemp /tmp/d5-fix1-prophet-api-full
      tests/test_prophet_lab.py tests/test_prophet_lab_api.py
    result: >
      104 passed; 38 passed; 300 passed with 10 pre-existing deprecation/OpenAPI
      warnings. Total 442 passed, zero failures.
  - claim: >
      The repaired PR code-gate ownership is executable, not a path-only declaration.
    command: >
      python3 -m pytest -q -p no:cacheprovider --basetemp
      /tmp/d5-fix1-green-routing-2
      tests/test_ci_pack.py::test_company_intelligence_workspace_chain_is_executed_by_pr_code_gate;
      CI_CHANGED_FILES_JSON='["tests/test_company_intelligence_workspace_chain.py"]'
      python3 scripts/run_ci_pack.py --workflow .github/ci/legacy-jobs.yml --gate code
      --pack-count 12 --scope-mode active --plan-only --emit-plan-json
      /tmp/d5-fix1-code-plan.json
    result: >
      Routing assertion 1 passed. The path-isolated plan validates all 133 code jobs,
      reports one scoped match and no unowned path, and places prophet-lab in pack 2;
      prophet-lab's run step executes the workspace-chain file. The real branch-range
      planner also exits 0 and selects all 133 code jobs because this fix necessarily
      changes the global CI manifest.
  - claim: >
      The Data OS manifest-owned job line is green with the new identity seam and all
      sibling Data OS contracts.
    command: >
      PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider --basetemp
      /tmp/d5-task4-dataos-job tests/test_dataos_identity.py
      tests/test_dataos_temporal.py tests/test_dataos_price.py tests/test_dataos_nulls.py
      tests/test_dataos_registry.py tests/test_dataos_quality.py -q -rs
    result: "390 passed in 3.89s."
  - claim: >
      The repository changed-path planner validates the code manifest and exposes one
      ownership gap rather than silently widening it.
    command: >
      python3 scripts/run_ci_pack.py --workflow .github/ci/legacy-jobs.yml --gate code
      --pack-count 12 --changed-from eaa2a5bf656d2883fa77382755f833969bed35bd
      --scope-mode active --validate-only
    result: >
      Exit 0; 9 changed files; 76/133 jobs in scope; 57 skipped; all 12 packs
      nonempty. The planner explicitly names
      tests/test_company_intelligence_workspace_chain.py as one unowned path and does
      not select neural-web-core, the manifest job that executes that test.
  - claim: >
      The broader repository job-line failures are outside the D5 delta and are exactly
      attributable to sparse/base state, not hidden as a green integrated pack.
    command: >
      python3 -m pytest -p no:cacheprovider --basetemp /tmp/d5-task4-prophet-job
      tests/test_prophet_lab.py tests/test_prophet_lab_api.py
      tests/test_prophet_lab_timeparse.py tests/test_prophet_lab_commissioning.py
      tests/test_caddy_hub_boundary.py -q; python3 -m pytest -p no:cacheprovider
      --basetemp /tmp/d5-task4-neural-job tests/test_mastermind_context.py
      tests/test_confluence.py tests/test_spine_query.py tests/test_ask_brain.py
      tests/test_company_intelligence_neural_reader.py
      tests/test_company_intelligence_workspace_chain.py
      tests/test_company_intelligence_event_workspace.py
      tests/test_company_intelligence_event_compiler_e3a.py
      tests/test_company_intelligence_qa_reconstruction.py
      tests/test_company_intelligence_qa_exchange.py
      tests/test_company_intelligence_qa_generalization_e3c.py
      tests/test_refresh_event_workspaces.py tests/test_issuer_profiles_a5a.py
      tests/test_world_state.py tests/test_macro_snapshot.py
      tests/test_macro_context_authority.py tests/test_law_dates.py
      tests/test_confluence_strength.py tests/test_neuralweb_health.py
      tests/test_neuralweb_daily_brief.py tests/test_brief_context.py
      tests/test_forward_calendar.py tests/test_orchestrator_log.py
      tests/test_mastermind_feedback.py tests/test_admin_orchestrator.py
      tests/test_admin_prophet.py tests/test_admin_trade_memory.py
      tests/test_macro_thesis.py tests/test_brain_doctrine.py
      tests/test_mastermind_response_log.py tests/test_admin_mastermind_logs.py
      tests/test_brain_analyst_doctrine.py tests/test_brain_analyst_wiring.py
      tests/test_market_packet.py tests/test_brain_market_intel.py
      tests/test_brain_seed_router.py tests/test_brain_analogues.py
      tests/test_brain_curve.py tests/test_response_eval.py
      tests/test_brain_user_memory.py tests/test_user_prefs.py -q; git diff --quiet
      eaa2a5bf656d2883fa77382755f833969bed35bd..e650dbc412a3746894c8ef4e950e775139f0dd1a
      -- tests/test_prophet_lab_timeparse.py tests/test_caddy_hub_boundary.py
      app/deploy/Caddyfile
    result: >
      Prophet Lab manifest line: 406 passed, 4 failed — two committed-data tests could
      not see sparse-omitted data and two unchanged stale-base Caddy expectations
      required 8 blocks while the Caddyfile has 7. The locally available origin/main
      tracking ref already carries the seven-block test correction. Neural Web line:
      1,981 passed, 5 skipped, 2 failed solely on sparse-omitted committed data; its
      guard named four generated data/site writes, which were restored from HEAD and
      sparse rules reapplied before record edits. The three Prophet companion paths
      are byte-identical from the branch base through the D5 implementation head.
  - claim: Agent OS was schema-clean before the records edit.
    command: python3 scripts/agentos.py validate
    result: "936 records; 0 errors; 60 pre-existing warnings."
  - claim: Agent OS remains schema-clean after the three narrow records edits.
    command: python3 scripts/agentos.py validate
    result: "937 records; 0 errors; 60 pre-existing warnings."
unverified:
  - claim: The final D5 branch head is independently hostile-review clean.
    what_would_verify: >
      A fresh reviewer PASS against the exact final base/head, full nine-plus-record
      changed-file census, Cell F contract/amendments, and prohibited-state checklist.
  - claim: The D5 branch is accepted by hosted CI and merged on main.
    what_would_verify: >
      Fill PR number, exact source head, every concluded binding check/run, squash merge
      SHA, and fresh origin/main ancestry plus file-hash receipts here after delivery.
  - claim: The D5 endpoint is deployed and live for paid users.
    what_would_verify: >
      Fill deploy run/commit and authenticated production receipts for one exact covered
      B1 episode and one typed identity-unresolved/not-covered episode, preserving source,
      observed, produced, and browser/consumer clocks separately.
unresolved:
  - >
    This branch started at eaa2a5bf656d and was 182 commits behind the locally available
    origin/main tracking ref at Task 4A start. Fresh-main reconciliation belongs to the
    parent Task 4 delivery step and was expressly forbidden in this records subtask.
  - >
    The broad Prophet Lab and Neural Web manifest lines are not locally clean in this
    sparse checkout for the named omitted-data/base reasons. Do not translate their
    partial counts into full-pack green; rerun after fresh-main reconciliation in the
    proper checkout/hosted lane.
  - >
    The optional local Agent OS pytest sweep returned 180 passed and one failure in
    `test_cross_repo_path_is_unchecked_when_that_checkout_is_absent`: its assertion
    requires zero phantom-artifact warnings, but this sparse carrier omits a Macro
    `verify_shots/` artifact and the host also has an independently stale Mastermind
    sibling checkout. This does not alter the schema-clean `agentos.py validate`
    result; rerun that fixture in the repository's full hosted environment.
next_actions:
  - >
    Run the independent hostile whole-branch re-review against exact repaired head
    1c5ac27a055df357325d7cab47394912aaf37acc and repair any further load-bearing
    finding test-first.
  - >
    Fetch and reconcile fresh origin/main in the parent session, then rerun the 442-test
    focused battery and the repository-selected manifest validation/job lines without
    running the repository-wide full suite in a sparse tree.
  - >
    Push claude/d5-earnings-20260829; open one PR; record the exact PR/source head and
    concluded hosted checks; squash-merge; verify the merge SHA, main ancestry, and exact
    file hashes. PR: PENDING. Hosted CI: PENDING. Merge: PENDING.
  - >
    Wait for the normal deploy lane and capture authenticated paid covered plus typed
    unresolved/not-covered endpoint receipts with separate clocks and a negative-field
    audit. Deploy: PENDING. Authenticated live proof: PENDING.
  - >
    Amend this handoff and the two narrow D5 records with the exact delivery/live packet
    through the required records closeout chain before advancing D5 to PROVEN_LIVE.
do_not_redo:
  - >
    Do not rerun the broad Neural Web or full repository suite in this sparse carrier;
    the measured result already proves omitted committed data makes that exercise
    destructive/noisy. Use the focused suite here and the proper hosted/full checkout
    for the manifest line.
  - >
    Do not widen D5 into Context Vector, another identity reader, a cache, store, queue,
    scheduler, ranker, lifecycle owner, Fusion binding, execution authority, or another
    evidence family/consumer.
  - >
    Do not claim hosted, merged, deployed, or live state from local pytest, task review,
    or manifest validation. All four receipts are explicitly pending.
danger_areas:
  - >
    agentos/workstreams/WS-PROPHET-US-V4-RECOVERY.md is concurrently edited by other
    waves. Re-diff it against fresh main before merge; a stale auto-resolution can delete
    ratified safety boundaries.
  - >
    Data/site are omitted. A broad test wrote four guard-named files inside omitted
    trees before failing; they were restored and `git sparse-checkout reapply` returned
    the carrier to clean sparse state. Never stage an unexpected data/site path.
  - >
    The initial code implementation head is e650dbc412a3746894c8ef4e950e775139f0dd1a;
    hostile-review fix round 1 is exact code/test/manifest head
    1c5ac27a055df357325d7cab47394912aaf37acc. The amended records commit is later
    without changing those fix bytes. Keep initial-code, fix, records, PR, merge, and
    deployed heads distinct.
decisions:
  - DEC:PROPHET-B1-CANONICAL-EPISODE-BINDINGS
  - DEC:PROPHET-D5-PRESERVES-CONTEXT-VECTOR-AND-SEPARATES-EVIDENCE-AUTHORITY
discoveries: []
---

## §0 State — what is true right now

D5's first bounded Earnings vertical is built and locally exact-head verified through
hostile-review fix head `1c5ac27a055df357325d7cab47394912aaf37acc`: one canonical
current issuer-to-CIK seam, one pure revision-chain projection, and one authenticated
existing Prophet Lab detail route. The repaired focused battery is 442 passed, and the
hermetic real-reader chain suite now has a real executing PR `gate: code` owner. It is
not independently re-review accepted, hosted-CI accepted, on main, deployed, or proven
through a real paid production request. The broad local manifest line remains honestly
non-green for the named sparse/base reasons.

## §1 What is LEFT — in order

1. Complete the exact-head hostile whole-branch re-review of fix head `1c5ac27a055d`.
2. Reconcile fresh main and rerun the focused plus repository-owned CI proof in the proper checkout.
3. Push one PR, wait for concluded hosted CI, squash-merge, and verify exact main ancestry/hashes.
4. Wait for normal deployment and prove one covered paid request plus one typed unresolved/not-covered request.
5. Replace every pending receipt in this handoff through the narrow records closeout chain.

## §2 What will bite you

The D5-focused battery is green, but the local carrier is sparse and started from an old
base. The broad Prophet Lab line therefore sees missing committed metadata and the stale
eight-block Caddy expectation; the broad Neural Web line sees missing committed datasets
and can write generated artifacts into omitted trees before the data guard stops it. The
workspace-chain ownership gap is closed at the fix head; do not confuse that code-gate
repair with the remaining sparse/base failures.

## §3 What was decided and found

No new decision or discovery record was minted. `DEC:PROPHET-B1-CANONICAL-EPISODE-BINDINGS`
and `DEC:PROPHET-D5-PRESERVES-CONTEXT-VECTOR-AND-SEPARATES-EVIDENCE-AUTHORITY` remain the
binding identity and authority boundaries.

## §4 Not in scope — do not adopt

This checkpoint does not authorize another evidence family, a cache/index, a second reader
or identity plane, Fusion/rank/entry behavior, downstream D6, or any later V4 wave. It also
does not convert a local exact-head test result into hosted acceptance, merge, deployment,
or live product proof.
