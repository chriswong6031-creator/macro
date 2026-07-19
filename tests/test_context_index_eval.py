"""
grade_row semantics per README v1.4 / CXI-R17.

- R17a: required_status binds ONLY to verdict-carrying registry sources
  (DO_NOT_REBUILD.md, ruling_graph.yml, compiled_kill_registry.yml); other
  required sources are graded on top-10 presence alone. An active masterplan
  required alongside a kill row must not be asked to carry the kill status.
- R17c: required_status: superseded rows are presence-only (the amended registry
  row keeps its live status while recording the struck sub-clause in text).
"""

from __future__ import annotations

from scripts.context_index_eval import grade_row


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
