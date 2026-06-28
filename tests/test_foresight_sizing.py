"""engine.foresight_sizing — posture bands + staged exit + portfolio concentration.
Encodes the HBM/ARK lessons: PRECIPICE sizes small, the flush is the ADD, glut+crowding
forces a de-risk. Pure / display-only.
"""
from __future__ import annotations

from engine import foresight_sizing as fz


def _row(**kw):
    base = {"stage": "WATCH", "bottleneck_band": "AWAITING_DATA", "score": 40,
            "revision_breadth": 0.0, "entry_ready": False, "glut_band": None,
            "demand_band": None}
    base.update(kw)
    return base


def test_precipice_physical_is_a_small_starter():
    r = _row(stage="PRECIPICE", bottleneck_band="TIGHT", score=80, revision_breadth=0.05)
    p = fz._posture(r)
    assert p["band"] == "STARTER" and p["derisk"] is False
    assert fz._size_mult(r, p) == 0.45            # capped small despite an 80 score (right but early)


def test_entry_ready_is_the_add_full_size():
    r = _row(stage="BROADENING", bottleneck_band="TIGHT", score=70, entry_ready=True)
    p = fz._posture(r)
    assert p["band"] == "ADD"
    assert fz._size_mult(r, p) == 0.70            # the flush -> full conviction allowed


def test_glut_risk_forces_exit():
    r = _row(stage="GLUT-RISK", bottleneck_band="LOOSE", score=40, revision_breadth=0.6)
    p = fz._posture(r)
    assert p["band"] == "EXIT" and p["derisk"] is True
    assert fz._size_mult(r, p) == 0.0


def test_forming_glut_while_crowded_forces_trim():
    r = _row(stage="BROADENING", bottleneck_band="TIGHT", score=65,
             glut_band="GLUT_FORMING", revision_breadth=0.8)
    p = fz._posture(r)
    assert p["band"] == "TRIM" and p["derisk"] is True


def test_rerating_holds_no_add():
    r = _row(stage="RE-RATING", bottleneck_band="TIGHT", score=60, revision_breadth=0.8)
    p = fz._posture(r)
    assert p["band"] == "HOLD" and p["derisk"] is False


def test_text_only_precipice_is_watch_capped():
    r = _row(stage="PRECIPICE", bottleneck_band="AWAITING_DATA", score=50,
             score_detail={"physical_confirmed": False})
    p = fz._posture(r)
    assert p["band"] == "WATCH"
    assert fz._size_mult(r, p) <= fz.TEXT_ONLY_SIZE_CAP


def test_portfolio_flags_capex_concentration():
    rows = [
        _row(stage="PRECIPICE", demand_band="ACCELERATING", score=75, size_detail={"derisk": False}),
        _row(stage="BROADENING", demand_band="STEADY", score=60, size_detail={"derisk": False}),
        _row(stage="WATCH", demand_band=None, score=30, size_detail={"derisk": False}),
    ]
    port = fz._portfolio(rows)
    assert port["n_constructive"] == 2 and port["n_capex_linked"] == 2
    assert port["concentration_flag"] is True


def test_annotate_adds_fields_and_is_none_safe():
    assert fz.annotate_sizing(None) is None
    assert fz.annotate_sizing({"themes": []}) == {"themes": []}
    cas = {"themes": [_row(stage="PRECIPICE", bottleneck_band="TIGHT", score=80, revision_breadth=0.05)]}
    out = fz.annotate_sizing(cas)
    r = out["themes"][0]
    assert r["size_band"] == "STARTER" and r["derisk"] is False and "size_mult" in r
    assert out["sizing"]["n_constructive"] == 1
