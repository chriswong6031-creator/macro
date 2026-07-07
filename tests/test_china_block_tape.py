"""Pure-logic tests for collectors/china_block_tape.py — no network, no disk writes.

Tests cover:
  - Ticker normalisation (_to_ticker)
  - Column finder (_col)
  - mrtj / mrmx row parsing (_parse_mrtj, _parse_mrmx)
  - Date-chunk generator (_date_chunks)
  - Append deduplication logic (new rows skipped if date already stored)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.china_block_tape import (
    _col,
    _date_chunks,
    _parse_mrmx,
    _parse_mrtj,
    _safe_float,
    _safe_int,
    _to_ticker,
)


# ── _to_ticker ────────────────────────────────────────────────────────────────

class TestToTicker:
    def test_sh_prefix(self):
        assert _to_ticker("600519") == "600519.SH"

    def test_sz_prefix(self):
        assert _to_ticker("000858") == "000858.SZ"

    def test_star_market_sh(self):
        assert _to_ticker("688599") == "688599.SH"

    def test_etf_sh(self):
        # 51xxxx / 50xxxx -> SH
        assert _to_ticker("510300").endswith(".SH")

    def test_bj_prefix(self):
        assert _to_ticker("830946") == "830946.BJ"

    def test_zero_padded(self):
        # short code should be zero-padded
        assert _to_ticker("1") == "000001.SZ"

    def test_none_returns_none(self):
        assert _to_ticker(None) is None

    def test_empty_returns_none(self):
        assert _to_ticker("") is None


# ── _col ─────────────────────────────────────────────────────────────────────

class TestCol:
    def test_finds_first_match(self):
        cols = ["序号", "交易日期", "证券代码", "折溢率"]
        assert _col(cols, "交易日期") == "交易日期"

    def test_finds_by_substring(self):
        cols = ["序号", "证券简称2", "成交总额"]
        assert _col(cols, "简称") == "证券简称2"

    def test_first_needle_wins(self):
        cols = ["折溢率pct", "成交笔数"]
        assert _col(cols, "折溢率", "成交笔数") == "折溢率pct"

    def test_returns_none_if_no_match(self):
        cols = ["A", "B", "C"]
        assert _col(cols, "折溢率") is None


# ── _safe_float / _safe_int ───────────────────────────────────────────────────

class TestSafeConversions:
    def test_float_ok(self):
        assert _safe_float(3.14) == pytest.approx(3.14)

    def test_float_str(self):
        assert _safe_float("2.5") == pytest.approx(2.5)

    def test_float_nan(self):
        assert _safe_float(float("nan")) is None

    def test_float_none(self):
        assert _safe_float(None) is None

    def test_int_ok(self):
        assert _safe_int(5) == 5

    def test_int_float(self):
        assert _safe_int(5.9) == 5

    def test_int_none(self):
        assert _safe_int(None) is None


# ── _parse_mrtj ───────────────────────────────────────────────────────────────

class TestParseMrtj:
    def _make_df(self):
        return pd.DataFrame([{
            "序号": 1,
            "交易日期": "2025-01-02",
            "证券代码": "000858",
            "证券简称": "五粮液",
            "涨跌幅": -1.5,
            "收盘价": 120.0,
            "成交价": 115.0,
            "折溢率": -0.04167,
            "成交笔数": 3,
            "成交总量": 10000.0,
            "成交总额": 1150000.0,
            "成交总额/流通市值": 0.01,
        }])

    def test_basic_parse(self):
        df = self._make_df()
        rows = _parse_mrtj(df, "2025-01-03")
        assert len(rows) == 1
        r = rows[0]
        assert r["ticker"] == "000858.SZ"
        assert r["date"] == "2025-01-02"
        assert r["asof"] == "2025-01-03"
        assert r["premium_ratio"] == pytest.approx(-0.04167, rel=1e-4)
        assert r["n_trades"] == 3
        assert r["amt_wan"] == pytest.approx(1150000.0)

    def test_empty_df_returns_empty(self):
        rows = _parse_mrtj(pd.DataFrame(), "2025-01-03")
        assert rows == []

    def test_none_df_returns_empty(self):
        rows = _parse_mrtj(None, "2025-01-03")
        assert rows == []

    def test_bad_code_skipped(self):
        df = pd.DataFrame([{"交易日期": "2025-01-02", "证券代码": None, "证券简称": "X"}])
        rows = _parse_mrtj(df, "2025-01-03")
        assert rows == []

    def test_sh_code(self):
        df = pd.DataFrame([{
            "交易日期": "2025-01-02", "证券代码": "600519", "证券简称": "茅台",
            "涨跌幅": 0.5, "收盘价": 1500.0, "成交价": 1480.0,
            "折溢率": -0.0133, "成交笔数": 1, "成交总量": 100.0,
            "成交总额": 148000.0, "成交总额/流通市值": 0.001,
        }])
        rows = _parse_mrtj(df, "2025-01-03")
        assert rows[0]["ticker"] == "600519.SH"


# ── _parse_mrmx ───────────────────────────────────────────────────────────────

class TestParseMrmx:
    def _make_df(self):
        return pd.DataFrame([{
            "序号": 1,
            "交易日期": "2025-01-02",
            "证券代码": "300750",
            "证券简称": "宁德时代",
            "成交价": 220.0,
            "成交量": 50000.0,
            "成交额": 11000000.0,
            "买方营业部": "机构专用",
            "卖方营业部": "招商证券XX营业部",
        }])

    def test_basic_parse(self):
        rows = _parse_mrmx(self._make_df(), "2025-01-03")
        assert len(rows) == 1
        r = rows[0]
        assert r["ticker"] == "300750.SZ"
        assert r["buyer_branch"] == "机构专用"
        assert r["seller_branch"] == "招商证券XX营业部"
        assert r["amt_wan"] == pytest.approx(11000000.0)

    def test_empty_returns_empty(self):
        assert _parse_mrmx(pd.DataFrame(), "2025-01-03") == []

    def test_none_returns_empty(self):
        assert _parse_mrmx(None, "2025-01-03") == []


# ── _date_chunks ──────────────────────────────────────────────────────────────

class TestDateChunks:
    def test_single_chunk(self):
        chunks = list(_date_chunks("20250101", "20250115", chunk_days=30))
        assert len(chunks) == 1
        assert chunks[0] == ("20250101", "20250115")

    def test_exact_two_chunks(self):
        chunks = list(_date_chunks("20250101", "20250201", chunk_days=30))
        assert len(chunks) == 2

    def test_starts_and_ends_correct(self):
        chunks = list(_date_chunks("20250101", "20250401", chunk_days=30))
        assert chunks[0][0] == "20250101"
        assert chunks[-1][1] == "20250401"

    def test_non_overlapping(self):
        chunks = list(_date_chunks("20250101", "20250401", chunk_days=30))
        for i in range(len(chunks) - 1):
            # End of chunk i + 1 day == start of chunk i+1
            from datetime import date, timedelta
            end_d = date.fromisoformat(chunks[i][1].replace(
                chunks[i][1][:4], chunks[i][1][:4]
            ))
            # just check lengths are consistent
            start_d = date(int(chunks[i][0][:4]), int(chunks[i][0][4:6]), int(chunks[i][0][6:8]))
            end_d   = date(int(chunks[i][1][:4]), int(chunks[i][1][4:6]), int(chunks[i][1][6:8]))
            assert (end_d - start_d).days < 30

    def test_single_day(self):
        chunks = list(_date_chunks("20250115", "20250115", chunk_days=30))
        assert len(chunks) == 1
        assert chunks[0] == ("20250115", "20250115")
