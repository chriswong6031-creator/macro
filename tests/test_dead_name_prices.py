"""Dead-name PRICE recovery (collectors/edgar_deadname_prices.py).

Network-free: the per-source fetchers are monkeypatched. Invariants:
  * source PRIORITY — Stooq wins; Polygon only when Stooq declines; yfinance last.
  * RESILIENT — a name every source declines is recorded (so it isn't re-hammered)
    and simply contributes no rows; the run never raises.
  * RESUMABLE — a freshly-fetched name is skipped on the next non-forced run.
  * dead_name_closes() pivots the long table to a concat-ready wide closes frame.
  * price_coverage() math + the residual-bias caveat is always stamped.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from collectors import edgar_deadname_prices as dp


def _series(start="2015-01-02", n=60, base=10.0):
    idx = pd.bdate_range(start, periods=n)
    return pd.Series([base + i * 0.1 for i in range(n)], index=idx)


def _setup(monkeypatch, tmp_path, resolved=("AAA", "BBB")):
    (tmp_path / "edgar").mkdir(parents=True, exist_ok=True)
    (tmp_path / "breadth").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(dp.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(dp.time, "sleep", lambda *a, **k: None)
    (tmp_path / "edgar" / "dead_name_cik.json").write_text(
        json.dumps({t: {"cik": i + 1, "method": "seed"} for i, t in enumerate(resolved)}))
    pd.DataFrame({"ticker": list(resolved),
                  "start_date": pd.to_datetime(["2014-01-01"] * len(resolved)),
                  "end_date": pd.to_datetime(["2016-01-01"] * len(resolved)),
                  "src": ["sp500"] * len(resolved)}).to_parquet(
        tmp_path / "breadth" / "sp1500_pit_membership.parquet")


def test_source_priority_stooq_first(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, resolved=("AAA",))
    monkeypatch.setattr(dp, "_stooq_daily", lambda t: _series())
    monkeypatch.setattr(dp, "_polygon_daily", lambda t, s, e: pytest.fail("polygon must not run"))
    out = dp.fetch_dead_prices(force=True)
    assert set(out["source"]) == {"stooq"} and out["ticker"].nunique() == 1


def test_falls_through_to_polygon_then_yf(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, resolved=("AAA", "BBB"))
    monkeypatch.setattr(dp, "_stooq_daily", lambda t: None)              # blocked
    monkeypatch.setattr(dp, "_polygon_daily", lambda t, s, e: _series() if t == "AAA" else None)
    monkeypatch.setattr(dp, "_yf_daily", lambda t, s, e: _series() if t == "BBB" else None)
    out = dp.fetch_dead_prices(force=True)
    srcs = out.drop_duplicates("ticker").set_index("ticker")["source"].to_dict()
    assert srcs == {"AAA": "polygon", "BBB": "yfinance"}


def test_resilient_all_blocked(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, resolved=("AAA",))
    monkeypatch.setattr(dp, "_stooq_daily", lambda t: None)
    monkeypatch.setattr(dp, "_polygon_daily", lambda t, s, e: None)
    monkeypatch.setattr(dp, "_yf_daily", lambda t, s, e: None)
    out = dp.fetch_dead_prices(force=True)                                # must not raise
    assert out.empty
    seen = json.loads((tmp_path / "edgar" / "_dead_name_prices_seen.json").read_text())
    assert seen["AAA"]["source"] is None and seen["AAA"]["n"] == 0        # recorded as a miss


def test_resumable_skips_fresh(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, resolved=("AAA",))
    calls = {"n": 0}

    def stooq(t):
        calls["n"] += 1
        return _series()

    monkeypatch.setattr(dp, "_stooq_daily", stooq)
    dp.fetch_dead_prices(force=True)
    dp.fetch_dead_prices(force=False)            # fresh -> skip
    assert calls["n"] == 1


def test_dead_name_closes_pivot(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, resolved=("AAA", "BBB"))
    monkeypatch.setattr(dp, "_stooq_daily", lambda t: _series(base=10 if t == "AAA" else 20))
    dp.fetch_dead_prices(force=True)
    wide = dp.dead_name_closes()
    assert list(wide.columns) == ["AAA", "BBB"]
    assert wide["BBB"].iloc[0] == pytest.approx(20.0)
    assert wide.index.is_monotonic_increasing


def test_price_coverage_math_and_caveat(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, resolved=("AAA", "BBB"))
    monkeypatch.setattr(dp, "_stooq_daily", lambda t: _series() if t == "AAA" else None)
    monkeypatch.setattr(dp, "_polygon_daily", lambda t, s, e: None)
    monkeypatch.setattr(dp, "_yf_daily", lambda t, s, e: None)
    dp.fetch_dead_prices(force=True)
    cov = dp.price_coverage()
    assert cov["n_dead_universe"] == 2 and cov["n_with_prices"] == 1
    assert cov["price_coverage_frac"] == pytest.approx(0.5)
    assert cov["by_source"] == {"stooq": 1}
    assert "ACQUISITION" in cov["residual_bias"]      # the up-bias is always stamped
