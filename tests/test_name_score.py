"""Market-aware per-name POTENTIAL score (engine/name_score) + the multi-market grader.

Pins the cross-market design: the trigger gates the tier in EVERY market (front-running),
fuel sizes within it, and the per-market edge blend PRESERVES each market's validated
selection edge (US event edge; CN/HK none) without ever overriding the timing gate.
"""
import pandas as pd

from engine import name_score as ns
from engine import name_score_grader as gr


def _rec(state, *, off_high=-28.0, vs200=-10.0, rsi=52.0, entry="buy_now", ticker="T"):
    return {"ticker": ticker,
            "ladder": {"state": state, "label": state.title(), "entry": {"urgency": "now"}},
            "tech": {"off_52w_high_pct": off_high, "pct_vs_200dma": vs200, "rsi14": rsi},
            "entry_signal": {"status": entry},
            "anticipation": {"anticipation_index": 55.0,
                             "horizons": {"medium": {"mfe_med": 7.0, "dd_avg": -8.0}}}}


# --- the US edge blend (preserve validated alpha) -------------------------------
def test_us_edge_blend_boosts_and_trims():
    base = ns.potential_score(_rec("FRESH BUY"), market="US", edge_z=0.0)
    boosted = ns.potential_score(_rec("FRESH BUY"), market="US", edge_z=1.6)   # insider buying
    against = ns.potential_score(_rec("FRESH BUY"), market="US", edge_z=-1.6)  # insider selling
    assert boosted["score"] > base["score"] > against["score"]
    assert boosted["components"]["edge"] > 1.0 and against["components"]["edge"] < 1.0


def test_cn_and_hk_ignore_edge():
    # CN reversal edge lives in the washout/cycle; HK has no validated name edge -> edge_mult=1
    for mkt in ("CN", "HK"):
        a = ns.potential_score(_rec("FRESH BUY"), market=mkt, edge_z=2.5)
        b = ns.potential_score(_rec("FRESH BUY"), market=mkt, edge_z=-2.5)
        assert a["score"] == b["score"]
        assert a["components"]["edge"] == 1.0


def test_ca_blend_is_lighter_than_us():
    z = 2.0
    us = ns.potential_score(_rec("FRESH BUY"), market="US", edge_z=z)["components"]["edge"]
    ca = ns.potential_score(_rec("FRESH BUY"), market="CA", edge_z=z)["components"]["edge"]
    assert 1.0 < ca < us                       # CA momentum prior weighted less than the US event edge


# --- the trigger gate dominates the edge in EVERY market (front-running) ---------
def test_declining_name_gated_out_despite_strong_edge():
    # the AAPL-in-DECLINE case: a great edge can't make a falling name a buy.
    p = ns.potential_score(_rec("DECLINE", off_high=-12.0, vs200=2.0, entry="hold"),
                           market="US", edge_z=2.0)
    assert p["score"] <= 5 and p["tier"] == "no_setup"


def test_washed_out_turning_is_primed_all_markets():
    for mkt in ("US", "CN", "HK", "CA", "INTL"):
        p = ns.potential_score(_rec("FRESH BUY"), market=mkt, edge_z=0.3)
        assert p["tier"] in ("primed", "setting_up") and p["band"] in ("high", "constructive")


def test_bounce_wait_scores_exactly_as_legacy_extended():
    """The COUNTERTREND BOUNCE wording split (entry_signal 'bounce_wait', formerly
    'extended') must move NO published score: the 0.50 confirm weight is kept
    deliberately, and an unmapped key would silently default to 1.0 and double it."""
    assert ns._ENTRY_CONFIRM["bounce_wait"] == ns._ENTRY_CONFIRM["extended"] == 0.50
    bounce = ns.potential_score(_rec("COUNTERTREND BOUNCE", entry="bounce_wait"),
                                market="CN", edge_z=0.0)
    legacy = ns.potential_score(_rec("COUNTERTREND BOUNCE", entry="extended"),
                                market="CN", edge_z=0.0)
    assert bounce["score"] == legacy["score"]


# --- the multi-market grader ----------------------------------------------------
def test_grader_market_paths_and_keep_first(tmp_path, monkeypatch):
    monkeypatch.setattr(gr.config, "data_dir", lambda: tmp_path)
    us = [{"ticker": "AAPL", "score": 80, "tier": "primed", "fuel": 0.7, "trigger": 1.0, "level": 200.0}]
    assert gr.append_name_calls(us, market="US", asof="2026-06-28") == 1
    assert gr.append_name_calls([{**us[0], "score": 1}], market="US", asof="2026-06-28") == 1  # keep-first
    # US writes to the name_score/<mkt> path; CN keeps its legacy china_name_score path
    assert (tmp_path / "name_score" / "us_calls.parquet").exists()
    gr.append_name_calls([{"ticker": "600030.SS", "score": 70, "tier": "watch",
                           "fuel": 0.5, "trigger": 0.5, "level": 27.0}], market="CN", asof="2026-06-28")
    assert (tmp_path / "china_name_score" / "calls.parquet").exists()
    df = pd.read_parquet(tmp_path / "name_score" / "us_calls.parquet")
    assert int(df.iloc[0]["score"]) == 80                # original not overwritten
    assert gr.grade("US")["available"] is True
    assert gr.grade("HK")["available"] is False          # nothing logged for HK
