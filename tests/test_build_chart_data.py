"""Per-stock chart OHLC emitter (scripts/build_chart_data.py).

The bespoke single-stock chart (site/chart.js) is fed a compact per-ticker JSON
written by this emitter. These tests pin the load-bearing invariants the chart
relies on:

  * candlestick reconstruction — the deep price store has no `open` column, so
    open is the PRIOR close and the high/low are clamped to contain it, or candles
    render inverted (wick swallowing the body);
  * the close-only path stays a 3-tuple [date, close, vol] the chart reads as an
    area series;
  * the history cap keeps every file small (lazy-loaded one-per-view);
  * the filename key matches the transform stock.html.j2 already uses to fetch
    stockdata/<safe>.json, so ohlc/<safe>.json resolves for the same ticker.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from scripts import build_chart_data as bcd


def _ohlc_df(n=5, start="2026-01-01"):
    idx = pd.date_range(start, periods=n, freq="D", name="Date")
    close = pd.Series([10.0, 11.0, 12.0, 11.5, 13.0][:n], index=idx)
    high = pd.Series([10.5, 11.4, 12.6, 12.0, 13.2][:n], index=idx)
    low = pd.Series([9.6, 10.4, 11.2, 11.0, 12.1][:n], index=idx)
    vol = pd.Series([100, 200, 300, 400, 500][:n], index=idx)
    return pd.DataFrame({"close": close, "high": high, "low": low, "volume": vol})


def test_safe_filename_matches_template_transform():
    assert bcd._safe("AAPL") == "AAPL"
    assert bcd._safe("BRK=F") == "BRK_F"          # futures '=' -> '_'
    assert bcd._safe("^GSPC") == "_GSPC"          # index '^' -> '_'


def test_ohlc_open_is_prior_close_first_bar_opens_at_itself():
    bars = bcd._bars_ohlc(_ohlc_df())
    # [date, open, high, low, close, vol]
    assert bars[0][1] == bars[0][4]               # first bar: open == close
    for i in range(1, len(bars)):
        assert bars[i][1] == bars[i - 1][4]       # open == prior close


def test_ohlc_high_low_clamped_to_contain_body():
    # a gap-up day: prior close (=open) sits ABOVE the raw high -> must be clamped
    idx = pd.date_range("2026-01-01", periods=2, freq="D", name="Date")
    df = pd.DataFrame({
        "close": pd.Series([100.0, 90.0], index=idx),
        "high": pd.Series([101.0, 95.0], index=idx),   # day2 high 95 < open(=100)
        "low": pd.Series([99.0, 88.0], index=idx),
        "volume": pd.Series([1, 2], index=idx),
    })
    _, o, h, lo, c, _v = bcd._bars_ohlc(df)[1]
    assert o == 100.0
    assert h >= max(o, c)                         # high lifted to include the open
    assert lo <= min(o, c)


def test_ohlc_volume_is_int_or_none():
    df = _ohlc_df()
    df.loc[df.index[2], "volume"] = np.nan        # a missing print
    bars = bcd._bars_ohlc(df)
    assert isinstance(bars[0][5], int)
    assert bars[2][5] is None


def test_close_only_is_three_tuple_and_drops_nans():
    idx = pd.date_range("2026-01-01", periods=4, freq="D", name="Date")
    close = pd.Series([5.0, np.nan, 6.0, 6.5], index=idx)
    bars = bcd._bars_close(close)
    assert len(bars) == 3                          # NaN row dropped
    assert all(len(b) == 3 for b in bars)          # [date, close, vol]
    assert bars[0] == ["2026-01-01", 5.0, None]    # no volume -> None


def test_history_capped_to_max_bars():
    long_df = _ohlc_df(n=1)
    big = pd.concat([long_df] * 0 + [_long_ohlc(bcd.MAX_BARS + 50)])
    assert len(bcd._bars_ohlc(big)) == bcd.MAX_BARS


def _long_ohlc(n):
    idx = pd.date_range("2000-01-01", periods=n, freq="D", name="Date")
    base = np.linspace(10, 50, n)
    return pd.DataFrame({
        "close": pd.Series(base, index=idx),
        "high": pd.Series(base + 1, index=idx),
        "low": pd.Series(base - 1, index=idx),
        "volume": pd.Series(np.arange(n), index=idx),
    })
