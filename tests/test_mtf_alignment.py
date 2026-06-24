"""Multi-timeframe bottoming-ALIGNMENT screen — the standout-strip selection gate
that replaced the falling-knife reversal/momentum admission. These exercise the pure
classifiers on hand-built _tf_state dicts (deterministic, no price caches)."""
from engine.cycles import (
    _hist_falling, _tf_phase, _daily_trigger, mtf_alignment,
)
from engine.setups import alignment_gate, _align_tier


# --------------------------------------------------------------- _hist_falling ----
def test_hist_falling_strictly_declining():
    assert _hist_falling([0.5, 0.2, -0.1, -0.4]) is True


def test_hist_falling_not_when_rising_or_flat():
    assert _hist_falling([-0.4, -0.2, -0.1, 0.0]) is False   # rising
    assert _hist_falling([-0.2, -0.2, -0.2, -0.2]) is False  # flat
    assert _hist_falling([-0.1, -0.2]) is False              # too few bars


# ------------------------------------------------------------------- _tf_phase ----
def test_tf_phase_classifies_each_posture():
    assert _tf_phase({}) == "unknown"
    assert _tf_phase({"macd_pos": True}) == "rising"
    assert _tf_phase({"macd_pos": True, "macd_curl_dn": True}) == "rolling"
    assert _tf_phase({"macd_pos": False, "macd_cross_dn": True}) == "falling"
    assert _tf_phase({"macd_pos": False, "macd_approaching_up": True}) == "turning"
    assert _tf_phase({"macd_pos": False, "macd_curl_up": True}) == "turning"
    # below zero AND still dropping, no up-flags -> the falling-knife tell
    assert _tf_phase({"macd_pos": False,
                      "spark_hist": [-0.1, -0.2, -0.3, -0.45]}) == "falling"
    # below zero but flat near a low -> basing (eligible, not a knife)
    assert _tf_phase({"macd_pos": False,
                      "spark_hist": [-0.20, -0.21, -0.20, -0.20]}) == "basing"


# -------------------------------------------------------------- _daily_trigger ----
def test_daily_trigger_cross_imminent_early():
    assert _daily_trigger({"macd_cross_up": True}) == "crossed"
    assert _daily_trigger({"macd_approaching_up": True, "macd_days_to_cross": 2}) == "imminent"
    # 0 trading days to cross is a VALID imminent ETA, not "missing" (round(0.5)==0)
    assert _daily_trigger({"macd_approaching_up": True, "macd_days_to_cross": 0}) == "imminent"
    assert _daily_trigger({"macd_approaching_up": True, "macd_days_to_cross": 5}) is None
    # approaching but no ETA computed -> can't call it imminent
    assert _daily_trigger({"macd_approaching_up": True, "macd_days_to_cross": None}) is None
    assert _daily_trigger({"macd_pos": True, "rsi14": 60}) == "early"
    # already extended/overbought -> NOT an entry (don't chase)
    assert _daily_trigger({"macd_pos": True, "rsi14": 75}) is None
    # macd positive with no RSI reading -> unknown RSI is not treated as extended
    assert _daily_trigger({"macd_pos": True}) == "early"
    assert _daily_trigger({}) is None


# ------------------------------------------------------------- mtf_alignment ----
def _mtf(w, t3, d):
    return {"W": w, "3D": t3, "D": d}


def test_aligned_when_weekly_basing_3d_turning_daily_crossed():
    a = mtf_alignment(_mtf(
        {"macd_pos": False, "spark_hist": [-0.20, -0.21, -0.20, -0.20]},  # weekly basing
        {"macd_pos": False, "macd_approaching_up": True},                  # 3d turning
        {"macd_cross_up": True},                                           # daily crossed
    ))
    assert a["aligned"] is True and a["near"] is False
    assert a["weekly"] == "basing" and a["daily_trigger"] == "crossed"
    assert a["score"] > 0


def test_falling_weekly_blocks_even_with_daily_cross():
    # the exact falling-knife the user complained about: mid weekly bear, daily bounce
    a = mtf_alignment(_mtf(
        {"macd_pos": False, "macd_cross_dn": True},      # weekly just crossed DOWN
        {"macd_pos": False, "macd_approaching_up": True},
        {"macd_cross_up": True},
    ))
    assert a["aligned"] is False and a["near"] is False
    assert a["blocked"] is True and a["weekly"] == "falling"


def test_sub_zero_still_dropping_weekly_blocks():
    a = mtf_alignment(_mtf(
        {"macd_pos": False, "spark_hist": [-0.1, -0.2, -0.3, -0.45]},  # weekly still dropping
        {"macd_pos": False, "macd_approaching_up": True},
        {"macd_cross_up": True},
    ))
    assert a["aligned"] is False and a["weekly"] == "falling" and a["blocked"] is True


def test_deep_knife_blocks_aligned_setup():
    a = mtf_alignment(
        _mtf({"macd_pos": False, "macd_approaching_up": True},
             {"macd_pos": False, "macd_approaching_up": True},
             {"macd_cross_up": True}),
        wo={"knife": 0.8},
    )
    assert a["aligned"] is False and a["blocked"] is True


def test_bad_ladder_state_blocks():
    a = mtf_alignment(
        _mtf({"macd_pos": False, "macd_approaching_up": True},
             {"macd_pos": False, "macd_approaching_up": True},
             {"macd_cross_up": True}),
        lad={"state": "COUNTERTREND BOUNCE"},
    )
    assert a["aligned"] is False and a["blocked"] is True


def test_near_when_weekly_ok_one_lower_tf_turning():
    a = mtf_alignment(_mtf(
        {"macd_pos": False, "spark_hist": [-0.20, -0.21, -0.20, -0.20]},  # weekly basing
        {"macd_pos": False, "macd_approaching_up": True},                  # 3d turning
        {"macd_pos": False},                                              # daily: no trigger
    ))
    assert a["aligned"] is False and a["near"] is True


def test_missing_weekly_is_not_eligible():
    a = mtf_alignment({"W": {}, "3D": {"macd_approaching_up": True},
                       "D": {"macd_cross_up": True}})
    assert a["aligned"] is False and a["near"] is False and a["have_tf"] is False


def test_no_daily_returns_empty():
    assert mtf_alignment({"W": {"macd_pos": True}, "3D": {}, "D": {}}) == {}


# ------------------------------------------------------------- alignment_gate ----
def test_alignment_gate_keeps_aligned_drops_unaligned_backfills_near():
    rows = [
        {"ticker": "A", "align": {"aligned": True, "score": 90}},
        {"ticker": "B", "align": {"aligned": False, "near": False}},   # dropped
        {"ticker": "C", "align": {"near": True, "score": 50}},          # backfill
        {"ticker": "D", "align": {"aligned": True, "score": 80}},
        {"ticker": "E", "align": {"near": True, "score": 70}},          # backfill (higher)
        {"ticker": "F", "align": None},                                  # dropped
    ]
    out = alignment_gate(rows, lambda r: r["align"], min_keep=4,
                         sort_key=lambda r: (r["align"] or {}).get("score") or 0)
    tickers = [r["ticker"] for r in out]
    # 2 aligned (A,D sorted by score) then 2 near to reach min_keep=4 (E before C)
    assert tickers == ["A", "D", "E", "C"]
    assert [r["align_tier"] for r in out] == ["aligned", "aligned", "near", "near"]


def test_alignment_gate_no_backfill_when_enough_aligned():
    rows = [
        {"ticker": "A", "align": {"aligned": True, "score": 90}},
        {"ticker": "B", "align": {"aligned": True, "score": 80}},
        {"ticker": "C", "align": {"near": True, "score": 99}},  # NOT added — aligned >= min_keep
    ]
    out = alignment_gate(rows, lambda r: r["align"], min_keep=2,
                         sort_key=lambda r: (r["align"] or {}).get("score") or 0)
    assert [r["ticker"] for r in out] == ["A", "B"]


def test_align_tier_helper():
    assert _align_tier({"aligned": True}) == "aligned"
    assert _align_tier({"near": True}) == "near"
    assert _align_tier({}) is None
    assert _align_tier(None) is None
