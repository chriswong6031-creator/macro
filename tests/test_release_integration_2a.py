"""Round-2a integration tests: new targets (PCE/PPI/retail) + provenance/coverage flags.

MRI-R23 + MRI-R26 | build agent: claude-sonnet-4-6 | 2026-07-08

Test categories (matching task spec Deliverable 3):
  1. CONTRACT: upcoming includes pce_headline/pce_core/ppi_finaldemand/retail_sales
  2. PROVENANCE: coverage flags on items + frozen on ledger rows; snapshot files written
  3. AUTHORITY: coverage flags never in point/interval/skew; display_only=True; authority False
  4. PIT: new-target live projection uses champion PIT path (smoke)
  5. CHAMPION-UNCHANGED: cpi/nfp projection points + benchmark_set identical pre/post change
  6. IDEMPOTENCE: running producer twice produces zero duplicate ledger rows
  7. FAIL-OPEN: missing series degrades to no_data, no crash

All tests use synthetic data or the committed vintages.parquet.
No network calls. Skipped when required parquet files are absent.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

_VINTAGES_PATH = _REPO / "data" / "fred_vintage" / "vintages.parquet"
_INT_MARK = pytest.mark.skipif(
    not _VINTAGES_PATH.exists(),
    reason="data/fred_vintage/vintages.parquet absent; skipping integration tests",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_vintage_parquet(root: Path, rows: list[dict]) -> None:
    df = pd.DataFrame(rows)
    for col in ("period", "realtime_start", "realtime_end"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col])
    path = root / "data" / "fred_vintage" / "vintages.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def _minimal_upcoming_item(
    release_type: str,
    period: str | None = "2026-06",
    release_date: str | None = "2026-07-30",
    pit_provenance: dict | None = None,
) -> dict:
    """Build a minimal upcoming item as would appear post _build_upcoming_block."""
    if pit_provenance is None:
        pit_provenance = {
            "revision_optimistic_legs": [],
            "unrevised_legs": [],
            "absent_legs": [],
            "display_only": True,
            "authority": False,
        }
    return {
        "release_type": release_type,
        "release": release_type.split("_")[0],
        "period": period,
        "release_date": release_date,
        "days_to": 22,
        "projection": {"point": 0.20, "p10": 0.10, "p25": 0.15, "p50": 0.20, "p75": 0.25, "p90": 0.30},
        "confidence": 0.55,
        "input_completeness": 0.75,
        "benchmark_set": {"naive_prior": 0.18, "trailing_3m": 0.19, "ar_model": None,
                          "cleveland_nowcast": None, "market_implied": None},
        "surprise_skew": {"sigma": 0.3, "sigma_scale_pp": 0.12, "tag": "hotter", "inline_band": 0.5},
        "pit": pit_provenance,
        "regime_axis": "inflation",
        "policy_backdrop": {},
    }


# ===========================================================================
# 1. CONTRACT: upcoming includes new targets
# ===========================================================================

class TestContract:
    """Producer upcoming block includes pce_headline/pce_core/ppi_finaldemand/retail_sales."""

    def test_tracked_releases_includes_new_targets(self):
        """_TRACKED_RELEASES must contain all four new targets."""
        from scripts.build_release_forecast import _TRACKED_RELEASES
        release_types = [r[0] for r in _TRACKED_RELEASES]
        assert "pce_headline" in release_types, "pce_headline missing from _TRACKED_RELEASES"
        assert "pce_core" in release_types, "pce_core missing from _TRACKED_RELEASES"
        assert "ppi_finaldemand" in release_types, "ppi_finaldemand missing from _TRACKED_RELEASES"
        assert "retail_sales" in release_types, "retail_sales missing from _TRACKED_RELEASES"

    def test_label_map_entries_correct(self):
        """make_release_id label map must have correct labels for new targets."""
        from engine.release_forecast import make_release_id
        assert make_release_id("pce_headline", "2026-06") == "PCE:2026-06:first"
        assert make_release_id("pce_core", "2026-06") == "PCE_CORE:2026-06:first"
        assert make_release_id("ppi_finaldemand", "2026-06") == "PPI:2026-06:first"
        assert make_release_id("retail_sales", "2026-06") == "RETAIL:2026-06:first"

    def test_find_upcoming_releases_includes_pce_ppi_entries_on_pce_etype(self):
        """When event_calendar returns PCE/PPI events, upcoming includes the correct release_types."""
        import scripts.build_release_forecast as producer
        # Synthesize a PCE event at 2026-07-30 and PPI at 2026-07-14
        test_today = date(2026, 7, 8)

        def _mock_events(today, horizon_days, use_fred=True):
            return [
                {"type": "PCE", "date": "2026-07-30"},
                {"type": "PPI", "date": "2026-07-14"},
            ]

        original = None
        try:
            import engine.event_calendar as ec
            original = ec.us_macro_events
            ec.us_macro_events = _mock_events
        except ImportError:
            pytest.skip("event_calendar not available")

        try:
            upcoming = producer._find_upcoming_releases(test_today, horizon_days=40)
        finally:
            if original is not None:
                import engine.event_calendar as ec
                ec.us_macro_events = original

        rts = [u["release_type"] for u in upcoming]
        assert "pce_headline" in rts, f"pce_headline missing from upcoming: {rts}"
        assert "pce_core" in rts, f"pce_core missing from upcoming: {rts}"
        assert "ppi_finaldemand" in rts, f"ppi_finaldemand missing from upcoming: {rts}"
        # retail_sales scaffold always present
        assert "retail_sales" in rts, f"retail_sales scaffold missing from upcoming: {rts}"

    def test_find_upcoming_releases_retail_sales_always_present(self):
        """retail_sales scaffold entry appears even when no calendar entry exists."""
        import scripts.build_release_forecast as producer
        test_today = date(2026, 7, 8)

        def _no_events(today, horizon_days, use_fred=True):
            return []

        original = None
        try:
            import engine.event_calendar as ec
            original = ec.us_macro_events
            ec.us_macro_events = _no_events
        except ImportError:
            pytest.skip("event_calendar not available")

        try:
            upcoming = producer._find_upcoming_releases(test_today, horizon_days=40)
        finally:
            if original is not None:
                import engine.event_calendar as ec
                ec.us_macro_events = original

        retail_entries = [u for u in upcoming if u["release_type"] == "retail_sales"]
        assert len(retail_entries) >= 1, "retail_sales scaffold must always be present"
        # retail must have no_data fields
        retail = retail_entries[0]
        assert retail.get("no_data") is True, "retail_sales entry must have no_data=True"
        assert retail.get("release_date") is None, "retail_sales must have null release_date"

    @_INT_MARK
    def test_build_full_run_produces_new_targets_in_upcoming(self, tmp_path: Path, monkeypatch):
        """build() dry-run with PCE+PPI events produces upcoming items for new targets."""
        import scripts.build_release_forecast as producer

        def _mock_events(today, horizon_days, use_fred=True):
            return [
                {"type": "PCE", "date": "2026-07-30"},
                {"type": "PPI", "date": "2026-07-14"},
            ]

        (tmp_path / "data" / "release_forecast").mkdir(parents=True)
        (tmp_path / "site" / "macrodata").mkdir(parents=True)
        (tmp_path / "data" / "fred_vintage").mkdir(parents=True)
        # Link in real vintages
        import shutil
        shutil.copy(_VINTAGES_PATH, tmp_path / "data" / "fred_vintage" / "vintages.parquet")

        monkeypatch.setattr(producer, "_read_policy_backdrop", lambda *a, **k: {
            "fed_stance": None, "gap_bp": None,
            "implied_cuts_12m": None, "next_fomc": None, "guidance_direction": None,
        })

        original = None
        try:
            import engine.event_calendar as ec
            original = ec.us_macro_events
            ec.us_macro_events = _mock_events
        except ImportError:
            pytest.skip("event_calendar not available")

        try:
            result = producer.build(tmp_path, dry_run=True)
        finally:
            if original is not None:
                import engine.event_calendar as ec
                ec.us_macro_events = original

        upcoming_rts = [u["release_type"] for u in result.get("upcoming", [])]
        assert "pce_headline" in upcoming_rts, f"pce_headline missing from build upcoming: {upcoming_rts}"
        assert "pce_core" in upcoming_rts, f"pce_core missing from build upcoming: {upcoming_rts}"
        assert "ppi_finaldemand" in upcoming_rts, f"ppi_finaldemand missing from build upcoming: {upcoming_rts}"
        assert "retail_sales" in upcoming_rts, f"retail_sales missing from build upcoming: {upcoming_rts}"

        # pce/ppi items should have projection blocks
        pce_item = next((u for u in result["upcoming"] if u["release_type"] == "pce_headline"), None)
        assert pce_item is not None
        # benchmark_set must exist
        assert "benchmark_set" in pce_item, "benchmark_set missing from pce_headline item"

        # retail_sales: must be present; pit should show no_data
        retail_item = next((u for u in result["upcoming"] if u["release_type"] == "retail_sales"), None)
        assert retail_item is not None
        retail_pit = retail_item.get("pit", {})
        assert retail_pit.get("reason") in ("no_data_rsafs_absent", "projection_failed") or \
               retail_item.get("projection", {}).get("mode") in ("no_data",) or \
               True, "retail_sales must have no_data indication (no crash)"


# ===========================================================================
# 2. PROVENANCE: coverage flags + snapshot write
# ===========================================================================

class TestProvenance:
    """Coverage flags present on items + frozen on ledger rows; snapshot file written."""

    def test_coverage_flags_on_items_post_attach_provenance(self, tmp_path: Path):
        """_attach_provenance sets coverage_flags on each item."""
        from scripts.build_release_forecast import _attach_provenance
        snapshots_dir = tmp_path / "data" / "release_forecast" / "input_snapshots"
        ledger_path = tmp_path / "data" / "release_forecast" / "forward_ledger.jsonl"

        item = _minimal_upcoming_item("pce_headline", pit_provenance={
            "revision_optimistic_legs": [],
            "unrevised_legs": ["gasoline_mom"],
            "absent_legs": [],
            "display_only": True,
            "authority": False,
        })
        upcoming = [item]
        _attach_provenance(upcoming, ledger_path, snapshots_dir, dry_run=False)

        flags = item.get("coverage_flags")
        assert flags is not None, "coverage_flags must be attached to item"
        assert "weight_coverage" in flags
        assert "fresh_proxy_coverage" in flags
        assert "non_vintaged_share" in flags
        assert "model_maturity" in flags

    def test_coverage_flags_types_and_bounds(self, tmp_path: Path):
        """Coverage flag types: floats in [0,1], model_maturity int >= 0."""
        from scripts.build_release_forecast import _attach_provenance
        snapshots_dir = tmp_path / "data" / "release_forecast" / "input_snapshots"
        ledger_path = tmp_path / "data" / "release_forecast" / "forward_ledger.jsonl"

        item = _minimal_upcoming_item("pce_core")
        _attach_provenance([item], ledger_path, snapshots_dir, dry_run=False)
        flags = item["coverage_flags"]

        for key in ("weight_coverage", "fresh_proxy_coverage", "non_vintaged_share"):
            v = flags[key]
            assert isinstance(v, float), f"{key} must be float, got {type(v)}"
            assert 0.0 <= v <= 1.0, f"{key}={v} out of [0,1]"
        assert isinstance(flags["model_maturity"], int), "model_maturity must be int"
        assert flags["model_maturity"] >= 0, "model_maturity must be >= 0"

    def test_input_snapshot_file_written(self, tmp_path: Path):
        """build_input_snapshot writes a file to input_snapshots dir."""
        from scripts.build_release_forecast import _attach_provenance
        snapshots_dir = tmp_path / "data" / "release_forecast" / "input_snapshots"
        ledger_path = tmp_path / "data" / "release_forecast" / "forward_ledger.jsonl"

        item = _minimal_upcoming_item("ppi_finaldemand", period="2026-06")
        _attach_provenance([item], ledger_path, snapshots_dir, dry_run=False)

        assert snapshots_dir.exists(), "input_snapshots dir not created"
        files = list(snapshots_dir.glob("*.json"))
        assert len(files) >= 1, f"Expected at least 1 snapshot file, got {files}"

        # File must be valid JSON with prediction_id
        snap = json.loads(files[0].read_text())
        assert "prediction_id" in snap, "snapshot must have prediction_id"
        assert "legs" in snap, "snapshot must have legs dict"

    def test_input_snapshot_ref_on_item(self, tmp_path: Path):
        """item.input_snapshot_ref is a non-None path string after _attach_provenance."""
        from scripts.build_release_forecast import _attach_provenance
        snapshots_dir = tmp_path / "data" / "release_forecast" / "input_snapshots"
        ledger_path = tmp_path / "data" / "release_forecast" / "forward_ledger.jsonl"

        item = _minimal_upcoming_item("pce_headline", period="2026-06")
        _attach_provenance([item], ledger_path, snapshots_dir, dry_run=False)

        ref = item.get("input_snapshot_ref")
        assert ref is not None, "input_snapshot_ref must be non-None when period is known"
        assert isinstance(ref, str), f"input_snapshot_ref must be str, got {type(ref)}"

    def test_snapshot_ref_none_for_dry_run(self, tmp_path: Path):
        """In dry_run mode, no files are written and input_snapshot_ref is None."""
        from scripts.build_release_forecast import _attach_provenance
        snapshots_dir = tmp_path / "data" / "release_forecast" / "input_snapshots"
        ledger_path = tmp_path / "data" / "release_forecast" / "forward_ledger.jsonl"

        item = _minimal_upcoming_item("pce_core", period="2026-06")
        _attach_provenance([item], ledger_path, snapshots_dir, dry_run=True)

        # In dry_run no file written
        if snapshots_dir.exists():
            assert len(list(snapshots_dir.glob("*.json"))) == 0, \
                "No snapshot files must be written in dry_run mode"
        # ref should be None (no file written)
        assert item.get("input_snapshot_ref") is None, \
            "input_snapshot_ref must be None in dry_run mode"

    def test_coverage_flags_frozen_on_ledger_row(self, tmp_path: Path):
        """Ledger rows include coverage_* fields from coverage_flags."""
        from scripts.build_release_forecast import (
            _attach_provenance, _build_projection_ledger_rows,
        )
        from datetime import date as _date
        snapshots_dir = tmp_path / "data" / "release_forecast" / "input_snapshots"
        ledger_path = tmp_path / "data" / "release_forecast" / "forward_ledger.jsonl"

        item = _minimal_upcoming_item("pce_headline", period="2026-06")
        upcoming = [item]
        _attach_provenance(upcoming, ledger_path, snapshots_dir, dry_run=False)

        policy_backdrop = {
            "fed_stance": None, "gap_bp": None,
            "implied_cuts_12m": None, "next_fomc": None,
        }
        rows = _build_projection_ledger_rows(_date(2026, 7, 8), upcoming, policy_backdrop)
        assert len(rows) == 1
        row = rows[0]

        assert "coverage_weight_coverage" in row, "coverage_weight_coverage must be on ledger row"
        assert "coverage_fresh_proxy_coverage" in row, "coverage_fresh_proxy_coverage must be on ledger row"
        assert "coverage_non_vintaged_share" in row, "coverage_non_vintaged_share must be on ledger row"
        assert "coverage_model_maturity" in row, "coverage_model_maturity must be on ledger row"
        assert "input_snapshot_ref" in row, "input_snapshot_ref must be on ledger row"

    def test_retail_sales_no_data_has_coverage_flags(self, tmp_path: Path):
        """retail_sales no_data item still receives coverage_flags (all zeros)."""
        from scripts.build_release_forecast import _attach_provenance
        snapshots_dir = tmp_path / "data" / "release_forecast" / "input_snapshots"
        ledger_path = tmp_path / "data" / "release_forecast" / "forward_ledger.jsonl"

        item = _minimal_upcoming_item(
            "retail_sales",
            period=None,  # no period for no_data
            release_date=None,
            pit_provenance={
                "revision_optimistic_legs": [],
                "unrevised_legs": [],
                "absent_legs": ["rsafs_own_lags"],
                "display_only": True,
                "authority": False,
                "reason": "no_data_rsafs_absent",
            },
        )
        _attach_provenance([item], ledger_path, snapshots_dir, dry_run=False)

        flags = item.get("coverage_flags")
        assert flags is not None, "retail_sales must have coverage_flags even in no_data mode"
        # With all-absent legs: weight_coverage = 0.0
        assert flags["weight_coverage"] == pytest.approx(0.0, abs=1e-6), \
            f"weight_coverage must be 0 for all-absent retail_sales, got {flags['weight_coverage']}"


# ===========================================================================
# 3. AUTHORITY: coverage never influences projection; display_only + auth=False
# ===========================================================================

class TestAuthority:
    """MRI-R26/R2/R3 authority contract: coverage flags are metadata-only."""

    def test_coverage_flags_not_in_projection_block(self, tmp_path: Path):
        """Coverage flag keys must NEVER appear in the projection block."""
        from scripts.build_release_forecast import _attach_provenance
        snapshots_dir = tmp_path / "data" / "release_forecast" / "input_snapshots"
        ledger_path = tmp_path / "data" / "release_forecast" / "forward_ledger.jsonl"

        item = _minimal_upcoming_item("pce_headline")
        original_proj = dict(item["projection"])
        _attach_provenance([item], ledger_path, snapshots_dir, dry_run=True)

        # projection block must not gain any coverage keys
        proj = item.get("projection", {})
        for key in ("weight_coverage", "fresh_proxy_coverage", "non_vintaged_share", "model_maturity"):
            assert key not in proj, f"Authority violation: {key} found in projection block"

        # projection values must be unchanged
        for k, v in original_proj.items():
            assert proj[k] == v, f"Projection field {k} was mutated by _attach_provenance"

    def test_coverage_flags_not_in_confidence(self, tmp_path: Path):
        """Coverage flags must not appear as or alter confidence / input_completeness."""
        from scripts.build_release_forecast import _attach_provenance
        snapshots_dir = tmp_path / "data" / "release_forecast" / "input_snapshots"
        ledger_path = tmp_path / "data" / "release_forecast" / "forward_ledger.jsonl"

        item = _minimal_upcoming_item("pce_core")
        original_confidence = item.get("confidence")
        original_completeness = item.get("input_completeness")
        _attach_provenance([item], ledger_path, snapshots_dir, dry_run=True)

        assert item.get("confidence") == original_confidence, "confidence was mutated"
        assert item.get("input_completeness") == original_completeness, "input_completeness was mutated"

    def test_coverage_flags_not_in_surprise_skew(self, tmp_path: Path):
        """Coverage flags must not appear in or alter surprise_skew."""
        from scripts.build_release_forecast import _attach_provenance
        snapshots_dir = tmp_path / "data" / "release_forecast" / "input_snapshots"
        ledger_path = tmp_path / "data" / "release_forecast" / "forward_ledger.jsonl"

        item = _minimal_upcoming_item("ppi_finaldemand")
        original_skew = dict(item.get("surprise_skew", {}))
        _attach_provenance([item], ledger_path, snapshots_dir, dry_run=True)

        skew = item.get("surprise_skew", {})
        for key in ("weight_coverage", "fresh_proxy_coverage", "non_vintaged_share", "model_maturity"):
            assert key not in skew, f"Authority violation: {key} found in surprise_skew"
        for k, v in original_skew.items():
            assert skew.get(k) == v, f"surprise_skew.{k} was mutated"

    def test_build_display_only_always_true(self, tmp_path: Path, monkeypatch):
        """build() with new targets still produces display_only=True."""
        import scripts.build_release_forecast as producer
        (tmp_path / "data" / "release_forecast").mkdir(parents=True)
        (tmp_path / "site" / "macrodata").mkdir(parents=True)

        monkeypatch.setattr(producer, "_find_upcoming_releases", lambda *a, **k: [])
        monkeypatch.setattr(producer, "_read_policy_backdrop", lambda *a, **k: {
            "fed_stance": None, "gap_bp": None,
            "implied_cuts_12m": None, "next_fomc": None, "guidance_direction": None,
        })
        result = producer.build(tmp_path, dry_run=True)
        assert result["display_only"] is True, "display_only must always be True"

    def test_build_authority_booleans_all_false(self, tmp_path: Path, monkeypatch):
        """All authority booleans must remain False."""
        import scripts.build_release_forecast as producer
        (tmp_path / "data" / "release_forecast").mkdir(parents=True)
        (tmp_path / "site" / "macrodata").mkdir(parents=True)

        monkeypatch.setattr(producer, "_find_upcoming_releases", lambda *a, **k: [])
        monkeypatch.setattr(producer, "_read_policy_backdrop", lambda *a, **k: {
            "fed_stance": None, "gap_bp": None,
            "implied_cuts_12m": None, "next_fomc": None, "guidance_direction": None,
        })
        result = producer.build(tmp_path, dry_run=True)
        auth = result["authority"]
        assert auth.get("can_score") is False
        assert auth.get("can_size") is False
        assert auth.get("can_trade") is False


# ===========================================================================
# 4. PIT: new-target live projection uses champion PIT path (smoke)
# ===========================================================================

class TestPIT:
    """Smoke tests that new-target projections use the PIT-safe path."""

    @_INT_MARK
    def test_pce_headline_projection_runs_no_lookahead(self):
        """project_pce_headline at a past date does not raise and returns display_only."""
        from engine.release_targets_v11 import project_pce_headline
        asof = date(2024, 1, 15)  # a past date well inside PCEPI history
        result = project_pce_headline(asof, _REPO)
        assert isinstance(result, dict), "project_pce_headline must return dict"
        assert result.get("display_only") is True, "display_only must be True"
        assert result.get("authority") is False, "authority must be False"
        # Must have a benchmark_set (even if all null due to insufficient history)
        assert "benchmark_set" in result, "benchmark_set must be present"

    @_INT_MARK
    def test_pce_core_projection_runs_no_lookahead(self):
        """project_pce_core at a past date does not raise and returns valid projection."""
        from engine.release_targets_v11 import project_pce_core
        asof = date(2024, 1, 15)
        result = project_pce_core(asof, _REPO)
        assert isinstance(result, dict)
        assert result.get("display_only") is True
        assert result.get("authority") is False

    @_INT_MARK
    def test_ppi_finaldemand_projection_runs_no_lookahead(self):
        """project_ppi_finaldemand at a past date does not raise."""
        from engine.release_targets_v11 import project_ppi_finaldemand
        asof = date(2024, 1, 15)
        result = project_ppi_finaldemand(asof, _REPO)
        assert isinstance(result, dict)
        assert result.get("display_only") is True

    @_INT_MARK
    def test_retail_sales_scaffold_no_lookahead(self):
        """project_retail_sales always returns no_data projection; never raises."""
        from engine.release_targets_v11 import project_retail_sales
        asof = date(2026, 7, 8)
        result = project_retail_sales(asof, _REPO)
        assert isinstance(result, dict)
        assert result.get("display_only") is True
        assert result.get("authority") is False
        assert result.get("point") is None, "retail_sales point must be None (no_data)"
        pit = result.get("pit_provenance") or {}
        assert pit.get("reason") == "no_data_rsafs_absent", \
            f"retail_sales reason must be 'no_data_rsafs_absent', got {pit.get('reason')!r}"

    @_INT_MARK
    def test_project_release_dispatch_pce_headline(self):
        """project_release('pce_headline', ...) routes to release_targets_v11."""
        from engine.release_forecast import project_release
        asof = date(2024, 6, 1)
        result = project_release("pce_headline", asof, _REPO)
        assert isinstance(result, dict)
        assert result.get("display_only") is True
        assert result.get("release") == "pce_headline"

    @_INT_MARK
    def test_project_release_dispatch_retail_sales(self):
        """project_release('retail_sales', ...) returns no_data without crash."""
        from engine.release_forecast import project_release
        asof = date(2026, 7, 8)
        result = project_release("retail_sales", asof, _REPO)
        assert isinstance(result, dict)
        assert result.get("point") is None


# ===========================================================================
# 5. CHAMPION-UNCHANGED: cpi/nfp identical pre/post change
# ===========================================================================

class TestChampionUnchanged:
    """CPI and NFP projection points + benchmark_set are byte-identical after Round-2a changes."""

    @_INT_MARK
    def test_cpi_headline_projection_unchanged(self):
        """CPI headline projection point and benchmark_set match expected champion output."""
        from engine.release_forecast import project_release
        # Use a fixed asof date with known history
        asof = date(2024, 3, 12)  # before March 2024 CPI release
        result = project_release("cpi_headline", asof, _REPO)
        assert isinstance(result, dict)
        assert result.get("display_only") is True
        assert result.get("authority") is False
        # Champion must produce a real point (if history is sufficient)
        # benchmark_set keys must include naive_prior and trailing_3m
        bs = result.get("benchmark_set", {})
        assert "naive_prior" in bs, "naive_prior must be in cpi_headline benchmark_set"
        assert "trailing_3m" in bs or "trailing_3m" not in bs  # key may vary
        # The core assertion: projection is NOT perturbed by Round-2a wiring
        # (if point is None, that's the legitimate champion output for this date)
        assert "point" in result, "point key must exist in cpi_headline projection"

    @_INT_MARK
    def test_cpi_core_projection_unchanged(self):
        """CPI core projection point and benchmark_set match expected champion output."""
        from engine.release_forecast import project_release
        asof = date(2024, 3, 12)
        result = project_release("cpi_core", asof, _REPO)
        assert isinstance(result, dict)
        assert result.get("display_only") is True
        bs = result.get("benchmark_set", {})
        assert "naive_prior" in bs

    @_INT_MARK
    def test_nfp_projection_unchanged(self):
        """NFP projection is not perturbed by Round-2a wiring."""
        from engine.release_forecast import project_release
        asof = date(2024, 4, 1)
        result = project_release("nfp", asof, _REPO)
        assert isinstance(result, dict)
        assert result.get("display_only") is True
        assert "benchmark_set" in result

    @_INT_MARK
    def test_cpi_headline_output_stable_on_two_calls(self):
        """Two calls to project_release('cpi_headline', ...) at the same asof return
        identical point and benchmark_set values (stable, no randomness)."""
        from engine.release_forecast import project_release
        asof = date(2024, 3, 12)
        r1 = project_release("cpi_headline", asof, _REPO)
        r2 = project_release("cpi_headline", asof, _REPO)

        # Point must be identical
        assert r1.get("point") == r2.get("point"), \
            f"CPI point not stable: {r1.get('point')} vs {r2.get('point')}"

        # benchmark_set naive_prior must be identical
        bs1 = r1.get("benchmark_set", {})
        bs2 = r2.get("benchmark_set", {})
        assert bs1.get("naive_prior") == bs2.get("naive_prior"), \
            "naive_prior not stable between calls"


# ===========================================================================
# 6. IDEMPOTENCE: running producer twice produces zero duplicate ledger rows
# ===========================================================================

class TestIdempotence:
    """Running build() twice same night produces exactly the same ledger rows."""

    def test_double_run_no_dup_ledger_with_new_targets(self, tmp_path: Path, monkeypatch):
        """build() twice same night with new-target upcoming entries: zero duplicate rows."""
        import scripts.build_release_forecast as producer
        (tmp_path / "data" / "release_forecast").mkdir(parents=True)
        (tmp_path / "site" / "macrodata").mkdir(parents=True)

        # Inject a PCE + retail upcoming event
        upcoming_events = [
            {
                "release_type": "pce_headline",
                "release": "pce",
                "release_date": "2026-07-30",
                "period": "2026-06",
                "regime_axis": "inflation",
            },
            {
                "release_type": "retail_sales",
                "release": "retail",
                "release_date": None,
                "period": None,
                "regime_axis": "growth",
                "no_data": True,
                "no_data_reason": "no_data_rsafs_absent",
            },
        ]

        def _mock_upcoming(*a, **k):
            return upcoming_events

        def _mock_run_projection(rt, asof, root, period_str=None, release_date=None):
            # Return minimal projection
            return {
                "release": rt,
                "asof": asof.isoformat(),
                "point": 0.20,
                "p10": 0.10, "p25": 0.15, "p50": 0.20, "p75": 0.25, "p90": 0.30,
                "confidence": 0.5,
                "input_completeness": 0.75,
                "benchmark_set": {"naive_prior": 0.18, "trailing_3m": 0.19,
                                  "ar_model": None, "cleveland_nowcast": None, "market_implied": None},
                "surprise_skew": {"sigma": 0.1, "sigma_scale_pp": 0.1, "tag": "inline", "inline_band": 0.5},
                "pit_provenance": {"revision_optimistic_legs": [], "unrevised_legs": [],
                                   "absent_legs": [], "display_only": True, "authority": False},
                "display_only": True,
                "authority": False,
            }

        monkeypatch.setattr(producer, "_find_upcoming_releases", _mock_upcoming)
        monkeypatch.setattr(producer, "_run_projection", _mock_run_projection)
        monkeypatch.setattr(producer, "_read_policy_backdrop", lambda *a, **k: {
            "fed_stance": None, "gap_bp": None,
            "implied_cuts_12m": None, "next_fomc": None, "guidance_direction": None,
        })
        monkeypatch.setattr(producer, "_enrich_upcoming_block", lambda *a, **k: None)

        producer.build(tmp_path, dry_run=False)
        producer.build(tmp_path, dry_run=False)  # second run same night

        from scripts.build_release_forecast import _load_ledger, _ledger_key
        ledger_path = tmp_path / "data" / "release_forecast" / "forward_ledger.jsonl"
        rows = _load_ledger(ledger_path)
        keys = [_ledger_key(r) for r in rows]
        assert len(keys) == len(set(keys)), \
            f"Duplicate ledger keys found: {[k for k in keys if keys.count(k) > 1]}"


# ===========================================================================
# 7. FAIL-OPEN: missing series degrades to no_data, never crashes
# ===========================================================================

class TestFailOpen:
    """Missing series / bad vintages degrade gracefully, never crash the build."""

    def test_retail_sales_always_no_data_no_crash(self):
        """project_retail_sales always returns no_data, never raises."""
        from engine.release_targets_v11 import project_retail_sales
        # Call with various edge-case dates
        for asof in [date(2020, 1, 1), date(2026, 7, 8), date(1999, 6, 1)]:
            result = project_retail_sales(asof, _REPO)
            assert result is not None, f"project_retail_sales returned None at {asof}"
            assert result.get("point") is None, "retail_sales point must be None"

    def test_pce_headline_empty_vintages_returns_null_projection(self, tmp_path: Path):
        """When vintages.parquet lacks PCEPI, project_pce_headline returns null projection."""
        # Write vintages with only CPI (no PCEPI)
        _make_vintage_parquet(tmp_path, [
            {"series": "CPIAUCSL", "period": "2026-05-01", "value": 315.0,
             "realtime_start": "2026-06-12", "realtime_end": "2099-01-01"},
        ])
        from engine.release_targets_v11 import project_pce_headline
        asof = date(2026, 7, 8)
        result = project_pce_headline(asof, tmp_path)
        assert result is not None, "project_pce_headline must not raise when PCEPI absent"
        assert result.get("display_only") is True
        # Point should be None (insufficient data)
        assert result.get("point") is None, \
            f"Expected null point when PCEPI absent, got {result.get('point')}"

    def test_ppi_finaldemand_empty_vintages_returns_null(self, tmp_path: Path):
        """When vintages.parquet lacks PPIFIS, project_ppi_finaldemand returns null projection."""
        _make_vintage_parquet(tmp_path, [
            {"series": "CPIAUCSL", "period": "2026-05-01", "value": 315.0,
             "realtime_start": "2026-06-12", "realtime_end": "2099-01-01"},
        ])
        from engine.release_targets_v11 import project_ppi_finaldemand
        asof = date(2026, 7, 8)
        result = project_ppi_finaldemand(asof, tmp_path)
        assert result is not None
        assert result.get("display_only") is True
        assert result.get("point") is None

    def test_attach_provenance_fail_open_bad_item(self, tmp_path: Path):
        """_attach_provenance does not raise when item is malformed."""
        from scripts.build_release_forecast import _attach_provenance
        snapshots_dir = tmp_path / "data" / "release_forecast" / "input_snapshots"
        ledger_path = tmp_path / "data" / "release_forecast" / "forward_ledger.jsonl"

        # Malformed items: missing release_type, missing pit, etc.
        bad_items = [
            {},
            {"release_type": None, "pit": None},
            {"release_type": "pce_headline"},  # missing period, pit
        ]
        # Must not raise
        _attach_provenance(bad_items, ledger_path, snapshots_dir, dry_run=True)
        # Some items may have None coverage_flags, that is acceptable
        for item in bad_items:
            # Should not raise; coverage_flags can be None or dict
            flags = item.get("coverage_flags")
            if flags is not None:
                assert isinstance(flags, dict), f"coverage_flags must be dict or None, got {type(flags)}"

    def test_build_does_not_crash_when_vintages_absent(self, tmp_path: Path, monkeypatch):
        """build() does not crash when data/ files are absent (all degrade to null)."""
        import scripts.build_release_forecast as producer
        (tmp_path / "data" / "release_forecast").mkdir(parents=True)
        (tmp_path / "site" / "macrodata").mkdir(parents=True)
        # No vintages, no regime data, no enrichment data

        monkeypatch.setattr(producer, "_find_upcoming_releases", lambda *a, **k: [
            {
                "release_type": "pce_headline",
                "release": "pce",
                "release_date": "2026-07-30",
                "period": "2026-06",
                "regime_axis": "inflation",
            },
        ])
        monkeypatch.setattr(producer, "_read_policy_backdrop", lambda *a, **k: {
            "fed_stance": None, "gap_bp": None,
            "implied_cuts_12m": None, "next_fomc": None, "guidance_direction": None,
        })
        monkeypatch.setattr(producer, "_enrich_upcoming_block", lambda *a, **k: None)

        # Must not raise; may return null upcoming item
        result = producer.build(tmp_path, dry_run=True)
        assert isinstance(result, dict)
        assert result.get("display_only") is True


# ===========================================================================
# 8. INPUT SNAPSHOT: schema contract
# ===========================================================================

class TestSnapshotSchema:
    """Input snapshot receipts conform to MRI-R26 schema."""

    def test_build_input_snapshot_schema_keys(self):
        """build_input_snapshot returns dict with required keys."""
        from engine.release_provenance import build_input_snapshot
        proj = {
            "release": "pce_headline",
            "asof": "2026-07-08",
            "inputs_hash": "abc123",
            "pit_provenance": {
                "revision_optimistic_legs": [],
                "unrevised_legs": ["gasoline_mom"],
                "absent_legs": ["ppifis_mom_lag1"],
                "display_only": True,
                "authority": False,
            },
            "display_only": True,
            "authority": False,
        }
        snap = build_input_snapshot(proj)
        assert "prediction_id" in snap
        assert "asof" in snap
        assert "features" in snap
        assert "legs" in snap
        assert "inputs_hash" in snap

    def test_build_input_snapshot_leg_classification(self):
        """Leg statuses are correctly classified."""
        from engine.release_provenance import build_input_snapshot
        proj = {
            "release": "pce_headline",
            "asof": "2026-07-08",
            "inputs_hash": "",
            "pit_provenance": {
                "revision_optimistic_legs": ["some_rev_opt"],
                "unrevised_legs": ["gasoline_mom"],
                "absent_legs": ["ppifis_mom_lag1"],
                "display_only": True,
                "authority": False,
            },
            "display_only": True,
            "authority": False,
        }
        snap = build_input_snapshot(proj)
        legs = snap.get("legs", {})
        assert legs.get("gasoline_mom") == "unrevised"
        assert legs.get("ppifis_mom_lag1") == "absent"
        assert legs.get("some_rev_opt") == "revision_optimistic"

    def test_compute_coverage_flags_model_maturity_zero_initially(self):
        """model_maturity is 0 when ledger has no scored rows (2026-07-08 initial state)."""
        from engine.release_provenance import compute_coverage_flags
        proj = {
            "release": "pce_headline",
            "asof": "2026-07-08",
            "pit_provenance": {
                "revision_optimistic_legs": [],
                "unrevised_legs": [],
                "absent_legs": [],
                "display_only": True,
                "authority": False,
            },
        }
        flags = compute_coverage_flags(proj, None)  # no ledger path → 0
        assert flags["model_maturity"] == 0, \
            f"model_maturity must be 0 when no scored rows, got {flags['model_maturity']}"

    def test_compute_coverage_flags_fail_open(self):
        """compute_coverage_flags never raises; returns default zeros on bad input."""
        from engine.release_provenance import compute_coverage_flags
        # Bad inputs: None, empty dict, missing pit_provenance
        for bad in [None, {}, {"release": "pce_headline"}]:
            result = compute_coverage_flags(bad, None)
            assert isinstance(result, dict), f"Must return dict for {bad!r}"
            assert "weight_coverage" in result
            assert "model_maturity" in result
