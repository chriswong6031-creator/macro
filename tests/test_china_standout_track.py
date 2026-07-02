"""China board-ORDER forward ledger — the CN-1 grader truth pass (masterplan §W6-CN).

Pins the conventions locked in the same pass as the #791 store-group fix:
  • the ledger reads the china_stocks store (per-name), not china (30 ETFs) — the dead-on-arrival
    bug that made n_graded=0 forever;
  • grading is CSI300-relative (510300.SS), fill-realistic (T+1 (H+L)/2), excludes locked-limit
    entry bars, and is NEVER anchored on a §7 marker date.
"""
import numpy as np
import pandas as pd
import pytest

from lib import config, store
from engine import china_standout_track as t


def _mk_ohlc(dates, closes, *, flat_at=None):
    """Build an OHLC frame; ``flat_at`` (index int) forces a locked-limit bar (h==l==c)."""
    closes = np.asarray(closes, dtype=float)
    df = pd.DataFrame({
        "close": closes,
        "high": closes * 1.01,
        "low": closes * 0.99,
        "volume": np.full(len(closes), 1e6),
    }, index=pd.DatetimeIndex(dates, name="Date"))
    if flat_at is not None:
        df.iloc[flat_at, [df.columns.get_loc("high"), df.columns.get_loc("low")]] = closes[flat_at]
    return df


@pytest.fixture
def cn_store(tmp_path, monkeypatch):
    """A synthetic china_stocks + china (CSI300 ETF) store 130 sessions long."""
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    dates = pd.bdate_range("2026-01-01", periods=130)
    return tmp_path, dates


def test_store_group_names_resolve(cn_store):
    """The #791 fix: per-NAME board tickers resolve in china_stocks (they never do in china)."""
    tmp_path, dates = cn_store
    df = _mk_ohlc(dates, np.linspace(10, 11, len(dates)))
    store.upsert("china_stocks", "600000.SS", df)
    assert t._price_frame("600000.SS") is not None            # names resolve now
    assert store.read("china", "600000.SS") is None           # the old (broken) group is empty


def test_grade_is_csi300_relative_and_fill_realistic(cn_store):
    """A matured row is graded on the T+1 (H+L)/2 fill, EXCESS over CSI300 — matches manual math."""
    tmp_path, dates = cn_store
    name_px = 10.0 * (1.02 ** np.arange(len(dates)))          # steady +2%/session name
    bench_px = 10.0 * (1.01 ** np.arange(len(dates)))         # slower CSI300
    store.upsert("china_stocks", "600001.SS", _mk_ohlc(dates, name_px))
    store.upsert("china", t._BENCH, _mk_ohlc(dates, bench_px)[["close", "volume"]])

    d0 = dates[0]
    ex, pinned = t._fwd_excess("600001.SS", d0, 21, t._bench_close())
    # manual: fill = T+1 (H+L)/2, exit = close at +21 sessions after d0
    df = t._price_frame("600001.SS")
    t1 = df.index[df.index > d0][0]
    fill = (df.loc[t1, "high"] + df.loc[t1, "low"]) / 2.0
    fwd = df["close"][df.index > d0]
    name_ret = fwd.iloc[21] / fill - 1.0
    b = t._bench_close(); bs = b[b.index > d0]
    bench_ret = bs.iloc[21] / bs.iloc[0] - 1.0
    assert ex == pytest.approx(name_ret - bench_ret, abs=1e-9)
    assert ex > 0                                             # faster name beats CSI300


def test_locked_limit_entry_excluded(cn_store):
    """A T+1 bar that is locked limit (high==low==close) is UNFILLABLE → excluded (None), not graded."""
    tmp_path, dates = cn_store
    px = 10.0 * (1.02 ** np.arange(len(dates)))
    df = _mk_ohlc(dates, px, flat_at=1)                       # T+1 (index 1) is locked
    store.upsert("china_stocks", "600002.SS", df)
    store.upsert("china", t._BENCH, _mk_ohlc(dates, px)[["close", "volume"]])
    ex, _ = t._fwd_excess("600002.SS", dates[0], 21, t._bench_close())
    assert ex is None                                        # fabricating a fill here is forbidden


def test_pinned_reference_close_flagged_not_graded_from_pin(cn_store):
    """A board-date close pinned at its own high is FLAGGED, but the grade still uses the T+1 fill."""
    tmp_path, dates = cn_store
    px = 10.0 * (1.02 ** np.arange(len(dates)))
    df = _mk_ohlc(dates, px)
    df.iloc[0, df.columns.get_loc("high")] = df.iloc[0, df.columns.get_loc("close")]  # d0 close==high
    store.upsert("china_stocks", "600003.SS", df)
    store.upsert("china", t._BENCH, _mk_ohlc(dates, px)[["close", "volume"]])
    ex, pinned = t._fwd_excess("600003.SS", dates[0], 21, t._bench_close())
    assert pinned is True and ex is not None                 # flagged, still graded from the T+1 fill


def test_grade_never_anchors_on_marker_date_leak(cn_store):
    """SYNTHETIC LOOK-AHEAD LEAK TEST — the grade must be knowable at the board close.

    Construct a name that is FLAT up to and including the board date, then jumps the day AFTER.
    A leaky grader that resolved the label with the next bar (signal_quality.py:161 'take' rule)
    would see the jump; the honest ledger anchors on the board-date close and measures from the T+1
    FILL, so the forward return is real and forward — it must equal the manual forward-from-fill
    number, never a value that peeks at the board-date bar's own future."""
    tmp_path, dates = cn_store
    px = np.full(len(dates), 10.0)
    px[1] = 12.0                                            # the JUMP lands on the T+1 fill bar
    px[2:] = 13.0 * (1.001 ** np.arange(len(dates) - 2))    # keep drifting so fill != d0 close
    store.upsert("china_stocks", "600004.SS", _mk_ohlc(dates, px))
    store.upsert("china", t._BENCH, _mk_ohlc(dates, np.full(len(dates), 10.0))[["close", "volume"]])
    d0 = dates[0]
    ex, _ = t._fwd_excess("600004.SS", d0, 21, t._bench_close())
    df = t._price_frame("600004.SS")
    t1 = df.index[df.index > d0][0]
    fill = (df.loc[t1, "high"] + df.loc[t1, "low"]) / 2.0    # T+1 fill sees the post-jump price (~12)
    fwd = df["close"][df.index > d0]
    manual = fwd.iloc[21] / fill - 1.0                       # bench flat → excess == name return
    assert ex == pytest.approx(manual, abs=1e-9)
    # the anchor is strictly the T+1 fill (~12): the return is NOT computed off the stale d0 close
    # (10.0), which would have manufactured a spuriously LARGER "gain" the moment the name jumped.
    stale = fwd.iloc[21] / px[0] - 1.0
    assert stale > ex                                        # the leaky base overstates the return
    assert ex != pytest.approx(stale, abs=1e-3)


def test_grade_end_to_end_publishes_conventions(cn_store):
    """grade() over a real (matured) synthetic ledger publishes the honest convention block + a
    Wilson-CI hit rate vs CSI300, and resolves prices (n>0) — proving the ledger is no longer dead."""
    tmp_path, dates = cn_store
    store.upsert("china", t._BENCH, _mk_ohlc(dates, 10.0 * (1.005 ** np.arange(len(dates))))[["close", "volume"]])
    rows = []
    rng = np.random.default_rng(0)
    for i in range(20):
        tk = f"60{i:04d}.SS"
        drift = 1.0 + (0.02 if i < 10 else 0.001)            # first 10 beat, rest lag
        store.upsert("china_stocks", tk, _mk_ohlc(dates, 10.0 * (drift ** np.arange(len(dates)))))
        rows.append({"ticker": tk, "price": 10.0, "signal": {"tier_cascade": "T2"},
                     "setup": "reversal", "extension": {"extended": i >= 10}, "washout_2w": False})
    t.append_board(rows, asof=str(dates[0].date()))
    g = t.grade()
    assert g["available"] and g["grading"]["benchmark"] == t._BENCH
    assert g["grading"]["relative"] and g["grading"]["marker_dates"] == "forbidden"
    h21 = g["by_horizon"]["21d"]
    assert h21["n"] >= t._MIN_GRADED                          # NOT perma-accruing anymore
    assert 0.0 <= h21["hit_vs_csi300"] <= 1.0
    assert h21["hit_ci"][0] <= h21["hit_vs_csi300"] <= h21["hit_ci"][1]
    assert g["n_graded"] > 0
