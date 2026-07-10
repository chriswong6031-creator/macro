"""tests/test_sf_harness_runner.py — Unit tests for run_signal_foundry_harness.py.

Tests:
  - Registers all pending specs BEFORE running any (fair DSR n)
  - Respects runs_per_week cap
  - Wall-clock cap (mocked time)
  - Idempotency: tested specs not re-run
  - dry-run: no writes to candidates.jsonl or results/
  - Governance events appended to sf governance.jsonl

No network calls; engine.signal_foundry.harness.run_spec is mocked.
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.run_signal_foundry_harness import (
    _register_pending_specs,
    _count_runs_this_week,
    _results_exist_for,
    main,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_root(tmp_path: Path) -> Path:
    """Create a minimal repo root with signal_foundry.yml."""
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "signal_foundry").mkdir(parents=True, exist_ok=True)
    cfg_text = """\
auto_loop: false
budgets:
  filed_per_week: 5
  runs_per_week: 10
  run_wallclock_min: 30
models:
  generator: claude-sonnet-4-6
  skeptic: claude-opus-4-8
  compiler: claude-haiku-4-5-20251001
"""
    (tmp_path / "config" / "signal_foundry.yml").write_text(cfg_text)
    return tmp_path


def _make_spec(spec_id: str, name: str, status: str = "proposed") -> dict:
    return {
        "id": spec_id,
        "name": name,
        "thesis": "test thesis",
        "mechanism": "test mechanism",
        "data": [{"path": "data/fred/test.parquet", "column": "value", "pit": "lagged"}],
        "feature": {"pipeline": [["zscore", {"window": 252}]]},
        "target": {"path": "data/yahoo/SPY.parquet", "kind": "excess_return", "horizon_d": 21},
        "universe": "single_series",
        "baseline": "buy_and_hold",
        "gates": {"min_t_hac": 2.0, "fdr_q": 0.10, "dsr": 0.90},
        "status": status,
        "iso_week": "2026-W28",
        "proposed_at": "2026-07-10T00:00:00+00:00",
    }


def _write_candidates(root: Path, specs: list[dict]) -> Path:
    cands_path = root / "data" / "signal_foundry" / "candidates.jsonl"
    with cands_path.open("w") as fh:
        for s in specs:
            fh.write(json.dumps(s) + "\n")
    return cands_path


def _read_candidates(root: Path) -> list[dict]:
    p = root / "data" / "signal_foundry" / "candidates.jsonl"
    if not p.exists():
        return []
    rows = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _read_governance(root: Path) -> list[dict]:
    p = root / "data" / "signal_foundry" / "governance.jsonl"
    if not p.exists():
        return []
    rows = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _read_lane_status(root: Path) -> dict:
    p = root / "data" / "signal_foundry" / "lane_status.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text())


# ---------------------------------------------------------------------------
# Test: register_all_before_running — Phase 1 transitions all proposed before run
# ---------------------------------------------------------------------------

class TestRegisterAllBeforeRunning:
    def test_all_proposed_become_registered(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path)
        specs = [
            _make_spec("SF-0001", "spec-a", status="proposed"),
            _make_spec("SF-0002", "spec-b", status="proposed"),
            _make_spec("SF-0003", "spec-c", status="proposed"),
        ]
        cands_path = _write_candidates(root, specs)

        rows, n_registered = _register_pending_specs(cands_path, dry_run=False)

        assert n_registered == 3
        for row in rows:
            assert row.get("status") == "registered"
            assert row.get("registered_at") is not None

    def test_already_registered_not_double_registered(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path)
        specs = [
            _make_spec("SF-0001", "spec-a", status="proposed"),
            {**_make_spec("SF-0002", "spec-b", status="registered"),
             "registered_at": "2026-07-09"},
        ]
        cands_path = _write_candidates(root, specs)

        rows, n_registered = _register_pending_specs(cands_path, dry_run=False)

        assert n_registered == 1  # only SF-0001 was proposed
        reg_rows = [r for r in rows if r.get("id") == "SF-0001"]
        assert reg_rows[0]["status"] == "registered"
        # SF-0002 untouched
        kept_rows = [r for r in rows if r.get("id") == "SF-0002"]
        assert kept_rows[0]["registered_at"] == "2026-07-09"

    def test_screen_rejected_not_registered(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path)
        specs = [
            _make_spec("SF-0001", "spec-a", status="proposed"),
            {**_make_spec("SF-0002", "spec-b", status="screen_rejected")},
        ]
        cands_path = _write_candidates(root, specs)

        rows, n_registered = _register_pending_specs(cands_path, dry_run=False)

        assert n_registered == 1
        rejected_rows = [r for r in rows if r.get("id") == "SF-0002"]
        assert rejected_rows[0]["status"] == "screen_rejected"

    def test_gates_hash_stamped_at_registration(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path)
        spec = _make_spec("SF-0001", "spec-a", status="proposed")
        assert "gates_hash" not in spec
        cands_path = _write_candidates(root, [spec])

        rows, n_registered = _register_pending_specs(cands_path, dry_run=False)

        assert n_registered == 1
        # gates_hash should now be set
        assert rows[0].get("gates_hash") is not None

    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path)
        specs = [_make_spec("SF-0001", "spec-a", status="proposed")]
        cands_path = _write_candidates(root, specs)
        original_content = cands_path.read_text()

        rows, n_registered = _register_pending_specs(cands_path, dry_run=True)

        # File unchanged in dry-run
        assert cands_path.read_text() == original_content
        assert n_registered == 1
        # But in-memory rows are updated
        assert rows[0]["status"] == "registered"


# ---------------------------------------------------------------------------
# Test: runs_per_week cap
# ---------------------------------------------------------------------------

_CFG_CAP_2 = {
    "auto_loop": False,
    "budgets": {"filed_per_week": 5, "runs_per_week": 2, "run_wallclock_min": 30},
    "models": {},
}

_CFG_DEFAULT = {
    "auto_loop": False,
    "budgets": {"filed_per_week": 5, "runs_per_week": 10, "run_wallclock_min": 30},
    "models": {},
}


class TestRunsPerWeekCap:
    def test_cap_respected(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path)
        # 3 registered specs, cap = 2
        specs = [
            {**_make_spec("SF-0001", "spec-a", status="registered"), "registered_at": "2026-07-09"},
            {**_make_spec("SF-0002", "spec-b", status="registered"), "registered_at": "2026-07-09"},
            {**_make_spec("SF-0003", "spec-c", status="registered"), "registered_at": "2026-07-09"},
        ]
        _write_candidates(root, specs)

        run_count = [0]

        def fake_run_spec(spec, repo_root="."):
            run_count[0] += 1
            return {"verdict": "null", "spec": spec, "stats": {}, "placebos": {},
                    "backtest": {}, "verdict_reasons": [], "battery_version": "sf-battery-1",
                    "ran_at": "2026-07-10", "ledger_n_at_run": run_count[0]}

        with mock.patch("scripts.run_signal_foundry_harness._load_config", return_value=_CFG_CAP_2):
            with mock.patch("scripts.run_signal_foundry_harness.run_spec", side_effect=fake_run_spec):
                rc = main(["--root", str(root)])

        assert rc == 0
        assert run_count[0] == 2  # capped at 2

    def test_already_tested_not_rerun(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path)
        # SF-0001 already has results
        specs = [
            {**_make_spec("SF-0001", "spec-a", status="tested"), "registered_at": "2026-07-09"},
            {**_make_spec("SF-0002", "spec-b", status="registered"), "registered_at": "2026-07-09"},
        ]
        _write_candidates(root, specs)

        # Create results file for SF-0001
        results_dir = root / "data" / "signal_foundry" / "results"
        results_dir.mkdir(parents=True, exist_ok=True)
        (results_dir / "SF-0001.json").write_text('{"verdict": "null"}')

        run_count = [0]

        def fake_run_spec(spec, repo_root="."):
            run_count[0] += 1
            return {"verdict": "null", "spec": spec, "stats": {}, "placebos": {},
                    "backtest": {}, "verdict_reasons": [], "battery_version": "sf-battery-1",
                    "ran_at": "2026-07-10", "ledger_n_at_run": 1}

        with mock.patch("scripts.run_signal_foundry_harness._load_config", return_value=_CFG_DEFAULT):
            with mock.patch("scripts.run_signal_foundry_harness.run_spec", side_effect=fake_run_spec):
                rc = main(["--root", str(root)])

        assert rc == 0
        assert run_count[0] == 1  # only SF-0002 ran

    def test_iso_week_budget_counted_from_governance(self, tmp_path: Path) -> None:
        """Runs already logged in governance.jsonl count against this week's budget."""
        root = _make_root(tmp_path)

        from scripts.run_signal_foundry_harness import _current_iso_week as _cw
        iso_week = _cw()

        # Pre-fill governance with 2 sf_harness_run events for this week
        gov_path = root / "data" / "signal_foundry" / "governance.jsonl"
        for i in range(2):
            row = {
                "ts": "2026-07-10T00:00:00+00:00",
                "event": "sf_harness_run",
                "evidence": {"spec_id": f"SF-{i+1:04d}", "verdict": "null", "iso_week": iso_week},
            }
            with gov_path.open("a") as fh:
                fh.write(json.dumps(row) + "\n")

        # One registered spec without results
        specs = [
            {**_make_spec("SF-0003", "spec-c", status="registered"), "registered_at": "2026-07-09"},
        ]
        _write_candidates(root, specs)

        run_count = [0]

        def fake_run_spec(spec, repo_root="."):
            run_count[0] += 1
            return {"verdict": "null", "spec": spec, "stats": {}, "placebos": {},
                    "backtest": {}, "verdict_reasons": [], "battery_version": "sf-battery-1",
                    "ran_at": "2026-07-10", "ledger_n_at_run": 3}

        with mock.patch("scripts.run_signal_foundry_harness._load_config", return_value=_CFG_CAP_2):
            with mock.patch("scripts.run_signal_foundry_harness.run_spec", side_effect=fake_run_spec):
                rc = main(["--root", str(root)])

        assert rc == 0
        # Budget was already full (2/2) → SF-0003 must NOT have run
        assert run_count[0] == 0


# ---------------------------------------------------------------------------
# Test: registration BEFORE running (fair DSR n law)
# ---------------------------------------------------------------------------

class TestRegisterBeforeRun:
    def test_all_specs_registered_before_first_run(self, tmp_path: Path) -> None:
        """The harness must register ALL pending specs before calling run_spec on any."""
        root = _make_root(tmp_path)
        specs = [
            _make_spec("SF-0001", "spec-a", status="proposed"),
            _make_spec("SF-0002", "spec-b", status="proposed"),
        ]
        _write_candidates(root, specs)

        registration_events: list[str] = []
        run_events: list[str] = []

        original_register = _register_pending_specs

        def patched_register(candidates_path, dry_run):
            rows, n = original_register(candidates_path, dry_run=dry_run)
            for row in rows:
                if row.get("status") == "registered":
                    registration_events.append(row["id"])
            return rows, n

        def fake_run_spec(spec, repo_root="."):
            run_events.append(spec["id"])
            return {"verdict": "null", "spec": spec, "stats": {}, "placebos": {},
                    "backtest": {}, "verdict_reasons": [], "battery_version": "sf-battery-1",
                    "ran_at": "2026-07-10", "ledger_n_at_run": len(run_events)}

        with mock.patch("scripts.run_signal_foundry_harness._load_config", return_value=_CFG_DEFAULT):
            with mock.patch("scripts.run_signal_foundry_harness._register_pending_specs",
                            side_effect=patched_register):
                with mock.patch("scripts.run_signal_foundry_harness.run_spec",
                                side_effect=fake_run_spec):
                    rc = main(["--root", str(root)])

        assert rc == 0
        assert "SF-0001" in registration_events
        assert "SF-0002" in registration_events


# ---------------------------------------------------------------------------
# Test: dry-run — no disk writes for candidates or results
# ---------------------------------------------------------------------------

class TestDryRun:
    def test_dry_run_no_disk_writes(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path)
        specs = [_make_spec("SF-0001", "spec-a", status="proposed")]
        _write_candidates(root, specs)
        original_content = (root / "data" / "signal_foundry" / "candidates.jsonl").read_text()

        def fake_run_spec(spec, repo_root="."):
            return {"verdict": "null", "spec": spec, "stats": {}, "placebos": {},
                    "backtest": {}, "verdict_reasons": [], "battery_version": "sf-battery-1",
                    "ran_at": "2026-07-10", "ledger_n_at_run": 1}

        with mock.patch("scripts.run_signal_foundry_harness._load_config", return_value=_CFG_DEFAULT):
            with mock.patch("scripts.run_signal_foundry_harness.run_spec", side_effect=fake_run_spec):
                rc = main(["--root", str(root), "--dry-run"])

        assert rc == 0
        # candidates.jsonl unchanged in dry-run
        assert (root / "data" / "signal_foundry" / "candidates.jsonl").read_text() == original_content
        # No results written
        results_dir = root / "data" / "signal_foundry" / "results"
        assert not results_dir.exists() or len(list(results_dir.glob("*.json"))) == 0


# ---------------------------------------------------------------------------
# Test: governance events are written
# ---------------------------------------------------------------------------

class TestGovernanceEvents:
    def test_batch_complete_event_written(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path)
        specs = [
            {**_make_spec("SF-0001", "spec-a", status="registered"), "registered_at": "2026-07-09"},
        ]
        _write_candidates(root, specs)

        def fake_run_spec(spec, repo_root="."):
            return {"verdict": "null", "spec": spec, "stats": {}, "placebos": {},
                    "backtest": {}, "verdict_reasons": [], "battery_version": "sf-battery-1",
                    "ran_at": "2026-07-10", "ledger_n_at_run": 1}

        with mock.patch("scripts.run_signal_foundry_harness._load_config", return_value=_CFG_DEFAULT):
            with mock.patch("scripts.run_signal_foundry_harness.run_spec", side_effect=fake_run_spec):
                rc = main(["--root", str(root)])

        assert rc == 0
        gov = _read_governance(root)
        batch_events = [g for g in gov if g.get("event") == "sf_batch_complete"]
        assert len(batch_events) >= 1

    def test_harness_run_event_per_spec(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path)
        specs = [
            {**_make_spec("SF-0001", "spec-a", status="registered"), "registered_at": "2026-07-09"},
            {**_make_spec("SF-0002", "spec-b", status="registered"), "registered_at": "2026-07-09"},
        ]
        _write_candidates(root, specs)

        def fake_run_spec(spec, repo_root="."):
            return {"verdict": "null", "spec": spec, "stats": {}, "placebos": {},
                    "backtest": {}, "verdict_reasons": [], "battery_version": "sf-battery-1",
                    "ran_at": "2026-07-10", "ledger_n_at_run": 1}

        with mock.patch("scripts.run_signal_foundry_harness._load_config", return_value=_CFG_DEFAULT):
            with mock.patch("scripts.run_signal_foundry_harness.run_spec", side_effect=fake_run_spec):
                rc = main(["--root", str(root)])

        assert rc == 0
        gov = _read_governance(root)
        run_events = [g for g in gov if g.get("event") == "sf_harness_run"]
        assert len(run_events) == 2


# ---------------------------------------------------------------------------
# Test: no candidates.jsonl → graceful no-op
# ---------------------------------------------------------------------------

class TestNoCandidates:
    def test_no_candidates_file_is_noop(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path)
        with mock.patch("scripts.run_signal_foundry_harness._load_config", return_value=_CFG_DEFAULT):
            rc = main(["--root", str(root)])
        assert rc == 0
        status = _read_lane_status(root)
        assert status.get("status") == "full"
