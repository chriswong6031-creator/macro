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
    _path_stats,
    _capture_ratio,
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
        # Filter ret rows only (path rows also present now)
        ret_grades = [g for g in grades if g.get("kind") in ("ret", None)]
        assert len(ret_grades) > 0, "Expected at least one ret grade row"
        assert ret_grades[0]["exec_date"] == expected_exec_date
        assert abs(ret_grades[0]["exec_price"] - expected_exec_price) < 1e-4

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
        h5 = [g for g in grades if g.get("horizon") == 5 and g.get("kind") in ("ret", None)]
        assert len(h5) > 0, "Expected h5 ret grade — panel has 100 sessions"
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
        h5 = [g for g in grades if g.get("horizon") == 5 and g.get("kind") in ("ret", None)]
        assert len(h5) > 0, "Expected h5 ret grade — panel has 100 sessions"
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
        ret_grades = [g for g in grades if g.get("kind") in ("ret", None)]
        assert len(ret_grades) > 0
        for g in ret_grades:
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
        ret_grades = [g for g in grades if g.get("kind") in ("ret", None)]
        assert len(ret_grades) > 0
        for g in ret_grades:
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
        fd = str(dates[0].date())
        # Pre-populate already_graded with all ret horizons AND path windows
        already = {
            ("plab_1d_pure", "AAPL", fd, h, "ret")
            for h in ENTRY_HORIZONS
        } | {
            ("plab_1d_pure", "AAPL", fd, w, "path")
            for w in (25, 63)
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


# ================================================================ NEW TESTS ====
# TASK 3 additions


class TestPathRowEmission:
    """(a) Path rows emitted at correct windows; absent when window not elapsed."""

    def _make_panel_with_path(
        self,
        n_sessions: int = 90,
        start: str = "2024-01-02",
        ticker: str = "AAPL",
        base: float = 100.0,
    ) -> pd.DataFrame:
        """Panel where price rises then falls, giving known MFE/MAE positions.

        Price path (after exec day=0):
          sessions 1-10: rise 1% per session
          sessions 11-25: fall 0.5% per session
          sessions 26+:  flat

        exec_price = base (session 1 in date index, fire on session 0).
        MFE = peak at session 10: (1.01^10 - 1) ≈ 0.1046
        MAE = trough at session 25: below 1.0 because fall dominates later
        t_mfe = 10, t_mae = 25 (within 25-session window)
        mae_before_mfe = False (t_mae=25 > t_mfe=10)
        """
        dates = pd.bdate_range(start=start, periods=n_sessions)
        prices = np.empty(n_sessions)
        prices[0] = base
        for i in range(1, n_sessions):
            if i <= 10:
                prices[i] = prices[i - 1] * 1.01
            elif i <= 25:
                prices[i] = prices[i - 1] * 0.995
            else:
                prices[i] = prices[i - 1]
        return pd.DataFrame({ticker: prices, "SPY": np.full(n_sessions, 450.0)}, index=dates)

    def test_path25_present_when_window_elapsed(self):
        """path-25 row is emitted when exec+25 sessions have elapsed."""
        panel = self._make_panel_with_path(n_sessions=90)
        dates = panel.index
        spy = panel["SPY"]
        # Fire on session 0; exec on session 1; exec+25 = session 26 < 90 → elapsed
        fire = _fire(fire_date=str(dates[0].date()), ticker="AAPL")
        grades, _ = grade_fires([fire], panel, spy)
        path25 = [g for g in grades if g.get("kind") == "path" and g.get("horizon") == 25]
        assert len(path25) == 1, f"Expected 1 path-25 row, got {len(path25)}"

    def test_path63_absent_when_window_not_elapsed(self):
        """path-63 row absent when only 90 sessions total (exec+63 = session 64 < 90 but fire on 0 so exec on 1: 1+63=64 < 90 → elapsed; use short panel)."""
        # Use panel of only 50 sessions so exec+63 is not elapsed
        panel = self._make_panel_with_path(n_sessions=50)
        dates = panel.index
        spy = panel["SPY"]
        fire = _fire(fire_date=str(dates[0].date()), ticker="AAPL")
        grades, _ = grade_fires([fire], panel, spy)
        path63 = [g for g in grades if g.get("kind") == "path" and g.get("horizon") == 63]
        assert len(path63) == 0, "path-63 should be absent when panel < exec+63 sessions"

    def test_path25_correct_mfe_mae_t(self):
        """path-25 t_mfe/t_mae/mae_before_mfe/sessions_underwater correct on hand-computable path."""
        panel = self._make_panel_with_path(n_sessions=90)
        dates = panel.index
        spy = panel["SPY"]
        fire = _fire(fire_date=str(dates[0].date()), ticker="AAPL")
        grades, _ = grade_fires([fire], panel, spy)
        p25 = [g for g in grades if g.get("kind") == "path" and g.get("horizon") == 25]
        assert len(p25) == 1
        row = p25[0]
        # Peak at session 10 (1-based within window [exec+1..exec+25])
        # exec = dates[1], window = dates[2..26] relative to exec+1..exec+25
        # In our panel: session 10 relative to fire_date=dates[0], exec=dates[1]
        # t_mfe = 1-based index within [exec+1..exec+25] where peak occurs
        # Price rises for sessions 1-10 (exec+1 to exec+10), so t_mfe=10
        # Compute expected values directly from the panel to avoid brittle hard-coded numbers.
        panel_local = self._make_panel_with_path(n_sessions=90)
        dates_local = panel_local.index
        exec_price_local = float(panel_local.loc[dates_local[1], "AAPL"])
        window_local = panel_local.loc[dates_local[2:27], "AAPL"]
        rets_local = (window_local.values - exec_price_local) / exec_price_local
        expected_t_mfe = int(rets_local.argmax()) + 1
        expected_t_mae = int(rets_local.argmin()) + 1
        expected_mae_before_mfe = bool(expected_t_mae < expected_t_mfe)
        expected_mfe = float(rets_local.max())
        expected_mae = float(rets_local.min())

        assert row["t_mfe"] == expected_t_mfe, f"Expected t_mfe={expected_t_mfe}, got {row['t_mfe']}"
        assert row["t_mae"] == expected_t_mae, f"Expected t_mae={expected_t_mae}, got {row['t_mae']}"
        assert row["mae_before_mfe"] is expected_mae_before_mfe
        assert isinstance(row["sessions_underwater"], int)
        assert 0 <= row["sessions_underwater"] <= 25
        assert abs(row["mfe"] - expected_mfe) < 1e-5
        assert abs(row["mae"] - expected_mae) < 1e-5

    def test_path_rows_carry_required_fields(self):
        """Every path row has all required fields."""
        panel = self._make_panel_with_path(n_sessions=90)
        dates = panel.index
        spy = panel["SPY"]
        fire = _fire(fire_date=str(dates[0].date()), ticker="AAPL")
        grades, _ = grade_fires([fire], panel, spy)
        required = {
            "engine_id", "ticker", "fire_date", "horizon", "kind",
            "exec_date", "exec_price", "mfe", "mae", "t_mfe", "t_mae",
            "mae_before_mfe", "sessions_underwater", "matured", "graded_at", "authority",
        }
        for g in grades:
            if g.get("kind") == "path":
                missing = required - set(g.keys())
                assert not missing, f"Path row missing fields: {missing}"
                assert g["authority"] == "display_only"
                assert g["matured"] is True


class TestIntradayPathMetrics:
    """(b) mfe_hl/mae_hl use high/low panels; absent → _hl fields null."""

    def _make_panels(self, n: int = 90, base: float = 100.0, spread: float = 2.0):
        """Panels where high = close + spread, low = close - spread."""
        dates = pd.bdate_range("2024-01-02", periods=n)
        closes = np.full(n, base)
        # Make close trend up slightly so mfe > 0
        closes = base * (1.001 ** np.arange(n))
        highs = closes + spread
        lows = closes - spread
        close_panel = pd.DataFrame({"AAPL": closes, "SPY": np.full(n, 450.0)}, index=dates)
        high_panel = pd.DataFrame({"AAPL": highs}, index=dates)
        low_panel = pd.DataFrame({"AAPL": lows}, index=dates)
        return close_panel, high_panel, low_panel, dates

    def test_mfe_hl_geq_close_mfe(self):
        """High panel mfe_hl >= close mfe (intraday high always >= close)."""
        close_panel, high_panel, low_panel, dates = self._make_panels()
        spy = close_panel["SPY"]
        fire = _fire(fire_date=str(dates[0].date()), ticker="AAPL")
        grades, _ = grade_fires([fire], close_panel, spy, high_panel=high_panel, low_panel=low_panel)
        path25 = [g for g in grades if g.get("kind") == "path" and g.get("horizon") == 25]
        assert len(path25) == 1
        row = path25[0]
        assert row["mfe_hl"] is not None, "mfe_hl should be populated when high_panel supplied"
        assert row["mfe_hl"] >= row["mfe"], f"mfe_hl {row['mfe_hl']} should >= close mfe {row['mfe']}"

    def test_mae_hl_leq_close_mae(self):
        """Low panel mae_hl <= close mae (intraday low always <= close)."""
        close_panel, high_panel, low_panel, dates = self._make_panels()
        spy = close_panel["SPY"]
        fire = _fire(fire_date=str(dates[0].date()), ticker="AAPL")
        grades, _ = grade_fires([fire], close_panel, spy, high_panel=high_panel, low_panel=low_panel)
        path25 = [g for g in grades if g.get("kind") == "path" and g.get("horizon") == 25]
        assert len(path25) == 1
        row = path25[0]
        assert row["mae_hl"] is not None, "mae_hl should be populated when low_panel supplied"
        assert row["mae_hl"] <= row["mae"], f"mae_hl {row['mae_hl']} should <= close mae {row['mae']}"

    def test_hl_null_when_panels_absent(self):
        """Without high/low panels: mfe_hl and mae_hl are null."""
        close_panel, _, _, dates = self._make_panels()
        spy = close_panel["SPY"]
        fire = _fire(fire_date=str(dates[0].date()), ticker="AAPL")
        grades, _ = grade_fires([fire], close_panel, spy)  # no high/low panels
        path25 = [g for g in grades if g.get("kind") == "path" and g.get("horizon") == 25]
        assert len(path25) == 1
        assert path25[0]["mfe_hl"] is None, "mfe_hl should be null without high_panel"
        assert path25[0]["mae_hl"] is None, "mae_hl should be null without low_panel"

    def test_close_mfe_mae_still_populated_without_hl(self):
        """Even without high/low panels: close-based mfe/mae are populated."""
        close_panel, _, _, dates = self._make_panels()
        spy = close_panel["SPY"]
        fire = _fire(fire_date=str(dates[0].date()), ticker="AAPL")
        grades, _ = grade_fires([fire], close_panel, spy)
        path25 = [g for g in grades if g.get("kind") == "path" and g.get("horizon") == 25]
        assert len(path25) == 1
        assert path25[0]["mfe"] is not None
        assert path25[0]["mae"] is not None


class TestCaptureRatio:
    """(c) Capture ratio: hand-computable case."""

    def test_capture_ratio_hand_computed(self):
        """Capture ratio = ret_abs_h21 / path25_mfe; median over fires with mfe > 0."""
        # Set up: 3 fires, each with ret_abs=0.05 at h21 and path25_mfe=0.10
        # → capture = 0.05/0.10 = 0.5 for each; median = 0.5
        my_grades = []
        for i in range(3):
            fd = f"2024-01-{10+i:02d}"
            my_grades.append({
                "engine_id": "plab_1d_pure",
                "ticker": f"T{i:02d}",
                "fire_date": fd,
                "horizon": 21,
                "kind": "ret",
                "ret_abs": 0.05,
                "ret_excess_spy": 0.02,
                "mfe": None,
                "mae": None,
                "authority": "display_only",
            })
            my_grades.append({
                "engine_id": "plab_1d_pure",
                "ticker": f"T{i:02d}",
                "fire_date": fd,
                "horizon": 25,
                "kind": "path",
                "mfe": 0.10,
                "mae": -0.03,
                "t_mfe": 10,
                "t_mae": 20,
                "mfe_hl": 0.11,
                "mae_hl": -0.04,
                "mae_before_mfe": False,
                "sessions_underwater": 5,
                "matured": True,
                "graded_at": "2024-02-15T00:00:00+00:00",
                "authority": "display_only",
            })
        ratio = _capture_ratio([], my_grades, entry_horizon=21, path_window=25)
        assert ratio is not None
        assert abs(ratio - 0.5) < 1e-5, f"Expected capture 0.5, got {ratio}"

    def test_capture_ratio_null_when_no_path_rows(self):
        """No path rows → capture ratio is None."""
        grades = [_grade(ticker="T01", fire_date="2024-01-10")]
        ratio = _capture_ratio([], grades, entry_horizon=21, path_window=25)
        assert ratio is None

    def test_scoreboard_h21_capture_field_present(self):
        """Scoreboard always has h{N}_capture fields (even when null)."""
        fires = [_fire(ticker="T01", fire_date="2024-01-10")]
        grades = [_grade(ticker="T01", fire_date="2024-01-10")]
        sb = scoreboard("plab_1d_pure", fires, grades)
        for h in (5, 10, 21, 63):
            assert f"h{h}_capture" in sb, f"Missing h{h}_capture in scoreboard"


class TestKindAwareDedup:
    """(d) kind-aware dedup: ret row and path row at same horizon both survive."""

    def test_ret_and_path_at_same_horizon_both_kept(self):
        """A ret row and path row for the same fire/horizon have different kind
        and must both be emitted (not deduped against each other).
        """
        # Use a 90-session panel so both h=5 (ret) and path-25 can be emitted
        n = 90
        dates = pd.bdate_range("2024-01-02", periods=n)
        panel = pd.DataFrame({"AAPL": np.full(n, 100.0), "SPY": np.full(n, 450.0)}, index=dates)
        spy = panel["SPY"]
        fire = _fire(fire_date=str(dates[0].date()), ticker="AAPL")
        grades, _ = grade_fires([fire], panel, spy)

        # Should have both ret rows (for h=5,10,21,63 or as many as elapsed)
        # and path rows (path-25 since n=90 > exec+25=27)
        ret_rows = [g for g in grades if g.get("kind") in ("ret", None)]
        path_rows = [g for g in grades if g.get("kind") == "path"]
        assert len(ret_rows) > 0, "Expected ret rows"
        assert len(path_rows) > 0, "Expected path rows"

        # Specifically, a ret row at h=25 does not exist (25 not in ENTRY_HORIZONS)
        # but a path row at h=25 should exist
        h25_ret = [g for g in grades if g.get("horizon") == 25 and g.get("kind") in ("ret", None)]
        h25_path = [g for g in grades if g.get("horizon") == 25 and g.get("kind") == "path"]
        assert len(h25_ret) == 0, "h=25 is not an entry ret horizon"
        assert len(h25_path) == 1, "h=25 path row should be present"

    def test_already_graded_path_key_prevents_duplicate(self):
        """already_graded containing a path key prevents re-emission of that path row."""
        n = 90
        dates = pd.bdate_range("2024-01-02", periods=n)
        panel = pd.DataFrame({"AAPL": np.full(n, 100.0), "SPY": np.full(n, 450.0)}, index=dates)
        spy = panel["SPY"]
        fire = _fire(fire_date=str(dates[0].date()), ticker="AAPL")
        fire_date_str = str(dates[0].date())

        # Pre-populate path-25 key
        already = {("plab_1d_pure", "AAPL", fire_date_str, 25, "path")}
        grades, _ = grade_fires([fire], panel, spy, already_graded=already)
        h25_path = [g for g in grades if g.get("horizon") == 25 and g.get("kind") == "path"]
        assert len(h25_path) == 0, "path-25 should be skipped when in already_graded"

    def test_ret_and_path_63_both_persist_in_ledger(self):
        """Ledger keeps a ret row and path row at horizon=63 as separate rows."""
        from engine.pick_lab.ledger import keep_first, GRADE_KEY
        rows = [
            {
                "engine_id": "plab_1d_pure",
                "ticker": "AAPL",
                "fire_date": "2024-01-10",
                "horizon": 63,
                "kind": "ret",
                "authority": "display_only",
            },
            {
                "engine_id": "plab_1d_pure",
                "ticker": "AAPL",
                "fire_date": "2024-01-10",
                "horizon": 63,
                "kind": "path",
                "authority": "display_only",
            },
        ]
        deduped = keep_first(rows, GRADE_KEY)
        assert len(deduped) == 2, (
            f"Both ret and path rows at same fire/horizon should survive; got {len(deduped)}"
        )


class TestRealCalendarFixture:
    """(e) Real-calendar fixture: gapped calendar, year boundary, exec/horizon counting."""

    def _make_gapped_panel(
        self,
        ticker: str = "AAPL",
        base: float = 100.0,
    ) -> pd.DataFrame:
        """Build a panel that:
        - Starts 2024-12-20 (Friday before Christmas week)
        - Has a gap over Christmas holiday (Dec 25-26 skipped)
        - Crosses the Dec-31 → Jan-2 year boundary
        - Contains a mid-window gap (e.g., Dec 25 missing from bdate_range)

        bdate_range already skips weekends.  Christmas 2024 falls on Wednesday;
        to simulate a holiday gap we manually exclude Dec 25.
        """
        # Build a raw business-day range then remove the holiday
        raw = pd.bdate_range("2024-12-20", "2025-02-28")
        # Remove Christmas Day (Dec 25, 2024) — it's a Wednesday (business day)
        holiday = pd.Timestamp("2024-12-25")
        dates = raw[raw != holiday]
        prices = base * (1.001 ** np.arange(len(dates)))
        spy_prices = np.full(len(dates), 450.0)
        return pd.DataFrame({ticker: prices, "SPY": spy_prices}, index=dates)

    def test_exec_date_skips_holiday_gap(self):
        """exec_date is the first session after fire_date, even when fire_date is
        immediately before a gap (Christmas).
        """
        panel = self._make_gapped_panel()
        dates = panel.index
        spy = panel["SPY"]

        # Fire on Dec 24 (day before gap); exec should be Dec 26 (Wed after Christmas)
        fire_date = pd.Timestamp("2024-12-24")
        assert fire_date in dates, "Dec 24 must be in the panel"

        fire = _fire(fire_date=str(fire_date.date()), ticker="AAPL")
        grades, _ = grade_fires([fire], panel, spy)
        ret_grades = [g for g in grades if g.get("kind") in ("ret", None)]
        assert len(ret_grades) > 0, "Expected at least one ret grade after the gap"

        exec_date_str = ret_grades[0]["exec_date"]
        exec_date = pd.Timestamp(exec_date_str)
        # exec should be the session after Dec 24 — Dec 26 (Christmas Day skipped)
        assert exec_date > fire_date
        assert exec_date.month == 12 and exec_date.day == 26, (
            f"Expected exec on Dec 26, got {exec_date_str}"
        )

    def test_horizon_counting_skips_gap(self):
        """Session counting is index-position-based (not calendar-day-based),
        so holiday gaps are naturally skipped.
        """
        panel = self._make_gapped_panel()
        dates = panel.index
        spy = panel["SPY"]

        # Fire on first date; exec on second
        fire_date = str(dates[0].date())
        fire = _fire(fire_date=fire_date, ticker="AAPL")
        grades, _ = grade_fires([fire], panel, spy)
        ret_grades = [g for g in grades if g.get("kind") in ("ret", None)]
        assert len(ret_grades) > 0

        # Verify exec_date is the immediately next session (not a calendar day later)
        exec_date = pd.Timestamp(ret_grades[0]["exec_date"])
        expected_exec = dates[1]
        assert exec_date == expected_exec, (
            f"exec_date {exec_date} should be next session {expected_exec}"
        )

    def test_year_boundary_no_error(self):
        """Panel crossing Dec-31 → Jan-2 year boundary grades without error."""
        panel = self._make_gapped_panel()
        dates = panel.index
        spy = panel["SPY"]

        # Fire near year end so the h=5 horizon crosses into January
        dec_dates = dates[dates.month == 12]
        assert len(dec_dates) >= 5, "Need at least 5 December sessions"

        fire_date = str(dec_dates[-5].date())  # 5 sessions before end of December
        fire = _fire(fire_date=fire_date, ticker="AAPL")
        grades, n_ung = grade_fires([fire], panel, spy)
        # Should grade without error; h=5 target lands in January
        assert n_ung == 0, "AAPL is in panel — should not be ungradeable"
        h5 = [g for g in grades if g.get("horizon") == 5 and g.get("kind") in ("ret", None)]
        assert len(h5) == 1, "h=5 should be graded when panel extends into January"
        h5_date = pd.Timestamp(h5[0].get("exec_date"))  # exec in Dec
        # The h=5 return target should be in January (crosses year boundary)
        # We can't easily assert target date here without reconstructing the index;
        # but we can assert exec_price is finite
        assert h5[0]["exec_price"] > 0


class TestPathStatsInScoreboard:
    """path25_* and path63_* fields appear in entry scoreboard."""

    def _path_grade(
        self, engine_id="plab_1d_pure", ticker="AAPL", fire_date="2024-01-10",
        horizon=25, mfe=0.10, mae=-0.03, t_mfe=8, t_mae=22,
        mae_before_mfe=False, sessions_underwater=5,
    ) -> dict:
        return {
            "engine_id": engine_id,
            "ticker": ticker,
            "fire_date": fire_date,
            "horizon": horizon,
            "kind": "path",
            "exec_date": "2024-01-11",
            "exec_price": 100.0,
            "mfe": mfe,
            "mae": mae,
            "t_mfe": t_mfe,
            "t_mae": t_mae,
            "mfe_hl": mfe + 0.01,
            "mae_hl": mae - 0.01,
            "mae_before_mfe": mae_before_mfe,
            "sessions_underwater": sessions_underwater,
            "matured": True,
            "graded_at": "2024-02-15T00:00:00+00:00",
            "authority": "display_only",
        }

    def test_path25_fields_in_scoreboard(self):
        """Scoreboard includes path25_* fields computed from path rows."""
        fires = [_fire(ticker="T01", fire_date="2024-01-10")]
        grades = [
            _grade(ticker="T01", fire_date="2024-01-10"),
            self._path_grade(ticker="T01", fire_date="2024-01-10", horizon=25),
        ]
        sb = scoreboard("plab_1d_pure", fires, grades)
        assert "path25_n" in sb
        assert sb["path25_n"] == 1
        assert sb["path25_med_mfe"] is not None
        assert sb["path25_med_abs_mae"] is not None
        assert "path25_asym" in sb
        assert "path25_med_t_mfe" in sb
        assert "path25_med_t_mae" in sb
        assert "path25_pct_mae_first" in sb
        assert "path25_med_underwater" in sb

    def test_path63_fields_in_scoreboard(self):
        """Scoreboard includes path63_* fields."""
        fires = [_fire(ticker="T01", fire_date="2024-01-10")]
        grades = [
            _grade(ticker="T01", fire_date="2024-01-10"),
            self._path_grade(ticker="T01", fire_date="2024-01-10", horizon=63),
        ]
        sb = scoreboard("plab_1d_pure", fires, grades)
        assert "path63_n" in sb
        assert "path63_med_mfe" in sb

    def test_existing_h21_fields_unchanged(self):
        """Existing h{N}_* return stats still present and unchanged."""
        fires = [_fire(ticker="T01", fire_date="2024-01-10")]
        grades = [_grade(ticker="T01", fire_date="2024-01-10", ret_excess_spy=0.05)]
        sb = scoreboard("plab_1d_pure", fires, grades)
        # Core return-based fields still present
        for h in (5, 10, 21, 63):
            assert f"h{h}_n" in sb
            assert f"h{h}_wr_abs" in sb
            assert f"h{h}_med_exc" in sb

    def test_path_rows_excluded_from_h21_wr(self):
        """Path rows at horizon=25 do not pollute h21 return stats."""
        fires = [_fire(ticker="T01", fire_date="2024-01-10")]
        # Only a path row, no ret row → h21_wr_abs should be None (no ret grades)
        grades = [
            self._path_grade(ticker="T01", fire_date="2024-01-10", horizon=25),
        ]
        sb = scoreboard("plab_1d_pure", fires, grades)
        # h21 stats should be null (no ret rows at h=21)
        assert sb["h21_wr_abs"] is None, "h21_wr_abs should be None with no ret rows"
        assert sb["h21_n"] == 0
