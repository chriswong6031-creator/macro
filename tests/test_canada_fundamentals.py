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


def test_valuation_forward_fields():
    info = {"forwardPE": 15.8, "trailingPegRatio": 2.56, "payoutRatio": 0.41,
            "fiveYearAvgDividendYield": 3.51}
    v = cf._valuation(info)
    assert v["forward_pe"] == 15.8 and v["peg"] == 2.56
    assert v["payout"] == 41.0                 # fraction -> %
    assert v["five_yr_yield"] == 3.51          # already a percent (do NOT rescale)


def test_consensus_upside_and_rating():
    info = {"numberOfAnalystOpinions": 14, "targetMeanPrice": 269.25,
            "targetHighPrice": 298.0, "targetLowPrice": 235.0,
            "recommendationKey": "buy", "recommendationMean": 2.0, "currentPrice": 278.46}
    c = cf._consensus(info)
    assert c["n_analysts"] == 14 and c["rating"] == "Buy"
    assert c["target_mean"] == 269.25 and c["target_high"] == 298.0
    assert c["upside_pct"] == -3.3             # (269.25/278.46 - 1)*100
    assert cf._consensus({}) is None           # no coverage / no target -> hidden


def test_positioning_scales_ownership():
    info = {"sharesShort": 8694860, "shortRatio": 2.15, "shortPercentOfFloat": 0.0119,
            "heldPercentInsiders": 0.0003, "heldPercentInstitutions": 0.4934}
    p = cf._positioning(info)
    assert p["days_to_cover"] == 2.15 and p["shares_short"] == 8694860
    assert p["short_pct_float"] == 1.19        # fraction -> %
    assert p["held_institutions"] == 49.3
    assert cf._positioning({}) is None
