"""Composer tests for the US consumer_payments workspace (F01 / R1B).

RED-first: each degraded condition must produce the correct TYPED state and
never a zero / neutral / calm default. Covers: the TODAY'S-DISK-TRUTH shape
(RSAFS + UMCSENT populated, the other seven series None -> the REAL first
build, headline refused COMPUTATION_REFUSED), the None-frame self-heal path
(each of the seven pending series populated one at a time and all together),
the corrected UMCSENT freshness cadence (61d/15d grace, hand-traced against
the concrete 2026-09-04 calendar fact that a July print sitting at age 65
should already be superseded by an August final -- see consumer_payments.py
judgment call 1), per-series MoM/YoY/level derived-read correctness on
hand-computable fixtures, the leg-floor laws on both headline axes, the
three-leg confidence-vs-credit-financed-spending contradiction (fires /
silent / flat-band-guarded / leg-absent), the typed-ABSENT remainder
(card-network panels RIGHTS_BLOCKED, NY Fed QHDC NOT_COVERED), digest
determinism with a genuinely-consumed-field mutation and unconsumed-field
negative controls, a prose scan for raw enum-token leaks, zh-narrative
integrity, and schema validation.

    python3 -m pytest tests/test_macro_workspace_consumer_payments.py -x -q
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

from engine.market_os.macro_workspaces import consumer_payments as cp  # noqa: E402
from engine.market_os.macro_workspaces import contract  # noqa: E402

BUILT_AT = "2026-09-04T00:00:00Z"
BUILT_DATE = dt.date(2026, 9, 4)


# --------------------------------------------------------------------------- #
# fixtures (small, hand-computable row lists -- see the inline arithmetic
# notes next to every derived-value assertion below)
# --------------------------------------------------------------------------- #
def _retail_rows() -> list[tuple[str, float]]:
    # anchor 2026-07-01 is 65 days before BUILT_AT (Jul->Aug 31d, Aug->Sep 31d,
    # Sep1->Sep4 3d = 65) -> CURRENT (cadence 80d/grace 17d).
    # MoM target = 2026-07-01 - 30d = 2026-06-01 (June has 30 days, so
    # June1->July1 is exactly 30 days) -> zero slack.
    # YoY target = 2026-07-01 - 365d = 2025-07-01 (2026 is not a leap year,
    # no Feb-29 crosses this span) -> zero slack.
    return [("2025-07-01", 660000.0), ("2026-06-01", 680000.0), ("2026-07-01", 700000.0)]


def _sentiment_rows_current() -> list[tuple[str, float]]:
    # anchor 2026-08-01 is 34 days before BUILT_AT (Aug->Sep 31d, Sep1->4 3d)
    # -> CURRENT (cadence 61d/grace 15d, judgment call 1).
    # YoY target = 2026-08-01 - 365d = 2025-08-01 (no leap-day crossing).
    return [("2025-08-01", 65.0), ("2026-08-01", 68.5)]


def _sentiment_rows_late() -> list[tuple[str, float]]:
    # anchor 2026-07-01 is 65 days before BUILT_AT -- under the corrected
    # 61d/15d cadence: 65 > 61 (not CURRENT) and 65 <= 61+15=76
    # -> LATE_WITHIN_TOLERANCE. This is the exact hand-off scenario (a July
    # UMCSENT print sitting on disk at age 65 on 2026-09-04, after the
    # August final should already exist upstream) -- see judgment call 1.
    return [("2025-07-01", 66.0), ("2026-07-01", 68.0)]


def _credit_total_rows() -> list[tuple[str, float]]:
    # anchor 2026-06-01 is 95 days before BUILT_AT (Jun->Jul 30d, Jul->Aug
    # 31d, Aug->Sep 31d, Sep1->4 3d = 95) -> CURRENT (cadence 100d/grace 15d).
    # YoY target = 2026-06-01 - 365d = 2025-06-01 (no leap-day crossing).
    return [("2025-06-01", 4800.0), ("2026-06-01", 4950.0)]


def _credit_revolving_rows() -> list[tuple[str, float]]:
    # same anchor/target dates as _credit_total_rows.
    # YoY = (1300/1250 - 1) * 100 = 4.0% exactly.
    return [("2025-06-01", 1250.0), ("2026-06-01", 1300.0)]


def _credit_revolving_rows_flat() -> list[tuple[str, float]]:
    # YoY = (1255/1250 - 1) * 100 = 0.4% -- inside the 1.0% flat band.
    return [("2025-06-01", 1250.0), ("2026-06-01", 1255.0)]


def _credit_nonrevolving_rows() -> list[tuple[str, float]]:
    return [("2025-06-01", 3550.0), ("2026-06-01", 3650.0)]


def _saving_rate_rows_falling() -> list[tuple[str, float]]:
    # anchor 2026-07-01 is 65 days before BUILT_AT -> CURRENT (cadence
    # 92d/grace 15d). 3m-change target = 2026-07-01 - 91d = 2026-04-01
    # (Apr1->May1 30d, May1->Jun1 31d, Jun1->Jul1 30d = 91) -> zero slack.
    # change_3m = 4.0 - 4.5 = -0.5 pct pts (beyond the -0.2 flat band).
    return [("2026-04-01", 4.5), ("2026-07-01", 4.0)]


def _saving_rate_rows_flat() -> list[tuple[str, float]]:
    # change_3m = 4.45 - 4.5 = -0.05 -- inside the 0.2 flat band.
    return [("2026-04-01", 4.5), ("2026-07-01", 4.45)]


def _real_income_rows() -> list[tuple[str, float]]:
    # same cadence/anchor law as saving rate (BEA, 92d/15d).
    # YoY = (17400/17000 - 1) * 100.
    return [("2025-07-01", 17000.0), ("2026-07-01", 17400.0)]


def _cc_delinquency_rows() -> list[tuple[str, float]]:
    # anchor 2026-01-01 is 246 days before BUILT_AT (Jan 31 + Feb 28 [2026
    # not leap] + Mar 31 + Apr 30 + May 31 + Jun 30 + Jul 31 + Aug 31 +
    # Sep1->4 3 = 246) -> CURRENT (cadence 255d/grace 30d).
    return [("2026-01-01", 3.2)]


def _mortgage_delinquency_rows() -> list[tuple[str, float]]:
    return [("2026-01-01", 1.8)]


_UNSET = object()  # sentinel: distinguishes "caller omitted the arg" (use the
# default fixture) from "caller explicitly passed None" (a genuinely absent
# owner input) -- a plain default cannot tell those apart.


def _pending_fred_frames() -> dict:
    """TODAY's real disk truth (2026-09-04): only RSAFS + UMCSENT populated,
    the other seven series None (pending collector population)."""
    return {
        cp.SERIES_RETAIL_SALES: _retail_rows(),
        cp.SERIES_SENTIMENT: _sentiment_rows_current(),
        cp.SERIES_CREDIT_TOTAL: None,
        cp.SERIES_CREDIT_REVOLVING: None,
        cp.SERIES_CREDIT_NONREVOLVING: None,
        cp.SERIES_SAVING_RATE: None,
        cp.SERIES_REAL_DISPOSABLE_INCOME: None,
        cp.SERIES_CC_DELINQUENCY: None,
        cp.SERIES_MORTGAGE_DELINQUENCY: None,
    }


def _populated_fred_frames() -> dict:
    """All nine series populated (the self-healed shape)."""
    return {
        cp.SERIES_RETAIL_SALES: _retail_rows(),
        cp.SERIES_SENTIMENT: _sentiment_rows_current(),
        cp.SERIES_CREDIT_TOTAL: _credit_total_rows(),
        cp.SERIES_CREDIT_REVOLVING: _credit_revolving_rows(),
        cp.SERIES_CREDIT_NONREVOLVING: _credit_nonrevolving_rows(),
        cp.SERIES_SAVING_RATE: _saving_rate_rows_falling(),
        cp.SERIES_REAL_DISPOSABLE_INCOME: _real_income_rows(),
        cp.SERIES_CC_DELINQUENCY: _cc_delinquency_rows(),
        cp.SERIES_MORTGAGE_DELINQUENCY: _mortgage_delinquency_rows(),
    }


def _compose(fred_frames=_UNSET, **kw) -> dict:
    kw.setdefault("built_at", BUILT_AT)
    return cp.compose(
        _pending_fred_frames() if fred_frames is _UNSET else fred_frames, **kw,
    )


def _metric(snapshot: dict, metric_id: str) -> dict:
    return next(m for m in snapshot["metrics"]["items"] if m["metric_id"] == metric_id)


def _required(snapshot: dict, cid: str) -> dict:
    return next(c for c in snapshot["availability"]["required"] if c["component_id"] == cid)


def _implication(snapshot: dict, iid: str) -> dict | None:
    return next((i for i in snapshot["implications"]["items"] if i["implication_id"] == iid), None)


def _axis(snapshot: dict, axis_id: str) -> dict:
    return next(a for a in snapshot["axes"]["items"] if a["axis_id"] == axis_id)


def _axis_component(axis_dict: dict, component_id: str) -> dict:
    return next(c for c in axis_dict["components"] if c["component_id"] == component_id)


# --------------------------------------------------------------------------- #
# today's real first build (pending fixture)
# --------------------------------------------------------------------------- #
def test_pending_build_baseline_shape() -> None:
    snap = _compose()
    assert snap["workspace"]["id"] == "consumer_payments"
    assert snap["region"]["code"] == "US"
    for cid in ("retail_sales", "consumer_sentiment"):
        r = _required(snap, cid)
        assert r["freshness"] == "CURRENT", (cid, r)
        assert r["status"] == "PRESENT"
    assert snap["availability"]["state"] == "CURRENT"
    assert snap["availability"]["coverage_ratio"] == 1.0


def test_pending_build_optional_legs_absent_never_degrade_required_state() -> None:
    snap = _compose()
    assert snap["availability"]["state"] == "CURRENT"
    optional_ids = {"consumer_credit_total", "consumer_credit_revolving",
                     "consumer_credit_nonrevolving", "personal_saving_rate",
                     "real_disposable_income", "cc_delinquency", "mortgage_delinquency"}
    for cid in optional_ids:
        c = next(x for x in snap["availability"]["required"] if x["component_id"] == cid)
        assert c["required"] is False
        assert c["status"] == "ABSENT"
        assert c["freshness"] == "SOURCE_FAILED"


def test_pending_build_headline_is_computation_refused_not_not_applicable() -> None:
    snap = _compose()
    h = snap["headline"]
    assert h["state_id"] is None
    assert h["status"] == "ABSENT"
    assert h["null_reason"] == "COMPUTATION_REFUSED"
    assert h["null_reason"] != "NOT_APPLICABLE"
    assert h["quadrant"]["x"] is None  # x needs real_disposable_income_yoy, absent today
    assert h["quadrant"]["y"] is None  # y needs >=2 of 4 credit-stress legs, all absent today
    assert h["nearest_boundary"]["null_reason"] == "COMPUTATION_REFUSED"
    assert h["one_month_vector"]["null_reason"] == "COMPUTATION_REFUSED"
    assert "two-axis blueprint" in h["hysteresis"]["note"]


def test_pending_build_axes_items_populated_not_empty() -> None:
    # unlike housing (permanently refused, axes.items == []), Consumer's
    # blueprint IS computable in principle, so both axis objects are always
    # emitted with their components arrays showing exactly which legs exist.
    snap = _compose()
    ids = {a["axis_id"] for a in snap["axes"]["items"]}
    assert ids == {"cash_flow_momentum", "credit_stress"}
    x = _axis(snap, "cash_flow_momentum")
    assert len(x["components"]) == 2
    y = _axis(snap, "credit_stress")
    assert len(y["components"]) == 4


def test_pending_build_credit_stress_axis_all_legs_absent() -> None:
    snap = _compose()
    y = _axis(snap, "credit_stress")
    assert y["value"] is None
    assert y["value_status"] == "ABSENT"
    assert y["null_reason"] == "COMPUTATION_REFUSED"
    assert y["components_available"] == 0
    for c in y["components"]:
        assert c["standardized_value"] is None
        assert c["coverage_state"] == "ABSENT"


def test_pending_build_cash_flow_axis_refused_missing_income_leg() -> None:
    snap = _compose()
    x = _axis(snap, "cash_flow_momentum")
    assert x["value"] is None
    assert x["null_reason"] == "COMPUTATION_REFUSED"
    retail_leg = _axis_component(x, "retail_sales_yoy_leg")
    assert retail_leg["standardized_value"] is not None  # retail IS present today
    income_leg = _axis_component(x, "real_disposable_income_yoy_leg")
    assert income_leg["standardized_value"] is None      # income is pending


def test_pending_build_remainder_metrics_typed() -> None:
    snap = _compose()
    m = _metric(snap, "payments_panel_card_network")
    assert m["value"] is None
    assert m["null_reason"] == "RIGHTS_BLOCKED"
    assert m["freshness"] == "RIGHTS_BLOCKED"
    assert m["rights_state"] == "RIGHTS_BLOCKED"
    n = _metric(snap, "household_debt_panel_nyfed_qhdc")
    assert n["value"] is None
    assert n["null_reason"] == "NOT_COVERED"
    assert n["freshness"] == "NOT_COVERED"
    assert n["rights_state"] == "OPEN"


# --------------------------------------------------------------------------- #
# retail sales: level + MoM + YoY (hand-computable)
# --------------------------------------------------------------------------- #
def test_retail_sales_level_mom_yoy() -> None:
    snap = _compose()
    level = _metric(snap, "retail_sales_level")
    assert level["value"] == pytest.approx(700000.0)
    assert level["unit"] == "usd_millions_sa"
    mom = _metric(snap, "retail_sales_mom")
    expected_mom = round((700000.0 / 680000.0 - 1.0) * 100.0, 4)
    assert mom["value"] == pytest.approx(expected_mom)
    yoy = _metric(snap, "retail_sales_yoy")
    expected_yoy = round((700000.0 / 660000.0 - 1.0) * 100.0, 4)
    assert yoy["value"] == pytest.approx(expected_yoy)


def test_retail_sales_mom_insufficient_history_when_only_latest_row() -> None:
    ff = _pending_fred_frames()
    ff[cp.SERIES_RETAIL_SALES] = [("2026-07-01", 700000.0)]
    snap = _compose(fred_frames=ff)
    mom = _metric(snap, "retail_sales_mom")
    assert mom["value"] is None
    assert mom["status"] == "ABSENT"
    assert mom["null_reason"] == "INSUFFICIENT_HISTORY"
    level = _metric(snap, "retail_sales_level")
    assert level["value"] == pytest.approx(700000.0)


def test_retail_sales_missing_is_source_failed_and_degrades_state() -> None:
    ff = _pending_fred_frames()
    ff[cp.SERIES_RETAIL_SALES] = None
    snap = _compose(fred_frames=ff)
    r = _required(snap, "retail_sales")
    assert r["freshness"] == "SOURCE_FAILED"
    assert r["status"] == "ABSENT"
    assert snap["availability"]["state"] == "SOURCE_FAILED"
    assert "retail_sales" in snap["availability"]["degraded"]


# --------------------------------------------------------------------------- #
# consumer sentiment: level + YoY
# --------------------------------------------------------------------------- #
def test_sentiment_level_and_yoy() -> None:
    snap = _compose()
    level = _metric(snap, "consumer_sentiment_level")
    assert level["value"] == pytest.approx(68.5)
    yoy = _metric(snap, "consumer_sentiment_yoy")
    expected = round((68.5 / 65.0 - 1.0) * 100.0, 4)
    assert yoy["value"] == pytest.approx(expected)
    assert yoy["status"] == "PRESENT"


def test_sentiment_yoy_insufficient_history_when_only_latest_row() -> None:
    ff = _pending_fred_frames()
    ff[cp.SERIES_SENTIMENT] = [("2026-08-01", 68.5)]
    snap = _compose(fred_frames=ff)
    yoy = _metric(snap, "consumer_sentiment_yoy")
    assert yoy["value"] is None
    assert yoy["null_reason"] == "INSUFFICIENT_HISTORY"


# --------------------------------------------------------------------------- #
# UMCSENT freshness cadence law (judgment call 1 -- the pinned proof)
# --------------------------------------------------------------------------- #
def test_umcsent_july_print_reads_late_not_current() -> None:
    """The exact hand-off scenario: a July UMCSENT print (age 65 on
    2026-09-04) must NOT read CURRENT -- the agency's August final should
    already exist upstream by then. Under the corrected 61d/15d cadence
    this reads LATE_WITHIN_TOLERANCE, honestly signalling the print is
    behind schedule rather than falsely asserting freshness."""
    ff = _pending_fred_frames()
    ff[cp.SERIES_SENTIMENT] = _sentiment_rows_late()
    snap = _compose(fred_frames=ff)
    r = _required(snap, "consumer_sentiment")
    assert r["freshness"] == "LATE_WITHIN_TOLERANCE"
    assert r["freshness"] != "CURRENT"
    assert snap["availability"]["state"] != "CURRENT"


def test_umcsent_cadence_boundary_unit() -> None:
    # Built via BUILT_DATE - timedelta(days=N) (never a hardcoded calendar
    # date) so the age is exact by construction -- no manual calendar
    # arithmetic to get wrong. cadence=61, grace=15: CURRENT through age 61,
    # LATE_WITHIN_TOLERANCE through age 76 (61+15), STALE_SOURCE from age 77.
    for age, expected in ((60, "CURRENT"), (61, "CURRENT"),
                          (62, "LATE_WITHIN_TOLERANCE"), (65, "LATE_WITHIN_TOLERANCE"),
                          (76, "LATE_WITHIN_TOLERANCE"), (77, "STALE_SOURCE")):
        asof = BUILT_DATE - dt.timedelta(days=age)
        got = cp._cadence_freshness(BUILT_AT, asof, cp._SENTIMENT_CADENCE_DAYS,
                                     cp._SENTIMENT_GRACE_DAYS, True)
        assert got == expected, (age, expected, got)


# --------------------------------------------------------------------------- #
# cadence / release-lag freshness law (unit-level, all five distinct pairs)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("age_days,cadence,grace,expected", [
    (0, 80, 17, "CURRENT"), (80, 80, 17, "CURRENT"), (81, 80, 17, "LATE_WITHIN_TOLERANCE"),
    (97, 80, 17, "LATE_WITHIN_TOLERANCE"), (98, 80, 17, "STALE_SOURCE"),
    (0, 61, 15, "CURRENT"), (61, 61, 15, "CURRENT"), (62, 61, 15, "LATE_WITHIN_TOLERANCE"),
    (76, 61, 15, "LATE_WITHIN_TOLERANCE"), (77, 61, 15, "STALE_SOURCE"),
    (0, 100, 15, "CURRENT"), (100, 100, 15, "CURRENT"), (101, 100, 15, "LATE_WITHIN_TOLERANCE"),
    (115, 100, 15, "LATE_WITHIN_TOLERANCE"), (116, 100, 15, "STALE_SOURCE"),
    (0, 92, 15, "CURRENT"), (92, 92, 15, "CURRENT"), (93, 92, 15, "LATE_WITHIN_TOLERANCE"),
    (107, 92, 15, "LATE_WITHIN_TOLERANCE"), (108, 92, 15, "STALE_SOURCE"),
    (0, 255, 30, "CURRENT"), (255, 255, 30, "CURRENT"), (256, 255, 30, "LATE_WITHIN_TOLERANCE"),
    (285, 255, 30, "LATE_WITHIN_TOLERANCE"), (286, 255, 30, "STALE_SOURCE"),
])
def test_cadence_freshness_tiers(age_days, cadence, grace, expected) -> None:
    asof = BUILT_DATE - dt.timedelta(days=age_days)
    got = cp._cadence_freshness(BUILT_AT, asof, cadence, grace, True)
    assert got == expected


def test_cadence_freshness_absent_value_is_source_failed() -> None:
    assert cp._cadence_freshness(BUILT_AT, BUILT_DATE, 80, 17, False) == "SOURCE_FAILED"


def test_cadence_freshness_future_asof_is_source_failed() -> None:
    future = BUILT_DATE + dt.timedelta(days=5)
    assert cp._cadence_freshness(BUILT_AT, future, 80, 17, True) == "SOURCE_FAILED"


# --------------------------------------------------------------------------- #
# consumer credit: total / revolving / nonrevolving, level + YoY, self-heal
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("series_key,metric_prefix,rows_fn,cid", [
    (cp.SERIES_CREDIT_TOTAL, "consumer_credit_total", _credit_total_rows, "consumer_credit_total"),
    (cp.SERIES_CREDIT_REVOLVING, "consumer_credit_revolving", _credit_revolving_rows, "consumer_credit_revolving"),
    (cp.SERIES_CREDIT_NONREVOLVING, "consumer_credit_nonrevolving", _credit_nonrevolving_rows, "consumer_credit_nonrevolving"),
])
def test_credit_leg_none_frame_is_source_failed(series_key, metric_prefix, rows_fn, cid) -> None:
    snap = _compose()  # pending fixture: all three credit legs are None
    level = _metric(snap, f"{metric_prefix}_level")
    assert level["value"] is None
    assert level["status"] == "ABSENT"
    assert level["null_reason"] == "SOURCE_FAILED"
    yoy = _metric(snap, f"{metric_prefix}_yoy")
    assert yoy["value"] is None
    assert yoy["null_reason"] == "SOURCE_FAILED"
    c = _required(snap, cid)
    assert c["status"] == "ABSENT"


@pytest.mark.parametrize("series_key,metric_prefix,rows_fn,level_a,level_b", [
    (cp.SERIES_CREDIT_TOTAL, "consumer_credit_total", _credit_total_rows, 4800.0, 4950.0),
    (cp.SERIES_CREDIT_REVOLVING, "consumer_credit_revolving", _credit_revolving_rows, 1250.0, 1300.0),
    (cp.SERIES_CREDIT_NONREVOLVING, "consumer_credit_nonrevolving", _credit_nonrevolving_rows, 3550.0, 3650.0),
])
def test_credit_leg_self_heals_when_populated(series_key, metric_prefix, rows_fn, level_a, level_b) -> None:
    ff = _pending_fred_frames()
    ff[series_key] = rows_fn()
    snap = _compose(fred_frames=ff)
    level = _metric(snap, f"{metric_prefix}_level")
    assert level["value"] == pytest.approx(level_b)
    assert level["unit"] == "usd_billions_sa"
    yoy = _metric(snap, f"{metric_prefix}_yoy")
    expected_yoy = round((level_b / level_a - 1.0) * 100.0, 4)
    assert yoy["value"] == pytest.approx(expected_yoy)
    assert yoy["status"] == "PRESENT"


# --------------------------------------------------------------------------- #
# personal saving rate: level + 3-month change, self-heal
# --------------------------------------------------------------------------- #
def test_saving_rate_absent_by_default() -> None:
    snap = _compose()
    level = _metric(snap, "personal_saving_rate_level")
    assert level["value"] is None
    assert level["null_reason"] == "SOURCE_FAILED"
    change = _metric(snap, "personal_saving_rate_change_3m")
    assert change["value"] is None
    assert change["null_reason"] == "SOURCE_FAILED"


def test_saving_rate_self_heals_level_and_3m_change() -> None:
    ff = _pending_fred_frames()
    ff[cp.SERIES_SAVING_RATE] = _saving_rate_rows_falling()
    snap = _compose(fred_frames=ff)
    level = _metric(snap, "personal_saving_rate_level")
    assert level["value"] == pytest.approx(4.0)
    change = _metric(snap, "personal_saving_rate_change_3m")
    assert change["value"] == pytest.approx(4.0 - 4.5)  # = -0.5
    assert change["status"] == "PRESENT"


def test_saving_rate_change_3m_insufficient_history_single_row() -> None:
    ff = _pending_fred_frames()
    ff[cp.SERIES_SAVING_RATE] = [("2026-07-01", 4.0)]
    snap = _compose(fred_frames=ff)
    change = _metric(snap, "personal_saving_rate_change_3m")
    assert change["value"] is None
    assert change["null_reason"] == "INSUFFICIENT_HISTORY"
    level = _metric(snap, "personal_saving_rate_level")
    assert level["value"] == pytest.approx(4.0)


# --------------------------------------------------------------------------- #
# real disposable income: level + YoY, self-heal
# --------------------------------------------------------------------------- #
def test_real_disposable_income_absent_by_default() -> None:
    snap = _compose()
    level = _metric(snap, "real_disposable_income_level")
    assert level["value"] is None
    assert level["null_reason"] == "SOURCE_FAILED"


def test_real_disposable_income_self_heals() -> None:
    ff = _pending_fred_frames()
    ff[cp.SERIES_REAL_DISPOSABLE_INCOME] = _real_income_rows()
    snap = _compose(fred_frames=ff)
    level = _metric(snap, "real_disposable_income_level")
    assert level["value"] == pytest.approx(17400.0)
    assert level["unit"] == "usd_billions_chained_saar"
    yoy = _metric(snap, "real_disposable_income_yoy")
    expected = round((17400.0 / 17000.0 - 1.0) * 100.0, 4)
    assert yoy["value"] == pytest.approx(expected)


# --------------------------------------------------------------------------- #
# delinquency: cc + mortgage, quarterly, level only, self-heal
# --------------------------------------------------------------------------- #
def test_delinquency_absent_by_default() -> None:
    snap = _compose()
    for mid in ("cc_delinquency_rate_level", "mortgage_delinquency_rate_level"):
        m = _metric(snap, mid)
        assert m["value"] is None
        assert m["null_reason"] == "SOURCE_FAILED"


def test_delinquency_self_heals() -> None:
    ff = _pending_fred_frames()
    ff[cp.SERIES_CC_DELINQUENCY] = _cc_delinquency_rows()
    ff[cp.SERIES_MORTGAGE_DELINQUENCY] = _mortgage_delinquency_rows()
    snap = _compose(fred_frames=ff)
    cc = _metric(snap, "cc_delinquency_rate_level")
    assert cc["value"] == pytest.approx(3.2)
    mtg = _metric(snap, "mortgage_delinquency_rate_level")
    assert mtg["value"] == pytest.approx(1.8)
    for m in (cc, mtg):
        assert m["freshness"] == "CURRENT"


def test_delinquency_never_cites_a_seasonal_adjustment() -> None:
    snap = _compose()
    for mid in ("cc_delinquency_rate_level", "mortgage_delinquency_rate_level"):
        m = _metric(snap, mid)
        assert "NOT seasonally adjusted" in m["transformation"]


# --------------------------------------------------------------------------- #
# malformed / None-row robustness
# --------------------------------------------------------------------------- #
def test_malformed_and_none_rows_are_dropped_never_fabricated() -> None:
    ff = _pending_fred_frames()
    ff[cp.SERIES_RETAIL_SALES] = [
        None, ("bad-date", 700000.0), ("2026-07-01", "not-a-number"),
        ("2026-06-01", 680000.0), ("2026-07-01", 700000.0),
    ]
    snap = _compose(fred_frames=ff)
    level = _metric(snap, "retail_sales_level")
    assert level["value"] == pytest.approx(700000.0)


def test_rows_supplied_as_lists_not_tuples_work_identically() -> None:
    ff = _pending_fred_frames()
    ff[cp.SERIES_RETAIL_SALES] = [["2026-06-01", 680000.0], ["2026-07-01", 700000.0]]
    snap = _compose(fred_frames=ff)
    level = _metric(snap, "retail_sales_level")
    assert level["value"] == pytest.approx(700000.0)


def test_all_nine_series_missing_still_typed_never_crashes() -> None:
    snap = cp.compose({}, built_at=BUILT_AT)
    assert snap["availability"]["state"] == "SOURCE_FAILED"
    assert snap["availability"]["coverage_ratio"] == 0.0
    for cid in ("retail_sales", "consumer_sentiment"):
        r = _required(snap, cid)
        assert r["status"] == "ABSENT"


def test_none_fred_frames_argument_never_crashes() -> None:
    snap = cp.compose(None, built_at=BUILT_AT)
    assert snap["availability"]["state"] == "SOURCE_FAILED"


# --------------------------------------------------------------------------- #
# unit / scale trap: RSAFS ($M) never mixed with G.19/DSPIC96 ($bn)
# --------------------------------------------------------------------------- #
def test_retail_sales_unit_is_millions_never_billions() -> None:
    snap = _compose()
    level = _metric(snap, "retail_sales_level")
    assert level["unit"] == "usd_millions_sa"
    assert level["unit"] != "usd_billions_sa"


def test_credit_and_income_units_are_billions() -> None:
    ff = _populated_fred_frames()
    snap = _compose(fred_frames=ff)
    for mid in ("consumer_credit_total_level", "consumer_credit_revolving_level",
                "consumer_credit_nonrevolving_level"):
        assert _metric(snap, mid)["unit"] == "usd_billions_sa"
    assert _metric(snap, "real_disposable_income_level")["unit"] == "usd_billions_chained_saar"


def test_no_metric_id_mixes_retail_sales_with_credit_series() -> None:
    snap = _compose()
    ids = {m["metric_id"] for m in snap["metrics"]["items"]}
    assert not any("retail_sales" in mid and "credit" in mid for mid in ids)


# --------------------------------------------------------------------------- #
# three-leg contradiction: fires / silent / flat-band-guarded / leg-absent
# --------------------------------------------------------------------------- #
def test_contradiction_fires_when_all_three_legs_diverge() -> None:
    ff = _populated_fred_frames()  # sentiment rising, revolving +4% YoY, saving -0.5pp
    snap = _compose(fred_frames=ff)
    c = snap["availability"]["contradiction"]
    assert c["present"] is True
    assert c["kind"] == "spending_on_credit_vs_confidence_divergence"
    assert set(c["components"]) == {
        "consumer_sentiment_yoy", "consumer_credit_revolving_yoy", "personal_saving_rate_change_3m",
    }
    sentiment_m = _metric(snap, "consumer_sentiment_yoy")
    assert sentiment_m["status"] == "DISAGREEMENT"
    assert sentiment_m["value"] is not None  # typed disagreement, never censored
    revolving_m = _metric(snap, "consumer_credit_revolving_yoy")
    assert revolving_m["status"] == "DISAGREEMENT"
    saving_m = _metric(snap, "personal_saving_rate_change_3m")
    assert saving_m["status"] == "DISAGREEMENT"
    assert _implication(snap, "contradiction_spending_on_credit_vs_confidence_divergence") is not None


def test_contradiction_silent_when_saving_rate_flat() -> None:
    ff = _populated_fred_frames()
    ff[cp.SERIES_SAVING_RATE] = _saving_rate_rows_flat()  # inside flat band
    snap = _compose(fred_frames=ff)
    assert snap["availability"]["contradiction"]["present"] is False


def test_contradiction_silent_when_revolving_credit_flat() -> None:
    ff = _populated_fred_frames()
    ff[cp.SERIES_CREDIT_REVOLVING] = _credit_revolving_rows_flat()
    snap = _compose(fred_frames=ff)
    assert snap["availability"]["contradiction"]["present"] is False


def test_contradiction_silent_when_revolving_credit_absent() -> None:
    ff = _populated_fred_frames()
    ff[cp.SERIES_CREDIT_REVOLVING] = None
    snap = _compose(fred_frames=ff)
    assert snap["availability"]["contradiction"]["present"] is False


def test_contradiction_silent_on_pending_build() -> None:
    # today's real first build: revolving credit and saving rate are both
    # None, so the contradiction can never fire regardless of sentiment.
    snap = _compose()
    assert snap["availability"]["contradiction"]["present"] is False


def test_contradiction_never_includes_real_disposable_income() -> None:
    # judgment call 12: scoped to exactly the three named legs.
    ff = _populated_fred_frames()
    snap = _compose(fred_frames=ff)
    c = snap["availability"]["contradiction"]
    if c["present"]:
        assert "real_disposable_income_yoy" not in c["components"]


def test_contradiction_never_flips_credit_stress_axis_status() -> None:
    # judgment call 16: DISAGREEMENT is scoped to the three metrics, never
    # propagated into the credit_stress axis's own value_status.
    ff = _populated_fred_frames()
    snap = _compose(fred_frames=ff)
    assert snap["availability"]["contradiction"]["present"] is True
    y = _axis(snap, "credit_stress")
    assert y["value_status"] in ("PRESENT", "PARTIAL")


# --------------------------------------------------------------------------- #
# headline: fully computable path (all nine series populated)
# --------------------------------------------------------------------------- #
def test_headline_computable_when_fully_populated() -> None:
    ff = _populated_fred_frames()
    snap = _compose(fred_frames=ff)
    h = snap["headline"]
    assert h["state_id"] in ("A", "B", "C", "D")
    assert h["status"] == "PRESENT"
    assert h["null_reason"] is None
    assert h["quadrant"]["x"] is not None
    assert h["quadrant"]["y"] is not None
    x = _axis(snap, "cash_flow_momentum")
    assert x["value_status"] == "PRESENT"
    y = _axis(snap, "credit_stress")
    assert y["value_status"] == "PRESENT"
    assert y["components_available"] == 4


def test_headline_quadrant_matches_classify_helper() -> None:
    ff = _populated_fred_frames()
    snap = _compose(fred_frames=ff)
    h = snap["headline"]
    assert h["state_id"] == cp._classify(h["quadrant"]["x"], h["quadrant"]["y"])


def test_headline_x_value_replicates_axis_component_formula() -> None:
    ff = _populated_fred_frames()
    snap = _compose(fred_frames=ff)
    retail_yoy = round((700000.0 / 660000.0 - 1.0) * 100.0, 4)
    income_yoy = round((17400.0 / 17000.0 - 1.0) * 100.0, 4)
    retail_std = round(cp._yoy_scale_to_100(retail_yoy, cp._RETAIL_YOY_SCALE), 2)
    income_std = round(cp._yoy_scale_to_100(income_yoy, cp._INCOME_YOY_SCALE), 2)
    expected_x = round(
        cp._clamp((retail_std * cp._X_WEIGHT_RETAIL_YOY + income_std * cp._X_WEIGHT_INCOME_YOY)
                  / (cp._X_WEIGHT_RETAIL_YOY + cp._X_WEIGHT_INCOME_YOY), 0.0, 100.0), 2)
    h = snap["headline"]
    assert h["quadrant"]["x"] == pytest.approx(expected_x, abs=0.01)


def test_headline_y_axis_saving_rate_leg_has_negative_sign() -> None:
    # judgment call 9: the first sign=-1 axis component in this estate.
    ff = _populated_fred_frames()
    snap = _compose(fred_frames=ff)
    y = _axis(snap, "credit_stress")
    saving_leg = _axis_component(y, "saving_rate_level_leg")
    assert saving_leg["sign"] == -1
    for cid in ("revolving_credit_yoy_leg", "cc_delinquency_level_leg", "mortgage_delinquency_level_leg"):
        assert _axis_component(y, cid)["sign"] == 1


def test_headline_higher_saving_rate_lowers_credit_stress() -> None:
    ff = _populated_fred_frames()
    ff[cp.SERIES_SAVING_RATE] = [("2026-04-01", 4.0), ("2026-07-01", 12.0)]  # very high saving rate
    snap_high_saving = _compose(fred_frames=ff)
    ff2 = _populated_fred_frames()
    ff2[cp.SERIES_SAVING_RATE] = [("2026-04-01", 4.0), ("2026-07-01", 0.5)]  # very low saving rate
    snap_low_saving = _compose(fred_frames=ff2)
    y_high = _axis(snap_high_saving, "credit_stress")["value"]
    y_low = _axis(snap_low_saving, "credit_stress")["value"]
    assert y_high < y_low


# --------------------------------------------------------------------------- #
# axis leg-floor laws
# --------------------------------------------------------------------------- #
def test_x_axis_refused_when_only_retail_leg_present() -> None:
    ff = _pending_fred_frames()  # real_disposable_income stays None
    snap = _compose(fred_frames=ff)
    x = _axis(snap, "cash_flow_momentum")
    assert x["value"] is None
    assert x["null_reason"] == "COMPUTATION_REFUSED"
    assert x["components_available"] == 1


def test_x_axis_refused_when_only_income_leg_present() -> None:
    ff = _pending_fred_frames()
    ff[cp.SERIES_RETAIL_SALES] = None
    ff[cp.SERIES_REAL_DISPOSABLE_INCOME] = _real_income_rows()
    snap = _compose(fred_frames=ff)
    x = _axis(snap, "cash_flow_momentum")
    assert x["value"] is None
    assert x["components_available"] == 1


def test_x_axis_computable_when_both_legs_present() -> None:
    ff = _pending_fred_frames()
    ff[cp.SERIES_REAL_DISPOSABLE_INCOME] = _real_income_rows()
    snap = _compose(fred_frames=ff)
    x = _axis(snap, "cash_flow_momentum")
    assert x["value"] is not None
    assert x["value_status"] == "PRESENT"
    assert x["components_available"] == 2


@pytest.mark.parametrize("present_series", [
    [cp.SERIES_CREDIT_REVOLVING],
    [cp.SERIES_SAVING_RATE],
    [cp.SERIES_CC_DELINQUENCY],
    [cp.SERIES_MORTGAGE_DELINQUENCY],
])
def test_y_axis_refused_with_only_one_leg(present_series) -> None:
    ff = _pending_fred_frames()
    fixture_map = {
        cp.SERIES_CREDIT_REVOLVING: _credit_revolving_rows(),
        cp.SERIES_SAVING_RATE: _saving_rate_rows_falling(),
        cp.SERIES_CC_DELINQUENCY: _cc_delinquency_rows(),
        cp.SERIES_MORTGAGE_DELINQUENCY: _mortgage_delinquency_rows(),
    }
    for s in present_series:
        ff[s] = fixture_map[s]
    snap = _compose(fred_frames=ff)
    y = _axis(snap, "credit_stress")
    assert y["value"] is None
    assert y["null_reason"] == "COMPUTATION_REFUSED"
    assert y["components_available"] == 1


def test_y_axis_computable_with_two_legs_at_coverage_floor() -> None:
    ff = _pending_fred_frames()
    ff[cp.SERIES_CREDIT_REVOLVING] = _credit_revolving_rows()
    ff[cp.SERIES_SAVING_RATE] = _saving_rate_rows_falling()
    snap = _compose(fred_frames=ff)
    y = _axis(snap, "credit_stress")
    assert y["value"] is not None
    assert y["value_status"] == "PARTIAL"  # 2 of 4 present
    assert y["components_available"] == 2


def test_y_axis_partial_still_computes_weighted_average() -> None:
    ff = _pending_fred_frames()
    ff[cp.SERIES_CREDIT_REVOLVING] = _credit_revolving_rows()
    ff[cp.SERIES_SAVING_RATE] = _saving_rate_rows_falling()
    snap = _compose(fred_frames=ff)
    y = _axis(snap, "credit_stress")
    rev_std = _axis_component(y, "revolving_credit_yoy_leg")["standardized_value"]
    sav_std = _axis_component(y, "saving_rate_level_leg")["standardized_value"]
    expected = round((rev_std * cp._Y_WEIGHT_REVOLVING_YOY + sav_std * cp._Y_WEIGHT_SAVING_RATE)
                      / (cp._Y_WEIGHT_REVOLVING_YOY + cp._Y_WEIGHT_SAVING_RATE), 2)
    assert y["value"] == pytest.approx(expected, abs=0.01)


# --------------------------------------------------------------------------- #
# typed-ABSENT remainder: rights-blocked / not-covered
# --------------------------------------------------------------------------- #
def test_payments_panel_rights_blocked_cites_the_compliance_doc() -> None:
    snap = _compose()
    m = _metric(snap, "payments_panel_card_network")
    assert "QUAL_DATA_COMPLIANCE.md" in m["transformation"]
    assert "2.3" in m["transformation"]
    src = next(s for s in snap["sources"]["items"] if s["source_id"] == "payments_panel_card_network")
    assert src["rights_state"] == "RIGHTS_BLOCKED"
    assert src["freshness"] == "RIGHTS_BLOCKED"


def test_household_debt_not_covered_never_rights_blocked() -> None:
    snap = _compose()
    m = _metric(snap, "household_debt_panel_nyfed_qhdc")
    assert m["null_reason"] == "NOT_COVERED"
    assert m["rights_state"] == "OPEN"
    assert "collector" in m["transformation"]
    src = next(s for s in snap["sources"]["items"] if s["source_id"] == "household_debt_nyfed_qhdc")
    assert src["rights_state"] == "OPEN"
    assert src["freshness"] == "NOT_COVERED"


def test_remainder_metrics_never_fabricate_a_value() -> None:
    snap = _compose()
    for mid in ("payments_panel_card_network", "household_debt_panel_nyfed_qhdc"):
        m = _metric(snap, mid)
        assert m["value"] is None
        assert m["status"] == "ABSENT"


# --------------------------------------------------------------------------- #
# metric inventory + digest determinism
# --------------------------------------------------------------------------- #
def test_metric_ids_are_unique_and_stable_count() -> None:
    snap = _compose()
    ids = [m["metric_id"] for m in snap["metrics"]["items"]]
    assert len(ids) == len(set(ids))
    assert len(ids) == 21


def test_digest_is_deterministic_across_identical_input() -> None:
    snap1 = contract.finalize(_compose())
    snap2 = contract.finalize(_compose())
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


def test_digest_changes_when_consumed_retail_field_changes() -> None:
    snap1 = contract.finalize(_compose())
    ff2 = _pending_fred_frames()
    ff2[cp.SERIES_RETAIL_SALES] = [("2025-07-01", 660000.0), ("2026-06-01", 680000.0), ("2026-07-01", 999999.0)]
    snap2 = contract.finalize(_compose(fred_frames=ff2))
    assert snap1["generation"]["content_sha256"] != snap2["generation"]["content_sha256"]


def test_digest_changes_when_pending_series_populates() -> None:
    snap1 = contract.finalize(_compose())
    snap2 = contract.finalize(_compose(fred_frames=_populated_fred_frames()))
    assert snap1["generation"]["content_sha256"] != snap2["generation"]["content_sha256"]


def test_digest_unaffected_by_unconsumed_fred_frames_key() -> None:
    snap1 = contract.finalize(_compose())
    ff3 = _pending_fred_frames()
    ff3["DGS10"] = [("2026-09-03", 4.2)]  # never read by this composer
    snap3 = contract.finalize(_compose(fred_frames=ff3))
    assert snap1["generation"]["content_sha256"] == snap3["generation"]["content_sha256"]


def test_digest_unaffected_by_unconsumed_row_tuple_element() -> None:
    snap1 = contract.finalize(_compose())
    ff4 = _pending_fred_frames()
    ff4[cp.SERIES_RETAIL_SALES] = [
        ("2025-07-01", 660000.0, "unrelated-extra-field"),
        ("2026-06-01", 680000.0, {"nested": "also unrelated"}),
        ("2026-07-01", 700000.0, None),
    ]
    snap4 = contract.finalize(_compose(fred_frames=ff4))
    assert snap1["generation"]["content_sha256"] == snap4["generation"]["content_sha256"]


# --------------------------------------------------------------------------- #
# changes / method-version comparability
# --------------------------------------------------------------------------- #
def _prior(method=cp.METHOD_VERSION, retail_level=700000.0,
           gen="consumer_payments-US-deadbeefdeadbeef") -> dict:
    prior = _compose()
    prior["headline"]["method_version"] = method
    prior["generation"]["generation_id"] = gen
    for m in prior["metrics"]["items"]:
        if m["metric_id"] == "retail_sales_level":
            m["value"] = retail_level
    return prior


def test_changes_no_prior_yields_warmup() -> None:
    snap = _compose()
    assert snap["changes"]["comparability"] == "NO_PRIOR"
    assert snap["changes"]["null_reason"] == "WARMUP"


def test_changes_method_mismatch_refuses_numeric_comparison() -> None:
    snap = _compose(prior_snapshot=_prior(method="consumer_payments.compose.v0"))
    assert snap["changes"]["comparability"] == "METHOD_CHANGED"
    assert snap["changes"]["deltas"] == []
    assert snap["changes"]["null_reason"] == "COMPUTATION_REFUSED"


def test_changes_comparable_prior_produces_deltas() -> None:
    snap = _compose(prior_snapshot=_prior(retail_level=650000.0))
    assert snap["changes"]["comparability"] == "COMPARABLE"
    ids = {d["metric_id"] for d in snap["changes"]["deltas"]}
    assert ids == set(cp._TRACKED_CHANGE_METRICS)
    delta = next(d for d in snap["changes"]["deltas"] if d["metric_id"] == "retail_sales_level")
    assert delta["prior_value"] == 650000.0
    assert delta["current_value"] == pytest.approx(700000.0)
    assert delta["delta"] == pytest.approx(50000.0)


# --------------------------------------------------------------------------- #
# corrections / supersession honesty
# --------------------------------------------------------------------------- #
def test_corrections_none_for_first_print() -> None:
    snap = _compose()
    assert snap["corrections"]["correction_state"] == "none"
    assert snap["corrections"]["predecessor_generation_id"] is None


def test_corrections_superseded_when_same_period_value_changes() -> None:
    ff = _pending_fred_frames()
    prior_snap = contract.finalize(cp.compose(ff, built_at=BUILT_AT))
    ff2 = copy.deepcopy(ff)
    ff2[cp.SERIES_RETAIL_SALES] = [("2025-07-01", 660000.0), ("2026-06-01", 680000.0), ("2026-07-01", 725000.0)]
    snap2 = cp.compose(ff2, built_at=BUILT_AT, prior_snapshot=prior_snap)
    assert snap2["corrections"]["correction_state"] == "superseded"
    assert snap2["corrections"]["changed_fingerprints"]
    assert snap2["corrections"]["predecessor_generation_id"] == prior_snap["generation"]["generation_id"]


def test_corrections_none_when_reference_period_advances() -> None:
    ff = _pending_fred_frames()
    prior_snap = contract.finalize(cp.compose(ff, built_at=BUILT_AT))
    ff2 = copy.deepcopy(ff)
    ff2[cp.SERIES_SENTIMENT] = ff2[cp.SERIES_SENTIMENT] + [("2026-09-01", 69.0)]  # new observation
    snap2 = cp.compose(ff2, built_at="2026-09-11T00:00:00Z", prior_snapshot=prior_snap)
    assert snap2["corrections"]["correction_state"] == "none"


def test_corrections_no_change_republication_wording() -> None:
    ff = _pending_fred_frames()
    prior_snap = contract.finalize(cp.compose(ff, built_at=BUILT_AT))
    snap2 = cp.compose(ff, built_at=BUILT_AT, prior_snapshot=prior_snap)
    assert snap2["corrections"]["correction_state"] == "none"
    assert "no-change republication" in snap2["corrections"]["note"]


# --------------------------------------------------------------------------- #
# schema validation
# --------------------------------------------------------------------------- #
def test_pending_build_validates_against_the_closed_contract() -> None:
    snap = contract.finalize(_compose())
    contract.validate(snap)  # raises ContractError on any violation
    assert snap["authority"]["can_size"] is False
    assert snap["authority"]["can_execute"] is False
    assert snap["authority"]["can_originate_signal"] is False


def test_fully_populated_headline_computed_snapshot_validates() -> None:
    snap = contract.finalize(cp.compose(_populated_fred_frames(), built_at=BUILT_AT))
    contract.validate(snap)


def test_all_nine_series_missing_still_validates() -> None:
    snap = contract.finalize(cp.compose({}, built_at=BUILT_AT))
    contract.validate(snap)
    assert snap["availability"]["state"] == "SOURCE_FAILED"


def test_degraded_single_leg_missing_still_validates() -> None:
    ff = _populated_fred_frames()
    ff[cp.SERIES_CC_DELINQUENCY] = None
    snap = contract.finalize(cp.compose(ff, built_at=BUILT_AT))
    contract.validate(snap)


def test_contradiction_fired_snapshot_validates() -> None:
    snap = contract.finalize(cp.compose(_populated_fred_frames(), built_at=BUILT_AT))
    contract.validate(snap)
    assert snap["availability"]["contradiction"]["present"] is True


# --------------------------------------------------------------------------- #
# disclosure implications present
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("iid", [
    "no_alfred_pit_vintage_capture", "payments_rights_blocked_disclosure",
    "household_debt_not_covered_disclosure", "driver_bucket_naming_note",
])
def test_disclosure_implications_present_on_pending_build(iid) -> None:
    snap = _compose()
    assert _implication(snap, iid) is not None


def test_headline_unavailable_implication_on_pending_build() -> None:
    snap = _compose()
    assert _implication(snap, "headline_unavailable") is not None
    assert _implication(snap, "headline_computed") is None


def test_headline_computed_implication_on_fully_populated_build() -> None:
    snap = _compose(fred_frames=_populated_fred_frames())
    assert _implication(snap, "headline_computed") is not None
    assert _implication(snap, "headline_unavailable") is None


def test_driver_bucket_reuse_disclosed_in_drivers_and_implication() -> None:
    snap = _compose()
    rate_side_ids = {d["driver_id"] for d in snap["drivers"]["rate_side"]}
    assert "retail_sales_yoy" in rate_side_ids
    balance_sheet_ids = {d["driver_id"] for d in snap["drivers"]["balance_sheet"]}
    assert "consumer_credit_revolving_yoy" in balance_sheet_ids
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


def test_prose_fields_contain_no_raw_enum_tokens_pending_build() -> None:
    snap = _compose()
    leaks = _find_raw_token_leaks(snap)
    assert leaks == [], f"raw enum tokens leaked into prose field(s): {leaks}"


def test_prose_fields_contain_no_raw_enum_tokens_populated_build() -> None:
    # exercise every disclosure branch at once: contradiction fired, headline
    # computed, the typed-absent remainder always present.
    snap = _compose(fred_frames=_populated_fred_frames())
    leaks = _find_raw_token_leaks(snap)
    assert leaks == [], f"raw enum tokens leaked into prose field(s): {leaks}"


# --------------------------------------------------------------------------- #
# zh-label integrity: composer-authored English phrasing must never leak into
# the composer-authored zh sibling
# --------------------------------------------------------------------------- #
_COMPOSER_ENGLISH_PHRASES = (
    "the composable-core", "This composer", "never combines it with",
    "leg-floor law", "cosmetic bucket reuse", "rights-adjacent",
    "point-in-time vintage capture", "credit-financed",
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
    snap = _compose(fred_frames=_populated_fred_frames())
    leaks = _find_english_leaks(snap)
    assert leaks == [], f"English phrasing leaked into zh field(s): {leaks}"


def test_zh_narrative_present_wherever_english_is_composer_authored() -> None:
    snap = _compose(fred_frames=_populated_fred_frames())
    for impl in snap["implications"]["items"]:
        assert impl["text"]["en"], impl
        assert impl["text"]["zh"], impl
    assert snap["workspace"]["title"]["zh"]
    assert snap["headline"]["subtitle"]["zh"]
    for axis in snap["axes"]["items"]:
        assert axis["label"]["zh"]
        for comp in axis["components"]:
            assert comp["label"]["zh"]


# --------------------------------------------------------------------------- #
# availability worst-of law
# --------------------------------------------------------------------------- #
def test_availability_worst_of_required_only_never_optional() -> None:
    # required = retail_sales + consumer_sentiment only; a missing OPTIONAL
    # leg (e.g. saving rate) must never appear in `degraded`.
    snap = _compose()
    assert "personal_saving_rate" not in snap["availability"]["degraded"]
    assert "cc_delinquency" not in snap["availability"]["degraded"]


def test_availability_state_degrades_when_required_leg_late() -> None:
    ff = _pending_fred_frames()
    ff[cp.SERIES_SENTIMENT] = _sentiment_rows_late()
    snap = _compose(fred_frames=ff)
    assert snap["availability"]["state"] == "LATE_WITHIN_TOLERANCE"
    assert "consumer_sentiment" in snap["availability"]["degraded"]


def test_coverage_ratio_reflects_required_set_only() -> None:
    snap = _compose()
    # both required components present -> coverage 1.0 regardless of the
    # seven absent optional legs.
    assert snap["availability"]["coverage_ratio"] == 1.0


# --------------------------------------------------------------------------- #
# registry / workspace identity sanity (no cross-import, no shadowing of the
# unrelated consumer.py machine-consumer reader module)
# --------------------------------------------------------------------------- #
def test_workspace_id_matches_registry_vocabulary() -> None:
    snap = _compose()
    assert snap["workspace"]["id"] == "consumer_payments"
    assert snap["schema"]["contract"] == "mastermind.macro_workspace_snapshot.v1"


def test_module_is_not_the_machine_consumer_reader() -> None:
    # sanity: this module's own name/id must never collide with the
    # unrelated engine.market_os.macro_workspaces.consumer reader module.
    assert cp.__name__.endswith("consumer_payments")
    assert cp.WORKSPACE_ID == "consumer_payments"
