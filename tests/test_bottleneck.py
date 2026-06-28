"""engine.bottleneck — T1 physical-tightness nowcast. Verifies the leg math fires a
TIGHT/SOLD_OUT band + HBM-template regime when the four physical legs all point to a
squeeze (synthetic FRED fixtures, since the live series need network), and that it
degrades to AWAITING_DATA when the store is empty. DISPLAY-ONLY contract.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import bottleneck as bn


def _series(values) -> pd.DataFrame:
    idx = pd.date_range("2020-01-01", periods=len(values), freq="MS")
    return pd.DataFrame({"v": values}, index=idx)


def _tight_store():
    """A fixture where every physical leg signals a squeeze."""
    n = 60
    ramp = np.linspace(0, 1, n)
    return {
        "CAPUTLG3344S": _series(70 + 20 * ramp),        # cap-U ramping high -> leg1 z>0
        "MNFCTRIRSA": _series(1.5 - 0.5 * ramp),         # inv/sales falling -> -z>0 (leg2)
        "AMTMUO": _series(100 + 80 * ramp),              # unfilled orders rising
        "AMTMVS": _series(np.full(n, 50.0)),             # shipments flat -> backlog ratio rising (leg3)
        # PPI flat for 4y then a sharp recent ramp -> latest yoy >> history -> leg4 z>0
        "PCU334413334413": _series(list(np.full(n - 12, 100.0)) +
                                   list(100 * (1 + 0.02 * np.arange(1, 13)))),
    }


def _patch_themes(monkeypatch, tmp_path):
    monkeypatch.setattr(bn.config, "load",
                        lambda: {"themes": {"memory_storage": {"name": "Memory", "tickers": ["MU"]}}})
    monkeypatch.setattr(bn.config, "data_dir", lambda: tmp_path)   # no EDGAR cache -> language None


def test_tight_regime_fires(monkeypatch, tmp_path):
    store = _tight_store()
    monkeypatch.setattr(bn.store, "read", lambda group, name: store.get(name))
    _patch_themes(monkeypatch, tmp_path)
    out = bn.compute_bottleneck(write_ledger=False)
    t = out["themes"]["memory_storage"]
    assert t["legs"]["leg1_capacity"] > 0      # capacity full
    assert t["legs"]["leg2_inventory"] > 0     # inventory drained
    assert t["legs"]["leg3_backlog"] > 0       # backlog building
    assert t["legs"]["leg4_pricing"] > 0       # pricing power
    assert t["regime"] is True                 # HBM template: all four fire
    assert t["band"] in ("TIGHT", "SOLD_OUT")
    assert t["tightness"] > 0.5


def test_awaiting_data_when_store_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(bn.store, "read", lambda group, name: None)
    _patch_themes(monkeypatch, tmp_path)
    out = bn.compute_bottleneck(write_ledger=False)
    t = out["themes"]["memory_storage"]
    assert t["band"] == "AWAITING_DATA"
    assert t["regime"] is False
    assert t["tightness"] is None


def test_loose_regime(monkeypatch, tmp_path):
    n = 60
    ramp = np.linspace(0, 1, n)
    store = {
        "CAPUTLG3344S": _series(90 - 20 * ramp),         # cap-U falling -> leg1 z<0
        "MNFCTRIRSA": _series(1.0 + 0.5 * ramp),          # inv/sales rising -> leg2<0
        "AMTMUO": _series(180 - 80 * ramp),               # backlog shrinking
        "AMTMVS": _series(np.full(n, 50.0)),
        "PCU334413334413": _series(120 - 10 * ramp),      # PPI falling -> leg4<0
    }
    monkeypatch.setattr(bn.store, "read", lambda group, name: store.get(name))
    _patch_themes(monkeypatch, tmp_path)
    out = bn.compute_bottleneck(write_ledger=False)
    t = out["themes"]["memory_storage"]
    assert t["regime"] is False
    assert t["band"] in ("LOOSE", "NEUTRAL")
