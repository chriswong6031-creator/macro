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
    resolver, no second implementation;
  * one window is SHARED by subject, bench and control, so no leg silently
    receives a different horizon length;
  * LEGACY (unitless) claims keep the pre-P0a arithmetic exactly and are stamped
    as the legacy basis, never re-labelled;
  * observations from different clock bases CANNOT be pooled — the aggregation
    primitive raises and the promotion gate refuses.

Hermetic: tmp_path store, synthetic session-indexed prices monkeypatched onto
the shared parquet layer. Nothing reads or asserts over data/qledger — the
nightly-appended store is never a fixture.
"""
from __future__ import annotations

from datetime import date, timedelta

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


def test_promotion_gate_refuses_a_family_that_straddles_two_clocks(tmp_path, monkeypatch):
    """Authority may not ride a selected basis. The display tier keeps reading
    (select-and-label); the promotion gate returns INELIGIBLE and says why."""
    claims = [{"claim_id": f"c{i}", "desk": "d", "claim_family": "f",
               "asof": f"2026-01-{i + 1:02d}", "is_placebo": False}
              for i in range(30)]
    grades = [_grade_row(None if i % 2 else q.HORIZON_UNIT_TRADING,
                         cid=f"c{i}", excess=0.05, hit=True) for i in range(30)]
    monkeypatch.setattr(q, "load_claims", lambda root=None: claims)
    monkeypatch.setattr(q, "load_grades", lambda root=None: grades)

    res = q.promotion_check("f", 21, root=tmp_path)
    assert res.eligible is False
    assert res.current_state == q.STATE_MIXED_CLOCK
    assert "refusing to pool" in res.reason
    # Negative control: the SAME rows on one basis clear the gate, so the
    # refusal above is the clock check firing and not an unrelated failure.
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
