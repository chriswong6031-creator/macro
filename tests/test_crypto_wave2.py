from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader

from collectors.crypto_misc import CryptoUniverseAdapter
from engine.crypto_market_state import build_market_state
from engine.crypto_universe import breadth_read, load_universe
from scripts import build_crypto, build_vector

ROOT = Path(__file__).resolve().parent.parent


def test_crypto_template_has_exact_governed_shelves():
    text = (ROOT / "templates" / "crypto.html.j2").read_text(encoding="utf-8")
    shelves = re.findall(r'data-shelf="([^"]+)"', text)
    assert shelves == [f"H{i}" for i in range(1, 9)]
    assert "plotly" not in text.lower()


def test_crypto_build_is_lightweight_and_live_wired(tmp_path):
    output = build_crypto.build(tmp_path / "site")
    html = output.read_text(encoding="utf-8")
    assert output.stat().st_size < 200 * 1024
    assert re.findall(r'data-shelf="([^"]+)"', html) == [f"H{i}" for i in range(1, 9)]
    assert html.count('class="market-row tone-') >= 20
    assert 'data-sym="BTC-USD"' in html
    assert 'data-sym="ETH-USD"' in html
    assert "CoinGecko primary" in html
    assert "CoinPaprika" in html
    assert "plotly" not in html.lower()


def test_universe_reads_ranked_daily_accrual(tmp_path):
    dates = pd.date_range("2026-06-01", periods=31, freq="D")
    for rank, symbol in ((2, "ETH"), (1, "BTC")):
        frame = pd.DataFrame(
            {
                "source": ["CoinGecko"] * len(dates),
                "coin_id": [symbol.lower()] * len(dates),
                "symbol": [symbol] * len(dates),
                "name": [symbol.title()] * len(dates),
                "market_cap_rank": [rank] * len(dates),
                "current_price": list(range(100, 131)),
                "market_cap": [1_000_000] * len(dates),
                "total_volume": [100_000] * len(dates),
                "change_24h_pct": [1.0] * len(dates),
                "change_7d_pct": [4.0] * len(dates),
                "change_30d_pct": [12.0] * len(dates),
            },
            index=dates,
        )
        frame.to_parquet(tmp_path / f"market_{symbol.lower()}.parquet")
    rows = load_universe(50, root=tmp_path)
    assert [row["symbol"] for row in rows] == ["BTC", "ETH"]
    assert rows[0]["history_days"] == 31
    assert rows[0]["history_chip"] == "31D"
    assert rows[0]["state"] == "Firm"
    assert breadth_read(rows)["available"] is False


def test_universe_collector_normalizes_coingecko(monkeypatch):
    adapter = CryptoUniverseAdapter()
    payload = [
        {
            "id": f"coin-{rank}",
            "symbol": f"c{rank}",
            "name": f"Coin {rank}",
            "market_cap_rank": rank,
            "current_price": rank * 10,
            "market_cap": rank * 1_000_000,
            "fully_diluted_valuation": rank * 1_100_000,
            "total_volume": rank * 100_000,
            "high_24h": rank * 11,
            "low_24h": rank * 9,
            "price_change_percentage_24h": 1.5,
            "price_change_percentage_7d_in_currency": 3.0,
            "price_change_percentage_30d_in_currency": 7.0,
            "price_change_percentage_200d_in_currency": 20.0,
            "price_change_percentage_1y_in_currency": 30.0,
            "ath_change_percentage": -10.0,
            "last_updated": "2026-07-29T00:00:00Z",
        }
        for rank in range(1, 21)
    ]

    class Response:
        def json(self):
            return payload

    monkeypatch.setattr(adapter, "http_get", lambda *args, **kwargs: Response())
    frames = adapter.fetch()
    assert len(frames) == 20
    btc = frames["market_c1"].iloc[0]
    assert btc["source"] == "CoinGecko"
    assert btc["symbol"] == "C1"
    assert btc["market_cap_rank"] == 1


def test_market_state_derives_class_cap_without_new_authority():
    dates = pd.date_range("2025-12-01", periods=220, freq="D")
    frames = {
        ("coinmetrics", "mcap_usd"): pd.DataFrame(
            {"mcap_usd": pd.Series(range(900, 1120), index=dates) * 1e9}
        ),
        ("bgeo", "btc_dominance"): pd.DataFrame(
            {"btc_dominance": pd.Series(range(220), index=dates) * 0.02 + 50}
        ),
        ("sentiment_crypto", "fear_greed"): pd.DataFrame(
            {"fear_greed": [42] * 220}, index=dates
        ),
        ("defillama", "stablecoins"): pd.DataFrame(
            {"stablecoin_mcap_usd": pd.Series(range(220), index=dates) * 1e8 + 200e9}
        ),
        ("coinbase", "btc_daily"): pd.DataFrame(
            {
                "close": pd.Series(range(220), index=dates) * 100 + 50_000,
                "volume": pd.Series(range(220), index=dates) * 1e6 + 1e9,
            }
        ),
        ("yahoo", "ETH-USD"): pd.DataFrame(
            {"close": pd.Series(range(220), index=dates) * 10 + 2_000}
        ),
        ("farside", "etf_flows"): pd.DataFrame({"total": [30] * 220}, index=dates),
        ("vector", "signals"): pd.DataFrame(
            {
                "funding_annual_pct": [4.0] * 220,
                "oi_mcap_ratio": [0.02] * 220,
                "oi_mcap_pctile": [45.0] * 220,
                "dvol": [48.0] * 220,
                "dvol_pctile": [55.0] * 220,
            },
            index=dates,
        ),
    }

    state = build_market_state(lambda group, name: frames.get((group, name)))
    expected = frames[("coinmetrics", "mcap_usd")]["mcap_usd"].iloc[-1] / (
        frames[("bgeo", "btc_dominance")]["btc_dominance"].iloc[-1] / 100
    )
    assert state["total_market_cap"] == expected
    assert state["flows"]["etf"]["value"] == 150
    assert state["heat"]["funding"]["state"] == "Balanced"
    assert state["as_of"] == str(dates[-1].date())


def test_allocation_and_strategy_legacy_urls_are_durable_redirects():
    allocation = (ROOT / "site" / "vector_allocation.html").read_text(
        encoding="utf-8"
    )
    strategy = (ROOT / "site" / "btc_strategy.html").read_text(encoding="utf-8")
    assert 'href="https://www.mastermind-x.com/crypto.html"' in allocation
    assert "crypto.html#allocation" in allocation
    assert 'http-equiv="refresh"' in allocation
    assert '<nav class="site-nav">' not in allocation
    assert 'href="https://www.mastermind-x.com/vector.html"' in strategy
    assert "vector.html#strategy-track-record" in strategy
    template = (ROOT / "templates" / "vector_allocation.html.j2").read_text(
        encoding="utf-8"
    )
    assert '"_seo_head.html.j2"' in template
    assert '"crypto" ~ ".html"' in template
    assert "crypto.html#allocation" in template

    vector_builder = (ROOT / "scripts" / "build_vector.py").read_text(encoding="utf-8")
    assert re.search(r"^\s+build_allocation_page\(", vector_builder, re.MULTILINE)


def test_vector_builder_regenerates_allocation_redirect(tmp_path):
    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")))
    build_vector.build_allocation_page(env, tmp_path, None, {}, {}, {})
    allocation = (tmp_path / "vector_allocation.html").read_text(encoding="utf-8")
    assert 'href="https://www.mastermind-x.com/crypto.html"' in allocation
    assert "crypto.html#allocation" in allocation
    assert "Bitcoin Vector — Allocation Strategy" not in allocation


def test_crypto_is_first_class_in_navigation_workflows_and_products():
    nav = (ROOT / "templates" / "_navlinks.html.j2").read_text(encoding="utf-8")
    nav_market = (ROOT / "templates" / "nav_market.js").read_text(encoding="utf-8")
    assert "{{ t('Crypto', '加密') }}" not in nav
    assert "Crypto Intelligence" in nav_market
    assert "Bitcoin Vector" in nav_market
    assert "Market state, flows, leverage and asset lanes" in nav_market
    assert "vector_allocation.html" not in nav
    assert "btc_strategy.html" not in nav

    daily = (ROOT / ".github" / "workflows" / "daily.yml").read_text(encoding="utf-8")
    render = (ROOT / ".github" / "workflows" / "render.yml").read_text(encoding="utf-8")
    assert "python -m scripts.build_crypto" in daily
    assert "scripts.build_crypto" in render
    assert "hub; crypto" in render

    engine_render = (
        ROOT / ".github" / "workflows" / "engine-render.yml"
    ).read_text(encoding="utf-8")
    assert "crypto() {" in engine_render
    assert "scripts.build_crypto" in engine_render
    case_body = engine_render.split('case "$SCOPE" in', 1)[1].split("esac", 1)[0]
    assert len(re.findall(r"\bhub\s*;\s*crypto\b", case_body)) == 8
    assert not re.search(r"\bhub\s*;(?!\s*crypto\b)", case_body)

    product = ROOT / "content" / "seo" / "products" / "crypto-intelligence.md"
    assert product.exists()
    assert "/crypto.html" in product.read_text(encoding="utf-8")


def test_committed_universe_has_snapshot_provenance():
    files = sorted((ROOT / "data" / "crypto_universe").glob("market_*.parquet"))
    assert len(files) >= 20
    frame = pd.read_parquet(files[0])
    assert {"source", "symbol", "market_cap_rank", "current_price"} <= set(frame.columns)
    assert frame.iloc[-1]["source"] in {"CoinGecko", "CoinPaprika"}
