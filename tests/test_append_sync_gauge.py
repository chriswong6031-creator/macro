"""Tests for scripts/append_sync_gauge.py.

Validates the circular-variance formula matches leadlag_phase0.py and
the upsert (idempotent per month) logic.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts.append_sync_gauge import (
    _compute_sync,
    _upsert_family,
    _phase,
    _month_end_date,
    SYNC_GAUGE_PATH,
    main,
)


# ── circular-variance formula ─────────────────────────────────────────────────

def _reference_sync(positions: list[float]) -> float:
    """Reference implementation lifted verbatim from scripts/leadlag_phase0.py
    compute_sync_gauge() so the test verifies formula fidelity."""
    vals = np.array(positions, dtype=float)
    ang = 2.0 * np.pi * (vals / 100.0)
    R = math.sqrt(np.mean(np.cos(ang)) ** 2 + np.mean(np.sin(ang)) ** 2)
    return R


def test_compute_sync_matches_leadlag_reference_all_same_phase():
    """All instruments at same position -> perfectly synchronised (sync = 1)."""
    vals = np.array([25.0, 25.0, 25.0, 25.0], dtype=float)
    result = _compute_sync(vals)
    ref = _reference_sync([25.0, 25.0, 25.0, 25.0])
    assert result == pytest.approx(ref, abs=1e-9)
    assert result == pytest.approx(1.0, abs=1e-6)


def test_compute_sync_matches_leadlag_reference_perfectly_dispersed():
    """Four instruments equally spaced on the circle -> minimally synchronised."""
    # 0, 25, 50, 75 on 0-100 scale -> 0, pi/2, pi, 3pi/2 radians
    vals = np.array([0.0, 25.0, 50.0, 75.0], dtype=float)
    result = _compute_sync(vals)
    ref = _reference_sync([0.0, 25.0, 50.0, 75.0])
    assert result == pytest.approx(ref, abs=1e-9)
    # mean resultant length ≈ 0 for equally dispersed
    assert result < 0.1


def test_compute_sync_matches_leadlag_reference_mixed():
    """Intermediate positions — formula must agree with reference to machine precision."""
    positions = [10.0, 30.0, 55.0, 72.0, 88.0, 5.0, 40.0]
    vals = np.array(positions, dtype=float)
    result = _compute_sync(vals)
    ref = _reference_sync(positions)
    assert result == pytest.approx(ref, abs=1e-9)


def test_compute_sync_bounds():
    """sync is always in [0, 1]."""
    rng = np.random.default_rng(42)
    for _ in range(20):
        vals = rng.uniform(0, 100, size=rng.integers(3, 20))
        s = _compute_sync(vals)
        assert 0.0 <= s <= 1.0 + 1e-9


# ── phase quadrant helper ─────────────────────────────────────────────────────

def test_phase_quadrants():
    assert _phase(0.0) == "trough"
    assert _phase(24.9) == "trough"
    assert _phase(25.0) == "advance"
    assert _phase(49.9) == "advance"
    assert _phase(50.0) == "peak"
    assert _phase(74.9) == "peak"
    assert _phase(75.0) == "decline"
    assert _phase(99.9) == "decline"


# ── _upsert_family ─────────────────────────────────────────────────────────────

def _entry(date: str, sync: float = 0.5) -> dict:
    return {"date": date, "sync": sync, "n": 5,
            "frac": {"trough": 0.2, "advance": 0.2, "peak": 0.3, "decline": 0.3}}


def test_upsert_appends_new_month():
    series = [_entry("2026-05-31", 0.4), _entry("2026-06-30", 0.45)]
    new_entry = _entry("2026-07-31", 0.6)
    result = _upsert_family(series, new_entry)
    assert len(result) == 3
    assert result[-1]["date"] == "2026-07-31"
    assert result[-1]["sync"] == pytest.approx(0.6)


def test_upsert_overwrites_same_month():
    """Same-month entry must be replaced (idempotent upsert)."""
    old = _entry("2026-07-31", 0.4)
    series = [_entry("2026-06-30", 0.45), old]
    new_entry = _entry("2026-07-31", 0.72)  # updated sync for July
    result = _upsert_family(series, new_entry)
    assert len(result) == 2
    july_rows = [r for r in result if r["date"].startswith("2026-07")]
    assert len(july_rows) == 1
    assert july_rows[0]["sync"] == pytest.approx(0.72)


def test_upsert_preserves_sort_order():
    series = [_entry("2026-05-31"), _entry("2026-07-31")]
    new_entry = _entry("2026-06-30", 0.55)
    result = _upsert_family(series, new_entry)
    dates = [r["date"] for r in result]
    assert dates == sorted(dates)


# ── _month_end_date ───────────────────────────────────────────────────────────

def test_month_end_date_regular():
    assert _month_end_date(2026, 6) == "2026-06-30"
    assert _month_end_date(2026, 1) == "2026-01-31"
    assert _month_end_date(2026, 2) == "2026-02-28"


def test_month_end_date_december():
    assert _month_end_date(2026, 12) == "2026-12-31"


# ── main() integration ────────────────────────────────────────────────────────

def _make_forward_log(tmp_path: Path, family_dir: str, ids: list[str],
                      date: str, pos_values: list[float]) -> None:
    p = tmp_path / family_dir / "forward_log.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    rows = [{"date": date, "id": iid, "pos": pv} for iid, pv in zip(ids, pos_values)]
    pd.DataFrame(rows).to_parquet(p, index=False)


def test_main_absent_safe(tmp_path, monkeypatch):
    """main() must exit 1 (no gauge file) without crashing."""
    monkeypatch.chdir(tmp_path)
    # Point ROOT at tmp_path so SYNC_GAUGE_PATH resolves there
    import scripts.append_sync_gauge as mod
    old_path = mod.SYNC_GAUGE_PATH
    mod.SYNC_GAUGE_PATH = tmp_path / "data" / "leadlag" / "sync_gauge.json"
    try:
        rc = main()
        assert rc == 1  # no gauge file -> error return, no crash
    finally:
        mod.SYNC_GAUGE_PATH = old_path


def test_main_upserts_current_month(tmp_path, monkeypatch):
    """main() must compute sync from forward_log and upsert it into gauge JSON."""
    import scripts.append_sync_gauge as mod

    # Build a minimal gauge JSON in tmp_path
    gauge_dir = tmp_path / "data" / "leadlag"
    gauge_dir.mkdir(parents=True, exist_ok=True)
    gauge_path = gauge_dir / "sync_gauge.json"
    gauge_path.write_text(json.dumps({
        "generated_at": "2026-07-03T15:50:32Z",
        "families": {"us_sector": [], "country": [], "cn_sector": []},
        "definition": "sync = 1 − circ_var(2π·pos/100); mean resultant length of phase angles",
    }))

    # Write synthetic forward_logs under tmp_path
    today = "2026-07-06"
    us_ids = ["xlb", "xlc", "xle", "xlf", "xli", "xlk", "xlp", "xlre", "xlu", "xlv", "xly"]
    _make_forward_log(tmp_path, "data/sector_cycles", us_ids[:5], today, [20, 30, 50, 70, 80])
    country_ids = ["ewa", "ewc", "ewd", "ewg", "ewi"]
    _make_forward_log(tmp_path, "data/country_cycles", country_ids, today, [10, 40, 60, 80, 90])
    cn_ids = ["801010", "801030", "801040", "801050", "801080"]
    _make_forward_log(tmp_path, "data/china_sector_cycles", cn_ids, today, [15, 35, 55, 75, 90])

    # Patch ROOT so FAMILIES paths and SYNC_GAUGE_PATH point into tmp_path
    old_root = mod.ROOT
    old_gauge_path = mod.SYNC_GAUGE_PATH
    mod.ROOT = tmp_path
    mod.SYNC_GAUGE_PATH = gauge_path
    # Patch FAMILIES to use the tmp_path-relative paths
    mod.FAMILIES["us_sector"]["forward_log"] = tmp_path / "data" / "sector_cycles" / "forward_log.parquet"
    mod.FAMILIES["us_sector"]["backfill"] = tmp_path / "data" / "sector_cycles" / "backfill.parquet"
    mod.FAMILIES["country"]["forward_log"] = tmp_path / "data" / "country_cycles" / "forward_log.parquet"
    mod.FAMILIES["country"]["backfill"] = tmp_path / "data" / "country_cycles" / "backfill.parquet"
    mod.FAMILIES["cn_sector"]["forward_log"] = tmp_path / "data" / "china_sector_cycles" / "forward_log.parquet"
    mod.FAMILIES["cn_sector"]["backfill"] = tmp_path / "data" / "china_sector_cycles" / "backfill.parquet"

    try:
        rc = main()
        assert rc == 0
        gauge = json.loads(gauge_path.read_text())
        for fam_key in ("us_sector", "country", "cn_sector"):
            series = gauge["families"][fam_key]
            assert len(series) == 1, f"{fam_key} should have one row"
            row = series[0]
            assert "sync" in row and 0.0 <= row["sync"] <= 1.0
            assert row["n"] == 5
            # verify formula: compute reference sync and compare
            if fam_key == "us_sector":
                ref = _reference_sync([20, 30, 50, 70, 80])
                assert row["sync"] == pytest.approx(ref, abs=1e-3)
        # idempotent: running again must not add a second entry per family
        rc2 = main()
        assert rc2 == 0
        gauge2 = json.loads(gauge_path.read_text())
        for fam_key in ("us_sector", "country", "cn_sector"):
            assert len(gauge2["families"][fam_key]) == 1
    finally:
        mod.ROOT = old_root
        mod.SYNC_GAUGE_PATH = old_gauge_path
