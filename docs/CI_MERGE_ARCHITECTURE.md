# CI + merge architecture (current state)

One page, no archaeology. History and receipts: workflow comments and
`research/CI_MERGE_CONTROL_PLANE_RECOVERY_2026_08_14.md`.

## The proof pipeline (`.github/workflows/ci.yml`)

Three jobs, every PR, hosted runners:

1. **ci-plan** (~1–3 min) — the single planning authority AND the fast
   preflight.
   - Checkout: `fetch-depth: 1`, `blob:none`. The PR diff comes from the
     **PR files API** (`scripts/ci_plan_changed_files.py`), not git history.
     Any doubt (API error, 3000-file truncation) emits `null` → full suite.
   - Selection: `scripts/run_ci_pack.py --plan-only` over the 188-job manifest
     `.github/ci/legacy-jobs.yml`. Scope inference (~106s) is cached via
     `actions/cache` keyed on the first-party `.py` tree + manifest (exact
     match only); a warm plan costs ~1s.
   - Scope tiers per job: `paths` (named evidence: closure files, literal
     refs, declared scopes, md-kind claims) always select; `fallback_paths`
     (opaque subprocess/traversal smear) select for everything EXCEPT
     narrative files (`**/*.md`); `scope: exclusive` in the manifest makes
     declared paths replace inference entirely (coverage-audited, fatal).
     Global invalidators (workflow/manifest/selector/conftest/dependency
     files) still run the full suite.
   - The plan (job lists per pack, weights, explanations, `plan_sha256`,
     `manifest_sha256`) is published as job outputs + the `ci-plan-document`
     run artifact. Pack count scales with selected weight
     (`PACK_TARGET_SECONDS`, 1..12); full-suite runs always use 12 so main's
     baseline publishes all of `ci-pack-0..11`.
   - **Preflight steps** (after the plan, before any pack): workflow YAML
     parse, `audit_unrun_tests` (a new test suite wired into no workflow reds
     HERE, in seconds), trigger closure, conflict markers. A preflight red
     fails `ci-plan`, so no pack launches.
2. **ci-pack-N** (matrix from the plan) — downloads nothing; the plan document
   arrives via job output, is digest-verified (`--plan-json` +
   `--expect-plan-sha`, recomputed from the document itself), and the pack
   executes exactly its planned job ids. No re-inference. If ci-plan could not
   publish a plan (fallback), the pack self-plans exactly as pre-2026-08-14.
   Pip's download cache is shared via `actions/cache`; environments are not.
3. **ci-gate** — the ONE stable check name. Adjudicates plan+packs, publishes
   an affirmative success even on a proven-no-work PR (#4779), and emits
   exactly one machine-readable `CI_CLASS=` line
   (`structural-preflight | planner-infra | pack-failure | superseded |
   no-work | pass`) plus a step-summary verdict table. Packs list their failed
   legacy jobs in `CI_PACK_FAILED_JOBS=` and their step summary.

Main has no `push` CI; its proof is a full-suite `workflow_dispatch` baseline
(all 188 jobs, 12 packs). Kill switches: repo variables `CI_SCOPE_MODE=off`,
`CI_DYNAMIC_MATRIX_MODE=off`.

## The merge controller (`.github/workflows/merge-on-green.yml`)

A label-driven reconciler on the reserved `merge-control` runner, running
`scripts/merge_on_green.py`. Sessions arm a PR with `merge-on-green` and stop
(CLAUDE.md §CI handoff is terminal).

- **Wakes**: `workflow_run` completions of ci/fences/integration-baseline.
  `skipped` conclusions and fences-on-main ticks do not schedule/coalesce away
  the useful wake; success → full sweep; failure → bounded mark-only pass
  (read-after-write verified marker); cron every 10 min as recovery net.
- **Merge law**: squash-merge only on CONCLUDED green (affirmative `ci-gate`;
  spurious "Workers Builds: macro" excluded), never mid-flight, never red,
  never conflicting, never empty. Genuine red → `merge-blocked` + one comment.
- **Staleness** (`stale_for`): a clean head re-proves ONLY when a main commit
  since its proof (a) changed check definitions, or (b) touched a path inside
  the PR's OWN tested surface. `[skip ci]` ticks, data/site bakes, and unowned
  files never stale anyone. Refreshes are capped per sweep and by live CI
  capacity (#5580); update-branch is serialized through a durable lease.
- **Inherited reds**: a red also red on main's own proof defers to the
  base-inherited machinery rather than blaming the PR; a too-stale main proof
  triggers a self-dispatched baseline (rate-floored, never over a live one).

## Native GitHub Merge Queue — evaluated 2026-08-14, rejected with receipts

Available on the current org/Enterprise config (proven live: ruleset
20833101 + probe PR #5581 merged by the queue in 31s), but rejected for
`main`: one direct push to the target branch destroys and rebuilds every
in-flight merge group (live receipt in the recovery doc §3), and main takes
~323 direct producer pushes/day; also `github-actions` cannot be a ruleset
bypass actor (422), so ~35 `GITHUB_TOKEN` producer lanes cannot be exempted.
Re-open the question only if producers stop pushing directly to main.

## Where things are

| concern | file |
|---|---|
| job manifest (188 logical jobs) | `.github/ci/legacy-jobs.yml` |
| planner/selector/executor | `scripts/run_ci_pack.py` |
| AST scope inference | `scripts/ci_scope_dependencies.py` |
| PR diff from API | `scripts/ci_plan_changed_files.py` |
| merge controller | `scripts/merge_on_green.py` |
| unwired-suite ratchet | `scripts/audit_unrun_tests.py` (+ baseline/waivers in `config/`) |
| pipeline contract tests | `tests/test_ci_plan_workflow.py`, `tests/test_ci_pack.py` |
| controller tests | `tests/test_merge_on_green.py` |
| worker handoff contract | `scripts/ci_handoff.py` (CLAUDE.md §CI handoff is terminal) |
