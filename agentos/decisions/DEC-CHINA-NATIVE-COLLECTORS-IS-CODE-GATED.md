---
key: CHINA-NATIVE-COLLECTORS-IS-CODE-GATED
question: >
  W1 (#5954) classified the `china-native-collectors` legacy job `gate: data`,
  which under W2 keeps it off the merge gate entirely — `data-health.yml` has no
  `pull_request` trigger, so none of its eighteen suites has ever run on a pull
  request. Is that classification correct, or is the job code-gated and owed a
  place on the merge gate?
answer: >
  The job is CODE-gated and is reclassified `gate: data` -> `gate: code`. No test
  file, dependency, step, or scope declaration changes; only the `gate:` field
  moves, plus the comment recording the evidence. The eighteen suites now bind
  the merge gate, which is what makes #6142's seven P1-R1 same-cycle acceptance
  tests in tests/test_china_visits_collector.py enforceable on the PR that
  changes them rather than post-merge only.
rationale: >
  Two independent lines of evidence, both pointing the same way, and both of them
  the discriminators W1 itself declared.

  (1) Direct measurement. Under a sparse checkout with `data/` absent from disk
  entirely, 17 of the job's 18 suites pass green (515 tests). A suite that passes
  with no data tree at all cannot have a verdict a nightly data commit can move.
  They are hermetic by construction, not by luck: test_china_visits_collector.py
  carries two autouse fixtures redirecting `config.data_dir` AND
  `lib.store.read_status`/`write_status` to tmp_path; test_china_official_corpora.py
  monkeypatches `_store_dir`; test_cn_intel_pit_accrual.py monkeypatches the
  `OUT`/`OUT_HIST` module globals; test_china_tushare_spine.py passes tmp_path as
  an explicit base_dir to every `spine.*` call.

  (2) The authorship discriminator. The 18th suite,
  tests/test_china_news_intel_w2.py, has exactly one test that reaches the real
  tree: `tag_tickers` -> `entity_resolver.resolve_cn` -> `cn_name_to_ticker()`
  reads `config.data_dir()/"baskets_china"/"membership.json"`. That file is a
  hand-authored registry, not a nightly ledger — six commits in its entire life,
  five PR-authored (newest #4512) and the lone dashboard-bot commit a page-copy
  edit. It moves only when a pull request moves it. W1's own decisive
  discriminator was "git authorship of the asserted file: dashboard-bot vs
  PR-only", and W1 already reclassified 56 jobs into exactly this category:
  "pinned fixtures, tmp_path roots, and hand-authored registries the heuristic's
  read_parquet match over-flagged". The root-cause doctrine states the rule
  outright: "a job that reads `data/` to build a fixture is code-gated, and a job
  that reads a pinned golden is code-gated".

  This is a correction of one job's classification, not a repeal of W2. The
  reliability program's thesis — assertions over the moving data tree do not
  belong on the merge gate — is unchanged and is why the correction matters:
  leaving a hermetic job on the data side costs merge-gate coverage while buying
  none of the stability W2 was built to win.

  Cost is bounded and measured: +44 weight-seconds onto a 2,086s `gate: code` set
  spread over twelve packs, and the max pack weight does not move (274s before and
  after) because the job lands in a lighter pack. `gate` is not an input to
  `infer_job_scopes` or `select_jobs`, and `job_exec_sha256` hashes only
  dependency_install_command / timeout_minutes / runner_contract — so the
  narrow-diff ceilings in tests/test_ci_pack.py and every semantic proof digest
  are untouched by this edit, which is what separates a gate flip from ADDING a
  job (the ci-pack smear/ceiling trap of #6115/#6133).
alternatives:
  - option: "Leave the job `gate: data` and record why the suites must stay dark"
    why_not: >
      Nothing in the manifest, in DO_NOT_REBUILD.md, or in agentos/decisions
      records a deliberate freeze of this job, and the measurement refutes the
      classification rather than confirming it. `if: ${{ false }}` is not the
      freeze it resembles — run_ci_pack.py REFUSES to load any legacy job that
      omits it, and all 199 jobs carry it. Staying dark would leave seven
      acceptance tests written specifically to pin same-cycle visit derivation
      unable to fail the PR that breaks them.
  - option: "Split tests/test_china_visits_collector.py into a NEW `gate: code` job"
    why_not: >
      Fixes the narrow symptom and leaves sixteen equally hermetic suites off the
      merge gate. Worse on risk, not better: a NEW job is exactly what the
      narrow-diff ceilings count, and they sit at zero headroom
      (scripts/build_free_content.py 124/124, engine/prophet/plan_book.py 120/120),
      so a new unscoped job would red tests/test_ci_pack.py. The gate flip adds no
      job at all.
  - option: "Append the visits suite as a step to an existing `gate: code` China job (china-board-breadth / china-search-universe / china-native-w2)"
    why_not: >
      Adds no job, but splits one collector family's suites across two owners for
      no reason other than avoiding the classification question, and orphans the
      other sixteen suites. It also mis-files the subject: china-board-breadth's
      declared subject is whole-board 涨跌家数 behind the heatmap, not the visit tape.
  - option: Harden test_china_news_intel_w2.py's one impure test with a pinned
      basket fixture before flipping
    why_not: >
      Not needed for the classification — a PR-authored registry is already
      code-gated under W1's discriminator — and it would widen an authority-changing
      PR into engine test semantics during a green window that
      research/CI_MERGE_GATE_RELIABILITY_ROOT_CAUSE_2026_08_19.md §"the trap"
      says to spend on the smallest possible diff. Worth doing on its own merits
      later; it is not a precondition here.
evidence:
  - "PR #6142 (650be4dfe6d5) added the seven P1-R1 acceptance tests to tests/test_china_visits_collector.py; the job that names it (.github/ci/legacy-jobs.yml:2677) was gate: data, so they never ran on that PR."
  - "gate -> lane wiring: .github/workflows/ci.yml:4453,4748,4771 pass `--gate code`; .github/workflows/data-health.yml:115 passes `--gate data`."
  - "data-health.yml triggers resolve to {workflow_run: [daily completed], workflow_dispatch, schedule: 30 13 * * *} — no pull_request key, so gate: data jobs never execute on a PR."
  - "Sparse-checkout measurement (data/ absent), python3 -m pytest <file> -q per file: 17/18 green — test_china_visits_collector.py 38 passed, test_china_tushare_spine.py 43 passed, test_tushare_freshness_tripwire.py 7 passed, test_china_official_corpora.py 25 passed, test_cn_intel_pit_accrual.py 14 passed, test_china_omo_collector.py 101 passed, test_tushare_minutes_plane.py 72 passed (etc.)."
  - "Sole impurity: tests/test_china_news_intel_w2.py::TestDelegationEquivalence::test_tag_tickers_alias_via_resolver, via engine/entity_resolver.py:92-95 `config.data_dir()/\"baskets_china\"/\"membership.json\"`."
  - "git log --format='%an' -- data/baskets_china/membership.json: 6 commits total, 5 by chriswong6031-creator (newest #4512), 1 dashboard-bot page-copy edit — PR-authored registry, not a nightly ledger."
  - "W1 discriminator + reclassified category: commit d7a9a026b54e (#5954) message — 'decisive discriminator = git authorship of the asserted file: dashboard-bot vs PR-only ... reclassified 56 of those as code - mostly pinned fixtures, tmp_path roots, and hand-authored registries'."
  - "Doctrine: research/CI_MERGE_GATE_RELIABILITY_ROOT_CAUSE_2026_08_19.md §Staged plan W1 — 'a job that reads data/ to build a fixture is code-gated, and a job that reads a pinned golden is code-gated'."
  - "python3 scripts/run_ci_pack.py --workflow .github/ci/legacy-jobs.yml --validate-only -> 'Validated 199 legacy jobs'."
  - "python3 scripts/check_contract_delta.py --base origin/main -> 'contract-delta: 0 introduced, 0 inherited (base a7058adae14d)'."
  - "Gate split before -> after: code 125 jobs/2,086s -> 126/2,130s; data 74/5,457s -> 73/5,413s. gate: code 12-pack max weight 274s before AND after; no empty pack in either lane (12-way code, 6-way data)."
  - "scripts/ci_semantic_proof.py:192-204 — job_exec_sha256 hashes dependency_install_command / timeout_minutes / runner_contract only; `gate` is absent, so no proof digest moves."
  - "scripts/run_ci_pack.py:1292-1296 — a legacy job that omits `if: ${{ false }}` fails to load; all 199 jobs carry it, so it is mandatory boilerplate and never a per-job freeze."
affects:
  - "WS:CI-MERGE-CONTROL-PLANE"
  - ".github/ci/legacy-jobs.yml"
  - "tests/test_china_visits_collector.py"
  - "tests/test_china_news_intel_w2.py"
confidence: high
reversibility: easy
decided_by: "session: claude/china-visits-gate-code"
decided_at: 2026-08-21
review_by: 2026-09-21
---

## Residual exposure, stated plainly

One test on the merge gate now reads a real committed file
(`data/baskets_china/membership.json`) rather than a fixture. That is lawful
under W1's discriminator — the file moves only in pull requests — but it is a
weaker guarantee than the other seventeen suites carry, and
`cn_name_to_ticker()` swallows a read failure into an empty dict
(`except Exception: pass`), so the test fails on a *missing* file rather than
reporting one. The follow-up worth doing on its own merits is a pinned basket
fixture for `test_tag_tickers_alias_via_resolver`, after which the job is
hermetic end to end. It was deliberately not bundled here: every PR touching
`.github/ci/**` is authority-changing, and the doctrine's own instruction for
this program is to land each wave in the smallest possible diff inside a
verified-green window.

## What this does NOT change

W2 stands. `gate: data` remains the correct home for assertions over the moving
data tree, `data-health.yml` remains their lane, and 73 jobs stay there. This
record corrects one job's classification on measurement; it is not a precedent
for moving data-gated jobs onto the merge gate to obtain coverage.
