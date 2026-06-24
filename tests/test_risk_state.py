"""Tests for engine/risk_state.py — the fused equity-internal RISK STATE.

Exercises each leg, the 2026-06-23-shaped blow-off fixture, graceful degradation,
monotonicity, the band/label map, and the alert flag. The pure compute() core is
tested directly with synthetic `latest` dicts (no IO); snapshot() is smoke-tested.
"""
from __future__ import annotations

from engine import risk_state as rs


# --- fixtures ----------------------------------------------------------------
def _benign_latest():
    return {
        "asof": "2026-01-15",
        "conditions": {
            "complacency": {"state": "neutral", "breadth_div": False,
                            "vix_low": False, "contango": False, "credit_widen": False,
                            "hy_oas_chg_21d_bp": -5.0},
            "risk_appetite": {"vix_term_state": "contango (calm)",
                              "vrp_state": "normal", "skew_pctile": 0.4,
                              "roro_state": "risk-on"},
        },
        "turning_point": {"state": "normal"},
        "cross_asset_confirm": {"caution_flags": []},
        "macro_risk": {"score": 0.1, "label": "low"},
    }


def _blowoff_latest():
    """The 2026-06-23 shape: calm surface, fragile internals, dealers wobbling."""
    return {
        "asof": "2026-06-23",
        "conditions": {
            "complacency": {"state": "hidden_fragility", "breadth_div": True,
                            "vix_low": True, "contango": True, "credit_widen": True,
                            "spy_high_prox": 0.99, "breadth_above200_pctile": 0.2,
                            "hy_oas_chg_21d_bp": 12.0},
            "risk_appetite": {"vix_term_state": "contango (calm)",
                              "vrp_state": "rich (vol overpriced)", "skew_pctile": 0.92,
                              "roro_state": "neutral"},
        },
        "turning_point": {"state": "fragile-reversible"},
        "cross_asset_confirm": {"caution_flags": [
            {"key": "bonds", "lead": "credit", "severity": "high"},
            {"key": "fx", "lead": "dollar", "severity": "med"}]},
        "macro_risk": {"score": 0.3, "label": "moderate"},
    }


def _gex_short():
    return [{"key": "SPX", "grp": "Index", "regime": "short", "net_gex_bn": -8.0,
             "spot": 7000.0, "gamma_flip": 7100.0, "vh_state": "IN_HOLE",
             "tilt_read": "agree_down"}]


def _gex_long():
    return [{"key": "SPX", "grp": "Index", "regime": "long", "net_gex_bn": 18.0,
             "spot": 7500.0, "gamma_flip": 7400.0, "vh_state": "STABLE",
             "tilt_read": "neutral"}]


# --- core behavior -----------------------------------------------------------
def test_benign_is_low_risk():
    out = rs.compute(_benign_latest(), gex_index=_gex_long())
    assert out["schema"] == "risk_state.v1"
    assert out["state"] in ("risk-on", "neutral")
    assert out["score"] < 40
    assert out["alert"] is False
    assert out["is_context_only"] is False


def test_blowoff_is_risk_off_and_alerts():
    out = rs.compute(_blowoff_latest(), gex_index=_gex_short(),
                     hyg_tlt_roc=-0.03, board_stretch="stretched")
    assert out["score"] >= 60
    assert out["state"] in ("elevated", "risk-off")
    assert out["alert"] is True
    # the keystone complacency leg + breadth + dealer gamma must be among drivers
    keys = {d["key"] for d in out["drivers"]}
    assert "complacency" in keys
    assert "dealer_gamma" in keys
    # drivers are sorted by contribution descending
    contribs = [d["contribution"] for d in out["drivers"]]
    assert contribs == sorted(contribs, reverse=True)


def test_monotonicity_more_firing_legs_higher_score():
    low = rs.compute(_benign_latest(), gex_index=_gex_long())
    high = rs.compute(_blowoff_latest(), gex_index=_gex_short(),
                      hyg_tlt_roc=-0.03, board_stretch="stretched")
    assert high["score"] > low["score"]


def test_individual_legs_present_and_absent():
    out = rs.compute(_blowoff_latest(), gex_index=_gex_short(),
                     hyg_tlt_roc=-0.03)
    legs = out["legs"]
    # complacency leg fires at full intensity on hidden_fragility
    assert legs["complacency"]["available"] is True
    assert legs["complacency"]["intensity"] == 1.0
    # extension leg is absent when no board_stretch is injected
    assert legs["extension"]["available"] is False
    # dealer gamma fires on short regime
    assert legs["dealer_gamma"]["available"] is True
    assert legs["dealer_gamma"]["intensity"] >= 0.9


def test_dealer_gamma_long_is_calm_but_vol_hole_adds():
    # long gamma, stable -> ~0; intensity should be low
    out = rs.compute(_benign_latest(), gex_index=_gex_long())
    assert out["legs"]["dealer_gamma"]["intensity"] <= 0.2


def test_credit_leg_combines_hy_and_hyg_tlt():
    latest = _benign_latest()
    latest["conditions"]["complacency"]["hy_oas_chg_21d_bp"] = 10.0  # widening
    out = rs.compute(latest, gex_index=_gex_long(), hyg_tlt_roc=-0.04)
    # 0.5 (HY widening) + 0.5 (HYG/TLT -4% at scale 0.04) -> clipped to 1.0
    assert out["legs"]["credit"]["intensity"] == 1.0


def test_technical_leg_fires_and_counts_as_leading():
    # technical breakdown of the indexes (from mtf_monitor) is a leading leg
    latest = _benign_latest()
    latest["conditions"]["complacency"]["state"] = "hidden_fragility"  # 1 leading hot
    out = rs.compute(latest, gex_index=_gex_long(), tech_intensity=0.9)
    assert out["legs"]["technical"]["available"] is True
    assert out["legs"]["technical"]["intensity"] == 0.9
    # complacency(1.0) + technical(0.9) = 2 hot leading legs -> conjunction escalates
    assert out["conjunction"]["escalated"] is True
    assert "technical" in out["conjunction"]["hot_leading_legs"]


def test_technical_leg_absent_when_none():
    out = rs.compute(_benign_latest(), gex_index=_gex_long(), tech_intensity=None)
    assert out["legs"]["technical"]["available"] is False


def test_sizing_fields_degross_and_favor_entries():
    # benign -> no de-gross, no entry tilt
    benign = rs.compute(_benign_latest(), gex_index=_gex_long())
    assert benign["gross_factor"] == 1.0
    assert benign["favor_entries"] in (False, True)  # depends on banding; benign is risk-on/neutral
    # blow-off -> de-gross < 1, favor entries, cap leadership
    blow = rs.compute(_blowoff_latest(), gex_index=_gex_short(),
                      hyg_tlt_roc=-0.03, board_stretch="stretched")
    assert blow["gross_factor"] < 1.0
    assert blow["gross_factor"] >= 0.5            # floored
    assert blow["favor_entries"] is True
    assert blow["cap_leadership"] is True


def test_sizing_monotonic_in_state():
    # gross_factor must be non-increasing as the state worsens
    order = {"risk-on": 1.0, "neutral": 1.0, "caution": 0.90, "elevated": 0.78, "risk-off": 0.60}
    g = rs._cfg()["gross"]
    prev = 1.01
    for st in rs._STATE_ORDER:
        gf = rs._sizing(st, g)["gross_factor"]
        assert gf <= prev + 1e-9
        prev = gf


def test_graceful_no_legs():
    out = rs.compute({})
    assert out["score"] is None
    assert out["state"] is None
    assert out["alert"] is False
    assert out["is_context_only"] is False


def test_graceful_partial_legs():
    # only a complacency read available -> still computes
    latest = {"conditions": {"complacency": {"state": "watch", "breadth_div": True}}}
    out = rs.compute(latest)
    assert out["score"] is not None
    assert out["n_legs"] >= 1


def test_conjunction_escalates_diluted_mean():
    # 2 leading legs fire hard but the weighted mean is diluted to ~neutral by the
    # calm slow legs -> the conjunction escalator floors the state at caution.
    latest = _benign_latest()
    latest["conditions"]["complacency"]["state"] = "hidden_fragility"
    latest["conditions"]["complacency"]["breadth_div"] = True
    out = rs.compute(latest, gex_index=_gex_long())  # dealers calm (not hot)
    assert out["conjunction"]["escalated"] is True
    assert out["conjunction"]["floor"] == "caution"
    assert out["state"] in ("caution", "elevated", "risk-off")
    assert {"complacency", "breadth_div"}.issubset(set(out["conjunction"]["hot_leading_legs"]))


def test_no_escalation_when_few_hot():
    out = rs.compute(_benign_latest(), gex_index=_gex_long())
    assert out["conjunction"]["escalated"] is False


def test_band_state_map():
    bands = rs._DEFAULT_BANDS
    assert rs._band_state(5, bands) == "risk-on"
    assert rs._band_state(25, bands) == "neutral"
    assert rs._band_state(45, bands) == "caution"
    assert rs._band_state(65, bands) == "elevated"
    assert rs._band_state(85, bands) == "risk-off"


def test_labels_and_contract_present_for_every_state():
    for st in rs._STATE_ORDER:
        assert st in rs._LABEL
        assert st in rs._READER_CONTRACT


def test_snapshot_smoke_does_not_raise():
    # IO wrapper: reads store/gex; must return a dict and never raise even if data
    # is partial in the test environment.
    out = rs.snapshot(_benign_latest())
    assert isinstance(out, dict)
    assert out["schema"] == "risk_state.v1"
