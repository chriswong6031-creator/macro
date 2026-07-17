"""Tests for widened lookback windows and last-good fallback in engine/macro_surprise.py.

Covers:
  W1-PARTIAL fix:
    - monthly boundary: obs exactly 45d old → card DROPS under old window,
      PASSES under new 80d window.
    - monthly boundary: obs exactly 46d old → also passes new 80d window.
    - monthly boundary: obs exactly 80d old → PASSES (boundary inclusive).
    - monthly boundary: obs exactly 81d old → DROPS (just outside new window).
    - weekly boundary: obs exactly 12d old → PASSES (new 14d window).
    - weekly boundary: obs exactly 14d old → PASSES (boundary inclusive).
    - weekly boundary: obs exactly 15d old → DROPS.
    - quarterly boundary: obs exactly 95d old → PASSES (new 210d window).
    - quarterly boundary: obs exactly 210d old → PASSES (boundary inclusive).
    - quarterly boundary: obs exactly 211d old → DROPS.

  Last-good fallback (fix 3):
    - when freshly-fetched latest_date is OLDER than prior artifact latest_date,
      the prior card is kept (last_good_fallback=True).
    - when freshly-fetched latest_date is NEWER or equal to prior, fresh card wins.
    - prior card outside its lookback window is NOT rescued.
    - kill-criterion: prior cards within window are rescued under kill-criterion.

No network calls: FRED fetches are mocked.  No real data/ or site/ writes
(MM_DATA_GUARD conftest enforces this; fixtures use tmp_path).

Run:  python3 -m pytest tests/test_macro_surprise_windows.py -x -q
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import macro_surprise as ms


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_records_ending(target_date, n: int = 40, step_days: int = 30) -> list[dict]:
    """Build FRED-style records whose LAST observation is exactly target_date."""
    from datetime import date as _date
    records = []
    d = target_date - timedelta(days=step_days * (n - 1))
    for i in range(n):
        records.append({"date": d.isoformat(), "value": 100.0 + i * 0.1})
        d += timedelta(days=step_days)
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


def _patch_all_fred(monkeypatch, records_fn):
    """Patch _fetch_fred_series to call records_fn(entry) for each registry entry."""
    def _fake(series_id: str):
        entry = next((e for e in ms.RELEASE_REGISTRY if e["fred_series"] == series_id), None)
        if entry is None:
            return None
        return records_fn(entry)
    monkeypatch.setattr(ms, "_fetch_fred_series", _fake)


# ── W1-PARTIAL: window boundary tests ────────────────────────────────────────

class TestNewWindows:
    """Verify _LOOKBACK_BY_CADENCE was widened to 14/80/210."""

    def test_weekly_window_is_14(self):
        assert ms._LOOKBACK_BY_CADENCE["weekly"] == 14

    def test_monthly_window_is_80(self):
        assert ms._LOOKBACK_BY_CADENCE["monthly"] == 80

    def test_quarterly_window_is_210(self):
        assert ms._LOOKBACK_BY_CADENCE["quarterly"] == 210

    def test_lookback_days_for_weekly(self):
        assert ms.lookback_days_for(_entry("weekly")) == 14

    def test_lookback_days_for_monthly(self):
        assert ms.lookback_days_for(_entry("monthly")) == 80

    def test_lookback_days_for_quarterly(self):
        assert ms.lookback_days_for(_entry("quarterly")) == 210


class TestMonthlyBoundary:
    """Monthly series: old=45 was the window; new=80."""

    ASOF = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)

    def test_45d_old_passes_new_window(self):
        # Previously at the boundary (exactly 45d), would have been the last day
        # inside the OLD window; new window is 80 so it still passes.
        d = (self.ASOF.date() - timedelta(days=45)).isoformat()
        assert ms._within_lookback(d, self.ASOF, 80), "45d old monthly must be within new 80d window"

    def test_46d_old_passes_new_window(self):
        # Was OUTSIDE old 45d window, must be inside new 80d window.
        d = (self.ASOF.date() - timedelta(days=46)).isoformat()
        assert ms._within_lookback(d, self.ASOF, 80), "46d old monthly must be within new 80d window"

    def test_80d_old_at_boundary(self):
        d = (self.ASOF.date() - timedelta(days=80)).isoformat()
        assert ms._within_lookback(d, self.ASOF, 80), "80d old monthly must be AT boundary (inclusive)"

    def test_81d_old_drops(self):
        d = (self.ASOF.date() - timedelta(days=81)).isoformat()
        assert not ms._within_lookback(d, self.ASOF, 80), "81d old monthly must be OUTSIDE new 80d window"

    def test_76d_old_passes(self):
        """CPI/PPI/PCE/retail: ~76d old per 2026-07-16 measurement — must pass."""
        d = (self.ASOF.date() - timedelta(days=76)).isoformat()
        assert ms._within_lookback(d, self.ASOF, 80)


class TestWeeklyBoundary:
    """Weekly series: old=10 was the window; new=14."""

    ASOF = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)

    def test_12d_old_passes_new_window(self):
        # Was OUTSIDE old 10d window (and border case dropping NFP/unemployment).
        d = (self.ASOF.date() - timedelta(days=12)).isoformat()
        assert ms._within_lookback(d, self.ASOF, 14), "12d old weekly must pass new 14d window"

    def test_14d_old_at_boundary(self):
        d = (self.ASOF.date() - timedelta(days=14)).isoformat()
        assert ms._within_lookback(d, self.ASOF, 14), "14d old weekly at boundary must pass"

    def test_15d_old_drops(self):
        d = (self.ASOF.date() - timedelta(days=15)).isoformat()
        assert not ms._within_lookback(d, self.ASOF, 14), "15d old weekly must drop"


class TestQuarterlyBoundary:
    """Quarterly series: old=95 was the window; new=210."""

    ASOF = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)

    def test_95d_old_passes_new_window(self):
        # Was at boundary of OLD window; must pass new 210d window.
        d = (self.ASOF.date() - timedelta(days=95)).isoformat()
        assert ms._within_lookback(d, self.ASOF, 210)

    def test_196d_old_passes(self):
        """GDP: ~196d old per 2026-07-16 measurement — must pass."""
        d = (self.ASOF.date() - timedelta(days=196)).isoformat()
        assert ms._within_lookback(d, self.ASOF, 210)

    def test_210d_old_at_boundary(self):
        d = (self.ASOF.date() - timedelta(days=210)).isoformat()
        assert ms._within_lookback(d, self.ASOF, 210)

    def test_211d_old_drops(self):
        d = (self.ASOF.date() - timedelta(days=211)).isoformat()
        assert not ms._within_lookback(d, self.ASOF, 210)


class TestBuildReleaseCardsWidenedWindows:
    """Integration: build_release_cards emits monthly cards that were dropped at 45d."""

    def test_monthly_card_visible_at_76d_old(self, monkeypatch):
        """Monthly series 76d old must produce a card under the new 80d window."""
        asof = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)
        target = asof.date() - timedelta(days=76)

        def _records(entry):
            step = {"weekly": 7, "quarterly": 91}.get(entry.get("cadence", "monthly"), 30)
            if entry.get("cadence") == "weekly":
                # Give weekly series a fresh print so they pass
                return _make_records_ending(asof.date() - timedelta(days=5), step_days=7, n=50)
            if entry.get("cadence") == "quarterly":
                return _make_records_ending(asof.date() - timedelta(days=100), step_days=91, n=20)
            return _make_records_ending(target, step_days=30, n=40)

        _patch_all_fred(monkeypatch, _records)
        result = ms.build_release_cards(asof=asof)
        monthly_cards = [
            c for c in result.get("cards", [])
            if ms.lookback_days_for(
                next((e for e in ms.RELEASE_REGISTRY if e["key"] == c["release"]), {})
            ) == 80
        ]
        assert len(monthly_cards) > 0, (
            f"Expected monthly cards for 76d old series; got {result.get('n_cards', 0)} total. "
            f"kill_criterion={result.get('kill_criterion_triggered')} "
            f"skipped={result.get('skipped')}"
        )

    def test_lookback_by_cadence_metadata_reflects_new_windows(self, monkeypatch):
        asof = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)

        def _records(entry):
            return _make_records_ending(asof.date() - timedelta(days=5), step_days=30, n=40)

        _patch_all_fred(monkeypatch, _records)
        result = ms.build_release_cards(asof=asof)
        lbc = result.get("lookback_by_cadence", {})
        assert lbc.get("monthly") == 80
        assert lbc.get("weekly") == 14
        assert lbc.get("quarterly") == 210


# ── Last-good fallback tests ──────────────────────────────────────────────────

def _make_prior_artifact(tmp_path: Path, cards: list[dict]) -> Path:
    """Write a synthetic prior macro_releases.json to tmp_path, return its path."""
    p = tmp_path / "macro_releases.json"
    p.write_text(json.dumps({
        "schema": "macro_releases.v1",
        "is_context_only": True,
        "asof": "2026-07-15T18:00:00+00:00",
        "cards": cards,
        "n_cards": len(cards),
    }))
    return p


class TestLastGoodFallback:
    """When a fresh FRED fetch returns a stale date, keep the prior card."""

    ASOF = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)

    def _first_monthly_key(self):
        """Return the key of the first monthly registry entry."""
        for e in ms.RELEASE_REGISTRY:
            if e.get("cadence") == "monthly":
                return e["key"]
        pytest.skip("no monthly registry entry found")

    def test_stale_fresh_fetch_keeps_prior_card(self, monkeypatch, tmp_path):
        """If fresh fetch returns older date than prior artifact, prior card is kept."""
        key = self._first_monthly_key()
        # Prior artifact: card with latest_date 30d ago (within 80d window)
        prior_date = (self.ASOF.date() - timedelta(days=30)).isoformat()
        prior_cards = [{
            "release": key,
            "latest_date": prior_date,
            "value": 3.0,
            "surprise_size": "inline",
        }]
        prior_path = _make_prior_artifact(tmp_path, prior_cards)

        # Fresh fetch: returns records ending 60d ago (OLDER than prior 30d ago)
        stale_date = self.ASOF.date() - timedelta(days=60)

        def _records(entry):
            step = {"weekly": 7, "quarterly": 91}.get(entry.get("cadence", "monthly"), 30)
            return _make_records_ending(stale_date, step_days=step, n=40)

        _patch_all_fred(monkeypatch, _records)
        result = ms.build_release_cards(asof=self.ASOF, prior_artifact_path=prior_path)

        matched = [c for c in result.get("cards", []) if c.get("release") == key]
        assert len(matched) == 1, (
            f"Expected prior card for {key!r} to be rescued; cards={result.get('cards')}"
        )
        assert matched[0].get("last_good_fallback") is True, (
            f"Card must be marked last_good_fallback=True; got {matched[0]}"
        )
        assert matched[0]["latest_date"] == prior_date, (
            "Rescued card must carry prior latest_date, not the stale fresh date"
        )

    def test_fresh_newer_date_wins(self, monkeypatch, tmp_path):
        """If fresh fetch returns newer date than prior, fresh card is used (no fallback)."""
        key = self._first_monthly_key()
        # Prior: 60d ago
        prior_date = (self.ASOF.date() - timedelta(days=60)).isoformat()
        prior_cards = [{"release": key, "latest_date": prior_date, "value": 3.0}]
        prior_path = _make_prior_artifact(tmp_path, prior_cards)

        # Fresh: 30d ago (NEWER than prior)
        fresh_date = self.ASOF.date() - timedelta(days=30)

        def _records(entry):
            step = {"weekly": 7, "quarterly": 91}.get(entry.get("cadence", "monthly"), 30)
            return _make_records_ending(fresh_date, step_days=step, n=40)

        _patch_all_fred(monkeypatch, _records)
        result = ms.build_release_cards(asof=self.ASOF, prior_artifact_path=prior_path)

        matched = [c for c in result.get("cards", []) if c.get("release") == key]
        # Fresh card should not be marked as fallback
        for card in matched:
            assert not card.get("last_good_fallback"), (
                f"Fresh-date card must NOT be marked last_good_fallback; got {card}"
            )

    def test_missing_fetch_series_rescued_from_prior(self, monkeypatch, tmp_path):
        """Completeness rescue: a series whose fetch fails OUTRIGHT (returns None)
        never reaches the fresh-vs-prior comparison — its in-window prior card must
        still be rescued so a single flaky fetch can't shrink the board (9/10 case,
        below the kill-criterion threshold)."""
        key = self._first_monthly_key()
        prior_date = (self.ASOF.date() - timedelta(days=30)).isoformat()
        prior_path = _make_prior_artifact(tmp_path, [{
            "release": key, "latest_date": prior_date, "value": 3.0,
            "surprise_size": "inline",
        }])

        fresh_date = self.ASOF.date() - timedelta(days=8)

        def _records(entry):
            if entry["key"] == key:
                return None                      # this one series' fetch dies
            step = {"weekly": 7, "quarterly": 91}.get(entry.get("cadence", "monthly"), 30)
            return _make_records_ending(fresh_date, step_days=step, n=40)

        _patch_all_fred(monkeypatch, _records)
        result = ms.build_release_cards(asof=self.ASOF, prior_artifact_path=prior_path)

        assert not result.get("kill_criterion_triggered"), (
            "9/10 series fetched — kill criterion must not fire in this fixture"
        )
        matched = [c for c in result.get("cards", []) if c.get("release") == key]
        assert len(matched) == 1, (
            f"Expected missing-fetch series {key!r} rescued from prior; cards="
            f"{[c.get('release') for c in result.get('cards', [])]}"
        )
        assert matched[0].get("last_good_fallback") is True
        assert matched[0]["latest_date"] == prior_date

    def test_prior_card_outside_window_not_rescued(self, monkeypatch, tmp_path):
        """Prior card whose date is outside the lookback window must NOT be rescued."""
        key = self._first_monthly_key()
        # Prior: 90d ago (outside new 80d monthly window)
        prior_date = (self.ASOF.date() - timedelta(days=90)).isoformat()
        prior_cards = [{"release": key, "latest_date": prior_date, "value": 3.0}]
        prior_path = _make_prior_artifact(tmp_path, prior_cards)

        # Fresh: also stale (110d ago — older than prior but both outside window)
        stale_date = self.ASOF.date() - timedelta(days=110)

        def _records(entry):
            step = {"weekly": 7, "quarterly": 91}.get(entry.get("cadence", "monthly"), 30)
            return _make_records_ending(stale_date, step_days=step, n=40)

        _patch_all_fred(monkeypatch, _records)
        result = ms.build_release_cards(asof=self.ASOF, prior_artifact_path=prior_path)

        matched = [c for c in result.get("cards", []) if c.get("release") == key]
        # Prior card (90d, outside window) must not appear even as fallback
        assert len(matched) == 0, (
            f"Prior card outside window must NOT be rescued; got {matched}"
        )

    def test_no_prior_artifact_path_works_normally(self, monkeypatch):
        """When prior_artifact_path=None, build proceeds without fallback (normal path)."""
        asof = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)
        fresh_date = asof.date() - timedelta(days=30)

        def _records(entry):
            step = {"weekly": 7, "quarterly": 91}.get(entry.get("cadence", "monthly"), 30)
            return _make_records_ending(fresh_date, step_days=step, n=40)

        _patch_all_fred(monkeypatch, _records)
        result = ms.build_release_cards(asof=asof, prior_artifact_path=None)
        # Should succeed with cards and no errors
        assert result.get("schema") == "macro_releases.v1"
        assert isinstance(result.get("cards"), list)

    def test_missing_prior_artifact_file_works_normally(self, monkeypatch, tmp_path):
        """Passing a path to a non-existent file degrades gracefully (no exception)."""
        nonexistent = tmp_path / "does_not_exist.json"
        asof = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)
        fresh_date = asof.date() - timedelta(days=30)

        def _records(entry):
            step = {"weekly": 7, "quarterly": 91}.get(entry.get("cadence", "monthly"), 30)
            return _make_records_ending(fresh_date, step_days=step, n=40)

        _patch_all_fred(monkeypatch, _records)
        # Must not raise
        result = ms.build_release_cards(asof=asof, prior_artifact_path=nonexistent)
        assert result.get("schema") == "macro_releases.v1"


class TestKillCriterionRescue:
    """Under kill-criterion (< 6 fetched), prior cards within window are rescued."""

    def test_kill_criterion_rescues_in_window_prior_cards(self, monkeypatch, tmp_path):
        """If <6 series fetch and prior has cards within window, they are rescued."""
        asof = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)
        # Write a prior artifact with a couple of cards
        prior_date = (asof.date() - timedelta(days=30)).isoformat()
        prior_cards = [
            {"release": "cpi", "latest_date": prior_date, "value": 3.0,
             "surprise_size": "inline"},
            {"release": "payrolls", "latest_date": prior_date, "value": 250000.0,
             "surprise_size": "notable"},
        ]
        prior_path = _make_prior_artifact(tmp_path, prior_cards)

        # Patch fetch to return None for all series → triggers kill-criterion
        monkeypatch.setattr(ms, "_fetch_fred_series", lambda sid: None)

        result = ms.build_release_cards(asof=asof, prior_artifact_path=prior_path)
        assert result.get("kill_criterion_triggered") is True
        rescued = result.get("cards", [])
        assert len(rescued) > 0, "Prior cards within window must be rescued under kill-criterion"
        for c in rescued:
            assert c.get("last_good_fallback") is True

    def test_kill_criterion_does_not_rescue_stale_prior_cards(self, monkeypatch, tmp_path):
        """Under kill-criterion, prior cards outside their lookback window are not rescued."""
        asof = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)
        # Prior card 90d ago (outside 80d monthly window)
        stale_prior_date = (asof.date() - timedelta(days=90)).isoformat()
        prior_cards = [
            {"release": "cpi", "latest_date": stale_prior_date, "value": 3.0},
        ]
        prior_path = _make_prior_artifact(tmp_path, prior_cards)

        monkeypatch.setattr(ms, "_fetch_fred_series", lambda sid: None)

        result = ms.build_release_cards(asof=asof, prior_artifact_path=prior_path)
        assert result.get("kill_criterion_triggered") is True
        rescued = result.get("cards", [])
        assert len(rescued) == 0, (
            f"Stale prior cards must not be rescued under kill-criterion; got {rescued}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-x", "-q"])
