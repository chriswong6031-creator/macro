"""tests/test_positioning_persistence.py — OIP E3 positioning persistence.

Pins the things that would otherwise ship a fabricated number:

  1. Cluster truth table — matched contracts only, build/unwind split, top-N bound.
  2. Mixed-vintage REFUSAL — two snapshots with identical open interest for a name
     yield empty lists + same_vintage=True + a plain-word note, never "no change".
  3. Session filtering — weekend / holiday snapshot files are dropped before any
     delta or percentile is computed (#3721 weekend-row class; the real store holds
     11 non-session files out of 39).
  4. Unit seams — a fixture-shaped frame (int64 oi, object underlying, "C"/"P"
     rights) and a production-shaped one (float32 oi, category underlying, bool
     rights) produce IDENTICAL output; a normalised/fractional oi column is refused;
     oi_delta_pct is a PERCENT (1000 -> 1500 is 50.0, never 0.5).
  5. Wall persistence counting — consecutive-from-newest, padded for a root that
     entered mid-window, "whole window" phrasing when it never moved.
  6. Own-history percentile — session-filtered, low_confidence flagged, iv_rank idiom.
  7. Deep-history context — index roots only, calm staleness disclosure, and NO
     cross-source percentile of today's value.
  8. Degraded paths — no store dir, one snapshot, unreadable snapshot: honest empty
     with a note, never an exception into the caller.
  9. Payload strings are plain-word EN/ZH pairs with no internal slugs.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from engine import positioning_persistence as pp

# ── fixtures ─────────────────────────────────────────────────────────────────

D_THU = dt.date(2026, 7, 23)   # session
D_FRI = dt.date(2026, 7, 24)   # session
D_SAT = dt.date(2026, 7, 25)   # NOT a session
D_SUN = dt.date(2026, 7, 26)   # NOT a session
D_MON = dt.date(2026, 7, 27)   # session
D_JUNETEENTH = dt.date(2026, 6, 19)  # Friday, NYSE closed


def _chain(rows: list[dict], *, prod_shape: bool = False) -> pd.DataFrame:
    """Build a chain frame. prod_shape mirrors the real parquet dtypes exactly
    (category underlying, float32 numerics, bool is_call); otherwise plain fixture
    dtypes (object underlying, int64 oi, "C"/"P" rights)."""
    df = pd.DataFrame(rows)
    if prod_shape:
        df["underlying"] = df["underlying"].astype("category")
        for c in ("K", "oi", "spot"):
            df[c] = df[c].astype("float32")
        df["is_call"] = df["is_call"].map(
            lambda v: v is True or str(v).upper() in ("C", "CALL", "TRUE", "1"))
        df["is_call"] = df["is_call"].astype(bool)
    else:
        df["oi"] = df["oi"].astype("int64")
        df["is_call"] = df["is_call"].map(
            lambda v: "C" if (v is True or str(v).upper() in ("C", "CALL", "TRUE", "1"))
            else "P")
    return df


def _row(u: str, tkr: str, k: float, call: bool, oi: float, spot: float) -> dict:
    return {"underlying": u, "strike_ticker": tkr, "K": k,
            "is_call": call, "oi": oi, "spot": spot}


def _two_day_store(prod_shape: bool = False):
    """AAA: a call strike builds, a put strike unwinds, one contract is new-only and
    one is expired-only (both unmatched -> excluded). BBB: identical both days."""
    prior = _chain([
        _row("AAA", "O:AAA260821C00110000", 110.0, True, 1000, 100.0),
        _row("AAA", "O:AAA260918C00110000", 110.0, True, 500, 100.0),
        _row("AAA", "O:AAA260821P00090000", 90.0, False, 4000, 100.0),
        _row("AAA", "O:AAA260731P00095000", 95.0, False, 7777, 100.0),   # expires -> unmatched
        _row("BBB", "O:BBB260821C00055000", 55.0, True, 2000, 50.0),
        _row("BBB", "O:BBB260821P00045000", 45.0, False, 3000, 50.0),
    ], prod_shape=prod_shape)
    latest = _chain([
        _row("AAA", "O:AAA260821C00110000", 110.0, True, 1500, 101.0),
        _row("AAA", "O:AAA260918C00110000", 110.0, True, 900, 101.0),
        _row("AAA", "O:AAA260821P00090000", 90.0, False, 1000, 101.0),
        _row("AAA", "O:AAA261016C00130000", 130.0, True, 9999, 101.0),   # new -> unmatched
        _row("BBB", "O:BBB260821C00055000", 55.0, True, 2000, 50.0),
        _row("BBB", "O:BBB260821P00045000", 45.0, False, 3000, 50.0),
    ], prod_shape=prod_shape)
    frames = {D_FRI: prior, D_MON: latest}
    return (lambda: sorted(frames), lambda d: frames.get(d))


@pytest.fixture(autouse=True)
def _clean_cache():
    pp.reset_cache()
    yield
    pp.reset_cache()


# ── 1. cluster truth table ───────────────────────────────────────────────────

class TestClusterTruthTable:
    def test_build_and_unwind_split_on_matched_contracts_only(self):
        dates, read = _two_day_store()
        st = pp.load(chain_dates=dates, read_chain=read, use_cache=False)
        c = st.clusters("AAA")

        assert c["same_vintage"] is False
        assert c["prior_snapshot"] == D_FRI.isoformat()
        assert c["latest_snapshot"] == D_MON.isoformat()
        # 110 calls: (1000->1500) + (500->900) = +900 across 2 matched contracts
        assert len(c["new_oi"]) == 1
        build = c["new_oi"][0]
        assert build["K"] == 110.0 and build["right"] == "call"
        assert build["oi_prior"] == 1500 and build["oi_now"] == 2400
        assert build["oi_delta"] == 900
        assert build["contracts"] == 2
        # 90 puts: 4000 -> 1000 = -3000
        assert len(c["exit_oi"]) == 1
        unwind = c["exit_oi"][0]
        assert unwind["K"] == 90.0 and unwind["right"] == "put"
        assert unwind["oi_delta"] == -3000

    def test_unmatched_contracts_never_contribute(self):
        """A contract present on ONE side only (new listing / expired) is not a
        change in open interest — counting it would fabricate a build or an unwind."""
        dates, read = _two_day_store()
        st = pp.load(chain_dates=dates, read_chain=read, use_cache=False)
        c = st.clusters("AAA")
        strikes = {r["K"] for r in c["new_oi"] + c["exit_oi"]}
        assert 130.0 not in strikes, "new-only contract leaked into the clusters"
        assert 95.0 not in strikes, "expired-only contract leaked into the clusters"

    def test_top_n_is_bounded(self):
        rows_prior, rows_latest = [], []
        for i in range(12):
            k = 100.0 + i
            rows_prior.append(_row("CCC", f"O:CCC260821C{i:08d}", k, True, 1000, 100.0))
            rows_latest.append(_row("CCC", f"O:CCC260821C{i:08d}", k, True, 1000 + 100 * i, 100.0))
        frames = {D_FRI: _chain(rows_prior), D_MON: _chain(rows_latest)}
        st = pp.load(chain_dates=lambda: sorted(frames), read_chain=frames.get,
                     top_n=3, use_cache=False)
        c = st.clusters("CCC")
        assert len(c["new_oi"]) == 3
        # ranked by absolute change, biggest first
        assert [r["oi_delta"] for r in c["new_oi"]] == [1100, 1000, 900]

    def test_dist_pct_is_signed_distance_from_the_latest_price(self):
        dates, read = _two_day_store()
        st = pp.load(chain_dates=dates, read_chain=read, use_cache=False)
        c = st.clusters("AAA")
        # spot on the LATEST side is 101.0; the 110 strike is ~8.9% above it
        assert c["new_oi"][0]["dist_pct"] == pytest.approx(8.9, abs=0.05)
        assert c["exit_oi"][0]["dist_pct"] == pytest.approx(-10.9, abs=0.05)


# ── 2. mixed-vintage refusal ─────────────────────────────────────────────────

class TestMixedVintageRefusal:
    def test_identical_vintage_refuses_per_name(self):
        """BBB is byte-identical across the two snapshots while AAA advanced. The
        refusal is PER NAME: one repeating root must not silence the rest, and an
        all-zero delta must never be published as 'no change'."""
        dates, read = _two_day_store()
        st = pp.load(chain_dates=dates, read_chain=read, use_cache=False)
        bbb = st.clusters("BBB")
        assert bbb["same_vintage"] is True
        assert bbb["new_oi"] == [] and bbb["exit_oi"] == []
        assert bbb["matched_contracts"] == 0
        assert "identical open interest" in bbb["note_en"]
        assert "完全相同" in bbb["note_zh"]
        # the other name in the same file is unaffected
        assert st.clusters("AAA")["same_vintage"] is False

    def test_same_vintage_mask_is_content_not_filename(self):
        a = _chain([_row("X", "t1", 10.0, True, 100, 10.0)])
        b = _chain([_row("X", "t1", 10.0, True, 100, 10.0)])
        mask = pp.same_vintage_mask(
            pp.vintage_fingerprints(pp._normalise_chain(a)),
            pp.vintage_fingerprints(pp._normalise_chain(b)))
        assert bool(mask["X"]) is True
        c = _chain([_row("X", "t1", 10.0, True, 101, 10.0)])
        mask2 = pp.same_vintage_mask(
            pp.vintage_fingerprints(pp._normalise_chain(a)),
            pp.vintage_fingerprints(pp._normalise_chain(c)))
        assert bool(mask2["X"]) is False


# ── 3. session filtering ─────────────────────────────────────────────────────

class TestSessionFiltering:
    def test_weekend_and_holiday_snapshots_are_dropped(self):
        """The weekend files re-fetch Friday's reading. Comparing Sat vs Sun would
        produce a silent all-zero delta stamped with weekend dates."""
        base = _chain([_row("AAA", "t1", 110.0, True, 1000, 100.0)])
        moved = _chain([_row("AAA", "t1", 110.0, True, 1400, 101.0)])
        frames = {D_FRI: base, D_SAT: base, D_SUN: base, D_MON: moved}
        st = pp.load(chain_dates=lambda: sorted(frames), read_chain=frames.get,
                     use_cache=False)
        assert st.meta["prior_snapshot"] == D_FRI
        assert st.meta["latest_snapshot"] == D_MON
        c = st.clusters("AAA")
        assert c["new_oi"][0]["oi_delta"] == 400

    def test_default_chain_dates_filters_the_real_store(self):
        """Against the committed store: every date returned is an NYSE session, and
        the known non-session files (Saturdays, Sundays, Juneteenth) are gone."""
        from lib import nyse_calendar
        dates = pp.default_chain_dates()
        assert dates, "the committed chain store should not be empty"
        assert all(nyse_calendar.is_session(d) for d in dates)
        assert D_SAT not in dates and D_SUN not in dates
        assert D_JUNETEENTH not in dates


# ── 4. unit seams ────────────────────────────────────────────────────────────

class TestUnitSeams:
    def test_fixture_and_production_dtypes_agree(self):
        """The x100 / dtype class: the same numbers in fixture shape (int64 oi,
        object underlying, 'C'/'P') and production shape (float32 oi, category
        underlying, bool) must produce byte-identical cluster rows."""
        d_fix, r_fix = _two_day_store(prod_shape=False)
        d_prod, r_prod = _two_day_store(prod_shape=True)
        fix = pp.load(chain_dates=d_fix, read_chain=r_fix, use_cache=False).clusters("AAA")
        prod = pp.load(chain_dates=d_prod, read_chain=r_prod, use_cache=False).clusters("AAA")
        assert fix["new_oi"] == prod["new_oi"]
        assert fix["exit_oi"] == prod["exit_oi"]
        assert fix["matched_contracts"] == prod["matched_contracts"]

    def test_oi_delta_pct_is_a_percent_not_a_fraction(self):
        prior = _chain([_row("AAA", "t1", 100.0, True, 1000, 100.0)])
        latest = _chain([_row("AAA", "t1", 100.0, True, 1500, 100.0)])
        frames = {D_FRI: prior, D_MON: latest}
        st = pp.load(chain_dates=lambda: sorted(frames), read_chain=frames.get,
                     use_cache=False)
        row = st.clusters("AAA")["new_oi"][0]
        assert row["oi_delta_pct"] == 50.0, "must be a percent (50.0), never 0.5"

    def test_normalised_open_interest_is_refused(self, capsys):
        """An oi column of shares/fractions is a rescaled feed, not a contract count:
        every delta downstream would be a fabricated number. Refuse the snapshot."""
        frac = pd.DataFrame([
            {"underlying": "AAA", "strike_ticker": "t1", "K": 100.0,
             "is_call": True, "oi": 0.42, "spot": 100.0},
        ])
        with pytest.raises(pp.ChainShapeError, match="normalised"):
            pp._normalise_chain(frac)
        # and through the loader it is DROPPED with a GitHub annotation at line start
        good = _chain([_row("AAA", "t1", 100.0, True, 1000, 100.0)])
        frames = {D_FRI: good, D_MON: frac}
        st = pp.load(chain_dates=lambda: sorted(frames), read_chain=frames.get,
                     use_cache=False)
        out = capsys.readouterr().out
        line = next((ln for ln in out.splitlines() if "oi-chain-shape" in ln), "")
        assert line.startswith("::warning"), f"annotation must start the line: {out!r}"
        assert st.meta["sessions_covered"] == 1

    def test_non_integral_open_interest_is_refused(self):
        odd = pd.DataFrame([
            {"underlying": "AAA", "strike_ticker": "t1", "K": 100.0,
             "is_call": True, "oi": 1200.5, "spot": 100.0},
        ])
        with pytest.raises(pp.ChainShapeError, match="integral"):
            pp._normalise_chain(odd)

    def test_negative_open_interest_is_refused(self):
        bad = pd.DataFrame([
            {"underlying": "AAA", "strike_ticker": "t1", "K": 100.0,
             "is_call": True, "oi": -5.0, "spot": 100.0},
        ])
        with pytest.raises(pp.ChainShapeError, match="negative"):
            pp._normalise_chain(bad)

    def test_missing_columns_are_refused(self):
        with pytest.raises(pp.ChainShapeError, match="missing columns"):
            pp._normalise_chain(pd.DataFrame({"underlying": ["AAA"]}))


# ── 5. wall persistence counting ─────────────────────────────────────────────

class TestWallPersistence:
    def test_sessions_at_level_counts_back_from_the_newest(self):
        assert pp.sessions_at_level([100.0, 105.0, 110.0, 110.0, 110.0]) == 3
        assert pp.sessions_at_level([110.0, 110.0, 110.0]) == 3
        assert pp.sessions_at_level([110.0, 110.0, 105.0]) == 1
        assert pp.sessions_at_level([110.0, None, 110.0]) == 1
        assert pp.sessions_at_level([110.0, 110.0, None]) == 0
        assert pp.sessions_at_level([]) == 0

    def test_wall_level_and_count_over_a_window(self):
        """Heaviest call open interest ABOVE the price and heaviest put BELOW it.
        The call wall moves on the newest snapshot; the put wall never does."""
        def day(call_heavy_k, oi_heavy):
            return _chain([
                _row("AAA", "c1", 110.0, True, oi_heavy if call_heavy_k == 110 else 10, 100.0),
                _row("AAA", "c2", 120.0, True, oi_heavy if call_heavy_k == 120 else 10, 100.0),
                _row("AAA", "p1", 90.0, False, 5000, 100.0),
                _row("AAA", "p2", 80.0, False, 100, 100.0),
            ])
        frames = {
            dt.date(2026, 7, 20): day(110, 900),
            dt.date(2026, 7, 21): day(110, 900),
            dt.date(2026, 7, 22): day(110, 900),
            D_THU: day(120, 900),
        }
        st = pp.load(chain_dates=lambda: sorted(frames), read_chain=frames.get,
                     window_sessions=4, use_cache=False)
        w = st.wall_persistence("AAA")
        assert w["sessions_covered"] == 4
        assert w["window_start"] == "2026-07-20"
        assert w["window_end"] == D_THU.isoformat()
        assert w["call_side"]["level"] == 120.0
        assert w["call_side"]["sessions_at_level"] == 1
        assert w["put_side"]["level"] == 90.0
        assert w["put_side"]["sessions_at_level"] == 4
        # never-moved side gets the "whole window" phrasing, not a bare count
        assert "every one of the 4" in w["put_side"]["note_en"]
        assert "may have held longer" in w["put_side"]["note_en"]

    def test_root_entering_mid_window_cannot_inflate_its_count(self):
        """A name first seen on the newest snapshot must report 1, not the window
        length — the series is padded so it cannot borrow another root's history."""
        old = _chain([_row("AAA", "c1", 110.0, True, 900, 100.0),
                      _row("AAA", "p1", 90.0, False, 900, 100.0)])
        both = _chain([_row("AAA", "c1", 110.0, True, 900, 100.0),
                       _row("AAA", "p1", 90.0, False, 900, 100.0),
                       _row("NEW", "c9", 55.0, True, 700, 50.0),
                       _row("NEW", "p9", 45.0, False, 700, 50.0)])
        frames = {dt.date(2026, 7, 21): old, dt.date(2026, 7, 22): old, D_THU: both}
        st = pp.load(chain_dates=lambda: sorted(frames), read_chain=frames.get,
                     window_sessions=3, use_cache=False)
        assert st.wall_persistence("AAA")["call_side"]["sessions_at_level"] == 3
        new = st.wall_persistence("NEW")
        assert new["sessions_covered"] == 3
        assert new["call_side"]["sessions_at_level"] == 1

    def test_uncovered_name_gets_no_wall_block_at_all(self):
        dates, read = _two_day_store()
        st = pp.load(chain_dates=dates, read_chain=read, use_cache=False)
        assert st.wall_persistence("SPX") is None

    def test_oi_walls_ignores_wrong_side_strikes(self):
        df = pp._normalise_chain(_chain([
            _row("AAA", "c1", 90.0, True, 9999, 100.0),    # call BELOW spot — ignored
            _row("AAA", "c2", 110.0, True, 50, 100.0),
            _row("AAA", "p1", 120.0, False, 9999, 100.0),  # put ABOVE spot — ignored
            _row("AAA", "p2", 80.0, False, 50, 100.0),
        ]))
        w = pp.oi_walls(df).set_index("underlying").loc["AAA"]
        assert w["call_K"] == 110.0 and w["put_K"] == 80.0


# ── 6. own-history percentile ────────────────────────────────────────────────

class TestOwnHistoryPercentile:
    def _hist(self):
        # 2026-07-25 / 26 are weekend rows that REPEAT the Friday reading — the real
        # cboe store carries 13 of these in 36 rows for SPY.
        return [
            {"date": "2026-07-20", "net_gex_bn": -1.0},
            {"date": "2026-07-21", "net_gex_bn": -2.0},
            {"date": "2026-07-22", "net_gex_bn": -3.0},
            {"date": "2026-07-23", "net_gex_bn": -4.0},
            {"date": "2026-07-24", "net_gex_bn": -5.0},
            {"date": "2026-07-25", "net_gex_bn": -5.0},
            {"date": "2026-07-26", "net_gex_bn": -5.0},
        ]

    def test_weekend_rows_are_excluded_from_the_denominator(self):
        got = pp.net_gex_percentile(self._hist(), -2.5)
        assert got["n_sessions"] == 5, "weekend rows double-counted the distribution"
        assert got["window_start"] == "2026-07-20"
        assert got["window_end"] == "2026-07-24"
        # strictly-below share (iv_rank idiom): -3, -4, -5 are below -2.5 -> 3/5
        assert got["pctile"] == 60

    def test_short_record_is_flagged_and_said_in_plain_words(self):
        got = pp.net_gex_percentile(self._hist(), -2.5)
        assert got["low_confidence"] is True
        assert "record is short" in got["note_en"]
        assert "记录较短" in got["note_zh"]

    def test_too_few_sessions_returns_none(self):
        assert pp.net_gex_percentile(
            [{"date": "2026-07-20", "net_gex_bn": -1.0}], -1.0) is None
        assert pp.net_gex_percentile(None, -1.0) is None
        assert pp.net_gex_percentile(self._hist(), None) is None

    def test_long_record_is_not_flagged(self):
        hist = [{"date": d.isoformat(), "net_gex_bn": float(i)}
                for i, d in enumerate(_sessions(80))]
        got = pp.net_gex_percentile(hist, 1000.0)
        assert got["n_sessions"] == 80
        assert got["low_confidence"] is False
        assert got["pctile"] == 100
        assert "record is short" not in got["note_en"]


def _sessions(n: int) -> list[dt.date]:
    from lib import nyse_calendar
    out, d = [], dt.date(2026, 1, 2)
    while len(out) < n:
        if nyse_calendar.is_session(d):
            out.append(d)
        d += dt.timedelta(days=1)
    return out


# ── 7. deep-history context ──────────────────────────────────────────────────

class TestDeepHistory:
    def _hist(self, last="2026-07-02"):
        idx = pd.to_datetime(["2017-01-03", "2020-06-15", "2024-03-11", last])
        return pd.DataFrame({"net_gex_bn": [10.0, -5.0, 0.0, -2.0],
                             "gamma_regime": ["long", "short", "long", "short"]},
                            index=idx)

    def test_only_index_roots_get_a_block(self):
        r = lambda g, n: self._hist()  # noqa: E731
        assert pp.deep_history_context("SPY", reader=r) is not None
        assert pp.deep_history_context("NVDA", reader=r) is None
        assert pp.deep_history_context("SPX", reader=r) is None

    def test_stale_window_is_disclosed_calmly(self):
        now = dt.datetime(2026, 7, 29, 23, 0, tzinfo=dt.timezone.utc)
        got = pp.deep_history_context("SPY", reader=lambda g, n: self._hist(), now=now)
        assert got["window_start"] == "2017-01-03"
        assert got["window_end"] == "2026-07-02"
        assert got["sessions_behind"] > pp.DEEP_HISTORY_STALE_SESSIONS
        assert got["stale"] is True
        assert "behind the latest close" in got["note_en"]
        assert "落后" in got["note_zh"]
        # calm, not an alarm
        low = got["note_en"].lower()
        for banned in ("error", "failed", "broken", "alert", "stale", "warning"):
            assert banned not in low, f"alarm word {banned!r} in a Tier-1 disclosure"

    def test_fresh_window_says_current(self):
        now = dt.datetime(2026, 7, 29, 23, 0, tzinfo=dt.timezone.utc)
        got = pp.deep_history_context("SPY", now=now,
                                      reader=lambda g, n: self._hist("2026-07-28"))
        assert got["stale"] is False
        assert "is current" in got["note_en"]

    def test_no_cross_source_percentile_is_emitted(self):
        """The rebuild is a ThetaData reconstruction; today's payload value comes from
        the Cboe chain. Placing one inside the other is the mixed-source class, so the
        block reports the WINDOW and SPREAD and says today's value is not placed."""
        got = pp.deep_history_context("SPY", reader=lambda g, n: self._hist())
        assert "pctile" not in got and "percentile" not in got
        assert "not placed inside that window" in got["note_en"]
        assert got["net_gex_bn_min"] == -5.0 and got["net_gex_bn_max"] == 10.0

    def test_absent_or_empty_store_returns_none(self):
        assert pp.deep_history_context("SPY", reader=lambda g, n: None) is None
        assert pp.deep_history_context("SPY", reader=lambda g, n: pd.DataFrame()) is None
        assert pp.deep_history_context(
            "SPY", reader=lambda g, n: pd.DataFrame({"other": [1]},
                                                    index=pd.to_datetime(["2020-01-02"]))) is None

    def test_reader_exception_degrades_to_none(self):
        def boom(g, n):
            raise OSError("store unreadable")
        assert pp.deep_history_context("SPY", reader=boom) is None


# ── 8. degraded paths ────────────────────────────────────────────────────────

class TestDegradedPaths:
    def test_no_snapshots_at_all(self):
        st = pp.load(chain_dates=lambda: [], read_chain=lambda d: None, use_cache=False)
        c = st.clusters("SPY")
        assert c["new_oi"] == [] and c["exit_oi"] == []
        assert c["prior_snapshot"] is None and c["latest_snapshot"] is None
        assert "No per-strike chain snapshots are stored" in c["note_en"]
        assert st.wall_persistence("SPY") is None

    def test_single_snapshot_says_so(self):
        one = _chain([_row("AAA", "t1", 110.0, True, 1000, 100.0)])
        st = pp.load(chain_dates=lambda: [D_MON], read_chain=lambda d: one,
                     use_cache=False)
        c = st.clusters("AAA")
        assert c["new_oi"] == [] and c["exit_oi"] == []
        assert "Only one stored chain snapshot" in c["note_en"]
        # the wall read still works off the one snapshot it has
        assert st.wall_persistence("AAA")["call_side"]["sessions_at_level"] == 1

    def test_unreadable_snapshot_is_skipped_not_fatal(self):
        good = _chain([_row("AAA", "t1", 110.0, True, 1000, 100.0)])
        moved = _chain([_row("AAA", "t1", 110.0, True, 1200, 100.0)])
        frames = {D_THU: good, D_FRI: None, D_MON: moved}
        st = pp.load(chain_dates=lambda: sorted(frames), read_chain=frames.get,
                     use_cache=False)
        assert st.meta["prior_snapshot"] == D_THU
        assert st.meta["latest_snapshot"] == D_MON
        assert st.clusters("AAA")["new_oi"][0]["oi_delta"] == 200

    def test_listing_exception_degrades_to_empty(self):
        def boom():
            raise OSError("no store dir")
        st = pp.load(chain_dates=boom, read_chain=lambda d: None, use_cache=False)
        assert st.meta["sessions_available"] == 0
        assert st.clusters("SPY")["new_oi"] == []


# ── 9. payload strings are plain-word EN/ZH pairs ────────────────────────────

_BANNED_IN_COPY = (
    "polygon_gex", "oi_delta", "gex_state", "same_vintage", "strike_ticker",
    "n=", "validated", "None", "null", "nan", "display-only", "authority_tier",
    "falsifier", "refuted", "证伪",
)


def _all_notes(obj, out=None):
    out = [] if out is None else out
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and k.startswith("note_") and isinstance(v, str):
                out.append(v)
            else:
                _all_notes(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _all_notes(v, out)
    return out


class TestPlainWordCopy:
    def test_every_note_is_slug_free_and_paired(self):
        dates, read = _two_day_store()
        st = pp.load(chain_dates=dates, read_chain=read, use_cache=False)
        blocks = [st.clusters("AAA"), st.clusters("BBB"), st.clusters("SPX"),
                  st.wall_persistence("AAA"),
                  pp.deep_history_context("SPY", reader=lambda g, n: pd.DataFrame(
                      {"net_gex_bn": [1.0, 2.0]},
                      index=pd.to_datetime(["2020-01-02", "2026-07-02"])))]
        for b in blocks:
            assert b is not None
            notes = _all_notes(b)
            assert notes, f"block carries no note strings: {sorted(b)}"
            # EN/ZH always come in pairs
            for parent in _note_parents(b):
                assert parent.get("note_en") and parent.get("note_zh"), \
                    f"unpaired note in {sorted(parent)}"
            for n in notes:
                for bad in _BANNED_IN_COPY:
                    assert bad not in n, f"{bad!r} leaked into user-facing copy: {n!r}"

    def test_zh_notes_carry_no_english_state_names(self):
        """ZH must be independently plain — no English state names or words inside it.
        Ticker roots are the one allowed ASCII token (the site shows SPY as SPY in
        both languages), so they are stripped before the check rather than excusing
        the whole block from it."""
        dates, read = _two_day_store()
        st = pp.load(chain_dates=dates, read_chain=read, use_cache=False)
        deep = pp.deep_history_context("SPY", reader=lambda g, n: pd.DataFrame(
            {"net_gex_bn": [1.0, 2.0]},
            index=pd.to_datetime(["2020-01-02", "2026-07-02"])))
        roots = ("SPY", "QQQ", "IWM", "DIA", "AAA", "BBB")
        for b in (st.clusters("AAA"), st.clusters("BBB"), st.wall_persistence("AAA"), deep):
            zh = [v for k, v in _flat(b) if k == "note_zh"]
            assert zh
            for s in zh:
                probe = s
                for r in roots:
                    probe = probe.replace(r, "")
                # "Gamma" is the term the ZH surfaces already use untranslated; every
                # other English word is a leak.
                probe = probe.replace("Gamma", "")
                letters = [ch for ch in probe if ch.isascii() and ch.isalpha()]
                assert not letters, f"English letters inside a ZH note: {s!r}"


def _note_parents(obj, out=None):
    out = [] if out is None else out
    if isinstance(obj, dict):
        if any(isinstance(k, str) and k.startswith("note_") for k in obj):
            out.append(obj)
        for v in obj.values():
            _note_parents(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _note_parents(v, out)
    return out


def _flat(obj, out=None):
    out = [] if out is None else out
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str):
                out.append((k, v))
            else:
                _flat(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _flat(v, out)
    return out


# ── 10. process cache is shared and resettable ───────────────────────────────

def test_cache_is_reused_across_calls():
    calls = {"n": 0}

    def dates():
        calls["n"] += 1
        return []

    pp.reset_cache()
    a = pp.load(chain_dates=dates, read_chain=lambda d: None)
    b = pp.load(chain_dates=dates, read_chain=lambda d: None)
    assert a is b
    assert calls["n"] == 1, "the store must be built exactly once per process"
    pp.reset_cache()
    c = pp.load(chain_dates=dates, read_chain=lambda d: None)
    assert c is not a and calls["n"] == 2


# ── 11. end-to-end against the REAL committed store ──────────────────────────

def test_real_store_lights_the_clusters():
    """Gate 1 (fresh-eyes, production data): the committed chain store must actually
    light the field this wave exists to light — for a long time it returned [] by
    construction, so a shape-only assertion would pass on a dead read."""
    st = pp.load(use_cache=False)
    if st.meta["sessions_available"] < 2:
        pytest.skip("chain store has fewer than 2 session snapshots in this checkout")
    assert st.meta["roots_with_clusters"] > 100, st.meta
    c = st.clusters("SPY")
    assert c["same_vintage"] is False
    assert c["matched_contracts"] > 0
    assert c["new_oi"] and c["exit_oi"], "SPY clusters are still empty on real data"
    assert all(r["oi_delta"] > 0 for r in c["new_oi"])
    assert all(r["oi_delta"] < 0 for r in c["exit_oi"])
    w = st.wall_persistence("SPY")
    assert w["call_side"]["level"] and w["put_side"]["level"]
    assert 1 <= w["call_side"]["sessions_at_level"] <= w["sessions_covered"]


# ── 12. matches_board_wall is stamped in the payload layer, not faked here ───

class TestMatchesBoardWall:
    """The open-interest wall must never silently stand in for the payload's
    dollar-gamma call_wall / put_wall. gex_state stamps an explicit comparison."""

    def _block(self, call_wall, put_wall, root="AAA"):
        """Prime the PROCESS cache with a fixture store (use_cache=True is the
        mechanism gex_state reads through), then ask the payload layer."""
        from engine import gex_state as gs

        pp.reset_cache()
        day = _chain([
            _row("AAA", "c1", 110.0, True, 900, 100.0),
            _row("AAA", "p1", 90.0, False, 900, 100.0),
        ])
        frames = {D_FRI: day, D_MON: day}
        primed = pp.load(chain_dates=lambda: sorted(frames), read_chain=frames.get)
        assert primed.wall_persistence("AAA") is not None, "fixture store did not prime"
        try:
            return gs._wall_persistence(root, call_wall, put_wall)
        finally:
            pp.reset_cache()

    def test_true_when_the_levels_coincide(self):
        b = self._block(110.0, 90.0)
        assert b["call_side"]["matches_board_wall"] is True
        assert b["put_side"]["matches_board_wall"] is True

    def test_false_when_they_disagree(self):
        b = self._block(115.0, 85.0)
        assert b["call_side"]["matches_board_wall"] is False
        assert b["put_side"]["matches_board_wall"] is False

    def test_null_when_the_board_wall_is_absent(self):
        b = self._block(None, None)
        assert b["call_side"]["matches_board_wall"] is None
        assert b["put_side"]["matches_board_wall"] is None

    def test_uncovered_name_stays_absent_even_with_a_board_wall(self):
        """A name the chain store does not cover gets NO block — the payload must not
        grow a wall_persistence key whose only content is the board wall echoed back."""
        assert self._block(5000.0, 4000.0, root="SPX") is None


# ── 13. B1 — cross-source price is emitted and disclosed, never mixed ────────

class TestSnapshotSpotDisclosure:
    """dist_pct and the wall split are measured against the SNAPSHOT's price while the
    payload's own `spot` is the board's. Both must be visible, and a material gap said."""

    def test_both_blocks_emit_the_price_they_used(self):
        dates, read = _two_day_store()
        st = pp.load(chain_dates=dates, read_chain=read, use_cache=False)
        # latest snapshot's AAA spot is 101.0 (prior was 100.0) — the latest wins
        assert st.clusters("AAA")["snapshot_spot"] == 101.0
        assert st.wall_persistence("AAA")["snapshot_spot"] == 101.0

    def test_dist_pct_uses_the_snapshot_price_not_the_board_price(self):
        dates, read = _two_day_store()
        st = pp.load(chain_dates=dates, read_chain=read, use_cache=False)
        row = st.clusters("AAA")["new_oi"][0]
        # K=110 against the snapshot's 101.0 -> +8.9%. Against a board spot of, say,
        # 120 it would be NEGATIVE — which is exactly why the price is published.
        assert row["dist_pct"] == pytest.approx(8.9, abs=0.05)

    def test_divergence_note_fires_above_the_threshold(self):
        note = pp.spot_divergence_note(197.01, 192.32)      # 2.4% apart
        assert note is not None
        assert "197.01" in note[0] and "2.4%" in note[0]
        assert "197.01" in note[1] and "2.4%" in note[1]

    def test_divergence_note_silent_inside_the_threshold(self):
        assert pp.spot_divergence_note(740.86, 735.05) is None   # 0.79% apart
        assert pp.spot_divergence_note(100.0, 100.0) is None

    def test_divergence_note_null_safe(self):
        assert pp.spot_divergence_note(None, 100.0) is None
        assert pp.spot_divergence_note(100.0, None) is None
        assert pp.spot_divergence_note(100.0, 0.0) is None
        assert pp.spot_divergence_note(float("nan"), 100.0) is None

    def test_wall_block_states_the_comparison_basis(self):
        """matches_board_wall is a cross-source, exact-strike comparison and False is the
        common case — the block must explain that rather than leaving it as a bare flag."""
        dates, read = _two_day_store()
        st = pp.load(chain_dates=dates, read_chain=read, use_cache=False)
        w = st.wall_persistence("AAA")
        assert w["basis_en"] and w["basis_zh"]
        assert "different chain source" in w["basis_en"]
        assert "different strikes" in w["basis_en"]


# ── 14. B2 — snapshots on both dates, zero shared contracts ──────────────────

class TestNoMatchedContracts:
    def _store(self):
        """DDD is listed on both dates but every contract id turned over."""
        prior = _chain([
            _row("DDD", "O:DDD260731C00100000", 100.0, True, 500, 100.0),
            _row("DDD", "O:DDD260731P00090000", 90.0, False, 400, 100.0),
        ])
        latest = _chain([
            _row("DDD", "O:DDD260821C00100000", 100.0, True, 700, 101.0),
            _row("DDD", "O:DDD260821P00090000", 90.0, False, 300, 101.0),
        ])
        frames = {D_FRI: prior, D_MON: latest}
        return pp.load(chain_dates=lambda: sorted(frames), read_chain=frames.get,
                       use_cache=False)

    def test_state_is_distinct_from_absent(self):
        c = self._store().clusters("DDD")
        assert c["new_oi"] == [] and c["exit_oi"] == []
        assert c["matched_contracts"] == 0
        assert c["same_vintage"] is False
        # the two dates ARE known, so the copy must not claim nothing is stored
        assert c["prior_snapshot"] == D_FRI.isoformat()
        assert c["latest_snapshot"] == D_MON.isoformat()
        assert "No per-strike chain snapshots are stored" not in c["note_en"]
        assert "exist for this name on both" in c["note_en"]
        assert "turned over" in c["note_en"]
        assert "完全更替" in c["note_zh"]

    def test_absent_root_still_gets_the_absent_copy(self):
        c = self._store().clusters("ZZZZ")
        assert "No per-strike chain snapshots are stored" in c["note_en"]
        assert c["prior_snapshot"] is None

    def test_reachable_on_the_real_store(self):
        """2026-07-02 -> 2026-07-07 in the committed store: CRWD is listed on both dates
        with zero shared contract ids (1 of 350 shared roots)."""
        import datetime as _d
        a, b = _d.date(2026, 7, 2), _d.date(2026, 7, 7)
        if not all((pp._chains_dir() / f"{d.isoformat()}.parquet").exists() for d in (a, b)):
            pytest.skip("that vintage pair is not in this checkout")
        st = pp.load(chain_dates=lambda: [a, b], read_chain=pp.default_read_chain,
                     window_sessions=2, use_cache=False)
        c = st.clusters("CRWD")
        assert c["matched_contracts"] == 0
        assert c["prior_snapshot"] == a.isoformat()
        assert "turned over" in c["note_en"], c["note_en"]


# ── 15. M1 — pair gap and store staleness are disclosed ──────────────────────

class TestGapAndStaleness:
    def _straddling_store(self, prior_d, latest_d):
        prior = _chain([_row("AAA", "t1", 110.0, True, 1000, 100.0),
                        _row("AAA", "p1", 90.0, False, 1000, 100.0)])
        latest = _chain([_row("AAA", "t1", 110.0, True, 1600, 100.0),
                         _row("AAA", "p1", 90.0, False, 1000, 100.0)])
        frames = {prior_d: prior, latest_d: latest}
        return pp.load(chain_dates=lambda: sorted(frames), read_chain=frames.get,
                       window_sessions=2, use_cache=False)

    def test_consecutive_pair_says_nothing_about_a_gap(self):
        st = self._straddling_store(D_FRI, D_MON)     # Fri -> Mon IS consecutive
        c = st.clusters("AAA")
        assert c["sessions_apart"] == 1
        assert "sessions apart" not in c["note_en"]

    def test_pair_straddling_a_gap_says_how_far(self):
        st = self._straddling_store(dt.date(2026, 6, 15), dt.date(2026, 7, 27))
        c = st.clusters("AAA")
        assert c["sessions_apart"] and c["sessions_apart"] > 20
        assert f"{c['sessions_apart']} trading sessions apart" in c["note_en"]
        assert "not consecutive" in c["note_en"]
        assert "并不相邻" in c["note_zh"]

    def test_stalled_collector_is_disclosed_in_both_blocks(self):
        st = self._straddling_store(dt.date(2026, 6, 15), dt.date(2026, 6, 16))
        c = st.clusters("AAA")
        w = st.wall_persistence("AAA")
        assert c["stale"] is True and c["sessions_behind"] > pp.CHAIN_STALE_SESSIONS
        assert "behind the latest close" in c["note_en"]
        assert w["stale"] is True and w["sessions_behind"] == c["sessions_behind"]
        assert "behind the latest close" in w["call_side"]["note_en"]
        assert "落后" in w["put_side"]["note_zh"]

    def test_current_store_adds_no_staleness_noise(self):
        """Pinned to a FIXED clock, not the wall clock. The earlier version skipped
        itself once the committed fixture dates aged past the threshold, which would
        have silently disarmed the assertion from ~2026-07-31 onward — the
        silently-disarmed-test class. `now` is a real seam on load()/_build()."""
        now = dt.datetime(2026, 7, 29, 23, 0, tzinfo=dt.timezone.utc)
        st = pp.load(use_cache=False, now=now)
        if st.meta["sessions_available"] < 2:
            pytest.skip("chain store too short in this checkout")
        c = st.clusters("SPY")
        assert c["sessions_behind"] == 0, c["sessions_behind"]
        assert c["stale"] is False
        assert "behind the latest close" not in c["note_en"]
        w = st.wall_persistence("SPY")
        assert w["stale"] is False
        assert "behind the latest close" not in w["call_side"]["note_en"]

    def test_staleness_copy_is_calm(self):
        st = self._straddling_store(dt.date(2026, 6, 15), dt.date(2026, 6, 16))
        low = st.clusters("AAA")["note_en"].lower()
        for banned in ("error", "failed", "broken", "alert", "warning", "stale"):
            assert banned not in low, f"alarm word {banned!r} in the disclosure"


# ── 16. M2 — a failed build is memoised, not retried per root ────────────────

class TestFailureMemoisation:
    def test_build_failure_is_cached_and_warned_once(self, monkeypatch, capsys):
        calls = {"n": 0}

        def boom(*a, **k):
            calls["n"] += 1
            raise RuntimeError("synthetic pandas failure")

        pp.reset_cache()
        monkeypatch.setattr(pp, "_build", boom)
        first = pp.load()
        for _ in range(20):
            assert pp.load() is first
        assert calls["n"] == 1, (
            "each load() re-ran the failing build — at board scale gex_state calls this "
            "3x per root, so 555 roots would mean 1,665 rebuilds")
        out = capsys.readouterr().out
        warns = [ln for ln in out.splitlines() if "positioning-persistence-degraded" in ln]
        assert len(warns) == 1
        assert warns[0].startswith("::warning")

    def test_degraded_store_answers_every_root_honestly(self, monkeypatch):
        pp.reset_cache()
        monkeypatch.setattr(pp, "_build",
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("nope")))
        st = pp.load()
        assert st.meta["degraded"] is True
        assert "nope" in st.meta["degraded_reason"]
        c = st.clusters("SPY")
        assert c["new_oi"] == [] and c["exit_oi"] == []
        # A READ FAILURE must not claim nothing is stored — the store may be intact and
        # merely unreadable this run, and the two send an operator to different places.
        assert "could not be read" in c["note_en"]
        assert "No per-strike chain snapshots are stored" not in c["note_en"]
        assert c["note_en"] == pp.OI_DELTA_UNAVAILABLE_EN
        assert c["note_zh"] == pp.OI_DELTA_UNAVAILABLE_ZH
        assert st.wall_persistence("SPY") is None


# ── 17. M5 — the join-key invariant holds before the merge ───────────────────

class TestJoinKeyInvariant:
    def test_null_shaped_keys_are_dropped(self):
        df = pd.DataFrame([
            {"underlying": "AAA", "strike_ticker": "t1", "K": 100.0,
             "is_call": True, "oi": 100, "spot": 100.0},
            {"underlying": "AAA", "strike_ticker": "nan", "K": 100.0,
             "is_call": True, "oi": 100, "spot": 100.0},
            {"underlying": "AAA", "strike_ticker": None, "K": 100.0,
             "is_call": True, "oi": 100, "spot": 100.0},
            {"underlying": "AAA", "strike_ticker": "", "K": 100.0,
             "is_call": True, "oi": 100, "spot": 100.0},
        ])
        out = pp._normalise_chain(df)
        assert list(out["strike_ticker"]) == ["t1"]
        assert out.attrs["dropped_bad_join_keys"] == 3

    def test_duplicate_keys_are_dropped_on_both_sides(self):
        df = pd.DataFrame([
            {"underlying": "AAA", "strike_ticker": "dup", "K": 100.0,
             "is_call": True, "oi": 100, "spot": 100.0},
            {"underlying": "AAA", "strike_ticker": "dup", "K": 100.0,
             "is_call": True, "oi": 200, "spot": 100.0},
            {"underlying": "AAA", "strike_ticker": "ok", "K": 105.0,
             "is_call": True, "oi": 300, "spot": 100.0},
        ])
        out = pp._normalise_chain(df)
        assert list(out["strike_ticker"]) == ["ok"], "a duplicated id must not survive"
        assert out.attrs["dropped_bad_join_keys"] == 2

    def test_cartesian_blowup_cannot_happen(self):
        """2 nulls x 2 nulls would be 4 invented contract pairs feeding the OI sums."""
        def side(oi_a, oi_b):
            return pd.DataFrame([
                {"underlying": "AAA", "strike_ticker": None, "K": 100.0,
                 "is_call": True, "oi": oi_a, "spot": 100.0},
                {"underlying": "AAA", "strike_ticker": "nan", "K": 100.0,
                 "is_call": True, "oi": oi_a, "spot": 100.0},
                {"underlying": "AAA", "strike_ticker": "real", "K": 110.0,
                 "is_call": True, "oi": oi_b, "spot": 100.0},
            ])
        prior = pp._normalise_chain(side(1000, 500))
        latest = pp._normalise_chain(side(9999, 800))
        d = pp.matched_oi_delta(prior, latest)
        assert len(d) == 1 and int(d["contracts"].iloc[0]) == 1
        assert int(d["oi_delta"].iloc[0]) == 300

    def test_loud_when_it_fires_and_counted_in_meta(self, capsys):
        bad = pd.DataFrame([
            {"underlying": "AAA", "strike_ticker": "t1", "K": 110.0,
             "is_call": True, "oi": 100, "spot": 100.0},
            {"underlying": "AAA", "strike_ticker": None, "K": 110.0,
             "is_call": True, "oi": 100, "spot": 100.0},
            {"underlying": "AAA", "strike_ticker": "p1", "K": 90.0,
             "is_call": False, "oi": 100, "spot": 100.0},
        ])
        frames = {D_FRI: bad, D_MON: bad}
        st = pp.load(chain_dates=lambda: sorted(frames), read_chain=frames.get,
                     use_cache=False)
        out = capsys.readouterr().out
        line = next((ln for ln in out.splitlines() if "oi-chain-join-keys" in ln), "")
        assert line.startswith("::warning"), out
        assert "1 row(s)" in line
        assert st.meta["dropped_bad_join_keys"] == 2      # one per snapshot

    def test_clean_real_store_reports_zero(self):
        st = pp.load(use_cache=False)
        assert st.meta["dropped_bad_join_keys"] == 0, (
            "the committed store should have no null/duplicate contract ids")


# ── 18. m8 — vintage equality is exact, not tolerant ────────────────────────

def test_vintage_match_is_exact_not_within_a_tolerance():
    """np.isclose's rtol=1e-5 on a liquid root's ~1e8 total open interest is a
    ~1,000-contract tolerance — it would call a real thousand-contract day 'the same
    vintage' and suppress the delta."""
    a = pd.DataFrame({"contracts": [10], "oi_total": [100_000_000.0], "spot": [500.0]},
                     index=pd.Index(["X"]))
    b = pd.DataFrame({"contracts": [10], "oi_total": [100_000_500.0], "spot": [500.0]},
                     index=pd.Index(["X"]))
    assert bool(pp.same_vintage_mask(a, b)["X"]) is False
    same = pd.DataFrame({"contracts": [10], "oi_total": [100_000_000.0], "spot": [500.0]},
                        index=pd.Index(["X"]))
    assert bool(pp.same_vintage_mask(a, same)["X"]) is True


# ── 19. m10 — the ends of the percentile range read as sentences ─────────────

def test_percentile_ends_are_plain_words():
    hist = [{"date": d.isoformat(), "net_gex_bn": 5.0} for d in _sessions(10)]
    bottom = pp.net_gex_percentile(hist, -100.0)
    assert bottom["pctile"] == 0
    assert "above 0%" not in bottom["note_en"]
    assert "at or below every one" in bottom["note_en"]
    assert "不高于" in bottom["note_zh"]
    top = pp.net_gex_percentile(hist, 100.0)
    assert top["pctile"] == 100
    assert "above 100%" not in top["note_en"]
    assert "above every one" in top["note_en"]
    middle = pp.net_gex_percentile(
        [{"date": d.isoformat(), "net_gex_bn": float(i)} for i, d in enumerate(_sessions(10))],
        4.5)
    assert 0 < middle["pctile"] < 100
    assert f"above {middle['pctile']}%" in middle["note_en"]


# ── 20. m2 — deep_history quantiles are session-filtered ────────────────────

def test_deep_history_quantiles_exclude_non_session_rows():
    """The real rebuild carries a 2019-02-02 Saturday row in every root; n_sessions and
    the spread must be computed after the filter, as the docstring claims."""
    idx = pd.to_datetime(["2020-01-02", "2020-01-03", "2019-02-02", "2020-01-06"])
    hist = pd.DataFrame({"net_gex_bn": [1.0, 2.0, 999.0, 3.0]}, index=idx)
    got = pp.deep_history_context("SPY", reader=lambda g, n: hist)
    assert got["n_sessions"] == 3, "the Saturday row leaked into the denominator"
    assert got["net_gex_bn_max"] == 3.0, "the Saturday row leaked into the spread"
    assert got["window_end"] == "2020-01-06"


# ── 21. B1 residual — a sign flip triggers the note at ANY magnitude ─────────

class TestSignFlipTrigger:
    """Adjudication: the note fires on divergence > 2% OR when sign(K - snapshot_spot)
    != sign(K - board_spot). Direction is what breaks the reader's model, not distance —
    the distance threshold alone left 27 of 104 flipped rows undisclosed."""

    def test_detects_a_strike_between_the_two_prices(self):
        # prices only 0.5% apart (well under the threshold) but K sits between them
        assert pp.rows_cross_the_board_price([{"K": 100.2}], 100.0, 100.5) is True
        assert pp.rows_cross_the_board_price([{"K": 100.5}], 100.0, 100.5) is True
        assert pp.rows_cross_the_board_price([{"K": 100.0}], 100.0, 100.5) is False

    def test_ignores_strikes_on_the_same_side_of_both(self):
        assert pp.rows_cross_the_board_price([{"K": 120.0}], 100.0, 100.5) is False
        assert pp.rows_cross_the_board_price([{"K": 90.0}], 100.0, 100.5) is False

    def test_any_one_row_is_enough(self):
        rows = [{"K": 90.0}, {"K": 120.0}, {"K": 100.2}]
        assert pp.rows_cross_the_board_price(rows, 100.0, 100.5) is True

    def test_null_safe(self):
        assert pp.rows_cross_the_board_price(None, 100.0, 100.5) is False
        assert pp.rows_cross_the_board_price([], 100.0, 100.5) is False
        assert pp.rows_cross_the_board_price([{"K": None}], 100.0, 100.5) is False
        assert pp.rows_cross_the_board_price([{"K": 100.2}], None, 100.5) is False
        assert pp.rows_cross_the_board_price([{"K": 100.2}], 100.0, None) is False

    def test_identical_prices_never_flip(self):
        """5 of the reviewer's 104 apparent flips are this shape: the two prices agree
        exactly and dist_pct merely rounds to 0.0. There is nothing to disclose."""
        assert pp.rows_cross_the_board_price([{"K": 212.5}], 212.41, 212.41) is False

    def test_note_fires_below_the_threshold_when_forced(self):
        assert pp.spot_divergence_note(100.0, 100.5) is None          # 0.5%, no flip
        forced = pp.spot_divergence_note(100.0, 100.5, force=True)
        assert forced is not None
        assert "the other way round" in forced[0]
        assert "方向会相反" in forced[1]

    def test_distance_trigger_does_not_add_the_direction_sentence(self):
        """Above the threshold the note names distance; the direction clause is reserved
        for the case a reader would otherwise get backwards."""
        note = pp.spot_divergence_note(197.01, 192.32)   # 2.4%
        assert "the other way round" not in note[0]
        assert "2.4%" in note[0]


# ── 22. B2 third condition — union-not-intersection roots ────────────────────

class TestPerRootCoverageDrivesTheFallback:
    """A root in the snapshot UNION but not the INTERSECTION used to fall to the
    store-wide fallback and claim "No per-strike chain snapshots are stored for this
    name" while a wall block derived from those very snapshots sat beside it. Measured on
    the real store: 25 of 375 roots on the 2026-07-02 -> 07-07 pair, and 346 of 356 on
    the 2026-06-18 -> 06-22 universe-expansion pair. The state now comes from PER-ROOT
    coverage."""

    def _pair(self):
        """AAA in both; ONLYP in the prior only; ONLYL in the latest only."""
        prior = _chain([
            _row("AAA", "a1", 110.0, True, 1000, 100.0),
            _row("AAA", "a2", 90.0, False, 1000, 100.0),
            _row("ONLYP", "p1", 55.0, True, 500, 50.0),
            _row("ONLYP", "p2", 45.0, False, 500, 50.0),
        ])
        latest = _chain([
            _row("AAA", "a1", 110.0, True, 1400, 100.0),
            _row("AAA", "a2", 90.0, False, 1000, 100.0),
            _row("ONLYL", "l1", 22.0, True, 700, 20.0),
            _row("ONLYL", "l2", 18.0, False, 700, 20.0),
        ])
        frames = {D_FRI: prior, D_MON: latest}
        return pp.load(chain_dates=lambda: sorted(frames), read_chain=frames.get,
                       window_sessions=2, use_cache=False)

    def test_only_latest_root_is_not_called_absent(self):
        st = self._pair()
        c = st.clusters("ONLYL")
        assert "No per-strike chain snapshots are stored" not in c["note_en"], c["note_en"]
        assert "Only one stored chain snapshot covers this name" in c["note_en"]
        assert "目前只有一次" in c["note_zh"]
        # and the wall block derived from that snapshot really does exist
        assert st.wall_persistence("ONLYL") is not None

    def test_only_prior_root_is_not_called_absent(self):
        st = self._pair()
        c = st.clusters("ONLYP")
        assert "No per-strike chain snapshots are stored" not in c["note_en"]
        assert "Only one stored chain snapshot covers this name" in c["note_en"]

    def test_coverage_counts_are_exposed(self):
        st = self._pair()
        assert st.coverage("AAA") == (2, 2)
        assert st.coverage("ONLYL") == (1, 1)
        assert st.coverage("ONLYP") == (1, 1)
        assert st.coverage("NOPE") == (0, 0)
        assert st.meta["roots_outside_pair"] == 2

    def test_truly_absent_root_still_says_absent(self):
        c = self._pair().clusters("NOPE")
        assert "No per-strike chain snapshots are stored" in c["note_en"]

    def test_root_in_older_snapshots_but_not_the_pair(self):
        """pair=0 but window>=1: 'only one snapshot covers this name' would be false, so
        the copy names the actual situation instead."""
        old = _chain([_row("GONE", "g1", 55.0, True, 500, 50.0),
                      _row("GONE", "g2", 45.0, False, 500, 50.0),
                      _row("AAA", "a1", 110.0, True, 900, 100.0),
                      _row("AAA", "a2", 90.0, False, 900, 100.0)])
        pair_a = _chain([_row("AAA", "a1", 110.0, True, 900, 100.0),
                         _row("AAA", "a2", 90.0, False, 900, 100.0)])
        pair_b = _chain([_row("AAA", "a1", 110.0, True, 1200, 100.0),
                         _row("AAA", "a2", 90.0, False, 900, 100.0)])
        frames = {dt.date(2026, 7, 22): old, D_THU: pair_a, D_FRI: pair_b}
        st = pp.load(chain_dates=lambda: sorted(frames), read_chain=frames.get,
                     window_sessions=3, use_cache=False)
        assert st.coverage("GONE") == (0, 1)
        c = st.clusters("GONE")
        assert "Neither of the two most recent stored chain snapshots lists this name" \
            in c["note_en"]
        assert "No per-strike chain snapshots are stored" not in c["note_en"]

    def test_one_of_pair_when_older_snapshots_also_list_it(self):
        """pair=1 and window>1: 'only one snapshot covers this name' is false."""
        early = _chain([_row("FADE", "f1", 55.0, True, 500, 50.0),
                        _row("FADE", "f2", 45.0, False, 500, 50.0)])
        mid = _chain([_row("FADE", "f1", 55.0, True, 600, 50.0),
                      _row("FADE", "f2", 45.0, False, 500, 50.0)])
        late = _chain([_row("AAA", "a1", 110.0, True, 900, 100.0),
                       _row("AAA", "a2", 90.0, False, 900, 100.0)])
        frames = {dt.date(2026, 7, 22): early, D_THU: mid, D_FRI: late}
        st = pp.load(chain_dates=lambda: sorted(frames), read_chain=frames.get,
                     window_sessions=3, use_cache=False)
        assert st.coverage("FADE") == (1, 2)
        c = st.clusters("FADE")
        assert "Only one of the two most recent stored chain snapshots lists this name" \
            in c["note_en"]

    def test_real_universe_expansion_pair(self):
        """2026-06-18 -> 06-22 in the committed store: 10 roots on the prior side, 356 on
        the latest. 346 union-not-intersection roots must NOT be told nothing is stored."""
        a, b = dt.date(2026, 6, 18), dt.date(2026, 6, 22)
        if not all((pp._chains_dir() / f"{d.isoformat()}.parquet").exists() for d in (a, b)):
            pytest.skip("that vintage pair is not in this checkout")
        st = pp.load(chain_dates=lambda: [a, b], read_chain=pp.default_read_chain,
                     window_sessions=2, use_cache=False)
        outside = [r for r, (pair, _w) in st._coverage.items() if pair < 2]
        assert len(outside) > 300, len(outside)
        liars = [r for r in outside
                 if "No per-strike chain snapshots are stored"
                 in st.clusters(r)["note_en"]]
        assert not liars, f"{len(liars)} roots falsely told nothing is stored: {liars[:5]}"
        # spot-check one that only the latest snapshot lists
        sample = outside[0]
        assert st.wall_persistence(sample) is not None
        assert "Only one stored chain snapshot" in st.clusters(sample)["note_en"]


def test_unavailable_copy_matches_the_gex_state_duplicate():
    """gex_state keeps a byte-identical pair for the one path that cannot reach this
    module (its own import failing). Pin them equal so the two cannot drift."""
    from engine import gex_state
    assert gex_state._OI_DELTA_UNAVAILABLE_EN == pp.OI_DELTA_UNAVAILABLE_EN
    assert gex_state._OI_DELTA_UNAVAILABLE_ZH == pp.OI_DELTA_UNAVAILABLE_ZH
