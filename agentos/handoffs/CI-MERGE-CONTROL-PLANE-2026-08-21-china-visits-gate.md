---
workstream: WS:CI-MERGE-CONTROL-PLANE
session: claude/china-visits-collector-gate-code
model: fable
ended_because: complete
mission: >
  Investigate a report that the CI jobs running the China Alpha P1 visit-tape
  test suites were "dark" because they carry `if: ${{ false }}`, and either
  re-enable them as `gate: code` or record why they must stay dark.
state_before: >
  `.github/ci/legacy-jobs.yml` at origin/main a7058adae14d: 199 jobs, all 199
  carrying `if: ${{ false }}`, split 125 `gate: code` / 74 `gate: data` by
  PR #5954 (W1 of research/CI_MERGE_GATE_RELIABILITY_ROOT_CAUSE_2026_08_19.md).
  `tests/test_china_visits_collector.py` was named by the `china-native-collectors`
  job (`gate: data`); `tests/test_china_intel_hub_visits.py` and
  `tests/test_china_intel_visits_render.py` by `unrun-brain-desks` (`gate: code`).
changed:
  - path: .github/ci/legacy-jobs.yml
    what: >
      Moved the `china institutional-visit tape collector tests (P1)` step
      (tests/test_china_visits_collector.py) out of `china-native-collectors`
      (gate: data) and into `china-native-w2` (gate: code). No dependency line
      changed; both jobs keep their `if: ${{ false }}` and their gate. Left a
      pointer comment at the old site so the suite does not read as a new
      wiring hole.
  - path: agentos/discoveries/DSC-LEGACY-JOB-IF-FALSE-IS-MANDATORY-NOT-A-FREEZE.md
    what: >
      New discovery record: `if: ${{ false }}` is a mandatory manifest field
      enforced by run_ci_pack.py, not a per-job freeze; `gate:` is what decides
      merge-gate binding.
verified:
  - claim: >
      `if: ${{ false }}` is mandatory on every legacy job, so its presence is
      not evidence a job is disabled.
    command: >
      grep -cF 'if: ${{ false }}' .github/ci/legacy-jobs.yml ; sed -n
      '1292,1295p' scripts/run_ci_pack.py
    result: >
      199 of 199 jobs carry it; the validator emits "must declare `if:
      ${{ false }}` so GitHub does not allocate a duplicate runner" for any job
      that omits it.
  - claim: >
      `unrun-brain-desks` was never dark — both china_intel_hub visit suites
      already bind the merge gate and ran green on PR #6142's head.
    command: >
      gh api repos/mastermindx-market-intelligence/macro/commits/470dcb1bc10059bbb401fb9c55d43f9f9385c566/check-runs
      --jq '.check_runs[]|select(.name|test("ci-pack|ci-gate"))|"\(.name) \(.conclusion)"'
      ; python3 scripts/run_ci_pack.py --workflow .github/ci/legacy-jobs.yml --validate-only
    result: >
      ci-pack-0..11 and ci-gate all `success`; `unrun-brain-desks` is present in
      the selected-jobs list.
  - claim: >
      `china-native-collectors` is not dark either — it runs nightly in
      data-health.yml, and its visit-tape step executed there on 2026-08-21.
    command: >
      gh run view 32430236421 --job <data-pack-5> --log | grep -i 'china institutional-visit'
    result: >
      "##[group]china-native-collectors — china institutional-visit tape
      collector tests (P1)"; the job does not appear in that run's --log-failed
      output, i.e. it passed while five of six packs failed on other jobs.
  - claim: >
      Exactly one of the 18 suites in `china-native-collectors` is data-coupled,
      so the job's `gate: data` is correct and must NOT be flipped.
    command: >
      python3 -m pytest tests/<each of the 18 files> -q  (run individually in a
      sparse worktree with data/ absent)
    result: >
      17 pass with data/ absent; `tests/test_china_news_intel_w2.py` fails
      1 of 31 (`assert '600519.SS' in []`) via engine/entity_resolver.py:102
      reading data/baskets_china/membership.json.
  - claim: >
      The moved suite passes under china-native-w2's exact install line, so the
      move adds no dependency.
    command: >
      python3 -m venv w2venv && w2venv/bin/pip install pytest pandas numpy
      pyarrow pyyaml requests openpyxl && w2venv/bin/python -m pytest
      tests/test_china_visits_collector.py -q
    result: "38 passed, 3 warnings in 67.13s"
  - claim: The manifest still validates and introduces no contract delta.
    command: >
      python3 scripts/run_ci_pack.py --workflow .github/ci/legacy-jobs.yml
      --validate-only ; python3 scripts/check_contract_delta.py --base origin/main
    result: >
      "Validated 199 legacy jobs; 199 in scope"; gate-code manifest 125 jobs,
      pack weights [1043,1043] -> [1045,1044]; "contract-delta: 0 introduced,
      0 inherited (base a7058adae14d)".
unverified:
  - claim: >
      `tests/test_china_news_intel_w2.py`'s single failure is caused ONLY by the
      sparse checkout and would pass on a full tree.
    what_would_verify: >
      `python3 scripts/worktree_sparse.py full` then re-run that one test; or
      read the same job's verdict in a green data-health run.
unresolved:
  - >
    16 pure-code suites besides the visit tape are still off the merge gate
    purely because they share `china-native-collectors` with the one
    data-coupled suite. Splitting them out is a real improvement and is NOT
    done here.
  - >
    tests/test_ci_pack.py::test_exclusive_curation_narrows_ordinary_code_prs is
    RED on origin/main independently of this change: the templates/index.html
    probe selects 128 jobs against a ceiling of 127. It lives in the
    `workflow-yaml` job, which is itself `gate: data`, so the merge gate cannot
    see it.
next_actions:
  - >
    Optional follow-up, own PR: split `china-native-collectors` so only the
    step naming tests/test_china_news_intel_w2.py stays `gate: data` and the
    other 16 pure-code suites move to a `gate: code` home. Do NOT create a new
    always-on job for them while the templates/index.html probe is over its
    ceiling — add them to an already-selected `gate: code` job as this PR did,
    or curate a `scope:` first.
  - >
    Separately: heal the 128>127 ceiling breach, or ratchet it with a measured
    justification in the docstring, per that test's own wave-note convention.
do_not_redo:
  - >
    Do NOT delete `if: ${{ false }}` from a legacy job to "re-enable" it. The
    validator fails closed on the whole manifest and every pack dies at exit 2.
    See DSC:LEGACY-JOB-IF-FALSE-IS-MANDATORY-NOT-A-FREEZE.
  - >
    Do NOT flip `china-native-collectors` to `gate: code`. Its
    tests/test_china_news_intel_w2.py step is genuinely data-coupled; promoting
    the job re-adds a moving-data assertion to the merge gate, which is the
    exact coupling the W2 split removed.
  - >
    Do NOT treat `unrun-brain-desks` as dark. It is `gate: code` and its two
    china_intel_hub visit suites already ran green on PR #6142.
  - >
    Do NOT diagnose a `gate: data` job as "never runs" without reading
    data-health.yml. That lane is frequently red for unrelated reasons, but the
    per-job groups in its pack logs carry the real verdicts.
danger_areas:
  - >
    `gate` is a per-JOB field. One data-coupled suite silently demotes every
    other suite in the same job, and nothing in the manifest surfaces that.
  - >
    Adding a NEW legacy job (rather than a step to an existing one) adds a job
    to every narrow-diff probe in
    tests/test_ci_pack.py::test_exclusive_curation_narrows_ordinary_code_prs.
    Its templates/index.html ceiling has zero headroom and is already breached.
  - >
    Any edit under `.github/ci/**` sets `authority_changed=true`
    (scripts/ci_authority_paths.py), which removes the base-inherited-red
    excuse for the merged head. Check main is green immediately before merging.
prs: [6142]
discoveries: ["DSC:LEGACY-JOB-IF-FALSE-IS-MANDATORY-NOT-A-FREEZE"]
---

## Why this ended up being a one-step move rather than a re-enable

The task arrived as "these CI jobs are dark, turn them on". Both halves of that
premise turned out to be false, and the false half is load-bearing enough to be
worth stating plainly: `if: ${{ false }}` does not disable a legacy job. It is
required on all 199 of them, because `ci.yml`'s `ci-pack-N` matrix executes the
manifest through `run_ci_pack.py --execute` and the line exists only to stop
GitHub allocating a second, duplicate runner per job. Deleting it is actively
destructive — the validator refuses the manifest and every pack exits 2.

What was real is narrower and still worth fixing: `gate:` is a per-job field,
`china-native-collectors` holds 18 suites, and exactly one of them
(`tests/test_china_news_intel_w2.py`, through
`engine/entity_resolver.py:102` reading `data/baskets_china/membership.json`)
is moved by the nightly. That one suite correctly makes the job `gate: data`,
and it dragged the visit-tape suite off the merge gate with it — so PR #6142's
seven P1-R1 acceptance tests could only ever grade a day late, in a lane that
is red most nights for reasons of its own.

The fix is a move, not a reclassification: the suite is pure-code (its
`_tmp_data_dir` fixture monkeypatches `lib.config.data_dir` to `tmp_path`
module-wide), so it belongs in `china-native-w2`, the `gate: code` sibling that
already owns the other China-native collector suites and already carries every
dependency it needs.
