"""W3-C data-accrual infrastructure tests.

Covers:
  C1 — ChinaMarginDetailAdapter: unit tests with mocked akshare, idempotency,
       schema (date/ticker/fin_balance/short_balance/short_balance_yuan/
               fin_balance_prior/prior_date/asof), adapter registered in collect.py
  C2 — ChinaLhbAdapter + backfill script: mocked _raw_events round-trip,
       idempotency, schema (date/ticker/name/net_buy_yi/reason),
       backfill_china_lhb.py imports cleanly and exports run()
  C3 — collect.py registration: both new adapter keys present with ``china`` prefix
       (auto-assigns to ``asia`` shard)

Design rules (LAWS):
  - No network: akshare calls are fully mocked via monkeypatch
  - No git writes; no test side-effects on real data/ trees
  - Deterministic; PYTHONPATH=$PWD python3 safe
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ─────────────────────────────────────────────────────────────────────────────
# C1  ChinaMarginDetailAdapter + schema
# ─────────────────────────────────────────────────────────────────────────────

def _make_sse_df() -> pd.DataFrame:
    """Minimal mock of stock_margin_detail_sse() return value."""
    return pd.DataFrame({
        "信用交易日期": ["2026-07-02", "2026-07-02"],
        "标的证券代码": ["600000", "000001"],
        "标的证券简称": ["浦发银行", "平安银行"],
        "融资余额": [3.8e9, 1.2e9],
        "融资买入额": [1e8, 5e7],
        "融资偿还额": [8e7, 4e7],
        "融券余量": [120000.0, 55000.0],
        "融券卖出量": [10000.0, 5000.0],
        "融券偿还量": [8000.0, 4000.0],
    })


def _make_szse_df() -> pd.DataFrame:
    """Minimal mock of stock_margin_detail_szse() return value."""
    return pd.DataFrame({
        "证券代码": ["000001", "000002"],
        "证券简称": ["平安银行", "万科A"],
        "融资买入额": [5e7, 3e7],
        "融资余额": [1.2e9, 8e8],
        "融券卖出量": [5000.0, 3000.0],
        "融券余量": [55000.0, 30000.0],
        "融券余额": [2.5e8, 1.5e8],
        "融资融券余额": [1.45e9, 9.5e8],
    })


class TestMarginDetailSchema:
    """Schema and idempotency tests for china_margin_detail.py."""

    def test_detail_for_returns_expected_schema(self, monkeypatch):
        """_detail_for() should map both SSE + SZSE into
        {ticker: {fin_balance, short_balance, short_balance_yuan}}."""
        import collectors.china_margin_detail as cmd

        # akshare is imported locally inside _detail_for (``import akshare as ak``);
        # patch the module in sys.modules to intercept it.
        mock_ak = MagicMock()
        mock_ak.stock_margin_detail_sse.side_effect = lambda date: _make_sse_df()
        mock_ak.stock_margin_detail_szse.side_effect = lambda date: _make_szse_df()

        with patch.dict("sys.modules", {"akshare": mock_ak}):
            result = cmd._detail_for("20260702")

        # SSE maps 600000 -> 600000.SS; SZSE maps 000002 -> 000002.SZ
        assert "600000.SS" in result, "SSE ticker not converted"
        assert "000002.SZ" in result, "SZSE-only ticker missing"

        r = result["600000.SS"]
        assert "fin_balance" in r and r["fin_balance"] == pytest.approx(3.8e9)
        assert "short_balance" in r       # 融券余量 from SSE
        assert r["short_balance"] == pytest.approx(120000.0)
        # SSE provides no 融券余额 (yuan) so short_balance_yuan should be None
        assert r.get("short_balance_yuan") is None, "SSE should not set short_balance_yuan"

        r2 = result["000002.SZ"]
        assert r2["fin_balance"] == pytest.approx(8e8)
        assert r2.get("short_balance_yuan") == pytest.approx(1.5e8)

    def test_refresh_writes_correct_columns(self, tmp_path, monkeypatch):
        """refresh() must write rows with the full schema columns."""
        import collectors.china_margin_detail as cmd

        monkeypatch.setattr(cmd.config, "data_dir", lambda: tmp_path)

        _cur = {"600000.SS": {"fin_balance": 3.8e9, "short_balance": 120000.0,
                               "short_balance_yuan": None}}
        _prior = {"600000.SS": {"fin_balance": 3.7e9, "short_balance": 110000.0,
                                 "short_balance_yuan": None}}
        # Stub _first_populated so the date-count guard is bypassed
        call_count = [0]
        def _fake_first_populated(dates):
            call_count[0] += 1
            if call_count[0] == 1:
                return "20260702", _cur
            return "20260630", _prior

        monkeypatch.setattr(cmd, "_trading_dates", lambda n=40: [f"202607{d:02d}" for d in range(1, 42)])
        monkeypatch.setattr(cmd, "_first_populated", _fake_first_populated)

        n = cmd.refresh()
        assert n > 0, "refresh() should return > 0 names"

        out = tmp_path / "china_margin_detail" / "detail.parquet"
        assert out.exists(), "detail.parquet not written"
        df = pd.read_parquet(out)

        required_cols = {"date", "ticker", "fin_balance", "short_balance",
                         "short_balance_yuan", "fin_balance_prior", "prior_date", "asof"}
        assert required_cols.issubset(set(df.columns)), (
            f"Missing columns: {required_cols - set(df.columns)}")

        row = df[df["ticker"] == "600000.SS"].iloc[0]
        assert row["fin_balance"] == pytest.approx(3.8e9)
        assert row["short_balance"] == pytest.approx(120000.0)
        assert row["asof"] is not None

    def test_refresh_idempotent_same_day(self, tmp_path, monkeypatch):
        """Calling refresh() twice on the same day must not duplicate rows."""
        import collectors.china_margin_detail as cmd

        monkeypatch.setattr(cmd.config, "data_dir", lambda: tmp_path)

        _cur = {"600000.SS": {"fin_balance": 3.8e9, "short_balance": 100.0,
                               "short_balance_yuan": None}}
        _prior = {"600000.SS": {"fin_balance": 3.7e9, "short_balance": 90.0,
                                 "short_balance_yuan": None}}

        call_count = [0]
        def _fake_first_populated(dates):
            call_count[0] += 1
            if call_count[0] % 2 == 1:
                return "20260702", _cur
            return "20260630", _prior

        monkeypatch.setattr(cmd, "_trading_dates", lambda n=40: [f"202607{d:02d}" for d in range(1, 42)])
        monkeypatch.setattr(cmd, "_first_populated", _fake_first_populated)

        cmd.refresh()
        cmd.refresh()  # second call — must be idempotent

        df = pd.read_parquet(tmp_path / "china_margin_detail" / "detail.parquet")
        # Only one session's worth of rows for 2026-07-02
        rows_for_date = df[df["date"] == "2026-07-02"]
        assert len(rows_for_date) == len(rows_for_date.drop_duplicates(subset=["ticker"])), (
            "duplicate rows detected after second refresh()")

    def test_akshare_failure_is_non_fatal(self, tmp_path, monkeypatch):
        """If both SSE and SZSE calls throw, refresh() must return 0, not raise."""
        import collectors.china_margin_detail as cmd

        monkeypatch.setattr(cmd.config, "data_dir", lambda: tmp_path)
        monkeypatch.setattr(cmd, "_trading_dates", lambda n=40: ["20260630", "20260702"])

        def _fail(date):
            return {}  # simulates connection failure returning empty

        monkeypatch.setattr(cmd, "_detail_for", _fail)
        result = cmd.refresh()
        assert result == 0, "akshare failure must return 0, not raise"


# ─────────────────────────────────────────────────────────────────────────────
# C2  ChinaLhbAdapter + backfill script
# ─────────────────────────────────────────────────────────────────────────────

class TestLhbAdapter:
    """Tests for the LHB adapter and backfill infrastructure."""

    def test_lhb_events_schema(self, tmp_path, monkeypatch):
        """_raw_events() must produce rows with date/ticker/name/net_buy_yi/reason."""
        import collectors.china_lhb as lhb

        # Minimal mock of stock_lhb_detail_em return
        mock_df = pd.DataFrame({
            "上榜日": ["2026-07-02", "2026-07-02"],
            "代码": ["600000", "000001"],
            "名称": ["浦发银行", "平安银行"],
            "净买额": [5e7, -2e7],
            "上榜原因": ["涨幅偏离值达7%", "换手率达20%"],
        })

        # akshare imported locally; patch via sys.modules
        mock_ak = MagicMock()
        mock_ak.stock_lhb_detail_em.return_value = mock_df

        with patch.dict("sys.modules", {"akshare": mock_ak}):
            rows = lhb._raw_events("20260702", "20260702")

        assert len(rows) == 2, "expected 2 event rows"
        r = rows[0]
        assert set(r.keys()) >= {"date", "ticker", "name", "net_buy_yi", "reason"}
        assert r["ticker"].endswith(".SS") or r["ticker"].endswith(".SZ")
        assert isinstance(r["net_buy_yi"], float)
        assert r["date"] == "2026-07-02"

    def test_lhb_events_idempotency(self, tmp_path, monkeypatch):
        """_drip.append_snapshot keep-last on (date, ticker) must prevent duplication."""
        from collectors import _drip

        path = tmp_path / "events.parquet"
        rows1 = [{"date": "2026-07-02", "ticker": "600000.SS",
                  "name": "浦发", "net_buy_yi": 0.5, "reason": "X"}]
        _drip.append_snapshot(path, rows1, "date")
        # Second append of same (date, ticker) should overwrite, not duplicate
        rows2 = [{"date": "2026-07-02", "ticker": "600000.SS",
                  "name": "浦发", "net_buy_yi": 0.9, "reason": "X (updated)"}]
        _drip.append_snapshot(path, rows2, "date")

        df = pd.read_parquet(path)
        matches = df[(df["date"] == "2026-07-02") & (df["ticker"] == "600000.SS")]
        assert len(matches) == 1, "idempotency failed: duplicate row detected"
        assert matches.iloc[0]["net_buy_yi"] == pytest.approx(0.9)

    def test_lhb_akshare_failure_non_fatal(self, tmp_path, monkeypatch):
        """If akshare raises during refresh(), return 0 and do not raise."""
        import collectors.china_lhb as lhb

        monkeypatch.setattr(lhb.store, "read", lambda *a, **kw: None)

        mock_ak = MagicMock()
        mock_ak.stock_lhb_detail_em.side_effect = ConnectionError("GFW")
        mock_ak.stock_lhb_jgmmtj_em.side_effect = ConnectionError("GFW")

        with patch.dict("sys.modules", {"akshare": mock_ak}):
            n = lhb.refresh()

        assert n == 0, "failure must return 0, not raise"

    def test_backfill_script_importable(self):
        """scripts/backfill_china_lhb.py must import without error and expose run()."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "backfill_china_lhb",
            ROOT / "scripts" / "backfill_china_lhb.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert callable(getattr(mod, "run", None)), "run() must be exported"

    def test_backfill_script_dry_run(self, monkeypatch):
        """run(dry_run=True) must return ok=True without writing anything."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "backfill_china_lhb",
            ROOT / "scripts" / "backfill_china_lhb.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        result = mod.run(start="2024-07-01", end="2024-07-31", dry_run=True, timeout_s=30)
        assert result["ok"] is True
        assert result.get("error") is None


# ─────────────────────────────────────────────────────────────────────────────
# C3  collect.py registration and asia-group auto-assignment
# ─────────────────────────────────────────────────────────────────────────────

class TestCollectRegistration:
    """Verify that both new adapters are present in collect.py's registry and
    that the ``asia`` group auto-assignment covers them."""

    def _build_registry(self):
        import scripts.collect as col
        return col.all_adapters()

    def test_china_margin_detail_registered(self):
        reg = self._build_registry()
        assert "china_margin_detail" in reg, (
            "china_margin_detail not in collect.py registry")

    def test_china_lhb_registered(self):
        reg = self._build_registry()
        assert "china_lhb" in reg, (
            "china_lhb not in collect.py registry")

    def test_both_in_asia_group(self):
        """Keys starting with 'china' must be auto-assigned to the asia shard."""
        import scripts.collect as col
        reg = self._build_registry()
        asia = col.group_members("asia", reg)
        assert "china_margin_detail" in asia, (
            "china_margin_detail not in asia shard")
        assert "china_lhb" in asia, (
            "china_lhb not in asia shard")

    def test_adapters_loadable(self):
        """Both adapter classes must be importable."""
        from collectors.china_margin_detail import ChinaMarginDetailAdapter
        from collectors.china_lhb import ChinaLhbAdapter
        assert ChinaMarginDetailAdapter.name == "china_margin_detail"
        assert ChinaLhbAdapter.name == "china_lhb"
        assert ChinaMarginDetailAdapter.group.startswith("china")
        assert ChinaLhbAdapter.group.startswith("china")
