"""tests/test_moat_falsifiers.py — Long-Hold W2 PR-K: Moat Falsifier Sensors.

Five test groups:

  A. Sensor logic (pure): each of the 4 sensors fires / does not fire on
     synthetic row-pairs, including edge cases.

  B. Coverage stamps: every result dict carries _horizon_role="hold_thesis",
     _display_only=True, _version="v1", sensor_coverage, coverage_n_years.

  C. Base-rate computation: correct across a synthetic universe; median/fy
     correctly derived; missing-data entries excluded.

  D. Great-company-trap overlay: each leg independently; combined; de-escalation
     only (never escalates); prints all inputs.

  E. Firewall: moat falsifier artifacts are hold_thesis with no
     scored_path_surfaces; the real registry allowlist test passes.

All tests are deterministic.  Groups A–D use purely in-memory data.
Group E does a read-only assertion against config/synapse.yml.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engine.moat_falsifiers import (  # noqa: E402
    _sensor_margin_compression,
    _sensor_receivables_stretch,
    _sensor_inventory_build,
    _sensor_capex_intensity,
    compute_moat_falsifiers,
    compute_base_rates,
    great_company_trap,
    _SENSOR_FNS,
    _HORIZON_ROLE,
    _sensor_cols,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _row(**kwargs) -> pd.Series:
    """Build a minimal row Series for a sensor test."""
    defaults = {
        "fy": 2024,
        "revenue": 100.0,
        "gross_profit": 50.0,
        "op_income": 20.0,
        "receivables": 10.0,
        "inventory": 5.0,
        "capex": 8.0,
        "cfo": 15.0,
    }
    defaults.update(kwargs)
    return pd.Series(defaults)


def _make_statements(rows: list[dict]) -> pd.DataFrame:
    """Build a synthetic statements DataFrame from a list of row dicts."""
    defaults = {
        "fy": 2020, "ticker": "TEST",
        "revenue": 100.0, "gross_profit": 50.0, "op_income": 20.0,
        "receivables": 10.0, "inventory": 5.0, "capex": 8.0, "cfo": 15.0,
        "assets": 200.0, "cur_assets": 80.0, "cur_liab": 40.0,
        "ni": 12.0, "cash": 20.0, "equity": 80.0, "liabilities": 120.0,
    }
    full_rows = []
    for r in rows:
        row = dict(defaults)
        row.update(r)
        full_rows.append(row)
    return pd.DataFrame(full_rows)


# ===========================================================================
# Group A — Sensor logic (pure; synthetic row-pairs)
# ===========================================================================


class TestMarginCompression:
    """margin_compression_despite_revenue_growth fires when revenue grows >= 3%
    AND gross margin declines."""

    def test_fires_when_revenue_grows_and_margin_drops(self) -> None:
        cur = _row(revenue=110.0, gross_profit=50.0)   # margin 45.5%
        pri = _row(revenue=100.0, gross_profit=50.0)   # margin 50.0%
        assert _sensor_margin_compression(cur, pri) is True

    def test_does_not_fire_when_margin_stable(self) -> None:
        cur = _row(revenue=110.0, gross_profit=55.0)   # margin 50% (unchanged)
        pri = _row(revenue=100.0, gross_profit=50.0)   # margin 50%
        assert _sensor_margin_compression(cur, pri) is False

    def test_does_not_fire_below_revenue_threshold(self) -> None:
        # Revenue grew only 1% (below 3% threshold)
        cur = _row(revenue=101.0, gross_profit=45.0)   # margin drops
        pri = _row(revenue=100.0, gross_profit=50.0)
        assert _sensor_margin_compression(cur, pri) is False

    def test_returns_none_on_missing_gross_profit(self) -> None:
        cur = _row(revenue=110.0, gross_profit=float("nan"))
        pri = _row(revenue=100.0, gross_profit=50.0)
        assert _sensor_margin_compression(cur, pri) is None

    def test_returns_none_when_revenue_zero(self) -> None:
        cur = _row(revenue=0.0, gross_profit=50.0)
        pri = _row(revenue=100.0, gross_profit=50.0)
        assert _sensor_margin_compression(cur, pri) is None

    def test_does_not_fire_when_margin_improves(self) -> None:
        cur = _row(revenue=110.0, gross_profit=60.0)   # margin 54.5% — better
        pri = _row(revenue=100.0, gross_profit=50.0)   # margin 50%
        assert _sensor_margin_compression(cur, pri) is False


class TestReceivablesStretch:
    """receivables_stretch fires when AR grows > revenue_growth + 10pp."""

    def test_fires_when_ar_far_outpaces_revenue(self) -> None:
        # Revenue +10%, AR +25%
        cur = _row(revenue=110.0, receivables=12.5)
        pri = _row(revenue=100.0, receivables=10.0)
        assert _sensor_receivables_stretch(cur, pri) is True

    def test_does_not_fire_within_threshold(self) -> None:
        # Revenue +10%, AR +15% → gap = 5pp (< 10pp threshold)
        cur = _row(revenue=110.0, receivables=11.5)
        pri = _row(revenue=100.0, receivables=10.0)
        assert _sensor_receivables_stretch(cur, pri) is False

    def test_returns_none_on_missing_receivables(self) -> None:
        cur = _row(revenue=110.0, receivables=float("nan"))
        pri = _row(revenue=100.0, receivables=10.0)
        assert _sensor_receivables_stretch(cur, pri) is None

    def test_returns_none_when_revenue_not_positive(self) -> None:
        cur = _row(revenue=-10.0, receivables=12.5)
        pri = _row(revenue=-5.0, receivables=10.0)
        assert _sensor_receivables_stretch(cur, pri) is None

    def test_ar_grows_same_rate_no_fire(self) -> None:
        # AR grows exactly same % as revenue
        cur = _row(revenue=110.0, receivables=11.0)
        pri = _row(revenue=100.0, receivables=10.0)
        assert _sensor_receivables_stretch(cur, pri) is False


class TestInventoryBuild:
    """inventory_build fires when inventory grows > revenue_growth + 15pp."""

    def test_fires_when_inventory_far_outpaces_revenue(self) -> None:
        # Revenue +5%, Inventory +25%
        cur = _row(revenue=105.0, inventory=6.25)
        pri = _row(revenue=100.0, inventory=5.0)
        assert _sensor_inventory_build(cur, pri) is True

    def test_does_not_fire_within_threshold(self) -> None:
        # Revenue +5%, Inventory +18% → gap = 13pp (< 15pp threshold)
        cur = _row(revenue=105.0, inventory=5.9)
        pri = _row(revenue=100.0, inventory=5.0)
        assert _sensor_inventory_build(cur, pri) is False

    def test_returns_none_on_missing_inventory(self) -> None:
        cur = _row(revenue=105.0, inventory=float("nan"))
        pri = _row(revenue=100.0, inventory=5.0)
        assert _sensor_inventory_build(cur, pri) is None

    def test_returns_none_when_revenue_not_positive(self) -> None:
        cur = _row(revenue=0.0, inventory=6.25)
        pri = _row(revenue=100.0, inventory=5.0)
        assert _sensor_inventory_build(cur, pri) is None


class TestCapexIntensity:
    """capital_intensity_rising fires when capex grows >> revenue AND op_income."""

    def test_fires_when_capex_far_outpaces_both(self) -> None:
        # Revenue +5%, Op_income +5%, Capex +30%
        cur = _row(revenue=105.0, op_income=21.0, capex=10.4)
        pri = _row(revenue=100.0, op_income=20.0, capex=8.0)
        assert _sensor_capex_intensity(cur, pri) is True

    def test_does_not_fire_when_capex_in_line_with_revenue(self) -> None:
        # Revenue +10%, Capex +15% → gap = 5pp (< 10pp threshold)
        cur = _row(revenue=110.0, op_income=22.0, capex=9.2)
        pri = _row(revenue=100.0, op_income=20.0, capex=8.0)
        assert _sensor_capex_intensity(cur, pri) is False

    def test_returns_none_on_missing_capex(self) -> None:
        cur = _row(revenue=110.0, op_income=22.0, capex=float("nan"))
        pri = _row(revenue=100.0, op_income=20.0, capex=8.0)
        assert _sensor_capex_intensity(cur, pri) is None

    def test_returns_none_when_capex_not_positive(self) -> None:
        # capex = 0 or negative = disposal, skip
        cur = _row(revenue=110.0, op_income=22.0, capex=-2.0)
        pri = _row(revenue=100.0, op_income=20.0, capex=8.0)
        assert _sensor_capex_intensity(cur, pri) is None

    def test_relaxed_logic_when_op_income_not_positive(self) -> None:
        # op_income <= 0: only capex vs revenue gate applies
        # Capex +30% vs Revenue +5% → fires
        cur = _row(revenue=105.0, op_income=-5.0, capex=10.4)
        pri = _row(revenue=100.0, op_income=20.0, capex=8.0)
        assert _sensor_capex_intensity(cur, pri) is True


# ===========================================================================
# Group B — Coverage stamps
# ===========================================================================


class TestCoverageStamps:
    """Every result carries required firewall and coverage annotations."""

    def test_firewall_stamps_present(self) -> None:
        rows = [
            {"ticker": "X", "fy": 2023, "revenue": 100.0, "gross_profit": 50.0,
             "op_income": 20.0, "receivables": 10.0, "inventory": 5.0, "capex": 8.0},
            {"ticker": "X", "fy": 2024, "revenue": 110.0, "gross_profit": 52.0,
             "op_income": 21.0, "receivables": 11.0, "inventory": 5.2, "capex": 8.5},
        ]
        df = _make_statements(rows)
        result = compute_moat_falsifiers("X", df)
        assert result["_horizon_role"] == "hold_thesis"
        assert result["_display_only"] is True
        assert result["_version"] == "v1"
        assert "sensor_coverage" in result
        assert "coverage_n_years" in result

    def test_missing_ticker_returns_missing_stamps(self) -> None:
        df = _make_statements([{"ticker": "OTHER", "fy": 2024}])
        result = compute_moat_falsifiers("NOTEXIST", df)
        assert result["sensor_coverage"] == "missing"
        assert result["coverage_n_years"] == 0
        assert result["_horizon_role"] == "hold_thesis"
        assert result["_display_only"] is True

    def test_empty_df_returns_missing(self) -> None:
        result = compute_moat_falsifiers("AAPL", pd.DataFrame())
        assert result["sensor_coverage"] == "missing"
        assert result["_display_only"] is True

    def test_single_year_is_partial(self) -> None:
        df = _make_statements([{"ticker": "ONE", "fy": 2024, "revenue": 100.0}])
        result = compute_moat_falsifiers("ONE", df)
        assert result["coverage_n_years"] == 1
        # single row → no year-pair possible
        for s_dict in result["sensors"].values():
            assert s_dict["fired"] is None

    def test_all_sensor_keys_present(self) -> None:
        rows = [
            {"ticker": "Y", "fy": 2023, "revenue": 100.0, "gross_profit": 50.0,
             "op_income": 20.0, "receivables": 10.0, "inventory": 5.0, "capex": 8.0},
            {"ticker": "Y", "fy": 2024, "revenue": 110.0, "gross_profit": 52.0,
             "op_income": 22.0, "receivables": 11.5, "inventory": 5.3, "capex": 9.0},
        ]
        df = _make_statements(rows)
        result = compute_moat_falsifiers("Y", df)
        for sensor_name in _SENSOR_FNS:
            assert sensor_name in result["sensors"], f"Missing sensor: {sensor_name}"
            s = result["sensors"][sensor_name]
            assert "fired" in s
            assert "base_rate_annual_fy" in s
            assert "base_rate_median_all_years" in s
            assert "coverage" in s


# ===========================================================================
# Group C — Base-rate computation
# ===========================================================================


class TestBaseRateComputation:
    """Base rates are correctly computed across a synthetic universe."""

    def _universe_df(self) -> pd.DataFrame:
        """10 tickers × 3 years each; known fire patterns for margin_compression."""
        rows = []
        for i in range(1, 11):
            tk = f"TK{i:02d}"
            for fy, rev, gp in [
                (2021, 100.0, 50.0),
                (2022, 110.0, 50.0),  # revenue +10%, margin down → fires margin_compression
                (2023, 120.0, 55.0),  # revenue +9%, margin ~46% → still fires for some
            ]:
                rows.append({
                    "ticker": tk, "fy": fy, "revenue": rev, "gross_profit": gp,
                    "op_income": 20.0, "receivables": 10.0, "inventory": 5.0, "capex": 8.0,
                    "assets": 200.0, "ni": 12.0, "cfo": 15.0, "cash": 20.0,
                    "equity": 80.0, "liabilities": 120.0, "cur_assets": 80.0, "cur_liab": 40.0,
                })
        return pd.DataFrame(rows)

    def test_base_rates_have_all_sensors(self) -> None:
        df = self._universe_df()
        rates = compute_base_rates(df)
        assert set(rates.keys()) == set(_SENSOR_FNS.keys())

    def test_base_rates_between_zero_and_one(self) -> None:
        df = self._universe_df()
        rates = compute_base_rates(df)
        for sensor, fy_rates in rates.items():
            for fy, rate in fy_rates.items():
                assert 0.0 <= rate <= 1.0, (
                    f"Base rate out of range for {sensor} FY={fy}: {rate}"
                )

    def test_margin_compression_base_rate_non_zero(self) -> None:
        """margin_compression should fire for the 2022 FY (revenue +10%, margin drops)."""
        df = self._universe_df()
        rates = compute_base_rates(df)
        mc_rates = rates["margin_compression_despite_revenue_growth"]
        # FY 2022: all 10 tickers had revenue +10% and margin dropped (50.0% → 45.5%)
        assert 2022 in mc_rates, "FY 2022 rate missing"
        assert mc_rates[2022] > 0.0, "Expected some margin compression fires in 2022"

    def test_empty_df_returns_empty_rates(self) -> None:
        rates = compute_base_rates(pd.DataFrame())
        for sensor in _SENSOR_FNS:
            assert rates[sensor] == {}

    def test_missing_cols_returns_empty_rates(self) -> None:
        df = pd.DataFrame([{"ticker": "X", "fy": 2022}])
        rates = compute_base_rates(df)
        # All rates should be empty (no evaluable pairs due to missing columns)
        for sensor in _SENSOR_FNS:
            assert rates[sensor] == {}

    def test_base_rate_fy_in_result(self) -> None:
        """base_rate_annual_fy in sensor result matches the base_rates dict."""
        rows = []
        for i in range(1, 10):
            tk = f"AA{i}"
            rows += [
                {"ticker": tk, "fy": 2023, "revenue": 100.0, "gross_profit": 50.0,
                 "op_income": 20.0, "receivables": 10.0, "inventory": 5.0, "capex": 8.0,
                 "assets": 200.0, "ni": 10.0, "cfo": 12.0, "cash": 15.0,
                 "equity": 70.0, "liabilities": 130.0, "cur_assets": 60.0, "cur_liab": 30.0},
                {"ticker": tk, "fy": 2024, "revenue": 115.0, "gross_profit": 52.0,
                 "op_income": 21.0, "receivables": 13.0, "inventory": 5.1, "capex": 8.5,
                 "assets": 200.0, "ni": 11.0, "cfo": 13.0, "cash": 16.0,
                 "equity": 75.0, "liabilities": 125.0, "cur_assets": 65.0, "cur_liab": 32.0},
            ]
        df = pd.DataFrame(rows)
        base = compute_base_rates(df)
        result = compute_moat_falsifiers("AA1", df, base_rates=base)
        for sensor_name, s_dict in result["sensors"].items():
            if s_dict["fy_evaluated"] is not None:
                fy = s_dict["fy_evaluated"]
                expected = base.get(sensor_name, {}).get(fy)
                assert s_dict["base_rate_annual_fy"] == expected, (
                    f"{sensor_name} FY={fy}: expected {expected}, got {s_dict['base_rate_annual_fy']}"
                )


# ===========================================================================
# Group D — Great-company-trap overlay
# ===========================================================================


class TestGreatCompanyTrap:
    """Overlay only lowers conviction; inputs printed; deterministic."""

    def test_all_three_legs_fire(self) -> None:
        result = great_company_trap(
            crowding_z=2.0,
            insider_net_usd=-1_000_000,
            revision_direction="downgrading",
        )
        assert result["trap_signals_present"] is True
        assert len(result["de_escalation_reason"]) == 3

    def test_no_legs_fire(self) -> None:
        result = great_company_trap(
            crowding_z=0.5,
            insider_net_usd=100_000,
            revision_direction="upgrading",
        )
        assert result["trap_signals_present"] is False
        assert result["de_escalation_reason"] == []

    def test_only_crowding_fires(self) -> None:
        result = great_company_trap(
            crowding_z=2.0,
            insider_net_usd=200_000,
            revision_direction="stable",
        )
        assert result["trap_signals_present"] is True
        assert result["legs"]["crowding"]["fired"] is True
        assert result["legs"]["insider_net"]["fired"] is False
        assert result["legs"]["revision_direction"]["fired"] is False

    def test_only_insider_net_selling_fires(self) -> None:
        result = great_company_trap(
            crowding_z=0.5,
            insider_net_usd=-600_000,
            revision_direction="stable",
        )
        assert result["trap_signals_present"] is True
        assert result["legs"]["insider_net"]["fired"] is True
        assert result["legs"]["crowding"]["fired"] is False

    def test_only_revision_downgrading_fires(self) -> None:
        result = great_company_trap(
            crowding_z=0.3,
            insider_net_usd=0.0,
            revision_direction="downgrading",
        )
        assert result["trap_signals_present"] is True
        assert result["legs"]["revision_direction"]["fired"] is True
        assert result["legs"]["crowding"]["fired"] is False

    def test_available_flags_when_none(self) -> None:
        """Passing None → available=False; fired=False; no de-escalation."""
        result = great_company_trap(
            crowding_z=None,
            insider_net_usd=None,
            revision_direction=None,
        )
        assert result["trap_signals_present"] is False
        for leg in result["legs"].values():
            assert leg["available"] is False
            assert leg["fired"] is False

    def test_inputs_are_printed_verbatim(self) -> None:
        result = great_company_trap(
            crowding_z=1.8,
            insider_net_usd=-750_000,
            revision_direction="downgrading",
        )
        assert result["inputs_used"]["crowding_z"] == 1.8
        assert result["inputs_used"]["insider_net_usd"] == -750_000
        assert result["inputs_used"]["revision_direction"] == "downgrading"

    def test_firewall_stamps(self) -> None:
        result = great_company_trap()
        assert result["_horizon_role"] == "hold_thesis"
        assert result["_display_only"] is True
        assert result["_version"] == "v1"

    def test_does_not_escalate(self) -> None:
        """Trap output has no 'escalation', 'buy', or 'score_boost' keys."""
        result = great_company_trap(crowding_z=0.1, revision_direction="upgrading")
        for key in ("escalate", "escalation", "score_boost", "buy", "upgrade_signal"):
            assert key not in result, f"Forbidden escalation key found: {key}"

    def test_stable_revision_does_not_fire(self) -> None:
        result = great_company_trap(revision_direction="stable")
        assert result["legs"]["revision_direction"]["fired"] is False

    def test_upgrading_revision_does_not_fire(self) -> None:
        result = great_company_trap(revision_direction="upgrading")
        assert result["legs"]["revision_direction"]["fired"] is False

    def test_threshold_boundary_crowding_exact(self) -> None:
        """Crowding_z exactly at threshold (1.0 = engine.theme_crowding.CROWDED_Z) → fires."""
        result = great_company_trap(crowding_z=1.0)
        assert result["legs"]["crowding"]["fired"] is True

    def test_threshold_boundary_crowding_below(self) -> None:
        """Crowding_z just below threshold → does not fire."""
        result = great_company_trap(crowding_z=0.999)
        assert result["legs"]["crowding"]["fired"] is False


# ===========================================================================
# Group E — Firewall: registry allowlist
# ===========================================================================


class TestFirewall:
    """moat-falsifier-sensors artifact must be hold_thesis with no scored_path_surfaces."""

    def _load_registry(self) -> dict:
        from engine.neuralweb.synapse import load_registry
        return load_registry(REPO_ROOT)

    def test_moat_falsifier_artifact_is_hold_thesis(self) -> None:
        """moat-falsifier-sensors artifact must exist and be hold_thesis."""
        reg = self._load_registry()
        arts = reg.get("artifacts") or {}
        assert "moat-falsifier-sensors" in arts, (
            "moat-falsifier-sensors not registered in config/synapse.yml. "
            "Add it with horizon_role: hold_thesis."
        )
        art = arts["moat-falsifier-sensors"]
        assert art.get("horizon_role") == "hold_thesis", (
            f"moat-falsifier-sensors has wrong horizon_role: {art.get('horizon_role')!r}. "
            "Must be 'hold_thesis'."
        )

    def test_moat_falsifier_no_scored_path_surfaces(self) -> None:
        """moat-falsifier-sensors must have no scored_path_surfaces."""
        reg = self._load_registry()
        arts = reg.get("artifacts") or {}
        if "moat-falsifier-sensors" not in arts:
            pytest.skip("moat-falsifier-sensors not in registry (test_moat_falsifier_artifact_is_hold_thesis will fail)")
        art = arts["moat-falsifier-sensors"]
        surfaces = list(art.get("scored_path_surfaces") or [])
        assert surfaces == [], (
            f"moat-falsifier-sensors has scored_path_surfaces: {surfaces}. "
            "hold_thesis artifacts must never route to entry scoring surfaces (LH-R1)."
        )

    def test_great_company_trap_artifact_is_hold_thesis(self) -> None:
        """great-company-trap artifact must exist and be hold_thesis."""
        reg = self._load_registry()
        arts = reg.get("artifacts") or {}
        assert "great-company-trap" in arts, (
            "great-company-trap not registered in config/synapse.yml. "
            "Add it with horizon_role: hold_thesis."
        )
        art = arts["great-company-trap"]
        assert art.get("horizon_role") == "hold_thesis", (
            f"great-company-trap has wrong horizon_role: {art.get('horizon_role')!r}."
        )

    def test_great_company_trap_no_scored_path_surfaces(self) -> None:
        """great-company-trap must have no scored_path_surfaces."""
        reg = self._load_registry()
        arts = reg.get("artifacts") or {}
        if "great-company-trap" not in arts:
            pytest.skip("great-company-trap not in registry")
        art = arts["great-company-trap"]
        surfaces = list(art.get("scored_path_surfaces") or [])
        assert surfaces == [], (
            f"great-company-trap has scored_path_surfaces: {surfaces}. "
            "hold_thesis artifacts must never route to entry scoring surfaces (LH-R1)."
        )

    def test_horizon_firewall_still_clean_after_new_artifacts(self) -> None:
        """Full horizon firewall must still pass with new hold_thesis artifacts."""
        from scripts.check_synapse_reads import check_horizon_firewall
        reg = self._load_registry()
        violations = check_horizon_firewall(reg)
        if violations:
            msgs = [v.label() for v in violations]
            pytest.fail(
                f"Horizon firewall violations after W2 PR-K registration:\n"
                + "\n".join(msgs)
            )

    def test_hold_thesis_allowlist_updated(self) -> None:
        """test_horizon_firewall.py allowlist must include the new W2 PR-K artifacts."""
        firewall_test_path = REPO_ROOT / "tests" / "test_horizon_firewall.py"
        assert firewall_test_path.exists()
        source = firewall_test_path.read_text(encoding="utf-8")
        assert "moat-falsifier-sensors" in source, (
            "tests/test_horizon_firewall.py _EXPECTED_HOLD_THESIS_ARTIFACTS does not "
            "include 'moat-falsifier-sensors'. Update it to prevent false firewall failures."
        )
        assert "great-company-trap" in source, (
            "tests/test_horizon_firewall.py _EXPECTED_HOLD_THESIS_ARTIFACTS does not "
            "include 'great-company-trap'. Update it."
        )


# ===========================================================================
# Group F — Point-in-time gate (W2 PR-K PIT fix)
# ===========================================================================


class TestPointInTimeGate:
    """A fiscal row whose availability date (period_end + 120d) is AFTER the as-of
    date was not yet filed, and must be dropped before any sensor evaluates."""

    def _prior_plus_future(self, future_period_end: str, future_fy: int = 2026) -> pd.DataFrame:
        """Filed prior FY + a margin-compressing future FY (revenue +10%, gross
        margin halved → margin_compression WOULD fire if the future row were used)."""
        return _make_statements([
            {"ticker": "PIT", "fy": future_fy - 1, "revenue": 100.0, "gross_profit": 50.0,
             "op_income": 20.0, "receivables": 10.0, "inventory": 5.0, "capex": 8.0,
             "period_end": f"{future_fy - 1}-12-31"},
            {"ticker": "PIT", "fy": future_fy, "revenue": 110.0, "gross_profit": 27.5,
             "op_income": 20.0, "receivables": 10.0, "inventory": 5.0, "capex": 8.0,
             "period_end": future_period_end},
        ])

    def test_not_yet_filed_row_does_not_fire(self) -> None:
        # period_end 2026-12-31 → available 2027-04-30, AFTER as-of 2026-07-05.
        df = self._prior_plus_future("2026-12-31")
        res = compute_moat_falsifiers("PIT", df, asof_date="2026-07-05")
        mc = res["sensors"]["margin_compression_despite_revenue_growth"]
        assert mc["fired"] in (None, False), f"not-yet-filed FY2026 fired: {mc}"
        assert mc["fy_evaluated"] != 2026

    def test_filed_row_still_fires_after_availability(self) -> None:
        # Same shape, but as-of 2027-06-01 is AFTER availability (2027-04-30).
        df = self._prior_plus_future("2026-12-31")
        res = compute_moat_falsifiers("PIT", df, asof_date="2027-06-01")
        mc = res["sensors"]["margin_compression_despite_revenue_growth"]
        assert mc["fired"] is True
        assert mc["fy_evaluated"] == 2026

    def test_none_asof_gates_against_today(self) -> None:
        # A fiscal year that files far in the future must not fire on the live path
        # (asof_date=None → today).  period_end year+1 guarantees availability > now.
        future_fy = pd.Timestamp.now().year + 2
        df = self._prior_plus_future(f"{future_fy}-12-31", future_fy=future_fy)
        res = compute_moat_falsifiers("PIT", df, asof_date=None)
        mc = res["sensors"]["margin_compression_despite_revenue_growth"]
        assert mc["fired"] in (None, False), f"future FY fired on live path: {mc}"
        assert mc["fy_evaluated"] != future_fy

    def test_missing_period_end_is_kept(self) -> None:
        # Legacy rows without a period_end column cannot be gated → kept & evaluated.
        df = _make_statements([
            {"ticker": "LEG", "fy": 2023, "revenue": 100.0, "gross_profit": 50.0,
             "op_income": 20.0, "receivables": 10.0, "inventory": 5.0, "capex": 8.0},
            {"ticker": "LEG", "fy": 2024, "revenue": 110.0, "gross_profit": 27.5,
             "op_income": 20.0, "receivables": 10.0, "inventory": 5.0, "capex": 8.0},
        ])
        assert "period_end" not in df.columns
        res = compute_moat_falsifiers("LEG", df, asof_date="2026-07-05")
        mc = res["sensors"]["margin_compression_despite_revenue_growth"]
        assert mc["fired"] is True

    def test_base_rates_exclude_not_yet_filed_fy(self) -> None:
        # 6 names each with a not-yet-filed compressing FY2026 → FY2026 must be
        # absent from the base rate as of 2026-07-05 (rows dropped before pairing).
        rows: list[dict] = []
        for i in range(6):
            tk = f"BR{i}"
            rows += [
                {"ticker": tk, "fy": 2025, "revenue": 100.0, "gross_profit": 50.0,
                 "op_income": 20.0, "receivables": 10.0, "inventory": 5.0, "capex": 8.0,
                 "period_end": "2025-12-31"},
                {"ticker": tk, "fy": 2026, "revenue": 110.0, "gross_profit": 27.5,
                 "op_income": 20.0, "receivables": 10.0, "inventory": 5.0, "capex": 8.0,
                 "period_end": "2026-12-31"},
            ]
        df = _make_statements(rows)
        rates = compute_base_rates(df, asof_date="2026-07-05")
        mc = rates["margin_compression_despite_revenue_growth"]
        assert 2026 not in mc, f"not-yet-filed FY2026 leaked into base rate: {mc}"


# ---------------------------------------------------------------------------
# F. Declared evidence gates the verdict (2026-08-07)
# ---------------------------------------------------------------------------

class TestDeclaredEvidenceGatesTheVerdict:
    """A sensor must not publish `fired` on an input it DECLARES it requires.

    ``_sensor_cols()`` is this module's own statement of what each sensor needs.
    Publishing ``fired=True`` while one of those inputs is absent is the module
    contradicting itself, and it did exactly that until 2026-08-07:
    ``_sensor_capex_intensity`` read a MISSING ``op_income`` as licence to take
    the revenue-only fallback — a branch that exists only for a NON-POSITIVE
    operating income — and fired on 62 of the 336 live ``capital_intensity_rising``
    fires in ``data/edgar/statements.parquet`` (18%), while ``_assess_coverage``
    recorded those very rows as ``"partial"``.

    The coverage flag is not a safety net. ``engine/thesis_funnel.py`` reads
    ``sv.get("fired")`` and never reads ``sv.get("coverage")``, so the module's
    own "our evidence is incomplete" annotation is dropped before the signal
    reaches ``site/stock.html``. The VERDICT itself has to carry the refusal,
    which is why these tests assert on ``fired`` and not on ``coverage``.
    """

    @staticmethod
    def _pair(**current_overrides) -> pd.DataFrame:
        """Two adjacent FYs where capex growth clears every threshold by a mile.

        Capex +100% against revenue +3% is far outside the 10pp band, so any
        sensor that reaches a verdict at all will FIRE. That makes "did not
        fire" unambiguous evidence of a refusal rather than of a near miss.
        """
        current = {
            "ticker": "EVD", "fy": 2026, "period_end": "2026-12-31",
            "revenue": 1030.0, "gross_profit": 400.0, "receivables": 100.0,
            "inventory": 100.0, "capex": 200.0, "op_income": 210.0,
        }
        current.update(current_overrides)
        return _make_statements([
            {"ticker": "EVD", "fy": 2025, "period_end": "2025-12-31",
             "revenue": 1000.0, "gross_profit": 400.0, "receivables": 100.0,
             "inventory": 100.0, "capex": 100.0, "op_income": 200.0},
            current,
        ])

    def test_control_fires_so_the_refusals_below_mean_something(self) -> None:
        """Non-vacuity anchor: with every input present this pair DOES fire."""
        res = compute_moat_falsifiers("EVD", self._pair(), asof_date="2027-06-01")
        assert res["sensors"]["capital_intensity_rising"]["fired"] is True, (
            "the control pair no longer fires capital_intensity_rising, so the "
            "not-evaluable assertions below would pass for the wrong reason — "
            "they would be measuring a harness that never reaches the sensor."
        )

    @pytest.mark.parametrize("missing", ["op_income", "capex", "revenue"])
    def test_absent_declared_input_publishes_not_evaluable_never_a_fire(self, missing) -> None:
        """Absence must reach the published dict as None, not as a verdict."""
        res = compute_moat_falsifiers(
            "EVD", self._pair(**{missing: np.nan}), asof_date="2027-06-01"
        )
        sensor = res["sensors"]["capital_intensity_rising"]
        assert sensor["fired"] is not True, (
            f"capital_intensity_rising published fired={sensor['fired']!r} while "
            f"its declared-required input {missing!r} was absent "
            f"(_sensor_cols() -> {_sensor_cols()['capital_intensity_rising']}). "
            f"A signal computed on evidence the module does not have reaches "
            f"site/stock.html with no trace of what was missing, because "
            f"engine/thesis_funnel.py forwards `fired` and drops `coverage`."
        )

    def test_nonpositive_operating_income_keeps_its_disclosed_fallback(self) -> None:
        """The revenue-only branch is deliberate and must NOT be gated away.

        A loss-making filer has no interpretable operating-income growth, so the
        capex-vs-revenue leg alone decides. This is published to users
        bilingually by scripts/build_fundamental_forensics.py ("revenue-only when
        operating income is non-positive") and taken by the registry kernel too.
        De-escalating the ABSENT case must not collaterally kill this one — that
        would drop findings two live surfaces already show.
        """
        res = compute_moat_falsifiers(
            "EVD", self._pair(op_income=-50.0), asof_date="2027-06-01"
        )
        assert res["sensors"]["capital_intensity_rising"]["fired"] is True, (
            "the documented non-positive-operating-income fallback stopped "
            "firing. Unknown is not non-positive: the fix for absent evidence "
            "must key on whether the CURRENT value is known, not on whether the "
            "growth term happens to be computable."
        )
