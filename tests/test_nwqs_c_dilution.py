"""tests/test_nwqs_c_dilution.py — Unit tests for nwqs-c item C deliverables.

Coverage:
  1. collectors/edgar_dilution.py — parse_dilution_idx() fixture test
  2. engine/falsifier_tripwires.py — TripwireResult scope roundtrip +
     results_summary() exclusion + results_by_ticker() helper
  3. engine/neuralweb/bottom_sensors.py — absent-parquet no-crash test
     for dilution columns in assemble()
"""
from __future__ import annotations

import datetime
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# ─────────────────────────────────────────────────────────────────────────────
# 1. Collector parse unit test — parse_dilution_idx()
# ─────────────────────────────────────────────────────────────────────────────

from collectors.edgar_dilution import parse_dilution_idx, _ALL_FORMS, _SHELF_FORMS, _PROSPECTUS_FORMS  # noqa: E402

# A realistic form.YYYYMMDD.idx snippet with S-3, 424B3, and a non-target form.
_IDX_FIXTURE = """\
Form Type|Company Name|CIK|Date Filed|Filename
----------------------------------------------------------------------
S-3                 ACME CORP                      0001234567  20260101  edgar/data/1234567/0001234567-26-000001.txt
S-3ASR              BIGCO INC                      0009876543  20260102  edgar/data/9876543/0009876543-26-000002.txt
424B3               MEDTECH LTD                    0001111111  20260103  edgar/data/1111111/0001111111-26-000003.txt
424B5               GROWTH CO                      0002222222  20260104  edgar/data/2222222/0002222222-26-000004.txt
S-3/A               REFINANCEME INC                0003333333  20260105  edgar/data/3333333/0003333333-26-000005.txt
10-K                BORING CORP                    0004444444  20260106  edgar/data/4444444/0004444444-26-000006.txt
8-K                 ANOTHER CO                     0005555555  20260107  edgar/data/5555555/0005555555-26-000007.txt
"""

# The actual daily-index separator line is all dashes with NO | characters;
# re-generate as the parser expects (set(ln.strip()) == {"-"}).
_IDX_REAL_FORMAT = """\
Form Type                            Company Name                              CIK         Date Filed  Filename
-------------------------------------------------------------------------------------------------------------------------------------------
S-3                                  ACME CORP                                 1234567     20260101    edgar/data/1234567/0001234567-26-000001.txt
S-3ASR                               BIGCO INC                                 9876543     20260102    edgar/data/9876543/0009876543-26-000002.txt
424B3                                MEDTECH LTD                               1111111     20260103    edgar/data/1111111/0001111111-26-000003.txt
424B5                                GROWTH CO                                 2222222     20260104    edgar/data/2222222/0002222222-26-000004.txt
S-3/A                                REFINANCEME INC                           3333333     20260105    edgar/data/3333333/0003333333-26-000005.txt
10-K                                 BORING CORP                               4444444     20260106    edgar/data/4444444/0004444444-26-000006.txt
8-K                                  ANOTHER CO                                5555555     20260107    edgar/data/5555555/0005555555-26-000007.txt
"""


class TestParseDilutionIdx:

    def test_extracts_target_forms_only(self):
        """Only S-3/S-3ASR/S-3/A/424B* rows are returned; 10-K/8-K are excluded."""
        rows = parse_dilution_idx(_IDX_REAL_FORMAT)
        forms = {r["form"] for r in rows}
        assert "10-K" not in forms
        assert "8-K" not in forms
        # We should have captured S-3, S-3ASR, 424B3, 424B5, S-3/A = 5 rows
        assert len(rows) == 5

    def test_form_set_correct(self):
        rows = parse_dilution_idx(_IDX_REAL_FORMAT)
        forms = {r["form"] for r in rows}
        expected = {"S-3", "S-3ASR", "424B3", "424B5", "S-3/A"}
        assert forms == expected

    def test_accession_number_extracted(self):
        """Accession is the stem of the file path (no path prefix)."""
        rows = parse_dilution_idx(_IDX_REAL_FORMAT)
        accessions = {r["accession"] for r in rows}
        assert "0001234567-26-000001" in accessions
        assert "0001111111-26-000003" in accessions

    def test_cik_extracted(self):
        rows = parse_dilution_idx(_IDX_REAL_FORMAT)
        by_acc = {r["accession"]: r for r in rows}
        assert by_acc["0001234567-26-000001"]["cik"] == "1234567"

    def test_filing_date_iso(self):
        """filing_date is formatted as YYYY-MM-DD."""
        rows = parse_dilution_idx(_IDX_REAL_FORMAT)
        by_acc = {r["accession"]: r for r in rows}
        assert by_acc["0001234567-26-000001"]["filing_date"] == "2026-01-01"
        assert by_acc["0001111111-26-000003"]["filing_date"] == "2026-01-03"

    def test_empty_text_returns_empty(self):
        assert parse_dilution_idx("") == []

    def test_no_target_forms_returns_empty(self):
        text = "10-K  SOME CO  1234  20260101  edgar/data/1234/0001234-26-000001.txt\n"
        assert parse_dilution_idx(text) == []

    def test_all_forms_in_constant(self):
        """Constant sets are correct supersets."""
        assert _SHELF_FORMS == {"S-3", "S-3ASR", "S-3/A"}
        assert _PROSPECTUS_FORMS == {"424B1", "424B2", "424B3", "424B4", "424B5"}
        assert _ALL_FORMS == _SHELF_FORMS | _PROSPECTUS_FORMS


# ─────────────────────────────────────────────────────────────────────────────
# 2. Falsifier tripwire scope roundtrip + results_summary exclusion
# ─────────────────────────────────────────────────────────────────────────────

from engine.falsifier_tripwires import (  # noqa: E402
    TripwireResult,
    results_summary,
    results_by_ticker,
)


def _make_cycle_result(**kwargs) -> TripwireResult:
    defaults = dict(
        id="tw-cycle-1",
        cycle="expansion",
        version=1,
        state="ARMED",
        fired_on=None,
        latched=False,
        current_leg=False,
        claim="test cycle claim",
        direction="refutes",
        coverage="full",
        expires=None,
        scope="cycle",
        tickers=[],
    )
    defaults.update(kwargs)
    return TripwireResult(**defaults)


def _make_ticker_result(**kwargs) -> TripwireResult:
    defaults = dict(
        id="tw-ticker-1",
        cycle="per-stock",
        version=1,
        state="ARMED",
        fired_on=None,
        latched=False,
        current_leg=False,
        claim="test ticker claim",
        direction="refutes",
        coverage="none",
        expires=None,
        scope="ticker",
        tickers=["AAPL", "MSFT"],
    )
    defaults.update(kwargs)
    return TripwireResult(**defaults)


class TestTripwireResultScope:

    def test_scope_defaults_to_cycle(self):
        """A TripwireResult built without scope= gets 'cycle' (the default)."""
        r = TripwireResult(
            id="x", cycle="c", version=1, state="ARMED",
            fired_on=None, latched=False, current_leg=None,
            claim="", direction="refutes", coverage="none", expires=None,
        )
        assert r.scope == "cycle"
        assert r.tickers == []

    def test_scope_ticker_roundtrip(self):
        r = _make_ticker_result()
        assert r.scope == "ticker"
        assert "AAPL" in r.tickers
        assert "MSFT" in r.tickers

    def test_results_summary_excludes_ticker_scope(self):
        """results_summary() must NOT include scope='ticker' entries in cycle dict."""
        cycle_r = _make_cycle_result(cycle="expansion")
        ticker_r = _make_ticker_result(cycle="per-stock")
        summary = results_summary([cycle_r, ticker_r])
        # cycle entry is present
        assert "expansion" in summary
        # ticker scope is excluded entirely
        assert "per-stock" not in summary

    def test_results_summary_pure_cycle_unchanged(self):
        """Existing cycle entries (scope='cycle') are still grouped as before."""
        r1 = _make_cycle_result(id="tw-1", cycle="expansion")
        r2 = _make_cycle_result(id="tw-2", cycle="contraction")
        summary = results_summary([r1, r2])
        assert "expansion" in summary
        assert "contraction" in summary
        assert summary["expansion"][0]["id"] == "tw-1"

    def test_results_by_ticker_groups_correctly(self):
        """results_by_ticker() groups scope='ticker' entries by each ticker."""
        ticker_r = _make_ticker_result(tickers=["AAPL", "MSFT"])
        by_ticker = results_by_ticker([ticker_r])
        assert "AAPL" in by_ticker
        assert "MSFT" in by_ticker
        # Same result record appears under both
        assert by_ticker["AAPL"][0]["id"] == "tw-ticker-1"
        assert by_ticker["MSFT"][0]["id"] == "tw-ticker-1"

    def test_results_by_ticker_excludes_cycle_scope(self):
        """results_by_ticker() must not return scope='cycle' entries."""
        cycle_r = _make_cycle_result()
        ticker_r = _make_ticker_result()
        by_ticker = results_by_ticker([cycle_r, ticker_r])
        # Only ticker-scoped entries appear
        for entries in by_ticker.values():
            for e in entries:
                assert e["id"] != "tw-cycle-1"

    def test_results_by_ticker_empty_when_no_ticker_scope(self):
        """No scope='ticker' entries → empty dict."""
        r = _make_cycle_result()
        assert results_by_ticker([r]) == {}

    def test_results_summary_all_cycle_still_works(self):
        """When ALL results are scope='cycle', output matches legacy behaviour."""
        results = [
            _make_cycle_result(id=f"tw-{i}", cycle="expansion") for i in range(3)
        ]
        summary = results_summary(results)
        assert len(summary["expansion"]) == 3


# ─────────────────────────────────────────────────────────────────────────────
# 3. bottom_sensors.py — absent parquet no-crash test
# ─────────────────────────────────────────────────────────────────────────────

from engine.neuralweb.bottom_sensors import (  # noqa: E402
    _load_dilution_index,
    _build_dilution_index,
    _dilution_fields,
)


class TestBottomSensorsDilutionAbsentParquet:

    def test_load_dilution_index_absent(self, tmp_path):
        """_load_dilution_index returns empty DataFrame when file does not exist."""
        df = _load_dilution_index(tmp_path)
        assert isinstance(df, pd.DataFrame)
        assert df.empty

    def test_build_dilution_index_empty(self, tmp_path):
        """_build_dilution_index on empty DataFrame returns empty dict."""
        df = pd.DataFrame()
        idx = _build_dilution_index(df)
        assert idx == {}

    def test_dilution_fields_empty_index(self):
        """_dilution_fields returns (None, None, None) when index is empty."""
        today = datetime.date(2026, 7, 5)
        assert _dilution_fields("AAPL", {}, today) == (None, None, None)

    def test_dilution_fields_ticker_not_in_index(self):
        """_dilution_fields returns (None, None, None) when ticker not in index."""
        today = datetime.date(2026, 7, 5)
        idx = {"MSFT": {"latest_shelf": None, "latest_takedown": None, "dates": []}}
        assert _dilution_fields("AAPL", idx, today) == (None, None, None)

    def test_dilution_fields_with_real_data(self):
        """_dilution_fields computes correct days and event count."""
        today = datetime.date(2026, 7, 5)
        shelf_date = pd.Timestamp("2026-06-15")      # 20 days ago
        takedown_date = pd.Timestamp("2026-07-01")   # 4 days ago
        # One event 200 days ago (outside 365d window? No, 200 < 365)
        old_date = pd.Timestamp(today - datetime.timedelta(days=200))
        idx = {
            "AAPL": {
                "latest_shelf": shelf_date,
                "latest_takedown": takedown_date,
                "dates": [shelf_date, takedown_date, old_date],
            }
        }
        d_shelf, d_takedown, d_events = _dilution_fields("AAPL", idx, today)
        assert d_shelf == 20
        assert d_takedown == 4
        # All 3 events are within 365 days (200 + 4 + 20 all < 365)
        assert d_events == 3

    def test_dilution_fields_events_outside_365d_excluded(self):
        """Events older than 365 days are excluded from dilution_events_365d."""
        today = datetime.date(2026, 7, 5)
        old_date = pd.Timestamp(today - datetime.timedelta(days=400))
        recent_date = pd.Timestamp(today - datetime.timedelta(days=10))
        idx = {
            "TSLA": {
                "latest_shelf": recent_date,
                "latest_takedown": None,
                "dates": [old_date, recent_date],
            }
        }
        _, _, d_events = _dilution_fields("TSLA", idx, today)
        # Only the recent one qualifies
        assert d_events == 1

    def test_build_dilution_index_separates_shelf_and_takedown(self):
        """_build_dilution_index correctly separates latest_shelf vs latest_takedown."""
        df = pd.DataFrame({
            "ticker": ["AAPL", "AAPL", "AAPL"],
            "form": ["S-3", "424B3", "S-3ASR"],
            "filing_date": pd.to_datetime(["2026-01-01", "2026-02-01", "2026-03-01"]),
        })
        idx = _build_dilution_index(df)
        assert "AAPL" in idx
        entry = idx["AAPL"]
        # latest shelf = 2026-03-01 (S-3ASR)
        assert pd.Timestamp(entry["latest_shelf"]).date() == datetime.date(2026, 3, 1)
        # latest takedown = 2026-02-01 (424B3)
        assert pd.Timestamp(entry["latest_takedown"]).date() == datetime.date(2026, 2, 1)
        # All 3 dates recorded
        assert len(entry["dates"]) == 3

    def test_build_dilution_index_drops_unmapped_tickers(self):
        """Rows with ticker=None/NaN are excluded from the index."""
        df = pd.DataFrame({
            "ticker": [None, "MSFT", float("nan")],
            "form": ["S-3", "424B3", "S-3ASR"],
            "filing_date": pd.to_datetime(["2026-01-01", "2026-02-01", "2026-03-01"]),
        })
        idx = _build_dilution_index(df)
        assert None not in idx
        assert "MSFT" in idx
        # NaN ticker should also be excluded (dropna)
        keys = list(idx.keys())
        for k in keys:
            assert k == "MSFT"

    def test_assemble_degrades_gracefully_absent_dilution(self, tmp_path, monkeypatch):
        """assemble() must not raise when dilution_events.parquet is absent.
        dilution columns are None for all tickers.
        """
        # Patch all heavy loaders so assemble can run with minimal fixtures.
        minimal_sg_verdicts = {
            "AAPL": {"tier_cascade": "T1", "ticks": 0, "bars_to_cross": None},
        }
        monkeypatch.setattr(
            "engine.neuralweb.bottom_sensors._load_signal_gate",
            lambda root: (minimal_sg_verdicts, "2026-07-05"),
        )
        monkeypatch.setattr(
            "engine.neuralweb.bottom_sensors._load_us_standouts",
            lambda root: {},
        )
        monkeypatch.setattr(
            "engine.neuralweb.bottom_sensors._load_earnings",
            lambda root: pd.DataFrame(),
        )
        monkeypatch.setattr(
            "engine.neuralweb.bottom_sensors._load_statements",
            lambda: {},
        )
        monkeypatch.setattr(
            "engine.neuralweb.bottom_sensors.build_sector_map",
            lambda root: {},
        )
        monkeypatch.setattr(
            "engine.neuralweb.bottom_sensors._load_oracle_panel",
            lambda root, filename: None,
        )
        monkeypatch.setattr(
            "engine.neuralweb.bottom_sensors._load_close",
            lambda root, ticker: None,
        )
        # Patch _data_dilution to point at a non-existent path (tmp_path, empty)
        monkeypatch.setattr(
            "engine.neuralweb.bottom_sensors._data_dilution",
            lambda root: tmp_path / "nonexistent.parquet",
        )

        from engine.neuralweb.bottom_sensors import assemble
        df = assemble(root=tmp_path, today=datetime.date(2026, 7, 5))

        # Must return a DataFrame (not raise)
        assert isinstance(df, pd.DataFrame)
        assert not df.empty, "Expected at least one row for AAPL"

        # Dilution columns must be present but None (absent parquet)
        assert "days_since_shelf" in df.columns
        assert "days_since_takedown" in df.columns
        assert "dilution_events_365d" in df.columns
        for col in ("days_since_shelf", "days_since_takedown", "dilution_events_365d"):
            assert df.loc["AAPL", col] is None or pd.isna(df.loc["AAPL", col]), (
                f"{col} should be None/NaN when parquet absent"
            )
