"""Regime-dynamics trajectory math must survive null-holed timeline series.

2026-08-08: a collection gap committed nulls into site regime_timeline.json and
`_regime_dynamics` raised `TypeError: NoneType - float` at the window endpoint,
redding every consumer of the vector build (test_factor_exposure,
test_spvector_page) fleet-wide. The contract in its own docstring is
"Empty (null) when we have no history — honest, not guessed": nulls compact to
clean pairs, and the 30-reading coverage floor counts CLEAN pairs.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import build_vector  # noqa: E402


def _write_timeline(tmp_path, g, i, trans=None):
    (tmp_path / "regime_timeline.json").write_text(
        json.dumps({"g": g, "i": i, "trans": trans or []}), encoding="utf-8")


def test_null_endpoints_do_not_raise_and_still_read(tmp_path, monkeypatch):
    """Nulls at the tail and mid-window compact away; the read survives."""
    monkeypatch.setattr(build_vector.config, "site_dir", lambda: tmp_path)
    g = [0.5] * 40 + [None, 0.6, None]
    i = [0.2] * 40 + [0.1, None, None]
    _write_timeline(tmp_path, g, i, ["STABLE"])
    out = build_vector._regime_dynamics("US", {"quad": "Q1"})
    assert out["rdir"] in ("improving", "stable", "deteriorating")
    assert out["rphase"] is not None


def test_nulls_below_the_coverage_floor_return_empty(tmp_path, monkeypatch):
    """29 clean pairs is under the floor even when the raw series is long."""
    monkeypatch.setattr(build_vector.config, "site_dir", lambda: tmp_path)
    g = ([0.5, None] * 29)[:58]
    i = [0.2 if k % 2 == 0 else None for k in range(58)]
    _write_timeline(tmp_path, g, i)
    out = build_vector._regime_dynamics("US", {"quad": "Q1"})
    assert out == {"rdir": None, "rphase": None, "rtoward_en": None,
                   "rtoward_zh": None, "rflip": None}


def test_all_null_series_return_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(build_vector.config, "site_dir", lambda: tmp_path)
    _write_timeline(tmp_path, [None] * 60, [None] * 60)
    out = build_vector._regime_dynamics("US", {"quad": "Q2"})
    assert out["rdir"] is None
