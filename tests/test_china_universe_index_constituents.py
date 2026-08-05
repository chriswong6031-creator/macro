"""Guard `collectors.china_universe._index_constituents` — the CSI index union.

The search universe unions CSI 300 + CSI 1000 into the Sina top-N. Sourced from
`ak.index_stock_cons`, that union shipped SHORT and silent: the 1000-row CSI 1000
frame carries only 772 unique codes (288 of 300 for CSI 300, measured 2026-08-04),
dropping 228 real constituents — 002716.SZ 湖南白银 among them — while the collector
logged `len(df)` = 1000 as if coverage were full and deduplicated the shortfall away
downstream. Nothing tested this function, so the gap shipped dark.

`ak.index_stock_cons_csindex` (official CSIndex) is the fix, and its columns are the
trap these tests exist to pin: the frame carries 指数代码/指数名称 (the INDEX's own code
and name) alongside 成分券代码/成分券名称, so the old "代码"/"名称" substring scan matches
the index columns FIRST and maps every row to one bogus ticker. No network.
"""
from __future__ import annotations

import logging
import sys
import types
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors import china_universe as cu  # noqa: E402

CSINDEX_COLS = ["日期", "指数代码", "指数名称", "指数英文名称", "成分券代码",
                "成分券名称", "成分券英文名称", "交易所", "交易所英文名称"]

# The live 000852 frame's own index code — a valid 6-digit code that _code_to_ticker
# maps to 000852.SZ, so a substring-scan column pick is DETECTABLE in the output
# rather than merely plausible. Never reused as a constituent code below.
INDEX_CODE = "000852"


def _csindex_frame(codes: list[str], names: list[str] | None = None) -> pd.DataFrame:
    """A CSIndex-shaped frame (all nine live columns, index columns populated)."""
    names = names or [f"名称{c}" for c in codes]
    n = len(codes)
    return pd.DataFrame({
        "日期": ["2026-08-04"] * n,
        "指数代码": [INDEX_CODE] * n,
        "指数名称": ["中证1000"] * n,
        "指数英文名称": ["CSI 1000"] * n,
        "成分券代码": list(codes),
        "成分券名称": list(names),
        "成分券英文名称": [f"EN {c}" for c in codes],
        "交易所": ["深圳证券交易所"] * n,
        "交易所英文名称": ["Shenzhen Stock Exchange"] * n,
    })[CSINDEX_COLS]


def _legacy_frame(codes: list[str]) -> pd.DataFrame:
    """`ak.index_stock_cons` shape: ['品种代码','品种名称','纳入日期']."""
    return pd.DataFrame({"品种代码": list(codes),
                         "品种名称": [f"旧{c}" for c in codes],
                         "纳入日期": ["2026-06-13"] * len(codes)})


def _install_ak(monkeypatch, *, csindex=None, legacy=None) -> None:
    """Inject a fake `akshare` — the collector imports it lazily inside the function."""
    def _absent(*a, **kw):
        raise AssertionError("this endpoint must not be called")
    mod = types.ModuleType("akshare")
    mod.index_stock_cons_csindex = csindex or _absent
    mod.index_stock_cons = legacy or _absent
    monkeypatch.setitem(sys.modules, "akshare", mod)


@pytest.fixture()
def adapter():
    return cu.ChinaUniverseAdapter()


def test_constituents_come_from_the_constituent_columns(monkeypatch, adapter):
    """THE mutation test: 成分券代码/成分券名称 by name, never a 代码/名称 substring scan.

    A scan picks 指数代码 ('000852' → 000852.SZ) and 指数名称 ('中证1000') for EVERY row.
    The legacy endpoint is wired to explode, so preferring csindex is pinned too."""
    _install_ak(monkeypatch, csindex=lambda symbol: _csindex_frame(
        ["600519", "002716", "000001"], ["贵州茅台", "湖南白银", "平安银行"]))

    rows = adapter._index_constituents([INDEX_CODE])

    assert [r["ticker"] for r in rows] == ["600519.SS", "002716.SZ", "000001.SZ"]
    assert [r["name_zh"] for r in rows] == ["贵州茅台", "湖南白银", "平安银行"]
    assert "000852.SZ" not in {r["ticker"] for r in rows}, "index code leaked in as a constituent"
    assert "中证1000" not in {r["name_zh"] for r in rows}, "index name leaked in as a constituent"


def test_duplicate_codes_collapse_to_one_entry(monkeypatch, adapter):
    """The exact shape of the legacy defect: repeated codes must not inflate the union."""
    _install_ak(monkeypatch, csindex=lambda symbol: _csindex_frame(
        ["002716", "600519", "002716", "600519"]))

    tickers = [r["ticker"] for r in adapter._index_constituents([INDEX_CODE])]

    assert tickers == ["002716.SZ", "600519.SS"]


def test_beijing_codes_are_dropped(monkeypatch, adapter):
    _install_ak(monkeypatch, csindex=lambda symbol: _csindex_frame(
        ["830799", "430418", "688508", "300061"]))

    tickers = [r["ticker"] for r in adapter._index_constituents([INDEX_CODE])]

    assert tickers == ["688508.SS", "300061.SZ"]


def test_logged_count_is_the_union_not_the_row_count(monkeypatch, adapter, caplog):
    """The old log printed len(df), so a 1000-row/772-code frame read as full coverage."""
    _install_ak(monkeypatch, csindex=lambda symbol: _csindex_frame(
        ["002716", "002716", "830799", "600519"]))

    with caplog.at_level(logging.INFO, logger="collectors.china_universe"):
        adapter._index_constituents([INDEX_CODE])

    line = next(m for m in caplog.messages if "CSI index" in m)
    assert "2 constituents" in line and "4" in line, line


def test_falls_back_to_legacy_endpoint_when_csindex_fails(monkeypatch, adapter, caplog):
    """Old akshare (no csindex attr) or a CSIndex outage still yields constituents,
    with the incompleteness said out loud."""
    def _boom(symbol):
        raise RuntimeError("csindex down")

    _install_ak(monkeypatch, csindex=_boom,
                legacy=lambda symbol: _legacy_frame(["600519", "002716"]))

    with caplog.at_level(logging.WARNING, logger="collectors.china_universe"):
        rows = adapter._index_constituents([INDEX_CODE])

    assert [r["ticker"] for r in rows] == ["600519.SS", "002716.SZ"]
    assert [r["name_zh"] for r in rows] == ["旧600519", "旧002716"]
    assert any("KNOWN-INCOMPLETE" in m for m in caplog.messages)


def test_one_failing_index_does_not_block_the_other(monkeypatch, adapter):
    """Both endpoints dead for 000300; 000852 must still come back (best-effort)."""
    def _csindex(symbol):
        if symbol == "000300":
            raise RuntimeError("csindex down")
        return _csindex_frame(["002716"])

    def _legacy(symbol):
        raise RuntimeError("legacy down")

    _install_ak(monkeypatch, csindex=_csindex, legacy=_legacy)

    rows = adapter._index_constituents(["000300", "000852"])

    assert [r["ticker"] for r in rows] == ["002716.SZ"]


def test_missing_akshare_is_not_fatal(monkeypatch, adapter):
    monkeypatch.setitem(sys.modules, "akshare", None)   # `import akshare` -> ImportError
    assert adapter._index_constituents([INDEX_CODE]) == []
