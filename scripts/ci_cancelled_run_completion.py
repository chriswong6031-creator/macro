#!/usr/bin/env python3
"""Classify one cancelled CI workflow run without guessing supersession.

The ``workflow_run`` payload identifies the cancelled run, but its embedded
pull-request object is not an authoritative statement of the pull request's
*current* head.  Supersession is therefore emitted only after a read-only GET
of the associated open pull request proves that its current head differs from
the cancelled run's head.  Missing, ambiguous, malformed, or unavailable API
evidence fails closed to ``infrastructure``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any


SCHEMA = "ci.cancelled_run_disposition.v1"
_SHA = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?")


class CompletionContractError(ValueError):
    """The trusted workflow invoked the classifier with an invalid envelope."""


class GitHubReadError(RuntimeError):
    """The read-only pull-request request did not produce usable JSON."""


def _mapping(value: object) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _sha(value: object) -> str | None:
    return value if type(value) is str and _SHA.fullmatch(value) else None


def _positive_int(value: object) -> int | None:
    return value if type(value) is int and value > 0 else None


def _base_disposition(
    *,
    run_id: int,
    workflow_name: str,
    original_event: str,
    original_head_sha: str | None,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "original_run_id": run_id,
        "workflow_name": workflow_name,
        "original_event": original_event,
        "original_head_sha": original_head_sha,
        "pull_request_number": None,
        "current_head_sha": None,
        "api_evidence": "unavailable",
        "superseded": False,
        "category": "infrastructure",
        "reason": "supersession was not proven",
    }


def _fail_closed(
    disposition: dict[str, Any],
    reason: str,
    *,
    api_evidence: str = "unavailable",
) -> dict[str, Any]:
    result = dict(disposition)
    result["api_evidence"] = api_evidence
    result["superseded"] = False
    result["category"] = "infrastructure"
    result["reason"] = reason
    return result


def classify_cancelled_run(
    payload: object,
    expected_repository: str,
    get_pull: Callable[[str, int], object],
) -> dict[str, Any]:
    """Return a strict disposition for one cancelled ``ci`` workflow run.

    ``get_pull`` is deliberately a GET-only dependency.  Any failure or
    ambiguity is represented as infrastructure; the only path to
    ``superseded: true`` is a verified, different current head SHA.
    """
    event = _mapping(payload)
    if event is None:
        raise CompletionContractError("workflow_run event must be an object")
    run = _mapping(event.get("workflow_run"))
    repository = _mapping(event.get("repository"))
    if run is None or repository is None:
        raise CompletionContractError(
            "workflow_run event requires workflow_run and repository objects"
        )

    run_id = _positive_int(run.get("id"))
    workflow_name = run.get("name")
    original_event = run.get("event")
    if run_id is None:
        raise CompletionContractError("workflow_run.id must be a positive integer")
    if workflow_name != "ci":
        raise CompletionContractError("workflow_run.name must be 'ci'")
    if run.get("conclusion") != "cancelled":
        raise CompletionContractError("workflow_run.conclusion must be 'cancelled'")
    if event.get("action") != "completed":
        raise CompletionContractError("workflow_run action must be 'completed'")
    if type(original_event) is not str:
        raise CompletionContractError("workflow_run.event must be a string")

    original_head = _sha(run.get("head_sha"))
    disposition = _base_disposition(
        run_id=run_id,
        workflow_name=workflow_name,
        original_event=original_event,
        original_head_sha=original_head,
    )

    event_repository = repository.get("full_name")
    if (
        type(expected_repository) is not str
        or not expected_repository
        or event_repository != expected_repository
    ):
        return _fail_closed(
            disposition,
            "event repository does not match the trusted workflow repository",
            api_evidence="rejected",
        )
    if original_head is None:
        return _fail_closed(
            disposition,
            "cancelled workflow head SHA is missing or malformed",
            api_evidence="rejected",
        )
    if original_event != "pull_request":
        return _fail_closed(
            disposition,
            "cancelled run was not a pull_request workflow",
            api_evidence="not_applicable",
        )

    associated = run.get("pull_requests")
    if not isinstance(associated, list) or len(associated) != 1:
        return _fail_closed(
            disposition,
            "cancelled run does not identify exactly one associated pull request",
        )
    associated_pr = _mapping(associated[0])
    number = None if associated_pr is None else _positive_int(associated_pr.get("number"))
    if number is None:
        return _fail_closed(
            disposition,
            "associated pull request number is missing or malformed",
            api_evidence="rejected",
        )
    disposition["pull_request_number"] = number

    try:
        current = get_pull(expected_repository, number)
    except Exception as exc:  # The disposition, not an exception, is the durable result.
        return _fail_closed(
            disposition,
            "current pull request API evidence is unavailable "
            f"({type(exc).__name__})",
        )
    current_pr = _mapping(current)
    if current_pr is None:
        return _fail_closed(
            disposition,
            "current pull request API response is not an object",
            api_evidence="rejected",
        )
    base = _mapping(current_pr.get("base"))
    base_repo = None if base is None else _mapping(base.get("repo"))
    head = _mapping(current_pr.get("head"))
    current_head = None if head is None else _sha(head.get("sha"))
    if (
        _positive_int(current_pr.get("number")) != number
        or base_repo is None
        or base_repo.get("full_name") != expected_repository
        or current_pr.get("state") != "open"
        or current_head is None
    ):
        return _fail_closed(
            disposition,
            "current pull request API response failed identity, state, or head validation",
            api_evidence="rejected",
        )

    disposition["current_head_sha"] = current_head
    disposition["api_evidence"] = "verified"
    if current_head == original_head:
        return _fail_closed(
            disposition,
            "current pull request head matches the cancelled run; "
            "operator or infrastructure cancellation cannot be called superseded",
            api_evidence="verified",
        )

    disposition["superseded"] = True
    disposition["category"] = "superseded"
    disposition["reason"] = (
        "read-only pull request evidence proves the cancelled head is obsolete"
    )
    return disposition


class GitHubApi:
    """Minimal GitHub REST reader; this controller has no mutation method."""

    def __init__(self, api_url: str, token: str) -> None:
        if not api_url.startswith("https://"):
            raise GitHubReadError("GITHUB_API_URL must use https")
        if not token:
            raise GitHubReadError("GITHUB_TOKEN is absent")
        self.api_url = api_url.rstrip("/")
        self.token = token

    def get_pull(self, repository: str, number: int) -> object:
        owner, separator, name = repository.partition("/")
        if not separator or not owner or not name or "/" in name:
            raise GitHubReadError("repository must be owner/name")
        path = "/repos/{}/{}/pulls/{}".format(
            urllib.parse.quote(owner, safe=""),
            urllib.parse.quote(name, safe=""),
            number,
        )
        request = urllib.request.Request(
            self.api_url + path,
            method="GET",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "macro-ci-cancelled-run-completion",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                status = response.status
                body = response.read(2_000_001)
        except (OSError, urllib.error.HTTPError, urllib.error.URLError) as exc:
            raise GitHubReadError("pull request GET failed") from exc
        if status != 200:
            raise GitHubReadError(f"pull request GET returned HTTP {status}")
        if len(body) > 2_000_000:
            raise GitHubReadError("pull request response exceeds size bound")
        try:
            return json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GitHubReadError("pull request response is not valid JSON") from exc


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CompletionContractError(f"cannot read workflow event JSON: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--event",
        type=Path,
        default=Path(os.environ.get("GITHUB_EVENT_PATH", "")),
    )
    args = parser.parse_args(argv)
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    try:
        def get_pull(repo: str, number: int) -> object:
            # Construct lazily so a missing token or malformed API URL becomes
            # durable fail-closed evidence instead of aborting summary creation.
            api = GitHubApi(
                os.environ.get("GITHUB_API_URL", "https://api.github.com"),
                os.environ.get("GITHUB_TOKEN", ""),
            )
            return api.get_pull(repo, number)

        disposition = classify_cancelled_run(
            _read_json(args.event), repository, get_pull
        )
    except CompletionContractError as exc:
        print(f"cancelled CI completion: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(disposition, ensure_ascii=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
