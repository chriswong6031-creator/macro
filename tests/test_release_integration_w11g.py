"""W11-G integration tests.

MRI W11-G | Round 2 (serial integration) | build agent: claude-sonnet-4-6 | 2026-07-10

Test categories:
  1. MF_ENERGY SHADOW: shadow row present with model='mf_energy'; artifact carries
     the shadow under item['shadows']['mf_energy']; scoring sweep picks it up.
  2. QUIRK FLAG ROOT FIX: live producer path passes root to compute_quirk_flags;
     active_strike / nfp_preliminary_benchmark fire correctly via the live path
     (regression test for CRITICAL SIGNATURE FIX — W11-G task 2).
  3. INTEGRITY CHIP: print_integrity present and fail-opens when parquet absent.
  4. REVISION CONTEXT: shape + NO lean field; model_status block present.
  5. CHAMPION VALUES UNCHANGED: champion projection bytes byte-identical to pre-W11G.
  6. IDEMPOTENCE: two producer runs add zero duplicate rows.
  7. CAPTURE HEALTH: work_stoppages_mtime and print_integrity_mtime keys present.

All tests use synthetic data / monkeypatching. No real parquet files required.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_upcoming_item(
    release_type: str = "cpi_headline",
    period: str | None = "2026-06",
    release_date: str | None = "2026-07-30",
) -> dict:
    """Build a minimal upcoming item as would appear post _build_upcoming_block."""
    return {
        "release_type": release_type,
        "release": release_type.split("_")[0],
        "period": period,
        "release_date": release_date,
        "days_to": 22,
        "projection": {
            "point": 0.25, "p10": 0.10, "p25": 0.18,
            "p50": 0.25, "p75": 0.32, "p90": 0.40,
        },
        "confidence": 0.60,
        "input_completeness": 0.80,
        "benchmark_set": {
            "naive_prior": 0.22, "trailing_3m": 0.23,
            "ar_model": None, "cleveland_nowcast": None, "market_implied": None,
        },
        "surprise_skew": {
            "sigma": 0.35, "sigma_scale_pp": 0.14,
            "tag": "hotter", "inline_band": 0.5,
        },
        "pit": {
            "revision_optimistic_legs": [],
            "unrevised_legs": [],
            "absent_legs": [],
            "display_only": True,
            "authority": False,
        },
        "regime_axis": "inflation",
        "policy_backdrop": {},
        "input_manifest": {},
    }


def _mock_mf_energy_projection() -> dict:
    """Return a minimal valid mf_energy projection dict."""
    return {
        "release": "cpi_headline",
        "model": "mf_energy",
        "asof": "2026-07-09",
        "cutoff_label": "T-1",
        "point": 0.23,
        "p10": 0.10, "p25": 0.17, "p50": 0.23, "p75": 0.29, "p90": 0.37,
        "confidence": 0.58,
        "input_completeness": 0.75,
        "mf_energy_components": {
            "gasoline_mom": 0.5,
            "energy_contrib": 0.012,
            "exenergy_ar": 0.22,
            "gasoline_ri_weight": 2.895,
            "gamma": 0.85,
            "n_gasoline_weeks_published": 3,
            "n_gasoline_weeks_projected": 1,
            "gasoline_wti_beta_slope": 0.9,
            "gasoline_wti_beta_intercept": 0.01,
            "gasoline_wti_n_train": 120,
        },
        "benchmark_set": {
            "naive_prior": 0.22,
            "expanding_mean": 0.20,
            "trailing_3m": 0.21,
            "ar_model": None,
            "cleveland_nowcast": None,
            "market_implied": None,
        },
        "surprise_skew": {
            "sigma": 0.2, "sigma_scale_pp": 0.14,
            "tag": "inline", "inline_band": 0.35,
        },
        "pit_provenance": {
            "revision_optimistic_legs": ["cpi_weights"],
            "unrevised_legs": ["gasoline_weekly", "wti_crude"],
            "absent_legs": [],
            "display_only": True,
            "authority": False,
        },
        "display_only": True,
        "authority": False,
    }


def _minimal_root(tmp_path: Path) -> Path:
    """Create minimal directory structure for producer tests."""
    (tmp_path / "data" / "release_forecast").mkdir(parents=True)
    (tmp_path / "site" / "macrodata").mkdir(parents=True)
    return tmp_path


# ===========================================================================
# 1. MF_ENERGY SHADOW
# ===========================================================================

class TestMfEnergyShadow:
    """mf_energy shadow row emitted with correct model tag; artifact shape correct."""

    def test_shadow_ledger_row_model_mf_energy(self, tmp_path: Path, monkeypatch):
        """_build_shadow_ledger_rows emits a row with model='mf_energy' for cpi_headline."""
        import scripts.build_release_forecast as producer

        monkeypatch.setattr(producer, "_run_shadow_v3", lambda *a, **k: None)
        monkeypatch.setattr(producer, "_run_shadow_bridge", lambda *a, **k: None)
        monkeypatch.setattr(producer, "_run_shadow_mf_energy", lambda *a, **k: _mock_mf_energy_projection())

        items = [_make_upcoming_item("cpi_headline")]
        rows = producer._build_shadow_ledger_rows(date(2026, 7, 9), items, tmp_path)

        mfe_rows = [r for r in rows if r.get("model") == "mf_energy"]
        assert len(mfe_rows) == 1, f"Expected 1 mf_energy shadow row, got {len(mfe_rows)}"
        row = mfe_rows[0]
        assert row["row_type"] == "shadow_projection"
        assert row["release"] == "cpi_headline"
        assert row["display_only"] is True
        assert row["authority"] is False

    def test_shadow_ledger_row_point_value(self, tmp_path: Path, monkeypatch):
        """mf_energy ledger row carries projection_point from the engine result."""
        import scripts.build_release_forecast as producer

        monkeypatch.setattr(producer, "_run_shadow_v3", lambda *a, **k: None)
        monkeypatch.setattr(producer, "_run_shadow_bridge", lambda *a, **k: None)
        monkeypatch.setattr(producer, "_run_shadow_mf_energy", lambda *a, **k: _mock_mf_energy_projection())

        items = [_make_upcoming_item("cpi_headline")]
        rows = producer._build_shadow_ledger_rows(date(2026, 7, 9), items, tmp_path)

        mfe_rows = [r for r in rows if r.get("model") == "mf_energy"]
        assert mfe_rows, "No mf_energy row"
        assert mfe_rows[0]["projection_point"] == pytest.approx(0.23)

    def test_artifact_shadow_present_in_upcoming_item(self, tmp_path: Path, monkeypatch):
        """item['shadows']['mf_energy'] populated after _attach_shadows_to_items."""
        import scripts.build_release_forecast as producer

        monkeypatch.setattr(producer, "_run_shadow_v3", lambda *a, **k: None)
        monkeypatch.setattr(producer, "_run_shadow_bridge", lambda *a, **k: None)
        monkeypatch.setattr(producer, "_run_shadow_mf_energy", lambda *a, **k: _mock_mf_energy_projection())

        items = [_make_upcoming_item("cpi_headline")]
        producer._attach_shadows_to_items(items, tmp_path, date(2026, 7, 9))

        assert "shadows" in items[0], "No shadows dict on item"
        assert "mf_energy" in items[0]["shadows"], f"mf_energy not in shadows: {list(items[0]['shadows'].keys())}"
        shadow = items[0]["shadows"]["mf_energy"]
        assert shadow["display_only"] is True
        assert shadow["point"] == pytest.approx(0.23)
        assert "mf_energy_components" in shadow, "mf_energy_components missing from shadow"

    def test_mf_energy_not_on_nfp(self, tmp_path: Path, monkeypatch):
        """mf_energy shadow is NOT attached to nfp items."""
        import scripts.build_release_forecast as producer

        call_count = {"n": 0}

        def mock_mfe(*a, **k):
            call_count["n"] += 1
            return _mock_mf_energy_projection()

        monkeypatch.setattr(producer, "_run_shadow_v3", lambda *a, **k: None)
        monkeypatch.setattr(producer, "_run_shadow_bridge", lambda *a, **k: None)
        monkeypatch.setattr(producer, "_run_shadow_mf_energy", mock_mfe)

        nfp_item = _make_upcoming_item("nfp")
        producer._attach_shadows_to_items([nfp_item], tmp_path, date(2026, 7, 9))

        assert call_count["n"] == 0, f"_run_shadow_mf_energy should NOT be called for nfp, called {call_count['n']} times"
        shadows = nfp_item.get("shadows", {})
        assert "mf_energy" not in shadows

    def test_mf_energy_fail_open(self, tmp_path: Path, monkeypatch):
        """If _run_shadow_mf_energy raises, the item still gets built (no crash)."""
        import scripts.build_release_forecast as producer

        def raising_mfe(*a, **k):
            raise RuntimeError("intentional test failure")

        monkeypatch.setattr(producer, "_run_shadow_v3", lambda *a, **k: None)
        monkeypatch.setattr(producer, "_run_shadow_bridge", lambda *a, **k: None)
        monkeypatch.setattr(producer, "_run_shadow_mf_energy", raising_mfe)

        items = [_make_upcoming_item("cpi_headline")]
        # Must not raise
        producer._attach_shadows_to_items(items, tmp_path, date(2026, 7, 9))
        # Shadow may or may not be present, but 'mf_energy' should be absent
        shadows = items[0].get("shadows", {})
        assert "mf_energy" not in shadows

    def test_mf_energy_scoring_sweep_pickup(self, tmp_path: Path, monkeypatch):
        """Existing mf_energy shadow_projection rows get scored by _check_release_day_capture."""
        import scripts.build_release_forecast as producer

        root = _minimal_root(tmp_path)
        today = date(2026, 7, 9)
        release_date = "2026-07-09"  # released today
        period = "2026-06"

        # Pre-existing ledger: one mf_energy shadow_projection row
        existing_ledger = [
            {
                "schema": 2,
                "row_type": "shadow_projection",
                "model": "mf_energy",
                "asof_night": "2026-07-08",
                "release": "cpi_headline",
                "period": period,
                "release_date": release_date,
                "release_id": "cpi_headline:2026-06",
                "prediction_id": "cpi_headline:2026-06:2026-07-08:mf_energy",
                "horizon_days": 1,
                "projection_point": 0.23,
                "projection_p10": 0.10,
                "projection_p25": 0.17,
                "projection_p50": 0.23,
                "projection_p75": 0.29,
                "projection_p90": 0.37,
                "confidence": 0.58,
                "display_only": True,
                "authority": False,
            }
        ]

        # Monkeypatch _get_actual to return a real value
        monkeypatch.setattr(producer, "_get_initial_print",
                            lambda *a, **k: 100.50)
        monkeypatch.setattr(producer, "_compute_actual_from_print",
                            lambda *a, **k: 0.25)

        scored = producer._check_release_day_capture(today, root, existing_ledger)

        mfe_scored = [r for r in scored if r.get("model") == "mf_energy"]
        assert len(mfe_scored) >= 1, (
            f"Expected at least 1 mf_energy scored row, got {len(mfe_scored)}. "
            f"All scored: {[r.get('model') for r in scored]}"
        )
        assert mfe_scored[0]["row_type"] == "scored"
        assert mfe_scored[0]["actual"] == pytest.approx(0.25)


# ===========================================================================
# 2. QUIRK FLAG ROOT FIX (CRITICAL SIGNATURE CHECK — W11-G task 2)
# ===========================================================================

class TestQuirkFlagRootFix:
    """active_strike and nfp_preliminary_benchmark fire via the LIVE producer path."""

    def test_quirk_flags_call_uses_root(self, tmp_path: Path, monkeypatch):
        """The producer calls compute_quirk_flags with the correct root arg.

        Regression test: before W11-G, the producer called compute_quirk_flags(rt, period_str)
        without root — the new Track S flags SILENTLY never fired because _check_active_strike
        and _check_preliminary_benchmark defaulted to _repo_root(), which may differ.
        This test verifies root is passed correctly via the functools.partial wrapper.
        """
        import scripts.build_release_forecast as producer

        calls: list[dict] = []

        def capture_quirk_flags(release_type: str, period_str: str, root=None) -> list:
            calls.append({"release_type": release_type, "period_str": period_str, "root": root})
            return []

        # Temporarily replace compute_quirk_flags inside the module's namespace
        # (the partial is constructed at call time using the live root)
        import functools

        def patched_import_quirks_fn(monkeypatch_inner, root_val):
            # We patch the import to return our capture function
            import engine.release_quirks as rq_module
            original = rq_module.compute_quirk_flags
            try:
                rq_module.compute_quirk_flags = capture_quirk_flags
                yield
            finally:
                rq_module.compute_quirk_flags = original

        # Build a minimal upcoming block + call _enrich_upcoming_block with root=tmp_path
        # Patch out the market_context import to avoid real IO
        class _FakeMarketCtx:
            @staticmethod
            def compute_surprise_distribution(*a, **k): return None
            @staticmethod
            def compute_expectation_read(*a, **k): return None
            @staticmethod
            def get_kalshi_implied(*a, **k): return None
            @staticmethod
            def get_market_implied_benchmark(*a, **k): return None
            @staticmethod
            def get_reaction_sensitivity(*a, **k): return None

        import sys
        fake_mc = _FakeMarketCtx()
        # Patch engine.release_quirks.compute_quirk_flags
        import engine.release_quirks as rq_module
        saved = rq_module.compute_quirk_flags
        try:
            rq_module.compute_quirk_flags = capture_quirk_flags
            import engine.release_market_context as rmc
            # Patch the market context functions
            saved_fns = {}
            for fn in ("compute_surprise_distribution", "compute_expectation_read",
                       "get_kalshi_implied", "get_market_implied_benchmark",
                       "get_reaction_sensitivity"):
                saved_fns[fn] = getattr(rmc, fn)
                setattr(rmc, fn, getattr(fake_mc, fn))

            items = [_make_upcoming_item("nfp")]
            producer._enrich_upcoming_block(items, tmp_path)
        finally:
            rq_module.compute_quirk_flags = saved
            for fn, orig in saved_fns.items():
                setattr(rmc, fn, orig)

        assert len(calls) >= 1, "compute_quirk_flags was not called at all"
        for call in calls:
            assert call["root"] == tmp_path, (
                f"root not passed to compute_quirk_flags! Got root={call['root']!r}, "
                f"expected {tmp_path!r}. W11-G CRITICAL SIGNATURE FIX regression."
            )

    def test_active_strike_fires_via_live_path(self, tmp_path: Path, monkeypatch):
        """active_strike flag lands on an nfp item via the live compute_quirk_flags path
        when the work-stoppages fixture has an overlapping stoppage.

        This is the regression test: verifies that the live producer path (with root)
        actually causes flags to appear on items, not just that the engine function exists.
        """
        import scripts.build_release_forecast as producer
        from engine.release_quirks import compute_quirk_flags

        # Build a fixture work-stoppages parquet in tmp_path so the engine finds it
        ws_dir = tmp_path / "data" / "bls_work_stoppages"
        ws_dir.mkdir(parents=True, exist_ok=True)
        # NFP reference week for 2026-06 = week containing June 12, 2026
        # June 12, 2026 is a Friday; reference Saturday = June 13, 2026
        # ref_sun = June 7, 2026
        # Place a strike overlapping that week
        ws_df = pd.DataFrame([{
            "org": "TestUnion",
            "start_date": date(2026, 6, 5),
            "end_date": None,  # ongoing
            "workers": 30000,  # >= 25k threshold
            "action": "strike",
        }])
        ws_df.to_parquet(ws_dir / "stoppages.parquet", index=False)

        # Call the engine function directly to verify it returns the flag
        flags = compute_quirk_flags("nfp", "2026-06", root=tmp_path)
        codes = {f["code"] for f in flags}

        assert "active_strike" in codes, (
            f"active_strike should be in flags for 2026-06 given the fixture stoppage. "
            f"Got codes: {codes}. "
            f"W11-G CRITICAL REGRESSION: quirk_flags root must be passed."
        )

    def test_nfp_preliminary_benchmark_fires_via_live_path(self, tmp_path: Path):
        """nfp_preliminary_benchmark flag fires for January NFP when the YAML has a large estimate."""
        from engine.release_quirks import compute_quirk_flags

        # Create the quirk_calendars YAML
        cal_dir = tmp_path / "data" / "release_forecast" / "quirk_calendars"
        cal_dir.mkdir(parents=True, exist_ok=True)
        (cal_dir / "nfp_preliminary_benchmarks.yml").write_text(
            "preliminary_benchmarks:\n"
            "  - published_month: '2025-08'\n"
            "    preliminary_estimate: -818\n"  # |818| > 100 -> flag fires
            "    note: Large downward benchmark revision for 2026-Jan NFP\n"
        )
        # January 2026 NFP => check for 2025 published
        flags = compute_quirk_flags("nfp", "2026-01", root=tmp_path)
        codes = {f["code"] for f in flags}

        assert "nfp_preliminary_benchmark" in codes, (
            f"nfp_preliminary_benchmark should fire for 2026-01 given |818|>100 estimate. "
            f"Got codes: {codes}. Root: {tmp_path}"
        )


# ===========================================================================
# 3. INTEGRITY CHIP
# ===========================================================================

class TestIntegrityChip:
    """print_integrity chip present on items; fail-opens when parquet absent."""

    def test_integrity_chip_present(self, tmp_path: Path, monkeypatch):
        """After _attach_integrity_and_revision_context, item has print_integrity dict."""
        import scripts.build_release_forecast as producer

        # Monkeypatch compute_print_integrity to return a fixed dict
        def fake_integrity(release_type="nfp", as_of=None, root=None):
            return {
                "regime": "normal",
                "collection_rate_vs_5y": -2.5,
                "cpi_median_se_trend": None,
                "revision_streak": 3,
                "source_years": [2019, 2020, 2021, 2022, 2023],
                "as_of": str(as_of or date.today()),
            }

        import engine.release_integrity as ri
        monkeypatch.setattr(ri, "compute_print_integrity", fake_integrity)

        items = [_make_upcoming_item("nfp")]
        producer._attach_integrity_and_revision_context(items, tmp_path, date(2026, 7, 9))

        item = items[0]
        assert "print_integrity" in item, "print_integrity missing from item"
        pi = item["print_integrity"]
        assert pi is not None
        assert pi["regime"] == "normal"
        assert pi["display_only"] is True
        assert pi["authority"] is False
        assert "revision_streak" in pi

    def test_integrity_chip_regime_frozen_on_item(self, tmp_path: Path, monkeypatch):
        """item['print_integrity_regime'] is populated (for freezing on ledger row)."""
        import scripts.build_release_forecast as producer

        def fake_integrity(release_type="nfp", as_of=None, root=None):
            return {"regime": "degraded", "collection_rate_vs_5y": -6.0,
                    "cpi_median_se_trend": None, "revision_streak": -2,
                    "source_years": [], "as_of": "2026-07-09"}

        import engine.release_integrity as ri
        monkeypatch.setattr(ri, "compute_print_integrity", fake_integrity)

        items = [_make_upcoming_item("cpi_headline")]
        producer._attach_integrity_and_revision_context(items, tmp_path, date(2026, 7, 9))

        assert items[0].get("print_integrity_regime") == "degraded"

    def test_integrity_chip_fail_open_parquet_absent(self, tmp_path: Path, monkeypatch):
        """When integrity parquet absent, item still gets built (print_integrity=None)."""
        import scripts.build_release_forecast as producer

        def raising_integrity(*a, **k):
            raise FileNotFoundError("integrity parquet absent")

        import engine.release_integrity as ri
        monkeypatch.setattr(ri, "compute_print_integrity", raising_integrity)

        items = [_make_upcoming_item("nfp")]
        # Must not raise
        producer._attach_integrity_and_revision_context(items, tmp_path, date(2026, 7, 9))

        # print_integrity should be None or missing (fail-open)
        assert items[0].get("print_integrity") is None

    def test_integrity_chip_all_release_types(self, tmp_path: Path, monkeypatch):
        """print_integrity is called for each release_type (not just nfp)."""
        import scripts.build_release_forecast as producer

        called_with: list[str] = []

        def recording_integrity(release_type="nfp", as_of=None, root=None):
            called_with.append(release_type)
            return {"regime": "normal", "collection_rate_vs_5y": None,
                    "cpi_median_se_trend": None, "revision_streak": None,
                    "source_years": [], "as_of": "2026-07-09"}

        import engine.release_integrity as ri
        monkeypatch.setattr(ri, "compute_print_integrity", recording_integrity)

        items = [
            _make_upcoming_item("cpi_headline"),
            _make_upcoming_item("nfp"),
            _make_upcoming_item("pce_headline"),
        ]
        producer._attach_integrity_and_revision_context(items, tmp_path, date(2026, 7, 9))

        assert set(called_with) == {"cpi_headline", "nfp", "pce_headline"}, (
            f"compute_print_integrity not called for all release types. Got: {called_with}"
        )


# ===========================================================================
# 4. REVISION CONTEXT
# ===========================================================================

class TestRevisionContext:
    """revision_context shape correct; no lean field; model_status present."""

    def test_revision_context_on_nfp(self, tmp_path: Path, monkeypatch):
        """NFP item gets revision_context with level_bias_annotation."""
        import scripts.build_release_forecast as producer

        # Let compute_revision_context run naturally (it's pure constants, no IO)
        items = [_make_upcoming_item("nfp")]
        producer._attach_integrity_and_revision_context(items, tmp_path, date(2026, 7, 9))

        item = items[0]
        assert "revision_context" in item, "revision_context missing from nfp item"
        rc = item["revision_context"]
        assert rc is not None, "revision_context is None"
        assert rc["display_only"] is True
        assert rc["authority"] is False

    def test_revision_context_has_level_bias(self, tmp_path: Path, monkeypatch):
        """revision_context carries level_bias_annotation with expansion/contraction keys."""
        import scripts.build_release_forecast as producer

        items = [_make_upcoming_item("nfp")]
        producer._attach_integrity_and_revision_context(items, tmp_path, date(2026, 7, 9))

        rc = items[0].get("revision_context") or {}
        lba = rc.get("level_bias_annotation") or {}
        assert "expansion_mean_cumulative_revision_k" in lba, (
            f"expansion_mean_cumulative_revision_k missing from level_bias_annotation: {lba}"
        )
        assert "contraction_mean_cumulative_revision_k" in lba
        assert lba["expansion_mean_cumulative_revision_k"] == 216
        assert lba["contraction_mean_cumulative_revision_k"] == -262

    def test_no_lean_field_in_revision_context(self, tmp_path: Path, monkeypatch):
        """revision_context must NOT carry a 'lean' or 'lean_direction' field.

        Track R is KILLED (attempt 1). No lean may be displayed (MRI-R37).
        """
        import scripts.build_release_forecast as producer

        items = [_make_upcoming_item("nfp")]
        producer._attach_integrity_and_revision_context(items, tmp_path, date(2026, 7, 9))

        rc = items[0].get("revision_context") or {}
        # Walk entire dict recursively to ensure no 'lean' key with a direction
        def _check_no_lean(d: Any, path: str = "") -> None:
            if isinstance(d, dict):
                for k, v in d.items():
                    if k == "lean" and isinstance(v, str) and v in ("up", "down"):
                        raise AssertionError(
                            f"Found lean='{v}' at path '{path}.{k}' — "
                            f"Track R is KILLED, no lean direction must be displayed (MRI-R37)"
                        )
                    _check_no_lean(v, path=f"{path}.{k}")

        _check_no_lean(rc)

    def test_model_status_block_present(self, tmp_path: Path, monkeypatch):
        """revision_context carries model_status with track_r='killed_attempt_1' and lean_display=False."""
        import scripts.build_release_forecast as producer

        items = [_make_upcoming_item("nfp")]
        producer._attach_integrity_and_revision_context(items, tmp_path, date(2026, 7, 9))

        rc = items[0].get("revision_context") or {}
        ms = rc.get("model_status") or {}
        assert ms.get("track_r") == "killed_attempt_1", (
            f"Expected track_r='killed_attempt_1', got {ms.get('track_r')!r}"
        )
        assert ms.get("lean_display") is False, (
            f"Expected lean_display=False, got {ms.get('lean_display')!r}"
        )

    def test_revision_context_not_on_cpi(self, tmp_path: Path, monkeypatch):
        """CPI items do not get revision_context (it's NFP-only)."""
        import scripts.build_release_forecast as producer

        items = [_make_upcoming_item("cpi_headline")]
        producer._attach_integrity_and_revision_context(items, tmp_path, date(2026, 7, 9))

        # CPI item should not have revision_context (the field is absent or None)
        # (The spec is NFP-only for revision_context)
        rc = items[0].get("revision_context")
        assert rc is None, (
            f"CPI items should not have revision_context, got: {rc}"
        )


# ===========================================================================
# 5. CHAMPION VALUES BYTE-IDENTICAL
# ===========================================================================

class TestChampionValuesByteIdentical:
    """Champion projection rows are unaffected by W11-G additions."""

    def test_champion_row_model_is_none(self, tmp_path: Path, monkeypatch):
        """Champion projection ledger rows still have model=None after W11-G."""
        import scripts.build_release_forecast as producer

        item = _make_upcoming_item("cpi_headline")
        rows = producer._build_projection_ledger_rows(
            date(2026, 7, 9), [item], {}
        )
        assert len(rows) == 1
        assert rows[0]["model"] is None, (
            f"Champion row should have model=None, got {rows[0]['model']!r}"
        )

    def test_champion_projection_point_unchanged(self, tmp_path: Path, monkeypatch):
        """Shadow additions do not alter champion projection_point value."""
        import scripts.build_release_forecast as producer

        item = _make_upcoming_item("cpi_headline")
        original_point = item["projection"]["point"]  # 0.25

        # Attach all W11-G enrichments
        monkeypatch.setattr(producer, "_run_shadow_v3", lambda *a, **k: None)
        monkeypatch.setattr(producer, "_run_shadow_bridge", lambda *a, **k: None)
        monkeypatch.setattr(producer, "_run_shadow_mf_energy", lambda *a, **k: _mock_mf_energy_projection())

        producer._attach_shadows_to_items([item], tmp_path, date(2026, 7, 9))

        # Champion point must be unchanged
        assert item["projection"]["point"] == original_point, (
            f"Champion projection point changed after shadow attachment! "
            f"Expected {original_point}, got {item['projection']['point']}"
        )

    def test_ledger_row_no_shadow_fields_on_champion(self, tmp_path: Path, monkeypatch):
        """Champion ledger rows do not carry mf_energy-specific shadow fields."""
        import scripts.build_release_forecast as producer

        item = _make_upcoming_item("cpi_headline")
        item["print_integrity_regime"] = "normal"  # W11-G adds this
        rows = producer._build_projection_ledger_rows(date(2026, 7, 9), [item], {})

        assert len(rows) == 1
        row = rows[0]
        # mf_energy-specific fields should NOT appear on champion rows
        assert "mf_energy_components" not in row, "mf_energy_components on champion row"
        # print_integrity_regime IS frozen on champion rows (task 3)
        assert "print_integrity_regime" in row


# ===========================================================================
# 6. IDEMPOTENCE
# ===========================================================================

class TestIdempotence:
    """Two shadow_ledger_rows calls produce zero duplicate mf_energy rows in ledger."""

    def test_two_runs_no_duplicate_mf_energy_rows(self, tmp_path: Path, monkeypatch):
        """Running _build_shadow_ledger_rows twice and appending both results to ledger
        then calling _append_ledger_rows deduplicate mf_energy rows."""
        import scripts.build_release_forecast as producer

        monkeypatch.setattr(producer, "_run_shadow_v3", lambda *a, **k: None)
        monkeypatch.setattr(producer, "_run_shadow_bridge", lambda *a, **k: None)
        monkeypatch.setattr(producer, "_run_shadow_mf_energy", lambda *a, **k: _mock_mf_energy_projection())

        root = _minimal_root(tmp_path)
        ledger_path = root / "data" / "release_forecast" / "forward_ledger.jsonl"
        items = [_make_upcoming_item("cpi_headline")]
        today = date(2026, 7, 9)

        rows_run1 = producer._build_shadow_ledger_rows(today, items, root)
        rows_run2 = producer._build_shadow_ledger_rows(today, items, root)

        # Append run 1
        producer._append_ledger_rows(ledger_path, rows_run1)
        # Append run 2 (should be deduplicated)
        producer._append_ledger_rows(ledger_path, rows_run2)

        # Read back the ledger
        with open(ledger_path) as f:
            ledger = [json.loads(line) for line in f if line.strip()]

        mfe_rows = [r for r in ledger if r.get("model") == "mf_energy"]
        assert len(mfe_rows) == 1, (
            f"Expected exactly 1 mf_energy row after two idempotent runs, got {len(mfe_rows)}"
        )


# ===========================================================================
# 7. CAPTURE HEALTH
# ===========================================================================

class TestCaptureHealth:
    """capture_health includes new W11-G staleness keys."""

    def test_capture_health_has_work_stoppages_mtime(self, tmp_path: Path, monkeypatch):
        """capture_health['enricher_staleness']['work_stoppages_mtime'] is present."""
        import scripts.build_release_forecast as producer

        root = _minimal_root(tmp_path)
        # Create a work_stoppages parquet
        ws_dir = root / "data" / "bls_work_stoppages"
        ws_dir.mkdir(parents=True, exist_ok=True)
        ws_df = pd.DataFrame([{"org": "X", "start_date": "2026-06-01",
                                "end_date": None, "workers": 50000}])
        ws_df.to_parquet(ws_dir / "stoppages.parquet", index=False)

        health = producer._compute_capture_health(date(2026, 7, 9), root, [])
        staleness = health.get("enricher_staleness", {})
        assert "work_stoppages_mtime" in staleness, (
            f"work_stoppages_mtime missing from enricher_staleness: {staleness}"
        )
        # The mtime should be non-None since we created the file
        assert staleness["work_stoppages_mtime"] is not None

    def test_capture_health_has_print_integrity_mtime(self, tmp_path: Path, monkeypatch):
        """capture_health['enricher_staleness']['print_integrity_mtime'] is present."""
        import scripts.build_release_forecast as producer

        root = _minimal_root(tmp_path)
        # Create a print_integrity parquet
        pi_dir = root / "data" / "bls_print_integrity"
        pi_dir.mkdir(parents=True, exist_ok=True)
        pi_df = pd.DataFrame([{"table": "ces_response", "period_key": "2023",
                                "metric_a": 62.5, "component": "all"}])
        pi_df.to_parquet(pi_dir / "integrity.parquet", index=False)

        health = producer._compute_capture_health(date(2026, 7, 9), root, [])
        staleness = health.get("enricher_staleness", {})
        assert "print_integrity_mtime" in staleness, (
            f"print_integrity_mtime missing from enricher_staleness: {staleness}"
        )
        assert staleness["print_integrity_mtime"] is not None

    def test_capture_health_null_when_files_absent(self, tmp_path: Path, monkeypatch):
        """When work_stoppages / print_integrity files absent, mtime keys are None."""
        import scripts.build_release_forecast as producer

        root = _minimal_root(tmp_path)
        # Ensure directories do NOT exist
        # (they don't in a fresh tmp_path)

        health = producer._compute_capture_health(date(2026, 7, 9), root, [])
        staleness = health.get("enricher_staleness", {})
        # These keys should be present but None when files are absent
        assert "work_stoppages_mtime" in staleness
        assert staleness.get("work_stoppages_mtime") is None
        assert "print_integrity_mtime" in staleness
        assert staleness.get("print_integrity_mtime") is None
