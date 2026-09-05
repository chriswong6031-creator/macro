"""Composer tests for the US ``trade_flows`` workspace (beyond-F01 expansion,
Chairman-authorized 2026-09-04 -- the SECOND workspace past the frozen
twelve-workspace Market Ontology architecture set, alongside ``rates_curves``).

RED-first: each degraded condition must produce the correct TYPED state and
never a zero / neutral / calm default. Covers: the REAL FIRST BUILD (all five
series ``None`` -- today's actual disk truth, verified via a live glob during
authoring: zero of the five parquets exist), the fully self-healed shape
(hand-computed fixtures for level/YoY/3m-average/coverage-ratio/terms-of-
trade/balance-share-of-flows/identity-residual), the required-only (no
optional split) availability law, the SAME-DATE DISCIPLINE this composer
introduces for monthly cadence (leg-floor refusal, no-common-date refusal,
staleness-bound refusal) across all four combined reads (coverage ratio,
terms-of-trade proxy, balance-share-of-flows, the identity residual), the
trade-balance-identity contradiction (on / off / exact tolerance boundary),
the freshness cadence laws (dollar-flow group 102d/17d, price-index group
80d/15d), the SA/NSA never-mix law, the $M-never-rescaled unit discipline,
the four typed NOT_COVERED remainder lanes (each individually named and
disclosed), digest determinism with genuinely-consumed-field mutations and
unconsumed-field negative controls, a prose scan for raw enum-token leaks,
zh-narrative integrity, and schema validation.

    python3 -m pytest tests/test_macro_workspace_trade_flows.py -x -q
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

from engine.market_os.macro_workspaces import contract, trade_flows as tf  # noqa: E402

BUILT_AT = "2026-09-04T00:00:00Z"
BUILT_DATE = dt.date(2026, 9, 4)


# --------------------------------------------------------------------------- #
# fixtures (small, hand-computable row lists -- see the inline arithmetic
# notes next to every derived-value assertion below)
# --------------------------------------------------------------------------- #
def _trade_balance_rows() -> list[tuple[str, float]]:
    # latest 2026-06-01 is 95 days before BUILT_AT (Jun1->Jul1=30, Jul1->Aug1=31,
    # Aug1->Sep1=31, Sep1->Sep4=3 -> 95) -> CURRENT (cadence 102d/grace 17d).
    # 3m-avg window = latest - 65d = 2026-03-28; rows 04-01/05-01/06-01 all
    # fall inside -> avg = (-70000-72000-68000)/3 = -70000.0 exactly.
    # YoY target = 2026-06-01 - 365d = 2025-06-01 (neither 2025 nor 2026 is a
    # leap year, so no Feb-29 crosses this span) -> exact match, zero slack.
    # yoy_change = -68000.0 - (-63000.0) = -5000.0.
    return [
        ("2025-06-01", -63000.0),
        ("2026-04-01", -70000.0),
        ("2026-05-01", -72000.0),
        ("2026-06-01", -68000.0),
    ]


def _exports_rows() -> list[tuple[str, float]]:
    # YoY = (270000/260000 - 1) * 100 = 100/26 = 3.8461538... -> round 4dp = 3.8462.
    # exports - imports (at 2026-06-01) = 270000 - 338000 = -68000.0, exactly
    # matching the trade-balance level above (identity residual = 0.0).
    return [("2025-06-01", 260000.0), ("2026-05-01", 265000.0), ("2026-06-01", 270000.0)]


def _imports_rows() -> list[tuple[str, float]]:
    # YoY = (338000/325000 - 1) * 100 = 4.0 exactly (325000 * 1.04 = 338000).
    return [("2025-06-01", 325000.0), ("2026-05-01", 335000.0), ("2026-06-01", 338000.0)]


def _import_price_rows() -> list[tuple[str, float]]:
    # latest 2026-07-01 is 65 days before BUILT_AT (Jul1->Aug1=31, Aug1->Sep1=31,
    # Sep1->Sep4=3 -> 65) -> CURRENT (cadence 80d/grace 15d).
    # YoY = (134/130 - 1) * 100 = 400/130 = 3.0769230... -> round 4dp = 3.0769.
    return [("2025-07-01", 130.0), ("2026-07-01", 134.0)]


def _export_price_rows() -> list[tuple[str, float]]:
    # YoY = (131/127 - 1) * 100 = 400/127 = 3.14960629... -> round 4dp = 3.1496.
    # terms_of_trade = 131/134 = 0.97761194... -> round 4dp = 0.9776.
    return [("2025-07-01", 127.0), ("2026-07-01", 131.0)]


_UNSET = object()  # sentinel: distinguishes "caller omitted the arg" (use the
# default fixture) from "caller explicitly passed None" (a genuinely absent
# owner input) -- a plain default cannot tell those apart.


def _all_none_frames() -> dict:
    """TODAY's real disk truth (2026-09-04, verified via a live glob during
    authoring): none of the five parquets exist -- every frame is None."""
    return {
        tf.SERIES_TRADE_BALANCE: None,
        tf.SERIES_EXPORTS: None,
        tf.SERIES_IMPORTS: None,
        tf.SERIES_IMPORT_PRICE: None,
        tf.SERIES_EXPORT_PRICE: None,
    }


def _populated_frames() -> dict:
    """All five series populated (the self-healed shape)."""
    return {
        tf.SERIES_TRADE_BALANCE: _trade_balance_rows(),
        tf.SERIES_EXPORTS: _exports_rows(),
        tf.SERIES_IMPORTS: _imports_rows(),
        tf.SERIES_IMPORT_PRICE: _import_price_rows(),
        tf.SERIES_EXPORT_PRICE: _export_price_rows(),
    }


def _compose(fred_frames=_UNSET, **kw) -> dict:
    kw.setdefault("built_at", BUILT_AT)
    return tf.compose(
        _all_none_frames() if fred_frames is _UNSET else fred_frames, **kw,
    )


def _metric(snapshot: dict, metric_id: str) -> dict:
    return next(m for m in snapshot["metrics"]["items"] if m["metric_id"] == metric_id)


def _required(snapshot: dict, cid: str) -> dict:
    return next(c for c in snapshot["availability"]["required"] if c["component_id"] == cid)


def _implication(snapshot: dict, iid: str) -> dict | None:
    return next((i for i in snapshot["implications"]["items"] if i["implication_id"] == iid), None)


# --------------------------------------------------------------------------- #
# today's real first build (all five series None)
# --------------------------------------------------------------------------- #
def test_real_first_build_baseline_shape() -> None:
    snap = _compose()
    assert snap["workspace"]["id"] == "trade_flows"
    assert snap["region"]["code"] == "US"
    assert snap["availability"]["state"] == "SOURCE_FAILED"
    assert snap["availability"]["coverage_ratio"] == 0.0


def test_real_first_build_all_five_required_and_absent() -> None:
    snap = _compose()
    for cid in ("trade_balance", "exports", "imports", "import_price_index", "export_price_index"):
        r = _required(snap, cid)
        assert r["required"] is True
        assert r["status"] == "ABSENT"
        assert r["freshness"] == "SOURCE_FAILED"
        assert r["null_reason"] == "SOURCE_FAILED"


def test_real_first_build_no_optional_legs_at_all() -> None:
    # judgment call 1: unlike consumer_payments/rates_curves, Trade Flows has
    # NO optional split -- every one of the five required components IS the
    # entire required set.
    snap = _compose()
    optional = [c for c in snap["availability"]["required"] if not c["required"]]
    assert optional == []
    assert len(snap["availability"]["required"]) == 5


def test_real_first_build_every_domain_metric_typed_null() -> None:
    snap = _compose()
    domain_ids = (
        "trade_balance_level", "trade_balance_avg_3m", "trade_balance_yoy_change",
        "exports_level", "exports_yoy", "imports_level", "imports_yoy",
        "export_import_coverage_ratio", "import_price_index_level",
        "import_price_index_yoy", "export_price_index_level",
        "export_price_index_yoy", "terms_of_trade_proxy",
        "trade_balance_share_of_flows_pct", "trade_balance_identity_residual",
    )
    for mid in domain_ids:
        m = _metric(snap, mid)
        assert m["value"] is None, mid
        assert m["status"] == "ABSENT", mid
        assert m["null_reason"] == "SOURCE_FAILED", mid


def test_real_first_build_headline_still_not_applicable() -> None:
    # judgment call 10: unconditional, unaffected by data completeness.
    snap = _compose()
    h = snap["headline"]
    assert h["state_id"] is None
    assert h["status"] == "ABSENT"
    assert h["null_reason"] == "NOT_APPLICABLE"
    assert h["quadrant"] == {"x": None, "y": None, "x_status": "ABSENT", "y_status": "ABSENT"}


def test_real_first_build_contradiction_never_fires() -> None:
    snap = _compose()
    assert snap["availability"]["contradiction"]["present"] is False


def test_all_none_never_crashes_and_validates() -> None:
    snap = contract.finalize(tf.compose({}, built_at=BUILT_AT))
    contract.validate(snap)
    assert snap["availability"]["state"] == "SOURCE_FAILED"
    assert snap["availability"]["coverage_ratio"] == 0.0


def test_none_fred_frames_argument_never_crashes() -> None:
    snap = tf.compose(None, built_at=BUILT_AT)
    assert snap["availability"]["state"] == "SOURCE_FAILED"
    assert snap["workspace"]["id"] == "trade_flows"


# --------------------------------------------------------------------------- #
# trade balance: level + 3m average + YoY level change (hand-computable)
# --------------------------------------------------------------------------- #
def test_trade_balance_level_avg3m_and_yoy_change() -> None:
    snap = _compose(fred_frames=_populated_frames())
    level = _metric(snap, "trade_balance_level")
    assert level["value"] == pytest.approx(-68000.0)
    assert level["unit"] == "usd_millions_sa"
    avg = _metric(snap, "trade_balance_avg_3m")
    assert avg["value"] == pytest.approx(-70000.0)
    yoy = _metric(snap, "trade_balance_yoy_change")
    assert yoy["value"] == pytest.approx(-5000.0)
    assert yoy["value_type"] == "number"  # never "percent" -- judgment call 4


def test_trade_balance_yoy_change_never_uses_percent_value_type() -> None:
    snap = _compose(fred_frames=_populated_frames())
    yoy = _metric(snap, "trade_balance_yoy_change")
    assert yoy["value_type"] != "percent"
    assert yoy["unit"] == "usd_millions_sa"


def test_trade_balance_avg3m_insufficient_history_with_only_two_months() -> None:
    ff = _populated_frames()
    ff[tf.SERIES_TRADE_BALANCE] = [("2025-06-01", -63000.0), ("2026-05-01", -72000.0),
                                    ("2026-06-01", -68000.0)]
    snap = _compose(fred_frames=ff)
    avg = _metric(snap, "trade_balance_avg_3m")
    assert avg["value"] is None
    assert avg["null_reason"] == "INSUFFICIENT_HISTORY"
    # the level itself is unaffected
    assert _metric(snap, "trade_balance_level")["value"] == pytest.approx(-68000.0)


def test_trade_balance_avg3m_window_excludes_stale_rows_outside_65_days() -> None:
    ff = _populated_frames()
    # only ONE row falls inside the 65-day window (2026-06-01); the other two
    # observations sit far outside it -- still insufficient (< 3 in-window).
    ff[tf.SERIES_TRADE_BALANCE] = [
        ("2024-01-01", -50000.0), ("2025-01-01", -55000.0), ("2026-06-01", -68000.0),
    ]
    snap = _compose(fred_frames=ff)
    avg = _metric(snap, "trade_balance_avg_3m")
    assert avg["value"] is None
    assert avg["null_reason"] == "INSUFFICIENT_HISTORY"


def test_trade_balance_yoy_change_insufficient_history_single_row() -> None:
    ff = _populated_frames()
    ff[tf.SERIES_TRADE_BALANCE] = [("2026-06-01", -68000.0)]
    snap = _compose(fred_frames=ff)
    yoy = _metric(snap, "trade_balance_yoy_change")
    assert yoy["value"] is None
    assert yoy["null_reason"] == "INSUFFICIENT_HISTORY"


def test_trade_balance_missing_is_source_failed_and_degrades_state() -> None:
    ff = _populated_frames()
    ff[tf.SERIES_TRADE_BALANCE] = None
    snap = _compose(fred_frames=ff)
    r = _required(snap, "trade_balance")
    assert r["status"] == "ABSENT"
    assert r["freshness"] == "SOURCE_FAILED"
    assert snap["availability"]["state"] == "SOURCE_FAILED"
    assert "trade_balance" in snap["availability"]["degraded"]


# --------------------------------------------------------------------------- #
# exports / imports: level + YoY
# --------------------------------------------------------------------------- #
def test_exports_level_and_yoy() -> None:
    snap = _compose(fred_frames=_populated_frames())
    level = _metric(snap, "exports_level")
    assert level["value"] == pytest.approx(270000.0)
    assert level["unit"] == "usd_millions_sa"
    yoy = _metric(snap, "exports_yoy")
    expected = round((270000.0 / 260000.0 - 1.0) * 100.0, 4)
    assert yoy["value"] == pytest.approx(expected)
    assert yoy["value_type"] == "percent"


def test_imports_level_and_yoy() -> None:
    snap = _compose(fred_frames=_populated_frames())
    level = _metric(snap, "imports_level")
    assert level["value"] == pytest.approx(338000.0)
    yoy = _metric(snap, "imports_yoy")
    assert yoy["value"] == pytest.approx(4.0)  # 338000/325000 = 1.04 exactly


def test_exports_yoy_insufficient_history_single_row() -> None:
    ff = _populated_frames()
    ff[tf.SERIES_EXPORTS] = [("2026-06-01", 270000.0)]
    snap = _compose(fred_frames=ff)
    yoy = _metric(snap, "exports_yoy")
    assert yoy["value"] is None
    assert yoy["null_reason"] == "INSUFFICIENT_HISTORY"


def test_imports_missing_is_source_failed() -> None:
    ff = _populated_frames()
    ff[tf.SERIES_IMPORTS] = None
    snap = _compose(fred_frames=ff)
    level = _metric(snap, "imports_level")
    assert level["value"] is None
    assert level["null_reason"] == "SOURCE_FAILED"
    r = _required(snap, "imports")
    assert r["status"] == "ABSENT"


# --------------------------------------------------------------------------- #
# import / export price indexes: level + YoY
# --------------------------------------------------------------------------- #
def test_import_price_index_level_and_yoy() -> None:
    snap = _compose(fred_frames=_populated_frames())
    level = _metric(snap, "import_price_index_level")
    assert level["value"] == pytest.approx(134.0)
    assert level["value_type"] == "index"
    yoy = _metric(snap, "import_price_index_yoy")
    expected = round((134.0 / 130.0 - 1.0) * 100.0, 4)
    assert yoy["value"] == pytest.approx(expected)


def test_export_price_index_level_and_yoy() -> None:
    snap = _compose(fred_frames=_populated_frames())
    level = _metric(snap, "export_price_index_level")
    assert level["value"] == pytest.approx(131.0)
    yoy = _metric(snap, "export_price_index_yoy")
    expected = round((131.0 / 127.0 - 1.0) * 100.0, 4)
    assert yoy["value"] == pytest.approx(expected)


def test_price_index_levels_never_cite_seasonal_adjustment() -> None:
    snap = _compose(fred_frames=_populated_frames())
    for mid in ("import_price_index_level", "export_price_index_level"):
        m = _metric(snap, mid)
        assert "NOT seasonally adjusted" in m["transformation"]


def test_price_index_base_year_disclosed_as_unverified() -> None:
    snap = _compose(fred_frames=_populated_frames())
    for mid in ("import_price_index_level", "export_price_index_level"):
        m = _metric(snap, mid)
        assert "NOT verified in this authoring environment" in m["transformation"]


def test_export_price_missing_is_source_failed() -> None:
    ff = _populated_frames()
    ff[tf.SERIES_EXPORT_PRICE] = None
    snap = _compose(fred_frames=ff)
    level = _metric(snap, "export_price_index_level")
    assert level["value"] is None
    assert level["null_reason"] == "SOURCE_FAILED"


# --------------------------------------------------------------------------- #
# freshness cadence law (dollar-flow group 102d/17d, price-index group 80d/15d)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("age_days,expected", [
    (0, "CURRENT"), (102, "CURRENT"), (103, "LATE_WITHIN_TOLERANCE"),
    (119, "LATE_WITHIN_TOLERANCE"), (120, "STALE_SOURCE"),
])
def test_dollar_cadence_freshness_tiers(age_days, expected) -> None:
    asof = BUILT_DATE - dt.timedelta(days=age_days)
    got = tf._cadence_freshness(BUILT_AT, asof, tf._TRADE_DOLLAR_CADENCE_DAYS,
                                 tf._TRADE_DOLLAR_GRACE_DAYS, True)
    assert got == expected


@pytest.mark.parametrize("age_days,expected", [
    (0, "CURRENT"), (80, "CURRENT"), (81, "LATE_WITHIN_TOLERANCE"),
    (95, "LATE_WITHIN_TOLERANCE"), (96, "STALE_SOURCE"),
])
def test_price_index_cadence_freshness_tiers(age_days, expected) -> None:
    asof = BUILT_DATE - dt.timedelta(days=age_days)
    got = tf._cadence_freshness(BUILT_AT, asof, tf._TRADE_PRICE_CADENCE_DAYS,
                                 tf._TRADE_PRICE_GRACE_DAYS, True)
    assert got == expected


def test_cadence_freshness_absent_value_is_source_failed() -> None:
    assert tf._cadence_freshness(BUILT_AT, BUILT_DATE, 102, 17, False) == "SOURCE_FAILED"


def test_cadence_freshness_future_asof_is_source_failed() -> None:
    future = BUILT_DATE + dt.timedelta(days=5)
    assert tf._cadence_freshness(BUILT_AT, future, 102, 17, True) == "SOURCE_FAILED"


def test_populated_baseline_all_required_sources_current() -> None:
    snap = _compose(fred_frames=_populated_frames())
    assert snap["availability"]["state"] == "CURRENT"
    assert snap["availability"]["coverage_ratio"] == 1.0
    for cid in ("trade_balance", "exports", "imports", "import_price_index", "export_price_index"):
        assert _required(snap, cid)["freshness"] == "CURRENT"


def test_dollar_group_and_price_group_use_different_cadence_constants() -> None:
    assert tf._TRADE_DOLLAR_CADENCE_DAYS != tf._TRADE_PRICE_CADENCE_DAYS
    assert tf._TRADE_DOLLAR_GRACE_DAYS != tf._TRADE_PRICE_GRACE_DAYS


# --------------------------------------------------------------------------- #
# export/import coverage ratio (same-date pair, both SA dollar-flow legs)
# --------------------------------------------------------------------------- #
def test_coverage_ratio_hand_computed() -> None:
    snap = _compose(fred_frames=_populated_frames())
    m = _metric(snap, "export_import_coverage_ratio")
    assert m["value"] == pytest.approx(270000.0 / 338000.0, abs=1e-4)
    assert m["value_type"] == "ratio"
    assert m["reference_period"] == "2026-06-01"


def test_coverage_ratio_source_failed_when_one_leg_missing() -> None:
    ff = _populated_frames()
    ff[tf.SERIES_IMPORTS] = None
    snap = _compose(fred_frames=ff)
    m = _metric(snap, "export_import_coverage_ratio")
    assert m["value"] is None
    assert m["null_reason"] == "SOURCE_FAILED"


def test_coverage_ratio_source_failed_when_both_legs_missing() -> None:
    ff = _populated_frames()
    ff[tf.SERIES_EXPORTS] = None
    ff[tf.SERIES_IMPORTS] = None
    snap = _compose(fred_frames=ff)
    m = _metric(snap, "export_import_coverage_ratio")
    assert m["value"] is None
    assert m["null_reason"] == "SOURCE_FAILED"


def test_coverage_ratio_refused_when_legs_share_no_common_date() -> None:
    ff = _populated_frames()
    ff[tf.SERIES_EXPORTS] = [("2026-06-01", 270000.0)]
    ff[tf.SERIES_IMPORTS] = [("2025-01-01", 300000.0)]
    snap = _compose(fred_frames=ff)
    m = _metric(snap, "export_import_coverage_ratio")
    assert m["value"] is None
    assert m["null_reason"] == "COMPUTATION_REFUSED"


def test_coverage_ratio_refused_when_shared_date_too_stale() -> None:
    ff = _populated_frames()
    # both legs individually CURRENT off their own separately-recent prints,
    # but the only date they share lags each leg's own newest print by more
    # than the 20-day same-date bound.
    ff[tf.SERIES_EXPORTS] = [("2026-04-01", 265000.0), ("2026-06-01", 270000.0)]
    ff[tf.SERIES_IMPORTS] = [("2026-04-01", 330000.0), ("2026-07-01", 340000.0)]
    snap = _compose(fred_frames=ff)
    m = _metric(snap, "export_import_coverage_ratio")
    assert m["value"] is None
    assert m["null_reason"] == "COMPUTATION_REFUSED"


def test_coverage_ratio_accepts_at_exact_staleness_boundary() -> None:
    ff = _populated_frames()
    ff[tf.SERIES_EXPORTS] = [("2026-05-12", 268000.0), ("2026-06-01", 270000.0)]
    ff[tf.SERIES_IMPORTS] = [("2026-05-12", 336000.0)]
    # shared date 2026-05-12 lags exports' own newest (2026-06-01) by exactly
    # 20 days -- the bound is inclusive (<=).
    snap = _compose(fred_frames=ff)
    m = _metric(snap, "export_import_coverage_ratio")
    assert m["value"] == pytest.approx(268000.0 / 336000.0, abs=1e-4)
    assert m["reference_period"] == "2026-05-12"


def test_coverage_ratio_refused_one_day_past_boundary() -> None:
    ff = _populated_frames()
    ff[tf.SERIES_EXPORTS] = [("2026-05-11", 268000.0), ("2026-06-01", 270000.0)]
    ff[tf.SERIES_IMPORTS] = [("2026-05-11", 336000.0)]
    # lag = 21 days -- one more than the 20-day bound.
    snap = _compose(fred_frames=ff)
    m = _metric(snap, "export_import_coverage_ratio")
    assert m["value"] is None
    assert m["null_reason"] == "COMPUTATION_REFUSED"


# --------------------------------------------------------------------------- #
# terms-of-trade proxy (same-date pair, both NSA price-index legs)
# --------------------------------------------------------------------------- #
def test_terms_of_trade_proxy_hand_computed() -> None:
    snap = _compose(fred_frames=_populated_frames())
    m = _metric(snap, "terms_of_trade_proxy")
    assert m["value"] == pytest.approx(131.0 / 134.0, abs=1e-4)
    assert m["value_type"] == "ratio"
    assert m["reference_period"] == "2026-07-01"


def test_terms_of_trade_source_failed_when_one_leg_missing() -> None:
    ff = _populated_frames()
    ff[tf.SERIES_IMPORT_PRICE] = None
    snap = _compose(fred_frames=ff)
    m = _metric(snap, "terms_of_trade_proxy")
    assert m["value"] is None
    assert m["null_reason"] == "SOURCE_FAILED"


def test_terms_of_trade_refused_when_no_common_date() -> None:
    ff = _populated_frames()
    ff[tf.SERIES_IMPORT_PRICE] = [("2026-07-01", 134.0)]
    ff[tf.SERIES_EXPORT_PRICE] = [("2025-01-01", 120.0)]
    snap = _compose(fred_frames=ff)
    m = _metric(snap, "terms_of_trade_proxy")
    assert m["value"] is None
    assert m["null_reason"] == "COMPUTATION_REFUSED"


def test_terms_of_trade_only_reads_the_two_nsa_price_series() -> None:
    snap = _compose(fred_frames=_populated_frames())
    m = _metric(snap, "terms_of_trade_proxy")
    assert set(m["source_refs"]) == {"FRED:IQ", "FRED:IR"}


# --------------------------------------------------------------------------- #
# SA/NSA never-mix law (judgment call 2, verified by construction)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("mid", [
    "export_import_coverage_ratio", "trade_balance_share_of_flows_pct",
    "trade_balance_identity_residual",
])
def test_dollar_only_derived_reads_never_touch_price_series(mid) -> None:
    snap = _compose(fred_frames=_populated_frames())
    m = _metric(snap, mid)
    refs = set(m["source_refs"])
    assert not (refs & {"FRED:IR", "FRED:IQ"}), (mid, refs)


def test_terms_of_trade_never_touches_dollar_flow_series() -> None:
    snap = _compose(fred_frames=_populated_frames())
    m = _metric(snap, "terms_of_trade_proxy")
    refs = set(m["source_refs"])
    assert not (refs & {"FRED:BOPGSTB", "FRED:BOPTEXP", "FRED:BOPTIMP"})


def test_dollar_and_price_series_are_disjoint_sets() -> None:
    assert not (tf._DOLLAR_SERIES & tf._PRICE_SERIES)
    assert tf._DOLLAR_SERIES | tf._PRICE_SERIES == set(tf._ALL_SERIES)


# --------------------------------------------------------------------------- #
# $M unit discipline (judgment call 3): never rescaled to $bn, never mixed
# --------------------------------------------------------------------------- #
def test_dollar_flow_metrics_use_millions_never_billions() -> None:
    snap = _compose(fred_frames=_populated_frames())
    for mid in ("trade_balance_level", "trade_balance_avg_3m", "trade_balance_yoy_change",
                "exports_level", "imports_level"):
        m = _metric(snap, mid)
        assert m["unit"] == "usd_millions_sa"
        assert m["unit"] != "usd_billions_sa"


# --------------------------------------------------------------------------- #
# balance-as-share-of-flows (triple-leg: trade balance / exports / imports)
# --------------------------------------------------------------------------- #
def test_balance_share_of_flows_hand_computed() -> None:
    snap = _compose(fred_frames=_populated_frames())
    m = _metric(snap, "trade_balance_share_of_flows_pct")
    expected = round((-68000.0 / (270000.0 + 338000.0)) * 100.0, 4)
    assert m["value"] == pytest.approx(expected)
    assert m["value_type"] == "percent"
    assert m["reference_period"] == "2026-06-01"


def test_balance_share_of_flows_source_failed_when_one_leg_missing() -> None:
    ff = _populated_frames()
    ff[tf.SERIES_TRADE_BALANCE] = None
    snap = _compose(fred_frames=ff)
    m = _metric(snap, "trade_balance_share_of_flows_pct")
    assert m["value"] is None
    assert m["null_reason"] == "SOURCE_FAILED"


def test_balance_share_of_flows_source_failed_when_two_of_three_legs_missing() -> None:
    ff = _populated_frames()
    ff[tf.SERIES_EXPORTS] = None
    ff[tf.SERIES_IMPORTS] = None
    snap = _compose(fred_frames=ff)
    m = _metric(snap, "trade_balance_share_of_flows_pct")
    assert m["value"] is None
    assert m["null_reason"] == "SOURCE_FAILED"


def test_balance_share_of_flows_refused_on_date_mismatch() -> None:
    ff = _populated_frames()
    ff[tf.SERIES_TRADE_BALANCE] = [("2026-06-01", -68000.0)]
    ff[tf.SERIES_EXPORTS] = [("2026-06-01", 270000.0)]
    ff[tf.SERIES_IMPORTS] = [("2025-01-01", 300000.0)]
    snap = _compose(fred_frames=ff)
    m = _metric(snap, "trade_balance_share_of_flows_pct")
    assert m["value"] is None
    assert m["null_reason"] == "COMPUTATION_REFUSED"


def test_balance_share_and_identity_residual_share_the_same_triple_leg_date() -> None:
    snap = _compose(fred_frames=_populated_frames())
    share = _metric(snap, "trade_balance_share_of_flows_pct")
    residual = _metric(snap, "trade_balance_identity_residual")
    assert share["reference_period"] == residual["reference_period"] == "2026-06-01"


# --------------------------------------------------------------------------- #
# trade-balance identity residual + the one contradiction this composer ships
# --------------------------------------------------------------------------- #
def test_identity_residual_zero_at_healthy_baseline_no_contradiction() -> None:
    snap = _compose(fred_frames=_populated_frames())
    m = _metric(snap, "trade_balance_identity_residual")
    assert m["value"] == pytest.approx(0.0)
    assert m["status"] == "PRESENT"
    assert snap["availability"]["contradiction"]["present"] is False


def test_identity_residual_exactly_at_tolerance_boundary_does_not_fire() -> None:
    ff = _populated_frames()
    # tb=-68100 -> residual = -68100 - (270000-338000) = -68100-(-68000) = -100
    ff[tf.SERIES_TRADE_BALANCE] = [
        ("2025-06-01", -63000.0), ("2026-04-01", -70000.0),
        ("2026-05-01", -72000.0), ("2026-06-01", -68100.0),
    ]
    snap = _compose(fred_frames=ff)
    m = _metric(snap, "trade_balance_identity_residual")
    assert m["value"] == pytest.approx(-100.0)
    assert m["status"] == "PRESENT"
    assert snap["availability"]["contradiction"]["present"] is False


def test_identity_residual_just_over_boundary_fires() -> None:
    ff = _populated_frames()
    # tb=-68101 -> residual = -68101-(-68000) = -101, magnitude 101 > 100
    ff[tf.SERIES_TRADE_BALANCE] = [
        ("2025-06-01", -63000.0), ("2026-04-01", -70000.0),
        ("2026-05-01", -72000.0), ("2026-06-01", -68101.0),
    ]
    snap = _compose(fred_frames=ff)
    m = _metric(snap, "trade_balance_identity_residual")
    assert m["value"] == pytest.approx(-101.0)
    assert m["status"] == "DISAGREEMENT"
    assert m["null_reason"] == "DISAGREEMENT"
    c = snap["availability"]["contradiction"]
    assert c["present"] is True
    assert c["kind"] == "trade_balance_identity_disagreement"
    assert c["components"] == ["trade_balance_identity_residual"]
    assert any("contradiction=trade_balance_identity_disagreement" in r
               for r in snap["availability"]["reasons"])
    assert _implication(snap, "contradiction_trade_balance_identity_disagreement") is not None


def test_identity_residual_positive_direction_fires_too() -> None:
    ff = _populated_frames()
    # tb=-67800 -> residual = -67800-(-68000) = +200, magnitude 200 > 100
    ff[tf.SERIES_TRADE_BALANCE] = [
        ("2025-06-01", -63000.0), ("2026-04-01", -70000.0),
        ("2026-05-01", -72000.0), ("2026-06-01", -67800.0),
    ]
    snap = _compose(fred_frames=ff)
    m = _metric(snap, "trade_balance_identity_residual")
    assert m["value"] == pytest.approx(200.0)
    assert m["status"] == "DISAGREEMENT"


def test_identity_residual_source_failed_when_one_leg_missing() -> None:
    ff = _populated_frames()
    ff[tf.SERIES_EXPORTS] = None
    snap = _compose(fred_frames=ff)
    m = _metric(snap, "trade_balance_identity_residual")
    assert m["value"] is None
    assert m["null_reason"] == "SOURCE_FAILED"
    assert snap["availability"]["contradiction"]["present"] is False


def test_identity_residual_tolerance_constant_matches_disclosed_100m() -> None:
    assert tf._IDENTITY_RESIDUAL_TOLERANCE_USD_M == pytest.approx(100.0)


def test_dollar_flows_vs_price_index_divergence_never_fires_a_contradiction() -> None:
    # the hand-off's own domain brief raises this pattern as an INSIGHT, never
    # a contradiction (judgment call 8): nominal imports rising sharply while
    # import prices fall sharply must never flip contradiction.present. The
    # trade balance is kept CONSISTENT with the new imports level (tb = ex -
    # im = 270000 - 360000 = -90000) so this test isolates the dollar-vs-price
    # pattern from the (unrelated, and here deliberately silent) identity
    # residual check.
    ff = _populated_frames()
    ff[tf.SERIES_IMPORTS] = [("2025-06-01", 300000.0), ("2026-05-01", 330000.0),
                              ("2026-06-01", 360000.0)]  # imports up 20% YoY
    ff[tf.SERIES_TRADE_BALANCE] = [
        ("2025-06-01", -63000.0), ("2026-04-01", -70000.0),
        ("2026-05-01", -72000.0), ("2026-06-01", -90000.0),
    ]
    ff[tf.SERIES_IMPORT_PRICE] = [("2025-07-01", 150.0), ("2026-07-01", 120.0)]  # prices down 20%
    snap = _compose(fred_frames=ff)
    assert snap["availability"]["contradiction"]["present"] is False
    residual = _metric(snap, "trade_balance_identity_residual")
    assert residual["value"] == pytest.approx(0.0)


# --------------------------------------------------------------------------- #
# same-date discipline unit tests (the shared _pair_value / _triple_value /
# _shared_reading helpers)
# --------------------------------------------------------------------------- #
def test_shared_reading_returns_none_when_no_common_date() -> None:
    a = [(dt.date(2026, 6, 1), 1.0)]
    b = [(dt.date(2026, 1, 1), 2.0)]
    assert tf._shared_reading([a, b], 20) is None


def test_shared_reading_refuses_when_shared_date_exceeds_staleness_bound() -> None:
    a = [(dt.date(2026, 4, 1), 1.0), (dt.date(2026, 6, 1), 1.1)]
    b = [(dt.date(2026, 4, 1), 2.0)]
    assert tf._shared_reading([a, b], 20) is None


def test_shared_reading_accepts_at_exact_staleness_boundary_unit() -> None:
    a = [(dt.date(2026, 5, 12), 1.0), (dt.date(2026, 6, 1), 1.1)]
    b = [(dt.date(2026, 5, 12), 2.0)]
    result = tf._shared_reading([a, b], 20)
    assert result is not None
    d, vals = result
    assert d == dt.date(2026, 5, 12)
    assert vals == (1.0, 2.0)


def test_pair_value_leg_floor_both_missing_is_source_failed() -> None:
    d_, va, vb, fresh, null_reason = tf._pair_value([], [], "CURRENT", "CURRENT")
    assert (d_, va, vb) == (None, None, None)
    assert fresh == "SOURCE_FAILED"
    assert null_reason == "SOURCE_FAILED"


def test_pair_value_leg_floor_one_missing_is_source_failed() -> None:
    rows = [(dt.date(2026, 6, 1), 1.0)]
    d_, va, vb, fresh, null_reason = tf._pair_value(rows, [], "CURRENT", "CURRENT")
    assert (d_, va, vb) == (None, None, None)
    assert fresh == "SOURCE_FAILED"
    assert null_reason == "SOURCE_FAILED"


def test_triple_value_leg_floor_all_missing_is_source_failed() -> None:
    d_, vals, fresh, null_reason = tf._triple_value([], [], [], "CURRENT", "CURRENT", "CURRENT")
    assert vals == (None, None, None)
    assert fresh == "SOURCE_FAILED"
    assert null_reason == "SOURCE_FAILED"


def test_triple_value_leg_floor_one_of_three_missing_is_source_failed() -> None:
    rows = [(dt.date(2026, 6, 1), 1.0)]
    d_, vals, fresh, null_reason = tf._triple_value(rows, rows, [], "CURRENT", "CURRENT", "CURRENT")
    assert null_reason == "SOURCE_FAILED"


# --------------------------------------------------------------------------- #
# 3-month average window helper (unit-level)
# --------------------------------------------------------------------------- #
def test_trailing_avg_direct_helper_hand_computed() -> None:
    rows = [(dt.date(2026, 4, 1), -70000.0), (dt.date(2026, 5, 1), -72000.0),
            (dt.date(2026, 6, 1), -68000.0)]
    assert tf._trailing_avg(rows, 3, 65) == pytest.approx(-70000.0)


def test_trailing_avg_direct_helper_below_min_count() -> None:
    rows = [(dt.date(2026, 5, 1), -72000.0), (dt.date(2026, 6, 1), -68000.0)]
    assert tf._trailing_avg(rows, 3, 65) is None


def test_trailing_avg_direct_helper_empty_rows() -> None:
    assert tf._trailing_avg([], 3, 65) is None


# --------------------------------------------------------------------------- #
# malformed / None-row robustness
# --------------------------------------------------------------------------- #
def test_malformed_and_none_rows_are_dropped_never_fabricated() -> None:
    ff = _populated_frames()
    ff[tf.SERIES_TRADE_BALANCE] = [
        None, ("bad-date", -68000.0), ("2026-06-01", "not-a-number"),
        ("2026-05-01", -72000.0), ("2026-06-01", -68000.0),
    ]
    snap = _compose(fred_frames=ff)
    level = _metric(snap, "trade_balance_level")
    assert level["value"] == pytest.approx(-68000.0)


def test_rows_supplied_as_lists_not_tuples_work_identically() -> None:
    ff = _populated_frames()
    ff[tf.SERIES_TRADE_BALANCE] = [["2026-05-01", -72000.0], ["2026-06-01", -68000.0]]
    snap = _compose(fred_frames=ff)
    level = _metric(snap, "trade_balance_level")
    assert level["value"] == pytest.approx(-68000.0)


def test_duplicate_date_keeps_last_listed_value() -> None:
    ff = _populated_frames()
    ff[tf.SERIES_TRADE_BALANCE] = [
        ("2026-05-01", -72000.0), ("2026-06-01", -99999.0), ("2026-06-01", -68000.0),
    ]
    snap = _compose(fred_frames=ff)
    level = _metric(snap, "trade_balance_level")
    assert level["value"] == pytest.approx(-68000.0)


# --------------------------------------------------------------------------- #
# NOT_COVERED remainder: four named lanes, never rights-blocked
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("mid,keyword", [
    ("bilateral_country_trade_detail", "china_trade_detail"),
    ("petroleum_specific_trade_flows", "EIA"),
    ("customs_tariff_receipts", "collector"),
    ("trade_services_detail", "goods-AND-services"),
])
def test_remainder_metric_names_its_lane(mid, keyword) -> None:
    snap = _compose()
    m = _metric(snap, mid)
    assert m["value"] is None
    assert m["status"] == "ABSENT"
    assert m["null_reason"] == "NOT_COVERED"
    assert m["rights_state"] == "OPEN"
    assert keyword in m["transformation"]


def test_remainder_metrics_never_rights_blocked() -> None:
    snap = _compose()
    for mid in ("bilateral_country_trade_detail", "petroleum_specific_trade_flows",
                "customs_tariff_receipts", "trade_services_detail"):
        m = _metric(snap, mid)
        assert m["null_reason"] != "RIGHTS_BLOCKED"
        assert m["freshness"] == "NOT_COVERED"


def test_remainder_sources_present_and_not_covered() -> None:
    snap = _compose()
    remainder_ids = {"bilateral_country_trade_detail", "petroleum_specific_trade_flows",
                      "customs_tariff_receipts", "trade_services_detail"}
    src_ids = {s["source_id"] for s in snap["sources"]["items"]}
    assert remainder_ids <= src_ids
    for sid in remainder_ids:
        s = next(x for x in snap["sources"]["items"] if x["source_id"] == sid)
        assert s["freshness"] == "NOT_COVERED"
        assert s["rights_state"] == "OPEN"


def test_bilateral_country_disclosure_names_the_china_lane() -> None:
    snap = _compose()
    text = _implication(snap, "bilateral_country_not_covered_disclosure")["text"]["en"]
    assert "China" in text or "GACC" in text


def test_petroleum_disclosure_names_eia() -> None:
    snap = _compose()
    text = _implication(snap, "petroleum_not_covered_disclosure")["text"]["en"]
    assert "EIA" in text


# --------------------------------------------------------------------------- #
# metric inventory + digest determinism
# --------------------------------------------------------------------------- #
def test_metric_ids_are_unique_and_stable_count() -> None:
    snap = _compose()
    ids = [m["metric_id"] for m in snap["metrics"]["items"]]
    assert len(ids) == len(set(ids))
    assert len(ids) == 19


def test_metric_inventory_covers_every_named_domain_read() -> None:
    snap = _compose()
    ids = {m["metric_id"] for m in snap["metrics"]["items"]}
    expected = {
        "trade_balance_level", "trade_balance_avg_3m", "trade_balance_yoy_change",
        "exports_level", "exports_yoy", "imports_level", "imports_yoy",
        "export_import_coverage_ratio", "import_price_index_level",
        "import_price_index_yoy", "export_price_index_level",
        "export_price_index_yoy", "terms_of_trade_proxy",
        "trade_balance_share_of_flows_pct", "trade_balance_identity_residual",
        "bilateral_country_trade_detail", "petroleum_specific_trade_flows",
        "customs_tariff_receipts", "trade_services_detail",
    }
    assert ids == expected


def test_digest_is_deterministic_across_identical_input() -> None:
    snap1 = contract.finalize(_compose(fred_frames=_populated_frames()))
    snap2 = contract.finalize(_compose(fred_frames=_populated_frames()))
    assert snap1["generation"]["content_sha256"] == snap2["generation"]["content_sha256"]
    assert snap1["generation"]["generation_id"] == snap2["generation"]["generation_id"]


def test_digest_unaffected_by_code_version() -> None:
    snap1 = contract.finalize(_compose(code_version="abc123"))
    snap2 = contract.finalize(_compose(code_version="def456"))
    assert snap1["generation"]["content_sha256"] == snap2["generation"]["content_sha256"]


def test_digest_unaffected_by_built_at_when_same_calendar_facts() -> None:
    snap1 = contract.finalize(_compose(built_at="2026-09-04T00:00:00Z"))
    snap2 = contract.finalize(_compose(built_at="2026-09-04T23:59:59Z"))
    assert snap1["generation"]["content_sha256"] == snap2["generation"]["content_sha256"]


def test_digest_changes_when_consumed_field_changes() -> None:
    snap1 = contract.finalize(_compose(fred_frames=_populated_frames()))
    ff2 = _populated_frames()
    ff2[tf.SERIES_TRADE_BALANCE] = [
        ("2025-06-01", -63000.0), ("2026-04-01", -70000.0),
        ("2026-05-01", -72000.0), ("2026-06-01", -99000.0),
    ]
    snap2 = contract.finalize(_compose(fred_frames=ff2))
    assert snap1["generation"]["content_sha256"] != snap2["generation"]["content_sha256"]


def test_digest_changes_when_all_none_becomes_populated() -> None:
    snap1 = contract.finalize(_compose())
    snap2 = contract.finalize(_compose(fred_frames=_populated_frames()))
    assert snap1["generation"]["content_sha256"] != snap2["generation"]["content_sha256"]


def test_digest_unaffected_by_unconsumed_fred_frames_key() -> None:
    snap1 = contract.finalize(_compose())
    ff3 = _all_none_frames()
    ff3["DGS10"] = [("2026-09-03", 4.2)]  # never read by this composer
    snap3 = contract.finalize(_compose(fred_frames=ff3))
    assert snap1["generation"]["content_sha256"] == snap3["generation"]["content_sha256"]


def test_digest_unaffected_by_unconsumed_row_tuple_element() -> None:
    snap1 = contract.finalize(_compose(fred_frames=_populated_frames()))
    ff4 = _populated_frames()
    ff4[tf.SERIES_TRADE_BALANCE] = [
        ("2025-06-01", -63000.0, "unrelated-extra-field"),
        ("2026-04-01", -70000.0, {"nested": "also unrelated"}),
        ("2026-05-01", -72000.0, None),
        ("2026-06-01", -68000.0, 42),
    ]
    snap4 = contract.finalize(_compose(fred_frames=ff4))
    assert snap1["generation"]["content_sha256"] == snap4["generation"]["content_sha256"]


def test_digest_unaffected_by_duplicate_date_keeping_last_listed() -> None:
    snap1 = contract.finalize(_compose(fred_frames=_populated_frames()))
    ff5 = _populated_frames()
    ff5[tf.SERIES_TRADE_BALANCE] = [
        ("2025-06-01", -63000.0), ("2026-04-01", -70000.0),
        ("2026-05-01", -72000.0), ("2026-06-01", -999.0), ("2026-06-01", -68000.0),
    ]
    snap5 = contract.finalize(_compose(fred_frames=ff5))
    assert snap1["generation"]["content_sha256"] == snap5["generation"]["content_sha256"]


# --------------------------------------------------------------------------- #
# changes / method-version comparability
# --------------------------------------------------------------------------- #
def _prior(method=tf.METHOD_VERSION, trade_balance_level=-68000.0,
           gen="trade_flows-US-deadbeefdeadbeef") -> dict:
    prior = _compose(fred_frames=_populated_frames())
    prior["headline"]["method_version"] = method
    prior["generation"]["generation_id"] = gen
    for m in prior["metrics"]["items"]:
        if m["metric_id"] == "trade_balance_level":
            m["value"] = trade_balance_level
    return prior


def test_changes_no_prior_yields_warmup() -> None:
    snap = _compose()
    assert snap["changes"]["comparability"] == "NO_PRIOR"
    assert snap["changes"]["null_reason"] == "WARMUP"


def test_changes_method_mismatch_refuses_numeric_comparison() -> None:
    snap = _compose(prior_snapshot=_prior(method="trade_flows.compose.v0"))
    assert snap["changes"]["comparability"] == "METHOD_CHANGED"
    assert snap["changes"]["deltas"] == []
    assert snap["changes"]["null_reason"] == "COMPUTATION_REFUSED"


def test_changes_comparable_prior_produces_deltas() -> None:
    snap = _compose(fred_frames=_populated_frames(), prior_snapshot=_prior(trade_balance_level=-60000.0))
    assert snap["changes"]["comparability"] == "COMPARABLE"
    ids = {d["metric_id"] for d in snap["changes"]["deltas"]}
    assert ids == set(tf._TRACKED_CHANGE_METRICS)
    delta = next(d for d in snap["changes"]["deltas"] if d["metric_id"] == "trade_balance_level")
    assert delta["prior_value"] == -60000.0
    assert delta["current_value"] == pytest.approx(-68000.0)
    assert delta["delta"] == pytest.approx(-8000.0)


# --------------------------------------------------------------------------- #
# corrections / supersession honesty
# --------------------------------------------------------------------------- #
def test_corrections_none_for_first_print() -> None:
    snap = _compose()
    assert snap["corrections"]["correction_state"] == "none"
    assert snap["corrections"]["predecessor_generation_id"] is None


def test_corrections_superseded_when_same_period_value_changes() -> None:
    ff = _populated_frames()
    prior_snap = contract.finalize(tf.compose(ff, built_at=BUILT_AT))
    ff2 = copy.deepcopy(ff)
    ff2[tf.SERIES_TRADE_BALANCE][-1] = ("2026-06-01", -75000.0)
    snap2 = tf.compose(ff2, built_at=BUILT_AT, prior_snapshot=prior_snap)
    assert snap2["corrections"]["correction_state"] == "superseded"
    assert snap2["corrections"]["changed_fingerprints"]
    assert snap2["corrections"]["predecessor_generation_id"] == prior_snap["generation"]["generation_id"]


def test_corrections_none_when_reference_period_advances() -> None:
    ff = _populated_frames()
    prior_snap = contract.finalize(tf.compose(ff, built_at=BUILT_AT))
    ff2 = copy.deepcopy(ff)
    # effective_date is the max latest-date across ALL five series, which the
    # default fixture already pins at 2026-07-01 (IR/IQ's own latest date) --
    # appending a later IR observation is what actually advances it.
    ff2[tf.SERIES_IMPORT_PRICE] = ff2[tf.SERIES_IMPORT_PRICE] + [("2026-08-01", 136.0)]
    snap2 = tf.compose(ff2, built_at="2026-10-04T00:00:00Z", prior_snapshot=prior_snap)
    assert snap2["corrections"]["correction_state"] == "none"


def test_corrections_no_change_republication_wording() -> None:
    ff = _populated_frames()
    prior_snap = contract.finalize(tf.compose(ff, built_at=BUILT_AT))
    snap2 = tf.compose(ff, built_at=BUILT_AT, prior_snapshot=prior_snap)
    assert snap2["corrections"]["correction_state"] == "none"
    assert "no-change republication" in snap2["corrections"]["note"]


# --------------------------------------------------------------------------- #
# headline: unconditionally NOT_APPLICABLE (never data-completeness-dependent)
# --------------------------------------------------------------------------- #
def test_headline_is_not_applicable_a_design_absence() -> None:
    snap = _compose(fred_frames=_populated_frames())
    h = snap["headline"]
    assert h["state_id"] is None
    assert h["status"] == "ABSENT"
    assert h["null_reason"] == "NOT_APPLICABLE"
    assert h["nearest_boundary"]["null_reason"] == "NOT_APPLICABLE"
    assert h["one_month_vector"]["null_reason"] == "NOT_APPLICABLE"
    assert h["hysteresis"]["applied"] is False
    assert "Chairman-authorized expansion" in h["hysteresis"]["note"]


def test_axes_items_is_empty_by_design() -> None:
    snap = _compose(fred_frames=_populated_frames())
    assert snap["axes"]["items"] == []


def test_headline_unaffected_by_full_data_completeness() -> None:
    snap = _compose(fred_frames=_populated_frames())
    assert snap["availability"]["state"] == "CURRENT"
    assert snap["headline"]["null_reason"] == "NOT_APPLICABLE"


def test_headline_hysteresis_note_never_leaks_raw_not_applicable_token() -> None:
    note = _compose()["headline"]["hysteresis"]["note"]
    assert "NOT_APPLICABLE" not in note


# --------------------------------------------------------------------------- #
# schema validation
# --------------------------------------------------------------------------- #
def test_real_first_build_validates_against_the_closed_contract() -> None:
    snap = contract.finalize(_compose())
    contract.validate(snap)
    assert snap["authority"]["can_size"] is False
    assert snap["authority"]["can_execute"] is False
    assert snap["authority"]["can_originate_signal"] is False


def test_fully_populated_snapshot_validates() -> None:
    snap = contract.finalize(tf.compose(_populated_frames(), built_at=BUILT_AT))
    contract.validate(snap)


def test_degraded_single_leg_missing_still_validates() -> None:
    ff = _populated_frames()
    ff[tf.SERIES_IMPORT_PRICE] = None
    snap = contract.finalize(tf.compose(ff, built_at=BUILT_AT))
    contract.validate(snap)


def test_contradiction_fired_snapshot_validates() -> None:
    ff = _populated_frames()
    ff[tf.SERIES_TRADE_BALANCE] = [
        ("2025-06-01", -63000.0), ("2026-04-01", -70000.0),
        ("2026-05-01", -72000.0), ("2026-06-01", -68101.0),
    ]
    snap = contract.finalize(tf.compose(ff, built_at=BUILT_AT))
    contract.validate(snap)
    assert snap["availability"]["contradiction"]["present"] is True


def test_all_inputs_missing_never_crashes_and_types_every_domain_metric_absent() -> None:
    snap = tf.compose({}, built_at=BUILT_AT)
    for m in snap["metrics"]["items"]:
        assert m["value"] is None
        assert m["status"] == "ABSENT"
        assert m["null_reason"] in ("SOURCE_FAILED", "NOT_COVERED", "COMPUTATION_REFUSED")


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


def test_prose_fields_contain_no_raw_enum_tokens_real_first_build() -> None:
    snap = _compose()
    leaks = _find_raw_token_leaks(snap)
    assert leaks == [], f"raw enum tokens leaked into prose field(s): {leaks}"


def test_prose_fields_contain_no_raw_enum_tokens_populated_build() -> None:
    # exercise every disclosure branch at once: contradiction fired, a
    # required leg missing, the typed-absent remainder always present.
    ff = _populated_frames()
    ff[tf.SERIES_TRADE_BALANCE] = [
        ("2025-06-01", -63000.0), ("2026-04-01", -70000.0),
        ("2026-05-01", -72000.0), ("2026-06-01", -68101.0),
    ]
    ff[tf.SERIES_IMPORT_PRICE] = None
    snap = _compose(fred_frames=ff)
    leaks = _find_raw_token_leaks(snap)
    assert leaks == [], f"raw enum tokens leaked into prose field(s): {leaks}"


# --------------------------------------------------------------------------- #
# zh-label integrity: composer-authored English phrasing must never leak into
# the composer-authored zh sibling
# --------------------------------------------------------------------------- #
_COMPOSER_ENGLISH_PHRASES = (
    "Chairman-authorized expansion", "same-date discipline", "never mixed",
    "a design absence, not a data gap", "cosmetic bucket reuse",
    "revision-vintage mismatch", "context/display-tier-only",
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
    snap = _compose(fred_frames=_populated_frames())
    leaks = _find_english_leaks(snap)
    assert leaks == [], f"English phrasing leaked into zh field(s): {leaks}"


def test_zh_narrative_present_wherever_english_is_composer_authored() -> None:
    snap = _compose(fred_frames=_populated_frames())
    for impl in snap["implications"]["items"]:
        assert impl["text"]["en"], impl
        assert impl["text"]["zh"], impl
    assert snap["workspace"]["title"]["zh"]
    assert snap["workspace"]["title"]["zh"] == "贸易流动"
    assert snap["headline"]["subtitle"]["zh"]
    for d in snap["drivers"]["rate_side"] + snap["drivers"]["balance_sheet"]:
        assert d["label"]["zh"]
    for s in snap["sources"]["items"]:
        assert s["label"]["zh"]


# --------------------------------------------------------------------------- #
# availability worst-of law (all five required, no optional escape hatch)
# --------------------------------------------------------------------------- #
def test_availability_state_degrades_when_any_single_required_leg_absent() -> None:
    ff = _populated_frames()
    ff[tf.SERIES_EXPORT_PRICE] = None
    snap = _compose(fred_frames=ff)
    assert snap["availability"]["state"] == "SOURCE_FAILED"
    assert "export_price_index" in snap["availability"]["degraded"]
    assert snap["availability"]["coverage_ratio"] == pytest.approx(0.8)


def test_availability_state_degrades_on_late_required_leg() -> None:
    ff = _populated_frames()
    # 2026-05-17 is 110 days before BUILT_AT (May17->May31=14, +Jun(30)+Jul(31)
    # +Aug(31)+Sep1->4(4) = 14+30+31+31+4 = 110) -- inside the dollar-flow
    # group's LATE_WITHIN_TOLERANCE band (103-119 days under cadence 102d /
    # grace 17d), pushing the trade-balance leg outside CURRENT but inside grace.
    ff[tf.SERIES_TRADE_BALANCE] = [("2026-02-17", -70000.0), ("2026-05-17", -68000.0)]
    snap = _compose(fred_frames=ff)
    r = _required(snap, "trade_balance")
    assert r["freshness"] == "LATE_WITHIN_TOLERANCE"
    assert snap["availability"]["state"] != "CURRENT"
    assert "trade_balance" in snap["availability"]["degraded"]


def test_coverage_ratio_field_reflects_required_set_of_five() -> None:
    snap = _compose(fred_frames=_populated_frames())
    assert snap["availability"]["coverage_ratio"] == 1.0
    assert len(snap["availability"]["required"]) == 5


# --------------------------------------------------------------------------- #
# drivers / implications / scenario / alert contracts
# --------------------------------------------------------------------------- #
def test_driver_bucket_reuse_disclosed_in_drivers_and_implication() -> None:
    snap = _compose(fred_frames=_populated_frames())
    rate_side_ids = {d["driver_id"] for d in snap["drivers"]["rate_side"]}
    balance_sheet_ids = {d["driver_id"] for d in snap["drivers"]["balance_sheet"]}
    assert "import_price_index_level" in rate_side_ids
    assert "terms_of_trade_proxy" in rate_side_ids
    assert "trade_balance_level" in balance_sheet_ids
    assert "trade_balance_identity_residual" in balance_sheet_ids
    assert _implication(snap, "driver_bucket_naming_note") is not None


@pytest.mark.parametrize("iid", [
    "headline_unavailable", "sa_nsa_never_mix_disclosure",
    "same_date_discipline_disclosure", "no_alfred_pit_vintage_capture",
    "bilateral_country_not_covered_disclosure", "petroleum_not_covered_disclosure",
    "customs_tariff_not_covered_disclosure", "services_detail_not_covered_disclosure",
    "driver_bucket_naming_note",
])
def test_disclosure_implications_present_on_real_first_build(iid) -> None:
    snap = _compose()
    assert _implication(snap, iid) is not None, iid


def test_domain_read_implications_present_when_populated() -> None:
    snap = _compose(fred_frames=_populated_frames())
    for iid in ("trade_balance_read", "flows_read", "price_index_read",
                "balance_share_of_flows_read", "identity_residual_read"):
        assert _implication(snap, iid) is not None, iid


def test_scenario_contract_execution_unavailable() -> None:
    snap = _compose()
    sc = snap["scenario_contract"]
    assert sc["execution_available"] is False
    assert sc["result_schema"] == "mastermind.macro_workspace_scenario_result.v1"
    assert len(sc["assumptions"]) >= 3


def test_alert_contract_service_unavailable() -> None:
    snap = _compose()
    ac = snap["alert_contract"]
    assert ac["service_available"] is False
    assert len(ac["eligible_conditions"]) >= 3


# --------------------------------------------------------------------------- #
# sources
# --------------------------------------------------------------------------- #
def test_sources_include_all_nine_entries() -> None:
    snap = _compose()
    source_ids = {s["source_id"] for s in snap["sources"]["items"]}
    assert len(source_ids) == 9
    assert {"bopgstb", "boptexp", "boptimp", "ir", "iq"} <= source_ids


def test_five_live_fred_sources_provider_names_fred() -> None:
    snap = _compose()
    for sid in ("bopgstb", "boptexp", "boptimp", "ir", "iq"):
        s = next(x for x in snap["sources"]["items"] if x["source_id"] == sid)
        assert "FRED" in s["provider"]


def test_source_refs_use_the_prescribed_fred_style() -> None:
    snap = _compose(fred_frames=_populated_frames())
    assert _metric(snap, "trade_balance_level")["source_refs"] == ["FRED:BOPGSTB"]
    assert set(_metric(snap, "export_import_coverage_ratio")["source_refs"]) == {
        "FRED:BOPTEXP", "FRED:BOPTIMP",
    }
    assert set(_metric(snap, "trade_balance_identity_residual")["source_refs"]) == {
        "FRED:BOPGSTB", "FRED:BOPTEXP", "FRED:BOPTIMP",
    }


# --------------------------------------------------------------------------- #
# authority ceiling (no rank/gate/size/originate/execute authority anywhere)
# --------------------------------------------------------------------------- #
def test_authority_is_fully_descriptive() -> None:
    snap = _compose(fred_frames=_populated_frames())
    a = snap["authority"]
    assert a["class"] == "context_only"
    assert a["display_only"] is True
    assert a["can_rank"] is False
    assert a["can_gate"] is False
    assert a["can_size"] is False
    assert a["can_originate_signal"] is False
    assert a["can_execute"] is False
    assert a["axis_authority_ceiling"] == "DESCRIPTIVE"
    for m in snap["metrics"]["items"]:
        assert m["authority_ceiling"] == "DESCRIPTIVE"


# --------------------------------------------------------------------------- #
# registry / workspace identity sanity
# --------------------------------------------------------------------------- #
def test_workspace_id_matches_registry_vocabulary() -> None:
    snap = _compose()
    assert snap["workspace"]["id"] == "trade_flows"
    assert snap["schema"]["contract"] == "mastermind.macro_workspace_snapshot.v1"


def test_series_identity_constants_match_the_orchestrator_config() -> None:
    # cross-checked against build.py's own _TRADE_FRED_COLUMNS at authoring
    # time -- these five ids/columns are load-bearing for the orchestrator.
    assert tf.SERIES_TRADE_BALANCE == "BOPGSTB"
    assert tf.SERIES_EXPORTS == "BOPTEXP"
    assert tf.SERIES_IMPORTS == "BOPTIMP"
    assert tf.SERIES_IMPORT_PRICE == "IR"
    assert tf.SERIES_EXPORT_PRICE == "IQ"


def test_module_workspace_id_constant() -> None:
    assert tf.WORKSPACE_ID == "trade_flows"
    assert tf.__name__.endswith("trade_flows")
