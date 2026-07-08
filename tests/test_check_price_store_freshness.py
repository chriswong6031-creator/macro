"""Tests for scripts/check_price_store_freshness.py — the engine-lane freshness gate.

Pins the decision logic and the heal flow with the store readers monkeypatched (the
real readers live in scripts/refresh_regime_if_stale and are pinned by its own tests).
The reference time is the 2026-07-07 incident engine run (06:01 UTC) whose expected
session is Mon 2026-07-06.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

import scripts.check_price_store_freshness as gate
import scripts.refresh_regime_if_stale as rr
from lib import config

INCIDENT_NOW = datetime(2026, 7, 7, 6, 1, tzinfo=timezone.utc)


@pytest.fixture
def tmp_data(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    return tmp_path


def _marker(tmp_path) -> dict:
    return json.loads((tmp_path / "quality" / "price_store_freshness.json").read_text())


def test_fresh_store_exits_zero(monkeypatch, tmp_data):
    monkeypatch.setattr(rr, "_store_close_date", lambda: "2026-07-06")
    monkeypatch.setattr(rr, "_repull_yahoo",
                        lambda: (_ for _ in ()).throw(AssertionError("must not re-pull")))
    assert gate.run(heal=True, now=INCIDENT_NOW) == 0
    m = _marker(tmp_data)
    assert m["status"] == "fresh" and m["healed"] is False
    assert m["expected_session"] == "2026-07-06"


def test_stale_store_heals_and_exits_zero(monkeypatch, tmp_data):
    """The incident case with the guard in place: frozen 07-02 store, keyless re-pull
    lands the 07-06 bar -> gate passes and records the heal."""
    monkeypatch.setattr(rr, "_store_close_date", lambda: "2026-07-02")
    monkeypatch.setattr(rr, "_repull_yahoo", lambda: "2026-07-06")
    assert gate.run(heal=True, now=INCIDENT_NOW) == 0
    m = _marker(tmp_data)
    assert m["status"] == "fresh" and m["healed"] is True
    assert m["store_before"] == "2026-07-02" and m["store_after"] == "2026-07-06"


def test_stale_store_unhealed_exits_three(monkeypatch, tmp_data, capsys):
    """Feed still hasn't published (re-pull returns the same stale date) -> red gate."""
    monkeypatch.setattr(rr, "_store_close_date", lambda: "2026-07-02")
    monkeypatch.setattr(rr, "_repull_yahoo", lambda: "2026-07-02")
    assert gate.run(heal=True, now=INCIDENT_NOW) == 3
    assert _marker(tmp_data)["status"] == "stale"
    assert "::error title=price store STALE::" in capsys.readouterr().out


def test_stale_without_heal_exits_three(monkeypatch, tmp_data):
    """Check-only mode (engine-render lane, network-free) never re-pulls."""
    monkeypatch.setattr(rr, "_store_close_date", lambda: "2026-07-02")
    monkeypatch.setattr(rr, "_repull_yahoo",
                        lambda: (_ for _ in ()).throw(AssertionError("must not re-pull")))
    assert gate.run(heal=False, now=INCIDENT_NOW) == 3
    m = _marker(tmp_data)
    assert m["status"] == "stale" and m["heal_attempted"] is False


def test_repull_crash_degrades_to_stale(monkeypatch, tmp_data):
    monkeypatch.setattr(rr, "_store_close_date", lambda: "2026-07-02")
    monkeypatch.setattr(rr, "_repull_yahoo",
                        lambda: (_ for _ in ()).throw(RuntimeError("yahoo down")))
    assert gate.run(heal=True, now=INCIDENT_NOW) == 3


def test_missing_store_treated_as_stale(monkeypatch, tmp_data):
    monkeypatch.setattr(rr, "_store_close_date", lambda: None)
    monkeypatch.setattr(rr, "_repull_yahoo", lambda: "2026-07-06")
    assert gate.run(heal=True, now=INCIDENT_NOW) == 0
    assert _marker(tmp_data)["store_before"] is None


def test_selftest_passes():
    assert gate.selftest() == 0


def test_calendar_reference_in_market_reference_date(monkeypatch, tmp_data):
    """refresh_regime_if_stale's market reference now includes the NYSE calendar leg:
    with the massive manifest frozen at 07-02 (the incident blind spot — it died in the
    same push), the reference must still say 07-06."""
    from lib import nyse_calendar
    (tmp_data / "massive_stock_day").mkdir(parents=True)
    (tmp_data / "massive_stock_day" / "_manifest.json").write_text(
        json.dumps({"latest_date": "2026-07-02"}))
    monkeypatch.setattr(nyse_calendar, "expected_last_session",
                        lambda now=None: __import__("datetime").date(2026, 7, 6))
    assert rr._market_reference_date() == "2026-07-06"
