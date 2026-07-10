"""Tests for engine.manager_lag — pure-function coverage with in-memory fixtures.

Pathologies mirrored:
- dual-class BRK.A/B same issuer (should count once)
- fund with 2 snapshots only (lag_tier falls back to hint)
- empty snapshot
- effective_holding_period with position gaps
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import manager_lag as ml


# --------------------------------------------------------------------------- #
# Fixtures                                                                      #
# --------------------------------------------------------------------------- #

def _snap(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal snapshot DataFrame from a list of dicts."""
    base = {"cusip": "", "ticker": None, "sh_type": "SH",
            "value_usd": 0.0, "shares": 0.0, "issuer": ""}
    return pd.DataFrame([{**base, **r} for r in rows])


EQUIV = {"GOOG": "GOOGL", "BRK.B": "BRK.A"}


def _brk_snap_a():
    """BRK.A only in prev."""
    return _snap([{"ticker": "BRK.A", "cusip": "084670702", "value_usd": 1e7, "shares": 100}])


def _brk_snap_ab():
    """Both BRK.A and BRK.B in cur — should count as ONE issuer."""
    return _snap([
        {"ticker": "BRK.A", "cusip": "084670702", "value_usd": 1.1e7, "shares": 110},
        {"ticker": "BRK.B", "cusip": "084670201", "value_usd": 5e5, "shares": 1000},
    ])


# --------------------------------------------------------------------------- #
# issuer_key tests                                                               #
# --------------------------------------------------------------------------- #

def test_issuer_key_equiv_table():
    assert ml._issuer_key("GOOG", None, EQUIV) == "GOOGL"
    assert ml._issuer_key("BRK.B", None, EQUIV) == "BRK.A"
    assert ml._issuer_key("AAPL", None, EQUIV) == "AAPL"


def test_issuer_key_cusip_fallback():
    # No ticker, valid CUSIP → 6-char stem
    k = ml._issuer_key(None, "084670702", {})
    assert k == "084670"


def test_issuer_key_unknown_fallback():
    k = ml._issuer_key(None, None, {})
    assert k == "UNKNOWN"


# --------------------------------------------------------------------------- #
# quarterly_turnover                                                             #
# --------------------------------------------------------------------------- #

def test_turnover_basic():
    prev = _snap([{"ticker": "AAPL", "cusip": "A", "value_usd": 100.0, "shares": 10}])
    cur  = _snap([{"ticker": "AAPL", "cusip": "A", "value_usd": 120.0, "shares": 12}])
    t = ml.quarterly_turnover(prev, cur, {})
    # delta = |120-100| = 20; avg book = (100+120)/2 = 110; turnover = 20/(2*110) = 9.1%
    assert abs(t - 20.0 / (2.0 * 110.0)) < 1e-9


def test_turnover_new_position():
    """A new position drives turnover up."""
    prev = _snap([{"ticker": "AAPL", "cusip": "A", "value_usd": 100.0, "shares": 10}])
    cur  = _snap([
        {"ticker": "AAPL", "cusip": "A", "value_usd": 100.0, "shares": 10},
        {"ticker": "MSFT", "cusip": "B", "value_usd": 50.0, "shares": 5},
    ])
    t = ml.quarterly_turnover(prev, cur, {})
    # delta = 50 (new MSFT); avg_book = (100 + 150) / 2 = 125; t = 50 / 250 = 0.20
    assert abs(t - 50.0 / (2.0 * 125.0)) < 1e-9


def test_turnover_dual_class_counts_once():
    """BRK.A + BRK.B in cur should collapse to one issuer before turnover math."""
    prev = _brk_snap_a()
    cur  = _brk_snap_ab()
    t_with_equiv = ml.quarterly_turnover(prev, cur, EQUIV)
    # Both BRK.A and BRK.B collapse to BRK.A → total cur value = 1.15e7
    # prev value = 1e7; delta = |1.15e7 - 1e7| = 1.5e6
    # avg_book = (1e7 + 1.15e7) / 2 = 1.075e7
    expected = 1.5e6 / (2.0 * 1.075e7)
    assert abs(t_with_equiv - expected) < 1e-9


def test_turnover_equiv_collapses_issuer_counts():
    """With equiv table, BRK.A+BRK.B in cur collapses to one issuer (BRK.A).
    n_holdings should be 1 after collapse (not 2 separate entries).
    This validates that the issuer_key deduplication works as intended for
    the holding-count dimension; value-based turnover is invariant since it
    sums the same dollars regardless of collapse."""
    snap = _snap([
        {"ticker": "BRK.A", "cusip": "084670702", "value_usd": 1.1e7, "shares": 110},
        {"ticker": "BRK.B", "cusip": "084670201", "value_usd": 5e5, "shares": 1000},
    ])
    n_with_equiv = ml.n_holdings(snap, EQUIV)
    n_without_equiv = ml.n_holdings(snap, {})
    # With equiv: both collapse to BRK.A → 1 unique issuer key
    assert n_with_equiv == 1
    # Without equiv: two different tickers with different CUSIP stems → 2
    assert n_without_equiv == 2


def test_turnover_empty_snaps():
    prev = _snap([])
    cur  = _snap([])
    assert ml.quarterly_turnover(prev, cur, {}) == 0.0


def test_turnover_non_sh_rows_excluded():
    """PUT rows (sh_type != SH) must NOT contribute to book value."""
    prev = _snap([{"ticker": "AAPL", "cusip": "A", "value_usd": 100.0, "shares": 10}])
    cur  = _snap([
        {"ticker": "AAPL", "cusip": "A", "value_usd": 100.0, "shares": 10},
        {"ticker": "AAPL", "cusip": "A", "value_usd": 50.0, "shares": 5,
         "sh_type": "PUT"},  # should be ignored
    ])
    t = ml.quarterly_turnover(prev, cur, {})
    assert t == pytest.approx(0.0, abs=1e-9)  # no SH change


# --------------------------------------------------------------------------- #
# effective_holding_period                                                       #
# --------------------------------------------------------------------------- #

def _snaps_series(*ticker_sets):
    """Build a list of (period_end, filing_date, snap) tuples from sets of tickers."""
    result = []
    for i, tickers in enumerate(ticker_sets):
        rows = [{"ticker": t, "cusip": f"C{t}", "value_usd": 1e6, "shares": 100}
                for t in tickers]
        result.append((f"2024-Q{i+1}", f"2024-0{i+1}-14", _snap(rows)))
    return result


def test_holding_period_basic():
    """AAPL held 3 straight quarters → median run length = 3."""
    snaps = _snaps_series(
        {"AAPL", "MSFT"},   # Q1
        {"AAPL", "MSFT"},   # Q2
        {"AAPL"},            # Q3 — MSFT exits
    )
    hp = ml.effective_holding_period(snaps, {})
    # AAPL: run=3; MSFT: run=2
    # run_lengths = [3, 2]; median = 2.5
    assert hp == pytest.approx(2.5, abs=0.1)


def test_holding_period_insufficient():
    snaps = _snaps_series({"AAPL"})  # only 1 snapshot
    assert ml.effective_holding_period(snaps, {}) is None


def test_holding_period_gap():
    """A position with a gap (Q1 yes, Q2 no, Q3 yes) creates two separate runs."""
    snaps = _snaps_series(
        {"AAPL"},  # Q1
        {},        # Q2 — AAPL absent
        {"AAPL"},  # Q3 — AAPL re-enters
    )
    hp = ml.effective_holding_period(snaps, {})
    # run_lengths = [1, 1]; median = 1.0
    assert hp == pytest.approx(1.0, abs=0.1)


# --------------------------------------------------------------------------- #
# lag_tier                                                                       #
# --------------------------------------------------------------------------- #

def test_lag_tier_low_by_turnover():
    r = ml.lag_tier(20.0, 2.0, n_pairs=5)
    assert r["tier"] == "low" and r["source"] == "data"


def test_lag_tier_low_by_hold():
    r = ml.lag_tier(40.0, 4.0, n_pairs=5)
    assert r["tier"] == "low" and r["source"] == "data"


def test_lag_tier_high():
    r = ml.lag_tier(80.0, 1.0, n_pairs=5)
    assert r["tier"] == "high" and r["source"] == "data"


def test_lag_tier_med():
    r = ml.lag_tier(50.0, 2.0, n_pairs=5)
    assert r["tier"] == "med" and r["source"] == "data"


def test_lag_tier_hint_fallback_low_pairs():
    r = ml.lag_tier(None, None, hint="low", n_pairs=2)
    assert r["tier"] == "low" and r["source"] == "hint"


def test_lag_tier_insufficient_no_hint():
    r = ml.lag_tier(None, None, hint=None, n_pairs=1)
    assert r["tier"] == "med" and r["source"] == "insufficient"


# --------------------------------------------------------------------------- #
# concentration_top10 + n_holdings                                              #
# --------------------------------------------------------------------------- #

def test_concentration_top10_ten_names():
    """10 equal positions → top-10 = 100%."""
    rows = [{"ticker": f"T{i}", "cusip": f"C{i}", "value_usd": 1.0, "shares": 1}
            for i in range(10)]
    snap = _snap(rows)
    assert ml.concentration_top10(snap, {}) == pytest.approx(100.0, abs=0.1)


def test_concentration_top10_twenty_equal():
    """20 equal positions → top-10 = 50%."""
    rows = [{"ticker": f"T{i}", "cusip": f"C{i}", "value_usd": 1.0, "shares": 1}
            for i in range(20)]
    snap = _snap(rows)
    assert ml.concentration_top10(snap, {}) == pytest.approx(50.0, abs=0.1)


def test_n_holdings_collapses_dual_class():
    """BRK.A + BRK.B should count as 1 holding with equiv table."""
    snap = _snap([
        {"ticker": "BRK.A", "cusip": "084670702", "value_usd": 1e7, "shares": 100},
        {"ticker": "BRK.B", "cusip": "084670201", "value_usd": 5e5, "shares": 1000},
        {"ticker": "AAPL",  "cusip": "XAAPLX",   "value_usd": 2e6, "shares": 50},
    ])
    n = ml.n_holdings(snap, EQUIV)
    assert n == 2  # BRK (collapsed) + AAPL


def test_n_holdings_no_equiv():
    """Without equiv table, BRK.A and BRK.B count separately."""
    snap = _snap([
        {"ticker": "BRK.A", "cusip": "084670702", "value_usd": 1e7, "shares": 100},
        {"ticker": "BRK.B", "cusip": "084670201", "value_usd": 5e5, "shares": 1000},
    ])
    assert ml.n_holdings(snap, {}) == 2  # separate CUSIPs → 2 issuers
