"""Tests for engine.pick_lab.ledger (spec §4).

Covers:
  - append_fires: authority enforcement, keep-first dedup
  - append_grades: authority enforcement, keep-first dedup
  - is_open: refire lockout helper
  - load_fires / load_grades: round-trip
  - LH file separation (PL-R6)

Run:
    python -m pytest tests/test_pick_lab_ledger.py -x -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.pick_lab.ledger import (
    FIRE_KEY,
    GRADE_KEY,
    append_fires,
    append_grades,
    is_open,
    keep_first,
    load_fires,
    load_grades,
    load_jsonl,
    write_jsonl,
    FIRES_PATH,
    GRADES_PATH,
    LH_FIRES_PATH,
    LH_GRADES_PATH,
)


# ------------------------------------------------------------------ fixtures --


def _fire(engine_id="plab_1d_pure", ticker="AAPL", fire_date="2024-01-10",
          exec_date="2024-01-11", **kwargs) -> dict:
    row = {
        "engine_id": engine_id,
        "ticker": ticker,
        "fire_date": fire_date,
        "exec_date": exec_date,
        "rank": 1,
        "close_at_fire": 150.0,
        "sector": "Technology",
        "regime_calm": 0.7,
        "regime_stress": 0.2,
        "config_hash": "abc123",
        "authority": "display_only",
    }
    row.update(kwargs)
    return row


def _grade(engine_id="plab_1d_pure", ticker="AAPL", fire_date="2024-01-10",
           horizon=21, **kwargs) -> dict:
    row = {
        "engine_id": engine_id,
        "ticker": ticker,
        "fire_date": fire_date,
        "horizon": horizon,
        "exec_date": "2024-01-11",
        "exec_price": 150.0,
        "ret_abs": 0.05,
        "ret_excess_spy": 0.02,
        "ret_rel_sector": 0.01,
        "mfe": 0.08,
        "mae": -0.03,
        "matured": True,
        "graded_at": "2024-02-15T10:00:00+00:00",
        "authority": "display_only",
    }
    row.update(kwargs)
    return row


_TDATE_INDEX = pd.bdate_range("2024-01-02", "2024-12-31")


# ================================================================ keep_first ==


class TestKeepFirst:
    def test_first_wins(self):
        rows = [
            {"engine_id": "e", "ticker": "T", "fire_date": "2024-01-10", "val": "first"},
            {"engine_id": "e", "ticker": "T", "fire_date": "2024-01-10", "val": "second"},
        ]
        result = keep_first(rows, FIRE_KEY)
        assert len(result) == 1
        assert result[0]["val"] == "first"

    def test_different_keys_kept(self):
        rows = [
            {"engine_id": "e", "ticker": "T", "fire_date": "2024-01-10"},
            {"engine_id": "e", "ticker": "T", "fire_date": "2024-01-11"},
        ]
        result = keep_first(rows, FIRE_KEY)
        assert len(result) == 2

    def test_empty_input(self):
        assert keep_first([], FIRE_KEY) == []

    def test_grade_key(self):
        rows = [
            {"engine_id": "e", "ticker": "T", "fire_date": "2024-01-10", "horizon": 21, "val": "a"},
            {"engine_id": "e", "ticker": "T", "fire_date": "2024-01-10", "horizon": 21, "val": "b"},
            {"engine_id": "e", "ticker": "T", "fire_date": "2024-01-10", "horizon": 63, "val": "c"},
        ]
        result = keep_first(rows, GRADE_KEY)
        assert len(result) == 2
        assert result[0]["val"] == "a"
        assert result[1]["val"] == "c"


# ================================================================ append_fires =


class TestAppendFires:
    def test_write_and_read(self, tmp_path, monkeypatch):
        """Round-trip: write a fire and read it back."""
        monkeypatch.setattr("engine.pick_lab.ledger.FIRES_PATH",
                            tmp_path / "fires.jsonl")
        fire = _fire()
        n = append_fires([fire])
        assert n == 1
        loaded = load_fires()
        assert len(loaded) == 1
        assert loaded[0]["ticker"] == "AAPL"

    def test_authority_enforced(self, tmp_path, monkeypatch):
        """Rows without authority='display_only' raise ValueError."""
        monkeypatch.setattr("engine.pick_lab.ledger.FIRES_PATH",
                            tmp_path / "fires.jsonl")
        bad = _fire(authority="raw")
        with pytest.raises(ValueError, match="display_only"):
            append_fires([bad])

    def test_dedup_keep_first(self, tmp_path, monkeypatch):
        """Same (engine_id, ticker, fire_date) written twice → only 1 row stored."""
        monkeypatch.setattr("engine.pick_lab.ledger.FIRES_PATH",
                            tmp_path / "fires.jsonl")
        fire = _fire()
        n1 = append_fires([fire])
        n2 = append_fires([fire])
        assert n1 == 1
        assert n2 == 0
        loaded = load_fires()
        assert len(loaded) == 1

    def test_different_tickers_both_written(self, tmp_path, monkeypatch):
        monkeypatch.setattr("engine.pick_lab.ledger.FIRES_PATH",
                            tmp_path / "fires.jsonl")
        append_fires([_fire(ticker="AAPL"), _fire(ticker="MSFT")])
        loaded = load_fires()
        assert {r["ticker"] for r in loaded} == {"AAPL", "MSFT"}

    def test_empty_list_noop(self, tmp_path, monkeypatch):
        monkeypatch.setattr("engine.pick_lab.ledger.FIRES_PATH",
                            tmp_path / "fires.jsonl")
        n = append_fires([])
        assert n == 0

    def test_lh_fires_separate_file(self, tmp_path, monkeypatch):
        """hold_thesis=True writes to lh_fires.jsonl, not fires.jsonl."""
        entry_path = tmp_path / "fires.jsonl"
        lh_path = tmp_path / "lh_fires.jsonl"
        monkeypatch.setattr("engine.pick_lab.ledger.FIRES_PATH", entry_path)
        monkeypatch.setattr("engine.pick_lab.ledger.LH_FIRES_PATH", lh_path)
        append_fires([_fire()], hold_thesis=True)
        assert not entry_path.exists()
        assert lh_path.exists()

    def test_lh_fires_do_not_mix_with_entry(self, tmp_path, monkeypatch):
        """LH fires and entry fires go to separate files."""
        entry_path = tmp_path / "fires.jsonl"
        lh_path = tmp_path / "lh_fires.jsonl"
        monkeypatch.setattr("engine.pick_lab.ledger.FIRES_PATH", entry_path)
        monkeypatch.setattr("engine.pick_lab.ledger.LH_FIRES_PATH", lh_path)
        append_fires([_fire(engine_id="plab_1d_pure")], hold_thesis=False)
        append_fires([_fire(engine_id="plab_lh_compounder")], hold_thesis=True)
        entry = load_fires()
        lh = load_fires(hold_thesis=True)
        assert len(entry) == 1
        assert len(lh) == 1
        assert entry[0]["engine_id"] == "plab_1d_pure"
        assert lh[0]["engine_id"] == "plab_lh_compounder"


# ================================================================ append_grades =


class TestAppendGrades:
    def test_write_and_read(self, tmp_path, monkeypatch):
        monkeypatch.setattr("engine.pick_lab.ledger.GRADES_PATH",
                            tmp_path / "grades.jsonl")
        g = _grade()
        n = append_grades([g])
        assert n == 1
        loaded = load_grades()
        assert len(loaded) == 1

    def test_authority_enforced(self, tmp_path, monkeypatch):
        monkeypatch.setattr("engine.pick_lab.ledger.GRADES_PATH",
                            tmp_path / "grades.jsonl")
        bad = _grade(authority="raw")
        with pytest.raises(ValueError, match="display_only"):
            append_grades([bad])

    def test_dedup_grade_key(self, tmp_path, monkeypatch):
        """Same (engine_id, ticker, fire_date, horizon) → only 1 row kept."""
        monkeypatch.setattr("engine.pick_lab.ledger.GRADES_PATH",
                            tmp_path / "grades.jsonl")
        g = _grade()
        append_grades([g])
        append_grades([g])
        loaded = load_grades()
        assert len(loaded) == 1

    def test_different_horizons_both_kept(self, tmp_path, monkeypatch):
        monkeypatch.setattr("engine.pick_lab.ledger.GRADES_PATH",
                            tmp_path / "grades.jsonl")
        append_grades([_grade(horizon=21), _grade(horizon=63)])
        loaded = load_grades()
        assert len(loaded) == 2
        horizons = {r["horizon"] for r in loaded}
        assert horizons == {21, 63}

    def test_lh_grades_separate_file(self, tmp_path, monkeypatch):
        entry_path = tmp_path / "grades.jsonl"
        lh_path = tmp_path / "lh_grades.jsonl"
        monkeypatch.setattr("engine.pick_lab.ledger.GRADES_PATH", entry_path)
        monkeypatch.setattr("engine.pick_lab.ledger.LH_GRADES_PATH", lh_path)
        append_grades([_grade(horizon=126)], hold_thesis=True)
        assert not entry_path.exists()
        assert lh_path.exists()


# ================================================================ is_open =====


class TestIsOpen:
    """Refire lockout: ticker is 'open' if last fire < lockout sessions ago."""

    def _make_fires(self, fire_date: str, engine_id="plab_1d_pure",
                    ticker="AAPL") -> list[dict]:
        return [{
            "engine_id": engine_id,
            "ticker": ticker,
            "fire_date": fire_date,
        }]

    def test_open_when_fired_recently(self):
        """Fire 5 sessions ago with lockout=21 → still open."""
        # Trading dates: 2024-01-02 to 2024-12-31
        dates = _TDATE_INDEX
        # Current date = 2024-01-10 (~6 sessions after 2024-01-02)
        sub = dates[dates <= pd.Timestamp("2024-01-10")]
        fires = self._make_fires("2024-01-05")
        result = is_open("plab_1d_pure", "AAPL", sub, fires, lockout_sessions=21)
        assert bool(result) is True

    def test_not_open_when_lockout_elapsed(self):
        """Fire 30 sessions ago with lockout=21 → not open."""
        dates = _TDATE_INDEX
        # Fire on Jan 2, check on Feb 13 = ~30 business days later
        sub = dates[dates <= pd.Timestamp("2024-02-13")]
        fires = self._make_fires("2024-01-02")
        result = is_open("plab_1d_pure", "AAPL", sub, fires, lockout_sessions=21)
        assert bool(result) is False

    def test_not_open_when_no_fires(self):
        """No fires → not open."""
        dates = _TDATE_INDEX
        result = is_open("plab_1d_pure", "AAPL", dates, [], lockout_sessions=21)
        assert bool(result) is False

    def test_open_respects_engine_id(self):
        """Lockout is per (engine_id, ticker) — different engine = not open."""
        dates = _TDATE_INDEX
        sub = dates[dates <= pd.Timestamp("2024-01-10")]
        fires = self._make_fires("2024-01-05", engine_id="plab_1d_pure")
        # Check for different engine
        result = is_open("plab_1d_regime", "AAPL", sub, fires, lockout_sessions=21)
        assert bool(result) is False

    def test_open_respects_ticker(self):
        """Lockout is per ticker — different ticker = not open."""
        dates = _TDATE_INDEX
        sub = dates[dates <= pd.Timestamp("2024-01-10")]
        fires = self._make_fires("2024-01-05", ticker="AAPL")
        result = is_open("plab_1d_pure", "MSFT", sub, fires, lockout_sessions=21)
        assert bool(result) is False

    def test_lh_lockout_63(self):
        """LH lockout=63: fired 30 sessions ago → still open."""
        dates = _TDATE_INDEX
        # 30 sessions after 2024-01-02 ≈ 2024-02-13
        sub = dates[dates <= pd.Timestamp("2024-02-13")]
        fires = self._make_fires("2024-01-02", engine_id="plab_lh_compounder")
        result = is_open("plab_lh_compounder", "AAPL", sub, fires, lockout_sessions=63)
        assert bool(result) is True

    def test_lh_lockout_63_elapsed(self):
        """LH lockout=63: fired 70 sessions ago → not open."""
        dates = _TDATE_INDEX
        # 70 business days after 2024-01-02 ≈ 2024-04-10
        sub = dates[dates <= pd.Timestamp("2024-04-10")]
        fires = self._make_fires("2024-01-02", engine_id="plab_lh_compounder")
        result = is_open("plab_lh_compounder", "AAPL", sub, fires, lockout_sessions=63)
        assert bool(result) is False

    def test_empty_trading_dates(self):
        """Empty trading date index → not open (safe default)."""
        fires = self._make_fires("2024-01-05")
        result = is_open("plab_1d_pure", "AAPL", pd.DatetimeIndex([]), fires, 21)
        assert bool(result) is False


# ================================================================ write_jsonl ==


class TestWriteJsonl:
    def test_atomic_overwrite(self, tmp_path):
        path = tmp_path / "test.jsonl"
        rows = [{"engine_id": "e", "ticker": "T", "fire_date": "2024-01-01",
                 "authority": "display_only"}]
        write_jsonl(path, rows)
        loaded = load_jsonl(path)
        assert len(loaded) == 1

    def test_authority_enforced(self, tmp_path):
        path = tmp_path / "test.jsonl"
        with pytest.raises(ValueError, match="display_only"):
            write_jsonl(path, [{"authority": "raw"}])

    def test_empty_list_creates_empty_file(self, tmp_path):
        path = tmp_path / "test.jsonl"
        write_jsonl(path, [])
        loaded = load_jsonl(path)
        assert loaded == []
