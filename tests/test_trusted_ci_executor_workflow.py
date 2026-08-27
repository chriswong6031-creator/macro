from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
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


def trusted_gate_step() -> dict:
    trust = workflow("trusted-ci-executor.yml")["jobs"]["trust-gate"]
    return next(
        step
        for step in trust["steps"]
        if step.get("name")
        == "admit direct dispatch or exact main-called same-repository PR"
    )


def run_trusted_gate(
    tmp_path: Path, **overrides: str
) -> tuple[subprocess.CompletedProcess[str], dict[str, str]]:
    repository = "mastermindx-market-intelligence/macro"
    pr_number = "6390"
    output = tmp_path / "github-output"
    environment = {
        **os.environ,
        "GITHUB_OUTPUT": str(output),
        "EVENT_NAME": "pull_request",
        "TRUSTED_REF": f"refs/pull/{pr_number}/merge",
        "CALLER_WORKFLOW_REF": (
            f"{repository}/.github/workflows/ci.yml@refs/pull/{pr_number}/merge"
        ),
        "CALLED_WORKFLOW_REF": (
            f"{repository}/.github/workflows/"
            "trusted-ci-executor.yml@refs/heads/main"
        ),
        "CALLED_WORKFLOW_SHA": "a" * 40,
        "REPOSITORY": repository,
        "HEAD_REPOSITORY": repository,
        "BASE_REF": "main",
        "EVENT_PR_NUMBER": pr_number,
        "DISPATCH_PR_NUMBER": "",
    }
    environment.update(overrides)
    result = subprocess.run(
        ["bash", "-c", trusted_gate_step()["run"]],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    values: dict[str, str] = {}
    if output.exists():
        for line in output.read_text(encoding="utf-8").splitlines():
            key, value = line.split("=", 1)
            values[key] = value
    return result, values


def test_p3bb_executor_stays_call_capable_after_production_route_activation() -> None:
    document = workflow("trusted-ci-executor.yml")
    assert triggers(document) == {"workflow_call", "workflow_dispatch"}
    trigger_config = document.get("on", document.get(True))
    assert trigger_config["workflow_call"].get("inputs", {}) == {}
    assert set(trigger_config["workflow_call"]["outputs"]) == {
        "matrix",
        "plan_sha",
        "tested_sha",
        "base_sha",
        "head_sha",
        "control_sha",
    }
    assert set(trigger_config["workflow_dispatch"]["inputs"]) == {"pr_number"}
    assert document["permissions"] == {"contents": "read", "pull-requests": "read"}

    trust = document["jobs"]["trust-gate"]
    assert trust["runs-on"] == "ubuntu-latest"
    assert trust["outputs"] == {
        "control_sha": "${{ steps.admit.outputs.control_sha }}",
        "pr_number": "${{ steps.admit.outputs.pr_number }}",
        "mode": "${{ steps.admit.outputs.mode }}",
        "semantic_workflow": "${{ steps.admit.outputs.semantic_workflow }}",
    }
    gate = trusted_gate_step()
    assert gate["id"] == "admit"
    assert gate["env"] == {
        "EVENT_NAME": "${{ github.event_name }}",
        "TRUSTED_REF": "${{ github.ref }}",
        "CALLER_WORKFLOW_REF": "${{ github.workflow_ref }}",
        "CALLED_WORKFLOW_REF": "${{ job.workflow_ref }}",
        "CALLED_WORKFLOW_SHA": "${{ job.workflow_sha }}",
        "REPOSITORY": "${{ github.repository }}",
        "HEAD_REPOSITORY": "${{ github.event.pull_request.head.repo.full_name }}",
        "BASE_REF": "${{ github.base_ref }}",
        "EVENT_PR_NUMBER": "${{ github.event.pull_request.number }}",
        "DISPATCH_PR_NUMBER": "${{ inputs.pr_number }}",
    }

    production = workflow("ci.yml")
    assert production["jobs"]["trusted-ci"]["uses"] == (
        "mastermindx-market-intelligence/macro/.github/workflows/"
        "trusted-ci-executor.yml@refs/heads/main"
    )
    assert {
        production["jobs"][name]["runs-on"]
        for name in ("ci-plan", "ci-pack", "ci-gate")
    } == {"ubuntu-latest"}


def test_p3ba_accepts_exact_main_called_same_repo_pr_and_derives_identity(
    tmp_path: Path,
) -> None:
    result, outputs = run_trusted_gate(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert outputs == {
        "control_sha": "a" * 40,
        "pr_number": "6390",
        "mode": "production",
        "semantic_workflow": "ci",
    }


def test_p3ba_keeps_the_direct_main_dispatch_canary(tmp_path: Path) -> None:
    repository = "mastermindx-market-intelligence/macro"
    result, outputs = run_trusted_gate(
        tmp_path,
        EVENT_NAME="workflow_dispatch",
        TRUSTED_REF="refs/heads/main",
        CALLER_WORKFLOW_REF=(
            f"{repository}/.github/workflows/"
            "trusted-ci-executor.yml@refs/heads/main"
        ),
        HEAD_REPOSITORY="",
        BASE_REF="",
        EVENT_PR_NUMBER="",
        DISPATCH_PR_NUMBER="6390",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert outputs == {
        "control_sha": "a" * 40,
        "pr_number": "6390",
        "mode": "dispatch",
        "semantic_workflow": "trusted-ci-executor",
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {"EVENT_NAME": "push"},
        {
            "CALLED_WORKFLOW_REF": (
                "mastermindx-market-intelligence/macro/.github/workflows/"
                "trusted-ci-executor.yml@refs/pull/6390/merge"
            )
        },
        {
            "CALLER_WORKFLOW_REF": (
                "mastermindx-market-intelligence/macro/.github/workflows/"
                "rogue.yml@refs/pull/6390/merge"
            )
        },
        {"HEAD_REPOSITORY": "attacker/fork"},
        {"BASE_REF": "release"},
        {"TRUSTED_REF": "refs/pull/6391/merge"},
        {"EVENT_PR_NUMBER": "6391"},
        {"DISPATCH_PR_NUMBER": "6390"},
        {"CALLED_WORKFLOW_SHA": "candidate"},
    ],
)
def test_p3ba_refuses_untrusted_call_contexts(
    tmp_path: Path, overrides: dict[str, str]
) -> None:
    result, outputs = run_trusted_gate(tmp_path, **overrides)
    assert result.returncode != 0
    assert outputs == {}


def test_p3ba_planner_uses_main_control_and_routes_one_or_all_exact_pr_packs() -> None:
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
    assert control_checkout["with"]["ref"] == (
        "${{ needs.trust-gate.outputs.control_sha }}"
    )
    assert control_checkout["with"]["persist-credentials"] is False

    resolve = next(step for step in steps if step.get("id") == "ref")
    assert "resolve_ci_canary_ref.py" in resolve["run"]
    assert '--github-sha "${{ needs.trust-gate.outputs.control_sha }}"' in resolve["run"]
    assert '--pr-number "${{ needs.trust-gate.outputs.pr_number }}"' in resolve["run"]
    candidate_checkout = next(
        step for step in steps if step.get("name") == "checkout the immutable PR candidate"
    )
    assert candidate_checkout["with"]["ref"] == "${{ steps.ref.outputs.tested_sha }}"
    assert candidate_checkout["with"]["persist-credentials"] is False

    planner = next(step for step in steps if step.get("id") == "plan")
    for token in (
        '--workflow-name "${{ needs.trust-gate.outputs.semantic_workflow }}"',
        '--event "${{ github.event_name }}"',
        "--role pr_head",
        "--gate code",
        "--tested-tree-sha",
        "--subject-head-sha",
        "--base-sha",
        "--changed-from",
    ):
        assert token in planner["run"]
    selector = next(step for step in steps if step.get("id") == "select")
    assert selector["env"] == {
        "EXECUTION_MODE": "${{ needs.trust-gate.outputs.mode }}",
        "FULL_MATRIX": "${{ steps.plan.outputs.matrix }}",
    }
    assert "--count 1" in selector["run"]
    assert "matrix=$FULL_MATRIX" in selector["run"]

    trusted_pack = document["jobs"]["trusted-pack"]
    assert trusted_pack["strategy"]["max-parallel"] == 3


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
