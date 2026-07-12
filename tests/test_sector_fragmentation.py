"""Rotation Command W1 — RC-R6 fragmentation index (engine/sector_fragmentation.py).

Network-free synthetic legs: a sector whose legs disagree hard (one +9%, one −18% over
20 sessions) must flag fragmented with honest bilingual copy; a homogeneous sector must
not. One failing sector must never kill the board.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import sector_fragmentation as sf


def _series(daily_ret: float, n: int = 320, tail: int = 20, tail_ret: float | None = None,
            seed: int = 7):
    """Drifted series with deterministic ±0.5% noise so the ratio-z has a real
    variance history (a zero-variance baseline makes any move infinitely abnormal)."""
    rng = np.random.default_rng(seed)
    noise = rng.normal(0.0, 0.005, n)
    idx = pd.bdate_range("2024-01-02", periods=n)
    vals = [100.0]
    for k in range(1, n):
        r = tail_ret if (tail_ret is not None and k >= n - tail) else daily_ret
        vals.append(vals[-1] * (1.0 + r + noise[k]))
    return pd.Series(vals, index=idx)


def _sector(legs: dict, etf=None):
    cfg = {"key": "xlk", "etf": "XLK", "name_en": "Technology", "name_zh": "科技",
           "legs": [{"key": k, "tier": "secondary", "name_en": k.title(), "name_zh": k}
                    for k in legs]}
    return {"cfg": cfg, "etf_close": etf if etf is not None else _series(0.0),
            "legs": legs, "leg_meta": {}}


def test_fragmented_when_legs_disagree():
    legs = {"mag7": _series(0.0, tail_ret=0.0045, seed=1),     # ≈ +9% over the last 20
            "memory": _series(0.0, tail_ret=-0.0095, seed=2)}  # ≈ −17%
    row = sf.sector_row(_sector(legs))
    assert row is not None
    assert row["fragmented"] is True
    assert row["opposite_signs"] is True
    assert row["spread"] > 0.20
    assert "not be representative" in row["copy_en"]
    assert "板块聚合读数或失真" in row["copy_zh"]
    # ranked: best leg first
    assert row["legs"][0]["key"] == "mag7" and row["legs"][-1]["key"] == "memory"


def test_not_fragmented_when_homogeneous():
    legs = {"a": _series(0.0, tail_ret=0.0012, seed=3), "b": _series(0.0, tail_ret=0.0006, seed=4)}
    row = sf.sector_row(_sector(legs))
    assert row is not None
    assert row["fragmented"] is False
    assert row["copy_en"] is None


def test_single_leg_sector_returns_none():
    assert sf.sector_row(_sector({"only": _series(0.001)})) is None


def test_compute_survives_a_broken_sector():
    good = _sector({"a": _series(0.0, tail_ret=0.005), "b": _series(0.0, tail_ret=-0.008)})
    broken = {"cfg": {"key": "bad", "etf": "BAD", "name_en": "Bad", "name_zh": "坏",
                      "legs": [{"key": "x", "name_en": "X", "name_zh": "X"}]},
              "etf_close": None, "legs": {"x": None}, "leg_meta": {}}
    out = sf.compute({"xlk": good, "bad": broken}, generated_utc="test")
    assert out["ok"] is True
    assert out["schema"] == "sector_fragmentation.v1"
    assert out["authority"]["may_gate"] is False
    assert len(out["sectors"]) == 1
    assert out["n_fragmented"] == 1
