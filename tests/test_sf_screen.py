"""tests/test_sf_screen.py — screen_candidate tests.

Covers:
  - blocklist regex hit → forbidden with quoted source
  - dedup by construction hash
  - untracked data path rejected
"""
from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

import pytest

from engine.signal_foundry.screen import screen_candidate
from engine.signal_foundry.spec import construction_hash


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_git_repo(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=str(tmp_path), capture_output=True)


def _add_tracked_csv(tmp_path: Path, name: str = "test.csv") -> str:
    """Add a tracked CSV file in the data/ dir.  Returns relative path."""
    import pandas as pd
    import numpy as np
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    p = data_dir / name
    idx = pd.date_range("2000-01-01", periods=2000, freq="B")
    pd.DataFrame({"value": np.random.randn(2000)}, index=idx).to_csv(p)
    subprocess.run(["git", "add", str(p.relative_to(tmp_path))], cwd=str(tmp_path), capture_output=True)
    subprocess.run(["git", "commit", "-m", "add data"], cwd=str(tmp_path), capture_output=True)
    return str(p.relative_to(tmp_path))


def _add_blocklist(tmp_path: Path) -> None:
    """Write a minimal signal_foundry_blocklist.yml."""
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(exist_ok=True)
    bl = cfg_dir / "signal_foundry_blocklist.yml"
    bl.write_text(textwrap.dedent("""
        entries:
          - id: BL-TEST-001
            match:
              any_of:
                - "forbidden_magic_signal"
                - "llm.{0,30}originat"
            reason: "Test forbidden construction"
            source: "test-ruling-001"
    """))
    subprocess.run(["git", "add", str(bl.relative_to(tmp_path))], cwd=str(tmp_path), capture_output=True)
    subprocess.run(["git", "commit", "-m", "add blocklist"], cwd=str(tmp_path), capture_output=True)


def _make_candidate(tracked_path: str, name: str = "Some signal", **overrides) -> dict:
    c = {
        "id": "SF-9901",
        "name": name,
        "market": "US macro",
        "thesis": "A test signal",
        "mechanism": "Test mechanism",
        "data": [{"path": tracked_path, "column": "value", "pit": "clean"}],
        "feature": {"pipeline": [["zscore", {"window": 252}]]},
        "target": {
            "path": tracked_path,
            "kind": "absolute_return",
            "horizon_d": 21,
        },
        "universe": "single_series",
        "baseline": "buy_and_hold",
        "gates": {"min_t_hac": 2.0, "fdr_q": 0.10, "dsr": 0.90},
        "registered_at": "2026-07-10",
        "pit": "clean",
        "history_years": 8,
        "orthogonality_note": "Distinct from momentum: uses macro rate series",
        "evidence_note": "Fama-French literature",
    }
    c.update(overrides)
    return c


# ---------------------------------------------------------------------------
# Blocklist tests
# ---------------------------------------------------------------------------

class TestBlocklist:
    def test_blocklist_hit_returns_forbidden(self, tmp_path):
        _make_git_repo(tmp_path)
        _add_blocklist(tmp_path)
        tracked = _add_tracked_csv(tmp_path)
        # Candidate with name matching the blocklist pattern
        candidate = _make_candidate(
            tracked,
            name="forbidden_magic_signal predictor",
            thesis="A forbidden_magic_signal construction",
        )
        result = screen_candidate(candidate, repo_root=tmp_path)
        assert result["verdict"] == "forbidden", f"Expected forbidden, got {result}"
        assert result["admit"] is False
        assert any("BLOCKLIST" in r for r in result["reasons"])
        assert any("test-ruling-001" in r for r in result["reasons"])

    def test_llm_originated_signal_blocked(self, tmp_path):
        _make_git_repo(tmp_path)
        _add_blocklist(tmp_path)
        tracked = _add_tracked_csv(tmp_path)
        candidate = _make_candidate(
            tracked,
            name="LLM originating alpha signal",
            thesis="This is a LLM originated signal score",
        )
        result = screen_candidate(candidate, repo_root=tmp_path)
        assert result["verdict"] == "forbidden"

    def test_non_blocked_candidate_not_forbidden(self, tmp_path):
        _make_git_repo(tmp_path)
        _add_blocklist(tmp_path)
        tracked = _add_tracked_csv(tmp_path)
        candidate = _make_candidate(tracked, name="Legitimate HY spread signal")
        result = screen_candidate(candidate, repo_root=tmp_path)
        assert result["verdict"] != "forbidden"


# ---------------------------------------------------------------------------
# Untracked data path
# ---------------------------------------------------------------------------

class TestUntrackedPath:
    def test_untracked_path_rejected(self, tmp_path):
        _make_git_repo(tmp_path)
        # Don't add any tracked file
        candidate = _make_candidate("data/nonexistent_untracked.parquet")
        result = screen_candidate(candidate, repo_root=tmp_path)
        assert result["admit"] is False
        assert "data_path_tracked" in result["gates_failed"]

    def test_tracked_path_passes_gate_1(self, tmp_path):
        _make_git_repo(tmp_path)
        tracked = _add_tracked_csv(tmp_path)
        candidate = _make_candidate(tracked)
        result = screen_candidate(candidate, repo_root=tmp_path)
        assert "data_path_tracked" in result.get("gates_passed", [])


# ---------------------------------------------------------------------------
# Construction hash dedup
# ---------------------------------------------------------------------------

class TestDedup:
    def test_duplicate_hash_rejected(self, tmp_path):
        _make_git_repo(tmp_path)
        tracked = _add_tracked_csv(tmp_path)

        candidate = _make_candidate(tracked)
        # Write the hash to candidates.jsonl to simulate prior filing
        cands_dir = tmp_path / "data" / "signal_foundry"
        cands_dir.mkdir(parents=True, exist_ok=True)
        cands_file = cands_dir / "candidates.jsonl"
        c_hash = construction_hash(candidate)
        with cands_file.open("w") as fh:
            fh.write(json.dumps({"id": "SF-0001", "construction_hash": c_hash, "status": "registered"}) + "\n")

        result = screen_candidate(candidate, repo_root=tmp_path)
        assert result["admit"] is False
        assert "novelty" in result["gates_failed"]
        assert any("SF-R8" in r for r in result["reasons"])

    def test_novel_hash_passes_novelty_gate(self, tmp_path):
        _make_git_repo(tmp_path)
        tracked = _add_tracked_csv(tmp_path)

        candidate = _make_candidate(tracked)
        # candidates.jsonl has a DIFFERENT hash
        cands_dir = tmp_path / "data" / "signal_foundry"
        cands_dir.mkdir(parents=True, exist_ok=True)
        cands_file = cands_dir / "candidates.jsonl"
        with cands_file.open("w") as fh:
            fh.write(json.dumps({"id": "SF-0001", "construction_hash": "aaabbbccc", "status": "registered"}) + "\n")

        result = screen_candidate(candidate, repo_root=tmp_path)
        assert "novelty" in result.get("gates_passed", [])


# ---------------------------------------------------------------------------
# Gate coverage
# ---------------------------------------------------------------------------

class TestGateCoverage:
    def test_missing_pit_plan_rejected(self, tmp_path):
        _make_git_repo(tmp_path)
        tracked = _add_tracked_csv(tmp_path)
        candidate = _make_candidate(tracked)
        candidate["pit"] = "unknown"
        result = screen_candidate(candidate, repo_root=tmp_path)
        assert "pit_plan" in result["gates_failed"]

    def test_missing_baseline_rejected(self, tmp_path):
        _make_git_repo(tmp_path)
        tracked = _add_tracked_csv(tmp_path)
        candidate = _make_candidate(tracked)
        candidate["baseline"] = ""
        result = screen_candidate(candidate, repo_root=tmp_path)
        assert "baseline_named" in result["gates_failed"]

    def test_missing_orthogonality_note_rejected(self, tmp_path):
        _make_git_repo(tmp_path)
        tracked = _add_tracked_csv(tmp_path)
        candidate = _make_candidate(tracked)
        candidate["orthogonality_note"] = ""
        result = screen_candidate(candidate, repo_root=tmp_path)
        assert "orthogonality_noted" in result["gates_failed"]

    def test_missing_evidence_note_rejected(self, tmp_path):
        _make_git_repo(tmp_path)
        tracked = _add_tracked_csv(tmp_path)
        candidate = _make_candidate(tracked)
        candidate["evidence_note"] = ""
        result = screen_candidate(candidate, repo_root=tmp_path)
        assert "evidence_noted" in result["gates_failed"]

    def test_short_history_rejected(self, tmp_path):
        _make_git_repo(tmp_path)
        # CSV with only 2 years of data
        import pandas as pd
        import numpy as np
        data_dir = tmp_path / "data"
        data_dir.mkdir(exist_ok=True)
        p = data_dir / "short.csv"
        idx = pd.date_range("2022-01-01", periods=500, freq="B")
        pd.DataFrame({"value": np.random.randn(500)}, index=idx).to_csv(p)
        subprocess.run(["git", "add", str(p.relative_to(tmp_path))], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "commit", "-m", "short"], cwd=str(tmp_path), capture_output=True)

        candidate = _make_candidate(str(p.relative_to(tmp_path)))
        candidate["history_years"] = 2  # explicitly say 2 years
        result = screen_candidate(candidate, repo_root=tmp_path)
        assert "sample_5y" in result["gates_failed"]

    def test_all_gates_pass(self, tmp_path):
        _make_git_repo(tmp_path)
        tracked = _add_tracked_csv(tmp_path)
        candidate = _make_candidate(tracked)
        result = screen_candidate(candidate, repo_root=tmp_path)
        assert result["admit"] is True
        assert result["verdict"] == "admitted"
        assert result["gates_failed"] == []
