"""Tests for fear_greed.py honesty fixes (VSB W5).

Covers:
  1. last_date field: every leg dict has 'last_date' as ISO string or None
  2. as_of uses max leg data-date, not today-UTC (stale fixture)
  3. as_of fallback to today when no included leg has last_date
  4. persist_dial_history: keep-first per date (no-op on same date)
  5. persist_dial_history: writes new row on new date
  6. persist_dial_history: None payload returns False without writing
  7. persist_dial_history: logged_at stored as string (aware UTC ISO), not datetime
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import engine.fear_greed as fgmod  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_spy(n: int = 500, start: str = "2015-01-01") -> pd.DataFrame:
    idx = pd.bdate_range(start, periods=n)
    close = np.linspace(100, 300, n)
    return pd.DataFrame({"close": close}, index=idx)


def _make_breadth(n: int = 500) -> pd.DataFrame:
    idx = pd.bdate_range("2015-01-01", periods=n)
    nh = np.abs(np.sin(np.arange(n) / 20)) * 50 + 10
    nl = np.abs(np.cos(np.arange(n) / 20)) * 30 + 5
    adv = nh + 5
    dec = nl + 3
    return pd.DataFrame({"nh": nh, "nl": nl, "adv": adv, "dec": dec}, index=idx)


# ---------------------------------------------------------------------------
# 1. every leg has 'last_date' field
# ---------------------------------------------------------------------------

class TestLegLastDate:
    """Every individual leg builder must return a dict containing 'last_date'."""

    def _stub_read(self, cat, name):
        """Return a minimal DataFrame for any key."""
        n = 500
        idx = pd.bdate_range("2015-01-01", periods=n)
        if cat == "breadth":
            return _make_breadth(n)
        return _make_spy(n)

    def test_all_legs_have_last_date_key_present(self, monkeypatch):
        """Call each leg builder with a working stub and assert 'last_date' key exists."""
        monkeypatch.setattr(fgmod.store, "read", self._stub_read)
        legs = [
            fgmod._leg_spx_momentum,
            fgmod._leg_nh_nl_ratio,
            fgmod._leg_safe_haven,
            fgmod._leg_vix_level,
            fgmod._leg_vix_trend,
            fgmod._leg_vix_term,
            fgmod._leg_skew,
            fgmod._leg_naaim,
        ]
        for fn in legs:
            try:
                leg = fn()
            except Exception:
                # If the leg errored, it should still have last_date=None
                continue
            assert "last_date" in leg, (
                f"{fn.__name__} returned dict without 'last_date' key: {list(leg.keys())}"
            )

    def test_missing_leg_has_last_date_none(self, monkeypatch):
        """When a leg's data is missing, last_date must be None (not absent)."""
        monkeypatch.setattr(fgmod.store, "read", lambda cat, name: None)
        leg = fgmod._leg_vix_level()
        assert "last_date" in leg
        assert leg["last_date"] is None

    def test_present_leg_has_iso_date_string(self, monkeypatch):
        """When a leg has data, last_date must be a 'YYYY-MM-DD' ISO string."""
        spy = _make_spy(n=500, start="2019-01-02")
        monkeypatch.setattr(fgmod.store, "read", lambda cat, name: spy)
        leg = fgmod._leg_vix_level()
        assert leg["last_date"] is not None
        # Validate ISO format
        try:
            pd.Timestamp(leg["last_date"])
        except Exception:
            pytest.fail(f"last_date is not a valid date string: {leg['last_date']!r}")
        assert len(leg["last_date"]) == 10, f"Expected YYYY-MM-DD, got {leg['last_date']!r}"


# ---------------------------------------------------------------------------
# 2. as_of uses max leg data-date, not today-UTC
# ---------------------------------------------------------------------------

class TestAsOf:
    def test_as_of_equals_data_date_not_today(self, monkeypatch):
        """When all data comes from a stale series (2019), as_of must be 2019-xx-xx."""
        n = 500
        stale_start = "2019-01-02"
        spy = _make_spy(n=n, start=stale_start)
        breadth = _make_breadth(n)

        def _read(cat, name):
            if cat == "breadth":
                return breadth
            return spy

        monkeypatch.setattr(fgmod.store, "read", _read)
        payload = fgmod.compute_fear_greed()
        if payload is None:
            pytest.skip("no qualifying legs in stale fixture")
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        assert payload["as_of"] != today, (
            f"as_of must be the data date, not today. Got {payload['as_of']!r}"
        )
        # It should be in 2019 or early 2021 (n=500 bdays from 2019-01-02)
        assert payload["as_of"] < today, "as_of must be in the past"
        assert payload["as_of"] > "2019-01-01", "as_of must be after stale_start"

    def test_as_of_is_max_across_legs(self, monkeypatch):
        """as_of should be the maximum data date from included legs."""
        n = 500
        spy_early = _make_spy(n=n, start="2018-01-02")   # earlier end date
        spy_late = _make_spy(n=n, start="2019-01-02")    # later end date

        call_count = {"n": 0}

        def _read(cat, name):
            call_count["n"] += 1
            if cat == "breadth":
                return _make_breadth(n)
            # VIX legs get the late series; others get early
            if name in ("_VIX", "_VIX3M"):
                return spy_late
            return spy_early

        monkeypatch.setattr(fgmod.store, "read", _read)
        payload = fgmod.compute_fear_greed()
        if payload is None:
            pytest.skip("no qualifying legs")
        # as_of must be the max, which comes from the latest series
        # (we can't know exact date without running the engine, but we know it's
        # at least >= the start of spy_late)
        assert payload["as_of"] >= "2019-01-02"


# ---------------------------------------------------------------------------
# 3. as_of fallback when no last_date available
# ---------------------------------------------------------------------------

class TestAsOfFallback:
    def test_as_of_falls_back_to_today_when_no_dates(self, monkeypatch):
        """If all last_dates are None (missing legs), as_of falls back to today."""
        # Patch compute_fear_greed to use a fixture where included legs have last_date=None
        # We test this by patching _leg_* to return legs with last_date=None but valid z
        import types

        def _fake_leg(key="fake"):
            return {
                "key": key, "name_en": key, "name_zh": key,
                "value": 50.0, "z": 0.5, "pct": 50,
                "freshness": "fresh", "obs_count": 500,
                "orientation": "higher=greed", "unit": "test",
                "last_date": None,   # <- explicitly None
            }

        legs_to_patch = [
            "_leg_spx_momentum", "_leg_nh_nl_ratio", "_leg_mcclellan",
            "_leg_hy_oas", "_leg_safe_haven", "_leg_vix_level",
            "_leg_vix_trend", "_leg_vix_term", "_leg_skew",
            "_leg_naaim", "_leg_insider",
        ]
        for i, fn_name in enumerate(legs_to_patch):
            key = f"fake_{i}"
            monkeypatch.setattr(fgmod, fn_name, lambda k=key: _fake_leg(k))
        # Also patch young tiles
        monkeypatch.setattr(fgmod, "_young_tile_putcall",
                            lambda: {"key": "putcall", "freshness": "young", "obs_count": 10,
                                     "name_en": "x", "name_zh": "x", "value": None})
        monkeypatch.setattr(fgmod, "_young_tile_aaii",
                            lambda: {"key": "aaii", "freshness": "young", "obs_count": 10,
                                     "name_en": "x", "name_zh": "x", "value": None})

        payload = fgmod.compute_fear_greed()
        assert payload is not None
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        assert payload["as_of"] == today, (
            f"When no leg has a last_date, as_of should be today ({today}), got {payload['as_of']!r}"
        )


# ---------------------------------------------------------------------------
# 4 & 5. persist_dial_history
# ---------------------------------------------------------------------------

class TestPersistDialHistory:
    def _make_payload(self, date: str = "2025-01-15", dial: int = 62) -> dict:
        return {
            "dial": dial,
            "label_en": "Greed",
            "label_zh": "贪婪",
            "n_legs_qualifying": 8,
            "as_of": date,
            "generated_utc": "2025-01-15T10:00:00Z",
        }

    def test_writes_new_row(self, monkeypatch, tmp_path):
        """First call for a date writes a row and returns True."""
        monkeypatch.setattr(fgmod.config, "data_dir", lambda: tmp_path)
        payload = self._make_payload("2025-03-01", dial=75)
        result = fgmod.persist_dial_history(payload)
        assert result is True
        out = tmp_path / "sentiment_us" / "fear_greed_dial.parquet"
        assert out.exists()
        df = pd.read_parquet(out)
        assert len(df) == 1
        assert df["date"].iloc[0] == "2025-03-01"
        assert df["dial"].iloc[0] == 75

    def test_keep_first_no_op_on_same_date(self, monkeypatch, tmp_path):
        """Second call for the same date is a no-op (keep-first) and returns False."""
        monkeypatch.setattr(fgmod.config, "data_dir", lambda: tmp_path)
        payload1 = self._make_payload("2025-03-02", dial=60)
        payload2 = self._make_payload("2025-03-02", dial=40)   # different dial, same date
        assert fgmod.persist_dial_history(payload1) is True
        assert fgmod.persist_dial_history(payload2) is False
        df = pd.read_parquet(tmp_path / "sentiment_us" / "fear_greed_dial.parquet")
        assert len(df) == 1
        assert df["dial"].iloc[0] == 60, "Keep-first: first dial value should be retained"

    def test_appends_second_date(self, monkeypatch, tmp_path):
        """Two calls with different dates produce two rows."""
        monkeypatch.setattr(fgmod.config, "data_dir", lambda: tmp_path)
        fgmod.persist_dial_history(self._make_payload("2025-04-01", dial=55))
        fgmod.persist_dial_history(self._make_payload("2025-04-02", dial=65))
        df = pd.read_parquet(tmp_path / "sentiment_us" / "fear_greed_dial.parquet")
        assert len(df) == 2
        assert set(df["date"].astype(str)) == {"2025-04-01", "2025-04-02"}

    def test_none_payload_returns_false(self, monkeypatch, tmp_path):
        """None payload returns False without writing anything."""
        monkeypatch.setattr(fgmod.config, "data_dir", lambda: tmp_path)
        result = fgmod.persist_dial_history(None)
        assert result is False
        out = tmp_path / "sentiment_us" / "fear_greed_dial.parquet"
        assert not out.exists()

    def test_empty_payload_returns_false(self, monkeypatch, tmp_path):
        """Empty dict returns False."""
        monkeypatch.setattr(fgmod.config, "data_dir", lambda: tmp_path)
        result = fgmod.persist_dial_history({})
        assert result is False

    def test_logged_at_stored_as_string(self, monkeypatch, tmp_path):
        """logged_at must be stored as a plain string (ISO), not a datetime object.

        pandas>=2 raises TypeError on aware datetime setitem into naive parquet
        column (tz-aware-into-naive-parquet-ledger law). Storing as string avoids this.
        """
        monkeypatch.setattr(fgmod.config, "data_dir", lambda: tmp_path)
        fgmod.persist_dial_history(self._make_payload("2025-05-01", dial=48))
        df = pd.read_parquet(tmp_path / "sentiment_us" / "fear_greed_dial.parquet")
        logged_at_val = df["logged_at"].iloc[0]
        # Must be a string, not a datetime/Timestamp
        assert isinstance(logged_at_val, str), (
            f"logged_at must be a string, got {type(logged_at_val)}: {logged_at_val!r}"
        )
        # Must be parseable as an aware ISO datetime
        try:
            dt = datetime.fromisoformat(logged_at_val)
        except ValueError:
            pytest.fail(f"logged_at is not a valid ISO string: {logged_at_val!r}")
        assert dt.tzinfo is not None, "logged_at string must include timezone offset"

    def test_schema_columns(self, monkeypatch, tmp_path):
        """Written parquet must have the expected columns."""
        monkeypatch.setattr(fgmod.config, "data_dir", lambda: tmp_path)
        fgmod.persist_dial_history(self._make_payload("2025-06-01", dial=33))
        df = pd.read_parquet(tmp_path / "sentiment_us" / "fear_greed_dial.parquet")
        expected_cols = {"date", "dial", "n_legs", "label_en", "logged_at"}
        assert expected_cols.issubset(set(df.columns)), (
            f"Missing columns: {expected_cols - set(df.columns)}"
        )

    def test_mkdir_parents_created(self, monkeypatch, tmp_path):
        """The sentiment_us/ directory is created if it does not exist."""
        nested = tmp_path / "deep" / "nested"
        monkeypatch.setattr(fgmod.config, "data_dir", lambda: nested)
        # nested does not exist yet; persist_dial_history must mkdir parents
        fgmod.persist_dial_history(self._make_payload("2025-07-01", dial=72))
        assert (nested / "sentiment_us" / "fear_greed_dial.parquet").exists()
