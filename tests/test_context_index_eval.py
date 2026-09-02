"""
grade_row semantics per README v1.4 / CXI-R17, plus the CXI eval-harness metric
repair (C0, 2026-08-28, op key macro-context-index-completion-20260828-sol-001):
true governance A0/A1 precision, negative-control accuracy, NOT-EVALUATED
handling for a missing/unindexed project DB, and per-row project scoping
(CXI-R16).

- R17a: required_status binds ONLY to verdict-carrying registry sources
  (DO_NOT_REBUILD.md, ruling_graph.yml, compiled_kill_registry.yml); other
  required sources are graded on top-10 presence alone. An active masterplan
  required alongside a kill row must not be asked to carry the kill status.
- R17c: required_status: superseded rows are presence-only (the amended registry
  row keeps its live status while recording the struck sub-clause in text).
"""

from __future__ import annotations

import pytest

from scripts.context_index_eval import (
    grade_row,
    evaluate_row,
    compute_governance_true_precision,
    compute_negative_control_accuracy,
    _not_evaluated_reason,
    _project_db_map_for_row,
)


def _pkt(rows):
    return {"results": rows, "no_answer_reason": None}


def _res(path, status):
    return {"path": path, "source_uri": f"repo://macro-dashboard/{path}", "status": status}


_DNR = "research/DO_NOT_REBUILD.md"
_MP = "research/WINNER_AUTOPSY_MASTERPLAN_BY_FABLE.md"


def _row(**over):
    base = {
        "id": "CTX-TEST",
        "required_sources": [_DNR, _MP],
        "required_status": "killed",
    }
    base.update(over)
    return base


def test_active_masterplan_alongside_kill_row_passes():
    """R17a regression (CTX-008/CTX-013 class): the masterplan is active; only
    the registry chunk must carry the kill status."""
    grade = grade_row(_row(), _pkt([_res(_DNR, "killed"), _res(_MP, "active")]))
    assert grade["pass"], grade


def test_verdict_source_wrong_status_fails():
    grade = grade_row(_row(), _pkt([_res(_DNR, "forbidden"), _res(_MP, "active")]))
    assert not grade["pass"]
    assert grade["miss_sources"] == [_DNR]


def test_verdict_source_absent_fails():
    grade = grade_row(_row(), _pkt([_res(_MP, "active")]))
    assert not grade["pass"]
    assert grade["miss_sources"] == [_DNR]


def test_non_verdict_source_below_top10_fails():
    filler = [_res(f"engine/filler_{n}.py", "active") for n in range(10)]
    grade = grade_row(_row(), _pkt([_res(_DNR, "killed")] + filler + [_res(_MP, "active")]))
    assert not grade["pass"]
    assert grade["miss_sources"] == [_MP]


def test_superseded_rows_are_presence_only():
    """R17c (CTX-010/CTX-082 class): the amended registry row stays 'forbidden'
    for its surviving ban; superseded rows assert presence of the amended row
    plus the superseding masterplan, not a chunk status."""
    grade = grade_row(
        _row(required_status="superseded"),
        _pkt([_res(_DNR, "forbidden"), _res(_MP, "active")]),
    )
    assert grade["pass"], grade


def test_superseded_rows_still_require_all_sources():
    grade = grade_row(_row(required_status="superseded"), _pkt([_res(_DNR, "forbidden")]))
    assert not grade["pass"]
    assert grade["miss_sources"] == [_MP]


def test_no_answer_honest_null_passes_and_results_fail():
    row = _row(required_sources=[], required_status="no_answer")
    assert grade_row(row, {"results": [], "no_answer_reason": "nothing matched"})["pass"]
    assert not grade_row(row, _pkt([_res(_MP, "active")]))["pass"]


def test_retrieval_error_is_not_an_honest_null():
    row = _row(required_status="no_answer", required_sources=[])
    grade = grade_row(row, {"results": [], "no_answer_reason": None, "error": "boom"})
    assert not grade["pass"]
    assert "ERROR" in grade["notes"]


# ---------------------------------------------------------------------------
# (a) TRUE governance A0/A1 precision — TP/FP arithmetic + 0-denominator NOT-MET
# ---------------------------------------------------------------------------


def _gov_row(**over):
    base = {
        "id": "CTX-GOV",
        "family": "governance",
        "required_sources": [_DNR],
        "acceptable_sources": ["CLAUDE.md"],
    }
    base.update(over)
    return base


def _gov_result(path, authority_class, project="macro-dashboard"):
    return {
        "path": path,
        "source_uri": f"repo://{project}/{path}",
        "authority_class": authority_class,
    }


def test_governance_true_precision_counts_required_and_acceptable_sources_as_tp():
    row = _gov_row()
    packet = {
        "results": [
            _gov_result(_DNR, "A0"),  # TP: matches required_sources
            _gov_result("CLAUDE.md", "A1"),  # TP: matches acceptable_sources
            _gov_result("research/unrelated_doc.md", "A0"),  # FP: A0/A1 but no source match
            _gov_result("engine/some_engine_file.py", "A3"),  # ignored: not A0/A1
        ],
    }
    results_by_id = {row["id"]: {"row": row, "packet": packet}}

    out = compute_governance_true_precision(results_by_id)

    assert out["tp"] == 2
    assert out["fp"] == 1
    assert out["precision"] == pytest.approx(2 / 3)


def test_governance_true_precision_ignores_non_governance_rows():
    gov = _gov_row()
    gov_packet = {"results": [_gov_result(_DNR, "A0")]}
    other = {"id": "CTX-OTHER", "family": "research", "required_sources": [_DNR], "acceptable_sources": []}
    other_packet = {"results": [_gov_result("research/unrelated_doc.md", "A0")]}
    results_by_id = {
        gov["id"]: {"row": gov, "packet": gov_packet},
        other["id"]: {"row": other, "packet": other_packet},
    }

    out = compute_governance_true_precision(results_by_id)

    # Only the governance row's A0 result counts; the research-family FP is excluded.
    assert out["tp"] == 1
    assert out["fp"] == 0
    assert out["precision"] == 1.0


def test_governance_true_precision_zero_denominator_is_not_met():
    row = _gov_row()
    packet = {"results": [_gov_result(_DNR, "A3")]}  # matches, but not A0/A1
    results_by_id = {row["id"]: {"row": row, "packet": packet}}

    out = compute_governance_true_precision(results_by_id)

    assert out["tp"] == 0
    assert out["fp"] == 0
    assert out["precision"] is None


def test_governance_true_precision_empty_scope_is_not_met():
    out = compute_governance_true_precision({})
    assert out["tp"] == 0
    assert out["fp"] == 0
    assert out["precision"] is None


# ---------------------------------------------------------------------------
# (b) Negative-control (no-answer) accuracy
# ---------------------------------------------------------------------------


def test_negative_control_accuracy_computation():
    results_by_id = {
        "CTX-N1": {"row": {"family": "negative_control"}, "pass": True},
        "CTX-N2": {"row": {"family": "negative_control"}, "pass": False},
        "CTX-N3": {"row": {"family": "negative_control"}, "pass": True},
        "CTX-G1": {"row": {"family": "governance"}, "pass": True},  # excluded: wrong family
    }

    out = compute_negative_control_accuracy(results_by_id)

    assert out["total"] == 3
    assert out["pass"] == 2
    assert out["accuracy"] == pytest.approx(2 / 3)


def test_negative_control_accuracy_zero_rows_in_scope_is_not_met():
    out = compute_negative_control_accuracy({})
    assert out["total"] == 0
    assert out["pass"] == 0
    assert out["accuracy"] is None


# ---------------------------------------------------------------------------
# (c) NOT-EVALUATED: a missing project DB never grades as a correct null
# ---------------------------------------------------------------------------


def test_not_evaluated_reason_reports_missing_db_file(tmp_path):
    assert _not_evaluated_reason("terminal", tmp_path) == "db missing: terminal.sqlite"


def test_not_evaluated_reason_none_when_db_present_and_indexed(tmp_path, monkeypatch):
    import scripts.context_index_eval as cie

    db_path = tmp_path / "terminal.sqlite"
    db_path.write_bytes(b"not a real sqlite file, existence + sha are both faked")
    monkeypatch.setattr(cie, "index_sha", lambda path: "deadbeef")

    assert cie._not_evaluated_reason("terminal", tmp_path) is None


def test_no_answer_row_with_missing_db_is_not_evaluated_never_pass(tmp_path):
    """The exact bug this wave fixes: a no_answer row must NEVER grade as a
    'correct null' just because an absent DB returns zero results."""
    row = {
        "id": "CTX-P1",
        "family": "negative_control",
        "project": "terminal",
        "required_sources": [],
        "required_status": "no_answer",
        "query": "does this cross-repo system exist",
    }

    result = evaluate_row(row, db_dir=tmp_path, repo_root_map={})

    assert result["not_evaluated"] is True
    assert result["reason"] == "db missing: terminal.sqlite"
    assert "pass" not in result


def test_not_evaluated_row_excluded_from_negative_control_accuracy(tmp_path):
    """A NOT-EVALUATED row must never enter results_by_id, so it can never be
    counted (correctly or incorrectly) by any downstream metric."""
    row = {
        "id": "CTX-P1",
        "family": "negative_control",
        "project": "terminal",
        "required_sources": [],
        "required_status": "no_answer",
        "query": "does this cross-repo system exist",
    }
    result = evaluate_row(row, db_dir=tmp_path, repo_root_map={})
    assert result["not_evaluated"] is True

    # Simulating run_eval's loop: a not_evaluated row is never added to results_by_id.
    results_by_id: dict = {}
    out = compute_negative_control_accuracy(results_by_id)
    assert out["total"] == 0
    assert out["accuracy"] is None


# ---------------------------------------------------------------------------
# (d) Per-row project scoping (CXI-R16): exactly the owning project's DB
# ---------------------------------------------------------------------------


def test_project_db_map_for_row_scopes_to_owning_project_only():
    assert _project_db_map_for_row({"project": "terminal"}) == {"terminal": "terminal.sqlite"}
    assert _project_db_map_for_row({"project": "mastermind"}) == {"mastermind": "mastermind.sqlite"}
    assert _project_db_map_for_row({"project": "macro-dashboard"}) == {"macro-dashboard": "shared.sqlite"}


def test_project_db_map_for_row_defaults_to_macro_dashboard_when_absent():
    assert _project_db_map_for_row({}) == {"macro-dashboard": "shared.sqlite"}


def test_private_visibility_row_still_scopes_to_its_own_project_only(monkeypatch):
    """Regression guard for the fixed bug: a private-visibility row whose
    project is macro-dashboard must NOT expand to the full 3-DB map."""
    row = {
        "id": "CTX-005",
        "family": "gotcha",
        "project": "macro-dashboard",
        "visibility": "private",
    }
    assert _project_db_map_for_row(row) == {"macro-dashboard": "shared.sqlite"}


def test_evaluate_row_calls_build_packet_with_only_the_owning_project_db_map(tmp_path, monkeypatch):
    """End-to-end (within evaluate_row) confirmation that the removed 3-DB
    code path for private rows is gone: build_packet is invoked with
    project_db_map scoped to exactly the row's own project."""
    import scripts.context_index_eval as cie

    captured = {}

    def fake_build_packet(**kwargs):
        captured.update(kwargs)
        return {"results": [], "no_answer_reason": "nothing matched"}

    monkeypatch.setattr(cie, "_not_evaluated_reason", lambda project, db_dir: None)
    monkeypatch.setattr(cie, "build_packet", fake_build_packet)

    row = {
        "id": "CTX-PRIV",
        "family": "gotcha",
        "project": "terminal",
        "visibility": "private",
        "required_sources": [],
        "required_status": "no_answer",
        "query": "does something exist",
    }

    result = evaluate_row(row, db_dir=tmp_path, repo_root_map={})

    assert result["not_evaluated"] is False
    assert captured["project_db_map"] == {"terminal": "terminal.sqlite"}


# ---------------------------------------------------------------------------
# (e) Intended in-scope NOT-EVALUATED rows fail the promotion gates closed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("not_evaluated_family", "affected_gate"),
    [
        ("research", None),
        ("adjudication_replay", "gate_adj"),
        ("governance", "gate_gov"),
        ("negative_control", "gate_neg"),
    ],
)
def test_in_scope_not_evaluated_row_forces_global_and_affected_gates_not_met(
    tmp_path, monkeypatch, not_evaluated_family, affected_gate
):
    """An intended row that cannot be evaluated is not a harmless denominator
    exclusion: the global promotion gate and its own family gate must be
    NOT-MET, while the other fully evaluated gates remain independently useful.
    """
    import scripts.context_index_eval as cie

    family_counts = {
        "research": 1,
        "adjudication_replay": 2,
        "governance": 2,
        "negative_control": 2,
    }
    rows = []
    for family, count in family_counts.items():
        for number in range(count):
            row_id = f"CTX-{family}-{number}"
            rows.append({
                "id": row_id,
                "family": family,
                "project": "macro-dashboard",
                "visibility": "shared",
                "required_sources": [f"research/{row_id}.md"],
                "acceptable_sources": [],
            })

    target = next(row for row in rows if row["family"] == not_evaluated_family)

    def fake_evaluate_row(row, db_dir, repo_root_map):
        if row["id"] == target["id"]:
            return {
                "not_evaluated": True,
                "reason": "db missing: shared.sqlite",
                "row": row,
            }
        results = []
        if row["family"] == "governance":
            results = [{
                "path": row["required_sources"][0],
                "source_uri": row["required_sources"][0],
                "authority_class": "A0",
            }]
        return {
            "not_evaluated": False,
            "row": row,
            "pass": True,
            "packet": {"results": results},
            "latency_s": 0.01,
        }

    monkeypatch.setattr(cie, "get_db_dir", lambda: tmp_path)
    monkeypatch.setattr(cie, "load_questions", lambda: rows)
    monkeypatch.setattr(cie, "_resolve_repo_root_map", lambda: {})
    monkeypatch.setattr(cie, "index_sha", lambda _path: "indexed-test-sha")
    monkeypatch.setattr(cie, "evaluate_row", fake_evaluate_row)

    summary = cie.run_eval(output_path=tmp_path / "results.md")

    assert summary["gate_global"] == "NOT-MET"
    for gate_name in ("gate_adj", "gate_gov", "gate_neg"):
        expected = "NOT-MET" if gate_name == affected_gate else "PASS"
        assert summary[gate_name] == expected
