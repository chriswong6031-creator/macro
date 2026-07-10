"""tests/test_sf_spec.py — validate_spec accept/reject + hash stability."""
from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

import pytest

from engine.signal_foundry.spec import (
    validate_spec,
    construction_hash,
    load_spec,
    stamp_gates_hash,
    _compute_gates_hash,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_good_spec(tmp_path: Path, tracked_file: str) -> dict:
    """Build a minimal valid spec pointing to a tracked file."""
    return {
        "id": "SF-0001",
        "name": "Test signal",
        "market": "US macro",
        "thesis": "A test signal for unit tests.",
        "data": [{"path": tracked_file, "column": "value", "pit": "proxy"}],
        "feature": {"pipeline": [["zscore", {"window": 252}], ["lag", {"n": 1}]]},
        "target": {
            "path": tracked_file,
            "kind": "excess_return",
            "horizon_d": 21,
            "column": "value",
        },
        "universe": "single_series",
        "baseline": "buy_and_hold",
        "gates": {"min_t_hac": 2.0, "fdr_q": 0.10, "dsr": 0.90},
        "registered_at": "2026-07-10",
    }


def _git_init_with_file(tmp_path: Path) -> Path:
    """Create a minimal git repo with one tracked CSV file."""
    import os
    subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), capture_output=True)
    # Create a tracked CSV file
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    csv_file = data_dir / "test_series.csv"
    csv_file.write_text("date,value\n2010-01-01,1.0\n2020-01-01,2.0\n")
    subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), capture_output=True)
    return csv_file


# ---------------------------------------------------------------------------
# Acceptance tests
# ---------------------------------------------------------------------------

class TestValidateSpecAccept:
    def test_valid_spec_passes(self, tmp_path):
        tracked = _git_init_with_file(tmp_path)
        spec = _make_good_spec(tmp_path, str(tracked.relative_to(tmp_path)))
        ok, errors = validate_spec(spec, repo_root=tmp_path)
        assert ok, f"Expected valid spec to pass, got errors: {errors}"
        assert errors == []

    def test_all_valid_horizons(self, tmp_path):
        tracked = _git_init_with_file(tmp_path)
        for h in [5, 10, 21, 63, 126]:
            spec = _make_good_spec(tmp_path, str(tracked.relative_to(tmp_path)))
            spec["target"]["horizon_d"] = h
            ok, errors = validate_spec(spec, repo_root=tmp_path)
            assert ok, f"horizon_d={h} should be valid, got: {errors}"

    def test_all_valid_target_kinds(self, tmp_path):
        tracked = _git_init_with_file(tmp_path)
        for kind in ["excess_return", "absolute_return", "drawdown_onset", "forward_vol"]:
            spec = _make_good_spec(tmp_path, str(tracked.relative_to(tmp_path)))
            spec["target"]["kind"] = kind
            ok, errors = validate_spec(spec, repo_root=tmp_path)
            assert ok, f"kind={kind} should be valid, got: {errors}"


# ---------------------------------------------------------------------------
# Rejection tests
# ---------------------------------------------------------------------------

class TestValidateSpecReject:
    def test_bad_id_format(self, tmp_path):
        tracked = _git_init_with_file(tmp_path)
        spec = _make_good_spec(tmp_path, str(tracked.relative_to(tmp_path)))
        spec["id"] = "SL-0001"  # wrong prefix
        ok, errors = validate_spec(spec, repo_root=tmp_path)
        assert not ok
        assert any("SF-" in e for e in errors)

    def test_unknown_transform(self, tmp_path):
        tracked = _git_init_with_file(tmp_path)
        spec = _make_good_spec(tmp_path, str(tracked.relative_to(tmp_path)))
        spec["feature"]["pipeline"] = [["magic_sauce", {"x": 1}]]
        ok, errors = validate_spec(spec, repo_root=tmp_path)
        assert not ok
        assert any("magic_sauce" in e for e in errors)

    def test_untracked_data_path(self, tmp_path):
        _git_init_with_file(tmp_path)
        # Use a path that doesn't exist in the git index
        spec = _make_good_spec(tmp_path, "data/untracked_file.csv")
        ok, errors = validate_spec(spec, repo_root=tmp_path)
        assert not ok
        assert any("git-tracked" in e or "not a git-tracked" in e for e in errors)

    def test_invalid_target_kind(self, tmp_path):
        tracked = _git_init_with_file(tmp_path)
        spec = _make_good_spec(tmp_path, str(tracked.relative_to(tmp_path)))
        spec["target"]["kind"] = "raw_price"
        ok, errors = validate_spec(spec, repo_root=tmp_path)
        assert not ok
        assert any("kind" in e for e in errors)

    def test_invalid_horizon(self, tmp_path):
        tracked = _git_init_with_file(tmp_path)
        spec = _make_good_spec(tmp_path, str(tracked.relative_to(tmp_path)))
        spec["target"]["horizon_d"] = 30  # not in {5,10,21,63,126}
        ok, errors = validate_spec(spec, repo_root=tmp_path)
        assert not ok
        assert any("horizon_d" in e for e in errors)

    def test_missing_gates_key(self, tmp_path):
        tracked = _git_init_with_file(tmp_path)
        spec = _make_good_spec(tmp_path, str(tracked.relative_to(tmp_path)))
        del spec["gates"]["dsr"]
        ok, errors = validate_spec(spec, repo_root=tmp_path)
        assert not ok
        assert any("gates" in e for e in errors)

    def test_missing_registered_at(self, tmp_path):
        tracked = _git_init_with_file(tmp_path)
        spec = _make_good_spec(tmp_path, str(tracked.relative_to(tmp_path)))
        del spec["registered_at"]
        ok, errors = validate_spec(spec, repo_root=tmp_path)
        assert not ok

    def test_lag_negative_rejected(self, tmp_path):
        tracked = _git_init_with_file(tmp_path)
        spec = _make_good_spec(tmp_path, str(tracked.relative_to(tmp_path)))
        spec["feature"]["pipeline"] = [["lag", {"n": -1}]]
        ok, errors = validate_spec(spec, repo_root=tmp_path)
        assert not ok
        assert any("lag" in e for e in errors)

    def test_window_non_positive_rejected(self, tmp_path):
        tracked = _git_init_with_file(tmp_path)
        spec = _make_good_spec(tmp_path, str(tracked.relative_to(tmp_path)))
        spec["feature"]["pipeline"] = [["zscore", {"window": 0}]]
        ok, errors = validate_spec(spec, repo_root=tmp_path)
        assert not ok


# ---------------------------------------------------------------------------
# Gate-freeze (SF-R4)
# ---------------------------------------------------------------------------

class TestGateFreeze:
    def test_gate_freeze_pass_on_unchanged_gates(self, tmp_path):
        tracked = _git_init_with_file(tmp_path)
        spec = _make_good_spec(tmp_path, str(tracked.relative_to(tmp_path)))
        spec_with_hash = stamp_gates_hash(spec)
        ok, errors = validate_spec(spec_with_hash, repo_root=tmp_path)
        assert ok, errors

    def test_gate_freeze_fail_on_changed_gates(self, tmp_path):
        tracked = _git_init_with_file(tmp_path)
        spec = _make_good_spec(tmp_path, str(tracked.relative_to(tmp_path)))
        spec_with_hash = stamp_gates_hash(spec)
        # Now modify gates
        spec_with_hash["gates"]["min_t_hac"] = 3.0
        ok, errors = validate_spec(spec_with_hash, repo_root=tmp_path)
        assert not ok
        assert any("gates" in e.lower() for e in errors)


# ---------------------------------------------------------------------------
# construction_hash stability
# ---------------------------------------------------------------------------

class TestConstructionHash:
    def test_hash_stable_on_name_change(self):
        spec1 = {
            "market": "US macro",
            "feature": {"pipeline": [["zscore", {"window": 252}]]},
            "target": {"path": "data/foo.parquet", "kind": "excess_return", "horizon_d": 21},
            "universe": "single_series",
        }
        spec2 = dict(spec1)
        spec2["name"] = "A different name"
        assert construction_hash(spec1) == construction_hash(spec2)

    def test_hash_changes_on_pipeline_change(self):
        spec1 = {
            "market": "US macro",
            "feature": {"pipeline": [["zscore", {"window": 252}]]},
            "target": {"path": "data/foo.parquet", "kind": "excess_return", "horizon_d": 21},
            "universe": "single_series",
        }
        spec2 = dict(spec1)
        spec2["feature"] = {"pipeline": [["diff", {"n": 1}]]}
        assert construction_hash(spec1) != construction_hash(spec2)

    def test_hash_changes_on_horizon_change(self):
        spec1 = {
            "market": "US macro",
            "feature": {"pipeline": [["zscore", {"window": 252}]]},
            "target": {"path": "data/foo.parquet", "kind": "excess_return", "horizon_d": 21},
            "universe": "single_series",
        }
        spec2 = dict(spec1)
        spec2["target"] = dict(spec1["target"])
        spec2["target"]["horizon_d"] = 63
        assert construction_hash(spec1) != construction_hash(spec2)

    def test_hash_changes_on_market_change(self):
        spec1 = {
            "market": "US macro",
            "feature": {"pipeline": [["zscore", {"window": 252}]]},
            "target": {"path": "data/foo.parquet", "kind": "excess_return", "horizon_d": 21},
            "universe": "single_series",
        }
        spec2 = dict(spec1)
        spec2["market"] = "China A"
        assert construction_hash(spec1) != construction_hash(spec2)

    def test_hash_is_deterministic(self):
        spec = {
            "market": "US macro",
            "feature": {"pipeline": [["zscore", {"window": 252}], ["lag", {"n": 1}]]},
            "target": {"path": "data/spy.parquet", "kind": "absolute_return", "horizon_d": 63},
            "universe": "single_series",
        }
        h1 = construction_hash(spec)
        h2 = construction_hash(spec)
        assert h1 == h2
        assert len(h1) == 20
