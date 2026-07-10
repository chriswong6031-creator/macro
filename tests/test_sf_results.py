"""tests/test_sf_results.py — accrue_forward idempotency + load_results + promotion_docket."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine.signal_foundry.results import (
    accrue_forward,
    load_results,
    promotion_docket,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_sf_dirs(tmp_path: Path) -> None:
    (tmp_path / "data" / "signal_foundry" / "results").mkdir(parents=True)
    (tmp_path / "data" / "signal_foundry" / "forward").mkdir(parents=True)


def _write_result(tmp_path: Path, spec_id: str, verdict: str = "pass_candidate") -> None:
    result_dir = tmp_path / "data" / "signal_foundry" / "results"
    result = {
        "spec": {"id": spec_id},
        "stats": {},
        "verdict": verdict,
        "verdict_reasons": [],
        "battery_version": "sf-battery-1",
        "ran_at": "2026-07-10",
        "ledger_n_at_run": 1,
    }
    (result_dir / f"{spec_id}.json").write_text(json.dumps(result))


def _write_candidates_jsonl(tmp_path: Path, entries: list[dict]) -> None:
    cands_dir = tmp_path / "data" / "signal_foundry"
    cands_dir.mkdir(parents=True, exist_ok=True)
    with (cands_dir / "candidates.jsonl").open("w") as fh:
        for entry in entries:
            fh.write(json.dumps(entry) + "\n")


def _make_fake_parquet(tmp_path: Path, name: str, n: int = 500) -> str:
    """Write a fake parquet with a feature column and return relative path."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    p = data_dir / name
    idx = pd.bdate_range("2020-01-01", periods=n)
    pd.DataFrame({
        "feature": np.random.default_rng(0).standard_normal(n),
        "price": 100 + np.cumsum(np.random.default_rng(1).standard_normal(n)),
    }, index=idx).to_parquet(p)
    return str(p.relative_to(tmp_path))


# ---------------------------------------------------------------------------
# load_results
# ---------------------------------------------------------------------------

class TestLoadResults:
    def test_absent_dir_returns_empty(self, tmp_path):
        results = load_results(repo_root=tmp_path)
        assert results == []

    def test_loads_json_files(self, tmp_path):
        _make_sf_dirs(tmp_path)
        _write_result(tmp_path, "SF-0001", "pass_candidate")
        _write_result(tmp_path, "SF-0002", "null")
        results = load_results(repo_root=tmp_path)
        assert len(results) == 2
        ids = {r["spec"]["id"] for r in results}
        assert ids == {"SF-0001", "SF-0002"}

    def test_malformed_json_skipped(self, tmp_path):
        _make_sf_dirs(tmp_path)
        _write_result(tmp_path, "SF-0001", "pass_candidate")
        # Write a malformed JSON file
        bad = tmp_path / "data" / "signal_foundry" / "results" / "SF-XXXX.json"
        bad.write_text("NOT JSON {{{")
        results = load_results(repo_root=tmp_path)
        assert len(results) == 1  # only the valid one


# ---------------------------------------------------------------------------
# promotion_docket
# ---------------------------------------------------------------------------

class TestPromotionDocket:
    def test_pass_candidate_appears_in_docket(self, tmp_path):
        _make_sf_dirs(tmp_path)
        _write_result(tmp_path, "SF-0001", "pass_candidate")
        _write_result(tmp_path, "SF-0002", "null")
        docket = promotion_docket(repo_root=tmp_path)
        ids = {r["spec"]["id"] for r in docket}
        assert "SF-0001" in ids
        assert "SF-0002" not in ids

    def test_adjudicated_removed_from_docket(self, tmp_path):
        _make_sf_dirs(tmp_path)
        _write_result(tmp_path, "SF-0001", "pass_candidate")
        # Write promotions.jsonl saying SF-0001 was adjudicated
        prom_dir = tmp_path / "data" / "signal_foundry"
        prom_dir.mkdir(parents=True, exist_ok=True)
        with (prom_dir / "promotions.jsonl").open("w") as fh:
            fh.write(json.dumps({"spec_id": "SF-0001", "decision": "promote"}) + "\n")
        docket = promotion_docket(repo_root=tmp_path)
        ids = {r["spec"]["id"] for r in docket}
        assert "SF-0001" not in ids

    def test_empty_results_empty_docket(self, tmp_path):
        docket = promotion_docket(repo_root=tmp_path)
        assert docket == []


# ---------------------------------------------------------------------------
# accrue_forward idempotency
# ---------------------------------------------------------------------------

class TestAccrueForward:
    def test_absent_candidates_returns_empty(self, tmp_path):
        written = accrue_forward(repo_root=tmp_path, asof="2026-07-10")
        assert written == {}

    def test_no_registered_candidates_skipped(self, tmp_path):
        _make_sf_dirs(tmp_path)
        _write_candidates_jsonl(tmp_path, [
            {"id": "SF-0001", "status": "proposed", "registered_at": "2026-01-01"},
        ])
        written = accrue_forward(repo_root=tmp_path, asof="2026-07-10")
        assert "SF-0001" not in written

    def test_asof_not_after_registered_at_skipped(self, tmp_path):
        _make_sf_dirs(tmp_path)
        _write_candidates_jsonl(tmp_path, [
            {"id": "SF-0001", "status": "registered", "registered_at": "2026-07-10"},
        ])
        # asof == registered_at → must be AFTER, not equal
        written = accrue_forward(repo_root=tmp_path, asof="2026-07-10")
        assert "SF-0001" not in written

    def test_idempotent_double_call(self, tmp_path):
        """Calling accrue_forward twice with the same asof must not duplicate rows."""
        _make_sf_dirs(tmp_path)
        feat_path = _make_fake_parquet(tmp_path, "feat.parquet")
        _write_candidates_jsonl(tmp_path, [{
            "id": "SF-0001",
            "status": "registered",
            "registered_at": "2020-01-01",
            "data": [{"path": feat_path, "column": "feature", "pit": "clean"}],
            "feature": {"pipeline": [["zscore", {"window": 63}]]},
            "target": {"path": feat_path, "kind": "absolute_return", "horizon_d": 21,
                       "column": "price"},
        }])

        asof = "2021-06-01"
        accrue_forward(repo_root=tmp_path, asof=asof)
        accrue_forward(repo_root=tmp_path, asof=asof)  # second call

        fwd_file = tmp_path / "data" / "signal_foundry" / "forward" / "SF-0001.jsonl"
        if fwd_file.exists():
            rows = [json.loads(line) for line in fwd_file.read_text().splitlines() if line.strip()]
            dates_seen = [r["date"] for r in rows]
            # Must not have duplicate dates
            assert len(dates_seen) == len(set(dates_seen)), (
                f"Duplicate dates in forward file after double call: {dates_seen}"
            )
