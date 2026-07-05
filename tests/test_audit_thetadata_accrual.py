"""Tests for scripts/audit_thetadata_accrual.py — ThetaData EOD store health check.

Tests the audit() function directly (injectable data_root — no live filesystem outside tmp_path).
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from scripts.audit_thetadata_accrual import audit, DEFAULT_MAX_AGE_DAYS


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_store(base: Path, *, write_state: bool = True, write_manifest: bool = True,
                n_roots: int = 0, write_parquet: bool = False,
                parquet_age_days: float = 0.0) -> Path:
    """Create a thetadata_eod store directory under base with controlled fixtures."""
    store = base / "thetadata_eod"
    store.mkdir(parents=True)
    if write_state:
        (store / "_backfill_state.json").write_text(
            json.dumps({"version": 1, "completed": {
                "SPY": ["2025"] if n_roots > 0 else []
            }})
        )
    if write_manifest:
        per_root = {"SPY": {"completed_years": ["2025"], "n_years": 1}} if n_roots > 0 else {}
        (store / "_manifest.json").write_text(
            json.dumps({"store": "thetadata_eod", "n_roots": n_roots,
                        "per_root": per_root, "updated_at": None})
        )
    if write_parquet:
        p = store / "eod" / "SPY"
        p.mkdir(parents=True)
        parquet_path = p / "2025.parquet"
        pd.DataFrame({"x": [1]}).to_parquet(parquet_path)
        if parquet_age_days > 0:
            # Backdate mtime
            target_ts = time.time() - parquet_age_days * 86400
            os.utime(parquet_path, (target_ts, target_ts))
    return store


# ── DARK: store absent ─────────��─────────────────────────────────────────────

def test_dark_when_store_absent(tmp_path):
    """No store directory → DARK fail."""
    result = audit(data_root=tmp_path)
    assert not result["ok"]
    assert any("DARK" in f for f in result["fail_reasons"])


# ── BACKFILL IN PROGRESS grace ────────────────────────────────────────────────

def test_backfill_in_progress_no_parquets(tmp_path):
    """State file exists, no parquets → backfill_in_progress grace → ok=True, warning not error."""
    _make_store(tmp_path, write_state=True, write_manifest=True,
                n_roots=0, write_parquet=False)
    result = audit(data_root=tmp_path)
    # Must not fail — backfill is legitimately in progress
    assert result["ok"], f"Expected ok but got fail_reasons={result['fail_reasons']}"
    assert not result["fail_reasons"]
    assert result["detail"]["backfill_in_progress"] is True
    # Should emit a warning (not silence) describing the in-progress state
    assert any("IN PROGRESS" in w for w in result["warnings"])


def test_backfill_in_progress_n_roots_zero_even_with_parquets(tmp_path):
    """n_roots=0 in manifest but parquets exist → still in-progress (manifest not updated yet)."""
    _make_store(tmp_path, write_state=True, write_manifest=True,
                n_roots=0, write_parquet=True)
    result = audit(data_root=tmp_path)
    assert result["ok"]
    assert result["detail"]["backfill_in_progress"] is True


# ── STEADY STATE: ok ────────────���────────────────────────────────────────────

def test_steady_state_fresh_parquet(tmp_path):
    """n_roots>0 + parquet just written → ok."""
    _make_store(tmp_path, write_state=True, write_manifest=True,
                n_roots=1, write_parquet=True, parquet_age_days=0.5)
    result = audit(data_root=tmp_path, max_age_days=DEFAULT_MAX_AGE_DAYS)
    assert result["ok"], f"Expected ok but: {result['fail_reasons']}"
    assert not result["fail_reasons"]
    assert result["detail"]["backfill_in_progress"] is False


def test_steady_state_parquet_at_limit(tmp_path):
    """Parquet exactly at limit (age == max_age_days - epsilon) → ok."""
    _make_store(tmp_path, write_state=True, write_manifest=True,
                n_roots=1, write_parquet=True, parquet_age_days=DEFAULT_MAX_AGE_DAYS - 0.01)
    result = audit(data_root=tmp_path, max_age_days=DEFAULT_MAX_AGE_DAYS)
    assert result["ok"]


# ── STEADY STATE: STALE ──────────────────────────────────────────��────────────

def test_steady_state_stale_parquet(tmp_path):
    """Parquet older than max_age_days → STALE fail."""
    _make_store(tmp_path, write_state=True, write_manifest=True,
                n_roots=1, write_parquet=True, parquet_age_days=DEFAULT_MAX_AGE_DAYS + 1)
    result = audit(data_root=tmp_path, max_age_days=DEFAULT_MAX_AGE_DAYS)
    assert not result["ok"]
    assert any("STALE" in f for f in result["fail_reasons"])


def test_stale_parquet_custom_threshold(tmp_path):
    """Custom max_age_days=1: parquet 2 days old → STALE."""
    _make_store(tmp_path, write_state=True, write_manifest=True,
                n_roots=1, write_parquet=True, parquet_age_days=2)
    result = audit(data_root=tmp_path, max_age_days=1)
    assert not result["ok"]
    assert any("STALE" in f for f in result["fail_reasons"])


def test_stale_parquet_custom_threshold_fresh(tmp_path):
    """Custom max_age_days=5: parquet 2 days old → ok."""
    _make_store(tmp_path, write_state=True, write_manifest=True,
                n_roots=1, write_parquet=True, parquet_age_days=2)
    result = audit(data_root=tmp_path, max_age_days=5)
    assert result["ok"]


# ── edge cases ──────���─────────────────────────────────────────────────────────

def test_manifest_missing_n_roots_defaults_zero(tmp_path):
    """Missing manifest → n_roots defaults to 0 → backfill_in_progress if state exists + no parquets."""
    store = tmp_path / "thetadata_eod"
    store.mkdir()
    (store / "_backfill_state.json").write_text(
        json.dumps({"version": 1, "completed": {}})
    )
    # No manifest, no parquets
    result = audit(data_root=tmp_path)
    assert result["ok"]
    assert result["detail"]["backfill_in_progress"] is True


def test_no_state_file_and_empty_store(tmp_path):
    """Store dir exists, no state, no parquets → DARK fail (backfill never started)."""
    (tmp_path / "thetadata_eod").mkdir()
    result = audit(data_root=tmp_path)
    # No state file and no parquets — treat as dark
    assert not result["ok"]
    assert any("DARK" in f for f in result["fail_reasons"])


def test_detail_fields_always_present(tmp_path):
    """Detail dict always contains the key fields regardless of outcome."""
    _make_store(tmp_path, write_state=True, write_manifest=True, n_roots=0)
    result = audit(data_root=tmp_path)
    for key in ("now_utc", "store_dir", "store_exists", "state_file_exists",
                "n_parquets", "backfill_in_progress"):
        assert key in result["detail"], f"Missing detail key: {key}"
