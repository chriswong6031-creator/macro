"""tests/test_symbol_directory.py — Synthetic unit tests for LHB-R8 symbol-directory
archival collector (collectors/symbol_directory.py).

All tests are fully synthetic (no network calls):
  A. Parse fixture blobs -> correct rows/flags.
  B. Snapshot-once-per-day idempotency (tmp_path + monkeypatched data_dir).
  C. CIK-map once-per-ISO-week idempotency.
  D. Manifest contents after a write cycle.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Fixtures — synthetic file text bodies
# ---------------------------------------------------------------------------

_NASDAQLISTED_TEXT = """\
Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size
AAPL|Apple Inc.|Q|N|N|100
MSFT|Microsoft Corporation|Q|N|N|100
TESTX|Test Issue Corp|Q|Y|N|100
AAPL$|Apple Inc. Preferred|Q|N|N|100
File Creation Time: 7/12/2026 06:30:00\
"""

_OTHERLISTED_TEXT = """\
ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol
SPY|SPDR S&P 500 ETF Trust|P|SPY|Y|100|N|SPY
BRK/A|Berkshire Hathaway Inc.|N|BRK/A|N|1|N|
File Creation Time: 7/12/2026 06:31:00\
"""

_SEC_TICKERS_JSON = {
    "0": {"cik_str": 320193, "ticker": "AAPL",  "title": "Apple Inc."},
    "1": {"cik_str": 789019, "ticker": "MSFT",  "title": "Microsoft Corp"},
    "2": {"cik_str": 93751,  "ticker": "SPY",   "title": "SPDR S&P 500 ETF Trust"},
}


# ---------------------------------------------------------------------------
# Helpers — import the module under test after we can patch data_dir
# ---------------------------------------------------------------------------

def _import_module():
    import importlib
    import collectors.symbol_directory as m
    importlib.reload(m)
    return m


# ---------------------------------------------------------------------------
# A. Parse fixture blobs
# ---------------------------------------------------------------------------

class TestParsing:
    def test_nasdaqlisted_basic_rows(self):
        from collectors.symbol_directory import _parse_nasdaqlisted
        df = _parse_nasdaqlisted(_NASDAQLISTED_TEXT)
        symbols = set(df["symbol"].tolist())
        # AAPL and MSFT should be present
        assert "AAPL" in symbols
        assert "MSFT" in symbols

    def test_nasdaqlisted_preferred_dropped(self):
        """Symbols containing '$' (preferred shares) must be excluded."""
        from collectors.symbol_directory import _parse_nasdaqlisted
        df = _parse_nasdaqlisted(_NASDAQLISTED_TEXT)
        assert "AAPL$" not in df["symbol"].tolist()

    def test_nasdaqlisted_test_issue_flag(self):
        """TESTX has Test Issue = Y -> test_issue=True."""
        from collectors.symbol_directory import _parse_nasdaqlisted
        df = _parse_nasdaqlisted(_NASDAQLISTED_TEXT)
        testx = df[df["symbol"] == "TESTX"]
        assert len(testx) == 1
        assert testx.iloc[0]["test_issue"] == True  # noqa: E712

    def test_nasdaqlisted_normal_issue_flag(self):
        """AAPL has Test Issue = N -> test_issue=False."""
        from collectors.symbol_directory import _parse_nasdaqlisted
        df = _parse_nasdaqlisted(_NASDAQLISTED_TEXT)
        aapl = df[df["symbol"] == "AAPL"]
        assert len(aapl) == 1
        assert aapl.iloc[0]["test_issue"] == False  # noqa: E712

    def test_nasdaqlisted_footer_dropped(self):
        """Footer line ('File Creation Time: ...') must not produce a data row."""
        from collectors.symbol_directory import _parse_nasdaqlisted
        df = _parse_nasdaqlisted(_NASDAQLISTED_TEXT)
        # footer would appear as a symbol containing 'File'
        assert not any("File" in str(s) for s in df["symbol"].tolist())

    def test_nasdaqlisted_exchange_is_nasdaq(self):
        from collectors.symbol_directory import _parse_nasdaqlisted
        df = _parse_nasdaqlisted(_NASDAQLISTED_TEXT)
        assert (df["exchange"] == "NASDAQ").all()

    def test_nasdaqlisted_source_column(self):
        from collectors.symbol_directory import _parse_nasdaqlisted
        df = _parse_nasdaqlisted(_NASDAQLISTED_TEXT)
        assert (df["source"] == "nasdaqlisted").all()

    def test_otherlisted_etf_flag(self):
        """SPY has ETF = Y -> etf=True; BRK/A has ETF = N -> etf=False."""
        from collectors.symbol_directory import _parse_otherlisted
        df = _parse_otherlisted(_OTHERLISTED_TEXT)
        spy = df[df["symbol"] == "SPY"]
        assert len(spy) == 1
        assert spy.iloc[0]["etf"] == True  # noqa: E712
        brk = df[df["symbol"] == "BRK/A"]
        assert len(brk) == 1
        assert brk.iloc[0]["etf"] == False  # noqa: E712

    def test_otherlisted_exchange_code(self):
        """SPY is on P (NYSE Arca); BRK/A is on N (NYSE)."""
        from collectors.symbol_directory import _parse_otherlisted
        df = _parse_otherlisted(_OTHERLISTED_TEXT)
        spy = df[df["symbol"] == "SPY"]
        assert spy.iloc[0]["exchange"] == "P"

    def test_otherlisted_footer_dropped(self):
        from collectors.symbol_directory import _parse_otherlisted
        df = _parse_otherlisted(_OTHERLISTED_TEXT)
        assert not any("File" in str(s) for s in df["symbol"].tolist())

    def test_otherlisted_source_column(self):
        from collectors.symbol_directory import _parse_otherlisted
        df = _parse_otherlisted(_OTHERLISTED_TEXT)
        assert (df["source"] == "otherlisted").all()


# ---------------------------------------------------------------------------
# B. Snapshot-once-per-day idempotency
# ---------------------------------------------------------------------------

class TestSnapshotIdempotency:
    def _make_adapter(self, tmp_data_dir: Path):
        """Return an adapter instance with data_dir patched to tmp_data_dir."""
        import collectors.symbol_directory as m
        return m.SymbolDirectoryAdapter(), m

    def test_snapshot_written_first_call(self, tmp_path):
        """First call today: snapshot parquet is written."""
        import collectors.symbol_directory as m

        today_str = date.today().isoformat()

        with patch("collectors.symbol_directory.config") as mock_cfg, \
             patch("collectors.symbol_directory._fetch_text") as mock_text, \
             patch("collectors.symbol_directory._fetch_sec_json") as mock_sec:

            mock_cfg.data_dir.return_value = tmp_path
            mock_text.side_effect = [_NASDAQLISTED_TEXT, _OTHERLISTED_TEXT]
            mock_sec.return_value = _SEC_TICKERS_JSON

            adapter = m.SymbolDirectoryAdapter()
            result = adapter.fetch()

        snap_path = tmp_path / "symbol_directory" / "snapshots" / f"{today_str}.parquet"
        assert snap_path.exists(), f"Expected snapshot at {snap_path}"
        df = pd.read_parquet(snap_path)
        assert len(df) > 0
        assert "symbol" in df.columns
        # Ingest frame returned
        assert "symbol_directory__ingest" in result
        assert result["symbol_directory__ingest"].iloc[0]["snapshot_written"] == 1

    def test_snapshot_not_written_second_call_same_day(self, tmp_path):
        """Second call same day: snapshot already exists -> skip write, snapshot_written=0."""
        import collectors.symbol_directory as m

        today_str = date.today().isoformat()
        snap_dir = tmp_path / "symbol_directory" / "snapshots"
        snap_dir.mkdir(parents=True)

        # Pre-populate with a synthetic snapshot
        existing = pd.DataFrame([{
            "date": today_str, "symbol": "AAPL", "security_name": "Apple Inc.",
            "exchange": "NASDAQ", "etf": False, "test_issue": False, "source": "nasdaqlisted",
        }])
        snap_path = snap_dir / f"{today_str}.parquet"
        existing.to_parquet(snap_path, index=False)

        with patch("collectors.symbol_directory.config") as mock_cfg, \
             patch("collectors.symbol_directory._fetch_text") as mock_text, \
             patch("collectors.symbol_directory._fetch_sec_json") as mock_sec:

            mock_cfg.data_dir.return_value = tmp_path
            # If fetch were called, it should fail the test
            mock_text.side_effect = AssertionError("should not fetch on second call")
            mock_sec.return_value = _SEC_TICKERS_JSON

            adapter = m.SymbolDirectoryAdapter()
            result = adapter.fetch()

        assert result["symbol_directory__ingest"].iloc[0]["snapshot_written"] == 0


# ---------------------------------------------------------------------------
# C. CIK-map once-per-ISO-week idempotency
# ---------------------------------------------------------------------------

class TestCikMapIdempotency:
    def test_cik_map_written_when_none_this_week(self, tmp_path):
        """No CIK map this week -> write one."""
        import collectors.symbol_directory as m

        today_str = date.today().isoformat()

        with patch("collectors.symbol_directory.config") as mock_cfg, \
             patch("collectors.symbol_directory._fetch_text") as mock_text, \
             patch("collectors.symbol_directory._fetch_sec_json") as mock_sec:

            mock_cfg.data_dir.return_value = tmp_path
            mock_text.side_effect = [_NASDAQLISTED_TEXT, _OTHERLISTED_TEXT]
            mock_sec.return_value = _SEC_TICKERS_JSON

            adapter = m.SymbolDirectoryAdapter()
            result = adapter.fetch()

        cik_path = tmp_path / "symbol_directory" / "cik_map" / f"{today_str}.parquet"
        assert cik_path.exists()
        df = pd.read_parquet(cik_path)
        assert len(df) > 0
        assert "ticker" in df.columns and "cik" in df.columns and "title" in df.columns
        assert result["symbol_directory__ingest"].iloc[0]["cik_written"] == 1

    def test_cik_map_skipped_when_already_written_this_week(self, tmp_path):
        """CIK map already written this ISO week -> skip."""
        import collectors.symbol_directory as m

        today = date.today()
        # Put a file dated within the same ISO week
        cik_dir = tmp_path / "symbol_directory" / "cik_map"
        cik_dir.mkdir(parents=True)
        existing_cik = pd.DataFrame([{"ticker": "AAPL", "cik": 320193, "title": "Apple Inc."}])
        cik_file = cik_dir / f"{today.isoformat()}.parquet"
        existing_cik.to_parquet(cik_file, index=False)

        with patch("collectors.symbol_directory.config") as mock_cfg, \
             patch("collectors.symbol_directory._fetch_text") as mock_text, \
             patch("collectors.symbol_directory._fetch_sec_json") as mock_sec:

            mock_cfg.data_dir.return_value = tmp_path
            mock_text.side_effect = [_NASDAQLISTED_TEXT, _OTHERLISTED_TEXT]
            # SEC fetch should NOT be called for cik_map this week
            mock_sec.return_value = _SEC_TICKERS_JSON

            adapter = m.SymbolDirectoryAdapter()
            result = adapter.fetch()

        assert result["symbol_directory__ingest"].iloc[0]["cik_written"] == 0

    def test_cik_map_written_when_last_week_exists(self, tmp_path):
        """File exists but from LAST week -> write a new one this week."""
        import collectors.symbol_directory as m

        today = date.today()
        last_week = today - timedelta(weeks=1)

        # Ensure different ISO week
        while last_week.isocalendar()[:2] == today.isocalendar()[:2]:
            last_week -= timedelta(days=1)

        cik_dir = tmp_path / "symbol_directory" / "cik_map"
        cik_dir.mkdir(parents=True)
        existing_cik = pd.DataFrame([{"ticker": "AAPL", "cik": 320193, "title": "Apple Inc."}])
        cik_file = cik_dir / f"{last_week.isoformat()}.parquet"
        existing_cik.to_parquet(cik_file, index=False)

        with patch("collectors.symbol_directory.config") as mock_cfg, \
             patch("collectors.symbol_directory._fetch_text") as mock_text, \
             patch("collectors.symbol_directory._fetch_sec_json") as mock_sec:

            mock_cfg.data_dir.return_value = tmp_path
            mock_text.side_effect = [_NASDAQLISTED_TEXT, _OTHERLISTED_TEXT]
            mock_sec.return_value = _SEC_TICKERS_JSON

            adapter = m.SymbolDirectoryAdapter()
            result = adapter.fetch()

        assert result["symbol_directory__ingest"].iloc[0]["cik_written"] == 1


# ---------------------------------------------------------------------------
# D. Manifest contents
# ---------------------------------------------------------------------------

class TestManifest:
    def test_manifest_written(self, tmp_path):
        """Adapter writes manifest.json with expected keys."""
        import collectors.symbol_directory as m

        with patch("collectors.symbol_directory.config") as mock_cfg, \
             patch("collectors.symbol_directory._fetch_text") as mock_text, \
             patch("collectors.symbol_directory._fetch_sec_json") as mock_sec:

            mock_cfg.data_dir.return_value = tmp_path
            mock_text.side_effect = [_NASDAQLISTED_TEXT, _OTHERLISTED_TEXT]
            mock_sec.return_value = _SEC_TICKERS_JSON

            adapter = m.SymbolDirectoryAdapter()
            adapter.fetch()

        manifest_path = tmp_path / "symbol_directory" / "manifest.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text())

        assert manifest["_display_only"] is True
        assert manifest["_version"] == "v1"
        assert "last_snapshot_date" in manifest
        assert "n_symbols" in manifest
        assert "n_etf" in manifest
        assert "n_common_estimate" in manifest
        assert "last_cik_map_date" in manifest
        assert "n_cik_rows" in manifest

    def test_manifest_n_etf_count(self, tmp_path):
        """n_etf counts only ETF-flagged rows (SPY from otherlisted)."""
        import collectors.symbol_directory as m

        with patch("collectors.symbol_directory.config") as mock_cfg, \
             patch("collectors.symbol_directory._fetch_text") as mock_text, \
             patch("collectors.symbol_directory._fetch_sec_json") as mock_sec:

            mock_cfg.data_dir.return_value = tmp_path
            mock_text.side_effect = [_NASDAQLISTED_TEXT, _OTHERLISTED_TEXT]
            mock_sec.return_value = _SEC_TICKERS_JSON

            adapter = m.SymbolDirectoryAdapter()
            adapter.fetch()

        manifest = json.loads(
            (tmp_path / "symbol_directory" / "manifest.json").read_text()
        )
        # SPY is the only ETF in our fixture (AAPL$ is dropped, AAPL/MSFT/TESTX are N,
        # BRK/A is N in otherlisted)
        assert manifest["n_etf"] == 1

    def test_manifest_n_common_estimate(self, tmp_path):
        """n_common_estimate = n_symbols - n_etf."""
        import collectors.symbol_directory as m

        with patch("collectors.symbol_directory.config") as mock_cfg, \
             patch("collectors.symbol_directory._fetch_text") as mock_text, \
             patch("collectors.symbol_directory._fetch_sec_json") as mock_sec:

            mock_cfg.data_dir.return_value = tmp_path
            mock_text.side_effect = [_NASDAQLISTED_TEXT, _OTHERLISTED_TEXT]
            mock_sec.return_value = _SEC_TICKERS_JSON

            adapter = m.SymbolDirectoryAdapter()
            adapter.fetch()

        manifest = json.loads(
            (tmp_path / "symbol_directory" / "manifest.json").read_text()
        )
        assert manifest["n_common_estimate"] == manifest["n_symbols"] - manifest["n_etf"]

    def test_manifest_last_snapshot_date_is_today(self, tmp_path):
        """manifest.last_snapshot_date is today's ISO date."""
        import collectors.symbol_directory as m
        from datetime import date as _date

        with patch("collectors.symbol_directory.config") as mock_cfg, \
             patch("collectors.symbol_directory._fetch_text") as mock_text, \
             patch("collectors.symbol_directory._fetch_sec_json") as mock_sec:

            mock_cfg.data_dir.return_value = tmp_path
            mock_text.side_effect = [_NASDAQLISTED_TEXT, _OTHERLISTED_TEXT]
            mock_sec.return_value = _SEC_TICKERS_JSON

            adapter = m.SymbolDirectoryAdapter()
            adapter.fetch()

        manifest = json.loads(
            (tmp_path / "symbol_directory" / "manifest.json").read_text()
        )
        assert manifest["last_snapshot_date"] == _date.today().isoformat()


# ---------------------------------------------------------------------------
# E. Adapter metadata
# ---------------------------------------------------------------------------

class TestAdapterMeta:
    def test_name_and_group(self):
        import collectors.symbol_directory as m
        adapter = m.SymbolDirectoryAdapter()
        assert adapter.name == "symbol_directory"
        assert adapter.group == "sec"

    def test_importable_from_collect(self):
        """collect.py can import the adapter without error."""
        import scripts.collect as sc
        registry = sc.all_adapters()
        assert "symbol_directory" in registry, (
            "symbol_directory not registered in scripts/collect.py all_adapters()"
        )
