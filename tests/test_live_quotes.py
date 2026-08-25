"""Live last-price fetch (engine.live_quotes).

Pins symbol routing (US -> Polygon, mainland -> entitled Tushare -> Tencent,
other intl -> Yahoo), pure parsers, exchange clocks, no-trade semantics, provider
fallback order, and the offline fail-safe without requiring live sockets/secrets.
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
    assert not lq.is_us_symbol("GC=F")
    assert not lq.is_us_symbol("BTC-USD")
    assert not lq.is_us_symbol("^VIX")
    assert not lq.is_us_symbol("")


def test_cn_symbol_routing_and_provider_codes():
    assert lq.is_cn_symbol("600519.SS")
    assert lq.is_cn_symbol("002241.SZ")
    assert lq.is_cn_symbol("000001.SS")
    assert not lq.is_cn_symbol("0700.HK")
    assert not lq.is_cn_symbol("AAPL")
    assert lq._tencent_code("600519.SS") == "sh600519"
    assert lq._tencent_code("002241.SZ") == "sz002241"
    assert lq._tushare_code("600519.SS") == "600519.SH"
    assert lq._tushare_code("002241.SZ") == "002241.SZ"


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
    assert q["delay_min"] == 10.0


def test_parse_polygon_snapshot_prevday_basis_is_not_live():
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


def test_parse_tushare_rt_k_is_live_and_uses_trade_time():
    now = datetime(2026, 8, 25, 1, 38, tzinfo=timezone.utc)  # 09:38 China
    rows = [{
        "ts_code": "603026.SH", "pre_close": 63.90, "open": 64.20,
        "high": 65.30, "low": 64.05, "close": 65.10, "vol": 1_234_500,
        "amount": 80_000_000, "num": 20_001, "trade_time": "2026-08-25 09:37:00",
    }]
    q = lq.parse_tushare_rt_k(rows, now=now)["603026.SS"]
    assert q["price"] == 65.10 and q["prev_close"] == 63.90
    assert q["source"] == "tushare-rt-k" and q["price_basis"] == "trade"
    assert q["quote_ts"] == "2026-08-25T01:37:00+00:00"
    assert q["quote_ts_synthetic"] is False
    assert q["delay_min"] == 1.0
    assert q["day_volume"] == 1_234_500       # Tushare rt_k volume is shares
    assert q["day_high"] == 65.30 and q["day_low"] == 64.05


def test_parse_tushare_requires_real_trade_clock():
    rows = [{
        "ts_code": "603026.SH", "pre_close": 63.90, "open": 64.20,
        "high": 65.30, "low": 64.05, "close": 65.10, "vol": 1_234_500,
        "amount": 80_000_000, "trade_time": None,
    }]
    assert lq.parse_tushare_rt_k(rows) == {}


def test_parse_tushare_suspended_no_trade_placeholder_is_absent():
    rows = [{
        "ts_code": "002155.SZ", "pre_close": 24.56, "open": 0,
        "high": 0, "low": 0, "close": 24.56, "vol": 0, "amount": 0,
        "num": 0, "trade_time": "2026-08-25 09:37:00",
    }]
    assert lq.parse_tushare_rt_k(rows) == {}


def test_parse_tencent_a_share_is_live_and_uses_exchange_clock():
    now = datetime(2026, 8, 25, 1, 38, tzinfo=timezone.utc)
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


def test_fetch_tushare_cn_uses_existing_client_and_returns_only_real_rows(monkeypatch):
    class FakeClient:
        @staticmethod
        def enabled():
            return True

        @staticmethod
        def query(api_name, **kwargs):
            assert api_name == "rt_k"
            assert kwargs["ts_code"] == "600519.SH,000001.SZ"
            assert "trade_time" in kwargs["fields"]
            assert kwargs["_return_empty"] is True
            return [{
                "ts_code": "600519.SS", "pre_close": 1300, "open": 1305,
                "high": 1312, "low": 1298, "close": 1310, "vol": 123,
                "amount": 160_000, "trade_time": "2026-08-25 09:37:00",
            }]

    monkeypatch.setattr(lq, "_load_tushare_client", lambda: FakeClient)
    out, missing, status = lq.fetch_tushare_cn(["600519.SS", "000001.SZ"])
    assert out["600519.SS"]["source"] == "tushare-rt-k"
    assert missing == ["000001.SZ"]
    assert status == "ok"


def test_fetch_tushare_cn_without_token_falls_through(monkeypatch):
    class DisabledClient:
        @staticmethod
        def enabled():
            return False

    monkeypatch.setattr(lq, "_load_tushare_client", lambda: DisabledClient)
    out, missing, status = lq.fetch_tushare_cn(["600519.SS"])
    assert out == {} and missing == ["600519.SS"] and status == "disabled"


def test_fetch_polygon_surfaces_not_authorized(monkeypatch):
    monkeypatch.setattr(lq, "_http_json",
                        lambda *a, **k: {"status": "NOT_AUTHORIZED", "message": "key"})
    out, status = lq.fetch_polygon(["AAPL"], "badkey")
    assert out == {} and status == "not_authorized"


def test_fetch_quotes_offline_is_clean_noop():
    diag = {}
    assert lq.fetch_quotes(["AAPL", "600519.SS", "0700.HK"], offline=True, diag=diag) == {}
    assert diag["polygon_status"] == "offline"
    assert diag["tushare_status"] == "offline"
    assert diag["tencent_status"] == "offline"
    assert lq.fetch_quotes([], offline=False) == {}


def test_cn_prefers_tushare_and_does_not_call_tencent_for_resolved_name(monkeypatch):
    monkeypatch.setattr(lq.config, "secret", lambda name: None)
    seen = {"tencent": [], "yahoo": []}
    monkeypatch.setattr(lq, "fetch_tushare_cn",
                        lambda syms: ({"600519.SS": {"price": 1310.0, "source": "tushare-rt-k"}}, [], "ok"))
    monkeypatch.setattr(lq, "fetch_tencent_cn",
                        lambda syms: seen["tencent"].append(list(syms)) or ({}, [], "ok"))
    monkeypatch.setattr(lq, "fetch_yahoo",
                        lambda syms: seen["yahoo"].append(list(syms)) or
                        {s: {"price": 1.0, "source": "yahoo"} for s in syms})
    diag = {}
    out = lq.fetch_quotes(["600519.SS", "0700.HK"], us_source="polygon", diag=diag)
    assert out["600519.SS"]["source"] == "tushare-rt-k"
    assert seen["tencent"] == []
    assert seen["yahoo"] == [["0700.HK"]]
    assert diag["tushare_status"] == "ok"
    assert diag["tencent_status"] == "unused"


def test_tushare_miss_falls_to_tencent_not_yahoo(monkeypatch):
    monkeypatch.setattr(lq.config, "secret", lambda name: None)
    seen = []
    monkeypatch.setattr(lq, "fetch_tushare_cn",
                        lambda syms: ({}, list(syms), "disabled"))
    monkeypatch.setattr(lq, "fetch_tencent_cn",
                        lambda syms: ({"600519.SS": {"price": 1309.0, "source": "tencent"}}, [], "ok"))
    monkeypatch.setattr(lq, "fetch_yahoo",
                        lambda syms: seen.append(list(syms)) or {})
    out = lq.fetch_quotes(["600519.SS"], us_source="polygon")
    assert out["600519.SS"]["source"] == "tencent"
    assert seen == []


def test_successful_live_chain_no_trade_does_not_fall_back_to_yahoo(monkeypatch):
    monkeypatch.setattr(lq.config, "secret", lambda name: None)
    seen = []
    monkeypatch.setattr(lq, "fetch_tushare_cn",
                        lambda syms: ({}, list(syms), "ok"))
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
    monkeypatch.setattr(lq, "fetch_tushare_cn",
                        lambda syms: ({}, list(syms), "unavailable"))
    monkeypatch.setattr(lq, "fetch_tencent_cn",
                        lambda syms: ({}, list(syms), "no_response"))
    monkeypatch.setattr(lq, "fetch_yahoo",
                        lambda syms: {s: {"price": 10.0, "source": "yahoo"} for s in syms})
    diag = {}
    out = lq.fetch_quotes(["300751.SZ"], us_source="polygon", diag=diag)
    assert out["300751.SZ"]["source"] == "yahoo"
    assert diag["tushare_status"] == "unavailable"
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
    assert "polygon" not in seen
    assert set(out) == {"AAPL", "GC=F"}
    assert diag["polygon_status"] == "unused"
    assert diag["tushare_status"] == "unused"
    assert diag["tencent_status"] == "unused"


def test_globe_index_symbols_route_to_expected_non_us_provider():
    """Mainland indexes enter live CN chain; other global indexes remain Yahoo."""
    yahoo_syms = ["^GSPC", "^GSPTSE", "^HSI", "^N225", "^KS11", "^TWII", "^FTSE", "^STOXX50E"]
    for sym in yahoo_syms:
        assert not lq.is_us_symbol(sym)
        assert not lq.is_cn_symbol(sym)
    assert lq.is_cn_symbol("000001.SS")
