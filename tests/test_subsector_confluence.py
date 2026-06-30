"""Tests for the Subsector Confluence desk (engine/subsector_confluence.py).

Pure-logic tests (classification, the double-gate factor, the funnel) run with no data.
A guarded integration test exercises the real composition (basket index -> cascade ->
regime) on one S&P sub-industry IF the OHLCV store is present.
"""
from __future__ import annotations

import pytest

from engine import subsector_confluence as sc


# ----------------------------------------------------------------- pure logic ----

def test_slug():
    assert sc._slug("Software - Infrastructure") == "software-infrastructure"
    assert sc._slug("Diagnostics & Research") == "diagnostics-research"
    assert sc._slug("REIT - Healthcare Facilities") == "reit-healthcare-facilities"
    assert sc._slug("") == "x"


def test_seed_members_dedupes_and_shapes():
    m = sc._seed_members(["AAPL", "MSFT", "AAPL", None, "NVDA"])
    assert [x["ticker"] for x in m] == ["AAPL", "MSFT", "NVDA"]
    assert all(x["removed"] is None and "added" in x for x in m)


def test_classify_headwind_dominates_buyable():
    # a fresh cascade tier that coincides with a TOPPING/SELL regime is NOT entry-now —
    # the validated AVOID edge wins (don't label a distributing subsector buy-ready).
    assert sc._classify(buyable=True, tier="T1", state="TOPPING") == "headwind"
    assert sc._classify(buyable=True, tier="T2", state="SELL") == "headwind"


def test_classify_entry_forming_tailwind_late_neutral():
    assert sc._classify(True, "T1", "EXTENDED") == "entry_now"       # buyable, not headwind
    assert sc._classify(True, "T2", "BELOW_TREND") == "entry_now"
    assert sc._classify(False, "T4", "NEUTRAL") == "forming"
    assert sc._classify(False, None, "BUY_PARTIAL") == "tailwind"
    assert sc._classify(False, None, "EXTENDED") == "late"
    assert sc._classify(False, None, "NEUTRAL") == "neutral"


def test_subsector_factor_is_max_of_entry_and_regime_and_zero_for_headwind():
    assert sc._subsector_factor(1.0, "BELOW_TREND") == 1.0          # entry tier dominates
    assert sc._subsector_factor(0.0, "BUY_PARTIAL") == 0.60         # regime carries it
    assert sc._subsector_factor(0.4, "BUY") == 0.80                 # regime > weak tier
    assert sc._subsector_factor(0.0, "TOPPING") == 0.0             # headwind contributes nothing
    assert sc._subsector_factor(0.0, "SELL") == 0.0


def _grp(key, state, entry_tier, entry_w, buyable, members):
    tailwind = state in sc._TAILWIND_STATES
    headwind = state in sc._HEADWIND_STATES
    return {
        "key": key, "label": key, "sector": "X", "kind": "subsector",
        "entry": {"tier": entry_tier, "weight": entry_w, "buyable": buyable},
        "regime": {"state": state, "side": "buy" if tailwind else ("avoid" if headwind else "neutral"),
                   "tailwind": tailwind, "headwind": headwind},
        "members": members,
    }


def _mem(tk, tier, w, buyable, vs=0.0):
    return {"ticker": tk, "price": 10.0, "stock_tier": tier, "stock_weight": w,
            "stock_ticks": 0, "stock_bars_to_cross": None, "stock_buyable": buyable, "vs_basket": vs}


def test_funnel_double_buy_and_headwind_split():
    groups = [
        # entry-now subsector (T1) -> its buyable member is a top double-buy (1.0 * 1.0)
        _grp("alpha", "BELOW_TREND", "T1", 1.0, True, [_mem("AAA", "T1", 1.0, True), _mem("BBB", None, 0.0, False)]),
        # regime tailwind (no cascade tier) -> buyable member still funnels, factor 0.6
        _grp("beta", "BUY_PARTIAL", None, 0.0, False, [_mem("CCC", "T2", 0.8, True)]),
        # headwind subsector -> a buyable member is a WARNING, never a double-buy
        _grp("gamma", "TOPPING", None, 0.0, False, [_mem("DDD", "T1", 1.0, True)]),
    ]
    ff = sc.funnel(groups)
    db = {r["ticker"]: r for r in ff["double_buy"]}
    hw = {r["ticker"]: r for r in ff["headwind_warn"]}
    assert set(db) == {"AAA", "CCC"}
    assert set(hw) == {"DDD"}
    assert db["AAA"]["combined_score"] == 1.0                       # 1.0 stock * 1.0 subsector
    assert db["CCC"]["combined_score"] == pytest.approx(0.48)       # 0.8 stock * 0.6 regime factor
    # best-first ordering
    assert ff["double_buy"][0]["ticker"] == "AAA"
    # a non-buyable member never appears
    assert "BBB" not in db and "BBB" not in hw


def test_funnel_skips_non_buyable_members():
    g = _grp("x", "BUY", "T1", 1.0, True, [_mem("NB", None, 0.0, False)])
    ff = sc.funnel([g])
    assert ff["double_buy"] == [] and ff["headwind_warn"] == []


# ---------------------------------------------------------------- integration ----

def _has_ohlcv():
    from lib import config
    return (config.data_dir() / "baskets" / "ohlcv").exists()


@pytest.mark.skipif(not _has_ohlcv(), reason="OHLCV store not present")
def test_score_group_real_subsector_semiconductors():
    from engine import subsector_scan
    groups = subsector_scan._industry_map()
    key = next(k for k in groups if k[1] == "Semiconductors")
    g = sc.score_group(sc._slug(key[1]), key[1], key[0], groups[key], None, {})
    assert g is not None
    assert g["key"] == "semiconductors"
    assert g["entry"]["tier"] in (None, "T1", "T2", "T3", "T4")
    assert g["regime"]["state"] in {
        "BUY", "BUY_PARTIAL", "SETUP_BUY", "NEUTRAL", "EXTENDED",
        "TOPPING", "SELL", "BELOW_TREND", "OVERSOLD_BOUNCE"}
    assert g["n_priced"] >= 3
    assert len(g["members"]) >= 3
    # the chart series + markers are present for the detail page
    assert "_candle" in g and not g["_candle"]["close"].dropna().empty
    # every member carries its own gate verdict shape
    for m in g["members"]:
        assert "stock_tier" in m and "stock_buyable" in m


# ----------------------------------------------------- China 同花顺 (THS) desk ----

def _has_china():
    from lib import config
    return (config.data_dir() / "china_stocks").exists() and \
        (config.data_dir() / "baskets_china_ths" / "membership.json").exists()


@pytest.mark.skipif(not _has_china(), reason="China stores not present")
def test_china_benchmark_and_member_loader_resolve():
    from engine import basket_index
    # CSI 300 benchmark loads (from data/china, not the member stores)
    b = sc._bench_close("510300.SS")
    assert b is not None and len(b) > 260
    # an A-share .SZ/.SS ticker now resolves through the member loader (the china_stocks fallback)
    df = basket_index._load_member_ohlcv("000725.SZ")
    assert df is not None and "close" in df and "open" in df  # open synthesised from close


@pytest.mark.skipif(not _has_china(), reason="China stores not present")
def test_china_ths_score_group_is_bilingual_and_uses_csi300():
    import json
    from lib import config
    mem = json.loads((config.data_dir() / "baskets_china_ths" / "membership.json").read_text())
    bench = sc._bench_close(mem.get("benchmark") or "510300.SS")
    bid, spec = next(iter(mem["baskets"].items()))
    tickers = [m["ticker"] for m in spec["members"] if not m.get("removed")]
    g = sc.score_group(sc._slug(bid), spec["name"], spec.get("category"), tickers, bench, {},
                       kind="concept", label_zh=spec.get("name_zh"), sector_zh=spec.get("category_zh"),
                       member_names={m["ticker"]: m.get("name_zh") for m in spec["members"]})
    assert g is not None
    assert g["kind"] == "concept"
    assert g["label_zh"] == spec.get("name_zh")        # bilingual label flows through
    assert g["regime"]["state"] in {
        "BUY", "BUY_PARTIAL", "SETUP_BUY", "NEUTRAL", "EXTENDED",
        "TOPPING", "SELL", "BELOW_TREND", "OVERSOLD_BOUNCE"}
    assert g["regime"]["rs_60d"] is not None           # measured vs CSI 300, not SPY
    # at least one member carries a Chinese name (the funnel/detail bilingual join key)
    assert any(m.get("name_zh") for m in g["members"])
