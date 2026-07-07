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
    _build_projection_ledger_rows,
    _build_scoreboard,
    _build_upcoming_block,
    _check_release_day_capture,
    _CLAIMS_MODE,
    _compute_actual_from_print,
    _get_initial_print,
    _ledger_key,
    _load_ledger,
    _read_cleveland_nowcast,
    _read_policy_backdrop,
    _run_projection,
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
        """build() returns a dict with all required release_forecast.v1/v2 keys."""
        # Patch _find_upcoming_releases to return empty (no real engine needed)
        import scripts.build_release_forecast as producer
        monkeypatch.setattr(producer, "_find_upcoming_releases", lambda *a, **k: [])
        monkeypatch.setattr(producer, "_read_policy_backdrop", lambda *a, **k: {
            "fed_stance": None, "gap_bp": None,
            "implied_cuts_12m": None, "next_fomc": None, "guidance_direction": None,
        })

        result = producer.build(tmp_root, dry_run=True)

        assert result["schema"] in ("release_forecast.v1", "release_forecast.v2")
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
        assert sb["schema"] in ("release_forecast_scoreboard.v1", "release_forecast_scoreboard.v2")
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
        assert result["schema"] in ("release_forecast.v1", "release_forecast.v2")
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
# 8. CLAIMS — scoreboard label, block_note, benchmark_only mode
# ============================================================

def _claims_scored_row(period: str = "2026-07-03", asof_night: str = "2026-07-10") -> dict:
    """Build a synthetic scored row for claims (weekly period, benchmark_only mode).

    In benchmark_only mode projection_point is null, so our_surprise, interval_hit,
    and skew_hit are also null. Benchmarks carry real values so trailing/naive
    surprise_vs_* is computable.
    """
    return {
        "row_type": "scored",
        "asof_night": asof_night,
        "release": "claims",
        "period": period,
        "release_date": asof_night,
        "actual": 215.0,            # ICSA in thousands
        "raw_initial_print": 215000.0,
        "frozen_asof_night": "2026-07-09",
        "frozen_projection_point": None,     # benchmark_only
        "frozen_projection_p10": None,
        "frozen_projection_p90": None,
        "our_surprise": None,                # null in benchmark_only
        "surprise_vs_naive": 215.0 - 220.0, # vs naive_prior
        "surprise_vs_trailing": 215.0 - 218.0,
        "surprise_vs_ar": 215.0 - 217.0,
        "surprise_vs_cleveland": None,
        "interval_hit": None,               # null in benchmark_only
        "skew_hit": None,                   # null in benchmark_only
        "projection_mode": "benchmark_only",
        "benchmark_trailing_key": "benchmark_trailing_4w",
    }


class TestClaimsScoreboard:
    """Verify claims-specific scoreboard behavior: block_note, label, and benchmark_only mode."""

    def test_claims_scoreboard_block_note_present(self):
        """Claims scoreboard entry must include a block_note (MRI-R9 caveat)."""
        row = _claims_scored_row()
        sb = _build_scoreboard([row], accrual_start="2026-07-07")
        claims_stats = sb["by_release"].get("claims")
        assert claims_stats is not None, "claims entry missing from scoreboard"
        assert "block_note" in claims_stats, "block_note missing from claims scoreboard entry"
        assert "MRI-R9" in claims_stats["block_note"]

    def test_claims_scoreboard_trailing_label_is_4w(self):
        """Claims scoreboard uses mae_trailing_4w label, not mae_trailing_3m."""
        row = _claims_scored_row()
        sb = _build_scoreboard([row], accrual_start="2026-07-07")
        claims_stats = sb["by_release"]["claims"]
        assert "mae_trailing_4w" in claims_stats, "mae_trailing_4w key missing"
        assert "mae_trailing_3m" not in claims_stats, "mae_trailing_3m must not appear for claims"

    def test_claims_scoreboard_n_counts(self):
        """Two scored claims rows produce n=2 in scoreboard."""
        row1 = _claims_scored_row(period="2026-07-03", asof_night="2026-07-10")
        row2 = _claims_scored_row(period="2026-07-10", asof_night="2026-07-17")
        sb = _build_scoreboard([row1, row2], accrual_start="2026-07-07")
        claims_stats = sb["by_release"]["claims"]
        assert claims_stats["n"] == 2

    def test_claims_benchmark_only_mae_ours_null(self):
        """In benchmark_only mode all scored rows have null proj_point -> mae_ours is None."""
        row = _claims_scored_row()
        # Confirm frozen_projection_point is None in our fixture
        assert row["frozen_projection_point"] is None
        sb = _build_scoreboard([row], accrual_start="2026-07-07")
        claims_stats = sb["by_release"]["claims"]
        # mae_ours = None because no projection_point was frozen (benchmark_only)
        assert claims_stats["mae_ours"] is None, (
            f"Expected mae_ours=None in benchmark_only mode, got {claims_stats['mae_ours']}"
        )

    def test_claims_naive_mae_computable_from_surprise(self):
        """Even in benchmark_only mode, mae_naive_prior accumulates from surprise_vs_naive."""
        row = _claims_scored_row()
        # surprise_vs_naive = 215 - 220 = -5; abs = 5
        sb = _build_scoreboard([row], accrual_start="2026-07-07")
        claims_stats = sb["by_release"]["claims"]
        assert claims_stats["mae_naive_prior"] == pytest.approx(5.0, abs=1e-3)

    def test_non_claims_has_no_block_note(self):
        """CPI scoreboard entry must NOT have a block_note (that's claims-only)."""
        scored = _scored_row(release="cpi_headline")
        scored["actual"] = 0.30
        scored["frozen_projection_point"] = 0.28
        scored["interval_hit"] = True
        scored["skew_hit"] = True
        sb = _build_scoreboard([scored], accrual_start="2026-07-07")
        cpi_stats = sb["by_release"].get("cpi_headline", {})
        assert "block_note" not in cpi_stats, "block_note must not appear for non-claims releases"

    def test_non_claims_has_trailing_3m_not_4w(self):
        """CPI scoreboard entry must use mae_trailing_3m, not mae_trailing_4w."""
        scored = _scored_row(release="cpi_headline")
        scored["actual"] = 0.30
        scored["frozen_projection_point"] = 0.28
        scored["interval_hit"] = True
        scored["skew_hit"] = True
        scored["surprise_vs_trailing"] = 0.05
        sb = _build_scoreboard([scored], accrual_start="2026-07-07")
        cpi_stats = sb["by_release"]["cpi_headline"]
        assert "mae_trailing_3m" in cpi_stats, "mae_trailing_3m must appear for CPI"
        assert "mae_trailing_4w" not in cpi_stats, "mae_trailing_4w must not appear for CPI"


# ============================================================
# 9. CLAIMS LEDGER — weekly period dedup semantics
# ============================================================

class TestClaimsLedger:
    """Verify ledger dedup works for weekly (YYYY-MM-DD) claim periods."""

    def test_claims_weekly_period_dedup(self, tmp_root: Path):
        """Two identical claims projection rows (same period, same asof_night) don't duplicate."""
        ledger_path = tmp_root / "data" / "release_forecast" / "forward_ledger.jsonl"
        row = {
            "row_type": "projection",
            "asof_night": "2026-07-06",
            "release": "claims",
            "period": "2026-07-10",        # Thursday date (weekly period)
            "release_date": "2026-07-10",
            "days_to": 4,
            "projection_point": None,       # benchmark_only
            "benchmark_naive_prior": 220.0,
            "benchmark_trailing_4w": 218.5,
        }
        _append_ledger_rows(ledger_path, [row])
        _append_ledger_rows(ledger_path, [row])  # second run same night
        rows = _load_ledger(ledger_path)
        assert len(rows) == 1, f"Expected 1 row, got {len(rows)}: dedup failed for claims period"

    def test_claims_different_weekly_periods_not_deduped(self, tmp_root: Path):
        """Two different claim weekly periods are separate ledger rows (not deduped)."""
        ledger_path = tmp_root / "data" / "release_forecast" / "forward_ledger.jsonl"
        row1 = {
            "row_type": "projection",
            "asof_night": "2026-07-06",
            "release": "claims",
            "period": "2026-07-10",
            "release_date": "2026-07-10",
        }
        row2 = {
            "row_type": "projection",
            "asof_night": "2026-07-06",
            "release": "claims",
            "period": "2026-07-17",        # different week
            "release_date": "2026-07-17",
        }
        _append_ledger_rows(ledger_path, [row1, row2])
        rows = _load_ledger(ledger_path)
        assert len(rows) == 2, f"Expected 2 rows for different weekly periods, got {len(rows)}"


# ============================================================
# 10. CLAIMS PROJECTION — integration tests (require vintages.parquet)
# ============================================================

_VINTAGES_PATH = Path(__file__).resolve().parents[1] / "data" / "fred_vintage" / "vintages.parquet"
_REPO_ROOT = Path(__file__).resolve().parents[1]
_CLAIMS_INT_MARK = pytest.mark.skipif(
    not _VINTAGES_PATH.exists(),
    reason="data/fred_vintage/vintages.parquet not present; skipping claims integration tests",
)


class TestB1ClaimsProjectionIntegration:
    """Integration: _run_projection for 'claims' returns a valid dict, not None.

    These tests require the committed vintages.parquet (ICSA + IC4WSA series).
    Skipped automatically if the file is absent.
    """

    @_CLAIMS_INT_MARK
    def test_run_projection_claims_returns_dict_not_none(self, tmp_root: Path):
        """_run_projection('claims', ...) must return a dict, not None (B1 crash fix)."""
        asof = date(2026, 7, 7)
        # Use a recent Thursday-date period (the period string for claims is a Thursday date)
        result = _run_projection("claims", asof, _REPO_ROOT, period_str="2026-07-03")
        assert result is not None, (
            "_run_projection('claims') returned None — likely a crash in project_claims"
        )
        assert isinstance(result, dict), f"Expected dict, got {type(result)}"

    @_CLAIMS_INT_MARK
    def test_run_projection_claims_benchmark_set_populated(self, tmp_root: Path):
        """benchmark_set for claims must have naive_prior and trailing_4w as real floats."""
        asof = date(2026, 7, 7)
        result = _run_projection("claims", asof, _REPO_ROOT, period_str="2026-07-03")
        assert result is not None
        bs = result.get("benchmark_set", {})
        assert "naive_prior" in bs, "naive_prior missing from claims benchmark_set"
        assert "trailing_4w" in bs, "trailing_4w missing from claims benchmark_set (must not be trailing_3m)"
        assert "trailing_3m" not in bs, "trailing_3m must not appear in claims benchmark_set"
        # Both should be floats (real ICSA values in thousands)
        assert isinstance(bs["naive_prior"], float), f"naive_prior is {type(bs['naive_prior'])}, expected float"
        assert isinstance(bs["trailing_4w"], float), f"trailing_4w is {type(bs['trailing_4w'])}, expected float"
        # Sanity: ICSA in thousands is typically 200–300k range (i.e., 200.0–300.0 as float)
        assert 100.0 <= bs["naive_prior"] <= 1000.0, f"naive_prior out of plausible range: {bs['naive_prior']}"
        assert 100.0 <= bs["trailing_4w"] <= 1000.0, f"trailing_4w out of plausible range: {bs['trailing_4w']}"

    @_CLAIMS_INT_MARK
    def test_build_upcoming_block_claims_benchmark_only_mode(self, tmp_root: Path):
        """_build_upcoming_block with a claims release emits benchmark_only projection block."""
        # Synthetic upcoming releases list with one claims event
        upcoming_releases = [
            {
                "release_type": "claims",
                "release": "claims",
                "period": "2026-07-10",
                "release_date": "2026-07-10",
                "regime_axis": "growth",
            }
        ]
        policy_backdrop = {
            "fed_stance": None, "gap_bp": None,
            "implied_cuts_12m": None, "next_fomc": None, "guidance_direction": None,
        }
        today = date(2026, 7, 7)
        root = _REPO_ROOT
        block = _build_upcoming_block(today, root, upcoming_releases, policy_backdrop)

        assert len(block) == 1, f"Expected 1 upcoming card, got {len(block)}"
        card = block[0]

        # Projection block must carry benchmark_only mode (§6 kill rule is active)
        assert _CLAIMS_MODE == "benchmark_only", "_CLAIMS_MODE must be benchmark_only"
        proj = card.get("projection", {})
        assert proj.get("mode") == "benchmark_only", (
            f"claims projection.mode must be 'benchmark_only', got {proj.get('mode')!r}"
        )
        assert "reason" in proj, "benchmark_only projection must include reason"

        # Benchmark set must be populated (even in benchmark_only mode, benchmarks are graded)
        bs = card.get("benchmark_set", {})
        assert bs.get("naive_prior") is not None, "naive_prior must be a real value, not null"
        assert bs.get("trailing_4w") is not None, "trailing_4w must be a real value, not null"
        assert "trailing_3m" not in bs, "trailing_3m must not appear in claims benchmark_set"

        # Point/quantiles/confidence must all be null
        assert card.get("confidence") is None, "confidence must be null in benchmark_only mode"
        assert card.get("input_completeness") is None, "input_completeness must be null in benchmark_only mode"


# ============================================================
# 11. CLAIMS CAPTURE PATH — end-to-end integration (FIX-6)
#     Requires committed data/fred_vintage/vintages.parquet
# ============================================================

class TestClaimsCapturePathIntegration:
    """Verify the full claims capture path end-to-end against real committed ICSA vintages.

    Release Thursday 2026-06-11 → ICSA vintage period 2026-06-06 (Sat, Thu−5d)
    ICSA initial print: 229,000 raw persons → 229.0 thousands.

    Asserts:
      - _get_initial_print returns 229000.0 (raw persons from ALFRED)
      - _compute_actual_from_print returns 229.0 (thousands)
      - _check_release_day_capture produces exactly one scored row
      - actual = 229.0 thousands (plausible range)
      - benchmark MAEs computable (surprise_vs_naive populated)
      - our-model fields (our_surprise, interval_hit, skew_hit) are None in benchmark_only mode
      - scoreboard emits a claims entry with mae_naive_prior populated and mae_ours None
    """

    @_CLAIMS_INT_MARK
    def test_get_initial_print_thursday_to_saturday_mapping(self):
        """_get_initial_print must map Thursday period to preceding Saturday for ICSA lookup."""
        # Thursday 2026-06-11 → Saturday 2026-06-06 (−5 days)
        raw = _get_initial_print(
            _REPO_ROOT,
            release_type="claims",
            period_str="2026-06-11",   # Thursday date (as stored in ledger)
            release_date_str="2026-06-11",
        )
        assert raw is not None, (
            "_get_initial_print returned None for claims 2026-06-11. "
            "Likely Thursday→Saturday period mapping failed or ICSA missing in vintages.parquet."
        )
        # Raw value from ALFRED is in persons (expected ~229000.0)
        assert 100_000.0 <= raw <= 1_000_000.0, f"raw_print={raw} out of plausible persons range"
        # Specifically: 2026-06-06 period, realtime_start 2026-06-11, value 229000.0
        assert raw == pytest.approx(229_000.0, abs=1.0), (
            f"Expected ICSA initial print 229000.0 for period 2026-06-06, got {raw}"
        )

    @_CLAIMS_INT_MARK
    def test_compute_actual_claims_returns_thousands(self):
        """_compute_actual_from_print for claims returns raw_print / 1000.0."""
        actual = _compute_actual_from_print(
            "claims", 229_000.0, _REPO_ROOT, "2026-06-11"
        )
        assert actual is not None, "_compute_actual_from_print returned None for claims"
        assert actual == pytest.approx(229.0, abs=0.01), (
            f"Expected 229.0 thousands (229000 / 1000), got {actual}"
        )

    @_CLAIMS_INT_MARK
    def test_full_claims_capture_path_produces_scored_row(self):
        """End-to-end: a benchmark_only claims projection ledger row produces exactly one
        scored row when _check_release_day_capture runs on/after the release date."""
        # Build a synthetic benchmark_only claims projection row for Thu 2026-06-11
        proj_row = {
            "schema": 2,
            "row_type": "projection",
            "asof_night": "2026-06-10",          # T-1 (day before release)
            "release": "claims",
            "period": "2026-06-11",              # Thursday release date (ledger period)
            "release_date": "2026-06-11",
            "projection_mode": "benchmark_only",  # FIX-3: projection_mode written to ledger
            "projection_point": None,             # benchmark_only: null
            "projection_p10": None,
            "projection_p90": None,
            "benchmark_naive_prior": 225.0,      # thousands (synthetic prior)
            "benchmark_trailing_4w": 222.0,
            "benchmark_ar_model": 223.0,
            "benchmark_cleveland": None,
        }
        existing_ledger = [proj_row]

        # Run capture as of the release day (2026-06-11 = Thursday)
        today = date(2026, 6, 11)
        scored_rows = _check_release_day_capture(today, _REPO_ROOT, existing_ledger)

        assert len(scored_rows) == 1, (
            f"Expected exactly 1 scored row for claims 2026-06-11, got {len(scored_rows)}. "
            "FIX-1 (ICSA in _FRED_VINTAGE_SERIES) or FIX-2 (Thursday→Saturday mapping) may be missing."
        )
        sr = scored_rows[0]

        # actual must be thousands-scale and match the known initial print
        assert sr["actual"] is not None, "actual must not be None in scored row"
        assert sr["actual"] == pytest.approx(229.0, abs=0.1), (
            f"Expected actual=229.0 thousands (ICSA 229000 / 1000), got {sr['actual']}"
        )

        # Our-model fields must be None in benchmark_only mode (FIX-3 guard works)
        assert sr.get("our_surprise") is None, (
            f"our_surprise must be None in benchmark_only mode, got {sr.get('our_surprise')}"
        )
        assert sr.get("interval_hit") is None, (
            f"interval_hit must be None in benchmark_only mode, got {sr.get('interval_hit')}"
        )
        assert sr.get("skew_hit") is None, (
            f"skew_hit must be None in benchmark_only mode, got {sr.get('skew_hit')}"
        )

        # Benchmark surprises must be computable
        assert sr.get("surprise_vs_naive") is not None, "surprise_vs_naive must be populated"
        expected_vs_naive = round(229.0 - 225.0, 4)
        assert sr["surprise_vs_naive"] == pytest.approx(expected_vs_naive, abs=0.01), (
            f"Expected surprise_vs_naive={expected_vs_naive}, got {sr['surprise_vs_naive']}"
        )

        # projection_mode must be carried through to scored row
        assert sr.get("projection_mode") == "benchmark_only", (
            f"projection_mode in scored row must be 'benchmark_only', got {sr.get('projection_mode')!r}"
        )

    @_CLAIMS_INT_MARK
    def test_claims_scoreboard_from_real_capture(self):
        """Scoreboard from a real-data claims scored row: mae_naive_prior populated, mae_ours None."""
        proj_row = {
            "schema": 2,
            "row_type": "projection",
            "asof_night": "2026-06-10",
            "release": "claims",
            "period": "2026-06-11",
            "release_date": "2026-06-11",
            "projection_mode": "benchmark_only",
            "projection_point": None,
            "projection_p10": None,
            "projection_p90": None,
            "benchmark_naive_prior": 225.0,
            "benchmark_trailing_4w": 222.0,
            "benchmark_ar_model": 223.0,
            "benchmark_cleveland": None,
        }
        today = date(2026, 6, 11)
        scored_rows = _check_release_day_capture(today, _REPO_ROOT, [proj_row])
        assert len(scored_rows) == 1, "Expected 1 scored row (prerequisite)"

        sb = _build_scoreboard(scored_rows, accrual_start="2026-01-01")
        claims_stats = sb["by_release"].get("claims")
        assert claims_stats is not None, "claims entry missing from scoreboard"
        assert claims_stats["n"] == 1, f"Expected n=1, got {claims_stats['n']}"
        # mae_ours must be None (no projection point in benchmark_only)
        assert claims_stats["mae_ours"] is None, (
            f"mae_ours must be None in benchmark_only mode, got {claims_stats['mae_ours']}"
        )
        # mae_naive_prior must be populated (|229.0 - 225.0| = 4.0)
        assert claims_stats["mae_naive_prior"] is not None, "mae_naive_prior must be populated"
        assert claims_stats["mae_naive_prior"] == pytest.approx(4.0, abs=0.1), (
            f"Expected mae_naive_prior=4.0, got {claims_stats['mae_naive_prior']}"
        )
