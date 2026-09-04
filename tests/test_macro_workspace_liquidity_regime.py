"""Composer tests for the US liquidity_regime workspace (F01 / R1A).

RED-first: each degraded condition must produce the correct TYPED state and
never a zero / neutral / calm default. Also covers quadrant classification,
disclosed hysteresis, the 1M vector, and a real-owner-artifact build.

    python3 -m pytest tests/test_macro_workspace_liquidity_regime.py -x -q
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.market_os.macro_workspaces import contract, liquidity_regime  # noqa: E402

BUILT_AT = "2026-09-04T00:00:00Z"
REGIME_LATEST = ROOT / "data" / "regime" / "latest.json"


def _base_regime() -> dict:
    return {
        "asof": "2026-09-03", "date": "2026-09-03",
        "liquidity_overlay": "contracting",
        "liquidity_quality": {
            "asof": "2026-09-03", "label": "contracting", "quantity_roc_bn": -165.3,
            "rrp_buffer_bn": 6.7, "rrp_exhausted": True,
            "composition": {"mechanical": True},
            "stress_overlay": {"confirming_stress": False, "hy_oas_z": -0.2, "hy_oas_pct": 2.66},
            "walcl_stale_days": 1, "degraded": False,
        },
        "conditions": {
            "stale_inputs": [],
            "vintages": {
                "nfci": {"asof": "2026-08-28", "stale": False},
                "ofr_fsi": {"asof": "2026-08-30", "stale": False},
                "hy_oas": {"asof": "2026-09-02", "stale": False},
            },
            "financial_conditions": {"nfci": -0.558, "nfci_pctile": 0.046},
            "systemic_stress": {"ofr_fsi": -2.749, "ofr_fsi_pctile": 0.0278},
        },
        "regime_vector": {"rate_pressure_rates_scare_score": 43.2,
                          "rate_pressure_real10y_chg63_bp": 24.0},
    }


def _compose(regime: dict, **kw) -> dict:
    return liquidity_regime.compose(regime, built_at=BUILT_AT, **kw)


def _required(snapshot: dict, cid: str) -> dict:
    return next(c for c in snapshot["availability"]["required"] if c["component_id"] == cid)


def _axis(snapshot: dict, axis_id: str) -> dict:
    return next(a for a in snapshot["axes"]["items"] if a["axis_id"] == axis_id)


# --------------------------------------------------------------------------- #
# healthy baseline
# --------------------------------------------------------------------------- #
def test_baseline_classifies_easy_funding_weak_support_quadrant_C() -> None:
    snap = _compose(_base_regime())
    assert snap["availability"]["state"] == "CURRENT"
    assert snap["headline"]["status"] == "PRESENT"
    x = snap["headline"]["quadrant"]["x"]
    y = snap["headline"]["quadrant"]["y"]
    assert x < 50 and y < 50            # easy funding, weak support
    assert snap["headline"]["state_id"] == "C"
    assert snap["headline"]["state_label"]["en"].startswith("Easy funding")
    # every required source is CURRENT and present
    for cid in ("net_liquidity_roc", "liquidity_quality_level", "nfci_pctile", "ofr_fsi_pctile"):
        r = _required(snap, cid)
        assert r["freshness"] == "CURRENT"
        assert r["status"] == "PRESENT"


# --------------------------------------------------------------------------- #
# typed degraded states (never zero / neutral / calm)
# --------------------------------------------------------------------------- #
def test_missing_required_source_is_typed_source_failed() -> None:
    reg = _base_regime()
    reg["conditions"]["financial_conditions"]["nfci_pctile"] = None
    snap = _compose(reg)
    r = _required(snap, "nfci_pctile")
    assert r["freshness"] == "SOURCE_FAILED"
    assert r["status"] == "ABSENT"
    assert r["null_reason"] == "SOURCE_FAILED"
    assert "nfci_pctile" in snap["availability"]["degraded"]
    assert snap["availability"]["state"] == "SOURCE_FAILED"  # conservative worst


def test_axis_below_coverage_floor_refuses_no_neutral_default() -> None:
    reg = _base_regime()
    # knock out 3 of 4 funding components -> below min_components/floor
    reg["conditions"]["financial_conditions"]["nfci_pctile"] = None
    reg["conditions"]["systemic_stress"]["ofr_fsi_pctile"] = None
    reg["liquidity_quality"]["stress_overlay"]["hy_oas_z"] = None
    snap = _compose(reg)
    axis = _axis(snap, "funding_pressure")
    assert axis["value"] is None
    assert axis["value_status"] == "ABSENT"
    assert axis["null_reason"] == "COMPUTATION_REFUSED"
    # no quadrant is asserted rather than defaulting to a neutral one
    assert snap["headline"]["state_id"] is None
    assert snap["headline"]["status"] == "ABSENT"
    assert snap["headline"]["quadrant"]["x"] is None


def test_stale_required_source_is_typed_stale_not_current() -> None:
    reg = _base_regime()
    reg["conditions"]["stale_inputs"] = ["nfci"]
    snap = _compose(reg)
    r = _required(snap, "nfci_pctile")
    assert r["freshness"] == "STALE_SOURCE"
    assert snap["availability"]["state"] == "STALE_SOURCE"
    assert snap["availability"]["state"] != "CURRENT"


def test_not_yet_released_source_is_typed() -> None:
    reg = _base_regime()
    reg["conditions"]["financial_conditions"]["nfci_pctile"] = None
    reg["conditions"]["vintages"]["nfci"] = {"not_yet_released": True}
    snap = _compose(reg)
    r = _required(snap, "nfci_pctile")
    assert r["freshness"] == "NOT_YET_RELEASED"
    assert snap["availability"]["state"] == "NOT_YET_RELEASED"


def test_source_failed_on_missing_liquidity_quantity() -> None:
    reg = _base_regime()
    reg["liquidity_quality"]["quantity_roc_bn"] = None
    snap = _compose(reg)
    r = _required(snap, "net_liquidity_roc")
    assert r["freshness"] == "SOURCE_FAILED"
    assert r["status"] == "ABSENT"


def test_contradiction_quantity_vs_quality_is_typed_disagreement() -> None:
    reg = _base_regime()
    reg["liquidity_quality"]["label"] = "stress-expansion"
    reg["liquidity_quality"]["quantity_roc_bn"] = 120.0
    snap = _compose(reg)
    c = snap["availability"]["contradiction"]
    assert c["present"] is True
    assert c["kind"] == "quantity_vs_quality"
    assert any("contradiction" in r for r in snap["availability"]["reasons"])
    # surfaced as an implication too, never silently calm
    assert any(i["implication_id"] == "quantity_quality_contradiction"
               for i in snap["implications"]["items"])


def test_hollow_expansion_is_flagged() -> None:
    reg = _base_regime()
    reg["liquidity_quality"]["label"] = "neutral"
    reg["liquidity_quality"]["quantity_roc_bn"] = 60.0
    reg["liquidity_quality"]["rrp_exhausted"] = True
    snap = _compose(reg)
    assert snap["availability"]["contradiction"]["present"] is True
    assert snap["availability"]["contradiction"]["kind"] == "hollow_expansion"


# --------------------------------------------------------------------------- #
# changes / method-version comparability / 1M vector
# --------------------------------------------------------------------------- #
def _prior(state_id="C", method=liquidity_regime.METHOD_VERSION, x=20.0, y=25.0) -> dict:
    return {
        "generation": {"generation_id": "liquidity_regime-US-deadbeefdeadbeef"},
        "headline": {
            "state_id": state_id, "method_version": method,
            "effective_date": "2026-08-04",
            "quadrant": {"x": x, "y": y},
        },
    }


def test_no_prior_yields_warmup() -> None:
    snap = _compose(_base_regime())
    assert snap["changes"]["comparability"] == "NO_PRIOR"
    assert snap["changes"]["null_reason"] == "WARMUP"
    assert snap["headline"]["one_month_vector"]["status"] == "ABSENT"
    assert snap["headline"]["one_month_vector"]["null_reason"] == "WARMUP"


def test_method_version_mismatch_refuses_numeric_comparison() -> None:
    snap = _compose(_base_regime(), prior_snapshot=_prior(method="liquidity_regime.compose.v0"))
    assert snap["changes"]["comparability"] == "METHOD_CHANGED"
    assert snap["changes"]["deltas"] == []
    assert snap["changes"]["null_reason"] == "COMPUTATION_REFUSED"


def test_comparable_prior_produces_deltas_and_vector() -> None:
    snap = _compose(_base_regime(), prior_snapshot=_prior(x=10.0, y=40.0))
    assert snap["changes"]["comparability"] == "COMPARABLE"
    assert {d["metric_id"] for d in snap["changes"]["deltas"]} == {"funding_pressure", "balance_sheet_support"}
    v = snap["headline"]["one_month_vector"]
    assert v["status"] == "PRESENT"
    assert v["dx"] is not None and v["dy"] is not None


# --------------------------------------------------------------------------- #
# hysteresis
# --------------------------------------------------------------------------- #
def _regime_at(x_targets, y_targets) -> dict:
    """Craft owner inputs to place the axes near chosen scores.
    x = .30*nfci*100 + .30*ofr*100 + .20*z(50) + .20*scare
    y = .35*overlay(50) + .40*quality(50) + .25*roc_mapped
    """
    nfci_p, ofr_p, scare = x_targets
    roc = y_targets
    reg = _base_regime()
    reg["liquidity_overlay"] = "neutral"
    reg["liquidity_quality"]["label"] = "neutral"
    reg["liquidity_quality"]["quantity_roc_bn"] = roc
    reg["liquidity_quality"]["stress_overlay"]["hy_oas_z"] = 0.0
    reg["liquidity_quality"]["rrp_exhausted"] = False
    reg["liquidity_quality"]["composition"] = {"mechanical": False}
    reg["conditions"]["financial_conditions"]["nfci_pctile"] = nfci_p
    reg["conditions"]["systemic_stress"]["ofr_fsi_pctile"] = ofr_p
    reg["regime_vector"]["rate_pressure_rates_scare_score"] = scare
    return reg


def test_hysteresis_holds_prior_within_band() -> None:
    # x ~ 47.6 (easy, near boundary), y ~ 48 (weak, near boundary) -> raw C,
    # prior D within band -> hold D
    reg = _regime_at((0.47, 0.47, 47.0), -80.0)
    snap = _compose(reg, prior_snapshot=_prior(state_id="D", x=52.0, y=48.0))
    assert abs(snap["headline"]["quadrant"]["x"] - 47.6) < 1.0
    assert snap["headline"]["hysteresis"]["held_prior"] is True
    assert snap["headline"]["state_id"] == "D"


def test_hysteresis_flips_when_both_axes_beyond_band() -> None:
    # x ~ 42, y ~ 40 -> both beyond 5-pt band -> flip to raw C off prior D
    reg = _regime_at((0.40, 0.40, 40.0), -400.0)
    snap = _compose(reg, prior_snapshot=_prior(state_id="D", x=52.0, y=48.0))
    assert snap["headline"]["hysteresis"]["held_prior"] is False
    assert snap["headline"]["state_id"] == "C"


# --------------------------------------------------------------------------- #
# real owner artifact
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(not REGIME_LATEST.exists(), reason="owner artifact data/regime/latest.json absent")
def test_builds_and_validates_from_real_owner_artifact() -> None:
    regime = json.loads(REGIME_LATEST.read_text(encoding="utf-8"))
    snap = contract.finalize(liquidity_regime.compose(regime, built_at=BUILT_AT))
    contract.validate(snap)  # real-data snapshot satisfies the closed contract
    assert snap["headline"]["state_id"] in ("A", "B", "C", "D", None)
    assert snap["generation"]["calculation_as_of"] == regime.get("asof")
    assert snap["authority"]["can_size"] is False
