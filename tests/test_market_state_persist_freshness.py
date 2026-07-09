"""Tests for engine.market_state.persist's freshness contract (2026-07-07 incident):
the no-regress guard (a stale lane must not clobber a fresher canonical snapshot) and
the self-declaring freshness stamp (calendar-stale data is marked, not hidden).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from engine import market_state as ms

# Tuesday 2026-07-07 06:01 UTC — expected last completed NYSE session = Mon 2026-07-06.
INCIDENT_NOW = datetime(2026, 7, 7, 6, 1, tzinfo=timezone.utc)


def _read(root):
    return json.loads((root / "data" / "market_state" / "latest.json").read_text())


def test_persist_stamps_stale_when_behind_calendar(tmp_path):
    """The incident snapshot (asof 07-02 on a morning that expects 07-06) persists —
    the dashboard must still build from cached data — but is stamped stale."""
    ms.persist({"asof": "2026-07-02", "verdict": "RISK_OFF"}, root=tmp_path, now=INCIDENT_NOW)
    got = _read(tmp_path)
    assert got["freshness"] == {
        "data_asof": "2026-07-02", "expected_asof": "2026-07-06", "stale": True}


def test_persist_stamps_fresh_when_current(tmp_path):
    ms.persist({"asof": "2026-07-06", "verdict": "MIXED"}, root=tmp_path, now=INCIDENT_NOW)
    got = _read(tmp_path)
    assert got["freshness"]["stale"] is False
    assert got["freshness"]["expected_asof"] == "2026-07-06"


def test_no_regress_refuses_older_snapshot(tmp_path):
    """The incident race: the fresh re-dispatch persisted 07-06, then a delayed stale
    lane tries to persist 07-02 — it must be refused."""
    ms.persist({"asof": "2026-07-06", "verdict": "MIXED", "score": 56},
               root=tmp_path, now=INCIDENT_NOW)
    ms.persist({"asof": "2026-07-02", "verdict": "RISK_OFF", "score": 40},
               root=tmp_path, now=INCIDENT_NOW)
    got = _read(tmp_path)
    assert got["asof"] == "2026-07-06" and got["verdict"] == "MIXED"


def test_equal_asof_overwrites(tmp_path):
    """Same-session recomputes (render lanes, intraday self-heal) must keep flowing."""
    ms.persist({"asof": "2026-07-06", "verdict": "MIXED"}, root=tmp_path, now=INCIDENT_NOW)
    ms.persist({"asof": "2026-07-06", "verdict": "RISK_ON"}, root=tmp_path, now=INCIDENT_NOW)
    assert _read(tmp_path)["verdict"] == "RISK_ON"


def test_missing_asof_never_blocks(tmp_path):
    """Snapshots without asof (degraded builds) persist as before — the guard only
    engages when both sides carry a comparable date."""
    ms.persist({"asof": "2026-07-06", "verdict": "MIXED"}, root=tmp_path, now=INCIDENT_NOW)
    ms.persist({"verdict": "NO_ASOF"}, root=tmp_path, now=INCIDENT_NOW)
    assert _read(tmp_path)["verdict"] == "NO_ASOF"


def test_corrupt_existing_never_blocks(tmp_path):
    p = tmp_path / "data" / "market_state" / "latest.json"
    p.parent.mkdir(parents=True)
    p.write_text("{not json")
    ms.persist({"asof": "2026-07-06", "verdict": "MIXED"}, root=tmp_path, now=INCIDENT_NOW)
    assert _read(tmp_path)["verdict"] == "MIXED"
