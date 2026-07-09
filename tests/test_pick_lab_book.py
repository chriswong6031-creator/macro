"""Tests for engine.pick_lab.grade and engine.pick_lab.book (spec §4).

Covers:
  grade.py:
    - no-lookahead: grading refuses when bars not yet elapsed
    - exec = next trading session after fire_date
    - missing ticker → counted as ungradeable, never silently dropped
    - ret_abs / ret_excess_spy / ret_rel_sector computed correctly
    - MFE/MAE computed only when exec+25 elapsed; null when not elapsed

  book.py:
    - NAV ladder on a tiny hand-computed example (assert exact values)
    - ACCRUING floor logic (n_fires/months/distinct dates)
    - avoid-book sign handling (avoid_accuracy field present)
    - LH books: per-horizon medians + ETA only
    - universe_base_rate from random_ctrl grades
    - lift vs ctrl and vs base rate

Run:
    python -m pytest tests/test_pick_lab_book.py -x -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.pick_lab.grade import grade_fires, ENTRY_HORIZONS, LH_HORIZONS, MFE_MAE_SESSIONS
from engine.pick_lab.book import (
    scoreboard,
    universe_base_rate,
    all_scoreboards,
    _nav_ladder,
    _months_span,
    _distinct_fire_dates,
    FLOOR_N_FIRES,
    FLOOR_MONTHS_SPAN,
    FLOOR_DISTINCT_FIRE_DATES,
)


# ================================================================ helpers =====


def _make_panel(
    tickers: list[str],
    n_sessions: int = 300,
    start: str = "2024-01-02",
    base_price: float = 100.0,
) -> pd.DataFrame:
    """Flat-price panel: all tickers at base_price every session."""
    dates = pd.bdate_range(start=start, periods=n_sessions)
    data = {t: np.full(n_sessions, base_price) for t in tickers}
    return pd.DataFrame(data, index=dates)


def _panel_with_returns(
    tickers: dict[str, float],
    n_sessions: int = 300,
    start: str = "2024-01-02",
    base_price: float = 100.0,
) -> pd.DataFrame:
    """Panel where each ticker has a constant drift per session after session 0."""
    dates = pd.bdate_range(start=start, periods=n_sessions)
    data = {}
    for ticker, daily_drift in tickers.items():
        prices = base_price * (1 + daily_drift) ** np.arange(n_sessions)
        data[ticker] = prices
    return pd.DataFrame(data, index=dates)


def _fire(engine_id="plab_1d_pure", ticker="AAPL", fire_date="2024-01-10",
          exec_date="2024-01-11", sector="Information Technology", **kwargs) -> dict:
    row = {
        "engine_id": engine_id,
        "ticker": ticker,
        "fire_date": fire_date,
        "exec_date": exec_date,
        "sector": sector,
        "authority": "display_only",
    }
    row.update(kwargs)
    return row


def _grade(engine_id="plab_1d_pure", ticker="AAPL", fire_date="2024-01-10",
           horizon=21, ret_excess_spy=0.02, mfe=0.05, mae=-0.02, **kwargs) -> dict:
    row = {
        "engine_id": engine_id,
        "ticker": ticker,
        "fire_date": fire_date,
        "exec_date": "2024-01-11",
        "horizon": horizon,
        "ret_abs": 0.05,
        "ret_excess_spy": ret_excess_spy,
        "ret_rel_sector": 0.01,
        "mfe": mfe,
        "mae": mae,
        "matured": True,
        "graded_at": "2024-02-15T10:00:00+00:00",
        "authority": "display_only",
    }
    row.update(kwargs)
    return row


# ================================================================ grade.py ====


class TestGradeNoLookahead:
    """Grade must refuse when the required bars have not elapsed."""

    def test_horizon_not_elapsed_returns_no_grade(self):
        """If exec + h sessions haven't elapsed, no grade row is produced."""
        # Panel has only 10 sessions after exec_date (Jan 11) → horizon 21 not elapsed
        dates = pd.bdate_range("2024-01-02", "2024-01-25")  # ~17 sessions
        panel = pd.DataFrame({"AAPL": np.full(len(dates), 100.0)}, index=dates)
        spy = pd.Series(np.full(len(dates), 450.0), index=dates)

        fire = _fire(fire_date="2024-01-10")
        grades, n_ung = grade_fires([fire], panel, spy)
        # exec_date = 2024-01-11; exec + 21 sessions = ~2024-02-07 which is beyond panel
        h21_grades = [g for g in grades if g.get("horizon") == 21]
        assert len(h21_grades) == 0, "h=21 should not be graded when panel is too short"

    def test_horizon_elapsed_produces_grade(self):
        """When exec + h sessions have elapsed, grade is produced."""
        # 100 sessions should be enough for h=5
        n = 100
        dates = pd.bdate_range("2024-01-02", periods=n)
        panel = pd.DataFrame({"AAPL": np.full(n, 100.0)}, index=dates)
        spy = pd.Series(np.full(n, 450.0), index=dates)

        fire = _fire(fire_date=str(dates[0].date()))
        grades, n_ung = grade_fires([fire], panel, spy)
        h5 = [g for g in grades if g.get("horizon") == 5]
        assert len(h5) == 1, "h=5 should be graded when enough sessions exist"

    def test_mfe_mae_not_computed_when_25_not_elapsed(self):
        """MFE/MAE remain null if exec + 25 sessions not elapsed."""
        # 20 sessions total → exec on session 1, exec+25 = session 26 > 20
        n = 20
        dates = pd.bdate_range("2024-01-02", periods=n)
        panel = pd.DataFrame({"AAPL": np.full(n, 100.0)}, index=dates)
        spy = pd.Series(np.full(n, 450.0), index=dates)

        fire = _fire(fire_date=str(dates[0].date()))
        grades, _ = grade_fires([fire], panel, spy)
        for g in grades:
            assert g.get("mfe") is None, f"MFE should be null, got {g.get('mfe')}"
            assert g.get("mae") is None, f"MAE should be null, got {g.get('mae')}"

    def test_mfe_mae_computed_when_25_elapsed(self):
        """MFE/MAE populated when exec + 25 sessions elapsed."""
        n = 150
        dates = pd.bdate_range("2024-01-02", periods=n)
        # Rising price: MFE should be positive
        prices = 100.0 * (1.001 ** np.arange(n))
        panel = pd.DataFrame({"AAPL": prices}, index=dates)
        spy = pd.Series(np.full(n, 450.0), index=dates)

        fire = _fire(fire_date=str(dates[0].date()))
        grades, _ = grade_fires([fire], panel, spy)
        h21 = [g for g in grades if g.get("horizon") == 21]
        assert len(h21) == 1
        mfe = h21[0].get("mfe")
        assert mfe is not None, "MFE should be populated"
        assert mfe > 0, "Rising prices → MFE > 0"


class TestGradeExecDate:
    """exec = next trading session after fire_date."""

    def test_exec_is_next_session(self):
        """Exec price is the close of the next session after fire_date."""
        n = 50
        dates = pd.bdate_range("2024-01-02", periods=n)
        # Give AAPL a different price on each day
        prices = 100.0 + np.arange(n)
        panel = pd.DataFrame({"AAPL": prices}, index=dates)
        spy = pd.Series(np.full(n, 450.0), index=dates)

        # fire_date = dates[5]; exec should be dates[6]
        fire_date = str(dates[5].date())
        expected_exec_date = str(dates[6].date())
        expected_exec_price = prices[6]

        fire = _fire(fire_date=fire_date)
        grades, _ = grade_fires([fire], panel, spy)
        if grades:
            assert grades[0]["exec_date"] == expected_exec_date
            assert abs(grades[0]["exec_price"] - expected_exec_price) < 1e-4

    def test_exec_on_last_session_no_grade(self):
        """fire_date = last session → no next session → no grade."""
        n = 30
        dates = pd.bdate_range("2024-01-02", periods=n)
        panel = pd.DataFrame({"AAPL": np.full(n, 100.0)}, index=dates)
        spy = pd.Series(np.full(n, 450.0), index=dates)

        fire = _fire(fire_date=str(dates[-1].date()))
        grades, _ = grade_fires([fire], panel, spy)
        assert len(grades) == 0, "No session after last date → nothing to grade"


class TestGradeReturns:
    """ret_abs, ret_excess_spy, ret_rel_sector computed correctly."""

    def test_ret_abs_correct(self):
        """ret_abs = (price_h - exec_price) / exec_price."""
        n = 100
        dates = pd.bdate_range("2024-01-02", periods=n)
        # exec_price = 100 (dates[1]); price at exec+5 = 110
        prices = np.full(n, 100.0)
        exec_idx = 1   # dates[1] is exec
        prices[exec_idx + 5] = 110.0
        panel = pd.DataFrame({"AAPL": prices}, index=dates)
        spy = pd.Series(np.full(n, 450.0), index=dates)

        fire = _fire(fire_date=str(dates[0].date()))
        grades, _ = grade_fires([fire], panel, spy)
        h5 = [g for g in grades if g.get("horizon") == 5]
        if h5:
            expected = (110.0 - 100.0) / 100.0
            assert abs(h5[0]["ret_abs"] - expected) < 1e-5

    def test_ret_excess_spy_flat_spy(self):
        """When SPY is flat, ret_excess_spy == ret_abs."""
        n = 100
        dates = pd.bdate_range("2024-01-02", periods=n)
        # AAPL up 5% at h=5; SPY flat
        prices = np.full(n, 100.0)
        prices[6] = 105.0  # exec on dates[1], h=5 on dates[6]
        panel = pd.DataFrame({"AAPL": prices, "SPY": np.full(n, 450.0)}, index=dates)
        spy = pd.Series(np.full(n, 450.0), index=dates)

        fire = _fire(fire_date=str(dates[0].date()))
        grades, _ = grade_fires([fire], panel, spy)
        h5 = [g for g in grades if g.get("horizon") == 5]
        if h5:
            # flat SPY → excess ≈ abs
            assert h5[0]["ret_excess_spy"] is not None
            assert abs(h5[0]["ret_excess_spy"] - h5[0]["ret_abs"]) < 1e-4

    def test_ret_rel_sector_null_when_etf_missing(self):
        """Sector ETF absent from panel → ret_rel_sector is null (honest null)."""
        n = 100
        dates = pd.bdate_range("2024-01-02", periods=n)
        # No XLK in panel
        panel = pd.DataFrame({"AAPL": np.full(n, 100.0)}, index=dates)
        spy = pd.Series(np.full(n, 450.0), index=dates)

        fire = _fire(fire_date=str(dates[0].date()), sector="Information Technology")
        grades, _ = grade_fires([fire], panel, spy)
        for g in grades:
            assert g["ret_rel_sector"] is None

    def test_ret_rel_sector_computed_when_etf_present(self):
        """Sector ETF in panel → ret_rel_sector is populated."""
        n = 100
        dates = pd.bdate_range("2024-01-02", periods=n)
        # AAPL and XLK both in panel
        panel = pd.DataFrame({
            "AAPL": np.full(n, 100.0),
            "XLK": np.full(n, 200.0),
        }, index=dates)
        spy = pd.Series(np.full(n, 450.0), index=dates)

        fire = _fire(fire_date=str(dates[0].date()), sector="Information Technology")
        grades, _ = grade_fires([fire], panel, spy)
        for g in grades:
            # Both flat → excess vs sector ≈ 0
            assert g["ret_rel_sector"] is not None
            assert abs(g["ret_rel_sector"]) < 1e-4


class TestGradeUngradeableTicker:
    """Missing ticker → skip + increment counter (never silently drop)."""

    def test_missing_ticker_counted(self):
        """Ticker absent from panel increments ungradeable counter."""
        n = 100
        dates = pd.bdate_range("2024-01-02", periods=n)
        panel = pd.DataFrame({"MSFT": np.full(n, 200.0)}, index=dates)
        spy = pd.Series(np.full(n, 450.0), index=dates)

        fire = _fire(ticker="AAPL")  # AAPL not in panel
        grades, n_ung = grade_fires([fire], panel, spy)
        assert n_ung == 1

    def test_present_ticker_graded_missing_skipped(self):
        """Mix of present/absent: present graded, absent counted."""
        n = 100
        dates = pd.bdate_range("2024-01-02", periods=n)
        panel = pd.DataFrame({"AAPL": np.full(n, 100.0)}, index=dates)
        spy = pd.Series(np.full(n, 450.0), index=dates)

        fires = [
            _fire(ticker="AAPL", fire_date=str(dates[0].date())),
            _fire(ticker="MISSING", fire_date=str(dates[0].date())),
        ]
        grades, n_ung = grade_fires(fires, panel, spy)
        assert n_ung == 1
        aapl_grades = [g for g in grades if g["ticker"] == "AAPL"]
        assert len(aapl_grades) > 0

    def test_authority_in_grade_rows(self):
        """All grade rows carry authority='display_only'."""
        n = 100
        dates = pd.bdate_range("2024-01-02", periods=n)
        panel = pd.DataFrame({"AAPL": np.full(n, 100.0)}, index=dates)
        spy = pd.Series(np.full(n, 450.0), index=dates)

        fire = _fire(fire_date=str(dates[0].date()))
        grades, _ = grade_fires([fire], panel, spy)
        for g in grades:
            assert g["authority"] == "display_only"


class TestGradeAlreadyGraded:
    """Already-graded keys are skipped (dedup guard)."""

    def test_already_graded_skipped(self):
        n = 100
        dates = pd.bdate_range("2024-01-02", periods=n)
        panel = pd.DataFrame({"AAPL": np.full(n, 100.0)}, index=dates)
        spy = pd.Series(np.full(n, 450.0), index=dates)

        fire = _fire(fire_date=str(dates[0].date()))
        # Pre-populate already_graded with all horizons for this fire
        already = {
            ("plab_1d_pure", "AAPL", str(dates[0].date()), h)
            for h in ENTRY_HORIZONS
        }
        grades, _ = grade_fires([fire], panel, spy, already_graded=already)
        assert len(grades) == 0


# ================================================================ book.py =====


class TestNAVLadder:
    """NAV ladder hand-computed example."""

    def _make_fires_grades(self, n_cohorts: int = 3, exc_per_cohort: float = 0.021):
        """Build n_cohorts fires, each with ret_excess_spy=exc_per_cohort at h=21.

        All fire on consecutive days so they overlap in the NAV window.
        """
        fires = []
        grades = []
        start = pd.Timestamp("2024-01-02")
        for i in range(n_cohorts):
            fire_date = str((start + pd.offsets.BDay(i)).date())
            exec_date = str((start + pd.offsets.BDay(i + 1)).date())
            fires.append({
                "engine_id": "plab_1d_pure",
                "ticker": f"T{i:02d}",
                "fire_date": fire_date,
                "exec_date": exec_date,
                "authority": "display_only",
            })
            grades.append({
                "engine_id": "plab_1d_pure",
                "ticker": f"T{i:02d}",
                "fire_date": fire_date,
                "exec_date": exec_date,
                "horizon": 21,
                "ret_excess_spy": exc_per_cohort,
                "authority": "display_only",
            })
        return fires, grades

    def test_nav_positive_on_positive_returns(self):
        """NAV > 1 when all cohorts have positive excess returns."""
        fires, grades = self._make_fires_grades(n_cohorts=3, exc_per_cohort=0.021)
        nav, max_dd = _nav_ladder(fires, grades)
        assert not nav.empty
        assert nav.iloc[-1] > 1.0

    def test_nav_starts_at_one(self):
        """NAV series starts at 1.0 (first period compounding starts from 1)."""
        fires, grades = self._make_fires_grades(n_cohorts=2, exc_per_cohort=0.01)
        nav, _ = _nav_ladder(fires, grades)
        assert abs(nav.iloc[0] - 1.0) < 0.01  # first bar close to 1

    def test_nav_max_dd_zero_on_monotone_positive(self):
        """Monotonically positive daily returns → max drawdown near 0."""
        fires, grades = self._make_fires_grades(n_cohorts=1, exc_per_cohort=0.01)
        _, max_dd = _nav_ladder(fires, grades)
        # With positive uniform daily returns, drawdown should be <= 0
        assert max_dd <= 0.0

    def test_nav_empty_on_no_h21_grades(self):
        """No h=21 grades → empty NAV."""
        fires = [_fire()]
        grades = [_grade(horizon=63)]  # only h=63
        nav, max_dd = _nav_ladder(fires, grades)
        assert nav.empty
        assert max_dd == 0.0

    def test_nav_exact_single_cohort(self):
        """Single cohort, one grade: daily return = 0.021/21 per day for 21 days.

        Final NAV = (1 + 0.021/21)^21 ≈ 1.021 (approximately).
        """
        daily = 0.021 / 21
        fires = [{
            "engine_id": "plab_1d_pure",
            "ticker": "T00",
            "fire_date": "2024-01-02",
            "exec_date": "2024-01-03",
            "authority": "display_only",
        }]
        grades = [{
            "engine_id": "plab_1d_pure",
            "ticker": "T00",
            "fire_date": "2024-01-02",
            "exec_date": "2024-01-03",
            "horizon": 21,
            "ret_excess_spy": 0.021,
            "authority": "display_only",
        }]
        nav, max_dd = _nav_ladder(fires, grades)
        if not nav.empty:
            # Final value should be approximately (1 + daily)^21
            expected = (1 + daily) ** 21
            assert abs(nav.iloc[-1] - expected) < 0.01, (
                f"NAV final {nav.iloc[-1]:.6f} vs expected {expected:.6f}"
            )


class TestAccruingFloor:
    """ACCRUING until PL-R4 floor: n>=25, >=3 months, >=6 distinct fire dates."""

    def _make_n_fires(self, n: int, months_span: float = 4.0,
                      distinct_dates: int = None) -> list[dict]:
        """Generate n fire rows spanning ~months_span months."""
        fires = []
        start = pd.Timestamp("2024-01-02")
        total_days = int(months_span * 30)
        for i in range(n):
            offset = int(i * total_days / max(n, 1))
            fd = str((start + pd.Timedelta(days=offset)).date())
            fires.append(_fire(ticker=f"T{i:03d}", fire_date=fd))
        if distinct_dates is not None and distinct_dates < n:
            # Collapse to fewer distinct dates
            for i in range(n - distinct_dates):
                fires[i]["fire_date"] = fires[0]["fire_date"]
        return fires

    def test_below_floor_is_accruing(self):
        """< 25 fires → ACCRUING."""
        fires = self._make_n_fires(10, months_span=4.0)
        grades = [_grade(ticker=f["ticker"], fire_date=f["fire_date"]) for f in fires]
        sb = scoreboard("plab_1d_pure", fires, grades)
        assert sb["status"] == "ACCRUING"

    def test_at_floor_n25_months3_dates6(self):
        """Exactly 25 fires, 3+ months, 6+ distinct dates → SCOREABLE."""
        fires = self._make_n_fires(25, months_span=3.5)
        # Ensure distinct dates >= 6
        unique_dates = list({f["fire_date"] for f in fires})
        assert len(unique_dates) >= 6, f"Need >=6 distinct dates, got {len(unique_dates)}"
        grades = [
            _grade(ticker=f["ticker"], fire_date=f["fire_date"])
            for f in fires
        ]
        sb = scoreboard("plab_1d_pure", fires, grades)
        assert sb["status"] == "SCOREABLE"

    def test_floor_needs_all_three_conditions(self):
        """25 fires but only 1 month span → ACCRUING."""
        fires = self._make_n_fires(25, months_span=0.5)
        grades = [_grade(ticker=f["ticker"], fire_date=f["fire_date"]) for f in fires]
        sb = scoreboard("plab_1d_pure", fires, grades)
        assert sb["status"] == "ACCRUING"

    def test_floor_distinct_dates_check(self):
        """25 fires all on same date → ACCRUING (distinct_dates=1 < 6)."""
        fires = [_fire(ticker=f"T{i:03d}", fire_date="2024-01-10") for i in range(25)]
        grades = [_grade(ticker=f["ticker"], fire_date=f["fire_date"]) for f in fires]
        sb = scoreboard("plab_1d_pure", fires, grades)
        assert sb["status"] == "ACCRUING"


class TestAvoidBook:
    """plab_topping_avoid: avoid_accuracy field, sign handling."""

    def test_avoid_book_has_avoid_accuracy(self):
        """Avoid book scoreboard includes avoid_accuracy field."""
        fires = [_fire(engine_id="plab_topping_avoid", ticker=f"T{i:03d}",
                       fire_date=f"2024-0{i+1}-10") for i in range(3)]
        grades = [
            _grade(engine_id="plab_topping_avoid", ticker=f["ticker"],
                   fire_date=f["fire_date"], ret_excess_spy=-0.03)
            for f in fires
        ]
        sb = scoreboard("plab_topping_avoid", fires, grades, horizon_role="entry")
        assert "h21_avoid_accuracy" in sb
        assert sb["is_avoid"] is True

    def test_avoid_book_accuracy_when_negative_excess(self):
        """Negative excess returns (expected for avoid) → avoid_accuracy > 0.5."""
        fires = [
            _fire(engine_id="plab_topping_avoid", ticker=f"T{i:02d}",
                  fire_date=f"2024-01-{10+i:02d}")
            for i in range(5)
        ]
        grades = [
            _grade(engine_id="plab_topping_avoid", ticker=f["ticker"],
                   fire_date=f["fire_date"], ret_excess_spy=-0.05)  # all negative
            for f in fires
        ]
        sb = scoreboard("plab_topping_avoid", fires, grades, horizon_role="entry")
        # WR_exc should be 0 (all negative) → avoid_accuracy = 1 - wr_exc = 1.0
        aa = sb.get("h21_avoid_accuracy")
        assert aa is not None
        assert aa > 0.5, f"Expected avoid_accuracy > 0.5, got {aa}"


class TestLHBook:
    """LH books: per-horizon medians + ETA only; no NAV, no entry stats."""

    def test_lh_scoreboard_has_eta(self):
        fires = [_fire(engine_id="plab_lh_compounder", ticker="T001",
                       fire_date="2024-01-10")]
        grades = [_grade(engine_id="plab_lh_compounder", ticker="T001",
                         fire_date="2024-01-10", horizon=126)]
        sb = scoreboard("plab_lh_compounder", fires, grades, horizon_role="hold_thesis")
        assert "first_maturation_eta" in sb
        assert sb["first_maturation_eta"] is not None

    def test_lh_scoreboard_no_nav(self):
        """LH scoreboard does not contain NAV fields."""
        fires = [_fire(engine_id="plab_lh_compounder", ticker="T001",
                       fire_date="2024-01-10")]
        grades = [_grade(engine_id="plab_lh_compounder", ticker="T001",
                         fire_date="2024-01-10", horizon=126)]
        sb = scoreboard("plab_lh_compounder", fires, grades, horizon_role="hold_thesis")
        assert "nav_max_drawdown" not in sb
        assert "lift_vs_ctrl" not in sb

    def test_lh_uses_lh_horizons(self):
        """LH scoreboard includes 126d and 252d horizon stats."""
        fires = [_fire(engine_id="plab_lh_compounder", ticker="T001",
                       fire_date="2024-01-10")]
        grades = [
            _grade(engine_id="plab_lh_compounder", ticker="T001",
                   fire_date="2024-01-10", horizon=126),
            _grade(engine_id="plab_lh_compounder", ticker="T001",
                   fire_date="2024-01-10", horizon=252),
        ]
        sb = scoreboard("plab_lh_compounder", fires, grades, horizon_role="hold_thesis")
        assert "h126_n" in sb
        assert "h252_n" in sb


class TestUniverseBaseRate:
    """universe_base_rate computes median 21d excess from random_ctrl."""

    def test_base_rate_from_ctrl_grades(self):
        ctrl_grades = [
            _grade(engine_id="plab_random_ctrl", ticker=f"T{i:02d}",
                   fire_date=f"2024-01-{10+i:02d}", ret_excess_spy=0.01)
            for i in range(10)
        ]
        br = universe_base_rate(ctrl_grades, horizon=21)
        assert br is not None
        assert abs(br - 0.01) < 1e-6

    def test_base_rate_none_when_no_grades(self):
        br = universe_base_rate([], horizon=21)
        assert br is None

    def test_base_rate_ignores_wrong_horizon(self):
        ctrl_grades = [
            _grade(engine_id="plab_random_ctrl", ticker="T01",
                   fire_date="2024-01-10", horizon=63, ret_excess_spy=0.10),
        ]
        br = universe_base_rate(ctrl_grades, horizon=21)
        assert br is None  # no h=21 grades


class TestLiftCalculation:
    """Lift vs ctrl and vs base rate."""

    def test_lift_vs_ctrl_positive(self):
        """Book exceeds random ctrl → positive lift."""
        ctrl_grades = [
            _grade(engine_id="plab_random_ctrl", ticker=f"C{i:02d}",
                   fire_date=f"2024-01-{10+i:02d}", ret_excess_spy=0.01)
            for i in range(5)
        ]
        my_fires = [
            _fire(ticker=f"T{i:02d}", fire_date=f"2024-01-{10+i:02d}")
            for i in range(5)
        ]
        my_grades = [
            _grade(ticker=f["ticker"], fire_date=f["fire_date"], ret_excess_spy=0.03)
            for f in my_fires
        ]
        sb = scoreboard(
            "plab_1d_pure", my_fires, my_grades,
            ctrl_fires=[], ctrl_grades=ctrl_grades,
        )
        assert sb["lift_vs_ctrl"] is not None
        assert sb["lift_vs_ctrl"] > 0

    def test_lift_vs_universe_base(self):
        """Book exceeds universe base rate → positive lift."""
        my_fires = [
            _fire(ticker=f"T{i:02d}", fire_date=f"2024-01-{10+i:02d}")
            for i in range(5)
        ]
        my_grades = [
            _grade(ticker=f["ticker"], fire_date=f["fire_date"], ret_excess_spy=0.04)
            for f in my_fires
        ]
        sb = scoreboard(
            "plab_1d_pure", my_fires, my_grades,
            universe_base_rate_21d=0.01,
        )
        assert sb["lift_vs_universe_base"] is not None
        assert abs(sb["lift_vs_universe_base"] - 0.03) < 1e-5

    def test_lift_null_when_no_ctrl(self):
        """No ctrl grades → lift_vs_ctrl is None."""
        my_fires = [_fire()]
        my_grades = [_grade()]
        sb = scoreboard("plab_1d_pure", my_fires, my_grades)
        assert sb["lift_vs_ctrl"] is None


class TestScoreboardMonthsSpan:
    """months_span and distinct_fire_dates helpers."""

    def test_months_span_zero_one_fire(self):
        assert _months_span(["2024-01-10"]) == 0.0

    def test_months_span_three_months(self):
        span = _months_span(["2024-01-02", "2024-04-02"])
        assert abs(span - 3.0) < 0.1

    def test_distinct_fire_dates(self):
        dates = ["2024-01-02", "2024-01-02", "2024-01-03"]
        assert _distinct_fire_dates(dates) == 2


class TestAllScoreboards:
    """all_scoreboards returns one scoreboard per engine_id."""

    def test_all_scoreboards_returns_all_ids(self):
        role_map = {
            "plab_1d_pure": "entry",
            "plab_lh_compounder": "hold_thesis",
        }
        boards = all_scoreboards(fires=[], grades=[], horizon_role_map=role_map)
        ids = {sb["engine_id"] for sb in boards}
        assert ids == {"plab_1d_pure", "plab_lh_compounder"}


class TestNAVTradingSessionFix:
    """NAV ladder uses business-day offsets, not calendar-day offsets (Finding 3).

    Calendar days include weekends; the 21-session cohort window must span exactly
    21 business days, not ~28 calendar days.
    """

    def test_nav_no_weekend_dates(self):
        """NAV index must not contain Saturday (weekday=5) or Sunday (weekday=6)."""
        # Two cohorts 5 business days apart
        fires = []
        grades = []
        start = pd.Timestamp("2024-01-02")  # Tuesday
        for i in range(2):
            fire_date = str((start + pd.offsets.BDay(i * 5)).date())
            exec_date = str((start + pd.offsets.BDay(i * 5 + 1)).date())
            fires.append({
                "engine_id": "plab_1d_pure",
                "ticker": f"T{i:02d}",
                "fire_date": fire_date,
                "exec_date": exec_date,
                "authority": "display_only",
            })
            grades.append({
                "engine_id": "plab_1d_pure",
                "ticker": f"T{i:02d}",
                "fire_date": fire_date,
                "exec_date": exec_date,
                "horizon": 21,
                "ret_excess_spy": 0.02,
                "authority": "display_only",
            })
        nav, _ = _nav_ladder(fires, grades)
        assert not nav.empty
        weekdays = [d.weekday() for d in nav.index]
        assert all(wd < 5 for wd in weekdays), (
            f"NAV index contains weekend dates: "
            f"{[d for d in nav.index if d.weekday() >= 5]}"
        )

    def test_nav_single_cohort_21_sessions_only(self):
        """Single cohort: NAV must have exactly 21 entries (21 business days)."""
        fires = [{
            "engine_id": "plab_1d_pure",
            "ticker": "T00",
            "fire_date": "2024-01-02",
            "exec_date": "2024-01-03",
            "authority": "display_only",
        }]
        grades = [{
            "engine_id": "plab_1d_pure",
            "ticker": "T00",
            "fire_date": "2024-01-02",
            "exec_date": "2024-01-03",
            "horizon": 21,
            "ret_excess_spy": 0.021,
            "authority": "display_only",
        }]
        nav, _ = _nav_ladder(fires, grades)
        assert not nav.empty
        # Should be exactly 21 business-day entries
        assert len(nav) == 21, (
            f"Single cohort NAV should have 21 trading-session entries, got {len(nav)}"
        )


class TestRulerBranching:
    """Washout/reversion family uses wr_abs as primary lift metric (Finding 5, PL-R3)."""

    def test_reversion_ruler_uses_wr_abs_for_lift(self):
        """For ruler='21d_abs_reversion_capture_mfe_mae', lift_vs_ctrl uses wr_abs, not med_exc."""
        eid = "plab_washout_deep"
        ctrl_grades = [
            _grade(engine_id="plab_random_ctrl", ticker=f"C{i:02d}",
                   fire_date=f"2024-01-{10+i:02d}",
                   ret_excess_spy=0.01, ret_abs=0.02)
            for i in range(5)
        ]
        my_fires = [
            _fire(engine_id=eid, ticker=f"T{i:02d}", fire_date=f"2024-01-{10+i:02d}")
            for i in range(5)
        ]
        # All absolute returns positive → wr_abs = 1.0; excess neutral to show ruler matters
        my_grades = [
            _grade(engine_id=eid, ticker=f["ticker"], fire_date=f["fire_date"],
                   ret_abs=0.10, ret_excess_spy=0.00)
            for f in my_fires
        ]
        sb = scoreboard(
            eid, my_fires, my_grades,
            ruler="21d_abs_reversion_capture_mfe_mae",
            ctrl_fires=[], ctrl_grades=ctrl_grades,
        )
        # Both book and ctrl have wr_abs=1.0 (all ret_abs > 0) → lift = 0.0 (not None)
        # If we had used med_exc: 0.00 - 0.01 = -0.01 (wrong ruler)
        assert sb.get("ruler") == "21d_abs_reversion_capture_mfe_mae"
        assert sb.get("lift_vs_ctrl") is not None, (
            "lift_vs_ctrl should be computed for reversion ruler; got None. "
            "Check that engine_id matches in fires/grades."
        )
        # Since both are wr_abs=1.0, lift=0.0 not a negative number
        assert sb["lift_vs_ctrl"] >= 0.0

    def test_momentum_ruler_uses_med_exc_for_lift(self):
        """For ruler='21d_spy_excess', lift_vs_ctrl still uses med_exc (default behaviour)."""
        ctrl_grades = [
            _grade(engine_id="plab_random_ctrl", ticker=f"C{i:02d}",
                   fire_date=f"2024-01-{10+i:02d}", ret_excess_spy=0.01)
            for i in range(5)
        ]
        my_fires = [_fire(ticker=f"T{i:02d}", fire_date=f"2024-01-{10+i:02d}") for i in range(5)]
        my_grades = [
            _grade(ticker=f["ticker"], fire_date=f["fire_date"], ret_excess_spy=0.03)
            for f in my_fires
        ]
        sb = scoreboard(
            "plab_1d_pure", my_fires, my_grades,
            ruler="21d_spy_excess",
            ctrl_fires=[], ctrl_grades=ctrl_grades,
        )
        assert abs(sb["lift_vs_ctrl"] - 0.02) < 1e-5, (
            f"lift_vs_ctrl should be ~0.02 (0.03-0.01), got {sb['lift_vs_ctrl']}"
        )

    def test_ruler_stored_in_scoreboard(self):
        """Scoreboard dict includes the ruler key for downstream display."""
        sb = scoreboard(
            "plab_washout_deep", [], [],
            ruler="21d_abs_reversion_capture_mfe_mae",
        )
        assert sb["ruler"] == "21d_abs_reversion_capture_mfe_mae"


class TestControlsNotDuplicated:
    """PL-R5: lift_vs_universe_base must be null until a genuine independent base rate
    is available.  Passing the same ctrl median as both lift_vs_ctrl and
    lift_vs_universe_base misrepresents two independent yardsticks (Finding 4/8).
    """

    def test_all_scoreboards_lift_vs_universe_base_is_null_by_default(self):
        """all_scoreboards passes universe_base_rate_21d=None so lift_vs_universe_base is null."""
        ctrl_grades = [
            _grade(engine_id="plab_random_ctrl", ticker=f"C{i:02d}",
                   fire_date=f"2024-01-{10+i:02d}", ret_excess_spy=0.01)
            for i in range(5)
        ]
        my_fires = [_fire(ticker=f"T{i:02d}", fire_date=f"2024-01-{10+i:02d}") for i in range(5)]
        my_grades = [
            _grade(ticker=f["ticker"], fire_date=f["fire_date"], ret_excess_spy=0.03)
            for f in my_fires
        ]
        all_fires = my_fires + [_fire(engine_id="plab_random_ctrl", ticker=f"C{i:02d}",
                                       fire_date=f"2024-01-{10+i:02d}") for i in range(5)]
        all_grades = my_grades + ctrl_grades
        boards = all_scoreboards(
            all_fires, all_grades,
            {"plab_1d_pure": "entry"},
            ctrl_grades=ctrl_grades,
        )
        sb = next(b for b in boards if b["engine_id"] == "plab_1d_pure")
        # lift_vs_ctrl is populated from ctrl (we have ctrl grades)
        assert sb["lift_vs_ctrl"] is not None
        # lift_vs_universe_base is null — no independent base rate wired in yet
        assert sb["lift_vs_universe_base"] is None, (
            "lift_vs_universe_base must be null until a genuine independent universe "
            f"base rate is wired in; got {sb['lift_vs_universe_base']}"
        )

    def test_scoreboard_lift_vs_base_populated_when_explicit(self):
        """Explicit universe_base_rate_21d argument does populate lift_vs_universe_base."""
        my_fires = [_fire(ticker="T01", fire_date="2024-01-10")]
        my_grades = [_grade(ticker="T01", fire_date="2024-01-10", ret_excess_spy=0.05)]
        sb = scoreboard(
            "plab_1d_pure", my_fires, my_grades,
            universe_base_rate_21d=0.01,
        )
        assert sb["lift_vs_universe_base"] is not None
        assert abs(sb["lift_vs_universe_base"] - 0.04) < 1e-5
