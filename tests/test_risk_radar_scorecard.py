"""Hermetic tests for engine/risk_radar_scorecard.py.

Covers:
- every outcome label (true_positive, false_positive, tp_watch, tn_watch, calm_dd, calm_quiet)
- window math (full vs trailing 365d)
- min-n honesty floor (n=4 -> null, n=5 -> rate)
- malformed JSONL line skipped cleanly
- missing intl ledger -> fail-soft entry (no raise)
- ungraded backlog count (rows older than 7 days with graded=null)
- atomic write to both paths
- build() never raises with empty/absent everything
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from engine import risk_radar_scorecard as sc


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _asof(days_ago: int) -> str:
    return (date.today() - timedelta(days=days_ago)).isoformat()


def _graded(outcome: str) -> dict:
    """Synthetic graded block for a US forward-log row."""
    return {
        "base_px": 500.0,
        "fwd_dd": {"h5": -0.02, "h10": -0.03, "h21": -0.06},
        "hit": {"h5": {"dd5": False, "dd8": False}, "h10": {"dd5": False, "dd8": False},
                "h21": {"dd5": True, "dd8": False}},
        "outcome": outcome,
        "any_dd5_within_h21": outcome in ("true_positive", "tp_watch", "calm_dd"),
        "graded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def _row(state: str, dominant_scare: str | None, days_ago: int, outcome: str) -> dict:
    return {
        "asof": _asof(days_ago),
        "state": state,
        "alert": state in ("elevated", "risk-off"),
        "dominant_scare": dominant_scare,
        "top_score": 75.0,
        "scares": {},
        "logged_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "graded": _graded(outcome),
    }


def _ungraded_row(state: str, days_ago: int) -> dict:
    return {
        "asof": _asof(days_ago),
        "state": state,
        "alert": state in ("elevated", "risk-off"),
        "dominant_scare": "growth",
        "top_score": 60.0,
        "scares": {},
        "logged_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "graded": None,
    }


def _recovery_graded(fwd_ret_h21: float) -> dict:
    """Synthetic graded block for a recovery log row."""
    return {
        "base_px": 500.0,
        "h21": {"fwd_ret": fwd_ret_h21, "mae": -0.02},
        "h63": {"fwd_ret": fwd_ret_h21 + 0.01, "mae": -0.01},
        "graded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def _recovery_row(days_ago: int, fwd_ret_h21: float | None) -> dict:
    return {
        "asof": _asof(days_ago),
        "phase": "receding",
        "logged_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "graded": _recovery_graded(fwd_ret_h21) if fwd_ret_h21 is not None else None,
    }


def _write_jsonl(p: Path, rows: list[dict]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# build() — never raises on empty/absent everything
# ---------------------------------------------------------------------------

def test_build_empty_root(tmp_path):
    result = sc.build(root=tmp_path)
    assert result["schema"] == "risk_radar_scorecard.v1"
    assert "markets" in result
    assert set(result["markets"]) == {"us", "cn", "hk", "ca"}


def test_build_never_raises_with_nothing(tmp_path):
    # No files at all — must not raise, must return a dict
    result = sc.build(root=tmp_path)
    assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Outcome labels — every label produces correct counts
# ---------------------------------------------------------------------------

@pytest.fixture()
def all_outcomes_root(tmp_path):
    rows = [
        _row("elevated", "credit", 100, "true_positive"),
        _row("risk-off", "rates", 101, "false_positive"),
        _row("watch", None, 102, "tp_watch"),
        _row("caution", "vol", 103, "tn_watch"),
        _row("calm", None, 104, "calm_dd"),
        _row("calm", None, 105, "calm_quiet"),
    ]
    _write_jsonl(tmp_path / "data" / "risk_radar" / "forward_log.jsonl", rows)
    return tmp_path


def test_alerts_counts(all_outcomes_root):
    result = sc.build(root=all_outcomes_root)
    alerts = result["markets"]["us"]["windows"]["full"]["alerts"]
    assert alerts["n"] == 2
    assert alerts["tp"] == 1
    assert alerts["fp"] == 1
    assert alerts["hit_rate"] is None  # n=2 < 5


def test_watch_caution_counts(all_outcomes_root):
    result = sc.build(root=all_outcomes_root)
    wc = result["markets"]["us"]["windows"]["full"]["watch_caution"]
    assert wc["n"] == 2
    assert wc["tp"] == 1
    assert wc["tn"] == 1


def test_calm_counts(all_outcomes_root):
    result = sc.build(root=all_outcomes_root)
    calm = result["markets"]["us"]["windows"]["full"]["calm"]
    assert calm["n"] == 2
    assert calm["dd_missed"] == 1
    assert calm["quiet"] == 1


def test_by_scare_counts(all_outcomes_root):
    result = sc.build(root=all_outcomes_root)
    by_scare = result["markets"]["us"]["windows"]["full"]["by_scare"]
    # Only alert rows (elevated/risk-off) contribute to by_scare
    assert "credit" in by_scare
    assert by_scare["credit"]["n"] == 1
    assert by_scare["credit"]["tp"] == 1
    assert by_scare["rates"]["fp"] == 1


# ---------------------------------------------------------------------------
# Min-n honesty floor: n=4 -> null, n=5 -> float
# ---------------------------------------------------------------------------

def test_min_n_null_at_4(tmp_path):
    rows = [_row("elevated", "credit", 10 + i, "true_positive") for i in range(4)]
    _write_jsonl(tmp_path / "data" / "risk_radar" / "forward_log.jsonl", rows)
    result = sc.build(root=tmp_path)
    alerts = result["markets"]["us"]["windows"]["full"]["alerts"]
    assert alerts["n"] == 4
    assert alerts["hit_rate"] is None


def test_min_n_rate_at_5(tmp_path):
    rows = [_row("elevated", "credit", 10 + i, "true_positive") for i in range(5)]
    _write_jsonl(tmp_path / "data" / "risk_radar" / "forward_log.jsonl", rows)
    result = sc.build(root=tmp_path)
    alerts = result["markets"]["us"]["windows"]["full"]["alerts"]
    assert alerts["n"] == 5
    assert alerts["hit_rate"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Window: full vs trailing 365d
# ---------------------------------------------------------------------------

def test_window_trailing_365_excludes_old_rows(tmp_path):
    old_rows = [_row("elevated", "credit", 400 + i, "true_positive") for i in range(5)]
    recent_rows = [_row("elevated", "credit", 10 + i, "false_positive") for i in range(5)]
    _write_jsonl(tmp_path / "data" / "risk_radar" / "forward_log.jsonl",
                 old_rows + recent_rows)
    result = sc.build(root=tmp_path)
    full = result["markets"]["us"]["windows"]["full"]["alerts"]
    y1 = result["markets"]["us"]["windows"]["y1"]["alerts"]
    assert full["n"] == 10   # all rows
    assert y1["n"] == 5      # only the recent ones


def test_window_y1_excludes_old_but_inside_365_included(tmp_path):
    rows = [_row("elevated", "credit", 300 + i, "true_positive") for i in range(5)]
    _write_jsonl(tmp_path / "data" / "risk_radar" / "forward_log.jsonl", rows)
    result = sc.build(root=tmp_path)
    # All rows are 300-304 days ago — still within 365
    y1 = result["markets"]["us"]["windows"]["y1"]["alerts"]
    assert y1["n"] == 5


# ---------------------------------------------------------------------------
# Malformed JSONL line skipped
# ---------------------------------------------------------------------------

def test_malformed_line_skipped(tmp_path):
    p = tmp_path / "data" / "risk_radar" / "forward_log.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    rows = [_row("elevated", "credit", 10, "true_positive"),
            _row("elevated", "credit", 11, "true_positive")]
    lines = [json.dumps(r) for r in rows]
    lines.insert(1, "NOT JSON {{{{")  # inject malformed
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # Should not raise; should still parse the 2 valid rows
    result = sc.build(root=tmp_path)
    graded_n = result["markets"]["us"]["monitoring"]["graded_n"]
    assert graded_n == 2


# ---------------------------------------------------------------------------
# Missing intl ledger -> fail-soft entry
# ---------------------------------------------------------------------------

def test_missing_intl_ledger_fail_soft(tmp_path):
    # Only write US ledger; leave CN/HK/CA absent
    rows = [_row("elevated", "credit", 10, "true_positive")]
    _write_jsonl(tmp_path / "data" / "risk_radar" / "forward_log.jsonl", rows)
    result = sc.build(root=tmp_path)
    # Should not raise; cn/hk/ca should each have a fail-soft structure
    for market in ("cn", "hk", "ca"):
        m = result["markets"][market]
        assert "monitoring" in m
        assert m["monitoring"]["log_fresh"] is False
        assert "windows" in m


# ---------------------------------------------------------------------------
# Ungraded backlog count
# ---------------------------------------------------------------------------

def test_ungraded_backlog_counts_old_rows(tmp_path):
    # Backlog threshold: rows with graded=None AND (today - asof).days > 7
    rows = [
        _ungraded_row("caution", 3),    # 3 days ago — NOT backlog (<=7)
        _ungraded_row("caution", 7),    # exactly 7 days ago — NOT backlog (not > 7)
        _ungraded_row("caution", 8),    # 8 days ago — IS backlog (> 7)
        _ungraded_row("caution", 20),   # 20 days ago — IS backlog
        _row("elevated", "credit", 50, "true_positive"),  # graded, not counted
    ]
    _write_jsonl(tmp_path / "data" / "risk_radar" / "forward_log.jsonl", rows)
    result = sc.build(root=tmp_path)
    monitoring = result["markets"]["us"]["monitoring"]
    assert monitoring["ungraded_backlog"] == 2


# ---------------------------------------------------------------------------
# Recovery block
# ---------------------------------------------------------------------------

def test_recovery_ok_rate(tmp_path):
    recovery_rows = [
        _recovery_row(50, 0.05),    # h21 > 0 = ok
        _recovery_row(51, 0.02),    # ok
        _recovery_row(52, -0.01),   # not ok
        _recovery_row(53, 0.03),    # ok
        _recovery_row(54, 0.01),    # ok
    ]
    _write_jsonl(tmp_path / "data" / "risk_radar" / "recovery_log.jsonl", recovery_rows)
    _write_jsonl(tmp_path / "data" / "risk_radar" / "forward_log.jsonl", [])
    result = sc.build(root=tmp_path)
    rec = result["markets"]["us"]["windows"]["full"]["recovery"]
    assert rec is not None
    assert rec["n"] == 5
    assert rec["ok"] == 4
    assert rec["rate"] == pytest.approx(4 / 5)


def test_recovery_null_rate_below_min_n(tmp_path):
    recovery_rows = [_recovery_row(50 + i, 0.01) for i in range(4)]
    _write_jsonl(tmp_path / "data" / "risk_radar" / "recovery_log.jsonl", recovery_rows)
    _write_jsonl(tmp_path / "data" / "risk_radar" / "forward_log.jsonl", [])
    result = sc.build(root=tmp_path)
    rec = result["markets"]["us"]["windows"]["full"]["recovery"]
    assert rec is not None
    assert rec["rate"] is None   # n=4 < 5


def test_recovery_none_when_no_graded(tmp_path):
    # Ungraded recovery rows → recovery block should be None (no graded rows)
    recovery_rows = [_recovery_row(50, None), _recovery_row(51, None)]
    _write_jsonl(tmp_path / "data" / "risk_radar" / "recovery_log.jsonl", recovery_rows)
    _write_jsonl(tmp_path / "data" / "risk_radar" / "forward_log.jsonl", [])
    result = sc.build(root=tmp_path)
    rec = result["markets"]["us"]["windows"]["full"]["recovery"]
    assert rec is None


# ---------------------------------------------------------------------------
# Intl market entries (with data)
# ---------------------------------------------------------------------------

def test_intl_cn_market(tmp_path):
    rows = [_row("elevated", "breadth", 50 + i, "true_positive") for i in range(5)]
    for r in rows:
        r["market"] = "cn"
    _write_jsonl(tmp_path / "data" / "risk_radar_intl" / "cn_forward_log.jsonl", rows)
    result = sc.build(root=tmp_path)
    cn = result["markets"]["cn"]
    assert cn["monitoring"]["graded_n"] == 5
    assert cn["windows"]["full"]["alerts"]["n"] == 5


# ---------------------------------------------------------------------------
# Atomic write — both paths get valid JSON
# ---------------------------------------------------------------------------

def test_write_both_paths(tmp_path):
    # Write some data
    rows = [_row("elevated", "credit", 30 + i, "true_positive") for i in range(5)]
    _write_jsonl(tmp_path / "data" / "risk_radar" / "forward_log.jsonl", rows)

    returned = sc.write(root=tmp_path)
    assert isinstance(returned, dict)
    assert returned.get("schema") == "risk_radar_scorecard.v1"

    data_path = tmp_path / "data" / "risk_radar" / "scorecard.json"
    site_path = tmp_path / "site" / "riskdata" / "scorecard.json"

    assert data_path.exists(), "data/risk_radar/scorecard.json not written"
    assert site_path.exists(), "site/riskdata/scorecard.json not written"

    data_obj = json.loads(data_path.read_text())
    site_obj = json.loads(site_path.read_text())

    assert data_obj["schema"] == "risk_radar_scorecard.v1"
    assert site_obj["schema"] == "risk_radar_scorecard.v1"
    # Both copies must be identical
    assert data_obj == site_obj


def test_write_never_raises_empty(tmp_path):
    result = sc.write(root=tmp_path)
    assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Monitoring block: log_fresh, last_logged_days_ago
# ---------------------------------------------------------------------------

def test_log_fresh_recent_row(tmp_path):
    rows = [_ungraded_row("caution", 1)]  # 1 day ago
    _write_jsonl(tmp_path / "data" / "risk_radar" / "forward_log.jsonl", rows)
    result = sc.build(root=tmp_path)
    assert result["markets"]["us"]["monitoring"]["log_fresh"] is True
    assert result["markets"]["us"]["monitoring"]["last_logged_days_ago"] == 1


def test_log_fresh_stale_row(tmp_path):
    rows = [_ungraded_row("caution", 5)]  # 5 days ago — still within 3d? No, fails
    _write_jsonl(tmp_path / "data" / "risk_radar" / "forward_log.jsonl", rows)
    result = sc.build(root=tmp_path)
    assert result["markets"]["us"]["monitoring"]["log_fresh"] is False
    assert result["markets"]["us"]["monitoring"]["last_logged_days_ago"] == 5


# ---------------------------------------------------------------------------
# Schema guard: all required keys present in output
# ---------------------------------------------------------------------------

def test_schema_keys_present(tmp_path):
    result = sc.build(root=tmp_path)
    assert "schema" in result
    assert "generated_at" in result
    assert "markets" in result
    for market in ("us", "cn", "hk", "ca"):
        m = result["markets"][market]
        assert "monitoring" in m, f"{market} missing monitoring"
        assert "windows" in m, f"{market} missing windows"
        for wk in ("full", "y1"):
            w = m["windows"][wk]
            assert "alerts" in w, f"{market}/{wk} missing alerts"
            assert "watch_caution" in w
            assert "calm" in w
            assert "by_scare" in w
            assert "recovery" in w


# ---------------------------------------------------------------------------
# FIX 5: corrupt graded value drops only that row, not the whole market
# ---------------------------------------------------------------------------

def test_corrupt_graded_row_dropped_not_whole_market(tmp_path):
    """A row with graded='CORRUPT' (not a dict) must be skipped;
    valid rows in the same ledger are still counted."""
    rows = [
        _row("elevated", "credit", 10, "true_positive"),
        _row("elevated", "credit", 11, "true_positive"),
        _row("elevated", "credit", 12, "true_positive"),
        _row("elevated", "credit", 13, "true_positive"),
        _row("elevated", "credit", 14, "true_positive"),
    ]
    # Inject one corrupt row (graded is a scalar string, not a dict)
    corrupt_row = {
        "asof": _asof(15),
        "state": "elevated",
        "alert": True,
        "dominant_scare": "credit",
        "top_score": 80.0,
        "scares": {},
        "logged_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "graded": "CORRUPT",  # must be ignored, not crash
    }
    _write_jsonl(tmp_path / "data" / "risk_radar" / "forward_log.jsonl",
                 rows + [corrupt_row])
    result = sc.build(root=tmp_path)
    alerts = result["markets"]["us"]["windows"]["full"]["alerts"]
    # 5 valid rows should still be counted; corrupt row excluded from window math
    assert alerts["n"] == 5
    assert alerts["tp"] == 5
    assert alerts["hit_rate"] == pytest.approx(1.0)
