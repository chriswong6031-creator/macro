"""China per-name POTENTIAL score (engine/china_name_score) + its forward-grader.

Pins the design intent: a high score = washed-out AND turning up now AND survivable
(NOT "the most fallen"). The trigger gates the tier; fuel sizes within it.
"""
import pandas as pd

from engine import china_name_score as ns
from engine import china_name_score_grader as gr
from engine import name_score_grader as _ng  # the actual implementation (gr is a shim)


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


# ---------------------------------------------------------------------------
# W0.3 — CN store-group fix: A-share board tickers now resolve prices
# ---------------------------------------------------------------------------

def test_cn_fwd_group_is_tuple_not_china_only():
    """W0.3: _FWD_GROUP['CN'] in name_score_grader must be a tuple starting with
    'china_stocks' — the fix for the dead grader (original "china" only → 0/N resolves
    because all board tickers live in china_stocks, not in the ~30 ETF parquets in china)."""
    grp = _ng._FWD_GROUP.get("CN")
    assert isinstance(grp, tuple), f"_FWD_GROUP['CN'] must be a tuple, got {type(grp)}"
    assert grp[0] == "china_stocks", f"first element must be 'china_stocks', got {grp[0]}"
    assert "china" in grp, "china ETF fallback must still be present in the tuple"


def test_cn_resolution_uses_china_stocks_first(tmp_path, monkeypatch):
    """W0.3: a CN A-share ticker in china_stocks resolves; the same ticker absent from
    the china ETF store would have returned None under the original single-group mapping."""
    import numpy as np
    import pandas as pd
    from lib import config as lconfig, store as lstore

    monkeypatch.setattr(lconfig, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(_ng.config, "data_dir", lambda: tmp_path)

    dates = pd.bdate_range("2026-01-01", periods=130)
    closes = 10.0 * (1.02 ** np.arange(len(dates)))
    df = pd.DataFrame({"close": closes, "high": closes * 1.01,
                       "low": closes * 0.99, "volume": np.full(len(dates), 1e6)},
                      index=dates)
    lstore.upsert("china_stocks", "600001.SS", df)     # per-name A-share store
    # confirm the china (ETF) store does NOT have this ticker — proving the old mapping failed
    assert lstore.read("china", "600001.SS") is None

    # post-fix: _fwd_return resolves via china_stocks (on the real implementation module)
    result = _ng._fwd_return("CN", "600001.SS", pd.Timestamp("2026-01-02"), 21)
    assert result is not None, (
        "W0.3 fix failed: CN ticker should resolve via china_stocks → non-None fwd return")


def test_cn_grade_resolves_nonzero_after_fix(tmp_path, monkeypatch):
    """W0.3: grade('CN') reports n_graded > 0 for a matured synthetic ledger once the
    store-group fix is in place. Under the old mapping grade() always reported n_graded=0."""
    import numpy as np
    import pandas as pd
    from lib import config as lconfig, store as lstore

    monkeypatch.setattr(lconfig, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(_ng.config, "data_dir", lambda: tmp_path)

    dates = pd.bdate_range("2026-01-01", periods=130)
    # seed 10 per-name tickers in china_stocks
    for i in range(10):
        tk = f"60000{i}.SS"
        closes = 10.0 * (1.02 ** np.arange(len(dates)))
        df = pd.DataFrame({"close": closes, "high": closes * 1.01,
                           "low": closes * 0.99, "volume": np.full(len(dates), 1e6)},
                          index=dates)
        lstore.upsert("china_stocks", tk, df)

    # log 10 calls stamped at a date that has 21+ forward sessions (date[0] → exit date[21])
    calls = [{"ticker": f"60000{i}.SS", "score": 50 + i * 5, "tier": "primed",
              "fuel": 0.7, "trigger": 1.0, "level": 10.0} for i in range(10)]
    gr.append_name_calls(calls, market="CN", asof=str(dates[0].date()))

    result = gr.grade("CN")
    assert result["available"] is True
    assert result["n_calls"] == 10
    # 21d horizon must have graded rows (not 0) since dates[0]+21 is within the series
    n_21 = result.get("by_horizon", {}).get("21d", {}).get("n", 0)
    assert n_21 > 0, (
        f"W0.3 fix verification: expected n_21d > 0, got {n_21}. "
        "If n==0, the store-group fix did not take effect."
    )
