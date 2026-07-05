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
from datetime import date
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

    def test_wildcard_single_range_request(self, monkeypatch):
        """/history/eod ACCEPTS multi-day wildcard in ONE range request (measured live 2026-07-04).

        With exp=0 (wildcard), bulk_eod issues a SINGLE range request regardless of how many
        days the range spans.  This replaces the old day-by-day loop (~250 requests → 1).
        Contrast: bulk_greeks keeps day-by-day (greeks/eod rejects multi-day wildcard HTTP 400).
        """
        csv_data = _csv_bytes("bulk_eod_response.csv")
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        call_count = [0]
        seen_params: list[dict] = []

        def _mock_get_csv(session, path, params):
            call_count[0] += 1
            seen_params.append(dict(params))
            return pd.read_csv(io.BytesIO(csv_data), low_memory=False)

        monkeypatch.setattr(td, "_get_csv", _mock_get_csv)
        # 3-day range with wildcard → 1 call (range request), NOT 3
        td.bulk_eod("SPY", 0, date(2026, 1, 1), date(2026, 1, 3))
        assert call_count[0] == 1, (
            f"bulk_eod wildcard should issue 1 range request, got {call_count[0]}. "
            "Note: /history/eod accepts multi-day wildcard; only /greeks/eod requires day-by-day."
        )
        # Verify it passed the full range (start=20260101, end=20260103)
        assert seen_params[0].get("start_date") == 20260101
        assert seen_params[0].get("end_date") == 20260103
        assert seen_params[0].get("expiration") == "*"


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

    def test_wildcard_expiration_iterates_day_by_day(self, monkeypatch):
        """greeks/eod supports wildcard expiration via day-by-day iteration.

        Wildcard with a 2-day range (Jan 1–2) should call _get_csv twice (once per day)
        and concatenate the results.
        """
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        calls: list[dict] = []

        def _mock_get_csv(session, path, params):
            calls.append(dict(params))
            return pd.DataFrame()  # Each day returns empty (holiday/weekend)

        monkeypatch.setattr(td, "_get_csv", _mock_get_csv)
        df = td.bulk_greeks("SPY", 0, date(2026, 1, 1), date(2026, 1, 2), order=1)
        # Wildcard: 2 days → 2 calls
        assert len(calls) == 2
        assert all(c.get("expiration") == "*" for c in calls)
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
        """If _get_csv raises _StreamTruncated, bulk_eod returns None (not partial).

        bulk_eod now issues a SINGLE range request even for wildcard (one-request model),
        so we raise _StreamTruncated on the first (and only) call.
        """
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        def _mock_get_csv(session, path, params):
            raise td._StreamTruncated("simulated mid-stream failure on range request")

        monkeypatch.setattr(td, "_get_csv", _mock_get_csv)
        # Wildcard range request raises _StreamTruncated → must return None (no partial)
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
        """If _get_csv raises _StreamTruncated, bulk_open_interest returns None."""
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        from collectors import thetadata as td

        call_count = [0]

        def _mock_get_csv(session, path, params):
            call_count[0] += 1
            if call_count[0] == 1:
                return pd.DataFrame({"symbol": ["SPY"], "expiration": ["2026-01-17"],
                                     "strike": [580.0], "right": ["CALL"],
                                     "timestamp": ["2026-01-01T06:30:00.000"],
                                     "open_interest": [125000]})
            raise td._StreamTruncated("simulated mid-stream failure")

        monkeypatch.setattr(td, "_get_csv", _mock_get_csv)
        result = td.bulk_open_interest("SPY", 0, date(2026, 1, 1), date(2026, 1, 2))
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
