from __future__ import annotations

import ast
import importlib.util
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from scripts import ci_semantic_proof as SEMANTIC
from scripts import run_ci_pack as RUN_PACK


ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SELECT = load("select_ci_canary_packs", ROOT / "scripts" / "select_ci_canary_packs.py")
RESOLVE = load("resolve_ci_canary_ref", ROOT / "scripts" / "resolve_ci_canary_ref.py")
PREWARM = ROOT / "ops" / "runner-host" / "pc" / "mastermind_ci_prewarm.py"
ADMISSION = load(
    "runner_admission", ROOT / "ops" / "runner-host" / "common" / "runner_admission.py"
)
CLEANUP = load(
    "runner_cleanup", ROOT / "ops" / "runner-host" / "common" / "runner_cleanup.py"
)
RESOURCE_GUARD = load(
    "mastermind_ci_resource_guard",
    ROOT / "ops" / "runner-host" / "pc" / "mastermind_ci_resource_guard.py",
)
COMPARE = load("compare_ci_canary_receipts", ROOT / "scripts" / "compare_ci_canary_receipts.py")
CAPTURE = load("capture_ci_canary_receipt", ROOT / "scripts" / "capture_ci_canary_receipt.py")


def git(cwd: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def cache_fixture(tmp_path: Path) -> tuple[Path, str]:
    source = tmp_path / "source"
    source.mkdir()
    git(source, "init")
    git(source, "config", "user.name", "Canary Test")
    git(source, "config", "user.email", "canary@example.invalid")
    (source / "tracked.txt").write_text("cache-backed\n", encoding="utf-8")
    git(source, "add", "tracked.txt")
    git(source, "commit", "-m", "seed")
    sha = git(source, "rev-parse", "HEAD")
    cache = tmp_path / "cache.git"
    subprocess.run(["git", "clone", "--bare", str(source), str(cache)], check=True, capture_output=True)
    git(cache, "remote", "set-url", "origin", "https://github.com/mastermindx-market-intelligence/macro.git")
    (cache / ".mastermind-cache-identity.json").write_text(
        json.dumps({"schema": "mastermind.ci_git_cache.v1", "repository": "mastermindx-market-intelligence/macro"}) + "\n",
        encoding="utf-8",
    )
    for path in sorted(cache.rglob("*"), reverse=True):
        if path.is_symlink():
            continue
        mode = path.stat().st_mode
        path.chmod(mode & ~(stat.S_IWGRP | stat.S_IWOTH))
    cache.chmod(cache.stat().st_mode & ~(stat.S_IWGRP | stat.S_IWOTH))
    return cache, sha


def run_prewarm(cache: Path, workspace: Path, sha: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "python3",
            str(PREWARM),
            "--cache",
            str(cache),
            "--workspace",
            str(workspace),
            "--repository",
            "mastermindx-market-intelligence/macro",
            "--repository-url",
            "https://github.com/mastermindx-market-intelligence/macro.git",
            "--base-sha",
            sha,
            "--expected-owner-uid",
            str(os.getuid()),
        ],
        text=True,
        capture_output=True,
        check=False,
    )


def test_shared_cache_prewarm_materializes_without_origin(tmp_path: Path) -> None:
    cache, sha = cache_fixture(tmp_path)
    workspace = tmp_path / "workspace"
    result = run_prewarm(cache, workspace, sha)
    assert result.returncode == 0, result.stdout + result.stderr
    assert git(workspace, "rev-parse", "HEAD") == sha
    assert (workspace / "tracked.txt").read_text(encoding="utf-8") == "cache-backed\n"
    assert (workspace / ".git" / "objects" / "info" / "alternates").read_text(encoding="utf-8").strip() == str((cache / "objects").resolve())


def test_missing_cache_fails_before_workspace_initialization(tmp_path: Path) -> None:
    result = run_prewarm(tmp_path / "absent.git", tmp_path / "workspace", "0" * 40)
    assert result.returncode == 66
    assert "shared cache unavailable" in result.stdout
    assert not (tmp_path / "workspace" / ".git").exists()


def test_wrong_cache_identity_fails_closed(tmp_path: Path) -> None:
    cache, sha = cache_fixture(tmp_path)
    marker = cache / ".mastermind-cache-identity.json"
    marker.chmod(0o644)
    marker.write_text(
        json.dumps({"schema": "mastermind.ci_git_cache.v1", "repository": "somewhere/else"}),
        encoding="utf-8",
    )
    result = run_prewarm(cache, tmp_path / "workspace", sha)
    assert result.returncode == 66
    assert "identity mismatch" in result.stdout


def test_selector_uses_current_weights_not_a_fixed_pack_number() -> None:
    plan = {
        "schema": SELECT._PLAN_SCHEMA,
        "packs": [
            {"index": 0, "weight": 2, "jobs": ["small"]},
            {"index": 7, "weight": 99, "jobs": ["heavy"]},
            {"index": 4, "weight": 50, "jobs": ["middle"]},
        ],
    }
    assert [item["index"] for item in SELECT.select(plan, 1)] == [7]
    assert [item["index"] for item in SELECT.select(plan, 3)] == [7, 4, 0]


def test_selector_schema_literal_matches_the_live_planner_and_refuses_a_stale_one() -> None:
    """The 2026-08-25 (#6351) defect: a hardcoded 'ci.pack_plan.v1' literal here
    rejected every plan.json the pack runner actually emits (schema
    'ci.pack_plan.v2'), so the canary's own `select` step could never
    succeed. This selector must stay a stdlib-only self-contained script (it
    is copied alone into a trusted-control directory outside the untrusted
    candidate checkout — see the comment in select_ci_canary_packs.py), so it
    cannot import scripts.ci_semantic_proof.PLAN_SCHEMA directly; pin the
    literal against the live constant here instead, and pin that a
    stale/foreign schema is still refused.
    """
    from scripts import ci_semantic_proof as SEMANTIC

    assert SELECT._PLAN_SCHEMA == SEMANTIC.PLAN_SCHEMA == "ci.pack_plan.v2"
    stale_plan = {
        "schema": "ci.pack_plan.v1",
        "packs": [{"index": 0, "weight": 1, "jobs": ["only"]}],
    }
    with pytest.raises(ValueError, match="unexpected CI plan schema"):
        SELECT.select(stale_plan, 1)


def _fragment(**overrides: object) -> dict:
    base = {
        "schema": "ci.semantic_fragment.v1",
        "workflow_run_id": "123",
        "workflow": "infrastructure-selfhosted-ci-canary",
        "event": "workflow_dispatch",
        "role": "pr_head",
        "tested_tree_sha": "a" * 40,
        "subject_head_sha": "b" * 40,
        "base_sha": "c" * 40,
        "plan_sha256": "d" * 64,
        "pack_index": 0,
        "infrastructure": [],
        "jobs": [{"logical_job_id": "demo", "outcome": "passed"}],
    }
    base.update(overrides)
    return base


def _receipt(**overrides: object) -> dict:
    base = {
        "tested_sha": "a" * 40,
        "base_sha": "c" * 40,
        "pack": 0,
        "plan_sha256": "d" * 64,
        "logical_jobs": ["demo"],
        "executed_jobs": ["demo"],
        "failed_jobs": [],
        "result": "passed",
    }
    base.update(overrides)
    return base


def test_compare_never_touches_merge_authority_reconciliation() -> None:
    """Diagnostic-only comparator (#6351 spec C.6): this workflow never calls
    scripts.merge_on_green, and the comparator must never import
    ci_semantic_proof.reconcile_evidence or any other merge-gating entry
    point — only the pure canonicalization helpers.
    """
    assert not hasattr(COMPARE, "reconcile_evidence")
    assert not hasattr(COMPARE, "merge_on_green")
    tree = ast.parse(
        (ROOT / "scripts" / "compare_ci_canary_receipts.py").read_text(encoding="utf-8")
    )
    imported_names = {
        alias.asname or alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert "merge_on_green" not in imported_names
    assert "reconcile_evidence" not in imported_names


def test_compare_requires_strict_canonical_fragment_equality() -> None:
    hosted = _receipt()
    selfhosted = _receipt()
    hosted_fragment = _fragment()
    selfhosted_fragment = _fragment()
    assert COMPARE.compare(hosted, selfhosted, hosted_fragment, selfhosted_fragment) == {}

    # Identical identity, different content -> canonical digest catches it.
    diverged = _fragment(jobs=[{"logical_job_id": "demo", "outcome": "failed"}])
    mismatches = COMPARE.compare(hosted, selfhosted, hosted_fragment, diverged)
    assert "fragment_canonical_sha256" in mismatches


def test_compare_flags_fragment_identity_mismatch_before_the_digest() -> None:
    hosted = _receipt()
    selfhosted = _receipt()
    hosted_fragment = _fragment()
    wrong_identity = _fragment(tested_tree_sha="f" * 40)
    mismatches = COMPARE.compare(hosted, selfhosted, hosted_fragment, wrong_identity)
    assert "fragment_tested_tree_sha" in mismatches
    # Identity validation happens FIRST and short-circuits the byte compare.
    assert "fragment_canonical_sha256" not in mismatches


def test_compare_flags_wrong_fragment_schema() -> None:
    hosted = _receipt()
    selfhosted = _receipt()
    hosted_fragment = _fragment()
    bad_schema = _fragment(schema="ci.semantic_fragment.v0")
    mismatches = COMPARE.compare(hosted, selfhosted, hosted_fragment, bad_schema)
    assert "selfhosted_fragment_schema" in mismatches


def test_compare_cross_checks_fragment_identity_against_the_receipt() -> None:
    hosted = _receipt(tested_sha="a" * 40)
    selfhosted = _receipt(tested_sha="a" * 40)
    hosted_fragment = _fragment(tested_tree_sha="e" * 40)
    selfhosted_fragment = _fragment(tested_tree_sha="e" * 40)
    mismatches = COMPARE.compare(hosted, selfhosted, hosted_fragment, selfhosted_fragment)
    assert mismatches == {
        "fragment_receipt_identity": {
            "hosted_fragment_tested_tree_sha": "e" * 40,
            "hosted_receipt_tested_sha": "a" * 40,
        }
    }


def test_capture_receipt_records_fragment_reference_and_bumps_schema(tmp_path: Path) -> None:
    """Materialization-receipt amendment (D, #6351): the receipt now carries
    a v2 schema and a reference to the semantic fragment the same pack
    invocation emitted, so a reader can cross-check receipt identity
    against fragment identity without re-deriving it.
    """
    plan = {"plan_sha256": "d" * 64, "packs": [{"index": 0, "jobs": ["demo"]}]}
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    log_path = tmp_path / "pack.log"
    log_path.write_text("::group::demo — proof\nok\nCI_PACK_FAILED_JOBS=[]\n", encoding="utf-8")
    fragment_path = tmp_path / "fragment.json"
    fragment_path.write_text(
        json.dumps({"schema": "ci.semantic_fragment.v1", "plan_sha256": "d" * 64}),
        encoding="utf-8",
    )
    output_path = tmp_path / "receipt.json"
    result = subprocess.run(
        [
            "python3",
            str(ROOT / "scripts" / "capture_ci_canary_receipt.py"),
            "--log", str(log_path),
            "--plan", str(plan_path),
            "--pack", "0",
            "--exit-code", "0",
            "--tested-sha", "a" * 40,
            "--base-sha", "b" * 40,
            "--runner-kind", "selfhosted",
            "--runner-name", "test-runner",
            "--fragment", str(fragment_path),
            "--output", str(output_path),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    receipt = json.loads(output_path.read_text(encoding="utf-8"))
    assert receipt["schema"] == "ci.selfhosted_canary_receipt.v2"
    assert receipt["fragment_schema"] == "ci.semantic_fragment.v1"
    assert receipt["fragment_plan_sha256"] == "d" * 64
    assert receipt["prewarm_seconds"] is None


def test_capture_receipt_tolerates_a_missing_fragment_reference(tmp_path: Path) -> None:
    plan = {"plan_sha256": "d" * 64, "packs": [{"index": 0, "jobs": ["demo"]}]}
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    log_path = tmp_path / "pack.log"
    log_path.write_text("ok\n", encoding="utf-8")
    output_path = tmp_path / "receipt.json"
    result = subprocess.run(
        [
            "python3",
            str(ROOT / "scripts" / "capture_ci_canary_receipt.py"),
            "--log", str(log_path),
            "--plan", str(plan_path),
            "--pack", "0",
            "--exit-code", "0",
            "--tested-sha", "a" * 40,
            "--base-sha", "b" * 40,
            "--runner-kind", "hosted",
            "--runner-name", "test-runner",
            "--output", str(output_path),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    receipt = json.loads(output_path.read_text(encoding="utf-8"))
    assert receipt["fragment_schema"] is None
    assert receipt["fragment_plan_sha256"] is None


def test_capture_enriches_non_authoritative_execution_timing(
    tmp_path: Path,
) -> None:
    tested = "a" * 40
    head = tested
    base = tested
    plan = RUN_PACK.plan_from_workflow(
        ROOT / ".github" / "ci" / "legacy-jobs.yml",
        changed_from=None,
        scope_mode="active",
        pack_count=12,
        changed_files_file=None,
        workflow_run_id="123",
        workflow_name="ci",
        event="workflow_dispatch",
        role="main",
        tested_tree_sha=tested,
        subject_head_sha=head,
        base_sha=base,
        gate="code",
    )
    pack_index = next(
        index for index, jobs in enumerate(plan.pack_jobs) if len(jobs) > 1
    )
    selected = list(plan.pack_jobs[pack_index])
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan.to_dict()), encoding="utf-8")
    log_path = tmp_path / "pack.log"
    log_path.write_text("CI_PACK_FAILED_JOBS=[]\n", encoding="utf-8")
    observations_path = tmp_path / "observations.jsonl"
    observations_path.write_text(
        json.dumps(
            {
                "logical_job_id": selected[0],
                "phase": "dependency_install",
                "status": "observed",
                "started_monotonic_ns": 100,
                "ended_monotonic_ns": 130,
                "duration_ns": 30,
            }
        )
        + "\n"
        + json.dumps(
            {
                "logical_job_id": selected[0],
                "phase": "test",
                "status": "observed",
                "started_monotonic_ns": 140,
                "ended_monotonic_ns": 200,
                "duration_ns": 60,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    phase_path = tmp_path / "phase-monotonic.txt"
    phase_path.write_text(
        "job_start 10\n"
        "checkout_start 20\n"
        "checkout_end 30\n"
        "executor_setup_start 31\n"
        "executor_setup_end 40\n"
        "pack_execution_start 41\n"
        "pack_execution_end 70\n"
        "job_end 80\n",
        encoding="utf-8",
    )
    receipt_path = tmp_path / "receipt.json"
    timing_path = tmp_path / "execution-timing.jsonl"
    env = {
        **os.environ,
        "GITHUB_REPOSITORY": "mastermindx-market-intelligence/macro",
        "GITHUB_RUN_ATTEMPT": "2",
    }
    result = subprocess.run(
        [
            "python3",
            str(ROOT / "scripts" / "capture_ci_canary_receipt.py"),
            "--log", str(log_path),
            "--plan", str(plan_path),
            "--pack", str(pack_index),
            "--exit-code", "0",
            "--tested-sha", tested,
            "--base-sha", base,
            "--runner-kind", "selfhosted",
            "--runner-name", "pc-ci-1",
            "--runner-profile", RUN_PACK.RUNNER_CONTRACT,
            "--timing-observations", str(observations_path),
            "--phase-monotonic", str(phase_path),
            "--timing-output", str(timing_path),
            "--output", str(receipt_path),
        ],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    rows = [
        json.loads(line)
        for line in timing_path.read_text(encoding="utf-8").splitlines()
    ]
    assert rows
    expected_identity = {
        "schema": "ci.execution_timing.v1",
        "repository": "mastermindx-market-intelligence/macro",
        "workflow_run_id": "123",
        "workflow_run_attempt": 2,
        "subject_head_sha": head,
        "base_sha": base,
        "tested_tree_sha": tested,
        "plan_sha256": plan.plan_sha256,
        "pack_index": pack_index,
        "runner_kind": "selfhosted",
        "runner_name": "pc-ci-1",
        "runner_profile": RUN_PACK.RUNNER_CONTRACT,
    }
    assert all(
        {key: row[key] for key in expected_identity} == expected_identity
        for row in rows
    )
    by_phase = {(row["logical_job_id"], row["phase"]): row for row in rows}
    assert by_phase[(None, "queue")]["status"] == "missing"
    assert by_phase[(None, "checkout")]["duration_ns"] == 10
    assert by_phase[(None, "executor_setup")]["duration_ns"] == 9
    assert by_phase[(None, "pack_execution")]["duration_ns"] == 29
    assert by_phase[(None, "pack_completion")]["duration_ns"] == 70
    assert by_phase[(selected[0], "dependency_install")]["duration_ns"] == 30
    assert by_phase[(selected[0], "test")]["duration_ns"] == 60
    assert all(
        by_phase[(job_id, phase)]["status"] in {"observed", "missing"}
        for job_id in selected
        for phase in ("dependency_install", "test")
    )

    with pytest.raises(SEMANTIC.SemanticProofError, match="plan schema"):
        SEMANTIC._expected_plan(rows[0])
    with pytest.raises(SEMANTIC.SemanticProofError, match="fragment schema"):
        SEMANTIC.reconcile_evidence(plan.to_dict(), [rows[0]])
    with pytest.raises(SEMANTIC.SemanticProofError, match="evidence schema"):
        SEMANTIC._validate_evidence(rows[0])


def test_malformed_timing_degrades_without_changing_the_receipt(
    tmp_path: Path,
) -> None:
    tested = "a" * 40
    plan = {
        "workflow_run_id": "123",
        "tested_tree_sha": tested,
        "subject_head_sha": tested,
        "base_sha": tested,
        "plan_sha256": "d" * 64,
        "packs": [{"index": 0, "jobs": ["demo"]}],
    }
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    log_path = tmp_path / "pack.log"
    log_path.write_text("CI_PACK_FAILED_JOBS=[]\n", encoding="utf-8")
    empty_observations = tmp_path / "empty-observations.jsonl"
    empty_observations.write_text("", encoding="utf-8")
    reversed_phase = tmp_path / "reversed-phase-monotonic.txt"
    reversed_phase.write_text(
        "job_start 80\n"
        "checkout_start 30\n"
        "checkout_end 20\n"
        "executor_setup_start 40\n"
        "executor_setup_end 31\n"
        "pack_execution_start 70\n"
        "pack_execution_end 41\n"
        "job_end 10\n",
        encoding="utf-8",
    )
    baseline_receipt = tmp_path / "baseline-receipt.json"
    degraded_receipt = tmp_path / "degraded-receipt.json"
    timing_path = tmp_path / "execution-timing.jsonl"
    common = [
        "python3",
        str(ROOT / "scripts" / "capture_ci_canary_receipt.py"),
        "--log", str(log_path),
        "--plan", str(plan_path),
        "--pack", "0",
        "--exit-code", "0",
        "--tested-sha", tested,
        "--base-sha", tested,
        "--runner-kind", "selfhosted",
        "--runner-name", "pc-ci-1",
        "--runner-profile", RUN_PACK.RUNNER_CONTRACT,
    ]
    baseline = subprocess.run(
        [*common, "--output", str(baseline_receipt)],
        text=True,
        capture_output=True,
        check=False,
    )
    degraded = subprocess.run(
        [
            *common,
            "--timing-observations", str(empty_observations),
            "--phase-monotonic", str(reversed_phase),
            "--timing-output", str(timing_path),
            "--output", str(degraded_receipt),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert baseline.returncode == 0, baseline.stdout + baseline.stderr
    assert degraded.returncode == 0, degraded.stdout + degraded.stderr
    assert degraded_receipt.read_bytes() == baseline_receipt.read_bytes()
    assert "::warning title=ci timing telemetry degraded::" in degraded.stdout
    rows = [
        json.loads(line)
        for line in timing_path.read_text(encoding="utf-8").splitlines()
    ]
    assert rows
    assert all(row["status"] == "missing" for row in rows)
    assert {(row["logical_job_id"], row["phase"]) for row in rows} == {
        (None, "queue"),
        (None, "checkout"),
        (None, "executor_setup"),
        (None, "pack_execution"),
        (None, "pack_completion"),
        ("demo", "dependency_install"),
        ("demo", "test"),
    }


def _assert_invalid_raw_timing_is_non_authoritative(
    tmp_path: Path,
    raw_observations: bytes,
) -> None:
    """Run the receipt CLI against a malformed raw timing sidecar.

    A timing-input rejection must leave the already-established canary receipt
    and its passed pack verdict byte-for-byte untouched, while still producing
    a complete missing-row sidecar when the final timing destination works.
    """
    tested = "a" * 40
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "workflow_run_id": "123",
                "tested_tree_sha": tested,
                "subject_head_sha": tested,
                "base_sha": tested,
                "plan_sha256": "d" * 64,
                "packs": [{"index": 0, "jobs": ["demo"]}],
            }
        ),
        encoding="utf-8",
    )
    log_path = tmp_path / "pack.log"
    log_path.write_text("CI_PACK_FAILED_JOBS=[]\n", encoding="utf-8")
    observations_path = tmp_path / "observations.jsonl"
    observations_path.write_bytes(raw_observations)
    phase_path = tmp_path / "phase-monotonic.txt"
    phase_path.write_text(
        "job_start 10\n"
        "checkout_start 20\n"
        "checkout_end 30\n"
        "executor_setup_start 31\n"
        "executor_setup_end 40\n"
        "pack_execution_start 41\n"
        "pack_execution_end 70\n"
        "job_end 80\n",
        encoding="utf-8",
    )
    baseline_receipt = tmp_path / "baseline-receipt.json"
    degraded_receipt = tmp_path / "degraded-receipt.json"
    timing_path = tmp_path / "execution-timing.jsonl"
    common = [
        sys.executable,
        str(ROOT / "scripts" / "capture_ci_canary_receipt.py"),
        "--log", str(log_path),
        "--plan", str(plan_path),
        "--pack", "0",
        "--exit-code", "0",
        "--tested-sha", tested,
        "--base-sha", tested,
        "--runner-kind", "selfhosted",
        "--runner-name", "pc-ci-1",
        "--runner-profile", RUN_PACK.RUNNER_CONTRACT,
    ]
    baseline = subprocess.run(
        [*common, "--output", str(baseline_receipt)],
        text=True,
        capture_output=True,
        check=False,
    )
    degraded = subprocess.run(
        [
            *common,
            "--timing-observations", str(observations_path),
            "--phase-monotonic", str(phase_path),
            "--timing-output", str(timing_path),
            "--output", str(degraded_receipt),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert baseline.returncode == 0, baseline.stdout + baseline.stderr
    assert degraded.returncode == 0, degraded.stdout + degraded.stderr
    assert degraded_receipt.read_bytes() == baseline_receipt.read_bytes()
    assert json.loads(degraded_receipt.read_text(encoding="utf-8"))["result"] == "passed"
    assert "::warning title=ci timing telemetry degraded::" in degraded.stdout
    rows = [
        json.loads(line)
        for line in timing_path.read_text(encoding="utf-8").splitlines()
    ]
    assert {(row["logical_job_id"], row["phase"]) for row in rows} == {
        (None, "queue"),
        (None, "checkout"),
        (None, "executor_setup"),
        (None, "pack_execution"),
        (None, "pack_completion"),
        ("demo", "dependency_install"),
        ("demo", "test"),
    }
    by_phase = {(row["logical_job_id"], row["phase"]): row for row in rows}
    assert all(
        by_phase[("demo", phase)]["status"] == "missing"
        for phase in ("dependency_install", "test")
    )


def test_duplicate_raw_timing_observations_degrade_without_receipt_or_verdict_impact(
    tmp_path: Path,
) -> None:
    observation = {
        "logical_job_id": "demo",
        "phase": "test",
        "status": "observed",
        "started_monotonic_ns": 100,
        "ended_monotonic_ns": 130,
        "duration_ns": 30,
    }
    _assert_invalid_raw_timing_is_non_authoritative(
        tmp_path,
        (json.dumps(observation) + "\n" + json.dumps(observation) + "\n").encode(),
    )


def test_oversized_raw_timing_observations_degrade_without_receipt_or_verdict_impact(
    tmp_path: Path,
) -> None:
    _assert_invalid_raw_timing_is_non_authoritative(
        tmp_path,
        b"x" * (4 * 1024 * 1024 + 1),
    )


def test_deeply_nested_raw_timing_json_degrades_without_receipt_or_verdict_impact(
    tmp_path: Path,
) -> None:
    _assert_invalid_raw_timing_is_non_authoritative(
        tmp_path,
        b"[" * 10_000 + b"0" + b"]" * 10_000 + b"\n",
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [("logical_job_id", []), ("phase", {})],
    ids=("non-hashable-logical-job-id", "non-hashable-phase"),
)
def test_non_hashable_raw_timing_fields_degrade_without_receipt_or_verdict_impact(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    observation = {
        "logical_job_id": "demo",
        "phase": "test",
        "status": "observed",
        "started_monotonic_ns": 100,
        "ended_monotonic_ns": 130,
        "duration_ns": 30,
    }
    observation[field] = value
    _assert_invalid_raw_timing_is_non_authoritative(
        tmp_path,
        (json.dumps(observation) + "\n").encode(),
    )


def test_unwritable_final_timing_output_degrades_without_receipt_or_verdict_impact(
    tmp_path: Path,
) -> None:
    tested = "a" * 40
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "workflow_run_id": "123",
                "tested_tree_sha": tested,
                "subject_head_sha": tested,
                "base_sha": tested,
                "plan_sha256": "d" * 64,
                "packs": [{"index": 0, "jobs": ["demo"]}],
            }
        ),
        encoding="utf-8",
    )
    log_path = tmp_path / "pack.log"
    log_path.write_text("CI_PACK_FAILED_JOBS=[]\n", encoding="utf-8")
    baseline_receipt = tmp_path / "baseline-receipt.json"
    degraded_receipt = tmp_path / "degraded-receipt.json"
    blocked_parent = tmp_path / "not-a-directory"
    blocked_parent.write_text("not a directory\n", encoding="utf-8")
    common = [
        "python3",
        str(ROOT / "scripts" / "capture_ci_canary_receipt.py"),
        "--log", str(log_path),
        "--plan", str(plan_path),
        "--pack", "0",
        "--exit-code", "0",
        "--tested-sha", tested,
        "--base-sha", tested,
        "--runner-kind", "selfhosted",
        "--runner-name", "pc-ci-1",
        "--runner-profile", RUN_PACK.RUNNER_CONTRACT,
    ]
    baseline = subprocess.run(
        [*common, "--output", str(baseline_receipt)],
        text=True,
        capture_output=True,
        check=False,
    )
    degraded = subprocess.run(
        [
            *common,
            "--timing-output", str(blocked_parent / "execution-timing.jsonl"),
            "--output", str(degraded_receipt),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert baseline.returncode == 0, baseline.stdout + baseline.stderr
    assert degraded.returncode == 0, degraded.stdout + degraded.stderr
    assert degraded_receipt.read_bytes() == baseline_receipt.read_bytes()
    assert json.loads(degraded_receipt.read_text(encoding="utf-8"))["result"] == "passed"
    assert "::warning title=ci timing telemetry degraded::" in degraded.stdout


def test_trusted_executor_publishes_timing_without_gate_authority() -> None:
    executor = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "trusted-ci-executor.yml").read_text(
            encoding="utf-8"
        )
    )
    steps = executor["jobs"]["trusted-pack"]["steps"]
    execute = next(
        step
        for step in steps
        if step.get("name") == "execute the frozen logical pack and retain its actual result"
    )
    receipt = next(
        step
        for step in steps
        if step.get("name") == "write trusted self-hosted receipt"
    )
    timing_upload = next(
        step
        for step in steps
        if step.get("name") == "publish non-authoritative execution timing"
    )
    marker_lines = [
        line.strip()
        for step in steps
        if isinstance(step, dict)
        for line in str(step.get("run", "")).splitlines()
        if "time.monotonic_ns()" in line
    ]
    for marker in (
        "job_start",
        "checkout_start",
        "checkout_end",
        "executor_setup_start",
        "executor_setup_end",
        "pack_execution_start",
        "pack_execution_end",
        "job_end",
    ):
        assert any(marker in line for line in marker_lines)
    assert all(line.endswith("|| true") for line in marker_lines)
    assert "--emit-timing-observations" in execute["run"]
    assert "--timing-observations" in receipt["run"]
    assert "--phase-monotonic" in receipt["run"]
    assert "--timing-output" in receipt["run"]
    assert timing_upload["if"] == "always()"
    assert timing_upload["continue-on-error"] is True
    assert timing_upload["timeout-minutes"] == 5
    assert timing_upload["with"]["if-no-files-found"] == "warn"
    assert timing_upload["with"]["name"] == (
        "trusted-ci-execution-timing-${{ matrix.pack }}"
    )
    required_artifact_indices = [
        index
        for index, step in enumerate(steps)
        if step.get("with", {}).get("name")
        in {
            "trusted-ci-receipt-${{ matrix.pack }}",
            "trusted-ci-fragment-${{ matrix.pack }}",
        }
    ]
    timing_index = steps.index(timing_upload)
    assert len(required_artifact_indices) == 2
    assert all(index < timing_index for index in required_artifact_indices)

    ci = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    gate = json.dumps(ci["jobs"]["ci-gate"], sort_keys=True)
    assert "execution-timing" not in gate
    assert "timing-observations" not in gate


def test_main_dispatch_freezes_parent_as_the_changed_from_base(monkeypatch) -> None:
    tested = "a" * 40
    parent = "b" * 40

    def fake_git(*args: str) -> str:
        assert args[0] == "rev-parse"
        return tested if args[1].endswith("^{commit}") else parent

    monkeypatch.setattr(RESOLVE, "git", fake_git)
    result = RESOLVE.resolve("mastermindx-market-intelligence/macro", tested, 0, "")
    assert result["tested_ref"] == tested
    assert result["tested_sha"] == tested
    assert result["base_sha"] == parent
    assert result["head_ref"] == "main"
    assert result["contamination_sha"] == parent


def test_pr_dispatch_uses_the_fetched_merge_parent_when_api_base_is_stale(
    monkeypatch,
) -> None:
    """The merge ref is the tested tree; its first parent is its tested base.

    GitHub's pull-request ``base.sha`` can lag the first parent of the current
    synthetic merge ref while the PR head and immutable merge SHA remain exact.
    """
    merge = "a" * 40
    tested_base = "b" * 40
    head = "c" * 40
    stale_api_base = "d" * 40
    monkeypatch.setattr(
        RESOLVE,
        "pull_request",
        lambda *_: {
            "state": "open",
            "merge_commit_sha": merge,
            "base": {"ref": "main", "sha": stale_api_base},
            "head": {
                "ref": "codex/ci-p3bb-production-route-6351",
                "sha": head,
                "repo": {"full_name": "mastermindx-market-intelligence/macro"},
            },
        },
    )

    def fake_git(*args: str) -> str:
        if args[0] == "fetch":
            return ""
        if args[0] == "check-ref-format":
            return args[2]
        revisions = {
            "refs/ci-canary/pull/7/merge^{commit}": merge,
            f"{merge}^1": tested_base,
            f"{merge}^2": head,
        }
        return revisions[args[1]]

    monkeypatch.setattr(RESOLVE, "git", fake_git)
    result = RESOLVE.resolve(
        "mastermindx-market-intelligence/macro", "e" * 40, 7, "token"
    )
    assert result["tested_sha"] == merge
    assert result["base_sha"] == tested_base
    assert result["head_sha"] == head
    assert result["head_ref"] == "codex/ci-p3bb-production-route-6351"
    assert result["contamination_sha"] == tested_base


def test_pr_dispatch_requires_fetched_merge_sha_and_head_to_match_api(monkeypatch) -> None:
    merge = "a" * 40
    base = "b" * 40
    head = "c" * 40
    monkeypatch.setattr(
        RESOLVE,
        "pull_request",
        lambda *_: {
            "state": "open",
            "merge_commit_sha": merge,
            "base": {"ref": "main", "sha": base},
            "head": {
                "ref": "codex/ci-p3bb-production-route-6351",
                "sha": head,
                "repo": {"full_name": "mastermindx-market-intelligence/macro"},
            },
        },
    )

    def fake_git(*args: str) -> str:
        if args[0] == "fetch":
            return ""
        if args[0] == "check-ref-format":
            return args[2]
        revisions = {
            "refs/ci-canary/pull/7/merge^{commit}": merge,
            f"{merge}^1": base,
            f"{merge}^2": head,
        }
        return revisions[args[1]]

    monkeypatch.setattr(RESOLVE, "git", fake_git)
    result = RESOLVE.resolve(
        "mastermindx-market-intelligence/macro", "d" * 40, 7, "token"
    )
    assert result["tested_sha"] == merge
    assert result["base_sha"] == base
    assert result["head_sha"] == head

    monkeypatch.setattr(RESOLVE, "git", lambda *args: "e" * 40 if args[0] != "fetch" else "")
    try:
        RESOLVE.resolve("mastermindx-market-intelligence/macro", "d" * 40, 7, "token")
    except RESOLVE.ResolutionError as exc:
        assert "merge" in str(exc)
    else:
        raise AssertionError("mismatched merge/API parents must fail closed")


def test_host_admission_accepts_only_the_main_dispatch_canary() -> None:
    allowed = {
        "MASTERMIND_CI_PROFILE": "pc-ci",
        "GITHUB_REPOSITORY": "mastermindx-market-intelligence/macro",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_WORKFLOW_REF": (
            "mastermindx-market-intelligence/macro/.github/workflows/"
            "selfhosted-ci-canary.yml@refs/heads/main"
        ),
        "GITHUB_JOB": "selfhosted-pack",
    }
    assert ADMISSION.decision(allowed)[0]
    for key, value in (
        ("GITHUB_EVENT_NAME", "pull_request"),
        ("GITHUB_REF", "refs/pull/7/merge"),
        ("GITHUB_WORKFLOW_REF", "mastermindx-market-intelligence/macro/.github/workflows/rogue.yml@refs/heads/main"),
        ("GITHUB_REPOSITORY", "attacker/fork"),
    ):
        mutated = {**allowed, key: value}
        assert not ADMISSION.decision(mutated)[0]


def test_host_admission_accepts_only_the_main_dispatch_trusted_executor_pack() -> None:
    allowed = {
        "MASTERMIND_CI_PROFILE": "pc-ci",
        "GITHUB_REPOSITORY": "mastermindx-market-intelligence/macro",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_WORKFLOW_REF": (
            "mastermindx-market-intelligence/macro/.github/workflows/"
            "trusted-ci-executor.yml@refs/heads/main"
        ),
        "GITHUB_JOB": "trusted-pack",
    }
    assert ADMISSION.decision(allowed)[0]
    for key, value in (
        ("GITHUB_EVENT_NAME", "workflow_call"),
        ("GITHUB_REF", "refs/pull/7/merge"),
        (
            "GITHUB_WORKFLOW_REF",
            "mastermindx-market-intelligence/macro/.github/workflows/"
            "trusted-ci-executor.yml@refs/heads/candidate",
        ),
        (
            "GITHUB_WORKFLOW_REF",
            "mastermindx-market-intelligence/macro/.github/workflows/"
            "hostile-main-caller.yml@refs/heads/main",
        ),
        ("GITHUB_REPOSITORY", "attacker/fork"),
        ("GITHUB_JOB", "rogue-pack"),
    ):
        mutated = {**allowed, key: value}
        assert not ADMISSION.decision(mutated)[0]


def test_host_admission_accepts_only_main_gated_same_repo_pr_executor_pack(
    tmp_path: Path,
) -> None:
    pr_number = "6505"
    event_path = tmp_path / "event.json"
    event_path.write_text(
        json.dumps(
            {
                "pull_request": {
                    "base": {"ref": "main"},
                    "head": {
                        "repo": {
                            "full_name": "mastermindx-market-intelligence/macro"
                        }
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    allowed = {
        "MASTERMIND_CI_PROFILE": "pc-ci",
        "GITHUB_REPOSITORY": "mastermindx-market-intelligence/macro",
        "GITHUB_EVENT_NAME": "pull_request",
        "GITHUB_REF": f"refs/pull/{pr_number}/merge",
        "GITHUB_WORKFLOW_REF": (
            "mastermindx-market-intelligence/macro/.github/workflows/"
            f"ci.yml@refs/pull/{pr_number}/merge"
        ),
        "GITHUB_JOB": "trusted-pack",
        "GITHUB_EVENT_PATH": str(event_path),
    }
    assert ADMISSION.decision(allowed)[0]
    for key, value in (
        ("GITHUB_EVENT_NAME", "workflow_dispatch"),
        ("GITHUB_REF", "refs/pull/6506/merge"),
        (
            "GITHUB_WORKFLOW_REF",
            "mastermindx-market-intelligence/macro/.github/workflows/rogue.yml@refs/pull/6505/merge",
        ),
        ("GITHUB_JOB", "rogue-pack"),
        ("GITHUB_EVENT_PATH", str(tmp_path / "missing-event.json")),
    ):
        assert not ADMISSION.decision({**allowed, key: value})[0]

    for name, payload in (
        (
            "fork.json",
            {
                "pull_request": {
                    "base": {"ref": "main"},
                    "head": {"repo": {"full_name": "attacker/fork"}},
                }
            },
        ),
        (
            "release-base.json",
            {
                "pull_request": {
                    "base": {"ref": "release"},
                    "head": {
                        "repo": {
                            "full_name": "mastermindx-market-intelligence/macro"
                        }
                    },
                }
            },
        ),
    ):
        mutated_event = tmp_path / name
        mutated_event.write_text(json.dumps(payload), encoding="utf-8")
        assert not ADMISSION.decision(
            {**allowed, "GITHUB_EVENT_PATH": str(mutated_event)}
        )[0]


def test_cache_update_disables_automatic_maintenance() -> None:
    script = (ROOT / "ops" / "runner-host" / "pc" / "mastermind_ci_cache_update.sh").read_text(
        encoding="utf-8"
    )
    assert "fetch --no-auto-maintenance" in script
    assert "config gc.auto 0" in script
    assert "config maintenance.auto false" in script


def test_runner_service_seals_runtime_and_binds_host_admission() -> None:
    unit = (
        ROOT / "ops" / "runner-host" / "pc" / "actions-runner-ci.service.template"
    ).read_text(encoding="utf-8")
    assert "ACTIONS_RUNNER_HOOK_JOB_STARTED=/usr/local/libexec/mastermind-ci-admission-pc-ci.js" in unit
    assert "ACTIONS_RUNNER_HOOK_JOB_COMPLETED" not in unit
    assert "Restart=always" in unit
    assert "RestartSec=5" in unit
    assert "StartLimitIntervalSec=0" in unit
    assert "StartLimitBurst" not in unit
    assert "--refusal-backoff-seconds 300" in unit
    assert "TimeoutStartSec=10min" in unit
    assert "MASTERMIND_CI_RUNNER_ROOT=__RUNNER_ROOT__" in unit
    assert "ReadOnlyPaths=__RUNNER_ROOT__ /var/cache/mastermind-ci/macro.git" in unit
    assert "ReadWritePaths=__RUNNER_ROOT__/_work __RUNNER_ROOT__/_diag" in unit
    assert "ReadWritePaths=__RUNNER_ROOT__ " not in unit
    assert "UMask=0022" in unit
    assert "UMask=0027" not in unit
    pc_wrapper = (
        ROOT / "ops" / "runner-host" / "pc" / "mastermind_ci_runner.sh"
    ).read_text(encoding="utf-8")
    assert "ACTIONS_RUNNER_HOOK_JOB_STARTED=/usr/local/libexec/mastermind-ci-admission-pc-ci.js" in pc_wrapper
    assert "/usr/bin/python3 -I /usr/local/libexec/runner_cleanup.py" in pc_wrapper
    assert 'run --startuptype service --once' in pc_wrapper
    assert 'MASTERMIND_CI_RUNNER_ROOT="$runner_root"' in pc_wrapper
    m1 = (ROOT / "ops" / "runner-host" / "m1" / "run_guarded_runner.sh").read_text(
        encoding="utf-8"
    )
    assert 'ACTIONS_RUNNER_HOOK_JOB_STARTED="$guard_root/runner_admission_m1_canary.js"' in m1
    assert "MASTERMIND_CI_PROFILE=m1-canary" in m1
    hook = (
        ROOT / "ops" / "runner-host" / "common" / "runner_admission_hook.js"
    ).read_text(encoding="utf-8")
    assert 'spawnSync("/usr/bin/python3", ["-I", script]' in hook
    assert '"GITHUB_EVENT_PATH"' in hook
    assert "process.env.PATH" not in hook
    assert "process.env.MASTERMIND_CI_PROFILE" not in hook


def test_resource_refusal_backoff_only_delays_an_unsafe_retry() -> None:
    sleeps: list[int] = []
    RESOURCE_GUARD.refusal_backoff([], 300, sleep=sleeps.append)
    assert sleeps == []
    RESOURCE_GUARD.refusal_backoff(["critical disk pressure"], 300, sleep=sleeps.append)
    assert sleeps == [300]


def test_listener_startup_cleanup_scrubs_all_pc_job_state_and_recreates_runtime_dirs(
    tmp_path: Path, monkeypatch
) -> None:
    runner = tmp_path / "runner-1"
    work = runner / "_work"
    (work / "_temp").mkdir(parents=True)
    (work / "_temp" / "current-event.json").write_text("{}", encoding="utf-8")
    (work / "macro" / "macro").mkdir(parents=True)
    (work / "macro" / "macro" / "sentinel").write_text("old", encoding="utf-8")
    (work / "_actions").mkdir()
    (work / "_tool").symlink_to(work / "macro", target_is_directory=True)
    private_tmp = tmp_path / "private-tmp"
    private_tmp.mkdir()
    (private_tmp / "prior-job").write_text("old", encoding="utf-8")
    monkeypatch.setattr(CLEANUP, "PC_CI_ROOTS", {runner})
    assert CLEANUP.scrub_pc_state(runner, (private_tmp,)) >= 4
    assert not (work / "_temp" / "current-event.json").exists()
    assert list((work / "_temp").iterdir()) == []
    assert list((work / "_home").iterdir()) == []
    assert not (work / "macro").exists()
    assert not (work / "_actions").exists()
    assert not (work / "_tool").exists()
    assert list(private_tmp.iterdir()) == []


def test_start_admission_has_no_workspace_mutation_api() -> None:
    assert not hasattr(ADMISSION, "scrub_pc_state")
    assert not hasattr(ADMISSION, "remove_entry")
