"""Alert-rule tests: engineered frames + a real historical slice."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.alerts import (  # noqa: E402
    _regime_history,
    hy_oas_widening,
    net_liquidity_roc_flip,
    transition_state_change,
)


def _mk_hist(states: list[str]) -> pd.DataFrame:
    idx = pd.bdate_range("2024-01-01", periods=len(states))
    return pd.DataFrame({
        "quad": "Q1", "transition_state": states,
        "n_flags": [2] * len(states),
        "growth_confidence": 0.5, "inflation_confidence": 0.5,
    }, index=idx)


def test_transition_change_fires() -> None:
    hist = _mk_hist(["STABLE"] * 5 + ["WEAKENING"])
    a = transition_state_change(hist, pd.DataFrame())
    assert a is not None and "STABLE -> WEAKENING" in a.message


def test_transition_no_change_silent() -> None:
    hist = _mk_hist(["STABLE"] * 6)
    assert transition_state_change(hist, pd.DataFrame()) is None


def test_liquidity_flip_fires() -> None:
    idx = pd.bdate_range("2024-01-01", periods=60)
    nl = pd.Series(np.linspace(0, 100, 60), index=idx)   # rising RoC
    nl.iloc[-2:] = nl.iloc[-22] - 40                      # last 2 days: 20d change sharply negative,
                                                          # holds >=confirm days and clears the deadband
    f = pd.DataFrame({"net_liquidity_bn": nl})
    a = net_liquidity_roc_flip(None, f)
    assert a is not None and "contracting" in a.message


def test_oas_widening_fires() -> None:
    idx = pd.bdate_range("2023-01-01", periods=300)
    oas = pd.Series(3.5 + np.random.default_rng(1).normal(0, 0.02, 300), index=idx)
    oas.iloc[-1] = oas.iloc[-2] + 0.5                     # half-point single-day widening
    f = pd.DataFrame({"hy_oas": oas})
    a = hy_oas_widening(None, f)
    assert a is not None and "sigma" in a.message


def test_oas_quiet_day_silent() -> None:
    idx = pd.bdate_range("2023-01-01", periods=300)
    oas = pd.Series(3.5 + np.random.default_rng(2).normal(0, 0.02, 300), index=idx)
    f = pd.DataFrame({"hy_oas": oas})
    assert hy_oas_widening(None, f) is None


def test_historical_state_changes_detectable() -> None:
    """Replay the rule at real state-change dates in stored history."""
    hist = _regime_history()
    if hist is None or len(hist) < 100:
        print("  (no stored history — skipped)")
        return
    chg = hist["transition_state"].ne(hist["transition_state"].shift())
    change_dates = hist.index[chg][-5:]
    fired = 0
    for d in change_dates:
        sub = hist.loc[:d]
        if len(sub) < 2:
            continue
        if transition_state_change(sub, pd.DataFrame()) is not None:
            fired += 1
    assert fired >= max(1, len(change_dates) - 1), f"only {fired} fired of {len(change_dates)}"


if __name__ == "__main__":
    for fn in [test_transition_change_fires, test_transition_no_change_silent,
               test_liquidity_flip_fires, test_oas_widening_fires,
               test_oas_quiet_day_silent, test_historical_state_changes_detectable]:
        fn()
        print(f"PASS {fn.__name__}")
    print("all alert tests passed")
