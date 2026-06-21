"""China namespace spine + conviction scale — contract tests."""
from __future__ import annotations

from engine import china_basket_spine as sp
from engine import china_conviction as cv


# ---- spine (reads live membership.json) ------------------------------------ #
def test_etf_maps_to_multiple_baskets():
    e2b = sp.etf_to_basket()
    assert isinstance(e2b, dict)
    # 512400.SS backs BOTH metals and rare-earth — the join must not drop one
    assert set(e2b.get("512400.SS", [])) == {"cn_metals", "cn_rare_earth"}
    assert e2b.get("512800.SS") == ["cn_banks"]
    assert e2b.get("NONEXISTENT.SS") is None


def test_ticker_to_basket_and_members():
    t2b = sp.ticker_to_basket()
    assert t2b.get("688981.SS") == "cn_semis"      # SMIC
    members = sp.basket_members("cn_semis")
    assert "688981.SS" in members and len(members) >= 10
    assert sp.basket_members("nope") == []


def test_basket_label_bilingual():
    en, zh = sp.basket_label("cn_semis")
    assert en == "Semiconductors" and zh == "半导体"
    assert sp.basket_label("unknown") == ("unknown", "unknown")


def test_cn_property_absent():
    # the dead basket flagged in the audit must not exist in the spine
    assert "cn_property" not in sp.basket_ids()
    assert sp.basket_members("cn_property") == []


# ---- conviction scale (pure) ----------------------------------------------- #
def test_to_100_clamp_and_map():
    assert cv.to_100(0.0) == 0 and cv.to_100(1.0) == 100
    assert cv.to_100(0.5) == 50
    assert cv.to_100(2.0) == 100 and cv.to_100(-1.0) == 0
    assert cv.to_100(None) == 0
    assert cv.to_100(3.0, lo=0, hi=6) == 50


def test_band_boundaries():
    assert cv.band(75)[0] == "high" and cv.band(74)[0] == "elevated"
    assert cv.band(55)[0] == "elevated" and cv.band(54)[0] == "moderate"
    assert cv.band(35)[0] == "moderate" and cv.band(34)[0] == "low"
    assert cv.band(0)[0] == "none"
    # bilingual present
    assert cv.band(80)[1] == "High" and cv.band(80)[2] == "高置信"


def test_signed_band():
    assert cv.signed_band(80, 1)[0] == "+high"
    assert cv.signed_band(80, -1)[0] == "-high"
    assert cv.signed_band(0, 1)[0] == "none"          # no side on empty


def test_combine_geometric_penalizes_zero_leg():
    # one strong + two zero legs must stay LOW (geometric-leaning), not ~0.33
    weak = cv.combine(1.0, 0.0, 0.0)
    strong = cv.combine(0.8, 0.8, 0.8)
    assert weak < 0.2 and strong > 0.7
    assert cv.combine(None, None) == 0.0
    assert 0.0 <= cv.combine(0.5, 0.5) <= 1.0
