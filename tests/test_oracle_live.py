"""Hermetic tests for engine.oracle.live — build_oracle_state.

All fixtures are synthetic (no network, no real data reads).
Verifies degrade-never-raise contract and payload structure.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from engine.oracle.live import build_oracle_state, write_oracle_state, SCHEMA


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_data_dir(tmp_path: Path, with_episodes: bool = True, with_panel: bool = True,
                   with_groups: bool = True, with_gauntlet: bool = True) -> Path:
    oracle_dir = tmp_path / "oracle"
    oracle_dir.mkdir(parents=True)

    if with_panel:
        import numpy as np
        idx = pd.MultiIndex.from_tuples(
            [("XLK", "2026-07-01"), ("XLV", "2026-07-01"), ("XLE", "2026-07-01"),
             ("XLK", "2026-06-30"), ("XLV", "2026-06-30")],
            names=["node", "date"],
        )
        panel = pd.DataFrame({
            "rs": [0.05, 0.02, -0.01, 0.03, 0.01],
            "accel": [1.2, 0.8, -0.5, 0.9, 0.6],
            "accel_z": [1.5, 0.9, -0.6, 1.1, 0.7],
            "breadth_50": [0.7, 0.75, 0.3, 0.65, 0.72],
            "vix_pctile": [0.38, 0.38, 0.38, 0.35, 0.35],
            "cohesion": [0.4, 0.5, 0.3, 0.4, 0.5],
            "cohesion_chg": [0.01, 0.02, -0.01, 0.01, 0.02],
            "persistence": [0.6, 0.7, 0.4, 0.6, 0.7],
            "ret": [0.01, 0.005, -0.002, 0.008, 0.003],
            "vel_1w": [1.0, 0.5, -0.3, 0.8, 0.4],
            "vel_1m": [2.0, 1.0, -0.5, 1.8, 0.9],
            "vel_3m": [5.0, 2.5, -1.0, 4.5, 2.3],
            "turnover_z": [0.1, 0.2, -0.1, 0.1, 0.2],
            "tlt_ret_10d": [-0.01, -0.01, -0.01, -0.01, -0.01],
            "spy_above_200d": [1.0, 1.0, 1.0, 1.0, 1.0],
        }, index=idx)
        panel.to_parquet(oracle_dir / "panel_s.parquet")

    if with_episodes:
        ep = pd.DataFrame([
            {
                "episode_id": "XLK::out::2026-06-25::1",
                "node": "XLK",
                "direction": "out",
                "onset_date": pd.Timestamp("2026-06-25"),
                "confirmed_date": pd.Timestamp("2026-06-28"),
                "undeniable_date": pd.NaT,
                "exhausted_date": pd.NaT,
                "two_sided": False,
                "paired_episode_id": None,
                "survivorship_flagged": False,
                "tier_src": "s",
            },
            {
                "episode_id": "XLV::in::2026-06-26::1",
                "node": "XLV",
                "direction": "in",
                "onset_date": pd.Timestamp("2026-06-26"),
                "confirmed_date": pd.NaT,
                "undeniable_date": pd.NaT,
                "exhausted_date": pd.NaT,
                "two_sided": False,
                "paired_episode_id": None,
                "survivorship_flagged": False,
                "tier_src": "s",
            },
        ])
        ep.to_parquet(oracle_dir / "episodes_s.parquet")

    if with_groups:
        rg = {
            "_meta": {"version": "1"},
            "complexes": [
                {"id": "tech", "name": "Technology", "name_zh": "科技", "members": ["XLK"]},
                {"id": "healthcare", "name": "Healthcare", "name_zh": "医疗", "members": ["XLV"]},
            ],
        }
        (oracle_dir / "rotation_groups.json").write_text(json.dumps(rg))

    if with_gauntlet:
        gauntlet_dir = oracle_dir / "gauntlet"
        gauntlet_dir.mkdir()
        p3 = {
            "s3_error_rates": {
                "false_start_rate_out_5d": 0.38,
                "false_start_rate_in_5d": 0.34,
                "onset_to_confirmed_rate_out": 0.997,
                "onset_to_confirmed_rate_in": 0.997,
            }
        }
        (gauntlet_dir / "p3_results.json").write_text(json.dumps(p3))

    return tmp_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_empty_dir_degrades_gracefully(tmp_path):
    """No artifacts present → payload still returns a valid dict."""
    oracle_dir = tmp_path / "oracle"
    oracle_dir.mkdir()
    state = build_oracle_state(data_dir=tmp_path)
    assert isinstance(state, dict)
    assert state["schema"] == SCHEMA
    assert state["disclaimers"]["display_only"] is True
    assert state["active_episodes"] == []
    assert state["complexes"] == []


def test_full_fixture_builds_correctly(tmp_path):
    data_dir = _make_data_dir(tmp_path)
    state = build_oracle_state(data_dir=data_dir)

    assert state["asof"] == "2026-07-01"
    assert isinstance(state["regime"]["breadth"], float)
    # XLK has a confirmed episode (out), XLV has onset episode (in)
    ep_nodes = {ep["node"] for ep in state["active_episodes"]}
    assert "XLK" in ep_nodes
    assert "XLV" in ep_nodes


def test_active_episodes_tiers(tmp_path):
    data_dir = _make_data_dir(tmp_path)
    state = build_oracle_state(data_dir=data_dir)
    ep_map = {ep["node"]: ep for ep in state["active_episodes"]}
    # XLK has confirmed_date set → tier should be confirmed
    assert ep_map["XLK"]["tier"] == "confirmed"
    # XLV has no confirmed_date → tier should be onset
    assert ep_map["XLV"]["tier"] == "onset"


def test_error_rates_from_gauntlet_not_hardcoded(tmp_path):
    data_dir = _make_data_dir(tmp_path)
    state = build_oracle_state(data_dir=data_dir)
    er = state["disclaimers"]["error_rates"]
    assert er["false_start_rate"] == pytest.approx(0.38)
    assert er["onset_to_confirmed_conversion"] == pytest.approx(0.997)


def test_error_rates_degrade_without_gauntlet(tmp_path):
    data_dir = _make_data_dir(tmp_path, with_gauntlet=False)
    state = build_oracle_state(data_dir=data_dir)
    er = state["disclaimers"]["error_rates"]
    assert er["false_start_rate"] is None
    assert er["onset_to_confirmed_conversion"] is None


def test_onset_watchlist_excludes_active_episodes(tmp_path):
    data_dir = _make_data_dir(tmp_path)
    state = build_oracle_state(data_dir=data_dir)
    # XLE has accel_z=-0.6 which is below WATCH_ACCEL_Z (0.8) → not on watchlist
    # XLK has active episode → should NOT appear on watchlist
    assert "XLK" not in state["onset_watchlist"]


def test_complex_state_reflects_episodes(tmp_path):
    data_dir = _make_data_dir(tmp_path)
    state = build_oracle_state(data_dir=data_dir)
    comp_map = {c["id"]: c for c in state["complexes"]}
    # tech complex has XLK → active_out
    assert comp_map["tech"]["state"] == "active_out"
    assert comp_map["tech"]["direction"] == "out"
    # healthcare complex has XLV → active_in
    assert comp_map["healthcare"]["state"] == "active_in"


def test_write_oracle_state(tmp_path):
    data_dir = _make_data_dir(tmp_path)
    state = build_oracle_state(data_dir=data_dir)
    out_dir = tmp_path / "out"
    write_oracle_state(state, out_dir=out_dir)
    p = out_dir / "oracle_state.json"
    assert p.exists()
    loaded = json.loads(p.read_text())
    assert loaded["schema"] == SCHEMA


def test_missing_episodes_tier_degrades(tmp_path):
    data_dir = _make_data_dir(tmp_path, with_episodes=False)
    state = build_oracle_state(data_dir=data_dir)
    assert state["active_episodes"] == []


def test_missing_groups_yields_empty_complexes(tmp_path):
    data_dir = _make_data_dir(tmp_path, with_groups=False)
    state = build_oracle_state(data_dir=data_dir)
    assert state["complexes"] == []
