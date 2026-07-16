"""tests/test_levels_engine.py — hermetic tests for engine/levels_engine.py.

WP-A1 of the Voltick Gamma-Levels program. All fixtures are crafted by_strike ladders
with hand-known answers (no real parquet / no I/O). The final test reconstructs a
realistic SPY ``options_hub.gex/v1`` payload (synthesized from the true compute_gex
field names, anchored to observed live SPY levels) and asserts the emitted nodes are
internally consistent.

Coverage:
  1.  Anchor = the max |gamma_net| strike
  2.  Cluster threshold: exactly 50% included, 49% excluded; Anchor itself excluded
  3.  Flip: payload value reused verbatim; recomputed from a crafted sign-change when absent
  4.  Void: exactly 3 empties = a void run; 2 = not
  5.  Trapdoor / Launchpad orientation
  6.  Regime label follows the net-gamma sign
  7.  Stack tagging when the Anchor coincides with a wall
  8.  Empty / degenerate input => honest nulls, never a crash or a fabricated strike
  9.  Palette colorblind swap (green/red -> blue/orange)
  10. Counter = heaviest strike on the far side of the flip from the Anchor
  11. Real-ish SPY reconstruction: internally consistent nodes
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# ── ensure repo root on path ──────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.levels_engine import SCHEMA, compute_levels


# --------------------------------------------------------------------------- #
# fixture helpers
# --------------------------------------------------------------------------- #

def _row(strike: float, gamma_net: float, **extra) -> dict:
    """One by_strike row (options_hub.gex/v1 contract). Only strike + gamma_net are
    load-bearing for the taxonomy; the rest default to 0.0 like a real row."""
    r = {
        "strike": float(strike),
        "gamma_net": float(gamma_net),
        "gamma_call": 0.0,
        "gamma_put": 0.0,
        "delta_net": 0.0,
        "vanna_net": 0.0,
        "charm_net": 0.0,
    }
    r.update(extra)
    return r


def _payload(by_strike, spot=100.0, net_gex_bn=1.0, gamma_flip=None,
             call_wall=None, put_wall=None, root="TEST", asof="2026-07-16") -> dict:
    return {
        "schema": "options_hub.gex/v1",
        "asof": asof,
        "root": root,
        "spot_ref": spot,
        "net_gex_bn": net_gex_bn,
        "gamma_flip": gamma_flip,
        "call_wall": call_wall,
        "put_wall": put_wall,
        "by_strike": by_strike,
        "convention": "dealer-sign per engine/gex_model (long-call/short-put)",
    }


def _role(levels: dict, role: str) -> list[dict]:
    return [n for n in levels["nodes"] if n["role"] == role]


def _one(levels: dict, role: str) -> dict:
    xs = _role(levels, role)
    assert len(xs) == 1, f"expected exactly one {role}, got {len(xs)}"
    return xs[0]


# --------------------------------------------------------------------------- #
# 1. Anchor
# --------------------------------------------------------------------------- #

def test_anchor_is_max_abs_weight_strike():
    # 105 has the largest magnitude (-8) even though it is negative.
    rows = [_row(95, 2.0), _row(100, 5.0), _row(105, -8.0), _row(110, 3.0)]
    lv = compute_levels(_payload(rows, spot=101.0))
    anchor = _one(lv, "anchor")
    assert anchor["strike"] == 105.0
    assert anchor["weight"] == -8.0
    assert anchor["sticky"] is False          # negative gamma => slippery
    assert anchor["brightness"] == 1.0        # Anchor is always full brightness


# --------------------------------------------------------------------------- #
# 2. Cluster threshold — exactly 50% in, 49% out, Anchor excluded
# --------------------------------------------------------------------------- #

def test_cluster_threshold_boundary():
    # Anchor = 100 at weight 10. 50% => 5.0. 105 at 5.0 (in), 95 at 4.9 (out).
    rows = [_row(95, 4.9), _row(100, 10.0), _row(105, 5.0), _row(110, 1.0)]
    lv = compute_levels(_payload(rows, spot=100.0))
    cluster_strikes = {n["strike"] for n in _role(lv, "cluster")}
    assert 105.0 in cluster_strikes            # exactly 50% => included
    assert 95.0 not in cluster_strikes         # 49% => excluded
    assert 100.0 not in cluster_strikes        # the Anchor itself is never a Cluster
    assert 110.0 not in cluster_strikes        # 10% => excluded


# --------------------------------------------------------------------------- #
# 3. Flip — reuse payload verbatim; recompute when absent
# --------------------------------------------------------------------------- #

def test_flip_reuses_payload_value():
    rows = [_row(95, -4.0), _row(100, 6.0), _row(105, 5.0), _row(110, 2.0)]
    lv = compute_levels(_payload(rows, spot=101.0, gamma_flip=99.37))
    flip = _one(lv, "flip")
    assert flip["strike"] == 99.37            # verbatim, not recomputed
    assert "Reconstructed" not in flip["note"]


def test_flip_recomputed_when_absent():
    # Cumulative from the bottom: -6 (95), -1 (100), +4 (105) -> crosses between 100 & 105.
    # Interp: 100 - (-1)*(105-100)/(4-(-1)) = 100 + 5/5 = 101.0
    rows = [_row(95, -6.0), _row(100, 5.0), _row(105, 5.0), _row(110, 1.0)]
    lv = compute_levels(_payload(rows, spot=104.0, gamma_flip=None))
    flip = _one(lv, "flip")
    assert flip["strike"] == pytest.approx(101.0, abs=1e-6)
    assert "Reconstructed" in flip["note"]


def test_flip_null_when_no_crossing():
    # All positive cumulative -> never crosses zero.
    rows = [_row(95, 3.0), _row(100, 4.0), _row(105, 5.0), _row(110, 2.0)]
    lv = compute_levels(_payload(rows, spot=100.0, gamma_flip=None))
    flip = _one(lv, "flip")
    assert flip["strike"] is None
    assert "does not cross zero" in flip["note"]


# --------------------------------------------------------------------------- #
# 4. Void — exactly 3 consecutive empties = a void; 2 = not
# --------------------------------------------------------------------------- #

def test_void_run_of_three_detected():
    # Anchor = 130 at 100. 5% threshold = 5.0. Strikes 100,105,110 all < 5 => a run of 3.
    rows = [
        _row(100, 1.0), _row(105, 1.0), _row(110, 1.0),   # 3 empties -> void
        _row(120, 60.0),
        _row(130, 100.0),                                  # Anchor
    ]
    lv = compute_levels(_payload(rows, spot=125.0))
    voids = _role(lv, "void")
    assert len(voids) == 1
    v = voids[0]
    assert v["strike_lo"] == 100.0
    assert v["strike_hi"] == 110.0
    assert v["n_strikes"] == 3
    assert v["strike"] is None                 # a void is a range, not a strike


def test_void_run_of_two_not_detected():
    # Only 2 consecutive empties -> below the 3-run minimum.
    rows = [
        _row(100, 1.0), _row(105, 1.0),        # 2 empties -> NOT a void
        _row(115, 60.0),
        _row(120, 100.0),                       # Anchor
    ]
    lv = compute_levels(_payload(rows, spot=118.0))
    assert _role(lv, "void") == []


# --------------------------------------------------------------------------- #
# 5. Trapdoor / Launchpad orientation
# --------------------------------------------------------------------------- #

def test_trapdoor_sticky_above_slippery():
    # Adjacent heavy pair: slippery -8 at 100, sticky +9 at 105 (105 directly above 100).
    # Anchor = 105 (|9|). Both >= 50% of 9 => qualify. Sticky-above-slippery => Trapdoor.
    rows = [_row(100, -8.0), _row(105, 9.0)]
    lv = compute_levels(_payload(rows, spot=102.0))
    traps = _role(lv, "trapdoor")
    launch = _role(lv, "launchpad")
    assert len(traps) == 1
    assert traps[0]["strike"] == 105.0         # the sticky shelf is the trapdoor
    assert traps[0]["sticky"] is True
    assert launch == []


def test_launchpad_slippery_above_sticky():
    # Mirror: sticky +9 at 100, slippery -8 at 105 (slippery lid directly above sticky).
    rows = [_row(100, 9.0), _row(105, -8.0)]
    lv = compute_levels(_payload(rows, spot=102.0))
    launch = _role(lv, "launchpad")
    traps = _role(lv, "trapdoor")
    assert len(launch) == 1
    assert launch[0]["strike"] == 100.0        # the sticky shelf is the launchpad anchor
    assert launch[0]["sticky"] is True
    assert traps == []


# --------------------------------------------------------------------------- #
# 6. Regime label sign
# --------------------------------------------------------------------------- #

def test_regime_label_positive_is_sticky():
    rows = [_row(95, 2.0), _row(100, 5.0), _row(105, 3.0)]
    lv = compute_levels(_payload(rows, spot=100.0, net_gex_bn=1.5))
    assert lv["regime"]["label"] == "sticky"
    assert lv["regime"]["net_gamma"] == 1.5
    assert "sticky" in lv["regime"]["ribbon"]


def test_regime_label_negative_is_slippery():
    rows = [_row(95, -2.0), _row(100, -5.0), _row(105, -3.0)]
    lv = compute_levels(_payload(rows, spot=100.0, net_gex_bn=-2.3))
    assert lv["regime"]["label"] == "slippery"
    assert lv["regime"]["net_gamma"] == -2.3
    assert "slippery" in lv["regime"]["ribbon"]


# --------------------------------------------------------------------------- #
# 7. Stack — Anchor coincides with a wall
# --------------------------------------------------------------------------- #

def test_stack_when_anchor_is_call_wall():
    # 110 is both the biggest |gamma| (Anchor) and the reported call_wall above spot.
    rows = [_row(95, -3.0), _row(100, 4.0), _row(110, 20.0)]
    lv = compute_levels(_payload(rows, spot=100.0, call_wall=110.0))
    strikes = {s["strike"] for s in lv["stacks"]}
    assert 110.0 in strikes
    stack = next(s for s in lv["stacks"] if s["strike"] == 110.0)
    assert "anchor" in stack["roles"]
    assert "call_wall" in stack["roles"]
    assert len(stack["roles"]) >= 2


# --------------------------------------------------------------------------- #
# 8. Degenerate input — honest nulls, no crash, no fabrication
# --------------------------------------------------------------------------- #

def test_empty_input_yields_honest_nulls():
    lv = compute_levels(_payload([], spot=None, net_gex_bn=None))
    assert lv["schema"] == SCHEMA
    anchor = _one(lv, "anchor")
    assert anchor["strike"] is None            # never a fabricated strike
    assert anchor["weight"] is None
    assert "No by_strike rows" in anchor["note"]
    assert lv["stacks"] == []


def test_none_payload_does_not_crash():
    lv = compute_levels(None)
    assert lv["schema"] == SCHEMA
    assert _one(lv, "anchor")["strike"] is None


def test_rows_missing_gamma_net_are_dropped_not_guessed():
    # One good row + one row with no gamma_net -> only the good one survives.
    rows = [_row(100, 7.0), {"strike": 105.0}]
    lv = compute_levels(_payload(rows, spot=100.0))
    assert _one(lv, "anchor")["strike"] == 100.0


# --------------------------------------------------------------------------- #
# 9. Palette colorblind swap
# --------------------------------------------------------------------------- #

def test_palette_default_and_colorblind_swap():
    rows = [_row(100, 5.0)]
    std = compute_levels(_payload(rows, spot=100.0), colorblind=False)
    assert std["palette_hint"]["sticky"] == "green"
    assert std["palette_hint"]["slippery"] == "red"
    assert std["palette_hint"]["colorblind"] is False

    cb = compute_levels(_payload(rows, spot=100.0), colorblind=True)
    assert cb["palette_hint"]["sticky"] == "blue"
    assert cb["palette_hint"]["slippery"] == "orange"
    assert cb["palette_hint"]["colorblind"] is True


# --------------------------------------------------------------------------- #
# 10. Counter — heaviest strike on the far side of the flip from the Anchor
# --------------------------------------------------------------------------- #

def test_counter_is_heaviest_on_far_side_of_flip():
    # Anchor = 120 at +20 (above flip). Flip at 105. Far side = below 105:
    # candidates 90 (|7|) and 100 (|12|) -> Counter = 100.
    rows = [
        _row(90, -7.0), _row(100, -12.0),      # below flip (far side)
        _row(110, 6.0), _row(120, 20.0),       # above flip (Anchor side)
    ]
    lv = compute_levels(_payload(rows, spot=118.0, gamma_flip=105.0))
    counter = _one(lv, "counter")
    assert counter["strike"] == 100.0
    assert counter["sticky"] is False


# --------------------------------------------------------------------------- #
# 11. Real-ish SPY reconstruction — internal consistency
# --------------------------------------------------------------------------- #

def _spy_reconstruction_payload() -> dict:
    """A realistic SPY options_hub.gex/v1 payload synthesized from the true compute_gex
    field names, anchored to observed live SPY structure (spot ~750, heavy call gamma
    into 755/760, slippery puts below, flip just above spot). Values are in $mn, signed
    per the dealer-sign convention (calls +, puts -)."""
    by_strike = [
        _row(735.0, -220.0),
        _row(740.0, -140.0),
        _row(742.0, -3.0),        # near-empty
        _row(744.0, -2.5),        # near-empty
        _row(746.0, -4.0),        # near-empty  -> void run of 3 (742,744,746)
        _row(748.0, -95.0),
        _row(750.0, 180.0),
        _row(752.0, 240.0),
        _row(755.0, 640.0),       # heaviest positive (Anchor / call wall region)
        _row(760.0, 410.0),
        _row(765.0, 120.0),
    ]
    return _payload(
        by_strike,
        spot=750.72,
        net_gex_bn=2.9,
        gamma_flip=749.4,
        call_wall=755.0,
        put_wall=735.0,
        root="SPY",
        asof="2026-07-16",
    )


def test_spy_reconstruction_internally_consistent():
    lv = compute_levels(_spy_reconstruction_payload())
    spot = lv["spot"]
    assert lv["schema"] == SCHEMA
    assert lv["root"] == "SPY"

    # Anchor is a real strike present in the input, and the max |gamma|.
    anchor = _one(lv, "anchor")
    input_strikes = {r["strike"] for r in _spy_reconstruction_payload()["by_strike"]}
    assert anchor["strike"] in input_strikes
    assert anchor["strike"] == 755.0           # the 640 mn strike
    assert anchor["sticky"] is True
    assert anchor["brightness"] == 1.0

    # Walls relate to spot sensibly: call wall above spot, put wall below spot.
    call_wall = _one(lv, "call_wall")
    put_wall = _one(lv, "put_wall")
    assert call_wall["strike"] is not None and call_wall["strike"] >= spot
    assert put_wall["strike"] is not None and put_wall["strike"] <= spot

    # Flip is within the reported strike range (or null) — here reused from the payload.
    flip = _one(lv, "flip")
    assert flip["strike"] is not None
    assert min(input_strikes) <= flip["strike"] <= max(input_strikes)

    # Every WEIGHTED located node sits on a real input strike (the Flip is a price
    # boundary, not a weighted strike, so its interpolated price is exempt — it is
    # range-checked separately above).
    for n in lv["nodes"]:
        if n["role"] == "flip":
            continue
        if n.get("strike") is not None:
            assert n["strike"] in input_strikes
        if n.get("brightness") is not None:
            assert 0.0 <= n["brightness"] <= 1.0

    # The crafted near-empty band (742/744/746) surfaces as a void.
    voids = _role(lv, "void")
    assert len(voids) == 1
    assert voids[0]["strike_lo"] == 742.0 and voids[0]["strike_hi"] == 746.0

    # Regime label agrees with the headline net-gamma sign (positive => sticky).
    assert lv["regime"]["label"] == "sticky"

    # Stacks (if any) reference only real strikes and carry >= 2 roles each.
    for s in lv["stacks"]:
        assert s["strike"] in input_strikes
        assert len(s["roles"]) >= 2
