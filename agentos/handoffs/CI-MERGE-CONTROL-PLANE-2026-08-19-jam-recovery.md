---
workstream: WS:CI-MERGE-CONTROL-PLANE
session: new-session-97d810
model: fable
ended_because: complete
prs: [6002, 6005]
mission: >
  Operator escalation 2026-08-19 ~17:00Z: "PRs stuck unmerged like a traffic
  jam — figure out the root cause and fix it permanently." Diagnose why the
  armed backlog stopped merging after the W1/W2 gate split landed, heal main,
  and close the recurrence class.
state_before: >
  Sweep log 17:00Z: 21 armed PRs baseline-blocked behind a red circuit
  breaker. Binding red = ONE test on main's integration-baseline push lane
  (tests/test_ci_pack.py::test_curated_exclusive_scopes_cover_their_own_import_closure),
  red since ~12:00Z (first red push a22e65630f83, run 32276602747): merges
  5872 (engine/oracle/oopt.py now imports engine/options_universe.py) and
  5932 (scripts/build_security_master.py now reads
  config/issuer_group_allowlist.yml) grew curated-exclusive closures without
  widening paths. Jam CLASS: that contract test runs only post-merge —
  path-scoped PR packs never reach it, so culprits merge green, main reds,
  the breaker latches, the fleet queues. Sibling repair PR 5985 (unrun-suite
  wiring) was mid-flight with a checkout infra flake on its last pack.
changed:
  - path: .github/ci/legacy-jobs.yml
    what: >
      PR 6002: biocatalyst-serving paths += engine/options_universe.py;
      dataos-foundation paths += config/issuer_group_allowlist.yml (the
      test's own prescribed widening; comments name the import edges and
      origin merges). PR 6005: workflow-yaml job gains a run: step for
      tests/test_contract_delta.py.
  - path: .github/workflows/ci.yml
    what: >
      PR 6005: new always-on contract-delta job (pull_request events only,
      ubuntu-latest, integration-baseline checkout recipe) feeding ci-gate
      needs with skipped-OK on non-PR events.
  - path: scripts/check_contract_delta.py
    what: >
      PR 6005 (new): differential PR-vs-base contract gate; fails ONLY on
      findings the PR introduces (closure misses keyed (job_id,path);
      unwired suites by path); inherited findings print ::notice; base tree
      materialized via throwaway git worktree.
  - path: scripts/run_ci_pack.py
    what: >
      PR 6005: closure finding computation factored into importable
      functions shared by the gate and the pre-existing absolute tests (no
      drift copy); same treatment for the unrun-suite census in
      scripts/audit_unrun_tests.py.
  - path: tests/test_contract_delta.py
    what: >
      PR 6005 (new, wired into workflow-yaml job): delta semantics,
      formatting, identity pins, wiring pins.
  - path: tests/test_ci_pack.py
    what: >
      PR 6005: two hard-coded ci.yml structure assertions widened to admit
      the contract-delta job (the second lives in
      tests/test_ci_plan_workflow.py).
verified:
  - claim: integration-baseline is green on healed main (breaker proof).
    command: gh run view 32291151787 --json status,conclusion
    result: >
      completed/success at 19:06Z. Dispatched by hand — the 6002 merge push
      scheduled NO integration-baseline run (silent-no-run class);
      preflighted no live run before dispatching.
  - claim: the heal and the permanent gate are merged, run-level green.
    command: gh pr view 6002 --json state,mergedAt; gh run list --commit <head>
    result: >
      6002 MERGED 18:19:58Z as successor main-red-repair, head runs
      ci/fences/ci-authority all completed/success (run-level reads, not
      rollups); 6005 MERGED 19:27:58Z on green main, head runs all
      completed/success, and its merge push DID schedule integration-baseline
      (32293174816).
  - claim: the closure test fails pre-heal and passes with the widening.
    command: python3.12 -m pytest tests/test_ci_pack.py::test_curated_exclusive_scopes_cover_their_own_import_closure -q
    result: >
      Fails on pre-heal origin/main with the same two misses CI reported
      (biocatalyst-serving engine/options_universe.py; dataos-foundation
      config/issuer_group_allowlist.yml); 1 passed with 6002's diff.
  - claim: the differential gate behaves correctly in both directions.
    command: python3.12 scripts/check_contract_delta.py --base origin/main
    result: >
      exit 0 with 10 inherited ::notice against the then-red main; exit 1
      with exactly one ::error naming job/path/fix on a simulated introduced
      defect; exit 0 again after revert. All three outputs pasted in PR
      6005's body.
  - claim: the armed backlog began draining once the breaker opened.
    command: gh pr list --state open --label merge-on-green --json number --jq length
    result: >
      21 baseline-blocked at the 17:00Z sweep → 17 armed open within the
      hour of the 19:06Z green. Sibling repair 5985 merged after one rerun of
      its checkout infra flake (job 96148198193, blob:none promisor
      early-EOF).
unverified:
  - claim: >
      contract-delta runs and stays inherited-immune on ordinary PRs opened
      after 2026-08-19 19:27Z (proven pre-merge via local functional runs).
    what_would_verify: >
      Next few ordinary PRs show a contract-delta check concluding success
      while main still carries five unwired suites; a PR adding an unwired
      test file or uncovered import goes red on that check alone.
  - claim: >
      the armed backlog fully drains now that the breaker is open.
    what_would_verify: >
      gh pr list --state open --label merge-on-green trending to only PRs
      with real reds or explicit holds by 2026-08-20; sweep logs showing
      merges rather than baseline-blocked.
unresolved:
  - >
    Five suites remain unwired on main (test_analyzer_i18n_percentile,
    test_check_stock_dossier_integrity,
    test_china_special_situations_truth_wave1,
    test_dossier_identity_end_to_end, test_dossier_numeric_contract) — they
    red only the data-gated workflow-yaml job (data-health lane standing
    issue); subject-owners wire them, contract-delta blocks any new one.
next_actions:
  - >
    Verify contract-delta behavior on the next few ordinary PRs
    (inherited-immune; catches introduced defects) and that the backlog
    drains to only genuinely-red/held PRs.
  - >
    W3 at >=72h from the W2 merge (~2026-08-22): trailing-100 green rate
    above 90% via scripts/ci_gate_reliability_report.py plus two consecutive
    ordinary PRs merged with no main-red-repair.
do_not_redo:
  - >
    Do NOT revert the contract-delta gate to an absolute (non-differential)
    check — inherited-red immunity is what keeps a red main from re-jamming
    every open PR at PR level (the always-on-validator trap).
  - >
    Do NOT absorb the five remaining unwired suites into this workstream —
    separate owners; deliberately out of scope in PR 6005.
  - >
    Do NOT treat a merge push that scheduled no integration-baseline run as
    breaker damage — preflight for a live run, then workflow_dispatch it.
danger_areas:
  - >
    check_contract_delta.py's self-test revert (git checkout -- <file>) is a
    full-file restore — it wiped an uncommitted sibling edit to
    legacy-jobs.yml during delivery (caught in review, fixed 5109dcbfcc94);
    commit before running destructive proofs.
  - >
    The workflow-yaml job (audit_unrun_tests home) is gate:data — grammar and
    packing contracts prove on main pushes (integration-baseline) and in the
    data-health lane, NOT in PR packs; contract-delta covers only the two
    jam-class defects PR-side.
---

# 2026-08-19 afternoon merge-train jam — recovery + permanent differential gate

Narrative, receipts, and design rationale live in the frontmatter above and
in PR 6002 / PR 6005 bodies (all functional-proof outputs pasted verbatim in
6005). Cold-stranger summary: post-merge-only contract checks let culprit PRs
merge green and red main afterwards; the breaker then pauses everyone. The
heal widened two curated scopes; the permanent layer is a differential
PR-side contract gate that reds the offending PR before merge and is immune
to inherited reds, so a red main can never again jam the fleet through this
class.
