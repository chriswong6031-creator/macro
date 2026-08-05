"""Tests for scripts/heal_us_ignition_log.py — the session-inference + weekend-dupe
quarantine heal (census PR #4564 charter §4).

Pins the executable spec of the inference rule:

  run at/after 16:00 PT -> session = last trading day <= the run's PT date
  run before 16:00 PT   -> session = last trading day <  the run's PT date
                           (a drifted past-midnight nightly still holds the
                           previous session's tape)

and the first-writer-wins quarantine: a later row re-logging an already-recorded
session moves to us_ignition_quarantine.jsonl with a reason; nothing is deleted.

All dates are PINNED (no wall clock) — the rule is calendar arithmetic and must
grade the same on any run day.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.heal_us_ignition_log import heal, infer_session


# ── inference rule ────────────────────────────────────────────────────────────

def test_infer_session_friday_evening_run():
    # 2026-07-18T01:14Z = Fri 2026-07-17 18:14 PT → that Friday's session
    assert infer_session("2026-07-18T01:14:04+00:00") == "2026-07-17"


def test_infer_session_saturday_evening_run_is_friday():
    # 2026-07-19T01:00Z = Sat 2026-07-18 18:00 PT → weekend, last session = Friday
    assert infer_session("2026-07-19T01:00:56+00:00") == "2026-07-17"


def test_infer_session_drifted_past_midnight_run_is_prior_session():
    # 2026-07-14T07:54Z = Tue 2026-07-14 00:54 PT — the Monday-evening nightly
    # drifted past midnight; its stores still hold Monday's tape.
    assert infer_session("2026-07-14T07:54:54+00:00") == "2026-07-13"


def test_infer_session_drifted_monday_run_is_friday():
    # 2026-07-13T08:09Z = Mon 2026-07-13 01:09 PT — the Sunday-night weekend
    # re-run drifted past midnight; tape is still Friday's.
    assert infer_session("2026-07-13T08:09:28+00:00") == "2026-07-10"


def test_infer_session_steps_over_holiday():
    # Evening run on Labor Day (Mon 2026-09-07, NYSE closed) → Friday 09-04.
    assert infer_session("2026-09-08T01:00:00+00:00") == "2026-09-04"


# ── heal: quarantine + stamping ───────────────────────────────────────────────

def _row(asof, logged_at, session=None, **extra):
    r = {"asof": asof, "market": "us", "broad_state": "warming", "k_count": 1,
         "top_narrow": [{"id": "XLK", "ignition_score": 0.7, "state": "igniting"}],
         "logged_at": logged_at, "graded_broad": None, "graded_narrow": None}
    if session:
        r["session"] = session
    r.update(extra)
    return r


def _write_log(root: Path, rows):
    p = root / "data" / "ignition_log" / "us_ignition.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return p


def _fixture_rows():
    return [
        _row("2026-07-17", "2026-07-18T01:14:04+00:00"),  # Fri evening → keep (07-17)
        _row("2026-07-18", "2026-07-19T01:00:56+00:00"),  # Sat re-log → dup of 07-17
        _row("2026-07-20", "2026-07-20T08:09:28+00:00"),  # drifted Mon 01:09 PT → dup of 07-17
        _row("2026-07-20", "2026-07-21T01:07:37+00:00"),  # Mon evening → keep (07-20)
        _row("2026-07-21", "2026-07-22T01:19:55+00:00",   # already stamped → untouched
             session="2026-07-21"),
    ]


def test_heal_quarantines_dupes_first_writer_wins(tmp_path):
    _write_log(tmp_path, _fixture_rows())
    summary = heal(tmp_path)
    assert summary["n_survivors"] == 3
    assert summary["sessions"] == ["2026-07-17", "2026-07-20", "2026-07-21"]
    assert summary["quarantined_asofs"] == ["2026-07-18", "2026-07-20"]

    main = [json.loads(l) for l in
            (tmp_path / "data/ignition_log/us_ignition.jsonl").read_text().splitlines() if l]
    assert [r["session"] for r in main] == ["2026-07-17", "2026-07-20", "2026-07-21"]
    # the drifted Sat/Mon re-runs are gone from main; the Fri original survives
    assert [r["asof"] for r in main] == ["2026-07-17", "2026-07-20", "2026-07-21"]
    # inferred rows are marked; the pre-stamped row is not re-marked
    assert main[0].get("session_inferred") is True
    assert "session_inferred" not in main[2]
    # graded fields never touched
    assert all(r["graded_broad"] is None and r["graded_narrow"] is None for r in main)

    quar = [json.loads(l) for l in
            (tmp_path / "data/ignition_log/us_ignition_quarantine.jsonl").read_text().splitlines() if l]
    assert len(quar) == 2
    for q in quar:
        assert "duplicate re-log" in q["quarantine_reason"]
        assert q["quarantined_kept_row"]["asof"] in ("2026-07-17", "2026-07-20")

    meta = json.loads((tmp_path / "data/ignition_log/us_ignition_meta.json").read_text())
    assert meta["quarantine"]["n_rows"] == 2


def test_heal_is_idempotent(tmp_path):
    _write_log(tmp_path, _fixture_rows())
    heal(tmp_path)
    second = heal(tmp_path)
    assert second["n_quarantined_now"] == 0
    assert second["n_inferred"] == 0
    assert second.get("note") == "already healed — nothing to do"
    quar = (tmp_path / "data/ignition_log/us_ignition_quarantine.jsonl").read_text()
    assert len([l for l in quar.splitlines() if l]) == 2  # not re-appended


def test_heal_dry_run_writes_nothing(tmp_path):
    p = _write_log(tmp_path, _fixture_rows())
    before = p.read_text()
    summary = heal(tmp_path, dry_run=True)
    assert summary["dry_run"] is True
    assert summary["n_quarantined_now"] == 2
    assert p.read_text() == before
    assert not (tmp_path / "data/ignition_log/us_ignition_quarantine.jsonl").exists()


def test_heal_fails_closed_on_missing_logged_at(tmp_path):
    rows = _fixture_rows()
    rows[1].pop("logged_at")
    p = _write_log(tmp_path, rows)
    before = p.read_text()
    with pytest.raises(SystemExit):
        heal(tmp_path)
    assert p.read_text() == before  # aborted before any write
