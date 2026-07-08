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
17. liquidity_overlay         — regime block carries liquidity_overlay and sector_rs
18. test_rulnw2_artifact_present_lobe_from_artifact   — RUL-NW2a canonical path
19. test_rulnw2_artifact_absent_fallback_path         — RUL-NW2b fallback path
20. test_rulnw2_artifact_corrupt_json_fallback        — RUL-NW2c corrupt artifact
21. test_rulnw2_artifact_missing_factor_weather_block — RUL-NW2d missing fw block
22. test_rulnw2_prefer_artifact_false_skips_artifact  — freeze-regression: prefer_artifact=False
23. test_rulnw2_builder_calls_prefer_artifact_false   — builder integration regression
24. test_rulnw2_artifact_display_only_false_is_coerced — display_only:False coerced True
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
        "sector_rs": [
            {"ticker": "XLK", "rs": 0.9, "mom_20d_pct": 5.2, "mom_60d_pct": 18.0,
             "above_200d_trend": True, "pctile_252d": 96.0, "rank": 1},
        ],
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


def _make_transmission(root: Path) -> dict:
    tx = {
        "asof": "2026-07-01",
        "state": {"rates": {"regime": "restrictive"}},
        "scored_status": {"en": "Display-only."},
        "calibrated": True,
        "headwinds": [{"asset": "XLU", "verdict": "headwind", "net": -0.4}],
        "tailwinds": [{"asset": "XLK", "verdict": "tailwind", "net": 0.3}],
        "yield_curve": {
            "regime": {"key": "bear_flattener", "label": "Bear Flattener"},
            "recession": {"risk": "low", "ntfs": "no signal"},
            "shape": {"slope_2s10s": 0.31},
        },
    }
    _write_json(root / "data" / "transmission" / "latest.json", tx)
    return tx


def _make_forex(root: Path) -> dict:
    fx = {
        "date": "Jul 01, 2026",
        "regime": "dollar_bull",
        "risk": "risk_on",
        "favored": ["EUR", "JPY"],
        "dollar_desk": {
            "lean": "neutral",
            "real_rate_regime": "positive",
            "usd_valuation": "overvalued",
            "trend": "declining",
            "fed_path_lean": "hawkish",
            "liquidity_dir": "tightening",
        },
        "transmission": {
            "usd_dir": "down",
            "headwind_for": ["EM", "Gold"],
            "tailwind_for": ["USD assets"],
            "unstable": False,
        },
        "regime_radar": {
            "as_of": "2026-07-01",
            "dominant": "dollar_bull",
            "active": ["dollar_bull"],
        },
    }
    _write_json(root / "data" / "forex" / "latest.json", fx)
    return fx


def _make_bond_health(root: Path) -> dict:
    bh = {
        "as_of": "2026-07-01",
        "health_score": 85,
        "health_label": "healthy",
        "cycle_phase": "late",
        "recession_risk": 3.9,
        "drawdown_risk": 15.1,
        "alarms": [],
        "verdict_en": "Bond health healthy.",
        "drivers_for": {},
        "fed_path": {
            "policy_rate": 5.25,
            "implied_bp_12m": -75.0,
            "implied_cuts_12m": 3,
        },
        "bond_compass": {"duration": "short", "curve_trade": "steepener"},
        "bond_cross_asset": {"verdict_en": "Rates supportive."},
    }
    _write_json(root / "data" / "bonds" / "bond_health.json", bh)
    return bh


def _make_china_regime(root: Path) -> dict:
    cr = {
        "date": "2026-07-01",
        "quad": "Q3",
        "quad_name": "Stagflation",
        "cycle_tag": "mid",
        "confidence": 0.185,
        "liquidity_overlay": "neutral",
        "pending_quad": "Q2",
    }
    _write_json(root / "data" / "china_regime" / "latest.json", cr)
    return cr


def _make_hk_regime(root: Path) -> dict:
    hkr = {
        "date": "2026-07-01",
        "quad": "Q4",
        "quad_name": "Growth-scare",
        "cycle_tag": "mid",
        "confidence": 0.083,
        "liquidity_overlay": "neutral",
        "pending_quad": "Q3",
        "risk_state": "Neutral",
        "peg_state": "weak-side",
    }
    _write_json(root / "data" / "hk_regime" / "latest.json", hkr)
    return hkr


def _make_canada_regime(root: Path) -> dict:
    car = {
        "date": "2026-07-01",
        "quad": "Q1",
        "quad_name": "Goldilocks",
        "cycle_tag": "late",
        "confidence": 0.305,
        "liquidity_overlay": "neutral",
        "pending_quad": "Q4",
    }
    _write_json(root / "data" / "canada_regime" / "latest.json", car)
    return car


def _make_commodity(root: Path) -> dict:
    cm = {
        "date": "Jul 01, 2026",
        "regime": "Goldilocks",
        "favored": ["Gold", "Copper"],
        "assets": {
            "gold": {"label": "Gold", "trend": "up", "action": "hold", "conviction": "high"},
            "copper": {"label": "Copper", "trend": "up", "action": "hold", "conviction": "medium"},
        },
    }
    _write_json(root / "data" / "commodity" / "latest.json", cm)
    return cm


def _make_briefing(root: Path) -> dict:
    br = {
        "schema": "briefing.v1",
        "as_of": "2026-07-04",
        "n_universe": 4725,
        "n_priority": 25,
        "n_actionable": 9,
        "n_divergences": 51,
        "macro_context": {
            "regime": "Q1",
            "posture": "neutral",
            "fed_stance": "hawkish",
        },
        "priority_queue": [
            {"ticker": "AAPL", "priority": 1, "lean": "long", "read": "Breakout."},
            {"ticker": "MSFT", "priority": 2, "lean": "long", "read": "Momentum."},
        ],
    }
    _write_json(root / "site" / "intelligence" / "briefing.json", br)
    return br


def _make_factor_series(root: Path) -> dict:
    fs = {
        "as_of": "2026-07-04",
        "rotation": {
            "leader": "quality",
            "leader_label": "Quality",
            "leader_ret20_pct": 2.1,
            "leader_held_days": 25,
            "recent_flips": [
                {"date": "2026-03-17", "to": "quality", "label": "Quality"},
            ],
        },
        "horizons": {
            "value": {"long_only": {"d1": 0.01, "d5": 0.02, "d20": 0.05}},
            "quality": {"long_only": {"d1": 0.02, "d5": 0.03, "d20": 0.07}},
        },
    }
    _write_json(root / "site" / "factordata" / "factor_series.json", fs)
    return fs


def _make_transitions_jsonl(root: Path) -> None:
    """Write a valid (empty) transitions.jsonl so macro_deltas gap is not raised."""
    p = root / "data" / "macro_snapshots" / "transitions.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("", encoding="utf-8")


def _make_crossasset(root: Path) -> dict:
    """Write data/crossasset/latest.json with R6 flows block so the lobe gap is suppressed."""
    d = {
        "date": "2026-07-05",
        "regime": "mixed / no clear trend",
        "breadth": 0.1,
        "favored": ["equity_us"],
        "correlation": "converging",
        "asof": "2026-07-05",
        "flows": {
            "schema": "crossasset_flows.v1",
            "display_only": True,
            "correlation": {"verdict": "converging", "absorption_pctile": 0.55, "n_markets": 6},
            "breadth": 0.1,
            "trend_top": [{"asset": "equity_us", "trend": "up", "z": 0.5}],
            "intermarket": [{"pair": "copper_gold", "ratio": 0.22, "trend": "mid"}],
            "carry": None,
            "leadlag": {"verdict": "contemporaneous", "links": []},
            "global_liquidity": None,
            "funding_stress": None,
            "note": "display-only regime read",
        },
    }
    p = root / "data" / "crossasset" / "latest.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d))
    return d


def _full_tree(root: Path) -> tuple[dict, dict, dict, dict, dict]:
    """Build all synthetic source files; return the raw dicts for assertions.

    Extended for PR-B: writes the six new R5 macro source files plus an empty
    transitions.jsonl so test_full_composition_shape's non_contra_gaps == []
    assertion stays green.

    Extended for R6: writes data/crossasset/latest.json with a flows block so
    the cross_asset_flows lobe gap is suppressed.
    """
    _seed_synapse(root)
    ms = _make_market_state(root)
    reg = _make_regime(root)
    _make_breadth_parquet(root)
    oracle = _make_oracle_state(root)
    rs = _make_run_status(root)
    at = _make_alerts_triage(root)
    # R5 macro sources (PR-B)
    _make_transmission(root)
    _make_forex(root)
    _make_bond_health(root)
    _make_china_regime(root)
    _make_hk_regime(root)
    _make_canada_regime(root)
    _make_commodity(root)
    _make_briefing(root)
    _make_factor_series(root)
    _make_transitions_jsonl(root)
    # R6 cross-asset source
    _make_crossasset(root)
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
                 "alerts", "qi", "qi_note", "live_overlay", "gaps", "sources",
                 # R5 macro lobes (PR-B)
                 "rates_transmission", "fx_dollar", "rates_credit",
                 "global_regimes", "commodity_context", "intelligence",
                 "macro_deltas",
                 # R6 cross-asset lobe
                 "cross_asset_flows"):
        assert key in payload, f"missing top-level key: {key!r}"

    # All R5+R6 lobes carry display_only=True
    for lobe_key in ("rates_transmission", "fx_dollar", "rates_credit",
                     "global_regimes", "commodity_context", "intelligence",
                     "macro_deltas", "cross_asset_flows"):
        assert payload[lobe_key].get("display_only") is True, (
            f"{lobe_key!r} missing display_only=True"
        )

    # Envelope keys
    from engine.neuralweb.envelope import ENVELOPE_KEYS
    for k in ENVELOPE_KEYS:
        assert k in payload, f"missing envelope key: {k!r}"

    # (R5 factor_weather rotation enrichment was withdrawn at rebase — it collided
    # with the factor-intel program's RUL-NW2 canonical-artifact ruling, #1589.)

    # No gaps from a full tree (contradictions gaps are expected for optional inputs
    # not included in this fixture — filter them as they are W4 display-only)
    non_contra_gaps = [g for g in payload["gaps"] if not g.startswith("contradictions/")]
    assert non_contra_gaps == [], f"unexpected non-contradictions gaps: {non_contra_gaps}"


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


# ---------------------------------------------------------------------------
# Test 17: regime block carries sector_rs and liquidity_overlay (W1 PR2 addition)
# ---------------------------------------------------------------------------

def test_regime_block_carries_sector_rs_and_liquidity_overlay(tmp_path):
    """_compose_regime now includes sector_rs and liquidity_overlay (added W1 PR2)."""
    ms, reg, oracle, rs, at = _full_tree(tmp_path)
    payload = build_world_state(root=tmp_path, now=_NOW)

    regime = payload.get("regime")
    assert regime is not None

    # liquidity_overlay must be present in the regime block
    assert "liquidity_overlay" in regime
    assert regime["liquidity_overlay"] == "expanding"

    # sector_rs must be present and match the fixture
    assert "sector_rs" in regime
    assert isinstance(regime["sector_rs"], list)
    assert len(regime["sector_rs"]) >= 1
    assert regime["sector_rs"][0]["ticker"] == "XLK"


# ---------------------------------------------------------------------------
# Tests 18-21: RUL-NW2 — factor_weather canonical source (PR-2)
# ---------------------------------------------------------------------------

def _make_state_artifact(root: Path, factor_weather: dict | None = None, as_of: str = "2026-07-05") -> Path:
    """Write a synthetic factor_intelligence_state.json to tmp root."""
    fw = factor_weather if factor_weather is not None else {
        "style_regime": "growth",
        "style_regime_pending": None,
        "style_regime_hold_days": 12,
        "factor_leader": "momentum",
        "factor_leader_ic": 0.042,
        "etf_pulse_summary": "IWF/IWD_20d=+0.0120; QQQ/SPY_20d=+0.0085; IWM/SPY_20d=-0.0031",
        "ratio_iwf_iwd_20d": 0.012,
        "ratio_qqq_spy_20d": 0.0085,
        "ratio_iwm_spy_20d": -0.0031,
        "display_only": True,
    }
    state = {
        "schema": "neuralweb.factor_intelligence_state.v1",
        "as_of": as_of,
        "produced_at": f"{as_of}T06:00:00Z",
        "is_context_only": True,
        "display_only": True,
        "factor_weather": fw,
        "panel": None,
        "scorecard": None,
        "contradictions": None,
        "attention": None,
        "hypotheses": None,
        "latest_board_coordinates": None,
        "allowed_actions": {
            "may_rank": False,
            "may_originate": False,
            "may_deescalate": False,
            "authority_source": "constitution.grant_authority + prereg gates; this block is a mirror, never a switch",
        },
        "gaps": [],
    }
    dest = root / "data" / "neuralweb" / "factor_intelligence_state.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(state), encoding="utf-8")
    return dest


def test_rulnw2_artifact_present_lobe_from_artifact(tmp_path):
    """Test 18 (RUL-NW2a): artifact present → factor_weather block comes from artifact
    and factor_state_as_of is set to artifact's as_of.
    """
    from engine.neuralweb.world_state import _compose_factor_weather

    _make_state_artifact(tmp_path, as_of="2026-07-05")

    result = _compose_factor_weather(root=tmp_path)

    # factor_state_as_of must carry the artifact's as_of
    assert result.get("factor_state_as_of") == "2026-07-05", (
        f"expected factor_state_as_of='2026-07-05', got {result.get('factor_state_as_of')!r}"
    )

    # lobe fields come from the artifact
    assert result.get("style_regime") == "growth"
    assert result.get("factor_leader") == "momentum"
    assert abs(result.get("factor_leader_ic") - 0.042) < 1e-9

    # display_only is always True
    assert result.get("display_only") is True

    # factor_state_as_of key exists (11th key check)
    assert "factor_state_as_of" in result


def test_rulnw2_artifact_absent_fallback_path(tmp_path):
    """Test 19 (RUL-NW2b): artifact absent → legacy fallback used, factor_state_as_of null.

    No panel/ETF data in tmp_path, so all fallback fields will be null — but the
    key invariants are: no raise, factor_state_as_of is None, display_only True.
    """
    from engine.neuralweb.world_state import _compose_factor_weather

    # Artifact file is NOT created — only the directory may or may not exist.
    result = _compose_factor_weather(root=tmp_path)

    assert result.get("factor_state_as_of") is None, (
        f"expected factor_state_as_of=None on fallback, got {result.get('factor_state_as_of')!r}"
    )
    assert result.get("display_only") is True
    # Must carry all 11 keys (no raise)
    assert "style_regime" in result
    assert "factor_state_as_of" in result


def test_rulnw2_artifact_corrupt_json_fallback(tmp_path):
    """Test 20 (RUL-NW2c): artifact exists but is corrupt JSON → fallback, factor_state_as_of null.
    """
    from engine.neuralweb.world_state import _compose_factor_weather

    dest = tmp_path / "data" / "neuralweb" / "factor_intelligence_state.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("{ this is not valid JSON {{{{", encoding="utf-8")

    result = _compose_factor_weather(root=tmp_path)

    assert result.get("factor_state_as_of") is None, (
        f"expected factor_state_as_of=None on corrupt artifact, got {result.get('factor_state_as_of')!r}"
    )
    assert result.get("display_only") is True
    # No raise
    assert isinstance(result, dict)


def test_rulnw2_artifact_missing_factor_weather_block_fallback(tmp_path):
    """Test 21 (RUL-NW2d): artifact present but factor_weather key absent → fallback.

    The state artifact exists and is valid JSON, but lacks the factor_weather block
    (e.g. from a partial build run). The function must fall back to the legacy path
    and return factor_state_as_of: null.
    """
    from engine.neuralweb.world_state import _compose_factor_weather

    # Write artifact WITHOUT factor_weather key
    state_no_fw = {
        "schema": "neuralweb.factor_intelligence_state.v1",
        "as_of": "2026-07-05",
        "is_context_only": True,
        "display_only": True,
        # factor_weather intentionally omitted
        "panel": None,
        "gaps": [],
    }
    dest = tmp_path / "data" / "neuralweb" / "factor_intelligence_state.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(state_no_fw), encoding="utf-8")

    result = _compose_factor_weather(root=tmp_path)

    assert result.get("factor_state_as_of") is None, (
        f"expected factor_state_as_of=None when factor_weather block missing from artifact, "
        f"got {result.get('factor_state_as_of')!r}"
    )
    assert result.get("display_only") is True
    assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Tests 22-24: Regression tests for Opus PR-2 review findings
# ---------------------------------------------------------------------------

def test_rulnw2_prefer_artifact_false_skips_artifact(tmp_path):
    """Test 22 (RUL-NW2 freeze-regression): prefer_artifact=False bypasses the committed
    artifact and forces a fresh panel-based recompute.

    Regression for the circular-staleness freeze: _build_factor_weather_block in the
    state builder must pass prefer_artifact=False so that it never reads and re-emits
    the prior night's artifact verbatim.  This test seeds an artifact whose style_regime
    is a sentinel value ('STALE_FROZEN_VALUE'), then calls _compose_factor_weather with
    prefer_artifact=False and asserts the sentinel does NOT appear in the result — the
    function recomputed from scratch (no panel in tmp_path, so all fields are null).
    """
    from engine.neuralweb.world_state import _compose_factor_weather

    # Seed a prior-night artifact with a distinguishable sentinel value.
    stale_fw = {
        "style_regime": "STALE_FROZEN_VALUE",
        "style_regime_pending": None,
        "style_regime_hold_days": 999,
        "factor_leader": "STALE_LEADER",
        "factor_leader_ic": 0.999,
        "etf_pulse_summary": "STALE",
        "ratio_iwf_iwd_20d": 9.99,
        "ratio_qqq_spy_20d": 9.99,
        "ratio_iwm_spy_20d": 9.99,
        "display_only": True,
    }
    _make_state_artifact(tmp_path, factor_weather=stale_fw, as_of="2026-07-05")

    # With default (prefer_artifact=True) the sentinel WOULD be returned —
    # confirm that first so we know the artifact is readable.
    result_canonical = _compose_factor_weather(root=tmp_path, prefer_artifact=True)
    assert result_canonical.get("style_regime") == "STALE_FROZEN_VALUE", (
        "Positive-control failed: artifact is present but canonical path did not read it — "
        "the freeze-regression test would be vacuous.  Check _make_state_artifact."
    )

    # With prefer_artifact=False the builder path must NOT return the stale sentinel.
    result_fresh = _compose_factor_weather(root=tmp_path, prefer_artifact=False)
    assert result_fresh.get("style_regime") != "STALE_FROZEN_VALUE", (
        "FREEZE REGRESSION: prefer_artifact=False still returned the stale artifact value "
        f"(style_regime={result_fresh.get('style_regime')!r}).  The builder will freeze "
        "factor_weather at day-1 values forever."
    )
    # No panel in tmp_path → all panel-derived fields are null (fresh compute).
    assert result_fresh.get("style_regime") is None, (
        f"expected style_regime=None (no panel in tmp_path), got {result_fresh.get('style_regime')!r}"
    )
    # factor_state_as_of must be null on the fresh-compute path.
    assert result_fresh.get("factor_state_as_of") is None
    assert result_fresh.get("display_only") is True


def test_rulnw2_builder_calls_prefer_artifact_false(tmp_path):
    """Test 23 (builder integration): _build_factor_weather_block passes prefer_artifact=False.

    Verifies the builder-side fix end-to-end: even with a stale artifact on disk,
    calling _build_factor_weather_block returns a fresh (null-filled) result rather
    than the artifact's sentinel values.
    """
    import sys
    import importlib

    # Seed the stale artifact in tmp_path.
    stale_fw = {
        "style_regime": "BUILDER_STALE_SENTINEL",
        "style_regime_pending": None,
        "style_regime_hold_days": 42,
        "factor_leader": "BUILDER_STALE_LEADER",
        "factor_leader_ic": 0.777,
        "etf_pulse_summary": "STALE_ETF",
        "ratio_iwf_iwd_20d": 7.77,
        "ratio_qqq_spy_20d": 7.77,
        "ratio_iwm_spy_20d": 7.77,
        "display_only": True,
    }
    _make_state_artifact(tmp_path, factor_weather=stale_fw, as_of="2026-07-05")

    # Import the builder's private function and call it directly.
    import scripts.build_factor_intelligence_state as bfis
    gaps: list[str] = []
    result = bfis._build_factor_weather_block(tmp_path, gaps)

    assert result.get("style_regime") != "BUILDER_STALE_SENTINEL", (
        "BUILDER FREEZE REGRESSION: _build_factor_weather_block returned stale artifact "
        f"value (style_regime={result.get('style_regime')!r}).  It must pass "
        "prefer_artifact=False to _compose_factor_weather."
    )
    # No panel in tmp_path → style_regime must be null.
    assert result.get("style_regime") is None, (
        f"expected style_regime=None (no panel), got {result.get('style_regime')!r}"
    )


def test_rulnw2_artifact_display_only_false_is_coerced(tmp_path):
    """Test 24 (display_only coercion): artifact carrying display_only:False is overridden.

    world_state.py:504 forces display_only=True regardless of what the artifact carries.
    This test verifies the override is applied — an artifact with display_only:False must
    still produce display_only:True in the returned dict.
    """
    from engine.neuralweb.world_state import _compose_factor_weather

    # Seed an artifact whose factor_weather block carries display_only: False.
    fw_with_false = {
        "style_regime": "growth",
        "style_regime_pending": None,
        "style_regime_hold_days": 5,
        "factor_leader": "value",
        "factor_leader_ic": 0.031,
        "etf_pulse_summary": "IWF/IWD_20d=+0.005",
        "ratio_iwf_iwd_20d": 0.005,
        "ratio_qqq_spy_20d": 0.002,
        "ratio_iwm_spy_20d": -0.001,
        "display_only": False,  # deliberately set to False — should be coerced
    }
    _make_state_artifact(tmp_path, factor_weather=fw_with_false, as_of="2026-07-06")

    result = _compose_factor_weather(root=tmp_path, prefer_artifact=True)

    assert result.get("display_only") is True, (
        f"display_only override failed: artifact carried display_only=False but result has "
        f"display_only={result.get('display_only')!r}.  §5.4 mandates display_only always True."
    )
    # Confirm we did take the canonical path (not fallback).
    assert result.get("factor_state_as_of") == "2026-07-06"
    assert result.get("style_regime") == "growth"
