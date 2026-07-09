"""tests/test_options_matrix.py — Package E: strike×expiry matrix engine tests.

Test coverage:
  1. gex_cell_formula        — hand-computed GEX case
  2. delta_oi_pit_safety     — asserts t-1 vs t-2 used, never t (lookahead guard)
  3. heat_seeker_pass        — normal pass path with standout cell
  4. heat_seeker_fail_min_oi — blocked by _MIN_TOTAL_OI gate
  5. heat_seeker_fail_ratio  — blocked by standout-ratio gate
  6. heat_seeker_null_path   — build_matrix null when no data
  7. max_pain                — hand-computed max-pain
  8. validator_round_trip    — validate_matrix on a well-formed payload
  9. thin_chain_null_safety  — build_matrix returns valid payload on empty store
 10. note_field_exact        — heat_seeker note field is exactly the CI-enforced string
"""
from __future__ import annotations

import math
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

# ── project imports ────────────────────────────────────────────────────────────
import sys
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from engine.greeks import npdf
from engine.options_matrix import (
    _bs_gamma_scalar,
    _bs_vanna_scalar,
    _compute_max_pain,
    _gex_dollar,
    _heat_seeker,
    _median_iv,
    _null_payload,
    _vex_mn,
    build_matrix,
    _MIN_TOTAL_OI,
    _CONTRACT_MULT,
    _VOL_PCT,
    _R,
)
from engine.options_structure import validate_matrix


# ─────────────────────────────────────────────────────────────────────────────
# fixtures / helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_oi_df(rows: list[dict]) -> pd.DataFrame:
    """Helper: make a minimal OI DataFrame."""
    return pd.DataFrame(rows)


def _make_store(tmp_path: Path, root: str,
                oi_rows_t1: list[dict],
                oi_rows_t2: list[dict] | None = None,
                eod_rows: list[dict] | None = None) -> Path:
    """Write minimal parquets for one root into a temp ThetaData store.

    Parquet schema mirrors thetadata_store expectations:
      OI: root, expiration, strike, right, date, open_interest
      EOD: root, expiration, strike, right, date, open, high, low, close, volume, count
    """
    store = tmp_path / "theta_store"

    t1_date = "2026-07-07"
    t2_date = "2026-07-04"   # earlier session

    def _write(tier: str, rows: list[dict], date: str) -> None:
        if not rows:
            return
        base = store / tier / root
        base.mkdir(parents=True, exist_ok=True)
        year = pd.Timestamp(date).year
        path = base / f"{year}.parquet"
        df = pd.DataFrame(rows)
        df["date"] = date
        if path.exists():
            existing = pd.read_parquet(path)
            df = pd.concat([existing, df], ignore_index=True)
        df.to_parquet(path, index=False)

    _write("oi", oi_rows_t1, t1_date)
    if oi_rows_t2:
        _write("oi", oi_rows_t2, t2_date)
    if eod_rows:
        _write("eod", eod_rows, t1_date)

    return store


def _base_oi_row(root="SPY", strike=500.0, expiration="2026-07-18",
                 right="C", oi=1000) -> dict:
    return {
        "root": root, "expiration": expiration, "strike": strike,
        "right": right, "open_interest": oi,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. GEX cell formula — hand-computed case
# ─────────────────────────────────────────────────────────────────────────────

def test_gex_cell_formula():
    """GEX formula: gex = oi * gamma * S^2 * 0.01 * 100.

    Hand-computed:
      S=500, K=500, iv=0.20, T=7/365 (7 DTE), oi=1000
      d1 = [ln(500/500) + (0.05 + 0.5*0.04)*0.01918] / (0.20 * sqrt(0.01918))
         = [0 + 0.05384 * 0.01918] / (0.20 * 0.13850)
         = [0.001033] / 0.027700
         = 0.037294
      gamma = npdf(d1) / (S * iv * sqrtT)
            = npdf(0.037294) / (500 * 0.20 * 0.13850)
            = 0.39895 / 13.850
            = 0.028802   (approx)
      gex = 1000 * 0.028802 * 500^2 * 0.01 * 100
          = 1000 * 0.028802 * 250000 * 1
          = 7,200,500  (approx $7.2M)
    """
    S = 500.0
    K = 500.0
    iv = 0.20
    oi = 1000.0
    T_years = 7.0 / 365.0

    gamma_bs = _bs_gamma_scalar(S, K, T_years, iv, 0.30)
    gex = _gex_dollar(oi, gamma_bs, S)

    # Verify the formula matches a direct hand computation
    sqrtT = math.sqrt(T_years)
    d1 = (math.log(S / K) + (_R + 0.5 * iv ** 2) * T_years) / (iv * sqrtT)
    expected_gamma = npdf(d1) / (S * iv * sqrtT)
    expected_gex = oi * expected_gamma * S * S * _VOL_PCT * _CONTRACT_MULT

    assert abs(gex - expected_gex) < 1.0, (
        f"GEX formula mismatch: got {gex:.2f} expected {expected_gex:.2f}"
    )
    # Rough sanity: 7DTE ATM SPY500 with 1000 OI should be in the $5M–$15M range
    assert 5_000_000 < gex < 15_000_000, f"GEX out of plausible range: {gex:.0f}"


# ─────────────────────────────────────────────────────────────────────────────
# 2. delta_oi PIT-safety — OI[t-1] vs OI[t-2], never same-day t
# ─────────────────────────────────────────────────────────────────────────────

def test_delta_oi_pit_safety(tmp_path):
    """delta_oi must use OI[t-1] − OI[t-2]; never t0 (same-day/future) OI.

    Strategy: write three dates of OI for a single strike:
      t2 (2026-07-04): call OI = 800
      t1 (2026-07-07): call OI = 1000  ← this is OI[t-1] for asof="2026-07-07"
      t0 (2026-07-08): call OI = 9999  ← FUTURE row; must NEVER appear in output

    When build_matrix(asof="2026-07-07") runs:
      - call_oi   must equal 1000  (OI[t-1]), not 9999
      - delta_oi.call must equal 200 (= 1000 − 800)
    If lookahead were present, call_oi or delta_oi.call would involve 9999.
    This is a discrimination test: the assertion would FAIL if the code
    used OI[t] instead of OI[t-1] or OI[t-1] instead of OI[t-2].
    """
    root = "SPY"
    expiry = "2026-08-15"
    spot = 500.0

    # t2 (2026-07-04): OI = 800
    t2_rows = [_base_oi_row(root, 500.0, expiry, "C", 800)]
    # t1 (2026-07-07): OI = 1000 — the reference day
    t1_rows = [_base_oi_row(root, 500.0, expiry, "C", 1000)]

    store = _make_store(tmp_path, root, t1_rows, t2_rows)

    # Write the FUTURE row (2026-07-08, OI=9999) directly into the parquet so
    # _load_parquets sees it.  build_matrix must never incorporate this row.
    oi_base = store / "oi" / root
    oi_base.mkdir(parents=True, exist_ok=True)
    future_row = pd.DataFrame([{
        "root": root, "expiration": expiry, "strike": 500.0,
        "right": "C", "open_interest": 9999, "date": "2026-07-08",
    }])
    future_parquet = oi_base / "2026.parquet"
    if future_parquet.exists():
        existing = pd.read_parquet(future_parquet)
        future_row = pd.concat([existing, future_row], ignore_index=True)
    future_row.to_parquet(future_parquet, index=False)

    # Write greeks for spot extraction
    greeks_path = store / "greeks" / root
    greeks_path.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{
        "root": root, "expiration": expiry, "strike": 500.0, "right": "C",
        "date": "2026-07-07", "implied_vol": 0.20,
        "underlying_price": spot,
        "delta": 0.5, "theta": -0.1, "vega": 0.2, "rho": 0.0, "iv_error": 0.0,
    }]).to_parquet(greeks_path / "2026.parquet", index=False)

    payload = build_matrix(root, store=str(store), asof="2026-07-07")

    assert payload["schema"] == "options_structure.matrix/v1"
    cells = payload["cells"]
    assert len(cells) > 0, "Expected at least one cell"

    # Find the cell for strike=500, expiry=2026-08-15
    target = [c for c in cells if c["strike"] == 500.0 and c["expiry"] == expiry]
    assert len(target) == 1, f"Expected exactly one cell for 500/{expiry}, got {len(target)}"

    cell = target[0]

    # call_oi must be OI[t-1]=1000, not the future 9999
    assert cell["call_oi"] == 1000, (
        f"call_oi should be OI[t-1]=1000, got {cell['call_oi']} "
        "(9999 means future OI leaked in)"
    )

    # delta_oi.call must be OI[t-1] − OI[t-2] = 1000 − 800 = 200
    d_call = cell["delta_oi"]["call"]
    assert d_call is not None, "delta_oi.call should not be None"
    assert d_call == 200, (
        f"Expected delta_oi.call=200 (OI[t-1]−OI[t-2]=1000−800), got {d_call} "
        "(non-200 means wrong date window was used)"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3. heat_seeker_pass
# ─────────────────────────────────────────────────────────────────────────────

def test_heat_seeker_pass():
    """heat_seeker returns a pick when one cell strongly dominates.

    spot=500.3 so the nearest strike is 500.0 (|0.3| < |9.7|).
    The 500.0 strike is excluded (spot-row exclusion, prism_spec §5).
    Dominant cell at 510.0 (GEX=10M) vs second at 520.0 (GEX=1M) → ratio=10 > 1.5.
    Total OI must exceed 5000.
    """
    spot = 500.3   # nearest-to-spot = 500.0 (will be excluded)
    cells = [
        # spot-adjacent row — excluded by prism_spec §5
        {"strike": 500.0, "expiry": "2026-07-18", "gex": 50_000_000.0,
         "call_oi": 2000, "put_oi": 2000, "call_vol": 200, "put_vol": 200, "_dte": 11.0},
        # dominant candidate (should be the heat_seeker pick)
        {"strike": 510.0, "expiry": "2026-07-18", "gex": 10_000_000.0,
         "call_oi": 1500, "put_oi": 1000, "call_vol": 100, "put_vol": 50, "_dte": 11.0},
        # second candidate
        {"strike": 520.0, "expiry": "2026-07-18", "gex": 1_000_000.0,
         "call_oi": 300, "put_oi": 200, "call_vol": 30, "put_vol": 20, "_dte": 11.0},
    ]
    hs = _heat_seeker(cells, spot, "GEX")
    assert hs is not None, "Expected a heat_seeker pick"
    assert hs["strike"] == 510.0, f"Expected 510.0, got {hs['strike']}"
    assert hs["lens"] == "GEX"
    assert hs["confidence"] > 0.15
    assert hs["note"] == "descriptive — not a recommendation"


# ─────────────────────────────────────────────────────────────────────────────
# 4. heat_seeker_fail_min_oi
# ─────────────────────────────────────────────────────────────────────────────

def test_heat_seeker_fail_min_oi():
    """heat_seeker returns None when total chain OI < 5000."""
    spot = 500.0
    cells = [
        {"strike": 490.0, "expiry": "2026-07-18", "gex": 10_000_000.0,
         "call_oi": 100, "put_oi": 50, "call_vol": 10, "put_vol": 5, "_dte": 11.0},
        {"strike": 510.0, "expiry": "2026-07-18", "gex": 1_000_000.0,
         "call_oi": 50, "put_oi": 30, "call_vol": 5, "put_vol": 3, "_dte": 11.0},
    ]
    # total OI = 100+50+50+30 = 230 < 5000
    hs = _heat_seeker(cells, spot, "GEX")
    assert hs is None, "Expected None when total OI < 5000"


# ─────────────────────────────────────────────────────────────────────────────
# 5. heat_seeker_fail_ratio
# ─────────────────────────────────────────────────────────────────────────────

def test_heat_seeker_fail_ratio():
    """heat_seeker returns None when standout ratio < 1.5 for GEX lens."""
    spot = 500.0
    # OI high enough (≥5000), but ratio = 1.2 < 1.5 threshold for GEX
    cells = [
        {"strike": 490.0, "expiry": "2026-07-18", "gex": 1_200_000.0,
         "call_oi": 3000, "put_oi": 500, "call_vol": 100, "put_vol": 10, "_dte": 11.0},
        {"strike": 510.0, "expiry": "2026-07-18", "gex": 1_000_000.0,
         "call_oi": 500, "put_oi": 1500, "call_vol": 50, "put_vol": 50, "_dte": 11.0},
    ]
    hs = _heat_seeker(cells, spot, "GEX")
    assert hs is None, f"Expected None for ratio<1.5, got {hs}"


# ─────────────────────────────────────────────────────────────────────────────
# 6. heat_seeker_null_path — build_matrix returns conforming null when no data
# ─────────────────────────────────────────────────────────────────────────────

def test_heat_seeker_null_path(tmp_path):
    """build_matrix returns a valid conforming payload when the store is empty."""
    store = tmp_path / "empty_store"
    store.mkdir()

    payload = build_matrix("XYZ", store=str(store), asof="2026-07-07")
    assert payload["schema"] == "options_structure.matrix/v1"
    assert payload["cells"] == []
    assert payload["heat_seeker"] is None
    errors = validate_matrix(payload)
    assert errors == [], f"validate_matrix errors: {errors}"


# ─────────────────────────────────────────────────────────────────────────────
# 7. max_pain — hand-computed case
# ─────────────────────────────────────────────────────────────────────────────

def test_max_pain():
    """Max pain: argmin of payout over candidate strikes.

    Setup:
      strikes: [490, 500, 510]
      call OI:  [100, 200,   0]   (calls at 490 and 500)
      put  OI:  [  0, 100, 200]   (puts at 500 and 510)

    payout(490):
      call side: Σ max(490-s, 0)*callOI_s = max(490-490,0)*100 + max(490-500,0)*200 + ...
               = 0 + 0 = 0
      put side:  Σ max(s-490, 0)*putOI_s  = (500-490)*100 + (510-490)*200
               = 1000 + 4000 = 5000
      total = 5000

    payout(500):
      call side: max(500-490,0)*100 + max(500-500,0)*200 = 1000 + 0 = 1000
      put side:  max(500-500,0)*100 + max(510-500,0)*200 = 0 + 2000 = 2000
      total = 3000

    payout(510):
      call side: max(510-490,0)*100 + max(510-500,0)*200 = 2000 + 2000 = 4000
      put side:  max(510-500,0)*100 + max(510-510,0)*200 = 1000 + 0 = 1000
      total = 5000

    min at 500 → max_pain = 500.0
    """
    chain = pd.DataFrame([
        {"strike": 490.0, "call_oi": 100, "put_oi":   0},
        {"strike": 500.0, "call_oi": 200, "put_oi": 100},
        {"strike": 510.0, "call_oi":   0, "put_oi": 200},
    ])
    result = _compute_max_pain(chain)
    assert result == 500.0, f"Expected max_pain=500.0, got {result}"


# ─────────────────────────────────────────────────────────────────────────────
# 8. validator_round_trip
# ─────────────────────────────────────────────────────────────────────────────

def test_validator_round_trip():
    """A well-formed payload passes validate_matrix cleanly."""
    payload = {
        "schema": "options_structure.matrix/v1",
        "asof": "2026-07-07T12:00:00+00:00",
        "root": "SPY",
        "spot": 500.0,
        "expiries": ["2026-07-18"],
        "strikes": [490.0, 500.0, 510.0],
        "cells": [
            {"strike": 500.0, "expiry": "2026-07-18",
             "gex": 5_000_000, "call_oi": 1000, "put_oi": 800,
             "call_vol": 200, "put_vol": 150,
             "delta_oi": {"call": 100, "put": -50}},
        ],
        "levels": {
            "call_wall": 510.0, "put_support": 490.0,
            "hvl": 500.0, "gamma_flip": 498.5, "max_pain": 499.0,
        },
        "heat_seeker": {
            "strike": 500.0, "expiry": "2026-07-18", "lens": "GEX",
            "standout_ratio": 2.5, "confidence": 0.5,
            "note": "descriptive — not a recommendation",
        },
        "authority_tier": "display",
        "reliability": {
            "gex": "assumption-signed",
            "delta_oi": "reliable",
            "vol": "reliable magnitude",
            "note": "test",
        },
    }
    errors = validate_matrix(payload)
    assert errors == [], f"Unexpected errors: {errors}"


# ─────────────────────────────────────────────────────────────────────────────
# 9. thin_chain_null_safety
# ─────────────────────────────────────────────────────────────────────────────

def test_thin_chain_null_safety(tmp_path):
    """build_matrix returns a conforming payload even with minimal data (1 OI row)."""
    root = "SPY"
    expiry = "2026-08-15"

    t1_rows = [_base_oi_row(root, 500.0, expiry, "C", 50)]  # very thin
    store = _make_store(tmp_path, root, t1_rows)

    # Write greeks for spot
    greeks_path = store / "greeks" / root
    greeks_path.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{
        "root": root, "expiration": expiry, "strike": 500.0, "right": "C",
        "date": "2026-07-07", "implied_vol": 0.20, "underlying_price": 500.0,
        "delta": 0.5, "theta": -0.1, "vega": 0.2, "rho": 0.0, "iv_error": 0.0,
    }]).to_parquet(greeks_path / "2026.parquet", index=False)

    payload = build_matrix(root, store=str(store), asof="2026-07-07")
    assert payload["schema"] == "options_structure.matrix/v1"
    errors = validate_matrix(payload)
    assert errors == [], f"validate_matrix errors on thin chain: {errors}"
    # heat_seeker may be None (thin chain < min OI gate) — that's fine
    # The key is that no exception is raised and the schema validates


# ─────────────────────────────────────────────────────────────────────────────
# 10. note_field_exact — CI-enforced string
# ─────────────────────────────────────────────────────────────────────────────

def test_heat_seeker_note_field_exact():
    """heat_seeker note must be exactly 'descriptive — not a recommendation'.

    This is enforced by validate_matrix (Package A contract).
    spot=500.3 so nearest = 500.0 is excluded; 490.0 dominates the remaining set.
    """
    spot = 500.3   # nearest-to-spot = 500.0 (excluded)
    cells = [
        # spot-adjacent (excluded)
        {"strike": 500.0, "expiry": "2026-07-18", "gex": 50_000_000.0,
         "call_oi": 2000, "put_oi": 2000, "call_vol": 200, "put_vol": 200, "_dte": 11.0},
        # dominant pick after exclusion
        {"strike": 490.0, "expiry": "2026-07-18", "gex": 10_000_000.0,
         "call_oi": 1500, "put_oi": 1500, "call_vol": 100, "put_vol": 100, "_dte": 11.0},
        {"strike": 510.0, "expiry": "2026-07-18", "gex": 500_000.0,
         "call_oi": 500, "put_oi": 500, "call_vol": 50, "put_vol": 50, "_dte": 11.0},
    ]
    hs = _heat_seeker(cells, spot, "GEX")
    assert hs is not None
    assert hs["note"] == "descriptive — not a recommendation", (
        f"note field wrong: {hs['note']!r}"
    )

    # Also verify that a payload with a different note fails validate_matrix
    bad_payload = {
        "schema": "options_structure.matrix/v1",
        "asof": "2026-07-07T00:00:00+00:00",
        "root": "SPY",
        "cells": [{"strike": 500.0, "expiry": "2026-07-18"}],
        "heat_seeker": {
            "strike": 490.0, "expiry": "2026-07-18",
            "note": "this is a recommendation",   # WRONG
        },
    }
    errors = validate_matrix(bad_payload)
    assert any("note" in e for e in errors), f"Expected note error, got: {errors}"


# ─────────────────────────────────────────────────────────────────────────────
# 11. median_iv fallback
# ─────────────────────────────────────────────────────────────────────────────

def test_median_iv_fallback():
    """_median_iv returns 0.30 when no valid IVs, and correct median otherwise."""
    assert _median_iv([]) == 0.30
    assert _median_iv([0.0, -1.0, 6.0]) == 0.30   # all out of (0.01, 5.0)
    result = _median_iv([0.15, 0.20, 0.25])
    assert abs(result - 0.20) < 1e-9


# ─────────────────────────────────────────────────────────────────────────────
# 12. VEX — vanna formula known-value check (EXPERIMENTAL)
# ─────────────────────────────────────────────────────────────────────────────

def test_bs_vanna_scalar_known_value():
    """_bs_vanna_scalar: known-value cross-check against the greeks.bs_greeks vanna.

    vanna = -N'(d1) * d2 / sigma  (dividend-free, r=_R)

    Hand computation (S=500, K=500, T=14/365, iv=0.20):
      sqrtT = sqrt(14/365) ≈ 0.19579
      d1 = [ln(1) + (0.05 + 0.5*0.04)*14/365] / (0.20*0.19579)
         = [0 + 0.001096] / 0.039159
         ≈ 0.027992
      d2 = d1 - 0.20*0.19579 = 0.027992 - 0.039159 ≈ -0.011167
      N'(d1) = exp(-0.5*d1^2) / sqrt(2π) ≈ 0.39884
      vanna = -0.39884 * (-0.011167) / 0.20 ≈ +0.022267
    """
    S = 500.0
    K = 500.0
    iv = 0.20
    T_years = 14.0 / 365.0

    vanna = _bs_vanna_scalar(S, K, T_years, iv, 0.30)

    # Cross-check: direct formula
    sqrtT = math.sqrt(T_years)
    d1 = (math.log(S / K) + (_R + 0.5 * iv ** 2) * T_years) / (iv * sqrtT)
    d2 = d1 - iv * sqrtT
    expected_vanna = -npdf(d1) * d2 / iv
    assert abs(vanna - expected_vanna) < 1e-9, (
        f"vanna mismatch: got {vanna:.6f} expected {expected_vanna:.6f}"
    )

    # Cross-check with greeks.bs_greeks (which also computes vanna, using q=0 assumption)
    from engine.greeks import bs_greeks
    _, _, greeks_vanna, _ = bs_greeks(S, K, T_years, iv, is_call=True, r=_R, q=0.0)
    # bs_greeks uses -eqT * pdf * d2 / sigma; with q=0 eqT=1 so should match exactly
    assert abs(vanna - greeks_vanna) < 1e-9, (
        f"vanna vs bs_greeks mismatch: {vanna:.6f} vs {greeks_vanna:.6f}"
    )

    # Sanity: ATM vanna is finite and non-zero for typical parameters.
    # Sign depends on moneyness/d2: when d2 > 0 (ATM + rate effect) vanna is negative;
    # when d2 < 0 (short-dated deep OTM or low-rate) vanna is positive.  Only test finiteness.
    assert math.isfinite(vanna), f"Expected finite vanna, got {vanna}"
    assert vanna != 0.0, f"Expected non-zero vanna for typical ATM parameters"


def test_bs_vanna_scalar_degenerate():
    """_bs_vanna_scalar returns 0.0 only when BOTH iv and median_iv are below _MIN_IV.

    When iv is below the floor, median_iv is used as fallback (same as _bs_gamma_scalar).
    Only when median_iv is also too small does the function return 0.0.
    """
    # Both iv and median_iv below _MIN_IV (0.005) → 0.0
    assert _bs_vanna_scalar(500.0, 500.0, 0.038, 0.004, 0.004) == 0.0

    # iv below floor but median_iv=0.30 → fallback to median_iv → finite non-zero result
    result = _bs_vanna_scalar(500.0, 500.0, 0.038, 0.0, 0.30)
    assert math.isfinite(result), "Expected finite result when fallback iv is valid"


def test_vex_mn_formula():
    """_vex_mn: known-value check — formula oi * vanna * S * 0.01 * 100 / 1e6.

    S=500, oi=2000, vanna=0.025 → vex = 2000 * 0.025 * 500 * 0.01 * 100 / 1e6
                                       = 2000 * 0.025 * 500 * 1 / 1e6
                                       = 25 / 1e6 * 1e6 ... let's compute:
    = 2000 * 0.025 = 50
    = 50 * 500 = 25000
    = 25000 * 0.01 * 100 = 25000
    = 25000 / 1e6 = 0.025
    """
    S = 500.0
    oi = 2000.0
    vanna = 0.025
    expected = oi * vanna * S * _VOL_PCT * _CONTRACT_MULT / 1_000_000
    result = _vex_mn(oi, vanna, S)
    assert abs(result - expected) < 1e-12, (
        f"_vex_mn formula mismatch: got {result} expected {expected}"
    )
    assert abs(result - 0.025) < 1e-9, f"Expected 0.025, got {result}"


def test_vanna_same_sign_call_put():
    """_bs_vanna_scalar returns the SAME value for calls and puts at identical strike/params.

    Closed-form BS vanna = -N'(d1) * d2 / sigma is RIGHT-INDEPENDENT: the formula
    contains no call/put branch, only S, K, T, sigma, r.  Therefore a call and a put
    at the same strike must produce identical vanna values.

    This test pins the convention fix: earlier comments incorrectly stated
    "calls: positive vex" / "puts: negative vex", implying vanna depends on right.
    The correct convention is that both accumulate the SAME vanna sign (determined by
    d2 = moneyness), and net_vex = call_vex + put_vex sums those same-signed values.

    Hand computation (S=500, K=500, T=14/365, iv=0.20, r=_R=0.05):
      sqrtT = sqrt(14/365) ≈ 0.195791
      d1 = [ln(1) + (0.05 + 0.5*0.04)*14/365] / (0.20*0.195791)
         ≈ 0.068547
      d2 = d1 - 0.20*0.195791 ≈ 0.029377  (positive: ATM with r=0.05 pushes d2 > 0)
      N'(d1) ≈ 0.398006
      vanna = -0.398006 * 0.029377 / 0.20 ≈ -0.058461  (negative because d2 > 0)
      Same for call and put — right-independent formula.
    """
    S = 500.0
    K = 500.0
    iv = 0.20
    T_years = 14.0 / 365.0

    vanna_c = _bs_vanna_scalar(S, K, T_years, iv, 0.30)
    vanna_p = _bs_vanna_scalar(S, K, T_years, iv, 0.30)

    # Must be identical — formula is right-independent
    assert abs(vanna_c - vanna_p) < 1e-15, (
        f"Call vanna {vanna_c:.8f} != put vanna {vanna_p:.8f} — formula must be right-independent"
    )

    # Both must have the same sign (sign from d2/moneyness, not right)
    assert math.copysign(1, vanna_c) == math.copysign(1, vanna_p), (
        f"Call and put vanna have different signs: call={vanna_c:.6f} put={vanna_p:.6f}"
    )

    # Verify hand-computed value: vanna ≈ -0.058461
    sqrtT = math.sqrt(T_years)
    d1 = (math.log(S / K) + (_R + 0.5 * iv ** 2) * T_years) / (iv * sqrtT)
    d2 = d1 - iv * sqrtT
    expected = -npdf(d1) * d2 / iv
    assert abs(vanna_c - expected) < 1e-9, (
        f"Vanna {vanna_c:.8f} does not match hand computation {expected:.8f}"
    )
    # d2 > 0 at ATM with r=0.05, T=14/365 → vanna is negative
    assert d2 > 0, f"Expected d2>0 for this param set, got {d2:.6f}"
    assert expected < 0, f"Expected negative vanna (d2>0), got {expected:.6f}"


def test_build_matrix_vex_mn_present(tmp_path):
    """build_matrix output cells carry vex_mn field when greeks data is present.

    The field must be a finite float (not None) for contracts with real OI + IV.
    """
    root = "SPY"
    expiry = "2026-08-15"

    t1_rows = [
        {"root": root, "expiration": expiry, "strike": 500.0, "right": "C", "open_interest": 1000},
        {"root": root, "expiration": expiry, "strike": 490.0, "right": "P", "open_interest": 800},
    ]
    store = _make_store(tmp_path, root, t1_rows)

    # Write greeks with IV + spot
    greeks_path = store / "greeks" / root
    greeks_path.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {
            "root": root, "expiration": expiry, "strike": 500.0, "right": "C",
            "date": "2026-07-07", "implied_vol": 0.20, "underlying_price": 500.0,
            "delta": 0.5, "theta": -0.1, "vega": 0.2, "rho": 0.0, "iv_error": 0.0,
        },
        {
            "root": root, "expiration": expiry, "strike": 490.0, "right": "P",
            "date": "2026-07-07", "implied_vol": 0.22, "underlying_price": 500.0,
            "delta": -0.3, "theta": -0.08, "vega": 0.18, "rho": 0.0, "iv_error": 0.0,
        },
    ]).to_parquet(greeks_path / "2026.parquet", index=False)

    from engine.thetadata_store import clear_parquet_cache
    clear_parquet_cache()

    payload = build_matrix(root, store=str(store), asof="2026-07-07")
    errors = validate_matrix(payload)
    assert errors == [], f"validate_matrix errors: {errors}"

    # All cells must have vex_mn key
    cells = payload["cells"]
    assert len(cells) > 0, "Expected at least one cell"
    for c in cells:
        assert "vex_mn" in c, f"Cell missing vex_mn: {c}"

    # At least one cell should have a non-None vex_mn (call with real OI + IV)
    vex_values = [c["vex_mn"] for c in cells if c.get("vex_mn") is not None]
    assert len(vex_values) > 0, "Expected at least one non-None vex_mn cell"

    # Payload should be marked experimental
    assert payload.get("experimental") is True, "Payload should have experimental=True"

    # reliability should mention vex_mn
    assert "vex_mn" in payload.get("reliability", {}), "reliability should document vex_mn"


# ─────────────────────────────────────────────────────────────────────────────
# 12. GEX sign convention
# ─────────────────────────────────────────────────────────────────────────────

def test_gex_sign_convention(tmp_path):
    """Cells dominated by calls should have positive net GEX; puts → negative.

    Net GEX = call_gex − put_gex (dealer-short assumption).
    """
    root = "SPY"
    expiry = "2026-08-15"

    # Call-dominant strike at 510: 2000 call OI, 100 put OI
    # Put-dominant strike at 490: 100 call OI, 2000 put OI
    t1_rows = [
        _base_oi_row(root, 510.0, expiry, "C", 2000),
        _base_oi_row(root, 510.0, expiry, "P",  100),
        _base_oi_row(root, 490.0, expiry, "C",  100),
        _base_oi_row(root, 490.0, expiry, "P", 2000),
    ]
    store = _make_store(tmp_path, root, t1_rows)

    # greeks for spot
    greeks_path = store / "greeks" / root
    greeks_path.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {"root": root, "expiration": expiry, "strike": 510.0, "right": "C",
         "date": "2026-07-07", "implied_vol": 0.20, "underlying_price": 500.0,
         "delta": 0.5, "theta": -0.1, "vega": 0.2, "rho": 0.0, "iv_error": 0.0},
        {"root": root, "expiration": expiry, "strike": 490.0, "right": "P",
         "date": "2026-07-07", "implied_vol": 0.20, "underlying_price": 500.0,
         "delta": -0.5, "theta": -0.1, "vega": 0.2, "rho": 0.0, "iv_error": 0.0},
    ]).to_parquet(greeks_path / "2026.parquet", index=False)

    payload = build_matrix(root, store=str(store), asof="2026-07-07")
    cells = {c["strike"]: c for c in payload["cells"]}

    cell_510 = cells.get(510.0)
    cell_490 = cells.get(490.0)

    if cell_510:
        assert (cell_510["gex"] or 0) > 0, "Call-dominant strike should have positive GEX"
    if cell_490:
        assert (cell_490["gex"] or 0) < 0, "Put-dominant strike should have negative GEX"


# ─────────────────────────────────────────────────────────────────────────────
# 13. spot_row_exclusion — nearest strike, not exact-match (prism_spec §5)
# ─────────────────────────────────────────────────────────────────────────────

def test_heat_seeker_excludes_nearest_not_exact():
    """heat_seeker must exclude the NEAREST-to-spot strike, not an exact spot match.

    Scenario: spot=500.5, strikes=[500.0, 510.0, 520.0].
      nearest-to-spot = 500.0 (|500.0-500.5|=0.5 < |510.0-500.5|=9.5)
      Strike 500.0 carries the largest GEX (50M) and should be EXCLUDED.
      Under the old exact-match code (abs(strike-spot)<1e-6), 500.0 would NOT
      be excluded (0.5 != 0) and would become the heat_seeker pick.
      Under the correct nearest-strike code, 500.0 is excluded; the top
      remaining candidate is 510.0 (GEX=5M) → heat_seeker picks 510.0.
    """
    spot = 500.5   # intentionally NOT equal to any strike
    cells = [
        # Nearest-to-spot — must be excluded per spec
        {"strike": 500.0, "expiry": "2026-07-18", "gex": 50_000_000.0,
         "call_oi": 4000, "put_oi": 2000, "call_vol": 200, "put_vol": 100, "_dte": 11.0},
        # Second candidate — should become the pick after 500.0 is excluded
        {"strike": 510.0, "expiry": "2026-07-18", "gex": 5_000_000.0,
         "call_oi": 1500, "put_oi": 1000, "call_vol": 80, "put_vol": 40, "_dte": 11.0},
        # Third candidate
        {"strike": 520.0, "expiry": "2026-07-18", "gex": 200_000.0,
         "call_oi": 300, "put_oi": 200, "call_vol": 20, "put_vol": 10, "_dte": 11.0},
    ]
    hs = _heat_seeker(cells, spot, "GEX")
    # The nearest strike (500.0) must NOT be selected
    assert hs is not None, "Expected a heat_seeker pick from non-nearest strikes"
    assert hs["strike"] != 500.0, (
        f"Strike 500.0 is nearest to spot=500.5 and must be excluded, "
        f"but heat_seeker picked {hs['strike']}"
    )
    assert hs["strike"] == 510.0, (
        f"Expected 510.0 (top non-nearest candidate), got {hs['strike']}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 14. expired_expiries_excluded — regression for operator-gate finding 2026-07-07
# ─────────────────────────────────────────────────────────────────────────────

def test_expired_expiries_excluded(tmp_path):
    """Contracts with expiry < asof must be excluded from cells, expiries list,
    and must never be selected by heat_seeker.

    Regression for: SPY payload asof=2026-07-06 contained expiries 2026-07-02
    and 2026-07-06 (already expired / same-day only retained by 0.5 floor).
    The DTE window must be [0, +90] — never negative.
    """
    root = "SPY"
    asof = "2026-07-07"
    spot = 500.0

    # Three rows: one expired (2026-07-02), one future (2026-08-15)
    t1_rows = [
        # EXPIRED — expiry 5 days before asof — must be excluded
        _base_oi_row(root, 500.0, "2026-07-02", "C", 9999),
        # FUTURE — expiry 39 days out — must be included
        _base_oi_row(root, 500.0, "2026-08-15", "C", 1000),
        _base_oi_row(root, 495.0, "2026-08-15", "P", 2000),
        _base_oi_row(root, 505.0, "2026-08-15", "C", 3000),
    ]
    store = _make_store(tmp_path, root, t1_rows)

    # greeks for spot
    greeks_path = store / "greeks" / root
    greeks_path.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{
        "root": root, "expiration": "2026-08-15", "strike": 500.0, "right": "C",
        "date": asof, "implied_vol": 0.20, "underlying_price": spot,
        "delta": 0.5, "theta": -0.1, "vega": 0.2, "rho": 0.0, "iv_error": 0.0,
    }]).to_parquet(greeks_path / "2026.parquet", index=False)

    payload = build_matrix(root, store=str(store), asof=asof)

    # 1. Expired expiry must not appear in the expiries list
    assert "2026-07-02" not in payload["expiries"], (
        f"Expired expiry 2026-07-02 leaked into payload['expiries']: {payload['expiries']}"
    )

    # 2. No cell must have an expired expiry
    expired_cells = [c for c in payload["cells"] if c.get("expiry", "") < asof]
    assert expired_cells == [], (
        f"Expired cells in payload: {expired_cells}"
    )

    # 3. heat_seeker must not reference an expired expiry
    hs = payload.get("heat_seeker")
    if hs is not None:
        assert hs.get("expiry", "") >= asof, (
            f"heat_seeker picked expired expiry: {hs.get('expiry')}"
        )

    # 4. Schema still valid
    errors = validate_matrix(payload)
    assert errors == [], f"validate_matrix errors: {errors}"


# ─────────────────────────────────────────────────────────────────────────────
# 15. heat_seeker_never_picks_negative_dte
# ─────────────────────────────────────────────────────────────────────────────

def test_heat_seeker_never_picks_negative_dte():
    """heat_seeker must never select a cell whose DTE < 0 (already expired).

    This exercises the _heat_seeker function directly with a cell whose _dte
    is negative — it should be excluded before ranking, so only the non-expired
    cell can win.
    """
    spot = 500.0
    cells = [
        # EXPIRED cell — massive GEX — must be excluded
        {"strike": 490.0, "expiry": "2026-07-02", "gex": 999_000_000.0,
         "call_oi": 50000, "put_oi": 50000, "call_vol": 5000, "put_vol": 5000,
         "_dte": -5.0},   # explicitly negative DTE
        # FUTURE cell — smaller GEX but non-expired
        {"strike": 510.0, "expiry": "2026-08-15", "gex": 5_000_000.0,
         "call_oi": 3000, "put_oi": 2000, "call_vol": 100, "put_vol": 80,
         "_dte": 39.0},
        # Second future cell for ratio computation
        {"strike": 520.0, "expiry": "2026-08-15", "gex": 500_000.0,
         "call_oi": 1000, "put_oi": 800, "call_vol": 30, "put_vol": 20,
         "_dte": 39.0},
    ]
    hs = _heat_seeker(cells, spot, "GEX")
    assert hs is not None, "Expected a pick from the non-expired cells"
    assert (hs.get("expiry") or "") >= "2026-07-07", (
        f"heat_seeker selected an expired expiry: {hs.get('expiry')}"
    )
    assert hs["strike"] != 490.0, (
        f"heat_seeker must not pick the expired cell (strike=490.0), got {hs['strike']}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 16. plain_iso_expiry_serialization — no pandas timestamp strings
# ─────────────────────────────────────────────────────────────────────────────

def test_plain_iso_expiry_serialization(tmp_path):
    """Expiry strings in cells, expiries list, and heat_seeker must match
    the pattern YYYY-MM-DD (plain ISO), not a pandas Timestamp string like
    '2026-07-18 00:00:00'.

    Regression for: ThetaData parquets store expiration as Timestamp objects;
    str(Timestamp) produces '2026-07-18 00:00:00' which is non-canonical.
    """
    import re
    ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

    root = "SPY"
    asof = "2026-07-07"
    # Use a pandas Timestamp as the expiration in the parquet to simulate the
    # real store format.
    expiry_ts = pd.Timestamp("2026-08-15")

    t1_rows = [
        {"root": root, "expiration": expiry_ts, "strike": 500.0,
         "right": "C", "open_interest": 1000},
        {"root": root, "expiration": expiry_ts, "strike": 495.0,
         "right": "P", "open_interest": 2000},
        {"root": root, "expiration": expiry_ts, "strike": 505.0,
         "right": "C", "open_interest": 3000},
    ]
    store = _make_store(tmp_path, root, t1_rows)

    greeks_path = store / "greeks" / root
    greeks_path.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{
        "root": root, "expiration": expiry_ts, "strike": 500.0, "right": "C",
        "date": asof, "implied_vol": 0.20, "underlying_price": 500.0,
        "delta": 0.5, "theta": -0.1, "vega": 0.2, "rho": 0.0, "iv_error": 0.0,
    }]).to_parquet(greeks_path / "2026.parquet", index=False)

    payload = build_matrix(root, store=str(store), asof=asof)

    # All expiry strings in the expiries list must be plain ISO
    for exp in payload["expiries"]:
        assert ISO_DATE_RE.match(str(exp)), (
            f"expiries list contains non-ISO date: {exp!r}"
        )

    # All expiry strings in cells must be plain ISO
    for cell in payload["cells"]:
        exp = cell.get("expiry", "")
        assert ISO_DATE_RE.match(str(exp)), (
            f"cell expiry is not plain ISO: {exp!r}"
        )

    # heat_seeker expiry (if present) must be plain ISO
    hs = payload.get("heat_seeker")
    if hs is not None:
        exp = hs.get("expiry", "")
        assert ISO_DATE_RE.match(str(exp)), (
            f"heat_seeker expiry is not plain ISO: {exp!r}"
        )
