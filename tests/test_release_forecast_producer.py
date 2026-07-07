"""Tests for scripts/build_release_forecast.py — MRI PR-C nightly producer.

Categories:
  1. Contract   — latest.json schema keys, display_only=True, authority booleans False,
                  asof is full-ISO-UTC parseable.
  2. Ledger     — append-only (no dup on double run), projection rows unaffected by
                  capture, scored row math correctness.
  3. Scoreboard — computed from scored rows only; n=0 honest output.
  4. Cleveland  — PIT read (obs_date <= today), absent-file fail-open.
  5. Policy backdrop — all sources missing → nulls, no raise.

All tests use synthetic data / tmp directories. No real parquet files are required.

Run:
    python -m pytest tests/test_release_forecast_producer.py -v
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from scripts.build_release_forecast import (
    _append_ledger_rows,
    _build_scoreboard,
    _check_release_day_capture,
    _claims_period_for_release_date,
    _compute_actual_from_print,
    _ledger_key,
    _load_ledger,
    _next_thursday,
    _read_cleveland_nowcast,
    _read_policy_backdrop,
    _wilson,
)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture()
def tmp_root(tmp_path: Path) -> Path:
    """A minimal repo-shaped temp root directory."""
    (tmp_path / "data" / "release_forecast").mkdir(parents=True)
    (tmp_path / "data" / "cleveland_nowcast").mkdir(parents=True)
    (tmp_path / "data" / "regime").mkdir(parents=True)
    (tmp_path / "data" / "fred_vintage").mkdir(parents=True)
    (tmp_path / "site" / "macrodata").mkdir(parents=True)
    return tmp_path


def _make_vintage_parquet(root: Path, rows: list[dict]) -> None:
    """Write a minimal vintages.parquet for testing."""
    df = pd.DataFrame(rows)
    for col in ("period", "realtime_start", "realtime_end"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col])
    path = root / "data" / "fred_vintage" / "vintages.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def _make_cleveland_parquet(root: Path, rows: list[dict]) -> None:
    """Write a minimal cleveland_nowcast/nowcast.parquet for testing."""
    df = pd.DataFrame(rows)
    path = root / "data" / "cleveland_nowcast" / "nowcast.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def _projection_row(release: str = "cpi_headline", period: str = "2026-06",
                    asof_night: str = "2026-07-01", proj_point: float = 0.28,
                    proj_p10: float = 0.10, proj_p90: float = 0.46,
                    release_date: str = "2026-07-10") -> dict:
    return {
        "row_type": "projection",
        "asof_night": asof_night,
        "release": release,
        "period": period,
        "release_date": release_date,
        "days_to": 9,
        "projection_point": proj_point,
        "projection_p10": proj_p10,
        "projection_p90": proj_p90,
        "confidence": 0.60,
        "input_completeness": 0.75,
        "benchmark_naive_prior": 0.24,
        "benchmark_trailing_3m": 0.25,
        "benchmark_ar_model": 0.26,
        "benchmark_cleveland": 0.30,
        "surprise_skew_sigma": 0.40,
        "surprise_skew_tag": "hotter",
        "fed_stance": "hawkish",
        "gap_bp": 7,
        "implied_cuts_12m": -1,
        "next_fomc": "2026-07-29",
    }


def _scored_row(release: str = "cpi_headline", period: str = "2026-06",
                asof_night: str = "2026-07-14") -> dict:
    return {
        "row_type": "scored",
        "asof_night": asof_night,
        "release": release,
        "period": period,
        "release_date": "2026-07-10",
        "actual": 0.30,
        "raw_initial_print": None,
        "frozen_asof_night": "2026-07-01",
        "frozen_projection_point": 0.28,
        "frozen_projection_p10": 0.10,
        "frozen_projection_p90": 0.46,
        "our_surprise": 0.02,
        "surprise_vs_naive": 0.06,
        "surprise_vs_trailing": 0.05,
        "surprise_vs_ar": 0.04,
        "surprise_vs_cleveland": 0.0,
        "interval_hit": True,
        "skew_hit": True,
    }


# ============================================================
# 1. CONTRACT — latest.json schema
# ============================================================

class TestContract:
    """Verify the latest.json artifact structure."""

    def test_build_produces_schema_keys(self, tmp_root: Path, monkeypatch):
        """build() returns a dict with all required release_forecast.v1 keys."""
        # Patch _find_upcoming_releases to return empty (no real engine needed)
        import scripts.build_release_forecast as producer
        monkeypatch.setattr(producer, "_find_upcoming_releases", lambda *a, **k: [])
        monkeypatch.setattr(producer, "_read_policy_backdrop", lambda *a, **k: {
            "fed_stance": None, "gap_bp": None,
            "implied_cuts_12m": None, "next_fomc": None, "guidance_direction": None,
        })

        result = producer.build(tmp_root, dry_run=True)

        assert result["schema"] == "release_forecast.v1"
        assert "asof" in result
        assert "display_only" in result
        assert "authority" in result
        assert "upcoming" in result
        assert "last_scored" in result
        assert "scoreboard_ref" in result

    def test_display_only_true(self, tmp_root: Path, monkeypatch):
        """display_only must always be True."""
        import scripts.build_release_forecast as producer
        monkeypatch.setattr(producer, "_find_upcoming_releases", lambda *a, **k: [])
        monkeypatch.setattr(producer, "_read_policy_backdrop", lambda *a, **k: {
            "fed_stance": None, "gap_bp": None,
            "implied_cuts_12m": None, "next_fomc": None, "guidance_direction": None,
        })

        result = producer.build(tmp_root, dry_run=True)
        assert result["display_only"] is True

    def test_authority_booleans_all_false(self, tmp_root: Path, monkeypatch):
        """All authority booleans must be False."""
        import scripts.build_release_forecast as producer
        monkeypatch.setattr(producer, "_find_upcoming_releases", lambda *a, **k: [])
        monkeypatch.setattr(producer, "_read_policy_backdrop", lambda *a, **k: {
            "fed_stance": None, "gap_bp": None,
            "implied_cuts_12m": None, "next_fomc": None, "guidance_direction": None,
        })

        result = producer.build(tmp_root, dry_run=True)
        auth = result["authority"]
        assert auth.get("can_score") is False
        assert auth.get("can_size") is False
        assert auth.get("can_trade") is False

    def test_asof_is_parseable_utc_iso(self, tmp_root: Path, monkeypatch):
        """asof must be a full ISO UTC timestamp parseable by datetime.fromisoformat."""
        import scripts.build_release_forecast as producer
        monkeypatch.setattr(producer, "_find_upcoming_releases", lambda *a, **k: [])
        monkeypatch.setattr(producer, "_read_policy_backdrop", lambda *a, **k: {
            "fed_stance": None, "gap_bp": None,
            "implied_cuts_12m": None, "next_fomc": None, "guidance_direction": None,
        })

        result = producer.build(tmp_root, dry_run=True)
        asof = result["asof"]
        # Must be parseable and end with Z (UTC)
        assert isinstance(asof, str)
        assert asof.endswith("Z"), f"asof does not end with Z: {asof!r}"
        # Should parse successfully (replace trailing Z with +00:00 for Python < 3.11)
        dt = datetime.fromisoformat(asof.replace("Z", "+00:00"))
        assert dt.tzinfo is not None


# ============================================================
# 2. LEDGER — append-only, no dups, projection rows not mutated
# ============================================================

class TestLedger:
    """Verify ledger append-only and idempotency semantics."""

    def test_append_creates_ledger(self, tmp_root: Path):
        """Appending rows to a non-existent ledger creates the file."""
        ledger_path = tmp_root / "data" / "release_forecast" / "forward_ledger.jsonl"
        row = _projection_row()
        _append_ledger_rows(ledger_path, [row])
        assert ledger_path.exists()
        rows = _load_ledger(ledger_path)
        assert len(rows) == 1
        assert rows[0]["row_type"] == "projection"

    def test_no_dup_same_night(self, tmp_root: Path):
        """Running twice same night appends zero duplicate rows."""
        ledger_path = tmp_root / "data" / "release_forecast" / "forward_ledger.jsonl"
        row = _projection_row()
        _append_ledger_rows(ledger_path, [row])
        _append_ledger_rows(ledger_path, [row])  # second run
        rows = _load_ledger(ledger_path)
        assert len(rows) == 1, f"Expected 1 row, got {len(rows)}"

    def test_second_night_appends(self, tmp_root: Path):
        """A second night with a different asof_night appends a new row."""
        ledger_path = tmp_root / "data" / "release_forecast" / "forward_ledger.jsonl"
        row1 = _projection_row(asof_night="2026-07-01")
        row2 = _projection_row(asof_night="2026-07-02")
        _append_ledger_rows(ledger_path, [row1])
        _append_ledger_rows(ledger_path, [row2])
        rows = _load_ledger(ledger_path)
        assert len(rows) == 2

    def test_projection_row_not_mutated_by_scored_append(self, tmp_root: Path):
        """Appending a scored row never changes existing projection rows."""
        ledger_path = tmp_root / "data" / "release_forecast" / "forward_ledger.jsonl"
        proj = _projection_row(asof_night="2026-07-01", proj_point=0.28)
        _append_ledger_rows(ledger_path, [proj])

        scored = _scored_row(asof_night="2026-07-14")
        _append_ledger_rows(ledger_path, [scored])

        rows = _load_ledger(ledger_path)
        proj_rows = [r for r in rows if r["row_type"] == "projection"]
        assert len(proj_rows) == 1
        assert proj_rows[0]["projection_point"] == pytest.approx(0.28)

    def test_scored_row_math(self, tmp_root: Path):
        """Release-day capture computes correct surprise and interval hit."""
        today = date(2026, 7, 14)
        # Build a minimal vintage parquet with prior + current month for CPI
        _make_vintage_parquet(tmp_root, [
            # Prior month (2026-05): level = 315.000
            {
                "series": "CPIAUCSL", "period": "2026-05-01",
                "value": 315.000, "realtime_start": "2026-06-12",
                "realtime_end": "2099-01-01",
            },
            # Current month (2026-06): initial print level = 316.260
            {
                "series": "CPIAUCSL", "period": "2026-06-01",
                "value": 316.260, "realtime_start": "2026-07-14",
                "realtime_end": "2099-01-01",
            },
        ])

        proj_row = _projection_row(
            release="cpi_headline", period="2026-06",
            asof_night="2026-07-01",
            proj_point=0.28, proj_p10=0.10, proj_p90=0.46,
            release_date="2026-07-10",
        )
        existing_ledger = [proj_row]

        scored_rows = _check_release_day_capture(today, tmp_root, existing_ledger)

        # Expected actual: (316.260 / 315.000 - 1) * 100 = 0.4000 MoM%
        assert len(scored_rows) == 1, f"Expected 1 scored row, got {scored_rows}"
        sr = scored_rows[0]

        expected_actual = round((316.260 / 315.000 - 1) * 100, 4)
        assert sr["actual"] == pytest.approx(expected_actual, abs=1e-3)
        assert sr["row_type"] == "scored"

        # Interval hit: expected_actual (0.4) is within [0.10, 0.46]
        assert sr["interval_hit"] is True

        # Surprise vs our projection
        expected_surprise = round(expected_actual - 0.28, 4)
        assert sr["our_surprise"] == pytest.approx(expected_surprise, abs=1e-3)

    def test_no_duplicate_scored_row(self, tmp_root: Path):
        """If a scored row already exists in the ledger, no second scored row is emitted."""
        today = date(2026, 7, 15)
        existing_ledger = [
            _projection_row(asof_night="2026-07-01"),
            _scored_row(asof_night="2026-07-14"),
        ]
        scored_rows = _check_release_day_capture(today, tmp_root, existing_ledger)
        # Already scored, so no new rows
        assert len(scored_rows) == 0


# ============================================================
# 3. SCOREBOARD — from scored rows only; n=0 honest
# ============================================================

class TestScoreboard:
    """Verify scoreboard is computed from scored rows only."""

    def test_n_zero_honest_output(self):
        """With no scored rows, scoreboard prints zeros/nulls honestly."""
        sb = _build_scoreboard([], accrual_start="2026-07-07")
        assert sb["schema"] == "release_forecast_scoreboard.v1"
        assert sb["forward_accrual_began"] == "2026-07-07"
        assert sb["by_release"] == {}

    def test_projection_rows_excluded(self):
        """Projection rows in ledger must NOT enter the scoreboard."""
        ledger = [_projection_row()]  # projection only
        sb = _build_scoreboard(ledger, accrual_start="2026-07-07")
        assert sb["by_release"] == {}

    def test_scoreboard_from_scored_rows(self):
        """Scoreboard correctly aggregates a set of scored rows."""
        scored1 = _scored_row(
            release="cpi_headline", period="2026-05", asof_night="2026-06-15",
        )
        scored1["actual"] = 0.25
        scored1["frozen_projection_point"] = 0.28
        scored1["interval_hit"] = True
        scored1["skew_hit"] = False
        scored1["surprise_vs_naive"] = 0.01

        scored2 = _scored_row(
            release="cpi_headline", period="2026-06", asof_night="2026-07-14",
        )
        scored2["actual"] = 0.30
        scored2["frozen_projection_point"] = 0.27
        scored2["interval_hit"] = False
        scored2["skew_hit"] = True
        scored2["surprise_vs_naive"] = 0.06

        sb = _build_scoreboard([scored1, scored2], accrual_start="2026-07-07")

        cpi_stats = sb["by_release"].get("cpi_headline")
        assert cpi_stats is not None
        assert cpi_stats["n"] == 2
        # MAE ours: abs(0.25-0.28) + abs(0.30-0.27) = 0.03 + 0.03 = 0.03 avg
        assert cpi_stats["mae_ours"] == pytest.approx(0.03, abs=1e-4)
        # coverage: 1/2 = 0.5
        assert cpi_stats["p10_p90_coverage"] == pytest.approx(0.5, abs=1e-4)
        # skew hit: 1/2 = 0.5
        assert cpi_stats["skew_hit_rate"] == pytest.approx(0.5, abs=1e-4)
        # Wilson CI must be present
        assert cpi_stats["skew_hit_rate_wilson_ci"] is not None
        assert len(cpi_stats["skew_hit_rate_wilson_ci"]) == 2

    def test_multiple_release_types_independent(self):
        """NFP and CPI stats are tracked independently."""
        cpi_scored = _scored_row(release="cpi_headline", period="2026-05")
        cpi_scored["actual"] = 0.25
        cpi_scored["frozen_projection_point"] = 0.28
        cpi_scored["interval_hit"] = True
        cpi_scored["skew_hit"] = True

        nfp_scored = _scored_row(release="nfp", period="2026-05")
        nfp_scored["actual"] = 200.0
        nfp_scored["frozen_projection_point"] = 180.0
        nfp_scored["interval_hit"] = False
        nfp_scored["skew_hit"] = False

        sb = _build_scoreboard([cpi_scored, nfp_scored], accrual_start="2026-07-07")
        assert "cpi_headline" in sb["by_release"]
        assert "nfp" in sb["by_release"]
        assert sb["by_release"]["cpi_headline"]["n"] == 1
        assert sb["by_release"]["nfp"]["n"] == 1


# ============================================================
# 4. CLEVELAND BENCHMARK — PIT read; absent-file fail-open
# ============================================================

class TestClevelandBenchmark:
    """Verify PIT safety and fail-open behavior for Cleveland nowcast read."""

    def test_absent_file_returns_none(self, tmp_root: Path):
        """If the nowcast parquet doesn't exist, return None without raising."""
        result = _read_cleveland_nowcast(tmp_root, "cpi_headline", "2026-06", date.today())
        assert result is None

    def test_pit_filter_excludes_future_obs(self, tmp_root: Path):
        """obs_date > today must be excluded from the PIT read."""
        today = date(2026, 7, 7)
        _make_cleveland_parquet(tmp_root, [
            {
                "first_seen_asof": "2026-07-08",
                "target_period": "2026-06-01",
                "series": "cpi_mom",
                "obs_date": "2026-07-08",  # future relative to today
                "value": 0.40,
            },
            {
                "first_seen_asof": "2026-07-06",
                "target_period": "2026-06-01",
                "series": "cpi_mom",
                "obs_date": "2026-07-06",  # past relative to today
                "value": 0.31,
            },
        ])
        result = _read_cleveland_nowcast(tmp_root, "cpi_headline", "2026-06", today)
        # Only the 2026-07-06 obs is PIT-safe; value should be 0.31
        assert result == pytest.approx(0.31, abs=1e-5)

    def test_returns_latest_obs_date_value(self, tmp_root: Path):
        """When multiple obs_dates are PIT-safe, the latest one wins."""
        today = date(2026, 7, 10)
        _make_cleveland_parquet(tmp_root, [
            {
                "first_seen_asof": "2026-07-05",
                "target_period": "2026-06-01",
                "series": "cpi_mom",
                "obs_date": "2026-07-05",
                "value": 0.29,
            },
            {
                "first_seen_asof": "2026-07-07",
                "target_period": "2026-06-01",
                "series": "cpi_mom",
                "obs_date": "2026-07-07",
                "value": 0.31,
            },
        ])
        result = _read_cleveland_nowcast(tmp_root, "cpi_headline", "2026-06", today)
        assert result == pytest.approx(0.31, abs=1e-5)

    def test_wrong_series_returns_none(self, tmp_root: Path):
        """NFP release type has no Cleveland series mapping, returns None."""
        _make_cleveland_parquet(tmp_root, [
            {
                "first_seen_asof": "2026-07-05",
                "target_period": "2026-06-01",
                "series": "cpi_mom",
                "obs_date": "2026-07-05",
                "value": 0.29,
            },
        ])
        result = _read_cleveland_nowcast(tmp_root, "nfp", "2026-06", date.today())
        assert result is None

    def test_core_cpi_uses_core_series(self, tmp_root: Path):
        """cpi_core maps to core_cpi_mom series."""
        today = date(2026, 7, 10)
        _make_cleveland_parquet(tmp_root, [
            {
                "first_seen_asof": "2026-07-07",
                "target_period": "2026-06-01",
                "series": "core_cpi_mom",
                "obs_date": "2026-07-07",
                "value": 0.26,
            },
            {
                "first_seen_asof": "2026-07-07",
                "target_period": "2026-06-01",
                "series": "cpi_mom",
                "obs_date": "2026-07-07",
                "value": 0.31,
            },
        ])
        result = _read_cleveland_nowcast(tmp_root, "cpi_core", "2026-06", today)
        assert result == pytest.approx(0.26, abs=1e-5)


# ============================================================
# 5. POLICY BACKDROP — all sources missing → nulls, no raise
# ============================================================

class TestPolicyBackdrop:
    """Verify fail-open behavior when all backdrop sources are absent."""

    def test_all_sources_missing_returns_nulls(self, tmp_root: Path):
        """When no regime/latest.json and no event_calendar, backdrop is all null."""
        # tmp_root has no data/regime/latest.json and event_calendar may fail
        # We patch event_calendar to raise so we don't need network
        import scripts.build_release_forecast as producer

        def _failing_calendar(*a, **k):
            raise RuntimeError("test: no calendar")

        original = None
        try:
            import engine.event_calendar as ec
            original = ec.us_macro_events
            ec.us_macro_events = _failing_calendar
        except ImportError:
            pass

        try:
            result = _read_policy_backdrop(tmp_root, date(2026, 7, 7))
        finally:
            if original is not None:
                import engine.event_calendar as ec
                ec.us_macro_events = original

        assert result["fed_stance"] is None
        assert result["gap_bp"] is None
        assert result["implied_cuts_12m"] is None
        assert result["next_fomc"] is None
        assert result["guidance_direction"] is None

    def test_reads_from_regime_latest(self, tmp_root: Path):
        """When regime/latest.json exists, backdrop fields are populated."""
        regime_data = {
            "fed_stance": {"stance": "hawkish", "implied_cuts_12m": -1.0},
            "fed_path": {"gap": {"gap_bp": 7}},
            "catalyst_tone": {"guidance_direction": "on_hold"},
        }
        regime_path = tmp_root / "data" / "regime" / "latest.json"
        regime_path.parent.mkdir(parents=True, exist_ok=True)
        with open(regime_path, "w") as fh:
            json.dump(regime_data, fh)

        # Patch event_calendar to avoid network
        import scripts.build_release_forecast as producer

        def _no_fomc(*a, **k):
            return []

        try:
            import engine.event_calendar as ec
            original = ec.us_macro_events
            ec.us_macro_events = _no_fomc
        except ImportError:
            original = None

        try:
            result = _read_policy_backdrop(tmp_root, date(2026, 7, 7))
        finally:
            if original is not None:
                import engine.event_calendar as ec
                ec.us_macro_events = original

        assert result["fed_stance"] == "hawkish"
        assert result["gap_bp"] == 7
        assert result["implied_cuts_12m"] == -1.0
        assert result["guidance_direction"] == "on_hold"


# ============================================================
# 6. WILSON CI helper
# ============================================================

class TestWilson:
    def test_n_zero_returns_none(self):
        assert _wilson(0, 0) is None

    def test_perfect_hit_rate(self):
        ci = _wilson(10, 10)
        assert ci is not None
        assert ci[0] > 0.7  # Lower bound above 0.7 for 10/10

    def test_zero_hit_rate(self):
        ci = _wilson(0, 10)
        assert ci is not None
        assert ci[0] == 0.0
        assert ci[1] < 0.3

    def test_output_bounds(self):
        for k, n in [(3, 10), (7, 20), (15, 30)]:
            ci = _wilson(k, n)
            assert ci is not None
            lb, ub = ci
            assert 0.0 <= lb <= ub <= 1.0


# ============================================================
# 7. DRY-RUN integration (smoke — no real data required)
# ============================================================

class TestDryRun:
    """Smoke test: build() with dry_run=True completes without writing files."""

    def test_dry_run_no_files_written(self, tmp_root: Path, monkeypatch):
        import scripts.build_release_forecast as producer
        monkeypatch.setattr(producer, "_find_upcoming_releases", lambda *a, **k: [])
        monkeypatch.setattr(producer, "_read_policy_backdrop", lambda *a, **k: {
            "fed_stance": None, "gap_bp": None,
            "implied_cuts_12m": None, "next_fomc": None, "guidance_direction": None,
        })

        result = producer.build(tmp_root, dry_run=True)

        # No files written in dry-run mode
        assert not (tmp_root / "data" / "release_forecast" / "latest.json").exists()
        assert not (tmp_root / "data" / "release_forecast" / "forward_ledger.jsonl").exists()
        assert not (tmp_root / "data" / "release_forecast" / "scoreboard.json").exists()
        assert not (tmp_root / "site" / "macrodata" / "release_forecast.json").exists()

        # Result is still a well-formed payload
        assert result["schema"] == "release_forecast.v1"
        assert result["display_only"] is True

    def test_full_run_writes_artifacts(self, tmp_root: Path, monkeypatch):
        """build() with dry_run=False writes latest.json, scoreboard, and site copy."""
        import scripts.build_release_forecast as producer
        monkeypatch.setattr(producer, "_find_upcoming_releases", lambda *a, **k: [])
        monkeypatch.setattr(producer, "_read_policy_backdrop", lambda *a, **k: {
            "fed_stance": None, "gap_bp": None,
            "implied_cuts_12m": None, "next_fomc": None, "guidance_direction": None,
        })

        producer.build(tmp_root, dry_run=False)

        # latest.json, scoreboard, and site copy are always written
        assert (tmp_root / "data" / "release_forecast" / "latest.json").exists()
        assert (tmp_root / "data" / "release_forecast" / "scoreboard.json").exists()
        assert (tmp_root / "site" / "macrodata" / "release_forecast.json").exists()
        # ledger is only written when there are new rows to append; with no upcoming
        # releases the ledger file may not exist yet — that is correct behavior

    def test_double_run_no_dup_ledger(self, tmp_root: Path, monkeypatch):
        """Running build() twice same night produces exactly the same ledger rows."""
        import scripts.build_release_forecast as producer
        monkeypatch.setattr(producer, "_find_upcoming_releases", lambda *a, **k: [])
        monkeypatch.setattr(producer, "_read_policy_backdrop", lambda *a, **k: {
            "fed_stance": None, "gap_bp": None,
            "implied_cuts_12m": None, "next_fomc": None, "guidance_direction": None,
        })

        producer.build(tmp_root, dry_run=False)
        producer.build(tmp_root, dry_run=False)  # second run same night

        ledger_path = tmp_root / "data" / "release_forecast" / "forward_ledger.jsonl"
        rows = _load_ledger(ledger_path)
        # No duplicates: each (release, period, row_type, asof_night) appears once
        keys = [_ledger_key(r) for r in rows]
        assert len(keys) == len(set(keys)), "Duplicate ledger keys detected"


# ============================================================
# 8. CLAIMS — weekly period format, benchmark_only mode, scoreboard
# ============================================================

class TestClaimsHelpers:
    """Unit tests for claims-specific helper functions."""

    def test_next_thursday_from_monday(self):
        """From Monday, next Thursday is 3 days later."""
        monday = date(2026, 7, 6)  # Monday (weekday=0)
        assert monday.weekday() == 0  # sanity
        thu = _next_thursday(monday)
        assert thu == date(2026, 7, 9)  # Thursday
        assert thu.weekday() == 3

    def test_next_thursday_from_thursday(self):
        """From Thursday itself, next Thursday is 7 days later (not same day)."""
        thu = date(2026, 7, 9)  # Thursday (weekday=3)
        assert thu.weekday() == 3  # sanity
        next_thu = _next_thursday(thu)
        assert next_thu == date(2026, 7, 16)
        assert next_thu.weekday() == 3

    def test_next_thursday_from_friday(self):
        """From Friday, next Thursday is 6 days later."""
        fri = date(2026, 7, 10)  # Friday (weekday=4)
        assert fri.weekday() == 4
        next_thu = _next_thursday(fri)
        assert next_thu == date(2026, 7, 16)
        assert next_thu.weekday() == 3

    def test_claims_period_from_release_date(self):
        """Claims released Thursday; period = release_date - 5 days (prior Saturday)."""
        # Thursday 2026-07-09 → Saturday 2026-07-04
        release_date = date(2026, 7, 9)
        period_str = _claims_period_for_release_date(release_date)
        assert period_str == "2026-07-04"
        # Verify it's a Saturday
        period_date = date(2026, 7, 4)
        assert period_date.weekday() == 5  # Saturday

    def test_claims_period_iso_format(self):
        """Period string must be a full ISO date (YYYY-MM-DD)."""
        period_str = _claims_period_for_release_date(date(2026, 7, 9))  # Thursday
        # Must be parseable as a date
        parsed = date.fromisoformat(period_str)
        assert isinstance(parsed, date)


class TestClaimsActualComputation:
    """_compute_actual_from_print for claims: raw level / 1000."""

    def test_claims_raw_to_thousands(self, tmp_root: Path):
        """Claims actual = raw_initial_print / 1000, rounded to 2 decimals."""
        raw = 215000.0
        actual = _compute_actual_from_print("claims", raw, tmp_root, "2026-07-05")
        assert actual == pytest.approx(215.0, abs=1e-4)

    def test_claims_actual_odd_value(self, tmp_root: Path):
        """Claims actual with a non-round value."""
        raw = 215482.0
        actual = _compute_actual_from_print("claims", raw, tmp_root, "2026-07-05")
        assert actual == pytest.approx(215.48, abs=1e-3)

    def test_initial_print_weekly_period(self, tmp_root: Path):
        """_get_initial_print for claims uses full ISO date period, not YYYY-MM-01."""
        from scripts.build_release_forecast import _get_initial_print

        # Write a vintage parquet with a weekly-format period (Saturday)
        period_str = "2026-07-05"  # Saturday
        release_date_str = "2026-07-10"  # Thursday
        _make_vintage_parquet(tmp_root, [
            {
                "series": "ICSA",
                "period": period_str,  # full ISO date
                "value": 215000.0,
                "realtime_start": release_date_str,
                "realtime_end": "2099-12-31",
            },
        ])
        raw = _get_initial_print(tmp_root, "claims", period_str, release_date_str)
        assert raw == pytest.approx(215000.0, abs=1.0)

    def test_initial_print_monthly_still_uses_month_format(self, tmp_root: Path):
        """_get_initial_print for CPI uses YYYY-MM-01 period, not weekly format."""
        from scripts.build_release_forecast import _get_initial_print

        _make_vintage_parquet(tmp_root, [
            {
                "series": "CPIAUCSL",
                "period": "2026-06-01",
                "value": 316.260,
                "realtime_start": "2026-07-10",
                "realtime_end": "2099-12-31",
            },
        ])
        # period_str "2026-06" → internally target_ts = 2026-06-01
        raw = _get_initial_print(tmp_root, "cpi_headline", "2026-06", "2026-07-10")
        assert raw == pytest.approx(316.260, abs=1e-3)


class TestClaimsLedger:
    """Weekly claims ledger: period is full ISO date; dedup works correctly."""

    def test_claims_weekly_period_dedup(self, tmp_root: Path):
        """Claims ledger row with weekly period string deduplicates correctly."""
        ledger_path = tmp_root / "data" / "release_forecast" / "forward_ledger.jsonl"
        row = {
            "row_type": "projection",
            "asof_night": "2026-07-07",
            "release": "claims",
            "period": "2026-07-05",  # full ISO date (Saturday)
            "release_date": "2026-07-10",
            "days_to": 3,
            "projection_point": None,
            "projection_p10": None,
            "projection_p90": None,
            "confidence": None,
            "input_completeness": None,
            "benchmark_naive_prior": 215.0,
            "benchmark_trailing": 217.0,
            "benchmark_trailing_key": "trailing_4w",
            "benchmark_ar_model": 214.5,
            "benchmark_cleveland": None,
            "projection_mode": "benchmark_only",
            "surprise_skew_sigma": None,
            "surprise_skew_tag": None,
            "fed_stance": None,
            "gap_bp": None,
            "implied_cuts_12m": None,
            "next_fomc": None,
        }
        _append_ledger_rows(ledger_path, [row])
        _append_ledger_rows(ledger_path, [row])  # second run same night
        rows = _load_ledger(ledger_path)
        assert len(rows) == 1, f"Expected 1 row after double append, got {len(rows)}"

    def test_claims_different_weekly_periods_not_duped(self, tmp_root: Path):
        """Two different weekly periods for claims each get their own ledger row."""
        ledger_path = tmp_root / "data" / "release_forecast" / "forward_ledger.jsonl"

        def _make_row(period_str: str, asof_night: str) -> dict:
            return {
                "row_type": "projection",
                "asof_night": asof_night,
                "release": "claims",
                "period": period_str,
                "release_date": "2026-07-10",
                "days_to": 3,
                "projection_point": None,
                "projection_p10": None,
                "projection_p90": None,
                "confidence": None,
                "input_completeness": None,
                "benchmark_naive_prior": 215.0,
                "benchmark_trailing": 217.0,
                "benchmark_trailing_key": "trailing_4w",
                "benchmark_ar_model": 214.5,
                "benchmark_cleveland": None,
                "projection_mode": "benchmark_only",
                "surprise_skew_sigma": None,
                "surprise_skew_tag": None,
                "fed_stance": None,
                "gap_bp": None,
                "implied_cuts_12m": None,
                "next_fomc": None,
            }

        row1 = _make_row("2026-07-05", "2026-07-07")
        row2 = _make_row("2026-07-12", "2026-07-07")
        _append_ledger_rows(ledger_path, [row1, row2])
        rows = _load_ledger(ledger_path)
        assert len(rows) == 2, f"Two different periods must produce 2 ledger rows, got {len(rows)}"


class TestClaimsScoreboard:
    """Scoreboard claims entry: block_note present; trailing_4w label used."""

    def _make_claims_scored(self, actual_k: float = 215.0, proj_k: float | None = None) -> dict:
        """Minimal scored row for claims."""
        return {
            "row_type": "scored",
            "asof_night": "2026-07-14",
            "release": "claims",
            "period": "2026-07-05",
            "release_date": "2026-07-10",
            "actual": actual_k,
            "raw_initial_print": None,
            "frozen_asof_night": "2026-07-07",
            "frozen_projection_point": proj_k,
            "frozen_projection_p10": None,
            "frozen_projection_p90": None,
            "our_surprise": None,  # null in benchmark_only mode
            "surprise_vs_naive": round(actual_k - 213.0, 4),
            "surprise_vs_trailing": round(actual_k - 217.0, 4),
            "surprise_vs_ar": round(actual_k - 214.5, 4),
            "surprise_vs_cleveland": None,
            "interval_hit": None,  # null in benchmark_only mode
            "skew_hit": None,  # null in benchmark_only mode
            "benchmark_trailing_key": "trailing_4w",
            "projection_mode": "benchmark_only",
        }

    def test_claims_scoreboard_block_note(self):
        """Claims scoreboard entry must contain block_note (MRI-R9 caveat)."""
        scored = self._make_claims_scored()
        sb = _build_scoreboard([scored], accrual_start="2026-07-07")
        claims_stats = sb["by_release"].get("claims")
        assert claims_stats is not None, "claims entry missing from scoreboard"
        assert "block_note" in claims_stats, "block_note must be present for claims"
        assert "autocorrelation" in claims_stats["block_note"].lower() or \
               "serial" in claims_stats["block_note"].lower() or \
               "MRI-R9" in claims_stats["block_note"], (
            f"block_note must mention autocorrelation/serial correlation or MRI-R9: {claims_stats['block_note']!r}"
        )

    def test_claims_scoreboard_trailing_label_is_4w(self):
        """Claims scoreboard must use mae_trailing_4w label, not mae_trailing_3m."""
        scored = self._make_claims_scored()
        sb = _build_scoreboard([scored], accrual_start="2026-07-07")
        claims_stats = sb["by_release"]["claims"]
        assert "mae_trailing_4w" in claims_stats, "Claims scoreboard must have mae_trailing_4w"
        assert "mae_trailing_3m" not in claims_stats, "Claims scoreboard must NOT have mae_trailing_3m"

    def test_claims_n_counts(self):
        """n must equal number of scored rows for claims."""
        scored1 = self._make_claims_scored(actual_k=215.0)
        scored2 = self._make_claims_scored(actual_k=218.0)
        scored2["period"] = "2026-07-12"
        scored2["asof_night"] = "2026-07-21"
        sb = _build_scoreboard([scored1, scored2], accrual_start="2026-07-07")
        claims_stats = sb["by_release"]["claims"]
        assert claims_stats["n"] == 2

    def test_claims_benchmark_only_mae_ours_null(self):
        """In benchmark_only mode, mae_ours is None since our_surprise is None."""
        scored = self._make_claims_scored(proj_k=None)
        scored["our_surprise"] = None
        scored["frozen_projection_point"] = None
        sb = _build_scoreboard([scored], accrual_start="2026-07-07")
        claims_stats = sb["by_release"]["claims"]
        # With proj_point=None and our_surprise=None, mae_ours should be None
        assert claims_stats["mae_ours"] is None, (
            "mae_ours must be None in benchmark_only mode (no model projection)"
        )
