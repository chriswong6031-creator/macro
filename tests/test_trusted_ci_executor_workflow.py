from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
MAIN_CONTROL_FILES = {
    "__init__.py",
    "run_ci_pack.py",
    "ci_semantic_proof.py",
    "ci_authority_paths.py",
    "ci_scope_dependencies.py",
    "audit_unrun_tests.py",
    "workflow_run_source.py",
    "resolve_ci_canary_ref.py",
    "select_ci_canary_packs.py",
    "monitor_ci_host_resources.py",
    "capture_ci_canary_receipt.py",
}
CONTROL_REPO_ROOT_ENV = "MASTERMIND_TRUSTED_CI_REPO_ROOT"


def workflow(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def triggers(document: dict) -> set[str]:
    raw = document.get("on", document.get(True, {}))
    return set(raw) if isinstance(raw, dict) else {str(raw)}


def test_p3a_executor_is_dispatch_provable_but_production_inert() -> None:
    document = workflow("trusted-ci-executor.yml")
    assert triggers(document) == {"workflow_call", "workflow_dispatch"}
    trigger_config = document.get("on", document.get(True))
    assert set(trigger_config["workflow_call"]["inputs"]) == {"pr_number"}
    assert set(trigger_config["workflow_dispatch"]["inputs"]) == {"pr_number"}
    assert document["permissions"] == {"contents": "read", "pull-requests": "read"}

    trust = document["jobs"]["trust-gate"]
    assert trust["runs-on"] == "ubuntu-latest"
    rendered = str(trust)
    assert "refs/heads/main" in rendered
    assert "workflow_dispatch" in rendered
    assert "P3A refuses workflow_call" in rendered
    gate = next(
        step
        for step in trust["steps"]
        if step.get("name") == "keep P3A dispatch-provable and production-inert"
    )
    assert gate["env"]["TRUSTED_WORKFLOW_REF"] == "${{ github.workflow_ref }}"
    assert (
        'test "$TRUSTED_WORKFLOW_REF" = '
        "mastermindx-market-intelligence/macro/.github/workflows/"
        'trusted-ci-executor.yml@refs/heads/main || {'
    ) in gate["run"].splitlines()

    production = workflow("ci.yml")
    assert "trusted-ci-executor.yml" not in str(production)
    assert {
        production["jobs"][name]["runs-on"]
        for name in ("ci-plan", "ci-pack", "ci-gate")
    } == {"ubuntu-latest"}


def test_p3a_planner_is_hosted_main_control_and_freezes_one_exact_pr_pack() -> None:
    document = workflow("trusted-ci-executor.yml")
    plan = document["jobs"]["plan"]
    assert plan["runs-on"] == "ubuntu-latest"
    assert plan["needs"] == "trust-gate"
    assert {
        "matrix",
        "plan_sha",
        "tested_sha",
        "base_sha",
        "head_sha",
        "control_sha",
    } <= set(plan["outputs"])

    steps = plan["steps"]
    control_checkout = next(
        step for step in steps if step.get("name") == "checkout main-owned executor control code"
    )
    assert control_checkout["uses"] == "actions/checkout@v4"
    assert control_checkout["with"]["ref"] == "${{ github.sha }}"
    assert control_checkout["with"]["persist-credentials"] is False

    resolve = next(step for step in steps if step.get("id") == "ref")
    assert "resolve_ci_canary_ref.py" in resolve["run"]
    candidate_checkout = next(
        step for step in steps if step.get("name") == "checkout the immutable PR candidate"
    )
    assert candidate_checkout["with"]["ref"] == "${{ steps.ref.outputs.tested_sha }}"
    assert candidate_checkout["with"]["persist-credentials"] is False

    planner = next(step for step in steps if step.get("id") == "plan")
    for token in (
        "--workflow-name trusted-ci-executor",
        "--event workflow_dispatch",
        "--role pr_head",
        "--gate code",
        "--tested-tree-sha",
        "--subject-head-sha",
        "--base-sha",
        "--changed-from",
    ):
        assert token in planner["run"]
    selector = next(step for step in steps if step.get("id") == "select")
    assert "--count 1" in selector["run"]


def test_p3ar_freezes_and_transports_the_complete_main_owned_control_bundle() -> None:
    document = workflow("trusted-ci-executor.yml")
    plan_steps = document["jobs"]["plan"]["steps"]
    preserve = next(
        step
        for step in plan_steps
        if step.get("name") == "freeze the complete main-owned control bundle"
    )
    for filename in MAIN_CONTROL_FILES:
        assert f"scripts/{filename}" in preserve["run"]
    assert "$RUNNER_TEMP/trusted-ci-control/scripts/" in preserve["run"]

    planner = next(step for step in plan_steps if step.get("id") == "plan")
    assert planner["env"][CONTROL_REPO_ROOT_ENV] == "${{ github.workspace }}"
    assert (
        '"$RUNNER_TEMP/trusted-ci-plan-runner/bin/python" '
        '"$RUNNER_TEMP/trusted-ci-control/scripts/run_ci_pack.py"'
    ) in planner["run"]
    assert 'bin/python" scripts/run_ci_pack.py' not in planner["run"]

    control_upload = next(
        step
        for step in plan_steps
        if step.get("uses") == "actions/upload-artifact@v4"
        and step["with"]["name"] == "trusted-ci-control"
    )
    assert control_upload["with"]["path"] == "${{ runner.temp }}/trusted-ci-control"
    assert control_upload["with"]["if-no-files-found"] == "error"

    pack_steps = document["jobs"]["trusted-pack"]["steps"]
    control_download_index = next(
        index
        for index, step in enumerate(pack_steps)
        if step.get("uses") == "actions/download-artifact@v4"
        and step["with"].get("name") == "trusted-ci-control"
    )
    materialize_index = next(
        index
        for index, step in enumerate(pack_steps)
        if step.get("name", "").startswith("materialize exact candidate")
    )
    assert control_download_index < materialize_index
    assert pack_steps[control_download_index]["with"]["path"] == (
        "${{ runner.temp }}/trusted-ci-control"
    )

    execute_step = next(
        step
        for step in pack_steps
        if step.get("name") == "execute the frozen logical pack and retain its actual result"
    )
    assert execute_step["env"][CONTROL_REPO_ROOT_ENV] == "${{ github.workspace }}"
    execute = execute_step["run"]
    assert (
        '"$RUNNER_TEMP/trusted-ci-pack-runner/bin/python" '
        '"$RUNNER_TEMP/trusted-ci-control/scripts/run_ci_pack.py"'
    ) in execute
    assert 'bin/python" scripts/run_ci_pack.py' not in execute

    receipt = next(
        step
        for step in pack_steps
        if step.get("name") == "write trusted self-hosted receipt"
    )["run"]
    assert "$RUNNER_TEMP/trusted-ci-control/scripts/capture_ci_canary_receipt.py" in receipt
    assert "$RUNNER_TEMP/trusted-ci-control/scripts/monitor_ci_host_resources.py" in execute


def test_p3ar_control_bundle_imports_without_candidate_control_modules(
    tmp_path: Path,
) -> None:
    control_scripts = tmp_path / "trusted-ci-control" / "scripts"
    control_scripts.mkdir(parents=True)
    for filename in MAIN_CONTROL_FILES:
        (control_scripts / filename).write_bytes((ROOT / "scripts" / filename).read_bytes())

    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(control_scripts.parent)
    environment[CONTROL_REPO_ROOT_ENV] = str(ROOT)
    root_probe = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                f"sys.path.insert(0, {str(control_scripts.parent)!r}); "
                "from scripts.ci_scope_dependencies import ROOT; print(ROOT)"
            ),
        ],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert root_probe.returncode == 0, root_probe.stdout + root_probe.stderr
    assert root_probe.stdout.strip() == str(ROOT.resolve())

    result = subprocess.run(
        [
            sys.executable,
            str(control_scripts / "run_ci_pack.py"),
            "--workflow",
            ".github/ci/legacy-jobs.yml",
            "--gate",
            "code",
            "--validate-only",
        ],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Validated 132 legacy jobs" in result.stdout


def test_p3a_selfhosted_job_uses_the_selected_group_and_negotiated_cache() -> None:
    document = workflow("trusted-ci-executor.yml")
    job = document["jobs"]["trusted-pack"]
    assert job["needs"] == "plan"
    assert job["runs-on"] == {
        "group": "macro-home-canary",
        "labels": "ci-linux",
    }
    steps = job["steps"]
    assert all(step.get("uses") != "actions/checkout@v4" for step in steps)

    prewarm_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("name", "").startswith("prewarm exact base")
    )
    materialize_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("name", "").startswith("materialize exact candidate")
    )
    assert prewarm_index < materialize_index
    assert "/usr/local/libexec/mastermind-ci-prewarm" in str(steps[prewarm_index])
    materialize = steps[materialize_index]["run"]
    for token in (
        "fetch.negotiationAlgorithm=skipping",
        "--filter=blob:none --depth=1",
        'origin "$TESTED_SHA"',
        "GIT_TERMINAL_PROMPT=0",
        "GIT_ASKPASS=/bin/false",
        "credential.helper=",
        "extraheader",
        "GIT_NO_LAZY_FETCH=1",
    ):
        assert token in materialize
    assert materialize.index("extraheader") < materialize.index("git -c credential.helper=")


def test_p3a_executor_consumes_one_frozen_plan_and_emits_existing_evidence() -> None:
    document = workflow("trusted-ci-executor.yml")
    steps = document["jobs"]["trusted-pack"]["steps"]
    execute = next(
        step
        for step in steps
        if step.get("name") == "execute the frozen logical pack and retain its actual result"
    )["run"]
    for token in (
        "--plan-json",
        "--changed-files-file",
        "--expect-plan-sha",
        "--expect-tested-tree-sha",
        "--expect-subject-head-sha",
        "--expect-base-sha",
        "--emit-semantic-fragment",
        "--gate code",
    ):
        assert token in execute
    assert "--changed-from" not in execute

    rendered = str(steps)
    assert "capture_ci_canary_receipt.py" in rendered
    assert "ci.semantic_fragment.v1" not in rendered  # emitted by the existing helper
    upload_names = {
        step["with"]["name"]
        for step in steps
        if step.get("uses") == "actions/upload-artifact@v4"
    }
    assert "trusted-ci-receipt-${{ matrix.pack }}" in upload_names
    assert "trusted-ci-fragment-${{ matrix.pack }}" in upload_names


def test_p3a_executor_has_no_secret_or_candidate_credential_surface() -> None:
    document = workflow("trusted-ci-executor.yml")
    rendered = str(document)
    for forbidden in (
        "secrets:",
        "pull_request_target",
        "persist-credentials: true",
        "ADMIN_GH_TOKEN",
        "MERGE_TOKEN",
        "macstudio",
        "render-linux",
        "m1-",
    ):
        assert forbidden not in rendered
    for job in document["jobs"].values():
        for step in job.get("steps", []) or []:
            if step.get("uses") == "actions/checkout@v4":
                assert step["with"]["persist-credentials"] is False
