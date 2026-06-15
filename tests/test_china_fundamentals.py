"""China descriptive-fundamentals engine tests (engine/china_fundamentals.py).

Pure-function checks on the derivations (no network / no cache): Piotroski counts
the right signals, Altman builds its abstract-derivable legs, CAGR is annualized,
valuation derives PE/PB/PS, and the archetype bucketing matches its rules. These
are CONTEXT, not a validated signal (research/CHINA_HK_STOCK_SIGNALS.md)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import china_fundamentals as cf  # noqa: E402


def _row(fy, **kw):
    base = dict(fy=fy, revenue=100e8, ni=20e8, equity=80e8, bvps=8.0, eps=2.0, roe=15.0,
                roa=10.0, cfo=25e8, gross_margin=40.0, net_margin=20.0, debt_ratio=30.0,
                current_ratio=2.0, equity_multiplier=1.5, asset_turnover=0.6,
                retained_earnings_ps=4.0, ebit_margin=25.0)
    base.update(kw)
    return base


def test_cagr_annualizes():
    # 100 -> 200 over 5 points = 4 intervals -> ~18.9%/yr
    assert cf._cagr([100, 120, 140, 170, 200]) == 18.9
    assert cf._cagr([100]) is None
    assert cf._cagr([-1, 5]) is None        # non-positive endpoint -> None


def test_piotroski_improving_company_scores_high():
    prior = _row(2023, roa=8.0, cfo=20e8, debt_ratio=35.0, current_ratio=1.8,
                 gross_margin=38.0, asset_turnover=0.55, ni=18e8)
    latest = _row(2024, roa=12.0, cfo=26e8, debt_ratio=30.0, current_ratio=2.1,
                  gross_margin=41.0, asset_turnover=0.62, ni=22e8)
    p = cf._piotroski([prior, latest])
    assert p is not None and p["of"] >= 5
    assert p["score"] >= 7          # ROA>0, CFO>0, ΔROA, accruals, Δlev, Δcurr, Δgm, Δturn


def test_piotroski_needs_two_years():
    assert cf._piotroski([_row(2024)]) is None


def test_altman_builds_four_legs():
    z = cf._altman(_row(2024), mktcap=300e8)
    assert z is not None
    assert z["approx"] is True
    assert z["zone"] in ("safe", "grey", "distress")
    assert isinstance(z["z"], float)


def test_valuation_derives_ratios():
    v = cf._valuation(_row(2024, eps=2.0, bvps=8.0, revenue=100e8), price=24.0, mktcap_yi=300.0)
    assert v["pe"] == 12.0          # 24 / 2
    assert v["pb"] == 3.0           # 24 / 8
    assert v["ps"] == 3.0           # 300亿 / (100e8/1e8=100亿)
    assert v["roe"] == 15.0


def test_archetype_quality_and_unprofitable():
    fin = {"rev_cagr": 12.0}
    # high ROE + low debt + growth -> quality compounder
    assert cf._archetype({"div_yield": 0.5}, fin, _row(2024, roe=22.0, debt_ratio=20.0)) \
        == "quality_compounder"
    # negative earnings -> speculative
    assert cf._archetype({}, fin, _row(2024, ni=-5e8)) == "speculative_unprofitable"
    # high yield, low growth -> dividend defensive
    assert cf._archetype({"div_yield": 4.5}, {"rev_cagr": 2.0}, _row(2024, roe=8.0)) \
        == "dividend_defensive"


def test_build_all_empty_when_no_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(cf, "CACHE", tmp_path / "missing.parquet")
    assert cf.build_all({}, {}, {}) == {}
