"""Tests for engine/gex_confirm.py — dealer-gamma as a long-entry verifier/confirmer."""
from engine import gex_confirm as gc


def _payload(regime="long", dist=2.0, vh_state="IN_HOLE", to_up=None, to_lo=None,
             call_wall=110.0, put_wall=90.0, tier="full", n_strikes=30):
    return {
        "summary": {"tier": tier, "n_strikes": n_strikes, "regime": regime, "spot": 100.0,
                    "gamma_flip": 98.0, "dist_to_flip_pct": dist,
                    "call_wall": call_wall, "put_wall": put_wall},
        "vol_hole": {"state": vh_state, "to_upper_sigma": to_up, "to_lower_sigma": to_lo},
    }


# --- liquidity gate ---------------------------------------------------------
def test_none_when_no_options():
    assert gc.assess(_payload(tier="no_options")) is None
    assert gc.assess(_payload(tier=None)) is None
    assert gc.assess({}) is None


def test_none_when_too_few_strikes():
    assert gc.assess(_payload(n_strikes=3)) is None


# --- the three verdicts -----------------------------------------------------
def test_confirm_short_gamma_coiled_up_runway():
    out = gc.assess(_payload(regime="short", vh_state="COILED_UP", to_up=3.0, to_lo=1.5))
    assert out["verdict"] == "confirm"
    assert out["score"] >= 1.0
    assert any(r["tone"] == "confirm" for r in out["reasons"])


def test_caution_deep_long_gamma_near_call_wall():
    out = gc.assess(_payload(regime="long", dist=5.0, vh_state="IN_HOLE", to_up=0.8))
    assert out["verdict"] == "caution"
    assert out["score"] <= -1.0
    assert out["levels"]["call_wall"] == 110.0


def test_neutral_mixed():
    out = gc.assess(_payload(regime="long", dist=1.8, vh_state="IN_HOLE"))
    assert out["verdict"] == "neutral"


# --- guards -----------------------------------------------------------------
def test_opex_suppresses_to_neutral():
    out = gc.assess(_payload(regime="short", vh_state="COILED_UP", to_up=3.0, to_lo=1.5),
                    opex_days=1)
    assert out["verdict"] == "neutral"
    assert out["opex_suppressed"] is True


def test_direction_down_cannot_confirm_a_long():
    out = gc.assess(_payload(regime="short", vh_state="COILED_UP", to_up=3.0, to_lo=1.5),
                    direction="down")
    assert out["verdict"] != "confirm"      # a long confirmer can't be positive on a faller
    assert out["score"] <= 0


# --- skew change (level excluded, change dormant unless supplied) ------------
def test_skew_steepening_adds_caution():
    base = gc.assess(_payload(regime="long", dist=1.8, vh_state="IN_HOLE"))
    steep = gc.assess(_payload(regime="long", dist=1.8, vh_state="IN_HOLE"), rr_change=-1.0)
    assert steep["score"] < base["score"]


def test_skew_flattening_adds_confirm():
    base = gc.assess(_payload(regime="long", dist=1.8, vh_state="IN_HOLE"))
    flat = gc.assess(_payload(regime="long", dist=1.8, vh_state="IN_HOLE"), rr_change=1.0)
    assert flat["score"] > base["score"]


def test_flat_summary_shape_also_accepted():
    # a flat summary (no nested 'summary') that carries vol_hole inline
    flat = {"tier": "full", "n_strikes": 20, "regime": "short", "dist_to_flip_pct": -1.0,
            "call_wall": 110.0, "put_wall": 90.0,
            "vol_hole": {"state": "EXPANSION", "to_upper_sigma": None, "to_lower_sigma": None}}
    out = gc.assess(flat)
    assert out is not None
    assert out["levels"]["regime"] == "short"
