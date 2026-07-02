"""Unit tests for scripts/audit_fred_groups.py — FRED group coverage counting logic.

Verifies that the audit correctly counts present/fresh parquets, flags dark groups,
and passes/fails the gate — all against a synthetic temp directory (no network).
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from scripts.audit_fred_groups import audit_groups, MIN_PRESENT_PCT, STALE_DAYS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_parquet(path: Path) -> None:
    """Write a minimal parquet stub so the file exists with a current mtime."""
    import pandas as pd
    df = pd.DataFrame({"val": [1.0]}, index=pd.to_datetime(["2026-01-01"]))
    df.to_parquet(path)


def _minimal_cfg(groups: dict) -> dict:
    """Build a minimal config dict with just the fred.series block."""
    return {"fred": {"series": groups}}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_all_present_no_dark(tmp_path):
    """All configured series are fresh — gate passes, any_dark is False."""
    fred_dir = tmp_path / "fred"
    fred_dir.mkdir()
    _make_parquet(fred_dir / "AAA.parquet")
    _make_parquet(fred_dir / "BBB.parquet")

    cfg = _minimal_cfg({"bottleneck": {"AAA": "col_a", "BBB": "col_b"}})
    doc = audit_groups(cfg=cfg, data_dir=tmp_path, asof=date.today(), out_dir=tmp_path / "q_out")

    assert doc["any_dark"] is False
    assert len(doc["groups"]) == 1
    g = doc["groups"][0]
    assert g["group"] == "bottleneck"
    assert g["n_present"] == 2
    assert g["n_total"] == 2
    assert g["dark"] is False
    assert g["missing"] == []


def test_below_50pct_marks_dark(tmp_path):
    """Only 1 of 3 series present — below 50% threshold — group is DARK."""
    fred_dir = tmp_path / "fred"
    fred_dir.mkdir()
    _make_parquet(fred_dir / "AAA.parquet")
    # BBB and CCC are absent

    cfg = _minimal_cfg({"power": {"AAA": "col_a", "BBB": "col_b", "CCC": "col_c"}})
    doc = audit_groups(cfg=cfg, data_dir=tmp_path, asof=date.today(), out_dir=tmp_path / "q_out")

    assert doc["any_dark"] is True
    g = doc["groups"][0]
    assert g["dark"] is True
    assert g["n_present"] == 1
    assert g["n_total"] == 3
    assert set(g["missing"]) == {"BBB", "CCC"}


def test_exactly_50pct_not_dark(tmp_path):
    """Exactly 50% present — equal to min_present_pct — should NOT be dark (strict less-than)."""
    fred_dir = tmp_path / "fred"
    fred_dir.mkdir()
    _make_parquet(fred_dir / "AAA.parquet")
    # BBB absent → 1/2 = 50%

    cfg = _minimal_cfg({"grp": {"AAA": "col_a", "BBB": "col_b"}})
    doc = audit_groups(cfg=cfg, data_dir=tmp_path, asof=date.today(), min_present_pct=50.0, out_dir=tmp_path / "q_out")

    g = doc["groups"][0]
    assert g["pct_present"] == 50.0
    # 50.0 < 50.0 is False → not dark
    assert g["dark"] is False
    assert doc["any_dark"] is False


def test_stale_parquet_counts_as_absent(tmp_path):
    """A parquet older than stale_days counts as missing even if it exists."""
    fred_dir = tmp_path / "fred"
    fred_dir.mkdir()
    stale_file = fred_dir / "OLD.parquet"
    _make_parquet(stale_file)
    # Back-date the mtime beyond the stale window
    old_ts = (date.today() - timedelta(days=STALE_DAYS + 10)).timetuple()
    import time
    import os
    old_epoch = time.mktime(old_ts)
    os.utime(stale_file, (old_epoch, old_epoch))

    cfg = _minimal_cfg({"grp": {"OLD": "old_col", "NEW": "new_col"}})
    # NEW parquet is absent too — so 0/2 = 0%, dark
    doc = audit_groups(cfg=cfg, data_dir=tmp_path, asof=date.today(), out_dir=tmp_path / "q_out")

    g = doc["groups"][0]
    assert "OLD" in g["missing"]   # stale → treated as missing
    assert g["n_present"] == 0
    assert g["dark"] is True


def test_multi_group_one_dark(tmp_path):
    """Two groups — only the second one is dark; any_dark is True but first is OK."""
    fred_dir = tmp_path / "fred"
    fred_dir.mkdir()
    _make_parquet(fred_dir / "G1A.parquet")
    _make_parquet(fred_dir / "G1B.parquet")
    # G2 series absent entirely

    cfg = _minimal_cfg({
        "group_ok": {"G1A": "a", "G1B": "b"},
        "group_dark": {"G2X": "x", "G2Y": "y", "G2Z": "z"},
    })
    doc = audit_groups(cfg=cfg, data_dir=tmp_path, asof=date.today(), out_dir=tmp_path / "q_out")

    names = {g["group"]: g for g in doc["groups"]}
    assert names["group_ok"]["dark"] is False
    assert names["group_dark"]["dark"] is True
    assert doc["any_dark"] is True


def test_audit_writes_json(tmp_path):
    """The audit writes data/quality/fred_groups_audit.json and it is valid JSON."""
    fred_dir = tmp_path / "fred"
    fred_dir.mkdir()
    _make_parquet(fred_dir / "X.parquet")

    cfg = _minimal_cfg({"grp": {"X": "col_x"}})
    out_dir = tmp_path / "quality"
    audit_groups(cfg=cfg, data_dir=tmp_path, asof=date.today(), out_dir=out_dir)

    out_file = out_dir / "fred_groups_audit.json"
    assert out_file.exists()
    doc = json.loads(out_file.read_text())
    assert doc["audit"] == "fred_groups"
    assert "groups" in doc
    assert "any_dark" in doc


def test_empty_group_skipped(tmp_path):
    """A group with no series (empty dict) is skipped and doesn't appear in output."""
    fred_dir = tmp_path / "fred"
    fred_dir.mkdir()

    cfg = _minimal_cfg({"empty_grp": {}, "real_grp": {"A": "col_a"}})
    _make_parquet(fred_dir / "A.parquet")
    doc = audit_groups(cfg=cfg, data_dir=tmp_path, asof=date.today(), out_dir=tmp_path / "q_out")

    group_names = [g["group"] for g in doc["groups"]]
    assert "empty_grp" not in group_names
    assert "real_grp" in group_names
