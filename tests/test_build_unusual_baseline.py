"""tests/test_build_unusual_baseline.py — unit tests for scripts/build_unusual_baseline.py.

Tests:
  1. _recent_sessions: returns sorted dates descending, bounded to WINDOW_SESSIONS
  2. compute_root_baseline: null when <MIN_SESSIONS
  3. compute_root_baseline: computes mean/p95 on synthetic data
  4. build: dry_run produces correct schema
  5. Schema keys present in output
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.build_unusual_baseline import (
    MIN_SESSIONS,
    WINDOW_SESSIONS,
    _recent_sessions,
    _load_volume_for_sessions,
    compute_root_baseline,
    build,
)


# ── fixture helpers ────────────────────────────────────────────────────────────

def _write_eod_parquet(eod_dir: Path, root: str, year: int, rows: list[dict]) -> None:
    """Write a minimal EOD parquet for (root, year)."""
    d = eod_dir / root.upper()
    d.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_parquet(d / f"{year}.parquet", index=False)


def _make_store(tmp_path: Path, root: str, n_sessions: int,
                vol_per_session: float = 1_000_000.0) -> Path:
    """Create a minimal EOD store with n_sessions of synthetic data.

    Each session has vol_per_session volume (uniform) across a single contract row.
    Dates are YYYY-07-01 through YYYY-07-{n_sessions} for simplicity.
    """
    store = tmp_path / "theta_store"
    eod_dir = store / "eod"
    rows = []
    for i in range(1, n_sessions + 1):
        day = f"2026-07-{i:02d}"
        rows.append({
            "date":       day,
            "root":       root.upper(),
            "expiration": "2026-09-19",
            "strike":     500.0,
            "right":      "C",
            "open":       10.0,
            "high":       11.0,
            "low":        9.5,
            "close":      10.5,
            "volume":     int(vol_per_session),
            "count":      500,
        })
    _write_eod_parquet(eod_dir, root, 2026, rows)
    return store


# ── test 1: _recent_sessions ──────────────────────────────────────────────────

def test_recent_sessions_bounded(tmp_path):
    """_recent_sessions returns at most WINDOW_SESSIONS entries, sorted desc."""
    root = "SPY"
    n = WINDOW_SESSIONS + 5   # more than window
    store = _make_store(tmp_path, root, n)
    sessions = _recent_sessions(store, root, WINDOW_SESSIONS)

    assert len(sessions) == WINDOW_SESSIONS, (
        f"Expected {WINDOW_SESSIONS} sessions, got {len(sessions)}"
    )
    # Sorted descending
    assert sessions == sorted(sessions, reverse=True), "Sessions not sorted descending"


def test_recent_sessions_missing_root(tmp_path):
    """_recent_sessions returns empty list for unknown root."""
    store = tmp_path / "theta_store"
    store.mkdir(parents=True, exist_ok=True)
    result = _recent_sessions(store, "ZZZZ", WINDOW_SESSIONS)
    assert result == []


# ── test 2: compute_root_baseline — null when < MIN_SESSIONS ─────────────────

def test_compute_null_below_min_sessions(tmp_path):
    """compute_root_baseline returns null entry when fewer than MIN_SESSIONS sessions."""
    root = "SPY"
    n = MIN_SESSIONS - 1   # one short of minimum
    store = _make_store(tmp_path, root, n)
    result = compute_root_baseline(store, root)

    assert result["mean_vol_30d"] is None, "Expected null mean_vol_30d below MIN_SESSIONS"
    assert result["p95_vol_30d"] is None, "Expected null p95_vol_30d below MIN_SESSIONS"
    assert result["null_reason"] is not None, "Expected null_reason to be set"
    assert result["sessions_used"] == n, f"Expected sessions_used={n}, got {result['sessions_used']}"


# ── test 3: compute_root_baseline — correct stats ─────────────────────────────

def test_compute_root_baseline_stats(tmp_path):
    """compute_root_baseline computes correct mean and p95 from synthetic uniform volumes."""
    root = "NVDA"
    n = MIN_SESSIONS + 5
    vol = 500_000.0
    store = _make_store(tmp_path, root, n, vol_per_session=vol)
    result = compute_root_baseline(store, root)

    assert result["mean_vol_30d"] is not None, "Expected non-null mean"
    assert result["p95_vol_30d"] is not None, "Expected non-null p95"
    assert result["null_reason"] is None, f"Unexpected null_reason: {result['null_reason']}"

    # Uniform volume: mean == p95 == vol (all sessions identical)
    assert abs(result["mean_vol_30d"] - vol) < 1.0, (
        f"mean_vol_30d={result['mean_vol_30d']} expected ~{vol}"
    )
    assert abs(result["p95_vol_30d"] - vol) < 1.0, (
        f"p95_vol_30d={result['p95_vol_30d']} expected ~{vol}"
    )
    assert result["sessions_used"] >= MIN_SESSIONS, "Expected sessions_used >= MIN_SESSIONS"


# ── test 4: build dry_run schema ──────────────────────────────────────────────

def test_build_dry_run_schema(tmp_path):
    """build() in dry_run mode returns a dict with the correct schema key."""
    root = "TSLA"
    n = MIN_SESSIONS + 2
    store = _make_store(tmp_path, root, n, vol_per_session=250_000.0)

    payload = build(roots=[root], store=store, publish=False, dry_run=True)

    assert payload["schema"] == "flow.unusual_baseline/v1", (
        f"Wrong schema: {payload['schema']}"
    )
    assert "asof" in payload, "Missing asof"
    assert "roots" in payload, "Missing roots key"
    assert root in payload["roots"], f"Root {root} missing from output"

    entry = payload["roots"][root]
    assert "mean_vol_30d" in entry, "Missing mean_vol_30d in root entry"
    assert "p95_vol_30d" in entry, "Missing p95_vol_30d in root entry"
    assert "sessions_used" in entry, "Missing sessions_used in root entry"


# ── test 5: build writes local file (non-dry-run) ────────────────────────────

def test_build_writes_local_file(tmp_path, monkeypatch):
    """build() writes unusual_baseline.json to the local data/live_flow_out/ path."""
    root = "SPY"
    n = MIN_SESSIONS + 2
    store = _make_store(tmp_path, root, n, vol_per_session=1_000_000.0)

    # Redirect data output to tmp_path
    out_dir = tmp_path / "data" / "live_flow_out"
    out_dir.mkdir(parents=True, exist_ok=True)

    import scripts.build_unusual_baseline as mod
    original_out_path = mod._out_path

    def _mock_out_path():
        return out_dir / "unusual_baseline.json"

    monkeypatch.setattr(mod, "_out_path", _mock_out_path)

    payload = build(roots=[root], store=store, publish=False, dry_run=False)

    out_file = out_dir / "unusual_baseline.json"
    assert out_file.exists(), f"Expected output file at {out_file}"

    written = json.loads(out_file.read_text())
    assert written["schema"] == "flow.unusual_baseline/v1"
    assert root in written["roots"]


# ── test 6: regression — post-load n_ok gate (MUST-FIX bypass) ───────────────

def test_compute_null_when_post_load_volume_sparse(tmp_path):
    """Regression: compute_root_baseline must emit null when date-scan finds >=
    MIN_SESSIONS session dates but only a few rows survive the volume load.

    Simulates the bypass: write a parquet that has MIN_SESSIONS *date entries*
    in one year (visible to _recent_sessions) but only MIN_SESSIONS-1 of those
    rows have a non-zero, non-null volume value.  Pre-fix: the MIN_SESSIONS gate
    at line 176 passed (len(sessions) is OK) and stats were computed over a
    sub-threshold sample.  Post-fix: the post-load n_ok gate must block this.
    """
    from scripts.build_unusual_baseline import MIN_SESSIONS

    root = "SPY"
    store = tmp_path / "theta_store"
    eod_dir = store / "eod"
    d = eod_dir / root
    d.mkdir(parents=True, exist_ok=True)

    # Enough date entries to pass the date-scan gate.
    n_date_entries = MIN_SESSIONS + 2

    rows = []
    for i in range(1, n_date_entries + 1):
        day = f"2026-07-{i:02d}"
        # Only the first (MIN_SESSIONS - 1) rows carry real volume; the rest have
        # zero volume so they are filtered out by the volume-load step.
        vol = 500_000 if i < MIN_SESSIONS else 0
        rows.append({
            "date":       day,
            "root":       root,
            "expiration": "2026-09-19",
            "strike":     500.0,
            "right":      "C",
            "volume":     vol,
        })

    pd.DataFrame(rows).to_parquet(d / "2026.parquet", index=False)

    result = compute_root_baseline(store, root)

    assert result["mean_vol_30d"] is None, (
        "REGRESSION: post-load n_ok gate not applied — mean_vol_30d should be null "
        f"when only {MIN_SESSIONS - 1} sessions have volume (< MIN_SESSIONS={MIN_SESSIONS})"
    )
    assert result["p95_vol_30d"] is None, "p95_vol_30d should also be null"
    assert result["null_reason"] is not None, "null_reason must be set"
    # sessions_used should reflect the actual post-load count, not date-scan count
    assert result["sessions_used"] < MIN_SESSIONS, (
        f"sessions_used {result['sessions_used']} should be < MIN_SESSIONS {MIN_SESSIONS}"
    )
