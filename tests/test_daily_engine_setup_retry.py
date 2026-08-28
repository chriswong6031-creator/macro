from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml

from scripts.ci import retry_daily_engine_setup_cancel as retry

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "daily-engine-setup-retry.yml"
REPOSITORY = "mastermindx-market-intelligence/macro"
RUN_ID = 12345
JOB_ID = 98765


def _run(**overrides: object) -> dict:
    row = {
        "id": RUN_ID,
        "name": "daily",
        "path": ".github/workflows/daily.yml",
        "status": "completed",
        "conclusion": "cancelled",
        "event": "workflow_dispatch",
        "run_attempt": 1,
        "head_branch": "main",
        "head_repository": {"full_name": REPOSITORY},
    }
    row.update(overrides)
    return row


def _engine_job(**overrides: object) -> dict:
    row = {
        "id": JOB_ID,
        "name": "engine",
        "status": "completed",
        "conclusion": "cancelled",
        "labels": ["self-hosted", "macstudio"],
        "runner_name": "mac-builder-2",
        "started_at": "2026-08-09T06:36:57Z",
        "completed_at": "2026-08-09T06:37:02Z",
        "steps": [
            {
                "name": "Set up job",
                "status": "completed",
                "conclusion": "cancelled",
                "number": 1,
            }
        ],
    }
    row.update(overrides)
    return row


def _success_job(name: str, *, started_at: str, completed_at: str) -> dict:
    return {
        "id": abs(hash(name)) % 10_000 + 1,
        "name": name,
        "status": "completed",
        "conclusion": "success",
        "started_at": started_at,
        "completed_at": completed_at,
        "steps": [],
    }


def _required_jobs() -> list[dict]:
    return [
        _success_job(
            "collect",
            started_at="2026-08-09T03:43:44Z",
            completed_at="2026-08-09T06:03:03Z",
        ),
        _success_job(
            "government_revenue_projection / refresh",
            started_at="2026-08-09T06:03:06Z",
            completed_at="2026-08-09T06:09:14Z",
        ),
    ]


def _continuation_job() -> dict:
    return _success_job(
        "factor_panel",
        started_at="2026-08-09T06:36:59Z",
        completed_at="2026-08-09T06:38:48Z",
    )


def _incident_jobs() -> list[dict]:
    return [_engine_job(), *_required_jobs(), _continuation_job()]


def _decide(run: dict, jobs: list[dict]) -> retry.RetryDecision:
    return retry.decide_retry(run, jobs, REPOSITORY, RUN_ID, "main")


def test_exact_setup_only_engine_cancel_is_eligible() -> None:
    decision = _decide(_run(), _incident_jobs())
    assert decision.eligible is True
    assert decision.job_id == JOB_ID


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ({"steps": _engine_job()["steps"] + [{"name": "Run actions/checkout@v4"}]}, "progressed"),
        ({"completed_at": "2026-08-09T06:40:00Z"}, "progressed"),
        ({"labels": ["ubuntu-latest"]}, "progressed"),
        ({"conclusion": "failure"}, "no cancelled"),
    ],
)
def test_non_setup_engine_failures_are_not_retried(mutation: dict, reason: str) -> None:
    decision = _decide(_run(), [_engine_job(**mutation)])
    assert decision.eligible is False
    assert reason in decision.reason


def test_mass_or_operator_cancellation_is_not_retried() -> None:
    jobs = [
        _engine_job(),
        {"id": 2, "name": "publish", "status": "completed", "conclusion": "cancelled"},
    ]
    decision = _decide(_run(), jobs)
    assert decision.eligible is False
    assert "multiple cancelled jobs" in decision.reason


@pytest.mark.parametrize(
    "overrides",
    [
        {"event": "pull_request"},
        {"head_branch": "feature"},
        {"head_repository": {"full_name": "attacker/fork"}},
        {"path": ".github/workflows/other.yml"},
        {"status": "in_progress"},
    ],
)
def test_untrusted_or_nonterminal_runs_fail_closed(overrides: dict) -> None:
    with pytest.raises(retry.RetryContractError):
        _decide(_run(**overrides), [_engine_job()])


def test_attempt_two_is_a_permanent_noop() -> None:
    decision = _decide(_run(run_attempt=2), _incident_jobs())
    assert decision.eligible is False
    assert "attempt 1" in decision.reason


def test_required_upstream_failure_is_not_retried() -> None:
    jobs = [
        _engine_job(),
        _success_job(
            "collect",
            started_at="2026-08-09T03:43:44Z",
            completed_at="2026-08-09T06:03:03Z",
        ),
        {
            **_success_job(
                "government_revenue_projection / refresh",
                started_at="2026-08-09T06:03:06Z",
                completed_at="2026-08-09T06:09:14Z",
            ),
            "conclusion": "failure",
        },
    ]
    decision = _decide(_run(), jobs)
    assert decision.eligible is False
    assert "required upstream job" in decision.reason


def test_run_must_have_continued_after_engine_cancellation() -> None:
    jobs = [
        _engine_job(),
        _success_job(
            "collect",
            started_at="2026-08-09T03:43:44Z",
            completed_at="2026-08-09T06:36:00Z",
        ),
        _success_job(
            "government_revenue_projection / refresh",
            started_at="2026-08-09T06:03:06Z",
            completed_at="2026-08-09T06:36:30Z",
        ),
    ]
    decision = _decide(_run(), jobs)
    assert decision.eligible is False
    assert "continued after engine cancellation" in decision.reason


def test_known_dependent_failure_does_not_block_setup_race_recovery() -> None:
    jobs = [
        _engine_job(),
        *_required_jobs(),
        _continuation_job(),
        {
            "id": 333,
            "name": "publish",
            "status": "completed",
            "conclusion": "failure",
            "completed_at": "2026-08-09T08:00:00Z",
        },
    ]
    assert _decide(_run(), jobs).eligible is True


def test_workflow_run_envelope_is_bound_to_repository_and_default_branch() -> None:
    payload = {
        "action": "completed",
        "repository": {"full_name": REPOSITORY, "default_branch": "main"},
        "workflow_run": {"id": RUN_ID},
    }
    assert retry.event_context(payload, REPOSITORY) == retry.EventContext(RUN_ID, "main")

    bad = copy.deepcopy(payload)
    bad["repository"]["full_name"] = "attacker/fork"
    with pytest.raises(retry.RetryContractError):
        retry.event_context(bad, REPOSITORY)


def test_controller_posts_only_the_specific_engine_job_rerun(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    event_path = tmp_path / "event.json"
    event_path.write_text(
        json.dumps(
            {
                "action": "completed",
                "repository": {"full_name": REPOSITORY, "default_branch": "main"},
                "workflow_run": {"id": RUN_ID},
            }
        ),
        encoding="utf-8",
    )
    calls: list[tuple[str, str, object]] = []
    rerun_started = False

    class FakeApi:
        def __init__(self, repository: str, token: str) -> None:
            assert repository == REPOSITORY
            assert token == "token"

        def request(self, path: str, *, method: str = "GET", body=None):
            nonlocal rerun_started
            calls.append((method, path, body))
            if path == f"/actions/runs/{RUN_ID}":
                return 200, _run(run_attempt=2 if rerun_started else 1)
            if path == f"/actions/runs/{RUN_ID}/attempts/1/jobs?per_page=100&page=1":
                jobs = _incident_jobs()
                return 200, {"total_count": len(jobs), "jobs": jobs}
            if path == f"/actions/jobs/{JOB_ID}/rerun" and method == "POST":
                rerun_started = True
                return 201, None
            raise AssertionError((method, path, body))

    monkeypatch.setattr(retry, "GitHubApi", FakeApi)
    monkeypatch.setenv("GITHUB_REPOSITORY", REPOSITORY)
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
    monkeypatch.setenv("GITHUB_TOKEN", "token")

    assert retry.main([]) == 0
    writes = [call for call in calls if call[0] == "POST"]
    assert writes == [
        ("POST", f"/actions/jobs/{JOB_ID}/rerun", {"enable_debug_logging": False})
    ]


def test_live_attempt_advanced_before_post_is_a_noop(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    event_path = tmp_path / "event.json"
    event_path.write_text(
        json.dumps(
            {
                "action": "completed",
                "repository": {"full_name": REPOSITORY, "default_branch": "main"},
                "workflow_run": {"id": RUN_ID},
            }
        ),
        encoding="utf-8",
    )
    run_reads = 0
    writes: list[str] = []

    class FakeApi:
        def __init__(self, repository: str, token: str) -> None:
            pass

        def request(self, path: str, *, method: str = "GET", body=None):
            nonlocal run_reads
            if path == f"/actions/runs/{RUN_ID}":
                run_reads += 1
                return 200, _run(run_attempt=1 if run_reads == 1 else 2)
            if path == f"/actions/runs/{RUN_ID}/attempts/1/jobs?per_page=100&page=1":
                jobs = _incident_jobs()
                return 200, {"total_count": len(jobs), "jobs": jobs}
            if method == "POST":
                writes.append(path)
            raise AssertionError((method, path, body))

    monkeypatch.setattr(retry, "GitHubApi", FakeApi)
    monkeypatch.setenv("GITHUB_REPOSITORY", REPOSITORY)
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
    monkeypatch.setenv("GITHUB_TOKEN", "token")

    assert retry.main([]) == 0
    assert writes == []


def test_duplicate_delivery_sees_running_attempt_two_and_noops_before_jobs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    event_path = tmp_path / "event.json"
    event_path.write_text(
        json.dumps(
            {
                "action": "completed",
                "repository": {"full_name": REPOSITORY, "default_branch": "main"},
                "workflow_run": {"id": RUN_ID},
            }
        ),
        encoding="utf-8",
    )
    calls: list[tuple[str, str]] = []

    class FakeApi:
        def __init__(self, repository: str, token: str) -> None:
            pass

        def request(self, path: str, *, method: str = "GET", body=None):
            calls.append((method, path))
            if path == f"/actions/runs/{RUN_ID}":
                return 200, _run(run_attempt=2, status="in_progress", conclusion=None)
            raise AssertionError((method, path, body))

    monkeypatch.setattr(retry, "GitHubApi", FakeApi)
    monkeypatch.setenv("GITHUB_REPOSITORY", REPOSITORY)
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
    monkeypatch.setenv("GITHUB_TOKEN", "token")

    assert retry.main([]) == 0
    assert calls == [("GET", f"/actions/runs/{RUN_ID}")]


def test_recovery_workflow_is_narrow_and_least_privilege() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    doc = yaml.safe_load(source)
    job = doc["jobs"]["retry-setup-cancelled-engine"]
    checkout = job["steps"][0]

    assert "workflow_run:" in source
    assert "workflows: [daily]" in source
    assert "types: [completed]" in source
    assert "branches: [main]" in source
    assert "workflow_dispatch:" not in source
    assert doc["permissions"] == {}
    assert job["permissions"] == {"actions": "write", "contents": "read"}
    assert job["timeout-minutes"] == 10
    assert "head_branch" in job["if"]
    assert "head_repository.full_name" in job["if"]
    assert checkout["with"]["persist-credentials"] is False
    assert "github.event.workflow_run.id" in doc["concurrency"]["group"]
    assert doc["concurrency"]["cancel-in-progress"] is False
    assert "retry_daily_engine_setup_cancel.py" in job["steps"][1]["run"]

    controller = (
        ROOT / "scripts" / "ci" / "retry_daily_engine_setup_cancel.py"
    ).read_text(encoding="utf-8")
    assert 'f"/actions/jobs/{decision.job_id}/rerun"' in controller
    assert "/actions/runs/{run_id}/rerun" not in controller
    assert "rerun-failed-jobs" not in controller
    assert "gh workflow run" not in source + controller


DAILY_WORKFLOW = ROOT / ".github" / "workflows" / "daily.yml"

# Production run names observed on the workflow_run envelopes this controller
# consumes.  ``run-name`` landed in daily.yml on 2026-08-15 (#5723) and the
# ``/actions/runs/{id}`` API reports the RENDERED run name in ``name``, which is
# why an identity assertion on that field failed 28 consecutive nightlies.
PRODUCTION_RUN_NAMES = (
    "daily 30 22 * * *",
    "daily 30 23 * * *",
    "daily workflow_dispatch",
)


@pytest.mark.parametrize("run_name", PRODUCTION_RUN_NAMES)
def test_templated_run_name_is_not_an_identity_signal(run_name: str) -> None:
    """``run.name`` is author-controlled display text, never workflow identity.

    Regression for the 2026-08-15 outage: daily.yml gained
    ``run-name: daily ${{ github.event.schedule || github.event_name }}``, the
    runs API began reporting that rendered string in ``name``, and the
    controller rejected every real nightly as "run is not the daily workflow".
    """
    decision = _decide(_run(name=run_name), _incident_jobs())
    assert decision.eligible is True
    assert decision.job_id == JOB_ID


def test_workflow_path_remains_the_authoritative_identity() -> None:
    """Dropping the display-name assertion must not weaken identity."""
    with pytest.raises(retry.RetryContractError, match="authoritative daily workflow"):
        _decide(
            _run(name="daily", path=".github/workflows/impostor.yml"),
            _incident_jobs(),
        )


def test_controller_does_not_bind_to_daily_run_name() -> None:
    """Contract test across the two files the 2026-08-15 break spanned.

    daily.yml may template ``run-name`` freely; the controller must key identity
    off ``path`` alone so a future run-name edit cannot re-break this lane.
    """
    daily = yaml.safe_load(DAILY_WORKFLOW.read_text(encoding="utf-8"))
    assert daily["name"] == "daily"

    run_name = daily.get("run-name")
    if run_name is not None:
        # A templated run-name renders to something other than the workflow
        # name, so it can never be compared against one.
        assert "${{" in run_name

    controller = (
        ROOT / "scripts" / "ci" / "retry_daily_engine_setup_cancel.py"
    ).read_text(encoding="utf-8")
    assert 'run.get("name")' not in controller
    assert 'EXPECTED_WORKFLOW_PATH' in controller


def test_upstream_cancellation_before_engine_exists_is_a_disclosed_noop() -> None:
    """A daily cancelled during collect never creates the engine job.

    Observed in production on daily run 32194718597 (2026-08-18): two job rows,
    ``collect`` cancelled and no ``engine`` row at all.  Nothing is ambiguous
    and nothing can be retried, so this is a no-op -- not a contract violation
    that reds the recovery lane.  Masked until 2026-08-26 because the run-name
    identity assertion refused every envelope first.
    """
    jobs = [
        {
            "id": 1,
            "name": "collect",
            "status": "completed",
            "conclusion": "cancelled",
            "steps": [],
        }
    ]
    decision = _decide(_run(name="daily 30 22 * * *"), jobs)
    assert decision.eligible is False
    assert "never created an engine job" in decision.reason


def test_duplicate_engine_jobs_still_fail_closed() -> None:
    """Two engine rows are genuinely ambiguous and must not be retried."""
    with pytest.raises(retry.RetryContractError, match="exactly one engine job"):
        _decide(
            _run(),
            [
                _engine_job(),
                _engine_job(id=JOB_ID + 1, conclusion="success"),
                *_required_jobs(),
            ],
        )
