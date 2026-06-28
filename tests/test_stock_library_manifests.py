"""Regression guards for single-stock search library manifests."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts import build_china_library as bcl
from scripts import build_hk_library as bhl


def test_verified_index_drops_rows_without_detail_json(tmp_path: Path):
    out = tmp_path / "chinastockdata"
    out.mkdir()
    (out / "600519.SS.json").write_text("{}")

    verified = bcl._write_verified_index(out, [
        {"t": "600519.SS", "n": "Kweichow Moutai"},
        {"t": "300131.SZ", "n": "Yitoa"},
    ])

    assert verified == [{"t": "600519.SS", "n": "Kweichow Moutai"}]
    assert json.loads((out / "index.json").read_text()) == verified


def test_hk_universe_prefers_deep_search_panel(tmp_path: Path, monkeypatch):
    dd = tmp_path / "data"
    (dd / "hk_breadth").mkdir(parents=True)
    (dd / "hk_search").mkdir(parents=True)

    shallow_idx = pd.date_range("2026-01-01", periods=2, freq="B")
    deep_idx = pd.date_range("2024-01-01", periods=400, freq="B")
    pd.DataFrame({"9999.HK": [1.0, 1.1]}, index=shallow_idx).to_parquet(
        dd / "hk_breadth" / "_closes_cache.parquet")
    pd.DataFrame({"9999.HK": range(400)}, index=deep_idx).to_parquet(
        dd / "hk_search" / "closes_deep.parquet")
    pd.DataFrame({"name": ["NetEase"], "sector": ["Technology"]},
                 index=pd.Index(["9999.HK"], name="ticker")).to_parquet(
        dd / "hk_breadth" / "constituents.parquet")

    monkeypatch.setattr(bhl.config, "data_dir", lambda: dd)
    monkeypatch.setattr(bhl.config, "load", lambda: {
        "hk": {"names": {}, "yahoo": {"indices": {}, "etf_proxies": {}}},
    })

    uni = bhl.universe()
    assert len(uni) == 1
    ticker, close, _high, name, sector = uni[0]
    assert (ticker, name, sector) == ("9999.HK", "NetEase", "Technology")
    assert len(close.dropna()) == 400
