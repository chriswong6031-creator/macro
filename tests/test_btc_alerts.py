"""Bitcoin Vector alert-engine tests — synthetic, no network.

Run: .venv/bin/python -m tests.test_btc_alerts
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import btc_alerts as A  # noqa: E402
from lib import config  # noqa: E402


def _flat_then_crash(n_pre=400, crash_pct=-0.25) -> pd.DataFrame:
    """Quiet hourly tape, then a one-bar acute crash, then recovery."""
    rng = np.random.default_rng(0)
    px = [50000.0]
    for _ in range(n_pre - 1):
        px.append(px[-1] * (1 + rng.normal(0, 0.002)))
    px.append(px[-1] * (1 + crash_pct))          # the crash hour
    for _ in range(200):
        px.append(px[-1] * (1 + rng.normal(0.0003, 0.002)))  # slow recovery
    idx = pd.date_range("2024-01-01", periods=len(px), freq="h")
    close = pd.Series(px, index=idx)
    return pd.DataFrame({"open": close, "high": close * 1.001,
                         "low": close * 0.999, "close": close, "volume": 1.0}, index=idx)


def test_flash_state_machine_detects_and_recovers() -> None:
    cfg = config.load()["vector"]["alerts"]
    hourly = _flat_then_crash()
    states = A.flash_crash_states(hourly, cfg)
    assert (states == "normal").iloc[:300].all()          # quiet before
    assert states.isin(["flash_crash", "tail_risk_event"]).any()  # fired
    assert states.iloc[-1] == "normal"                    # recovered to normal


def test_flash_machine_ignores_normal_chop() -> None:
    cfg = config.load()["vector"]["alerts"]
    idx = pd.date_range("2024-01-01", periods=600, freq="h")
    rng = np.random.default_rng(3)
    close = pd.Series(50000 * np.exp(np.cumsum(rng.normal(0, 0.006, 600))), index=idx)
    hourly = pd.DataFrame({"open": close, "high": close * 1.002,
                           "low": close * 0.998, "close": close, "volume": 1.0}, index=idx)
    states = A.flash_crash_states(hourly, cfg)
    # ordinary 0.6%/hr chop must not trip the acute-drop machine
    assert (states == "normal").mean() > 0.9


def test_event_schema_and_idempotent_ids() -> None:
    cfg = config.load()["vector"]["alerts"]
    ev = A.flash_events(_flat_then_crash(), cfg)
    assert ev, "expected at least one flash event"
    for e in ev:
        assert {"id", "ts", "source", "type", "severity", "headline",
                "detail", "context", "anchor"} <= set(e)
        assert e["source"] == "vector"
        assert e["severity"] in ("high", "medium", "info")
    # same input -> same ids (deterministic, dedup-safe)
    ids2 = [e["id"] for e in A.flash_events(_flat_then_crash(), cfg)]
    assert [e["id"] for e in ev] == ids2


def test_daily_state_events_on_transitions() -> None:
    idx = pd.date_range("2024-01-01", periods=10, freq="D")
    sig = pd.DataFrame({
        "close": np.linspace(50000, 60000, 10),
        "risk_index": [10, 10, 30, 30, 30, 10, 10, 10, 10, 10],
        "risk_regime": ["low_risk"] * 2 + ["high_risk"] * 3 + ["low_risk"] * 5,
        "structure": np.zeros(10), "structure_state": ["neutral"] * 10,
        "momentum": np.zeros(10), "momentum_state": ["neutral"] * 10,
        "alloc_optimal": [1.0] * 10,
    }, index=idx)
    ev = A.daily_state_events(sig)
    regime_ev = [e for e in ev if e["type"] == "risk_regime"]
    assert len(regime_ev) == 2  # one into high_risk, one back to low_risk
    assert "High Risk" in regime_ev[0]["headline"] or "High Risk" in regime_ev[1]["headline"]


if __name__ == "__main__":
    for fn in [test_flash_state_machine_detects_and_recovers,
               test_flash_machine_ignores_normal_chop,
               test_event_schema_and_idempotent_ids,
               test_daily_state_events_on_transitions]:
        fn()
        print(f"PASS {fn.__name__}")
    print("all btc alert tests passed")
