"""Unit tests for the Impulse Tracker engine (engine/impulse.py).

Pure / synthetic — no network, no disk. Covers the load-bearing properties:
  • leakage-free: recompute-on-truncated == full-history (causal transforms).
  • the EARLY-IGNITION vs EXTENDED_RUN split (the core product rule: a name that
    already ran is demoted, never surfaced as a fresh buy).
  • the absolute-trend gate (no falling knives) and volume confirmation.
  • NaN-not-0 semantics + the min-history drop.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine import impulse


# --------------------------------------------------------------------------- #
#  classify() — absolute, per-row state logic (the heart of the lane routing)
# --------------------------------------------------------------------------- #
def _row(**kw) -> pd.DataFrame:
    """One feature row with sensible defaults; override what a test cares about."""
    base = dict(accel_z=0.0, impulse_macd=0.0, trend_vel=0.0, runup_20=0.0,
                dist_50=0.0, dist_200=0.0, vol_vel=1.2, rvol=1.5)
    base.update(kw)
    return pd.DataFrame({"X": base}).T


CFG = impulse.ImpulseConfig()


def test_classify_early_ignition():
    f = _row(accel_z=0.9, impulse_macd=0.5, trend_vel=0.6, runup_20=0.06,
             dist_50=0.04, dist_200=0.10, vol_vel=1.4, rvol=1.6)
    assert impulse.classify(f, CFG)["X"] == impulse.EARLY_IGNITION


def test_classify_extended_by_runup():
    # accelerating but already up 30% in 20d → no entry → EXTENDED_RUN, not a buy.
    f = _row(accel_z=0.9, impulse_macd=0.5, trend_vel=0.6, runup_20=0.30,
             dist_50=0.10, dist_200=0.20)
    assert impulse.classify(f, CFG)["X"] == impulse.EXTENDED_RUN


def test_classify_extended_by_ma_distance():
    # 50% above the 200d average = a sustained runner, even with a small 20d gain.
    f = _row(accel_z=0.9, impulse_macd=0.5, trend_vel=0.6, runup_20=0.05,
             dist_50=0.05, dist_200=0.50)
    assert impulse.classify(f, CFG)["X"] == impulse.EXTENDED_RUN


def test_classify_downtrend_never_buys():
    # acceleration up but in an active down-trend (falling knife) → NOT a buy.
    f = _row(accel_z=0.9, impulse_macd=0.5, trend_vel=-2.0, runup_20=0.05)
    assert impulse.classify(f, CFG)["X"] != impulse.EARLY_IGNITION


def test_classify_volume_unconfirmed_demotes_to_igniting():
    # fresh + accelerating but volume NOT confirming → IGNITING, not EARLY.
    f = _row(accel_z=0.9, impulse_macd=0.5, trend_vel=0.6, runup_20=0.05,
             vol_vel=0.9, rvol=0.9)
    assert impulse.classify(f, CFG)["X"] == impulse.IGNITING


def test_classify_missing_volume_is_allowed():
    # absent volume is "unknown", not "no signal" → does not block the buy lane.
    f = _row(accel_z=0.9, impulse_macd=0.5, trend_vel=0.6, runup_20=0.05,
             vol_vel=np.nan, rvol=np.nan)
    assert impulse.classify(f, CFG)["X"] == impulse.EARLY_IGNITION


def test_classify_fading():
    f = _row(accel_z=-0.9, impulse_macd=-0.5, trend_vel=-0.4)
    assert impulse.classify(f, CFG)["X"] == impulse.FADING


def test_classify_coiling():
    # flat price, volume perking up, not yet accelerating → pre-ignition watch.
    f = _row(accel_z=0.1, impulse_macd=0.0, trend_vel=0.0, runup_20=0.01, vol_vel=1.3)
    assert impulse.classify(f, CFG)["X"] == impulse.COILING


# --------------------------------------------------------------------------- #
#  synthetic price panels for the integration / leakage tests
# --------------------------------------------------------------------------- #
def _panel():
    idx = pd.bdate_range("2024-01-01", periods=260)
    n = len(idx)
    flat = np.full(n, 100.0)

    # EARLY: flat base, then a clean +8% ramp over the last 12 sessions.
    early = flat.copy()
    early[-12:] = 100.0 * (1 + np.linspace(0, 0.08, 12))

    # EXTENDED: flat base, then a CONVEX +35% ramp over the last 25 sessions —
    # still accelerating into the close (so it ignites) AND already up a lot (so the
    # extension gate routes it to EXTENDED_RUN, never the buy lane).
    ext = flat.copy()
    ext[-25:] = 100.0 * (1 + 0.35 * np.linspace(0, 1, 25) ** 2)

    # FADE: ramp up to a peak at day -15, then sell off into the close.
    fade = flat.copy()
    fade[-30:-15] = 100.0 * (1 + np.linspace(0, 0.12, 15))
    fade[-15:] = fade[-16] * (1 - np.linspace(0, 0.10, 15))

    # DEAD: flat with tiny deterministic wobble.
    dead = 100.0 + 0.05 * np.sin(np.arange(n))

    closes = pd.DataFrame({"EARLY": early, "EXT": ext, "FADE": fade, "DEAD": dead}, index=idx)

    vol = pd.DataFrame(1.0e6, index=idx, columns=closes.columns)
    vol.iloc[-3:, vol.columns.get_loc("EARLY")] *= 1.8   # volume confirming the EARLY ramp
    vol.iloc[-3:, vol.columns.get_loc("EXT")] *= 1.5
    return closes, vol


def test_states_on_synthetic_panel():
    closes, vol = _panel()
    feat = impulse.compute_features(closes, vol, cfg=CFG)
    state = impulse.classify(feat, CFG)
    assert state["EARLY"] == impulse.EARLY_IGNITION
    assert state["EXT"] == impulse.EXTENDED_RUN
    assert state["FADE"] == impulse.FADING
    # the dead-flat name is never a buy
    assert state["DEAD"] != impulse.EARLY_IGNITION


def test_score_panel_structure_and_ranking():
    closes, vol = _panel()
    res = impulse.score_panel(closes, vol, cfg=CFG)
    for col in ("impulse_score", "state", "just_starting", "raw", "liquid",
                "accel_z", "vol_vel", "days_igniting"):
        assert col in res.columns
    # sorted by score descending
    assert res["impulse_score"].is_monotonic_decreasing
    assert res["impulse_score"].between(0, 100).all()
    # the fresh igniter outranks the already-extended runner
    assert res.loc["EARLY", "impulse_score"] >= res.loc["EXT", "impulse_score"]
    # just_starting flags exactly the EARLY-state names
    assert bool(res.loc["EARLY", "just_starting"]) is True


def test_days_since_ignition_fresh_vs_flat():
    closes, vol = _panel()
    feat = impulse.compute_features(closes, vol, cfg=CFG)
    assert feat.loc["EARLY", "days_igniting"] >= 1     # ramped into the close = igniting now
    assert feat.loc["DEAD", "days_igniting"] == 0       # never igniting


def test_leakage_free_recompute():
    # a deterministic multi-name random walk; recompute at an earlier asof on the
    # FULL frame (sliced internally) must equal recompute on the TRUNCATED frame.
    rng = np.random.default_rng(7)
    idx = pd.bdate_range("2023-01-01", periods=220)
    data = 100 * np.exp(np.cumsum(rng.normal(0, 0.012, (220, 8)), axis=0))
    closes = pd.DataFrame(data, index=idx, columns=[f"T{i}" for i in range(8)])
    vol = pd.DataFrame(rng.uniform(5e5, 5e6, (220, 8)), index=idx, columns=closes.columns)
    asof = idx[-30]
    full = impulse.score_panel(closes, vol, asof=asof, cfg=CFG)
    trunc = impulse.score_panel(closes.loc[:asof], vol.loc[:asof], cfg=CFG)
    common = full.index.intersection(trunc.index)
    assert len(common) > 0
    assert (full.loc[common, "raw"] - trunc.loc[common, "raw"]).abs().max() < 1e-9
    assert (full.loc[common, "accel_z"] - trunc.loc[common, "accel_z"]).abs().max() < 1e-9


def test_nan_volume_is_not_zero():
    closes, vol = _panel()
    vol["EARLY"] = np.nan          # wipe one name's volume entirely
    feat = impulse.compute_features(closes, vol, cfg=CFG)
    # volume features are NaN (unknown), never a fake 0
    assert pd.isna(feat.loc["EARLY", "vol_vel"])
    assert pd.isna(feat.loc["EARLY", "rvol"])
    # price impulse still computes, and missing-volume must not block the buy lane
    assert impulse.classify(feat, CFG)["EARLY"] == impulse.EARLY_IGNITION


def test_min_history_drops_short_names():
    closes, vol = _panel()
    # a name with only 20 valid closes (< min_history 40) must be dropped, not scored 0
    closes["SHORT"] = np.nan
    closes.iloc[-20:, closes.columns.get_loc("SHORT")] = 50.0
    vol["SHORT"] = 1.0e6
    feat = impulse.compute_features(closes, vol, cfg=CFG)
    assert "SHORT" not in feat.index
    assert "EARLY" in feat.index


def test_config_from_config_overrides_and_ignores_unknown():
    cfg = impulse.ImpulseConfig.from_config(
        {"runup_early_max": 0.25, "min_dollar_vol": 5.0e6, "bogus_key": 1})
    assert cfg.runup_early_max == 0.25
    assert cfg.min_dollar_vol == 5.0e6
    assert cfg.accel_early_z == impulse.ImpulseConfig().accel_early_z  # untouched default
    assert not hasattr(cfg, "bogus_key")


def test_empty_input_is_safe():
    empty = pd.DataFrame()
    assert impulse.compute_features(empty, None, cfg=CFG).empty
    assert impulse.score_panel(empty, None, cfg=CFG).empty


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
