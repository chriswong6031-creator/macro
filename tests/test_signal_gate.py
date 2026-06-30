"""Tests for engine.signal_gate.is_buyable — the hard BUY gate behind the Top-setups strip
(us_stocks.html) and the discovery "Buy-zone" picks.

The owner's spec: a name is a recommendation ONLY if it has triggered the MACD-2D x StochRSI-3D
confluence within the fresh window (T1/T2 confirmed) or the 3D StochRSI has crossed and the 2D
MACD is about to (T3). T4 (off the 2D StochRSI) and every HOLD / topped / downtrend verdict are
NOT buyable.
"""
import json

from engine.signal_gate import BUYABLE_TIERS, buy_signal, is_buyable


def test_buyable_tiers_are_t1_t2_t3_only():
    # T4 is deliberately excluded — it fires off the 2D StochRSI, not the StochRSI-3D the spec
    # requires; everything below it is not a confluence buy.
    assert BUYABLE_TIERS == ("T1", "T2", "T3")
    assert "T4" not in BUYABLE_TIERS


def test_is_buyable_admits_confirmed_and_anticipation_tiers():
    for tier in ("T1", "T2", "T3"):
        assert is_buyable({"eligible": True, "tier_cascade": tier}) is True


def test_is_buyable_rejects_t4_and_no_tier():
    assert is_buyable({"eligible": True, "tier_cascade": "T4"}) is False    # 2D StochRSI, not 3D
    assert is_buyable({"eligible": True, "tier_cascade": None}) is False    # early-only / no cross


def test_is_buyable_rejects_ineligible_even_with_a_tier():
    # a topped / stale verdict clears eligibility — never a fresh buy regardless of any stale tier
    assert is_buyable({"eligible": False, "tier_cascade": "T2"}) is False
    assert is_buyable({"eligible": False, "tier_cascade": "T1"}) is False


def test_is_buyable_handles_none_and_empty():
    assert is_buyable(None) is False
    assert is_buyable({}) is False


def test_buy_signal_is_slim_and_json_safe():
    # buy_signal drops the §7 marker payload (which can carry NaN) so signal_gate.json can be
    # persisted with allow_nan=False without ever crashing the build. is_buyable round-trips it.
    full = {"eligible": True, "tier_cascade": "T2", "tier_sub": "deep", "ticks": 1,
            "bars_to_cross": None, "last": {"price": float("nan")}, "result": {"big": "payload"}}
    slim = buy_signal(full)
    assert set(slim) == {"eligible", "tier_cascade", "tier_sub", "ticks", "bars_to_cross"}
    assert "last" not in slim and "result" not in slim          # no NaN-prone / heavy fields
    json.dumps(slim, allow_nan=False)                            # must not raise
    assert is_buyable(slim) is True                              # slim still gates correctly
    assert buy_signal(None) == {"eligible": False, "tier_cascade": None}
    assert is_buyable(buy_signal(None)) is False
