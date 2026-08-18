"""Static safety contracts for the universal institutional 13F workflows."""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
ROLLING = ROOT / ".github/workflows/smart-money-13f-census.yml"
BULK = ROOT / ".github/workflows/smart-money-13f-bulk-reconcile.yml"

# The fast lane's cadence is a runner-budget contract against the shared
# two-host `macstudio` pool, not a freshness preference.  It is hourly (never
# denser) and it stops before the authoritative nightly's 22:30Z firing.  See
# the block comment in the workflow and
# research/PROPHET_OUTAGE_2026_08_17_POSTMORTEM.md chipped follow-up 2.
FAST_LANE_CRON = "10 12-20 * * 1-5"
# Latest hour the fast lane may fire, and the cap it runs under.  The product
# must leave the pool clear before daily.yml starts at 22:30Z.
FAST_LANE_LAST_HOUR_UTC = 20
FAST_LANE_TIMEOUT_MINUTES = 60
NIGHTLY_FIRST_CRON_MINUTE_UTC = 22 * 60 + 30


def _load(path: Path) -> dict:
    return yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _step(job: dict, name: str) -> dict:
    return next(step for step in job["steps"] if step.get("name") == name)


def _assert_isolated_locked_runtime(job: dict) -> None:
    step = _step(job, "Python 3.12 (isolated locked runtime)")
    command = step["run"]
    assert 'VENV="$RUNNER_TEMP/institutional-13f-venv"' in command
    assert '/opt/homebrew/bin/python3.12 -m venv "$VENV"' in command
    assert 'echo "$VENV/bin" >> "$GITHUB_PATH"' in command
    assert command.count('"$VENV/bin/pip" install') == 1
    assert "-r requirements/institutional-13f-macos-arm64-py312.lock" in command
    assert "requirements.txt" not in command
    assert "$HOME/.cache" not in command


def _assert_private_research_environment(step: dict) -> None:
    assert {
        key: step["env"].get(key)
        for key in (
            "INSTITUTIONAL_13F_RESEARCH_R2_ENDPOINT",
            "INSTITUTIONAL_13F_RESEARCH_R2_ACCESS_KEY_ID",
            "INSTITUTIONAL_13F_RESEARCH_R2_SECRET_ACCESS_KEY",
            "INSTITUTIONAL_13F_RESEARCH_R2_BUCKET",
        )
    } == {
        "INSTITUTIONAL_13F_RESEARCH_R2_ENDPOINT": (
            "${{ secrets.R2_RESEARCH_ENDPOINT }}"
        ),
        "INSTITUTIONAL_13F_RESEARCH_R2_ACCESS_KEY_ID": (
            "${{ secrets.R2_RESEARCH_ACCESS_KEY_ID }}"
        ),
        "INSTITUTIONAL_13F_RESEARCH_R2_SECRET_ACCESS_KEY": (
            "${{ secrets.R2_RESEARCH_SECRET_ACCESS_KEY }}"
        ),
        "INSTITUTIONAL_13F_RESEARCH_R2_BUCKET": ("${{ secrets.R2_RESEARCH_BUCKET }}"),
    }


def test_rolling_workflow_is_read_only_bounded_and_non_cancelling() -> None:
    text = ROLLING.read_text(encoding="utf-8")
    workflow = _load(ROLLING)

    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"]["cancel-in-progress"] == "false"
    schedules = {row["cron"] for row in workflow["on"]["schedule"]}
    assert schedules == {
        FAST_LANE_CRON,
        "17 6 * * 2-6",
        "47 7 * * 0",
    }
    assert set(
        workflow["on"]["workflow_dispatch"]["inputs"]["discovery_lane"]["options"]
    ) == {"atom", "daily", "full"}

    job = workflow["jobs"]["discover_retain_publish"]
    assert job["if"] == "github.ref == 'refs/heads/main'"
    assert job["timeout-minutes"] == (
        f"${{{{ github.event.schedule == '{FAST_LANE_CRON}'"
        f" && {FAST_LANE_TIMEOUT_MINUTES} || 180 }}}}"
    )
    _assert_isolated_locked_runtime(job)
    run_step = _step(
        job, "Discover, retain raw evidence, and publish catalog generations"
    )
    assert run_step["env"]["INSTITUTIONAL_13F_R2_ENDPOINT"] == (
        "${{ secrets.R2_ENDPOINT }}"
    )
    assert run_step["env"]["INSTITUTIONAL_13F_R2_BUCKET"] == (
        "${{ secrets.R2_BUCKET }}"
    )
    assert "--max-accessions 750" in run_step["run"]
    assert "--requests-per-second 8" in run_step["run"]
    expected_receipt = "${{ runner.temp }}/institutional-13f-rolling-receipt.json"
    assert run_step["env"]["RECEIPT_PATH"] == expected_receipt
    assert (
        _step(job, "Assert complete, bounded run receipt")["env"]["RECEIPT_PATH"]
        == expected_receipt
    )
    upload = _step(job, "Upload the redacted operator receipt")
    assert upload["with"]["path"] == expected_receipt
    assert upload["with"]["retention-days"] == "30"
    assert "git push" not in text
    assert not re.search(r"\bgit\s+(?:add|commit|push)\b", text)
    assert "contents: write" not in text
    assert "data/institutional_13f" not in text


def test_fast_lane_yields_the_shared_runner_before_the_nightly() -> None:
    """The fast lane must stay hourly and finish before daily.yml fires.

    This pins the *budget*, not the literal strings: `macstudio` is two
    physical hosts shared with the authoritative nightly, and a denser or
    later-running fast lane is what starved it on 2026-08-17.  A future
    session that widens the window has to change this reasoning on purpose.
    """

    workflow = _load(ROLLING)
    schedules = [row["cron"] for row in workflow["on"]["schedule"]]
    assert FAST_LANE_CRON in schedules

    minutes, hours, dom, month, dow = FAST_LANE_CRON.split()

    # Hourly at a single minute — never a comma/step list, which is what
    # produced the 24-firings-a-day supersede thrash (20 of 86 runs cancelled
    # while pending, never executed).
    assert minutes.isdigit(), f"fast lane must fire once per hour, got {minutes!r}"
    minute = int(minutes)

    # A contiguous hour range ending no later than FAST_LANE_LAST_HOUR_UTC.
    assert re.fullmatch(r"\d+-\d+", hours), f"unexpected hour spec {hours!r}"
    first_hour, last_hour = (int(part) for part in hours.split("-"))
    assert first_hour < last_hour
    assert last_hour <= FAST_LANE_LAST_HOUR_UTC

    # Weekdays only: EDGAR does not accept filings at the weekend, and the
    # Sunday full-index reconcile is a separate cron.
    assert (dom, month, dow) == ("*", "*", "1-5")

    # The load-bearing arithmetic: the last firing, run to its cap, must be
    # done before the nightly's first cron minute.
    latest_finish = last_hour * 60 + minute + FAST_LANE_TIMEOUT_MINUTES
    assert latest_finish < NIGHTLY_FIRST_CRON_MINUTE_UTC, (
        f"fast lane can still be running at {latest_finish // 60:02d}:"
        f"{latest_finish % 60:02d}Z, at or past daily.yml's 22:30Z firing"
    )

    # Minutes already claimed by other `macstudio` lanes in this window:
    # closing-bell :05, smart-money-filings :17, earlyclose :20,
    # close-pass :25, daily :30, metabolism-cycle :35, heartbeat :45.
    assert minute not in {5, 17, 20, 25, 30, 35, 45}


def test_bulk_workflow_publishes_only_the_bounded_projection() -> None:
    workflow = _load(BULK)

    assert workflow["concurrency"]["cancel-in-progress"] == "false"
    job = workflow["jobs"]["reconcile_publish"]
    assert job["if"] == "github.ref == 'refs/heads/main'"
    _assert_isolated_locked_runtime(job)

    build_step = _step(
        job, "Retain SEC ZIP revisions and build completed-quarter census"
    )
    _assert_private_research_environment(build_step)
    assert "--publish-bulk-evidence" in build_step["run"]
    assert "--publish-research-bench" in build_step["run"]
    research_bench_path = (
        "${{ runner.temp }}/institutional-13f-research-bench.json"
    )
    assert build_step["env"]["RESEARCH_BENCH_PATH"] == research_bench_path
    assert (
        '--research-bench-output "$RESEARCH_BENCH_PATH"' in build_step["run"]
    )
    assert "data/institutional_13f/research_bench" not in build_step["run"]
    _assert_private_research_environment(
        _step(job, "Assert private research-bench durability")
    )

    cleanup_step = _step(job, "Remove private research-bench working copy")
    assert cleanup_step["if"] == "always()"
    assert cleanup_step["env"]["RESEARCH_BENCH_PATH"] == research_bench_path
    assert cleanup_step["run"].splitlines() == [
        "set -euo pipefail",
        'expected="$RUNNER_TEMP/institutional-13f-research-bench.json"',
        'test "$RESEARCH_BENCH_PATH" = "$expected"',
        'rm -f -- "$expected"',
    ]

    render_step = _step(job, "Re-render only the Smart Money census surface")
    assert render_step["run"] == (
        "python -m scripts.build_smart_money --census-render-only"
    )

    commit_step = _step(job, "Commit and publish reconciled census")
    command = commit_step["run"]
    staged_match = re.search(
        r"git add --\s+(?P<paths>.*?)\n\s*if git diff --cached",
        command,
        flags=re.DOTALL,
    )
    assert staged_match is not None
    staged = set(shlex.split(staged_match.group("paths").replace("\\\n", " ")))
    assert staged == {
        "data/institutional_13f/public/census_latest.json",
        "data/institutional_13f/receipts/census_latest.json",
        "site/factordata/institutional_census_summary.json",
        "site/factordata/smartmoney_desk.json",
        "site/smart_money.html",
        "site/assets/css",
    }
    assert "data/institutional_13f/bulk_cache" not in command
    assert "data/institutional_13f/research_bench" not in command
    assert "git add -A" not in command


def test_assert_step_accepts_bounded_backlog_only_on_master_index_lanes() -> None:
    """The daily/full master-index backstops legitimately saturate
    --max-accessions and must accept a bounded_backlog receipt; the atom lane
    must never fall behind, so it stays pinned to ok/no_changes with a
    zero backlog."""
    job = _load(ROLLING)["jobs"]["discover_retain_publish"]
    assert_step_run = _step(job, "Assert complete, bounded run receipt")["run"]

    assert 'expected_lane = os.environ["EXPECTED_LANE"]' in assert_step_run
    assert 'if expected_lane == "atom":' in assert_step_run
    atom_branch, _, backstop_branch = assert_step_run.partition('else:')
    assert 'assert receipt["status"] in {"ok", "no_changes"}' in atom_branch
    assert 'assert receipt["discovery"]["backlog_accessions"] == 0' in atom_branch
    assert (
        'assert receipt["status"] in {"ok", "no_changes", "bounded_backlog"}'
        in backstop_branch
    )
    assert 'assert receipt["counts"]["failures"] == 0' in assert_step_run
    assert 'assert receipt["discovery"]["atom"]["complete"] is True' in assert_step_run
