"""Cycle engine tests on synthetic fixtures."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.cycles import (  # noqa: E402
    _EQ_BEARISH, _EQ_BULLISH, _eq_grade, _eq_proximity, analyze, bottom_confidence,
    bottom_confidence_fields, cycle_state, early_signals, entry_quality,
    entry_quality_fields, find_troughs, ladder_state, mtf_snapshot, signal_age,
    signal_age_fields, STATE_DISPLAY,
)

IDX = pd.bdate_range("2020-01-01", periods=520)


def synth_cycles(period: int = 40, crest_at: float = 0.5, n: int = 520) -> pd.Series:
    """Sawtooth-ish cycles with adjustable crest position + uptrend + noise."""
    rng = np.random.default_rng(3)
    t = np.arange(n)
    phase = (t % period) / period
    cyc = np.where(phase < crest_at, phase / crest_at, (1 - phase) / (1 - crest_at))
    price = 100 * np.exp(0.0004 * t) * (1 + 0.06 * cyc) + rng.normal(0, 0.15, n)
    return pd.Series(price, index=pd.bdate_range("2020-01-01", periods=n))


def test_trough_spacing() -> None:
    c = synth_cycles(period=40)
    troughs = find_troughs(c)
    gaps = np.diff([c.index.get_loc(t) for t in troughs])
    assert 30 <= np.median(gaps) <= 50, f"median gap {np.median(gaps)}"


def test_translation_right() -> None:
    c = synth_cycles(period=40, crest_at=0.75)
    st = cycle_state(c)
    assert st["translation"] == "right", st["translation"]


def test_translation_left() -> None:
    c = synth_cycles(period=40, crest_at=0.25)
    st = cycle_state(c)
    assert st["translation"] == "left", st["translation"]


def test_failed_cycle_flag() -> None:
    c = synth_cycles(period=40)
    # force a break below the last cycle low
    c.iloc[-3:] = c.min() * 0.95
    st = cycle_state(c)
    assert st["failed_cycle"] is True


def test_ladder_states_sane() -> None:
    c = synth_cycles(period=40)
    st = ladder_state(cycle_state(c), mtf_snapshot(c))
    assert st["state"] in ("BOTTOM WATCH", "TURN SIGNALED", "FRESH BUY", "RALLY ON",
                           "TOP WATCH", "ROLLING OVER", "DECLINE", "COUNTERTREND BOUNCE")
    assert -100 <= st["score"] <= 100
    assert st["why"] and st["next"]


def test_decline_on_breakdown() -> None:
    c = synth_cycles(period=40)
    c.iloc[-15:] = np.linspace(float(c.iloc[-16]), float(c.min() * 0.85), 15)
    st = ladder_state(cycle_state(c), mtf_snapshot(c))
    assert st["state"] in ("DECLINE", "ROLLING OVER"), st["state"]


def test_signal_age_detects_recent_cross() -> None:
    """A series engineered to flip its state in the last few bars should report
    a small, non-capped age and name the state it switched away from."""
    c = synth_cycles(period=40)
    cur = ladder_state(cycle_state(c), mtf_snapshot(c))["state"]
    age = signal_age(c, cur)
    assert age, "signal_age returned empty on a 520-bar series"
    assert 0 <= age["days"] <= 45
    # synthetic data isn't a 45-day-stable trend, so it should find a real cross
    assert age["capped"] is False
    assert age["prev_state"] is not None and age["prev_state"] != cur


def test_signal_age_contract_holds() -> None:
    """Whatever the lookback, the two branches stay self-consistent: a capped
    result reports exactly max_lookback days with no prior state/date; an
    uncapped one reports an in-range age, a different prior state, and a date."""
    c = synth_cycles(period=40)
    cur = ladder_state(cycle_state(c), mtf_snapshot(c))["state"]
    for lb in (1, 3, 45):
        age = signal_age(c, cur, max_lookback=lb)
        assert age, f"empty at max_lookback={lb}"
        if age["capped"]:
            assert age["days"] == lb
            assert age["prev_state"] is None and age["date"] is None
        else:
            assert 0 <= age["days"] < lb
            assert age["prev_state"] is not None and age["prev_state"] != cur
            assert age["date"] is not None


def test_signal_age_thin_history() -> None:
    """Under the history floor, signal_age bows out cleanly (no crash)."""
    c = synth_cycles(period=40, n=120)
    assert signal_age(c, "FRESH BUY") == {}


def test_signal_age_fields_prose() -> None:
    fresh = signal_age_fields("FRESH BUY", 80,
                              {"days": 3, "capped": False, "prev_state": "TURN SIGNALED",
                               "date": "2026-06-05"})
    assert "3 trading days ago" in fresh["age_line"]
    assert "3天前" in fresh["age_short_zh"] or "3天前" in fresh["age_line_zh"]
    assert fresh["strength"] == "strong" and "+80" in fresh["age_line"]
    today = signal_age_fields("FRESH BUY", 80, {"days": 0, "capped": False,
                                                "prev_state": None, "date": "2026-06-13"})
    assert "today" in today["age_line"] and today["age_short"] == "today"
    capped = signal_age_fields("RALLY ON", 55, {"days": 45, "capped": True,
                                                "prev_state": None, "date": None})
    assert "45+" in capped["age_line"] and "established" in capped["age_line"]


def test_analyze_attaches_age() -> None:
    res = analyze(synth_cycles(period=40))
    lad = res["ladder"]
    assert "age_days" in lad and "age_line" in lad and "age_short" in lad
    assert lad["state"] in lad["age_line"] or \
        any(w in lad["age_line"] for w in ("BUY", "UPTREND", "TOPPING", "BOTTOM",
                                           "DOWNTREND", "HIGH", "LOW", "BOUNCE"))


def test_eq_proximity_peaks_near_the_low() -> None:
    """The dominant lever: proximity must peak just above the pivot and decay as
    price runs away — and a broken pivot (below the low) is discounted."""
    f = _eq_proximity
    assert f(0.01, True) > f(0.10, True) > f(0.20, True)   # nearer the low = higher
    assert f(0.02, True) >= 0.9                              # sweet spot near 1
    assert f(-0.10, True) <= 0.2                             # deep below pivot = knife
    # short side mirrors: 'near the high' (small negative pct) scores high
    assert f(-0.01, False) > f(-0.10, False)
    # the curve must be CONTINUOUS — no cliff at any breakpoint (esp. -0.03)
    xs = [x / 1000 for x in range(-90, 260)]
    for a, b in zip(xs, xs[1:]):
        assert abs(f(b, True) - f(a, True)) < 0.05, f"jump near {b:.3f}"


def test_eq_grade_bands() -> None:
    assert _eq_grade(75)[0] == "strong"
    assert _eq_grade(-45)[0] == "solid"
    assert _eq_grade(20)[0] == "light"
    assert _eq_grade(5)[0] == "minimal"


def test_eq_sign_anchored_to_state() -> None:
    """The score's SIGN must follow the ladder state, never contradict it."""
    c = synth_cycles(period=40)
    cyc = cycle_state(c)
    mtf = mtf_snapshot(c)
    early = early_signals(c, cyc, mtf)
    reg = {"regime": "neutral"}
    for st in _EQ_BULLISH:
        eq = entry_quality(c, cyc, mtf, early, reg, state=st)
        assert eq and eq["score"] >= 0, f"{st} should be >=0, got {eq}"
    for st in _EQ_BEARISH:
        eq = entry_quality(c, cyc, mtf, early, reg, state=st)
        assert eq and eq["score"] <= 0, f"{st} should be <=0, got {eq}"


def test_eq_every_state_classified() -> None:
    """Every displayed ladder state is bullish or bearish (no silent fallback)."""
    for st in STATE_DISPLAY:
        assert st in _EQ_BULLISH or st in _EQ_BEARISH, f"{st} unclassified"


def test_eq_thin_history_bows_out() -> None:
    c = synth_cycles(period=40, n=120)
    assert entry_quality(c, cycle_state(c) or {"x": 1}, {"D": {}}, {}, {"regime": "neutral"}) == {}


def test_eq_fields_and_analyze() -> None:
    fields = entry_quality_fields({"score": 58.0, "pct_from_low": 4.2})
    assert fields["eq_dir"] == "up" and "+58" in fields["eq_badge"]
    assert "drawdown" in fields["eq_tip"] and "return forecast" in fields["eq_tip"]
    neg = entry_quality_fields({"score": -40.0, "pct_from_low": 1.0})
    assert neg["eq_dir"] == "down" and neg["eq_badge"].startswith("▼")
    res = analyze(synth_cycles(period=40))
    assert "eq_score" in res["ladder"] and -100 <= res["ladder"]["eq_score"] <= 100


def test_bottom_confidence_confluence_and_gating() -> None:
    full = {"D": {"macd_cross_up": True}, "3D": {"macd_cross_up": True},
            "W": {"macd_cross_up": True}, "M": {"macd_cross_up": True}}
    none = {"D": {}, "3D": {}, "W": {}, "M": {}}
    eq = {"long": 80.0}
    # full multi-TF confluence => no discount (bc == entry quality)
    assert bottom_confidence(full, eq, "FRESH BUY")["score"] == 80.0
    # zero confluence => the floor (0.55 x long)
    assert abs(bottom_confidence(none, eq, "FRESH BUY")["score"] - 44.0) < 0.1
    # confluence only DISCOUNTS, never inflates
    assert bottom_confidence(none, eq, "FRESH BUY")["score"] <= eq["long"]
    # non-bottoming states get no bottom-confidence at all
    assert bottom_confidence(full, eq, "RALLY ON") == {}
    assert bottom_confidence(full, eq, "TOP WATCH") == {}
    # counter-trend bounce is capped into the high-risk band
    assert bottom_confidence(full, {"long": 95.0}, "COUNTERTREND BOUNCE")["score"] <= 30
    # a missing monthly bar renormalises (no silent cap, no crash)
    bc = bottom_confidence({"D": {"macd_cross_up": True}, "3D": {}, "W": {"macd_cross_up": True}},
                           eq, "TURN SIGNALED")
    assert 0 < bc["score"] <= 80 and bc["monthly_avail"] is False
    # fields render a per-timeframe line + a grade
    f = bottom_confidence_fields(bottom_confidence(full, eq, "FRESH BUY"))
    assert "Weekly ✓" in f["bc_line"] and f["bc_grade"] == "strong"


if __name__ == "__main__":
    for fn in [test_trough_spacing, test_translation_right, test_translation_left,
               test_failed_cycle_flag, test_ladder_states_sane, test_decline_on_breakdown,
               test_signal_age_detects_recent_cross, test_signal_age_contract_holds,
               test_signal_age_thin_history, test_signal_age_fields_prose,
               test_analyze_attaches_age, test_eq_proximity_peaks_near_the_low,
               test_eq_grade_bands, test_eq_sign_anchored_to_state,
               test_eq_every_state_classified, test_eq_thin_history_bows_out,
               test_eq_fields_and_analyze, test_bottom_confidence_confluence_and_gating]:
        fn()
        print(f"PASS {fn.__name__}")
    print("all cycle tests passed")
