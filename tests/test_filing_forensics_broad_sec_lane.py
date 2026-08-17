"""FF-1 broad SEC lane sits off the render path and cannot silently enter recovery."""
from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
DAILY = ROOT / ".github/workflows/daily.yml"
WAVE2 = ROOT / ".github/workflows/filing-forensics-sec.yml"
LANE = ROOT / ".github/workflows/filing-forensics-broad-sec.yml"
MODULE = "scripts.run_fundamental_forensics_broad_sec"
R2_RESEARCH_KEYS = {
    "R2_RESEARCH_ENDPOINT",
    "R2_RESEARCH_ACCESS_KEY_ID",
    "R2_RESEARCH_SECRET_ACCESS_KEY",
    "R2_RESEARCH_BUCKET",
}


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _steps(workflow: dict, job: str) -> list[dict]:
    return list(workflow["jobs"][job]["steps"])


def test_broad_sec_lane_is_scheduled_off_the_render_path_and_never_cancelled() -> None:
    lane = _load(LANE)
    triggers = lane[True] if True in lane else lane["on"]
    assert triggers["schedule"] == [{"cron": "15 3 * * *"}]
    assert "workflow_dispatch" in triggers
    assert lane["concurrency"]["group"] == "filing-forensics-sec"
    assert lane["concurrency"]["cancel-in-progress"] is False
    wave2 = _load(WAVE2)
    assert wave2["concurrency"]["group"] == "filing-forensics-sec"
    job = lane["jobs"]["poll_broad_sec"]
    assert "macstudio-light" in job["runs-on"]
    assert job["timeout-minutes"] <= 90


def test_daily_render_does_not_run_the_broad_sec_poll() -> None:
    daily = _load(DAILY)
    offenders = [
        step.get("name", "(unnamed)")
        for step in _steps(daily, "engine")
        if MODULE in str(step.get("run", ""))
    ]
    assert offenders == []
    assert MODULE not in DAILY.read_text(encoding="utf-8")


def test_scheduled_path_cannot_enter_recovery() -> None:
    body = LANE.read_text(encoding="utf-8")
    assert "MODE=\"incremental\"" in body
    assert "github.event_name" in body
    assert "workflow_dispatch" in body
    poll_step = next(
        step
        for step in _steps(_load(LANE), "poll_broad_sec")
        if MODULE.replace(".", " ") in str(step.get("run", "")).replace(".", " ")
        or MODULE in str(step.get("run", ""))
    )
    run = poll_step["run"]
    assert "continue-on-error" not in poll_step
    assert set(poll_step["env"]) == R2_RESEARCH_KEYS
    incremental_arm = [
        line
        for line in run.splitlines()
        if "--mode incremental" in line and not line.strip().startswith("#")
    ]
    recovery_arm = [
        line
        for line in run.splitlines()
        if "--mode recovery" in line and not line.strip().startswith("#")
    ]
    assert incremental_arm
    assert recovery_arm
    recovery_index = run.index("--mode recovery")
    dispatch_index = run.index('github.event_name')
    assert dispatch_index < recovery_index
    assert "backlog" not in run.lower() or "cannot enter recovery merely because a backlog exists" in run


def test_lane_failure_is_a_hard_gate() -> None:
    for step in _steps(_load(LANE), "poll_broad_sec"):
        assert "continue-on-error" not in step
    payload = _load(LANE)
    assert "continue-on-error" not in payload
    assert "continue-on-error" not in payload["jobs"]["poll_broad_sec"]
