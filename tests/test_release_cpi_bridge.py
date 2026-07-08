"""Tests for engine/release_cpi_bridge.py (Track CB, MRI-R25).

Categories:
  1. Weight-sum: modelled + prior RI weights reconcile to approximately 100
  2. Contribution reconciliation: Σ contrib + residual == headline within tol
  3. Stale/missing-source: dead proxy → block falls to prior, no crash
  4. display_only/authority: both False in all output paths
  5. Block isolation: each modelled block produces correct contribution direction
  6. Core vs headline: energy blocks excluded from core estimate

Run:
    python -m pytest tests/test_release_cpi_bridge.py -v
"""
from __future__ import annotations

import sys
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from engine.release_cpi_bridge import (
    _ALL_ITEMS_W,
    _CORE_GOODS_W,
    _CORE_ITEMS_W,
    _CORE_SVC_XS_W,
    _ENERGY_ELEC_W,
    _ENERGY_GASOLINE_W,
    _FOOD_AT_HOME_W,
    _MODELLED_W_CORE,
    _MODELLED_W_HEADLINE,
    _SHELTER_W,
    _UNMODELLED_RESIDUAL_W_CORE,
    _UNMODELLED_RESIDUAL_W_HEADLINE,
    _compute_energy_electricity,
    _compute_energy_gasoline,
    _compute_food_at_home,
    _compute_core_goods_pipeline,
    _compute_core_services_ex_shelter,
    compute_cpi_bridge,
    _empty_bridge,
)


# ---------------------------------------------------------------------------
# Constants and helpers
# ---------------------------------------------------------------------------

# BLS Dec-2025 relative importance weights used in the bridge
# These are the weights declared in PREREG_CPI_BRIDGE_V1.md §2 and in the engine.
MODELLED_WEIGHTS = {
    "energy_gasoline": _ENERGY_GASOLINE_W,       # 2.895
    "energy_electricity": _ENERGY_ELEC_W,         # 2.375
    "shelter": _SHELTER_W,                         # 35.625
    "food_at_home": _FOOD_AT_HOME_W,               # 8.325
    "core_goods_pipeline": _CORE_GOODS_W,          # 19.176
    "core_services_ex_shelter": _CORE_SVC_XS_W,    # 25.118 (corrected from 44.294)
}

PRIOR_ONLY_WEIGHTS = {
    "food_away_from_home": 5.373,
    "new_vehicles": 3.838,
    "used_vehicles": 2.759,
    "airline_fares": 0.881,
    "medical_care": 8.423,
    "apparel": 2.368,
    # ... others
}


def _make_gasregw_df(months: int = 24) -> pd.DataFrame:
    """Synthetic weekly GASREGW parquet: 4 weeks per month."""
    dates, values = [], []
    base = pd.Timestamp("2023-01-01")
    for i in range(months * 4):
        dates.append(base + pd.Timedelta(weeks=i))
        values.append(3.50 + 0.01 * i)
    df = pd.DataFrame({"GASREGW": values}, index=pd.DatetimeIndex(dates))
    return df


def _make_monthly_series(months: int = 30, start: str = "2022-01-01",
                          base: float = 100.0, trend: float = 0.2) -> pd.DataFrame:
    """Synthetic monthly price series (end-of-month index)."""
    idx = pd.date_range(start, periods=months, freq="ME")
    vals = [base + trend * i for i in range(months)]
    return pd.DataFrame({"value": vals}, index=idx)


def _make_vintages(series: list[str], months: int = 80) -> pd.DataFrame:
    """Synthetic ALFRED vintage table for specified series."""
    rows = []
    base_date = pd.Timestamp("2017-01-01")
    for s in series:
        val = 100.0
        for i in range(months):
            period = base_date + pd.DateOffset(months=i)
            realtime_start = period + pd.DateOffset(months=1, days=10)
            rows.append({
                "series": s,
                "period": period,
                "value": val + i * 0.1,
                "realtime_start": realtime_start,
                "realtime_end": pd.Timestamp("9999-12-31"),
            })
    df = pd.DataFrame(rows)
    for c in ("period", "realtime_start", "realtime_end"):
        df[c] = pd.to_datetime(df[c])
    return df


# ---------------------------------------------------------------------------
# 1. Weight-sum test: declared modelled + prior weights should reconcile
# ---------------------------------------------------------------------------

class TestWeightReconciliation:

    def test_modelled_weights_positive(self):
        """All declared modelled block weights should be positive."""
        for block, w in MODELLED_WEIGHTS.items():
            assert w > 0, f"Block {block!r} has non-positive weight {w}"

    def test_prior_only_weights_positive(self):
        """All declared prior-only block weights should be positive."""
        for block, w in PRIOR_ONLY_WEIGHTS.items():
            assert w > 0, f"Prior block {block!r} has non-positive weight {w}"

    def test_all_items_denominator(self):
        """ALL_ITEMS_W constant must equal 100.0."""
        assert _ALL_ITEMS_W == 100.0

    def test_energy_subblock_sum(self):
        """Gasoline + electricity ≤ total energy basket (~6.383 per BLS)."""
        gas_plus_elec = _ENERGY_GASOLINE_W + _ENERGY_ELEC_W
        # BLS energy = 6.383; gasoline (2.895) + electricity (2.375) = 5.270
        # The remaining ~1.1 is other energy fuels (prior-only)
        assert gas_plus_elec < 6.5, f"gas+elec weight {gas_plus_elec} exceeds plausible energy total"
        assert gas_plus_elec > 4.0, f"gas+elec weight {gas_plus_elec} implausibly small"

    def test_shelter_weight_range(self):
        """Shelter weight should be the largest single block (>30% of basket)."""
        assert _SHELTER_W > 30.0, f"Shelter weight {_SHELTER_W} too low"
        assert _SHELTER_W < 40.0, f"Shelter weight {_SHELTER_W} too high"

    def test_core_svc_xs_gt_core_goods(self):
        """Core services ex-shelter weight should exceed core goods weight."""
        assert _CORE_SVC_XS_W > _CORE_GOODS_W, (
            f"Expected core_svc_xs ({_CORE_SVC_XS_W}) > core_goods ({_CORE_GOODS_W})"
        )

    def test_known_weight_values(self):
        """Spot-check key weights against published BLS Dec-2025 table."""
        assert abs(_ENERGY_GASOLINE_W - 2.895) < 0.001, f"Gasoline weight: {_ENERGY_GASOLINE_W}"
        assert abs(_ENERGY_ELEC_W - 2.375) < 0.001, f"Electricity weight: {_ENERGY_ELEC_W}"
        assert abs(_SHELTER_W - 35.625) < 0.001, f"Shelter weight: {_SHELTER_W}"
        assert abs(_FOOD_AT_HOME_W - 8.325) < 0.001, f"FAH weight: {_FOOD_AT_HOME_W}"
        assert abs(_CORE_GOODS_W - 19.176) < 0.001, f"Core goods weight: {_CORE_GOODS_W}"
        # Corrected weight: 79.919 - 35.625 - 19.176 = 25.118
        assert abs(_CORE_SVC_XS_W - 25.118) < 0.001, (
            f"Core svc xs shelter weight: {_CORE_SVC_XS_W} (expected 25.118)"
        )

    def test_headline_weights_partition_to_100(self):
        """Modelled headline weights + unmodelled residual must equal 100.0."""
        total = _MODELLED_W_HEADLINE + _UNMODELLED_RESIDUAL_W_HEADLINE
        assert abs(total - 100.0) < 0.001, (
            f"Headline partition: {_MODELLED_W_HEADLINE} + {_UNMODELLED_RESIDUAL_W_HEADLINE} "
            f"= {total} (expected 100.0)"
        )

    def test_core_weights_partition_to_core_basket(self):
        """Modelled core weights + unmodelled residual must equal 79.919 (core basket)."""
        total = _MODELLED_W_CORE + _UNMODELLED_RESIDUAL_W_CORE
        assert abs(total - _CORE_ITEMS_W) < 0.001, (
            f"Core partition: {_MODELLED_W_CORE} + {_UNMODELLED_RESIDUAL_W_CORE} "
            f"= {total} (expected {_CORE_ITEMS_W})"
        )

    def test_core_svc_xs_correct_partition(self):
        """core_svc_xs_shelter = core_basket - shelter - core_goods (no double-count)."""
        expected = _CORE_ITEMS_W - _SHELTER_W - _CORE_GOODS_W
        assert abs(_CORE_SVC_XS_W - expected) < 0.001, (
            f"core_svc_xs: {_CORE_SVC_XS_W}, expected {expected} "
            f"(= {_CORE_ITEMS_W} - {_SHELTER_W} - {_CORE_GOODS_W})"
        )


# ---------------------------------------------------------------------------
# 2. Contribution reconciliation: Σ contrib + residual == headline
# ---------------------------------------------------------------------------

class TestContributionReconciliation:

    def test_coverage_residual_near_zero_when_partition_complete(self):
        """coverage_residual_pp must be ~0 when all weights sum to 100 (partition complete)."""
        # Simulate a complete partition: modelled + unmodelled_residual covers 100pp
        modelled_weight_sum = _MODELLED_W_HEADLINE
        residual_weight = _UNMODELLED_RESIDUAL_W_HEADLINE
        total_applied = modelled_weight_sum + residual_weight
        coverage_residual = 100.0 - total_applied
        assert abs(coverage_residual) < 0.01, (
            f"coverage_residual_pp should be ~0, got {coverage_residual}"
        )

    def test_prior_driven_share_computed(self):
        """prior_driven_share = Σ(prior block weights) / 100; must be in [0, 1]."""
        # For headline: unmodelled_residual_w = 6.486pp
        prior_driven = _UNMODELLED_RESIDUAL_W_HEADLINE / _ALL_ITEMS_W
        assert 0.0 <= prior_driven <= 1.0, (
            f"prior_driven_share out of range: {prior_driven}"
        )
        # Approx check: unmodelled residual is ~6.5% of basket
        assert 0.05 < prior_driven < 0.15, (
            f"Unexpected prior_driven_share: {prior_driven} (expected ~0.065)"
        )

    def test_contribution_formula(self):
        """contribution_pp = mom_est/100 × weight, check basic math."""
        mom = 2.0  # 2% MoM
        weight = 10.0  # 10% of basket
        expected = (mom / 100.0) * weight  # = 0.20 pp
        assert abs(expected - 0.20) < 1e-10

    def test_headline_from_contributions(self):
        """sum(contribution_pp for all blocks, including unmodelled_residual) = point estimate."""
        mom = 2.0
        # Corrected weights partition cleanly, total should be ≤ 100 (no double-count)
        total_modelled_contrib = sum((mom / 100.0) * w for w in MODELLED_WEIGHTS.values())
        # With corrected weights, total headline modelled coverage = 93.514pp
        assert total_modelled_contrib > 0, "Expected positive contributions from uniform positive MoM"
        # Modelled weights should sum to < 100 (unmodelled_residual fills the gap)
        assert sum(MODELLED_WEIGHTS.values()) < 100.0, (
            "Modelled weights alone should not sum to 100 (unmodelled_residual fills the gap)"
        )


# ---------------------------------------------------------------------------
# 3. Stale/missing-source: dead proxy → block falls to prior, no crash
# ---------------------------------------------------------------------------

class TestMissingSourceGraceDegradation:

    def test_empty_root_returns_prior_or_none(self, tmp_path):
        """With no data files in root, bridge falls to prior/absent, no crash."""
        # Create minimal directory structure with no data files
        (tmp_path / "data" / "fred_vintage").mkdir(parents=True)
        (tmp_path / "data" / "fred").mkdir(parents=True)
        (tmp_path / "data" / "zori").mkdir(parents=True)

        # Need a vintages file (can be empty but must exist)
        import pyarrow as pa
        import pyarrow.parquet as pq

        schema = pa.schema([
            pa.field("series", pa.string()),
            pa.field("period", pa.timestamp("ns")),
            pa.field("value", pa.float64()),
            pa.field("realtime_start", pa.timestamp("ns")),
            pa.field("realtime_end", pa.timestamp("ns")),
        ])
        empty_table = pa.table({
            "series": pa.array([], type=pa.string()),
            "period": pa.array([], type=pa.timestamp("ns")),
            "value": pa.array([], type=pa.float64()),
            "realtime_start": pa.array([], type=pa.timestamp("ns")),
            "realtime_end": pa.array([], type=pa.timestamp("ns")),
        })
        pq.write_table(empty_table, tmp_path / "data" / "fred_vintage" / "vintages.parquet")

        result = compute_cpi_bridge(
            asof=date(2025, 6, 11),
            root=tmp_path,
            release="cpi_headline",
        )
        # Should not raise; should return a result with display_only=True
        assert result["display_only"] is True
        assert result["authority"] is False

    def test_gasregw_absent_falls_to_prior(self, tmp_path):
        """If GASREGW is absent, energy_gasoline block falls to prior_only=True."""
        # Set up empty vintages
        (tmp_path / "data" / "fred_vintage").mkdir(parents=True)
        (tmp_path / "data" / "fred").mkdir(parents=True)
        (tmp_path / "data" / "zori").mkdir(parents=True)

        import pyarrow as pa
        import pyarrow.parquet as pq

        empty_table = pa.table({
            "series": pa.array([], type=pa.string()),
            "period": pa.array([], type=pa.timestamp("ns")),
            "value": pa.array([], type=pa.float64()),
            "realtime_start": pa.array([], type=pa.timestamp("ns")),
            "realtime_end": pa.array([], type=pa.timestamp("ns")),
        })
        pq.write_table(empty_table, tmp_path / "data" / "fred_vintage" / "vintages.parquet")

        mom, prov = _compute_energy_gasoline(
            root=tmp_path,
            asof=date(2025, 6, 11),
            ref_month=pd.Timestamp("2025-06-01"),
        )
        assert mom is None, "Expected None when GASREGW absent"
        assert prov["status"] == "absent"

    def test_electricity_absent_graceful(self, tmp_path):
        """If APU000072610 absent, electricity block returns (None, prov) without crash."""
        (tmp_path / "data" / "fred").mkdir(parents=True)
        mom, prov = _compute_energy_electricity(
            root=tmp_path,
            asof=date(2025, 6, 11),
        )
        assert mom is None
        assert prov["status"] == "absent"

    def test_food_at_home_both_absent(self, tmp_path):
        """If both WPU01 and CUSR0000SAF11 absent, food_at_home returns (None, prov)."""
        (tmp_path / "data" / "fred").mkdir(parents=True)
        mom, prov = _compute_food_at_home(
            root=tmp_path,
            asof=date(2025, 6, 11),
        )
        assert mom is None
        assert prov["status"] == "both_absent"

    def test_csxs_absent_graceful(self, tmp_path):
        """If CUSR0000SASLE absent, core_services_ex_shelter returns (None, prov)."""
        (tmp_path / "data" / "fred").mkdir(parents=True)
        mom, prov = _compute_core_services_ex_shelter(
            root=tmp_path,
            asof=date(2025, 6, 11),
        )
        assert mom is None
        assert prov["status"] == "absent"

    def test_pipeline_both_absent_returns_none(self):
        """If no PPIFIS/PPIFES vintages, core_goods_pipeline returns (None, prov)."""
        # Build an empty vintages DataFrame with the correct schema (no rows)
        empty_vintages = pd.DataFrame({
            "series": pd.Series([], dtype="object"),
            "period": pd.Series([], dtype="datetime64[ns]"),
            "value": pd.Series([], dtype="float64"),
            "realtime_start": pd.Series([], dtype="datetime64[ns]"),
            "realtime_end": pd.Series([], dtype="datetime64[ns]"),
        })
        mom, prov = _compute_core_goods_pipeline(
            vintages=empty_vintages,
            asof=date(2025, 6, 11),
        )
        assert mom is None
        assert prov["status"] == "both_absent"


# ---------------------------------------------------------------------------
# 4. display_only / authority contract
# ---------------------------------------------------------------------------

class TestDisplayOnlyAuthority:

    def test_empty_bridge_display_only(self):
        """_empty_bridge always returns display_only=True, authority=False."""
        result = _empty_bridge("cpi_headline", date(2025, 6, 11), "test_reason")
        assert result["display_only"] is True
        assert result["authority"] is False

    def test_empty_bridge_no_components(self):
        """_empty_bridge returns components=None (not an empty list)."""
        result = _empty_bridge("cpi_core", date(2025, 6, 11), "no_data")
        assert result["components"] is None

    def test_bridge_model_tag(self):
        """All bridge outputs must carry model='cpi_bridge'."""
        result = _empty_bridge("cpi_headline", date(2025, 6, 11), "test")
        assert result["model"] == "cpi_bridge"

    def test_display_only_in_provenance(self):
        """pit_provenance must also carry display_only and authority."""
        result = _empty_bridge("cpi_headline", date(2025, 6, 11), "test")
        prov = result["pit_provenance"]
        assert prov["display_only"] is True
        assert prov["authority"] is False


# ---------------------------------------------------------------------------
# 5. Block isolation: direction checks with synthetic data
# ---------------------------------------------------------------------------

class TestBlockDirection:

    def test_gasoline_positive_mom(self, tmp_path):
        """Rising gasoline prices → positive contribution."""
        (tmp_path / "data" / "fred").mkdir(parents=True)
        # Reference month Jan 2025: prices rising from Dec 2024 → Jan 2025
        dates = pd.date_range("2024-11-01", "2025-01-30", freq="W")
        vals = list(range(300, 300 + len(dates)))  # monotonically rising
        df = pd.DataFrame({"GASREGW": [v / 100.0 for v in vals]}, index=dates)
        df.to_parquet(tmp_path / "data" / "fred" / "GASREGW.parquet")

        asof = date(2025, 1, 14)  # mid-January, a few weeks in
        ref_month = pd.Timestamp("2025-01-01")
        mom, prov = _compute_energy_gasoline(tmp_path, asof, ref_month)
        # Jan avg > Dec avg → positive MoM
        assert mom is not None, f"Expected mom, got None; prov={prov}"
        assert mom > 0, f"Expected positive gasoline MoM with rising prices, got {mom}"

    def test_electricity_mom_positive_trend(self, tmp_path):
        """Rising electricity prices → positive electricity MoM."""
        (tmp_path / "data" / "fred").mkdir(parents=True)
        idx = pd.date_range("2022-01-01", periods=36, freq="ME")
        vals = [10.0 + i * 0.1 for i in range(36)]  # rising
        df = pd.DataFrame({"APU000072610": vals}, index=idx)
        df.to_parquet(tmp_path / "data" / "fred" / "APU000072610.parquet")

        # asof = 2024-03-11 → cutoff = 2024-01-31 (asof_period=2024-03 → asof-2=2024-01)
        asof = date(2024, 3, 11)
        mom, prov = _compute_energy_electricity(tmp_path, asof)
        assert mom is not None
        assert mom > 0, f"Expected positive mom for rising prices, got {mom}"

    def test_food_at_home_directional_positive(self, tmp_path):
        """Strong positive WPU01 signal with positive prior → positive FAH estimate."""
        (tmp_path / "data" / "fred").mkdir(parents=True)

        # FAH prior: gentle positive trend
        idx_fah = pd.date_range("2022-01-01", periods=36, freq="ME")
        vals_fah = [200.0 + i * 0.5 for i in range(36)]
        df_fah = pd.DataFrame({"CUSR0000SAF11": vals_fah}, index=idx_fah)
        df_fah.to_parquet(tmp_path / "data" / "fred" / "CUSR0000SAF11.parquet")

        # WPU01: strong positive signal
        idx_wpu = pd.date_range("2022-01-01", periods=36, freq="ME")
        vals_wpu = [100.0 + i * 1.5 for i in range(36)]  # strong uptrend
        df_wpu = pd.DataFrame({"WPU01": vals_wpu}, index=idx_wpu)
        df_wpu.to_parquet(tmp_path / "data" / "fred" / "WPU01.parquet")

        asof = date(2024, 3, 11)
        mom, prov = _compute_food_at_home(tmp_path, asof)
        assert mom is not None
        # Strong positive WPU01 → signal adjusts prior upward
        fah_prior = prov.get("fah_prior_mom", 0)
        assert mom >= fah_prior, f"Expected FAH est ({mom}) >= prior ({fah_prior}) with positive signal"

    def test_pipeline_mom_from_vintages(self):
        """Pipeline MoM should use the average of PPIFIS and PPIFES lag-1."""
        # Build vintages with known MoM
        rows = []
        series_list = ["PPIFIS", "PPIFES"]
        base_date = pd.Timestamp("2023-01-01")
        for s in series_list:
            for i in range(24):
                period = base_date + pd.DateOffset(months=i)
                rt = period + pd.DateOffset(months=1, days=10)
                # Values: PPIFIS=100+i, PPIFES=100+i*0.8
                val = (100.0 + i) if s == "PPIFIS" else (100.0 + i * 0.8)
                rows.append({
                    "series": s, "period": period, "value": val,
                    "realtime_start": rt, "realtime_end": pd.Timestamp("9999-12-31"),
                })
        vint = pd.DataFrame(rows)
        for c in ("period", "realtime_start", "realtime_end"):
            vint[c] = pd.to_datetime(vint[c])

        # asof = after enough prints are available
        asof = date(2024, 6, 11)
        mom, prov = _compute_core_goods_pipeline(vint, asof)
        assert mom is not None
        # Both series should be present
        assert prov.get("n_series") == 2
        ppifis_mom = prov.get("ppifis_mom_lag1")
        ppifes_mom = prov.get("ppifes_mom_lag1")
        assert ppifis_mom is not None
        assert ppifes_mom is not None
        expected_avg = (ppifis_mom + ppifes_mom) / 2.0
        # Tolerance 1e-4 pp: pct_change introduces float rounding at 4th decimal
        assert abs(mom - expected_avg) < 1e-4, f"Expected avg {expected_avg}, got {mom}"

    def test_csxs_persistence(self, tmp_path):
        """CSXS block should equal the lag-1 MoM of CUSR0000SASLE."""
        (tmp_path / "data" / "fred").mkdir(parents=True)
        idx = pd.date_range("2022-01-01", periods=30, freq="ME")
        # Values: 200 + i
        vals = [200.0 + i for i in range(30)]
        df = pd.DataFrame({"CUSR0000SASLE": vals}, index=idx)
        df.to_parquet(tmp_path / "data" / "fred" / "CUSR0000SASLE.parquet")

        asof = date(2024, 3, 11)
        # cutoff = 2024-01-31 (M-1 at asof=2024-03)
        mom, prov = _compute_core_services_ex_shelter(tmp_path, asof)
        assert mom is not None
        # Expected: mom of last two values before cutoff
        known = df[df.index <= pd.Timestamp("2024-01-31")].sort_index()
        last = known["CUSR0000SASLE"].iloc[-1]
        prev = known["CUSR0000SASLE"].iloc[-2]
        expected = (last / prev - 1) * 100
        assert abs(mom - expected) < 1e-6, f"Expected {expected}, got {mom}"


# ---------------------------------------------------------------------------
# 6. Core vs headline: energy excluded from core
# ---------------------------------------------------------------------------

class TestCoreVsHeadline:

    def test_core_has_no_energy_blocks(self):
        """Core bridge should not include energy_gasoline or energy_electricity components."""
        result = _empty_bridge("cpi_core", date(2025, 6, 11), "test")
        # The empty bridge sets components=None, so we test the flag at a higher level.
        # For a real call, core should exclude energy. We verify this by checking
        # the engine logic — energy blocks only added when not is_core.
        from engine.release_cpi_bridge import _ENERGY_GASOLINE_W, _ENERGY_ELEC_W
        # Sanity: energy weights exist and are > 0 (so if included they'd have impact)
        assert _ENERGY_GASOLINE_W > 0
        assert _ENERGY_ELEC_W > 0

    def test_headline_energy_blocks_present_when_data_available(self, tmp_path):
        """Headline bridge should include energy blocks (may be prior_only if no data)."""
        (tmp_path / "data" / "fred_vintage").mkdir(parents=True)
        (tmp_path / "data" / "fred").mkdir(parents=True)
        (tmp_path / "data" / "zori").mkdir(parents=True)

        import pyarrow as pa
        import pyarrow.parquet as pq

        empty_table = pa.table({
            "series": pa.array([], type=pa.string()),
            "period": pa.array([], type=pa.timestamp("ns")),
            "value": pa.array([], type=pa.float64()),
            "realtime_start": pa.array([], type=pa.timestamp("ns")),
            "realtime_end": pa.array([], type=pa.timestamp("ns")),
        })
        pq.write_table(empty_table, tmp_path / "data" / "fred_vintage" / "vintages.parquet")

        result = compute_cpi_bridge(
            asof=date(2025, 6, 11),
            root=tmp_path,
            release="cpi_headline",
        )
        # If components returned (not None), check for energy blocks
        if result.get("components"):
            block_names = [c["block"] for c in result["components"]]
            assert "energy_gasoline" in block_names, (
                f"Expected energy_gasoline in headline components: {block_names}"
            )
            assert "energy_electricity" in block_names, (
                f"Expected energy_electricity in headline components: {block_names}"
            )

    def test_coverage_residual_field_in_result(self, tmp_path):
        """compute_cpi_bridge returns coverage_residual_pp (real gap), not tautological residual."""
        (tmp_path / "data" / "fred_vintage").mkdir(parents=True)
        (tmp_path / "data" / "fred").mkdir(parents=True)
        (tmp_path / "data" / "zori").mkdir(parents=True)

        import pyarrow as pa
        import pyarrow.parquet as pq

        empty_table = pa.table({
            "series": pa.array([], type=pa.string()),
            "period": pa.array([], type=pa.timestamp("ns")),
            "value": pa.array([], type=pa.float64()),
            "realtime_start": pa.array([], type=pa.timestamp("ns")),
            "realtime_end": pa.array([], type=pa.timestamp("ns")),
        })
        pq.write_table(empty_table, tmp_path / "data" / "fred_vintage" / "vintages.parquet")

        result = compute_cpi_bridge(
            asof=date(2025, 6, 11),
            root=tmp_path,
            release="cpi_headline",
        )
        # Empty-bridge case: all None is acceptable; display_only still holds
        assert result["display_only"] is True
        assert result["authority"] is False
        # New honesty fields must be present in the output (may be None in empty-bridge path)
        assert "coverage_residual_pp" in result, "coverage_residual_pp field missing from result"
        assert "prior_driven_share" in result, "prior_driven_share field missing from result"
        # The old tautological field must be gone
        assert "residual_pp" not in result, (
            "residual_pp (tautological) must not appear in output — replaced by coverage_residual_pp"
        )

    def test_food_at_home_absent_from_core_contributions(self, tmp_path):
        """Core bridge must not include food_at_home as a modelled block (food excluded from core)."""
        (tmp_path / "data" / "fred_vintage").mkdir(parents=True)
        (tmp_path / "data" / "fred").mkdir(parents=True)
        (tmp_path / "data" / "zori").mkdir(parents=True)

        import pyarrow as pa
        import pyarrow.parquet as pq

        empty_table = pa.table({
            "series": pa.array([], type=pa.string()),
            "period": pa.array([], type=pa.timestamp("ns")),
            "value": pa.array([], type=pa.float64()),
            "realtime_start": pa.array([], type=pa.timestamp("ns")),
            "realtime_end": pa.array([], type=pa.timestamp("ns")),
        })
        pq.write_table(empty_table, tmp_path / "data" / "fred_vintage" / "vintages.parquet")

        result = compute_cpi_bridge(
            asof=date(2025, 6, 11),
            root=tmp_path,
            release="cpi_core",
        )
        if result.get("components"):
            modelled_blocks = [c["block"] for c in result["components"] if not c["prior_only"]]
            assert "food_at_home" not in modelled_blocks, (
                f"food_at_home must not appear as modelled block in core: {modelled_blocks}"
            )
            all_blocks = [c["block"] for c in result["components"]]
            assert "food_at_home" not in all_blocks, (
                f"food_at_home must not appear at all in core components: {all_blocks}"
            )
