---
workstream: "WS:CI-MERGE-CONTROL-PLANE"
session: github-ci-merge-recovery-d4a921
model: fable
ended_because: ci_handoff
mission: >
  Incident commander for the recurring CI/merge traffic jam: measure the loop
  live, break it structurally (not another local patch), re-evaluate native
  merge queue with fresh evidence, land the repair, prove it on live runs.
state_before: >
  32 armed PRs (median age 23h), 7/8 sampled heads red with inherited-shaped
  pack failures; PR CI p50 64.5 min (p95 78.4); pack queue delays to 37m43s on
  a saturated Enterprise hosted pool; merge-on-green fired 394 times in 8h
  (64% cancelled); main baselines escalated 31->73 min with 3/10 failing; one
  markdown file selected 118/188 jobs and 12/12 packs; merges happened only in
  post-baseline batch windows (7 PRs inside 42 seconds at 05:44Z).
changed:
  - path: .github/workflows/ci.yml
    what: >
      ci-plan: depth-1 checkout + PR-files-API diff + exact-key scope cache +
      plan-document output/artifact + fast preflight steps gating packs.
      ci-pack: materializes and executes the published plan (--plan-json,
      digest-verified), pip download cache. ci-gate: one CI_CLASS= line +
      summary table per run.
  - path: scripts/run_ci_pack.py
    what: >
      Two-tier scopes (paths vs fallback_paths; **/*.md never matches the
      fallback tier unless the job demonstrably reads md); `scope: exclusive`
      manifest tier (declared paths replace inference, coverage-audited
      fatally); dynamic pack count (weight/600, only when scoping narrowed;
      full suite keeps 12 for the sweeper's ci-pack-0..11 main-proof anchor);
      scope-map cache; _plan_digest_from_document + _execute_from_plan; failed
      legacy jobs into GITHUB_STEP_SUMMARY.
  - path: scripts/ci_plan_changed_files.py
    what: new; PR files API -> one-line JSON array or `null` (widen on doubt).
  - path: scripts/merge_on_green.py
    what: mark_only_pass verifies its label write read-after-write; a
      verifiably absent marker annotates at error level.
  - path: .github/workflows/merge-on-green.yml
    what: skipped-conclusion workflow_run wakes no longer schedule sweeps.
  - path: .github/ci/legacy-jobs.yml
    what: promoted the three structural guards to preflight (selftests stay);
      free-content-estate declares content/** ownership (union tier).
  - path: tests/test_ci_plan_workflow.py, tests/test_ci_pack.py, tests/test_ci_plan_changed_files.py
    what: contract updates + 8 incident regression fixtures + new suite.
  - path: research/CI_MERGE_CONTROL_PLANE_RECOVERY_2026_08_14.md, docs/CI_MERGE_ARCHITECTURE.md, agentos/decisions/DEC-CI-NATIVE-MERGE-QUEUE-REJECTED.md
    what: incident model with run IDs; one-page architecture; merge-queue verdict.
verified:
  - claim: markdown handoff shape collapsed 118 jobs/12 packs -> 3 jobs/1 pack
    command: CI_CHANGED_FILES_JSON='["research/DESIGN_NOTES.md"]' python3 scripts/run_ci_pack.py --workflow .github/ci/legacy-jobs.yml --pack-count 12 --plan-only --changed-from HEAD
    result: "Planned 3 of 188 legacy jobs into 1 packs"
  - claim: scope inference cache turns 122s cold planning into ~1s warm
    command: scratchpad plan_shapes2.sh (wall_seconds lines)
    result: 122s cold, 0-1s warm across five shapes
  - claim: an unwired new pytest suite reds in ~10s at preflight
    command: git add tests/test_zz_preflight_probe_unwired.py && python3 scripts/audit_unrun_tests.py
    result: exit 1 with an unrun-suite error annotation naming the probe file
  - claim: packs execute exactly the published plan slice via the real CLI
    command: synthetic-manifest round trip (GITHUB_ACTIONS=true GITHUB_WORKSPACE=... run_ci_pack.py --execute --plan-json --expect-plan-sha)
    result: exit 0, pack 0 ran exactly plan.pack_jobs[0]; wrong sha exit 2; drifted manifest exit 2
  - claim: control-plane suites green on the merged (rebased) tree
    command: python3 -m pytest tests/test_ci_plan_workflow.py tests/test_ci_pack.py tests/test_merge_on_green.py tests/test_ci_handoff.py tests/test_ci_plan_changed_files.py -q
    result: all green (31 + 494 + 339 + handoff subset), 2026-08-14 ~06:45Z
  - claim: native merge queue available but structurally incompatible with the producer main
    command: ruleset 20833101 + probe PR #5581 + direct push (receipts in recovery doc §3)
    result: queue merged probe 31s after green; one base push rebuilt the merge group; bypass_actors 422 for github-actions
unverified:
  - claim: live PR-lane behavior of the new pipeline (cold planner service time, preflight wall, pack consumption at fleet load)
    what_would_verify: PR #5585's own run 31777710942 job timings (monitor armed this session)
  - claim: narrow-PR fanout, structural-red-in-minutes, and green-to-merge latency on live GitHub
    what_would_verify: the two post-merge probe PRs described in WS next_action
unresolved:
  - Heavy code-file fanout (engine module still selects ~121 jobs) until the
    chipped exclusive-scope curation and engine-render-guards split land.
  - The twice-529'd full-diff opus review; a focused reviewer run was armed at
    session end — read its verdict before large follow-on edits.
next_actions:
  - Read run 31777710942's conclusion; if ci-gate green, arm PR #5585 with merge-on-green.
  - After merge: probe A (one research-md-file PR) — expect ci-plan ~1-2 min, 3 jobs/1 pack, auto-merge; record green-to-merge latency.
  - Probe B (PR adding an unwired test file) — expect ci-plan red in ~2-3 min with CI_CLASS=structural-preflight and zero packs; close it.
  - Fill recovery doc §5 with before/after numbers; delete mq-eval-base branch + ruleset 20833101; close the incident PARTIAL/PASS per §0.
do_not_redo:
  - Do not re-evaluate native merge queue availability (DEC:CI-NATIVE-MERGE-QUEUE-REJECTED has fresh receipts and the reopen precondition).
  - Do not "fix" markdown fanout by promoting .md-suffixed fallback patterns to the owned tier — measured 2026-08-14: it re-selects 55/188 (doc-census breadth); declare per-job paths instead (free-content-estate is the template).
  - Do not give ci-plan fetch-depth:0 back; the diff is the files API with widen-on-doubt.
  - Do not make dynamic pack count apply to full-suite runs; merge_on_green REQUIRED_CI_ANCHORS needs ci-pack-0..11 on main baselines.
danger_areas:
  - plan_hash_payload / to_dict / _plan_digest_from_document must stay field-identical; a drift reds every pack fleet-wide (loudly, by design).
  - The scope cache is exact-key only; adding restore-keys would silently mis-scope.
  - legacy-jobs.yml is fleet-hot: re-fetch origin/main and re-resolve before any push (this session's rebase hit exactly one union conflict there).
---

Cold-stranger note: read docs/CI_MERGE_ARCHITECTURE.md first (one page), then
research/CI_MERGE_CONTROL_PLANE_RECOVERY_2026_08_14.md for the measured why.
