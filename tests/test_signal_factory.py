"""Phase-4 signal factory (engine/signal_factory.py).

Invariants:
  * LEAK GUARD — legs at `asof` use ONLY fiscal years whose asof_date (true filed
    date) ≤ asof; a not-yet-filed year must never enter a trend.
  * TREND legs need a genuine prior year (single-year tickers → NaN, no look-ahead
    borrowing); LEVEL legs (cash_conversion) need only the latest year.
  * Values are correct against a hand-computed panel.
  * inverse_correlation_weights down-weights redundant legs, stays long-only, sums 1.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine.signal_factory import LEGS, build_legs, inverse_correlation_weights


def _panel():
    rows = [
        # AAA: two years, improving margins/turnover, deleveraging, buying back stock
        {"ticker": "AAA", "fy": 2018, "revenue": 100, "gross_profit": 40, "assets": 200,
         "debt_lt": 50, "shares": 10, "cfo": 30, "ni": 20, "asof_date": "2019-03-01"},
        {"ticker": "AAA", "fy": 2019, "revenue": 120, "gross_profit": 54, "assets": 220,
         "debt_lt": 44, "shares": 9, "cfo": 40, "ni": 25, "asof_date": "2020-03-01"},
        # BBB: single knowable year only
        {"ticker": "BBB", "fy": 2019, "revenue": 80, "gross_profit": 20, "assets": 160,
         "debt_lt": 30, "shares": 5, "cfo": 10, "ni": 8, "asof_date": "2020-03-01"},
    ]
    df = pd.DataFrame(rows)
    df["asof_date"] = pd.to_datetime(df["asof_date"])
    return df


def test_legs_values_correct():
    legs = build_legs(_panel(), "2020-06-01")
    a = legs.loc["AAA"]
    assert a["gross_margin_trend"] == pytest.approx(54/120 - 40/100)      # 0.45-0.40 = 0.05
    assert a["asset_turnover_trend"] == pytest.approx(120/220 - 100/200)
    assert a["deleveraging"] == pytest.approx(-(44/220 - 50/200))         # +0.05 (leverage fell)
    assert a["net_issuance"] == pytest.approx(-(9/10 - 1))                # +0.10 (shares fell)
    assert a["cash_conversion"] == pytest.approx(40/25)                   # latest cfo/|ni|
    assert list(legs.columns) == LEGS


def test_leak_guard_excludes_not_yet_filed():
    """At 2019-06-01 only FY2018 is filed; FY2019 (filed 2020-03) must be invisible,
    so AAA has NO prior year -> trend legs NaN, and cash_conversion is the FY2018 value."""
    legs = build_legs(_panel(), "2019-06-01")
    a = legs.loc["AAA"]
    assert np.isnan(a["gross_margin_trend"])         # no prior -> no trend (no look-ahead)
    assert np.isnan(a["asset_turnover_trend"])
    assert a["cash_conversion"] == pytest.approx(30/20)   # FY2018 cfo/ni, not FY2019


def test_single_year_ticker_trend_is_nan():
    legs = build_legs(_panel(), "2020-06-01")
    b = legs.loc["BBB"]                               # only FY2019 ever
    assert np.isnan(b["gross_margin_trend"]) and np.isnan(b["net_issuance"])
    assert b["cash_conversion"] == pytest.approx(10/8)   # level leg still computes


def test_empty_when_nothing_filed_yet():
    legs = build_legs(_panel(), "2017-01-01")         # before any asof_date
    assert legs.empty or legs.dropna(how="all").empty


def test_inverse_correlation_weights_downweights_redundant():
    rng = np.random.default_rng(0)
    base = rng.normal(size=400)
    z = pd.DataFrame({
        "a": base + rng.normal(0, 0.05, 400),         # a,b nearly identical (redundant)
        "b": base + rng.normal(0, 0.05, 400),
        "c": rng.normal(size=400),                    # independent
    })
    w = inverse_correlation_weights(z, shrink=0.0)     # pure inverse-corr
    assert w["c"] > w["a"] and w["c"] > w["b"]         # independent leg gets more weight
    assert abs(sum(w.values()) - 1.0) < 1e-9
    assert all(v >= 0 for v in w.values())


def test_inverse_correlation_weights_equal_fallback():
    z = pd.DataFrame({"a": [1.0, 2.0], "b": [3.0, 4.0]})   # <30 rows -> equal weight
    w = inverse_correlation_weights(z)
    assert w == pytest.approx({"a": 0.5, "b": 0.5})


# --- filing-flow legs: Form-4 cluster breadth + 8-K velocity -----------------

def _insider_panel():
    """Form-4 PIT panel for AAA. 3 distinct buyers in the 90d before 2020-06-01
    (one owner files twice → still 3 distinct); a sale, an out-of-window buy, and a
    NOT-YET-FILED buy (2020-07-01) that the leak guard must hide at 2020-06-01."""
    rows = [
        {"ticker": "AAA", "filing_date": "2020-04-01", "code": "P", "rptownercik": 1},
        {"ticker": "AAA", "filing_date": "2020-04-15", "code": "P", "rptownercik": 2},
        {"ticker": "AAA", "filing_date": "2020-05-01", "code": "P", "rptownercik": 3},
        {"ticker": "AAA", "filing_date": "2020-05-02", "code": "P", "rptownercik": 3},  # dup owner
        {"ticker": "AAA", "filing_date": "2020-05-03", "code": "S", "rptownercik": 4},  # sale → out
        {"ticker": "AAA", "filing_date": "2020-01-01", "code": "P", "rptownercik": 6},  # >90d → out
        {"ticker": "AAA", "filing_date": "2020-07-01", "code": "P", "rptownercik": 5},  # future → out
    ]
    df = pd.DataFrame(rows)
    df["filing_date"] = pd.to_datetime(df["filing_date"])
    return df


def _eightk_panel():
    """Material-8K PIT panel for AAA: 4 filings in the recent 90d window and 4 in the
    prior 365d baseline, plus a too-old filing and a NOT-YET-FILED one (2020-07-01)."""
    rows = [("AAA", d) for d in
            ["2020-03-10", "2020-04-10", "2020-05-10", "2020-05-20",        # recent (4)
             "2019-06-01", "2019-09-01", "2019-12-01", "2020-02-01",        # baseline (4)
             "2018-01-01",                                                  # too old → out
             "2020-07-01"]]                                                 # future → leak guard
    df = pd.DataFrame(rows, columns=["ticker", "filing_date"])
    return df  # filing_date kept as str on purpose (mirrors collectors/edgar_8k.py)


def test_form4_cluster_breadth_value_and_size_norm():
    legs = build_legs(_panel(), "2020-06-01", insider_panel=_insider_panel())
    # 3 distinct buyers in window, size-normalised by log of latest knowable assets
    # (AAA FY2019 assets = 220). Owner 3's two buys count once; sale/out-of-window/
    # future buys are all excluded.
    assert legs.loc["AAA", "form4_cluster_breadth"] == pytest.approx(3 / np.log1p(220))
    assert np.isnan(legs.loc["BBB", "form4_cluster_breadth"])   # no insider activity → NaN


def test_form4_leak_guard_excludes_not_yet_filed_buy():
    """AAA's only purchases at 2020-02-15 are FY-irrelevant: at that asof the earliest
    in-window buy (2020-01-01) is the lone knowable one; the 2020-04→07 buys are all in
    the future and must NOT inflate the cluster."""
    asof = "2020-02-15"
    legs = build_legs(_panel(), asof, insider_panel=_insider_panel())
    # only the 2020-01-01 buy (owner 6) is filed AND within 90d of 2020-02-15; and at
    # this asof the latest knowable fiscal year is FY2018 (assets=200), since FY2019
    # only files 2020-03-01 — so the size proxy is log1p(200), not log1p(220).
    assert legs.loc["AAA", "form4_cluster_breadth"] == pytest.approx(1 / np.log1p(200))
    # and a panel whose ONLY buy is still in the future yields NO cluster
    future_only = _insider_panel()[_insider_panel()["filing_date"] >= "2020-07-01"]
    legs2 = build_legs(_panel(), "2020-06-01", insider_panel=future_only)
    assert np.isnan(legs2.loc["AAA", "form4_cluster_breadth"])


def test_eightk_velocity_poisson_surprise_and_leak_guard():
    legs = build_legs(_panel(), "2020-06-01", eightk_panel=_eightk_panel())
    rec, bas = 4.0, 4.0                       # recent vs prior-year baseline counts
    lam = bas * (90 / 365)
    expected = (rec - lam) / np.sqrt(lam + 1.0)
    assert legs.loc["AAA", "eightk_velocity"] == pytest.approx(expected)
    # the 2020-07-01 filing is in the future: removing it must not change the value
    no_future = _eightk_panel()
    no_future = no_future[no_future["filing_date"] != "2020-07-01"]
    legs2 = build_legs(_panel(), "2020-06-01", eightk_panel=no_future)
    assert legs2.loc["AAA", "eightk_velocity"] == pytest.approx(expected)


def test_eightk_uncovered_is_nan_covered_quiet_is_zero():
    legs = build_legs(_panel(), "2020-06-01", eightk_panel=_eightk_panel())
    assert np.isnan(legs.loc["BBB", "eightk_velocity"])       # never in 8-K panel → NaN
    # a name covered (has a filing ≤ asof) but with zero recent AND zero baseline → 0
    quiet = pd.DataFrame({"ticker": ["BBB"], "filing_date": ["2017-01-01"]})
    legs2 = build_legs(_panel(), "2020-06-01", eightk_panel=quiet)
    assert legs2.loc["BBB", "eightk_velocity"] == pytest.approx(0.0)


def test_filing_flow_legs_nan_without_panels():
    """Backward-compatible: no panels → both filing-flow legs are NaN, columns intact."""
    legs = build_legs(_panel(), "2020-06-01")
    assert list(legs.columns) == LEGS
    assert "form4_cluster_breadth" in LEGS and "eightk_velocity" in LEGS
    assert legs["form4_cluster_breadth"].isna().all()
    assert legs["eightk_velocity"].isna().all()
