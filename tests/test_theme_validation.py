"""Real-activity validation overlay — byte-stable core + bounded one-slot promotion."""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import narrative_rotation as nr
from engine import theme_validation as tv


def _prep(bid, i):
    lvl = pd.Series(np.linspace(100.0, 100.0 + i, 60),
                    index=pd.date_range("2026-01-01", periods=60, freq="D"))
    return {"id": bid, "name": bid, "name_zh": bid, "category": "x", "parent": bid, "lvl": lvl}


def _preps(n=5):
    return [_prep(f"t{i}", i) for i in range(1, n + 1)]


def _ranks(n=5, upgrades=(), annotate=False):
    r = {}
    for i in range(n):
        bid = f"t{i + 1}"
        r[bid] = {"rank": i + 1, "eligible": True, "score": round(5.0 - i, 3)}
        if bid in upgrades:
            r[bid]["val_upgrade"] = True
        elif annotate:
            r[bid].update({"val_upgrade": False, "val_state": "quiet", "val_z": 0.1})
    return r


def _alloc(preps, ranks):
    return nr.allocate(preps, ranks, crowd={}, rot={}, bench_close=None)


def _core(a):
    return [(w["id"], w["weight"], w["rank"]) for w in a["weights"]], a["cash"], a["n_held"]


# --- byte-stable core ----------------------------------------------------------
def test_overlay_keys_do_not_change_the_book():
    preps = _preps()
    plain = _alloc(preps, _ranks())                       # no val keys at all
    annotated = _alloc(preps, _ranks(annotate=True))      # val keys present, no upgrades
    assert _core(plain) == _core(annotated)               # weights/cash/n_held byte-identical
    assert [w["id"] for w in plain["weights"]] == ["t1", "t2", "t3", "t4"]


# --- bounded one-slot promotion ------------------------------------------------
def test_val_upgrade_promotes_exactly_one_slot():
    a = _alloc(_preps(), _ranks(upgrades={"t5"}))
    ids = {w["id"] for w in a["weights"]}
    assert ids == {"t1", "t2", "t3", "t5"}                # t5 promoted in, t4 displaced
    t5 = next(w for w in a["weights"] if w["id"] == "t5")
    assert t5["rank"] == 5                                # price-scored RANK unchanged — only inclusion


def test_val_upgrade_cannot_leapfrog_more_than_one():
    # even upgraded, rank-5 cannot vault above rank-3 — it swaps with rank-4 only
    a = _alloc(_preps(), _ranks(upgrades={"t5"}))
    assert "t3" in {w["id"] for w in a["weights"]}        # rank-3 never displaced by a rank-5 upgrade


def test_two_upgrades_stay_bounded():
    # t5 and t6 both upgraded; each moves exactly ONE slot, so only t5 (5->4) reaches the
    # top-4 book — t6 (6->5) stays outside. The bound holds even with multiple upgrades.
    a = _alloc(_preps(6), _ranks(6, upgrades={"t5", "t6"}))
    ids = {w["id"] for w in a["weights"]}
    assert ids == {"t1", "t2", "t3", "t5"} and "t6" not in ids


# --- the overlay itself --------------------------------------------------------
def test_apply_validation_flags_diverging_eligible_themes():
    radar = {"flags": [
        {"basket": "defense", "state": "POSITIVE_DIVERGENCE", "divergence": 1.2},
        {"basket": "nuclear", "state": "POSITIVE_DIVERGENCE", "divergence": 0.3},   # below threshold
        {"basket": "crit", "state": "NEGATIVE_DIVERGENCE", "divergence": -1.0}]}
    ranks = {"defense": {"eligible": True}, "nuclear": {"eligible": True},
             "crit": {"eligible": True}, "x": {"eligible": True}}
    tv.apply_validation(ranks, "us", radar=radar)
    assert ranks["defense"]["val_upgrade"] is True
    assert ranks["nuclear"]["val_upgrade"] is False       # divergence < VAL_UP_THRESH
    assert ranks["crit"]["val_upgrade"] is False and ranks["crit"]["val_state"] == "fading"
    assert ranks["x"]["val_state"] == "no_data"


def test_validation_never_upgrades_ineligible():
    radar = {"flags": [{"basket": "d", "state": "POSITIVE_DIVERGENCE", "divergence": 2.0}]}
    ranks = {"d": {"eligible": False}}
    tv.apply_validation(ranks, "us", radar=radar)
    assert ranks["d"]["val_upgrade"] is False             # never relaxes the absolute-trend gate


def test_validation_does_not_touch_score_or_rank():
    radar = {"flags": [{"basket": "d", "state": "POSITIVE_DIVERGENCE", "divergence": 2.0}]}
    ranks = {"d": {"eligible": True, "score": 1.23, "rank": 1}}
    tv.apply_validation(ranks, "us", radar=radar)
    assert ranks["d"]["score"] == 1.23 and ranks["d"]["rank"] == 1


def test_non_us_region_is_a_noop():
    ranks = {"d": {"eligible": True}}
    tv.apply_validation(ranks, "china",
                        radar={"flags": [{"basket": "d", "state": "POSITIVE_DIVERGENCE", "divergence": 2}]})
    assert "val_upgrade" not in ranks["d"]


def test_empty_radar_is_a_noop():
    ranks = {"d": {"eligible": True, "rank": 1, "score": 1.0}}
    tv.apply_validation(ranks, "us", radar={})            # no flags -> early return, ranks untouched
    assert ranks == {"d": {"eligible": True, "rank": 1, "score": 1.0}}
