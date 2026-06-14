"""Dead-man's switch logic (Phase B ops hardening). Fresh + few-breakers = OK;
stale last_run or a broad outage = fail. Pure function, deterministic `now`."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from scripts.healthcheck import check_health

NOW = datetime(2026, 6, 13, 12, 0, tzinfo=timezone.utc)


def _status(hours_ago: float, breakers: dict | None = None) -> dict:
    return {"last_run": (NOW - timedelta(hours=hours_ago)).isoformat(),
            "circuit_breaker": breakers or {}}


def test_fresh_run_is_healthy():
    r = check_health(_status(20, {"cot": 1, "aaii": 3}), NOW)
    assert r["ok"] is True and not r["fail_reasons"]
    assert r["tripped"] == ["aaii"]                       # reported as a warning, not a failure
    assert r["warnings"]


def test_stale_run_fails():
    r = check_health(_status(120), NOW, max_age_hours=96)
    assert r["ok"] is False
    assert any("STALE" in f for f in r["fail_reasons"])


def test_weekend_gap_within_limit_is_ok():
    r = check_health(_status(72), NOW, max_age_hours=96)   # Fri->Mon gap
    assert r["ok"] is True


def test_broad_outage_fails():
    breakers = {f"src{i}": 5 for i in range(9)}            # 9 sources down
    r = check_health(_status(10, breakers), NOW, broad_outage=8)
    assert r["ok"] is False
    assert any("BROAD OUTAGE" in f for f in r["fail_reasons"])


def test_missing_last_run_fails():
    r = check_health({"circuit_breaker": {}}, NOW)
    assert r["ok"] is False
    assert any("last_run" in f for f in r["fail_reasons"])
