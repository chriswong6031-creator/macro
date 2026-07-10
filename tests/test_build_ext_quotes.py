"""tests/test_build_ext_quotes.py — Unit tests for scripts/build_ext_quotes.py.

Tests pure extraction and window functions only — no network calls, no R2.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

# Ensure repo root is on sys.path.
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.build_ext_quotes import (
    DEFAULT_SYMBOLS,
    classify_ext_session,
    extract_ext_print,
    is_ext_window_now,
)

ET = ZoneInfo("America/New_York")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _et(date_str: str, hhmm: str) -> datetime:
    """Return a tz-aware datetime in ET for the given date and HH:MM."""
    h, m = [int(x) for x in hhmm.split(":")]
    return datetime(
        *[int(x) for x in date_str.split("-")], h, m, 0, tzinfo=ET
    )


# A session date that is a NYSE trading day (2026-07-10 = Thursday).
_TRADING_DAY = "2026-07-10"
# A weekend date that is NOT a trading day.
_WEEKEND = "2026-07-12"


# ---------------------------------------------------------------------------
# is_ext_window_now
# ---------------------------------------------------------------------------

class TestIsExtWindowNow:
    def test_pre_market_inside(self):
        assert is_ext_window_now(_et(_TRADING_DAY, "06:00")) is True

    def test_pre_market_boundary_open(self):
        # 04:00 ET is inclusive start of pre-market.
        assert is_ext_window_now(_et(_TRADING_DAY, "04:00")) is True

    def test_pre_market_boundary_close(self):
        # 09:30 is RTH open — NOT in ext window.
        assert is_ext_window_now(_et(_TRADING_DAY, "09:30")) is False

    def test_rth_not_in_ext_window(self):
        assert is_ext_window_now(_et(_TRADING_DAY, "12:00")) is False

    def test_post_market_inside(self):
        assert is_ext_window_now(_et(_TRADING_DAY, "17:00")) is True

    def test_post_market_boundary_open(self):
        # 16:00 is inclusive start of post-market.
        assert is_ext_window_now(_et(_TRADING_DAY, "16:00")) is True

    def test_post_market_boundary_close(self):
        # 20:00 is exclusive end of post-market.
        assert is_ext_window_now(_et(_TRADING_DAY, "20:00")) is False

    def test_overnight_not_ext(self):
        # 02:00 ET is deep overnight — not a defined ext window.
        assert is_ext_window_now(_et(_TRADING_DAY, "02:00")) is False

    def test_weekend_not_ext(self):
        # Weekend trading session check returns False.
        assert is_ext_window_now(_et(_WEEKEND, "07:00")) is False


# ---------------------------------------------------------------------------
# classify_ext_session
# ---------------------------------------------------------------------------

class TestClassifyExtSession:
    def test_pre(self):
        assert classify_ext_session(_et(_TRADING_DAY, "07:00")) == "pre"

    def test_post(self):
        assert classify_ext_session(_et(_TRADING_DAY, "18:00")) == "post"

    def test_rth_is_none(self):
        assert classify_ext_session(_et(_TRADING_DAY, "11:00")) == "none"

    def test_overnight_is_none(self):
        assert classify_ext_session(_et(_TRADING_DAY, "02:00")) == "none"


# ---------------------------------------------------------------------------
# extract_ext_print
# ---------------------------------------------------------------------------

def _make_chart(
    timestamps: list[int],
    closes: list[float],
    sess_start: int,
    sess_end: int,
    rth_end: int,
    regular_price: float,
    session: str = "post",
) -> dict:
    """Build a minimal Yahoo chart JSON structure for testing."""
    ctp_key = "pre" if session == "pre" else "post"
    return {
        "chart": {
            "result": [
                {
                    "meta": {
                        "regularMarketPrice": regular_price,
                        "currentTradingPeriod": {
                            ctp_key: {"start": sess_start, "end": sess_end},
                            "regular": {"end": rth_end},
                        },
                    },
                    "timestamp": timestamps,
                    "indicators": {
                        "quote": [{"close": closes}]
                    },
                }
            ]
        }
    }


class TestExtractExtPrint:
    # Realistic post-market example:
    # Regular session closed at Unix 1720814400 (16:00 ET 2026-07-10).
    # Post-market bar at 1720814460 (16:01 ET).
    _RTH_END = 1720814400
    _POST_START = 1720814400
    _POST_END = 1720828800  # 20:00 ET
    _CLOSE = 212.30

    def _post_chart(self, ts: int, price: float) -> dict:
        return _make_chart(
            timestamps=[self._RTH_END - 60, ts],
            closes=[self._CLOSE, price],
            sess_start=self._POST_START,
            sess_end=self._POST_END,
            rth_end=self._RTH_END,
            regular_price=self._CLOSE,
            session="post",
        )

    def test_valid_post_market_print(self):
        chart = self._post_chart(self._RTH_END + 60, 213.45)
        result = extract_ext_print("AAPL", chart, "post")
        assert result is not None
        assert result["extPrice"] == 213.45
        assert result["extTs"] == self._RTH_END + 60
        assert result["close"] == self._CLOSE

    def test_pre_market_print(self):
        # Build a pre-market chart.
        pre_start = 1720771200   # 04:00 ET
        pre_end = 1720785000     # 09:30 ET
        rth_end = 1720814400     # 16:00 ET (previous session reference)
        chart = _make_chart(
            timestamps=[pre_start + 120],
            closes=[210.50],
            sess_start=pre_start,
            sess_end=pre_end,
            rth_end=pre_start - 1,  # rth_end before pre_start → ext print qualifies
            regular_price=209.80,
            session="pre",
        )
        result = extract_ext_print("AAPL", chart, "pre")
        assert result is not None
        assert result["extPrice"] == 210.50
        assert result["close"] == 209.80

    def test_no_print_when_empty_result(self):
        chart = {"chart": {"result": []}}
        assert extract_ext_print("AAPL", chart, "post") is None

    def test_no_print_when_only_rth_bar_outside_session_window(self):
        # Only a bar from before post-market start (inside RTH) → nothing qualifies.
        chart = self._post_chart(self._RTH_END - 100, 212.10)
        result = extract_ext_print("AAPL", chart, "post")
        # The bar at RTH_END - 100 is outside [POST_START, POST_END) and
        # even if included, its ts <= rth_end so it would be rejected.
        assert result is None

    def test_no_print_when_ts_not_newer_than_rth_end(self):
        # Bar exactly at rth_end — should be rejected (not newer).
        chart = self._post_chart(self._RTH_END, 212.20)
        # ts == rth_end: the guard requires ts > rth_end_ts.
        result = extract_ext_print("AAPL", chart, "post")
        assert result is None, "ts == rth_end must be rejected"

    def test_null_close_skipped(self):
        # Inject a bar with None close before a good bar.
        chart = {
            "chart": {
                "result": [
                    {
                        "meta": {
                            "regularMarketPrice": self._CLOSE,
                            "currentTradingPeriod": {
                                "post": {"start": self._POST_START, "end": self._POST_END},
                                "regular": {"end": self._RTH_END},
                            },
                        },
                        "timestamp": [self._RTH_END + 60, self._RTH_END + 120],
                        "indicators": {"quote": [{"close": [None, 214.00]}]},
                    }
                ]
            }
        }
        result = extract_ext_print("AAPL", chart, "post")
        assert result is not None
        assert result["extPrice"] == 214.00

    def test_missing_session_boundaries_returns_none(self):
        # No currentTradingPeriod.post block.
        chart = {
            "chart": {
                "result": [
                    {
                        "meta": {
                            "regularMarketPrice": self._CLOSE,
                            "currentTradingPeriod": {},
                        },
                        "timestamp": [self._RTH_END + 60],
                        "indicators": {"quote": [{"close": [213.45]}]},
                    }
                ]
            }
        }
        assert extract_ext_print("AAPL", chart, "post") is None

    def test_malformed_json_returns_none(self):
        assert extract_ext_print("AAPL", {}, "post") is None
        assert extract_ext_print("AAPL", {"chart": None}, "post") is None


# ---------------------------------------------------------------------------
# DEFAULT_SYMBOLS sanity
# ---------------------------------------------------------------------------

class TestDefaultSymbols:
    def test_no_duplicates(self):
        assert len(DEFAULT_SYMBOLS) == len(set(DEFAULT_SYMBOLS)), \
            "DEFAULT_SYMBOLS must not contain duplicates"

    def test_min_length(self):
        assert len(DEFAULT_SYMBOLS) >= 80, \
            f"Expected ≥80 symbols, got {len(DEFAULT_SYMBOLS)}"

    def test_core_symbols_present(self):
        for sym in ("SPY", "QQQ", "AAPL", "NVDA", "MSFT", "TSLA"):
            assert sym in DEFAULT_SYMBOLS, f"{sym} must be in DEFAULT_SYMBOLS"

    def test_no_crypto_or_forex(self):
        # Crypto (BTC-USD) and raw Forex have no Yahoo ext-hours bars.
        forbidden = {"BTC-USD", "ETH-USD", "EURUSD=X"}
        overlap = set(DEFAULT_SYMBOLS) & forbidden
        assert not overlap, f"Forbidden symbols in DEFAULT_SYMBOLS: {overlap}"
