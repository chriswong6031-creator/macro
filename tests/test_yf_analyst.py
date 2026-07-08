"""Unit tests for collectors/yf_analyst.py.

Covers:
1. implied_upside_pct computation (positive / negative / zero denominator guard)
2. target_dispersion computation (positive / zero denominator guard)
3. Honest-null row when yfinance raises (all numeric fields None)
4. Staleness filter: fresh tickers are skipped
5. Column schema of output parquet matches expected columns
6. No network calls escape during _fetch_one (monkeypatched yfinance)
"""
from __future__ import annotations

import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.yf_analyst import (
    _COLUMNS,
    _fetch_one,
    _load_candidate_universe,
    _stale_tickers,
    _upsert_and_write,
    _days_ago_str,
)


# ---------------------------------------------------------------------------
# 1. implied_upside_pct math
# ---------------------------------------------------------------------------

class TestImpliedUpside:
    def test_positive_upside(self, monkeypatch):
        """target_mean > current_price → positive implied_upside_pct."""
        _mock_yf(monkeypatch, target_mean=110.0, current_price=100.0)
        row = _fetch_one("AAPL", "2026-07-05")
        assert row["implied_upside_pct"] == pytest.approx(10.0, rel=1e-4)

    def test_negative_upside(self, monkeypatch):
        """target_mean < current_price → negative implied_upside_pct."""
        _mock_yf(monkeypatch, target_mean=90.0, current_price=100.0)
        row = _fetch_one("AAPL", "2026-07-05")
        assert row["implied_upside_pct"] == pytest.approx(-10.0, rel=1e-4)

    def test_zero_current_price_gives_none(self, monkeypatch):
        """current_price=0 must not raise ZeroDivisionError; implied_upside_pct=None."""
        _mock_yf(monkeypatch, target_mean=100.0, current_price=0.0)
        row = _fetch_one("AAPL", "2026-07-05")
        assert row["implied_upside_pct"] is None

    def test_none_target_mean_gives_none(self, monkeypatch):
        """target_mean=None → implied_upside_pct=None."""
        _mock_yf(monkeypatch, target_mean=None, current_price=100.0)
        row = _fetch_one("AAPL", "2026-07-05")
        assert row["implied_upside_pct"] is None

    def test_none_current_price_gives_none(self, monkeypatch):
        """current_price=None → implied_upside_pct=None."""
        _mock_yf(monkeypatch, target_mean=110.0, current_price=None)
        row = _fetch_one("AAPL", "2026-07-05")
        assert row["implied_upside_pct"] is None


# ---------------------------------------------------------------------------
# 2. target_dispersion math
# ---------------------------------------------------------------------------

class TestTargetDispersion:
    def test_normal_dispersion(self, monkeypatch):
        """(high - low) / mean computed correctly."""
        _mock_yf(monkeypatch, target_mean=100.0, target_high=120.0, target_low=80.0)
        row = _fetch_one("AAPL", "2026-07-05")
        # (120 - 80) / 100 = 0.4
        assert row["target_dispersion"] == pytest.approx(0.4, rel=1e-4)

    def test_zero_target_mean_gives_none(self, monkeypatch):
        """target_mean=0 → target_dispersion=None (guard division by zero)."""
        _mock_yf(monkeypatch, target_mean=0.0, target_high=120.0, target_low=80.0)
        row = _fetch_one("AAPL", "2026-07-05")
        assert row["target_dispersion"] is None

    def test_none_high_gives_none(self, monkeypatch):
        """Missing target_high → target_dispersion=None."""
        _mock_yf(monkeypatch, target_mean=100.0, target_high=None, target_low=80.0)
        row = _fetch_one("AAPL", "2026-07-05")
        assert row["target_dispersion"] is None


# ---------------------------------------------------------------------------
# 3. Honest-null on yfinance error
# ---------------------------------------------------------------------------

class TestHonestNull:
    def test_all_none_on_exception(self, monkeypatch):
        """When yfinance raises, all numeric fields are None (honest-null row)."""
        import collectors.yf_analyst as mod
        import types

        class _BrokenTicker:
            @property
            def info(self):
                raise RuntimeError("401 rate limited")

        fake_yf = types.SimpleNamespace(Ticker=lambda t: _BrokenTicker())
        monkeypatch.setitem(sys.modules, "yfinance", fake_yf)

        row = _fetch_one("BROKEN", "2026-07-05")
        assert row["ticker"] == "BROKEN"
        assert row["target_mean"] is None
        assert row["implied_upside_pct"] is None
        assert row["target_dispersion"] is None
        assert row["recommendation"] is None
        assert row["num_analysts"] is None
        assert row["current_price"] is None
        assert row["as_of"] == "2026-07-05"
        assert row["provenance_note"] == "yfinance_info_pit_snapshot"

    def test_429_rate_limit_is_honest_null(self, monkeypatch):
        """HTTP 429 rate-limit → honest-null row (no exception propagation)."""
        import collectors.yf_analyst as mod
        import types

        class _429Ticker:
            @property
            def info(self):
                raise Exception("429 Too Many Requests")

        fake_yf = types.SimpleNamespace(Ticker=lambda t: _429Ticker())
        monkeypatch.setitem(sys.modules, "yfinance", fake_yf)

        row = _fetch_one("RATELIMITED", "2026-07-05")
        assert row["target_mean"] is None
        assert row["implied_upside_pct"] is None


# ---------------------------------------------------------------------------
# 4. Staleness filter
# ---------------------------------------------------------------------------

class TestStalenessFilter:
    def test_fresh_tickers_skipped(self, tmp_path):
        """Tickers with a row as_of today are skipped (stale_days=2)."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        existing = pd.DataFrame([
            {
                "ticker": "AAPL",
                "target_mean": 200.0,
                "target_high": 220.0,
                "target_low": 180.0,
                "implied_upside_pct": 5.0,
                "target_dispersion": 0.2,
                "recommendation": "buy",
                "num_analysts": 10,
                "current_price": 190.0,
                "as_of": today,
                "provenance_note": "yfinance_info_pit_snapshot",
            }
        ])
        stale = _stale_tickers(["AAPL", "MSFT"], existing, stale_days=2)
        assert "AAPL" not in stale, "Fresh AAPL should be excluded"
        assert "MSFT" in stale, "Absent MSFT should be included"

    def test_old_tickers_refreshed(self, tmp_path):
        """Tickers with a row older than stale_days are included in the fetch list."""
        old_date = _days_ago_str(10)  # 10 days ago
        existing = pd.DataFrame([
            {
                "ticker": "AAPL",
                "target_mean": 200.0,
                "target_high": 220.0,
                "target_low": 180.0,
                "implied_upside_pct": 5.0,
                "target_dispersion": 0.2,
                "recommendation": "buy",
                "num_analysts": 10,
                "current_price": 190.0,
                "as_of": old_date,
                "provenance_note": "yfinance_info_pit_snapshot",
            }
        ])
        stale = _stale_tickers(["AAPL"], existing, stale_days=2)
        assert "AAPL" in stale, "Stale AAPL (10d old) should be included"

    def test_no_existing_all_stale(self):
        """No existing parquet → all tickers are considered stale."""
        stale = _stale_tickers(["AAPL", "MSFT", "GOOG"], None, stale_days=2)
        assert set(stale) == {"AAPL", "MSFT", "GOOG"}


# ---------------------------------------------------------------------------
# 5. Output parquet schema
# ---------------------------------------------------------------------------

class TestParquetSchema:
    def test_upsert_produces_expected_columns(self, tmp_path):
        """_upsert_and_write must produce a parquet with exactly the _COLUMNS schema."""
        rows = [
            {
                "ticker": "AAPL",
                "target_mean": 200.0,
                "target_high": 220.0,
                "target_low": 180.0,
                "implied_upside_pct": 5.26,
                "target_dispersion": 0.2,
                "recommendation": "buy",
                "num_analysts": 15,
                "current_price": 190.0,
                "as_of": "2026-07-05",
                "provenance_note": "yfinance_info_pit_snapshot",
            },
        ]
        out_path = tmp_path / "targets.parquet"
        _upsert_and_write(rows, None, out_path)
        df = pd.read_parquet(out_path)
        assert list(df.columns) == _COLUMNS, (
            f"Column mismatch: expected {_COLUMNS}, got {list(df.columns)}"
        )

    def test_upsert_merges_over_existing(self, tmp_path):
        """_upsert_and_write replaces old rows for refreshed tickers, keeps others."""
        old = pd.DataFrame([
            {
                "ticker": "AAPL",
                "target_mean": 190.0, "target_high": 210.0, "target_low": 170.0,
                "implied_upside_pct": 3.0, "target_dispersion": 0.21,
                "recommendation": "hold", "num_analysts": 8, "current_price": 184.0,
                "as_of": "2026-07-01", "provenance_note": "yfinance_info_pit_snapshot",
            },
            {
                "ticker": "MSFT",
                "target_mean": 400.0, "target_high": 430.0, "target_low": 370.0,
                "implied_upside_pct": 5.0, "target_dispersion": 0.15,
                "recommendation": "buy", "num_analysts": 20, "current_price": 380.0,
                "as_of": "2026-07-01", "provenance_note": "yfinance_info_pit_snapshot",
            },
        ])
        new_rows = [
            {
                "ticker": "AAPL",
                "target_mean": 220.0, "target_high": 240.0, "target_low": 200.0,
                "implied_upside_pct": 10.0, "target_dispersion": 0.18,
                "recommendation": "buy", "num_analysts": 10, "current_price": 200.0,
                "as_of": "2026-07-05", "provenance_note": "yfinance_info_pit_snapshot",
            },
        ]
        out_path = tmp_path / "targets.parquet"
        _upsert_and_write(new_rows, old, out_path)
        df = pd.read_parquet(out_path)
        # AAPL should be updated
        aapl = df[df["ticker"] == "AAPL"]
        assert len(aapl) == 1
        assert aapl.iloc[0]["target_mean"] == pytest.approx(220.0)
        # MSFT should be preserved
        msft = df[df["ticker"] == "MSFT"]
        assert len(msft) == 1
        assert msft.iloc[0]["target_mean"] == pytest.approx(400.0)


# ---------------------------------------------------------------------------
# 6. Candidate universe derivation (no network)
# ---------------------------------------------------------------------------

class TestCandidateUniverse:
    def test_empty_universe_on_absent_files(self, tmp_path):
        """When all input JSON files are absent, universe is empty (fail-open)."""
        result = _load_candidate_universe(tmp_path)
        assert result == [], f"Expected empty list, got {result}"

    def test_standouts_included(self, tmp_path, monkeypatch):
        """Standout tickers should appear in the universe."""
        import json
        (tmp_path / "site" / "factordata").mkdir(parents=True, exist_ok=True)
        (tmp_path / "site" / "factordata" / "us_standouts.json").write_text(json.dumps({
            "buy": [{"ticker": "AAPL"}, {"ticker": "MSFT"}],
            "watch": [{"ticker": "NVDA"}],
            "laggards": [],
        }))
        result = _load_candidate_universe(tmp_path)
        assert "AAPL" in result
        assert "MSFT" in result
        assert "NVDA" in result

    def test_capped_at_250(self, tmp_path, monkeypatch):
        """Universe is capped at 250 tickers."""
        import json
        (tmp_path / "site" / "factordata").mkdir(parents=True, exist_ok=True)
        # Generate 300 fake tickers
        big_buy = [{"ticker": f"FAKE{i:03d}"} for i in range(300)]
        (tmp_path / "site" / "factordata" / "us_standouts.json").write_text(json.dumps({
            "buy": big_buy,
            "watch": [],
            "laggards": [],
        }))
        result = _load_candidate_universe(tmp_path)
        assert len(result) <= 250, f"Universe cap exceeded: {len(result)} > 250"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_yf(
    monkeypatch,
    target_mean: float | None = 100.0,
    target_high: float | None = 120.0,
    target_low: float | None = 80.0,
    recommend_key: str | None = "buy",
    num_analysts: int | None = 10,
    current_price: float | None = 100.0,
) -> None:
    """Monkeypatch yfinance to return controlled .info values."""
    import types

    info_data = {
        "targetMeanPrice": target_mean,
        "targetHighPrice": target_high,
        "targetLowPrice": target_low,
        "recommendationKey": recommend_key,
        "numberOfAnalystOpinions": num_analysts,
        "currentPrice": current_price,
    }

    class _FakeTicker:
        def __init__(self, symbol):
            pass
        @property
        def info(self):
            return info_data

    fake_yf = types.SimpleNamespace(Ticker=_FakeTicker)
    monkeypatch.setitem(sys.modules, "yfinance", fake_yf)
