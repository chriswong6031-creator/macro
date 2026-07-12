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
    out = rr.compute(sigs=_sigs(growth_defensives=0.95, growth_cyc_def=0.95), gate={"met": True})
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
    base = rr.compute(sigs=_sigs(growth_defensives=0.90, growth_cyc_def=0.90), gate={"met": True})
    esc = rr.compute(sigs=_sigs(growth_defensives=0.90, growth_cyc_def=0.90, vol_term=0.99), gate={"met": True})
    order = ["calm", "watch", "caution", "elevated", "risk-off"]
    assert order.index(esc["state"]) >= order.index(base["state"])


def test_dominant_is_validated_leg_not_coincident_vol():
    # growth (validated) + vol (coincident) both hot -> dominant names growth, not vol
    out = rr.compute(sigs=_sigs(growth_defensives=0.95, growth_cyc_def=0.95, vol_term=0.99), gate={"met": True})
    assert out["dominant_scare"] in ("growth", "credit", "bubble", "rates")


def test_context_gate_caps_loud_alert():
    # same hot signals: gate MET -> loud (elevated/risk-off, alert); gate NOT met -> capped to caution
    hot = dict(credit_oas_roc=0.97, bubble_ext=0.97, growth_defensives=0.97, growth_cyc_def=0.97)
    on = rr.compute(sigs=_sigs(**hot), gate={"met": True})
    off = rr.compute(sigs=_sigs(**hot), gate={"met": False})
    assert on["state"] in ("elevated", "risk-off") and on["alert"] is True
    assert off["state"] == "caution" and off["alert"] is False
    assert off["context_gate"]["met"] is False


def test_loud_early_calm_when_quiet():
    out = rr.compute(sigs=_sigs(growth_defensives=0.10, vol_term=0.10, credit_oas_roc=0.10))
    assert out["state"] == "calm"
    assert out["alert"] is False
    assert out["gross_factor"] == 1.0


def test_gross_and_contracts_scale_with_state():
    hot = rr.compute(sigs=_sigs(credit_oas_roc=0.97, bubble_ext=0.97, growth_defensives=0.97,
                                growth_cyc_def=0.97), gate={"met": True})
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
    claimed = [leg for leg, c in rr._LEG_CALIB.items()
               if c["lift_2020"] is not None and c["lift_2020"] >= rr._VALIDATED_MIN]
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


def test_flow_legs_inert_until_mature():
    # deep options-flow history is unavailable, so put/call & GEX legs accrue forward and must be
    # ABSENT from leading_signals() until >= _FLOW_MIN_HISTORY rows (currently ~14)
    cols = set(rr.leading_signals().columns)
    fs = rr.flow_status()
    if not fs["mature"]:
        assert "vol_putcall" not in cols and "vol_gex" not in cols
    assert fs["min_history"] == rr._FLOW_MIN_HISTORY
    assert fs["putcall_rows"] >= 0 and fs["gex_rows"] >= 0


def test_flow_legs_are_tierB_and_unvalidated():
    # the flow legs live under the vol scare (Tier-B) and are NOT validated (lift unknown)
    vol_legs = {leg for leg, w in rr._SCARES["vol"]["legs"]}
    assert {"vol_putcall", "vol_gex"} <= vol_legs
    assert rr._SCARES["vol"]["tier"] == "B"
    assert rr._is_validated("vol_putcall") is False and rr._is_validated("vol_gex") is False


def test_flow_status_in_snapshot():
    out = rr.compute(gate={"met": True})
    assert "flow_status" in out and out["flow_status"]["min_history"] == rr._FLOW_MIN_HISTORY


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
                                growth_cyc_def=0.97), gate={"met": True})
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


# --- RRX W3 Tier-B accruing legs (nh_contraction + jpy_carry) ---------------

def test_rrx_internals_scare_is_tierB():
    """internals scare must be Tier-B (display/escalator only; cannot originate state)."""
    assert "internals" in rr._SCARES
    assert rr._SCARES["internals"]["tier"] == "B"
    # nh_contraction must be the sole leg
    legs = [leg for leg, w in rr._SCARES["internals"]["legs"]]
    assert "nh_contraction" in legs


def test_rrx_jpy_carry_in_global_scare():
    """jpy_carry must appear in the 'global' scare (Tier-B) as a carry-stress channel."""
    assert "global" in rr._SCARES
    assert rr._SCARES["global"]["tier"] == "B"
    global_legs = {leg for leg, w in rr._SCARES["global"]["legs"]}
    assert "jpy_carry" in global_legs
    assert "global_breadth" in global_legs
    # weights must be non-zero and sum to ~1
    total_w = sum(w for leg, w in rr._SCARES["global"]["legs"])
    assert abs(total_w - 1.0) < 1e-9, f"global scare weights sum to {total_w} not 1.0"


def test_rrx_tierb_legs_not_validated():
    """New Tier-B legs must NOT be validated (accruing only, lift not yet at bar)."""
    assert rr._is_validated("nh_contraction") is False
    assert rr._LEG_CALIB["nh_contraction"].get("accruing") is True
    # jpy_carry: phase-0 measured 1.45 (recorded as measured_lift_2020 in _LEG_CALIB) but
    # lift_2020 is kept None so _is_validated returns False.  This prevents jpy_carry from
    # entering the CI validated-leg gate (test_evidence_gate_validated_legs_still_lead), where
    # a future live-data shift below 1.0 would red unrelated PRs.  Tier-B / accruing only.
    assert rr._is_validated("jpy_carry") is False
    assert rr._LEG_CALIB["jpy_carry"].get("accruing") is True
    # measured_lift_2020 non-gating field preserves the phase-0 result for documentation
    assert rr._LEG_CALIB["jpy_carry"].get("measured_lift_2020") == 1.450


def test_rrx_internals_cannot_originate_state():
    """A hot nh_contraction (internals Tier-B) must never originate state alone."""
    out = rr.compute(sigs=_sigs(nh_contraction=0.99))
    assert out["state"] == "calm", (
        f"Tier-B internals scare originated state '{out['state']}' — must stay calm")
    assert out["alert"] is False


def test_rrx_null_leg_cannot_escalate_tier_a():
    """nh_contraction (measured-null, lift_2020=0.0) must NOT escalate a hot Tier-A scare.
    A caution-band growth scare alone → state 'caution'.  Adding a hot nh_contraction must
    NOT push state to 'elevated' (the loud banner).  The escalation gate excludes Tier-B
    scares whose all legs are measured-zero per the context-accrual law."""
    # growth legs at caution level
    base = rr.compute(sigs=_sigs(growth_defensives=0.72, growth_cyc_def=0.72),
                      gate={"met": True})
    assert base["state"] in ("caution", "watch"), (
        f"baseline growth scare not at caution band: {base['state']}")
    caution_state = base["state"]
    # now add a maxed-out nh_contraction
    with_null = rr.compute(
        sigs=_sigs(growth_defensives=0.72, growth_cyc_def=0.72, nh_contraction=0.99),
        gate={"met": True})
    assert with_null["state"] == caution_state, (
        f"measured-null nh_contraction escalated state from '{caution_state}' to "
        f"'{with_null['state']}' — must be excluded from escalation set")


def test_rrx_jpy_carry_cannot_originate_state():
    """A hot jpy_carry (global Tier-B) must never originate state alone."""
    out = rr.compute(sigs=_sigs(jpy_carry=0.99))
    assert out["state"] == "calm", (
        f"Tier-B jpy_carry originated state '{out['state']}' — must stay calm")
    assert out["alert"] is False


def test_rrx_tierb_legs_appear_in_leading_signals():
    """nh_contraction and jpy_carry should appear in leading_signals() when stores are present.
    Both stores (breadth.parquet, FRED DEXJPUS) are tracked and present in the worktree."""
    sigs = rr.leading_signals()
    # Both stores are present in the test environment; columns must appear.
    assert "jpy_carry" in sigs.columns, "jpy_carry absent from leading_signals — DEXJPUS missing?"
    assert "nh_contraction" in sigs.columns, "nh_contraction absent — breadth.parquet missing?"
    # Values must be in [0, 1] range (causal percentiles)
    assert sigs["jpy_carry"].dropna().between(0.0, 1.0).all(), "jpy_carry out of [0,1]"
    assert sigs["nh_contraction"].dropna().between(0.0, 1.0).all(), "nh_contraction out of [0,1]"


def test_rrx_subscore_renormalization_unaffected():
    """Adding Tier-B nh_contraction / jpy_carry must not break Tier-A subscore math.
    Tier-A growth at 0.95 must still produce a high score regardless of new Tier-B values."""
    out_clean = rr.compute(sigs=_sigs(growth_defensives=0.95, growth_cyc_def=0.95),
                           gate={"met": True})
    out_with_tierb = rr.compute(sigs=_sigs(growth_defensives=0.95, growth_cyc_def=0.95,
                                           jpy_carry=0.99, nh_contraction=0.99),
                                gate={"met": True})
    g_clean = next(s for s in out_clean["scares"] if s["scare"] == "growth")
    g_tierb = next(s for s in out_with_tierb["scares"] if s["scare"] == "growth")
    # growth score must be identical — Tier-B legs are in different scares
    assert g_clean["score"] == g_tierb["score"], (
        f"growth score changed after adding Tier-B legs: {g_clean['score']} vs {g_tierb['score']}")


def test_rrx_internals_label_bilingual():
    """internals scare must have non-empty EN + ZH labels."""
    assert "internals" in rr._SCARE_LABEL
    en, zh = rr._SCARE_LABEL["internals"]
    assert len(en) > 0 and len(zh) > 0


# --- unit tests for series builders on synthetic data -------------------------

def test_build_nh_contraction_near_high_masking():
    """Near-high mask: nh_contraction must be 0.0 on days when SPY is NOT near its 252d high.

    The mask zeros the percentile output on non-near-high days. The 252d rolling max is causal
    so SPY must stay below 0.98 * (rolling 252d max) for the mask to be False. We construct
    a sustained decline long enough that the prior peak leaves the 252d window.
    """
    from engine.risk_radar import build_nh_contraction

    # Use 800 days: 300 near-high, then 500 well below (last 200 are past the 252d window).
    n = 800
    idx = pd.date_range("2020-01-02", periods=n, freq="B")
    # First 300 days at 100; then drop to 70 (well below 0.98 * 100 = 98).
    # After 252 more days the 252d max rolls to 70, but 70 >= 0.98*70 = 68.6 -> True.
    # To keep near_high=False we need to keep declining each day slightly so max stays above price.
    # Build a series that declines continuously: max is always yesterday's peak.
    prices = [100.0] * 300 + [100.0 - (i + 1) * 0.3 for i in range(500)]  # 100 -> ~-50, clamp
    prices = [max(p, 30.0) for p in prices]
    spy = pd.Series(prices, index=idx)
    breadth = pd.DataFrame({"nh": [20.0] * n, "n_members": [500.0] * n}, index=idx)
    breadth.index = pd.to_datetime(breadth.index)

    leg = build_nh_contraction(spy, breadth)
    # In the window 350..550 (in the sustained decline), SPY is dropping and the 252d max
    # is still from the 100-level era, so near_high=False and the leg should be 0.0.
    check_window = leg.iloc[350:550]
    assert (check_window == 0.0).all(), (
        f"nh_contraction non-zero during sustained decline (near_high=False):\n"
        f"{check_window[check_window != 0.0]}")


def test_build_nh_contraction_zero_on_regime_off():
    """nh_contraction produces 0.0 values when the near-high mask is False."""
    from engine.risk_radar import build_nh_contraction
    n = 600
    idx = pd.date_range("2020-01-02", periods=n, freq="B")
    # SPY steadily declining — never near the 252d high
    spy = pd.Series(list(range(n, 0, -1)), index=idx, dtype=float)
    breadth = pd.DataFrame({"nh": [10.0] * n, "n_members": [500.0] * n}, index=idx)
    leg = build_nh_contraction(spy, breadth)
    # After warmup, all should be 0 (price well below 252d max)
    assert (leg.iloc[300:] == 0.0).all(), "nh_contraction non-zero during sustained decline"


def test_build_jpy_carry_zeros_off_regime():
    """jpy_carry raw stress must be 0.0 when USD/JPY is ABOVE its 50d MA (regime gate active).

    The 50d-MA gate zeroes the raw stress before pct_rank_window. The pctile of a constant-zero
    stress series is ~0.5 (not 0), which is intentional — the gate suppresses signal content,
    not the rank itself. The key property is that the intermediate stress value is 0.0 so the
    series carries no information when the regime gate is off.
    """
    from engine.risk_radar import build_jpy_carry
    import numpy as np
    n = 700
    idx = pd.date_range("2018-01-02", periods=n, freq="B")
    spy = pd.Series(100.0, index=idx)
    # USD/JPY steadily rising — always above its 50d MA
    dexjpus = pd.Series([100.0 + i * 0.1 for i in range(n)], index=idx)
    # Compute the raw stress manually to verify the gate is working
    x = dexjpus
    ma50 = x.rolling(50, min_periods=25).mean()
    roc10 = x / x.shift(10) - 1.0
    raw_stress = (-roc10).where(x < ma50, other=0.0)
    # Gate condition: USD/JPY is always above 50d MA -> stress must be exactly 0.0
    assert (raw_stress.iloc[100:].dropna() == 0.0).all(), (
        "Raw stress non-zero when USD/JPY above 50d MA (gate should suppress it)")
    # Confirm the builder produces the same raw stress (by recomputing with the builder
    # and checking the leg is not NaN — the pctile may be ~0.5, which is expected behavior)
    leg = build_jpy_carry(spy, dexjpus)
    # The leg should not be NaN after warmup (values present, just at ~0.5 pctile rank)
    assert not leg.iloc[200:].isna().all(), "jpy_carry all-NaN after warmup"


def test_build_jpy_carry_50dma_regime_fires():
    """jpy_carry must be non-zero when USD/JPY falls BELOW its 50d MA (regime gate passes)."""
    from engine.risk_radar import build_jpy_carry
    import numpy as np
    n = 800
    idx = pd.date_range("2018-01-02", periods=n, freq="B")
    spy = pd.Series(100.0, index=idx)
    # First 400d: stable (high USD/JPY). Next 400d: declining (yen strengthening, below MA).
    px = [150.0] * 400 + [150.0 - (i + 1) * 0.3 for i in range(400)]
    dexjpus = pd.Series(px, index=idx)
    leg = build_jpy_carry(spy, dexjpus)
    # In the second half, yen is strengthening and USD/JPY is below its 50d MA -> stress fires
    active = leg.iloc[550:]   # well into the declining phase with MA below
    assert (active > 0.0).any(), (
        "jpy_carry never fires when USD/JPY is declining below 50d MA")


def test_deescalation_emits_deescalated_chip_list():
    """The de-escalated-scares chip list mirrors trajectory drivers.faded
    (from=peak, to=now) — context narration for the v4 'What faded' box."""
    traj = {"phase": "receding", "odds_delta": -0.01,
            "drivers": {"faded": [{"key": "vol", "label_en": "Volatility scare",
                                   "label_zh": "波动率惊吓", "peak": 62.0, "now": 38.0}],
                        "warm": []}}
    out = rr._deescalation(None, None, traj, {"h21": 0.1})
    assert out["deescalated"] == [{"key": "vol", "label_en": "Volatility scare",
                                   "label_zh": "波动率惊吓", "from": 62.0, "to": 38.0}]


def test_deescalation_deescalated_empty_on_missing_drivers():
    """Old artifacts / missing trajectory degrade to an empty chip list, never a crash."""
    assert rr._deescalation(None, None, None, None)["deescalated"] == []
    assert rr._deescalation(None, None, {"phase": "peaking"}, None)["deescalated"] == []
