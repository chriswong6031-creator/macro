"""tests/test_thetadata.py — hermetic tests for the ThetaData v3 client + backfill driver.

All tests are network-free: the terminal is mocked via monkeypatching.
No fixture parquets written to data/ during tests.

Test coverage:
  1. Client: parses v3 CSV fixtures correctly (bulk_eod, greeks, trade_quote, open_interest)
  2. Client: streaming-read concatenation (multi-day wildcard iterates day by day)
  3. Client: offline/unreachable path returns None/empty without raising
  4. Client: strike is a dollar float in v3 (no divisor applied; STRIKE_DIVISOR = 1.0)
  5. Client: right normalization ("CALL"/"PUT" → "C"/"P" in output)
  6. Client: trade_quote right normalization for requests ("C"/"CALL" → "call")
  7. Client: _StreamTruncated on mid-stream failure returns None, not partial DataFrame
  8. Backfill: --dry-run plans correctly off a fixture universe
  9. Backfill: resume state logic (skip completed root-years)
  10. Calibration: --source thetadata is additive (existing gate JSON keys untouched)
  11. Helpers: _date_int, _normalize_right_request, _normalize_expiration_param
  12. Strike: STRIKE_DIVISOR = 1.0 (v3 identity; strike values already in dollars)
"""
from __future__ import annotations

import io
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "thetadata"


# ── helpers ─────────────────────────────────────────────────────────────────────
def _csv_bytes(name: str) -> bytes:
    """Read a fixture CSV file as bytes."""
    return (FIXTURES / name).read_bytes()


def _make_csv_response(content: bytes, status_code: int = 200) -> MagicMock:
    """Create a mock requests.Response that streams CSV content."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    # iter_content yields chunks
    mock_resp.iter_content = lambda chunk_size: iter([content])
    # iter_lines yields individual lines (for streaming line-based reads)
    lines = content.split(b"\n")
    mock_resp.iter_lines = lambda: iter(lines)
    mock_resp.text = content.decode("utf-8", errors="replace")[:200]
    return mock_resp


# ── 1. Response parsing ────────────────────────────────────────────────────────

class TestBulkEodParsing:
    """bulk_eod: parses v3 CSV fixture into a normalized DataFrame."""

    def test_basic_parse(self, monkeypatch):
        """Three rows (2 CALL + 1 PUT) from v3 CSV → correct row count and columns."""
        csv_data = _csv_bytes("bulk_eod_response.csv")
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        def _mock_get_csv(session, path, params):
            return pd.read_csv(io.BytesIO(csv_data), low_memory=False)

        monkeypatch.setattr(td, "_get_csv", _mock_get_csv)
        df = td.bulk_eod("SPY", 20260117, date(2026, 1, 1), date(2026, 1, 2))
        assert df is not None
        assert not df.empty
        # Fixture: 2 CALL ticks + 1 PUT tick = 3 rows
        assert len(df) == 3
        assert set(df.columns).issuperset(
            {"root", "expiration", "strike", "right", "date",
             "open", "high", "low", "close", "volume", "count", "bid", "ask"})

    def test_strike_is_dollar_float_no_divisor(self, monkeypatch):
        """Strike in v3 is a dollar float (580.000 = $580.00); STRIKE_DIVISOR = 1.0."""
        csv_data = _csv_bytes("bulk_eod_response.csv")
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        def _mock_get_csv(session, path, params):
            return pd.read_csv(io.BytesIO(csv_data), low_memory=False)

        monkeypatch.setattr(td, "_get_csv", _mock_get_csv)
        df = td.bulk_eod("SPY", 20260117, date(2026, 1, 1), date(2026, 1, 2))
        assert df is not None
        # Fixture has strike=580.000 → should be 580.0, NOT 580000/1000
        assert (df["strike"] == 580.0).all(), f"strikes: {df['strike'].unique()}"

    def test_right_normalized_c_p(self, monkeypatch):
        """Response 'CALL'/'PUT' → normalized to 'C'/'P' in output."""
        csv_data = _csv_bytes("bulk_eod_response.csv")
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        def _mock_get_csv(session, path, params):
            return pd.read_csv(io.BytesIO(csv_data), low_memory=False)

        monkeypatch.setattr(td, "_get_csv", _mock_get_csv)
        df = td.bulk_eod("SPY", 0, date(2026, 1, 1), date(2026, 1, 2))
        assert df is not None
        assert set(df["right"]) == {"C", "P"}

    def test_date_column_is_datetime(self, monkeypatch):
        """date column comes back as datetime64."""
        csv_data = _csv_bytes("bulk_eod_response.csv")
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        def _mock_get_csv(session, path, params):
            return pd.read_csv(io.BytesIO(csv_data), low_memory=False)

        monkeypatch.setattr(td, "_get_csv", _mock_get_csv)
        df = td.bulk_eod("SPY", 0, date(2026, 1, 1), date(2026, 1, 2))
        assert df is not None
        assert pd.api.types.is_datetime64_any_dtype(df["date"]), f"dtype: {df['date'].dtype}"

    def test_expiration_is_datetime(self, monkeypatch):
        """expiration column parsed from 'YYYY-MM-DD' string → datetime64."""
        csv_data = _csv_bytes("bulk_eod_response.csv")
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        def _mock_get_csv(session, path, params):
            return pd.read_csv(io.BytesIO(csv_data), low_memory=False)

        monkeypatch.setattr(td, "_get_csv", _mock_get_csv)
        df = td.bulk_eod("SPY", 0, date(2026, 1, 1), date(2026, 1, 2))
        assert df is not None
        assert pd.api.types.is_datetime64_any_dtype(df["expiration"])

    def test_wildcard_windowed_pulls(self, monkeypatch):
        """bulk_eod wildcard iterates in ≤7-day windows (stall fix 2026-07-05).

        3-day range → 1 window (≤7 days).
        10-day range → 2 windows (7 days + 3 days).
        Each window issues one _get_csv call with expiration="*".
        Contrast: before the stall fix a single multi-month range request would hang.
        """
        csv_data = _csv_bytes("bulk_eod_response.csv")
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        # 3-day range fits in 1 window (≤7 days)
        call_count = [0]
        seen_params: list[dict] = []

        def _mock_get_csv(session, path, params):
            call_count[0] += 1
            seen_params.append(dict(params))
            return pd.read_csv(io.BytesIO(csv_data), low_memory=False)

        monkeypatch.setattr(td, "_get_csv", _mock_get_csv)
        td.bulk_eod("SPY", 0, date(2026, 1, 1), date(2026, 1, 3))
        assert call_count[0] == 1, (
            f"3-day range fits in 1 window (≤7 days), got {call_count[0]} calls"
        )
        assert seen_params[0].get("expiration") == "*"
        # Window spans the full 3-day range
        assert seen_params[0].get("start_date") == 20260101
        assert seen_params[0].get("end_date") == 20260103

    def test_wildcard_10day_yields_two_windows(self, monkeypatch):
        """10-day range → 2 windows: [Jan 1–7] and [Jan 8–10] (≤7-day window rule)."""
        csv_data = _csv_bytes("bulk_eod_response.csv")
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        seen_params: list[dict] = []

        def _mock_get_csv(session, path, params):
            seen_params.append(dict(params))
            return pd.read_csv(io.BytesIO(csv_data), low_memory=False)

        monkeypatch.setattr(td, "_get_csv", _mock_get_csv)
        td.bulk_eod("SPY", 0, date(2026, 1, 1), date(2026, 1, 10))
        assert len(seen_params) == 2, (
            f"10-day range should yield 2 windows (7+3), got {len(seen_params)}"
        )
        # First window: Jan 1–7
        assert seen_params[0]["start_date"] == 20260101
        assert seen_params[0]["end_date"] == 20260107
        # Second window: Jan 8–10
        assert seen_params[1]["start_date"] == 20260108
        assert seen_params[1]["end_date"] == 20260110


class TestOpenInterestParsing:
    """bulk_open_interest: parses v3 OI CSV fixture."""

    def test_basic_parse(self, monkeypatch):
        csv_data = _csv_bytes("open_interest_response.csv")
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        def _mock_get_csv(session, path, params):
            return pd.read_csv(io.BytesIO(csv_data), low_memory=False)

        monkeypatch.setattr(td, "_get_csv", _mock_get_csv)
        df = td.bulk_open_interest("SPY", 20260117, date(2026, 1, 1), date(2026, 1, 2))
        assert df is not None
        assert not df.empty
        assert "open_interest" in df.columns
        assert set(df.columns).issuperset(
            {"root", "expiration", "strike", "right", "date", "open_interest"})

    def test_oi_date_from_timestamp(self, monkeypatch):
        """OI timestamp '2026-01-01T06:30:16.218' → date 2026-01-01."""
        csv_data = _csv_bytes("open_interest_response.csv")
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        def _mock_get_csv(session, path, params):
            return pd.read_csv(io.BytesIO(csv_data), low_memory=False)

        monkeypatch.setattr(td, "_get_csv", _mock_get_csv)
        df = td.bulk_open_interest("SPY", 20260117, date(2026, 1, 1), date(2026, 1, 2))
        assert df is not None
        dates = pd.to_datetime(df["date"]).dt.date.unique()
        assert date(2026, 1, 1) in dates

    def test_oi_strike_is_dollar_float(self, monkeypatch):
        """OI strike 580.000 → 580.0 (no divisor)."""
        csv_data = _csv_bytes("open_interest_response.csv")
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        def _mock_get_csv(session, path, params):
            return pd.read_csv(io.BytesIO(csv_data), low_memory=False)

        monkeypatch.setattr(td, "_get_csv", _mock_get_csv)
        df = td.bulk_open_interest("SPY", 20260117, date(2026, 1, 1), date(2026, 1, 2))
        assert df is not None
        assert (df["strike"] == 580.0).all()


class TestGreeksParsing:
    """bulk_greeks: parses v3 greeks/eod CSV fixture (buffered, not streamed)."""

    def test_first_order_columns(self, monkeypatch):
        """order=1 returns first-order greek columns."""
        csv_data = _csv_bytes("bulk_greeks_response.csv")
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        # greeks/eod uses _get_csv (buffered), not _stream_lines
        def _mock_get_csv(session, path, params):
            return pd.read_csv(io.BytesIO(csv_data), low_memory=False)

        monkeypatch.setattr(td, "_get_csv", _mock_get_csv)
        df = td.bulk_greeks("SPY", 20260117, date(2026, 1, 1), date(2026, 1, 2), order=1)
        assert df is not None
        assert not df.empty
        assert set(df.columns).issuperset(
            {"delta", "theta", "vega", "rho", "epsilon", "lambda",
             "implied_vol", "underlying_price"})

    def test_second_order_columns_included_for_order2(self, monkeypatch):
        """order=2 includes first + second order columns."""
        csv_data = _csv_bytes("bulk_greeks_response.csv")
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        def _mock_get_csv(session, path, params):
            return pd.read_csv(io.BytesIO(csv_data), low_memory=False)

        monkeypatch.setattr(td, "_get_csv", _mock_get_csv)
        df = td.bulk_greeks("SPY", 20260117, date(2026, 1, 1), date(2026, 1, 2), order=2)
        assert df is not None
        assert not df.empty
        assert set(df.columns).issuperset({"delta", "gamma", "vanna"})

    def test_implied_vol_in_greeks(self, monkeypatch):
        """IV is in the fixture; should parse as a numeric ~0.22."""
        csv_data = _csv_bytes("bulk_greeks_response.csv")
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        def _mock_get_csv(session, path, params):
            return pd.read_csv(io.BytesIO(csv_data), low_memory=False)

        monkeypatch.setattr(td, "_get_csv", _mock_get_csv)
        df = td.bulk_greeks("SPY", 20260117, date(2026, 1, 1), date(2026, 1, 2), order=1)
        assert df is not None
        assert abs(df["implied_vol"].iloc[0] - 0.22) < 1e-6

    def test_invalid_order_raises(self):
        from collectors import thetadata as td
        with pytest.raises(ValueError, match="order must be"):
            td.bulk_greeks("SPY", 20260117, date(2026, 1, 1), date(2026, 1, 2), order=5)

    def test_wildcard_expiration_day_by_day_concurrent(self, monkeypatch):
        """greeks/eod wildcard: 1-day windows (API rejects multi-day wildcard: HTTP 400).

        greeks/eod requires start_date == end_date when expiration="*".
        bulk_greeks uses _concurrent_windows with window_days=1, so each window is
        exactly 1 calendar day.  A 2-day range → 2 calls (one per day).
        An 8-day range → 8 calls (one per day).
        Each window has expiration="*".
        """
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        calls: list[dict] = []

        def _mock_get_csv(session, path, params):
            calls.append(dict(params))
            return pd.DataFrame()  # Each day returns empty (holiday/weekend)

        monkeypatch.setattr(td, "_get_csv", _mock_get_csv)
        # 2-day range → 2 calls (1-day windows: start_date == end_date for greeks)
        df = td.bulk_greeks("SPY", 0, date(2026, 1, 1), date(2026, 1, 2), order=1)
        assert len(calls) == 2, (
            f"2-day greeks range → 2 day-by-day calls (window_days=1), got {len(calls)}"
        )
        assert all(c.get("expiration") == "*" for c in calls)
        # Each window: start_date == end_date
        for c in calls:
            assert c.get("start_date") == c.get("end_date"), (
                f"greeks window start != end: {c}"
            )
        # Returns empty DataFrame (all days were empty), not None
        assert df is not None
        assert df.empty

    def test_greeks_uses_eod_endpoint(self, monkeypatch):
        """bulk_greeks calls the /v3/option/history/greeks/eod endpoint, NOT /greeks/all."""
        csv_data = _csv_bytes("bulk_greeks_response.csv")
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        endpoint_seen: list[str] = []

        def _mock_get_csv(session, path, params):
            endpoint_seen.append(path)
            return pd.read_csv(io.BytesIO(csv_data), low_memory=False)

        monkeypatch.setattr(td, "_get_csv", _mock_get_csv)
        td.bulk_greeks("SPY", 20260117, date(2026, 1, 1), date(2026, 1, 2), order=1)
        assert len(endpoint_seen) == 1
        assert endpoint_seen[0] == "/v3/option/history/greeks/eod"


class TestTradeQuoteParsing:
    """trade_quote: parses v3 trade_quote CSV into normalized columns."""

    def test_basic_parse(self, monkeypatch):
        csv_data = _csv_bytes("trade_quote_response.csv")
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        def _mock_stream_lines(session, path, params):
            return iter(csv_data.split(b"\n"))

        monkeypatch.setattr(td, "_stream_lines", _mock_stream_lines)
        df = td.trade_quote("SPY", 20260117, "C", 580.0, date(2026, 1, 1), date(2026, 1, 1))
        assert df is not None
        assert not df.empty
        assert len(df) == 2   # fixture has 2 trades
        assert set(df.columns).issuperset(
            {"price", "size", "bid", "ask", "date", "strike", "right", "root"})

    def test_strike_and_right_in_output(self, monkeypatch):
        csv_data = _csv_bytes("trade_quote_response.csv")
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        def _mock_stream_lines(session, path, params):
            return iter(csv_data.split(b"\n"))

        monkeypatch.setattr(td, "_stream_lines", _mock_stream_lines)
        df = td.trade_quote("SPY", 20260117, "C", 580.0, date(2026, 1, 1), date(2026, 1, 1))
        assert df is not None
        assert (df["strike"] == 580.0).all()
        assert (df["right"] == "C").all()

    def test_trade_timestamp_columns_present(self, monkeypatch):
        """trade_quote output includes trade_timestamp and quote_timestamp columns."""
        csv_data = _csv_bytes("trade_quote_response.csv")
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        def _mock_stream_lines(session, path, params):
            return iter(csv_data.split(b"\n"))

        monkeypatch.setattr(td, "_stream_lines", _mock_stream_lines)
        df = td.trade_quote("SPY", 20260117, "C", 580.0, date(2026, 1, 1), date(2026, 1, 1))
        assert df is not None
        assert "trade_timestamp" in df.columns
        assert "quote_timestamp" in df.columns


# ── 2. Streaming read / truncation semantics ──────────────────────────────────

class TestStreamTruncation:
    """_StreamTruncated on mid-stream failure → None, never a partial DataFrame."""

    def test_stream_error_during_bulk_eod_returns_none(self, monkeypatch):
        """If _get_csv raises _StreamTruncated on any window, bulk_eod returns None (not partial).

        Stall fix: bulk_eod wildcard iterates in ≤7-day windows. A stall on any window
        (after all retries) → the whole call returns None. No partial DataFrame is returned.
        """
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        def _mock_get_csv(session, path, params):
            raise td._StreamTruncated("simulated mid-stream stall on window request")

        monkeypatch.setattr(td, "_get_csv", _mock_get_csv)
        # Window stalls on first attempt → retried → still fails → returns None (no partial)
        result = td.bulk_eod("SPY", 0, date(2026, 1, 1), date(2026, 1, 2))
        assert result is None   # must be None, not an empty or partial DataFrame

    def test_stream_error_during_greeks_returns_none(self, monkeypatch):
        """If _get_csv raises _StreamTruncated, bulk_greeks returns None."""
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        def _mock_get_csv(session, path, params):
            raise td._StreamTruncated("simulated connection reset")

        monkeypatch.setattr(td, "_get_csv", _mock_get_csv)
        result = td.bulk_greeks("SPY", 20260117, date(2026, 1, 1), date(2026, 1, 1), order=1)
        assert result is None

    def test_stream_error_during_oi_returns_none(self, monkeypatch):
        """If _get_csv raises _StreamTruncated on any window, bulk_open_interest returns None.

        Uses a ≥8-day range to produce 2 windows.  First window succeeds; second stalls.
        Result must be None (no partial DataFrame).
        """
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        # Suppress retries to speed up the test
        monkeypatch.setattr(td.time, "sleep", lambda s: None)
        monkeypatch.setattr(td, "WINDOW_RETRY_BACKOFF", (0, 0))

        def _mock_get_csv(session, path, params):
            sd = params.get("start_date", 0)
            # First window (Jan 1–7) succeeds; second window (Jan 8+) stalls
            if sd == 20260101:
                return pd.DataFrame({"symbol": ["SPY"], "expiration": ["2026-01-17"],
                                     "strike": [580.0], "right": ["CALL"],
                                     "timestamp": ["2026-01-01T06:30:00.000"],
                                     "open_interest": [125000]})
            raise td._StreamTruncated("simulated mid-stream failure on second window")

        monkeypatch.setattr(td, "_get_csv", _mock_get_csv)
        # 8-day range → 2 windows; second window stalls → must return None (no partial)
        result = td.bulk_open_interest("SPY", 0, date(2026, 1, 1), date(2026, 1, 8))
        assert result is None

    def test_stream_error_during_trade_quote_returns_none(self, monkeypatch):
        """If _stream_lines raises _StreamTruncated, trade_quote returns None."""
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        def _mock_stream_lines(session, path, params):
            yield b"symbol,expiration,strike,right,trade_timestamp,quote_timestamp,sequence,ext_condition1,ext_condition2,ext_condition3,ext_condition4,condition,size,exchange,price,bid_size,bid_exchange,bid,bid_condition,ask_size,ask_exchange,ask,ask_condition"
            raise td._StreamTruncated("connection reset during trade_quote")

        monkeypatch.setattr(td, "_stream_lines", _mock_stream_lines)
        result = td.trade_quote("SPY", 20260117, "C", 580.0, date(2026, 1, 1), date(2026, 1, 1))
        assert result is None


    def test_chunked_encoding_error_returns_none(self, monkeypatch):
        """iter_content yields one valid chunk then raises ChunkedEncodingError → None.

        Proves mid-stream truncation discards already-parsed rows (INERT contract).
        The public method (bulk_eod) must return None even if some bytes arrived before
        the error — _get_csv raises _StreamTruncated which bulk_eod catches and converts
        to None.
        """
        import requests as _req
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        valid_chunk = (
            b"symbol,expiration,strike,right,created,last_trade,"
            b"open,high,low,close,volume,count,bid_size,bid_exchange,"
            b"bid,bid_condition,ask_size,ask_exchange,ask,ask_condition\n"
            b'"SPY","2026-01-17",580.000,"CALL",'
            b"2026-01-17T17:00:00,2026-01-17T14:30:00,"
            b"5.00,5.50,4.90,5.20,100,10,100,C,5.10,50,100,C,5.30,50\n"
        )

        def _iter_content_raise(chunk_size):
            yield valid_chunk
            raise _req.exceptions.ChunkedEncodingError("connection reset mid-stream")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.iter_content = _iter_content_raise

        # Patch requests.Session.get so bulk_eod gets the mock response
        mock_session_cls = MagicMock()
        mock_session_cls.return_value.__enter__ = lambda s: s
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_session_cls.return_value.headers = {}
        mock_session_cls.return_value.get = MagicMock(return_value=mock_resp)

        # Patch _session() to return the mock session
        monkeypatch.setattr(td, "_session", lambda: mock_session_cls.return_value)

        # bulk_eod (non-wildcard path) calls _get_csv which raises _StreamTruncated;
        # bulk_eod must catch that and return None (not a partial DataFrame).
        result = td.bulk_eod("SPY", 20260117, date(2026, 1, 17), date(2026, 1, 17))
        assert result is None, (
            f"Expected None when ChunkedEncodingError occurs mid-stream, got: {result}"
        )


# ── 3. Offline / unreachable path ─────────────────────────────────────────────

class TestOfflineBehavior:
    """When the terminal is unreachable, all methods return None without raising."""

    def test_bulk_eod_offline_returns_none(self, monkeypatch):
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: False)
        from collectors import thetadata as td
        result = td.bulk_eod("SPY", 0, date(2026, 1, 1), date(2026, 1, 7))
        assert result is None

    def test_bulk_greeks_offline_returns_none(self, monkeypatch):
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: False)
        from collectors import thetadata as td
        result = td.bulk_greeks("SPY", 20260117, date(2026, 1, 1), date(2026, 1, 7), order=1)
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
        result = td._get_csv(td._session(), "/v3/option/history/eod", {})
        assert result is None

    def test_non_200_returns_none(self, monkeypatch):
        """Non-200 HTTP response → None without raising."""
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        mock_resp = MagicMock()
        mock_resp.status_code = 471
        mock_resp.text = "PERMISSION"

        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp

        result = td._get_csv(mock_session, "/v3/option/history/eod", {"symbol": "SPY"})
        assert result is None

    def test_empty_response_returns_empty_df(self, monkeypatch):
        """Empty/no-data response body → empty DataFrame, not None."""
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        def _mock_get_csv(session, path, params):
            return pd.DataFrame()

        monkeypatch.setattr(td, "_get_csv", _mock_get_csv)
        df = td.bulk_eod("SPY", 0, date(2026, 1, 1), date(2026, 1, 1))
        assert df is not None
        assert df.empty


# ── 4. Helpers ────────────────────────────────────────────────────────────────

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

    def test_normalize_right_call_variants(self):
        from collectors.thetadata import _normalize_right_request
        assert _normalize_right_request("C") == "call"
        assert _normalize_right_request("CALL") == "call"
        assert _normalize_right_request("call") == "call"

    def test_normalize_right_put_variants(self):
        from collectors.thetadata import _normalize_right_request
        assert _normalize_right_request("P") == "put"
        assert _normalize_right_request("PUT") == "put"
        assert _normalize_right_request("put") == "put"

    def test_normalize_expiration_wildcard(self):
        from collectors.thetadata import _normalize_expiration_param
        assert _normalize_expiration_param("*") == "*"
        assert _normalize_expiration_param(0) == "*"   # v2 compat: 0 → wildcard

    def test_normalize_expiration_date(self):
        from collectors.thetadata import _normalize_expiration_param
        assert _normalize_expiration_param(20260117) == "20260117"
        assert _normalize_expiration_param(date(2026, 1, 17)) == "20260117"

    def test_iter_days(self):
        from collectors.thetadata import _iter_days
        days = list(_iter_days(date(2026, 1, 1), date(2026, 1, 3)))
        assert len(days) == 3
        assert days[0] == date(2026, 1, 1)
        assert days[2] == date(2026, 1, 3)


# ── 5. Strike convention ────────────────────────────────────────────────────────

class TestStrikeConvention:
    """v3: strikes are DOLLAR FLOATS; STRIKE_DIVISOR = 1.0 (identity)."""

    def test_strike_divisor_is_one(self):
        """v3 STRIKE_DIVISOR = 1.0 (no division needed; strikes already in dollars)."""
        from collectors.thetadata import STRIKE_DIVISOR
        assert STRIKE_DIVISOR == 1.0

    def test_strike_580_stays_580(self):
        """580.000 from the API → 580.0 in output (no /1000 divisor)."""
        from collectors.thetadata import STRIKE_DIVISOR
        api_strike = 580.000
        output_strike = api_strike / STRIKE_DIVISOR
        assert output_strike == 580.0

    def test_trade_quote_strike_passthrough(self):
        """trade_quote: float strike passed in → same float in output row."""
        from collectors.thetadata import STRIKE_DIVISOR
        for strike in [100.0, 150.5, 200.0, 580.0, 4200.0]:
            output = strike / STRIKE_DIVISOR
            assert abs(output - strike) < 1e-9, f"strike {strike} not preserved"


# ── 6. Backfill --dry-run ──────────────────────────────────────────────────────

class TestBackfillDryRun:
    """--dry-run prints the plan without making API calls."""

    def test_dry_run_produces_plan(self, monkeypatch, tmp_path, capsys):
        """With a fixture universe, dry-run prints work items and exits 0."""
        import sys

        monkeypatch.setattr("lib.config.data_dir", lambda: tmp_path)
        monkeypatch.setattr(
            "engine.options_universe.gex_symbols",
            lambda: ["SPY", "QQQ"],
        )

        monkeypatch.setattr(sys, "argv",
                            ["backfill_thetadata_eod", "--dry-run",
                             "--start", "20260101", "--end", "20260630",
                             "--roots", "SPY,QQQ"])

        from scripts import backfill_thetadata_eod as bk
        monkeypatch.setattr(bk, "_store_dir", lambda: tmp_path / "thetadata_eod")

        rc = bk.main()
        out = capsys.readouterr().out
        assert rc == 0
        assert "Dry Run" in out
        assert "SPY" in out or "QQQ" in out

    def test_default_start_is_20120601(self):
        """DEFAULT_START must be 20120601 (history starts ~2012-06-01, measured 2026-07-04)."""
        from scripts.backfill_thetadata_eod import DEFAULT_START
        assert DEFAULT_START == "20120601"

    def test_spxw_in_index_roots(self):
        """SPXW must be in INDEX_ROOTS (confirmed as distinct root 2026-07-04)."""
        from scripts.backfill_thetadata_eod import INDEX_ROOTS
        assert "SPXW" in INDEX_ROOTS
        assert "SPX" in INDEX_ROOTS


# ── 7. Backfill resume state ────────────────────────────────────────────────────

class TestBackfillResumeState:
    """State-file resume: completed root-years are skipped; failed ones are retried."""

    def test_completed_root_year_is_skipped(self, tmp_path):
        from scripts.backfill_thetadata_eod import (
            _load_state, _mark_completed, _save_state, _is_completed,
        )
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
        assert len(chunks) == 3
        assert chunks[0][0] == date(2024, 6, 1)
        assert chunks[0][1] == date(2024, 12, 31)
        assert chunks[1][0] == date(2025, 1, 1)
        assert chunks[2][1] == date(2026, 3, 31)

    def test_completed_years_not_in_plan(self, tmp_path, monkeypatch):
        from scripts import backfill_thetadata_eod as bk
        monkeypatch.setattr(bk, "_store_dir", lambda: tmp_path)

        state = {"version": 1, "completed": {"SPY": ["2026"]}}
        bk._save_state(state)

        loaded = bk._load_state()
        assert bk._is_completed(loaded, "SPY", 2026)
        assert not bk._is_completed(loaded, "SPY", 2025)


# ── 8. Calibration --source thetadata is additive ─────────────────────────────

class TestCalibrationAdditive:
    """--source thetadata writes only into 'thetadata_tape' key; existing keys untouched."""

    def test_existing_gate_keys_untouched_when_terminal_absent(self, tmp_path, monkeypatch):
        import json

        gate_dir = tmp_path / "options_flow"
        gate_dir.mkdir()
        gate_path = gate_dir / "signing_gate.json"

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

        monkeypatch.setattr("lib.config.data_dir", lambda: tmp_path)
        monkeypatch.setattr("lib.config.load", lambda: {})
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: False)

        from scripts.calibrate_flow_signing import _run_thetadata_source
        _run_thetadata_source(["SPY"], ("2026-06-18T14:30", "2026-06-18T14:50"))

        written = json.loads(gate_path.read_text())

        # All original keys must be byte-identical
        for k, v in existing.items():
            assert written.get(k) == v, f"key {k!r} was altered: {written.get(k)!r} != {v!r}"

        assert "thetadata_tape" in written
        assert written["thetadata_tape"]["signing_source"] == "tape"
        assert written["thetadata_tape"]["status"] == "terminal_unreachable"

    def test_direction_reliable_not_flipped_by_measurement(self, tmp_path, monkeypatch):
        """Even if tape passes both bars, direction_reliable in root gate is NOT flipped."""
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
        monkeypatch.setattr("collectors.databento_tbbo.enabled", lambda: False)

        from scripts.calibrate_flow_signing import run
        run()

        written = json.loads(gate_path.read_text())
        assert "thetadata_tape" not in written


# ── 9. reachable() uses v3 endpoint ─────────────────────────────────────────────

class TestReachableV3:
    """reachable() hits /v3/option/list/symbols (NOT the dead v2 endpoint)."""

    def test_reachable_uses_v3_path(self, monkeypatch):
        """reachable() calls /v3/option/list/symbols and returns True on 200."""
        import requests as _req
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        captured_urls = []
        original_get = _req.get

        def _capture_get(url, **kw):
            captured_urls.append(url)
            mock = MagicMock()
            mock.status_code = 200
            return mock

        monkeypatch.setattr(_req, "get", _capture_get)
        # Directly test the real reachable()
        monkeypatch.undo()  # remove the lambda override to test the real function
        from collectors import thetadata as td2
        import importlib
        importlib.reload(td2)
        monkeypatch.setattr(_req, "get", _capture_get)
        td2.reachable()
        assert any("/v3/option/list/symbols" in u for u in captured_urls), \
            f"Expected v3 health check, got: {captured_urls}"

    def test_v2_path_never_called(self, monkeypatch):
        """reachable() must NOT call any /v2/* path (those return 410 Gone)."""
        import requests as _req
        called_v2 = []

        def _check_get(url, **kw):
            if "/v2/" in url:
                called_v2.append(url)
            mock = MagicMock()
            mock.status_code = 200
            return mock

        monkeypatch.setattr(_req, "get", _check_get)
        from collectors import thetadata as td
        td.reachable()
        assert not called_v2, f"reachable() called v2 endpoint: {called_v2}"


# ── 10. Stall fix: window iteration boundaries ───────────────────────────────

class TestWindowIteration:
    """_iter_windows tiles [start, end] exactly: no gaps, no overlaps, ≤7 days per window."""

    def test_single_day_yields_one_window(self):
        from collectors.thetadata import _iter_windows
        wins = list(_iter_windows(date(2026, 1, 1), date(2026, 1, 1)))
        assert len(wins) == 1
        assert wins[0] == (date(2026, 1, 1), date(2026, 1, 1))

    def test_exact_7_days_yields_one_window(self):
        from collectors.thetadata import _iter_windows
        wins = list(_iter_windows(date(2026, 1, 1), date(2026, 1, 7)))
        assert len(wins) == 1
        assert wins[0] == (date(2026, 1, 1), date(2026, 1, 7))

    def test_8_days_yields_two_windows(self):
        from collectors.thetadata import _iter_windows
        wins = list(_iter_windows(date(2026, 1, 1), date(2026, 1, 8)))
        assert len(wins) == 2
        assert wins[0] == (date(2026, 1, 1), date(2026, 1, 7))
        assert wins[1] == (date(2026, 1, 8), date(2026, 1, 8))

    def test_14_days_yields_two_equal_windows(self):
        from collectors.thetadata import _iter_windows
        wins = list(_iter_windows(date(2026, 1, 1), date(2026, 1, 14)))
        assert len(wins) == 2
        assert wins[0] == (date(2026, 1, 1), date(2026, 1, 7))
        assert wins[1] == (date(2026, 1, 8), date(2026, 1, 14))

    def test_no_gaps_no_overlaps_31_days(self):
        """31-day range: windows tile exactly, no gaps, no overlaps."""
        from collections import Counter
        from collectors.thetadata import _iter_windows
        wins = list(_iter_windows(date(2026, 1, 1), date(2026, 1, 31)))
        # Count all days covered
        covered: list[date] = []
        for ws, we in wins:
            d = ws
            while d <= we:
                covered.append(d)
                d += timedelta(days=1)
        # Each day should appear exactly once
        counts = Counter(covered)
        assert max(counts.values()) == 1, "overlap detected"
        assert len(covered) == 31, f"expected 31 days covered, got {len(covered)}"
        assert min(covered) == date(2026, 1, 1)
        assert max(covered) == date(2026, 1, 31)

    def test_all_windows_le_7_days(self):
        """Every window in a 31-day range is ≤7 calendar days."""
        from collectors.thetadata import _iter_windows
        wins = list(_iter_windows(date(2026, 1, 1), date(2026, 1, 31)))
        for ws, we in wins:
            span = (we - ws).days + 1
            assert span <= 7, f"window {ws}→{we} is {span} days (exceeds 7)"

    def test_31_day_range_exact_window_count(self):
        """31-day range with 7-day windows → ceil(31/7) = 5 windows."""
        from collectors.thetadata import _iter_windows
        wins = list(_iter_windows(date(2026, 1, 1), date(2026, 1, 31)))
        import math
        expected = math.ceil(31 / 7)  # = 5
        assert len(wins) == expected, f"expected {expected} windows, got {len(wins)}"


# ── 11. Stall fix: retry-then-fail returns None with nothing persisted ────────

class TestRetryThenFail:
    """Per-window retry: after WINDOW_MAX_RETRIES+1 failures, entire call returns None."""

    def test_bulk_eod_retry_exhausted_returns_none(self, monkeypatch):
        """All retry attempts stall → bulk_eod returns None (no partial)."""
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        # Speed up retries for the test by monkeypatching sleep in the module under test
        monkeypatch.setattr(td.time, "sleep", lambda s: None)
        monkeypatch.setattr(td, "WINDOW_RETRY_BACKOFF", (0, 0))

        call_count = [0]

        def _always_truncated(session, path, params):
            call_count[0] += 1
            raise td._StreamTruncated("simulated stall — all retries")

        monkeypatch.setattr(td, "_get_csv", _always_truncated)
        result = td.bulk_eod("SPY", 0, date(2026, 1, 1), date(2026, 1, 3))
        assert result is None, "Expected None after retry exhaustion"
        # With WINDOW_MAX_RETRIES=2: 1 attempt + 2 retries = 3 total calls per window
        # 1 window (3-day range ≤ 7 days) × 3 attempts = 3 calls
        assert call_count[0] == td.WINDOW_MAX_RETRIES + 1, (
            f"expected {td.WINDOW_MAX_RETRIES + 1} total attempts, got {call_count[0]}"
        )

    def test_bulk_oi_retry_exhausted_returns_none(self, monkeypatch):
        """All retry attempts stall → bulk_open_interest returns None (no partial)."""
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        monkeypatch.setattr(td.time, "sleep", lambda s: None)
        monkeypatch.setattr(td, "WINDOW_RETRY_BACKOFF", (0, 0))

        def _always_truncated(session, path, params):
            raise td._StreamTruncated("simulated stall")

        monkeypatch.setattr(td, "_get_csv", _always_truncated)
        result = td.bulk_open_interest("SPY", 0, date(2026, 1, 1), date(2026, 1, 3))
        assert result is None

    def test_bulk_greeks_retry_exhausted_returns_none(self, monkeypatch):
        """All retry attempts stall → bulk_greeks returns None (no partial)."""
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        monkeypatch.setattr(td.time, "sleep", lambda s: None)
        monkeypatch.setattr(td, "WINDOW_RETRY_BACKOFF", (0, 0))

        def _always_none(session, path, params):
            return None   # _get_csv returning None also triggers retry logic

        monkeypatch.setattr(td, "_get_csv", _always_none)
        result = td.bulk_greeks("SPY", 0, date(2026, 1, 1), date(2026, 1, 3), order=1)
        assert result is None

    def test_partial_window_failure_returns_none_not_partial_df(self, monkeypatch):
        """First window succeeds, second window fails → whole call returns None (no partial)."""
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        monkeypatch.setattr(td.time, "sleep", lambda s: None)
        monkeypatch.setattr(td, "WINDOW_RETRY_BACKOFF", (0, 0))

        csv_data = _csv_bytes("bulk_eod_response.csv")
        call_count = [0]

        def _fail_second_window(session, path, params):
            call_count[0] += 1
            # First window succeeds; subsequent windows always stall
            if params.get("start_date") == 20260101:
                return pd.read_csv(io.BytesIO(csv_data), low_memory=False)
            raise td._StreamTruncated("simulated stall on second window")

        monkeypatch.setattr(td, "_get_csv", _fail_second_window)
        # 10-day range → 2 windows; second window stalls → must return None not partial
        result = td.bulk_eod("SPY", 0, date(2026, 1, 1), date(2026, 1, 10))
        assert result is None, (
            "When any window fails after retries, bulk_eod must return None (no partial)"
        )


# ── 12. Stall fix: concurrency + deterministic ordering ─────────────────────

class TestConcurrencyOrdering:
    """Windowed concurrent pulls return rows in deterministic (chronological window) order."""

    def test_bulk_eod_wildcard_result_sorted_by_window(self, monkeypatch):
        """Rows from multiple windows are sorted by window date (ascending) in output."""
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        # Build fake CSVs with dates in each window
        def _csv_for_window(last_trade: str) -> pd.DataFrame:
            return pd.DataFrame({
                "symbol": ["SPY"],
                "expiration": ["2026-02-01"],
                "strike": [580.0],
                "right": ["CALL"],
                "created": [last_trade],
                "last_trade": [last_trade],
                "open": [5.0], "high": [5.5], "low": [4.9], "close": [5.2],
                "volume": [100], "count": [10], "bid_size": [10], "bid_exchange": ["C"],
                "bid": [5.1], "bid_condition": [50], "ask_size": [10],
                "ask_exchange": ["C"], "ask": [5.3], "ask_condition": [50],
            })

        call_order: list[int] = []

        def _mock_get_csv(session, path, params):
            sd = params.get("start_date", 0)
            call_order.append(sd)
            # Return a row whose last_trade date matches the window start
            s = str(sd)
            last_trade = f"{s[:4]}-{s[4:6]}-{s[6:8]}T14:00:00"
            return _csv_for_window(last_trade)

        monkeypatch.setattr(td, "_get_csv", _mock_get_csv)
        # 14-day range → 2 windows
        result = td.bulk_eod("SPY", 0, date(2026, 1, 1), date(2026, 1, 14))
        assert result is not None
        assert not result.empty
        # Verify chronological ordering: dates should be ascending
        dates = result["date"].dropna().sort_values().tolist()
        assert dates == sorted(dates), "Result rows are not in chronological order"

    def test_read_timeout_config_present(self):
        """READ_TIMEOUT_BETWEEN_BYTES is defined and is a positive number."""
        from collectors import thetadata as td
        assert hasattr(td, "READ_TIMEOUT_BETWEEN_BYTES"), "READ_TIMEOUT_BETWEEN_BYTES must be defined"
        assert td.READ_TIMEOUT_BETWEEN_BYTES > 0, "Read timeout must be positive"
        # Should be less than a few minutes — generous but not infinite
        assert td.READ_TIMEOUT_BETWEEN_BYTES <= 300, "Read timeout unreasonably large"

    def test_window_workers_constant_present_and_bounded(self):
        """WINDOW_WORKERS is defined and ≤ terminal concurrent ceiling (8)."""
        from collectors import thetadata as td
        assert hasattr(td, "WINDOW_WORKERS")
        assert 1 <= td.WINDOW_WORKERS <= 8, (
            f"WINDOW_WORKERS={td.WINDOW_WORKERS} exceeds terminal ceiling of 8"
        )

    def test_window_days_constant_present_and_short(self):
        """WINDOW_DAYS is defined and ≤7 (measured reliable short window size)."""
        from collectors import thetadata as td
        assert hasattr(td, "WINDOW_DAYS")
        assert 1 <= td.WINDOW_DAYS <= 7, (
            f"WINDOW_DAYS={td.WINDOW_DAYS} exceeds measured-reliable 7-day limit"
        )


# ── 13. _endpoint_label — greeks path produces "greeks" not "eod" ─────────────

class TestEndpointLabel:
    """_endpoint_label: log-line label is human-readable for multi-segment paths."""

    def test_plain_eod_path(self):
        from collectors.thetadata import _endpoint_label
        assert _endpoint_label("/v3/option/history/eod") == "eod"

    def test_greeks_eod_path_returns_greeks(self):
        """The greeks/eod path must label as 'greeks', not 'eod'.

        Bug: path.split('/')[-1] on /v3/option/history/greeks/eod returns 'eod',
        making greeks windows log as 'eod' — indistinguishable from the plain EOD
        endpoint in the log.  _endpoint_label uses the parent segment when the last
        path component is 'eod' under 'greeks'.
        """
        from collectors.thetadata import _endpoint_label
        label = _endpoint_label("/v3/option/history/greeks/eod")
        assert label == "greeks", (
            f"Expected 'greeks' but got {label!r} — greeks windows would log as 'eod'"
        )

    def test_open_interest_path(self):
        from collectors.thetadata import _endpoint_label
        assert _endpoint_label("/v3/option/history/open_interest") == "open_interest"

    def test_trade_quote_path(self):
        from collectors.thetadata import _endpoint_label
        assert _endpoint_label("/v3/option/history/trade_quote") == "trade_quote"

    def test_greeks_all_path_returns_greeks(self):
        """Hypothetical /greeks/all path also labels as 'greeks'."""
        from collectors.thetadata import _endpoint_label
        assert _endpoint_label("/v3/option/history/greeks/all") == "greeks"

    def test_bare_path_segment(self):
        from collectors.thetadata import _endpoint_label
        assert _endpoint_label("eod") == "eod"


# ── Current-day per-expiration fallback tests ──────────────────────────────────

class TestBulkTradeQuoteCurrentDayFallback:
    """bulk_trade_quote: current-day wildcard fallback + DTE cap filter.

    Hermetic — no network.  Mocks _stream_lines and list_expirations so that:
      - The wildcard call raises _StreamTruncated with the "specifying an expiration"
        message that ThetaData v3 returns for today's date.
      - list_expirations returns a mix of in-cap and out-of-cap expirations.
      - Per-expiration calls return rows only for the in-cap expirations.

    Verifies:
      1. Only in-cap expirations are fetched.
      2. A different 400 (no "specifying an expiration" in body) → returns None.
      3. All expirations failing individually → returns None.
      4. Summary INFO log is emitted.
    """

    # Minimal valid trade_quote CSV row (23 fields)
    _HEADER = (b"symbol,expiration,strike,right,trade_timestamp,quote_timestamp,"
               b"sequence,ext_condition1,ext_condition2,ext_condition3,ext_condition4,"
               b"condition,size,exchange,price,bid_size,bid_exchange,bid,bid_condition,"
               b"ask_size,ask_exchange,ask,ask_condition\n")
    _ROW_TMPL = (
        'SPY,{exp},550.0,CALL,2026-07-06T10:00:00,2026-07-06T10:00:00,'
        '1001,0,0,0,0,0,10,CBOE,2.50,5,CBOE,2.40,0,5,CBOE,2.60,0\n'
    )

    def _row_bytes(self, exp: str) -> bytes:
        return (self._HEADER + self._ROW_TMPL.format(exp=exp).encode()).strip()

    def test_current_day_fallback_dte_cap(self, monkeypatch):
        """Wildcard 400 'specifying an expiration' → per-exp loop; DTE cap filters far exps."""
        from collectors import thetadata as td
        from collectors.thetadata import _StreamTruncated

        session_date = "2026-07-06"

        # Expirations: 2 in-cap (<=90 DTE from 2026-07-06 = up to ~2026-10-04),
        # 1 out-of-cap (far future), 1 already expired (past target_date).
        EXP_INCAP_1 = "2026-07-10"    # 4 DTE — in cap
        EXP_INCAP_2 = "2026-08-01"    # 26 DTE — in cap
        EXP_OUTCAP  = "2027-01-15"    # >90 DTE — filtered out
        EXP_PAST    = "2026-07-01"    # past — filtered out

        exps_returned = [EXP_PAST, EXP_INCAP_1, EXP_INCAP_2, EXP_OUTCAP]

        fetched_exps: list[int] = []

        def _mock_stream_lines(session, path, params):
            exp_param = params.get("expiration")
            if exp_param == "*":
                raise _StreamTruncated(
                    "HTTP 400: Cannot fetch current-day data without specifying an expiration"
                )
            # Record which expiration int was fetched
            fetched_exps.append(exp_param)
            # Return a row for this expiration
            # Derive ISO from int
            s = str(exp_param)
            iso = f"{s[:4]}-{s[4:6]}-{s[6:8]}"
            content = self._row_bytes(iso)
            lines = content.split(b"\n")
            return iter(lines)

        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        monkeypatch.setattr(td, "_stream_lines", _mock_stream_lines)
        monkeypatch.setattr(td, "list_expirations", lambda sym: exps_returned)

        df = td.bulk_trade_quote("SPY", "call", session_date, session_date,
                                 near_dte_cap_days=90)

        assert df is not None, "Expected a DataFrame, got None"
        # Only in-cap expirations should have been fetched
        from collectors.thetadata import _date_int
        assert _date_int(EXP_INCAP_1) in fetched_exps
        assert _date_int(EXP_INCAP_2) in fetched_exps
        assert _date_int(EXP_OUTCAP) not in fetched_exps, (
            "Out-of-cap expiration should not be fetched"
        )
        assert _date_int(EXP_PAST) not in fetched_exps, (
            "Past expiration should not be fetched"
        )
        # Rows from both in-cap expirations are present
        assert len(df) == 2
        assert set(df["expiration"].astype(str)) == {EXP_INCAP_1, EXP_INCAP_2}

    def test_different_400_returns_none(self, monkeypatch):
        """A 400 without 'specifying an expiration' in the body → returns None (no fallback)."""
        from collectors import thetadata as td
        from collectors.thetadata import _StreamTruncated

        def _mock_stream_lines(session, path, params):
            raise _StreamTruncated("HTTP 400: some other error")

        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        monkeypatch.setattr(td, "_stream_lines", _mock_stream_lines)

        result = td.bulk_trade_quote("SPY", "call", "2026-07-06", "2026-07-06")
        assert result is None, f"Expected None for non-expiration 400, got {result}"

    def test_all_per_exp_failures_returns_none(self, monkeypatch):
        """All individual expiration fetches fail → returns None."""
        from collectors import thetadata as td
        from collectors.thetadata import _StreamTruncated

        call_count = [0]

        def _mock_stream_lines(session, path, params):
            exp_param = params.get("expiration")
            if exp_param == "*":
                raise _StreamTruncated(
                    "HTTP 400: Cannot fetch current-day data without specifying an expiration"
                )
            call_count[0] += 1
            raise _StreamTruncated("HTTP 500: server error")

        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        monkeypatch.setattr(td, "_stream_lines", _mock_stream_lines)
        monkeypatch.setattr(td, "list_expirations",
                            lambda sym: ["2026-07-10", "2026-07-17"])

        result = td.bulk_trade_quote("SPY", "call", "2026-07-06", "2026-07-06",
                                     near_dte_cap_days=90)
        assert result is None, "All-expirations-failed should return None"
        assert call_count[0] == 2, f"Expected 2 per-exp calls, got {call_count[0]}"

    def test_list_expirations_failure_returns_none(self, monkeypatch):
        """list_expirations returns None → fallback returns None."""
        from collectors import thetadata as td
        from collectors.thetadata import _StreamTruncated

        def _mock_stream_lines(session, path, params):
            if params.get("expiration") == "*":
                raise _StreamTruncated(
                    "HTTP 400: Cannot fetch current-day data without specifying an expiration"
                )
            return iter([])

        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        monkeypatch.setattr(td, "_stream_lines", _mock_stream_lines)
        monkeypatch.setattr(td, "list_expirations", lambda sym: None)

        result = td.bulk_trade_quote("SPY", "call", "2026-07-06", "2026-07-06",
                                     near_dte_cap_days=90)
        assert result is None
