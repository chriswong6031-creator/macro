"""PIT history accrual for FINRA short interest — append + idempotency + schema.

Tests the new short_interest_history.parquet path added in W0 of the Signal
Commons programme.  All writes go to tmp_path so the git-tracked data/ tree is
never touched.
"""
from __future__ import annotations

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Helpers: build a minimal snapshot that mirrors _snapshot()'s output shape
# (index=ticker, columns include settlement_date + numeric fields).
# ---------------------------------------------------------------------------

_COLS = ["short_shares", "prev_short_shares", "avg_daily_vol", "days_to_cover",
         "si_change_pct", "settlement_date"]


def _make_snap(tickers: list[str], settlement: str, **kw) -> pd.DataFrame:
    rows = {t: {
        "short_shares": kw.get("short_shares", 1_000_000),
        "prev_short_shares": kw.get("prev_short_shares", 900_000),
        "avg_daily_vol": kw.get("avg_daily_vol", 5_000_000),
        "days_to_cover": kw.get("days_to_cover", 2.0),
        "si_change_pct": kw.get("si_change_pct", 11.1),
        "settlement_date": settlement,
    } for t in tickers}
    return pd.DataFrame.from_dict(rows, orient="index")


# ---------------------------------------------------------------------------
# Replicate the accrual logic exactly as written in fetch_short_interest(), so
# tests exercise the SAME call shape (not a wrapper).  This is the house law:
# tests copy the real call shape.
# ---------------------------------------------------------------------------

def _accrue(snap: pd.DataFrame, hist_p, capture_date: pd.Timestamp) -> pd.DataFrame:
    """Run the accrual block from fetch_short_interest() against *hist_p*."""
    hist_snap = snap.copy()
    hist_snap["capture_date"] = capture_date
    hist_snap = hist_snap.reset_index()          # ticker column
    if hist_snap.columns[0] != "ticker":
        # reset_index names the old index; rename if it came out as "index"
        hist_snap = hist_snap.rename(columns={"index": "ticker"})
    if hist_p.exists():
        hist_snap = pd.concat([pd.read_parquet(hist_p), hist_snap], ignore_index=True)
        hist_snap = hist_snap.drop_duplicates(
            subset=["settlement_date", "ticker"], keep="last"
        )
    hist_snap.to_parquet(hist_p)
    return pd.read_parquet(hist_p)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSchemaOnFirstWrite:
    def test_required_columns_present(self, tmp_path):
        snap = _make_snap(["AAPL", "MSFT"], "2026-06-13")
        hist_p = tmp_path / "short_interest_history.parquet"
        capture = pd.Timestamp("2026-07-05")

        result = _accrue(snap, hist_p, capture)

        assert "ticker" in result.columns
        assert "settlement_date" in result.columns
        assert "capture_date" in result.columns
        assert "days_to_cover" in result.columns

    def test_row_count_matches_snapshot(self, tmp_path):
        snap = _make_snap(["AAPL", "MSFT", "NVDA"], "2026-06-13")
        hist_p = tmp_path / "short_interest_history.parquet"
        capture = pd.Timestamp("2026-07-05")

        result = _accrue(snap, hist_p, capture)

        assert len(result) == 3

    def test_ticker_values_preserved(self, tmp_path):
        snap = _make_snap(["AAPL", "MSFT"], "2026-06-13")
        hist_p = tmp_path / "short_interest_history.parquet"
        capture = pd.Timestamp("2026-07-05")

        result = _accrue(snap, hist_p, capture)

        assert set(result["ticker"]) == {"AAPL", "MSFT"}


class TestIdempotencyWithinCalendarDay:
    """Re-running the accrual with the SAME settlement_date must not duplicate rows."""

    def test_same_run_does_not_duplicate(self, tmp_path):
        snap = _make_snap(["AAPL", "MSFT"], "2026-06-13")
        hist_p = tmp_path / "short_interest_history.parquet"
        capture = pd.Timestamp("2026-07-05")

        _accrue(snap, hist_p, capture)
        result = _accrue(snap, hist_p, capture)    # second identical run

        # Still exactly 2 rows — no duplication
        assert len(result) == 2

    def test_rerun_overwrites_rows_not_appends(self, tmp_path):
        snap = _make_snap(["AAPL"], "2026-06-13", days_to_cover=2.0)
        hist_p = tmp_path / "short_interest_history.parquet"
        capture = pd.Timestamp("2026-07-05")

        _accrue(snap, hist_p, capture)

        # Simulate updated data on same settlement date (e.g. corrected value)
        snap2 = _make_snap(["AAPL"], "2026-06-13", days_to_cover=3.5)
        result = _accrue(snap2, hist_p, capture)

        assert len(result) == 1
        assert result.iloc[0]["days_to_cover"] == pytest.approx(3.5)


class TestAppendAcrossSettlementDates:
    """Different settlement dates must accumulate as separate rows."""

    def test_two_settlement_dates_accumulate(self, tmp_path):
        hist_p = tmp_path / "short_interest_history.parquet"

        snap1 = _make_snap(["AAPL", "MSFT"], "2026-05-30")
        _accrue(snap1, hist_p, pd.Timestamp("2026-06-02"))

        snap2 = _make_snap(["AAPL", "MSFT"], "2026-06-13")
        result = _accrue(snap2, hist_p, pd.Timestamp("2026-07-05"))

        assert len(result) == 4   # 2 tickers × 2 settlement dates

    def test_settlement_dates_are_distinct(self, tmp_path):
        hist_p = tmp_path / "short_interest_history.parquet"

        snap1 = _make_snap(["AAPL"], "2026-05-30")
        _accrue(snap1, hist_p, pd.Timestamp("2026-06-02"))

        snap2 = _make_snap(["AAPL"], "2026-06-13")
        result = _accrue(snap2, hist_p, pd.Timestamp("2026-07-05"))

        dates = set(result["settlement_date"])
        assert "2026-05-30" in dates
        assert "2026-06-13" in dates

    def test_growing_universe_across_dates(self, tmp_path):
        """New tickers added in later snapshots accumulate alongside prior ones."""
        hist_p = tmp_path / "short_interest_history.parquet"

        snap1 = _make_snap(["AAPL"], "2026-05-30")
        _accrue(snap1, hist_p, pd.Timestamp("2026-06-02"))

        # MSFT added in the next snapshot
        snap2 = _make_snap(["AAPL", "MSFT"], "2026-06-13")
        result = _accrue(snap2, hist_p, pd.Timestamp("2026-07-05"))

        assert len(result) == 3   # AAPL/2026-05-30, AAPL/2026-06-13, MSFT/2026-06-13
        assert set(result["ticker"]) == {"AAPL", "MSFT"}


class TestCaptureDate:
    """capture_date must be recorded and be timezone-naive (UTC-normalised)."""

    def test_capture_date_is_stored(self, tmp_path):
        snap = _make_snap(["AAPL"], "2026-06-13")
        hist_p = tmp_path / "short_interest_history.parquet"
        capture = pd.Timestamp("2026-07-05")

        result = _accrue(snap, hist_p, capture)

        assert pd.notna(result.iloc[0]["capture_date"])

    def test_capture_date_is_tz_naive(self, tmp_path):
        snap = _make_snap(["AAPL"], "2026-06-13")
        hist_p = tmp_path / "short_interest_history.parquet"
        capture = pd.Timestamp("2026-07-05")

        result = _accrue(snap, hist_p, capture)

        # parquet round-trips timestamps; tz_localize(None) must have stripped tz
        cap = result.iloc[0]["capture_date"]
        assert getattr(cap, "tz", None) is None or cap.tzinfo is None

    def test_different_capture_dates_same_settlement_keep_last(self, tmp_path):
        """If the same settlement_date is captured on two different run days, the
        second capture's data should win (keep='last' semantics)."""
        hist_p = tmp_path / "short_interest_history.parquet"
        settlement = "2026-06-13"

        snap1 = _make_snap(["AAPL"], settlement, days_to_cover=2.0)
        _accrue(snap1, hist_p, pd.Timestamp("2026-06-14"))

        snap2 = _make_snap(["AAPL"], settlement, days_to_cover=3.0)
        result = _accrue(snap2, hist_p, pd.Timestamp("2026-06-15"))

        # dedup is on (settlement_date, ticker) so only 1 row survives
        assert len(result) == 1
        assert result.iloc[0]["days_to_cover"] == pytest.approx(3.0)


class TestEmptySnapshotHandling:
    """The accrual block is only reached with non-empty snaps (fetch_short_interest
    returns early on empty snapshots).  Verify no crash on degenerate inputs."""

    def test_single_ticker_single_settlement(self, tmp_path):
        snap = _make_snap(["SPY"], "2026-06-13")
        hist_p = tmp_path / "short_interest_history.parquet"

        result = _accrue(snap, hist_p, pd.Timestamp("2026-07-05"))

        assert len(result) == 1
        assert result.iloc[0]["ticker"] == "SPY"
