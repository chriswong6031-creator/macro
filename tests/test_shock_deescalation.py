"""Tests for engine/shock_deescalation.py (policy-shock program W2-E).

Contract requirements tested:
  - Trigger: SHOCK fires; single ELEVATED does not; two consecutive ELEVATED
    with flip fires; two ELEVATED without flip does not.
  - Expiry window math (trigger date + 3 NYSE sessions).
  - Keep-first ledger semantics.
  - Intraday path cannot write data/ (PS-R7 guard).
  - Backscan regression: 2026-07-07 must appear as would-have-fired.
"""
from __future__ import annotations

import json
import os
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from engine import shock_deescalation as sd


# ── helpers ─────────────────────────────────────────────────────────────────────

def _make_coh(state="QUIET", score=0, flip=0):
    """Minimal repricing_coherence block."""
    return {
        "score": score,
        "state": state,
        "state_zh": {"QUIET": "平静", "ELEVATED": "偏高", "SHOCK": "冲击"}[state],
        "components": {
            "driver_flip": flip,
            "strength_extreme": 0,
            "absorption_spike": 0,
            "repricing_breadth": 0,
        },
        "note": "test",
        "note_zh": "测试",
    }


def _make_snap(asof="2026-07-07", state="SHOCK", score=75, flip=30, primary="ai_semis"):
    return {
        "asof": asof,
        "verdict": "clear",
        "primary": primary,
        "strength": 2.81,
        "repricing_coherence": _make_coh(state=state, score=score, flip=flip),
    }


# ── trigger evaluation ───────────────────────────────────────────────────────────

class TestTriggerEvaluation:
    def test_shock_fires(self):
        reason = sd._evaluate_trigger("SHOCK", 30, "ELEVATED")
        assert reason == "state==SHOCK"

    def test_shock_fires_even_without_flip(self):
        reason = sd._evaluate_trigger("SHOCK", 0, None)
        assert reason == "state==SHOCK"

    def test_single_elevated_does_not_fire(self):
        reason = sd._evaluate_trigger("ELEVATED", 30, "QUIET")
        assert reason is None

    def test_single_elevated_no_prev_does_not_fire(self):
        reason = sd._evaluate_trigger("ELEVATED", 30, None)
        assert reason is None

    def test_two_consecutive_elevated_with_flip_fires(self):
        reason = sd._evaluate_trigger("ELEVATED", 30, "ELEVATED")
        assert reason == "two_consecutive_ELEVATED_with_flip"

    def test_two_elevated_without_flip_does_not_fire(self):
        """Latest print must have driver_flip > 0 for the two-ELEVATED trigger."""
        reason = sd._evaluate_trigger("ELEVATED", 0, "ELEVATED")
        assert reason is None

    def test_quiet_never_fires(self):
        assert sd._evaluate_trigger("QUIET", 30, "ELEVATED") is None
        assert sd._evaluate_trigger("QUIET", 0, "QUIET") is None


# ── expiry window math ──────────────────────────────────────────────────────────

class TestExpiryWindow:
    def test_three_sessions_from_thursday(self):
        """2026-07-09 (Thursday) + 3 sessions = 2026-07-14 (Tuesday)."""
        start = date(2026, 7, 9)  # Thursday
        expires = sd._add_sessions(start, 3)
        # Fri 07-10, Mon 07-13, Tue 07-14
        assert expires == date(2026, 7, 14)

    def test_three_sessions_skips_weekend(self):
        start = date(2026, 7, 11)  # Saturday
        expires = sd._add_sessions(start, 3)
        # Mon 07-13, Tue 07-14, Wed 07-15
        assert expires == date(2026, 7, 15)

    def test_three_sessions_from_wednesday(self):
        start = date(2026, 7, 8)  # Wednesday
        expires = sd._add_sessions(start, 3)
        # Thu 07-09, Fri 07-10, Mon 07-13
        assert expires == date(2026, 7, 13)

    def test_active_within_window(self):
        since = date(2026, 7, 7)
        expires = date(2026, 7, 10)
        assert sd._active(since, expires, today=date(2026, 7, 8))

    def test_inactive_after_window(self):
        since = date(2026, 7, 7)
        expires = date(2026, 7, 10)
        # today > expires
        assert not sd._active(since, expires, today=date(2026, 7, 14))


# ── keep-first ledger semantics ─────────────────────────────────────────────────

class TestKeepFirst:
    def test_keep_first_same_date(self, tmp_path):
        firing_path = tmp_path / "firings.jsonl"
        firing = {"date": "2026-07-07", "score": 75, "state": "SHOCK",
                  "trigger_reason": "state==SHOCK", "primary_driver": "ai_semis",
                  "expires": "2026-07-14"}
        firings = sd._append_firing([], firing, firing_path)
        # second call same date — keep-first, no append
        firing2 = dict(firing, score=50, state="ELEVATED")
        firings2 = sd._append_firing(firings, firing2, firing_path)
        # check on-disk: only one row
        lines = [l for l in firing_path.read_text().splitlines() if l.strip()]
        assert len(lines) == 1
        assert json.loads(lines[0])["score"] == 75  # first row kept

    def test_different_dates_both_appended(self, tmp_path):
        firing_path = tmp_path / "firings.jsonl"
        f1 = {"date": "2026-06-25", "score": 50, "state": "ELEVATED",
              "trigger_reason": "two_consecutive_ELEVATED_with_flip",
              "primary_driver": "ai_semis", "expires": "2026-06-30"}
        f2 = {"date": "2026-07-07", "score": 75, "state": "SHOCK",
              "trigger_reason": "state==SHOCK", "primary_driver": "ai_semis",
              "expires": "2026-07-14"}
        firings = sd._append_firing([], f1, firing_path)
        firings = sd._append_firing(firings, f2, firing_path)
        lines = [l for l in firing_path.read_text().splitlines() if l.strip()]
        assert len(lines) == 2

    def test_load_firings_empty_if_absent(self, tmp_path):
        path = tmp_path / "nonexistent.jsonl"
        assert sd._load_firings(path) == []

    def test_load_firings_reads_correctly(self, tmp_path):
        path = tmp_path / "test.jsonl"
        row = {"date": "2026-07-07", "score": 75, "state": "SHOCK",
               "trigger_reason": "state==SHOCK", "primary_driver": "ai_semis",
               "expires": "2026-07-14"}
        path.write_text(json.dumps(row) + "\n")
        rows = sd._load_firings(path)
        assert len(rows) == 1
        assert rows[0]["date"] == "2026-07-07"


# ── intraday cannot write data/ ─────────────────────────────────────────────────

class TestIntradayGuard:
    def test_intraday_does_not_write_firings(self, tmp_path, monkeypatch):
        """build_intraday must not write to data/reflexes/ (PS-R7)."""
        from lib import config

        # Patch config.data_dir to a tmp path
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)

        # Provide a minimal market_drivers.json in site/live/
        site = config.ROOT / config.load()["storage"]["site_dir"]
        live_dir = site / "live"
        live_dir.mkdir(parents=True, exist_ok=True)
        snap = {
            "asof": "2026-07-07",
            "verdict": "clear",
            "primary": "ai_semis",
            "strength": 2.81,
            "repricing_coherence": _make_coh("SHOCK", 75, 30),
        }
        (live_dir / "market_drivers.json").write_text(json.dumps(snap))

        sd.build_intraday()

        # data/ firings must NOT have been created
        firings_path = tmp_path / "reflexes" / "shock_deescalation" / "firings.jsonl"
        assert not firings_path.exists(), (
            "intraday path must not write data/reflexes/ (PS-R7 violation)"
        )


# ── nightly build integration ────────────────────────────────────────────────────

class TestNightlyBuild:
    def test_nightly_shock_writes_firing(self, tmp_path, monkeypatch):
        from lib import config
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)

        snap = _make_snap(asof="2026-07-07", state="SHOCK", score=75, flip=30)
        result = sd.build_nightly(snap=snap)

        assert result["active"] is True
        firings_path = tmp_path / "reflexes" / "shock_deescalation" / "firings.jsonl"
        assert firings_path.exists()
        rows = [json.loads(l) for l in firings_path.read_text().splitlines() if l.strip()]
        assert len(rows) == 1
        assert rows[0]["state"] == "SHOCK"
        assert rows[0]["trigger_reason"] == "state==SHOCK"

    def test_nightly_no_trigger_does_not_write(self, tmp_path, monkeypatch):
        from lib import config
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)

        snap = _make_snap(asof="2026-07-08", state="QUIET", score=10, flip=0)
        result = sd.build_nightly(snap=snap)

        assert result["active"] is False
        firings_path = tmp_path / "reflexes" / "shock_deescalation" / "firings.jsonl"
        assert not firings_path.exists()

    def test_nightly_keep_first_on_second_call(self, tmp_path, monkeypatch):
        from lib import config
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)

        snap = _make_snap(asof="2026-07-07", state="SHOCK", score=75, flip=30)
        sd.build_nightly(snap=snap)
        # second call same date with different score
        snap2 = dict(snap)
        snap2["repricing_coherence"] = _make_coh("SHOCK", 80, 30)
        sd.build_nightly(snap=snap2)

        firings_path = tmp_path / "reflexes" / "shock_deescalation" / "firings.jsonl"
        rows = [json.loads(l) for l in firings_path.read_text().splitlines() if l.strip()]
        assert len(rows) == 1  # keep-first: only the first firing kept
        assert rows[0]["score"] == 75


# ── shock_state computation ─────────────────────────────────────────────────────

class TestShockStateComputation:
    def test_active_state_from_firing(self):
        today = date(2026, 7, 8)
        firing = {"date": "2026-07-07", "score": 75, "state": "SHOCK",
                  "trigger_reason": "state==SHOCK", "primary_driver": "ai_semis",
                  "expires": "2026-07-10"}
        shock_state = sd._compute_shock_state([firing], today)
        assert shock_state["active"] is True
        assert shock_state["since"] == "2026-07-07"
        assert shock_state["expires"] == "2026-07-10"

    def test_inactive_when_expired(self):
        today = date(2026, 7, 14)
        firing = {"date": "2026-07-07", "score": 75, "state": "SHOCK",
                  "trigger_reason": "state==SHOCK", "primary_driver": "ai_semis",
                  "expires": "2026-07-10"}
        shock_state = sd._compute_shock_state([firing], today)
        assert shock_state["active"] is False

    def test_inactive_when_no_firings(self):
        shock_state = sd._compute_shock_state([], date(2026, 7, 7))
        assert shock_state["active"] is False
        assert shock_state["schema"] == "shock_deescalation.v1"

    def test_most_recent_active_firing_selected(self):
        today = date(2026, 7, 9)
        firings = [
            {"date": "2026-06-25", "score": 50, "state": "ELEVATED",
             "trigger_reason": "two_consecutive_ELEVATED_with_flip",
             "primary_driver": "ai_semis", "expires": "2026-06-30"},
            {"date": "2026-07-07", "score": 75, "state": "SHOCK",
             "trigger_reason": "state==SHOCK", "primary_driver": "ai_semis",
             "expires": "2026-07-14"},
        ]
        shock_state = sd._compute_shock_state(firings, today)
        assert shock_state["active"] is True
        assert shock_state["since"] == "2026-07-07"


# ── backscan regression ─────────────────────────────────────────────────────────

class TestBackscanRegression:
    def test_backscan_finds_20260707(self):
        """2026-07-07 was SHOCK(75) in the committed log — must appear as would-have-fired."""
        rows = sd.backscan()
        dates = {r["date"] for r in rows}
        assert "2026-07-07" in dates, (
            f"Sanity anchor: 2026-07-07 must be a would-have-fired date. Got: {sorted(dates)}"
        )

    def test_backscan_is_descriptive_labeled(self):
        """All rows must carry descriptive=True."""
        rows = sd.backscan()
        for r in rows:
            assert r.get("descriptive") is True, f"Row {r['date']} missing descriptive=True"

    def test_backscan_returns_list(self):
        result = sd.backscan()
        assert isinstance(result, list)
        # Every row has the expected fields
        for r in result:
            assert "date" in r
            assert "score" in r
            assert "state" in r
            assert "trigger_reason" in r
            assert "expires" in r

    def test_backscan_trigger_reasons_valid(self):
        rows = sd.backscan()
        valid_reasons = {"state==SHOCK", "two_consecutive_ELEVATED_with_flip"}
        for r in rows:
            assert r["trigger_reason"] in valid_reasons


# ── shock_state artifact schema ──────────────────────────────────────────────────

class TestShockStateSchema:
    def test_inactive_state_has_required_fields(self):
        s = sd._inactive_shock_state()
        for key in ("active", "score", "since", "expires", "reason", "reason_zh",
                    "trigger_reason", "primary_driver", "note", "note_zh", "schema"):
            assert key in s, f"Missing field: {key}"
        assert s["active"] is False
        assert s["schema"] == "shock_deescalation.v1"

    def test_active_state_has_required_fields(self):
        firing = {"date": "2026-07-07", "score": 75, "state": "SHOCK",
                  "trigger_reason": "state==SHOCK", "primary_driver": "ai_semis",
                  "expires": "2026-07-10"}
        s = sd._compute_shock_state([firing], date(2026, 7, 8))
        for key in ("active", "score", "since", "expires", "reason", "reason_zh",
                    "trigger_reason", "primary_driver", "note", "note_zh", "schema"):
            assert key in s, f"Missing field: {key}"
        assert s["active"] is True
        assert s["reason"]     # non-empty EN reason
        assert s["reason_zh"]  # non-empty ZH reason
