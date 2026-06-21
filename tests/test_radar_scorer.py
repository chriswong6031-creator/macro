"""Radar / Narrative-Brain ledger scorer tests (hermetic — no price store needed)."""
from __future__ import annotations

import json
from datetime import date

from engine import radar_scorer as rs


def _write(d, rows):
    d.mkdir(parents=True, exist_ok=True)
    (d / "theses.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def test_state_asof_derivation():
    assert rs._state_asof({"logged_at": "2026-06-19T12:00:00+00:00"}) == "2026-06-19"
    assert rs._state_asof({"id": "2026-06-19-radar-defense"}) == "2026-06-19"
    assert rs._state_asof({"state_asof": "2026-01-01", "logged_at": "x"}) == "2026-01-01"
    assert rs._state_asof({"id": "nb-defense"}) is None


def test_soft_thesis_unscored_and_idempotent(tmp_path):
    _write(tmp_path / "data" / "radar", [{
        "id": "2026-06-19-radar-defense", "subject": "defense", "lean": "positive_divergence",
        "conviction": "medium", "logged_at": "2026-06-19T00:00:00+00:00", "check_by": "2026-09-18",
        "falsifier": {"check": {"kind": "soft", "reason": "no ETF proxy"}}}])
    tr = rs.run(root=tmp_path, today=date(2026, 12, 1))["radar"]
    assert tr["unscored_soft"] == 1 and tr["scored_total"] == 0
    # idempotent — a second run doesn't re-score the same id
    tr2 = rs.run(root=tmp_path, today=date(2026, 12, 1))["radar"]
    assert tr2["unscored_soft"] == 1
    assert (tmp_path / "data" / "radar" / "scored.jsonl").exists()
    assert (tmp_path / "site" / "basketdata" / "radar_track_record.json").exists()


def test_future_thesis_stays_open(tmp_path):
    _write(tmp_path / "data" / "narrative_brain", [{
        "id": "2026-06-19-nb-defense", "subject": "defense", "lean": "constructive", "conviction": "high",
        "logged_at": "2026-06-19T00:00:00+00:00", "check_by": "2027-06-19",
        "falsifier": {"check": {"kind": "rel_return", "subject_ticker": "ITA", "vs": "SPY",
                                "op": "<", "threshold": -0.05, "horizon_d": 21}}}])
    tr = rs.run(root=tmp_path, today=date(2026, 6, 20))["narrative_brain"]   # before check_by, no price -> not ready
    assert tr["scored_total"] == 0 and tr["open"] == 1


def test_no_ledgers_returns_none(tmp_path):
    assert rs.run(root=tmp_path, today=date(2026, 6, 20)) is None


def test_both_desks_graded(tmp_path):
    _write(tmp_path / "data" / "radar", [{"id": "2026-06-19-radar-x", "logged_at": "2026-06-19T00:00:00+00:00",
           "check_by": "2026-09-18", "falsifier": {"check": {"kind": "soft"}}}])
    _write(tmp_path / "data" / "narrative_brain", [{"id": "2026-06-19-nb-y", "logged_at": "2026-06-19T00:00:00+00:00",
           "check_by": "2026-09-18", "falsifier": {"check": {"kind": "soft"}}}])
    out = rs.run(root=tmp_path, today=date(2026, 12, 1))
    assert set(out) == {"radar", "narrative_brain"}
