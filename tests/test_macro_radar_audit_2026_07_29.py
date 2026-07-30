"""Regression tests for the 2026-07-29 adversarial audit of the macro.html Risk Radar.

One test (or small cluster) per audited defect.  Every fix here is a BUG / HONESTY fix — no
gate value, threshold, weight, band cut or calibration constant moves, and several tests assert
that invariance directly.

Index of what is pinned:
  1  market_state._flip_text ......... impossible flip claims (both directions unreachable)
  2  market_state ceiling vs blend .... score_source / capped / score_gap + disarmed amplifiers
  3  conditions + market_state ........ NFCI silent-neutral, drawdown composition, vintages
  4  risk_radar.build_nh_contraction .. structurally-inapplicable leg diluted the sub-score
  5  risk_radar.subscore_series ....... display_only leg set the displayed number
  6  risk_radar calibration honesty ... flat "~1.5-2x lift" claim vs a state measuring 0.90x
  7  risk_radar_audit ................. context-gate counterfactual was unfalsifiable
  9  the minor cluster ................ 9a copy, 9b rounding, 9c bounds, 9d PIT gate, 9h replica
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from engine import conditions, cycles
from engine import market_state as ms
from engine import risk_radar as rr
from engine import risk_radar_audit as rra
from engine import risk_radar_backtest as rrb


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _comp(key, score, weight, label_en, label_zh):
    return {"key": key, "score": score, "weight": weight,
            "label_en": label_en, "label_zh": label_zh}


def _six_legs(**over):
    """A blend shaped like the live 2026-07-29 board (weights sum to 1.0, raw 63)."""
    base = {"trend": 62, "risk": 42, "vol": 46, "breadth": 85, "liquidity": 69, "stress": 86}
    base.update(over)
    labels = {"trend": ("Trend & technicals", "趋势与技术"),
              "risk": ("Risk appetite", "风险偏好"),
              "vol": ("Volatility regime", "波动率环境"),
              "breadth": ("Breadth & participation", "广度与参与"),
              "liquidity": ("Liquidity & credit", "流动性与信用"),
              "stress": ("Downturn-risk guard", "下行风险护栏")}
    return [_comp(k, base[k], ms.WEIGHTS[k], *labels[k]) for k in base]


def _blend(comps):
    den = sum(c["weight"] for c in comps)
    return int(round(100 * sum(c["score"] / 100 * c["weight"] for c in comps) / den))


# ===========================================================================
# 1 — BLOCKER: the flip line claimed two arithmetically impossible outcomes
# ===========================================================================

def test_flip_line_is_reachable_in_both_directions_when_the_radar_ceiling_binds():
    """The 2026-07-29 board printed

        "→ Green if risk appetite firms up (now 42/100); → Red if it deteriorates further."

    while BOTH clauses were unreachable: risk-appetite -> 100 lifts the blend 63 -> 73 but the
    score stays min(73, ceiling 56) = 56 (Mixed), and risk-appetite -> 0 pulls the blend only to
    55, far above the 41 the Risk-off band needs.  The line must now name the constraint that
    actually binds, and every clause must be an achievable claim."""
    comps = _six_legs()
    raw = _blend(comps)
    assert raw == 63, raw
    radar = {"state": "caution", "top_score": 77, "ceiling": 56,
             "severe_gated": False, "amp_keys": []}
    overrides = [{"kind": "radar", "note_en": "Capped at Mixed by the Risk Radar above."}]
    en, zh = ms._flip_text(comps, "MIXED", raw_score=raw, radar=radar, overrides=overrides)

    # the exact impossible sentence is gone
    assert "risk appetite firms up" not in en, en
    assert "deteriorates further" not in en, en
    # UP clause names the binding ceiling, not a leg that cannot out-run it
    assert en.startswith("→ Green if "), en
    assert "Risk Radar leaves caution" in en and "77/100" in en, en
    # DOWN clause is an achievable route
    assert "→ Red if " in en, en
    assert zh.startswith("→ 若") and "「偏多」" in zh and "「避险」" in zh, zh
    assert "风险雷达退出警戒" in zh, zh


def test_flip_upside_names_legs_when_the_blend_is_what_binds():
    """With no cap in play the upside is purely a blend problem — name the leg(s) whose full
    move really does carry the score over the 60 cut, not merely the weakest one."""
    comps = _six_legs(trend=30, breadth=40, stress=40, liquidity=40)
    raw = _blend(comps)
    assert raw < 60, raw
    en, zh = ms._flip_text(comps, "MIXED", raw_score=raw, radar={"ceiling": None}, overrides=[])
    assert en.startswith("→ Green if "), en
    assert "Risk Radar" not in en, en
    assert "/100)" in en, en                  # it quotes the legs' live readings
    assert zh.startswith("→ 若") and "「偏多」" in zh, zh


def test_flip_claims_are_arithmetically_sufficient():
    """Whatever legs the line names, driving exactly those to the extreme must cross the band."""
    comps = _six_legs(trend=45, breadth=55, stress=55, liquidity=50)
    raw = _blend(comps)
    assert 41 < raw < 60, raw                 # a genuine Mixed blend, both cuts reachable
    for direction, target in ((1, 60), (-1, 41)):
        legs = ms._legs_to_cross(comps, raw, target, direction)
        assert legs, (direction, legs)
        moved = []
        for c in comps:
            c2 = dict(c)
            if any(c["key"] == p["key"] for p in legs):
                c2["score"] = 100 if direction > 0 else 0
            moved.append(c2)
        got = _blend(moved)
        if direction > 0:
            assert got >= target, (got, target, [p["key"] for p in legs])
        else:
            assert got <= target, (got, target, [p["key"] for p in legs])


def test_flip_legacy_signature_keeps_the_guarded_prefixes():
    """scripts/check_ms_board_coherence pins the flip prefixes per verdict, and calls the
    function with `comps` only.  Without weights/raw_score there is no arithmetic to check, so
    the legacy wording must survive verbatim rather than a claim being manufactured."""
    comps = [{"score": 10, "label_en": "Trend & technicals", "label_zh": "趋势"},
             {"score": 80, "label_en": "Breadth", "label_zh": "广度"}]
    assert ms._flip_text(comps, "RISK_ON")[0].startswith("→ Mixed if ")
    assert ms._flip_text(comps, "RISK_OFF")[0].startswith("→ Mixed when ")
    assert ms._flip_text(comps, "MIXED")[0].startswith("→ Green if ")


def test_flip_risk_off_upside_names_the_radar_when_it_is_the_floor():
    comps = _six_legs()
    radar = {"state": "risk-off", "top_score": 91, "ceiling": 26,
             "severe_gated": False, "amp_keys": []}
    en, zh = ms._flip_text(comps, "RISK_OFF", raw_score=_blend(comps), radar=radar,
                           overrides=[{"kind": "radar"}])
    assert en.startswith("→ Mixed when "), en
    assert "Risk Radar leaves risk-off" in en, en
    assert "「混合」" in zh, zh


def test_flip_names_a_hard_force_override_when_that_is_the_binding_cap():
    """A stress/dislocation force pins the score at 41 — no amount of leg improvement can lift
    the verdict while it holds, so THAT is the only honest upside claim."""
    comps = _six_legs()
    overrides = [{"kind": "stress", "note_en": "forced to Risk-off"}]
    en, _zh = ms._flip_text(comps, "RISK_OFF", raw_score=_blend(comps),
                            radar={"ceiling": None}, overrides=overrides)
    assert en.startswith("→ Mixed when "), en
    assert "drawdown / systemic-stress band" in en, en


# ===========================================================================
# 2 — ceiling vs blend provenance + structurally-disarmed amplifiers
# ===========================================================================

def test_score_source_distinguishes_the_ceiling_constant_from_the_blend():
    """On a radar-capped day the displayed number is the ceiling CONSTANT, not a measurement.
    raw_score was already in the payload but nothing said which one the dial showed."""
    latest = {"date": "2026-07-29", "conditions": {}, "liquidity_overlay": "expanding",
              "risk_radar": {"state": "caution", "top_score": 77, "drawdown_prob": {}}}
    overrides = []
    rd = ms._radar_override(latest, overrides)
    assert rd["ceiling"] is not None
    # the ceiling is fully decomposed so a surface can show what produced it
    assert rd["ceiling"] == max(rd["ceiling_floor"],
                                round(rd["ceiling_base"] - rd["ceiling_severe_bump"]
                                      - rd["ceiling_amp_pull"]))


def test_snapshot_publishes_score_provenance_keys():
    snap = _mixed_snapshot()
    assert snap["score_source"] in ("blend", "radar_ceiling", "verdict_cap", "hard_force")
    assert isinstance(snap["capped"], bool)
    assert "score_ceiling" in snap and "score_caps" in snap
    if snap["capped"]:
        assert snap["score_gap"] == snap["raw_score"] - snap["score"]
        assert snap["score"] <= snap["raw_score"]


def test_disarmed_amplifiers_are_named_not_silently_absent():
    """complacency needs a calm surface and breadth_div needs the index near its 1y high —
    both DISARM in a decline, which is why the amplified ceiling could RISE on a down day.
    A silent gauge must be reported as silent-by-construction, not read as reassuring."""
    latest = {
        "date": "2026-07-29",
        "conditions": {
            "complacency": {"calm": 0, "fragility": 1, "state": "neutral",
                            "spy_high_prox": 0.93},
            "drawdown_risk": {"band": "low"},
            "systemic_stress": {"state": "normal"},
        },
        "turning_point": {"present": False},
    }
    un = ms._amp_unavailable(latest)
    keys = [u["key"] for u in un]
    assert "complacency" in keys and "breadth_div" in keys, keys
    for u in un:
        assert u["note_en"] and u["note_zh"], u
        # the note must say WHY it cannot fire, not merely that it did not
        assert "cannot fire" in u["note_en"] or "no current read" in u["note_en"], u


def test_disarmed_amplifiers_empty_on_a_calm_near_high_tape():
    latest = {
        "date": "2026-07-29",
        "conditions": {
            "complacency": {"calm": 2, "fragility": 0, "state": "calm", "spy_high_prox": 0.995},
            "drawdown_risk": {"band": "low"},
            "systemic_stress": {"state": "normal"},
        },
        "turning_point": {"present": False},
    }
    assert [u["key"] for u in ms._amp_unavailable(latest)] == []


# ===========================================================================
# 3 — NFCI silent-neutral / composition / vintages
# ===========================================================================

def _liquidity_latest(fc_state):
    return {"liquidity_overlay": "expanding",
            "conditions": {"complacency": {"hy_oas_chg_21d_bp": 1.0,
                                           "hy_oas_chg_21d_bp_exact": 1.0,
                                           "credit_widen": True},
                           "financial_conditions": {"state": fc_state},
                           "systemic_stress": {"state": "normal"}}}


def test_missing_nfci_degrades_the_liquidity_leg_instead_of_imputing_neutral_silently():
    """The fc term is an additive OFFSET around 0.5, so a missing input contributes 0.0 —
    arithmetically the only unbiased choice.  What was wrong is that the leg then rendered at
    full confidence with the metric row simply vanished.  The number must not move; the
    shortfall must be named."""
    have = ms._comp_liquidity(_liquidity_latest("neutral"))
    gone = ms._comp_liquidity(_liquidity_latest(None))
    assert have["score"] == gone["score"], "the arithmetic must be unchanged"
    assert have["degraded"] is False and gone["degraded"] is True
    assert gone["degraded_inputs"] == ["financial_conditions"]
    assert "NFCI" in gone["degraded_note_en"]
    assert "NFCI" in gone["degraded_note_zh"] or "金融条件" in gone["degraded_note_zh"]


def test_drawdown_claim_degrades_when_the_composition_is_not_the_validated_set():
    f = _synthetic_macro_frame()
    full = conditions.conditions_snapshot(f)["drawdown_risk"]
    assert full["partial"] is False
    assert full["dd10_prob_pct"] is not None
    assert full["stat_passport"]["basis"] == "measured"
    assert full["stat_passport"]["n_base"] is not None

    f2 = f.copy()
    f2.loc[f2.index[-1], "nfci"] = np.nan          # the live 2026-07-29 NFCI hole
    part = conditions.conditions_snapshot(f2)["drawdown_risk"]
    assert part["partial"] is True
    assert part["basis_missing"] == ["NFCI"]
    assert part["n_legs"] == part["n_legs_expected"] - 1
    # the band/score still ship (a null never blocks display tier) ...
    assert part["band"] is not None and part["score"] is not None
    # ... but the claim measured on a DIFFERENT composition does not
    assert part["dd10_prob_pct"] is None
    assert part["dd10_prob_informative"] is False
    assert part["stat_passport"]["basis"] == "partial"
    assert part["stat_passport"]["n_base"] is None
    assert part["degraded_note_en"] and part["degraded_note_zh"]
    assert "NFCI" not in part["basis"], part["basis"]


def test_per_input_vintages_are_emitted():
    snap = conditions.conditions_snapshot(_synthetic_macro_frame())
    v = snap["vintages"]
    for key in ("nfci", "hy_oas", "ebp", "vix"):
        assert key in v, key
        assert set(v[key]) >= {"asof", "age_days", "stale", "label", "cadence_days"}
    assert isinstance(snap["stale_inputs"], list)


def test_vintage_reports_the_print_date_not_the_ffilled_frame_date():
    """The frame carries slow series forward onto every trading day, so the frame date is not
    the vintage.  A weekly series stamped once and ffilled must report its OWN date."""
    f = _synthetic_macro_frame()
    f["nfci"] = np.nan
    stamp = f.index[-12]
    f.loc[stamp, "nfci"] = -0.5
    f["nfci"] = f["nfci"].ffill()
    v = conditions.conditions_snapshot(f)["vintages"]["nfci"]
    assert v["asof"] == str(stamp.date()), v
    assert v["age_days"] == (f.index[-1] - stamp).days


# ===========================================================================
# 4 — structurally-inapplicable leg must be NaN, not a diluting 0.0
# ===========================================================================

def test_subscore_renormalises_over_a_nan_leg_instead_of_averaging_it_as_zero():
    """The mechanic behind the 'internals prints 50.0 and can never reach watch' defect: one
    leg confirmed at 1.0, its sibling structurally inapplicable -> 100, not 50."""
    idx = pd.bdate_range("2026-01-01", periods=30)
    sigs = pd.DataFrame({"leg_hot": 1.0, "leg_na": np.nan}, index=idx)
    calib = {"bands": dict(rr._DEFAULT_BANDS),
             "legs": {"leg_hot": {"thr_pct": 0.85}, "leg_na": {"thr_pct": 0.85}},
             "scares": {"synthetic": {"tier": "B",
                                      "legs": [("leg_hot", 1.0), ("leg_na", 1.0)]}}}
    out = rr.subscore_series(sigs, calib)
    assert out["synthetic"].iloc[-1] == pytest.approx(100.0)

    # and the defect shape, for contrast: a notna 0.0 sibling DOES halve it
    sigs_zero = sigs.copy()
    sigs_zero["leg_na"] = 0.0
    out_zero = rr.subscore_series(sigs_zero, calib)
    assert out_zero["synthetic"].iloc[-1] == pytest.approx(50.0)


def test_nh_contraction_is_nan_off_near_high():
    n = 700
    idx = pd.bdate_range("2021-01-04", periods=n)
    px = [100.0] * 300 + [100.0 - (i + 1) * 0.1 for i in range(n - 300)]
    spy = pd.Series(px, index=idx)
    breadth = pd.DataFrame({"nh": [20.0] * n, "n_members": [500.0] * n}, index=idx)
    leg = rr.build_nh_contraction(spy, breadth)
    tail = leg.iloc[400:]
    assert tail.isna().all(), tail[tail.notna()]
    assert not (tail == 0.0).any()


# ===========================================================================
# 5 — display_only legs must not set the DISPLAYED number either
# ===========================================================================

def _vol_shaped_calib():
    return {"bands": dict(rr._DEFAULT_BANDS),
            "legs": {"graded": {"thr_pct": 0.90, "lift_2020": 0.44},
                     "unpromoted": {"thr_pct": 0.85, "lift_2020": None,
                                    "accruing": True, "display_only": True}},
            "scares": {"vol_like": {"tier": "B",
                                    "legs": [("graded", 0.5), ("unpromoted", 1.0)]}}}


def test_display_only_leg_still_dilutes_the_displayed_subscore_KNOWN_DEFECT():
    """PINS A KNOWN DEFECT — do not "fix" this test, fix it via the gauntlet (§15 of
    research/REGIME_DISLOCATION_RECAL_PROPOSAL.md).

    The VSB W6 contract says a display_only leg is 'STRUCTURALLY UNABLE to move scare tier
    until gauntlet-promoted'.  It is enforced only for escalation, so a quiet un-promoted leg
    at 0.0 still carries full weight in the mean and buries the one graded leg.  That IS a
    doctrine violation and it reads in the calming direction.

    Excluding the leg was implemented on 2026-07-29 and reverted the same day: 'vol' registers
    3 legs and only vix_term resolves (weight_coverage 0.5), so renormalising promotes half the
    registered evidence to full confidence against band cuts never calibrated on that
    composition — measured live as vol 22.4 -> 67.3, ceiling 56 -> 40, US verdict MIXED ->
    RISK_OFF, on ONE unvalidated leg reading BELOW its own thr_pct.  Escalating on that is
    originating a signal, not fixing a bug.

    This test pins the DEFECTIVE arithmetic so the eventual gauntlet-approved fix is a visible,
    reviewed diff rather than a silent behaviour change."""
    idx = pd.bdate_range("2026-01-01", periods=30)
    sigs = pd.DataFrame({"graded": 0.8, "unpromoted": 0.0}, index=idx)
    calib = _vol_shaped_calib()
    got = rr.subscore_series(sigs, calib)["vol_like"].iloc[-1]
    # the diluted value: (0.8*0.5 + 0.0*1.0) / 1.5 * 100 == 26.67, NOT the graded leg's 80.0
    assert got == pytest.approx(0.8 * 0.5 / 1.5 * 100), got
    assert got != pytest.approx(80.0)


def test_display_only_dilution_is_disclosed_even_though_it_is_not_fixed():
    """The defect above is not silent: coverage keys let a surface say "this scare is running on
    half its registered evidence".  Disclosure is what ships while the fix waits on the
    gauntlet, so these keys are the load-bearing part of the 2026-07-29 audit response."""
    skip = rr.display_only_legs()
    assert skip, "no display_only legs registered — the contract lost its subject"
    for leg in skip:
        assert rr._LEG_CALIB[leg].get("display_only") is True
    # the legs DO still reach the sub-score (the pinned defect), so the series is not empty
    idx = pd.bdate_range("2026-01-01", periods=30)
    sigs = pd.DataFrame({leg: 1.0 for leg in skip}, index=idx)
    out = rr.subscore_series(sigs)
    assert not out.dropna(how="all").empty, "display_only legs no longer score — see §15"


def test_firing_display_only_leg_surfaces_in_the_payload():
    """A confirmed 1.0 on an un-promoted leg must be visible in its own right, whatever the
    sub-score does with it — this is how a reader learns the doctrine is silencing a firing
    signal."""
    idx = pd.bdate_range("2026-01-01", periods=30)
    sigs = pd.DataFrame({"credit_oas_roc": 0.6, "ai_breadth_divergence": 1.0}, index=idx)
    out = rr.compute(sigs=sigs)
    legs = {d["leg"]: d for d in out["display_only_legs"]}
    assert "ai_breadth_divergence" in legs, out["display_only_legs"]
    d = legs["ai_breadth_divergence"]
    assert d["pctile"] == 1.0 and d["firing"] is True and d["confirmed"] is True
    assert d["scare"] == "internals"
    assert d["reason_en"] and d["reason_zh"]
    # internals DOES carry a sub-score (the leg is counted — the pinned defect above)
    assert "internals" in {s["scare"] for s in out["scares"]}


def test_composition_coverage_is_published_for_every_scare():
    """Disclosure only — gates nothing.  subscore_series renormalises over resolving legs, so a
    scare running on part of its registered evidence publishes at full confidence; the coverage
    is what makes that visible (and it is how the live 'vol' scare reads 1 of 3 legs)."""
    idx = pd.bdate_range("2026-01-01", periods=30)
    sigs = pd.DataFrame({"credit_oas_roc": 0.6, "credit_hyg_tlt": 0.2, "vol_term": 0.8},
                        index=idx)
    out = rr.compute(sigs=sigs)
    by = {s["scare"]: s for s in out["scares"]}
    assert by["credit"]["weight_coverage"] == pytest.approx(1.0)
    assert by["credit"]["partial_composition"] is False
    # vol registers vol_term/putcall/gex as non-display_only; only vol_term resolves
    assert by["vol"]["partial_composition"] is True
    assert by["vol"]["n_legs_resolved"] == 1
    assert by["vol"]["weight_coverage"] == pytest.approx(0.5)


# ===========================================================================
# 6 — calibration honesty: the disclaimer may only claim what the state measured
# ===========================================================================

def test_caution_state_lift_is_reported_and_is_below_base():
    lift = rr._state_lift("caution")
    assert lift["h21"] == pytest.approx(rr._PROB_CAL["h21"]["caution"] / rr._PROB_BASE["h21"], abs=0.01)
    assert lift["h21"] < 1.0, lift
    assert lift["above_base"] is False


def test_disclaimer_is_state_conditional_and_drops_the_flat_lift_claim():
    """The module claimed a flat '~1.5-2x conditional lift' for every state.  The caution
    state's own table entry is 0.16 h21 against a 0.178 base — 0.90x, BELOW base."""
    caution = rr._disclaimer_for("caution")
    assert "1.5-2x" not in caution
    assert "BELOW base" in caution
    assert "17.8%" in caution and "16.0%" in caution
    # a state that DOES measure an edge is allowed to say so
    risk_off = rr._disclaimer_for("risk-off")
    assert "Edge is MODEST" in risk_off and "BELOW base" not in risk_off
    # and with no state to condition on, no multiple is claimed at all
    assert "1.5-2x" not in rr._DISCLAIMER
    assert "STATE-CONDITIONAL" in rr._DISCLAIMER


def test_drawdown_prob_carries_the_states_own_lift_beside_the_blended_one():
    """lift_h21 blends in the conjunction bump, so a quiet tier could read as an edge it never
    measured.  The state's OWN lift is now published beside it."""
    p = rr._drawdown_prob("caution", 3)
    assert p["lift_h21"] > 1.0                  # conjunction-inflated
    assert p["state_lift_h21"] < 1.0            # what the state alone measured
    assert p["state_above_base"] is False
    assert "below base" in p["lift_note_en"]
    assert p["lift_note_zh"]


def test_calibration_constants_are_untouched():
    """The audit forbids moving any calibration number; only the copy may change."""
    assert rr._PROB_CAL["h21"] == {"calm": 0.13, "watch": 0.13, "caution": 0.16,
                                   "elevated": 0.25, "risk-off": 0.33}
    assert rr._PROB_BASE == {"h5": 0.036, "h10": 0.086, "h21": 0.178}
    assert rr._DEFAULT_BANDS == {"watch": 55.0, "caution": 68.0,
                                 "elevated": 78.0, "risk_off": 88.0}
    assert rr._GATE_BREADTH_PCT == 0.40
    assert rr._VALIDATED_MIN == 1.20
    assert ms._DEFAULT_CALIB["base"] == {"caution": 56, "elevated": 38, "risk-off": 26}
    assert ms._DEFAULT_CALIB["severe_bump"] == 10 and ms._DEFAULT_CALIB["floor"] == 12
    assert ms.WEIGHTS == {"trend": 0.24, "risk": 0.18, "vol": 0.16,
                          "breadth": 0.16, "liquidity": 0.14, "stress": 0.12}


# ===========================================================================
# 7 — the context gate's own claim must be falsifiable
# ===========================================================================

def _snap_for_log(state, ungated, gate_met):
    return {"asof": "2026-07-29", "state": state, "alert": state in rra.ALERT_STATES,
            "state_ungated": ungated, "dominant_scare": "growth", "top_score": 65.0,
            "scares": [], "drawdown_prob": {"conjunction_n": 1},
            "context_gate": {"met": gate_met, "spy_below_200dma": False,
                             "breadth_weak": False}}


def test_forward_log_records_the_ungated_state_and_the_gate_legs():
    """Only the GATED state was logged, so every day the gate clamped elevated -> caution was
    recorded as a caution day: alerts n=0 for the life of the ledger and the gate's measured
    false-positive reduction was unfalsifiable on its own evidence."""
    e = rra._entry_from_snapshot(_snap_for_log("caution", "elevated", False))
    assert e["state"] == "caution"
    assert e["state_ungated"] == "elevated"
    assert e["alert"] is False and e["alert_ungated"] is True
    assert e["gate_clamped"] is True
    assert e["context_gate"] == {"met": False, "spy_below_200dma": False, "breadth_weak": False}


def test_ungated_alert_is_graded_as_its_own_counterfactual():
    idx = pd.bdate_range("2026-01-01", periods=200)
    # a real decline: >5% inside the first 21 business days, so the row grades as a precursor
    spy = pd.Series(np.linspace(100, 40, len(idx)), index=idx)
    entry = {"asof": str(idx[0].date()), "state": "caution", "state_ungated": "elevated"}
    graded = rra._grade_entry(entry, spy)
    assert graded is not None
    assert graded["outcome"] == "tp_watch"                 # the GATED row
    assert graded["outcome_ungated"] == "true_positive"    # the alert the gate suppressed


def test_scorecard_publishes_the_gate_counterfactual(tmp_path):
    rows = []
    for i, dd in enumerate((True, False, False)):
        rows.append({
            "asof": f"2026-0{i+1}-05", "state": "caution", "alert": False,
            "state_ungated": "elevated", "alert_ungated": True, "gate_clamped": True,
            "graded": {"outcome": "tp_watch" if dd else "tn_watch",
                       "outcome_ungated": "true_positive" if dd else "false_positive",
                       "any_dd5_within_h21": dd, "fwd_dd": {"h21": -0.06 if dd else -0.01}},
        })
    p = tmp_path / "data" / "risk_radar" / "forward_log.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    sc = rra.scorecard(root=tmp_path)
    cf = sc["context_gate_counterfactual"]
    assert cf["n_clamped_by_gate"] == 3
    assert cf["n_alerts_ungated"] == 3
    assert cf["n_true_pos_ungated"] == 1 and cf["n_false_pos_ungated"] == 2
    assert cf["alert_precision_ungated"] == pytest.approx(1 / 3, abs=0.001)
    # the gated view is still 0 alerts — which is exactly why the block is needed
    assert sc["n_alerts"] == 0


def test_compute_marks_when_the_gate_clamped_the_state():
    idx = pd.bdate_range("2026-01-01", periods=30)
    out = rr.compute(sigs=pd.DataFrame({"credit_oas_roc": 0.6}, index=idx),
                     gate={"met": False, "spy_below_200dma": False, "breadth_weak": False})
    assert "state_ungated" in out and "gate_clamped" in out
    assert out["gate_clamped"] == (out["state_ungated"] != out["state"])


# ===========================================================================
# 9 — the minor cluster
# ===========================================================================

def test_9a_breadth_copy_names_the_real_percentile_window():
    """The window is conditions.complacency.breadth_pctile_lookback_d = 504 trading days
    (~2y); the copy said 'of 5y', inflating the claimed history 2.5x."""
    latest = {"conditions": {"complacency": {"breadth_above200_pctile": 0.84,
                                             "breadth_div": False}}}
    c = ms._comp_breadth(latest)
    assert "of 5y" not in c["read_en"], c["read_en"]
    assert "五年" not in c["read_zh"], c["read_zh"]
    assert "of 2y" in c["read_en"] and "两年" in c["read_zh"]


def test_9b_hy_direction_uses_the_unrounded_change():
    """hy_oas_chg_21d_bp is rounded to whole bp, so a -0.4bp TIGHTENING becomes -0.0 — and
    `-0.0 < 0` is False, so the copy said 'widening' on a session credit had tightened."""
    def leg(bp, exact, widen):
        return ms._comp_liquidity({
            "liquidity_overlay": "expanding",
            "conditions": {"complacency": {"hy_oas_chg_21d_bp": bp,
                                           "hy_oas_chg_21d_bp_exact": exact,
                                           "credit_widen": widen},
                           "financial_conditions": {"state": "neutral"},
                           "systemic_stress": {"state": "normal"}}})
    tight = leg(-0.0, -0.4, False)
    assert "tightening" in tight["read_en"], tight["read_en"]
    assert "收窄" in tight["read_zh"]
    wide = leg(0.0, 0.4, True)
    assert "widening" in wide["read_en"], wide["read_en"]
    flat = leg(0.0, 0.0, False)
    assert "flat" in flat["read_en"] and "持平" in flat["read_zh"]


def test_9b_conditions_ships_the_unrounded_companion():
    snap = conditions.conditions_snapshot(_synthetic_macro_frame())
    c = snap["complacency"]
    if c["hy_oas_chg_21d_bp"] is not None:
        assert c["hy_oas_chg_21d_bp_exact"] is not None
        assert round(c["hy_oas_chg_21d_bp_exact"]) == pytest.approx(c["hy_oas_chg_21d_bp"], abs=1)


def test_9c_calibration_overlay_is_bounded_on_every_field(tmp_path, monkeypatch):
    """weights were clamped; base / severe_bump / floor were applied verbatim, so an overlay
    could drive the ceiling negative or raise inside the live override."""
    d = tmp_path / "data" / "market_state"
    d.mkdir(parents=True)
    (d / "calibration.json").write_text(json.dumps({
        "weights": {"complacency": 999.0, "breadth_div": -5.0},
        "base": {"caution": -500, "elevated": 90, "risk-off": 95},
        "severe_bump": "not-a-number",
        "floor": 10 ** 9,
    }))
    c = ms._ms_calib(root=tmp_path)
    lo, hi = ms._WEIGHT_BOUNDS
    assert lo <= c["weights"]["complacency"] <= hi
    assert lo <= c["weights"]["breadth_div"] <= hi
    for k, v in c["base"].items():
        assert 0.0 <= v <= 100.0, (k, v)
    # a looser state may never cap HIGHER than a tighter one
    assert c["base"]["caution"] >= c["base"]["elevated"] >= c["base"]["risk-off"]
    assert c["severe_bump"] == ms._DEFAULT_CALIB["severe_bump"], "unparseable value must be dropped"
    assert 0.0 <= c["floor"] <= 100.0
    # and the ceiling that comes out is still a sane score
    for st in ("caution", "elevated", "risk-off"):
        ceil = ms._ceiling_for(st, True, list(ms.CORROBORATORS), c)
        assert 0 <= ceil <= 100, (st, ceil)


def test_9c_absent_overlay_leaves_the_defaults_exactly(tmp_path):
    c = ms._ms_calib(root=tmp_path)
    assert c["base"] == ms._DEFAULT_CALIB["base"]
    assert c["weights"] == ms._DEFAULT_WEIGHTS
    assert c["severe_bump"] == ms._DEFAULT_CALIB["severe_bump"]
    assert c["floor"] == ms._DEFAULT_CALIB["floor"]


def test_9d_monthly_timeframe_gets_the_same_pit_gate_as_weekly():
    """R3b PIT-gated W but left M resampling the LIVE partial month under completed_only."""
    idx = pd.bdate_range("2019-01-01", periods=1100)
    s = pd.Series(np.linspace(100, 200, len(idx)), index=idx)
    completed = cycles._me_completed(s)
    live = s.resample("ME").last().dropna()
    assert completed.index[-1] <= s.index.max()
    assert len(live) >= len(completed)
    if live.index[-1] > s.index.max():
        assert len(live) == len(completed) + 1

    # the availability gate is identical between paths (the FIX B lesson from W)
    short = pd.Series(np.linspace(100, 110, 400), index=pd.bdate_range("2024-01-01", periods=400))
    assert cycles.mtf_snapshot(short, completed_only=True).get("M") == {}
    assert cycles.mtf_snapshot(short, completed_only=False).get("M") == {}
    # D / 3D are untouched by the M change (W legitimately differs — that IS the R3b gate)
    a = cycles.mtf_snapshot(s, completed_only=True)
    b = cycles.mtf_snapshot(s, completed_only=False)
    assert a["D"] == b["D"], "D must not depend on completed_only"
    assert a["3D"] == b["3D"], "3D must not depend on completed_only"


def test_9d_default_path_is_byte_identical():
    """completed_only=False is every other caller in the repo — it must not move."""
    idx = pd.bdate_range("2019-01-01", periods=1100)
    s = pd.Series(np.linspace(100, 200, len(idx)) + np.sin(np.arange(len(idx)) / 7), index=idx)
    got = cycles.mtf_snapshot(s, completed_only=False)
    expect_m = cycles._tf_state(s.dropna().resample("ME").last().dropna())
    assert got["M"] == expect_m


def test_9e_freshness_stamp_carries_real_input_vintages(tmp_path):
    from datetime import datetime, timezone
    now = datetime(2026, 7, 29, 6, 1, tzinfo=timezone.utc)
    snap = {"asof": "2026-07-29", "verdict": "MIXED",
            "input_vintages": {"nfci": {"asof": "2026-07-10", "age_days": 19, "stale": True},
                               "vix": {"asof": "2026-07-29", "age_days": 0, "stale": False}}}
    ms.persist(snap, root=tmp_path, now=now)
    fresh = json.loads((tmp_path / "data" / "market_state" / "latest.json").read_text())["freshness"]
    assert fresh["any_input_stale"] is True
    assert fresh["stale_inputs"] == ["nfci"]
    assert fresh["worst_input_age_days"] == 19
    assert fresh["inputs"]["nfci"]["asof"] == "2026-07-10"


def test_9g_global_breadth_stale_guard_uses_the_frames_asof(monkeypatch, tmp_path):
    """pd.Timestamp.today() inside a causal series builder graded the store against TODAY, so a
    replay at an older as-of could drop the leg from ALL history for a staleness that did not
    exist then."""
    import inspect
    src = inspect.getsource(rr._global_breadth_raw)
    assert "asof" in inspect.signature(rr._global_breadth_raw).parameters
    assert "pd.Timestamp(asof)" in src
    # and leading_signals threads the SPY calendar's own max
    assert "_global_breadth_raw(asof=" in inspect.getsource(rr.leading_signals)


def test_9h_backtest_replica_applies_the_election_band_modulation():
    """state_series is consumed by trajectory() as 'what the card would have shown', and its
    odds_delta gates de-escalation eligibility — so a replica missing the live band nudge was
    systematically less escalated for ~7 months of every midterm year."""
    from engine import election_cycle as ec
    idx = pd.bdate_range("2026-05-01", periods=40)      # midterm year, inside Apr-Oct
    d = rrb.band_delta_series(idx)
    assert len(d) == len(idx)
    assert set(np.unique(d.to_numpy())) <= {0.0, float(ec._BAND_NUDGE)}

    # outside the window the nudge is always zero
    off = rrb.band_delta_series(pd.bdate_range("2025-05-01", periods=20))   # not a midterm year
    assert (off == 0.0).all()

    # a sub-score sitting between the nudged and un-nudged caution cut must band differently
    calib = {"bands": dict(rr._DEFAULT_BANDS),
             "legs": {"credit_oas_roc": {}},
             "scares": {"credit": {"tier": "A", "legs": [("credit_oas_roc", 1.0)]}}}
    between = (rr._DEFAULT_BANDS["caution"] + rr._DEFAULT_BANDS["watch"]) / 2
    mid = rr._DEFAULT_BANDS["caution"] - 1.0        # inside the 4-point nudge
    subs = pd.DataFrame({"credit": mid}, index=idx)
    states = rrb.state_series(subs, calib)
    assert states.notna().all()
    assert between < mid < rr._DEFAULT_BANDS["caution"]


def test_9h_band_delta_series_never_touches_the_loud_cuts():
    """The calendar may lower watch/caution only — it can NEVER manufacture a loud banner."""
    import inspect
    src = inspect.getsource(rrb.state_series)
    assert '"watch": (bands["watch"] - _d)' in src
    assert '"caution": (bands["caution"] - _d)' in src
    assert '"elevated"' not in src.split("bands = {**bands,")[1].split("}")[0]


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

def _synthetic_macro_frame(n: int = 800) -> pd.DataFrame:
    """A complete feature frame for the conditions layer — every drawdown-composite input
    present AND varying (a constant input z-scores to NaN and silently leaves the composite)."""
    idx = pd.bdate_range("2023-01-02", periods=n)
    rng = np.arange(n, dtype=float)
    f = pd.DataFrame(index=idx)
    f["SPY"] = 400 + np.cumsum(np.sin(rng / 9) * 0.4)
    f["vix"] = 16 + 3 * np.sin(rng / 30)
    f["vix3m"] = 18 + 2 * np.sin(rng / 30)
    f["vix_ratio"] = f["vix"] / f["vix3m"]
    f["skew"] = 130 + 8 * np.sin(rng / 40)
    f["us10y"] = 4.0 + 0.3 * np.sin(rng / 50)
    f["hy_oas"] = 3.5 + 0.4 * np.sin(rng / 45)
    f["copper_gold"] = 0.18 + 0.01 * np.sin(rng / 35)
    f["dxy"] = 103 + 2 * np.sin(rng / 60)
    f["spread_2s10s"] = 0.2 + 0.2 * np.sin(rng / 70)
    f["term_premium_10y"] = 0.4 + 0.02 * np.sin(rng / 28)
    f["curve_tp_adj"] = f["spread_2s10s"] + f["term_premium_10y"]
    f["nfci"] = -0.4 + 0.1 * np.sin(rng / 25)
    f["anfci"] = -0.2 + 0.05 * np.sin(rng / 31)
    f["stlfsi"] = -0.8 + 0.05 * np.sin(rng / 29)
    f["sahm"] = 0.10
    f["recession_prob"] = 1.0
    f["ebp"] = -0.3 + 0.05 * np.sin(rng / 33)
    f["ebp_recession_prob"] = 0.08
    f["initial_claims"] = 220 + 5 * np.sin(rng / 20)
    f["initial_claims_4wk"] = 222 + 3 * np.sin(rng / 25)
    f["continued_claims"] = 1800 + 20 * np.sin(rng / 30)
    f["pct_above_200"] = 60 + 10 * np.sin(rng / 22)
    return f


def _mixed_snapshot():
    latest = {
        "date": "2026-07-29",
        "liquidity_overlay": "expanding",
        "conditions": {
            "risk_appetite": {"roro_state": "neutral", "vix_term": 0.98},
            "complacency": {"vix_pctile": 0.6, "breadth_above200_pctile": 0.84,
                            "breadth_div": False, "hy_oas_chg_21d_bp": 1.0,
                            "hy_oas_chg_21d_bp_exact": 1.0, "credit_widen": True,
                            "calm": 0, "spy_high_prox": 0.94, "state": "neutral"},
            "financial_conditions": {"state": None},
            "systemic_stress": {"state": "normal"},
            "drawdown_risk": {"band": "low", "dd10_prob_pct": None},
            "recession": {"score": 20, "label": "low"},
            "vintages": {"nfci": {"asof": "2026-07-17", "age_days": 12, "stale": False}},
            "stale_inputs": [],
        },
        "macro_risk": {"score": 0.2, "label": "low"},
        "risk_radar": {"state": "caution", "top_score": 77, "drawdown_prob": {},
                       "scares": [], "state_ungated": "caution"},
        "turning_point": {"present": False},
    }
    return ms.market_state_snapshot(latest, None)


def test_snapshot_reports_degraded_components_and_vintages():
    snap = _mixed_snapshot()
    assert snap is not None
    assert "liquidity" in snap["degraded_components"]
    assert snap["input_vintages"].get("nfci", {}).get("asof") == "2026-07-17"
