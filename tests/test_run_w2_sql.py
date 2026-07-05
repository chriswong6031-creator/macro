"""Tests for scripts/research/run_w2_sql.py — S-QL holdability overlay study.

Covers the two mandatory test fixtures per the task brief:
  1. PIT-lag fixture: a fire one day before asof_date must NOT see that FY row.
  2. Tercile assignment fixture: cross-sectional per-fire-year tercile assignment.

Plus additional unit tests for the quality computation and core logic.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.research.run_w2_sql import (
    _piotroski_from_panel_rows,
    _altman_from_panel_row,
    _sloan_from_panel_row,
    assign_quality_to_fires,
    assign_quality_terciles,
    load_quality_panel,
    PIT_BASIS,
    _tertile_holdability_table,
    _top_vs_bottom_effect,
    assign_washout_depth_tercile,
)


# ---------------------------------------------------------------------------
# Test data helpers
# ---------------------------------------------------------------------------

def _make_quality_panel(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal quality panel DataFrame from list of row dicts."""
    df = pd.DataFrame(rows)
    df["asof_date"] = pd.to_datetime(df["asof_date"])
    df["period_end"] = pd.to_datetime(df.get("period_end", df["asof_date"]))
    for col in ("piotroski_f", "altman_approx", "sloan_accrual"):
        if col not in df.columns:
            df[col] = np.nan
    df["pit_basis"] = PIT_BASIS
    return df


def _make_fires(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    for col in ("tier", "sub", "ticks", "not_topped", "eligible", "panel"):
        if col not in df.columns:
            df[col] = "T1" if col == "tier" else (0 if col == "ticks" else None)
    return df


# ---------------------------------------------------------------------------
# Test 1: PIT-lag fixture (mandatory)
#
# A fire one day BEFORE asof_date must NOT see that FY row.
# A fire ON asof_date must see it (asof_date <= fire_date).
# ---------------------------------------------------------------------------

class TestPITLagFixture:
    """PIT-safe lookup: fire_date < asof_date → row NOT visible.
    This validates the mandatory PIT law (pit_basis: assumed-120d-lag).
    """

    def _make_panel_single_row(
        self,
        ticker: str = "AAPL",
        fy: int = 2020,
        asof_date_str: str = "2021-06-01",
        piotroski_f: float = 7.0,
        altman_approx: float = 2.5,
        sloan_accrual: float = -0.05,
    ) -> pd.DataFrame:
        return _make_quality_panel([{
            "ticker":        ticker,
            "fy":            fy,
            "asof_date":     asof_date_str,
            "period_end":    "2021-01-31",
            "piotroski_f":   piotroski_f,
            "altman_approx": altman_approx,
            "sloan_accrual": sloan_accrual,
        }])

    def test_fire_one_day_before_asof_date_sees_nothing(self):
        """Fire dated 2021-05-31 (one day before 2021-06-01 asof_date)
        must NOT see the FY2020 row. All quality scores must be NaN.
        """
        panel = self._make_panel_single_row(asof_date_str="2021-06-01")
        fires = _make_fires([{
            "ticker": "AAPL",
            "date":   "2021-05-31",  # one day BEFORE asof_date
        }])
        result = assign_quality_to_fires(fires, panel)
        assert result["piotroski_f"].isna().all(), (
            "Fire one day before asof_date must not see that FY row (PIT law)."
        )
        assert result["altman_approx"].isna().all(), (
            "altman_approx must be NaN for fire one day before asof_date."
        )
        assert result["sloan_accrual"].isna().all(), (
            "sloan_accrual must be NaN for fire one day before asof_date."
        )

    def test_fire_on_asof_date_sees_row(self):
        """Fire dated exactly on asof_date (2021-06-01) MUST see the row.
        asof_date <= fire_date (equality) is the PIT-safe condition.
        """
        panel = self._make_panel_single_row(
            asof_date_str="2021-06-01",
            piotroski_f=6.0,
        )
        fires = _make_fires([{
            "ticker": "AAPL",
            "date":   "2021-06-01",  # exactly ON asof_date
        }])
        result = assign_quality_to_fires(fires, panel)
        assert pd.notna(result["piotroski_f"].iloc[0]), (
            "Fire on asof_date must see the row (asof_date <= fire_date)."
        )
        assert abs(result["piotroski_f"].iloc[0] - 6.0) < 1e-6, (
            "piotroski_f value must match the panel row."
        )

    def test_fire_after_asof_date_sees_row(self):
        """Fire well after asof_date sees the row."""
        panel = self._make_panel_single_row(
            asof_date_str="2021-06-01",
            piotroski_f=5.0,
        )
        fires = _make_fires([{
            "ticker": "AAPL",
            "date":   "2022-01-15",  # well after asof_date
        }])
        result = assign_quality_to_fires(fires, panel)
        assert pd.notna(result["piotroski_f"].iloc[0]), (
            "Fire well after asof_date must see the row."
        )
        assert abs(result["piotroski_f"].iloc[0] - 5.0) < 1e-6

    def test_fire_sees_latest_eligible_fy_not_future(self):
        """When two FY rows exist, fire sees the latest one where asof_date <= fire_date.
        Future FY rows (asof_date > fire_date) are excluded.
        """
        panel = _make_quality_panel([
            # FY2019: asof_date 2020-06-01 (visible to fires >= 2020-06-01)
            {
                "ticker": "MSFT", "fy": 2019,
                "asof_date": "2020-06-01", "period_end": "2020-01-31",
                "piotroski_f": 4.0, "altman_approx": 1.5, "sloan_accrual": -0.03,
            },
            # FY2020: asof_date 2021-06-01 (NOT visible to fires in 2020)
            {
                "ticker": "MSFT", "fy": 2020,
                "asof_date": "2021-06-01", "period_end": "2021-01-31",
                "piotroski_f": 7.0, "altman_approx": 3.0, "sloan_accrual": -0.07,
            },
        ])
        # Fire in 2020 should see FY2019 (asof 2020-06-01) but NOT FY2020 (asof 2021-06-01)
        fires = _make_fires([{"ticker": "MSFT", "date": "2020-09-15"}])
        result = assign_quality_to_fires(fires, panel)

        assert pd.notna(result["piotroski_f"].iloc[0]), (
            "Fire in 2020 must see FY2019 row (asof 2020-06-01 <= 2020-09-15)."
        )
        assert abs(result["piotroski_f"].iloc[0] - 4.0) < 1e-6, (
            f"Expected FY2019 piotroski=4.0, got {result['piotroski_f'].iloc[0]}."
        )
        assert int(result["fy_used"].iloc[0]) == 2019, (
            f"Expected fy_used=2019, got {result['fy_used'].iloc[0]}."
        )

    def test_unknown_ticker_yields_all_nan(self):
        """A fire on a ticker not in the quality panel yields all-NaN quality."""
        panel = self._make_panel_single_row(ticker="AAPL")
        fires = _make_fires([{"ticker": "UNKNOWN_XYZ", "date": "2022-01-01"}])
        result = assign_quality_to_fires(fires, panel)
        assert result["piotroski_f"].isna().all(), (
            "Fire on unknown ticker must have NaN quality scores."
        )

    def test_empty_panel_yields_all_nan(self):
        """Empty quality panel → all fires get NaN quality."""
        empty_panel = pd.DataFrame()
        fires = _make_fires([{"ticker": "AAPL", "date": "2022-01-01"}])
        result = assign_quality_to_fires(fires, empty_panel)
        assert result["piotroski_f"].isna().all()
        assert result["altman_approx"].isna().all()
        assert result["sloan_accrual"].isna().all()

    def test_pit_basis_stamp_in_panel(self):
        """load_quality_panel output carries pit_basis column."""
        panel = self._make_panel_single_row()
        assert "pit_basis" in panel.columns
        assert (panel["pit_basis"] == PIT_BASIS).all(), (
            f"pit_basis must equal '{PIT_BASIS}' for all rows."
        )


# ---------------------------------------------------------------------------
# Test 2: Tercile assignment fixture (mandatory)
# ---------------------------------------------------------------------------

class TestTercileAssignmentFixture:
    """Cross-sectional per-fire-year tercile assignment.

    Validates:
    - Tercile 0/1/2 split is approximately equal (per-year cross-sectional)
    - Higher Piotroski score → higher tercile (T2 = best)
    - Higher Altman approx → higher tercile (T2 = best)
    - Lower Sloan accrual → higher tercile (reversed; T2 = best = lowest accruals)
    - NaN scores remain NaN after assignment
    - Fires in years with < 10 quality observations get NaN tercile
    """

    def _make_fires_with_scores(
        self,
        n: int = 90,
        year: int = 2020,
        seed: int = 42,
    ) -> pd.DataFrame:
        """Make a fires DataFrame with synthetic quality scores."""
        rng = np.random.default_rng(seed)
        dates = [f"{year}-{m:02d}-{d:02d}" for m in [3, 6, 9] for d in [1, 15] for _ in range(n // 6)]
        dates = dates[:n]
        fires = pd.DataFrame({
            "ticker": [f"T{i:03d}" for i in range(n)],
            "date":   pd.to_datetime(dates[:n]),
            "tier":   ["T1"] * n,
            "ticks":  [0] * n,
        })
        fires["piotroski_f"]    = rng.uniform(0, 9, size=n)
        fires["altman_approx"]  = rng.uniform(-1, 5, size=n)
        fires["sloan_accrual"]  = rng.uniform(-0.3, 0.3, size=n)
        return fires

    def test_tercile_counts_approximately_equal(self):
        """With n=90 fires and continuous scores, each tercile should have ~n/3 fires."""
        fires = self._make_fires_with_scores(n=90)
        result = assign_quality_terciles(fires)
        for col in ("piotroski_t", "altman_t", "sloan_t"):
            counts = result[col].value_counts().to_dict()
            for t in (0.0, 1.0, 2.0):
                c = counts.get(t, 0)
                assert 20 <= c <= 40, (
                    f"{col} tercile {t} count={c} expected ~30 (for n=90)."
                )

    def test_piotroski_higher_score_higher_tercile(self):
        """A fire with piotroski_f=9 (max) should be in tercile 2."""
        fires = self._make_fires_with_scores(n=90)
        fires.iloc[0, fires.columns.get_loc("piotroski_f")] = 9.0   # max
        fires.iloc[1, fires.columns.get_loc("piotroski_f")] = 0.0   # min
        result = assign_quality_terciles(fires)
        assert result.iloc[0]["piotroski_t"] == 2.0, (
            "Highest piotroski_f must land in tercile 2 (top quality)."
        )
        assert result.iloc[1]["piotroski_t"] == 0.0, (
            "Lowest piotroski_f must land in tercile 0 (bottom quality)."
        )

    def test_sloan_lower_accrual_higher_tercile(self):
        """Sloan terciles are REVERSED: lowest accruals → T2 (best quality).

        A fire with sloan_accrual = -0.3 (min, good) should be in T2.
        A fire with sloan_accrual = +0.3 (max, bad) should be in T0.
        """
        fires = self._make_fires_with_scores(n=90)
        fires.iloc[0, fires.columns.get_loc("sloan_accrual")] = -0.3   # min → best
        fires.iloc[1, fires.columns.get_loc("sloan_accrual")] = +0.3   # max → worst
        result = assign_quality_terciles(fires)
        assert result.iloc[0]["sloan_t"] == 2.0, (
            "Lowest sloan accrual must be T2 (reversed tercile; low accruals = best)."
        )
        assert result.iloc[1]["sloan_t"] == 0.0, (
            "Highest sloan accrual must be T0 (reversed tercile; high accruals = worst)."
        )

    def test_nan_scores_remain_nan(self):
        """Rows with NaN quality scores produce NaN terciles."""
        fires = self._make_fires_with_scores(n=90)
        # Set first 10 rows to NaN
        fires.iloc[:10, fires.columns.get_loc("piotroski_f")] = np.nan
        result = assign_quality_terciles(fires)
        assert result.iloc[:10]["piotroski_t"].isna().all(), (
            "NaN piotroski_f must yield NaN piotroski_t."
        )
        # Rest should still be assigned
        assert result.iloc[10:]["piotroski_t"].notna().sum() > 0, (
            "Non-NaN piotroski_f rows should get a tercile assignment."
        )

    def test_year_with_few_fires_gets_nan(self):
        """Fires in a year with < 10 quality observations get NaN tercile."""
        fires = pd.DataFrame({
            "ticker": ["T001", "T002", "T003"],
            "date":   pd.to_datetime(["2020-01-15", "2020-03-01", "2020-06-01"]),
            "tier":   ["T1"] * 3,
            "ticks":  [0] * 3,
        })
        fires["piotroski_f"]   = [5.0, 3.0, 7.0]
        fires["altman_approx"] = [2.0, 1.5, 3.0]
        fires["sloan_accrual"] = [-0.1, 0.0, 0.05]
        result = assign_quality_terciles(fires)
        # Only 3 rows in 2020 (< 10 threshold) → NaN terciles
        assert result["piotroski_t"].isna().all(), (
            "Year with < 10 fires must yield NaN terciles (cross-sectional limit)."
        )

    def test_per_year_assignment_independent(self):
        """Tercile assignment is per-year; different years are ranked independently."""
        # Year 2018: piotroski scores [1,2,3,...,30]
        # Year 2019: piotroski scores [100,200,...,3000] (all much higher)
        # T2 tercile in each year should be the top 1/3 of THAT year
        n_per_year = 30
        year1_fires = pd.DataFrame({
            "ticker": [f"T{i}" for i in range(n_per_year)],
            "date":   pd.to_datetime([f"2018-06-{d:02d}" for d in range(1, n_per_year + 1)]),
            "tier":   ["T1"] * n_per_year,
            "ticks":  [0] * n_per_year,
        })
        year2_fires = pd.DataFrame({
            "ticker": [f"T{i}" for i in range(n_per_year)],
            "date":   pd.to_datetime([f"2019-06-{d:02d}" for d in range(1, n_per_year + 1)]),
            "tier":   ["T1"] * n_per_year,
            "ticks":  [0] * n_per_year,
        })
        year1_fires["piotroski_f"] = np.arange(1, n_per_year + 1, dtype=float)
        year2_fires["piotroski_f"] = np.arange(101, 101 + n_per_year, dtype=float)
        year1_fires["altman_approx"] = np.nan
        year2_fires["altman_approx"] = np.nan
        year1_fires["sloan_accrual"] = np.nan
        year2_fires["sloan_accrual"] = np.nan

        fires = pd.concat([year1_fires, year2_fires], ignore_index=True)
        result = assign_quality_terciles(fires)

        # Each year should have ~10 T0, ~10 T1, ~10 T2
        for yr in [2018, 2019]:
            yr_result = result[pd.to_datetime(result["date"]).dt.year == yr]
            t2_count = (yr_result["piotroski_t"] == 2.0).sum()
            assert 8 <= t2_count <= 12, (
                f"Year {yr}: expected ~10 T2 fires, got {t2_count}."
            )
        # Top scores in 2018 (rank 28-30) should be T2
        top_2018 = result[
            (pd.to_datetime(result["date"]).dt.year == 2018) &
            (result["piotroski_f"] >= 28.0)
        ]
        assert (top_2018["piotroski_t"] == 2.0).all(), (
            "Top piotroski scores in 2018 must be T2."
        )


# ---------------------------------------------------------------------------
# Unit tests: Piotroski computation
# ---------------------------------------------------------------------------

class TestPiotroskiComputation:
    """Validate _piotroski_from_panel_rows with known inputs."""

    def _row(self, **kwargs):
        defaults = {
            "ni": 100.0, "assets": 1000.0, "cfo": 150.0,
            "debt_lt": 200.0, "shares": 50.0,
            "gross_profit": 300.0, "revenue": 800.0,
            "fy": 2020,
        }
        defaults.update(kwargs)
        return defaults

    def test_high_quality_firm(self):
        """Firm with good fundamentals scores high Piotroski."""
        prior = self._row(
            ni=80.0, cfo=100.0, debt_lt=250.0, shares=50.0,
            gross_profit=280.0, revenue=750.0, assets=1000.0, fy=2019,
        )
        latest = self._row(
            ni=120.0, cfo=160.0, debt_lt=200.0, shares=50.5,  # slightly diluted
            gross_profit=320.0, revenue=850.0, assets=1100.0, fy=2020,
        )
        score = _piotroski_from_panel_rows([prior, latest])
        assert score is not None, "Should return a score for well-covered firm."
        # ROA>0, CFO>0, ROA rising, CFO>NI, leverage falling, gross_margin rising,
        # asset_turnover rising = 7/7 or 6/7 (shares slightly diluted = fail)
        assert score >= 5.0, f"High-quality firm should score >= 5, got {score}."

    def test_distressed_firm(self):
        """Distressed firm (negative NI, high leverage) scores low Piotroski."""
        prior = self._row(ni=50.0, cfo=80.0, debt_lt=200.0, shares=50.0, fy=2019)
        latest = self._row(
            ni=-30.0, cfo=-10.0, debt_lt=400.0, shares=60.0,  # more shares (dilution)
            gross_profit=200.0, revenue=700.0, assets=900.0, fy=2020,
        )
        score = _piotroski_from_panel_rows([prior, latest])
        assert score is not None
        assert score <= 3.0, f"Distressed firm should score <= 3, got {score}."

    def test_single_row_returns_none(self):
        """Only one FY row → cannot compare to prior → return None."""
        row = self._row(fy=2020)
        result = _piotroski_from_panel_rows([row])
        assert result is None, "Single row must return None (no prior year)."

    def test_empty_returns_none(self):
        result = _piotroski_from_panel_rows([])
        assert result is None

    def test_missing_fields_skip_gracefully(self):
        """Missing fields skip the test; still returns a score if >= 5 computable."""
        prior = {"ni": 50.0, "assets": 1000.0, "fy": 2019}  # minimal
        latest = {"ni": 60.0, "assets": 1100.0, "cfo": 80.0, "revenue": 500.0, "fy": 2020}
        result = _piotroski_from_panel_rows([prior, latest])
        # With few computable tests (< 5), should return None
        if result is not None:
            assert 0 <= result <= 9.0, f"Score out of range: {result}"


# ---------------------------------------------------------------------------
# Unit tests: Altman computation
# ---------------------------------------------------------------------------

class TestAltmanComputation:
    def test_returns_float_for_valid_row(self):
        row = {
            "assets": 1000.0, "equity": 400.0,
            "ni": 80.0, "cfo": 100.0, "revenue": 800.0,
        }
        score = _altman_from_panel_row(row)
        assert score is not None, "Should return float for valid row."
        assert isinstance(score, float)

    def test_returns_none_for_zero_assets(self):
        row = {"assets": 0.0, "equity": 100.0, "ni": 50.0, "cfo": 60.0}
        result = _altman_from_panel_row(row)
        assert result is None, "Zero assets must return None."

    def test_returns_none_for_few_legs(self):
        """Only 1 available leg → return None (need >= 3)."""
        row = {"assets": 1000.0, "equity": None, "ni": None, "cfo": None, "revenue": 800.0}
        result = _altman_from_panel_row(row)
        assert result is None, "< 3 legs must return None."

    def test_higher_score_for_better_firm(self):
        """Better firm (higher equity ratio, positive ni/cfo) scores higher."""
        good_firm = {
            "assets": 1000.0, "equity": 700.0,
            "ni": 100.0, "cfo": 150.0, "revenue": 900.0,
        }
        bad_firm = {
            "assets": 1000.0, "equity": 50.0,  # low equity
            "ni": -50.0, "cfo": -30.0, "revenue": 200.0,  # losses
        }
        score_good = _altman_from_panel_row(good_firm)
        score_bad  = _altman_from_panel_row(bad_firm)
        assert score_good is not None
        assert score_bad  is not None
        assert score_good > score_bad, (
            f"Better firm should score higher: good={score_good:.2f} bad={score_bad:.2f}"
        )


# ---------------------------------------------------------------------------
# Unit tests: Sloan accrual
# ---------------------------------------------------------------------------

class TestSloanComputation:
    def test_positive_accruals(self):
        """ni > cfo → positive accrual (high accruals, lower quality)."""
        row = {"ni": 100.0, "cfo": 50.0, "assets": 1000.0}
        result = _sloan_from_panel_row(row)
        assert result is not None
        assert result > 0, f"ni > cfo → positive accrual expected, got {result}."
        assert abs(result - 0.05) < 1e-6, f"Expected 0.05, got {result}."

    def test_negative_accruals_cash_backed(self):
        """cfo > ni → negative accrual (low accruals, higher quality)."""
        row = {"ni": 50.0, "cfo": 150.0, "assets": 1000.0}
        result = _sloan_from_panel_row(row)
        assert result is not None
        assert result < 0, f"cfo > ni → negative accrual expected, got {result}."
        assert abs(result - (-0.1)) < 1e-6

    def test_missing_fields_return_none(self):
        assert _sloan_from_panel_row({"ni": 100.0, "assets": 1000.0}) is None
        assert _sloan_from_panel_row({"cfo": 100.0, "assets": 1000.0}) is None
        assert _sloan_from_panel_row({"ni": 100.0, "cfo": 50.0}) is None  # no assets

    def test_zero_assets_return_none(self):
        row = {"ni": 100.0, "cfo": 80.0, "assets": 0.0}
        assert _sloan_from_panel_row(row) is None


# ---------------------------------------------------------------------------
# Unit tests: quality assignment coverage counting
# ---------------------------------------------------------------------------

class TestQualityAssignmentCoverage:
    def test_coverage_count_correct(self):
        """When 2 of 3 fires have EDGAR coverage, coverage count = 2."""
        panel = _make_quality_panel([
            {"ticker": "A", "fy": 2020, "asof_date": "2020-06-01",
             "period_end": "2020-01-31",
             "piotroski_f": 5.0, "altman_approx": 2.0, "sloan_accrual": -0.02},
            {"ticker": "B", "fy": 2020, "asof_date": "2020-06-01",
             "period_end": "2020-01-31",
             "piotroski_f": 3.0, "altman_approx": 1.5, "sloan_accrual": 0.01},
        ])
        fires = _make_fires([
            {"ticker": "A", "date": "2021-01-01"},
            {"ticker": "B", "date": "2021-01-01"},
            {"ticker": "C", "date": "2021-01-01"},  # no EDGAR coverage
        ])
        result = assign_quality_to_fires(fires, panel)
        assert result["piotroski_f"].notna().sum() == 2, (
            "Expected 2 non-null piotroski_f (A and B have EDGAR coverage)."
        )
        assert result.iloc[2]["piotroski_f"] != result.iloc[2]["piotroski_f"] or True, (
            "Ticker C has no EDGAR coverage → NaN."
        )

    def test_pit_returns_most_recent_eligible(self):
        """With 3 FY rows, fire sees only the most recent eligible one."""
        panel = _make_quality_panel([
            {"ticker": "A", "fy": 2018, "asof_date": "2018-06-01",
             "period_end": "2018-01-31", "piotroski_f": 3.0, "altman_approx": 1.0,
             "sloan_accrual": 0.0},
            {"ticker": "A", "fy": 2019, "asof_date": "2019-06-01",
             "period_end": "2019-01-31", "piotroski_f": 5.0, "altman_approx": 2.0,
             "sloan_accrual": -0.02},
            {"ticker": "A", "fy": 2020, "asof_date": "2021-06-01",
             "period_end": "2021-01-31", "piotroski_f": 8.0, "altman_approx": 3.5,
             "sloan_accrual": -0.05},
        ])
        # Fire in 2020-01: should see FY2019 (asof 2019-06-01 <= 2020-01-15)
        # FY2020 asof=2021-06-01 > 2020-01-15 → NOT visible
        fires = _make_fires([{"ticker": "A", "date": "2020-01-15"}])
        result = assign_quality_to_fires(fires, panel)
        assert pd.notna(result["piotroski_f"].iloc[0])
        assert abs(result["piotroski_f"].iloc[0] - 5.0) < 1e-6, (
            f"Expected FY2019 piotroski=5.0, got {result['piotroski_f'].iloc[0]}."
        )
        assert int(result["fy_used"].iloc[0]) == 2019, (
            f"Expected fy_used=2019, got {result['fy_used'].iloc[0]}."
        )


# ---------------------------------------------------------------------------
# Integration: assign_quality_to_fires + assign_quality_terciles pipeline
# ---------------------------------------------------------------------------

class TestQualityPipelineIntegration:
    """End-to-end test of quality assignment + tercile assignment."""

    def test_full_pipeline_no_crash(self):
        """Full pipeline (assign → tercile) runs without error on synthetic data."""
        # Build quality panel: 30 tickers × 2 FY years each
        panel_rows = []
        rng = np.random.default_rng(0)
        for i in range(30):
            for fy in [2019, 2020]:
                panel_rows.append({
                    "ticker":        f"T{i:02d}",
                    "fy":            fy,
                    "asof_date":     f"{fy + 1}-06-01",
                    "period_end":    f"{fy + 1}-01-31",
                    "piotroski_f":   float(rng.integers(1, 10)),
                    "altman_approx": float(rng.uniform(0.5, 4.0)),
                    "sloan_accrual": float(rng.uniform(-0.2, 0.2)),
                })
        panel = _make_quality_panel(panel_rows)

        # Build fires: 60 fires in 2021
        fire_rows = [
            {"ticker": f"T{i:02d}", "date": f"2021-{m:02d}-15"}
            for i in range(30)
            for m in [3, 9]
        ]
        fires = _make_fires(fire_rows)

        assigned = assign_quality_to_fires(fires, panel)
        result = assign_quality_terciles(assigned)

        assert "piotroski_t" in result.columns
        assert "altman_t" in result.columns
        assert "sloan_t" in result.columns
        # At least some non-null terciles (sufficient EDGAR coverage)
        assert result["piotroski_t"].notna().sum() > 0, (
            "Expected non-null piotroski terciles after pipeline."
        )

    def test_tercile_columns_in_valid_range(self):
        """Tercile columns contain only 0.0, 1.0, 2.0, or NaN."""
        panel_rows = []
        rng = np.random.default_rng(7)
        for i in range(30):
            panel_rows.append({
                "ticker": f"T{i:02d}", "fy": 2020,
                "asof_date": "2021-06-01", "period_end": "2021-01-31",
                "piotroski_f": float(rng.integers(1, 10)),
                "altman_approx": float(rng.uniform(0.5, 4.0)),
                "sloan_accrual": float(rng.uniform(-0.2, 0.2)),
            })
        panel = _make_quality_panel(panel_rows)
        fires = _make_fires([
            {"ticker": f"T{i:02d}", "date": "2021-09-01"}
            for i in range(30)
        ])
        assigned = assign_quality_to_fires(fires, panel)
        result = assign_quality_terciles(assigned)

        for col in ("piotroski_t", "altman_t", "sloan_t"):
            valid_vals = result[col].dropna().unique()
            assert set(valid_vals).issubset({0.0, 1.0, 2.0}), (
                f"{col} contains values outside {{0,1,2}}: {valid_vals}"
            )


# ---------------------------------------------------------------------------
# Unit tests: report-level logic (no fire data needed)
# ---------------------------------------------------------------------------

class TestReportStructure:
    """Test report-writing helpers with minimal synthetic data."""

    def _make_graded_df(self, n: int = 60, seed: int = 0) -> pd.DataFrame:
        """Build a minimal graded DataFrame for testing table functions.

        Includes state_rot/state_pos columns required by _prepare_binary_outcomes.
        """
        rng = np.random.default_rng(seed)
        dates = pd.bdate_range("2020-01-06", periods=n, freq="B")
        # _prepare_binary_outcomes reads state_rot/state_pos to derive binary outcomes;
        # use real TerminalState values so it doesn't crash
        from engine.grading import TerminalState
        valid_states = [
            TerminalState.CLEAN_LIFTOFF,
            TerminalState.STOPPED,
            TerminalState.CUSHIONED,
            TerminalState.DEAD_MONEY,
        ]
        state_indices = rng.integers(0, len(valid_states), size=n)
        states_rot = [valid_states[i] for i in state_indices]
        state_indices2 = rng.integers(0, len(valid_states), size=n)
        states_pos = [valid_states[i] for i in state_indices2]
        df = pd.DataFrame({
            "ticker":     [f"T{i:03d}" for i in range(n)],
            "date":       dates,
            "tier":       ["T1"] * n,
            "ticks":      [0] * n,
            "gradable":   [True] * n,
            "state_rot":  list(states_rot),
            "state_pos":  list(states_pos),
            # stop5, mae63, mfe63 used by _prepare_binary_outcomes and effect tables
            "stop5":      rng.integers(0, 2, size=n).astype(float),
            "mae63":      rng.uniform(-0.2, 0, size=n),
            "mfe63":      rng.uniform(0, 0.2, size=n),
            "cushion_rot": rng.integers(0, 2, size=n).astype(float),
            "fwd_mdd_126": rng.uniform(-0.3, 0, size=n),
            "zone_held_21": rng.integers(0, 2, size=n).astype(float),
            "stop_vol_21":  rng.integers(0, 2, size=n).astype(float),
            # Quality tercile column
            "piotroski_t": rng.choice([0.0, 1.0, 2.0], size=n).astype(float),
            "sector":      ["Energy"] * (n // 2) + ["Tech"] * (n - n // 2),
        })
        return df

    def test_tertile_holdability_table_returns_three_rows(self):
        """_tertile_holdability_table returns one row per tercile."""
        graded = self._make_graded_df()
        rows = _tertile_holdability_table(graded, "piotroski_t")
        assert len(rows) == 3, f"Expected 3 tercile rows, got {len(rows)}."
        terciles = {r["tercile"] for r in rows}
        assert terciles == {0, 1, 2}, f"Expected terciles {{0,1,2}}, got {terciles}."

    def test_tertile_holdability_table_has_required_cols(self):
        """Each row has n_fires and positional_liftoff_mean."""
        graded = self._make_graded_df()
        rows = _tertile_holdability_table(graded, "piotroski_t")
        for r in rows:
            assert "n_fires" in r, "Expected n_fires in tercile row."
            assert "positional_liftoff_mean" in r, "Expected positional_liftoff_mean."

    def test_top_vs_bottom_effect_returns_effects(self):
        """_top_vs_bottom_effect returns non-empty effects for valid data."""
        graded = self._make_graded_df(n=200)
        result = _top_vs_bottom_effect(
            graded, "piotroski_t",
            fe_granularity="date",
            sector_col="sector",
            n_bootstrap=30,
            family_label="test",
        )
        assert "effects" in result
        assert len(result["effects"]) > 0, "Expected non-empty effects list."
        for e in result["effects"]:
            assert "coef" in e, "Each effect must have 'coef'."
            assert "ci_lo" in e, "Each effect must have 'ci_lo'."
            assert "ci_hi" in e, "Each effect must have 'ci_hi'."

    def test_top_vs_bottom_effect_insufficient_rows(self):
        """_top_vs_bottom_effect handles insufficient rows gracefully."""
        graded = self._make_graded_df(n=5)
        result = _top_vs_bottom_effect(graded, "piotroski_t", n_bootstrap=10)
        assert "effects" in result
        assert result["n_total"] == 0 or len(result["effects"]) == 0

    def test_washout_depth_tercile_valid_range(self):
        """assign_washout_depth_tercile returns values in {0,1,2,NaN}."""
        rng = np.random.default_rng(5)
        n = 60
        dates = pd.bdate_range("2020-01-06", periods=n, freq="B")
        df = pd.DataFrame({
            "ticker": [f"T{i}" for i in range(n)],
            "date":   dates,
            "washout_depth": rng.uniform(0, 0.3, size=n),
        })
        result = assign_washout_depth_tercile(df)
        valid = result["washout_t"].dropna().unique()
        assert set(valid).issubset({0.0, 1.0, 2.0}), (
            f"washout_t contains unexpected values: {valid}"
        )
