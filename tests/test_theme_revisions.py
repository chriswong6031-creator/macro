"""engine.theme_revisions — T4 revision-breadth roll-up. Verifies the per-theme breadth
math, the thin-coverage guard, level-state banding, and the PIT broadening derivative
(INSUFFICIENT_HISTORY until the archive spans the lookback). DISPLAY-ONLY contract.
"""
from __future__ import annotations

import pandas as pd

from engine import theme_revisions as tr


def _latest_frame():
    # memory_storage members: 3 strongly-positive, 1 thin (ignored), 1 absent
    return pd.DataFrame(
        {"net_up_30d": [10.0, 8.0, 6.0, 1.0],
         "breadth": [0.9, 0.8, 0.7, 0.5],
         "est_chg_30d": [5.0, 4.0, 3.0, 1.0],
         "est_chg_90d": [20.0, 18.0, 15.0, 2.0],
         "n_analysts": [12.0, 10.0, 8.0, 2.0],          # last one < MIN_ANALYSTS -> dropped
         "asof": pd.Timestamp("2026-06-16")},
        index=["MU", "WDC", "STX", "SNDK"],
    )


def _themes():
    return {"themes": {"memory_storage": {"name": "Memory", "tickers": ["MU", "WDC", "STX", "SNDK", "NTAP"]}}}


def _patch(monkeypatch, latest, hist=None, themes=None):
    monkeypatch.setattr(tr, "_latest", lambda: latest)
    monkeypatch.setattr(tr, "_history", lambda: hist)
    monkeypatch.setattr(tr.config, "load", lambda: themes or _themes())


def test_breadth_drops_thin_coverage(monkeypatch):
    _patch(monkeypatch, _latest_frame())
    out = tr.compute_theme_revisions(write_ledger=False)
    t = out["themes"]["memory_storage"]
    # mean breadth over the 3 covered names (0.9,0.8,0.7) = 0.8; the n=2 name is excluded
    assert t["breadth"] == 0.8
    assert t["n_covered"] == 3 and t["n_members"] == 5
    assert t["coverage"] == round(3 / 5, 2)
    assert t["level_state"] == "POSITIVE"
    assert t["est_drift_90d"] == 18.0          # median of 20,18,15


def test_flat_low_level(monkeypatch):
    df = _latest_frame()
    df["breadth"] = [0.05, -0.05, 0.02, 0.5]   # near zero -> FLAT_LOW
    _patch(monkeypatch, df)
    out = tr.compute_theme_revisions(write_ledger=False)
    assert out["themes"]["memory_storage"]["level_state"] == "FLAT_LOW"


def test_insufficient_history_when_no_archive(monkeypatch):
    _patch(monkeypatch, _latest_frame(), hist=None)
    out = tr.compute_theme_revisions(write_ledger=False)
    t = out["themes"]["memory_storage"]
    assert t["broadening_state"] == "INSUFFICIENT_HISTORY"
    assert t["breadth_accel"] is None


def test_broadening_rising_with_spanning_history(monkeypatch):
    latest = _latest_frame()
    # history: a snapshot ~40d earlier with LOWER breadth -> breadth rising -> RISING
    hist = pd.DataFrame({
        "ticker": ["MU", "WDC", "STX", "MU", "WDC", "STX"],
        "breadth": [0.2, 0.1, 0.1, 0.9, 0.8, 0.7],
        "n_analysts": [12.0, 10.0, 8.0, 12.0, 10.0, 8.0],
        "asof": [pd.Timestamp("2026-05-05")] * 3 + [pd.Timestamp("2026-06-16")] * 3,
    })
    _patch(monkeypatch, latest, hist=hist)
    out = tr.compute_theme_revisions(write_ledger=False)
    t = out["themes"]["memory_storage"]
    assert t["breadth_accel"] is not None and t["breadth_accel"] > 0
    assert t["broadening_state"] == "RISING"


def test_returns_none_without_data(monkeypatch):
    monkeypatch.setattr(tr, "_latest", lambda: None)
    assert tr.compute_theme_revisions(write_ledger=False) is None
