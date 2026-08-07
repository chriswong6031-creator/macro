"""GAP DISCIPLINE — the polygon_gex family reads N-session endpoints by CALENDAR.

`data/polygon_gex/` is chronically gapped: measured over 2026-06-15..08-06 (37 NYSE
sessions, 418 stores) SIX sessions hold zero rows in ANY store — 07-06, 07-15, 07-17,
and the unrecoverable 08-03..08-05 collection outage (the snapshot API is current-only).
Every site below sliced that store POSITIONALLY while labelling the result with a
session count, so each shipped a wider basis than it claimed.

EVERY fixture here reproduces the real outage geometry — six rows spanning NINE sessions
(2026-07-27..08-06) — and every test carries a PREMISE assertion pinning that span. A
gap fixture that silently becomes dense would make these tests pass for the wrong reason
and the defect would walk back in unnoticed; the premise assertion is what makes the
fixture unable to rot vacuous.

Expectations are OPPOSITE-SIGN wherever a value is produced: the positional answer and
the calendar answer do not merely differ in magnitude, they point the other way. That is
the property that makes this class dangerous rather than cosmetic — on the live screener
at as_of 2026-08-06 it flipped the sign of 80 of 375 published numbers.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from lib import nyse_calendar as nc

# ── the real outage geometry ────────────────────────────────────────────────
# Six stored sessions spanning nine: 07-31 -> 08-06 skips 08-03, 08-04, 08-05.
GAPPED = [dt.date(2026, 7, 27), dt.date(2026, 7, 28), dt.date(2026, 7, 29),
          dt.date(2026, 7, 30), dt.date(2026, 7, 31), dt.date(2026, 8, 6)]
# The same six rows with no gap, where positional and calendar MUST agree.
DENSE = [dt.date(2026, 7, 23), dt.date(2026, 7, 24), dt.date(2026, 7, 27),
         dt.date(2026, 7, 28), dt.date(2026, 7, 29), dt.date(2026, 7, 30)]


def _premise_gapped():
    """Pin the fixture's geometry so it cannot quietly become dense."""
    assert len(GAPPED) == 6, "fixture must hold exactly six rows"
    assert nc.sessions_apart(GAPPED[0], GAPPED[-1]) == 8, (
        "fixture must span NINE sessions inclusive (eight steps) — the 08-03..08-05 "
        "outage. A dense fixture would make positional and calendar agree and every "
        "assertion below would pass without testing anything.")
    assert nc.session_n_back(GAPPED[-1], 5) == dt.date(2026, 7, 30)
    assert GAPPED[-6] == dt.date(2026, 7, 27), "positional -6 must be the WRONG session"
    assert nc.session_n_back(GAPPED[-1], 5) != GAPPED[-6]


def _premise_dense():
    assert nc.sessions_apart(DENSE[0], DENSE[-1]) == 5, "control fixture must be gapless"
    assert nc.session_n_back(DENSE[-1], 5) == DENSE[-6] == DENSE[0]


# ═══════════════════════════════════════════════════════════════════════════
# lib/nyse_calendar — the shared resolvers
# ═══════════════════════════════════════════════════════════════════════════
def test_premise_fixtures_are_what_they_claim():
    _premise_gapped()
    _premise_dense()


def test_session_n_back_resolves_by_calendar_not_position():
    _premise_gapped()
    assert nc.session_n_back(dt.date(2026, 8, 6), 5) == dt.date(2026, 7, 30)
    assert nc.session_n_back(dt.date(2026, 8, 6), 0) == dt.date(2026, 8, 6)
    # A Saturday has no session-relative answer — fail CLOSED, never a nearby guess.
    assert nc.session_n_back(dt.date(2026, 8, 8), 5) is None
    with pytest.raises(ValueError):
        nc.session_n_back(dt.date(2026, 8, 6), -1)


def test_session_n_forward_is_the_mirror():
    assert nc.session_n_forward(dt.date(2026, 7, 30), 5) == dt.date(2026, 8, 6)
    assert nc.session_n_forward(dt.date(2026, 8, 8), 5) is None


def test_sessions_apart_and_is_prior_session():
    # The live pair on the board today: four sessions apart, not adjacent.
    assert nc.sessions_apart(dt.date(2026, 7, 31), dt.date(2026, 8, 6)) == 4
    assert nc.is_prior_session(dt.date(2026, 7, 31), dt.date(2026, 8, 6)) is False
    assert nc.is_prior_session(dt.date(2026, 8, 5), dt.date(2026, 8, 6)) is True
    assert nc.sessions_apart(dt.date(2026, 8, 6), dt.date(2026, 7, 31)) is None   # reversed
    assert nc.is_prior_session(dt.date(2026, 8, 8), dt.date(2026, 8, 10)) is False  # Sat


def test_row_n_sessions_back_returns_the_dated_row_and_refuses_on_a_gap():
    _premise_gapped()
    s = pd.Series([1.0, 2, 3, 4, 5, 6], index=pd.to_datetime(GAPPED))
    assert nc.row_n_sessions_back(s, 5) == 4.0      # 07-30, NOT 1.0 at the positional -6
    assert s.iloc[-6] == 1.0, "positional would have used the 07-27 row"

    df = pd.DataFrame({"v": [1.0, 2, 3, 4, 5, 6]}, index=pd.to_datetime(GAPPED))
    assert float(nc.row_n_sessions_back(df, 5)["v"]) == 4.0

    # Target session absent entirely -> refuse. 5 back from 07-13 is 07-06, a session
    # for which NO store holds a row (one of the six measured zero-row sessions).
    absent = [dt.date(2026, 7, 2), dt.date(2026, 7, 7), dt.date(2026, 7, 8),
              dt.date(2026, 7, 9), dt.date(2026, 7, 10), dt.date(2026, 7, 13)]
    assert nc.session_n_back(absent[-1], 5) == dt.date(2026, 7, 6)
    assert dt.date(2026, 7, 6) not in absent, "premise: the 5-back target is missing"
    assert nc.row_n_sessions_back(pd.Series(range(6), index=pd.to_datetime(absent)), 5) is None


def test_row_n_sessions_back_reads_a_date_column():
    _premise_gapped()
    df = pd.DataFrame({"date": [d.isoformat() for d in GAPPED], "v": [1.0, 2, 3, 4, 5, 6]})
    assert float(nc.row_n_sessions_back(df, 5, date_col="date")["v"]) == 4.0
    assert nc.row_n_sessions_back(df, 5, date_col="nope") is None


def test_numbers_are_rejected_not_coerced_to_epoch_dates():
    """`pd.Timestamp(0)` is 1970-01-01, so a RangeIndex would answer every session
    question confidently and wrongly. Regression: this silently NaN'd out all of
    validate_gex's forward RV on undated frames."""
    assert nc.as_day(0) is None and nc.as_day(5) is None and nc.as_day(1.5) is None
    assert nc.as_day(np.int64(3)) is None, "numpy scalars too"
    assert nc.as_day(True) is None, "bool is an int subclass"
    assert nc.as_day("2026-08-06") == dt.date(2026, 8, 6)
    assert nc.as_day(pd.Timestamp("2026-08-06")) == dt.date(2026, 8, 6)
    assert nc.as_day(None) is None and nc.as_day("not-a-date") is None
    # An undated frame must REFUSE, never resolve into 1970.
    assert nc.row_n_sessions_back(pd.Series(range(6)), 5) is None

    from scripts import validate_gex as V
    assert V._session_steps(list(range(6)), 6) is None, (
        "a RangeIndex must degrade to row-steps, not become epoch dates")


def test_session_ordinals_place_gapped_rows_at_true_x():
    _premise_gapped()
    assert nc.session_ordinals(GAPPED) == [0, 1, 2, 3, 4, 8]
    assert nc.session_ordinals(DENSE) == [0, 1, 2, 3, 4, 5]


# ═══════════════════════════════════════════════════════════════════════════
# SITE 1 — scripts/build_options_screener._compute_iv30_chg_5d  (PUBLIC surface)
# ═══════════════════════════════════════════════════════════════════════════
def _iv_frame(dates, vals):
    return pd.DataFrame({"iv30": vals}, index=pd.to_datetime(dates))


def test_site1_screener_iv30_chg_flips_sign_under_calendar_resolution():
    from scripts import build_options_screener as B
    _premise_gapped()
    # 07-27 high, 07-30 low, 08-06 middling: positional reads DOWN, calendar reads UP.
    vals = [0.30, 0.28, 0.26, 0.20, 0.22, 0.25]
    got = B._compute_iv30_chg_5d(_iv_frame(GAPPED, vals))
    assert got == pytest.approx((0.25 - 0.20) * 100, abs=1e-6)
    assert got > 0, "calendar (vs 07-30) must read as rising IV"
    positional = (vals[-1] - vals[-6]) * 100
    assert positional < 0, "positional (vs 07-27) read as FALLING IV — the opposite sign"


def test_site1_screener_refuses_when_the_five_back_session_is_absent():
    from scripts import build_options_screener as B
    absent = [dt.date(2026, 7, 2), dt.date(2026, 7, 7), dt.date(2026, 7, 8),
              dt.date(2026, 7, 9), dt.date(2026, 7, 10), dt.date(2026, 7, 13)]
    assert nc.session_n_back(absent[-1], 5) == dt.date(2026, 7, 6) not in absent
    assert B._compute_iv30_chg_5d(_iv_frame(absent, [0.1, 0.2, 0.3, 0.4, 0.5, 0.6])) is None


def test_site1_screener_agrees_with_positional_on_a_dense_store():
    from scripts import build_options_screener as B
    _premise_dense()
    vals = [0.30, 0.28, 0.26, 0.20, 0.22, 0.25]
    assert B._compute_iv30_chg_5d(_iv_frame(DENSE, vals)) == pytest.approx(
        (vals[-1] - vals[0]) * 100, abs=1e-6)


def test_site1_dropna_does_not_smuggle_the_endpoint_further_back():
    """The screener is the LOOSEST reader of the family: it dropna()s first, so a hole
    in iv30 used to slide the positional endpoint back another session."""
    from scripts import build_options_screener as B
    dates = [dt.date(2026, 7, 24)] + GAPPED           # seven rows, one of them null
    vals = [0.99, np.nan, 0.28, 0.26, 0.20, 0.22, 0.25]
    assert pd.isna(vals[1]), "premise: the 07-27 reading is a hole"
    got = B._compute_iv30_chg_5d(_iv_frame(dates, vals))
    assert got == pytest.approx((0.25 - 0.20) * 100, abs=1e-6), "still resolves to 07-30"


# ═══════════════════════════════════════════════════════════════════════════
# SITE 2 — engine/options_dislocation: d5_* + the unfiltered chain reader
# ═══════════════════════════════════════════════════════════════════════════
def _panel(dates, vals, name="AAA"):
    return pd.DataFrame({"date": [d.isoformat() for d in dates],
                         "underlying": [name] * len(dates), "skew": vals})


def test_site2_d5_flips_sign_under_calendar_resolution():
    from engine import options_dislocation as D
    _premise_gapped()
    vals = [0.30, 0.28, 0.26, 0.20, 0.22, 0.25]
    P = _panel(GAPPED, vals)
    out = D._d5_by_session(P, "skew")
    assert out.iloc[-1] == pytest.approx(0.25 - 0.20, abs=1e-9)
    assert out.iloc[-1] > 0
    assert (vals[-1] - vals[-6]) < 0, "positional diff(5) had the opposite sign"
    # Rows without a resolvable 5-back endpoint are null, not approximated.
    assert out.iloc[:-1].isna().all()


def test_site2_d5_refuses_when_the_endpoint_session_is_missing():
    from engine import options_dislocation as D
    absent = [dt.date(2026, 7, 2), dt.date(2026, 7, 7), dt.date(2026, 7, 8),
              dt.date(2026, 7, 9), dt.date(2026, 7, 10), dt.date(2026, 7, 13)]
    # 5 back from 07-13 is 07-06 — one of the six measured zero-row sessions.
    assert nc.session_n_back(absent[-1], 5) == dt.date(2026, 7, 6) not in absent
    vals = [0.10, 0.20, 0.30, 0.40, 0.50, 0.60]
    out = D._d5_by_session(_panel(absent, vals), "skew")
    assert pd.isna(out.iloc[-1]), "the as_of whose 5-back session is missing must refuse"
    assert vals[-1] - vals[-6] == pytest.approx(0.50), (
        "premise: the positional read WOULD have produced a number — the refusal is a "
        "real behaviour change, not a no-op on already-null data")
    # 07-10's own 5-back IS present (07-02, since 07-03 is the observed July-4 holiday),
    # so calendar resolution keeps it — refusal is targeted, not blanket.
    assert nc.session_n_back(dt.date(2026, 7, 10), 5) == dt.date(2026, 7, 2)
    assert out.iloc[4] == pytest.approx(0.50 - 0.10, abs=1e-9)


def test_site2_dated_chains_drops_non_session_snapshots(tmp_path, monkeypatch):
    """The reader had NO session filter, which is why diff(5) spans of THREE and FOUR
    sessions outnumbered the correct five in the committed panel."""
    from lib import config
    from engine import options_dislocation as D
    d = tmp_path / "polygon_gex" / "chains"
    d.mkdir(parents=True)
    weekend = dt.date(2026, 8, 1)               # Saturday
    assert not nc.is_session(weekend), "premise: fixture date must be a non-session"
    for day in (dt.date(2026, 7, 31), weekend, dt.date(2026, 8, 6)):
        pd.DataFrame({"underlying": ["AAA"]}).to_parquet(d / f"{day.isoformat()}.parquet")
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    got = set(D._dated_chains())
    assert got == {"2026-07-31", "2026-08-06"}
    assert weekend.isoformat() not in got


def test_site2_coverage_floor_nulls_a_date_rather_than_ranking_survivors(capsys):
    """The null is date-WIDE — every name reads the same store on the same schedule — so
    the handful that survive a gap are coverage-SELECTED, not a sample."""
    from engine import options_dislocation as D
    # Eight sessions of history so the gapped names remain CANDIDATES (>= 6 own
    # sessions) — the real failure mode is a name with plenty of history that is
    # missing the ONE session its basis needs, not a name that is simply too young.
    dates = [dt.date(2026, 7, 23), dt.date(2026, 7, 24), dt.date(2026, 7, 27),
             dt.date(2026, 7, 28), dt.date(2026, 7, 29), dt.date(2026, 7, 30),
             dt.date(2026, 7, 31), dt.date(2026, 8, 6)]
    rows = []
    for i in range(10):                          # 10 names, only ONE keeps the 5-back row
        keep = dates if i == 0 else [x for x in dates if x != dt.date(2026, 7, 30)]
        for d in keep:
            rows.append({"date": d.isoformat(), "underlying": f"N{i}", "skew": float(i + 1)})
    P = pd.DataFrame(rows)
    assert (P[P["underlying"] == "N1"].shape[0] >= 6), "premise: gapped names are candidates"
    P["d5_skew"] = D._d5_by_session(P, "skew")
    last = P["date"] == "2026-08-06"
    assert P.loc[last, "d5_skew"].notna().sum() == 1, "premise: exactly one survivor"
    assert P.loc[last].shape[0] == 10, "premise: ten candidates on the date"
    D._apply_coverage_floor(P, ["d5_skew"])
    assert P.loc[last, "d5_skew"].isna().all(), "1 of 10 is below the 50% floor"
    out = capsys.readouterr().out
    assert out.startswith("::warning") or "\n::warning" in out
    assert "dislocation-d5-coverage" in out


def test_site2_coverage_floor_leaves_a_healthy_date_alone(capsys):
    from engine import options_dislocation as D
    dates = [dt.date(2026, 7, 23), dt.date(2026, 7, 24)] + GAPPED
    rows = [{"date": d.isoformat(), "underlying": f"N{i}", "skew": float(i + 1)}
            for i in range(10) for d in dates]
    P = pd.DataFrame(rows)
    P["d5_skew"] = D._d5_by_session(P, "skew")
    last = P["date"] == "2026-08-06"
    assert P.loc[last, "d5_skew"].notna().sum() == 10, "premise: full coverage"
    D._apply_coverage_floor(P, ["d5_skew"])
    assert P.loc[last, "d5_skew"].notna().all()
    assert "dislocation-d5-coverage" not in capsys.readouterr().out


# ═══════════════════════════════════════════════════════════════════════════
# SITE 3 — scripts/validate_gex._fwd_rv  (FIT/WINDOW: re-weight, never refuse)
# ═══════════════════════════════════════════════════════════════════════════
def test_site3_fwd_rv_scales_returns_by_elapsed_sessions():
    """A FIT is re-weighted, not refused: the gap return is divided by sqrt(Δsessions)
    so it enters the variance as a per-session quantity instead of a 4× outlier."""
    from scripts import validate_gex as V
    # A TWO-session step, deliberately small enough to survive the span cap — the two
    # mechanisms are separate and this test must observe scaling, not the cap.
    dates = [dt.date(2026, 7, 27), dt.date(2026, 7, 28), dt.date(2026, 7, 29),
             dt.date(2026, 7, 30), dt.date(2026, 7, 31), dt.date(2026, 8, 4)]
    assert nc.sessions_apart(dates[-2], dates[-1]) == 2, "premise: the last step is 2 sessions"
    assert 1 + 2 <= V.MAX_WINDOW_STRETCH * 2, "premise: this window must clear the span cap"
    spot = pd.Series([100.0, 101, 102, 103, 104, 120], index=pd.to_datetime(dates))
    steps = V._session_steps(dates, len(spot))
    assert steps[-1] == 2.0 and steps[1] == 1.0
    scaled = V._fwd_rv(spot, 2, dates)
    naive = V._fwd_rv(spot, 2, ["x"] * len(spot))         # unusable labels -> old behaviour
    both = scaled.notna() & naive.notna()
    assert both.any(), "premise: the gap window must survive the cap and be comparable"
    assert (scaled[both] < naive[both]).any(), (
        "the gap-spanning return must contribute LESS after per-session scaling")


def test_site3_session_steps_refuses_unusable_labels():
    from scripts import validate_gex as V
    assert V._session_steps(["x", "y", "z"], 3) is None, (
        "degrade to row-steps rather than divide by garbage")


def test_site3_fwd_rv_span_cap_drops_an_overstretched_window():
    from scripts import validate_gex as V
    dates = [dt.date(2026, 6, 15), dt.date(2026, 6, 16), dt.date(2026, 7, 31),
             dt.date(2026, 8, 4), dt.date(2026, 8, 5), dt.date(2026, 8, 6)]
    assert nc.sessions_apart(dates[1], dates[2]) > 2 * 2, "premise: window blows the cap"
    spot = pd.Series([100.0, 101, 102, 103, 104, 105], index=pd.to_datetime(dates))
    rv = V._fwd_rv(spot, 2, dates)
    assert rv.isna().iloc[0], "a window spanning >2x its nominal sessions is not an h-day RV"


def test_site3_evaluate_filters_non_session_rows():
    from scripts import validate_gex as V
    sat = dt.date(2026, 8, 1)
    assert not nc.is_session(sat)
    idx = [dt.date(2026, 7, 29), dt.date(2026, 7, 30), dt.date(2026, 7, 31), sat,
           dt.date(2026, 8, 6)]
    d = pd.DataFrame({"spot": [1.0, 2, 3, 3, 4],
                      "gamma_regime": ["long"] * 5}, index=pd.to_datetime(idx))
    lines = V.evaluate("AAA", d, store_label="polygon_gex")
    assert any("n=4" in ln for ln in lines), (
        f"the Saturday row must be dropped before any statistic; got {lines}")


# ═══════════════════════════════════════════════════════════════════════════
# SITE 4 — engine/neuralweb/options_plane._trend  (n=1 == COMPARE)
# ═══════════════════════════════════════════════════════════════════════════
def test_site4_velocity_is_null_across_a_gap_but_trend_survives():
    from engine.neuralweb import options_plane as OP
    hist = [{"date": "2026-07-29", "net_gex_bn": -10.21},
            {"date": "2026-07-30", "net_gex_bn": -16.30},
            {"date": "2026-07-31", "net_gex_bn": -6.16}]
    assert nc.sessions_apart(dt.date(2026, 7, 31), dt.date(2026, 8, 6)) == 4, "premise"
    trend, vel = OP._trend(hist, -8.0, asof="2026-08-06")
    assert vel is None, "a FOUR-session move must not be published as regime_velocity_1d"
    assert trend in {"strengthening", "weakening", "stable"}, (
        "the magnitude read carries no day-count claim and survives the gap")


def test_site4_velocity_publishes_when_the_prior_row_is_yesterday():
    from engine.neuralweb import options_plane as OP
    hist = [{"date": "2026-08-03", "net_gex_bn": -4.0},
            {"date": "2026-08-04", "net_gex_bn": -10.0},
            {"date": "2026-08-05", "net_gex_bn": -16.0}]
    assert len(hist) >= OP._TREND_MIN_SESSIONS, "premise: clears the trend history floor"
    assert nc.is_prior_session(dt.date(2026, 8, 5), dt.date(2026, 8, 6))
    _, vel = OP._trend(hist, -8.0, asof="2026-08-06")
    assert vel == pytest.approx(-8.0 - (-16.0), abs=1e-9)


def test_site4_a_weekend_row_cannot_pose_as_yesterday():
    from engine.neuralweb import options_plane as OP
    sat = dt.date(2026, 8, 1)
    assert not nc.is_session(sat)
    hist = [{"date": "2026-07-30", "net_gex_bn": -10.0},
            {"date": "2026-07-31", "net_gex_bn": -16.0},
            {"date": sat.isoformat(), "net_gex_bn": -16.0}]
    _, vel = OP._trend(hist, -8.0, asof="2026-08-03")
    assert vel is None


# ═══════════════════════════════════════════════════════════════════════════
# SITE 5 — scripts/build_flow_leaders: oi_confirm's "next day d+1"  (COMPARE)
# ═══════════════════════════════════════════════════════════════════════════
def _chains(root: Path, days) -> None:
    d = root / "polygon_gex" / "chains"
    d.mkdir(parents=True, exist_ok=True)
    for day in days:
        pd.DataFrame({"underlying": ["AAA"], "K": [100.0], "is_call": [True],
                      "volume": [10.0], "oi": [5.0]}).to_parquet(
            d / f"{day.isoformat()}.parquet")


def test_site5_refuses_a_non_adjacent_chain_pair(tmp_path, capsys):
    """This is the pair the live board holds TODAY: 07-31 -> 08-06, four sessions."""
    from scripts import build_flow_leaders as F
    _chains(tmp_path, [dt.date(2026, 7, 30), dt.date(2026, 7, 31), dt.date(2026, 8, 6)])
    assert nc.sessions_apart(dt.date(2026, 7, 31), dt.date(2026, 8, 6)) == 4, "premise"
    a, b = F._load_two_chain_days(tmp_path)
    assert a.empty and b.empty, "a d+1 OI confirmation cannot be read across a gap"
    out = capsys.readouterr().out
    assert "::warning" in out and "oi-confirm-nonadjacent" in out


def test_site5_publishes_an_adjacent_pair(tmp_path):
    from scripts import build_flow_leaders as F
    _chains(tmp_path, [dt.date(2026, 8, 4), dt.date(2026, 8, 5), dt.date(2026, 8, 6)])
    assert nc.is_prior_session(dt.date(2026, 8, 5), dt.date(2026, 8, 6))
    a, b = F._load_two_chain_days(tmp_path)
    assert not a.empty and not b.empty


# ═══════════════════════════════════════════════════════════════════════════
# SITE 6 — validate_options_skew / _ivspread: the forward endpoint
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("mod,col", [
    ("scripts.validate_options_skew", "skew"),
    ("scripts.validate_options_ivspread", "ivspread"),
])
def test_site6_forward_endpoint_is_resolved_by_calendar(mod, col):
    """A horizon study may only score pairings that really are h sessions apart.

    The panel below is the store's own July geometry — 12 stored sessions with the three
    measured zero-row sessions (07-06, 07-15, 07-17) missing. Positionally EVERY date but
    the last five looks evaluable (7 of them); by calendar only 6 have a real +5-session
    endpoint. The count is the guard: a positional run silently scores a 7th date whose
    "5-day" forward return is actually six or seven sessions long.
    """
    import importlib
    M = importlib.import_module(mod)
    names = [f"N{i}" for i in range(12)]
    panel_dates = [dt.date(2026, 7, d) for d in
                   (1, 2, 7, 8, 9, 10, 13, 14, 16, 20, 21, 22)]
    for missing in (dt.date(2026, 7, 6), dt.date(2026, 7, 15), dt.date(2026, 7, 17)):
        assert nc.is_session(missing) and missing not in panel_dates, (
            f"premise: {missing} is a real session the store does not hold")
    # Which dates have a genuine +5-session endpoint inside the panel.
    reachable = [d for d in panel_dates
                 if nc.session_n_forward(d, 5) in set(panel_dates)]
    assert len(reachable) == 6, f"premise: expected 6 calendar-evaluable dates, got {reachable}"
    assert len(panel_dates) - 5 == 7, "premise: the positional loop would score 7"
    assert dt.date(2026, 7, 8) not in reachable, (
        "premise: 07-08's true endpoint 07-15 is one of the missing sessions")

    rows = []
    for k, d in enumerate(panel_dates):
        for j, n in enumerate(names):
            # Spot varies by BOTH name and date so forward returns are non-degenerate;
            # a constant panel would make rank_ic NaN and the test vacuous.
            rows.append({"date": d.isoformat(), "underlying": n,
                         col: float(j), "spot": 100.0 + j * (k + 1)})
        rows.append({"date": d.isoformat(), "underlying": "SPY", col: 0.0, "spot": 100.0})
    panel = pd.DataFrame(rows)
    assert len(names) >= 10, "premise: clears the joint-name floor inside _fwd_ic"

    res = M._fwd_ic(panel, 5)
    assert res.get("n_dates", 0) == 6, (
        "only the six dates with a real 5-session endpoint may be scored; the positional "
        "reading scores 7, the extra one over a stretched horizon")


@pytest.mark.parametrize("mod,col", [
    ("scripts.validate_options_skew", "skew"),
    ("scripts.validate_options_ivspread", "ivspread"),
])
def test_fwd_ic_survives_a_none_hac_t(mod, col):
    """Incidental, surfaced by the mutation check: `ic_summary` returns ``t_hac=None``
    at n=6 and `_fwd_ic` called ``float()`` on it, raising TypeError. Unreachable only
    because the gate has never held six evaluable dates — a landmine, not a default.

    NaN is the honest substitute: every consumer asks `abs(hac_t) >= _T_BAR`, and NaN
    compares False, so a series too short to carry a HAC correction cannot open a gate.
    """
    import importlib
    import math
    import numpy as np
    from engine import validation as V
    M = importlib.import_module(mod)
    assert V.ic_summary(np.array([0.1, -0.2, 0.3, -0.1, 0.05, 0.2]),
                        periods_per_year=50).get("t_hac") is None, (
        "premise: six observations is exactly where ic_summary yields t_hac=None")

    names = [f"N{i}" for i in range(12)]
    panel_dates = [dt.date(2026, 7, d) for d in (1, 2, 7, 8, 9, 10, 13, 14, 16, 20, 21, 22)]
    rows = []
    for k, d in enumerate(panel_dates):
        for j, n in enumerate(names):
            rows.append({"date": d.isoformat(), "underlying": n,
                         col: float(j), "spot": 100.0 + j * (k + 1)})
        rows.append({"date": d.isoformat(), "underlying": "SPY", col: 0.0, "spot": 100.0})
    res = M._fwd_ic(pd.DataFrame(rows), 5)           # must not raise
    assert res["n_dates"] == 6
    assert math.isnan(res["hac_t"]), "an unavailable HAC t is NaN, never None and never 0"
    assert not (abs(res["hac_t"]) >= 2.0), "NaN must not clear the t-bar"


# ═══════════════════════════════════════════════════════════════════════════
# SITE 7 — engine/options_entry_state: the DISPLAY twin of the ledger column
# ═══════════════════════════════════════════════════════════════════════════
def _snap(root: Path, store: str, col: str, dates, vals) -> None:
    p = root / "data" / store
    p.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"date": [d.isoformat() for d in dates],
                  "underlying": ["AAA"] * len(dates),
                  col: vals}).to_parquet(p / "snapshots.parquet")


@pytest.mark.parametrize("loader,store,col,out_key", [
    ("_load_skew_snapshots", "options_skew", "skew", "skew_5d_chg"),
    ("_load_ivspread_snapshots", "options_ivspread", "ivspread_rel", "ivspread_5d_chg"),
])
def test_site7_display_twin_flips_sign_under_calendar_resolution(
        tmp_path, loader, store, col, out_key):
    from engine import options_entry_state as E
    _premise_gapped()
    vals = [0.30, 0.28, 0.26, 0.20, 0.22, 0.25]
    _snap(tmp_path, store, col, GAPPED, vals)
    got = getattr(E, loader)(tmp_path)["AAA"][out_key]
    assert got == pytest.approx(0.25 - 0.20, abs=1e-9)
    assert got > 0 and (vals[-1] - vals[-6]) < 0, "opposite signs"


@pytest.mark.parametrize("loader,store,col,out_key", [
    ("_load_skew_snapshots", "options_skew", "skew", "skew_5d_chg"),
    ("_load_ivspread_snapshots", "options_ivspread", "ivspread_rel", "ivspread_5d_chg"),
])
def test_site7_display_twin_refuses_a_missing_endpoint(tmp_path, loader, store, col, out_key):
    from engine import options_entry_state as E
    absent = [dt.date(2026, 7, 2), dt.date(2026, 7, 7), dt.date(2026, 7, 8),
              dt.date(2026, 7, 9), dt.date(2026, 7, 10), dt.date(2026, 7, 13)]
    assert nc.session_n_back(absent[-1], 5) not in absent, "premise"
    _snap(tmp_path, store, col, absent, [0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
    got = getattr(E, loader)(tmp_path)["AAA"]
    assert got[out_key] is None
    assert got["asof"] == "2026-07-13", "the LEVEL still publishes; only the change refuses"


# ═══════════════════════════════════════════════════════════════════════════
# SITE 8 — engine/options_ivspread.prior_spread_map keeps the DATE
# ═══════════════════════════════════════════════════════════════════════════
def test_site8_prior_spread_map_carries_the_date(tmp_path, monkeypatch):
    from lib import config
    from engine import options_ivspread as S
    p = tmp_path / "options_ivspread"
    p.mkdir(parents=True)
    pd.DataFrame({"date": ["2026-07-30", "2026-07-31"], "underlying": ["AAA", "AAA"],
                  "ivspread": [0.03, 0.04], "spot": [100.0, 101.0]}).to_parquet(
        p / "snapshots.parquet")
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    pm = S.prior_spread_map()
    assert pm["AAA"]["ivspread"] == pytest.approx(0.04)
    assert pm["AAA"]["date"] == dt.date(2026, 7, 31), (
        "without the date the caller cannot tell 'yesterday' from four sessions ago")


def test_site8_adjacency_decides_whether_the_delta_may_be_narrated():
    """The copy `assess` renders says 'vs the prior session'. That is only true when the
    two readings ARE adjacent sessions — the test the caller now runs."""
    cur_asof, prior_d = dt.date(2026, 8, 6), dt.date(2026, 7, 31)
    assert not nc.is_prior_session(prior_d, cur_asof), "premise: four sessions apart"
    assert nc.is_prior_session(dt.date(2026, 8, 5), cur_asof)


def test_site8_latest_chain_skips_a_weekend_snapshot(tmp_path, monkeypatch):
    from lib import config
    from engine import options_ivspread as S
    d = tmp_path / "polygon_gex" / "chains"
    d.mkdir(parents=True)
    sat = dt.date(2026, 8, 1)
    assert not nc.is_session(sat)
    for day in (dt.date(2026, 7, 31), sat):
        pd.DataFrame({"underlying": ["AAA"]}).to_parquet(d / f"{day.isoformat()}.parquet")
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    _, asof = S._latest_chain_dated()
    assert asof == dt.date(2026, 7, 31), "the Saturday byte-copy must not become 'latest'"


# ═══════════════════════════════════════════════════════════════════════════
# SITE 9 — engine/altdata.unusual_options: WINDOW/BASELINE, span-capped
# ═══════════════════════════════════════════════════════════════════════════
def test_site9_baseline_window_is_span_capped(tmp_path, monkeypatch):
    """Not the mislabeling class — a median baseline publishes no day count — so this is
    capped, never refused. The cap bounds how stale 'recent' may become."""
    from lib import config
    from engine import altdata as A
    d = tmp_path / "polygon_gex" / "chains"
    d.mkdir(parents=True)
    # THREE stale days, so leaving them in genuinely moves the MEDIAN baseline — a
    # single stale point cannot, and a fixture built that way would pass either way.
    stale = [dt.date(2026, 6, 15), dt.date(2026, 6, 16), dt.date(2026, 6, 17)]
    recent = [dt.date(2026, 7, 30), dt.date(2026, 7, 31), dt.date(2026, 8, 6)]
    for s in stale:
        assert nc.sessions_apart(s, recent[-1]) > A._BASELINE_MAX_SESSIONS, (
            "premise: the stale days must fall outside the span cap")
    for r in recent:
        assert nc.sessions_apart(r, recent[-1]) < A._BASELINE_MAX_SESSIONS, (
            "premise: the recent days must survive the cap")
    for day, vol in [(s, 1.0) for s in stale] + [(r, 50.0) for r in recent]:
        pd.DataFrame({"underlying": ["AAA"] * 2, "oi": [6000.0, 6000.0],
                      "volume": [vol, vol], "is_call": [True, False],
                      "asof": [day.isoformat()] * 2}).to_parquet(
            d / f"{day.isoformat()}.parquet")
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    rows = A.unusual_options(min_oi=1.0)
    assert rows, "the panel must still publish — a FIT-shaped stat is never refused"
    # Capped: the baseline is the recent ratios, so today is ordinary (mult 1.0).
    # Uncapped: the median of [stale, stale, stale, recent, recent] is a STALE ratio and
    # `mult` becomes 50x — a fabricated surge, and `hot` would fire on it.
    assert rows[0]["mult"] == pytest.approx(1.0, abs=1e-6)
    assert rows[0]["hot"] is False
