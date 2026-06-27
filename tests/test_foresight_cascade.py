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
    out = fc.compute_foresight_cascade(bottleneck=bottleneck, revisions=revisions, write_ledger=False)
    assert out["themes"][0]["theme"] == "a"
    assert out["themes"][0]["stage"] == "PRECIPICE"
