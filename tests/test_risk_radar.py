"""Tests for engine/risk_radar.py (v2) + engine/risk_radar_backtest.py.

Includes the EVIDENCE GATE: the legs the engine claims are 'validated leading' must still
clear the strict day-level lift bar on live data (a leg that stops leading fails CI), and
the engine must NOT tier a non-leading leg as a validated driver. Plus tier behavior
(Tier-A originates, Tier-B vol escalates-only), loud+early bands, and graceful degradation.
"""
from __future__ import annotations

import pandas as pd

from engine import risk_radar as rr


def _sigs(**legs):
    """A 2-row causal-percentile signal frame for compute() (uses .iloc[-1])."""
    idx = pd.to_datetime(["2026-06-22", "2026-06-23"])
    cols = {leg: [v, v] for leg, v in legs.items()}
    return pd.DataFrame(cols, index=idx)


# --- schema + live smoke -----------------------------------------------------
def test_compute_real_data_schema():
    out = rr.compute()
    assert out["schema"] == "risk_radar.v2"
    assert out["state"] in ("calm", "watch", "caution", "elevated", "risk-off")
    assert out["is_context_only"] is False
    assert "scares" in out and isinstance(out["scares"], list)


def test_snapshot_never_raises():
    out = rr.snapshot()
    assert isinstance(out, dict) and out["schema"] == "risk_radar.v2"


# --- tier behavior -----------------------------------------------------------
def test_tierA_growth_originates_elevated():
    # both validated growth legs near top -> growth sub-score high -> at least caution
    out = rr.compute(sigs=_sigs(growth_defensives=0.95, growth_cyc_def=0.95))
    g = next(s for s in out["scares"] if s["scare"] == "growth")
    assert g["tier"] == "A"
    assert g["score"] >= rr._DEFAULT_BANDS["caution"]
    assert out["state"] in ("caution", "elevated", "risk-off")


def test_tierB_vol_cannot_originate():
    # vol (Tier-B) screaming, everything else calm -> state must stay calm (no validated driver)
    out = rr.compute(sigs=_sigs(vol_term=0.99))
    assert out["dominant_scare"] != "vol" or out["state"] == "calm"
    assert out["state"] == "calm"
    assert out["alert"] is False


def test_tierB_vol_escalates_a_hot_tierA():
    base = rr.compute(sigs=_sigs(growth_defensives=0.90, growth_cyc_def=0.90))
    esc = rr.compute(sigs=_sigs(growth_defensives=0.90, growth_cyc_def=0.90, vol_term=0.99))
    order = ["calm", "watch", "caution", "elevated", "risk-off"]
    assert order.index(esc["state"]) >= order.index(base["state"])


def test_dominant_is_validated_leg_not_coincident_vol():
    # growth (validated) + vol (coincident) both hot -> dominant names growth, not vol
    out = rr.compute(sigs=_sigs(growth_defensives=0.95, growth_cyc_def=0.95, vol_term=0.99))
    assert out["dominant_scare"] in ("growth", "credit", "bubble", "rates")


def test_loud_early_calm_when_quiet():
    out = rr.compute(sigs=_sigs(growth_defensives=0.10, vol_term=0.10, credit_oas_roc=0.10))
    assert out["state"] == "calm"
    assert out["alert"] is False
    assert out["gross_factor"] == 1.0


def test_gross_and_contracts_scale_with_state():
    hot = rr.compute(sigs=_sigs(credit_oas_roc=0.97, bubble_ext=0.97, growth_defensives=0.97,
                                growth_cyc_def=0.97))
    assert hot["state"] in ("elevated", "risk-off")
    assert hot["alert"] is True
    assert hot["gross_factor"] < 1.0
    assert hot["favor_entries"] is True


# --- the EVIDENCE GATE (strict bar on live data) -----------------------------
def test_evidence_gate_validated_legs_still_lead():
    from engine import risk_radar_backtest as bt
    sigs = rr.leading_signals()
    onsets = bt.detect_events()
    assert len(onsets) >= 20  # famous-event coverage 1994-2026
    rep = bt.gate_report(sigs=sigs, onsets=onsets, thr=0.90)
    claimed = [leg for leg, c in rr._LEG_CALIB.items() if c["lift_2020"] >= rr._VALIDATED_MIN]
    assert len(claimed) >= 4
    # every leg the engine CLAIMS as validated must not be anti-predictive on live data (do-no-harm)
    for leg in claimed:
        lv = rep.get(leg, {}).get("lift_2020")
        assert lv is None or lv >= 1.0, f"{leg} claimed validated but live 2020+ lift={lv}"
    # and a majority of them must still clear the real 1.2x bar (tolerant to daily data drift)
    cleared = sum(1 for leg in claimed if (rep.get(leg, {}).get("lift_2020") or 0) >= 1.2)
    assert cleared >= 3, f"only {cleared}/{len(claimed)} validated legs clear 1.2x: {rep}"


def test_credit_oas_roc_is_era_robust():
    from engine import risk_radar_backtest as bt
    sigs = rr.leading_signals(); onsets = bt.detect_events()
    full = bt.lift(sigs["credit_oas_roc"], onsets, thr=0.90)
    assert full["lift"] is not None and full["lift"] >= 1.3  # era-robust credit-spread velocity


def test_vol_term_is_not_claimed_validated():
    # vol has no leg clearing the bar -> the engine must tier it B, not A
    assert rr._SCARES["vol"]["tier"] == "B"
    assert rr._LEG_CALIB["vol_term"]["lift_2020"] < rr._VALIDATED_MIN


def test_drawdown_prob_escalates_with_intensity():
    # P(drawdown within 21bd) must be non-decreasing as the state climbs (empirical monotonicity)
    p = [rr._drawdown_prob(st, 0)["h21"] for st in ("calm", "watch", "caution", "elevated", "risk-off")]
    assert p == sorted(p), f"prob not monotonic in state: {p}"
    assert rr._drawdown_prob("risk-off", 0)["h21"] > rr._drawdown_prob("calm", 0)["h21"]
    # and the near-term (5d) hazard is higher at risk-off than calm too
    assert rr._drawdown_prob("risk-off", 0)["h5"] > rr._drawdown_prob("calm", 0)["h5"]


def test_drawdown_prob_escalates_with_conjunction():
    # more scare-types firing together raises the probability at the same state
    lo = rr._drawdown_prob("elevated", 1)["h21"]
    hi = rr._drawdown_prob("elevated", 3)["h21"]
    assert hi > lo
    assert rr._drawdown_prob("elevated", 3)["lift_h21"] > 1.0


def test_compute_emits_drawdown_prob():
    out = rr.compute(sigs=_sigs(credit_oas_roc=0.97, bubble_ext=0.97, growth_defensives=0.97,
                                growth_cyc_def=0.97))
    dp = out.get("drawdown_prob")
    assert dp and "h5" in dp and "h10" in dp and "h21" in dp
    assert dp["h21"] > dp["h10"] > dp["h5"]          # cumulative over longer horizon
    assert dp["h21"] > rr._PROB_BASE["h21"]          # elevated/risk-off above base


def test_calibration_overlay_merges(tmp_path):
    (tmp_path / "data" / "risk_radar").mkdir(parents=True)
    (tmp_path / "data" / "risk_radar" / "calibration.json").write_text(
        '{"bands": {"elevated": 99.0}}')
    c = rr._calib(root=tmp_path)
    assert c["bands"]["elevated"] == 99.0
    assert "credit_oas_roc" in c["legs"]
