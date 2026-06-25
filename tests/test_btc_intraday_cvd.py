"""Intraday aggressor-CVD collector parsing + engine (display-only).

Run: .venv/bin/python -m tests.test_btc_intraday_cvd
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from collectors.okx import OkxAdapter  # noqa: E402
from engine import btc_intraday_cvd as CVD  # noqa: E402


class _Resp:
    def __init__(self, data):
        self._d = data

    def json(self):
        return {"code": "0", "data": self._d}


def test_collector_parses_hourly_buy_sell():
    a = OkxAdapter()
    # rubik returns NEWEST-FIRST rows [ts_ms, sellVol, buyVol]
    rows = [[str(1_700_000_000_000 + i * 3_600_000), str(100 + i), str(200 + i)] for i in range(6)]
    rows = rows[::-1]
    a.http_get = lambda *args, **kw: _Resp(rows)
    df = a._taker_volume_hourly()
    assert list(df.columns) == ["taker_buy_vol", "taker_sell_vol"]
    assert df.index.is_monotonic_increasing
    # buy (200+) must exceed sell (100+) — confirms column order not flipped
    assert (df["taker_buy_vol"] > df["taker_sell_vol"]).all()
    # hourly cadence preserved (not normalized to dates)
    assert (df.index.to_series().diff().dropna() == pd.Timedelta(hours=1)).all()


def test_collector_empty_returns_none():
    a = OkxAdapter()
    a.http_get = lambda *args, **kw: _Resp([])
    assert a._taker_volume_hourly() is None


def _store_patch(frames):
    orig = CVD.store.read
    CVD.store.read = lambda ns, nm: frames.get((ns, nm))
    return orig


def _hourly(n, buy, sell, start="2026-01-01"):
    idx = pd.date_range(start, periods=n, freq="h")
    return pd.DataFrame({"taker_buy_vol": np.asarray(buy, dtype=float),
                         "taker_sell_vol": np.asarray(sell, dtype=float)}, index=idx)


def test_engine_accruing_and_distribution_state():
    n = 800                                          # < MIN_HOURS_DIV -> accruing
    buy = np.full(n, 1e7)                            # realistic ~1e7 hourly volume
    sell = np.full(n, 1e7); sell[-24:] = 3e7         # heavy net selling last 24h
    df = _hourly(n, buy, sell)
    orig = _store_patch({("okx", "taker_volume_hourly"): df})
    try:
        o = CVD.compute()
    finally:
        CVD.store.read = orig
    assert o["ok"] and o["accruing"] is True
    assert o["flow_state"] == "distribution"         # net aggressor selling
    assert o["net_flow_24h_mn"] < 0
    assert o["divergence"] is None                   # not enough history


def test_engine_divergence_when_history_sufficient():
    n = 1600                                          # > MIN_HOURS_DIV
    rng = np.random.default_rng(0)
    buy = 1e7 + rng.normal(0, 5e5, n)
    sell = 1e7 + rng.normal(0, 5e5, n)
    # price firm/up while flow turns net-negative -> "hidden distribution" lean
    sell[-200:] += 4e6
    cvd_df = _hourly(n, buy, sell)
    rets = 0.0002 + rng.normal(0, 0.003, n)          # noisy uptrend (nonzero return variance)
    price = pd.DataFrame({"close": 60000 * np.cumprod(1 + rets)}, index=cvd_df.index)
    orig = _store_patch({("okx", "taker_volume_hourly"): cvd_df, ("coinbase", "btc_hourly"): price})
    try:
        o = CVD.compute()
    finally:
        CVD.store.read = orig
    assert o["ok"] and o["accruing"] is False
    assert o["divergence"] is not None
    assert 0.0 <= o["divergence"]["pctile"] <= 1.0
    assert o["divergence"]["state"] in ("hidden_distribution", "hidden_accumulation", "none")


def test_engine_no_store_degrades():
    orig = _store_patch({})
    try:
        o = CVD.compute()
    finally:
        CVD.store.read = orig
    assert o["ok"] is False and o["accruing"] is True


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed")
