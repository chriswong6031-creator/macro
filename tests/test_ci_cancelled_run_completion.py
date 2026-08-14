"""Cancellation completion must prove, never infer, supersession."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import ci_cancelled_run_completion as COMPLETION  # noqa: E402


REPOSITORY = "mastermindx-market-intelligence/macro"
RUN_ID = 31763116872
OLD_HEAD = "5" * 40
NEW_HEAD = "e" * 40
WORKFLOW = ROOT / ".github/workflows/ci-cancelled-completion.yml"


def _event(*, head: str = OLD_HEAD, pulls: list[object] | None = None) -> dict:
    return {
        "action": "completed",
        "repository": {"full_name": REPOSITORY, "default_branch": "main"},
        "workflow_run": {
            "id": RUN_ID,
            "name": "ci",
            "event": "pull_request",
            "conclusion": "cancelled",
            "head_sha": head,
            "pull_requests": [{"number": 5506}] if pulls is None else pulls,
        },
    }


def _pull(*, head: str = NEW_HEAD, state: str = "open", number: int = 5506) -> dict:
    return {
        "number": number,
        "state": state,
        "base": {"repo": {"full_name": REPOSITORY}},
        "head": {"sha": head},
    }


def _classify(event: object, response: object = None) -> tuple[dict, list[tuple[str, int]]]:
    calls: list[tuple[str, int]] = []

    def get_pull(repository: str, number: int) -> object:
        calls.append((repository, number))
        if isinstance(response, BaseException):
            raise response
        return _pull() if response is None else response

    return COMPLETION.classify_cancelled_run(event, REPOSITORY, get_pull), calls


def test_different_current_open_pr_head_is_proven_superseded() -> None:
    disposition, calls = _classify(_event(), _pull(head=NEW_HEAD))

    assert calls == [(REPOSITORY, 5506)]
    assert disposition == {
        "schema": COMPLETION.SCHEMA,
        "original_run_id": RUN_ID,
        "workflow_name": "ci",
        "original_event": "pull_request",
        "original_head_sha": OLD_HEAD,
        "pull_request_number": 5506,
        "current_head_sha": NEW_HEAD,
        "api_evidence": "verified",
        "superseded": True,
        "category": "superseded",
        "reason": "read-only pull request evidence proves the cancelled head is obsolete",
    }


def test_same_head_operator_cancellation_is_infrastructure_not_superseded() -> None:
    disposition, calls = _classify(_event(), _pull(head=OLD_HEAD))

    assert calls == [(REPOSITORY, 5506)]
    assert disposition["superseded"] is False
    assert disposition["category"] == "infrastructure"
    assert disposition["api_evidence"] == "verified"
    assert disposition["current_head_sha"] == OLD_HEAD
    assert "operator or infrastructure" in disposition["reason"]


@pytest.mark.parametrize(
    "pulls,reason",
    [
        ([], "exactly one"),
        ([{"number": 1}, {"number": 2}], "exactly one"),
        ([{"number": "5506"}], "number is missing"),
    ],
)
def test_ambiguous_association_fails_closed_without_an_api_call(
    pulls: list[object], reason: str
) -> None:
    disposition, calls = _classify(_event(pulls=pulls))

    assert calls == []
    assert disposition["superseded"] is False
    assert disposition["category"] == "infrastructure"
    assert reason in disposition["reason"]


def test_api_failure_fails_closed_without_leaking_exception_detail() -> None:
    disposition, calls = _classify(_event(), RuntimeError("secret response body"))

    assert calls == [(REPOSITORY, 5506)]
    assert disposition["superseded"] is False
    assert disposition["category"] == "infrastructure"
    assert disposition["api_evidence"] == "unavailable"
    assert "RuntimeError" in disposition["reason"]
    assert "secret response body" not in disposition["reason"]


@pytest.mark.parametrize(
    "response",
    [
        _pull(head=NEW_HEAD, state="closed"),
        _pull(head=NEW_HEAD, number=9999),
        {**_pull(head=NEW_HEAD), "base": {"repo": {"full_name": "other/repo"}}},
        {**_pull(head=NEW_HEAD), "head": {"sha": "not-a-sha"}},
        [],
    ],
)
def test_untrusted_or_malformed_current_pr_response_fails_closed(response: object) -> None:
    disposition, calls = _classify(_event(), response)

    assert calls == [(REPOSITORY, 5506)]
    assert disposition["superseded"] is False
    assert disposition["category"] == "infrastructure"
    assert disposition["api_evidence"] == "rejected"


def test_non_pr_or_repository_mismatch_fails_closed_without_api() -> None:
    non_pr = _event()
    non_pr["workflow_run"]["event"] = "workflow_dispatch"
    disposition, calls = _classify(non_pr)
    assert calls == []
    assert disposition["category"] == "infrastructure"
    assert disposition["api_evidence"] == "not_applicable"

    mismatch = _event()
    mismatch["repository"]["full_name"] = "attacker/fork"
    disposition, calls = _classify(mismatch)
    assert calls == []
    assert disposition["superseded"] is False
    assert disposition["api_evidence"] == "rejected"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda event: event["workflow_run"].update(name="other"),
        lambda event: event["workflow_run"].update(conclusion="success"),
        lambda event: event.update(action="requested"),
        lambda event: event["workflow_run"].update(id=True),
    ],
)
def test_wrong_completion_envelope_is_rejected(mutation) -> None:
    event = _event()
    mutation(event)
    with pytest.raises(COMPLETION.CompletionContractError):
        _classify(event)


def test_completion_workflow_is_cancelled_only_read_only_and_immutable() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    doc = yaml.safe_load(source)
    job = doc["jobs"]["summarize-cancelled-run"]
    checkout, classify, materialize, validate, upload = job["steps"]

    assert "workflow_run:" in source
    assert "workflows: [ci]" in source
    assert "types: [completed]" in source
    assert "workflow_dispatch:" not in source
    assert "schedule:" not in source
    assert "push:" not in source
    assert doc["permissions"] == {}
    assert job["permissions"] == {
        "actions": "read",
        "contents": "read",
        "pull-requests": "read",
    }
    assert "workflow_run.conclusion == 'cancelled'" in job["if"]
    assert "workflow_run.id" in doc["concurrency"]["group"]
    assert doc["concurrency"]["cancel-in-progress"] is False
    assert job["timeout-minutes"] == 10

    assert checkout["with"]["ref"] == "${{ github.event.repository.default_branch }}"
    assert checkout["with"]["persist-credentials"] is False
    assert "head_sha" not in checkout["with"]["ref"]
    assert "ci_cancelled_run_completion.py" in classify["run"]
    assert materialize["run"].count("ci_collect_pack_evidence.py") == 3
    assert "ci_failure_summary.py" in materialize["run"]
    assert "GITHUB_STEP_SUMMARY" in validate["run"]
    assert "github.event.workflow_run.id" in upload["with"]["name"]
    assert upload["with"]["if-no-files-found"] == "error"

    uses = re.findall(r"uses:\s*([^\s]+)", source)
    assert uses
    assert all(re.fullmatch(r"[^@\s]+@[0-9a-f]{40}", use) for use in uses)
    assert any(use.startswith("actions/upload-artifact@") for use in uses)
    assert "urllib.request.Request" in (
        ROOT / "scripts/ci_cancelled_run_completion.py"
    ).read_text(encoding="utf-8")
    assert 'method="GET"' in (
        ROOT / "scripts/ci_cancelled_run_completion.py"
    ).read_text(encoding="utf-8")
