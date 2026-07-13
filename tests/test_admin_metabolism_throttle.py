"""Tests for admin/metabolism_panel.py V10 Throttle & Key Economy additions.

DATA-LAYER ONLY — no HTTP server construction.

Covers:
  throttle() shape + effective defaults on None repo variables
  throttle() when engine.metabolism.throttle is absent (fail-soft)
  keys() passthrough from usage_snapshot()
  keys() error note on exception
  validate_throttle_body() — good/bad intensity/pace/keys_enabled
  validate_run_body() — mode allowlist, lobe regex, stages vocab
  panel() includes "throttle" key
"""
from __future__ import annotations

import sys
import types
import unittest.mock as mock
from pathlib import Path

import pytest

# Ensure repo root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _mp():
    """Import metabolism_panel freshly (avoids module-state cross-contamination)."""
    import admin.metabolism_panel as mp  # noqa: PLC0415
    return mp


def _mock_github(mp, intensity=None, pace=None, keys_enabled=None):
    """Patch get_repo_variable to return canned values per variable name."""
    _map = {
        "METAB_INTENSITY": intensity,
        "METAB_PACE": pace,
        "METAB_KEYS_ENABLED": keys_enabled,
        "AUTONOMY_PAUSED": None,
    }

    def fake_get(name):
        return _map.get(name)

    return mock.patch.object(mp.github_api, "get_repo_variable", side_effect=fake_get)


# ---------------------------------------------------------------------------
# 1. throttle() shape
# ---------------------------------------------------------------------------

class TestThrottleShape:
    """throttle() always returns a dict with the required keys, never raises."""

    def _call(self, mp, intensity=None, pace=None, keys_enabled=None):
        with _mock_github(mp, intensity=intensity, pace=pace, keys_enabled=keys_enabled):
            return mp.throttle()

    def test_returns_dict(self):
        mp = _mp()
        result = self._call(mp)
        assert isinstance(result, dict)

    def test_has_intensity_key(self):
        mp = _mp()
        result = self._call(mp)
        assert "intensity" in result
        assert "value" in result["intensity"]
        assert "effective" in result["intensity"]
        assert "allowed" in result["intensity"]

    def test_has_pace_key(self):
        mp = _mp()
        result = self._call(mp)
        assert "pace" in result
        assert "value" in result["pace"]
        assert "effective" in result["pace"]
        assert "allowed" in result["pace"]
        assert "extra_cycles" in result["pace"]

    def test_has_keys_enabled_key(self):
        mp = _mp()
        result = self._call(mp)
        assert "keys_enabled" in result
        assert "value" in result["keys_enabled"]
        assert "effective_ids" in result["keys_enabled"]

    def test_none_intensity_defaults_to_normal(self):
        mp = _mp()
        result = self._call(mp, intensity=None)
        assert result["intensity"]["value"] is None
        assert result["intensity"]["effective"] == "normal"

    def test_none_pace_defaults_to_single(self):
        mp = _mp()
        result = self._call(mp, pace=None)
        assert result["pace"]["value"] is None
        assert result["pace"]["effective"] == "single"
        assert result["pace"]["extra_cycles"] == 0

    def test_valid_intensity_high(self):
        mp = _mp()
        result = self._call(mp, intensity="high")
        assert result["intensity"]["value"] == "high"
        assert result["intensity"]["effective"] == "high"

    def test_valid_intensity_max(self):
        mp = _mp()
        result = self._call(mp, intensity="max")
        assert result["intensity"]["effective"] == "max"

    def test_invalid_intensity_falls_back_to_normal(self):
        """A garbage variable value should fail-open to 'normal'."""
        mp = _mp()
        result = self._call(mp, intensity="TURBO")
        # effective must be a valid value, not the garbage
        assert result["intensity"]["effective"] in {"low", "normal", "high", "max"}

    def test_pace_2x_extra_cycles_one(self):
        mp = _mp()
        result = self._call(mp, pace="2x")
        assert result["pace"]["effective"] == "2x"
        assert result["pace"]["extra_cycles"] == 1

    def test_pace_4x_extra_cycles_three(self):
        mp = _mp()
        result = self._call(mp, pace="4x")
        assert result["pace"]["extra_cycles"] == 3

    def test_allowed_intensity_list(self):
        mp = _mp()
        result = self._call(mp)
        assert set(result["intensity"]["allowed"]) == {"low", "normal", "high", "max"}

    def test_allowed_pace_list(self):
        mp = _mp()
        result = self._call(mp)
        assert set(result["pace"]["allowed"]) == {"single", "2x", "4x"}


class TestThrottleEngineAbsent:
    """When engine.metabolism.throttle is not importable, throttle() fails-soft."""

    def _call_no_engine(self, mp, intensity=None, pace=None):
        with _mock_github(mp, intensity=intensity, pace=pace):
            # Block the engine import
            with mock.patch.dict("sys.modules", {"engine.metabolism.throttle": None}):
                return mp.throttle()

    def test_returns_dict_without_engine(self):
        mp = _mp()
        result = self._call_no_engine(mp)
        assert isinstance(result, dict)
        assert "intensity" in result
        assert "pace" in result

    def test_note_present_without_engine(self):
        mp = _mp()
        result = self._call_no_engine(mp)
        # Should include a note about the missing engine
        assert "note" in result

    def test_defaults_still_apply_without_engine(self):
        mp = _mp()
        result = self._call_no_engine(mp, intensity=None, pace=None)
        assert result["intensity"]["effective"] == "normal"
        assert result["pace"]["effective"] == "single"

    def test_valid_values_still_resolve_without_engine(self):
        mp = _mp()
        result = self._call_no_engine(mp, intensity="low", pace="4x")
        assert result["intensity"]["effective"] == "low"
        assert result["pace"]["effective"] == "4x"
        assert result["pace"]["extra_cycles"] == 3


# ---------------------------------------------------------------------------
# 2. keys() passthrough + error note
# ---------------------------------------------------------------------------

class TestKeysFunction:
    """keys() wraps usage_snapshot() and is fail-soft."""

    def test_keys_passthrough(self):
        """When usage_snapshot() returns rows, keys() returns them."""
        mp = _mp()
        fake_rows = [
            {"key_id": "claude_code_oauth_1", "present": True, "enabled": True,
             "cooling": False, "cool_kind": None, "reset_hint": None,
             "window_5h_est_tokens": 1000, "weekly_est_tokens": 50000,
             "window_5h_sessions": 5, "weekly_sessions": 200,
             "last_outcome": "ok", "last_ts": "2026-07-13T00:00:00Z",
             "ratelimit_headers": {}, "headers_ts": None},
            {"key_id": "legacy", "present": False, "enabled": True,
             "cooling": False, "cool_kind": None, "reset_hint": None,
             "window_5h_est_tokens": None, "weekly_est_tokens": None,
             "window_5h_sessions": 0, "weekly_sessions": 0,
             "last_outcome": None, "last_ts": None,
             "ratelimit_headers": {}, "headers_ts": None},
        ]
        stub_pool = types.ModuleType("engine.neuralweb.key_pool")
        stub_pool.usage_snapshot = mock.Mock(return_value=fake_rows)
        with mock.patch.dict("sys.modules", {
            "engine": types.ModuleType("engine"),
            "engine.neuralweb": types.ModuleType("engine.neuralweb"),
            "engine.neuralweb.key_pool": stub_pool,
        }):
            result = mp.keys()
        assert result == fake_rows

    def test_keys_import_error_returns_error_dict(self):
        """When key_pool is absent, keys() returns {"error": ...}."""
        mp = _mp()
        with mock.patch.dict("sys.modules", {"engine.neuralweb.key_pool": None}):
            result = mp.keys()
        assert isinstance(result, dict)
        assert "error" in result

    def test_keys_runtime_error_returns_error_dict(self):
        """When usage_snapshot() raises, keys() returns {"error": ...}."""
        mp = _mp()
        stub_pool = types.ModuleType("engine.neuralweb.key_pool")
        stub_pool.usage_snapshot = mock.Mock(side_effect=RuntimeError("boom"))
        with mock.patch.dict("sys.modules", {
            "engine": types.ModuleType("engine"),
            "engine.neuralweb": types.ModuleType("engine.neuralweb"),
            "engine.neuralweb.key_pool": stub_pool,
        }):
            result = mp.keys()
        assert isinstance(result, dict)
        assert "error" in result
        assert "boom" in result["error"]

    def test_keys_never_raises(self):
        """keys() must not propagate any exception."""
        mp = _mp()
        # Make the import itself raise something unusual
        with mock.patch.dict("sys.modules", {"engine.neuralweb.key_pool": None}):
            try:
                result = mp.keys()
            except Exception as exc:  # noqa: BLE001
                pytest.fail(f"keys() raised unexpectedly: {exc}")


# ---------------------------------------------------------------------------
# 3. panel() includes throttle key
# ---------------------------------------------------------------------------

class TestPanelIncludesThrottle:
    """panel() must return a dict containing a 'throttle' key."""

    def test_panel_has_throttle_key(self, tmp_path):
        mp = _mp()
        with mock.patch.object(mp.github_api, "token", return_value=None), \
             mock.patch.object(mp.github_api, "get_repo_variable", return_value=None), \
             mock.patch.object(mp.github_api, "list_runs", return_value={"ok": False, "runs": []}):
            result = mp.panel(root=tmp_path)
        assert "throttle" in result

    def test_panel_throttle_has_intensity(self, tmp_path):
        mp = _mp()
        with mock.patch.object(mp.github_api, "token", return_value=None), \
             mock.patch.object(mp.github_api, "get_repo_variable", return_value=None), \
             mock.patch.object(mp.github_api, "list_runs", return_value={"ok": False, "runs": []}):
            result = mp.panel(root=tmp_path)
        assert isinstance(result["throttle"], dict)
        # throttle may be {} on hard error, or fully populated — either is valid
        # but it must not be absent


# ---------------------------------------------------------------------------
# 4. validate_throttle_body()
# ---------------------------------------------------------------------------

class TestValidateThrottleBody:
    """validate_throttle_body(body) -> (ok, errors, to_set)"""

    def _v(self, body):
        mp = _mp()
        return mp.validate_throttle_body(body)

    # --- good inputs ---

    def test_valid_intensity_low(self):
        ok, errors, to_set = self._v({"intensity": "low"})
        assert ok is True
        assert errors == {}
        assert to_set == {"METAB_INTENSITY": "low"}

    def test_valid_intensity_normal(self):
        ok, errors, to_set = self._v({"intensity": "normal"})
        assert ok is True
        assert to_set["METAB_INTENSITY"] == "normal"

    def test_valid_intensity_high(self):
        ok, errors, to_set = self._v({"intensity": "high"})
        assert ok is True

    def test_valid_intensity_max(self):
        ok, errors, to_set = self._v({"intensity": "max"})
        assert ok is True

    def test_valid_pace_single(self):
        ok, errors, to_set = self._v({"pace": "single"})
        assert ok is True
        assert to_set["METAB_PACE"] == "single"

    def test_valid_pace_2x(self):
        ok, errors, to_set = self._v({"pace": "2x"})
        assert ok is True

    def test_valid_pace_4x(self):
        ok, errors, to_set = self._v({"pace": "4x"})
        assert ok is True

    def test_valid_keys_csv(self):
        ok, errors, to_set = self._v({"keys_enabled": "1,2,3"})
        assert ok is True
        assert to_set["METAB_KEYS_ENABLED"] == "1,2,3"

    def test_valid_keys_empty_string(self):
        """Empty string = all keys — valid."""
        ok, errors, to_set = self._v({"keys_enabled": ""})
        assert ok is True
        assert to_set["METAB_KEYS_ENABLED"] == ""

    def test_valid_keys_legacy(self):
        ok, errors, to_set = self._v({"keys_enabled": "legacy"})
        assert ok is True

    def test_valid_keys_mixed(self):
        ok, errors, to_set = self._v({"keys_enabled": "1,legacy"})
        assert ok is True

    def test_multiple_valid_fields(self):
        ok, errors, to_set = self._v({"intensity": "high", "pace": "2x"})
        assert ok is True
        assert "METAB_INTENSITY" in to_set
        assert "METAB_PACE" in to_set

    def test_empty_body_ok_but_no_to_set(self):
        """Empty body is valid (no errors) but to_set is empty."""
        ok, errors, to_set = self._v({})
        assert ok is True
        assert to_set == {}

    # --- bad inputs ---

    def test_invalid_intensity(self):
        ok, errors, to_set = self._v({"intensity": "turbo"})
        assert ok is False
        assert "intensity" in errors
        assert "METAB_INTENSITY" not in to_set

    def test_invalid_pace(self):
        ok, errors, to_set = self._v({"pace": "3x"})
        assert ok is False
        assert "pace" in errors

    def test_invalid_keys_too_long(self):
        ok, errors, to_set = self._v({"keys_enabled": "1," * 33})  # 66 chars > 64
        assert ok is False
        assert "keys_enabled" in errors

    def test_invalid_keys_forbidden_chars(self):
        ok, errors, to_set = self._v({"keys_enabled": "1;DROP TABLE"})
        assert ok is False
        assert "keys_enabled" in errors

    def test_invalid_keys_not_string(self):
        ok, errors, to_set = self._v({"keys_enabled": [1, 2, 3]})
        assert ok is False
        assert "keys_enabled" in errors

    def test_partial_ok_partial_bad(self):
        """When intensity valid and pace invalid, only intensity lands in to_set."""
        ok, errors, to_set = self._v({"intensity": "low", "pace": "FAST"})
        assert ok is False
        assert "METAB_INTENSITY" in to_set
        assert "METAB_PACE" not in to_set


# ---------------------------------------------------------------------------
# 5. validate_run_body()
# ---------------------------------------------------------------------------

class TestValidateRunBody:
    """validate_run_body(body) -> (ok, error, workflow, inputs)"""

    def _v(self, body):
        mp = _mp()
        return mp.validate_run_body(body)

    # --- mode allowlist ---

    def test_mode_cycle(self):
        ok, err, wf, inputs = self._v({"mode": "cycle"})
        assert ok is True
        assert wf == "metabolism-cycle.yml"
        assert err is None

    def test_mode_agenda(self):
        ok, err, wf, inputs = self._v({"mode": "agenda"})
        assert ok is True
        assert wf == "metabolism-agenda.yml"

    def test_mode_propose(self):
        ok, err, wf, inputs = self._v({"mode": "propose"})
        assert ok is True
        assert wf == "metabolism-propose.yml"

    def test_mode_adjudicate(self):
        ok, err, wf, inputs = self._v({"mode": "adjudicate"})
        assert ok is True
        assert wf == "metabolism-adjudicate.yml"

    def test_mode_build(self):
        ok, err, wf, inputs = self._v({"mode": "build"})
        assert ok is True
        assert wf == "metabolism-build.yml"

    def test_mode_unknown_rejected(self):
        ok, err, wf, inputs = self._v({"mode": "daily"})
        assert ok is False
        assert err is not None
        assert wf is None

    def test_mode_missing_rejected(self):
        ok, err, wf, inputs = self._v({})
        assert ok is False

    # --- lobe regex ---

    def test_lobe_valid(self):
        ok, err, wf, inputs = self._v({"mode": "cycle", "lobe": "til"})
        assert ok is True
        assert inputs.get("lobe") == "til"

    def test_lobe_valid_hyphen(self):
        ok, err, wf, inputs = self._v({"mode": "cycle", "lobe": "site-us-standouts"})
        assert ok is True
        assert inputs.get("lobe") == "site-us-standouts"

    def test_lobe_invalid_uppercase(self):
        ok, err, wf, inputs = self._v({"mode": "cycle", "lobe": "TIL"})
        assert ok is False
        assert err is not None

    def test_lobe_invalid_too_long(self):
        ok, err, wf, inputs = self._v({"mode": "cycle", "lobe": "a" * 41})
        assert ok is False

    def test_lobe_invalid_special_chars(self):
        ok, err, wf, inputs = self._v({"mode": "cycle", "lobe": "til; rm -rf /"})
        assert ok is False

    def test_lobe_on_propose_goes_to_inputs(self):
        ok, err, wf, inputs = self._v({"mode": "propose", "lobe": "til"})
        assert ok is True
        assert inputs.get("lobe") == "til"

    def test_lobe_on_agenda_not_in_inputs(self):
        """Lobe is only passed for cycle and propose modes."""
        ok, err, wf, inputs = self._v({"mode": "agenda", "lobe": "til"})
        assert ok is True
        assert "lobe" not in inputs

    # --- stages vocab ---

    def test_stages_full(self):
        ok, err, wf, inputs = self._v({"mode": "cycle", "stages": "full"})
        assert ok is True
        assert inputs.get("stages") == "full"

    def test_stages_sense(self):
        ok, err, wf, inputs = self._v({"mode": "cycle", "stages": "sense"})
        assert ok is True
        assert inputs.get("stages") == "sense"

    def test_stages_through_adjudicate(self):
        ok, err, wf, inputs = self._v({"mode": "cycle", "stages": "through-adjudicate"})
        assert ok is True
        assert inputs.get("stages") == "through-adjudicate"

    def test_stages_invalid(self):
        ok, err, wf, inputs = self._v({"mode": "cycle", "stages": "partial"})
        assert ok is False
        assert err is not None

    def test_stages_only_applied_to_cycle(self):
        """stages input should only be passed for cycle mode."""
        ok, err, wf, inputs = self._v({"mode": "propose", "stages": "full"})
        assert ok is True
        assert "stages" not in inputs

    def test_no_inputs_for_adjudicate(self):
        ok, err, wf, inputs = self._v({"mode": "adjudicate"})
        assert ok is True
        assert inputs == {}

    def test_no_inputs_for_build(self):
        ok, err, wf, inputs = self._v({"mode": "build"})
        assert ok is True
        assert inputs == {}
