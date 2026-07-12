"""_hk_index_turn (scripts.build_allocation) — the IHM ^HSI washout-turn context row.

Fail-open is the contract: the builder runs on boxes with data/index_momentum/latest.json
AND in worktrees/CI where it is absent — every shortfall must yield None (no row), never
an exception. Pure logic; no network.
"""
from __future__ import annotations

import json

import pandas as pd

from lib import config
from scripts.build_allocation import _hk_index_turn


def _write_artifact(tmp_path, data_as_of=None, events=None):
    d = tmp_path / "index_momentum"
    d.mkdir(parents=True, exist_ok=True)
    now = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    payload = {
        "organ": "index_momentum.v1",
        "data_as_of": str((data_as_of if data_as_of is not None else now).date()),
        "indices": {"^HSI": {"id": "^HSI", "grids": {"1D": {
            "recent_events": events or [],
        }}}},
    }
    (d / "latest.json").write_text(json.dumps(payload))
    return now


def _event(date, tag="washout_turn", direction="bull", us_confirm=True):
    return {"index": "^HSI", "grid": "1D", "date": str(date.date()),
            "direction": direction, "depth_at_cross": -8.6, "depth_pctile": 4.2,
            "quality_tag": tag, "us_confirm": us_confirm,
            "global_washout_turn": False}


def test_wrong_region_none(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    now = _write_artifact(tmp_path)
    _write_artifact(tmp_path, events=[_event(now - pd.Timedelta(days=3))])
    assert _hk_index_turn("us") is None
    assert _hk_index_turn("china") is None


def test_missing_artifact_none(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)  # nothing written
    assert _hk_index_turn("hk") is None


def test_malformed_artifact_none(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    d = tmp_path / "index_momentum"
    d.mkdir(parents=True)
    (d / "latest.json").write_text("{not json")
    assert _hk_index_turn("hk") is None


def test_stale_artifact_none(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    now = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    _write_artifact(tmp_path, data_as_of=now - pd.Timedelta(days=9),
                    events=[_event(now - pd.Timedelta(days=3))])
    assert _hk_index_turn("hk") is None  # frozen-lane fence (>5 calendar days)


def test_old_event_none(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    now = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    _write_artifact(tmp_path, events=[_event(now - pd.Timedelta(days=30))])
    assert _hk_index_turn("hk") is None  # outside ~15-session window


def test_trap_zone_filtered(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    now = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    _write_artifact(tmp_path, events=[
        _event(now - pd.Timedelta(days=2), tag="trap_zone"),
        _event(now - pd.Timedelta(days=4), tag="ordinary"),
        _event(now - pd.Timedelta(days=6), tag="washout_turn", direction="bear"),
    ])
    assert _hk_index_turn("hk") is None  # only bull washout_turn qualifies


def test_fresh_washout_turn_fires(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    now = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    ev_date = now - pd.Timedelta(days=5)
    _write_artifact(tmp_path, events=[
        _event(now - pd.Timedelta(days=12), us_confirm=False),  # older turn
        _event(ev_date, us_confirm=True),
    ])
    out = _hk_index_turn("hk")
    assert out is not None
    assert out["date"] == str(ev_date.date())  # most recent qualifying event wins
    assert out["us_confirm"] is True
    assert out["date_en"] and out["date_zh"].endswith("日")


def test_unconfirmed_variant(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    now = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    _write_artifact(tmp_path, events=[_event(now - pd.Timedelta(days=3), us_confirm=False)])
    out = _hk_index_turn("hk")
    assert out is not None and out["us_confirm"] is False
