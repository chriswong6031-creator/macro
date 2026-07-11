"""The intraday overlay build (scripts.build_live_overlay) + Mastermind emit v2.

The offline path is load-bearing: it must always emit a VALID overlay (NaN-safe,
every leg stale, falling back to baseline) with no network — now including the
market-context + per-region session blocks. Also pins the Mastermind emit v2
(alloc weights + asof in JSON).
"""
from __future__ import annotations

import json

from scripts import build_live_overlay as blo
from scripts import build_masterminds as bmm


def test_universe_includes_gtaa_assets():
    uni = blo.build_universe()
    assert isinstance(uni, list) and uni
    assert "SPY" in uni and "GC=F" in uni
    assert len(uni) <= int((blo.config.load().get("live") or {}).get("max_universe", 150))


def test_offline_build_emits_valid_v2_overlay():
    res = blo.build(offline=True, limit=8)
    assert res["status"] == "ok"
    site = blo.config.ROOT / blo.config.load()["storage"]["site_dir"]
    raw = (site / "live" / "overlay.json").read_text()
    assert "NaN" not in raw                         # allow_nan=False -> never invalid JSON
    out = json.loads(raw)
    assert out["schema"] == "live.overlay.v2"
    assert out["n_quotes"] == 0 and out["n"] >= 1
    for rec in out["tickers"].values():
        assert rec["stale"] is True and "tech" in rec and "region" in rec
    # new blocks present — all 9 globe regions (W2b: jp/kr/tw/gb/eu added)
    assert set(out["sessions"]) == {"us", "cn", "hk", "ca", "jp", "kr", "tw", "gb", "eu"}
    assert "VIX" in out["market"] and "band" in out["market"]["VIX"]
    assert (site / "live_config.js").exists()


def test_offline_allocations_are_stale_marked():
    blo.build(offline=True, limit=4)
    site = blo.config.ROOT / blo.config.load()["storage"]["site_dir"]
    out = json.loads((site / "live" / "overlay.json").read_text())
    for region in out.get("allocations", {}).values():
        for card in region["cards"]:
            for leg in card["alloc"]:
                assert leg["stale"] is True and leg["live_price"] is None


def test_market_session_block_shape():
    blo.build(offline=True, limit=2)
    site = blo.config.ROOT / blo.config.load()["storage"]["site_dir"]
    out = json.loads((site / "live" / "overlay.json").read_text())
    us = out["sessions"]["us"]
    assert set(us) == {"region", "open", "local_time"} and isinstance(us["open"], bool)


def test_live_config_js_carries_worker_url():
    site = blo.config.ROOT / blo.config.load()["storage"]["site_dir"]
    blo.write_live_config(site)
    js = (site / "live_config.js").read_text()
    assert "LIVE_QUOTES_URL" in js and "LIVE_POLL_SEC" in js


def test_resolve_worker_url_env_override_and_https_guard(monkeypatch):
    # env var overrides config + strips a trailing slash (turn-on via a GitHub repo variable)
    monkeypatch.setenv("LIVE_QUOTES_WORKER_URL", "https://q.example.workers.dev/")
    assert blo.resolve_worker_url() == "https://q.example.workers.dev"
    # a non-https value is rejected so a malformed variable can't break live.js
    monkeypatch.setenv("LIVE_QUOTES_WORKER_URL", "http://insecure.dev")
    assert blo.resolve_worker_url() == ""
    # empty env -> falls back to config.yml (default "")
    monkeypatch.delenv("LIVE_QUOTES_WORKER_URL", raising=False)
    assert blo.resolve_worker_url() == str((blo.config.load().get("live") or {}).get("quotes_worker_url", "") or "")


def test_masterminds_snap_v2_carries_alloc_and_asof():
    if not hasattr(bmm, "_snap"):
        import pytest
        pytest.skip("build_masterminds._snap (v2 alloc emit) is a main-only refactor not "
                    "yet on feat/signal-engine-buy-filter; auto-reactivates after merge")
    cards = [{"key": "mm_moderate", "name_en": "MM Moderate", "cagr": 11.5,
              "sharpe": 1.1, "maxdd": -24.0}]
    ress = [{"asof": "2026-06-20", "gross_now": 1.4,
             "alloc": [{"asset": "SPY", "weight": 40.0},
                       {"asset": "GC=F", "weight": 20.0}]}]
    snap = bmm._snap(cards, ress, "2026-06-21 08:20 UTC")
    assert snap["schema"] == "masterminds.latest.v2"
    assert snap["asof"] == "2026-06-20" and snap["stale_after_min"] == 1440
    c0 = snap["cards"][0]
    assert c0["alloc"][0]["asset"] == "SPY" and c0["gross_now"] == 1.4
