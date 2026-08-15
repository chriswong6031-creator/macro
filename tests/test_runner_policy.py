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
    for name in ("ci.yml", "fences.yml", "selfhosted-ci-canary.yml", "m1-runner-canary.yml"):
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


def test_ordinary_ci_and_fences_cannot_move_off_hosted(tmp_path: Path) -> None:
    root, registry, workflows = fixture_tree(tmp_path)
    ci = yaml.safe_load((workflows / "ci.yml").read_text(encoding="utf-8"))
    ci["jobs"]["ci-pack"]["runs-on"] = ["self-hosted", "ci-linux"]
    (workflows / "ci.yml").write_text(yaml.safe_dump(ci, sort_keys=False), encoding="utf-8")
    result = run_guard(root, registry, workflows)
    assert result.returncode == 1
    assert "R4" in result.stdout


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
        for step in document["jobs"]["selfhosted-pack"]["steps"]
        if step.get("uses") == "actions/checkout@v4"
    )
    checkout["with"].pop("persist-credentials")
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    result = run_guard(root, registry, workflows)
    assert result.returncode == 1
    assert "R10" in result.stdout
    assert "credential persistence" in result.stdout


def test_migration_job_cannot_bypass_hosted_main_trust_gate(tmp_path: Path) -> None:
    root, registry, workflows = fixture_tree(tmp_path)
    path = workflows / "m1-runner-canary.yml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    document["jobs"]["m1-service-canary"].pop("needs")
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    result = run_guard(root, registry, workflows)
    assert result.returncode == 1
    assert "R5" in result.stdout
