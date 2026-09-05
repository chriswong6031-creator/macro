"""Composer tests for the US ``rates_curves`` workspace (beyond-F01 expansion,
Chairman-authorized 2026-09-04 -- the first workspace past the frozen
twelve-workspace Market Ontology architecture set).

RED-first: each degraded condition must produce the correct TYPED state and
never a zero / neutral / calm default. Covers: the NOT_APPLICABLE headline
shape (a design absence one level removed even from monetary_policy.py's own
design-absence case, since no architecture section for this workspace exists
at all -- see rates_curves.py's module docstring), the daily CMT/corridor
5d/4d cadence law + the THREEFYTP10 9d/5d law, hand-computable 13-week
changes on 2y/10y/30y/term-premium, the SAME-DATE DISCIPLINE this composer
introduces (leg-floor refusal, no-common-date refusal, staleness-bound
refusal, and the exact-boundary accept/reject pair) across all eight
two-/three-leg combinations (2s10s, 3m10y, 5s30s, the butterfly, the
nominal/real/breakeven decomposition, and the three corridor spreads), the
inversion run-length walk (a real multi-day fixture, the insufficient-history
floor independent of a known current sign, and failure-inheritance from the
base spread refusal), the decomposition-residual contradiction (on / off /
exact tolerance boundary), the required/optional split (fourteen required,
five optional -- verified never load-bearing for a derived metric), digest
determinism with genuinely-consumed-field mutations and unconsumed-field
negative controls, a prose scan for raw enum-token leaks, zh-narrative
integrity, and schema validation.

SCHEMA DEPENDENCY (disclosed, verified during authoring, not worked around
here): the closed contract schema's ``$defs.workspaceId`` enum in
``contracts/market_os/macro_workspace_snapshot.v1.schema.json`` was checked
directly against the committed file at authoring time and DOES already
include ``"rates_curves"`` -- widened in the same 2026-09-04 expansion as
``engine.market_os.macro_workspaces.registry.WORKSPACE_IDS``. (An earlier
read, at the very start of this authoring session, found the enum not yet
widened; a later re-check of the same file found it widened, since this is a
live, shared worktree. The stale "not yet widened" premise this docstring
originally carried is corrected here rather than left standing.) The
``test_*_validates_against_the_closed_contract`` tests below are therefore
expected to pass their schema step on the ``workspaceId`` front specifically.
They were never executed end-to-end by this authoring session (no Bash/
pytest access was available to the composer agent or to a delegated
sub-agent asked to run them) -- only hand-traced against ``contract.py``'s
own validate/finalize logic and the schema's other closed vocabularies
(status, null_reason, freshness). Whether they pass in full is therefore
disclosed as unverified-by-execution, not asserted.

    python3 -m pytest tests/test_macro_workspace_rates_curves.py -x -q
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

from engine.market_os.macro_workspaces import contract, rates_curves  # noqa: E402

BUILT_AT = "2026-09-04T00:00:00Z"
BUILT_DATE = dt.date(2026, 9, 4)

RC = rates_curves


# --------------------------------------------------------------------------- #
# fixture helpers (small, hand-computable -- see the inline arithmetic notes
# next to every derived-value assertion below)
# --------------------------------------------------------------------------- #
# Hand-verified date arithmetic (reused across fixtures):
#   2026-06-03 is EXACTLY 91 days before 2026-09-02 (Jun3->Jun30=27d,
#   +Jul(31)+Aug(31)+Sep(2)=91d total) -- the 13w-change lookback finds it at
#   zero slack for every daily-cadence series.
#   2026-05-29 is EXACTLY 91 days before 2026-08-28 (May29->May31=2d,
#   +Jun(30)+Jul(31)+Aug(28)=91d total) -- used for THREEFYTP10's own anchor.
#   2026-08-28 is age 7 days on 2026-09-04 (Aug28->29,30,31,Sep1,2,3,4 = 7d),
#   which MUST read CURRENT under the 9d/5d term-premium cadence (7<=9).
#   2026-09-02 is age 2 days on 2026-09-04, which MUST read CURRENT under the
#   5d/4d daily cadence (2<=5).
def _pt(new_val: float, old_val: float | None = None,
        new_date: str = "2026-09-02", old_date: str = "2026-06-03") -> list[tuple[str, float]]:
    if old_val is None:
        return [(new_date, new_val)]
    return [(old_date, old_val), (new_date, new_val)]


def _baseline_frames() -> dict:
    return {
        RC.SERIES_US3M: _pt(4.90),
        RC.SERIES_US6M: _pt(4.70),
        RC.SERIES_US1Y: _pt(4.40),
        RC.SERIES_US2Y: _pt(3.80, 4.10),
        RC.SERIES_US3Y: _pt(3.70),
        RC.SERIES_US5Y: _pt(3.90),
        RC.SERIES_US7Y: _pt(4.00),
        RC.SERIES_US10Y: _pt(4.10, 4.00),
        RC.SERIES_US20Y: _pt(4.50),
        RC.SERIES_US30Y: _pt(4.30, 4.40),
        RC.SERIES_US5Y_REAL: _pt(1.80),
        RC.SERIES_US10Y_REAL: _pt(1.90),
        RC.SERIES_BREAKEVEN_10Y: _pt(2.20),
        RC.SERIES_BREAKEVEN_5Y5Y: _pt(2.30),
        RC.SERIES_TERM_PREMIUM_10Y: _pt(0.45, 0.30, new_date="2026-08-28", old_date="2026-05-29"),
        RC.SERIES_EFFR: _pt(4.33),
        RC.SERIES_OBFR: _pt(4.32),
        RC.SERIES_SOFR: _pt(4.35),
        RC.SERIES_IORB: _pt(4.40),
    }
    # Hand-verified derived values from this exact fixture (used throughout):
    #   us2y_change_13w  = 3.80 - 4.10 = -0.30
    #   us10y_change_13w = 4.10 - 4.00 = +0.10
    #   us30y_change_13w = 4.30 - 4.40 = -0.10
    #   term_premium_10y_change_13w = 0.45 - 0.30 = +0.15
    #   curve_2s10s_level = 4.10 - 3.80 = +0.30 (normal)
    #   curve_3m10y_level = 4.10 - 4.90 = -0.80 (inverted)
    #   curve_5s30s_level = 4.30 - 3.90 = +0.40 (normal)
    #   curvature_butterfly_2s5s10s = 2*3.90 - 3.80 - 4.10 = -0.10
    #   nominal_real_breakeven_residual_10y = 4.10 - (1.90 + 2.20) = 0.00
    #   corridor_effr_minus_iorb_bp = (4.33 - 4.40) * 100 = -7.0
    #   corridor_sofr_minus_effr_bp = (4.35 - 4.33) * 100 = +2.0
    #   corridor_sofr_minus_iorb_bp = (4.35 - 4.40) * 100 = -5.0
    # (Both 2s10s and 3m10y run-lengths refuse INSUFFICIENT_HISTORY on this
    # fixture: only 2 shared-date rows exist, well below the 20-row floor --
    # see the dedicated richer fixture below for a real run-length walk.)


def _daily_rows(end: dt.date, n_days: int, value_fn) -> list[tuple[str, float]]:
    """``n_days`` CONSECUTIVE daily rows ending at (and including) ``end``,
    ``value_fn(i)`` for the i-th row counting from the OLDEST (i=0) to the
    NEWEST (i=n_days-1) -- mirrors national_debt.py's ``_daily_rows`` helper,
    adapted to a caller-supplied value function."""
    return [((end - dt.timedelta(days=n_days - 1 - i)).isoformat(), value_fn(i))
            for i in range(n_days)]


def _run_length_pair_rows() -> tuple[list, list]:
    """25 consecutive daily rows ending 2026-09-02: us2y flat at 3.80
    throughout; us10y at 4.10 for the OLDEST 15 rows (spread +0.30, normal)
    and 3.50 for the NEWEST 10 rows (spread -0.30, inverted). Walking
    backward from the latest (inverted) row, the run breaks exactly at row
    15 -- hand-verified run length = 10."""
    end = dt.date(2026, 9, 2)
    us2y = _daily_rows(end, 25, lambda i: 3.80)
    us10y = _daily_rows(end, 25, lambda i: 4.10 if i < 15 else 3.50)
    return us2y, us10y


_UNSET = object()  # sentinel: distinguishes "caller omitted the arg" (use the
# default fixture) from "caller explicitly passed None/empty" (a genuinely
# absent owner input) -- a plain ``=None`` default cannot tell those apart.


def _compose(curve_frames=_UNSET, **kw) -> dict:
    return RC.compose(
        _baseline_frames() if curve_frames is _UNSET else curve_frames,
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
    assert snap["workspace"]["id"] == "rates_curves"
    assert snap["region"]["code"] == "US"
    assert snap["availability"]["state"] == "CURRENT"
    assert snap["availability"]["coverage_ratio"] == 1.0


def test_required_optional_split_matches_the_disclosed_fourteen_five() -> None:
    snap = _compose()
    all_c = snap["availability"]["required"]
    required_ids = {c["component_id"] for c in all_c if c["required"]}
    optional_ids = {c["component_id"] for c in all_c if not c["required"]}
    assert optional_ids == {"us1y", "us3y", "us7y", "us20y", "obfr"}
    assert required_ids == {
        "us3m", "us6m", "us2y", "us5y", "us10y", "us30y", "us5y_real",
        "us10y_real", "breakeven_10y", "breakeven_5y5y", "term_premium_10y",
        "effr", "sofr", "iorb",
    }
    assert len(required_ids) == 14
    assert len(optional_ids) == 5
    assert not (required_ids & optional_ids)


@pytest.mark.parametrize("optional_id,series", [
    ("us1y", RC.SERIES_US1Y), ("us3y", RC.SERIES_US3Y), ("us7y", RC.SERIES_US7Y),
    ("us20y", RC.SERIES_US20Y), ("obfr", RC.SERIES_OBFR),
])
def test_each_optional_series_missing_never_degrades_required_availability(optional_id, series) -> None:
    cf = _baseline_frames()
    cf[series] = None
    snap = _compose(curve_frames=cf)
    assert snap["availability"]["state"] == "CURRENT"
    assert snap["availability"]["coverage_ratio"] == 1.0
    opt = _required(snap, optional_id)
    assert opt["status"] == "ABSENT"
    assert opt["required"] is False
    assert opt["freshness"] == "SOURCE_FAILED"


def test_all_five_optional_series_missing_together_still_current() -> None:
    cf = _baseline_frames()
    for sid in (RC.SERIES_US1Y, RC.SERIES_US3Y, RC.SERIES_US7Y, RC.SERIES_US20Y, RC.SERIES_OBFR):
        cf[sid] = None
    snap = _compose(curve_frames=cf)
    assert snap["availability"]["state"] == "CURRENT"
    assert snap["availability"]["coverage_ratio"] == 1.0


# --------------------------------------------------------------------------- #
# levels (spot checks across every family)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("metric_id,expected", [
    ("us3m_level", 4.90), ("us6m_level", 4.70), ("us1y_level", 4.40),
    ("us2y_level", 3.80), ("us3y_level", 3.70), ("us5y_level", 3.90),
    ("us7y_level", 4.00), ("us10y_level", 4.10), ("us20y_level", 4.50),
    ("us30y_level", 4.30), ("us5y_real_level", 1.80), ("us10y_real_level", 1.90),
    ("breakeven_10y_level", 2.20), ("breakeven_5y5y_level", 2.30),
    ("term_premium_10y_level", 0.45), ("effr_level", 4.33), ("obfr_level", 4.32),
    ("sofr_level", 4.35), ("iorb_level", 4.40),
])
def test_level_metrics_pass_through(metric_id, expected) -> None:
    snap = _compose()
    m = _metric(snap, metric_id)
    assert m["value"] == pytest.approx(expected)
    assert m["value_type"] == "percent"
    assert m["freshness"] == "CURRENT"
    assert m["status"] == "PRESENT"


def test_level_metric_source_failed_when_series_wholly_absent() -> None:
    cf = _baseline_frames()
    cf[RC.SERIES_US10Y] = None
    snap = _compose(curve_frames=cf)
    m = _metric(snap, "us10y_level")
    assert m["value"] is None
    assert m["status"] == "ABSENT"
    assert m["null_reason"] == "SOURCE_FAILED"
    r = _required(snap, "us10y")
    assert r["status"] == "ABSENT"
    assert r["freshness"] == "SOURCE_FAILED"
    assert snap["availability"]["state"] == "SOURCE_FAILED"


def test_us10y_missing_propagates_to_every_dependent_derived_metric() -> None:
    cf = _baseline_frames()
    cf[RC.SERIES_US10Y] = None
    snap = _compose(curve_frames=cf)
    # Estate convention (housing/consumer_payments precedent): a MISSING input
    # series propagates as SOURCE_FAILED into every derived read that needs it;
    # COMPUTATION_REFUSED is reserved for present-but-unusable data (e.g. the
    # same-date discipline refusing mismatched legs).
    for mid in ("us10y_change_13w", "curve_2s10s_level", "curve_3m10y_level",
                "curvature_butterfly_2s5s10s", "nominal_real_breakeven_residual_10y"):
        m = _metric(snap, mid)
        assert m["value"] is None, mid
        assert m["null_reason"] == "SOURCE_FAILED", mid


def test_levels_never_rounded_or_rescaled() -> None:
    snap = _compose()
    assert _metric(snap, "us10y_level")["unit"] == "percent"
    assert _metric(snap, "us10y_level")["value"] == pytest.approx(4.10)


# --------------------------------------------------------------------------- #
# 13-week changes (hand-computable)
# --------------------------------------------------------------------------- #
def test_thirteen_week_changes() -> None:
    snap = _compose()
    assert _metric(snap, "us2y_change_13w")["value"] == pytest.approx(-0.30)
    assert _metric(snap, "us10y_change_13w")["value"] == pytest.approx(0.10)
    assert _metric(snap, "us30y_change_13w")["value"] == pytest.approx(-0.10)
    assert _metric(snap, "term_premium_10y_change_13w")["value"] == pytest.approx(0.15)


def test_thirteen_week_change_insufficient_history_when_only_latest_row() -> None:
    cf = _baseline_frames()
    cf[RC.SERIES_US2Y] = _pt(3.80)  # single row, no 13w-prior observation
    snap = _compose(curve_frames=cf)
    m = _metric(snap, "us2y_change_13w")
    assert m["value"] is None
    assert m["status"] == "ABSENT"
    assert m["null_reason"] == "INSUFFICIENT_HISTORY"
    # the level itself is unaffected
    assert _metric(snap, "us2y_level")["value"] == pytest.approx(3.80)


def test_thirteen_week_change_source_failed_when_series_wholly_absent() -> None:
    cf = _baseline_frames()
    cf[RC.SERIES_US30Y] = None
    snap = _compose(curve_frames=cf)
    m = _metric(snap, "us30y_change_13w")
    assert m["value"] is None
    assert m["null_reason"] == "SOURCE_FAILED"


def test_thirteen_week_change_refused_outside_lookback_slack() -> None:
    cf = _baseline_frames()
    # prior row sits 25 days short of the 91-day target (well beyond the
    # 10-day disclosed slack) -- refused, never a stitched-together value.
    cf[RC.SERIES_US2Y] = [("2026-05-10", 5.00), ("2026-09-02", 3.80)]
    snap = _compose(curve_frames=cf)
    m = _metric(snap, "us2y_change_13w")
    assert m["value"] is None
    assert m["null_reason"] == "INSUFFICIENT_HISTORY"


# --------------------------------------------------------------------------- #
# same-date discipline: the shared _pair_value / _triple_value /
# _shared_reading helpers (JUDGMENT CALLS 3-4), exercised both directly and
# through the public slope/corridor/decomposition metrics.
# --------------------------------------------------------------------------- #
def test_shared_reading_returns_none_when_no_common_date() -> None:
    a = [(dt.date(2026, 9, 1), 1.0)]
    b = [(dt.date(2026, 8, 15), 2.0)]
    assert RC._shared_reading([a, b], 5) is None


def test_shared_reading_refuses_when_shared_date_exceeds_staleness_bound() -> None:
    a = [(dt.date(2026, 8, 20), 1.0), (dt.date(2026, 9, 2), 1.1)]
    b = [(dt.date(2026, 8, 20), 2.0)]
    # shared date 2026-08-20 lags a's own newest (2026-09-02) by 13 days > 5
    assert RC._shared_reading([a, b], 5) is None


def test_shared_reading_accepts_at_exact_staleness_boundary() -> None:
    a = [(dt.date(2026, 8, 28), 1.0), (dt.date(2026, 9, 2), 1.1)]
    b = [(dt.date(2026, 8, 28), 2.0)]
    # lag = exactly 5 days (Aug28->Sep2); bound is inclusive (<=)
    result = RC._shared_reading([a, b], 5)
    assert result is not None
    d, vals = result
    assert d == dt.date(2026, 8, 28)
    assert vals == (1.0, 2.0)


def test_shared_reading_refuses_one_day_past_the_boundary() -> None:
    a = [(dt.date(2026, 8, 27), 1.0), (dt.date(2026, 9, 2), 1.1)]
    b = [(dt.date(2026, 8, 27), 2.0)]
    # lag = 6 days -- one more than the 5-day bound
    assert RC._shared_reading([a, b], 5) is None


def test_pair_value_leg_floor_both_missing_is_source_failed() -> None:
    d_, va, vb, fresh, null_reason = RC._pair_value([], [], "CURRENT", "CURRENT")
    assert (d_, va, vb) == (None, None, None)
    assert fresh == "SOURCE_FAILED"
    assert null_reason == "SOURCE_FAILED"


def test_pair_value_leg_floor_one_missing_is_source_failed() -> None:
    # Estate propagation law: an absent leg IS a failed source, and that
    # failure propagates into the pair read (housing/consumer precedent).
    rows = [(dt.date(2026, 9, 2), 1.0)]
    d_, va, vb, fresh, null_reason = RC._pair_value(rows, [], "CURRENT", "CURRENT")
    assert (d_, va, vb) == (None, None, None)
    assert fresh == "SOURCE_FAILED"
    assert null_reason == "SOURCE_FAILED"


def test_triple_value_leg_floor_two_of_three_missing_is_source_failed() -> None:
    d_, vals, fresh, null_reason = RC._triple_value([], [], [], "CURRENT", "CURRENT", "CURRENT")
    assert vals == (None, None, None)
    assert fresh == "SOURCE_FAILED"
    assert null_reason == "SOURCE_FAILED"


def test_triple_value_leg_floor_one_of_three_missing_is_source_failed() -> None:
    rows = [(dt.date(2026, 9, 2), 1.0)]
    d_, vals, fresh, null_reason = RC._triple_value(rows, rows, [], "CURRENT", "CURRENT", "CURRENT")
    assert null_reason == "SOURCE_FAILED"


# --------------------------------------------------------------------------- #
# slopes (2s10s / 3m10y / 5s30s) -- hand-computable + same-date refusals
# --------------------------------------------------------------------------- #
def test_slopes_hand_computed() -> None:
    snap = _compose()
    assert _metric(snap, "curve_2s10s_level")["value"] == pytest.approx(0.30)
    assert _metric(snap, "curve_3m10y_level")["value"] == pytest.approx(-0.80)
    assert _metric(snap, "curve_5s30s_level")["value"] == pytest.approx(0.40)
    for mid in ("curve_2s10s_level", "curve_3m10y_level", "curve_5s30s_level"):
        assert _metric(snap, mid)["unit"] == "pct_pts"
        assert _metric(snap, mid)["value_type"] == "number"


def test_slope_source_failed_when_one_leg_wholly_missing() -> None:
    cf = _baseline_frames()
    cf[RC.SERIES_US2Y] = None
    snap = _compose(curve_frames=cf)
    m = _metric(snap, "curve_2s10s_level")
    assert m["value"] is None
    assert m["null_reason"] == "SOURCE_FAILED"


def test_slope_refused_when_both_legs_wholly_missing() -> None:
    cf = _baseline_frames()
    cf[RC.SERIES_US2Y] = None
    cf[RC.SERIES_US10Y] = None
    snap = _compose(curve_frames=cf)
    m = _metric(snap, "curve_2s10s_level")
    assert m["value"] is None
    assert m["null_reason"] == "SOURCE_FAILED"


def test_slope_refused_when_legs_share_no_common_date() -> None:
    cf = _baseline_frames()
    cf[RC.SERIES_US2Y] = [("2026-09-01", 3.80)]
    cf[RC.SERIES_US10Y] = [("2026-08-15", 4.05)]
    snap = _compose(curve_frames=cf)
    m = _metric(snap, "curve_2s10s_level")
    assert m["value"] is None
    assert m["null_reason"] == "COMPUTATION_REFUSED"


def test_slope_refused_when_shared_date_is_too_stale() -> None:
    # both legs individually read CURRENT off their OWN separately-recent
    # prints (age 2d and 1d respectively), but the only date they share
    # (2026-08-20, a common historical print) lags each leg's own newest
    # print by 13-14 days -- well beyond the 5-day same-date bound.
    cf = _baseline_frames()
    cf[RC.SERIES_US2Y] = [("2026-08-20", 3.80), ("2026-09-02", 3.75)]
    cf[RC.SERIES_US10Y] = [("2026-08-20", 4.05), ("2026-09-03", 4.08)]
    snap = _compose(curve_frames=cf)
    m = _metric(snap, "curve_2s10s_level")
    assert m["value"] is None
    assert m["null_reason"] == "COMPUTATION_REFUSED"
    # both legs are individually fine -- freshness still CURRENT, only the
    # same-date discipline refuses the derived read
    assert m["freshness"] == "CURRENT"


def test_slope_reference_period_is_the_shared_date_not_either_legs_own_latest() -> None:
    cf = _baseline_frames()
    cf[RC.SERIES_US2Y] = [("2026-08-30", 3.80), ("2026-09-02", 3.75)]
    cf[RC.SERIES_US10Y] = [("2026-08-30", 4.05)]
    snap = _compose(curve_frames=cf)
    m = _metric(snap, "curve_2s10s_level")
    assert m["value"] == pytest.approx(4.05 - 3.80)
    assert m["reference_period"] == "2026-08-30"


# --------------------------------------------------------------------------- #
# inversion run-length (a genuine multi-day walk, the independent
# minimum-history floor, and failure-inheritance from the base spread)
# --------------------------------------------------------------------------- #
def test_inversion_run_length_hand_computed() -> None:
    us2y, us10y = _run_length_pair_rows()
    cf = _baseline_frames()
    cf[RC.SERIES_US2Y] = us2y
    cf[RC.SERIES_US10Y] = us10y
    snap = _compose(curve_frames=cf)
    m = _metric(snap, "curve_2s10s_inversion_run_length_bd")
    assert m["value"] == 10
    assert m["value_type"] == "count"
    assert m["null_reason"] is None
    # sanity: the current sign IS inverted (us10y 3.50 < us2y 3.80)
    assert _metric(snap, "curve_2s10s_level")["value"] == pytest.approx(3.50 - 3.80)


def test_inversion_run_length_direct_helper() -> None:
    shared = [(dt.date(2026, 8, 9) + dt.timedelta(days=i),
               3.80, 4.10 if i < 15 else 3.50) for i in range(25)]
    run, null_reason = RC._inversion_run_length(shared, min_rows=20)
    assert run == 10
    assert null_reason is None


def test_inversion_run_length_insufficient_history_below_floor() -> None:
    # the baseline fixture carries only 2 shared-date rows for 2s10s -- well
    # short of the 20-row floor -- even though the CURRENT sign is perfectly
    # well known from the latest shared date.
    snap = _compose()
    m = _metric(snap, "curve_2s10s_inversion_run_length_bd")
    assert m["value"] is None
    assert m["null_reason"] == "INSUFFICIENT_HISTORY"
    # the sign-bearing slope value itself is NOT held back by the same floor
    assert _metric(snap, "curve_2s10s_level")["value"] is not None


def test_inversion_run_length_direct_helper_insufficient_history() -> None:
    shared = [(dt.date(2026, 9, 2) - dt.timedelta(days=i), 3.80, 4.10) for i in range(5)]
    run, null_reason = RC._inversion_run_length(shared, min_rows=20)
    assert run is None
    assert null_reason == "INSUFFICIENT_HISTORY"


def test_inversion_run_length_inherits_base_leg_floor_failure() -> None:
    cf = _baseline_frames()
    cf[RC.SERIES_US10Y] = None
    snap = _compose(curve_frames=cf)
    m = _metric(snap, "curve_2s10s_inversion_run_length_bd")
    assert m["value"] is None
    # inherits the SAME reason as the base spread null (estate propagation
    # law: us10y absent -> its absence propagates as SOURCE_FAILED into every
    # dependent read), never a generic INSUFFICIENT_HISTORY masking the real
    # cause.
    assert m["null_reason"] == "SOURCE_FAILED"


def test_inversion_run_length_inherits_source_failed_when_both_legs_absent() -> None:
    cf = _baseline_frames()
    cf[RC.SERIES_US2Y] = None
    cf[RC.SERIES_US10Y] = None
    snap = _compose(curve_frames=cf)
    m = _metric(snap, "curve_2s10s_inversion_run_length_bd")
    assert m["value"] is None
    assert m["null_reason"] == "SOURCE_FAILED"


def test_run_length_uses_business_days_unit() -> None:
    us2y, us10y = _run_length_pair_rows()
    cf = _baseline_frames()
    cf[RC.SERIES_US2Y] = us2y
    cf[RC.SERIES_US10Y] = us10y
    snap = _compose(curve_frames=cf)
    m = _metric(snap, "curve_2s10s_inversion_run_length_bd")
    assert m["unit"] == "business_days"


# --------------------------------------------------------------------------- #
# curvature butterfly (2*5y - 2y - 10y)
# --------------------------------------------------------------------------- #
def test_curvature_butterfly_hand_computed() -> None:
    snap = _compose()
    m = _metric(snap, "curvature_butterfly_2s5s10s")
    assert m["value"] == pytest.approx(2 * 3.90 - 3.80 - 4.10)  # = -0.10


def test_curvature_butterfly_source_failed_when_one_leg_missing() -> None:
    cf = _baseline_frames()
    cf[RC.SERIES_US5Y] = None
    snap = _compose(curve_frames=cf)
    m = _metric(snap, "curvature_butterfly_2s5s10s")
    assert m["value"] is None
    assert m["null_reason"] == "SOURCE_FAILED"


def test_curvature_butterfly_source_failed_when_all_three_legs_missing() -> None:
    cf = _baseline_frames()
    cf[RC.SERIES_US2Y] = None
    cf[RC.SERIES_US5Y] = None
    cf[RC.SERIES_US10Y] = None
    snap = _compose(curve_frames=cf)
    m = _metric(snap, "curvature_butterfly_2s5s10s")
    assert m["value"] is None
    assert m["null_reason"] == "SOURCE_FAILED"


# --------------------------------------------------------------------------- #
# nominal/real/breakeven decomposition residual + the one contradiction
# --------------------------------------------------------------------------- #
def test_decomposition_residual_within_tolerance_no_contradiction() -> None:
    snap = _compose()
    m = _metric(snap, "nominal_real_breakeven_residual_10y")
    assert m["value"] == pytest.approx(0.0)
    assert m["status"] == "PRESENT"
    assert snap["availability"]["contradiction"]["present"] is False


def test_decomposition_residual_exactly_at_tolerance_boundary_does_not_fire() -> None:
    cf = _baseline_frames()
    # nominal=4.10, real=1.90, breakeven=2.05 -> residual = 4.10-3.95 = 0.15
    cf[RC.SERIES_BREAKEVEN_10Y] = _pt(2.05)
    snap = _compose(curve_frames=cf)
    m = _metric(snap, "nominal_real_breakeven_residual_10y")
    assert m["value"] == pytest.approx(0.15)
    assert m["status"] == "PRESENT"
    assert snap["availability"]["contradiction"]["present"] is False


def test_decomposition_residual_just_over_boundary_fires() -> None:
    cf = _baseline_frames()
    # nominal=4.10, real=1.90, breakeven=2.04 -> residual = 4.10-3.94 = 0.16
    cf[RC.SERIES_BREAKEVEN_10Y] = _pt(2.04)
    snap = _compose(curve_frames=cf)
    m = _metric(snap, "nominal_real_breakeven_residual_10y")
    assert m["value"] == pytest.approx(0.16)
    assert m["status"] == "DISAGREEMENT"
    assert m["null_reason"] == "DISAGREEMENT"
    c = snap["availability"]["contradiction"]
    assert c["present"] is True
    assert c["kind"] == "nominal_real_breakeven_decomposition_disagreement"
    assert c["components"] == ["nominal_real_breakeven_residual_10y"]
    assert any("contradiction=nominal_real_breakeven_decomposition_disagreement" in r
               for r in snap["availability"]["reasons"])
    assert any(i["implication_id"] == "contradiction_nominal_real_breakeven_decomposition_disagreement"
               for i in snap["implications"]["items"])


def test_decomposition_residual_negative_direction_fires_too() -> None:
    cf = _baseline_frames()
    # nominal=4.10, real=1.90, breakeven=2.40 -> real+breakeven=4.30,
    # residual = 4.10-4.30 = -0.20 (below, magnitude 0.20 > 0.15)
    cf[RC.SERIES_BREAKEVEN_10Y] = _pt(2.40)
    snap = _compose(curve_frames=cf)
    m = _metric(snap, "nominal_real_breakeven_residual_10y")
    assert m["value"] == pytest.approx(-0.20)
    assert m["status"] == "DISAGREEMENT"


def test_decomposition_source_failed_when_one_leg_missing() -> None:
    cf = _baseline_frames()
    cf[RC.SERIES_US10Y_REAL] = None
    snap = _compose(curve_frames=cf)
    m = _metric(snap, "nominal_real_breakeven_residual_10y")
    assert m["value"] is None
    assert m["null_reason"] == "SOURCE_FAILED"
    assert snap["availability"]["contradiction"]["present"] is False


def test_decomposition_tolerance_constant_matches_disclosed_15bp() -> None:
    assert RC._DECOMPOSITION_RESIDUAL_TOLERANCE_PCT_PTS == pytest.approx(0.15)


# --------------------------------------------------------------------------- #
# policy corridor spreads (basis points)
# --------------------------------------------------------------------------- #
def test_corridor_spreads_hand_computed() -> None:
    snap = _compose()
    assert _metric(snap, "corridor_effr_minus_iorb_bp")["value"] == pytest.approx(-7.0)
    assert _metric(snap, "corridor_sofr_minus_effr_bp")["value"] == pytest.approx(2.0)
    assert _metric(snap, "corridor_sofr_minus_iorb_bp")["value"] == pytest.approx(-5.0)
    for mid in ("corridor_effr_minus_iorb_bp", "corridor_sofr_minus_effr_bp",
                "corridor_sofr_minus_iorb_bp"):
        assert _metric(snap, mid)["value_type"] == "basis_points"
        assert _metric(snap, mid)["unit"] == "bp"


def test_corridor_spread_source_failed_when_one_leg_missing() -> None:
    cf = _baseline_frames()
    cf[RC.SERIES_IORB] = None
    snap = _compose(curve_frames=cf)
    m = _metric(snap, "corridor_effr_minus_iorb_bp")
    assert m["value"] is None
    assert m["null_reason"] == "SOURCE_FAILED"
    # the sibling spread not touching IORB is unaffected
    assert _metric(snap, "corridor_sofr_minus_effr_bp")["value"] == pytest.approx(2.0)


def test_corridor_spread_never_published_in_percent() -> None:
    snap = _compose()
    m = _metric(snap, "corridor_sofr_minus_iorb_bp")
    assert m["unit"] != "percent"


# --------------------------------------------------------------------------- #
# freshness cadence law (daily 5d/4d, term premium 9d/5d)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("age_days,cadence,grace,expected", [
    (0, 5, 4, "CURRENT"),
    (5, 5, 4, "CURRENT"),
    (6, 5, 4, "LATE_WITHIN_TOLERANCE"),
    (9, 5, 4, "LATE_WITHIN_TOLERANCE"),
    (10, 5, 4, "STALE_SOURCE"),
    (0, 9, 5, "CURRENT"),
    (9, 9, 5, "CURRENT"),
    (10, 9, 5, "LATE_WITHIN_TOLERANCE"),
    (14, 9, 5, "LATE_WITHIN_TOLERANCE"),
    (15, 9, 5, "STALE_SOURCE"),
])
def test_cadence_freshness_tiers(age_days, cadence, grace, expected) -> None:
    asof = BUILT_DATE - dt.timedelta(days=age_days)
    got = RC._cadence_freshness(BUILT_AT, asof, cadence, grace, True)
    assert got == expected


def test_cadence_freshness_absent_value_is_source_failed() -> None:
    assert RC._cadence_freshness(BUILT_AT, BUILT_DATE, 5, 4, False) == "SOURCE_FAILED"


def test_cadence_freshness_future_asof_is_source_failed() -> None:
    future = BUILT_DATE + dt.timedelta(days=5)
    assert RC._cadence_freshness(BUILT_AT, future, 5, 4, True) == "SOURCE_FAILED"


def test_daily_cadence_hand_check_worst_case_holiday_age_reads_current() -> None:
    # worst-case newest-possible print over a long weekend/holiday cluster
    # (~4-5 calendar days) must still read CURRENT under the disclosed 5d/4d law.
    asof = BUILT_DATE - dt.timedelta(days=5)
    got = RC._cadence_freshness(BUILT_AT, asof, RC._DAILY_CADENCE_DAYS, RC._DAILY_GRACE_DAYS, True)
    assert got == "CURRENT"


def test_term_premium_cadence_hand_check_extra_lag_reads_current() -> None:
    asof = dt.date(2026, 8, 28)  # age 7 days, disclosed extra publication lag
    got = RC._cadence_freshness(BUILT_AT, asof, RC._TERM_PREMIUM_CADENCE_DAYS,
                                 RC._TERM_PREMIUM_GRACE_DAYS, True)
    assert got == "CURRENT"


def test_baseline_disk_truth_anchor_reads_current() -> None:
    # real disk-truth check: every daily series anchored 2026-09-02 (age 2d)
    # on 2026-09-04 -- must read CURRENT.
    snap = _compose()
    assert _required(snap, "us10y")["freshness"] == "CURRENT"
    assert RC._age_days(BUILT_AT, dt.date(2026, 9, 2)) == 2


# --------------------------------------------------------------------------- #
# headline: NOT_APPLICABLE (a design absence -- no architecture section
# exists for this expansion workspace at all)
# --------------------------------------------------------------------------- #
def test_headline_is_not_applicable_a_design_absence() -> None:
    snap = _compose()
    h = snap["headline"]
    assert h["state_id"] is None
    assert h["status"] == "ABSENT"
    assert h["null_reason"] == "NOT_APPLICABLE"
    assert h["quadrant"] == {"x": None, "y": None, "x_status": "ABSENT", "y_status": "ABSENT"}
    assert h["nearest_boundary"]["null_reason"] == "NOT_APPLICABLE"
    assert h["one_month_vector"]["null_reason"] == "NOT_APPLICABLE"
    assert h["hysteresis"]["applied"] is False
    assert "Chairman-authorized expansion" in h["hysteresis"]["note"]


def test_axes_items_is_empty_by_design() -> None:
    snap = _compose()
    assert snap["axes"]["items"] == []


def test_headline_unaffected_by_data_completeness() -> None:
    # even a fully-populated, all-CURRENT build still carries the same
    # design-absence null -- this is not a per-build degraded state.
    snap = _compose()
    assert snap["availability"]["state"] == "CURRENT"
    assert snap["headline"]["null_reason"] == "NOT_APPLICABLE"


def test_headline_hysteresis_note_never_leaks_raw_not_applicable_token() -> None:
    # the leak guard scans prose fields -- the hysteresis note is prose and
    # must describe the design absence WITHOUT the raw closed-vocabulary token.
    note = _compose()["headline"]["hysteresis"]["note"]
    assert "NOT_APPLICABLE" not in note


# --------------------------------------------------------------------------- #
# digest determinism (contract.py's content_digest excludes generation/build
# provenance; identical owner input -> identical digest)
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


def test_digest_changes_when_consumed_level_field_changes() -> None:
    snap1 = contract.finalize(_compose())
    cf2 = _baseline_frames()
    cf2[RC.SERIES_US10Y] = _pt(9.99, 4.00)
    snap2 = contract.finalize(_compose(curve_frames=cf2))
    assert snap1["generation"]["content_sha256"] != snap2["generation"]["content_sha256"]


def test_digest_changes_when_consumed_corridor_field_changes() -> None:
    snap1 = contract.finalize(_compose())
    cf2 = _baseline_frames()
    cf2[RC.SERIES_IORB] = _pt(1.11)
    snap2 = contract.finalize(_compose(curve_frames=cf2))
    assert snap1["generation"]["content_sha256"] != snap2["generation"]["content_sha256"]


def test_digest_unaffected_by_unconsumed_dict_key() -> None:
    snap1 = contract.finalize(_compose())
    cf3 = _baseline_frames()
    cf3["DTB3"] = _pt(4.50)  # never read by this composer (discount basis, excluded)
    snap3 = contract.finalize(_compose(curve_frames=cf3))
    assert snap1["generation"]["content_sha256"] == snap3["generation"]["content_sha256"]


def test_digest_unaffected_by_unconsumed_row_tuple_element() -> None:
    snap1 = contract.finalize(_compose())
    cf4 = _baseline_frames()
    cf4[RC.SERIES_US2Y] = [
        ("2026-06-03", 4.10, "unrelated-extra-field"),
        ("2026-09-02", 3.80, {"nested": "also unrelated"}),
    ]
    snap4 = contract.finalize(_compose(curve_frames=cf4))
    assert snap1["generation"]["content_sha256"] == snap4["generation"]["content_sha256"]


def test_digest_unaffected_by_duplicate_date_keeping_last_listed() -> None:
    snap1 = contract.finalize(_compose())
    cf5 = _baseline_frames()
    # a duplicated date with a stale first value, LAST-listed wins (matches
    # _clean_rows's dict-overwrite convention) -- final result identical.
    cf5[RC.SERIES_US2Y] = [("2026-06-03", 4.10), ("2026-09-02", -999.0), ("2026-09-02", 3.80)]
    snap5 = contract.finalize(_compose(curve_frames=cf5))
    assert snap1["generation"]["content_sha256"] == snap5["generation"]["content_sha256"]


# --------------------------------------------------------------------------- #
# changes / method-version comparability
# --------------------------------------------------------------------------- #
def _prior(method=RC.METHOD_VERSION, us10y_level=4.10,
           gen="rates_curves-US-deadbeefdeadbeef") -> dict:
    prior = _compose()
    prior["headline"]["method_version"] = method
    prior["headline"]["effective_date"] = "2026-08-21"
    prior["generation"]["generation_id"] = gen
    for m in prior["metrics"]["items"]:
        if m["metric_id"] == "us10y_level":
            m["value"] = us10y_level
    return prior


def test_changes_no_prior_yields_warmup() -> None:
    snap = _compose()
    assert snap["changes"]["comparability"] == "NO_PRIOR"
    assert snap["changes"]["null_reason"] == "WARMUP"


def test_changes_method_mismatch_refuses_numeric_comparison() -> None:
    snap = _compose(prior_snapshot=_prior(method="rates_curves.compose.v0"))
    assert snap["changes"]["comparability"] == "METHOD_CHANGED"
    assert snap["changes"]["deltas"] == []
    assert snap["changes"]["null_reason"] == "COMPUTATION_REFUSED"


def test_changes_comparable_prior_produces_deltas() -> None:
    snap = _compose(prior_snapshot=_prior(us10y_level=4.00))
    assert snap["changes"]["comparability"] == "COMPARABLE"
    ids = {d["metric_id"] for d in snap["changes"]["deltas"]}
    assert ids == set(RC._TRACKED_CHANGE_METRICS)
    delta = next(d for d in snap["changes"]["deltas"] if d["metric_id"] == "us10y_level")
    assert delta["prior_value"] == 4.00
    assert delta["current_value"] == pytest.approx(4.10)
    assert delta["delta"] == pytest.approx(0.10)


# --------------------------------------------------------------------------- #
# corrections / supersession honesty
# --------------------------------------------------------------------------- #
def test_corrections_none_for_first_print() -> None:
    snap = _compose()
    assert snap["corrections"]["correction_state"] == "none"
    assert snap["corrections"]["predecessor_generation_id"] is None


def test_corrections_superseded_when_same_period_value_changes() -> None:
    cf = _baseline_frames()
    prior_snap = contract.finalize(RC.compose(cf, built_at=BUILT_AT))
    cf2 = copy.deepcopy(cf)
    cf2[RC.SERIES_US10Y][-1] = ("2026-09-02", 5.00)  # same asof, revised value
    snap2 = RC.compose(cf2, built_at=BUILT_AT, prior_snapshot=prior_snap)
    assert snap2["corrections"]["correction_state"] == "superseded"
    assert snap2["corrections"]["changed_fingerprints"]
    assert snap2["corrections"]["predecessor_generation_id"] == prior_snap["generation"]["generation_id"]


def test_corrections_none_when_reference_period_advances() -> None:
    cf = _baseline_frames()
    prior_snap = contract.finalize(RC.compose(cf, built_at=BUILT_AT))
    cf2 = copy.deepcopy(cf)
    cf2[RC.SERIES_US10Y] = cf2[RC.SERIES_US10Y] + [("2026-09-03", 4.20)]
    snap2 = RC.compose(cf2, built_at="2026-09-04T12:00:00Z", prior_snapshot=prior_snap)
    assert snap2["corrections"]["correction_state"] == "none"


# --------------------------------------------------------------------------- #
# schema validation (SCHEMA DEPENDENCY -- see module docstring: the schema's
# workspaceId enum was verified during authoring to already include
# "rates_curves"; these tests were hand-traced, never executed, since no
# shell/pytest access was available to this authoring session)
# --------------------------------------------------------------------------- #
def test_baseline_snapshot_validates_against_the_closed_contract() -> None:
    snap = contract.finalize(_compose())
    contract.validate(snap)  # raises ContractError on any violation
    assert snap["authority"]["can_size"] is False
    assert snap["authority"]["can_execute"] is False
    assert snap["authority"]["can_originate_signal"] is False


def test_degraded_snapshot_still_validates() -> None:
    cf = _baseline_frames()
    cf[RC.SERIES_US10Y] = None
    snap = contract.finalize(RC.compose(cf, built_at=BUILT_AT))
    contract.validate(snap)


def test_contradiction_snapshot_validates() -> None:
    cf = _baseline_frames()
    cf[RC.SERIES_BREAKEVEN_10Y] = _pt(2.40)
    snap = contract.finalize(RC.compose(cf, built_at=BUILT_AT))
    contract.validate(snap)
    assert snap["availability"]["contradiction"]["present"] is True


def test_all_owner_inputs_missing_still_validates() -> None:
    snap = contract.finalize(RC.compose(None, built_at=BUILT_AT))
    contract.validate(snap)
    assert snap["availability"]["state"] == "SOURCE_FAILED"
    assert snap["availability"]["coverage_ratio"] == 0.0


def test_all_inputs_missing_never_crashes_and_types_every_metric_absent() -> None:
    snap = RC.compose({}, built_at=BUILT_AT)
    for m in snap["metrics"]["items"]:
        assert m["value"] is None
        assert m["status"] == "ABSENT"
        assert m["null_reason"] in ("SOURCE_FAILED", "COMPUTATION_REFUSED")


def test_compose_tolerates_none_curve_frames_argument() -> None:
    snap = RC.compose(None, built_at=BUILT_AT)
    assert snap["workspace"]["id"] == "rates_curves"
    assert snap["availability"]["state"] == "SOURCE_FAILED"


# --------------------------------------------------------------------------- #
# metric inventory
# --------------------------------------------------------------------------- #
def test_metric_ids_are_unique_and_stable_count() -> None:
    snap = _compose()
    ids = [m["metric_id"] for m in snap["metrics"]["items"]]
    assert len(ids) == len(set(ids))
    assert len(ids) == 33


def test_metric_inventory_covers_every_named_domain_read() -> None:
    snap = _compose()
    ids = {m["metric_id"] for m in snap["metrics"]["items"]}
    expected = {
        "us3m_level", "us6m_level", "us1y_level", "us2y_level", "us3y_level",
        "us5y_level", "us7y_level", "us10y_level", "us20y_level", "us30y_level",
        "us5y_real_level", "us10y_real_level", "breakeven_10y_level",
        "breakeven_5y5y_level", "term_premium_10y_level", "effr_level",
        "obfr_level", "sofr_level", "iorb_level",
        "us2y_change_13w", "us10y_change_13w", "us30y_change_13w",
        "term_premium_10y_change_13w",
        "curve_2s10s_level", "curve_3m10y_level", "curve_5s30s_level",
        "curve_2s10s_inversion_run_length_bd", "curve_3m10y_inversion_run_length_bd",
        "curvature_butterfly_2s5s10s", "nominal_real_breakeven_residual_10y",
        "corridor_effr_minus_iorb_bp", "corridor_sofr_minus_effr_bp",
        "corridor_sofr_minus_iorb_bp",
    }
    assert ids == expected


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
    # exercise every disclosure branch at once: contradiction fired, a
    # required leg missing, an optional leg missing, insufficient history.
    cf = _baseline_frames()
    cf[RC.SERIES_BREAKEVEN_10Y] = _pt(2.40)  # fires the contradiction
    cf[RC.SERIES_US30Y] = None               # a required leg missing
    cf[RC.SERIES_OBFR] = None                # an optional leg missing
    snap = _compose(curve_frames=cf)
    leaks = _find_raw_token_leaks(snap)
    assert leaks == [], f"raw enum tokens leaked into prose field(s): {leaks}"


def test_prose_fields_contain_no_raw_enum_tokens_all_missing() -> None:
    snap = RC.compose({}, built_at=BUILT_AT)
    leaks = _find_raw_token_leaks(snap)
    assert leaks == [], f"raw enum tokens leaked into prose field(s): {leaks}"


# --------------------------------------------------------------------------- #
# zh-label integrity: composer-authored English phrasing must never leak into
# the composer-authored zh sibling
# --------------------------------------------------------------------------- #
_COMPOSER_ENGLISH_PHRASES = (
    "Chairman-authorized expansion", "same-date discipline", "never mixing",
    "a design absence, not a data gap", "cosmetic bucket reuse",
    "interpolation-noise tolerance", "literal fit",
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
    cf = _baseline_frames()
    cf[RC.SERIES_BREAKEVEN_10Y] = _pt(2.40)
    snap = _compose(curve_frames=cf)
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
# disclosure implications present
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("iid", [
    "headline_unavailable", "seam_decision_disclosure",
    "same_date_discipline_disclosure", "investment_basis_only_disclosure",
    "driver_bucket_naming_note",
])
def test_disclosure_implications_present(iid) -> None:
    snap = _compose()
    assert _implication(snap, iid) is not None


def test_seam_decision_disclosure_names_rates_command_and_monetary_policy() -> None:
    snap = _compose()
    text = _implication(snap, "seam_decision_disclosure")["text"]["en"]
    assert "rates_command" in text
    assert "Monetary Policy" in text


def test_investment_basis_disclosure_names_dtb3_exclusion() -> None:
    snap = _compose()
    text = _implication(snap, "investment_basis_only_disclosure")["text"]["en"]
    assert "DTB3" in text


def test_driver_bucket_reuse_disclosed_in_drivers_and_implication() -> None:
    snap = _compose()
    rate_side_ids = {d["driver_id"] for d in snap["drivers"]["rate_side"]}
    balance_sheet_ids = {d["driver_id"] for d in snap["drivers"]["balance_sheet"]}
    assert "us10y_level" in rate_side_ids
    assert "corridor_sofr_minus_iorb_bp" in balance_sheet_ids
    assert _implication(snap, "driver_bucket_naming_note") is not None


def test_curve_shape_and_inversion_and_corridor_reads_present_at_baseline() -> None:
    snap = _compose()
    for iid in ("curve_shape_read", "inversion_status_read", "real_breakeven_decomposition_read",
                "term_premium_read", "corridor_read"):
        assert _implication(snap, iid) is not None, iid


# --------------------------------------------------------------------------- #
# sources
# --------------------------------------------------------------------------- #
def test_sources_include_all_nineteen_series() -> None:
    snap = _compose()
    source_ids = {s["source_id"] for s in snap["sources"]["items"]}
    assert len(source_ids) == 19
    assert "dgs10" in source_ids
    assert "effr" in source_ids
    assert all(s["provider"] and "FRED" in s["provider"] for s in snap["sources"]["items"])


def test_source_refs_use_the_prescribed_fred_style() -> None:
    snap = _compose()
    assert _metric(snap, "us10y_level")["source_refs"] == ["FRED:DGS10"]
    assert set(_metric(snap, "curve_2s10s_level")["source_refs"]) == {"FRED:DGS10", "FRED:DGS2"}


# --------------------------------------------------------------------------- #
# scenario / alert contracts (declared vocabulary only -- non-goal: execution)
# --------------------------------------------------------------------------- #
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
# authority ceiling (no rank/gate/size/originate/execute authority anywhere)
# --------------------------------------------------------------------------- #
def test_authority_is_fully_descriptive() -> None:
    snap = _compose()
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
