# GitHub CI Cost + Flow Migration — Wave 1 (self-hosted trusted CI)

Operator charter 2026-08-12 ("Mastermind GitHub CI Cost + Flow Migration — Executive
Execution Charter"): routine trusted CI must consume self-hosted compute by default;
GitHub-hosted compute becomes a documented exception. This supersedes the 2026-08-09
reasoning that returned the CI packs to hosted runners after Enterprise concurrency
became abundant (ci.yml history comment at the `ci-pack.runs-on` key). The security
property that motivated hosted PR CI — untrusted code never reaches persistent home
runners — is preserved by trust ROUTING, not by paying for hosted compute.

## §0 Acceptance gates (not done unless)

1. A same-repo PR's `ci-pack-N` jobs and fences `fence-pack` execute on
   `pc-render-*` (verified in job metadata via the runner name), not
   `ubuntu-latest`. This PR's own run is the proof. (`ci-plan`/`ci-gate` stay
   hosted in Wave 1 — see §2.)
2. Check names unchanged: `ci-plan`, `ci-pack-N`, `ci-gate`, `fence-pack`,
   `self-mod-fence` / `capability-broker` / `grader-manifest` (published contexts),
   `integration-baseline`. merge-on-green continues to adjudicate without edits.
3. Fork-PR routing: a `pull_request` head from a different repo full_name resolves
   every one of those jobs to `ubuntu-latest` (static inspection + tests; the repo
   additionally holds `approval_policy: all_external_contributors`, verified live
   2026-08-12).
4. Concurrency semantics untouched: PR groups keep `cancel-in-progress: true`; the
   `workflow_dispatch` (main-baseline) group keeps `false`; the merged-close fence
   stays. fences keeps PR-only cancel. integration-baseline keeps `false`.
5. Old hosted-pinning policy tests rewritten to pin the NEW property (trusted →
   self-hosted, fork → hosted, no untrusted head on self-hosted); no safety test
   deleted to get green.
6. `scripts/check_runner_policy.py` + `.github/runner-policy.yml` +
   `tests/test_runner_policy.py` land, wired into integration-baseline and a legacy
   job, and every currently-hosted job that is not migrated in this PR is registered
   as `pending-migration` debt (the Wave-2 worklist).
7. Workspace hygiene preserved: the sparse-clear guard runs on every job that can
   land on a self-hosted runner (ci-pack keeps it; fence-pack gains it; ci-plan
   stays hosted-only in Wave 1 so it needs none — §2, and §7.4 records this
   supersession);
   `run_ci_pack.py` between-job cleanup unchanged.
8. Capacity partition explicit: `ci-pack` gets `strategy.max-parallel: 2` with the
   one-physical-host measurement recorded in the comment.

## §1 Measured ground truth (2026-08-12)

- Fleet: 10 repo-level runners, all online. Six macOS ARM64 (mac-builder-1/2:
  macstudio+codex+theta-m1; 3: macstudio-light; light: render-heavy; 4: parked+
  merge-control; 5: macstudio+parked). Four Linux X64 `render-linux`: pc-render-1..4.
- **pc-render-1..4 are ONE physical machine** (canary run 31595700406: hostname
  `winpc`, machine_id `da9bccd5`, `runner_listeners_on_host=4`, runner dirs
  `/home/longr/actions-runner-{1..4}`): 24 cores, 31 GiB RAM, ~893 GB free on /,
  load ~0.02 (idle), up 25 days. Python 3.12.3 system; tool cache already carries
  Python + node from setup-* actions (integration-baseline/render lanes); docker
  ABSENT.
- ci.yml: `pull_request` (fail-closed paths catch-all) + bare `workflow_dispatch`;
  jobs ci-plan → ci-pack (12-way plan-driven matrix, no max-parallel) → ci-gate; all
  three `runs-on: ubuntu-latest`. Sparse-clear hygiene step already present in
  ci-pack, guarded `if: runner.environment != 'github-hosted'`.
- fences.yml: `fence-pack` (ubuntu-latest) fires on every PR AND every main push
  (~30-90 s apart in storms; concluded-run coalescing via event-conditional
  cancel-in-progress). Fork fallbacks `fork-self-mod-fence` / `fork-capability-broker`
  / `fork-grader-manifest` already exist with dynamic names preserving the three
  published check contexts.
- integration-baseline.yml: ALREADY self-hosted on main
  (`runs-on: ${{ github.ref == 'refs/heads/main' && fromJSON('["self-hosted","render-linux"]') || 'ubuntu-latest' }}`),
  30-min timeout for the ~60k-path checkout; off-main dispatch deliberately hosted.
- merge-on-green.yml: already `[self-hosted, macOS, ARM64, merge-control]`
  (mac-builder-4). CLAUDE.md:18 and AGENTS.md:248 still say "GitHub-hosted
  ubuntu-latest" — stale, fixed in this PR.
- Repo visibility: **`private: false` (PUBLIC)** while the charter says "Keep
  Mastermind private" — surfaced to the operator; not changed by this PR (visibility
  is an operator action with Pages/product implications). Fork-PR workflow approval
  policy is `all_external_contributors`; default workflow token is read-only.
- Volume at peak (measured 09:14-12:13Z window): ~20 ci.yml runs/hr AND ~20
  fences runs/hr. Census (2026-08-12): 122 jobs across 82 workflows — 50 hosted
  (all ubuntu-latest), 67 self-hosted (47 macstudio / 17 macstudio-light / codex /
  theta-m1 / merge-control), 4 dynamic, 1 reusable-call; zero pull_request_target;
  zero container/services. Hosted tail beyond ci+fences = scheduled lanes
  (marketing-press-wire */5 ≈288/day, live-quotes */5 wkdy, vps-live-heartbeat
  */10, prophet-live + marketing-hot-tape market-hours 5-min, ci-main-heartbeat
  11 jobs ×4/day, earnings-* hourly, etc.) — the Wave-2 registry worklist.
- **Billing truth (org billing API, month-to-date 2026-08)**: Actions Linux =
  267,066 min gross $1,602.40, discount −$1,602.95, **net $0.00** (repo=macro) —
  the metered "spend" is fully discounted because the repo is PUBLIC. Net org
  spend ≈ $2.03 (Enterprise seat). The furnace is real capacity-wise (~22k hosted
  min/day) but bills $0 TODAY; it becomes real dollars the moment the repo goes
  private, which is the operator's stated intent ("Keep Mastermind private").
  This migration is the prerequisite for flipping visibility without igniting
  ~$130+/day of real spend.

## §2 Routing design

`ci-pack` (the mass — ~97% of ci.yml minutes) gets the trusted-routing expression:

    runs-on: ${{ (github.event_name == 'pull_request' && github.event.pull_request.head.repo.full_name != github.repository) && 'ubuntu-latest' || inputs.runner_pool == 'hosted' && 'ubuntu-latest' || fromJSON('["self-hosted","Linux","X64","render-linux"]') }}

- Same-repo PR, workflow_dispatch, any future trusted event → self-hosted Linux pool.
- Fork PR → ubuntu-latest (GITHUB-HOSTED EXCEPTION: untrusted external head must
  never execute on the persistent home fleet).
- `workflow_dispatch` gains `inputs.runner_pool` (choice: selfhosted|hosted, default
  selfhosted) — the operator recovery lever when the self-hosted fleet is down
  (GITHUB-HOSTED EXCEPTION: fleet-down recovery). `inputs.*` is empty on
  non-dispatch events, so the middle clause is inert on PRs/pushes.
- **ci-plan and ci-gate STAY `ubuntu-latest` in Wave 1** (registered exception,
  class `cheap-orchestration`): together ~2-3% of ci.yml minutes (plan ~4-5 min,
  gate <1 min), they are the SERIAL head/tail of every run (hosted pickup is 2-3 s
  vs pool queue-wait added twice to every PR), and at the measured ~20 ci runs/hr
  fleet churn the plan jobs alone would consume ~1.7 of the pool's 4 slots.
  Keeping them hosted preserves pool capacity for packs. Wave 2 (more runner slots
  on the 24-core host + dedicated ci labels) revisits. ci-plan's "hosted-only, no
  sparse-clear needed" comment therefore stays TRUE.
- fences `fence-pack` is already same-repo-gated by its `if:`, so it takes the
  static label array; the three fork-* fallbacks stay `ubuntu-latest` (exception:
  untrusted fork boundary). fence-pack gains the sparse-clear step and
  `timeout-minutes: 30` sized for a cold first checkout (integration-baseline
  precedent: >12 min for the ~60k-path index update).
- ci-pack `strategy.max-parallel: 2` (charter §6 one-physical-PC posture: 2 CI /
  1 render / 1 control-burst on the measured single 24-core host). The old "do not
  reintroduce without a shared-pool reason" comment is satisfied: the shared pool
  is back, and this time the sweeper is NOT co-resident (merge-control moved).
- Security invariant (public repo!): YAML same-repo routing + job-level `if:` guards
  + `approval_policy: all_external_contributors` + read-only default token. A fork
  PR that edits workflow YAML still cannot run anything without a maintainer
  approving the run first. check_runner_policy.py enforces the YAML half forever.

## §3 Policy guard (regression prevention, charter §12)

- `.github/runner-policy.yml`: `default: self-hosted`, `hosted_labels` list,
  `hosted_exceptions` entries `{workflow, job, reason, class}` with class ∈
  `fork-fallback | recovery | pending-migration | platform` (class is reporting
  metadata; any listed entry passes the gate).
- `scripts/check_runner_policy.py`: parses every workflow; resolves each job's
  `runs-on` (string / list / matrix / expression); any job that can resolve to a
  hosted label without a registry entry → `::error` + exit 1. Additional fail-closed
  invariants: any job that can resolve to self-hosted in a `pull_request`-triggered
  workflow must carry a same-repo guard (in `runs-on` expression or job `if:`);
  `pull_request_target` is forbidden outright. `--selftest` with synthetic fixtures
  (house guard idiom); annotations via bare `print("::error ...", flush=True)`.
- `tests/test_runner_policy.py`: fixture-driven behavior pins + live-tree assertion
  + explicit pins of the §2 routing properties (trusted→self-hosted, fork→hosted,
  fence fork fallbacks hosted, merge-on-green on merge-control).
- Registered per the house recipe (census 2026-08-12): (a) `run:` step in
  `.github/ci/legacy-jobs.yml` job `workflow-yaml` (~line 1704 — the job that already
  runs test_ci_pack/test_merge_on_green at line 1752; `if: ${{ false }}` there is the
  manifest's DISABLED_IF marker, required, not dead code); (b) explicit ci.yml
  `paths:` entries for the three new files (both-halves #3488 idiom — the explicit
  entry keeps the job reachable for scope inference, not just workflow start);
  (c) a step in integration-baseline.yml for post-merge main coverage.
  `audit_unrun_tests.py` (hard gate) is satisfied by (a); `check_ci_trigger_closure.py`
  by (b).

## §3b Exact old-policy test rewrites (census 2026-08-12, both in tests/test_ci_pack.py)

1. `test_ci_pack_uses_twelve_balanced_hosted_jobs` (def ~1176): asserts at 1218
   (`runs-on == "ubuntu-latest"`), 1221-1223 (bans substrings self-hosted /
   render-linux / macstudio), 1229 (bans `max-parallel`). REWRITE to pin the new
   property: exact routing expression string on ci-pack AND ci-plan AND ci-gate
   (ci-plan/ci-gate runs-on were previously unpinned — pin them now), fork branch →
   'ubuntu-latest', trusted branch → fromJSON self-hosted list, `max-parallel == 2`
   REQUIRED with the one-host measurement in the assert message, and
   `workflow_dispatch.inputs.runner_pool` present with default `selfhosted`. Rename
   the function so "hosted" no longer mislabels it.
2. `test_same_repo_fences_share_one_runner_and_keep_required_contexts` (~1332):
   assert 1343 fence-pack == "ubuntu-latest" → exact list
   ["self-hosted","Linux","X64","render-linux"]; the fork-fallback asserts at 1371
   (fork-* == "ubuntu-latest") STAY.
- `scripts/merge_on_green.py` needs ZERO changes (names-only adjudication;
  MAIN_PROOF_WORKFLOWS/anchors unaffected). `run_ci_pack.py:565`'s
  `runs-on == ubuntu-latest` check governs manifest-internal boilerplate in
  legacy-jobs.yml entries — unaffected, do not touch the manifest entries.
- `test_no_bare_self_hosted_job_can_steal_the_merge_control_runner`
  (tests/test_merge_on_green.py:151) passes unchanged: our label set is not a subset
  of the merge-control set, and the ci.yml expression is an opaque string to it.
- `check_workflow_yaml.py` imposes no constraint on dynamic runs-on / max-parallel.

## §4 What stays hosted (initial exception registry)

- ci.yml ci-plan/ci-pack/ci-gate fork-PR branch of the routing expression
  (fork-fallback) + runner_pool=hosted dispatch value (recovery).
- fences fork-self-mod-fence / fork-capability-broker / fork-grader-manifest
  (fork-fallback).
- integration-baseline off-main dispatch branch (recovery/hygiene: an off-main ref
  must not execute in the production-adjacent persistent workspace).
- Every other currently-hosted job: `pending-migration` (Wave 2 worklist), enumerated
  from the census. Wave 2 = migrate or justify each; Wave 2 also owns the dedicated
  `ci-linux` label separation so CI stops sharing the `render-linux` label
  (charter §6 — label change deferred: host-side re-registration is an outage risk
  not needed for Wave 1 capacity, which max-parallel provides).

## §5 Observability (charter §13)

`scripts/runner_usage_receipt.py` — quota-bounded gh sampler: last-N-days runs per
workflow, hosted vs self-hosted job counts (runner_name prefix), duration sums,
queue-wait quantiles; emits a small Markdown+JSON receipt. Operator-run (no schedule
in Wave 1). Before/after §15 numbers come from it.

## §6 Explicitly out of scope for this PR

- Flipping CI_SCOPE_MODE / CI_DYNAMIC_MATRIX_MODE to `active` (Wave-B shadow → active
  is its own evidence-gated step; shadow-vs-actual comparison is the prerequisite).
- Wave-C scope narrowing (the 3-8 min fast gate; pack-0 indivisibility).
- Runner re-labeling (`ci-linux`), macstudio lane changes, render.yml/engine-render.yml,
  merge-on-green.yml behavior, product code.
- Repo visibility change (operator decision; flagged).

## §7 Implementation receipts (2026-08-12)

### §7.0 Deviations from the build spec — READ FIRST

1. **ADDED, not in the brief: `config/house_law_checks.yml` entry
   `ops.runner_routing_policy` + regenerated `docs/HOUSE_LAW_CI_GUARD_SUITE.md`.**
   The meta-guard `scripts/check_house_law_registry.py` (law `meta.house_law_registry`,
   wired in `ci.yml/house-law-registry`) CENSUSES `scripts/check_*.py` and hard-fails
   any unregistered one, and a second step re-emits the docs and `git diff
   --exit-code`s them. Landing `scripts/check_runner_policy.py` without both edits
   would have shipped a guaranteed red. `ci_wiring` names `ci.yml/workflow-yaml`
   (the meta-guard's wiring pass is textual over that job's `run:` bodies, which
   the new step satisfies); the integration-baseline copy is recorded in `notes`
   because the registry's `lane` vocabulary in use is hook/pr_ci/publish/render/
   scheduled and none of them honestly describes a main-push circuit breaker.
2. **`ci.yml/ci-pack` carries TWO registry entries, not one** — `fork-fallback` and
   `recovery` — because one `runs-on` expression contains two independent hosted
   branches with different justifications and different lifetimes (the fork branch
   is permanent and a security property; the recovery branch is an operator lever).
   Collapsing them into one entry would have made the Wave-2 worklist read as if
   removing the recovery lever also removed the fork boundary.
3. **`.github/ci/legacy-jobs.yml` step name left as "hosted-runner packing
   contract"** even though "hosted-runner" is now stale. The brief scoped manifest
   edits to the pytest line plus one new step; renaming was not requested and every
   manifest edit rebalances pack weights. Flagged for Wave 2, not fixed here.
4. **`scripts/audit_unrun_tests.py` exits 1 on this tree for a PRE-EXISTING
   reason** — see §7.3. `tests/test_runner_policy.py` is NOT the offender.

### §7.1 Files created

| File | Lines | What / why |
|---|---:|---|
| `.github/runner-policy.yml` | 340 | The exception registry. `default: self-hosted`, `hosted_labels`, and 53 `{workflow, job, class, reason}` entries: 4 fork-fallback, 4 recovery, 2 cheap-orchestration, 43 pending-migration (the Wave-2 worklist). |
| `scripts/check_runner_policy.py` | 554 | The guard. R1 unregistered-hosted (opaque counts as hosted — fail closed), R2 self-hosted in a `pull_request` workflow without a same-repo guard, R3 `pull_request_target` forbidden with no override, R4 stale entry = warning. `--selftest` builds synthetic fixtures; `--registry` / `--workflows-dir` overrides exist for the test suite. Annotations are bare line-start `print(..., flush=True)`. |
| `tests/test_runner_policy.py` | 273 | 14 tests: selftest passes, live tree passes, four fixture negatives (each a one-property mutation of a passing tree, plus the positive control that registering the same job flips it green), and the routing pins — exact `ci-pack` expression, `fence-pack` self-hosted, fork-* hosted, merge-on-green on merge-control, no `pull_request_target` anywhere, registry shape. |
| `.github/workflows/runner-canary.yml` | 68 | `workflow_dispatch`-only read-only pool probe (4-way matrix, `sleep 20` to force distinct runner slots). No checkout, no secrets. This is the instrument that produced the one-physical-host finding. |
| `scripts/runner_usage_receipt.py` | 416 | Operator observability, NOT wired into CI. Hard 25-call REST budget (counted, `gh run list --limit N` charged at ceil(N/100)), never `--paginate`, preflight `rate_limit` printed in the receipt. Emits Markdown + JSON: runs/workflow in window, static placement from the local tree, empirical `runner_name` sampling for ci.yml/fences.yml only, and the `pending-migration` list. Honest-limits section is part of the output. |

### §7.2 Files edited

| File | Edit |
|---|---|
| `.github/workflows/ci.yml` | (a) `workflow_dispatch.inputs.runner_pool` choice selfhosted\|hosted, default selfhosted; (b) `ci-pack.runs-on` → the trust-routing expression, with the history comment rewritten to keep BOTH 2026-08-09 acts as prior acts and append the 2026-08-12 reversal (cost/visibility, fork boundary, recovery lever); (c) `strategy.max-parallel: 2` + the "NO max-parallel" comment rewritten around the canary measurement, Wave-B dynamic-matrix half kept intact; (d) one `GITHUB-HOSTED EXCEPTION (cheap-orchestration)` line above `ci-plan` and `ci-gate` (both stay `ubuntu-latest`; ci-plan's "hosted-only, no sparse-clear" comment stays, still true); (e) three `paths:` entries for the new guard/registry/suite. No job id or name changed; no `concurrency:` line touched. |
| `.github/workflows/fences.yml` | `fence-pack` → `[self-hosted, Linux, X64, render-linux]`, `timeout-minutes: 30`, and the ci-pack sparse-clear step copied VERBATIM as the FIRST step (`if: runner.environment != 'github-hosted'`, rc=5 handling intact). Comment records that the job's existing same-repo `if:` IS the security boundary. One `GITHUB-HOSTED EXCEPTION` line above each of the three `fork-*` jobs. |
| `tests/test_ci_pack.py` | Module constant `CI_PACK_RUNS_ON`. `test_ci_pack_uses_twelve_balanced_hosted_jobs` → `test_ci_pack_routes_trusted_runs_to_selfhosted_and_forks_to_hosted`: every non-runner assert kept (job-set subset, matrix wiring, `--pack-count 12`, closed-event fence, paths); the hosted pin and the self-hosted/render-linux substring bans replaced by the exact expression + semantic-substring pins, `max-parallel == 2`, `runner_pool` options/default, and ci-plan/ci-gate hosted. The `macstudio` ban is KEPT. `test_same_repo_fences_share_one_runner_and_keep_required_contexts`: fence-pack runs-on → exact list, plus `timeout-minutes == 30`, same-repo `if:` substring, and first-step-is-the-sparse-clear; the fork-fallback `ubuntu-latest` asserts stay. |
| `.github/ci/legacy-jobs.yml` | `workflow-yaml` job ONLY: pytest step extended with `tests/test_runner_policy.py`; one new step `runner-policy selftest + live gate`. No new job (narrow-diff ceiling), no other manifest content touched. |
| `.github/workflows/integration-baseline.yml` | Step renamed "hosted-runner packing and merge-train contracts" → "CI packing and merge-train contracts" (step names are not check names); two steps added: the guard selftest+live gate and `tests/test_runner_policy.py`. |
| `AGENTS.md` | Stale merge-on-green runner line fixed (`[self-hosted, macOS, ARM64, merge-control]` / mac-builder-4, not GitHub-hosted ubuntu-latest); new `## Runner routing policy (operator charter 2026-08-12)` section placed between §CI handoff is terminal and §Definition of done. |
| `CLAUDE.md` | Same stale parenthetical fixed in the §Shared workspace merge-on-green passage; one new §House laws bullet stating the policy, the guard, and the recovery lever. |
| `config/house_law_checks.yml` + `docs/HOUSE_LAW_CI_GUARD_SUITE.md` | New `ops.runner_routing_policy` entry (see §7.0 item 1) and the byte-exact docs regeneration the meta-guard's docs-drift step requires. |

### §7.3 Validation (run from the worktree root, 2026-08-12)

| # | Command | Result |
|---|---|---|
| 1 | `pytest tests/test_ci_pack.py tests/test_merge_on_green.py tests/test_ci_plan_workflow.py tests/test_runner_policy.py -q` | `381 passed in 492.47s (0:08:12)` |
| 2 | `check_workflow_yaml.py --selftest` / `… .github/workflows` | `SELFTEST OK: 4 cases.` / `OK: 83 workflow file(s) parse with on: + jobs: blocks.` (83 = 82 + runner-canary.yml) |
| 3 | `check_runner_policy.py --selftest && check_runner_policy.py` | `SELFTEST OK: 8 cases` / `122 job(s) across 83 workflow file(s): 51 hosted-resolvable, 73 self-hosted-resolvable, 1 opaque; 53 registered exception(s). OK` — exit 0 |
| 4 | `run_ci_pack.py --pack-count 12 --validate-only` | `Validated 184 legacy jobs; 184 in scope; pack weights=[481, 321, 321, 320, 323, 321, 321, 322, 322, 321, 321, 320]` — exit 0 |
| 5a | `audit_unrun_tests.py` | **exit 1 — PRE-EXISTING, not this PR.** Sole offender `tests/test_odometer_light_mode_surface.py`, added by #5458 (`908436bb156`, already on main) and named by no `run:` step anywhere in `HEAD`. `tests/test_runner_policy.py` does NOT appear in the unrun list. |
| 5b | `check_ci_trigger_closure.py` | `1383 suites; TRIGGER GAP 0` — exit 0 |
| 6 | `pytest tests/test_gh_annotation_line_start.py -q` | `4 passed` — the new guard satisfies the line-start law |
| + | `check_house_law_registry.py --selftest` / live / `--emit-docs` | `selftest OK` / `73 laws, 60 enforced in CI` / docs regen idempotent |
| + | `check_skip_only_suites.py` | `120 skip gates; SKIP-ONLY 0` — exit 0 |
| + | `pytest tests/test_workflow_file_size.py tests/test_push_retry.py tests/test_close_pass_lane.py tests/test_render_run_size_cap.py -q` | `161 passed` — the workflow-enumerating suites accept the new `runner-canary.yml` |
| + | `check_dag_conformance.py` | `DAG conformance OK — 26 lane(s), 2 suspect drift(s)` (both pre-existing W5a inheritances) |

### §7.4 Acceptance gates §0 status

- **G1 (packs execute on `pc-render-*`)** — cannot be proven from the tree; it is
  proven by THIS PR's own ci.yml run. Static half is pinned by
  `tests/test_ci_pack.py` and `tests/test_runner_policy.py`.
- **G2 (check names unchanged)** — no job `id` or `name:` key was touched in any
  workflow. `ci-plan`, `ci-pack-${{ matrix.pack }}`, `ci-gate`, `fence-pack`, the
  three dynamic fork names, and `integration-baseline` are byte-identical.
- **G3 (fork routing)** — pinned three ways: exact expression compare, the
  `head.repo.full_name != github.repository` substring assert, and
  `check_runner_policy.py` R2 (which reds if the guard is ever removed).
- **G4 (concurrency untouched)** — no `concurrency:`, `group:` or
  `cancel-in-progress:` line was edited in any file.
- **G5 (old policy tests rewritten, none deleted)** — both functions rewritten in
  place; the `macstudio` ban survives; the pool-starvation asserts were replaced
  by strictly stronger untrusted-head asserts.
- **G6 (guard + registry + suite land and are wired)** — done, plus the house-law
  registry entry the brief did not anticipate (§7.0 item 1). All 43 unmigrated
  hosted jobs are registered `pending-migration`.
- **G7 (sparse-clear hygiene)** — `fence-pack` gains it; `ci-pack` keeps it.
  **NOT DONE: `ci-plan` did not gain it** — §0.7 says "ci-plan gains it", but §2
  keeps ci-plan hosted-only in Wave 1, and the build brief explicitly specified
  ci-plan unchanged except for the exception comment. A sparse-clear on a job that
  can only ever run on a fresh hosted VM is the cargo cult its own comment warns
  against. It becomes REQUIRED the moment ci-plan migrates (Wave 2); flagged.
- **G8 (capacity partition explicit)** — `max-parallel: 2` with the canary
  measurement in the comment and in the test's assert message.
