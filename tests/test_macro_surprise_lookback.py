"""Tests for tiered lookback in engine/macro_surprise.py.

Covers:
  - lookback_days_for: returns correct window per cadence.
  - Monthly series print 30 days old -> card emitted (within 45d window).
  - Weekly series print 12 days old -> NO card (outside 10d window).
  - Quarterly series print 80 days old -> card emitted (within 95d window).
  - lookback_days_for respects an unknown cadence with the default.
  - build_release_cards emits lookback_by_cadence metadata.
  - Each card has a lookback_days field.

No network calls: FRED fetches are mocked.

Run:  python3 -m pytest tests/test_macro_surprise_lookback.py -x -q
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import macro_surprise as ms


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_records(n: int, cadence: str = "monthly") -> list[dict]:
    """Build a simple FRED-style records list with n observations starting 2020-01-01.
    Values are a simple arithmetic series so z-scores are non-degenerate."""
    from datetime import date
    step = timedelta(days={"monthly": 30, "weekly": 7, "quarterly": 91}[cadence])
    d = date(2020, 1, 1)
    records = []
    for i in range(n):
        records.append({"date": d.isoformat(), "value": 100.0 + i * 0.1})
        d += step
    return records


def _entry(cadence: str, key: str = "test") -> dict:
    """Minimal registry entry for testing."""
    return {
        "key": key,
        "display_name": f"Test {cadence}",
        "title_aliases": [],
        "fred_series": "FAKE",
        "transform": "level",
        "cadence": cadence,
        "macro_channel": "growth",
        "direction_map": "neutral",
    }


# ── unit tests for lookback_days_for ─────────────────────────────────────────

@pytest.mark.parametrize("cadence,expected", [
    ("weekly",    10),
    ("monthly",   45),
    ("quarterly", 95),
])
def test_lookback_days_for_cadence(cadence, expected):
    assert ms.lookback_days_for(_entry(cadence)) == expected


def test_lookback_days_for_unknown_cadence():
    """Unknown cadence should return the default (45), not raise."""
    e = _entry("monthly")
    e["cadence"] = "hourly"  # not in the table
    result = ms.lookback_days_for(e)
    assert isinstance(result, int) and result > 0


# ── within_lookback integration ───────────────────────────────────────────────

def test_monthly_print_30_days_old_yields_card():
    """A monthly series print dated 30 days ago must be within the 45d window."""
    asof = datetime(2026, 7, 10, 12, 0, 0, tzinfo=timezone.utc)
    # latest_date = 30 days before asof
    latest = (asof.date() - timedelta(days=30)).isoformat()
    entry = _entry("monthly")
    window = ms.lookback_days_for(entry)
    assert window == 45
    assert ms._within_lookback(latest, asof, window), (
        f"monthly print 30 days old should be within {window}d window"
    )


def test_weekly_print_12_days_old_not_in_window():
    """A weekly series print dated 12 days ago must be OUTSIDE the 10d window."""
    asof = datetime(2026, 7, 10, 12, 0, 0, tzinfo=timezone.utc)
    latest = (asof.date() - timedelta(days=12)).isoformat()
    entry = _entry("weekly")
    window = ms.lookback_days_for(entry)
    assert window == 10
    assert not ms._within_lookback(latest, asof, window), (
        f"weekly print 12 days old should be OUTSIDE {window}d window"
    )


def test_quarterly_print_80_days_old_yields_card():
    """A quarterly series print dated 80 days ago must be within the 95d window."""
    asof = datetime(2026, 7, 10, 12, 0, 0, tzinfo=timezone.utc)
    latest = (asof.date() - timedelta(days=80)).isoformat()
    entry = _entry("quarterly")
    window = ms.lookback_days_for(entry)
    assert window == 95
    assert ms._within_lookback(latest, asof, window), (
        f"quarterly print 80 days old should be within {window}d window"
    )


# ── build_release_cards integration ──────────────────────────────────────────

def _make_enough_records(n: int = 40, cadence: str = "monthly") -> list[dict]:
    """Build records so the kill-criterion (< 6 series) does not trigger when used
    in a single-series patch — we patch ALL registry entries to return data."""
    return _make_records(n, cadence)


def _patch_fred(monkeypatch, records_by_key: dict[str, list[dict]]) -> None:
    """Patch _fetch_fred_series to return pre-built records keyed by series_id."""
    series_id_to_records = {}
    for entry in ms.RELEASE_REGISTRY:
        key = entry["key"]
        series_id_to_records[entry["fred_series"]] = records_by_key.get(
            key, _make_records(40, entry.get("cadence", "monthly"))
        )

    def _fake_fetch(series_id: str):
        return series_id_to_records.get(series_id)

    monkeypatch.setattr(ms, "_fetch_fred_series", _fake_fetch)


def test_build_release_cards_emits_lookback_metadata(monkeypatch):
    """build_release_cards must include lookback_by_cadence in the result."""
    _patch_fred(monkeypatch, {})
    asof = datetime(2026, 7, 10, 12, 0, 0, tzinfo=timezone.utc)
    result = ms.build_release_cards(asof=asof)
    assert "lookback_by_cadence" in result, "must include lookback_by_cadence metadata"
    lbc = result["lookback_by_cadence"]
    assert lbc["monthly"] == 45
    assert lbc["weekly"] == 10
    assert lbc["quarterly"] == 95


def test_cards_have_lookback_days_field(monkeypatch):
    """Each emitted card must have a lookback_days field."""
    _patch_fred(monkeypatch, {})
    asof = datetime(2026, 7, 10, 12, 0, 0, tzinfo=timezone.utc)
    result = ms.build_release_cards(asof=asof)
    for card in result.get("cards", []):
        assert "lookback_days" in card, (
            f"card {card.get('release')!r} missing lookback_days field"
        )


def test_monthly_series_visible_30_days_after_print(monkeypatch):
    """A monthly series print 30 days ago must produce a card (not filtered out)."""
    asof = datetime(2026, 7, 10, 12, 0, 0, tzinfo=timezone.utc)
    # Build records where the last observation is 30 days before asof
    from datetime import date, timedelta
    latest_date = asof.date() - timedelta(days=30)

    def _make_records_ending(target_date, n=40, step_days=30):
        records = []
        d = target_date - timedelta(days=step_days * (n - 1))
        for i in range(n):
            records.append({"date": d.isoformat(), "value": 100.0 + i * 0.1})
            d += timedelta(days=step_days)
        return records

    monthly_records = _make_records_ending(latest_date)
    weekly_records = _make_records_ending(
        asof.date() - timedelta(days=5), n=50, step_days=7
    )

    def _fake_fetch(series_id: str):
        entry = next((e for e in ms.RELEASE_REGISTRY if e["fred_series"] == series_id), None)
        if entry is None:
            return None
        if entry["cadence"] == "weekly":
            return weekly_records
        return monthly_records

    monkeypatch.setattr(ms, "_fetch_fred_series", _fake_fetch)
    result = ms.build_release_cards(asof=asof)

    # At least one monthly card should appear (the print is 30 days ago, within 45d)
    monthly_cards = [
        c for c in result.get("cards", [])
        if ms.lookback_days_for(next(
            (e for e in ms.RELEASE_REGISTRY if e["key"] == c["release"]), {}
        )) == 45
    ]
    assert len(monthly_cards) > 0, (
        "Expected at least one monthly card for a print 30 days ago; "
        f"got {result.get('n_cards', 0)} cards total"
    )


def test_weekly_series_absent_when_12_days_old(monkeypatch):
    """A weekly series print 12 days ago must NOT produce a card (outside 10d window)."""
    asof = datetime(2026, 7, 10, 12, 0, 0, tzinfo=timezone.utc)
    from datetime import date, timedelta

    def _make_records_ending(target_date, n=50, step_days=7):
        records = []
        d = target_date - timedelta(days=step_days * (n - 1))
        for i in range(n):
            records.append({"date": d.isoformat(), "value": 300_000.0 + i * 1000})
            d += timedelta(days=step_days)
        return records

    # Weekly series (ICSA) print is 12 days ago
    weekly_records = _make_records_ending(asof.date() - timedelta(days=12))
    # Monthly series print is 5 days ago (within window)
    monthly_records = _make_records_ending(
        asof.date() - timedelta(days=5), step_days=30, n=40
    )

    def _fake_fetch(series_id: str):
        entry = next((e for e in ms.RELEASE_REGISTRY if e["fred_series"] == series_id), None)
        if entry is None:
            return None
        if entry["cadence"] == "weekly":
            return weekly_records
        return monthly_records

    monkeypatch.setattr(ms, "_fetch_fred_series", _fake_fetch)
    result = ms.build_release_cards(asof=asof)

    weekly_cards = [
        c for c in result.get("cards", [])
        if next(
            (e for e in ms.RELEASE_REGISTRY if e["key"] == c["release"]),
            {}
        ).get("cadence") == "weekly"
    ]
    assert len(weekly_cards) == 0, (
        f"Weekly print 12 days old should not yield a card; got {weekly_cards}"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-x", "-q"])
