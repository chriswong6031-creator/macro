"""Risk unification tests — P2-B' / masterplan W2 / audit #4.

Guards, one per mechanism:
  1. Single gross SOURCE — risk_state + risk_radar derive their gross magnitudes from the
     ONE versioned regime_one.RISK_STATE_GROSS table (byte-identical to the prior literals).
  2. fused_risk positioning fusion — the fused state is MAX-CAUTIOUS(quad prior, live
     risk_state); a positioning blow-off escalates the fused state even when the quad is benign.
  3. fused_gate_factor — routes the fused 5-state through the same quad/liquidity nudges the
     legacy gate used; degraded caps the gate at 'caution'.
  4. directives consumer — risk_state's favor_entries / cap_leadership (previously zero
     consumers) are carried onto the fused verdict by refuse().
  5. 2026-06-23 REPLAY (the acceptance-gate regression) — the fused gate does NOT de-gross
     below MRS in the event window (NO-FLIP is the correct, permanent verdict on this data).
  6. Coherence assert — (A) gross tables agree, (B) a silent gate-basis flip hard-fails,
     (C1) a fused-would-have-caught-it day hard-fails, (C) a bare banner-vs-gate divergence
     under no-flip is TRACKED not failed.
"""
from __future__ import annotations

import pytest

from engine import regime_coherence as CO
from engine import regime_one as R


# --- 1. single gross source ------------------------------------------------- #
def test_single_gross_source_byte_identical():
    from engine.risk_radar import _GROSS as RR
    from engine.risk_state import _DEFAULT_GROSS as RS
    # prior literals (documented in each module) must be reproduced exactly from the source.
    assert RS == {"caution": 0.90, "elevated": 0.78, "risk_off": 0.60, "floor": 0.50}
    assert RR == {"watch": 0.97, "caution": 0.90, "elevated": 0.78, "risk_off": 0.60, "floor": 0.50}
    # and they must MATCH regime_one on the shared bands (single source, no drift).
    assert RS["caution"] == R.RISK_STATE_GROSS["caution"]
    assert RS["elevated"] == R.RISK_STATE_GROSS["elevated"]
    assert RS["risk_off"] == R.RISK_STATE_GROSS["risk-off"]
    assert RR["caution"] == R.RISK_STATE_GROSS["caution"]
    assert RR["risk_off"] == R.RISK_STATE_GROSS["risk-off"]


# --- 2. positioning fusion (the 06-23 lesson) ------------------------------- #
def test_max_cautious_positioning_overrides_benign_quad():
    # quad prior risk-on (Q1) but live risk_state screaming 'elevated' -> fused = elevated.
    assert R._max_cautious("risk-on", "elevated") == "elevated"
    # None risk_state drops out -> quad prior wins.
    assert R._max_cautious("risk-on", None) == "risk-on"
    # a calmer risk_state never LOOSENS a cautious quad.
    assert R._max_cautious("elevated", "neutral") == "elevated"


def test_rs_state_token_normalization():
    # risk_state uses 'risk_off' (underscore); we unify on 'risk-off' (hyphen).
    assert R._rs_state({"state": "risk_off"}) == "risk-off"
    assert R._rs_state({"state": "caution"}) == "caution"
    assert R._rs_state({"state": None}) is None
    assert R._rs_state(None) is None


def test_fused_risk_escalates_on_positioning_blowoff():
    # A Q1 (risk-on) quad with a live risk_state at 'elevated' must produce a fused state
    # more cautious than the quad prior — the exact catch MRS/quad miss.
    tape = {"inflation": -0.2, "growth": 0.3, "n_available": 6, "inflation_legs": {}, "growth_legs": {}}
    macro = {"inflation": -0.1, "growth": 0.2, "n_available": 2, "inflation_legs": {}, "growth_legs": {}}
    flip = {"degraded": False, "label_quad": "Q1", "asof": "2026-06-23"}
    fused = R._fused_risk(tape, macro, "Q1", flip, base_conf=0.8,
                          risk_state={"state": "elevated", "score": 62})
    assert fused["quad_prior_state"] == "risk-on"
    assert fused["risk_state_state"] == "elevated"
    assert fused["label"] == "elevated"
    assert fused["positioning_override"] is True
    assert fused["gross_factor"] == R.RISK_STATE_GROSS["elevated"]


# --- 3. fused_gate_factor --------------------------------------------------- #
def test_fused_gate_factor_mirrors_legacy_nudges():
    # caution base 0.90, expanding liquidity x1.1 -> 0.99 (matches the legacy arithmetic).
    g = R.fused_gate_factor({"gross_factor": 0.90, "label": "caution", "degraded": False},
                            quad="Q1", liquidity="expanding")
    assert g["gate_factor"] == 0.99
    assert g["basis"] == "fused_risk"
    # risk-off base 0.60, Q4 x0.85, contracting x0.8 -> clipped.
    g2 = R.fused_gate_factor({"gross_factor": 0.60, "label": "risk-off", "degraded": False},
                             quad="Q4", liquidity="contracting")
    assert 0.2 <= g2["gate_factor"] <= 0.60


def test_fused_gate_degraded_caps_at_caution():
    g = R.fused_gate_factor({"gross_factor": 1.0, "label": "risk-on", "degraded": True},
                            quad="Q1", liquidity="expanding")
    assert g["gate_factor"] <= R.RISK_STATE_GROSS["caution"]


# --- 4. directives consumer ------------------------------------------------- #
def test_refuse_carries_risk_state_directives():
    r1 = {
        "label_quad": "Q1", "degraded": False,
        "fused_risk": {"label": "risk-on", "gross_factor": 1.0, "_liquidity": "neutral"},
        "flip_attribution": {"label_quad": "Q1"},
    }
    rs = {"state": "caution", "score": 44, "favor_entries": True, "cap_leadership": False}
    out = R.refuse(r1, rs)
    fr = out["fused_risk"]
    assert fr["label"] == "caution"                 # positioning escalated the quad prior
    assert fr["favor_entries"] is True              # directive consumed (was a zombie field)
    assert fr["cap_leadership"] is False
    assert fr["gate"]["basis"] == "fused_risk"
    assert fr["gate"]["gate_factor"] <= R.RISK_STATE_GROSS["caution"] + 1e-9


# --- 5. the 2026-06-23 replay (permanent regression) ------------------------ #
def test_replay_2026_06_23_no_flip():
    """The acceptance-gate regression: on the committed event archive, the fused gate must
    NOT de-gross below MRS in the window — so NO-FLIP is the correct, permanent verdict.
    If this ever changes (fused catches it), the flip decision must be re-litigated
    DELIBERATELY (this test failing is the signal)."""
    from scripts.ab_risk_gate import run_replay
    rep = run_replay()
    if not rep.get("available"):
        pytest.skip("event archive not present in this checkout")
    assert rep["verdict"] == "MISSES", rep
    assert rep["fused_catches_where_mrs_failed"] is False
    # fused is looser (delta positive) on every window day.
    assert rep["min_delta_gate_B_minus_A"] is not None and rep["min_delta_gate_B_minus_A"] > 0
    # the positioning detector had no reading on the event day itself.
    assert rep["detector_live_on_event_day"] is False


def test_gross_reconciliation_all_agree():
    from scripts.ab_risk_gate import reconcile_gross_tables
    recon = reconcile_gross_tables()
    assert recon["reconciled"] is True
    assert recon["max_shared_gap"] == 0.0


# --- 6. coherence assert ---------------------------------------------------- #
def _latest(banner, gate_basis="MRS", gate_factor=0.91, fused_gate_factor=None,
            fused_label="risk-on", rs_state="neutral"):
    """A minimal assembled-latest shim + a monkeypatch of the live gate reader."""
    return {
        "regime_one": {"shadow": True, "fused_risk": {
            "label": fused_label,
            "gate": ({"basis": "fused_risk", "gate_factor": fused_gate_factor}
                     if fused_gate_factor is not None else {})}},
        "risk_state": {"state": rs_state},
        "_test_gate": {"gate_factor": gate_factor, "basis": gate_basis, "computed": True,
                       "ms_verdict": banner, "radar_state": "caution"},
    }


@pytest.fixture()
def patch_live_gate(monkeypatch):
    def _install(latest):
        monkeypatch.setattr(CO, "_live_gate", lambda _l: latest["_test_gate"])
    return _install


def test_coherence_gross_tables_agree_passes(patch_live_gate):
    latest = _latest("RISK_ON", gate_factor=1.0)
    patch_live_gate(latest)
    rep = CO.assert_coherence(latest, strict=False)
    assert rep["checks"]["gross_tables_agree"]["ok"] is True


def test_coherence_silent_basis_flip_hard_fails(patch_live_gate):
    latest = _latest("RISK_ON", gate_basis="fused_risk", gate_factor=1.0)
    patch_live_gate(latest)
    with pytest.raises(CO.CoherenceError):
        CO.assert_coherence(latest, strict=True)


def test_coherence_gate_compute_failure_is_not_a_flip(monkeypatch):
    # a transient _regime_anchor failure (computed=False, basis=None) must NOT hard-fail as a
    # silent basis flip — it's tracked, not a flip.
    latest = _latest("RISK_ON", gate_factor=1.0)
    monkeypatch.setattr(CO, "_live_gate",
                        lambda _l: {"gate_factor": None, "basis": None, "computed": False,
                                    "error": "boom", "ms_verdict": None, "radar_state": None})
    rep = CO.assert_coherence(latest, strict=True)   # must NOT raise
    assert rep["ok"] is True
    assert any("could not be computed" in r for r in rep["reasons"])


def test_coherence_bare_divergence_is_tracked_not_failed(patch_live_gate):
    # banner RISK_OFF, MRS gate 0.91 (risk-on), fused shadow NOT cautious -> known residual.
    latest = _latest("RISK_OFF", gate_factor=0.91, fused_gate_factor=None)
    patch_live_gate(latest)
    rep = CO.assert_coherence(latest, strict=True)   # must NOT raise
    d = rep["checks"]["directional"]
    assert d["banner_vs_gate_divergence"] is True
    assert d["c1_fused_would_have_caught"] is False
    assert rep["ok"] is True


def test_coherence_c1_fused_would_have_caught_hard_fails(patch_live_gate):
    # banner RISK_OFF, MRS gate 0.91 (loose), but the SHADOW fused gate IS cautious (0.72)
    # -> flipping WOULD have de-grossed -> re-open no-flip -> hard fail.
    latest = _latest("RISK_OFF", gate_factor=0.91, fused_gate_factor=0.72,
                     fused_label="caution")
    patch_live_gate(latest)
    with pytest.raises(CO.CoherenceError):
        CO.assert_coherence(latest, strict=True)


def test_coherence_c3_envelope_breach_hard_fails(patch_live_gate):
    # a full risk-off banner while the gate is wide-open (>0.98) -> regression.
    latest = _latest("RISK_OFF", gate_factor=1.0, fused_gate_factor=None)
    patch_live_gate(latest)
    with pytest.raises(CO.CoherenceError):
        CO.assert_coherence(latest, strict=True)
