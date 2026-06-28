"""Tests for engine.pullback_zone (don't-chase → concrete buy levels, display-only)."""
import pytest

from engine import pullback_zone as pz


def _tech(price, p200, p50=None, off_high=-1.0, above50=True):
    return {"price": price, "pct_vs_200dma": p200, "pct_vs_50dma": p50,
            "off_52w_high_pct": off_high, "above50": above50}


def test_not_applicable_below_block():
    # +20% over the 200d (below the 30% block) and not parabolic -> no zone (won't contradict a
    # "good entry" verdict)
    assert pz.compute(_tech(120, 20, p50=5)) is None


def test_missing_inputs():
    assert pz.compute({}) is None
    assert pz.compute(None) is None
    assert pz.compute({"price": 0, "pct_vs_200dma": 40}) is None


def test_accumulate_shallow_zone_for_a_leader():
    # +35% over the 200d, +6% over the 50d, near highs -> a shallow, timeable zone -> ACCUMULATE
    out = pz.compute(_tech(135.0, 35.0, p50=6.0, off_high=-1.0), grade="steady")
    assert out is not None and out["stance"] == "accumulate"
    labels = [lv["label_en"] for lv in out["levels"]]
    assert any("50-day" in s for s in labels)              # the rising-50d support is offered
    assert any("200-day" in s for s in labels)             # ...and the chase-exit line
    # the 50d is the shallowest level, all pulls are below spot (negative)
    assert out["levels"][0]["pull_pct"] < 0
    assert out["shallow_pull"] == out["levels"][0]["pull_pct"]
    # exit line is shallow for a +35% name (~ -3.7%)
    assert -8 < out["exit_pull"] < 0


def test_chase_for_a_deep_blowoff():
    # +90% over the 200d -> the non-chase line is ~ -34% lower -> CHASE, no 50d dip-buy offered
    out = pz.compute(_tech(190.0, 90.0, p50=20.0, off_high=-0.5), grade="stretched")
    assert out is not None and out["stance"] == "chase"
    labels = [lv["label_en"] for lv in out["levels"]]
    assert not any("50-day" in s for s in labels)          # a 50d bounce is still a chase → not shown
    assert any("200-day" in s for s in labels)
    assert out["exit_pull"] <= pz.CHASE_DEPTH
    assert str(abs(round(out["exit_pull"]))) in out["headline_en"]


def test_parabolic_is_always_chase_even_if_barely_extended():
    # own-history parabolic flag forces the chase read regardless of absolute distance
    out = pz.compute(_tech(110.0, 12.0, p50=4.0, off_high=-1.0), grade="parabolic")
    assert out is not None and out["stance"] == "chase" and out["parabolic"] is True


def test_rolling_over_extended_name_gets_no_zone():
    # extended on the 200d but well off its high and below the 50d -> a sell, not a dip -> None
    assert pz.compute(_tech(140.0, 35.0, p50=-3.0, off_high=-25.0, above50=False)) is None


def test_downtrend_suppresses_zone():
    # extended but the cycle is rolling over (dir 'down') -> the 'avoid — downtrend' verdict owns
    # it; no accumulate-on-a-downtrend zone
    assert pz.compute(_tech(135.0, 35.0, p50=6.0, off_high=-1.0), grade="steady",
                      downtrend=True) is None
    # ...still shows when not a downtrend
    assert pz.compute(_tech(135.0, 35.0, p50=6.0, off_high=-1.0), grade="steady",
                      downtrend=False) is not None


def test_levels_sorted_shallow_to_deep():
    out = pz.compute(_tech(140.0, 40.0, p50=8.0, off_high=-2.0), grade="steady")
    assert out is not None
    prices = [lv["price"] for lv in out["levels"]]
    assert prices == sorted(prices, reverse=True)          # shallowest (highest price) first
    assert all(lv["price"] < out["price"] for lv in out["levels"])
