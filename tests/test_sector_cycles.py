"""Sector Cycle Intelligence engine tests — ZigZag turns, oscillator, phase
classification, projection, and an end-to-end compute() smoke test."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import sector_cycles as sc  # noqa: E402

IDX = pd.bdate_range("2020-01-01", periods=900)


def _saw(ampl=0.5, period=180, n=900, trend=0.0003):
    """Deterministic triangle-wave price with a gentle uptrend (clean major swings)."""
    t = np.arange(n)
    phase = (t % period) / period
    tri = np.where(phase < 0.5, phase * 2, 2 - phase * 2)        # 0..1..0
    return pd.Series(100 * np.exp(trend * t) * (1 + ampl * tri), index=IDX[:n])


# ── ZigZag swing detection ───────────────────────────────────────────────────

def test_zigzag_alternates_and_is_significant():
    s = _saw(ampl=0.5, period=180)
    turns = sc._detect_swings(s, pct=12.0)
    assert len(turns) >= 5
    # strict alternation
    kinds = [t["k"] for t in turns]
    for a, b in zip(kinds, kinds[1:]):
        assert a != b, f"non-alternating turns: {kinds}"
    # every confirmed leg clears the threshold (provisional last leg may not)
    for t in turns[1:-1]:
        assert t["mag_pct"] is None or t["mag_pct"] >= 12.0 - 1e-6
    assert turns[-1]["provisional"] is True
    assert all(set(["date", "t", "x", "px", "k"]).issubset(t) for t in turns)


def test_zigzag_threshold_thins_turns():
    s = _saw(ampl=0.5, period=120)
    assert len(sc._detect_swings(s, pct=8.0)) >= len(sc._detect_swings(s, pct=20.0))


def test_zigzag_flat_series_no_swings():
    flat = pd.Series(np.full(400, 100.0) + np.random.default_rng(0).normal(0, 0.05, 400), index=IDX[:400])
    turns = sc._detect_swings(flat, pct=12.0)
    # a noisy-flat line never reverses 12% -> only the provisional leg, no confirmed turns
    assert len([t for t in turns if not t["provisional"]]) <= 1


# ── oscillator ───────────────────────────────────────────────────────────────

def test_detrended_osc_bounded_and_tracks_cycle():
    s = _saw(ampl=0.6, period=200)
    osc = sc._detrended_osc(s).dropna()
    assert osc.between(-0.01, 100.01).all()
    # the oscillator should be higher near a price peak than near the prior trough
    assert osc.max() > 60 and osc.min() < 40


# ── phase classification ─────────────────────────────────────────────────────

def test_classify_phase_buckets():
    up_w, up3 = {"macd_pos": True}, {"macd_pos": True}
    dn_w, dn3 = {"macd_pos": False}, {"macd_pos": False}
    # 2026-07 rollover-lag fix: high + rising WITHOUT deceleration evidence is a leader
    # in full thrust — Trending (extended), not Topping (XLV read Topping at breadth 81%)
    assert sc._classify_phase(85, +5, up_w, up3, True)[0] == "Expansion"
    # high + rising WITH confirmed deceleration (3D negative / weekly fading) = true Topping
    assert sc._classify_phase(85, +5, up_w, dn3, True)[0] == "Peak"
    assert sc._classify_phase(85, +5, {"macd_pos": True, "macd_approaching_dn": True},
                              up3, True)[0] == "Peak"
    assert sc._classify_phase(85, -5, dn_w, dn3, True)[0] == "Downturn"    # high + falling = rolling over
    assert sc._classify_phase(50, +5, up_w, up3, True)[0] == "Expansion"   # mid + rising
    assert sc._classify_phase(20, +5, up_w, up3, True)[0] == "Recovery"    # low + rising
    assert sc._classify_phase(15, -5, dn_w, dn3, False)[0] == "Trough"     # low + falling = bottoming
    # every phase is a known bucket with a hue
    for pos in (10, 50, 90):
        for sl in (-8, 8):
            ph, lab = sc._classify_phase(pos, sl, up_w, dn3, True)
            assert ph in sc.PHASES and isinstance(lab, str) and lab


def test_classify_phase_anticipates_rollover():
    """2026-07 sector-central audit: the weekly histogram holds positive for weeks after
    a real top, so the pre-cross deceleration window must flip the direction vote —
    XLK's exact stamp (weekly still positive but approaching its cross, 3D negative,
    oscillator collapsing) must read Rolling over, not Topping/Trending."""
    w_fading = {"macd_pos": True, "macd_approaching_dn": True}
    dn3 = {"macd_pos": False}
    # stretched (XLK 2026-07-16: pos 70.2, slope −20.7) → Downturn / Rolling over
    assert sc._classify_phase(70.2, -20.7, w_fading, dn3, True) == ("Downturn", "Rolling over")
    # mid position (ai_infra: pos 60.1, slope −30.4) → also Rolling over
    assert sc._classify_phase(60.1, -30.4, w_fading, dn3, True)[0] == "Downturn"
    # direction TIES break to the FASTER 3D clock, not the stale weekly sign
    # (weekly pos, 3D negative, slope down: votes 2−1−1=0 → 3D decides → falling)
    assert sc._classify_phase(60.0, -5.0, {"macd_pos": True}, dn3, True)[0] == "Downturn"
    # ... and the monthly kernel (t3={}) keeps the legacy weekly-sign tiebreak
    assert sc._classify_phase(60.0, -5.0, {"macd_pos": True}, {}, True)[0] == "Expansion"


# ── projection ───────────────────────────────────────────────────────────────

def test_project_next_alternates_and_ranges():
    s = _saw(ampl=0.5, period=180)
    turns = sc._detect_swings(s, pct=12.0)
    proj = sc._project_next(turns, s.index[-1])
    assert proj is not None
    assert proj["nextTurn"] in ("peak", "trough")
    # W1.6: projection anchors at the last CONFIRMED turn and projects its opposite
    # (which matches the provisional open-leg extreme, so compare vs confirmed only)
    last_confirmed = [t for t in turns if not t.get("provisional")][-1]
    assert proj["nextTurn"] != last_confirmed["k"]
    assert proj["period_yrs"]["lo"] <= proj["period_yrs"]["median"] <= proj["period_yrs"]["hi"]


def test_x_to_ym_roundtrips_month():
    assert sc._x_to_ym(2026.0) == "2026-01"
    assert sc._x_to_ym(2026.96) in ("2026-12", "2027-01")


# ── end-to-end ───────────────────────────────────────────────────────────────

def test_compute_smoke():
    try:
        data = sc.compute()
    except Exception as e:  # pragma: no cover - data env issue
        pytest.skip(f"yahoo_closes unavailable: {e}")
    if not data:
        pytest.skip("no sector data in this environment")
    assert data["meta"]["n_sectors"] >= 8
    assert set(data["phases"]) == {"Trough", "Recovery", "Expansion", "Peak", "Downturn"}
    for s in data["sectors"]:
        assert s["ticker"] in sc.SECTORS
        assert s["price"] and s["osc"], f"{s['ticker']} missing series"
        assert s["now"]["phase"] in sc.PHASES
        assert 0 <= s["now"]["pos"] <= 100
        # turns alternate
        kinds = [t["k"] for t in s["turns"]]
        for a, b in zip(kinds, kinds[1:]):
            assert a != b
        # rebased series starts ~100
        assert abs(s["price"][0]["v"] - 100.0) < 5.0
        if s["proj"]:
            assert s["proj"]["nextTurn"] in ("peak", "trough")


def test_compute_json_serialisable():
    import json
    data = sc.compute()
    if not data:
        pytest.skip("no sector data")
    js = json.dumps(data)            # must not raise (no numpy/Timestamp leakage)
    assert "NaN" not in js and "Infinity" not in js
