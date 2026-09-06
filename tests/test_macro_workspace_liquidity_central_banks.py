"""Composer tests for the US liquidity_central_banks workspace (F01 / R3).

RED-first: each degraded condition must produce the correct TYPED state and
never a zero / neutral / calm default. Covers: the NOT_APPLICABLE headline
shape (this workspace has no headline model at all in architecture 10.9 -
see liquidity_central_banks.py's module docstring), the W-FRI weekly-grid
freshness law (CURRENT/LATE_WITHIN_TOLERANCE/STALE_SOURCE boundaries), the
disclosed WALCL units defect (sanity check -> typed SOURCE_FAILED, never
rescaled), the 52-week monetary_impulse_z warmup, the owner's quality-
degraded no-look-ahead passthrough, the global-state-vs-Fed-desk
contradiction (fires / stays silent), digest determinism with a genuinely-
consumed-field mutation and an unconsumed-field negative control, a prose
scan for raw enum-token leaks, zh-narrative integrity, schema validation,
and a real-owner-artifact build across the two owner inputs (GLT + cb_desk).

    python3 -m pytest tests/test_macro_workspace_liquidity_central_banks.py -x -q
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

from engine.market_os.macro_workspaces import contract, liquidity_central_banks  # noqa: E402

BUILT_AT = "2026-09-04T00:00:00Z"
GLT_LATEST = ROOT / "site" / "liquiditydata" / "global_liquidity_transmission.json"
INTL_RISK_LATEST = ROOT / "data" / "intl_risk" / "latest.json"
GLT_HISTORY_META = ROOT / "data" / "global_liquidity_transmission" / "state_history_meta.json"


# --------------------------------------------------------------------------- #
# fixtures (trimmed, representative subsets of the real owner artifacts)
# --------------------------------------------------------------------------- #
def _base_glt() -> dict:
    return {
        "meta": {
            "schema": "global_liquidity_transmission.v1",
            "model_version": "glt_state.v1",
            "producer_version": "w-liq.1.0",
            "owner": "Macro/Data Producer W-LIQ.1",
            "frequency": "W-FRI",
            "generated_at": "2026-09-04T11:03:41.497178+00:00",
            "architecture_authority": "Mastermind issue #117; orchestration and acceptance authority Mastermind issue #123",
        },
        "freshness": {
            "status": "fresh",
            "degraded": False,
            "monetary_coverage_ratio": 1.0,
            "funding_coverage_ratio": 1.0,
            "clocks": {
                "evidence_available_at": "2026-08-28T00:00:00Z",
                "first_known_at": "2026-09-04T11:03:41.497178Z",
            },
            "component_snapshot": {
                "monetary": {
                    "fed": {"current_contribution_z": 0.970391},
                    "ecb": {"current_contribution_z": 1.008565},
                    "boj": {"current_contribution_z": 0.850842},
                },
                "usd_funding": {
                    "broad_dollar": {"current_contribution_z": 0.261985},
                    "high_yield_oas": {"current_contribution_z": 0.05906},
                    "real_yield_10y": {"current_contribution_z": -0.755348},
                },
            },
            "components": {
                "monetary": {
                    "fed": {"status": "usable"},
                    "ecb": {"status": "usable"},
                    "boj": {"status": "usable"},
                },
                "usd_funding": {
                    "broad_dollar": {"status": "usable"},
                    "high_yield_oas": {"status": "usable"},
                    "real_yield_10y": {"status": "usable"},
                },
            },
        },
        "quality": {
            "status": "degraded",
            "degraded": True,
            "event_quality": "mixed",
            "missing_or_stale": [],
            "confidence": {
                "kind": "data_lineage_and_coverage_only",
                "value": 0.833333,
                "not": ["predictive_probability", "alpha_confidence", "promotion_grade"],
            },
            "global_credit": {
                "status": "insufficient_comparable_pit_coverage",
                "reason": "US C&I loans and China TSF are different constructs.",
                "credit_impulse_global": None,
                "components": {
                    "china_total_social_financing": {"direction": "weakening", "status": "context_only"},
                    "us_bank_credit": {"direction": "improving", "status": "context_only"},
                },
            },
            "us_liquidity_quality": None,
        },
        "state": {
            "asof": "2026-08-28",
            "label": "flat",
            "monetary_impulse": 0.003956,
            "monetary_impulse_z": 0.077032,
            "monetary_stance": 0.943266,
            "orthogonalised_impulse": 0.0165,
            "liquidity_breadth": 0.333333,
            "usd_funding_impulse": -0.144768,
            "policy_liquidity_impulse": 0.003956,
            "credit_impulse_global": None,
            "event_reference": {
                "quality": "mixed",
                "confidence": 0.833333,
                "conditions": {"us_liquidity_quality": "unknown", "usd_funding_impulse": -0.144768},
            },
        },
    }


def _base_cb_desk() -> dict:
    return {
        "as_of": "2026-09-03",
        "built": "2026-09-04T12:23:01.174224+00:00",
        "cbs": [
            {"id": "FED", "policy_rate": 3.63, "asof": "2026-09-02", "stale": False,
             "last_change": {"date": "2026-05-07", "direction": "cut", "bp": -1.0},
             "bs_impulse": {"impulse_13w": 0.38, "impulse_52w": 2.05, "level": 6737204.0,
                            "asof": "2026-09-02",
                            "unit": "USD billions (×1, raw WALCL is in billions)",
                            "series": "WALCL"}},
            {"id": "ECB", "policy_rate": 2.25, "asof": "2026-09-03", "stale": False,
             "last_change": {"date": "2026-06-17", "direction": "hike", "bp": 25.0},
             "bs_impulse": {"impulse_13w": -4.0, "impulse_52w": -2.86, "level": 5915343.0,
                            "asof": "2026-08-28", "unit": "EUR billions", "series": "ECBASSETSW"}},
            {"id": "BOJ", "policy_rate": 0.841, "asof": "2026-06-01", "stale": True,
             "last_change": {"date": "2026-06-01", "direction": "hike", "bp": 11.4},
             "bs_impulse": {"impulse_13w": -10.64, "impulse_52w": -12.73, "level": 6446620.0,
                            "asof": "2026-08-01", "unit": "JPY trillions", "series": "JPNASSETS"}},
        ],
    }


def _base_hist() -> dict:
    return {
        "artifact": "data/global_liquidity_transmission/state_history.parquet",
        "rows": 1483,
        "first_asof": "1998-04-03",
        "last_asof": "2026-08-28",
    }


def _compose(glt=None, cbd=None, hist=None, **kw) -> dict:
    return liquidity_central_banks.compose(
        glt if glt is not None else _base_glt(),
        cbd if cbd is not None else _base_cb_desk(),
        hist if hist is not None else _base_hist(),
        built_at=BUILT_AT, **kw,
    )


def _metric(snapshot: dict, metric_id: str) -> dict:
    return next(m for m in snapshot["metrics"]["items"] if m["metric_id"] == metric_id)


def _required(snapshot: dict, cid: str) -> dict:
    return next(c for c in snapshot["availability"]["required"] if c["component_id"] == cid)


# --------------------------------------------------------------------------- #
# healthy baseline (mirrors the REAL owner artifacts: quality.degraded=True
# from global_credit context, WALCL units defect present, GLT label="flat" so
# no Fed-desk contradiction fires)
# --------------------------------------------------------------------------- #
def test_baseline_all_required_sources_current() -> None:
    snap = _compose()
    assert snap["workspace"]["id"] == "liquidity_central_banks"
    assert snap["region"]["code"] == "US"
    for cid in ("glt_monetary_impulse", "glt_liquidity_breadth",
                "glt_usd_funding_impulse", "cb_fed_balance_sheet_impulse_13w"):
        r = _required(snap, cid)
        assert r["freshness"] == "CURRENT", (cid, r)
        assert r["status"] == "PRESENT"
    assert snap["availability"]["state"] == "CURRENT"


def test_baseline_no_contradiction_when_glt_reads_flat() -> None:
    snap = _compose()
    c = snap["availability"]["contradiction"]
    assert c["present"] is False
    assert c["kind"] is None


def test_baseline_quality_degraded_reason_surfaces_despite_current_freshness() -> None:
    # quality.status=="degraded" (owner-level, driven by global_credit context)
    # is a DIFFERENT signal from freshness.status=="fresh" -- the required
    # components can legitimately read CURRENT while this diagnostic reason
    # is still honestly surfaced (never smoothed over).
    snap = _compose()
    assert any(r.startswith("glt_quality_status=degraded") for r in snap["availability"]["reasons"])
    assert any(i["implication_id"] == "glt_quality_degraded_passthrough"
               for i in snap["implications"]["items"])


def test_baseline_walcl_defect_fires_by_default() -> None:
    # The real cb_desk artifact's FED bs_impulse carries the disclosed units
    # defect (level in millions, labeled "USD billions") -- the baseline
    # fixture mirrors that, so this fires without any special setup.
    snap = _compose()
    m = _metric(snap, "cb_fed_balance_sheet_level")
    assert m["value"] is None
    assert m["status"] == "ABSENT"
    assert m["null_reason"] == "SOURCE_FAILED"
    assert "implausible" in m["transformation"]
    assert any(i["implication_id"] == "fed_balance_sheet_level_unit_defect"
               for i in snap["implications"]["items"])
    # the unit-free 13w/52w legs are unaffected
    m13 = _metric(snap, "cb_fed_balance_sheet_impulse_13w")
    assert m13["value"] == 0.38
    assert m13["status"] == "PRESENT"


# --------------------------------------------------------------------------- #
# NOT_APPLICABLE headline / empty axes (this workspace has no headline model)
# --------------------------------------------------------------------------- #
def test_headline_is_not_applicable_by_design() -> None:
    snap = _compose()
    h = snap["headline"]
    assert h["state_id"] is None
    assert h["status"] == "ABSENT"
    assert h["null_reason"] == "NOT_APPLICABLE"
    assert h["quadrant"] == {"x": None, "y": None, "x_status": "ABSENT", "y_status": "ABSENT"}
    assert h["nearest_boundary"]["null_reason"] == "NOT_APPLICABLE"
    assert h["one_month_vector"]["null_reason"] == "NOT_APPLICABLE"
    assert h["hysteresis"]["applied"] is False
    assert "no headline model at all" in h["hysteresis"]["note"]


def test_axes_items_is_empty_by_design() -> None:
    snap = _compose()
    assert snap["axes"]["items"] == []


# --------------------------------------------------------------------------- #
# typed degraded states (never zero / neutral / calm)
# --------------------------------------------------------------------------- #
def test_missing_glt_artifact_is_typed_source_failed() -> None:
    snap = _compose(glt={})
    r = _required(snap, "glt_monetary_impulse")
    assert r["freshness"] == "SOURCE_FAILED"
    assert r["status"] == "ABSENT"
    assert r["null_reason"] == "SOURCE_FAILED"
    assert snap["availability"]["state"] == "SOURCE_FAILED"
    m = _metric(snap, "glt_monetary_impulse")
    assert m["value"] is None and m["status"] == "ABSENT"


def test_missing_cb_desk_artifact_is_typed_source_failed() -> None:
    snap = _compose(cbd={})
    r = _required(snap, "cb_fed_balance_sheet_impulse_13w")
    assert r["freshness"] == "SOURCE_FAILED"
    assert r["status"] == "ABSENT"
    m = _metric(snap, "cb_fed_balance_sheet_level")
    assert m["value"] is None
    assert "No balance-sheet data reported for FED" in m["transformation"]


def test_missing_fed_row_is_typed_source_failed() -> None:
    cbd = copy.deepcopy(_base_cb_desk())
    cbd["cbs"] = [c for c in cbd["cbs"] if c["id"] != "FED"]
    snap = _compose(cbd=cbd)
    r = _required(snap, "cb_fed_balance_sheet_impulse_13w")
    assert r["freshness"] == "SOURCE_FAILED"
    assert r["status"] == "ABSENT"
    assert r["null_reason"] == "SOURCE_FAILED"
    assert "cb_fed_balance_sheet_impulse_13w" in snap["availability"]["degraded"]


def test_missing_liquidity_breadth_is_typed_source_failed_without_affecting_siblings() -> None:
    glt = copy.deepcopy(_base_glt())
    glt["state"]["liquidity_breadth"] = None
    snap = _compose(glt=glt)
    r = _required(snap, "glt_liquidity_breadth")
    assert r["freshness"] == "SOURCE_FAILED"
    assert r["status"] == "ABSENT"
    # sibling required components (from the SAME owner state object) are
    # unaffected -- freshness must reflect THIS field's own presence only.
    r2 = _required(snap, "glt_monetary_impulse")
    assert r2["status"] == "PRESENT"
    assert r2["freshness"] == "CURRENT"


def test_missing_usd_funding_impulse_is_typed_source_failed() -> None:
    glt = copy.deepcopy(_base_glt())
    glt["state"]["usd_funding_impulse"] = None
    snap = _compose(glt=glt)
    r = _required(snap, "glt_usd_funding_impulse")
    assert r["freshness"] == "SOURCE_FAILED"
    m = _metric(snap, "glt_usd_funding_impulse")
    assert m["value"] is None and m["status"] == "ABSENT"


def test_credit_impulse_global_is_refused_not_covered() -> None:
    snap = _compose()
    m = _metric(snap, "glt_credit_impulse_global")
    assert m["value"] is None
    assert m["status"] == "ABSENT"
    assert m["null_reason"] == "NOT_COVERED"
    assert "insufficient_comparable_pit_coverage" in m["transformation"]


# --------------------------------------------------------------------------- #
# owner "unusable" per-leg receipt is typed stale, never date-math CURRENT
# --------------------------------------------------------------------------- #
def test_owner_unusable_leg_receipt_downgrades_that_legs_freshness_only() -> None:
    glt = copy.deepcopy(_base_glt())
    glt["freshness"]["components"]["monetary"]["fed"]["status"] = "stale"
    snap = _compose(glt=glt)
    m = _metric(snap, "glt_fed_monetary_contribution_z")
    assert m["freshness"] == "STALE_SOURCE"
    # a sibling leg with a healthy receipt is unaffected
    m2 = _metric(snap, "glt_ecb_monetary_contribution_z")
    assert m2["freshness"] == "CURRENT"


def test_owner_freshness_degraded_flag_downgrades_required_components() -> None:
    glt = copy.deepcopy(_base_glt())
    glt["freshness"]["status"] = "degraded"
    glt["freshness"]["degraded"] = True
    snap = _compose(glt=glt)
    r = _required(snap, "glt_monetary_impulse")
    assert r["freshness"] == "STALE_SOURCE"
    assert r["freshness"] != "CURRENT"
    assert snap["availability"]["state"] != "CURRENT"


# --------------------------------------------------------------------------- #
# W-FRI weekly-grid release-lag law: CURRENT / LATE_WITHIN_TOLERANCE / STALE.
# BUILT_AT is held fixed (never overridden -- the composer never reads a wall
# clock) and glt.state.asof is varied instead, which has the identical effect
# on the computed age.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("glt_asof,expected", [
    ("2026-09-04", "CURRENT"),                # age 0
    ("2026-08-28", "CURRENT"),                 # age 7 (boundary)
    ("2026-08-27", "LATE_WITHIN_TOLERANCE"),   # age 8
    ("2026-08-24", "LATE_WITHIN_TOLERANCE"),   # age 11 (boundary)
    ("2026-08-23", "STALE_SOURCE"),            # age 12
])
def test_glt_wfri_freshness_tiers(glt_asof: str, expected: str) -> None:
    glt = copy.deepcopy(_base_glt())
    glt["state"]["asof"] = glt_asof
    snap = _compose(glt=glt)
    r = _required(snap, "glt_monetary_impulse")
    assert r["freshness"] == expected


def test_glt_asof_after_built_at_is_source_failed() -> None:
    glt = copy.deepcopy(_base_glt())
    glt["state"]["asof"] = "2026-09-05"  # AFTER BUILT_AT (2026-09-04)
    snap = _compose(glt=glt)
    r = _required(snap, "glt_monetary_impulse")
    assert r["freshness"] == "SOURCE_FAILED"


# --------------------------------------------------------------------------- #
# 52-week monetary_impulse_z warmup (raw present, standardized twin not yet)
# --------------------------------------------------------------------------- #
def test_monetary_impulse_z_warmup_is_typed_insufficient_history() -> None:
    glt = copy.deepcopy(_base_glt())
    glt["state"]["monetary_impulse_z"] = None
    snap = _compose(glt=glt)
    m = _metric(snap, "glt_monetary_impulse_z")
    assert m["value"] is None
    assert m["status"] == "ABSENT"
    assert m["null_reason"] == "INSUFFICIENT_HISTORY"
    # the raw twin is unaffected
    raw = _metric(snap, "glt_monetary_impulse")
    assert raw["value"] == pytest.approx(0.003956)
    assert raw["status"] == "PRESENT"


def test_monetary_impulse_z_present_reads_normally() -> None:
    snap = _compose()
    m = _metric(snap, "glt_monetary_impulse_z")
    assert m["value"] == pytest.approx(0.077032)
    assert m["status"] == "PRESENT"
    assert m["null_reason"] is None


# --------------------------------------------------------------------------- #
# WALCL units defect: sanity check, never rescaled
# --------------------------------------------------------------------------- #
def test_plausible_walcl_level_publishes_normally() -> None:
    cbd = copy.deepcopy(_base_cb_desk())
    cbd["cbs"][0]["bs_impulse"]["level"] = 6737.2  # plausible USD-billions scale
    snap = _compose(cbd=cbd)
    m = _metric(snap, "cb_fed_balance_sheet_level")
    assert m["value"] == 6737.2
    assert m["status"] == "PRESENT"
    assert "corrected by this composer" in m["transformation"]


def test_non_walcl_series_is_never_sanity_checked() -> None:
    # A hypothetically huge ECB level (same magnitude issue) is NOT
    # sanity-checked -- the disclosed defect is scoped to WALCL only.
    cbd = copy.deepcopy(_base_cb_desk())
    cbd["cbs"][1]["bs_impulse"]["level"] = 5915343.0  # already the baseline value
    snap = _compose(cbd=cbd)
    m = _metric(snap, "cb_ecb_balance_sheet_level")
    assert m["value"] == 5915343.0
    assert m["status"] == "PRESENT"


# --------------------------------------------------------------------------- #
# global-state-vs-Fed-desk contradiction: fires on genuine two-sided data,
# stays silent on one-sided / flat / missing data
# --------------------------------------------------------------------------- #
def test_contradiction_fires_when_glt_expanding_and_fed_contracting() -> None:
    glt = copy.deepcopy(_base_glt())
    glt["state"]["label"] = "expanding"
    cbd = copy.deepcopy(_base_cb_desk())
    cbd["cbs"][0]["bs_impulse"]["impulse_13w"] = -5.0  # decisively contracting
    snap = _compose(glt=glt, cbd=cbd)
    c = snap["availability"]["contradiction"]
    assert c["present"] is True
    assert c["kind"] == "global_state_vs_fed_desk"
    assert set(c["components"]) == {"glt_monetary_impulse", "cb_fed_balance_sheet_impulse_13w"}
    assert any("contradiction=global_state_vs_fed_desk" in r for r in snap["availability"]["reasons"])
    mi = _metric(snap, "glt_monetary_impulse")
    assert mi["status"] == "DISAGREEMENT"
    assert mi["value"] is not None  # typed disagreement, not censored
    fed13 = _metric(snap, "cb_fed_balance_sheet_impulse_13w")
    assert fed13["status"] == "DISAGREEMENT"
    assert any(i["implication_id"] == "contradiction_global_state_vs_fed_desk"
               for i in snap["implications"]["items"])


def test_contradiction_silent_when_glt_reads_flat() -> None:
    cbd = copy.deepcopy(_base_cb_desk())
    cbd["cbs"][0]["bs_impulse"]["impulse_13w"] = -5.0
    snap = _compose(cbd=cbd)  # baseline glt label stays "flat"
    assert snap["availability"]["contradiction"]["present"] is False
    fed13 = _metric(snap, "cb_fed_balance_sheet_impulse_13w")
    assert fed13["status"] == "PRESENT"


def test_contradiction_silent_when_both_sides_agree() -> None:
    glt = copy.deepcopy(_base_glt())
    glt["state"]["label"] = "expanding"
    cbd = copy.deepcopy(_base_cb_desk())
    cbd["cbs"][0]["bs_impulse"]["impulse_13w"] = 3.0  # also expanding
    snap = _compose(glt=glt, cbd=cbd)
    assert snap["availability"]["contradiction"]["present"] is False


def test_contradiction_silent_when_fed_leg_within_flat_band() -> None:
    glt = copy.deepcopy(_base_glt())
    glt["state"]["label"] = "expanding"
    cbd = copy.deepcopy(_base_cb_desk())
    cbd["cbs"][0]["bs_impulse"]["impulse_13w"] = 0.2  # inside the 0.5 flat band
    snap = _compose(glt=glt, cbd=cbd)
    assert snap["availability"]["contradiction"]["present"] is False


def test_contradiction_silent_when_fed_leg_missing() -> None:
    glt = copy.deepcopy(_base_glt())
    glt["state"]["label"] = "expanding"
    cbd = copy.deepcopy(_base_cb_desk())
    cbd["cbs"] = [c for c in cbd["cbs"] if c["id"] != "FED"]
    snap = _compose(glt=glt, cbd=cbd)
    assert snap["availability"]["contradiction"]["present"] is False


# --------------------------------------------------------------------------- #
# scope boundary: no TGA/RRP/reserves metric is fabricated by this composer
# --------------------------------------------------------------------------- #
def test_no_tga_rrp_reserves_metric_is_fabricated() -> None:
    snap = _compose()
    ids = {m["metric_id"] for m in snap["metrics"]["items"]}
    assert not any("tga" in mid or "rrp" in mid or "reserve" in mid for mid in ids)


def test_metric_ids_are_unique() -> None:
    snap = _compose()
    ids = [m["metric_id"] for m in snap["metrics"]["items"]]
    assert len(ids) == len(set(ids))
    assert len(ids) == 28


# --------------------------------------------------------------------------- #
# changes / method-version comparability
# --------------------------------------------------------------------------- #
def _prior(method=liquidity_central_banks.METHOD_VERSION, mi=0.001,
           gen="liquidity_central_banks-US-deadbeefdeadbeef") -> dict:
    prior = _compose()
    prior["headline"]["method_version"] = method
    prior["headline"]["effective_date"] = "2026-08-21"
    prior["generation"]["generation_id"] = gen
    for m in prior["metrics"]["items"]:
        if m["metric_id"] == "glt_monetary_impulse":
            m["value"] = mi
    return prior


def test_changes_no_prior_yields_warmup() -> None:
    snap = _compose()
    assert snap["changes"]["comparability"] == "NO_PRIOR"
    assert snap["changes"]["null_reason"] == "WARMUP"


def test_changes_method_mismatch_refuses_numeric_comparison() -> None:
    snap = _compose(prior_snapshot=_prior(method="liquidity_central_banks.compose.v0"))
    assert snap["changes"]["comparability"] == "METHOD_CHANGED"
    assert snap["changes"]["deltas"] == []
    assert snap["changes"]["null_reason"] == "COMPUTATION_REFUSED"


def test_changes_comparable_prior_produces_deltas() -> None:
    snap = _compose(prior_snapshot=_prior(mi=0.001))
    assert snap["changes"]["comparability"] == "COMPARABLE"
    ids = {d["metric_id"] for d in snap["changes"]["deltas"]}
    assert ids == set(liquidity_central_banks._TRACKED_CHANGE_METRICS)
    mi_delta = next(d for d in snap["changes"]["deltas"] if d["metric_id"] == "glt_monetary_impulse")
    assert mi_delta["prior_value"] == 0.001
    assert mi_delta["current_value"] == pytest.approx(0.003956)
    assert mi_delta["delta"] == pytest.approx(0.002956, abs=1e-6)


# --------------------------------------------------------------------------- #
# corrections / supersession honesty
# --------------------------------------------------------------------------- #
def test_corrections_none_for_first_print() -> None:
    snap = _compose()
    assert snap["corrections"]["correction_state"] == "none"
    assert snap["corrections"]["predecessor_generation_id"] is None


def test_corrections_superseded_when_same_period_value_changes() -> None:
    glt = _base_glt()
    prior_snap = contract.finalize(liquidity_central_banks.compose(
        glt, _base_cb_desk(), _base_hist(), built_at=BUILT_AT))
    glt2 = copy.deepcopy(glt)
    glt2["state"]["monetary_impulse"] = 0.05  # same asof, revised value
    snap2 = liquidity_central_banks.compose(
        glt2, _base_cb_desk(), _base_hist(), built_at=BUILT_AT, prior_snapshot=prior_snap)
    assert snap2["corrections"]["correction_state"] == "superseded"
    assert snap2["corrections"]["changed_fingerprints"]
    assert snap2["corrections"]["predecessor_generation_id"] == prior_snap["generation"]["generation_id"]


def test_corrections_none_when_reference_period_advances() -> None:
    glt = _base_glt()
    prior_snap = contract.finalize(liquidity_central_banks.compose(
        glt, _base_cb_desk(), _base_hist(), built_at=BUILT_AT))
    glt2 = copy.deepcopy(glt)
    glt2["state"]["asof"] = "2026-09-04"  # new observation, not a revision
    glt2["state"]["monetary_impulse"] = 0.05
    snap2 = liquidity_central_banks.compose(
        glt2, _base_cb_desk(), _base_hist(), built_at=BUILT_AT, prior_snapshot=prior_snap)
    assert snap2["corrections"]["correction_state"] == "none"


# --------------------------------------------------------------------------- #
# digest determinism (contract.py's content_digest excludes generation/build
# provenance; identical owner input -> identical digest). Includes a
# genuinely-consumed-field mutation AND an unconsumed-field negative control.
# --------------------------------------------------------------------------- #
def test_digest_is_deterministic_across_identical_input() -> None:
    snap1 = contract.finalize(_compose())
    snap2 = contract.finalize(_compose())
    assert snap1["generation"]["content_sha256"] == snap2["generation"]["content_sha256"]
    assert snap1["generation"]["generation_id"] == snap2["generation"]["generation_id"]


def test_digest_unaffected_by_code_version() -> None:
    snap1 = contract.finalize(_compose(code_version="abc123"))
    snap2 = contract.finalize(_compose(code_version="def456"))
    assert snap1["generation"]["content_sha256"] == snap2["generation"]["content_sha256"]


def test_digest_changes_when_consumed_glt_field_changes() -> None:
    snap1 = contract.finalize(_compose())
    glt2 = copy.deepcopy(_base_glt())
    glt2["state"]["monetary_impulse"] = 0.5  # genuinely consumed
    snap2 = contract.finalize(_compose(glt=glt2))
    assert snap1["generation"]["content_sha256"] != snap2["generation"]["content_sha256"]


def test_digest_changes_when_consumed_cb_desk_field_changes() -> None:
    snap1 = contract.finalize(_compose())
    cbd2 = copy.deepcopy(_base_cb_desk())
    cbd2["cbs"][0]["bs_impulse"]["impulse_13w"] = 9.9  # genuinely consumed
    snap2 = contract.finalize(_compose(cbd=cbd2))
    assert snap1["generation"]["content_sha256"] != snap2["generation"]["content_sha256"]


def test_digest_unaffected_by_unconsumed_glt_field() -> None:
    snap1 = contract.finalize(_compose())
    glt3 = copy.deepcopy(_base_glt())
    glt3["meta"]["architecture_authority"] = "some unrelated string this composer never reads"
    snap3 = contract.finalize(_compose(glt=glt3))
    assert snap1["generation"]["content_sha256"] == snap3["generation"]["content_sha256"]


def test_digest_unaffected_by_unconsumed_cb_desk_field() -> None:
    snap1 = contract.finalize(_compose())
    cbd3 = copy.deepcopy(_base_cb_desk())
    cbd3["cbs"][0]["last_change"]["bp"] = -999.0  # never read by this composer
    snap3 = contract.finalize(_compose(cbd=cbd3))
    assert snap1["generation"]["content_sha256"] == snap3["generation"]["content_sha256"]


def test_digest_unaffected_by_unconsumed_history_meta_row_count() -> None:
    snap1 = contract.finalize(_compose())
    hist3 = copy.deepcopy(_base_hist())
    hist3["rows"] = 999999  # not read by this composer (only last_asof is)
    snap3 = contract.finalize(_compose(hist=hist3))
    assert snap1["generation"]["content_sha256"] == snap3["generation"]["content_sha256"]


# --------------------------------------------------------------------------- #
# schema validation
# --------------------------------------------------------------------------- #
def test_baseline_snapshot_validates_against_the_closed_contract() -> None:
    snap = contract.finalize(_compose())
    contract.validate(snap)  # raises ContractError on any violation
    assert snap["authority"]["can_size"] is False
    assert snap["authority"]["can_execute"] is False
    assert snap["authority"]["can_originate_signal"] is False


def test_degraded_snapshots_still_validate() -> None:
    glt = copy.deepcopy(_base_glt())
    glt["state"]["label"] = "expanding"
    glt["state"]["monetary_impulse_z"] = None
    glt["freshness"]["status"] = "degraded"
    glt["freshness"]["degraded"] = True
    cbd = copy.deepcopy(_base_cb_desk())
    cbd["cbs"][0]["bs_impulse"]["impulse_13w"] = -5.0
    cbd["cbs"] = [cbd["cbs"][0]]  # only FED reports
    snap = contract.finalize(liquidity_central_banks.compose(
        glt, cbd, _base_hist(), built_at=BUILT_AT))
    contract.validate(snap)


def test_snapshot_with_all_owner_inputs_missing_still_validates() -> None:
    snap = contract.finalize(liquidity_central_banks.compose({}, {}, {}, built_at=BUILT_AT))
    contract.validate(snap)
    assert snap["availability"]["state"] == "SOURCE_FAILED"


# --------------------------------------------------------------------------- #
# disclosure prose: reader language only -- never a raw closed-vocabulary
# enum token (PRESENT/SOURCE_FAILED/etc.) inside a human-readable field.
# --------------------------------------------------------------------------- #
_RAW_ENUM_TOKENS = frozenset({
    "CURRENT", "LATE_WITHIN_TOLERANCE", "STALE_SOURCE", "NOT_YET_RELEASED",
    "SOURCE_FAILED", "RIGHTS_BLOCKED", "NOT_COVERED", "HISTORICAL_AS_KNOWN", "SIMULATED",
    "UNKNOWN", "NOT_APPLICABLE", "INSUFFICIENT_HISTORY", "WARMUP",
    "REVISION_PENDING_REBUILD", "DISAGREEMENT", "COMPUTATION_REFUSED", "OUT_OF_REGION",
    "PRESENT", "PARTIAL", "ABSENT",
})
_PROSE_KEYS = ("en", "zh", "note", "transformation")


def _find_raw_token_leaks(node, path: str = "$") -> list[tuple[str, str, str]]:
    leaks: list[tuple[str, str, str]] = []
    if isinstance(node, dict):
        for k, v in node.items():
            if k in _PROSE_KEYS and isinstance(v, str):
                for tok in _RAW_ENUM_TOKENS:
                    if tok in v:
                        leaks.append((f"{path}.{k}", tok, v))
            leaks.extend(_find_raw_token_leaks(v, f"{path}.{k}"))
    elif isinstance(node, list):
        for idx, v in enumerate(node):
            leaks.extend(_find_raw_token_leaks(v, f"{path}[{idx}]"))
    return leaks


def test_prose_fields_contain_no_raw_enum_tokens() -> None:
    # exercise every disclosure branch at once: contradiction fired, quality
    # degraded, WALCL defect fired, 52w warmup.
    glt = copy.deepcopy(_base_glt())
    glt["state"]["label"] = "expanding"
    glt["state"]["monetary_impulse_z"] = None
    cbd = copy.deepcopy(_base_cb_desk())
    cbd["cbs"][0]["bs_impulse"]["impulse_13w"] = -5.0
    snap = _compose(glt=glt, cbd=cbd)
    leaks = _find_raw_token_leaks(snap)
    assert leaks == [], f"raw enum tokens leaked into prose field(s): {leaks}"


# --------------------------------------------------------------------------- #
# zh-label integrity: composer-authored English phrasing must never leak into
# the composer-authored zh sibling
# --------------------------------------------------------------------------- #
_COMPOSER_ENGLISH_PHRASES = (
    "the owner's own", "This composer", "Rather than guess", "measures data lineage",
    "does not agree with", "cosmetic bucket reuse", "a promotion grade",
)


def _find_english_leaks(node, path: str = "$") -> list[tuple[str, str, str]]:
    leaks: list[tuple[str, str, str]] = []
    if isinstance(node, dict):
        zh = node.get("zh")
        if "en" in node and isinstance(zh, str):
            for phrase in _COMPOSER_ENGLISH_PHRASES:
                if phrase in zh:
                    leaks.append((path, phrase, zh))
        for k, v in node.items():
            leaks.extend(_find_english_leaks(v, f"{path}.{k}"))
    elif isinstance(node, list):
        for idx, v in enumerate(node):
            leaks.extend(_find_english_leaks(v, f"{path}[{idx}]"))
    return leaks


def test_zh_narrative_never_embeds_composer_english_phrasing() -> None:
    glt = copy.deepcopy(_base_glt())
    glt["state"]["label"] = "expanding"
    cbd = copy.deepcopy(_base_cb_desk())
    cbd["cbs"][0]["bs_impulse"]["impulse_13w"] = -5.0
    snap = _compose(glt=glt, cbd=cbd)
    leaks = _find_english_leaks(snap)
    assert leaks == [], f"English phrasing leaked into zh field(s): {leaks}"


def test_zh_narrative_present_wherever_english_is_composer_authored() -> None:
    snap = _compose()
    for impl in snap["implications"]["items"]:
        assert impl["text"]["en"], impl
        assert impl["text"]["zh"], impl
    assert snap["workspace"]["title"]["zh"]
    assert snap["headline"]["subtitle"]["zh"]


# --------------------------------------------------------------------------- #
# real owner artifacts (site/liquiditydata + data/intl_risk#cb_desk +
# data/global_liquidity_transmission/state_history_meta.json) -- skipped
# where an artifact is absent, never fabricated.
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(
    not (GLT_LATEST.exists() and INTL_RISK_LATEST.exists()),
    reason="one or more real owner artifacts are absent")
def test_builds_and_validates_from_real_owner_artifacts() -> None:
    glt = json.loads(GLT_LATEST.read_text(encoding="utf-8"))
    intl_risk = json.loads(INTL_RISK_LATEST.read_text(encoding="utf-8"))
    cbd = intl_risk.get("cb_desk") or {}
    hist = json.loads(GLT_HISTORY_META.read_text(encoding="utf-8")) if GLT_HISTORY_META.exists() else {}

    snap = contract.finalize(liquidity_central_banks.compose(glt, cbd, hist, built_at=BUILT_AT))
    contract.validate(snap)
    assert snap["headline"]["state_id"] is None
    assert snap["axes"]["items"] == []
    assert snap["authority"]["can_size"] is False
    assert snap["authority"]["can_execute"] is False
    # FED/ECB/BoJ are the architecture-named trio and should be present in
    # any live cb_desk pull (a real-data smoke check, not a fixture claim).
    ids = {m["metric_id"] for m in snap["metrics"]["items"]}
    assert {"cb_fed_balance_sheet_impulse_13w", "cb_ecb_balance_sheet_impulse_13w",
            "cb_boj_balance_sheet_impulse_13w"} <= ids
    # this composer never fabricates a global-credit scalar
    credit = next(m for m in snap["metrics"]["items"] if m["metric_id"] == "glt_credit_impulse_global")
    if credit["value"] is None:
        assert credit["null_reason"] in ("NOT_COVERED", "SOURCE_FAILED", "UNKNOWN")
