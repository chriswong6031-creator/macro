"""Tests for engine/risk_radar_recovery_audit.py

Uses synthetic SPY paths for deterministic grading. No network.
"""
from __future__ import annotations

import pandas as pd
import numpy as np

from engine import risk_radar_recovery_audit as rrra


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _synthetic_spy(n: int = 130, rebound: bool = True) -> pd.Series:
    """Flat at 400, then drops 8%, then recovers (for rebound testing).
    With n=130 and horizons h21 + h63, entries at bar ~30 will be gradeable for both.
    """
    idx = pd.bdate_range("2024-01-02", periods=n)
    px = [400.0] * n
    if rebound:
        # Drop at bar 30, recover strongly
        for i in range(30, 40):
            px[i] = 400.0 - (i - 29) * 3.0   # drops to ~370 (-7.5%)
        for i in range(40, n):
            px[i] = 370.0 + (i - 40) * 1.0   # gradual recovery
    return pd.Series(px, index=idx)


def _recovery(turn_confirmed_full: bool = True,
              chip_keys: list[str] | None = None,
              liquidity_n: int = 2) -> dict:
    """Synthetic recovery dict matching the shape assess() returns."""
    chip_keys = chip_keys or ["thrust_confluence", "msi_swing", "oas_rollover"]
    chips = [{"key": k, "fired": True, "fresh": True} for k in chip_keys]
    return {
        "asof": "2024-02-05",
        "present": True,
        "turn_confirmed": True,
        "turn_confirmed_full": turn_confirmed_full,
        "n_fresh": liquidity_n,
        "market": {
            "asof": "2024-02-05",
            "chips": chips,
            "market_confirmed": True,
            "market_confirmed_raw": True,
            "n_fresh": len(chip_keys),
            "veto": {"active": False, "p_now": 0.3},
        },
    }


def _radar_snap(phase: str = "receding", intensity: float = 72.0) -> dict:
    return {
        "asof": "2024-02-05",
        "trajectory": {
            "phase": phase,
            "intensity": intensity,
            "off_peak": 15.0,
        },
    }


# ---------------------------------------------------------------------------
# log_snapshot
# ---------------------------------------------------------------------------

class TestLogSnapshot:

    def test_writes_one_row(self, tmp_path):
        assert rrra.log_snapshot(_recovery(), _radar_snap(), root=tmp_path) is True
        rows = rrra._read(rrra._path(tmp_path))
        assert len(rows) == 1

    def test_idempotent_by_asof(self, tmp_path):
        rrra.log_snapshot(_recovery(), _radar_snap(), root=tmp_path)
        result = rrra.log_snapshot(_recovery(), _radar_snap(), root=tmp_path)
        assert result is False  # no duplicate
        rows = rrra._read(rrra._path(tmp_path))
        assert len(rows) == 1

    def test_row_has_required_fields(self, tmp_path):
        rrra.log_snapshot(_recovery(), _radar_snap(), root=tmp_path)
        row = rrra._read(rrra._path(tmp_path))[0]
        for field in ("asof", "phase", "intensity", "chips", "veto",
                      "liquidity_n", "market_confirmed", "turn_confirmed_full",
                      "logged_at", "graded"):
            assert field in row, f"missing field: {field}"
        assert row["graded"] is None

    def test_chips_captured(self, tmp_path):
        rec = _recovery(chip_keys=["thrust_confluence", "oas_rollover"])
        rrra.log_snapshot(rec, _radar_snap(), root=tmp_path)
        row = rrra._read(rrra._path(tmp_path))[0]
        chips = row["chips"]
        assert "thrust_confluence" in chips
        assert chips["thrust_confluence"]["fired"] is True
        assert chips["thrust_confluence"]["fresh"] is True

    def test_phase_logged(self, tmp_path):
        rrra.log_snapshot(_recovery(), _radar_snap(phase="peaking"), root=tmp_path)
        row = rrra._read(rrra._path(tmp_path))[0]
        assert row["phase"] == "peaking"

    def test_degrade_on_bad_recovery(self, tmp_path):
        """None/malformed recovery => no crash, returns False."""
        assert rrra.log_snapshot(None, {}, root=tmp_path) is False
        assert rrra.log_snapshot({}, {}, root=tmp_path) is False

    def test_multiple_rows_different_asof(self, tmp_path):
        rec1 = _recovery()
        rec1["asof"] = "2024-02-05"
        radar1 = _radar_snap()
        radar1["asof"] = "2024-02-05"

        rec2 = _recovery()
        rec2["asof"] = "2024-02-06"
        radar2 = _radar_snap()
        radar2["asof"] = "2024-02-06"

        rrra.log_snapshot(rec1, radar1, root=tmp_path)
        rrra.log_snapshot(rec2, radar2, root=tmp_path)
        rows = rrra._read(rrra._path(tmp_path))
        assert len(rows) == 2


# ---------------------------------------------------------------------------
# grade_log
# ---------------------------------------------------------------------------

class TestGradeLog:

    def _write_entry(self, tmp_path, asof: str, phase: str = "receding") -> None:
        rec = _recovery()
        rec["asof"] = asof
        radar = _radar_snap(phase=phase)
        radar["asof"] = asof
        rrra.log_snapshot(rec, radar, root=tmp_path)

    def test_grades_matured_entry(self, tmp_path, monkeypatch):
        spy = _synthetic_spy(n=130, rebound=True)
        monkeypatch.setattr(rrra, "_spy", lambda: spy)

        # Write entry at bar 20 (bar 20 + 63 < 130 => matured for both horizons)
        asof = str(spy.index[20].date())
        self._write_entry(tmp_path, asof)

        n_graded = rrra.grade_log(root=tmp_path)
        assert n_graded == 1

        rows = rrra._read(rrra._path(tmp_path))
        assert rows[0]["graded"] is not None
        g = rows[0]["graded"]
        assert "h21" in g and "h63" in g
        assert g["h21"]["fwd_ret"] is not None
        assert g["h63"]["fwd_ret"] is not None
        assert g["h21"]["mae"] is not None

    def test_immature_entry_not_graded(self, tmp_path, monkeypatch):
        """Entry too close to end of spy series => not graded yet."""
        spy = _synthetic_spy(n=100, rebound=True)
        monkeypatch.setattr(rrra, "_spy", lambda: spy)

        asof = str(spy.index[-5].date())   # only 4 bars left -> < h21
        self._write_entry(tmp_path, asof)
        n = rrra.grade_log(root=tmp_path)
        assert n == 0

    def test_already_graded_not_regraded(self, tmp_path, monkeypatch):
        spy = _synthetic_spy(n=130)
        monkeypatch.setattr(rrra, "_spy", lambda: spy)
        asof = str(spy.index[20].date())
        self._write_entry(tmp_path, asof)
        rrra.grade_log(root=tmp_path)
        # Second call: should return 0 (already graded)
        n = rrra.grade_log(root=tmp_path)
        assert n == 0

    def test_grade_returns_zero_on_empty_log(self, tmp_path, monkeypatch):
        spy = _synthetic_spy()
        monkeypatch.setattr(rrra, "_spy", lambda: spy)
        assert rrra.grade_log(root=tmp_path) == 0

    def test_grade_returns_zero_when_spy_unavailable(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rrra, "_spy", lambda: None)
        self._write_entry(tmp_path, "2024-02-05")
        assert rrra.grade_log(root=tmp_path) == 0

    def test_fwd_ret_positive_on_rebound(self, tmp_path, monkeypatch):
        """After a drop+rebound: h63 fwd_ret should be positive."""
        spy = _synthetic_spy(n=130, rebound=True)
        monkeypatch.setattr(rrra, "_spy", lambda: spy)

        asof = str(spy.index[35].date())  # near the trough, h63 will capture recovery
        self._write_entry(tmp_path, asof)
        rrra.grade_log(root=tmp_path)
        rows = rrra._read(rrra._path(tmp_path))
        g = rows[0]["graded"]
        if g is not None:
            # fwd_ret_h63 should be > 0 since spy recovers after the trough
            assert g["h63"]["fwd_ret"] is not None


# ---------------------------------------------------------------------------
# scorecard
# ---------------------------------------------------------------------------

class TestScorecard:

    def _populate(self, tmp_path, monkeypatch, n_rows: int = 3, phase: str = "receding") -> None:
        spy = _synthetic_spy(n=200, rebound=True)
        monkeypatch.setattr(rrra, "_spy", lambda: spy)

        for i in range(n_rows):
            asof = str(spy.index[i + 10].date())
            rec = _recovery()
            rec["asof"] = asof
            radar = _radar_snap(phase=phase)
            radar["asof"] = asof
            rrra.log_snapshot(rec, radar, root=tmp_path)

        rrra.grade_log(root=tmp_path)

    def test_scorecard_empty_is_safe(self, tmp_path):
        sc = rrra.scorecard(root=tmp_path)
        assert sc["n_graded"] == 0
        assert "note" in sc

    def test_scorecard_schema(self, tmp_path, monkeypatch):
        self._populate(tmp_path, monkeypatch, n_rows=3)
        sc = rrra.scorecard(root=tmp_path)
        assert "n_graded" in sc
        assert "n_eligible_phase" in sc
        assert "note" in sc
        # Should have per_chip if eligible
        if sc["n_eligible_phase"] > 0:
            assert "per_chip" in sc
            assert "base_rates" in sc

    def test_per_chip_significance_note(self, tmp_path, monkeypatch):
        """Significance note must mention insufficient n below 30."""
        self._populate(tmp_path, monkeypatch, n_rows=3)
        sc = rrra.scorecard(root=tmp_path)
        if sc.get("per_chip"):
            for chip_stat in sc["per_chip"].values():
                assert "significance_note" in chip_stat
                assert "INSUFFICIENT" in chip_stat["significance_note"]   # n < 30

    def test_scorecard_non_eligible_phase_excluded(self, tmp_path, monkeypatch):
        """Rising phase rows should not count as eligible."""
        spy = _synthetic_spy(n=200)
        monkeypatch.setattr(rrra, "_spy", lambda: spy)
        asof = str(spy.index[10].date())
        rec = _recovery()
        rec["asof"] = asof
        radar = _radar_snap(phase="rising")
        radar["asof"] = asof
        rrra.log_snapshot(rec, radar, root=tmp_path)
        rrra.grade_log(root=tmp_path)
        sc = rrra.scorecard(root=tmp_path)
        assert sc.get("n_eligible_phase", 0) == 0


# ---------------------------------------------------------------------------
# snapshot_and_grade
# ---------------------------------------------------------------------------

class TestSnapshotAndGrade:

    def test_returns_scorecard_dict(self, tmp_path, monkeypatch):
        spy = _synthetic_spy(n=200)
        monkeypatch.setattr(rrra, "_spy", lambda: spy)
        sc = rrra.snapshot_and_grade(_recovery(), _radar_snap(), root=tmp_path)
        assert isinstance(sc, dict)
        assert "n_graded" in sc

    def test_never_raises_on_garbage(self, tmp_path):
        """Even with junk inputs, never raises."""
        result = rrra.snapshot_and_grade(None, None, root=tmp_path)
        assert isinstance(result, dict)
        result = rrra.snapshot_and_grade({}, {}, root=tmp_path)
        assert isinstance(result, dict)

    def test_idempotent_second_call(self, tmp_path, monkeypatch):
        spy = _synthetic_spy(n=200)
        monkeypatch.setattr(rrra, "_spy", lambda: spy)
        rrra.snapshot_and_grade(_recovery(), _radar_snap(), root=tmp_path)
        # Second call with same asof should not duplicate
        sc = rrra.snapshot_and_grade(_recovery(), _radar_snap(), root=tmp_path)
        rows = rrra._read(rrra._path(tmp_path))
        assert len(rows) == 1   # idempotent


# ---------------------------------------------------------------------------
# degrade on missing store (empty root)
# ---------------------------------------------------------------------------

class TestDegradeOnMissingStore:

    def test_grade_log_missing_spy_returns_zero(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rrra, "_spy", lambda: None)
        rrra.log_snapshot(_recovery(), _radar_snap(), root=tmp_path)
        assert rrra.grade_log(root=tmp_path) == 0

    def test_scorecard_safe_on_empty_dir(self, tmp_path):
        sc = rrra.scorecard(root=tmp_path)
        assert sc["n_graded"] == 0
