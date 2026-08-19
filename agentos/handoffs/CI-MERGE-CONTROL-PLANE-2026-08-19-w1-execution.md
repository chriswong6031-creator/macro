---
workstream: WS:CI-MERGE-CONTROL-PLANE
session: claude/w1-gate-classification (worktree new-session-97d810)
model: fable
ended_because: complete
prs: [5941, 5954]
discoveries:
  - DSC:BREADTH-LEDGER-REVISES-HISTORY
mission: >
  Execute the W1-W4 remediation handed off by the diagnosis session
  (CI-MERGE-CONTROL-PLANE-2026-08-19-gate-reliability.md): drain the four
  armed PRs, then classify all 194 merge-gate jobs (W1), split the lane (W2),
  prove (W3), and guard (W4). Operator grant §4b of
  research/CI_MERGE_GATE_RELIABILITY_ROOT_CAUSE_2026_08_19.md applies.
state_before: >
  Main red on four rotating roots (signal-contract, market-memory-contract,
  house-law-registry, unrun-prophet-learning-loop); #5937/#5938/#5922/#5737
  armed and merge-blocked; W1-W4 not started.
changed:
  - path: tests/test_market_memory_breadth_observation.py + _store.py + tests/fixtures/market_memory/
    what: >
      (PR #5941, MERGED 07:38Z) market-memory-contract heal. Root cause deeper
      than the diagnosis knew: the nightly REVISES historical breadth rows
      (DSC:BREADTH-LEDGER-REVISES-HISTORY), so the truncation-frozen fixture
      mutated under the test. Fixed with a byte-pinned era-consistent fixture
      pair captured from one nightly commit (448cfacc0957). 43/43 pass.
  - path: .github/ci/legacy-jobs.yml + scripts/run_ci_pack.py + tests/test_ci_pack.py
    what: >
      (PR #5954) W1 - every job declares gate: code | data. Final split 120
      code / 74 data. Loader validates the field (invalid fatal; absent
      defaults to code so nothing leaves the gate silently); real-manifest
      test forces declaration. Also carries the 6-line wiring heal for the
      workflow-yaml red that #5938's merge left on main (its new suite named
      by no run: step - wired into the workflow-yaml job).
verified:
  - claim: all four handoff PRs are merged.
    command: gh pr view 5937/5938/5922/5941 --json state
    result: >
      #5937 admin-merged 07:28Z (grant, inherited reds named in comment);
      #5941 admin-merged 07:38Z (same); #5938 merged 07:47Z by the account
      token mid-run; #5922 merged ~08:05Z. #5737 deliberately left armed -
      design-authority conditions gate, another lane's flagship UI.
  - claim: the W1 classification is judgment-verified, not heuristic.
    command: see PR #5954 body (by-name list, §0 gate 4)
    result: >
      Four Opus analyst sweeps over every named suite + main-loop
      adjudication reclassified 56 of the heuristic's 130 data-candidates as
      code. Decisive discriminator - git authorship of the asserted file:
      dashboard-bot commits = nightly-moved (data); PR-only commits = reviewed
      input (code), even when parked under data/ (e.g. biocatalyst fixtures,
      data/experiments/registry_seed.json, data/intl_risk/cb_calendar.yml).
unverified:
  - claim: the split raises main's green rate above 90%.
    what_would_verify: >
      W3 - python3 scripts/ci_gate_reliability_report.py over a trailing 100
      runs measured >=72h after W2 lands, plus two consecutive ordinary PRs
      merging with no main-red-repair between them.
unresolved:
  - >
    W2 build was commissioned to a Sonnet builder (frozen spec: --gate filter
    in run_ci_pack.py applied before partition arithmetic; --gate code at
    ci.yml's THREE run_ci_pack call sites (~4423, ~4717, ~4739) so baselines
    prove exactly what the gate runs; new .github/workflows/data-health.yml -
    workflow_run on daily + dispatch + 13:30Z cron fallback, 6 packs,
    ubuntu-latest ONLY, one standing issue labeled data-health; W4
    reachability test). If the builder's branch is not yet a PR, its worktree
    branch claude/w2-gate-split is based on claude/w1-gate-classification.
  - >
    house-law-registry and unrun-prophet-learning-loop stay red until the
    next nightly writes a symbol-directory snapshot (verify
    data/symbol_directory/manifest.json shows last_snapshot_date past
    2026-08-10 and n_symbols non-zero - it read 0 while frozen) and advances
    data/baskets/ohlcv/ASTS.parquet. Do NOT fix the tests; both are correct.
  - >
    #5938 was merged at 07:47:39Z by the account token while its own run was
    red-and-in-flight (its workflow-yaml red was its own diff's). Mechanism
    unattributed - possibly an operator hand-merge, possibly a sweeper path
    that needs a look. If PRs start merging mid-run again, attribute this
    properly before trusting merge-on-green's wait-for-concluded contract.
do_not_redo:
  - >
    Do not re-run the 194-job classification from scratch - the split is in
    the manifest (PR #5954 body carries the by-name list and the reasons
    live in this handoff's session transcripts). Reclassify individual jobs
    with evidence, one line each.
  - >
    Do not "fix" ASTS/VMRK reds (correct data reporting), and do not advance
    the market-memory fixture constant - advance BOTH pinned fixture files
    together from one commit if the fixture era must move.
  - >
    Do not derive frozen fixtures by truncating live ledgers anywhere -
    DSC:BREADTH-LEDGER-REVISES-HISTORY.
danger_areas:
  - >
    Both W1 (#5954) and W2 are authority-changing AND global invalidators
    (legacy-jobs.yml / ci.yml edits -> full-manifest runs that inherit every
    latent main red). Grant §4b covers admin-merging with inherited reds
    named by logical job IN THE PR before merging.
  - >
    After W2 lands, data-gated jobs no longer run on PRs AT ALL - a PR
    editing a data-job's own suite gets no pre-merge run of it. That is the
    accepted §4 trade; data-health reds an issue within a day (§0 gate 3).
next_actions:
  - Merge #5954 on its run's conclusion (grant; name residual inherited reds).
  - Land W2 from the builder's branch; verify data-health.yml fires after the
    next nightly and its issue plumbing works (dispatch it once by hand).
  - W3 at >=72h - re-measure green rate; W4 test ships with W2.
  - Verify the symbol-directory collector recovered after the next nightly.
  - Then update WS:CI-MERGE-CONTROL-PLANE status and close the loop with a
    final handoff.
---

## One-line state

W1 armed (#5954, full split 120/74 + loader contract), W2 building against a
frozen spec, all four inherited-red PRs drained, two of main's four rotating
roots healed at source and the other two clear on the next nightly.
