"""Tests for refresh_trial_log (W5 surgical trial-log refresh).

Verifies that refresh_trial_log:
  - reads calibration.json for variant/family names
  - reads trial_log.json for the existing asof date (leaves it unchanged)
  - uses current config for cost_bps and n_trials
  - computes n_declared = n_trials + sum(override dof)
  - writes the new trial_log.json with all required keys
  - does NOT touch calibration.json
"""
from __future__ import annotations

import json
import sys
import types
from datetime import date
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
FIXTURE_CALIBRATION = {
    "allocation": {"optimal": {}, "moderate": {}},
    "signals": {"mvrv_z": {}, "puell": {}},
}

FIXTURE_TRIAL_LOG = {
    "asof": "2026-06-13",
    "n_trials_declared": 50,
    "cost_bps_one_way": 10.0,
    "note": "old note",
}

# Config the stub will return
_STUB_CFG = {
    "vector": {
        "calibration": {"n_trials": 65, "cost_bps": 10.0},
        "allocation": {"midterm_gate": {"enabled": True}},
        # No "overrides" key → triggers legacy fallback (_W0_MIDTERM_DOF = 3)
    }
}


# ---------------------------------------------------------------------------
# Patching helpers
# ---------------------------------------------------------------------------
def _make_stub_ledger():
    """A no-op TrialLedger that accepts log_declared_budget without touching disk."""
    class _StubLedger:
        def __init__(self, *a, **kw):
            pass
        def log_declared_budget(self, *a, **kw):
            return True
        def effective_n(self, *a, **kw):
            return 68
    return _StubLedger


@pytest.fixture()
def tmp_vector(tmp_path):
    """Write fixture files and return the tmp dir root."""
    vec = tmp_path / "data" / "vector"
    vec.mkdir(parents=True)
    (vec / "calibration.json").write_text(json.dumps(FIXTURE_CALIBRATION))
    (vec / "trial_log.json").write_text(json.dumps(FIXTURE_TRIAL_LOG))
    return tmp_path


# ---------------------------------------------------------------------------
# The test
# ---------------------------------------------------------------------------
def test_refresh_trial_log(tmp_vector, monkeypatch):
    # Patch lib.config so refresh_trial_log sees our stub cfg and tmp data_dir
    stub_config = types.ModuleType("lib.config")
    stub_config.load = lambda: _STUB_CFG
    stub_config.data_dir = lambda: tmp_vector / "data"

    # Patch engine.trial_ledger.TrialLedger to the no-op stub
    stub_ledger_mod = types.ModuleType("engine.trial_ledger")
    stub_ledger_mod.TrialLedger = _make_stub_ledger()

    import lib  # ensure lib package is importable
    import engine  # ensure engine package is importable

    monkeypatch.setitem(sys.modules, "lib.config", stub_config)
    monkeypatch.setitem(sys.modules, "engine.trial_ledger", stub_ledger_mod)

    # Also patch the names as they appear inside calibrate_vector's module namespace
    import scripts.calibrate_vector as cv_mod
    monkeypatch.setattr(cv_mod, "config", stub_config, raising=True)
    monkeypatch.setattr(cv_mod, "TrialLedger", _make_stub_ledger(), raising=True)

    # Record calibration.json bytes before the call
    cal_path = tmp_vector / "data" / "vector" / "calibration.json"
    cal_bytes_before = cal_path.read_bytes()

    result = cv_mod.refresh_trial_log(root=tmp_vector / "data")

    # --- assertions on returned dict ---
    assert result["n_trials_config"] == 65
    assert result["overrides_dof"] == {"midterm_blackout": 3}   # legacy fallback
    assert result["n_trials_declared"] == 68                    # 65 + 3
    assert result["asof"] == "2026-06-13"                       # unchanged
    assert "refreshed_on" in result
    assert result["refreshed_on"] == date.today().isoformat()
    assert "refresh_note" in result
    assert "fdr_note" in result

    # --- written file matches returned dict ---
    tl_path = tmp_vector / "data" / "vector" / "trial_log.json"
    on_disk = json.loads(tl_path.read_text())
    assert on_disk["n_trials_config"] == 65
    assert on_disk["overrides_dof"] == {"midterm_blackout": 3}
    assert on_disk["n_trials_declared"] == 68
    assert on_disk["asof"] == "2026-06-13"
    assert "refreshed_on" in on_disk

    # --- calibration.json MUST be untouched ---
    assert cal_path.read_bytes() == cal_bytes_before, (
        "refresh_trial_log must not write calibration.json"
    )
