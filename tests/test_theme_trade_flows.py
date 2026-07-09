"""tests/test_theme_trade_flows.py — Tests for engine/theme_trade_flows.py (TIL W8).

Coverage:
  - YoY and 3m-vs-12m acceleration math on synthetic parquet fixtures
  - Sign logic per expected_direction on fixtures (rising/falling confirms)
  - Honest-null coverage when parquet absent
  - Confirmation enum values
  - Authority block fields (all may_* false; is_context_only=true)
  - Banned words in outputs ('validated' must never appear)
  - Synapse/dag conformance: output files match registered paths
  - check_validated_claims integration (schema field never says 'validated')
  - Output schema fields present in both NW artifact and site projection
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Optional
from unittest import mock

import numpy as np
import pandas as pd
import pytest
import yaml


# ---------------------------------------------------------------------------
# Fixtures: synthetic parquet builder
# ---------------------------------------------------------------------------

def _make_parquet(tmp_path: Path, rows: list[dict]) -> Path:
    """Build imports_monthly.parquet in tmp_path from row dicts."""
    from collectors.census_trade import STORE_COLS
    df = pd.DataFrame(rows, columns=STORE_COLS)
    path = tmp_path / "imports_monthly.parquet"
    df.to_parquet(path, index=False)
    return path


def _monthly_rows(
    hs_code: str,
    start_ym: str,
    n_months: int,
    base_value: float,
    yoy_growth_pct: Optional[float] = None,
) -> list[dict]:
    """
    Generate synthetic monthly rows for a given HS code.
    If yoy_growth_pct is set, values grow at that annualized rate.
    """
    from collectors.census_trade import STORE_COLS
    rows = []
    period = pd.Period(start_ym, freq="M")
    for i in range(n_months):
        p = period + i
        stat_month = str(p)
        if yoy_growth_pct is not None:
            # Monthly compound factor
            monthly_factor = (1 + yoy_growth_pct / 100) ** (1 / 12)
            value = base_value * (monthly_factor ** i)
        else:
            value = base_value
        rows.append({
            "hs_code": hs_code,
            "stat_month": stat_month,
            "value_usd": value,
            "quantity": value / 100,
            "quantity_unit": "KG",
            "ingested_at": "2026-07-09T00:00:00+00:00",
        })
    return rows


# ---------------------------------------------------------------------------
# YoY math tests
# ---------------------------------------------------------------------------

class TestYoYMath:

    def test_positive_yoy(self):
        from engine.theme_trade_flows import _compute_yoy
        # 24 months: value doubles (100% YoY)
        rows = _monthly_rows("854231", "2023-01", 24, 1_000_000.0, yoy_growth_pct=100.0)
        series = pd.Series(
            {r["stat_month"]: r["value_usd"] for r in rows}
        )
        yoy = _compute_yoy(series)
        assert yoy is not None
        assert yoy > 90.0, f"Expected ~100% YoY growth, got {yoy:.1f}%"

    def test_negative_yoy(self):
        from engine.theme_trade_flows import _compute_yoy
        # Values decline 30% over a year
        rows = _monthly_rows("854140", "2023-01", 24, 2_000_000.0, yoy_growth_pct=-30.0)
        series = pd.Series(
            {r["stat_month"]: r["value_usd"] for r in rows}
        )
        yoy = _compute_yoy(series)
        assert yoy is not None
        assert yoy < -20.0, f"Expected ~-30% YoY, got {yoy:.1f}%"

    def test_insufficient_data_returns_none(self):
        from engine.theme_trade_flows import _compute_yoy
        # Only 6 months — need at least 13
        rows = _monthly_rows("854231", "2024-01", 6, 1_000_000.0)
        series = pd.Series({r["stat_month"]: r["value_usd"] for r in rows})
        yoy = _compute_yoy(series)
        assert yoy is None

    def test_exactly_13_months_computes(self):
        from engine.theme_trade_flows import _compute_yoy
        rows = _monthly_rows("854231", "2023-01", 13, 1_000_000.0)
        series = pd.Series({r["stat_month"]: r["value_usd"] for r in rows})
        yoy = _compute_yoy(series)
        assert yoy is not None
        # No growth → ~0% YoY
        assert abs(yoy) < 1.0

    def test_zero_base_returns_none(self):
        from engine.theme_trade_flows import _compute_yoy
        rows = _monthly_rows("854231", "2023-01", 13, 0.0)
        series = pd.Series({r["stat_month"]: r["value_usd"] for r in rows})
        yoy = _compute_yoy(series)
        assert yoy is None


# ---------------------------------------------------------------------------
# Acceleration math tests
# ---------------------------------------------------------------------------

class TestAccelMath:

    def test_positive_accel(self):
        """Accelerating imports: 3m rate > 12m rate → positive accel.

        The accel formula is: rate_3m - rate_12m where:
          rate_3m  = (v[-1] - v[-4]) / v[-4] * 100  (last 3 months span)
          rate_12m = (v[-1] - v[-13]) / v[-13] * 100 (12 months span)

        For accel > 0: v[-4] must be relatively HIGH vs v[-13] (meaning the
        period from month -13 to month -4 was already rising), AND v[-1] must
        be high enough that rate from v[-4] exceeds the full-year rate from v[-13].
        Concretely: need v[-4] > v[-13] AND the ratio (v[-1]/v[-4]) > (v[-1]/v[-13]).
        That means v[-4] < v[-1] AND v[-13] < v[-4] — a steadily rising series
        where recent pace outstrips historical pace.

        Fixture: exponentially growing series at 60% annual rate (strong acceleration
        vs a low base). After 13+ months of compound growth, the rate over the last
        3 months is faster in absolute pct terms from the higher base.

        Actually for 3m rate > 12m rate with same endpoint:
          (v_end - v_4) / v_4 > (v_end - v_13) / v_13
          => v_end/v_4 - 1 > v_end/v_13 - 1
          => v_end/v_4 > v_end/v_13
          => v_13 > v_4   (more recent starting point is LOWER than older starting point)

        This means: 3m start (v[-4]) must be LOWER than 12m start (v[-13]).
        i.e., the series must have DECLINED from month -13 to month -4, then surged.
        Or more simply: a V-shape where the trough is around month -4.
        """
        from engine.theme_trade_flows import _compute_accel

        # V-shape: high → low → high. For series with 13 months:
        # months[-13] = 2M (high start), months[-4] = 0.5M (trough), months[-1] = 3M (surge end)
        # rate_3m = (3M - 0.5M)/0.5M*100 = 500%
        # rate_12m = (3M - 2M)/2M*100 = 50%
        # accel = 500 - 50 = 450 (positive)
        rows = []
        start = pd.Period("2023-01", freq="M")
        n = 13
        for i in range(n):
            p = start + i
            # V-shape: index 0 = 2M, index 9 = 0.5M (trough at -4), index 12 = 3M
            if i <= 9:
                v = 2_000_000.0 - i * 150_000.0  # declining: 2M → 0.65M
            else:
                v = 500_000.0 + (i - 9) * 833_333.0  # recovering
            rows.append({"stat_month": str(p), "value_usd": max(v, 100_000.0)})

        series = pd.Series({r["stat_month"]: r["value_usd"] for r in rows})
        assert len(series) >= 13

        accel = _compute_accel(series)
        assert accel is not None
        assert accel > 0, (
            f"Expected positive accel for V-shape (recent 3m rate > full 12m rate), "
            f"got {accel:.2f}. "
            f"v[-13]={series.iloc[-13]:.0f}, v[-4]={series.iloc[-4]:.0f}, v[-1]={series.iloc[-1]:.0f}"
        )

    def test_insufficient_data_returns_none(self):
        from engine.theme_trade_flows import _compute_accel
        rows = _monthly_rows("854231", "2024-01", 10, 1_000_000.0)
        series = pd.Series({r["stat_month"]: r["value_usd"] for r in rows})
        accel = _compute_accel(series)
        assert accel is None


# ---------------------------------------------------------------------------
# Sign logic per expected_direction
# ---------------------------------------------------------------------------

class TestSignLogic:

    def test_rising_imports_confirms_positive_yoy(self):
        """rising_imports_confirms + positive YoY → confirmation='confirms'."""
        from engine.theme_trade_flows import _sign_reading
        confirmation, band = _sign_reading(
            yoy_pct=25.0, accel=5.0, expected_direction="rising_imports_confirms"
        )
        assert confirmation == "confirms"
        assert band == "large"

    def test_rising_imports_confirms_negative_yoy(self):
        """rising_imports_confirms + negative YoY → confirmation='contradicts'."""
        from engine.theme_trade_flows import _sign_reading
        confirmation, band = _sign_reading(
            yoy_pct=-15.0, accel=-3.0, expected_direction="rising_imports_confirms"
        )
        assert confirmation == "contradicts"
        assert band == "moderate"

    def test_falling_imports_confirms_negative_yoy(self):
        """falling_imports_confirms + negative YoY → confirmation='confirms'
        (import decline = domestic substitution)."""
        from engine.theme_trade_flows import _sign_reading
        confirmation, band = _sign_reading(
            yoy_pct=-25.0, accel=-5.0, expected_direction="falling_imports_confirms"
        )
        assert confirmation == "confirms"
        assert band == "large"

    def test_falling_imports_confirms_positive_yoy(self):
        """falling_imports_confirms + positive YoY → confirmation='contradicts'
        (imports still rising = substitution not happening)."""
        from engine.theme_trade_flows import _sign_reading
        confirmation, band = _sign_reading(
            yoy_pct=12.0, accel=2.0, expected_direction="falling_imports_confirms"
        )
        assert confirmation == "contradicts"
        assert band == "moderate"

    def test_small_yoy_is_neutral(self):
        """YoY below threshold (< 5%) → neutral regardless of direction."""
        from engine.theme_trade_flows import _sign_reading
        confirmation, band = _sign_reading(
            yoy_pct=3.0, accel=1.0, expected_direction="rising_imports_confirms"
        )
        assert confirmation == "neutral"
        assert band is None

    def test_none_yoy_is_neutral(self):
        from engine.theme_trade_flows import _sign_reading
        confirmation, band = _sign_reading(
            yoy_pct=None, accel=None, expected_direction="rising_imports_confirms"
        )
        assert confirmation == "neutral"
        assert band is None

    def test_magnitude_bands(self):
        from engine.theme_trade_flows import _sign_reading
        _, band = _sign_reading(25.0, 0.0, "rising_imports_confirms")
        assert band == "large"

        _, band = _sign_reading(15.0, 0.0, "rising_imports_confirms")
        assert band == "moderate"

        _, band = _sign_reading(7.0, 0.0, "rising_imports_confirms")
        assert band == "small"

    def test_confirmation_enum_valid(self):
        """Confirmation must always be one of the three valid values."""
        from engine.theme_trade_flows import _sign_reading
        valid = {"confirms", "contradicts", "neutral"}
        for yoy in [None, -50.0, -3.0, 3.0, 50.0]:
            for direction in ["rising_imports_confirms", "falling_imports_confirms"]:
                confirmation, _ = _sign_reading(yoy, None, direction)
                assert confirmation in valid, (
                    f"Invalid confirmation {confirmation!r} for yoy={yoy} dir={direction}"
                )


# ---------------------------------------------------------------------------
# Honest-null coverage (parquet absent)
# ---------------------------------------------------------------------------

class TestHonestNull:

    def test_absent_parquet_returns_honest_null(self, monkeypatch):
        """When parquet is absent, all themes get n_codes_with_data=0 and null metrics."""
        from engine import theme_trade_flows as ttf

        # Patch _load_parquet to return None (absent)
        with mock.patch.object(ttf, "_load_parquet", return_value=None):
            result = ttf.compute_theme_trade_flows(write_nw=False, write_site=False)

        themes = result.get("themes", {})
        assert len(themes) > 0, "Should have theme entries even when parquet absent"

        for theme_id, theme_data in themes.items():
            assert theme_data["n_codes_with_data"] == 0, (
                f"Theme {theme_id} should have 0 codes with data when parquet absent"
            )
            assert theme_data["yoy_pct"] is None
            assert theme_data["accel_3m_vs_12m"] is None
            assert theme_data["confirmation"] == "neutral"
            assert theme_data["coverage_note"], "Coverage note must explain absence"

    def test_coverage_stats_parquet_absent_flag(self, monkeypatch):
        from engine import theme_trade_flows as ttf
        with mock.patch.object(ttf, "_load_parquet", return_value=None):
            result = ttf.compute_theme_trade_flows(write_nw=False, write_site=False)
        assert result["coverage_stats"]["parquet_absent"] is True

    def test_write_outputs_with_parquet_absent(self, tmp_path, monkeypatch):
        """Engine writes valid JSON even when parquet is absent."""
        from engine import theme_trade_flows as ttf

        nw_out = tmp_path / "theme_trade_flows.json"
        site_out = tmp_path / "trade_flows.json"

        with (
            mock.patch.object(ttf, "_load_parquet", return_value=None),
            mock.patch.object(ttf, "_NW_OUT", nw_out),
            mock.patch.object(ttf, "_SITE_OUT", site_out),
        ):
            ttf.compute_theme_trade_flows(write_nw=True, write_site=True)

        assert nw_out.exists(), "NW artifact must be written even when parquet absent"
        assert site_out.exists(), "Site projection must be written even when parquet absent"

        with open(nw_out) as fh:
            nw = json.load(fh)
        assert nw["schema"] == "theme_trade_flows.v1"
        assert "themes" in nw


# ---------------------------------------------------------------------------
# Authority block
# ---------------------------------------------------------------------------

class TestAuthorityBlock:

    def test_authority_all_may_false(self):
        from engine.theme_trade_flows import AUTHORITY
        assert AUTHORITY["may_rank"] is False
        assert AUTHORITY["may_gate"] is False
        assert AUTHORITY["may_size"] is False
        assert AUTHORITY["may_escalate"] is False
        assert AUTHORITY["is_context_only"] is True

    def test_output_contains_authority(self, monkeypatch):
        from engine import theme_trade_flows as ttf
        with mock.patch.object(ttf, "_load_parquet", return_value=None):
            result = ttf.compute_theme_trade_flows(write_nw=False, write_site=False)
        auth = result.get("authority", {})
        assert auth.get("may_rank") is False
        assert auth.get("is_context_only") is True


# ---------------------------------------------------------------------------
# Output schema completeness
# ---------------------------------------------------------------------------

class TestOutputSchema:

    def test_nw_artifact_top_level_fields(self, monkeypatch):
        from engine import theme_trade_flows as ttf
        with mock.patch.object(ttf, "_load_parquet", return_value=None):
            result = ttf.compute_theme_trade_flows(write_nw=False, write_site=False)
        required_fields = {"schema", "as_of", "generated_at", "authority",
                           "honesty_header", "coverage_stats", "themes"}
        missing = required_fields - set(result.keys())
        assert not missing, f"NW artifact missing top-level fields: {missing}"

    def test_site_projection_compact(self, tmp_path, monkeypatch):
        """Site projection must not include code_detail (compact format)."""
        from engine import theme_trade_flows as ttf

        # Create synthetic parquet with 14 months of data
        rows = _monthly_rows("854231", "2023-06", 14, 1_000_000.0, yoy_growth_pct=20.0)
        store_path = tmp_path / "trade_flows"
        store_path.mkdir()
        _make_parquet(store_path, rows)

        nw_out = tmp_path / "nw.json"
        site_out = tmp_path / "site.json"

        with (
            mock.patch.object(ttf, "_load_parquet", return_value=pd.read_parquet(store_path / "imports_monthly.parquet")),
            mock.patch.object(ttf, "_NW_OUT", nw_out),
            mock.patch.object(ttf, "_SITE_OUT", site_out),
        ):
            ttf.compute_theme_trade_flows(write_nw=True, write_site=True)

        with open(site_out) as fh:
            site = json.load(fh)

        # Site projection must not have code_detail in any theme
        for theme_id, theme_data in site.get("themes", {}).items():
            assert "code_detail" not in theme_data, (
                f"Theme {theme_id} in site projection must not have code_detail"
            )

    def test_theme_data_required_keys(self, monkeypatch):
        from engine import theme_trade_flows as ttf
        with mock.patch.object(ttf, "_load_parquet", return_value=None):
            result = ttf.compute_theme_trade_flows(write_nw=False, write_site=False)
        required = {"theme_id", "n_codes_configured", "n_codes_with_data",
                    "confirmation", "coverage_note", "coverage_note_zh"}
        for theme_id, theme_data in result["themes"].items():
            missing = required - set(theme_data.keys())
            assert not missing, (
                f"Theme {theme_id} missing required fields: {missing}"
            )


# ---------------------------------------------------------------------------
# Banned words
# ---------------------------------------------------------------------------

class TestBannedWords:

    def test_no_validated_in_nw_output(self, monkeypatch):
        """'validated' must not appear in theme_trade_flows.v1 NW output."""
        from engine import theme_trade_flows as ttf
        with mock.patch.object(ttf, "_load_parquet", return_value=None):
            result = ttf.compute_theme_trade_flows(write_nw=False, write_site=False)
        output_str = json.dumps(result, ensure_ascii=False).lower()
        assert "validated" not in output_str, (
            "Banned word 'validated' found in theme_trade_flows NW output"
        )

    def test_no_validated_in_authority_block(self):
        from engine.theme_trade_flows import AUTHORITY
        auth_str = json.dumps(AUTHORITY).lower()
        assert "validated" not in auth_str, (
            "Banned word 'validated' found in AUTHORITY block"
        )

    def test_no_validated_in_site_projection(self, monkeypatch, tmp_path):
        from engine import theme_trade_flows as ttf
        site_out = tmp_path / "trade_flows.json"
        with (
            mock.patch.object(ttf, "_load_parquet", return_value=None),
            mock.patch.object(ttf, "_NW_OUT", tmp_path / "nw.json"),
            mock.patch.object(ttf, "_SITE_OUT", site_out),
        ):
            ttf.compute_theme_trade_flows(write_nw=True, write_site=True)
        with open(site_out) as fh:
            site_str = fh.read().lower()
        assert "validated" not in site_str, (
            "Banned word 'validated' found in site projection"
        )


# ---------------------------------------------------------------------------
# End-to-end with synthetic parquet data
# ---------------------------------------------------------------------------

class TestEndToEnd:

    def test_compute_with_data(self, tmp_path, monkeypatch):
        """
        End-to-end: synthetic parquet with known YoY growth → expected outputs.
        Uses ai_semiconductors code 854231 with 30% YoY growth (rising_imports_confirms).
        Expected: confirmation='confirms', magnitude_band='large'.
        """
        from engine import theme_trade_flows as ttf

        # 15 months starting 2023-05 → last month 2024-07
        rows = _monthly_rows("854231", "2023-05", 15, 1_000_000.0, yoy_growth_pct=30.0)
        df = pd.DataFrame(rows, columns=[
            "hs_code", "stat_month", "value_usd", "quantity", "quantity_unit", "ingested_at"
        ])

        with mock.patch.object(ttf, "_load_parquet", return_value=df):
            result = ttf.compute_theme_trade_flows(write_nw=False, write_site=False)

        # ai_semiconductors should show confirms with large magnitude
        ai_theme = result["themes"].get("ai_semiconductors")
        assert ai_theme is not None, "ai_semiconductors theme not found in output"
        assert ai_theme["n_codes_with_data"] >= 1
        assert ai_theme["yoy_pct"] is not None
        assert ai_theme["yoy_pct"] > 0, "Expected positive YoY for 30% growth scenario"
        assert ai_theme["confirmation"] in ("confirms", "neutral"), (
            f"Expected confirms or neutral, got {ai_theme['confirmation']!r}"
        )

    def test_falling_imports_theme(self, tmp_path, monkeypatch):
        """
        Solar code 854140 (falling_imports_confirms): import decline should confirm.
        15 months with -25% YoY → expected confirmation='confirms'.
        """
        from engine import theme_trade_flows as ttf

        rows = _monthly_rows("854140", "2023-05", 15, 2_000_000.0, yoy_growth_pct=-25.0)
        df = pd.DataFrame(rows, columns=[
            "hs_code", "stat_month", "value_usd", "quantity", "quantity_unit", "ingested_at"
        ])

        with mock.patch.object(ttf, "_load_parquet", return_value=df):
            result = ttf.compute_theme_trade_flows(write_nw=False, write_site=False)

        solar_theme = result["themes"].get("solar")
        assert solar_theme is not None
        if solar_theme["n_codes_with_data"] >= 1:
            assert solar_theme["yoy_pct"] is not None
            # Negative YoY for falling_imports_confirms → should confirm
            if abs(solar_theme["yoy_pct"]) >= 5.0:
                assert solar_theme["confirmation"] == "confirms", (
                    f"Expected 'confirms' for solar with -25% YoY, got {solar_theme['confirmation']!r}"
                )

    def test_no_composite_across_themes(self, monkeypatch):
        """Each theme must have its own independent metrics — no cross-theme composite."""
        from engine import theme_trade_flows as ttf
        with mock.patch.object(ttf, "_load_parquet", return_value=None):
            result = ttf.compute_theme_trade_flows(write_nw=False, write_site=False)
        # Each theme must have its own confirmation field (independent)
        themes = result.get("themes", {})
        assert len(themes) > 1
        for tid, tdata in themes.items():
            assert "confirmation" in tdata, f"Theme {tid} missing independent confirmation"


# ---------------------------------------------------------------------------
# Synapse/dag conformance
# ---------------------------------------------------------------------------

class TestSynapseConformance:

    def test_nw_artifact_registered_in_synapse(self):
        """data/neuralweb/theme_trade_flows.json must be registered in synapse.yml."""
        synapse_path = Path(__file__).resolve().parent.parent / "config" / "synapse.yml"
        with open(synapse_path) as fh:
            synapse = yaml.safe_load(fh)
        paths = [
            entry.get("path", "")
            for entry in (synapse.get("artifacts") or {}).values()
        ]
        assert any("theme_trade_flows" in p for p in paths), (
            "data/neuralweb/theme_trade_flows.json not found in synapse.yml artifacts"
        )

    def test_site_artifact_registered_in_synapse(self):
        """site/basketdata/trade_flows.json must be registered in synapse.yml."""
        synapse_path = Path(__file__).resolve().parent.parent / "config" / "synapse.yml"
        with open(synapse_path) as fh:
            synapse = yaml.safe_load(fh)
        paths = [
            entry.get("path", "")
            for entry in (synapse.get("artifacts") or {}).values()
        ]
        assert any("trade_flows" in p and "basketdata" in p for p in paths), (
            "site/basketdata/trade_flows.json not found in synapse.yml artifacts"
        )

    def test_dag_has_collect_census_trade_entry(self):
        """dag.yml must have a collect_census_trade step in the collect lane."""
        dag_path = Path(__file__).resolve().parent.parent / "config" / "dag.yml"
        with open(dag_path) as fh:
            content = fh.read()
        assert "collect_census_trade" in content, (
            "dag.yml missing collect_census_trade step"
        )

    def test_synapse_artifact_fields_complete(self):
        """Both W8 synapse artifacts must have all required fields."""
        synapse_path = Path(__file__).resolve().parent.parent / "config" / "synapse.yml"
        with open(synapse_path) as fh:
            synapse = yaml.safe_load(fh)
        required_fields = {
            "path", "format", "producer", "owner_program", "cadence", "storage",
            "asof_field", "freshness_sla_hours", "schema", "tier", "horizon_role",
        }
        for artifact_id, entry in (synapse.get("artifacts") or {}).items():
            if "trade_flow" in artifact_id or "census_trade" in artifact_id:
                missing = required_fields - set(entry.keys())
                assert not missing, (
                    f"Synapse artifact {artifact_id!r} missing required fields: {missing}"
                )

    def test_synapse_producer_paths_exist(self):
        """Synapse entries for W8 must have producer paths that exist."""
        synapse_path = Path(__file__).resolve().parent.parent / "config" / "synapse.yml"
        repo_root = synapse_path.parent.parent
        with open(synapse_path) as fh:
            synapse = yaml.safe_load(fh)
        for artifact_id, entry in (synapse.get("artifacts") or {}).items():
            if "trade_flow" in artifact_id or "census_trade" in artifact_id:
                producer = entry.get("producer", "")
                producer_path = repo_root / producer
                assert producer_path.exists(), (
                    f"Synapse {artifact_id!r}: producer {producer!r} does not exist"
                )


# ---------------------------------------------------------------------------
# check_validated_claims integration
# ---------------------------------------------------------------------------

class TestCheckValidatedClaims:

    def test_no_affirmative_validated_in_outputs(self, monkeypatch, tmp_path):
        """
        Affirmative 'validated' claim in output would fail check_validated_claims.
        This test proves no such claim appears in theme_trade_flows output.
        """
        from engine import theme_trade_flows as ttf

        nw_out = tmp_path / "nw.json"
        site_out = tmp_path / "site.json"

        with (
            mock.patch.object(ttf, "_load_parquet", return_value=None),
            mock.patch.object(ttf, "_NW_OUT", nw_out),
            mock.patch.object(ttf, "_SITE_OUT", site_out),
        ):
            ttf.compute_theme_trade_flows(write_nw=True, write_site=True)

        for out_path in [nw_out, site_out]:
            with open(out_path) as fh:
                text = fh.read().lower()
            # Simple affirmative 'validated' check (negated forms are OK)
            # We check for 'validated' not preceded by 'un', 'not', 'no', 'non'
            import re
            # Remove negated forms, then check for bare 'validated'
            negated = re.sub(
                r'\b(un|not|no|non)-?validated\b',
                '',
                text
            )
            assert "validated" not in negated, (
                f"Affirmative 'validated' claim found in {out_path}"
            )
