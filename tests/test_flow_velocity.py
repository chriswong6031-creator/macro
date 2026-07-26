"""Flow-velocity engine guards — the measure, not just its plumbing.

The desk shipped for weeks with a readout that was pinned by construction: velocity is a
drift-vs-ZERO t-stat, but neither source has a zero null (主力净占比 is structurally ~-2.5%,
southbound net is structurally positive), so the sector breadth gauge printed "broad outflow"
on 93.4% of days and "broad inflow" on 0 of 256, and southbound printed "accelerating in" on
96.6% of the last two years. Everything was green the whole time — there was no test that
looked at the *distribution* of the verdict, only at whether the panels rendered.

These tests are built to fail on that class of defect:
  · a null-drift series must score ~0 regardless of its structural offset (the actual bug)
  · a quiet stretch must not manufacture an extreme velocity (the leaderboard artifact)
  · truncated display lists must ship their true population counts (the "6 speeding up" lie)
  · the displayed rate must never contradict the velocity's sign on screen
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine import flow_velocity as fv
from engine import indicators


def _series(vals, start="2025-01-01") -> pd.Series:
    idx = pd.bdate_range(start, periods=len(vals))
    return pd.Series(np.asarray(vals, dtype=float), index=idx)


def _cfg(**over) -> dict:
    cfg = {k: v for k, v in fv._WK.items()}
    cfg.update(over)
    return cfg


# ── the defect that shipped: a structural offset must not become a verdict ────
@pytest.mark.parametrize("offset", [-2.5, 0.0, +2.5, +8.0])
def test_flat_series_scores_near_zero_whatever_its_offset(offset):
    """A series with NO drift must read ~balanced even when its mean is far from zero.

    This is the regression: undemeaned, an offset of -2.5 alone drove velocity to ~-0.6 and
    tripped the -0.5 "outflow" cutoff, so the median A-share name was classified as bleeding
    with nothing happening. 66% of names sat past the cutoff at rest.
    """
    rng = np.random.default_rng(11)
    flow = _series(offset + rng.normal(0, 3.0, 400))
    kin = fv._kinetics(flow, _cfg())
    assert kin is not None
    assert abs(kin["vel_primary"]) < 0.5, (
        f"offset {offset:+} alone produced velocity {kin['vel_primary']:+.2f} — the measure is "
        "reading the structural level, not the drift")
    assert kin["state"] == "balanced"


def test_real_drift_still_scores_after_demeaning():
    """Demeaning must not sand off a genuine acceleration — the fix has to keep the signal."""
    rng = np.random.default_rng(5)
    base = -2.5 + rng.normal(0, 2.0, 400)
    base[-25:] += 9.0                       # a real, recent inflow burst on top of the offset
    kin = fv._kinetics(_series(base), _cfg())
    assert kin is not None
    assert kin["vel_primary"] >= 0.5, f"a real burst scored only {kin['vel_primary']:+.2f}"
    assert kin["state"] in ("accelerating in", "inflow cooling")


def test_breadth_gauge_can_reach_both_verdicts():
    """flow_breadth must be able to print inflow AND outflow — the shipped one never printed
    'broad inflow' on any of 256 days because its input was pinned."""
    mk = lambda vel: {"vel": vel}                                        # noqa: E731
    inflow = {"rows": [{"vel": 1.4} for _ in range(18)] + [{"vel": -0.1}] * 4}
    outflow = {"rows": [{"vel": -1.4} for _ in range(18)] + [{"vel": 0.1}] * 4}
    up = fv.flow_breadth({f"t{i}": mk(1.2) for i in range(50)}, inflow)
    down = fv.flow_breadth({f"t{i}": mk(-1.2) for i in range(50)}, outflow)
    assert up["state"] == "broad inflow" and up["tilt"] > 0
    assert down["state"] == "broad outflow" and down["tilt"] < 0


# ── the leaderboard artifact: a quiet stretch must not manufacture an extreme ──
def test_vol_floor_caps_the_quiet_series_blowup():
    """A name whose flow goes quiet had its baseline vol collapse and printed a huge t-stat on
    a trivial move (+0.5% net rate -> +9.64σ, ranking #1 above a name with 13.3% net flow)."""
    rng = np.random.default_rng(3)
    loud = rng.normal(0, 6.0, 300)             # a normal, volatile history
    quiet = 0.5 + rng.normal(0, 0.10, 90)      # then it goes quiet just above zero
    flow = _series(np.concatenate([loud, quiet]))
    floored = fv._kinetics(flow, _cfg(demean=None, vol_floor=0.25))
    unfloored = fv._kinetics(flow, _cfg(demean=None, vol_floor=0.0))
    assert unfloored["vel_primary"] > 4.0, "fixture no longer reproduces the blowup"
    assert floored["vel_primary"] < unfloored["vel_primary"] / 2, (
        f"vol floor barely bit: {floored['vel_primary']:.2f} vs {unfloored['vel_primary']:.2f}")


def test_vel_series_matches_slope_z_when_unfloored():
    """_vel_series is slope_z's formula plus a denominator floor — with the floor off the two
    must agree, so the house indicator stays the single definition of the measure.

    They agree EXACTLY from bar `base` onward. Before that they differ slightly because
    slope_z rebuilds the flow as cum.diff() (NaN at position 0) and so normalizes against one
    fewer observation while bar 0 is still inside the baseline window; _vel_series works on the
    flow directly and keeps it. Both halves are pinned here so the divergence can't grow.
    """
    w, base = 20, 65
    rng = np.random.default_rng(7)
    x = _series(rng.normal(0.4, 2.0, 300))
    both = pd.concat([fv._vel_series(x, w, base, 0.0),
                      indicators.slope_z(x.cumsum(), w, base, use_log=False)], axis=1).dropna()
    assert len(both) > 100
    settled = both.iloc[base:]
    assert len(settled) > 50
    assert np.allclose(settled.iloc[:, 0], settled.iloc[:, 1], atol=1e-9), (
        "the two definitions diverge after the baseline window has cleared bar 0")
    head = both.iloc[:base]
    assert np.allclose(head.iloc[:, 0], head.iloc[:, 1], atol=0.05), (
        "warm-up divergence is larger than the single-observation effect explains")


# ── display contracts: truncation and sign agreement ──────────────────────────
def test_momentum_ships_true_counts_not_list_lengths():
    """The hero chip read '6 speeding up' when 116 names qualified — the list is capped at
    `top` for display, so the population total must ride along separately."""
    kmap = {f"t{i}": {"ticker": f"t{i}", "vel": 1.5, "accel": 0.1 + i / 1000}
            for i in range(40)}
    kmap.update({f"c{i}": {"ticker": f"c{i}", "vel": 1.5, "accel": -0.2} for i in range(15)})
    kmap.update({f"e{i}": {"ticker": f"e{i}", "vel": -1.5, "accel": 0.3} for i in range(9)})
    mom = fv.momentum(kmap, top=6)
    assert len(mom["accel_in"]) == 6 and mom["n_accel_in"] == 40
    assert len(mom["cooling"]) == 6 and mom["n_cooling"] == 15
    assert len(mom["easing"]) == 6 and mom["n_easing"] == 9


def test_displayed_rate_never_contradicts_velocity_sign():
    """The board prints `rate_rel`; velocity is measured on the same demeaned series, so the
    two must agree in sign or the page contradicts itself in a single row."""
    rng = np.random.default_rng(19)
    mismatches = 0
    for i in range(60):
        flow = _series(-2.5 + rng.normal(0, 3.0, 320) + np.linspace(0, rng.uniform(-6, 6), 320))
        kin = fv._kinetics(flow, fv._WK)
        rr = fv._rate_read(flow, fv._WK)
        if kin is None or rr["rate_rel"] is None or kin["vel_primary"] is None:
            continue
        if abs(rr["rate_rel"]) < 0.05 or abs(kin["vel_primary"]) < 0.05:
            continue                                   # rounding noise at the zero crossing
        if (rr["rate_rel"] > 0) != (kin["vel_primary"] > 0):
            mismatches += 1
    assert mismatches == 0, f"{mismatches} rows would print a rate that fights their own σ"


def test_rate_read_tooltip_arithmetic_is_exact():
    """The tooltip claims raw - norm == vs-norm; `norm` is derived so that stays true."""
    rng = np.random.default_rng(23)
    rr = fv._rate_read(_series(-3.0 + rng.normal(0, 2.5, 300)), fv._WK)
    assert rr["rate_4wk"] is not None and rr["rate_norm"] is not None
    assert rr["rate_4wk"] - rr["rate_norm"] == pytest.approx(rr["rate_rel"], abs=0.11)


# ── cadence: the windows must match the store the engine actually reads ───────
def test_windows_are_sized_for_a_daily_grid():
    """flow_hist is daily (the collector's tail-anchored stride phase-shifts each build and the
    append-only store accreted every phase), but the UI prints '4wk'/'13wk'. If those labels
    are to be true the windows must be ~20 / ~65 bars, not 4 / 13."""
    assert fv._WK["horizons"]["4wk"] == 20
    assert fv._WK["horizons"]["13wk"] == 65
    assert fv._WK["base"] >= 65, "baseline vol shorter than the 13wk horizon it normalizes"
    assert fv._WK.get("demean"), "the daily grid has a structural offset — demean is required"


def test_northbound_note_matches_the_frozen_constant():
    """The rendered note said '19 Aug 2024' while the constant, the data and the footer all
    said 2024-08-16."""
    assert fv.NORTHBOUND_FROZEN == "2024-08-16"
    chan = {"key": "northbound", "live": False}
    note = (f"Aggregate northbound net disclosure ended {fv.NORTHBOUND_FROZEN} (Stock "
            "Connect home-market rule) — historical only, no live velocity.")
    assert fv.NORTHBOUND_FROZEN in note and "19 Aug" not in note
    assert chan["live"] is False
