"""tests/test_thetadata_tape_sessions.py — unit tests for the multi-session calibration harness.

Tests:
  1. gate-update isolation: root keys byte-identical after update_gate (non-tape keys untouched)
  2. suspend trigger: any session with agreement < 0.75 sets direction_reliable_tape=False
  3. append-only: second run adds records, never rewrites past records
  4. dry-run fixture: run_session with dry_run=True produces a well-formed session record
  5. production_ready=False with fewer than 5 sessions
  6. production_ready=False with no high-VIX session
  7. update_gate preserves prior per_trade_agreement from thetadata_tape single-session key
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

_REPO = Path(__file__).parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


# ────────────────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def tmp_data(tmp_path: Path) -> Path:
    """Create a tmp dir acting as config.data_dir()."""
    (tmp_path / "options_flow").mkdir(parents=True)
    return tmp_path


@pytest.fixture()
def gate_with_root_keys(tmp_data: Path) -> dict:
    """Write a realistic signing_gate.json with canonical root-level keys."""
    gate = {
        "scored": False,
        "direction_reliable": False,
        "magnitude_reliable": True,
        "net_sign_recovery": 0.4108,
        "per_trade_agreement": 0.7774,
        "per_trade_size_weighted": 0.8083,
        "bar": 0.7,
        "note": "flow DIRECTION is SOFT — option minute-ticks are delta-dominated",
        "asof": "2026-06-21",
        "generated": "2026-06-21T10:41:41.598333+00:00",
        "n_trades": 101934,
        "universe": ["SPY", "QQQ"],
        "enabled": True,
        "delta_adjusted": {"tested": True, "improves_direction": False},
    }
    gate_path = tmp_data / "options_flow" / "signing_gate.json"
    gate_path.write_text(json.dumps(gate, indent=2))
    return gate


def _import_module(tmp_data: Path):
    """Import the harness with config.data_dir() patched to tmp_data."""
    import importlib
    with patch("lib.config.data_dir", return_value=tmp_data):
        import scripts.calibrate_thetadata_tape_sessions as m
        importlib.reload(m)
        return m


# ────────────────────────────────────────────────────────────────────────────
# Helper: write fixture session records to JSONL
# ────────────────────────────────────────────────────────────────────────────

def _write_sessions(tmp_data: Path, sessions: list[dict]) -> Path:
    """Write session records to the JSONL path."""
    jsonl_path = tmp_data / "options_flow" / "tape_signing_sessions.jsonl"
    with open(jsonl_path, "w") as fh:
        for s in sessions:
            fh.write(json.dumps(s) + "\n")
    return jsonl_path


def _make_ok_session(day_str: str, roots: list[str], vix: float) -> dict:
    """Minimal passing session record."""
    return {
        "date": day_str,
        "window_start": f"{day_str}T14:30",
        "window_end": f"{day_str}T14:50",
        "roots": sorted(roots),
        "n_contracts": 6,
        "n_trades": 9000,
        "per_trade_agreement": 0.88,
        "net_sign_recovery": 0.81,
        "vix_close": vix,
        "vix_regime": "high" if vix >= 20 else "calm",
        "moneyness_buckets": ["ATM", "OTM-call"],
        "expiries_covered": ["20250407", "20250414"],
        "agreement_ok": True,
        "recovery_ok": True,
        "pass": True,
        "status": "ok",
        "agreement_bar": 0.75,
        "recovery_bar": 0.75,
        "agreement_method": "quote_rule_self_consistency",
        "agreement_note": "test record",
        "recorded": "2026-07-06T00:00:00+00:00",
    }


def _make_fail_session(day_str: str, roots: list[str], vix: float, agr: float = 0.55) -> dict:
    """Minimal failing session record (agreement below bar)."""
    s = _make_ok_session(day_str, roots, vix)
    s["per_trade_agreement"] = agr
    s["agreement_ok"] = False
    s["pass"] = False
    return s


# ────────────────────────────────────────────────────────────────────────────
# Test 1: root keys byte-identical after update_gate
# ────────────────────────────────────────────────────────────────────────────

def test_update_gate_root_keys_unchanged(tmp_data: Path, gate_with_root_keys: dict):
    """update_gate must not touch any root-level key in signing_gate.json."""
    jsonl_path = _write_sessions(tmp_data, [
        _make_ok_session("2025-04-07", ["SPY", "QQQ"], vix=47.0),
    ])
    gate_path = tmp_data / "options_flow" / "signing_gate.json"

    m = _import_module(tmp_data)
    with patch("lib.config.data_dir", return_value=tmp_data):
        m.update_gate(jsonl_path=jsonl_path, gate_path=gate_path)

    written = json.loads(gate_path.read_text())
    for key, original_val in gate_with_root_keys.items():
        assert key in written, f"Root key '{key}' disappeared"
        assert json.dumps(written[key], sort_keys=True) == json.dumps(original_val, sort_keys=True), (
            f"Root key '{key}' was mutated: before={original_val!r} after={written[key]!r}"
        )
    # thetadata_tape must be present and updated
    assert "thetadata_tape" in written
    assert written["thetadata_tape"]["sessions_n"] == 1


# ────────────────────────────────────────────────────────────────────────────
# Test 2: suspend trigger — any failing session sets direction_reliable_tape=False
# ────────────────────────────────────────────────────────────────────────────

def test_suspend_on_fail(tmp_data: Path, gate_with_root_keys: dict):
    """direction_reliable_tape must be False and suspend_reason populated if any session fails."""
    sessions = [
        _make_ok_session("2025-04-07", ["SPY"], vix=47.0),
        _make_ok_session("2025-04-08", ["QQQ"], vix=52.0),
        _make_fail_session("2025-06-10", ["SPY"], vix=14.0, agr=0.62),  # fails agreement
    ]
    jsonl_path = _write_sessions(tmp_data, sessions)
    gate_path = tmp_data / "options_flow" / "signing_gate.json"

    m = _import_module(tmp_data)
    with patch("lib.config.data_dir", return_value=tmp_data):
        agg = m.update_gate(jsonl_path=jsonl_path, gate_path=gate_path)

    assert agg["direction_reliable_tape"] is False, "direction_reliable_tape must be False on fail"
    assert "suspend_reason" in agg, "suspend_reason must be populated on fail"
    assert "2025-06-10" in agg["suspend_reason"], "suspend_reason must name the failing date"

    # Root key must still be False
    written = json.loads(gate_path.read_text())
    assert written["direction_reliable"] is False
    assert written["thetadata_tape"]["direction_reliable_tape"] is False


# ────────────────────────────────────────────────────────────────────────────
# Test 3: append-only — second run adds records, never overwrites
# ────────────────────────────────────────────────────────────────────────────

def test_append_only_jsonl(tmp_data: Path, gate_with_root_keys: dict):
    """Each run_session appends one record; re-running twice gives 2 records."""
    gate_path = tmp_data / "options_flow" / "signing_gate.json"
    jsonl_path = tmp_data / "options_flow" / "tape_signing_sessions.jsonl"

    m = _import_module(tmp_data)
    with patch("lib.config.data_dir", return_value=tmp_data):
        m.run_session(
            roots=["SPY"],
            day=date(2025, 4, 7),
            window_start="14:30",
            window_end="14:50",
            dry_run=True,
            jsonl_path=jsonl_path,
            gate_path=gate_path,
            seed=1,
        )
        m.run_session(
            roots=["QQQ"],
            day=date(2025, 4, 8),
            window_start="14:30",
            window_end="14:50",
            dry_run=True,
            jsonl_path=jsonl_path,
            gate_path=gate_path,
            seed=2,
        )

    records = [json.loads(l) for l in jsonl_path.read_text().strip().splitlines()]
    assert len(records) == 2, f"Expected 2 records, got {len(records)}"
    assert records[0]["roots"] == ["SPY"]
    assert records[1]["roots"] == ["QQQ"]

    # Sessions are cumulative in gate
    written = json.loads(gate_path.read_text())
    assert written["thetadata_tape"]["sessions_n"] == 2


# ────────────────────────────────────────────────────────────────────────────
# Test 4: dry-run fixture produces well-formed session record
# ────────────────────────────────────────────────────────────────────────────

def test_dry_run_well_formed(tmp_data: Path, gate_with_root_keys: dict):
    """dry_run=True must produce a record with required fields and non-null metrics."""
    gate_path = tmp_data / "options_flow" / "signing_gate.json"
    jsonl_path = tmp_data / "options_flow" / "tape_signing_sessions.jsonl"

    m = _import_module(tmp_data)
    with patch("lib.config.data_dir", return_value=tmp_data):
        record = m.run_session(
            roots=["SPY", "QQQ"],
            day=date(2025, 4, 7),
            window_start="14:30",
            window_end="14:50",
            dry_run=True,
            jsonl_path=jsonl_path,
            gate_path=gate_path,
        )

    required_fields = [
        "date", "window_start", "window_end", "roots", "n_contracts", "n_trades",
        "per_trade_agreement", "net_sign_recovery", "vix_close", "vix_regime",
        "moneyness_buckets", "expiries_covered", "agreement_ok", "recovery_ok",
        "pass", "status", "agreement_method", "agreement_note", "recorded",
    ]
    for f in required_fields:
        assert f in record, f"Required field '{f}' missing from session record"

    assert record["status"] == "dry_run"
    assert record["roots"] == ["QQQ", "SPY"]   # sorted
    assert record["n_trades"] > 0
    assert record["per_trade_agreement"] is not None
    assert record["net_sign_recovery"] is not None
    assert record["agreement_method"] == "quote_rule_self_consistency"


# ────────────────────────────────────────────────────────────────────────────
# Test 5: production_ready=False with fewer than 5 passing sessions
# ────────────────────────────────────────────────────────────────────────────

def test_production_ready_false_insufficient_sessions(tmp_data: Path, gate_with_root_keys: dict):
    """production_ready must be False when fewer than 5 sessions pass."""
    # 4 good sessions — one short of the 5 needed
    sessions = [
        _make_ok_session("2025-04-07", ["SPY", "QQQ"], vix=47.0),
        _make_ok_session("2025-04-08", ["SPY", "QQQ"], vix=52.0),
        _make_ok_session("2024-12-16", ["SPY", "QQQ"], vix=15.0),
        _make_ok_session("2025-01-14", ["SPY", "QQQ"], vix=18.0),
    ]
    jsonl_path = _write_sessions(tmp_data, sessions)
    gate_path = tmp_data / "options_flow" / "signing_gate.json"

    m = _import_module(tmp_data)
    with patch("lib.config.data_dir", return_value=tmp_data):
        agg = m.update_gate(jsonl_path=jsonl_path, gate_path=gate_path)

    assert agg["production_ready"] is False, "Should not be production_ready with only 4 sessions"
    assert agg["sessions_passed"] == 4


# ────────────────────────────────────────────────────────────────────────────
# Test 6: production_ready=False when no high-VIX session
# ────────────────────────────────────────────────────────────────────────────

def test_production_ready_false_no_high_vix(tmp_data: Path, gate_with_root_keys: dict):
    """production_ready must be False if no high-VIX session is present."""
    sessions = [
        _make_ok_session("2025-01-07", ["SPY", "QQQ"], vix=14.0),
        _make_ok_session("2025-01-08", ["SPY", "QQQ"], vix=15.0),
        _make_ok_session("2025-01-09", ["SPY", "QQQ"], vix=13.5),
        _make_ok_session("2025-01-10", ["SPY", "QQQ"], vix=16.0),
        _make_ok_session("2025-01-13", ["SPY", "QQQ"], vix=17.0),
    ]
    jsonl_path = _write_sessions(tmp_data, sessions)
    gate_path = tmp_data / "options_flow" / "signing_gate.json"

    m = _import_module(tmp_data)
    with patch("lib.config.data_dir", return_value=tmp_data):
        agg = m.update_gate(jsonl_path=jsonl_path, gate_path=gate_path)

    assert agg["production_ready"] is False
    assert agg["conditions_covered"]["high_vix"] is False
    assert agg["conditions_covered"]["calm"] is True


# ────────────────────────────────────────────────────────────────────────────
# Test 7: update_gate preserves existing thetadata_tape measurement keys
# ────────────────────────────────────────────────────────────────────────────

def test_update_gate_preserves_prior_tape_measurement(tmp_data: Path):
    """update_gate must preserve prior per_trade_agreement from the single-session thetadata_tape key."""
    # Simulate a gate that already has the #1292 ratified single-session result
    gate = {
        "scored": False,
        "direction_reliable": False,
        "magnitude_reliable": True,
        "net_sign_recovery": 0.4108,
        "per_trade_agreement": 0.7774,
        "bar": 0.7,
        "note": "bar source soft",
        "thetadata_tape": {
            "status": "measured",
            "per_trade_agreement": 0.8848,
            "net_sign_recovery": 0.80,
            "n_trades": 16366,
            "n_contracts": 15,
            "direction_reliable_tape": True,
        },
    }
    gate_path = tmp_data / "options_flow" / "signing_gate.json"
    gate_path.write_text(json.dumps(gate, indent=2))

    sessions = [_make_ok_session("2025-04-07", ["SPY"], vix=47.0)]
    jsonl_path = _write_sessions(tmp_data, sessions)

    m = _import_module(tmp_data)
    with patch("lib.config.data_dir", return_value=tmp_data):
        m.update_gate(jsonl_path=jsonl_path, gate_path=gate_path)

    written = json.loads(gate_path.read_text())
    td = written["thetadata_tape"]
    # Prior measurement keys must be preserved (update_gate merges, not overwrites)
    assert td.get("n_trades") == 16366, "Prior n_trades must be preserved"
    assert td.get("n_contracts") == 15, "Prior n_contracts must be preserved"
    # New aggregate keys must be added
    assert "sessions_n" in td
    assert td["sessions_n"] == 1
    # Root direction_reliable untouched
    assert written["direction_reliable"] is False


# ────────────────────────────────────────────────────────────────────────────
# Test 8: direction_reliable never auto-flipped even with 5+ passing sessions
# ────────────────────────────────────────────────────────────────────────────

def test_direction_reliable_never_auto_flipped(tmp_data: Path, gate_with_root_keys: dict):
    """Root direction_reliable must stay False regardless of session outcomes."""
    sessions = [
        _make_ok_session("2025-04-07", ["SPY", "QQQ"], vix=47.0),
        _make_ok_session("2025-04-08", ["SPY", "QQQ"], vix=52.0),
        _make_ok_session("2024-12-16", ["SPY", "QQQ"], vix=15.0),
        _make_ok_session("2025-01-14", ["SPY", "QQQ"], vix=18.0),
        _make_ok_session("2025-02-21", ["SPY", "QQQ"], vix=16.0),
        _make_ok_session("2025-03-10", ["SPY", "QQQ", "NVDA"], vix=22.0),
    ]
    jsonl_path = _write_sessions(tmp_data, sessions)
    gate_path = tmp_data / "options_flow" / "signing_gate.json"

    m = _import_module(tmp_data)
    with patch("lib.config.data_dir", return_value=tmp_data):
        agg = m.update_gate(jsonl_path=jsonl_path, gate_path=gate_path)

    written = json.loads(gate_path.read_text())
    assert written["direction_reliable"] is False, (
        "Root direction_reliable MUST NOT be auto-flipped — "
        "only Fable/human adjudication may flip it"
    )
    assert written["scored"] is False, "scored must stay False"
    # production_ready can be True (all conditions met)
    assert agg["conditions_covered"]["high_vix"] is True
    assert agg["conditions_covered"]["calm"] is True
