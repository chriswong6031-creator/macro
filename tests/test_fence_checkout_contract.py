from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "fences.yml"
CANARY_CONTRACT_PATH = ROOT / "tests" / "test_ci_canary_workflows.py"
HOLD_SUITE_PATH = ROOT / "tests" / "test_ship_loop_hold_wrapper.py"


def _document() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _named_step(job: dict, name: str) -> dict:
    matches = [step for step in job["steps"] if step.get("name") == name]
    assert len(matches) == 1, (name, [step.get("name") for step in job["steps"]])
    return matches[0]


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_canary_contract_module():
    return _load_module(CANARY_CONTRACT_PATH, "fence_owned_ci_canary_contract")


def _load_hold_suite_module():
    return _load_module(HOLD_SUITE_PATH, "fence_owned_ship_loop_hold_contract")


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


def test_hold_wrapper_regressions_execute_inside_the_fast_fence() -> None:
    """Execute the canonical HOLD state regressions in required fences.

    ``audit_unrun_tests.py`` understands direct legacy-manifest ownership only, so
    the separate waiver records this intentional transitive fast-fence ownership.
    This is the executable half: every canonical regression is invoked here rather
    than copied into a second assertion set.
    """
    hold = _load_hold_suite_module()
    hold.test_exact_sol_hold_protocol_is_recognized()
    for mutation in (
        {"draft": False},
        {"labels": [{"name": "merge-on-green"}]},
        {"auto_merge": {"merge_method": "SQUASH"}},
        {"title": "please hold this for later"},
        {"body": "HOLD-FOR-SOL. Do not merge. Authority: session. Release condition: session."},
        {"body": "HOLD-FOR-SOL. Do not merge. Authority: Sol. Release condition: CI green."},
    ):
        hold.test_incomplete_or_unsafe_hold_fails_closed(mutation)
    hold.test_markdown_protocol_fields_are_not_required_to_be_plain_text()

    with tempfile.TemporaryDirectory() as raw:
        tmp_path = Path(raw)
        with pytest.MonkeyPatch.context() as monkeypatch:
            hold.test_lawful_concluded_green_hold_becomes_parked(monkeypatch, tmp_path)
        with pytest.MonkeyPatch.context() as monkeypatch:
            hold.test_lawful_sol_authority_branch_parks_after_unsafe_branch(
                monkeypatch, tmp_path
            )
        with pytest.MonkeyPatch.context() as monkeypatch:
            hold.test_lawful_sol_authority_branch_parks_before_first_unsafe_branch(
                monkeypatch, tmp_path
            )
        with pytest.MonkeyPatch.context() as monkeypatch:
            hold.test_unsafe_branch_hold_exception_is_sol_namespace_only(
                monkeypatch, tmp_path
            )
        with pytest.MonkeyPatch.context() as monkeypatch:
            hold.test_red_or_pending_claude_hold_does_not_park(monkeypatch, tmp_path)
        with pytest.MonkeyPatch.context() as monkeypatch:
            hold.test_pending_sol_hold_waits_before_first_unsafe_branch_remediation(
                monkeypatch, tmp_path
            )
        with pytest.MonkeyPatch.context() as monkeypatch:
            hold.test_red_sol_hold_repairs_check_without_branch_remediation(
                monkeypatch, tmp_path
            )
        with pytest.MonkeyPatch.context() as monkeypatch:
            hold.test_dirty_or_not_exactly_pushed_hold_does_not_park(monkeypatch, tmp_path)
        with pytest.MonkeyPatch.context() as monkeypatch:
            hold.test_hold_probe_spends_no_github_quota_outside_candidate_branches(
                monkeypatch, tmp_path
            )

    hold.test_stop_hook_routes_through_wrapper_but_keeps_original_guard_as_delegate()
