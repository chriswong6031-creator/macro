"""Canada descriptive-fundamentals engine tests (engine/canada_fundamentals.py).

Pure-function checks on the derivations (no network / no cache): valuation maps the
yfinance fields (ratios stay as-is, fractions like ROE/yield -> %), the archetype
bucketing matches its rules, CAGR annualizes, and build_all/display_names degrade to
empty without a cache. CONTEXT, not a validated signal."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import canada_fundamentals as cf  # noqa: E402


def test_cagr_annualizes():
    assert cf._cagr([100, 120, 140, 170, 200]) == 18.9
    assert cf._cagr([100]) is None
    assert cf._cagr([-1, 5]) is None


def test_valuation_maps_yfinance_fields():
    info = {"trailingPE": 12.0, "priceToBook": 1.5, "priceToSalesTrailing12Months": 3.0,
            "returnOnEquity": 0.18, "profitMargins": 0.22, "debtToEquity": 60.0,
            "dividendYield": 4.1, "revenueGrowth": 0.12, "marketCap": 5.0e10}
    v = cf._valuation(info)
    assert v["pe"] == 12.0 and v["pb"] == 1.5 and v["ps"] == 3.0
    assert v["roe"] == 18.0          # fraction -> %
    assert v["net_margin"] == 22.0
    assert v["div_yield"] == 4.1     # yfinance dividendYield is already a percent
    assert v["rev_growth"] == 12.0
    assert v["debt_to_equity"] == 60.0


def test_archetype_rules():
    # high ROE + modest debt + growth -> quality compounder
    assert cf._archetype({"roe": 22.0, "div_yield": 0.5, "net_margin": 18.0,
                          "rev_growth": 10.0, "debt_to_equity": 80.0}) == "quality_compounder"
    # negative margin -> speculative / unprofitable
    assert cf._archetype({"roe": None, "net_margin": -5.0, "div_yield": 0.0,
                          "rev_growth": 5.0, "debt_to_equity": None}) == "speculative_unprofitable"
    # high yield, low growth -> dividend defensive
    assert cf._archetype({"roe": 8.0, "div_yield": 4.5, "net_margin": 12.0,
                          "rev_growth": 2.0, "debt_to_equity": 90.0}) == "dividend_defensive"
    # fast top-line -> growth
    assert cf._archetype({"roe": 6.0, "div_yield": 0.0, "net_margin": 8.0,
                          "rev_growth": 28.0, "debt_to_equity": 40.0}) == "growth"


def test_build_all_and_names_empty_when_no_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(cf, "CACHE", tmp_path / "missing.parquet")
    assert cf.build_all({}) == {}
    assert cf.display_names() == {}
