"""Thematic-baskets engine (engine.baskets.compute_baskets).

Equal-weight with point-in-time dated membership over the free price cache:
verify the EW return math, that members outside the cache are excluded and counted
(n_missing), that a removed member drops out of the latest weights, that thin
baskets (<3 names present) are skipped, and that relative-to-SPY is basket−SPY.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import baskets as bk


def _setup(monkeypatch, members):
    idx = pd.date_range("2025-01-02", periods=180, freq="B")
    # deterministic, distinct trends so EW != any single name
    closes = pd.DataFrame({
        "A": 100 * (1.001 ** np.arange(180)),
        "B": 100 * (1.002 ** np.arange(180)),
        "C": 100 * (0.999 ** np.arange(180)),
        "D": 100 * (1.0005 ** np.arange(180)),
    }, index=idx)
    spy = pd.DataFrame({"close": 400 * (1.0008 ** np.arange(180)),
                        "volume": np.ones(180)}, index=idx)
    monkeypatch.setattr(bk, "_closes", lambda: closes)
    monkeypatch.setattr(bk, "_names_sectors",
                        lambda: {t: (f"{t} Inc", "Tech") for t in "ABCD"})
    monkeypatch.setattr(bk.store, "read",
                        lambda g, n: spy if (g, n) == ("yahoo", "SPY") else None)
    monkeypatch.setattr(bk, "_membership", lambda: {"seed_date": "2025-01-02",
                                                    "curated": "2026-06-14", "note": "x",
                                                    "baskets": members})
    return closes, spy


def test_equal_weight_pit_and_missing(monkeypatch):
    members = {
        "t1": {"name": "Theme One", "category": "Tech", "etf_proxy": None,
               "created": "2025-01-02", "curated": "2026-06-14", "omitted": ["ZZZ"],
               "members": [
                   {"ticker": "A", "added": "2025-01-02", "removed": None, "note": "seed"},
                   {"ticker": "B", "added": "2025-01-02", "removed": None, "note": "seed"},
                   {"ticker": "C", "added": "2025-01-02", "removed": None, "note": "seed"},
                   {"ticker": "X", "added": "2025-01-02", "removed": None, "note": "seed"},  # not in cache
               ]},
        "thin": {"name": "Too Thin", "category": "Tech", "etf_proxy": None,
                 "created": "2025-01-02", "curated": "2026-06-14",
                 "members": [{"ticker": "A", "added": "2025-01-02", "removed": None},
                             {"ticker": "B", "added": "2025-01-02", "removed": None}]},
    }
    _setup(monkeypatch, members)
    out = bk.compute_baskets()
    assert out is not None
    ids = [b["id"] for b in out["baskets"]]
    assert ids == ["t1"]                              # thin (<3 present) skipped
    b = out["baskets"][0]
    assert b["n"] == 3 and b["n_missing"] == 1        # X excluded + counted
    assert len(b["members"]) == 3
    assert abs(sum(m["weight"] for m in b["members"]) - 1.0) < 2e-3   # weights rounded to 4dp for display
    # relative = raw − SPY over the same horizon (identity check vs an independent SPY calc)
    spy_ret = pd.Series(400 * (1.0008 ** np.arange(180)),
                        index=pd.date_range("2025-01-02", periods=180, freq="B")).pct_change()
    assert b["ret"]["rel"]["d20"] == round(b["ret"]["raw"]["d20"] - bk._hz(spy_ret, 20), 2)
    assert len(b["spark"]) > 1 and len(b["spy_spark"]) == len(b["spark"])


def test_removed_member_drops_from_latest(monkeypatch):
    members = {
        "t1": {"name": "Theme", "category": "Tech", "etf_proxy": None,
               "created": "2025-01-02", "curated": "2026-06-14",
               "members": [
                   {"ticker": "A", "added": "2025-01-02", "removed": None},
                   {"ticker": "B", "added": "2025-01-02", "removed": None},
                   {"ticker": "C", "added": "2025-01-02", "removed": None},
                   {"ticker": "D", "added": "2025-01-02", "removed": "2025-03-01"},  # dropped mid-series
               ]},
    }
    _setup(monkeypatch, members)
    out = bk.compute_baskets()
    b = out["baskets"][0]
    held = {m["ticker"] for m in b["members"]}
    assert "D" not in held and held == {"A", "B", "C"}   # D removed before the last date
    assert b["n"] == 3


def test_degrades_without_membership(monkeypatch):
    monkeypatch.setattr(bk, "_membership", lambda: None)
    assert bk.compute_baskets() is None
