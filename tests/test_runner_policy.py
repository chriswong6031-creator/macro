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
        "selfhosted-ci-canary.yml",
        "m1-runner-canary.yml",
        "ci-authority.yml",
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
