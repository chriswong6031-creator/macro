from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "fences.yml"
CANARY_CONTRACT_PATH = ROOT / "tests" / "test_ci_canary_workflows.py"


def _document() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _named_step(job: dict, name: str) -> dict:
    matches = [step for step in job["steps"] if step.get("name") == name]
    assert len(matches) == 1, (name, [step.get("name") for step in job["steps"]])
    return matches[0]


def _load_canary_contract_module():
    spec = importlib.util.spec_from_file_location(
        "fence_owned_ci_canary_contract", CANARY_CONTRACT_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_same_repo_fence_checkout_is_bounded_sparse_and_blob_filtered() -> None:
    job = _document()["jobs"]["fence-pack"]
    checkout = next(step for step in job["steps"] if step.get("uses") == "actions/checkout@v4")
    options = checkout["with"]

    assert options["filter"] == "blob:none"
    assert options["fetch-depth"] == 256
    assert options["sparse-checkout-cone-mode"] is False

    sparse = {line.strip() for line in str(options["sparse-checkout"]).splitlines() if line.strip()}
    required = {
        "/.github/",
        "/config/",
        "/engine/metabolism/",
        "/engine/neuralweb/",
        "/engine/foresight_leadlag.py",
        "/engine/theme_placebo.py",
        "/engine/qledger_falsifier.py",
        "/lib/",
        "/scripts/",
        "/templates/",
        "/tests/",
        "/site/chat.html",
        "/data/neuralweb/capability_audit.jsonl",
        "/data/metabolism/key_ledger.jsonl",
        "/data/metabolism/journal/",
        "/data/ai_costs/usage.jsonl",
        "/config.yml",
    }
    assert required <= sparse
    assert "/site/" not in sparse
    assert "/data/" not in sparse


def test_self_mod_live_check_uses_exact_synthetic_parents_and_fails_closed() -> None:
    job = _document()["jobs"]["fence-pack"]
    live = _named_step(job, "self-mod-fence live check (loop PR + immutable → BLOCKED)")
    command = live["run"]

    assert 'git rev-list --parents -n 1 "$GITHUB_SHA"' in command
    assert "expected one synthetic merge with exactly two parents" in command
    assert 'MERGE_BASE=$(git merge-base "$TESTED_BASE_SHA" "$SUBJECT_HEAD_SHA")' in command
    assert 'git log --format="%B" "$MERGE_BASE..$SUBJECT_HEAD_SHA"' in command
    assert 'git diff --name-only "$MERGE_BASE" "$SUBJECT_HEAD_SHA"' in command
    assert "could not establish exact PR ancestry inside the bounded checkout" in command
    assert "git fetch " not in command
    assert "origin/${{ github.base_ref" not in command


def test_self_mod_fence_suite_pins_checkout_contract() -> None:
    job = _document()["jobs"]["fence-pack"]
    suite = _named_step(job, "self-mod-fence test suite")["run"]
    assert "tests/test_self_mod_fence.py" in suite
    assert "tests/test_fence_checkout_contract.py" in suite


def test_hosted_merge_control_canary_contract_executes_in_fast_fence() -> None:
    """Reuse the canonical W1-A assertions inside the always-on PR fence.

    ``workflow-yaml`` also names ``test_ci_canary_workflows.py``, but that logical
    job is ``gate: data`` and therefore is not a PR merge precondition. Loading the
    canonical module here makes the hosted-canary safety contract execute in the
    already-required ``fence-pack`` without copying the assertions or adding a
    parallel CI workflow.
    """

    contract = _load_canary_contract_module()
    contract.test_canaries_are_dispatch_only_and_not_merge_authority()
    contract.test_merge_control_hosted_canary_is_read_only_main_pinned_and_non_acting()
