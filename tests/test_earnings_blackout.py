"""Unit tests for engine/earnings_blackout.py — W1.5 earnings-blackout hygiene veto.

Tests cover (per task spec):
  1. Passed-date row is dropped (in_blackout=False, reason='next_date_in_past').
  2. Boundary: day 3 is IN blackout (in_blackout=True), day 4 is OUT.
  3. Stale row fails open (in_blackout=False, stale=True).
  4. Missing ticker fails open (in_blackout=False, stale=False).
  5. next_time is carried through in the result dict.

No live I/O — all tests use tmp_path-backed synthetic parquets or store overrides.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import engine.earnings_blackout as eb  # noqa: E402


# ── helpers ────────────────────────────────────────────────────────────────

def _make_store(tmp_path: Path, rows: dict) -> Path:
    """Write a minimal earnings parquet with the given ticker->row mapping.

    Each value in rows is a dict: {next_date, next_time, as_of}.
    Returns the path to the written parquet.
    """
    records = []
    for ticker, d in rows.items():
        records.append({
            "ticker": ticker.upper(),
            "next_date": d.get("next_date", ""),
            "next_time": d.get("next_time", ""),
            "eps_forecast": d.get("eps_forecast", None),
            "surprises_json": d.get("surprises_json", "[]"),
            "as_of": d.get("as_of", ""),
        })
    df = pd.DataFrame(records).set_index("ticker")
    p = tmp_path / "earnings.parquet"
    df.to_parquet(p)
    return p


def _fresh_as_of(today: date, days_ago_td: int = 5) -> str:
    """Return an ISO-format as_of string that is days_ago_td trading days before today.

    Uses a simple calendar-day approximation (not holiday-aware) which is
    fine for unit-test freshness checks.
    """
    # Approximate: 5 td ≈ 7 calendar days
    offset = timedelta(days=int(days_ago_td * 1.5))
    ts = pd.Timestamp(today) - offset
    return ts.isoformat() + "+00:00"


def _stale_as_of(today: date) -> str:
    """Return an ISO-format as_of that is 15+ trading days before today (stale)."""
    ts = pd.Timestamp(today) - timedelta(days=25)  # ~18 td
    return ts.isoformat() + "+00:00"


# Use a fixed reference "today" so tests are deterministic.
TODAY = date(2026, 7, 5)


# ── 1. Passed-date row is dropped ──────────────────────────────────────────

class TestPassedDateDropped:
    def test_yesterday_not_blackout(self, tmp_path):
        """A next_date strictly before today must never veto."""
        eb.clear_cache()
        yesterday = (pd.Timestamp(TODAY) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        p = _make_store(tmp_path, {
            "AAPL": {"next_date": yesterday,
                     "next_time": "time-after-hours",
                     "as_of": _fresh_as_of(TODAY)},
        })
        result = eb.assess("AAPL", today=TODAY, store_path=p)
        assert result["in_blackout"] is False
        assert result["reason"] == "next_date_in_past"

    def test_one_week_ago_not_blackout(self, tmp_path):
        eb.clear_cache()
        past = (pd.Timestamp(TODAY) - pd.Timedelta(days=7)).strftime("%Y-%m-%d")
        p = _make_store(tmp_path, {
            "MSFT": {"next_date": past, "as_of": _fresh_as_of(TODAY)},
        })
        result = eb.assess("MSFT", today=TODAY, store_path=p)
        assert result["in_blackout"] is False
        assert result["reason"] == "next_date_in_past"


# ── 2. Boundary: day 3 IN / day 4 OUT ──────────────────────────────────────

class TestBoundaryDays:
    """k=3 is the primary.  We use business-day-offset next_dates relative to TODAY.

    TODAY=2026-07-05 (Sunday, but that's fine — bdate_range handles it).
    We use bdate_range to advance N business days from TODAY.
    """

    @staticmethod
    def _next_bdate(n: int) -> str:
        """Return the date n business days after TODAY."""
        bd = pd.bdate_range(TODAY, periods=n + 1)
        return bd[-1].strftime("%Y-%m-%d")

    def test_same_day_in_blackout(self, tmp_path):
        """k=0: announcement on same day as today => in_blackout."""
        eb.clear_cache()
        same = pd.Timestamp(TODAY).strftime("%Y-%m-%d")
        p = _make_store(tmp_path, {
            "TSLA": {"next_date": same, "as_of": _fresh_as_of(TODAY)},
        })
        result = eb.assess("TSLA", today=TODAY, store_path=p)
        assert result["in_blackout"] is True
        assert result["days_to_earnings"] == 0

    def test_1td_in_blackout(self, tmp_path):
        eb.clear_cache()
        next_d = self._next_bdate(1)
        p = _make_store(tmp_path, {
            "GOOGL": {"next_date": next_d, "as_of": _fresh_as_of(TODAY)},
        })
        result = eb.assess("GOOGL", today=TODAY, store_path=p)
        assert result["in_blackout"] is True
        assert result["days_to_earnings"] == 1

    def test_2td_in_blackout(self, tmp_path):
        eb.clear_cache()
        next_d = self._next_bdate(2)
        p = _make_store(tmp_path, {
            "AMZN": {"next_date": next_d, "as_of": _fresh_as_of(TODAY)},
        })
        result = eb.assess("AMZN", today=TODAY, store_path=p)
        assert result["in_blackout"] is True
        assert result["days_to_earnings"] == 2

    def test_3td_in_blackout(self, tmp_path):
        eb.clear_cache()
        next_d = self._next_bdate(3)
        p = _make_store(tmp_path, {
            "META": {"next_date": next_d, "as_of": _fresh_as_of(TODAY)},
        })
        result = eb.assess("META", today=TODAY, store_path=p)
        assert result["in_blackout"] is True
        assert result["days_to_earnings"] == 3

    def test_4td_outside_blackout(self, tmp_path):
        """Day 4: outside the k=3 window => in_blackout=False."""
        eb.clear_cache()
        next_d = self._next_bdate(4)
        p = _make_store(tmp_path, {
            "NVDA": {"next_date": next_d, "as_of": _fresh_as_of(TODAY)},
        })
        result = eb.assess("NVDA", today=TODAY, store_path=p)
        assert result["in_blackout"] is False
        assert result["days_to_earnings"] == 4
        assert result["reason"] == "outside_window"

    def test_10td_outside_blackout(self, tmp_path):
        eb.clear_cache()
        next_d = self._next_bdate(10)
        p = _make_store(tmp_path, {
            "SPY": {"next_date": next_d, "as_of": _fresh_as_of(TODAY)},
        })
        result = eb.assess("SPY", today=TODAY, store_path=p)
        assert result["in_blackout"] is False
        assert result["days_to_earnings"] >= 4


# ── 3. Stale row fails open ─────────────────────────────────────────────────

class TestStaleRowFailOpen:
    def test_stale_row_not_blackout(self, tmp_path):
        """Row with as_of > 10 td ago must fail open."""
        eb.clear_cache()
        future = (pd.Timestamp(TODAY) + pd.Timedelta(days=2)).strftime("%Y-%m-%d")
        p = _make_store(tmp_path, {
            "IBM": {"next_date": future, "as_of": _stale_as_of(TODAY)},
        })
        result = eb.assess("IBM", today=TODAY, store_path=p)
        assert result["in_blackout"] is False
        assert result["stale"] is True
        assert result["reason"] == "row_stale"

    def test_stale_row_carries_next_date(self, tmp_path):
        """Even on stale fail-open, next_date is returned for display."""
        eb.clear_cache()
        future = (pd.Timestamp(TODAY) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        p = _make_store(tmp_path, {
            "GE": {"next_date": future, "as_of": _stale_as_of(TODAY)},
        })
        result = eb.assess("GE", today=TODAY, store_path=p)
        assert result["in_blackout"] is False
        assert result["stale"] is True
        assert result["next_date"] == future


# ── 4. Missing ticker fails open ────────────────────────────────────────────

class TestMissingTickerFailOpen:
    def test_unknown_ticker(self, tmp_path):
        eb.clear_cache()
        p = _make_store(tmp_path, {
            "AAPL": {"next_date": "2026-07-10", "as_of": _fresh_as_of(TODAY)},
        })
        result = eb.assess("ZZZZZ", today=TODAY, store_path=p)
        assert result["in_blackout"] is False
        assert result["stale"] is False
        assert result["reason"] == "ticker_not_in_store"

    def test_missing_store(self, tmp_path):
        """No parquet file at all => fail-open."""
        eb.clear_cache()
        p = tmp_path / "nonexistent.parquet"
        result = eb.assess("AAPL", today=TODAY, store_path=p)
        assert result["in_blackout"] is False
        assert result["stale"] is True
        assert "missing" in result["reason"].lower() or "empty" in result["reason"].lower()

    def test_case_insensitive(self, tmp_path):
        """Ticker lookup is case-insensitive."""
        eb.clear_cache()
        future = (pd.Timestamp(TODAY) + pd.Timedelta(days=2)).strftime("%Y-%m-%d")
        p = _make_store(tmp_path, {
            "AAPL": {"next_date": future, "as_of": _fresh_as_of(TODAY)},
        })
        result_lower = eb.assess("aapl", today=TODAY, store_path=p)
        eb.clear_cache()
        result_upper = eb.assess("AAPL", today=TODAY, store_path=p)
        assert result_lower["in_blackout"] == result_upper["in_blackout"]


# ── 5. next_time carried through ────────────────────────────────────────────

class TestNextTimeCarriedThrough:
    def test_next_time_present_in_result(self, tmp_path):
        eb.clear_cache()
        future = (pd.Timestamp(TODAY) + pd.Timedelta(days=2)).strftime("%Y-%m-%d")
        p = _make_store(tmp_path, {
            "COST": {"next_date": future,
                     "next_time": "time-after-hours",
                     "as_of": _fresh_as_of(TODAY)},
        })
        result = eb.assess("COST", today=TODAY, store_path=p)
        assert result["next_time"] == "time-after-hours"

    def test_next_time_premarket(self, tmp_path):
        eb.clear_cache()
        future = (pd.Timestamp(TODAY) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        p = _make_store(tmp_path, {
            "WMT": {"next_date": future,
                    "next_time": "time-pre-market",
                    "as_of": _fresh_as_of(TODAY)},
        })
        result = eb.assess("WMT", today=TODAY, store_path=p)
        assert result["next_time"] == "time-pre-market"
        assert result["in_blackout"] is True

    def test_next_time_none_when_missing(self, tmp_path):
        """When next_time column is NaN/empty, result next_time is None."""
        eb.clear_cache()
        future = (pd.Timestamp(TODAY) + pd.Timedelta(days=2)).strftime("%Y-%m-%d")
        p = _make_store(tmp_path, {
            "XOM": {"next_date": future, "next_time": None,
                    "as_of": _fresh_as_of(TODAY)},
        })
        result = eb.assess("XOM", today=TODAY, store_path=p)
        assert result["next_time"] is None


# ── 6. store_staleness helper ────────────────────────────────────────────────

class TestStoreStaleness:
    def test_fresh_store_not_stale(self, tmp_path):
        eb.clear_cache()
        # as_of = 3 td ago
        p = _make_store(tmp_path, {
            "AAPL": {"next_date": "2026-07-10", "as_of": _fresh_as_of(TODAY, days_ago_td=3)},
        })
        info = eb.store_staleness(today=TODAY, store_path=p)
        assert info["stale"] is False
        assert info["store_missing"] is False

    def test_missing_store_is_stale(self, tmp_path):
        eb.clear_cache()
        p = tmp_path / "no_file.parquet"
        info = eb.store_staleness(today=TODAY, store_path=p)
        assert info["stale"] is True
        assert info["store_missing"] is True


# ── 7. Result dict schema completeness ──────────────────────────────────────

class TestResultSchema:
    _REQUIRED_KEYS = frozenset({
        "in_blackout", "days_to_earnings", "next_date",
        "next_time", "as_of_age_td", "stale", "reason",
    })

    def _assert_schema(self, result: dict) -> None:
        missing = self._REQUIRED_KEYS - set(result.keys())
        assert not missing, f"Missing keys in result: {missing}"
        assert isinstance(result["in_blackout"], bool)
        assert isinstance(result["stale"], bool)

    def test_schema_normal_case(self, tmp_path):
        eb.clear_cache()
        future = (pd.Timestamp(TODAY) + pd.Timedelta(days=2)).strftime("%Y-%m-%d")
        p = _make_store(tmp_path, {
            "JNJ": {"next_date": future, "as_of": _fresh_as_of(TODAY)},
        })
        result = eb.assess("JNJ", today=TODAY, store_path=p)
        self._assert_schema(result)

    def test_schema_fail_open(self, tmp_path):
        eb.clear_cache()
        p = tmp_path / "nope.parquet"
        result = eb.assess("ANY", today=TODAY, store_path=p)
        self._assert_schema(result)

    def test_schema_past_date(self, tmp_path):
        eb.clear_cache()
        past = (pd.Timestamp(TODAY) - pd.Timedelta(days=5)).strftime("%Y-%m-%d")
        p = _make_store(tmp_path, {
            "BA": {"next_date": past, "as_of": _fresh_as_of(TODAY)},
        })
        result = eb.assess("BA", today=TODAY, store_path=p)
        self._assert_schema(result)
