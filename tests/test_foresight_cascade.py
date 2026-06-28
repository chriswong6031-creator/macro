"""engine.foresight_cascade — the per-theme STAGE machine (T1 x T4). Verifies the stage
logic on the four canonical states and that it ranks by edge remaining (PRECIPICE first)
and degrades honestly when a tier is missing.
"""
from __future__ import annotations

from engine import foresight_cascade as fc


def test_precipice_tight_plus_flat():
    bn = {"band": "SOLD_OUT", "tightness": 1.6, "regime": True}
    rv = {"breadth": 0.05, "level_state": "FLAT_LOW"}
    stage, _ = fc._stage(bn, rv)
    assert stage == "PRECIPICE"          # the June-2024 HBM state


def test_broadening_tight_plus_rising():
    bn = {"band": "TIGHT", "tightness": 0.9, "regime": True}
    rv = {"breadth": 0.3, "level_state": "POSITIVE"}
    stage, _ = fc._stage(bn, rv)
    assert stage == "BROADENING"


def test_rerating_tight_but_already_broad():
    bn = {"band": "TIGHT", "tightness": 0.9}
    rv = {"breadth": 0.8, "level_state": "POSITIVE"}
    stage, _ = fc._stage(bn, rv)
    assert stage == "RE-RATING"          # runway maturing -> do not chase


def test_glut_risk_loose_but_estimates_high():
    bn = {"band": "LOOSE", "tightness": -0.6}
    rv = {"breadth": 0.4, "level_state": "POSITIVE"}
    stage, _ = fc._stage(bn, rv)
    assert stage == "GLUT-RISK"


def test_revisions_only_flags_lateness():
    stage, _ = fc._stage(None, {"breadth": 0.8, "level_state": "POSITIVE"})
    assert stage == "RE-RATING"
    stage2, _ = fc._stage(None, {"breadth": 0.02, "level_state": "FLAT_LOW"})
    assert stage2 == "WATCH"


def test_ranks_precipice_first():
    bottleneck = {"themes": {
        "a": {"name": "A", "band": "TIGHT", "tightness": 0.9, "regime": True},
        "b": {"name": "B", "band": "TIGHT", "tightness": 0.9},
    }}
    revisions = {"themes": {
        "a": {"name": "A", "breadth": 0.05, "level_state": "FLAT_LOW"},   # PRECIPICE
        "b": {"name": "B", "breadth": 0.8, "level_state": "POSITIVE"},    # RE-RATING
    }}
    out = fc.compute_foresight_cascade(bottleneck=bottleneck, revisions=revisions,
                                       demand={"themes": {}}, write_ledger=False)
    assert out["themes"][0]["theme"] == "a"
    assert out["themes"][0]["stage"] == "PRECIPICE"


def test_entry_overlay():
    # thesis stage + active dislocation -> entry window
    ready, _ = fc._entry("PRECIPICE", {"active": True, "verdict": "buyable_washout"})
    assert ready is True
    # thesis stage but calm market -> wait for the flush
    ready2, note2 = fc._entry("BROADENING", {"active": False, "verdict": "calm"})
    assert ready2 is False and "await" in note2.lower()
    # late stage never an entry, even on a flush
    ready3, _ = fc._entry("RE-RATING", {"active": True})
    assert ready3 is False


def test_demand_confirms_in_rationale():
    bottleneck = {"themes": {"a": {"name": "A", "band": "TIGHT", "tightness": 0.9, "regime": True}}}
    revisions = {"themes": {"a": {"name": "A", "breadth": 0.05, "level_state": "FLAT_LOW"}}}
    demand = {"themes": {"a": {"name": "A", "demand_band": "ACCELERATING",
                               "capex_yoy": 69.0, "strength": "direct"}}}
    out = fc.compute_foresight_cascade(bottleneck=bottleneck, revisions=revisions,
                                       demand=demand, glut={"themes": {}}, write_ledger=False)
    r = out["themes"][0]
    assert r["stage"] == "PRECIPICE"
    assert r["demand_band"] == "ACCELERATING"
    assert "capex" in r["rationale"].lower()


def test_guidance_confirms_without_changing_stage():
    # T3 guidance is a LEADING confirmer on the rationale + a score input, never a
    # stage-changer: a BROAD-RAISE on a PRECIPICE theme stays PRECIPICE but lifts the
    # acceleration axis and annotates the rationale.
    bottleneck = {"themes": {"a": {"name": "A", "band": "TIGHT", "tightness": 0.9, "regime": True}}}
    revisions = {"themes": {"a": {"name": "A", "breadth": 0.05, "level_state": "FLAT_LOW"}}}
    guidance = {"themes": {"a": {"name": "A", "guidance_band": "BROAD-RAISE",
                                 "n_raisers": 3, "n_cutters": 0, "net": 3}}}
    out = fc.compute_foresight_cascade(bottleneck=bottleneck, revisions=revisions,
                                       demand={"themes": {}}, glut={"themes": {}},
                                       guidance=guidance, write_ledger=False)
    r = out["themes"][0]
    assert r["stage"] == "PRECIPICE"
    assert r["guidance_band"] == "BROAD-RAISE"
    assert r["guidance_raisers"] == 3
    assert "pre-signaling" in r["rationale"]
    assert r["score_detail"]["axes"]["acceleration"] >= 0.5   # T3 raise lifts acceleration


def test_altdata_confirmers_inverse_to_breadth():
    # leading alt-data confirmers reinforce an EARLY (thesis-stage) theme's rationale + score,
    # but on a LATE (broad-revisions) theme they are crowding -> NOT added to the rationale.
    bn = {"themes": {"a": {"name": "A", "band": "TIGHT", "tightness": 0.9, "regime": True}}}
    conf = {"themes": {"a": {"name": "A", "n_leading": 2, "leading_members": ["MU", "WDC"],
                             "summary": "2 insider clusters · 1 gov-award accel"}}}
    early = fc.compute_foresight_cascade(
        bottleneck=bn, revisions={"themes": {"a": {"name": "A", "breadth": 0.05, "level_state": "FLAT_LOW"}}},
        demand={"themes": {}}, glut={"themes": {}}, guidance={"themes": {}}, confirmers=conf, write_ledger=False)
    r = early["themes"][0]
    assert r["stage"] == "PRECIPICE" and r["n_altdata_leading"] == 2
    assert "alt-data confirms" in r["rationale"]

    late = fc.compute_foresight_cascade(
        bottleneck=bn, revisions={"themes": {"a": {"name": "A", "breadth": 0.9, "level_state": "POSITIVE"}}},
        demand={"themes": {}}, glut={"themes": {}}, guidance={"themes": {}}, confirmers=conf, write_ledger=False)
    r2 = late["themes"][0]
    assert r2["stage"] == "RE-RATING"
    assert "alt-data confirms" not in r2["rationale"]              # crowding, not a tell, when broad
    assert r["score_detail"]["axes"]["acceleration"] > r2["score_detail"]["axes"]["acceleration"]


def test_glut_overrides_to_exit_risk():
    # a forming glut while estimates are still broad -> GLUT-RISK (exit clock) takes precedence
    bottleneck = {"themes": {"a": {"name": "A", "band": "TIGHT", "tightness": 0.9}}}
    revisions = {"themes": {"a": {"name": "A", "breadth": 0.8, "level_state": "POSITIVE"}}}
    glut = {"themes": {"a": {"name": "A", "band": "GLUT_FORMING", "glut_score": 0.8}}}
    out = fc.compute_foresight_cascade(bottleneck=bottleneck, revisions=revisions,
                                       demand={"themes": {}}, glut=glut, write_ledger=False)
    r = out["themes"][0]
    assert r["stage"] == "GLUT-RISK"
    assert r["glut_band"] == "GLUT_FORMING"
    assert "exit clock" in r["rationale"]
