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
    _compute_max_pain,
    _gex_dollar,
    _heat_seeker,
    _median_iv,
    _null_payload,
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
