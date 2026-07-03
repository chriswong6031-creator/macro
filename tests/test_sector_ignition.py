"""Tests for the W5 sector-ignition layer + forward ledger + basket-level persistence.

Covers:
  engine/sector_ignition.py     — breadth thrust, RS curvature, MTF confirm, oil-flip
                                   (resource-only), missing-leg renormalization, state map.
  engine/ignition_audit.py      — snapshot idempotency + grading POWER (synthetic matured
                                   entry graded true/false-positive; the positive control).
  engine/basket_levels_persist.py — persist/read round-trip + idempotent merge.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import sector_ignition as si
from engine import ignition_audit as ia
from engine import basket_levels_persist as blp


# ──────────────────────────────────────────────────────────────────────────────
# helpers
# ──────────────────────────────────────────────────────────────────────────────

def _idx(n=120, start="2024-01-01"):
    return pd.date_range(start, periods=n, freq="B")


def _rising(n=120, slope=0.002, start="2024-01-01"):
    idx = _idx(n, start)
    return pd.Series((1 + np.full(n, slope)).cumprod(), index=idx)


# ──────────────────────────────────────────────────────────────────────────────
# breadth thrust
# ──────────────────────────────────────────────────────────────────────────────

def test_breadth_thrust_counts_fresh_crossers():
    idx = _idx(60)
    # member A: below its MA then jumps above in the last 3 sessions (a fresh thrust)
    a = pd.Series(np.r_[np.full(55, 100.0), [95, 96, 130, 131, 132]], index=idx)
    # member B: flat and far below its MA the whole time (no cross)
    b = pd.Series(np.linspace(100, 80, 60), index=idx)
    # member C: extended above MA for a long time (NOT a fresh cross → excluded from thrust)
    c = pd.Series(np.linspace(80, 160, 60), index=idx)
    frac, n_thr, n_elig = si._breadth_thrust(pd.DataFrame({"A": a, "B": b, "C": c}))
    assert n_elig == 3
    assert n_thr == 1                 # only A freshly crossed up
    assert abs(frac - 1 / 3) < 1e-9


def test_breadth_thrust_none_when_too_short():
    idx = _idx(10)
    df = pd.DataFrame({"A": pd.Series(range(10), index=idx, dtype=float)})
    frac, n_thr, n_elig = si._breadth_thrust(df)
    assert frac is None and n_thr == 0 and n_elig == 0


# ──────────────────────────────────────────────────────────────────────────────
# RS slope-change (curvature) — a TURN, not a level
# ──────────────────────────────────────────────────────────────────────────────

def test_rs_slope_change_positive_when_rs_accelerates_up():
    idx = _idx(120)
    bench = pd.Series(np.full(120, 1.0).cumprod(), index=idx)            # flat bench
    # basket flat for the first half then accelerating up (RS curvature > 0)
    lvl = pd.Series(np.r_[np.full(60, 1.0), (1 + np.linspace(0, 0.01, 60)).cumprod()], index=idx)
    norm, raw = si._rs_slope_change(lvl, bench)
    assert raw is not None and raw > 0
    assert 0.5 < norm <= 1.0


def test_rs_slope_change_negative_when_rs_rolls_over():
    idx = _idx(120)
    bench = pd.Series(np.full(120, 1.0), index=idx)
    # accelerating up then decelerating (curvature < 0 at the end)
    up = (1 + np.linspace(0.01, 0.0, 60)).cumprod()
    lvl = pd.Series(np.r_[np.full(60, 1.0), up], index=idx)
    norm, raw = si._rs_slope_change(lvl, bench)
    assert raw is not None and raw < 0
    assert 0.0 <= norm < 0.5


# ──────────────────────────────────────────────────────────────────────────────
# weekly MTF confirm
# ──────────────────────────────────────────────────────────────────────────────

def test_mtf_confirm_up_and_down():
    up = _rising(120, 0.002)
    leg, ok = si._mtf_confirm(up)
    assert leg == 1.0 and ok is True
    down = _rising(120, -0.002)
    leg, ok = si._mtf_confirm(down)
    assert leg == 0.0 and ok is False


# ──────────────────────────────────────────────────────────────────────────────
# per-basket score: missing-leg renormalization + oil-flip resource gating
# ──────────────────────────────────────────────────────────────────────────────

def test_missing_leg_renormalizes_not_penalizes():
    # only the MTF leg is computable (no members, no bench) → score == that leg, not diluted
    up = _rising(120, 0.002)
    r = si.compute_basket_ignition("b", member_closes=None, level=up, bench=None)
    assert r["components"]["breadth_thrust"] is None
    assert r["components"]["rs_slope_change"] is None
    assert r["components"]["mtf_confirm"] == 1.0
    assert r["ignition_score"] == 1.0        # renormalized over the single available leg


def test_oil_flip_only_boosts_resource_mapped():
    up, bench = _rising(120, 0.003), _rising(120, 0.0)
    base = si.compute_basket_ignition("e", None, up, bench,
                                      commodity_flip=True, resource_mapped=False)
    boosted = si.compute_basket_ignition("e", None, up, bench,
                                         commodity_flip=True, resource_mapped=True)
    assert not base["components"]["commodity_flip"]
    assert boosted["components"]["commodity_flip"]
    assert boosted["ignition_score"] > base["ignition_score"]


def test_score_none_when_no_legs():
    r = si.compute_basket_ignition("x", None, None, None)
    assert r["ignition_score"] is None and r["state"] == "idle"


def test_compute_ignition_ranks_and_hk_has_no_flow_leg():
    idx = _idx(120)
    dates = [d.strftime("%Y-%m-%d") for d in idx]
    bench = list((1 + np.full(120, 0.0)).cumprod())
    strong = list((1 + np.linspace(0, 0.01, 120)).cumprod())     # accelerating
    weak = list((1 + np.linspace(0.01, -0.005, 120)).cumprod())  # rolling over
    chart = {"dates": dates, "bench": bench, "baskets": {"s": strong, "w": weak}}
    baskets = [{"id": "s", "name": "Strong", "category": "X"},
               {"id": "w", "name": "Weak", "category": "X"}]
    out = si.compute_ignition(chart, baskets, lambda b: None, market="hk")
    assert out["has_southbound_leg"] is False
    assert [i["id"] for i in out["items"]][0] == "s"   # strong turn ranks first


# ──────────────────────────────────────────────────────────────────────────────
# forward ledger — idempotency + grading POWER (the positive control)
# ──────────────────────────────────────────────────────────────────────────────

def _snap(asof, items):
    return {"market": "hk", "as_of": asof, "items": items}


def test_ledger_log_idempotent(tmp_path):
    snap = _snap("2026-01-05", [{"id": "b1", "name": "B1", "ignition_score": 0.7, "state": "igniting"}])
    assert ia.log_snapshot(snap, "hk", root=tmp_path) == 1
    assert ia.log_snapshot(snap, "hk", root=tmp_path) == 0          # same (asof,basket) not re-added
    rows = ia._read(ia._path("hk", tmp_path))
    assert len(rows) == 1 and rows[0]["basket"] == "b1"


def test_grading_true_and_false_positive(tmp_path):
    # basket that beats the flat bench → an "igniting" call is a TRUE positive
    idx = pd.date_range("2026-01-01", periods=80, freq="B")
    bench = pd.Series(np.full(80, 100.0), index=idx)
    winner = pd.Series(np.linspace(100, 130, 80), index=idx)       # +30% vs flat bench
    loser = pd.Series(np.linspace(100, 80, 80), index=idx)         # -20% vs flat bench
    asof = "2026-01-03"
    ia.log_snapshot(_snap(asof, [
        {"id": "win", "name": "W", "ignition_score": 0.8, "state": "igniting"},
        {"id": "lose", "name": "L", "ignition_score": 0.7, "state": "igniting"},
    ]), "hk", root=tmp_path)
    lvl = {"win": winner, "lose": loser}
    n = ia.grade_log("hk", level_of=lambda b: lvl.get(b), bench_series=bench, root=tmp_path)
    assert n == 2
    rows = {r["basket"]: r for r in ia._read(ia._path("hk", tmp_path))}
    assert rows["win"]["graded"]["outcome"] == "true_positive"
    assert rows["win"]["graded"]["excess"]["h20"] > 0
    assert rows["lose"]["graded"]["outcome"] == "false_positive"
    assert rows["lose"]["graded"]["excess"]["h20"] < 0
    sc = ia.scorecard("hk", root=tmp_path)
    assert sc["n_graded"] == 2 and sc["n_alerts"] == 2
    assert sc["alert_precision_4w"] == 0.5


def test_grading_skips_immature(tmp_path):
    # as-of at the very end → no forward window → nothing graded (the guard against premature grades)
    idx = pd.date_range("2026-01-01", periods=30, freq="B")
    bench = pd.Series(np.full(30, 100.0), index=idx)
    lvl = pd.Series(np.linspace(100, 120, 30), index=idx)
    ia.log_snapshot(_snap("2026-02-10", [{"id": "b", "name": "B", "ignition_score": 0.8, "state": "igniting"}]),
                    "hk", root=tmp_path)
    n = ia.grade_log("hk", level_of=lambda b: lvl, bench_series=bench, root=tmp_path)
    assert n == 0


# ──────────────────────────────────────────────────────────────────────────────
# basket-level persistence
# ──────────────────────────────────────────────────────────────────────────────

def _payload():
    idx = _idx(40)
    dates = [d.strftime("%Y-%m-%d") for d in idx]
    return {
        "chart": {"dates": dates, "bench": list(np.linspace(1.0, 1.1, 40)),
                  "baskets": {"b1": list(np.linspace(1.0, 1.3, 40)),
                              "b2": list(np.linspace(1.0, 0.9, 40))}},
        "baskets": [{"id": "b1", "perf": {"20d": {"rel": 0.05}}},
                    {"id": "b2", "perf": {"20d": {"rel": -0.03}}}],
    }


def test_persist_and_read_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(blp.config, "data_dir", lambda: tmp_path)
    res = blp.persist(_payload(), "hk")
    assert res["wrote"] and res["n_baskets"] == 2 and res["n_dates"] == 40
    df = blp.read_levels("hk")
    assert df is not None and "b1__level" in df.columns and "__bench" in df.columns
    s = blp.level_series("hk", "b1")
    assert s is not None and len(s) == 40 and s.iloc[-1] > s.iloc[0]
    # 20d rel stamped on the as-of row only
    assert abs(df["b1__rel20"].dropna().iloc[-1] - 0.05) < 1e-9
    assert blp.bench_series("hk") is not None


def test_persist_idempotent_merge(tmp_path, monkeypatch):
    monkeypatch.setattr(blp.config, "data_dir", lambda: tmp_path)
    blp.persist(_payload(), "ca")
    r2 = blp.persist(_payload(), "ca")            # second write must not error or duplicate dates
    assert r2["wrote"]
    df = blp.read_levels("ca")
    assert not df.index.duplicated().any()
