"""Fail-closed wrapper for the covenant-terms compile step (packet B-F09-5).

RULING BLOCKER-1 (elevated finding): .github/workflows/daily.yml runs this
script's main() immediately before the fail-closed health gate step, with no
`continue-on-error`. A producer bug there must never crash the daily job
before the health gate can even run (F13 alarm-bus law) -- main() must catch
ANY producer exception, record a typed covenant_extraction:{state: failed,
reason} marker that evaluate_health() reads on the very next step, and still
exit 0. These tests monkeypatch compile_from_disk() itself (never touching a
real source store/R2) to prove main()'s wrapper, independent of the producer
internals already covered by tests/test_covenant_terms.py.
"""
from __future__ import annotations

import json

import pytest

import scripts.compile_capital_structure_covenant_terms as compile_script
from engine.capital_structure.ingestion_health import (
    COVENANT_EXTRACTION_FAILURE_FILENAME,
    covenant_extraction_coverage,
    evaluate_health,
    health_exit_code,
)


def test_main_never_propagates_a_producer_exception_and_marks_the_health_artifact(
    tmp_path, monkeypatch,
):
    monkeypatch.setattr(compile_script, "_data_root", lambda: tmp_path)

    def _boom(root=None, *, generated_at=None, source_store=None):
        raise RuntimeError("malformed fixture: unbound _seq")

    monkeypatch.setattr(compile_script, "compile_from_disk", _boom)

    exit_code = compile_script.main([])

    assert exit_code == 0  # NEVER a non-zero exit on a producer bug
    marker_path = tmp_path / COVENANT_EXTRACTION_FAILURE_FILENAME
    assert marker_path.exists()
    marker = json.loads(marker_path.read_text())
    assert marker["state"] == "failed"
    assert "RuntimeError" in marker["reason"]
    assert "unbound _seq" in marker["reason"]
    assert marker["failed_at"]

    # the failure marker is exactly what evaluate_health() feeds into the
    # non-gating covenant_extraction census -- confirm the composed state.
    coverage = covenant_extraction_coverage([], [], failure=marker)
    assert coverage["state"] == "failed"
    assert coverage["reason"] == marker["reason"]
    assert coverage["observations"] == 0


def test_main_clears_a_stale_failure_marker_once_the_producer_recovers(tmp_path, monkeypatch):
    monkeypatch.setattr(compile_script, "_data_root", lambda: tmp_path)
    marker_path = tmp_path / COVENANT_EXTRACTION_FAILURE_FILENAME
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.write_text(json.dumps({"state": "failed", "reason": "stale", "failed_at": "x"}))

    monkeypatch.setattr(
        compile_script, "compile_from_disk",
        lambda root=None, *, generated_at=None, source_store=None: {
            "status": "ok", "schema": compile_script.COVENANT_TERM_SCHEMA,
            "eligible_manifests": 0, "deferred": 0, "observations": 0, "path": str(tmp_path),
        },
    )

    exit_code = compile_script.main([])

    assert exit_code == 0
    assert not marker_path.exists()  # a healed run clears the prior crash's marker


def test_covenant_extraction_coverage_reports_failed_state_with_a_reason():
    failed = covenant_extraction_coverage([], [], failure={"reason": "ValueError: boom"})
    assert failed == {
        "eligible_exhibits": 0,
        "covered_manifests": 0,
        "observations": 0,
        "issuers_covered": 0,
        "unavailable_terms": 0,
        "state": "failed",
        "reason": "ValueError: boom",
    }


def test_covenant_extraction_coverage_without_failure_is_unaffected():
    # No `failure` kwarg at all: behaves exactly as before (Blocker 1 in the
    # PRIOR review round -- flat-row shape, "uncovered" when there is nothing).
    uncovered = covenant_extraction_coverage([], [])
    assert uncovered["state"] == "uncovered"
    assert "reason" not in uncovered


def test_evaluate_health_reports_covenant_extraction_failed_without_a_nonzero_exit(tmp_path):
    """Full integration path a reviewer would actually run: a REAL failure
    marker file on disk (as main() would have written it), read back through
    evaluate_health() exactly as scripts/check_capital_structure_health.py
    calls it, with health_exit_code() proving the OTHER (real) gate stays
    unaffected by a covenant-producer crash."""
    marker_path = tmp_path / COVENANT_EXTRACTION_FAILURE_FILENAME
    marker_path.write_text(json.dumps({
        "state": "failed",
        "reason": "UnboundLocalError: cannot access local variable '_seq'",
        "failed_at": "2026-09-06T00:00:00Z",
    }))

    record = evaluate_health(tmp_path)

    assert record["covenant_extraction"]["state"] == "failed"
    assert "_seq" in record["covenant_extraction"]["reason"]
    # covenant_extraction is context-only (never a gate): an empty root with
    # no selected filings is a legitimate "no_new_work" verdict, not "fail".
    assert record["verdict"] != "fail"
    assert health_exit_code(record) == 0
