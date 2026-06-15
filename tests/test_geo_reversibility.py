"""Tests for the deterministic GPR threat/act reversibility cross-check (P3).

engine/dislocation._geopolitical_reversibility is the free, always-available
complement to the default-off LLM catalyst cross-check: on an active dislocation
with elevated geopolitical risk it reads threat-led (reversible-scare) vs act-led
(regime-break) from the GPR split (Caldara-Iacoviello). Like _catalyst_narrative it
is CONTEXT ONLY and must NEVER change the verdict. No network.

Run as a plain script:  python tests/test_geo_reversibility.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import dislocation as dz  # noqa: E402

_THREAT = {"pct": 92.0, "lean": "threat", "threat": 210.0, "act": 150.0}
_ACT = {"pct": 95.0, "lean": "act", "threat": 150.0, "act": 240.0}


def test_corroborates_buyable_threat():
    out = dz._geopolitical_reversibility("buyable_washout", _THREAT)
    assert out and out["agreement"] == "corroborates"
    assert out["reversibility"] == "reversible" and out["lean"] == "threat"
    assert out["is_context_only"] is True
    assert "verdict" not in out                       # never carries the verdict


def test_corroborates_standaside_act():
    out = dz._geopolitical_reversibility("stand_aside", _ACT)
    assert out and out["agreement"] == "corroborates"
    assert out["reversibility"] == "persistent" and out["lean"] == "act"


def test_diverges_buyable_act():
    out = dz._geopolitical_reversibility("buyable_washout", _ACT)
    assert out and out["agreement"] == "diverges"
    assert out["reversibility"] == "persistent"       # gate constructive, geo cautious
    assert "caution" in out["note"].lower()


def test_diverges_standaside_threat():
    out = dz._geopolitical_reversibility("stand_aside", _THREAT)
    assert out and out["agreement"] == "diverges"
    assert out["reversibility"] == "reversible"        # gate knife, geo constructive
    assert "not a green light" in out["note"].lower()


# --------------------------------------------------------------------------- #
# gating — only a live, geopolitically-elevated dislocation with a clear lean fires
# --------------------------------------------------------------------------- #
def test_skips_when_no_dislocation():
    assert dz._geopolitical_reversibility("calm", _THREAT) is None
    assert dz._geopolitical_reversibility("unknown", _ACT) is None


def test_skips_when_gpr_not_elevated():
    low = {"pct": 55.0, "lean": "threat", "threat": 90.0, "act": 70.0}
    assert dz._geopolitical_reversibility("buyable_washout", low) is None


def test_skips_when_no_clear_lean():
    bal = {"pct": 90.0, "lean": "balanced", "threat": 100.0, "act": 100.0}
    assert dz._geopolitical_reversibility("buyable_washout", bal) is None
    none_lean = {"pct": 90.0, "lean": None}
    assert dz._geopolitical_reversibility("buyable_washout", none_lean) is None


def test_skips_when_no_gpr():
    assert dz._geopolitical_reversibility("buyable_washout", None) is None


# --------------------------------------------------------------------------- #
# the store reader never raises and returns None-or-shape
# --------------------------------------------------------------------------- #
def test_gpr_reading_shape():
    r = dz._gpr_reading()
    if r is None:
        return                                         # no store data in this env
    assert set(r) >= {"value", "pct", "lean"}
    assert r["pct"] is None or 0.0 <= r["pct"] <= 100.0
    assert r["lean"] in (None, "threat", "act", "balanced")


def test_snapshot_emits_geo_field_without_changing_verdict():
    """A dislocation snapshot must always carry the geo_reversibility KEY (possibly
    None) and its verdict must be one of the canonical values — the cross-check is
    attached, never substituted."""
    import pandas as pd
    # minimal frame: SPY only, calm tape -> verdict 'calm', geo None
    idx = pd.date_range("2025-01-01", periods=400, freq="B")
    f = pd.DataFrame({"SPY": pd.Series(range(400), index=idx, dtype=float) + 100})
    snap = dz.snapshot(f)
    assert "geo_reversibility" in snap
    assert snap["verdict"] in ("calm", "buyable_washout", "stand_aside", "unknown")
    # calm tape -> the cross-check is dormant
    assert snap["geo_reversibility"] is None


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
