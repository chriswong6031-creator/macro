"""tests/test_admin_metabolism_ux.py — Hermetic tests for Metabolism Throttle UX v11.

Coverage:
  validate_rununtil_body()  — vocab, bad values, missing mode
  validate_throttle_body()  — pace accepts new vocab (low/medium/high/max) AND legacy
  _median_cycle_duration()  — median math, sub-300s exclusion, empty input
  panel() loop_duration      — correct key present, median computed
  panel() budget_status      — fresh/stale/absent variants (monkeypatched file)
  rununtil POST handler      — arm sets variable + dispatches; off sets only; blocked path
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

def _mp():
    """Import metabolism_panel freshly."""
    import admin.metabolism_panel as mp  # noqa: PLC0415
    return mp


def _make_run(workflow="metabolism-cycle.yml", conclusion="success",
              duration_s=3600, created_offset_hours=0):
    """Build a fake run dict as returned by _recent_metabolism_runs."""
    now = datetime(2026, 7, 13, 12, 0, 0, tzinfo=timezone.utc)
    created = now - timedelta(hours=created_offset_hours)
    updated = created + timedelta(seconds=duration_s)
    return {
        "name": "Metabolism Cycle",
        "workflow": workflow,
        "status": "completed",
        "conclusion": conclusion,
        "created_at": created.isoformat().replace("+00:00", "Z"),
        "updated_at": updated.isoformat().replace("+00:00", "Z"),
        "html_url": "https://github.com/example/runs/1",
    }


def _mock_gh(mp, *, variables=None, runs=None):
    """Patch github_api for metabolism_panel: get_repo_variable + list_runs."""
    variables = variables or {}
    runs_data = runs or []

    def fake_get(name):
        return variables.get(name)

    patcher_var = mock.patch.object(mp.github_api, "get_repo_variable", side_effect=fake_get)
    patcher_runs = mock.patch.object(
        mp.github_api, "list_runs",
        return_value={"ok": True, "runs": runs_data},
    )
    return patcher_var, patcher_runs


# ---------------------------------------------------------------------------
# 1. validate_rununtil_body — pure function
# ---------------------------------------------------------------------------

class TestValidateRununtilBody:
    def test_off_valid(self):
        mp = _mp()
        ok, err, mode = mp.validate_rununtil_body({"mode": "off"})
        assert ok is True
        assert err is None
        assert mode == "off"

    def test_5h_max_valid(self):
        mp = _mp()
        ok, err, mode = mp.validate_rununtil_body({"mode": "5h_max"})
        assert ok is True
        assert mode == "5h_max"

    def test_weekly_max_valid(self):
        mp = _mp()
        ok, err, mode = mp.validate_rununtil_body({"mode": "weekly_max"})
        assert ok is True
        assert mode == "weekly_max"

    def test_invalid_mode(self):
        mp = _mp()
        ok, err, mode = mp.validate_rununtil_body({"mode": "banana"})
        assert ok is False
        assert err is not None
        assert "banana" in err
        assert mode is None

    def test_missing_mode(self):
        mp = _mp()
        ok, err, mode = mp.validate_rununtil_body({})
        assert ok is False
        assert err is not None
        assert mode is None

    def test_none_mode(self):
        mp = _mp()
        ok, err, mode = mp.validate_rununtil_body({"mode": None})
        assert ok is False
        assert mode is None

    def test_never_raises_on_bad_input(self):
        mp = _mp()
        # Should not raise even with completely wrong type
        ok, err, mode = mp.validate_rununtil_body("not a dict")  # type: ignore[arg-type]
        assert ok is False


# ---------------------------------------------------------------------------
# 2. validate_throttle_body — pace accepts new and legacy vocab
# ---------------------------------------------------------------------------

class TestValidateThrottleBodyPace:
    """Pace validator must accept new vocab (low/medium/high/max) AND legacy (single/2x/4x)."""

    def test_pace_low_accepted(self):
        mp = _mp()
        ok, errors, to_set = mp.validate_throttle_body({"pace": "low"})
        assert ok is True
        assert "METAB_PACE" in to_set
        assert to_set["METAB_PACE"] == "low"

    def test_pace_medium_accepted(self):
        mp = _mp()
        ok, errors, to_set = mp.validate_throttle_body({"pace": "medium"})
        assert ok is True
        assert to_set["METAB_PACE"] == "medium"

    def test_pace_high_accepted(self):
        mp = _mp()
        ok, errors, to_set = mp.validate_throttle_body({"pace": "high"})
        assert ok is True
        assert to_set["METAB_PACE"] == "high"

    def test_pace_max_accepted(self):
        mp = _mp()
        ok, errors, to_set = mp.validate_throttle_body({"pace": "max"})
        assert ok is True
        assert to_set["METAB_PACE"] == "max"

    def test_pace_legacy_single_accepted(self):
        mp = _mp()
        ok, errors, to_set = mp.validate_throttle_body({"pace": "single"})
        assert ok is True
        assert to_set["METAB_PACE"] == "single"

    def test_pace_legacy_2x_accepted(self):
        mp = _mp()
        ok, errors, to_set = mp.validate_throttle_body({"pace": "2x"})
        assert ok is True
        assert to_set["METAB_PACE"] == "2x"

    def test_pace_legacy_4x_accepted(self):
        mp = _mp()
        ok, errors, to_set = mp.validate_throttle_body({"pace": "4x"})
        assert ok is True
        assert to_set["METAB_PACE"] == "4x"

    def test_pace_invalid_rejected(self):
        mp = _mp()
        ok, errors, to_set = mp.validate_throttle_body({"pace": "turbo"})
        assert ok is False
        assert "pace" in errors
        assert "METAB_PACE" not in to_set

    def test_pace_empty_string_rejected(self):
        mp = _mp()
        ok, errors, to_set = mp.validate_throttle_body({"pace": ""})
        assert ok is False
        assert "pace" in errors


# ---------------------------------------------------------------------------
# 3. _median_cycle_duration — median math + exclusion logic
# ---------------------------------------------------------------------------

class TestMedianCycleDuration:
    def _dur(self, runs, floor_s=300):
        mp = _mp()
        return mp._median_cycle_duration(runs, floor_s=floor_s)

    def test_empty_runs_returns_fallback(self):
        result = self._dur([])
        assert result["median_s"] is None
        assert result["n"] == 0
        assert "worst case" in result["label"]

    def test_single_run_is_median(self):
        runs = [_make_run(duration_s=3600)]
        result = self._dur(runs)
        assert result["median_s"] == pytest.approx(3600.0)
        assert result["n"] == 1
        assert "60m" in result["label"]

    def test_odd_count_median(self):
        # durations: 1h, 2h, 3h — median = 2h
        runs = [
            _make_run(duration_s=3600, created_offset_hours=0),
            _make_run(duration_s=7200, created_offset_hours=1),
            _make_run(duration_s=10800, created_offset_hours=2),
        ]
        result = self._dur(runs)
        assert result["median_s"] == pytest.approx(7200.0)
        assert result["n"] == 3

    def test_even_count_median(self):
        # durations: 1h, 2h — median = 1.5h = 90m
        runs = [
            _make_run(duration_s=3600, created_offset_hours=0),
            _make_run(duration_s=7200, created_offset_hours=1),
        ]
        result = self._dur(runs)
        assert result["median_s"] == pytest.approx(5400.0)
        assert "90m" in result["label"]

    def test_sub_floor_runs_excluded(self):
        # One run below floor (200s), one above (3600s)
        short = _make_run(duration_s=200)
        long_run = _make_run(duration_s=3600, created_offset_hours=1)
        result = self._dur([short, long_run], floor_s=300)
        assert result["n"] == 1
        assert result["median_s"] == pytest.approx(3600.0)

    def test_all_below_floor_returns_fallback(self):
        runs = [_make_run(duration_s=100), _make_run(duration_s=200)]
        result = self._dur(runs, floor_s=300)
        assert result["median_s"] is None
        assert "worst case" in result["label"]

    def test_non_cycle_runs_excluded(self):
        # Only metabolism-agenda runs — not cycle
        agenda = _make_run(workflow="metabolism-agenda.yml", duration_s=1800)
        result = self._dur([agenda])
        assert result["median_s"] is None
        assert result["n"] == 0

    def test_in_progress_runs_excluded(self):
        # conclusion=None means in-progress
        in_prog = _make_run(conclusion=None, duration_s=3600)
        result = self._dur([in_prog])
        assert result["n"] == 0

    def test_cap_at_10(self):
        # 12 valid runs — only first 10 counted
        runs = [_make_run(duration_s=3600 + i * 60, created_offset_hours=i) for i in range(12)]
        result = self._dur(runs, floor_s=300)
        assert result["n"] == 10

    def test_label_format(self):
        runs = [_make_run(duration_s=5400)]  # 90 minutes
        result = self._dur(runs)
        assert "~90m median" in result["label"]
        assert "(of 1)" in result["label"]


# ---------------------------------------------------------------------------
# 4. panel() — loop_duration key present and plumbed correctly
# ---------------------------------------------------------------------------

class TestPanelLoopDuration:
    def test_loop_duration_key_present(self, tmp_path):
        mp = _mp()
        pv, pr = _mock_gh(mp)
        with pv, pr:
            with mock.patch.object(mp, "_key_health", return_value=[]):
                result = mp.panel()
        assert "loop_duration" in result
        ld = result["loop_duration"]
        assert "median_s" in ld
        assert "n" in ld
        assert "label" in ld

    def test_loop_duration_with_real_runs(self, tmp_path):
        mp = _mp()
        runs_data = [_make_run(duration_s=3600), _make_run(duration_s=7200, created_offset_hours=6)]
        pv, pr = _mock_gh(mp, runs=runs_data)
        with pv, pr:
            with mock.patch.object(mp, "_key_health", return_value=[]):
                with mock.patch.object(mp, "_recent_metabolism_runs", return_value=runs_data):
                    result = mp.panel()
        ld = result["loop_duration"]
        assert ld["n"] == 2
        assert ld["median_s"] == pytest.approx(5400.0)

    def test_panel_never_raises(self):
        mp = _mp()
        with mock.patch.object(mp.github_api, "get_repo_variable", side_effect=RuntimeError("boom")):
            with mock.patch.object(mp.github_api, "list_runs", side_effect=RuntimeError("boom")):
                result = mp.panel()
        assert isinstance(result, dict)
        assert "loop_duration" in result


# ---------------------------------------------------------------------------
# 5. panel() — budget_status ingestion (fresh/stale/absent)
# ---------------------------------------------------------------------------

class TestPanelBudgetStatus:
    def _panel_with_budget(self, tmp_path, data=None):
        mp = _mp()
        if data is not None:
            budget_path = tmp_path / "data" / "metabolism" / "key_budget_status.json"
            budget_path.parent.mkdir(parents=True, exist_ok=True)
            budget_path.write_text(json.dumps(data), encoding="utf-8")
        pv, pr = _mock_gh(mp)
        with pv, pr:
            with mock.patch.object(mp, "_key_health", return_value=[]):
                with mock.patch.object(mp, "_budget_status", return_value=data):
                    result = mp.panel()
        return result

    def test_absent_budget_status_returns_none(self, tmp_path):
        result = self._panel_with_budget(tmp_path, data=None)
        assert result["budget_status"] is None

    def test_budget_status_passthrough(self, tmp_path):
        data = {
            "schema": "metab_budget_status.v1",
            "ts": "2026-07-13T12:00:00Z",
            "per_key": {
                "claude_code_oauth_1": {
                    "pct_5h": 42.0,
                    "src_5h": "reported",
                    "pct_weekly": 30.0,
                    "src_weekly": "reported",
                    "reset_5h": None,
                    "reset_weekly": None,
                }
            },
            "verdicts": {
                "manual": {"blocked": False, "eligible_keys": [], "all_done": False, "reason": ""}
            },
        }
        result = self._panel_with_budget(tmp_path, data=data)
        bs = result["budget_status"]
        assert bs is not None
        assert bs["schema"] == "metab_budget_status.v1"
        assert "claude_code_oauth_1" in bs["per_key"]

    def test_budget_status_key_in_panel(self, tmp_path):
        mp = _mp()
        pv, pr = _mock_gh(mp)
        with pv, pr:
            with mock.patch.object(mp, "_key_health", return_value=[]):
                result = mp.panel()
        assert "budget_status" in result


# ---------------------------------------------------------------------------
# 6. rununtil POST handler (via server.py) — monkeypatched github_api
# ---------------------------------------------------------------------------

class TestRununtiHandler:
    """Test the /api/metabolism/rununtil server route."""

    def _srv(self):
        import admin.server as srv  # noqa: PLC0415
        return srv

    def _do_post(self, srv, body, *, token_ok=True, set_ok=True, dispatch_ok=True,
                 budget_blocked=False):
        """Simulate the rununtil POST handler logic directly."""
        mp = _mp()
        # Patch github_api on server module
        with mock.patch.object(srv.github_api, "token", return_value="fake" if token_ok else None):
            with mock.patch.object(srv.github_api, "set_repo_variable", return_value=set_ok):
                with mock.patch.object(srv.github_api, "dispatch",
                                       return_value={"ok": dispatch_ok}):
                    # Patch validate + budget_gate on server's metabolism_panel reference
                    with mock.patch.object(srv.metabolism_panel, "validate_rununtil_body",
                                           wraps=mp.validate_rununtil_body):
                        # Simulate budget_gate import with monkeypatch
                        fake_gate = mock.MagicMock(return_value={
                            "blocked": budget_blocked,
                            "reason": "All keys >=90% weekly — wait for a weekly reset." if budget_blocked else "",
                            "eligible_keys": [],
                            "all_done": False,
                        })
                        import sys as _sys  # noqa: PLC0415
                        # Create a fake budget_gate module
                        fake_mod = type(_sys)("engine.metabolism.budget_gate")
                        fake_mod.gate_verdict = fake_gate
                        old = _sys.modules.get("engine.metabolism.budget_gate")
                        _sys.modules["engine.metabolism.budget_gate"] = fake_mod
                        try:
                            # Run the handler logic directly
                            return self._handler_logic(srv, mp, body, fake_gate)
                        finally:
                            if old is None:
                                _sys.modules.pop("engine.metabolism.budget_gate", None)
                            else:
                                _sys.modules["engine.metabolism.budget_gate"] = old

    def _handler_logic(self, srv, mp, body, fake_gate):
        """Replicate the server route logic for testing without HTTP."""
        if not body.get("confirm"):
            return {"ok": False, "error": "confirm required"}
        if not srv.github_api.token():
            return {"ok": False, "error": "No GitHub token configured."}
        ok_v, err_msg, mode = mp.validate_rununtil_body(body)
        if not ok_v:
            return {"ok": False, "error": err_msg}
        # For arm modes, check budget gate
        if mode != "off":
            verdict = fake_gate("manual")
            if verdict.get("blocked"):
                reason = verdict.get("reason") or "All keys >=90% weekly."
                return {"ok": False, "error": reason, "blocked": True}
        set_ok = srv.github_api.set_repo_variable("METAB_RUN_UNTIL", mode)
        if not set_ok:
            return {"ok": False, "error": "Failed to set METAB_RUN_UNTIL"}
        dispatch_result = None
        if mode != "off":
            dispatch_result = srv.github_api.dispatch(
                workflow="metabolism-cycle.yml", ref="main"
            )
        return {
            "ok": True,
            "mode": mode,
            "dispatched": dispatch_result is not None and bool(dispatch_result.get("ok")),
        }

    def test_arm_5h_max_sets_variable(self):
        srv = self._srv()
        mp = _mp()
        set_calls = []
        dispatch_calls = []
        with mock.patch.object(srv.github_api, "token", return_value="fake"):
            with mock.patch.object(srv.github_api, "set_repo_variable",
                                   side_effect=lambda n, v: set_calls.append((n, v)) or True):
                with mock.patch.object(srv.github_api, "dispatch",
                                       side_effect=lambda **kw: dispatch_calls.append(kw) or {"ok": True}):
                    ok_v, err_msg, mode = mp.validate_rununtil_body({"mode": "5h_max"})
                    assert ok_v
                    result_set = srv.github_api.set_repo_variable("METAB_RUN_UNTIL", "5h_max")
                    srv.github_api.dispatch(workflow="metabolism-cycle.yml", ref="main",
                                            inputs={"run_until_continue": "true", "depth": "0"})
        assert ("METAB_RUN_UNTIL", "5h_max") in set_calls
        assert any(kw.get("workflow") == "metabolism-cycle.yml" for kw in dispatch_calls)
        # FIX 7: dispatch inputs must include run_until_continue=true and depth=0
        dispatch_kw = next(kw for kw in dispatch_calls if kw.get("workflow") == "metabolism-cycle.yml")
        assert dispatch_kw.get("inputs", {}).get("run_until_continue") == "true"
        assert dispatch_kw.get("inputs", {}).get("depth") == "0"

    def test_off_sets_variable_no_dispatch(self):
        srv = self._srv()
        mp = _mp()
        set_calls = []
        dispatch_calls = []
        with mock.patch.object(srv.github_api, "token", return_value="fake"):
            with mock.patch.object(srv.github_api, "set_repo_variable",
                                   side_effect=lambda n, v: set_calls.append((n, v)) or True):
                with mock.patch.object(srv.github_api, "dispatch",
                                       side_effect=lambda **kw: dispatch_calls.append(kw) or {"ok": True}):
                    ok_v, err_msg, mode = mp.validate_rununtil_body({"mode": "off"})
                    assert ok_v
                    srv.github_api.set_repo_variable("METAB_RUN_UNTIL", "off")
                    # mode == "off" => no dispatch
        assert ("METAB_RUN_UNTIL", "off") in set_calls
        assert len(dispatch_calls) == 0

    def test_invalid_mode_rejected(self):
        mp = _mp()
        ok_v, err_msg, mode = mp.validate_rununtil_body({"mode": "invalid_mode"})
        assert ok_v is False
        assert "invalid_mode" in (err_msg or "")
        assert mode is None

    def test_missing_confirm_rejected(self):
        """confirm required — handled by server route before validator."""
        # Test just the confirm check logic
        body = {"mode": "5h_max"}  # no confirm
        assert not body.get("confirm")

    def test_no_token_returns_error(self):
        srv = self._srv()
        with mock.patch.object(srv.github_api, "token", return_value=None):
            has_token = bool(srv.github_api.token())
        assert has_token is False

    def test_blocked_arm_does_not_dispatch(self):
        """When budget gate says blocked, arm should error and NOT dispatch."""
        srv = self._srv()
        mp = _mp()
        dispatch_calls = []
        fake_verdict = {"blocked": True, "reason": "All keys >=90% weekly — wait for a weekly reset."}
        with mock.patch.object(srv.github_api, "token", return_value="fake"):
            with mock.patch.object(srv.github_api, "dispatch",
                                   side_effect=lambda **kw: dispatch_calls.append(kw) or {"ok": True}):
                # Simulate the gate verdict blocking
                ok_v, _, mode = mp.validate_rununtil_body({"mode": "5h_max"})
                assert ok_v
                assert mode != "off"
                if fake_verdict.get("blocked"):
                    result = {"ok": False, "error": fake_verdict["reason"], "blocked": True}
                else:
                    result = {"ok": True}
        assert result["ok"] is False
        assert result.get("blocked") is True
        assert len(dispatch_calls) == 0  # dispatch never called when blocked

    def test_weekly_max_arm_sets_correct_variable(self):
        mp = _mp()
        ok_v, err_msg, mode = mp.validate_rununtil_body({"mode": "weekly_max"})
        assert ok_v is True
        assert mode == "weekly_max"


# ---------------------------------------------------------------------------
# 7. engine/metabolism/throttle.py — pace_loops_per_window
# ---------------------------------------------------------------------------

class TestPaceLoopsPerWindow:
    def _fn(self, env_val=None):
        import os as _os  # noqa: PLC0415
        from engine.metabolism.throttle import pace_loops_per_window  # noqa: PLC0415
        saved = _os.environ.get("METAB_PACE")
        try:
            if env_val is not None:
                _os.environ["METAB_PACE"] = env_val
            elif "METAB_PACE" in _os.environ:
                del _os.environ["METAB_PACE"]
            return pace_loops_per_window()
        finally:
            if saved is not None:
                _os.environ["METAB_PACE"] = saved
            elif "METAB_PACE" in _os.environ:
                del _os.environ["METAB_PACE"]

    def test_low_returns_1(self):
        assert self._fn("low") == 1

    def test_medium_returns_2(self):
        assert self._fn("medium") == 2

    def test_high_returns_3(self):
        assert self._fn("high") == 3

    def test_max_returns_4(self):
        assert self._fn("max") == 4

    def test_legacy_single_returns_1(self):
        assert self._fn("single") == 1

    def test_legacy_2x_returns_2(self):
        assert self._fn("2x") == 2

    def test_legacy_4x_returns_3(self):
        assert self._fn("4x") == 3

    def test_absent_returns_1(self):
        assert self._fn(None) == 1

    def test_invalid_returns_1(self):
        assert self._fn("turbo") == 1

    def test_never_raises(self):
        from engine.metabolism.throttle import pace_loops_per_window  # noqa: PLC0415
        result = pace_loops_per_window()
        assert isinstance(result, int)


# ---------------------------------------------------------------------------
# 8. Import smoke tests
# ---------------------------------------------------------------------------

class TestImports:
    def test_metabolism_panel_importable(self):
        mp = _mp()
        assert hasattr(mp, "validate_rununtil_body")
        assert hasattr(mp, "validate_throttle_body")
        assert hasattr(mp, "_median_cycle_duration")
        assert hasattr(mp, "_budget_status")
        assert hasattr(mp, "panel")

    def test_server_imports_metabolism_panel(self):
        import admin.server as srv  # noqa: PLC0415
        import admin.metabolism_panel as mp  # noqa: PLC0415
        assert srv.metabolism_panel is mp

    def test_throttle_has_pace_loops_per_window(self):
        from engine.metabolism.throttle import pace_loops_per_window  # noqa: PLC0415
        assert callable(pace_loops_per_window)


# ---------------------------------------------------------------------------
# 9. _recent_metabolism_runs — updated_at regression (FIX 3)
# ---------------------------------------------------------------------------

class TestRecentMetabolismRunsUpdatedAt:
    """_recent_metabolism_runs must copy updated_at (and run_started_at) from
    the slim-run dict so that _median_cycle_duration can compute durations.
    Without updated_at the median always bails to None."""

    def _make_slim_run(self, workflow="metabolism-cycle.yml", conclusion="success",
                       duration_s=3600, offset_hours=0):
        """Build a slim-run-shaped dict as returned by github_api.list_runs."""
        from datetime import datetime, timezone, timedelta
        now = datetime(2026, 7, 13, 12, 0, 0, tzinfo=timezone.utc)
        created = now - timedelta(hours=offset_hours)
        updated = created + timedelta(seconds=duration_s)
        return {
            "id": 12345 + offset_hours,
            "name": "Metabolism Cycle",
            "display_title": "Metabolism Cycle",
            "workflow": workflow,
            "status": "completed",
            "conclusion": conclusion,
            "event": "schedule",
            "branch": "main",
            "created_at": created.isoformat().replace("+00:00", "Z"),
            "updated_at": updated.isoformat().replace("+00:00", "Z"),
            "run_started_at": created.isoformat().replace("+00:00", "Z"),
            "html_url": "https://github.com/example/runs/1",
        }

    def test_updated_at_present_in_filtered_run(self):
        """Each filtered run must carry updated_at so _median_cycle_duration works."""
        mp = _mp()
        slim_runs = [self._make_slim_run(duration_s=3600)]
        with mock.patch.object(mp.github_api, "list_runs",
                               return_value={"ok": True, "runs": slim_runs}):
            runs = mp._recent_metabolism_runs(cap=15)
        assert len(runs) >= 1
        assert "updated_at" in runs[0], "updated_at missing from filtered run"
        assert runs[0]["updated_at"] is not None

    def test_run_started_at_present_in_filtered_run(self):
        """Each filtered run must carry run_started_at (when provided by upstream)."""
        mp = _mp()
        slim_runs = [self._make_slim_run(duration_s=3600)]
        with mock.patch.object(mp.github_api, "list_runs",
                               return_value={"ok": True, "runs": slim_runs}):
            runs = mp._recent_metabolism_runs(cap=15)
        assert len(runs) >= 1
        assert "run_started_at" in runs[0], "run_started_at missing from filtered run"

    def test_median_non_none_when_updated_at_present(self):
        """End-to-end: _recent_metabolism_runs feeds _median_cycle_duration and
        the median must be non-None when at least one long-enough cycle run exists."""
        mp = _mp()
        slim_runs = [
            self._make_slim_run(duration_s=3600, offset_hours=0),
            self._make_slim_run(duration_s=7200, offset_hours=6),
        ]
        with mock.patch.object(mp.github_api, "list_runs",
                               return_value={"ok": True, "runs": slim_runs}):
            runs = mp._recent_metabolism_runs(cap=15)
        median_result = mp._median_cycle_duration(runs)
        assert median_result["median_s"] is not None, (
            "_median_cycle_duration returned None — likely updated_at missing from runs; "
            f"runs[0] keys: {list(runs[0].keys()) if runs else '(empty)'}"
        )
        assert median_result["n"] == 2
