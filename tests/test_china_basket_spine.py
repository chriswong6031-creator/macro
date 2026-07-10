"""China namespace spine + conviction scale — contract tests."""
from __future__ import annotations

from engine import china_basket_spine as sp
from engine import china_conviction as cv
from lib import config


def _clear_spine_caches():
    for fn in (sp._baskets, sp._ths_baskets, sp.etf_to_basket, sp.ticker_to_basket,
               sp._ticker_names, sp._ths_ticker_names, sp.ths_ticker_to_baskets,
               sp.member_tickers_all):
        fn.cache_clear()


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


# ---- THS concept-board layer (reads live baskets_china_ths/membership.json) - #
def test_ths_ticker_to_baskets_multi_membership():
    t2b = sp.ths_ticker_to_baskets()
    # 603129.SS (春风动力) lives ONLY in THS boards — the "603129-hole" this layer closes
    bids = t2b.get("603129.SS", [])
    assert "thsc309127" in bids and "thsc301248" in bids   # THS Global 50 + Two-Wheelers
    # ...and the curated map must NOT have silently absorbed THS membership
    assert sp.ticker_to_basket().get("603129.SS") is None


def test_ths_basket_members_and_label():
    assert "300474.SZ" in sp.ths_basket_members("ths_ai")
    assert sp.ths_basket_members("nope") == []
    en, zh = sp.ths_basket_label("thsc301248")
    assert en == "Two-Wheelers" and zh == "两轮车"
    assert sp.ths_basket_label("unknown") == ("unknown", "unknown")


def test_ths_no_etf_bridge():
    # THS boards carry no etf_proxy — the ETF bridge stays curated-only
    ths = set(sp.ths_basket_ids())
    assert len(ths) >= 200
    for bids in sp.etf_to_basket().values():
        assert not (set(bids) & ths)


def test_ticker_name_curated_first_ths_fallback():
    assert sp.ticker_name("688981.SS") == "中芯国际"      # curated still wins
    assert sp.ticker_name("603129.SS") == "春风动力"      # THS-only name resolves now
    assert sp.ticker_name("NOPE") is None


def test_member_tickers_all_union():
    uni = sp.member_tickers_all()
    assert "688981.SS" in uni and "603129.SS" in uni
    assert set(sp.ticker_to_basket()) <= uni


def test_ths_degrades_empty_on_missing_data(monkeypatch, tmp_path):
    _clear_spine_caches()
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    try:
        assert sp.ths_ticker_to_baskets() == {}
        assert sp.ths_basket_members("ths_ai") == []
        assert sp.ths_basket_label("x") == ("x", "x")
        assert sp.ths_basket_ids() == []
        assert sp.member_tickers_all() == frozenset()
        assert sp.ticker_name("603129.SS") is None
    finally:
        _clear_spine_caches()


def test_discovery_bundle_universe_covers_ths_members():
    # china_discovery off-desk tagging: a THS-only member is ON-DESK (it lives on the
    # THS boards surface) — the tag must not call it undiscovered
    from engine import china_discovery as disc
    disc._bundle_universe.cache_clear()
    try:
        uni = disc._bundle_universe()
        assert "603129.SS" in uni and "688981.SS" in uni
    finally:
        disc._bundle_universe.cache_clear()


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


def test_leg_weights_earned_from_validation(monkeypatch):
    """Review fix: leg_weights_for reads china_validation's mean_ic/sign_ok/proven (not 'ic'),
    so a proven wrong-sign family is zeroed and the bridge is live (not a no-op)."""
    from engine import china_signal_lab as sl
    # proven wrong-sign valuation family → the 'value' leg must drop to 0
    monkeypatch.setattr(sl, "load_validation", lambda: {
        "valuation": {"mean_ic": -0.05, "t_hac": -3.0, "n_obs": 500, "sign_ok": False, "proven": False}})
    w = sl.leg_weights_for("altdata")
    assert w.get("value", 0) == 0.0
    assert sum(w.values()) > 0.99   # renormalized, never all-zero
