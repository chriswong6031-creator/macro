#!/usr/bin/env python3
"""Trusted-base gate for files capable of manufacturing CI proof.

``pull_request_target`` runs this controller from the default branch.  It never
checks out or executes pull-request code.  The event identifies the proposed
head and base, then read-only API calls re-prove the current PR identity and
enumerate its exact changed files.  Complementary base-specific checks are
written to that exact head: the current-base verdict and a terminal failure for
the other supported base.  They must never be the sole required authority; the
organization required-workflow rule and its stable ``ci-authority`` job remain
mandatory.

Read-only GET calls (``get_pull``, ``list_pull_files``,
``get_collaborator_permission``) are retried with bounded backoff on transient
conditions only (timeouts, 429/408/5xx, and rate-limit-shaped 403s); the gate
still fails closed on every non-transient or exhausted-retry outcome, and the
published reject reason names the failure mode (rate limited, timeout,
rejected, or unavailable) instead of one opaque string.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

try:
    from scripts.ci_authority_paths import (
        AuthorityPathError,
        canonical_repo_path,
        is_ci_authority_path,
    )
except ModuleNotFoundError:  # Direct ``python scripts/ci_authority.py``.
    from ci_authority_paths import (  # type: ignore[no-redef]
        AuthorityPathError,
        canonical_repo_path,
        is_ci_authority_path,
    )


SCHEMA = "ci.authority.v1"
CHECK_NAME = "ci-authority"
SUPPORTED_BASE_REFS = ("main", "codex/merge-queue-pilot")
MAX_CHANGED_FILES = 3000  # GitHub's pull-files API hard ceiling.
MAX_AUTHORITY_PATHS_IN_RECEIPT = 20
MAX_RECEIPT_PATH_CHARS = 160
_SHA = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?")

API_TIMEOUT_SECONDS = 20
API_RETRY_ATTEMPTS = 4  # one initial attempt plus up to three retries
API_RETRY_BASE_DELAY_SECONDS = 1.0
API_RETRY_MAX_DELAY_SECONDS = 8.0
API_RETRY_TOTAL_BUDGET_SECONDS = 45.0
RETRYABLE_HTTP_STATUSES = frozenset({408, 429, 500, 502, 503, 504})


class AuthorityContractError(ValueError):
    """The trusted workflow received an unusable event envelope."""


class GitHubApiError(RuntimeError):
    """A GitHub API request did not produce bounded, usable evidence."""

    def __init__(
        self,
        message: str,
        *,
        kind: str = "unavailable",
        status: int | None = None,
        retryable: bool = False,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.status = status
        self.retryable = retryable
        self.retry_after = retry_after


class AuthorityApi(Protocol):
    def get_pull(self, repository: str, number: int) -> object: ...

    def list_pull_files(
        self, repository: str, number: int, expected_count: int
    ) -> object: ...

    def get_collaborator_permission(self, repository: str, login: str) -> object: ...

    def create_check(self, repository: str, payload: Mapping[str, object]) -> object: ...


def _mapping(value: object) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _sha(value: object) -> str | None:
    return value if type(value) is str and _SHA.fullmatch(value) else None


def _positive_int(value: object) -> int | None:
    return value if type(value) is int and value > 0 else None


def _nonnegative_int(value: object) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _safe_login(value: object) -> str | None:
    if type(value) is not str or not (1 <= len(value) <= 100):
        return None
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        return None
    return value


def _safe_ref(value: object) -> str | None:
    if type(value) is not str or not (1 <= len(value.encode("utf-8")) <= 1024):
        return None
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        return None
    if (
        value.startswith("/")
        or value.endswith("/")
        or value.startswith(".")
        or value.endswith(".")
        or ".." in value
        or "@{" in value
        or "\\" in value
        or any(character in value for character in " ~^:?*[")
    ):
        return None
    return value


def _repository(value: object) -> str | None:
    if type(value) is not str or value.count("/") != 1:
        return None
    owner, name = value.split("/", 1)
    if not owner or not name or len(value) > 200:
        return None
    if any(ord(character) < 33 or ord(character) > 126 for character in value):
        return None
    return value


def _event_target(payload: object, expected_repository: str) -> dict[str, object]:
    event = _mapping(payload)
    if event is None:
        raise AuthorityContractError("event must be an object")
    repository = _mapping(event.get("repository"))
    pull = _mapping(event.get("pull_request"))
    sender = _mapping(event.get("sender"))
    action = event.get("action")
    if repository is None or pull is None or sender is None:
        raise AuthorityContractError(
            "event requires repository, pull_request, and sender"
        )
    if action not in {"opened", "synchronize", "reopened", "edited"}:
        raise AuthorityContractError("unsupported pull_request_target action")
    trusted_repository = _repository(expected_repository)
    if trusted_repository is None or repository.get("full_name") != trusted_repository:
        raise AuthorityContractError("event repository does not match workflow repository")

    number = _positive_int(pull.get("number"))
    head = _mapping(pull.get("head"))
    head_repo = None if head is None else _mapping(head.get("repo"))
    base = _mapping(pull.get("base"))
    base_repo = None if base is None else _mapping(base.get("repo"))
    user = _mapping(pull.get("user"))
    head_sha = None if head is None else _sha(head.get("sha"))
    head_repository = None if head_repo is None else _repository(head_repo.get("full_name"))
    base_sha = None if base is None else _sha(base.get("sha"))
    base_ref = None if base is None else _safe_ref(base.get("ref"))
    base_repository = None if base_repo is None else _repository(base_repo.get("full_name"))
    author = None if user is None else _safe_login(user.get("login"))
    actor = _safe_login(sender.get("login"))
    if (
        number is None
        or head_sha is None
        or head_repository is None
        or base_sha is None
        or base_ref is None
        or base_repository != trusted_repository
        or author is None
        or actor is None
    ):
        raise AuthorityContractError("event PR identity is missing or malformed")
    return {
        "repository": trusted_repository,
        "pull_request_number": number,
        "event_action": action,
        "head_sha": head_sha,
        "head_repository": head_repository,
        "base_sha": base_sha,
        "base_ref": base_ref,
        "base_repository": base_repository,
        "author": author,
        "actor": actor,
    }


def _base_decision(target: Mapping[str, object]) -> dict[str, object]:
    return {
        "schema": SCHEMA,
        "event": "pull_request_target",
        **target,
        "changed_file_count": None,
        "authority_hit_count": 0,
        "authority_hits": [],
        "author_admin_verified": False,
        "actor_admin_verified": False,
        "admin_verified": False,
        "allowed": False,
        "reason": "unproven",
    }


def _reject(decision: Mapping[str, object], reason: str) -> dict[str, object]:
    result = dict(decision)
    result["allowed"] = False
    result["reason"] = reason
    return result


def _current_pull_identity(
    response: object, target: Mapping[str, object]
) -> tuple[Mapping[str, Any], int] | None:
    pull = _mapping(response)
    if pull is None:
        return None
    base = _mapping(pull.get("base"))
    base_repo = None if base is None else _mapping(base.get("repo"))
    head = _mapping(pull.get("head"))
    head_repo = None if head is None else _mapping(head.get("repo"))
    user = _mapping(pull.get("user"))
    changed_count = _nonnegative_int(pull.get("changed_files"))
    if (
        pull.get("number") != target["pull_request_number"]
        or pull.get("state") != "open"
        or base_repo is None
        or base_repo.get("full_name") != target["repository"]
        or _sha(base.get("sha")) is None
        or _safe_ref(base.get("ref")) is None
        or head is None
        or _sha(head.get("sha")) is None
        or head_repo is None
        or _repository(head_repo.get("full_name")) is None
        or user is None
        or _safe_login(user.get("login")) is None
        or changed_count is None
        or changed_count > MAX_CHANGED_FILES
    ):
        return None
    return pull, changed_count


def _changed_paths(file_entries: object, expected_count: int) -> tuple[str, ...]:
    if not isinstance(file_entries, Sequence) or isinstance(file_entries, (str, bytes)):
        raise AuthorityContractError("pull files response is not an array")
    if len(file_entries) != expected_count:
        raise AuthorityContractError("pull files response count does not match current PR")
    paths: list[str] = []
    current_names: set[str] = set()
    for entry in file_entries:
        item = _mapping(entry)
        if item is None:
            raise AuthorityContractError("pull files response contains a non-object")
        status = item.get("status")
        if status not in {
            "added",
            "removed",
            "modified",
            "renamed",
            "copied",
            "changed",
            "unchanged",
        }:
            raise AuthorityContractError("pull files response has an unknown status")
        current = canonical_repo_path(item.get("filename"))
        if current in current_names:
            raise AuthorityContractError("pull files response repeats a filename")
        current_names.add(current)
        paths.append(current)
        previous = item.get("previous_filename")
        if status == "renamed" and previous is None:
            raise AuthorityContractError("renamed file omits previous_filename")
        if previous is not None:
            paths.append(canonical_repo_path(previous))
    return tuple(dict.fromkeys(paths))


def _identity_still_matches(
    current: Mapping[str, Any],
    target: Mapping[str, object],
) -> bool:
    head = _mapping(current.get("head"))
    head_repo = None if head is None else _mapping(head.get("repo"))
    base = _mapping(current.get("base"))
    base_repo = None if base is None else _mapping(base.get("repo"))
    user = _mapping(current.get("user"))
    return bool(
        head is not None
        and head_repo is not None
        and base is not None
        and base_repo is not None
        and user is not None
        and head.get("sha") == target["head_sha"]
        and head_repo.get("full_name") == target["head_repository"]
        and base.get("sha") == target["base_sha"]
        and base.get("ref") == target["base_ref"]
        and base_repo.get("full_name") == target["base_repository"]
        and user.get("login") == target["author"]
    )


def _permission_proves_admin(response: object, login: str) -> bool:
    permission = _mapping(response)
    permission_user = None if permission is None else _mapping(permission.get("user"))
    return bool(
        permission is not None
        and permission.get("permission") == "admin"
        and permission_user is not None
        and permission_user.get("login") == login
    )


def _receipt_path(path: str) -> str:
    """Keep the check summary bounded without losing long-path identity."""
    if len(path) <= MAX_RECEIPT_PATH_CHARS:
        return path
    digest = hashlib.sha256(path.encode("utf-8")).hexdigest()
    prefix = path[: MAX_RECEIPT_PATH_CHARS - 70]
    return f"{prefix}...sha256:{digest}"


_API_FAILURE_SUFFIX = {
    "rate_limited": "rate_limited",
    "timeout": "timeout",
    "rejected": "api_rejected",
}


def _api_failure_reason(prefix: str, exc: BaseException) -> str:
    """Name the failure MODE so triage does not restart from zero."""
    kind = getattr(exc, "kind", "")
    return f"{prefix}_{_API_FAILURE_SUFFIX.get(kind, 'api_unavailable')}"


def _log_api_failure(stage: str, exc: BaseException) -> None:
    """Surface the swallowed exception instead of discarding it silently.

    A GitHub annotation MUST start at column 0 of a bare ``print`` — never go
    through a logger, which prefixes the line and makes GitHub drop it (house
    law, ``tests/test_gh_annotation_line_start.py``). The full traceback goes
    to stderr for humans reading the job log.
    """
    status = getattr(exc, "status", None)
    kind = getattr(exc, "kind", None)
    cause = exc.__cause__
    detail = f"{stage}: {type(exc).__name__}: {exc}"
    if status is not None:
        detail += f" (status={status})"
    if kind:
        detail += f" (kind={kind})"
    if cause is not None:
        detail += f" (cause={type(cause).__name__}: {cause})"
    detail = " ".join(detail.split())
    if len(detail) > 300:
        detail = detail[:300]
    print(f"::error title=ci-authority-api::{detail}", flush=True)
    traceback_text = "".join(
        traceback.format_exception(type(exc), exc, exc.__traceback__)
    )
    print(traceback_text, file=sys.stderr)


def evaluate_pull_request_target(
    payload: object,
    expected_repository: str,
    api: AuthorityApi,
) -> dict[str, object]:
    """Return a fail-closed authority decision from current GitHub evidence."""
    target = _event_target(payload, expected_repository)
    decision = _base_decision(target)
    number = int(target["pull_request_number"])
    repository = str(target["repository"])

    try:
        current_response = api.get_pull(repository, number)
    except Exception as exc:
        _log_api_failure("current_pull", exc)
        return _reject(decision, _api_failure_reason("current_pull", exc))
    identity = _current_pull_identity(current_response, target)
    if identity is None:
        return _reject(decision, "current_pull_identity_rejected")
    current, changed_count = identity
    if not _identity_still_matches(current, target):
        return _reject(decision, "event_head_base_or_author_drift")

    try:
        entries = api.list_pull_files(repository, number, changed_count)
        paths = _changed_paths(entries, changed_count)
    except (AuthorityContractError, AuthorityPathError):
        return _reject(decision, "changed_files_rejected")
    except Exception as exc:
        _log_api_failure("changed_files", exc)
        return _reject(decision, _api_failure_reason("changed_files", exc))

    # The files endpoint is PR-number scoped rather than SHA scoped. Re-read the
    # PR after pagination so a push between the first identity GET and the last
    # files page cannot let a new candidate inherit an old inventory (or vice
    # versa). The new synchronize event will evaluate the new head independently.
    try:
        after_response = api.get_pull(repository, number)
    except Exception as exc:
        _log_api_failure("post_files_pull", exc)
        return _reject(decision, _api_failure_reason("post_files_pull", exc))
    after_identity = _current_pull_identity(after_response, target)
    if (
        after_identity is None
        or after_identity[1] != changed_count
        or not _identity_still_matches(after_identity[0], target)
    ):
        return _reject(decision, "event_head_base_or_files_drift")

    authority_hits = sorted(path for path in paths if is_ci_authority_path(path))
    decision["changed_file_count"] = changed_count
    decision["authority_hit_count"] = len(authority_hits)
    decision["authority_hits"] = [
        _receipt_path(path)
        for path in authority_hits[:MAX_AUTHORITY_PATHS_IN_RECEIPT]
    ]
    if not authority_hits:
        decision["allowed"] = True
        decision["reason"] = "ordinary_change"
        return decision

    if target["head_repository"] != repository:
        return _reject(decision, "fork_cannot_change_ci_authority")

    try:
        author_permission = api.get_collaborator_permission(
            repository, str(target["author"])
        )
    except Exception as exc:
        _log_api_failure("author_admin_permission", exc)
        return _reject(decision, _api_failure_reason("author_admin_permission", exc))
    if not _permission_proves_admin(author_permission, str(target["author"])):
        return _reject(decision, "same_repo_author_is_not_admin")
    decision["author_admin_verified"] = True

    # PR authorship is stable across synchronize events and therefore cannot
    # identify who pushed the exact head being evaluated. Bind the signed event
    # sender and re-check that actor's live repository permission too. Reuse the
    # author result only when GitHub identifies the same login in both fields.
    if target["actor"] == target["author"]:
        actor_permission = author_permission
    else:
        try:
            actor_permission = api.get_collaborator_permission(
                repository, str(target["actor"])
            )
        except Exception as exc:
            _log_api_failure("actor_admin_permission", exc)
            return _reject(decision, _api_failure_reason("actor_admin_permission", exc))
    if not _permission_proves_admin(actor_permission, str(target["actor"])):
        return _reject(decision, "current_head_actor_is_not_admin")

    decision["actor_admin_verified"] = True
    decision["admin_verified"] = True
    decision["allowed"] = True
    decision["reason"] = "same_repo_admin_authority_change"
    return decision


def _completed_check_payload(
    receipt: Mapping[str, object],
    *,
    name: str,
    head_sha: str,
    external_id: str,
    allowed: bool,
    details_url: str = "",
) -> dict[str, object]:
    """Build complementary evidence; never the sole required authority."""
    if _sha(head_sha) is None or not name.startswith(CHECK_NAME + "/"):
        raise AuthorityContractError("check cannot identify an exact supported context")
    summary = json.dumps(receipt, ensure_ascii=True, separators=(",", ":"))
    payload: dict[str, object] = {
        "name": name,
        "head_sha": head_sha,
        "status": "completed",
        "conclusion": "success" if allowed else "failure",
        "external_id": external_id,
        "output": {
            "title": (
                "CI authority context accepted"
                if allowed
                else "CI authority context rejected"
            ),
            "summary": summary,
        },
    }
    if details_url:
        if not details_url.startswith("https://") or len(details_url) > 2048:
            raise AuthorityContractError("details URL must be bounded HTTPS")
        payload["details_url"] = details_url
    return payload


def _base_context_receipt(
    decision: Mapping[str, object], context_base_ref: str
) -> tuple[dict[str, object], bool]:
    active = decision.get("base_ref") == context_base_ref
    allowed = active and decision.get("allowed") is True
    receipt = dict(decision)
    receipt.update(
        {
            "check_context": f"{CHECK_NAME}/{context_base_ref}",
            "context_base_ref": context_base_ref,
            "context_active": active,
            "context_allowed": allowed,
            "context_reason": (
                decision.get("reason") if active else "inactive_base_context"
            ),
        }
    )
    return receipt, allowed


def check_payload(
    decision: Mapping[str, object],
    context_base_ref: str,
    *,
    details_url: str = "",
) -> dict[str, object]:
    """Build one PR base-context check on the exact proposed head."""
    if context_base_ref not in SUPPORTED_BASE_REFS:
        raise AuthorityContractError("unsupported base-specific authority context")
    head_sha = _sha(decision.get("head_sha"))
    number = _positive_int(decision.get("pull_request_number"))
    repository = _repository(decision.get("repository"))
    if head_sha is None or number is None or repository is None:
        raise AuthorityContractError("decision cannot identify an exact PR head")
    receipt, allowed = _base_context_receipt(decision, context_base_ref)
    return _completed_check_payload(
        receipt,
        name=f"{CHECK_NAME}/{context_base_ref}",
        head_sha=head_sha,
        external_id=(
            f"{SCHEMA}:{repository}:{number}:{head_sha}:{context_base_ref}"
        ),
        allowed=allowed,
        details_url=details_url,
    )


def run_pull_request_target(
    payload: object,
    expected_repository: str,
    api: AuthorityApi,
    *,
    details_url: str = "",
) -> tuple[int, dict[str, object], dict[str, object]]:
    """Publish current-base verdict plus terminal invalidation of the other base."""
    decision = evaluate_pull_request_target(payload, expected_repository, api)
    current_base = decision.get("base_ref")
    if current_base in SUPPORTED_BASE_REFS:
        ordered_bases = tuple(
            base_ref
            for base_ref in SUPPORTED_BASE_REFS
            if base_ref != current_base
        ) + (str(current_base),)
    else:
        decision = _reject(decision, "unsupported_base_ref")
        ordered_bases = SUPPORTED_BASE_REFS
    # Invalidate the inactive context first. If publication later fails, the
    # organization required workflow is red and no stale cross-base success can
    # be treated as current by the complementary branch rule.
    checks: list[dict[str, object]] = []
    for base_ref in ordered_bases:
        check = check_payload(decision, base_ref, details_url=details_url)
        try:
            api.create_check(expected_repository, check)
        except Exception as exc:
            raise GitHubApiError(
                "completed base-specific ci-authority check could not be created"
            ) from exc
        checks.append(check)
    active_check = next(
        (check for check in checks if check["name"] == f"{CHECK_NAME}/{current_base}"),
        checks[-1],
    )
    return (0 if decision["allowed"] is True else 1), decision, active_check


def evaluate_merge_group(payload: object, expected_repository: str) -> dict[str, object]:
    """Validate the queue event consumed by the trusted-default-branch job."""
    event = _mapping(payload)
    repository = None if event is None else _mapping(event.get("repository"))
    group = None if event is None else _mapping(event.get("merge_group"))
    raw_base_ref = None if group is None else group.get("base_ref")
    prefix = "refs/heads/"
    base_ref = (
        _safe_ref(raw_base_ref[len(prefix) :])
        if type(raw_base_ref) is str and raw_base_ref.startswith(prefix)
        else None
    )
    if (
        event is None
        or event.get("action") != "checks_requested"
        or repository is None
        or repository.get("full_name") != _repository(expected_repository)
        or group is None
        or _sha(group.get("head_sha")) is None
        or _sha(group.get("base_sha")) is None
        or base_ref not in SUPPORTED_BASE_REFS
    ):
        raise AuthorityContractError("merge_group event identity is missing or malformed")
    return {
        "schema": SCHEMA,
        "event": "merge_group",
        "repository": expected_repository,
        "head_sha": group["head_sha"],
        "base_sha": group["base_sha"],
        "base_ref": base_ref,
        "base_repository": expected_repository,
        "allowed": True,
        "reason": "trusted_default_branch_merge_group",
    }


def run_merge_group(
    payload: object,
    expected_repository: str,
    api: AuthorityApi,
    *,
    details_url: str = "",
) -> tuple[int, dict[str, object], dict[str, object]]:
    """Publish the matching base-specific context on the synthetic queue head."""
    decision = evaluate_merge_group(payload, expected_repository)
    head_sha = str(decision["head_sha"])
    base_ref = str(decision["base_ref"])
    receipt, allowed = _base_context_receipt(decision, base_ref)
    check = _completed_check_payload(
        receipt,
        name=f"{CHECK_NAME}/{base_ref}",
        head_sha=head_sha,
        external_id=(
            f"{SCHEMA}:{expected_repository}:merge_group:{head_sha}:{base_ref}"
        ),
        allowed=allowed,
        details_url=details_url,
    )
    try:
        api.create_check(expected_repository, check)
    except Exception as exc:
        raise GitHubApiError(
            "completed merge-group ci-authority check could not be created"
        ) from exc
    return 0, decision, check


def _retry_after_seconds(headers: Any) -> float | None:
    """Read a server-provided retry hint, tolerating a missing header object.

    ``urllib`` hands back an ``email.message.Message`` whose ``.get`` is
    already case-insensitive, so no case-folding is required here.
    """
    if headers is None:
        return None
    retry_after = headers.get("Retry-After")
    if retry_after is not None:
        try:
            seconds = float(int(str(retry_after).strip()))
        except (TypeError, ValueError):
            pass
        else:
            return seconds if seconds >= 0 else None
    if headers.get("x-ratelimit-remaining") == "0":
        reset = headers.get("x-ratelimit-reset")
        try:
            seconds = float(reset) - time.time()
        except (TypeError, ValueError):
            return None
        return seconds if seconds >= 0 else None
    return None


def _api_failure_message(method: str, status: int | None) -> str:
    if status is None:
        return f"GitHub {method} request failed"
    return f"GitHub {method} request failed (HTTP {status})"


def _classify_api_exception(method: str, exc: BaseException) -> GitHubApiError:
    """Turn a raw urllib failure into a fail-closed, retry-aware error.

    Retryable means transient only: timeouts and 408/429/5xx are retried; a
    403 is retried solely when the response itself says it is a rate limit
    (header or body), never treated as a permission verdict by default; every
    other 4xx (401, 403 without a rate-limit signal, 404, ...) is a genuine
    rejection and must never be retried.
    """
    if isinstance(exc, urllib.error.HTTPError):
        status = getattr(exc, "status", None) or getattr(exc, "code", None)
        headers = getattr(exc, "headers", None)
        retry_after = _retry_after_seconds(headers)
        if status == 429:
            return GitHubApiError(
                _api_failure_message(method, status),
                kind="rate_limited",
                status=status,
                retryable=True,
                retry_after=retry_after,
            )
        if status == 403:
            rate_limited = retry_after is not None
            if not rate_limited:
                try:
                    body = exc.read(2048)
                    text = body.decode("utf-8", errors="replace")
                except Exception:
                    text = ""
                if "rate limit" in text.lower():
                    rate_limited = True
            if rate_limited:
                return GitHubApiError(
                    _api_failure_message(method, status),
                    kind="rate_limited",
                    status=status,
                    retryable=True,
                    retry_after=retry_after,
                )
            return GitHubApiError(
                _api_failure_message(method, status),
                kind="rejected",
                status=status,
                retryable=False,
            )
        if status == 408:
            return GitHubApiError(
                _api_failure_message(method, status),
                kind="timeout",
                status=status,
                retryable=True,
                retry_after=retry_after,
            )
        if status in RETRYABLE_HTTP_STATUSES:
            return GitHubApiError(
                _api_failure_message(method, status),
                kind="unavailable",
                status=status,
                retryable=True,
                retry_after=retry_after,
            )
        return GitHubApiError(
            _api_failure_message(method, status),
            kind="rejected",
            status=status,
            retryable=False,
        )
    if isinstance(exc, TimeoutError) or (
        isinstance(exc, urllib.error.URLError)
        and isinstance(exc.reason, TimeoutError)
    ):
        return GitHubApiError(
            _api_failure_message(method, None), kind="timeout", retryable=True
        )
    return GitHubApiError(
        _api_failure_message(method, None), kind="unavailable", retryable=True
    )


class GitHubApi:
    """Small REST client exposing only the calls required by this controller."""

    def __init__(
        self,
        api_url: str,
        token: str,
        *,
        sleep=time.sleep,
        jitter=random.random,
        retry_attempts: int = API_RETRY_ATTEMPTS,
        retry_budget: float = API_RETRY_TOTAL_BUDGET_SECONDS,
    ) -> None:
        if not api_url.startswith("https://"):
            raise GitHubApiError("GITHUB_API_URL must use https")
        if not token:
            raise GitHubApiError("GITHUB_TOKEN is absent")
        self.api_url = api_url.rstrip("/")
        self.token = token
        self._sleep = sleep
        self._jitter = jitter
        self._retry_attempts = retry_attempts
        self._retry_budget = retry_budget

    @staticmethod
    def _repo_path(repository: str) -> str:
        trusted = _repository(repository)
        if trusted is None:
            raise GitHubApiError("repository must be owner/name")
        owner, name = trusted.split("/", 1)
        return "/repos/{}/{}".format(
            urllib.parse.quote(owner, safe=""),
            urllib.parse.quote(name, safe=""),
        )

    def _attempt_json(
        self,
        method: str,
        path: str,
        *,
        payload: Mapping[str, object] | None = None,
        expected_status: int,
    ) -> object:
        body = None
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "macro-ci-authority",
        }
        if payload is not None:
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.api_url + path,
            data=body,
            method=method,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(
                request, timeout=API_TIMEOUT_SECONDS
            ) as response:
                status = response.status
                response_body = response.read(4_000_001)
        except (OSError, urllib.error.HTTPError, urllib.error.URLError) as exc:
            raise _classify_api_exception(method, exc) from exc
        if status != expected_status:
            raise GitHubApiError(
                f"GitHub {method} returned HTTP {status}, expected {expected_status}"
            )
        if len(response_body) > 4_000_000:
            raise GitHubApiError("GitHub response exceeds size bound")
        try:
            return json.loads(response_body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GitHubApiError("GitHub response is not valid JSON") from exc

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        payload: Mapping[str, object] | None = None,
        expected_status: int,
    ) -> object:
        """Retry a bounded number of times on transient GET failures only.

        POST is never retried here: ``create_check`` is not idempotent, and a
        retried POST that actually succeeded server-side would publish a
        duplicate check run on the PR head.
        """
        remaining_budget = self._retry_budget
        last_exc: GitHubApiError | None = None
        for attempt in range(1, self._retry_attempts + 1):
            try:
                return self._attempt_json(
                    method, path, payload=payload, expected_status=expected_status
                )
            except GitHubApiError as exc:
                last_exc = exc
                if (
                    method != "GET"
                    or not exc.retryable
                    or attempt >= self._retry_attempts
                ):
                    raise
                if exc.retry_after is not None:
                    delay = (
                        min(max(exc.retry_after, 0.0), API_RETRY_MAX_DELAY_SECONDS)
                        + self._jitter() * API_RETRY_BASE_DELAY_SECONDS
                    )
                else:
                    base = min(
                        API_RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1)),
                        API_RETRY_MAX_DELAY_SECONDS,
                    )
                    delay = base * (0.5 + 0.5 * self._jitter())
                if delay > remaining_budget:
                    raise
                print(
                    f"::warning title=ci-authority-api-retry::"
                    f"{method} {path} attempt {attempt} failed "
                    f"({exc.kind}); retrying in {delay:.2f}s",
                    flush=True,
                )
                self._sleep(delay)
                remaining_budget -= delay
        assert last_exc is not None  # pragma: no cover - loop always raises or returns
        raise last_exc

    def get_pull(self, repository: str, number: int) -> object:
        return self._request_json(
            "GET",
            f"{self._repo_path(repository)}/pulls/{number}",
            expected_status=200,
        )

    def list_pull_files(
        self, repository: str, number: int, expected_count: int
    ) -> object:
        if not (0 <= expected_count <= MAX_CHANGED_FILES):
            raise GitHubApiError("changed-file count exceeds API proof ceiling")
        entries: list[object] = []
        page_count = max(1, (expected_count + 99) // 100)
        for page in range(1, page_count + 1):
            response = self._request_json(
                "GET",
                f"{self._repo_path(repository)}/pulls/{number}/files"
                f"?per_page=100&page={page}",
                expected_status=200,
            )
            if not isinstance(response, list):
                raise GitHubApiError("pull files page is not an array")
            if len(response) > 100:
                raise GitHubApiError("pull files page exceeds per_page bound")
            entries.extend(response)
            if len(response) < 100:
                break
        if len(entries) != expected_count:
            raise GitHubApiError("paginated pull files do not match changed_files")
        return entries

    def get_collaborator_permission(self, repository: str, login: str) -> object:
        safe_login = _safe_login(login)
        if safe_login is None:
            raise GitHubApiError("collaborator login is malformed")
        return self._request_json(
            "GET",
            f"{self._repo_path(repository)}/collaborators/"
            f"{urllib.parse.quote(safe_login, safe='')}/permission",
            expected_status=200,
        )

    def create_check(self, repository: str, payload: Mapping[str, object]) -> object:
        return self._request_json(
            "POST",
            f"{self._repo_path(repository)}/check-runs",
            payload=payload,
            expected_status=201,
        )


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AuthorityContractError("cannot read workflow event JSON") from exc


def _details_url() -> str:
    server = os.environ.get("GITHUB_SERVER_URL", "")
    repository = _repository(os.environ.get("GITHUB_REPOSITORY", ""))
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    if (
        not server.startswith("https://")
        or repository is None
        or not run_id.isdigit()
    ):
        return ""
    return f"{server.rstrip('/')}/{repository}/actions/runs/{run_id}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--event", type=Path, default=Path(os.environ.get("GITHUB_EVENT_PATH", ""))
    )
    args = parser.parse_args(argv)
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    try:
        payload = _read_json(args.event)
        event = _mapping(payload)
        api = GitHubApi(
            os.environ.get("GITHUB_API_URL", "https://api.github.com"),
            os.environ.get("GITHUB_TOKEN", ""),
        )
        if event is not None and event.get("merge_group") is not None:
            exit_code, decision, _check = run_merge_group(
                payload,
                repository,
                api,
                details_url=_details_url(),
            )
        else:
            exit_code, decision, _check = run_pull_request_target(
                payload,
                repository,
                api,
                details_url=_details_url(),
            )
    except (AuthorityContractError, GitHubApiError):
        print(
            json.dumps(
                {"schema": SCHEMA, "allowed": False, "reason": "controller_error"},
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(decision, ensure_ascii=True, separators=(",", ":")))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
