from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "fences.yml"


def _document() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _named_step(job: dict, name: str) -> dict:
    matches = [step for step in job["steps"] if step.get("name") == name]
    assert len(matches) == 1, (name, [step.get("name") for step in job["steps"]])
    return matches[0]


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
