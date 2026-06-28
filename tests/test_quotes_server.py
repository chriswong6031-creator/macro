"""quotes_server pure-logic tests — offline (no socket, no upstream fetch)."""
from __future__ import annotations

from scripts import quotes_server as qs


def test_canonical_symbols_dedupe_sort_validate_cap():
    assert qs.canonical_symbols("aapl, MSFT,aapl ,0700.hk") == ["0700.HK", "AAPL", "MSFT"]
    assert qs.canonical_symbols("^VIX,GC=F,BRK-B") == ["BRK-B", "GC=F", "^VIX"]
    assert qs.canonical_symbols("bad symbol!, ok") == ["OK"]      # space/!-> dropped
    assert qs.canonical_symbols("") == []
    assert qs.canonical_symbols(None) == []
    assert len(qs.canonical_symbols(",".join(f"SYM{i}" for i in range(500)))) == qs._MAX_SYMBOLS


def test_to_worker_quotes_maps_and_drops():
    fetched = {
        "AAPL": {"price": 100.5, "quote_ts": "2026-06-23T14:00:00+00:00",
                 "source": "polygon", "price_basis": "trade", "prev_close": 99.0},
        "NOPRICE": {"price": None, "source": "yahoo"},      # dropped
    }
    out = qs.to_worker_quotes(fetched)
    assert set(out) == {"AAPL"}
    a = out["AAPL"]
    assert a["price"] == 100.5 and a["source"] == "polygon" and a["basis"] == "trade"
    assert a["prevClose"] == 99.0
    assert a["ts"] == int(__import__("datetime").datetime
                          .fromisoformat("2026-06-23T14:00:00+00:00").timestamp() * 1000)


def test_to_worker_quotes_tolerates_missing_ts():
    out = qs.to_worker_quotes({"X": {"price": 5, "source": "yahoo"}})
    assert out["X"]["ts"] is None and out["X"]["prevClose"] is None


def test_build_payload_uses_injected_fetcher():
    calls = {}

    def fake(symbols):
        calls["syms"] = symbols
        return {"SPY": {"price": 500.0, "quote_ts": None, "source": "yahoo",
                        "price_basis": "regular", "prev_close": 498.0}}

    p = qs.build_payload(["SPY"], fetcher=fake, now_ms=1234)
    assert p == {"ts": 1234, "quotes": {"SPY": {"price": 500.0, "ts": None, "source": "yahoo",
                                                 "basis": "regular", "prevClose": 498.0}}}
    assert calls["syms"] == ["SPY"]
    # empty universe -> no fetch, empty quotes
    assert qs.build_payload([], fetcher=fake, now_ms=9)["quotes"] == {}


def test_cache_ttl_with_fake_clock():
    t = {"v": 1000.0}
    c = qs.QuoteCache(ttl=60, clock=lambda: t["v"])
    c.put("AAPL", {"x": 1})
    assert c.get("AAPL") == {"x": 1}          # fresh
    t["v"] += 30
    assert c.get("AAPL") == {"x": 1}          # still within ttl
    t["v"] += 31
    assert c.get("AAPL") is None              # expired
    assert c.get("MSFT") is None              # miss
