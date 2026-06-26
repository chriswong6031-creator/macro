"""The fresh-from-oversold ENTRY gate (engine.cycles.mtf_alignment v2).

These pin the swing-entry revamp: the board must rank a FRESH turn-from-a-low above an
already-running leader, require an OVERSOLD ORIGIN on the 3-day, and EXCLUDE the
overextended chase to the watch strip. Pure classifiers on hand-built _tf_state dicts."""
from engine.cycles import (
    _weekly_bear_recovering, _three_day_fresh, _overextended, _tf_phase, mtf_alignment,
)
from engine.setups import alignment_gate, ALIGN_MIN_KEEP


def _mtf(w, t3, d):
    return {"W": w, "3D": t3, "D": d}


# the user's "best combination" weekly leg: still bearish, histogram recovering
_WK_RECOVER = {"macd_pos": False, "macd_curl_up": True}
# a fresh 3-day turn FROM a low (MACD curling up below zero)
_T3_FRESH = {"macd_pos": False, "macd_curl_up": True}
# daily just crossed up
_D_CROSS = {"macd_cross_up": True}


# ------------------------------------------------------- _weekly_bear_recovering ----
def test_weekly_bear_recovering_below_zero_and_turning():
    assert _weekly_bear_recovering({"macd_pos": False, "macd_curl_up": True}) is True
    assert _weekly_bear_recovering({"macd_pos": False, "macd_approaching_up": True}) is True
    # histogram rising while still negative (multi-bar recovery)
    assert _weekly_bear_recovering({"macd_pos": False, "spark_hist": [-0.4, -0.3, -0.2, -0.1]}) is True
    # NOT recovering: already positive, or still dropping, or a fresh down-cross
    assert _weekly_bear_recovering({"macd_pos": True}) is False
    assert _weekly_bear_recovering({"macd_pos": False, "spark_hist": [-0.1, -0.2, -0.3, -0.45]}) is False
    assert _weekly_bear_recovering({"macd_pos": False, "macd_cross_dn": True}) is False


def test_tf_phase_weekly_flag_emits_bear_recovering():
    s = {"macd_pos": False, "macd_curl_up": True}
    assert _tf_phase(s, weekly=True) == "bear_recovering"   # weekly view: the prize state
    assert _tf_phase(s) == "turning"                         # default view unchanged


# --------------------------------------------------------------- _three_day_fresh ----
def test_three_day_fresh_requires_turn_from_a_low():
    assert _three_day_fresh({"macd_curl_up": True}) == "macd_trough"
    assert _three_day_fresh({"macd_cross_up": True}) == "macd_trough"
    # StochRSI popping up from < 25 (the user's "from the bottom" line)
    assert _three_day_fresh({"spark_stoch": [18.0, 22.0, 30.0]}) == "stoch_os"
    # about-to-cross below zero -> the backfill "approaching" case
    assert _three_day_fresh({"macd_pos": False, "macd_approaching_up": True}) == "approaching"
    # ALREADY running (positive, StochRSI never came from oversold) -> NOT fresh
    assert _three_day_fresh({"macd_pos": True, "spark_stoch": [60.0, 65.0, 72.0]}) is None
    # StochRSI rising but never below 25 -> NOT a fresh-from-oversold turn
    assert _three_day_fresh({"spark_stoch": [40.0, 45.0, 55.0]}) is None


# ------------------------------------------------------------------ _overextended ----
def test_overextended_flags_the_chase():
    assert _overextended({"D": {}, "3D": {"stoch": 86.0}}) is True       # 3D StochRSI overbought
    assert _overextended({"D": {"stoch": 90.0}, "3D": {}}) is True       # daily StochRSI overbought
    assert _overextended({"D": {"rsi14": 70.0}, "3D": {}}) is True       # daily RSI too hot
    assert _overextended({"D": {}, "3D": {}}, ext_pct=35.0) is True      # far above the 200dma
    assert _overextended({"D": {"rsi14": 55.0, "stoch": 60.0}, "3D": {"stoch": 50.0}}, ext_pct=10.0) is False


# ----------------------------------------------------------------- mtf_alignment ----
def test_prime_when_weekly_recovering_3d_fresh_daily_crossed():
    a = mtf_alignment(_mtf(_WK_RECOVER, _T3_FRESH, _D_CROSS))
    assert a["tier"] == "PRIME" and a["aligned"] is True and a["near"] is False
    assert a["weekly"] == "bear_recovering" and a["three_day_trigger"] == "macd_trough"
    assert a["entry_tier"] == "Prime entry"
    assert "oversold" in a["reason"].lower() or "below zero" in a["reason"].lower()
    assert "recovering" in a["reason"].lower()


def test_stoch_from_oversold_is_a_prime_trigger():
    a = mtf_alignment(_mtf(
        {"macd_pos": False, "spark_hist": [-0.21, -0.20, -0.20, -0.20]},  # weekly basing
        {"macd_pos": False, "spark_stoch": [18.0, 22.0, 30.0]},           # 3D StochRSI from <25
        _D_CROSS))
    assert a["tier"] == "PRIME" and a["three_day_trigger"] == "stoch_os"


def test_prime_outranks_already_running_leader():
    prime = mtf_alignment(_mtf(_WK_RECOVER, _T3_FRESH, _D_CROSS))
    # an "already took off" leader: weekly & 3-day already rising, daily early, not yet OB
    running = mtf_alignment(_mtf(
        {"macd_pos": True},                                          # weekly already up
        {"macd_pos": True, "spark_stoch": [60.0, 66.0, 70.0]},       # 3D running, not from a low
        {"macd_pos": True, "rsi14": 58.0}))                          # daily rising
    assert running["tier"] in (None, "APPROACHING")                 # never PRIME/ARMED
    assert running["aligned"] is False                              # cannot top the buy board
    assert prime["score"] > running["score"]                       # the fresh entry ranks higher


def test_overextended_leader_excluded_to_watch():
    # a fresh-looking setup but the 3-day StochRSI is overbought -> already ran
    a = mtf_alignment(_mtf(_WK_RECOVER, {"macd_curl_up": True, "stoch": 88.0}, _D_CROSS))
    assert a["overextended"] is True
    assert a["aligned"] is False and a["near"] is False            # off the buy board
    assert a["entry_tier"] == "Extended — wait"
    # and via the 200dma stretch leg
    b = mtf_alignment(_mtf(_WK_RECOVER, _T3_FRESH, _D_CROSS), ext_pct=33.0)
    assert b["overextended"] is True and b["aligned"] is False


def test_never_empty_backfills_approaching_but_not_the_chase():
    # 2 PRIME, several APPROACHING, plus an overextended (excluded) name
    rows = [
        {"ticker": "P1", "a": mtf_alignment(_mtf(_WK_RECOVER, _T3_FRESH, _D_CROSS))},
        {"ticker": "P2", "a": mtf_alignment(_mtf(_WK_RECOVER, _T3_FRESH, _D_CROSS))},
        {"ticker": "A1", "a": mtf_alignment(_mtf({"macd_pos": False, "spark_hist": [-0.2, -0.2, -0.2, -0.2]},
                                                 _T3_FRESH, {"macd_pos": False}))},  # 3D fresh, no daily -> APPROACHING
        {"ticker": "A2", "a": mtf_alignment(_mtf({"macd_pos": False, "spark_hist": [-0.2, -0.2, -0.2, -0.2]},
                                                 _T3_FRESH, {"macd_pos": False}))},
        {"ticker": "X", "a": mtf_alignment(_mtf(_WK_RECOVER, {"macd_curl_up": True, "stoch": 88.0}, _D_CROSS))},
    ]
    kept = alignment_gate(rows, lambda r: r["a"], min_keep=4,
                          sort_key=lambda r: (r["a"] or {}).get("score") or 0)
    tickers = [r["ticker"] for r in kept]
    assert "P1" in tickers and "P2" in tickers          # PRIME always kept
    assert "A1" in tickers and "A2" in tickers          # backfilled to reach min_keep
    assert "X" not in tickers                           # the overextended chase is NEVER backfilled
    # PRIME sorts above APPROACHING
    assert tickers.index("P1") < tickers.index("A1")


def test_align_min_keep_default_from_config():
    assert ALIGN_MIN_KEEP >= 1   # sourced from config.yml engine.entry_gate.align_min_keep (fallback 10)
