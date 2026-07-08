"""Tests for W6 — china_market_state.v1 spine.

All tests use synthetic fixtures; no live data stores are loaded.

Coverage:
  1. Schema keys and authority contract
  2. Fully-populated packet (all lobes present)
  3. All-absent lobes → graceful null degradation + data_gaps
  4. Phase block absent (W3 parallel build scenario)
  5. Cross-lobe contradiction detection (each rule)
  6. Builder script validate() function
  7. JSON serialisability of the assembled packet
  8. Smoke run with live stores (if present; skips gracefully when absent)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Ensure repo root is importable
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from engine.china_market_state import (
    SCHEMA,
    _AUTHORITY,
    _build_allocation_block,
    _build_external_block,
    _build_macro_block,
    _build_microstructure_block,
    _build_participation_block,
    _build_phase_block,
    _build_policy_block,
    _build_rotation_block,
    _compute_contradictions,
    _compute_evidence,
    _collect_falsifiers,
    build,
)
from scripts.build_china_market_state import _validate

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_REQUIRED_KEYS = {
    "schema", "as_of", "generated_utc", "authority",
    "phase", "participation", "microstructure", "policy",
    "rotation", "macro", "external", "allocation",
    "evidence", "contradictions", "falsifiers", "data_gaps",
}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh)


def _make_participation_json(tmp_path: Path) -> Path:
    p = tmp_path / "site" / "chinastatedata" / "participation.json"
    _write_json(p, {
        "date": "2026-07-07",
        "regime": "institutional_accumulation",
        "who_controls": "institutional",
        "risk": "normal",
        "turnover_z20": 0.3,
        "turnover_z60": -0.1,
        "margin_balance": 15000.0,
        "margin_chg_5d": 0.5,
        "margin_to_mcap": 2.1,
        "zt_breadth": 0.8,
        "failed_seal_ratio": 0.15,
        "southbound_net": 3500.0,
        "southbound_z": 1.2,
        "qvix": 18.5,
        "qvix_z": -0.4,
        "etf_share_chg": None,
        "broker_rs": 0.02,
        "evidence": ["turnover_z20 stable", "southbound positive"],
        "contradictions": [],
        "data_gaps": [],
        "backfill": False,
        "snapshot_note": "test",
        "authority": {"tier": "context_only"},
    })
    return p


def _make_microstructure_json(tmp_path: Path) -> Path:
    p = tmp_path / "site" / "chinastatedata" / "microstructure.json"
    _write_json(p, {
        "as_of": "2026-07-07",
        "generated_utc": "2026-07-08T10:00:00Z",
        "authority": {"tier": "context_only", "source": "W1_microstructure"},
        "latest_aggregate": {
            "date": "2026-07-07",
            "limit_up_count": 42,
            "limit_down_count": 5,
            "sealed_up_close": 35,
            "failed_up_seal_count": 7,
            "lianban_2plus": 8,
            "lianban_max": 3,
            "universe_n": 5200,
            "st_excluded_counts": 20,
            "limit_up_breadth_pct": 0.81,
            "limit_down_breadth_pct": 0.10,
            "backfill": False,
        },
        "name_packets": [
            {
                "ticker": "600267.SS",
                "board": "main",
                "limit_width": 10.0,
                "limit_state": "open",
                "fillable": True,
                "t_plus_one_risk": "normal",
                "chase_veto": {"flag": False, "reason": None},
            },
            {
                "ticker": "002271.SZ",
                "board": "main",
                "limit_width": 10.0,
                "limit_state": "sealed_up",
                "fillable": False,
                "t_plus_one_risk": "high",
                "chase_veto": {"flag": True, "reason": "sealed limit-up"},
            },
        ],
        "data_gaps": [],
        "metadata": {"st_flags_current_only": True, "st_flags_note": "test", "backfill_version": "1.0"},
    })
    return p


def _make_policy_json(tmp_path: Path) -> Path:
    p = tmp_path / "site" / "chinastatedata" / "policy_transmission.json"
    _write_json(p, {
        "schema": "china_policy_transmission.v1",
        "authority": {"tier": "context_only", "may_originate": False, "may_escalate": False},
        "built": "2026-07-08T09:00:00Z",
        "asof": "2026-07-08",
        "policy_impulse": "targeted_support",
        "transmission_channel": ["fiscal_or_structural", "liquidity"],
        "recent_events": [
            {"source": "csrc", "kind": "capital_market", "title": "Test event 1", "ts": "2026-06-01"},
        ],
        "staleness": {"per_source_days": {"lpr": 10, "rrr": 30}},
        "priced_in_check": {},
        "data_gaps": [],
    })
    return p


def _make_phase_json(tmp_path: Path) -> Path:
    p = tmp_path / "site" / "chinastatedata" / "cycle_phase.json"
    _write_json(p, {
        "schema": "china_cycle_phase.v1",
        "date": "2026-07-07",
        "as_of": "2026-07-07",
        "phase": "LIQUIDITY_IGNITION",
        "confidence": 0.75,
        "evidence": ["turnover expanding", "policy easing"],
        "contradictions": [],
        "falsifiers": [
            {"id": "F1", "expr": "cn_10y < 1.5", "horizon_d": 20},
        ],
        "data_gaps": [],
        "backfill": False,
    })
    return p


def _make_regime_json(tmp_path: Path) -> Path:
    p = tmp_path / "data" / "china_regime" / "latest.json"
    _write_json(p, {
        "date": "2026-07-07",
        "quad": "Q3",
        "quad_name": "Stagflation",
        "growth_score": -0.3,
        "inflation_score": 0.2,
        "liquidity_overlay": "neutral",
        "cycle_tag": "mid",
        "pending_quad": "Q2",
        "pending_days": 3,
        "confirming": ["growth_indpro_trend"],
        "contradicting": ["inflation_inflation_beta_basket"],
        "conditions": {
            "roro": "risk_off",
            "recession": False,
            "drawdown_risk": "low",
        },
        "alerts": [],
    })
    return p


def _make_alloc_json(tmp_path: Path) -> Path:
    p = tmp_path / "data" / "china_regime" / "china_alloc_latest.json"
    _write_json(p, {
        "date": "2026-07-07",
        "variant": "balanced",
        "label_en": "Balanced",
        "label_zh": "均衡",
        "growth_w": 35,
        "defensive_w": 65,
        "band": "elevated",
    })
    return p


# ---------------------------------------------------------------------------
# 1. Schema keys and authority
# ---------------------------------------------------------------------------

def test_schema_constant():
    assert SCHEMA == "china_market_state.v1"


def test_authority_tier():
    assert _AUTHORITY["tier"] == "context_only"
    assert "rank" in _AUTHORITY["cannot_do"]
    assert "size" in _AUTHORITY["cannot_do"]
    assert "gate" in _AUTHORITY["cannot_do"]
    assert "originate" in _AUTHORITY["cannot_do"]


# ---------------------------------------------------------------------------
# 2. Full build with all lobes present
# ---------------------------------------------------------------------------

def test_full_build_with_all_lobes(tmp_path):
    """Fully-populated packet has all required keys and non-null lobes."""
    _make_participation_json(tmp_path)
    _make_microstructure_json(tmp_path)
    _make_policy_json(tmp_path)
    _make_phase_json(tmp_path)
    _make_regime_json(tmp_path)
    _make_alloc_json(tmp_path)

    packet = build(tmp_path)

    # All top-level keys present
    assert _REQUIRED_KEYS <= set(packet.keys()), (
        f"Missing keys: {_REQUIRED_KEYS - set(packet.keys())}"
    )

    # Core lobes present
    assert packet["participation"] is not None
    assert packet["microstructure"] is not None
    assert packet["policy"] is not None
    assert packet["phase"] is not None
    assert packet["macro"] is not None
    assert packet["allocation"] is not None

    # Authority
    assert packet["authority"]["tier"] == "context_only"

    # Schema
    assert packet["schema"] == "china_market_state.v1"

    # Lists
    assert isinstance(packet["evidence"], list)
    assert isinstance(packet["contradictions"], list)
    assert isinstance(packet["falsifiers"], list)
    assert isinstance(packet["data_gaps"], list)


def test_full_build_passes_validation(tmp_path):
    _make_participation_json(tmp_path)
    _make_microstructure_json(tmp_path)
    _make_policy_json(tmp_path)
    _make_phase_json(tmp_path)
    _make_regime_json(tmp_path)
    _make_alloc_json(tmp_path)

    packet = build(tmp_path)
    failures = _validate(packet)
    assert not failures, f"Validation failures: {failures}"


# ---------------------------------------------------------------------------
# 3. All absent lobes → graceful null degradation + data_gaps
# ---------------------------------------------------------------------------

def test_all_absent_lobes_degrades_gracefully(tmp_path):
    """When no lobe artifacts exist, all blocks null, data_gaps populated."""
    # Ensure clean tmp_path (no artifacts)
    packet = build(tmp_path)

    assert packet["schema"] == "china_market_state.v1"
    # All nullable lobes should be None
    for lobe in ["phase", "participation", "microstructure", "policy",
                 "macro", "allocation"]:
        assert packet[lobe] is None, f"Expected {lobe}=None, got {packet[lobe]}"
    # data_gaps must be populated
    assert len(packet["data_gaps"]) > 0, "Expected data_gaps entries for absent lobes"
    # Should not raise; must still pass validation
    failures = _validate(packet)
    assert not failures, f"Validation failures on null build: {failures}"


# ---------------------------------------------------------------------------
# 4. Phase block absent (W3 parallel build scenario)
# ---------------------------------------------------------------------------

def test_phase_absent_other_lobes_present(tmp_path):
    """When cycle_phase.json is missing, phase=None but other lobes still load."""
    _make_participation_json(tmp_path)
    _make_policy_json(tmp_path)
    _make_regime_json(tmp_path)
    _make_alloc_json(tmp_path)
    # Do NOT write phase json

    packet = build(tmp_path)
    assert packet["phase"] is None
    assert packet["participation"] is not None
    assert packet["macro"] is not None
    assert any("phase" in g for g in packet["data_gaps"])
    failures = _validate(packet)
    assert not failures


# ---------------------------------------------------------------------------
# 5. Phase block present and absent — fixture coverage requirement
# ---------------------------------------------------------------------------

def test_phase_present_and_absent_fixtures(tmp_path):
    """Explicitly verify both present and absent phase scenarios."""
    site_cn = tmp_path / "site" / "chinastatedata"

    # Absent
    block_absent, gaps_absent = _build_phase_block(site_cn)
    assert block_absent is None
    assert len(gaps_absent) > 0

    # Present
    _make_phase_json(tmp_path)
    block_present, gaps_present = _build_phase_block(site_cn)
    assert block_present is not None
    assert block_present["phase"] == "LIQUIDITY_IGNITION"
    assert isinstance(block_present["falsifiers"], list)


# ---------------------------------------------------------------------------
# 6. Participation block field coverage
# ---------------------------------------------------------------------------

def test_participation_block_fields(tmp_path):
    _make_participation_json(tmp_path)
    site_cn = tmp_path / "site" / "chinastatedata"
    block, gaps = _build_participation_block(site_cn)
    assert block is not None
    assert block["regime"] == "institutional_accumulation"
    assert block["who_controls"] == "institutional"
    assert block["risk"] == "normal"
    assert block["turnover_z20"] == pytest.approx(0.3)
    assert block["zt_breadth"] == pytest.approx(0.8)
    assert gaps == []


# ---------------------------------------------------------------------------
# 7. Microstructure block — aggregate + name_summary
# ---------------------------------------------------------------------------

def test_microstructure_block_fields(tmp_path):
    _make_microstructure_json(tmp_path)
    site_cn = tmp_path / "site" / "chinastatedata"
    block, gaps = _build_microstructure_block(site_cn)
    assert block is not None
    agg = block["aggregate"]
    assert agg["limit_up_count"] == 42
    assert agg["limit_down_count"] == 5
    ns = block["name_summary"]
    assert ns["n_packets"] == 2
    assert ns["chase_veto_count"] == 1  # one name has chase_veto.flag=True
    assert ns["fillable_count"] == 1    # one name is fillable
    assert "names_ref" in block
    assert gaps == []


# ---------------------------------------------------------------------------
# 8. Microstructure absent
# ---------------------------------------------------------------------------

def test_microstructure_absent(tmp_path):
    site_cn = tmp_path / "site" / "chinastatedata"
    block, gaps = _build_microstructure_block(site_cn)
    assert block is None
    assert any("microstructure" in g for g in gaps)


# ---------------------------------------------------------------------------
# 9. Policy block fields
# ---------------------------------------------------------------------------

def test_policy_block_fields(tmp_path):
    _make_policy_json(tmp_path)
    site_cn = tmp_path / "site" / "chinastatedata"
    block, gaps = _build_policy_block(site_cn)
    assert block is not None
    assert block["policy_impulse"] == "targeted_support"
    assert "fiscal_or_structural" in block["transmission_channel"]
    assert block["recent_event_count"] == 1
    assert len(block["recent_events_summary"]) == 1
    assert gaps == []


# ---------------------------------------------------------------------------
# 10. Macro block fields
# ---------------------------------------------------------------------------

def test_macro_block_fields(tmp_path):
    _make_regime_json(tmp_path)
    data_dir = tmp_path / "data"
    block, gaps = _build_macro_block(data_dir)
    assert block is not None
    assert block["quad"] == "Q3"
    assert block["quad_name"] == "Stagflation"
    assert block["liquidity_overlay"] == "neutral"
    assert block["cycle_tag"] == "mid"
    assert gaps == []


# ---------------------------------------------------------------------------
# 11. External block — yield curve and USDCNH
# ---------------------------------------------------------------------------

def test_external_block_with_no_stores(tmp_path):
    """External block degrades to None + gaps when stores absent."""
    data_dir = tmp_path / "data"
    block, gaps = _build_external_block(data_dir)
    # Block may still be non-None if partial; gaps must be non-empty
    assert len(gaps) > 0


def test_external_block_with_forex_only(tmp_path):
    """When only forex/latest.json exists, USDCNH is populated."""
    forex_path = tmp_path / "data" / "forex" / "latest.json"
    _write_json(forex_path, {
        "date": "Jul 07, 2026",
        "pairs": {
            "USDCNH": {"quote": 6.77, "chg": -0.3, "score": 15.0, "action": "FLAT", "label": "USD/CNH"}
        },
    })
    data_dir = tmp_path / "data"
    block, gaps = _build_external_block(data_dir)
    # Even with missing parquets, USDCNH should be in block
    assert block is not None
    assert block["usdcnh"] is not None
    assert block["usdcnh"]["quote"] == pytest.approx(6.77)
    # DXY gap must be documented
    assert any("DXY" in g for g in gaps)


# ---------------------------------------------------------------------------
# 12. Allocation block
# ---------------------------------------------------------------------------

def test_allocation_block_fields(tmp_path):
    _make_alloc_json(tmp_path)
    data_dir = tmp_path / "data"
    block, gaps = _build_allocation_block(data_dir)
    assert block is not None
    assert block["variant"] == "balanced"
    assert block["growth_w"] == 35
    assert block["defensive_w"] == 65
    assert gaps == []


# ---------------------------------------------------------------------------
# 13. Cross-lobe contradiction: participation_risk_vs_phase
# ---------------------------------------------------------------------------

def test_contradiction_risk_vs_phase():
    phase = {"phase": "POLICY_PUT", "confidence": 0.7, "evidence": [], "contradictions": [], "falsifiers": []}
    participation = {"risk": "frothy", "who_controls": "retail", "regime": "retail_ignition"}
    contradictions = _compute_contradictions(phase, participation, None, None, None, None)
    assert any("participation_risk_vs_phase" in c for c in contradictions), \
        f"Expected contradiction not found in: {contradictions}"


def test_no_contradiction_risk_normal_policy_put():
    phase = {"phase": "POLICY_PUT"}
    participation = {"risk": "normal", "who_controls": "institutional", "regime": "institutional_accumulation"}
    contradictions = _compute_contradictions(phase, participation, None, None, None, None)
    assert not any("participation_risk_vs_phase" in c for c in contradictions)


# ---------------------------------------------------------------------------
# 14. Cross-lobe contradiction: policy_easing_vs_participation
# ---------------------------------------------------------------------------

def test_contradiction_policy_easing_vs_margin():
    policy = {"policy_impulse": "easing"}
    participation = {"risk": "frothy", "who_controls": "margin", "regime": "margin_acceleration"}
    contradictions = _compute_contradictions(None, participation, None, policy, None, None)
    assert any("policy_easing_vs_participation" in c for c in contradictions)


def test_no_contradiction_easing_institutional():
    policy = {"policy_impulse": "easing"}
    participation = {"risk": "normal", "who_controls": "institutional", "regime": "institutional_accumulation"}
    contradictions = _compute_contradictions(None, participation, None, policy, None, None)
    assert not any("policy_easing_vs_participation" in c for c in contradictions)


# ---------------------------------------------------------------------------
# 15. Cross-lobe contradiction: external_cnh_vs_macro
# ---------------------------------------------------------------------------

def test_contradiction_cnh_vs_q2_macro():
    macro = {"quad": "Q2", "quad_name": "Reflation"}
    external = {"usdcnh": {"quote": 7.30, "chg_pct": 0.5, "as_of": "2026-07-07"}}
    contradictions = _compute_contradictions(None, None, None, None, macro, external)
    assert any("external_cnh_vs_macro" in c for c in contradictions)


def test_no_cnh_contradiction_below_threshold():
    macro = {"quad": "Q1"}
    external = {"usdcnh": {"quote": 7.10}}
    contradictions = _compute_contradictions(None, None, None, None, macro, external)
    assert not any("external_cnh_vs_macro" in c for c in contradictions)


# ---------------------------------------------------------------------------
# 16. Cross-lobe contradiction: microstructure_chase_vs_participation
# ---------------------------------------------------------------------------

def test_contradiction_chase_vs_dormant():
    micro = {"name_summary": {"chase_veto_count": 5, "fillable_count": 100}}
    participation = {"risk": "normal", "regime": "dormant", "who_controls": "retail"}
    contradictions = _compute_contradictions(None, participation, micro, None, None, None)
    assert any("microstructure_chase_vs_participation" in c for c in contradictions)


def test_no_chase_contradiction_zero_vetos():
    micro = {"name_summary": {"chase_veto_count": 0}}
    participation = {"risk": "normal", "regime": "dormant"}
    contradictions = _compute_contradictions(None, participation, micro, None, None, None)
    assert not any("microstructure_chase_vs_participation" in c for c in contradictions)


# ---------------------------------------------------------------------------
# 17. Falsifiers pass-through from phase
# ---------------------------------------------------------------------------

def test_falsifiers_passthrough(tmp_path):
    _make_phase_json(tmp_path)
    site_cn = tmp_path / "site" / "chinastatedata"
    block, _ = _build_phase_block(site_cn)
    falsifiers = _collect_falsifiers(block)
    assert isinstance(falsifiers, list)
    assert len(falsifiers) == 1
    assert falsifiers[0]["id"] == "F1"


def test_falsifiers_empty_when_phase_absent():
    falsifiers = _collect_falsifiers(None)
    assert falsifiers == []


# ---------------------------------------------------------------------------
# 18. _validate() function
# ---------------------------------------------------------------------------

def test_validate_good_packet():
    packet = {
        "schema": "china_market_state.v1",
        "as_of": "2026-07-08",
        "generated_utc": "2026-07-08T10:00:00Z",
        "authority": {"tier": "context_only", "cannot_do": ["rank", "size", "gate", "originate"]},
        "phase": None,
        "participation": None,
        "microstructure": None,
        "policy": None,
        "rotation": None,
        "macro": None,
        "external": None,
        "allocation": None,
        "evidence": [],
        "contradictions": [],
        "falsifiers": [],
        "data_gaps": [],
    }
    assert _validate(packet) == []


def test_validate_wrong_schema():
    packet = {
        "schema": "wrong.schema",
        "as_of": "2026-07-08",
        "generated_utc": "2026-07-08T10:00:00Z",
        "authority": {"tier": "context_only", "cannot_do": ["rank"]},
        "phase": None, "participation": None, "microstructure": None, "policy": None,
        "rotation": None, "macro": None, "external": None, "allocation": None,
        "evidence": [], "contradictions": [], "falsifiers": [], "data_gaps": [],
    }
    failures = _validate(packet)
    assert any("schema" in f for f in failures)


def test_validate_missing_keys():
    packet = {"schema": "china_market_state.v1"}
    failures = _validate(packet)
    assert len(failures) >= 1


# ---------------------------------------------------------------------------
# 19. JSON serialisability
# ---------------------------------------------------------------------------

def test_packet_is_json_serialisable(tmp_path):
    """The assembled packet must be serialisable to JSON without errors."""
    _make_participation_json(tmp_path)
    _make_microstructure_json(tmp_path)
    _make_policy_json(tmp_path)
    _make_phase_json(tmp_path)
    _make_regime_json(tmp_path)
    _make_alloc_json(tmp_path)

    packet = build(tmp_path)
    serialised = json.dumps(packet, default=str)
    roundtripped = json.loads(serialised)
    assert roundtripped["schema"] == "china_market_state.v1"


# ---------------------------------------------------------------------------
# 20. Rotation block — sector phase distribution
# ---------------------------------------------------------------------------

def test_rotation_block_absent(tmp_path):
    data_dir = tmp_path / "data"
    block, gaps = _build_rotation_block(data_dir)
    assert block is None
    assert len(gaps) > 0


def test_rotation_block_with_ths_only(tmp_path):
    """THS basket summary produced even without leg_context."""
    ths_path = tmp_path / "data" / "baskets_china_ths" / "latest.json"
    _write_json(ths_path, {
        "as_of": "2026-07-07",
        "baskets": [
            {"id": "ths_storage_chip", "ret_60d": 0.75, "above_200d": True},
            {"id": "thsc308690", "ret_60d": 0.69, "above_200d": True},
            {"id": "ths_weak", "ret_60d": -0.20, "above_200d": False},
        ],
    })
    data_dir = tmp_path / "data"
    block, gaps = _build_rotation_block(data_dir)
    assert block is not None
    assert block["ths_heat"] is not None
    assert block["ths_heat"]["basket_count"] == 3
    assert block["ths_heat"]["hot_baskets"][0]["id"] == "ths_storage_chip"


# ---------------------------------------------------------------------------
# 21. Evidence builder smoke
# ---------------------------------------------------------------------------

def test_evidence_builder_with_macro_and_policy():
    macro = {
        "quad": "Q3",
        "quad_name": "Stagflation",
        "liquidity_overlay": "neutral",
        "confirming": ["growth_indpro_trend"],
        "contradicting": [],
    }
    policy = {
        "policy_impulse": "targeted_support",
        "transmission_channel": ["liquidity"],
    }
    evidence = _compute_evidence(None, None, policy, macro)
    assert any("macro:" in e for e in evidence)
    assert any("policy:" in e for e in evidence)


# ---------------------------------------------------------------------------
# 22. Smoke test with live stores (skip when absent)
# ---------------------------------------------------------------------------

def test_live_smoke():
    """Smoke: build() succeeds with live data stores in the repo."""
    live_site = _REPO_ROOT / "site" / "chinastatedata"
    live_data = _REPO_ROOT / "data"

    if not (live_site / "participation.json").exists():
        pytest.skip("Live participation.json not present — skipping live smoke")

    packet = build(_REPO_ROOT)
    failures = _validate(packet)
    assert not failures, f"Live smoke validation failures: {failures}"

    # Must have at least participation and macro in a real run
    lobes_present = [k for k in ["participation", "microstructure", "policy", "macro"]
                     if packet.get(k) is not None]
    assert lobes_present, "Expected at least one lobe present in live smoke"
