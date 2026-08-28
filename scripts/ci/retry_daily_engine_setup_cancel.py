"""Retry one daily ``engine`` job lost before checkout.

This is deliberately much narrower than a generic workflow retry.  It admits
only a trusted first-attempt ``daily.yml`` run whose sole cancelled job is the
``engine`` job and whose sole executed step is GitHub's cancelled ``Set up
job`` step.  Timeouts, operator-cancelled runs, and deterministic build
failures remain untouched.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

API_VERSION = "2022-11-28"
# ``path`` is the authoritative identity of a workflow run and is assigned by
# GitHub.  ``run.name`` is NOT identity: the runs API reports the RENDERED
# ``run-name:``, which daily.yml templates per firing (``daily 30 23 * * *``).
# Comparing that display string against the workflow name rejected 28
# consecutive nightlies after #5723 added run-name on 2026-08-15.  Never
# reintroduce an identity assertion on author-controlled display text.
EXPECTED_WORKFLOW_PATH = ".github/workflows/daily.yml"
TARGET_JOB_NAME = "engine"
TRUSTED_EVENTS = frozenset({"schedule", "workflow_dispatch"})
MAX_SETUP_CANCEL_SECONDS = 120.0


class RetryContractError(RuntimeError):
    """The event or GitHub response violated the recovery contract."""


@dataclass(frozen=True)
class RetryDecision:
    job_id: int | None
    reason: str

    @property
    def eligible(self) -> bool:
        return self.job_id is not None


@dataclass(frozen=True)
class EventContext:
    run_id: int
    default_branch: str


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RetryContractError(f"{label} must be an object")
    return value


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise RetryContractError(f"{label} must be a positive integer")
    return value


def _timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise RetryContractError(f"{label} must be an ISO timestamp")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RetryContractError(f"{label} must be an ISO timestamp") from exc


def event_context(payload: Mapping[str, Any], repository: str) -> EventContext:
    """Validate the trusted workflow_run envelope."""
    if payload.get("action") != "completed":
        raise RetryContractError("workflow_run action must be completed")

    event_repo = _object(payload.get("repository"), "repository")
    if event_repo.get("full_name") != repository:
        raise RetryContractError("workflow_run repository does not match GITHUB_REPOSITORY")
    default_branch = event_repo.get("default_branch")
    if not isinstance(default_branch, str) or not default_branch:
        raise RetryContractError("workflow_run repository is missing its default branch")

    workflow_run = _object(payload.get("workflow_run"), "workflow_run")
    return EventContext(
        run_id=_positive_int(workflow_run.get("id"), "workflow_run.id"),
        default_branch=default_branch,
    )


def _validate_run(
    run: Mapping[str, Any],
    repository: str,
    run_id: int,
    default_branch: str,
    *,
    require_terminal: bool = True,
) -> None:
    if _positive_int(run.get("id"), "run.id") != run_id:
        raise RetryContractError("event run id does not match the API run")
    if run.get("path") != EXPECTED_WORKFLOW_PATH:
        raise RetryContractError("run path is not the authoritative daily workflow")
    if require_terminal and run.get("status") != "completed":
        raise RetryContractError("daily run must be terminal before a job rerun")
    if run.get("event") not in TRUSTED_EVENTS:
        raise RetryContractError("daily run event is not trusted for automatic retry")
    _positive_int(run.get("run_attempt"), "run.run_attempt")

    head_repo = _object(run.get("head_repository"), "run.head_repository")
    if head_repo.get("full_name") != repository:
        raise RetryContractError("daily run did not originate in this repository")
    if run.get("head_branch") != default_branch:
        raise RetryContractError("daily run did not originate from the default branch")


def _setup_only_cancel(job: Mapping[str, Any]) -> bool:
    if job.get("status") != "completed" or job.get("conclusion") != "cancelled":
        return False
    labels = job.get("labels")
    if not isinstance(labels, list) or not {"self-hosted", "macstudio"}.issubset(
        {label for label in labels if isinstance(label, str)}
    ):
        return False
    steps = job.get("steps")
    if not isinstance(steps, list) or len(steps) != 1:
        return False
    step = _object(steps[0], "engine setup step")
    if (
        step.get("name") != "Set up job"
        or step.get("status") != "completed"
        or step.get("conclusion") != "cancelled"
        or step.get("number") != 1
    ):
        return False

    started = _timestamp(job.get("started_at"), "engine.started_at")
    completed = _timestamp(job.get("completed_at"), "engine.completed_at")
    elapsed = (completed - started).total_seconds()
    return 0 <= elapsed <= MAX_SETUP_CANCEL_SECONDS


def decide_retry(
    run: Mapping[str, Any],
    jobs: Sequence[Mapping[str, Any]],
    repository: str,
    run_id: int,
    default_branch: str,
) -> RetryDecision:
    """Return the one admissible retry target, or a disclosed no-op decision."""
    _validate_run(run, repository, run_id, default_branch)
    if run.get("run_attempt") != 1:
        return RetryDecision(None, "automatic retry is permanently limited to attempt 1")

    cancelled = [job for job in jobs if job.get("conclusion") == "cancelled"]
    if not cancelled:
        return RetryDecision(None, "daily run has no cancelled jobs")
    if len(cancelled) != 1:
        return RetryDecision(
            None,
            "daily run has multiple cancelled jobs; treating it as a wider/operator cancellation",
        )

    engine_jobs = [job for job in jobs if job.get("name") == TARGET_JOB_NAME]
    if not engine_jobs:
        # A daily cancelled during an upstream job (observed: run 32194718597,
        # collect cancelled, two job rows total) never creates the engine job at
        # all.  Nothing is ambiguous and nothing can be retried, so disclose a
        # no-op instead of reddening the recovery lane on an ordinary shape.
        return RetryDecision(None, "daily attempt never created an engine job")
    if len(engine_jobs) != 1:
        raise RetryContractError("daily attempt must contain exactly one engine job")
    engine = engine_jobs[0]
    if cancelled[0] is not engine:
        return RetryDecision(None, "the sole cancelled job is not engine")
    if not _setup_only_cancel(engine):
        return RetryDecision(
            None,
            "engine cancellation progressed beyond the bounded setup-only contract",
        )

    for required_name in ("collect", "government_revenue_projection / refresh"):
        required = [job for job in jobs if job.get("name") == required_name]
        if len(required) != 1:
            raise RetryContractError(
                f"daily attempt must contain exactly one {required_name} job"
            )
        if required[0].get("conclusion") != "success":
            return RetryDecision(
                None, f"required upstream job {required_name} did not succeed"
            )

    engine_completed = _timestamp(engine.get("completed_at"), "engine.completed_at")
    continued_after_cancel = False
    for sibling in jobs:
        if sibling is engine or sibling.get("conclusion") != "success":
            continue
        completed_at = sibling.get("completed_at")
        if not isinstance(completed_at, str) or not completed_at:
            continue
        try:
            if _timestamp(completed_at, "sibling.completed_at") > engine_completed:
                continued_after_cancel = True
                break
        except RetryContractError:
            continue
    if not continued_after_cancel:
        return RetryDecision(
            None,
            "no successful sibling proves the daily continued after engine cancellation",
        )
    return RetryDecision(
        _positive_int(engine.get("id"), "engine.id"),
        "engine was cancelled during its sole Set up job step",
    )


class GitHubApi:
    def __init__(self, repository: str, token: str) -> None:
        if not token:
            raise RetryContractError("GITHUB_TOKEN is required")
        self.repository = repository
        self.base = f"https://api.github.com/repos/{repository}"
        self.headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "macro-daily-engine-setup-retry",
        }

    def request(
        self, path: str, *, method: str = "GET", body: Mapping[str, Any] | None = None
    ) -> tuple[int, Any]:
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base}{path}", data=data, headers=self.headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read()
                parsed = json.loads(raw) if raw else None
                return response.status, parsed
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RetryContractError(
                f"GitHub API {method} {path} failed: HTTP {exc.code}: {detail[:500]}"
            ) from exc


def _jobs(api: GitHubApi, run_id: int, attempt: int) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    total_count: int | None = None
    for page in range(1, 11):
        status, payload = api.request(
            f"/actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100&page={page}"
        )
        if status != 200:
            raise RetryContractError(f"jobs API returned unexpected HTTP {status}")
        obj = _object(payload, "jobs response")
        page_total = obj.get("total_count")
        if isinstance(page_total, bool) or not isinstance(page_total, int) or page_total < 0:
            raise RetryContractError("jobs response has an invalid total_count")
        if total_count is None:
            total_count = page_total
        elif total_count != page_total:
            raise RetryContractError("jobs total_count changed during pagination")
        page_rows = obj.get("jobs")
        if not isinstance(page_rows, list) or not all(
            isinstance(job, Mapping) for job in page_rows
        ):
            raise RetryContractError("jobs response must contain an object list")
        rows.extend(page_rows)
        if len(rows) >= total_count:
            if len(rows) != total_count:
                raise RetryContractError("jobs pagination exceeded total_count")
            return rows
        if not page_rows:
            raise RetryContractError("jobs pagination ended before total_count")
    raise RetryContractError("jobs response exceeded the bounded 1,000-job census")


def _wait_for_attempt(api: GitHubApi, run_id: int, minimum_attempt: int = 2) -> None:
    for _ in range(12):
        status, payload = api.request(f"/actions/runs/{run_id}")
        if status != 200:
            raise RetryContractError(
                f"rerun acknowledgement API returned unexpected HTTP {status}"
            )
        run = _object(payload, "rerun acknowledgement")
        attempt = _positive_int(run.get("run_attempt"), "run.run_attempt")
        if attempt >= minimum_attempt:
            return
        time.sleep(5)
    raise RetryContractError("GitHub accepted the rerun but attempt 2 was not observable")


def _summary(message: str) -> None:
    print(message)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with Path(summary_path).open("a", encoding="utf-8") as handle:
            handle.write(f"### Daily engine setup retry\n\n{message}\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    repository = os.environ.get("GITHUB_REPOSITORY", "")
    if not repository or repository.count("/") != 1:
        raise RetryContractError("GITHUB_REPOSITORY must be owner/repo")
    event_path = os.environ.get("GITHUB_EVENT_PATH", "")
    if not event_path:
        raise RetryContractError("GITHUB_EVENT_PATH is required")
    payload = _object(json.loads(Path(event_path).read_text(encoding="utf-8")), "event")
    context = event_context(payload, repository)
    run_id = context.run_id

    api = GitHubApi(repository, os.environ.get("GITHUB_TOKEN", ""))
    status, run_payload = api.request(f"/actions/runs/{run_id}")
    if status != 200:
        raise RetryContractError(f"run API returned unexpected HTTP {status}")
    run = _object(run_payload, "run response")
    attempt = _positive_int(run.get("run_attempt"), "run.run_attempt")
    _validate_run(
        run,
        repository,
        run_id,
        context.default_branch,
        require_terminal=False,
    )
    if attempt != 1:
        _summary("No retry: automatic recovery is permanently limited to attempt 1.")
        return 0
    _validate_run(run, repository, run_id, context.default_branch)
    jobs = _jobs(api, run_id, attempt)
    decision = decide_retry(run, jobs, repository, run_id, context.default_branch)
    if not decision.eligible:
        _summary(f"No retry: {decision.reason}.")
        return 0
    if args.dry_run:
        _summary(f"Dry run: would retry engine job {decision.job_id}: {decision.reason}.")
        return 0

    # Re-read immediately before the write so a manual retry cannot race this
    # control plane into a second attempt.
    latest_status, latest_payload = api.request(f"/actions/runs/{run_id}")
    if latest_status != 200:
        raise RetryContractError(
            f"latest run API returned unexpected HTTP {latest_status}"
        )
    latest = _object(latest_payload, "latest run response")
    _validate_run(
        latest,
        repository,
        run_id,
        context.default_branch,
        require_terminal=False,
    )
    if latest.get("run_attempt") != 1:
        _summary("No retry: a manual or automatic attempt 2 already exists.")
        return 0
    _validate_run(latest, repository, run_id, context.default_branch)
    status, _ = api.request(
        f"/actions/jobs/{decision.job_id}/rerun",
        method="POST",
        body={"enable_debug_logging": False},
    )
    if status != 201:
        raise RetryContractError(f"job rerun returned unexpected HTTP {status}")
    _wait_for_attempt(api, run_id)
    _summary(
        f"Retried engine job {decision.job_id} and its dependent jobs for daily run {run_id}."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RetryContractError, json.JSONDecodeError, OSError) as exc:
        print(f"::error title=Daily engine setup retry::{exc}", file=sys.stderr)
        raise SystemExit(1) from exc
