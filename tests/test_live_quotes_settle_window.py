"""TS-U5 settle-clean US quote routing — post-close the Polygon trade/minute
rungs carry extended-hours prints, so fetch_quotes routes US symbols to Yahoo
(regularMarketPrice pins the official settle, basis 'regular')."""
from __future__ import annotations

from datetime import datetime, timezone

from engine import live_quotes as lq


def _utc(y, m, d, h, mi):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


class TestSettleWindow:
    # 2026-07-09 is a Thursday; EDT (UTC-4).
    def test_rth_stays_polygon(self):
        assert lq._us_settle_window(_utc(2026, 7, 9, 19, 55)) is False  # 15:55 ET

    def test_post_close_routes_yahoo(self):
        assert lq._us_settle_window(_utc(2026, 7, 9, 20, 5)) is True    # 16:05 ET

    def test_evening_routes_yahoo(self):
        assert lq._us_settle_window(_utc(2026, 7, 10, 2, 0)) is True    # 22:00 ET

    def test_premarket_stays_polygon(self):
        # premarket tape is a designed feature (FTR W2c)
        assert lq._us_settle_window(_utc(2026, 7, 9, 12, 0)) is False   # 08:00 ET

    def test_overnight_routes_yahoo(self):
        assert lq._us_settle_window(_utc(2026, 7, 9, 7, 30)) is True    # 03:30 ET

    def test_weekend_routes_yahoo(self):
        assert lq._us_settle_window(_utc(2026, 7, 11, 16, 0)) is True   # Saturday


class TestRouting:
    def test_us_skips_polygon_in_settle_window(self, monkeypatch):
        calls = {"polygon": 0, "yahoo": []}

        def fake_polygon(symbols, key):
            calls["polygon"] += 1
            return ({s: {"price": 1.0, "quote_ts": None, "source": "polygon",
                         "price_basis": "trade", "delay_min": 0.0,
                         "prev_close": 1.0, "currency": "USD"} for s in symbols}, "ok")

        def fake_yahoo(symbols):
            calls["yahoo"].extend(symbols)
            return {s: {"price": 1.0, "quote_ts": None, "source": "yahoo",
                        "price_basis": "regular", "delay_min": 0.0,
                        "prev_close": 1.0, "currency": "USD"} for s in symbols}

        monkeypatch.setattr(lq, "fetch_polygon", fake_polygon)
        monkeypatch.setattr(lq, "fetch_yahoo", fake_yahoo)
        monkeypatch.setattr(lq, "_us_settle_window", lambda now=None: True)
        monkeypatch.setattr(lq.config, "secret", lambda name: "test-key")

        out = lq.fetch_quotes(["AAPL", "MSFT"], us_source="polygon")
        assert calls["polygon"] == 0
        assert set(calls["yahoo"]) >= {"AAPL", "MSFT"}
        assert out["AAPL"]["price_basis"] == "regular"

    def test_us_uses_polygon_during_rth(self, monkeypatch):
        calls = {"polygon": 0}

        def fake_polygon(symbols, key):
            calls["polygon"] += 1
            return ({s: {"price": 1.0, "quote_ts": None, "source": "polygon",
                         "price_basis": "trade", "delay_min": 0.0,
                         "prev_close": 1.0, "currency": "USD"} for s in symbols}, "ok")

        monkeypatch.setattr(lq, "fetch_polygon", fake_polygon)
        monkeypatch.setattr(lq, "fetch_yahoo", lambda symbols: {})
        monkeypatch.setattr(lq, "_us_settle_window", lambda now=None: False)
        monkeypatch.setattr(lq.config, "secret", lambda name: "test-key")

        lq.fetch_quotes(["AAPL"], us_source="polygon")
        assert calls["polygon"] == 1
