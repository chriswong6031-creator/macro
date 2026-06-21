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
