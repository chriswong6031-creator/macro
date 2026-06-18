"""Tests for the world-class bond-hub additions: intl_bonds (Global Sovereign
Scorecard), bond_compass (Duration & Curve Compass) and bond_cross_asset
(Bonds → everything transmission).

Synthetic where the maths is deterministic; a real-data integration cross-check
skips if the parquet store is empty. Locks in: the slope-state / direction
classification, the global GDP-weighted aggregate, the compass leg SIGNS (high real
yield → bullish, steep carry → bullish, reflation → bearish), the compass bucket
bounds, the measured-beta sign of a known relationship, and graceful degradation.

Run: python -m tests.test_bond_hub
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import bond_compass as BC  # noqa: E402
from engine import bond_cross_asset as BX  # noqa: E402
from engine import intl_bonds as IB  # noqa: E402


def _bidx(n=900):
    return pd.date_range("2014-01-01", periods=n, freq="B")


# --- intl_bonds --------------------------------------------------------------
def test_slope_state_and_direction():
    assert IB._slope_state(-0.3) == "inverted"
    assert IB._slope_state(0.1) == "flat"
    assert IB._slope_state(0.6) == "normal"
    assert IB._slope_state(1.5) == "steep"
    assert IB._slope_state(None) is None
    assert IB._direction(40) == "rising"
    assert IB._direction(-40) == "falling"
    assert IB._direction(2) == "stable"
    assert IB._direction(None) is None


def test_chg_bp_and_z():
    idx = _bidx(300)
    s = pd.Series(np.linspace(2.0, 3.0, 300), index=idx)   # +100bp over the window
    bp = IB._chg_bp(s, 63)
    assert bp is not None and bp > 0          # rising
    # z-score of a monotonically rising series at the top -> positive
    assert IB._z(s, 252) > 0


def test_intl_snapshot_synthetic():
    """A frame with a full US curve + (no foreign store) still yields the US row,
    a global aggregate and a US-vs-world block, and degrades gracefully."""
    idx = _bidx(800)
    f = pd.DataFrame(index=idx)
    f["us10y"] = np.linspace(3.0, 4.4, 800)
    f["us2y"] = np.linspace(2.5, 4.0, 800)
    f["us3m"] = np.linspace(1.0, 3.8, 800)
    f["us10y_real"] = np.linspace(0.5, 2.1, 800)
    snap = IB.snapshot(f)
    assert snap is not None
    us = next(r for r in snap["countries"] if r["code"] == "US")
    assert us["y10"] == 4.4 or abs(us["y10"] - 4.4) < 0.01
    assert us["real_10y"] is not None
    assert us["slope_state"] in ("inverted", "flat", "normal", "steep")
    assert snap["global"]["avg_10y"] is not None
    assert snap["us_vs_world"]["us_10y"] is not None
    # contract keys the build + AI brain rely on
    for k in ("as_of", "global", "us_vs_world", "countries", "verdict_en", "drivers_for"):
        assert k in snap


# --- bond_compass ------------------------------------------------------------
def test_compass_leg_signs():
    """High real yield → bullish (cheap); steep curve → bullish carry; reflation → bearish."""
    idx = _bidx(900)
    # value: real yield ramps to a multi-year high -> bullish (+)
    f = pd.DataFrame(index=idx)
    f["us10y_real"] = np.linspace(-1.0, 2.5, 900)
    assert BC._value_leg(f) > 0
    f2 = pd.DataFrame(index=idx)
    f2["us10y_real"] = np.linspace(2.5, -1.0, 900)   # now expensive -> bearish
    assert BC._value_leg(f2) < 0
    # carry: a steepening curve to a high percentile -> bullish carry (+)
    f3 = pd.DataFrame(index=idx)
    f3["spread_10y3m"] = np.linspace(-0.5, 2.0, 900)
    assert BC._carry_leg(f3) > 0
    # macro reflation: an ACCELERATING copper/gold + breakeven impulse (flat history,
    # then a fresh rise) -> a positive recent z -> bearish duration (-). A linear ramp
    # would give a DECLINING 63d %-change, so the impulse must be a fresh acceleration.
    f4 = pd.DataFrame(index=idx)
    f4["copper_gold"] = np.concatenate([np.full(650, 0.12), np.linspace(0.12, 0.22, 250)])
    f4["breakeven_10y"] = np.concatenate([np.full(650, 1.9), np.linspace(1.9, 2.8, 250)])
    m = BC._macro_leg(f4)
    assert m is not None and m < 0, m


def test_compass_snapshot_bounds():
    idx = _bidx(900)
    f = pd.DataFrame(index=idx)
    f["us10y_real"] = np.linspace(0.0, 2.0, 900)
    f["spread_10y3m"] = np.linspace(0.0, 1.5, 900)
    f["term_premium_10y"] = np.linspace(-0.5, 0.8, 900)
    f["us10y"] = np.linspace(2.0, 4.4, 900)
    f["us7y"] = np.linspace(1.8, 4.1, 900)
    f["copper_gold"] = np.full(900, 0.15)
    f["breakeven_10y"] = np.full(900, 2.3)
    snap = BC.snapshot(f)
    assert snap is not None
    d = snap["duration"]
    assert -1.0 <= d["lean"] <= 1.0
    assert d["bucket"] in ("lean_long", "neutral", "lean_short")
    assert d["legs"] and all(-1 <= l["value"] <= 1 for l in d["legs"])
    assert snap["curve_trade"]["lean"] in ("steepener", "flattener", "neutral")
    # expected-return cushion must be a sane positive number for a positive carry
    if snap["expected"]:
        assert snap["expected"]["cushion_bp"] is None or snap["expected"]["cushion_bp"] > 0
    assert "honest_en" in snap and "display-only" in snap["honest_en"].lower()


def test_compass_degrades_on_empty():
    assert BC.snapshot(pd.DataFrame()) is None
    assert IB.snapshot(pd.DataFrame()) is None
    assert BX.snapshot(pd.DataFrame()) is None


# --- bond_cross_asset --------------------------------------------------------
def test_measured_beta_sign():
    """A synthetic asset built to fall when its driver rises must yield a NEGATIVE beta."""
    idx = _bidx(900)
    rng = np.random.default_rng(0)
    driver = pd.Series(np.cumsum(rng.normal(0, 0.03, 900)) + 2.0, index=idx)  # a rate level
    # asset return = -1.5 * driver weekly change + noise -> price index
    dch = driver.diff().fillna(0.0)
    ret = -1.5 * dch + rng.normal(0, 0.005, 900)
    px = (1.0 + ret).cumprod() * 100.0
    px = pd.Series(px, index=idx)
    b = BX._beta(px, driver)
    assert b is not None
    assert b["beta"] < 0          # inverse relationship recovered
    assert b["corr"] < 0


def test_xasset_snapshot_real_or_skip():
    """Real-data smoke: the transmission map must produce signed betas with sane fields."""
    try:
        from engine import inputs
        f = inputs.build_features()
    except Exception as e:  # noqa: BLE001 — no store in CI-less env
        print(f"  (skip xasset real-data: {e})")
        return
    snap = BX.snapshot(f)
    if snap is None:
        print("  (xasset snapshot None — store thin)")
        return
    assert snap["assets"], "no transmission rows"
    for a in snap["assets"]:
        assert a["verdict"] in ("tailwind", "headwind", "neutral")
        assert -1.0 <= (a["corr"] or 0) <= 1.0
        assert a["beta_disp"]
    # the S&P↔HY-OAS relationship should be measured negative (credit canary)
    spx = next((a for a in snap["assets"] if a["key"] == "spx"), None)
    if spx and spx["corr"] is not None:
        assert spx["corr"] < 0, f"S&P↔HY-OAS corr should be negative, got {spx['corr']}"
    print(f"  real data: {len(snap['assets'])} transmission rows, "
          f"verdict='{snap['verdict_en'][:60]}...'")


def test_intl_real_or_skip():
    try:
        from engine import inputs
        f = inputs.build_features()
    except Exception as e:  # noqa: BLE001
        print(f"  (skip intl real-data: {e})")
        return
    snap = IB.snapshot(f)
    if snap is None:
        print("  (intl snapshot None — store thin)")
        return
    assert snap["countries"]
    codes = {r["code"] for r in snap["countries"]}
    assert "US" in codes
    print(f"  real data: {len(snap['countries'])} sovereigns, "
          f"global 10y={snap['global']['avg_10y']}%, US-vs-world={snap['us_vs_world']['us_premium_bp']}bp")


if __name__ == "__main__":
    for fn in [test_slope_state_and_direction, test_chg_bp_and_z, test_intl_snapshot_synthetic,
               test_compass_leg_signs, test_compass_snapshot_bounds, test_compass_degrades_on_empty,
               test_measured_beta_sign, test_xasset_snapshot_real_or_skip, test_intl_real_or_skip]:
        fn()
        print(f"PASS {fn.__name__}")
    print("all bond-hub tests passed")
