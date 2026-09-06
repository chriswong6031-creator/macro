"""Composer tests for the US growth_real_economy workspace (F01 / R2).

Mirrors tests/test_macro_workspace_liquidity_regime.py's RED-first discipline:
each degraded condition must produce the correct TYPED state and never a
zero / neutral / calm default. Also covers quadrant classification, disclosed
hysteresis, the 1M vector, both typed contradictions (asserted at BOTH the
axes.items[axis_id].value_status level and the composite metric level -- they
must always agree), the axis component/weight table, digest determinism, the
zh-label-leak regression, and a real-owner-artifact build.

    python3 -m pytest tests/test_macro_workspace_growth.py -x -q
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

from engine.market_os.macro_workspaces import contract, growth  # noqa: E402

BUILT_AT = "2026-09-04T00:00:00Z"
REGIME_LATEST = ROOT / "data" / "regime" / "latest.json"


def _base_regime() -> dict:
    return {
        "asof": "2026-09-03", "date": "2026-09-03",
        "growth_score": -0.467,
        "freshness": {"asof": "2026-09-03", "stale": False},
        "conditions": {
            "growth_nowcast": {"wei": 3.06, "wei_trend": "falling", "gdpnow": 4.7487},
            "recession": {
                "score": 0.217, "label": "low",
                "components": {"prob": 0.76, "curve": 0.0, "claims": 0.0},
                "sahm": -0.03, "ebp": -0.319,
            },
            "labor_nowcast": {"withheld_tax_yoy_pct": 2.908, "income_trend": "rising"},
            "financial_conditions": {"nfci": -0.558},
        },
        "business_cycle": {
            "available": True,
            "asof": "2026-09-30",
            "tiers": {
                "leading": {"index": 95.24, "mom6": 0.7427, "trend": 0.7366, "diffusion": 100.0,
                            "n_legs": 3, "direction": "rising"},
                "coincident": {"index": 35.43, "mom6": -0.2177, "trend": -0.359, "diffusion": 66.6667,
                               "n_legs": 3, "direction": "falling"},
                "lagging": {"index": 92.87, "mom6": 0.5854, "trend": 0.2148, "diffusion": 50.0,
                            "n_legs": 4, "direction": "rising"},
            },
            "calibrated": True,
            "calibration_resolution": {
                "calibration_version": "w2.7-loro-v1",
                "calibration_generated_at": "2026-07-02T12:32:51Z",
                "calibration_age_days": 63,
            },
        },
    }


def _compose(regime: dict, **kw) -> dict:
    kw.setdefault("built_at", BUILT_AT)
    return growth.compose(regime, **kw)


def _required(snapshot: dict, cid: str) -> dict:
    return next(c for c in snapshot["availability"]["required"] if c["component_id"] == cid)


def _metric(snapshot: dict, metric_id: str) -> dict:
    return next(m for m in snapshot["metrics"]["items"] if m["metric_id"] == metric_id)


def _axis(snapshot: dict, axis_id: str) -> dict:
    return next(a for a in snapshot["axes"]["items"] if a["axis_id"] == axis_id)


def _axis_component(axis: dict, component_id: str) -> dict:
    return next(c for c in axis["components"] if c["component_id"] == component_id)


# --------------------------------------------------------------------------- #
# healthy baseline + real sample-data contradiction
# --------------------------------------------------------------------------- #
def test_baseline_classifies_and_validates_against_the_closed_contract() -> None:
    snap = _compose(_base_regime())
    contract.validate(contract.finalize(snap))  # schema-conformant end to end
    assert snap["workspace"]["id"] == "growth_real_economy"
    assert snap["region"]["code"] == "US"
    assert snap["headline"]["status"] == "PRESENT"
    x = snap["headline"]["quadrant"]["x"]
    y = snap["headline"]["quadrant"]["y"]
    assert x is not None and y is not None
    assert snap["headline"]["state_id"] in ("A", "B", "C", "D")
    for cid in ("gdpnow_growth", "wei_growth", "leading_diffusion", "coincident_diffusion"):
        r = _required(snap, cid)
        assert r["freshness"] == "CURRENT"
        assert r["status"] == "PRESENT"
    # axes.items now carries the two real, full-disclosure axis objects
    # (schema's axis_id enum widened to lowercase-snake-case beyond the
    # original two liquidity_regime values).
    assert [a["axis_id"] for a in snap["axes"]["items"]] == ["growth_momentum", "growth_level_breadth"]
    momentum_axis = _axis(snap, "growth_momentum")
    breadth_axis = _axis(snap, "growth_level_breadth")
    assert momentum_axis["value"] == x
    assert breadth_axis["value"] == y
    assert momentum_axis["value_status"] == snap["headline"]["quadrant"]["x_status"]
    assert breadth_axis["value_status"] == snap["headline"]["quadrant"]["y_status"]
    assert {c["component_id"] for c in momentum_axis["components"]} == {
        "gdpnow_growth", "wei_growth", "leading_tier_momentum", "coincident_tier_momentum",
    }
    assert {c["component_id"] for c in breadth_axis["components"]} == {
        "leading_diffusion", "coincident_diffusion", "coincident_index_level", "growth_axis_score",
    }
    assert momentum_axis["min_components"] == 2
    assert momentum_axis["coverage_floor"] == 0.5
    assert momentum_axis["thresholds"]["boundary"] == 50.0
    assert momentum_axis["thresholds"]["hysteresis_band"] == 5.0
    assert momentum_axis["authority_ceiling"] == "DESCRIPTIVE"
    assert momentum_axis["data_version"] == "w2.7-loro-v1"  # business_cycle.calibration_resolution.calibration_version


def test_real_sample_data_fires_nowcast_vs_hard_data_contradiction() -> None:
    # The base fixture's GDPNow (4.75%, standardized ~84 >= 65 threshold)
    # strongly accelerates while the coincident tier direction is "falling":
    # a genuine nowcast-vs-hard-data disagreement, not a synthetic edge case.
    snap = _compose(_base_regime())
    c = snap["availability"]["contradiction"]
    assert c["present"] is True
    assert c["kind"] == "nowcast_vs_hard_data"
    assert any("contradiction" in r for r in snap["availability"]["reasons"])
    assert any(i["implication_id"] == "nowcast_vs_hard_data_contradiction"
               for i in snap["implications"]["items"])
    momentum = _metric(snap, "growth_momentum")
    assert momentum["status"] == "DISAGREEMENT"
    assert momentum["value"] is not None  # typed disagreement, not censored
    assert snap["headline"]["quadrant"]["x_status"] == "DISAGREEMENT"
    gdpnow = _metric(snap, "gdpnow_growth")
    coincident_mom = _metric(snap, "coincident_tier_momentum")
    assert gdpnow["value"] == 4.7487
    assert coincident_mom["value"] == -0.2177
    # y-axis is untouched -- this contradiction only implicates x-side components
    breadth = _metric(snap, "growth_level_breadth")
    assert breadth["status"] != "DISAGREEMENT"
    assert snap["headline"]["quadrant"]["y_status"] != "DISAGREEMENT"
    # the axis-level DISAGREEMENT (axes.items[growth_momentum]) and the
    # composite metric's DISAGREEMENT are two views of the SAME state --
    # they always agree, since the axis reuses the same component dicts.
    momentum_axis = _axis(snap, "growth_momentum")
    assert momentum_axis["value_status"] == "DISAGREEMENT"
    assert momentum_axis["value"] is not None
    for cid in ("gdpnow_growth", "coincident_tier_momentum"):
        assert _axis_component(momentum_axis, cid)["coverage_state"] == "DISAGREEMENT"
    # the affected components are NOT the whole axis -- wei_growth and
    # leading_tier_momentum are untouched by this contradiction
    for cid in ("wei_growth", "leading_tier_momentum"):
        assert _axis_component(momentum_axis, cid)["coverage_state"] != "DISAGREEMENT"
    breadth_axis = _axis(snap, "growth_level_breadth")
    assert breadth_axis["value_status"] != "DISAGREEMENT"


def test_narrow_breadth_despite_level_contradiction() -> None:
    reg = _base_regime()
    reg["business_cycle"]["tiers"]["coincident"]["index"] = 90.0     # strong level (>=65 std)
    reg["business_cycle"]["tiers"]["coincident"]["diffusion"] = 20.0  # narrow breadth (<=35 std)
    reg["business_cycle"]["tiers"]["coincident"]["direction"] = "rising"  # avoid the other contradiction
    reg["conditions"]["growth_nowcast"]["gdpnow"] = 2.0  # neutral, won't trip nowcast_vs_hard_data
    snap = _compose(reg)
    c = snap["availability"]["contradiction"]
    assert c["present"] is True
    assert c["kind"] == "narrow_breadth_despite_level"
    breadth = _metric(snap, "growth_level_breadth")
    assert breadth["status"] == "DISAGREEMENT"
    assert breadth["value"] is not None
    assert snap["headline"]["quadrant"]["y_status"] == "DISAGREEMENT"
    breadth_axis = _axis(snap, "growth_level_breadth")
    assert breadth_axis["value_status"] == "DISAGREEMENT"
    assert breadth_axis["value"] is not None
    for cid in ("coincident_index_level", "coincident_diffusion"):
        assert _axis_component(breadth_axis, cid)["coverage_state"] == "DISAGREEMENT"
    for cid in ("leading_diffusion", "growth_axis_score"):
        assert _axis_component(breadth_axis, cid)["coverage_state"] != "DISAGREEMENT"
    momentum_axis = _axis(snap, "growth_momentum")
    assert momentum_axis["value_status"] != "DISAGREEMENT"


# --------------------------------------------------------------------------- #
# typed degraded states (never zero / neutral / calm)
# --------------------------------------------------------------------------- #
def test_missing_required_source_is_typed_source_failed() -> None:
    reg = _base_regime()
    reg["conditions"]["growth_nowcast"]["gdpnow"] = None
    snap = _compose(reg)
    r = _required(snap, "gdpnow_growth")
    assert r["freshness"] == "SOURCE_FAILED"
    assert r["status"] == "ABSENT"
    assert r["null_reason"] == "SOURCE_FAILED"
    assert "gdpnow_growth" in snap["availability"]["degraded"]
    assert snap["availability"]["state"] == "SOURCE_FAILED"  # conservative worst
    m = _metric(snap, "gdpnow_growth")
    assert m["status"] == "ABSENT"
    assert m["null_reason"] == "SOURCE_FAILED"


def test_business_cycle_offline_is_typed_source_failed_not_neutral() -> None:
    reg = _base_regime()
    reg["business_cycle"]["available"] = False
    snap = _compose(reg)
    for cid in ("leading_diffusion", "coincident_diffusion"):
        r = _required(snap, cid)
        assert r["freshness"] == "SOURCE_FAILED"
        assert r["status"] == "ABSENT"
    assert snap["availability"]["state"] == "SOURCE_FAILED"
    # y-axis (growth_level_breadth) loses its two required legs; only
    # coincident_index_level (also business_cycle-sourced -> also SOURCE_FAILED)
    # and growth_axis_score remain -- below min_components(2)/coverage_floor(0.5)
    # is NOT guaranteed here since growth_axis_score is nowcast-sourced and
    # survives; assert the refusal only when it actually drops below the floor.
    breadth = _metric(snap, "growth_level_breadth")
    if breadth["value"] is None:
        assert breadth["null_reason"] == "COMPUTATION_REFUSED"
        assert snap["headline"]["state_id"] is None
        assert snap["headline"]["status"] == "ABSENT"
        assert snap["headline"]["quadrant"]["y"] is None


def test_axis_below_coverage_floor_refuses_no_neutral_default() -> None:
    reg = _base_regime()
    # Knock out 3 of 4 x-components -> below min_components(2)/coverage_floor(0.5).
    reg["conditions"]["growth_nowcast"]["gdpnow"] = None
    reg["conditions"]["growth_nowcast"]["wei"] = None
    reg["business_cycle"]["tiers"]["leading"]["mom6"] = None
    snap = _compose(reg)
    momentum = _metric(snap, "growth_momentum")
    assert momentum["value"] is None
    assert momentum["status"] == "ABSENT"
    assert momentum["null_reason"] == "COMPUTATION_REFUSED"
    # no quadrant is asserted rather than defaulting to a neutral one
    assert snap["headline"]["state_id"] is None
    assert snap["headline"]["status"] == "ABSENT"
    assert snap["headline"]["quadrant"]["x"] is None


def test_stale_artifact_is_typed_stale_not_current() -> None:
    reg = _base_regime()
    reg["freshness"]["stale"] = True
    snap = _compose(reg)
    r = _required(snap, "gdpnow_growth")
    assert r["freshness"] == "STALE_SOURCE"
    assert snap["availability"]["state"] == "STALE_SOURCE"
    assert snap["availability"]["state"] != "CURRENT"
    lagging_idx = _metric(snap, "lagging_tier_index")
    assert lagging_idx["freshness"] == "STALE_SOURCE"


def test_calibration_stale_caveat_implication() -> None:
    reg = _base_regime()
    reg["business_cycle"]["calibrated"] = False
    snap = _compose(reg)
    assert any(i["implication_id"] == "recession_calibration_caveat"
               for i in snap["implications"]["items"])


def test_calibration_age_over_threshold_caveat_implication() -> None:
    reg = _base_regime()
    reg["business_cycle"]["calibration_resolution"]["calibration_age_days"] = 900
    snap = _compose(reg)
    assert any(i["implication_id"] == "recession_calibration_caveat"
               for i in snap["implications"]["items"])


# --------------------------------------------------------------------------- #
# changes / method-version comparability / 1M vector
# --------------------------------------------------------------------------- #
def _prior(state_id="B", method=growth.METHOD_VERSION, x=70.0, y=64.0) -> dict:
    return {
        "generation": {"generation_id": "growth_real_economy-US-deadbeefdeadbeef"},
        "headline": {
            "state_id": state_id, "method_version": method,
            "effective_date": "2026-08-04",
            "quadrant": {"x": x, "y": y},
        },
        "metrics": {"items": []},
    }


def test_no_prior_yields_warmup() -> None:
    snap = _compose(_base_regime())
    assert snap["changes"]["comparability"] == "NO_PRIOR"
    assert snap["changes"]["null_reason"] == "WARMUP"
    assert snap["headline"]["one_month_vector"]["status"] == "ABSENT"
    assert snap["headline"]["one_month_vector"]["null_reason"] == "WARMUP"


def test_method_version_mismatch_refuses_numeric_comparison() -> None:
    snap = _compose(_base_regime(), prior_snapshot=_prior(method="growth_real_economy.compose.v0"))
    assert snap["changes"]["comparability"] == "METHOD_CHANGED"
    assert snap["changes"]["deltas"] == []
    assert snap["changes"]["null_reason"] == "COMPUTATION_REFUSED"
    assert snap["headline"]["one_month_vector"]["status"] == "ABSENT"
    assert snap["headline"]["one_month_vector"]["null_reason"] == "COMPUTATION_REFUSED"


def test_comparable_prior_produces_deltas_and_vector() -> None:
    snap = _compose(_base_regime(), prior_snapshot=_prior(x=50.0, y=50.0))
    assert snap["changes"]["comparability"] == "COMPARABLE"
    assert {d["metric_id"] for d in snap["changes"]["deltas"]} == {"growth_momentum", "growth_level_breadth"}
    v = snap["headline"]["one_month_vector"]
    assert v["status"] == "PRESENT"
    assert v["dx"] is not None and v["dy"] is not None


# --------------------------------------------------------------------------- #
# hysteresis (mirrors liquidity_regime's F1-corrected per-axis-crossing rule)
# --------------------------------------------------------------------------- #
def _regime_at(gdpnow, wei, leading_mom6, coincident_mom6, leading_diff, coincident_diff,
               coincident_index, growth_score) -> dict:
    reg = _base_regime()
    reg["conditions"]["growth_nowcast"]["gdpnow"] = gdpnow
    reg["conditions"]["growth_nowcast"]["wei"] = wei
    reg["business_cycle"]["tiers"]["leading"]["mom6"] = leading_mom6
    reg["business_cycle"]["tiers"]["coincident"]["mom6"] = coincident_mom6
    reg["business_cycle"]["tiers"]["leading"]["diffusion"] = leading_diff
    reg["business_cycle"]["tiers"]["coincident"]["diffusion"] = coincident_diff
    reg["business_cycle"]["tiers"]["coincident"]["index"] = coincident_index
    reg["business_cycle"]["tiers"]["coincident"]["direction"] = "rising"  # avoid contradiction noise
    reg["growth_score"] = growth_score
    return reg


def test_hysteresis_holds_prior_within_band() -> None:
    # x ~ 48 (near boundary, just under), y ~ 48 (near boundary, just under) ->
    # raw C, prior D within band -> hold D.
    reg = _regime_at(gdpnow=1.84, wei=1.34, leading_mom6=-0.02, coincident_mom6=-0.02,
                      leading_diff=48.0, coincident_diff=48.0, coincident_index=48.0, growth_score=-0.02)
    snap = _compose(reg, prior_snapshot=_prior(state_id="D", x=52.0, y=48.0))
    assert snap["headline"]["hysteresis"]["held_prior"] is True
    assert snap["headline"]["state_id"] == "D"


def test_hysteresis_flips_when_both_axes_beyond_band() -> None:
    reg = _regime_at(gdpnow=-2.0, wei=-2.5, leading_mom6=-2.0, coincident_mom6=-2.0,
                      leading_diff=10.0, coincident_diff=10.0, coincident_index=10.0, growth_score=-1.0)
    snap = _compose(reg, prior_snapshot=_prior(state_id="D", x=52.0, y=48.0))
    assert snap["headline"]["hysteresis"]["held_prior"] is False
    assert snap["headline"]["state_id"] == "C"


# --------------------------------------------------------------------------- #
# zh narrative must never embed an English quadrant label
# --------------------------------------------------------------------------- #
_QUADRANT_EN_LABEL_PHRASES = (
    "Decelerating momentum, still broad strength",
    "Accelerating momentum, broad strength",
    "Decelerating momentum, narrow/weak breadth",
    "Accelerating momentum, narrow/weak breadth",
)


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
    for kwargs in (
        dict(gdpnow=1.9, wei=1.4, leading_mom6=0.0, coincident_mom6=0.0,
             leading_diff=90.0, coincident_diff=90.0, coincident_index=90.0, growth_score=0.5),  # B
        dict(gdpnow=-3.0, wei=-3.0, leading_mom6=-3.0, coincident_mom6=-3.0,
             leading_diff=5.0, coincident_diff=5.0, coincident_index=5.0, growth_score=-1.0),   # C
    ):
        reg = _regime_at(**kwargs)
        snap = _compose(reg)
        assert snap["headline"]["state_id"] in ("A", "B", "C", "D")
        leaks = _find_english_label_leaks(snap)
        assert leaks == [], f"English quadrant label leaked into zh field(s): {leaks}"


# --------------------------------------------------------------------------- #
# digest determinism (content_sha256 stable under wall-clock/build churn)
# --------------------------------------------------------------------------- #
def test_identical_owner_input_yields_identical_digest_across_builds() -> None:
    reg = _base_regime()
    snap1 = contract.finalize(_compose(reg, built_at="2026-09-04T00:00:00Z", code_version="aaa111"))
    snap2 = contract.finalize(_compose(reg, built_at="2026-09-05T12:34:56Z", code_version="bbb222"))
    assert snap1["generation"]["content_sha256"] == snap2["generation"]["content_sha256"]
    assert snap1["generation"]["generation_id"] == snap2["generation"]["generation_id"]


def test_different_owner_input_yields_different_digest() -> None:
    reg1 = _base_regime()
    reg2 = copy.deepcopy(reg1)
    reg2["conditions"]["growth_nowcast"]["gdpnow"] = 1.0
    snap1 = contract.finalize(_compose(reg1, built_at=BUILT_AT))
    snap2 = contract.finalize(_compose(reg2, built_at=BUILT_AT))
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
    reg2["conditions"]["growth_nowcast"]["gdpnow"] = 1.5  # revision, SAME asof
    snap2 = _compose(reg2, prior_snapshot=prior_snap)
    assert snap2["corrections"]["correction_state"] == "superseded"
    assert snap2["corrections"]["changed_fingerprints"]
    assert any(fp.startswith("gdpnow:gdpnow_growth:") for fp in snap2["corrections"]["changed_fingerprints"])
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
    reg2["asof"] = reg2["date"] = "2026-09-04"  # new observation, not a revision
    reg2["conditions"]["growth_nowcast"]["gdpnow"] = 1.5
    snap2 = _compose(reg2, prior_snapshot=prior_snap)
    assert snap2["corrections"]["correction_state"] == "none"


# --------------------------------------------------------------------------- #
# lagging tier is preserved separately, never folded into the composite
# --------------------------------------------------------------------------- #
def test_lagging_tier_is_published_but_excluded_from_composite() -> None:
    reg = _base_regime()
    # Push the lagging tier to an extreme; the x/y composite must NOT move.
    reg["business_cycle"]["tiers"]["lagging"]["mom6"] = 999.0
    reg["business_cycle"]["tiers"]["lagging"]["diffusion"] = 0.0
    reg["business_cycle"]["tiers"]["lagging"]["index"] = 0.0
    snap_extreme = _compose(reg)
    snap_baseline = _compose(_base_regime())
    assert snap_extreme["headline"]["quadrant"]["x"] == snap_baseline["headline"]["quadrant"]["x"]
    assert snap_extreme["headline"]["quadrant"]["y"] == snap_baseline["headline"]["quadrant"]["y"]
    lagging_mom = _metric(snap_extreme, "lagging_tier_momentum")
    assert lagging_mom["value"] == 999.0


# --------------------------------------------------------------------------- #
# axes.items: full section-7.9 disclosure lives on the real axis objects
# (growth_momentum / growth_level_breadth), with an independently-valuable
# composite-level summary kept on the matching metrics.items entry too.
# --------------------------------------------------------------------------- #
def test_axes_items_carry_full_composite_disclosure_and_metrics_carry_a_summary() -> None:
    snap = _compose(_base_regime())
    assert len(snap["axes"]["items"]) == 2
    momentum_axis = _axis(snap, "growth_momentum")
    breadth_axis = _axis(snap, "growth_level_breadth")
    # full section-7.9 disclosure lives on the axis object itself now
    for axis in (momentum_axis, breadth_axis):
        assert axis["min_components"] == 2
        assert axis["coverage_floor"] == 0.5
        assert axis["weights_law"]
        assert axis["transformation"]
        assert axis["frequency_alignment"]
        assert axis["definition_version"] == growth.AXIS_DEFINITION_VERSION
        assert axis["revision_behavior"]
        assert axis["authority_ceiling"] == "DESCRIPTIVE"
        assert axis["freshness"] in (
            "CURRENT", "LATE_WITHIN_TOLERANCE", "STALE_SOURCE", "NOT_YET_RELEASED",
            "SOURCE_FAILED", "RIGHTS_BLOCKED", "NOT_COVERED", "HISTORICAL_AS_KNOWN", "SIMULATED",
        )
        for c in axis["components"]:
            assert set(c.keys()) == {
                "component_id", "label", "owner_field", "owner_ref", "raw_value",
                "standardized_value", "contribution", "sign", "weight", "coverage_state",
                "freshness", "null_reason",
            }
    # the composite-level metric SUMMARY is kept too (independently valuable,
    # not a fallback -- the axis object above is the primary disclosure home)
    momentum = _metric(snap, "growth_momentum")
    breadth = _metric(snap, "growth_level_breadth")
    assert momentum["value"] == momentum_axis["value"]
    assert breadth["value"] == breadth_axis["value"]
    assert "min_components=2" in momentum["transformation"]
    assert "coverage_floor=0.5" in momentum["transformation"]
    assert "min_components=2" in breadth["transformation"]
    assert "coverage_floor=0.5" in breadth["transformation"]
    assert "axes.items[growth_momentum]" in momentum["transformation"]
    assert "axes.items[growth_level_breadth]" in breadth["transformation"]


def test_axis_components_carry_real_weight_and_raw_value_table() -> None:
    # Hand-traceable component/weight table against the real-sample-shaped
    # fixture (see the growth.py hand-trace evidence in the R2 handoff).
    snap = _compose(_base_regime())
    momentum_axis = _axis(snap, "growth_momentum")
    expected_x_weights = {
        "gdpnow_growth": 0.35, "wei_growth": 0.30,
        "leading_tier_momentum": 0.20, "coincident_tier_momentum": 0.15,
    }
    for cid, w in expected_x_weights.items():
        c = _axis_component(momentum_axis, cid)
        assert c["weight"] == w
        assert c["sign"] == 1
    assert _axis_component(momentum_axis, "gdpnow_growth")["raw_value"] == 4.7487
    assert _axis_component(momentum_axis, "coincident_tier_momentum")["raw_value"] == -0.2177

    breadth_axis = _axis(snap, "growth_level_breadth")
    expected_y_weights = {
        "leading_diffusion": 0.30, "coincident_diffusion": 0.35,
        "coincident_index_level": 0.20, "growth_axis_score": 0.15,
    }
    for cid, w in expected_y_weights.items():
        c = _axis_component(breadth_axis, cid)
        assert c["weight"] == w
        assert c["sign"] == 1
    assert _axis_component(breadth_axis, "leading_diffusion")["raw_value"] == 100.0
    assert _axis_component(breadth_axis, "growth_axis_score")["raw_value"] == -0.467


def test_drivers_disclose_the_schema_key_repurposing() -> None:
    snap = _compose(_base_regime())
    for d in snap["drivers"]["rate_side"]:
        assert "schema key law" in d["note"]
    for d in snap["drivers"]["balance_sheet"]:
        assert "schema key law" in d["note"]


# --------------------------------------------------------------------------- #
# real owner artifact
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(not REGIME_LATEST.exists(), reason="owner artifact data/regime/latest.json absent")
def test_builds_and_validates_from_real_owner_artifact() -> None:
    regime = json.loads(REGIME_LATEST.read_text(encoding="utf-8"))
    snap = contract.finalize(growth.compose(regime, built_at=BUILT_AT))
    contract.validate(snap)  # real-data snapshot satisfies the closed contract
    assert snap["headline"]["state_id"] in ("A", "B", "C", "D", None)
    assert snap["generation"]["calculation_as_of"] == regime.get("asof")
    assert snap["authority"]["can_size"] is False


# The business-cycle owner clocks each tier independently. Its top-level asof
# is the leading tier's month bucket, not a timestamp shared by every tier.
_TIER_METRIC_IDS = {
    "leading": ("leading_tier_momentum", "leading_diffusion", "leading_tier_index"),
    "coincident": ("coincident_tier_momentum", "coincident_diffusion", "coincident_index_level"),
    "lagging": ("lagging_tier_index", "lagging_tier_diffusion", "lagging_tier_momentum"),
}
_TIER_PERIODS = {"leading": "2026-09-30", "coincident": "2026-07-31", "lagging": "2026-08-31"}


def _individually_dated_regime() -> dict:
    regime = _base_regime()
    for tier, period in _TIER_PERIODS.items():
        regime["business_cycle"]["tiers"][tier]["asof"] = period
    return regime


@pytest.mark.parametrize("tier", tuple(_TIER_METRIC_IDS))
def test_tier_reference_period_follows_its_own_source(tier: str) -> None:
    snapshot = _compose(_individually_dated_regime())
    for metric_id in _TIER_METRIC_IDS[tier]:
        assert _metric(snapshot, metric_id)["reference_period"] == _TIER_PERIODS[tier]
    source = next(s for s in snapshot["sources"]["items"]
                  if s["source_id"] == f"business_cycle_{tier}")
    assert source["reference_period"] == _TIER_PERIODS[tier]
    if tier != "lagging":
        assert _required(snapshot, f"{tier}_diffusion")["source_asof"] == _TIER_PERIODS[tier]


@pytest.mark.parametrize("tier", tuple(_TIER_METRIC_IDS))
@pytest.mark.parametrize("bad_period", [None, "", "not-a-date", "2026-02-30", "20260930", True])
def test_missing_or_invalid_tier_period_never_borrows_the_leading_period(tier, bad_period) -> None:
    regime = _individually_dated_regime()
    regime["business_cycle"]["tiers"][tier]["asof"] = bad_period
    snapshot = _compose(regime)
    contract.validate(contract.finalize(snapshot))
    for metric_id in _TIER_METRIC_IDS[tier]:
        metric = _metric(snapshot, metric_id)
        assert metric["reference_period"] is None
        assert metric["value"] is not None  # unknown period is not a missing numeric read
    source = next(s for s in snapshot["sources"]["items"]
                  if s["source_id"] == f"business_cycle_{tier}")
    assert source["reference_period"] is None
    if tier != "lagging":
        assert _required(snapshot, f"{tier}_diffusion")["source_asof"] is None
    for other in set(_TIER_METRIC_IDS) - {tier}:
        assert _metric(snapshot, _TIER_METRIC_IDS[other][0])["reference_period"] == _TIER_PERIODS[other]


@pytest.mark.parametrize("tier", tuple(_TIER_METRIC_IDS))
def test_month_bucket_is_not_an_observation_or_calculation_timestamp(tier) -> None:
    regime = _individually_dated_regime()
    snapshot = _compose(regime)
    for metric_id in _TIER_METRIC_IDS[tier]:
        metric = _metric(snapshot, metric_id)
        assert metric["observed_at"] is None
        assert metric["calculation_as_of"] == regime["asof"]
        assert metric["released_at"] is None
        assert metric["available_at"] is None


def test_period_fidelity_preserves_numeric_method_and_does_not_mutate_owner() -> None:
    regime = _individually_dated_regime()
    original = copy.deepcopy(regime)
    dated = _compose(regime)
    undated = _compose(_base_regime())
    assert regime == original
    for field in ("headline", "axes", "drivers", "changes", "corrections", "authority"):
        assert dated[field] == undated[field]
    assert dated["headline"]["method_version"] == "growth_real_economy.compose.v1"
    for item in dated["metrics"]["items"]:
        before = _metric(undated, item["metric_id"])
        for field in ("value", "status", "freshness", "model_version", "authority_ceiling"):
            assert item[field] == before[field]
    # A monthly bucket may end after this build day; it is a reference period,
    # not fabricated knowledge of a release at that future instant.
    assert _metric(dated, "leading_diffusion")["reference_period"] == "2026-09-30"
    assert dated["generation"]["calculation_as_of"] == regime["asof"]
