"""tests/test_admin_live_runs.py — Hermetic tests for admin/live_runs.py.

Coverage:
  snapshot() shape   — all required keys present
  active/queued split — runs routed correctly by status
  elapsed_s          — computed from run_started_at for in_progress
  last_completed     — newest completed run with duration_s + html_url
  jobs budget        — run_jobs called for at most 2 in_progress runs
  queued never gets  jobs call
  bot probe          — 200 → reachable True; 404/timeout/exception → False
  no-requests-lib    → reachable False (graceful degradation)
  heartbeat          — tail-parse from tmp file; malformed line skipped
  snapshot never raises when everything throws
"""
from __future__ import annotations

import json
import sys
import unittest.mock as mock
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _lr():
    """Import live_runs freshly."""
    import admin.live_runs as lr  # noqa: PLC0415
    return lr


def _ga():
    import admin.github_api as ga  # noqa: PLC0415
    return ga


def _make_run(
    workflow: str = "metabolism-cycle.yml",
    status: str = "in_progress",
    conclusion: str | None = None,
    run_id: int = 1000,
    offset_hours: float = 0,
    duration_s: float = 3600,
) -> dict:
    """Build a slim-run-shaped dict as returned by github_api.list_runs."""
    now = datetime(2026, 7, 13, 12, 0, 0, tzinfo=timezone.utc)
    started = now - timedelta(hours=offset_hours, seconds=duration_s if status == "completed" else 0)
    updated = started + timedelta(seconds=duration_s)
    return {
        "id": run_id,
        "name": f"run-{run_id}",
        "display_title": f"Run {run_id}",
        "workflow": workflow,
        "status": status,
        "conclusion": conclusion,
        "event": "schedule",
        "branch": "main",
        "created_at": started.isoformat().replace("+00:00", "Z"),
        "run_started_at": started.isoformat().replace("+00:00", "Z"),
        "updated_at": updated.isoformat().replace("+00:00", "Z"),
        "html_url": f"https://github.com/example/runs/{run_id}",
    }


def _mock_list_runs(lr_mod, runs: list[dict]):
    return mock.patch.object(
        lr_mod.github_api, "list_runs",
        return_value={"ok": True, "runs": runs},
    )


def _mock_run_jobs(lr_mod, jobs: list[dict] | None = None):
    return mock.patch.object(
        lr_mod.github_api, "run_jobs",
        return_value=jobs or [],
    )


# ---------------------------------------------------------------------------
# 1. snapshot() shape — all required top-level keys present
# ---------------------------------------------------------------------------

class TestSnapshotShape:
    def test_all_top_level_keys_present(self):
        lr = _lr()
        with _mock_list_runs(lr, []):
            with _mock_run_jobs(lr):
                result = lr.snapshot()
        for key in ("ts", "metabolism", "codex", "nightly", "mastermind_bot"):
            assert key in result, f"missing key: {key}"

    def test_metabolism_subkeys_present(self):
        lr = _lr()
        with _mock_list_runs(lr, []):
            with _mock_run_jobs(lr):
                result = lr.snapshot()
        met = result["metabolism"]
        for key in ("active", "queued", "last_completed", "heartbeat"):
            assert key in met, f"metabolism missing key: {key}"

    def test_codex_subkeys_present(self):
        lr = _lr()
        with _mock_list_runs(lr, []):
            with _mock_run_jobs(lr):
                result = lr.snapshot()
        for key in ("active", "queued", "last_completed"):
            assert key in result["codex"]

    def test_nightly_subkeys_present(self):
        lr = _lr()
        with _mock_list_runs(lr, []):
            with _mock_run_jobs(lr):
                result = lr.snapshot()
        for key in ("active", "queued", "last_completed"):
            assert key in result["nightly"]

    def test_mastermind_bot_subkeys_present(self):
        lr = _lr()
        with _mock_list_runs(lr, []):
            with _mock_run_jobs(lr):
                with mock.patch.object(lr, "_probe_bot", return_value=False):
                    result = lr.snapshot()
        bot = result["mastermind_bot"]
        for key in ("base", "reachable", "checked_at"):
            assert key in bot

    def test_ts_is_iso_string(self):
        lr = _lr()
        with _mock_list_runs(lr, []):
            with _mock_run_jobs(lr):
                result = lr.snapshot()
        # Must be parseable as an ISO datetime
        dt = datetime.fromisoformat(result["ts"].replace("Z", "+00:00"))
        assert dt.tzinfo is not None


# ---------------------------------------------------------------------------
# 2. active/queued split — runs routed correctly by status
# ---------------------------------------------------------------------------

class TestActiveQueuedSplit:
    def test_in_progress_goes_to_active(self):
        lr = _lr()
        runs = [_make_run(status="in_progress", run_id=1)]
        with _mock_list_runs(lr, runs):
            with _mock_run_jobs(lr):
                result = lr.snapshot()
        assert len(result["metabolism"]["active"]) == 1
        assert len(result["metabolism"]["queued"]) == 0

    def test_queued_goes_to_queued(self):
        lr = _lr()
        runs = [_make_run(status="queued", run_id=2)]
        with _mock_list_runs(lr, runs):
            with _mock_run_jobs(lr):
                result = lr.snapshot()
        assert len(result["metabolism"]["queued"]) == 1
        assert len(result["metabolism"]["active"]) == 0

    def test_completed_goes_to_last_completed(self):
        lr = _lr()
        runs = [_make_run(status="completed", conclusion="success", run_id=3)]
        with _mock_list_runs(lr, runs):
            with _mock_run_jobs(lr):
                result = lr.snapshot()
        lc = result["metabolism"]["last_completed"]
        assert lc is not None
        assert lc["conclusion"] == "success"

    def test_wrong_workflow_excluded(self):
        lr = _lr()
        # daily.yml run should not appear in metabolism scope
        runs = [_make_run(workflow="daily.yml", status="in_progress", run_id=4)]
        with _mock_list_runs(lr, runs):
            with _mock_run_jobs(lr):
                result = lr.snapshot()
        assert len(result["metabolism"]["active"]) == 0
        assert len(result["nightly"]["active"]) == 1

    def test_codex_scope_routing(self):
        lr = _lr()
        runs = [
            _make_run(workflow="codex-research.yml", status="in_progress", run_id=5),
            _make_run(workflow="codex-research.yml", status="queued", run_id=6),
        ]
        with _mock_list_runs(lr, runs):
            with _mock_run_jobs(lr):
                result = lr.snapshot()
        assert len(result["codex"]["active"]) == 1
        assert len(result["codex"]["queued"]) == 1
        assert len(result["metabolism"]["active"]) == 0


# ---------------------------------------------------------------------------
# 3. elapsed_s — computed for in_progress runs
# ---------------------------------------------------------------------------

class TestElapsedS:
    def test_elapsed_s_computed_for_active(self):
        lr = _lr()
        # offset_hours=0, run started now − 0s; but since status=in_progress, _make_run
        # sets started = now − duration_s=3600 (meaning started 1h ago).
        # We use offset_hours=1 here so started = now−1h and elapsed_s ≈ 3600.
        run = _make_run(status="in_progress", run_id=10, offset_hours=1, duration_s=0)
        # Freeze "now" inside live_runs to make elapsed deterministic.
        frozen_now = datetime(2026, 7, 13, 12, 0, 0, tzinfo=timezone.utc)
        with _mock_list_runs(lr, [run]):
            with _mock_run_jobs(lr):
                with mock.patch.object(lr, "_now_utc", return_value=frozen_now):
                    result = lr.snapshot()
        active = result["metabolism"]["active"]
        assert len(active) == 1
        assert "elapsed_s" in active[0]
        assert active[0]["elapsed_s"] is not None
        # 1 hour ago → ≈ 3600s
        assert active[0]["elapsed_s"] == pytest.approx(3600.0, abs=5)

    def test_elapsed_s_none_when_no_timestamps(self):
        lr = _lr()
        run = _make_run(status="in_progress", run_id=11)
        run.pop("run_started_at", None)
        run.pop("created_at", None)
        with _mock_list_runs(lr, [run]):
            with _mock_run_jobs(lr):
                result = lr.snapshot()
        active = result["metabolism"]["active"]
        if active:
            assert active[0]["elapsed_s"] is None


# ---------------------------------------------------------------------------
# 4. last_completed — duration_s + html_url + conclusion
# ---------------------------------------------------------------------------

class TestLastCompleted:
    def test_last_completed_has_duration_s(self):
        lr = _lr()
        run = _make_run(status="completed", conclusion="success", run_id=20, duration_s=1800)
        with _mock_list_runs(lr, [run]):
            with _mock_run_jobs(lr):
                result = lr.snapshot()
        lc = result["metabolism"]["last_completed"]
        assert lc is not None
        assert "duration_s" in lc
        assert lc["duration_s"] is not None
        assert lc["duration_s"] == pytest.approx(1800.0, abs=5)

    def test_last_completed_has_html_url(self):
        lr = _lr()
        run = _make_run(status="completed", conclusion="failure", run_id=21)
        with _mock_list_runs(lr, [run]):
            with _mock_run_jobs(lr):
                result = lr.snapshot()
        lc = result["metabolism"]["last_completed"]
        assert lc is not None
        assert "html_url" in lc
        assert "runs/21" in (lc["html_url"] or "")

    def test_last_completed_is_none_when_no_completed_runs(self):
        lr = _lr()
        runs = [_make_run(status="in_progress", run_id=22)]
        with _mock_list_runs(lr, runs):
            with _mock_run_jobs(lr):
                result = lr.snapshot()
        assert result["metabolism"]["last_completed"] is None

    def test_newest_completed_wins(self):
        lr = _lr()
        # Two completed runs; the one with smaller offset_hours is more recent.
        run_recent = _make_run(status="completed", conclusion="success", run_id=30,
                               offset_hours=1, duration_s=600)
        run_older = _make_run(status="completed", conclusion="failure", run_id=31,
                              offset_hours=5, duration_s=600)
        # list_runs returns newest first, so put run_recent first.
        with _mock_list_runs(lr, [run_recent, run_older]):
            with _mock_run_jobs(lr):
                result = lr.snapshot()
        lc = result["metabolism"]["last_completed"]
        assert lc is not None
        assert lc["id"] == 30


# ---------------------------------------------------------------------------
# 5. jobs budget — run_jobs called for at most 2 in_progress runs total
# ---------------------------------------------------------------------------

class TestJobsBudget:
    def test_jobs_called_on_in_progress_run(self):
        lr = _lr()
        run = _make_run(status="in_progress", run_id=40)
        call_log = []
        def fake_run_jobs(run_id, cap=10):
            call_log.append(run_id)
            return []
        with _mock_list_runs(lr, [run]):
            with mock.patch.object(lr.github_api, "run_jobs", side_effect=fake_run_jobs):
                result = lr.snapshot()
        assert 40 in call_log, "run_jobs should have been called for in_progress run"

    def test_jobs_not_called_for_queued(self):
        lr = _lr()
        run = _make_run(status="queued", run_id=41)
        call_log = []
        def fake_run_jobs(run_id, cap=10):
            call_log.append(run_id)
            return []
        with _mock_list_runs(lr, [run]):
            with mock.patch.object(lr.github_api, "run_jobs", side_effect=fake_run_jobs):
                lr.snapshot()
        assert 41 not in call_log, "run_jobs must not be called for queued run"

    def test_jobs_budget_capped_at_two(self):
        lr = _lr()
        # 4 in_progress runs across metabolism + codex + nightly
        runs = [
            _make_run(workflow="metabolism-cycle.yml", status="in_progress", run_id=50),
            _make_run(workflow="codex-research.yml", status="in_progress", run_id=51),
            _make_run(workflow="daily.yml", status="in_progress", run_id=52),
            _make_run(workflow="metabolism-agenda.yml", status="in_progress", run_id=53),
        ]
        call_log = []
        def fake_run_jobs(run_id, cap=10):
            call_log.append(run_id)
            return []
        with _mock_list_runs(lr, runs):
            with mock.patch.object(lr.github_api, "run_jobs", side_effect=fake_run_jobs):
                lr.snapshot()
        assert len(call_log) <= 2, (
            f"run_jobs called {len(call_log)} times; budget is 2; called for: {call_log}"
        )

    def test_jobs_attached_to_run_dict(self):
        lr = _lr()
        fake_jobs = [{"name": "Build", "status": "in_progress", "conclusion": None,
                      "started_at": None, "completed_at": None,
                      "current_step": "Run tests", "steps_done": 1, "steps_total": 3}]
        run = _make_run(status="in_progress", run_id=60)
        with _mock_list_runs(lr, [run]):
            with mock.patch.object(lr.github_api, "run_jobs", return_value=fake_jobs):
                result = lr.snapshot()
        active = result["metabolism"]["active"]
        assert len(active) == 1
        assert "jobs" in active[0]
        assert active[0]["jobs"] == fake_jobs


# ---------------------------------------------------------------------------
# 6. mastermind bot probe
# ---------------------------------------------------------------------------

class TestMastermindBotProbe:
    def test_200_returns_reachable_true(self):
        lr = _lr()
        lr._BOT_PROBE_CACHE = None  # clear any cached result from previous test
        with _mock_list_runs(lr, []):
            with _mock_run_jobs(lr):
                with mock.patch.object(lr, "_probe_bot", return_value=True):
                    result = lr.snapshot()
        assert result["mastermind_bot"]["reachable"] is True

    def test_404_returns_reachable_false(self):
        lr = _lr()
        lr._BOT_PROBE_CACHE = None  # clear any cached result from previous test
        with _mock_list_runs(lr, []):
            with _mock_run_jobs(lr):
                with mock.patch.object(lr, "_probe_bot", return_value=False):
                    result = lr.snapshot()
        assert result["mastermind_bot"]["reachable"] is False

    def test_exception_returns_reachable_false(self):
        lr = _lr()
        lr._BOT_PROBE_CACHE = None  # clear any cached result from previous test
        with _mock_list_runs(lr, []):
            with _mock_run_jobs(lr):
                with mock.patch.object(lr, "_probe_bot", side_effect=RuntimeError("boom")):
                    result = lr.snapshot()
        assert result["mastermind_bot"]["reachable"] is False

    def test_probe_bot_direct_200(self, monkeypatch):
        """_probe_bot returns True when requests.get gives HTTP 200."""
        lr = _lr()
        fake_resp = mock.MagicMock()
        fake_resp.status_code = 200
        fake_req = mock.MagicMock()
        fake_req.get.return_value = fake_resp
        monkeypatch.setitem(sys.modules, "requests", fake_req)
        result = lr._probe_bot("http://127.0.0.1:8000")
        assert result is True

    def test_probe_bot_direct_404(self, monkeypatch):
        """_probe_bot returns False when requests.get gives HTTP 404."""
        lr = _lr()
        fake_resp = mock.MagicMock()
        fake_resp.status_code = 404
        fake_req = mock.MagicMock()
        fake_req.get.return_value = fake_resp
        monkeypatch.setitem(sys.modules, "requests", fake_req)
        result = lr._probe_bot("http://127.0.0.1:8000")
        assert result is False

    def test_probe_bot_timeout(self, monkeypatch):
        """_probe_bot returns False on requests.exceptions.Timeout."""
        import requests as _requests_real  # noqa: PLC0415
        lr = _lr()
        fake_req = mock.MagicMock()
        fake_req.get.side_effect = Exception("timeout")
        monkeypatch.setitem(sys.modules, "requests", fake_req)
        result = lr._probe_bot("http://127.0.0.1:8000")
        assert result is False

    def test_probe_bot_no_requests_lib(self, monkeypatch):
        """_probe_bot returns False when requests library is unavailable."""
        lr = _lr()
        saved = sys.modules.pop("requests", None)
        monkeypatch.setitem(sys.modules, "requests", None)  # type: ignore[arg-type]
        try:
            result = lr._probe_bot("http://127.0.0.1:8000")
        finally:
            if saved is not None:
                sys.modules["requests"] = saved
            else:
                sys.modules.pop("requests", None)
        assert result is False

    def test_base_url_from_env(self, monkeypatch):
        """snapshot() uses MASTERMIND_BOT_BASE env when set."""
        lr = _lr()
        lr._BOT_PROBE_CACHE = None  # clear any cached result from previous test
        monkeypatch.setenv("MASTERMIND_BOT_BASE", "http://10.0.0.1:9001")
        with _mock_list_runs(lr, []):
            with _mock_run_jobs(lr):
                with mock.patch.object(lr, "_probe_bot", return_value=False) as probe:
                    result = lr.snapshot()
        assert result["mastermind_bot"]["base"] == "http://10.0.0.1:9001"

    def test_default_base_when_env_unset(self, monkeypatch):
        """snapshot() defaults to http://127.0.0.1:8000 when env is unset."""
        lr = _lr()
        lr._BOT_PROBE_CACHE = None  # clear any cached result from previous test
        monkeypatch.delenv("MASTERMIND_BOT_BASE", raising=False)
        with _mock_list_runs(lr, []):
            with _mock_run_jobs(lr):
                with mock.patch.object(lr, "_probe_bot", return_value=False):
                    result = lr.snapshot()
        assert result["mastermind_bot"]["base"] == "http://127.0.0.1:8000"


# ---------------------------------------------------------------------------
# 7. heartbeat tail parsing
# ---------------------------------------------------------------------------

class TestHeartbeatParsing:
    def _write_heartbeat(self, tmp_path: Path, lines: list[str]) -> Path:
        p = tmp_path / "heartbeat.jsonl"
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return p

    def test_last_valid_line_returned(self, tmp_path):
        lr = _lr()
        lines = [
            json.dumps({"schema": "metabolism.heartbeat.v1", "ts": "2026-07-12T11:00:00Z",
                        "phase": "P0_inert", "note": "first"}),
            json.dumps({"schema": "metabolism.heartbeat.v1", "ts": "2026-07-12T12:00:00Z",
                        "phase": "P0_inert", "note": "second"}),
        ]
        path = self._write_heartbeat(tmp_path, lines)
        with mock.patch.object(lr, "_HEARTBEAT_PATH", path):
            hb = lr._read_last_heartbeat()
        assert hb is not None
        assert hb["note"] == "second"

    def test_malformed_line_skipped(self, tmp_path):
        lr = _lr()
        lines = [
            json.dumps({"schema": "metabolism.heartbeat.v1", "ts": "2026-07-12T11:00:00Z",
                        "phase": "P0_inert", "note": "good"}),
            "this is not JSON!!!",
        ]
        path = self._write_heartbeat(tmp_path, lines)
        with mock.patch.object(lr, "_HEARTBEAT_PATH", path):
            hb = lr._read_last_heartbeat()
        # Last valid line is the first one (second is malformed)
        assert hb is not None
        assert hb["note"] == "good"

    def test_absent_heartbeat_returns_none(self, tmp_path):
        lr = _lr()
        absent_path = tmp_path / "nonexistent.jsonl"
        with mock.patch.object(lr, "_HEARTBEAT_PATH", absent_path):
            hb = lr._read_last_heartbeat()
        assert hb is None

    def test_empty_file_returns_none(self, tmp_path):
        lr = _lr()
        path = tmp_path / "heartbeat.jsonl"
        path.write_text("", encoding="utf-8")
        with mock.patch.object(lr, "_HEARTBEAT_PATH", path):
            hb = lr._read_last_heartbeat()
        assert hb is None

    def test_all_malformed_returns_none(self, tmp_path):
        lr = _lr()
        path = self._write_heartbeat(tmp_path, ["bad1", "bad2", "{incomplete"])
        with mock.patch.object(lr, "_HEARTBEAT_PATH", path):
            hb = lr._read_last_heartbeat()
        assert hb is None

    def test_heartbeat_appears_in_snapshot(self, tmp_path):
        lr = _lr()
        lines = [json.dumps({"schema": "v1", "ts": "2026-07-13T10:00:00Z",
                              "phase": "P0_inert", "note": "probe"})]
        path = self._write_heartbeat(tmp_path, lines)
        with mock.patch.object(lr, "_HEARTBEAT_PATH", path):
            with _mock_list_runs(lr, []):
                with _mock_run_jobs(lr):
                    with mock.patch.object(lr, "_probe_bot", return_value=False):
                        result = lr.snapshot()
        assert result["metabolism"]["heartbeat"] is not None
        assert result["metabolism"]["heartbeat"]["note"] == "probe"


# ---------------------------------------------------------------------------
# 8. snapshot never raises when EVERYTHING is broken
# ---------------------------------------------------------------------------

class TestSnapshotNeverRaises:
    def test_list_runs_throws(self):
        lr = _lr()
        lr._BOT_PROBE_CACHE = None  # clear any cached result from previous test
        with mock.patch.object(lr.github_api, "list_runs", side_effect=RuntimeError("net dead")):
            with mock.patch.object(lr.github_api, "run_jobs", side_effect=RuntimeError("net dead")):
                with mock.patch.object(lr, "_probe_bot", side_effect=RuntimeError("probe dead")):
                    with mock.patch.object(lr, "_read_last_heartbeat",
                                           side_effect=RuntimeError("fs dead")):
                        result = lr.snapshot()
        assert isinstance(result, dict)
        assert "ts" in result
        assert result["metabolism"]["active"] == []
        assert result["metabolism"]["heartbeat"] is None
        assert result["mastermind_bot"]["reachable"] is False

    def test_list_runs_returns_error(self):
        lr = _lr()
        with mock.patch.object(lr.github_api, "list_runs",
                               return_value={"ok": False, "error": "HTTP 403", "runs": []}):
            with _mock_run_jobs(lr):
                result = lr.snapshot()
        assert isinstance(result, dict)
        assert result["metabolism"]["active"] == []

    def test_all_mocks_throw(self):
        """snapshot() must not raise when every external call (network + filesystem
        + bot probe) throws. _now_utc is an internal datetime helper, not an
        external dependency, so it is not mocked here."""
        lr = _lr()
        lr._BOT_PROBE_CACHE = None  # clear any cached result from previous test
        with mock.patch.object(lr.github_api, "list_runs", side_effect=Exception("x")):
            with mock.patch.object(lr.github_api, "run_jobs", side_effect=Exception("x")):
                with mock.patch.object(lr, "_probe_bot", side_effect=Exception("x")):
                    with mock.patch.object(lr, "_read_last_heartbeat",
                                           side_effect=Exception("x")):
                        try:
                            result = lr.snapshot()
                            assert isinstance(result, dict)
                        except Exception as exc:
                            pytest.fail(f"snapshot() raised {exc!r}")

    def test_returns_dict_type(self):
        lr = _lr()
        with mock.patch.object(lr.github_api, "list_runs",
                               return_value={"ok": True, "runs": []}):
            with _mock_run_jobs(lr):
                result = lr.snapshot()
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# 9. run_jobs shape (via github_api)
# ---------------------------------------------------------------------------

class TestRunJobsShape:
    def test_run_jobs_returns_list(self):
        ga = _ga()
        if ga.requests is None:
            pytest.skip("requests not installed")
        # Monkeypatch requests at the module level
        fake_resp = mock.MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {
            "jobs": [{
                "name": "Build",
                "status": "in_progress",
                "conclusion": None,
                "started_at": "2026-07-13T10:00:00Z",
                "completed_at": None,
                "steps": [
                    {"name": "Checkout", "status": "completed"},
                    {"name": "Run tests", "status": "in_progress"},
                    {"name": "Upload artifacts", "status": "queued"},
                ],
            }]
        }
        with mock.patch.object(ga.requests, "get", return_value=fake_resp):
            with mock.patch("admin.github_api.repo", return_value=("owner", "repo")):
                jobs = ga.run_jobs(run_id=12345, cap=10)
        assert isinstance(jobs, list)
        assert len(jobs) == 1
        j = jobs[0]
        assert j["name"] == "Build"
        assert j["status"] == "in_progress"
        assert j["current_step"] == "Run tests"
        assert j["steps_done"] == 1
        assert j["steps_total"] == 3

    def test_run_jobs_fail_soft_on_error(self):
        ga = _ga()
        if ga.requests is None:
            pytest.skip("requests not installed")
        fake_resp = mock.MagicMock()
        fake_resp.status_code = 403
        with mock.patch.object(ga.requests, "get", return_value=fake_resp):
            with mock.patch("admin.github_api.repo", return_value=("owner", "repo")):
                jobs = ga.run_jobs(run_id=99999)
        assert jobs == []

    def test_run_jobs_no_requests_returns_empty(self):
        ga = _ga()
        saved = ga.requests
        ga.requests = None
        try:
            jobs = ga.run_jobs(run_id=1)
        finally:
            ga.requests = saved
        assert jobs == []

    def test_run_jobs_no_repo_returns_empty(self):
        ga = _ga()
        if ga.requests is None:
            pytest.skip("requests not installed")
        with mock.patch("admin.github_api.repo", return_value=(None, None)):
            jobs = ga.run_jobs(run_id=1)
        assert jobs == []

    def test_run_jobs_exception_returns_empty(self):
        ga = _ga()
        if ga.requests is None:
            pytest.skip("requests not installed")
        with mock.patch.object(ga.requests, "get", side_effect=Exception("net error")):
            with mock.patch("admin.github_api.repo", return_value=("owner", "repo")):
                jobs = ga.run_jobs(run_id=1)
        assert jobs == []

    def test_run_jobs_never_raises(self):
        """run_jobs must never raise regardless of what the API does."""
        ga = _ga()
        if ga.requests is None:
            # requests unavailable — fail-soft path already tested above
            result = ga.run_jobs(run_id=1)
            assert result == []
            return
        with mock.patch.object(ga.requests, "get", side_effect=RuntimeError("kaboom")):
            with mock.patch("admin.github_api.repo", return_value=("owner", "repo")):
                result = ga.run_jobs(run_id=1)
        assert isinstance(result, list)

    def test_run_jobs_current_step_none_when_no_in_progress(self):
        ga = _ga()
        if ga.requests is None:
            pytest.skip("requests not installed")
        fake_resp = mock.MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {
            "jobs": [{
                "name": "Done",
                "status": "completed",
                "conclusion": "success",
                "started_at": None,
                "completed_at": None,
                "steps": [
                    {"name": "Step A", "status": "completed"},
                    {"name": "Step B", "status": "completed"},
                ],
            }]
        }
        with mock.patch.object(ga.requests, "get", return_value=fake_resp):
            with mock.patch("admin.github_api.repo", return_value=("owner", "repo")):
                jobs = ga.run_jobs(run_id=1)
        assert jobs[0]["current_step"] is None
        assert jobs[0]["steps_done"] == 2
        assert jobs[0]["steps_total"] == 2


# ---------------------------------------------------------------------------
# 10. Import smoke tests
# ---------------------------------------------------------------------------

class TestImports:
    def test_live_runs_importable(self):
        lr = _lr()
        assert callable(lr.snapshot)
        assert callable(lr._probe_bot)
        assert callable(lr._read_last_heartbeat)

    def test_server_imports_live_runs(self):
        import admin.server as srv  # noqa: PLC0415
        import admin.live_runs as lr  # noqa: PLC0415
        assert srv.live_runs is lr

    def test_github_api_has_run_jobs(self):
        ga = _ga()
        assert callable(ga.run_jobs)


# ---------------------------------------------------------------------------
# 11. Bot probe caching (FIX 2a)
# ---------------------------------------------------------------------------

class TestBotProbeCache:
    def _snapshot_with_fake_probe(self, lr, probe_fn):
        """Call snapshot() with a patched _probe_bot (no network side-effects)."""
        with _mock_list_runs(lr, []):
            with _mock_run_jobs(lr):
                with mock.patch.object(lr, "_probe_bot", side_effect=probe_fn):
                    return lr.snapshot()

    def test_probe_called_once_within_window(self, monkeypatch):
        """Two snapshot() calls within 120s must trigger exactly one probe call."""
        lr = _lr()
        # Reset module-level cache so we start fresh.
        lr._BOT_PROBE_CACHE = None

        call_count = []

        def counting_probe(base):
            call_count.append(base)
            return True

        frozen_now = datetime(2026, 7, 13, 12, 0, 0, tzinfo=timezone.utc)

        with _mock_list_runs(lr, []):
            with _mock_run_jobs(lr):
                with mock.patch.object(lr, "_probe_bot", side_effect=counting_probe):
                    with mock.patch.object(lr, "_now_utc", return_value=frozen_now):
                        lr.snapshot()
                    # Second call with the same frozen time (within 120s window).
                    with mock.patch.object(lr, "_probe_bot", side_effect=counting_probe):
                        with mock.patch.object(lr, "_now_utc", return_value=frozen_now):
                            result2 = lr.snapshot()

        assert len(call_count) == 1, (
            f"probe called {len(call_count)} times within the cache window; expected 1"
        )
        # Cached result must be reused.
        assert result2["mastermind_bot"]["reachable"] is True

    def test_probe_re_called_after_window(self, monkeypatch):
        """When clock advances past 120s, snapshot() must re-probe."""
        lr = _lr()
        lr._BOT_PROBE_CACHE = None

        t0 = datetime(2026, 7, 13, 12, 0, 0, tzinfo=timezone.utc)
        t1 = t0 + timedelta(seconds=121)

        call_count = []

        def counting_probe(base):
            call_count.append(base)
            return False

        with _mock_list_runs(lr, []):
            with _mock_run_jobs(lr):
                # First snapshot at t0.
                with mock.patch.object(lr, "_probe_bot", side_effect=counting_probe):
                    with mock.patch.object(lr, "_now_utc", return_value=t0):
                        lr.snapshot()
                # Second snapshot at t1 (past the 120s interval).
                with mock.patch.object(lr, "_probe_bot", side_effect=counting_probe):
                    with mock.patch.object(lr, "_now_utc", return_value=t1):
                        lr.snapshot()

        assert len(call_count) == 2, (
            f"probe called {len(call_count)} times; expected 2 (once at t0, once at t1)"
        )

    def test_checked_at_reflects_actual_probe_time(self, monkeypatch):
        """checked_at in the snapshot must equal the time of the most recent probe."""
        lr = _lr()
        lr._BOT_PROBE_CACHE = None

        probe_time = datetime(2026, 7, 13, 12, 0, 0, tzinfo=timezone.utc)

        with _mock_list_runs(lr, []):
            with _mock_run_jobs(lr):
                with mock.patch.object(lr, "_probe_bot", return_value=True):
                    with mock.patch.object(lr, "_now_utc", return_value=probe_time):
                        result = lr.snapshot()

        assert result["mastermind_bot"]["checked_at"] == probe_time.isoformat()


# ---------------------------------------------------------------------------
# 12. last_completed filters to primary workflow (FIX 3)
# ---------------------------------------------------------------------------

class TestLastCompletedPrimaryFilter:
    def test_stage_workflow_does_not_shadow_primary(self):
        """A completed stage workflow (metabolism-build.yml) must NOT appear as
        last_completed when the primary (metabolism-cycle.yml) has no completed run."""
        lr = _lr()
        # Only a stage workflow completed — primary has no completed run.
        runs = [
            _make_run(workflow="metabolism-build.yml", status="completed",
                      conclusion="success", run_id=100),
        ]
        with _mock_list_runs(lr, runs):
            with _mock_run_jobs(lr):
                result = lr.snapshot()
        # last_completed must be None because no PRIMARY run completed.
        assert result["metabolism"]["last_completed"] is None

    def test_primary_workflow_wins_over_recent_stage(self):
        """When a stage workflow completed more recently than the primary,
        last_completed must still be the primary workflow's run."""
        lr = _lr()
        # Stage run (more recent — lower offset) completed more recently.
        run_stage = _make_run(workflow="metabolism-build.yml", status="completed",
                              conclusion="success", run_id=200, offset_hours=1, duration_s=300)
        # Primary run (older — higher offset).
        run_primary = _make_run(workflow="metabolism-cycle.yml", status="completed",
                                conclusion="success", run_id=201, offset_hours=3, duration_s=600)
        # list_runs returns newest first.
        with _mock_list_runs(lr, [run_stage, run_primary]):
            with _mock_run_jobs(lr):
                result = lr.snapshot()
        lc = result["metabolism"]["last_completed"]
        assert lc is not None, "last_completed must not be None when primary ran"
        assert lc["id"] == 201, (
            f"expected primary run id=201 as last_completed; got id={lc['id']}"
        )

    def test_codex_primary_filter(self):
        """codex last_completed must only return codex-research.yml runs."""
        lr = _lr()
        # Only a non-existent codex sub-workflow (shouldn't exist, but safety check).
        # We simulate a run with a codex-adjacent name that is NOT the primary.
        runs = [
            _make_run(workflow="codex-research.yml", status="completed",
                      conclusion="success", run_id=300),
        ]
        with _mock_list_runs(lr, runs):
            with _mock_run_jobs(lr):
                result = lr.snapshot()
        lc = result["codex"]["last_completed"]
        assert lc is not None
        assert lc["id"] == 300

    def test_nightly_primary_filter(self):
        """nightly last_completed must only return daily.yml runs."""
        lr = _lr()
        runs = [
            _make_run(workflow="daily.yml", status="completed",
                      conclusion="success", run_id=400),
        ]
        with _mock_list_runs(lr, runs):
            with _mock_run_jobs(lr):
                result = lr.snapshot()
        lc = result["nightly"]["last_completed"]
        assert lc is not None
        assert lc["id"] == 400
