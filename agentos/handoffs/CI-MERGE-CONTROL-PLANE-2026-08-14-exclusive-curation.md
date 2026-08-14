---
workstream: "WS:CI-MERGE-CONTROL-PLANE"
session: claude-ci-exclusive-scope-curation
model: opus
ended_because: ci_handoff
mission: >
  Close the "heavy code-file fanout" item the 2026-08-14 incident handoff left
  unresolved: curate `scope: exclusive` declarations for the heaviest legacy CI
  jobs so an ordinary code PR stops selecting ~120/188 jobs and twelve packs.
state_before: >
  PR #5585 shipped the `scope: exclusive` mechanism with exactly one
  union-tier user (free-content-estate) and zero exclusive ones. Measured on
  #5585's planner against main's manifest: a one-file diff selected 123/188
  jobs and 11 packs (engine module), 129/188 and 12 packs (template), 129/188
  and 11 packs (script), 146/188 and 12 packs (site/theme.css).
changed:
  - path: .github/ci/legacy-jobs.yml
    what: >
      Eight `scope: exclusive` + `paths:` declarations — unrun-government-
      revenue-grader (322s), biocatalyst-worker (274), biocatalyst-serving
      (272), flow-surface (267), unrun-picks-boards (245), biocatalyst-history
      (172), unrun-subsector-themes (134), inline-js (124). Each carries a
      comment naming the weight and why the tier split reaches it.
  - path: tests/test_ci_pack.py
    what: >
      Five fixtures: the declared set is pinned by name; every declaration is
      re-checked against the import closure inference WOULD have derived (zero
      MISS); every curated drop is proven to have been a fallback-tier match,
      never owned evidence; the before/after job/weight/pack bounds; and
      inline-js's rendered-tree ownership.
verified:
  - claim: all eight declarations cover their own import closure with zero misses
    command: python3 -m pytest tests/test_ci_pack.py -k "curated or exclusive or inline_js or narrows" -q
    result: 5 passed (with PR #5585's planner installed)
  - claim: the manifest loads under the fatal declared-scope coverage audit
    command: "PACK.load_legacy_jobs(MANIFEST) with #5585's run_ci_pack.py"
    result: "LOADED OK: 188 jobs; exclusive: 8"
  - claim: ordinary code PRs narrow ~24% of selected pack weight, 12 packs -> 9
    command: CI_CHANGED_FILES_JSON='["<probe>"]' python3 scripts/run_ci_pack.py --workflow .github/ci/legacy-jobs.yml --pack-count 12 --plan-only --changed-from HEAD
    result: >
      templates/index.html 129->123 jobs, 6677->5115 weight-seconds (-23.4%),
      12->9 packs; scripts/build_free_content.py 129->123, 6430->4878
      (-24.1%), 11->9; engine/prophet/plan_book.py 123->117, 6416->4864
      (-24.2%), 11->9; site/theme.css 146->139, 6846->5160 (-24.6%), 12->9.
  - claim: every one of the five fixtures can actually fail
    command: four manifest mutations run against the suite
    result: >
      dropping engine/earnings_narrative/** from flow-surface failed the
      closure-coverage fixture naming all 8 orphaned files; stripping
      inline-js's site/**+templates/** failed the rendered-tree fixture;
      un-declaring one job failed the set fixture; removing all eight
      exclusivity flags failed the narrowing fixture at 130 jobs.
unverified:
  - claim: live PR-lane behavior of the curated scopes
    what_would_verify: >
      this PR cannot run its own packs until #5585 merges (see unresolved);
      after that, a one-file template PR should show ci-plan selecting ~123
      jobs into 9 packs.
unresolved:
  - >
    THIS PR IS BLOCKED ON PR #5585 AND SAYS SO LOUDLY. `scope` is not in
    main's ALLOWED_JOB_KEYS, so today's loader refuses the manifest with
    "job '<id>' has unsupported keys: scope" and every pack reds. That is the
    intended gate, not an accident: the ordering is self-enforcing, main can
    never take this change before the mechanism, and the sweeper will not
    merge a genuinely red head. Once #5585 lands, rerun this PR's checks.
  - >
    Six of the fourteen weight-ranked candidates were deliberately SKIPPED:
    market-memory-contract (416s), capital-structure-intelligence (247),
    marketing-engine (250), unrun-market-plumbing (114), neural-web-core (89),
    and font-ui-defined (96). The first five have 500-813-file closures whose
    honest declaration runs 106-158 patterns — a frozen list that large rots
    faster than it helps. font-ui-defined was skipped for the opposite reason:
    its inferred scope is already correct and narrow, so a declaration would
    add freeze risk for zero measured drops. Re-open these only with a
    generated-and-checked-in declaration, not a hand-written one.
next_actions:
  - >
    When PR #5585 merges, rerun this PR's checks (`gh pr checks --watch
    --interval 60`, or let the armed merge-on-green label re-sweep). Both of
    this branch's failure modes — the manifest's `scope` key and this record's
    WS:CI-MERGE-CONTROL-PLANE reference — clear on that one merge.
  - >
    After merge, confirm the live numbers on a real one-file template PR:
    ci-plan should report ~123/188 jobs and 9 packs, not 129 and 12.
  - >
    Optional next wave: regenerate declarations for the six skipped heavies
    (see unresolved) from their closures and let the coverage fixture prove
    them. market-memory-contract at 416s is the largest single prize left.
do_not_redo:
  - >
    Do not declare a scope narrower than the job's import closure to chase a
    bigger number. Measured: every drop this wave produces was a FALLBACK-tier
    match; not one owned/closure edge was removed. The closures are real —
    engine/__init__.py is empty, so there is no package-init hub to blame, and
    the shared core across the ten big jobs is only 115 files.
  - >
    Do not glob tests/** or scripts/** inside an exclusive declaration. Those
    are the most-edited trees in the repo; globbing them widens the heaviest
    jobs onto every test edit and gives back more than the curation wins.
    Name the files (they are short, and the load-time coverage audit re-checks
    exactly those).
danger_areas:
  - >
    legacy-jobs.yml is fleet-hot AND is a GLOBAL_INVALIDATOR — re-fetch
    origin/main and re-resolve before any push; this PR runs the full suite by
    construction.
  - >
    An exclusive declaration FREEZES inference for that job. The only thing
    standing between a new import and a silently-never-running job is
    test_curated_exclusive_scopes_cover_their_own_import_closure. Do not
    weaken or skip that fixture.
---

Cold-stranger note: the method is in the fixtures, not in a doc. Read
`test_curated_exclusive_scopes_cover_their_own_import_closure` first — it
re-derives what inference WOULD have produced for each exclusive job and
diffs it against the declaration. That is the whole safety argument, and it
is why declarations here were generated from the closure rather than written
by eye. To extend the wave to a skipped job, generate its declaration the same
way and let that fixture prove it.
