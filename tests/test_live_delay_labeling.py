"""Live-data HONESTY + KEY-SAFETY guards (Polygon STANDARD = 15-min DELAYED).

Two load-bearing guarantees of the live-data layer:
  1. The feed is labeled DELAYED, never "real-time": the browser config + the
     snapshot/overlay JSON carry delayed_min>0 and realtime=False on the Standard plan.
  2. The vendor API key NEVER reaches a browser-shipped artifact — even when a key IS
     present in the environment, live_config.js and quotes.json must not contain it.
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


def test_config_live_block_is_delayed_not_realtime():
    """The shipped config must declare a non-zero vendor delay (Standard plan)."""
    live = config.load().get("live") or {}
    assert int(live.get("delayed_min", 0)) >= 15
    assert (live.get("feed_label") or "").strip()    # an honest human caption is present


def test_quotes_snapshot_meta_is_honestly_delayed(tmp_path, monkeypatch):
    monkeypatch.setenv("POLYGON_API_KEY", "SECRET-do-not-ship-123")
    # offline -> no network, empty quotes, but the meta still declares the delay honestly
    snap = blq.build(tmp_path, offline=True, cap=20)
    expect = int((config.load().get("live") or {}).get("delayed_min", 0))
    assert snap["meta"]["delayed_min"] == expect
    assert snap["meta"]["realtime"] is (expect == 0)
    assert "feed" in snap["meta"]
    # the serialized snapshot must never carry the key
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
