from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
MANIFEST = ROOT / ".github" / "ci" / "legacy-jobs.yml"
FENCES = ROOT / ".github" / "workflows" / "fences.yml"

SPEC = importlib.util.spec_from_file_location(
    "run_ci_pack", ROOT / "scripts" / "run_ci_pack.py"
)
assert SPEC and SPEC.loader
PACK = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PACK
SPEC.loader.exec_module(PACK)


def _yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def test_all_legacy_jobs_are_disabled_and_packable() -> None:
    jobs = PACK.load_legacy_jobs(MANIFEST)
    assert len(jobs) >= 86
    assert all(job.definition["if"] == PACK.DISABLED_IF for job in jobs)


def test_two_packs_are_complete_disjoint_and_balanced() -> None:
    jobs = PACK.load_legacy_jobs(MANIFEST)
    packs = PACK.partition_jobs(jobs, 2)
    flattened = [job.job_id for pack in packs for job in pack]
    assert sorted(flattened) == sorted(job.job_id for job in jobs)
    assert len(flattened) == len(set(flattened))

    weights = [sum(job.weight for job in pack) for pack in packs]
    assert max(weights) - min(weights) <= max(job.weight for job in jobs)


def test_legacy_expressions_are_supported() -> None:
    for job in PACK.load_legacy_jobs(MANIFEST):
        for step in job.definition["steps"]:
            if "run" not in step:
                continue
            rendered = PACK.render_command(
                str(step["run"]), base_ref="main", head_ref="claude/example"
            )
            assert "${{" not in rendered


def test_unknown_job_semantics_fail_closed(tmp_path: Path) -> None:
    workflow = tmp_path / "ci.yml"
    workflow.write_text(
        """
jobs:
  ci-pack:
    runs-on: ubuntu-latest
    steps:
      - run: echo pack
  unsafe:
    if: ${{ false }}
    runs-on: ubuntu-latest
    services:
      db:
        image: postgres
    steps:
      - run: echo unsafe
"""
    )
    with pytest.raises(PACK.ManifestError, match="unsupported keys: services"):
        PACK.load_legacy_jobs(workflow)


def test_execute_refuses_to_clean_a_developer_checkout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("GITHUB_WORKSPACE", raising=False)
    with pytest.raises(RuntimeError, match="only inside GitHub Actions"):
        PACK._workspace_root()


def test_execution_restores_workspace_between_legacy_jobs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "checkout"
    repo.mkdir()
    workflow = repo / "ci.yml"
    workflow.write_text(
        """
jobs:
  ci-pack:
    runs-on: ubuntu-latest
    steps:
      - run: echo pack
  first:
    if: ${{ false }}
    runs-on: ubuntu-latest
    steps:
      - run: printf leak > leaked.tmp
  second:
    if: ${{ false }}
    runs-on: ubuntu-latest
    steps:
      - run: test ! -e leaked.tmp
"""
    )
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "ci-pack@example.invalid"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "CI Pack Test"], cwd=repo, check=True
    )
    subprocess.run(["git", "add", "ci.yml"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-m", "fixture"], cwd=repo, check=True, capture_output=True
    )

    monkeypatch.chdir(repo)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_WORKSPACE", str(repo))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path / "runner-temp"))
    jobs = PACK.load_legacy_jobs(workflow)
    assert PACK.execute_pack(jobs) == 0
    assert not (repo / "leaked.tmp").exists()


def test_workflows_cancel_superseded_pr_runs() -> None:
    ci = _yaml(WORKFLOW)
    fences = _yaml(FENCES)
    for workflow in (ci, fences):
        assert workflow["concurrency"]["cancel-in-progress"] is True
    assert "pull_request.number" in ci["concurrency"]["group"]
    assert "github.ref" in ci["concurrency"]["group"]
    assert "pull_request.number" in fences["concurrency"]["group"]


def test_ci_pack_is_a_few_hosted_jobs_not_eighty_six() -> None:
    workflow = _yaml(WORKFLOW)
    assert set(workflow["jobs"]) == {"ci-pack"}
    pack = workflow["jobs"]["ci-pack"]
    # The pack COUNT tunes (2 -> 4 on 2026-07-28 to halve time-to-green); the
    # SHAPE is the contract: a small ordered matrix of balanced packs on hosted
    # runners, never one job per legacy suite (86 VMs), and the matrix must
    # agree with the --pack-count handed to the runner or some packs' jobs
    # would execute nowhere.
    matrix = pack["strategy"]["matrix"]["pack"]
    assert matrix == list(range(len(matrix)))
    assert 2 <= len(matrix) <= 8
    # Pull requests stay on the hosted pool; main's proof runs on the idle self-hosted
    # Linux pool. Asserted as a CONTRACT on both branches rather than as a literal,
    # because the point of the expression is that the two events route differently —
    # pinning the string would have forbidden the routing outright.
    #
    # Why main routes away from `ubuntu-latest` (2026-08-09): main's ci.yml proof sat
    # `queued` 30+ minutes behind 133 queued runs while `render-linux` idled, and that
    # one starved run blocks the whole fleet — `merge_on_green.main_proof` answers "is
    # main green on ci-pack-N" from the newest CONCLUDED ci.yml run on main, so with no
    # fresh proof the base-inherited-red refresh cannot fire and every pull request that
    # inherited a since-healed red stays blocked.
    runs_on = " ".join(str(pack["runs-on"]).split())
    assert "github.event_name == 'pull_request'" in runs_on
    assert "'ubuntu-latest'" in runs_on
    assert '["self-hosted","render-linux"]' in runs_on
    # The macstudio pool is the render/nightly lane and must never absorb CI packs.
    assert "macstudio" not in runs_on
    assert pack["strategy"]["fail-fast"] is False
    assert pack["if"] == "github.event.action != 'closed'"
    run_text = "\n".join(
        str(step.get("run", "")) for step in pack["steps"] if isinstance(step, dict)
    )
    assert "--workflow .github/ci/legacy-jobs.yml" in run_text
    assert f"--pack-count {len(matrix)}" in run_text

    # A manifest edit must trigger CI even though GitHub does not interpret the
    # manifest itself as a workflow.
    triggers = workflow.get("on") or workflow.get(True)
    assert ".github/ci/legacy-jobs.yml" in triggers["pull_request"]["paths"]
    assert "closed" in triggers["pull_request"]["types"]


def test_company_intelligence_product_surfaces_reach_focused_ci_packs() -> None:
    """Both public product faces must trigger CI and run their focused suites."""
    workflow = _yaml(WORKFLOW)
    triggers = workflow.get("on") or workflow.get(True)
    paths = set(triggers["pull_request"]["paths"])
    required_paths = {
        "app/company_intelligence.py",
        "app/earnings.py",
        "tests/test_company_intelligence_api.py",
        "site/assets/js/company-intelligence-dossier.js",
        "templates/ticker.html.j2",
        "engine/earnings_narrative/public_wire.py",
        "engine/earnings_narrative/context_packets.py",
        "engine/earnings_narrative/private_publication.py",
        "engine/neuralweb/earnings_context_reader.py",
        "engine/prophet_bridge.py",
        "scripts/build_earnings_public_wire.py",
        "scripts/publish_earnings_private_store.py",
        "templates/earnings_wire/**",
        "tests/test_earnings_public_wire.py",
        "tests/test_earnings_api.py",
        "tests/test_earnings_private_store.py",
        "tests/test_prophet_bridge.py",
        "tests/test_earnings_worker_launchd.py",
        "tests/test_earnings_worker_terminal.py",
        "ops/bootstrap_earnings_worker.sh",
        "ops/launchd/com.mastermind.earnings-worker.plist",
        "ops/launchd/run_earnings_worker.sh",
        "tests/test_ticker_dossier_render_lane.py",
    }
    assert required_paths <= paths

    manifest = _yaml(MANIFEST)

    def job_commands(job_id: str) -> str:
        return "\n".join(
            str(step.get("run", ""))
            for step in manifest["jobs"][job_id]["steps"]
            if isinstance(step, dict)
        )

    assert "tests/test_company_intelligence_api.py" in job_commands(
        "prelaunch-hardening"
    )
    publish_ops = job_commands("unrun-publish-ops")
    publish_ops_install = next(
        step["run"]
        for step in manifest["jobs"]["unrun-publish-ops"]["steps"]
        if step.get("name") == "install minimal deps"
    )
    assert "tests/test_earnings_public_wire.py" in publish_ops
    assert "tests/test_earnings_api.py" in publish_ops
    assert "tests/test_earnings_private_store.py" in publish_ops
    assert "tests/test_earnings_worker_launchd.py" in publish_ops
    assert "tests/test_earnings_worker_terminal.py" in publish_ops
    assert "tests/test_ticker_dossier_render_lane.py" in publish_ops
    assert "tests/test_ticker_pages.py" in publish_ops
    assert re.search(r"\bfastapi\b", publish_ops_install)
    assert re.search(r"\bhttpx\b", publish_ops_install)


def test_ci_pack_partial_clone_keeps_history_without_historical_site_blobs() -> None:
    """Full history is load-bearing; full historical blob transfer is not.

    The four #4053 hosted runners spent 6m45s-14m39s in checkout before tests.
    ``filter: blob:none`` preserves the complete current working tree and commit
    graph while omitting historical generated-site blobs from the initial fetch.
    Do not replace this with sparse checkout: legacy suites legitimately inspect
    current ``site/`` files.
    """
    workflow = _yaml(WORKFLOW)
    pack = workflow["jobs"]["ci-pack"]
    checkout = next(
        step
        for step in pack["steps"]
        if str(step.get("uses", "")).startswith("actions/checkout@")
    )
    assert checkout["with"]["filter"] == "blob:none"
    assert checkout["with"]["fetch-depth"] == 0
    assert "sparse-checkout" not in checkout["with"]


def test_same_repo_fences_share_one_runner_and_keep_required_contexts() -> None:
    workflow = _yaml(FENCES)
    assert workflow["permissions"]["checks"] == "write"
    jobs = workflow["jobs"]
    pack = jobs["fence-pack"]
    assert pack["runs-on"] == "ubuntu-latest"
    checkout = next(
        step
        for step in pack["steps"]
        if str(step.get("uses", "")).startswith("actions/checkout@")
    )
    assert checkout["with"]["filter"] == "blob:none"
    assert checkout["with"]["fetch-depth"] == 0

    publish = next(step for step in pack["steps"] if step.get("id") == "publish")
    assert publish["if"] == "always()"
    assert publish["uses"].startswith("actions/github-script@")
    script = publish["with"]["script"]
    for context in ("self-mod-fence", "capability-broker", "grader-manifest"):
        assert f"name: '{context}'" in script
    assert "github.rest.checks.create" in script

    # Fork tokens cannot write check runs. Their compatibility jobs retain the
    # exact contexts only when the PR truly comes from a fork; on the high-volume
    # same-repo path their skipped names are deliberately different, so they
    # cannot satisfy a required fence before fence-pack publishes its verdict.
    for job_id, context in (
        ("fork-self-mod-fence", "self-mod-fence"),
        ("fork-capability-broker", "capability-broker"),
        ("fork-grader-manifest", "grader-manifest"),
    ):
        fallback = jobs[job_id]
        assert "head.repo.full_name != github.repository" in fallback["if"]
        assert context in fallback["name"]
        assert f"fork-{context}-unused" in fallback["name"]

    # The fork self-mod fence also compares against the base branch and needs
    # complete ancestry without downloading obsolete generated-site contents.
    fork_checkout = next(
        step
        for step in jobs["fork-self-mod-fence"]["steps"]
        if str(step.get("uses", "")).startswith("actions/checkout@")
    )
    assert fork_checkout["with"]["filter"] == "blob:none"
    assert fork_checkout["with"]["fetch-depth"] == 0


# ── every tests/*.py a workflow names must exist ─────────────────────────────
#
# `pytest a.py b.py missing.py` does not skip the missing path — it aborts the
# whole invocation with "ERROR: file or directory not found" and runs NOTHING.
# So one deleted test file silently disables every other test in its step.
# ci-main-heartbeat's engine-render-guards step listed
# tests/test_leadership_board.py, deleted with the Mag-7 board in #3359; the job
# had been erroring out ever since, taking 2084 passing tests in the other 73
# files down with it, and main's heartbeat red, until #3555.
#
# This is the [[ci-trigger-must-reach-the-guard]] class one turn worse: there the
# guard could not be triggered, here it is triggered and then never runs. A red
# job is not evidence that the tests under it ran.

_TEST_PATH_RE = re.compile(r'(?<![\w/-])(tests/[A-Za-z0-9_][A-Za-z0-9_./-]*\.py)')


def test_every_workflow_test_path_exists() -> None:
    """No workflow may name a tests/*.py file that is not on disk."""
    missing: list[str] = []
    checked = sorted((ROOT / ".github" / "workflows").glob("*.yml")) + [MANIFEST]
    for workflow_or_manifest in checked:
        text = workflow_or_manifest.read_text(encoding="utf-8")
        for rel in sorted(set(_TEST_PATH_RE.findall(text))):
            if not (ROOT / rel).exists():
                missing.append(f"{workflow_or_manifest.name} -> {rel}")

    assert not missing, (
        "Workflow steps name test files that do not exist:\n  "
        + "\n  ".join(missing)
        + "\n\npytest aborts the ENTIRE invocation on an unresolvable path, so "
        "every other test listed in that step never runs and the job is red for "
        "a reason unrelated to the code. Delete the stale path from the workflow "
        "(or restore the file if the deletion was a mistake)."
    )


# ── the converse: a suite NAMED BY NOTHING never runs ────────────────────────
#
# READ THIS BEFORE "FIXING" AN `if: ${{ false }}` LINE. `.github/ci/legacy-jobs.yml`
# is a MANIFEST, not a set of GitHub jobs. Every one of its ~162 jobs declares
# `if: ${{ false }}`, and that line is REQUIRED BOILERPLATE, not a disable switch:
# scripts/run_ci_pack.py FLAGS AS AN ERROR any manifest job that omits it, so that
# GitHub does not allocate a second, duplicate runner for steps the ci-pack matrix
# already executes. Removing or inverting it fails validation and breaks the pack.
# The manifest's jobs genuinely run — unrun-government-revenue executes in
# ci-pack-1.
#
# The real darkness sits one line away and looks like nothing at all: a suite that
# no `run:` step ANYWHERE names is executed by nothing, whatever any `if:` says.
# This repo has no catch-all `pytest tests/` sweep to pick up the omission, so an
# unnamed suite is silently inert. It passes locally, it is never red, and the lobe
# it guards reads green because its guards are INVISIBLE, not because they hold.
# Nineteen Government Revenue suites sat that way — among them
# test_government_revenue_award_spine.py and test_government_revenue_award_events.py,
# which own the forward award-event spine whose persistence break shipped to
# production on 2026-08-06. A line tracer over the seven suites CI did name
# executed 0 of 147 function bodies across metrics.py, candidates.py,
# opportunities.py, budget_program.py, freshness.py and federation.py (5,279
# lines) — including the fail-closed withholding gate in metrics.py.
#
# test_every_workflow_test_path_exists (above) checks NAMED -> EXISTS. The two
# below check the converse, EXISTS -> NAMED, and then the same question one layer
# down: a contract the ENGINE loads at runtime must be able to start the CI that
# validates against it.
#
# SCOPE — deliberately Government Revenue only. scripts/audit_unrun_tests.py
# measures 963 of 2,015 tests/test_*.py suites unrun repo-wide, so the generalised
# "every suite must be named" assertion would be red on ~48% of the tree the day it
# landed and would be deleted rather than fixed. Widen this per-program, behind a
# program that has actually closed its own darkness.

_GOVERNMENT_REVENUE_SUITE_GLOBS = (
    # also catches tests/test_prophet_government_revenue_context.py
    "tests/test_*government_revenue*.py",
    "tests/test_usaspending*.py",
)

_CLOSURE_SPEC = importlib.util.spec_from_file_location(
    "check_ci_trigger_closure", ROOT / "scripts" / "check_ci_trigger_closure.py"
)
assert _CLOSURE_SPEC and _CLOSURE_SPEC.loader
CLOSURE = importlib.util.module_from_spec(_CLOSURE_SPEC)
sys.modules[_CLOSURE_SPEC.name] = CLOSURE
_CLOSURE_SPEC.loader.exec_module(CLOSURE)


def _executable_run_commands() -> str:
    """Every `run:` body CI can execute: the packed manifest plus real workflows.

    The manifest is the usual home, but a suite wired into a standalone workflow
    genuinely runs too. Scanning both keeps this guard from going red on a correct
    fix — a guard that punishes the right answer gets weakened, not obeyed.
    """
    bodies: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "run" and isinstance(value, str):
                    bodies.append(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for path in [MANIFEST] + sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        walk(yaml.safe_load(path.read_text(encoding="utf-8")))
    return "\n".join(bodies)


def test_every_government_revenue_suite_is_named_by_a_run_step() -> None:
    """A Government Revenue suite no `run:` step names is executed by nothing."""
    on_disk = sorted(
        {
            str(path.relative_to(ROOT))
            for pattern in _GOVERNMENT_REVENUE_SUITE_GLOBS
            for path in ROOT.glob(pattern)
        }
    )
    # Vacuity gate: if the globs stop matching the program, this guard would pass
    # by finding nothing at all. 29 suites exist as of 2026-08-06.
    assert len(on_disk) >= 25, (
        f"only {len(on_disk)} Government Revenue suites matched "
        f"{_GOVERNMENT_REVENUE_SUITE_GLOBS} — the program was renamed or moved and "
        "this guard is now measuring an empty set. Re-point the globs; do not "
        "lower this floor."
    )

    commands = _executable_run_commands()
    unnamed = [rel for rel in on_disk if rel not in commands]

    assert not unnamed, (
        f"{len(unnamed)} Government Revenue suite(s) are named by NO `run:` step in "
        ".github/ci/legacy-jobs.yml or .github/workflows/, so nothing executes "
        "them:\n  " + "\n  ".join(unnamed) + "\n\n"
        "This is NOT the `if: ${{ false }}` line, and 'enabling' a job does not fix "
        "it. That line is required boilerplate on every manifest job — "
        "scripts/run_ci_pack.py errors on any job missing it so GitHub does not "
        "allocate a duplicate runner — and the manifest's steps really are "
        "executed, by the ci-pack matrix in ci.yml. The defect is being UNNAMED: "
        "there is no catch-all `pytest tests/` sweep in this repo, so a suite no "
        "step lists is inert, green-by-absence, and its subject ships unguarded. "
        "Fix by naming the suite in a `run:` step of the owning manifest job "
        "(unrun-government-revenue) AND adding its path to ci.yml's "
        "on.pull_request.paths so an edit to it can start that job."
    )


_RUNTIME_SCHEMA_RE = re.compile(r'"([A-Za-z0-9_.]+\.schema\.json)"')
_WORKSPACE = ROOT / "engine" / "government_revenue" / "workspace.py"


def test_workspace_runtime_contracts_can_start_the_ci_that_validates_them() -> None:
    """A contract the engine loads at runtime must be a trigger for its own CI."""
    names = sorted(set(_RUNTIME_SCHEMA_RE.findall(_WORKSPACE.read_text("utf-8"))))
    assert names, (
        f"{_WORKSPACE.relative_to(ROOT)} no longer names a *.schema.json literal. "
        "Either the runtime loader moved (re-point this guard at its new home) or "
        "the extractor drifted — a silently empty extraction turns this assertion "
        "into a no-op, which is the exact failure mode it exists to prevent."
    )

    contracts = [f"contracts/government_revenue/{name}" for name in names]
    absent = [rel for rel in contracts if not (ROOT / rel).exists()]
    assert not absent, (
        "workspace.py loads contract files that are not in the tree:\n  "
        + "\n  ".join(absent)
        + "\n\nThe validator fails CLOSED on a missing schema, so every payload "
        "would read invalid at runtime."
    )

    workflow = _yaml(WORKFLOW)
    triggers = (workflow.get("on") or workflow.get(True))["pull_request"]["paths"]
    unmatched = [rel for rel in contracts if not CLOSURE.matched(rel, triggers)]

    assert not unmatched, (
        f"{len(unmatched)} contract(s) that engine/government_revenue/workspace.py "
        "loads AT RUNTIME match no glob in ci.yml's on.pull_request.paths:\n  "
        + "\n  ".join(unmatched)
        + "\n\nSo editing one of these schemas cannot fire the CI that validates "
        "against it. workspace.py's validator fails CLOSED — a schema edit that "
        "makes every payload read invalid merges without a single check running. "
        "scripts/check_ci_trigger_closure.py does not cover this: it is DEPTH 1 "
        "(the files a test file itself reads), and these are read one layer "
        "deeper, inside the engine module the test imports. Fix by adding "
        '- "contracts/government_revenue/**" to that paths list.'
    )


# ─────────────────────────────────────────────────────────────────────────────
# PATH SELECTION (CI_SELECTIVE=1).  scripts/run_ci_pack.py §PATH SELECTION.
#
# Every test below pins a direction, not a behaviour: the mechanism is allowed to
# run a job it could have skipped, and is never allowed to skip a job it should
# have run.  A test that only asserted "skipping works" would pass just as
# happily on a selector that skips everything.
# ─────────────────────────────────────────────────────────────────────────────

SELECTION_MANIFEST = """
jobs:
  unannotated:
    if: ${{ false }}
    runs-on: ubuntu-latest
    steps:
      - run: echo unannotated
  site-only:
    if: ${{ false }}
    runs-on: ubuntu-latest
    paths:
      - "site/**"
      - "scripts/check_site_js.py"
    steps:
      - run: echo site
  engine-flat:
    if: ${{ false }}
    runs-on: ubuntu-latest
    paths:
      - "engine/*.py"
    steps:
      - run: echo flat
  engine-deep:
    if: ${{ false }}
    runs-on: ubuntu-latest
    paths:
      - "engine/**"
    steps:
      - run: echo deep
"""


def _selection_jobs(tmp_path: Path) -> list:
    manifest = tmp_path / "legacy-jobs.yml"
    manifest.write_text(SELECTION_MANIFEST)
    return PACK.load_legacy_jobs(manifest)


def _ids(jobs) -> list[str]:
    return sorted(job.job_id for job in jobs)


def test_an_unannotated_job_runs_for_every_diff_including_an_empty_one(
    tmp_path: Path,
) -> None:
    """The core safety property: no `paths:` key means unskippable, always.

    This is what makes the whole mechanism inert until someone deliberately opts
    a job in, so it is asserted against the widest set of diffs available: an
    unrelated file, the empty diff, and a diff naming the job itself.
    """
    jobs = _selection_jobs(tmp_path)
    for changed in ([], ["docs/UNRELATED.md"], ["engine/x.py"], ["site/a.html"]):
        selected, skipped = PACK.select_jobs(jobs, changed)
        assert "unannotated" in _ids(selected), (
            f"a job with no `paths:` was skipped for diff {changed!r} — the "
            "default is unskippable, and every other safety property here rests "
            "on it"
        )
        assert "unannotated" not in _ids(skipped)


def test_a_declared_job_runs_on_a_match_and_skips_only_without_one(
    tmp_path: Path,
) -> None:
    jobs = _selection_jobs(tmp_path)

    selected, skipped = PACK.select_jobs(jobs, ["site/markets.html"])
    assert "site-only" in _ids(selected)
    assert "site-only" not in _ids(skipped)

    selected, skipped = PACK.select_jobs(jobs, ["scripts/check_site_js.py"])
    assert "site-only" in _ids(selected), "an exact-file entry must match itself"

    selected, skipped = PACK.select_jobs(jobs, ["docs/UNRELATED.md"])
    assert "site-only" in _ids(skipped)
    assert "site-only" not in _ids(selected)

    # One matching file in a diff of many is enough — selection is an OR over the
    # changed set, never a majority vote.
    selected, _ = PACK.select_jobs(
        jobs, ["docs/a.md", "docs/b.md", "site/markets.html", "docs/c.md"]
    )
    assert "site-only" in _ids(selected)


def test_an_unusable_diff_runs_everything(monkeypatch: pytest.MonkeyPatch) -> None:
    """git failure, empty output and an unresolvable ref all mean "no answer"."""
    monkeypatch.setenv(PACK.SELECTION_ENV, "1")

    monkeypatch.setattr(PACK, "_git_stdout", lambda args: None)
    assert PACK.changed_files("main", "topic") is None, "git failure must be None"

    # Refs resolve, diff is empty: indistinguishable from a base that is simply
    # wrong (a shallow clone whose merge-base is HEAD), and the wrong reading
    # skips the entire pack.
    monkeypatch.setattr(
        PACK, "_git_stdout", lambda args: "abc\n" if args[0] == "rev-parse" else ""
    )
    assert PACK.changed_files("main", "topic") is None, "empty diff must be None"

    # Base ref does not resolve under any spelling.
    monkeypatch.setattr(
        PACK, "_git_stdout", lambda args: None if args[0] == "rev-parse" else "a.py\n"
    )
    assert PACK.changed_files("main", "topic") is None


def test_an_unusable_diff_keeps_every_job_in_the_pack(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    jobs = _selection_jobs(tmp_path)
    monkeypatch.setenv(PACK.SELECTION_ENV, "1")
    monkeypatch.setattr(PACK, "changed_files", lambda base, head: None)
    assert _ids(PACK.apply_selection(jobs)) == _ids(jobs)


@pytest.mark.parametrize(
    "trigger",
    [
        "tests/conftest.py",
        "config.yml",
        ".github/ci/legacy-jobs.yml",
        "scripts/run_ci_pack.py",
        "scripts/gh_path_filter.py",
        ".github/workflows/ci.yml",
        ".github/workflows/daily.yml",
    ],
)
def test_each_always_run_trigger_disarms_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, trigger: str
) -> None:
    """A change to the machinery invalidates the selection, not just a job."""
    jobs = _selection_jobs(tmp_path)
    assert PACK.always_run_reason([trigger]) is not None, (
        f"{trigger} no longer disarms selection"
    )

    monkeypatch.setenv(PACK.SELECTION_ENV, "1")
    monkeypatch.setattr(
        PACK, "changed_files", lambda base, head: [trigger, "docs/UNRELATED.md"]
    )
    assert _ids(PACK.apply_selection(jobs)) == _ids(jobs)

    # ...and the same diff WITHOUT the trigger does skip, so the assertion above
    # is not passing for some unrelated reason.
    monkeypatch.setattr(PACK, "changed_files", lambda base, head: ["docs/UNRELATED.md"])
    assert _ids(PACK.apply_selection(jobs)) != _ids(jobs)


def test_an_ordinary_file_does_not_disarm_selection() -> None:
    assert PACK.always_run_reason(["engine/market_state.py", "site/a.html"]) is None


@pytest.mark.parametrize("value", [None, "", "0", "true", "yes", "2"])
def test_selection_is_off_unless_the_env_var_is_exactly_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    jobs = _selection_jobs(tmp_path)
    if value is None:
        monkeypatch.delenv(PACK.SELECTION_ENV, raising=False)
    else:
        monkeypatch.setenv(PACK.SELECTION_ENV, value)
    assert PACK.selection_enabled() is False
    monkeypatch.setattr(
        PACK,
        "changed_files",
        lambda base, head: pytest.fail("the diff must not be read when selection is off"),
    )
    assert _ids(PACK.apply_selection(jobs)) == _ids(jobs)


def test_selection_is_on_when_the_env_var_is_exactly_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(PACK.SELECTION_ENV, "1")
    assert PACK.selection_enabled() is True


def test_glob_semantics_are_githubs_not_fnmatchs(tmp_path: Path) -> None:
    """A single `*` must NOT cross `/`; `**` must.

    `fnmatch` lets one `*` cross a directory separator, which would make
    `engine/*.py` silently claim every nested module — the declaration would then
    mean something wider than its author wrote, and jobs would be skipped on the
    strength of coverage that does not exist.
    """
    jobs = _selection_jobs(tmp_path)

    selected, skipped = PACK.select_jobs(jobs, ["engine/sub/x.py"])
    assert "engine-flat" in _ids(skipped), (
        "`engine/*.py` matched a NESTED file — that is fnmatch semantics, not "
        "GitHub's, and it widens every declaration past what its author wrote"
    )
    assert "engine-deep" in _ids(selected), "`engine/**` must cross directories"

    selected, _ = PACK.select_jobs(jobs, ["engine/x.py"])
    assert {"engine-flat", "engine-deep"} <= set(_ids(selected))


def test_a_paths_key_that_is_not_a_usable_pattern_list_fails_closed(
    tmp_path: Path,
) -> None:
    for bad, expected in (
        ("paths: []", "non-empty list"),
        ("paths: engine/**", "non-empty list"),
        ('paths:\n      - ""', "non-empty string"),
        ('paths:\n      - "!engine/**"', "negation"),
    ):
        manifest = tmp_path / "bad.yml"
        manifest.write_text(
            "jobs:\n"
            "  broken:\n"
            "    if: ${{ false }}\n"
            "    runs-on: ubuntu-latest\n"
            f"    {bad}\n"
            "    steps:\n"
            "      - run: echo hi\n"
        )
        with pytest.raises(PACK.ManifestError, match=expected):
            PACK.load_legacy_jobs(manifest)


def test_every_skip_is_announced_where_github_can_see_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """A silent skip is indistinguishable from a job that never existed.

    The annotation must START the line: every builder here logs with a prefixing
    format, so a logged `::notice` emits `INFO ::notice` and GitHub drops it —
    the call reviews as an announcement and produces nothing (CLAUDE.md).
    """
    jobs = _selection_jobs(tmp_path)
    monkeypatch.setenv(PACK.SELECTION_ENV, "1")
    monkeypatch.setattr(PACK, "changed_files", lambda base, head: ["docs/UNRELATED.md"])

    selected = PACK.apply_selection(jobs)
    out = capsys.readouterr().out
    notices = [line for line in out.splitlines() if line.startswith("::notice")]
    assert notices, "no ::notice reached stdout at column 0"

    skipped = sorted(set(_ids(jobs)) - set(_ids(selected)))
    assert skipped, "the fixture must skip something for this test to mean anything"
    blob = "\n".join(notices)
    for job_id in skipped:
        assert job_id in blob, f"{job_id} was skipped without being named"
    assert f"skipping {len(skipped)}" in blob, "the skip COUNT is not reported"
    weight = sum(job.weight for job in jobs if job.job_id in skipped)
    assert f"weight saved {weight}" in blob, "the estimated weight saved is not reported"


def test_a_full_run_says_so_rather_than_staying_silent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    jobs = _selection_jobs(tmp_path)
    monkeypatch.delenv(PACK.SELECTION_ENV, raising=False)
    PACK.apply_selection(jobs)
    out = capsys.readouterr().out
    assert any(
        line.startswith("::notice") and "selection OFF" in line
        for line in out.splitlines()
    ), "a full run must announce WHY it is full, not just produce no skip notice"


def test_declared_paths_in_the_live_manifest_cover_their_read_closure() -> None:
    """The guard, run over the real manifest — the same call CI makes.

    Registered in config/house_law_checks.yml as ops.ci_pack_paths_cover_closure
    and wired into the workflow-yaml job; this keeps a red visible in the pack
    that owns run_ci_pack.py rather than only in the guard step.
    """
    paths_guard = importlib.util.spec_from_file_location(
        "check_ci_pack_paths", ROOT / "scripts" / "check_ci_pack_paths.py"
    )
    assert paths_guard and paths_guard.loader
    module = importlib.util.module_from_spec(paths_guard)
    sys.modules[paths_guard.name] = module
    paths_guard.loader.exec_module(module)

    rows = module.audit(MANIFEST)
    assert rows, "no job declares `paths:` — the guard would be vacuous"
    gaps = {
        row["job"]: [rel for rel, _ in row["gaps"]] for row in rows if row["gaps"]
    }
    assert not gaps, (
        "a declared `paths:` list does not cover what its job reads:\n  "
        + "\n  ".join(f"{job}: {rels}" for job, rels in gaps.items())
        + "\n\nA pull request touching only those files would SKIP the job. Widen "
        "the declaration (prefer the directory); never narrow the subject."
    )


def test_the_coverage_guard_fires_on_an_omission_and_passes_on_a_superset() -> None:
    """Round-trip the detector itself, so a blind guard cannot read green."""
    paths_guard = importlib.util.spec_from_file_location(
        "check_ci_pack_paths_probe", ROOT / "scripts" / "check_ci_pack_paths.py"
    )
    assert paths_guard and paths_guard.loader
    module = importlib.util.module_from_spec(paths_guard)
    sys.modules[paths_guard.name] = module
    paths_guard.loader.exec_module(module)

    found = {
        "engine/marketing/press_lane.py": "import",
        "site/markets.html": "path literal",
        "scripts/build_x.py": "import",
    }
    omitted = module.uncovered(["engine/**", "site/**"], found)
    assert [rel for rel, _ in omitted] == ["scripts/build_x.py"], (
        "the guard did not report the one subject the declaration omits"
    )
    assert module.uncovered(["engine/**", "site/**", "scripts/**"], found) == []
    assert module.uncovered(["**"], found) == []
    assert len(module.uncovered([], found)) == len(found)

    # And the direction that matters: a declaration wider than the closure is
    # never a finding. Over-declaring costs a needless run; under-declaring ships
    # a regression, so only one of the two may ever be reported.
    assert module.uncovered(["engine/**", "site/**", "scripts/**", "app/**"], found) == []


def test_selection_never_repartitions_a_pull_requests_packs() -> None:
    """PR pack N must stay a strict SUBSET of main's pack N.

    `merge_on_green`'s base-inherited-red refresh compares checks BY NAME: it
    excuses a pull request's `ci-pack-2` red when main's own proof is red on
    `ci-pack-2`. Rebalancing the survivors would put different jobs under that
    name on the two sides, and the fail-open direction of that mistake is a real
    red excused as inherited (CLAUDE.md, #5037).
    """
    jobs = PACK.load_legacy_jobs(MANIFEST)
    packs = PACK.partition_jobs(jobs, 4)
    for index, pack in enumerate(packs):
        selected, skipped = PACK.select_jobs(pack, ["site/markets.html"])
        assert set(_ids(selected)) <= set(_ids(pack)), (
            f"pack {index} gained a job under selection"
        )
        assert set(_ids(selected)) | set(_ids(skipped)) == set(_ids(pack)), (
            f"pack {index} lost a job that was neither run nor reported skipped"
        )


def test_ci_yml_arms_selection_for_pull_requests_only() -> None:
    """main / push / dispatch / schedule must keep proving the whole manifest."""
    workflow = _yaml(WORKFLOW)
    step = next(
        step
        for step in workflow["jobs"]["ci-pack"]["steps"]
        if "run_ci_pack.py" in str(step.get("run", ""))
    )
    expression = str(step["env"][PACK.SELECTION_ENV])
    assert "github.event_name == 'pull_request'" in expression, (
        "CI_SELECTIVE is no longer scoped to pull requests. main's ci.yml run is "
        "what merge_on_green.main_proof reads to decide whether a pull request's "
        "red is base-side; a partial main proof narrows that signal silently."
    )
    assert re.search(r"&&\s*'1'", expression), "the armed value must be exactly '1'"
    assert re.search(r"\|\|\s*'0'", expression), "every other event must get '0'"
