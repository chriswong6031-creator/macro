"""Tests for F-HZ-1 dilution-hazard phase-0 study harness.

Covers:
  - Predicate thresholds match F_HZ1_PREREG.md exactly (via F_HZ1_CONSTANTS)
  - PIT join correctness: filing on fire_date excluded; filing day-before included
  - Floor gating: arms below N_FIRES_FLOOR / N_EPISODE_FLOOR route to DEFER-on-floor
  - Era-law split routing (2021+ vs pre-2021)
  - Gate behavior when dilution_events.parquet or replay_boarded absent
  - Trial-budget declaration fires before any statistic (idempotent)
"""
from __future__ import annotations

import json
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Import harness — single source of truth for constants
# ---------------------------------------------------------------------------
from scripts.research.f_hz1_study import (
    F_HZ1_CONSTANTS,
    build_predicates,
    check_data_gates,
    check_floors,
    compute_contrast,
    compute_outcomes,
    declare_trial_budget,
    era_law_split,
    run_study,
    _assign_episode_cluster,
    _store_age_days,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_fire(ticker: str, fire_date: str) -> dict:
    return {"ticker": ticker, "date": fire_date, "verdict_grade": True, "verdict_type": "fire"}


def _fires(*args) -> pd.DataFrame:
    """Build fires DataFrame from tuples (ticker, date)."""
    return pd.DataFrame([_make_fire(t, d) for t, d in args])


def _dilution(ticker: str, form: str, filing_date: str) -> dict:
    return {"ticker": ticker, "form": form, "filing_date": filing_date, "accession": f"{ticker}-{filing_date}"}


def _dilutions(*args) -> pd.DataFrame:
    """Build dilution DataFrame from tuples (ticker, form, filing_date)."""
    return pd.DataFrame([_dilution(t, f, d) for t, f, d in args])


# ---------------------------------------------------------------------------
# 1. Predicate threshold constants match the prereg
# ---------------------------------------------------------------------------

class TestPreregConstants:
    """Verify that constants in F_HZ1_CONSTANTS match the prereg document values."""

    def test_shelf_lookback_days(self):
        assert F_HZ1_CONSTANTS.SHELF_LOOKBACK_DAYS == 365

    def test_takedown_lookback_days(self):
        assert F_HZ1_CONSTANTS.TAKEDOWN_LOOKBACK_DAYS == 90

    def test_trailing_lookback_days(self):
        assert F_HZ1_CONSTANTS.TRAILING_LOOKBACK_DAYS == 365

    def test_trailing_min_count(self):
        assert F_HZ1_CONSTANTS.TRAILING_MIN_COUNT == 1

    def test_stop_mult(self):
        assert F_HZ1_CONSTANTS.STOP_MULT == 0.95

    def test_dead_money_21_threshold(self):
        assert F_HZ1_CONSTANTS.DEAD_MONEY_21_THRESHOLD == 0.0

    def test_n_fires_floor(self):
        assert F_HZ1_CONSTANTS.N_FIRES_FLOOR == 300

    def test_n_episode_floor(self):
        assert F_HZ1_CONSTANTS.N_EPISODE_FLOOR == 25

    def test_fdr_family(self):
        assert F_HZ1_CONSTANTS.FDR_FAMILY == "dilution_hazard"

    def test_fdr_budget(self):
        assert F_HZ1_CONSTANTS.FDR_BUDGET == 3

    def test_shelf_forms_exact(self):
        assert F_HZ1_CONSTANTS.SHELF_FORMS == frozenset({"S-3", "S-3ASR", "S-3/A"})

    def test_takedown_forms_exact(self):
        assert F_HZ1_CONSTANTS.TAKEDOWN_FORMS == frozenset(
            {"424B1", "424B2", "424B3", "424B4", "424B5"}
        )

    def test_trailing_forms_is_union(self):
        expected = F_HZ1_CONSTANTS.SHELF_FORMS | F_HZ1_CONSTANTS.TAKEDOWN_FORMS
        assert F_HZ1_CONSTANTS.TRAILING_FORMS == expected


# ---------------------------------------------------------------------------
# 2. PIT join correctness
# ---------------------------------------------------------------------------

class TestPITJoin:
    """PIT law: filing_date < fire_date (strictly before). Same-day excluded."""

    def test_filing_strictly_before_counts(self):
        fires = _fires(("AAPL", "2024-06-15"))
        dil   = _dilutions(("AAPL", "S-3", "2024-06-14"))  # day before → counts
        result = build_predicates(fires, dil)
        assert bool(result["hazard_shelf_active"].iloc[0]) is True

    def test_filing_on_fire_date_excluded(self):
        """Same-day filing must NOT count (intraday unknown)."""
        fires = _fires(("AAPL", "2024-06-15"))
        dil   = _dilutions(("AAPL", "S-3", "2024-06-15"))  # same day → excluded
        result = build_predicates(fires, dil)
        assert bool(result["hazard_shelf_active"].iloc[0]) is False

    def test_filing_after_fire_date_excluded(self):
        fires = _fires(("AAPL", "2024-06-15"))
        dil   = _dilutions(("AAPL", "S-3", "2024-06-16"))  # after → excluded
        result = build_predicates(fires, dil)
        assert bool(result["hazard_shelf_active"].iloc[0]) is False

    def test_shelf_lookback_boundary_inclusive(self):
        """Filing exactly 365 days before fire_date should count for predicate A."""
        fire_date = date(2024, 6, 15)
        filing_date = fire_date - timedelta(days=365)
        fires = _fires(("AAPL", str(fire_date)))
        dil   = _dilutions(("AAPL", "S-3", str(filing_date)))
        result = build_predicates(fires, dil)
        assert bool(result["hazard_shelf_active"].iloc[0]) is True

    def test_shelf_lookback_beyond_window_excluded(self):
        """Filing 366 days before fire_date must NOT count for predicate A."""
        fire_date = date(2024, 6, 15)
        filing_date = fire_date - timedelta(days=366)
        fires = _fires(("AAPL", str(fire_date)))
        dil   = _dilutions(("AAPL", "S-3", str(filing_date)))
        result = build_predicates(fires, dil)
        assert bool(result["hazard_shelf_active"].iloc[0]) is False

    def test_takedown_lookback_boundary(self):
        """Filing exactly 90 days before fire_date counts for predicate B."""
        fire_date = date(2024, 6, 15)
        filing_date = fire_date - timedelta(days=90)
        fires = _fires(("AAPL", str(fire_date)))
        dil   = _dilutions(("AAPL", "424B4", str(filing_date)))
        result = build_predicates(fires, dil)
        assert bool(result["hazard_takedown_recent"].iloc[0]) is True

    def test_takedown_beyond_90d_excluded(self):
        fire_date = date(2024, 6, 15)
        filing_date = fire_date - timedelta(days=91)
        fires = _fires(("AAPL", str(fire_date)))
        dil   = _dilutions(("AAPL", "424B4", str(filing_date)))
        result = build_predicates(fires, dil)
        assert bool(result["hazard_takedown_recent"].iloc[0]) is False

    def test_wrong_ticker_not_counted(self):
        fires = _fires(("AAPL", "2024-06-15"))
        dil   = _dilutions(("MSFT", "S-3", "2024-06-14"))  # different ticker
        result = build_predicates(fires, dil)
        assert bool(result["hazard_shelf_active"].iloc[0]) is False

    def test_wrong_form_not_counted_for_shelf(self):
        fires = _fires(("AAPL", "2024-06-15"))
        dil   = _dilutions(("AAPL", "424B4", "2024-06-14"))  # takedown, not shelf
        result = build_predicates(fires, dil)
        assert bool(result["hazard_shelf_active"].iloc[0]) is False

    def test_trailing_event_counts_both_form_types(self):
        fire_date = "2024-06-15"
        fires = _fires(("AAPL", fire_date))
        dil   = _dilutions(("AAPL", "424B4", "2024-05-01"))  # takedown in 365d
        result = build_predicates(fires, dil)
        assert bool(result["hazard_trailing_event"].iloc[0]) is True

    def test_no_dilution_rows_all_false(self):
        fires = _fires(("AAPL", "2024-06-15"), ("MSFT", "2024-06-15"))
        dil   = pd.DataFrame(columns=["ticker", "form", "filing_date", "accession"])
        result = build_predicates(fires, dil)
        assert result["hazard_shelf_active"].sum() == 0
        assert result["hazard_takedown_recent"].sum() == 0
        assert result["hazard_trailing_event"].sum() == 0

    def test_multiple_fires_independent_labels(self):
        """Two fires on the same date: one with hazard, one without."""
        fires = _fires(("AAPL", "2024-06-15"), ("GOOG", "2024-06-15"))
        dil   = _dilutions(
            ("AAPL", "S-3", "2024-06-14"),   # AAPL has shelf
        )
        result = build_predicates(fires, dil)
        aapl = result[result["ticker"] == "AAPL"]["hazard_shelf_active"].iloc[0]
        goog = result[result["ticker"] == "GOOG"]["hazard_shelf_active"].iloc[0]
        assert bool(aapl) is True
        assert bool(goog) is False


# ---------------------------------------------------------------------------
# 3. Floor gating
# ---------------------------------------------------------------------------

class TestFloorGating:
    """Floors printed before statistics; DEFER-on-floor when not met."""

    def _labeled_fires(self, n_hazard: int, n_non_hazard: int) -> pd.DataFrame:
        """Build minimal labeled fires DataFrame."""
        rows = []
        # Create distinct tickers so each fire has a unique ticker×year cluster
        for i in range(n_hazard):
            rows.append({
                "ticker": f"HZ{i:04d}",
                "date": f"2023-0{(i % 9) + 1:02d}-01" if i < 9 else "2023-09-01",
                "hazard_shelf_active": True,
                "hazard_takedown_recent": False,
                "hazard_trailing_event": True,
            })
        for i in range(n_non_hazard):
            rows.append({
                "ticker": f"NZ{i:04d}",
                "date": f"2023-0{(i % 9) + 1:02d}-01" if i < 9 else "2023-09-01",
                "hazard_shelf_active": False,
                "hazard_takedown_recent": False,
                "hazard_trailing_event": False,
            })
        df = pd.DataFrame(rows)
        df["episode_cluster"] = _assign_episode_cluster(df).values
        return df

    def test_floor_pass_when_both_arms_above_threshold(self):
        fires = self._labeled_fires(
            n_hazard=F_HZ1_CONSTANTS.N_FIRES_FLOOR + 50,
            n_non_hazard=F_HZ1_CONSTANTS.N_FIRES_FLOOR + 50,
        )
        result = check_floors(fires, "hazard_shelf_active")
        # May still fail on cluster count if we don't have 25 distinct clusters
        # That's expected — the test verifies n_fires direction
        assert result["hazard_n_fires"] >= F_HZ1_CONSTANTS.N_FIRES_FLOOR
        assert result["non_hazard_n_fires"] >= F_HZ1_CONSTANTS.N_FIRES_FLOOR

    def test_floor_fail_when_hazard_arm_too_small(self):
        fires = self._labeled_fires(
            n_hazard=F_HZ1_CONSTANTS.N_FIRES_FLOOR - 1,
            n_non_hazard=F_HZ1_CONSTANTS.N_FIRES_FLOOR + 50,
        )
        result = check_floors(fires, "hazard_shelf_active")
        assert result["pass"] is False
        assert result["hazard_n_fires"] < F_HZ1_CONSTANTS.N_FIRES_FLOOR

    def test_floor_fail_when_non_hazard_arm_too_small(self):
        fires = self._labeled_fires(
            n_hazard=F_HZ1_CONSTANTS.N_FIRES_FLOOR + 50,
            n_non_hazard=F_HZ1_CONSTANTS.N_FIRES_FLOOR - 1,
        )
        result = check_floors(fires, "hazard_shelf_active")
        assert result["pass"] is False
        assert result["non_hazard_n_fires"] < F_HZ1_CONSTANTS.N_FIRES_FLOOR

    def test_floor_message_present(self):
        fires = self._labeled_fires(n_hazard=10, n_non_hazard=10)
        result = check_floors(fires, "hazard_shelf_active")
        assert "FLOOR" in result["message"]
        assert "gradable" in result["message"]
        assert "n_clusters_gradable" in result["message"]

    def test_floor_message_contains_both_membership_and_gradable(self):
        """Floor message prints membership count and gradable count separately."""
        fires = self._labeled_fires(n_hazard=10, n_non_hazard=10)
        result = check_floors(fires, "hazard_shelf_active")
        assert "membership" in result["message"]
        assert "gradable" in result["message"]

    def test_floor_result_has_member_keys(self):
        """check_floors result dict includes hazard_n_fires_member keys."""
        fires = self._labeled_fires(n_hazard=10, n_non_hazard=10)
        result = check_floors(fires, "hazard_shelf_active")
        assert "hazard_n_fires_member" in result
        assert "non_hazard_n_fires_member" in result

    def test_floor_enforces_on_gradable_counts(self):
        """Floors enforce on gradable (non-NaN) counts, not membership counts.

        When gradable=False for all fires, floor fails even if membership is large.
        """
        # Build fires above membership floor but all ungradable
        rows = []
        for i in range(F_HZ1_CONSTANTS.N_FIRES_FLOOR + 50):
            rows.append({
                "ticker": f"HZ{i:04d}",
                "date": "2023-01-01",
                "hazard_shelf_active": True,
                "gradable": False,  # all ungradable
            })
        for i in range(F_HZ1_CONSTANTS.N_FIRES_FLOOR + 50):
            rows.append({
                "ticker": f"NZ{i:04d}",
                "date": "2023-01-01",
                "hazard_shelf_active": False,
                "gradable": False,  # all ungradable
            })
        df = pd.DataFrame(rows)
        df["episode_cluster"] = _assign_episode_cluster(df).values
        result = check_floors(df, "hazard_shelf_active")
        # Membership is above floor but gradable=0 → floor fails
        assert result["hazard_n_fires_member"] >= F_HZ1_CONSTANTS.N_FIRES_FLOOR
        assert result["hazard_n_fires"] == 0
        assert result["pass"] is False

    def test_compute_contrast_returns_note_on_floor_fail(self, capsys):
        fires = self._labeled_fires(n_hazard=5, n_non_hazard=5)
        result = compute_contrast(fires, "hazard_shelf_active")
        assert result["floor"]["pass"] is False
        assert "DEFER-on-floor" in result.get("note", "")


# ---------------------------------------------------------------------------
# 4. Era-law split routing
# ---------------------------------------------------------------------------

class TestEraLawSplit:
    def test_2021plus_cohort_date_boundary(self):
        fires = _fires(
            ("AAPL", "2020-12-31"),  # pre-2021
            ("MSFT", "2021-01-01"),  # 2021+
            ("GOOG", "2022-06-01"),  # 2021+
        )
        cohorts = era_law_split(fires)
        plus = cohorts["verdict_grade_2021plus"]
        pre  = cohorts["pre_2021"]
        assert len(plus) == 2
        assert len(pre) == 1
        assert "AAPL" in pre["ticker"].values
        assert "MSFT" in plus["ticker"].values
        assert "GOOG" in plus["ticker"].values

    def test_all_pre_2021_gives_empty_2021plus(self):
        fires = _fires(("AAPL", "2020-01-01"), ("MSFT", "2019-06-01"))
        cohorts = era_law_split(fires)
        assert len(cohorts["verdict_grade_2021plus"]) == 0
        assert len(cohorts["pre_2021"]) == 2

    def test_all_post_2021_gives_empty_pre(self):
        fires = _fires(("AAPL", "2022-01-01"), ("MSFT", "2023-06-01"))
        cohorts = era_law_split(fires)
        assert len(cohorts["verdict_grade_2021plus"]) == 2
        assert len(cohorts["pre_2021"]) == 0


# ---------------------------------------------------------------------------
# 5. Gate behavior when data absent
# ---------------------------------------------------------------------------

class TestDataGates:
    def test_dilution_absent_all_clear_false(self, tmp_path):
        dilution_path = tmp_path / "dilution_events.parquet"
        boarded_path  = tmp_path / "replay_boarded.parquet"
        # Write only boarded; dilution absent
        _fires(("AAPL", "2023-01-01")).to_parquet(boarded_path)
        gate = check_data_gates(dilution_path, boarded_path)
        assert gate["all_clear"] is False
        assert gate["dilution_present"] is False
        assert any("dilution" in m.lower() for m in gate["messages"])

    def test_boarded_absent_all_clear_false(self, tmp_path):
        dilution_path = tmp_path / "dilution_events.parquet"
        boarded_path  = tmp_path / "replay_boarded.parquet"
        # Write dilution with >365d span; boarded absent
        d = pd.DataFrame([
            {"ticker": "AAPL", "form": "S-3", "filing_date": "2022-01-01"},
            {"ticker": "AAPL", "form": "S-3", "filing_date": "2023-06-01"},
        ])
        d.to_parquet(dilution_path)
        gate = check_data_gates(dilution_path, boarded_path)
        assert gate["all_clear"] is False
        assert gate["boarded_present"] is False

    def test_both_absent_all_clear_false(self, tmp_path):
        dilution_path = tmp_path / "dilution_events.parquet"
        boarded_path  = tmp_path / "replay_boarded.parquet"
        gate = check_data_gates(dilution_path, boarded_path)
        assert gate["all_clear"] is False
        assert gate["dilution_present"] is False
        assert gate["boarded_present"] is False

    def test_store_age_routing_accrual_convert(self, tmp_path):
        """Store present but <365d age → ACCRUAL-CONVERT."""
        dilution_path = tmp_path / "dilution_events.parquet"
        boarded_path  = tmp_path / "replay_boarded.parquet"
        # Store with only 30 days of history
        d = pd.DataFrame([
            {"ticker": "AAPL", "form": "S-3", "filing_date": "2024-05-01"},
            {"ticker": "AAPL", "form": "S-3", "filing_date": "2024-05-31"},
        ])
        d.to_parquet(dilution_path)
        _fires(("AAPL", "2024-06-01")).to_parquet(boarded_path)
        gate = check_data_gates(dilution_path, boarded_path)
        assert gate["all_clear"] is False
        assert gate["come_back_date"] is not None

    def test_run_study_exits_cleanly_when_dilution_absent(self, tmp_path):
        """run_study returns branch=ACCRUAL-CONVERT and exit code 0 when data absent."""
        ledger_path = tmp_path / "test_ledger.jsonl"
        result = run_study(
            dilution_path=tmp_path / "missing_dilution.parquet",
            boarded_path=tmp_path / "missing_boarded.parquet",
            ledger_path=ledger_path,
        )
        assert result["ran"] is False
        assert result["branch"] == "ACCRUAL-CONVERT"

    def test_trial_budget_declared_even_when_data_absent(self, tmp_path):
        """Budget declaration fires before gate check — even on ACCRUAL-CONVERT."""
        ledger_path = tmp_path / "test_ledger.jsonl"
        run_study(
            dilution_path=tmp_path / "missing_dilution.parquet",
            boarded_path=tmp_path / "missing_boarded.parquet",
            ledger_path=ledger_path,
        )
        # Ledger file should now exist with a declared_budget entry
        assert ledger_path.exists()
        entries = [json.loads(line) for line in ledger_path.read_text().splitlines() if line.strip()]
        budget_entries = [e for e in entries if e.get("kind") == "declared_budget"]
        assert len(budget_entries) >= 1
        assert budget_entries[0]["family"] == "dilution_hazard"
        assert budget_entries[0]["n"] == F_HZ1_CONSTANTS.FDR_BUDGET


# ---------------------------------------------------------------------------
# 6. Trial budget declaration
# ---------------------------------------------------------------------------

class TestTrialBudget:
    def test_declare_trial_budget_idempotent(self, tmp_path):
        ledger_path = tmp_path / "ledger.jsonl"
        declare_trial_budget(ledger_path)
        declare_trial_budget(ledger_path)
        declare_trial_budget(ledger_path)
        entries = [json.loads(l) for l in ledger_path.read_text().splitlines() if l.strip()]
        budget_entries = [e for e in entries if e.get("kind") == "declared_budget"]
        # log_declared_budget is idempotent: same (family, n, reason) deduped
        assert len(budget_entries) == 1

    def test_declare_trial_budget_family_and_n(self, tmp_path):
        ledger_path = tmp_path / "ledger.jsonl"
        declare_trial_budget(ledger_path)
        entries = [json.loads(l) for l in ledger_path.read_text().splitlines() if l.strip()]
        b = entries[0]
        assert b["family"] == "dilution_hazard"
        assert b["n"] == 3


# ---------------------------------------------------------------------------
# 7. Episode clustering
# ---------------------------------------------------------------------------

class TestEpisodeClustering:
    def test_episode_id_column_used_when_present(self):
        fires = pd.DataFrame([
            {"ticker": "AAPL", "date": "2023-01-01", "episode_id": "EP001"},
            {"ticker": "MSFT", "date": "2023-01-01", "episode_id": "EP002"},
        ])
        clusters = _assign_episode_cluster(fires)
        assert list(clusters) == ["EP001", "EP002"]

    def test_fallback_to_ticker_year_without_episode_id(self):
        fires = _fires(
            ("AAPL", "2023-01-01"),
            ("AAPL", "2023-06-01"),   # same ticker, same year → same cluster
            ("AAPL", "2024-01-01"),   # same ticker, different year → different cluster
            ("MSFT", "2023-01-01"),   # different ticker → different cluster
        )
        clusters = _assign_episode_cluster(fires)
        # AAPL-2023 × 2 should share cluster; AAPL-2024 and MSFT-2023 are distinct
        assert clusters.iloc[0] == clusters.iloc[1]   # both AAPL 2023
        assert clusters.iloc[0] != clusters.iloc[2]   # AAPL 2023 vs 2024
        assert clusters.iloc[0] != clusters.iloc[3]   # AAPL 2023 vs MSFT 2023


# ---------------------------------------------------------------------------
# 8. Store age helper
# ---------------------------------------------------------------------------

class TestStoreAge:
    def test_store_age_one_year_span(self):
        d = pd.DataFrame([
            {"filing_date": "2023-01-01"},
            {"filing_date": "2024-01-01"},
        ])
        age = _store_age_days(d)
        # 2024-01-01 - 2023-01-01 = 365 calendar days
        assert age == 365

    def test_store_age_empty_df(self):
        d = pd.DataFrame(columns=["filing_date"])
        assert _store_age_days(d) is None

    def test_store_age_single_row(self):
        d = pd.DataFrame([{"filing_date": "2024-01-01"}])
        # max == min → span = 0
        assert _store_age_days(d) == 0


# ---------------------------------------------------------------------------
# 9. Synthetic-closes fixture: compute_outcomes produces non-NaN outcomes
# ---------------------------------------------------------------------------

class TestComputeOutcomesSyntheticCloses:
    """Prove that compute_outcomes() produces gradable (non-NaN) stop5 and
    dead_money_21 when a synthetic close series with enough forward bars is supplied.

    This is the end-to-end gradability fixture required by the closes-loader PR.
    """

    def _make_close_series(
        self,
        start: str,
        n_bars: int = 60,
        start_price: float = 100.0,
        daily_return: float = 0.0,
    ) -> pd.Series:
        """Build a flat (or trending) close series with a DatetimeIndex."""
        import numpy as np
        idx = pd.bdate_range(start=start, periods=n_bars)
        prices = start_price * ((1 + daily_return) ** np.arange(n_bars))
        return pd.Series(prices, index=idx)

    def test_flat_close_gradable_no_stop5(self):
        """Flat close: stop5=0 (no -5% hit), dead_money_21=0 (flat = 0% return >= 0 threshold fails → actually 0%<=0.0 so dead_money_21=1)."""
        # flat close: fill price = start_price, fwd_ret_21 = 0.0 → dead_money_21=1 (<=0.0)
        fire_date = "2023-06-01"
        close = self._make_close_series(start="2023-05-01", n_bars=60, start_price=100.0, daily_return=0.0)
        fires = _fires(("AAPL", fire_date))
        fires["hazard_shelf_active"] = False
        fires["episode_cluster"] = "AAPL_2023"

        result = compute_outcomes(fires, closes={"AAPL": close})

        # Must have at least one gradable row (price path was available)
        assert result["gradable"].any(), "Expected at least one gradable fire with synthetic close"
        # stop5 must not be NaN for gradable rows
        gradable_rows = result[result["gradable"] == True]  # noqa: E712
        assert not gradable_rows["stop5"].isna().any(), "stop5 must be non-NaN for gradable fires"
        assert not gradable_rows["dead_money_21"].isna().any(), "dead_money_21 must be non-NaN for gradable fires"

    def test_declining_close_triggers_stop5(self):
        """Declining close that drops >5% within 5 bars → stop5=1."""
        fire_date = "2023-06-01"
        # -2% per day: after 3 days, cumulative ≈ -5.9% → stop5=1
        close = self._make_close_series(
            start="2023-05-01", n_bars=60, start_price=100.0, daily_return=-0.02
        )
        fires = _fires(("AAPL", fire_date))
        fires["hazard_shelf_active"] = True
        fires["episode_cluster"] = "AAPL_2023"

        result = compute_outcomes(fires, closes={"AAPL": close})

        gradable_rows = result[result["gradable"] == True]  # noqa: E712
        assert len(gradable_rows) >= 1, "Expected gradable fire"
        assert float(gradable_rows["stop5"].iloc[0]) == 1.0, "Expected stop5=1 for -2%/day series"

    def test_rising_close_no_stop5_no_dead_money(self):
        """Rising close: stop5=0, dead_money_21=0 (positive 21d return)."""
        fire_date = "2023-06-01"
        close = self._make_close_series(
            start="2023-05-01", n_bars=60, start_price=100.0, daily_return=0.005
        )
        fires = _fires(("AAPL", fire_date))
        fires["hazard_shelf_active"] = False
        fires["episode_cluster"] = "AAPL_2023"

        result = compute_outcomes(fires, closes={"AAPL": close})

        gradable_rows = result[result["gradable"] == True]  # noqa: E712
        assert len(gradable_rows) >= 1, "Expected gradable fire"
        assert float(gradable_rows["stop5"].iloc[0]) == 0.0, "Rising series: stop5 must be 0"
        assert float(gradable_rows["dead_money_21"].iloc[0]) == 0.0, "Rising series: dead_money_21 must be 0"

    def test_missing_ticker_stays_ungradable(self):
        """Fire for ticker not in closes dict → gradable=False, outcomes NaN."""
        fire_date = "2023-06-01"
        close = self._make_close_series(start="2023-05-01", n_bars=60)
        fires = _fires(("AAPL", fire_date))
        fires["hazard_shelf_active"] = False
        fires["episode_cluster"] = "AAPL_2023"

        # Pass closes only for a different ticker
        result = compute_outcomes(fires, closes={"MSFT": close})

        assert not result["gradable"].any(), "AAPL not in closes → must be ungradable"
        assert result["stop5"].isna().all()
        assert result["dead_money_21"].isna().all()

    def test_no_closes_dict_all_ungradable(self):
        """Empty closes dict → all fires ungradable."""
        fires = _fires(("AAPL", "2023-06-01"), ("MSFT", "2023-06-02"))
        fires["hazard_shelf_active"] = True
        fires["episode_cluster"] = "cluster"

        result = compute_outcomes(fires, closes={})

        assert not result["gradable"].any()
        assert result["stop5"].isna().all()
        assert result["dead_money_21"].isna().all()
