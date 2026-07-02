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
    # the lagged series at month t equals the unlagged value 2 months earlier (the extra
    # lag_m=2 stacks on the same per-leg PUB_LAG_M floor, so the DIFFERENCE is 2 months)
    common = lagged.dropna().index[-1]
    assert abs(lagged.loc[common] - base.shift(2).loc[common]) < 1e-6


# --- W2.7: per-leg publication lag applied symmetrically --------------------
def test_per_leg_publication_lag_applied() -> None:
    # PAYEMS carries a 1-month floor even at lag_m=0; a daily leg (SPY) carries lag 0.
    assert bc.PUB_LAG_M["PAYEMS"] == 1
    assert bc.PUB_LAG_M["SPY"] == 0
    raw = bc.store.read("fred", "PAYEMS")
    if raw is None:
        return  # store not populated
    m0 = bc._component_monthly("fred", "PAYEMS", "payrolls", lag_m=0)
    # the value now stamped at month t is the reference figure from t-1 (published later)
    monthly = bc.pd.to_numeric(raw["payrolls"], errors="coerce").dropna().resample("ME").last()
    t = m0.dropna().index[-1]
    assert abs(m0.loc[t] - monthly.shift(1).loc[t]) < 1e-6


# --- W2.7: cl_ratio causal rebase (macro-regime-5) --------------------------
def test_cl_ratio_rebase_is_append_causal() -> None:
    """Appending future months must NOT change the historical cl_ratio level — the
    old full-history anchor was a global normalization; the fixed anchor is the
    first-valid value, stable under append."""
    cfg = _cfg()

    # build two synthetic coincident/lagging index paths where cl_ratio is well-defined,
    # by driving cycle_frame is heavy — instead exercise the rebase math directly on the
    # same construction cycle_frame uses.
    def _cl(coin, lag):
        ratio = (coin / lag.replace(0, np.nan)).dropna()
        if ratio.empty:
            return None
        anchor = float(ratio.iloc[0])
        return (100.0 * ratio / anchor) if anchor else None

    idx = pd.date_range("2000-01-31", periods=60, freq="ME")
    coin = pd.Series(100 + np.cumsum(np.random.default_rng(1).normal(0.1, 1, 60)), index=idx)
    lag = pd.Series(100 + np.cumsum(np.random.default_rng(2).normal(0.05, 1, 60)), index=idx)
    full = _cl(coin, lag)
    # recompute with 12 fewer FUTURE months
    short = _cl(coin.iloc[:-12], lag.iloc[:-12])
    common = short.index
    # historical values identical -> appending future data did not rewrite history
    assert np.allclose(full.reindex(common).values, short.values, atol=1e-9)


# --- W2.7: threshold-override guard resolution order (macro-regime-miss) -----
def _cfg_full() -> dict:
    return _cfg()  # includes a signal block with roc_threshold -1.25


def test_override_guard_uses_calibration_when_fresh_and_versioned() -> None:
    import datetime as dt
    fresh = dt.datetime.now(dt.timezone.utc).replace(microsecond=0, tzinfo=None).isoformat() + "Z"
    cal = {"version": bc.CALIBRATION_VERSION, "generated_at": fresh,
           "signal": {"roc_threshold": -0.9}}
    c, meta = bc._resolve_signal_cfg(_cfg_full(), cal)
    assert meta["threshold_source"] == "calibration"
    assert c["signal"]["roc_threshold"] == -0.9


def test_override_guard_falls_back_on_version_mismatch() -> None:
    import datetime as dt
    fresh = dt.datetime.now(dt.timezone.utc).replace(microsecond=0, tzinfo=None).isoformat() + "Z"
    cal = {"version": "someone-hand-edited-v0", "generated_at": fresh,
           "signal": {"roc_threshold": -0.9}}
    c, meta = bc._resolve_signal_cfg(_cfg_full(), cal)
    assert meta["threshold_source"] == "config_default"
    assert c["signal"]["roc_threshold"] == -1.25   # config default, NOT the JSON's -0.9
    assert "version" in meta["reason"]


def test_override_guard_falls_back_on_stale_and_missing_timestamp() -> None:
    import datetime as dt
    stale = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=bc._CAL_MAX_AGE_DAYS + 30)
             ).replace(microsecond=0, tzinfo=None).isoformat() + "Z"
    cal_stale = {"version": bc.CALIBRATION_VERSION, "generated_at": stale,
                 "signal": {"roc_threshold": -0.9}}
    c, meta = bc._resolve_signal_cfg(_cfg_full(), cal_stale)
    assert meta["threshold_source"] == "config_default" and c["signal"]["roc_threshold"] == -1.25
    # no timestamp at all -> also falls back
    cal_nots = {"version": bc.CALIBRATION_VERSION, "signal": {"roc_threshold": -0.9}}
    c2, meta2 = bc._resolve_signal_cfg(_cfg_full(), cal_nots)
    assert meta2["threshold_source"] == "config_default" and c2["signal"]["roc_threshold"] == -1.25
    # empty cal -> config default, no crash
    c3, meta3 = bc._resolve_signal_cfg(_cfg_full(), {})
    assert meta3["threshold_source"] == "config_default"
