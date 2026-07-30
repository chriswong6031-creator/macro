from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from collectors.coinbase import CoinbaseAdapter
from engine import btc_dat, btc_options, eth_state, master_brain
from scripts import build_crypto

ROOT = Path(__file__).resolve().parent.parent


def _bars(start: float, periods: int = 260, step: float = 1.0) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=periods, freq="D")
    close = pd.Series([start + i * step for i in range(periods)], index=idx)
    return pd.DataFrame(
        {
            "open": close * 0.99,
            "high": close * 1.02,
            "low": close * 0.98,
            "close": close,
            "volume": 1_000_000,
        },
        index=idx,
    )


def test_eth_sol_states_are_display_only_and_never_allocate():
    btc = _bars(50_000, step=30)
    eth = _bars(2_000, step=4)
    state = eth_state.build_asset_state("ETH", eth, btc, source="coinbase")
    assert state["display_only"] is True
    assert state["authority"] == "states_only"
    assert state["allocation"] is None
    assert state["recommendation"] is None
    assert state["coverage"]["available"] is True
    assert state["trend"]["state"] in {"Advancing", "Range", "Fading"}
    assert state["risk"]["state"] in {"Calm", "Watch", "Stressed"}
    assert "observations" in state["coverage"]["note_en"]

    source = (ROOT / "engine" / "eth_state.py").read_text(encoding="utf-8")
    assert "btc_signals.allocation" not in source
    assert "from engine import btc_signals" not in source


def test_asset_state_plain_word_null_coverage():
    state = eth_state.build_asset_state(
        "SOL", _bars(100, periods=12), _bars(50_000, periods=12), source="coinbase"
    )
    assert state["trend"]["state"] == "Building history"
    assert state["risk"]["state"] == "Unavailable"
    assert state["coverage"]["available"] is False
    assert "Building daily history" in state["coverage"]["note_en"]
    assert "积累" in state["coverage"]["note_zh"]


def test_coinbase_fetch_requests_eth_and_sol_daily(monkeypatch):
    adapter = CoinbaseAdapter()
    calls: list[tuple[str, str, int, str, bool]] = []

    def fake(series, product, granularity, earliest, full_history):
        calls.append((series, product, granularity, earliest, full_history))
        return _bars(100, periods=2)

    monkeypatch.setattr(adapter, "_candles", fake)
    out = adapter.fetch(full_history=False)
    assert set(out) == {"btc_daily", "btc_hourly", "eth_daily", "sol_daily"}
    assert ("eth_daily", "ETH-USD", 86400, adapter.cfg["eth_earliest"], False) in calls
    assert ("sol_daily", "SOL-USD", 86400, adapter.cfg["sol_earliest"], False) in calls


def test_coinbase_normalizes_each_daily_series():
    adapter = CoinbaseAdapter()
    index = pd.to_datetime(["2026-07-29T08:00:00Z", "2026-07-30T08:00:00Z"])
    frame = _bars(100, periods=2).set_axis(index)
    normalized = adapter.validate("eth_daily", frame)
    assert all(ts.hour == 0 for ts in normalized.index)


def test_btc_options_contract_publishes_full_deribit_receipt():
    idx = pd.to_datetime(["2026-07-28", "2026-07-29"])
    structure = pd.DataFrame(
        {
            "underlying": [110_000, 112_000],
            "atm_iv_7d": [42, 43],
            "atm_iv_30d": [45, 46],
            "atm_iv_90d": [49, 50],
            "atm_iv_180d": [52, 53],
            "term_slope_30_90": [4, 4],
            "rr_25d": [-3, -2],
            "skew_25d": [0.06, 0.05],
            "skew_term": [0.01, 0.02],
            "put_call_oi_ratio": [0.8, 0.9],
            "put_call_vol_ratio": [0.7, 0.75],
            "max_pain": [108_000, 110_000],
            "max_pain_expiry_d": [8, 7],
            "total_oi_btc": [200_000, 210_000],
            "gex_per_1pct_usd": [1e9, 1.2e9],
            "gamma_concentration_usd": [2e9, 2.2e9],
            "gamma_flip": [109_000, 111_000],
            "dist_to_flip_pct": [0.9, 0.89],
            "gamma_regime": ["long", "long"],
            "basis_ann": [8.2, 8.5],
            "basis_front_ann": [7.5, 7.8],
            "basis_slope": [1.1, 1.2],
        },
        index=idx,
    )
    dvol = pd.DataFrame({"dvol_close": [48, 49]}, index=idx)
    frames = {
        ("deribit", "options_structure"): structure,
        ("deribit", "dvol"): dvol,
    }
    contract = btc_options.build_contract(lambda g, n: frames.get((g, n)))
    assert contract["schema"] == "crypto.btc_options/v1"
    assert contract["display_only"] is True
    assert contract["volatility"]["atm_iv_30d"] == 46
    assert contract["gamma"]["flip"] == 111_000
    assert contract["gamma"]["distance_pct"] == 0.89
    assert contract["positioning"]["max_pain"] == 110_000
    assert contract["basis"]["annualized_pct"] == 8.5


def test_btc_options_null_contract_is_plain_and_render_safe():
    contract = btc_options.build_contract(lambda _group, _name: None)
    assert contract["coverage"]["available"] is False
    assert contract["volatility"]["atm_iv_30d"] is None
    assert contract["positioning"]["put_call_oi_ratio"] is None
    assert contract["gamma"]["flip"] is None
    assert contract["basis"]["annualized_pct"] is None
    assert "awaiting" in contract["coverage"]["note_en"]


def test_crypto_template_renders_null_options_contract(monkeypatch, tmp_path):
    empty = btc_options.build_contract(lambda _group, _name: None)
    monkeypatch.setattr(build_crypto, "build_btc_options", lambda: empty)
    output = build_crypto.build(tmp_path / "site")
    html = output.read_text(encoding="utf-8")
    assert "Deribit options snapshot is awaiting its next collection." in html


def test_build_publishes_wave3_contracts_and_three_asset_lanes(tmp_path):
    output = build_crypto.build(tmp_path / "site")
    html = output.read_text(encoding="utf-8")
    assert 'data-sym="ETH-USD"' in html
    assert 'data-sym="SOL-USD"' in html
    assert "Bitcoin derivatives desk" in html
    assert "Distance to flip" in html
    assert "&lt;br&gt;" not in html
    assert 'data-shelf="H6" id="asset-lanes"' in html
    for name in ("btc_options.json", "crypto_asset_states.json", "crypto_class_state.json"):
        path = tmp_path / "site" / name
        assert path.exists()
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["display_only"] is True


def test_btc_brain_reads_class_state_as_narration_only(tmp_path):
    (tmp_path / "site").mkdir()
    payload = {
        "schema": "crypto.class_state/v1",
        "tier": "display",
        "display_only": True,
        "as_of": "2026-07-29",
        "market": {"total_state": "Rising"},
        "flows": {"stablecoins": "Firm"},
        "heat": {"funding": "Balanced"},
        "assets": {"ETH": {"trend": "Advancing"}},
        "forbidden_score": 99,
    }
    (tmp_path / "site" / "crypto_class_state.json").write_text(json.dumps(payload))
    state = master_brain.gather_btc_state(tmp_path)
    assert state["crypto_class"]["display_only"] is True
    assert state["crypto_class"]["market"]["total_state"] == "Rising"
    assert "forbidden_score" not in state["crypto_class"]


def test_wave3_data_quality_decisions_are_explicit():
    cfg = (ROOT / "config.yml").read_text(encoding="utf-8")
    assert "enabled: false" in cfg[cfg.index("  btc_dat:"):cfg.index("  btc_leverage_cascade:")]
    vector = (ROOT / "templates" / "vector.html.j2").read_text(encoding="utf-8")
    assert "Reserve Risk and VDD use backfill vintages only" in vector
    assert "No daily scrape or quota expansion is used" in vector


def test_runtime_navigation_names_the_crypto_products_honestly():
    runtime = (ROOT / "templates" / "nav_market.js").read_text(encoding="utf-8")
    assert "'Crypto Intelligence', 'Market state, flows, leverage and asset lanes'" in runtime
    assert "'Bitcoin Vector', 'Bitcoin state, risk and cycle evidence'" in runtime
    assert "'Strategy Track Record', 'Cycle and allocation evidence'" in runtime
    assert (ROOT / "site" / "nav_market.js").read_bytes() == (
        ROOT / "templates" / "nav_market.js"
    ).read_bytes()


def test_vector_derivatives_formats_implied_volatility_for_humans():
    template = (ROOT / "templates" / "vector.html.j2").read_text(encoding="utf-8")
    assert '"%.1f"|format(btc_options.volatility.atm_iv_30d)' in template
    rendered = (ROOT / "site" / "vector.html").read_text(encoding="utf-8")
    match = re.search(
        r"Implied volatility.*?<div class=\"v\">([^<]+)</div>",
        rendered,
        re.DOTALL,
    )
    assert match is not None
    assert re.fullmatch(r"\d+\.\d|—", match.group(1))


def test_retired_dat_module_honours_nested_vector_config(monkeypatch):
    monkeypatch.setattr(
        btc_dat.config,
        "load",
        lambda: {"vector": {"btc_dat": {"enabled": False}}},
    )
    assert btc_dat.compute() == {
        "ok": False,
        "reason": "btc_dat disabled in config",
    }


def test_wave3_synapse_contracts_are_display_only():
    registry = (ROOT / "config" / "synapse.yml").read_text(encoding="utf-8")
    for key in ("btc-options:", "crypto-asset-states:", "crypto-class-state:"):
        assert key in registry
    assert "scored_path_surfaces: []" in registry
