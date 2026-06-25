"""Impulse-radar + OI-crowding alert emitters (engine/btc_alerts.py).

Verifies the P1 contract: act-tier LEADING crosses emit warnings, two legs
co-firing emit the loud trigger, the OI-crowding de-risk break fires
INDEPENDENT of funding (watch-tier, low-conviction), and ids dedupe.

Run: .venv/bin/python -m tests.test_btc_impulse_alerts
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from engine import btc_alerts as A  # noqa: E402
from engine import btc_impulse_radar  # noqa: E402


def _with_fire_series(fires, fn):
    orig = btc_impulse_radar.fire_series
    btc_impulse_radar.fire_series = lambda s=None: fires
    try:
        return fn()
    finally:
        btc_impulse_radar.fire_series = orig


def test_act_warnings_trigger_and_up_and_dedup():
    idx = pd.date_range("2025-01-01", periods=12, freq="D")
    d2 = pd.Series(False, index=idx); d2.iloc[5] = True            # D2 cross
    d3 = pd.Series(False, index=idx); d3.iloc[5] = True            # D3 cross same day -> trigger
    u1 = pd.Series(False, index=idx); u1.iloc[8] = True            # U1 wash-out
    fires = pd.DataFrame({"d2": d2, "d3": d3, "u1": u1})
    sig = pd.DataFrame({"close": pd.Series(60000.0, index=idx)})
    evs = _with_fire_series(fires, lambda: A.impulse_radar_events(sig))

    by_type = {}
    for e in evs:
        by_type.setdefault(e["type"], []).append(e)
    assert "impulse_warn_down" in by_type and "impulse_trigger_down" in by_type
    assert "impulse_warn_up" in by_type
    # down warnings + trigger are act-tier high; up is act-tier medium
    assert all(e["tier"] == "act" for e in evs)
    assert by_type["impulse_warn_down"][0]["severity"] == "high"
    assert by_type["impulse_warn_up"][0]["severity"] == "medium"
    # each carries an honest edge string + zh
    assert all(e["edge"] and e["headline_zh"] for e in evs)
    # ids are unique (idempotent dedupe key)
    ids = [e["id"] for e in evs]
    assert len(ids) == len(set(ids))


def test_no_event_when_no_cross():
    idx = pd.date_range("2025-01-01", periods=10, freq="D")
    fires = pd.DataFrame({"d2": pd.Series(False, index=idx),
                          "d3": pd.Series(False, index=idx),
                          "u1": pd.Series(False, index=idx)})
    sig = pd.DataFrame({"close": pd.Series(60000.0, index=idx)})
    assert _with_fire_series(fires, lambda: A.impulse_radar_events(sig)) == []


def test_oi_crowding_fires_independent_of_funding():
    """OI crossing into elevated must emit a watch-tier de-risk nudge even with
    NO funding columns present — the funding-AND gate is broken."""
    n = 320
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    ratio = np.full(n, 0.012)
    ratio[-40:] = np.linspace(0.012, 0.05, 40)          # OI ramps into the top of its window
    sig = pd.DataFrame({
        "close": pd.Series(60000.0, index=idx),
        "oi_mcap_ratio": pd.Series(ratio, index=idx),
        "oi_change": pd.Series(0.01, index=idx),         # building (positive)
        # NOTE: deliberately NO funding columns -> proves funding-independence
    }, index=idx)
    evs = A.leverage_derisk_events(sig)
    assert evs, "expected an OI-crowding de-risk event from rising OI without funding"
    e = evs[-1]
    assert e["type"] == "oi_crowding_derisk"
    assert e["tier"] == "watch"                          # low-conviction, NOT act-tier
    assert "low-conviction" in e["edge"].lower()
    assert e["context"]["oi_state"] in ("elevated", "stretched")


def test_oi_declining_is_not_crowded():
    n = 320
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    ratio = np.full(n, 0.012); ratio[-40:] = np.linspace(0.012, 0.05, 40)
    sig = pd.DataFrame({
        "close": pd.Series(60000.0, index=idx),
        "oi_mcap_ratio": pd.Series(ratio, index=idx),
        "oi_change": pd.Series(-0.01, index=idx),        # DECLINING -> state 'declining', never crowded
    }, index=idx)
    assert A.leverage_derisk_events(sig) == []


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed")
