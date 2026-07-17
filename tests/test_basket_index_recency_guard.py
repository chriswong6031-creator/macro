"""tests/test_basket_index_recency_guard.py — render-budget + recency-guard pins for
engine/basket_index._load_member_ohlcv (#2697/#2698 follow-up).

MM_DATA_GUARD: every path is under tmp_path via monkeypatched lib.config.data_dir —
the suite NEVER touches the repo's real data/ directories.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from lib import config
from engine import basket_index as bi


# ------------------------------------------------------------------ fixtures

@pytest.fixture
def data_root(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(bi, "_CACHE", {})
    for d in ("baskets/ohlcv", "stocks", "china_stocks", "yahoo"):
        (tmp_path / d).mkdir(parents=True)
    return tmp_path


def _make_ohlcv(n: int, close_base: float = 100.0, start: str = "2024-01-01",
                columns: list[str] | None = None) -> pd.DataFrame:
    """Deterministic OHLCV with a stable close series; close_base seeds the level."""
    idx = pd.bdate_range(start, periods=n)
    close = pd.Series(close_base + np.arange(n, dtype=float) * 0.01, index=idx)
    cols = columns if columns is not None else ["open", "high", "low", "close", "volume"]
    df: dict[str, pd.Series] = {}
    if "close" in cols:
        df["close"] = close
    if "open" in cols:
        df["open"] = close * 0.995
    if "high" in cols:
        df["high"] = close * 1.005
    if "low" in cols:
        df["low"] = close * 0.990
    if "volume" in cols:
        df["volume"] = pd.Series(1_000_000.0, index=idx)
    return pd.DataFrame(df, index=idx)


def _write(path, df: pd.DataFrame) -> None:
    df.to_parquet(path)


# ------------------------------------------------------------------ tests

def test_fresh_deep_served_verbatim_and_no_full_fallback_read(data_root, monkeypatch):
    """bp and sp both end on the same date but have distinct close levels.
    RENDER-BUDGET PIN: the sp parquet must only be probed via columns=[] (index-only);
    the full 5-column read of sp must NOT happen when the deep tape is current."""
    n = 20
    bp_df = _make_ohlcv(n, close_base=200.0)
    sp_df = _make_ohlcv(n, close_base=100.0)
    _write(data_root / "baskets/ohlcv/AAPL.parquet", bp_df)
    _write(data_root / "stocks/AAPL.parquet", sp_df)

    real_read_parquet = pd.read_parquet
    calls: list[tuple] = []

    def spy(path, **kw):
        calls.append((str(path), kw.get("columns")))
        return real_read_parquet(path, **kw)

    monkeypatch.setattr(pd, "read_parquet", spy)
    result = bi._load_member_ohlcv("AAPL")
    assert result is not None
    # result close values should match bp_df (deep tape served), not sp_df
    last = result["close"].iloc[-1]
    assert abs(last - bp_df["close"].iloc[-1]) < 1e-6, "deep tape should be served verbatim"

    # Every call to the sp path must have been an index-only probe (columns=[])
    sp_str = str(data_root / "stocks/AAPL.parquet")
    sp_calls = [c for p, c in calls if p == sp_str]
    assert sp_calls, "sp must have been probed at least once (for recency check)"
    for cols in sp_calls:
        assert cols == [], f"sp was read with columns={cols!r}; expected [] (index-only probe)"


def test_stale_deep_tail_spliced_and_rescaled(data_root, caplog):
    """bp ends 11 business days before sp; sp close at the last shared bar is exactly half
    of bp's (factor 2.0). Assert: result last date == sp last date, spliced tail closes
    == sp tail * 2.0, bp's history rows intact, and caplog carries the splice warning."""
    # bp: 30 bars ending 2024-01-17 (approx); sp: 41 bars ending 11 bdays later
    bp_idx = pd.bdate_range("2024-01-02", periods=30)
    sp_idx = pd.bdate_range("2024-01-02", periods=41)
    overlap_date = bp_idx[-1]  # last shared bar
    # at overlap: bp close = 200, sp close = 100 → factor = 2.0
    bp_close = pd.Series(200.0, index=bp_idx)
    sp_close = pd.Series(100.0, index=sp_idx)
    bp_df = pd.DataFrame({"open": bp_close * 0.99, "high": bp_close * 1.01,
                          "low": bp_close * 0.98, "close": bp_close,
                          "volume": 1e6}, index=bp_idx)
    sp_df = pd.DataFrame({"open": sp_close * 0.99, "high": sp_close * 1.01,
                          "low": sp_close * 0.98, "close": sp_close,
                          "volume": 1e6}, index=sp_idx)
    _write(data_root / "baskets/ohlcv/MSFT.parquet", bp_df)
    _write(data_root / "stocks/MSFT.parquet", sp_df)

    import logging
    with caplog.at_level(logging.WARNING, logger="engine.basket_index"):
        result = bi._load_member_ohlcv("MSFT")

    assert result is not None
    result.index = pd.DatetimeIndex(result.index)
    # last date should be sp's last date (11 bdays ahead of bp)
    assert result.index.max() == sp_idx[-1], "result must extend to sp's last date"
    # tail rows (those beyond bp_idx[-1]) should have close == sp_close * 2.0
    tail = result[result.index > overlap_date]
    assert len(tail) > 0, "there should be spliced tail rows"
    expected_tail_close = 100.0 * 2.0  # sp close × factor
    assert (tail["close"] - expected_tail_close).abs().max() < 1e-6, \
        "spliced tail close should be rescaled by factor 2.0"
    # bp history rows preserved
    hist = result[result.index <= overlap_date]
    assert len(hist) == len(bp_idx), "all deep-tape rows must be present"
    assert any("spliced" in r.message for r in caplog.records), "splice warning must be emitted"


def test_one_session_lead_still_heals(data_root):
    """sp exactly 1 business day ahead => splice happens.
    Pins the adjudicated any-lead (no N-session threshold) semantics."""
    sp_idx = pd.bdate_range("2024-01-02", periods=21)
    bp_df = _make_ohlcv(20, close_base=100.0, start="2024-01-02")
    # sp: same length + 1 extra day
    sp_close = pd.Series(50.0, index=sp_idx)
    sp_df = pd.DataFrame({"open": sp_close, "high": sp_close, "low": sp_close,
                          "close": sp_close, "volume": 1e6}, index=sp_idx)
    _write(data_root / "baskets/ohlcv/SPY.parquet", bp_df)
    _write(data_root / "stocks/SPY.parquet", sp_df)
    result = bi._load_member_ohlcv("SPY")
    assert result is not None
    assert pd.DatetimeIndex(result.index).max() == sp_idx[-1], \
        "1-session lead must trigger splice"


def test_first_existing_fallback_only(data_root):
    """bp stale, sp exists but equally stale as bp, yp is fresh.
    Only sp (the first existing fallback) is consulted; yp is NOT spliced.
    Pins the break-after-first-existing design."""
    bp_idx = pd.bdate_range("2024-01-02", periods=20)
    bp_df = _make_ohlcv(20, close_base=100.0, start="2024-01-02")
    sp_df = _make_ohlcv(20, close_base=80.0, start="2024-01-02")  # same length as bp
    yp_idx = pd.bdate_range("2024-01-02", periods=30)             # 10 days fresher
    yp_close = pd.Series(70.0, index=yp_idx)
    yp_df = pd.DataFrame({"close": yp_close, "volume": 1e6}, index=yp_idx)
    _write(data_root / "baskets/ohlcv/QQQ.parquet", bp_df)
    _write(data_root / "stocks/QQQ.parquet", sp_df)
    _write(data_root / "yahoo/QQQ.parquet", yp_df)
    result = bi._load_member_ohlcv("QQQ")
    assert result is not None
    # yp ends 30 bdays out; if it were spliced, result would be longer than 20
    assert len(result) == 20, "yp must NOT be spliced; only the first existing fallback (sp) is checked"
    assert pd.DatetimeIndex(result.index).max() == bp_idx[-1]


def test_china_fallback_probed(data_root):
    """ticker '600000.SS': bp stale, no sp, cp is fresher => spliced from china_stocks."""
    ticker = "600000.SS"
    bp_idx = pd.bdate_range("2024-01-02", periods=20)
    cp_idx = pd.bdate_range("2024-01-02", periods=30)
    bp_close = pd.Series(100.0, index=bp_idx)
    cp_close = pd.Series(50.0, index=cp_idx)
    bp_df = pd.DataFrame({"open": bp_close, "high": bp_close, "low": bp_close,
                          "close": bp_close, "volume": 1e6}, index=bp_idx)
    cp_df = pd.DataFrame({"high": cp_close, "low": cp_close,
                          "close": cp_close, "volume": 1e6}, index=cp_idx)
    _write(data_root / f"baskets/ohlcv/{ticker}.parquet", bp_df)
    _write(data_root / f"china_stocks/{ticker}.parquet", cp_df)
    result = bi._load_member_ohlcv(ticker)
    assert result is not None
    # splice should have extended the tape to cp's last date
    assert pd.DatetimeIndex(result.index).max() == cp_idx[-1], \
        "china_stocks fallback must be spliced when it is fresher than the deep tape"


def test_yahoo_tail_synthesised(data_root):
    """bp stale; only yp exists with ONLY close+volume columns.
    Spliced tail rows must have open==high==low==close and no NaN in price columns."""
    bp_idx = pd.bdate_range("2024-01-02", periods=20)
    yp_idx = pd.bdate_range("2024-01-02", periods=30)
    bp_close = pd.Series(200.0, index=bp_idx)
    yp_close = pd.Series(100.0, index=yp_idx)
    bp_df = pd.DataFrame({"open": bp_close, "high": bp_close, "low": bp_close,
                          "close": bp_close, "volume": 1e6}, index=bp_idx)
    yp_df = pd.DataFrame({"close": yp_close, "volume": 5e5}, index=yp_idx)
    _write(data_root / "baskets/ohlcv/NVDA.parquet", bp_df)
    _write(data_root / "yahoo/NVDA.parquet", yp_df)
    result = bi._load_member_ohlcv("NVDA")
    assert result is not None
    tail = result[result.index > bp_idx[-1]]
    assert len(tail) > 0, "tail rows should be present"
    for col in ("open", "high", "low", "close"):
        assert col in tail.columns, f"column {col} missing from tail"
        assert not tail[col].isna().any(), f"NaN in tail column {col}"
    # open/high/low should equal close for the tail (synthesised from close before rescale)
    # After ratio rescale all three should still be equal (same factor applied)
    assert (tail["open"] == tail["high"]).all()
    assert (tail["open"] == tail["low"]).all()
    assert (tail["open"] == tail["close"]).all()


def test_empty_deep_falls_through(data_root):
    """bp exists with 0 rows; sp exists and has data => sp is served (fall-through path)."""
    bp_df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    sp_df = _make_ohlcv(15, close_base=100.0)
    _write(data_root / "baskets/ohlcv/AMZN.parquet", bp_df)
    _write(data_root / "stocks/AMZN.parquet", sp_df)
    result = bi._load_member_ohlcv("AMZN")
    assert result is not None and len(result) == 15, \
        "empty deep store must fall through to sp"
    # open should be synthesised from close (sp has no open column)
    sp_no_open = _make_ohlcv(15, close_base=100.0, columns=["close", "volume"])
    bi._CACHE.clear()
    _write(data_root / "stocks/AMZN.parquet", sp_no_open)
    result2 = bi._load_member_ohlcv("AMZN")
    assert result2 is not None
    # open synthesised from close — all values should equal close
    assert (result2["open"] == result2["close"]).all()


def test_no_fallback_deep_served_even_if_ancient(data_root):
    """Only bp exists, ends months ago => served unchanged — no fallback to probe."""
    bp_df = _make_ohlcv(20, close_base=150.0, start="2023-01-02")
    _write(data_root / "baskets/ohlcv/META.parquet", bp_df)
    result = bi._load_member_ohlcv("META")
    assert result is not None and len(result) == 20
    last_close = result["close"].iloc[-1]
    assert abs(last_close - 150.0 - 19 * 0.01) < 1e-6, "ancient deep tape served unchanged"


def test_corrupt_fallback_probe_no_crash(data_root):
    """bp is fresh; sp contains garbage bytes (not a valid parquet).
    bp must be served and no exception must propagate."""
    bp_df = _make_ohlcv(20, close_base=100.0)
    _write(data_root / "baskets/ohlcv/GOOG.parquet", bp_df)
    (data_root / "stocks/GOOG.parquet").write_bytes(b"not a parquet file \x00\xff")
    result = bi._load_member_ohlcv("GOOG")
    assert result is not None, "corrupt sp must not crash or suppress the deep result"
    assert len(result) == 20


def test_staler_fallback_probe_only_no_full_read(data_root, monkeypatch):
    """sp exists but is STALER than the deep tape => served deep, and the sp parquet
    is only ever probed via columns=[] — pins the other arm of the budget guard
    (an inverted comparison would splice a stale tail AND double the read cost)."""
    bp_df = _make_ohlcv(25, close_base=200.0)
    sp_df = _make_ohlcv(20, close_base=100.0)          # 5 bdays behind bp
    _write(data_root / "baskets/ohlcv/AVGO.parquet", bp_df)
    _write(data_root / "stocks/AVGO.parquet", sp_df)

    real_read_parquet = pd.read_parquet
    calls: list[tuple] = []

    def spy(path, **kw):
        calls.append((str(path), kw.get("columns")))
        return real_read_parquet(path, **kw)

    monkeypatch.setattr(pd, "read_parquet", spy)
    result = bi._load_member_ohlcv("AVGO")
    assert result is not None
    assert pd.DatetimeIndex(result.index).max() == bp_df.index[-1], \
        "staler fallback must never displace the deep tape"
    assert abs(result["close"].iloc[-1] - bp_df["close"].iloc[-1]) < 1e-6
    sp_str = str(data_root / "stocks/AVGO.parquet")
    sp_calls = [c for p, c in calls if p == sp_str]
    assert sp_calls and all(c == [] for c in sp_calls), \
        "a staler sp must only ever be probed index-only (columns=[])"


def test_tz_aware_fallback_heals_naive_deep(data_root):
    """sp carries a tz-aware index while the deep tape is naive. The probe compare and
    the splice must tz-strip rather than raise — a raise inside the loader's outer try
    would drop the member to None entirely (reviewer-found regression class)."""
    bp_df = _make_ohlcv(20, close_base=100.0, start="2024-01-02")
    sp_idx = pd.bdate_range("2024-01-02", periods=30, tz="America/New_York")
    sp_close = pd.Series(100.0, index=sp_idx)
    sp_df = pd.DataFrame({"open": sp_close, "high": sp_close, "low": sp_close,
                          "close": sp_close, "volume": 1e6}, index=sp_idx)
    _write(data_root / "baskets/ohlcv/ORCL.parquet", bp_df)
    _write(data_root / "stocks/ORCL.parquet", sp_df)
    result = bi._load_member_ohlcv("ORCL")
    assert result is not None, "tz mismatch must never drop the member"
    assert pd.DatetimeIndex(result.index).max() == sp_idx[-1].tz_localize(None), \
        "tz-aware fresher fallback must still heal the stale deep tape"


def test_empty_first_fallback_does_not_veto_heal(data_root):
    """bp stale; sp exists but is a 0-row file; yp is fresher. An existing-but-empty
    candidate has no opinion (probe None) — the loop must advance to yp and heal."""
    bp_df = _make_ohlcv(20, close_base=200.0, start="2024-01-02")
    empty = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    yp_idx = pd.bdate_range("2024-01-02", periods=30)
    yp_df = pd.DataFrame({"close": pd.Series(100.0, index=yp_idx), "volume": 1e6},
                         index=yp_idx)
    _write(data_root / "baskets/ohlcv/AMD.parquet", bp_df)
    _write(data_root / "stocks/AMD.parquet", empty)
    _write(data_root / "yahoo/AMD.parquet", yp_df)
    result = bi._load_member_ohlcv("AMD")
    assert result is not None
    assert pd.DatetimeIndex(result.index).max() == yp_idx[-1], \
        "empty sp must not veto the yp heal"


def test_cache_semantics(data_root, monkeypatch):
    """Load once, delete all parquet files, call again => same frame from cache.
    A read_parquet spy records zero new calls on the second load."""
    bp_df = _make_ohlcv(10, close_base=100.0)
    _write(data_root / "baskets/ohlcv/TSLA.parquet", bp_df)

    real_read = pd.read_parquet
    call_count: list[int] = [0]

    def spy(path, **kw):
        call_count[0] += 1
        return real_read(path, **kw)

    monkeypatch.setattr(pd, "read_parquet", spy)
    first = bi._load_member_ohlcv("TSLA")
    calls_after_first = call_count[0]
    assert first is not None

    # delete all parquet files so a real read would fail
    for f in data_root.rglob("*.parquet"):
        f.unlink()

    second = bi._load_member_ohlcv("TSLA")
    assert call_count[0] == calls_after_first, \
        "second call must be served from cache with zero new pd.read_parquet calls"
    assert second is first, "cache must return the exact same frame object"
