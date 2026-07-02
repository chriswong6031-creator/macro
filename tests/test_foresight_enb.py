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
