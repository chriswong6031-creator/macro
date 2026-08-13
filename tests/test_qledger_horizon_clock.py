"""P0a — the EXPLICIT HORIZON-CLOCK CONTRACT for engine/qledger.py.

THE DEFECT THESE TESTS PIN. `horizon_d` used to be a bare integer with no
declared unit, and qledger read it two different ways in the same module:

    make_claim()  ->  check_by = asof + pd.offsets.BusinessDay(horizon_d)
    _fwd_ret()    ->  exit     = fill + pd.Timedelta(days=horizon_d)   [CALENDAR]

From a Friday asof=2026-08-07 those diverge by +2d at horizon_d=5, +4d at 7 and
+10d at 21 — the falsifier deadline a human read and the window actually graded
were ten days apart at the 21d rung. The emitters disagreed too: four desks
document "integer TRADING days", build_whitehouse passes CALENDAR banner_days,
and engine/source_registry bypassed `_fwd_ret` outright to compute an exact
trading-session exit precisely because an approximated calendar horizon is unsafe.

WHAT IS ASSERTED HERE (one test per contract clause):
  * a declared unit changes the resolved exit — 5 trading days and 5 calendar
    days do NOT land on the same day across a weekend;
  * exchange HOLIDAYS are excluded, and both `pd.Timedelta` and
    `pd.offsets.BusinessDay` are shown to give the WRONG answer on the same case
    (BusinessDay counts Mon-Fri, so it walks straight through Thanksgiving);
  * `check_by` and the grader resolve the SAME exit, under BOTH units — one
    resolver, no second implementation, and NO bypass: a caller-supplied
    `check_by` (the two highest-volume US backfill lanes pass one) does not
    override the clock, it is kept for audit as `check_by_source`;
  * one window is SHARED by subject, bench and control, so no leg silently
    receives a different horizon length — and that is ENFORCED, not described:
    a leg missing either endpoint bar of the window is REFUSED, never graded
    over a shortened window under the declared horizon's label;
  * LEGACY (unitless) claims keep the pre-P0a arithmetic exactly and are stamped
    as the legacy basis, never re-labelled;
  * observations from different clock bases CANNOT be pooled — the aggregation
    primitive raises, and the promotion gate evaluates INSIDE one basis (never
    pooling, never permanently refusing: the migration terminates);
  * the resolver states its supported date range instead of mis-resolving old
    anchors, and never returns a window maturity would call ready but the return
    path would refuse.

Hermetic: tmp_path store, synthetic session-indexed prices monkeypatched onto
the shared parquet layer. Nothing reads or asserts over data/qledger — the
nightly-appended store is never a fixture.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from engine import qledger as q
from lib.nyse_calendar import is_session, sessions_between


# --------------------------------------------------------------------------- #
# synthetic price layer — indexed on REAL NYSE sessions
# --------------------------------------------------------------------------- #
# Deliberately NOT pd.bdate_range: business days include market holidays, and a
# holiday-blind fixture cannot tell a correct session ruler from BusinessDay.
def _session_series(start: str, end: str, start_px: float, drift: float) -> pd.Series:
    idx = [pd.Timestamp(d) for d in
           sessions_between(date.fromisoformat(start), date.fromisoformat(end))]
    return pd.Series([start_px * (1.0 + drift) ** i for i in range(len(idx))],
                     index=pd.DatetimeIndex(idx))


@pytest.fixture
def prices(monkeypatch):
    """Subject/bench/control on the real session calendar, spanning both the
    2026-08 weekend case and the 2026-11 Thanksgiving case."""
    store = {
        "CARR": _session_series("2026-01-02", "2026-12-31", 100.0, 0.010),
        "SPY":  _session_series("2026-01-02", "2026-12-31", 400.0, 0.002),
        "XLI":  _session_series("2026-01-02", "2026-12-31", 100.0, 0.004),
    }
    monkeypatch.setattr("engine.ai_desk._close_series",
                        lambda ticker, root: store.get(ticker))
    return store


def _claim(**kw):
    base = dict(desk="clocktest", asof="2026-08-07", scope_type="entity",
                scope_key="CARR", direction=1, horizon_d=5,
                timestamp_quality="CRAWL_BOUNDED", sector="Industrials",
                claim_family="clocktest")
    base.update(kw)
    return q.make_claim(**base)


# --------------------------------------------------------------------------- #
# ACCEPTANCE 1 — the unit changes the exit
# --------------------------------------------------------------------------- #
def test_five_trading_days_and_five_calendar_days_differ_across_a_weekend():
    """asof = Friday 2026-08-07. The shared fill is Monday 2026-08-10.
    5 sessions later is Monday 2026-08-17; 5 calendar days later is Saturday
    2026-08-15 (window closing on Friday 2026-08-14). A single unitless integer
    cannot mean both."""
    td = q.resolve_horizon_window("2026-08-07", 5, q.HORIZON_UNIT_TRADING)
    cd = q.resolve_horizon_window("2026-08-07", 5, q.HORIZON_UNIT_CALENDAR)

    assert td.fill_date == cd.fill_date == date(2026, 8, 10)   # ONE shared fill
    assert td.exit_date == date(2026, 8, 17)
    assert cd.exit_date == date(2026, 8, 15)
    assert td.exit_date != cd.exit_date

    # calendar exits can land on a closed day; the window closes on the last
    # session on/before it, and that is what maturity is measured against.
    assert not is_session(cd.exit_date)
    assert cd.coverage_date == date(2026, 8, 14)
    assert td.coverage_date == td.exit_date


def test_declared_number_is_never_converted():
    """Contract rule 2: horizon_d stays the DECLARED ruler. A 126-trading-day
    policy claim and a 7-calendar-day whitehouse claim keep their own numbers."""
    policy = _claim(horizon_d=126, horizon_unit=q.HORIZON_UNIT_TRADING)
    wh = _claim(horizon_d=7, horizon_unit=q.HORIZON_UNIT_CALENDAR)
    assert policy["horizon_d"] == 126
    assert policy["horizon_unit"] == q.HORIZON_UNIT_TRADING
    assert wh["horizon_d"] == 7
    assert wh["horizon_unit"] == q.HORIZON_UNIT_CALENDAR


# --------------------------------------------------------------------------- #
# ACCEPTANCE 2 — a real market holiday
# --------------------------------------------------------------------------- #
def test_thanksgiving_is_excluded_and_businessday_would_be_wrong():
    """Thanksgiving 2026-11-26 (Thu) is a full NYSE closure.

    From the fill Wed 2026-11-25, two SESSIONS forward is Mon 2026-11-30 —
    Thursday does not exist, Friday 11-27 is session one. Both rejected rulers
    land on Fri 2026-11-27 instead: `pd.Timedelta(days=2)` because it counts
    calendar days, and `pd.offsets.BusinessDay(2)` because it counts Mon-Fri and
    so walks straight THROUGH the holiday."""
    thanksgiving = date(2026, 11, 26)
    assert not is_session(thanksgiving), "fixture premise: NYSE shut that day"

    win = q.resolve_horizon_window("2026-11-24", 2, q.HORIZON_UNIT_TRADING)
    assert win.fill_date == date(2026, 11, 25)
    assert win.exit_date == date(2026, 11, 30)

    wrong_calendar = (pd.Timestamp(win.fill_date) + pd.Timedelta(days=2)).date()
    wrong_bday = (pd.Timestamp(win.fill_date) + pd.offsets.BusinessDay(2)).date()
    assert wrong_calendar == date(2026, 11, 27) != win.exit_date
    assert wrong_bday == date(2026, 11, 27) != win.exit_date


def test_independence_day_observed_closure_is_excluded():
    """2026-07-04 falls on a Saturday, so NYSE observes it on Friday 2026-07-03.
    One session after the Thursday 07-02 fill is Monday 07-06, not 07-03."""
    assert not is_session(date(2026, 7, 3))
    win = q.resolve_horizon_window("2026-07-01", 1, q.HORIZON_UNIT_TRADING)
    assert win.fill_date == date(2026, 7, 2)
    assert win.exit_date == date(2026, 7, 6)
    assert (pd.Timestamp(win.fill_date) + pd.offsets.BusinessDay(1)).date() == date(2026, 7, 3)


def test_a_non_session_anchor_still_fills_on_the_next_session():
    """asof can be a Saturday or a holiday; the fill is the next open session."""
    assert q.next_session_strictly_after(date(2026, 8, 8)) == date(2026, 8, 10)
    assert q.next_session_strictly_after(date(2026, 11, 25)) == date(2026, 11, 27)


# --------------------------------------------------------------------------- #
# ACCEPTANCE 3 — check_by and the grader resolve the SAME exit (both units)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("unit, expected_exit", [
    (q.HORIZON_UNIT_TRADING, "2026-08-17"),
    (q.HORIZON_UNIT_CALENDAR, "2026-08-15"),
])
def test_check_by_equals_the_graded_exit(prices, tmp_path, unit, expected_exit):
    """One resolver, one answer. `check_by` is the falsifier deadline a human
    reads; `clock_exit_date` is the boundary the grade was actually measured to.
    Before P0a these were different implementations and drifted up to 10 days
    apart at horizon_d=21."""
    c = _claim(horizon_unit=unit)
    assert c["check_by"] == expected_exit

    rows = q.grade_claim({**c, "claim_id": "cid-1"}, root=tmp_path,
                         today=date(2026, 9, 30))
    assert len(rows) == 1, rows                       # in_scope_horizons(5) == [5]
    row = rows[0]
    assert row["horizon_d"] == 5
    assert row["clock_exit_date"] == c["check_by"]
    assert row["horizon_unit"] == unit
    assert row["clock_version"] == q.CLOCK_V1


def test_disclosure_embargo_shifts_check_by_and_the_grader_together(prices, tmp_path):
    """A DISCLOSURE_DATE claim enters +1bd. If check_by anchored on the raw asof
    while the grader anchored on the shifted date, the divergence this contract
    closes would reopen through the embargo path."""
    c = _claim(timestamp_quality="DISCLOSURE_DATE",
               horizon_unit=q.HORIZON_UNIT_TRADING)
    rows = q.grade_claim({**c, "claim_id": "cid-emb"}, root=tmp_path,
                         today=date(2026, 9, 30))
    assert rows and rows[0]["clock_exit_date"] == c["check_by"]
    # asof Fri 08-07 -> +1bd = Mon 08-10 -> fill Tue 08-11 -> 5 sessions -> 08-18
    assert c["check_by"] == "2026-08-18"


# --------------------------------------------------------------------------- #
# rule 5 — ONE window shared by every leg
# --------------------------------------------------------------------------- #
def test_every_leg_is_measured_over_the_same_window(prices, tmp_path):
    """Subject, bench and control are priced on the SAME resolved fill/exit, so
    the three legs cannot silently receive different horizon lengths."""
    c = _claim(horizon_unit=q.HORIZON_UNIT_TRADING)
    win = q.resolve_horizon_window("2026-08-07", 5, q.HORIZON_UNIT_TRADING)

    rows = q.grade_claim({**c, "claim_id": "cid-legs"}, root=tmp_path,
                         today=date(2026, 9, 30))
    row = rows[0]
    assert row["control_ret"] is not None, "control leg must be priced"

    for ticker, key in (("CARR", "subject_ret"), ("SPY", "bench_ret"),
                        ("XLI", "control_ret")):
        s = prices[ticker]
        w = s[(s.index >= pd.Timestamp(win.fill_date))
              & (s.index <= pd.Timestamp(win.exit_date))]
        assert len(w) == 6, f"{ticker}: fill + 5 sessions"
        assert row[key] == pytest.approx(round(float(w.iloc[-1]) / float(w.iloc[0]) - 1.0, 6))


# --------------------------------------------------------------------------- #
# ACCEPTANCE 4 — the legacy basis is immutable
# --------------------------------------------------------------------------- #
def test_a_unitless_claim_still_grades_on_the_pre_p0a_calendar_math(prices, tmp_path):
    """No `horizon_unit` == the LEGACY clock. The graded number must still equal
    the pre-P0a arithmetic (entry = first close strictly after asof; exit = last
    close on/before fill + Timedelta(days=h)), so nothing already in
    grades.jsonl is invalidated by this change."""
    c = _claim()                                   # no horizon_unit
    assert "horizon_unit" not in c
    # legacy check_by default is untouched: asof + BusinessDay(horizon_d)
    assert c["check_by"] == (pd.Timestamp("2026-08-07")
                             + pd.offsets.BusinessDay(5)).date().isoformat()

    rows = q.grade_claim({**c, "claim_id": "cid-legacy"}, root=tmp_path,
                         today=date(2026, 9, 30))
    row = rows[0]
    s = prices["CARR"]
    fwd = s[s.index > pd.Timestamp("2026-08-07")]
    fill_ts = fwd.index[0]
    w = s[s.index <= fill_ts + pd.Timedelta(days=5)]
    assert row["subject_ret"] == pytest.approx(
        round(float(w.iloc[-1]) / float(fwd.iloc[0]) - 1.0, 6))


def test_legacy_rows_carry_no_clock_stamp_and_read_as_the_legacy_basis(prices, tmp_path):
    c = _claim()
    row = q.grade_claim({**c, "claim_id": "cid-legacy2"}, root=tmp_path,
                        today=date(2026, 9, 30))[0]
    assert "clock_version" not in row and "horizon_unit" not in row
    assert q.grade_clock_basis(row) == q.CLOCK_LEGACY
    # A pre-existing grades.jsonl row (no stamp at all) reads the same way.
    assert q.grade_clock_basis({"horizon_d": 21, "excess": 0.01}) == q.CLOCK_LEGACY


def test_an_unrecognised_unit_is_rejected_not_silently_taken_as_legacy():
    """Fail closed: a typo'd unit must not sail through as a legacy claim and
    quietly grade on the old clock."""
    c = _claim()
    c["horizon_unit"] = "business_days"
    ok, reason = q._validate_claim(c)
    assert not ok and "horizon_unit" in reason
    with pytest.raises(ValueError):
        q.resolve_horizon_window("2026-08-07", 5, "business_days")


# --------------------------------------------------------------------------- #
# ACCEPTANCE 5 — different clocks cannot be pooled
# --------------------------------------------------------------------------- #
def _grade_row(basis_unit, *, cid, excess, hit):
    row = {"claim_id": cid, "horizon_d": 21, "excess": excess, "hit": hit}
    if basis_unit is not None:
        row["horizon_unit"] = basis_unit
        row["clock_version"] = q.CLOCK_V1
    return row


def test_require_single_clock_refuses_a_mixed_set():
    rows = [_grade_row(None, cid="a", excess=0.01, hit=True),
            _grade_row(q.HORIZON_UNIT_TRADING, cid="b", excess=0.01, hit=True)]
    assert q.require_single_clock(rows[:1]) == q.CLOCK_LEGACY
    assert q.require_single_clock(rows[1:]) == f"{q.CLOCK_V1}:{q.HORIZON_UNIT_TRADING}"
    with pytest.raises(q.HorizonClockMismatch):
        q.require_single_clock(rows)


def test_aggregate_is_fail_closed_on_a_mixed_set():
    """The refusal lives at the aggregation primitive, not in caller etiquette:
    a caller that never heard of the clock cannot blend the two bases."""
    claims = [{"claim_id": "a", "desk": "d", "claim_family": "f", "asof": "2026-01-05"},
              {"claim_id": "b", "desk": "d", "claim_family": "f", "asof": "2026-01-06"}]
    grades = [_grade_row(None, cid="a", excess=0.01, hit=True),
              _grade_row(q.HORIZON_UNIT_TRADING, cid="b", excess=0.02, hit=True)]
    with pytest.raises(q.HorizonClockMismatch):
        q._aggregate(claims, grades, "family", 21)
    # ...but each basis on its own aggregates normally.
    legacy = q._aggregate(claims, grades, "family", 21, clock_basis=q.CLOCK_LEGACY)
    assert legacy["f"]["n_obs"] == 1


def _mixed_family(monkeypatch, n_legacy: int, n_v1: int, *, v1_unit=None):
    """A family whose rows straddle the legacy clock and ONE explicit clock.
    Every row is a hit on its own distinct asof, so n_dates == row count."""
    v1_unit = v1_unit or q.HORIZON_UNIT_TRADING
    claims, grades = [], []
    for i in range(n_legacy):
        cid = f"L{i}"
        claims.append({"claim_id": cid, "desk": "d", "claim_family": "f",
                       "asof": (date(2025, 1, 1) + timedelta(days=i)).isoformat(),
                       "is_placebo": False})
        grades.append(_grade_row(None, cid=cid, excess=0.05, hit=True))
    for i in range(n_v1):
        cid = f"V{i}"
        claims.append({"claim_id": cid, "desk": "d", "claim_family": "f",
                       "asof": (date(2026, 1, 1) + timedelta(days=i)).isoformat(),
                       "is_placebo": False})
        grades.append(_grade_row(v1_unit, cid=cid, excess=0.05, hit=True))
    monkeypatch.setattr(q, "load_claims", lambda root=None: claims)
    monkeypatch.setattr(q, "load_grades", lambda root=None: grades)
    return claims, grades


def test_promotion_evaluates_inside_the_explicit_basis_never_pooling(tmp_path, monkeypatch):
    """AUTHORITY rides ONE clock and counts nothing else.

    40 legacy dates + 26 explicit-clock dates: the gate must report 26 (the
    explicit basis alone), NOT 66 (pooled) and NOT 40 (the bigger pile). The
    legacy history is excluded by name in the reason, not silently dropped."""
    _mixed_family(monkeypatch, n_legacy=40, n_v1=26)
    res = q.promotion_check("f", 21, root=tmp_path)

    assert res.clock_basis == f"{q.CLOCK_V1}:{q.HORIZON_UNIT_TRADING}"
    assert res.n_dates == 26, "the legacy pile must not be counted"
    assert res.eligible is True
    assert q.CLOCK_LEGACY in res.reason and "NOT pooled" in res.reason


def test_promotion_is_reachable_again_after_a_clock_change(tmp_path, monkeypatch):
    """MAJOR 1 — the migration TERMINATES.

    The same family walked forward: at the split it is ineligible for the
    ordinary reason (too few dates ON THE NEW CLOCK), and it becomes promotable
    once the explicit-clock corpus alone clears the 25-date bar. The legacy pile
    is identical in both frames, so what moves the verdict is accrual on the new
    clock — not a pooling concession."""
    _mixed_family(monkeypatch, n_legacy=59, n_v1=3)
    early = q.promotion_check("f", 21, root=tmp_path)
    assert early.eligible is False
    assert early.current_state != q.STATE_MIXED_CLOCK, \
        "a permanently-mixed verdict is the defect this fixes"
    assert early.n_dates == 3 and "n_dates=3 < 25" in early.reason

    _mixed_family(monkeypatch, n_legacy=59, n_v1=25)
    later = q.promotion_check("f", 21, root=tmp_path)
    assert later.eligible is True and later.n_dates == 25


def test_promotion_can_still_be_asked_what_the_legacy_history_said(tmp_path, monkeypatch):
    """The legacy numbers are excluded from AUTHORITY, not deleted: an explicit
    `clock_basis` still evaluates them, labelled as such."""
    _mixed_family(monkeypatch, n_legacy=40, n_v1=3)
    res = q.promotion_check("f", 21, root=tmp_path, clock_basis=q.CLOCK_LEGACY)
    assert res.clock_basis == q.CLOCK_LEGACY and res.n_dates == 40


def test_promotion_refuses_only_when_two_EXPLICIT_clocks_collide(tmp_path, monkeypatch):
    """The one genuinely ambiguous case survives as a refusal: a family holding
    both trading_days and calendar_days rows at one horizon has no non-arbitrary
    basis to promote on, so the gate says MIXED_CLOCK instead of picking."""
    claims = [{"claim_id": f"c{i}", "desk": "d", "claim_family": "f",
               "asof": (date(2026, 1, 1) + timedelta(days=i)).isoformat(),
               "is_placebo": False} for i in range(30)]
    grades = [_grade_row(q.HORIZON_UNIT_TRADING if i % 2 else q.HORIZON_UNIT_CALENDAR,
                         cid=f"c{i}", excess=0.05, hit=True) for i in range(30)]
    monkeypatch.setattr(q, "load_claims", lambda root=None: claims)
    monkeypatch.setattr(q, "load_grades", lambda root=None: grades)

    res = q.promotion_check("f", 21, root=tmp_path)
    assert res.eligible is False
    assert res.current_state == q.STATE_MIXED_CLOCK
    assert res.clock_basis is None and "refusing to pool" in res.reason
    # Negative control: the SAME rows on one explicit basis clear the gate, so
    # the refusal above is the clock check firing, not an unrelated failure.
    monkeypatch.setattr(q, "load_grades",
                        lambda root=None: [_grade_row(q.HORIZON_UNIT_TRADING,
                                                      cid=f"c{i}", excess=0.05,
                                                      hit=True) for i in range(30)])
    assert q.promotion_check("f", 21, root=tmp_path).eligible is True


def test_track_record_publishes_one_basis_labelled_never_a_blend(tmp_path, monkeypatch):
    claims = [{"claim_id": f"c{i}", "desk": "d", "claim_family": "f",
               "asof": f"2026-01-{i + 1:02d}", "is_placebo": False}
              for i in range(4)]
    grades = [
        _grade_row(None, cid="c0", excess=0.01, hit=True),
        _grade_row(None, cid="c1", excess=0.01, hit=True),
        _grade_row(None, cid="c2", excess=0.01, hit=True),
        _grade_row(q.HORIZON_UNIT_TRADING, cid="c3", excess=-0.09, hit=False),
    ]
    monkeypatch.setattr(q, "load_claims", lambda root=None: claims)
    monkeypatch.setattr(q, "load_grades", lambda root=None: grades)

    tr = q.compute_track_record(root=tmp_path)
    cell = tr["by_desk"]["d"]["21"]
    assert cell["pooling_refused"] is True
    assert cell["clock_basis"] == q.CLOCK_LEGACY          # 3 dates beats 1
    assert cell["clock_bases"] == [f"{q.CLOCK_V1}:{q.HORIZON_UNIT_TRADING}",
                                   q.CLOCK_LEGACY]
    assert cell["n_obs"] == 3, "the published cell is ONE basis, never the union"
    assert cell["hit_rate"] == 1.0, "the losing new-clock row must not bleed in"

    # the excluded basis is printed, not hidden
    other = tr["by_clock_basis"][f"{q.CLOCK_V1}:{q.HORIZON_UNIT_TRADING}"]
    assert other["by_desk"]["d"]["21"]["n_obs"] == 1
    assert tr["counts"]["grades_by_clock_basis"] == {
        q.CLOCK_LEGACY: 3, f"{q.CLOCK_V1}:{q.HORIZON_UNIT_TRADING}": 1}


def test_single_basis_track_record_is_unchanged_by_the_split(tmp_path, monkeypatch):
    """Negative control for the refusal machinery: while only ONE basis exists —
    which is every row in the live store today — the published cell carries no
    refusal marker and reads exactly as it did before P0a."""
    claims = [{"claim_id": f"c{i}", "desk": "d", "claim_family": "f",
               "asof": f"2026-01-{i + 1:02d}", "is_placebo": False}
              for i in range(3)]
    grades = [_grade_row(None, cid=f"c{i}", excess=0.01, hit=True) for i in range(3)]
    monkeypatch.setattr(q, "load_claims", lambda root=None: claims)
    monkeypatch.setattr(q, "load_grades", lambda root=None: grades)

    cell = q.compute_track_record(root=tmp_path)["by_desk"]["d"]["21"]
    assert "pooling_refused" not in cell and "clock_basis" not in cell
    assert cell["n_obs"] == 3 and cell["hit_rate"] == 1.0


# --------------------------------------------------------------------------- #
# resolver fail-closed edges
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("horizon_d", [0, -1, "x", None])
def test_resolver_returns_none_rather_than_inventing_a_window(horizon_d):
    assert q.resolve_horizon_window("2026-08-07", horizon_d,
                                    q.HORIZON_UNIT_TRADING) is None


def test_window_is_never_graded_short(prices, tmp_path):
    """An immature window grades nothing at all rather than measuring a partial
    horizon — the same law `_fwd_ret` holds for the legacy clock."""
    c = _claim(horizon_unit=q.HORIZON_UNIT_TRADING)
    assert q.grade_claim({**c, "claim_id": "cid-early"}, root=tmp_path,
                         today=date(2026, 8, 12)) == []


def test_calendar_unit_preserves_calendar_arithmetic():
    """Contract rule 3: the calendar branch is untouched calendar math —
    fill + N days, no session snapping of the DECLARED boundary."""
    for n in (1, 7, 30, 90):
        win = q.resolve_horizon_window("2026-08-07", n, q.HORIZON_UNIT_CALENDAR)
        assert win.exit_date == win.fill_date + timedelta(days=n)


def test_resolver_refuses_anchors_outside_its_supported_range():
    """The session ruler models NO pre-2012 one-off closure (2001-09-11..14,
    2004-06-11 Reagan, 2007-01-02 Ford), so a session-counted exit before
    `CLOCK_SUPPORTED_FROM` would land late without saying so. The clock declares
    its range instead of answering outside it."""
    assert q.CLOCK_SUPPORTED_FROM == date(2012, 10, 31)
    # 2007-01-02 was a full closure (Ford) the calendar does not know about.
    assert q.resolve_horizon_window("2006-12-29", 5, q.HORIZON_UNIT_TRADING) is None
    assert q.resolve_horizon_window("2011-06-01", 5, q.HORIZON_UNIT_CALENDAR) is None
    # ...and the first supported day resolves normally.
    assert q.resolve_horizon_window(q.CLOCK_SUPPORTED_FROM, 5,
                                    q.HORIZON_UNIT_TRADING) is not None


def test_a_calendar_window_with_no_session_after_the_fill_has_no_window():
    """MINOR — maturity and the return must not disagree.

    1 calendar day from a FRIDAY fill exits on the Saturday, whose last session
    on/before is the Friday fill itself: a one-bar window. `_matured_window` used
    to call that matured while `_leg_ret_in_window` refused it on the two-bar
    guard — a window that was simultaneously ready and ungradeable. There is now
    no such window at all."""
    # asof Thu 2026-08-06 -> fill Fri 2026-08-07 -> +1 calendar day = Sat 08-08.
    assert q.resolve_horizon_window("2026-08-06", 1, q.HORIZON_UNIT_CALENDAR) is None
    # the same horizon from a Monday fill has a real second bar and resolves.
    win = q.resolve_horizon_window("2026-08-07", 1, q.HORIZON_UNIT_CALENDAR)
    assert win is not None and win.coverage_date > win.fill_date


# --------------------------------------------------------------------------- #
# MAJOR 2 — rule 5 is ENFORCED, not documented
# --------------------------------------------------------------------------- #
def _drop_bar(series: pd.Series, day: str) -> pd.Series:
    return series[series.index != pd.Timestamp(day)]


def test_a_leg_missing_the_windows_entry_bar_is_refused_not_graded_short(
        prices, tmp_path, monkeypatch):
    """The window is 2026-08-10..2026-08-17. Delete the CONTROL leg's entry bar
    and the naive slice would start on 08-11 — a 4-session window graded under a
    5-session label, for one leg only. Rule 5 says every leg is measured over the
    SAME window, so the leg is refused instead."""
    win = q.resolve_horizon_window("2026-08-07", 5, q.HORIZON_UNIT_TRADING)
    assert win.fill_date == date(2026, 8, 10)

    holed = dict(prices)
    holed["XLI"] = _drop_bar(prices["XLI"], "2026-08-10")
    monkeypatch.setattr("engine.ai_desk._close_series",
                        lambda ticker, root: holed.get(ticker))

    # The hole is real: the store still REACHES the coverage date, so maturity
    # passes and only the endpoint check can catch this.
    assert holed["XLI"].index.max() >= pd.Timestamp(win.coverage_date)
    assert q._leg_ret_in_window("XLI", tmp_path, win) is None
    assert q._leg_ret_in_window("CARR", tmp_path, win) is not None   # control

    c = _claim(horizon_unit=q.HORIZON_UNIT_TRADING)
    row = q.grade_claim({**c, "claim_id": "cid-hole-in"}, root=tmp_path,
                        today=date(2026, 9, 30))[0]
    assert row["control_ret"] is None, "a short control leg must not be graded"


def test_a_leg_missing_the_windows_exit_bar_is_refused_not_graded_short(
        prices, tmp_path, monkeypatch):
    """The mirror case: without the 08-17 exit bar the slice would end on 08-14
    and publish a 4-session return under the 5-session label. Refused."""
    win = q.resolve_horizon_window("2026-08-07", 5, q.HORIZON_UNIT_TRADING)
    assert win.exit_date == date(2026, 8, 17)

    holed = dict(prices)
    holed["CARR"] = _drop_bar(prices["CARR"], "2026-08-17")
    monkeypatch.setattr("engine.ai_desk._close_series",
                        lambda ticker, root: holed.get(ticker))

    assert holed["CARR"].index.max() > pd.Timestamp(win.coverage_date)
    assert q._leg_ret_in_window("CARR", tmp_path, win) is None
    # The SUBJECT leg being refused means the whole claim grades nothing at this
    # horizon — never a partial window under the declared label.
    c = _claim(horizon_unit=q.HORIZON_UNIT_TRADING)
    assert q.grade_claim({**c, "claim_id": "cid-hole-out"}, root=tmp_path,
                         today=date(2026, 9, 30)) == []


def test_an_intact_window_still_grades(prices, tmp_path):
    """Negative control for the two refusals above: with both endpoint bars
    present every leg grades, so the refusals are the endpoint check firing and
    not a blanket break."""
    win = q.resolve_horizon_window("2026-08-07", 5, q.HORIZON_UNIT_TRADING)
    for t in ("CARR", "SPY", "XLI"):
        assert q._leg_ret_in_window(t, tmp_path, win) is not None


# --------------------------------------------------------------------------- #
# MINOR — the display selection states its intent and its cost
# --------------------------------------------------------------------------- #
def test_display_selection_names_its_rule_and_prints_the_excluded_basis_size(
        tmp_path, monkeypatch):
    """The legacy basis wins straddled display cells on sample size, and will for
    a long time. That is allowed — but the cell must SAY the rule it used and how
    big the basis it dropped was, so correctly-clocked observations are never
    merely invisible."""
    claims = [{"claim_id": f"c{i}", "desk": "d", "claim_family": "f",
               "asof": (date(2026, 1, 1) + timedelta(days=i)).isoformat(),
               "is_placebo": False} for i in range(4)]
    grades = [_grade_row(None, cid="c0", excess=0.01, hit=True),
              _grade_row(None, cid="c1", excess=0.01, hit=True),
              _grade_row(None, cid="c2", excess=0.01, hit=True),
              _grade_row(q.HORIZON_UNIT_TRADING, cid="c3", excess=-0.09, hit=False)]
    monkeypatch.setattr(q, "load_claims", lambda root=None: claims)
    monkeypatch.setattr(q, "load_grades", lambda root=None: grades)

    cell = q.compute_track_record(root=tmp_path)["by_desk"]["d"]["21"]
    assert cell["clock_basis_selection"] == q.CLOCK_DISPLAY_SELECTION
    assert cell["clock_bases_n_dates"] == {
        q.CLOCK_LEGACY: 3, f"{q.CLOCK_V1}:{q.HORIZON_UNIT_TRADING}": 1}


# --------------------------------------------------------------------------- #
# BLOCKER 1 — the NIGHTLY promotion-readiness post-step must not raise
# --------------------------------------------------------------------------- #
def _write_store(root, claims, grades):
    d = root / "data" / "qledger"
    d.mkdir(parents=True, exist_ok=True)
    for name, rows in (("claims.jsonl", claims), ("grades.jsonl", grades)):
        with (d / name).open("w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")


def _mixed_store_rows(n_legacy: int, n_v1: int):
    claims, grades = [], []
    for tag, n, unit, base in (("L", n_legacy, None, date(2025, 1, 1)),
                               ("V", n_v1, q.HORIZON_UNIT_TRADING, date(2026, 1, 1))):
        for i in range(n):
            cid = f"{tag}{i}"
            claims.append({"claim_id": cid, "desk": "d", "claim_family": "f",
                           "asof": (base + timedelta(days=i)).isoformat(),
                           "is_placebo": False, "status": "open"})
            row = {"claim_id": cid, "horizon_d": 21, "excess": 0.05, "hit": True,
                   "subject_ret": 0.06, "bench_ret": 0.01, "control_ret": 0.01,
                   "graded_at": "2026-08-13T00:00:00+00:00"}
            if unit is not None:
                row["horizon_unit"] = unit
                row["clock_version"] = q.CLOCK_V1
            grades.append(row)
    return claims, grades


def test_nightly_promotion_readiness_step_survives_a_mixed_clock_corpus(tmp_path):
    """BLOCKER 1 — `scripts/grade_qledger.compute_promotion_readiness` is a
    nightly post-step and called `_aggregate` with NO clock basis, i.e. on the
    fail-closed default. The first night any ladder family held both bases it
    would have raised `HorizonClockMismatch` and taken the step down.

    The corpus below is exactly that state. The step must run clean and report
    WHICH clock each row was measured on."""
    import scripts.grade_qledger as grader

    claims, grades = _mixed_store_rows(n_legacy=30, n_v1=26)
    _write_store(tmp_path, claims, grades)

    # The defect, pinned: the un-basised call this step used to make DOES raise
    # on this corpus, so the assertion below is not vacuous.
    with pytest.raises(q.HorizonClockMismatch):
        q._aggregate(claims, grades, "family", 21)

    out = grader.compute_promotion_readiness(tmp_path, families=["f"])
    cell = out["f"]["21"]
    assert cell["clock_basis"] == f"{q.CLOCK_V1}:{q.HORIZON_UNIT_TRADING}"
    assert cell["n_dates"] == 26 and cell["ready"] is True
    # the headline stats describe the SAME basis the gate used, never a blend
    assert cell["hit_rate"] == 1.0


def test_readiness_reports_a_null_rather_than_a_pooled_number_when_ambiguous(tmp_path):
    """Two EXPLICIT clocks in one family: the gate refuses, so the panel must
    print nulls, not numbers borrowed from one of them."""
    import scripts.grade_qledger as grader

    claims, grades = [], []
    for i in range(30):
        cid = f"c{i}"
        claims.append({"claim_id": cid, "desk": "d", "claim_family": "f",
                       "asof": (date(2026, 1, 1) + timedelta(days=i)).isoformat(),
                       "is_placebo": False, "status": "open"})
        grades.append({"claim_id": cid, "horizon_d": 21, "excess": 0.05, "hit": True,
                       "clock_version": q.CLOCK_V1,
                       "horizon_unit": (q.HORIZON_UNIT_TRADING if i % 2
                                        else q.HORIZON_UNIT_CALENDAR)})
    _write_store(tmp_path, claims, grades)

    cell = grader.compute_promotion_readiness(tmp_path, families=["f"])["f"]["21"]
    assert cell["clock_basis"] is None
    assert cell["hit_rate"] is None and cell["excess_mean"] is None
    assert cell["ready"] is False


# --------------------------------------------------------------------------- #
# BLOCKER 2 — no bypass: a caller-supplied check_by does not beat the resolver
# --------------------------------------------------------------------------- #
def _lane_root(tmp_path, source_check_by: str) -> Path:
    """The `backfill_qledger_us` altdata + policy source ledgers, shaped exactly
    as the live lanes read them — including the source's own `check_by`, which
    upstream computed as `asof + BusinessDay(horizon)` (`ai_desk._check_by`)."""
    rows = {
        "data/altdata/theses.jsonl": [{
            "id": "2026-06-19-CARR-altconv",
            "ticker": "CARR",
            "state_asof": "2026-06-19",
            "claim_family": "altdata",
            "lean": "overweight",
            "conviction": "low",
            "horizon_d": 63,
            "channels": [],
            "falsifier": {"text": "CARR fails to beat SPY.",
                          "check": {"kind": "rel_return", "subject_ticker": "CARR",
                                    "vs": "SPY", "op": "<", "threshold": -0.05,
                                    "horizon_d": 63}},
            "check_by": source_check_by,
            "entry_levels": {"CARR": 71.81, "SPY": 746.74},
            "status": "open",
        }],
        "data/policy_intent/theses.jsonl": [{
            "id": "2026-06-19-policy-CARR",
            "state_asof": "2026-06-19",
            "actor": "admin",
            "subject": "CARR",
            "lean": "overweight",
            "conviction": "low",
            "horizon_d": 63,
            "falsifier": {"text": "CARR underperforms SPY.",
                          "check": {"kind": "rel_return", "subject_ticker": "CARR",
                                    "vs": "SPY", "op": "<", "threshold": -0.05,
                                    "horizon_d": 63}},
            "check_by": source_check_by,
            "entry_levels": {"CARR": 71.81, "SPY": 746.74},
            "status": "open",
        }],
    }
    for rel, payload in rows.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as fh:
            for r in payload:
                fh.write(json.dumps(r) + "\n")
    return tmp_path


@pytest.mark.parametrize("unit", [q.HORIZON_UNIT_TRADING, q.HORIZON_UNIT_CALENDAR])
def test_backfill_us_lane_check_by_is_the_exit_the_grader_resolves(
        prices, tmp_path, monkeypatch, unit):
    """BLOCKER 2 — the headline guarantee held on the two highest-volume lanes.

    `backfill_altdata` and `backfill_policy` both pass a `check_by` read straight
    off their source thesis. That value SHORT-CIRCUITED the resolver, so on
    exactly the lanes carrying the most claims the falsifier deadline a human
    read was still the old holiday-blind `asof + BusinessDay(h)` while the grader
    measured somewhere else. The resolver now always wins and the source value is
    kept as `check_by_source` — proven here end-to-end on real lane rows, under
    BOTH units (the unit constant the lanes pass is swapped to exercise the same
    lane code on the calendar clock; the lanes themselves declare trading_days).
    """
    import scripts.backfill_qledger_us as lane

    source_check_by = (pd.Timestamp("2026-06-19")
                       + pd.offsets.BusinessDay(63)).date().isoformat()
    root = _lane_root(tmp_path, source_check_by)
    monkeypatch.setattr(lane, "HORIZON_UNIT_TRADING", unit)
    monkeypatch.setattr(lane, "_close_series",
                        lambda ticker, root=None: prices.get(ticker))

    assert lane.backfill_altdata(root) == 1
    assert lane.backfill_policy(root) == 1

    claims = [c for c in q.load_claims(root) if not c.get("is_placebo")]
    assert {c["desk"] for c in claims} == {"altdata", "policy"}

    for c in claims:
        assert c["horizon_unit"] == unit
        # 1. the source's value did NOT win, and was not thrown away either
        assert c["check_by"] != source_check_by
        assert c["check_by_source"] == source_check_by
        # 2. check_by IS the resolver's exit, off the post-embargo anchor
        #    (_TQ_ALTDATA/_TQ_POLICY are DISCLOSURE_DATE: +1bd)
        win = q.resolve_horizon_window(
            q._entry_anchor(c["asof"], c["timestamp_quality"]),
            c["horizon_d"], unit)
        assert c["check_by"] == win.exit_date.isoformat()
        # 3. and it is the exit the GRADER actually measured to
        rows = q.grade_claim(c, root=root, today=date(2026, 12, 1))
        own = [r for r in rows if r["horizon_d"] == c["horizon_d"]]
        assert own, f"{c['desk']}: claim's own horizon must grade"
        assert own[0]["clock_exit_date"] == c["check_by"]


def test_a_supplied_check_by_still_passes_through_on_a_legacy_claim():
    """The override is scoped to claims that DECLARE a unit. A legacy (unitless)
    claim is byte-for-byte unchanged — including a caller-supplied deadline."""
    c = _claim(check_by="2026-12-31")
    assert "horizon_unit" not in c
    assert c["check_by"] == "2026-12-31" and "check_by_source" not in c
