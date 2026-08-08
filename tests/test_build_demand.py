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
    # ...and the Alert Center write, for the same reason. `bd.build()` calls
    # `engine.demand_alerts.rebuild`, which appends to data/demand_chain/alerts.jsonl and
    # rewrites alerts_state.json in the REAL tree — it takes no root/out parameter, so
    # unlike write_page it cannot be pointed elsewhere. MM_DATA_GUARD forced
    # `unrun-builders-stores` to exit 1 on a step reporting "906 passed".
    #
    # It reds INTERMITTENTLY, which is what made it hard to place: rebuild() diffs today's
    # reads against the committed state and only writes when a variant flips, so the job is
    # green on every run where the recomputed state happens to match what is checked in.
    # The observed flip was one ticker (GEV -> DHR in alerts_state.json, one appended
    # alerts.jsonl row). An intermittent tree-dirty is still a hard red, not a flake.
    #
    # Neutralised rather than redirected: this test asserts the PAGE skeleton, and the
    # alert center has its own suite (tests/test_demand_alerts.py). Returning [] matches
    # rebuild's own documented seed-run result, so `build()` takes the same branch it does
    # on a first run.
    from engine import demand_alerts
    monkeypatch.setattr(demand_alerts, "rebuild", lambda reads, as_of=None: [])

    html = bd.build()
    assert "Demand Desk" in html
    assert 'class="cards"' in html and "Ahead of consensus" in html
    assert "demand.html" in html                # nav link present (self-referential)
