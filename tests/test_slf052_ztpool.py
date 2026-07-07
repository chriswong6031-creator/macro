"""Tests for china_zt_pool collector logic — SLF-052.

Pure-function tests; NO network, NO disk I/O beyond tiny in-memory fixtures.
"""
from __future__ import annotations

import io
import pandas as pd
import pytest

# ── _drip helpers ─────────────────────────────────────────────────────────────

from collectors._drip import append_snapshot, latest_snapshot


def _tmp_path(tmp_path, name="pool.parquet"):
    return tmp_path / name


def test_latest_snapshot_returns_newest_date():
    df = pd.DataFrame({
        "date": ["2026-06-15", "2026-06-15", "2026-06-16", "2026-06-16"],
        "ticker": ["A.SZ", "B.SZ", "A.SZ", "B.SZ"],
        "value": [1, 2, 3, 4],
    })
    result = latest_snapshot(df, "date")
    assert list(result["date"].unique()) == ["2026-06-16"]
    assert len(result) == 2


def test_latest_snapshot_passthrough_on_missing_col():
    df = pd.DataFrame({"ticker": ["A", "B"]})
    result = latest_snapshot(df, "date")
    assert result is df


def test_append_snapshot_creates_file(tmp_path):
    path = _tmp_path(tmp_path)
    rows = [
        {"ticker": "000001.SZ", "date": "2026-06-15", "consec_boards": 1},
        {"ticker": "000002.SZ", "date": "2026-06-15", "consec_boards": 2},
    ]
    n = append_snapshot(path, rows, date_col="date")
    assert n == 2
    df = pd.read_parquet(path)
    assert len(df) == 2


def test_append_snapshot_idempotent_same_day(tmp_path):
    """Re-appending the same session rows must not duplicate."""
    path = _tmp_path(tmp_path)
    rows = [{"ticker": "000001.SZ", "date": "2026-06-15", "consec_boards": 1}]
    append_snapshot(path, rows, date_col="date")
    append_snapshot(path, rows, date_col="date")  # second time — same session
    df = pd.read_parquet(path)
    assert len(df) == 1


def test_append_snapshot_corrects_same_day(tmp_path):
    """A same-day re-collect with updated data must correct, not duplicate."""
    path = _tmp_path(tmp_path)
    rows_v1 = [{"ticker": "000001.SZ", "date": "2026-06-15", "consec_boards": 1}]
    rows_v2 = [{"ticker": "000001.SZ", "date": "2026-06-15", "consec_boards": 3}]
    append_snapshot(path, rows_v1, date_col="date")
    append_snapshot(path, rows_v2, date_col="date")
    df = pd.read_parquet(path)
    assert len(df) == 1
    assert int(df.iloc[0]["consec_boards"]) == 3


def test_append_snapshot_accumulates_sessions(tmp_path):
    """Different session dates accumulate correctly."""
    path = _tmp_path(tmp_path)
    for date in ["2026-06-15", "2026-06-16", "2026-06-17"]:
        rows = [
            {"ticker": "000001.SZ", "date": date, "consec_boards": 1},
            {"ticker": "000002.SZ", "date": date, "consec_boards": 1},
        ]
        append_snapshot(path, rows, date_col="date")
    df = pd.read_parquet(path)
    assert len(df) == 6  # 3 sessions × 2 tickers
    assert sorted(df["date"].unique()) == ["2026-06-15", "2026-06-16", "2026-06-17"]


# ── collector _parse logic ─────────────────────────────────────────────────────

from collectors.china_zt_pool import _parse, _col, _stored_sessions


def test_col_returns_first_match():
    cols = ["代码", "名称", "连板数", "封板资金"]
    assert _col(cols, "代码") == "代码"
    assert _col(cols, "连板") == "连板数"
    assert _col(cols, "missing") is None


def test_parse_basic():
    df = pd.DataFrame({
        "代码": ["000001", "600001"],
        "名称": ["A公司", "B公司"],
        "连板数": [2, 1],
        "封板资金": [5e8, 1e8],
        "炸板次数": [0, 1],
        "换手率": [5.0, 3.0],
        "所属行业": ["银行", "科技"],
    })
    rows = _parse("20260615", df, "2026-06-15")
    assert len(rows) == 2
    # SH/SZ routing
    tickers = {r["ticker"] for r in rows}
    assert "000001.SZ" in tickers
    assert "600001.SS" in tickers  # Shanghai suffix is .SS per china_analyst.to_ticker
    # date field is ISO
    assert all(r["date"] == "2026-06-15" for r in rows)
    # seal_fund_yi conversion
    b_row = next(r for r in rows if r["ticker"] == "600001.SS")
    assert abs(b_row["seal_fund_yi"] - 1.0) < 0.01


def test_parse_empty_df_returns_empty():
    df = pd.DataFrame(columns=["代码", "名称"])
    rows = _parse("20260615", df, "2026-06-15")
    assert rows == []


def test_stored_sessions_empty_on_nonexistent(tmp_path, monkeypatch):
    """_stored_sessions returns empty set when file missing."""
    import collectors.china_zt_pool as mod
    original_out = mod.OUT
    mod.OUT = tmp_path / "nonexistent.parquet"
    try:
        result = mod._stored_sessions()
        assert result == set()
    finally:
        mod.OUT = original_out
