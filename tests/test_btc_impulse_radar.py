"""BTC forward impulse-pressure radar (engine/btc_impulse_radar.py).

Pure-compute + store-stubbed. No network. Covers the contract that matters:
  - legs SUM to the headline; ladder thresholds;
  - the anti-"permanently-on" guarantees (context caps at coiled; decay → quiet);
  - leak-free causal features (a future spike never changes a past z);
  - escalation on a SYNTHETIC flush the radar was not built around (generalises
    beyond June-24); the honest June-24 read (coiled context, no act trigger);
  - NaN-safe degrade.

Run: .venv/bin/python -m tests.test_btc_impulse_radar
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from engine import btc_impulse_radar as R  # noqa: E402


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _base_sig(n=400, start_price=60000.0, drift=0.0):
    """A neutral synthetic signals frame — no leg fires unless a test perturbs it."""
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    close = pd.Series(start_price * (1 + drift) ** np.arange(n), index=idx)
    return pd.DataFrame({
        "close": close,
        "coinbase_premium": pd.Series(0.0, index=idx),
        "oi_mcap_ratio": pd.Series(0.015, index=idx),
        "vol_of_vol": pd.Series(5.0, index=idx),
        "funding_annual_pct": pd.Series(5.0, index=idx),
        "funding_z": pd.Series(0.0, index=idx),
        "oi_change": pd.Series(0.0, index=idx),
    }, index=idx)


def _dvol(idx, ranges):
    """Build a Deribit-dvol OHLC frame whose (high-low)/close == the given ranges."""
    close = pd.Series(50.0, index=idx)
    low = close * (1 - np.asarray(ranges) / 2)
    high = close * (1 + np.asarray(ranges) / 2)
    return pd.DataFrame({"dvol_open": close, "dvol_high": high,
                         "dvol_low": low, "dvol_close": close}, index=idx)


def _sopr(idx, vals):
    return pd.DataFrame({"sopr": pd.Series(np.asarray(vals, dtype=float), index=idx)}, index=idx)


# calm (noisy) baselines — a CONSTANT series has zero rolling-std → NaN z-scores,
# so neutral fixtures need a little deterministic wobble for the legs to be live.
def _calm_ranges(n):
    return 0.04 + 0.004 * np.sin(np.arange(n) * 0.7)


def _neutral_sopr(n):
    return 1.0 + 0.004 * np.sin(np.arange(n) * 0.7)


class _Store:
    """Stub for R.store.read — serves injected frames, else empty."""
    def __init__(self, frames):  # frames: {(ns,name): df}
        self.frames = frames

    def read(self, ns, name):
        return self.frames.get((ns, name))


def _run(sig, dvol=None, sopr=None, hourly=None):
    frames = {("vector", "signals"): sig}
    if dvol is not None:
        frames[("deribit", "dvol")] = dvol
    if sopr is not None:
        frames[("bgeo", "sopr")] = sopr
    if hourly is not None:
        frames[("coinbase", "btc_hourly")] = hourly
    orig = R.store
    R.store = _Store(frames)
    # Isolate the radar's leg-summation/ladder logic from the LIVE falsifier
    # verdict: these tests assert compute behaviour, not gate policy (that is
    # covered in test_btc_impulse_falsifier). Force an all-'leading' gate so a
    # real-world demotion (act points zeroed on disk) can't spuriously fail them.
    import engine.btc_impulse_radar_backtest as bt
    orig_gate = bt.load_gate
    bt.load_gate = lambda: {"legs": {"d2": {"status": "leading"},
                                     "d3": {"status": "leading"},
                                     "u1": {"status": "leading"}}}
    try:
        return R.compute(sig)
    finally:
        R.store = orig
        bt.load_gate = orig_gate


# --------------------------------------------------------------------------- #
# pure-helper invariants
# --------------------------------------------------------------------------- #
def test_legs_sum_to_headline():
    sig = _base_sig()
    idx = sig.index
    # a fresh DVOL jolt on the last bar → D2 ~40
    ranges = _calm_ranges(len(idx)); ranges[-1] = 0.30
    out = _run(sig, dvol=_dvol(idx, ranges), sopr=_sopr(idx, _neutral_sopr(len(idx))))
    assert out["ok"]
    d = out["down"]
    assert d["score"] == min(round(sum(l["points"] for l in d["legs"])), 100)
    assert out["up"]["score"] == min(round(sum(l["points"] for l in out["up"]["legs"])), 100)


def test_ladder_context_only_caps_at_coiled():
    """Context legs (cbp + fuel + OI-only cascade) can stack past 35 points but
    MUST stay `coiled` — only an act-tier cross may reach warning/trigger. This
    is the exact failure the user hit (a permanent bearish/crowded backdrop
    reading as an acute warning)."""
    sig = _base_sig()
    idx = sig.index
    # light up every CONTEXT leg, no act leg:
    sig.loc[idx[-3:], "coinbase_premium"] = -50.0            # cbp_z << -1  → D1
    sig["coinbase_premium"] = sig["coinbase_premium"].astype(float)
    sig.loc[idx[-260:], "oi_mcap_ratio"] = np.linspace(0.015, 0.05, 260)  # OI pctile high → fuel + oi-only cascade
    sig.loc[idx[-260:], "vol_of_vol"] = np.linspace(5.0, 9.0, 260)        # vov rising + high pctile → fuel
    out = _run(sig, dvol=_dvol(idx, _calm_ranges(len(idx))),             # calm dvol, no D2
               sopr=_sopr(idx, _neutral_sopr(len(idx))))                   # neutral sopr, no D3/U1
    d = out["down"]
    assert d["act_live"] is False
    assert d["score"] >= 35                       # context genuinely stacked past the warning line
    assert d["ladder"] == "coiled"                # ...yet capped, because no act cross


def test_act_cross_reaches_warning_and_two_legs_trigger():
    """A SYNTHETIC flush the radar was not built around must ESCALATE — proves
    generalisation beyond June-24."""
    sig = _base_sig(drift=0.004)                  # gently rising → p5>0 for D3
    idx = sig.index
    ranges = _calm_ranges(len(idx)); ranges[-1] = 0.30            # D2 jolt (z60 ≥ 2)
    out1 = _run(sig, dvol=_dvol(idx, ranges), sopr=_sopr(idx, _neutral_sopr(len(idx))))
    d1 = out1["down"]
    assert d1["act_live"] is True and d1["ladder"] == "warning"     # one act leg → warning
    assert next(l for l in d1["legs"] if l["key"] == "d2_dvol")["fired_today"]

    # add a SOPR profit-take spike on the last bar → D3 also fires → trigger
    sopr_vals = _neutral_sopr(len(idx)); sopr_vals[-1] = 1.20
    out2 = _run(sig, dvol=_dvol(idx, ranges), sopr=_sopr(idx, sopr_vals))
    d2 = out2["down"]
    assert d2["score"] >= 60 and d2["ladder"] == "trigger"


def test_decay_back_to_quiet():
    """After a lone act cross, with nothing fresh since, the gauge must bleed
    back toward quiet (geometric decay) — no permanent floor."""
    sig = _base_sig()
    idx = sig.index
    ranges = _calm_ranges(len(idx))
    ranges[-7] = 0.30                              # jolt 6 days ago, calm since
    out = _run(sig, dvol=_dvol(idx, ranges), sopr=_sopr(idx, _neutral_sopr(len(idx))))
    d2 = next(l for l in out["down"]["legs"] if l["key"] == "d2_dvol")
    assert d2["fired_today"] is False
    assert d2["points"] < 2.0                      # 40 * 0.5**6 ≈ 0.6 → floored toward 0
    assert out["down"]["ladder"] in ("quiet", "coiled")


def test_up_capitulation_leg_fires_on_washout():
    """U1: SOPR z<-1.5 AND already down ≥5%/5d → up act leg fires (reactive
    bounce caller)."""
    sig = _base_sig()
    idx = sig.index
    sig.loc[idx[-6:], "close"] = sig["close"].iloc[-7] * np.array([0.99, 0.97, 0.95, 0.93, 0.91, 0.89])
    sopr_vals = _neutral_sopr(len(idx)); sopr_vals[-10:] = 0.93     # capitulation z << -1.5
    out = _run(sig, dvol=_dvol(idx, _calm_ranges(len(idx))), sopr=_sopr(idx, sopr_vals))
    u = out["up"]
    assert u["act_live"] is True
    assert next(l for l in u["legs"] if l["key"] == "u1_sopr")["points"] > 0


def test_causal_z_is_leak_free():
    """A spike in the FUTURE must not change a past z-score."""
    s = pd.Series(np.r_[np.zeros(100), 0.0, np.zeros(50)], index=pd.date_range("2024-01-01", periods=151))
    z_a = R._causal_z(s, 30)
    s2 = s.copy(); s2.iloc[140] = 9999.0           # mutate a far-future value
    z_b = R._causal_z(s2, 30)
    assert np.isclose(z_a.iloc[110], z_b.iloc[110], equal_nan=True)   # earlier z unchanged


def test_deepening_bonus_suppressed_when_already_falling():
    """The cbp deepening bonus must NOT fire when the move is already underway
    (the June-24 case) — D1 stays at its base 15, not 23."""
    sig = _base_sig()
    idx = sig.index
    # price already falling into the cbp cross (trailing-3d << -2%)
    sig.loc[idx[-6:], "close"] = sig["close"].iloc[-7] * np.array([0.99, 0.97, 0.95, 0.93, 0.91, 0.90])
    sig.loc[idx[-3:], "coinbase_premium"] = -50.0
    out = _run(sig, dvol=_dvol(idx, _calm_ranges(len(idx))), sopr=_sopr(idx, _neutral_sopr(len(idx))))
    d1 = next(l for l in out["down"]["legs"] if l["key"] == "d1_cbp")
    assert d1["points"] <= 15.0                    # no +8 deepening while already falling


def test_staleness_tracks_intraday_data_not_sentinel_heartbeat():
    """Staleness is driven by the freshness of the committed HOURLY data, not the
    flash sentinel's commit-on-change heartbeat (which lags by design and would
    cry wolf). Fresh hourly -> not stale; >1d-old hourly -> stale."""
    sig = _base_sig()
    last = sig.index[-1]
    fresh = pd.DataFrame({"close": [60000.0]}, index=pd.DatetimeIndex([last]))
    assert _run(sig, hourly=fresh)["staleness"]["stale"] is False
    old = pd.DataFrame({"close": [60000.0]}, index=pd.DatetimeIndex([last - pd.Timedelta(days=10)]))
    out = _run(sig, hourly=old)
    assert out["staleness"]["stale"] is True
    assert out["staleness"]["intraday_asof"] is not None


def test_nan_safe_empty():
    assert R.compute(pd.DataFrame())["ok"] is False


def test_real_data_act_gating_invariant():
    """Integration on the committed stores. The live SNAPSHOT moves with the
    market (pre-cascade it was coiled/no-act; post-cascade an act leg fires and
    it escalates) — so we assert the INVARIANT, not a frozen state: warning/
    trigger REQUIRE a live act leg, and without one the ladder cannot exceed
    coiled. This is the anti-permanently-on guarantee, on real data."""
    out = R.compute()                              # real signals + deribit + bgeo stores
    if not out["ok"]:
        return                                     # stores absent in this env → skip
    for g in (out["down"], out["up"]):
        assert g["ladder"] in ("quiet", "coiled", "warning", "trigger")
        if g["ladder"] in ("warning", "trigger"):
            assert g["act_live"] is True           # escalation only from an act-tier cross
        if not g["act_live"]:
            assert g["ladder"] in ("quiet", "coiled")   # context alone caps at coiled
        assert g["score"] == min(round(sum(l["points"] for l in g["legs"])), 100)
    assert out["staleness"]["daily_asof"] is not None


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed")
