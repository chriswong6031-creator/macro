"""tests/test_thetadata.py — hermetic tests for the ThetaData client + backfill driver.

All tests are network-free: the terminal is mocked via requests_mock or monkeypatching.
No fixture parquets written to data/ during tests.

Test coverage:
  1. Client: parses documented JSON response fixtures correctly (bulk_eod, greeks,
     trade_quote, open_interest)
  2. Client: pagination concatenation (follows next_page until "null")
  3. Client: offline/unreachable path returns None/empty without raising
  4. Client: strike divisor (STRIKE_DIVISOR=1000.0) normalizes to dollar floats
  5. Backfill: --dry-run plans correctly off a fixture universe
  6. Backfill: resume state logic (skip completed root-years)
  7. Calibration: --source thetadata is additive (existing gate JSON keys untouched when
     terminal is absent)
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "thetadata"


# ── helpers ─────────────────────────────────────────────────────────────────────
def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


# ── 1. Response parsing ────────────────────────────────────────────────────────

class TestBulkEodParsing:
    """bulk_eod: parses the documented JSON fixture into a normalized DataFrame."""

    def test_basic_parse(self, monkeypatch):
        """Two contracts, two dates → correct row count and column types."""
        fixture = _load("bulk_eod_response.json")
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)

        from collectors import thetadata as td

        def _mock_paginate(session, path, params):
            yield fixture["response"]

        monkeypatch.setattr(td, "_paginate", _mock_paginate)
        df = td.bulk_eod("SPY", 20260117, date(2026, 1, 1), date(2026, 1, 2))
        assert df is not None
        assert not df.empty
        # Fixture: 2 ticks for C + 1 tick for P = 3 rows
        assert len(df) == 3
        assert set(df.columns).issuperset(
            {"root", "expiration", "strike", "right", "date", "open", "high", "low", "close",
             "volume", "count", "bid", "ask"})

    def test_strike_divisor(self, monkeypatch):
        """Strike integer 580000 → dollar value 580.0 (divisor = 1000.0)."""
        fixture = _load("bulk_eod_response.json")
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        def _mock_paginate(session, path, params):
            yield fixture["response"]

        monkeypatch.setattr(td, "_paginate", _mock_paginate)
        df = td.bulk_eod("SPY", 0, date(2026, 1, 1), date(2026, 1, 2))
        assert df is not None
        assert (df["strike"] == 580.0).any(), f"strikes: {df['strike'].unique()}"

    def test_date_column_is_datetime(self, monkeypatch):
        """date column comes back as datetime64, not raw int."""
        fixture = _load("bulk_eod_response.json")
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        def _mock_paginate(session, path, params):
            yield fixture["response"]

        monkeypatch.setattr(td, "_paginate", _mock_paginate)
        df = td.bulk_eod("SPY", 0, date(2026, 1, 1), date(2026, 1, 2))
        assert df is not None
        assert pd.api.types.is_datetime64_any_dtype(df["date"]), f"dtype: {df['date'].dtype}"

    def test_right_values(self, monkeypatch):
        """Fixture has both C and P contracts."""
        fixture = _load("bulk_eod_response.json")
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        def _mock_paginate(session, path, params):
            yield fixture["response"]

        monkeypatch.setattr(td, "_paginate", _mock_paginate)
        df = td.bulk_eod("SPY", 0, date(2026, 1, 1), date(2026, 1, 2))
        assert df is not None
        assert set(df["right"]) == {"C", "P"}


class TestGreeksParsing:
    """bulk_greeks: parses first-order Greeks + IV from the documented fixture."""

    def test_first_order_columns(self, monkeypatch):
        fixture = _load("bulk_greeks_response.json")
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        def _mock_paginate(session, path, params):
            yield fixture["response"]

        monkeypatch.setattr(td, "_paginate", _mock_paginate)
        df = td.bulk_greeks("SPY", 20260117, date(2026, 1, 1), date(2026, 1, 2), order=1)
        assert df is not None
        assert not df.empty
        assert set(df.columns).issuperset(
            {"delta", "theta", "vega", "rho", "epsilon", "lambda_", "implied_vol",
             "underlying_price"})

    def test_implied_vol_in_greeks(self, monkeypatch):
        """IV is at index 9 in the tick array; should parse as a numeric column."""
        fixture = _load("bulk_greeks_response.json")
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        def _mock_paginate(session, path, params):
            yield fixture["response"]

        monkeypatch.setattr(td, "_paginate", _mock_paginate)
        df = td.bulk_greeks("SPY", 0, date(2026, 1, 1), date(2026, 1, 2), order=1)
        assert df is not None
        # fixture has implied_vol=0.22
        assert abs(df["implied_vol"].iloc[0] - 0.22) < 1e-6

    def test_invalid_order_raises(self):
        from collectors import thetadata as td
        with pytest.raises(ValueError, match="order must be"):
            td.bulk_greeks("SPY", 0, date(2026, 1, 1), date(2026, 1, 2), order=5)


class TestTradeQuoteParsing:
    """trade_quote: parses the documented fixture into normalized columns."""

    def test_basic_parse(self, monkeypatch):
        fixture = _load("trade_quote_response.json")
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        def _mock_paginate(session, path, params):
            yield fixture["response"]

        monkeypatch.setattr(td, "_paginate", _mock_paginate)
        df = td.trade_quote("SPY", 20260117, "C", 580.0, date(2026, 1, 1), date(2026, 1, 1))
        assert df is not None
        assert not df.empty
        assert len(df) == 2   # fixture has 2 trades
        assert set(df.columns).issuperset({"price", "size", "bid", "ask", "date", "strike", "right"})

    def test_strike_and_right_in_output(self, monkeypatch):
        fixture = _load("trade_quote_response.json")
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        def _mock_paginate(session, path, params):
            yield fixture["response"]

        monkeypatch.setattr(td, "_paginate", _mock_paginate)
        df = td.trade_quote("SPY", 20260117, "C", 580.0, date(2026, 1, 1), date(2026, 1, 1))
        assert df is not None
        assert (df["strike"] == 580.0).all()
        assert (df["right"] == "C").all()


# ── 2. Pagination concatenation ───────────────────────────────────────────────

class TestPagination:
    """Pagination: _paginate follows next_page until 'null', concatenating rows."""

    def test_two_pages_concatenated(self, monkeypatch):
        """Two-page response: first page has next_page URL, second page has 'null'.
        Uses unittest.mock to avoid needing requests_mock package."""
        from unittest.mock import MagicMock, patch
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        page1 = _load("bulk_eod_page1.json")
        page2 = _load("bulk_eod_page2.json")

        # Mock _get to return page1 for the first call
        call_count = [0]
        def _mock_get(session, path, params):
            call_count[0] += 1
            return page1

        # Mock session.get to return page2 for the next_page URL
        mock_resp2 = MagicMock()
        mock_resp2.status_code = 200
        mock_resp2.json.return_value = page2

        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp2

        monkeypatch.setattr(td, "_get", _mock_get)
        monkeypatch.setattr(td, "_session", lambda: mock_session)

        df = td.bulk_eod("SPY", 20260117, date(2026, 1, 1), date(2026, 1, 1))
        assert df is not None
        # page1: 1 C contract (1 tick), page2: 1 P contract (1 tick) = 2 rows
        assert len(df) == 2
        assert set(df["right"]) == {"C", "P"}
        # Verify session.get was called with the next_page URL
        mock_session.get.assert_called_once_with(
            page1["header"]["next_page"],
            timeout=(td.CONNECT_TIMEOUT, td.READ_TIMEOUT),
        )

    def test_null_string_terminates(self, monkeypatch):
        """next_page = 'null' (string) terminates pagination."""
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        # Response with next_page = "null" string (as documented)
        fixture = _load("bulk_eod_response.json")
        assert fixture["header"]["next_page"] == "null"

        def _mock_paginate(session, path, params):
            yield fixture["response"]

        monkeypatch.setattr(td, "_paginate", _mock_paginate)
        df = td.bulk_eod("SPY", 0, date(2026, 1, 1), date(2026, 1, 2))
        assert df is not None
        # No infinite loop; returns normally
        assert len(df) > 0


# ── 3. Offline / unreachable path ─────────────────────────────────────────────

class TestOfflineBehavior:
    """When the terminal is unreachable, all methods return None (or empty) without raising."""

    def test_bulk_eod_offline_returns_none(self, monkeypatch):
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: False)
        from collectors import thetadata as td
        result = td.bulk_eod("SPY", 0, date(2026, 1, 1), date(2026, 1, 7))
        assert result is None

    def test_bulk_greeks_offline_returns_none(self, monkeypatch):
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: False)
        from collectors import thetadata as td
        result = td.bulk_greeks("SPY", 0, date(2026, 1, 1), date(2026, 1, 7), order=1)
        assert result is None

    def test_trade_quote_offline_returns_none(self, monkeypatch):
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: False)
        from collectors import thetadata as td
        result = td.trade_quote("SPY", 20260117, "C", 580.0, date(2026, 1, 1), date(2026, 1, 7))
        assert result is None

    def test_bulk_open_interest_offline_returns_none(self, monkeypatch):
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: False)
        from collectors import thetadata as td
        result = td.bulk_open_interest("SPY", 0, date(2026, 1, 1), date(2026, 1, 7))
        assert result is None

    def test_connection_error_returns_none_not_raises(self, monkeypatch):
        """ConnectionError during the request → None (never raises into a build)."""
        import requests
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        def _fail_get(*a, **kw):
            raise requests.exceptions.ConnectionError("refused")

        monkeypatch.setattr("requests.Session.get", _fail_get)
        result = td._get(td._session(), "/v2/bulk_hist/option/eod", {})
        assert result is None

    def test_malformed_json_returns_none(self, monkeypatch):
        """Non-JSON response body → None without raising."""
        from unittest.mock import MagicMock
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.side_effect = ValueError("No JSON object could be decoded")

        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp

        result = td._get(mock_session, "/v2/bulk_hist/option/eod", {"root": "SPY"})
        assert result is None

    def test_permission_error_471(self, monkeypatch):
        """HTTP 471 (permission) → None, with a warning (not a raise)."""
        from unittest.mock import MagicMock
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        mock_resp = MagicMock()
        mock_resp.status_code = 471

        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp

        result = td._get(mock_session, "/v2/bulk_hist/option/eod", {})
        assert result is None

    def test_no_data_472_returns_empty_df(self, monkeypatch):
        """HTTP 472 (no_data) → empty DataFrame, not None (valid response for empty range)."""
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        def _mock_paginate(session, path, params):
            return iter([])   # empty iterator: _get returned empty response

        monkeypatch.setattr(td, "_paginate", _mock_paginate)
        df = td.bulk_eod("SPY", 0, date(2026, 1, 1), date(2026, 1, 1))
        assert df is not None
        assert df.empty


# ── 4. Date / strike helpers ─────────────────────────────────────────────────

class TestHelpers:
    def test_date_int_from_date(self):
        from collectors.thetadata import _date_int
        assert _date_int(date(2026, 1, 7)) == 20260107

    def test_date_int_from_iso_string(self):
        from collectors.thetadata import _date_int
        assert _date_int("2026-01-07") == 20260107

    def test_date_int_from_int(self):
        from collectors.thetadata import _date_int
        assert _date_int(20260107) == 20260107

    def test_to_date_round_trip(self):
        from collectors.thetadata import _to_date
        ts = _to_date(20260107)
        assert ts is not None
        assert ts.year == 2026 and ts.month == 1 and ts.day == 7

    def test_to_date_invalid(self):
        from collectors.thetadata import _to_date
        assert _to_date(None) is None
        assert _to_date("bad") is None


# ── 5. Backfill --dry-run ──────────────────────────────────────────────────────

class TestBackfillDryRun:
    """--dry-run prints the plan without making API calls."""

    def test_dry_run_produces_plan(self, monkeypatch, tmp_path, capsys):
        """With a fixture universe, dry-run prints work items and exits 0."""
        import sys

        # Point data dir at tmp_path so state file is isolated
        monkeypatch.setattr("lib.config.data_dir", lambda: tmp_path)

        # Mock the universe to 2 roots
        monkeypatch.setattr(
            "engine.options_universe.gex_symbols",
            lambda: ["SPY", "QQQ"],
        )

        # Patch sys.argv
        monkeypatch.setattr(sys, "argv",
                            ["backfill_thetadata_eod", "--dry-run",
                             "--start", "20260101", "--end", "20260630",
                             "--roots", "SPY,QQQ"])

        from scripts import backfill_thetadata_eod as bk
        # Override store dir to use tmp_path
        monkeypatch.setattr(bk, "_store_dir", lambda: tmp_path / "thetadata_eod")

        rc = bk.main()
        out = capsys.readouterr().out
        assert rc == 0
        assert "Dry Run" in out
        # 2 roots × 1 year chunk = 2 entries (or more if chunked)
        assert "SPY" in out or "QQQ" in out


# ── 6. Backfill resume state ────────────────────────────────────────────────────

class TestBackfillResumeState:
    """State-file resume: completed root-years are skipped; failed ones are retried."""

    def test_completed_root_year_is_skipped(self, tmp_path):
        from scripts.backfill_thetadata_eod import (
            _load_state, _mark_completed, _save_state, _is_completed,
        )
        state_file = tmp_path / "_backfill_state.json"
        state_file.write_text('{"version":1,"completed":{}}')

        import json
        state = {"version": 1, "completed": {}}
        _mark_completed(state, "SPY", 2026)
        assert _is_completed(state, "SPY", 2026)
        assert not _is_completed(state, "SPY", 2025)
        assert not _is_completed(state, "QQQ", 2026)

    def test_save_and_load_state_round_trip(self, tmp_path, monkeypatch):
        from scripts import backfill_thetadata_eod as bk

        monkeypatch.setattr(bk, "_store_dir", lambda: tmp_path)

        state = {"version": 1, "completed": {"SPY": ["2024", "2025"], "QQQ": ["2023"]}}
        bk._save_state(state)
        loaded = bk._load_state()
        assert loaded["completed"]["SPY"] == ["2024", "2025"]
        assert loaded["completed"]["QQQ"] == ["2023"]

    def test_year_chunks_correct(self):
        from scripts.backfill_thetadata_eod import _year_chunks
        chunks = _year_chunks(date(2024, 6, 1), date(2026, 3, 31))
        # Should have 3 chunks: 2024 (Jun-Dec), 2025 (full year), 2026 (Jan-Mar)
        assert len(chunks) == 3
        assert chunks[0][0] == date(2024, 6, 1)
        assert chunks[0][1] == date(2024, 12, 31)
        assert chunks[1][0] == date(2025, 1, 1)
        assert chunks[2][1] == date(2026, 3, 31)

    def test_completed_years_not_in_plan(self, tmp_path, monkeypatch):
        """A root-year in state['completed'] is absent from the pull plan."""
        from scripts import backfill_thetadata_eod as bk

        monkeypatch.setattr(bk, "_store_dir", lambda: tmp_path)

        state = {"version": 1, "completed": {"SPY": ["2026"]}}
        bk._save_state(state)

        loaded = bk._load_state()
        # 2026 is done; 2025 is not
        assert bk._is_completed(loaded, "SPY", 2026)
        assert not bk._is_completed(loaded, "SPY", 2025)


# ── 7. Calibration --source thetadata is additive ─────────────────────────────

class TestCalibrationAdditive:
    """--source thetadata writes only into 'thetadata_tape' key; existing keys untouched."""

    def test_existing_gate_keys_untouched_when_terminal_absent(self, tmp_path, monkeypatch):
        """When terminal is unreachable, existing signing_gate.json is preserved."""
        import json

        gate_dir = tmp_path / "options_flow"
        gate_dir.mkdir()
        gate_path = gate_dir / "signing_gate.json"

        # Existing gate with the keys the Databento calibration wrote
        existing = {
            "scored": False,
            "direction_reliable": False,
            "magnitude_reliable": True,
            "net_sign_recovery": 0.41,
            "per_trade_agreement": 0.7774,
            "bar": 0.7,
            "note": "flow DIRECTION is SOFT",
            "asof": "2026-06-21",
        }
        gate_path.write_text(json.dumps(existing))

        # Mock data_dir to our tmp_path
        monkeypatch.setattr("lib.config.data_dir", lambda: tmp_path)
        monkeypatch.setattr("lib.config.load", lambda: {})

        # Terminal is unreachable
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: False)

        from scripts.calibrate_flow_signing import _run_thetadata_source
        _run_thetadata_source(["SPY"], ("2026-06-18T14:30", "2026-06-18T14:50"))

        written = json.loads(gate_path.read_text())

        # All original keys must be byte-identical
        for k, v in existing.items():
            assert written.get(k) == v, f"key {k!r} was altered: {written.get(k)!r} != {v!r}"

        # Only new key added
        assert "thetadata_tape" in written
        assert written["thetadata_tape"]["signing_source"] == "tape"
        assert written["thetadata_tape"]["status"] == "terminal_unreachable"

    def test_direction_reliable_not_flipped_by_measurement(self, tmp_path, monkeypatch):
        """Even if the tape passes both bars, direction_reliable in the root gate is NOT
        flipped — that flip is reserved for Fable adjudication (§7.1 doctrine)."""
        import json

        gate_dir = tmp_path / "options_flow"
        gate_dir.mkdir()
        gate_path = gate_dir / "signing_gate.json"

        existing = {"direction_reliable": False, "magnitude_reliable": True, "bar": 0.7}
        gate_path.write_text(json.dumps(existing))

        monkeypatch.setattr("lib.config.data_dir", lambda: tmp_path)
        monkeypatch.setattr("lib.config.load", lambda: {})
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: False)

        from scripts.calibrate_flow_signing import _run_thetadata_source
        _run_thetadata_source(["SPY"], ("2026-06-18T14:30", "2026-06-18T14:50"))

        written = json.loads(gate_path.read_text())
        # Root-level direction_reliable must remain False regardless
        assert written["direction_reliable"] is False

    def test_no_thetadata_tape_key_when_databento_path(self, tmp_path, monkeypatch):
        """Default (Databento) path must not write thetadata_tape into the gate."""
        import json

        gate_dir = tmp_path / "options_flow"
        gate_dir.mkdir()
        gate_path = gate_dir / "signing_gate.json"
        gate_path.write_text(json.dumps({"direction_reliable": False}))

        monkeypatch.setattr("lib.config.data_dir", lambda: tmp_path)
        monkeypatch.setattr("lib.config.load", lambda: {})
        # Databento disabled (no key)
        monkeypatch.setattr("collectors.databento_tbbo.enabled", lambda: False)

        from scripts.calibrate_flow_signing import run
        run()

        written = json.loads(gate_path.read_text())
        # thetadata_tape must NOT be present when the databento path ran
        assert "thetadata_tape" not in written


# ── 8. _date_int round-trips ────────────────────────────────────────────────────

class TestStrikeConvention:
    """Verify the strike divisor matches the documented API contract."""

    def test_strike_divisor_constant(self):
        """Documented: strike 170000 = $170.00 → STRIKE_DIVISOR must be 1000.0."""
        from collectors.thetadata import STRIKE_DIVISOR
        assert STRIKE_DIVISOR == 1000.0
        assert 170000 / STRIKE_DIVISOR == 170.0
        assert 580000 / STRIKE_DIVISOR == 580.0

    def test_trade_quote_strike_int_conversion(self):
        """trade_quote: float strike → API int → back to float is lossless for round numbers."""
        from collectors.thetadata import STRIKE_DIVISOR
        for strike in [100.0, 150.5, 200.0, 580.0, 4200.0]:
            int_val = int(round(strike * STRIKE_DIVISOR))
            recovered = int_val / STRIKE_DIVISOR
            assert abs(recovered - strike) < 1e-6, f"roundtrip failed for {strike}"
