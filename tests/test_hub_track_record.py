"""Tests for engine/hub_track_record.py — the falsifiable signal track-record.

The price layer (_fwd_rel / _covers) is monkeypatched so maturation + IC are deterministic."""
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from engine import hub_track_record as H  # noqa: E402

_OLD = date(2026, 1, 2)           # snapshot date
_NOW = date(2026, 6, 21)          # well past every horizon


def _rows(n=14):
    # opp ascending 10..75; stage emerging for high-opp, exhausted for low-opp; all lean +1
    rows = []
    for i in range(n):
        opp = 10 + i * 5
        stage = "emerging" if opp >= 55 else "exhausted" if opp <= 25 else "early"
        rows.append({"t": f"T{i:02d}", "opp": opp, "edge": round(opp / 100, 2),
                     "stage": stage, "lean": 1})
    return rows


def test_snapshot_idempotent(tmp_path):
    rows = _rows()
    assert H.snapshot(rows, _OLD, root=tmp_path) == len(rows)
    assert H.snapshot(rows, _OLD, root=tmp_path) == 0          # same day → no double-append
    assert H.snapshot(rows, _OLD + timedelta(days=1), root=tmp_path) == len(rows)


def test_snapshot_persists_engine_version(tmp_path):
    import json
    rows = [{"t": "AAA", "opp": 60, "edge": 0.6, "stage": "emerging", "lean": 1,
             "engine_version": "hub-v3-trajectory"},
            {"t": "BBB", "opp": 20, "edge": 0.2, "stage": "exhausted", "lean": 1}]  # no version
    H.snapshot(rows, _OLD, root=tmp_path)
    written = [json.loads(l) for l in H._path(tmp_path).read_text().splitlines()]
    by = {r["t"]: r for r in written}
    assert by["AAA"]["engine_version"] == "hub-v3-trajectory"  # era-stamp carried through
    assert "engine_version" not in by["BBB"]                    # additive — old rows stay valid


def test_compute_accruing_when_empty(tmp_path):
    out = H.compute(_NOW, root=tmp_path)
    assert out["schema"] == H.SCHEMA and out["n_snapshots"] == 0
    assert out["any_matured"] is False and not any(out["proven"].values())


def test_ic_positive_and_stage_ordering(tmp_path, monkeypatch):
    rows = _rows(14)
    H.snapshot(rows, _OLD, root=tmp_path)
    # forward rel-return increases with opportunity → a POSITIVE IC; emerging beats exhausted
    fwd = {f"T{i:02d}": (i - 6) * 0.01 for i in range(14)}   # -0.06 .. +0.07
    monkeypatch.setattr(H, "_covers", lambda *a, **k: True)
    monkeypatch.setattr(H, "_fwd_rel", lambda t, root, start, h: fwd[t])
    out = H.compute(_NOW, root=tmp_path)
    h21 = out["horizons"]["21"]
    assert h21["n_matured"] == 14
    # single snapshot date → the rigorous daily-HAC IC isn't available yet (needs ≥6 dates),
    # but the provisional POOLED cross-sectional IC is, and is strongly positive
    assert h21["opportunity_ic_pooled"] is not None and h21["opportunity_ic_pooled"] > 0.5
    bs = h21["by_stage"]
    assert bs["emerging"]["mean_fwd_rel"] > bs["exhausted"]["mean_fwd_rel"]
    assert bs["emerging"]["hit_rate"] is not None       # bullish stage hit-rate computed


def test_daily_hac_path_and_proven_gate(tmp_path, monkeypatch):
    # 8 dates × 12 names, opportunity consistently ranks the forward return → the per-date
    # HAC path matures and the 'proven' gate can fire (n≥40, t_hac≥2, mean_ic>0).
    fwd = {f"N{i:02d}": (i - 5) * 0.01 for i in range(12)}     # monotone in name index
    for k in range(8):
        rows = [{"t": f"N{i:02d}", "opp": 10 + i * 6, "edge": 0.5,
                 "stage": "early", "lean": 1} for i in range(12)]
        H.snapshot(rows, _OLD + timedelta(days=k), root=tmp_path)
    monkeypatch.setattr(H, "_covers", lambda *a, **k: True)
    monkeypatch.setattr(H, "_fwd_rel", lambda t, root, start, h: fwd[t])
    out = H.compute(_NOW, root=tmp_path)
    h21 = out["horizons"]["21"]
    d = h21["opportunity_ic_daily"]
    assert d.get("mean_ic") is not None and d["mean_ic"] > 0.9   # near-perfect ranking each day
    assert h21["opportunity_ic"] == d["mean_ic"]                 # headline = rigorous daily IC
    assert out["proven"]["21"] is True                          # clears n≥40 + HAC-t bar
    assert out["lead_time_d"] in (5, 10, 21, 63)                # a significant horizon was picked


def test_signed_ic_respects_lean(tmp_path, monkeypatch):
    # a high-opp SHORT (lean -1) that falls is a CORRECT call → must not read as negative IC
    rows = [{"t": f"S{i:02d}", "opp": 70, "edge": 0.7, "stage": "distribution", "lean": -1}
            for i in range(12)]
    H.snapshot(rows, _OLD, root=tmp_path)
    monkeypatch.setattr(H, "_covers", lambda *a, **k: True)
    monkeypatch.setattr(H, "_fwd_rel", lambda t, root, start, h: -0.05)   # all fell (good shorts)
    out = H.compute(_NOW, root=tmp_path)
    bs = out["horizons"]["21"]["by_stage"]["distribution"]
    assert bs["hit_rate"] == 1.0                         # every short fell → 100% directional hit


def test_proven_requires_enough_matured(tmp_path, monkeypatch):
    # only a handful of obs → never "proven" even with a clean signal
    rows = _rows(12)
    H.snapshot(rows, _OLD, root=tmp_path)
    monkeypatch.setattr(H, "_covers", lambda *a, **k: True)
    monkeypatch.setattr(H, "_fwd_rel", lambda t, root, start, h: 0.02)
    out = H.compute(_NOW, root=tmp_path)
    assert not any(out["proven"].values())              # n_matured (12) < _MIN_PROVEN_N (40)
