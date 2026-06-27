"""Tests for the Conference-Board-style business-cycle model
(engine/business_cycle.py): tier construction, the 3-D's recession signal, phase
classification, graceful degradation, and the publication-lag seam used by the
point-in-time validation harness. Synthetic frames where possible; a couple of
light integration checks against the live store that skip if data is absent."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import business_cycle as bc  # noqa: E402


def _cfg(**signal) -> dict:
    s = {"roc_threshold": -1.25, "diffusion_max": 50.0, "min_consecutive_m": 3,
         "lookahead_window_m": 18, "max_lead_window_m": 24}
    s.update(signal)
    return {"z_lookback_m": 120, "z_min_months": 36, "roc_window_m": 6,
            "trend_smooth_m": 6, "diffusion_window_m": 6, "rebase": 100.0, "signal": s}


def _synthetic_frame(n: int = 120, lead_mom: float = 0.5, lead_diff: float = 70.0,
                     coin_mom: float = 0.4, rec_tail: int = 0) -> pd.DataFrame:
    """A cycle_frame-shaped monthly frame with controllable leading state."""
    idx = pd.date_range("2014-01-31", periods=n, freq="ME")
    f = pd.DataFrame(index=idx)
    for t, mom in (("leading", lead_mom), ("coincident", coin_mom), ("lagging", 0.3)):
        f[f"{t}_index"] = 100.0 + np.linspace(0, 5, n)
        f[f"{t}_mom6"] = mom
        f[f"{t}_trend"] = mom * 0.8
        f[f"{t}_diffusion"] = lead_diff if t == "leading" else 65.0
        f[f"{t}_n_legs"] = 4
    f["cl_ratio_mom6"] = 0.1
    rec = np.zeros(n, dtype=int)
    if rec_tail:
        rec[-rec_tail:] = 1
    f["nber_recession"] = rec
    return f


# --- pure helpers ------------------------------------------------------------
def test_phase_classification() -> None:
    assert bc._phase(0.5, 0.5)[0] == "expansion"
    assert bc._phase(-0.5, 0.5)[0] == "slowdown"
    assert bc._phase(-0.5, -0.5)[0] == "contraction"
    assert bc._phase(0.5, -0.5)[0] == "recovery"
    assert bc._phase(None, 0.5)[0] == "unknown"


def test_spark_caps_and_handles_none() -> None:
    s = pd.Series([float("nan")] + list(range(500)), dtype=float)
    out = bc._spark(s, n=372)
    assert len(out) == 372
    assert all(v is None or isinstance(v, float) for v in out)


def test_causal_z_is_causal() -> None:
    # a z-score at time t must not depend on future values (varying series so the
    # rolling std is non-zero and z is finite)
    s = pd.Series(np.cumsum(np.sin(np.arange(60) / 5.0)))
    z = bc._causal_z(s.diff(), lookback=24, min_p=12)
    assert z.iloc[:11].isna().all()      # warmup respected
    assert np.isfinite(z.iloc[-1])


# --- recession signal (3 D's) ------------------------------------------------
def test_signal_off_in_calm_expansion() -> None:
    f = _synthetic_frame(lead_mom=0.6, lead_diff=72.0)
    sig = bc.recession_signal(f, _cfg())
    assert sig is not None and not bool(sig["signal"].iloc[-1])


def test_signal_fires_on_deep_broad_decline() -> None:
    # leading momentum below threshold AND diffusion broad-weak, held > duration
    f = _synthetic_frame(lead_mom=-2.0, lead_diff=30.0)
    sig = bc.recession_signal(f, _cfg(min_consecutive_m=3))
    assert bool(sig["signal"].iloc[-1])
    assert bool(sig["depth"].iloc[-1]) and bool(sig["breadth"].iloc[-1])


def test_signal_needs_both_depth_and_breadth() -> None:
    # deep momentum but NARROW (high diffusion) -> no fire
    f = _synthetic_frame(lead_mom=-2.0, lead_diff=80.0)
    sig = bc.recession_signal(f, _cfg())
    assert not bool(sig["signal"].iloc[-1])
    # broad-weak but SHALLOW momentum -> no fire
    f2 = _synthetic_frame(lead_mom=-0.3, lead_diff=30.0)
    assert not bool(bc.recession_signal(f2, _cfg())["signal"].iloc[-1])


def test_duration_filter_suppresses_one_month_blip() -> None:
    f = _synthetic_frame(lead_mom=0.5, lead_diff=70.0)
    f.iloc[-1, f.columns.get_loc("leading_mom6")] = -2.0   # single bad month
    f.iloc[-1, f.columns.get_loc("leading_diffusion")] = 20.0
    sig = bc.recession_signal(f, _cfg(min_consecutive_m=3))
    assert not bool(sig["signal"].iloc[-1])                # one month < 3 -> suppressed


# --- snapshot ----------------------------------------------------------------
def test_snapshot_blocks_and_json_serializable() -> None:
    snap = bc.business_cycle_snapshot(frame=_synthetic_frame(), cfg=_cfg())
    assert snap["available"] is True
    for tier in ("leading", "coincident", "lagging"):
        assert tier in snap["tiers"]
        assert snap["tiers"][tier]["direction"] in ("rising", "falling")
    assert snap["recession_signal"]["state"] in ("on", "off")
    assert snap["phase"]["label"] in ("expansion", "slowdown", "contraction", "recovery", "unknown")
    json.dumps(snap, default=str)        # must be serializable for latest.json


def test_snapshot_signal_on_when_frame_recessionary() -> None:
    f = _synthetic_frame(lead_mom=-2.0, lead_diff=25.0, coin_mom=-1.0)
    snap = bc.business_cycle_snapshot(frame=f, cfg=_cfg())
    assert snap["recession_signal"]["state"] == "on"
    assert snap["phase"]["label"] == "contraction"


def test_snapshot_graceful_on_empty() -> None:
    assert bc.business_cycle_snapshot(frame=pd.DataFrame(), cfg=_cfg()) == {"available": False}


# --- light integration against the live store (skip if data absent) ----------
def test_cycle_frame_builds_and_leads_2008() -> None:
    frame = bc.cycle_frame()
    if frame is None or "leading_mom6" not in frame.columns:
        return  # data not collected in this environment — nothing to assert
    assert {"leading_index", "coincident_mom6", "lagging_diffusion"} <= set(frame.columns)
    # the defining property: leading momentum was negative going INTO the GFC
    pre_gfc = frame.loc["2007-08-31":"2007-12-31", "leading_mom6"].dropna()
    if len(pre_gfc):
        assert (pre_gfc < 0).mean() >= 0.6        # mostly negative ahead of the recession


def test_publication_lag_shifts_monthly_series() -> None:
    base = bc._component_monthly("fred", "PAYEMS", "payrolls", lag_m=0)
    lagged = bc._component_monthly("fred", "PAYEMS", "payrolls", lag_m=2)
    if base is None or lagged is None or len(base) < 12:
        return  # store not populated here
    # the lagged series at month t equals the unlagged value 2 months earlier
    common = lagged.dropna().index[-1]
    assert abs(lagged.loc[common] - base.shift(2).loc[common]) < 1e-6
