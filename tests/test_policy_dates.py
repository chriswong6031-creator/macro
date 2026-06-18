"""Tests for engine.policy_dates — live dating of the policy substrate."""
from __future__ import annotations

from datetime import date

from engine import policy_dates as pd

TODAY = date(2026, 6, 18)


def test_days_to_signs():
    assert pd._days_to("2026-06-28", TODAY) == 10
    assert pd._days_to("2026-06-08", TODAY) == -10
    assert pd._days_to("bad", TODAY) is None


def test_annotate_staleness():
    fresh = pd.annotate({"as_of": "2026-06-18"}, today=TODAY)["staleness"]
    assert fresh["age_days"] == 0 and fresh["stale"] is False
    stale = pd.annotate({"as_of": "2026-06-01"}, today=TODAY)["staleness"]
    assert stale["age_days"] == 17 and stale["stale"] is True


def test_annotate_overdue_logic():
    intel = {
        "as_of": "2026-06-18",
        "fed": {"task_forces": [
            {"id": "tf_a", "check_by": "2026-05-01", "status": "pending"},   # past + pending -> overdue
            {"id": "tf_b", "check_by": "2026-12-31", "status": "pending"},   # future -> not
        ]},
        "predictions": [
            {"id": "P1", "check_by": "2026-05-01", "status": "open"},        # past + open -> overdue
            {"id": "P2", "check_by": "2026-05-01", "status": "hit"},         # past but resolved -> not
            {"id": "P3", "check_by": "2026-12-31", "status": "open"},        # future -> not
        ],
    }
    a = pd.annotate(intel, today=TODAY)
    assert a["task_forces"]["tf_a"]["overdue"] is True and a["task_forces"]["tf_b"]["overdue"] is False
    assert a["overdue_task_forces"] == 1
    assert a["predictions"]["P1"]["overdue"] is True
    assert a["predictions"]["P2"]["overdue"] is False and a["predictions"]["P3"]["overdue"] is False
    assert a["overdue_predictions"] == 1


def test_annotate_defensive_on_empty():
    a = pd.annotate({}, today=TODAY)
    assert a["staleness"]["stale"] is False and a["overdue_predictions"] == 0
    assert pd.annotate(None, today=TODAY)["task_forces"] == {}
