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


# ── display-grid anchor block (era display-grid-abs-session-2026-08-06, DG-R3/R4/R6) ──
#
# The chart cannot re-derive session positions in the browser, so the payload SHIPS its
# 3-session bucket boundaries. These pin the emitter half of that contract.

import json                                                  # noqa: E402
import shutil                                                # noqa: E402
import subprocess                                            # noqa: E402
from datetime import date                                    # noqa: E402
from pathlib import Path                                     # noqa: E402

import pytest                                                # noqa: E402

from engine import bar_derive as bd                          # noqa: E402
from lib import nyse_calendar                                # noqa: E402

_SESSIONS = pd.DatetimeIndex(pd.to_datetime(
    nyse_calendar.sessions_between(date(2023, 1, 3), date(2026, 8, 4))))


def _session_frame(n: int) -> pd.DataFrame:
    """Deep-store-shaped OHLCV on the last ``n`` REAL NYSE sessions (never bdate_range:
    business days include exchange holidays, which is the mis-split this era removed)."""
    idx = _SESSIONS[len(_SESSIONS) - n:]
    base = np.linspace(10, 50, n)
    return pd.DataFrame({"close": pd.Series(base, index=idx),
                         "high": pd.Series(base + 1, index=idx),
                         "low": pd.Series(base - 1, index=idx),
                         "volume": pd.Series(np.arange(n), index=idx)},
                        index=idx)


def test_anchor_block_marks_every_bucket_open():
    df = _session_frame(200)
    rec = bcd._with_anchor({"t": "T", "o": 1, "bars": bcd._bars_ohlc(df)}, df["close"], "US")
    dates = pd.DatetimeIndex(pd.to_datetime([b[0] for b in rec["bars"]]))
    ids = bd.bucket_ids(dates)
    assert rec["anchor"]["b3"] == [0] + [i for i in range(1, len(ids)) if ids[i] != ids[i - 1]]
    # every shipped boundary really opens a bucket, and no boundary is missing
    assert all(i == 0 or ids[i] != ids[i - 1] for i in rec["anchor"]["b3"])
    assert len(rec["anchor"]["b3"]) == len(bd.derive_3d_ohlcv(df))


def test_anchor_era_is_bar_derives_single_source():
    """DG-R6: one era string, imported — never re-typed into an emitter."""
    df = _session_frame(30)
    rec = bcd._with_anchor({"t": "T", "o": 1, "bars": bcd._bars_ohlc(df)}, df["close"], "US")
    assert rec["anchor"]["era"] == bd.ANCHOR_ERA


@pytest.mark.parametrize("cap", [301, 302, 303])
def test_window_is_trimmed_to_open_a_bucket(cap):
    """DG-R4 at every phase the cap can land on: the first shipped row opens a bucket, so
    the first candle is complete and the visible grid does not regroup night over night."""
    df = _session_frame(400)
    capped = df.tail(cap)
    rec = bcd._with_anchor({"t": "T", "o": 1, "bars": bcd._bars_ohlc(capped)},
                           df["close"], "US")
    kept = pd.DatetimeIndex(pd.to_datetime([b[0] for b in rec["bars"]]))
    assert 0 <= cap - len(kept) <= 2                      # at most n-1 rows dropped
    prev = df.index[df.index < kept[0]]
    assert bd.bucket_ids(kept)[0] != bd.bucket_ids(prev[-1:])[0], \
        "the window still shares its first bucket with the row before it"


def test_a_halt_moves_boundaries_off_row_arithmetic():
    """Why boundaries and not a phase offset: a mid-window halt desynchronises floor(i/3)
    from the calendar for the whole remainder of the window, and b3 tracks the calendar."""
    df = _session_frame(120)
    gapped = df.drop(df.index[40:44])                     # a 4-session suspension
    rec = bcd._with_anchor({"t": "T", "o": 1, "bars": bcd._bars_ohlc(gapped)},
                           gapped["close"], "US")
    b3 = rec["anchor"]["b3"]
    assert b3 != list(range(0, len(rec["bars"]), 3)), \
        "with a halt in the window, row arithmetic must disagree with the session grid"
    ids = bd.bucket_ids(pd.DatetimeIndex(pd.to_datetime([b[0] for b in rec["bars"]])))
    assert all(i == 0 or ids[i] != ids[i - 1] for i in b3)


def test_payload_shape_is_otherwise_unchanged():
    """The anchor block is additive — every existing key and the bar tuple stay as they
    were, so an old client ignores it and a stale cached payload still renders."""
    df = _session_frame(40)
    bars = bcd._bars_ohlc(df)
    rec = bcd._with_anchor({"t": "T", "o": 1, "src": "deep", "bars": list(bars)},
                           df["close"], "US")
    assert set(rec) == {"t", "o", "src", "bars", "anchor"}
    assert all(len(b) == 6 for b in rec["bars"])
    assert rec["bars"] == bars[len(bars) - len(rec["bars"]):]   # only leading rows trimmed


def _run_chart_resample(rows, tf, anchor):
    """Execute site/chart.js's REAL ``resample`` against a fixture, in node.

    A source-text assertion is not enough here: deleting the one line that makes the
    boundaries drive the bucket key leaves every string a grep would look for (`anchor`,
    `b3`, the fallback ordering) still in the file, so the guard stays green while the
    client silently reverts to row arithmetic — verified by mutation. Running the function
    is what actually pins the behaviour.
    """
    js = (Path(__file__).resolve().parents[1] / "site" / "chart.js").read_text()
    fn = js[js.index("function resample(rows, tf"):js.index("  function resample4H")]
    harness = (fn + "\nconst out = resample(" + json.dumps(rows) + ", "
               + json.dumps(tf) + ", " + json.dumps(anchor) + ");\n"
               "console.log(JSON.stringify(out.map(r => r.time)));\n")
    res = subprocess.run([shutil.which("node"), "-e", harness],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


def _rows_and_expected(df):
    """(payload rows, the engine grid as each bucket's LAST session) for a frame."""
    rec = bcd._with_anchor({"t": "T", "o": 1, "bars": bcd._bars_ohlc(df)}, df["close"], "US")
    rows = [{"time": b[0], "o": b[1], "h": b[2], "l": b[3], "c": b[4], "v": b[5]}
            for b in rec["bars"]]
    dates = [b[0] for b in rec["bars"]]
    seen = {}
    for d, b in zip(dates, bd.bucket_ids(pd.DatetimeIndex(pd.to_datetime(dates)))):
        seen[int(b)] = d                      # last write per bucket = its closing session
    return rec, rows, dates, [seen[k] for k in sorted(seen)]


@pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")
def test_chart_js_buckets_3d_by_the_shipped_boundaries():
    """The client half of DG-R3, pinned by EXECUTION on a GAPPED window.

    The fixture must contain a halt. On a gapless window the DG-R4 trim already lands row
    0 on a bucket open, and from there ``floor(i/3)`` counts the same groups the calendar
    does — so a gapless fixture cannot tell the two apart and this test would pass with
    the client's use of the shipped grid deleted (verified by mutation). Missing sessions
    are exactly where row arithmetic and the session calendar part company, and they are
    ordinary: halts, suspensions, and every short-history or late-listing name.
    """
    df = _session_frame(60)
    gapped = df.drop(df.index[20:24])                  # a 4-session suspension mid-window
    rec, rows, dates, want = _rows_and_expected(gapped)

    got = _run_chart_resample(rows, "3D", rec["anchor"])
    assert got == want, "3D candles do not match the engine's session buckets"

    # the fixture has real discriminating power: row arithmetic gives a DIFFERENT answer
    naive = [dates[min(i + 2, len(dates) - 1)] for i in range(0, len(dates), 3)]
    assert naive != want, "fixture cannot distinguish the two grids — it proves nothing"

    # a stale cached payload (no anchor block) degrades to exactly that old grouping
    assert _run_chart_resample(rows, "3D", None) == naive
    # and the payload's block is actually threaded into the render call
    js = (Path(__file__).resolve().parents[1] / "site" / "chart.js").read_text()
    assert "resample(this.rows, this.tf, this.data && this.data.anchor)" in js


@pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")
def test_a_trimmed_gapless_window_agrees_with_row_arithmetic():
    """The honest boundary of DG-R4, stated as a test rather than left for a reader to
    discover: once the window opens on a bucket, a name that trades EVERY session groups
    identically under both grids. That is why the trim alone stabilises the common case —
    and why ``b3`` is still the correctness carrier: it is what covers the gapped names,
    and it keeps the client correct without trusting the emitter's trim."""
    rec, rows, dates, want = _rows_and_expected(_session_frame(60))
    naive = [dates[min(i + 2, len(dates) - 1)] for i in range(0, len(dates), 3)]
    assert want == naive
    assert _run_chart_resample(rows, "3D", rec["anchor"]) == want
