"""Tests for M3 escalation organ — scripts/check_nw_health_escalation.py.

Guards:
1. Streak math — 3-night trigger fires, 2-night does not, recovery resets.
   CRITICAL: fixture reflects PROD PATHOLOGY — frozen as_of across many nights.
   Streak is keyed by NIGHTLY RUN DATE (produced_at), NOT data-vintage (as_of).
2. Lane single-writer — alert writes to push_sent_nw_health.jsonl only.
3. Verb blacklist — composed message contains no trading verbs.
4. Fail-open — missing/corrupt inputs produce exit 0, no exception.
5. Adjacency guard — non-consecutive degraded dates do not form a streak.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

# Module under test
from scripts import check_nw_health_escalation as M


# ── fixtures ──────────────────────────────────────────────────────────────

_NOW = datetime(2026, 7, 9, 12, 0, 0, tzinfo=timezone.utc)

# FROZEN as_of used across multiple nightly runs — this is the prod pathology:
# upstream data is stale so as_of stays pinned at 2026-07-02 while the pipeline
# runs degraded for consecutive nights on 07-07, 07-08, 07-09, etc.
_FROZEN_AS_OF = "2026-07-02"


def _health(
    as_of: str,
    overall_status: str = "degraded",
    lobes: list | None = None,
    produced_at: str | None = None,
) -> dict:
    """Build a minimal health.json shape.

    produced_at defaults to a run timestamp on the same calendar day as as_of
    UNLESS overridden — callers that test the frozen-as_of pathology must pass
    a distinct produced_at.
    """
    if produced_at is None:
        produced_at = f"{as_of}T08:00:00+00:00"
    return {
        "schema": "neuralweb.health.v1",
        "produced_at": produced_at,
        "as_of": as_of,
        "overall_status": overall_status,
        "lobes": lobes or [],
    }


def _run_record(run_date: str, degraded: bool, produced_at: str | None = None) -> str:
    """One JSONL line for nw_health_run_history.jsonl."""
    return json.dumps({
        "run_date": run_date,
        "degraded": degraded,
        "produced_at": produced_at or f"{run_date}T08:00:00+00:00",
        "reasons_count": 1 if degraded else 0,
    })


def _write_health(
    tmp_path: Path,
    as_of: str,
    overall_status: str = "degraded",
    produced_at: str | None = None,
) -> None:
    h = _health(as_of, overall_status, produced_at=produced_at)
    p = tmp_path / "data" / "neuralweb"
    p.mkdir(parents=True, exist_ok=True)
    (p / "health.json").write_text(json.dumps(h))


def _write_run_history(tmp_path: Path, rows: list[tuple[str, bool]]) -> None:
    """Write nw_health_run_history.jsonl with (run_date, degraded) pairs."""
    p = tmp_path / "data" / "neuralweb"
    p.mkdir(parents=True, exist_ok=True)
    lines = "\n".join(_run_record(rd, deg) for rd, deg in rows)
    (p / "nw_health_run_history.jsonl").write_text(lines + "\n")


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
        """3 consecutive degraded nightly runs must trigger dispatch."""
        # Current run: degraded, produced_at = 2026-07-09
        _write_health(tmp_path, _FROZEN_AS_OF, "degraded",
                      produced_at="2026-07-09T08:10:00+00:00")
        # Prior run history: 2 consecutive degraded nights
        _write_run_history(tmp_path, [
            ("2026-07-08", True),
            ("2026-07-07", True),
            ("2026-07-06", False),
        ])
        dispatch = _Dispatch()
        with patch("engine.alert_triage.push_ops_alert", dispatch):
            result = M.run(root=tmp_path, _now=_NOW)
        assert result is True
        assert len(dispatch.calls) == 1

    def test_2_night_streak_no_fire(self, tmp_path):
        """2 consecutive degraded nightly runs must NOT trigger dispatch."""
        _write_health(tmp_path, _FROZEN_AS_OF, "degraded",
                      produced_at="2026-07-09T08:10:00+00:00")
        _write_run_history(tmp_path, [
            ("2026-07-08", True),
            ("2026-07-07", False),
        ])
        dispatch = _Dispatch()
        with patch("engine.alert_triage.push_ops_alert", dispatch):
            result = M.run(root=tmp_path, _now=_NOW)
        assert result is False
        assert len(dispatch.calls) == 0

    def test_recovery_resets_streak(self, tmp_path):
        """A healthy night breaks the streak; 2 nights after = no trigger."""
        _write_health(tmp_path, _FROZEN_AS_OF, "degraded",
                      produced_at="2026-07-09T08:10:00+00:00")
        _write_run_history(tmp_path, [
            ("2026-07-08", False),   # recovery night — streak break
            ("2026-07-07", True),
            ("2026-07-06", True),
            ("2026-07-05", True),
        ])
        dispatch = _Dispatch()
        with patch("engine.alert_triage.push_ops_alert", dispatch):
            result = M.run(root=tmp_path, _now=_NOW)
        # streak is only current night (2026-07-09 = degraded; 2026-07-08 = healthy = break)
        assert result is False

    def test_healthy_current_no_fire(self, tmp_path):
        """If today is healthy, no alert regardless of history."""
        _write_health(tmp_path, _FROZEN_AS_OF, "healthy",
                      produced_at="2026-07-09T08:10:00+00:00")
        _write_run_history(tmp_path, [
            ("2026-07-08", True),
            ("2026-07-07", True),
            ("2026-07-06", True),
        ])
        dispatch = _Dispatch()
        with patch("engine.alert_triage.push_ops_alert", dispatch):
            result = M.run(root=tmp_path, _now=_NOW)
        assert result is False

    def test_exactly_3_nights_fires(self, tmp_path):
        """Exactly 3 consecutive nights is sufficient (boundary condition)."""
        _write_health(tmp_path, _FROZEN_AS_OF, "degraded",
                      produced_at="2026-07-09T08:10:00+00:00")
        _write_run_history(tmp_path, [
            ("2026-07-08", True),
            ("2026-07-07", True),
        ])
        dispatch = _Dispatch()
        with patch("engine.alert_triage.push_ops_alert", dispatch):
            result = M.run(root=tmp_path, _now=_NOW)
        assert result is True

    def test_streak_from_health_alone_no_history(self, tmp_path):
        """With no history file, single degraded night = no fire (streak=1)."""
        _write_health(tmp_path, _FROZEN_AS_OF, "degraded",
                      produced_at="2026-07-09T08:10:00+00:00")
        # No run history written
        dispatch = _Dispatch()
        with patch("engine.alert_triage.push_ops_alert", dispatch):
            result = M.run(root=tmp_path, _now=_NOW)
        assert result is False

    # ── PROD PATHOLOGY TESTS ──────────────────────────────────────────────
    # These tests mirror the exact production scenario identified by the reviewer:
    # upstream data is stale → as_of freezes at 2026-07-02 across many nights.
    # The daily_brief_history upsert-by-as_of approach collapsed all degraded
    # nights to ONE row (streak=1, never fires).  The run-history approach must
    # correctly count consecutive runs despite the frozen as_of.

    def test_frozen_as_of_three_consecutive_runs_fires(self, tmp_path):
        """PROD PATHOLOGY: 3 consecutive degraded runs, all with same as_of, must fire.

        This is the exact '5-night silent cortex outage' scenario:
        as_of=2026-07-02 frozen (stale upstream data),
        nightly runs on 07-07, 07-08, 07-09 all degrade.
        Old approach: all collapse to one history_map key → streak=1, no fire.
        New approach: keyed by produced_at date → streak=3, fires.
        """
        # Current run: 2026-07-09, frozen as_of
        _write_health(tmp_path, _FROZEN_AS_OF, "degraded",
                      produced_at="2026-07-09T08:10:00+00:00")
        # Prior run history: 2 nights also degraded with same frozen as_of
        _write_run_history(tmp_path, [
            ("2026-07-08", True),   # degraded, as_of was also 2026-07-02
            ("2026-07-07", True),   # degraded, as_of was also 2026-07-02
        ])
        dispatch = _Dispatch()
        with patch("engine.alert_triage.push_ops_alert", dispatch):
            result = M.run(root=tmp_path, _now=_NOW)
        assert result is True, (
            "PROD PATHOLOGY REGRESSION: 3 consecutive degraded runs with frozen "
            "as_of must fire — streak must be keyed by produced_at, not as_of"
        )

    def test_frozen_as_of_two_runs_no_fire(self, tmp_path):
        """PROD PATHOLOGY: 2 consecutive degraded runs, frozen as_of — must NOT fire yet."""
        _write_health(tmp_path, _FROZEN_AS_OF, "degraded",
                      produced_at="2026-07-09T08:10:00+00:00")
        _write_run_history(tmp_path, [
            ("2026-07-08", True),   # degraded, same frozen as_of
        ])
        dispatch = _Dispatch()
        with patch("engine.alert_triage.push_ops_alert", dispatch):
            result = M.run(root=tmp_path, _now=_NOW)
        assert result is False, (
            "Only 2 consecutive runs — must not fire (threshold is 3)"
        )

    def test_frozen_as_of_five_consecutive_runs_fires(self, tmp_path):
        """PROD PATHOLOGY: 5 consecutive degraded runs with frozen as_of must fire."""
        _write_health(tmp_path, _FROZEN_AS_OF, "degraded",
                      produced_at="2026-07-09T08:10:00+00:00")
        _write_run_history(tmp_path, [
            ("2026-07-08", True),
            ("2026-07-07", True),
            ("2026-07-06", True),
            ("2026-07-05", True),
        ])
        dispatch = _Dispatch()
        with patch("engine.alert_triage.push_ops_alert", dispatch):
            result = M.run(root=tmp_path, _now=_NOW)
        assert result is True


# ── 2. ADJACENCY GUARD ────────────────────────────────────────────────────

class TestAdjacencyGuard:
    def test_non_consecutive_dates_no_false_streak(self, tmp_path):
        """MAJOR: degraded dates separated by months must NOT form a streak.

        Old approach: no adjacency check — any 3+ degraded entries in sorted
        history would fire.  E.g., 2026-07-09 + 2026-01-01 + 2026-01-02 = 3
        entries → streak=3, false positive.
        """
        _write_health(tmp_path, _FROZEN_AS_OF, "degraded",
                      produced_at="2026-07-09T08:10:00+00:00")
        # Two degraded runs from January — six-month gap before current night
        _write_run_history(tmp_path, [
            ("2026-01-02", True),
            ("2026-01-01", True),
        ])
        dispatch = _Dispatch()
        with patch("engine.alert_triage.push_ops_alert", dispatch):
            result = M.run(root=tmp_path, _now=_NOW)
        # Gap between 2026-07-09 and 2026-01-02 is >> 1 day → streak breaks at 1
        assert result is False, (
            "ADJACENCY REGRESSION: degraded dates separated by months must not "
            "count as a consecutive streak — adjacency guard required"
        )

    def test_streak_broken_by_gap(self, tmp_path):
        """2 recent consecutive + 1 older non-adjacent degraded → streak=2, no fire."""
        _write_health(tmp_path, _FROZEN_AS_OF, "degraded",
                      produced_at="2026-07-09T08:10:00+00:00")
        _write_run_history(tmp_path, [
            ("2026-07-08", True),    # consecutive with current
            ("2026-07-03", True),    # gap of 5 days — breaks streak
            ("2026-07-02", True),    # old — not in streak
        ])
        dispatch = _Dispatch()
        with patch("engine.alert_triage.push_ops_alert", dispatch):
            result = M.run(root=tmp_path, _now=_NOW)
        # streak = 2 (07-09, 07-08); 07-03 is non-adjacent → no fire
        assert result is False


# ── 3. LANE SINGLE-WRITER ────────────────────────────────────────────────

class TestLaneSingleWriter:
    def test_alert_uses_nw_health_lane(self, tmp_path):
        """Alert must use lane='nw_health', not any other lane."""
        _write_health(tmp_path, _FROZEN_AS_OF, "degraded",
                      produced_at="2026-07-09T08:10:00+00:00")
        _write_run_history(tmp_path, [
            ("2026-07-08", True),
            ("2026-07-07", True),
        ])
        dispatch = _Dispatch()
        with patch("engine.alert_triage.push_ops_alert", dispatch):
            M.run(root=tmp_path, _now=_NOW)
        assert dispatch.calls, "alert must have been dispatched"
        assert dispatch.calls[0]["lane"] == "nw_health"

    def test_alert_source_is_nw_health(self, tmp_path):
        """Alert source must be 'nw_health'."""
        _write_health(tmp_path, _FROZEN_AS_OF, "degraded",
                      produced_at="2026-07-09T08:10:00+00:00")
        _write_run_history(tmp_path, [
            ("2026-07-08", True),
            ("2026-07-07", True),
        ])
        dispatch = _Dispatch()
        with patch("engine.alert_triage.push_ops_alert", dispatch):
            M.run(root=tmp_path, _now=_NOW)
        assert dispatch.calls[0]["source"] == "nw_health"

    def test_alert_type_is_health_breach_streak(self, tmp_path):
        """Alert type must be 'health_breach_streak'."""
        _write_health(tmp_path, _FROZEN_AS_OF, "degraded",
                      produced_at="2026-07-09T08:10:00+00:00")
        _write_run_history(tmp_path, [
            ("2026-07-08", True),
            ("2026-07-07", True),
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


# ── 4. VERB BLACKLIST ─────────────────────────────────────────────────────

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


# ── 5. FAIL-OPEN ─────────────────────────────────────────────────────────

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
        """Missing run history file must return gracefully (not enough data = no fire)."""
        _write_health(tmp_path, _FROZEN_AS_OF, "degraded",
                      produced_at="2026-07-09T08:10:00+00:00")
        # No run history file
        result = M.run(root=tmp_path)
        # streak=1 (only current run appended then read), no fire
        assert result is False

    def test_corrupt_history_file_continues(self, tmp_path):
        """Corrupt lines in run history must be skipped; valid lines still counted."""
        _write_health(tmp_path, _FROZEN_AS_OF, "degraded",
                      produced_at="2026-07-09T08:10:00+00:00")
        p = tmp_path / "data" / "neuralweb"
        p.mkdir(parents=True, exist_ok=True)
        lines = [
            _run_record("2026-07-08", True),
            "not valid json !!!",
            _run_record("2026-07-07", True),
        ]
        (p / "nw_health_run_history.jsonl").write_text("\n".join(lines))
        # Should still fire: 3 nights (current + 2 valid history)
        dispatch = _Dispatch()
        with patch("engine.alert_triage.push_ops_alert", dispatch):
            result = M.run(root=tmp_path, _now=_NOW)
        assert result is True

    def test_push_ops_alert_failure_returns_false(self, tmp_path):
        """push_ops_alert exception must be caught; run() must return False."""
        _write_health(tmp_path, _FROZEN_AS_OF, "degraded",
                      produced_at="2026-07-09T08:10:00+00:00")
        _write_run_history(tmp_path, [
            ("2026-07-08", True),
            ("2026-07-07", True),
        ])

        def _raise(*a, **kw):
            raise RuntimeError("simulated transport failure")

        with patch("engine.alert_triage.push_ops_alert", _raise):
            result = M.run(root=tmp_path, _now=_NOW)
        assert result is False
