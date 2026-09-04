"""Composer tests for the US business_activity workspace (F01 / R2).

RED-first, mirroring tests/test_macro_workspace_liquidity_regime.py: every
degraded condition must produce the correct TYPED state and never a zero /
neutral / calm default. business_activity's specific twist is that the
blueprinted dual-axis headline (new demand/orders x production/utilization)
is ALWAYS typed ABSENT/COMPUTATION_REFUSED by design -- the owner artifact
(engine.business_cycle) only publishes blended tier composites, never the
individual orders/production/inventory legs -- so a large share of these
tests pin that refusal rather than a computed quadrant. See the module
docstring in engine/market_os/macro_workspaces/business_activity.py for the
full rationale.

    python3 -m pytest tests/test_macro_workspace_business_activity.py -x -q
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

from engine.market_os.macro_workspaces import business_activity, contract  # noqa: E402

BUILT_AT = "2026-09-04T00:00:00Z"
REGIME_LATEST = ROOT / "data" / "regime" / "latest.json"


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
def _base_bc() -> dict:
    """A healthy business_cycle block shaped exactly like the real published
    ``data/regime/latest.json#business_cycle`` (engine/business_cycle.py's
    ``business_cycle_snapshot()`` return value)."""
    return {
        "available": True,
        "asof": "2026-09-30",
        "tiers": {
            "leading": {"asof": "2026-09-30", "index": 95.24, "mom6": 0.74, "trend": 0.73,
                        "diffusion": 100.0, "n_legs": 8, "direction": "rising"},
            "coincident": {"asof": "2026-07-31", "index": 35.43, "mom6": -0.21, "trend": -0.35,
                          "diffusion": 66.66, "n_legs": 3, "direction": "falling"},
            "lagging": {"asof": "2026-07-31", "index": 92.86, "mom6": 0.58, "trend": 0.21,
                       "diffusion": 50.0, "n_legs": 4, "direction": "rising"},
        },
        "cl_ratio_mom6": -0.68,
        "recession_signal": {
            "available": True, "state": "off", "label": "no recession signal", "label_zh": "无衰退信号",
            "months_active": 40, "fired_on": None,
            "conditions": {"depth": False, "breadth": False, "diffusion_max": 50.0, "roc_threshold": -1.0},
        },
        "recession_now": False,
        "phase": {"label": "recovery", "label_zh": "复苏"},
        "measured": {"method": "LORO", "oos_catch_rate": 0.667, "oos_endogenous": 3, "oos_caught": 2},
        "calibrated": True,
        "calibration_resolution": {"threshold_source": "calibration", "reason": "version-matched + fresh"},
        "lag_passport": {"basis": "per_leg_schedule"},
        "shadow": None,
        "caveat": "tiny sample caveat", "caveat_zh": "样本极小的说明",
    }


def _base_regime() -> dict:
    return {"asof": "2026-09-30", "date": "2026-09-30", "business_cycle": _base_bc()}


def _compose(regime: dict, **kw) -> dict:
    return business_activity.compose(regime, built_at=BUILT_AT, **kw)


def _metric(snapshot: dict, metric_id: str) -> dict:
    return next(m for m in snapshot["metrics"]["items"] if m["metric_id"] == metric_id)


def _required(snapshot: dict, cid: str) -> dict:
    return next(c for c in snapshot["availability"]["required"] if c["component_id"] == cid)


def _implication(snapshot: dict, iid: str) -> dict | None:
    return next((i for i in snapshot["implications"]["items"] if i["implication_id"] == iid), None)


# --------------------------------------------------------------------------- #
# healthy baseline
# --------------------------------------------------------------------------- #
def test_baseline_publishes_real_tier_metrics_with_headline_absent_by_design() -> None:
    snap = _compose(_base_regime())
    assert snap["availability"]["state"] == "CURRENT"

    # headline is ALWAYS absent -- not a degraded state, a designed refusal
    h = snap["headline"]
    assert h["state_id"] is None
    assert h["status"] == "ABSENT"
    assert h["null_reason"] == "COMPUTATION_REFUSED"
    assert h["quadrant"] == {"x": None, "y": None, "x_status": "ABSENT", "y_status": "ABSENT"}
    assert h["hysteresis"]["applied"] is False

    # no axis / no axis-component drivers -- schema-legal empty arrays
    assert snap["axes"]["items"] == []
    assert snap["drivers"] == {"rate_side": [], "balance_sheet": []}

    # but the REAL owner-published tier composites flow through untouched
    li = _metric(snap, "leading_tier_index")
    assert li["value"] == 95.24 and li["status"] == "PRESENT" and li["freshness"] == "CURRENT"
    lm = _metric(snap, "leading_tier_momentum_6m")
    assert lm["value"] == 0.74 and lm["status"] == "PRESENT"
    ld = _metric(snap, "leading_tier_diffusion")
    assert ld["value"] == 100.0
    cn = _metric(snap, "coincident_tier_leg_count")
    assert cn["value"] == 3 and cn["status"] == "PRESENT"  # never refused by the coverage floor
    clm = _metric(snap, "coincident_lagging_ratio_momentum_6m")
    assert clm["value"] == -0.68

    for cid in ("leading_tier", "coincident_tier"):
        r = _required(snap, cid)
        assert r["freshness"] == "CURRENT"
        assert r["status"] == "PRESENT"


def test_implications_include_headline_unavailable_disclosure() -> None:
    snap = _compose(_base_regime())
    imp = _implication(snap, "headline_unavailable")
    assert imp is not None
    assert imp["evidence_class"] == "DESCRIPTIVE"
    assert "not separable" in imp["text"]["en"] or "blended" in imp["text"]["en"]


# --------------------------------------------------------------------------- #
# typed degraded states (never zero / neutral / calm)
# --------------------------------------------------------------------------- #
def test_business_cycle_unavailable_is_typed_source_failed() -> None:
    reg = _base_regime()
    reg["business_cycle"]["available"] = False
    snap = _compose(reg)
    li = _metric(snap, "leading_tier_index")
    assert li["status"] == "ABSENT" and li["null_reason"] == "SOURCE_FAILED" and li["freshness"] == "SOURCE_FAILED"
    r = _required(snap, "leading_tier")
    assert r["freshness"] == "SOURCE_FAILED" and r["status"] == "ABSENT"
    assert snap["availability"]["state"] == "SOURCE_FAILED"


def test_business_cycle_key_entirely_absent_is_typed_source_failed() -> None:
    reg = {"asof": "2026-09-30", "date": "2026-09-30"}  # no "business_cycle" key at all
    snap = _compose(reg)
    assert snap["availability"]["state"] == "SOURCE_FAILED"
    li = _metric(snap, "leading_tier_index")
    assert li["status"] == "ABSENT" and li["null_reason"] == "SOURCE_FAILED"


def test_missing_required_tier_is_typed_source_failed_without_affecting_the_other() -> None:
    reg = _base_regime()
    del reg["business_cycle"]["tiers"]["coincident"]
    snap = _compose(reg)
    ci = _metric(snap, "coincident_tier_index")
    assert ci["status"] == "ABSENT" and ci["null_reason"] == "SOURCE_FAILED"
    r = _required(snap, "coincident_tier")
    assert r["status"] == "ABSENT" and r["null_reason"] == "SOURCE_FAILED"
    # leading (the OTHER required tier) is unaffected
    li = _metric(snap, "leading_tier_index")
    assert li["status"] == "PRESENT"
    assert snap["availability"]["state"] == "SOURCE_FAILED"  # conservative worst over required set


def test_optional_lagging_tier_missing_does_not_degrade_page_availability() -> None:
    reg = _base_regime()
    del reg["business_cycle"]["tiers"]["lagging"]
    snap = _compose(reg)
    lg = _metric(snap, "lagging_tier_index")
    assert lg["status"] == "ABSENT" and lg["null_reason"] == "SOURCE_FAILED"
    # lagging is NOT in the required set -> page-level availability stays CURRENT
    assert snap["availability"]["state"] == "CURRENT"
    opt = _required(snap, "lagging_tier")
    assert opt["required"] is False
    assert opt["status"] == "ABSENT"


def test_low_leg_coverage_refuses_tier_value_but_leg_count_stays_honest() -> None:
    reg = _base_regime()
    # coincident has 4 configured legs; 1 live leg is below both TIER_MIN_LEGS(2)
    # and the 0.5 coverage floor -> the composite must be refused, not published
    # as if trustworthy at n=1.
    reg["business_cycle"]["tiers"]["coincident"]["n_legs"] = 1
    snap = _compose(reg)
    ci = _metric(snap, "coincident_tier_index")
    assert ci["value"] is None
    assert ci["status"] == "ABSENT"
    assert ci["null_reason"] == "COMPUTATION_REFUSED"
    # the tier is still structurally PRESENT/CURRENT (this is a confidence
    # refusal, not a source failure) -- freshness stays CURRENT
    assert ci["freshness"] == "CURRENT"
    # the raw leg count itself is never refused -- it IS the honesty flag
    cn = _metric(snap, "coincident_tier_leg_count")
    assert cn["value"] == 1
    assert cn["status"] == "PRESENT"
    r = _required(snap, "coincident_tier")
    assert r["status"] == "PARTIAL"
    assert r["null_reason"] == "COMPUTATION_REFUSED"
    # freshness-only availability roll-up is unaffected by the coverage floor
    assert snap["availability"]["state"] == "CURRENT"


def test_survey_lane_is_always_typed_rights_blocked() -> None:
    for reg in (_base_regime(), {"asof": "2026-09-30", "date": "2026-09-30"}):
        snap = _compose(reg)
        pmi = _metric(snap, "survey_composite_pmi")
        assert pmi["value"] is None
        assert pmi["status"] == "ABSENT"
        assert pmi["null_reason"] == "RIGHTS_BLOCKED"
        assert pmi["freshness"] == "RIGHTS_BLOCKED"
        assert pmi["rights_state"] == "RIGHTS_BLOCKED"
    imp = _implication(_compose(_base_regime()), "survey_lane_unavailable")
    assert imp is not None


def test_granular_blueprint_items_are_refused_not_fabricated() -> None:
    snap = _compose(_base_regime())
    for mid in ("new_orders_demand", "production_utilization", "inventory_cycle_phase",
               "capex_orders_growth", "shipments_sales_growth"):
        m = _metric(snap, mid)
        assert m["value"] is None
        assert m["status"] == "ABSENT"
        assert m["null_reason"] == "COMPUTATION_REFUSED"


# --------------------------------------------------------------------------- #
# contradiction / DISAGREEMENT (owner's own 3 D's depth-vs-breadth divergence)
# --------------------------------------------------------------------------- #
def test_depth_breadth_divergence_is_typed_disagreement() -> None:
    reg = _base_regime()
    reg["business_cycle"]["recession_signal"]["conditions"]["depth"] = True
    reg["business_cycle"]["recession_signal"]["conditions"]["breadth"] = False
    snap = _compose(reg)
    c = snap["availability"]["contradiction"]
    assert c["present"] is True
    assert c["kind"] == "depth_breadth_divergence"
    assert any("contradiction" in r for r in snap["availability"]["reasons"])
    mom = _metric(snap, "leading_tier_momentum_6m")
    diff = _metric(snap, "leading_tier_diffusion")
    assert mom["status"] == "DISAGREEMENT" and mom["null_reason"] == "DISAGREEMENT"
    assert diff["status"] == "DISAGREEMENT" and diff["null_reason"] == "DISAGREEMENT"
    # value stays published -- typed disagreement, not censoring
    assert mom["value"] is not None and diff["value"] is not None
    assert any(i["implication_id"] == "depth_breadth_divergence" for i in snap["implications"]["items"])
    # the OTHER tiers are untouched
    ci = _metric(snap, "coincident_tier_momentum_6m")
    assert ci["status"] != "DISAGREEMENT"


def test_depth_breadth_agreement_never_fires_contradiction() -> None:
    for depth, breadth in ((False, False), (True, True)):
        reg = _base_regime()
        reg["business_cycle"]["recession_signal"]["conditions"]["depth"] = depth
        reg["business_cycle"]["recession_signal"]["conditions"]["breadth"] = breadth
        snap = _compose(reg)
        assert snap["availability"]["contradiction"]["present"] is False


# --------------------------------------------------------------------------- #
# changes / method-version comparability
# --------------------------------------------------------------------------- #
def _prior(method=business_activity.METHOD_VERSION, gen_id="business_activity-US-deadbeefdeadbeef",
          eff="2026-08-31", leading_mom=0.4) -> dict:
    return {
        "generation": {"generation_id": gen_id},
        "headline": {"method_version": method, "effective_date": eff},
        "metrics": {"items": [
            {"metric_id": "leading_tier_momentum_6m", "value": leading_mom},
            {"metric_id": "coincident_tier_momentum_6m", "value": -0.5},
            {"metric_id": "lagging_tier_momentum_6m", "value": 0.3},
            {"metric_id": "coincident_lagging_ratio_momentum_6m", "value": -0.2},
        ]},
    }


def test_no_prior_yields_warmup() -> None:
    snap = _compose(_base_regime())
    assert snap["changes"]["comparability"] == "NO_PRIOR"
    assert snap["changes"]["null_reason"] == "WARMUP"


def test_method_version_mismatch_refuses_numeric_comparison() -> None:
    snap = _compose(_base_regime(), prior_snapshot=_prior(method="business_activity.compose.v0"))
    assert snap["changes"]["comparability"] == "METHOD_CHANGED"
    assert snap["changes"]["deltas"] == []
    assert snap["changes"]["null_reason"] == "COMPUTATION_REFUSED"


def test_comparable_prior_produces_real_deltas() -> None:
    snap = _compose(_base_regime(), prior_snapshot=_prior(leading_mom=0.4))
    assert snap["changes"]["comparability"] == "COMPARABLE"
    d = next(x for x in snap["changes"]["deltas"] if x["metric_id"] == "leading_tier_momentum_6m")
    assert d["prior_value"] == 0.4
    assert d["current_value"] == 0.74
    assert abs(d["delta"] - 0.34) < 1e-9


# --------------------------------------------------------------------------- #
# corrections / supersession honesty
# --------------------------------------------------------------------------- #
def test_corrections_none_for_first_print() -> None:
    snap = _compose(_base_regime())
    assert snap["corrections"]["correction_state"] == "none"
    assert snap["corrections"]["predecessor_generation_id"] is None


def test_corrections_superseded_when_same_period_tier_value_changes() -> None:
    reg = _base_regime()
    prior_snap = contract.finalize(_compose(reg))
    reg2 = copy.deepcopy(reg)
    reg2["business_cycle"]["tiers"]["leading"]["mom6"] = 2.5  # revision, SAME asof
    snap2 = _compose(reg2, prior_snapshot=prior_snap)
    assert snap2["corrections"]["correction_state"] == "superseded"
    assert any(fp.startswith("business_cycle:leading_tier_momentum_6m:")
               for fp in snap2["corrections"]["changed_fingerprints"])
    assert snap2["corrections"]["predecessor_generation_id"] == prior_snap["generation"]["generation_id"]


def test_corrections_none_when_same_period_no_change() -> None:
    reg = _base_regime()
    prior_snap = contract.finalize(_compose(reg))
    snap2 = _compose(copy.deepcopy(reg), prior_snapshot=prior_snap)
    assert snap2["corrections"]["correction_state"] == "none"
    assert snap2["corrections"]["changed_fingerprints"] == []


def test_corrections_none_when_reference_period_advances() -> None:
    reg = _base_regime()
    prior_snap = contract.finalize(_compose(reg))
    reg2 = copy.deepcopy(reg)
    reg2["business_cycle"]["asof"] = "2026-10-31"
    reg2["asof"] = reg2["date"] = "2026-10-31"
    reg2["business_cycle"]["tiers"]["leading"]["mom6"] = 2.5
    snap2 = _compose(reg2, prior_snapshot=prior_snap)
    assert snap2["corrections"]["correction_state"] == "none"


# --------------------------------------------------------------------------- #
# digest determinism (content_sha256 excludes generation/build-provenance)
# --------------------------------------------------------------------------- #
def test_digest_is_deterministic_for_identical_owner_input() -> None:
    reg = _base_regime()
    snap1 = contract.finalize(_compose(reg))
    snap2 = contract.finalize(_compose(reg))
    assert snap1["generation"]["content_sha256"] == snap2["generation"]["content_sha256"]
    assert snap1["generation"]["generation_id"] == snap2["generation"]["generation_id"]


def test_digest_unaffected_by_built_at_or_code_version() -> None:
    reg = _base_regime()
    body1 = business_activity.compose(reg, built_at="2026-01-01T00:00:00Z", code_version="aaa111")
    body2 = business_activity.compose(reg, built_at="2099-12-31T23:59:59Z", code_version="bbb222")
    snap1, snap2 = contract.finalize(body1), contract.finalize(body2)
    assert snap1["generation"]["content_sha256"] == snap2["generation"]["content_sha256"]


def test_digest_changes_when_owner_data_changes() -> None:
    reg1 = _base_regime()
    reg2 = copy.deepcopy(reg1)
    reg2["business_cycle"]["tiers"]["leading"]["mom6"] = 9.99
    snap1 = contract.finalize(_compose(reg1))
    snap2 = contract.finalize(_compose(reg2))
    assert snap1["generation"]["content_sha256"] != snap2["generation"]["content_sha256"]


# --------------------------------------------------------------------------- #
# zh-label integrity
# --------------------------------------------------------------------------- #
_EN_ONLY_LABEL_PHRASES = ("Leading tier", "Coincident tier", "Lagging tier", "New demand", "Business Activity")


def _find_english_label_leaks(node, path: str = "$") -> list[tuple[str, str, str]]:
    """Walk every bilingual {"en": ..., "zh": ...} pair and flag any zh string
    that contains an English-only label phrase (the F11 bug class: a shared
    interpolation variable leaking the English label into the zh narrative
    instead of the zh label)."""
    leaks: list[tuple[str, str, str]] = []
    if isinstance(node, dict):
        zh = node.get("zh")
        if "en" in node and isinstance(zh, str):
            for phrase in _EN_ONLY_LABEL_PHRASES:
                if phrase in zh:
                    leaks.append((path, phrase, zh))
        for k, v in node.items():
            leaks.extend(_find_english_label_leaks(v, f"{path}.{k}"))
    elif isinstance(node, list):
        for idx, v in enumerate(node):
            leaks.extend(_find_english_label_leaks(v, f"{path}[{idx}]"))
    return leaks


def test_zh_fields_never_embed_english_only_label_phrases() -> None:
    reg = _base_regime()
    reg["business_cycle"]["recession_signal"]["conditions"]["depth"] = True
    reg["business_cycle"]["recession_signal"]["conditions"]["breadth"] = False
    snap = _compose(reg)  # exercise the contradiction + all tier-read implications too
    leaks = _find_english_label_leaks(snap)
    assert leaks == [], f"English-only label phrase leaked into zh field(s): {leaks}"


def test_every_bilingual_pair_has_a_zh_value_when_en_is_present() -> None:
    def _walk(node, path="$"):
        missing = []
        if isinstance(node, dict):
            if "en" in node and "zh" in node and isinstance(node.get("en"), str) and node.get("zh") is None:
                missing.append(path)
            for k, v in node.items():
                missing.extend(_walk(v, f"{path}.{k}"))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                missing.extend(_walk(v, f"{path}[{i}]"))
        return missing
    snap = _compose(_base_regime())
    assert _walk(snap) == []


# --------------------------------------------------------------------------- #
# schema validation
# --------------------------------------------------------------------------- #
def test_schema_validates_the_full_snapshot() -> None:
    snap = contract.finalize(_compose(_base_regime()))
    contract.validate(snap)  # raises ContractError on any violation
    assert snap["axes"]["items"] == []
    assert snap["drivers"] == {"rate_side": [], "balance_sheet": []}
    assert snap["authority"]["can_size"] is False
    assert snap["authority"]["axis_authority_ceiling"] == "DESCRIPTIVE"


def test_schema_validates_every_degraded_fixture() -> None:
    """Every typed-degradation fixture above must ALSO satisfy the closed
    contract -- a refusal must never be an invalid document."""
    fixtures = []
    reg = _base_regime()
    reg["business_cycle"]["available"] = False
    fixtures.append(reg)
    reg2 = _base_regime()
    del reg2["business_cycle"]["tiers"]["coincident"]
    fixtures.append(reg2)
    reg3 = _base_regime()
    reg3["business_cycle"]["tiers"]["coincident"]["n_legs"] = 1
    fixtures.append(reg3)
    reg4 = _base_regime()
    reg4["business_cycle"]["recession_signal"]["conditions"]["depth"] = True
    reg4["business_cycle"]["recession_signal"]["conditions"]["breadth"] = False
    fixtures.append(reg4)
    for reg in fixtures:
        snap = contract.finalize(_compose(reg))
        contract.validate(snap)


# --------------------------------------------------------------------------- #
# real owner artifact
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(not REGIME_LATEST.exists(), reason="owner artifact data/regime/latest.json absent")
def test_builds_and_validates_from_real_owner_artifact() -> None:
    regime = json.loads(REGIME_LATEST.read_text(encoding="utf-8"))
    snap = contract.finalize(business_activity.compose(regime, built_at=BUILT_AT))
    contract.validate(snap)  # real-data snapshot satisfies the closed contract
    assert snap["headline"]["state_id"] is None  # always, by design
    assert snap["generation"]["calculation_as_of"] == (regime.get("business_cycle") or {}).get("asof")
    assert snap["authority"]["can_size"] is False
