"""Tests for engine/hk_market_drivers.py — deterministic HK cross-asset attribution.

Display-only; bilingual; degrades to verdict='unknown'.
"""
from __future__ import annotations

import pytest

from engine import hk_market_drivers as md


def test_drivers_bilingual_and_well_formed():
    """Every driver has EN + ZH labels and a non-empty leg fingerprint."""
    for key, spec in md.DRIVERS.items():
        assert spec["label"] and spec["pos"] and spec["neg"]
        assert key in md.DRIVERS_ZH and len(md.DRIVERS_ZH[key]) == 3
        assert spec["legs"], f"{key} has no legs"
        for col, mtype, sign, w, lw in spec["legs"]:
            assert mtype in ("d", "p")
            assert sign != 0 and w > 0


def test_names_cover_all_legs():
    cols = {leg[0] for spec in md.DRIVERS.values() for leg in spec["legs"]}
    for c in cols:
        assert c in md.NAMES, f"{c} missing EN name"
        assert c in md.NAMES_ZH, f"{c} missing ZH name"


def test_snapshot_runs_and_shape():
    snap = md.snapshot()
    assert "verdict" in snap
    assert snap["verdict"] in ("clear", "mixed", "quiet", "unknown")
    if snap["verdict"] != "unknown":
        assert snap["primary_label"] and snap["primary_label_zh"]
        assert snap["headline"]
        assert snap["confidence"] in ("low", "medium", "high")
        for lg in snap.get("evidence_legs", []):
            assert lg["en"] and lg["zh"]
        assert snap["note"]


def test_assemble_frame_has_hk_native_legs():
    """The HK-native legs the drivers need must be present in the assembled frame."""
    frame = md.assemble_frame()
    for col in ("SPY", "^VIX", "DX-Y.NYB", "hshare_hsi", "vhsi", "hibor_on"):
        assert col in frame.columns, f"{col} missing from assembled frame"
