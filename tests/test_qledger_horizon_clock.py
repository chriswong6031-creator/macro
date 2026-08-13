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
def _grade_row(basis_unit, *, cid, excess, hit, market=q.MARKET_US):
    row = {"claim_id": cid, "horizon_d": 21, "excess": excess, "hit": hit}
    if basis_unit is not None:
        row["horizon_unit"] = basis_unit
        row["clock_version"] = q.CLOCK_V1
        row["clock_market"] = market
    return row


def _v1(unit=q.HORIZON_UNIT_TRADING, market=q.MARKET_US):
    """The explicit-clock basis key, built by the module's own constructor so a
    later segment addition cannot leave a second spelling in the tests."""
    return q.clock_basis_key(q.CLOCK_V1, unit, market)


def test_require_single_clock_refuses_a_mixed_set():
    rows = [_grade_row(None, cid="a", excess=0.01, hit=True),
            _grade_row(q.HORIZON_UNIT_TRADING, cid="b", excess=0.01, hit=True)]
    assert q.require_single_clock(rows[:1]) == q.CLOCK_LEGACY
    assert q.require_single_clock(rows[1:]) == _v1()
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

    assert res.clock_basis == _v1()
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
    assert cell["clock_bases"] == [_v1(),
                                   q.CLOCK_LEGACY]
    assert cell["n_obs"] == 3, "the published cell is ONE basis, never the union"
    assert cell["hit_rate"] == 1.0, "the losing new-clock row must not bleed in"

    # the excluded basis is printed, not hidden
    other = tr["by_clock_basis"][_v1()]
    assert other["by_desk"]["d"]["21"]["n_obs"] == 1
    assert tr["counts"]["grades_by_clock_basis"] == {
        q.CLOCK_LEGACY: 3, _v1(): 1}


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


def test_a_refused_control_leg_refuses_the_ROW_not_just_the_control_number(
        prices, tmp_path, monkeypatch):
    """MAJOR 1 — rule 5 was enforced on subject and bench but NOT on the control.

    The window is 2026-08-10..2026-08-17. Delete the CONTROL leg's entry bar and
    the naive slice would start on 08-11 — a 4-session window graded under a
    5-session label, for one leg only. The endpoint assertion caught that and
    returned None... which `grade_claim` then wrote out as `control_ret: null`,
    a value that in this store means "this claim declared NO control". So the
    row published as if it had never had a control leg, and the §3 promotion
    gate — whose bar is excess-vs-CONTROL — fell through to its primary-hit
    fallback on exactly the claims whose control window was broken. A leg
    silently receiving a different window is the one thing rule 5 forbids.

    The row is now refused whole, like a refused subject or bench.
    """
    win = q.resolve_horizon_window("2026-08-07", 5, q.HORIZON_UNIT_TRADING)
    assert win.fill_date == date(2026, 8, 10)

    holed = dict(prices)
    holed["XLI"] = _drop_bar(prices["XLI"], "2026-08-10")
    monkeypatch.setattr("engine.ai_desk._close_series",
                        lambda ticker, root: holed.get(ticker))

    # The hole is real: the store still REACHES the coverage date, so maturity
    # passes and only the endpoint check can catch this.
    assert holed["XLI"].index.max() >= pd.Timestamp(win.coverage_date)
    assert q._leg_ret_in_window("XLI", tmp_path, win) is None       # control
    assert q._leg_ret_in_window("CARR", tmp_path, win) is not None  # subject
    assert q._leg_ret_in_window("SPY", tmp_path, win) is not None   # bench

    c = _claim(horizon_unit=q.HORIZON_UNIT_TRADING)
    assert c["control"] == "XLI", "fixture must actually declare a control"
    assert q.grade_claim({**c, "claim_id": "cid-hole-in"}, root=tmp_path,
                         today=date(2026, 9, 30)) == [], \
        "a control that cannot be measured over the shared window refuses the row"


def test_a_claim_with_no_control_still_grades_with_a_null_control(
        prices, tmp_path):
    """Negative control for the refusal above: `control_ret: null` must keep
    meaning 'no control was declared'. If the fix had been implemented by
    refusing every null control, this claim would stop grading — and the two
    states (no control / broken control) would still be indistinguishable, just
    in the other direction."""
    c = _claim(horizon_unit=q.HORIZON_UNIT_TRADING, sector=None)
    assert c["control"] is None
    rows = q.grade_claim({**c, "claim_id": "cid-no-ctrl"}, root=tmp_path,
                         today=date(2026, 9, 30))
    assert len(rows) == 1 and rows[0]["control_ret"] is None


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
        q.CLOCK_LEGACY: 3, _v1(): 1}


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
                row["clock_market"] = q.MARKET_US
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
    assert cell["clock_basis"] == _v1()
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


# --------------------------------------------------------------------------- #
# BLOCKER (round 3) — the resolver DISPATCHES on the market the claim is priced in
# --------------------------------------------------------------------------- #
# The first cut of this clock resolved every claim through lib.nyse_calendar.
# 5,726 live claims (china_news, cn_importance_v0, cn_importance_v0_pit,
# china_special_sits) are priced on A-shares, whose exchange keeps a different
# calendar — so those claims got NYSE fill/coverage dates that the rule-5
# endpoint assertion can never satisfy. Two measured consequences on the live
# corpus: 31.9% of CN windows were the wrong LENGTH in A-share sessions, and on a
# 2025-2026 anchor sweep 5.9% of h=21 CN windows land an endpoint on a CN-only
# closure and are therefore PERMANENTLY ungradeable.
def _cn_session_count(a: date, b: date) -> int:
    from lib import cn_calendar
    n, d = 0, a
    while d <= b:
        if cn_calendar.is_session(d):
            n += 1
        d += timedelta(days=1)
    return n


def test_a_cn_claim_resolves_on_the_cn_calendar_across_golden_week():
    """National Day Golden Week (Oct 1-7) closes the mainland exchanges and is a
    normal trading week in New York. From a 2026-09-28 anchor, 5 A-share sessions
    end on 2026-10-13; 5 NYSE sessions end on 2026-10-06 — a date INSIDE Golden
    Week, with no A-share bar, so a CN claim resolved on NYSE could never grade
    at all: rule 5's endpoint assertion refuses it forever."""
    from lib import cn_calendar, nyse_calendar

    cn_win = q.resolve_horizon_window("2026-09-28", 5, q.HORIZON_UNIT_TRADING,
                                      q.MARKET_CN)
    us_win = q.resolve_horizon_window("2026-09-28", 5, q.HORIZON_UNIT_TRADING,
                                      q.MARKET_US)

    assert cn_win.market == q.MARKET_CN and us_win.market == q.MARKET_US
    assert cn_win.exit_date == date(2026, 10, 13)
    assert us_win.exit_date == date(2026, 10, 6)
    assert cn_win.exit_date != us_win.exit_date

    # the NYSE answer is not merely different, it is UNREACHABLE on this market
    assert not cn_calendar.is_session(us_win.exit_date)
    assert cn_calendar.is_session(cn_win.exit_date)
    # ...and Golden Week is a full trading week in New York, so the US answer is
    # right for the US and wrong here — one hardcoded calendar cannot serve both.
    assert nyse_calendar.is_session(us_win.exit_date)
    # the window really is 5 A-share sessions past the fill (fill + 5)
    assert _cn_session_count(cn_win.fill_date, cn_win.coverage_date) == 6


def test_a_cn_claim_window_is_the_declared_number_of_a_share_sessions():
    """The quieter half of the defect: even when the NYSE endpoints happen to be
    A-share sessions, a US-only closure inside the span (Labor Day 2026-09-07)
    makes the window the wrong LENGTH — 21 declared sessions spanning 20 real
    ones. Measured over the live corpus this hit 31.9% of CN windows."""
    us_win = q.resolve_horizon_window("2026-08-12", 21, q.HORIZON_UNIT_TRADING,
                                      q.MARKET_US)
    cn_win = q.resolve_horizon_window("2026-08-12", 21, q.HORIZON_UNIT_TRADING,
                                      q.MARKET_CN)
    from lib import cn_calendar
    # both NYSE endpoints ARE A-share sessions here, so the endpoint assertion
    # cannot catch this one — it grades, at the wrong length.
    assert cn_calendar.is_session(us_win.fill_date)
    assert cn_calendar.is_session(us_win.coverage_date)
    # Labor Day 2026-09-07 is a NYSE closure and a normal A-share session, so the
    # NYSE-resolved "21 trading days" spans 22 A-share sessions past the fill.
    assert _cn_session_count(us_win.fill_date, us_win.coverage_date) == 23
    assert _cn_session_count(cn_win.fill_date, cn_win.coverage_date) == 22


def test_no_live_cn_lane_window_is_ungradeable_or_mis_lengthed_after_dispatch():
    """The corpus-shaped proof, run on SYNTHESISED claims spanning the live CN
    lanes' asof range (2026-06-20..2026-08-12) plus a Golden Week straddle —
    never on data/qledger, which the nightly appends to.

    Under the NYSE resolver these windows are 21-or-22 A-share sessions and some
    land an endpoint on a CN-only closure. Under dispatch, every window is
    exactly its declared number of A-share sessions and both endpoints are
    A-share sessions. Zero, not 'fewer'."""
    from lib import cn_calendar

    anchors = [date(2026, 6, 20) + timedelta(days=i) for i in range(0, 54)]
    anchors += [date(2026, 9, 20) + timedelta(days=i) for i in range(0, 20)]

    us_bad = cn_bad = total = 0
    for a in anchors:
        for h in (5, 21):
            total += 1
            us = q.resolve_horizon_window(a.isoformat(), h,
                                          q.HORIZON_UNIT_TRADING, q.MARKET_US)
            cn = q.resolve_horizon_window(a.isoformat(), h,
                                          q.HORIZON_UNIT_TRADING, q.MARKET_CN)
            if (us is None
                    or not cn_calendar.is_session(us.fill_date)
                    or not cn_calendar.is_session(us.coverage_date)
                    or _cn_session_count(us.fill_date, us.coverage_date) != h + 1):
                us_bad += 1
            assert cn is not None
            assert cn_calendar.is_session(cn.fill_date)
            assert cn_calendar.is_session(cn.coverage_date)
            if _cn_session_count(cn.fill_date, cn.coverage_date) != h + 1:
                cn_bad += 1

    assert cn_bad == 0, "every dispatched CN window is its declared length"
    assert us_bad > 0.2 * total, (
        f"the pre-fix control must still be broken at scale: {us_bad}/{total}")


def test_an_hk_claim_resolves_on_the_hk_calendar():
    """The HK mirror, and the sharpest version of it: the FILL diverges, not just
    the exit. Chung Yeung 2026-10-19 closes HKEX and is an ordinary NYSE session,
    so an HK claim anchored on 2026-10-16 gets an NYSE fill of 2026-10-19 — a day
    with no HKEX bar. Rule 5 asserts the fill bar exists, so that window is
    permanently ungradeable, exactly as the CN case."""
    from lib import hk_calendar, nyse_calendar

    hk_win = q.resolve_horizon_window("2026-10-16", 3, q.HORIZON_UNIT_TRADING,
                                      q.MARKET_HK)
    us_win = q.resolve_horizon_window("2026-10-16", 3, q.HORIZON_UNIT_TRADING,
                                      q.MARKET_US)
    assert not hk_calendar.is_session(date(2026, 10, 19))
    assert nyse_calendar.is_session(date(2026, 10, 19))

    assert us_win.fill_date == date(2026, 10, 19)
    assert not hk_calendar.is_session(us_win.fill_date)   # unreachable bar
    assert hk_win.fill_date == date(2026, 10, 20)
    assert hk_calendar.is_session(hk_win.fill_date)
    assert hk_calendar.is_session(hk_win.exit_date)
    assert hk_win.exit_date != us_win.exit_date
    assert hk_win.market == q.MARKET_HK


def test_the_market_is_derived_from_the_claim_not_passed_by_the_caller(
        monkeypatch, tmp_path):
    """End to end: a CN claim built by `make_claim` carries a CN-resolved
    check_by, and the grader measures to that same date — with no caller
    anywhere naming a market."""
    from lib import cn_calendar

    c = q.make_claim(desk="cn_importance_v0", asof="2026-09-28",
                     scope_type="entity", scope_key="300024.SZ",
                     direction=1, horizon_d=5,
                     horizon_unit=q.HORIZON_UNIT_TRADING,
                     bench="510300.SS", timestamp_quality="CRAWL_BOUNDED")
    assert c["clock_market"] == q.MARKET_CN
    assert c["check_by"] == "2026-10-13"
    assert cn_calendar.is_session(date.fromisoformat(c["check_by"]))

    idx = pd.DatetimeIndex([pd.Timestamp(d) for d in
                            (date(2026, 9, 1) + timedelta(days=i)
                             for i in range(120))
                            if cn_calendar.is_session(d.date()
                                                      if hasattr(d, "date") else d)])
    store = {t: pd.Series([100.0 * (1.01 ** i) for i in range(len(idx))], index=idx)
             for t in ("300024.SZ", "510300.SS")}
    monkeypatch.setattr("engine.ai_desk._close_series",
                        lambda ticker, root: store.get(ticker))
    rows = q.grade_claim({**c, "claim_id": "cid-cn"}, root=tmp_path,
                         today=date(2026, 12, 1))
    assert len(rows) == 1
    assert rows[0]["clock_exit_date"] == c["check_by"]
    assert rows[0]["clock_market"] == q.MARKET_CN


# --------------------------------------------------------------------------- #
# BLOCKER (round 3) — an undeterminable market FAILS CLOSED
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("scope_key, bench, expect", [
    # a real live exemplar: four china_special_sits claims are priced on Beijing
    # Stock Exchange tickers, a suffix engine.session_anchor.MARKET_SUFFIX does
    # not carry — so `market_for_ticker` calls them US and they would have graded
    # Beijing names on NYSE sessions. It is in the ENUMERATED deny-list, so the
    # refusal names the exchange rather than shrugging at the suffix.
    ("920007.BJ", "510300.SS", q.MARKET_UNDETERMINED_FOREIGN_EXCHANGE),
    # a suffix in NEITHER house table: no venue claimed, still refused.
    ("FOO.ZZZ", "SPY", q.MARKET_UNDETERMINED_UNKNOWN_SUFFIX),
    # a single-letter suffix on a symbol the house US-equity gate rejects: the
    # share-class reading is corroborated, never assumed.
    ("600519.Q", "SPY", q.MARKET_UNDETERMINED_NOT_A_US_SYMBOL),
    # legs on two markets: no single session ruler exists, and picking one hands
    # two legs different horizon lengths (the exact rule-5 failure).
    ("300024.SZ", "SPY", q.MARKET_UNDETERMINED_MIXED),
    # a market the house table CAN name but this repo has no calendar for.
    ("SHOP.TO", "XIU.TO", q.MARKET_UNDETERMINED_NO_CALENDAR),
])
def test_an_undeterminable_market_fails_closed_and_says_why(scope_key, bench, expect):
    claim = {"scope": {"type": "entity", "key": scope_key}, "bench": bench,
             "control": None}
    market, reason = q.resolve_claim_market(claim)
    assert market is None
    assert reason.startswith(expect), reason


def test_the_house_classifier_would_have_answered_us_for_all_three():
    """The refusals above are not the house classifier's answer — they are a
    deliberate narrowing of it. `session_anchor.market_for_ticker` resolves an
    unmapped suffix to US openly (its R3 ruling), which is harmless for bucket
    edges and NOT harmless for a graded exit."""
    from engine.session_anchor import market_for_ticker
    assert market_for_ticker("920007.BJ") == "US"
    # and the suffix table itself is REUSED, not re-invented
    assert q._ticker_market("300024.SZ")[0] == market_for_ticker("300024.SZ") == "CN"
    assert q._ticker_market("0700.HK")[0] == market_for_ticker("0700.HK") == "HK"


def test_a_us_share_class_ticker_is_not_mistaken_for_an_exchange_suffix():
    """`BRK.B` / `BRK.A` are 527 legs in the live store. A blanket
    'dotted suffix we cannot name -> refuse' would have failed them closed."""
    assert q._ticker_market("BRK.B") == (q.MARKET_US, "")
    assert q._ticker_market("BRK.A") == (q.MARKET_US, "")
    assert q.resolve_claim_market(
        {"scope": {"type": "entity", "key": "BRK.B"}, "bench": "SPY"}) == ("US", "")


def test_an_unknown_market_is_never_answered_with_another_markets_sessions():
    """The resolver refuses an unknown market key outright rather than defaulting
    — the default in its signature is for direct US callers, never a fallback."""
    with pytest.raises(ValueError):
        q.resolve_horizon_window("2026-08-07", 5, q.HORIZON_UNIT_TRADING, "CA")


def test_each_markets_supported_range_is_declared_and_enforced():
    """CN/HK carry a CEILING as well as a floor: their lunar tables stop at 2030
    and the modules do not raise past it — they return a holiday set with no
    lunar closures at all, so a 2031 exit would walk through Spring Festival."""
    from lib import cn_calendar

    lny_2030 = cn_calendar.LNY_FIRST[2030]
    assert lny_2030 in cn_calendar.holidays(2030)
    assert not any(h.month == 2 for h in cn_calendar.holidays(2031)), \
        "past the table the CN calendar silently loses Spring Festival"

    assert q.resolve_horizon_window("2031-01-05", 5, q.HORIZON_UNIT_TRADING,
                                    q.MARKET_CN) is None
    # ...including a window that STARTS inside the range and ENDS outside it
    assert q.resolve_horizon_window("2030-12-20", 21, q.HORIZON_UNIT_TRADING,
                                    q.MARKET_CN) is None
    assert q.resolve_horizon_window("2013-06-03", 5, q.HORIZON_UNIT_TRADING,
                                    q.MARKET_CN) is None
    # the US floor is unchanged by the dispatch
    assert q.CLOCK_MARKET_SUPPORT[q.MARKET_US][0] == q.CLOCK_SUPPORTED_FROM


def test_the_search_bound_still_covers_the_longest_modelled_closure():
    """`_MAX_CLOSED_STRETCH_DAYS` fails CLOSED (returns None) rather than
    spinning, so a calendar edit that lengthens a closure past it would turn into
    silently unresolvable windows. Measured maxima over 2014-2030 pinned here."""
    worst = {}
    for market, cal in q.CLOCK_CALENDARS.items():
        run = best = 0
        d = date(2014, 1, 1)
        while d <= date(2030, 12, 31):
            run = 0 if cal.is_session(d) else run + 1
            best = max(best, run)
            d += timedelta(days=1)
        worst[market] = best
    assert worst == {"US": 3, "CN": 10, "HK": 6}
    assert max(worst.values()) < q._MAX_CLOSED_STRETCH_DAYS


def test_us_session_arithmetic_is_unchanged_by_the_generic_walkers():
    """The dispatch rewrote the forward walkers to run over `is_session`. For the
    US market they must agree with `lib.nyse_calendar`'s own helpers on every
    session of a two-year span — the round-2 behaviour is not allowed to move."""
    from lib import nyse_calendar

    d = date(2025, 1, 1)
    checked = 0
    while d <= date(2026, 12, 31):
        if nyse_calendar.is_session(d):
            for n in (0, 1, 5, 21):
                assert (q._session_n_forward(q.MARKET_US, d, n)
                        == nyse_calendar.session_n_forward(d, n))
            checked += 1
        d += timedelta(days=1)
    assert checked > 400


# --------------------------------------------------------------------------- #
# MAJOR 3 (round 3) — no zombie claims
# --------------------------------------------------------------------------- #
def test_an_unresolvable_clock_refuses_registration_and_is_counted(tmp_path):
    """A declared-unit claim whose clock cannot resolve used to register
    status=open with check_by=None: it could never grade (grade_claim skips an
    unresolvable window), never close (status advances only when every in-scope
    horizon matures), and appeared in no count. Silent immortality.

    It is now a REJECTED row with a stable reason prefix, and the population is
    a number."""
    c = q.make_claim(desk="d", asof="2026-08-05", scope_type="entity",
                     scope_key="920007.BJ", direction=1, horizon_d=21,
                     horizon_unit=q.HORIZON_UNIT_TRADING, bench="510300.SS",
                     timestamp_quality="CRAWL_BOUNDED", claim_family="cn_special_sits")
    assert c["check_by"] is None, "the pre-condition of the defect"

    stored = q.register(c, root=tmp_path)
    assert stored["status"] == q.STATUS_REJECTED
    assert stored["reject_reason"].startswith(q.REJECT_CLOCK_UNRESOLVABLE)
    assert stored["status"] != q.STATUS_OPEN, "never open-forever"

    counted = q.count_unresolvable_clock_claims(root=tmp_path)
    assert counted["n"] == 1
    assert counted["by_family"] == {"cn_special_sits": 1}
    assert sum(counted["by_reason"].values()) == 1

    # and it can never be graded even if something re-opened it by hand
    assert q.grade_claim({**stored, "status": q.STATUS_OPEN}, root=tmp_path,
                         today=date(2027, 1, 1)) == []


def test_an_out_of_range_anchor_is_refused_at_registration_not_left_open(tmp_path):
    """The same rule for the other unresolvable cause — an anchor outside the
    market's declared span."""
    c = q.make_claim(desk="d", asof="2009-06-01", scope_type="entity",
                     scope_key="CARR", direction=1, horizon_d=5,
                     horizon_unit=q.HORIZON_UNIT_TRADING,
                     timestamp_quality="CRAWL_BOUNDED")
    stored = q.register(c, root=tmp_path)
    assert stored["status"] == q.STATUS_REJECTED
    assert stored["reject_reason"].startswith(q.REJECT_CLOCK_UNRESOLVABLE)
    assert q.count_unresolvable_clock_claims(root=tmp_path)["n"] == 1


def test_a_resolvable_claim_and_every_legacy_claim_still_register_open(tmp_path):
    """Negative control for both refusals: the gate is scoped to declared-unit
    claims whose clock genuinely cannot resolve. A legacy claim has no resolved
    window at all and must be untouched by it."""
    ok = q.make_claim(desk="d", asof="2026-08-07", scope_type="entity",
                      scope_key="CARR", direction=1, horizon_d=5,
                      horizon_unit=q.HORIZON_UNIT_TRADING,
                      timestamp_quality="CRAWL_BOUNDED")
    legacy_bj = q.make_claim(desk="d", asof="2009-06-01", scope_type="entity",
                             scope_key="920007.BJ", direction=1, horizon_d=5,
                             bench="510300.SS",
                             timestamp_quality="CRAWL_BOUNDED")
    assert q.register(ok, root=tmp_path)["status"] == q.STATUS_OPEN
    assert q.register(legacy_bj, root=tmp_path)["status"] == q.STATUS_OPEN
    assert q.count_unresolvable_clock_claims(root=tmp_path)["n"] == 0


# --------------------------------------------------------------------------- #
# MAJOR 2 (round 3) — the headline guarantee states EXACTLY where it holds
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("horizon_d, holds", [
    (5, True), (21, True), (63, True),     # the graded rungs
    (3, True),                             # below the smallest rung: graded at 3
    (7, False), (30, False), (126, False),  # off-rung: check_by is not a graded exit
])
def test_check_by_is_a_graded_exit_only_on_the_graded_rungs(horizon_d, holds):
    """MAJOR 2 — the docstring asserted unconditionally that "check_by IS the
    authoritative exit the grader resolves". That is FALSE for every off-rung
    horizon: check_by is resolved at the claim's OWN horizon_d, the grader grades
    at `in_scope_horizons(horizon_d)`. Making it true would mean changing
    GRADE_HORIZONS / in_scope_horizons, which is P0b and out of scope — so the
    scope is stated instead, and it is EXECUTABLE rather than prose."""
    assert q.check_by_is_a_graded_exit(horizon_d) is holds
    assert (horizon_d in q.in_scope_horizons(horizon_d)) is holds


def test_an_off_rung_claims_check_by_is_a_real_exit_that_no_grade_row_matches(
        prices, tmp_path):
    """The concrete shape of that gap on a live lane. A 126-trading-day policy
    claim's check_by is a correctly resolved 126-session exit — and no grade row
    is ever measured to it, because the claim grades at 5, 21 and 63."""
    c = _claim(horizon_d=126, horizon_unit=q.HORIZON_UNIT_TRADING)
    win = q.resolve_horizon_window(q._entry_date(c), 126,
                                   q.HORIZON_UNIT_TRADING, q.MARKET_US)
    assert c["check_by"] == win.exit_date.isoformat()   # a REAL resolved exit
    assert not q.check_by_is_a_graded_exit(126)

    rows = q.grade_claim({**c, "claim_id": "cid-126"}, root=tmp_path,
                         today=date(2027, 6, 30))
    assert sorted(r["horizon_d"] for r in rows) == [5, 21, 63]
    assert c["check_by"] not in {r["clock_exit_date"] for r in rows}

    # ...while an ON-rung claim's check_by IS one of the graded exits.
    on = _claim(horizon_d=63, horizon_unit=q.HORIZON_UNIT_TRADING)
    on_rows = q.grade_claim({**on, "claim_id": "cid-63"}, root=tmp_path,
                            today=date(2027, 6, 30))
    assert q.check_by_is_a_graded_exit(63)
    assert on["check_by"] in {r["clock_exit_date"] for r in on_rows}


# --------------------------------------------------------------------------- #
# MAJOR 4 (round 3) — the migration demotion is LEGIBLE, never a silent collapse
# --------------------------------------------------------------------------- #
def test_a_clock_migration_is_labelled_not_rendered_as_a_collapse(tmp_path):
    """The basis reset is the CEO's ruling and is NOT changed here — the numbers
    below are identical to round 2. What is added is the reason they moved: a
    family reading GRADED/n_dates=40 flips to ACCRUING/n_dates=1 the night its
    first explicit-clock grade lands, and nothing on the verdict said why."""
    claims, grades = _mixed_store_rows(n_legacy=40, n_v1=1)
    _write_store(tmp_path, claims, grades)

    res = q.promotion_check("f", 21, root=tmp_path, control_only=True)

    # the ruling stands: NOT pooled, evaluated inside the explicit basis
    assert res.clock_basis == _v1()
    assert res.n_dates == 1 and res.current_state == q.STATE_ACCRUING

    # ...and the demotion is now legible
    assert res.clock_migration is True
    assert res.clock_prior_n_dates == {q.CLOCK_LEGACY: 40}
    assert "corrected clock" in res.migration_note
    assert res.as_dict()["clock_migration"] is True
    assert res.as_dict()["clock_prior_n_dates"] == {q.CLOCK_LEGACY: 40}


def test_a_single_basis_family_is_not_labelled_as_migrating(tmp_path):
    """Negative control: the flag must mean something. A family that never
    straddled carries no migration label and no phantom prior count."""
    claims, grades = _mixed_store_rows(n_legacy=0, n_v1=26)
    _write_store(tmp_path, claims, grades)
    res = q.promotion_check("f", 21, root=tmp_path, control_only=True)
    assert res.eligible is True
    assert res.clock_migration is False
    assert res.clock_prior_n_dates == {} and res.migration_note == ""


def test_the_admin_experiments_surface_renders_the_migration(tmp_path, monkeypatch):
    """The consumer, end to end. Before: `n_dates=1/25 @ 21d · CI-low=n/a · …` —
    indistinguishable from a family whose evidence evaporated. After: the same
    numbers plus, in plain words, that it is re-accruing on a corrected clock and
    how big the history being counted separately is."""
    import scripts.grade_qledger as grader
    from engine import experiments_registry as er

    claims, grades = _mixed_store_rows(n_legacy=40, n_v1=1)
    _write_store(tmp_path, claims, grades)
    readiness = grader.compute_promotion_readiness(tmp_path, families=["f"])
    cell = readiness["f"]["21"]
    assert cell["clock_migration"] is True
    assert cell["clock_prior_n_dates"] == {q.CLOCK_LEGACY: 40}

    monkeypatch.setattr(er, "_read_json",
                        lambda rel: {"promotion_readiness": readiness}
                        if rel.endswith("track_record.json") else {})
    out = er._refresh_qledger_promotion({"claim_family": "f"})

    assert out["clock_migration"] is True
    assert out["clock_prior_n_dates"] == {q.CLOCK_LEGACY: 40}
    assert "RE-ACCRUING on a corrected clock" in out["state"]
    assert "40 dates on the previous clock" in out["state"]
    assert out["ready"] is False and out["status"] == "accruing"

    # BEFORE/AFTER: the same corpus with the migration label suppressed is the
    # line a reader used to get — numbers only, no reason.
    bare = dict(cell)
    bare["clock_migration"] = False
    monkeypatch.setattr(er, "_read_json",
                        lambda rel: {"promotion_readiness": {"f": {"21": bare}}}
                        if rel.endswith("track_record.json") else {})
    before = er._refresh_qledger_promotion({"claim_family": "f"})
    assert "RE-ACCRUING" not in before["state"]
    assert before["state"] in out["state"], \
        "the migration line is ADDED to the honest numbers, never replaces them"


# --------------------------------------------------------------------------- #
# MINOR (round 3) — the nightly maturity PRE-GATE dispatches on the claim's clock
# --------------------------------------------------------------------------- #
def test_the_nightly_pre_gate_uses_the_claims_own_clock_not_the_legacy_one(
        prices, tmp_path, monkeypatch):
    """MINOR — `scripts/grade_qledger` pre-gates every claim on `q._matured`, the
    LEGACY calendar maturity function, before paying for grade_claim's price
    reads. It ran with NO unit dispatch, so a `trading_days` h=21 claim was
    opened on roughly the calendar clock.

    SCOPE OF THE DEFECT, STATED HONESTLY. The legacy pre-gate errs EARLY (a
    calendar h is never longer than h sessions), and `grade_claim` re-resolves on
    the real window and refuses, so no wrong grade was ever written and the
    blocked COUNT is the same either way. What was wrong is that the pre-gate and
    the grader asked about different windows — the nightly's own admission test
    was not the test its grades are measured by. The property below is what that
    costs and what the dispatch buys: the pre-gate must never admit a horizon the
    grader's own window says is immature.
    """
    import scripts.grade_qledger as grader

    c = _claim(horizon_d=21, horizon_unit=q.HORIZON_UNIT_TRADING)
    win = q.claim_window(c, 21)
    assert win is not None
    legs = ["CARR", "SPY", "XLI"]

    # 1. the divergence is real — the pre-fix control still fires
    early = win.entry_anchor + timedelta(days=22)
    assert early < win.coverage_date
    assert q._matured(tmp_path, q._entry_date(c), 21, early, legs) is True, \
        "the pre-fix control: the legacy pre-gate opens this claim early"
    assert q._matured_window(tmp_path, win, early, legs) is False

    # 2. and it is not one lucky day — over the whole approach to the exit, the
    #    legacy gate says 'ready' on days the real clock does not, and the
    #    dispatched gate never does.
    disagreements = 0
    d = win.entry_anchor
    while d <= win.coverage_date:
        legacy = q._matured(tmp_path, q._entry_date(c), 21, d, legs)
        real = q._matured_window(tmp_path, win, d, legs)
        assert not (real and not legacy), \
            "the legacy gate errs EARLY, never late — pinned so the claim above " \
            "about the defect's direction cannot rot"
        if legacy and not real:
            disagreements += 1
        d += timedelta(days=1)
    assert disagreements >= 7, disagreements

    # 3. the nightly, run at that date, writes the 5d rung and NOT the 21d one
    q.register({**c, "claim_family": "clocktest"}, root=tmp_path)
    monkeypatch.setattr(grader, "compute_promotion_readiness", lambda *a, **k: {})
    grader.run(root=tmp_path, today=early, dry_run=False)
    graded = sorted(g["horizon_d"] for g in q.load_grades(tmp_path))
    assert graded == [5], graded

    # 4. ...and past the real session exit, the 21d rung grades
    grader.run(root=tmp_path, today=date(2026, 12, 1), dry_run=False)
    graded = sorted(g["horizon_d"] for g in q.load_grades(tmp_path))
    assert graded == [5, 21], graded


def test_the_pre_gate_and_the_grader_ask_about_the_SAME_window(prices, tmp_path):
    """The property the dispatch establishes, under BOTH units: the nightly's
    admission test is `claim_window` + `_matured_window` — the very window
    `grade_claim` will measure — so 'admitted' and 'gradeable' can no longer be
    two different questions."""
    for unit in (q.HORIZON_UNIT_TRADING, q.HORIZON_UNIT_CALENDAR):
        c = _claim(horizon_d=21, horizon_unit=unit)
        for h in q.in_scope_horizons(21):
            win = q.claim_window(c, h)
            assert win is not None
            d = win.entry_anchor
            while d <= win.coverage_date + timedelta(days=3):
                admitted = q._matured_window(tmp_path, win, d,
                                             ["CARR", "SPY", "XLI"])
                rows = [r for r in q.grade_claim({**c, "claim_id": "x"},
                                                 root=tmp_path, today=d)
                        if r["horizon_d"] == h]
                assert admitted == bool(rows), (unit, h, d)
                d += timedelta(days=1)


def test_run_status_publishes_the_refused_clock_population(tmp_path, monkeypatch):
    """`fail closed` is only auditable if the refusals are a number on the
    nightly. A lane that starts refusing everything must show up here rather
    than as claims that quietly never grade."""
    import scripts.grade_qledger as grader

    q.register(q.make_claim(desk="d", asof="2026-08-05", scope_type="entity",
                            scope_key="920007.BJ", direction=1, horizon_d=21,
                            horizon_unit=q.HORIZON_UNIT_TRADING,
                            bench="510300.SS",
                            timestamp_quality="CRAWL_BOUNDED",
                            claim_family="cn_special_sits"), root=tmp_path)
    monkeypatch.setattr(grader, "compute_promotion_readiness", lambda *a, **k: {})
    out = grader.run(root=tmp_path, today=date(2026, 12, 1), dry_run=True)
    assert out["clock_unresolvable_claims"]["n"] == 1
    assert out["clock_unresolvable_claims"]["by_family"] == {"cn_special_sits": 1}


# --------------------------------------------------------------------------- #
# ROUND-4 BLOCKER — the market dispatch FAILED OPEN on single-letter foreign
# exchange suffixes. The shape heuristic ("one letter => US share class") is
# replaced by an ENUMERATION, because a shape heuristic failed here twice.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("ticker, exchange_word", [
    ("VOD.L", "London"),      # London Stock Exchange
    ("7203.T", "Tokyo"),      # Tokyo Stock Exchange
    ("BAS.F", "Frankfurt"),   # Frankfurt (Fukuoka under the JP convention)
    ("9432.N", "Nagoya"),
    ("8524.S", "Sapporo"),
])
def test_a_single_letter_exchange_suffix_refuses_with_a_named_reason(
        ticker, exchange_word):
    """THE ROUND-3 BLOCKER RETURNING IN A NEW PLACE. `.L` / `.T` / `.F` are real
    exchanges whose Yahoo suffix is ONE letter, and the previous rule read every
    single-letter suffix as a US share class — so a London, Tokyo or Frankfurt
    name resolved silently onto NYSE sessions, which is the exact failure the
    dispatch exists to stop. Each must now REFUSE, and the refusal must NAME the
    venue rather than shrug."""
    market, reason = q._ticker_market(ticker)
    assert market is None, f"{ticker} must not resolve to any market"
    assert reason.startswith(q.MARKET_UNDETERMINED_FOREIGN_EXCHANGE), reason
    assert exchange_word.lower() in reason.lower(), reason
    # and it is refused at the claim level too, not merely at the leg level
    m, r = q.resolve_claim_market(
        {"scope": {"type": "entity", "key": ticker}, "bench": ticker})
    assert m is None and r.startswith(q.MARKET_UNDETERMINED_FOREIGN_EXCHANGE), r


def test_the_us_share_class_legs_are_untouched_by_the_deny_list():
    """NEGATIVE CONTROL for the blocker fix, and the reason a blanket 'refuse
    every dotted suffix' was not the answer: `BRK.B` / `BRK.A` are 527 legs in
    the live store and must still resolve US, through the SAME code path that
    now refuses `.L`."""
    for t in ("BRK.B", "BRK.A", "BF.B", "HEI.A"):
        assert q._ticker_market(t) == (q.MARKET_US, ""), t
    assert q.resolve_claim_market(
        {"scope": {"type": "entity", "key": "BRK.B"}, "bench": "SPY"}) == ("US", "")
    # a dotless US ticker is unaffected
    assert q._ticker_market("CARR") == (q.MARKET_US, "")


@pytest.mark.parametrize("ticker", ["NESN.SW", "MC.PA", "005930.KS", "2330.TW",
                                    "920007.BJ"])
def test_the_multi_letter_refusals_are_intact(ticker):
    """Round-3's refusals must survive round-4's restructuring: every one of
    these still refuses, with a reason that names a class."""
    market, reason = q._ticker_market(ticker)
    assert market is None, ticker
    assert reason.startswith((q.MARKET_UNDETERMINED_FOREIGN_EXCHANGE,
                              q.MARKET_UNDETERMINED_UNKNOWN_SUFFIX)), reason


def test_every_live_leg_suffix_resolves_the_way_the_store_needs():
    """The suffix census of the live claims store (46,629 claims, measured
    2026-08-13): .SS 9,403 · .SZ 2,489 · .B 287 · .A 240 · .BJ 4 — and nothing
    else. Pinned as a LITERAL, never read from data/**: the store is
    nightly-appended and a test may not assert over it. The deny-list must not
    have refused anything that is live-and-correct, and must still refuse .BJ."""
    assert q._ticker_market("600519.SS") == (q.MARKET_CN, "")
    assert q._ticker_market("300024.SZ") == (q.MARKET_CN, "")
    assert q._ticker_market("BRK.B")[0] == q.MARKET_US
    assert q._ticker_market("BRK.A")[0] == q.MARKET_US
    assert q._ticker_market("920007.BJ")[0] is None


def test_the_two_suffix_tables_cannot_both_claim_a_suffix():
    """A mapped suffix is RESOLVED and an enumerated one is REFUSED — a suffix in
    both would make the answer depend on lookup order. Disjointness is the
    invariant; the ordering in `_ticker_market` is not allowed to be load-bearing."""
    overlap = set(q.MARKET_SUFFIX) & set(q.EXCHANGE_SUFFIXES_UNSUPPORTED)
    assert overlap == set(), overlap
    for suffix, exchange in q.EXCHANGE_SUFFIXES_UNSUPPORTED.items():
        assert suffix.startswith("."), suffix
        assert suffix == suffix.upper(), suffix
        assert exchange.strip(), suffix          # every entry names a venue
    # the single-letter entries are the point of this round
    assert {".L", ".T", ".F"} <= set(q.EXCHANGE_SUFFIXES_UNSUPPORTED)


def test_the_share_class_reading_is_corroborated_not_assumed():
    """The ONE inference left in the dispatch is bounded on both sides: the
    enumeration takes every known exchange suffix BEFORE it, and the house
    US-equity gate (`ticker_shape.valid_us_ticker` — the gate every emitter here
    routes ticker keys through) has to accept the whole symbol AFTER it. So a
    single-letter suffix on something that is not a US symbol shape still fails
    closed rather than inheriting NYSE."""
    from engine.ticker_shape import valid_us_ticker

    assert valid_us_ticker("BRK.B") is not None          # corroborated
    assert valid_us_ticker("600519.Q") is None           # digit-first root
    market, reason = q._ticker_market("600519.Q")
    assert market is None
    assert reason.startswith(q.MARKET_UNDETERMINED_NOT_A_US_SYMBOL), reason


def test_a_london_claim_is_refused_at_registration_and_counted(tmp_path):
    """End to end, on the store: the blocker's exemplar cannot become a zombie
    claim graded on NYSE. It is a rejected row with a bucketable reason head."""
    c = q.make_claim(desk="d", asof="2026-08-05", scope_type="entity",
                     scope_key="VOD.L", direction=1, horizon_d=21,
                     horizon_unit=q.HORIZON_UNIT_TRADING,
                     timestamp_quality="CRAWL_BOUNDED", claim_family="intl_desk")
    assert c["check_by"] is None
    stored = q.register(c, root=tmp_path)
    assert stored["status"] == q.STATUS_REJECTED
    counted = q.count_unresolvable_clock_claims(root=tmp_path)
    assert counted["n"] == 1
    assert list(counted["by_reason"]) == [
        f"{q.REJECT_CLOCK_UNRESOLVABLE}:"
        f"{q.MARKET_UNDETERMINED_FOREIGN_EXCHANGE}:.L"]


# --------------------------------------------------------------------------- #
# ROUND-4 MAJOR 1 — the no-pooling boundary is MARKET-AWARE
# --------------------------------------------------------------------------- #
def test_a_us_trading_day_row_and_a_cn_trading_day_row_cannot_pool():
    """THE DEFECT. `grade_clock_basis` returned `explicit_unit_v1:trading_days`
    for a US-resolved row and a CN-resolved row alike, so two observations
    measured on incompatible session calendars — 21 NYSE sessions and 21 SSE
    sessions are different spans, and Golden Week/Thanksgiving fall in different
    places — pooled into ONE statistic at every aggregation point. Stopping
    exactly that is what a clock basis is for."""
    us = _grade_row(q.HORIZON_UNIT_TRADING, cid="u", excess=0.05, hit=True,
                    market=q.MARKET_US)
    cn = _grade_row(q.HORIZON_UNIT_TRADING, cid="c", excess=0.05, hit=True,
                    market=q.MARKET_CN)
    assert q.grade_clock_basis(us) != q.grade_clock_basis(cn)
    assert q.grade_clock_basis(us) == _v1(market=q.MARKET_US)
    assert q.grade_clock_basis(cn) == _v1(market=q.MARKET_CN)

    # the boundary primitives all inherit it — nothing has to remember
    assert sorted(q.partition_grades_by_clock([us, cn])) == [
        _v1(market=q.MARKET_CN), _v1(market=q.MARKET_US)]
    with pytest.raises(q.HorizonClockMismatch):
        q.require_single_clock([us, cn], context="us+cn")
    claims = [{"claim_id": "u", "desk": "d", "claim_family": "f",
               "asof": "2026-01-05"},
              {"claim_id": "c", "desk": "d", "claim_family": "f",
               "asof": "2026-01-06"}]
    with pytest.raises(q.HorizonClockMismatch):
        q._aggregate(claims, [us, cn], "family", 21)


def test_an_explicit_row_with_no_market_stamp_pools_with_nothing():
    """Fail closed on the residual: a row written by the first cut of this
    contract (NYSE-hardcoded, unstamped) has an UNKNOWN calendar, and unknown
    pools with nothing — least of all with US, which is what it silently was."""
    unstamped = {"claim_id": "x", "horizon_d": 21, "hit": True,
                 "horizon_unit": q.HORIZON_UNIT_TRADING,
                 "clock_version": q.CLOCK_V1}
    assert q.grade_clock_basis(unstamped) == _v1(market=q.CLOCK_MARKET_UNSTAMPED)
    stamped = _grade_row(q.HORIZON_UNIT_TRADING, cid="y", excess=0.0, hit=True,
                         market=q.MARKET_US)
    with pytest.raises(q.HorizonClockMismatch):
        q.require_single_clock([unstamped, stamped])


def _two_market_store(n_us: int, n_cn: int):
    """A family whose grades split across two markets on the SAME unit."""
    claims, grades = [], []
    for tag, n, market, base in (("U", n_us, q.MARKET_US, date(2026, 1, 1)),
                                 ("C", n_cn, q.MARKET_CN, date(2026, 6, 1))):
        for i in range(n):
            cid = f"{tag}{i}"
            claims.append({"claim_id": cid, "desk": "d", "claim_family": "f",
                           "asof": (base + timedelta(days=i)).isoformat(),
                           "is_placebo": False, "status": "open"})
            grades.append({"claim_id": cid, "horizon_d": 21, "excess": 0.05,
                           "hit": True, "subject_ret": 0.06, "bench_ret": 0.01,
                           "control_ret": 0.01,
                           "horizon_unit": q.HORIZON_UNIT_TRADING,
                           "clock_version": q.CLOCK_V1, "clock_market": market})
    return claims, grades


def test_promotion_is_reachable_per_market_and_never_by_pooling(tmp_path):
    """The boundary must not become a wall. A family graded on two markets is
    PROMOTABLE on each of them, by name — and the pooled count (52) is not
    reachable by any call."""
    claims, grades = _two_market_store(n_us=26, n_cn=26)
    _write_store(tmp_path, claims, grades)

    # the DEFAULT is a refusal: two explicit bases have no non-arbitrary answer
    mixed = q.promotion_check("f", 21, root=tmp_path, control_only=True)
    assert mixed.eligible is False
    assert mixed.current_state == q.STATE_MIXED_CLOCK
    assert mixed.clock_basis is None
    assert "clock_basis" in mixed.reason, "the reason must name the way out"

    # ...and each market promotes on its OWN 26 dates
    for market in (q.MARKET_US, q.MARKET_CN):
        res = q.promotion_check("f", 21, root=tmp_path, control_only=True,
                                clock_basis=_v1(market=market))
        assert res.eligible is True, (market, res.reason)
        assert res.n_dates == 26, (market, res.n_dates)
        assert res.clock_basis == _v1(market=market)
    assert mixed.clock_prior_n_dates == {_v1(market=q.MARKET_US): 26,
                                         _v1(market=q.MARKET_CN): 26}


def test_the_track_record_splits_the_two_markets_and_sums_neither(tmp_path,
                                                                  monkeypatch):
    """The display tier obeys the same boundary: two markets are two published
    blocks, and the headline cell is ONE of them, labelled."""
    claims, grades = _two_market_store(n_us=3, n_cn=1)
    monkeypatch.setattr(q, "load_claims", lambda root=None: claims)
    monkeypatch.setattr(q, "load_grades", lambda root=None: grades)

    tr = q.compute_track_record(root=tmp_path)
    assert tr["counts"]["grades_by_clock_basis"] == {
        _v1(market=q.MARKET_US): 3, _v1(market=q.MARKET_CN): 1}
    cell = tr["by_family"]["f"]["21"]
    assert cell["pooling_refused"] is True
    assert cell["clock_basis"] == _v1(market=q.MARKET_US)   # 3 dates beats 1
    assert cell["n_obs"] == 3, "the published cell is ONE market, never the union"


# --------------------------------------------------------------------------- #
# ROUND-4 MAJOR 2 — the migration banner CLEARS
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("n_legacy, n_v1, migrating", [
    (40, 1, True),     # the night the first corrected-clock grade lands
    (40, 39, True),    # still short of the history it replaced
    (40, 40, False),   # caught up — there is no drop left to explain
    (40, 55, False),   # past it
])
def test_the_migration_banner_is_true_only_while_there_is_a_drop_to_explain(
        tmp_path, n_legacy, n_v1, migrating):
    """THE DEFECT. `clock_migration = bool(excluded)` never referenced the live
    n_dates, so ANY family carrying even one legacy row was flagged as migrating
    FOREVER — including one that finished migrating and whose legacy pile is a
    closed, never-growing set. A banner that never clears is furniture, not
    disclosure, and both docstrings described it as something it was not.

    The flag now means exactly what it is for: the headline count is SMALLER than
    the history being counted separately, so the drop a reader sees is a clock
    migration rather than a collapse."""
    claims, grades = _mixed_store_rows(n_legacy=n_legacy, n_v1=n_v1)
    _write_store(tmp_path, claims, grades)
    res = q.promotion_check("f", 21, root=tmp_path, control_only=True)

    assert res.n_dates == n_v1, "the ruling is unchanged: nothing is pooled"
    assert res.clock_migration is migrating
    assert bool(res.migration_note) is migrating
    assert res.as_dict()["clock_migration"] is migrating
    # the excluded history stays a published fact either way — it is disclosure
    # about the verdict, not a function of whether the banner is lit
    assert res.clock_prior_n_dates == {q.CLOCK_LEGACY: n_legacy}
    # ...and the excluded basis is still named in the reason, always
    assert q.CLOCK_LEGACY in res.reason and "NOT pooled" in res.reason


def test_the_cleared_banner_reaches_the_admin_surface_as_a_plain_state_line(
        tmp_path, monkeypatch):
    """The consumer end of the same fix: a fully-migrated family must not carry
    'RE-ACCRUING on a corrected clock' in the admin Experiments state line."""
    import scripts.grade_qledger as grader
    from engine import experiments_registry as er

    claims, grades = _mixed_store_rows(n_legacy=26, n_v1=26)
    _write_store(tmp_path, claims, grades)
    readiness = grader.compute_promotion_readiness(tmp_path, families=["f"])
    cell = readiness["f"]["21"]
    assert cell["clock_migration"] is False
    assert cell["clock_prior_n_dates"] == {q.CLOCK_LEGACY: 26}

    monkeypatch.setattr(er, "_read_json",
                        lambda rel: {"promotion_readiness": readiness}
                        if rel.endswith("track_record.json") else {})
    out = er._refresh_qledger_promotion({"claim_family": "f"})
    assert out["clock_migration"] is False
    assert "RE-ACCRUING" not in out["state"]
    assert "migration_note" not in out


# --------------------------------------------------------------------------- #
# ROUND-4 MAJOR 3 — a live producer is never killed SILENTLY by the refusal
# --------------------------------------------------------------------------- #
# Lives here, not in tests/test_communique_diff.py, because that file is owned by
# no legacy job: a test of this contract placed there would never run in CI.
def _diff_result(tickers):
    return {"asof": "2026-08-05",
            "events": [{"event_id": "e1", "kind": "APPEARED", "organ": "pboc",
                        "phrase": "适度宽松", "asof": "2026-08-05"}],
            "counts": {"n_events": 1}}, tickers


def test_communique_diffs_entity_path_resolves_on_the_calendar_it_prices_in(
        tmp_path, monkeypatch):
    """MAJOR 3. `communique_diff` mints TRADING-unit claims on A-share tickers
    resolved by `entity_resolver.resolve_cn`, and named no bench — so it took
    qledger's non-macro default (SPY) and the A-share/US pair was refused as
    mixed_markets. The producer's entity path died with no disclosure.

    It prices Chinese policy on Chinese sessions, so it names the CN bench and
    the claim resolves on the A-share calendar."""
    from engine import communique_diff as cd

    result, tickers = _diff_result(["600519.SS", "300024.SZ"])
    monkeypatch.setattr(cd, "_entities_for", lambda e: tickers)
    n = cd.register_claims(result, root=tmp_path)

    assert n == 2, "both entity claims register OPEN"
    assert result["n_claims_clock_refused"] == 0
    stored = q.load_claims(tmp_path)
    assert {c["scope"]["key"] for c in stored} == set(tickers)
    for c in stored:
        assert c["status"] == q.STATUS_OPEN
        assert c["bench"] == cd.CN_BENCH
        assert c["clock_market"] == q.MARKET_CN
        assert c["check_by"], "a resolved A-share exit, not None"
    assert q.count_unresolvable_clock_claims(root=tmp_path)["n"] == 0


def test_a_producer_claim_the_clock_refuses_is_counted_never_silent(
        tmp_path, monkeypatch, caplog):
    """The other half of MAJOR 3, and the property that outlives this particular
    bench fix: if the clock ever refuses this desk's claims again, the run says
    so and the number travels with the artifact. 'Registered' means OPEN — a
    rejected row was never on the forward log, and counting it as one is exactly
    how a producer goes dark behind a healthy-looking count."""
    from engine import communique_diff as cd

    result, tickers = _diff_result(["920007.BJ", "600519.SS"])
    monkeypatch.setattr(cd, "_entities_for", lambda e: tickers)
    with caplog.at_level("WARNING"):
        n = cd.register_claims(result, root=tmp_path)

    assert n == 1, "only the resolvable claim is on the forward log"
    assert result["n_claims_clock_refused"] == 1
    assert result["n_claims_rejected"] == 1
    assert "REFUSED by the horizon clock" in caplog.text
    counted = q.count_unresolvable_clock_claims(root=tmp_path)
    assert counted["n"] == 1
    assert counted["by_family"] == {cd.CLAIM_FAMILY: 1}


# --------------------------------------------------------------------------- #
# ROUND-4 MINOR — by_reason buckets on the machine-readable HEAD
# --------------------------------------------------------------------------- #
def test_by_reason_buckets_on_the_head_not_the_prose_tail(tmp_path):
    """THE DEFECT. The out-of-range class's reason carries the ANCHOR DATE, and
    the old split kept everything before the first '(' — so every refused claim
    got its own histogram key. A histogram with one row per event is not a
    histogram; its own docstring said it bucketed on the machine-readable head."""
    for i in range(5):
        q.register(q.make_claim(
            desk="d", asof=f"2009-06-0{i + 1}", scope_type="entity",
            scope_key=f"AAP{chr(65 + i)}", direction=1, horizon_d=5,
            horizon_unit=q.HORIZON_UNIT_TRADING,
            timestamp_quality="CRAWL_BOUNDED", claim_family="fam"),
            root=tmp_path)
    counted = q.count_unresolvable_clock_claims(root=tmp_path)
    assert counted["n"] == 5
    assert counted["by_reason"] == {
        f"{q.REJECT_CLOCK_UNRESOLVABLE}:window_unresolvable:{q.MARKET_US}": 5}
    # every offending detail is still ON the row, just not in the histogram key
    rejected = [c for c in q.load_claims(tmp_path)
                if c["status"] == q.STATUS_REJECTED]
    assert all("2009-06-0" in c["reject_reason"] for c in rejected)


def test_the_reason_head_is_bounded_while_the_tail_names_the_offender():
    """The head/tail split is a contract, not a parsing convention: the head is
    what a histogram may key on, the tail is where a ticker or a date may go."""
    _, reason = q._ticker_market("VOD.L")
    assert q.clock_reason_head(reason) == \
        f"{q.MARKET_UNDETERMINED_FOREIGN_EXCHANGE}:.L"
    _, mixed = q.resolve_claim_market(
        {"scope": {"type": "entity", "key": "300024.SZ"}, "bench": "SPY"})
    # the mixed reason names BOTH legs — and none of that may become a key
    assert "300024.SZ" in mixed and "SPY" in mixed
    assert q.clock_reason_head(mixed) == q.MARKET_UNDETERMINED_MIXED


# --------------------------------------------------------------------------- #
# ROUND 5 — BLOCKER 1: THE NO-SUFFIX BRANCH FAILED OPEN ONTO US.
#
# Three rounds in a row patched a new failure of the SAME assumption — "a
# claim's market can be read off the SHAPE of its ticker" — and this is the
# fourth: a bare numeric like `600519` or `0700` carries NO market information
# in its shape at all, and round 4's "no suffix -> US" answered US for it,
# silently, every time. The fix is structural: market is now derived from the
# claim's OWN PROVENANCE (`DESK_MARKET`/`_provenance_market`) when the shape
# cannot say, and ticker shape may only corroborate (a real exchange suffix,
# or `valid_us_ticker` when provenance is silent) or refuse — never originate.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("ticker", ["600519", "000001", "0700"])
def test_a_bare_ticker_never_silently_resolves_to_us(ticker):
    """The live exemplars, called with NO claim context — exactly what
    `session_anchor.market_for_ticker` (the house classifier) would answer US
    for. `_ticker_market` alone has no provenance to consult, so every one of
    these FAILS CLOSED — never `(q.MARKET_US, "")`, the round-4 behaviour.

    P0a-2 REMOVED `^HSI` from this list, and that is a STRENGTHENING, not a
    relaxation. Acceptance bar #1 is "the TRUE market, or fail closed" — `^HSI`
    used to satisfy it the weak way (fail closed, because `plausible_symbol`
    rejects the leading `^` and it read as an absent leg). It now satisfies it
    the strong way: `INDEX_MARKET` names HK. See
    `test_an_index_subject_no_longer_lets_the_default_bench_name_the_market`
    for why failing closed was NOT good enough here — an absent leg let the
    DEFAULT BENCH name the market, which is how the Hang Seng resolved US."""
    from engine.session_anchor import market_for_ticker
    assert market_for_ticker(ticker) == "US", (
        "negative control: the house classifier really would have said US here")
    market, reason = q._ticker_market(ticker)
    assert market is None, f"{ticker} must never silently resolve to US"
    head = q.clock_reason_head(reason).split(":", 1)[0]
    assert head in (q.MARKET_UNDETERMINED_NO_LEG,
                    q.MARKET_UNDETERMINED_NO_PROVENANCE), reason


def test_a_bare_a_share_code_resolves_cn_through_its_desks_own_provenance():
    """The TRUE-market half of the acceptance bar: 600519 (Kweichow Moutai,
    Shanghai) and 000001 (Ping An, Shenzhen) — BARE, no suffix — resolve CN
    when the claim carries the desk `cn_importance_v0` is provenanced under,
    with the provenance path shown explicitly (`_provenance_market`), and via
    the full `make_claim` -> `resolve_claim_market` path a real producer takes."""
    assert q._provenance_market({"desk": "cn_importance_v0"}) == q.MARKET_CN
    assert q._provenance_market({"claim_family": "china_news"}) == q.MARKET_CN
    for ticker, desk in (("600519", "cn_importance_v0"), ("000001", "china_news")):
        market, reason = q._ticker_market(ticker, provenance=q.MARKET_CN)
        assert (market, reason) == (q.MARKET_CN, "")
        # end to end: the claim itself, with no suffix anywhere, resolves CN
        # because ITS DESK says so — not because the ticker looks like anything.
        c = q.make_claim(desk=desk, asof="2026-08-07", scope_type="entity",
                         scope_key=ticker, direction=0, horizon_d=5,
                         horizon_unit=q.HORIZON_UNIT_TRADING,
                         timestamp_quality="CRAWL_BOUNDED", bench="510300.SS",
                         claim_family=desk)
        assert c["clock_market"] == q.MARKET_CN
        assert c["check_by"], "a resolved A-share exit, not None"


def test_a_bare_ticker_with_no_provenance_anywhere_fails_closed_and_counted(tmp_path):
    """0700 (Tencent, Hong Kong) is bare and ticker-SHAPED (`plausible_symbol`
    is True — it is all digits, a real subject), and THIS repo has no
    HK-priced desk in `DESK_MARKET` to provenance it from — so the honest
    answer is FAIL CLOSED, not a guess at HK. It fails closed regardless of
    what the bench says, because a ticker-shaped leg that cannot resolve
    refuses the WHOLE claim (`resolve_claim_market`'s per-leg contract) —
    unlike a purely symbolic label (see `^HSI` below), it never defers to
    another leg. Registration refuses the claim (never a zombie open row) and
    the refusal is COUNTED, matching acceptance bar #2 ('a claim with no
    determinable provenance fails closed and is counted')."""
    claim = q.make_claim(desk="some_unmapped_desk", asof="2026-08-07",
                         scope_type="entity", scope_key="0700", direction=0,
                         horizon_d=5, horizon_unit=q.HORIZON_UNIT_TRADING,
                         timestamp_quality="CRAWL_BOUNDED", bench="SPY",
                         claim_family="some_unmapped_desk")
    assert claim["check_by"] is None, "the clock could not resolve — no zombie exit"
    stored = q.register(claim, root=tmp_path)
    assert stored["status"] == q.STATUS_REJECTED
    assert stored["reject_reason"].startswith(q.REJECT_CLOCK_UNRESOLVABLE)
    counted = q.count_unresolvable_clock_claims(root=tmp_path)
    assert counted["n"] == 1


def test_hsi_resolves_its_own_market_and_never_defers_to_the_bench():
    """SUPERSEDES a round-5 test that ENSHRINED THE DEFECT.

    That test asserted, as correct behaviour:

        resolve_claim_market({"scope": {"key": "^HSI"}, "bench": "SPY"})
            == (q.MARKET_US, "")

    ...on the reasoning that `^HSI` is not ticker-SHAPED (`plausible_symbol` is
    False for the leading `^`), so it is an absent leg and "the market comes
    from whichever OTHER leg carries real information". The reasoning is sound
    for a symbolic MACRO label, where nothing is priced. It is wrong for an
    INDEX, which is a real instrument on a real exchange — and the consequence
    was that a Hang Seng claim graded on NYSE sessions against SPY, with a
    green test standing behind it. `^HSI` skipping itself is precisely what let
    the DEFAULT bench name the market.

    An index now names its own market from `INDEX_MARKET`, and a claim pairing
    a HK subject with a US bench is refused as MIXED — which is the honest
    answer: those two legs have no single session ruler."""
    assert q._ticker_market("^HSI") == (q.MARKET_HK, "")

    market, reason = q.resolve_claim_market(
        {"scope": {"type": "macro", "key": "^HSI"}, "bench": "SPY",
         "control": None})
    assert market is None, "the Hang Seng resolved on NYSE sessions"
    assert q.clock_reason_head(reason).startswith(q.MARKET_UNDETERMINED_MIXED)
    assert "HK" in reason and "US" in reason

    # ^HSI benchmarked against a HK instrument has ONE ruler and resolves.
    assert q.resolve_claim_market(
        {"scope": {"type": "macro", "key": "^HSI"}, "bench": "2800.HK",
         "control": None}) == (q.MARKET_HK, "")

    # ...and an index against ITSELF still resolves its own market, rather than
    # failing closed for want of a second opinion.
    assert q.resolve_claim_market(
        {"scope": {"type": "macro", "key": "^HSI"}, "bench": "^HSI",
         "control": None}) == (q.MARKET_HK, "")


def test_a_desk_not_in_the_provenance_table_is_unaffected_negative_control():
    """Negative control: a desk this table has never heard of still resolves
    every REAL US ticker exactly as before — provenance only ADDS a source, it
    never narrows the existing shape-corroborated US fallback. Every live US
    lane (altdata/radar/policy/whitehouse/narrative/intel_hub/…) keeps working
    with no entry in `DESK_MARKET` at all."""
    assert q._provenance_market({"desk": "altdata"}) is None
    for ticker in ("AAPL", "SPY", "XLP", "BRK.B"):
        market, reason = q._ticker_market(ticker, provenance=None)
        assert (market, reason)[0] == q.MARKET_US, (ticker, reason)


# --------------------------------------------------------------------------- #
# ROUND 5 — BLOCKER 2: THE MIXED-MARKET REFUSAL KILLED A LIVE PRODUCER
# --------------------------------------------------------------------------- #
def test_missing_tapes_symbolic_macro_key_never_originates_a_market():
    """`engine/missing_tape.py` registers `scope_key="CN_CENSORSHIP_RISK"`
    (a symbolic risk-flag label, never a real ticker) against
    `bench="510300.SS"`. Under the round-4 code the symbolic key fell through
    the no-suffix branch to US, and the US/CN pair refused as mixed_markets —
    silently killing this desk's forward log. `CN_CENSORSHIP_RISK` is not even
    ticker-SHAPED (`plausible_symbol` is False, underscores included), so it
    now contributes NOTHING toward the market — exactly like an absent leg —
    and the bench alone, unaided, decides CN."""
    from engine.ticker_shape import plausible_symbol
    assert plausible_symbol("CN_CENSORSHIP_RISK") is False
    market, reason = q._ticker_market("CN_CENSORSHIP_RISK")
    assert (market, reason) == (None, q.MARKET_UNDETERMINED_NO_LEG)

    claim = {"scope": {"type": "macro", "key": "CN_CENSORSHIP_RISK"},
             "bench": "510300.SS", "control": None,
             "desk": "missing_tape", "claim_family": "missing_tape"}
    assert q.resolve_claim_market(claim) == (q.MARKET_CN, "")


def test_missing_tapes_claim_registers_open_not_refused_as_mixed(tmp_path):
    """End to end — the EXACT claim shape `missing_tape._register_claim` builds
    (desk/scope/bench copied verbatim from `engine/missing_tape.py`), registered
    hermetically against `tmp_path` (`_register_claim` itself hardcodes the real
    repo root with no `root=` passthrough — a separate, pre-existing gap in that
    module's testability, out of this fix's scope — so the claim is built here
    and registered directly rather than calling `mt.emit`, which would otherwise
    write into the real `data/qledger/`). Never the mixed_markets refusal."""
    claim = q.make_claim(
        desk="missing_tape", asof="2026-08-05", scope_type="macro",
        scope_key="CN_CENSORSHIP_RISK", direction=0, horizon_d=21,
        horizon_unit=q.HORIZON_UNIT_TRADING, timestamp_quality="SNAPSHOT_DATE",
        bench="510300.SS", claim_family="missing_tape",
        extra={"risk_level": "NONE", "divergence_z": None, "is_context_only": True},
    )
    stored = q.register(claim, root=tmp_path)
    assert stored["status"] == q.STATUS_OPEN, stored.get("reject_reason")
    assert stored["clock_market"] == q.MARKET_CN
    assert stored["check_by"]


def test_sibling_sweep_no_other_symbolic_scope_key_desk_is_mixed_refused():
    """BLOCKER 2's sweep, made executable. Every OTHER live producer that
    pairs a non-suffixed scope key with an explicit bench (`basket_turn_cohort`
    — a bare ISO-date cohort id vs SPY; `build_whitehouse`'s WH_POLICY macro
    fallback vs SPY) resolves exactly as before: none of these are
    ticker-shaped, so none of them can originate a market either, and the
    named bench decides alone — the same fix, uniformly, not a per-producer
    patch."""
    for scope_key, bench, expect in (
            ("CN_CENSORSHIP_RISK", "510300.SS", q.MARKET_CN),   # missing_tape
            ("WH_POLICY", "SPY", q.MARKET_US),                  # build_whitehouse
            ("2026-10-15", "SPY", q.MARKET_US),                 # basket_turn_cohort
    ):
        claim = {"scope": {"type": "macro", "key": scope_key}, "bench": bench,
                 "control": None}
        assert q.resolve_claim_market(claim) == (expect, "")


# --------------------------------------------------------------------------- #
# ROUND 5 — MAJOR 1: _placebo_magnitude NO LONGER POOLS ACROSS CLOCK BASES
# --------------------------------------------------------------------------- #
def _placebo_claim(cid: str, path: str) -> dict:
    return {"claim_id": cid, "desk": "placebo", "is_placebo": True,
            "placebo_path": path, "event_id": f"e_{cid}"}


def test_placebo_magnitude_no_longer_pools_us_and_cn_grades():
    """BEFORE/AFTER, on the same fixture. THE DEFECT: a US-clock grade
    (excess=0.01) and a CN-clock grade (excess=0.99) on the SAME horizon used
    to average into one number (0.50) with no clock guard at all — exactly the
    pooling `require_single_clock`/`_aggregate` exist to forbid, on the
    control arm the whole 'beat placebo' comparison leans on. AFTER: the
    published cell is ONE basis's own honest mean, the other basis's own
    count is disclosed beside it, and 0.50 is not reachable by any reading."""
    claims = [_placebo_claim("u1", "covered_ticker"),
              _placebo_claim("c1", "covered_ticker")]
    us_grade = {"claim_id": "u1", "horizon_d": 5, "excess": 0.01,
               "horizon_unit": q.HORIZON_UNIT_TRADING,
               "clock_version": q.CLOCK_V1, "clock_market": q.MARKET_US}
    cn_grade = {"claim_id": "c1", "horizon_d": 5, "excess": 0.99,
               "horizon_unit": q.HORIZON_UNIT_TRADING,
               "clock_version": q.CLOCK_V1, "clock_market": q.MARKET_CN}

    # BEFORE (the reverted defect — mirrored here as a plain mean, never
    # called): summing both into one bucket the old way gives exactly 0.50.
    pooled_before = round((0.01 + 0.99) / 2, 6)
    assert pooled_before == 0.5

    out = q._placebo_magnitude(claims, [us_grade, cn_grade])
    cell = out["5"]
    assert cell["pooling_refused"] is True
    # THE SELECTION IS DETERMINISTIC AND PINNED TO ONE ANSWER. An earlier
    # version of this test asserted `clock_basis in (US, CN)` and
    # `mean_abs_excess in (0.01, 0.99)` — a test written to accept EITHER
    # answer, which does not pin behaviour, it records an ambiguity. It was
    # accepting a real one: `_placebo_magnitude` built its blocks by iterating
    # `grades` in append-only FILE ORDER and selected with `max`, which keeps
    # the first maximum — so on a tie the published placebo counterfactual
    # depended on which row was written first. Two bases' `n_grades` are
    # monotone integer counts, so during a migration they pass through equality
    # exactly once, and on that night the control arm could flip.
    #
    # The rule is now `_select_single_clock_block`'s: most n_grades, ties to the
    # newer clock, then alphabetically by basis. Both rows here have n_grades=1
    # and both are explicit, so the tie falls to the alphabetically first basis
    # — CN — whichever order the rows arrive in.
    cn_basis = q.clock_basis_key(q.CLOCK_V1, q.HORIZON_UNIT_TRADING, q.MARKET_CN)
    assert cell["clock_basis"] == cn_basis
    assert cell["overall"]["mean_abs_excess"] == 0.99      # CN's OWN number
    assert cell["overall"]["mean_abs_excess"] != pooled_before

    # ...and REVERSING the file order must not move the published cell.
    reversed_out = q._placebo_magnitude(claims, [cn_grade, us_grade])
    assert reversed_out["5"]["clock_basis"] == cell["clock_basis"]
    assert (reversed_out["5"]["overall"]["mean_abs_excess"]
            == cell["overall"]["mean_abs_excess"])

    # both bases' own counts stay visible, disclosed, never hidden
    assert cell["clock_bases_n_grades"] == {
        q.clock_basis_key(q.CLOCK_V1, q.HORIZON_UNIT_TRADING, q.MARKET_CN): 1,
        q.clock_basis_key(q.CLOCK_V1, q.HORIZON_UNIT_TRADING, q.MARKET_US): 1,
    }


def test_placebo_magnitude_single_basis_is_unchanged_by_the_split():
    """Negative control: while every placebo grade shares one clock basis (the
    live corpus today), the cell carries no refusal marker and no key that
    did not exist before this fix."""
    claims = [_placebo_claim("a", "covered_ticker"),
              _placebo_claim("b", "fallback_no_ticker")]
    grades = [{"claim_id": "a", "horizon_d": 5, "excess": 0.02},
             {"claim_id": "b", "horizon_d": 5, "excess": -0.04}]
    out = q._placebo_magnitude(claims, grades)
    cell = out["5"]
    assert "pooling_refused" not in cell
    assert cell["clock_basis"] == q.CLOCK_LEGACY
    assert cell["covered_ticker"]["mean_abs_excess"] == 0.02
    assert cell["fallback_no_ticker"]["mean_abs_excess"] == 0.04
    assert cell["overall"]["mean_abs_excess"] == 0.03
    assert cell["overall"]["n_grades"] == 2


# --------------------------------------------------------------------------- #
# ROUND 5 — MAJOR 2: PROMOTION REACHABLE PER MARKET, FROM PRODUCTION
# --------------------------------------------------------------------------- #
def test_emit_ladder_states_reaches_per_market_promotion(tmp_path):
    """`emit_ladder_states` — the ACTUAL production call path that gates
    SHADOW->CONFIRMER — used to call `promotion_check` with no `clock_basis`,
    so a bi-market family read STATE_MIXED_CLOCK/ineligible forever with no
    way out through this path, even though `promotion_check(clock_basis=...)`
    could always promote it per market. `by_clock_basis` closes that gap."""
    claims, grades = _two_market_store(n_us=26, n_cn=26)
    _write_store(tmp_path, claims, grades)

    states = q.emit_ladder_states(root=tmp_path, families=["f"])
    cell = states["f"]["21"]
    assert cell["current_state"] == q.STATE_MIXED_CLOCK
    assert cell["eligible"] is False, "the pooled default is still a refusal"

    per_market = cell["by_clock_basis"]
    assert set(per_market) == {_v1(market=q.MARKET_US), _v1(market=q.MARKET_CN)}
    for basis, res in per_market.items():
        assert res["eligible"] is True, (basis, res["reason"])
        assert res["n_dates"] == 26
        assert res["clock_basis"] == basis

    # negative control: a single-basis family carries no extra key at all
    single_claims, single_grades = _two_market_store(n_us=26, n_cn=0)
    _write_store(tmp_path, single_claims, single_grades)
    single_states = q.emit_ladder_states(root=tmp_path, families=["f"])
    assert "by_clock_basis" not in single_states["f"]["21"]


def test_compute_promotion_readiness_also_reaches_per_market(tmp_path):
    """The admin-tab-facing sibling of the same production gap
    (`scripts.grade_qledger.compute_promotion_readiness`)."""
    import scripts.grade_qledger as grader

    claims, grades = _two_market_store(n_us=26, n_cn=26)
    _write_store(tmp_path, claims, grades)
    readiness = grader.compute_promotion_readiness(tmp_path, families=["f"])
    cell = readiness["f"]["21"]
    assert cell["clock_migration"] is False
    per_market = cell["by_clock_basis"]
    assert set(per_market) == {_v1(market=q.MARKET_US), _v1(market=q.MARKET_CN)}
    assert all(r["ready"] for r in per_market.values())


def _legacy_plus_two_market_store(n_legacy: int, n_us: int, n_cn: int):
    """A family that holds the LEGACY basis alongside two explicit ones — the
    real shape of the corpus during the migration, once a second market starts
    accruing under the new clock while the pre-P0a rows are still on file."""
    claims, grades = _two_market_store(n_us=n_us, n_cn=n_cn)
    for i in range(n_legacy):
        cid = f"L{i}"
        claims.append({"claim_id": cid, "desk": "d", "claim_family": "f",
                       "asof": (date(2025, 1, 1) + timedelta(days=i)).isoformat(),
                       "is_placebo": False, "status": "open"})
        # no horizon_unit / clock_version / clock_market == CLOCK_LEGACY
        grades.append({"claim_id": cid, "horizon_d": 21, "excess": 0.05,
                       "hit": True, "subject_ret": 0.06, "bench_ret": 0.01,
                       "control_ret": 0.01})
    return claims, grades


def test_promotion_check_by_market_never_evaluates_the_legacy_basis(tmp_path):
    """THE DEFECT. The per-market escape hatch re-ran `promotion_check` once per
    key of `clock_prior_n_dates` — and that dict discloses EVERY basis the
    family holds, `CLOCK_LEGACY` included. So a family straddling the migration
    published a real, per-basis PROMOTION VERDICT computed on the legacy grading
    basis, into `ladder_states.<fam>.<h>.by_clock_basis`, where an `eligible`
    cell reads as authority earned.

    `_authority_clock_basis` refuses exactly this on the default path ("legacy +
    one v1 -> the v1 basis; legacy rows are not counted"), and the contract's
    whole premise is that a measurement-basis change RESETS authority rather
    than carrying it across. The escape hatch now inherits that rule.

    Note the legacy arm here is the LARGEST (40 dates vs 26 + 26) — exactly the
    real corpus's shape, and exactly the case where an n-ranked selection rule
    would have handed the legacy basis the headline."""
    claims, grades = _legacy_plus_two_market_store(n_legacy=40, n_us=26, n_cn=26)
    _write_store(tmp_path, claims, grades)

    mixed = q.promotion_check("f", 21, root=tmp_path, control_only=True)
    assert mixed.current_state == q.STATE_MIXED_CLOCK

    # THE DISCLOSURE IS UNCHANGED — the legacy history is still visible, and
    # still the biggest arm. This fix removes a VERDICT, never a disclosure.
    assert mixed.clock_prior_n_dates == {
        q.CLOCK_LEGACY: 40,
        _v1(market=q.MARKET_US): 26,
        _v1(market=q.MARKET_CN): 26,
    }

    per_market = q.promotion_check_by_market("f", 21, mixed, root=tmp_path,
                                             control_only=True)
    assert q.CLOCK_LEGACY not in per_market, (
        "a promotion verdict was computed on the legacy grading basis")
    assert set(per_market) == {_v1(market=q.MARKET_US), _v1(market=q.MARKET_CN)}
    assert all(r.eligible for r in per_market.values())

    # ...and the production surface that publishes it agrees.
    states = q.emit_ladder_states(root=tmp_path, families=["f"])
    published = states["f"]["21"]["by_clock_basis"]
    assert q.CLOCK_LEGACY not in published
    assert set(published) == {_v1(market=q.MARKET_US), _v1(market=q.MARKET_CN)}


def test_by_clock_basis_still_appears_when_only_explicit_bases_straddle(tmp_path):
    """Negative control for the filter: excluding the legacy basis must not
    empty the escape hatch. With no legacy rows at all, both markets are still
    re-evaluated and still promotable — so a green on the test above cannot be
    bought by returning `{}`."""
    claims, grades = _two_market_store(n_us=26, n_cn=26)
    _write_store(tmp_path, claims, grades)
    mixed = q.promotion_check("f", 21, root=tmp_path, control_only=True)
    per_market = q.promotion_check_by_market("f", 21, mixed, root=tmp_path,
                                             control_only=True)
    assert set(per_market) == {_v1(market=q.MARKET_US), _v1(market=q.MARKET_CN)}
    assert all(r.eligible for r in per_market.values())


# --------------------------------------------------------------------------- #
# ROUND 5 — MAJOR 3: THE MIGRATION BANNER NEVER FLAPS AND NEVER LIES ON A
# BI-MARKET SPLIT
# --------------------------------------------------------------------------- #
def test_a_bi_market_split_is_never_labelled_a_migration(tmp_path):
    """THE DEFECT. A family holding two EXPLICIT bases (two markets, both
    accruing forever) hit the STATE_MIXED_CLOCK branch, which unconditionally
    stamped `clock_migration=True` — a flag defined elsewhere in this same
    contract to mean 'there is a drop to explain, and it will clear once the
    corrected clock catches up'. A bi-market split never converges to one
    clock, so the flag could never clear: not a disclosure of a temporary
    state, a permanently false one. It is now False, and `reason` (not
    `migration_note`) carries the real, accurate prose."""
    claims, grades = _two_market_store(n_us=26, n_cn=26)
    _write_store(tmp_path, claims, grades)

    res = q.promotion_check("f", 21, root=tmp_path, control_only=True)
    assert res.current_state == q.STATE_MIXED_CLOCK
    assert res.clock_migration is False
    assert res.migration_note == ""
    # the disclosure is not lost — it just is not mislabelled as a migration
    assert res.clock_prior_n_dates == {
        _v1(market=q.MARKET_US): 26, _v1(market=q.MARKET_CN): 26}
    assert "no single explicit clock" in res.reason


def test_the_bi_market_banner_does_not_flap_across_two_consecutive_runs(tmp_path):
    """Acceptance #6. THE STORE MUST MOVE BETWEEN THE TWO READS, or this proves
    nothing: `promotion_check` is a pure function of the store, so calling it
    twice on identical bytes returns identical bytes by construction — the
    first cut of this test asserted exactly that, and would have stayed green
    against any flap a real night could produce.

    A nightly run reads a store that GREW since the last one. The flap this
    guards is the one that shipped: the bi-market branch stamped
    `clock_migration=True` unconditionally, so the banner appeared the night a
    second market's first grade landed and could never clear. So: run 1 on a
    single-market family (no banner), then grow the store the way a night does
    — CN's first rows arrive — and run 2 must still not claim a migration."""
    us_claims, us_grades = _two_market_store(n_us=26, n_cn=0)
    _write_store(tmp_path, us_claims, us_grades)
    run1 = q.promotion_check("f", 21, root=tmp_path, control_only=True)
    assert run1.current_state != q.STATE_MIXED_CLOCK
    assert run1.clock_migration is False

    # ...the next night, CN starts accruing under the same explicit clock.
    grown_claims, grown_grades = _two_market_store(n_us=26, n_cn=30)
    _write_store(tmp_path, grown_claims, grown_grades)
    run2 = q.promotion_check("f", 21, root=tmp_path, control_only=True)

    assert run2.current_state == q.STATE_MIXED_CLOCK, "the split is real"
    assert run2.clock_migration is False, (
        "a second market accruing is not a migration and never clears")
    assert run2.migration_note == ""
    assert run2.clock_prior_n_dates == {
        _v1(market=q.MARKET_US): 26, _v1(market=q.MARKET_CN): 30}
    # and a third read of the now-stable store still does not move
    run3 = q.promotion_check("f", 21, root=tmp_path, control_only=True)
    assert run3.as_dict() == run2.as_dict()


def test_the_admin_surface_never_renders_re_accruing_for_a_mixed_market_family(
        tmp_path, monkeypatch):
    """The consumer end: `experiments_registry` must not render the
    "RE-ACCRUING on a corrected clock ... not lost" sentence for a family that
    was never migrating anywhere — that sentence is FALSE for a stable
    bi-market split (there is no single corrected clock it is re-accruing on)."""
    import scripts.grade_qledger as grader
    from engine import experiments_registry as er

    claims, grades = _two_market_store(n_us=26, n_cn=26)
    _write_store(tmp_path, claims, grades)
    readiness = grader.compute_promotion_readiness(tmp_path, families=["f"])
    assert readiness["f"]["21"]["clock_migration"] is False

    monkeypatch.setattr(er, "_read_json",
                        lambda rel: {"promotion_readiness": readiness}
                        if rel.endswith("track_record.json") else {})
    out = er._refresh_qledger_promotion({"claim_family": "f"})
    assert out["clock_migration"] is False
    assert "RE-ACCRUING" not in out["state"]
    assert "migration_note" not in out


# --------------------------------------------------------------------------- #
# ROUND 5 — MUTATION CONTROL: revert provenance derivation to shape inference
# --------------------------------------------------------------------------- #
def test_mutant_reverting_provenance_to_shape_inference_is_caught(monkeypatch):
    """The kill-switch for a regression back to round 4's defect: if a future
    edit makes the no-suffix branch answer US again WITHOUT consulting
    provenance (i.e. re-introduces "no suffix -> US"), this must fail. Applied
    directly against `_ticker_market` so the mutant is exactly "ignore
    provenance, fall back to the old default" — the smallest edit that
    reproduces round 4's bug."""
    real = q._ticker_market

    def _reverted_no_suffix_defaults_to_us(ticker, provenance=None):
        # THE MUTANT: provenance is accepted but never consulted — the exact
        # round-4 shape of the bug (bare shape decides, silently, every time).
        t = str(ticker or "").strip().upper()
        if t and "." not in t:
            from engine.ticker_shape import plausible_symbol
            if plausible_symbol(t):
                return q.MARKET_US, ""
        return real(ticker, provenance)

    monkeypatch.setattr(q, "_ticker_market", _reverted_no_suffix_defaults_to_us)
    # the CN provenance test must now fail under the mutant...
    with pytest.raises(AssertionError):
        market, reason = q._ticker_market("600519", provenance=q.MARKET_CN)
        assert market == q.MARKET_CN
    # ...and the fail-closed test must fail too (the mutant resolves US instead
    # of refusing) — confirms the mutant is live, not merely present.
    market, _ = q._ticker_market("0700", provenance=None)
    assert market == q.MARKET_US, "mutant sanity: this is what the bug looked like"


# --------------------------------------------------------------------------- #
# REVIEW FINDINGS — the per-market fix was published into JSON and read by
# nothing, and the duel paired two independently-selected clock bases.
# --------------------------------------------------------------------------- #
def test_a_family_promotable_on_two_markets_reaches_the_operator(tmp_path):
    """THE DEFECT. `promotion_check_by_market` was added so a bi-market family
    "stuck at STATE_MIXED_CLOCK never reaches promotion on EITHER market". It
    wrote `by_clock_basis` into track_record.json — and every consumer read
    only the TOP-LEVEL `ready`, which is False for exactly that family. So on
    the first night two markets both cleared the 25-date bar, `run_status.json`
    reported `n_families_ready: 0` and no operator was told.

    Fixing it one layer up and leaving it broken one layer down is not fixing
    it. This asserts the summary the operator actually reads."""
    import scripts.grade_qledger as grader

    claims, grades = _two_market_store(n_us=26, n_cn=26)
    _write_store(tmp_path, claims, grades)
    readiness = grader.compute_promotion_readiness(tmp_path, families=["f"])

    # the pooled default still refuses — nothing here pools
    assert readiness["f"]["21"]["ready"] is False

    ready, approaching = grader._summarise_readiness(readiness)
    us = _v1(market=q.MARKET_US)
    cn = _v1(market=q.MARKET_CN)
    assert f"f@21d[{us}]" in ready, ready
    assert f"f@21d[{cn}]" in ready, ready
    # ...and the pooled key is NOT there: the refusal is still a refusal
    assert "f@21d" not in ready


def test_the_operator_summary_never_names_the_legacy_basis(tmp_path):
    """NEGATIVE CONTROL. Reading `by_clock_basis` must not become a back door
    to legacy authority: `promotion_check_by_market` already excludes
    `CLOCK_LEGACY`, and the summary excludes it again rather than trusting an
    upstream filter it does not own."""
    import scripts.grade_qledger as grader

    claims, grades = _legacy_plus_two_market_store(n_legacy=40, n_us=26, n_cn=26)
    _write_store(tmp_path, claims, grades)
    readiness = grader.compute_promotion_readiness(tmp_path, families=["f"])
    ready, approaching = grader._summarise_readiness(readiness)
    assert not any(q.CLOCK_LEGACY in k for k in ready + approaching), (
        ready, approaching)


def test_a_single_basis_family_summarises_exactly_as_before(tmp_path):
    """NEGATIVE CONTROL for the whole change: a family on ONE basis carries no
    `by_clock_basis` key at all, so the new loop contributes nothing and the
    summary is byte-identical to the pre-fix behaviour."""
    import scripts.grade_qledger as grader

    claims, grades = _two_market_store(n_us=26, n_cn=0)
    _write_store(tmp_path, claims, grades)
    readiness = grader.compute_promotion_readiness(tmp_path, families=["f"])
    assert "by_clock_basis" not in readiness["f"]["21"]
    ready, _ = grader._summarise_readiness(readiness)
    assert ready == ["f@21d"]


def test_the_duel_refuses_to_compare_two_different_clock_bases(tmp_path):
    """THE D3 COUNTERFACTUAL MUST NOT STRADDLE. `challenger_excess_mean_5d` and
    `placebo_covered_abs_excess_5d` are selected INDEPENDENTLY — each picks the
    basis with the most observations — so during a migration they can land on
    different clocks. Comparing a challenger measured on 5 exchange sessions
    against a placebo measured on 5 CALENDAR days is the pooling this contract
    forbids, wearing a comparison's clothes. Neither basis was recorded, so the
    mismatch was not merely unguarded — it was invisible."""
    import scripts.grade_qledger as grader

    tr = tmp_path / "site" / "qledger"
    tr.mkdir(parents=True)
    (tr / "track_record.json").write_text(json.dumps({
        "by_family": {"f": {"5": {"excess_mean": 0.02, "n_dates": 30,
                                  "wilson_ci_low": 0.4,
                                  "clock_basis": _v1(market=q.MARKET_US)}}},
        "placebo_magnitude": {"5": {"covered_ticker": {"mean_abs_excess": 0.01},
                                    "clock_basis": q.CLOCK_LEGACY}},
    }), encoding="utf-8")
    claims, grades = _two_market_store(n_us=26, n_cn=0)
    _write_store(tmp_path, claims, grades)

    ctx = grader.compute_promotion_readiness(
        tmp_path, families=["f"])["_duel_context"]["f"]
    assert ctx["duel_comparable"] is False
    assert ctx["challenger_clock_basis"] == _v1(market=q.MARKET_US)
    assert ctx["placebo_clock_basis"] == q.CLOCK_LEGACY
    assert "not a comparison" in ctx["duel_not_comparable_reason"]
    # the NUMBERS stay — each is honest on its own basis; the COMPARISON is
    # what is withdrawn.
    assert ctx["challenger_excess_mean_5d"] == 0.02
    assert ctx["placebo_covered_abs_excess_5d"] == 0.01


def test_the_duel_compares_normally_when_both_sides_share_a_basis(tmp_path):
    """NEGATIVE CONTROL: matching bases must still compare, or the guard would
    simply withdraw every duel and read as 'safe' while saying nothing."""
    import scripts.grade_qledger as grader

    tr = tmp_path / "site" / "qledger"
    tr.mkdir(parents=True)
    (tr / "track_record.json").write_text(json.dumps({
        "by_family": {"f": {"5": {"excess_mean": 0.02, "n_dates": 30,
                                  "wilson_ci_low": 0.4,
                                  "clock_basis": q.CLOCK_LEGACY}}},
        "placebo_magnitude": {"5": {"covered_ticker": {"mean_abs_excess": 0.01},
                                    "clock_basis": q.CLOCK_LEGACY}},
    }), encoding="utf-8")
    claims, grades = _two_market_store(n_us=26, n_cn=0)
    _write_store(tmp_path, claims, grades)

    ctx = grader.compute_promotion_readiness(
        tmp_path, families=["f"])["_duel_context"]["f"]
    assert ctx["duel_comparable"] is True
    assert "duel_not_comparable_reason" not in ctx


def test_promotion_on_a_legacy_only_family_is_the_documented_status_quo(tmp_path):
    """PINS WHAT THIS PR DOES **NOT** CHANGE, because the first draft of its own
    commit message overstated it.

    `_authority_clock_basis` returns the sole basis when a family has exactly
    one — and for every live family today that basis IS `CLOCK_LEGACY`, since no
    explicit-clock grade row exists yet. So `promotion_check` on the DEFAULT
    path does grant `eligible=True` with `clock_basis='legacy_calendar_unstamped'`.

    That is deliberate and is the status quo: refusing it would make every
    family on the board permanently un-promotable until it accrues 25 dates on
    the new clock, which is a fleet-wide product decision, not a side effect to
    slip into a clock-plumbing PR. What this PR narrows is strictly the
    STRADDLING case — `promotion_check_by_market` no longer mints a per-basis
    legacy verdict beside the real ones.

    This test exists so the boundary is asserted rather than assumed, and so a
    future change to it is a deliberate act with a failing test attached."""
    claims, grades = _legacy_plus_two_market_store(n_legacy=30, n_us=0, n_cn=0)
    _write_store(tmp_path, claims, grades)
    pr = q.promotion_check("f", 21, root=tmp_path, control_only=True)
    assert pr.clock_basis == q.CLOCK_LEGACY
    assert pr.current_state == q.STATE_GRADED
    assert pr.eligible is True, (
        "legacy-only promotion is the documented status quo; changing it is a "
        "fleet-wide decision, not a side effect of the clock contract")
# =========================================================================== #
# P0a-2 — THE MARKET RESOLVER, HARDENED
#
# The rule: PROVENANCE and TICKER SHAPE are two INDEPENDENT signals, NEITHER
# authoritative alone. Where both speak they must AGREE, or the leg is refused
# and counted. Five earlier rounds each let ONE source be sufficient and each
# failed a new way; the tests below pin the four holes that survived round 5.
#
# Every one of these is PROSPECTIVE. Measured against the live 46,630-claim
# corpus, this whole section changes the resolved market of ZERO claims — the
# shapes it refuses do not occur yet. That is the point: they are refused
# BEFORE a producer starts emitting them, not after a quarter of silent
# mis-grading.
# =========================================================================== #
def _mkclaim(desk, key, **kw):
    c = {"desk": desk, "claim_family": desk,
         "scope": {"type": "entity", "key": key}}
    c.update(kw)
    return c


def test_an_index_subject_no_longer_lets_the_default_bench_name_the_market():
    """THE DEFECT. `^HSI` fails `ticker_shape.plausible_symbol` (`^` is not in
    PLAUSIBLE_SYMBOL_RE), so round 5 read it as "contributes no market
    information, same as an absent leg" and skipped it. That left only the
    bench — which DEFAULTS to SPY — so a Hang Seng claim resolved US and would
    have graded on NYSE sessions against SPY, silently.

    `^HSI` now reads HK from `INDEX_MARKET`, which contradicts `radar`'s US
    provenance, so the claim is refused instead of silently mis-graded."""
    market, reason = q.resolve_claim_market(_mkclaim("radar", "^HSI"))
    assert market is None, "the Hang Seng resolved on somebody else's calendar"
    # MIXED, not "contradiction": the index names HK from its own enumerated
    # entry — a hard fact the desk table may not veto — and the claim's SPY
    # default bench names US, so the two LEGS span two markets and have no
    # single session ruler. That is the honest reason, and it is the same
    # answer for an unlisted desk as for an enumerated one.
    assert q.clock_reason_head(reason).startswith(q.MARKET_UNDETERMINED_MIXED)
    assert "HK" in reason and "US" in reason

    # ...and with no provenance in play, the index names its own market.
    assert q._ticker_market("^HSI") == (q.MARKET_HK, "")
    assert q._ticker_market("^GSPC") == (q.MARKET_US, "")
    assert q._ticker_market("^SSEC") == (q.MARKET_CN, "")


def test_an_unenumerated_index_symbol_is_refused_by_name_never_inferred():
    """`^HSI` and `^GSPC` are shaped identically and trade on different
    continents, so there is nothing in the STRING to infer a market from. An
    index this clock has no entry for is refused, by name, and counted."""
    market, reason = q._ticker_market("^N225")       # Nikkei — no HK/CN/US cal
    assert market is None
    assert q.clock_reason_head(reason) == q.MARKET_UNDETERMINED_UNKNOWN_INDEX
    assert "^N225" in reason, "the detail must name the offending symbol"
    # the symbol sits AFTER the separator, so it can never become a histogram key
    assert "^N225" not in q.clock_reason_head(reason)


def test_provenance_may_not_name_a_market_the_shape_positively_excludes():
    """THE ROUND-5 DEFECT, DIRECTLY. Round 5 made provenance the sole source
    for a no-suffix leg, so a US-listed desk emitting a bare A-share code
    resolved US — on NYSE sessions, silently. `valid_us_ticker` positively
    rejects a digit-first root, so US is EXCLUDED for `600519` no matter what
    the desk table says, and nothing else corroborates it."""
    market, reason = q.resolve_claim_market(_mkclaim("radar", "600519"))
    assert market is None
    assert q.clock_reason_head(reason).startswith(
        q.MARKET_UNDETERMINED_SHAPE_EXCLUDES)

    # The MIRROR case is refused too — provenance is not privileged in either
    # direction. A US-shaped ticker on a CN desk is equally a contradiction.
    market, reason = q.resolve_claim_market(_mkclaim("china_news", "AAPL"))
    assert market is None
    assert q.clock_reason_head(reason).startswith(
        q.MARKET_UNDETERMINED_CONTRADICTION)


def test_provenance_still_decides_a_bare_code_its_shape_admits():
    """The corroboration rule must not become a wall: the forward use case
    provenance exists FOR still works. A CN desk's bare `600519` is a 6-digit
    A-share code — a shape CN admits — so provenance decides it, and the claim
    resolves CN end to end when its bench is CN too."""
    claim = _mkclaim("china_news", "600519", bench="510300.SS")
    assert q.resolve_claim_market(claim) == (q.MARKET_CN, "")
    # ...and the leg-level call agrees
    assert q._ticker_market("600519", provenance=q.MARKET_CN) == (q.MARKET_CN, "")
    # HK's bare-code shape is admitted for HK and refused for CN
    assert q._ticker_market("0700", provenance=q.MARKET_HK) == (q.MARKET_HK, "")
    assert q._ticker_market("0700", provenance=q.MARKET_CN)[0] is None


def test_provenance_can_never_re_market_a_symbol_that_names_its_own():
    """The sharpest form of the round-5 inversion: under a CN desk, round 5
    resolved the string `SPY` ITSELF to CN, because provenance was consulted
    before the shape gate. A CN-priced claim benchmarked against SPY would then
    have graded the S&P 500 tracker on A-share sessions.

    SPY is a US symbol under every desk. The claim is refused (its two legs
    genuinely span two markets and have no single session ruler) — never
    silently re-marketed."""
    # SPY is a bare symbol: its US reading is an INFERENCE (valid_us_ticker), not
    # a hard exchange fact, so it is the weaker arm and a disagreeing provenance
    # refuses it. This is the arm where agree-or-refuse genuinely binds.
    assert q._ticker_market("SPY", provenance=q.MARKET_CN)[0] is None
    assert q._ticker_market("SPY", provenance=None) == (q.MARKET_US, "")
    assert q._ticker_market("SPY", provenance=q.MARKET_US) == (q.MARKET_US, "")

    # A hard exchange suffix outranks provenance — in the OTHER direction. The
    # suffix is direct evidence about the instrument and simply wins; the claim
    # is still refused, one level up, as MIXED (see the test below).
    assert q._ticker_market("600519.SS", provenance=q.MARKET_US) == (q.MARKET_CN, "")
    assert q._ticker_market("600519.SS", provenance=q.MARKET_CN) == (q.MARKET_CN, "")


def test_a_claim_with_no_subject_leg_is_refused_not_resolved_off_the_bench():
    """THE FAIL-OPEN. The subject was simply skipped when absent, leaving
    `_DEFAULT_BENCH` (SPY) to name US — so ANY malformed or half-built claim
    resolved US. `_validate_claim` already rejects a claim missing `scope.key`,
    so this is unreachable through registration; but `resolve_claim_market` is
    a public entry point, and this exact fail-open made a malformed probe report
    a defect that did not exist (research/EVAL_OS_P0A_HORIZON_CLOCK.md §3).

    A resolver whose answer is "US" for an empty claim is not fail-closed."""
    for empty in ({"desk": "radar", "scope": {"type": "entity"}},
                  {"desk": "radar", "scope": {"type": "entity", "key": ""}},
                  {"desk": "radar"},
                  {"desk": "radar", "scope": "not-a-dict"}):
        market, reason = q.resolve_claim_market(empty)
        assert market is None, f"resolved a market for {empty!r}"
        assert q.clock_reason_head(reason) == q.MARKET_UNDETERMINED_NO_SUBJECT

    # ...and the shape that made the original probe lie: scope_key at the TOP
    # level instead of inside `scope`. The resolver reads claim["scope"]["key"],
    # so this claim has no subject — and must say so rather than answer US.
    market, _ = q.resolve_claim_market(
        {"desk": "us_importance_v0", "claim_family": "us_importance_v0",
         "scope_key": "600519.SS", "scope_type": "entity"})
    assert market is None, "the malformed-probe fail-open is still open"


def test_a_symbolic_macro_label_still_contributes_nothing_rather_than_refusing():
    """NEGATIVE CONTROL for the index branch. A symbolic macro label is NOT an
    index: nothing is priced, so it carries nothing to corroborate or refuse and
    is read exactly like an absent leg — letting a leg that IS priced decide.
    Refusing it here would kill `missing_tape`'s `CN_CENSORSHIP_RISK` scope key
    beside its `510300.SS` bench, which round 5 fixed deliberately."""
    assert q._ticker_market("CN_CENSORSHIP_RISK") == (
        None, q.MARKET_UNDETERMINED_NO_LEG)
    claim = _mkclaim("missing_tape", "CN_CENSORSHIP_RISK", bench="510300.SS")
    assert q.resolve_claim_market(claim) == (q.MARKET_CN, "")


def test_the_shape_admissibility_predicates_are_mutually_exclusive():
    """The docstring claims the three per-market shape predicates never both
    accept one bare code. Pin it, rather than trusting the claim: a string two
    markets both admit would make `_shape_admits_market` a coin flip."""
    samples = ["600519", "000001", "300750", "0700", "9988", "5", "AAPL",
               "SPY", "BRK", "MSFT", "12345", "1234567"]
    for s in samples:
        admitted = [m for m in (q.MARKET_US, q.MARKET_CN, q.MARKET_HK)
                    if q._shape_admits_market(s, m)]
        assert len(admitted) <= 1, (s, admitted)
    # and the predicate fails CLOSED on a market it does not model
    assert q._shape_admits_market("AAPL", "CA") is False
    assert q._shape_admits_market("AAPL", "") is False


def test_corroborate_records_the_strength_of_every_call_site():
    """`_corroborate`'s `shape_is_decisive` distinguishes a hard exchange fact
    in the string from an inferred one. Both arms behave identically TODAY, so
    nothing else would catch the parameter rotting into a lie. Pin every call
    site's value at the source level: a new caller must make a deliberate
    choice, and an existing one cannot be flipped silently."""
    import inspect
    import re as _re
    src = inspect.getsource(q._ticker_market)
    calls = _re.findall(r"_corroborate\([^)]*shape_is_decisive=(\w+)", src)
    assert calls == ["True", "True", "True", "False"], calls
    # the sole False is the bare-symbol US inference; the three Trues are the
    # enumerated index, the mapped exchange suffix, and the share-class suffix.
    assert src.count("_corroborate(") == 4


def test_the_hardening_refuses_only_shapes_the_live_corpus_does_not_contain():
    """THE COST OF THIS PR, STATED AS A TEST. Every shape the live corpus
    actually holds must still resolve exactly as it did before — the refusals
    above are prospective, not a retroactive cull of the accrued record.

    The fixtures below are the shape CLASSES measured in the 46,630-claim store
    (a US ticker on a US desk against the SPY default; a suffixed CN ticker on
    a CN desk against a CN bench; a US-desk placebo; a CN-desk placebo). This
    asserts over FIXTURES, never over `data/qledger/claims.jsonl` — that store
    is append-only and nightly, so any assertion counting its rows or its
    outcomes can be falsified by tomorrow's append."""
    live_shapes = [
        (_mkclaim("us_importance_v0", "CARR"), q.MARKET_US),
        (_mkclaim("radar", "AAPL"), q.MARKET_US),
        (_mkclaim("intel_hub", "MSFT"), q.MARKET_US),
        (_mkclaim("altdata", "BRK.B"), q.MARKET_US),
        (_mkclaim("whitehouse", "LMT"), q.MARKET_US),
        (_mkclaim("policy", "XOM"), q.MARKET_US),
        (_mkclaim("placebo", "NVDA"), q.MARKET_US),
        (_mkclaim("cn_importance_v0", "600519.SS", bench="510300.SS"), q.MARKET_CN),
        (_mkclaim("cn_importance_v0_pit", "300024.SZ", bench="510300.SS"), q.MARKET_CN),
        (_mkclaim("china_news", "601398.SS", bench="510300.SS"), q.MARKET_CN),
        (_mkclaim("china_special_sits", "000001.SZ", bench="510300.SS"), q.MARKET_CN),
        (_mkclaim("placebo", "600519.SS", bench="510300.SS"), q.MARKET_CN),
    ]
    for claim, expect in live_shapes:
        market, reason = q.resolve_claim_market(claim)
        assert market == expect, (claim["desk"], claim["scope"]["key"], reason)

    # ...and the one shape class the live corpus DOES hold that must still
    # refuse: china_special_sits on a Beijing Stock Exchange ticker (4 claims).
    market, reason = q.resolve_claim_market(
        _mkclaim("china_special_sits", "920007.BJ", bench="510300.SS"))
    assert market is None
    assert q.clock_reason_head(reason).startswith(
        q.MARKET_UNDETERMINED_FOREIGN_EXCHANGE)


def test_a_hard_exchange_suffix_is_never_vetoed_by_provenance():
    """THE DEFECT WAS THIS CONTRACT'S OWN, AND ITS OWN TEST COULD NOT SEE IT.

    P0a-2's first cut documented `shape_is_decisive` as the seam between a hard
    exchange fact and a shape inference, threaded it through all four
    `_corroborate` call sites, and added
    `test_corroborate_records_the_strength_of_every_call_site` to pin every call
    site's value — then **never read the parameter in the function body**. Every
    caller got the agree-or-refuse arm, so a hard suffix was vetoed by a desk
    table:

        {'desk': 'china_news', 'scope': {'key': '0700.HK'}, 'bench': '2800.HK'}
            -> (None, 'shape_provenance_contradiction:HK!=CN')

    while the identical claim on the UNLISTED desk `altdata` resolved
    ('HK', ''). Admissibility depended on whether the desk happened to be
    enumerated — backwards — and since `DESK_MARKET` carries no HK entry while
    HK is a first-class market in `CLOCK_CALENDARS`, **no enumerated desk could
    ever claim a Hong Kong security.**

    The pinning test asserts the parameter's VALUE at each call site, never its
    EFFECT, so it is a guard that cannot fail on the defect it exists to gate.
    This test asserts the effect."""
    hk = {"scope": {"type": "entity", "key": "0700.HK"}, "bench": "2800.HK"}
    for desk in ("china_news", "cn_importance_v0", "radar", "whitehouse",
                 "policy", "us_importance_v0", "altdata", "narrative"):
        claim = dict(hk, desk=desk, claim_family=desk)
        assert q.resolve_claim_market(claim) == (q.MARKET_HK, ""), desk
    assert not any(v == q.MARKET_HK for v in q.DESK_MARKET.values()), (
        "if an HK desk is ever added, this test stops covering the case it "
        "exists for — the point is that HK resolves with NO provenance help")

    # The leg-level rule, at each of the three DECISIVE shape sources.
    assert q._ticker_market("0700.HK", provenance=q.MARKET_CN) == (q.MARKET_HK, "")
    assert q._ticker_market("600519.SS", provenance=q.MARKET_US) == (q.MARKET_CN, "")
    assert q._ticker_market("^HSI", provenance=q.MARKET_US) == (q.MARKET_HK, "")
    assert q._ticker_market("BRK.B", provenance=q.MARKET_CN) == (q.MARKET_US, "")

    # ...and the INFERRED arm still binds: a bare symbol's US reading is not a
    # hard fact, so a disagreeing provenance refuses it.
    assert q._ticker_market("AAPL", provenance=q.MARKET_CN)[0] is None


def test_a_genuinely_cross_market_claim_is_still_refused_as_mixed():
    """NEGATIVE CONTROL for the fix above: letting a hard suffix win must NOT
    let a two-market claim through. It is caught one level up, by
    `resolve_claim_market`'s MIXED refusal, and that is the honest reason — the
    two legs have no single session ruler, which is a fact about the CLAIM, not
    a disagreement between two classifiers."""
    for desk, key, bench in (
            ("us_importance_v0", "600519.SS", "SPY"),
            ("radar", "^HSI", "SPY"),
            ("china_news", "0700.HK", "510300.SS"),
            ("altdata", "600519.SS", "SPY")):
        claim = {"desk": desk, "claim_family": desk,
                 "scope": {"type": "entity", "key": key}, "bench": bench}
        market, reason = q.resolve_claim_market(claim)
        assert market is None, (desk, key, bench)
        assert q.clock_reason_head(reason).startswith(
            q.MARKET_UNDETERMINED_MIXED), (desk, key, reason)
