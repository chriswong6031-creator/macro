from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def workflow(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def named_step(job: dict, name: str) -> dict:
    return next(step for step in job["steps"] if step.get("name") == name)


def test_p3bb_same_repo_pr_calls_only_the_exact_main_owned_executor() -> None:
    jobs = workflow("ci.yml")["jobs"]
    trusted = jobs["trusted-ci"]

    assert trusted == {
        "name": "trusted-ci",
        "needs": "ci-plan",
        "if": (
            "needs.ci-plan.outputs.has_work == 'true' && "
            "github.event.pull_request.head.repo.full_name == github.repository"
        ),
        "uses": (
            "mastermindx-market-intelligence/macro/.github/workflows/"
            "trusted-ci-executor.yml@main"
        ),
        "permissions": {"contents": "read", "pull-requests": "read"},
    }
    assert "with" not in trusted
    assert "secrets" not in trusted


def test_p3bb_keeps_hosted_pack_names_as_trusted_relays_or_fork_executors() -> None:
    job = workflow("ci.yml")["jobs"]["ci-pack"]

    assert job["name"] == "ci-pack-${{ matrix.pack }}"
    assert job["runs-on"] == "ubuntu-latest"
    assert job["needs"] == ["ci-plan", "trusted-ci"]
    assert job["strategy"] == {
        "fail-fast": False,
        "matrix": "${{ fromJSON(needs.ci-plan.outputs.matrix) }}",
    }
    assert job["if"] == (
        "always() && needs.ci-plan.result == 'success' && "
        "needs.ci-plan.outputs.has_work == 'true' && "
        "(github.event.pull_request.head.repo.full_name != github.repository || "
        "needs.trusted-ci.result == 'success')"
    )

    same_repo_guard = (
        "github.event.pull_request.head.repo.full_name == github.repository"
    )
    fork_guard = (
        "github.event.pull_request.head.repo.full_name != github.repository"
    )
    relay = named_step(job, "relay the trusted pack fragment under the existing check contract")
    assert relay["if"] == same_repo_guard
    assert relay["uses"] == (
        "actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093"
    )
    assert relay["with"] == {
        "name": "trusted-ci-fragment-${{ matrix.pack }}",
        "path": "${{ runner.temp }}/trusted-ci-fragment",
    }

    parity = named_step(job, "bind trusted execution to the hosted authoritative plan")
    assert parity["if"] == same_repo_guard
    assert parity["env"] == {
        "HOSTED_PLAN_SHA": "${{ needs.ci-plan.outputs.plan_sha }}",
        "TRUSTED_PLAN_SHA": "${{ needs.trusted-ci.outputs.plan_sha }}",
        "TRUSTED_FRAGMENT": (
            "${{ runner.temp }}/trusted-ci-fragment/trusted-fragment.json"
        ),
        "RELAY_FRAGMENT": (
            "${{ runner.temp }}/ci-semantic-fragments/pack-${{ matrix.pack }}.json"
        ),
    }
    assert "plan_sha256" in parity["run"]
    assert "HOSTED_PLAN_SHA" in parity["run"]
    assert "TRUSTED_PLAN_SHA" in parity["run"]

    upload = named_step(job, "publish this pack's raw semantic fragment")
    assert upload["if"] == "always() && needs.ci-plan.outputs.plan_sha != ''"
    assert upload["with"]["name"] == (
        "ci-semantic-pack-${{ github.run_id }}-${{ matrix.pack }}"
    )
    assert upload["with"]["path"] == (
        "${{ runner.temp }}/ci-semantic-fragments/pack-${{ matrix.pack }}.json"
    )

    # Candidate-authored code may retain the hosted fork implementation, but every
    # heavyweight checkout/setup/execute step must be mechanically unreachable for
    # a same-repository PR after the main-defined executor has run.
    for step in job["steps"]:
        if step is relay or step is parity or step is upload:
            continue
        if step.get("uses") in {
            "actions/checkout@v4",
            "actions/setup-python@v5",
            "actions/setup-node@v4",
            "actions/download-artifact@v4",
        } or step.get("name") in {
            "install isolated pack runner",
            "download the authoritative semantic plan",
            "publish the changed-file handle",
            "validate and run legacy CI pack",
            "fail-safe full suite when no authoritative plan was produced",
        }:
            assert fork_guard in step["if"]


def test_p3bb_keeps_the_existing_hosted_semantic_gate_and_fork_path() -> None:
    jobs = workflow("ci.yml")["jobs"]
    gate = jobs["ci-gate"]
    assert gate["needs"] == ["ci-plan", "ci-pack", "contract-delta"]
    assert gate["runs-on"] == "ubuntu-latest"
    assert gate["if"] == "always()"

    pack = jobs["ci-pack"]
    checkout = next(step for step in pack["steps"] if step.get("uses") == "actions/checkout@v4")
    assert checkout["if"] == (
        "github.event.pull_request.head.repo.full_name != github.repository"
    )
    execute = named_step(pack, "validate and run legacy CI pack")
    assert "scripts/run_ci_pack.py" in execute["run"]


def test_p3bb_policy_declares_only_same_repo_production_on_pc() -> None:
    registry = yaml.safe_load(
        (ROOT / ".github" / "runner-policy.yml").read_text(encoding="utf-8")
    )
    assert registry["phase"] == "p3b-b-production-route"
    assert registry["repository_visibility"] == "public"
    assert registry["scenario_routes"] == {
        "same_repo_ordinary_pr": "pc-ci-via-main-executor",
        "fork_pr": "github-hosted",
        "trusted_dispatch_canary": "pc-ci-canary",
        "trusted_executor_dispatch": "pc-ci",
    }
    assert registry["trusted_executor_route"]["call_enabled"] is True
    assert registry["trusted_executor_route"]["production_enabled"] is True
    assert registry["protected_hosted_routes"][0] == {
        "workflow": ".github/workflows/ci.yml",
        "jobs": ["ci-plan", "ci-pack", "ci-gate"],
    }


def test_p3bb_called_pack_exports_main_derived_host_admission_facts() -> None:
    job = workflow("trusted-ci-executor.yml")["jobs"]["trusted-pack"]
    assert job["env"] == {
        "MASTERMIND_TRUSTED_HEAD_REPOSITORY": (
            "${{ github.event.pull_request.head.repo.full_name }}"
        ),
        "MASTERMIND_TRUSTED_BASE_REF": "${{ github.base_ref }}",
        "MASTERMIND_TRUSTED_CONTROL_SHA": "${{ needs.plan.outputs.control_sha }}",
    }
