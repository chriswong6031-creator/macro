"""engine.cross_asset_confirm — does bonds + FX confirm/diverge from equities?

DISPLAY-ONLY leaf. These tests pin: the confirm/diverge/mixed verdict logic, the
equity-blind early-attention flags, graceful degradation when a contract is missing,
the bilingual contract shape, the compact `to_brain` payload, that it NEVER raises,
that it does NOT mutate the input `latest`, and the house invariant that NOTHING in
the scoring path imports it.
"""
from __future__ import annotations

import copy
from pathlib import Path

from engine.cross_asset_confirm import snapshot
from lib import config


# --- synthetic fixtures ------------------------------------------------------
def _bonds(**over):
    b = {
        "as_of": "2026-06-15", "health_score": 86, "health_label": "healthy",
        "cycle_phase": "mid", "verdict_en": "ok",
        "pillars": {
            "curve": {"move_taxonomy": "bull_flattener", "inverted": False, "ntfs": 0.7,
                      "uninversion_alarm": False, "bull_steepener_uninversion": False},
            "credit": {"distress_band": "tight", "direction": "tightening", "hy_oas": 2.7, "ebp": -0.4},
            "real_inflation": {"real_10y": 2.1, "breakeven_5y5y": 2.2, "term_premium": None},
            "stress": {"move_band": "calm", "move_leads_vix": False, "repo_stress": False},
            "cross_asset": {"regime": "breakdown", "hedge_working": False},
            "sovereign": {"frag_state": "calm", "jgb_state": "steep"},
        },
        "drivers_for": {"equities": {"credit_canary": False}},
    }
    for k, v in over.items():
        if k in ("cycle_phase", "health_score", "health_label"):
            b[k] = v
        else:  # nested pillar override: {"credit": {...}}
            b["pillars"].setdefault(k, {}).update(v)
    return b


def _fx(**over):
    f = {"date": "Jun 16, 2026", "regime": "US growth premium", "favored": ["USD"],
         "risk": "risk-on",
         "pairs": {"USDMXN": {"action": "SHORT", "score": -40}, "USDBRL": {"action": "FLAT", "score": -5}}}
    f.update(over)
    return f


def _latest(cycle="mid", roro="risk-on", dd_band="low", **over):
    d = {"quad": "Q1", "quad_name": "Goldilocks", "cycle_tag": cycle,
         "transition_flags": {}, "label": "Q1",
         "conditions": {"risk_appetite": {"roro_state": roro},
                        "drawdown_risk": {"band": dd_band}}}
    d.update(over)
    return d


# --- verdict logic -----------------------------------------------------------
def test_confirm_when_all_agree():
    out = snapshot(_latest(cycle="mid", roro="risk-on", dd_band="low"),
                   bonds=_bonds(cycle_phase="mid"), fx=_fx())
    assert out["verdict"] == "confirm"
    assert out["caution_flags"] == []
    assert out["agree_pct"] == 100


def test_mixed_when_cycle_diverges_but_risk_agrees():
    # bonds late vs equities mid (cycle diverge) but both risk-on, no caution flags
    out = snapshot(_latest(cycle="mid", roro="risk-on", dd_band="low"),
                   bonds=_bonds(cycle_phase="late"), fx=_fx())
    assert out["verdict"] == "mixed"
    assert out["n_diverge"] == 1 and out["n_agree"] == 1


def test_diverge_on_equity_blind_credit_widening():
    # credit widening while equities calm + risk-on -> a real divergence (equity-blind)
    out = snapshot(_latest(cycle="mid", roro="risk-on", dd_band="low"),
                   bonds=_bonds(cycle_phase="mid",
                                credit={"distress_band": "elevated", "direction": "widening"}),
                   fx=_fx())
    assert out["verdict"] == "diverge"
    keys = {f["key"] for f in out["caution_flags"]}
    assert "credit" in keys
    assert any(f["equity_blind"] for f in out["caution_flags"])


def test_confirm_full_risk_off_agreement():
    # bonds + FX + equities ALL cautious -> the cautious read is confirmed (not a divergence)
    out = snapshot(
        _latest(cycle="late", roro="risk-off", dd_band="high"),
        bonds=_bonds(cycle_phase="late",
                     credit={"distress_band": "distress", "direction": "widening"},
                     stress={"move_band": "crisis", "move_leads_vix": True, "repo_stress": False}),
        fx=_fx(risk="risk-off", regime="Risk-off haven bid"))
    assert out["verdict"] == "confirm"
    assert out["agree_pct"] == 100
    # flags fire but are NOT equity-blind (equities already cautious)
    assert out["caution_flags"]
    assert not any(f["equity_blind"] for f in out["caution_flags"])


def test_em_fx_stress_flag_fires_on_usd_bid_vs_em():
    out = snapshot(_latest(),
                   bonds=_bonds(cycle_phase="mid"),
                   fx=_fx(pairs={"USDMXN": {"action": "LONG", "score": 45},
                                 "USDBRL": {"action": "LONG", "score": 30}}))
    assert any(f["key"] == "em_fx_stress" for f in out["caution_flags"])


def test_em_fx_stress_fires_on_strong_long_band():
    # the STRONGEST USD-bid-vs-EM band must also fire (regression: exact "LONG" match dropped it)
    out = snapshot(_latest(),
                   bonds=_bonds(cycle_phase="mid"),
                   fx=_fx(pairs={"USDMXN": {"action": "STRONG LONG", "score": 75},
                                 "USDBRL": {"action": "STRONG LONG", "score": 68}}))
    assert any(f["key"] == "em_fx_stress" for f in out["caution_flags"])


def _cycle_leg(out):
    return next((l for l in out["legs"] if l["key"] == "cycle"), None)


def test_cycle_recession_is_most_adverse():
    # bonds flashing RECESSION while equities only mid/late = the MOST bearish divergence
    # (the case the whole leg exists to surface) -> cycle leg must lean BEAR, not BULL.
    for eq in ("mid", "late"):
        leg = _cycle_leg(snapshot(_latest(cycle=eq), bonds=_bonds(cycle_phase="recession"), fx=_fx()))
        assert leg is not None and leg["dir"] == -1 and leg["tone"] == "down", eq
    # converse: equities in Recession while bonds only late = bonds the more benign read -> BULL
    leg = _cycle_leg(snapshot(_latest(cycle="late", label="Q4/Recession"),
                              bonds=_bonds(cycle_phase="late"), fx=_fx()))
    assert leg is not None and leg["dir"] == 1


def test_cycle_early_mid_late_ordering_preserved():
    # bonds late vs equities mid = bonds further along (mild caution) -> BEAR (the live case)
    leg = _cycle_leg(snapshot(_latest(cycle="mid"), bonds=_bonds(cycle_phase="late"), fx=_fx()))
    assert leg["dir"] == -1
    # bonds early vs equities late = bonds earlier/benign -> BULL
    leg = _cycle_leg(snapshot(_latest(cycle="late"), bonds=_bonds(cycle_phase="early"), fx=_fx()))
    assert leg["dir"] == 1


# --- graceful degradation ----------------------------------------------------
def test_unknown_when_no_contracts():
    out = snapshot(_latest(), bonds={}, fx={})
    assert out["verdict"] == "unknown"


def test_never_raises_on_garbage():
    for bad in (None, {}, {"conditions": None}, {"cycle_tag": 123}):
        out = snapshot(bad, bonds=_bonds(), fx=_fx())
        assert isinstance(out, dict) and "verdict" in out
    # garbage contracts
    assert isinstance(snapshot(_latest(), bonds={"pillars": "nope"}, fx={"pairs": 7}), dict)


def test_does_not_mutate_latest():
    lat = _latest()
    before = copy.deepcopy(lat)
    snapshot(lat, bonds=_bonds(), fx=_fx())
    assert lat == before


# --- contract shape ----------------------------------------------------------
def test_bilingual_and_to_brain_contract():
    out = snapshot(_latest(cycle="mid"), bonds=_bonds(cycle_phase="late",
                   credit={"distress_band": "elevated", "direction": "widening"}), fx=_fx())
    for k in ("headline_en", "headline_zh", "verdict_zh", "note_en", "note_zh",
              "confidence", "cycle", "to_brain", "legs", "caution_flags"):
        assert k in out, f"missing {k}"
    for leg in out["legs"]:
        assert {"detail_en", "detail_zh", "tone", "dir"} <= set(leg)
    for fl in out["caution_flags"]:
        assert {"en", "zh", "severity", "owner", "lead", "equity_blind"} <= set(fl)
    tb = out["to_brain"]
    assert {"verdict", "cycle", "leading_caution_votes", "caution_flags"} <= set(tb)


def test_runs_on_real_contracts_if_present():
    root = config.ROOT
    if (root / "data" / "bonds" / "bond_health.json").exists():
        import json
        lat = json.loads((root / "data" / "regime" / "latest.json").read_text())
        out = snapshot(lat)
        assert out["verdict"] in ("confirm", "diverge", "mixed", "unknown")


# --- house invariant: NEVER scored ------------------------------------------
def test_not_imported_by_scoring_path():
    """The scoring path (axes / regime / conditions-MRS) must not import this leaf —
    it is display-only and must never feed a score."""
    eng = Path(config.ROOT) / "engine"
    for mod in ("axes.py", "regime.py", "conditions.py", "transition.py"):
        src = (eng / mod).read_text()
        assert "cross_asset_confirm" not in src, f"{mod} must not import cross_asset_confirm"
