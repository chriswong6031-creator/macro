from __future__ import annotations

import copy
import subprocess
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts" / "check_runner_policy.py"
REGISTRY = ROOT / ".github" / "runner-policy.yml"
WORKFLOWS = ROOT / ".github" / "workflows"


def run_guard(root: Path, registry: Path, workflows: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "python3",
            str(GUARD),
            "--root",
            str(root),
            "--registry",
            str(registry),
            "--workflows-dir",
            str(workflows),
        ],
        text=True,
        capture_output=True,
        check=False,
    )


def fixture_tree(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = tmp_path
    workflows = root / ".github" / "workflows"
    workflows.mkdir(parents=True)
    for name in (
        "ci.yml",
        "fences.yml",
        "merge-on-green.yml",
        "selfhosted-ci-canary.yml",
        "m1-runner-canary.yml",
        "ci-authority.yml",
        "trusted-ci-executor.yml",
    ):
        (workflows / name).write_text((WORKFLOWS / name).read_text(encoding="utf-8"), encoding="utf-8")
    registry = root / ".github" / "runner-policy.yml"
    registry.write_text(REGISTRY.read_text(encoding="utf-8"), encoding="utf-8")
    return root, registry, workflows


def mutate_registry(path: Path, callback) -> None:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    callback(document)
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")


def test_live_tree_satisfies_transitional_policy() -> None:
    result = run_guard(ROOT, REGISTRY, WORKFLOWS)
    assert result.returncode == 0, result.stdout + result.stderr


def test_merge_control_registration_stays_live_as_w1b_rollback_capacity() -> None:
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    merge_control = registry["label_registry"]["merge-control"]
    assert merge_control["status"] == "live"
    assert merge_control["carried_by"] == ["mac-builder-4"]
    assert "rollback-only" in merge_control["note"].lower()
    assert "w5" in merge_control["note"].lower()


def test_fork_scenario_cannot_mutate_to_selfhosted(tmp_path: Path) -> None:
    root, registry, workflows = fixture_tree(tmp_path)
    mutate_registry(registry, lambda doc: doc["scenario_routes"].__setitem__("fork_pr", "pc-ci"))
    result = run_guard(root, registry, workflows)
    assert result.returncode == 1
    assert "R1" in result.stdout


def test_server_side_runner_group_cannot_lose_main_pinned_workflow_restriction(
    tmp_path: Path,
) -> None:
    root, registry, workflows = fixture_tree(tmp_path)
    mutate_registry(
        registry,
        lambda doc: doc["runtime_runner_group"].__setitem__(
            "restricted_to_workflows", False
        ),
    )
    result = run_guard(root, registry, workflows)
    assert result.returncode == 1
    assert "runner-group policy drifted" in result.stdout


def test_p3ba_executor_is_main_pinned_and_call_capable_but_route_stays_hosted() -> None:
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    assert registry["phase"] == "p3b-a-call-capable"
    selected = set(registry["runtime_runner_group"]["selected_workflows"])
    assert (
        "mastermindx-market-intelligence/macro/.github/workflows/"
        "trusted-ci-executor.yml@refs/heads/main"
    ) in selected
    assert registry["scenario_routes"]["same_repo_ordinary_pr"] == "github-hosted"
    assert registry["scenario_routes"]["fork_pr"] == "github-hosted"
    route = registry["trusted_executor_route"]
    assert route == {
        "workflow": ".github/workflows/trusted-ci-executor.yml",
        "job": "trusted-pack",
        "group": "macro-home-canary",
        "labels": ["ci-linux"],
        "call_enabled": True,
        "production_enabled": False,
    }


def test_p3ba_policy_rejects_early_production_enable(tmp_path: Path) -> None:
    root, registry, workflows = fixture_tree(tmp_path)
    mutate_registry(
        registry,
        lambda doc: doc["trusted_executor_route"].__setitem__(
            "production_enabled", True
        ),
    )
    result = run_guard(root, registry, workflows)
    assert result.returncode == 1
    assert "R13" in result.stdout
    assert "P3B-A" in result.stdout


def _mutate_trusted_gate(tmp_path: Path, old: str, new: str) -> subprocess.CompletedProcess[str]:
    root, registry, workflows = fixture_tree(tmp_path)
    path = workflows / "trusted-ci-executor.yml"
    rendered = path.read_text(encoding="utf-8")
    assert old in rendered
    path.write_text(rendered.replace(old, new, 1), encoding="utf-8")
    return run_guard(root, registry, workflows)


def test_p3ba_policy_rejects_disabled_main_called_workflow_refusal(
    tmp_path: Path,
) -> None:
    result = _mutate_trusted_gate(
        tmp_path,
        'test "$CALLED_WORKFLOW_REF" = "$trusted_workflow_ref" || {',
        'true || { # test "$CALLED_WORKFLOW_REF" = "$trusted_workflow_ref" || {',
    )
    assert result.returncode == 1
    assert "R13" in result.stdout


def test_p3ba_policy_rejects_disabled_direct_main_ref_refusal(tmp_path: Path) -> None:
    result = _mutate_trusted_gate(
        tmp_path,
        'test "$TRUSTED_REF" = refs/heads/main || {',
        'true || { # test "$TRUSTED_REF" = refs/heads/main || {',
    )
    assert result.returncode == 1
    assert "R13" in result.stdout


def test_p3ba_policy_rejects_disabled_same_repo_refusal(
    tmp_path: Path,
) -> None:
    result = _mutate_trusted_gate(
        tmp_path,
        'test "$HEAD_REPOSITORY" = "$REPOSITORY" || {',
        'true || { # test "$HEAD_REPOSITORY" = "$REPOSITORY" || {',
    )
    assert result.returncode == 1
    assert "R13" in result.stdout


def test_p3ba_policy_rejects_disabled_exact_ci_caller_refusal(
    tmp_path: Path,
) -> None:
    result = _mutate_trusted_gate(
        tmp_path,
        'test "$CALLER_WORKFLOW_REF" = "$expected_caller_ref" || {',
        'true || { # test "$CALLER_WORKFLOW_REF" = "$expected_caller_ref" || {',
    )
    assert result.returncode == 1
    assert "R13" in result.stdout


def test_p3ba_policy_rejects_new_caller_supplied_inputs(tmp_path: Path) -> None:
    root, registry, workflows = fixture_tree(tmp_path)
    path = workflows / "trusted-ci-executor.yml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    trigger_config = document.get("on", document.get(True))
    trigger_config["workflow_call"]["inputs"]["tested_sha"] = {
        "required": False,
        "type": "string",
    }
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    result = run_guard(root, registry, workflows)
    assert result.returncode == 1
    assert "R13" in result.stdout


def test_p3ba_policy_rejects_a_second_runner_group_consumer(tmp_path: Path) -> None:
    root, registry, workflows = fixture_tree(tmp_path)
    path = workflows / "trusted-ci-executor.yml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    document["jobs"]["rogue-group-job"] = {
        "runs-on": {"group": "macro-home-canary"},
        "steps": [{"run": "echo rogue"}],
    }
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    result = run_guard(root, registry, workflows)
    assert result.returncode == 1
    assert "R13" in result.stdout
    assert "runner-group consumer" in result.stdout


def test_ordinary_ci_and_fences_cannot_move_off_hosted(tmp_path: Path) -> None:
    root, registry, workflows = fixture_tree(tmp_path)
    ci = yaml.safe_load((workflows / "ci.yml").read_text(encoding="utf-8"))
    ci["jobs"]["ci-pack"]["runs-on"] = ["self-hosted", "ci-linux"]
    (workflows / "ci.yml").write_text(yaml.safe_dump(ci, sort_keys=False), encoding="utf-8")
    result = run_guard(root, registry, workflows)
    assert result.returncode == 1
    assert "R4" in result.stdout


def test_merge_control_cannot_move_off_hosted(tmp_path: Path) -> None:
    root, registry, workflows = fixture_tree(tmp_path)
    merge_control = yaml.safe_load(
        (workflows / "merge-on-green.yml").read_text(encoding="utf-8")
    )
    merge_control["jobs"]["sweep"]["runs-on"] = [
        "self-hosted",
        "macOS",
        "ARM64",
        "merge-control",
    ]
    (workflows / "merge-on-green.yml").write_text(
        yaml.safe_dump(merge_control, sort_keys=False), encoding="utf-8"
    )
    result = run_guard(root, registry, workflows)
    assert result.returncode == 1
    assert "R4" in result.stdout
    assert "merge-on-green.yml:sweep" in result.stdout


def test_ci_and_render_slot_labels_cannot_recombine(tmp_path: Path) -> None:
    root, registry, workflows = fixture_tree(tmp_path)
    mutate_registry(
        registry,
        lambda doc: doc["pool_topology"]["pc-ci"]["labels"].append("render-linux"),
    )
    result = run_guard(root, registry, workflows)
    assert result.returncode == 1
    assert "R7" in result.stdout


def test_m1_workflow_cannot_regain_generic_production_label(tmp_path: Path) -> None:
    root, registry, workflows = fixture_tree(tmp_path)
    path = workflows / "m1-runner-canary.yml"
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    workflow["jobs"]["m1-service-canary"]["runs-on"].append("macstudio")
    path.write_text(yaml.safe_dump(workflow, sort_keys=False), encoding="utf-8")
    result = run_guard(root, registry, workflows)
    assert result.returncode == 1
    assert "R8" in result.stdout


def test_unregistered_custom_label_consumer_fails(tmp_path: Path) -> None:
    root, registry, workflows = fixture_tree(tmp_path)
    (workflows / "rogue.yml").write_text(
        "on:\n  workflow_dispatch:\njobs:\n  rogue:\n    runs-on: [self-hosted, ci-linux]\n    steps:\n      - run: true\n",
        encoding="utf-8",
    )
    result = run_guard(root, registry, workflows)
    assert result.returncode == 1
    assert "R6" in result.stdout


def test_pull_request_target_is_never_registerable(tmp_path: Path) -> None:
    root, registry, workflows = fixture_tree(tmp_path)
    (workflows / "rogue.yml").write_text(
        "on:\n  pull_request_target:\njobs:\n  rogue:\n    runs-on: ubuntu-latest\n    steps:\n      - run: true\n",
        encoding="utf-8",
    )
    result = run_guard(root, registry, workflows)
    assert result.returncode == 1
    assert "R2" in result.stdout
    assert "rogue.yml: pull_request_target is forbidden" in result.stdout


def test_trusted_ci_authority_is_the_only_allowed_pull_request_target(
    tmp_path: Path,
) -> None:
    """The live controller is allowed; a second pull_request_target file is not."""
    root, registry, workflows = fixture_tree(tmp_path)
    result = run_guard(root, registry, workflows)
    assert result.returncode == 0, result.stdout + result.stderr
    (workflows / "also-authority.yml").write_text(
        (WORKFLOWS / "ci-authority.yml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    result = run_guard(root, registry, workflows)
    assert result.returncode == 1
    assert "also-authority.yml: pull_request_target is forbidden" in result.stdout


def test_ci_authority_loses_r2_if_it_checkouts_the_candidate(tmp_path: Path) -> None:
    root, registry, workflows = fixture_tree(tmp_path)
    path = workflows / "ci-authority.yml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    document["jobs"]["ci-authority"]["steps"][0]["with"]["ref"] = (
        "${{ github.event.pull_request.head.sha }}"
    )
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    result = run_guard(root, registry, workflows)
    assert result.returncode == 1
    assert "R2" in result.stdout
    assert "default branch without credentials" in result.stdout
    assert "must not materialize candidate code" in result.stdout


def test_computed_migration_label_cannot_hide_a_pull_request_selfhosted_route(tmp_path: Path) -> None:
    root, registry, workflows = fixture_tree(tmp_path)
    (workflows / "rogue.yml").write_text(
        "on:\n  pull_request:\njobs:\n  rogue:\n"
        "    runs-on: [self-hosted, \"m1-${{ 'theta' }}\"]\n"
        "    steps:\n      - run: true\n",
        encoding="utf-8",
    )
    result = run_guard(root, registry, workflows)
    assert result.returncode == 1
    assert "R3" in result.stdout


def test_pull_request_job_cannot_delegate_to_a_reusable_workflow(tmp_path: Path) -> None:
    root, registry, workflows = fixture_tree(tmp_path)
    (workflows / "rogue.yml").write_text(
        "on:\n  pull_request:\njobs:\n  delegated:\n"
        "    uses: ./.github/workflows/hidden-selfhosted.yml\n",
        encoding="utf-8",
    )
    result = run_guard(root, registry, workflows)
    assert result.returncode == 1
    assert "R3" in result.stdout
    assert "may not delegate" in result.stdout


def test_canary_candidate_checkout_cannot_persist_the_job_token(tmp_path: Path) -> None:
    root, registry, workflows = fixture_tree(tmp_path)
    path = workflows / "selfhosted-ci-canary.yml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    checkout = next(
        step
        for step in document["jobs"]["hosted-control"]["steps"]
        if step.get("uses") == "actions/checkout@v4"
        and "tested_sha" in str(step.get("with", {}).get("ref", ""))
    )
    checkout["with"].pop("persist-credentials")
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    result = run_guard(root, registry, workflows)
    assert result.returncode == 1
    assert "R10" in result.stdout
    assert "credential persistence" in result.stdout


def test_selfhosted_candidate_fetch_cannot_restore_no_negotiation_transfer(tmp_path: Path) -> None:
    root, registry, workflows = fixture_tree(tmp_path)
    path = workflows / "selfhosted-ci-canary.yml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    materialize = next(
        step
        for step in document["jobs"]["selfhosted-pack"]["steps"]
        if step.get("name", "").startswith("materialize exact candidate")
    )
    materialize["run"] = materialize["run"].replace(
        "fetch.negotiationAlgorithm=skipping", "fetch.negotiationAlgorithm=noop"
    )
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    result = run_guard(root, registry, workflows)
    assert result.returncode == 1
    assert "R9" in result.stdout
    assert "candidate fetch" in result.stdout


def test_selfhosted_candidate_fetch_checks_credentials_before_network(tmp_path: Path) -> None:
    root, registry, workflows = fixture_tree(tmp_path)
    path = workflows / "selfhosted-ci-canary.yml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    materialize = next(
        step
        for step in document["jobs"]["selfhosted-pack"]["steps"]
        if step.get("name", "").startswith("materialize exact candidate")
    )
    lines = materialize["run"].splitlines()
    guard = next(i for i, line in enumerate(lines) if "extraheader" in line)
    lines.append(lines.pop(guard))
    materialize["run"] = "\n".join(lines) + "\n"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    result = run_guard(root, registry, workflows)
    assert result.returncode == 1
    assert "R9" in result.stdout
    assert "credential-free" in result.stdout


def test_contamination_probe_cannot_fetch_missing_objects(tmp_path: Path) -> None:
    root, registry, workflows = fixture_tree(tmp_path)
    path = workflows / "selfhosted-ci-canary.yml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    detach = next(
        step
        for step in document["jobs"]["contamination-probe"]["steps"]
        if step.get("name", "").startswith("detach the second")
    )
    detach["run"] += "git fetch origin main\n"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    result = run_guard(root, registry, workflows)
    assert result.returncode == 1
    assert "R9" in result.stdout
    assert "cache-only" in result.stdout


def test_migration_job_cannot_bypass_hosted_main_trust_gate(tmp_path: Path) -> None:
    root, registry, workflows = fixture_tree(tmp_path)
    path = workflows / "m1-runner-canary.yml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    document["jobs"]["m1-service-canary"].pop("needs")
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    result = run_guard(root, registry, workflows)
    assert result.returncode == 1
    assert "R5" in result.stdout


# ── label registry (R11/R12), added 2026-08-17 ────────────────────────────────
# `fixture_tree` copies only five workflows and other tests depend on that exact
# set, so R11/R12 cases that need a synthetic workflow write one directly into
# the fixture's workflows dir instead of touching `fixture_tree` itself.


def write_synthetic_workflow(workflows: Path, name: str, content: str) -> Path:
    path = workflows / name
    path.write_text(content, encoding="utf-8")
    return path


def test_unregistered_runs_on_label_fails_r11(tmp_path: Path) -> None:
    root, registry, workflows = fixture_tree(tmp_path)
    write_synthetic_workflow(
        workflows,
        "mystery.yml",
        "on:\n  workflow_dispatch:\n"
        "jobs:\n  mystery:\n"
        "    runs-on: [self-hosted, mystery-label]\n"
        "    steps:\n      - run: true\n",
    )
    result = run_guard(root, registry, workflows)
    assert result.returncode == 1
    assert "R11" in result.stdout
    assert "mystery-label" in result.stdout
    assert "mystery.yml:mystery" in result.stdout


def test_fromjson_expression_label_is_extracted_by_r11(tmp_path: Path) -> None:
    """Dropping `ci-linux-canary` from the registry reds the REAL
    selfhosted-ci-canary.yml `selfhosted-pack` job, whose `runs-on` is
    `${{ fromJSON(inputs.slots == '1' && '["self-hosted","ci-linux-canary"]' ||
    '["self-hosted","ci-linux"]') }}` — proving the extractor reaches into the
    fromJSON ternary rather than only seeing plain lists, and that it does NOT
    also invent a phantom label out of the `'1'` comparison operand next to it
    (that would make this fixture red for an unrelated reason).
    """
    root, registry, workflows = fixture_tree(tmp_path)
    mutate_registry(registry, lambda doc: doc["label_registry"].pop("ci-linux-canary"))
    result = run_guard(root, registry, workflows)
    assert result.returncode == 1
    assert "R11" in result.stdout
    assert "ci-linux-canary" in result.stdout
    assert "selfhosted-ci-canary.yml:selfhosted-pack" in result.stdout
    assert "'1'" not in result.stdout


def test_scheduled_workflow_on_orphaned_label_without_waiver_fails_r12(tmp_path: Path) -> None:
    root, registry, workflows = fixture_tree(tmp_path)
    mutate_registry(
        registry,
        lambda doc: doc["label_registry"]["ci-linux"].update(
            {"status": "orphaned", "carried_by": []}
        ),
    )
    write_synthetic_workflow(
        workflows,
        "orphan-cron.yml",
        "on:\n  schedule:\n    - cron: '5 5 * * *'\n"
        "jobs:\n  orphan:\n"
        "    runs-on: [self-hosted, ci-linux]\n"
        "    steps:\n      - run: true\n",
    )
    result = run_guard(root, registry, workflows)
    assert result.returncode == 1
    assert "R12" in result.stdout
    assert "ci-linux" in result.stdout
    assert "orphan-cron.yml:orphan" in result.stdout


def test_scheduled_orphaned_label_with_valid_waiver_does_not_fail_r12(tmp_path: Path) -> None:
    root, registry, workflows = fixture_tree(tmp_path)
    write_synthetic_workflow(
        workflows,
        "orphan-cron.yml",
        "on:\n  schedule:\n    - cron: '5 5 * * *'\n"
        "jobs:\n  orphan:\n"
        "    runs-on: [self-hosted, ci-linux]\n"
        "    steps:\n      - run: true\n",
    )
    def orphan_with_waiver(document: dict) -> None:
        document["label_registry"]["ci-linux"].update(
            {
                "status": "orphaned",
                "carried_by": [],
                "scheduled_use_waiver": {
                    "since": "2026-08-17",
                    "reason": "test waiver has both fields",
                },
            }
        )

    mutate_registry(registry, orphan_with_waiver)
    result = run_guard(root, registry, workflows)
    assert "R12" not in result.stdout


def test_scheduled_workflow_on_offline_label_does_not_fail_r12(tmp_path: Path) -> None:
    root, registry, workflows = fixture_tree(tmp_path)
    write_synthetic_workflow(
        workflows,
        "offline-cron.yml",
        "on:\n  schedule:\n    - cron: '5 5 * * *'\n"
        "jobs:\n  offline:\n"
        "    runs-on: [self-hosted, Linux, X64, render-linux]\n"
        "    steps:\n      - run: true\n",
    )
    result = run_guard(root, registry, workflows)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "R12" not in result.stdout


def test_live_label_with_empty_carried_by_fails_r11_hygiene(tmp_path: Path) -> None:
    root, registry, workflows = fixture_tree(tmp_path)
    mutate_registry(
        registry,
        lambda doc: doc["label_registry"]["macstudio"].__setitem__("carried_by", []),
    )
    result = run_guard(root, registry, workflows)
    assert result.returncode == 1
    assert "R11" in result.stdout
    assert "macstudio" in result.stdout
    assert "carried_by" in result.stdout


def test_codex_registry_entry_keeps_its_scheduled_waiver() -> None:
    """Deleting the waiver without restoring the host must red — this pins the
    waiver's presence so that deletion is caught by `test_...without_waiver`-style
    coverage rather than silently reopening the R12 hole R11/R12 exist to close.
    """
    document = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    codex = document["label_registry"]["codex"]
    assert codex["status"] == "orphaned"
    waiver = codex["scheduled_use_waiver"]
    assert waiver["reason"]
    assert waiver["since"]
