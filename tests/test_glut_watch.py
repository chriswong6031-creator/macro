"""engine.glut_watch — exit-risk mirror of the bottleneck. Verifies the GLUT band + regime
fire when all four supply-catching-up legs turn (cap-U rolling over, inventories restocking,
backlog draining, pricing fading), via synthetic FRED fixtures, and that it degrades to
AWAITING_DATA when the store is empty. DISPLAY-ONLY contract.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import bottleneck as bn
from engine import glut_watch as gw


def _s(values) -> pd.DataFrame:
    idx = pd.date_range("2018-01-01", periods=len(values), freq="MS")
    return pd.DataFrame({"v": values}, index=idx)


def _glut_store():
    """A fixture where the bottleneck is unwinding: every supply-catching-up leg turns."""
    up = np.linspace(0, 1, 60)
    return {
        "CAPUTLG3344S": _s(np.concatenate([70 + 20 * up, np.linspace(90, 80, 12)])),   # cap-U peaks then rolls over
        "MNFCTRIRSA":   _s(np.concatenate([1.5 - 0.4 * up, np.linspace(1.1, 1.5, 12)])),  # inv/sales bottoms then restocks
        "AMTMUO":       _s(np.concatenate([100 + 80 * up, np.linspace(180, 110, 12)])),  # backlog peaks then drains
        "AMTMVS":       _s(np.full(72, 50.0)),
        "PCU334413334413": _s(np.concatenate([100 * (1 + 0.5 * up), np.full(12, 150.0)])),  # PPI rips then flat -> yoy decel
        "CAPG3344S":    _s(np.linspace(100, 160, 72)),                                   # capacity expanding (supply response)
    }


def _patch(monkeypatch, store):
    monkeypatch.setattr(bn.store, "read", lambda group, name: store.get(name))
    monkeypatch.setattr(gw.config, "load",
                        lambda: {"themes": {"memory_storage": {"name": "Memory", "tickers": ["MU"]}}})


def test_glut_regime_fires(monkeypatch):
    _patch(monkeypatch, _glut_store())
    out = gw.compute_glut_watch(demand={"themes": {}}, write_ledger=False)
    t = out["themes"]["memory_storage"]
    assert t["legs"]["leg1_caputil_rollover"] > 0    # cap-U rolling over
    assert t["legs"]["leg2_inventory_restock"] > 0   # inventories restocking
    assert t["legs"]["leg3_backlog_drain"] > 0       # backlog draining
    assert t["legs"]["leg4_pricing_fade"] > 0        # pricing fading
    assert t["regime"] is True
    assert t["band"] in ("GLUT_FORMING", "GLUT")


def test_cooling_demand_escalates_band(monkeypatch):
    _patch(monkeypatch, _glut_store())
    base = gw.compute_glut_watch(demand={"themes": {}}, write_ledger=False)["themes"]["memory_storage"]["band"]
    # a cooling customer-capex pool brings the glut closer (display nuance)
    esc = gw.compute_glut_watch(
        demand={"themes": {"memory_storage": {"demand_band": "COOLING"}}},
        write_ledger=False)["themes"]["memory_storage"]["band"]
    order = ["STABLE", "EARLY_GLUT", "GLUT_FORMING", "GLUT"]
    assert order.index(esc) >= order.index(base)


def test_awaiting_when_store_empty(monkeypatch):
    monkeypatch.setattr(bn.store, "read", lambda group, name: None)
    monkeypatch.setattr(gw.config, "load",
                        lambda: {"themes": {"memory_storage": {"name": "M", "tickers": ["MU"]}}})
    out = gw.compute_glut_watch(demand={"themes": {}}, write_ledger=False)
    assert out["themes"]["memory_storage"]["band"] == "AWAITING_DATA"
    assert out["themes"]["memory_storage"]["regime"] is False
