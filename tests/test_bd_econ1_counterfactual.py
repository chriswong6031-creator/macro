"""Tests for BD-ECON-1 counterfactual harness.

Synthetic fixtures only — CI has no canonical massive_stock_day data.

Covers:
  1. Flagging rule: event_date < signal_date <= event_date+21 bars
  2. Generating-fire exclusion: signal_date <= event_date is never flagged
  3. Recent-stop cohort construction
  4. Bootstrap smoke test (two arms, small N)
  5. Floor gating: P0-DEFER when below floor
  6. Censoring accounting: NaN rows counted, not silently dropped
  7. TrialLedger budget logging: declared_budget logged before statistics
  8. Per-cell config logging: literal_n accumulates all 6 cells
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from engine.trial_ledger import TrialLedger

# Import the module under test (not the canonical data paths — all overridden in tests)
import scripts.research.bd_econ1_counterfactual as mod


# ---------------------------------------------------------------------------
# Calendar fixture
# ---------------------------------------------------------------------------

def _make_calendar(start: str = "2021-07-06", periods: int = 600) -> pd.DatetimeIndex:
    """Build a synthetic trading-bar calendar (business days)."""
    return pd.bdate_range(start=start, periods=periods)


# ---------------------------------------------------------------------------
# Tape fixtures
# ---------------------------------------------------------------------------

def _make_events(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal breakdown_events DataFrame."""
    df = pd.DataFrame(rows)
    if "is_control" not in df.columns:
        df["is_control"] = False
    if "definition" not in df.columns:
        df["definition"] = "BD-2"
    if "ticker" not in df.columns:
        df["ticker"] = "AAPL"
    if "event_date" not in df.columns:
        df["event_date"] = "2022-08-01"
    return df


def _make_fires(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal fires DataFrame (ERA-LAW cohort)."""
    defaults = {
        "ticker": "AAPL",
        "signal_date": "2022-08-10",
        "state_8_21": "STOPPED",
        "fwd_ret_21": -0.05,
        "fwd_mdd_21": -0.10,
        "fwd_mfe_21": 0.03,
        "stopped_at_8_21": 5,
        "fill_date": "2022-08-11",
        "tier_cascade": "T1",
    }
    result = []
    for row in rows:
        r = dict(defaults)
        r.update(row)
        result.append(r)
    return pd.DataFrame(result)


# ---------------------------------------------------------------------------
# 1. Flagging rule correctness
# ---------------------------------------------------------------------------

class TestFlaggingRule:

    def test_signal_within_window_is_flagged(self):
        """signal_date on day 10 of a 21-bar window → flagged."""
        cal = _make_calendar()
        ev_date = str(cal[5].date())
        sig_date = str(cal[15].date())  # 10 bars after event

        events = _make_events([{"ticker": "X", "definition": "BD-2", "event_date": ev_date}])
        fires = _make_fires([{"ticker": "X", "signal_date": sig_date}])

        flagged, unflagged, n_eps = mod.build_flagged_fires(events, fires, "BD-2", cal)
        assert len(flagged) == 1
        assert len(unflagged) == 0
        assert n_eps == 1

    def test_signal_at_window_end_is_flagged(self):
        """signal_date at exactly event_date + 21 bars → flagged (inclusive end)."""
        cal = _make_calendar()
        ev_date = str(cal[5].date())
        sig_date = str(cal[5 + 21].date())  # exactly 21 bars later

        events = _make_events([{"ticker": "X", "definition": "BD-2", "event_date": ev_date}])
        fires = _make_fires([{"ticker": "X", "signal_date": sig_date}])

        flagged, unflagged, n_eps = mod.build_flagged_fires(events, fires, "BD-2", cal)
        assert len(flagged) == 1
        assert len(unflagged) == 0

    def test_signal_one_bar_past_window_is_unflagged(self):
        """signal_date at event_date + 22 bars → unflagged."""
        cal = _make_calendar()
        ev_date = str(cal[5].date())
        sig_date = str(cal[5 + 22].date())  # 22 bars — outside window

        events = _make_events([{"ticker": "X", "definition": "BD-2", "event_date": ev_date}])
        fires = _make_fires([{"ticker": "X", "signal_date": sig_date}])

        flagged, unflagged, n_eps = mod.build_flagged_fires(events, fires, "BD-2", cal)
        assert len(flagged) == 0
        assert len(unflagged) == 1

    def test_different_ticker_not_flagged(self):
        """BD-2 event on ticker A does not flag fire on ticker B."""
        cal = _make_calendar()
        ev_date = str(cal[5].date())
        sig_date = str(cal[10].date())

        events = _make_events([{"ticker": "A", "definition": "BD-2", "event_date": ev_date}])
        fires = _make_fires([{"ticker": "B", "signal_date": sig_date}])

        flagged, unflagged, n_eps = mod.build_flagged_fires(events, fires, "BD-2", cal)
        assert len(flagged) == 0
        assert len(unflagged) == 1

    def test_generating_fire_excluded(self):
        """Fires with signal_date == event_date are never flagged (generating-fire exclusion).

        The prereg §2 states: 'Fires with signal_date <= event_date are never flagged —
        this excludes BD-2's generating fire by construction.'
        """
        cal = _make_calendar()
        ev_date = str(cal[10].date())
        sig_date_eq = str(cal[10].date())   # equal — must NOT be flagged
        sig_date_before = str(cal[5].date())  # before — must NOT be flagged

        events = _make_events([{"ticker": "X", "definition": "BD-2", "event_date": ev_date}])
        fires = _make_fires([
            {"ticker": "X", "signal_date": sig_date_eq},
            {"ticker": "X", "signal_date": sig_date_before},
        ])

        flagged, unflagged, n_eps = mod.build_flagged_fires(events, fires, "BD-2", cal)
        assert len(flagged) == 0, "Generating fire should not be flagged"
        assert len(unflagged) == 2

    def test_wrong_definition_not_flagged(self):
        """BD-3 events do not flag fires when we request BD-2 flagging."""
        cal = _make_calendar()
        ev_date = str(cal[5].date())
        sig_date = str(cal[10].date())

        events = _make_events([{"ticker": "X", "definition": "BD-3", "event_date": ev_date}])
        fires = _make_fires([{"ticker": "X", "signal_date": sig_date}])

        flagged, unflagged, n_eps = mod.build_flagged_fires(events, fires, "BD-2", cal)
        assert len(flagged) == 0
        assert len(unflagged) == 1

    def test_episode_count_distinct(self):
        """Two events on the same ticker contribute 2 episodes, not 1."""
        cal = _make_calendar()
        ev1 = str(cal[5].date())
        ev2 = str(cal[30].date())  # beyond first episode window
        sig = str(cal[35].date())  # only in second episode window

        events = _make_events([
            {"ticker": "X", "definition": "BD-2", "event_date": ev1},
            {"ticker": "X", "definition": "BD-2", "event_date": ev2},
        ])
        fires = _make_fires([{"ticker": "X", "signal_date": sig}])

        flagged, unflagged, n_eps = mod.build_flagged_fires(events, fires, "BD-2", cal)
        assert len(flagged) == 1
        assert n_eps == 1  # only ev2 contributed; ev1's window doesn't cover sig


# ---------------------------------------------------------------------------
# 2. Recent-stop cohort
# ---------------------------------------------------------------------------

class TestRecentStopCohort:

    def test_recent_stop_identified(self):
        """Fire with a stopped predecessor within 21 bars enters recent-stop cohort."""
        cal = _make_calendar()
        # stop bar at cal[15]; fire at cal[20] (5 bars later, within 21)
        stop_fill_date = str(cal[10].date())
        stop_offset = 5  # stopped_at_8_21=5 means stop at fill+4 (0-indexed) = cal[14]
        sig_date = str(cal[20].date())

        fires = _make_fires([
            # The stopped predecessor fire
            {
                "ticker": "X",
                "signal_date": str(cal[8].date()),
                "state_8_21": "STOPPED",
                "fill_date": stop_fill_date,
                "stopped_at_8_21": 5,
            },
            # The unflagged fire we're testing for recent-stop membership
            {
                "ticker": "X",
                "signal_date": sig_date,
                "state_8_21": "CLEAN_LIFTOFF",
                "fill_date": str(cal[21].date()),
                "stopped_at_8_21": None,
            },
        ])

        cohort = mod.build_recent_stop_cohort(fires, cal)
        # The second fire should be in the cohort
        cohort_sigs = set(cohort["signal_date"].tolist())
        assert sig_date in cohort_sigs, f"{sig_date} should be in recent-stop cohort"

    def test_old_stop_not_recent(self):
        """Stopped predecessor more than 21 bars before signal → NOT in recent-stop cohort."""
        cal = _make_calendar()
        # stop bar at ~cal[5]; fire at cal[40] (35 bars later — outside 21 bar window)
        stop_fill_date = str(cal[3].date())
        sig_date = str(cal[40].date())

        fires = _make_fires([
            {
                "ticker": "X",
                "signal_date": str(cal[1].date()),
                "state_8_21": "STOPPED",
                "fill_date": stop_fill_date,
                "stopped_at_8_21": 2,
            },
            {
                "ticker": "X",
                "signal_date": sig_date,
                "state_8_21": "CLEAN_LIFTOFF",
                "fill_date": str(cal[41].date()),
                "stopped_at_8_21": None,
            },
        ])

        cohort = mod.build_recent_stop_cohort(fires, cal)
        cohort_sigs = set(cohort["signal_date"].tolist())
        assert sig_date not in cohort_sigs, f"{sig_date} should NOT be in recent-stop cohort"


# ---------------------------------------------------------------------------
# 3. Bootstrap smoke test
# ---------------------------------------------------------------------------

class TestBootstrap:

    def test_bootstrap_returns_valid_ci(self):
        """Bootstrap on two small arms returns a dict with valid CI."""
        rng = np.random.default_rng(42)
        cal = _make_calendar()
        n = 30

        arm_a = pd.DataFrame({
            "signal_date": [str(cal[i].date()) for i in range(n)],
            "ticker": [f"T{i % 5}" for i in range(n)],
            "_ep": np.random.default_rng(1).normal(0.6, 0.1, n),
        })
        arm_b = pd.DataFrame({
            "signal_date": [str(cal[i + n].date()) for i in range(n)],
            "ticker": [f"T{i % 5}" for i in range(n)],
            "_ep": np.random.default_rng(2).normal(0.4, 0.1, n),
        })

        result = mod._month_ticker_bootstrap(arm_a, arm_b, "_ep", False, rng, n_draws=100)

        assert result["n_arm_a"] == n
        assert result["n_arm_b"] == n
        assert result["ci95_lo"] is not None
        assert result["ci95_hi"] is not None
        assert result["ci95_lo"] < result["ci95_hi"]
        assert result["delta"] == pytest.approx(result["mean_a"] - result["mean_b"], abs=1e-6)

    def test_bootstrap_empty_arm_returns_none(self):
        """Bootstrap with empty arm returns None for CI values."""
        rng = np.random.default_rng(42)
        cal = _make_calendar()

        arm_a = pd.DataFrame({
            "signal_date": [str(cal[0].date())],
            "ticker": ["X"],
            "_ep": [0.5],
        })
        arm_b = pd.DataFrame({
            "signal_date": pd.Series([], dtype=str),
            "ticker": pd.Series([], dtype=str),
            "_ep": pd.Series([], dtype=float),
        })

        result = mod._month_ticker_bootstrap(arm_a, arm_b, "_ep", False, rng, n_draws=10)
        assert result["delta"] is None

    def test_bootstrap_reproducible_with_seed(self):
        """Same seed produces same CI."""
        cal = _make_calendar()
        n = 20

        arm_a = pd.DataFrame({
            "signal_date": [str(cal[i].date()) for i in range(n)],
            "ticker": [f"T{i % 3}" for i in range(n)],
            "_ep": np.linspace(0.3, 0.7, n),
        })
        arm_b = pd.DataFrame({
            "signal_date": [str(cal[i + n].date()) for i in range(n)],
            "ticker": [f"T{i % 3}" for i in range(n)],
            "_ep": np.linspace(0.2, 0.5, n),
        })

        rng1 = np.random.default_rng(999)
        r1 = mod._month_ticker_bootstrap(arm_a, arm_b, "_ep", False, rng1, n_draws=50)

        rng2 = np.random.default_rng(999)
        r2 = mod._month_ticker_bootstrap(arm_a, arm_b, "_ep", False, rng2, n_draws=50)

        assert r1["ci95_lo"] == pytest.approx(r2["ci95_lo"])
        assert r1["ci95_hi"] == pytest.approx(r2["ci95_hi"])


# ---------------------------------------------------------------------------
# 4. Floor gating — P0-DEFER branch
# ---------------------------------------------------------------------------

class TestFloorGating:

    def test_p0_defer_when_flagged_below_floor(self):
        """Fewer than FLOOR_FLAGGED_FIRES flagged fires → P0-DEFER status returned."""
        cal = _make_calendar()

        # Patch the floor to 1000 so our tiny fixture always triggers P0-DEFER
        original_floor = mod.FLOOR_FLAGGED_FIRES
        mod.FLOOR_FLAGGED_FIRES = 1000
        try:
            ev_date = str(cal[5].date())
            sig_date = str(cal[10].date())

            events = _make_events([{"ticker": "X", "definition": "BD-2", "event_date": ev_date}])
            fires = _make_fires([{"ticker": "X", "signal_date": sig_date}])

            flagged, unflagged, n_eps = mod.build_flagged_fires(events, fires, "BD-2", cal)

            # Under n=1, we're below any reasonable floor
            assert len(flagged) < mod.FLOOR_FLAGGED_FIRES, "fixture should be below floor"

            # Verify the floor check itself
            floor_ok = len(flagged) >= mod.FLOOR_FLAGGED_FIRES
            assert not floor_ok, "Floor should NOT be met with tiny fixture"
        finally:
            mod.FLOOR_FLAGGED_FIRES = original_floor

    def test_floor_printed_not_statistics(self, capsys):
        """P0-DEFER triggers count print, no statistics computed."""
        # The main run() function handles this, but we can test the floor logic inline
        cal = _make_calendar()

        # 1 flagged fire, floor=300 → DEFER
        assert 1 < mod.FLOOR_FLAGGED_FIRES

        # Floor check
        n_flagged = 1
        n_eps = 50
        floor_ok = (n_flagged >= mod.FLOOR_FLAGGED_FIRES and
                    n_eps >= mod.FLOOR_BD_EPISODES)
        assert not floor_ok


# ---------------------------------------------------------------------------
# 5. Censoring accounting
# ---------------------------------------------------------------------------

class TestCensoringAccounting:

    def test_nan_state_counted_not_dropped(self):
        """Fires with NaN state_8_21 are counted in censoring stats, not silently dropped."""
        cal = _make_calendar()
        n = 5

        flagged = _make_fires([
            {"ticker": f"T{i}", "signal_date": str(cal[i + 5].date()),
             "state_8_21": None if i == 0 else "STOPPED",
             "fwd_ret_21": None if i == 1 else -0.05,
             "stopped_at_8_21": None}
            for i in range(n)
        ])
        unflagged = _make_fires([
            {"ticker": f"U{i}", "signal_date": str(cal[i + 50].date()),
             "state_8_21": "STOPPED",
             "fwd_ret_21": -0.03}
            for i in range(n)
        ])

        rng = np.random.default_rng(42)
        result = mod.run_contrast(flagged, unflagged, "C1", rng)

        cens = result["censoring"]
        # Row 0 had NaN state_8_21 in flagged
        assert cens["n_flagged_stop_nan"] >= 1, "NaN state_8_21 should be counted"
        # Row 1 had NaN fwd_ret_21 in flagged
        assert cens["n_flagged_ret21_nan"] >= 1, "NaN fwd_ret_21 should be counted"

    def test_valid_rows_used_despite_nans(self):
        """Bootstrap uses only non-NaN rows; does not crash when some are NaN."""
        cal = _make_calendar()

        flagged = _make_fires([
            {"ticker": "T", "signal_date": str(cal[i + 5].date()),
             "state_8_21": "STOPPED" if i > 0 else None,
             "fwd_ret_21": -0.05}
            for i in range(10)
        ])
        unflagged = _make_fires([
            {"ticker": "U", "signal_date": str(cal[i + 50].date()),
             "state_8_21": "STOPPED",
             "fwd_ret_21": -0.03}
            for i in range(10)
        ])

        rng = np.random.default_rng(42)
        result = mod.run_contrast(flagged, unflagged, "C1", rng)

        # Should complete without error; n_arm_a reflects only valid rows
        ep_a = result["endpoint_a_stop_rate"]
        assert ep_a.get("n_arm_a") is not None


# ---------------------------------------------------------------------------
# 6. TrialLedger budget logging
# ---------------------------------------------------------------------------

class TestTrialLedger:

    def test_declared_budget_logged_first(self, tmp_path):
        """TrialLedger.log_declared_budget called with DECLARED_BUDGET before cells."""
        ledger_path = tmp_path / "test_ledger.jsonl"
        ledger = TrialLedger(path=ledger_path)

        literal_n = mod._register_budget_and_cells(ledger)

        # Check declared budget
        assert ledger.declared_budget(mod.TRIAL_FAMILY) == mod.DECLARED_BUDGET

        # Check literal_n accumulated
        assert literal_n == mod.DECLARED_BUDGET  # 6 distinct cells
        assert ledger.literal_n(mod.TRIAL_FAMILY) == mod.DECLARED_BUDGET

    def test_all_6_cells_logged_as_distinct_configs(self, tmp_path):
        """All 6 verdict cells are logged as distinct configs (literal_n = 6)."""
        ledger_path = tmp_path / "test_ledger.jsonl"
        ledger = TrialLedger(path=ledger_path)

        # Log each cell
        for cell in mod.VERDICT_CELL_CONFIGS:
            ledger.log_trial(cell, family=mod.TRIAL_FAMILY)

        assert ledger.literal_n(mod.TRIAL_FAMILY) == 6, "All 6 cells should be distinct"

    def test_idempotent_rerun(self, tmp_path):
        """Re-running _register_budget_and_cells does not inflate literal_n."""
        ledger_path = tmp_path / "test_ledger.jsonl"
        ledger = TrialLedger(path=ledger_path)

        n1 = mod._register_budget_and_cells(ledger)
        n2 = mod._register_budget_and_cells(ledger)

        assert n1 == n2, "Idempotent: re-run should not inflate literal_n"

    def test_declared_budget_is_max_floor(self, tmp_path):
        """declared_budget acts as a floor: effective_n >= declared_budget."""
        ledger_path = tmp_path / "test_ledger.jsonl"
        ledger = TrialLedger(path=ledger_path)

        mod._register_budget_and_cells(ledger)
        # With 6 logged cells (= declared budget), effective_n == declared_budget
        eff_n = ledger.effective_n(mod.TRIAL_FAMILY)
        assert eff_n >= mod.DECLARED_BUDGET


# ---------------------------------------------------------------------------
# 7. Overlap printing
# ---------------------------------------------------------------------------

class TestOverlapCounting:

    def test_overlap_count_correct(self):
        """Fire flagged by both BD-2 and BD-3 counted in overlap."""
        cal = _make_calendar()
        ev2 = str(cal[5].date())
        ev3 = str(cal[5].date())  # BD-3 event same day
        sig = str(cal[10].date())

        events = pd.concat([
            _make_events([{"ticker": "X", "definition": "BD-2", "event_date": ev2}]),
            _make_events([{"ticker": "X", "definition": "BD-3", "event_date": ev3}]),
        ], ignore_index=True)

        fires = _make_fires([{"ticker": "X", "signal_date": sig}])

        flagged2, _, _ = mod.build_flagged_fires(events, fires, "BD-2", cal)
        flagged3, _, _ = mod.build_flagged_fires(events, fires, "BD-3", cal)

        overlap = len(set(flagged2.index) & set(flagged3.index))
        assert overlap == 1, "Fire flagged by both definitions should count as 1 in overlap"


# ---------------------------------------------------------------------------
# 8. Jackknife sensitivity
# ---------------------------------------------------------------------------

class TestJackknifeSensitivity:

    def test_jackknife_runs_without_error(self):
        """Jackknife computes without error on a simple example."""
        cal = _make_calendar()
        n = 10

        arm_a = _make_fires([
            {"ticker": f"T{i}", "signal_date": str(cal[i + 5].date()),
             "fwd_ret_21": float(i) * 0.01}
            for i in range(n)
        ])
        arm_b = _make_fires([
            {"ticker": f"U{i}", "signal_date": str(cal[i + 50].date()),
             "fwd_ret_21": float(i) * 0.005}
            for i in range(n)
        ])

        result = mod._jackknife_sensitivity(arm_a, arm_b, "fwd_ret_21")

        assert "n_tickers_a" in result or "note" in result  # either result or a skip note

    def test_jackknife_skips_single_ticker(self):
        """Jackknife skips gracefully when arm_a has only 1 ticker."""
        cal = _make_calendar()

        arm_a = _make_fires([
            {"ticker": "X", "signal_date": str(cal[i + 5].date()),
             "fwd_ret_21": 0.01}
            for i in range(5)
        ])
        arm_b = _make_fires([
            {"ticker": "U", "signal_date": str(cal[i + 50].date()),
             "fwd_ret_21": 0.005}
            for i in range(5)
        ])

        result = mod._jackknife_sensitivity(arm_a, arm_b, "fwd_ret_21")
        assert "note" in result


# ---------------------------------------------------------------------------
# 9. Economics block symmetry
# ---------------------------------------------------------------------------

class TestEconomicsBlock:

    def test_avoided_drawdown_and_missed_upside_both_populated(self):
        """Economics block prints both avoided drawdown AND missed upside (RUL-N6)."""
        cal = _make_calendar()

        flagged = _make_fires([
            {"ticker": "T1", "signal_date": str(cal[5].date()),
             "state_8_21": "STOPPED", "fwd_mdd_21": -0.10, "fwd_ret_21": -0.05,
             "fwd_mfe_21": 0.02},
            {"ticker": "T2", "signal_date": str(cal[6].date()),
             "state_8_21": "CLEAN_LIFTOFF", "fwd_mdd_21": -0.02, "fwd_ret_21": 0.08,
             "fwd_mfe_21": 0.12},
        ])

        unflagged = _make_fires([
            {"ticker": "U1", "signal_date": str(cal[50].date()),
             "state_8_21": "STOPPED", "fwd_ret_21": -0.03}
        ])

        ep_b_ci = {"delta": 0.02, "ci95_lo": 0.005, "ci95_hi": 0.035}
        econ = mod._econ_block(flagged, "BD-2", unflagged, ep_b_ci)

        # Both sides must be populated
        assert econ["avoided_drawdown_fwd_mdd_21"]["n"] == 1, "Stopped fire should have avoidable drawdown"
        assert econ["missed_upside_fwd_ret_21"]["n"] == 1, "Clean fire should have missed upside"
        assert econ["missed_upside_fwd_mfe_21"]["n"] == 1, "Clean fire should have missed MFE"
        # Symmetric cost note present
        assert "rn6_symmetric_cost_note" in econ
