"""Weekend rows must not reach the options readers — the #3721 class, swept.

WHAT A WEEKEND ROW IS.  Several EOD options stores accrue a row on non-session days.  It
is NOT a harmless carry-forward duplicate: the builder RECOMPUTES iv30 / spot / walls /
net-GEX / skew off a stale carried-forward price, so the row is a fabricated observation
of a day that never traded.  Measured on the real stores, 2026-07-29:

    data/cboe/gex.parquet                     13 non-session rows of 39
    data/cboe/putcall.parquet                 13 non-session rows of 39  (same dates)
    data/options_skew/snapshots.parquet         8 non-session dates of 28
    data/options_ivspread/snapshots.parquet     6 non-session dates of 21
    data/polygon_gex/summary_*.parquet        ~11 non-session dates of 39
    data/polygon_gex/chains/{DATE}.parquet     11 non-session snapshot files of 39
    data/flows/broad_flow_proxy.parquet         5 non-session dates of 15
    (clean: options_flow/summary_* 0 of 136, tape_flow/daily 0 of 4,
     options_entry/state 0 of 3, market_structure/ledger 0 of 6;
     index_gex_history/SPY 1 of 2388, dated 2019-02-02)

SUPERSEDED FOR THE TWO polygon_gex LINES (2026-08-06).  Those rows were not weekend
recomputes of a session that had passed — they were the UTC RUN date, one session AHEAD
of the closing chain each file actually held, so no reader filter could recover the right
date.  ``scripts/migrate_polygon_gex_session_stamps.py`` re-stamped the store to the
session each snapshot describes; it now holds 24 chains files and 8,062 summary rows with
ZERO non-session stamps.  The guards below therefore split into two properties — the raw
store is session-clean at the SOURCE, and the readers would still drop a planted
non-session row — because "the reader drops something" is no longer a premise the real
store can supply.

Left in, one weekend row corrupts THREE things at once:
  1. ``.iloc[-1]`` — the "latest" reading can be a Saturday recompute;
  2. percentile / quantile windows — fabricated points inside the distribution a
     threshold is measured against;
  3. POSITIONAL lookbacks — ``.iloc[-6]`` stops meaning "5 sessions ago", and any
     ``n_obs`` count used as an activation gate is padded with non-trading days.

(3) was live: ``build_leader_radar._load_options_skew``'s ``min_obs=21`` gate read the
store's 28 dates as 28 observations, so ``call_skew_rich`` — chip 6 of the seven-chip
CROWDED state gate — was firing for 350 of 401 names on a count of which 8 were weekends.
Filtered, the real session count is 20 and every name is correctly null until the 21st.

Two canonical fixes existed (build_market_structure._read_gex_spx #F3-11/#F3-12,
build_options_screener._load_gex_summary #F3-17); this sweep extends the idiom to the
readers they missed, via the shared ``lib.nyse_calendar.session_rows`` /
``session_dates`` helpers — and then kills the class at the source with write-side gates
on the two writers that mint these rows (see TestCboeCollectorSessionGate /
TestPolygonChainsSessionGate at the bottom of this file).

Run: .venv/bin/python -m pytest tests/test_options_session_guards.py -q
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib import config, nyse_calendar  # noqa: E402

# 2026-07-24 Fri (session), 07-25 Sat, 07-26 Sun, 07-27 Mon (session)
FRI, SAT, SUN, MON = "2026-07-24", "2026-07-25", "2026-07-26", "2026-07-27"


def test_the_fixture_dates_really_are_what_this_file_claims():
    """Guard the guard: if the calendar disagrees, every assertion below is vacuous."""
    assert nyse_calendar.is_session(date(2026, 7, 24))
    assert not nyse_calendar.is_session(date(2026, 7, 25))
    assert not nyse_calendar.is_session(date(2026, 7, 26))
    assert nyse_calendar.is_session(date(2026, 7, 27))


# ──────────────────────────────────────────────────────── the shared helpers


class TestSessionRows:
    def test_datetime_index_shape(self):
        df = pd.DataFrame({"v": [1, 2, 3, 4]},
                          index=pd.to_datetime([FRI, SAT, SUN, MON]))
        out = nyse_calendar.session_rows(df)
        assert list(out.index.strftime("%Y-%m-%d")) == [FRI, MON]
        assert out.iloc[-1]["v"] == 4, "iloc[-1] must land on the Monday session"

    def test_date_column_shape(self):
        df = pd.DataFrame({"date": [FRI, SAT, SUN, MON], "v": [1, 2, 3, 4]})
        out = nyse_calendar.session_rows(df, "date")
        assert list(out["date"]) == [FRI, MON]

    def test_a_non_default_index_survives_the_column_filter(self):
        """groupby output and post-sort frames carry arbitrary indices — the boolean
        mask must align to the frame's own index, not to 0..n."""
        df = pd.DataFrame({"date": [FRI, SAT, SUN, MON], "v": [1, 2, 3, 4]},
                          index=[17, 3, 88, 42])
        out = nyse_calendar.session_rows(df, "date")
        assert list(out["date"]) == [FRI, MON]
        assert list(out.index) == [17, 42]

    def test_fail_open_when_filtering_would_empty_the_frame(self):
        """A calendar surprise must degrade to the OLD behaviour, never to a blank panel."""
        df = pd.DataFrame({"date": [SAT, SUN], "v": [1, 2]})
        out = nyse_calendar.session_rows(df, "date")
        assert len(out) == 2, "an all-weekend frame must pass through, not vanish"

    def test_unparseable_dates_are_kept_never_silently_dropped(self):
        df = pd.DataFrame({"date": ["garbage", FRI, SAT], "v": [1, 2, 3]})
        out = nyse_calendar.session_rows(df, "date")
        assert list(out["date"]) == ["garbage", FRI]

    @pytest.mark.parametrize("empty", [None, pd.DataFrame()])
    def test_empty_and_none_pass_through(self, empty):
        out = nyse_calendar.session_rows(empty)
        assert out is None or len(out) == 0

    def test_a_holiday_is_dropped_too_not_just_weekends(self):
        # 2026-07-03 is the observed Independence Day holiday (July 4 is a Saturday)
        assert not nyse_calendar.is_session(date(2026, 7, 3))
        df = pd.DataFrame({"date": ["2026-07-02", "2026-07-03", "2026-07-06"], "v": [1, 2, 3]})
        assert list(nyse_calendar.session_rows(df, "date")["date"]) == \
            ["2026-07-02", "2026-07-06"]


class TestSessionDates:
    def test_plain_dates(self):
        assert nyse_calendar.session_dates([FRI, SAT, SUN, MON]) == [FRI, MON]

    def test_key_extracts_the_date_from_a_path(self):
        paths = [f"/store/chains/{d}.parquet" for d in (FRI, SAT, SUN, MON)]
        import os
        out = nyse_calendar.session_dates(
            paths, key=lambda f: os.path.basename(f).removesuffix(".parquet"),
            keep_unparseable=True)
        assert out == [paths[0], paths[3]]

    def test_without_a_key_a_path_list_would_be_unparseable(self):
        """Why `key` exists: paths do not parse as dates, and keep_unparseable would
        make the whole filter a silent no-op."""
        paths = [f"/store/chains/{d}.parquet" for d in (FRI, SAT)]
        assert nyse_calendar.session_dates(paths, keep_unparseable=True) == paths

    def test_fail_open(self):
        assert nyse_calendar.session_dates([SAT, SUN]) == [SAT, SUN]


# ─────────────────────────────── the readers this sweep fixed are wired


# SMOKE ONLY (per the review adjudication): a text assertion cannot distinguish
# "filters" from "calls a filter and throws the result away" — neutralising the result at
# all 8 sites left this green. The load-bearing assertions are the behavioural classes at
# the bottom of this file. These stay because a DELETED call is still worth catching, and
# they are keyed to the assignment (`x = session_rows(...)`), not the argument spelling.
FIXED = {
    "engine/market_gamma.py": 2,
    "engine/options_entry_state.py": 4,
    "engine/options_stamp.py": 3,
    "engine/froth_fragility.py": 2,
    "engine/altdata.py": 1,
    "scripts/build_leader_radar.py": 1,
    "scripts/build_options_screener.py": 2,
    "scripts/build_gex_board.py": 1,
    "engine/risk_radar.py": 1,
    "engine/fear_greed.py": 1,
    "engine/flare_persistence.py": 1,
    "engine/rotation_flows.py": 1,
    "engine/etf_flows.py": 1,
}


@pytest.mark.parametrize("rel", sorted(FIXED))
def test_the_fixed_readers_still_assign_a_filtered_frame(rel):
    """Each site must ASSIGN the filter's result (`x = ...session_rows(...)`), never call
    it bare. Counting assignments catches a deleted call and a discarded result."""
    import re
    src = (ROOT / rel).read_text()
    assigns = re.findall(
        r"(?:=|return)\s*\(?\s*(?:nyse_calendar\.|nyse_calendar_)"
        r"session_(?:rows|dates)\s*\(", src)
    assert len(assigns) >= FIXED[rel], (
        f"{rel}: {len(assigns)} assigned session filter(s), expected >= {FIXED[rel]} — "
        "a bare call whose result is discarded is a no-op guard"
    )


def test_the_two_canonical_fixes_are_untouched():
    """This sweep EXTENDS the idiom; it must not have disturbed its origins."""
    ms = (ROOT / "scripts" / "build_market_structure.py").read_text()
    assert "nyse_calendar.is_session(ts.date()) for ts in df.index" in ms
    scr = (ROOT / "scripts" / "build_options_screener.py").read_text()
    assert "nyse_calendar.is_session(ts.date()) for ts in idx" in scr


# ───────────────────────── the call_skew_rich activation gate counts SESSIONS


def test_the_skew_activation_gate_counts_sessions_not_rows(tmp_path):
    """THE live defect: min_obs=21 over a store whose dates include weekends.

    Frame: 26 dates, 8 of them non-session -> 18 real sessions. Unfiltered it clears the
    activation floor; filtered it correctly does not.

    SIZED AGAINST LRV-R6 (#4020), not against min_obs alone: the loader now holds the last
    CROWDED_SKEW_PERSIST_WINDOW=5 observations out of their own benchmark
    (``hist = daily.iloc[:-5]``), so the first possible non-null moved from n_obs >= 21 to
    n_obs >= 21 + 5 = 26. The 22-date frame this test shipped with therefore gave an
    unfiltered hist of 17 < 21 and stayed null for the WRONG reason — the padding, not the
    filter — which made the premise assertion at the bottom pass vacuously. Eight padding
    rows restore it: unfiltered hist = 21 (activates), filtered hist = 13 (stays null)."""
    import scripts.build_leader_radar as blr

    sessions, cur = [], date(2026, 6, 22)
    while len(sessions) < 18:
        if nyse_calendar.is_session(cur):
            sessions.append(cur.isoformat())
        cur = date.fromordinal(cur.toordinal() + 1)
    # Every non-session day INSIDE the 2026-06-22..2026-07-16 session span — the three
    # weekend pairs AND the observed Independence Day holiday (2026-07-03, a Friday: the
    # guard must catch holidays, not just Saturdays) — which is the shape a store accruing
    # one row per CALENDAR day actually has, plus the trailing Saturday.
    non_sessions = ["2026-06-27", "2026-06-28", "2026-07-03", "2026-07-04", "2026-07-05",
                    "2026-07-11", "2026-07-12", SAT]
    dates = sorted(set(sessions + non_sessions))
    # Not `len(dates) == 26` (a literal against a literal, minor 11): assert the two
    # PROPERTIES the test's arithmetic depends on — 18 real sessions and 8 fabricated days.
    assert sum(1 for d in dates if nyse_calendar.is_session(date.fromisoformat(d))) == 18
    assert sum(1 for d in dates if not nyse_calendar.is_session(date.fromisoformat(d))) == 8

    df = pd.DataFrame({
        "date": dates,
        "underlying": ["TESTX"] * len(dates),
        "atm_call_iv": [0.30] * len(dates),
        "otm_put_iv": [0.28] * len(dates),
    })

    (tmp_path / "options_skew").mkdir(parents=True)
    df.to_parquet(tmp_path / "options_skew" / "snapshots.parquet")

    got = blr._load_options_skew(tmp_path, min_obs=21)
    assert got["TESTX"]["skew_n_obs"] == 18, (
        "the gate must count the 18 SESSIONS, not the 26 stored dates"
    )
    assert got["TESTX"]["rr_25d"] is None, (
        "18 sessions leave a 13-observation prior history once the 5-session evaluation "
        "window is held out — 13 < 21, so the chip must stay null"
    )

    # neutralise the filter and the same store wrongly activates
    orig = blr.nyse_calendar_session_rows
    blr.nyse_calendar_session_rows = lambda d, c=None, **kw: d
    try:
        bad = blr._load_options_skew(tmp_path, min_obs=21)
    finally:
        blr.nyse_calendar_session_rows = orig
    assert bad["TESTX"]["skew_n_obs"] == 26
    assert bad["TESTX"]["rr_25d"] is not None, (
        "premise check: unfiltered, this store DOES wrongly activate the chip"
    )


def test_a_null_skew_chip_degrades_the_crowded_gate_honestly():
    """call_skew_rich is chip 6 of the CROWDED state's seven-chip k-of-n gate, not a
    decorative badge. A null must leave the DENOMINATOR, not count as False."""
    from engine import leader_lifecycle as ll
    k, n = ll.count_k_true_n_avail(
        ll.STATE_CROWDED,
        {"extension_extreme": True, "monthly_rsi_80": True, "parabolic": False,
         "valuation_extreme": None, "analyst_saturated": None,
         "call_skew_rich": None, "basket_corr_rising": False},
    )
    assert (k, n) == (2, 4), (
        "a null chip must drop out of n_avail entirely — counting it as False would "
        "silently make every CROWDED read stricter"
    )


# ──────────────────────────────────────── the real stores, as measured


WEEKEND_BEARING = {
    "data/cboe/gex.parquet": None,
    "data/options_skew/snapshots.parquet": "date",
    "data/options_ivspread/snapshots.parquet": "date",
}


@pytest.mark.parametrize("rel", sorted(WEEKEND_BEARING))
def test_the_premise_holds_on_the_real_stores(rel):
    """If these stores ever stop carrying weekend rows the fixes become no-ops — which is
    fine — but the reason recorded in the code would be wrong, so surface the change."""
    p = ROOT / rel
    if not p.exists():
        pytest.skip(f"{rel} absent on this runner")
    df = pd.read_parquet(p)
    if df.empty:
        pytest.skip("empty store")
    filtered = nyse_calendar.session_rows(df, WEEKEND_BEARING[rel])
    src = df[WEEKEND_BEARING[rel]] if WEEKEND_BEARING[rel] else pd.Series(df.index)
    n_dates = len({pd.Timestamp(d).date() for d in src})
    fsrc = (filtered[WEEKEND_BEARING[rel]] if WEEKEND_BEARING[rel]
            else pd.Series(filtered.index))
    n_sessions = len({pd.Timestamp(d).date() for d in fsrc})
    # `n_sessions <= n_dates` was the assertion here and it is TRUE BY CONSTRUCTION — a
    # filter cannot add rows (minor 11). Assert the PREMISE these fixes rest on instead:
    # this store really does carry non-session rows, so the guards are not decoration.
    assert n_sessions < n_dates, (
        f"{rel}: {n_dates} dates, {n_sessions} sessions — the store carries NO non-session "
        "rows any more. Good news, but this PR's rationale (and the write-side gates) are "
        "written against a store that does; update the premise before trusting the guards."
    )
    print(f"{rel}: {n_dates} dates -> {n_sessions} sessions "
          f"({n_dates - n_sessions} fabricated)")


def test_the_filtered_latest_row_is_always_a_session():
    """The single assertion every one of these fixes exists to make true."""
    p = config.data_dir() / "options_skew" / "snapshots.parquet"
    if not p.exists():
        pytest.skip("options_skew store absent")
    df = nyse_calendar.session_rows(pd.read_parquet(p), "date")
    latest = max(pd.Timestamp(d).date() for d in df["date"])
    assert nyse_calendar.is_session(latest), (
        f"the session-filtered store's latest date {latest} is not a trading session"
    )


# ══════════════════ BEHAVIOURAL: the guard must DROP rows, not merely be called ══
#
# The first version of this file asserted that the filter CALL appears in each reader's
# source.  Review neutralised 8/8 sites by keeping the call and discarding its result —
# zero reds.  A text assertion cannot tell "filters" from "calls a filter and ignores it".
# These tests read the OUTPUT.  Priority is the LEDGER-BEARING paths.


def _summary_frame(dates: list[str], iv30_by_date: dict[str, float] | None = None):
    """A polygon_gex summary frame indexed by date, weekend rows included."""
    iv = iv30_by_date or {}
    return pd.DataFrame(
        {"iv30": [iv.get(d, 0.30) for d in dates],
         "net_vex": [1_000_000.0] * len(dates),
         "spot": [100.0] * len(dates),
         "gamma_regime": ["long"] * len(dates),
         "dist_to_flip_pct": [5.0] * len(dates),
         "magnet_up": [110.0] * len(dates),
         "magnet_down": [90.0] * len(dates)},
        index=pd.to_datetime(dates))


class TestStampFunnelDropsWeekendRows:
    """engine/options_stamp.stamp_options_state — feeds opt_* LEDGER columns."""

    def test_an_injected_reader_with_a_weekend_row_never_stamps_it(self):
        from engine.options_stamp import stamp_options_state
        # Fri, Sat, Sun: the weekend rows carry a WILDLY different iv30 so the stamp
        # betrays which row it read.
        dates = [FRI, SAT, SUN]
        frame = _summary_frame(dates, {FRI: 0.30, SAT: 0.99, SUN: 0.98})
        s = stamp_options_state(SUN, "FOO", read_summary=lambda t: frame,
                                chain_dates=[], read_chain=lambda d: None)
        assert s["opt_iv30"] == pytest.approx(0.30), (
            f"the stamp read a non-session row (iv30={s['opt_iv30']}); Friday's 0.30 is "
            "the only legitimate value for a Sunday as_of"
        )

    def test_the_positional_five_session_lookback_spans_five_sessions(self):
        """_vanna_hedge_5d_from_summary / _DOI_WINDOW take POSITIONAL lookbacks that are
        USED as trading-day changes. With weekend rows in, iloc[-6] is ~3 sessions back.

        TWO THINGS MOVE THE SPAN OFF SIX, IN OPPOSITE DIRECTIONS (2026-08-06).

          * FEWER sessions than rows — the reader let a non-session (or a duplicated
            date) into the window, so ``iloc[-6]`` is nearer than five sessions back.
            That is this file's defect class; it stays a hard failure.

          * MORE sessions than rows — the STORE never holds those sessions, because
            the collector did not run.  ``polygon_gex`` is chronically gappy and
            always has been: measured on ``summary_AAPL`` at 2026-08-06, SIX sessions
            are absent from its 37-session span, and three of them (07-06, 07-15,
            07-17) predate the 08-03..08-05 nightly outage that finally pushed a hole
            into the six-row tail window.  No repo change heals a collector outage,
            and while this was asserted as a flat ``== 6`` the whole merge queue was
            hostage to the options collector's uptime — it took ci-pack-2 red on main
            and blocked 56 armed PRs.  The gap is reported, not asserted.

        So the flat equality is replaced by the reader contract it was standing in
        for, asserted DIRECTLY against the real store (and non-vacuously: the raw
        store still carries fabricated rows, which is asserted first).  The residual
        risk the equality used to cover — a gap making the shipped
        ``opt_vanna_hedge_5d`` a nine-session change rather than a five-session one —
        is a property of ``_vanna_hedge_5d_from_summary``'s positional slice, and
        making that slice date-anchored is a ledger-affecting change that belongs to
        its own PR, not to a CI heal.
        """
        import warnings
        from engine.options_stamp import _default_read_summary
        import scripts.build_options_screener  # noqa: F401 - keeps import order stable
        from lib import config
        p = config.data_dir() / "polygon_gex" / "summary_AAPL.parquet"
        if not p.exists():
            pytest.skip("summary_AAPL absent on this runner")
        sdf = _default_read_summary("AAPL")
        assert sdf is not None and len(sdf) >= 6
        idx = [pd.Timestamp(d).date() for d in sdf.index]

        # (1) The premise, INVERTED by the 2026-08-06 session-stamp migration. This used
        # to assert the store still carried fabricated rows, because that was what kept
        # (2) non-vacuous. The migration re-stamped every file and row to the session it
        # describes and dropped the non-session ones, so the store is now clean BY
        # CONTRACT — a fabricated row reappearing means the writer regressed to run-date
        # stamping. Non-vacuity moves off the store and onto a direct probe: the same
        # filter, handed a fabricated Saturday row, must still drop it.
        raw_df = pd.read_parquet(p)
        raw = [pd.Timestamp(d).date() for d in raw_df.index]
        fabricated = [d for d in raw if not nyse_calendar.is_session(d)]
        assert not fabricated, (
            f"{p.name} carries non-session rows {fabricated}. Since the 2026-08-06 "
            "migration every polygon_gex stamp is the SESSION the snapshot describes; a "
            "new non-session stamp means scripts/build_polygon_gex.py went back to "
            "stamping the UTC run date")
        probe = pd.concat([raw_df, raw_df.iloc[[-1]].set_axis(
            pd.DatetimeIndex([pd.Timestamp(SAT)]), axis=0)])
        assert len(nyse_calendar.session_rows(probe, label="probe")) == len(raw_df), (
            "session_rows let a fabricated Saturday row through — the filter every "
            "assertion below leans on is a no-op")

        # (2) The reader's contract on the REAL store: exactly the session rows,
        # in order, nothing else dropped. A neutralised filter fails here.
        assert idx == [d for d in raw if nyse_calendar.is_session(d)], (
            "the source reader did not return exactly the store's session rows")

        # (3) The positional window may never span FEWER sessions than it holds rows
        # — that is precisely what a weekend row or a duplicated date does to
        # iloc[-6], and it is the failure this guard exists to catch.
        window = idx[-6:]
        span = nyse_calendar.sessions_between(window[0], window[-1])
        assert len(span) >= len(window), (
            f"iloc[-6]..iloc[-1] holds {len(window)} rows but spans only {len(span)} "
            "sessions — the positional lookback is not session-true")

        # (4) The other direction is a collection gap. Surfaced, never silent: this
        # lands in pytest's warnings summary in the job log.
        missing = [d for d in span if d not in set(window)]
        if missing:
            warnings.warn(
                f"polygon_gex/{p.name}: iloc[-6]..iloc[-1] spans {len(span)} sessions "
                f"for {len(window)} rows — the store is missing "
                f"{', '.join(str(d) for d in missing)}, so the '5-session' positional "
                f"lookback in _vanna_hedge_5d_from_summary is reading "
                f"{len(span) - 1} sessions back", stacklevel=2)

    def test_neutralising_the_filter_changes_the_stamp(self, monkeypatch):
        """Premise check — proves this test can actually fail. With session_rows made a
        no-op, the same call stamps the Sunday row."""
        from engine import options_stamp as os_mod
        frame = _summary_frame([FRI, SAT, SUN], {FRI: 0.30, SAT: 0.99, SUN: 0.98})
        monkeypatch.setattr(os_mod.nyse_calendar, "session_rows",
                            lambda df, col=None, **kw: df)
        s = os_mod.stamp_options_state(SUN, "FOO", read_summary=lambda t: frame,
                                       chain_dates=[], read_chain=lambda d: None)
        assert s["opt_iv30"] == pytest.approx(0.98), (
            "premise failed: without the filter the stamp should read the Sunday row"
        )


# ══════════════════ GAP: a session-true snapshot list is still not a DENSE one ══
#
# Session-filtering guarantees every snapshot IS a session.  It cannot guarantee every
# session HAS a snapshot, and polygon_gex is chronically gappy — four interior holes in the
# 31 committed chain dates, the largest being the 2026-08-03..08-05 collection outage.  The
# snapshot API is current-only, so no backfill is possible, ever.
#
# Positional slicing then lies a SECOND way, independent of the weekend-row class above:
# `usable[-6:]` still returns six rows but they span NINE sessions at as_of 2026-08-06, and
# `usable[-2]` is FOUR sessions back rather than one.  These tests pin the two different
# honest answers — re-weight the fit, refuse the two-snapshot comparisons — against the real
# outage geometry.

_GAP_WINDOW = [date(2026, 7, 27), date(2026, 7, 28), date(2026, 7, 29),
               date(2026, 7, 30), date(2026, 7, 31), date(2026, 8, 6)]
_DENSE_WINDOW = [date(2026, 7, 23), date(2026, 7, 24), date(2026, 7, 27),
                 date(2026, 7, 28), date(2026, 7, 29), date(2026, 7, 30)]

# A series whose positional and session-ordinal fits have OPPOSITE SIGNS: five sessions of
# steady accumulation, then a slump on the far side of the hole.  Positional charges that
# slump one step and still reads "accumulating"; the session fit gives it the four steps it
# actually took and reads "distributing".  S-DOI buckets on slope > 0, so the two disagree
# about which bucket the fire lands in.
_OI_SERIES = [100.0, 110.0, 120.0, 130.0, 140.0, 90.0]
_POSITIONAL_SLOPE = 0.012422    # (25/17.5)/115 — x = [0,1,2,3,4,5]
_SESSION_SLOPE = -0.010870      # (-50/40)/115  — x = [0,1,2,3,4,8]


def _sessions_from(start: date, n: int) -> list[date]:
    """`n` consecutive NYSE sessions starting at/after `start`."""
    from datetime import timedelta
    out: list[date] = []
    d = start
    while len(out) < n:
        if nyse_calendar.is_session(d):
            out.append(d)
        d += timedelta(days=1)
    return out


def _gap_chain_frame(ticker: str, *, call_oi: float, expiries: list[date],
                     volume: float = 5.0, spot: float = 100.0):
    """One chain snapshot carrying every column the three chain readers require.

    `expiries` are FIXED across the snapshots of a window, as real contracts are: the
    prior-OI lookup keys on (expiry, K, is_call), so an expiry that drifts with the
    snapshot date matches nothing and silently nulls the charm share. One expiry sits
    inside the ≤7-calendar-day front bucket and one well outside, so `_ovc_from_chain`
    has a real share to compute rather than a degenerate 0/0.
    """
    rows = []
    for expiry in expiries:
        for k in (95.0, 100.0, 105.0):
            for is_call in (True, False):
                rows.append({
                    "underlying": ticker, "K": k, "is_call": is_call,
                    "oi": call_oi if is_call else 0.8 * call_oi,
                    "volume": volume, "spot": spot,
                    "expiry": pd.Timestamp(expiry), "T": 0.05, "iv": 0.30,
                })
    return pd.DataFrame(rows)


def _stamp_over(window: list[date], series: list[float], ticker: str = "FOO") -> dict:
    """Stamp the last date of `window`, feeding `series[i]` as day i's near-money call OI."""
    from datetime import timedelta

    from engine.options_stamp import stamp_options_state
    by_date = dict(zip(window, series))
    # dated off the snapshot being stamped, so one expiry is always inside the front bucket
    expiries = [window[-1] + timedelta(days=3), window[-1] + timedelta(days=45)]
    return stamp_options_state(
        window[-1].isoformat(), ticker,
        read_summary=lambda t: None,
        chain_dates=list(window),
        read_chain=lambda d: (_gap_chain_frame(ticker, call_oi=by_date[d], expiries=expiries)
                              if d in by_date else None),
    )


class TestChainGapsAreNotSessionSpacing:
    """engine/options_stamp — the three chain readers vs a store the collector skipped."""

    def test_the_outage_geometry_is_what_this_file_claims(self):
        """Guard the guard: if the calendar or the fixture drifts, every test below is
        vacuous — a 'gap' window that is secretly dense proves nothing."""
        span = nyse_calendar.sessions_between(_GAP_WINDOW[0], _GAP_WINDOW[-1])
        assert len(span) == 9, f"the fixture window spans {len(span)} sessions, not 9"
        assert len(_GAP_WINDOW) == 6
        missing = [d for d in span if d not in set(_GAP_WINDOW)]
        assert missing == [date(2026, 8, 3), date(2026, 8, 4), date(2026, 8, 5)], (
            f"the missing sessions are {missing}, not the 08-03..08-05 outage"
        )
        assert all(nyse_calendar.is_session(d) for d in _GAP_WINDOW), (
            "a fixture snapshot date is not a session — this file's OTHER defect class"
        )
        # and the control really is dense
        dense_span = nyse_calendar.sessions_between(_DENSE_WINDOW[0], _DENSE_WINDOW[-1])
        assert len(dense_span) == len(_DENSE_WINDOW) == 6

    def test_session_ordinals_count_the_hole_as_elapsed_time(self):
        from engine.options_stamp import _session_ordinals
        assert _session_ordinals(_GAP_WINDOW) == [0.0, 1.0, 2.0, 3.0, 4.0, 8.0]
        assert _session_ordinals(_DENSE_WINDOW) == [0.0, 1.0, 2.0, 3.0, 4.0, 5.0], (
            "a dense window must reproduce np.arange exactly, or the fix moved values "
            "it had no business moving"
        )
        # fabricated / unusable inputs degrade to null, never to a silent mis-fit
        assert _session_ordinals([date(2026, 7, 25)]) is None, "Saturday is not a session"
        assert _session_ordinals([_GAP_WINDOW[1], _GAP_WINDOW[0]]) is None, "not ascending"
        assert _session_ordinals([_GAP_WINDOW[0], _GAP_WINDOW[0]]) is None, "duplicate date"
        assert _session_ordinals([]) is None

    def test_the_doi_slope_is_fitted_against_sessions_not_positions(self):
        """THE DEFECT. Six snapshots spanning nine sessions: the positional fit charges the
        07-31 -> 08-06 move to a single step and reports accumulation; the session fit gives
        it the four sessions it took and reports distribution."""
        got = _stamp_over(_GAP_WINDOW, _OI_SERIES)["opt_doi_slope_5d"]
        assert got == pytest.approx(_SESSION_SLOPE, abs=1e-6), (
            f"opt_doi_slope_5d = {got}; the session-true fit is {_SESSION_SLOPE} and the "
            f"positional fit is {_POSITIONAL_SLOPE}"
        )
        assert got < 0 < _POSITIONAL_SLOPE, (
            "premise failed: the fixture no longer separates the two fits by SIGN, so this "
            "test would pass on the positional code it exists to fail"
        )

    def test_a_dense_window_is_unchanged_by_the_ordinal_fit(self):
        """The other half of the contract: wherever the collector ran every session the
        ordinals ARE np.arange, so no already-stamped dense value may move."""
        got = _stamp_over(_DENSE_WINDOW, _OI_SERIES)["opt_doi_slope_5d"]
        assert got == pytest.approx(_POSITIONAL_SLOPE, abs=1e-6), (
            f"a dense window stamped {got}, not the unchanged {_POSITIONAL_SLOPE}"
        )

    def test_the_slope_refuses_a_window_that_is_more_gap_than_observation(self):
        """`_DOI_MAX_SPAN`: at most as many sessions missing as the fit has steps. Re-
        weighting keeps the UNITS honest, not the word '5d' — past the cap there is no
        reading left to publish, so the stat nulls."""
        from engine.options_stamp import _DOI_MAX_SPAN
        assert _DOI_MAX_SPAN == 11

        base = _sessions_from(date(2026, 6, 1), 14)
        # five consecutive sessions + a sixth far enough out to hit the cap exactly
        at_cap = base[:5] + [base[10]]
        beyond = base[:5] + [base[11]]
        assert len(nyse_calendar.sessions_between(at_cap[0], at_cap[-1])) == 11
        assert len(nyse_calendar.sessions_between(beyond[0], beyond[-1])) == 12

        assert _stamp_over(at_cap, _OI_SERIES)["opt_doi_slope_5d"] is not None, (
            "premise failed: the boundary window must still stamp, or the cap test below "
            "is passing for the wrong reason"
        )
        assert _stamp_over(beyond, _OI_SERIES)["opt_doi_slope_5d"] is None, (
            "a window spanning 12 sessions for 6 rows was published as a 5-day slope"
        )

    def test_the_voi_flag_refuses_an_oi_book_that_is_not_yesterdays(self):
        """`vol > YESTERDAY's OI` is the whole construction. Across the outage the baseline
        is four sessions of accrual old — a systematically lower bar — and a boolean has no
        re-weighting escape, so it nulls."""
        assert _stamp_over(_GAP_WINDOW, _OI_SERIES)["opt_voi_flag"] is None, (
            "the fresh-positioning flag was computed against a four-session-stale OI book"
        )
        dense = _stamp_over(_DENSE_WINDOW, _OI_SERIES)["opt_voi_flag"]
        assert dense in (True, False), (
            f"premise failed: the same fixture must still stamp on adjacent sessions "
            f"(got {dense}), or the test above proves nothing about the GAP"
        )

    def test_front7_charm_share_refuses_a_stale_book_but_keeps_root_class(self):
        """`_ovc_from_chain`'s PIT certification rests on the study's shift(1) prior-session
        OI; across the gap it is a shift(4). root_class is taxonomy from the ticker alone and
        must survive — it has a display twin and a 100%-null tripwire."""
        gapped = _stamp_over(_GAP_WINDOW, _OI_SERIES)
        assert gapped["opt_front7_charm_share"] is None, (
            "the charm share was weighted by an OI book four sessions stale"
        )
        assert gapped["opt_root_class"] == "single_name", (
            f"root_class needs no chain at all and must not go null with the share "
            f"(got {gapped['opt_root_class']!r})"
        )
        dense = _stamp_over(_DENSE_WINDOW, _OI_SERIES)["opt_front7_charm_share"]
        assert dense is not None, (
            "premise failed: this fixture must produce a real share on adjacent sessions, "
            "else the gap assertion above is indistinguishable from a missing column"
        )


class TestLedgerPathReadersDropWeekendRows:
    """The two ledger-writing call paths in scripts/stamp_options_state.py bypass the
    funnel and call engine.options_stamp._default_read_summary DIRECTLY (:199 vanna,
    :313 iv30_5d_chg -> opt_vanna_relief). The filter must live in the READER."""

    def test_default_read_summary_returns_only_sessions(self):
        from engine.options_stamp import _default_read_summary
        from lib import config
        import glob
        files = sorted(glob.glob(str(config.data_dir() / "polygon_gex" / "summary_*.parquet")))
        if not files:
            pytest.skip("polygon_gex summaries absent")
        checked = 0
        for f in files[:25]:
            sym = Path(f).stem.replace("summary_", "")
            out = _default_read_summary(sym)
            if out is None or out.empty:
                continue
            checked += 1
            bad = [d.date() for d in out.index if not nyse_calendar.is_session(d.date())]
            assert not bad, f"summary_{sym} returned non-session rows {bad}"
        assert checked, "no summaries were actually checked"

    def test_the_reader_still_drops_a_non_session_row(self, tmp_path, monkeypatch):
        """Guard the guard: the assertion above would pass vacuously on a clean store.

        It USED to prove non-vacuity from the real store, which carried weekend rows.
        The 2026-08-06 session-stamp migration removed them, so the proof moves to a
        planted row: a fabricated Saturday written into a stand-in store must not come
        back out of ``_default_read_summary``. A neutralised filter fails here.
        """
        from engine import options_stamp as os_mod
        real = config.data_dir() / "polygon_gex" / "summary_AAPL.parquet"
        if not real.exists():
            pytest.skip("summary_AAPL absent")
        raw = pd.read_parquet(real)
        planted = pd.concat([raw, raw.iloc[[-1]].set_axis(
            pd.DatetimeIndex([pd.Timestamp(SAT)]), axis=0)])
        (tmp_path / "polygon_gex").mkdir(parents=True)
        planted.to_parquet(tmp_path / "polygon_gex" / "summary_AAPL.parquet")
        monkeypatch.setattr(os_mod.config, "data_dir", lambda: tmp_path)
        out = os_mod._default_read_summary("AAPL")
        assert len(out) == len(raw), (
            f"the reader dropped nothing ({len(planted)} -> {len(out)}) — the session "
            "filter is a no-op")
        assert pd.Timestamp(SAT) not in out.index

    def test_the_real_store_carries_no_non_session_rows(self):
        """The migration's standing invariant, asserted where the readers live.

        Before 2026-08-06 the polygon_gex summaries were stamped with the UTC RUN date,
        so ~26% of rows were weekends and every stamp sat one session ahead of the market
        state it held. Both are gone; this fails the moment either comes back.
        """
        import glob
        files = sorted(glob.glob(str(config.data_dir() / "polygon_gex"
                                     / "summary_*.parquet")))
        if not files:
            pytest.skip("polygon_gex summaries absent")
        bad = []
        for f in files:
            for d in pd.read_parquet(f).index:
                if not nyse_calendar.is_session(pd.Timestamp(d).date()):
                    bad.append((Path(f).name, str(pd.Timestamp(d).date())))
        assert not bad, f"non-session summary rows are back: {bad[:10]}"

    def test_the_two_snapshot_loaders_return_only_sessions(self):
        from engine.options_stamp import (_default_read_skew_snapshots,
                                          _default_read_ivspread_snapshots)
        for loader, name in ((_default_read_skew_snapshots, "options_skew"),
                             (_default_read_ivspread_snapshots, "options_ivspread")):
            df = loader()
            if df is None or df.empty:
                continue
            bad = sorted({pd.Timestamp(d).date() for d in df["date"]
                          if not nyse_calendar.is_session(pd.Timestamp(d).date())})
            assert not bad, f"{name} loader returned non-session dates {bad}"


class TestScreenerGexSummaryDropsWeekendRows:
    """scripts/build_options_screener._load_gex_summary — the canonical #F3-17 fix; its
    output sets each row's `asof` and drives iv_rank's n_obs."""

    def test_load_gex_summary_returns_only_sessions(self):
        """Two properties, split apart by the 2026-08-06 session-stamp migration.

        This used to prove non-vacuity with ``assert dropped_any`` — the real store
        carried weekend rows, so the lookup had to drop some. The migration removed them
        at the SOURCE, so the honest statement of the contract is now stronger and comes
        in two halves: the RAW store carries zero non-session rows (asserted here,
        before any filtering), and the lookup would still drop one if it appeared
        (asserted on a synthetic frame in the next test, non-vacuous by construction).
        """
        import scripts.build_options_screener as bos
        from lib import config
        import glob
        files = sorted(glob.glob(str(config.data_dir() / "polygon_gex" / "summary_*.parquet")))
        if not files:
            pytest.skip("polygon_gex summaries absent")
        checked = 0
        for f in files[:25]:
            sym = Path(f).stem.replace("summary_", "")
            raw = pd.read_parquet(f)
            dirty = [pd.Timestamp(d).date() for d in raw.index
                     if not nyse_calendar.is_session(pd.Timestamp(d).date())]
            assert not dirty, (
                f"summary_{sym} carries non-session rows {dirty} at the SOURCE — the "
                "writer regressed to UTC run-date stamping")
            out = bos._load_gex_summary(sym)
            if out is None or out.empty:
                continue
            checked += 1
            idx = pd.to_datetime(out.index)
            bad = [d.date() for d in idx if not nyse_calendar.is_session(d.date())]
            assert not bad, f"summary_{sym} lookup returned non-session rows {bad}"
        assert checked, "no summaries were actually checked"

    def test_the_lookup_still_drops_a_planted_non_session_row(self, tmp_path, monkeypatch):
        """The filter half, non-vacuous by construction: a planted Saturday must not
        survive ``_load_gex_summary`` even though the real store no longer has one."""
        import scripts.build_options_screener as bos
        real = config.data_dir() / "polygon_gex" / "summary_AAPL.parquet"
        if not real.exists():
            pytest.skip("summary_AAPL absent")
        raw = pd.read_parquet(real)
        planted = pd.concat([raw, raw.iloc[[-1]].set_axis(
            pd.DatetimeIndex([pd.Timestamp(SAT)]), axis=0)])
        planted.to_parquet(tmp_path / "summary_AAPL.parquet")
        monkeypatch.setattr(bos, "GEX_DIR", tmp_path)
        out = bos._load_gex_summary("AAPL")
        assert len(out) == len(raw), (
            f"the lookup dropped nothing ({len(planted)} -> {len(out)}) — it is a no-op")
        assert pd.Timestamp(SAT) not in pd.to_datetime(out.index)

    def test_the_emitted_asof_is_always_a_session(self):
        """The #F3-17 shape verbatim: a Sunday stamped as a row's asof."""
        rows_json = ROOT / "site" / "screenerdata" / "rows.json"
        if not rows_json.exists():
            pytest.skip("rows.json not built on this runner")
        import json
        rows = json.loads(rows_json.read_text())["rows"]
        bad = [(r["ticker"], r["asof"]) for r in rows if r.get("asof")
               and not nyse_calendar.is_session(pd.Timestamp(r["asof"]).date())]
        assert not bad, f"non-session asof published for {bad[:5]}"


class TestSkewLookupsDropWeekendRows:
    """The two screener snapshot lookups (missed by #F3-17, fixed in this PR)."""

    @pytest.mark.parametrize("loader_name,path_attr,col", [
        ("_load_skew_lookup", "SKEW_PATH", "skew"),
        ("_load_ivspread_lookup", "IVSPREAD_PATH", "ivspread_rel"),
    ])
    def test_a_weekend_row_never_becomes_the_published_value(
            self, tmp_path, loader_name, path_attr, col):
        import scripts.build_options_screener as bos
        # Friday = the honest value; Saturday = a fabricated recompute 10x larger.
        df = pd.DataFrame({
            "date": [FRI, SAT], "underlying": ["AAA", "AAA"],
            col: [0.0400, 0.4000], "tenor_days": [30, 30],
        })
        sub = tmp_path / "s"
        sub.mkdir()
        path = sub / "snapshots.parquet"
        df.to_parquet(path)
        orig = getattr(bos, path_attr)
        setattr(bos, path_attr, path)
        try:
            out = getattr(bos, loader_name)()
        finally:
            setattr(bos, path_attr, orig)
        got = out["AAA"]["skew_pp"] if col == "skew" else out["AAA"]
        assert got == pytest.approx(4.0), (
            f"published {got}; Friday's 0.04 -> 4.0pp is the only session-true value "
            "(40.0 means the Saturday recompute was read)"
        )


# ═══════════════ M7: WRITE-SIDE gates — the class dies at the source ═════════════
#
# Every reader filtering is remediation.  The rows exist because two writers stamp
# `date.today()` unconditionally: collectors/cboe.py's PutCallAdapter/GexAdapter (13
# non-session rows of 39 in each of gex.parquet and putcall.parquet) and
# scripts/build_polygon_gex.py's chain snapshot (11 non-session FILES of 39).  Historical
# rows stay — readers filter them now — but no NEW one may land.


class TestCboeCollectorSessionGate:
    def test_a_non_session_day_discards_the_whole_snapshot(self, monkeypatch):
        import collectors.cboe as cboe
        monkeypatch.setattr(cboe.nyse_calendar, "is_session", lambda d: False)
        assert cboe._session_gated({"putcall": "frame"}, "PutCallAdapter") == {}

    def test_a_session_day_passes_the_snapshot_through_untouched(self, monkeypatch):
        import collectors.cboe as cboe
        monkeypatch.setattr(cboe.nyse_calendar, "is_session", lambda d: True)
        frames = {"putcall": "frame", "gex": "other"}
        assert cboe._session_gated(frames, "PutCallAdapter") is frames

    def test_the_gate_annotates_at_line_start(self, monkeypatch, capsys):
        import collectors.cboe as cboe
        monkeypatch.setattr(cboe.nyse_calendar, "is_session", lambda d: False)
        cboe._session_gated({"putcall": "f"}, "PutCallAdapter")
        ann = [l for l in capsys.readouterr().out.splitlines() if "::" in l]
        assert ann and all(l.startswith("::") for l in ann), ann
        assert any("cboe-session-gate" in l for l in ann)

    @pytest.mark.parametrize("adapter", ["PutCallAdapter", "GexAdapter"])
    def test_both_adapters_route_their_return_through_the_gate(self, adapter):
        src = (ROOT / "collectors" / "cboe.py").read_text()
        body = src.split(f"class {adapter}", 1)[1].split("\nclass ", 1)[0]
        assert "_session_gated(" in body, (
            f"{adapter}.fetch must return through _session_gated — otherwise it keeps "
            "stamping non-session snapshots as observations"
        )


class TestPolygonChainsSessionGate:
    """The gate, and what 2026-08-06 changed underneath it.

    The gate was written against `asof = datetime.now(timezone.utc).date()` — the RUN
    date — and in that world it fired constantly, including on every Saturday/Sunday UTC.
    But a run at 01:24 UTC Saturday is a FRIDAY-EVENING ET accrual holding Friday's
    closing chain, so the gate was rejecting real sessions: 2026-07-31 was permanently
    lost that way (runs fired on 08-01 and 08-02, both refused before the fetch, and
    polygon OI cannot be backfilled). `asof` is now the SESSION the snapshot describes
    (`_resolve_session` -> `expected_last_session`), so on the datetime path the gate is
    always true and never fires — THAT is what restores the Fridays. It still guards the
    explicit `--date` path, where a caller can name a day the market never opened.
    """

    def test_a_non_session_asof_writes_nothing(self, monkeypatch, tmp_path):
        import scripts.build_polygon_gex as bpg

        wrote = []
        monkeypatch.setattr(bpg.nyse_calendar, "is_session", lambda d: False)
        monkeypatch.setattr(bpg, "_chains_dir", lambda: tmp_path)

        class _Client:
            def snapshot(self, *a, **k):
                wrote.append("FETCHED")
                return pd.DataFrame()

        # the gate must fire BEFORE the network fetch and before any write
        src = (ROOT / "scripts" / "build_polygon_gex.py").read_text()
        gate_at = src.index("nyse_calendar.is_session(asof)")
        fetch_at = src.index("client.snapshot(symbols, asof)")
        assert gate_at < fetch_at, (
            "the session gate must precede the snapshot fetch — otherwise a non-session "
            "run still spends the API quota"
        )
        assert not list(tmp_path.glob("*.parquet"))
        assert not wrote

    def test_the_gate_returns_a_named_status(self):
        src = (ROOT / "scripts" / "build_polygon_gex.py").read_text()
        assert '"status": "non_session"' in src, (
            "the skip must be reported as its own status, not silently as empty/ok"
        )

    def test_the_gate_annotation_starts_the_line(self):
        src = (ROOT / "scripts" / "build_polygon_gex.py").read_text()
        block = src.split("nyse_calendar.is_session(asof)", 1)[1][:800]
        assert 'print(f"::notice title=polygon-session-gate::' in block
        assert "flush=True" in block

    def test_the_stamp_is_the_session_not_the_utc_run_date(self):
        """The 2026-08-06 contract, pinned against the AST so a revert is loud.

        A reversion to `datetime.now(timezone.utc).date()` — or to `session_date()`, which
        calls the whole ET calendar day "the session" and so returns Wednesday for a
        02:24 ET Wednesday snapshot carrying Tuesday's close — puts the store back one
        session ahead of the market and re-arms the Friday refusal.

        THIS SCANS CODE, NOT TEXT, and that is load-bearing. The module's docstring names
        BOTH defects on purpose (it is what stops the next reader from "simplifying"
        `_resolve_session` back to a run-date stamp), so a `str in src` grep matches its
        own explanation and either goes permanently red or forces the documentation out.
        Walking `ast.Call` nodes sees calls only: docstrings are `Constant` expressions
        and comments are not in the tree at all. It also survives reformatting.

        VERIFIED BY MUTATION (2026-08-06) — every assertion below was watched to fail,
        not assumed. Four mutations, each applied to the real module and then reverted:
        (1) `_resolve_session` reverted to `return datetime.now(timezone.utc).date()` and
        (2) `expected_last_session` swapped for `session_date` both go red on the helper
        assertion; (3) the isinstance branches reordered goes red on the order assertion;
        (4) a stray `datetime.now(timezone.utc).date()` added elsewhere in the module with
        `_resolve_session` left intact goes red on the stray-call assertion — the case a
        function-scoped check alone would miss.
        """
        import ast
        src = (ROOT / "scripts" / "build_polygon_gex.py").read_text()
        tree = ast.parse(src)

        def _called(node) -> set[str]:
            return {ast.unparse(c.func) for c in ast.walk(node)
                    if isinstance(c, ast.Call)}

        fn = next((n for n in ast.walk(tree)
                   if isinstance(n, ast.FunctionDef) and n.name == "_resolve_session"),
                  None)
        assert fn is not None, (
            "the accrual must resolve a SESSION from the accrual instant, not stamp the "
            "run date")

        assert "nyse_calendar.expected_last_session" in _called(fn), (
            "a datetime is an accrual INSTANT — the session it describes is "
            "expected_last_session(instant), not its calendar date")
        stray = {c for c in _called(tree)
                 if c.endswith("session_date") or c == "datetime.now(timezone.utc).date"}
        assert not stray, (
            f"{sorted(stray)} is called in build_polygon_gex. Stamping the UTC run date "
            "is the defect this replaced, and session_date() returns the ET calendar day "
            "— one session ahead for any post-midnight-UTC accrual. The only correct "
            "helper here is expected_last_session.")

        # datetime subclasses date: the wrong order silently takes every accrual INSTANT
        # as an explicit session, which is the defect wearing the fix's name.
        order = sorted((c.lineno, ast.unparse(c.args[1])) for c in ast.walk(fn)
                       if isinstance(c, ast.Call) and ast.unparse(c.func) == "isinstance")
        assert [t for _ln, t in order] == ["datetime", "date"], (
            f"isinstance checks run in the order {[t for _ln, t in order]}; datetime is a "
            "subclass of date, so the datetime branch must come first")

    def test_an_already_stored_session_is_not_overwritten(self):
        """FIRST WRITER WINS. Session stamping makes Friday-evening, Saturday, Sunday and
        Monday-pre-open runs all resolve to Friday; without this guard each would
        overwrite Friday's file with a staler and eventually PRE-MARKET snapshot —
        manufacturing exactly the mixed-tape rows the 2026-08-06 migration quarantined.
        """
        src = (ROOT / "scripts" / "build_polygon_gex.py").read_text()
        assert '"status": "already_present"' in src, (
            "a repeat run for a stored session must report its own status, not re-write")
        block = src.split('"status": "already_present"', 1)[0]
        assert "if path.exists() and not force:" in block
        # ahead of the fetch, so a repeat run spends no API quota either
        assert src.index("if path.exists() and not force:") < src.index(
            "client.snapshot(symbols, asof)")
        assert 'print(f"::notice title=polygon-session-present::' in src
        assert "--force" in src, "the guard needs a documented override"


def test_the_writers_do_not_rewrite_history():
    """The WRITERS are forward-only by design: no backfill, no delete, no rewrite.

    RULING 2026-08-06 — this law now has one named exception, and it is deliberately not
    here. The historical polygon_gex stamps were not merely non-session: they were the
    UTC RUN date, one session AHEAD of the market state each file held, and no reader can
    filter its way out of a wrong stamp. That history was rewritten exactly ONCE, under
    cross-section verification against an independent price store and against a pinned
    adjudication, by the dedicated audited script
    ``scripts/migrate_polygon_gex_session_stamps.py`` (manifest:
    ``docs/polygon_gex_session_stamp_migration.json``; precedent: #4207's repair of the
    dated GEX archive). The accrual writers below stay forward-only, and this test is
    what keeps them that way.
    """
    for rel in ("collectors/cboe.py", "scripts/build_polygon_gex.py"):
        src = (ROOT / rel).read_text()
        for banned in ("unlink(", "shutil.rmtree", "drop_duplicates(subset=[\"date\"], keep=\"first\")"):
            assert banned not in src.split("SESSION GATE", 1)[-1][:2000], (
                f"{rel}: the session gate must not mutate history ({banned})"
            )
