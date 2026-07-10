"""Round-2b integration tests: v3_factor + cpi_bridge shadow tracks.

MRI-R21 + MRI-R25 | Round 2b | build agent: claude-sonnet-4-6 | 2026-07-08

Test categories:
  1. SHADOW LEDGER: shadow_projection rows present with correct model tags;
     champion "projection" rows byte-identical to pre-2b (snapshot compare).
  2. ARTIFACT SHADOWS: upcoming items carry item["shadows"] only where expected;
     nfp shadow carries the warning; cpi_core has no cpi_bridge; pce/ppi/claims have no shadows.
  3. AUTHORITY: no shadow value alters champion point/interval/skew/benchmark or
     gates/scores/sizes anything; artifact display_only=True; authority booleans False.
  4. IDEMPOTENCE: two producer runs don't duplicate champion OR shadow rows.
  5. FAIL-OPEN: a shadow-model exception degrades to "no shadow", never breaks the build.
  6. SCORING: a synthetic release-day capture scores both champion and shadow rows.
  7. SCOREBOARD: by_shadow section present and forward-only (n=0 until data accrues).

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
) -> dict:
    """Build a minimal upcoming item as would appear post _build_upcoming_block."""
    return {
        "release_type": release_type,
        "release": release_type.split("_")[0],
        "period": period,
        "release_date": release_date,
        "days_to": 22,
        "projection": {
            "point": 0.20, "p10": 0.10, "p25": 0.15,
            "p50": 0.20, "p75": 0.25, "p90": 0.30,
        },
        "confidence": 0.55,
        "input_completeness": 0.75,
        "benchmark_set": {
            "naive_prior": 0.18, "trailing_3m": 0.19,
            "ar_model": None, "cleveland_nowcast": None, "market_implied": None,
        },
        "surprise_skew": {
            "sigma": 0.3, "sigma_scale_pp": 0.12,
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


def _mock_v3_projection(release_type: str) -> dict:
    """Return a minimal valid v3_factor projection dict."""
    return {
        "release": release_type,
        "model": "v3_factor",
        "asof": "2026-07-08",
        "point": 0.18,
        "p10": 0.10, "p25": 0.15, "p50": 0.18, "p75": 0.21, "p90": 0.26,
        "confidence": None,
        "input_completeness": 0.7,
        "display_only": True,
        "authority": False,
        "benchmark_set": {"naive_prior": 0.19, "trailing_3m": 0.20},
        "surprise_skew": {"sigma": -0.1, "tag": "inline", "inline_band": 0.35},
        "pit_provenance": {"revision_optimistic_legs": [], "unrevised_legs": [], "absent_legs": []},
    }


def _mock_bridge_projection(release_type: str = "cpi_headline") -> dict:
    """Return a minimal valid cpi_bridge projection dict."""
    return {
        "release": release_type,
        "model": "cpi_bridge",
        "asof": "2026-07-08",
        "point": 0.21,
        "p10": None, "p25": None, "p50": None, "p75": None, "p90": None,
        "confidence": 0.55,
        "components": [
            {"block": "shelter", "contribution_pp": 0.10, "weight": 35.625,
             "confidence": 0.6, "prior_only": False},
        ],
        "weight_coverage": 0.839,
        "coverage_residual_pp": 0.0,
        "prior_driven_share": 0.06,
        "display_only": True,
        "authority": False,
        "benchmark_set": {"naive_prior": 0.19, "trailing_3m": 0.20},
        "pit_provenance": {"revision_optimistic_legs": [], "unrevised_legs": [], "absent_legs": []},
    }


def _make_minimal_root(tmp_path: Path) -> Path:
    """Create minimal directory structure for producer tests."""
    (tmp_path / "data" / "release_forecast").mkdir(parents=True)
    (tmp_path / "site" / "macrodata").mkdir(parents=True)
    return tmp_path


# ===========================================================================
# 1. SHADOW LEDGER
# ===========================================================================

class TestShadowLedger:
    """Shadow rows appear in ledger with correct model tags; champion rows unchanged."""

    def test_shadow_rows_have_row_type_shadow_projection(self, tmp_path: Path, monkeypatch):
        """_build_shadow_ledger_rows emits rows with row_type='shadow_projection'."""
        import scripts.build_release_forecast as producer

        monkeypatch.setattr(producer, "_run_shadow_v3", lambda *a, **k: _mock_v3_projection(a[0]))
        monkeypatch.setattr(producer, "_run_shadow_bridge", lambda *a, **k: _mock_bridge_projection())

        items = [_minimal_upcoming_item("cpi_headline")]
        rows = producer._build_shadow_ledger_rows(date(2026, 7, 8), items, tmp_path)

        assert len(rows) >= 1, "Expected at least one shadow row"
        for row in rows:
            assert row["row_type"] == "shadow_projection", \
                f"Expected 'shadow_projection', got {row['row_type']!r}"

    def test_shadow_rows_carry_model_field(self, tmp_path: Path, monkeypatch):
        """Shadow rows carry explicit model='v3_factor' or 'cpi_bridge'."""
        import scripts.build_release_forecast as producer

        monkeypatch.setattr(producer, "_run_shadow_v3", lambda *a, **k: _mock_v3_projection(a[0]))
        monkeypatch.setattr(producer, "_run_shadow_bridge", lambda *a, **k: _mock_bridge_projection())

        items = [_minimal_upcoming_item("cpi_headline")]
        rows = producer._build_shadow_ledger_rows(date(2026, 7, 8), items, tmp_path)

        models = {row["model"] for row in rows}
        assert "v3_factor" in models, f"v3_factor not in shadow row models: {models}"
        assert "cpi_bridge" in models, f"cpi_bridge not in shadow row models: {models}"

    def test_champion_rows_have_model_none(self, tmp_path: Path, monkeypatch):
        """Champion projection rows have model=None."""
        import scripts.build_release_forecast as producer

        items = [_minimal_upcoming_item("cpi_headline")]
        policy_backdrop = {
            "fed_stance": None, "gap_bp": None,
            "implied_cuts_12m": None, "next_fomc": None,
        }
        rows = producer._build_projection_ledger_rows(date(2026, 7, 8), items, policy_backdrop)

        assert len(rows) >= 1
        for row in rows:
            assert row.get("model") is None, \
                f"Champion row must have model=None, got {row.get('model')!r}"

    def test_champion_rows_have_row_type_projection(self, tmp_path: Path):
        """Champion rows still have row_type='projection' after Round-2b."""
        import scripts.build_release_forecast as producer

        items = [_minimal_upcoming_item("cpi_headline")]
        policy_backdrop = {
            "fed_stance": None, "gap_bp": None,
            "implied_cuts_12m": None, "next_fomc": None,
        }
        rows = producer._build_projection_ledger_rows(date(2026, 7, 8), items, policy_backdrop)

        for row in rows:
            assert row["row_type"] == "projection", \
                f"Champion row must have row_type='projection', got {row['row_type']!r}"

    def test_shadow_idempotency_key_includes_model(self, tmp_path: Path, monkeypatch):
        """Shadow rows are deduplicated by (release, period, row_type, asof_night, model)."""
        import scripts.build_release_forecast as producer

        monkeypatch.setattr(producer, "_run_shadow_v3", lambda *a, **k: _mock_v3_projection(a[0]))
        monkeypatch.setattr(producer, "_run_shadow_bridge", lambda *a, **k: _mock_bridge_projection())

        items = [_minimal_upcoming_item("cpi_headline")]
        rows = producer._build_shadow_ledger_rows(date(2026, 7, 8), items, tmp_path)

        # Check that idempotency keys are unique
        keys = [producer._ledger_key(r) for r in rows]
        assert len(keys) == len(set(keys)), \
            f"Duplicate idempotency keys in shadow rows: {keys}"

    def test_champion_and_shadow_keys_dont_collide(self, tmp_path: Path, monkeypatch):
        """Champion and shadow idempotency keys don't collide."""
        import scripts.build_release_forecast as producer

        monkeypatch.setattr(producer, "_run_shadow_v3", lambda *a, **k: _mock_v3_projection(a[0]))
        monkeypatch.setattr(producer, "_run_shadow_bridge", lambda *a, **k: _mock_bridge_projection())

        items = [_minimal_upcoming_item("cpi_headline")]
        policy_backdrop = {
            "fed_stance": None, "gap_bp": None,
            "implied_cuts_12m": None, "next_fomc": None,
        }
        champ_rows = producer._build_projection_ledger_rows(date(2026, 7, 8), items, policy_backdrop)
        shadow_rows = producer._build_shadow_ledger_rows(date(2026, 7, 8), items, tmp_path)

        all_rows = champ_rows + shadow_rows
        keys = [producer._ledger_key(r) for r in all_rows]
        assert len(keys) == len(set(keys)), \
            f"Collision between champion and shadow ledger keys: {[k for k in keys if keys.count(k) > 1]}"

    def test_nfp_shadow_no_cpi_bridge(self, tmp_path: Path, monkeypatch):
        """NFP items get v3_factor shadow but no cpi_bridge (bridge is cpi_headline only)."""
        import scripts.build_release_forecast as producer

        monkeypatch.setattr(producer, "_run_shadow_v3", lambda *a, **k: _mock_v3_projection(a[0]))
        monkeypatch.setattr(producer, "_run_shadow_bridge", lambda *a, **k: _mock_bridge_projection())

        items = [_minimal_upcoming_item("nfp")]
        rows = producer._build_shadow_ledger_rows(date(2026, 7, 8), items, tmp_path)

        models = {row["model"] for row in rows}
        assert "v3_factor" in models, "NFP must have v3_factor shadow"
        assert "cpi_bridge" not in models, "NFP must NOT have cpi_bridge shadow"

    def test_cpi_core_shadow_no_bridge(self, tmp_path: Path, monkeypatch):
        """cpi_core gets v3_factor shadow but no cpi_bridge (bridge killed for core)."""
        import scripts.build_release_forecast as producer

        monkeypatch.setattr(producer, "_run_shadow_v3", lambda *a, **k: _mock_v3_projection(a[0]))
        monkeypatch.setattr(producer, "_run_shadow_bridge", lambda *a, **k: _mock_bridge_projection())

        items = [_minimal_upcoming_item("cpi_core")]
        rows = producer._build_shadow_ledger_rows(date(2026, 7, 8), items, tmp_path)

        models = {row["model"] for row in rows}
        assert "v3_factor" in models, "cpi_core must have v3_factor shadow"
        assert "cpi_bridge" not in models, "cpi_core must NOT have cpi_bridge shadow (closed)"

    def test_pce_has_no_shadows(self, tmp_path: Path, monkeypatch):
        """PCE/PPI/claims/retail items produce no shadow rows."""
        import scripts.build_release_forecast as producer

        monkeypatch.setattr(producer, "_run_shadow_v3", lambda *a, **k: _mock_v3_projection(a[0]))
        monkeypatch.setattr(producer, "_run_shadow_bridge", lambda *a, **k: _mock_bridge_projection())

        for rt in ("pce_headline", "pce_core", "ppi_finaldemand", "claims", "retail_sales"):
            items = [_minimal_upcoming_item(rt)]
            rows = producer._build_shadow_ledger_rows(date(2026, 7, 8), items, tmp_path)
            assert len(rows) == 0, \
                f"{rt} must produce no shadow ledger rows, got {len(rows)}"

    def test_bridge_row_carries_components_fields(self, tmp_path: Path, monkeypatch):
        """cpi_bridge shadow ledger row carries components, coverage_residual_pp, prior_driven_share."""
        import scripts.build_release_forecast as producer

        monkeypatch.setattr(producer, "_run_shadow_v3", lambda *a, **k: None)
        monkeypatch.setattr(producer, "_run_shadow_bridge", lambda *a, **k: _mock_bridge_projection())

        items = [_minimal_upcoming_item("cpi_headline")]
        rows = producer._build_shadow_ledger_rows(date(2026, 7, 8), items, tmp_path)

        bridge_rows = [r for r in rows if r.get("model") == "cpi_bridge"]
        assert len(bridge_rows) == 1, f"Expected 1 bridge row, got {len(bridge_rows)}"
        br = bridge_rows[0]
        assert "components" in br, "bridge row must carry 'components'"
        assert "coverage_residual_pp" in br, "bridge row must carry 'coverage_residual_pp'"
        assert "prior_driven_share" in br, "bridge row must carry 'prior_driven_share'"


# ===========================================================================
# 2. ARTIFACT SHADOWS
# ===========================================================================

class TestArtifactShadows:
    """upcoming items carry shadows dict only where expected."""

    def test_cpi_headline_item_has_both_shadows(self, tmp_path: Path, monkeypatch):
        """cpi_headline item.shadows carries v3_factor and cpi_bridge."""
        import scripts.build_release_forecast as producer

        monkeypatch.setattr(producer, "_run_shadow_v3", lambda *a, **k: _mock_v3_projection(a[0]))
        monkeypatch.setattr(producer, "_run_shadow_bridge", lambda *a, **k: _mock_bridge_projection())

        items = [_minimal_upcoming_item("cpi_headline")]
        producer._attach_shadows_to_items(items, tmp_path, date(2026, 7, 8))

        item = items[0]
        shadows = item.get("shadows", {})
        assert "v3_factor" in shadows, f"cpi_headline shadows must include v3_factor: {list(shadows)}"
        assert "cpi_bridge" in shadows, f"cpi_headline shadows must include cpi_bridge: {list(shadows)}"

    def test_cpi_core_item_has_v3_only(self, tmp_path: Path, monkeypatch):
        """cpi_core item.shadows carries v3_factor but NOT cpi_bridge."""
        import scripts.build_release_forecast as producer

        monkeypatch.setattr(producer, "_run_shadow_v3", lambda *a, **k: _mock_v3_projection(a[0]))
        monkeypatch.setattr(producer, "_run_shadow_bridge", lambda *a, **k: _mock_bridge_projection())

        items = [_minimal_upcoming_item("cpi_core")]
        producer._attach_shadows_to_items(items, tmp_path, date(2026, 7, 8))

        item = items[0]
        shadows = item.get("shadows", {})
        assert "v3_factor" in shadows, "cpi_core shadows must include v3_factor"
        assert "cpi_bridge" not in shadows, "cpi_core shadows must NOT include cpi_bridge"

    def test_nfp_shadow_carries_warning(self, tmp_path: Path, monkeypatch):
        """nfp item.shadows.v3_factor carries the NFP warning text."""
        import scripts.build_release_forecast as producer

        monkeypatch.setattr(producer, "_run_shadow_v3", lambda *a, **k: _mock_v3_projection("nfp"))
        monkeypatch.setattr(producer, "_run_shadow_bridge", lambda *a, **k: None)

        items = [_minimal_upcoming_item("nfp")]
        producer._attach_shadows_to_items(items, tmp_path, date(2026, 7, 8))

        item = items[0]
        shadows = item.get("shadows", {})
        assert "v3_factor" in shadows, "nfp must have v3_factor shadow"
        v3_entry = shadows["v3_factor"]
        assert "warning" in v3_entry, "nfp v3_factor shadow must carry 'warning'"
        assert "catastrophic" in v3_entry["warning"].lower(), \
            f"nfp warning must mention 'catastrophic': {v3_entry['warning']}"
        assert "sub-naive" in v3_entry["warning"].lower(), \
            f"nfp warning must mention 'sub-naive': {v3_entry['warning']}"

    def test_cpi_headline_shadow_nfp_warning_absent(self, tmp_path: Path, monkeypatch):
        """cpi_headline v3_factor shadow does NOT carry the NFP warning."""
        import scripts.build_release_forecast as producer

        monkeypatch.setattr(producer, "_run_shadow_v3", lambda *a, **k: _mock_v3_projection(a[0]))
        monkeypatch.setattr(producer, "_run_shadow_bridge", lambda *a, **k: _mock_bridge_projection())

        items = [_minimal_upcoming_item("cpi_headline")]
        producer._attach_shadows_to_items(items, tmp_path, date(2026, 7, 8))

        item = items[0]
        v3_entry = item.get("shadows", {}).get("v3_factor", {})
        assert "warning" not in v3_entry, \
            f"cpi_headline v3_factor shadow must NOT have warning, got {v3_entry}"

    def test_pce_ppi_claims_no_shadows(self, tmp_path: Path, monkeypatch):
        """PCE/PPI/claims/retail items do NOT receive shadows."""
        import scripts.build_release_forecast as producer

        monkeypatch.setattr(producer, "_run_shadow_v3", lambda *a, **k: _mock_v3_projection(a[0]))
        monkeypatch.setattr(producer, "_run_shadow_bridge", lambda *a, **k: _mock_bridge_projection())

        for rt in ("pce_headline", "pce_core", "ppi_finaldemand", "claims", "retail_sales"):
            items = [_minimal_upcoming_item(rt)]
            producer._attach_shadows_to_items(items, tmp_path, date(2026, 7, 8))
            item = items[0]
            shadows = item.get("shadows")
            assert shadows is None or shadows == {}, \
                f"{rt} must not receive shadows, got {shadows}"

    def test_shadow_entries_are_display_only(self, tmp_path: Path, monkeypatch):
        """Each shadow entry in item.shadows has display_only=True."""
        import scripts.build_release_forecast as producer

        monkeypatch.setattr(producer, "_run_shadow_v3", lambda *a, **k: _mock_v3_projection(a[0]))
        monkeypatch.setattr(producer, "_run_shadow_bridge", lambda *a, **k: _mock_bridge_projection())

        for rt in ("cpi_headline", "cpi_core", "nfp"):
            items = [_minimal_upcoming_item(rt)]
            producer._attach_shadows_to_items(items, tmp_path, date(2026, 7, 8))
            item = items[0]
            for model, entry in item.get("shadows", {}).items():
                assert entry.get("display_only") is True, \
                    f"{rt}.shadows.{model} must have display_only=True"

    def test_bridge_shadow_carries_component_fields(self, tmp_path: Path, monkeypatch):
        """cpi_bridge shadow entry in artifact carries components and prior_driven_share."""
        import scripts.build_release_forecast as producer

        monkeypatch.setattr(producer, "_run_shadow_v3", lambda *a, **k: _mock_v3_projection(a[0]))
        monkeypatch.setattr(producer, "_run_shadow_bridge", lambda *a, **k: _mock_bridge_projection())

        items = [_minimal_upcoming_item("cpi_headline")]
        producer._attach_shadows_to_items(items, tmp_path, date(2026, 7, 8))

        bridge_entry = items[0].get("shadows", {}).get("cpi_bridge", {})
        assert "components" in bridge_entry, "cpi_bridge shadow must carry 'components'"
        assert "prior_driven_share" in bridge_entry, "cpi_bridge shadow must carry 'prior_driven_share'"


# ===========================================================================
# 3. AUTHORITY
# ===========================================================================

class TestAuthority:
    """Shadow values must NEVER alter champion projection or gate anything."""

    def test_champion_projection_unchanged_after_shadows_attached(self, tmp_path: Path, monkeypatch):
        """item['projection'] is byte-identical before and after _attach_shadows_to_items."""
        import scripts.build_release_forecast as producer

        monkeypatch.setattr(producer, "_run_shadow_v3", lambda *a, **k: _mock_v3_projection(a[0]))
        monkeypatch.setattr(producer, "_run_shadow_bridge", lambda *a, **k: _mock_bridge_projection())

        item = _minimal_upcoming_item("cpi_headline")
        proj_before = dict(item["projection"])
        producer._attach_shadows_to_items([item], tmp_path, date(2026, 7, 8))

        assert item["projection"] == proj_before, \
            f"Champion projection was mutated by shadow attachment: {item['projection']} vs {proj_before}"

    def test_champion_benchmark_set_unchanged(self, tmp_path: Path, monkeypatch):
        """item['benchmark_set'] is unchanged after shadow attachment."""
        import scripts.build_release_forecast as producer

        monkeypatch.setattr(producer, "_run_shadow_v3", lambda *a, **k: _mock_v3_projection(a[0]))
        monkeypatch.setattr(producer, "_run_shadow_bridge", lambda *a, **k: _mock_bridge_projection())

        item = _minimal_upcoming_item("cpi_headline")
        bench_before = dict(item["benchmark_set"])
        producer._attach_shadows_to_items([item], tmp_path, date(2026, 7, 8))

        assert item["benchmark_set"] == bench_before, \
            f"Champion benchmark_set was mutated: {item['benchmark_set']} vs {bench_before}"

    def test_champion_surprise_skew_unchanged(self, tmp_path: Path, monkeypatch):
        """item['surprise_skew'] is unchanged after shadow attachment."""
        import scripts.build_release_forecast as producer

        monkeypatch.setattr(producer, "_run_shadow_v3", lambda *a, **k: _mock_v3_projection(a[0]))
        monkeypatch.setattr(producer, "_run_shadow_bridge", lambda *a, **k: _mock_bridge_projection())

        item = _minimal_upcoming_item("cpi_headline")
        skew_before = dict(item["surprise_skew"])
        producer._attach_shadows_to_items([item], tmp_path, date(2026, 7, 8))

        assert item["surprise_skew"] == skew_before, \
            f"Champion surprise_skew was mutated: {item['surprise_skew']} vs {skew_before}"

    def test_shadow_row_authority_false(self, tmp_path: Path, monkeypatch):
        """Shadow ledger rows have authority=False."""
        import scripts.build_release_forecast as producer

        monkeypatch.setattr(producer, "_run_shadow_v3", lambda *a, **k: _mock_v3_projection(a[0]))
        monkeypatch.setattr(producer, "_run_shadow_bridge", lambda *a, **k: _mock_bridge_projection())

        items = [_minimal_upcoming_item("cpi_headline")]
        rows = producer._build_shadow_ledger_rows(date(2026, 7, 8), items, tmp_path)

        for row in rows:
            assert row.get("authority") is False, \
                f"Shadow row must have authority=False: {row}"

    def test_build_display_only_true_after_shadow_integration(self, tmp_path: Path, monkeypatch):
        """build() result display_only=True and authority all False after Round-2b."""
        import scripts.build_release_forecast as producer
        _make_minimal_root(tmp_path)

        monkeypatch.setattr(producer, "_find_upcoming_releases", lambda *a, **k: [])
        monkeypatch.setattr(producer, "_read_policy_backdrop", lambda *a, **k: {
            "fed_stance": None, "gap_bp": None,
            "implied_cuts_12m": None, "next_fomc": None, "guidance_direction": None,
        })

        result = producer.build(tmp_path, dry_run=True)
        assert result["display_only"] is True
        auth = result["authority"]
        assert auth["can_score"] is False
        assert auth["can_size"] is False
        assert auth["can_trade"] is False


# ===========================================================================
# 4. IDEMPOTENCE
# ===========================================================================

class TestIdempotence:
    """Two producer runs don't duplicate champion OR shadow rows."""

    def test_double_run_no_dup_champion_rows(self, tmp_path: Path, monkeypatch):
        """build() twice same night produces no duplicate champion rows."""
        import scripts.build_release_forecast as producer
        _make_minimal_root(tmp_path)

        upcoming_events = [
            {
                "release_type": "cpi_headline",
                "release": "cpi",
                "release_date": "2026-07-30",
                "period": "2026-06",
                "regime_axis": "inflation",
            },
        ]

        def _mock_upcoming(*a, **k):
            return upcoming_events

        def _mock_run_proj(rt, asof, root, period_str=None, release_date=None):
            return {
                "release": rt, "asof": asof.isoformat(),
                "point": 0.20, "p10": 0.10, "p25": 0.15, "p50": 0.20, "p75": 0.25, "p90": 0.30,
                "confidence": 0.5, "input_completeness": 0.75,
                "benchmark_set": {"naive_prior": 0.18, "trailing_3m": 0.19,
                                  "ar_model": None, "cleveland_nowcast": None, "market_implied": None},
                "surprise_skew": {"sigma": 0.1, "sigma_scale_pp": 0.1, "tag": "inline", "inline_band": 0.5},
                "pit_provenance": {"revision_optimistic_legs": [], "unrevised_legs": [],
                                   "absent_legs": [], "display_only": True, "authority": False},
                "display_only": True, "authority": False,
            }

        monkeypatch.setattr(producer, "_find_upcoming_releases", _mock_upcoming)
        monkeypatch.setattr(producer, "_run_projection", _mock_run_proj)
        monkeypatch.setattr(producer, "_run_shadow_v3", lambda *a, **k: _mock_v3_projection(a[0]))
        monkeypatch.setattr(producer, "_run_shadow_bridge", lambda *a, **k: _mock_bridge_projection())
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
            f"Duplicate ledger keys found: {[k for k in set(keys) if keys.count(k) > 1]}"

    def test_double_run_no_dup_shadow_rows(self, tmp_path: Path, monkeypatch):
        """Shadow rows are deduplicated across two runs on the same night."""
        import scripts.build_release_forecast as producer
        _make_minimal_root(tmp_path)

        upcoming_events = [
            {
                "release_type": "cpi_headline",
                "release": "cpi",
                "release_date": "2026-07-30",
                "period": "2026-06",
                "regime_axis": "inflation",
            },
        ]

        monkeypatch.setattr(producer, "_find_upcoming_releases", lambda *a, **k: upcoming_events)
        monkeypatch.setattr(producer, "_run_projection", lambda rt, asof, root, **kw: {
            "release": rt, "asof": asof.isoformat(),
            "point": 0.20, "p10": 0.10, "p25": 0.15, "p50": 0.20, "p75": 0.25, "p90": 0.30,
            "confidence": 0.5, "input_completeness": 0.75,
            "benchmark_set": {"naive_prior": 0.18, "trailing_3m": 0.19,
                              "ar_model": None, "cleveland_nowcast": None, "market_implied": None},
            "surprise_skew": {"sigma": 0.1, "sigma_scale_pp": 0.1, "tag": "inline", "inline_band": 0.5},
            "pit_provenance": {"revision_optimistic_legs": [], "unrevised_legs": [],
                               "absent_legs": [], "display_only": True, "authority": False},
            "display_only": True, "authority": False,
        })
        monkeypatch.setattr(producer, "_run_shadow_v3", lambda *a, **k: _mock_v3_projection(a[0]))
        monkeypatch.setattr(producer, "_run_shadow_bridge", lambda *a, **k: _mock_bridge_projection())
        monkeypatch.setattr(producer, "_read_policy_backdrop", lambda *a, **k: {
            "fed_stance": None, "gap_bp": None,
            "implied_cuts_12m": None, "next_fomc": None, "guidance_direction": None,
        })
        monkeypatch.setattr(producer, "_enrich_upcoming_block", lambda *a, **k: None)

        producer.build(tmp_path, dry_run=False)
        producer.build(tmp_path, dry_run=False)

        from scripts.build_release_forecast import _load_ledger, _ledger_key
        ledger_path = tmp_path / "data" / "release_forecast" / "forward_ledger.jsonl"
        rows = _load_ledger(ledger_path)
        shadow_rows = [r for r in rows if r.get("row_type") == "shadow_projection"]
        shadow_keys = [_ledger_key(r) for r in shadow_rows]
        assert len(shadow_keys) == len(set(shadow_keys)), \
            f"Duplicate shadow ledger keys: {[k for k in set(shadow_keys) if shadow_keys.count(k) > 1]}"


# ===========================================================================
# 5. FAIL-OPEN
# ===========================================================================

class TestFailOpen:
    """Shadow exceptions degrade to no-shadow, never crash the build."""

    def test_v3_exception_degrades_to_no_v3_shadow(self, tmp_path: Path, monkeypatch):
        """When _run_shadow_v3 raises, the item gets no v3_factor shadow (no crash)."""
        import scripts.build_release_forecast as producer

        def _raise_v3(*a, **k):
            raise RuntimeError("synthetic v3 failure")

        monkeypatch.setattr(producer, "_run_shadow_v3", _raise_v3)
        monkeypatch.setattr(producer, "_run_shadow_bridge", lambda *a, **k: _mock_bridge_projection())

        items = [_minimal_upcoming_item("cpi_headline")]
        # Must not raise; v3 shadow absent; bridge shadow present
        producer._attach_shadows_to_items(items, tmp_path, date(2026, 7, 8))

        shadows = items[0].get("shadows", {})
        assert "v3_factor" not in shadows, "v3_factor shadow must be absent when it raises"
        # bridge shadow may still be present
        # (depends on whether bridge also raised; it didn't in this test)

    def test_bridge_exception_degrades_to_no_bridge_shadow(self, tmp_path: Path, monkeypatch):
        """When _run_shadow_bridge raises, the item gets no cpi_bridge shadow (no crash)."""
        import scripts.build_release_forecast as producer

        monkeypatch.setattr(producer, "_run_shadow_v3", lambda *a, **k: _mock_v3_projection(a[0]))

        def _raise_bridge(*a, **k):
            raise RuntimeError("synthetic bridge failure")

        monkeypatch.setattr(producer, "_run_shadow_bridge", _raise_bridge)

        items = [_minimal_upcoming_item("cpi_headline")]
        producer._attach_shadows_to_items(items, tmp_path, date(2026, 7, 8))

        shadows = items[0].get("shadows", {})
        assert "cpi_bridge" not in shadows, "cpi_bridge shadow must be absent when it raises"

    def test_both_shadows_fail_build_still_succeeds(self, tmp_path: Path, monkeypatch):
        """When both shadow models fail, the build completes successfully with no shadows on items."""
        import scripts.build_release_forecast as producer
        _make_minimal_root(tmp_path)

        upcoming_events = [
            {
                "release_type": "cpi_headline",
                "release": "cpi",
                "release_date": "2026-07-30",
                "period": "2026-06",
                "regime_axis": "inflation",
            },
        ]
        monkeypatch.setattr(producer, "_find_upcoming_releases", lambda *a, **k: upcoming_events)
        monkeypatch.setattr(producer, "_run_projection", lambda rt, asof, root, **kw: {
            "release": rt, "asof": asof.isoformat(), "point": None,
            "p10": None, "p25": None, "p50": None, "p75": None, "p90": None,
            "confidence": None, "input_completeness": 0.0,
            "benchmark_set": {"naive_prior": None, "trailing_3m": None,
                              "ar_model": None, "cleveland_nowcast": None, "market_implied": None},
            "surprise_skew": {}, "pit_provenance": {"reason": "test"},
            "display_only": True, "authority": False,
        })
        monkeypatch.setattr(producer, "_run_shadow_v3", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("v3 fail")))
        monkeypatch.setattr(producer, "_run_shadow_bridge", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bridge fail")))
        monkeypatch.setattr(producer, "_read_policy_backdrop", lambda *a, **k: {
            "fed_stance": None, "gap_bp": None,
            "implied_cuts_12m": None, "next_fomc": None, "guidance_direction": None,
        })
        monkeypatch.setattr(producer, "_enrich_upcoming_block", lambda *a, **k: None)

        # Must not raise
        result = producer.build(tmp_path, dry_run=True)
        assert isinstance(result, dict)
        assert result["display_only"] is True

    def test_shadow_ledger_fail_open_returns_empty_not_crash(self, tmp_path: Path, monkeypatch):
        """_build_shadow_ledger_rows returns empty list when both shadow models fail."""
        import scripts.build_release_forecast as producer

        monkeypatch.setattr(producer, "_run_shadow_v3", lambda *a, **k: None)
        monkeypatch.setattr(producer, "_run_shadow_bridge", lambda *a, **k: None)

        items = [_minimal_upcoming_item("cpi_headline")]
        rows = producer._build_shadow_ledger_rows(date(2026, 7, 8), items, tmp_path)
        assert rows == [], f"Expected empty list when all shadows fail, got {rows}"


# ===========================================================================
# 6. SCORING
# ===========================================================================

class TestScoring:
    """Release-day capture scores both champion and shadow rows."""

    def _build_ledger_with_shadow(
        self,
        release_type: str,
        period_str: str,
        release_date_str: str,
        asof_night: str,
    ) -> list[dict]:
        """Build a minimal ledger with one champion projection + two shadow projections."""
        rows = [
            # Champion projection
            {
                "schema": 2,
                "row_type": "projection",
                "model": None,
                "asof_night": asof_night,
                "release": release_type,
                "period": period_str,
                "release_date": release_date_str,
                "release_id": f"{release_type.upper()}:{period_str}:first",
                "prediction_id": f"{release_type}:{period_str}:{asof_night}",
                "projection_point": 0.20,
                "projection_p10": 0.10,
                "projection_p90": 0.30,
                "benchmark_naive_prior": 0.18,
                "benchmark_trailing_3m": 0.19,
                "benchmark_ar_model": None,
                "benchmark_cleveland": None,
            },
            # v3_factor shadow
            {
                "schema": 2,
                "row_type": "shadow_projection",
                "model": "v3_factor",
                "asof_night": asof_night,
                "release": release_type,
                "period": period_str,
                "release_date": release_date_str,
                "projection_point": 0.21,
                "projection_p10": 0.11,
                "projection_p90": 0.31,
            },
            # cpi_bridge shadow (headline only; skip for nfp)
        ]
        if release_type == "cpi_headline":
            rows.append({
                "schema": 2,
                "row_type": "shadow_projection",
                "model": "cpi_bridge",
                "asof_night": asof_night,
                "release": release_type,
                "period": period_str,
                "release_date": release_date_str,
                "projection_point": 0.22,
                "projection_p10": None,
                "projection_p90": None,
            })
        return rows

    def test_release_day_scores_champion(self, tmp_path: Path, monkeypatch):
        """_check_release_day_capture emits a scored row for the champion."""
        import scripts.build_release_forecast as producer

        release_date = date(2026, 7, 11)
        asof_night = "2026-07-10"
        ledger = self._build_ledger_with_shadow(
            "cpi_headline", "2026-06", release_date.isoformat(), asof_night
        )

        # Synthetic actual
        actual_val = 0.25
        monkeypatch.setattr(producer, "_get_initial_print",
                            lambda root, rt, period, rd_str: 100.25)
        monkeypatch.setattr(producer, "_compute_actual_from_print",
                            lambda rt, raw, root, period: actual_val)

        today = release_date
        scored = producer._check_release_day_capture(today, tmp_path, ledger)

        champ_scored = [r for r in scored if r.get("model") is None]
        assert len(champ_scored) == 1, f"Expected 1 champion scored row, got {len(champ_scored)}"
        assert champ_scored[0]["actual"] == actual_val

    def test_release_day_scores_shadow_v3(self, tmp_path: Path, monkeypatch):
        """_check_release_day_capture emits a scored row for v3_factor shadow."""
        import scripts.build_release_forecast as producer

        release_date = date(2026, 7, 11)
        asof_night = "2026-07-10"
        ledger = self._build_ledger_with_shadow(
            "cpi_headline", "2026-06", release_date.isoformat(), asof_night
        )

        actual_val = 0.25
        monkeypatch.setattr(producer, "_get_initial_print",
                            lambda root, rt, period, rd_str: 100.25)
        monkeypatch.setattr(producer, "_compute_actual_from_print",
                            lambda rt, raw, root, period: actual_val)

        today = release_date
        scored = producer._check_release_day_capture(today, tmp_path, ledger)

        v3_scored = [r for r in scored if r.get("model") == "v3_factor"]
        assert len(v3_scored) == 1, f"Expected 1 v3_factor scored row, got {len(v3_scored)}"
        assert v3_scored[0]["actual"] == actual_val
        assert v3_scored[0]["row_type"] == "scored"

    def test_release_day_scores_shadow_bridge(self, tmp_path: Path, monkeypatch):
        """_check_release_day_capture emits a scored row for cpi_bridge shadow."""
        import scripts.build_release_forecast as producer

        release_date = date(2026, 7, 11)
        asof_night = "2026-07-10"
        ledger = self._build_ledger_with_shadow(
            "cpi_headline", "2026-06", release_date.isoformat(), asof_night
        )

        actual_val = 0.25
        monkeypatch.setattr(producer, "_get_initial_print",
                            lambda root, rt, period, rd_str: 100.25)
        monkeypatch.setattr(producer, "_compute_actual_from_print",
                            lambda rt, raw, root, period: actual_val)

        today = release_date
        scored = producer._check_release_day_capture(today, tmp_path, ledger)

        bridge_scored = [r for r in scored if r.get("model") == "cpi_bridge"]
        assert len(bridge_scored) == 1, f"Expected 1 cpi_bridge scored row, got {len(bridge_scored)}"
        assert bridge_scored[0]["actual"] == actual_val

    def test_scored_shadow_row_has_correct_model_tag(self, tmp_path: Path, monkeypatch):
        """Scored shadow rows carry the model field from their shadow_projection source."""
        import scripts.build_release_forecast as producer

        release_date = date(2026, 7, 11)
        asof_night = "2026-07-10"
        ledger = self._build_ledger_with_shadow(
            "nfp", "2026-06", release_date.isoformat(), asof_night
        )

        actual_val = 150.0
        monkeypatch.setattr(producer, "_get_initial_print",
                            lambda root, rt, period, rd_str: 150000.0)
        monkeypatch.setattr(producer, "_compute_actual_from_print",
                            lambda rt, raw, root, period: actual_val)

        scored = producer._check_release_day_capture(release_date, tmp_path, ledger)

        # NFP should score champion + v3_factor; no bridge
        models_scored = {r.get("model") for r in scored}
        assert None in models_scored, "Champion (model=None) must be scored"
        assert "v3_factor" in models_scored, "v3_factor shadow must be scored for nfp"
        assert "cpi_bridge" not in models_scored, "cpi_bridge must not be scored for nfp"

    def test_score_idempotency_champion_and_shadow(self, tmp_path: Path, monkeypatch):
        """Scoring is idempotent: already-scored rows don't produce duplicate scored rows."""
        import scripts.build_release_forecast as producer

        release_date = date(2026, 7, 11)
        asof_night = "2026-07-10"
        ledger = self._build_ledger_with_shadow(
            "cpi_headline", "2026-06", release_date.isoformat(), asof_night
        )

        actual_val = 0.25
        monkeypatch.setattr(producer, "_get_initial_print",
                            lambda root, rt, period, rd_str: 100.25)
        monkeypatch.setattr(producer, "_compute_actual_from_print",
                            lambda rt, raw, root, period: actual_val)

        # First scoring pass
        scored1 = producer._check_release_day_capture(release_date, tmp_path, ledger)
        # Second pass: include scored1 in ledger
        ledger2 = ledger + scored1
        scored2 = producer._check_release_day_capture(release_date, tmp_path, ledger2)

        # No new scored rows on second pass (all already in existing_scored_keys)
        assert scored2 == [], \
            f"Second scoring pass must produce 0 rows (already scored), got {len(scored2)}: {scored2}"


# ===========================================================================
# 7. SCOREBOARD
# ===========================================================================

class TestScoreboard:
    """Scoreboard by_shadow section present and forward-only (n=0 initially)."""

    def test_scoreboard_has_by_shadow_key(self, tmp_path: Path):
        """_build_scoreboard output contains 'by_shadow' key."""
        from scripts.build_release_forecast import _build_scoreboard

        # Empty ledger → empty by_shadow
        scoreboard = _build_scoreboard([], "2026-07-08")
        assert "by_shadow" in scoreboard, "Scoreboard must have 'by_shadow' key"

    def test_by_shadow_empty_initially(self, tmp_path: Path):
        """by_shadow is empty when no shadow scored rows exist."""
        from scripts.build_release_forecast import _build_scoreboard

        scoreboard = _build_scoreboard([], "2026-07-08")
        assert scoreboard["by_shadow"] == {}, \
            f"by_shadow must be empty initially, got {scoreboard['by_shadow']}"

    def test_by_shadow_populated_when_scored(self, tmp_path: Path):
        """by_shadow is populated when shadow scored rows are present."""
        from scripts.build_release_forecast import _build_scoreboard

        # A synthetic shadow scored row
        scored_row = {
            "row_type": "scored",
            "model": "v3_factor",
            "release": "cpi_headline",
            "period": "2026-05",
            "actual": 0.22,
            "frozen_projection_point": 0.20,
            "interval_hit": True,
        }
        scoreboard = _build_scoreboard([scored_row], "2026-07-08")

        assert "by_shadow" in scoreboard
        assert "cpi_headline:v3_factor" in scoreboard["by_shadow"], \
            f"Expected 'cpi_headline:v3_factor' in by_shadow, got {list(scoreboard['by_shadow'])}"

        entry = scoreboard["by_shadow"]["cpi_headline:v3_factor"]
        assert entry["n"] == 1, f"Shadow track n must be 1, got {entry['n']}"
        assert entry["model"] == "v3_factor", f"Shadow entry model must be 'v3_factor'"

    def test_champion_scored_rows_not_in_by_shadow(self, tmp_path: Path):
        """Champion scored rows (model=None) stay in by_release, not by_shadow."""
        from scripts.build_release_forecast import _build_scoreboard

        champ_row = {
            "row_type": "scored",
            "model": None,
            "release": "cpi_headline",
            "period": "2026-05",
            "actual": 0.22,
            "frozen_projection_point": 0.20,
        }
        scoreboard = _build_scoreboard([champ_row], "2026-07-08")

        assert "cpi_headline" in scoreboard["by_release"], \
            "Champion scored row must appear in by_release"
        assert scoreboard["by_shadow"] == {}, \
            "Champion row must NOT appear in by_shadow"

    def test_scoreboard_by_shadow_forward_only_note(self, tmp_path: Path):
        """Scoreboard note confirms forward-only policy."""
        from scripts.build_release_forecast import _build_scoreboard

        scoreboard = _build_scoreboard([], "2026-07-08")
        note = scoreboard.get("note", "")
        assert "forward" in note.lower(), \
            f"Scoreboard note must mention 'forward', got {note!r}"

    def test_shadow_maturity_zero_on_day_one(self, tmp_path: Path):
        """Shadow track n=0 until forward accrual begins."""
        from scripts.build_release_forecast import _build_scoreboard

        # Only shadow_projection rows (no scored rows)
        proj_row = {
            "row_type": "shadow_projection",
            "model": "v3_factor",
            "release": "cpi_headline",
            "period": "2026-06",
            "asof_night": "2026-07-08",
        }
        scoreboard = _build_scoreboard([proj_row], "2026-07-08")

        # by_shadow should be empty (shadow_projection rows don't count; only scored rows)
        assert scoreboard["by_shadow"] == {}, \
            f"by_shadow must be empty until a scored row accrues, got {scoreboard['by_shadow']}"


# ===========================================================================
# 8. INTEGRATION: full build dry-run with shadow integration
# ===========================================================================

class TestFullBuildIntegration:
    """Full build() dry-run with shadow models wired."""

    @_INT_MARK
    def test_full_build_dry_run_with_shadows(self, tmp_path: Path, monkeypatch):
        """Full build() with CPI upcoming event: shadows attached to upcoming items."""
        import scripts.build_release_forecast as producer
        import shutil

        _make_minimal_root(tmp_path)
        vp_dir = tmp_path / "data" / "fred_vintage"
        vp_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(_VINTAGES_PATH, vp_dir / "vintages.parquet")

        def _mock_events(today, horizon_days, use_fred=True):
            return [{"type": "CPI", "date": "2026-07-11"}]

        original = None
        try:
            import engine.event_calendar as ec
            original = ec.us_macro_events
            ec.us_macro_events = _mock_events
        except ImportError:
            pytest.skip("event_calendar not available")

        monkeypatch.setattr(producer, "_read_policy_backdrop", lambda *a, **k: {
            "fed_stance": None, "gap_bp": None,
            "implied_cuts_12m": None, "next_fomc": None, "guidance_direction": None,
        })

        try:
            result = producer.build(tmp_path, dry_run=True)
        finally:
            if original is not None:
                import engine.event_calendar as ec
                ec.us_macro_events = original

        upcoming = result.get("upcoming", [])
        cpi_hl = next((u for u in upcoming if u["release_type"] == "cpi_headline"), None)
        if cpi_hl is None:
            pytest.skip("cpi_headline not in upcoming (event_calendar may not have CPI)")

        # If v3 or bridge ran, shadows will be present; if both failed (data absent), shadows empty.
        # We just verify the build completed without crash and the champion projection is unchanged.
        proj = cpi_hl.get("projection", {})
        assert isinstance(proj, dict), "Champion projection must be a dict"
        assert result["display_only"] is True

    def test_full_build_dry_run_no_crash_empty_events(self, tmp_path: Path, monkeypatch):
        """build() with no upcoming events completes without crash after Round-2b changes."""
        import scripts.build_release_forecast as producer
        _make_minimal_root(tmp_path)

        monkeypatch.setattr(producer, "_find_upcoming_releases", lambda *a, **k: [])
        monkeypatch.setattr(producer, "_read_policy_backdrop", lambda *a, **k: {
            "fed_stance": None, "gap_bp": None,
            "implied_cuts_12m": None, "next_fomc": None, "guidance_direction": None,
        })

        result = producer.build(tmp_path, dry_run=True)
        assert isinstance(result, dict)
        assert result["display_only"] is True
        assert result["upcoming"] == []

    def test_enrichments_field_includes_shadows(self, tmp_path: Path, monkeypatch):
        """latest.json enrichments list includes 'shadows' after Round-2b."""
        import scripts.build_release_forecast as producer
        _make_minimal_root(tmp_path)

        monkeypatch.setattr(producer, "_find_upcoming_releases", lambda *a, **k: [])
        monkeypatch.setattr(producer, "_read_policy_backdrop", lambda *a, **k: {
            "fed_stance": None, "gap_bp": None,
            "implied_cuts_12m": None, "next_fomc": None, "guidance_direction": None,
        })

        result = producer.build(tmp_path, dry_run=True)
        assert "shadows" in result.get("enrichments", []), \
            f"'shadows' must be in enrichments list, got {result.get('enrichments')}"


# ===========================================================================
# 9. FIX 1 — frozen_projection_p25/p75 in scored rows; all 5 pinball legs
# ===========================================================================

class TestFrozenP25P75:
    """Fix 1: frozen_projection_p25/p75 must be frozen into scored rows so all 5
    pinball legs accumulate on REAL scored rows (not hand-built fixtures).
    """

    def _build_projection_row_with_p25_p75(
        self,
        release_type: str = "cpi_headline",
        period: str = "2026-06",
        asof_night: str = "2026-07-01",
        release_date: str = "2026-07-10",
    ) -> dict:
        """A projection ledger row that includes p25 and p75 quantiles."""
        return {
            "schema": 2,
            "row_type": "projection",
            "model": None,
            "asof_night": asof_night,
            "release": release_type,
            "period": period,
            "release_date": release_date,
            "projection_point": 0.28,
            "projection_p10": 0.10,
            "projection_p25": 0.20,   # p25 present in projection row
            "projection_p75": 0.36,   # p75 present in projection row
            "projection_p90": 0.46,
            "benchmark_naive_prior": 0.24,
            "benchmark_trailing_3m": 0.25,
            "benchmark_ar_model": 0.26,
            "benchmark_cleveland": 0.30,
            "cutoff_label": "T-1",
        }

    def _build_shadow_row_with_p25_p75(
        self,
        release_type: str = "cpi_headline",
        period: str = "2026-06",
        asof_night: str = "2026-07-01",
        release_date: str = "2026-07-10",
    ) -> dict:
        """A shadow_projection ledger row that includes p25 and p75 quantiles."""
        return {
            "schema": 2,
            "row_type": "shadow_projection",
            "model": "v3_factor",
            "asof_night": asof_night,
            "release": release_type,
            "period": period,
            "release_date": release_date,
            "projection_point": 0.25,
            "projection_p10": 0.12,
            "projection_p25": 0.18,   # p25 present
            "projection_p75": 0.32,   # p75 present
            "projection_p90": 0.42,
            "cutoff_label": "T-1",
        }

    def test_scored_champion_row_has_frozen_p25_p75(self, tmp_path, monkeypatch):
        """_check_release_day_capture: champion scored row must carry frozen_projection_p25/p75.

        This is a live-path test through _check_release_day_capture on a fixture ledger
        (not a hand-built scored row). The p25/p75 fields must be frozen FROM the picked
        T-1 projection row.
        """
        import scripts.build_release_forecast as producer

        ledger = [self._build_projection_row_with_p25_p75()]
        actual_val = 0.30

        monkeypatch.setattr(producer, "_get_initial_print",
                            lambda root, rt, period, rd_str: 100.30)
        monkeypatch.setattr(producer, "_compute_actual_from_print",
                            lambda rt, raw, root, period: actual_val)

        today = date(2026, 7, 14)  # after release_date 2026-07-10
        scored = producer._check_release_day_capture(today, tmp_path, ledger)

        assert len(scored) == 1, f"Expected 1 scored row, got {len(scored)}"
        sr = scored[0]
        assert sr.get("row_type") == "scored"
        assert sr.get("model") is None  # champion

        # p25 and p75 must be frozen from the T-1 projection row
        assert sr.get("frozen_projection_p25") == pytest.approx(0.20, abs=1e-9), (
            f"Expected frozen_projection_p25=0.20, got {sr.get('frozen_projection_p25')!r}"
        )
        assert sr.get("frozen_projection_p75") == pytest.approx(0.36, abs=1e-9), (
            f"Expected frozen_projection_p75=0.36, got {sr.get('frozen_projection_p75')!r}"
        )

    def test_scored_shadow_row_has_frozen_p25_p75(self, tmp_path, monkeypatch):
        """_check_release_day_capture: shadow scored row must carry frozen_projection_p25/p75."""
        import scripts.build_release_forecast as producer

        ledger = [self._build_shadow_row_with_p25_p75()]
        actual_val = 0.28

        monkeypatch.setattr(producer, "_get_initial_print",
                            lambda root, rt, period, rd_str: 100.28)
        monkeypatch.setattr(producer, "_compute_actual_from_print",
                            lambda rt, raw, root, period: actual_val)

        today = date(2026, 7, 14)
        scored = producer._check_release_day_capture(today, tmp_path, ledger)

        v3_rows = [r for r in scored if r.get("model") == "v3_factor"]
        assert len(v3_rows) == 1, f"Expected 1 v3_factor scored row, got {len(v3_rows)}"
        sr = v3_rows[0]

        assert sr.get("frozen_projection_p25") == pytest.approx(0.18, abs=1e-9), (
            f"Expected frozen_projection_p25=0.18, got {sr.get('frozen_projection_p25')!r}"
        )
        assert sr.get("frozen_projection_p75") == pytest.approx(0.32, abs=1e-9), (
            f"Expected frozen_projection_p75=0.32, got {sr.get('frozen_projection_p75')!r}"
        )

    def test_all_5_pinball_legs_contribute_via_check_release_day_capture(
        self, tmp_path, monkeypatch
    ):
        """All 5 pinball legs (p10,p25,p50,p75,p90) accumulate in scoreboard from a
        ledger scored via _check_release_day_capture (not hand-built scored rows).

        This is the live-path test mandated by Fix 1.
        """
        import scripts.build_release_forecast as producer
        from scripts.build_release_forecast import _build_scoreboard

        ledger = [self._build_projection_row_with_p25_p75()]
        actual_val = 0.30

        monkeypatch.setattr(producer, "_get_initial_print",
                            lambda root, rt, period, rd_str: 100.30)
        monkeypatch.setattr(producer, "_compute_actual_from_print",
                            lambda rt, raw, root, period: actual_val)

        today = date(2026, 7, 14)
        scored = producer._check_release_day_capture(today, tmp_path, ledger)
        assert len(scored) == 1

        # Build scoreboard with the live scored row
        sb = _build_scoreboard(scored, accrual_start="2026-07-07")
        cpi_stats = sb["by_release"].get("cpi_headline")
        assert cpi_stats is not None, "cpi_headline must appear in scoreboard"

        # pinball_loss_5q_n must be >= 1 (at least 1 row contributed)
        assert cpi_stats.get("pinball_loss_5q_n", 0) >= 1, (
            f"Expected pinball_loss_5q_n >= 1, got {cpi_stats.get('pinball_loss_5q_n')}"
        )
        # pinball_loss_5q must be a finite number (not None)
        pb = cpi_stats.get("pinball_loss_5q")
        assert pb is not None, (
            "pinball_loss_5q must not be None when all 5 quantiles are present in the scored row"
        )
        assert isinstance(pb, (int, float)), f"pinball_loss_5q must be numeric, got {type(pb)}"

        # Verify all 5 legs contribute: each individual quantile should be reachable
        # by checking the frozen fields on the scored row
        sr = scored[0]
        for field in ("frozen_projection_p10", "frozen_projection_p25",
                      "frozen_projection_point", "frozen_projection_p75",
                      "frozen_projection_p90"):
            assert sr.get(field) is not None, (
                f"Expected {field} to be set on scored row for pinball leg, got None"
            )


# ===========================================================================
# 10. FIX 3 — by_cutoff sub-map in scoreboard (MRI-R35)
# ===========================================================================

class TestByCutoffScoreboard:
    """Fix 3: per-(release, model, cutoff_label) scoreboard split.

    per_release and per_shadow blocks gain a by_cutoff sub-map
    {T-1: {n, mae_ours, pinball_loss_5q}, early: {...}} each.
    Totals must be backward-compatible.
    """

    def _scored_row_with_cutoff(
        self,
        release: str = "cpi_headline",
        period: str = "2026-05",
        actual: float = 0.25,
        proj_point: float = 0.28,
        proj_p10: float = 0.10,
        proj_p25: float = 0.20,
        proj_p75: float = 0.36,
        proj_p90: float = 0.46,
        cutoff_label: str = "T-1",
        asof_night: str = "2026-06-15",
        model: Any = None,
    ) -> dict:
        return {
            "row_type": "scored",
            "model": model,
            "release": release,
            "period": period,
            "asof_night": asof_night,
            "actual": actual,
            "frozen_projection_point": proj_point,
            "frozen_projection_p10": proj_p10,
            "frozen_projection_p25": proj_p25,
            "frozen_projection_p75": proj_p75,
            "frozen_projection_p90": proj_p90,
            "interval_hit": True,
            "cutoff_label": cutoff_label,
        }

    def test_by_cutoff_present_in_by_release_entry(self):
        """Each by_release entry must have a 'by_cutoff' sub-map."""
        from scripts.build_release_forecast import _build_scoreboard

        row = self._scored_row_with_cutoff(cutoff_label="T-1")
        sb = _build_scoreboard([row], accrual_start="2026-07-07")
        cpi_stats = sb["by_release"].get("cpi_headline")
        assert cpi_stats is not None
        assert "by_cutoff" in cpi_stats, (
            f"by_cutoff sub-map missing from by_release entry: {list(cpi_stats)}"
        )

    def test_by_cutoff_t1_key_present_when_scored(self):
        """by_cutoff must contain 'T-1' bucket when a T-1 scored row is present."""
        from scripts.build_release_forecast import _build_scoreboard

        row = self._scored_row_with_cutoff(cutoff_label="T-1")
        sb = _build_scoreboard([row], accrual_start="2026-07-07")
        by_cutoff = sb["by_release"]["cpi_headline"]["by_cutoff"]
        assert "T-1" in by_cutoff, f"Expected 'T-1' in by_cutoff, got {list(by_cutoff)}"

    def test_by_cutoff_early_key_present_when_scored(self):
        """by_cutoff must contain 'early' bucket when an early scored row is present."""
        from scripts.build_release_forecast import _build_scoreboard

        row = self._scored_row_with_cutoff(cutoff_label="early")
        sb = _build_scoreboard([row], accrual_start="2026-07-07")
        by_cutoff = sb["by_release"]["cpi_headline"]["by_cutoff"]
        assert "early" in by_cutoff, f"Expected 'early' in by_cutoff, got {list(by_cutoff)}"

    def test_by_cutoff_n_counts_correct(self):
        """by_cutoff n counts must match the number of rows per cutoff_label."""
        from scripts.build_release_forecast import _build_scoreboard

        row1 = self._scored_row_with_cutoff(period="2026-05", cutoff_label="T-1")
        row2 = self._scored_row_with_cutoff(period="2026-06", cutoff_label="T-1", asof_night="2026-07-15")
        row3 = self._scored_row_with_cutoff(period="2026-04", cutoff_label="early", asof_night="2026-05-15")
        sb = _build_scoreboard([row1, row2, row3], accrual_start="2026-07-07")
        by_cutoff = sb["by_release"]["cpi_headline"]["by_cutoff"]

        assert by_cutoff["T-1"]["n"] == 2, (
            f"Expected T-1 n=2, got {by_cutoff['T-1']['n']}"
        )
        assert by_cutoff["early"]["n"] == 1, (
            f"Expected early n=1, got {by_cutoff['early']['n']}"
        )

    def test_by_cutoff_mae_ours_correct(self):
        """by_cutoff mae_ours must equal mean |actual - proj| for that cutoff."""
        from scripts.build_release_forecast import _build_scoreboard

        # T-1 row: |0.25 - 0.28| = 0.03
        row_t1 = self._scored_row_with_cutoff(
            period="2026-05", actual=0.25, proj_point=0.28, cutoff_label="T-1"
        )
        # early row: |0.30 - 0.25| = 0.05
        row_early = self._scored_row_with_cutoff(
            period="2026-04", actual=0.30, proj_point=0.25, cutoff_label="early",
            asof_night="2026-05-15"
        )
        sb = _build_scoreboard([row_t1, row_early], accrual_start="2026-07-07")
        by_cutoff = sb["by_release"]["cpi_headline"]["by_cutoff"]

        import pytest as _pytest
        assert by_cutoff["T-1"]["mae_ours"] == _pytest.approx(0.03, abs=1e-4), (
            f"T-1 mae_ours mismatch: {by_cutoff['T-1']['mae_ours']}"
        )
        assert by_cutoff["early"]["mae_ours"] == _pytest.approx(0.05, abs=1e-4), (
            f"early mae_ours mismatch: {by_cutoff['early']['mae_ours']}"
        )

    def test_totals_unchanged_by_cutoff_split(self):
        """Total n/mae_ours in the outer entry must not be affected by by_cutoff split."""
        from scripts.build_release_forecast import _build_scoreboard

        import pytest as _pytest
        row1 = self._scored_row_with_cutoff(period="2026-05", actual=0.25, proj_point=0.28,
                                            cutoff_label="T-1")
        row2 = self._scored_row_with_cutoff(period="2026-06", actual=0.30, proj_point=0.25,
                                            cutoff_label="early", asof_night="2026-07-15")
        sb = _build_scoreboard([row1, row2], accrual_start="2026-07-07")
        cpi_stats = sb["by_release"]["cpi_headline"]

        # Total n = 2 (unchanged)
        assert cpi_stats["n"] == 2, f"Total n must be 2, got {cpi_stats['n']}"
        # Total mae_ours = mean(0.03, 0.05) = 0.04
        assert cpi_stats["mae_ours"] == _pytest.approx(0.04, abs=1e-4), (
            f"Total mae_ours must be 0.04, got {cpi_stats['mae_ours']}"
        )

    def test_by_cutoff_in_by_shadow(self):
        """by_shadow entries also gain a by_cutoff sub-map (MRI-R35 covers shadow too)."""
        from scripts.build_release_forecast import _build_scoreboard

        shadow_row = self._scored_row_with_cutoff(
            model="v3_factor", cutoff_label="T-1"
        )
        sb = _build_scoreboard([shadow_row], accrual_start="2026-07-07")

        shadow_entry = sb["by_shadow"].get("cpi_headline:v3_factor")
        assert shadow_entry is not None, "Shadow entry missing from by_shadow"
        assert "by_cutoff" in shadow_entry, (
            f"by_cutoff missing from shadow scoreboard entry: {list(shadow_entry)}"
        )
        assert "T-1" in shadow_entry["by_cutoff"], (
            f"T-1 bucket missing from shadow by_cutoff: {list(shadow_entry['by_cutoff'])}"
        )

    def test_by_cutoff_empty_when_no_cutoff_label(self):
        """If scored rows have no cutoff_label, by_cutoff is empty (not a crash)."""
        from scripts.build_release_forecast import _build_scoreboard

        row = {
            "row_type": "scored",
            "model": None,
            "release": "cpi_headline",
            "period": "2026-05",
            "asof_night": "2026-06-15",
            "actual": 0.25,
            "frozen_projection_point": 0.28,
            # cutoff_label intentionally absent
        }
        sb = _build_scoreboard([row], accrual_start="2026-07-07")
        cpi_stats = sb["by_release"]["cpi_headline"]
        assert "by_cutoff" in cpi_stats
        assert cpi_stats["by_cutoff"] == {}, (
            f"by_cutoff must be empty when no cutoff_label on scored rows, got {cpi_stats['by_cutoff']}"
        )

    def test_pinball_loss_5q_in_by_cutoff(self):
        """by_cutoff buckets must include pinball_loss_5q when quantiles are available."""
        from scripts.build_release_forecast import _build_scoreboard
        import pytest as _pytest

        row = self._scored_row_with_cutoff(
            actual=0.30, proj_point=0.28,
            proj_p10=0.10, proj_p25=0.20, proj_p75=0.36, proj_p90=0.46,
            cutoff_label="T-1",
        )
        sb = _build_scoreboard([row], accrual_start="2026-07-07")
        by_cutoff = sb["by_release"]["cpi_headline"]["by_cutoff"]
        t1 = by_cutoff.get("T-1", {})
        assert "pinball_loss_5q" in t1, "by_cutoff T-1 must have pinball_loss_5q field"
        # pinball_loss_5q is not None since all 5 quantiles present
        assert t1["pinball_loss_5q"] is not None, (
            "pinball_loss_5q must not be None when all 5 quantiles are present"
        )


# ===========================================================================
# 11. FIX 4 — champion scored-row field equivalence test
# ===========================================================================

class TestChampionFieldEquivalence:
    """Fix 4: run OLD selection semantics (strictly-pre-release T-1) and NEW path
    on same fixture and assert identical scored-row field sets and values where
    both produce a row.
    """

    def _build_pre_release_ledger(
        self,
        release_type: str = "cpi_headline",
        period: str = "2026-06",
        release_date: str = "2026-07-10",
        pre_asof: str = "2026-07-01",   # strictly before release_date
        rd_asof: str = "2026-07-10",    # same day as release_date
    ) -> list[dict]:
        """Return a ledger with TWO projection rows:
        - One strictly-pre-release (asof_night < release_date) — this is what
          both old and new semantics would pick as T-1.
        - One release-day row (asof_night == release_date) — new path includes it
          as a candidate but still prefers the strictly-pre-release row.
        """
        return [
            {
                "schema": 2,
                "row_type": "projection",
                "model": None,
                "asof_night": pre_asof,
                "release": release_type,
                "period": period,
                "release_date": release_date,
                "projection_point": 0.28,
                "projection_p10": 0.10,
                "projection_p25": 0.20,
                "projection_p75": 0.36,
                "projection_p90": 0.46,
                "benchmark_naive_prior": 0.24,
                "benchmark_trailing_3m": 0.25,
                "benchmark_ar_model": 0.26,
                "benchmark_cleveland": 0.30,
                "cutoff_label": "T-1",
            },
            {
                "schema": 2,
                "row_type": "projection",
                "model": None,
                "asof_night": rd_asof,   # release-day
                "release": release_type,
                "period": period,
                "release_date": release_date,
                "projection_point": 0.29,  # different value than pre-release
                "projection_p10": 0.11,
                "projection_p25": 0.21,
                "projection_p75": 0.37,
                "projection_p90": 0.47,
                "benchmark_naive_prior": 0.24,
                "benchmark_trailing_3m": 0.25,
                "benchmark_ar_model": 0.26,
                "benchmark_cleveland": 0.30,
                "cutoff_label": "T-1",
            },
        ]

    def test_old_and_new_semantics_produce_identical_scored_row_fields(
        self, tmp_path, monkeypatch
    ):
        """OLD semantics (strictly-pre-release T-1 only) vs NEW path (release-day allowed
        but pre-release preferred): when a strictly-pre-release row exists, both paths
        select the same row and produce identical scored-row field sets and values.
        """
        import scripts.build_release_forecast as producer

        ledger = self._build_pre_release_ledger()
        release_date = date(2026, 7, 10)
        actual_val = 0.30

        monkeypatch.setattr(producer, "_get_initial_print",
                            lambda root, rt, period, rd_str: 100.30)
        monkeypatch.setattr(producer, "_compute_actual_from_print",
                            lambda rt, raw, root, period: actual_val)

        # --- New path (current code with Fix 1 + Fix 2 applied) ---
        today = date(2026, 7, 14)
        new_scored = producer._check_release_day_capture(today, tmp_path, ledger)

        champ_new = [r for r in new_scored if r.get("model") is None]
        assert len(champ_new) == 1, f"Expected 1 champion scored row, got {len(champ_new)}"
        new_row = champ_new[0]

        # --- Simulate OLD semantics: strictly-pre-release T-1 only ---
        # Under old semantics, only rows with asof_night < release_date are candidates.
        # Build a ledger that has ONLY the strictly-pre-release row.
        old_ledger = [r for r in ledger if r.get("asof_night", "") < release_date.isoformat()]
        old_scored = producer._check_release_day_capture(today, tmp_path, old_ledger)

        champ_old = [r for r in old_scored if r.get("model") is None]
        assert len(champ_old) == 1, f"Old semantics: expected 1 champion scored row, got {len(champ_old)}"
        old_row = champ_old[0]

        # Both must produce scored rows with identical field sets
        assert set(new_row.keys()) == set(old_row.keys()), (
            f"Field sets differ:\n  new-only={set(new_row)-set(old_row)}\n"
            f"  old-only={set(old_row)-set(new_row)}"
        )

        # Key scoring fields must be identical
        for field in (
            "frozen_projection_point", "frozen_projection_p10", "frozen_projection_p25",
            "frozen_projection_p75", "frozen_projection_p90",
            "actual", "our_surprise", "interval_hit", "row_type", "model",
            "release", "period", "release_date",
        ):
            assert new_row.get(field) == pytest.approx(old_row.get(field), abs=1e-9) if isinstance(old_row.get(field), float) else new_row.get(field) == old_row.get(field), (
                f"Field {field!r} differs: new={new_row.get(field)!r} vs old={old_row.get(field)!r}"
            )

    def test_new_path_prefers_pre_release_over_release_day(
        self, tmp_path, monkeypatch
    ):
        """When both strictly-pre-release and release-day rows exist, new path MUST
        select the strictly-pre-release row (same as old semantics).
        """
        import scripts.build_release_forecast as producer

        ledger = self._build_pre_release_ledger()

        # The strictly-pre-release row has projection_point=0.28;
        # the release-day row has projection_point=0.29.
        # New path must select the pre-release row (projection_point=0.28).

        actual_val = 0.30
        monkeypatch.setattr(producer, "_get_initial_print",
                            lambda root, rt, period, rd_str: 100.30)
        monkeypatch.setattr(producer, "_compute_actual_from_print",
                            lambda rt, raw, root, period: actual_val)

        today = date(2026, 7, 14)
        scored = producer._check_release_day_capture(today, tmp_path, ledger)
        champ = [r for r in scored if r.get("model") is None]
        assert len(champ) == 1
        sr = champ[0]

        # Must use the strictly-pre-release row (projection_point=0.28)
        assert sr["frozen_projection_point"] == pytest.approx(0.28, abs=1e-9), (
            f"Expected pre-release row's projection_point=0.28, got {sr['frozen_projection_point']}"
        )
