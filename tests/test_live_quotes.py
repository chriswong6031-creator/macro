"""Live last-price fetch (engine.live_quotes).

The HTTP call needs a live socket (and Polygon a key), so these pin the parts
that DON'T: symbol routing (US -> Polygon, mainland -> Tencent, other intl ->
Yahoo), pure parsers incl. price_basis + market-time stamping, provider status
surfacing, and the load-bearing fail-safe — offline must be a clean ``{}``.
"""
from __future__ import annotations

from datetime import datetime, timezone

from engine import live_quotes as lq


def _tencent_record(code: str, fields: dict[int, object]) -> str:
    row = ["0"] * 40
    row[0] = "1"
    row[1] = "TestCo"
    row[2] = code[2:]
    for idx, value in fields.items():
        row[idx] = str(value)
    return f'v_{code}="{"~".join(row)}";'


def test_us_symbol_routing():
    assert lq.is_us_symbol("AAPL") and lq.is_us_symbol("SPY")
    assert not lq.is_us_symbol("0700.HK")
    assert not lq.is_us_symbol("510300.SS")
    assert not lq.is_us_symbol("GC=F")          # Yahoo future
    assert not lq.is_us_symbol("BTC-USD")       # crypto pair
    assert not lq.is_us_symbol("^VIX")          # caret index -> Yahoo (not entitled)
    assert not lq.is_us_symbol("")


def test_cn_symbol_routing_and_tencent_codes():
    assert lq.is_cn_symbol("600519.SS")
    assert lq.is_cn_symbol("002241.SZ")
    assert lq.is_cn_symbol("000001.SS")          # SSE Composite also uses Tencent
    assert not lq.is_cn_symbol("0700.HK")
    assert not lq.is_cn_symbol("AAPL")
    assert lq._tencent_code("600519.SS") == "sh600519"
    assert lq._tencent_code("002241.SZ") == "sz002241"


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


def test_parse_tencent_a_share_is_live_and_uses_exchange_clock():
    now = datetime(2026, 8, 25, 1, 38, tzinfo=timezone.utc)  # 09:38 China
    text = _tencent_record("sh603026", {
        3: "65.10", 4: "63.90", 5: "64.20", 6: "12345",
        30: "20260825093700", 32: "1.88", 33: "65.30", 34: "64.05",
        37: "80000000",
    })
    q = lq.parse_tencent_quotes(text, now=now)["603026.SS"]
    assert q["price"] == 65.10
    assert q["prev_close"] == 63.90
    assert q["source"] == "tencent" and q["price_basis"] == "trade"
    assert q["quote_ts"] == "2026-08-25T01:37:00+00:00"
    assert q["quote_ts_synthetic"] is False
    assert q["delay_min"] == 1.0
    assert q["day_volume"] == 1_234_500       # Tencent A-share volume is lots
    assert q["day_high"] == 65.30 and q["day_low"] == 64.05


def test_parse_tencent_suspended_no_trade_placeholder_is_absent():
    text = _tencent_record("sz002155", {
        3: "24.56", 4: "24.56", 5: "0.00", 6: "0",
        30: "20260825093700", 32: "0.00", 33: "0.00", 34: "0.00", 37: "0",
    })
    assert lq.parse_tencent_quotes(text) == {}


def test_fetch_polygon_surfaces_not_authorized(monkeypatch):
    monkeypatch.setattr(lq, "_http_json",
                        lambda *a, **k: {"status": "NOT_AUTHORIZED", "message": "key"})
    out, status = lq.fetch_polygon(["AAPL"], "badkey")
    assert out == {} and status == "not_authorized"


def test_fetch_quotes_offline_is_clean_noop():
    diag = {}
    assert lq.fetch_quotes(["AAPL", "600519.SS", "0700.HK"], offline=True, diag=diag) == {}
    assert diag["polygon_status"] == "offline"
    assert diag["tencent_status"] == "offline"
    assert lq.fetch_quotes([], offline=False) == {}


def test_fetch_quotes_routes_cn_to_tencent_and_other_intl_to_yahoo(monkeypatch):
    monkeypatch.setattr(lq.config, "secret", lambda name: None)
    seen = {"yahoo": []}
    monkeypatch.setattr(lq, "fetch_tencent_cn",
                        lambda syms: ({"600519.SS": {"price": 1301.0, "source": "tencent"}}, [], "ok"))
    monkeypatch.setattr(lq, "fetch_yahoo",
                        lambda syms: seen["yahoo"].append(list(syms)) or
                        {s: {"price": 1.0, "source": "yahoo"} for s in syms})
    monkeypatch.setattr(lq, "fetch_polygon",
                        lambda syms, key: ({}, "ok"))
    diag = {}
    out = lq.fetch_quotes(["600519.SS", "0700.HK", "GC=F"], us_source="polygon", diag=diag)
    assert out["600519.SS"]["source"] == "tencent"
    assert set(out) == {"600519.SS", "0700.HK", "GC=F"}
    assert seen["yahoo"] == [["0700.HK", "GC=F"]]
    assert diag["tencent_status"] == "ok"


def test_successful_tencent_no_trade_does_not_fall_back_to_yahoo(monkeypatch):
    monkeypatch.setattr(lq.config, "secret", lambda name: None)
    seen = []
    monkeypatch.setattr(lq, "fetch_tencent_cn",
                        lambda syms: ({}, [], "ok"))
    monkeypatch.setattr(lq, "fetch_yahoo",
                        lambda syms: seen.append(list(syms)) or
                        {s: {"price": 24.56, "source": "yahoo"} for s in syms})
    out = lq.fetch_quotes(["002155.SZ"], us_source="polygon")
    assert out == {}
    assert seen == []


def test_failed_tencent_transport_falls_back_to_yahoo(monkeypatch):
    monkeypatch.setattr(lq.config, "secret", lambda name: None)
    monkeypatch.setattr(lq, "fetch_tencent_cn",
                        lambda syms: ({}, list(syms), "no_response"))
    monkeypatch.setattr(lq, "fetch_yahoo",
                        lambda syms: {s: {"price": 10.0, "source": "yahoo"} for s in syms})
    diag = {}
    out = lq.fetch_quotes(["300751.SZ"], us_source="polygon", diag=diag)
    assert out["300751.SZ"]["source"] == "yahoo"
    assert diag["tencent_status"] == "no_response"


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
    assert diag["tencent_status"] == "unused"


def test_globe_index_symbols_route_to_expected_non_us_provider():
    """Mainland indices use Tencent; other global indices remain on Yahoo."""
    yahoo_syms = ["^GSPC", "^GSPTSE", "^HSI", "^N225", "^KS11", "^TWII", "^FTSE", "^STOXX50E"]
    for sym in yahoo_syms:
        assert not lq.is_us_symbol(sym)
        assert not lq.is_cn_symbol(sym)
    assert lq.is_cn_symbol("000001.SS")
