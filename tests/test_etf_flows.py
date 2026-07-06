"""tests/test_etf_flows.py — unit tests for engine/etf_flows.py."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from engine.etf_flows import (
    _derive_flow,
    flows_wide,
    load_proxy,
    proxy_json,
    rebuild,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_so_file(tmp_dir: Path, ticker: str, rows: list[dict]) -> None:
    df = pd.DataFrame(rows)
    df.index = pd.to_datetime(df.pop("date"))
    df.index.name = "date"
    df.to_parquet(tmp_dir / f"{ticker}.parquet")


def _minimal_rows(n: int = 5) -> list[dict]:
    """n rows of synthetic SO data starting 2026-06-02."""
    base = pd.Timestamp("2026-06-02")
    rows = []
    for i in range(n):
        nav = 100.0 + i
        aum_mn = 1000.0 + i * 10
        rows.append({
            "date": base + pd.Timedelta(days=i),
            "nav": nav,
            "aum_mn": aum_mn,
            "so_mn": aum_mn / nav,
        })
    return rows


# ── _derive_flow ──────────────────────────────────────────────────────────────

def test_derive_flow_first_row_nan():
    df = pd.DataFrame(
        {"nav": [100.0, 101.0], "so_mn": [10.0, 11.0]},
        index=pd.to_datetime(["2026-06-02", "2026-06-03"]),
    )
    result = _derive_flow(df)
    assert pd.isna(result.iloc[0]), "first row must be NaN (no prior day)"
    # day-2: delta_so = 1.0, nav = 101.0 → flow = 101.0
    assert abs(result.iloc[1] - 101.0) < 1e-6


def test_derive_flow_negative_redemption():
    df = pd.DataFrame(
        {"nav": [100.0, 100.0], "so_mn": [10.0, 9.5]},
        index=pd.to_datetime(["2026-06-02", "2026-06-03"]),
    )
    result = _derive_flow(df)
    assert result.iloc[1] < 0, "outflow should be negative"


# ── flows_wide ────────────────────────────────────────────────────────────────

def test_flows_wide_returns_none_when_no_files(tmp_path):
    # Empty tickers → no files → None regardless of path
    result = flows_wide(tickers=(), _flows_dir=tmp_path)
    assert result is None


def test_flows_wide_correct_columns(tmp_path):
    for t in ("XLK", "XLF"):
        _make_so_file(tmp_path, t, _minimal_rows(3))

    # _flows_dir injection bypasses the sponsors path and reads synthetic files
    result = flows_wide(tickers=("XLK", "XLF"), _flows_dir=tmp_path)

    assert result is not None
    assert "XLK_flow_mn" in result.columns
    assert "XLF_flow_mn" in result.columns
    assert result.index.name == "date"
    # First row of each should be NaN (diff); remaining 2 are values
    assert result["XLK_flow_mn"].isna().sum() == 1


# ── rebuild ───────────────────────────────────────────────────────────────────

def test_rebuild_creates_parquet(tmp_path):
    for t in ("XLK", "XLF"):
        _make_so_file(tmp_path, t, _minimal_rows(4))
    proxy_path = tmp_path / "etf_flow_proxy.parquet"

    # flows_dir=tmp_path triggers test-injection path in flows_wide()
    out = rebuild(tickers=("XLK", "XLF"), flows_dir=tmp_path, proxy_path=proxy_path)

    assert out is not None
    assert proxy_path.exists()
    df = pd.read_parquet(proxy_path)
    assert "XLK_flow_mn" in df.columns
    assert len(df) == 4


def test_rebuild_idempotent(tmp_path):
    for t in ("XLK",):
        _make_so_file(tmp_path, t, _minimal_rows(3))
    proxy_path = tmp_path / "etf_flow_proxy.parquet"

    rebuild(tickers=("XLK",), flows_dir=tmp_path, proxy_path=proxy_path)
    # second run
    rebuild(tickers=("XLK",), flows_dir=tmp_path, proxy_path=proxy_path)

    df = pd.read_parquet(proxy_path)
    assert len(df) == 3, "idempotent rebuild must not duplicate rows"


def test_rebuild_returns_none_when_no_data(tmp_path):
    proxy_path = tmp_path / "etf_flow_proxy.parquet"
    out = rebuild(tickers=(), flows_dir=tmp_path, proxy_path=proxy_path)
    assert out is None


# ── proxy_json ────────────────────────────────────────────────────────────────

def _write_proxy(tmp_path: Path, n: int = 5) -> Path:
    proxy_path = tmp_path / "etf_flow_proxy.parquet"
    rows = _minimal_rows(n)
    for t in ("XLK", "XLF"):
        _make_so_file(tmp_path, t, rows)
    rebuild(tickers=("XLK", "XLF"), flows_dir=tmp_path, proxy_path=proxy_path)
    return proxy_path


def test_proxy_json_structure(tmp_path):
    proxy_path = _write_proxy(tmp_path, n=5)
    result = proxy_json(proxy_path=proxy_path)
    assert result is not None
    assert result["label"] == "creation/redemption proxy"
    assert "asof" in result
    assert "depth" in result
    assert "funds" in result
    assert "net_flow_1d" in result
    tickers = {f["ticker"] for f in result["funds"]}
    assert "XLK" in tickers
    assert "XLF" in tickers


def test_proxy_json_none_when_no_file(tmp_path):
    result = proxy_json(proxy_path=tmp_path / "missing.parquet")
    assert result is None


def test_proxy_json_flow_signs(tmp_path):
    """Net inflow when so_mn grows each day."""
    rows = []
    base = pd.Timestamp("2026-06-02")
    for i in range(3):
        nav = 100.0
        so = 10.0 + i  # growing SO → net creation
        rows.append({"date": base + pd.Timedelta(days=i),
                     "nav": nav, "aum_mn": so * nav, "so_mn": so})
    proxy_path = tmp_path / "etf_flow_proxy.parquet"

    _make_so_file(tmp_path, "XLK", rows)
    rebuild(tickers=("XLK",), flows_dir=tmp_path, proxy_path=proxy_path)

    result = proxy_json(proxy_path=proxy_path)
    assert result is not None
    xlk = next(f for f in result["funds"] if f["ticker"] == "XLK")
    assert xlk["flow_1d"] > 0, "growing SO → positive flow (creation)"
