"""W0b infrastructure tests — healthcare dispersion program.

(a) sector_holdings history archiver: appends and is idempotent per (as_of, etf).
(b) EW sector ETF tickers present in config.yml yahoo.tickers.ew_sectors.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402

# ---------------------------------------------------------------------------
# Expected EW ticker set (RGI stands in for RSPI which Yahoo does not serve)
# ---------------------------------------------------------------------------
EW_TICKERS = {
    "RSPH",  # Health Care
    "RSPT",  # Information Technology
    "RSPD",  # Consumer Discretionary
    "RSPS",  # Consumer Staples
    "RSPG",  # Energy
    "RSPF",  # Financials
    "RSPU",  # Utilities
    "RGI",   # Industrials (legacy; RSPI not served by Yahoo as of 2026-07-05)
    "RSPM",  # Materials
    "RSPC",  # Communication Services
    "RSPR",  # Real Estate
}


# ---------------------------------------------------------------------------
# Helper: build a minimal snap DataFrame matching _fetch_fund output shape
# ---------------------------------------------------------------------------

def _make_snap(as_of: date, n: int = 3) -> pd.DataFrame:
    """Return a snapshot DataFrame as _fetch_fund would produce it."""
    rows = pd.DataFrame({
        "ticker": [f"T{i}" for i in range(n)],
        "name": [f"Name {i}" for i in range(n)],
        "weight_pct": [round(10.0 + i, 2) for i in range(n)],
        "rank": list(range(1, n + 1)),
    })
    rows.index = pd.to_datetime([as_of] * n)
    return rows


# ---------------------------------------------------------------------------
# (a) History archiver tests
# ---------------------------------------------------------------------------

class TestHoldingsHistoryArchiver:
    """Unit tests for SectorHoldingsAdapter._append_history."""

    def _adapter(self, tmp_path: Path):
        """Return a SectorHoldingsAdapter with data_dir monkeypatched to tmp_path."""
        from collectors.sector_holdings import SectorHoldingsAdapter
        import lib.config as cfg_mod

        # Patch config.data_dir() to use tmp_path for this test
        original_data_dir = cfg_mod.data_dir

        def patched_data_dir():
            return tmp_path

        cfg_mod.data_dir = patched_data_dir  # type: ignore[method-assign]
        adapter = SectorHoldingsAdapter.__new__(SectorHoldingsAdapter)
        adapter.group = "sector_holdings"
        yield adapter
        cfg_mod.data_dir = original_data_dir  # type: ignore[method-assign]

    def test_append_creates_history_file(self, tmp_path):
        """_append_history creates history.parquet on first call."""
        from collectors.sector_holdings import SectorHoldingsAdapter
        import lib.config as cfg_mod

        original = cfg_mod.data_dir
        cfg_mod.data_dir = lambda: tmp_path  # type: ignore[method-assign]
        try:
            (tmp_path / "sector_holdings").mkdir()
            adapter = SectorHoldingsAdapter.__new__(SectorHoldingsAdapter)
            adapter.group = "sector_holdings"
            snap = _make_snap(date(2026, 7, 5))
            adapter._append_history("XLV", snap)
            hist_path = tmp_path / "sector_holdings" / "history.parquet"
            assert hist_path.exists()
            df = pd.read_parquet(hist_path)
            assert list(df.columns) == ["as_of", "etf", "ticker", "name", "weight_pct", "rank"]
            assert len(df) == 3
            assert (df["etf"] == "XLV").all()
        finally:
            cfg_mod.data_dir = original  # type: ignore[method-assign]

    def test_append_idempotent_same_day(self, tmp_path):
        """Re-running on the same day replaces rather than duplicates rows."""
        from collectors.sector_holdings import SectorHoldingsAdapter
        import lib.config as cfg_mod

        original = cfg_mod.data_dir
        cfg_mod.data_dir = lambda: tmp_path  # type: ignore[method-assign]
        try:
            (tmp_path / "sector_holdings").mkdir()
            adapter = SectorHoldingsAdapter.__new__(SectorHoldingsAdapter)
            adapter.group = "sector_holdings"
            snap = _make_snap(date(2026, 7, 5))
            adapter._append_history("XLV", snap)
            adapter._append_history("XLV", snap)  # second call — same day
            hist_path = tmp_path / "sector_holdings" / "history.parquet"
            df = pd.read_parquet(hist_path)
            # Should still have exactly 3 rows (not 6)
            xlv = df[df["etf"] == "XLV"]
            as_of_date = pd.Timestamp("2026-07-05").date()
            xlv_today = xlv[pd.to_datetime(xlv["as_of"]).dt.date == as_of_date]
            assert len(xlv_today) == 3, (
                f"Expected 3 rows after idempotent re-run, got {len(xlv_today)}"
            )
        finally:
            cfg_mod.data_dir = original  # type: ignore[method-assign]

    def test_append_accumulates_across_days(self, tmp_path):
        """Two different as_of dates produce separate rows in history."""
        from collectors.sector_holdings import SectorHoldingsAdapter
        import lib.config as cfg_mod

        original = cfg_mod.data_dir
        cfg_mod.data_dir = lambda: tmp_path  # type: ignore[method-assign]
        try:
            (tmp_path / "sector_holdings").mkdir()
            adapter = SectorHoldingsAdapter.__new__(SectorHoldingsAdapter)
            adapter.group = "sector_holdings"
            snap_d1 = _make_snap(date(2026, 7, 4))
            snap_d2 = _make_snap(date(2026, 7, 5))
            adapter._append_history("XLV", snap_d1)
            adapter._append_history("XLV", snap_d2)
            hist_path = tmp_path / "sector_holdings" / "history.parquet"
            df = pd.read_parquet(hist_path)
            dates = pd.to_datetime(df["as_of"]).dt.date.unique()
            assert date(2026, 7, 4) in dates
            assert date(2026, 7, 5) in dates
            assert len(df) == 6  # 3 rows × 2 dates
        finally:
            cfg_mod.data_dir = original  # type: ignore[method-assign]

    def test_multiple_etfs_do_not_cross_contaminate(self, tmp_path):
        """Rows for different ETFs on the same day coexist without collision."""
        from collectors.sector_holdings import SectorHoldingsAdapter
        import lib.config as cfg_mod

        original = cfg_mod.data_dir
        cfg_mod.data_dir = lambda: tmp_path  # type: ignore[method-assign]
        try:
            (tmp_path / "sector_holdings").mkdir()
            adapter = SectorHoldingsAdapter.__new__(SectorHoldingsAdapter)
            adapter.group = "sector_holdings"
            as_of = date(2026, 7, 5)
            adapter._append_history("XLV", _make_snap(as_of))
            adapter._append_history("XLK", _make_snap(as_of))
            hist_path = tmp_path / "sector_holdings" / "history.parquet"
            df = pd.read_parquet(hist_path)
            assert set(df["etf"].unique()) == {"XLV", "XLK"}
            # Idempotency for XLV must not affect XLK rows
            adapter._append_history("XLV", _make_snap(as_of))
            df2 = pd.read_parquet(hist_path)
            assert len(df2[df2["etf"] == "XLK"]) == 3
            assert len(df2[df2["etf"] == "XLV"]) == 3
        finally:
            cfg_mod.data_dir = original  # type: ignore[method-assign]


# ---------------------------------------------------------------------------
# (b) EW ticker list presence in config
# ---------------------------------------------------------------------------

def test_ew_tickers_in_config():
    """All expected EW sector tickers must be listed in config.yml yahoo.tickers.ew_sectors."""
    cfg = config.load()
    ew = set(cfg["yahoo"]["tickers"].get("ew_sectors", []))
    missing = EW_TICKERS - ew
    assert not missing, (
        f"EW tickers missing from config.yml yahoo.tickers.ew_sectors: {sorted(missing)}"
    )


def test_ew_tickers_all_known_good():
    """ew_sectors list must not contain any unknown tickers beyond the expected set."""
    cfg = config.load()
    ew = set(cfg["yahoo"]["tickers"].get("ew_sectors", []))
    unknown = ew - EW_TICKERS
    assert not unknown, (
        f"Unexpected tickers in ew_sectors (not in empirically verified set): {sorted(unknown)}"
    )


def test_ew_sectors_key_exists():
    """config.yml must have a yahoo.tickers.ew_sectors key (not silently absent)."""
    cfg = config.load()
    assert "ew_sectors" in cfg["yahoo"]["tickers"], (
        "yahoo.tickers.ew_sectors key is missing from config.yml"
    )
