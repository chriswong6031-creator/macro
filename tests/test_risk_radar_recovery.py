"""Risk-Radar DE-ESCALATION (engine/risk_radar_recovery.py + risk_radar.trajectory).

Covers: the trajectory phase classifier (receding / peaking / rising), the liquidity-catalyst
detector, the assembled recovery read, and the load-bearing invariant that it is DISPLAY-ONLY
(it never injects a score ceiling or amplification key into the radar view-model)."""
import numpy as np
import pandas as pd

from engine import risk_radar, risk_radar_intl, risk_radar_recovery


def _subs(vals):
    """A synthetic Tier-A subscore frame whose worst-scare path follows `vals` (0-100)."""
    idx = pd.bdate_range("2026-01-01", periods=len(vals))
    v = np.asarray(vals, dtype=float)
    return pd.DataFrame({"credit": v, "rates": v * 0.6, "bubble": v * 0.5,
                         "growth": v * 0.4, "vol": v * 0.3}, index=idx)


# ---- trajectory phase classifier --------------------------------------------------------------
def test_trajectory_receding_after_peak():
    vals = list(np.linspace(20, 92, 55)) + list(np.linspace(92, 70, 25))   # rise then fall
    t = risk_radar.trajectory(_subs(vals), risk_radar._calib())
    assert t is not None
    assert t["phase"] == "receding"
    assert t["velocity"] < 0                # falling
    assert t["off_peak"] > 0                # below the recent peak
    assert t["reached_risk"] is True
    assert t["spark_pts"]                   # a drawable sparkline


def test_trajectory_peaking_when_flat_at_top():
    vals = list(np.linspace(30, 92, 55)) + [92, 93, 92, 93, 92, 93, 92, 93, 92, 92,
                                            93, 92, 92, 93, 92, 92, 93, 92, 92, 93,
                                            92, 92, 93, 92, 92]               # rise then plateau
    t = risk_radar.trajectory(_subs(vals), risk_radar._calib())
    assert t["phase"] == "peaking"
    assert abs(t["velocity"]) < 1.5         # momentum stalled, not yet falling


def test_trajectory_rising_is_not_a_recovery():
    vals = list(np.linspace(20, 95, 80))    # monotonic up
    t = risk_radar.trajectory(_subs(vals), risk_radar._calib())
    assert t["phase"] == "rising"


def test_trajectory_calm_when_never_hot():
    vals = list(np.linspace(10, 35, 80))    # never reaches the caution band
    t = risk_radar.trajectory(_subs(vals), risk_radar._calib())
    assert t["reached_risk"] is False
    assert t["phase"] == "calm"


# ---- liquidity-catalyst detector --------------------------------------------------------------
def test_liquidity_catalysts_fed_legs():
    latest = {"liquidity_overlay": "expanding",
              "fed_stance": {"stance": "dovish", "implied_cuts_12m": 3.0, "guidance": "easing"},
              "fed_path": {"implied_cuts_12m": 3.0}}
    keys = {c["key"] for c in risk_radar_recovery._liquidity_catalysts(latest)}
    assert "fed_netliq" in keys            # TGA drawdown / net-liquidity expanding
    assert "fed_policy" in keys            # dovish / cuts priced (the emergency-cut case)


def test_liquidity_catalysts_quiet_when_contracting():
    latest = {"liquidity_overlay": "contracting",
              "fed_stance": {"stance": "hawkish", "implied_cuts_12m": -1.0, "guidance": "unknown"},
              "fed_path": {"implied_cuts_12m": -1.0}}
    cats = risk_radar_recovery._liquidity_catalysts(latest)
    assert all(c["key"] not in ("fed_netliq", "fed_policy") for c in cats)


# ---- assembled recovery read ------------------------------------------------------------------
def _receding_latest():
    vals = list(np.linspace(20, 92, 55)) + list(np.linspace(92, 70, 25))
    traj = risk_radar.trajectory(_subs(vals), risk_radar._calib())
    return {"risk_radar": {"trajectory": traj},
            "liquidity_overlay": "expanding",
            "fed_stance": {"stance": "dovish", "implied_cuts_12m": 3.0, "guidance": "easing"},
            "fed_path": {"implied_cuts_12m": 3.0}}


def test_assess_present_and_turn_confirmed():
    rec = risk_radar_recovery.assess(_receding_latest())
    assert rec and rec["present"] is True
    assert rec["receding"] is True
    assert rec["turn_confirmed"] is True   # risk derating + a fresh liquidity injection
    assert rec["headline_en"] and rec["sub_en"] and rec["do_en"] and rec["caveat_en"]
    assert 0 <= rec["strength"] <= 100
    assert rec["n_fresh"] >= 1


def test_assess_absent_when_rising():
    vals = list(np.linspace(20, 95, 80))
    latest = {"risk_radar": {"trajectory": risk_radar.trajectory(_subs(vals), risk_radar._calib())},
              "liquidity_overlay": "contracting", "fed_stance": {"stance": "hawkish"}}
    rec = risk_radar_recovery.assess(latest)
    assert rec == {"present": False}


def test_assess_none_without_trajectory():
    assert risk_radar_recovery.assess({"risk_radar": {}}) is None
    assert risk_radar_recovery.assess({}) is None


def test_assess_never_raises_on_garbage():
    # malformed inputs must degrade, never crash the build
    for bad in (None, {"risk_radar": None}, {"risk_radar": {"trajectory": {"phase": "receding"}}}):
        risk_radar_recovery.assess(bad)   # no exception


# ---- shared classifier (used by both US + intl radars) ----------------------------------------
def _win(vals):
    return pd.Series(vals, index=pd.bdate_range("2026-01-01", periods=len(vals)))


def test_shared_classifier_phases():
    receding = risk_radar._trajectory_from_series(_win([90, 88, 85, 80, 75, 70]), None, None, 68.0)
    assert receding["phase"] == "receding" and receding["velocity"] < 0
    rising = risk_radar._trajectory_from_series(_win([50, 58, 66, 74, 82, 90]), None, None, 68.0)
    assert rising["phase"] == "rising"
    peaking = risk_radar._trajectory_from_series(_win([90, 91, 90, 91, 90, 90]), None, None, 68.0)
    assert peaking["phase"] == "peaking"   # plateaued at the top (velocity ~0, still near peak)
    calm = risk_radar._trajectory_from_series(_win([10, 12, 14, 16, 18, 20]), None, None, 68.0)
    assert calm["phase"] == "calm"      # never reached the caution band -> nothing to recede from


# ---- international radar trajectory ------------------------------------------------------------
def test_intl_trajectory_receding():
    idx = pd.bdate_range("2025-01-01", periods=250)
    comp = pd.Series(np.concatenate([np.linspace(0.20, 0.95, 200),
                                     np.linspace(0.95, 0.70, 50)]), index=idx)   # 0-1 percentile
    B = pd.Series(np.linspace(100, 80, 250), index=idx)                          # declining index
    t = risk_radar_intl._trajectory(comp, B, risk_radar_intl._calib(risk_radar_intl.CN_PROFILE))
    assert t is not None
    assert t["phase"] == "receding"
    assert t["reached_risk"] is True
    assert t["odds_now"] is not None      # intl odds series built from the per-market prob surface


def test_intl_assess_uses_market_and_never_crashes():
    # an intl latest carries market='cn' on the radar snapshot and lacks Fed keys; assess must read
    # the Fed legs globally (via the US latest) and never crash on the intl shape.
    idx = pd.bdate_range("2025-01-01", periods=250)
    comp = pd.Series(np.concatenate([np.linspace(0.20, 0.95, 200),
                                     np.linspace(0.95, 0.70, 50)]), index=idx)
    B = pd.Series(np.linspace(100, 80, 250), index=idx)
    traj = risk_radar_intl._trajectory(comp, B, risk_radar_intl._calib(risk_radar_intl.CN_PROFILE))
    rec = risk_radar_recovery.assess({"risk_radar": {"market": "cn", "trajectory": traj}})
    assert rec and rec["present"] is True            # CN risk receding
    assert isinstance(rec["catalysts"], list)        # market-aware catalyst read, no crash


def test_intl_market_channel_is_not_applicable():
    # US-ONLY scoping (masterplan §5 / RRX): the market-internal chips read US stores, so on an
    # intl radar the market channel must be N/A (None), never a US-derived read or a hard False —
    # and no US chips may attach to the intl recovery payload.
    idx = pd.bdate_range("2025-01-01", periods=250)
    comp = pd.Series(np.concatenate([np.linspace(0.20, 0.95, 200),
                                     np.linspace(0.95, 0.70, 50)]), index=idx)
    B = pd.Series(np.linspace(100, 80, 250), index=idx)
    traj = risk_radar_intl._trajectory(comp, B, risk_radar_intl._calib(risk_radar_intl.CN_PROFILE))
    rec = risk_radar_recovery.assess({"risk_radar": {"market": "cn", "trajectory": traj}})
    assert rec and rec["present"] is True
    assert rec["market"] is None                     # no US chips on an intl card
    assert rec["channels"]["market"] is None         # N/A, not False
    assert rec["channels"]["veto"] is None
    assert rec["turn_confirmed_full"] is None        # conjunction not computed off-US
    assert isinstance(rec["turn_confirmed"], bool)   # legacy liquidity-only turn unchanged


def test_us_market_channel_attached():
    # The US path must attach the market dict (or None on store failure) and boolean channels.
    rec = risk_radar_recovery.assess(_receding_latest())
    assert rec and rec["present"] is True
    assert "market" in rec and "channels" in rec
    assert rec["channels"]["market"] in (True, False)
    assert rec["turn_confirmed_full"] in (True, False)


# ---- DISPLAY-ONLY invariant -------------------------------------------------------------------
def test_recovery_is_display_only_no_ceiling_or_amp():
    """The recovery read must never inject downward-pressure keys (ceiling/amp/amp_keys) — it
    illustrates the turn, it does not relax (or tighten) the radar's one-directional override."""
    rec = risk_radar_recovery.assess(_receding_latest())
    assert "ceiling" not in rec
    assert "amp" not in rec and "amp_keys" not in rec
