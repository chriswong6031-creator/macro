"""Thematic-baskets engine (engine.baskets.compute_baskets).

Equal-weight with point-in-time dated membership over the free cache. The engine now
emits a dense CHART level matrix (for the interactive chart + live σ/sort table) plus
BASKETS metadata with per-horizon perf (raw+rel), enriched members (symbol, rationale,
last, ret_20d, ret_ytd), reference cross-check and hygiene flags. Verify: thin baskets
skipped, members outside the cache surfaced in `missing`, removed members drop from the
latest roster, rel == ret − benchmark at a horizon, and the CHART matrix is well-formed.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import baskets as bk


def _setup(monkeypatch, members):
    idx = pd.date_range("2025-01-02", periods=180, freq="B")
    closes = pd.DataFrame({
        "A": 100 * (1.001 ** np.arange(180)),
        "B": 100 * (1.002 ** np.arange(180)),
        "C": 100 * (0.999 ** np.arange(180)),
        "D": 100 * (1.0005 ** np.arange(180)),
    }, index=idx)
    spy = pd.DataFrame({"close": 400 * (1.0008 ** np.arange(180)),
                        "volume": np.ones(180)}, index=idx)
    monkeypatch.setattr(bk, "_closes", lambda: closes)
    monkeypatch.setattr(bk, "_names_sectors", lambda: {t: (f"{t} Inc", "Tech") for t in "ABCD"})
    monkeypatch.setattr(bk.store, "read", lambda g, n: spy if (g, n) == ("yahoo", "SPY") else None)
    monkeypatch.setattr(bk, "_membership", lambda: {"baskets": members})
    return closes, spy, idx


def test_pit_membership_missing_chart_and_rel(monkeypatch):
    members = {
        "t1": {"name": "Theme One", "category": "Tech", "etf_proxy": None, "created": "2025-01-02",
               "thesis": "x", "members": [
                   {"ticker": "A", "added": "2025-01-02", "removed": None, "rationale": "ra"},
                   {"ticker": "B", "added": "2025-01-02", "removed": None, "rationale": "rb"},
                   {"ticker": "C", "added": "2025-01-02", "removed": None, "rationale": "rc"},
                   {"ticker": "X", "added": "2025-01-02", "removed": None, "rationale": "rx"}]},  # not in cache
        "thin": {"name": "Too Thin", "category": "Tech", "created": "2025-01-02",
                 "members": [{"ticker": "A", "added": "2025-01-02"}, {"ticker": "B", "added": "2025-01-02"}]},
    }
    _, spy, idx = _setup(monkeypatch, members)
    out = bk.compute_baskets()
    assert out is not None
    assert [b["id"] for b in out["baskets"]] == ["t1"]              # thin (<3 present) skipped
    b = out["baskets"][0]
    assert b["n_members"] == 3 and b["missing"] == ["X"]            # X excluded + surfaced
    assert {m["symbol"] for m in b["members"]} == {"A", "B", "C"}
    assert all(m.get("rationale") for m in b["members"])            # rationale carried
    assert all(m.get("last") is not None for m in b["members"])     # enriched with last price
    # rel == ret − benchmark over the same (level-based) 20d window
    br = spy["close"].iloc[-1] / spy["close"].iloc[-21] - 1
    assert abs(b["perf"]["20d"]["rel"] - (b["perf"]["20d"]["ret"] - br)) < 1e-6
    # CHART matrix well-formed
    c = out["chart"]
    assert len(c["dates"]) == 180 and len(c["bench"]) == 180
    assert "t1" in c["baskets"] and len(c["baskets"]["t1"]) == 180
    assert c["baskets"]["t1"][-1] is not None


def test_removed_member_drops_from_latest(monkeypatch):
    members = {"t1": {"name": "Theme", "category": "Tech", "created": "2025-01-02", "members": [
        {"ticker": "A", "added": "2025-01-02"}, {"ticker": "B", "added": "2025-01-02"},
        {"ticker": "C", "added": "2025-01-02"}, {"ticker": "D", "added": "2025-01-02", "removed": "2025-03-01"}]}}
    _setup(monkeypatch, members)
    b = bk.compute_baskets()["baskets"][0]
    assert {m["symbol"] for m in b["members"]} == {"A", "B", "C"} and b["n_members"] == 3


def test_reference_blend_and_market_adjusted(monkeypatch):
    members = {"t1": {"name": "T", "category": "Tech", "created": "2025-01-02",
                      "etf_proxy": ["E1", "E2"], "members": [
                          {"ticker": "A", "added": "2025-01-02"}, {"ticker": "B", "added": "2025-01-02"},
                          {"ticker": "C", "added": "2025-01-02"}]}}
    _, spy, idx = _setup(monkeypatch, members)
    rng = np.random.default_rng(0)
    etf = {s: pd.DataFrame({"close": 50 * np.cumprod(1 + rng.normal(0, 0.01, 180))}, index=idx) for s in ("E1", "E2")}
    monkeypatch.setattr(bk.store, "read",
                        lambda g, n: spy if n == "SPY" else etf.get(n))
    b = bk.compute_baskets()["baskets"][0]
    assert b["reference"] is not None
    assert b["reference"]["label"] == "E1+E2"                        # ETF blend
    assert "corr" in b["reference"] and "rel_corr" in b["reference"]  # absolute + market-adjusted


def test_degrades_without_membership(monkeypatch):
    monkeypatch.setattr(bk, "_membership", lambda: None)
    assert bk.compute_baskets() is None
