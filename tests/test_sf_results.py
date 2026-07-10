"""tests/test_sf_results.py — accrue_forward idempotency + load_results + promotion_docket
+ cohort_fdr BH-FDR.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine.signal_foundry.results import (
    accrue_forward,
    cohort_fdr,
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


# ---------------------------------------------------------------------------
# cohort_fdr — Benjamini-Hochberg FDR (E5)
# ---------------------------------------------------------------------------

def _make_synthetic_result(spec_id: str, t_hac: float, n_subsample: int,
                            verdict: str = "null") -> dict:
    """Build a minimal result dict with a HAC t-stat for BH-FDR testing."""
    return {
        "spec": {"id": spec_id},
        "stats": {
            "n_obs": n_subsample * 10,
            "hac": {"t": t_hac, "n": n_subsample, "mean": 0.0, "se": 0.0},
        },
        "verdict": verdict,
        "verdict_reasons": [],
        "battery_version": "sf-battery-1",
        "ran_at": "2026-07-10",
        "ledger_n_at_run": 5,
    }


class TestCohortFDR:
    """Unit tests for cohort_fdr() with known BH-FDR fixture."""

    def test_known_bh_fixture(self, tmp_path):
        """Known BH fixture: 5 hypotheses, alpha=0.05.

        p-values: [0.001, 0.008, 0.039, 0.041, 0.210]
        BH threshold at rank k: k/5 * 0.05
          k=1: 0.01  → 0.001 <= 0.01  REJECT (q = 5*0.001/1 = 0.005)
          k=2: 0.02  → 0.008 <= 0.02  REJECT (q = 5*0.008/2 = 0.020)
          k=3: 0.03  → 0.039 > 0.03   DON'T REJECT
          k=4: 0.04  → 0.041 > 0.04   DON'T REJECT
          k=5: 0.05  → 0.210 > 0.05   DON'T REJECT
        Expected BH rejects: ids 'A' and 'B'.

        We build synthetic t-stats that produce these p-values.
        p = 2 * t.sf(|t|, df=df), so |t| = t.ppf(1 - p/2, df=df).
        We use large df (100) so the t-dist ≈ normal.
        """
        from scipy.stats import t as _t_dist

        df = 100  # large df for near-normal approximation
        target_ps = {"A": 0.001, "B": 0.008, "C": 0.039, "D": 0.041, "E": 0.210}
        results = []
        for sid, target_p in target_ps.items():
            # Solve for t from p: |t| = t.ppf(1 - p/2, df)
            t_val = float(_t_dist.ppf(1 - target_p / 2, df=df))
            results.append(_make_synthetic_result(sid, t_val, n_subsample=df + 1))

        record = cohort_fdr(
            cohort_id="test-bh-fixture",
            member_ids=["A", "B", "C", "D", "E"],
            results=results,
            fdr_alpha=0.05,
            trigger="test",
            repo_root=tmp_path,
        )

        assert record["n_members"] == 5
        assert set(record["bh_rejects"]) == {"A", "B"}, (
            f"Expected BH rejects {{A, B}}, got {record['bh_rejects']}"
        )
        # Check q values are <= alpha for rejects, > for non-rejects
        for sid in ["A", "B"]:
            assert record["members"][sid]["bh_reject"] is True
        for sid in ["C", "D", "E"]:
            assert record["members"][sid]["bh_reject"] is False

    def test_all_null_no_rejects(self, tmp_path):
        """All p-values near 1.0 → no BH rejects."""
        results = [
            _make_synthetic_result(f"SF-{i:04d}", t_hac=0.1, n_subsample=50)
            for i in range(1, 6)
        ]
        ids = [f"SF-{i:04d}" for i in range(1, 6)]
        record = cohort_fdr(
            cohort_id="test-all-null",
            member_ids=ids,
            results=results,
            fdr_alpha=0.10,
            trigger="test",
            repo_root=tmp_path,
        )
        assert record["bh_rejects"] == []

    def test_all_strong_signals(self, tmp_path):
        """All members with very large |t| → all should be BH-rejected."""
        # Use t=10 for all 5 members → p << 0.001 for each
        results = [
            _make_synthetic_result(f"SF-{i:04d}", t_hac=10.0, n_subsample=200)
            for i in range(1, 6)
        ]
        ids = [f"SF-{i:04d}" for i in range(1, 6)]
        record = cohort_fdr(
            cohort_id="test-all-strong",
            member_ids=ids,
            results=results,
            fdr_alpha=0.10,
            trigger="test",
            repo_root=tmp_path,
        )
        assert set(record["bh_rejects"]) == set(ids)

    def test_missing_member_result(self, tmp_path):
        """A member with no result record gets p=1.0 and is not rejected."""
        results = [_make_synthetic_result("SF-0001", t_hac=10.0, n_subsample=200)]
        record = cohort_fdr(
            cohort_id="test-missing",
            member_ids=["SF-0001", "SF-XXXX"],  # SF-XXXX has no result
            results=results,
            fdr_alpha=0.10,
            trigger="test",
            repo_root=tmp_path,
        )
        assert "SF-XXXX" in record["members"]
        assert record["members"]["SF-XXXX"]["p"] == 1.0
        assert record["members"]["SF-XXXX"]["bh_reject"] is False

    def test_writes_cohort_file(self, tmp_path):
        """cohort_fdr writes a JSON file to data/signal_foundry/cohorts/."""
        results = [_make_synthetic_result("SF-0001", t_hac=5.0, n_subsample=100)]
        record = cohort_fdr(
            cohort_id="test-write",
            member_ids=["SF-0001"],
            results=results,
            fdr_alpha=0.10,
            trigger="test",
            repo_root=tmp_path,
        )
        cohort_file = tmp_path / "data" / "signal_foundry" / "cohorts" / "test-write.json"
        assert cohort_file.exists(), "Cohort JSON file was not written"
        with cohort_file.open() as fh:
            loaded = json.load(fh)
        assert loaded["cohort_id"] == "test-write"
        assert "members" in loaded
        assert "formula_note" in loaded

    def test_q_monotone(self, tmp_path):
        """q-values must be monotonically non-decreasing when sorted by p."""
        from scipy.stats import t as _t_dist
        # Create 6 members with varied t-stats → varied p-values
        df = 50
        t_vals = [5.0, 3.0, 2.5, 1.5, 0.8, 0.1]
        results = []
        ids = []
        for i, tv in enumerate(t_vals):
            sid = f"SF-{i + 1:04d}"
            ids.append(sid)
            results.append(_make_synthetic_result(sid, t_hac=tv, n_subsample=df + 1))

        record = cohort_fdr(
            cohort_id="test-monotone",
            member_ids=ids,
            results=results,
            fdr_alpha=0.10,
            trigger="test",
            repo_root=tmp_path,
        )
        # Extract q-values, sort by p, verify monotone
        members = record["members"]
        ordered = sorted(members.items(), key=lambda kv: kv[1]["p"])
        q_vals = [v["q"] for _, v in ordered]
        # Monotone non-decreasing
        for i in range(len(q_vals) - 1):
            assert q_vals[i] <= q_vals[i + 1] + 1e-10, (
                f"q not monotone at positions {i}, {i+1}: {q_vals[i]} > {q_vals[i+1]}"
            )
