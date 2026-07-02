"""engine.foresight_enb — ENB + hierarchical clustering.

Tests:
  (a) ENB math on synthetic 3-theme correlation fixtures:
      - perfect correlation (all ρ=1) → ENB ≈ 1
      - independent (identity matrix) → ENB ≈ 3
  (b) Cluster assignment (greedy fallback path for portability)
  (c) load_cluster_membership reads from log
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd
import pytest

from engine import foresight_enb as enb


# ---------------------------------------------------------------------------
# ENB eigenvalue math — pure, no I/O
# ---------------------------------------------------------------------------

def _corr_from_matrix(mat: list[list[float]]) -> pd.DataFrame:
    arr = np.array(mat, dtype=float)
    return pd.DataFrame(arr)


def test_enb_perfect_correlation():
    """Three perfectly-correlated themes → ENB ≈ 1.0 (one true bet)."""
    # When all pairwise ρ=1, the correlation matrix has one nonzero eigenvalue → ENB=1
    mat = [[1.0, 1.0, 1.0],
           [1.0, 1.0, 1.0],
           [1.0, 1.0, 1.0]]
    corr = _corr_from_matrix(mat)
    result = enb._enb(corr)
    assert result is not None
    assert result == pytest.approx(1.0, abs=0.05)


def test_enb_independent():
    """Three independent themes (identity matrix) → ENB ≈ 3.0 (three true bets)."""
    mat = [[1.0, 0.0, 0.0],
           [0.0, 1.0, 0.0],
           [0.0, 0.0, 1.0]]
    corr = _corr_from_matrix(mat)
    result = enb._enb(corr)
    assert result is not None
    assert result == pytest.approx(3.0, abs=0.05)


def test_enb_partial_correlation():
    """Partial correlation → ENB between 1 and 3."""
    mat = [[1.0, 0.8, 0.1],
           [0.8, 1.0, 0.1],
           [0.1, 0.1, 1.0]]
    corr = _corr_from_matrix(mat)
    result = enb._enb(corr)
    assert result is not None
    assert 1.0 < result < 3.0


def test_enb_empty():
    """Empty DataFrame → None."""
    assert enb._enb(pd.DataFrame()) is None


def test_enb_single_theme():
    """1×1 matrix → None (need ≥2 themes)."""
    assert enb._enb(pd.DataFrame([[1.0]])) is None


# ---------------------------------------------------------------------------
# Clustering — greedy fallback path
# ---------------------------------------------------------------------------

def test_cluster_high_correlation_merged():
    """Two highly correlated themes → same cluster; independent theme → own cluster."""
    themes = ["theme_a", "theme_b", "theme_c"]
    mat = [[1.0, 0.9, 0.1],
           [0.9, 1.0, 0.1],
           [0.1, 0.1, 1.0]]
    corr = _corr_from_matrix(mat)
    corr.index = themes
    corr.columns = themes
    membership = enb._cluster_themes(corr, themes)
    # theme_a and theme_b should share a cluster; theme_c should differ
    assert membership["theme_a"] == membership["theme_b"]
    assert membership["theme_c"] != membership["theme_a"]


def test_cluster_all_independent():
    """All independent → each theme in its own cluster."""
    themes = ["a", "b", "c"]
    mat = [[1.0, 0.0, 0.0],
           [0.0, 1.0, 0.0],
           [0.0, 0.0, 1.0]]
    corr = _corr_from_matrix(mat)
    corr.index = themes
    corr.columns = themes
    membership = enb._cluster_themes(corr, themes)
    ids = set(membership.values())
    assert len(ids) == 3   # all separate


# ---------------------------------------------------------------------------
# load_cluster_membership — reads latest row from jsonl log
# ---------------------------------------------------------------------------

def test_load_cluster_membership_reads_latest(tmp_path):
    """load_cluster_membership returns clusters from the latest asof row."""
    log_dir = tmp_path / "foresight"
    log_dir.mkdir()
    p = log_dir / "enb_log.jsonl"
    rows = [
        {"asof": "2026-06-30", "clusters": {"theme_a": "c0", "theme_b": "c0", "theme_c": "c1"}},
        {"asof": "2026-07-01", "clusters": {"theme_a": "c0", "theme_b": "c1", "theme_c": "c1"}},
    ]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")

    with mock.patch("engine.foresight_enb.config") as mock_cfg:
        mock_cfg.data_dir.return_value = tmp_path
        result = enb.load_cluster_membership()

    # Should return the 2026-07-01 row (latest)
    assert result == {"theme_a": "c0", "theme_b": "c1", "theme_c": "c1"}


def test_load_cluster_membership_empty(tmp_path):
    """Returns {} when no log file exists."""
    with mock.patch("engine.foresight_enb.config") as mock_cfg:
        mock_cfg.data_dir.return_value = tmp_path
        result = enb.load_cluster_membership()
    assert result == {}


# ---------------------------------------------------------------------------
# F3: pairwise NaN guard — disjoint-history themes must not disable ENB
# ---------------------------------------------------------------------------

def test_enb_disjoint_range_themes_still_computes(tmp_path, caplog):
    """Two themes with disjoint date ranges produce a NaN corr cell.

    F3: _build_corr_matrix must fill the NaN with 0.0, warn, and allow
    _enb() to still compute a finite result.  The bug: NaN → eigvalsh NaN →
    ENB None → all themes silently lose ENB and cluster-dilution display."""
    import logging
    import numpy as np

    # Build two disjoint date ranges
    dates_a = pd.date_range("2025-01-02", periods=60, freq="B")
    dates_b = pd.date_range("2025-04-01", periods=60, freq="B")  # no overlap with A
    # Two normal themes that overlap with each other (and with both A and B partially)
    dates_c = pd.date_range("2025-01-02", periods=100, freq="B")
    dates_d = pd.date_range("2025-01-02", periods=100, freq="B")

    rng = np.random.default_rng(42)
    returns = {
        "theme_disjoint_a": pd.Series(rng.normal(0, 0.01, len(dates_a)), index=dates_a),
        "theme_disjoint_b": pd.Series(rng.normal(0, 0.01, len(dates_b)), index=dates_b),
        "theme_normal_c":   pd.Series(rng.normal(0, 0.01, len(dates_c)), index=dates_c),
        "theme_normal_d":   pd.Series(rng.normal(0, 0.01, len(dates_d)), index=dates_d),
    }

    with caplog.at_level(logging.WARNING, logger="engine.foresight_enb"):
        corr, themes_included, n_low_overlap = enb._build_corr_matrix(returns)

    # At least 2 themes included (normal themes have plenty of overlap)
    assert len(themes_included) >= 2
    # No NaN in the filled corr matrix
    assert not corr.isnull().any().any(), "NaN survived the fill — pairwise guard failed"
    # ENB must compute (not None)
    enb_val = enb._enb(corr)
    assert enb_val is not None, "ENB is None — NaN propagated through eigvalsh"
    assert enb_val > 0
    # At least one low-overlap pair was detected and warned
    if n_low_overlap > 0:
        assert any("insufficient pairwise overlap" in r.message for r in caplog.records)
