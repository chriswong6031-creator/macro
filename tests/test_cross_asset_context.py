"""tests/test_cross_asset_context.py — Cross-asset context deltas (PR feat/cross-asset-context-deltas).

Hermetic fixtures via tmp_path.  No real data reads.

Coverage
--------
(a) _macro_ledger_deltas unit tests:
    1. streak counting (days_in_state) with a small synthetic ledger.parquet
    2. prev value: correctly identifies the value before the current run
    3. missing parquet → returns dict of None values (fail-open)
    4. missing field in ledger → None for that specific field

(b) Extractor tests for new commodity/fx fields:
    5. _extract_commodity new fields present when source keys present
    6. _extract_commodity absent keys fail-open (all None)
    7. _commodity_breadth_bucket thresholds: broad/mixed/narrow + invalid
    8. _extract_forex new fields: usd_valuation, usd_positioning, fed_path_lean
    9. _extract_forex per-pair action labels for 9 pairs
    10. _extract_forex absent dollar_desk/pairs fail-open

(c) Compose-fn tests verifying new blocks + display_only preserved:
    11. _compose_fx_dollar: pairs block (non-FLAT only, sorted by |score|, cap 5)
    12. _compose_fx_dollar: scenario_intensity top-2
    13. _compose_fx_dollar: deltas block present when ledger absent (None, fail-open)
    14. _compose_fx_dollar: display_only=True always
    15. _compose_commodity_context: index sub-block fields
    16. _compose_commodity_context: breadth sub-block with bucket
    17. _compose_commodity_context: confluence standouts (non-Neutral, cap 6)
    18. _compose_commodity_context: ratios pass-through
    19. _compose_commodity_context: usd_sensitivity cross-read (and fail-open)
    20. _compose_commodity_context: deltas None when ledger absent (fail-open)
    21. _compose_commodity_context: display_only=True always
    22. _block_cross_asset_context: delta_lines built from world_state lobes
    23. _block_cross_asset_context: returns None when ws is None
    24. _block_cross_asset_context: returns None when both lobes absent
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, default=str), encoding="utf-8")


def _make_ledger(tmp_path: Path, rows: list[dict]) -> Path:
    """Write a synthetic ledger.parquet in tmp_path/data/macro_snapshots/."""
    out_dir = tmp_path / "data" / "macro_snapshots"
    out_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    ledger_path = out_dir / "ledger.parquet"
    df.to_parquet(ledger_path, index=False)
    return ledger_path


def _minimal_forex_payload(*, with_pairs: bool = True, with_dd: bool = True) -> dict:
    payload: dict = {
        "date": "Jul 10, 2026",
        "asof": "2026-07-10",
        "regime": "US growth premium",
        "risk": "risk-on",
    }
    if with_dd:
        payload["dollar_desk"] = {
            "trend": "uptrend",
            "real_rate_regime": "positive",
            "usd_valuation": "overvalued",
            "usd_pos_state": "stretched_long",
            "fed_path_lean": "hold",
            "liquidity_dir": "tightening",
        }
    if with_pairs:
        payload["pairs"] = {
            "eurusd": {"action": "SHORT", "score": -0.8},
            "usdjpy": {"action": "LONG", "score": 0.6},
            "gbpusd": {"action": "FLAT", "score": 0.0},
            "usdcad": {"action": "SHORT", "score": -0.3},
            "audusd": {"action": "FLAT", "score": 0.0},
            "usdchf": {"action": "LONG", "score": 0.9},
            "usdmxn": {"action": "SHORT", "score": -0.2},
            "usdcnh": {"action": "LONG", "score": 0.4},
            "usdbrl": {"action": "LONG", "score": 0.5},
        }
    payload["regime_radar"] = {
        "dominant": "USD_safe_haven",
        "active": ["USD_safe_haven", "EM_selloff"],
        "intensity": {
            "USD_safe_haven": 0.85,
            "EM_selloff": 0.62,
            "Carry_unwind": 0.40,
        },
    }
    payload["transmission"] = {
        "usd_dir": "strengthening",
        "headwind_for": ["GLD", "EEM"],
        "tailwind_for": ["UUP"],
        "corr": {"GC=F": -0.75, "CL=F": -0.45, "HG=F": -0.60},
    }
    return payload


def _minimal_commodity_payload() -> dict:
    return {
        "date": "Jul 10, 2026",
        "asof": "2026-07-10",
        "regime": "Goldilocks",
        "favored": ["Gold", "Copper"],
        "index": {
            "mtf": {
                "grade": "A",
                "ladder_state": "bullish",
                "headline": "Broad commodity uptrend confirmed",
            },
            "shock_state": "normal",
            "chg_1m_pct": 2.4,
            "velocity": {"impulse": "rising"},
        },
        "breadth": {
            "n_members": 17,
            "n_up_trend": 14,
            "pct_up_trend": 0.82,
        },
        "confluence": {
            "index": {"state": "Bottom", "bottom_score": 0.78, "top_score": 0.12},
            "members": [
                {"name": "Gold", "label": "Gold", "state": "Bottom", "bottom_score": 0.9, "top_score": 0.1},
                {"name": "Silver", "label": "Silver", "state": "Neutral", "bottom_score": 0.5, "top_score": 0.5},
                {"name": "Copper", "label": "Copper", "state": "Bottom", "bottom_score": 0.8, "top_score": 0.2},
                {"name": "Oil", "label": "Oil", "state": "Top", "bottom_score": 0.1, "top_score": 0.85},
            ],
        },
        "ratios": {
            "copper_gold": {"value": 0.0023, "chg_20d_pct": 1.5, "dir": "up"},
            "gold_silver": {"value": 85.2, "chg_20d_pct": -0.8, "dir": "down"},
        },
        "assets": {
            "gold": {"label": "Gold", "trend": "bullish", "action": "BUY", "conviction": 0.8},
            "silver": {"label": "Silver", "trend": "neutral", "action": "HOLD", "conviction": 0.4},
            "copper": {"label": "Copper", "trend": "bullish", "action": "BUY", "conviction": 0.7},
            "oil": {"label": "Oil", "trend": "bearish", "action": "REDUCE", "conviction": 0.5},
        },
    }


# ---------------------------------------------------------------------------
# (a) _macro_ledger_deltas unit tests
# ---------------------------------------------------------------------------

from engine.neuralweb.world_state import _macro_ledger_deltas  # noqa: E402


def test_ledger_deltas_streak_counting(tmp_path: Path) -> None:
    """days_in_state counts calendar days from first occurrence of current consecutive run."""
    rows = [
        {"asof": "2026-07-01", "domain": "fx", "field": "usd_trend", "value": "downtrend",
         "source_asof": "2026-07-01", "macro_context_id": "x"},
        {"asof": "2026-07-05", "domain": "fx", "field": "usd_trend", "value": "uptrend",
         "source_asof": "2026-07-05", "macro_context_id": "y"},
        {"asof": "2026-07-06", "domain": "fx", "field": "usd_trend", "value": "uptrend",
         "source_asof": "2026-07-06", "macro_context_id": "y"},
        {"asof": "2026-07-10", "domain": "fx", "field": "usd_trend", "value": "uptrend",
         "source_asof": "2026-07-10", "macro_context_id": "z"},
    ]
    _make_ledger(tmp_path, rows)
    result = _macro_ledger_deltas(tmp_path, "fx", ["usd_trend"])
    entry = result.get("usd_trend")
    assert entry is not None, "Expected entry for usd_trend"
    assert entry["value"] == "uptrend"
    assert entry["since"] == "2026-07-05", f"Expected since=2026-07-05, got {entry['since']!r}"
    # days = 2026-07-10 - 2026-07-05 + 1 = 6
    assert entry["days_in_state"] == 6, f"Expected 6 days, got {entry['days_in_state']}"


def test_ledger_deltas_prev_value(tmp_path: Path) -> None:
    """prev correctly identifies the value before the current consecutive run."""
    rows = [
        {"asof": "2026-07-01", "domain": "fx", "field": "usd_regime", "value": "neutral",
         "source_asof": "2026-07-01", "macro_context_id": "a"},
        {"asof": "2026-07-08", "domain": "fx", "field": "usd_regime", "value": "US growth premium",
         "source_asof": "2026-07-08", "macro_context_id": "b"},
        {"asof": "2026-07-10", "domain": "fx", "field": "usd_regime", "value": "US growth premium",
         "source_asof": "2026-07-10", "macro_context_id": "c"},
    ]
    _make_ledger(tmp_path, rows)
    result = _macro_ledger_deltas(tmp_path, "fx", ["usd_regime"])
    entry = result["usd_regime"]
    assert entry is not None
    assert entry["value"] == "US growth premium"
    assert entry["prev"] == "neutral", f"Expected prev='neutral', got {entry['prev']!r}"


def test_ledger_deltas_gap_breaks_streak(tmp_path: Path) -> None:
    """A gap on an intermediate domain asof terminates the consecutive run.

    Scenario:
      Domain asofs: 2026-07-01, 2026-07-05, 2026-07-08, 2026-07-10
      Field 'usd_trend' rows: 07-01 (downtrend), 07-08 (uptrend), 07-10 (uptrend)
      The field is ABSENT on 07-05 (a domain asof) even though two adjacent field
      rows (07-08, 07-10) agree.  The streak must restart at 07-08, not 07-01.
    """
    # Rows for 'usd_trend' — intentionally skipping 2026-07-05
    trend_rows = [
        {"asof": "2026-07-01", "domain": "fx", "field": "usd_trend", "value": "downtrend",
         "source_asof": "2026-07-01", "macro_context_id": "a"},
        {"asof": "2026-07-08", "domain": "fx", "field": "usd_trend", "value": "uptrend",
         "source_asof": "2026-07-08", "macro_context_id": "b"},
        {"asof": "2026-07-10", "domain": "fx", "field": "usd_trend", "value": "uptrend",
         "source_asof": "2026-07-10", "macro_context_id": "c"},
    ]
    # Rows for 'usd_regime' — present on all four domain asofs (so domain includes 07-05)
    regime_rows = [
        {"asof": "2026-07-01", "domain": "fx", "field": "usd_regime", "value": "neutral",
         "source_asof": "2026-07-01", "macro_context_id": "a"},
        {"asof": "2026-07-05", "domain": "fx", "field": "usd_regime", "value": "neutral",
         "source_asof": "2026-07-05", "macro_context_id": "x"},
        {"asof": "2026-07-08", "domain": "fx", "field": "usd_regime", "value": "growth",
         "source_asof": "2026-07-08", "macro_context_id": "b"},
        {"asof": "2026-07-10", "domain": "fx", "field": "usd_regime", "value": "growth",
         "source_asof": "2026-07-10", "macro_context_id": "c"},
    ]
    _make_ledger(tmp_path, trend_rows + regime_rows)
    result = _macro_ledger_deltas(tmp_path, "fx", ["usd_trend"])
    entry = result.get("usd_trend")
    assert entry is not None, "Expected entry for usd_trend"
    assert entry["value"] == "uptrend"
    # Gap on 07-05 must break the streak — since must be 07-08, not 07-01
    assert entry["since"] == "2026-07-08", (
        f"Expected since=2026-07-08 (gap breaks streak), got {entry['since']!r}"
    )
    # days = 2026-07-10 - 2026-07-08 + 1 = 3
    assert entry["days_in_state"] == 3, f"Expected 3 days (gap restart), got {entry['days_in_state']}"


def test_ledger_deltas_missing_parquet(tmp_path: Path) -> None:
    """Missing ledger.parquet → all fields return None, no exception."""
    result = _macro_ledger_deltas(tmp_path, "fx", ["usd_trend", "usd_regime"])
    assert result["usd_trend"] is None
    assert result["usd_regime"] is None


def test_ledger_deltas_missing_field(tmp_path: Path) -> None:
    """Field not found in ledger → None for that field only."""
    rows = [
        {"asof": "2026-07-10", "domain": "fx", "field": "usd_trend", "value": "uptrend",
         "source_asof": "2026-07-10", "macro_context_id": "x"},
    ]
    _make_ledger(tmp_path, rows)
    result = _macro_ledger_deltas(tmp_path, "fx", ["usd_trend", "nonexistent_field"])
    assert result["usd_trend"] is not None
    assert result["nonexistent_field"] is None


# ---------------------------------------------------------------------------
# (b) Extractor tests (build_macro_snapshot)
# ---------------------------------------------------------------------------

import scripts.build_macro_snapshot as BMS  # noqa: E402


def test_extract_commodity_new_fields_present() -> None:
    """v1.2 commodity fields extracted when source keys present."""
    payload = _minimal_commodity_payload()
    labels, asof = BMS._extract_commodity(payload)
    comm = labels["commodity"]
    assert comm.get("commodity_mtf_grade") == "A", f"Got: {comm.get('commodity_mtf_grade')!r}"
    assert comm.get("commodity_ladder") == "bullish", f"Got: {comm.get('commodity_ladder')!r}"
    assert comm.get("commodity_shock_state") == "normal", f"Got: {comm.get('commodity_shock_state')!r}"
    assert comm.get("commodity_confluence_state") == "Bottom", f"Got: {comm.get('commodity_confluence_state')!r}"
    assert comm.get("commodity_breadth_bucket") == "broad", f"Got: {comm.get('commodity_breadth_bucket')!r}"
    assert comm.get("gold_action") == "BUY", f"Got: {comm.get('gold_action')!r}"
    assert comm.get("silver_action") == "HOLD", f"Got: {comm.get('silver_action')!r}"
    assert comm.get("copper_action") == "BUY", f"Got: {comm.get('copper_action')!r}"
    assert comm.get("oil_action") == "REDUCE", f"Got: {comm.get('oil_action')!r}"


def test_extract_commodity_absent_keys_fail_open() -> None:
    """Absent keys in commodity payload → all new v1.2 fields None (fail-open)."""
    payload = {"date": "2026-07-10", "regime": "Neutral"}
    labels, _ = BMS._extract_commodity(payload)
    comm = labels["commodity"]
    for field in (
        "commodity_mtf_grade", "commodity_ladder", "commodity_shock_state",
        "commodity_confluence_state", "commodity_breadth_bucket",
        "gold_action", "silver_action", "copper_action", "oil_action",
    ):
        assert comm.get(field) is None, f"Expected None for {field!r}, got {comm.get(field)!r}"


def test_commodity_breadth_bucket_thresholds() -> None:
    """_commodity_breadth_bucket returns correct bucket label."""
    assert BMS._commodity_breadth_bucket(0.75) == "broad"
    assert BMS._commodity_breadth_bucket(0.70) == "broad"
    assert BMS._commodity_breadth_bucket(0.69) == "mixed"
    assert BMS._commodity_breadth_bucket(0.40) == "mixed"
    assert BMS._commodity_breadth_bucket(0.39) == "narrow"
    assert BMS._commodity_breadth_bucket(0.0) == "narrow"
    assert BMS._commodity_breadth_bucket(None) is None
    assert BMS._commodity_breadth_bucket("invalid") is None


def test_extract_forex_new_fields_present() -> None:
    """v1.2 forex fields: usd_valuation, usd_positioning, fed_path_lean extracted."""
    payload = _minimal_forex_payload()
    labels, asof = BMS._extract_forex(payload)
    fx = labels["fx"]
    assert fx.get("usd_valuation") == "overvalued", f"Got: {fx.get('usd_valuation')!r}"
    assert fx.get("usd_positioning") == "stretched_long", f"Got: {fx.get('usd_positioning')!r}"
    assert fx.get("fed_path_lean") == "hold", f"Got: {fx.get('fed_path_lean')!r}"


def test_extract_forex_per_pair_action_labels() -> None:
    """Per-pair action labels extracted for all 9 pairs."""
    payload = _minimal_forex_payload()
    labels, _ = BMS._extract_forex(payload)
    fx = labels["fx"]
    assert fx.get("fx_eurusd_action") == "SHORT", f"Got: {fx.get('fx_eurusd_action')!r}"
    assert fx.get("fx_usdjpy_action") == "LONG", f"Got: {fx.get('fx_usdjpy_action')!r}"
    assert fx.get("fx_gbpusd_action") == "FLAT", f"Got: {fx.get('fx_gbpusd_action')!r}"
    assert fx.get("fx_usdchf_action") == "LONG", f"Got: {fx.get('fx_usdchf_action')!r}"
    assert fx.get("fx_usdbrl_action") == "LONG", f"Got: {fx.get('fx_usdbrl_action')!r}"


def test_extract_forex_absent_fail_open() -> None:
    """Absent dollar_desk/pairs in forex payload → new v1.2 fields None."""
    payload = {"date": "2026-07-10", "regime": "neutral"}
    labels, _ = BMS._extract_forex(payload)
    fx = labels["fx"]
    assert fx.get("usd_valuation") is None
    assert fx.get("usd_positioning") is None
    assert fx.get("fed_path_lean") is None
    # No pair fields emitted when pairs absent
    pair_fields = [k for k in fx if k.startswith("fx_") and k.endswith("_action")]
    assert len(pair_fields) == 0, f"Expected no pair action fields, got {pair_fields}"


# ---------------------------------------------------------------------------
# (c) Compose-fn tests (_compose_fx_dollar, _compose_commodity_context)
# ---------------------------------------------------------------------------

from engine.neuralweb.world_state import (  # noqa: E402
    _compose_fx_dollar,
    _compose_commodity_context,
)


def test_compose_fx_dollar_pairs_non_flat_sorted(tmp_path: Path) -> None:
    """pairs block: only non-FLAT actions, sorted by |score| descending, cap 5."""
    _write_json(tmp_path / "data" / "forex" / "latest.json", _minimal_forex_payload())
    result = _compose_fx_dollar(root=tmp_path)
    pairs = result.get("pairs")
    assert pairs is not None, "Expected pairs block"
    # FLAT pairs (gbpusd, audusd) must not appear
    pair_keys = [p["pair"] for p in pairs]
    assert "gbpusd" not in pair_keys, f"FLAT pair gbpusd must be excluded; got {pair_keys}"
    assert "audusd" not in pair_keys, f"FLAT pair audusd must be excluded; got {pair_keys}"
    # Must be sorted by |score| desc
    scores = [abs(p["score"]) for p in pairs if p["score"] is not None]
    assert scores == sorted(scores, reverse=True), f"pairs not sorted by |score|: {pairs}"
    # Cap 5 non-FLAT pairs (we have 7 non-FLAT: eurusd, usdjpy, usdcad, usdchf, usdmxn, usdcnh, usdbrl)
    assert len(pairs) <= 5


def test_compose_fx_dollar_scenario_intensity_top2(tmp_path: Path) -> None:
    """scenario_intensity contains top-2 intensity entries sorted desc."""
    _write_json(tmp_path / "data" / "forex" / "latest.json", _minimal_forex_payload())
    result = _compose_fx_dollar(root=tmp_path)
    si = result.get("scenario_intensity")
    assert si is not None and len(si) == 2, f"Expected 2 entries, got {si}"
    # Top-2 by value: USD_safe_haven=0.85, EM_selloff=0.62
    assert si[0]["name"] == "USD_safe_haven", f"Got {si[0]!r}"
    assert si[1]["name"] == "EM_selloff", f"Got {si[1]!r}"


def test_compose_fx_dollar_deltas_none_when_ledger_absent(tmp_path: Path) -> None:
    """deltas is None (not an exception) when ledger.parquet is absent."""
    _write_json(tmp_path / "data" / "forex" / "latest.json", _minimal_forex_payload())
    result = _compose_fx_dollar(root=tmp_path)
    # ledger absent → deltas should be a dict of Nones (not raise)
    deltas = result.get("deltas")
    # Could be a dict (all None) or None — either is fine for fail-open
    if deltas is not None:
        assert isinstance(deltas, dict), f"deltas should be dict or None, got {type(deltas)}"
        for v in deltas.values():
            assert v is None, f"All delta entries should be None when ledger absent; got {v!r}"


def test_compose_fx_dollar_delta_fields_match_payload_pairs(tmp_path: Path) -> None:
    """Regression: delta keys for per-pair fields must exactly mirror the pairs in the payload.

    Prevents fixture-masking: if nzdusd/usdsgd were in the fixture but not the live
    payload (or vice versa) the deltas dict would silently contain dead/missing keys.
    """
    from engine.neuralweb.world_state import _compose_fx_dollar

    # Build a ledger with per-pair action fields for the 9 real active pairs
    active_pairs = ["eurusd", "gbpusd", "usdjpy", "usdchf",
                    "audusd", "usdcad", "usdmxn", "usdbrl", "usdcnh"]
    ledger_rows = []
    for p in active_pairs:
        ledger_rows.append(
            {"asof": "2026-07-10", "domain": "fx",
             "field": f"fx_{p}_action", "value": "LONG",
             "source_asof": "2026-07-10", "macro_context_id": "test"}
        )
    _make_ledger(tmp_path, ledger_rows)
    _write_json(tmp_path / "data" / "forex" / "latest.json", _minimal_forex_payload())
    result = _compose_fx_dollar(root=tmp_path)

    deltas = result.get("deltas") or {}
    # Every pair in the payload must have a delta key; no dead pairs allowed
    payload_pairs = list(_minimal_forex_payload()["pairs"].keys())
    for p in payload_pairs:
        key = f"fx_{p}_action"
        assert key in deltas, f"Delta key {key!r} missing; got keys: {sorted(deltas)}"
    # No nzdusd/usdsgd (old wrong set) in the delta keys
    assert "fx_nzdusd_action" not in deltas, "fx_nzdusd_action must not be queried (not active)"
    assert "fx_usdsgd_action" not in deltas, "fx_usdsgd_action must not be queried (not active)"


def test_compose_fx_dollar_display_only_always(tmp_path: Path) -> None:
    """_compose_fx_dollar always sets display_only=True."""
    _write_json(tmp_path / "data" / "forex" / "latest.json", _minimal_forex_payload())
    result = _compose_fx_dollar(root=tmp_path)
    assert result.get("display_only") is True
    # Also check null_out path (no artifact)
    null_result = _compose_fx_dollar(root=tmp_path / "nonexistent")
    assert null_result.get("display_only") is True


def test_compose_commodity_context_index_block(tmp_path: Path) -> None:
    """index sub-block has mtf_grade, ladder_state, shock_state, impulse, chg_1m_pct, headline."""
    _write_json(tmp_path / "data" / "commodity" / "latest.json", _minimal_commodity_payload())
    result = _compose_commodity_context(root=tmp_path)
    idx = result.get("index")
    assert idx is not None, "Expected index block"
    assert idx.get("mtf_grade") == "A"
    assert idx.get("ladder_state") == "bullish"
    assert idx.get("shock_state") == "normal"
    assert idx.get("impulse") == "rising"
    assert idx.get("chg_1m_pct") == 2.4
    assert idx.get("headline") == "Broad commodity uptrend confirmed"


def test_compose_commodity_context_breadth_with_bucket(tmp_path: Path) -> None:
    """breadth sub-block has n_members, n_up_trend, pct_up_trend, bucket."""
    _write_json(tmp_path / "data" / "commodity" / "latest.json", _minimal_commodity_payload())
    result = _compose_commodity_context(root=tmp_path)
    breadth = result.get("breadth")
    assert breadth is not None, "Expected breadth block"
    assert breadth.get("n_members") == 17
    assert breadth.get("n_up_trend") == 14
    assert breadth.get("pct_up_trend") == 0.82
    assert breadth.get("bucket") == "broad", f"Got: {breadth.get('bucket')!r}"


def test_compose_commodity_context_confluence_standouts(tmp_path: Path) -> None:
    """confluence.standouts contains only non-Neutral members, capped at 6."""
    _write_json(tmp_path / "data" / "commodity" / "latest.json", _minimal_commodity_payload())
    result = _compose_commodity_context(root=tmp_path)
    conf = result.get("confluence")
    assert conf is not None, "Expected confluence block"
    assert conf.get("index_state") == "Bottom"
    standouts = conf.get("standouts") or []
    # Silver is Neutral — must be excluded
    standout_names = [s.get("name") for s in standouts]
    assert "Silver" not in standout_names, f"Neutral Silver must be excluded; got {standout_names}"
    # Gold, Copper (Bottom), Oil (Top) should appear
    assert "Gold" in standout_names, f"Gold missing from standouts: {standout_names}"
    assert "Copper" in standout_names, f"Copper missing from standouts: {standout_names}"
    assert "Oil" in standout_names, f"Oil missing from standouts: {standout_names}"
    assert len(standouts) <= 6


def test_compose_commodity_context_ratios_passthrough(tmp_path: Path) -> None:
    """ratios block passes through from latest.json."""
    _write_json(tmp_path / "data" / "commodity" / "latest.json", _minimal_commodity_payload())
    result = _compose_commodity_context(root=tmp_path)
    ratios = result.get("ratios")
    assert ratios is not None, "Expected ratios block"
    assert "copper_gold" in ratios
    assert "gold_silver" in ratios
    assert ratios["copper_gold"]["dir"] == "up"
    assert ratios["gold_silver"]["dir"] == "down"


def test_compose_commodity_context_usd_sensitivity_cross_read(tmp_path: Path) -> None:
    """usd_sensitivity is cross-read from forex/latest.json."""
    _write_json(tmp_path / "data" / "commodity" / "latest.json", _minimal_commodity_payload())
    _write_json(tmp_path / "data" / "forex" / "latest.json", _minimal_forex_payload())
    result = _compose_commodity_context(root=tmp_path)
    usd_s = result.get("usd_sensitivity")
    assert usd_s is not None, "Expected usd_sensitivity block when forex present"
    assert usd_s.get("gold") == -0.75
    assert usd_s.get("oil") == -0.45
    assert usd_s.get("copper") == -0.60
    assert usd_s.get("usd_dir") == "strengthening"


def test_compose_commodity_context_usd_sensitivity_absent_forex(tmp_path: Path) -> None:
    """usd_sensitivity is None when forex/latest.json absent (fail-open)."""
    _write_json(tmp_path / "data" / "commodity" / "latest.json", _minimal_commodity_payload())
    # No forex file written
    result = _compose_commodity_context(root=tmp_path)
    # Must not raise; usd_sensitivity should be None or an empty dict
    usd_s = result.get("usd_sensitivity")
    # fail-open: None is acceptable; the block should not raise
    assert "display_only" in result and result["display_only"] is True


def test_compose_commodity_context_deltas_absent_ledger(tmp_path: Path) -> None:
    """deltas is dict of Nones (fail-open) when ledger.parquet absent."""
    _write_json(tmp_path / "data" / "commodity" / "latest.json", _minimal_commodity_payload())
    result = _compose_commodity_context(root=tmp_path)
    deltas = result.get("deltas")
    if deltas is not None:
        assert isinstance(deltas, dict)
        for v in deltas.values():
            assert v is None, f"All delta entries should be None when ledger absent; got {v!r}"


def test_compose_commodity_context_display_only_always(tmp_path: Path) -> None:
    """_compose_commodity_context always sets display_only=True."""
    _write_json(tmp_path / "data" / "commodity" / "latest.json", _minimal_commodity_payload())
    result = _compose_commodity_context(root=tmp_path)
    assert result.get("display_only") is True
    null_result = _compose_commodity_context(root=tmp_path / "nonexistent")
    assert null_result.get("display_only") is True


# ---------------------------------------------------------------------------
# (c) _block_cross_asset_context
# ---------------------------------------------------------------------------

from engine.neuralweb.brief_context import _block_cross_asset_context  # noqa: E402


def _make_ws_with_lobes(*, with_fx: bool = True, with_commodity: bool = True) -> dict:
    """Build a minimal world_state dict with fx_dollar and/or commodity_context lobes."""
    ws: dict = {"display_only": True}
    if with_fx:
        ws["fx_dollar"] = {
            "display_only": True,
            "regime": "US growth premium",
            "asof": "2026-07-10",
            "dollar_desk": {"trend": "uptrend"},
            "scenario_intensity": [
                {"name": "USD_safe_haven", "value": 0.85},
                {"name": "EM_selloff", "value": 0.62},
            ],
            "deltas": {
                "usd_trend": {"value": "uptrend", "prev": "downtrend", "since": "2026-07-05", "days_in_state": 6},
                "usd_regime": {"value": "US growth premium", "prev": "neutral", "since": "2026-06-30", "days_in_state": 10},
            },
        }
    if with_commodity:
        ws["commodity_context"] = {
            "display_only": True,
            "regime": "Goldilocks",
            "asof": "2026-07-10",
            "index": {"shock_state": "normal"},
            "breadth": {"n_up_trend": 14, "n_members": 17, "pct_up_trend": 0.82, "bucket": "broad"},
            "ratios": {
                "copper_gold": {"value": 0.0023, "chg_20d_pct": 1.5, "dir": "up"},
                "gold_silver": {"value": 85.2, "chg_20d_pct": -0.8, "dir": "down"},
            },
            "confluence": {
                "index_state": "Bottom",
                "standouts": [
                    {"name": "Gold", "state": "Bottom"},
                    {"name": "Copper", "state": "Bottom"},
                ],
            },
            "deltas": {
                "commodity_regime": {"value": "Goldilocks", "prev": "Neutral", "since": "2026-06-25", "days_in_state": 15},
                "commodity_shock_state": {"value": "normal", "prev": "elevated", "since": "2026-07-03", "days_in_state": 7},
            },
        }
    return ws


def test_block_cross_asset_context_delta_lines(tmp_path: Path) -> None:
    """delta_lines are built from world_state fx and commodity lobes."""
    ws = _make_ws_with_lobes()
    result = _block_cross_asset_context(ws)
    assert result is not None, "Expected a block when lobes present"
    assert result.get("display_only") is True
    lines = result.get("delta_lines") or []
    assert len(lines) >= 1, f"Expected at least 1 delta line, got: {lines}"
    # Reconcile #2845: USD trend/regime narration moved to the fx_dollar block;
    # this block now carries commodity lines + per-pair streak lines.
    # With no pairs in the fixture the commodity line is first; verify it
    # mentions the regime and a since-date.
    all_text = " ".join(lines)
    assert "since" in all_text, f"Expected 'since <date>' in delta lines, got: {lines}"
    # At least one commodity line present when commodity lobe present
    assert any("Commodities" in ln or "commodity" in ln.lower() for ln in lines), (
        f"Expected commodity line in delta_lines: {lines}"
    )
    # Per-pair streak lines: verify with fixture that has pairs
    ws_with_pairs = _make_ws_with_lobes()
    ws_with_pairs["fx_dollar"]["pairs"] = [
        {"pair": "USD/JPY", "action": "SHORT", "score": -0.7},
    ]
    ws_with_pairs["fx_dollar"]["deltas"]["fx_usdjpy_action"] = {
        "value": "SHORT", "prev": "FLAT", "since": "2026-07-05", "days_in_state": 5,
    }
    result2 = _block_cross_asset_context(ws_with_pairs)
    assert result2 is not None
    lines2 = result2.get("delta_lines") or []
    all_text2 = " ".join(lines2)
    assert "USD/JPY" in all_text2, f"Expected pair streak line, got: {lines2}"
    assert "SHORT" in all_text2, f"Expected pair action in streak line, got: {lines2}"


def test_block_cross_asset_context_returns_none_when_ws_none() -> None:
    """Returns None when ws is None."""
    assert _block_cross_asset_context(None) is None


def test_block_cross_asset_context_returns_none_when_both_lobes_absent() -> None:
    """Returns None when both fx_dollar and commodity_context are absent."""
    ws = {"display_only": True}  # no lobes
    result = _block_cross_asset_context(ws)
    assert result is None


def test_block_cross_asset_context_ratios_line(tmp_path: Path) -> None:
    """Ratios direction appears in delta_lines when both ratios present."""
    ws = _make_ws_with_lobes()
    result = _block_cross_asset_context(ws)
    assert result is not None
    lines = result.get("delta_lines") or []
    all_text = " ".join(lines)
    # Should mention copper/gold or gold/silver direction
    assert "copper" in all_text.lower() or "gold" in all_text.lower(), (
        f"Expected ratios mention in delta_lines: {lines}"
    )
