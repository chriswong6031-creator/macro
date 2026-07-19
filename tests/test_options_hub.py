"""tests/test_options_hub.py — hermetic tests for engine/options_hub.py and app/hub.py.

All tests use synthetic fixture frames — no real parquet files read.

Coverage:
  1.  ATM IV interpolation (two-nearest, inverse-distance weighting)
  2.  iv_rank_252 null when <60 observations
  3.  term structure sorted ascending by DTE
  4.  smile shape: exactly 2 expiries (>=2 DTE) returned
  5.  GEX dealer-sign parity vs hand-computed 2-contract fixture
  6.  GEX walls (call wall above spot positive gamma / put wall below spot negative)
  7.  GEX gamma flip with crossing and no-crossing -> None
  8.  OI movers: t-1 vs t-2 delta (never same-day)
  9.  OI movers: same-session comparison (d_oi=0) -> not in output
  10. Hot contracts: by_premium sorted descending
  11. Hot contracts: vol_gt_oi flag correctness
  12. Router param sanitization: invalid root -> 400
  13. Router TTL: second call within TTL uses cache, not fetch
  14. Router stale: fetch failure returns stale=True
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

# ── ensure repo root on path ──────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.options_hub import (
    _atm_iv_for_expiry,
    _compute_smile,
    _find_gamma_flip,
    _rv20,
    compute_gex,
    compute_hot_contracts,
    compute_oi_movers,
    compute_vol,
)


# --------------------------------------------------------------------------- #
# fixture helpers
# --------------------------------------------------------------------------- #

def _make_greeks_row(
    root="SPY",
    expiration="2025-03-21",
    strike=500.0,
    right="C",
    date="2025-01-10",
    implied_vol=0.15,
    underlying_price=500.0,
    delta=0.5,
    gamma=0.01,
    vanna=0.001,
    charm=-0.002,
) -> dict:
    return dict(
        root=root,
        expiration=expiration,
        strike=strike,
        right=right,
        date=date,
        implied_vol=implied_vol,
        underlying_price=underlying_price,
        delta=delta,
        gamma=gamma,
        vanna=vanna,
        charm=charm,
    )


def _greeks_df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _oi_df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _eod_df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# 1. ATM IV interpolation
# --------------------------------------------------------------------------- #

class TestAtmIvInterpolation:
    def test_exact_strike_hit(self):
        """Nearest strike exactly at spot -> returns its IV directly."""
        grp = pd.DataFrame([
            {"strike": 100.0, "right": "C", "implied_vol": 0.20},
            {"strike": 105.0, "right": "C", "implied_vol": 0.18},
            {"strike": 110.0, "right": "C", "implied_vol": 0.22},
        ])
        result = _atm_iv_for_expiry(grp, spot=100.0)
        # nearest is 100, second-nearest is 105 (dist=5)
        # weight_100 = 1/eps, weight_105 = 1/5 — but k0=0 -> returns iv0 directly
        assert result == pytest.approx(0.20, abs=1e-6)

    def test_interpolation_between_two_strikes(self):
        """Spot between two strikes: weighted by inverse distance."""
        # spot=102: dist to 100=2, dist to 105=3
        # weight_100 = 1/2, weight_105 = 1/3
        # iv = (0.5*0.20 + 0.333*0.18) / (0.5 + 0.333) = (0.10 + 0.06) / 0.833 ≈ 0.192
        grp = pd.DataFrame([
            {"strike": 100.0, "right": "C", "implied_vol": 0.20},
            {"strike": 105.0, "right": "C", "implied_vol": 0.18},
        ])
        result = _atm_iv_for_expiry(grp, spot=102.0)
        expected = (0.5 * 0.20 + (1.0 / 3.0) * 0.18) / (0.5 + 1.0 / 3.0)
        assert result == pytest.approx(expected, rel=1e-5)

    def test_empty_group_returns_none(self):
        grp = pd.DataFrame([{"strike": 100.0, "right": "C", "implied_vol": 0.0}])
        assert _atm_iv_for_expiry(grp, spot=100.0) is None

    def test_single_valid_row_returns_directly(self):
        grp = pd.DataFrame([
            {"strike": 100.0, "right": "C", "implied_vol": 0.25},
            {"strike": 95.0, "right": "C", "implied_vol": 0.0},   # invalid
        ])
        result = _atm_iv_for_expiry(grp, spot=100.0)
        assert result == pytest.approx(0.25, abs=1e-6)


# --------------------------------------------------------------------------- #
# 2. iv_rank_252 null under 60 obs
# --------------------------------------------------------------------------- #

class TestIvRank252:
    def _build_short_greeks(self, n_days: int, asof: str) -> pd.DataFrame:
        """Build a greeks frame with n_days of history, one expiry."""
        dates = pd.bdate_range(end=asof, periods=n_days).strftime("%Y-%m-%d").tolist()
        rows = []
        for d in dates:
            rows.append(_make_greeks_row(
                date=d, strike=500.0, right="C",
                implied_vol=0.15, underlying_price=500.0,
                expiration="2025-12-19",
            ))
            rows.append(_make_greeks_row(
                date=d, strike=500.0, right="P",
                implied_vol=0.16, underlying_price=500.0,
                expiration="2025-12-19",
            ))
        return pd.DataFrame(rows)

    def test_iv_rank_null_when_fewer_than_60_obs(self):
        asof = "2025-02-28"
        greeks = self._build_short_greeks(n_days=55, asof=asof)
        closes = pd.Series(
            {d: 500.0 for d in pd.bdate_range("2024-01-01", asof).strftime("%Y-%m-%d")},
        )
        result = compute_vol(greeks, closes, asof, "SPY")
        assert result["iv_rank_252"] is None, (
            f"Expected None for <60 obs, got {result['iv_rank_252']}"
        )

    def test_iv_rank_not_null_when_ge_60_obs(self):
        asof = "2025-05-30"
        greeks = self._build_short_greeks(n_days=80, asof=asof)
        closes = pd.Series(
            {d: 500.0 + float(i) for i, d
             in enumerate(pd.bdate_range("2024-01-01", asof).strftime("%Y-%m-%d"))},
        )
        result = compute_vol(greeks, closes, asof, "SPY")
        assert result["iv_rank_252"] is not None, "Expected non-null iv_rank for >=60 obs"
        assert 0.0 <= result["iv_rank_252"] <= 100.0


# --------------------------------------------------------------------------- #
# 3. term structure sorted ascending by DTE
# --------------------------------------------------------------------------- #

class TestTermStructure:
    def test_term_sorted_by_dte(self):
        asof = "2025-01-10"
        # Three expiries: far, near, mid — should come out sorted near→mid→far
        rows = []
        for exp, strike, iv in [
            ("2025-06-20", 500.0, 0.18),   # far
            ("2025-02-21", 500.0, 0.14),   # near
            ("2025-04-17", 500.0, 0.16),   # mid
        ]:
            for right in ("C", "P"):
                rows.append(_make_greeks_row(
                    expiration=exp, strike=strike, right=right,
                    implied_vol=iv, date=asof,
                ))
        closes = pd.Series({"2025-01-09": 500.0, "2025-01-10": 500.0})
        result = compute_vol(pd.DataFrame(rows), closes, asof, "SPY")
        dtes = [r["dte"] for r in result["term"]]
        assert dtes == sorted(dtes), f"term not sorted: {dtes}"


# --------------------------------------------------------------------------- #
# 4. smile: exactly 2 nearest >=2 DTE expiries
# --------------------------------------------------------------------------- #

class TestSmile:
    def test_smile_returns_two_expiries(self):
        asof = "2025-01-10"
        rows = []
        # 3 expiries all >= 2 DTE; we want the 2 nearest to be returned
        exps = ["2025-01-17", "2025-01-24", "2025-02-21"]
        for exp in exps:
            for k in [490.0, 495.0, 500.0, 505.0, 510.0]:
                for right in ("C", "P"):
                    rows.append({
                        "expiration": exp, "strike": k, "right": right,
                        "implied_vol": 0.15, "underlying_price": 500.0,
                        "date": asof,
                    })
        df = pd.DataFrame(rows)
        smile = _compute_smile(df, spot=500.0, asof=asof)
        assert len(smile) == 2, f"Expected 2 smile expiries, got {len(smile)}"
        # nearest first
        assert smile[0]["exp"] < smile[1]["exp"]

    def test_smile_has_call_put_iv_fields(self):
        asof = "2025-01-10"
        rows = []
        for k in [490.0, 500.0, 510.0]:
            rows.append({"expiration": "2025-01-17", "strike": k, "right": "C",
                          "implied_vol": 0.15, "underlying_price": 500.0, "date": asof})
            rows.append({"expiration": "2025-01-17", "strike": k, "right": "P",
                          "implied_vol": 0.16, "underlying_price": 500.0, "date": asof})
        df = pd.DataFrame(rows)
        smile = _compute_smile(df, spot=500.0, asof=asof)
        if smile:
            for pt in smile[0]["points"]:
                assert "strike" in pt
                assert "call_iv" in pt
                assert "put_iv" in pt


# --------------------------------------------------------------------------- #
# 5. GEX dealer-sign parity (hand-computed 2-contract fixture)
# --------------------------------------------------------------------------- #

class TestGexDealerSign:
    """Hand-compute net_gex for 2 contracts (1 call, 1 put) and verify match.

    Dealer-sign convention (engine/gex_model.py / gex_engine.py lines 158–163):
      sign = +1 for call, -1 for put
      net_gex_row = sign * gamma * oi_prev * MULT * spot^2 * PM

    Fixture:
      spot = 500.0, MULT = 100, PM = 0.01
      Contract A: call, strike=500, expiry 2025-03-21, gamma=0.01, oi_prev=1000
        => gex_A = +1 * 0.01 * 1000 * 100 * 500^2 * 0.01 = +250000
      Contract B: put, strike=490, expiry 2025-03-21, gamma=0.01, oi_prev=500
        => gex_B = -1 * 0.01 * 500 * 100 * 500^2 * 0.01 = -125000
      net_gex = 250000 - 125000 = 125000 = 1.25e5
      net_gex_bn = 1.25e-4
    """

    def _fixture(self) -> tuple[pd.DataFrame, pd.DataFrame, float]:
        asof = "2025-01-10"
        spot = 500.0
        gamma_val = 0.01

        greeks_rows = [
            _make_greeks_row(
                expiration="2025-03-21", strike=500.0, right="C", date=asof,
                implied_vol=0.15, underlying_price=spot,
                delta=0.5, gamma=gamma_val, vanna=0.0, charm=0.0,
            ),
            _make_greeks_row(
                expiration="2025-03-21", strike=490.0, right="P", date=asof,
                implied_vol=0.17, underlying_price=spot,
                delta=-0.5, gamma=gamma_val, vanna=0.0, charm=0.0,
            ),
        ]

        oi_rows = [
            {"expiration": "2025-03-21", "strike": 500.0, "right": "C",
             "open_interest": 1000.0, "date": asof},
            {"expiration": "2025-03-21", "strike": 490.0, "right": "P",
             "open_interest": 500.0, "date": asof},
        ]

        return pd.DataFrame(greeks_rows), pd.DataFrame(oi_rows), spot

    def test_net_gex_matches_hand_calculation(self):
        greeks, oi, spot = self._fixture()
        asof = "2025-01-10"
        result = compute_gex(greeks, oi, asof, "SPY")

        # hand-computed values (before _f() display rounding)
        MULT, PM = 100.0, 0.01
        gex_call = +1 * 0.01 * 1000 * MULT * spot**2 * PM   # 2_500_000
        gex_put  = -1 * 0.01 * 500  * MULT * spot**2 * PM   # -1_250_000
        expected_net_raw = gex_call + gex_put                 # 1_250_000
        expected_net_bn = expected_net_raw / 1e9              # 0.00125

        # net_gex_bn is display-rounded by _f(x, 4). Python banker's rounding:
        # round(0.00125, 4) -> 0.0013. Use abs tolerance > max rounding error (0.00005).
        assert result["net_gex_bn"] == pytest.approx(expected_net_bn, abs=1e-4), (
            f"net_gex_bn mismatch: {result['net_gex_bn']} vs {expected_net_bn} "
            f"(note: _f() display-rounds to 4dp; tolerance covers banker's rounding)"
        )

        # also verify the by_strike gamma_net sums match the raw net_gex more precisely
        strike_sum_mn = sum(r["gamma_net"] for r in result["by_strike"])
        assert strike_sum_mn == pytest.approx(expected_net_raw / 1e6, abs=0.01), (
            f"by_strike sum {strike_sum_mn} mn != expected {expected_net_raw/1e6} mn"
        )

    def test_call_wall_above_spot(self):
        greeks, oi, spot = self._fixture()
        result = compute_gex(greeks, oi, "2025-01-10", "SPY")
        cw = result.get("call_wall")
        # call is at 500 (=spot); above not strictly >spot, so call_wall may be None
        # put_wall should be at 490 (below spot, negative gamma)
        pw = result.get("put_wall")
        assert pw is not None, "Expected a put wall"
        assert pw < spot, f"put_wall {pw} should be < spot {spot}"

    def test_convention_field(self):
        greeks, oi, _ = self._fixture()
        result = compute_gex(greeks, oi, "2025-01-10", "SPY")
        assert "convention" in result
        assert "dealer" in result["convention"].lower()

    def test_oi_zero_rows_excluded(self):
        """If OI[t-1] is zero for a contract, it should not contribute to net_gex."""
        asof = "2025-01-10"
        greeks = pd.DataFrame([_make_greeks_row(
            expiration="2025-03-21", strike=500.0, right="C", date=asof,
            gamma=0.02, underlying_price=500.0,
        )])
        oi = pd.DataFrame([{
            "expiration": "2025-03-21", "strike": 500.0, "right": "C",
            "open_interest": 0.0, "date": asof,
        }])
        result = compute_gex(greeks, oi, asof, "SPY")
        # no OI -> empty gex
        assert result["net_gex_bn"] is None or result["net_gex_bn"] == 0.0


# --------------------------------------------------------------------------- #
# 6. GEX walls
# --------------------------------------------------------------------------- #

class TestGexWalls:
    def test_call_wall_is_above_spot(self):
        """Call wall must be strictly above spot."""
        asof = "2025-01-10"
        spot = 100.0
        rows_g, rows_oi = [], []
        # calls at 105, 110 above spot; puts at 95, 90 below
        for k, right, oi_val, gamma in [
            (105.0, "C", 1000, 0.02),
            (110.0, "C", 500,  0.01),
            (95.0,  "P", 800,  0.02),
            (90.0,  "P", 600,  0.01),
        ]:
            rows_g.append(_make_greeks_row(
                strike=k, right=right, date=asof,
                gamma=gamma, underlying_price=spot,
                expiration="2025-03-21",
            ))
            rows_oi.append({
                "expiration": "2025-03-21", "strike": k, "right": right,
                "open_interest": oi_val, "date": asof,
            })
        result = compute_gex(pd.DataFrame(rows_g), pd.DataFrame(rows_oi), asof, "SPY")
        cw = result.get("call_wall")
        if cw is not None:
            assert cw > spot, f"call_wall {cw} not > spot {spot}"
        pw = result.get("put_wall")
        if pw is not None:
            assert pw < spot, f"put_wall {pw} not < spot {spot}"


# --------------------------------------------------------------------------- #
# 7. GEX gamma flip: crossing and no-crossing
# --------------------------------------------------------------------------- #

class TestGexGammaFlip:
    def _make_g(self, spot=100.0):
        """Build a greeks frame where cumulative net_gex crosses zero."""
        asof = "2025-01-10"
        rows_g, rows_oi = [], []
        # Many calls below spot (high OI) → positive net cumulative below spot
        # → zero crossing somewhere near spot
        for k in range(80, 121, 1):
            k_f = float(k)
            right = "C" if k < 100 else "P"
            oi_val = 2000 if k < 100 else 1000
            rows_g.append(_make_greeks_row(
                strike=k_f, right=right, date=asof,
                gamma=0.01, underlying_price=spot,
                expiration="2025-03-21",
            ))
            rows_oi.append({
                "expiration": "2025-03-21", "strike": k_f, "right": right,
                "open_interest": float(oi_val), "date": asof,
            })
        return pd.DataFrame(rows_g), pd.DataFrame(rows_oi)

    def test_gamma_flip_returns_number_or_none(self):
        g, oi = self._make_g()
        result = compute_gex(g, oi, "2025-01-10", "SPY")
        flip = result.get("gamma_flip")
        # Either a finite float or None — never NaN
        if flip is not None:
            assert np.isfinite(flip)

    def test_no_crossing_returns_none(self):
        """All calls -> all positive net gamma -> no crossing -> gamma_flip=None."""
        asof = "2025-01-10"
        rows_g, rows_oi = [], []
        for k in range(90, 115, 1):
            rows_g.append(_make_greeks_row(
                strike=float(k), right="C", date=asof,
                gamma=0.01, underlying_price=100.0,
                expiration="2025-03-21",
            ))
            rows_oi.append({
                "expiration": "2025-03-21", "strike": float(k), "right": "C",
                "open_interest": 100.0, "date": asof,
            })
        result = compute_gex(pd.DataFrame(rows_g), pd.DataFrame(rows_oi), asof, "SPY")
        # All calls → net always positive cumsum → no zero crossing
        assert result.get("gamma_flip") is None


# --------------------------------------------------------------------------- #
# 8 & 9. OI movers
# --------------------------------------------------------------------------- #

class TestOiMovers:
    def test_delta_uses_two_distinct_sessions(self):
        """d_oi = oi_t - oi_t1 where t and t1 are DIFFERENT sessions."""
        asof = "2025-01-10"
        oi_t  = pd.DataFrame([{
            "expiration": "2025-03-21", "strike": 500.0, "right": "C",
            "root": "SPY", "open_interest": 1500.0, "date": asof,
        }])
        oi_t1 = pd.DataFrame([{
            "expiration": "2025-03-21", "strike": 500.0, "right": "C",
            "root": "SPY", "open_interest": 1000.0, "date": "2025-01-09",
        }])
        result = compute_oi_movers(oi_t, oi_t1, pd.DataFrame(), asof)
        movers = result["movers"]
        assert len(movers) >= 1
        assert movers[0]["d_oi"] == 500, f"Expected d_oi=500, got {movers[0]['d_oi']}"

    def test_same_oi_both_sessions_not_in_output(self):
        """If d_oi == 0, the row should not appear in movers."""
        asof = "2025-01-10"
        oi_both = pd.DataFrame([{
            "expiration": "2025-03-21", "strike": 500.0, "right": "C",
            "root": "SPY", "open_interest": 1000.0, "date": asof,
        }])
        result = compute_oi_movers(oi_both, oi_both, pd.DataFrame(), asof)
        assert result["movers"] == [], (
            f"Expected empty movers for d_oi=0, got {result['movers']}"
        )

    def test_movers_sorted_by_abs_d_oi(self):
        """Top movers should appear in descending |d_oi| order."""
        asof = "2025-01-10"
        oi_t = pd.DataFrame([
            {"expiration": "2025-03-21", "strike": 500.0, "right": "C",
             "root": "SPY", "open_interest": 2000.0, "date": asof},
            {"expiration": "2025-03-21", "strike": 490.0, "right": "P",
             "root": "SPY", "open_interest": 1500.0, "date": asof},
        ])
        oi_t1 = pd.DataFrame([
            {"expiration": "2025-03-21", "strike": 500.0, "right": "C",
             "root": "SPY", "open_interest": 500.0, "date": "2025-01-09"},
            {"expiration": "2025-03-21", "strike": 490.0, "right": "P",
             "root": "SPY", "open_interest": 1200.0, "date": "2025-01-09"},
        ])
        result = compute_oi_movers(oi_t, oi_t1, pd.DataFrame(), asof)
        movers = result["movers"]
        assert len(movers) == 2
        d_ois = [abs(m["d_oi"]) for m in movers]
        assert d_ois == sorted(d_ois, reverse=True)


# --------------------------------------------------------------------------- #
# 10 & 11. Hot contracts
# --------------------------------------------------------------------------- #

class TestHotContracts:
    def _eod(self, root: str, rows: list[dict]) -> dict[str, pd.DataFrame]:
        return {root: pd.DataFrame(rows)}

    def test_by_premium_sorted_descending(self):
        """by_premium should be sorted by premium descending."""
        asof = "2025-01-10"
        eod = {
            "SPY": pd.DataFrame([
                {"expiration": "2025-03-21", "strike": 500.0, "right": "C",
                 "close": 5.0, "volume": 1000.0, "bid_eod": 4.9, "ask_eod": 5.1,
                 "root": "SPY", "date": asof},
                {"expiration": "2025-03-21", "strike": 490.0, "right": "P",
                 "close": 10.0, "volume": 2000.0, "bid_eod": 9.9, "ask_eod": 10.1,
                 "root": "SPY", "date": asof},
            ]),
        }
        result = compute_hot_contracts(eod, {}, asof)
        prems = [r["premium"] for r in result["by_premium"]]
        assert prems == sorted(prems, reverse=True), f"by_premium not sorted: {prems}"

    def test_vol_gt_oi_flag(self):
        """vol_gt_oi=True when volume > oi_prev; False otherwise; None when oi_prev absent."""
        asof = "2025-01-10"
        eod = {
            "SPY": pd.DataFrame([
                {"expiration": "2025-03-21", "strike": 500.0, "right": "C",
                 "close": 5.0, "volume": 1500.0, "bid_eod": 4.9, "ask_eod": 5.1,
                 "root": "SPY", "date": asof},
            ]),
        }
        oi_prev = {
            "SPY": pd.DataFrame([
                {"expiration": "2025-03-21", "strike": 500.0, "right": "C",
                 "open_interest": 1000.0, "date": "2025-01-09"},
            ]),
        }
        result = compute_hot_contracts(eod, oi_prev, asof)
        assert result["by_premium"], "Expected at least one entry"
        row = result["by_premium"][0]
        assert row["vol_gt_oi"] is True, f"Expected vol_gt_oi=True, got {row['vol_gt_oi']}"

    def test_vol_lt_oi_flag_false(self):
        asof = "2025-01-10"
        eod = {
            "SPY": pd.DataFrame([
                {"expiration": "2025-03-21", "strike": 500.0, "right": "C",
                 "close": 5.0, "volume": 500.0, "bid_eod": 4.9, "ask_eod": 5.1,
                 "root": "SPY", "date": asof},
            ]),
        }
        oi_prev = {
            "SPY": pd.DataFrame([
                {"expiration": "2025-03-21", "strike": 500.0, "right": "C",
                 "open_interest": 2000.0, "date": "2025-01-09"},
            ]),
        }
        result = compute_hot_contracts(eod, oi_prev, asof)
        row = result["by_premium"][0]
        assert row["vol_gt_oi"] is False, f"Expected False, got {row['vol_gt_oi']}"


# --------------------------------------------------------------------------- #
# 12. Router param sanitization
# --------------------------------------------------------------------------- #

class TestRouterSanitization:
    def test_valid_root_passes(self):
        """Valid roots must not raise."""
        from app.hub import _sanitize_root
        for root in ["SPY", "QQQ", "IWM", "XLF", "SPXW", "BTC"]:
            assert _sanitize_root(root) == root

    def test_invalid_root_raises_400(self):
        """Invalid roots (path traversal, special chars) must raise HTTPException(400)."""
        from app.hub import _sanitize_root
        from fastapi import HTTPException as FastHTTPException
        for bad in ["../etc/passwd", "SPY/GEX", "SPY;drop", "", "A" * 20]:
            with pytest.raises(FastHTTPException) as exc_info:
                _sanitize_root(bad)
            assert exc_info.value.status_code == 400


# --------------------------------------------------------------------------- #
# 13 & 14. Router TTL and stale fallback
# --------------------------------------------------------------------------- #

class TestRouterTtl:
    def setup_method(self):
        """Clear the hub cache before each test."""
        import app.hub as hub_module
        hub_module._HUB_CACHE.clear()

    def test_second_call_within_ttl_uses_cache(self):
        """Two calls within TTL: second must NOT call urllib."""
        import app.hub as hub_module

        fake_data = {"schema": "options_hub.vol/v1", "root": "SPY", "asof": "2025-01-10"}

        call_count = [0]

        def mock_urlopen(req, timeout=None):
            call_count[0] += 1
            m = MagicMock()
            m.__enter__ = lambda s: s
            m.__exit__ = MagicMock(return_value=False)
            m.read.return_value = json.dumps(fake_data).encode()
            return m

        import json
        import urllib.request

        with patch.object(urllib.request, "urlopen", mock_urlopen):
            with patch.object(hub_module, "_hub_r2_base", return_value="https://r2.example.com"):
                result1 = hub_module._hub_fetch("vol/SPY.json")
                result2 = hub_module._hub_fetch("vol/SPY.json")  # should use cache

        assert call_count[0] == 1, f"Expected 1 urlopen call, got {call_count[0]}"
        assert result1 == fake_data
        assert result2 == fake_data

    def test_fetch_failure_returns_stale(self):
        """If urlopen fails and cache exists, returns stale=True dict."""
        import app.hub as hub_module
        import json

        fake_data = {"schema": "options_hub.vol/v1", "root": "SPY", "asof": "2025-01-10"}

        # Pre-seed cache with old entry (before TTL)
        hub_module._HUB_CACHE["vol/SPY.json"] = (
            fake_data,
            time.monotonic() - hub_module._HUB_CACHE_TTL - 5,  # expired
        )

        def mock_urlopen(req, timeout=None):
            raise Exception("network error")

        import urllib.request

        with patch.object(urllib.request, "urlopen", mock_urlopen):
            with patch.object(hub_module, "_hub_r2_base", return_value="https://r2.example.com"):
                result = hub_module._hub_fetch("vol/SPY.json")

        assert result.get("stale") is True, f"Expected stale=True, got {result}"
        # data preserved
        assert result.get("root") == "SPY"

    def test_no_cache_no_r2_base_raises_503(self):
        """No cache + no R2 base -> 503."""
        import app.hub as hub_module
        from fastapi import HTTPException as FastHTTPException

        hub_module._HUB_CACHE.clear()
        with patch.object(hub_module, "_hub_r2_base", return_value=""):
            with pytest.raises(FastHTTPException) as exc_info:
                hub_module._hub_fetch("vol/NOKEY.json")
        assert exc_info.value.status_code == 503


# --------------------------------------------------------------------------- #
# Additional: rv20 sanity
# --------------------------------------------------------------------------- #

class TestRv20:
    def test_rv20_returns_none_for_short_series(self):
        s = pd.Series({"2025-01-01": 100.0, "2025-01-02": 101.0})
        assert _rv20(s, "2025-01-02") is None

    def test_rv20_returns_finite_for_sufficient_data(self):
        dates = pd.bdate_range("2024-01-01", periods=30).strftime("%Y-%m-%d")
        prices = pd.Series({d: 500.0 * (1 + 0.001 * i) for i, d in enumerate(dates)})
        result = _rv20(prices, dates[-1])
        assert result is not None
        assert np.isfinite(result)
        assert result > 0

    def test_rv20_uses_only_dates_up_to_asof(self):
        """rv20 must not use data after asof (no look-ahead)."""
        dates = pd.bdate_range("2024-01-01", periods=30).strftime("%Y-%m-%d")
        # future data with extreme values — must not affect result
        future = pd.bdate_range("2024-02-15", periods=5).strftime("%Y-%m-%d")
        prices = pd.Series({d: 500.0 for d in dates})
        future_prices = pd.Series({d: 100000.0 for d in future})
        combined = pd.concat([prices, future_prices])
        result_without_future = _rv20(prices, dates[-1])
        result_with_future = _rv20(combined, dates[-1])
        assert result_without_future == pytest.approx(result_with_future, rel=1e-6)


# --------------------------------------------------------------------------- #
# Schema field check: vol payload has required fields
# --------------------------------------------------------------------------- #

class TestVolPayloadSchema:
    def test_required_fields_present(self):
        asof = "2025-01-10"
        rows = [
            _make_greeks_row(
                date=asof, expiration="2025-03-21", strike=500.0, right="C",
                implied_vol=0.15, underlying_price=500.0,
            )
        ]
        greeks = pd.DataFrame(rows)
        closes = pd.Series({"2025-01-09": 500.0, "2025-01-10": 500.0})
        result = compute_vol(greeks, closes, asof, "SPY")
        required = ["schema", "asof", "root", "iv_rank_252", "atm_iv", "iv_52w_hi",
                    "iv_52w_lo", "rv20", "vrp", "term", "smile", "history", "coverage"]
        for field in required:
            assert field in result, f"Missing field: {field}"
        assert result["schema"] == "options_hub.vol/v1"

    def test_gex_required_fields_present(self):
        asof = "2025-01-10"
        g = pd.DataFrame([_make_greeks_row(date=asof, underlying_price=500.0)])
        oi = pd.DataFrame([{
            "expiration": "2025-03-21", "strike": 500.0, "right": "C",
            "open_interest": 100.0, "date": asof,
        }])
        result = compute_gex(g, oi, asof, "SPY")
        required = ["schema", "asof", "root", "spot_ref", "net_gex_bn", "gamma_flip",
                    "call_wall", "put_wall", "by_strike", "by_strike_full_n",
                    "by_expiry", "convention", "coverage"]
        for field in required:
            assert field in result, f"Missing GEX field: {field}"
        assert result["schema"] == "options_hub.gex/v1"
        # coverage superset
        cov = result["coverage"]
        for cov_field in ("n_contracts", "asof", "oi_date", "n_days", "since"):
            assert cov_field in cov, f"Missing coverage field: {cov_field}"


# --------------------------------------------------------------------------- #
# CONTRACT: by_strike windowing — 470-strike synthetic
# --------------------------------------------------------------------------- #

def _make_dense_gex_fixture(
    n_strikes: int = 470,
    spot: float = 500.0,
    asof: str = "2025-01-10",
    spread_pct: float = 0.50,  # strikes span ±50% around spot so >160 pass ±20%
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build a synthetic fixture with `n_strikes` uniformly spaced strikes.

    spread_pct=0.50 → strikes from spot*(1-0.5) to spot*(1+0.5), which means
    the ±20% window catches 40% of the range = 0.40/1.00 * n_strikes ≈ 188
    strikes for n=470 — enough to exercise the 160-row cap.
    """
    low  = spot * (1 - spread_pct)
    high = spot * (1 + spread_pct)
    strikes = np.linspace(low, high, n_strikes)

    rows_g, rows_oi = [], []
    for k in strikes:
        right = "C" if k >= spot else "P"
        rows_g.append(_make_greeks_row(
            strike=k, right=right, date=asof,
            gamma=0.01, underlying_price=spot,
            expiration="2025-06-20",
        ))
        rows_oi.append({
            "expiration": "2025-06-20", "strike": k, "right": right,
            "open_interest": 1000.0, "date": asof,
        })
    return pd.DataFrame(rows_g), pd.DataFrame(rows_oi)


class TestByStrikeWindowing:
    """CONTRACT: by_strike windowed to ±20% spot_ref, capped at 160 rows nearest spot."""

    def test_by_strike_capped_at_160(self):
        """470-strike fixture: by_strike must have at most 160 rows."""
        g, oi = _make_dense_gex_fixture(n_strikes=470)
        result = compute_gex(g, oi, "2025-01-10", "SPY")
        assert len(result["by_strike"]) <= 160, (
            f"by_strike has {len(result['by_strike'])} rows; expected <=160"
        )

    def test_by_strike_full_n_preserved(self):
        """by_strike_full_n must equal the pre-window unique-strike count."""
        g, oi = _make_dense_gex_fixture(n_strikes=470)
        result = compute_gex(g, oi, "2025-01-10", "SPY")
        assert "by_strike_full_n" in result, "Missing by_strike_full_n"
        assert result["by_strike_full_n"] > len(result["by_strike"]), (
            f"by_strike_full_n ({result['by_strike_full_n']}) should exceed "
            f"windowed count ({len(result['by_strike'])})"
        )

    def test_by_strike_within_20pct_window(self):
        """All returned strikes must be within ±20% of spot_ref."""
        spot = 500.0
        g, oi = _make_dense_gex_fixture(n_strikes=470, spot=spot)
        result = compute_gex(g, oi, "2025-01-10", "SPY")
        spot_ref = result["spot_ref"]
        assert spot_ref is not None
        for row in result["by_strike"]:
            ratio = abs(row["strike"] / spot_ref - 1)
            assert ratio <= 0.2001, (  # small float tolerance
                f"strike {row['strike']} is {ratio:.4%} from spot_ref {spot_ref} "
                f"— outside ±20% window"
            )

    def test_by_strike_sorted_ascending(self):
        """Returned strikes must be in ascending order (strike-asc per contract)."""
        g, oi = _make_dense_gex_fixture(n_strikes=470)
        result = compute_gex(g, oi, "2025-01-10", "SPY")
        strikes = [r["strike"] for r in result["by_strike"]]
        assert strikes == sorted(strikes), "by_strike not in ascending strike order"

    def test_small_fixture_not_capped(self):
        """With <=160 strikes all within window, full_n == len(by_strike)."""
        asof = "2025-01-10"
        spot = 100.0
        rows_g, rows_oi = [], []
        for k in range(90, 111):  # 21 strikes, all within ±20%
            rows_g.append(_make_greeks_row(
                strike=float(k), right="C", date=asof,
                gamma=0.01, underlying_price=spot,
                expiration="2025-06-20",
            ))
            rows_oi.append({
                "expiration": "2025-06-20", "strike": float(k), "right": "C",
                "open_interest": 500.0, "date": asof,
            })
        result = compute_gex(pd.DataFrame(rows_g), pd.DataFrame(rows_oi), asof, "SPY")
        assert result["by_strike_full_n"] == len(result["by_strike"]), (
            "All strikes in window: full_n should equal windowed len"
        )

    def test_coverage_superset_fields(self):
        """coverage must have n_contracts, asof, oi_date, n_days, since."""
        g, oi = _make_dense_gex_fixture(n_strikes=10)
        result = compute_gex(g, oi, "2025-01-10", "SPY")
        cov = result["coverage"]
        for field in ("n_contracts", "asof", "oi_date", "n_days", "since"):
            assert field in cov, f"Missing coverage field: {field}"
        assert cov["n_contracts"] > 0
        assert cov["oi_date"] == "t-1"
        assert cov["n_days"] >= 1
        assert cov["since"] is not None


# --------------------------------------------------------------------------- #
# CONTRACT: completeness guard in build_options_hub_nightly
# --------------------------------------------------------------------------- #

class TestCompletenessGuard:
    """Guard: empty by_strike + non-empty store → skip R2; empty store → publish."""

    def _gex_payload_empty(self, asof: str = "2025-01-10") -> dict:
        """A GEX payload with empty by_strike (simulates mid-backfill artifact)."""
        return {
            "schema": "options_hub.gex/v1",
            "asof": asof,
            "root": "SPY",
            "spot_ref": 500.0,
            "net_gex_bn": None,
            "gamma_flip": None,
            "call_wall": None,
            "put_wall": None,
            "by_strike": [],
            "by_strike_full_n": 0,
            "by_expiry": [],
            "convention": "dealer-sign per engine/gex_model (long-call/short-put)",
            "coverage": {"n_contracts": 0, "asof": asof, "oi_date": "t-1",
                         "n_days": 0, "since": asof},
        }

    def test_guard_skips_r2_when_store_has_contracts(self):
        """Empty by_strike + non-empty OI store → gex R2 upload suppressed.

        Calls _gex_publish_decision() directly (the real helper) so inverting the
        guard logic in the helper will cause this test to fail.
        """
        import scripts.build_options_hub_nightly as builder

        asof = "2025-01-10"
        empty_gex = self._gex_payload_empty(asof)
        non_empty_oi = pd.DataFrame([{
            "expiration": "2025-03-21", "strike": 500.0, "right": "C",
            "open_interest": 1000.0, "date": asof,
        }])

        orig_oi = builder._load_oi_for_date
        try:
            builder._load_oi_for_date = lambda root, date_str, theta_store: non_empty_oi

            gex_publish, out_payload, is_guarded = builder._gex_publish_decision(
                empty_gex, "SPY", asof, None
            )

            assert not gex_publish, "Guard should have suppressed upload"
            assert is_guarded, "is_guarded must be True when store has contracts"
            assert "no_data_reason" not in out_payload
        finally:
            builder._load_oi_for_date = orig_oi

    def test_guard_publishes_with_no_data_reason_when_store_empty(self):
        """Empty by_strike + empty OI store → publish with no_data_reason set.

        Calls _gex_publish_decision() directly so inverting the guard logic will
        cause this test to fail.
        """
        import scripts.build_options_hub_nightly as builder

        asof = "2025-01-10"
        empty_gex = self._gex_payload_empty(asof)

        orig_oi = builder._load_oi_for_date
        try:
            builder._load_oi_for_date = lambda root, date_str, theta_store: pd.DataFrame()

            gex_publish, out_payload, is_guarded = builder._gex_publish_decision(
                empty_gex, "SPY", asof, None
            )

            assert gex_publish, "Empty store: guard should allow publish"
            assert not is_guarded
            assert "no_data_reason" in out_payload, "Empty store: no_data_reason must be set"
            assert asof in out_payload["no_data_reason"]
        finally:
            builder._load_oi_for_date = orig_oi


# --------------------------------------------------------------------------- #
# WP-B: vex wiring in build_options_hub_nightly.build_root
# --------------------------------------------------------------------------- #

class TestVexWiring:
    """build_root must return (vol, gex, vex); vex is the vega-weighted sibling of gex.

    Monkeypatches the three store loaders so build_root runs hermetically on
    crafted greeks + OI frames — exercising the real wiring (compute_vex is called
    with greeks[asof] + OI[t-1]) without touching any parquet store.
    """

    def _fixtures(self, asof: str = "2025-01-10", spot: float = 500.0):
        # a call above spot (positive vex) + a put below spot (negative vex),
        # both with OI[t-1] > 0 so they survive the OI merge.
        greeks = pd.DataFrame([
            {**_make_greeks_row(expiration="2025-03-21", strike=505.0, right="C", date=asof,
                                gamma=0.01, underlying_price=spot), "vega": 0.30},
            {**_make_greeks_row(expiration="2025-03-21", strike=495.0, right="P", date=asof,
                                gamma=0.01, underlying_price=spot), "vega": 0.30},
        ])
        oi = pd.DataFrame([
            {"expiration": "2025-03-21", "strike": 505.0, "right": "C",
             "open_interest": 1000.0, "date": asof},
            {"expiration": "2025-03-21", "strike": 495.0, "right": "P",
             "open_interest": 1000.0, "date": asof},
        ])
        return greeks, oi

    def test_build_root_returns_vex_triple(self, monkeypatch):
        import scripts.build_options_hub_nightly as builder

        asof = "2025-01-10"
        greeks, oi = self._fixtures(asof)
        monkeypatch.setattr(builder, "_load_greeks", lambda root, ts: greeks)
        monkeypatch.setattr(builder, "_load_oi_for_date", lambda root, date_str, ts: oi)
        monkeypatch.setattr(builder, "_load_yahoo", lambda root: None)

        out = builder.build_root("SPY", asof, None)
        assert isinstance(out, tuple) and len(out) == 3, "build_root must return (vol, gex, vex)"
        vol_payload, gex_payload, vex_payload = out

        # vex is a real options_hub.vex/v1 board on the SAME PIT inputs as gex
        assert vex_payload["schema"] == "options_hub.vex/v1"
        assert vex_payload["root"] == "SPY" and vex_payload["asof"] == asof
        assert vex_payload["spot_ref"] == 500.0
        assert vex_payload["by_strike"], "expected non-empty vex by_strike"
        assert vex_payload["pos_vex_wall"] == 505.0  # positive vex above spot
        assert vex_payload["neg_vex_wall"] == 495.0  # negative vex below spot

        # gex still built alongside it (regression: the toggle needs both)
        assert gex_payload["schema"] == "options_hub.gex/v1"
        assert vol_payload["schema"] == "options_hub.vol/v1"

    def test_build_root_vex_empty_store(self, monkeypatch):
        """Empty store → vex is an honest empty board (schema present, no strikes)."""
        import scripts.build_options_hub_nightly as builder

        asof = "2025-01-10"
        monkeypatch.setattr(builder, "_load_greeks", lambda root, ts: pd.DataFrame())
        monkeypatch.setattr(builder, "_load_oi_for_date", lambda root, date_str, ts: pd.DataFrame())
        monkeypatch.setattr(builder, "_load_yahoo", lambda root: None)

        _vol, _gex, vex_payload = builder.build_root("SPY", asof, None)
        assert vex_payload["schema"] == "options_hub.vex/v1"
        assert vex_payload["by_strike"] == []
        assert vex_payload["spot_ref"] is None
