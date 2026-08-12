from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest

from scripts.ci_scope_dependencies import suite_dependency_closure
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
    """PR runs coalesce by cancel; MAIN proofs must be allowed to conclude.

    THE 2026-08-09 BASELINE LIVELOCK — a flat `cancel-in-progress: true` on these two
    workflows made main's CI proof structurally unreachable, and 12 merge-blocked +
    56 cap-deferred pull requests could not drain (sweep run 31311549150, 11:44:42Z:
    "0 main commit(s) classified … main proof: NO clean name at unknown-sha").

      ci.yml has no `push` trigger, so main is proven ONLY by a workflow_dispatch,
      and every main-ref dispatch shares `ci-refs/heads/main`. Each pinned session
      re-firing the documented `gh workflow run ci.yml --ref main` lever therefore
      KILLED the proof already running: 31309720615 cancelled at 44 minutes by
      31311537537, itself cancelled 4 minutes later by 31311693575.

      fences.yml is the OTHER proof merge_on_green reads, and the only one that
      triggers on push to main — but main takes a wire/nightly push every ~30-90s,
      and each one cancelled its predecessor (5 runs between 11:40:38Z and
      11:43:04Z). All ten runs in the sweeper's walk were `cancelled`. A run longer
      than the gap between pushes can NEVER conclude.

    So the expressions below are load-bearing, not stylistic. Reverting either to a
    flat `true` re-closes the sweeper's base-inherited-red refresh and re-pins the
    whole fleet — if this test is what is in your way, you are removing the fix.
    Dedup is NOT what the expressions cost: GitHub replaces the single PENDING run
    per group regardless of the flag, so bursts still collapse; only the kill is gone.
    """
    ci = _yaml(WORKFLOW)
    fences = _yaml(FENCES)
    # PR events keep cancel-on-newer-push. Dispatches (ci) and main pushes (fences)
    # do not — those are the two proof paths.
    assert ci["concurrency"]["cancel-in-progress"] == (
        "${{ github.event_name != 'workflow_dispatch' }}"
    ), "a main baseline dispatch must never cancel the proof already running"
    assert fences["concurrency"]["cancel-in-progress"] == (
        "${{ github.event_name == 'pull_request' }}"
    ), "a push to main must never cancel the fence run proving an earlier main SHA"
    assert "pull_request.number" in ci["concurrency"]["group"]
    assert "github.ref" in ci["concurrency"]["group"]
    assert "pull_request.number" in fences["concurrency"]["group"]
    # The 2026-07-28 merged-close fence (PR #3867) lives in the same expression and
    # must survive every later edit to this block.
    assert "merged" in ci["concurrency"]["group"], (
        "a MERGED close must stay fenced into its own group, or a fast squash-merge "
        "cancels the PR's own proof run and the merged head is unproven forever"
    )


def test_scope_glob_separator_semantics() -> None:
    """`*` must not cross `/`, or a one-directory scope silently covers a subtree."""
    match = lambda pattern, path: bool(  # noqa: E731
        PACK._glob_to_regex(pattern).match(path)
    )
    assert match("engine/*", "engine/a.py")
    assert not match("engine/*", "engine/a/b.py")
    assert match("engine/**", "engine/a/b.py")
    assert match("engine/", "engine/a/b.py")
    assert match("tests/test_x*.py", "tests/test_xy.py")
    assert not match("tests/test_x*.py", "tests/test_y.py")
    assert match("**/conftest.py", "tests/conftest.py")
    assert match("**/conftest.py", "conftest.py")


def test_selection_fails_safe_toward_running_everything() -> None:
    """Every unknown must widen the run, never narrow it.

    A wasted runner-minute is cheap; a false green is not. These four are the
    only ways scoping can be wrong, and all four must resolve to the full suite.
    """
    jobs, summary = PACK.infer_job_scopes(PACK.load_legacy_jobs(MANIFEST))
    scoped = [job for job in jobs if job.paths]
    assert len(scoped) >= 25, summary

    # 1. changed set unknowable (git failed, or main's baseline passes no ref)
    assert len(PACK.select_jobs(jobs, None)[0]) == len(jobs)
    # 2. a global invalidator can change what ANY job means
    for invalidator in ("scripts/run_ci_pack.py", "tests/conftest.py",
                        "requirements.txt", "worker/requirements-dev.txt",
                        "config/dag.yml", "config/synapse.yml",
                        ".github/ci/legacy-jobs.yml"):
        selected, reason = PACK.select_jobs(jobs, [invalidator])
        assert len(selected) == len(jobs), f"{invalidator} must force a full run"
        assert "full suite" in reason
    # 3. an unowned path is ambiguous, so it widens to the full suite
    selected, _ = PACK.select_jobs(jobs, ["no/such/path/at/all.txt"])
    assert len(selected) == len(jobs)
    # 4. a scoped job runs whenever its own scope matches
    for job in scoped:
        probe = job.paths[0].replace("**/", "").replace("**", "x").replace("*", "x")
        hit, _ = PACK.select_jobs(jobs, [probe])
        assert job in hit, f"{job.job_id} must run when {probe} changes"


def test_declared_scope_must_cover_paths_the_job_itself_reads() -> None:
    """A scope narrower than the job's own commands is a hard manifest error.

    This is what makes scoping reviewable instead of trusted: a job that runs
    `pytest tests/test_x.py` but scopes itself elsewhere would never re-run when
    that test changed, and would report green forever.
    """
    findings = PACK._scope_coverage_findings(
        "demo",
        {"steps": [{"run": "python -m pytest tests/test_ci_pack.py"}]},
        ("engine/nowhere/**",),
    )
    assert findings and "tests/test_ci_pack.py" in findings[0]
    # Widening to cover it clears the finding.
    assert not PACK._scope_coverage_findings(
        "demo",
        {"steps": [{"run": "python -m pytest tests/test_ci_pack.py"}]},
        ("tests/**",),
    )
    # A path that no longer exists must not be able to fail the build.
    assert not PACK._scope_coverage_findings(
        "demo",
        {"steps": [{"run": "python -m pytest tests/test_deleted_long_ago.py"}]},
        ("engine/nowhere/**",),
    )


def test_every_declared_scope_in_the_real_manifest_is_covered() -> None:
    """The production manifest itself must satisfy the coverage rule."""
    PACK.load_legacy_jobs(MANIFEST)  # raises ManifestError on any gap


def test_real_manifest_has_non_vacuous_derived_scopes() -> None:
    """The mechanism shipped with 0/179 owners; the 180-job manifest must stay live."""
    jobs, summary = PACK.infer_job_scopes(PACK.load_legacy_jobs(MANIFEST))
    scoped = {job.job_id: set(job.paths) for job in jobs if job.paths}
    assert len(scoped) >= 25, summary
    assert "unrun-government-revenue-candidate-projection" in scoped
    assert "stock-seasonality" in scoped
    assert "synapse-read-gate" in scoped
    assert "falsifier-tripwires" in scoped
    assert "tests/test_falsifier_tripwires.py" in scoped["falsifier-tripwires"]
    assert "engine/falsifier_tripwires.py" in scoped["falsifier-tripwires"]
    assert "lib/store.py" in scoped["falsifier-tripwires"]
    assert "lib/config.py" in scoped["falsifier-tripwires"]


def test_derived_closure_follows_relative_first_party_imports() -> None:
    """Package-local imports are ownership edges, not optional implementation detail."""
    closure = suite_dependency_closure("tests/test_admin_modules.py")
    assert "admin/ai_cost.py" in closure.files
    assert "admin/config_store.py" in closure.files
    assert "admin/flags.py" in closure.files
    assert "admin/paths.py" in closure.files

    materializer = suite_dependency_closure(
        "tests/test_capital_structure_share_count_materializer.py"
    )
    assert "engine/capital_structure/share_count_materializer.py" in materializer.files
    assert "engine/capital_structure/share_count_truth.py" in materializer.files


def test_whole_tree_glob_job_owns_every_scanned_code_root() -> None:
    """A tree scan cannot be narrowed to the scanner suite's import closure."""
    jobs, _ = PACK.infer_job_scopes(PACK.load_legacy_jobs(MANIFEST))
    export_guard = next(job for job in jobs if job.job_id == "all-exports-resolve")
    assert "engine/**" in export_guard.paths
    assert "scripts/**" in export_guard.paths
    assert "research/**" in export_guard.paths
    selected, _ = PACK.select_jobs(jobs, ["engine/market_state.py"])
    assert export_guard in selected


def test_derived_scopes_are_startable_by_the_ci_workflow() -> None:
    """A job owner is useless when its dependency edit cannot start ci.yml."""
    jobs, _ = PACK.infer_job_scopes(PACK.load_legacy_jobs(MANIFEST))
    on = _yaml(WORKFLOW).get("on") or _yaml(WORKFLOW).get(True)
    triggers = tuple(on["pull_request"]["paths"])
    gaps: list[tuple[str, str]] = []
    for job in jobs:
        for path in job.paths:
            if any(char in path for char in "*?"):
                if path not in triggers:
                    gaps.append((job.job_id, path))
            elif not PACK._matches_any(triggers, path):
                gaps.append((job.job_id, path))
    assert not gaps, gaps[:25]


def test_representative_narrow_diffs_skip_at_least_one_quarter_of_jobs() -> None:
    """The conservative first tranche must still deliver material speed."""
    jobs, _ = PACK.infer_job_scopes(PACK.load_legacy_jobs(MANIFEST))
    cases = {
        "govrev": [
            "research/GOVERNMENT_REVENUE_FORESIGHT_HANDOFF_2026-08-09.md",
            "scripts/build_government_revenue_candidates.py",
            "tests/test_government_revenue_candidate_projection.py",
        ],
        "tripwires": [
            "data/cycle_ontology/falsifiers.json",
            "data/cycle_ontology/tripwire_state.json",
            "engine/falsifier_tripwires.py",
            "tests/test_falsifier_tripwires.py",
        ],
    }
    for name, changed in cases.items():
        selected, reason = PACK.select_jobs(jobs, changed)
        assert len(selected) <= (len(jobs) * 4) // 5, (name, len(selected), reason)
    selected, _ = PACK.select_jobs(jobs, cases["tripwires"])
    assert any(job.job_id == "falsifier-tripwires" for job in selected)

    content, reason = PACK.select_jobs(jobs, ["content/seo/blog/example.md"])
    assert len(content) < len(jobs), reason
    assert any(job.job_id == "free-content-estate" for job in content)


@pytest.mark.parametrize("graph", ["config/dag.yml", "config/synapse.yml"])
def test_graph_metadata_is_a_global_invalidator(graph: str) -> None:
    jobs, _ = PACK.infer_job_scopes(PACK.load_legacy_jobs(MANIFEST))
    selected, reason = PACK.select_jobs(jobs, [graph])
    assert len(selected) == len(jobs)
    assert "global invalidator" in reason


def test_passive_markdown_stays_scoped_but_unknown_root_fails_full() -> None:
    jobs, _ = PACK.infer_job_scopes(PACK.load_legacy_jobs(MANIFEST))
    docs, _ = PACK.select_jobs(jobs, ["research/UNOWNED_HANDOFF.md"])
    code, reason = PACK.select_jobs(jobs, ["brand_new_root/unowned_runtime.xyz"])
    assert len(docs) < len(jobs)
    assert len(code) == len(jobs)
    assert "no proven owner" in reason


def test_name_status_diff_preserves_both_sides_of_rename(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = (
        "R100\0engine/old.py\0engine/new.py\0"
        "D\0config/removed.yml\0M\0tests/test_kept.py\0"
    )

    def fake_run(*args: object, **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(stdout=payload)

    monkeypatch.setattr(PACK.subprocess, "run", fake_run)
    assert PACK.changed_files("deadbeef") == [
        "engine/old.py",
        "engine/new.py",
        "config/removed.yml",
        "tests/test_kept.py",
    ]


def test_name_status_diff_preserves_copy_spaces_and_unicode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = "C087\0docs/old name.md\0docs/新 name.md\0"
    commands: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        commands.append(command)
        return SimpleNamespace(stdout=payload)

    monkeypatch.setattr(
        PACK.subprocess,
        "run",
        fake_run,
    )
    assert PACK.changed_files("deadbeef") == ["docs/old name.md", "docs/新 name.md"]
    assert "--find-copies" in commands[0]


def test_empty_successful_diff_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        PACK.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout=""),
    )
    assert PACK.changed_files("deadbeef") is None


def test_scope_mode_kill_switch_defaults_and_can_be_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CI_SCOPE_MODE", raising=False)
    assert PACK.parse_args(["--workflow", str(MANIFEST)]).scope_mode == "active"
    monkeypatch.setenv("CI_SCOPE_MODE", "off")
    assert PACK.parse_args(["--workflow", str(MANIFEST)]).scope_mode == "off"


def test_shadow_mode_emits_machine_readable_plan_and_job_results(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    definition = {"steps": [], "runs-on": "ubuntu-latest", "if": "${{ false }}"}
    owner = PACK.LegacyJob("owner", definition, 0, 1, ("engine/**",))
    skipped = PACK.LegacyJob("would-skip", definition, 1, 1, ("site/**",))
    jobs = [owner, skipped]
    monkeypatch.setattr(PACK, "load_legacy_jobs", lambda path: jobs)
    monkeypatch.setattr(PACK, "changed_files", lambda base: ["engine/example.py"])
    monkeypatch.setattr(PACK, "infer_job_scopes", lambda loaded: (loaded, "test scopes"))
    assert PACK.main([
        "--workflow", str(MANIFEST),
        "--changed-from", "base-sha",
        "--scope-mode", "shadow",
        "--validate-only",
        "--pack-count", "1",
    ]) == 0
    plan_line = next(
        line for line in capsys.readouterr().out.splitlines()
        if line.startswith("CI_SCOPE_SHADOW_PLAN=")
    )
    plan = json.loads(plan_line.split("=", 1)[1])
    assert plan["predicted_selected"] == ["owner"]
    assert plan["predicted_skipped"] == ["would-skip"]

    monkeypatch.setattr(PACK, "_workspace_root", lambda: ROOT)
    monkeypatch.setattr(PACK, "_restore_workspace", lambda: None)
    monkeypatch.setattr(PACK, "_run_job", lambda *args, **kwargs: None)
    assert PACK.execute_pack(jobs, shadow_predicted=frozenset({"owner"})) == 0
    records = [
        json.loads(line.split("=", 1)[1])
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("CI_SCOPE_SHADOW_RESULT=")
    ]
    assert records == [
        {"job": "owner", "predicted_selected": True, "status": "passed"},
        {"job": "would-skip", "predicted_selected": False, "status": "passed"},
    ]


def test_packs_stay_balanced_over_the_selected_subset() -> None:
    """Balance must be computed on the SELECTION, not the full manifest.

    Otherwise a scoped run leaves whole packs empty while one pack carries the
    work, and time-to-green gets worse instead of better.
    """
    jobs = PACK.load_legacy_jobs(MANIFEST)
    subset = sorted(jobs, key=lambda job: -job.weight)[:40]
    packs = PACK.partition_jobs(subset, 4)
    weights = [sum(job.weight for job in pack) for pack in packs]
    assert sum(len(pack) for pack in packs) == len(subset)
    assert max(weights) - min(weights) <= max(job.weight for job in subset)


# ── the plan is a contract between ci-plan and twelve packs ──────────────────
#
# Wave B (2026-08-11) moved the selection decision out of main() into
# build_plan(): ci-plan publishes one hashed plan, and every pack RECOMPUTES it
# and refuses when its own hash disagrees. So the tests below are not "does the
# plan look sensible" — they are the two ways that arrangement goes silently
# wrong.
#
#   1. THE PLAN NARROWS WHEN IT HAS NO RIGHT TO. `has_work: false` skips every
#      pack, and ci-gate then publishes an affirmative success anyway (it must:
#      merge_on_green requires a real pass, because absence of red is not a pass
#      — #4779). So a plan that wrongly proves no-work merges a completely unrun
#      PR green. Every widening rule is therefore re-pinned HERE, through
#      build_plan, not only through select_jobs: the rules moved, and a rule that
#      is correct in select_jobs but unreachable from build_plan is no rule.
#   2. THE PLAN AND THE EXECUTION DISAGREE. Twelve runners each deriving the
#      partition independently is exactly the shape a nondeterministic input
#      splits, and the resulting green means nothing. The parity test walks EVERY
#      index, because a divergence that only hits pack 7 is invisible to a test
#      that checks pack 0.


def _plan_job(
    job_id: str,
    ordinal: int,
    *,
    weight: int = 1,
    paths: tuple[str, ...] = (),
) -> object:
    """A minimal LegacyJob fixture: id, order, weight, hand-written scope."""
    return PACK.LegacyJob(
        job_id=job_id,
        definition={"if": PACK.DISABLED_IF, "runs-on": "ubuntu-latest", "steps": []},
        ordinal=ordinal,
        weight=weight,
        paths=paths,
    )


def _freeze_scope_inference(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the fixtures' hand-written scopes; real inference would erase them.

    infer_job_scopes derives ownership from a job's OWN commands, so a fixture
    job with no steps comes back UNSCOPED — which means always-on — and every
    selection assertion below would then pass for the wrong reason. It is also
    the expensive half of a real plan (106 s over the 180-job manifest, measured
    2026-08-11); a synthetic test must not pay it.
    """
    monkeypatch.setattr(
        PACK, "infer_job_scopes", lambda jobs: (list(jobs), "fixture scopes")
    )


def _parse_github_output(text: str) -> dict[str, str]:
    """Parse a `$GITHUB_OUTPUT` file the way the Actions runner does.

    Only the heredoc form is accepted, on purpose. A bare `name=value` line
    cannot carry the newline a multi-line ManifestError puts into `reason`, so
    emitting one would truncate the value GitHub hands to ci-gate — and the
    truncation would be invisible until a manifest actually broke.
    """
    values: dict[str, str] = {}
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        head = lines[index]
        assert "<<" in head, f"not a heredoc $GITHUB_OUTPUT entry: {head!r}"
        name, delimiter = head.split("<<", 1)
        index += 1
        body: list[str] = []
        while lines[index] != delimiter:
            body.append(lines[index])
            index += 1
        values[name] = "\n".join(body)
        index += 1
    return values


def _full_plan() -> object:
    """The real manifest's baseline plan: no --changed-from, so no inference."""
    return PACK.plan_from_workflow(
        MANIFEST, changed_from=None, scope_mode="active", pack_count=12
    )


def _never_execute(*args: object, **kwargs: object) -> int:
    raise AssertionError("execute_pack must not be reached on this path")


def test_plan_is_deterministic() -> None:
    first = _full_plan()
    second = _full_plan()
    assert first == second
    assert first.plan_sha256 == second.plan_sha256
    # Not satisfied by two empty plans agreeing about nothing.
    assert any(first.pack_jobs)


def test_plan_hash_covers_job_assignment_but_not_prose() -> None:
    """The hash is what makes twelve independent derivations one decision."""
    plan = _full_plan()
    payload = PACK.plan_hash_payload(
        changed_from=plan.changed_from,
        scope_mode=plan.scope_mode,
        pack_count=plan.pack_count,
        eligible_job_ids=plan.eligible_job_ids,
        pack_jobs=plan.pack_jobs,
        pack_weights=plan.pack_weights,
    )
    assert PACK._canonical_digest(payload) == plan.plan_sha256

    # Move ONE job to a different pack: same jobs, same membership, new plan.
    moved = [list(pack) for pack in plan.pack_jobs]
    assert moved[1], "fixture assumption: pack 1 carries jobs on the full suite"
    moved[2].append(moved[1].pop())
    assert PACK._canonical_digest({**payload, "pack_jobs": moved}) != plan.plan_sha256

    # Reordering the eligible list changes nothing about MEMBERSHIP and
    # everything about the partition: partition_jobs is greedy over
    # (-weight, ordinal), so the sequence is an input, which is why the payload
    # keeps plan order instead of sorting it.
    reordered = list(reversed(plan.eligible_job_ids))
    assert (
        PACK._canonical_digest({**payload, "eligible_job_ids": reordered})
        != plan.plan_sha256
    )

    # Prose is excluded BY CONSTRUCTION. If `reason` were hashed, rewording one
    # diagnostic would make every pack refuse a plan selecting identical jobs.
    assert "reason" not in payload
    assert "scope_summary" not in payload


def test_plan_keeps_the_fixed_twelve_pack_assignment() -> None:
    """Wave B changed WHERE the partition is decided, never WHAT it decides."""
    plan = _full_plan()
    assert plan.pack_count == 12
    assert len(plan.pack_jobs) == 12
    assert len(plan.pack_weights) == 12
    flattened = [job_id for pack in plan.pack_jobs for job_id in pack]
    assert sorted(flattened) == sorted(plan.eligible_job_ids)
    assert len(flattened) == len(set(flattened))
    by_id = {job.job_id: job for job in plan.scoped_jobs}
    for index, pack in enumerate(plan.pack_jobs):
        assert plan.pack_weights[index] == sum(by_id[job_id].weight for job_id in pack)
    # Same partition the standalone function produces from the same jobs.
    packs = PACK.partition_jobs(
        [by_id[job_id] for job_id in plan.eligible_job_ids], 12
    )
    assert plan.pack_jobs == tuple(
        tuple(job.job_id for job in pack) for pack in packs
    )


def test_full_suite_plan_emits_all_twelve_packs() -> None:
    """Main's baseline passes no --changed-from, so nothing may be narrowed."""
    plan = _full_plan()
    assert plan.reason == "full suite: changed-file set unavailable"
    assert plan.nonempty_pack_indices == tuple(range(12))
    assert plan.has_work is True
    assert plan.matrix() == {"include": [{"pack": index} for index in range(12)]}
    assert plan.skipped_job_ids == ()


def test_only_non_empty_pack_indices_reach_the_matrix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _freeze_scope_inference(monkeypatch)
    jobs = [
        _plan_job("heavy", 0, weight=9),
        _plan_job("middle", 1, weight=5),
        _plan_job("light", 2, weight=3),
    ]
    plan = PACK.build_plan(
        jobs, None, changed_from=None, scope_mode="active", pack_count=12
    )
    # The DOCUMENT still describes all twelve packs; only the MATRIX narrows.
    assert len(plan.pack_jobs) == 12
    assert plan.to_dict()["packs"][11] == {"index": 11, "weight": 0, "jobs": []}
    assert plan.nonempty_pack_indices == (0, 1, 2)
    assert plan.matrix() == {"include": [{"pack": 0}, {"pack": 1}, {"pack": 2}]}
    assert plan.has_work is True


def test_one_selected_job_emits_one_pack(monkeypatch: pytest.MonkeyPatch) -> None:
    _freeze_scope_inference(monkeypatch)
    jobs = [
        _plan_job("owner", 0, paths=("engine/**",)),
        _plan_job("elsewhere", 1, paths=("site/**",)),
    ]
    plan = PACK.build_plan(
        jobs,
        ["engine/example.py"],
        changed_from="base-sha",
        scope_mode="active",
        pack_count=12,
    )
    assert plan.eligible_job_ids == ("owner",)
    assert plan.skipped_job_ids == ("elsewhere",)
    assert plan.nonempty_pack_indices == (0,)
    assert plan.matrix() == {"include": [{"pack": 0}]}
    assert plan.has_work is True


def test_passive_unowned_markdown_can_plan_no_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ONE lawful road to has_work=false: an affirmative empty selection.

    Unreachable on the production manifest, which always carries unscoped
    always-on jobs — so it is pinned on fixtures rather than left untested until
    the day selection narrows enough to reach it in anger.
    """
    _freeze_scope_inference(monkeypatch)
    jobs = [
        _plan_job("engine-owner", 0, paths=("engine/**",)),
        _plan_job("site-owner", 1, paths=("site/**",)),
    ]
    plan = PACK.build_plan(
        jobs,
        ["research/CONTINUATION_HANDOFF.md"],
        changed_from="base-sha",
        scope_mode="active",
        pack_count=12,
    )
    assert plan.eligible_job_ids == ()
    assert plan.nonempty_pack_indices == ()
    assert plan.matrix() == {"include": []}
    assert plan.has_work is False
    document = plan.to_dict()
    assert document["has_work"] is False
    assert len(document["packs"]) == 12
    assert all(entry["jobs"] == [] for entry in document["packs"])


def test_unknown_top_level_path_widens_the_plan_to_the_full_suite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _freeze_scope_inference(monkeypatch)
    jobs = [
        _plan_job("engine-owner", 0, paths=("engine/**",)),
        _plan_job("site-owner", 1, paths=("site/**",)),
    ]
    plan = PACK.build_plan(
        jobs,
        ["brand_new_root/unowned_runtime.xyz"],
        changed_from="base-sha",
        scope_mode="active",
        pack_count=12,
    )
    assert set(plan.eligible_job_ids) == {"engine-owner", "site-owner"}
    assert "no proven owner" in plan.reason
    assert plan.has_work is True


def test_global_invalidator_widens_the_plan_without_inferring_scopes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A global invalidator changes what any job MEANS — and short-circuits.

    Skipping inference here is not an optimisation detail worth a comment
    elsewhere: it is a minute of work whose entire answer select_jobs is about
    to discard, paid on the one path where CI is already running everything.
    """
    calls: list[object] = []

    def record(jobs: object) -> tuple[list[object], str]:
        calls.append(jobs)
        return list(jobs), "inference ran"

    monkeypatch.setattr(PACK, "infer_job_scopes", record)
    jobs = [
        _plan_job("engine-owner", 0, paths=("engine/**",)),
        _plan_job("site-owner", 1, paths=("site/**",)),
    ]
    plan = PACK.build_plan(
        jobs,
        ["scripts/run_ci_pack.py", "engine/market_state.py"],
        changed_from="base-sha",
        scope_mode="active",
        pack_count=12,
    )
    assert set(plan.eligible_job_ids) == {"engine-owner", "site-owner"}
    assert "global invalidator" in plan.reason
    assert plan.scope_summary == "scope inference not needed"
    assert calls == []
    assert plan.has_work is True


def test_rename_plans_both_the_old_and_the_new_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`--find-renames` emits BOTH sides; the plan must select both owners.

    Deleting or renaming a subject has to re-run the job that owned its OLD
    path — that job is often the only thing that would notice the subject went
    away — while the new path selects its new owner.
    """
    _freeze_scope_inference(monkeypatch)
    jobs = [
        _plan_job("owns-old", 0, paths=("engine/old.py",)),
        _plan_job("owns-new", 1, paths=("engine/new.py",)),
        _plan_job("elsewhere", 2, paths=("site/**",)),
    ]
    monkeypatch.setattr(PACK, "load_legacy_jobs", lambda path: list(jobs))
    monkeypatch.setattr(
        PACK, "changed_files", lambda base: ["engine/old.py", "engine/new.py"]
    )
    plan = PACK.plan_from_workflow(
        MANIFEST, changed_from="base-sha", scope_mode="active", pack_count=12
    )
    assert set(plan.eligible_job_ids) == {"owns-old", "owns-new"}
    assert plan.skipped_job_ids == ("elsewhere",)

    # Non-vacuity: with only the new side in the diff, the old owner is skipped.
    monkeypatch.setattr(PACK, "changed_files", lambda base: ["engine/new.py"])
    narrowed = PACK.plan_from_workflow(
        MANIFEST, changed_from="base-sha", scope_mode="active", pack_count=12
    )
    assert narrowed.eligible_job_ids == ("owns-new",)


def test_planner_failure_never_emits_no_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An exception is not a proof. It must launch everything, and exit 0.

    This is the whole reason ci-plan is allowed to gate the matrix at all. If a
    planner crash could emit `has_work: false`, ci-gate would publish a green
    aggregate for a PR on which nothing ran.
    """

    def explode(path: object) -> object:
        raise PACK.ManifestError("job 'x' is broken\njob 'y' is broken too")

    monkeypatch.setattr(PACK, "load_legacy_jobs", explode)
    output = tmp_path / "github_output"
    assert (
        PACK.main(
            [
                "--workflow", str(MANIFEST),
                "--pack-count", "12",
                "--plan-only",
                "--github-output", str(output),
            ]
        )
        == 0
    )
    outputs = _parse_github_output(output.read_text())
    assert json.loads(outputs["matrix"]) == {
        "include": [{"pack": index} for index in range(12)]
    }
    assert outputs["has_work"] == "true"
    assert outputs["plan_sha"] == ""
    assert outputs["reason"].startswith("full suite: planner error")
    warning = next(
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("::warning title=ci-plan-fallback::")
    )
    # A multi-line manifest error must not smuggle a newline into an annotation:
    # GitHub reads only the line that STARTS with `::`, so the rest would vanish
    # and the warning would under-report what broke.
    assert "job 'x' is broken" in warning
    assert "job 'y' is broken too" in warning


def test_planner_failure_without_github_output_still_fails_loudly(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Only the ci-plan emission path widens; local validation stays fail-closed.

    Otherwise `--plan-only` would become a way to make a broken manifest look
    fine on a developer's machine.
    """

    def explode(path: object) -> object:
        raise PACK.ManifestError("manifest is broken")

    monkeypatch.setattr(PACK, "load_legacy_jobs", explode)
    assert (
        PACK.main(
            ["--workflow", str(MANIFEST), "--pack-count", "12", "--plan-only"]
        )
        == 2
    )
    assert "manifest is broken" in capsys.readouterr().err


def test_expect_plan_sha_mismatch_refuses_before_any_job_runs(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A pack that would run a different suite must not run a partial one first.

    Half a divergent pack is worse than none: its check name says ci-pack-N
    passed, and the sweeper reads that name as proof of the plan ci-plan
    published, not of whatever this runner actually derived.
    """
    monkeypatch.setattr(PACK, "execute_pack", _never_execute)
    assert (
        PACK.main(
            [
                "--workflow", str(MANIFEST),
                "--pack-index", "0",
                "--pack-count", "12",
                "--execute",
                "--expect-plan-sha", "0" * 64,
            ]
        )
        == 2
    )
    error = next(
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("::error title=ci-plan-parity::")
    )
    assert "0" * 64 in error


def test_plan_and_execution_select_the_exact_same_jobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every index, not one: a divergence at pack 7 is invisible at pack 0.

    This also pins that the plan hash does NOT depend on --pack-index. ci-plan
    computes it without one (default 0) and each pack recomputes it with its
    own; if the index ever entered the hashed payload, packs 1-11 would refuse
    every plan ci-plan ever published and CI would be permanently red.
    """
    plan = _full_plan()
    seen: list[str] = []
    for index in range(12):
        captured: list[str] = []

        def capture(jobs: list[object], **kwargs: object) -> int:
            captured.extend(job.job_id for job in jobs)
            return 0

        monkeypatch.setattr(PACK, "execute_pack", capture)
        assert (
            PACK.main(
                [
                    "--workflow", str(MANIFEST),
                    "--pack-index", str(index),
                    "--pack-count", "12",
                    "--execute",
                    "--expect-plan-sha", plan.plan_sha256,
                ]
            )
            == 0
        ), f"pack {index} refused the plan ci-plan published"
        assert tuple(captured) == plan.pack_jobs[index], index
        seen.extend(captured)
    # Non-vacuity: the twelve packs together are the whole eligible set, so this
    # cannot pass by every pack quietly executing nothing.
    assert sorted(seen) == sorted(plan.eligible_job_ids)


def test_github_output_is_byte_stable_and_parses_as_heredoc(tmp_path: Path) -> None:
    first, second = tmp_path / "one", tmp_path / "two"
    for path in (first, second):
        assert (
            PACK.main(
                [
                    "--workflow", str(MANIFEST),
                    "--pack-count", "12",
                    "--plan-only",
                    "--github-output", str(path),
                    "--matrix-mode", "active",
                ]
            )
            == 0
        )
    assert first.read_text() == second.read_text()
    outputs = _parse_github_output(first.read_text())
    assert set(outputs) == {"matrix", "has_work", "plan_sha", "reason"}
    assert json.loads(outputs["matrix"]) == {
        "include": [{"pack": index} for index in range(12)]
    }
    assert outputs["has_work"] == "true"
    assert len(outputs["plan_sha"]) == 64


def test_matrix_mode_overrules_a_no_work_plan_without_changing_its_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The dynamic matrix's kill switch, pinned where it is actually visible.

    On the real 180-job manifest every diff still fills all twelve packs, so
    `active` and `shadow` emit the SAME matrix and a test against the manifest
    alone would pass without exercising the mode at all. Only a no-work plan
    separates them.

    The hash must be identical across modes: it is a plan input, and the mode is
    an emission policy. If the mode entered the hash, flipping the repository
    variable mid-run would make every in-flight pack refuse its own plan.
    """
    _freeze_scope_inference(monkeypatch)
    jobs = [_plan_job("engine-owner", 0, paths=("engine/**",))]
    monkeypatch.setattr(PACK, "load_legacy_jobs", lambda path: list(jobs))
    monkeypatch.setattr(PACK, "changed_files", lambda base: ["research/NOTE.md"])
    emitted: dict[str, dict[str, str]] = {}
    for mode in ("active", "shadow", "off"):
        path = tmp_path / mode
        assert (
            PACK.main(
                [
                    "--workflow", str(MANIFEST),
                    "--pack-count", "12",
                    "--plan-only",
                    "--changed-from", "base-sha",
                    "--matrix-mode", mode,
                    "--github-output", str(path),
                ]
            )
            == 0
        )
        emitted[mode] = _parse_github_output(path.read_text())

    assert json.loads(emitted["active"]["matrix"]) == {"include": []}
    assert emitted["active"]["has_work"] == "false"
    for mode in ("shadow", "off"):
        assert json.loads(emitted[mode]["matrix"]) == {
            "include": [{"pack": index} for index in range(12)]
        }
        assert emitted[mode]["has_work"] == "true"
        assert emitted[mode]["reason"].startswith(f"matrix {mode} (all 12 launch): ")
    assert len({outputs["plan_sha"] for outputs in emitted.values()}) == 1
    assert len(emitted["active"]["plan_sha"]) == 64


def test_matrix_mode_defaults_to_shadow_and_reads_its_own_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scope mode and matrix mode are separate switches with separate defaults."""
    monkeypatch.delenv("CI_DYNAMIC_MATRIX_MODE", raising=False)
    assert PACK.parse_args(["--workflow", str(MANIFEST)]).matrix_mode == "shadow"
    monkeypatch.setenv("CI_DYNAMIC_MATRIX_MODE", "active")
    assert PACK.parse_args(["--workflow", str(MANIFEST)]).matrix_mode == "active"
    # Flipping the matrix switch must not move scope selection, or the emergency
    # kill switch for one would silently be the kill switch for both.
    monkeypatch.setenv("CI_SCOPE_MODE", "off")
    args = PACK.parse_args(["--workflow", str(MANIFEST)])
    assert (args.scope_mode, args.matrix_mode) == ("off", "active")


def test_plan_only_never_executes_and_refuses_to_pair_with_execute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(PACK, "execute_pack", _never_execute)
    assert (
        PACK.main(
            ["--workflow", str(MANIFEST), "--pack-count", "12", "--plan-only"]
        )
        == 0
    )
    with pytest.raises(SystemExit):
        PACK.parse_args(["--workflow", str(MANIFEST), "--plan-only", "--execute"])


def test_emit_plan_json_prints_exactly_one_machine_line(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`-` is a machine line in a human log, so a SECOND one would break parsers."""
    assert (
        PACK.main(
            [
                "--workflow", str(MANIFEST),
                "--pack-count", "12",
                "--plan-only",
                "--emit-plan-json", "-",
            ]
        )
        == 0
    )
    markers = [
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith(PACK.PLAN_MARKER)
    ]
    assert len(markers) == 1
    document = json.loads(markers[0][len(PACK.PLAN_MARKER):])
    assert set(document) == {
        "schema", "changed_from", "scope_mode", "reason", "scope_summary",
        "legacy_job_count", "eligible_job_count", "eligible_jobs",
        "skipped_job_count", "skipped_jobs", "packs", "nonempty_pack_indices",
        "matrix", "has_work", "plan_sha256",
    }
    assert document["schema"] == PACK.PLAN_SCHEMA == "ci.pack_plan.v1"
    assert [entry["index"] for entry in document["packs"]] == list(range(12))

    # A path gets the same document, indented, and no marker line on stdout.
    path = tmp_path / "plan.json"
    assert (
        PACK.main(
            [
                "--workflow", str(MANIFEST),
                "--pack-count", "12",
                "--plan-only",
                "--emit-plan-json", str(path),
            ]
        )
        == 0
    )
    assert json.loads(path.read_text()) == document
    assert PACK.PLAN_MARKER not in capsys.readouterr().out


def test_the_pack_report_survived_the_plan_refactor(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The three lines every CI log is read by eye for, after the rewrite.

    `pack weights=` is the one that nearly broke: the plan stores weights as a
    TUPLE, and printing it directly would render `pack weights=(481, ...)` — a
    silent cosmetic regression in the only summary a human reads when a pack
    looks wrong.
    """
    plan = _full_plan()
    assert (
        PACK.main(
            [
                "--workflow", str(MANIFEST),
                "--pack-index", "3",
                "--pack-count", "12",
                "--validate-only",
            ]
        )
        == 0
    )
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == (
        f"::notice title=ci-pack-scope::{plan.reason}; {plan.scope_summary}"
    )
    validated = next(line for line in lines if line.startswith("Validated "))
    assert validated.startswith(
        f"Validated {plan.legacy_job_count} legacy jobs; "
        f"{len(plan.eligible_job_ids)} in scope ({plan.reason}); "
    )
    assert f"pack weights={list(plan.pack_weights)};" in validated
    assert f"selected pack 3 ({len(plan.pack_jobs[3])} jobs)." in validated
    selected = next(line for line in lines if line.startswith("Selected jobs: "))
    assert selected == "Selected jobs: " + ", ".join(plan.pack_jobs[3])


def test_workflow_scopes_only_pull_requests() -> None:
    """Main's baseline must never pass --changed-from: it runs the full manifest."""
    pack = _yaml(WORKFLOW)["jobs"]["ci-pack"]
    step = next(
        s for s in pack["steps"]
        if isinstance(s, dict) and "legacy CI pack" in str(s.get("name", ""))
    )
    scope_arg = str(step["env"]["CI_SCOPE_ARG"])
    assert "github.event_name == 'pull_request'" in scope_arg
    assert "--changed-from" in scope_arg
    assert "pull_request.base.sha" in scope_arg
    assert "github.base_ref" not in scope_arg
    assert step["env"]["CI_SCOPE_MODE"] == "${{ vars.CI_SCOPE_MODE || 'shadow' }}"
    on = _yaml(WORKFLOW).get("on") or _yaml(WORKFLOW).get(True)
    pull_paths = on["pull_request"]["paths"]
    assert "**" in pull_paths
    assert "worker/**" in pull_paths
    assert "content/**" in pull_paths
    assert "wrangler.toml" in pull_paths
    assert "$CI_SCOPE_ARG" in str(step["run"])


def test_pack_command_folds_to_exactly_one_shell_command() -> None:
    """A newline in the folded scalar splits one command into two, silently.

    Putting the scope expression inline across continuation lines did exactly
    that: YAML preserves newlines for MORE-indented lines inside `>-`, so
    `--execute` landed on its own line and the pack ran without it. Same family
    as the `#`-in-a-folded-scalar trap, and invisible in review.
    """
    pack = _yaml(WORKFLOW)["jobs"]["ci-pack"]
    for step in pack["steps"]:
        if not isinstance(step, dict) or "run" not in step:
            continue
        if not str(step["run"]).lstrip().startswith('"$RUNNER_TEMP'):
            continue
        command = str(step["run"])
        assert "\n" not in command, (
            "the pack command must fold to ONE line; a newline here silently "
            f"drops every argument after it: {command!r}"
        )
        assert command.rstrip().endswith("--execute")


def test_ci_pack_uses_twelve_balanced_hosted_jobs() -> None:
    workflow = _yaml(WORKFLOW)
    # This job set was EXACTLY {"ci-pack"} until Wave B (2026-08-11) added the
    # planner and the aggregate. Pinned as a subset, not as equality: the
    # invariant this file defends is that CI does not fan back out (86 VMs, one
    # per legacy suite), so a FOURTH job here is the regression — while the exact
    # ci-plan/ci-gate shape belongs to tests/test_ci_plan_workflow.py, which owns
    # it positively. Two suites asserting the same equality would only mean two
    # places to edit, and the weaker one would win.
    assert set(workflow["jobs"]) <= {"ci-plan", "ci-pack", "ci-gate"}
    assert "ci-pack" in workflow["jobs"]
    pack = workflow["jobs"]["ci-pack"]
    # The pack COUNT tunes (2 -> 4 -> 12 as hosted capacity increased); the
    # SHAPE is the contract: a small ordered matrix of balanced packs on hosted
    # runners, never one job per legacy suite (86 VMs), and the matrix must
    # agree with the --pack-count handed to the runner or some packs' jobs
    # would execute nowhere.
    #
    # Wave B made the matrix the PLANNER's, so the list of indices is no longer
    # in this file — `--pack-count 12` below is now the only place the twelve-way
    # partition is written down, and run_ci_pack.py always emits exactly that
    # many packs (tests/test_ci_pack.py::test_plan_keeps_the_fixed_twelve_pack_assignment).
    matrix = pack["strategy"]["matrix"]
    if isinstance(matrix, str):
        assert "fromJSON(needs.ci-plan.outputs.matrix)" in " ".join(matrix.split())
    else:
        static = matrix["pack"]
        assert static == list(range(len(static)))
        assert len(static) == 12
    # EVERY event runs on the hosted pool — one `runs-on`, no event-dependent routing,
    # so main's baseline and a pull request prove the packs the SAME way.
    #
    # This replaces the 2026-08-09 self-hosted detour. Main's proof was briefly routed
    # to `["self-hosted","render-linux"]` because it sat `queued` 30+ minutes behind 133
    # queued runs while that pool idled, and a starved main proof blocks the whole fleet
    # (`merge_on_green.main_proof` reads the newest CONCLUDED ci.yml run on main, so
    # without one the base-inherited-red refresh cannot fire). The repository then moved
    # to the MastermindX enterprise org and hosted capacity became large enough to start
    # all twelve packs together. There is nothing left to escape, and the detour cost
    # more than it saved: `render-linux` is FOUR runners shared with render.yml,
    # engine-render.yml and merge-on-green.yml, so even four packs took the entire pool
    # and starved the sweeper that merges every armed pull request.
    assert pack["runs-on"] == "ubuntu-latest"
    # The self-hosted pools are the render/nightly lanes and must never absorb CI packs.
    runs_on = " ".join(str(pack["runs-on"]).split())
    assert "macstudio" not in runs_on
    assert "render-linux" not in runs_on
    assert "self-hosted" not in runs_on
    assert pack["strategy"]["fail-fast"] is False
    # No `max-parallel`: it existed only to stop main's packs from taking all four
    # `render-linux` runners. With no shared pool to protect, throttling would only
    # double main's proof (~26 min -> ~50 min), and it cannot help against the hosted
    # ceiling because that limit is ACCOUNT-wide, not per-matrix.
    assert "max-parallel" not in pack["strategy"], (
        "reintroducing max-parallel only slows main's proof; the hosted concurrency "
        "ceiling is account-wide and this key cannot raise it"
    )
    # The closed-event fence must LEAD the condition. Wave B appends
    # `&& needs.ci-plan.outputs.has_work == 'true'`; anything that replaces the
    # fence instead of extending it re-allocates a runner for every merged-close.
    assert pack["if"].startswith("github.event.action != 'closed'")
    run_text = "\n".join(
        str(step.get("run", "")) for step in pack["steps"] if isinstance(step, dict)
    )
    assert "--workflow .github/ci/legacy-jobs.yml" in run_text
    assert "--pack-count 12" in run_text

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
    assert set(jobs) == {
        "fence-pack",
        "fork-self-mod-fence",
        "fork-capability-broker",
        "fork-grader-manifest",
    }
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
        assert fallback["runs-on"] == "ubuntu-latest"
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
