"""Start-invariance battery for the pick-lab session-anchored oscillator grids.

Charter: the pick_lab leg of the session-anchor family (era ``pl-abs-session-2026-08-06``),
sibling of ``research/SIGNAL_QUALITY_SESSION_ANCHOR_ADJUDICATION_BY_FABLE.md`` (chip 3 of
its sibling triage). The defect being pinned: ``compute_grids`` built its d2 grid with
``panel.resample("2B")``, whose bin edges anchor to the PANEL's first date — so every
``d2_*`` scalar depended on how much leading history the caller's loader handed in
(measured 2026-08-06: 60/60 deep US names changed d2 scalars on a 1-row leading drop),
and the never-backfilled PIT snapshot froze that loader-phase noise into the permanent
research record. Same class, same repair as the cascade/§7 anchors: bucket by
``session_anchor.session_positions // n`` — a function of (reference calendar, date)
only, never of the series.

The battery mirrors ``tests/test_session_anchor_invariance.py``'s fixture doctrine:
real NYSE sessions (real phases, real holidays), deep fixtures assert tight-tolerance
invariance (EWM memory has decayed), the holiday span covers the short weeks whose
bins the old calendar-anchored resample mis-split.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from engine import session_anchor as sa
from engine.pick_lab.signals_1d import compute_grids
from lib import nyse_calendar

# Real NYSE sessions — real phases, real holidays (the sibling battery's doctrine).
_SESSIONS = pd.DatetimeIndex(pd.to_datetime(
    nyse_calendar.sessions_between(date(2005, 1, 1), date(2026, 8, 4))))


def _sess(n: int) -> pd.DatetimeIndex:
    """The last ``n`` real NYSE sessions ending 2026-08-04."""
    return _SESSIONS[len(_SESSIONS) - n:]


def _walk(idx: pd.DatetimeIndex, lg: np.ndarray, seed: int, vol: float) -> pd.Series:
    rng = np.random.default_rng(seed)
    return pd.Series(100 * np.exp(lg + np.cumsum(rng.normal(0.0, vol, len(idx)))), index=idx)


def _uptrend(n: int = 2000, seed: int = 11) -> pd.Series:
    """Smooth uptrend + sinusoid — crosses fire regularly."""
    idx = _sess(n); i = np.arange(n)
    return _walk(idx, 0.5 * i / n + 0.12 * np.sin(2 * np.pi * i / 45), seed, 0.006)


def _down_then_v(n: int = 2000, seed: int = 12) -> pd.Series:
    """Long downtrend then a V — a fresh cross near the END, the repaint-prone shape."""
    idx = _sess(n); i = np.arange(n)
    lg = np.where(i < n * 0.8, -0.8 * i / n, -0.64 + 2.2 * (i - n * 0.8) / n)
    return _walk(idx, lg, seed, 0.007)


def _holiday_span(seed: int = 13) -> pd.Series:
    """A span that certainly contains Thanksgiving, Christmas and July-4 weeks — the
    short weeks whose bins the old calendar-anchored ``resample("2B")`` mis-split."""
    idx = _SESSIONS[(_SESSIONS >= pd.Timestamp("2015-01-01"))
                    & (_SESSIONS <= pd.Timestamp("2025-01-31"))]
    i = np.arange(len(idx))
    return _walk(idx, 0.3 * i / len(idx) + 0.15 * np.sin(2 * np.pi * i / 38), seed, 0.008)


def _halted(n: int = 2000, seed: int = 14) -> pd.Series:
    """Three sessions missing mid-stream — a halt. The dates are absent from the SERIES
    but present in the REFERENCE, so buckets must simply skip them."""
    s = _uptrend(n, seed)
    return s.drop(s.index[[400, 401, 402]])


def _late_listing(n_total: int = 2000, n_live: int = 420, seed: int = 15) -> pd.Series:
    """A name that lists mid-panel: leading NaNs on the shared panel index."""
    idx = _sess(n_total)
    live = _walk(idx[-n_live:], 0.4 * np.arange(n_live) / n_live, seed, 0.007)
    return live.reindex(idx)


def _panel(cols: dict[str, pd.Series]) -> pd.DataFrame:
    return pd.DataFrame(cols)


#: Deep fixtures: >=2000 daily bars → >=1000 2-session buckets. Bucket VALUES are
#: exactly window-independent under the absolute anchor; the residual float drift under
#: a leading drop is EWM initial-condition memory only, dominated by the BASE_LEN=60
#: EMA: ~(59/60)^(buckets) ≈ 6e-8 relative at 1000 buckets. The rel=1e-6 tolerance
#: therefore passes with an order of margin while sitting far below the old
#: construction's re-paired-bucket moves. (The sibling cascade battery draws the same
#: line: discrete signal fields exact, raw EWM digits never asserted bit-wise on
#: truncation — see tests/test_session_anchor_invariance.py's GLYPH_FIELDS note.)
DEEP_FIXTURES = {
    "uptrend_sinusoid": _uptrend(),
    "downtrend_then_V": _down_then_v(),
    "holiday_span": _holiday_span(),
    "halted_3_sessions": _halted(),
}

_D2_FLOAT_FIELDS = ("d2_macd", "d2_sig", "d2_k", "d2_d")
_D2_EXACT_FIELDS = ("d2_macd_xup_bars", "d2_kd_xup_bars", "d2_from_os", "d2_ob")
_D1_FIELDS = ("d1_macd", "d1_sig", "d1_k", "d1_d",
              "d1_macd_xup_bars", "d1_kd_xup_bars", "d1_from_os", "d1_ob")


def _is_null(v) -> bool:
    return v is None or (isinstance(v, float) and np.isnan(v))


def _assert_fields_equal(row_a: pd.Series, row_b: pd.Series, float_fields, exact_fields,
                         label: str, rel: float = 1e-6, abs_: float = 1e-8) -> None:
    for f in exact_fields:
        a, b = row_a.get(f), row_b.get(f)
        if _is_null(a) and _is_null(b):
            continue
        assert a == b, f"{label}: {f} flipped {a!r} -> {b!r}"
    for f in float_fields:
        a, b = row_a.get(f), row_b.get(f)
        if _is_null(a) and _is_null(b):
            continue
        assert a is not None and b is not None, f"{label}: {f} null-flipped {a!r} -> {b!r}"
        assert a == pytest.approx(b, rel=rel, abs=abs_), f"{label}: {f} moved {a} -> {b}"


# --------------------------------------------------------------------------- #
# 1. START-INVARIANCE — the charter's core requirement
# --------------------------------------------------------------------------- #

class TestD2StartInvariance:
    """``compute_grids(panel).d2_* == compute_grids(panel.iloc[k:]).d2_*``, k = 1..6.

    Under the old ``resample("2B")`` every leading-row drop re-phased every bin
    (60/60 measured names moved); under the absolute session anchor the bucket of a
    date is a function of the date alone, so the scalars cannot move. d1 fields ride
    the same assertion as the control group — they never bucketed, so they were
    invariant before and must stay invariant.
    """

    @pytest.mark.parametrize("name", sorted(DEEP_FIXTURES))
    @pytest.mark.parametrize("k", [1, 2, 3, 4, 5, 6])
    def test_d2_scalars_survive_a_leading_history_drop(self, name, k):
        base = _panel({"T": DEEP_FIXTURES[name]})
        full = compute_grids(base)
        cut = compute_grids(base.iloc[k:])
        _assert_fields_equal(full.loc["T"], cut.loc["T"],
                             _D2_FLOAT_FIELDS, _D2_EXACT_FIELDS, f"{name} k={k}")

    @pytest.mark.parametrize("name", sorted(DEEP_FIXTURES))
    @pytest.mark.parametrize("k", [1, 2])
    def test_d1_control_group_also_survives(self, name, k):
        base = _panel({"T": DEEP_FIXTURES[name]})
        full = compute_grids(base)
        cut = compute_grids(base.iloc[k:])
        _assert_fields_equal(full.loc["T"], cut.loc["T"],
                             ("d1_macd", "d1_sig", "d1_k", "d1_d"),
                             ("d1_macd_xup_bars", "d1_kd_xup_bars", "d1_from_os", "d1_ob"),
                             f"{name} k={k} (d1 control)")

    def test_a_multi_name_panel_with_a_late_listing_is_invariant_per_name(self):
        """The panel-level positions computation must not let one name's window
        (leading NaNs from a late listing) phase any other name's buckets."""
        base = _panel({
            "DEEP": _uptrend(seed=21),
            "VSHAPE": _down_then_v(seed=22),
            "LATE": _late_listing(seed=23),
        })
        full = compute_grids(base)
        cut = compute_grids(base.iloc[3:])
        for t in ("DEEP", "VSHAPE", "LATE"):
            _assert_fields_equal(full.loc[t], cut.loc[t],
                                 _D2_FLOAT_FIELDS, _D2_EXACT_FIELDS, f"panel {t} k=3")

    def test_two_windows_of_the_same_history_agree_on_the_signal_story(self):
        """The two-loaders disease directly: a deep store and a ~3y rolling-cache
        window of the SAME name must read the same d2 SIGNAL story (the old
        construction disagreed night-for-night across data/stocks vs the breadth
        caches). Discrete fields must match exactly; of the floats only the
        StochRSI pair is asserted (its memory is the 14-bucket rolling window, fully
        decayed at this depth) — macd/sig carry the BASE_LEN=60 EMA's initial
        condition, which a 350-bucket window legitimately re-seeds. That residue is
        a property of truncation itself, not of bucket phase; the old defect moved
        the DISCRETE story, which is what may never move again."""
        s = _uptrend(seed=31)
        deep = compute_grids(_panel({"X": s}))
        shallow = compute_grids(_panel({"X": s.iloc[-700:]}))
        _assert_fields_equal(deep.loc["X"], shallow.loc["X"],
                             ("d2_k", "d2_d"), _D2_EXACT_FIELDS,
                             "deep-vs-700bar window", rel=1e-5)


# --------------------------------------------------------------------------- #
# 2. The bucketing helper itself — exact geometry, no tolerance
# --------------------------------------------------------------------------- #

class TestSessionBucketLast:
    def test_shared_buckets_are_byte_identical_under_truncation(self):
        from engine.pick_lab.signals_1d import session_bucket_last
        s = _uptrend(600, seed=41)
        p = _panel({"A": s, "B": _down_then_v(600, seed=42)})
        full = session_bucket_last(p, 2, market="US")
        cut = session_bucket_last(p.iloc[5:], 2, market="US")
        shared = full.index.intersection(cut.index)
        # Everything but (at most) the leading buckets of the cut is shared…
        assert len(shared) >= len(cut) - 1
        # …and shared buckets carry byte-identical values (.last() of a bucket's tail
        # equals .last() of the bucket whenever the bucket's final in-window session
        # survives the cut — the property the whole repair rests on).
        pd.testing.assert_frame_equal(full.loc[shared], cut.loc[shared])

    def test_bucket_ids_are_absolute_session_ordinals(self):
        from engine.pick_lab.signals_1d import session_bucket_last
        idx = _sess(40)
        p = pd.DataFrame({"A": np.arange(40.0)}, index=idx)
        out = session_bucket_last(p, 2, market="US")
        expect = sa.session_positions(idx, "US") // 2
        assert list(out.index) == sorted(set(expect.tolist()))

    @pytest.mark.parametrize("n", [2, 3])
    def test_a_halt_neither_shifts_nor_mints_buckets(self, n):
        """Sessions absent from the SERIES but present in the reference must not move
        any later bucket — the reference owns the grid, the series only fills it."""
        from engine.pick_lab.signals_1d import session_bucket_last
        s_full = _uptrend(600, seed=43)
        s_halt = s_full.drop(s_full.index[[300, 301, 302]])
        full = session_bucket_last(_panel({"A": s_full}), n, market="US")
        halt = session_bucket_last(_panel({"A": s_halt}), n, market="US")
        halted_buckets = set((sa.session_positions(s_full.index[[300, 301, 302]], "US") // n).tolist())
        shared = full.index.difference(pd.Index(sorted(halted_buckets)))
        pd.testing.assert_frame_equal(full.loc[shared], halt.loc[shared.intersection(halt.index)])

    def test_the_market_argument_reaches_the_anchor(self, monkeypatch):
        """A synthetic CN reference (every OTHER real session) must regroup the same
        dates differently than the US reference — proving the kwarg is threaded, not
        cosmetic."""
        from engine.pick_lab.signals_1d import session_bucket_last
        idx = _sess(120)
        synthetic_cn = _SESSIONS[::2]
        monkeypatch.setitem(sa._REF_CACHE, "CN", synthetic_cn)
        p = pd.DataFrame({"A": np.arange(120.0)}, index=idx)
        us = session_bucket_last(p, 2, market="US")
        cn = session_bucket_last(p, 2, market="CN")
        us_expect = sa.session_positions(idx, "US") // 2
        cn_expect = sa.session_positions(idx, "CN") // 2
        assert list(us.index) == sorted(set(us_expect.tolist()))
        assert list(cn.index) == sorted(set(cn_expect.tolist()))
        assert list(us.index) != list(cn.index)

    def test_a_missing_reference_store_raises_through_compute_grids(self, monkeypatch, tmp_path):
        """No fallback chain: a missing HK reference store must surface as the
        FileNotFoundError the callers' additive-except blocks log — never a silent
        re-bucket on the US calendar."""
        monkeypatch.delitem(sa._REF_CACHE, "HK", raising=False)
        monkeypatch.setattr(sa, "_data_root", lambda: tmp_path)
        p = _panel({"X": _uptrend(300, seed=44)})
        with pytest.raises(FileNotFoundError, match="HK session reference"):
            compute_grids(p, market="HK")


# --------------------------------------------------------------------------- #
# 3. Compact session_anchor pins — so the module lands tested regardless of
#    which sibling PR merges first (byte-identical file across the family).
# --------------------------------------------------------------------------- #

class TestAnchorGeometry:
    def test_positions_are_exact_ordinals_in_the_reference(self):
        R = sa.reference_sessions("US")
        take = R[500:520]
        assert (sa.session_positions(take, "US") == np.arange(500, 520)).all()

    def test_an_absent_date_takes_the_next_sessions_position(self):
        # 2024-07-04 (Thursday) is an NYSE holiday: absent from the reference, it must
        # bucket with the session that FOLLOWS it (2024-07-05), not phase anything.
        R = sa.reference_sessions("US")
        holiday = pd.DatetimeIndex([pd.Timestamp("2024-07-04")])
        after = pd.DatetimeIndex([pd.Timestamp("2024-07-05")])
        assert sa.session_positions(holiday, "US")[0] == sa.session_positions(after, "US")[0]
        assert pd.Timestamp("2024-07-04") not in R

    def test_dates_beyond_the_reference_end_extend_consecutively(self):
        R = sa.reference_sessions("US")
        beyond = pd.DatetimeIndex([R[-1] + pd.Timedelta(days=3), R[-1] + pd.Timedelta(days=5)])
        pos = sa.session_positions(beyond, "US")
        assert pos.tolist() == [len(R), len(R) + 1]

    @pytest.mark.parametrize("ticker,market", [
        ("0700.HK", "HK"), ("600519.SS", "CN"), ("000001.SZ", "CN"),
        ("SHOP.TO", "CA"), ("AAPL", "US"), (None, "US"),
    ])
    def test_market_for_ticker(self, ticker, market):
        assert sa.market_for_ticker(ticker) == market

    def test_an_unknown_market_string_resolves_to_the_us_reference(self):
        idx = _sess(10)
        assert (sa.session_positions(idx, "XX") == sa.session_positions(idx, "US")).all()


# --------------------------------------------------------------------------- #
# 4. The era stamp — new rows fenced, old rows never edited
# --------------------------------------------------------------------------- #

class TestEraStamp:
    def test_every_compute_grids_row_carries_the_era(self):
        from engine.pick_lab.signals_1d import ANCHOR_ERA
        p = _panel({"DEEP": _uptrend(seed=51), "SHORT": _uptrend(60, seed=52)})
        out = compute_grids(p)
        assert set(out["pl_anchor_era"]) == {ANCHOR_ERA}
        # The stamp describes the GEOMETRY the row was computed under — a too-short
        # name's null scalars are null UNDER THE NEW GEOMETRY, so it is stamped too.
        assert out.at["SHORT", "d2_macd"] is None or pd.isna(out.at["SHORT", "d2_macd"])
        assert out.at["SHORT", "pl_anchor_era"] == ANCHOR_ERA

    def test_the_era_value_is_the_charters_dated_stamp(self):
        from engine.pick_lab.signals_1d import ANCHOR_ERA
        assert ANCHOR_ERA == "pl-abs-session-2026-08-06"

    def test_all_three_snapshot_schemas_declare_the_column(self):
        from engine.pick_lab.snapshot import SNAPSHOT_COLUMNS
        from engine.pick_lab.cn_snapshot import CN_SNAPSHOT_COLUMNS
        from engine.pick_lab.hk_snapshot import HK_SNAPSHOT_COLUMNS
        for cols in (SNAPSHOT_COLUMNS, CN_SNAPSHOT_COLUMNS, HK_SNAPSHOT_COLUMNS):
            assert "pl_anchor_era" in cols

    def test_us_core_rows_carry_the_stamp_from_the_osc_dict(self):
        from engine.pick_lab.snapshot import build_core_rows
        from engine.pick_lab.signals_1d import ANCHOR_ERA
        rows = build_core_rows(
            profile_dicts=[{"ticker": "AAA"}, {"ticker": "BBB"}],
            oscillator_dicts={"AAA": {"d2_macd": 1.0, "pl_anchor_era": ANCHOR_ERA}},
            asof="2026-08-06",
        )
        by = {r["ticker"]: r for r in rows}
        assert by["AAA"]["pl_anchor_era"] == ANCHOR_ERA
        assert by["BBB"]["pl_anchor_era"] is None  # osc never computed → unstamped, null-honest

    def test_cn_and_hk_core_rows_thread_the_stamp(self):
        from engine.pick_lab.cn_snapshot import build_cn_core_rows
        from engine.pick_lab.hk_snapshot import build_hk_core_rows
        from engine.pick_lab.signals_1d import ANCHOR_ERA
        cn = build_cn_core_rows(
            tickers=["600519.SS"], asof="2026-08-06",
            close_by={}, turnover_by={}, sector_by={}, name_by={}, name_zh_by={},
            board_by={}, is_st_by={},
            osc_d12_by={"600519.SS": {"d2_macd": 0.5, "pl_anchor_era": ANCHOR_ERA}},
        )
        assert cn[0]["pl_anchor_era"] == ANCHOR_ERA
        hk = build_hk_core_rows(
            tickers=["0700.HK"], asof="2026-08-06",
            close_by={}, adv63_hkd_by={}, name_by={}, name_zh_by={}, sector_by={},
            osc_d123_by={"0700.HK": {"d2_macd": 0.5, "d3_macd_xup_bars": None,
                                     "pl_anchor_era": ANCHOR_ERA}},
        )
        assert hk[0]["pl_anchor_era"] == ANCHOR_ERA

    def test_keep_first_snapshot_fences_cohorts_without_retro_editing(self, tmp_path):
        """Pre-era rows stay exactly as logged (era null); the era column fences the
        cohorts. keep-first means a re-write of the same (asof, ticker) is a no-op —
        the no-retro-edit law in executable form."""
        from engine.pick_lab.snapshot import write_snapshot
        from engine.pick_lab.signals_1d import ANCHOR_ERA
        base = str(tmp_path / "snaps")
        pre = pd.DataFrame([{"ticker": "AAA", "d2_macd": 9.9}]).set_index("ticker")
        assert write_snapshot(pre, "2026-08-04", base_dir=base) == 1
        post_same = pd.DataFrame([
            {"ticker": "AAA", "d2_macd": 1.1, "pl_anchor_era": ANCHOR_ERA},
        ]).set_index("ticker")
        # Same (asof, ticker) again → keep-first refuses the re-write.
        assert write_snapshot(post_same, "2026-08-04", base_dir=base) == 0
        assert write_snapshot(post_same, "2026-08-05", base_dir=base) == 1
        got = pd.read_parquet(f"{base}/2026-08.parquet")
        d04 = got[got["asof"] == "2026-08-04"]
        d05 = got[got["asof"] == "2026-08-05"]
        assert float(d04["d2_macd"].iloc[0]) == 9.9
        assert _is_null(d04["pl_anchor_era"].iloc[0])       # pre-era row: never edited
        assert d05["pl_anchor_era"].iloc[0] == ANCHOR_ERA   # post-era row: fenced
