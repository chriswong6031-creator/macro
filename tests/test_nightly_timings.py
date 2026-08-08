"""W2 nightly runtime telemetry (masterplan §0.2 acceptance gate).

Two halves:

1. BEHAVIOR — scripts/nightly_timings.py: a synthetic run at 86% of its cap
   MUST trip the ``::warning`` (at line start — GitHub parses ``::`` only at
   column 0), an 84% run must NOT, bands are computed from the marks, and dark
   telemetry (no start stamp) is loud instead of silently recording nothing.

2. WIRING — .github/workflows/daily.yml: every self-hosted job with a
   ``timeout-minutes`` carries the job-start mark as its FIRST step and the
   ``if: always()`` finish step as its LAST, and the finish step's cap argument
   equals the job's actual ``timeout-minutes``. This is the anti-drift pin:
   raising a cap without updating the finish arg would silently rescale the 85%
   tripwire (the same stale-label class that produced the tech_lab 8-day outage).

Run: .venv/bin/python -m pytest tests/test_nightly_timings.py -q
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from scripts import nightly_timings as nt
from scripts import nightly_timings_report as ntr

ROOT = Path(__file__).resolve().parent.parent
DAILY = ROOT / ".github" / "workflows" / "daily.yml"

START_STEP_NAME = "timings — job start mark (W2)"
FINISH_STEP_NAME = "timings ledger + 85% budget tripwire (W2)"


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("NIGHTLY_TIMINGS_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("GITHUB_JOB", "engine")
    monkeypatch.setenv("GITHUB_RUN_ID", "12345")
    monkeypatch.setenv("RUNNER_NAME", "mac-builder-test")
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    (tmp_path / "state").mkdir()
    return tmp_path


def _write_start(seconds_ago: float, now: float = 1_800_000_000.0) -> float:
    nt.start_path().parent.mkdir(parents=True, exist_ok=True)
    nt.start_path().write_text(str(now - seconds_ago))
    return now


# ---------------------------------------------------------------------------
# behavior
# ---------------------------------------------------------------------------

def test_synthetic_86_percent_run_trips_the_warning(env, capsys):
    """Masterplan §0.2 gate: a synthetic 86% run trips the ::warning."""
    cap = 240.0
    now = _write_start(seconds_ago=0.86 * cap * 60)
    row = nt.cmd_finish(cap, env / "ledger", now=now)
    assert row["pct_of_cap"] == pytest.approx(86.0, abs=0.2)
    out = capsys.readouterr().out
    warn = [l for l in out.splitlines() if l.startswith("::warning")]
    assert len(warn) == 1, f"expected exactly one line-start ::warning, got: {out!r}"
    # column 0 is what GitHub parses — a prefixed line would ship a dead alarm
    assert warn[0].startswith("::warning title=nightly budget 85% tripwire::")
    assert "engine" in warn[0] and "86%" in warn[0]


def test_84_percent_run_does_not_warn(env, capsys):
    cap = 240.0
    now = _write_start(seconds_ago=0.84 * cap * 60)
    row = nt.cmd_finish(cap, env / "ledger", now=now)
    assert row["pct_of_cap"] == pytest.approx(84.0, abs=0.2)
    out = capsys.readouterr().out
    assert not [l for l in out.splitlines() if l.startswith("::warning")]
    assert "nightly-timings: engine elapsed" in out  # the plain trend line still prints


def test_ledger_row_appends_per_job_file(env):
    now = _write_start(seconds_ago=600)
    nt.cmd_finish(200.0, env / "ledger", now=now)
    nt.cmd_finish(200.0, env / "ledger", now=now + 60)
    path = env / "ledger" / "engine.jsonl"
    rows = [json.loads(l) for l in path.read_text().splitlines()]
    assert len(rows) == 2
    assert rows[0]["job"] == "engine"
    assert rows[0]["cap_minutes"] == 200.0
    assert rows[0]["elapsed_minutes"] == pytest.approx(10.0, abs=0.1)
    assert rows[0]["run_id"] == "12345"
    assert rows[0]["runner"] == "mac-builder-test"


def test_bands_computed_from_marks(env):
    now = 1_800_000_000.0
    _write_start(seconds_ago=1000, now=now)
    nt.cmd_mark("engine-core", now=now - 700)
    nt.cmd_mark("builders-parallel", now=now - 250)
    row = nt.cmd_finish(240.0, env / "ledger", now=now)
    assert row["bands"] == [
        {"band": "startup", "seconds": 300},
        {"band": "engine-core", "seconds": 450},
        {"band": "builders-parallel", "seconds": 250},
    ]


def test_dark_telemetry_is_loud_not_silent(env, capsys):
    """No start stamp + no marks = a row with null elapsed AND a ::warning.

    A tripwire that silently records nothing is the failure mode W2 exists to
    end (tech_lab's cap cancelled its own alarm step for 8 straight nights)."""
    row = nt.cmd_finish(240.0, env / "ledger", now=1_800_000_000.0)
    assert row["elapsed_minutes"] is None
    assert row["telemetry"] == "dark"
    out = capsys.readouterr().out
    warn = [l for l in out.splitlines() if l.startswith("::warning")]
    assert len(warn) == 1 and "title=nightly timings dark" in warn[0]
    # the row still lands, so the dark night is visible in the ledger too
    assert (env / "ledger" / "engine.jsonl").exists()


def test_missing_start_falls_back_to_first_mark(env):
    now = 1_800_000_000.0
    nt.cmd_mark("collectors", now=now - 900)
    row = nt.cmd_finish(240.0, env / "ledger", now=now)
    assert row["elapsed_minutes"] == pytest.approx(15.0, abs=0.1)
    assert row["bands"] == [{"band": "collectors", "seconds": 900}]


def test_report_flags_a_breach(env):
    now = _write_start(seconds_ago=0.9 * 100 * 60)
    nt.cmd_finish(100.0, env / "ledger", now=now)
    lines = ntr.report(env / "ledger", nights=14, show_bands=True)
    joined = "\n".join(lines)
    assert "engine" in joined
    assert "TRIPWIRE" in joined


def test_backfill_seeds_only_instrumented_jobs(env, tmp_path):
    payload = {"jobs": [
        {"name": "engine", "run_id": 1, "run_attempt": 1, "runner_name": "mac-builder-1",
         "conclusion": "success",
         "started_at": "2026-08-06T02:00:00Z", "completed_at": "2026-08-06T04:30:00Z"},
        {"name": "publish", "run_id": 1, "run_attempt": 1, "runner_name": "",
         "conclusion": "success",
         "started_at": "2026-08-06T05:00:00Z", "completed_at": "2026-08-06T05:02:00Z"},
    ]}
    jf = tmp_path / "jobs.json"
    jf.write_text(json.dumps(payload))
    n = nt.cmd_backfill(jf, DAILY, tmp_path / "ledger")
    assert n == 1  # publish is not self-hosted/instrumented → skipped
    rows = [json.loads(l) for l in (tmp_path / "ledger" / "engine.jsonl").read_text().splitlines()]
    assert rows[0]["elapsed_minutes"] == pytest.approx(150.0)
    assert rows[0]["source"] == "backfill-gh-api"
    # engine cap history lives in daily.yml's timeout-minutes comment; 300 since 2026-08-08
    assert rows[0]["cap_minutes"] == 300.0


# ---------------------------------------------------------------------------
# wiring — daily.yml
# ---------------------------------------------------------------------------

def _daily_jobs() -> dict:
    return yaml.safe_load(DAILY.read_text(encoding="utf-8"))["jobs"]


def _instrumented() -> dict[str, dict]:
    out = {}
    for key, spec in _daily_jobs().items():
        if not isinstance(spec, dict):
            continue
        runs_on = spec.get("runs-on")
        if isinstance(runs_on, list) and "self-hosted" in runs_on \
           and spec.get("timeout-minutes") is not None:
            out[key] = spec
    return out


def test_every_self_hosted_job_is_instrumented():
    jobs = _instrumented()
    assert jobs, "daily.yml parse found no self-hosted jobs — wiring test is broken"
    missing = []
    for key, spec in jobs.items():
        steps = spec["steps"]
        if steps[0].get("name") != START_STEP_NAME:
            missing.append(f"{key}: first step is {steps[0].get('name')!r}, not the job-start mark")
        if steps[-1].get("name") != FINISH_STEP_NAME:
            missing.append(f"{key}: last step is {steps[-1].get('name')!r}, not the finish/tripwire")
    assert not missing, (
        "W2 telemetry wiring gap — a self-hosted daily.yml job is missing its timings steps "
        "(add the job-start mark as the FIRST step and nightly_timings_finish.sh as the LAST):\n"
        + "\n".join(f"  {m}" for m in missing)
    )


def test_finish_cap_argument_matches_timeout_minutes():
    """The anti-drift pin: cap raises must update the finish arg in the same edit,
    or the 85% tripwire silently rescales against a stale cap."""
    bad = []
    for key, spec in _instrumented().items():
        run = spec["steps"][-1].get("run", "")
        expected = f"bash scripts/ci/nightly_timings_finish.sh {spec['timeout-minutes']}"
        if run.strip() != expected:
            bad.append(f"{key}: timeout-minutes={spec['timeout-minutes']} but finish step runs {run.strip()!r}")
        if spec["steps"][-1].get("if") != "always()":
            bad.append(f"{key}: finish step must be if: always() so a cap-cancel night still records")
    assert not bad, "finish step drifted from the job cap:\n" + "\n".join(f"  {b}" for b in bad)


def test_start_mark_writes_the_path_the_reader_expects():
    """The shell stamp and the Python reader must agree on the state filename."""
    for key, spec in _instrumented().items():
        run = spec["steps"][0].get("run", "")
        assert 'nightly-timings-${GITHUB_RUN_ID}-${GITHUB_JOB}-start' in run, (
            f"{key}: job-start mark writes an unexpected path: {run!r} — "
            "scripts/nightly_timings.py start_path() would never find it (dark telemetry)"
        )
        assert "${RUNNER_TEMP}" in run


def test_band_marks_use_the_cli(env):
    """Every band-mark step goes through the mark subcommand (state-file contract)."""
    for key, spec in _instrumented().items():
        for step in spec["steps"]:
            name = step.get("name") or ""
            if name.startswith("timings band — "):
                run = step.get("run", "").strip()
                assert run.startswith("python3 scripts/nightly_timings.py mark --band "), (
                    f"{key}: {name!r} runs {run!r}"
                )


def test_publish_job_carries_no_timings_wrapper():
    """publish runs on ubuntu-latest with no explicit cap — the wrapper's cap arg
    would be an invented number; it must stay uninstrumented until it gets one."""
    steps = _daily_jobs()["publish"].get("steps") or []
    for step in steps:
        assert "timings" not in (step.get("name") or ""), step
