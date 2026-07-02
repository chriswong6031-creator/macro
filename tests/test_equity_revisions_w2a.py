"""W2a (P1-A) tests for collectors/equity_revisions._one — n_covering + breadth_cov.

Tests verify:
  (a) breadth_cov is computed from n_covering (earnings_estimate accessor), never n_analysts.
  (b) n_covering unavailable (accessor absent / field missing) → breadth_cov is None; n_analysts
      NOT substituted.
  (c) earnings_estimate.numberOfAnalysts = NaN or 0 → breadth_cov is None (positive-guard).

The _one() function calls yfinance which requires network; we test by monkeypatching yf.Ticker
to return a synthetic object with the accessors pre-populated.
"""
from __future__ import annotations

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Synthetic yfinance Ticker stubs
# ---------------------------------------------------------------------------

class _FakeTicker:
    """Minimal stub of yf.Ticker for testing _one() without network."""

    def __init__(self, eps_revisions, eps_trend, earnings_estimate=None):
        self.eps_revisions = eps_revisions
        self.eps_trend = eps_trend
        self._earnings_estimate = earnings_estimate

    @property
    def earnings_estimate(self):
        return self._earnings_estimate


def _make_rev_df(up=4.0, dn=0.0) -> pd.DataFrame:
    """eps_revisions DataFrame with '+1y' row."""
    return pd.DataFrame(
        {"upLast30days": [up], "downLast30days": [dn]},
        index=["+1y"],
    )


def _make_trend_df(cur=10.0, d30=9.0, d90=8.0) -> pd.DataFrame:
    """eps_trend DataFrame with '+1y' row."""
    return pd.DataFrame(
        {"current": [cur], "30daysAgo": [d30], "90daysAgo": [d90]},
        index=["+1y"],
    )


def _make_ee_df(n_analysts: float | None, horizon: str = "+1y") -> pd.DataFrame | None:
    """earnings_estimate DataFrame (the new accessor)."""
    if n_analysts is None:
        return None
    return pd.DataFrame(
        {"numberOfAnalysts": [n_analysts]},
        index=[horizon],
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_breadth_cov_from_earnings_estimate_not_n_analysts(monkeypatch):
    """(a) breadth_cov = (up - dn) / n_covering; n_covering comes from earnings_estimate,
    NOT from n_analysts (the reviser count).

    Setup: up=4, dn=0 → n_analysts (revisers) = 4 → legacy breadth = 1.0 (saturated)
           n_covering (total analysts) = 20 → breadth_cov = 4/20 = 0.2 (de-saturated)
    """
    import yfinance as yf
    import collectors.equity_revisions as er

    ticker = _FakeTicker(
        eps_revisions=_make_rev_df(up=4.0, dn=0.0),
        eps_trend=_make_trend_df(),
        earnings_estimate=_make_ee_df(n_analysts=20.0),
    )
    monkeypatch.setattr(yf, "Ticker", lambda sym: ticker)

    result = er._one("TEST")
    assert result is not None

    # Legacy fields unchanged
    assert result["n_analysts"] == 4        # reviser count
    assert result["breadth"] == 1.0         # saturated: 4/4

    # W2a: coverage-normalised
    assert result["n_covering"] == 20
    expected_breadth_cov = round(4.0 / 20, 4)
    assert result["breadth_cov"] == expected_breadth_cov, (
        f"breadth_cov should be {expected_breadth_cov}, not {result['breadth_cov']}; "
        "ensure n_covering not substituted with n_analysts"
    )
    assert result["breadth_cov"] < result["breadth"], (
        "breadth_cov must be less than legacy breadth when n_covering > n_analysts (de-saturation)"
    )


def test_breadth_cov_none_when_earnings_estimate_accessor_unavailable(monkeypatch):
    """(b) earnings_estimate accessor raises → breadth_cov None; n_analysts NOT substituted."""
    import yfinance as yf
    import collectors.equity_revisions as er

    class _TickerNoEE(_FakeTicker):
        @property
        def earnings_estimate(self):
            raise AttributeError("earnings_estimate not available")

    ticker = _TickerNoEE(
        eps_revisions=_make_rev_df(up=4.0, dn=0.0),
        eps_trend=_make_trend_df(),
    )
    monkeypatch.setattr(yf, "Ticker", lambda sym: ticker)

    result = er._one("TEST")
    assert result is not None

    # HARD HONESTY RULE: breadth_cov and n_covering must be None — never substituted
    assert result["n_covering"] is None, "n_covering must be None when accessor unavailable"
    assert result["breadth_cov"] is None, (
        "breadth_cov must be None — must not substitute n_analysts for n_covering"
    )
    # Legacy breadth is unaffected
    assert result["breadth"] == 1.0
    assert result["n_analysts"] == 4


def test_breadth_cov_none_when_number_of_analysts_field_missing(monkeypatch):
    """(b) earnings_estimate exists but has no numberOfAnalysts column → both None."""
    import yfinance as yf
    import collectors.equity_revisions as er

    # earnings_estimate without the numberOfAnalysts column
    ee = pd.DataFrame({"someOtherField": [5.0]}, index=["+1y"])
    ticker = _FakeTicker(
        eps_revisions=_make_rev_df(up=3.0, dn=1.0),
        eps_trend=_make_trend_df(),
        earnings_estimate=ee,
    )
    monkeypatch.setattr(yf, "Ticker", lambda sym: ticker)

    result = er._one("TEST")
    assert result is not None
    assert result["n_covering"] is None
    assert result["breadth_cov"] is None


def test_breadth_cov_none_when_n_analysts_is_nan(monkeypatch):
    """(c) earnings_estimate.numberOfAnalysts = NaN → both None (NaN-guard)."""
    import yfinance as yf
    import collectors.equity_revisions as er

    ticker = _FakeTicker(
        eps_revisions=_make_rev_df(up=3.0, dn=0.0),
        eps_trend=_make_trend_df(),
        earnings_estimate=_make_ee_df(n_analysts=float("nan")),
    )
    monkeypatch.setattr(yf, "Ticker", lambda sym: ticker)

    result = er._one("TEST")
    assert result is not None
    assert result["n_covering"] is None
    assert result["breadth_cov"] is None


def test_breadth_cov_none_when_n_analysts_is_zero(monkeypatch):
    """(c) earnings_estimate.numberOfAnalysts = 0 → both None (positive-guard prevents /0)."""
    import yfinance as yf
    import collectors.equity_revisions as er

    ticker = _FakeTicker(
        eps_revisions=_make_rev_df(up=3.0, dn=0.0),
        eps_trend=_make_trend_df(),
        earnings_estimate=_make_ee_df(n_analysts=0.0),
    )
    monkeypatch.setattr(yf, "Ticker", lambda sym: ticker)

    result = er._one("TEST")
    assert result is not None
    assert result["n_covering"] is None
    assert result["breadth_cov"] is None


def test_earnings_estimate_falls_back_to_0y_horizon(monkeypatch):
    """earnings_estimate has '0y' but not '+1y' → still resolves n_covering from '0y'."""
    import yfinance as yf
    import collectors.equity_revisions as er

    # eps_revisions and trend have '+1y'; earnings_estimate has '0y'
    rev = pd.DataFrame({"upLast30days": [3.0], "downLast30days": [1.0]}, index=["+1y"])
    trend = _make_trend_df()
    ee = pd.DataFrame({"numberOfAnalysts": [15.0]}, index=["0y"])
    ticker = _FakeTicker(eps_revisions=rev, eps_trend=trend, earnings_estimate=ee)
    monkeypatch.setattr(yf, "Ticker", lambda sym: ticker)

    result = er._one("TEST")
    assert result is not None
    assert result["n_covering"] == 15
    assert result["breadth_cov"] == round(2.0 / 15, 4)     # (3-1)/15
