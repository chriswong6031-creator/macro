"""Weekend rows must not reach the options readers — the #3721 class, swept.

WHAT A WEEKEND ROW IS.  Several EOD options stores accrue a row on non-session days.  It
is NOT a harmless carry-forward duplicate: the builder RECOMPUTES iv30 / spot / walls /
net-GEX / skew off a stale carried-forward price, so the row is a fabricated observation
of a day that never traded.  Measured on the real stores, 2026-07-29:

    data/cboe/gex.parquet                    13 non-session rows of 39
    data/options_skew/snapshots.parquet        8 non-session dates of 28
    data/options_ivspread/snapshots.parquet    6 non-session dates of 21
    data/polygon_gex/summary_*.parquet        ~11 non-session dates of 39
    data/polygon_gex/chains/{DATE}.parquet     11 non-session snapshot files of 39
    (clean: options_flow/summary_* 0 of 136, tape_flow/daily 0 of 4,
     options_entry/state 0 of 3, market_structure/ledger 0 of 6)

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
``session_dates`` helpers.

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


FIXED = {
    "engine/market_gamma.py": ["nyse_calendar.session_rows(gex)",
                               "nyse_calendar.session_rows(hist)"],
    "engine/options_entry_state.py": ["nyse_calendar.session_rows(sdf)",
                                      "nyse_calendar.session_rows(df)",
                                      'nyse_calendar.session_rows(df, "date")'],
    "engine/options_stamp.py": ["nyse_calendar.session_rows(_raw_read_summary(tk))",
                                'nyse_calendar.session_rows(skew_df, "date")',
                                "nyse_calendar.session_dates(chain_dates)"],
    "engine/froth_fragility.py": ['nyse_calendar.session_rows(df, "date")'],
    "engine/altdata.py": ["nyse_calendar.session_dates("],
    "scripts/build_leader_radar.py": ["nyse_calendar_session_rows(df, date_col)"],
    "scripts/build_options_screener.py": ['nyse_calendar.session_rows(df, "date")'],
}


@pytest.mark.parametrize("rel", sorted(FIXED))
def test_the_fixed_readers_still_filter(rel):
    src = (ROOT / rel).read_text()
    for needle in FIXED[rel]:
        assert needle in src, f"{rel} lost its session filter: {needle!r}"


def test_the_two_canonical_fixes_are_untouched():
    """This sweep EXTENDS the idiom; it must not have disturbed its origins."""
    ms = (ROOT / "scripts" / "build_market_structure.py").read_text()
    assert "nyse_calendar.is_session(ts.date()) for ts in df.index" in ms
    scr = (ROOT / "scripts" / "build_options_screener.py").read_text()
    assert "nyse_calendar.is_session(ts.date()) for ts in idx" in scr


# ───────────────────────── the call_skew_rich activation gate counts SESSIONS


def test_the_skew_activation_gate_counts_sessions_not_rows(tmp_path):
    """THE live defect: min_obs=21 over a store whose dates include weekends.

    Frame: 22 dates, 4 of them non-session -> 18 real sessions. Unfiltered it clears a
    21-observation gate; filtered it correctly does not."""
    import scripts.build_leader_radar as blr

    sessions, cur = [], date(2026, 6, 22)
    while len(sessions) < 18:
        if nyse_calendar.is_session(cur):
            sessions.append(cur.isoformat())
        cur = date.fromordinal(cur.toordinal() + 1)
    weekends = [SAT, SUN, "2026-07-18", "2026-07-19"]
    dates = sorted(set(sessions + weekends))
    assert len(dates) == 22, dates

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
        "the gate must count the 18 SESSIONS, not the 22 stored dates"
    )
    assert got["TESTX"]["rr_25d"] is None, "18 < 21 — the chip must stay null"

    # neutralise the filter and the same store wrongly activates
    orig = blr.nyse_calendar_session_rows
    blr.nyse_calendar_session_rows = lambda d, c=None: d
    try:
        bad = blr._load_options_skew(tmp_path, min_obs=21)
    finally:
        blr.nyse_calendar_session_rows = orig
    assert bad["TESTX"]["skew_n_obs"] == 22
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
    assert n_sessions <= n_dates
    # informational, not a failure: record the ratio in the test output
    print(f"{rel}: {n_dates} dates -> {n_sessions} sessions")


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
