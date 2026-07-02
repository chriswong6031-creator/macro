"""Raw A-share price plane (collectors/china_stock_raw.py) — masterplan §W6-CN fix 3.

Proves the new RAW collector requests auto_adjust=False into a SEPARATE store group,
so level/limit/gap/A-H logic has a nominal price plane distinct from the adjusted
total-return plane the signals use. Network-free: yfinance.download is stubbed.

Run: .venv/bin/python -m pytest tests/test_china_raw_plane.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_raw_adapter_requests_unadjusted_into_separate_group(monkeypatch):
    from collectors import _stock_ohlc
    from collectors.china_stock_raw import ChinaStockRawPriceAdapter

    calls = {}

    def fake_download(batch, period, auto_adjust, progress, group_by, threads):
        calls["auto_adjust"] = auto_adjust
        idx = pd.bdate_range("2024-01-01", periods=60)
        cols = pd.MultiIndex.from_product([batch, ["Close", "High", "Low", "Volume"]])
        data = np.tile(np.linspace(10, 12, 60)[:, None], (1, len(cols)))
        return pd.DataFrame(data, index=idx, columns=cols)

    monkeypatch.setattr(_stock_ohlc.yf, "download", fake_download)
    # force the shallow/backfill plan without touching disk
    monkeypatch.setattr(_stock_ohlc, "_fetch_plan", lambda t, g, f: {"max": list(t)})

    a = ChinaStockRawPriceAdapter()
    frames = a.fetch(tickers=["600519.SS", "000001.SZ"])

    assert calls["auto_adjust"] is False, "raw plane must pull unadjusted prices"
    assert a.group == "china_stocks_raw" and a.group != "china_stocks"
    assert a.overwrite_overlap is False, "raw prints are final — plain append-only merge"
    assert set(frames) == {"600519.SS", "000001.SZ"}
    for df in frames.values():
        assert list(df.columns) == ["close", "high", "low", "volume"]


def test_raw_and_adjusted_planes_do_not_share_a_store_group():
    from collectors.china_stock_raw import ChinaStockRawPriceAdapter
    from collectors.china_stock_prices import ChinaStockPriceAdapter
    assert ChinaStockRawPriceAdapter.group != ChinaStockPriceAdapter.group
    # adjusted plane keeps the seam-free re-adjust; raw plane does not
    assert ChinaStockPriceAdapter.overwrite_overlap is True
    assert ChinaStockRawPriceAdapter.overwrite_overlap is False


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
