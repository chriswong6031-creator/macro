"""Basket-signal calibration (scripts.calibrate_baskets) + its engine wiring.

Two contracts are guarded here. (1) The HARNESS statistics the adversarial review pinned
down: delta_5d MUST be the single 5d relative read (matching engine.theme_scoring), the
event study collapses same-day sectors BEFORE the HAC t (no cross-sectional t-inflation),
and the firing gate is chosen OUT-OF-SAMPLE and only surfaced when its bootstrap lift CI
clears 1.0. (2) The WIRING: theme_scoring grades each label backtested-vs-descriptive and
theme_alerts down-grades an unvalidated continuation alert so it can't fire 'high' — both
falling back to the prior honest behaviour when the calibration JSON is absent. No network.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import theme_alerts as ta
from engine import theme_scoring as ts
from scripts import calibrate_baskets as cb


# ----------------------------------------------------------------- harness stats
def test_delta_5d_is_single_5d_rel_not_second_difference():
    """The confirmed faithfulness bug: theme_scoring passes perf['5d']['rel'] (a single
    5d relative return) as delta_5d; the harness must match, not a change-of-the-5d-read."""
    idx = pd.date_range("2024-01-01", periods=120, freq="B")
    lvl = pd.Series(np.linspace(1.0, 1.5, 120) + np.sin(np.arange(120) / 7) * 0.02, index=idx)
    bench = pd.Series(np.linspace(1.0, 1.2, 120), index=idx)
    f = cb._rs_features(lvl, bench)
    d, r5 = f["delta_5d"].dropna(), f["r5"].dropna()
    assert len(d) and (d == r5.reindex(d.index)).all()


def test_event_study_collapses_same_day_sectors_before_hac():
    """3 sectors firing the same label on each of 60 bars -> 180 pooled events but the HAC
    t must run on 60 DAILY means (else same-day correlation fakes significance)."""
    rng = np.random.default_rng(0)
    rows = []
    for i in range(60):
        for _ in range(3):
            rows.append((rng.normal(0, .01), rng.normal(0, .02),
                         -0.03 + rng.normal(0, .004), -0.05, i * cb.STEP))
    out = cb._event_study({"deteriorating": rows}, {"deteriorating": "risk"})
    r = out["deteriorating"]
    assert r["n"] == 180 and r["n_days"] == 60 and r["t_n"] == 60


def test_confidence_gate_oos_calibratable_when_score_separates():
    rng = np.random.default_rng(1)
    n = 4000
    p = rng.uniform(0, 1, n)
    idx = list(np.repeat(np.arange(n // 4), 4))                 # 4 correlated rows per bar
    y = (rng.uniform(0, 1, n) < (0.05 + 0.25 * p)).astype(float)  # higher p -> higher odds
    out = cb._calibrate_confidence(list(p), list(y), idx, "sep")
    assert out["verdict"] == "calibratable"
    assert out["gate"] is not None and out["gate"]["lift_ci"][0] > 1.0


def test_confidence_gate_rejected_on_noise():
    rng = np.random.default_rng(2)
    n = 4000
    p = rng.uniform(0, 1, n)
    idx = list(np.repeat(np.arange(n // 4), 4))
    y = (rng.uniform(0, 1, n) < 0.11).astype(float)            # outcome independent of p
    out = cb._calibrate_confidence(list(p), list(y), idx, "noise")
    assert out["verdict"] == "weak_separation" and out["gate"] is None
    assert out.get("gate_rejected") is not None                 # kept for the audit trail


# ----------------------------------------------------------------- engine wiring
_CAL = {"fading": {"verdict": "measurable_edge", "mean_pct": -3.7, "t_hac": -9.6, "n": 252},
        "deteriorating": {"verdict": "measurable_edge", "mean_pct": -3.6, "t_hac": -15.5, "n": 3959},
        "emerging": {"verdict": "not_measurable"}, "dominant": {"verdict": "not_measurable"}}


def test_signal_strength_grades_risk_backtested_entry_descriptive():
    risk = ts._signal_strength("deteriorating", _CAL)
    assert risk["grade"] == "backtested" and risk["kind"] == "risk" and risk["measured"] is True
    ent = ts._signal_strength("emerging", _CAL)
    assert ent["grade"] == "descriptive" and ent["measured"] is False
    # a risk label the proxy did NOT confirm is still risk-kind but graded 'unconfirmed'
    assert ts._signal_strength("fading", {"fading": {"verdict": "not_measurable"}})["grade"] == "unconfirmed"


def test_signal_strength_fallback_without_calibration():
    assert ts._signal_strength("deteriorating", {}) is None          # JSON absent -> no grade
    assert ts._signal_strength("neutral", _CAL) is None              # neutral is ungraded


def test_annotate_confidence_tags_and_gates_appearance():
    evs = [
        {"type": "theme_deteriorating", "severity": "high", "context": {"to": "deteriorating"}},
        {"type": "theme_emerging", "severity": "medium", "context": {"to": "emerging"}},
        {"type": "reco_change", "severity": "high", "context": {"to": "enter"}},
        {"type": "reco_change", "severity": "high", "context": {"to": "avoid"}},
        {"type": "leadership_rotation", "severity": "high", "context": {"new_leader": "x"}},
    ]
    out = ta._annotate_confidence(evs, _CAL)
    assert out[0]["confidence"] == "backtested" and out[0]["severity"] == "high"   # measured risk shouts
    assert out[1]["confidence"] == "descriptive"
    assert out[2]["confidence"] == "descriptive" and out[2]["severity"] == "medium"  # enter downgraded
    assert out[3]["confidence"] == "backtested" and out[3]["severity"] == "high"   # avoid = risk
    assert out[4]["confidence"] == "descriptive" and out[4]["severity"] == "medium"  # rotation downgraded


def test_annotate_confidence_noop_without_calibration():
    evs = [{"type": "reco_change", "severity": "high", "context": {"to": "enter"}}]
    out = ta._annotate_confidence([dict(e) for e in evs], {})
    assert out[0]["severity"] == "high" and "confidence" not in out[0]


# ----------------------------------------------------------------- sizing (E1)
def test_dd_reduction_ci_sign_shallower_is_favorable():
    """Locks the sign fix: a shallower-drawdown strat must report a POSITIVE, favorable
    reduction (MaxDD is negative, so reduction = strat_dd - base_dd > 0 when shallower)."""
    idx = pd.date_range("2010-01-01", periods=900, freq="B")
    base = pd.Series(np.random.default_rng(0).normal(0.0003, 0.02, 900), index=idx)
    strat = base * 0.5                          # half the swings -> shallower drawdown
    ci = cb._dd_reduction_ci(strat, base, B=600)
    assert ci["dd_reduction_pp_ci"][0] > 0 and ci["favorable"] is True


def test_book_voltarget_derisk_only_at_cap1():
    """De-risk-only default (cap 1.0): the vol-target book gross must never exceed the
    equal-weight base book's gross."""
    idx = pd.date_range("2015-01-01", periods=900, freq="B")
    rng = np.random.default_rng(1)
    P = pd.DataFrame({"A": 100 * np.cumprod(1 + rng.normal(0, 0.02, 900)),
                      "B": 100 * np.cumprod(1 + rng.normal(0, 0.02, 900))}, index=idx)
    ew = pd.DataFrame(0.5, index=idx, columns=["A", "B"])
    vt = cb._book_voltarget(ew, P, vol_win=40, target_mult=0.85, cap=1.0)
    assert float(vt.abs().sum(axis=1).max()) <= 1.0 + 1e-9


def test_vol_overlay_display_only_offered_not_applied(monkeypatch):
    """The narrative_rotation overlay: display_only -> offered (applied False, de-risk only,
    full measured provenance); calibration absent -> None (honest fallback)."""
    from engine import narrative_rotation as nr
    idx = pd.date_range("2015-01-01", periods=900, freq="B")
    lvl = pd.Series(100 * np.cumprod(1 + np.random.default_rng(3).normal(0, 0.02, 900)), index=idx)
    cal = {"verdict": "display_only",
           "default": {"vol_win": 40, "target_mult": 0.85, "cap": 1.0, "floor": 0.0},
           "beats_brake": True, "dsr": 0.855, "n_trials": 36,
           "dd_reduction_ci": {"dd_reduction_pp_ci": [1.0, 7.5, 17.2]}}
    byid = {"t1": {"lvl": lvl, "name": "T1", "name_zh": "T1"}}
    monkeypatch.setattr(nr, "_sizing_calibration", lambda: cal)
    vo = nr._vol_overlay(["t1"], {"t1": 0.25}, byid)
    assert vo is not None and vo["applied"] is False
    assert vo["measured"]["verdict"] == "display_only"
    assert vo["gross_after"] <= vo["gross_before"]              # de-risk only, never levers up
    monkeypatch.setattr(nr, "_sizing_calibration", lambda: {})
    assert nr._vol_overlay(["t1"], {"t1": 0.25}, byid) is None  # absent -> None


# ----------------------------------------------------------- residual A/B (Build#4)
def test_residual_momentum_monthly_causal_and_columns():
    """Residual momentum uses a SHIFTED (causal) beta and emits a monthly per-name frame."""
    idx = pd.date_range("2018-01-01", periods=600, freq="B")
    rng = np.random.default_rng(5)
    P = pd.DataFrame({c: 100 * np.cumprod(1 + rng.normal(0, 0.02, 600)) for c in ["A", "B", "C"]}, index=idx)
    bench = pd.Series(100 * np.cumprod(1 + rng.normal(0, 0.015, 600)), index=idx)
    rm = cb._residual_momentum_monthly(P, bench, beta_win=126, shrink=0.5)
    assert set(rm.columns) == {"A", "B", "C"}
    assert bool(rm.index.is_month_end.all())                 # monthly index
    assert rm.iloc[0].isna().all()                           # warm-up -> NaN, no look-ahead


def test_rotation_book_honors_momentum_override():
    """The Build#4 A/B reuses _rotation_book with a residual-momentum override; the override
    must drive selection (here it forces B) while the price trend-gate still applies."""
    idx = pd.date_range("2017-01-01", periods=700, freq="B")
    P = pd.DataFrame({"A": np.linspace(100, 220, 700), "B": np.linspace(100, 160, 700)}, index=idx)
    M = P.resample("ME").last()
    mom = pd.DataFrame(0.0, index=M.index, columns=["A", "B"]); mom["B"] = 1.0  # prefer B
    w = cb._rotation_book(P, top_n=1, mom_monthly=mom)
    assert (w["B"] > 0).any() and float(w["A"].sum()) == 0.0
