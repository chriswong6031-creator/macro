"""engine.guidance_gap — T3 guidance-language tilt. Verifies the directional band logic,
the per-theme rollup (most-recent direction per filer, recency window), and that it
degrades honestly on empty input. Pure / fixture-driven — no network, no filesystem writes.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from engine import guidance_gap as gg


def _df(rows):
    return pd.DataFrame(rows)


def test_band_raise_led():
    assert gg._band(2, 0) == "RAISING"
    assert gg._band(3, 0) == "BROAD-RAISE"
    assert gg._band(3, 1) == "BROAD-RAISE"      # raise-led with >=3 distinct raisers
    assert gg._band(2, 1) == "RAISING"


def test_band_cut_and_neutral():
    assert gg._band(0, 2) == "CUTTING"
    assert gg._band(1, 0) == "NEUTRAL"          # single filer < MIN_FILERS -> no tilt
    assert gg._band(1, 1) == "NEUTRAL"          # balanced
    assert gg._band(2, 2) == "NEUTRAL"          # balanced, no lead


def test_theme_guidance_latest_direction_wins():
    today = date.today()
    rows = _df([
        {"ticker": "MU", "direction": "cut", "phrase": "lowering guidance",
         "file_date": str(today - timedelta(days=40))},
        {"ticker": "MU", "direction": "raise", "phrase": "raising guidance",
         "file_date": str(today - timedelta(days=5))},    # MU's MOST RECENT read = raise
        {"ticker": "WDC", "direction": "raise", "phrase": "raising our outlook",
         "file_date": str(today - timedelta(days=10))},
    ])
    r = gg._theme_guidance("Memory", rows)
    assert r["n_raisers"] == 2 and r["n_cutters"] == 0    # MU counted once, as a raiser
    assert "MU" in r["raisers"] and "WDC" in r["raisers"]
    assert r["guidance_band"] == "RAISING"
    assert r["recent"][0]["ticker"] == "MU"               # most recent first


def test_theme_guidance_empty():
    assert gg._theme_guidance("X", _df([])) is None


def test_compute_rolls_up_to_config_theme_and_drops_stale():
    today = date.today()
    # memory_storage members in config: MU, WDC, SNDK, STX, NTAP
    hits = _df([
        {"ticker": "MU",  "direction": "raise", "phrase": "raising guidance",
         "file_date": str(today - timedelta(days=8))},
        {"ticker": "WDC", "direction": "raise", "phrase": "raising our outlook",
         "file_date": str(today - timedelta(days=12))},
        {"ticker": "STX", "direction": "cut",   "phrase": "lowering guidance",
         "file_date": str(today - timedelta(days=20))},
        {"ticker": "NTAP", "direction": "raise", "phrase": "raising guidance",
         "file_date": str(today - timedelta(days=200))},   # outside the 90d window -> dropped
    ])
    out = gg.compute_guidance_gap(write_ledger=False, hits=hits)
    assert out is not None
    ms = out["themes"].get("memory_storage")
    assert ms is not None
    assert ms["n_raisers"] == 2 and ms["n_cutters"] == 1   # NTAP stale, excluded
    assert ms["guidance_band"] == "RAISING"


def test_compute_none_on_empty():
    assert gg.compute_guidance_gap(write_ledger=False, hits=_df([])) is None
