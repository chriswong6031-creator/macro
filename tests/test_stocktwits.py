"""Pure fixture-based tests for collectors/stocktwits.py.

No network calls — parse_stream is pure; _merge + fetch use tmp_path + monkeypatching.
Tests cover: parse logic, bull/bear ratio math, missing sentiment handling,
rotation offset, PIT dedup, rate-limit early-stop.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import patch

import pandas as pd
import pytest

from collectors import stocktwits as ST


# ------------------------------------------------------------------ parse_stream

def _make_msg(sentiment: str | None) -> dict:
    """Build a minimal StockTwits message dict."""
    return {
        "id": 123,
        "body": "test message",
        "entities": {
            "sentiment": {"basic": sentiment} if sentiment else None,
        },
    }


def test_parse_all_bullish():
    """All tagged bullish: bull_ratio = 1.0."""
    msgs = [_make_msg("Bullish"), _make_msg("Bullish"), _make_msg("Bullish")]
    data = {"messages": msgs, "symbol": {"symbol": "AAPL", "watchlist_count": 1000}}
    row = ST.parse_stream(data, "AAPL")
    assert row is not None
    assert row["n_bullish"] == 3
    assert row["n_bearish"] == 0
    assert row["n_tagged"] == 3
    assert row["bull_ratio"] == 1.0
    assert row["watchlist_count"] == 1000


def test_parse_mixed_sentiment():
    """Mixed bullish/bearish messages compute correct ratio."""
    msgs = [
        _make_msg("Bullish"),
        _make_msg("Bullish"),
        _make_msg("Bearish"),
        _make_msg(None),   # untagged
    ]
    data = {"messages": msgs, "symbol": {"symbol": "NVDA", "watchlist_count": 500}}
    row = ST.parse_stream(data, "NVDA")
    assert row["n_bullish"] == 2
    assert row["n_bearish"] == 1
    assert row["n_tagged"] == 3
    assert row["bull_ratio"] == round(2 / 3, 4)
    assert row["n_messages"] == 4


def test_parse_no_sentiment_tags():
    """No tagged messages: bull_ratio is None (not 0.0 or NaN)."""
    msgs = [_make_msg(None), _make_msg(None)]
    data = {"messages": msgs, "symbol": {"symbol": "SPY", "watchlist_count": 200}}
    row = ST.parse_stream(data, "SPY")
    assert row is not None
    assert row["n_tagged"] == 0
    assert row["bull_ratio"] is None
    assert row["n_messages"] == 2


def test_parse_empty_messages():
    """Zero messages: row is returned with all counts 0."""
    data = {"messages": [], "symbol": {"symbol": "SPY", "watchlist_count": 200}}
    row = ST.parse_stream(data, "SPY")
    assert row is not None
    assert row["n_messages"] == 0
    assert row["n_bullish"] == 0


def test_parse_missing_messages_key_returns_none():
    """If 'messages' key is absent (bad response), returns None."""
    row = ST.parse_stream({"error": "Symbol not found"}, "XXXX")
    assert row is None


def test_parse_no_watchlist_count():
    """Absent watchlist_count field -> None in the row, not a crash."""
    data = {"messages": [_make_msg("Bullish")], "symbol": {"symbol": "QQQ"}}
    row = ST.parse_stream(data, "QQQ")
    assert row is not None
    assert row["watchlist_count"] is None


# ------------------------------------------------------------------ _today_offset rotation

def test_offset_in_bounds():
    """Offset is always in [0, n_total - n_pick]."""
    n_total, n_pick = 300, 150
    offset = ST._today_offset(n_total, n_pick)
    assert 0 <= offset <= n_total - n_pick


def test_offset_zero_when_universe_leq_pick():
    """When universe fits within the cap, offset must be 0."""
    assert ST._today_offset(100, 150) == 0
    assert ST._today_offset(150, 150) == 0


# ------------------------------------------------------------------ _merge / PIT dedup

def test_merge_writes_parquet(tmp_path, monkeypatch):
    """_merge stores rows and adds _collected + _collected_date columns."""
    from lib import config
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)

    adapter = ST.StockTwitsAdapter.__new__(ST.StockTwitsAdapter)
    adapter.name = ST.StockTwitsAdapter.name
    adapter.group = ST.StockTwitsAdapter.group

    df = pd.DataFrame([
        {"ticker": "AAPL", "n_messages": 10, "n_bullish": 7, "n_bearish": 1,
         "n_tagged": 8, "bull_ratio": 0.875, "watchlist_count": 900},
    ])
    n = adapter._merge(df)
    assert n == 1

    path = tmp_path / "stocktwits" / "sentiment.parquet"
    assert path.exists()
    stored = pd.read_parquet(path)
    assert "_collected" in stored.columns
    assert "_collected_date" in stored.columns
    assert stored.iloc[0]["ticker"] == "AAPL"


def test_merge_dedup_one_per_day(tmp_path, monkeypatch):
    """Two merges for the same ticker on the same date produce only one stored row."""
    from lib import config
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)

    adapter = ST.StockTwitsAdapter.__new__(ST.StockTwitsAdapter)
    adapter.name = ST.StockTwitsAdapter.name
    adapter.group = ST.StockTwitsAdapter.group

    row = {"ticker": "MSFT", "n_messages": 5, "n_bullish": 3, "n_bearish": 1,
           "n_tagged": 4, "bull_ratio": 0.75, "watchlist_count": 400}
    adapter._merge(pd.DataFrame([row]))
    adapter._merge(pd.DataFrame([{**row, "n_bullish": 99}]))  # second call, same day

    stored = pd.read_parquet(tmp_path / "stocktwits" / "sentiment.parquet")
    msft_rows = stored[stored["ticker"] == "MSFT"]
    assert len(msft_rows) == 1
    # keeps first -> original n_bullish=3 not the 99 from second call
    assert msft_rows.iloc[0]["n_bullish"] == 3


def test_merge_empty_is_noop(tmp_path, monkeypatch):
    """_merge on empty DataFrame returns 0 and creates no file."""
    from lib import config
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)

    adapter = ST.StockTwitsAdapter.__new__(ST.StockTwitsAdapter)
    adapter.name = ST.StockTwitsAdapter.name
    adapter.group = ST.StockTwitsAdapter.group

    n = adapter._merge(pd.DataFrame())
    assert n == 0
    assert not (tmp_path / "stocktwits" / "sentiment.parquet").exists()


# ------------------------------------------------------------------ fetch: rate-limit handling

def test_fetch_stops_on_rate_limit(tmp_path, monkeypatch):
    """A 429 rate-limit response causes fetch to stop early (no crash)."""
    from lib import config
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(config, "ROOT", tmp_path)
    (tmp_path / "baskets").mkdir()
    (tmp_path / "baskets" / "membership.json").write_text(json.dumps({
        "baskets": {"tech": {"members": [
            {"ticker": "AAPL"}, {"ticker": "NVDA"}, {"ticker": "MSFT"},
        ]}}
    }))

    adapter = ST.StockTwitsAdapter()
    call_log = []

    def mock_fetch_symbol(symbol):
        call_log.append(symbol)
        if symbol == "NVDA":
            return "rate_limited"
        msgs = [_make_msg("Bullish")]
        return {"messages": msgs, "symbol": {"symbol": symbol, "watchlist_count": 100}}

    with patch.object(adapter, "_fetch_symbol", side_effect=mock_fetch_symbol), \
         patch("time.sleep"):
        result = adapter.fetch()

    ingest = result["stocktwits__ingest"]
    assert ingest["rate_limited"].iloc[0] == True  # noqa: E712 — np.True_ needs ==, not `is`
    # AAPL was processed, NVDA triggered rate limit, MSFT was never called
    assert "MSFT" not in call_log


# ------------------------------------------------------------------ fetch: happy path

def test_fetch_stores_rows(tmp_path, monkeypatch):
    """Full fetch stores one row per unique successfully-polled symbol."""
    from lib import config
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(config, "ROOT", tmp_path)
    (tmp_path / "baskets").mkdir()
    # Use enough members so the rotation-wrap doesn't duplicate entries within one run.
    # With TOP_N=150 and 200 members the offset is in [0,50] and picks 150 distinct names.
    members = [{"ticker": f"T{i:03d}"} for i in range(200)]
    (tmp_path / "baskets" / "membership.json").write_text(json.dumps({
        "baskets": {"tech": {"members": members}}
    }))

    def mock_fetch(symbol):
        return {
            "messages": [_make_msg("Bullish"), _make_msg("Bearish"), _make_msg(None)],
            "symbol": {"symbol": symbol, "watchlist_count": 500},
        }

    adapter = ST.StockTwitsAdapter()
    with patch.object(adapter, "_fetch_symbol", side_effect=mock_fetch), \
         patch("time.sleep"):
        result = adapter.fetch()

    ingest = result["stocktwits__ingest"]
    assert ingest["rate_limited"].iloc[0] == False  # noqa: E712
    # All 150 polled symbols produce rows; stored = 150 (one per ticker, same day dedup)
    assert ingest["new_rows"].iloc[0] == ST.TOP_N

    stored = pd.read_parquet(tmp_path / "stocktwits" / "sentiment.parquet")
    assert len(stored) == ST.TOP_N
    # spot-check parse output on any stored row
    sample = stored.iloc[0]
    assert sample["n_bullish"] == 1
    assert sample["n_bearish"] == 1
    assert sample["n_tagged"] == 2
    assert sample["bull_ratio"] == 0.5
