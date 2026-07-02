"""Intraday -> multi-timeframe bar derivation hooks (engine.bar_derive).

Pins the contract that matters: the derived DAILY CLOSE Series is a drop-in for the
nightly store's ``['close'].dropna()`` (so the confluence engine consumes it unchanged),
the supplementary 2D/3D OHLCV frames aggregate correctly and stay OUT of the signal path,
and the integration switch falls back cleanly to the adjusted store.
"""
from __future__ import annotations

import pandas as pd
import pytest

from engine import bar_derive as bd


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


def test_3d_ohlcv_close_equals_internal_3B_resample():
    """derive_3d_ohlcv close == the daily close resampled '3B' (same as signal_frame
    does internally) — proves the supplementary frame is consistent, not divergent."""
    intr, _ = _synthetic_intraday()
    daily = bd.derive_daily_ohlcv(intr)
    three = bd.derive_3d_ohlcv(daily)
    ref = daily["close"].resample("3B").last().dropna()
    assert list(three["close"].values) == list(ref.values)
    # 2D candle aggregation: high is the max across the 2-day bucket
    two = bd.derive_2d_ohlcv(daily)
    assert two["high"].iloc[0] == daily["high"].iloc[:2].max()


def test_resample_ohlcv_tolerates_missing_open():
    """The nightly store has no 'open' column — resampling must not crash on its absence."""
    days = pd.bdate_range("2026-01-01", periods=9)
    df = pd.DataFrame({"close": range(9), "high": range(9), "low": range(9),
                       "volume": [1] * 9}, index=days, dtype="float64")
    out = bd.resample_ohlcv(df, "3B")
    assert "open" not in out.columns
    assert out["close"].iloc[0] == 2.0          # last of the first 3-business-day bucket


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
