"""Theme/sector SPOTLIGHT tilt — pure geometry + the dominance guarantees that keep it honest.

The contract these tests pin (the whole reason the tilt is safe to ship into the flagship
board): the spotlight RE-ORDERS names that already pass the risk gates, but it can never
(a) rescue an over-extended / cycle-blocked / AVOID name onto the buy list, (b) outrun the
macro / idiosyncratic risk taxes, or (c) inflate a position's suggested size.
"""
from __future__ import annotations

import copy

import pytest

from engine import spotlight as sp
from engine import stock_score as ss


# ---------------------------------------------------------------- pure geometry ----
def test_theme_tilt_direction_and_bounds():
    assert sp.theme_tilt("enter", 80) > 0.7
    assert sp.theme_tilt("accumulate", 65) > 0.3
    assert sp.theme_tilt("hold", 50) == 0.0
    assert sp.theme_tilt("trim", 40) < -0.3
    assert sp.theme_tilt("avoid", 20) < -0.7
    # always clamped to [-1, 1]
    assert -1.0 <= sp.theme_tilt("avoid", 0) <= 1.0
    assert -1.0 <= sp.theme_tilt("enter", 100) <= 1.0
    # neither leg -> None (never read missing as neutral)
    assert sp.theme_tilt(None, None) is None
    # one leg available is enough
    assert sp.theme_tilt("enter", None) == pytest.approx(1.0)
    assert sp.theme_tilt(None, 80) == pytest.approx((80 - 50) / 30.0)


def test_sector_tilt_stage_and_extended_cap():
    assert sp.sector_tilt("leading", False, 70) > 0.5
    assert sp.sector_tilt("improving", False, 50) == pytest.approx(0.3)
    assert sp.sector_tilt("lagging", False, 5) < -0.5
    # an EXTENDED leading sector ("don't chase") can never read better than the cap
    assert sp.sector_tilt("leading", True, 99) <= sp._EXTENDED_CAP
    assert sp.sector_tilt(None, None, None) is None


def test_blend_weights_and_multiplier():
    b = sp.blend(1.0, -0.6)
    assert b["z"] == pytest.approx(sp._W_THEME * 1.0 + sp._W_SECTOR * -0.6)
    assert b["mult"] == pytest.approx(1.0 + sp._MULT_SPAN * b["z"])
    # one channel present -> full weight to it
    assert sp.blend(0.8, None)["z"] == pytest.approx(0.8)
    assert sp.blend(None, -0.4)["z"] == pytest.approx(-0.4)
    # neither -> None
    assert sp.blend(None, None) is None
    # direction labels
    assert sp.blend(1.0, 1.0)["dir"] == "tailwind"
    assert sp.blend(-1.0, -1.0)["dir"] == "out_of_play"
    assert sp.blend(0.0, 0.0)["dir"] == "neutral"


def test_compute_picks_strongest_theme_by_abs_tilt():
    theme_by_id = {
        "hot": {"id": "hot", "name": "Hot", "reco": "enter", "score": 85},
        "cold": {"id": "cold", "name": "Cold", "reco": "avoid", "score": 10},
        "meh": {"id": "meh", "name": "Meh", "reco": "hold", "score": 52},
    }
    # a name in both a strong-enter and a strong-avoid theme -> the LARGER |tilt| wins
    mem = [{"slug": "meh"}, {"slug": "cold"}, {"slug": "hot"}]
    blk = sp.compute(mem, theme_by_id, sector_etf=None, sector_row=None)
    assert blk["theme"]["slug"] in ("hot", "cold")  # whichever is larger in magnitude
    assert abs(blk["theme_z"]) == max(abs(sp.theme_tilt("enter", 85)),
                                      abs(sp.theme_tilt("avoid", 10)))


def test_compute_none_when_no_channel():
    assert sp.compute(None, {}, None, None) is None
    assert sp.compute([{"slug": "missing"}], {}, None, None) is None


def test_compute_skips_pure_neutral_theme():
    # a name in ONLY a pure-hold theme (tilt exactly 0.0) and with no sector must yield NO
    # spotlight (None) — never a z=0 block — so the engine falls back to its legacy tailwind legs
    # instead of being silently pinned to zero.
    theme_by_id = {"meh": {"id": "meh", "name": "Meh", "reco": "hold", "score": 50}}
    assert sp.theme_tilt("hold", 50) == 0.0
    assert sp.compute([{"slug": "meh"}], theme_by_id, None, None) is None
    # but if that same name has a real sector, the sector channel still fires (non-zero)
    blk = sp.compute([{"slug": "meh"}], theme_by_id, "XLU",
                     {"stage": "lagging", "extended": False, "pctile_252d": 5, "name": "Utilities"})
    assert blk is not None and blk["z"] < 0 and blk["theme"] is None


def test_gics_to_etf_covers_drift_variants():
    # the canonical GICS strings + the playbook display-name drift cases must all map
    for s in ("Information Technology", "Technology", "Communication Services",
              "Communications", "Financials", "Consumer Discretionary",
              "Consumer Cyclical", "Health Care", "Healthcare"):
        assert s in sp.GICS_TO_ETF, s


# ---------------------------------------------------------------- integration ----
def _full_rec(**kw) -> dict:
    """A 4-axis-complete US record (selection + entry + tailwind + quality all present),
    so the composite denominator is ~1.0 and the tailwind weight is the canonical 0.10."""
    r = {
        "ticker": "T", "name": "T", "sector": "Information Technology",
        "alpha": 1.2, "rs_z": 1.0, "sue": 1.0,
        "tech": {"pct_vs_200dma": 8.0, "rsi14": 58, "off_52w_high_pct": -6},
        "ladder": {"entry": {"urgency": "building"}},
        "quality_context_z": 0.6,                       # quality axis present
    }
    r.update(kw)
    return r


_CTX = {"as_of": "2026-06-19", "regime": {"calm": 0.7}}


def _prof(spot, rec=None, ctx=None):
    rec = rec or _full_rec()
    return ss.conviction_profile(copy.deepcopy({**rec, "spotlight": spot}), "US",
                                 ctx=ctx or _CTX)


def test_tilt_is_subtle_and_symmetric():
    pu = _prof({"z": 1.0})
    p0 = _prof({"z": 0.0})
    pd_ = _prof({"z": -1.0})
    # monotone
    assert pu["composite_z"] > p0["composite_z"] > pd_["composite_z"]
    # full-tilt swing moves comp_z by only ~+/-0.04 (subtle) and roughly symmetric
    up, dn = pu["composite_z"] - p0["composite_z"], p0["composite_z"] - pd_["composite_z"]
    assert 0.02 <= up <= 0.06, up
    assert 0.02 <= dn <= 0.06, dn
    assert abs(up - dn) < 0.01                          # symmetric about neutral


def test_never_rewards_a_chase():
    # an over-extended NAME (+40% over 200dma) gets its positive tilt neutralized to 0,
    # and is hard-blocked from a buy regardless of how hot its theme is.
    pe = _prof({"z": 1.0, "mult": 1.175, "dir": "tailwind"},
               rec=_full_rec(tech={"pct_vs_200dma": 40.0, "rsi14": 76}))
    assert pe["spotlight"]["z"] == 0.0
    assert pe["spotlight"].get("clamped") == "stock-extended"
    assert pe["cycle_blocked"] is True
    assert pe["size"]["pct"] == 0                        # blocked -> avoid size


def test_cycle_blocked_name_neutralizes_positive_tilt():
    # a DECLINE-state name (cycle-blocked but NOT price-extended) must also have its positive
    # tilt neutralized — a hot theme can't lift a broken tape, even fractionally, above a peer.
    blocked_rec = _full_rec(ladder={"state": "DECLINE", "entry": {"urgency": "building"}},
                            tech={"pct_vs_200dma": 6.0, "rsi14": 45})
    pb = _prof({"z": 1.0, "dir": "tailwind"}, rec=blocked_rec)
    assert pb["cycle_blocked"] is True
    assert pb["spotlight"]["z"] == 0.0
    assert pb["spotlight"].get("clamped") == "cycle-blocked"
    # it must not out-rank an identical DECLINE name that carries NO spotlight
    pb0 = _prof(None, rec=blocked_rec)
    assert pb["composite_z"] <= pb0["composite_z"] + 1e-9


def test_out_of_play_trims_size_but_positive_never_inflates():
    base = _prof(None)["size"]["pct"]
    out = _prof({"z": -0.95})
    up = _prof({"z": 0.95})["size"]["pct"]
    assert out["size"]["pct"] <= base                   # out of play -> down a bucket
    assert up <= base                                   # tailwind never raises size
    # the trim is logged as a transparent risk component
    comps = out["risk"].get("components") or {}
    assert comps.get("out_of_play") is not None


def test_macro_tax_dominates_the_tilt():
    # a full-chase name into a stressed tape, even with a max tailwind, must be taxed BELOW
    # its own untaxed self by far more than the tilt could ever lift it.
    stress = {"as_of": "x", "regime": {"calm": 0.1},
              "risk_overlay": {"score": 1.0, "drivers": ["VIX"]}}
    chase = _full_rec(tech={"pct_vs_200dma": 25.0, "rsi14": 72})
    taxed = ss.conviction_profile(copy.deepcopy({**chase, "spotlight": {"z": 1.0}}), "US", ctx=stress)
    calm = ss.conviction_profile(copy.deepcopy({**chase, "spotlight": {"z": 1.0}}), "US", ctx=_CTX)
    # the macro tax (>=0.2 here) swamps the <=0.04 tilt
    assert calm["composite_z"] - taxed["composite_z"] > 0.1


def test_absent_tilt_is_not_neutral_zero():
    p = _prof(None)
    assert "spotlight" not in (p["axes"]["tailwind"]["present"] or [])
    assert p["spotlight"] is None
    assert "spotlight" in _prof({"z": 0.5})["axes"]["tailwind"]["present"]
