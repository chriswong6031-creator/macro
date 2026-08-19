"""The reliability report is the program's progress metric, so it must not be able
to report a number it did not measure.

`research/CI_MERGE_GATE_RELIABILITY_ROOT_CAUSE_2026_08_19.md` sets its acceptance
gate as a green rate from this script. A reporter that silently returns 0%, or
that counts a still-running run as a failure, would make that gate meaningless in
either direction.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "ci_gate_reliability_report", ROOT / "scripts" / "ci_gate_reliability_report.py"
)
REPORT = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = REPORT
_spec.loader.exec_module(REPORT)


class TestDataCouplingClassifier:
    def test_a_tmp_path_suite_is_not_data_coupled(self, tmp_path, monkeypatch) -> None:
        suite = tmp_path / "tests" / "test_pure.py"
        suite.parent.mkdir(parents=True)
        suite.write_text("def test_x(tmp_path):\n    (tmp_path / 'a').write_text('1')\n")
        monkeypatch.setattr(REPORT, "ROOT", tmp_path)
        assert REPORT._reads_committed_data("tests/test_pure.py") is False

    @pytest.mark.parametrize(
        "body",
        [
            "pd.read_parquet('data/breadth/_closes_cache.parquet')",
            'open(REPO / "data" / "x.json")',
            "resolve_close('CFG', data_dir=str(REPO / 'd'))",
            "ppm.load_closes(ROOT)",
        ],
    )
    def test_a_committed_tree_read_is_data_coupled(self, tmp_path, monkeypatch, body) -> None:
        suite = tmp_path / "tests" / "test_reads.py"
        suite.parent.mkdir(parents=True)
        suite.write_text(f"def test_x():\n    {body}\n")
        monkeypatch.setattr(REPORT, "ROOT", tmp_path)
        assert REPORT._reads_committed_data("tests/test_reads.py") is True

    def test_a_missing_suite_is_unknown_not_clean(self, tmp_path, monkeypatch) -> None:
        """A sparse worktree hides suites. Unknown must never read as code-only —
        that would understate the coupling count and flatter the diagnosis."""
        monkeypatch.setattr(REPORT, "ROOT", tmp_path)
        assert REPORT._reads_committed_data("tests/test_absent.py") is None


class TestGreenRateNeverInvents:
    def _stub(self, monkeypatch, *, returncode=0, stdout="", raises=None):
        def fake_run(*_a, **_k):
            if raises:
                raise raises
            return type("P", (), {"returncode": returncode, "stdout": stdout, "stderr": "boom"})()
        monkeypatch.setattr(REPORT.subprocess, "run", fake_run)

    def test_gh_failure_is_a_stated_skip_not_a_zero(self, monkeypatch) -> None:
        self._stub(monkeypatch, returncode=1)
        assert "skipped" in REPORT.measure_green_rate(10)

    def test_gh_absent_is_a_stated_skip(self, monkeypatch) -> None:
        self._stub(monkeypatch, raises=OSError("no gh"))
        assert "skipped" in REPORT.measure_green_rate(10)

    def test_unparseable_output_is_a_stated_skip(self, monkeypatch) -> None:
        self._stub(monkeypatch, stdout="{not json")
        assert "skipped" in REPORT.measure_green_rate(10)

    def test_in_flight_runs_are_excluded_not_counted_as_red(self, monkeypatch) -> None:
        """A queued run is not a failure. Counting it as one would make the gate
        look worse after every dispatch."""
        runs = [
            {"status": "completed", "conclusion": "success", "createdAt": "2026-08-01T00:00:00Z"},
            {"status": "completed", "conclusion": "failure", "createdAt": "2026-08-02T00:00:00Z"},
            {"status": "in_progress", "conclusion": None, "createdAt": "2026-08-03T00:00:00Z"},
        ]
        self._stub(monkeypatch, stdout=json.dumps(runs))
        got = REPORT.measure_green_rate(10)
        assert got["completed"] == 2 and got["green"] == 1
        assert got["green_pct"] == pytest.approx(50.0)

    def test_only_success_counts_as_green(self, monkeypatch) -> None:
        """`cancelled` is not a pass — a superseded run proves nothing."""
        runs = [
            {"status": "completed", "conclusion": "cancelled", "createdAt": "2026-08-01T00:00:00Z"},
            {"status": "completed", "conclusion": "success", "createdAt": "2026-08-02T00:00:00Z"},
        ]
        self._stub(monkeypatch, stdout=json.dumps(runs))
        assert REPORT.measure_green_rate(10)["green"] == 1

    def test_no_completed_runs_is_a_skip_not_zero_percent(self, monkeypatch) -> None:
        self._stub(monkeypatch, stdout=json.dumps([{"status": "queued", "conclusion": None}]))
        assert "skipped" in REPORT.measure_green_rate(10)


def test_the_real_manifest_classifies_and_is_mostly_data_coupled() -> None:
    """The claim this script exists to support, asserted against the real manifest."""
    got = REPORT.measure_coupling()
    assert got["jobs_total"] > 100, "the legacy manifest shrank unexpectedly"
    assert got["classified"] > 0.9 * got["jobs_total"], (
        f"only {got['classified']}/{got['jobs_total']} jobs classified — a sparse "
        "worktree hides suites; run `python3 scripts/worktree_sparse.py full`")
    assert got["coupled_pct"] > 50, (
        f"data coupling is {got['coupled_pct']:.0f}% — if this has genuinely fallen "
        "below half, re-measure the green rate before citing "
        "DSC:MERGE-GATE-IS-GATED-ON-MOVING-DATA")


def test_report_renders_without_gh() -> None:
    assert REPORT.main(["--coupling"]) == 0
