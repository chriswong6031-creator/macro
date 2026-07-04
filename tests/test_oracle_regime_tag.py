"""Hermetic tests for A3 regime tag and oracle_regime_tag alert transitions.

Covers:
  - _compute_regime_tag: rotation / liquidation / accumulation / quiet fixtures
  - rotation → liquidation transition fires exactly ONE alert
  - silent seed on first run (no events)
  - idempotent id: same transition same bucket → deduped on second compute_events call
  - oracle_state regime.rotation_tag is present in build_oracle_state output
  - _snapshot persists rotation_tag for next-run diff

All language verified to be descriptive (no forecast words).
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from engine.oracle.live import (
    _compute_regime_tag,
    build_oracle_state,
    REGIME_CONFIRMED_FRACTION,
    REGIME_LIQUIDATION_MIN_SOURCES,
    REGIME_ACCUMULATION_MIN_SINKS,
)
from engine.oracle import alerts as A


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _complexes_def():
    """Two complexes for fixture purposes."""
    return [
        {"id": "tech", "name": "Technology", "name_zh": "科技",
         "members": ["XLK", "semis"]},
        {"id": "healthcare", "name": "Healthcare", "name_zh": "医疗",
         "members": ["XLV", "biotech"]},
        {"id": "energy", "name": "Energy", "name_zh": "能源",
         "members": ["XLE", "energybasemajors"]},
    ]


def _ep_map_with_confirmed_out(nodes: list[str]) -> dict[str, list[dict]]:
    """Build an active_ep_map where given nodes have confirmed OUT episodes."""
    m = {}
    for n in nodes:
        m[n] = [{"direction": "out", "tier": "confirmed"}]
    return m


def _ep_map_with_confirmed_in(nodes: list[str]) -> dict[str, list[dict]]:
    m = {}
    for n in nodes:
        m[n] = [{"direction": "in", "tier": "confirmed"}]
    return m


def _state_with_tag(tag: str, n_sources: int = 0, n_sinks: int = 0,
                    source_names=None, sink_names=None, asof="2026-07-04") -> dict:
    """Build a minimal oracle_state with a given rotation_tag."""
    return {
        "schema": "oracle_state.v1",
        "asof": asof,
        "regime": {
            "n_active_complexes": n_sources + n_sinks,
            "breadth": 0.6,
            "vix_regime": 0.4,
            "rotation_tag": {
                "tag": tag,
                "tag_zh": {"rotation": "轮动", "liquidation": "流动性收缩",
                            "accumulation": "资金积累", "quiet": "平静"}.get(tag, tag),
                "n_sources": n_sources,
                "n_sinks": n_sinks,
                "source_names": source_names or [],
                "sink_names": sink_names or [],
                "description_en": "Descriptive read — not a forecast.",
                "description_zh": "描述性读数——非预测。",
            },
        },
        "active_episodes": [],
        "complexes": [],
        "onset_watchlist": [],
        "disclaimers": {
            "display_only": True,
            "error_rates": {"onset_to_confirmed_conversion": 0.997, "false_start_rate": 0.38},
        },
    }


# ---------------------------------------------------------------------------
# _compute_regime_tag: tag logic
# ---------------------------------------------------------------------------

def test_regime_tag_rotation():
    """≥1 source AND ≥1 sink → rotation."""
    complexes = _complexes_def()
    # XLK confirmed OUT (tech is source), XLV confirmed IN (healthcare is sink)
    ep_map = {**_ep_map_with_confirmed_out(["XLK"]), **_ep_map_with_confirmed_in(["XLV"])}
    result = _compute_regime_tag(complexes, ep_map)
    assert result["tag"] == "rotation"
    assert result["n_sources"] >= 1
    assert result["n_sinks"] >= 1


def test_regime_tag_liquidation():
    """≥2 sources, 0 sinks → liquidation."""
    complexes = _complexes_def()
    # tech and energy are sources, no sinks
    ep_map = {**_ep_map_with_confirmed_out(["XLK", "XLE"])}
    result = _compute_regime_tag(complexes, ep_map)
    assert result["tag"] == "liquidation", f"Expected liquidation, got {result['tag']}"
    assert result["n_sources"] >= 2
    assert result["n_sinks"] == 0


def test_regime_tag_accumulation():
    """≥2 sinks, 0 sources → accumulation."""
    complexes = _complexes_def()
    # tech and healthcare are sinks, no sources
    ep_map = {**_ep_map_with_confirmed_in(["XLK", "XLV"])}
    result = _compute_regime_tag(complexes, ep_map)
    assert result["tag"] == "accumulation", f"Expected accumulation, got {result['tag']}"
    assert result["n_sinks"] >= 2
    assert result["n_sources"] == 0


def test_regime_tag_quiet_no_episodes():
    """No active episodes → quiet."""
    result = _compute_regime_tag(_complexes_def(), {})
    assert result["tag"] == "quiet"
    assert result["n_sources"] == 0
    assert result["n_sinks"] == 0


def test_regime_tag_quiet_single_source():
    """1 source and 0 sinks (below liquidation threshold of 2) → quiet."""
    complexes = _complexes_def()
    ep_map = _ep_map_with_confirmed_out(["XLK"])
    result = _compute_regime_tag(complexes, ep_map)
    # 1 source only → not rotation (no sink), not liquidation (need ≥2), → quiet
    assert result["tag"] == "quiet"


def test_regime_tag_onset_tier_not_counted():
    """Onset-tier episodes do NOT contribute to source/sink counts (spec: confirmed+)."""
    complexes = _complexes_def()
    ep_map = {"XLK": [{"direction": "out", "tier": "onset"}],
              "XLV": [{"direction": "in", "tier": "onset"}]}
    result = _compute_regime_tag(complexes, ep_map)
    # Both are onset tier → neither confirmed → n_sources=0, n_sinks=0 → quiet
    assert result["tag"] == "quiet"
    assert result["n_sources"] == 0
    assert result["n_sinks"] == 0


def test_regime_tag_undeniable_tier_counts_as_confirmed():
    """undeniable-tier episodes count (they are confirmed+)."""
    complexes = _complexes_def()
    ep_map = {"XLK": [{"direction": "out", "tier": "undeniable"}],
              "XLV": [{"direction": "in", "tier": "undeniable"}]}
    result = _compute_regime_tag(complexes, ep_map)
    assert result["tag"] == "rotation"


def test_regime_tag_output_fields():
    """Result dict has all required fields."""
    result = _compute_regime_tag(_complexes_def(), {})
    for field in ("tag", "tag_zh", "n_sources", "n_sinks",
                  "source_names", "sink_names", "description_en", "description_zh"):
        assert field in result, f"Missing field: {field}"


def test_regime_tag_no_forecast_language():
    """Description language must not contain affirmative forecast words (R4 binding).

    The phrase 'not a forecast' is acceptable — it clarifies that the text is
    descriptive.  We test for affirmative forecast/prediction claims only.
    """
    # Forbidden: affirmative forecast phrases (not disclaimers like "not a forecast")
    _FORBIDDEN = ["will rally", "will fall", "buy signal", "sell signal",
                  "expect returns", "predict returns"]
    for ep_map in (
        {},
        {**_ep_map_with_confirmed_out(["XLK", "XLE"])},
        {**_ep_map_with_confirmed_in(["XLK", "XLV"])},
        {**_ep_map_with_confirmed_out(["XLK"]), **_ep_map_with_confirmed_in(["XLV"])},
    ):
        result = _compute_regime_tag(_complexes_def(), ep_map)
        for phrase in _FORBIDDEN:
            assert phrase not in result["description_en"].lower(), (
                f"Forbidden phrase '{phrase}' found in description_en: {result['description_en']}"
            )
    # Extra: description_en must contain the word "descriptive" or "not a forecast"
    # to confirm it self-labels as display-only.
    for ep_map in (
        {},
        {**_ep_map_with_confirmed_out(["XLK", "XLE"])},
    ):
        result = _compute_regime_tag(_complexes_def(), ep_map)
        desc = result["description_en"].lower()
        assert ("descriptive" in desc or "not a forecast" in desc), (
            f"description_en should assert display-only status: {result['description_en']}"
        )


# ---------------------------------------------------------------------------
# build_oracle_state: rotation_tag present in payload
# ---------------------------------------------------------------------------

def _make_data_dir(tmp_path: Path, ep_direction_map: dict[str, str]) -> Path:
    """Minimal data_dir fixture with given episodes."""
    oracle_dir = tmp_path / "oracle"
    oracle_dir.mkdir(parents=True, exist_ok=True)

    # Panel
    import numpy as np
    idx = pd.MultiIndex.from_tuples(
        [("XLK", "2026-07-01"), ("XLV", "2026-07-01"), ("XLE", "2026-07-01")],
        names=["node", "date"],
    )
    panel = pd.DataFrame({
        "rs": [0.05, 0.02, -0.01],
        "accel": [1.2, 0.8, -0.5],
        "accel_z": [0.5, 0.5, 0.5],
        "breadth_50": [0.7, 0.75, 0.3],
        "vix_pctile": [0.38, 0.38, 0.38],
        "cohesion": [0.4, 0.5, 0.3],
        "cohesion_chg": [0.01, 0.02, -0.01],
        "persistence": [0.6, 0.7, 0.4],
        "ret": [0.01, 0.005, -0.002],
        "vel_1w": [1.0, 0.5, -0.3],
        "vel_1m": [2.0, 1.0, -0.5],
        "vel_3m": [5.0, 2.5, -1.0],
        "turnover_z": [0.1, 0.2, -0.1],
        "tlt_ret_10d": [-0.01, -0.01, -0.01],
        "spy_above_200d": [1.0, 1.0, 1.0],
    }, index=idx)
    panel.to_parquet(oracle_dir / "panel_s.parquet")

    # Episodes
    rows = []
    for node, direction in ep_direction_map.items():
        rows.append({
            "episode_id": f"{node}::{direction}::2026-06-25::1",
            "node": node,
            "direction": direction,
            "onset_date": pd.Timestamp("2026-06-25"),
            "confirmed_date": pd.Timestamp("2026-06-28"),  # confirmed tier
            "undeniable_date": pd.NaT,
            "exhausted_date": pd.NaT,
            "two_sided": False,
            "paired_episode_id": None,
            "survivorship_flagged": False,
        })
    if rows:
        pd.DataFrame(rows).to_parquet(oracle_dir / "episodes_s.parquet")

    # Rotation groups
    rg = {
        "_meta": {},
        "complexes": [
            {"id": "tech", "name": "Technology", "name_zh": "科技", "members": ["XLK"]},
            {"id": "healthcare", "name": "Healthcare", "name_zh": "医疗", "members": ["XLV"]},
            {"id": "energy", "name": "Energy", "name_zh": "能源", "members": ["XLE"]},
        ],
    }
    (oracle_dir / "rotation_groups.json").write_text(json.dumps(rg))
    return tmp_path


def test_build_oracle_state_includes_rotation_tag(tmp_path):
    """oracle_state.regime.rotation_tag is present after build_oracle_state."""
    data_dir = _make_data_dir(tmp_path, {"XLK": "out", "XLE": "out"})
    state = build_oracle_state(data_dir=data_dir)
    regime = state.get("regime") or {}
    assert "rotation_tag" in regime, "regime.rotation_tag missing"
    rt = regime["rotation_tag"]
    assert rt["tag"] in ("rotation", "liquidation", "accumulation", "quiet")


def test_build_oracle_state_rotation_tag_liquidation_fixture(tmp_path):
    """Two confirmed OUT episodes, no IN → tag should be liquidation."""
    data_dir = _make_data_dir(tmp_path, {"XLK": "out", "XLE": "out"})
    state = build_oracle_state(data_dir=data_dir)
    rt = state["regime"]["rotation_tag"]
    assert rt["tag"] == "liquidation", (
        f"Expected liquidation (2 sources, 0 sinks), got {rt['tag']}. "
        f"n_sources={rt['n_sources']}, n_sinks={rt['n_sinks']}"
    )


def test_build_oracle_state_rotation_tag_rotation_fixture(tmp_path):
    """One confirmed OUT + one confirmed IN → tag should be rotation."""
    data_dir = _make_data_dir(tmp_path, {"XLK": "out", "XLV": "in"})
    state = build_oracle_state(data_dir=data_dir)
    rt = state["regime"]["rotation_tag"]
    assert rt["tag"] == "rotation", (
        f"Expected rotation (1 source, 1 sink), got {rt['tag']}. "
        f"n_sources={rt['n_sources']}, n_sinks={rt['n_sinks']}"
    )


def test_build_oracle_state_rotation_tag_degrades_without_episodes(tmp_path):
    """No episodes → tag should be quiet; no exception raised."""
    data_dir = _make_data_dir(tmp_path, {})
    state = build_oracle_state(data_dir=data_dir)
    rt = state["regime"]["rotation_tag"]
    assert rt["tag"] == "quiet"


# ---------------------------------------------------------------------------
# Alert tests: oracle_regime_tag transitions
# ---------------------------------------------------------------------------

def test_regime_tag_alert_silent_seed():
    """First run (no prior state) → no events (silent seed preserved)."""
    state = _state_with_tag("liquidation", n_sources=2, source_names=["Technology", "Energy"])
    events = A.compute_events(state, None)
    assert events == []


def test_regime_tag_alert_silent_seed_empty_prior():
    """Empty prior state (first run) → no events."""
    state = _state_with_tag("rotation", n_sources=1, n_sinks=1)
    events = A.compute_events(state, {})
    assert events == []


def test_regime_tag_transition_rotation_to_liquidation_fires_exactly_one_alert():
    """rotation → liquidation transition fires exactly one oracle_regime_tag alert."""
    # Prior state: tag was rotation
    prior = {
        "__regime__": {
            "breadth": 0.6,
            "n_active_complexes": 2,
            "rotation_tag": "rotation",   # prior tag
        }
    }
    # Current state: tag is liquidation
    state = _state_with_tag("liquidation", n_sources=2, n_sinks=0,
                             source_names=["Technology", "Energy"])

    events = A.compute_events(state, prior)
    tag_events = [e for e in events if e["type"] == "oracle_regime_tag"]
    assert len(tag_events) == 1, (
        f"Expected exactly 1 oracle_regime_tag event, got {len(tag_events)}. "
        f"events={[e['type'] for e in events]}"
    )
    ev = tag_events[0]
    assert ev["severity"] == "high"
    assert "rotation" in ev["headline"].lower()
    assert "liquidation" in ev["headline"].lower()


def test_regime_tag_no_alert_when_tag_unchanged():
    """Same tag in prior and current → no transition event."""
    prior = {"__regime__": {"breadth": 0.6, "n_active_complexes": 2, "rotation_tag": "rotation"}}
    state = _state_with_tag("rotation", n_sources=1, n_sinks=1)
    events = A.compute_events(state, prior)
    tag_events = [e for e in events if e["type"] == "oracle_regime_tag"]
    assert len(tag_events) == 0


def test_regime_tag_quiet_to_rotation_fires_alert():
    """quiet → rotation transition fires alert."""
    prior = {"__regime__": {"breadth": 0.4, "n_active_complexes": 0, "rotation_tag": "quiet"}}
    state = _state_with_tag("rotation", n_sources=1, n_sinks=1,
                             source_names=["Technology"], sink_names=["Healthcare"])
    events = A.compute_events(state, prior)
    tag_events = [e for e in events if e["type"] == "oracle_regime_tag"]
    assert len(tag_events) == 1


def test_regime_tag_alert_is_bilingual():
    """oracle_regime_tag event has headline_zh and detail_zh."""
    prior = {"__regime__": {"breadth": 0.4, "rotation_tag": "quiet"}}
    state = _state_with_tag("rotation", n_sources=1, n_sinks=1)
    events = A.compute_events(state, prior)
    tag_events = [e for e in events if e["type"] == "oracle_regime_tag"]
    assert len(tag_events) == 1
    ev = tag_events[0]
    assert ev.get("headline_zh"), "Missing headline_zh"
    assert ev.get("detail_zh"), "Missing detail_zh"


def test_regime_tag_alert_id_is_deterministic():
    """Same transition same date → same id (idempotent)."""
    prior = {"__regime__": {"breadth": 0.4, "rotation_tag": "quiet"}}
    state = _state_with_tag("rotation", n_sources=1, n_sinks=1, asof="2026-07-04")

    evs1 = A.compute_events(state, prior)
    evs2 = A.compute_events(state, prior)
    ids1 = {e["id"] for e in evs1 if e["type"] == "oracle_regime_tag"}
    ids2 = {e["id"] for e in evs2 if e["type"] == "oracle_regime_tag"}
    assert ids1 == ids2, "Same transition same date must produce same event id"


def test_regime_tag_alert_no_forecast_language():
    """Alert detail must not contain affirmative forecast phrases (R4 binding).

    Phrases like 'not a forecast' are acceptable — they clarify display-only intent.
    We check for affirmative prediction language only.
    """
    _FORBIDDEN = ["buy signal", "sell signal", "will rally", "will fall",
                  "predict returns", "expect returns"]
    prior = {"__regime__": {"breadth": 0.4, "rotation_tag": "quiet"}}
    state = _state_with_tag("liquidation", n_sources=2, n_sinks=0,
                             source_names=["Technology", "Energy"])
    events = A.compute_events(state, prior)
    tag_events = [e for e in events if e["type"] == "oracle_regime_tag"]
    assert len(tag_events) == 1
    ev = tag_events[0]
    for phrase in _FORBIDDEN:
        assert phrase not in ev["detail"].lower(), (
            f"Forbidden phrase '{phrase}' in detail: {ev['detail']}"
        )
    # The alert detail must also self-label as display-only
    detail_lower = ev["detail"].lower()
    assert ("descriptive" in detail_lower or "not a forecast" in detail_lower), (
        f"Alert detail should assert display-only status: {ev['detail']}"
    )


def test_snapshot_persists_rotation_tag():
    """_snapshot includes rotation_tag in __regime__ for next-run diff."""
    state = _state_with_tag("liquidation", n_sources=2)
    snap = A._snapshot(state)
    assert "__regime__" in snap
    assert snap["__regime__"]["rotation_tag"] == "liquidation"


def test_snapshot_persists_quiet_tag():
    """_snapshot persists quiet tag too."""
    state = _state_with_tag("quiet")
    snap = A._snapshot(state)
    assert snap["__regime__"]["rotation_tag"] == "quiet"


# ---------------------------------------------------------------------------
# B1 personality folded into oracle_state
# ---------------------------------------------------------------------------

def test_active_episodes_include_personality_field(tmp_path):
    """active_episodes in oracle_state include 'personality' field (None if no personality.json)."""
    data_dir = _make_data_dir(tmp_path, {"XLK": "out"})
    state = build_oracle_state(data_dir=data_dir)
    ep_list = state.get("active_episodes") or []
    assert len(ep_list) > 0
    for ep in ep_list:
        assert "personality" in ep, f"active_episode missing 'personality' field: {ep}"


def test_complexes_include_personality_field(tmp_path):
    """complexes in oracle_state include 'personality' field."""
    data_dir = _make_data_dir(tmp_path, {"XLK": "out"})
    state = build_oracle_state(data_dir=data_dir)
    complexes = state.get("complexes") or []
    for c in complexes:
        assert "personality" in c, f"complex missing 'personality' field: {c}"
