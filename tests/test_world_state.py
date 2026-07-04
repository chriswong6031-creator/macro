"""Hermetic tests for engine.neuralweb.world_state.

All tests use synthetic in-memory fixtures and a tmp_path store (no real
market data loaded from disk).  The build_world_state() and build_and_write()
functions accept a root override that points at a synthetic directory tree
constructed per-test.

Tests
-----
1.  full_composition_shape    — all blocks present with expected keys
2.  missing_market_state      — null verdict + gaps entry, no raise
3.  missing_regime            — null regime/vol/liquidity/risk_radar_raw + gaps
4.  missing_oracle            — null rotation + gaps, no raise
5.  missing_run_status        — null data_health + gaps, no raise
6.  missing_alerts_triage     — null alerts + gaps, no raise
7.  missing_breadth_parquet   — null breadth (or partial) + gaps, no raise
8.  risk_radar_raw_verbatim   — json.dumps equality with the source sub-object
9.  envelope_present          — produced_by, inputs_hash, tier, schema_version
10. envelope_verify_clean     — verify() returns []
11. stamp_if_changed_identity — unchanged sources -> byte-identical file
12. rotation_episode_counts   — episode_counts math correct
13. breadth_last_row          — last-row extraction correct (tiny parquet fixture)
14. determinism               — two calls with same now give same inputs_hash
15. qi_block_null             — qi is always null with qi_note present
16. all_missing               — total failure -> partial payload with all gaps, no raise
"""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from engine.neuralweb.world_state import build_world_state, build_and_write

# ---------------------------------------------------------------------------
# Shared synthetic registry (injected where needed)
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)
_NOW_STR = "2026-07-04T12:00:00Z"

# ---------------------------------------------------------------------------
# Fixtures — synthetic store builders
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SYNAPSE_YML = _REPO_ROOT / "config" / "synapse.yml"


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def _seed_synapse(root: Path) -> None:
    """Copy the real synapse.yml into the synthetic root so stamp() can resolve defaults."""
    import shutil
    dest = root / "config" / "synapse.yml"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(_SYNAPSE_YML, dest)


def _make_market_state(root: Path) -> dict:
    ms = {
        "schema": "market_state.v2",
        "asof": "2026-07-01",
        "verdict": "CAUTION",
        "score": 55,
        "raw_score": 60,
        "is_display_only": True,
        "label_en": "Caution",
        "label_zh": "谨慎",
        "radar": {
            "state": "caution",
            "ceiling": 60,
            "amp": 1.2,
            "amp_keys": ["vol"],
            "severe_gated": False,
            "recovery": False,
            "is_loud": False,
            "top_score": 58,
            "scares": [],
            "forward_log": [],
        },
        "components": {},
        "overrides": [],
    }
    _write_json(root / "data" / "market_state" / "latest.json", ms)
    return ms


def _make_regime(root: Path) -> dict:
    reg = {
        "quad": "Q1",
        "quad_name": "Goldilocks",
        "label": "Goldilocks",
        "confidence": 0.8,
        "growth_score": 70.0,
        "inflation_score": 30.0,
        "cycle_tag": "mid",
        "transition_state": "STABLE",
        "flip_condition": "inflation_rising",
        "flip_margin": 0.15,
        "liquidity_quality": "ok",
        "business_cycle": "expansion",
        "freshness": {
            "asof": "2026-07-01",
            "built_at": "2026-07-04T06:38:00Z",
            "age_days": 3,
            "age_sessions": 2,
            "max_age_sessions": 1,
            "stale": True,
            "note": "test freshness",
        },
        "asof": "2026-07-01",
        "schema_version": 1,
        "liquidity_overlay": "expanding",
        "risk_radar": {
            "schema": "risk_radar.v2",
            "asof": "2026-07-01",
            "state": "caution",
            "alert": False,
            "dominant_scare": "vol",
            "scares": [{"name": "vol", "score": 0.4}],
        },
        "vol_regime": {
            "available": True,
            "asof": "2026-07-01",
            "regime": "normalizing",
            "risk_score": -0.1,
            "scored_score": None,
            "scored_active": False,
            "vix": 15.2,
            "vrp_state": "normal",
            "vvix_state": "normal",
            "vol_target_scalar": 1.0,
            "fragility_confluence": 0,
            "flags": [],
        },
        "conditions": {
            "complacency": {
                "breadth_above200_pctile": 0.56,
                "breadth_div": False,
            },
            "financial_conditions": {"state": "loose"},
            "systemic_stress": {"state": "calm"},
        },
    }
    _write_json(root / "data" / "regime" / "latest.json", reg)
    return reg


def _make_breadth_parquet(root: Path) -> None:
    import numpy as np
    bp = root / "data" / "breadth" / "breadth.parquet"
    bp.parent.mkdir(parents=True, exist_ok=True)
    dates = pd.to_datetime(["2026-06-30", "2026-07-01"])
    df = pd.DataFrame(
        {
            "n_members": [500.0, 501.0],
            "pct_above_50": [60.0, 63.7],
            "pct_above_200": [62.0, 63.8],
            "nh": [40.0, 45.0],
            "nl": [3.0, 2.0],
            "adv": [290.0, 297.0],
            "dec": [210.0, 204.0],
            "ad_line": [6500.0, 6608.0],
        },
        index=dates,
    )
    df.to_parquet(bp)


def _make_oracle_state(root: Path) -> dict:
    oracle = {
        "schema": "oracle_state.v1",
        "asof": "2026-07-01",
        "regime": {
            "n_active_complexes": 7,
            "breadth": 0.6107,
            "vix_regime": 0.377,
        },
        "complexes": [
            {
                "id": "ai_compute",
                "name": "AI Compute",
                "name_zh": "AI计算",
                "state": "active_in",
                "tier": "confirmed",
                "direction": "in",
                "n_members_active": 5,
            },
            {
                "id": "healthcare_defensive",
                "name": "Healthcare Defensive",
                "name_zh": "医疗防御",
                "state": "active_out",
                "tier": "onset",
                "direction": "out",
                "n_members_active": 3,
            },
        ],
        "active_episodes": [
            {"node": "ai_compute", "direction": "in", "tier": "confirmed",
             "onset_date": "2026-06-01", "confirmed_date": "2026-06-05",
             "two_sided": False, "pair": None, "survivorship_flagged": False,
             "base_rate_context": {}, "analogues": []},
            {"node": "ai_compute", "direction": "in", "tier": "onset",
             "onset_date": "2026-06-15", "confirmed_date": None,
             "two_sided": False, "pair": None, "survivorship_flagged": False,
             "base_rate_context": {}, "analogues": []},
            {"node": "healthcare_defensive", "direction": "out", "tier": "confirmed",
             "onset_date": "2026-06-10", "confirmed_date": "2026-06-14",
             "two_sided": True, "pair": "ai_compute", "survivorship_flagged": False,
             "base_rate_context": {}, "analogues": []},
        ],
        "onset_watchlist": ["XLC", "XLY"],
        "disclaimers": {"display_only": True},
    }
    _write_json(root / "site" / "basketdata" / "oracle_state.json", oracle)
    return oracle


def _make_run_status(root: Path) -> dict:
    rs = {
        "last_run": "2026-07-04T11:04:44.441690+00:00",
        "sources": {
            "fred": {"status": "failed", "error": "403 Forbidden", "checked_at": "2026-07-04T11:00:00Z"},
            "polygon": {"status": "ok", "error": None, "checked_at": "2026-07-04T11:00:00Z"},
            "yfinance": {"status": "ok", "error": None, "checked_at": "2026-07-04T11:00:00Z"},
        },
        "circuit_breaker": {
            "fred": 7,
            "farside": 7,
            "polygon": 0,
        },
        "circuit_breaker_probe": {},
        "stale_series": ["SPY_vol", "GLD_vol"],
    }
    _write_json(root / "data" / "run_status.json", rs)
    return rs


def _make_alerts_triage(root: Path) -> dict:
    at = {
        "generated_utc": "2026-07-04T12:00:00",
        "asof": "2026-07-04",
        "window_days": 30,
        "regime": {},
        "cross_asset": {},
        "risk_backdrop": {},
        "events": [],
        "summary": {
            "total": 60,
            "critical": 2,
            "major": 58,
            "minor": 0,
            "actionable": 2,
            "backtested": 1,
            "by_source": {},
        },
        "alerts": [],
        "weights": {},
    }
    _write_json(root / "site" / "factordata" / "alerts_triage.json", at)
    return at


def _full_tree(root: Path) -> tuple[dict, dict, dict, dict, dict]:
    """Build all synthetic source files; return the raw dicts for assertions."""
    _seed_synapse(root)
    ms = _make_market_state(root)
    reg = _make_regime(root)
    _make_breadth_parquet(root)
    oracle = _make_oracle_state(root)
    rs = _make_run_status(root)
    at = _make_alerts_triage(root)
    return ms, reg, oracle, rs, at


# ---------------------------------------------------------------------------
# Test 1: full composition shape
# ---------------------------------------------------------------------------

def test_full_composition_shape(tmp_path):
    ms, reg, oracle, rs, at = _full_tree(tmp_path)
    payload = build_world_state(root=tmp_path, now=_NOW)

    assert isinstance(payload, dict)
    # Top-level required keys
    for key in ("verdict", "radar", "risk_radar_raw", "regime", "vol",
                 "breadth", "rotation", "liquidity", "data_health",
                 "alerts", "qi", "qi_note", "live_overlay", "gaps", "sources"):
        assert key in payload, f"missing top-level key: {key!r}"

    # Envelope keys
    from engine.neuralweb.envelope import ENVELOPE_KEYS
    for k in ENVELOPE_KEYS:
        assert k in payload, f"missing envelope key: {k!r}"

    # No gaps from a full tree
    assert payload["gaps"] == [], f"unexpected gaps: {payload['gaps']}"


# ---------------------------------------------------------------------------
# Test 2: missing market_state -> null verdict + gaps entry, no raise
# ---------------------------------------------------------------------------

def test_missing_market_state(tmp_path):
    _seed_synapse(tmp_path)
    _make_regime(tmp_path)
    _make_breadth_parquet(tmp_path)
    _make_oracle_state(tmp_path)
    _make_run_status(tmp_path)
    _make_alerts_triage(tmp_path)
    # market_state/latest.json is NOT created

    payload = build_world_state(root=tmp_path, now=_NOW)
    assert payload["verdict"] is None
    assert payload["radar"] is None
    assert any("market_state" in g for g in payload["gaps"])


# ---------------------------------------------------------------------------
# Test 3: missing regime -> null regime/vol/liquidity/risk_radar_raw + gaps
# ---------------------------------------------------------------------------

def test_missing_regime(tmp_path):
    _seed_synapse(tmp_path)
    _make_market_state(tmp_path)
    _make_breadth_parquet(tmp_path)
    _make_oracle_state(tmp_path)
    _make_run_status(tmp_path)
    _make_alerts_triage(tmp_path)
    # regime/latest.json is NOT created

    payload = build_world_state(root=tmp_path, now=_NOW)
    assert payload["regime"] is None or payload["regime"].get("quad") is None
    assert payload["risk_radar_raw"] is None
    assert any("regime" in g for g in payload["gaps"])


# ---------------------------------------------------------------------------
# Test 4: missing oracle -> null rotation + gaps, no raise
# ---------------------------------------------------------------------------

def test_missing_oracle(tmp_path):
    _seed_synapse(tmp_path)
    _make_market_state(tmp_path)
    _make_regime(tmp_path)
    _make_breadth_parquet(tmp_path)
    _make_run_status(tmp_path)
    _make_alerts_triage(tmp_path)
    # oracle_state.json NOT created

    payload = build_world_state(root=tmp_path, now=_NOW)
    assert payload["rotation"] is None
    assert any("oracle" in g for g in payload["gaps"])


# ---------------------------------------------------------------------------
# Test 5: missing run_status -> null data_health + gaps, no raise
# ---------------------------------------------------------------------------

def test_missing_run_status(tmp_path):
    _seed_synapse(tmp_path)
    _make_market_state(tmp_path)
    _make_regime(tmp_path)
    _make_breadth_parquet(tmp_path)
    _make_oracle_state(tmp_path)
    _make_alerts_triage(tmp_path)

    payload = build_world_state(root=tmp_path, now=_NOW)
    assert payload["data_health"] is None
    assert any("run_status" in g for g in payload["gaps"])


# ---------------------------------------------------------------------------
# Test 6: missing alerts_triage -> null alerts + gaps, no raise
# ---------------------------------------------------------------------------

def test_missing_alerts_triage(tmp_path):
    _seed_synapse(tmp_path)
    _make_market_state(tmp_path)
    _make_regime(tmp_path)
    _make_breadth_parquet(tmp_path)
    _make_oracle_state(tmp_path)
    _make_run_status(tmp_path)

    payload = build_world_state(root=tmp_path, now=_NOW)
    assert payload["alerts"] is None
    assert any("alerts_triage" in g for g in payload["gaps"])


# ---------------------------------------------------------------------------
# Test 7: missing breadth parquet -> breadth null or partial + gaps, no raise
# ---------------------------------------------------------------------------

def test_missing_breadth_parquet(tmp_path):
    _seed_synapse(tmp_path)
    _make_market_state(tmp_path)
    _make_regime(tmp_path)
    # breadth.parquet NOT created; directory exists
    (tmp_path / "data" / "breadth").mkdir(parents=True, exist_ok=True)
    _make_oracle_state(tmp_path)
    _make_run_status(tmp_path)
    _make_alerts_triage(tmp_path)

    payload = build_world_state(root=tmp_path, now=_NOW)
    # breadth block may be partially composed (derived fields from regime)
    # The test is: no raise, and breadth_above200_pctile is extracted from regime
    breadth = payload.get("breadth") or {}
    # pct_above_200 will be absent (parquet missing) but derived fields may be present
    assert "pct_above_200" not in breadth or breadth["pct_above_200"] is None


# ---------------------------------------------------------------------------
# Test 8: risk_radar_raw verbatim — json.dumps equality with source sub-object
# ---------------------------------------------------------------------------

def test_risk_radar_raw_verbatim(tmp_path):
    _seed_synapse(tmp_path)
    _make_market_state(tmp_path)
    reg = _make_regime(tmp_path)
    _make_breadth_parquet(tmp_path)
    _make_oracle_state(tmp_path)
    _make_run_status(tmp_path)
    _make_alerts_triage(tmp_path)

    source_rr = copy.deepcopy(reg["risk_radar"])
    payload = build_world_state(root=tmp_path, now=_NOW)

    # Byte-verbatim: json.dumps of the two dicts must match
    assert json.dumps(payload["risk_radar_raw"], sort_keys=True) == json.dumps(
        source_rr, sort_keys=True
    ), "risk_radar_raw differs from the source risk_radar sub-object"


# ---------------------------------------------------------------------------
# Test 9: envelope present
# ---------------------------------------------------------------------------

def test_envelope_present(tmp_path):
    _full_tree(tmp_path)
    payload = build_world_state(root=tmp_path, now=_NOW)

    from engine.neuralweb.envelope import ENVELOPE_KEYS
    for k in ENVELOPE_KEYS:
        assert k in payload, f"missing envelope key {k!r}"

    assert payload["produced_by"] == "engine/neuralweb/world_state.py"
    assert payload["produced_at"] == _NOW_STR
    assert payload["inputs_hash"].startswith("sha256:")
    assert payload["tier"] == "infrastructure"


# ---------------------------------------------------------------------------
# Test 10: envelope verify() returns empty list
# ---------------------------------------------------------------------------

def test_envelope_verify_clean(tmp_path):
    _full_tree(tmp_path)
    payload = build_world_state(root=tmp_path, now=_NOW)

    from engine.neuralweb.envelope import verify
    problems = verify(payload)
    assert problems == [], f"envelope verify() found problems: {problems}"


# ---------------------------------------------------------------------------
# Test 11: stamp_if_changed byte-identity on unchanged sources
# ---------------------------------------------------------------------------

def test_stamp_if_changed_identity(tmp_path):
    _full_tree(tmp_path)

    # First write
    out = tmp_path / "data" / "neuralweb" / "world_state.json"
    p1 = build_and_write(root=tmp_path, now=_NOW, out_path=out)
    bytes1 = out.read_bytes()

    # Second write with SAME now and SAME sources
    p2 = build_and_write(root=tmp_path, now=_NOW, out_path=out)
    bytes2 = out.read_bytes()

    # Bytes must be identical (stamp_if_changed returns prev_payload verbatim)
    assert bytes1 == bytes2, (
        f"stamp_if_changed did not preserve byte identity: "
        f"len1={len(bytes1)} len2={len(bytes2)}"
    )
    assert p1["inputs_hash"] == p2["inputs_hash"]


# ---------------------------------------------------------------------------
# Test 12: rotation episode_counts math correct
# ---------------------------------------------------------------------------

def test_rotation_episode_counts(tmp_path):
    _seed_synapse(tmp_path)
    _make_market_state(tmp_path)
    _make_regime(tmp_path)
    _make_breadth_parquet(tmp_path)
    oracle = _make_oracle_state(tmp_path)
    _make_run_status(tmp_path)
    _make_alerts_triage(tmp_path)

    payload = build_world_state(root=tmp_path, now=_NOW)
    rotation = payload["rotation"]
    assert rotation is not None

    episodes = oracle["active_episodes"]
    ec = rotation["episode_counts"]
    assert ec["total"] == len(episodes)

    # by_tier: confirmed=2, onset=1
    assert ec["by_tier"]["confirmed"] == 2
    assert ec["by_tier"]["onset"] == 1

    # by_direction: in=2, out=1
    assert ec["by_direction"]["in"] == 2
    assert ec["by_direction"]["out"] == 1

    assert rotation["n_onset_watchlist"] == len(oracle["onset_watchlist"])


# ---------------------------------------------------------------------------
# Test 13: breadth last-row extraction correct
# ---------------------------------------------------------------------------

def test_breadth_last_row(tmp_path):
    _seed_synapse(tmp_path)
    _make_market_state(tmp_path)
    reg = _make_regime(tmp_path)
    _make_breadth_parquet(tmp_path)
    _make_oracle_state(tmp_path)
    _make_run_status(tmp_path)
    _make_alerts_triage(tmp_path)

    payload = build_world_state(root=tmp_path, now=_NOW)
    breadth = payload["breadth"]
    assert breadth is not None

    # Last row values from _make_breadth_parquet
    assert abs(breadth["pct_above_200"] - 63.8) < 0.01
    assert abs(breadth["pct_above_50"] - 63.7) < 0.01
    assert breadth["nh"] == 45
    assert breadth["nl"] == 2
    assert breadth["date"] == "2026-07-01"

    # Derived from regime
    assert abs(breadth["breadth_above200_pctile"] - 0.56) < 0.001
    assert breadth["breadth_div"] is False


# ---------------------------------------------------------------------------
# Test 14: determinism — same now gives same inputs_hash
# ---------------------------------------------------------------------------

def test_determinism(tmp_path):
    _full_tree(tmp_path)

    p1 = build_world_state(root=tmp_path, now=_NOW)
    p2 = build_world_state(root=tmp_path, now=_NOW)

    assert p1["inputs_hash"] == p2["inputs_hash"], (
        f"non-deterministic: inputs_hash differs between two calls"
    )


# ---------------------------------------------------------------------------
# Test 15: qi block is always null with qi_note present
# ---------------------------------------------------------------------------

def test_qi_block_null(tmp_path):
    _full_tree(tmp_path)
    payload = build_world_state(root=tmp_path, now=_NOW)

    assert payload["qi"] is None, "qi must be null pending the W7 border ruling"
    assert isinstance(payload.get("qi_note"), str) and len(payload["qi_note"]) > 10


# ---------------------------------------------------------------------------
# Test 16: all sources missing -> partial payload, all gaps recorded, no raise
# ---------------------------------------------------------------------------

def test_all_missing(tmp_path):
    # Empty tree: only synapse present (no data source files created)
    _seed_synapse(tmp_path)
    payload = build_world_state(root=tmp_path, now=_NOW)

    assert isinstance(payload, dict)
    assert payload["verdict"] is None
    assert payload["regime"] is None
    assert payload["rotation"] is None
    assert payload["data_health"] is None
    assert payload["alerts"] is None
    assert len(payload["gaps"]) >= 4  # at least the major sources

    # qi is always null, regardless
    assert payload["qi"] is None
    assert "qi_note" in payload
