"""Tests for M3 escalation organ — scripts/check_nw_health_escalation.py.

Guards:
1. Streak math — 3-night trigger fires, 2-night does not, recovery resets.
2. Lane single-writer — alert writes to push_sent_nw_health.jsonl only.
3. Verb blacklist — composed message contains no trading verbs.
4. Fail-open — missing/corrupt inputs produce exit 0, no exception.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Module under test
from scripts import check_nw_health_escalation as M


# ── fixtures ──────────────────────────────────────────────────────────────

_NOW = datetime(2026, 7, 9, 12, 0, 0, tzinfo=timezone.utc)

# Minimal health.json shape used in tests
def _health(as_of: str, overall_status: str = "degraded", lobes: list | None = None) -> dict:
    return {
        "schema": "neuralweb.health.v1",
        "as_of": as_of,
        "overall_status": overall_status,
        "lobes": lobes or [],
    }


def _brief_row(as_of: str, status: str) -> str:
    """One JSONL line for daily_brief_history.jsonl."""
    return json.dumps({"as_of": as_of, "status": status, "phase": "final"})


def _write_health(tmp_path: Path, as_of: str, overall_status: str = "degraded") -> None:
    h = _health(as_of, overall_status)
    p = tmp_path / "data" / "neuralweb"
    p.mkdir(parents=True, exist_ok=True)
    (p / "health.json").write_text(json.dumps(h))


def _write_history(tmp_path: Path, rows: list[tuple[str, str]]) -> None:
    p = tmp_path / "data" / "neuralweb"
    p.mkdir(parents=True, exist_ok=True)
    lines = "\n".join(_brief_row(as_of, status) for as_of, status in rows)
    (p / "daily_brief_history.jsonl").write_text(lines + "\n")


# ── helpers for mocking push_ops_alert ───────────────────────────────────

class _Dispatch:
    """Records calls to push_ops_alert and returns True (dispatched)."""
    def __init__(self):
        self.calls: list[dict] = []

    def __call__(self, *, source, type_, message, severity, lane, root=None, _now=None, **kw):
        self.calls.append(dict(source=source, type_=type_, message=message,
                               severity=severity, lane=lane))
        return True


# ── 1. STREAK MATH ────────────────────────────────────────────────────────

class TestStreakMath:
    def test_3_night_streak_fires(self, tmp_path):
        """3 consecutive degraded nights must trigger dispatch."""
        _write_health(tmp_path, "2026-07-09", "degraded")
        _write_history(tmp_path, [
            ("2026-07-08", "degraded"),
            ("2026-07-07", "degraded"),
            ("2026-07-06", "healthy"),
        ])
        dispatch = _Dispatch()
        with patch("scripts.check_nw_health_escalation.push_ops_alert", dispatch, create=True):
            with patch("engine.alert_triage.push_ops_alert", dispatch):
                result = M.run(root=tmp_path, _now=_NOW)
        assert result is True
        assert len(dispatch.calls) == 1

    def test_2_night_streak_no_fire(self, tmp_path):
        """2 consecutive degraded nights must NOT trigger dispatch."""
        _write_health(tmp_path, "2026-07-09", "degraded")
        _write_history(tmp_path, [
            ("2026-07-08", "degraded"),
            ("2026-07-07", "healthy"),
        ])
        dispatch = _Dispatch()
        with patch("engine.alert_triage.push_ops_alert", dispatch):
            result = M.run(root=tmp_path, _now=_NOW)
        assert result is False
        assert len(dispatch.calls) == 0

    def test_recovery_resets_streak(self, tmp_path):
        """A healthy night breaks the streak; 2 nights after = no trigger."""
        _write_health(tmp_path, "2026-07-09", "degraded")
        _write_history(tmp_path, [
            ("2026-07-08", "healthy"),   # recovery
            ("2026-07-07", "degraded"),
            ("2026-07-06", "degraded"),
            ("2026-07-05", "degraded"),
        ])
        dispatch = _Dispatch()
        with patch("engine.alert_triage.push_ops_alert", dispatch):
            result = M.run(root=tmp_path, _now=_NOW)
        # streak is only current night (2026-07-09 = degraded; 2026-07-08 = healthy = break)
        assert result is False

    def test_healthy_current_no_fire(self, tmp_path):
        """If today is healthy, no alert regardless of history."""
        _write_health(tmp_path, "2026-07-09", "healthy")
        _write_history(tmp_path, [
            ("2026-07-08", "degraded"),
            ("2026-07-07", "degraded"),
            ("2026-07-06", "degraded"),
        ])
        dispatch = _Dispatch()
        with patch("engine.alert_triage.push_ops_alert", dispatch):
            result = M.run(root=tmp_path, _now=_NOW)
        assert result is False

    def test_exactly_3_nights_fires(self, tmp_path):
        """Exactly 3 consecutive nights is sufficient (boundary condition)."""
        _write_health(tmp_path, "2026-07-09", "degraded")
        _write_history(tmp_path, [
            ("2026-07-08", "degraded"),
            ("2026-07-07", "degraded"),
        ])
        dispatch = _Dispatch()
        with patch("engine.alert_triage.push_ops_alert", dispatch):
            result = M.run(root=tmp_path, _now=_NOW)
        assert result is True

    def test_streak_from_health_alone_no_history(self, tmp_path):
        """With no history file, single degraded night = no fire."""
        _write_health(tmp_path, "2026-07-09", "degraded")
        # No history written
        dispatch = _Dispatch()
        with patch("engine.alert_triage.push_ops_alert", dispatch):
            result = M.run(root=tmp_path, _now=_NOW)
        assert result is False


# ── 2. LANE SINGLE-WRITER ────────────────────────────────────────────────

class TestLaneSingleWriter:
    def test_alert_uses_nw_health_lane(self, tmp_path):
        """Alert must use lane='nw_health', not any other lane."""
        _write_health(tmp_path, "2026-07-09", "degraded")
        _write_history(tmp_path, [
            ("2026-07-08", "degraded"),
            ("2026-07-07", "degraded"),
        ])
        dispatch = _Dispatch()
        with patch("engine.alert_triage.push_ops_alert", dispatch):
            M.run(root=tmp_path, _now=_NOW)
        assert dispatch.calls, "alert must have been dispatched"
        assert dispatch.calls[0]["lane"] == "nw_health"

    def test_alert_source_is_nw_health(self, tmp_path):
        """Alert source must be 'nw_health'."""
        _write_health(tmp_path, "2026-07-09", "degraded")
        _write_history(tmp_path, [
            ("2026-07-08", "degraded"),
            ("2026-07-07", "degraded"),
        ])
        dispatch = _Dispatch()
        with patch("engine.alert_triage.push_ops_alert", dispatch):
            M.run(root=tmp_path, _now=_NOW)
        assert dispatch.calls[0]["source"] == "nw_health"

    def test_alert_type_is_health_breach_streak(self, tmp_path):
        """Alert type must be 'health_breach_streak'."""
        _write_health(tmp_path, "2026-07-09", "degraded")
        _write_history(tmp_path, [
            ("2026-07-08", "degraded"),
            ("2026-07-07", "degraded"),
        ])
        dispatch = _Dispatch()
        with patch("engine.alert_triage.push_ops_alert", dispatch):
            M.run(root=tmp_path, _now=_NOW)
        assert dispatch.calls[0]["type_"] == "health_breach_streak"

    def test_ops_lanes_contains_nw_health(self):
        """_OPS_LANES in alert_triage must include 'nw_health' after registration."""
        from engine import alert_triage
        assert "nw_health" in alert_triage._OPS_LANES, (
            "_OPS_LANES missing 'nw_health' — synapse registration incomplete"
        )
        assert alert_triage._OPS_LANES["nw_health"] == "push_sent_nw_health.jsonl"


# ── 3. VERB BLACKLIST ─────────────────────────────────────────────────────

class TestVerbBlacklist:
    def test_compose_message_no_trading_verbs(self):
        """Composed message must contain no trading verbs."""
        import re
        msg = M._compose_message(
            streak=5,
            reasons=["overall_status=degraded", "lobe:kernel-families:stale"],
            as_of="2026-07-09",
        )
        from engine.neuralweb.daily_brief import TRADING_VERBS
        for verb in TRADING_VERBS:
            match = re.search(rf"\b{re.escape(verb)}\b", msg.lower())
            assert match is None, (
                f"Trading verb '{verb}' found in escalation message: {msg!r}"
            )

    def test_internal_verb_check_detects_contamination(self):
        """_check_trading_verbs helper correctly flags contaminated text."""
        found = M._check_trading_verbs("System check: buy signal detected")
        assert "buy" in found

    def test_internal_verb_check_clean_text(self):
        """_check_trading_verbs returns empty list for maintenance-vocabulary text."""
        clean = "Ops check: review data/neuralweb/health.json for lobe status."
        assert M._check_trading_verbs(clean) == []

    def test_message_contains_streak_count(self):
        """Composed message must include the streak count."""
        msg = M._compose_message(
            streak=4,
            reasons=["overall_status=degraded"],
            as_of="2026-07-09",
        )
        assert "4" in msg

    def test_message_contains_as_of(self):
        """Composed message must include the as_of date."""
        msg = M._compose_message(
            streak=3,
            reasons=["overall_status=degraded"],
            as_of="2026-07-09",
        )
        assert "2026-07-09" in msg


# ── 4. FAIL-OPEN ─────────────────────────────────────────────────────────

class TestFailOpen:
    def test_missing_health_json_returns_false(self, tmp_path):
        """Missing health.json must return False, never raise."""
        # No health.json written
        result = M.run(root=tmp_path)
        assert result is False

    def test_corrupt_health_json_returns_false(self, tmp_path):
        """Corrupt health.json must return False, never raise."""
        p = tmp_path / "data" / "neuralweb"
        p.mkdir(parents=True, exist_ok=True)
        (p / "health.json").write_text("not valid json {{{{")
        result = M.run(root=tmp_path)
        assert result is False

    def test_missing_history_file_degrades_gracefully(self, tmp_path):
        """Missing history file must return gracefully (not enough data = no fire)."""
        _write_health(tmp_path, "2026-07-09", "degraded")
        # No history file
        result = M.run(root=tmp_path)
        # streak=1 (only current), no fire
        assert result is False

    def test_corrupt_history_file_continues(self, tmp_path):
        """Corrupt lines in history must be skipped; valid lines still counted."""
        _write_health(tmp_path, "2026-07-09", "degraded")
        p = tmp_path / "data" / "neuralweb"
        p.mkdir(parents=True, exist_ok=True)
        lines = [
            _brief_row("2026-07-08", "degraded"),
            "not valid json !!!",
            _brief_row("2026-07-07", "degraded"),
        ]
        (p / "daily_brief_history.jsonl").write_text("\n".join(lines))
        # Should still fire: 3 nights (current + 2 valid history)
        dispatch = _Dispatch()
        with patch("engine.alert_triage.push_ops_alert", dispatch):
            result = M.run(root=tmp_path, _now=_NOW)
        assert result is True

    def test_push_ops_alert_failure_returns_false(self, tmp_path):
        """push_ops_alert exception must be caught; run() must return False."""
        _write_health(tmp_path, "2026-07-09", "degraded")
        _write_history(tmp_path, [
            ("2026-07-08", "degraded"),
            ("2026-07-07", "degraded"),
        ])

        def _raise(*a, **kw):
            raise RuntimeError("simulated transport failure")

        with patch("engine.alert_triage.push_ops_alert", _raise):
            result = M.run(root=tmp_path, _now=_NOW)
        assert result is False
