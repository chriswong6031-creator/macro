---
workstream: WS:PROPHET-US-V4-RECOVERY
session: codex/d5-earnings-20260829-post-reconcile
model: codex
ended_because: complete
mission: >
  Execute D5 post-reconciliation verification in the existing governed carrier: prove
  the exact merge-parent relationship, run the full commissioned local battery, refresh
  only the three D5 records, and stop before push, PR, deploy, merge, or live acceptance.
state_before: >
  Independent whole-branch hostile re-review 4 had passed final reviewed head
  f48c8d1598c49aa0f3b1eba85922c9e633dd114d. Fresh-main head
  b7b3938aec35372dc32229981b4f3159f2b5faf2 had been reconciled into exact merge head
  bb34c575f58879f4944ca353e17ca6a6fa4512ca, but the complete post-reconciliation
  local battery and the corresponding records refresh were still owed.
changed:
  - path: .github/ci/legacy-jobs.yml
    what: >
      Fix round 4 widens only the five D5-affected curated exclusive jobs to their
      exact measured B1/Stock Identity import closure; it adds no wildcard and does
      not weaken or bypass exclusivity.
  - path: tests/test_ci_pack.py
    what: >
      Adds the strict RED -> GREEN five-job selector regression and preserves the
      repository's complete re-derived curated-closure guard.
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
      Hostile-review fix round 2 repairs the sole P1 left by the first whole-branch
      re-review at one exact local code/test head without disturbing the two accepted
      former-P1 repairs or widening D5 authority or product scope.
    command: >
      git show --stat --oneline --decorate --no-renames
      13e36371e2cd49ae790803f3d49c951062aad8a0; git diff --check
      056e529fea8be53b642d8cb2ee11a3c41f720505..13e36371e2cd49ae790803f3d49c951062aad8a0
    result: >
      Re-review head 056e529fea8be53b642d8cb2ee11a3c41f720505 accepted the A7
      any-clock/generated-receipt repair and executing gate:code ownership, but found
      that the valid source transition None -> issuer-release SHA still emitted
      NOT_OBSERVABLE and self-rejected. Exact round-2 code/test head
      13e36371e2cd49ae790803f3d49c951062aad8a0 changes only the Earnings projection
      and real-reader test: a distinct visible transition now takes OBSERVED precedence,
      while homogeneous same-hash and body-only chains retain NONE_IN_CHAIN and
      NOT_OBSERVABLE. Diff check exits 0.
  - claim: >
      The repaired D5 focused battery passes freshly at the exact fix head.
    command: >
      PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider
      --basetemp /tmp/d5-fix2-final-focused tests/test_dataos_identity.py
      tests/test_company_intelligence_workspace_chain.py tests/test_prophet_lab.py
      tests/test_prophet_lab_api.py
    result: >
      104 passed; 39 passed; 300 passed with 10 pre-existing deprecation/OpenAPI
      warnings. Total 443 passed, zero failures. The new constructed real-writer/
      real-reader mixed transition preserves immutable decision evidence, emits
      OBSERVED, binds the later generation receipt to corrected_at, passes the closed
      validator, and returns endpoint status 200 rather than 503.
  - claim: >
      Fix round 2 established a real path owner and executing run step, but did not yet
      prove the owning job's clean dependency closure.
    command: >
      python3 -m pytest -q -p no:cacheprovider --basetemp
      /tmp/d5-fix2-routing
      tests/test_ci_pack.py::test_company_intelligence_workspace_chain_is_executed_by_pr_code_gate;
      CI_CHANGED_FILES_JSON='["tests/test_company_intelligence_workspace_chain.py"]'
      python3 scripts/run_ci_pack.py --workflow .github/ci/legacy-jobs.yml --gate code
      --pack-count 12 --scope-mode active --plan-only --emit-plan-json
      /tmp/d5-fix2-code-plan.json
    result: >
      Routing assertion 1 passed. The path-isolated plan validates all 133 code jobs,
      reports one scoped match and no unowned path, and places prophet-lab in pack 2;
      prophet-lab's run step executes the workspace-chain file. The real branch-range
      planner also exits 0 and selects all 133 code jobs because this fix necessarily
      changes the global CI manifest. Whole-branch re-review 2 later proved this was
      routing/step evidence only: the clean job still lacked requests and pyarrow.
  - claim: >
      Hostile-review fix round 3 closes the readdressed mixed-lineage validator gap and
      the clean Python 3.12 D5 dependency gap at one exact local code/test/manifest head.
    command: >
      git show --stat --oneline 917b7eaef81b2a286551ede3ede0209c00f233e3;
      PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider
      --basetemp /tmp/d5-fix3-hostile <18 exact hostile selectors>;
      PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider
      --basetemp /tmp/d5-fix3-focused tests/test_dataos_identity.py
      tests/test_company_intelligence_workspace_chain.py tests/test_prophet_lab.py
      tests/test_prophet_lab_api.py
    result: >
      Exact head 917b7eaef81b2a286551ede3ede0209c00f233e3 changes only the D5
      validator, its hostile test, the prophet-lab dependency declaration, and the
      coupled manifest test. Strict RED proved the hostile relabel was accepted and both
      packages absent; GREEN is 18 hostile passed and 444 focused passed (104 identity +
      39 real-reader chain + 301 Prophet Lab/API), with same-hash NONE_IN_CHAIN,
      homogeneous body-only NOT_OBSERVABLE, real mixed-chain endpoint 200, and immutable
      decision evidence retained.
  - claim: >
      The D5-owned Python 3.12 job closure executes from only the dependencies declared
      by prophet-lab; no import/collection failure remains.
    command: >
      python3.12 -m venv /tmp/d5-fix3-py312.snQEKH; /tmp/d5-fix3-py312.snQEKH/bin/pip
      install pytest pandas pyarrow fastapi httpx pyyaml requests;
      /tmp/d5-fix3-py312.snQEKH/bin/python -m pytest tests/test_prophet_lab.py
      tests/test_prophet_lab_api.py tests/test_company_intelligence_workspace_chain.py
      tests/test_prophet_lab_timeparse.py tests/test_prophet_lab_commissioning.py -q
    result: >
      435 passed with 10 pre-existing FastAPI/OpenAPI warnings. The exact six-suite
      manifest line also collected and ran every test: 451 passed and only the two
      unchanged stale-branch Caddy 8-versus-7 proxy pins failed; there were zero missing
      dependency, import, collection, sparse-data, or D5 failures.
  - claim: >
      The repaired workspace-chain path is owned by prophet-lab and the current branch
      range remains valid under the code-gate planner.
    command: >
      CI_CHANGED_FILES_JSON='["tests/test_company_intelligence_workspace_chain.py"]'
      python3 scripts/run_ci_pack.py --workflow .github/ci/legacy-jobs.yml --gate code
      --pack-count 12 --scope-mode active --plan-only --emit-plan-json
      /tmp/d5-fix3-code-plan.json; CI_BASE_SHA=eaa2a5bf656d2883fa77382755f833969bed35bd
      CI_HEAD_SHA=917b7eaef81b2a286551ede3ede0209c00f233e3 python3
      scripts/run_ci_pack.py --workflow .github/ci/legacy-jobs.yml --gate code
      --pack-count 12 --scope-mode active --plan-only
    result: >
      The path-isolated plan reports semantic SHA-256
      0247d1eafa8a892529490fdaece3a32d7cce77c21d27e0e05b83fb86e4bb3bd7,
      selects 114 of 133 jobs (113 always-on plus prophet-lab), and reports no unowned
      path. The whole branch range validates all 133 jobs because the CI manifest is a
      global invalidator. Both commands exit 0.
  - claim: >
      Whole-branch re-review 3 correctly reattributed the final CI-pack P1 to D5, and
      fix round 4 closes it without weakening the curated exclusive-scope law.
    command: >
      git show --stat --oneline 1dfc8aab4cf2a6dd5aff1d90af39f110fc6e0b25;
      PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider
      --basetemp /tmp/d5-fix4-full-cipack tests/test_ci_pack.py;
      PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider
      --basetemp /tmp/d5-fix4-hostile <20 exact hostile selectors>;
      PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider
      --basetemp /tmp/d5-fix4-focused tests/test_dataos_identity.py
      tests/test_company_intelligence_workspace_chain.py tests/test_prophet_lab.py
      tests/test_prophet_lab_api.py
    result: >
      Review head 6c7dc87dbd23 showed the earlier `115 passed / 1 failed` result was
      D5-induced: five curated jobs could silently skip true dependencies reached by
      D5's Prophet Lab imports. Exact code/test/manifest head
      1dfc8aab4cf2a6dd5aff1d90af39f110fc6e0b25 adds six concrete paths to four jobs and
      four concrete Stock Identity paths to defense-rail-laws. The new selector pin was
      observed failing before the manifest repair and then passing; the re-derived
      isolated guard passed, complete tests/test_ci_pack.py is 117 passed, hostile
      lineage is 20 passed, and the focused D5 battery remains 444 passed.
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
      The historical Prophet Lab and Neural Web job-line failures in this receipt are
      outside the D5 delta and are exactly attributable to sparse/base state, not hidden
      as a green integrated pack; this claim does not include the D5-induced CI-pack
      closure defect repaired in fix round 4.
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
  - claim: Agent OS was schema-clean before the historical Task 4A records edit.
    command: python3 scripts/agentos.py validate
    result: "936 records; 0 errors; 60 pre-existing warnings."
  - claim: Agent OS remained schema-clean after the historical Task 4A records edit.
    command: python3 scripts/agentos.py validate
    result: "937 records; 0 errors; 32 pre-existing warnings in the full checkout."
  - claim: >
      The post-reconciliation carrier starts at the exact commissioned merge head, whose
      two parents preserve the final independently reviewed D5 head and fresh main.
    command: >
      git show -s --format='%H%n%P%n%s' HEAD; git merge-base
      eaa2a5bf656d2883fa77382755f833969bed35bd HEAD; git diff --name-status
      b7b3938aec35372dc32229981b4f3159f2b5faf2..HEAD; git diff --quiet
      b7b3938aec35372dc32229981b4f3159f2b5faf2..HEAD -- app/deploy/Caddyfile
      tests/test_caddy_hub_boundary.py
    result: >
      HEAD is bb34c575f58879f4944ca353e17ca6a6fa4512ca with exact parents
      f48c8d1598c49aa0f3b1eba85922c9e633dd114d and
      b7b3938aec35372dc32229981b4f3159f2b5faf2; the original branch base remains ancestor
      eaa2a5bf656d2883fa77382755f833969bed35bd. The fresh-main range is exactly the 14
      commissioned D5 files. Caddyfile and its boundary test are byte-identical to fresh
      main, so the historical stale-base failures are absent.
  - claim: >
      The full commissioned D5, hostile, complete CI-pack, exact route/closure, exact
      Prophet Lab manifest, and clean declared-dependency Python 3.12 batteries are green
      at exact merge head bb34c575f58879f4944ca353e17ca6a6fa4512ca.
    command: >
      PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider --basetemp
      /private/tmp/d5-post-reconcile.q9Y7hF/focused tests/test_dataos_identity.py
      tests/test_company_intelligence_workspace_chain.py tests/test_prophet_lab.py
      tests/test_prophet_lab_api.py; PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p
      no:cacheprovider --basetemp /private/tmp/d5-post-reconcile.q9Y7hF/hostile
      tests/test_company_intelligence_workspace_chain.py tests/test_prophet_lab_api.py -k
      '<22 exact lineage/PIT selectors>'; PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q
      -p no:cacheprovider --basetemp /private/tmp/d5-post-reconcile.q9Y7hF/full-cipack
      tests/test_ci_pack.py; PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p
      no:cacheprovider --basetemp /private/tmp/d5-post-reconcile.q9Y7hF/routing
      tests/test_ci_pack.py::test_company_intelligence_workspace_chain_is_executed_by_pr_code_gate
      tests/test_ci_pack.py::test_d5_route_closure_keeps_affected_curated_jobs_selecting_dependencies
      tests/test_ci_pack.py::test_curated_exclusive_scopes_cover_their_own_import_closure;
      PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider --basetemp
      /private/tmp/d5-post-reconcile.q9Y7hF/prophet-manifest tests/test_prophet_lab.py
      tests/test_prophet_lab_api.py tests/test_company_intelligence_workspace_chain.py
      tests/test_prophet_lab_timeparse.py tests/test_prophet_lab_commissioning.py
      tests/test_caddy_hub_boundary.py; /private/tmp/d5-rereview4-py312.xbItvx/bin/pip
      check; /private/tmp/d5-rereview4-py312.xbItvx/bin/python -m pytest -q -p
      no:cacheprovider --basetemp /private/tmp/d5-post-reconcile.q9Y7hF/py312
      tests/test_prophet_lab.py tests/test_prophet_lab_api.py
      tests/test_company_intelligence_workspace_chain.py tests/test_prophet_lab_timeparse.py
      tests/test_prophet_lab_commissioning.py
    result: >
      Focused 444 passed; exact hostile lineage/PIT 22 passed with 270 deselected;
      complete tests/test_ci_pack.py 117 passed; route/closure selectors 3 passed; exact
      six-suite Prophet Lab manifest line 453 passed; clean Python 3.12.13 environment has
      no broken requirements and the exact five-suite line is 435 passed. Only 10 known
      FastAPI/deprecation warnings appear on the relevant suites; there are zero failures.
  - claim: >
      Both path-isolated and whole-range semantic routing plans are fully receipted against
      the exact merge and fresh-main heads without an unowned-path or empty selected-job
      result.
    command: >
      CI_EVENT_NAME=pull_request CI_WORKFLOW_NAME=ci CI_HEAD_ROLE=pr_head
      CI_HEAD_SHA=bb34c575f58879f4944ca353e17ca6a6fa4512ca
      CI_BASE_SHA=b7b3938aec35372dc32229981b4f3159f2b5faf2
      CI_CHANGED_FILES_JSON='["tests/test_company_intelligence_workspace_chain.py"]'
      python3 scripts/run_ci_pack.py --workflow .github/ci/legacy-jobs.yml --gate code
      --pack-count 12 --scope-mode active --plan-only --emit-plan-json
      /private/tmp/d5-post-reconcile.q9Y7hF/path-plan.json; CI_EVENT_NAME=pull_request
      CI_WORKFLOW_NAME=ci CI_HEAD_ROLE=pr_head
      CI_HEAD_SHA=bb34c575f58879f4944ca353e17ca6a6fa4512ca
      CI_BASE_SHA=b7b3938aec35372dc32229981b4f3159f2b5faf2 python3
      scripts/run_ci_pack.py --workflow .github/ci/legacy-jobs.yml --gate code
      --pack-count 12 --scope-mode active --changed-from
      b7b3938aec35372dc32229981b4f3159f2b5faf2 --plan-only --emit-plan-json
      /private/tmp/d5-post-reconcile.q9Y7hF/whole-plan.json
    result: >
      Path-isolated selection is 3/133, including prophet-lab, with changed-files hash
      cad089b975a11d15962bb40ca630b7eb830dc5e92f2091b9592605a442856ced and plan hash
      179a8fde50a3647cba6779dbdf781379dcbc9a6ea8b1c19214f312d4198bf896. The complete
      14-file range sets authority_changed=true and selects 133/133 across all 12 packs,
      with changed-files hash 7aec8c18111b3714544d9091a845b8d1281b03edce725e64732665c636afa636
      and plan hash 8740f42f6b48b70142dc044eebf6c8ea16771a893c98aa34cb6d5890a5e86bd9.
  - claim: Agent OS is schema-clean after the post-reconciliation records refresh.
    command: python3 scripts/agentos.py validate
    result: "967 records; 0 errors; 40 pre-existing warnings in the full checkout."
unverified:
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
    Local reconciliation and exact-head verification are complete. Only external
    delivery states remain unresolved: the exact records head has not been pushed or
    opened as a PR, hosted CI has not concluded, no squash merge exists on main, the
    normal deploy has not incorporated D5, and no authenticated covered plus
    typed-unresolved production receipt has been captured.
next_actions:
  - >
    Push the exact records-only child of merge head
    bb34c575f58879f4944ca353e17ca6a6fa4512ca; open one PR; record the exact PR/source
    head and concluded hosted checks; squash-merge; verify the merge SHA, main ancestry,
    and exact file hashes. PR: PENDING. Hosted CI: PENDING. Merge: PENDING.
  - >
    Wait for the normal deploy lane and capture authenticated paid covered plus typed
    unresolved/not-covered endpoint receipts with separate clocks and a negative-field
    audit. Deploy: PENDING. Authenticated live proof: PENDING.
  - >
    Amend this handoff and the two narrow D5 records with the exact delivery/live packet
    through the required records closeout chain before advancing D5 to PROVEN_LIVE.
do_not_redo:
  - >
    Do not rerun the broad Neural Web or full repository suite merely to repeat the
    historical sparse result; that run already proved omitted committed data makes the
    exercise destructive/noisy. This carrier is now full, and the exact local Prophet
    Lab manifest line is green at 453 passed. The next integration verdict is hosted CI.
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
    waves. Re-diff it against the PR base before delivery; a stale auto-resolution can delete
    ratified safety boundaries.
  - >
    The carrier was initially sparse. A broad test wrote four guard-named files inside
    omitted trees before failing; those files were restored before records work. The
    carrier was later expanded to a full tracked checkout for the clean Python 3.12 job
    proof. Never stage an unexpected data/site path, and treat checkout mode as local
    workspace state rather than delivery evidence.
  - >
    The initial code implementation head is e650dbc412a3746894c8ef4e950e775139f0dd1a;
    hostile-review fix round 1 is exact code/test/manifest head
    1c5ac27a055df357325d7cab47394912aaf37acc; its records head is
    056e529fea8be53b642d8cb2ee11a3c41f720505; and the sole mixed-transition fix
    round 2 is exact code/test head 13e36371e2cd49ae790803f3d49c951062aad8a0.
    Fix round 3 is exact code/test/manifest head
    917b7eaef81b2a286551ede3ede0209c00f233e3; fix round 4 is exact
    code/test/manifest head 1dfc8aab4cf2a6dd5aff1d90af39f110fc6e0b25; final independently reviewed head is
    f48c8d1598c49aa0f3b1eba85922c9e633dd114d; fresh-main parent is
    b7b3938aec35372dc32229981b4f3159f2b5faf2; and the reconciliation merge head is
    bb34c575f58879f4944ca353e17ca6a6fa4512ca. Keep initial-code, all fix rounds,
    reviewed, fresh-main, reconciliation, records, PR, squash-merge, and deployed heads
    distinct.
decisions:
  - DEC:PROPHET-B1-CANONICAL-EPISODE-BINDINGS
  - DEC:PROPHET-D5-PRESERVES-CONTEXT-VECTOR-AND-SEPARATES-EVIDENCE-AUTHORITY
discoveries: []
---

## §0 State — what is true right now

D5's first bounded Earnings vertical is built, independently hostile-review accepted, and
locally exact-head verified after fresh-main reconciliation: final reviewed head
`f48c8d1598c49aa0f3b1eba85922c9e633dd114d` and fresh-main head
`b7b3938aec35372dc32229981b4f3159f2b5faf2` are the exact parents of merge head
`bb34c575f58879f4944ca353e17ca6a6fa4512ca`. At that merge head, the focused battery is
444 passed, the exact hostile lineage/PIT selector set is 22 passed, complete CI-pack is
117 passed, route/closure is 3 passed, the exact Prophet Lab six-suite manifest line is
453 passed, the clean Python 3.12 five-suite is 435 passed, and both semantic routing
plans are receipted. The prior stale Caddy mismatch is gone because the reconciled files
are byte-identical to fresh main. D5 is not hosted-CI accepted, on main, deployed, or
proven through a real paid production request.

## §1 What is LEFT — in order

1. Push the exact records-only child of merge head `bb34c575f588` and open one PR.
2. Wait for concluded hosted CI, squash-merge, and verify exact main ancestry/hashes.
3. Wait for normal deployment and prove one covered paid request plus one typed unresolved/not-covered request.
4. Replace every pending receipt in this handoff through the narrow records closeout chain.

## §2 What will bite you

The local proof is now green and reconciled, but it is still only local proof. Hosted CI,
the PR and squash merge, fresh-main ancestry after that merge, the normal deployment, and
authenticated production receipts remain separate states. Do not infer any of them from
the exact merge-head battery. The historical broad Neural Web sparse run remains historical
and is not a current D5 verdict.

## §3 What was decided and found

No new decision or discovery record was minted. `DEC:PROPHET-B1-CANONICAL-EPISODE-BINDINGS`
and `DEC:PROPHET-D5-PRESERVES-CONTEXT-VECTOR-AND-SEPARATES-EVIDENCE-AUTHORITY` remain the
binding identity and authority boundaries.

## §4 Not in scope — do not adopt

This checkpoint does not authorize another evidence family, a cache/index, a second reader
or identity plane, Fusion/rank/entry behavior, downstream D6, or any later V4 wave. It also
does not convert a local exact-head test result into hosted acceptance, merge, deployment,
or live product proof.
