"""Live-data HONESTY + KEY/RIGHTS-SAFETY guards.

The default Polygon/Yahoo plan is ~15-min delayed, but the browser now receives a
mixed-latency snapshot: a current Tencent mainland quote is allowed to be LIVE
from its own exchange timestamp while delayed sources retain the global floor.
The quote source — not the page — owns that latency claim.
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts import build_live_overlay as blo
from scripts import build_live_quotes as blq
from lib import config


_KEY_TOKENS = ("POLYGON_API_KEY", "MASSIVE_API_KEY", "apiKey")


def test_live_config_emits_delay_vars_and_no_key(tmp_path, monkeypatch):
    # a real key in the env must NOT leak into the browser config
    monkeypatch.setenv("POLYGON_API_KEY", "SECRET-do-not-ship-123")
    blo.write_live_config(tmp_path)
    js = (tmp_path / "live_config.js").read_text()
    assert "window.LIVE_DELAYED_MIN=" in js
    assert "window.LIVE_FEED_LABEL=" in js
    assert "window.LIVE_ENABLED=" in js
    assert "SECRET-do-not-ship-123" not in js
    for tok in _KEY_TOKENS:
        assert tok not in js


def test_config_live_block_keeps_delayed_default_for_delayed_sources():
    """The global config remains the conservative floor for Polygon/Yahoo."""
    live = config.load().get("live") or {}
    assert int(live.get("delayed_min", 0)) >= 15
    assert (live.get("feed_label") or "").strip()


def test_quotes_snapshot_meta_is_honestly_delayed(tmp_path, monkeypatch):
    monkeypatch.setenv("POLYGON_API_KEY", "SECRET-do-not-ship-123")
    # Snapshot-level meta stays conservative; live.js resolves the actual floor per quote source.
    snap = blq.build(tmp_path, offline=True, cap=20)
    expect = int((config.load().get("live") or {}).get("delayed_min", 0))
    assert snap["meta"]["delayed_min"] == expect
    assert snap["meta"]["realtime"] is (expect == 0)
    assert "feed" in snap["meta"]
    blob = json.dumps(snap)
    assert "SECRET-do-not-ship-123" not in blob
    for tok in _KEY_TOKENS:
        assert tok not in blob


def test_to_worker_quotes_passes_through_per_quote_delay():
    raw = {"AAPL": {"price": 200.0, "quote_ts": "2026-06-21T14:50:00+00:00",
                    "source": "polygon", "price_basis": "trade",
                    "prev_close": 198.0, "currency": "USD", "delay_min": 15.0}}
    out = blq.to_worker_quotes(raw)
    assert out["AAPL"]["delayMin"] == 15.0
    assert out["AAPL"]["source"] == "polygon"


def test_browser_resolves_vendor_delay_per_quote_source():
    """Regression for the China-board 15-minute bug: no feed-wide age clamp."""
    js = Path("templates/live.js").read_text()
    assert "function sourceDelayFloor(q)" in js
    assert 'src === "tencent"' in js
    assert "r.delayFloor = sourceDelayFloor(q);" in js
    assert "r.ageMin = Math.max(r.delayFloor, measuredAge, clockAge);" in js
    assert 'state === "delayed" ? ("≥" + delayFloor + "-min delayed")' in js
    # The old unconditional clamp is exactly what made a current China quote look 15m old.
    assert "r.ageMin = Math.max(DELAYED_MIN, Math.max(0" not in js


def test_customer_quote_router_does_not_activate_tushare_without_commercial_grant():
    """The recorded Tushare token/entitlement is not a customer-display license."""
    source = Path("engine/live_quotes.py").read_text().lower()
    assert "tushare" not in source
    assert "qt.gtimg.cn" in source


def test_served_live_js_matches_template_exactly():
    assert Path("site/live.js").read_bytes() == Path("templates/live.js").read_bytes()
