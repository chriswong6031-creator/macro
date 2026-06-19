"""Collector-side tests for collectors/china_fundamentals.py.

Guards _full_universe, which feeds the `--all` widen. members.parquet is
ticker-INDEXED (index.name == "ticker") with name/sector/mktcap COLUMNS — the old
`df.columns[0]` fallback returned the NAME column, so the widen fetched company
names as akshare symbols and stored nothing (a silent no-op that froze China
coverage at the high-value subset).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from collectors import china_fundamentals as cf  # noqa: E402


def test_full_universe_reads_ticker_index(tmp_path, monkeypatch):
    # exactly the real shape: ticker as the INDEX, name/sector as columns
    df = pd.DataFrame(
        {"name": ["Kweichow Moutai / 贵州茅台", "Ping An Bank / 平安银行"],
         "sector": ["Staples", "Financials"], "mktcap_yi": [21000.0, 2200.0]},
        index=pd.Index(["600519.SS", "000001.SZ"], name="ticker"))
    d = tmp_path / "china_search"
    d.mkdir(parents=True)
    df.to_parquet(d / "members.parquet")
    monkeypatch.setattr(cf.config, "data_dir", lambda: tmp_path)

    uni = cf._full_universe()
    # the TICKERS (sorted), never the company-name column
    assert uni == ["000001.SZ", "600519.SS"]
    assert all(t.endswith((".SS", ".SZ")) for t in uni)


def test_full_universe_prefers_explicit_ticker_column(tmp_path, monkeypatch):
    # if a future members.parquet carries an explicit `ticker` column, use it
    df = pd.DataFrame({"ticker": ["000002.SZ", "600000.SS"], "name": ["A", "B"]})
    d = tmp_path / "china_search"
    d.mkdir(parents=True)
    df.to_parquet(d / "members.parquet")
    monkeypatch.setattr(cf.config, "data_dir", lambda: tmp_path)

    assert cf._full_universe() == ["000002.SZ", "600000.SS"]


def test_full_universe_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(cf.config, "data_dir", lambda: tmp_path)
    assert cf._full_universe() == []
