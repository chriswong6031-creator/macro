"""Contracts for the append-only manager grade/excess history."""
from __future__ import annotations

from engine import manager_history as mh


def _memory() -> dict:
    return {
        "as_of": "2026-08-07",
        "benchmark": "SPY",
        "horizon_days": 60,
        "funds": {
            "alpha": {
                "name": "Alpha Fund", "grade": "A",
                "by_quarter": [
                    {"period_end": "2025-12-31", "anchor": "2026-02-17",
                     "n_priced": 4, "dw_excess_60d": 0.04,
                     "new_dw_excess_60d": 0.06, "add_dw_excess_60d": 0.02,
                     "hit_60d": 0.75, "rank": 1, "n_cohort": 10,
                     "beat": True},
                    {"period_end": "2026-03-31", "anchor": "2026-05-15",
                     "n_priced": 3, "dw_excess_60d": None,
                     "rank": None, "n_cohort": 0, "beat": None},
                ],
            },
            "beta": {
                "name": "Beta Fund", "grade": "B",
                "by_quarter": [
                    {"period_end": "2025-12-31", "anchor": "2026-02-17",
                     "n_priced": 2, "dw_excess_60d": -0.01,
                     "new_dw_excess_60d": None, "add_dw_excess_60d": -0.01,
                     "hit_60d": 0.5, "rank": 8, "n_cohort": 10,
                     "beat": False},
                ],
            },
        },
    }


def test_rows_include_only_settled_results_and_descriptive_grades():
    rows = mh._rows_from_memory(_memory(), recorded_at="2026-08-08T00:00:00+00:00")
    assert len(rows) == 2
    by_slug = {row["slug"]: row for row in rows}
    assert by_slug["alpha"]["outcome_grade"] == "A"
    assert by_slug["beta"]["outcome_grade"] == "D"
    assert all(row["method_version"] == mh.METHOD_VERSION for row in rows)
    assert all(row["roster_n"] == 2 for row in rows)
    assert len({row["roster_hash"] for row in rows}) == 1


def test_nightly_append_is_idempotent_and_freezes_first_vintage(tmp_path, monkeypatch):
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    assert mh.advance_manager_history(_memory(), root=tmp_path) == 2

    revised = _memory()
    revised["funds"]["alpha"]["by_quarter"][0]["dw_excess_60d"] = 0.99
    assert mh.advance_manager_history(revised, root=tmp_path) == 0

    frame = mh._load(tmp_path)
    alpha = frame[frame["slug"] == "alpha"].iloc[0]
    assert alpha["dw_excess_60d"] == 0.04
    summary = mh.manager_history_summary(tmp_path)
    assert summary["n_entries"] == 2
    assert summary["n_funds"] == 2
    assert summary["n_quarters"] == 1


def test_missing_roster_provenance_is_added_without_revising_outcomes(
        tmp_path, monkeypatch):
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    assert mh.advance_manager_history(_memory(), root=tmp_path) == 2
    frame = mh._load(tmp_path).drop(columns=["roster_n", "roster_hash"])
    frame.to_parquet(mh._path(tmp_path), index=False)

    revised = _memory()
    revised["funds"]["alpha"]["by_quarter"][0]["dw_excess_60d"] = 0.99
    assert mh.advance_manager_history(revised, root=tmp_path) == 0

    migrated = mh._load(tmp_path)
    alpha = migrated[migrated["slug"] == "alpha"].iloc[0]
    assert alpha["dw_excess_60d"] == 0.04
    assert alpha["roster_n"] == 2
    assert isinstance(alpha["roster_hash"], str)
    assert len(alpha["roster_hash"]) == 64


def test_non_nightly_lane_never_writes(tmp_path, monkeypatch):
    monkeypatch.setenv("COLLECT_LANE", "intraday")
    assert mh.advance_manager_history(_memory(), root=tmp_path) == 0
    assert not mh._path(tmp_path).exists()
