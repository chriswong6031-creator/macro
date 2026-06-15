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
    monkeypatch.setattr(bk, "_basket_extras", lambda: None)   # hermetic: ignore the real extras cache
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


def test_extras_union_partial_and_despac(monkeypatch):
    """Off-index members (data/baskets/extras.parquet) resolve instead of being dropped as
    `missing`; recent IPOs are flagged short-history `partial` from their first tape; a member
    only ADDED late (a de-SPAC shell pattern) is flagged from its `added` date, not its early tape."""
    idx = pd.date_range("2024-01-01", periods=400, freq="B")
    closes = pd.DataFrame({                                          # the in-cache, full-history names
        "A": 100 * (1.0010 ** np.arange(400)),
        "B": 100 * (1.0005 ** np.arange(400)),
        "C": 100 * (1.0008 ** np.arange(400)),
    }, index=idx)
    spy = pd.DataFrame({"close": 400 * (1.0006 ** np.arange(400)), "volume": np.ones(400)}, index=idx)
    extras = pd.DataFrame({                                          # off-cache names from the extras store
        "E": np.r_[[np.nan] * 300, 50 * (1.002 ** np.arange(100))],  # recent IPO — tape only the last 100 days
        "F": 20 * (1.0010 ** np.arange(400)),                        # long tape but added late (de-SPAC shell)
    }, index=idx)
    ipo = idx[300].strftime("%Y-%m-%d")
    late = idx[350].strftime("%Y-%m-%d")
    members = {"t": {"name": "T", "category": "X", "created": "2024-01-01", "etf_proxy": None, "members": [
        {"ticker": "A", "added": "2024-01-01", "rationale": "a"},
        {"ticker": "B", "added": "2024-01-01", "rationale": "b"},
        {"ticker": "C", "added": "2024-01-01", "rationale": "c"},
        {"ticker": "E", "added": ipo, "rationale": "ipo"},
        {"ticker": "F", "added": late, "rationale": "despac"}]}}
    monkeypatch.setattr(bk, "_closes", lambda: closes)
    monkeypatch.setattr(bk, "_basket_extras", lambda: extras)
    monkeypatch.setattr(bk, "_names_sectors", lambda: {})
    monkeypatch.setattr(bk.store, "read", lambda g, n: spy if (g, n) == ("yahoo", "SPY") else None)
    monkeypatch.setattr(bk, "_membership", lambda: {"baskets": members})

    b = bk.compute_baskets()["baskets"][0]
    assert {m["symbol"] for m in b["members"]} == {"A", "B", "C", "E", "F"}   # off-cache members resolved
    assert b["missing"] == []                                                  # ...not dropped as missing
    partial = {p["symbol"]: p["from"] for p in b["partial"]}
    assert partial.get("E") == ipo                  # recent IPO: short-history from its first tape
    assert partial.get("F") == late                 # de-SPAC: from `added`, NOT its earlier shell tape
    assert "A" not in partial and "C" not in partial  # full-history names are not flagged
