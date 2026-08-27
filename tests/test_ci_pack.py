from __future__ import annotations

import ast
import errno
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest

from scripts import audit_unrun_tests as AUDIT
from scripts import ci_scope_dependencies as DEPS
from scripts.ci_scope_dependencies import suite_dependency_closure
# Plain package import (not the importlib-from-path PACK below) so this test and
# scripts/check_contract_delta.py's own import of the same names resolve to the
# identical `scripts.run_ci_pack` module object — see
# test_curated_exclusive_closure_findings_is_the_shared_implementation in
# tests/test_contract_delta.py, which pins that identity.
from scripts.run_ci_pack import (
    curated_exclusive_closure_findings,
    inferred_as_if_not_exclusive,
)
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


def _closure_of(source: str) -> SimpleNamespace:
    """Classify a synthetic module the way the selector classifies a real one.

    ``_source_ambiguities`` reads the parsed tree and uses the path only to label
    findings, so a probe needs no file on disk — and must not leave one behind in
    a checkout the pack runner hard-resets between jobs.
    """
    import ast

    from scripts import ci_scope_dependencies as DEPS

    findings = DEPS._source_ambiguities(
        ROOT / "engine" / "_ci_scope_probe.py", ast.parse(source)
    )
    return SimpleNamespace(ambiguities=tuple(sorted(findings)))


def test_all_legacy_jobs_are_disabled_and_packable() -> None:
    jobs = PACK.load_legacy_jobs(MANIFEST)
    assert len(jobs) >= 86
    assert all(job.definition["if"] == PACK.DISABLED_IF for job in jobs)


def test_every_real_legacy_job_declares_its_gate() -> None:
    """Every job in the real manifest says which tree moves its verdict.

    The loader defaults an ABSENT `gate:` to "code" so synthetic fixtures keep
    working (and so nothing can leave the merge gate silently), but the real
    manifest must declare the field on every job: the code/data split is the
    W1 deliverable of research/CI_MERGE_GATE_RELIABILITY_ROOT_CAUSE_2026_08_19.md
    and an undeclared job is an unclassified one, not a classified-by-default
    one.
    """
    jobs = PACK.load_legacy_jobs(MANIFEST)
    undeclared = sorted(job.job_id for job in jobs if "gate" not in job.definition)
    assert not undeclared, (
        "legacy jobs without an explicit gate declaration: "
        + ", ".join(undeclared)
    )
    assert all(job.gate in PACK.GATE_VALUES for job in jobs)


def test_invalid_gate_value_fails_closed(tmp_path: Path) -> None:
    workflow = tmp_path / "ci.yml"
    workflow.write_text(
        """
jobs:
  ci-pack:
    runs-on: ubuntu-latest
    steps:
      - run: echo pack
  typo:
    if: ${{ false }}
    runs-on: ubuntu-latest
    gate: dtaa
    steps:
      - run: echo typo
"""
    )
    with pytest.raises(PACK.ManifestError, match="gate must be one of code/data"):
        PACK.load_legacy_jobs(workflow)


def test_absent_gate_defaults_to_code_never_data(tmp_path: Path) -> None:
    """An undeclared job stays a merge precondition — fail-closed direction."""
    workflow = tmp_path / "ci.yml"
    workflow.write_text(
        """
jobs:
  ci-pack:
    runs-on: ubuntu-latest
    steps:
      - run: echo pack
  bare:
    if: ${{ false }}
    runs-on: ubuntu-latest
    steps:
      - name: bare step
        proof_id: bare-step
        run: echo bare
"""
    )
    (job,) = PACK.load_legacy_jobs(workflow)
    assert job.gate == "code"


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
      - name: create the leak fixture
        run: printf leak > leaked.tmp
  second:
    if: ${{ false }}
    runs-on: ubuntu-latest
    steps:
      - name: prove the checkout was restored
        run: test ! -e leaked.tmp
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
    assert ci["concurrency"]["group"] == (
        "ci-${{ github.event.pull_request.number || github.ref }}"
    )
    triggers = ci.get("on") or ci.get(True)
    assert triggers["pull_request"]["types"] == [
        "opened", "synchronize", "reopened"
    ], "a closed event must never occupy or replace the active PR proof slot"
    assert "merged" not in ci["concurrency"]["group"]
    assert "github.event.action" not in ci["concurrency"]["group"]


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
    """Unknown changed-sets and global invalidators still widen; unowned paths do not.

    A wasted runner-minute is cheap; a false green on a control-plane file is
    not. The two remaining wideners are the only ways scoping can be unknowable
    rather than merely unowned. An unowned path used to be a third widener and
    that was the speed hole: one hook file ran all 185 jobs (PR #5488).
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
    # 3. an unowned path stays on always-on fences; it does not mint a full suite
    selected, reason = PACK.select_jobs(jobs, ["no/such/path/at/all.txt"])
    assert len(selected) < len(jobs), reason
    assert "did not widen" in reason
    # `is_scoped`, not `paths`: after the #5586 tier split a job can be scoped
    # entirely by opaque `fallback_paths`, and such a job is NOT always-on.
    unscoped = [job for job in jobs if not job.is_scoped]
    for job in unscoped:
        assert job in selected, f"always-on {job.job_id} must still run"
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
    assert "unrun-dark-guards" in scoped
    assert ".claude/hooks/gh_quota_guard.py" in scoped["unrun-dark-guards"]


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


def _declared_scan_dirs(rel: str) -> tuple[str, ...]:
    """The `SCAN_DIRS` literal a scanner suite declares, read without importing it.

    Parsed rather than imported so this stays a statement about the scanner's
    own source. The selector derives its roots from `CODE_SCAN_ROOTS`, so the
    two sides remain independent evidence and a root added to one but not
    reachable by the other is a real finding, not a tautology.
    """
    tree = ast.parse((ROOT / rel).read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "SCAN_DIRS"
            for target in node.targets
        ):
            return tuple(ast.literal_eval(node.value))
    raise AssertionError(f"{rel} no longer declares SCAN_DIRS at module level")


def test_whole_tree_glob_job_owns_every_scanned_code_root() -> None:
    """A tree scan cannot be narrowed to the scanner suite's import closure.

    `all-exports-resolve` AST-walks every `*.py` under eight directories, so a
    scope narrower than those roots is a guard that stops running on exactly the
    pull requests that can break it, and reports green forever.

    The roots reach the job on the OPAQUE tier: an `rglob("*.py")` is the
    textbook `fallback_paths` claim (#5586 split provenance out of `paths`).
    Reading `paths` alone reported the tier split ITSELF as the narrowing —
    after the split that field holds `tests/test_all_exports_resolve.py` and
    nothing else, which is precisely the scanner suite's own import closure
    this test is named for.

    The tier is also observable behavior, not merely an explanation: owned
    paths match before passive-file suppression, while fallback paths must not
    select narrative Markdown. Pin both the executable selection and the
    passive-file exclusion so a later refactor cannot silently undo #5586.
    """
    scan_dirs = _declared_scan_dirs("tests/test_all_exports_resolve.py")
    assert len(scan_dirs) >= 8, scan_dirs
    jobs, _ = PACK.infer_job_scopes(PACK.load_legacy_jobs(MANIFEST))
    export_guard = next(job for job in jobs if job.job_id == "all-exports-resolve")
    surface = export_guard.paths + export_guard.fallback_paths
    missing = [f"{root}/**" for root in scan_dirs if f"{root}/**" not in surface]
    assert not missing, (
        f"all-exports-resolve scans {missing} but no scope pattern claims them: "
        f"{surface}"
    )

    # Membership is not selection: a pattern nothing matches is a scope that
    # reads correct and runs never. A NEW module under a scanned root is the
    # case that matters most — that is where an unbound `__all__` name is born.
    for root in scan_dirs:
        assert f"{root}/**" in export_guard.fallback_paths
        probe = f"{root}/__whole_tree_probe__.py"
        assert PACK._job_diff_match(export_guard, [probe]) == (probe, "fallback")
        selected, reason = PACK.select_jobs(jobs, [probe])
        assert export_guard in selected, (probe, reason)
        narrative_probe = f"{root}/__whole_tree_probe__.md"
        assert PACK._job_diff_match(export_guard, [narrative_probe]) is None

    # And the probe that pins non-vacuity: an existing file OUTSIDE the scanner
    # suite's dependency closure, i.e. one the narrowed scope would have lost.
    closure = suite_dependency_closure("tests/test_all_exports_resolve.py").files
    assert "engine/market_state.py" not in closure
    selected, reason = PACK.select_jobs(jobs, ["engine/market_state.py"])
    assert export_guard in selected, reason


def test_a_glob_pattern_bounds_the_file_kinds_its_scan_can_reach() -> None:
    """`d.glob("*.parquet")` cannot be changed by a `.json` or `.py` edit.

    The classifier used to read a traversal's pattern only to pick a root SET and
    then claim every file under those roots.  Measured across the 181-job manifest
    on 2026-08-11, that is what handed `data/**` to 90 jobs off one parquet scan in
    a hub module and pinned the narrow-diff contract at exactly zero headroom.

    The narrowing is a strict subset, never a new claim: every path
    `data/**/*.parquet` matches, `data/**` already matched.
    """
    narrowed = PACK.narrow_to_suffixes(("data/**", "site/**", "*"), (".parquet",))
    assert "data/**/*.parquet" in narrowed
    assert "site/**/*.parquet" in narrowed
    assert "*.parquet" in narrowed
    assert "data/**" not in narrowed
    # pyarrow writes partitioned datasets as `x.parquet/part-0.parquet`, so the
    # subtree under a matched entry keeps its owner.
    assert "data/**/*.parquet/**" in narrowed
    for covered in ("data/x.parquet", "data/a/b/x.parquet", "data/a/x.parquet/p.json"):
        assert PACK._matches_any(narrowed, covered), covered
        assert PACK._matches_any(("data/**",), covered), covered
    for outside in ("data/cycle_ontology/falsifiers.json", "data/a/b.py"):
        assert not PACK._matches_any(narrowed, outside), outside
    # No suffix evidence means no narrowing at all.
    assert PACK.narrow_to_suffixes(("data/**",), ()) == ("data/**",)


def test_exclude_peer_test_ownership_drops_catch_alls_keeps_fixtures() -> None:
    """Named pytest jobs must not own every tests/*.py edit via opaque globs."""
    filtered = PACK.exclude_peer_test_ownership(
        (
            "*",
            "*.py",
            "tests/**",
            "tests/**/*.py",
            "tests/**/*.py/**",
            "tests/**/*.json",
            "research/**",
            "docs/**",
            "content/**",
            "research/**/*.md",
            "engine/**",
            "tests/test_foo.py",
        )
    )
    assert "*" not in filtered
    assert "tests/**" not in filtered
    assert "tests/**/*.py" not in filtered
    assert "docs/**" not in filtered
    assert "content/**" not in filtered
    assert "research/**" in filtered
    assert "tests/**/*.json" in filtered
    assert "research/**/*.md" in filtered
    assert "engine/**" in filtered
    assert "tests/test_foo.py" in filtered


def test_resolve_changed_files_prefers_planner_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Packs must not git-diff a shallow clone when ci-plan already listed the files."""
    monkeypatch.setattr(
        PACK, "changed_files", lambda base: (_ for _ in ()).throw(AssertionError("git"))
    )
    assert PACK.resolve_changed_files(
        "abc123", explicit_json='["tests/test_foo.py","engine/bar.py"]'
    ) == ["tests/test_foo.py", "engine/bar.py"]
    assert PACK.resolve_changed_files("abc123", explicit_json="null") is None
    assert PACK.resolve_changed_files("abc123", explicit_json="not-json") is None
    monkeypatch.setenv("CI_CHANGED_FILES_JSON", '["app/x.py"]')
    assert PACK.resolve_changed_files("abc123") == ["app/x.py"]
    monkeypatch.delenv("CI_CHANGED_FILES_JSON")
    monkeypatch.setattr(PACK, "changed_files", lambda base: ["from-git.py"])
    assert PACK.resolve_changed_files("abc123") == ["from-git.py"]
    assert PACK.resolve_changed_files(None) is None


# ─── The 2026-08-14 E2BIG transport regression (run 31775693780) ──────────────
#
# PR #5578 carried a handful of files, and every one of its twelve packs died
# before executing a single test:
#
#     An error occurred trying to start process '/usr/bin/bash' ...
#     Argument list too long
#
# The chain: ci-plan diffed against the PR's opening base SHA; by run time main
# had advanced 45 commits and 8,581 distinct paths through the nightly bake
# window; the whole drift was attributed to the PR; and the resulting list rode
# a job output into the pack step's `env:` as CI_CHANGED_FILES_JSON — 350,264
# measured bytes against Linux's 131,072-byte MAX_ARG_STRLEN, the per-STRING cap
# execve applies before any program runs.
#
# These tests pin the TRANSPORT — the property that the list's size stops
# mattering — and the first one is the mutation proof: it fires a real execve at
# a population no environment can hold.

_E2BIG_MIN_JSON_BYTES = 2_000_000

# The child proves three things at once, in one real process: the giant env
# string did not follow it through execve, the file transport did, and the paths
# survived byte-exact across the boundary.
_E2BIG_CHILD = """
import json, os, sys
assert "CI_CHANGED_FILES_JSON" not in os.environ, "the inline list reached a child"
with open(os.environ["CI_CHANGED_FILES_FILE"], encoding="utf-8") as handle:
    paths = json.load(handle)
assert len(paths) == int(sys.argv[1]), (len(paths), sys.argv[1])
assert paths[7] == sys.argv[2], (paths[7], sys.argv[2])
"""


def _e2big_population() -> list[str]:
    """A changed-file list no process environment can carry.

    Deliberately unpleasant, because the transport has to be indifferent to it:
    spaces, an em dash, Han characters and a Greek letter — the shapes a naive
    shell round-trip mangles — over enough volume to clear BOTH caps this suite
    fires against (Linux's 131,072-byte per-string MAX_ARG_STRLEN and macOS's
    ~1 MiB total ARG_MAX). The incident itself needed only 350,264 bytes; the
    margin keeps the proof honest on either kernel.
    """
    return [
        f"data/研究/{index:05d}/sector-rotation-quarterly-snapshot/"
        f"季度报告 {index} α — final draft.parquet"
        for index in range(18_000)
    ]


@pytest.mark.skipif(sys.platform == "win32", reason="execve argument caps are POSIX")
def test_a_large_changed_file_list_cannot_cross_a_process_environment() -> None:
    """The launch failure itself, reproduced — this is what must never be wired.

    Not a hypothetical: it is `subprocess.run` refusing to start a process that
    does nothing, purely because one environment string is too long. Every
    legacy step in a pack is exactly this call shape (`bash -eo pipefail -c`),
    which is why all twelve packs reported a bash startup error rather than a
    test failure.
    """
    population = _e2big_population()
    assert len(population) >= 12_000
    giant = json.dumps(population, separators=(",", ":"))
    assert len(giant.encode("utf-8")) > _E2BIG_MIN_JSON_BYTES
    with pytest.raises(OSError) as caught:
        subprocess.run(
            [sys.executable, "-c", "pass"],
            env={**os.environ, "CI_CHANGED_FILES_JSON": giant},
            check=True,
        )
    assert caught.value.errno == errno.E2BIG, (
        f"expected E2BIG, got errno {caught.value.errno}: {caught.value}"
    )


@pytest.mark.skipif(sys.platform == "win32", reason="execve argument caps are POSIX")
def test_the_file_transport_carries_the_list_that_e2bigs_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same population, same paths, byte for byte — and a child that launches.

    Three legs, in the order the production chain runs them: the planner
    resolving from a file must reach the identical plan it would reach from an
    in-memory list; `--emit-changed-files` must round-trip the array back out
    byte-exact; and a real child spawned through `_dependency_environment` must
    START, with the inline name absent from its environ and the file carrying
    the full count.

    The last leg is the mutation detector for `_child_environment`: the inline
    string is planted in `os.environ` at a size no execve accepts, so a child
    spawned from an environment that still forwards it CANNOT start. Drop the
    pop and this test does not merely fail an equality check — it reproduces the
    incident.
    """
    population = _e2big_population()
    handle = tmp_path / "changed-files.json"
    handle.write_text(
        json.dumps(population, separators=(",", ":")), encoding="utf-8"
    )
    monkeypatch.setenv("CI_CHANGED_FILES_FILE", str(handle))
    resolved = PACK.resolve_changed_files("stale-base-sha")
    assert resolved == population, "the file transport must not reshape the list"

    _freeze_scope_inference(monkeypatch)
    jobs = [
        _plan_job("data-owner", 0, paths=("data/**",)),
        _plan_job("engine-owner", 1, paths=("engine/**",)),
    ]
    from_file = PACK.build_plan(
        jobs, resolved, changed_from="stale-base-sha", scope_mode="active",
        pack_count=12,
    )
    in_memory = PACK.build_plan(
        jobs, population, changed_from="stale-base-sha", scope_mode="active",
        pack_count=12,
    )
    assert from_file.plan_sha256 == in_memory.plan_sha256
    assert from_file.changed_files_sha256 == in_memory.changed_files_sha256
    assert from_file.changed_files_count == len(population)
    assert from_file.eligible_job_ids == in_memory.eligible_job_ids

    # The artifact this planner publishes must be readable back as the same
    # list — a reshaped array would hash to something else and refuse the plan.
    republished = tmp_path / "published" / "changed-files.json"
    PACK._write_changed_files_artifact(republished, from_file.changed_paths)
    assert json.loads(republished.read_text(encoding="utf-8")) == population

    monkeypatch.setenv(
        "CI_CHANGED_FILES_JSON", json.dumps(population, separators=(",", ":"))
    )
    command_env = PACK._dependency_environment(None)
    assert "CI_CHANGED_FILES_JSON" not in command_env
    assert command_env["CI_CHANGED_FILES_FILE"] == str(handle)
    completed = subprocess.run(
        [sys.executable, "-c", _E2BIG_CHILD, str(len(population)), population[7]],
        env=command_env,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, (
        f"a legacy step could not launch with the list present as a file: "
        f"{completed.stderr}"
    )


def test_a_stale_comparison_base_never_smears_mains_paths_into_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other half of the 2026-08-14 chain: git must not be consulted at all.

    PR #5578's planner diffed an immutable base SHA that main had left 45
    commits behind, so `git diff` answered with 8,581 paths of somebody else's
    nightly bake. The published list is the ONLY authority — when a handle is
    configured, a stale `--changed-from` must not reach git even as a fallback,
    because the answer it would give is the incident.
    """
    handle = tmp_path / "changed-files.json"
    handle.write_text('["engine/example.py","tests/test_foo.py"]', encoding="utf-8")
    monkeypatch.setenv("CI_CHANGED_FILES_FILE", str(handle))
    monkeypatch.setattr(
        PACK,
        "changed_files",
        lambda base: (_ for _ in ()).throw(AssertionError(f"git diff {base}")),
    )
    assert PACK.resolve_changed_files("2ca4718") == [
        "engine/example.py", "tests/test_foo.py"
    ]
    # The file also out-ranks a contradicting inline string, so a stale env value
    # cannot out-vote the artifact the pack downloaded.
    monkeypatch.setenv("CI_CHANGED_FILES_JSON", '["site/decoy.html"]')
    assert PACK.resolve_changed_files("2ca4718") == [
        "engine/example.py", "tests/test_foo.py"
    ]
    # An unreadable handle widens; it must NOT fall through to that same git.
    monkeypatch.setenv("CI_CHANGED_FILES_FILE", str(tmp_path / "never-written.json"))
    assert PACK.resolve_changed_files("2ca4718") is None
    # And the explicit flag out-ranks both names, so a local reproduction can
    # replay a published list without touching the ambient environment.
    assert PACK.resolve_changed_files("2ca4718", explicit_file=handle) == [
        "engine/example.py", "tests/test_foo.py"
    ]


def test_changed_files_digest_is_an_affirmative_no_list_or_an_ordered_hash() -> None:
    """"" is not a hash — it is the encoding of "the planner had no list".

    That distinction is the whole reason a pack can tell "planned the full
    suite" from "planned this exact diff" without a second flag, and order is
    load-bearing because two transports that sorted differently would hash the
    same list to two values and refuse every plan.
    """
    assert PACK.changed_files_digest(None) == ""
    ordered = PACK.changed_files_digest(["b.py", "a.py"])
    assert len(ordered) == 64 and ordered != ""
    assert PACK.changed_files_digest(["a.py", "b.py"]) != ordered
    assert PACK.changed_files_digest(("b.py", "a.py")) == ordered


@pytest.mark.parametrize(
    ("body", "state", "count"),
    [
        ('["a.py","b.md"]', "list", 2),
        ("null", "null", 0),
        ('["", ""]', "null", 0),
        ("{nope", "malformed", 0),
        ("", "malformed", 0),
        ('"one string"', "malformed", 0),
        ("[1]", "malformed", 0),
    ],
)
def test_changed_files_handle_states_are_named_not_merely_falsy(
    tmp_path: Path, body: str, state: str, count: int
) -> None:
    """A pack that refuses has to say WHICH way the handle was wrong.

    `resolve_changed_files` only widens, which is right for the decision and
    useless for the diagnosis: since 2026-08-14 the most likely cause of a
    plan-sha parity failure is this file, not the manifest, so the annotation
    that accompanies the refusal names the state.
    """
    handle = tmp_path / "changed-files.json"
    handle.write_text(body, encoding="utf-8")
    got_state, paths = PACK._read_changed_files_handle(str(handle))
    assert (got_state, len(paths)) == (state, count)
    assert PACK._read_changed_files_handle(None) == ("absent", [])
    assert PACK._read_changed_files_handle(str(tmp_path / "gone.json")) == (
        "unreadable", []
    )


def test_plan_publishes_changed_paths_for_pack_shallow_checkout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _freeze_scope_inference(monkeypatch)
    jobs = [_plan_job("owner", 0, paths=("tests/test_foo.py",))]
    plan = PACK.build_plan(
        jobs,
        ["tests/test_foo.py"],
        changed_from="base-sha",
        scope_mode="active",
        pack_count=12,
    )
    assert plan.changed_paths == ("tests/test_foo.py",)
    assert plan.nonempty_pack_indices == (0,)


def test_traversal_pattern_evidence_is_read_only_when_it_is_literal() -> None:
    """An unreadable or unlisted pattern keeps the full root claim."""
    closure = _closure_of(
        "from pathlib import Path\n"
        "import config\n"
        "def a(pattern):\n"
        "    return list((config.data_dir() / 'x').glob(pattern))\n"
        "def b():\n"
        "    return list((config.data_dir() / 'x').glob('*.parquet'))\n"
        "def c():\n"
        "    return list((config.data_dir() / 'x').glob('*.unlisted'))\n"
        "def d():\n"
        "    return list((config.data_dir() / 'x').iterdir())\n"
        "def e():\n"
        "    return list((config.data_dir() / 'x').glob('v1.2'))\n"
    )
    kinds = {int(item.split(":")[1]): item for item in closure.ambiguities}
    # a: runtime pattern; c: suffix outside the closed vocabulary; d: iterdir has
    # no pattern; e: a FIXED name that may well be a directory whose contents
    # would then lose their owner.  All four keep the unnarrowed claim.
    for line in (4, 8, 10, 12):
        assert " suffixes=" not in kinds[line], kinds[line]
    assert kinds[6].endswith(" suffixes=.parquet"), kinds[6]


def test_a_module_local_walk_is_not_a_filesystem_traversal() -> None:
    """`walk()` over a JSON document is not `os.walk` over the repository.

    `engine/sector_intelligence/contracts.py` defines a recursive document
    `walk()`; the label-only classifier read all five call sites as tree scans and
    charged four repository roots to the 35 jobs that import it.
    """
    document = _closure_of(
        "def walk(value, path):\n"
        "    if isinstance(value, dict):\n"
        "        for key, nested in value.items():\n"
        "            walk(nested, (*path, key))\n"
        "def check(document):\n"
        "    walk(document, ())\n"
    )
    assert not document.ambiguities, document.ambiguities
    # An imported os.walk with the same name is still a traversal.
    imported = _closure_of(
        "from os import walk\n"
        "def scan(root):\n"
        "    return list(walk(root))\n"
    )
    assert any("filesystem" in item for item in imported.ambiguities)


def test_a_code_suffix_must_end_a_filename_not_merely_appear_in_one() -> None:
    """`.js` inside `*.json` promoted artifact scans to whole-tree code scans.

    A json-only traversal claimed every Python file in eleven code roots because
    the classifier used a substring test.
    """
    artifact = _closure_of(
        "def scan(root):\n"
        "    return list(root.glob('*.json'))\n"
    )
    assert any("artifact traversal" in item for item in artifact.ambiguities)
    assert not any("code traversal" in item for item in artifact.ambiguities)
    code = _closure_of(
        "def scan(root):\n"
        "    return list(root.rglob('*.py'))\n"
    )
    assert any("code traversal" in item for item in code.ambiguities)


def test_derived_scopes_are_startable_by_the_ci_workflow() -> None:
    """A job owner is useless when its dependency edit cannot start ci.yml.

    BOTH tiers are audited. #5586 split the PROVENANCE of a claim out of
    `paths` and into `fallback_paths`; it did not split the selection, so an
    opaque root ci.yml cannot start is the same silent hole in a different
    field — the planner picks the job and the run never begins.

    Measured on the manifest that shipped the split: zero gaps on either tier,
    so reading both is a restoration of dropped coverage, not a relaxation —
    but 289 of the 327 fallback patterns appear in NO job's `paths`, and
    dropping `ops/**` from ci.yml's triggers opens 448 gaps that the
    `paths`-only form still reports as zero.
    """
    jobs, _ = PACK.infer_job_scopes(PACK.load_legacy_jobs(MANIFEST))
    on = _yaml(WORKFLOW).get("on") or _yaml(WORKFLOW).get(True)
    triggers = tuple(on["pull_request"]["paths"])
    gaps: list[tuple[str, str]] = []
    for job in jobs:
        for path in job.paths + job.fallback_paths:
            if any(char in path for char in "*?"):
                if not PACK.scope_pattern_is_startable(path, triggers):
                    gaps.append((job.job_id, path))
            elif not PACK._matches_any(triggers, path):
                gaps.append((job.job_id, path))
    assert not gaps, gaps[:25]


def test_startability_accepts_only_provable_narrowings_of_a_trigger() -> None:
    """A derived scope may skip the trigger list only when a parent covers it.

    Literal membership used to be the whole rule, which forced one ci.yml entry
    per derived pattern.  With suffix- and subtree-narrowed scopes that vocabulary
    is open-ended, and a missing entry would red an unrelated pull request the
    first time any module globbed a new extension.  The replacement is a
    containment PROOF, not a relaxation: `data/**/*.parquet` and
    `data/smart_money/**` each match a strict subset of `data/**`, so an edit that
    reaches the job always starts the run.  A tree no trigger covers still fails.
    """
    triggers = ("data/**", "engine/**", "*", "config/dag.yml")
    for covered in (
        "data/**",                      # literal member
        "data/**/*.parquet",            # suffix-narrowed child of data/**
        "data/**/*.parquet/**",         # its directory-subtree companion
        "data/smart_money/**",          # subtree-narrowed child of data/**
        "data/a/b/c/**",                # deeper subtree
        "*.json",                       # repository-root form, `*` is a trigger
        "engine/*",                     # single-level subset of engine/**
    ):
        assert PACK.scope_pattern_is_startable(covered, triggers), covered
    for uncovered in (
        "brand_new_root/**",            # no ancestor is a trigger
        "brand_new_root/**/*.json",     # narrowing an untriggerable tree
        "brand_new_root/deep/**",
        "site/**",                      # a real root that this filter omits
        "app/*",                        # single-level, but app/** is not a trigger
    ):
        assert not PACK.scope_pattern_is_startable(uncovered, triggers), uncovered


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


def test_a_named_suite_edit_does_not_select_peer_pytest_jobs() -> None:
    """PR #5550 shape: one prophet test file used to mint 133/187 jobs and 12 packs.

    unrun-market-plumbing names tests/test_prophet_w1_intake_repair.py. marketing-engine
    and engine-render-guards do not. After exclude_peer_test_ownership they must not
    run for this diff, and the matrix must not be the full twelve.
    """
    jobs, _ = PACK.infer_job_scopes(PACK.load_legacy_jobs(MANIFEST))
    changed = ["tests/test_prophet_w1_intake_repair.py"]
    selected, reason = PACK.select_jobs(jobs, changed)
    ids = {job.job_id for job in selected}
    assert "unrun-market-plumbing" in ids, reason
    assert "marketing-engine" not in ids, reason
    assert "engine-render-guards" not in ids, reason
    assert "full suite" not in reason, reason
    assert len(selected) <= len(jobs) // 4, (len(selected), len(jobs), reason)
    packs = PACK.partition_jobs(selected, 12)
    nonempty = [index for index, pack in enumerate(packs) if pack]
    assert len(nonempty) < 12, nonempty


def test_unscoped_hook_diff_does_not_pull_the_full_suite() -> None:
    """PR #5488 shape: `.claude/hooks/gh_quota_guard.py` used to mint 187/187 jobs.

    CI_SCOPE_MODE is already active in ci.yml unless the repo var is exactly
    ``off``. The remaining hole was select_jobs treating an unowned path as a
    full-suite invalidator. After this PR the hook is owned by unrun-dark-guards
    and an unowned sibling still does not widen.
    """
    jobs, _ = PACK.infer_job_scopes(PACK.load_legacy_jobs(MANIFEST))
    selected, reason = PACK.select_jobs(
        jobs, [".claude/hooks/gh_quota_guard.py"]
    )
    assert "full suite" not in reason, reason
    assert len(selected) < len(jobs) * 4 // 5, (len(selected), len(jobs), reason)
    assert any(job.job_id == "unrun-dark-guards" for job in selected)
    mixed, mixed_reason = PACK.select_jobs(
        jobs,
        [".claude/hooks/gh_quota_guard.py", "engine/spine.py"],
    )
    assert "full suite" not in mixed_reason, mixed_reason
    assert len(mixed) < len(jobs), mixed_reason


@pytest.mark.parametrize("graph", ["config/dag.yml", "config/synapse.yml"])
def test_graph_metadata_is_a_global_invalidator(graph: str) -> None:
    jobs, _ = PACK.infer_job_scopes(PACK.load_legacy_jobs(MANIFEST))
    selected, reason = PACK.select_jobs(jobs, [graph])
    assert len(selected) == len(jobs)
    assert "global invalidator" in reason


def test_passive_markdown_stays_scoped_and_unknown_root_does_not_widen() -> None:
    jobs, _ = PACK.infer_job_scopes(PACK.load_legacy_jobs(MANIFEST))
    docs, _ = PACK.select_jobs(jobs, ["research/UNOWNED_HANDOFF.md"])
    code, reason = PACK.select_jobs(jobs, ["brand_new_root/unowned_runtime.xyz"])
    assert len(docs) < len(jobs)
    assert len(code) < len(jobs)
    assert "did not widen" in reason
    unscoped = [job for job in jobs if not job.is_scoped]
    assert {job.job_id for job in unscoped} <= {job.job_id for job in code}


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


def _git_in(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=check,
        capture_output=True,
        text=True,
    )


def _commit_fixture(repo: Path, message: str) -> str:
    _git_in(repo, "add", "-A")
    _git_in(repo, "commit", "-m", message)
    return _git_in(repo, "rev-parse", "HEAD").stdout.strip()


def _seed_tracked_path_repo(tmp_path: Path) -> tuple[Path, str, Path]:
    repo = tmp_path / "tracked-path-repo"
    repo.mkdir()
    _git_in(repo, "init", "-b", "main")
    _git_in(repo, "config", "user.email", "ci@example.invalid")
    _git_in(repo, "config", "user.name", "CI Fixture")
    for directory in ("engine", "tests", "site", "data"):
        (repo / directory).mkdir()
    (repo / "engine" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "engine" / "core.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repo / "tests" / "test_owner.py").write_text(
        "from pathlib import Path\n"
        "from engine import core\n\n"
        "def test_owner():\n"
        "    assert core.VALUE and Path('site/owner.json').read_text()\n",
        encoding="utf-8",
    )
    (repo / "tests" / "test_opaque.py").write_text(
        "from pathlib import Path\n\n"
        "def test_opaque():\n"
        "    assert list(Path('data').rglob('*.json'))\n",
        encoding="utf-8",
    )
    (repo / "site" / "owner.json").write_text('{"owner":true}\n', encoding="utf-8")
    (repo / "site" / "old.json").write_text('{"old":true}\n', encoding="utf-8")
    (repo / "site" / "omitted.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repo / "data" / "feed.json").write_text("[]\n", encoding="utf-8")
    sha = _commit_fixture(repo, "seed exact tree")
    inventory = tmp_path / "tracked-paths.v1"
    DEPS.write_tracked_path_inventory(inventory, sha, root=repo)
    return repo, sha, inventory


def test_depth_two_merge_needs_no_parent1_parent2_merge_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The authoritative diff is parent1...merge, not parent1...parent2.

    A depth-two checkout has the exact synthetic merge and both direct parents,
    but their common ancestor is deliberately outside the shallow boundary. The
    current planner diff still resolves exactly; progressive ancestry acquisition
    (the rejected #6261 design) is neither called nor needed.
    """
    source = tmp_path / "source"
    source.mkdir()
    _git_in(source, "init", "-b", "main")
    _git_in(source, "config", "user.email", "ci@example.invalid")
    _git_in(source, "config", "user.name", "CI Fixture")
    (source / "base.txt").write_text("base\n", encoding="utf-8")
    _commit_fixture(source, "base")
    _git_in(source, "switch", "-c", "feature")
    (source / "tests").mkdir()
    (source / "tests" / "feature.py").write_text("FEATURE = True\n", encoding="utf-8")
    _commit_fixture(source, "feature")
    _git_in(source, "switch", "main")
    (source / "engine").mkdir()
    (source / "engine" / "main.py").write_text("MAIN = True\n", encoding="utf-8")
    _commit_fixture(source, "main")
    _git_in(source, "merge", "--no-ff", "feature", "-m", "synthetic merge")
    _git_in(source, "branch", "candidate", "HEAD")

    shallow = tmp_path / "depth-two"
    subprocess.run(
        [
            "git", "clone", "--depth", "2", "--branch", "candidate",
            f"file://{source}", str(shallow),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    fields = _git_in(shallow, "rev-list", "--parents", "-n", "1", "HEAD").stdout.split()
    assert len(fields) == 3
    merge_sha, parent1, parent2 = fields
    assert _git_in(shallow, "rev-parse", "HEAD").stdout.strip() == merge_sha
    assert _git_in(shallow, "merge-base", parent1, parent2, check=False).returncode == 1
    assert _git_in(shallow, "merge-base", parent1, "HEAD").stdout.strip() == parent1

    monkeypatch.chdir(shallow)
    assert PACK.changed_files(parent1) == ["tests/feature.py"]


def test_exact_tree_inventory_rejects_missing_malformed_wrong_and_mutated_inputs(
    tmp_path: Path,
) -> None:
    repo, sha, inventory = _seed_tracked_path_repo(tmp_path)
    loaded = DEPS.load_tracked_path_inventory(inventory, sha, root=repo)
    assert loaded.tested_tree_sha == sha
    assert "site/owner.json" in loaded.files
    assert "site" in loaded.directories

    with pytest.raises(DEPS.TrackedPathInventoryError, match="unreadable"):
        DEPS.load_tracked_path_inventory(tmp_path / "missing.v1", sha, root=repo)

    malformed = tmp_path / "malformed.v1"
    malformed.write_bytes(b"not-json\nsite/owner.json\0")
    with pytest.raises(DEPS.TrackedPathInventoryError, match="header is malformed"):
        DEPS.load_tracked_path_inventory(malformed, sha, root=repo)

    header_raw, _, payload = inventory.read_bytes().partition(b"\n")
    header = json.loads(header_raw)
    wrong_tree = tmp_path / "wrong-tree.v1"
    wrong_header = {**header, "tested_tree_sha": "0" * 40}
    wrong_tree.write_bytes(
        json.dumps(wrong_header, sort_keys=True, separators=(",", ":")).encode()
        + b"\n"
        + payload
    )
    with pytest.raises(DEPS.TrackedPathInventoryError, match="does not match expected"):
        DEPS.load_tracked_path_inventory(wrong_tree, sha, root=repo)

    # Remove a real tracked path AND repair the mutation's own count/digest. The
    # independent exact-tree comparison must still catch this, rather than
    # trusting self-consistent but incomplete metadata.
    records = payload[:-1].split(b"\0")
    records.remove(b"site/owner.json")
    truncated_payload = b"\0".join(records) + b"\0"
    truncated_header = {
        **header,
        "path_count": len(records),
        "paths_sha256": DEPS.hashlib.sha256(truncated_payload).hexdigest(),
    }
    truncated = tmp_path / "missing-path.v1"
    truncated.write_bytes(
        json.dumps(truncated_header, sort_keys=True, separators=(",", ":")).encode()
        + b"\n"
        + truncated_payload
    )
    with pytest.raises(DEPS.TrackedPathInventoryError, match="not byte-identical"):
        DEPS.load_tracked_path_inventory(truncated, sha, root=repo)


def test_exact_tree_inventory_rejects_checkout_identity_drift(tmp_path: Path) -> None:
    repo, sha, inventory = _seed_tracked_path_repo(tmp_path)
    (repo / "engine" / "later.py").write_text("LATER = True\n", encoding="utf-8")
    later = _commit_fixture(repo, "move checkout")
    assert later != sha
    with pytest.raises(DEPS.TrackedPathInventoryError, match="checkout HEAD"):
        DEPS.load_tracked_path_inventory(inventory, sha, root=repo)


def test_inventory_preserves_omitted_tracked_existence_but_never_fakes_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, sha, inventory = _seed_tracked_path_repo(tmp_path)
    shutil.rmtree(repo / "site")
    monkeypatch.setattr(DEPS, "ROOT", repo)
    DEPS._selector_file_analysis.cache_clear()

    with DEPS.planner_tracked_path_inventory(inventory, sha, root=repo):
        reads = DEPS.direct_reads(repo / "tests" / "test_owner.py")
        assert "site/owner.json" in reads
        assert DEPS.pytest_invocation_ambiguities("pytest site") == (
            "directory pytest target 'site'",
        )
        with pytest.raises(DEPS.ScopeMaterializationError, match="omitted.py"):
            DEPS.suite_dependency_closure("site/omitted.py")


def test_invalid_inventory_enters_the_existing_full_suite_planner_fallback(
    tmp_path: Path,
) -> None:
    """Inventory doubt launches every pack; it can never publish no-work."""
    output = tmp_path / "github-output"
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert PACK.main(
        [
            "--workflow", str(MANIFEST),
            "--pack-count", "12",
            "--plan-only",
            "--github-output", str(output),
            "--tracked-paths-file", str(tmp_path / "missing.v1"),
            "--tested-tree-sha", sha,
        ]
    ) == 0
    outputs = _parse_github_output(output.read_text(encoding="utf-8"))
    assert json.loads(outputs["matrix"]) == {
        "include": [{"pack": index} for index in range(12)]
    }
    assert outputs["has_work"] == "true"
    assert outputs["plan_sha"] == ""
    assert "tracked-path inventory" in outputs["reason"]


def test_virtual_existence_oracle_is_confined_to_planner_scope_derivation() -> None:
    """The W3 oracle must never become a product/runtime filesystem law."""
    tree = ast.parse((ROOT / "scripts" / "run_ci_pack.py").read_text())
    oracle_calls = {
        "planner_path_exists": set(),
        "planner_path_is_file": set(),
        "planner_tracked_path_inventory": set(),
    }
    for function in (
        node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ):
        for node in ast.walk(function):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in oracle_calls:
                    oracle_calls[node.func.id].add(function.name)
    assert oracle_calls == {
        "planner_path_exists": {"_scope_coverage_findings"},
        # `infer_job_paths` is the nested implementation inside
        # `infer_job_scopes`; ast.walk reports both lexical owners.
        "planner_path_is_file": {"infer_job_paths", "infer_job_scopes"},
        "planner_tracked_path_inventory": {"plan_from_workflow"},
    }


def test_full_and_sparse_planners_are_field_and_byte_identical_over_replay_corpus(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Selection, partition, semantic identity, and plan hash survive sparsity.

    The corpus covers the handoff's distinct decision shapes. Changed path order
    is intentionally preserved, including both rename/copy sides; exact Git
    decoding is independently pinned by the hostile depth-two regression above.
    """
    repo, sha, inventory = _seed_tracked_path_repo(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.setattr(DEPS, "ROOT", repo)
    monkeypatch.setattr(AUDIT, "ROOT", repo)

    def job(job_id: str, ordinal: int, suite: str, weight: int) -> object:
        return PACK.LegacyJob(
            job_id=job_id,
            definition={
                "if": PACK.DISABLED_IF,
                "runs-on": "ubuntu-latest",
                "steps": [
                    {
                        "name": f"{job_id} semantic proof",
                        "run": f"python -m pytest {suite}",
                    }
                ],
            },
            ordinal=ordinal,
            weight=weight,
        )

    jobs = [
        job("literal-owner", 0, "tests/test_owner.py", 5),
        job("opaque-data-owner", 1, "tests/test_opaque.py", 3),
    ]
    corpus = [
        ["tests/test_owner.py"],
        ["engine/core.py"],
        ["site/owner.json"],
        ["data/feed.json"],
        ["site/old.json", "site/owner.json"],
        [".github/ci/legacy-jobs.yml"],
        ["research/PASSIVE_NOTE.md"],
        ["brand_new_root/unknown.xyz"],
    ]
    identity = {
        "changed_from": sha,
        "scope_mode": "active",
        "pack_count": 3,
        "workflow_run_id": "replay",
        "workflow": "ci",
        "event": "pull_request",
        "role": "pr_head",
        "tested_tree_sha": sha,
        "subject_head_sha": sha,
        "base_sha": sha,
    }
    AUDIT._classify.cache_clear()
    DEPS._selector_file_analysis.cache_clear()
    full = [PACK.build_plan(jobs, changed, **identity) for changed in corpus]

    shutil.rmtree(repo / "data")
    shutil.rmtree(repo / "site")
    AUDIT._classify.cache_clear()
    DEPS._selector_file_analysis.cache_clear()
    with DEPS.planner_tracked_path_inventory(inventory, sha, root=repo):
        sparse = [PACK.build_plan(jobs, changed, **identity) for changed in corpus]

    assert len(full) == len(sparse) == len(corpus)
    for changed, full_plan, sparse_plan in zip(corpus, full, sparse, strict=True):
        assert sparse_plan.changed_paths == full_plan.changed_paths == tuple(changed)
        assert sparse_plan.changed_files_sha256 == PACK.changed_files_digest(changed)
        assert sparse_plan.to_dict() == full_plan.to_dict()
        assert sparse_plan.plan_sha256 == full_plan.plan_sha256


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
    monkeypatch.setattr(PACK, "load_legacy_jobs", lambda path, gate=None: jobs)
    _stub_planner_paths(monkeypatch, ["engine/example.py"])
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
    monkeypatch.setattr(PACK, "_restore_workspace", lambda *_args: None)
    monkeypatch.setattr(
        PACK,
        "_run_job",
        lambda job, **_kwargs: PACK.JobExecution(
            logical_job_id=job.job_id,
            job_exec_sha256=PACK.semantic_job_digest(job),
            infrastructure={"outcome": "passed"},
            steps=(),
            failure=None,
        ),
    )
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


def test_execute_pack_emits_legacy_job_annotations_and_failed_job_ids(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """merge_on_green parses `title=legacy-job-<id>` for live-inherited reds."""
    definition = {
        "steps": [{"name": "semantic proof", "run": "true"}],
        "runs-on": "ubuntu-latest",
    }
    jobs = [
        PACK.LegacyJob("unrun-government-revenue", definition, 0, 1, ("engine/**",)),
        PACK.LegacyJob("other", definition, 1, 1, ("engine/**",)),
    ]
    monkeypatch.setattr(PACK, "_workspace_root", lambda: ROOT)
    monkeypatch.setattr(PACK, "_restore_workspace", lambda *_args: None)

    def fake_run(job, **_kwargs):
        failed = job.job_id == "unrun-government-revenue"
        specs = PACK.semantic_step_specs(job)
        return PACK.JobExecution(
            logical_job_id=job.job_id,
            job_exec_sha256=PACK.semantic_job_digest(job),
            infrastructure={"outcome": "passed"},
            steps=tuple(
                {
                    **spec.plan_dict(),
                    "outcome": "failed" if failed else "passed",
                    "failure_signature": None,
                }
                for spec in specs
            ),
            failure=(f"{job.job_id}: step 'pytest' exited 1" if failed else None),
        )

    monkeypatch.setattr(PACK, "_run_job", fake_run)
    assert PACK.execute_pack(jobs) == 1
    out = capsys.readouterr().out
    assert any(
        line.startswith("::error title=legacy-job-unrun-government-revenue::")
        for line in out.splitlines()
    ), out
    failed = next(
        line for line in out.splitlines() if line.startswith("CI_PACK_FAILED_JOBS=")
    )
    assert json.loads(failed.split("=", 1)[1]) == ["unrun-government-revenue"]


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


@pytest.fixture(autouse=True)
def _isolate_pack_runner_planner_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pack jobs inject planner env; unit tests must not inherit the live PR diff.

    Measured 2026-08-13: main ci.yml run 31746772926 and PR #5560 pack-1 redded
    workflow-yaml because packing-contract tests monkeypatched ``changed_files``
    while ``plan_from_workflow`` reads ``resolve_changed_files`` →
    ``CI_CHANGED_FILES_JSON``. On main the value was ``null`` (full suite); on
    #5560 it was the live 81-file PR list. Tests expecting an unscoped/full
    fixture plan then asserted against the hosted runner's diff.

    ``CI_CHANGED_FILES_FILE`` joined the list on 2026-08-14 and is now the one
    that matters: it is what every pack exports after downloading the
    changed-file artifact, and it OUT-RANKS the inline form, so leaving it
    ambient would leak the live PR diff into these fixtures exactly as #5560's
    inline value did.

    Semantic identity env joined on 2026-08-15 (PR #5750 pack-1 / job
    95003903089). ``build_plan`` now infers ``role=pr_head`` from
    ``GITHUB_EVENT_NAME=pull_request`` and then refuses a full-suite plan
    (``changed is None``) as "a PR semantic plan requires an exact
    changed-file inventory". Packing-contract tests that call
    ``plan_from_workflow(..., changed_from=None)`` or ``--plan-only``
    without ``--event/--role`` inherited the live PR event and the
    hosted-runner packing contract exited 1. Strip the identity vars so
    those tests keep the local ``workflow_dispatch`` / ``main`` default;
    tests that want a PR plan pass ``event``/``role`` or a file list
    explicitly. The production ci-plan path still passes ``--event`` and
    ``--role`` on the command line, so this does not weaken that gate.
    """
    for name in (
        "CI_CHANGED_FILES_FILE",
        "CI_CHANGED_FILES_JSON",
        "CI_SCOPE_MODE",
        "CI_DYNAMIC_MATRIX_MODE",
        "GITHUB_EVENT_NAME",
        "CI_SEMANTIC_ROLE",
        "CI_TESTED_TREE_SHA",
        "CI_SUBJECT_HEAD_SHA",
        "CI_BASE_SHA",
    ):
        monkeypatch.delenv(name, raising=False)


def _stub_planner_paths(
    monkeypatch: pytest.MonkeyPatch, paths: list[str] | None
) -> None:
    """Pin the #5564 production path (resolve_changed_files), not git."""
    monkeypatch.setattr(
        PACK,
        "resolve_changed_files",
        lambda changed_from, explicit_json=None, explicit_file=None, _paths=paths: (
            _paths
        ),
    )


def test_packing_contract_ignores_ambient_ci_changed_files_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The leak that redded every PR's pack-1 after #5564.

    Plant an 81-file live-PR list (the #5560 shape) as ambient env. The fixture
    still passes ``engine/example.py``. would-skip (``site/**``) must stay
    skipped — if this selects would-skip, the test inherited the hosted
    runner's diff and pack-1 is red on every unrelated PR.
    """
    ambient = [f"site/leak_{index}.html" for index in range(81)]
    monkeypatch.setenv("CI_CHANGED_FILES_JSON", json.dumps(ambient))
    assert PACK.resolve_changed_files("base-sha") == ambient
    _stub_planner_paths(monkeypatch, ["engine/example.py"])
    _freeze_scope_inference(monkeypatch)
    jobs = [
        _plan_job("owner", 0, paths=("engine/**",)),
        _plan_job("would-skip", 1, paths=("site/**",)),
    ]
    monkeypatch.setattr(PACK, "load_legacy_jobs", lambda path, gate=None: list(jobs))
    plan = PACK.plan_from_workflow(
        MANIFEST, changed_from="base-sha", scope_mode="active", pack_count=12
    )
    assert set(plan.eligible_job_ids) == {"owner"}
    assert plan.skipped_job_ids == ("would-skip",)
    assert PACK.resolve_changed_files("base-sha") == ["engine/example.py"]


def test_packing_contract_strips_ambient_pr_event_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The leak that redded pack-1 on PR #5750 head 168e8e1f.

    Autouse isolation must leave ``GITHUB_EVENT_NAME`` unset so
    ``_full_plan()`` mints a local main plan. Planting the live Actions
    PR event afterwards must raise the inventory ManifestError — that is
    the law that fired inside the packing contract when the fixture
    still inherited ``pull_request``.
    """
    assert os.environ.get("GITHUB_EVENT_NAME") != "pull_request"
    assert "CI_SEMANTIC_ROLE" not in os.environ
    plan = _full_plan()
    assert plan.event == "workflow_dispatch"
    assert plan.role == "main"
    assert plan.changed_from is None
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    with pytest.raises(PACK.ManifestError, match="exact changed-file inventory"):
        _full_plan()


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


DATA_HEALTH = ROOT / ".github" / "workflows" / "data-health.yml"


def test_every_data_health_trigger_can_actually_mint_a_plan() -> None:
    """The lane that took the data-gated jobs off the merge gate must be able to run.

    ``data-health.yml`` fires on ``workflow_run`` (daily completed) and on a
    13:30 UTC ``schedule`` backstop, and neither passes ``--role``/``--event``,
    so both resolve to role ``main`` from the ambient ``GITHUB_EVENT_NAME``.
    Until 2026-08-19 the supported set held only ``main/workflow_dispatch``, so
    both raised ManifestError BEFORE any legacy job ran: run 32262001614
    (schedule) died ``main/schedule is unsupported``, exit 2, in all six packs.
    That is not a fail-closed that protects anything — it silently emptied the
    only lane that grades the 74 ``gate: data`` jobs against a freshly written
    data tree, which is the entire promise W2 made when it moved them off ci.yml.

    This asserts the workflow's OWN trigger list, so adding a trigger there
    without teaching the planner reds here instead of going quiet in production.
    """
    workflow = _yaml(DATA_HEALTH)
    triggers = set((workflow.get("on") or workflow.get(True)).keys())
    assert triggers, "data-health.yml must declare triggers"
    for event in sorted(triggers):
        assert ("main", event) in PACK.SUPPORTED_PLAN_ROLE_EVENTS, (
            f"data-health.yml fires on {event!r} but the planner refuses "
            f"main/{event}; that pack dies at exit 2 before a single job runs"
        )


def test_a_main_role_plan_from_a_data_health_trigger_carries_every_data_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Widening the transport must not have relaxed what ``main`` MEANS.

    Both new events describe the shape ``main`` already required — a whole-tree
    run at one checked-out SHA with no diff — so the plan they mint must be the
    same full ``gate: data`` suite the manual dispatch minted, and it must carry
    ``house-law-registry``: the guard whose input (the newest
    ``data/symbol_directory`` snapshot) only ever moves on a nightly commit.
    """
    monkeypatch.setenv("GITHUB_SHA", "0" * 40)
    monkeypatch.delenv("CI_SEMANTIC_ROLE", raising=False)
    monkeypatch.delenv("CI_TESTED_TREE_SHA", raising=False)
    monkeypatch.delenv("CI_SUBJECT_HEAD_SHA", raising=False)
    monkeypatch.delenv("CI_BASE_SHA", raising=False)

    plans = {}
    for event in ("workflow_dispatch", "workflow_run", "schedule"):
        monkeypatch.setenv("GITHUB_EVENT_NAME", event)
        plan = PACK.plan_from_workflow(
            MANIFEST, changed_from=None, scope_mode="active",
            pack_count=6, gate="data",
        )
        assert plan.role == "main" and plan.event == event
        assert plan.changed_from is None
        plans[event] = {job for pack in plan.pack_jobs for job in pack}

    assert "house-law-registry" in plans["schedule"]
    assert plans["schedule"] == plans["workflow_dispatch"] == plans["workflow_run"]


def test_the_supported_role_event_set_stays_closed() -> None:
    """An unreasoned combination must still fail closed, both minting and consuming.

    The widening above is two named transports for a role whose substance is
    enforced elsewhere; it is not permission for any event to plan anything.
    """
    assert ("main", "push") not in PACK.SUPPORTED_PLAN_ROLE_EVENTS
    assert ("pr_head", "schedule") not in PACK.SUPPORTED_PLAN_ROLE_EVENTS
    assert ("pr_head", "workflow_dispatch") not in PACK.SUPPORTED_PLAN_ROLE_EVENTS
    # One constant, both gates: the planner and the authoritative-plan reader
    # cannot drift into disagreeing about what a legal plan is.
    source = (ROOT / "scripts" / "run_ci_pack.py").read_text()
    assert source.count("(role, event) not in SUPPORTED_PLAN_ROLE_EVENTS") == 2


def test_runner_contract_is_the_v2_linux_x86_64_string() -> None:
    """RUNNER_CONTRACT v2 (#6351 P0R bridge): a truthful logical claim about
    the runtime `attest_execution_profile` enforces, replacing the
    "ubuntu-latest" image name the v1 string aspirationally described.
    """
    assert PACK.RUNNER_CONTRACT == "ci-pack/linux-x86_64/python-3.12.13/node-20/v2"


def test_diagnostic_canary_workflow_constant_names_the_exact_workflow() -> None:
    assert PACK.DIAGNOSTIC_CANARY_WORKFLOW == "infrastructure-selfhosted-ci-canary"
    assert PACK.TRUSTED_EXECUTOR_WORKFLOW == "trusted-ci-executor"
    assert PACK.DIAGNOSTIC_PR_WORKFLOWS == frozenset(
        {PACK.DIAGNOSTIC_CANARY_WORKFLOW, PACK.TRUSTED_EXECUTOR_WORKFLOW}
    )


def test_runner_contract_v2_participates_in_the_job_semantic_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Changing the runtime contract must change what every job's digest
    means — that is the whole point of a semantic contract version bump.
    """
    job = _plan_job("demo", 0)
    before = PACK.semantic_job_digest(job)
    monkeypatch.setattr(
        PACK, "RUNNER_CONTRACT", "ci-pack/linux-x86_64/python-3.12.13/node-20/v3"
    )
    after = PACK.semantic_job_digest(job)
    assert before != after


def test_build_plan_admits_the_diagnostic_pair_only_for_its_exact_workflow_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``(pr_head, workflow_dispatch)`` is admitted ONLY when ``workflow``
    equals the exact canary name — SUPPORTED_PLAN_ROLE_EVENTS itself stays
    closed (pinned separately by test_the_supported_role_event_set_stays_closed).
    """
    _freeze_scope_inference(monkeypatch)
    jobs = [_plan_job("demo", 0)]
    base = "b" * 40
    plan = PACK.build_plan(
        jobs,
        ["engine/example.py"],
        changed_from=base,
        scope_mode="active",
        pack_count=1,
        workflow=PACK.DIAGNOSTIC_CANARY_WORKFLOW,
        event="workflow_dispatch",
        role="pr_head",
        tested_tree_sha="a" * 40,
        subject_head_sha="c" * 40,
        base_sha=base,
    )
    assert plan.role == "pr_head"
    assert plan.event == "workflow_dispatch"
    assert plan.workflow == PACK.DIAGNOSTIC_CANARY_WORKFLOW

    for other_workflow in ("ci", "some-other-workflow"):
        with pytest.raises(PACK.ManifestError, match="unsupported"):
            PACK.build_plan(
                jobs,
                ["engine/example.py"],
                changed_from=base,
                scope_mode="active",
                pack_count=1,
                workflow=other_workflow,
                event="workflow_dispatch",
                role="pr_head",
                tested_tree_sha="a" * 40,
                subject_head_sha="c" * 40,
                base_sha=base,
            )


def test_p3a_executor_uses_the_same_closed_diagnostic_plan_admission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _freeze_scope_inference(monkeypatch)
    base = "b" * 40
    plan = PACK.build_plan(
        [_plan_job("demo", 0)],
        ["engine/example.py"],
        changed_from=base,
        scope_mode="active",
        pack_count=1,
        workflow=PACK.TRUSTED_EXECUTOR_WORKFLOW,
        event="workflow_dispatch",
        role="pr_head",
        tested_tree_sha="a" * 40,
        subject_head_sha="c" * 40,
        base_sha=base,
    )
    assert plan.workflow == PACK.TRUSTED_EXECUTOR_WORKFLOW
    assert plan.role == "pr_head"
    assert plan.event == "workflow_dispatch"


def test_build_plan_still_requires_every_pr_head_invariant_for_the_diagnostic_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The diagnostic pair is a narrower ADMISSION, not a relaxed invariant:
    exact changed-file inventory and changed_from == base_sha still apply
    (spec item A.2).
    """
    _freeze_scope_inference(monkeypatch)
    jobs = [_plan_job("demo", 0)]
    with pytest.raises(PACK.ManifestError, match="exact changed-file inventory"):
        PACK.build_plan(
            jobs,
            None,
            changed_from="b" * 40,
            scope_mode="active",
            pack_count=1,
            workflow=PACK.DIAGNOSTIC_CANARY_WORKFLOW,
            event="workflow_dispatch",
            role="pr_head",
            tested_tree_sha="a" * 40,
            subject_head_sha="c" * 40,
            base_sha="b" * 40,
        )
    with pytest.raises(PACK.ManifestError, match="changed_from must equal"):
        PACK.build_plan(
            jobs,
            ["engine/example.py"],
            changed_from="b" * 40,
            scope_mode="active",
            pack_count=1,
            workflow=PACK.DIAGNOSTIC_CANARY_WORKFLOW,
            event="workflow_dispatch",
            role="pr_head",
            tested_tree_sha="a" * 40,
            subject_head_sha="c" * 40,
            base_sha="f" * 40,
        )


def test_build_plan_refuses_the_old_broken_main_dispatch_with_changed_from(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mutation-lock (#6351 addendum): the pre-fix canary passed
    ``--changed-from`` unconditionally, including for the ``pr_number=0``
    main dispatch. That shape must stay refused — the fix is to stop
    sending it for pr0, never to admit it.
    """
    _freeze_scope_inference(monkeypatch)
    jobs = [_plan_job("demo", 0)]
    with pytest.raises(PACK.ManifestError, match="main semantic plan"):
        PACK.build_plan(
            jobs,
            ["engine/example.py"],
            changed_from="a" * 40,
            scope_mode="active",
            pack_count=1,
            workflow=PACK.DIAGNOSTIC_CANARY_WORKFLOW,
            event="workflow_dispatch",
            role="main",
            tested_tree_sha="a" * 40,
            subject_head_sha="a" * 40,
            base_sha="a" * 40,
        )


def test_attest_execution_profile_refuses_on_a_non_linux_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The real guard refuses a deterministically simulated non-Linux host."""
    monkeypatch.setattr(PACK.platform, "system", lambda: "Darwin")
    with pytest.raises(PACK.ExecutionProfileError, match="Linux"):
        PACK.attest_execution_profile(None)


def test_attest_execution_profile_checks_system_machine_python_node_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(PACK.platform, "system", lambda: "Darwin")
    with pytest.raises(PACK.ExecutionProfileError, match="Linux"):
        PACK.attest_execution_profile(None)

    monkeypatch.setattr(PACK.platform, "system", lambda: "Linux")
    monkeypatch.setattr(PACK.platform, "machine", lambda: "arm64")
    with pytest.raises(PACK.ExecutionProfileError, match="x86_64"):
        PACK.attest_execution_profile(None)

    monkeypatch.setattr(PACK.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(PACK.platform, "python_version", lambda: "3.12.14")
    with pytest.raises(PACK.ExecutionProfileError, match="3.12.13"):
        PACK.attest_execution_profile(None)

    monkeypatch.setattr(PACK.platform, "python_version", lambda: "3.12.13")
    monkeypatch.setattr(PACK, "_node_major_version", lambda: 18)
    with pytest.raises(PACK.ExecutionProfileError, match="node 20"):
        PACK.attest_execution_profile(None)

    monkeypatch.setattr(PACK, "_node_major_version", lambda: 20)
    # All four checks satisfied and no plan -> success (tree-sha check skipped).
    PACK.attest_execution_profile(None)


def test_attest_execution_profile_checks_checkout_head_against_the_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(PACK.platform, "system", lambda: "Linux")
    monkeypatch.setattr(PACK.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(PACK.platform, "python_version", lambda: "3.12.13")
    monkeypatch.setattr(PACK, "_node_major_version", lambda: 20)
    plan = _full_plan()
    monkeypatch.setattr(PACK, "_workspace_root", lambda: Path("/tmp"))
    monkeypatch.setattr(PACK, "_current_commit_sha", lambda root: "0" * 40)
    with pytest.raises(PACK.ExecutionProfileError, match="does not match attested"):
        PACK.attest_execution_profile(plan)

    monkeypatch.setattr(PACK, "_current_commit_sha", lambda root: plan.tested_tree_sha)
    PACK.attest_execution_profile(plan)  # no raise


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
        workflow_run_id=plan.workflow_run_id,
        workflow=plan.workflow,
        event=plan.event,
        role=plan.role,
        tested_tree_sha=plan.tested_tree_sha,
        subject_head_sha=plan.subject_head_sha,
        base_sha=plan.base_sha,
        authority_changed=plan.authority_changed,
        changed_from=plan.changed_from,
        scope_mode=plan.scope_mode,
        changed_files_sha256=plan.changed_files_sha256,
        pack_count=plan.pack_count,
        eligible_job_ids=plan.eligible_job_ids,
        pack_jobs=plan.pack_jobs,
        pack_weights=plan.pack_weights,
        semantic_jobs=plan.semantic_jobs,
    )
    assert PACK._canonical_digest(payload) == plan.plan_sha256

    # WHICH DIFF, not merely which jobs (2026-08-14). The list left the job
    # outputs for an artifact nothing else hashes, so its digest has to be part
    # of the decision identity: a pack that downloaded the wrong file recomputes
    # a different plan sha and the parity check below refuses it. Without this
    # key that pack would pass parity and scope its guards to somebody else's
    # diff — see `test_a_pack_refuses_a_changed_file_list_it_cannot_prove`.
    assert payload["changed_files_sha256"] == plan.changed_files_sha256
    assert (
        PACK._canonical_digest({**payload, "changed_files_sha256": "f" * 64})
        != plan.plan_sha256
    )

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


def test_unknown_top_level_path_does_not_widen_the_plan_to_the_full_suite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _freeze_scope_inference(monkeypatch)
    jobs = [
        _plan_job("engine-owner", 0, paths=("engine/**",)),
        _plan_job("site-owner", 1, paths=("site/**",)),
        _plan_job("always-on", 2, paths=()),
    ]
    plan = PACK.build_plan(
        jobs,
        ["brand_new_root/unowned_runtime.xyz"],
        changed_from="base-sha",
        scope_mode="active",
        pack_count=12,
    )
    assert plan.eligible_job_ids == ("always-on",)
    assert "did not widen" in plan.reason
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
    monkeypatch.setattr(PACK, "load_legacy_jobs", lambda path, gate=None: list(jobs))
    _stub_planner_paths(monkeypatch, ["engine/old.py", "engine/new.py"])
    plan = PACK.plan_from_workflow(
        MANIFEST, changed_from="base-sha", scope_mode="active", pack_count=12
    )
    assert set(plan.eligible_job_ids) == {"owns-old", "owns-new"}
    assert plan.skipped_job_ids == ("elsewhere",)

    # Non-vacuity: with only the new side in the diff, the old owner is skipped.
    _stub_planner_paths(monkeypatch, ["engine/new.py"])
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

    def explode(path: object, gate: object = None) -> object:
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
    # The list itself is no longer an output (2026-08-14); the widened plan
    # publishes the affirmative "no list" digest instead, and the artifact this
    # path writes carries the token `null`.
    assert "changed_files" not in outputs
    assert outputs["changed_files_sha256"] == ""
    assert outputs["changed_files_count"] == "0"
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

    def explode(path: object, gate: object = None) -> object:
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


def test_a_pack_refuses_a_changed_file_list_it_cannot_prove(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The list left the job outputs on 2026-08-14; this is what replaced it.

    Moving it to an artifact (run 31775693780: 350,264 bytes of `env:` against
    execve's 131,072-byte cap, twelve packs dead at launch) put it OUTSIDE every
    channel the packs already trust. That matters because the list is not
    decoration — the guards inside a pack scope THEMSELVES to it
    (conflict-markers, self-mod-fence, the selection itself), so a stale,
    swapped or truncated artifact shrinks what a green pack actually proved,
    silently.

    The repair needs no new gate: `changed_files_sha256` went into
    `plan_hash_payload`, so a pack that recomputes from the wrong file
    recomputes a different plan sha and the EXISTING `--expect-plan-sha` parity
    check refuses before a single legacy step runs. Every shape below is one
    that used to pass parity and run the wrong suite under a check name the
    sweeper reads as proof.
    """
    handle = tmp_path / "changed-files.json"
    listed = ["engine/example.py", "docs/存档 note.md"]
    handle.write_text(json.dumps(listed, separators=(",", ":")), encoding="utf-8")
    _freeze_scope_inference(monkeypatch)
    jobs = [
        _plan_job("engine-owner", 0, paths=("engine/**",)),
        _plan_job("site-owner", 1, paths=("site/**",)),
    ]
    monkeypatch.setattr(PACK, "load_legacy_jobs", lambda path, gate=None: list(jobs))
    plan = PACK.plan_from_workflow(
        MANIFEST,
        changed_from="basesha",
        scope_mode="active",
        pack_count=2,
        changed_files_file=handle,
    )
    assert plan.changed_files_count == 2
    assert plan.changed_files_sha256 == PACK.changed_files_digest(listed)

    reached: list[int] = []
    monkeypatch.setattr(
        PACK, "execute_pack", lambda jobs, **kwargs: reached.append(len(jobs)) or 0
    )

    def run(handle_path: Path | None, *, expect: str | None = None) -> int:
        argv = [
            "--workflow", str(MANIFEST),
            "--pack-index", "0", "--pack-count", "2",
            "--changed-from", "basesha",
            "--execute",
            "--expect-plan-sha", expect or plan.plan_sha256,
        ]
        if handle_path is not None:
            argv += ["--changed-files-file", str(handle_path)]
        return PACK.main(argv)

    # A positive control FIRST, or every refusal below could be passing for a
    # reason that has nothing to do with the changed-file list.
    assert run(handle) == 0
    assert reached, "the unmutated fixture must reach execution"

    def refusal(handle_path: Path | None, needle: str) -> None:
        assert run(handle_path) == 2
        lines = capsys.readouterr().out.splitlines()
        diagnosis = next(
            line for line in lines
            if line.startswith("::error title=ci-changed-files::")
        )
        assert needle in diagnosis, diagnosis
        assert any(
            line.startswith("::error title=ci-plan-parity::") for line in lines
        ), "the parity check is the gate; the diagnosis alone must not be it"

    # (i) A well-formed list that is simply not THIS plan's list — the swapped
    # or stale artifact, and the only shape no structural check can catch.
    other = tmp_path / "other.json"
    other.write_text('["engine/example.py"]', encoding="utf-8")
    refusal(other, "read as list")

    # (ii) The artifact landed truncated / corrupt. Never widen here: a pack
    # that quietly ran the full suite under a pinned plan's check name reports
    # green for a suite the published plan does not describe.
    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text('["engine/example.py", "docs/', encoding="utf-8")
    refusal(corrupt, "read as malformed")

    # (iii) The download never landed.
    refusal(tmp_path / "missing.json", "read as unreadable")

    # (iv) No handle configured at all. `--changed-from` is still on the command
    # line, so without the file-first order this would silently git-diff a
    # depth-1 tree and widen — which is exactly the miss the pin now catches.
    monkeypatch.delenv("CI_CHANGED_FILES_FILE", raising=False)
    monkeypatch.setattr(
        PACK, "changed_files", lambda base: (_ for _ in ()).throw(RuntimeError(base))
    )
    assert run(None) == 2

    # (v) THE MIRROR IMAGE, and the one the old `changed_files` output could not
    # express: the plan recorded NO list (full suite, digest "") while the
    # handle carries a real one. Two channels describing different runs.
    widened = PACK.plan_from_workflow(
        MANIFEST, changed_from=None, scope_mode="active", pack_count=2
    )
    assert widened.changed_files_sha256 == ""
    assert (
        PACK.main(
            [
                "--workflow", str(MANIFEST),
                "--pack-index", "0", "--pack-count", "2",
                "--changed-from", "basesha",
                "--execute",
                "--expect-plan-sha", widened.plan_sha256,
                "--changed-files-file", str(handle),
            ]
        )
        == 2
    )

    # Non-vacuity: exactly one of the six runs reached execution.
    assert len(reached) == 1


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
    # EXACTLY these six, and none of them scales with the size of the diff. A
    # job output becomes an `env:` string in the consuming job and execve caps
    # one at 131,072 bytes; the retired `changed_files` output measured 350,264
    # on PR #5578 and killed all twelve packs at launch (run 31775693780). A
    # seventh, unbounded output added here would reopen exactly that.
    assert set(outputs) == {
        "matrix", "has_work", "plan_sha", "reason",
        "changed_files_sha256", "changed_files_count",
    }
    assert json.loads(outputs["matrix"]) == {
        "include": [{"pack": index} for index in range(12)]
    }
    assert outputs["has_work"] == "true"
    assert len(outputs["plan_sha"]) == 64
    assert outputs["changed_files_sha256"] == ""
    assert outputs["changed_files_count"] == "0"


def test_matrix_mode_overrules_a_no_work_plan_without_changing_its_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The dynamic matrix's kill switch, pinned where it is actually visible.

    After #5564, empty packs are omitted (`nonempty_pack_indices` only). A
    no-work plan must emit ``{"include": []}`` in active mode — not pack 0 —
    and shadow/off must still launch all twelve. The hash must be identical
    across modes: it is a plan input, and the mode is an emission policy. If
    the mode entered the hash, flipping the repository variable mid-run would
    make every in-flight pack refuse its own plan.
    """
    _freeze_scope_inference(monkeypatch)
    jobs = [_plan_job("engine-owner", 0, paths=("engine/**",))]
    monkeypatch.setattr(PACK, "load_legacy_jobs", lambda path, gate=None: list(jobs))
    _stub_planner_paths(monkeypatch, ["research/NOTE.md"])
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
    # The DIGEST and the COUNT joined this document on 2026-08-14, never the
    # list: it is printed as one machine line in the planner's log, so an
    # unbounded array here would only move the 350,264 bytes out of the pack
    # step's `env:` and into a log line nobody can read (run 31775693780).
    assert set(document) == {
        "schema", "changed_from", "scope_mode", "reason", "scope_summary",
        "legacy_job_count", "eligible_job_count", "eligible_jobs",
        "skipped_job_count", "skipped_jobs", "packs", "nonempty_pack_indices",
        "matrix", "has_work", "plan_sha256",
        "changed_files_sha256", "changed_files_count",
        "workflow_run_id", "workflow", "event", "role",
        "tested_tree_sha", "subject_head_sha", "base_sha",
        "authority_changed", "semantic_jobs",
    }
    # The full-suite baseline carries the affirmative "no list" encoding, which
    # is what lets a pack tell "planned everything" from "planned this exact
    # diff" without a second flag.
    assert document["changed_files_sha256"] == ""
    assert document["changed_files_count"] == 0
    assert document["schema"] == PACK.PLAN_SCHEMA == "ci.pack_plan.v2"
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
    step = next(s for s in pack["steps"] if s.get("id") == "execute_semantic_pack")
    assert "CI_SCOPE_ARG" not in step.get("env", {})
    assert "--changed-from" not in step["run"]
    # A leftover `shadow` GitHub Actions variable must not hostage the fleet:
    # anything other than exact `off` is active. Quote: before #5515 the var
    # could sit at `shadow` and run the full 185-job suite while reporting a
    # predicted subset; after, and still after this PR, the expression admits
    # only `off` or `active`.
    plan = _yaml(WORKFLOW)["jobs"]["ci-plan"]
    plan_step = next(
        s for s in plan["steps"]
        if isinstance(s, dict) and s.get("id") == "plan"
    )
    assert plan_step["env"]["CI_SCOPE_MODE"] == (
        "${{ vars.CI_SCOPE_MODE == 'off' && 'off' || 'active' }}"
    )
    assert plan_step["env"]["CI_DYNAMIC_MATRIX_MODE"] == (
        "${{ vars.CI_DYNAMIC_MATRIX_MODE == 'off' && 'off' || 'active' }}"
    )
    scope_arg = str(plan_step["env"]["CI_SCOPE_ARG"])
    assert "github.event_name == 'pull_request'" in scope_arg
    assert "--changed-from" in scope_arg
    assert "steps.identity.outputs.tested_base_sha" in scope_arg
    assert "github.base_ref" not in scope_arg
    on = _yaml(WORKFLOW).get("on") or _yaml(WORKFLOW).get(True)
    pull_paths = on["pull_request"]["paths"]
    assert "**" in pull_paths
    assert "worker/**" in pull_paths
    assert "content/**" in pull_paths
    assert "wrangler.toml" in pull_paths
    assert "$CI_SCOPE_ARG" in str(plan_step["run"])


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
    # per legacy suite), so a job-per-legacy-suite regression here is the thing
    # this guards against — while the exact ci-plan/ci-gate shape belongs to
    # tests/test_ci_plan_workflow.py, which owns it positively. Two suites
    # asserting the same equality would only mean two places to edit, and the
    # weaker one would win.
    #
    # `contract-delta` (2026-08-19) joined the allowed set deliberately: it is
    # one small, purposeful, path-independent job — same shape as ci-plan/
    # ci-pack/ci-gate, not a per-suite fan-out job — that re-derives two
    # CI-contract finding classes ci-pack's own path scoping cannot reach (see
    # scripts/check_contract_delta.py's module docstring). Adding it here is
    # the same class of change as ci-plan/ci-gate joining originally; it does
    # not reopen the 86-VM fan-out this test exists to prevent.
    assert set(workflow["jobs"]) <= {"ci-plan", "ci-pack", "contract-delta", "ci-gate"}
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
    # Sibling packs must finish so their proofs survive a single red. fail-fast
    # on pull_request cancelled the other eleven, ci-gate went red, and a heal
    # had to rerun everything. A real red still fails ci-gate.
    assert pack["strategy"]["fail-fast"] is False
    pack_src = WORKFLOW.read_text(encoding="utf-8")
    assert "fail-fast: false" in pack_src
    assert "fail-fast: ${{ github.event_name == 'pull_request' }}" not in pack_src
    assert 'fail-fast: "${{ github.event_name == \'pull_request\' }}"' not in pack_src
    # No `max-parallel`: it existed only to stop main's packs from taking all four
    # `render-linux` runners. With no shared pool to protect, throttling would only
    # double main's proof (~26 min -> ~50 min), and it cannot help against the hosted
    # ceiling because that limit is ACCOUNT-wide, not per-matrix.
    assert "max-parallel" not in pack["strategy"], (
        "reintroducing max-parallel only slows main's proof; the hosted concurrency "
        "ceiling is account-wide and this key cannot raise it"
    )
    assert pack["if"] == "needs.ci-plan.outputs.has_work == 'true'"
    run_text = "\n".join(
        str(step.get("run", "")) for step in pack["steps"] if isinstance(step, dict)
    )
    assert "--workflow .github/ci/legacy-jobs.yml" in run_text
    assert "--pack-count 12" in run_text

    # A manifest edit must trigger CI even though GitHub does not interpret the
    # manifest itself as a workflow.
    triggers = workflow.get("on") or workflow.get(True)
    assert ".github/ci/legacy-jobs.yml" in triggers["pull_request"]["paths"]
    assert triggers["pull_request"]["types"] == [
        "opened", "synchronize", "reopened"
    ]


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
    """ci-plan keeps full history; packs shallow-checkout the current tree.

    Measured PR #5550 / run 31729769728: twelve packs fetching fetch-depth:0 at
    once put ci-pack-1 in "Checking out the ref" for 31 minutes. Packs consume
    ci-plan's changed-file list and only need the current working tree (legacy
    suites inspect committed site/ artifacts, not historical blobs). Do not
    replace the PACK checkout with sparse checkout. W3 contains only ci-plan's
    working tree; ci-pack materialization remains W4.
    """
    workflow = _yaml(WORKFLOW)
    pack = workflow["jobs"]["ci-pack"]
    checkout = next(
        step
        for step in pack["steps"]
        if str(step.get("uses", "")).startswith("actions/checkout@")
    )
    assert checkout["with"]["filter"] == "blob:none"
    assert checkout["with"]["fetch-depth"] == 1
    assert "sparse-checkout" not in checkout["with"]
    plan = workflow["jobs"]["ci-plan"]
    plan_checkout = next(
        step
        for step in plan["steps"]
        if str(step.get("uses", "")).startswith("actions/checkout@")
    )
    assert plan_checkout["with"]["fetch-depth"] == 0
    assert plan_checkout["with"]["sparse-checkout-cone-mode"] is False
    assert plan_checkout["with"]["sparse-checkout"].splitlines() == [
        "/*",
        "!/data/",
        "!/site/",
        "!/mockups/",
        "!/verify_shots/",
    ]


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
    # Commit 09abde056620 "fix(ci): contain fence checkout to proof surface"
    # bounded fence-pack's checkout to fetch-depth 256 + sparse-checkout
    # (~74.7k -> 4,994 files, production-proven). The exact shape (paths,
    # cone-mode) is canonically owned by test_fence_checkout_contract.py;
    # this assertion only keeps this file from drifting back to the old pin.
    assert checkout["with"]["fetch-depth"] == 256

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


# ── a MIRROR that drifts measures its own venv, not the boundary ─────────────
#
# ci-main-heartbeat.yml claims, in its own header, that "Job names + steps mirror
# ci.yml exactly, so 'green here' means the same thing as 'green on the PR gate'".
# On 2026-08-18 that claim was false for `tier-gate`. The PR lane had grown
# `requests numpy pandas` — with a comment saying to keep the environment "closed
# over the real production import graph", because engine/etf_pulse.py imports numpy
# at module scope — and the heartbeat copy had not. So tests/test_etfs_gate.py
# stopped SKIPPING there and started ERRORING with ModuleNotFoundError, and the
# heartbeat went red about its own pip line while reporting a failure named
# "tier-preview split contract (no paid row in the free shell)" — i.e. it read as a
# PAYWALL LEAK. It stayed that way ~30h because the sentinel that watches this lane
# was itself blind (see DSC:BLIND-SENTINEL-REPORTS-CLEAN).
#
# SCOPE — deliberately `tier-gate` only, and deliberately NOT a general
# "heartbeat venv >= manifest venv" rule, which is FALSE BY DESIGN elsewhere:
# heartbeat's template-site-sync omits jinja2 on purpose (its own comment routes
# the jinja2-gated cross-module test to free-content-estate instead), and
# engine-render-guards omits fastapi/httpx/jsonschema while its suites skip
# cleanly. A thin venv is legitimate when the tests SKIP and illegitimate when they
# ERROR, and only tier-gate has been shown to error. Widen this per-job, behind a
# job that has actually demonstrated the failure — never speculatively.
_HEARTBEAT_WORKFLOW = ROOT / ".github" / "workflows" / "ci-main-heartbeat.yml"
_PIP_INSTALL_RE = re.compile(r"pip install\s+(.+)")


def _job_pip_packages(job: dict) -> set[str]:
    """Every package name any `pip install` line in this job installs."""
    packages: set[str] = set()
    for step in job.get("steps") or []:
        for line in (step.get("run") or "").splitlines():
            found = _PIP_INSTALL_RE.search(line)
            if found:
                packages |= {tok for tok in found.group(1).split()
                             if not tok.startswith("-")}
    return packages


def _job_test_paths(job: dict) -> set[str]:
    joined = "\n".join((step.get("run") or "") for step in job.get("steps") or [])
    return set(_TEST_PATH_RE.findall(joined))


def test_heartbeat_tier_gate_venv_matches_the_pr_lane() -> None:
    """The heartbeat's tier-gate must not run a shared suite on a thinner venv."""
    heartbeat = yaml.safe_load(_HEARTBEAT_WORKFLOW.read_text(encoding="utf-8"))
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    hb_job = heartbeat["jobs"]["tier-gate"]
    pr_job = manifest["jobs"]["tier-gate"]

    shared_suites = _job_test_paths(hb_job) & _job_test_paths(pr_job)
    assert shared_suites, (
        "heartbeat tier-gate and the manifest's tier-gate now share NO test file — "
        "either the mirror was renamed or one side stopped running the boundary "
        "suites. Re-point this guard rather than deleting it."
    )

    missing = sorted(_job_pip_packages(pr_job) - _job_pip_packages(hb_job))
    assert not missing, (
        f"ci-main-heartbeat.yml's tier-gate job runs {len(shared_suites)} of the PR "
        f"lane's own boundary suites but installs neither {missing}.\n\n"
        "The PR lane added those because the production import graph needs them at "
        "module scope. A suite that imports one of them does not skip here — it "
        "ERRORS, and the heartbeat then reports a red named for the serving "
        "boundary while actually failing on its own pip line. Add the packages to "
        "the heartbeat job; do not narrow the step to dodge them."
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


# ---------------------------------------------------------------------------
# CURATED `scope: exclusive` DECLARATIONS (2026-08-14 incident follow-up)
#
# The mechanism landed with one union-tier user and the incident's own handoff
# left "heavy code-file fanout (engine module still selects ~121 jobs)" open.
# These fixtures pin the curation that closed it. The load-bearing one is
# test_curated_exclusive_scopes_cover_their_own_import_closure: exclusivity
# SKIPS inference, so a declaration is a promise that nothing the job actually
# imports lost its owner, and only a test that re-derives the closure and
# compares can keep that promise honest as the tree moves.
# ---------------------------------------------------------------------------

CURATED_EXCLUSIVE = {
    # 2026-08-20. `regwall-boundary` carries tests/test_regwall_json_gate.py out
    # of `tier-gate` (`gate: data`, never packed by ci.yml) and onto the merge
    # gate. It is curated for COVERAGE, not to narrow: the suite names its two
    # subjects — app/deploy/Caddyfile and config/site_access.yml — as segment
    # literals (REPO_ROOT / "app" / "deploy" / "Caddyfile"), and no segment
    # holds a `/`, so inference cannot see them and the job would not re-run on
    # the Caddyfile edit that is the whole regression class. Exclusive is what
    # makes the declared paths replace inference instead of riding a whole-tree
    # fallback tier. Sole probe delta: templates/index.html +1, from the five
    # public documents test_public_pages_fetch_nothing_under_paid_prefixes
    # actually reads; the other two probes are unmoved.
    "regwall-boundary",
    # 2026-08-19 wave 5. #6027 moved #5984's three dossier suites into
    # conviction-profile — the right call, because their #6023 home
    # (unrun-publish-ops) is `gate: data`, which ci.yml never plans, so they
    # were named by a run: step and still dark on every PR. But those suites
    # import scripts/build_ticker_pages.py and check_stock_dossier_integrity.py,
    # which rglob templates/ and site/, so the job inherited whole-tree
    # fallback claims and newly matched templates/index.html — 128 > the 127
    # ceiling below. Curated rather than paid for: its 59 concrete owned files
    # plus the two templates build_ticker_pages loads by name. Probe returns
    # to 127; weight and pack ceilings unmoved.
    "conviction-profile",
    "unrun-government-revenue-grader",
    "biocatalyst-worker",
    "biocatalyst-serving",
    "flow-surface",
    "biocatalyst-history",
    "unrun-subsector-themes",
    "inline-js",
    "unrun-picks-boards",
    "intelligence-registry",
    # 2026-08-14 wave 2: the manifest grew 180→193 jobs and the new fallback
    # riders pushed scripts/build_free_content.py to 127 > 126, redding pack-1
    # fleet-wide. Curated: the three NEW subject-guards whose owner-written
    # `paths:` cover their measured import closure (dataos-foundation widened
    # by 6 files per the audit below; momoedge/vintage covered as written).
    # dataos-identity-seams was EVALUATED AND REJECTED — its genuine closure
    # spans 43 files across engine/, so exclusivity would either lie about
    # coverage or degenerate to fallback breadth; it stays inferred, like the
    # other new riders without paths (product-experience-capture/-registry,
    # wri-risk-core).
    "dataos-foundation",
    "momoedge-browser-observe",
    "vintage-pin-fence",
    # 2026-08-14 wave 3. options-estate-guards was listed above as a rider that
    # would stay inferred; that call is superseded. #5634 gave it
    # tests/test_options_gap_discipline.py, whose closure carries an opaque
    # construct, and the resulting whole-tree fallback claim made this job a
    # NEW selector on all three ratchet probes — smear, not evidence, and the
    # reason scripts/build_free_content.py ran out of headroom. The
    # dataos-identity-seams rejection does not transfer: an engine-heavy
    # closure only degenerates to fallback breadth when it needs `engine/**`,
    # and this one does not — its 35 engine files are top-level modules plus
    # four whole subpackages, so `engine/*` + four `engine/<pkg>/**` covers the
    # closure exactly and leaves engine/prophet/** outside. Measured: 100
    # closure files, zero uncovered; fallback tier drops to (); all four
    # probes in the test below were fallback-tier before and are unmatched
    # after, so nothing owned was lost.
    #
    # Derive that closure against a FULL checkout. `site` is in
    # audit_unrun_tests.FIRST_PARTY, but site/ literals are admitted through
    # `(ROOT / rel).is_file()`, which answers False for a tree a sparse
    # worktree omitted -- so the same job derives 85 files there and silently
    # loses all 15 site/ members. The first version of this curation was
    # derived sparse, declared `site/<dir>/**` for the 13 members it could
    # see, and was red HERE on the two top-level ones it could not
    # (site/flow_desk.json, site/options.html). This test is the check that
    # catches it; a sparse local run of it is not evidence that it passes.
    "options-estate-guards",
    # 2026-08-15 wave 4. The two jobs the #5754 re-base below deferred. Both had
    # NO owned tier at all — every inferred pattern was opaque fallback — after
    # scripts/build_china_library.py gained engine/china_intel_interest.py, whose
    # lazy china_intel_hub import reaches the full altdata convergence universe.
    # Neither reads templates/index.html; both matched it, which is what took
    # that probe 127 -> 129. Curated at the source instead of paid for again.
    #
    # These two are NOT the same declaration, and the difference is the point:
    # cn-standout-audit globs `scripts/**` because two of its suites rglob that
    # tree and AST-scan every hit (test_cn_board_lane_gate.py:361,
    # test_cn_entry_price_integrity.py:527) — the tree is their SUBJECT, so
    # enumerating it would stop the guard covering the new scripts it exists to
    # catch. coiled-mtf-anchor-era's two suites carry no traversal at all, so its
    # six scripts/ files are enumerated. Both glob `collectors/**`: the dynamic
    # import at build_china_library.py:1807 resolves seven collectors.tushare_*
    # drip modules the walker cannot see, so they are invisible to the coverage
    # test and enumeration would drop them silently.
    "cn-standout-audit",
    "coiled-mtf-anchor-era",
    # 2026-08-20 main-red-repair. serving-observability (#6115, Sentry arm for
    # the macro-api serving tier) shipped with no scope at all. Its own subject
    # (_release()'s `subprocess.run(["git", ...])` for the deployed SHA) is an
    # opaque subprocess call scope inference cannot see through, so it fell back
    # to SUBPROCESS_ROOTS — including site/** and templates/** — and matched
    # every ordinary templates/index.html PR (128 > the 127 ceiling below).
    # Curated at the source: its true subject is exactly app/observability.py
    # and tests/test_observability_sentry.py, both declared and covered.
    "serving-observability",
    # 2026-08-20 main-red-repair (same wave). govrev-company-bridge (D4
    # Company Financial Truth Bridge) also shipped with no scope. Its suite's
    # own `node` subprocess call (tests/test_government_revenue_company_bridge.py:197)
    # resolves to `subprocess roots=templates,tests`, widening to templates/**
    # and matching every ordinary templates/index.html PR. Curated at the
    # source: its true subject is the frozen fixture plus the two template
    # files its own header comment already documents as the only reads.
    "govrev-company-bridge",
    # #6117 (records(dislocation): P0-A1 price-blind candidate harvest) shipped
    # its own `scope: exclusive` declaration pre-curated — registered here so
    # this file's pin does not drift from the manifest (no fix required, the
    # job's own paths: already cover its full closure).
    "dislocation-p0-a1-blind-harvest",
    # 2026-08-26 (PR #6454): the D6-A + D6-B1 defense rail batteries moved
    # onto the merge gate (they sat in gate:data unrun-government-revenue,
    # which ci.yml never plans, so both commissioned merge-binding suites
    # were dark). tests/test_fms_ui.py imports app.government_revenue for
    # its route-boundary tests, whose closure's opaque edges smear whole-tree
    # fallback claims (app/**, templates/**, site/**) — measured
    # fallback-matching all four probes below and pushing
    # templates/index.html to 130 > 129. Curated at the source, same
    # treatment as stock-dossiers / cn-standout-audit / govrev-company-bridge:
    # the declaration names the earned 563-file closure (flat engine/*.py +
    # the read subpackages, deliberately not engine/**), the frozen fixture
    # trees, and the sha-frozen staged goldens.
    "defense-rail-laws",
}


def _inferred_as_if_not_exclusive() -> dict[str, PACK.LegacyJob]:
    """What inference WOULD derive for the curated jobs, exclusivity aside.

    Thin wrapper over the shared ``scripts.run_ci_pack.inferred_as_if_not_exclusive``
    — kept so the other call sites below need no change; the computation itself now
    lives in exactly one place (see the import block above).
    """
    return inferred_as_if_not_exclusive(MANIFEST)


def test_the_curated_exclusive_set_is_actually_declared() -> None:
    """The set this file pins must be the set the manifest declares."""
    declared = {job.job_id for job in PACK.load_legacy_jobs(MANIFEST) if job.exclusive}
    assert declared == CURATED_EXCLUSIVE, sorted(declared ^ CURATED_EXCLUSIVE)


def test_curated_exclusive_scopes_cover_their_own_import_closure() -> None:
    """Zero MISS: every file a curated job imports must still select it.

    `scope: exclusive` REPLACES inference, so the declared paths are the whole
    scope — a closure file with no matching pattern is a job that stops running
    when its own dependency changes, and reports green forever. The manifest's
    load-time coverage audit only reaches the paths a job's COMMANDS name; the
    transitive import closure is one layer deeper and is checked here.

    The computation itself is ``scripts.run_ci_pack.curated_exclusive_closure_findings``
    — the same function ``scripts/check_contract_delta.py`` calls for the head side
    of its PR-vs-base delta, so this test and that gate can never quietly diverge on
    what "covered" means.
    """
    misses_full = curated_exclusive_closure_findings(MANIFEST)
    misses = {job_id: list(paths[:8]) for job_id, paths in misses_full.items()}
    assert not misses, (
        "curated exclusive scope(s) no longer cover their own import closure:\n  "
        + "\n  ".join(f"{k}: {v}" for k, v in misses.items())
        + "\n\nA new import reached a tree the declaration does not name, so that "
        "job silently stopped running for edits to it. Widen the job's `paths:` "
        "in .github/ci/legacy-jobs.yml to cover the listed files — widening is "
        "always the safe direction."
    )


def test_curated_exclusivity_drops_only_the_opaque_fallback_tier() -> None:
    """Every job the curation stops selecting was selected by smear, not evidence.

    This is the whole safety argument for the wave: exclusivity removes the
    opaque `site/**`-shaped claims a subprocess deep in the closure minted, and
    removes nothing that named the changed file as a real dependency.
    """
    would_infer = _inferred_as_if_not_exclusive()
    curated = {job.job_id: job for job in PACK.load_legacy_jobs(MANIFEST)
               if job.exclusive}
    probes = [
        "templates/index.html",
        "site/theme.css",
        "engine/prophet/plan_book.py",
        "scripts/build_free_content.py",
    ]
    owned_losses: list[str] = []
    for job_id, job in sorted(curated.items()):
        before = would_infer[job_id]
        for probe in probes:
            was = PACK._job_diff_match(before, [probe])
            now = PACK._job_diff_match(job, [probe])
            if was and not now and was[1] != "fallback":
                owned_losses.append(f"{job_id} lost {probe} (tier={was[1]})")
    assert not owned_losses, owned_losses


def test_exclusive_curation_narrows_ordinary_code_prs() -> None:
    """The measured before/after this wave exists to produce.

    Baselines on the pre-curation manifest (PR #5585 planner, 188 jobs):
    templates/index.html 129 jobs / 6,677 weight-seconds; build_free_content.py
    129 / 6,430; engine/prophet/plan_book.py 123 / 6,416. Bounds below carry
    headroom so an unrelated job gaining or losing a scope does not red this,
    while a regression that gives the fallback tier back to the curated nine
    (~1,550 weight-seconds and three of twelve packs per shape) does.

    The templates/index.html job ceiling is 128 rather than 126 because
    `engine-render-guards` split into three lanes (#5587 on top of #5586): the
    sweep still owned-matches this probe, and the two sibling lanes
    (`express-render-guards`, `attested-history-guards`) still fallback-match
    it. That is +2 jobs / +210 weight-seconds vs the single pre-split job, not
    a return of the curated eight. Weight and pack ceilings are unchanged.

    JOB COUNTS RE-BASED +1 (129/127/121) for #5620, which added ONE new job,
    `intelligence-registry` (Eval OS T1). Measured against the pre-#5620
    manifest, it is the sole newcomer on all three probes and the ONLY delta:

        templates/index.html          128 -> 129 jobs, 5,253 -> 5,266 weight
        scripts/build_free_content.py 126 -> 127 jobs, 5,016 -> 5,029 weight
        engine/prophet/plan_book.py   120 -> 121 jobs, 5,002 -> 5,015 weight

    +13 weight-seconds per probe. The WEIGHT and PACK ceilings are deliberately
    NOT moved: they are what bound the incident this wave exists to prevent, and
    a regression that gave the fallback tier back to the curated eight would be
    ~1,550 weight-seconds and three of twelve packs — two orders of magnitude
    above this, so it still reds here. What moved is only the job count, and only
    because the previous bounds carried zero headroom on that axis: 128/126/120
    were the exact pre-#5620 measurements, so the very first honest new job
    breached all three. The docstring above promises headroom "so an unrelated
    job gaining or losing a scope does not red this"; `intelligence-registry` is
    exactly such a job, and that promise was not funded. Re-based to the new
    measurement rather than padded, so the next new job is again a visible event.

    This re-base is the same change carried by PR #5669 (authored there first).
    It is duplicated here because both fixes land in the SAME `workflow-yaml`
    job: run_ci_pack abandons a job's remaining steps on the first non-zero
    exit, so this assertion (step 5) masks `audit_unrun_tests.py` (step 12).
    A PR that healed only one of the two would leave `ci-pack-1` red and neither
    PR could ever merge — the two-partial-heals deadlock. Whichever lands second
    resolves to an identical tree.

    JOB COUNTS LOWERED to 127/124/119 (wave 3, 2026-08-14). The re-base above
    absorbed TWO newcomers on the two code probes, and only one of them was
    evidence. `intelligence-registry` matched on the DECLARED tier and stands.
    `options-estate-guards` matched on the FALLBACK tier: #5634 gave it
    tests/test_options_gap_discipline.py, an opaque construct in that suite's
    closure widened it to whole-tree scan roots, and it began selecting on
    files it does not read. That is smear, so it is curated away at the source
    (`scope: exclusive` in the manifest) rather than paid for here.

    Re-measured on the curated manifest, `options-estate-guards` is the sole
    delta and the ONLY job that leaves any probe:

        templates/index.html          127 -> 126 jobs, 5,259 -> 5,235 weight
        scripts/build_free_content.py 124 -> 123 jobs, 5,009 -> 4,985 weight
        engine/prophet/plan_book.py   119 -> 118 jobs, 5,001 -> 4,977 weight

    The ceilings are set at measurement + 1, not at measurement. The #5620
    re-base note above diagnosed zero headroom as the defect — "the very first
    honest new job breached all three" — and then re-based exact, funding the
    docstring's headroom promise with nothing again. One job of slack absorbs
    the next honest newcomer and still makes the second a visible event. Note
    the pre-curation measurements had already drifted BELOW the 129/127/121
    ceilings as later curation waves landed, so those bounds carried accidental
    slack of 2-3 jobs; this restores a ratchet that is tight on purpose.

    WEIGHT and PACK ceilings are again deliberately NOT moved, for the reason
    given above: they bound the incident, and a fallback-tier regression is
    ~1,550 weight-seconds — two orders of magnitude above the 24 removed here.

    JOB COUNT RE-BASED +2 on templates/index.html only (129, 2026-08-15).
    ``engine/china_intel_interest.py`` lazy-imports ``china_intel_hub``, and
    that hub's opaque constructs smear ``templates/**`` onto two inferred
    jobs that already imported ``build_china_library`` /
    ``china_standout_track`` (``cn-standout-audit``,
    ``coiled-mtf-anchor-era``). Measured 126 → 128 on this probe; the other
    two probes are unchanged. Weight and pack ceilings stay. Exclusive
    curation of those two jobs is the smear-at-source fix, but their
    closures run through ``build_china_library`` and would be a third
    exclusive-scope wave, not this packing-contract heal.

    THAT DEFERRAL IS NOW PAID (wave 4, 2026-08-15). Both jobs are curated
    ``scope: exclusive`` in the manifest, and the ceiling above comes back
    DOWN from 129 to 127. Neither job had an owned tier at all before this —
    every one of their 28 inferred patterns was opaque fallback, so they
    selected on ``*`` and on whole trees no suite in them reads. Re-measured
    on the curated manifest, they are the ONLY delta and NOTHING was added to
    any probe:

        templates/index.html          128 -> 126 jobs, 5,310 -> 5,292 weight
        scripts/build_free_content.py 123 -> 122 jobs, 5,044 -> 5,038 weight
        engine/prophet/plan_book.py   118 -> 118 jobs, 5,040 -> 5,040 weight

    Both jobs leave templates/index.html; only ``coiled-mtf-anchor-era``
    leaves build_free_content.py, because ``cn-standout-audit`` KEEPS
    ``scripts/**`` on the declared tier — two of its suites rglob that tree
    and AST-scan every hit for unlaned CN sink calls, so the tree is their
    subject and narrowing it would be the silent-stop failure this file's
    coverage test exists to prevent. Both keep ``engine/**`` for the same
    kind of reason, which is why plan_book.py does not move at all. That is
    the shape a correct curation has: it removes the fallback claims and
    keeps every earned one.

    The ceiling is set at measurement + 1 per the wave-3 note above, so 126
    measured -> 127. Note this lands exactly where wave 3 had it before
    #5754, which is the confirmation that these two jobs were the whole of
    that +2 and that no other drift hid inside the re-base. WEIGHT and PACK
    ceilings are again NOT moved: the 18 weight-seconds removed here are two
    orders of magnitude below the ~1,550 a fallback-tier regression costs,
    and packs were 9 on every probe before and after.

    JOB COUNT RE-BASED +1 on engine/prophet/plan_book.py only (120, wave 6,
    2026-08-20 main-red-repair). Measured against the last lane-green main
    commit (d972484c6474): baseline selects 119/195 jobs for this probe;
    the current manifest selects 120/196, and diffing the two selected-job
    NAME sets (not just counts) isolates the entire delta to one job,
    ``reference-integrity`` — present in both manifests, but newly matching
    this probe. #6122 (XPV2-SC-R3A, commit f4305a4485f6) added a third step
    to that already-existing job (`tests/test_xpv2_sector_r3_fixture.py`,
    over the frozen Sector Central fixture), and that suite's import closure
    carries several ``dynamic import`` / ``subprocess invocation``
    ambiguities several hops deep (engine/alert_triage.py,
    engine/codex_lane/runner.py) that resolve to CODE_SCAN_ROOTS/
    SUBPROCESS_ROOTS, which include ``engine/**`` — hence the new match on
    engine/prophet/plan_book.py specifically, not anything Sector Central or
    Prophet actually share.

    This is NOT curated away like serving-observability's smear (2026-08-20
    main-red-repair, same wave) or curated like dataos-identity-seams was
    REJECTED (wave 2 note above): reference-integrity's own header comment
    documents it as deliberately unscoped — "Unscoped on purpose: L7/L8/L9
    are namespace and coupling closures over mockups/design_system,
    research/migration_packets and the page registry, so a diff that adds a
    file anywhere in those roots must re-run this" — a whole-tree RIG V1
    reference-integrity gate that already existed pre-#6122 and is meant to
    fire broadly. Declaring `scope: exclusive` on a job whose real purpose is
    "catch reference laundering anywhere in these wide namespaces" would
    either lie about coverage or degenerate straight back to the fallback
    breadth it already carries — the identical failure mode
    dataos-identity-seams was rejected for. One extra match on an
    already-broad, already-reviewed, always-on gate costs nothing over the
    ~1,550 weight-seconds/3-pack fallback-regression bound this file guards;
    ratcheting the ceiling is the correct-risk response, not curation.
    WEIGHT and PACK ceilings stay unmoved (5,600 / 9 packs, unchanged).

    JOB COUNTS RE-BASED to 129/125/121 (wave 7, 2026-08-21) — a ratchet on the
    templates probe, and the wave-3 headroom promise re-funded on all three.
    Measured against the last commit at which this job's own lane was green
    (48bfd3c97e8a, data-health run 32380507121), diffing the selected-job NAME
    sets isolates one sole entrant per probe and nothing leaves:

        templates/index.html          127 -> 128 jobs, 5,390 -> 5,420 weight
        scripts/build_free_content.py 123 -> 124 jobs, 5,141 -> 5,173 weight
        engine/prophet/plan_book.py   119 -> 120 jobs, 5,143 -> 5,175 weight

    Only templates/index.html BREACHED (128 > 127). Its sole entrant is
    ``regwall-boundary``, the new ``gate: code`` job #6141 added so that
    tests/test_regwall_json_gate.py — whose only CI home had been the
    ``gate: data`` job ``tier-gate``, i.e. off the merge gate entirely — can
    actually block a merge. It matches on the DECLARED tier, not fallback:
    #6141 gave it an explicit ``scope: exclusive`` + ``paths:`` precisely
    because that suite names its subjects as segment literals
    (``REPO_ROOT / "templates" / "index.html"``, tests/test_regwall_json_gate.py:102),
    which SCOPE_REFERENCE_RE cannot see. So this is the ``intelligence-registry``
    case verbatim (wave 3 note above), not the ``options-estate-guards`` smear:
    there is no fallback claim to curate away, because the job arrived already
    curated to the narrowest honest scope it has. Narrowing it further would
    drop ``templates/index.html`` from the declaration of the one job whose
    entire purpose is to assert the regwall boundary inside that file — a
    silent false green, and ``curated_exclusive_closure_findings`` would hard-
    fail the manifest for it anyway. Ratcheting is the correct-risk response.

    The other two probes did NOT breach — but both sat at EXACTLY their
    ceiling (124/124 and 120/120), which is the zero-headroom defect the #5620
    note above already diagnosed once ("the very first honest new job breached
    all three") and which wave 6 re-introduced by re-basing plan_book exact.
    That is how this red reached main unseen: ``workflow-yaml`` is itself
    ``gate: data``, so under W2 of
    research/CI_MERGE_GATE_RELIABILITY_ROOT_CAUSE_2026_08_19.md this assertion
    is packed only by data-health.yml, which has no ``pull_request`` trigger —
    no PR can be blocked by it, so a zero-headroom ceiling does not red the
    newcomer's PR, it reds MAIN, silently, one commit later. All three are
    therefore set at measurement + 1 per the wave-3 rule, restoring the one
    job of slack that makes the NEXT newcomer a visible event rather than a
    fait accompli. WEIGHT and PACK ceilings stay unmoved (5,800 / 5,600 /
    5,600 and 10 packs): weights are 5,420 / 5,173 / 5,175, and a fallback-
    tier regression is still ~1,550 weight-seconds above them, so the bound
    this file exists to hold is untouched.
    """
    jobs, _ = PACK.infer_job_scopes(PACK.load_legacy_jobs(MANIFEST))
    for probe, max_jobs, max_weight in (
        ("templates/index.html", 129, 5_800),
        ("scripts/build_free_content.py", 125, 5_600),
        ("engine/prophet/plan_book.py", 121, 5_600),
    ):
        selected, reason = PACK.select_jobs(jobs, [probe])
        weight = sum(job.weight for job in selected)
        assert len(selected) <= max_jobs, (probe, len(selected), reason)
        assert weight <= max_weight, (probe, weight, reason)
        # Runners are what the incident actually spends: build_plan derives the
        # pack count from the SELECTED weight, so the weight cut above is a
        # runner cut. Twelve packs per shape was the pre-curation measurement.
        packs = max(1, min(12, -(-weight // PACK.PACK_TARGET_SECONDS)))
        assert packs <= 10, (probe, packs, weight, reason)


def test_inline_js_owns_the_rendered_tree_it_lints() -> None:
    """`check_inline_js.py site templates` names both trees as BARE argv.

    No `/` means SCOPE_REFERENCE_RE never saw a path, so this linter's real
    subject lived only in the opaque fallback tier — one tier-split away from
    a site edit silently not running the site linter. The declaration makes
    that ownership explicit, which is a correctness fix, not a narrowing.
    """
    jobs = {job.job_id: job for job in PACK.load_legacy_jobs(MANIFEST)}
    inline_js = jobs["inline-js"]
    assert inline_js.exclusive
    for probe in ("site/theme.css", "site/index.html", "templates/index.html"):
        match = PACK._job_diff_match(inline_js, [probe])
        assert match and match[1] == "declared", (probe, match)


def test_exclusive_scope_replaces_inference_and_audits_coverage(tmp_path: Path) -> None:
    """`scope: exclusive` is declared-wins: inference must not re-widen it.

    And the coverage audit is FATAL for it: an exclusive job whose commands
    name a file outside its declared paths must refuse to load — mis-declaring
    narrow has to be loud, because the silent version is a guard that stops
    running on the PRs that can break it.
    """
    workflow = tmp_path / "legacy.yml"
    workflow.write_text(
        """
jobs:
  curated:
    if: ${{ false }}
    runs-on: ubuntu-latest
    scope: exclusive
    paths:
      - "engine/example/**"
    steps:
      - name: curated semantic proof
        run: echo engine/example only
  plain:
    if: ${{ false }}
    runs-on: ubuntu-latest
    steps:
      - name: plain semantic proof
        run: echo unscoped
""",
        encoding="utf-8",
    )
    jobs = PACK.load_legacy_jobs(workflow)
    curated = {job.job_id: job for job in jobs}["curated"]
    assert curated.exclusive and curated.paths == ("engine/example/**",)
    inferred, _ = PACK.infer_job_scopes(jobs)
    curated_after = {job.job_id: job for job in inferred}["curated"]
    assert curated_after.paths == ("engine/example/**",)
    assert curated_after.fallback_paths == ()

    bad = tmp_path / "bad.yml"
    bad.write_text(
        """
jobs:
  curated:
    if: ${{ false }}
    runs-on: ubuntu-latest
    scope: exclusive
    paths:
      - "engine/example/**"
    steps:
      - name: outside-scope semantic proof
        run: python -m pytest tests/test_ci_pack.py -q
""",
        encoding="utf-8",
    )
    with pytest.raises(PACK.ManifestError, match="do not cover"):
        PACK.load_legacy_jobs(bad)

    empty = tmp_path / "empty.yml"
    empty.write_text(
        """
jobs:
  curated:
    if: ${{ false }}
    runs-on: ubuntu-latest
    scope: exclusive
    steps:
      - run: echo no paths declared
""",
        encoding="utf-8",
    )
    with pytest.raises(PACK.ManifestError, match="scope: exclusive but no paths"):
        PACK.load_legacy_jobs(empty)


def _released_cpython_versions() -> set[tuple[int, int, int]]:
    """Patch releases `document_terms` will accept, read without importing it.

    The module is parsed rather than imported on purpose. Importing it executes
    `_make_validate_released_parser_runtime`, which seals itself against the
    *running* interpreter — so on an unreleased CPython the import path is
    exactly the thing under test, and a guard that dies the same way it is
    meant to detect proves nothing.
    """
    source = (ROOT / "engine" / "capital_structure" / "document_terms.py").read_text()
    tree = ast.parse(source)
    allowlist = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_PARSER_V1_1_0_RUNTIME_ALLOWLIST"
            for t in node.targets
        ):
            allowlist = node.value
            break
    assert allowlist is not None, (
        "_PARSER_V1_1_0_RUNTIME_ALLOWLIST vanished from document_terms.py — this "
        "guard pins CI's Python against it and must be re-pointed, not deleted"
    )
    # MappingProxyType({...}) -> unwrap to the dict literal.
    if isinstance(allowlist, ast.Call):
        allowlist = allowlist.args[0]
    assert isinstance(allowlist, ast.Dict)

    versions: set[tuple[int, int, int]] = set()
    for key in allowlist.keys:
        assert isinstance(key, ast.Call), "allowlist keys are ParserRuntimeFingerprint(...)"
        for kw in key.keywords:
            if kw.arg != "version_info":
                continue
            parts = ast.literal_eval(kw.value)
            versions.add((int(parts[0]), int(parts[1]), int(parts[2])))
    assert versions, "no version_info keys parsed out of the runtime allowlist"
    return versions


def test_ci_python_is_pinned_to_a_released_parser_runtime() -> None:
    """A floating `python-version` lets a tool-cache bump red the whole fleet.

    `engine/capital_structure/document_terms.py` seals its parser behind an
    allowlist keyed on `sys.version_info` plus stdlib source digests, so a
    CPython PATCH bump produces an unreleased fingerprint and the parser fails
    closed — 22 tests at once, in whichever pack currently owns
    `capital-structure-intelligence`, on every PR regardless of its diff.

    Measured 2026-08-19: the hosted tool cache moved 3.12.13 -> 3.12.14,
    `python-version: "3.12"` followed it, and ci-pack-8 went red on two
    independent heads (#5737, #5903) with an identical failure neither PR's
    files could cause. The self-hosted lanes stayed green on Homebrew 3.12.13.

    So the pin must be EXACT and must name a release the allowlist carries.
    Moving it is therefore ordered: extend the allowlist first (a review act
    owned by the Capital Structure Intelligence lane), bump the pin second.
    """
    released = _released_cpython_versions()
    workflow = _yaml(WORKFLOW)

    pins: list[tuple[str, str]] = []
    for job_name, job in (workflow.get("jobs") or {}).items():
        for step in job.get("steps") or []:
            uses = str(step.get("uses") or "")
            if not uses.startswith("actions/setup-python"):
                continue
            pins.append((job_name, str((step.get("with") or {}).get("python-version", ""))))

    assert pins, "ci.yml no longer calls actions/setup-python — re-point this guard"

    for job_name, pin in pins:
        parts = pin.split(".")
        assert len(parts) == 3 and all(p.isdigit() for p in parts), (
            f"ci.yml job {job_name!r} pins python-version={pin!r}. A floating pin "
            "follows the hosted tool cache onto CPython releases the "
            "capital-structure parser allowlist has never reviewed, which reds "
            "every PR at once. Pin an exact major.minor.patch."
        )
        version = (int(parts[0]), int(parts[1]), int(parts[2]))
        assert version in released, (
            f"ci.yml job {job_name!r} pins CPython {pin}, which is NOT in "
            "_PARSER_V1_1_0_RUNTIME_ALLOWLIST in "
            "engine/capital_structure/document_terms.py "
            f"(released: {sorted('.'.join(map(str, v)) for v in released)}). "
            "Add the release to that allowlist first — with provenance, the way "
            "the 3.12.13 entry records its actions/python-versions archive "
            "SHA-256 — then bump this pin."
        )


# ---------------------------------------------------------------------------
# W2 of research/CI_MERGE_GATE_RELIABILITY_ROOT_CAUSE_2026_08_19.md: the merge
# gate packs only `gate: code` legacy jobs; `gate: data` jobs move to the
# post-nightly data-health.yml lane. `--gate` is the mechanism (load_legacy_jobs
# filters immediately, before any partition/weight arithmetic); the two tests
# below guard the mechanism itself and that every production caller actually
# uses it, so a future edit cannot silently widen the merge gate back to 194.
# ---------------------------------------------------------------------------

DATA_HEALTH_WORKFLOW = ROOT / ".github" / "workflows" / "data-health.yml"


def test_gate_filter_selects_only_matching_jobs(tmp_path: Path) -> None:
    """`--gate` (via `load_legacy_jobs(gate=...)`) is a strict partition.

    A synthetic two-job manifest — one `gate: code`, one `gate: data` — proves
    `code` selection excludes the data job and vice versa, and that omitting
    `gate` entirely (the pre-W2 default) still returns both, unchanged.
    """
    workflow = tmp_path / "ci.yml"
    workflow.write_text(
        """
jobs:
  ci-pack:
    runs-on: ubuntu-latest
    steps:
      - run: echo pack
  code-job:
    if: ${{ false }}
    runs-on: ubuntu-latest
    gate: code
    steps:
      - name: code step
        proof_id: code-step
        run: echo code
  data-job:
    if: ${{ false }}
    runs-on: ubuntu-latest
    gate: data
    steps:
      - name: data step
        proof_id: data-step
        run: echo data
"""
    )

    code_only = PACK.load_legacy_jobs(workflow, gate="code")
    assert [job.job_id for job in code_only] == ["code-job"]

    data_only = PACK.load_legacy_jobs(workflow, gate="data")
    assert [job.job_id for job in data_only] == ["data-job"]

    unfiltered = PACK.load_legacy_jobs(workflow)
    assert sorted(job.job_id for job in unfiltered) == ["code-job", "data-job"]

    # partition_jobs only ever sees what it is handed — proving the filter
    # runs before partitioning, not merely that the loader can produce it.
    code_packs = PACK.partition_jobs(code_only, 3)
    assert sum(len(pack) for pack in code_packs) == 1
    assert "data-job" not in [job.job_id for pack in code_packs for job in pack]


def _run_ci_pack_invocation_blocks(text: str) -> list[str]:
    """Every shell block that actually invokes run_ci_pack.py, as raw text.

    Matches only an interpreter invocation (`.../bin/python" scripts/
    run_ci_pack.py`), never a `paths:` trigger entry or a prose/comment
    mention of the filename — both of which also appear in ci.yml. A block
    runs from the invocation line through every following line indented AT
    LEAST as deep as it (YAML nesting, not blank lines: this file has no
    blank line between many adjacent steps, so a blank-line terminator
    swallows unrelated later steps — verified against the false positive
    that shape produced here). This covers both invocation shapes used in
    this repo: the `>-` folded-scalar argument list, whose continuation
    lines sit at the SAME indentation as the interpreter line, and the
    backslash-continued `run: |` block, whose continuation lines sit deeper.
    Either way the block ends at the first line that DEDENTS below the
    interpreter line — the next YAML key/step.
    """
    lines = text.splitlines()
    invocation_re = re.compile(r'bin/python"?\s+scripts/run_ci_pack\.py\b')
    blocks: list[str] = []
    index = 0
    while index < len(lines):
        if invocation_re.search(lines[index]):
            indent = len(lines[index]) - len(lines[index].lstrip(" "))
            block: list[str] = [lines[index]]
            cursor = index + 1
            while cursor < len(lines):
                line = lines[cursor]
                if not line.strip():
                    cursor += 1
                    continue
                line_indent = len(line) - len(line.lstrip(" "))
                if line_indent < indent:
                    break
                block.append(line)
                cursor += 1
            blocks.append("\n".join(block))
            index = cursor
        else:
            index += 1
    return blocks


# Workflows allowed to invoke run_ci_pack.py WITHOUT an explicit --gate, each
# with a reason a reviewer can check. This is a NAMED exception list, not a
# way to silence the guard — adding an entry here must be a deliberate,
# reasoned call, the same way GATE_VALUES itself is deliberate.
GATE_REACHABILITY_ALLOWLIST: dict[str, str] = {
    "selfhosted-ci-canary.yml": (
        "deliberate full-suite parity/contamination canary: it exists to "
        "compare self-hosted runner output against the hosted baseline over "
        "the COMPLETE manifest, so narrowing it to one gate would defeat its "
        "purpose"
    ),
}


def test_no_data_gated_job_is_reachable_from_ci_gate() -> None:
    """Every merge-gate invocation of run_ci_pack.py passes `--gate code`.

    This is the reachability half of the W2 guard: it is not enough for the
    `--gate` flag to exist and work (see the unit test above) — every actual
    caller inside ci.yml (the plan step and both pack-execution paths, plan-
    json and the unpinned fail-safe fallback) must pass it, or a `gate: data`
    job stays reachable from the merge gate despite the split. Symmetrically,
    data-health.yml's own invocation must pass `--gate data`, or the new lane
    silently re-runs (or worse, never runs) the wrong half of the manifest.

    Widened (Opus review of commit 18e0f878) to enumerate EVERY workflow file
    repo-wide, not just ci.yml and data-health.yml: a run_ci_pack.py call
    anywhere without an explicit --gate is exactly the kind of silent
    reachability hole this guard exists to catch, whichever workflow it is
    added to later. `GATE_REACHABILITY_ALLOWLIST` is the one permitted
    exception, and it is named and reasoned, not blanket.
    """
    ci_text = WORKFLOW.read_text()
    ci_blocks = _run_ci_pack_invocation_blocks(ci_text)
    assert len(ci_blocks) == 3, (
        f"expected exactly 3 run_ci_pack.py invocations in ci.yml (ci-plan, "
        f"the plan-json pack execution, and the unpinned fallback), found "
        f"{len(ci_blocks)}: re-point this guard if ci.yml's call sites changed"
    )
    for block in ci_blocks:
        assert "--gate code" in block, (
            "a run_ci_pack.py invocation in ci.yml is missing --gate code — "
            "this would leave a gate: data job reachable from the merge gate:\n"
            + block
        )

    assert DATA_HEALTH_WORKFLOW.exists(), (
        "W2 of research/CI_MERGE_GATE_RELIABILITY_ROOT_CAUSE_2026_08_19.md "
        "requires .github/workflows/data-health.yml to exist"
    )
    data_health_text = DATA_HEALTH_WORKFLOW.read_text()
    data_health_blocks = _run_ci_pack_invocation_blocks(data_health_text)
    assert data_health_blocks, "data-health.yml never invokes run_ci_pack.py"
    for block in data_health_blocks:
        assert "--gate data" in block, (
            "a run_ci_pack.py invocation in data-health.yml is missing "
            "--gate data:\n" + block
        )

    data_health_workflow = _yaml(DATA_HEALTH_WORKFLOW)
    for job_name, job in (data_health_workflow.get("jobs") or {}).items():
        runs_on = job.get("runs-on")
        assert runs_on == "ubuntu-latest" or (
            isinstance(runs_on, list) and "self-hosted" not in runs_on
        ), (
            f"data-health.yml job {job_name!r} runs on {runs_on!r} — this lane "
            "must stay on GitHub-hosted runners, never self-hosted "
            "(CLAUDE.md — render/nightly compute stays off this pool)"
        )

    # Repo-wide sweep: any OTHER workflow (present or future) that invokes
    # run_ci_pack.py must carry an explicit --gate, unless it is named in
    # GATE_REACHABILITY_ALLOWLIST above.
    workflows_dir = ROOT / ".github" / "workflows"
    gate_flag_re = re.compile(r"--gate\s+(?:code|data)\b")
    for workflow_path in sorted(workflows_dir.glob("*.yml")):
        name = workflow_path.name
        if name in {"ci.yml", "data-health.yml"}:
            continue  # already fully covered above
        blocks = _run_ci_pack_invocation_blocks(workflow_path.read_text())
        if not blocks:
            continue
        if name in GATE_REACHABILITY_ALLOWLIST:
            continue
        for block in blocks:
            assert gate_flag_re.search(block), (
                f"{name} invokes run_ci_pack.py without an explicit --gate — "
                "either pass --gate code/data or add a NAMED, reasoned entry "
                f"to GATE_REACHABILITY_ALLOWLIST:\n{block}"
            )


def test_no_empty_pack_in_the_code_gate_partition() -> None:
    """An empty ci-pack-N under the code gate would vanish from main's baseline.

    ci-gate's base-inherited-red refresh resolves a PR's failing check NAMES
    against main's own newest concluded ci.yml run by NAME (CLAUDE.md
    "green proof against a stale base"; #5037). A pack index with zero jobs
    still has to exist and publish a name on main's baseline, or a PR whose
    plan happens to land work on that index has no baseline check of the same
    name to compare against, and any red there becomes permanently
    unrefreshable. The load-bearing property is "no pack is empty" — not any
    particular per-pack job count, which shifts as the manifest grows.
    """
    jobs = PACK.load_legacy_jobs(MANIFEST, gate="code")
    packs = PACK.partition_jobs(jobs, 12)
    empty = [index for index, pack in enumerate(packs) if not pack]
    assert not empty, (
        f"pack index(es) {empty} are empty under --gate code with --pack-count "
        "12 — an empty pack's name would vanish from main's ci.yml baseline "
        "and any PR whose plan lands work there could never refresh a red"
    )
