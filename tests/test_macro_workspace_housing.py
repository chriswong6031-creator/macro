"""Composer tests for the US housing_real_estate workspace (F01 / R5).

RED-first: each degraded condition must produce the correct TYPED state and
never a zero / neutral / calm default. Covers: the COMPUTATION_REFUSED headline
shape (architecture 10.10 DOES define a two-axis blueprint, unlike the
NOT_APPLICABLE workspaces -- see housing.py's module docstring), the per-series
weekly/monthly cadence freshness law (CURRENT/LATE_WITHIN_TOLERANCE/STALE_SOURCE
boundaries), 13-week/YoY derived-read correctness on hand-computable fixtures,
the leg-floor refusal on permits_minus_starts_spread, the typed-ABSENT remainder
(NAR rights-blocked, Census not-covered, Redfin source-failed), the
home-price-vs-rent contradiction (fires / stays silent / flat-band-guarded), the
SA/NSA no-mix pin, digest determinism with a genuinely-consumed-field mutation
and unconsumed-field/unconsumed-row-element negative controls, a prose scan for
raw enum-token leaks, zh-narrative integrity, and schema validation.

    python3 -m pytest tests/test_macro_workspace_housing.py -x -q
"""
from __future__ import annotations

import copy
import datetime as dt
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.market_os.macro_workspaces import contract, housing  # noqa: E402

BUILT_AT = "2026-09-04T00:00:00Z"
BUILT_DATE = dt.date(2026, 9, 4)


# --------------------------------------------------------------------------- #
# fixtures (small, hand-computable row lists -- see the inline arithmetic notes
# next to every derived-value assertion below)
# --------------------------------------------------------------------------- #
def _mortgage_rows() -> list[tuple[str, float]]:
    # anchor 2026-09-03 is 1 day before BUILT_AT -> CURRENT (cadence 7d).
    # 2026-06-04 is EXACTLY 13 weeks (91 days) before the anchor (7*13=91,
    # verified by hand: 09-03 -7*13d walk lands on 06-04), so the 13w-change
    # lookup finds it at zero slack.
    return [("2026-06-04", 6.20), ("2026-09-03", 6.50)]


def _starts_rows() -> list[tuple[str, float]]:
    # anchor 2026-08-01 is 34 days before BUILT_AT -> CURRENT (cadence 80d).
    # 2025-08-01 is EXACTLY 365 days before 2026-08-01 (2026 is not a leap
    # year, so no Feb-29 sits between them) -> the YoY lookup finds it at
    # zero slack.
    return [("2025-08-01", 1300.0), ("2026-08-01", 1400.0)]


def _permits_rows() -> list[tuple[str, float]]:
    return [("2025-08-01", 1350.0), ("2026-08-01", 1450.0)]


def _case_shiller_rows() -> list[tuple[str, float]]:
    # anchor 2026-07-15 is 51 days before BUILT_AT -> CURRENT (cadence 124d).
    # 2025-07-15 is EXACTLY 365 days before 2026-07-15 (same leap-year note).
    return [("2025-07-15", 300.0), ("2026-07-15", 315.0)]


def _zori_rows_rising() -> list[tuple[str, float]]:
    # anchor 2026-08-01 is 34 days before BUILT_AT -> CURRENT (cadence 50d).
    return [("2025-08-01", 1900.0), ("2026-08-01", 1950.0)]


def _zori_rows_falling() -> list[tuple[str, float]]:
    return [("2025-08-01", 2000.0), ("2026-08-01", 1950.0)]


def _base_fred_frames() -> dict:
    return {
        housing.SERIES_MORTGAGE: _mortgage_rows(),
        housing.SERIES_STARTS: _starts_rows(),
        housing.SERIES_PERMITS: _permits_rows(),
        housing.SERIES_CASE_SHILLER: _case_shiller_rows(),
    }


_UNSET = object()  # sentinel: distinguishes "caller omitted the arg" (use the
# default fixture) from "caller explicitly passed None/empty" (test a genuinely
# absent owner input) -- a plain ``=None`` default cannot tell those apart.


def _compose(fred_frames=_UNSET, zori=_UNSET, **kw) -> dict:
    return housing.compose(
        _base_fred_frames() if fred_frames is _UNSET else fred_frames,
        _zori_rows_rising() if zori is _UNSET else zori,
        built_at=BUILT_AT, **kw,
    )


def _metric(snapshot: dict, metric_id: str) -> dict:
    return next(m for m in snapshot["metrics"]["items"] if m["metric_id"] == metric_id)


def _required(snapshot: dict, cid: str) -> dict:
    return next(c for c in snapshot["availability"]["required"] if c["component_id"] == cid)


def _implication(snapshot: dict, iid: str) -> dict | None:
    return next((i for i in snapshot["implications"]["items"] if i["implication_id"] == iid), None)


# --------------------------------------------------------------------------- #
# healthy baseline
# --------------------------------------------------------------------------- #
def test_baseline_all_required_sources_current() -> None:
    snap = _compose()
    assert snap["workspace"]["id"] == "housing_real_estate"
    assert snap["region"]["code"] == "US"
    for cid in ("mortgage_rate", "housing_starts", "building_permits", "case_shiller_hpi"):
        r = _required(snap, cid)
        assert r["freshness"] == "CURRENT", (cid, r)
        assert r["status"] == "PRESENT"
    assert snap["availability"]["state"] == "CURRENT"
    assert snap["availability"]["coverage_ratio"] == 1.0


def test_optional_zori_component_present_but_not_required() -> None:
    snap = _compose()
    required_ids = {c["component_id"] for c in snap["availability"]["required"] if c["required"]}
    optional_ids = {c["component_id"] for c in snap["availability"]["required"] if not c["required"]}
    assert "national_rent_zori" in optional_ids
    assert "national_rent_zori" not in required_ids


def test_zori_missing_never_degrades_required_availability_state() -> None:
    snap = _compose(zori=None)
    assert snap["availability"]["state"] == "CURRENT"
    opt = _required(snap, "national_rent_zori")
    assert opt["status"] == "ABSENT"
    assert opt["freshness"] == "SOURCE_FAILED"


# --------------------------------------------------------------------------- #
# 13-week / YoY derived-read correctness (hand-computable fixtures)
# --------------------------------------------------------------------------- #
def test_mortgage_rate_level_and_13w_change() -> None:
    snap = _compose()
    level = _metric(snap, "mortgage_30y_rate_level")
    assert level["value"] == pytest.approx(6.50)
    assert level["status"] == "PRESENT"
    change = _metric(snap, "mortgage_30y_rate_change_13w")
    assert change["value"] == pytest.approx(6.50 - 6.20)  # = 0.30
    assert change["status"] == "PRESENT"


def test_mortgage_13w_change_insufficient_history() -> None:
    ff = _base_fred_frames()
    ff[housing.SERIES_MORTGAGE] = [("2026-09-03", 6.50)]  # only the latest row
    snap = _compose(fred_frames=ff)
    change = _metric(snap, "mortgage_30y_rate_change_13w")
    assert change["value"] is None
    assert change["status"] == "ABSENT"
    assert change["null_reason"] == "INSUFFICIENT_HISTORY"
    # the level itself is unaffected
    level = _metric(snap, "mortgage_30y_rate_level")
    assert level["value"] == pytest.approx(6.50)


def test_housing_starts_level_and_yoy() -> None:
    snap = _compose()
    level = _metric(snap, "housing_starts_level")
    assert level["value"] == pytest.approx(1400.0)
    yoy = _metric(snap, "housing_starts_yoy")
    expected = round((1400.0 / 1300.0 - 1.0) * 100.0, 4)
    assert yoy["value"] == pytest.approx(expected)
    assert yoy["status"] == "PRESENT"


def test_building_permits_level_and_yoy() -> None:
    snap = _compose()
    level = _metric(snap, "building_permits_level")
    assert level["value"] == pytest.approx(1450.0)
    yoy = _metric(snap, "building_permits_yoy")
    expected = round((1450.0 / 1350.0 - 1.0) * 100.0, 4)
    assert yoy["value"] == pytest.approx(expected)


def test_permits_minus_starts_spread() -> None:
    snap = _compose()
    spread = _metric(snap, "permits_minus_starts_spread")
    assert spread["value"] == pytest.approx(1450.0 - 1400.0)  # = 50.0
    assert spread["status"] == "PRESENT"
    assert spread["source_refs"] == ["FRED:PERMIT", "FRED:HOUST"]


def test_case_shiller_level_and_yoy() -> None:
    snap = _compose()
    level = _metric(snap, "case_shiller_national_hpi_level")
    assert level["value"] == pytest.approx(315.0)
    yoy = _metric(snap, "case_shiller_national_hpi_yoy")
    assert yoy["value"] == pytest.approx(5.0)  # 315/300 - 1 = exactly 5%


def test_zori_level_and_yoy() -> None:
    snap = _compose(zori=_zori_rows_rising())
    level = _metric(snap, "national_rent_zori_level")
    assert level["value"] == pytest.approx(1950.0)
    yoy = _metric(snap, "national_rent_zori_yoy")
    expected = round((1950.0 / 1900.0 - 1.0) * 100.0, 4)
    assert yoy["value"] == pytest.approx(expected)


def test_starts_yoy_insufficient_history_when_only_latest_row() -> None:
    ff = _base_fred_frames()
    ff[housing.SERIES_STARTS] = [("2026-08-01", 1400.0)]
    snap = _compose(fred_frames=ff)
    yoy = _metric(snap, "housing_starts_yoy")
    assert yoy["value"] is None
    assert yoy["null_reason"] == "INSUFFICIENT_HISTORY"


# --------------------------------------------------------------------------- #
# leg-floor refusal: permits_minus_starts_spread
# --------------------------------------------------------------------------- #
def test_spread_refused_when_starts_missing() -> None:
    ff = _base_fred_frames()
    ff[housing.SERIES_STARTS] = None
    snap = _compose(fred_frames=ff)
    spread = _metric(snap, "permits_minus_starts_spread")
    assert spread["value"] is None
    assert spread["status"] == "ABSENT"
    assert spread["null_reason"] == "COMPUTATION_REFUSED"
    # permits itself is unaffected
    permits_level = _metric(snap, "building_permits_level")
    assert permits_level["value"] == pytest.approx(1450.0)


def test_spread_refused_when_permits_missing() -> None:
    ff = _base_fred_frames()
    ff[housing.SERIES_PERMITS] = []
    snap = _compose(fred_frames=ff)
    spread = _metric(snap, "permits_minus_starts_spread")
    assert spread["value"] is None
    assert spread["null_reason"] == "COMPUTATION_REFUSED"


def test_spread_source_failed_when_both_legs_missing() -> None:
    snap = _compose(fred_frames={})
    spread = _metric(snap, "permits_minus_starts_spread")
    assert spread["value"] is None
    assert spread["null_reason"] == "SOURCE_FAILED"


def test_spread_never_defaults_missing_leg_to_zero() -> None:
    ff = _base_fred_frames()
    ff[housing.SERIES_STARTS] = None
    snap = _compose(fred_frames=ff)
    spread = _metric(snap, "permits_minus_starts_spread")
    assert spread["value"] != 0
    assert spread["value"] is None


# --------------------------------------------------------------------------- #
# per-leg missing -> typed degradation, without affecting siblings
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("series_key,component_id", [
    (housing.SERIES_MORTGAGE, "mortgage_rate"),
    (housing.SERIES_STARTS, "housing_starts"),
    (housing.SERIES_PERMITS, "building_permits"),
    (housing.SERIES_CASE_SHILLER, "case_shiller_hpi"),
])
def test_missing_required_series_is_typed_source_failed(series_key, component_id) -> None:
    ff = _base_fred_frames()
    ff[series_key] = None
    snap = _compose(fred_frames=ff)
    r = _required(snap, component_id)
    assert r["freshness"] == "SOURCE_FAILED"
    assert r["status"] == "ABSENT"
    assert r["null_reason"] == "SOURCE_FAILED"
    assert snap["availability"]["state"] == "SOURCE_FAILED"
    assert component_id in snap["availability"]["degraded"]


def test_missing_mortgage_does_not_affect_starts_or_permits() -> None:
    ff = _base_fred_frames()
    ff[housing.SERIES_MORTGAGE] = None
    snap = _compose(fred_frames=ff)
    r_starts = _required(snap, "housing_starts")
    assert r_starts["status"] == "PRESENT"
    assert r_starts["freshness"] == "CURRENT"
    starts_metric = _metric(snap, "housing_starts_level")
    assert starts_metric["value"] == pytest.approx(1400.0)


def test_all_required_sources_missing_still_typed_never_crashes() -> None:
    snap = housing.compose({}, None, built_at=BUILT_AT)
    assert snap["availability"]["state"] == "SOURCE_FAILED"
    assert snap["availability"]["coverage_ratio"] == 0.0
    for cid in ("mortgage_rate", "housing_starts", "building_permits", "case_shiller_hpi"):
        r = _required(snap, cid)
        assert r["status"] == "ABSENT"


def test_malformed_and_none_rows_are_dropped_never_fabricated() -> None:
    ff = _base_fred_frames()
    ff[housing.SERIES_MORTGAGE] = [
        None, ("bad-date", 6.5), ("2026-09-03", "not-a-number"),
        ("2026-06-04", 6.20), ("2026-09-03", 6.50),
    ]
    snap = _compose(fred_frames=ff)
    level = _metric(snap, "mortgage_30y_rate_level")
    assert level["value"] == pytest.approx(6.50)


def test_rows_supplied_as_lists_not_tuples_work_identically() -> None:
    ff = {
        housing.SERIES_MORTGAGE: [["2026-06-04", 6.20], ["2026-09-03", 6.50]],
        housing.SERIES_STARTS: _starts_rows(),
        housing.SERIES_PERMITS: _permits_rows(),
        housing.SERIES_CASE_SHILLER: _case_shiller_rows(),
    }
    snap = _compose(fred_frames=ff)
    level = _metric(snap, "mortgage_30y_rate_level")
    assert level["value"] == pytest.approx(6.50)


# --------------------------------------------------------------------------- #
# typed-ABSENT remainder: rights-blocked / not-covered / source-failed
# --------------------------------------------------------------------------- #
def test_existing_home_sales_is_rights_blocked() -> None:
    snap = _compose()
    m = _metric(snap, "existing_home_sales")
    assert m["value"] is None
    assert m["status"] == "ABSENT"
    assert m["null_reason"] == "RIGHTS_BLOCKED"
    assert m["freshness"] == "RIGHTS_BLOCKED"
    assert m["rights_state"] == "RIGHTS_BLOCKED"


@pytest.mark.parametrize("metric_id", ["new_home_sales", "housing_completions"])
def test_new_construction_legs_are_not_covered(metric_id) -> None:
    snap = _compose()
    m = _metric(snap, metric_id)
    assert m["value"] is None
    assert m["null_reason"] == "NOT_COVERED"
    assert m["freshness"] == "NOT_COVERED"
    # NOT_COVERED is not a rights issue -- rights_state stays OPEN
    assert m["rights_state"] == "OPEN"


@pytest.mark.parametrize("metric_id", [
    "pending_home_sales_redfin", "active_listings_redfin",
    "price_drop_share_redfin", "median_days_on_market_redfin",
])
def test_redfin_legs_are_source_failed_not_not_covered(metric_id) -> None:
    snap = _compose()
    m = _metric(snap, metric_id)
    assert m["value"] is None
    assert m["null_reason"] == "SOURCE_FAILED"
    assert m["freshness"] == "SOURCE_FAILED"
    assert m["rights_state"] == "OPEN"
    assert "collector" in m["transformation"]


def test_redfin_price_drop_leg_discloses_seasonality_caveat() -> None:
    snap = _compose()
    m = _metric(snap, "price_drop_share_redfin")
    assert "34.5" in m["transformation"]
    assert "deseasonalize" in m["transformation"]


# --------------------------------------------------------------------------- #
# home-price-vs-rent contradiction: fires / silent / flat-band-guarded
# --------------------------------------------------------------------------- #
def test_contradiction_fires_when_prices_rise_and_rent_falls() -> None:
    snap = _compose(zori=_zori_rows_falling())
    c = snap["availability"]["contradiction"]
    assert c["present"] is True
    assert c["kind"] == "home_price_vs_rent_divergence"
    assert set(c["components"]) == {"case_shiller_national_hpi_yoy", "national_rent_zori_yoy"}
    cs = _metric(snap, "case_shiller_national_hpi_yoy")
    assert cs["status"] == "DISAGREEMENT"
    assert cs["value"] is not None  # typed disagreement, never censored
    zori_m = _metric(snap, "national_rent_zori_yoy")
    assert zori_m["status"] == "DISAGREEMENT"
    assert _implication(snap, "contradiction_home_price_vs_rent_divergence") is not None


def test_contradiction_silent_when_both_directions_agree() -> None:
    snap = _compose(zori=_zori_rows_rising())  # both rising in the baseline fixture
    assert snap["availability"]["contradiction"]["present"] is False


def test_contradiction_silent_when_within_flat_band() -> None:
    ff = _base_fred_frames()
    ff[housing.SERIES_CASE_SHILLER] = [("2025-07-15", 300.0), ("2026-07-15", 300.5)]  # ~0.17% YoY
    snap = _compose(fred_frames=ff, zori=_zori_rows_falling())
    assert snap["availability"]["contradiction"]["present"] is False


def test_contradiction_silent_when_zori_absent() -> None:
    snap = _compose(zori=None)
    assert snap["availability"]["contradiction"]["present"] is False


# --------------------------------------------------------------------------- #
# SA/NSA no-mix pin
# --------------------------------------------------------------------------- #
def test_case_shiller_metrics_never_cite_zillow_source() -> None:
    snap = _compose()
    for mid in ("case_shiller_national_hpi_level", "case_shiller_national_hpi_yoy"):
        m = _metric(snap, mid)
        assert not any("Zillow" in ref for ref in m["source_refs"])


def test_zori_metrics_never_cite_fred_source() -> None:
    snap = _compose()
    for mid in ("national_rent_zori_level", "national_rent_zori_yoy"):
        m = _metric(snap, mid)
        assert not any("FRED" in ref for ref in m["source_refs"])


def test_no_metric_combines_case_shiller_and_zori_in_one_value() -> None:
    snap = _compose()
    ids = {m["metric_id"] for m in snap["metrics"]["items"]}
    # no fabricated home-price-to-rent ratio/spread/composite metric exists
    assert not any("price_to_rent" in mid or "hpi_to_zori" in mid or "rent_to_price" in mid for mid in ids)


def test_permits_minus_starts_is_the_only_cross_series_metric_and_is_sa_vs_sa() -> None:
    snap = _compose()
    spread = _metric(snap, "permits_minus_starts_spread")
    assert set(spread["source_refs"]) == {"FRED:PERMIT", "FRED:HOUST"}


# --------------------------------------------------------------------------- #
# cadence / release-lag freshness law (unit-level, on the shared helper)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("age_days,cadence,grace,expected", [
    (0, 7, 5, "CURRENT"),
    (7, 7, 5, "CURRENT"),
    (8, 7, 5, "LATE_WITHIN_TOLERANCE"),
    (12, 7, 5, "LATE_WITHIN_TOLERANCE"),
    (13, 7, 5, "STALE_SOURCE"),
    (80, 80, 17, "CURRENT"),
    (81, 80, 17, "LATE_WITHIN_TOLERANCE"),
    (97, 80, 17, "LATE_WITHIN_TOLERANCE"),
    (98, 80, 17, "STALE_SOURCE"),
    (124, 124, 15, "CURRENT"),
    (125, 124, 15, "LATE_WITHIN_TOLERANCE"),
    (139, 124, 15, "LATE_WITHIN_TOLERANCE"),
    (140, 124, 15, "STALE_SOURCE"),
    (50, 50, 15, "CURRENT"),
    (51, 50, 15, "LATE_WITHIN_TOLERANCE"),
    (65, 50, 15, "LATE_WITHIN_TOLERANCE"),
    (66, 50, 15, "STALE_SOURCE"),
])
def test_cadence_freshness_tiers(age_days, cadence, grace, expected) -> None:
    asof = BUILT_DATE - dt.timedelta(days=age_days)
    got = housing._cadence_freshness(BUILT_AT, asof, cadence, grace, True)
    assert got == expected


def test_cadence_freshness_absent_value_is_source_failed() -> None:
    assert housing._cadence_freshness(BUILT_AT, BUILT_DATE, 7, 5, False) == "SOURCE_FAILED"


def test_cadence_freshness_future_asof_is_source_failed() -> None:
    future = BUILT_DATE + dt.timedelta(days=5)
    assert housing._cadence_freshness(BUILT_AT, future, 7, 5, True) == "SOURCE_FAILED"


def test_mortgage_late_within_tolerance_via_full_compose() -> None:
    ff = _base_fred_frames()
    late_date = (BUILT_DATE - dt.timedelta(days=10)).isoformat()  # age 10: LATE (8..12)
    ff[housing.SERIES_MORTGAGE] = [("2026-05-01", 6.0), (late_date, 6.3)]
    snap = _compose(fred_frames=ff)
    r = _required(snap, "mortgage_rate")
    assert r["freshness"] == "LATE_WITHIN_TOLERANCE"
    assert snap["availability"]["state"] != "CURRENT"


# --------------------------------------------------------------------------- #
# headline: COMPUTATION_REFUSED, NOT NOT_APPLICABLE (architecture 10.10 has a
# real two-axis blueprint, unlike monetary_policy/liquidity_central_banks)
# --------------------------------------------------------------------------- #
def test_headline_is_computation_refused_not_not_applicable() -> None:
    snap = _compose()
    h = snap["headline"]
    assert h["state_id"] is None
    assert h["status"] == "ABSENT"
    assert h["null_reason"] == "COMPUTATION_REFUSED"
    assert h["null_reason"] != "NOT_APPLICABLE"
    assert h["quadrant"] == {"x": None, "y": None, "x_status": "ABSENT", "y_status": "ABSENT"}
    assert h["nearest_boundary"]["null_reason"] == "COMPUTATION_REFUSED"
    assert h["one_month_vector"]["null_reason"] == "COMPUTATION_REFUSED"
    assert h["hysteresis"]["applied"] is False
    assert "two-axis blueprint" in h["hysteresis"]["note"]


def test_axes_items_is_empty_by_design() -> None:
    snap = _compose()
    assert snap["axes"]["items"] == []


# --------------------------------------------------------------------------- #
# metric inventory + digest determinism
# --------------------------------------------------------------------------- #
def test_metric_ids_are_unique_and_stable_count() -> None:
    snap = _compose()
    ids = [m["metric_id"] for m in snap["metrics"]["items"]]
    assert len(ids) == len(set(ids))
    assert len(ids) == 18


def test_digest_is_deterministic_across_identical_input() -> None:
    snap1 = contract.finalize(_compose())
    snap2 = contract.finalize(_compose())
    assert snap1["generation"]["content_sha256"] == snap2["generation"]["content_sha256"]
    assert snap1["generation"]["generation_id"] == snap2["generation"]["generation_id"]


def test_digest_unaffected_by_code_version() -> None:
    snap1 = contract.finalize(_compose(code_version="abc123"))
    snap2 = contract.finalize(_compose(code_version="def456"))
    assert snap1["generation"]["content_sha256"] == snap2["generation"]["content_sha256"]


def test_digest_changes_when_consumed_mortgage_field_changes() -> None:
    snap1 = contract.finalize(_compose())
    ff2 = _base_fred_frames()
    ff2[housing.SERIES_MORTGAGE] = [("2026-06-04", 6.20), ("2026-09-03", 9.99)]
    snap2 = contract.finalize(_compose(fred_frames=ff2))
    assert snap1["generation"]["content_sha256"] != snap2["generation"]["content_sha256"]


def test_digest_changes_when_consumed_zori_field_changes() -> None:
    snap1 = contract.finalize(_compose(zori=_zori_rows_rising()))
    snap2 = contract.finalize(_compose(zori=_zori_rows_falling()))
    assert snap1["generation"]["content_sha256"] != snap2["generation"]["content_sha256"]


def test_digest_unaffected_by_unconsumed_fred_frames_key() -> None:
    snap1 = contract.finalize(_compose())
    ff3 = _base_fred_frames()
    ff3["DGS10"] = [("2026-09-03", 4.2)]  # never read by this composer
    snap3 = contract.finalize(_compose(fred_frames=ff3))
    assert snap1["generation"]["content_sha256"] == snap3["generation"]["content_sha256"]


def test_digest_unaffected_by_unconsumed_row_tuple_element() -> None:
    snap1 = contract.finalize(_compose())
    ff4 = _base_fred_frames()
    ff4[housing.SERIES_MORTGAGE] = [
        ("2026-06-04", 6.20, "unrelated-extra-field"),
        ("2026-09-03", 6.50, {"nested": "also unrelated"}),
    ]
    snap4 = contract.finalize(_compose(fred_frames=ff4))
    assert snap1["generation"]["content_sha256"] == snap4["generation"]["content_sha256"]


# --------------------------------------------------------------------------- #
# changes / method-version comparability
# --------------------------------------------------------------------------- #
def _prior(method=housing.METHOD_VERSION, mortgage_level=6.50,
           gen="housing_real_estate-US-deadbeefdeadbeef") -> dict:
    prior = _compose()
    prior["headline"]["method_version"] = method
    prior["generation"]["generation_id"] = gen
    for m in prior["metrics"]["items"]:
        if m["metric_id"] == "mortgage_30y_rate_level":
            m["value"] = mortgage_level
    return prior


def test_changes_no_prior_yields_warmup() -> None:
    snap = _compose()
    assert snap["changes"]["comparability"] == "NO_PRIOR"
    assert snap["changes"]["null_reason"] == "WARMUP"


def test_changes_method_mismatch_refuses_numeric_comparison() -> None:
    snap = _compose(prior_snapshot=_prior(method="housing_real_estate.compose.v0"))
    assert snap["changes"]["comparability"] == "METHOD_CHANGED"
    assert snap["changes"]["deltas"] == []
    assert snap["changes"]["null_reason"] == "COMPUTATION_REFUSED"


def test_changes_comparable_prior_produces_deltas() -> None:
    snap = _compose(prior_snapshot=_prior(mortgage_level=6.00))
    assert snap["changes"]["comparability"] == "COMPARABLE"
    ids = {d["metric_id"] for d in snap["changes"]["deltas"]}
    assert ids == set(housing._TRACKED_CHANGE_METRICS)
    delta = next(d for d in snap["changes"]["deltas"] if d["metric_id"] == "mortgage_30y_rate_level")
    assert delta["prior_value"] == 6.00
    assert delta["current_value"] == pytest.approx(6.50)
    assert delta["delta"] == pytest.approx(0.50)


# --------------------------------------------------------------------------- #
# corrections / supersession honesty
# --------------------------------------------------------------------------- #
def test_corrections_none_for_first_print() -> None:
    snap = _compose()
    assert snap["corrections"]["correction_state"] == "none"
    assert snap["corrections"]["predecessor_generation_id"] is None


def test_corrections_superseded_when_same_period_value_changes() -> None:
    ff = _base_fred_frames()
    prior_snap = contract.finalize(housing.compose(ff, _zori_rows_rising(), built_at=BUILT_AT))
    ff2 = copy.deepcopy(ff)
    ff2[housing.SERIES_MORTGAGE] = [("2026-06-04", 6.20), ("2026-09-03", 7.10)]  # same asof, revised value
    snap2 = housing.compose(ff2, _zori_rows_rising(), built_at=BUILT_AT, prior_snapshot=prior_snap)
    assert snap2["corrections"]["correction_state"] == "superseded"
    assert snap2["corrections"]["changed_fingerprints"]
    assert snap2["corrections"]["predecessor_generation_id"] == prior_snap["generation"]["generation_id"]


def test_corrections_none_when_reference_period_advances() -> None:
    ff = _base_fred_frames()
    prior_snap = contract.finalize(housing.compose(ff, _zori_rows_rising(), built_at=BUILT_AT))
    ff2 = copy.deepcopy(ff)
    ff2[housing.SERIES_MORTGAGE] = ff2[housing.SERIES_MORTGAGE] + [("2026-09-10", 6.55)]  # new observation
    snap2 = housing.compose(ff2, _zori_rows_rising(), built_at="2026-09-11T00:00:00Z", prior_snapshot=prior_snap)
    assert snap2["corrections"]["correction_state"] == "none"


# --------------------------------------------------------------------------- #
# schema validation
# --------------------------------------------------------------------------- #
def test_baseline_snapshot_validates_against_the_closed_contract() -> None:
    snap = contract.finalize(_compose())
    contract.validate(snap)  # raises ContractError on any violation
    assert snap["authority"]["can_size"] is False
    assert snap["authority"]["can_execute"] is False
    assert snap["authority"]["can_originate_signal"] is False


def test_degraded_snapshot_still_validates() -> None:
    ff = _base_fred_frames()
    ff[housing.SERIES_STARTS] = None
    snap = contract.finalize(housing.compose(ff, _zori_rows_falling(), built_at=BUILT_AT))
    contract.validate(snap)


def test_all_owner_inputs_missing_still_validates() -> None:
    snap = contract.finalize(housing.compose({}, None, built_at=BUILT_AT))
    contract.validate(snap)
    assert snap["availability"]["state"] == "SOURCE_FAILED"


# --------------------------------------------------------------------------- #
# disclosure implications present
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("iid", [
    "headline_unavailable", "no_alfred_pit_vintage_capture",
    "nar_rights_blocked_disclosure", "new_construction_not_covered_disclosure",
    "redfin_store_empty_disclosure", "driver_bucket_naming_note",
])
def test_disclosure_implications_present(iid) -> None:
    snap = _compose()
    assert _implication(snap, iid) is not None


def test_driver_bucket_reuse_disclosed_in_drivers_and_implication() -> None:
    snap = _compose()
    balance_sheet_ids = {d["driver_id"] for d in snap["drivers"]["balance_sheet"]}
    assert "housing_starts_yoy" in balance_sheet_ids
    assert _implication(snap, "driver_bucket_naming_note") is not None


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
    # exercise every disclosure branch at once: contradiction fired, a required
    # leg missing, the typed-absent remainder always present.
    ff = _base_fred_frames()
    ff[housing.SERIES_STARTS] = None
    snap = _compose(fred_frames=ff, zori=_zori_rows_falling())
    leaks = _find_raw_token_leaks(snap)
    assert leaks == [], f"raw enum tokens leaked into prose field(s): {leaks}"


# --------------------------------------------------------------------------- #
# zh-label integrity: composer-authored English phrasing must never leak into
# the composer-authored zh sibling
# --------------------------------------------------------------------------- #
_COMPOSER_ENGLISH_PHRASES = (
    "the composable-core", "This composer", "never combines it with",
    "leg-floor refusal", "cosmetic bucket reuse", "a genuine price-to-income composite",
    "point-in-time vintage capture",
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
    ff = _base_fred_frames()
    ff[housing.SERIES_STARTS] = None
    snap = _compose(fred_frames=ff, zori=_zori_rows_falling())
    leaks = _find_english_leaks(snap)
    assert leaks == [], f"English phrasing leaked into zh field(s): {leaks}"


def test_zh_narrative_present_wherever_english_is_composer_authored() -> None:
    snap = _compose()
    for impl in snap["implications"]["items"]:
        assert impl["text"]["en"], impl
        assert impl["text"]["zh"], impl
    assert snap["workspace"]["title"]["zh"]
    assert snap["headline"]["subtitle"]["zh"]
