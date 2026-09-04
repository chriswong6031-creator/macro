"""Composer tests for the US financial_conditions workspace (F01 / R3).

RED-first, mirroring tests/test_macro_workspace_liquidity_regime.py: each
degraded condition must produce the correct TYPED state and never a
zero / neutral / calm default. Also covers quadrant classification, disclosed
hysteresis, the 1M vector, digest determinism, zh-label integrity, and a
hand-trace against liquidity_regime showing the two composers agree at the
OWNER level on every field they share, even though their COMPOSITIONS differ
on purpose.

    python3 -m pytest tests/test_macro_workspace_financial_conditions.py -x -q
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

from engine.market_os.macro_workspaces import contract, financial_conditions, liquidity_regime  # noqa: E402

BUILT_AT = "2026-09-04T00:00:00Z"
REGIME_LATEST = ROOT / "data" / "regime" / "latest.json"

FC = financial_conditions


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
def _base_regime() -> dict:
    """A realistic-shaped owner artifact carrying every field this composer
    reads (data/regime/latest.json's real shape, trimmed to what matters)."""
    return {
        "asof": "2026-09-03", "date": "2026-09-03",
        "liquidity_quality": {
            "stress_overlay": {"hy_oas_pct": 2.66, "hy_oas_z": -0.2, "hy_oas_chg_20d": -0.05},
        },
        "conditions": {
            "stale_inputs": [],
            "vintages": {
                "nfci": {"asof": "2026-08-28", "stale": False},
                "ofr_fsi": {"asof": "2026-09-01", "stale": False},
                "hy_oas": {"asof": "2026-09-02", "stale": False},
                "us10y": {"asof": "2026-09-01", "stale": False},
            },
            "financial_conditions": {
                "nfci": -0.558, "nfci_pctile": 0.046, "nfci_change_13w": -0.049,
                "subindices": {"nfci_credit": -0.059, "nfci_risk": -0.648, "nfci_leverage": 0.109},
            },
            "systemic_stress": {
                "ofr_fsi": -2.749, "ofr_fsi_pctile": 0.0278, "ofr_fsi_change_13w": -0.067,
                "state": "calm",
                "functional": {"credit": -1.148, "funding": -0.133, "equity_valuation": -0.58},
            },
        },
        "rate_inflation_transmission": {
            "asof": "2026-09-03",
            "state": {"rates": {"real_10y": 2.45, "real_10y_pctile": 0.99, "real_10y_chg_63d_bp": 24.0}},
        },
        "vol_regime": {"available": True, "asof": "2026-08-31", "vix": 14.92,
                       "risk_score": 0.201, "move_pctile": 0.33},
        "risk_state": {"asof": "2026-09-03", "state": "risk-on", "score": 16.1},
    }


def _regime_at(level_target: float, impulse_target: float) -> dict:
    """Craft owner inputs so EVERY channel component maps to the SAME
    standardized value (level_target), guaranteeing the level composite lands
    exactly on it (weighted mean of identical values = that value), and
    likewise for the 3 impulse legs -> impulse_target. Gives precise control
    over headline.quadrant.x/y for classification/hysteresis tests."""
    reg = _base_regime()
    p = level_target / 100.0
    z = (level_target - 50.0) * FC.Z_SCALE / 50.0
    rates = reg["rate_inflation_transmission"]["state"]["rates"]
    rates["real_10y_pctile"] = p
    reg["liquidity_quality"]["stress_overlay"]["hy_oas_z"] = z
    reg["conditions"]["financial_conditions"]["subindices"]["nfci_credit"] = z
    reg["conditions"]["systemic_stress"]["functional"]["funding"] = z
    reg["vol_regime"]["risk_score"] = p
    reg["vol_regime"]["move_pctile"] = p

    w = impulse_target
    reg["conditions"]["financial_conditions"]["nfci_change_13w"] = (w - 50.0) * FC.NFCI_CHG_SCALE / 50.0
    reg["conditions"]["systemic_stress"]["ofr_fsi_change_13w"] = (w - 50.0) * FC.OFR_CHG_SCALE / 50.0
    rates["real_10y_chg_63d_bp"] = (w - 50.0) * FC.REAL10Y_CHG_SCALE_BP / 50.0
    return reg


def _compose(regime: dict, **kw) -> dict:
    kw.setdefault("built_at", BUILT_AT)
    return FC.compose(regime, **kw)


def _required(snapshot: dict, cid: str) -> dict:
    return next(c for c in snapshot["availability"]["required"] if c["component_id"] == cid)


def _metric(snapshot: dict, mid: str) -> dict:
    return next(m for m in snapshot["metrics"]["items"] if m["metric_id"] == mid)


def _axis(snapshot: dict, axis_id: str) -> dict:
    return next(a for a in snapshot["axes"]["items"] if a["axis_id"] == axis_id)


def _prior(state_id="C", method=FC.METHOD_VERSION, x=20.0, y=25.0) -> dict:
    return {
        "generation": {"generation_id": "financial_conditions-US-deadbeefdeadbeef"},
        "headline": {
            "state_id": state_id, "method_version": method,
            "effective_date": "2026-08-04",
            "quadrant": {"x": x, "y": y},
        },
    }


# --------------------------------------------------------------------------- #
# healthy baseline + schema validation
# --------------------------------------------------------------------------- #
def test_baseline_classifies_tight_tightening_quadrant_B_and_validates() -> None:
    snap = contract.finalize(_compose(_base_regime()))
    contract.validate(snap)  # exercises the real jsonschema validator
    assert snap["availability"]["state"] == "CURRENT"
    assert snap["headline"]["status"] == "PRESENT"
    x = snap["headline"]["quadrant"]["x"]
    y = snap["headline"]["quadrant"]["y"]
    assert x >= 50 and y >= 50       # tight level, tightening impulse
    assert snap["headline"]["state_id"] == "B"
    assert snap["headline"]["state_label"]["en"].startswith("Tight conditions")
    for cid in ("nfci_pctile", "ofr_fsi_pctile", "hy_oas_pct", "real_10y_pctile", "vol_regime_risk_score"):
        r = _required(snap, cid)
        assert r["freshness"] == "CURRENT"
        assert r["status"] == "PRESENT"
    assert snap["authority"]["can_size"] is False
    assert snap["authority"]["display_only"] is True


def test_axes_items_carry_real_ids_and_full_disclosure() -> None:
    # axis_id was widened to a generic lowercase-snake-case pattern in the
    # integration pass; this workspace now publishes two real axis objects
    # (own naming, not R1A's borrowed funding_pressure/balance_sheet_support).
    snap = contract.finalize(_compose(_base_regime()))
    contract.validate(snap)
    assert {a["axis_id"] for a in snap["axes"]["items"]} == {
        "financial_conditions_level", "financial_conditions_impulse"}

    level = _axis(snap, "financial_conditions_level")
    assert level["value"] == snap["headline"]["quadrant"]["x"]
    assert level["value_status"] == snap["headline"]["quadrant"]["x_status"]
    assert level["direction_semantics"] == "higher_tighter"
    assert level["authority_ceiling"] == "DESCRIPTIVE"
    assert level["thresholds"]["boundary"] == FC.BOUNDARY
    assert level["thresholds"]["hysteresis_band"] == FC.HYSTERESIS_BAND
    level_component_ids = {c["component_id"] for c in level["components"]}
    assert level_component_ids == {
        "rates_channel", "credit_channel", "dollar_funding_channel", "equities_vol_channel"}
    level_weights = {c["component_id"]: c["weight"] for c in level["components"]}
    assert level_weights == {"rates_channel": 0.30, "credit_channel": 0.30,
                             "dollar_funding_channel": 0.20, "equities_vol_channel": 0.20}
    for c in level["components"]:
        assert c["raw_value"] is not None and c["standardized_value"] is not None
        assert c["owner_ref"] == FC.PRODUCER  # channel-level rollups, not raw owner fields
    assert "weighted mean" in level["transformation"]
    assert "boundary=50.0" in level["transformation"]

    impulse = _axis(snap, "financial_conditions_impulse")
    assert impulse["value"] == snap["headline"]["quadrant"]["y"]
    assert impulse["direction_semantics"] == "higher_tightening_impulse"
    impulse_component_ids = {c["component_id"] for c in impulse["components"]}
    assert impulse_component_ids == {"nfci_change_13w", "ofr_fsi_change_13w", "real_10y_chg_63d_bp"}
    impulse_weights = {c["component_id"]: c["weight"] for c in impulse["components"]}
    assert impulse_weights == {"nfci_change_13w": 0.35, "ofr_fsi_change_13w": 0.35,
                               "real_10y_chg_63d_bp": 0.30}
    for c in impulse["components"]:
        # impulse components ARE raw owner-native legs (not channel rollups)
        assert c["owner_ref"] != FC.PRODUCER
        assert c["owner_field"].startswith("conditions.") or c["owner_field"].startswith(
            "rate_inflation_transmission.")

    # the drivers-bucket cosmetic-reuse note survives (v1, unchanged by the widening)
    assert any(i["implication_id"] == "driver_bucket_naming_note" for i in snap["implications"]["items"])
    assert not any(i["implication_id"] == "axis_contract_limitation" for i in snap["implications"]["items"])


# --------------------------------------------------------------------------- #
# typed degraded states (never zero / neutral / calm)
# --------------------------------------------------------------------------- #
def test_missing_required_source_is_typed_source_failed_but_channel_degrades_gracefully() -> None:
    reg = _base_regime()
    reg["rate_inflation_transmission"]["state"]["rates"]["real_10y_pctile"] = None
    snap = contract.finalize(_compose(reg))
    contract.validate(snap)
    r = _required(snap, "real_10y_pctile")
    assert r["freshness"] == "SOURCE_FAILED"
    assert r["status"] == "ABSENT"
    assert "real_10y_pctile" in snap["availability"]["degraded"]
    assert snap["availability"]["state"] == "SOURCE_FAILED"  # conservative worst
    rc = _metric(snap, "rates_channel_score")
    assert rc["value"] is None
    assert rc["status"] == "ABSENT"
    assert rc["null_reason"] == "COMPUTATION_REFUSED"
    # only 1 of 4 declared channels lost -> level composite still computable
    level = _metric(snap, "financial_conditions_level")
    assert level["value"] is not None
    assert snap["headline"]["state_id"] is not None


def test_stale_required_source_is_typed_stale_not_current() -> None:
    reg = _base_regime()
    reg["conditions"]["stale_inputs"] = ["ofr_fsi"]
    snap = contract.finalize(_compose(reg))
    contract.validate(snap)
    r = _required(snap, "ofr_fsi_pctile")
    assert r["freshness"] == "STALE_SOURCE"
    assert snap["availability"]["state"] == "STALE_SOURCE"
    assert snap["availability"]["state"] != "CURRENT"


def test_not_yet_released_source_is_typed() -> None:
    reg = _base_regime()
    reg["liquidity_quality"]["stress_overlay"]["hy_oas_pct"] = None
    reg["conditions"]["vintages"]["hy_oas"] = {"not_yet_released": True}
    snap = contract.finalize(_compose(reg))
    contract.validate(snap)
    r = _required(snap, "hy_oas_pct")
    assert r["freshness"] == "NOT_YET_RELEASED"
    assert snap["availability"]["state"] == "NOT_YET_RELEASED"


def test_vol_regime_unavailable_is_typed_source_failed() -> None:
    reg = _base_regime()
    reg["vol_regime"]["available"] = False
    reg["vol_regime"]["risk_score"] = None
    snap = contract.finalize(_compose(reg))
    contract.validate(snap)
    r = _required(snap, "vol_regime_risk_score")
    assert r["freshness"] == "SOURCE_FAILED"
    assert r["status"] == "ABSENT"


def test_credit_channel_below_coverage_floor_refuses_no_neutral_default() -> None:
    reg = _base_regime()
    reg["liquidity_quality"]["stress_overlay"]["hy_oas_z"] = None
    reg["conditions"]["financial_conditions"]["subindices"]["nfci_credit"] = None
    snap = contract.finalize(_compose(reg))
    contract.validate(snap)
    cc = _metric(snap, "credit_channel_score")
    assert cc["value"] is None
    assert cc["status"] == "ABSENT"
    assert cc["null_reason"] == "COMPUTATION_REFUSED"


def test_level_composite_below_coverage_floor_refuses_no_neutral_default() -> None:
    # knock 3 of 4 declared channels below their own floors -> level itself refuses
    reg = _base_regime()
    reg["rate_inflation_transmission"]["state"]["rates"]["real_10y_pctile"] = None
    reg["liquidity_quality"]["stress_overlay"]["hy_oas_z"] = None
    reg["conditions"]["financial_conditions"]["subindices"]["nfci_credit"] = None
    reg["conditions"]["systemic_stress"]["functional"]["funding"] = None
    snap = contract.finalize(_compose(reg))
    contract.validate(snap)
    level = _metric(snap, "financial_conditions_level")
    assert level["value"] is None
    assert level["status"] == "ABSENT"
    assert level["null_reason"] == "COMPUTATION_REFUSED"
    # no quadrant is asserted rather than defaulting to a neutral one
    assert snap["headline"]["state_id"] is None
    assert snap["headline"]["status"] == "ABSENT"
    assert snap["headline"]["quadrant"]["x"] is None


# --------------------------------------------------------------------------- #
# permanently-declared-but-not-sourced legs (never fabricated, never silent)
# --------------------------------------------------------------------------- #
def test_lending_channel_is_always_typed_not_covered() -> None:
    snap = contract.finalize(_compose(_base_regime()))
    contract.validate(snap)
    m = _metric(snap, "lending_channel_score")
    assert m["value"] is None
    assert m["status"] == "ABSENT"
    assert m["null_reason"] == "NOT_COVERED"
    assert m["rights_state"] == "UNKNOWN"
    assert any(i["implication_id"] == "lending_channel_not_covered" for i in snap["implications"]["items"])


def test_ig_oas_and_dollar_index_legs_are_declared_not_covered() -> None:
    snap = contract.finalize(_compose(_base_regime()))
    contract.validate(snap)
    for mid in ("ig_oas_pct", "dollar_index_pctile"):
        m = _metric(snap, mid)
        assert m["value"] is None
        assert m["status"] == "ABSENT"
        assert m["null_reason"] == "NOT_COVERED"


# --------------------------------------------------------------------------- #
# contradiction: broad official stress calm vs risk-appetite gauge
# --------------------------------------------------------------------------- #
def test_baseline_risk_on_has_no_contradiction() -> None:
    snap = contract.finalize(_compose(_base_regime()))
    contract.validate(snap)
    assert snap["availability"]["contradiction"]["present"] is False


def test_broad_stress_vs_risk_appetite_contradiction_is_typed_disagreement() -> None:
    reg = _base_regime()
    reg["conditions"]["systemic_stress"]["state"] = "calm"
    reg["risk_state"]["state"] = "risk-off (elevated)"
    snap = contract.finalize(_compose(reg))
    contract.validate(snap)
    c = snap["availability"]["contradiction"]
    assert c["present"] is True
    assert c["kind"] == "broad_stress_vs_risk_appetite"
    assert any("contradiction" in r for r in snap["availability"]["reasons"])
    assert any(i["implication_id"] == "broad_stress_vs_risk_appetite" for i in snap["implications"]["items"])
    level_metric = _metric(snap, "financial_conditions_level")
    assert level_metric["status"] == "DISAGREEMENT"
    assert level_metric["value"] is not None  # typed disagreement, not censored
    ev = _metric(snap, "equities_vol_channel_score")
    assert ev["status"] == "DISAGREEMENT"
    assert ev["value"] is not None
    # F3-equivalent: the axis object's own value_status flips too, and the
    # implicated equities_vol_channel component inside it is flagged, never
    # left silently PRESENT beside the contradiction block.
    level_axis = _axis(snap, "financial_conditions_level")
    assert level_axis["value_status"] == "DISAGREEMENT"
    assert level_axis["value"] is not None
    ev_component = next(c for c in level_axis["components"] if c["component_id"] == "equities_vol_channel")
    assert ev_component["coverage_state"] == "DISAGREEMENT"
    # impulse is not implicated by this contradiction
    impulse_axis = _axis(snap, "financial_conditions_impulse")
    assert impulse_axis["value_status"] != "DISAGREEMENT"


# --------------------------------------------------------------------------- #
# changes / method-version comparability / 1M vector
# --------------------------------------------------------------------------- #
def test_no_prior_yields_warmup() -> None:
    snap = _compose(_base_regime())
    assert snap["changes"]["comparability"] == "NO_PRIOR"
    assert snap["changes"]["null_reason"] == "WARMUP"
    assert snap["headline"]["one_month_vector"]["status"] == "ABSENT"
    assert snap["headline"]["one_month_vector"]["null_reason"] == "WARMUP"


def test_method_version_mismatch_refuses_numeric_comparison() -> None:
    snap = _compose(_base_regime(), prior_snapshot=_prior(method="financial_conditions.compose.v0"))
    assert snap["changes"]["comparability"] == "METHOD_CHANGED"
    assert snap["changes"]["deltas"] == []
    assert snap["changes"]["null_reason"] == "COMPUTATION_REFUSED"
    assert snap["headline"]["one_month_vector"]["status"] == "ABSENT"
    assert snap["headline"]["one_month_vector"]["null_reason"] == "COMPUTATION_REFUSED"


def test_comparable_prior_produces_deltas_and_vector() -> None:
    snap = _compose(_base_regime(), prior_snapshot=_prior(x=10.0, y=40.0))
    assert snap["changes"]["comparability"] == "COMPARABLE"
    assert {d["metric_id"] for d in snap["changes"]["deltas"]} == {
        "financial_conditions_level", "financial_conditions_impulse"}
    v = snap["headline"]["one_month_vector"]
    assert v["status"] == "PRESENT"
    assert v["dx"] is not None and v["dy"] is not None


# --------------------------------------------------------------------------- #
# hysteresis
# --------------------------------------------------------------------------- #
def test_hysteresis_holds_prior_within_band() -> None:
    # level ~47.6 (easy, near boundary), impulse ~48 (easing, near boundary)
    # -> raw A, prior D(52,48) within band on the one crossing axis -> hold D
    reg = _regime_at(47.6, 48.0)
    snap = _compose(reg, prior_snapshot=_prior(state_id="D", x=52.0, y=48.0))
    assert abs(snap["headline"]["quadrant"]["x"] - 47.6) < 0.5
    assert snap["headline"]["hysteresis"]["held_prior"] is True
    assert snap["headline"]["state_id"] == "D"


def test_hysteresis_flips_when_both_axes_beyond_band() -> None:
    reg = _regime_at(30.0, 30.0)
    snap = _compose(reg, prior_snapshot=_prior(state_id="B", x=60.0, y=60.0))
    assert snap["headline"]["hysteresis"]["held_prior"] is False
    assert snap["headline"]["state_id"] == "A"


def test_hysteresis_does_not_suppress_decisive_flip_on_other_axis() -> None:
    # level flips decisively (20 -> 90, far beyond band) while impulse idles
    # near ITS OWN boundary (49, prior 48) WITHOUT crossing it. impulse must
    # never suppress level's real flip.
    reg = _regime_at(90.0, 49.0)
    snap = _compose(reg, prior_snapshot=_prior(state_id="C", x=20.0, y=48.0))
    assert snap["headline"]["quadrant"]["x"] == 90.0
    assert abs(snap["headline"]["quadrant"]["y"] - 50) <= FC.HYSTERESIS_BAND
    assert snap["headline"]["hysteresis"]["held_prior"] is False
    assert snap["headline"]["state_id"] == "D"


# --------------------------------------------------------------------------- #
# zh narrative integrity (regression pattern from R1A's F11 finding)
# --------------------------------------------------------------------------- #
_QUADRANT_EN_LABEL_PHRASES = ("Easy conditions", "Tight conditions", "Easing impulse", "Tightening impulse")


def _find_english_label_leaks(node, path: str = "$") -> list[tuple[str, str, str]]:
    leaks: list[tuple[str, str, str]] = []
    if isinstance(node, dict):
        zh = node.get("zh")
        if "en" in node and isinstance(zh, str):
            for phrase in _QUADRANT_EN_LABEL_PHRASES:
                if phrase in zh:
                    leaks.append((path, phrase, zh))
        for k, v in node.items():
            leaks.extend(_find_english_label_leaks(v, f"{path}.{k}"))
    elif isinstance(node, list):
        for idx, v in enumerate(node):
            leaks.extend(_find_english_label_leaks(v, f"{path}[{idx}]"))
    return leaks


def test_zh_narrative_never_embeds_english_quadrant_label() -> None:
    for level_t, impulse_t in ((30.0, 30.0), (70.0, 70.0), (30.0, 70.0), (70.0, 30.0)):
        reg = _regime_at(level_t, impulse_t)
        snap = _compose(reg)
        assert snap["headline"]["state_id"] in ("A", "B", "C", "D")
        leaks = _find_english_label_leaks(snap)
        assert leaks == [], f"English quadrant label leaked into zh field(s): {leaks}"


# --------------------------------------------------------------------------- #
# digest determinism
# --------------------------------------------------------------------------- #
def test_digest_is_stable_across_builds_of_identical_input() -> None:
    body1 = _compose(_base_regime(), code_version="deadbeef")
    body2 = _compose(_base_regime(), built_at="2026-09-05T00:00:00Z", code_version="cafef00d")
    snap1 = contract.finalize(body1)
    snap2 = contract.finalize(body2)
    assert snap1["generation"]["content_sha256"] == snap2["generation"]["content_sha256"]
    assert snap1["generation"]["generation_id"] == snap2["generation"]["generation_id"]


def test_digest_changes_when_owner_input_changes() -> None:
    snap1 = contract.finalize(_compose(_base_regime()))
    reg2 = _base_regime()
    reg2["liquidity_quality"]["stress_overlay"]["hy_oas_z"] = -1.5
    snap2 = contract.finalize(_compose(reg2))
    assert snap1["generation"]["content_sha256"] != snap2["generation"]["content_sha256"]


# --------------------------------------------------------------------------- #
# corrections / supersession honesty
# --------------------------------------------------------------------------- #
def test_corrections_none_for_first_print() -> None:
    snap = _compose(_base_regime())
    assert snap["corrections"]["correction_state"] == "none"
    assert snap["corrections"]["predecessor_generation_id"] is None
    assert snap["corrections"]["changed_fingerprints"] == []


def test_corrections_superseded_when_same_period_source_value_changes() -> None:
    reg = _base_regime()
    prior_snap = contract.finalize(_compose(reg))
    reg2 = copy.deepcopy(reg)
    reg2["liquidity_quality"]["stress_overlay"]["hy_oas_z"] = -1.9  # revision, SAME asof
    snap2 = _compose(reg2, prior_snapshot=prior_snap)
    assert snap2["corrections"]["correction_state"] == "superseded"
    assert snap2["corrections"]["changed_fingerprints"]
    assert any(fp.startswith("hy_oas:hy_oas_z:") for fp in snap2["corrections"]["changed_fingerprints"])
    assert snap2["corrections"]["predecessor_generation_id"] == prior_snap["generation"]["generation_id"]


def test_corrections_none_when_same_period_no_source_change() -> None:
    reg = _base_regime()
    prior_snap = contract.finalize(_compose(reg))
    snap2 = _compose(copy.deepcopy(reg), prior_snapshot=prior_snap)
    assert snap2["corrections"]["correction_state"] == "none"
    assert snap2["corrections"]["changed_fingerprints"] == []


def test_corrections_none_when_reference_period_advances() -> None:
    reg = _base_regime()
    prior_snap = contract.finalize(_compose(reg))
    reg2 = copy.deepcopy(reg)
    reg2["asof"] = reg2["date"] = "2026-09-04"
    reg2["liquidity_quality"]["stress_overlay"]["hy_oas_z"] = -1.9
    snap2 = _compose(reg2, prior_snapshot=prior_snap)
    assert snap2["corrections"]["correction_state"] == "none"


# --------------------------------------------------------------------------- #
# hand-trace vs R1A: same owner fields must agree at the OWNER level even
# though composition (what each workspace DOES with the number) differs
# --------------------------------------------------------------------------- #
def _combined_regime() -> dict:
    """A fixture both composers can read: financial_conditions' shape plus the
    liquidity_regime-specific fields (liquidity_overlay, quantity_roc_bn,
    rrp_buffer_bn, regime_vector) that FC never touches."""
    reg = _base_regime()
    reg["liquidity_overlay"] = "contracting"
    reg["liquidity_quality"].update({
        "asof": "2026-09-03", "label": "contracting", "quantity_roc_bn": -165.3,
        "rrp_buffer_bn": 6.7, "rrp_exhausted": True,
        "composition": {"mechanical": True},
        "walcl_stale_days": 1, "degraded": False,
    })
    reg["regime_vector"] = {"rate_pressure_rates_scare_score": 43.2}
    return reg


def test_nfci_pctile_agrees_with_r1a_at_owner_level() -> None:
    reg = _combined_regime()
    lr_snap = liquidity_regime.compose(reg, built_at=BUILT_AT)
    fc_snap = FC.compose(reg, built_at=BUILT_AT)
    lr_component = next(c for a in lr_snap["axes"]["items"] if a["axis_id"] == "funding_pressure"
                        for c in a["components"] if c["component_id"] == "nfci_pctile")
    fc_component = _metric(fc_snap, "nfci_pctile")
    assert lr_component["raw_value"] == fc_component["value"] == reg["conditions"]["financial_conditions"]["nfci_pctile"]


def test_ofr_fsi_pctile_agrees_with_r1a_at_owner_level() -> None:
    reg = _combined_regime()
    lr_snap = liquidity_regime.compose(reg, built_at=BUILT_AT)
    fc_snap = FC.compose(reg, built_at=BUILT_AT)
    lr_component = next(c for a in lr_snap["axes"]["items"] if a["axis_id"] == "funding_pressure"
                        for c in a["components"] if c["component_id"] == "ofr_fsi_pctile")
    fc_component = _metric(fc_snap, "ofr_fsi_pctile")
    assert lr_component["raw_value"] == fc_component["value"] == reg["conditions"]["systemic_stress"]["ofr_fsi_pctile"]


def test_hy_oas_pct_agrees_with_r1a_at_owner_level() -> None:
    reg = _combined_regime()
    lr_snap = liquidity_regime.compose(reg, built_at=BUILT_AT)
    fc_snap = FC.compose(reg, built_at=BUILT_AT)
    lr_metric = next(m for m in lr_snap["metrics"]["items"] if m["metric_id"] == "hy_oas_pct")
    fc_metric = _metric(fc_snap, "hy_oas_pct")
    assert lr_metric["value"] == fc_metric["value"] == reg["liquidity_quality"]["stress_overlay"]["hy_oas_pct"]


def test_hy_oas_z_agrees_with_r1a_at_owner_level_despite_different_use() -> None:
    """R1A reads hy_oas_z internally for its funding_pressure axis component
    (weight 0.20 there, never published as its own top-level metric). FC
    publishes it as a first-class metric AND feeds it into credit_channel at
    weight 0.45. The RAW owner number must agree; the USE differs on purpose
    and is disclosed in FC's metric transformation text (not silently)."""
    reg = _combined_regime()
    lr_snap = liquidity_regime.compose(reg, built_at=BUILT_AT)
    fc_snap = FC.compose(reg, built_at=BUILT_AT)
    lr_component = next(c for a in lr_snap["axes"]["items"] if a["axis_id"] == "funding_pressure"
                        for c in a["components"] if c["component_id"] == "hy_oas_z")
    fc_metric = _metric(fc_snap, "hy_oas_z")
    assert lr_component["raw_value"] == fc_metric["value"] == reg["liquidity_quality"]["stress_overlay"]["hy_oas_z"]
    # the disclosed difference in USE is present in FC's own text, not hidden
    assert "R1A" in fc_metric["transformation"]


# --------------------------------------------------------------------------- #
# real owner artifact
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(not REGIME_LATEST.exists(), reason="owner artifact data/regime/latest.json absent")
def test_builds_and_validates_from_real_owner_artifact() -> None:
    regime = json.loads(REGIME_LATEST.read_text(encoding="utf-8"))
    snap = contract.finalize(FC.compose(regime, built_at=BUILT_AT))
    contract.validate(snap)  # real-data snapshot satisfies the closed contract
    assert snap["headline"]["state_id"] in ("A", "B", "C", "D", None)
    assert snap["generation"]["calculation_as_of"] == regime.get("asof")
    assert snap["authority"]["can_size"] is False
    assert {a["axis_id"] for a in snap["axes"]["items"]} == {
        "financial_conditions_level", "financial_conditions_impulse"}
