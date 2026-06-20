"""Tests for engine.theme_flow_rollup.

Primary tests use synthetic in-memory data to prove the math deterministically.
One live-data smoke test exercises the public API against the real store, guarded
with pytest.skip when data is unavailable.
"""
from __future__ import annotations

import math
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from engine.theme_flow_rollup import (
    ThemeFlowResult,
    _basket_rel_perf,
    _build_ticker_flow_map,
    _flow_label,
    theme_flow,
)


# ---------------------------------------------------------------------------
# _build_ticker_flow_map
# ---------------------------------------------------------------------------

class TestBuildTickerFlowMap:
    def test_empty_signals(self):
        assert _build_ticker_flow_map([]) == {}

    def test_single_signal_accumulating(self):
        signals = [{"ticker": "NVDA", "conviction_pp": 0.5}]
        m = _build_ticker_flow_map(signals)
        assert m == {"NVDA": [0.5]}

    def test_single_signal_trimming(self):
        signals = [{"ticker": "AAPL", "conviction_pp": -0.3}]
        m = _build_ticker_flow_map(signals)
        assert m == {"AAPL": [-0.3]}

    def test_multiple_etfs_same_ticker_aggregates(self):
        # NVDA appears in two ETFs
        signals = [
            {"ticker": "NVDA", "conviction_pp": 0.4},
            {"ticker": "NVDA", "conviction_pp": 0.2},
            {"ticker": "AAPL", "conviction_pp": -0.1},
        ]
        m = _build_ticker_flow_map(signals)
        assert sorted(m["NVDA"]) == [0.2, 0.4]
        assert m["AAPL"] == [-0.1]

    def test_ticker_normalised_to_uppercase(self):
        signals = [{"ticker": "msft", "conviction_pp": 0.1}]
        m = _build_ticker_flow_map(signals)
        assert "MSFT" in m

    def test_missing_ticker_or_pp_skipped(self):
        signals = [
            {"conviction_pp": 0.5},           # no ticker
            {"ticker": "AMD", "conviction_pp": None},  # no pp
            {"ticker": "INTC", "conviction_pp": 0.2},  # valid
        ]
        m = _build_ticker_flow_map(signals)
        assert list(m.keys()) == ["INTC"]

    def test_non_numeric_pp_skipped(self):
        signals = [{"ticker": "X", "conviction_pp": "bad"}]
        m = _build_ticker_flow_map(signals)
        assert m == {}


# ---------------------------------------------------------------------------
# _basket_rel_perf
# ---------------------------------------------------------------------------

class TestBasketRelPerf:
    def _make_series(self, values):
        idx = pd.date_range("2024-01-01", periods=len(values), freq="B")
        return pd.Series(values, index=idx, dtype=float)

    def test_basket_outperforms_bench_positive(self):
        # basket +5%, bench +1% over last 5 sessions => rel ~ +4%
        lvl = self._make_series([1.0] * 5 + [1.05])
        bench = self._make_series([1.0] * 5 + [1.01])
        r = _basket_rel_perf(lvl, bench, window=5)
        assert r is not None
        assert abs(r - (1.05 / 1.0 - 1 - (1.01 / 1.0 - 1))) < 1e-9

    def test_basket_underperforms_bench_negative(self):
        lvl = self._make_series([1.0] * 5 + [0.97])
        bench = self._make_series([1.0] * 5 + [1.02])
        r = _basket_rel_perf(lvl, bench, window=5)
        assert r is not None
        assert r < 0

    def test_too_short_returns_none(self):
        lvl = self._make_series([1.0, 1.01])
        bench = self._make_series([1.0, 1.00])
        assert _basket_rel_perf(lvl, bench, window=5) is None

    def test_nan_in_series_returns_none(self):
        lvl = self._make_series([1.0] * 5 + [float("nan")])
        bench = self._make_series([1.0] * 6)
        assert _basket_rel_perf(lvl, bench, window=5) is None

    def test_zero_base_returns_none(self):
        lvl = self._make_series([0.0] * 6)
        bench = self._make_series([1.0] * 6)
        assert _basket_rel_perf(lvl, bench, window=5) is None


# ---------------------------------------------------------------------------
# _flow_label
# ---------------------------------------------------------------------------

class TestFlowLabel:
    def test_none_flow_score_is_na(self):
        assert _flow_label(None, None) == "n/a"

    def test_high_acc_pct_accumulating(self):
        assert _flow_label(0.3, 0.75) == "accumulating"

    def test_low_acc_pct_distributing(self):
        assert _flow_label(-0.2, 0.20) == "distributing"

    def test_mid_range_mixed(self):
        assert _flow_label(0.05, 0.50) == "mixed"

    def test_boundary_60pct_accumulating(self):
        assert _flow_label(0.1, 0.60) == "accumulating"

    def test_boundary_35pct_distributing(self):
        assert _flow_label(-0.05, 0.35) == "distributing"


# ---------------------------------------------------------------------------
# theme_flow — synthetic end-to-end
# ---------------------------------------------------------------------------

def _make_dates(n: int) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(
        pd.date_range("2024-01-01", periods=n, freq="B").as_unit("ms")
    )


def _make_rets(tickers: list[str], n: int = 200) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    idx = _make_dates(n)
    data = rng.normal(0.001, 0.02, size=(n, len(tickers)))
    return pd.DataFrame(data, index=idx, columns=tickers)


def _make_bench(n: int = 200) -> pd.Series:
    rng = np.random.default_rng(99)
    idx = _make_dates(n)
    vals = np.cumprod(1 + rng.normal(0.0005, 0.01, n))
    return pd.Series(vals, index=idx)


def _fake_setup(tickers: list[str], n: int = 200):
    rets = _make_rets(tickers, n)
    bench = _make_bench(n)
    idx = rets.index
    mem = {
        "baskets": {
            "ai_infra": {
                "id": "ai_infra",
                "name": "AI Infrastructure",
                "name_zh": "AI基础设施",
                "category": "Technology",
                "members": [
                    {"ticker": t, "added": "2023-01-01", "removed": None}
                    for t in tickers
                ],
            }
        }
    }
    return {"mem": mem, "rets": rets, "bench": bench, "idx": idx, "region": "us"}


class TestThemeFlowSynthetic:
    """End-to-end tests using fully synthetic data — no real store reads."""

    def _run(self, signals, tickers=None, n=200):
        tickers = tickers or ["AAPL", "NVDA", "MSFT", "AMZN", "META"]
        fake_s = _fake_setup(tickers, n)
        with (
            patch("engine.theme_flow_rollup.group_flow._setup", return_value=fake_s),
            patch("engine.theme_flow_rollup.all_etf_signals", return_value=signals),
        ):
            return theme_flow("us")

    def test_no_signals_sparse_coverage(self):
        # Zero signals → all themes get n/a (coverage below threshold)
        result = self._run(signals=[])
        assert "ai_infra" in result
        r = result["ai_infra"]
        assert r["flow_score"] is None
        assert r["accumulating_pct"] is None
        assert r["flow_label"] == "n/a"
        assert r["n_covered"] == 0
        assert r["n_members"] > 0

    def test_all_accumulating_positive_flow_score(self):
        tickers = ["AAPL", "NVDA", "MSFT", "AMZN", "META"]
        signals = [
            {"ticker": t, "conviction_pp": 0.5, "direction": "accumulating"}
            for t in tickers
        ]
        result = self._run(signals=signals, tickers=tickers)
        assert "ai_infra" in result
        r = result["ai_infra"]
        assert r["flow_score"] is not None
        assert r["flow_score"] > 0
        assert r["accumulating_pct"] == 1.0
        assert r["flow_label"] == "accumulating"

    def test_all_trimming_negative_flow_score(self):
        tickers = ["AAPL", "NVDA", "MSFT", "AMZN", "META"]
        signals = [
            {"ticker": t, "conviction_pp": -0.4, "direction": "trimming"}
            for t in tickers
        ]
        result = self._run(signals=signals, tickers=tickers)
        r = result["ai_infra"]
        assert r["flow_score"] is not None
        assert r["flow_score"] < 0
        assert r["accumulating_pct"] == 0.0
        assert r["flow_label"] == "distributing"

    def test_flow_score_is_mean_of_per_ticker_means(self):
        # AAPL appears twice (two ETFs); mean(0.6, 0.4)=0.5
        # NVDA appears once: 0.3
        # MSFT appears once: 0.8
        # Theme flow_score = mean(0.5, 0.3, 0.8) = 0.5333...
        tickers = ["AAPL", "NVDA", "MSFT", "AMZN", "META"]
        signals = [
            {"ticker": "AAPL", "conviction_pp": 0.6},
            {"ticker": "AAPL", "conviction_pp": 0.4},
            {"ticker": "NVDA", "conviction_pp": 0.3},
            {"ticker": "MSFT", "conviction_pp": 0.8},
        ]
        result = self._run(signals=signals, tickers=tickers)
        r = result["ai_infra"]
        expected = (0.5 + 0.3 + 0.8) / 3
        assert r["flow_score"] is not None
        assert abs(r["flow_score"] - round(expected, 4)) < 1e-6

    def test_divergence_true_when_flow_negative_price_flat(self):
        # Flow is negative but basket has been flat/rising relative to bench
        # We test the divergence flag by forcing a net-trimming signal on members
        # whose synthetic return makes the basket near-flat
        tickers = ["AAPL", "NVDA", "MSFT", "AMZN", "META"]
        # All members trimmed => flow_score < 0
        signals = [
            {"ticker": t, "conviction_pp": -0.5}
            for t in tickers
        ]
        # The synthetic returns are random; we patch _basket_rel_perf to return +0.01
        with (
            patch("engine.theme_flow_rollup.group_flow._setup",
                  return_value=_fake_setup(tickers)),
            patch("engine.theme_flow_rollup.all_etf_signals", return_value=signals),
            patch("engine.theme_flow_rollup._basket_rel_perf", return_value=0.01),
        ):
            result = theme_flow("us")
        r = result["ai_infra"]
        assert r["divergence"] is True

    def test_divergence_false_when_flow_negative_price_also_negative(self):
        tickers = ["AAPL", "NVDA", "MSFT", "AMZN", "META"]
        signals = [
            {"ticker": t, "conviction_pp": -0.5}
            for t in tickers
        ]
        # price also falling → no divergence
        with (
            patch("engine.theme_flow_rollup.group_flow._setup",
                  return_value=_fake_setup(tickers)),
            patch("engine.theme_flow_rollup.all_etf_signals", return_value=signals),
            patch("engine.theme_flow_rollup._basket_rel_perf", return_value=-0.05),
        ):
            result = theme_flow("us")
        r = result["ai_infra"]
        assert r["divergence"] is False

    def test_divergence_false_when_flow_positive(self):
        tickers = ["AAPL", "NVDA", "MSFT", "AMZN", "META"]
        signals = [{"ticker": t, "conviction_pp": 0.5} for t in tickers]
        with (
            patch("engine.theme_flow_rollup.group_flow._setup",
                  return_value=_fake_setup(tickers)),
            patch("engine.theme_flow_rollup.all_etf_signals", return_value=signals),
            patch("engine.theme_flow_rollup._basket_rel_perf", return_value=0.02),
        ):
            result = theme_flow("us")
        r = result["ai_infra"]
        assert r["divergence"] is False

    def test_n_members_and_n_covered_counts(self):
        tickers = ["AAPL", "NVDA", "MSFT", "AMZN", "META"]  # 5 members
        signals = [
            {"ticker": "AAPL", "conviction_pp": 0.3},
            {"ticker": "NVDA", "conviction_pp": 0.2},
        ]
        result = self._run(signals=signals, tickers=tickers)
        r = result["ai_infra"]
        assert r["n_members"] == 5
        # Only AAPL + NVDA covered — but 2/5 = 40% > 10% threshold, so scores computed
        assert r["n_covered"] == 2
        assert r["flow_score"] is not None

    def test_setup_returns_none_gives_empty_dict(self):
        with patch("engine.theme_flow_rollup.group_flow._setup", return_value=None):
            assert theme_flow("us") == {}

    def test_etf_signals_exception_gives_empty_signals(self):
        tickers = ["AAPL", "NVDA", "MSFT", "AMZN", "META"]
        fake_s = _fake_setup(tickers)
        with (
            patch("engine.theme_flow_rollup.group_flow._setup", return_value=fake_s),
            patch("engine.theme_flow_rollup.all_etf_signals",
                  side_effect=RuntimeError("store unavailable")),
        ):
            result = theme_flow("us")
        # Should not raise — all themes will be n/a due to no signals
        assert isinstance(result, dict)

    def test_removed_member_excluded_from_n_members(self):
        # META has a removed date in the past — should not count as active
        tickers = ["AAPL", "NVDA", "MSFT", "AMZN", "META"]
        fake_s = _fake_setup(tickers)
        # Inject a removed date for META that is before the last index date
        basket = fake_s["mem"]["baskets"]["ai_infra"]
        for m in basket["members"]:
            if m["ticker"] == "META":
                m["removed"] = "2020-01-01"   # definitely in the past
        signals = [{"ticker": t, "conviction_pp": 0.3} for t in tickers]
        with (
            patch("engine.theme_flow_rollup.group_flow._setup", return_value=fake_s),
            patch("engine.theme_flow_rollup.all_etf_signals", return_value=signals),
        ):
            result = theme_flow("us")
        r = result["ai_infra"]
        # META removed → n_members = 4
        assert r["n_members"] == 4


# ---------------------------------------------------------------------------
# Live smoke test — guarded
# ---------------------------------------------------------------------------

def test_theme_flow_live_us_smoke():
    """Live data smoke test: calls theme_flow('us') against the real store.
    Skipped when the data store is unavailable (CI / offline environments).
    """
    try:
        from lib import config, store
        p = config.data_dir() / "baskets" / "membership.json"
        if not p.exists():
            pytest.skip("baskets/membership.json not found — store unavailable")
        # Also check at least one ETF holdings dir exists
        etf_dir = config.data_dir() / "etf_holdings"
        if not etf_dir.exists() or not any(etf_dir.iterdir()):
            pytest.skip("data/etf_holdings not populated — store unavailable")
    except Exception as exc:
        pytest.skip(f"store init failed: {exc}")

    result = theme_flow("us")
    # Should return a dict (possibly empty if data too short, but never raises)
    assert isinstance(result, dict)
    for tid, r in result.items():
        assert isinstance(tid, str)
        assert "flow_score" in r
        assert "accumulating_pct" in r
        assert "divergence" in r
        assert isinstance(r["divergence"], bool)
        assert "n_covered" in r
        assert "n_members" in r
        assert "flow_label" in r
        assert r["flow_label"] in ("accumulating", "distributing", "mixed", "n/a")
        if r["flow_score"] is not None:
            assert math.isfinite(r["flow_score"])
        if r["accumulating_pct"] is not None:
            assert 0.0 <= r["accumulating_pct"] <= 1.0
