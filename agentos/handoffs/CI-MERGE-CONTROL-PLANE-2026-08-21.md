---
workstream: "WS:CI-MERGE-CONTROL-PLANE"
session: claude/china-visits-gate-code
model: opus
ended_because: complete
prs: [6152]
decisions: ["DEC:CHINA-NATIVE-COLLECTORS-IS-CODE-GATED"]
mission: >
  Investigate why the CI jobs carrying the China Alpha P1 visit-tape test suites
  appeared dark — .github/ci/legacy-jobs.yml `china-native-collectors` (which runs
  tests/test_china_visits_collector.py) and `unrun-brain-desks` (which runs
  tests/test_china_intel_hub_visits.py and tests/test_china_intel_visits_render.py)
  — and either re-enable them as gate:code jobs or record why they must stay dark.
state_before: >
  Both jobs carry `if: ${{ false }}`, which reads as a deliberate freeze. #6142
  (P1-R1 same-cycle visit derivation) added seven acceptance tests to
  tests/test_china_visits_collector.py believed to have run only locally.
  origin/main at a7058adae14d, three consecutive green ci.yml runs on main.
changed:
  - path: .github/ci/legacy-jobs.yml
    what: >
      `china-native-collectors` reclassified `gate: data` -> `gate: code`, moving its
      18 suites onto the merge gate. One field; no test, dependency, step, `scope:`
      or `paths:` change. A 38-line comment records the measurement and the
      authorship discriminator behind the reclassification.
  - path: agentos/decisions/DEC-CHINA-NATIVE-COLLECTORS-IS-CODE-GATED.md
    what: >
      New decision record. Documents the four alternatives considered (stay dark;
      split the visits suite into a new job; append it to an existing gate:code
      China job; harden the impure test first) and why each was rejected, plus the
      residual exposure and an explicit statement that W2 is not being repealed.
verified:
  - claim: "`if: ${{ false }}` is mandatory boilerplate on every legacy job, not a per-job freeze — a job that omits it fails to load."
    command: "grep -cF 'if: ${{ false }}' .github/ci/legacy-jobs.yml; sed -n '1292,1296p' scripts/run_ci_pack.py"
    result: "199 of 199 jobs carry it; run_ci_pack.py:1292 appends a fatal finding — 'must declare `if: ${{ false }}` so GitHub does not allocate a duplicate runner'."
  - claim: "`gate: data` jobs never execute on a pull request, so china-native-collectors' suites ran post-merge only."
    command: "python3 -c \"import yaml; d=yaml.safe_load(open('.github/workflows/data-health.yml')); print(d.get(True) or d.get('on'))\"; grep -n -- '--gate' .github/workflows/ci.yml .github/workflows/data-health.yml"
    result: "data-health triggers = {workflow_run: [daily completed], workflow_dispatch, schedule: '30 13 * * *'} — no pull_request key. ci.yml:4453/4748/4771 pass `--gate code`; data-health.yml:115 passes `--gate data`."
  - claim: "17 of the job's 18 suites are hermetic — they pass with the data/ tree absent from disk entirely."
    command: "python3 -m pytest <each of the 18 files> -q   (sparse worktree; data/, site/, mockups/, verify_shots/ not checked out)"
    result: "17 green, 515 tests — test_china_visits_collector.py 38 passed, test_china_tushare_spine.py 43 passed, test_china_omo_collector.py 101 passed, test_tushare_minutes_plane.py 72 passed, test_tushare_freshness_tripwire.py 7 passed, test_china_official_corpora.py 25 passed, test_cn_intel_pit_accrual.py 14 passed (etc.). Sole failure: test_china_news_intel_w2.py::TestDelegationEquivalence::test_tag_tickers_alias_via_resolver."
  - claim: "That sole impure test depends on a hand-authored registry, not a nightly ledger — which is code-gated under W1's own discriminator."
    command: "git log --format='%an | %s' -- data/baskets_china/membership.json; git rev-list --count HEAD -- data/baskets_china/membership.json"
    result: "6 commits total; 5 by chriswong6031-creator (newest #4512), 1 dashboard-bot commit that was a page-copy edit. The read path is engine/entity_resolver.py:92-95."
  - claim: "The gate flip moves no narrow-diff ceiling and no semantic proof digest."
    command: "PACK.infer_job_scopes(PACK.load_legacy_jobs(MANIFEST)) + PACK.select_jobs(jobs,[probe]) run before and after the edit; sed -n '192,204p' scripts/ci_semantic_proof.py"
    result: "templates/index.html 128 jobs/5420s, scripts/build_free_content.py 124/5173s, engine/prophet/plan_book.py 120/5175s — identical on both sides. job_exec_sha256 hashes only dependency_install_command / timeout_minutes / runner_contract; `gate` is absent."
  - claim: "The manifest still loads, no contract drifts, and the agentos store is clean."
    command: "python3 scripts/run_ci_pack.py --workflow .github/ci/legacy-jobs.yml --validate-only; python3 scripts/check_contract_delta.py --base origin/main; python3 scripts/agentos.py validate"
    result: "'Validated 199 legacy jobs'; 'contract-delta: 0 introduced, 0 inherited (base a7058adae14d)'; '448 records — 0 error(s), 22 warning(s)' (all 22 pre-existing, mostly sparse-tree phantom-path warnings on WS-STOCK-IDENTITY)."
  - claim: "Pack budget absorbs the move without moving the binding constraint."
    command: "PACK.partition_jobs(load_legacy_jobs(M, gate='code'), 12) before and after"
    result: "code 125 jobs/2,086s -> 126/2,130s; data 74/5,457s -> 73/5,413s. Max gate:code pack weight 274s BEFORE and AFTER; no empty pack in the 12-way code or 6-way data partition."
  - claim: "unrun-brain-desks required no change — its two visit suites were already binding the merge gate."
    command: "python3 -c \"...load_legacy_jobs(MANIFEST, gate='code')...\"; grep -n 'test_china_intel_hub_visits.py' .github/ci/legacy-jobs.yml"
    result: "unrun-brain-desks is present in the gate='code' set (weight 40s); legacy-jobs.yml:9141 names both test_china_intel_hub_visits.py and test_china_intel_visits_render.py."
unverified:
  - claim: "The 18 suites pass in CI's FULL checkout as well as in the sparse tree."
    what_would_verify: "The ci-pack check on PR #6152 that contains china-native-collectors — its step names are the job's own run: lines. This is the PR's own proof run and is the gate for merging it."
  - claim: "tests/test_ci_pack.py passes end to end locally on this branch."
    what_would_verify: "python3 -m pytest tests/test_ci_pack.py -q — started, still running at session end (each infer_job_scopes call costs ~4 minutes and the suite makes many). The three ceiling assertions it guards were measured directly instead, and are identical on both sides of the diff."
  - claim: "The templates/index.html narrow-diff ceiling is genuinely breached on main rather than over-reporting under a sparse checkout."
    what_would_verify: "Re-run the same probe measurement in a FULL checkout (python3 scripts/worktree_sparse.py full) and compare. Scope inference walks the tree, so absent data//site/ may change which jobs a probe selects."
unresolved:
  - >
    The templates/index.html probe measures 128 jobs against a ceiling of 127 on
    origin/main, and the other two probes sit at exactly zero headroom (124/124,
    120/120). Unattributable to this PR — identical on both sides of the diff — but
    if real it means tests/test_ci_pack.py is red on main and nobody is being told,
    because it runs in the `workflow-yaml` job which is itself `gate: data`.
  - >
    data-health.yml on main was failing ALL SIX packs as of run 32430236421
    (2026-08-20T23:49Z). Not investigated. That lane is the only thing grading the
    73 remaining gate:data jobs, so a persistent red there means those jobs' verdicts
    are going unread — the same class of silence W2 promised the lane would prevent.
  - >
    tests/test_china_news_intel_w2.py's one impure test is now on the merge gate. It
    is lawful (PR-authored registry) but weaker than its seventeen siblings, and
    cn_name_to_ticker() swallows a read failure into an empty dict, so the test fails
    on a MISSING file rather than reporting one.
next_actions:
  - >
    Re-measure the three narrow-diff probes in a FULL (non-sparse) checkout to settle
    whether the 128/127 breach is real or a sparse artifact. Do not report a main-red
    without that comparison. If real, choose between curating the newly-matching job's
    scope and ratcheting the ceiling, on the reasoning the test's own docstring uses
    for the reference-integrity and serving-observability precedents.
  - >
    Triage the six red data-health packs on main (run 32430236421) and determine which
    gate:data jobs are actually failing versus failing for a borrowed reason.
  - >
    Optional hardening, worth doing on its own merits: give
    tests/test_china_news_intel_w2.py::test_tag_tickers_alias_via_resolver a pinned
    basket fixture so china-native-collectors is hermetic end to end. Deliberately not
    bundled into #6152 — every PR touching .github/ci/** is authority-changing and the
    doctrine says to keep each wave's diff minimal inside a green window.
do_not_redo:
  - >
    Do NOT try to "enable" a legacy job by deleting its `if: ${{ false }}`. All 199
    jobs carry it and run_ci_pack.py REFUSES to load a job without it
    (scripts/run_ci_pack.py:1292). The marker exists so GitHub does not allocate a
    duplicate runner for a manifest that deliberately lives outside .github/workflows.
    It has never been a per-job freeze. Grep the count before treating it as one.
  - >
    Do NOT re-investigate whether unrun-brain-desks needs enabling for the China visit
    dossier suites. It is already gate: code; test_china_intel_hub_visits.py and
    test_china_intel_visits_render.py have been binding the merge gate since they were
    wired (legacy-jobs.yml:9141).
  - >
    Do NOT split tests/test_china_visits_collector.py into a NEW gate:code job as a way
    to make it binding. Considered and rejected in DEC:CHINA-NATIVE-COLLECTORS-IS-CODE-GATED:
    a new job is exactly what the narrow-diff ceilings count, and they sit at zero
    headroom — it would red tests/test_ci_pack.py while leaving sixteen equally hermetic
    suites off the gate. The gate flip adds no job at all.
  - >
    Do NOT re-derive the data-dependency of the 18 suites from source reading alone. The
    sparse checkout is a decisive natural experiment: run the file with data/ absent. 17
    pass, and the one that fails names its dependency precisely.
danger_areas:
  - >
    Every PR touching .github/ci/**, .github/workflows/**, scripts/**, or .claude/hooks/**
    sets authority_changed=true (scripts/ci_authority_paths.py), which removes the
    base-inherited-red excuse entirely. Merging one while main is red buys a permanently
    unclearable stop gate whose only lever is a green ci.yml run on a main DESCENDANT.
    Verify main is green immediately before merging, and keep the diff minimal.
  - >
    `gate` is safe to flip because it feeds neither scope inference nor the exec digest.
    ADDING or REMOVING a job is not — that moves the narrow-diff job counts and can red
    tests/test_ci_pack.py's ceilings, which currently have zero headroom on two of three
    probes. Measure both probes before and after any job-count change.
  - >
    Reclassifying data -> code is a one-way ratchet in risk terms: a suite that turns out
    to assert over moving data will red the MERGE GATE for the whole fleet, not an issue
    a human reads. Require the sparse-absent measurement, not a source reading, before
    moving any other job across.
  - >
    tests/test_ci_pack.py is extremely slow to run locally — each infer_job_scopes call is
    roughly four minutes and the suite makes many. Budget for it or measure the specific
    assertion directly.
---

## The shape of the mistake this wave corrects

W1 (#5954) classified 199 jobs in one pass and got 198 of them defensible. This one
it did not, and the reason is worth keeping: the job's suites call
`config.data_dir()` all over, which looks exactly like a data dependency until you
notice that every call is redirected to `tmp_path` by an autouse fixture. A static
read of the source says "data"; running the suite with no data tree at all says
"code". The sparse session worktree turned out to be the cheap decisive instrument
for that question, and it should be the first thing reached for the next time a
gate classification is in doubt.

The second half is subtler. One suite genuinely reads a committed file — but
"reads a file under `data/`" and "a nightly can flip this verdict" are different
claims, and only the second one is what `gate:` asks about. `data/` holds both
nightly ledgers and hand-authored registries, and the git authorship of the
asserted file is what separates them. W1 said so itself and had already moved 56
jobs on exactly that test; this job was simply missed.

## What was NOT wrong

The `if: ${{ false }}` marker, which is what the investigation was originally
pointed at. It is mandatory on all 199 jobs and enforced by the loader. Nothing
about it was ever a freeze, and no record anywhere describes one — the search for a
deliberate disablement decision came back empty because there was never a decision
to find.
