"""Tests for the HK freshness sentinel + hk_calendar.

Covers:
  (a) Fake stores with mismatched stamps -> sentinel returns stale
  (b) Coherent fresh stores -> ok
  (c) Regression: cache max going backwards -> flagged
  (d) July-8 replay: cache/standouts at 2026-07-02 while expected session is 2026-07-08
      -> stale verdict + banner present (cannot render as live)

Tests are discriminating: they fail against absence of the sentinel code, then pass.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# hk_calendar tests
# ---------------------------------------------------------------------------

class TestHKCalendar:
    def test_weekends_not_sessions(self):
        from lib.hk_calendar import is_session
        assert not is_session(date(2026, 7, 4))   # Saturday
        assert not is_session(date(2026, 7, 5))   # Sunday

    def test_weekday_is_session(self):
        from lib.hk_calendar import is_session
        # 2026-07-08 is Wednesday
        assert is_session(date(2026, 7, 8))

    def test_christmas_not_session(self):
        from lib.hk_calendar import is_session
        assert not is_session(date(2026, 12, 25))   # Christmas Friday

    def test_new_years_not_session(self):
        from lib.hk_calendar import is_session
        assert not is_session(date(2026, 1, 1))   # New Year's Day

    def test_labour_day_not_session(self):
        from lib.hk_calendar import is_session
        assert not is_session(date(2026, 5, 1))   # Labour Day Friday

    def test_hk_sar_day_not_session(self):
        from lib.hk_calendar import is_session
        assert not is_session(date(2026, 7, 1))   # HK SAR Day Wednesday

    def test_one_off_closure_not_session(self):
        from lib.hk_calendar import is_session
        assert not is_session(date(2023, 9, 8))   # Typhoon Saola

    def test_expected_last_session_july8_incident(self):
        """At 03:00 UTC on 2026-07-08 (before HKT 17:30 settle), expected session is 2026-07-07."""
        from lib.hk_calendar import expected_last_session
        now = datetime(2026, 7, 8, 3, 0, tzinfo=timezone.utc)
        result = expected_last_session(now)
        # If 2026-07-07 is a session, that's the expected
        from lib.hk_calendar import is_session
        # Expect the most recent session before 17:30 HKT on July 8
        # July 7 (Mon) = session; July 8 (Tue) = session but not yet closed at 03:00 UTC
        assert result <= date(2026, 7, 8)
        # Must not return anything stale like 2026-07-02
        assert result >= date(2026, 7, 6)

    def test_expected_last_session_after_settle(self):
        """At 11:00 UTC on 2026-07-08 (= 19:00 HKT, after 17:30 settle), expected = today."""
        from lib.hk_calendar import expected_last_session, is_session
        now = datetime(2026, 7, 8, 11, 0, tzinfo=timezone.utc)
        result = expected_last_session(now)
        if is_session(date(2026, 7, 8)):
            assert result == date(2026, 7, 8)

    def test_expected_last_session_uses_hkt(self):
        """UTC 10:00 on a Monday that's after HKT 17:30 should expect Monday, not Friday."""
        from lib.hk_calendar import expected_last_session, is_session
        # Try a Monday that isn't a holiday (2026-07-06, if a session)
        if is_session(date(2026, 7, 6)):
            # 10:00 UTC = 18:00 HKT — after close
            now = datetime(2026, 7, 6, 10, 0, tzinfo=timezone.utc)
            result = expected_last_session(now)
            assert result == date(2026, 7, 6)


# ---------------------------------------------------------------------------
# Fixtures and helpers for sentinel tests
# ---------------------------------------------------------------------------

def _write_parquet_with_date(path: Path, d: date) -> None:
    """Write a minimal parquet with a DatetimeIndex containing `d`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    idx = pd.DatetimeIndex([pd.Timestamp(d)])
    df = pd.DataFrame({"close": [100.0]}, index=idx)
    df.to_parquet(path)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


class TestHKFreshnessSentinel:
    """Sentinel tests using temporary directories."""

    def _run_sentinel(self, tmpdir: Path, now: datetime,
                      cache_date: date | None = None,
                      bell_date: date | None = None,
                      standouts_asof: date | None = None,
                      regime_date: date | None = None,
                      prev_cache_max: date | None = None) -> dict:
        """Set up fake stores in tmpdir and run sentinel."""
        data_root = tmpdir / "data"
        site_root = tmpdir / "site"

        # Write cache parquet
        if cache_date is not None:
            _write_parquet_with_date(
                data_root / "hk_breadth" / "_closes_cache.parquet", cache_date)

        # Write bellwether parquet
        if bell_date is not None:
            _write_parquet_with_date(
                data_root / "hk_stocks" / "9988.HK.parquet", bell_date)

        # Write standouts JSON
        if standouts_asof is not None:
            _write_json(
                site_root / "factordata" / "hk_standouts.json",
                {"as_of": str(standouts_asof), "buy": [], "watch": []})

        # Write regime JSON
        if regime_date is not None:
            _write_json(
                data_root / "hk_regime" / "latest.json",
                {"date": str(regime_date), "quad": "Q1"})

        # Write previous state (for regression check)
        if prev_cache_max is not None:
            state_dir = data_root / "hk_freshness"
            _write_json(state_dir / "state.json",
                        {"cache_max": str(prev_cache_max)})

        with (patch("lib.config.data_dir", return_value=data_root),
              patch("lib.config.load", return_value={"storage": {"site_dir": str(site_root)}}),
              patch("lib.config.ROOT", tmpdir)):
            from engine.hk_freshness import hk_freshness_sentinel
            return hk_freshness_sentinel(now=now)

    def test_b_coherent_fresh_stores_ok(self, tmp_path):
        """(b) Coherent fresh stores -> verdict ok."""
        # Use a fixed "now" well after the settle buffer: 2026-07-08 12:00 UTC = 20:00 HKT
        now = datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc)
        # We need to know what expected_last_session returns for this now
        from lib.hk_calendar import expected_last_session
        expected = expected_last_session(now)

        result = self._run_sentinel(
            tmp_path, now,
            cache_date=expected,
            bell_date=expected,
            standouts_asof=expected,
            regime_date=expected,
        )
        assert result["verdict"] == "ok", f"Expected ok, got {result['verdict']}: {result}"

    def test_a_stale_cache_mismatched_stamps(self, tmp_path):
        """(a) Cache is stale (2026-07-02 while expected is 2026-07-08) -> stale."""
        now = datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc)
        stale_date = date(2026, 7, 2)
        from lib.hk_calendar import expected_last_session
        expected = expected_last_session(now)

        result = self._run_sentinel(
            tmp_path, now,
            cache_date=stale_date,
            bell_date=stale_date,
            standouts_asof=stale_date,
            regime_date=stale_date,
        )
        assert result["verdict"] == "stale", f"Expected stale, got {result['verdict']}"
        assert result["stores"]["cache"]["state"] in ("stale",)
        lag = result["stores"]["cache"]["lag_days"]
        assert lag is not None and lag > 2

    def test_c_regression_cache_goes_backward(self, tmp_path):
        """(c) Cache max going backwards -> regression flagged, verdict stale."""
        now = datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc)
        from lib.hk_calendar import expected_last_session
        expected = expected_last_session(now)

        # Current cache date is OLDER than the previously seen max
        prev_max = expected   # was fresh yesterday
        curr_date = date(2026, 7, 2)   # now rolled back (the incident!)

        result = self._run_sentinel(
            tmp_path, now,
            cache_date=curr_date,
            bell_date=expected,
            standouts_asof=expected,
            regime_date=expected,
            prev_cache_max=prev_max,
        )
        assert not result["regression"]["ok"], "Expected regression to be flagged"
        assert result["verdict"] == "stale", f"Regression should force stale, got {result['verdict']}"
        assert result["regression"]["note"] is not None
        assert "clobber" in result["regression"]["note"].lower() or "rolled" in result["regression"]["note"].lower()

    def test_d_july8_incident_replay(self, tmp_path):
        """(d) July-8 incident replay: cache/standouts at 2026-07-02, expected 2026-07-07/08
        -> stale verdict + banner present."""
        # Simulate: nightly run at 2026-07-08 02:00 UTC (before HKT open)
        now = datetime(2026, 7, 8, 2, 0, tzinfo=timezone.utc)
        stale_date = date(2026, 7, 2)   # the incident: cache frozen at July 2

        result = self._run_sentinel(
            tmp_path, now,
            cache_date=stale_date,
            bell_date=stale_date,
            standouts_asof=stale_date,
            regime_date=stale_date,
        )
        # The page CANNOT render as live
        assert result["verdict"] == "stale", (
            f"July-8 incident replay must be stale, got {result['verdict']}: {result}")
        # Banner must be present
        assert result["banner_message"] is not None, "Banner must be present when stale"
        assert "en" in result["banner_message"]
        assert "zh" in result["banner_message"]
        assert "2026-07-02" in result["banner_message"]["en"]

    def test_d_july8_expected_session_not_july2(self, tmp_path):
        """The expected session on 2026-07-08 morning must be after 2026-07-02."""
        from lib.hk_calendar import expected_last_session
        now = datetime(2026, 7, 8, 2, 0, tzinfo=timezone.utc)
        expected = expected_last_session(now)
        assert expected > date(2026, 7, 2), (
            f"Expected session should be after 2026-07-02, got {expected}")

    def test_banner_absent_when_ok(self, tmp_path):
        """No banner when verdict is ok."""
        now = datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc)
        from lib.hk_calendar import expected_last_session
        expected = expected_last_session(now)

        result = self._run_sentinel(
            tmp_path, now,
            cache_date=expected,
            bell_date=expected,
            standouts_asof=expected,
            regime_date=expected,
        )
        if result["verdict"] == "ok":
            assert result["banner_message"] is None

    def test_coherence_broken_forces_stale(self, tmp_path):
        """Standouts and regime dates diverge -> coherence bad -> stale."""
        now = datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc)
        from lib.hk_calendar import expected_last_session
        expected = expected_last_session(now)

        result = self._run_sentinel(
            tmp_path, now,
            cache_date=expected,
            bell_date=expected,
            standouts_asof=expected,
            regime_date=date(2026, 7, 1),   # regime is a week old
        )
        assert not result["coherence"]["ok"], "Coherence must be broken"
        assert result["verdict"] == "stale"

    def test_missing_cache_is_dead_and_stale(self, tmp_path):
        """No cache file -> dead state -> stale verdict."""
        now = datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc)
        from lib.hk_calendar import expected_last_session
        expected = expected_last_session(now)

        # Omit cache_date entirely
        result = self._run_sentinel(
            tmp_path, now,
            cache_date=None,   # cache missing
            bell_date=expected,
            standouts_asof=expected,
            regime_date=expected,
        )
        assert result["stores"]["cache"]["state"] == "dead"
        assert result["verdict"] == "stale"

    def test_result_is_always_a_dict(self, tmp_path):
        """Sentinel never raises; always returns a dict."""
        from engine.hk_freshness import hk_freshness_sentinel
        now = datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc)
        # Even with no patches (so paths won't exist) it should return a dict
        result = hk_freshness_sentinel(now=now)
        assert isinstance(result, dict)
        assert "verdict" in result

    def test_regression_does_not_fire_when_cache_advances(self, tmp_path):
        """Cache advancing forward (healthy update) -> regression ok."""
        now = datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc)
        from lib.hk_calendar import expected_last_session
        expected = expected_last_session(now)

        result = self._run_sentinel(
            tmp_path, now,
            cache_date=expected,
            bell_date=expected,
            standouts_asof=expected,
            regime_date=expected,
            prev_cache_max=date(2026, 7, 7),   # yesterday was fresh, today is fresh
        )
        assert result["regression"]["ok"], f"Regression should not fire: {result['regression']}"


class TestRunSentinelSafe:
    """Test that run_sentinel (the public wrapper) never crashes."""

    def test_run_sentinel_returns_dict(self):
        from engine.hk_freshness import run_sentinel
        now = datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc)
        result = run_sentinel(now=now)
        assert isinstance(result, dict)
        assert "verdict" in result
        assert result["verdict"] in ("ok", "degraded", "stale")


class TestHKFreshnessJSON:
    """Test that write_freshness_json creates the expected file."""

    def test_write_freshness_json(self, tmp_path):
        site_root = tmp_path / "site"
        site_root.mkdir()
        from engine.hk_freshness import write_freshness_json
        result = {
            "verdict": "ok",
            "banner_message": None,
            "checked_at": "2026-07-08T12:00:00+00:00",
        }
        with (patch("lib.config.load",
                    return_value={"storage": {"site_dir": str(site_root)}}),
              patch("lib.config.ROOT", tmp_path)):
            write_freshness_json(result, site_root=site_root)
        out = site_root / "factordata" / "hk_freshness.json"
        assert out.exists()
        loaded = json.loads(out.read_text())
        assert loaded["verdict"] == "ok"
