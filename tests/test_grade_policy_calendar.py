"""Tests for scripts.grade_policy_calendar — maturity gating + idempotence.

Synthetic fixtures only; never reads or writes the real tracked JSONL.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from scripts.grade_policy_calendar import grade_matured_rows


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ledger(tmp_path: Path, rows: list[dict]) -> Path:
    p = tmp_path / "data" / "foresight" / "policy_calendar_ledger.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return p


def _fed_reg(tmp_path: Path, basket_id: str, comments_close_on: str) -> None:
    """Write a minimal federal_register/documents.parquet with one matching document."""
    p = tmp_path / "data" / "federal_register" / "documents.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([{
        "basket_id": basket_id,
        "comments_close_on": comments_close_on,
    }])
    df.to_parquet(p, index=False)


def _past_date(days: int = 5) -> str:
    return (date.today() - timedelta(days=days)).isoformat()


def _future_date(days: int = 30) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


# ---------------------------------------------------------------------------
# Test 1: pending row (future close date) is NOT graded
# ---------------------------------------------------------------------------

def test_pending_row_not_graded(tmp_path: Path) -> None:
    """A row whose next_comment_close_date is in the future must remain ungraded."""
    rows = [{
        "theme": "solar",
        "asof": "2026-07-01",
        "logged_utc": "2026-07-01T00:00:00+00:00",
        "days_to_comment_close": 30,
        "next_comment_close_date": _future_date(30),
        "prorule_inflow_60d": 1,
        "rule_finalization_60d": 0,
        "evidence_class": "dated-structured",
    }]
    _ledger(tmp_path, rows)
    # no need for fed_reg; shouldn't be consulted
    n = grade_matured_rows(root=tmp_path)
    assert n == 0

    p = tmp_path / "data" / "foresight" / "policy_calendar_ledger.jsonl"
    loaded = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    assert loaded[0].get("graded_date") is None


# ---------------------------------------------------------------------------
# Test 2: matured + matching document → accurate=True
# ---------------------------------------------------------------------------

def test_matured_matching_doc_accurate(tmp_path: Path) -> None:
    """When the predicted close date has passed AND a document matches, accurate=True."""
    close_date = _past_date(5)
    rows = [{
        "theme": "solar",
        "asof": "2026-06-01",
        "logged_utc": "2026-06-01T00:00:00+00:00",
        "days_to_comment_close": 5,
        "next_comment_close_date": close_date,
        "prorule_inflow_60d": 2,
        "rule_finalization_60d": 0,
        "evidence_class": "dated-structured",
    }]
    _ledger(tmp_path, rows)
    _fed_reg(tmp_path, basket_id="solar", comments_close_on=close_date)

    n = grade_matured_rows(root=tmp_path)
    assert n == 1

    p = tmp_path / "data" / "foresight" / "policy_calendar_ledger.jsonl"
    loaded = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    assert loaded[0]["graded_date"] == date.today().isoformat()
    assert loaded[0]["accurate"] is True


# ---------------------------------------------------------------------------
# Test 3: matured + NO matching document → accurate=False
# ---------------------------------------------------------------------------

def test_matured_no_matching_doc_inaccurate(tmp_path: Path) -> None:
    """When the predicted close date has passed AND no document matches, accurate=False."""
    close_date = _past_date(5)
    rows = [{
        "theme": "defense",
        "asof": "2026-06-01",
        "logged_utc": "2026-06-01T00:00:00+00:00",
        "days_to_comment_close": 5,
        "next_comment_close_date": close_date,
        "prorule_inflow_60d": 1,
        "rule_finalization_60d": 0,
        "evidence_class": "dated-structured",
    }]
    _ledger(tmp_path, rows)
    # Write fed_reg with a DIFFERENT basket_id → no match for "defense"
    _fed_reg(tmp_path, basket_id="solar", comments_close_on=close_date)

    n = grade_matured_rows(root=tmp_path)
    assert n == 1

    p = tmp_path / "data" / "foresight" / "policy_calendar_ledger.jsonl"
    loaded = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    assert loaded[0]["graded_date"] is not None
    assert loaded[0]["accurate"] is False


# ---------------------------------------------------------------------------
# Test 4: idempotence — already-graded row not re-graded
# ---------------------------------------------------------------------------

def test_idempotent_second_run(tmp_path: Path) -> None:
    """Running the grader twice must not change already-graded rows."""
    close_date = _past_date(5)
    rows = [{
        "theme": "solar",
        "asof": "2026-06-01",
        "logged_utc": "2026-06-01T00:00:00+00:00",
        "days_to_comment_close": 5,
        "next_comment_close_date": close_date,
        "prorule_inflow_60d": 1,
        "rule_finalization_60d": 0,
        "evidence_class": "dated-structured",
    }]
    _ledger(tmp_path, rows)
    _fed_reg(tmp_path, basket_id="solar", comments_close_on=close_date)

    n1 = grade_matured_rows(root=tmp_path)
    assert n1 == 1

    n2 = grade_matured_rows(root=tmp_path)
    assert n2 == 0, "second run must not re-grade already-graded rows"


# ---------------------------------------------------------------------------
# Test 5: mixed pending + matured — only matured is graded
# ---------------------------------------------------------------------------

def test_mixed_rows_only_matured_graded(tmp_path: Path) -> None:
    """Mixed rows: only the matured one should be graded."""
    past = _past_date(5)
    future = _future_date(30)
    rows = [
        {"theme": "solar", "asof": "2026-06-01", "logged_utc": "...",
         "days_to_comment_close": 5, "next_comment_close_date": past,
         "prorule_inflow_60d": 1, "rule_finalization_60d": 0, "evidence_class": "dated-structured"},
        {"theme": "nuclear_power", "asof": "2026-07-01", "logged_utc": "...",
         "days_to_comment_close": 30, "next_comment_close_date": future,
         "prorule_inflow_60d": 0, "rule_finalization_60d": 0, "evidence_class": "dated-structured"},
    ]
    _ledger(tmp_path, rows)
    _fed_reg(tmp_path, basket_id="solar", comments_close_on=past)

    n = grade_matured_rows(root=tmp_path)
    assert n == 1

    p = tmp_path / "data" / "foresight" / "policy_calendar_ledger.jsonl"
    loaded = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    solar = next(r for r in loaded if r["theme"] == "solar")
    nuclear = next(r for r in loaded if r["theme"] == "nuclear_power")
    assert solar["graded_date"] is not None
    assert nuclear.get("graded_date") is None


# ---------------------------------------------------------------------------
# Test 6: absent ledger → graceful return 0
# ---------------------------------------------------------------------------

def test_absent_ledger_returns_zero(tmp_path: Path) -> None:
    n = grade_matured_rows(root=tmp_path)
    assert n == 0
