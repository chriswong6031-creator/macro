"""Theme Rotation Desk scorer (engine.theme_scoring) — transparent, honest legs.

Verify the pure scoring legs behave (trend / breadth / impulse / macro / crowding), the
lifecycle LABEL logic separates dominant / emerging / fading / deteriorating, the
RECOMMENDATION verb accounts for dominant-topping (→ TRIM) vs emerging (→ ENTER), and the
full compute_theme_intel payload — when the price caches are present — has the contract the
page + alert engine read. Everything degrades gracefully; nothing here hits the network.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import theme_scoring as ts


# --------------------------------------------------------------------- legs
def test_impulse_leg_counts_up_and_down_3pct():
    idx = pd.date_range("2025-01-01", periods=5, freq="B")
    cols = ["A", "B", "C", "D"]
    closes = pd.DataFrame(1.0, index=idx, columns=cols)
    rets = pd.DataFrame(0.0, index=idx, columns=cols)
    rets.iloc[-1] = [0.05, 0.04, -0.06, 0.0]      # 2 up≥3%, 1 down≥3%, 1 flat
    leg, d = ts._impulse_leg(rets, closes, len(idx) - 1)
    assert d["up3"] == 2 and d["down3"] == 1 and d["n"] == 4
    assert d["net"] == 1
    assert leg > 0                                # net positive impulse


def test_breadth_leg_all_above_ma_and_new_highs():
    idx = pd.date_range("2024-01-01", periods=260, freq="B")
    ramp = np.linspace(1.0, 2.0, 260)            # steadily rising → above MAs, fresh highs
    mc = pd.DataFrame({"A": ramp, "B": ramp * 1.01, "C": ramp * 0.99}, index=idx)
    leg, d = ts._breadth_leg(mc, len(idx) - 1, {"broadening_z": 0.0})
    assert d["pct50"] == 1.0 and d["pct200"] == 1.0
    assert d["nh"] == 3 and d["nl"] == 0
    assert leg > 0.5                              # broad + new highs → strong positive leg


def test_trend_leg_positive_with_outperformance():
    perf = {"5d": {"rel": 0.02}, "20d": {"rel": 0.06}, "60d": {"rel": 0.10}}
    leg, why = ts._trend_leg(perf, {"accel_z": 1.2})
    assert leg > 0
    assert any("20d" in w for w in why)
    assert any("accel" in w.lower() for w in why)
    assert any("vs S&P" in w for w in why)                    # default benchmark label


def test_trend_leg_reason_uses_region_benchmark_label():
    # the 20d reason names the region's benchmark, not a hardcoded S&P (China bug fix)
    perf = {"20d": {"rel": 0.06}}
    _, why = ts._trend_leg(perf, {}, "CSI 300")
    assert any("vs CSI 300" in w for w in why)
    assert not any("S&P" in w for w in why)


def test_macro_leg_uses_prior_and_sector_rs():
    # mag7 maps to XLK; a pro-growth state + strong home-sector RS → positive macro leg
    mc = {"state": {"growth": 0.5, "rates": 0.3, "inflation": 0.1, "riskon": 0.9},
          "sector_rs": {"XLK": 0.9}, "display": {"fed_dir": "easing", "nfci_state": "loose"}}
    val, why = ts._macro_leg("mag7", mc)
    assert val > 0.3
    assert any("sector" in w.lower() for w in why)        # the live-RS confirmer fired
    # an unknown basket with no prior and no proxy → neutral, no crash
    val2, _ = ts._macro_leg("does_not_exist", {"state": mc["state"], "sector_rs": {},
                                               "display": mc["display"]})
    assert val2 == 0.0


def test_crowding_penalty_rises_with_extension_and_narrow():
    base, _ = ts._crowding_pen({"rs_pctile": 0.5}, {"breadth": "broad"}, None)
    hot, why = ts._crowding_pen({"rs_pctile": 0.98}, {"breadth": "narrow"},
                                {"crowding_z": 1.5})
    assert base == 0.0
    assert hot > base and hot <= 1.0
    assert why                                    # carries reasons


# --------------------------------------------------------------- labels / recos
def _fp(accel=0.0, rs=0.5):
    return {"accel_z": accel, "rs_pctile": rs}


def test_label_dominant_then_accumulate():
    label = ts._label(70, _fp(0.6, 0.55), {"20d": {"rel": 0.06}},
                      {"pct50": 0.7, "nh": 5, "nl": 0}, 0.02)
    assert label == "dominant"
    assert ts._reco(label, 0.3, 0.2, _fp(0.6, 0.55)) == "accumulate"
    # extended dominant → HOLD, don't chase
    assert ts._reco("dominant", 0.3, 0.2, _fp(0.0, 0.9)) == "hold"


def test_label_fading_then_trim():
    label = ts._label(58, _fp(-0.5, 0.85), {"20d": {"rel": 0.05}},
                      {"pct50": 0.55, "nh": 1, "nl": 1}, -0.02)
    assert label == "fading"
    assert ts._reco(label, 0.1, 0.4, _fp(-0.5, 0.85)) == "trim"


def test_label_deteriorating_then_avoid():
    label = ts._label(35, _fp(-0.7, 0.4), {"20d": {"rel": -0.03}},
                      {"pct50": 0.3, "nh": 0, "nl": 4}, -0.03)
    assert label == "deteriorating"
    assert ts._reco(label, 0.0, 0.1, _fp(-0.7, 0.4)) == "avoid"


def test_label_emerging_then_enter_unless_macro_headwind():
    label = ts._label(55, _fp(0.6, 0.5), {"20d": {"rel": 0.01}},
                      {"pct50": 0.55, "nh": 2, "nl": 0}, 0.01)
    assert label == "emerging"
    assert ts._reco(label, 0.1, 0.2, _fp(0.6, 0.5)) == "enter"      # macro ok → ENTER
    assert ts._reco(label, -0.5, 0.2, _fp(0.6, 0.5)) == "hold"      # macro against → HOLD


def test_ret_rel_is_basket_minus_bench():
    idx = pd.date_range("2025-01-01", periods=30, freq="B")
    lvl = pd.Series(np.linspace(1.0, 1.30, 30), index=idx)          # +30% over window
    bench = pd.Series(np.linspace(1.0, 1.10, 30), index=idx)        # +10%
    rr = ts._ret_rel(lvl, bench, 29, 20)
    assert rr is not None and rr > 0                               # basket beat bench
    assert ts._ret_rel(lvl, bench, 5, 20) is None                  # not enough lookback


# --------------------------------------------------------------- integration smoke
def test_compute_theme_intel_contract_when_data_present():
    ti = ts.compute_theme_intel()
    if ti is None:                                                  # caches absent in CI shard
        return
    for k in ("as_of", "bench_label", "bench_label_zh", "disclaimer", "macro_context",
              "themes", "rotation_5d", "impulse_scorecard", "recommendations", "weights"):
        assert k in ti
    assert ti["bench_label"] == "S&P 500"                      # US default
    assert ti["themes"], "expected at least one scored theme"
    th = ti["themes"][0]
    assert 0 <= th["score"] <= 100 and th["rank"] == 1
    assert th["label"] in ts.LABELS and th["reco"] in ts.RECOS
    assert set(th["components"]) == {"trend", "breadth", "impulse", "macro", "crowding"}
    sc = ti["impulse_scorecard"]
    assert sc["net"] == sc["up3"] - sc["down3"]
    assert sc["net_hl"] == sc["nh"] - sc["nl"]
    # the click-to-open scorecard rosters: counts match the named lists (capped at 80)
    for cnt, key, has_ret in ((sc["up3"], "up_names", True), (sc["down3"], "down_names", True),
                              (sc["nh"], "nh_names", False), (sc["nl"], "nl_names", False)):
        names = sc[key]
        assert len(names) == min(cnt, 80)
        for row in names:
            assert "t" in row and "tid" in row                # ticker + home-theme id (for links)
            assert ("r" in row) == has_ret                    # impulse rows carry the daily return
