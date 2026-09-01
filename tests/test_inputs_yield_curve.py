"""Regression guard for the canonical full Treasury curve feature projection."""
from __future__ import annotations

from engine.inputs import build_features


def test_existing_ccw_us20y_alias_reaches_the_canonical_feature_frame():
    frame = build_features()

    assert "us20y" in frame.columns
    assert frame["us20y"].notna().any()
