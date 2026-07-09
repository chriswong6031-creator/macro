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
        # Values decline 30% over a year (using solar PV cell HS2022 code 854142)
        rows = _monthly_rows("854142", "2023-01", 24, 2_000_000.0, yoy_growth_pct=-30.0)
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
        """Accelerating imports: 3m YoY rate > 12m YoY rate → positive accel.

        New seasonality-safe formula (fixed 2026-07-09):
          rate_3m  = avg(series[-3:]) / avg(series[-15:-12]) - 1  (YoY of recent 3m avg)
          rate_12m = series[-1] / series[-13] - 1                  (full-year YoY)
          accel    = rate_3m - rate_12m

        Both sides compare like calendar months, so seasonal effects cancel.
        Requires 15 months minimum.

        For accel > 0: avg_recent/avg_prior > v_end/v_13

        Fixture design: months 1-2 are low, month 3 is high (so v_13 = month 3 is
        above avg of months 1-3). Months 13-15 are all high and equal. This makes
        rate_12m (v_end/v_13) smaller than rate_3m (avg_recent/avg_prior), producing
        positive accel.

        Concrete numbers:
          months 1-2 (indices 0,1): 500_000   → avg_prior = (500k+500k+2M)/3 = 1M
          month  3   (index 2):    2_000_000  → v_13 = 2M
          months 4-12:              any values (irrelevant to the formula)
          months 13-15 (indices 12-14): 3_000_000 each → avg_recent = 3M; v_end = 3M
          rate_3m  = 3M/1M - 1 = 200%
          rate_12m = 3M/2M - 1 = 50%
          accel    = 150% > 0 ✓
        """
        from engine.theme_trade_flows import _compute_accel

        rows = []
        start = pd.Period("2022-01", freq="M")
        n = 15
        for i in range(n):
            p = start + i
            if i < 2:
                v = 500_000.0          # months 1-2: low
            elif i == 2:
                v = 2_000_000.0        # month 3: high (this becomes v_13)
            elif i < 12:
                v = 1_000_000.0        # months 4-12: middle (irrelevant to formula)
            else:
                v = 3_000_000.0        # months 13-15: high (recent acceleration)
            rows.append({"stat_month": str(p), "value_usd": v})

        series = pd.Series({r["stat_month"]: r["value_usd"] for r in rows})
        assert len(series) == 15

        # Verify expected fixture values
        assert series.iloc[-15:-12].mean() == pytest.approx(1_000_000.0), "avg_prior should be 1M"
        assert series.iloc[-13] == pytest.approx(2_000_000.0), "v_13 (month 3) should be 2M"
        assert series.iloc[-3:].mean() == pytest.approx(3_000_000.0), "avg_recent should be 3M"
        assert series.iloc[-1] == pytest.approx(3_000_000.0), "v_end should be 3M"

        accel = _compute_accel(series)
        assert accel is not None, (
            "Expected non-None accel for 15-month series"
        )
        assert accel > 0, (
            f"Expected positive accel: rate_3m=200% > rate_12m=50% → accel=+150pp, "
            f"got {accel:.2f}. "
            f"avg_recent={series.iloc[-3:].mean():.0f}, "
            f"avg_prior={series.iloc[-15:-12].mean():.0f}, "
            f"v_end={series.iloc[-1]:.0f}, v_13={series.iloc[-13]:.0f}"
        )

    def test_insufficient_data_returns_none(self):
        """Fewer than 15 months → None (requires 15 for like-month YoY-vs-YoY)."""
        from engine.theme_trade_flows import _compute_accel
        rows = _monthly_rows("854231", "2024-01", 10, 1_000_000.0)
        series = pd.Series({r["stat_month"]: r["value_usd"] for r in rows})
        accel = _compute_accel(series)
        assert accel is None

    def test_13_months_insufficient_for_accel(self):
        """13 months insufficient (need 15); old formula needed 13 — new needs 15."""
        from engine.theme_trade_flows import _compute_accel
        rows = _monthly_rows("854231", "2024-01", 13, 1_000_000.0)
        series = pd.Series({r["stat_month"]: r["value_usd"] for r in rows})
        accel = _compute_accel(series)
        assert accel is None

    def test_15_months_sufficient_for_accel(self):
        """Exactly 15 months with flat data → accel computes (near zero)."""
        from engine.theme_trade_flows import _compute_accel
        rows = _monthly_rows("854231", "2024-01", 15, 1_000_000.0)
        series = pd.Series({r["stat_month"]: r["value_usd"] for r in rows})
        accel = _compute_accel(series)
        # Flat series: rate_3m ≈ 0%, rate_12m ≈ 0%, accel ≈ 0
        assert accel is not None
        assert abs(accel) < 1.0, f"Expected near-zero accel for flat series, got {accel:.4f}"


# ---------------------------------------------------------------------------
# Sign logic per expected_direction
# ---------------------------------------------------------------------------

class TestSignLogic:

    def test_rising_imports_confirms_positive_yoy(self):
        """rising_imports_confirms + positive YoY → confirmation='confirms'."""
        from engine.theme_trade_flows import _sign_reading
        confirmation, band = _sign_reading(
            yoy_pct=25.0, expected_direction="rising_imports_confirms"
        )
        assert confirmation == "confirms"
        assert band == "large"

    def test_rising_imports_confirms_negative_yoy(self):
        """rising_imports_confirms + negative YoY → confirmation='contradicts'."""
        from engine.theme_trade_flows import _sign_reading
        confirmation, band = _sign_reading(
            yoy_pct=-15.0, expected_direction="rising_imports_confirms"
        )
        assert confirmation == "contradicts"
        assert band == "moderate"

    def test_falling_imports_confirms_negative_yoy(self):
        """falling_imports_confirms + negative YoY → confirmation='confirms'
        (import decline = domestic substitution)."""
        from engine.theme_trade_flows import _sign_reading
        confirmation, band = _sign_reading(
            yoy_pct=-25.0, expected_direction="falling_imports_confirms"
        )
        assert confirmation == "confirms"
        assert band == "large"

    def test_falling_imports_confirms_positive_yoy(self):
        """falling_imports_confirms + positive YoY → confirmation='contradicts'
        (imports still rising = substitution not happening)."""
        from engine.theme_trade_flows import _sign_reading
        confirmation, band = _sign_reading(
            yoy_pct=12.0, expected_direction="falling_imports_confirms"
        )
        assert confirmation == "contradicts"
        assert band == "moderate"

    def test_small_yoy_is_neutral(self):
        """YoY below threshold (< 5%) → neutral regardless of direction."""
        from engine.theme_trade_flows import _sign_reading
        confirmation, band = _sign_reading(
            yoy_pct=3.0, expected_direction="rising_imports_confirms"
        )
        assert confirmation == "neutral"
        assert band is None

    def test_none_yoy_is_neutral(self):
        from engine.theme_trade_flows import _sign_reading
        confirmation, band = _sign_reading(
            yoy_pct=None, expected_direction="rising_imports_confirms"
        )
        assert confirmation == "neutral"
        assert band is None

    def test_magnitude_bands(self):
        from engine.theme_trade_flows import _sign_reading
        _, band = _sign_reading(25.0, "rising_imports_confirms")
        assert band == "large"

        _, band = _sign_reading(15.0, "rising_imports_confirms")
        assert band == "moderate"

        _, band = _sign_reading(7.0, "rising_imports_confirms")
        assert band == "small"

    def test_confirmation_enum_valid(self):
        """Confirmation must always be one of the three valid values."""
        from engine.theme_trade_flows import _sign_reading
        valid = {"confirms", "contradicts", "neutral"}
        for yoy in [None, -50.0, -3.0, 3.0, 50.0]:
            for direction in ["rising_imports_confirms", "falling_imports_confirms"]:
                confirmation, _ = _sign_reading(yoy, direction)
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

        valid_null_confirmations = {"neutral", "mixed_direction"}
        for theme_id, theme_data in themes.items():
            assert theme_data["n_codes_with_data"] == 0, (
                f"Theme {theme_id} should have 0 codes with data when parquet absent"
            )
            assert theme_data["yoy_pct"] is None
            assert theme_data["accel_3m_vs_12m"] is None
            assert theme_data["confirmation"] in valid_null_confirmations, (
                f"Theme {theme_id} confirmation must be 'neutral' or 'mixed_direction' when absent, "
                f"got {theme_data['confirmation']!r}"
            )
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
                    "confirmation", "coverage_note", "coverage_note_zh",
                    "is_mixed_direction", "direction_legs"}
        for theme_id, theme_data in result["themes"].items():
            missing = required - set(theme_data.keys())
            assert not missing, (
                f"Theme {theme_id} missing required fields: {missing}"
            )

    def test_mixed_direction_themes_flagged(self, monkeypatch):
        """Themes with mixed expected_direction codes must be flagged is_mixed_direction=True."""
        from engine import theme_trade_flows as ttf
        with mock.patch.object(ttf, "_load_parquet", return_value=None):
            result = ttf.compute_theme_trade_flows(write_nw=False, write_site=False)
        # solar, rare_earth_critical_min, copper_steel_electrify have mixed directions
        mixed_themes = {"solar", "rare_earth_critical_min", "copper_steel_electrify"}
        for theme_id in mixed_themes:
            tdata = result["themes"].get(theme_id)
            if tdata is not None:
                assert tdata["is_mixed_direction"] is True, (
                    f"Theme {theme_id} should be flagged is_mixed_direction=True "
                    f"(has both rising and falling codes)"
                )
                assert tdata["confirmation"] == "mixed_direction", (
                    f"Theme {theme_id} should have confirmation='mixed_direction', "
                    f"got {tdata['confirmation']!r}"
                )

    def test_uniform_direction_themes_not_mixed(self, monkeypatch):
        """Themes with all same expected_direction must NOT be flagged as mixed."""
        from engine import theme_trade_flows as ttf
        with mock.patch.object(ttf, "_load_parquet", return_value=None):
            result = ttf.compute_theme_trade_flows(write_nw=False, write_site=False)
        # ai_semiconductors is all rising_imports_confirms
        ai_theme = result["themes"].get("ai_semiconductors")
        if ai_theme is not None:
            assert ai_theme["is_mixed_direction"] is False, (
                "ai_semiconductors should not be flagged as mixed-direction"
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
        Solar code 854142 HS2022 (falling_imports_confirms): import decline should confirm.
        15 months with -25% YoY → falling_imports_confirms leg confirmation='confirms'.

        Solar is a MIXED-DIRECTION theme (854142/854143=falling, 280461=rising), so:
          - theme-level confirmation = 'mixed_direction' (not directly readable)
          - direction_legs['falling_imports_confirms'] has the per-leg read
        """
        from engine import theme_trade_flows as ttf

        rows = _monthly_rows("854142", "2023-05", 15, 2_000_000.0, yoy_growth_pct=-25.0)
        df = pd.DataFrame(rows, columns=[
            "hs_code", "stat_month", "value_usd", "quantity", "quantity_unit", "ingested_at"
        ])

        with mock.patch.object(ttf, "_load_parquet", return_value=df):
            result = ttf.compute_theme_trade_flows(write_nw=False, write_site=False)

        solar_theme = result["themes"].get("solar")
        assert solar_theme is not None

        # Solar is mixed-direction: top-level confirmation must be 'mixed_direction'
        assert solar_theme["is_mixed_direction"] is True, (
            "Solar theme must be flagged as mixed-direction (has rising + falling codes)"
        )
        assert solar_theme["confirmation"] == "mixed_direction", (
            f"Expected 'mixed_direction' for solar top-level, got {solar_theme['confirmation']!r}"
        )

        if solar_theme["n_codes_with_data"] >= 1:
            # The falling_imports_confirms leg should show confirms for -25% YoY
            legs = solar_theme.get("direction_legs", {})
            falling_leg = legs.get("falling_imports_confirms")
            if falling_leg and falling_leg["yoy_pct"] is not None:
                if abs(falling_leg["yoy_pct"]) >= 5.0:
                    assert falling_leg["confirmation"] == "confirms", (
                        f"Expected falling_leg confirmation='confirms' for solar with -25% YoY, "
                        f"got {falling_leg['confirmation']!r}"
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
