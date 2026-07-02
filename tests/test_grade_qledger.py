"""Tests for scripts/grade_qledger.py — the nightly qledger grading runner.

All tests are hermetic: tmp_path store, monkeypatched price layer.
Covers the three requirements from the spec:
  * idempotency — re-running the grader never double-grades a (claim_id, horizon_d).
  * horizon capping — a horizon_d=21 claim grades only at 5d and 21d; not 63d.
  * coverage miss handling — when subject or bench prices are missing the horizon
    is counted in n_blocked_by_coverage, not silently dropped.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from engine import qledger as q
import scripts.grade_qledger as grader


# --------------------------------------------------------------------------- #
# synthetic price layer (same fixture pattern as test_qledger.py)
# --------------------------------------------------------------------------- #
def _mk_series(start: str, days: int, start_px: float, drift: float) -> pd.Series:
    idx = pd.bdate_range(start=start, periods=days)
    vals = [start_px * (1.0 + drift) ** i for i in range(days)]
    return pd.Series(vals, index=idx)


@pytest.fixture
def prices(monkeypatch):
    """Install synthetic closes for subject (CARR), bench (SPY), and control (XLI)."""
    store = {
        "CARR": _mk_series("2026-01-01", 180, 100.0, 0.010),  # +1%/bd
        "SPY":  _mk_series("2026-01-01", 180, 400.0, 0.002),  # +0.2%/bd
        "XLI":  _mk_series("2026-01-01", 180, 100.0, 0.004),  # +0.4%/bd
    }

    def _series(ticker, root):
        return store.get(ticker)

    monkeypatch.setattr("engine.ai_desk._close_series", _series)
    return store


@pytest.fixture
def no_prices(monkeypatch):
    """Price layer returns None for everything → coverage-miss scenario."""
    monkeypatch.setattr("engine.ai_desk._close_series", lambda ticker, root: None)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _register_claim(tmp_path, asof="2026-02-02", horizon_d=63,
                    ticker="CARR", desk="altdata", salt=None):
    c = q.make_claim(desk=desk, asof=asof, scope_type="entity",
                     scope_key=ticker, direction=1, horizon_d=horizon_d,
                     timestamp_quality="CRAWL_BOUNDED", sector="Industrials",
                     claim_family=desk)
    if salt is not None:
        c["salt"] = str(salt)
    return q.register(c, root=tmp_path)


def _grade_count(tmp_path) -> int:
    return len(q.load_grades(tmp_path))


# --------------------------------------------------------------------------- #
# idempotency
# --------------------------------------------------------------------------- #
def test_run_idempotent(prices, tmp_path):
    """Running the grader twice on the same store must not produce duplicate grades."""
    _register_claim(tmp_path)
    today = date(2026, 6, 1)

    s1 = grader.run(root=tmp_path, today=today)
    n_after_first = _grade_count(tmp_path)

    s2 = grader.run(root=tmp_path, today=today)
    n_after_second = _grade_count(tmp_path)

    assert n_after_first == n_after_second, "second run added duplicate grades"
    # The second run should have zero graded_today (all already graded).
    assert s2["n_graded_today"] == 0
    assert s2["n_already_graded"] == n_after_first


def test_run_idempotent_multiple_claims(prices, tmp_path):
    """Idempotency holds when multiple distinct claims are registered."""
    for i, asof in enumerate(["2026-02-02", "2026-02-09", "2026-02-16"]):
        _register_claim(tmp_path, asof=asof, salt=i)

    today = date(2026, 6, 1)
    grader.run(root=tmp_path, today=today)
    n1 = _grade_count(tmp_path)

    grader.run(root=tmp_path, today=today)
    n2 = _grade_count(tmp_path)

    assert n1 == n2


# --------------------------------------------------------------------------- #
# horizon capping
# --------------------------------------------------------------------------- #
def test_horizon_capping_21d_claim(prices, tmp_path):
    """A horizon_d=21 claim must grade at 5d and 21d only — not at 63d."""
    _register_claim(tmp_path, horizon_d=21)
    summary = grader.run(root=tmp_path, today=date(2026, 6, 1))

    grades = q.load_grades(tmp_path)
    horizons = sorted({int(g["horizon_d"]) for g in grades})
    assert horizons == [5, 21], f"expected [5,21], got {horizons}"


def test_horizon_capping_5d_claim(prices, tmp_path):
    """A horizon_d=5 claim grades at 5d only."""
    _register_claim(tmp_path, horizon_d=5)
    grader.run(root=tmp_path, today=date(2026, 6, 1))

    grades = q.load_grades(tmp_path)
    horizons = sorted({int(g["horizon_d"]) for g in grades})
    assert horizons == [5]


def test_horizon_capping_63d_claim_gets_all_three(prices, tmp_path):
    """A horizon_d=63 claim grades at 5d, 21d, and 63d."""
    _register_claim(tmp_path, horizon_d=63)
    grader.run(root=tmp_path, today=date(2026, 6, 1))

    grades = q.load_grades(tmp_path)
    horizons = sorted({int(g["horizon_d"]) for g in grades})
    assert horizons == [5, 21, 63]


def test_horizon_capping_short_horizon(prices, tmp_path):
    """A horizon_d=3 claim (below all GRADE_HORIZONS) grades once, at its own clock."""
    _register_claim(tmp_path, horizon_d=3)
    grader.run(root=tmp_path, today=date(2026, 6, 1))

    grades = q.load_grades(tmp_path)
    horizons = sorted({int(g["horizon_d"]) for g in grades})
    assert horizons == [3]


# --------------------------------------------------------------------------- #
# coverage miss handling
# --------------------------------------------------------------------------- #
def test_coverage_miss_counted_not_silently_dropped(no_prices, tmp_path):
    """When prices are unavailable, matured horizons are counted in
    n_blocked_by_coverage, not silently dropped."""
    _register_claim(tmp_path)
    summary = grader.run(root=tmp_path, today=date(2026, 6, 1))

    assert summary["n_graded_today"] == 0
    # All three horizons (5/21/63) should be blocked, not silently missing.
    assert summary["n_blocked_by_coverage"] > 0
    # run_status.json should also reflect this.
    status_p = tmp_path.joinpath(*grader._STATUS_FILE)
    assert status_p.exists()
    status = json.loads(status_p.read_text())
    assert status["n_blocked_by_coverage"] > 0


def test_coverage_miss_does_not_write_grade_row(no_prices, tmp_path):
    """No grade rows written when prices are unavailable."""
    _register_claim(tmp_path)
    grader.run(root=tmp_path, today=date(2026, 6, 1))
    assert _grade_count(tmp_path) == 0


# --------------------------------------------------------------------------- #
# ungradeable claims (EVENT_DATE / SNAPSHOT_DATE)
# --------------------------------------------------------------------------- #
def test_ungradeable_event_date_counted(prices, tmp_path):
    """Claims with EVENT_DATE timestamp_quality are counted in n_ungradeable."""
    c = q.make_claim(desk="intel", asof="2026-02-02", scope_type="entity",
                     scope_key="CARR", direction=1, horizon_d=21,
                     timestamp_quality="EVENT_DATE")
    q.register(c, root=tmp_path)

    summary = grader.run(root=tmp_path, today=date(2026, 6, 1))
    assert summary["n_ungradeable"] == 1
    assert summary["n_graded_today"] == 0


def test_ungradeable_snapshot_date_counted(prices, tmp_path):
    """Claims with SNAPSHOT_DATE timestamp_quality are counted in n_ungradeable."""
    c = q.make_claim(desk="intel", asof="2026-02-02", scope_type="entity",
                     scope_key="CARR", direction=1, horizon_d=21,
                     timestamp_quality="SNAPSHOT_DATE")
    q.register(c, root=tmp_path)

    summary = grader.run(root=tmp_path, today=date(2026, 6, 1))
    assert summary["n_ungradeable"] == 1
    assert summary["n_graded_today"] == 0


# --------------------------------------------------------------------------- #
# run_status.json health file
# --------------------------------------------------------------------------- #
def test_run_status_written(prices, tmp_path):
    """run_status.json is always written on a real run (broken != quiet)."""
    _register_claim(tmp_path)
    grader.run(root=tmp_path, today=date(2026, 6, 1))

    status_p = tmp_path.joinpath(*grader._STATUS_FILE)
    assert status_p.exists()
    status = json.loads(status_p.read_text())
    for key in ("n_open", "n_graded_today", "n_blocked_by_coverage",
                "n_ungradeable", "n_already_graded", "generated_at"):
        assert key in status, f"missing key {key!r}"


def test_run_status_not_written_in_dry_run(prices, tmp_path):
    """--dry-run must not write any files."""
    _register_claim(tmp_path)
    grader.run(root=tmp_path, today=date(2026, 6, 1), dry_run=True)

    status_p = tmp_path.joinpath(*grader._STATUS_FILE)
    assert not status_p.exists()
    assert _grade_count(tmp_path) == 0


# --------------------------------------------------------------------------- #
# track_record emit
# --------------------------------------------------------------------------- #
def test_track_record_emitted_after_grading(prices, tmp_path):
    """emit_track_record is called so site/qledger/track_record.json is updated."""
    _register_claim(tmp_path)
    grader.run(root=tmp_path, today=date(2026, 6, 1))

    tr_p = tmp_path.joinpath(*q._TRACK_FILE)
    assert tr_p.exists()
    tr = json.loads(tr_p.read_text())
    assert tr["counts"]["n_claims"] == 1
    assert tr["counts"]["n_grades"] > 0


# --------------------------------------------------------------------------- #
# rejected claims are skipped
# --------------------------------------------------------------------------- #
def test_rejected_claims_not_graded(prices, tmp_path):
    """register() can produce rejected claims (e.g. macro without named bench).
    The grader must skip them."""
    bad = q.make_claim(desk="policy", asof="2026-02-02", scope_type="macro",
                       scope_key="vibes", direction=1, horizon_d=21,
                       timestamp_quality="DISCLOSURE_DATE")  # no named bench → rejected
    q.register(bad, root=tmp_path)

    summary = grader.run(root=tmp_path, today=date(2026, 6, 1))
    assert summary["n_open"] == 0           # rejected claim is NOT open
    assert summary["n_graded_today"] == 0
    assert _grade_count(tmp_path) == 0


# --------------------------------------------------------------------------- #
# summary fields sanity
# --------------------------------------------------------------------------- #
def test_summary_fields_complete(prices, tmp_path):
    _register_claim(tmp_path)
    summary = grader.run(root=tmp_path, today=date(2026, 6, 1))
    for key in ("n_open", "n_graded_today", "n_blocked_by_coverage",
                "n_ungradeable", "n_already_graded", "generated_at",
                "as_of", "dry_run"):
        assert key in summary, f"summary missing {key!r}"


def test_empty_store_is_safe(prices, tmp_path):
    """Running on an empty claims store must not raise."""
    summary = grader.run(root=tmp_path, today=date(2026, 6, 1))
    assert summary["n_open"] == 0
    assert summary["n_graded_today"] == 0
