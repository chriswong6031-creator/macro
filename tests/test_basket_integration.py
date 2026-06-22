"""Tests for the narrative-basket → stock scored integration (the validated channel).

Invariants:
  * a name whose primary narrative basket is BELOW its long-term trend (or fading /
    deteriorating) is SIZED DOWN via a subtract-only risk component + a caution — never
    re-ranked (the absolute-trend gate is the one backtested edge; momentum rank is not).
  * a healthy (above-trend, not-crowded) basket adds NO de-risk.
  * the unified action board buckets baskets by reco and flags the validated risk side.
"""
import json

from engine import stock_score as ss


def _rec(basket_alloc=None, **kw):
    base = {
        "ticker": "TST", "name": "Test Co", "sector": "Technology",
        "alpha": 2.0, "alpha_entry": "pullback",
        "ladder": {"state": "RALLY ON", "label": "UPTREND", "dir": "up",
                   "eq_dir": "up", "entry": {"urgency": "now"}},
        "tech": {"off_52w_high_pct": -6.0, "rsi14": 55.0},
        "sector_rs": {"pct": 80.0},
        "factor": {"value": 0.5, "profitability": 0.8, "quality": 0.6, "low_vol": 0.2},
        "sue": 1.5, "insider_bps": 20.0, "accounting": {"verdict": "clean"},
    }
    if basket_alloc is not None:
        base["basket_alloc"] = basket_alloc
    base.update(kw)
    return base


# --- _basket_risk unit -------------------------------------------------------
def test_below_trend_basket_full_haircut():
    hc, cau = ss._basket_risk({"basket_alloc":
                               {"name": "Non-AI Software", "above_trend": False,
                                "eligible": False, "label": "deteriorating"}})
    assert hc == ss._BASKET_RISK_MAX
    assert cau and "below its long-term trend" in cau["en"]


def test_deteriorating_above_trend_partial():
    hc, _ = ss._basket_risk({"basket_alloc":
                             {"name": "X", "above_trend": True, "eligible": True,
                              "label": "deteriorating"}})
    assert 0 < hc < ss._BASKET_RISK_MAX


def test_crowded_small_cap():
    hc, _ = ss._basket_risk({"basket_alloc":
                             {"name": "X", "above_trend": True, "eligible": True,
                              "label": "dominant", "crowded": True}})
    assert 0 < hc < ss._BASKET_RISK_MAX * 0.5


def test_healthy_basket_no_derisk():
    hc, cau = ss._basket_risk({"basket_alloc":
                               {"name": "Memory", "above_trend": True, "eligible": True,
                                "label": "dominant"}})
    assert hc == 0.0 and cau is None
    assert ss._basket_risk({})[0] == 0.0


# --- conviction_profile integration -----------------------------------------
def test_below_trend_basket_sizes_down_and_warns():
    prof = ss.conviction_profile(
        _rec(basket_alloc={"name": "Non-AI Software", "above_trend": False,
                           "eligible": False, "label": "deteriorating", "slug": "non_ai_software"}),
        "US")
    comps = (prof.get("risk") or {}).get("components") or {}
    assert comps.get("basket_trend") == ss._BASKET_RISK_MAX
    assert any("narrative basket" in c.lower() for c in prof.get("cautions") or [])
    # surfaced for Mastermind / display
    assert (prof.get("basket_alloc") or {}).get("slug") == "non_ai_software"


def test_healthy_basket_no_basket_trend_component():
    prof = ss.conviction_profile(
        _rec(basket_alloc={"name": "Memory", "above_trend": True, "eligible": True,
                           "label": "dominant"}),
        "US")
    comps = (prof.get("risk") or {}).get("components") or {}
    assert "basket_trend" not in comps


def test_no_basket_alloc_is_inert():
    prof = ss.conviction_profile(_rec(), "US")
    comps = (prof.get("risk") or {}).get("components") or {}
    assert "basket_trend" not in comps
    assert prof.get("basket_alloc") is None


# --- unified action board ----------------------------------------------------
def test_basket_action_items_buckets_and_validates(tmp_path):
    import scripts.build_site as bs
    bd = tmp_path / "basketdata"; bd.mkdir()
    (bd / "baskets.json").write_text(json.dumps({"theme_intel": {"themes": [
        {"id": "memory_storage", "name": "Memory", "reco": "accumulate",
         "reco_en": "ACCUMULATE", "score": 80, "signal_strength": {"grade": "descriptive"}},
        {"id": "non_ai_software", "name": "Non-AI Software", "reco": "avoid",
         "reco_en": "AVOID", "score": 30, "signal_strength": {"grade": "backtested"}},
        {"id": "uranium", "name": "Uranium", "reco": "enter", "reco_en": "ENTER", "score": 60},
    ]}}))
    ad = tmp_path / "allocationdata"; ad.mkdir()
    (ad / "allocation.json").write_text(json.dumps({
        "ranks": [{"id": "memory_storage", "rank": 1, "eligible": True,
                   "gate": {"above_200dma": True}, "durability": {"bar": 0.8}}],
        "allocation": {"weights": [{"id": "memory_storage", "weight": 0.125}]}}))
    b = bs.basket_action_items(tmp_path)
    assert [x["name"] for x in b["buy_now"]] == ["Memory"]
    assert b["buy_now"][0]["book_wt"] == 0.125 and b["buy_now"][0]["validated"] is False
    assert [x["name"] for x in b["buy_soon"]] == ["Uranium"]
    assert b["avoid"][0]["name"] == "Non-AI Software" and b["avoid"][0]["validated"] is True
    assert all(x["kind"] == "theme" for lane in b.values() for x in lane)


def test_basket_action_items_graceful_without_files(tmp_path):
    b = __import__("scripts.build_site", fromlist=["x"]).basket_action_items(tmp_path)
    assert b == {"buy_now": [], "buy_soon": [], "take_profits": [], "hold": [], "avoid": []}
