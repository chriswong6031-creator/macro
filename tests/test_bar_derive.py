"""Intraday -> multi-timeframe bar derivation hooks (engine.bar_derive).

Pins the contract that matters: the derived DAILY CLOSE Series is a drop-in for the
nightly store's ``['close'].dropna()`` (so the confluence engine consumes it unchanged),
the supplementary 2D/3D OHLCV frames aggregate correctly and stay OUT of the signal path,
and the integration switch falls back cleanly to the adjusted store.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from engine import bar_derive as bd
from lib import config, nyse_calendar


def _synthetic_intraday():
    """Hourly UTC bars across 6 US business days, RTH window (13:00–20:00 UTC = NY RTH
    in June/EDT), close rising through each day so the 20:00 bar is the session close."""
    days = pd.bdate_range("2026-06-15", periods=6, tz=None)
    rows, idx = [], []
    for di, d in enumerate(days):
        for h in range(13, 21):                      # 13:00 .. 20:00 UTC
            ts = pd.Timestamp(d.date(), tz="UTC") + pd.Timedelta(hours=h)
            c = 100.0 + di * 10 + h                   # last hour (20) is the day's high/close
            rows.append({"open": c - 0.5, "high": c + 0.5, "low": c - 1.0,
                         "close": c, "volume": 1000 + h})
            idx.append(ts)
    df = pd.DataFrame(rows, index=pd.DatetimeIndex(idx, name="ts"))
    return df, days


def test_derive_daily_close_matches_store_shape():
    intr, days = _synthetic_intraday()
    s = bd.derive_daily_close(intr)
    # shape contract: 'Date' index, tz-naive, float64, sorted, no NaN, one row per session
    assert isinstance(s, pd.Series)
    assert s.index.name == "Date"
    assert s.index.tz is None
    assert str(s.dtype) == "float64"
    assert s.index.is_monotonic_increasing
    assert not s.isna().any()
    assert len(s) == len(days)
    # value = the 20:00 UTC (session-close) bar for the first day: 100 + 0 + 20
    assert s.iloc[0] == 120.0
    # index normalised to midnight session date
    assert s.index[0] == pd.Timestamp("2026-06-15")


def test_derive_daily_close_is_consumable_by_signal_frame():
    """Exercise the FULL pipeline: intraday bars -> derive_daily_close -> signal_frame.
    (Earlier this fed a hand-built Series and never touched the function under test.)"""
    from engine.signal_quality import signal_frame
    # ~360 business days of hourly bars -> enough 3D history past signal_frame's warmup guard
    days = pd.bdate_range("2024-01-01", periods=360)
    rows, idx = [], []
    for di, d in enumerate(days):
        for h in range(13, 21):
            idx.append(pd.Timestamp(d.date(), tz="UTC") + pd.Timedelta(hours=h))
            c = 100.0 + di + h * 0.01
            rows.append({"open": c, "high": c + 0.2, "low": c - 0.2, "close": c, "volume": 1000})
    intr = pd.DataFrame(rows, index=pd.DatetimeIndex(idx, name="ts"))
    close = bd.derive_daily_close(intr)                  # the function under test feeds the engine
    assert close.index.name == "Date" and close.index.tz is None
    assert not close.isna().any() and str(close.dtype) == "float64"
    sf = signal_frame(close)
    assert sf is not None and len(sf) > 0


# ── display-grid anchor (era display-grid-abs-session-2026-08-06, DG-R1..R8) ──
#
# Fixtures below sit on REAL NYSE sessions, never ``bdate_range``. The retired 3B test
# built its fixture from ``pd.bdate_range("2026-06-15", ...)``, which contains 2026-06-19
# — Juneteenth, a business day the exchange is CLOSED for. A grid that buckets business
# days and a grid that buckets sessions disagree exactly there, so a bdate fixture cannot
# see the mis-split this era removed.

_SESSIONS = pd.DatetimeIndex(pd.to_datetime(
    nyse_calendar.sessions_between(date(2023, 1, 3), date(2026, 8, 4))))


def _session_ohlc(n: int = 240, seed: int = 11) -> pd.DataFrame:
    """A daily OHLCV frame on the last ``n`` real NYSE sessions."""
    assert n <= len(_SESSIONS), f"fixture wants {n} sessions, calendar has {len(_SESSIONS)}"
    idx = _SESSIONS[len(_SESSIONS) - n:]
    rng = np.random.default_rng(seed)
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, n))), index=idx)
    df = pd.DataFrame({"close": close, "high": close * 1.01, "low": close * 0.99,
                       "volume": np.arange(1, n + 1, dtype="float64")}, index=idx)
    df.index.name = "Date"
    return df


def test_3d_close_equals_signal_frames_own_grid():
    """DG-R2: the docstring's equality claim, pinned against ``_tf_grid`` ITSELF.

    This claim shipped as prose and went FALSE for a whole era when signal_quality moved
    to the absolute anchor and bar_derive did not. Prose that points at another module's
    behaviour is an untested contract, so it is asserted here — labels included, because
    both sides label a bucket by its OPEN date (a real traded session), not by a synthetic
    bin edge that could land on a holiday.
    """
    from engine.signal_quality import _tf_grid
    df = _session_ohlc()
    for n, fn in ((3, bd.derive_3d_ohlcv), (2, bd.derive_2d_ohlcv)):
        got = fn(df)
        ref = _tf_grid(df["close"], n)
        assert list(got.index) == list(ref.close.index), f"n={n} labels diverged"
        assert np.array_equal(got["close"].to_numpy(), ref.close.to_numpy()), \
            f"n={n} closes diverged"


def test_3d_buckets_match_a_first_principles_derivation():
    """The pin above compares two implementations; this one derives the answer
    INDEPENDENTLY from the reference calendar, so neither can drift into the other."""
    df = _session_ohlc(n=60)
    out = bd.derive_3d_ohlcv(df)
    ref = pd.DatetimeIndex(pd.to_datetime(
        nyse_calendar.sessions_between(date(1950, 1, 3), date(2026, 8, 4))))
    want: dict[int, list] = {}
    for ts in df.index:                       # bucket = (ordinal in the session calendar)//3
        want.setdefault(int(ref.searchsorted(ts, side="left")) // 3, []).append(ts)
    assert len(out) == len(want)
    for label, (_, members) in zip(out.index, sorted(want.items())):
        assert label == members[0]                        # OPEN-date label (DG-R2)
    for (_, members), (_, row) in zip(sorted(want.items()), out.iterrows()):
        assert row["close"] == df.loc[members[-1], "close"]      # last close in the bucket
        assert row["high"] == df.loc[members, "high"].max()
        assert row["low"] == df.loc[members, "low"].min()
        assert row["volume"] == df.loc[members, "volume"].sum()


def test_a_holiday_week_buckets_by_sessions_not_business_days():
    """The mis-split, made visible. Juneteenth 2026-06-19 is a business day the exchange is
    CLOSED for, so a business-day bin spends one of its three slots on a day that never
    trades: ``3B`` cuts ``[06-18, 06-19, 06-22]`` — a candle built from TWO sessions
    wearing a 3-session label. The session grid cuts ``[06-17, 06-18, 06-22]``: three real
    sessions, every time. This is the defect ``canon.resample_sessions`` was built against
    and the reason a calendar anchor was rejected in favour of a session anchor."""
    df = _session_ohlc(n=400)
    week = df.loc["2026-06-15":"2026-06-26"].index
    assert pd.Timestamp("2026-06-19") not in week                # closed: it never trades

    ids = bd.bucket_ids(df.index)
    members: dict[int, list] = {}
    for d, b in zip(df.index, ids):
        members.setdefault(int(b), []).append(d)
    spanning = [m for m in members.values()
                if m[0] <= pd.Timestamp("2026-06-22") <= m[-1]]
    assert spanning and len(spanning[0]) == 3, "the holiday must not shrink a bucket"
    assert pd.Timestamp("2026-06-19") not in spanning[0]

    # the business-day grid, over the same sessions, DOES lose one to the holiday
    wk = pd.Series(range(len(week)), index=week)
    bd_bins = wk.resample("3B").apply(list)
    holed = [v for k, v in bd_bins.items() if k == pd.Timestamp("2026-06-18")]
    assert holed and len(holed[0]) == 2, "3B was expected to mis-split the holiday week"


@pytest.mark.parametrize("k", [1, 2, 3, 4, 5, 6])
def test_dropping_leading_bars_cannot_move_a_bucket(k):
    """DG-R1, the whole point: bucket membership is a function of (calendar, date) — never
    of how much leading history the caller handed in. OHLCV aggregation carries no EWM
    memory, so this is BIT-EXACT, not approximate (unlike the §7 stream's EWM indicators).
    Only the truncation-straddled first bucket is exempt: it is genuinely a partial bar."""
    df = _session_ohlc()
    full, sub = bd.derive_3d_ohlcv(df), bd.derive_3d_ohlcv(df.iloc[k:])
    common = full.index.intersection(sub.index)
    common = common[common > sub.index[0]]
    assert len(common) > 50, "fixture too short to prove anything"
    assert np.array_equal(full.loc[common].to_numpy(), sub.loc[common].to_numpy())
    f2, s2 = bd.derive_2d_ohlcv(df), bd.derive_2d_ohlcv(df.iloc[k:])
    c2 = f2.index.intersection(s2.index)
    c2 = c2[c2 > s2.index[0]]
    assert np.array_equal(f2.loc[c2].to_numpy(), s2.loc[c2].to_numpy())


def test_resample_ohlcv_refuses_multi_business_day_rules():
    """DG-R8: the footgun is closed, not merely bypassed — a caller reaching for the old
    start-anchored bins is told where the anchored derivers are."""
    df = _session_ohlc(n=30)
    for rule in ("2B", "3B", "5B", " 3b "):
        with pytest.raises(ValueError, match="derive_2d_ohlcv|derive_3d_ohlcv"):
            bd.resample_ohlcv(df, rule)
    # unaffected: single-day and calendar-absolute rules
    assert not bd.resample_ohlcv(df, "1D").empty
    assert not bd.resample_ohlcv(df, "W-FRI").empty


def test_anchored_derivers_tolerate_a_missing_open_column():
    """The nightly store has no 'open' column — bucketing must not crash on its absence."""
    df = _session_ohlc(n=9)
    out = bd.derive_3d_ohlcv(df)
    assert "open" not in out.columns
    assert out["close"].iloc[0] == df["close"].iloc[2]     # last close of the first bucket


def test_market_kwarg_uses_that_markets_calendar():
    """DG-R1: CN buckets are counted against the CN reference index, not the NYSE."""
    ref = config.data_dir() / "china" / "000001.SS.parquet"
    if not ref.exists():
        pytest.skip("CN session reference absent on this runner")
    cn = pd.read_parquet(ref).index
    cn = pd.DatetimeIndex(cn[-120:]).tz_localize(None).normalize()
    df = pd.DataFrame({"close": np.linspace(10, 20, len(cn)), "high": np.linspace(10, 20, len(cn)),
                       "low": np.linspace(9, 19, len(cn)), "volume": 1.0}, index=cn)
    out = bd.derive_3d_ohlcv(df, market="CN")
    assert len(out) == pytest.approx(len(cn) / 3, abs=2)
    assert list(out.index) == [d for d in out.index if d in set(cn)]   # labels are real sessions


# ── the payload anchor block the emitters ship (DG-R3/R4/R6) ──────────────────

def test_chart_anchor_boundaries_open_every_bucket():
    df = _session_ohlc(n=90)
    a = bd.chart_anchor(df.index)
    assert a["era"] == bd.ANCHOR_ERA
    assert a["b3"][0] == 0
    ids = bd.bucket_ids(df.index)
    assert a["b3"] == [0] + [i for i in range(1, len(ids)) if ids[i] != ids[i - 1]]
    # the boundaries reproduce the deriver's own grouping, row for row
    assert len(a["b3"]) == len(bd.derive_3d_ohlcv(df))


def test_chart_anchor_survives_a_halt_that_floor_i_over_3_cannot():
    """Why boundaries and not a phase offset (DG-R3): drop a mid-window session and every
    later bucket shifts under row arithmetic, while the shipped grid stays correct."""
    df = _session_ohlc(n=60)
    gapped = df.drop(df.index[20:23])                    # a 3-session halt
    a = bd.chart_anchor(gapped.index)
    ids = bd.bucket_ids(gapped.index)
    for i in a["b3"]:
        assert i == 0 or ids[i] != ids[i - 1]
    naive = list(range(0, len(gapped), 3))               # what floor(i/3) would have used
    assert a["b3"] != naive, "the halt must make row arithmetic disagree with the calendar"


def test_trim_drops_at_most_two_rows_and_lands_on_a_bucket_open():
    """DG-R4: a shipped window opens a bucket, so the first candle is never a partial."""
    df = _session_ohlc(n=200)
    for cap in range(40, 60):                            # every phase the cap can land on
        win = df.index[len(df) - cap:]
        prev = df.index[len(df) - cap - 1]
        cut = bd.trim_rows_to_bucket_open(win, prev)
        assert 0 <= cut <= 2
        kept = win[cut:]
        ids = bd.bucket_ids(df.index[len(df) - cap - 1:])
        assert bd.bucket_ids(kept)[0] != ids[0], "window must not share a bucket with prev"
    assert bd.trim_rows_to_bucket_open(df.index, None) == 0      # nothing precedes row 0


def test_daily_close_for_prefers_intraday_then_falls_back(tmp_path):
    root = tmp_path / "data"
    (root / "intraday").mkdir(parents=True)
    stocks = root / "stocks"
    stocks.mkdir()

    # adjusted store for AAPL (the fallback)
    days = pd.bdate_range("2026-01-01", periods=10)
    pd.DataFrame({"close": [50.0] * 10, "high": [50.0] * 10, "low": [50.0] * 10,
                  "volume": [1] * 10}, index=pd.DatetimeIndex(days, name="Date")
                 ).to_parquet(stocks / "AAPL.parquet")

    # no intraday file -> falls back to the adjusted store even when prefer_intraday=True
    s = bd.daily_close_for("AAPL", prefer_intraday=True, root=root, stocks_dir=stocks)
    assert s is not None and s.iloc[-1] == 50.0

    # now add an intraday file -> the derived (raw) close is preferred
    intr, _ = _synthetic_intraday()
    intr.to_parquet(root / "intraday" / "AAPL.parquet")
    s2 = bd.daily_close_for("AAPL", prefer_intraday=True, root=root, stocks_dir=stocks)
    assert s2 is not None and s2.iloc[-1] != 50.0        # came from intraday, not the store

    # unknown ticker -> None (no source)
    assert bd.daily_close_for("ZZZZ", prefer_intraday=True, root=root, stocks_dir=stocks) is None


def test_intraday_meta_reads_sidecar(tmp_path):
    import json
    root = tmp_path / "data"
    (root / "intraday").mkdir(parents=True)
    (root / "intraday" / "_meta.json").write_text(json.dumps(
        {"delayed_min": 15, "realtime": False, "source": "polygon_standard"}))
    meta = bd.intraday_meta(root=root)
    assert meta["delayed_min"] == 15 and meta["realtime"] is False
    assert bd.intraday_meta(root=tmp_path / "nope") == {}


# ── #45b: TZ mis-bucketing guard ─────────────────────────────────────────────

def _asia_intraday():
    """Synthetic CN intraday: 09:30–15:00 CST (01:30–07:00 UTC) on 3 business days.
    The 14:57 UTC bar is the last CST bar of the session (14:57 UTC = 22:57 CST next
    day — actually we use 06:57 UTC = 14:57 CST, which is the close).
    Simpler: bars from 01:30–07:00 UTC each day map to the SAME calendar day in CST
    but to the PREVIOUS day in America/New_York (01:30 UTC is 20:30 EST previous day)."""
    # Use hours 01..07 UTC so every bar is unambiguously in SAME calendar day for CN
    # but cross-midnight for NY (01 UTC = 20:00 EST prior day).
    days = pd.bdate_range("2026-06-15", periods=3, tz=None)
    rows, idx = [], []
    for di, d in enumerate(days):
        for h in range(1, 8):   # 01:00..07:00 UTC = 09:00..15:00 CST
            ts = pd.Timestamp(d.date(), tz="UTC") + pd.Timedelta(hours=h)
            rows.append({"open": 100.0, "high": 101.0, "low": 99.0,
                         "close": 100.0 + di + h * 0.01, "volume": 1000})
            idx.append(ts)
    return pd.DataFrame(rows, index=pd.DatetimeIndex(idx, name="ts"))


def test_tz_guard_warns_on_non_us_ticker():
    """#45b: a non-US ticker suffix triggers a UserWarning when tz is the NY default."""
    intr = _asia_intraday()
    import warnings
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        bd.derive_daily_close(intr, ticker="600519.SS")
        assert any(issubclass(x.category, UserWarning) and "600519.SS" in str(x.message)
                   for x in w), "Expected UserWarning for CN ticker with default TZ"


def test_tz_guard_silent_with_explicit_tz():
    """#45b: no warning when an explicit (correct) tz is supplied for a non-US ticker."""
    intr = _asia_intraday()
    import warnings
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        bd.derive_daily_close(intr, tz="Asia/Shanghai", ticker="600519.SS")
        assert not any(issubclass(x.category, UserWarning) for x in w), \
            "No warning expected when tz is supplied explicitly"


def test_cn_session_buckets_to_correct_date():
    """#45b: a bar at 01:30 UTC (09:30 CST) must bucket to the CST calendar date,
    NOT to the previous NY day.  With the correct 'Asia/Shanghai' tz the daily-close
    index matches the session date; with the NY default it would drift."""
    intr = _asia_intraday()
    import warnings
    # correct tz -> first row index == 2026-06-15 (the CST session date)
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        close_cn = bd.derive_daily_close(intr, tz="Asia/Shanghai", ticker="600519.SS")
    assert pd.Timestamp("2026-06-15") in close_cn.index, \
        f"CST session date 2026-06-15 missing; got {close_cn.index.tolist()}"

    # NY-default tz -> the 01:30 UTC bar (= 20:30 EST June 14) falls on June 14,
    # not June 15.  This proves the mis-bucketing the guard warns about.
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        close_ny = bd.derive_daily_close(intr, tz="America/New_York", ticker="")
    # With NY tz the first intraday bar at 01:00 UTC June 15 appears on June 14 NY
    assert pd.Timestamp("2026-06-15") not in close_ny.index or \
        close_ny.index[0] < pd.Timestamp("2026-06-15"), \
        "NY-default should mis-bucket the first CN bar to the previous day"
