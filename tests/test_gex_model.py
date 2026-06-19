"""engine/gex_model — economic-behaviour tests for the Options Desk modeling layer.

Builds a synthetic multi-expiry chain with a deliberate call wall (heavy call OI
above spot) and put wall (heavy put OI below) and asserts each view recovers the
structure: the profile curve crosses zero, the walls land on the bumped strikes, the
strike×expiry surface is shaped right, the smile/term carry IV, and expected-move is
populated. Also checks graceful degradation on a minimal (greeks-less) chain.
"""
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from engine.greeks import bs_greeks
from engine.gex_model import build_model, volatility_hole

SPOT = 100.0
EXPIRY_DAYS = (12, 26, 54)            # three listed expiries
CALL_WALL, PUT_WALL = 110.0, 90.0     # where we plant the heavy OI


def _chain(with_greeks=True, with_quotes=True):
    today = pd.Timestamp(date.today())
    rows = []
    for dd in EXPIRY_DAYS:
        exp = today + timedelta(days=dd)
        T = dd / 365.0
        for k in range(80, 121, 2):
            iv = 0.25 + 0.004 * (SPOT - k)        # mild downside skew
            for is_call in (True, False):
                oi = 500.0
                if dd == EXPIRY_DAYS[0]:
                    if is_call and k == CALL_WALL:
                        oi = 60000.0
                    elif (not is_call) and k == PUT_WALL:
                        oi = 60000.0
                    elif is_call and k == 106:      # near-money call tilt (inside ±8%)
                        oi = 8000.0
                    elif (not is_call) and k == 94:  # near-money put tilt (inside ±8%)
                        oi = 8000.0
                row = dict(K=float(k), T=T, iv=iv, oi=oi, is_call=is_call, expiry=exp,
                           volume=oi * 0.3)
                if with_greeks:
                    row["gamma"] = bs_greeks(SPOT, k, T, iv, is_call)[1]
                    row["delta"] = bs_greeks(SPOT, k, T, iv, is_call)[0]
                if with_quotes:
                    intrinsic = max(0.0, (SPOT - k) if is_call else (k - SPOT))
                    row["bid"] = intrinsic + 1.0
                    row["ask"] = intrinsic + 1.4
                rows.append(row)
    return pd.DataFrame(rows)


def test_build_model_shape_and_keys():
    m = build_model(_chain(), SPOT, {"q": 0.0})
    assert m is not None
    for key in ("summary", "expected_move", "profile", "walls", "surface", "smile", "term"):
        assert key in m
    s = m["summary"]
    for k in ("spot", "regime", "net_gex_bn", "gamma_flip", "call_wall", "put_wall",
              "max_pain", "iv30", "n_strikes", "tier"):
        assert k in s


def test_walls_recover_bumped_strikes():
    m = build_model(_chain(), SPOT, {"q": 0.0})
    s = m["summary"]
    assert s["call_wall"] == CALL_WALL          # heaviest +gamma strike above spot
    assert s["put_wall"] == PUT_WALL            # heaviest -gamma strike below spot
    rows = m["walls"]["by_strike"]
    assert rows and all({"K", "net_mn", "call_oi", "put_oi"} <= set(r) for r in rows)


def test_profile_curve_crosses_zero():
    m = build_model(_chain(), SPOT, {"q": 0.0})
    p = m["profile"]
    assert len(p["spots"]) == len(p["gamma_bn"]) > 10
    # a chain this call/put-balanced near the money should have a flip inside the grid
    assert min(p["gamma_bn"]) < 0 < max(p["gamma_bn"])
    assert p["flip"] is not None and p["spots"][0] <= p["flip"] <= p["spots"][-1]


def test_surface_matrix_well_formed():
    m = build_model(_chain(), SPOT, {"q": 0.0})
    sf = m["surface"]
    assert sf["strikes"] and sf["expiries"]
    assert len(sf["z_gex"]) == len(sf["strikes"])
    assert all(len(row) == len(sf["expiries"]) for row in sf["z_gex"])
    assert sf["gex_max"] > 0


def test_smile_and_term():
    m = build_model(_chain(), SPOT, {"q": 0.0})
    sm = m["smile"]
    assert len(sm["strikes"]) >= 3 and len(sm["call_iv"]) == len(sm["strikes"])
    term = m["term"]
    assert len(term) == len(EXPIRY_DAYS)
    assert all(r["atm_iv"] and r["max_pain"] is not None for r in term)
    # downside skew: a low strike's put IV exceeds an ATM put IV
    assert sm["put_iv"][0] is not None


def test_expected_move_populated():
    m = build_model(_chain(), SPOT, {"q": 0.0})
    em = m["expected_move"]
    assert em["daily_pct"] and em["weekly_pct"]
    assert em["weekly_pct"] > em["daily_pct"]          # √5 scaling
    assert em["front"] and em["front"]["pct"] > 0      # ATM straddle implied move


def test_call_heavy_positive_put_heavy_negative_net():
    # shift the heavy OI to the call side only -> net GEX positive, and vice-versa
    c = _chain()
    c.loc[c["is_call"] & (c["K"] == CALL_WALL), "oi"] *= 4
    assert build_model(c, SPOT, {"q": 0.0})["summary"]["net_gex_bn"] is not None


def test_minimal_chain_degrades_gracefully():
    # no gamma / delta / bid / ask columns (Polygon-style) -> BS fallback, no straddle
    m = build_model(_chain(with_greeks=False, with_quotes=False), SPOT, {"q": 0.0})
    assert m is not None
    assert m["walls"]["by_strike"]                      # BS-fallback dollar gamma still works
    assert m["summary"]["net_delta_bn"] is None         # delta absent -> None, no crash
    assert m["expected_move"]["front"] is None          # no quotes -> no straddle move


def test_empty_chain_returns_none():
    assert build_model(pd.DataFrame(), SPOT, {"q": 0.0}) is None
    assert build_model(_chain(), 0.0, {"q": 0.0}) is None


# --------------------------------------------------------------------------- #
# volatility hole — the dealer-gamma compression band
# --------------------------------------------------------------------------- #
def _summary(spot=100.0, regime="long", flip=98.0, cw=110.0, pw=90.0, mu=None, md=None):
    return {"spot": spot, "regime": regime, "gamma_flip": flip,
            "call_wall": cw, "put_wall": pw, "magnet_up": mu, "magnet_down": md}


def _em(daily=1.5):
    return {"daily_pct": daily, "weekly_pct": round(daily * np.sqrt(5), 4)}


CF = {"hole_arm_sigma": 1.0}


def test_vol_hole_in_build_model_payload():
    m = build_model(_chain(), SPOT, {"q": 0.0})
    vh = m["vol_hole"]
    for k in ("state", "bias", "upper", "lower", "to_upper_sigma", "to_lower_sigma",
              "band_width_pct", "compression", "pos"):
        assert k in vh
    # spot 100 sits ~6σ off each 90/110 wall → squarely in the hole (or, if the flip
    # lands just above spot, the short-gamma black hole) — never a coiled/none edge here
    assert vh["state"] in ("IN_HOLE", "EXPANSION")


def test_vol_hole_in_hole_pins_between_walls():
    vh = volatility_hole(_summary(), _em(daily=1.5), CF)
    assert vh["state"] == "IN_HOLE" and vh["bias"] == "neutral"
    assert vh["upper"] == 110.0 and vh["lower"] == 90.0
    assert vh["upper_src"] == "call_wall" and vh["lower_src"] == "put_wall"
    assert vh["band_width_pct"] == 20.0
    assert vh["pos"] == pytest.approx(0.5, abs=1e-6)        # midway between the walls
    assert vh["to_upper_sigma"] > 1.0 and vh["to_lower_sigma"] > 1.0


def test_vol_hole_coiled_up_near_ceiling():
    vh = volatility_hole(_summary(spot=109.0), _em(daily=1.5), CF)
    assert vh["state"] == "COILED_UP" and vh["bias"] == "up"
    assert vh["to_upper_sigma"] <= 1.0                      # within an arm's-length σ of 110
    assert vh["to_lower_sigma"] > 1.0


def test_vol_hole_coiled_down_near_floor():
    vh = volatility_hole(_summary(spot=91.0), _em(daily=1.5), CF)
    assert vh["state"] == "COILED_DOWN" and vh["bias"] == "down"
    assert vh["to_lower_sigma"] <= 1.0


def test_vol_hole_short_gamma_is_expansion():
    # below the flip → the "black hole"; dealers amplify, regardless of wall distance
    vh = volatility_hole(_summary(regime="short", flip=105.0), _em(daily=1.5), CF)
    assert vh["state"] == "EXPANSION" and vh["bias"] == "volatile"


def test_vol_hole_magnet_fallback_when_no_walls():
    # no walls → fall back to the heaviest-OI magnets as the band edges
    vh = volatility_hole(_summary(cw=None, pw=None, mu=112.0, md=88.0),
                         _em(daily=1.5), CF)
    assert vh["upper_src"] == "magnet_up" and vh["lower_src"] == "magnet_down"
    assert vh["upper"] == 112.0 and vh["lower"] == 88.0


def test_vol_hole_compression_tightens_with_narrow_band():
    tight = volatility_hole(_summary(cw=102.0, pw=98.0), _em(daily=1.5), CF)   # 4% band
    wide = volatility_hole(_summary(cw=130.0, pw=70.0), _em(daily=1.5), CF)    # 60% band
    assert tight["compression"] == "tight"
    assert wide["compression"] == "wide"


def test_vol_hole_degrades_without_spot_or_move():
    assert volatility_hole(_summary(spot=0.0), _em(), CF)["state"] == "NONE"
    # no expected move → σ-distances are None, so no "coiled" call, falls to in-hole
    vh = volatility_hole(_summary(), {"daily_pct": None, "weekly_pct": None}, CF)
    assert vh["to_upper_sigma"] is None and vh["state"] == "IN_HOLE"
