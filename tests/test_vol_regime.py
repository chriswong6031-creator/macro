"""engine/vol_regime.py — leg orientation, composite coherence, the firewall gate,
and the no-look-ahead guarantee the validated regime rests on."""
import numpy as np
import pandas as pd
import pytest

from engine import vol_regime


def _series(n=700, seed=0):
    """Synthetic but realistic-ish daily vol series (business days)."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2022-01-03", periods=n)
    vix = pd.Series(16 + np.cumsum(rng.normal(0, 0.4, n)), index=idx).clip(9, 80)
    vix3m = (vix + rng.normal(2.0, 0.5, n)).clip(10, 80)          # usually above VIX (contango)
    vix9d = (vix + rng.normal(-0.5, 0.5, n)).clip(8, 90)
    move = pd.Series(90 + np.cumsum(rng.normal(0, 1.0, n)), index=idx).clip(50, 200)
    skew = pd.Series(125 + np.cumsum(rng.normal(0, 0.3, n)), index=idx).clip(105, 160)
    spy = pd.Series(400 * np.cumprod(1 + rng.normal(0.0003, 0.01, n)), index=idx)
    return dict(vix=vix, vix3m=vix3m, vix9d=vix9d, move=move, skew=skew, spy=spy)


def _frame(d=None):
    d = d or _series()
    return vol_regime.build_frame(d["vix"], d["vix3m"], d["vix9d"], d["move"],
                                  d["skew"], d["spy"])


def test_frame_builds_and_has_core_columns():
    fr = _frame()
    assert not fr.empty
    for c in ("ts_slope", "leg_ts_slope", "leg_move", "leg_vrp", "risk_score",
              "vol_target_scalar", "vrp", "move_pctile"):
        assert c in fr.columns
    rs = fr["risk_score"].dropna()
    assert rs.between(-1.0, 1.0).all()


def test_contango_leg_is_risk_on():
    """When VIX/VIX3M sits LOW vs its own history (deeper contango), the term-structure
    leg should read risk-ON (positive)."""
    d = _series()
    # force the last value into deep contango vs history
    d["vix3m"].iloc[-1] = d["vix"].iloc[-1] + 6.0
    fr = _frame(d)
    assert fr["leg_ts_slope"].dropna().iloc[-1] > 0


def test_high_move_is_risk_off():
    d = _series()
    d["move"].iloc[-1] = d["move"].iloc[:-1].max() * 1.5      # spike bond vol
    fr = _frame(d)
    assert fr["leg_move"].dropna().iloc[-1] < 0


def test_composite_needs_two_legs():
    """A row with only ONE scored leg present must NOT produce a composite (the
    cadence-mismatch guard)."""
    d = _series()
    fr = vol_regime.build_frame(d["vix"], d["vix3m"], None, None, None, None)
    # only ts_slope leg exists -> need=min(2,1)=1 so composite allowed with the single leg
    assert "risk_score" in fr.columns
    # but with 3 eligible legs, a row missing 2 of them is dropped
    d2 = _series()
    d2["vix3m"].iloc[-1] = np.nan
    d2["move"].iloc[-1] = np.nan
    fr2 = _frame(d2)
    assert pd.isna(fr2["risk_score"].iloc[-1])


def test_snapshot_reads_one_coherent_asof():
    """Append a partial final row (VIX only); the snapshot must read the last FULLY
    populated row, not mix legs across dates."""
    d = _series()
    extra = d["vix"].index[-1] + pd.Timedelta(days=1)
    d["vix"] = pd.concat([d["vix"], pd.Series([20.0], index=[extra])])
    fr = _frame(d)
    snap = vol_regime.snapshot(fr)
    assert snap["available"]
    # as-of is the last row where all scored legs exist (not the VIX-only tail)
    assert snap["asof"] == str(d["vix3m"].index[-1].date())


def test_gate_closed_means_no_scored():
    fr = _frame()
    closed = {"legs": {}, "composite": {"scored": False}}
    assert vol_regime.scored_score(fr, gate=closed) is None
    snap = vol_regime.snapshot(fr, gate=closed)
    assert snap["scored_active"] is False
    assert snap["scored_score"] is None


def test_gate_open_activates_scored():
    fr = _frame()
    openg = {"legs": {"ts_slope": {"scored": True, "sign": 1, "weight": 1.0},
                      "move": {"scored": True, "sign": 1, "weight": 1.0}},
             "composite": {"scored": True}}
    sc = vol_regime.scored_score(fr, gate=openg)
    assert sc is not None and -1.0 <= sc <= 1.0
    snap = vol_regime.snapshot(fr, gate=openg)
    assert snap["scored_active"] is True


def test_no_look_ahead():
    """A leg/composite value at a past date must not change when future data is added."""
    d = _series(n=700)
    fr_full = _frame(d)
    cut = 500
    d_trunc = {k: v.iloc[:cut] for k, v in d.items()}
    fr_trunc = _frame(d_trunc)
    asof = fr_trunc.index[-1]
    for col in ("leg_ts_slope", "leg_move", "leg_vrp", "risk_score"):
        a = fr_full.loc[asof, col]
        b = fr_trunc.loc[asof, col]
        if pd.notna(a) and pd.notna(b):
            assert a == pytest.approx(b, rel=1e-9, abs=1e-9), col


def test_regime_label_bands():
    cf = vol_regime.DEFAULTS
    assert vol_regime._regime_label(1.02, -0.1, 0, cf) == "backwardation-stress"
    assert vol_regime._regime_label(0.98, 0.0, 0, cf) == "warning"
    assert vol_regime._regime_label(0.85, 0.5, 0, cf) == "calm-contango"
    assert vol_regime._regime_label(0.95, 0.0, 0, cf) == "normalizing"


def test_empty_inputs_degrade():
    assert vol_regime.build_frame(None, None, None, None, None, None).empty
    assert vol_regime.snapshot(pd.DataFrame()) == {"available": False}


# --------------------------------------------------------------------------- VVIX leg
def _series_vv(n=700, seed=1):
    """Add a synthetic VVIX (vol-of-vol) that loosely tracks VIX."""
    d = _series(n, seed)
    rng = np.random.default_rng(seed + 9)
    d["vvix"] = (90 + 1.5 * (d["vix"] - 16)
                 + pd.Series(np.cumsum(rng.normal(0, 0.5, n)), index=d["vix"].index)).clip(50, 200)
    return d


def _frame_vv(d):
    return vol_regime.build_frame(d["vix"], d["vix3m"], d["vix9d"], d["move"],
                                  d["skew"], d["spy"], None, d["vvix"])


def test_vvix_leg_is_context_only():
    d = _series_vv()
    fr = _frame_vv(d)
    for c in ("leg_vvix", "vvix", "vvix_vix", "vvix_vix_pctile", "vvix_pctile"):
        assert c in fr.columns
    # vvix is a CONTEXT/candidate leg — NOT scored-eligible (must not enter the composite set)
    assert "vvix" in vol_regime.CONTEXT_LEGS and "vvix" not in vol_regime.SCORED_LEGS


def test_vvix_absent_degrades_gracefully():
    d = _series_vv()
    fr = vol_regime.build_frame(d["vix"], d["vix3m"], d["vix9d"], d["move"], d["skew"], d["spy"])
    assert "leg_vvix" not in fr.columns and "vvix" not in fr.columns


def test_vvix_does_not_perturb_validated_composite():
    """Adding the VVIX context leg must NOT move the gated 3-leg composite/risk_score."""
    d = _series_vv()
    base = vol_regime.build_frame(d["vix"], d["vix3m"], d["vix9d"], d["move"], d["skew"], d["spy"])
    withv = _frame_vv(d)
    a, b = base["risk_score"].dropna(), withv["risk_score"].dropna()
    common = a.index.intersection(b.index)
    assert len(common) > 100
    assert np.allclose(a.loc[common], b.loc[common], rtol=1e-12, atol=1e-12)


def test_vvix_ratio_orientation_is_risk_on():
    """A spiking VVIX/VIX ratio (fear priced into vol-of-vol) reads risk-ON (+) — the MEASURED
    sign (rich ratio precedes lower forward realized vol)."""
    d = _series_vv()
    d["vvix"].iloc[-1] = d["vvix"].iloc[:-1].max() * 1.6
    fr = _frame_vv(d)
    assert fr["leg_vvix"].dropna().iloc[-1] > 0


def test_vvix_state_bands():
    cf = vol_regime.DEFAULTS
    assert "peak-fear" in vol_regime._vvix_state(0.95, 0.50, cf)     # absolute extreme
    assert "fear-priced" in vol_regime._vvix_state(0.50, 0.85, cf)   # rich ratio
    assert "complacent" in vol_regime._vvix_state(0.50, 0.10, cf)    # cheap ratio
    assert vol_regime._vvix_state(0.50, 0.50, cf) == "normal"
    assert vol_regime._vvix_state(None, None, cf) is None


def test_snapshot_surfaces_vvix():
    snap = vol_regime.snapshot(_frame_vv(_series_vv()))
    assert snap["available"]
    assert snap["vvix"] is not None and snap["vvix_vix"] is not None and snap["vvix_state"]
    # surfaced honestly as display/context — not eligible, not scored
    assert snap["legs"]["vvix"]["eligible"] is False
    assert snap["legs"]["vvix"]["scored"] is False


def test_vvix_no_look_ahead():
    d = _series_vv(n=700)
    full = _frame_vv(d)
    cut = 500
    dt = {k: v.iloc[:cut] for k, v in d.items()}
    trunc = _frame_vv(dt)
    asof = trunc.index[-1]
    for col in ("leg_vvix", "vvix_vix", "vvix_vix_pctile"):
        a, b = full.loc[asof, col], trunc.loc[asof, col]
        if pd.notna(a) and pd.notna(b):
            assert a == pytest.approx(b, rel=1e-9, abs=1e-9), col
