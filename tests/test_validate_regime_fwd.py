"""Tests for the forward-regime grading gate (scripts/validate_regime_fwd.py, #16).

Guards the pure grading math (no data-store I/O): Wilson intervals, realized-outcome
extraction from a synthetic history, hit computation, and the accrual-aware verdict.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts import validate_regime_fwd as V


def test_wilson_bounds_and_degenerate():
    lo, p, hi = V.wilson(0, 0)
    assert (lo, p, hi) == (0.0, 0.0, 1.0)          # n=0 -> widest
    lo, p, hi = V.wilson(8, 10)
    assert 0.0 < lo < 0.8 < hi <= 1.0              # 80% with a real interval
    lo, p, hi = V.wilson(10, 10)
    assert lo < 1.0 and hi == 1.0                  # all hits -> lo below 1


def test_realized_accel_sign_from_history():
    idx = pd.bdate_range("2020-01-01", periods=200)
    # growth score ramps up over the window -> realized accel sign at +63bd is +1
    gs = pd.Series(np.linspace(-1, 1, 200), index=idx)
    hist = pd.DataFrame({"growth_score": gs, "inflation_score": -gs,
                         "quad": ["Q1"] * 200}, index=idx)
    asof = idx[10]
    assert V._realized_accel_sign(hist, "growth", asof, 63) == 1
    assert V._realized_accel_sign(hist, "inflation", asof, 63) == -1
    # too close to the end -> None (horizon not elapsed)
    assert V._realized_accel_sign(hist, "growth", idx[190], 63) is None


def test_realized_quad_lookup():
    idx = pd.bdate_range("2020-01-01", periods=100)
    quads = ["Q1"] * 50 + ["Q4"] * 50
    hist = pd.DataFrame({"growth_score": 0.0, "inflation_score": 0.0, "quad": quads}, index=idx)
    assert V._realized_quad(hist, idx[10], 21) == "Q1"
    assert V._realized_quad(hist, idx[40], 21) == "Q4"   # 40+21=61 -> Q4 block
    assert V._realized_quad(hist, idx[95], 21) is None


def test_verdict_accruing_then_go():
    # below MIN_GRADE_N -> accruing with distance
    v = V._verdict(5, wilson_lo=0.9)
    assert v["status"] == "accruing" and v["distance_to_decision"] == V.MIN_GRADE_N - 5
    # enough n and lower bound clears baseline -> go
    v = V._verdict(V.MIN_GRADE_N, wilson_lo=0.62, baseline=0.5)
    assert v["status"] == "go"
    # enough n but lower bound below baseline -> no-go
    v = V._verdict(V.MIN_GRADE_N, wilson_lo=0.40, baseline=0.5)
    assert v["status"] == "no-go"


def test_grade_base_effect_on_synthetic_ledger(tmp_path, monkeypatch):
    """A synthetic matured ledger: predictions that mostly match realized -> a hit rate
    reflecting the matches, flat (0) predictions excluded from the directional grade."""
    import json
    from lib import config
    d = tmp_path / "regime"
    d.mkdir(parents=True)
    rows = []
    # 8 growth calls: 6 correct (+1 pred, +1 real), 1 wrong, 1 flat (excluded)
    for i in range(6):
        rows.append({"asof": f"2026-01-0{i+1}", "be_growth_2d_q1": 1, "be_infl_2d_q1": -1,
                     "realized_growth_2d_at_63d": 1, "realized_infl_2d_at_63d": -1})
    rows.append({"asof": "2026-01-07", "be_growth_2d_q1": 1, "be_infl_2d_q1": 1,
                 "realized_growth_2d_at_63d": -1, "realized_infl_2d_at_63d": 1})
    rows.append({"asof": "2026-01-08", "be_growth_2d_q1": 0, "be_infl_2d_q1": -1,
                 "realized_growth_2d_at_63d": 1, "realized_infl_2d_at_63d": -1})
    (d / "base_effect_fwd.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n")
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)

    g = V.grade_base_effect()
    # growth: 7 directional (flat excluded), 6 hits
    assert g["growth"]["n_directional"] == 7
    assert g["growth"]["hits"] == 6
    assert g["growth"]["n_matured"] == 8
    # inflation: all 8 directional, all correct
    assert g["inflation"]["n_directional"] == 8
    assert g["inflation"]["hits"] == 8


def test_grade_hmm_on_synthetic_ledger(tmp_path, monkeypatch):
    import json
    from lib import config
    d = tmp_path / "regime"
    d.mkdir(parents=True)
    rows = [{"asof": "2026-01-01", "pred_modal_quad": "Q1", "realized_quad_at_21d": "Q1"},
            {"asof": "2026-01-02", "pred_modal_quad": "Q1", "realized_quad_at_21d": "Q2"},
            {"asof": "2026-01-03", "pred_modal_quad": "Q4", "realized_quad_at_21d": "Q4"},
            {"asof": "2026-01-04", "pred_modal_quad": "Q3", "realized_quad_at_21d": None}]
    (d / "regime_fwd_hmm.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    g = V.grade_hmm()
    assert g["n_matured"] == 3      # the None row not matured
    assert g["hits"] == 2          # Q1==Q1, Q4==Q4
