"""Smoke + unit tests for scripts/build_demand.py (the Demand Desk page)."""
from __future__ import annotations

from scripts import build_demand as bd


def test_chain_cards_capex_and_rpo():
    signals = {"ai_datacenter": {"trend": "accelerating", "yoy_pct": 69.0,
                                 "total_latest_bn": 379.0, "fy_latest": 2025,
                                 "n_spenders": 5, "series": [[2024, 224.1], [2025, 379.0]],
                                 "chain_key": "ai_datacenter"}}
    reads = {"NVDA": {"chain_key": "ai_datacenter", "tier": "compute", "leading": True,
                      "fy_latest": 2025, "yoy_pct": 69.0},
             "ORCL": {"chain_key": "own_rpo", "tier": "bookings", "leading": True,
                      "fy_latest": 2025, "yoy_pct": 41.0, "total_latest_bn": 138.0}}
    cards = bd._chain_cards(signals, reads)
    keys = {c["key"] for c in cards}
    assert "ai_datacenter" in keys and "own_rpo" in keys
    rpo_card = next(c for c in cards if c["key"] == "own_rpo")
    assert rpo_card["n"] == 1 and rpo_card["leaders"][0]["t"] == "ORCL"


def test_div_order_complete():
    # every divergence the engine can emit must have a render slot
    assert set(bd._DIV_ORDER) == set(bd._DIV_META)


def test_build_smoke_renders_page(tmp_path, monkeypatch):
    # integration: build against committed repo data; must emit the page skeleton.
    # Redirect the page write to tmp — never the repo's real site/ tree.
    monkeypatch.setattr(
        bd, "write_page", lambda path, html: (tmp_path / path.name).write_text(html)
    )
    html = bd.build()
    assert "Demand Desk" in html
    assert 'class="cards"' in html and "Ahead of consensus" in html
    assert "demand.html" in html                # nav link present (self-referential)
