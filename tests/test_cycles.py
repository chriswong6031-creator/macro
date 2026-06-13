"""Cycle engine tests on synthetic fixtures."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.cycles import cycle_state, find_troughs, ladder_state, mtf_snapshot  # noqa: E402

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
                           "TOP WATCH", "ROLLING OVER", "DECLINE")
    assert -100 <= st["score"] <= 100
    assert st["why"] and st["next"]


def test_decline_on_breakdown() -> None:
    c = synth_cycles(period=40)
    c.iloc[-15:] = np.linspace(float(c.iloc[-16]), float(c.min() * 0.85), 15)
    st = ladder_state(cycle_state(c), mtf_snapshot(c))
    assert st["state"] in ("DECLINE", "ROLLING OVER"), st["state"]


if __name__ == "__main__":
    for fn in [test_trough_spacing, test_translation_right, test_translation_left,
               test_failed_cycle_flag, test_ladder_states_sane, test_decline_on_breakdown]:
        fn()
        print(f"PASS {fn.__name__}")
    print("all cycle tests passed")
