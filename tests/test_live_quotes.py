"""Live last-price fetch (engine.live_quotes).

The HTTP call needs a live socket (and Polygon a key), so these pin the parts
that DON'T: symbol routing (US -> Polygon, suffixed/caret -> Yahoo), the two pure
parsers incl. price_basis + trade-time stamping, Polygon status surfacing, and
the load-bearing fail-safe — offline must be a clean ``{}``.
"""
from __future__ import annotations

from datetime import datetime, timezone

from engine import live_quotes as lq


def test_us_symbol_routing():
    assert lq.is_us_symbol("AAPL") and lq.is_us_symbol("SPY")
    assert not lq.is_us_symbol("0700.HK")
    assert not lq.is_us_symbol("510300.SS")
    assert not lq.is_us_symbol("GC=F")          # Yahoo future
    assert not lq.is_us_symbol("BTC-USD")       # crypto pair
    assert not lq.is_us_symbol("^VIX")          # caret index -> Yahoo (not entitled)
    assert not lq.is_us_symbol("")


def test_parse_polygon_snapshot_trade_basis_uses_trade_time():
    now = datetime(2026, 6, 21, 15, 0, tzinfo=timezone.utc)
    trade_ns = int(datetime(2026, 6, 21, 14, 50, tzinfo=timezone.utc).timestamp() * 1e9)
    upd_ns = int(datetime(2026, 6, 21, 14, 59, tzinfo=timezone.utc).timestamp() * 1e9)
    payload = {"tickers": [
        {"ticker": "AAPL", "updated": upd_ns,
         "lastTrade": {"p": 201.25, "t": trade_ns},
         "day": {"c": 200.0}, "prevDay": {"c": 198.0}},
        {"ticker": "NODATA", "day": {}, "prevDay": {}},
    ]}
    out = lq.parse_polygon_snapshot(payload, now=now)
    assert "NODATA" not in out
    q = out["AAPL"]
    assert q["price"] == 201.25 and q["price_basis"] == "trade"
    assert q["prev_close"] == 198.0
    assert q["delay_min"] == 10.0               # from TRADE time, not the 1m-old `updated`


def test_parse_polygon_snapshot_prevday_basis_is_not_live():
    # no trade / minute / day -> falls to prevDay close, basis 'prev'
    payload = {"tickers": [{"ticker": "ZZZ", "prevDay": {"c": 50.0}}]}
    q = lq.parse_polygon_snapshot(payload)["ZZZ"]
    assert q["price"] == 50.0 and q["price_basis"] == "prev"


def test_parse_yahoo_spark_basis_regular():
    now = datetime(2026, 6, 21, 15, 0, tzinfo=timezone.utc)
    ts_s = int(datetime(2026, 6, 21, 14, 30, tzinfo=timezone.utc).timestamp())
    payload = {"spark": {"result": [
        {"symbol": "0700.HK", "response": [{"meta": {
            "regularMarketPrice": 412.6, "regularMarketTime": ts_s,
            "previousClose": 408.0, "currency": "HKD"}}]},
        {"symbol": "BAD", "response": [{"meta": {}}]},
    ]}}
    out = lq.parse_yahoo_spark(payload, now=now)
    assert "BAD" not in out
    q = out["0700.HK"]
    assert q["price"] == 412.6 and q["source"] == "yahoo" and q["price_basis"] == "regular"
    assert q["delay_min"] == 30.0


def test_fetch_polygon_surfaces_not_authorized(monkeypatch):
    monkeypatch.setattr(lq, "_http_json",
                        lambda *a, **k: {"status": "NOT_AUTHORIZED", "message": "key"})
    out, status = lq.fetch_polygon(["AAPL"], "badkey")
    assert out == {} and status == "not_authorized"


def test_fetch_quotes_offline_is_clean_noop():
    diag = {}
    assert lq.fetch_quotes(["AAPL", "0700.HK"], offline=True, diag=diag) == {}
    assert diag["polygon_status"] == "offline"
    assert lq.fetch_quotes([], offline=False) == {}


def test_fetch_quotes_routes_without_polygon_key(monkeypatch):
    monkeypatch.setattr(lq.config, "secret", lambda name: None)
    seen = {}
    monkeypatch.setattr(lq, "fetch_yahoo",
                        lambda syms: {s: {"price": 1.0, "source": "yahoo"} for s in syms})
    monkeypatch.setattr(lq, "fetch_polygon",
                        lambda syms, key: (seen.setdefault("polygon", syms) or {}, "ok"))
    diag = {}
    out = lq.fetch_quotes(["AAPL", "GC=F"], us_source="polygon", diag=diag)
    assert "polygon" not in seen               # no key -> polygon not called
    assert set(out) == {"AAPL", "GC=F"}        # both resolved via Yahoo
    assert diag["polygon_status"] == "unused"


def test_globe_index_symbols_route_to_yahoo():
    """W2b: the 9 globe pebble index symbols are non-US (caret/suffix) -> Yahoo path."""
    INDEX_SYMS = [
        "^GSPC", "^GSPTSE", "000001.SS", "^HSI",
        "^N225", "^KS11", "^TWII", "^FTSE", "^STOXX50E",
    ]
    for sym in INDEX_SYMS:
        assert not lq.is_us_symbol(sym), f"{sym} should route to Yahoo (not US/Polygon)"
