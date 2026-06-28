"""China per-name POTENTIAL score (engine/china_name_score) + its forward-grader.

Pins the design intent: a high score = washed-out AND turning up now AND survivable
(NOT "the most fallen"). The trigger gates the tier; fuel sizes within it.
"""
import pandas as pd

from engine import china_name_score as ns
from engine import china_name_score_grader as gr


def _rec(state, *, off_high=-10.0, vs200=0.0, rsi=55.0, entry_status="buy_now",
         ticker="000001.SZ", anticipation_index=50.0, fragility=None):
    r = {"ticker": ticker,
         "ladder": {"state": state, "label": state.title(), "entry": {"urgency": "now"}},
         "tech": {"off_52w_high_pct": off_high, "pct_vs_200dma": vs200, "rsi14": rsi},
         "entry_signal": {"status": entry_status},
         "anticipation": {"anticipation_index": anticipation_index,
                          "horizons": {"medium": {"mfe_med": 7.0, "dd_avg": -8.0}}}}
    if fragility:
        r["fragility"] = fragility
    return r


# --- the core inversion the engine exists to fix --------------------------------
def test_washed_out_fresh_buy_is_primed():
    # East Money case: deeply off its high AND a confirmed cycle low -> the top buy.
    p = ns.potential_score(_rec("FRESH BUY", off_high=-30.0, vs200=-11.0))
    assert p["tier"] == "primed" and p["score"] >= 70 and p["band"] == "high"


def test_extended_leader_is_no_setup():
    # an overbought leader at a high (TOP WATCH, far over the 200dma) has no room -> low.
    p = ns.potential_score(_rec("TOP WATCH", off_high=0.0, vs200=22.0, rsi=74.0,
                                entry_status="extended"))
    assert p["tier"] == "no_setup" and p["score"] < 25


def test_deep_washout_still_declining_is_gated_out():
    # THE key inversion vs the old reversal percentile: deeply oversold but still in a
    # down-leg (DECLINE) is a knife, not a buy -> the trigger gates the score to ~0.
    p = ns.potential_score(_rec("DECLINE", off_high=-45.0, vs200=-30.0, rsi=28.0,
                                entry_status="extended"))
    assert p["score"] <= 5 and p["tier"] == "no_setup"


def test_shallow_fresh_buy_still_actionable():
    # a clean FRESH BUY on a shallow pullback isn't crushed by a low washout reading —
    # the trigger decides the tier (the 0.4 fuel floor), so it reads at least 'setting up'.
    p = ns.potential_score(_rec("FRESH BUY", off_high=-9.0, vs200=1.4))
    assert p["score"] >= 40 and p["tier"] in ("setting_up", "primed")


def test_basing_ranks_below_a_confirmed_turn():
    # a deep-but-still-basing name (BOTTOM WATCH) must rank BELOW a confirmed turn
    # (FRESH BUY) of similar depth — the trigger is the actionable leg.
    basing = ns.potential_score(_rec("BOTTOM WATCH", off_high=-30.0, vs200=-12.0,
                                     entry_status="wait_pullback"))
    turned = ns.potential_score(_rec("FRESH BUY", off_high=-30.0, vs200=-12.0))
    assert turned["score"] > basing["score"]


def test_survive_haircut_only_subtracts():
    base = ns.potential_score(_rec("FRESH BUY", off_high=-30.0, vs200=-11.0))
    crowded = ns.potential_score(_rec("FRESH BUY", off_high=-30.0, vs200=-11.0,
                                      fragility={"flag": True}))
    assert crowded["score"] < base["score"]          # never a booster
    assert 0.6 <= crowded["components"]["survive"] <= 1.0


def test_score_bounded_and_shaped():
    p = ns.potential_score(_rec("RALLY ON", off_high=-11.0, vs200=2.0))
    assert 0 <= p["score"] <= 100
    c = p["components"]
    assert 0.0 <= c["fuel"] <= 1.0 and 0.0 <= c["trigger"] <= 1.0
    assert p["call"]["ticker"] == "000001.SZ"


# --- the grader (forward-grading honesty mechanism) -----------------------------
def test_grader_append_keep_first_and_accruing(tmp_path, monkeypatch):
    monkeypatch.setattr(gr.config, "data_dir", lambda: tmp_path)
    calls = [{"ticker": "000001.SZ", "score": 80, "tier": "primed", "fuel": 0.7, "trigger": 1.0,
              "level": 10.0}]
    n1 = gr.append_name_calls(calls, asof="2026-06-28")
    assert n1 == 1
    # keep-FIRST: a re-stamp on the same (date,ticker) must NOT overwrite the original score
    n2 = gr.append_name_calls([{**calls[0], "score": 5}], asof="2026-06-28")
    assert n2 == 1
    df = pd.read_parquet(tmp_path / "china_name_score" / "calls.parquet")
    assert int(df.iloc[0]["score"]) == 80
    # grade() is honest about thin data
    g = gr.grade()
    assert g["available"] is True
    assert all(v.get("note") == "accruing" for v in g["by_horizon"].values())


def test_grader_no_calls_is_honest(tmp_path, monkeypatch):
    monkeypatch.setattr(gr.config, "data_dir", lambda: tmp_path)
    g = gr.grade()
    assert g["available"] is False
