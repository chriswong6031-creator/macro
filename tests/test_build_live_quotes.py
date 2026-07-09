"""Live-quotes SNAPSHOT builder (scripts.build_live_quotes).

The snapshot is the keyless, no-Worker live path: a GitHub Action runs this and
force-pushes the JSON to the `live-data` branch; the browser live.js fetches it.
These pin the parts that DON'T need a socket: the universe (CORE symbols always
present, junk rejected, de-duped), the engine->Worker-contract mapping live.js
consumes (epoch-ms ts, change%, prevClose), the data-sym site scrape, and the
load-bearing fail-safe (offline = a valid, empty snapshot).
"""
from __future__ import annotations

from engine import live_quotes as lq
from scripts import build_live_quotes as blq


def test_yahoo_batch_stays_under_the_spark_cliff():
    # Yahoo spark HTTP-400s a symbols list >20 — the old batch of 50 silently
    # dropped every intl/equity quote. Guard the fix from regressing.
    assert lq._YAHOO_BATCH <= 20


def test_core_index_and_futures_symbols_always_in_universe(tmp_path):
    uni = blq.build_universe(tmp_path)                 # empty site dir -> CORE only
    for sym in ("^GSPC", "^IXIC", "^DJI", "^VIX", "ES=F", "NQ=F", "^HSI",
                "000001.SS", "^N225", "GC=F", "EURUSD=X"):
        assert sym in uni, sym


def test_btc_is_in_core_and_routes_to_yahoo(tmp_path):
    # BTC trades 24/7, so it's kept in CORE (always fetched) and the Bitcoin Vector
    # header links data-sym="BTC-USD". A crypto pair must route to Yahoo, never Polygon
    # (crypto isn't entitled on the stocks plan) — pin both.
    assert "BTC-USD" in blq.build_universe(tmp_path)
    assert lq.is_us_symbol("BTC-USD") is False


def test_symbols_override_builds_exact_universe(tmp_path):
    # The hourly btc-live Action passes --symbols BTC-USD to refresh ONLY the crypto
    # leg — the snapshot must contain exactly that, not the whole CORE+scrape universe.
    (tmp_path / "big.html").write_text('<span data-sym="AAPL"><span data-sym="NVDA">')
    snap = blq.build(tmp_path, offline=True, symbols=["BTC-USD"])
    assert snap["meta"]["requested"] == 1          # exactly one symbol, CORE/scrape bypassed
    # offline -> no resolved quotes, but the requested universe was BTC-only
    assert "AAPL" not in snap["quotes"] and "NVDA" not in snap["quotes"]


def test_validate_symbols_dedups_uppercases_and_rejects_junk():
    got = blq._validate_symbols(["btc-usd", "BTC-USD", " eth-usd ", "';DROP", ""])
    assert got == ["BTC-USD", "ETH-USD"]           # upper, de-duped, junk + empty dropped


def test_universe_rejects_junk_and_dedups(tmp_path):
    (tmp_path / "a.html").write_text(
        'x <span class="nb-px" data-sym="AAPL"> '
        'y <span data-sym="aapl"> '              # case-dupe of AAPL after upper
        'z <span data-sym="0700.HK"> '
        'bad <span data-sym="\';DROP TABLE"> '   # junk -> charset-rejected
        'bad2 <span data-sym="<script>">')
    uni = blq.build_universe(tmp_path)
    assert "AAPL" in uni and "0700.HK" in uni
    assert uni.count("AAPL") == 1                 # de-duped (incl. lowercase form)
    assert all(blq._SYMBOL_RE.match(s) for s in uni)   # nothing malformed survives


def test_scrape_site_symbols_extracts_only_valid(tmp_path):
    (tmp_path / "p1.html").write_text('<span data-sym="NVDA"><span data-sym="600519.SS">')
    (tmp_path / "p2.html").write_text('<span data-sym="ES=F"><span data-sym="bad sym!">')
    got = blq.scrape_site_symbols(tmp_path)
    assert set(got) == {"NVDA", "600519.SS", "ES=F"}


def test_to_worker_quotes_maps_engine_dict_to_contract():
    raw = {"AAPL": {"price": 212.5, "quote_ts": "2026-06-23T14:00:00+00:00",
                    "source": "polygon", "price_basis": "trade",
                    "prev_close": 210.0, "currency": "USD", "delay_min": 1.0}}
    out = blq.to_worker_quotes(raw)["AAPL"]
    assert out["price"] == 212.5
    assert out["source"] == "polygon" and out["basis"] == "trade"
    assert out["prevClose"] == 210.0
    assert out["changePct"] == round((212.5 / 210.0 - 1) * 100, 2)
    assert isinstance(out["ts"], int) and out["ts"] > 0     # epoch MILLIseconds
    from datetime import datetime
    assert out["ts"] == int(datetime.fromisoformat("2026-06-23T14:00:00+00:00").timestamp() * 1000)


def test_to_worker_quotes_handles_missing_prevclose_and_price():
    raw = {
        "IDX": {"price": 7400.0, "quote_ts": None, "source": "yahoo",
                "price_basis": "regular", "prev_close": None, "currency": None},
        "DEAD": {"price": None, "source": "yahoo"},        # priceless -> dropped
    }
    out = blq.to_worker_quotes(raw)
    assert "DEAD" not in out
    assert out["IDX"]["prevClose"] is None
    assert out["IDX"]["changePct"] is None
    assert out["IDX"]["ts"] is None                         # missing quote_ts -> None


def test_build_offline_is_a_valid_empty_snapshot(tmp_path):
    snap = blq.build(tmp_path, offline=True)
    assert snap["source"] == "snapshot"
    assert snap["quotes"] == {}
    assert snap["meta"]["offline"] is True
    assert snap["meta"]["requested"] > 0                    # universe still assembled
    assert isinstance(snap["ts"], int) and snap["ts"] > 0


# ── Cap-raise regression guards (2026-07-09) ─────────────────────────────────
# Problem: build_universe capped at 800 (default), truncating alphabetically.
# At cap=800 only ~249/680 basket members survived. Cap raised to 2200 to cover
# the full ~1942-symbol scraped universe (CORE 39 + site data-sym ~1918) with
# headroom. Measured: 1938/1942 resolved in 53 s on Yahoo path (< 8-min timeout).
# File size at full universe: ~275 KB (< 500 KB browser-fetch budget).

def test_default_cap_is_2200():
    """Cap default must be at least 2200 to cover the full scraped universe."""
    import inspect
    sig = inspect.signature(blq.build_universe)
    assert sig.parameters["cap"].default >= 2200, (
        f"build_universe default cap is {sig.parameters['cap'].default} — "
        "must be >= 2200 to cover the full ~1942-symbol scraped universe"
    )


def test_build_default_cap_is_2200():
    """build() inherits the raised cap — pin it so a build() caller without
    an explicit cap= argument still gets the full universe."""
    import inspect
    sig = inspect.signature(blq.build)
    assert sig.parameters["cap"].default >= 2200


def test_cap_high_enough_for_full_scraped_universe(tmp_path):
    """Universe of ~1942 symbols (CORE + site data-sym) must fit under the cap
    without truncation, so no basket member is silently dropped."""
    # Simulate the full-size scraped universe: write a page with 1960 fake symbols
    # (A0000..A1959 — all pass the charset) to verify the cap doesn't truncate them.
    syms = [f"A{i:04d}" for i in range(1960)]        # 1960 valid-looking symbols
    html_lines = " ".join(f'<span data-sym="{s}">' for s in syms)
    (tmp_path / "big.html").write_text(html_lines)
    uni = blq.build_universe(tmp_path)                # uses default cap=2200
    # CORE (39) + 1960 scraped = 1999 unique; all must survive under cap=2200
    assert len(uni) >= 1999, (
        f"universe len {len(uni)} — default cap truncated symbols that should survive"
    )
    # Every scraped symbol must be present (no alphabetical truncation)
    uni_set = set(uni)
    missing = [s for s in syms if s not in uni_set]
    assert not missing, f"{len(missing)} scraped symbols truncated: {missing[:5]}..."
