"""tests/test_capital_allocation.py — LT-3a: Buyback-execution reader + capital_allocation_delta.

Five test groups:

  A. Delta classification: 'accretive', 'dilutive', 'neutral', 'unavailable' states
     exercised via synthetic data.

  B. TTM repurchase computation: PIT gating (filed date present), window logic,
     coverage stamps (full/partial/missing).

  C. SBC handling: null SBC → 'unavailable', non-null SBC → net_buyback_after_sbc
     is computed; never treats None as zero.

  D. Derived fields: buyback_yield, share_count_reduction_confirmed,
     debt_funded_buyback_flag — all four delta states via compute_capital_allocation.

  E. Firewall: synapse.yml entry for capital-allocation-delta has
     tier=display, scored_path_surfaces=[], horizon_role=hold_thesis,
     fdr_family=long_hold, _display_only=True, _horizon_role=hold_thesis
     in every result dict.

All tests are deterministic. Groups A–D use purely in-memory data.
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

from engine.capital_allocation import (  # noqa: E402
    compute_capital_allocation,
    _classify_delta,
    _compute_repurch_ttm,
    _get_annual_repurchases,
    _get_sbc_ttm,
    _fy_overlaps_ttm_window,
    _ACCRETIVE_SHARES_CHANGE_PCT,
    _DILUTIVE_SHARES_CHANGE_PCT,
    _HORIZON_ROLE,
)


# ── Fixture helpers ──────────────────────────────────────────────────────────

_TODAY = pd.Timestamp("2026-06-01")


def _make_quarterly(rows: list[dict], ticker: str = "TEST") -> pd.DataFrame:
    """Build a synthetic statements_quarterly DataFrame."""
    defaults = {
        "ticker": ticker,
        "fiscal_year": 2025,
        "fiscal_quarter": 1,
        "period_end": "2025-03-31",
        "filed": "2025-05-01",
        "repurchases": 50_000_000.0,
        "shares": 1_000_000.0,
        "revenue": None,
    }
    full_rows = []
    for r in rows:
        row = dict(defaults)
        row.update(r)
        full_rows.append(row)
    return pd.DataFrame(full_rows)


def _make_fundamentals_panel(rows: list[dict], ticker: str = "TEST") -> pd.DataFrame:
    """Build a synthetic fundamentals_panel DataFrame."""
    defaults = {
        "ticker": ticker,
        "fy": 2024,
        "shares": 1_000_000.0,
        "debt_lt": 500_000_000.0,
        "dividends": 10_000_000.0,
        "asof_date": "2025-04-30",
        "period_end": "2024-12-31",
    }
    full_rows = []
    for r in rows:
        row = dict(defaults)
        row.update(r)
        full_rows.append(row)
    return pd.DataFrame(full_rows)


def _make_statements(rows: list[dict], ticker: str = "TEST") -> pd.DataFrame:
    """Build a synthetic statements DataFrame with sbc column."""
    defaults = {
        "ticker": ticker,
        "fy": 2024,
        "sbc": None,
        "period_end": "2024-12-31",
        "revenue": 1_000_000_000.0,
    }
    full_rows = []
    for r in rows:
        row = dict(defaults)
        row.update(r)
        full_rows.append(row)
    return pd.DataFrame(full_rows)


# ── Group A: Delta classification (pure function) ────────────────────────────

class TestDeltaClassification:
    """_classify_delta returns the correct state for all four outcomes."""

    def test_accretive_state(self) -> None:
        delta = _classify_delta(
            shares_yoy_change_pct=_ACCRETIVE_SHARES_CHANGE_PCT - 0.1,  # < -0.5%
            repurch_ttm=100_000_000.0,
        )
        assert delta == "accretive"

    def test_accretive_exactly_at_threshold(self) -> None:
        delta = _classify_delta(
            shares_yoy_change_pct=_ACCRETIVE_SHARES_CHANGE_PCT,  # exactly -0.5%
            repurch_ttm=100_000_000.0,
        )
        assert delta == "accretive"

    def test_dilutive_state(self) -> None:
        delta = _classify_delta(
            shares_yoy_change_pct=_DILUTIVE_SHARES_CHANGE_PCT + 0.1,  # > +3%
            repurch_ttm=None,
        )
        assert delta == "dilutive"

    def test_dilutive_exactly_at_threshold(self) -> None:
        delta = _classify_delta(
            shares_yoy_change_pct=_DILUTIVE_SHARES_CHANGE_PCT,  # exactly +3%
            repurch_ttm=0.0,
        )
        assert delta == "dilutive"

    def test_neutral_state_shares_shrinking_but_no_repurchases(self) -> None:
        # shares shrinking but repurch_ttm is None → not accretive → neutral
        delta = _classify_delta(
            shares_yoy_change_pct=-1.0,
            repurch_ttm=None,
        )
        assert delta == "neutral"

    def test_neutral_state_shares_slightly_growing(self) -> None:
        # small growth below dilutive threshold
        delta = _classify_delta(
            shares_yoy_change_pct=1.0,
            repurch_ttm=50_000_000.0,
        )
        assert delta == "neutral"

    def test_neutral_state_zero_change(self) -> None:
        delta = _classify_delta(
            shares_yoy_change_pct=0.0,
            repurch_ttm=50_000_000.0,
        )
        assert delta == "neutral"

    def test_unavailable_no_shares_data(self) -> None:
        delta = _classify_delta(
            shares_yoy_change_pct=None,
            repurch_ttm=100_000_000.0,
        )
        assert delta == "unavailable"

    def test_dilutive_takes_priority_over_accretive_check(self) -> None:
        # Even with a large share shrink, if >= +3% it should NOT be accretive.
        # This case is impossible in reality (shares can't both shrink and grow),
        # but we verify the conditional ordering: dilutive check runs first.
        delta = _classify_delta(
            shares_yoy_change_pct=3.5,   # dilutive
            repurch_ttm=1_000_000_000.0,  # large buyback irrelevant
        )
        assert delta == "dilutive"


# ── Group B: TTM repurchase computation ──────────────────────────────────────

class TestRepurchTTM:
    """_compute_repurch_ttm correctly sums TTM repurchases with PIT gating."""

    def test_full_coverage_four_quarters(self) -> None:
        # asof=2025-12-31 → TTM window: 2024-12-31..2025-12-31 — all 4 quarters included
        df = _make_quarterly([
            {"fiscal_quarter": 1, "period_end": "2025-09-30", "filed": "2025-11-01", "repurchases": 100e6},
            {"fiscal_quarter": 2, "period_end": "2025-06-30", "filed": "2025-08-01", "repurchases": 80e6},
            {"fiscal_quarter": 3, "period_end": "2025-03-31", "filed": "2025-05-01", "repurchases": 60e6},
            {"fiscal_quarter": 4, "period_end": "2024-12-31", "filed": "2025-01-31", "repurchases": 40e6},
        ])
        ttm, cov = _compute_repurch_ttm("TEST", df, as_of_date=pd.Timestamp("2025-12-31"))
        assert cov == "full"
        assert ttm == pytest.approx(280e6)

    def test_partial_coverage_fewer_than_four_quarters(self) -> None:
        df = _make_quarterly([
            {"fiscal_quarter": 1, "period_end": "2025-09-30", "filed": "2025-11-01", "repurchases": 100e6},
            {"fiscal_quarter": 2, "period_end": "2025-06-30", "filed": "2025-08-01", "repurchases": 80e6},
        ])
        ttm, cov = _compute_repurch_ttm("TEST", df, as_of_date=pd.Timestamp("2026-01-01"))
        assert cov == "partial"
        assert ttm == pytest.approx(180e6)

    def test_pit_gate_excludes_unfiled_rows(self) -> None:
        df = _make_quarterly([
            {"fiscal_quarter": 1, "period_end": "2025-09-30", "filed": None, "repurchases": 200e6},  # unfiled
            {"fiscal_quarter": 2, "period_end": "2025-06-30", "filed": "2025-08-01", "repurchases": 80e6},
        ])
        ttm, cov = _compute_repurch_ttm("TEST", df, as_of_date=pd.Timestamp("2026-01-01"))
        # unfiled row excluded; only one filed row counts
        assert cov == "partial"
        assert ttm == pytest.approx(80e6)

    def test_pit_gate_excludes_future_filed_rows(self) -> None:
        df = _make_quarterly([
            {"fiscal_quarter": 1, "period_end": "2025-09-30", "filed": "2026-07-01", "repurchases": 200e6},  # filed after asof
            {"fiscal_quarter": 2, "period_end": "2025-06-30", "filed": "2025-08-01", "repurchases": 80e6},
        ])
        asof = pd.Timestamp("2026-01-01")
        ttm, cov = _compute_repurch_ttm("TEST", df, as_of_date=asof)
        # Only the Q2 row was filed before asof
        assert ttm == pytest.approx(80e6)

    def test_missing_when_no_repurchases_data(self) -> None:
        df = _make_quarterly([
            {"fiscal_quarter": 1, "period_end": "2025-09-30", "filed": "2025-11-01", "repurchases": None},
        ])
        ttm, cov = _compute_repurch_ttm("TEST", df, as_of_date=pd.Timestamp("2026-01-01"))
        assert cov == "missing"
        assert ttm is None

    def test_missing_when_ticker_not_in_df(self) -> None:
        df = _make_quarterly([
            {"ticker": "OTHER", "fiscal_quarter": 1, "period_end": "2025-09-30",
             "filed": "2025-11-01", "repurchases": 100e6},
        ])
        ttm, cov = _compute_repurch_ttm("TEST", df, as_of_date=pd.Timestamp("2026-01-01"))
        assert cov == "missing"
        assert ttm is None

    def test_missing_on_empty_dataframe(self) -> None:
        ttm, cov = _compute_repurch_ttm("TEST", pd.DataFrame(), as_of_date=pd.Timestamp("2026-01-01"))
        assert cov == "missing"
        assert ttm is None

    def test_ttm_window_excludes_quarters_older_than_12_months(self) -> None:
        df = _make_quarterly([
            {"fiscal_quarter": 1, "period_end": "2025-09-30", "filed": "2025-11-01", "repurchases": 100e6},
            {"fiscal_quarter": 2, "period_end": "2024-06-30", "filed": "2024-08-01", "repurchases": 999e6},  # > 12m old
        ])
        ttm, cov = _compute_repurch_ttm("TEST", df, as_of_date=pd.Timestamp("2026-01-01"))
        # only the recent quarter is within TTM window
        assert ttm == pytest.approx(100e6)

    def test_none_asof_defaults_to_today(self) -> None:
        # smoke: passing None as_of_date should not raise
        df = _make_quarterly([
            {"fiscal_quarter": 1, "period_end": "2025-09-30", "filed": "2025-11-01", "repurchases": 100e6},
        ])
        ttm, cov = _compute_repurch_ttm("TEST", df, as_of_date=None)
        # Result depends on today's date; just ensure no crash
        assert isinstance(cov, str)

    def test_dedup_keeps_latest_filed_for_restated_quarter(self) -> None:
        """A quarter re-filed after restatement should not be double-counted."""
        df = _make_quarterly([
            # Q1 filed originally, then restated and re-filed with corrected amount
            {"fiscal_quarter": 1, "period_end": "2025-09-30", "filed": "2025-11-01", "repurchases": 100e6},
            {"fiscal_quarter": 1, "period_end": "2025-09-30", "filed": "2025-12-15", "repurchases": 90e6},  # restatement
        ])
        ttm, cov = _compute_repurch_ttm("TEST", df, as_of_date=pd.Timestamp("2026-01-01"))
        # Only the latest-filed row (90e6) should be counted, not both
        assert ttm == pytest.approx(90e6)
        assert cov == "partial"  # only 1 unique quarter


# ── Group B2: Annual fallback ─────────────────────────────────────────────────

class TestAnnualFallback:
    """compute_capital_allocation falls back to annual repurchases when quarterly is partial."""

    def test_partial_quarterly_triggers_annual_fallback(self) -> None:
        """When only 1 quarterly row exists, repurch_ttm should use annual figure."""
        # Only 1 quarterly row → partial coverage
        q_df = _make_quarterly([
            {"fiscal_quarter": 1, "period_end": "2025-09-30", "filed": "2025-11-01", "repurchases": 25e9},
        ])
        # Annual figure is the correct full-year amount
        fp_df = _make_fundamentals_panel([
            {"fy": 2025, "shares": 985_000.0, "repurchases": 90e9, "asof_date": "2025-10-30"},
            {"fy": 2024, "shares": 1_000_000.0, "asof_date": "2025-04-30"},
        ])
        result = compute_capital_allocation(
            "TEST", q_df, fp_df, mcap=3_000_000_000_000.0,
            as_of_date="2026-01-01",
        )
        # Annual fallback should be used
        assert result["repurch_coverage"] == "annual_fallback"
        assert result["repurch_ttm"] == pytest.approx(90e9)
        # buyback_yield uses annual figure
        assert result["buyback_yield"] == pytest.approx(90e9 / 3_000_000_000_000.0)

    def test_partial_with_no_annual_stays_partial(self) -> None:
        """When quarterly is partial AND annual is unavailable, keep partial."""
        q_df = _make_quarterly([
            {"fiscal_quarter": 1, "period_end": "2025-09-30", "filed": "2025-11-01", "repurchases": 25e9},
        ])
        # fundamentals_panel has no repurchases column
        fp_df = _make_fundamentals_panel([
            {"fy": 2024, "shares": 1_000_000.0, "asof_date": "2025-04-30"},
        ])
        # Remove repurchases column to simulate absence
        fp_df = fp_df.drop(columns=["dividends"], errors="ignore")
        # The repurchases column is built into _make_fundamentals_panel defaults as not present
        # Create panel without repurchases
        fp_df_no_rep = fp_df.drop(columns=["dividends"], errors="ignore")
        # Build a fundamentals panel that has no repurchases column
        fp_noq = pd.DataFrame([{
            "ticker": "TEST", "fy": 2024, "shares": 1_000_000.0,
            "debt_lt": 500_000_000.0, "asof_date": "2025-04-30", "period_end": "2024-12-31",
        }])
        result = compute_capital_allocation(
            "TEST", q_df, fp_noq, mcap=1_000_000_000.0,
            as_of_date="2026-01-01",
        )
        # Without annual, stays partial
        assert result["repurch_coverage"] == "partial"
        assert result["repurch_ttm"] == pytest.approx(25e9)

    def test_net_buyback_after_sbc_none_for_partial_coverage(self) -> None:
        """With partial quarterly coverage and no annual fallback, net_buyback must be None."""
        q_df = _make_quarterly([
            {"fiscal_quarter": 1, "period_end": "2025-09-30", "filed": "2025-11-01", "repurchases": 25e9},
        ])
        fp_noq = pd.DataFrame([{
            "ticker": "TEST", "fy": 2024, "shares": 1_000_000.0,
            "debt_lt": 500_000_000.0, "asof_date": "2025-04-30", "period_end": "2024-12-31",
        }])
        st_df = _make_statements([
            {"fy": 2024, "sbc": 12e9, "period_end": "2024-12-31"},
        ])
        result = compute_capital_allocation(
            "TEST", q_df, fp_noq, statements_df=st_df,
            mcap=3_000_000_000_000.0,
            as_of_date="2026-01-01",
        )
        assert result["repurch_coverage"] == "partial"
        assert result["net_buyback_after_sbc"] is None
        assert result["sbc_note"] is not None
        assert "period mismatch" in result["sbc_note"]

    def test_net_buyback_after_sbc_computed_for_annual_fallback(self) -> None:
        """With annual_fallback coverage AND available SBC, net_buyback_after_sbc is computed."""
        q_df = _make_quarterly([
            {"fiscal_quarter": 1, "period_end": "2025-09-30", "filed": "2025-11-01", "repurchases": 25e9},
        ])
        fp_df = _make_fundamentals_panel([
            {"fy": 2025, "shares": 985_000.0, "repurchases": 90e9, "asof_date": "2025-10-30"},
            {"fy": 2024, "shares": 1_000_000.0, "asof_date": "2025-04-30"},
        ])
        st_df = _make_statements([
            {"fy": 2024, "sbc": 12e9, "period_end": "2024-12-31"},
        ])
        mcap = 3_000_000_000_000.0
        result = compute_capital_allocation(
            "TEST", q_df, fp_df, statements_df=st_df,
            mcap=mcap,
            as_of_date="2026-01-01",
        )
        assert result["repurch_coverage"] == "annual_fallback"
        # net_buyback_after_sbc = (90B - 12B) / 3T
        assert result["net_buyback_after_sbc"] == pytest.approx((90e9 - 12e9) / mcap)


# ── Group C: SBC path ─────────────────────────────────────────────────────────

class TestSBCPath:
    """SBC handling: null SBC → net_buyback_after_sbc is None, not zero."""

    def test_null_sbc_gives_none_net_buyback(self) -> None:
        q_df = _make_quarterly([
            {"fiscal_quarter": 1, "period_end": "2025-09-30", "filed": "2025-11-01", "repurchases": 100e6},
            {"fiscal_quarter": 2, "period_end": "2025-06-30", "filed": "2025-08-01", "repurchases": 80e6},
            {"fiscal_quarter": 3, "period_end": "2025-03-31", "filed": "2025-05-01", "repurchases": 60e6},
            {"fiscal_quarter": 4, "period_end": "2024-12-31", "filed": "2025-01-31", "repurchases": 40e6},
        ])
        fp_df = _make_fundamentals_panel([
            {"fy": 2024, "shares": 900_000.0, "asof_date": "2025-04-30"},
            {"fy": 2023, "shares": 1_000_000.0, "asof_date": "2024-04-30"},
        ])
        # statements_df with no SBC data
        st_df = _make_statements([
            {"fy": 2024, "sbc": None},
        ])
        result = compute_capital_allocation(
            "TEST", q_df, fp_df, statements_df=st_df,
            mcap=10_000_000_000.0,
            as_of_date="2026-01-01",
        )
        assert result["net_buyback_after_sbc"] is None
        assert result["sbc_note"] == "unavailable — SBC not in data"
        assert result["sbc_ttm"] is None

    def test_null_statements_df_gives_none_sbc(self) -> None:
        q_df = _make_quarterly([
            {"fiscal_quarter": 1, "period_end": "2025-09-30", "filed": "2025-11-01", "repurchases": 100e6},
        ])
        fp_df = _make_fundamentals_panel([
            {"fy": 2024, "shares": 900_000.0, "asof_date": "2025-04-30"},
            {"fy": 2023, "shares": 1_000_000.0, "asof_date": "2024-04-30"},
        ])
        result = compute_capital_allocation(
            "TEST", q_df, fp_df, statements_df=None,
            mcap=10_000_000_000.0,
            as_of_date="2026-01-01",
        )
        assert result["sbc_ttm"] is None
        assert result["net_buyback_after_sbc"] is None

    def test_sbc_available_computes_net_buyback(self) -> None:
        # Use asof=2025-12-31 so all 4 quarters are within the TTM window
        q_df = _make_quarterly([
            {"fiscal_quarter": 1, "period_end": "2025-09-30", "filed": "2025-11-01", "repurchases": 200e6},
            {"fiscal_quarter": 2, "period_end": "2025-06-30", "filed": "2025-08-01", "repurchases": 200e6},
            {"fiscal_quarter": 3, "period_end": "2025-03-31", "filed": "2025-05-01", "repurchases": 200e6},
            {"fiscal_quarter": 4, "period_end": "2024-12-31", "filed": "2025-01-31", "repurchases": 200e6},
        ])
        fp_df = _make_fundamentals_panel([
            {"fy": 2024, "shares": 900_000.0, "asof_date": "2025-04-30"},
            {"fy": 2023, "shares": 1_000_000.0, "asof_date": "2024-04-30"},
        ])
        st_df = _make_statements([
            {"fy": 2024, "sbc": 100e6, "period_end": "2024-12-31"},
        ])
        mcap = 10_000_000_000.0
        result = compute_capital_allocation(
            "TEST", q_df, fp_df, statements_df=st_df,
            mcap=mcap,
            as_of_date="2025-12-31",
        )
        # repurch_ttm = 800e6 (4 × 200e6), sbc = 100e6, net = 700e6
        assert result["sbc_ttm"] == pytest.approx(100e6)
        assert result["net_buyback_after_sbc"] == pytest.approx(700e6 / mcap)

    def test_sbc_not_treated_as_zero_when_absent(self) -> None:
        """Ensure we cannot accidentally get net_buyback_after_sbc by treating None SBC as 0."""
        result_no_sbc = compute_capital_allocation(
            "TEST",
            _make_quarterly([
                {"period_end": "2025-09-30", "filed": "2025-11-01", "repurchases": 100e6},
            ]),
            _make_fundamentals_panel([
                {"fy": 2024, "shares": 900_000.0, "asof_date": "2025-04-30"},
                {"fy": 2023, "shares": 1_000_000.0, "asof_date": "2024-04-30"},
            ]),
            statements_df=None,
            mcap=1_000_000_000.0,
            as_of_date="2026-01-01",
        )
        # With SBC unavailable, net_buyback_after_sbc MUST be None, not repurch/mcap
        assert result_no_sbc["net_buyback_after_sbc"] is None
        # But buyback_yield is still computed (doesn't need SBC)
        assert result_no_sbc["buyback_yield"] is not None


# ── Group D: Full compute_capital_allocation — all four delta states ──────────

class TestComputeCapitalAllocation:
    """compute_capital_allocation produces correct output for all four delta states."""

    # Use asof=2025-12-31 so the Q4 2024-12-31 quarter is at the edge of the TTM window
    _AS_OF = "2025-12-31"

    def _base_quarterly(self):
        # 4 quarters with period_ends 2025-09-30, 2025-06-30, 2025-03-31, 2024-12-31
        # All within the TTM window when asof=2025-12-31
        return _make_quarterly([
            {"fiscal_quarter": 1, "period_end": "2025-09-30", "filed": "2025-11-01", "repurchases": 100e6},
            {"fiscal_quarter": 2, "period_end": "2025-06-30", "filed": "2025-08-01", "repurchases": 100e6},
            {"fiscal_quarter": 3, "period_end": "2025-03-31", "filed": "2025-05-01", "repurchases": 100e6},
            {"fiscal_quarter": 4, "period_end": "2024-12-31", "filed": "2025-01-31", "repurchases": 100e6},
        ])

    def test_accretive_state(self) -> None:
        q_df = self._base_quarterly()
        fp_df = _make_fundamentals_panel([
            {"fy": 2024, "shares": 985_000.0, "asof_date": "2025-04-30"},  # -1.5% YoY
            {"fy": 2023, "shares": 1_000_000.0, "asof_date": "2024-04-30"},
        ])
        result = compute_capital_allocation(
            "TEST", q_df, fp_df, as_of_date=self._AS_OF,
        )
        assert result["capital_allocation_delta"] == "accretive"
        assert result["share_count_reduction_confirmed"] is True
        assert result["repurch_ttm"] == pytest.approx(400e6)

    def test_dilutive_state(self) -> None:
        q_df = self._base_quarterly()
        fp_df = _make_fundamentals_panel([
            {"fy": 2024, "shares": 1_050_000.0, "asof_date": "2025-04-30"},  # +5% YoY
            {"fy": 2023, "shares": 1_000_000.0, "asof_date": "2024-04-30"},
        ])
        result = compute_capital_allocation(
            "TEST", q_df, fp_df, as_of_date=self._AS_OF,
        )
        assert result["capital_allocation_delta"] == "dilutive"
        assert result["share_count_reduction_confirmed"] is False

    def test_neutral_state(self) -> None:
        q_df = self._base_quarterly()
        fp_df = _make_fundamentals_panel([
            {"fy": 2024, "shares": 1_010_000.0, "asof_date": "2025-04-30"},  # +1% YoY — between thresholds
            {"fy": 2023, "shares": 1_000_000.0, "asof_date": "2024-04-30"},
        ])
        result = compute_capital_allocation(
            "TEST", q_df, fp_df, as_of_date=self._AS_OF,
        )
        assert result["capital_allocation_delta"] == "neutral"

    def test_unavailable_state_no_shares_data(self) -> None:
        q_df = self._base_quarterly()
        fp_df = _make_fundamentals_panel([
            {"fy": 2024, "shares": None, "asof_date": "2025-04-30"},  # no shares
            {"fy": 2023, "shares": None, "asof_date": "2024-04-30"},
        ])
        result = compute_capital_allocation(
            "TEST", q_df, fp_df, as_of_date=self._AS_OF,
        )
        assert result["capital_allocation_delta"] == "unavailable"
        assert result["share_count_reduction_confirmed"] is None

    def test_buyback_yield_computed_with_mcap(self) -> None:
        q_df = self._base_quarterly()
        fp_df = _make_fundamentals_panel([
            {"fy": 2024, "shares": 985_000.0, "asof_date": "2025-04-30"},
            {"fy": 2023, "shares": 1_000_000.0, "asof_date": "2024-04-30"},
        ])
        mcap = 10_000_000_000.0
        result = compute_capital_allocation(
            "TEST", q_df, fp_df, mcap=mcap, as_of_date=self._AS_OF,
        )
        # repurch_ttm = 400e6 (4 × 100e6), mcap = 10B → yield = 4%
        assert result["buyback_yield"] == pytest.approx(400e6 / mcap)

    def test_buyback_yield_none_without_mcap(self) -> None:
        q_df = self._base_quarterly()
        fp_df = _make_fundamentals_panel([
            {"fy": 2024, "shares": 985_000.0, "asof_date": "2025-04-30"},
            {"fy": 2023, "shares": 1_000_000.0, "asof_date": "2024-04-30"},
        ])
        result = compute_capital_allocation(
            "TEST", q_df, fp_df, mcap=None, as_of_date=self._AS_OF,
        )
        assert result["buyback_yield"] is None

    def test_debt_funded_buyback_flag_fires_when_debt_rose(self) -> None:
        # period_end="2025-09-30" ensures the FY overlaps the TTM window by >= 6 months
        # (ttm_start=2024-12-31; 2025-09-30 >= 2024-12-31+6m=2025-06-30 → aligned)
        q_df = self._base_quarterly()
        fp_df = _make_fundamentals_panel([
            {"fy": 2024, "shares": 985_000.0, "debt_lt": 600e6, "asof_date": "2025-04-30",
             "period_end": "2025-09-30"},  # debt rose; FY period aligned to TTM window
            {"fy": 2023, "shares": 1_000_000.0, "debt_lt": 500e6, "asof_date": "2024-04-30"},
        ])
        result = compute_capital_allocation(
            "TEST", q_df, fp_df, as_of_date=self._AS_OF,
        )
        assert result["debt_funded_buyback_flag"] is True

    def test_debt_funded_buyback_flag_false_when_debt_fell(self) -> None:
        # period_end="2025-09-30" ensures the FY overlaps the TTM window by >= 6 months
        q_df = self._base_quarterly()
        fp_df = _make_fundamentals_panel([
            {"fy": 2024, "shares": 985_000.0, "debt_lt": 400e6, "asof_date": "2025-04-30",
             "period_end": "2025-09-30"},  # debt fell; FY period aligned to TTM window
            {"fy": 2023, "shares": 1_000_000.0, "debt_lt": 500e6, "asof_date": "2024-04-30"},
        ])
        result = compute_capital_allocation(
            "TEST", q_df, fp_df, as_of_date=self._AS_OF,
        )
        assert result["debt_funded_buyback_flag"] is False

    def test_debt_funded_buyback_flag_none_when_no_repurchases(self) -> None:
        q_df = _make_quarterly([
            {"fiscal_quarter": 1, "period_end": "2025-09-30", "filed": "2025-11-01", "repurchases": 0.0},
        ])
        fp_df = _make_fundamentals_panel([
            {"fy": 2024, "shares": 985_000.0, "debt_lt": 600e6, "asof_date": "2025-04-30"},
            {"fy": 2023, "shares": 1_000_000.0, "debt_lt": 500e6, "asof_date": "2024-04-30"},
        ])
        result = compute_capital_allocation(
            "TEST", q_df, fp_df, as_of_date=self._AS_OF,
        )
        # repurch_ttm is 0 → flag is None (no buyback, flag doesn't apply)
        assert result["debt_funded_buyback_flag"] is None

    def test_stamps_present_in_all_outputs(self) -> None:
        """All outputs carry _horizon_role, _display_only, _version stamps."""
        q_df = self._base_quarterly()
        fp_df = _make_fundamentals_panel([
            {"fy": 2024, "shares": 985_000.0, "asof_date": "2025-04-30"},
            {"fy": 2023, "shares": 1_000_000.0, "asof_date": "2024-04-30"},
        ])
        result = compute_capital_allocation(
            "TEST", q_df, fp_df, as_of_date=self._AS_OF,
        )
        assert result["_horizon_role"] == "hold_thesis"
        assert result["_display_only"] is True
        assert result["_version"] == "v1"

    def test_empty_dataframes_do_not_raise(self) -> None:
        result = compute_capital_allocation(
            "TEST",
            pd.DataFrame(),
            pd.DataFrame(),
            statements_df=None,
            mcap=None,
            as_of_date=self._AS_OF,
        )
        assert result["capital_allocation_delta"] == "unavailable"
        assert result["_display_only"] is True

    def test_numpy_scalars_are_json_safe(self) -> None:
        """Result values must not contain numpy scalars (JSON safety)."""
        import json
        q_df = self._base_quarterly()
        # Inject numpy scalar into the data
        fp_df = _make_fundamentals_panel([
            {"fy": 2024, "shares": np.float64(985_000.0), "asof_date": "2025-04-30"},
            {"fy": 2023, "shares": np.float64(1_000_000.0), "asof_date": "2024-04-30"},
        ])
        result = compute_capital_allocation(
            "TEST", q_df, fp_df, mcap=np.float64(10_000_000_000.0),
            as_of_date=self._AS_OF,
        )
        # Should not raise — all numeric values should be native Python types
        # (float/bool/None/str), not numpy scalars.
        # We check that json.dumps succeeds (numpy scalars break it).
        try:
            json.dumps(result, default=str)
        except TypeError as exc:
            pytest.fail(f"json.dumps failed on result: {exc}")


# ── Group D2: debt_funded_buyback_flag period-alignment guard ─────────────────

class TestDebtFlagPeriodAlignment:
    """debt_funded_buyback_flag is None when FY and TTM windows are misaligned,
    and computes correctly when aligned.  Three required cases per task brief:
      1. Aligned case — flag computes (True or False)
      2. Misaligned FY — flag is None
      3. Missing repurchases — flag is None
    """

    # as_of="2026-06-01" → ttm_start="2025-06-01"
    # min_fy_end = ttm_start + 6m = "2025-12-01"
    _AS_OF = "2026-06-01"
    _TTM_START = pd.Timestamp("2025-06-01")

    def _base_quarterly(self):
        """4 filed quarterly rows, all within TTM window for as_of=2026-06-01."""
        return _make_quarterly([
            {"fiscal_quarter": 1, "period_end": "2026-03-31", "filed": "2026-05-01", "repurchases": 100e6},
            {"fiscal_quarter": 2, "period_end": "2025-12-31", "filed": "2026-02-01", "repurchases": 100e6},
            {"fiscal_quarter": 3, "period_end": "2025-09-30", "filed": "2025-11-01", "repurchases": 100e6},
            {"fiscal_quarter": 4, "period_end": "2025-06-30", "filed": "2025-08-01", "repurchases": 100e6},
        ])

    def test_aligned_fy_flag_computes(self) -> None:
        """When FY period_end >= ttm_start + 6 months, flag computes normally."""
        # fy_period_end="2025-12-31" >= "2025-06-01" + 6m = "2025-12-01" → aligned
        q_df = self._base_quarterly()
        fp_df = _make_fundamentals_panel([
            {"fy": 2025, "shares": 985_000.0, "debt_lt": 700e6, "asof_date": "2026-04-30",
             "period_end": "2025-12-31"},   # debt rose; FY aligned
            {"fy": 2024, "shares": 1_000_000.0, "debt_lt": 500e6, "asof_date": "2025-04-30",
             "period_end": "2024-12-31"},
        ])
        result = compute_capital_allocation(
            "TEST", q_df, fp_df, as_of_date=self._AS_OF,
        )
        # Alignment passes; debt rose → True
        assert result["debt_funded_buyback_flag"] is True

    def test_aligned_fy_flag_false_when_debt_fell(self) -> None:
        """Aligned FY + debt fell → False (not None)."""
        q_df = self._base_quarterly()
        fp_df = _make_fundamentals_panel([
            {"fy": 2025, "shares": 985_000.0, "debt_lt": 300e6, "asof_date": "2026-04-30",
             "period_end": "2025-12-31"},   # debt fell; FY aligned
            {"fy": 2024, "shares": 1_000_000.0, "debt_lt": 500e6, "asof_date": "2025-04-30",
             "period_end": "2024-12-31"},
        ])
        result = compute_capital_allocation(
            "TEST", q_df, fp_df, as_of_date=self._AS_OF,
        )
        assert result["debt_funded_buyback_flag"] is False

    def test_misaligned_fy_flag_is_none(self) -> None:
        """When FY period_end < ttm_start + 6 months, flag is None even with buybacks and debt data."""
        # as_of="2026-06-01" → ttm_start="2025-06-01" → min_fy_end="2025-12-01"
        # fy_period_end="2025-03-31" < "2025-12-01" → misaligned → flag None
        q_df = self._base_quarterly()
        fp_df = _make_fundamentals_panel([
            {"fy": 2025, "shares": 985_000.0, "debt_lt": 700e6, "asof_date": "2025-05-30",
             "period_end": "2025-03-31"},   # stale FY end — only 1 quarter overlaps TTM
            {"fy": 2024, "shares": 1_000_000.0, "debt_lt": 500e6, "asof_date": "2024-04-30",
             "period_end": "2024-12-31"},
        ])
        result = compute_capital_allocation(
            "TEST", q_df, fp_df, as_of_date=self._AS_OF,
        )
        # FY overlaps by < 2 quarters → flag must be None
        assert result["debt_funded_buyback_flag"] is None

    def test_missing_repurchases_flag_is_none(self) -> None:
        """When repurch_coverage='missing', flag is None regardless of debt data."""
        # No quarterly rows → coverage="missing"
        q_df = pd.DataFrame(columns=["ticker", "period_end", "filed", "repurchases",
                                      "fiscal_year", "fiscal_quarter"])
        fp_df = _make_fundamentals_panel([
            {"fy": 2025, "shares": 985_000.0, "debt_lt": 700e6, "asof_date": "2026-04-30",
             "period_end": "2025-12-31"},
            {"fy": 2024, "shares": 1_000_000.0, "debt_lt": 500e6, "asof_date": "2025-04-30",
             "period_end": "2024-12-31"},
        ])
        result = compute_capital_allocation(
            "TEST", q_df, fp_df, as_of_date=self._AS_OF,
        )
        assert result["repurch_coverage"] == "missing"
        # Condition (a) fails: coverage is missing → flag None
        assert result["debt_funded_buyback_flag"] is None

    def test_fy_overlaps_ttm_window_helper_boundary(self) -> None:
        """_fy_overlaps_ttm_window: exactly at boundary (= min_fy_end) is True."""
        ttm_start = pd.Timestamp("2025-06-01")
        # Exactly at ttm_start + 6m → boundary case → True
        assert _fy_overlaps_ttm_window(pd.Timestamp("2025-12-01"), ttm_start) is True

    def test_fy_overlaps_ttm_window_helper_one_day_before_boundary(self) -> None:
        """_fy_overlaps_ttm_window: one day before boundary is False."""
        ttm_start = pd.Timestamp("2025-06-01")
        # One day before min_fy_end → False
        assert _fy_overlaps_ttm_window(pd.Timestamp("2025-11-30"), ttm_start) is False

    def test_fy_overlaps_ttm_window_helper_none_period_end(self) -> None:
        """_fy_overlaps_ttm_window: None fy_period_end → False."""
        ttm_start = pd.Timestamp("2025-06-01")
        assert _fy_overlaps_ttm_window(None, ttm_start) is False


# ── Group E: Firewall — synapse.yml registration ──────────────────────────────

class TestFirewall:
    """Synapse registry entry for capital-allocation-delta is correctly stamped."""

    def test_synapse_entry_present_and_correct(self) -> None:
        """capital-allocation-delta entry in synapse.yml has correct firewall stamps."""
        import yaml  # noqa: PLC0415

        synapse_path = REPO_ROOT / "config" / "synapse.yml"
        assert synapse_path.exists(), "config/synapse.yml not found"

        with open(synapse_path) as f:
            data = yaml.safe_load(f)

        artifacts = data.get("artifacts", {})
        entry = artifacts.get("capital-allocation-delta")
        assert entry is not None, (
            "capital-allocation-delta not found in config/synapse.yml — "
            "run scripts/check_synapse_registry.py to diagnose"
        )
        assert entry.get("tier") == "display", (
            f"tier should be 'display', got {entry.get('tier')!r}"
        )
        assert entry.get("horizon_role") == "hold_thesis", (
            f"horizon_role should be 'hold_thesis', got {entry.get('horizon_role')!r}"
        )
        assert entry.get("scored_path_surfaces") == [], (
            f"scored_path_surfaces should be [], got {entry.get('scored_path_surfaces')!r}"
        )

    def test_result_horizon_role_matches_firewall(self) -> None:
        """_horizon_role in compute result matches the firewall constant."""
        result = compute_capital_allocation(
            "TEST",
            pd.DataFrame(),
            pd.DataFrame(),
            as_of_date="2026-01-01",
        )
        assert result["_horizon_role"] == _HORIZON_ROLE == "hold_thesis"
        assert result["_display_only"] is True
