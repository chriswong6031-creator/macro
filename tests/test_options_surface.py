"""Unit tests for engine/options_surface.py — W2 SURFACE (RIC program).

ISOLATION CONTRACT:
  All tests use synthetic DataFrames (no real T1 store reads). No MM_DATA_GUARD
  writes — pure in-memory computation only. Follows the pattern from
  tests/test_index_gex_history.py (synthetic fixture, monkeypatch for paths).

Tests cover:
  1. compute_surface_row: sign convention (call-heavy → positive net GEX)
  2. OI[t-1] law enforcement: zero-OI rows excluded; oi_prev correctly applied
  3. |·|-magnitude concentration shares: front7_abs_gex_share bounded [0,1]
  4. Expiry bucket breakdown: front-week / front-month / back split
  5. root_class mapping: SPY → index_etf, XLK → sector_etf, SMH → industry_etf
  6. dealer_sign_assumption: printed in every row
  7. Graceful null: empty greeks or OI → None (no exception)
  8. Root class map: all SURFACE_ROSTER roots have a class
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import engine.options_surface as OS
from engine.options_surface import (
    DEALER_SIGN_ASSUMPTION,
    FRONT_MONTH_MAX_CD,
    FRONT_WEEK_MAX_CD,
    ROOT_CLASS_MAP,
    SURFACE_ROSTER,
    compute_surface_row,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_greeks(
    spot: float = 100.0,
    strikes: list[float] | None = None,
    iv: float = 0.20,
    exp_days: int = 32,
    date_str: str = "2023-06-15",
    root: str = "TST",
) -> pd.DataFrame:
    """Minimal greeks day frame for (root, date) with calls + puts at each strike."""
    if strikes is None:
        strikes = [90.0, 95.0, 100.0, 105.0, 110.0]
    exp_date = pd.Timestamp(date_str) + pd.Timedelta(days=exp_days)
    rows = []
    for k in strikes:
        for right in ("C", "P"):
            rows.append({
                "root": root,
                "expiration": str(exp_date.date()),
                "strike": k,
                "right": right,
                "date": date_str,
                "implied_vol": iv,
                "underlying_price": spot,
            })
    return pd.DataFrame(rows)


def _make_oi(
    strikes: list[float] | None = None,
    call_oi: int = 1000,
    put_oi: int = 500,
    exp_days: int = 32,
    date_str: str = "2023-06-15",
    root: str = "TST",
) -> pd.DataFrame:
    """Minimal OI frame (oi_prev = OI[t−1] per OPRA timing law)."""
    if strikes is None:
        strikes = [90.0, 95.0, 100.0, 105.0, 110.0]
    exp_date = pd.Timestamp(date_str) + pd.Timedelta(days=exp_days)
    rows = []
    for k in strikes:
        rows.append({
            "root": root,
            "expiration": str(exp_date.date()),
            "strike": k,
            "right": "C",
            "date": date_str,
            "open_interest": call_oi,
        })
        rows.append({
            "root": root,
            "expiration": str(exp_date.date()),
            "strike": k,
            "right": "P",
            "date": date_str,
            "open_interest": put_oi,
        })
    return pd.DataFrame(rows)


def _make_row(
    call_oi: int = 1000,
    put_oi: int = 500,
    spot: float = 100.0,
    exp_days: int = 32,
    date_str: str = "2023-06-15",
    root: str = "TST",
    iv: float = 0.20,
) -> dict | None:
    g = _make_greeks(spot=spot, iv=iv, exp_days=exp_days, date_str=date_str, root=root)
    o = _make_oi(call_oi=call_oi, put_oi=put_oi, exp_days=exp_days, date_str=date_str, root=root)
    return compute_surface_row(g, o, root, date_str)


# ---------------------------------------------------------------------------
# 1. Dealer-sign convention: call-heavy → positive net GEX
# ---------------------------------------------------------------------------

def test_call_heavy_positive_net_gex():
    """Call-dominated OI → net_gex_bn > 0 (dealer long-call assumption)."""
    row = _make_row(call_oi=5000, put_oi=100)
    assert row is not None
    assert row["net_gex_bn"] > 0, f"expected positive net_gex_bn, got {row['net_gex_bn']}"


def test_put_heavy_negative_net_gex():
    """Put-dominated OI → net_gex_bn < 0 (dealer short-put assumption)."""
    row = _make_row(call_oi=100, put_oi=5000)
    assert row is not None
    assert row["net_gex_bn"] < 0, f"expected negative net_gex_bn, got {row['net_gex_bn']}"


def test_balanced_oi_near_zero():
    """Balanced call/put OI → net_gex_bn near 0 (gamma partial cancellation)."""
    row = _make_row(call_oi=1000, put_oi=1000)
    assert row is not None
    # Balanced OI: calls and puts partially cancel (not exactly 0 due to BS gamma asymmetry)
    assert abs(row["net_gex_bn"]) < abs(_make_row(call_oi=5000, put_oi=100)["net_gex_bn"])


# ---------------------------------------------------------------------------
# 2. dealer_sign_assumption always printed
# ---------------------------------------------------------------------------

def test_dealer_sign_assumption_in_every_row():
    """Every row must carry the dealer-sign assumption string."""
    row = _make_row()
    assert row is not None
    assert row["dealer_sign_assumption"] == DEALER_SIGN_ASSUMPTION
    assert DEALER_SIGN_ASSUMPTION == "long_call_short_put"


# ---------------------------------------------------------------------------
# 3. |·|-magnitude concentration shares bounded [0, 1]
# ---------------------------------------------------------------------------

def test_front7_abs_gex_share_bounded():
    """front7_abs_gex_share must be in [0, 1]."""
    row = _make_row(exp_days=5)   # front-week expiry
    assert row is not None
    assert 0.0 <= row["front7_abs_gex_share"] <= 1.0


def test_front7_abs_charm_share_bounded():
    row = _make_row(exp_days=5)
    assert row is not None
    assert 0.0 <= row["front7_abs_charm_share"] <= 1.0


def test_front7_all_front_week_share_near_one():
    """If all contracts expire within 7 calendar days, front7 shares → 1.0."""
    row = _make_row(exp_days=6)  # within front-week threshold
    assert row is not None
    assert row["front7_abs_gex_share"] == pytest.approx(1.0, abs=1e-6)
    assert row["front7_abs_charm_share"] == pytest.approx(1.0, abs=1e-6)


def test_front7_all_back_share_near_zero():
    """If all contracts expire > 35 calendar days out, front7 shares → 0."""
    row = _make_row(exp_days=90)  # back bucket
    assert row is not None
    assert row["front7_abs_gex_share"] == pytest.approx(0.0, abs=1e-6)
    assert row["front7_abs_charm_share"] == pytest.approx(0.0, abs=1e-6)


# ---------------------------------------------------------------------------
# 4. Expiry bucket breakdowns
# ---------------------------------------------------------------------------

def test_expiry_bucket_fw_only():
    """Single front-week expiry → fw_gex_bn == net_gex_bn, fm/bk == 0."""
    row = _make_row(call_oi=1000, put_oi=200, exp_days=5)
    assert row is not None
    assert row["fw_gex_bn"] == pytest.approx(row["net_gex_bn"], abs=1e-9)
    assert row["fm_gex_bn"] == pytest.approx(0.0, abs=1e-9)
    assert row["bk_gex_bn"] == pytest.approx(0.0, abs=1e-9)


def test_expiry_bucket_bk_only():
    """Single back-bucket expiry → bk_gex_bn == net_gex_bn, fw/fm == 0."""
    row = _make_row(call_oi=1000, put_oi=200, exp_days=60)
    assert row is not None
    assert row["bk_gex_bn"] == pytest.approx(row["net_gex_bn"], abs=1e-9)
    assert row["fw_gex_bn"] == pytest.approx(0.0, abs=1e-9)
    assert row["fm_gex_bn"] == pytest.approx(0.0, abs=1e-9)


def test_expiry_bucket_sum_equals_total():
    """fw + fm + bk should equal net_gex_bn for a chain with multiple expiries."""
    # Build a multi-expiry greeks+oi frame manually
    date_str = "2023-06-15"
    root = "TST"
    spot = 100.0
    rows_g, rows_o = [], []
    for exp_days, oi_c, oi_p in [(5, 800, 100), (20, 600, 200), (60, 400, 300)]:
        exp_date = pd.Timestamp(date_str) + pd.Timedelta(days=exp_days)
        for k in [95.0, 100.0, 105.0]:
            rows_g.append({
                "root": root, "expiration": str(exp_date.date()), "strike": k,
                "right": "C", "date": date_str, "implied_vol": 0.20, "underlying_price": spot,
            })
            rows_g.append({
                "root": root, "expiration": str(exp_date.date()), "strike": k,
                "right": "P", "date": date_str, "implied_vol": 0.20, "underlying_price": spot,
            })
            rows_o.append({
                "root": root, "expiration": str(exp_date.date()), "strike": k,
                "right": "C", "date": date_str, "open_interest": oi_c,
            })
            rows_o.append({
                "root": root, "expiration": str(exp_date.date()), "strike": k,
                "right": "P", "date": date_str, "open_interest": oi_p,
            })

    g_df = pd.DataFrame(rows_g)
    o_df = pd.DataFrame(rows_o)
    row = compute_surface_row(g_df, o_df, root, date_str)
    assert row is not None
    bucket_sum = row["fw_gex_bn"] + row["fm_gex_bn"] + row["bk_gex_bn"]
    assert bucket_sum == pytest.approx(row["net_gex_bn"], abs=1e-9)


# ---------------------------------------------------------------------------
# 5. root_class mapping
# ---------------------------------------------------------------------------

def test_root_class_index_etf():
    row = _make_row(root="SPY")
    row["root"] = "SPY"
    # root_class is set by ROOT_CLASS_MAP in compute_surface_row
    r = compute_surface_row(
        _make_greeks(root="SPY"),
        _make_oi(root="SPY"),
        "SPY",
        "2023-06-15",
    )
    assert r is not None
    assert r["root_class"] == "index_etf"


def test_root_class_sector_etf():
    r = compute_surface_row(
        _make_greeks(root="XLK"),
        _make_oi(root="XLK"),
        "XLK",
        "2023-06-15",
    )
    assert r is not None
    assert r["root_class"] == "sector_etf"


def test_root_class_industry_etf():
    r = compute_surface_row(
        _make_greeks(root="SMH"),
        _make_oi(root="SMH"),
        "SMH",
        "2023-06-15",
    )
    assert r is not None
    assert r["root_class"] == "industry_etf"


def test_all_roster_roots_have_class():
    """Every root in SURFACE_ROSTER must have a class in ROOT_CLASS_MAP."""
    missing = [r for r in SURFACE_ROSTER if r not in ROOT_CLASS_MAP]
    assert not missing, f"Roster roots without class: {missing}"


def test_surface_roster_frozen_19():
    """Roster should be exactly 19 roots (XLC excluded, audit 2026-07-17)."""
    assert len(SURFACE_ROSTER) == 19


# ---------------------------------------------------------------------------
# 6. OI = 0 → excluded from computation
# ---------------------------------------------------------------------------

def test_zero_oi_rows_excluded():
    """Contracts with open_interest = 0 must be excluded (not counted)."""
    date_str = "2023-06-15"
    root = "TST"
    exp_date = "2023-07-21"
    greeks = pd.DataFrame([
        {"root": root, "expiration": exp_date, "strike": 100.0, "right": "C",
         "date": date_str, "implied_vol": 0.20, "underlying_price": 100.0},
        {"root": root, "expiration": exp_date, "strike": 100.0, "right": "P",
         "date": date_str, "implied_vol": 0.20, "underlying_price": 100.0},
    ])
    # All OI = 0 → should return None
    oi_zero = pd.DataFrame([
        {"root": root, "expiration": exp_date, "strike": 100.0, "right": "C",
         "date": date_str, "open_interest": 0},
        {"root": root, "expiration": exp_date, "strike": 100.0, "right": "P",
         "date": date_str, "open_interest": 0},
    ])
    result = compute_surface_row(greeks, oi_zero, root, date_str)
    assert result is None, "Expected None when all OI = 0"


# ---------------------------------------------------------------------------
# 7. Graceful null on empty inputs
# ---------------------------------------------------------------------------

def test_empty_greeks_returns_none():
    row = compute_surface_row(
        greeks_day=pd.DataFrame(),
        oi_prev=_make_oi(),
        root="TST",
        date_str="2023-06-15",
    )
    assert row is None


def test_empty_oi_returns_none():
    row = compute_surface_row(
        greeks_day=_make_greeks(),
        oi_prev=pd.DataFrame(),
        root="TST",
        date_str="2023-06-15",
    )
    assert row is None


def test_none_greeks_returns_none():
    row = compute_surface_row(
        greeks_day=None,
        oi_prev=_make_oi(),
        root="TST",
        date_str="2023-06-15",
    )
    assert row is None


# ---------------------------------------------------------------------------
# 8. OI fw_oi_frac / fm_oi_frac in [0, 1] and bounded by 1
# ---------------------------------------------------------------------------

def test_oi_frac_bounded():
    row = _make_row(exp_days=5)  # front-week
    assert row is not None
    assert 0.0 <= row["fw_oi_frac"] <= 1.0
    assert 0.0 <= row["fm_oi_frac"] <= 1.0
    # front-week only: fw_oi_frac should be 1.0, fm should be 0
    assert row["fw_oi_frac"] == pytest.approx(1.0, abs=1e-6)
    assert row["fm_oi_frac"] == pytest.approx(0.0, abs=1e-6)


# ---------------------------------------------------------------------------
# 9. n_contracts and spot fields
# ---------------------------------------------------------------------------

def test_n_contracts_and_spot_present():
    row = _make_row()
    assert row is not None
    assert "n_contracts" in row
    assert row["n_contracts"] > 0
    assert "spot" in row
    assert row["spot"] == pytest.approx(100.0, abs=0.01)


# ---------------------------------------------------------------------------
# 10. Consistency of SURFACE_ROSTER and ROOT_CLASS_MAP
# ---------------------------------------------------------------------------

def test_roster_matches_map_keys():
    """SURFACE_ROSTER must equal sorted(ROOT_CLASS_MAP.keys())."""
    assert SURFACE_ROSTER == sorted(ROOT_CLASS_MAP.keys())


def test_class_values_valid():
    """All root_class values must be one of the three valid classes."""
    valid = {"index_etf", "sector_etf", "industry_etf"}
    for root, cls in ROOT_CLASS_MAP.items():
        assert cls in valid, f"{root} has unknown class {cls!r}"
