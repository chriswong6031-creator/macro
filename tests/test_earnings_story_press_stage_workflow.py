"""Closed, main-only, artifact-only workflow contract for earnings Press ingress."""
from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/earnings-story-press-stage.yml"
SCRIPT = ROOT / "scripts/stage_earnings_story_press.py"
CI_WORKFLOW = ROOT / ".github/workflows/ci.yml"
CI_MANIFEST = ROOT / ".github/ci/legacy-jobs.yml"


def _workflow() -> dict:
    return yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def test_workflow_is_manual_closed_input_main_only_and_serialized() -> None:
    workflow = _workflow()
    triggers = workflow["on"]
    assert set(triggers) == {"workflow_dispatch"}
    inputs = triggers["workflow_dispatch"]["inputs"]
    assert set(inputs) == {"generation_id", "packet_id", "story_revision_id"}
    assert all(row["required"] == "true" and row["type"] == "string" for row in inputs.values())
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"] == {
        "group": "earnings-story-press-stage",
        "cancel-in-progress": "false",
    }
    assert set(workflow["jobs"]) == {"stage"}
    gate = workflow["jobs"]["stage"]["if"]
    assert "github.ref == 'refs/heads/main'" in gate
    assert "vars.PRESS_PUBLISH_ENABLED == 'true'" in gate
    assert "vars.EARNINGS_STORY_INGRESS_ENABLED == 'true'" in gate


def test_workflow_uses_read_only_r2_identity_one_call_budget_and_artifact_only_output() -> None:
    body = WORKFLOW.read_text(encoding="utf-8")
    workflow = _workflow()
    steps = workflow["jobs"]["stage"]["steps"]
    run_text = "\n".join(str(step.get("run", "")) for step in steps)
    env = next(step["env"] for step in steps if step.get("name") == "full-audit and stage one exact packet")

    assert env["R2_ACCESS_KEY_ID"] == "${{ secrets.EARNINGS_R2_READ_ACCESS_KEY_ID }}"
    assert env["R2_SECRET_ACCESS_KEY"] == "${{ secrets.EARNINGS_R2_READ_SECRET_ACCESS_KEY }}"
    assert env["R2_ENDPOINT"] == "${{ secrets.EARNINGS_R2_READ_ENDPOINT }}"
    assert env["R2_BUCKET"] == "${{ secrets.EARNINGS_R2_READ_BUCKET }}"
    assert env["PRESS_RUN_TOKEN_BUDGET"] == "12000"
    assert env["PRESS_CIRCUIT_BREAKER_FAILURES"] == "1"
    assert env["CODEX_PROVIDER_ENABLED"] == "false"
    assert "DEEPSEEK_API_KEY" in env
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in env
    assert "ANTHROPIC_API_KEY" not in env
    assert env["EARNINGS_STAGE_GENERATION_ID"] == "${{ inputs.generation_id }}"
    assert env["EARNINGS_STAGE_PACKET_ID"] == "${{ inputs.packet_id }}"
    assert env["EARNINGS_STAGE_STORY_REVISION_ID"] == "${{ inputs.story_revision_id }}"
    assert "scripts.stage_earnings_story_press" in run_text
    assert "--generation-id" in run_text and "--packet-id" in run_text
    assert "--story-revision-id" in run_text

    lowered_runs = run_text.lower()
    for forbidden in (
        "--emit", "git commit", "git push", "put_object", "delete_object",
        "publish_earnings_story_packets_r2 --", "scripts.run_press",
    ):
        assert forbidden not in lowered_runs
    assert "contents: write" not in body
    assert "schedule:" not in body
    assert "secrets.R2_ACCESS_KEY_ID" not in body
    assert "secrets.R2_SECRET_ACCESS_KEY" not in body
    upload = next(step for step in steps if step.get("uses") == "actions/upload-artifact@v4")
    assert upload["if"] == "always()"
    assert upload["with"]["path"] == "${{ runner.temp }}/earnings-story-press-stage/"


def test_dispatch_inputs_never_cross_directly_into_a_shell_program() -> None:
    workflow = _workflow()
    for step in workflow["jobs"]["stage"]["steps"]:
        assert "${{ inputs." not in str(step.get("run", ""))


def test_ingress_cli_has_only_three_immutable_inputs_and_no_authority_knobs() -> None:
    body = SCRIPT.read_text(encoding="utf-8")
    parser_lines = [line.strip() for line in body.splitlines() if "parser.add_argument(" in line]
    assert parser_lines == [
        'parser.add_argument("--generation-id", required=True)',
        'parser.add_argument("--packet-id", required=True)',
        'parser.add_argument("--story-revision-id", required=True)',
    ]
    for forbidden in ("--tier", "--packet-path", "--slot", "--emit", "--staging-dir", "--root"):
        assert forbidden not in body


def test_ingress_subjects_and_suites_are_ci_reachable() -> None:
    ci = yaml.load(CI_WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    paths = set(ci["on"]["pull_request"]["paths"])
    required_paths = {
        "scripts/stage_earnings_story_press.py",
        ".github/workflows/earnings-story-press-stage.yml",
        "tests/test_earnings_story_press_admission.py",
        "tests/test_earnings_story_press_ingress.py",
        "tests/test_earnings_story_press_stage_workflow.py",
    }
    assert required_paths <= paths

    manifest = yaml.safe_load(CI_MANIFEST.read_text(encoding="utf-8"))
    commands = "\n".join(
        str(step.get("run", ""))
        for step in manifest["jobs"]["publish-r2-client"]["steps"]
    )
    for suite in required_paths & {path for path in required_paths if path.startswith("tests/")}:
        assert suite in commands
