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
