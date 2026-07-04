"""Hermetic tests for engine/oracle/memory.py — Oracle O3 Pattern Memory.

ALL fixtures are synthetic (no network, no real data files).

Test inventory
--------------
(a) twin_analogue — planted identical twin episode → top-1 analogue returned.
    A second episode with identical feature vector and RS trajectory should be
    the closest match. Test FAILS if distance is not minimised for the twin.

(b) leakage_guard — an episode whose outcome window overlaps the query's onset
    is EXCLUDED from analogues even if it is the closest match by feature
    distance.  This test is DESIGNED TO FAIL on an implementation that does
    not enforce the eligibility filter (i.e., it tests that the filter exists
    and is enforced before distance sorting, not after).
    Specifically: plant a "perfect" analogue with onset_date 10 sessions before
    the query → it is within the 63-session leakage buffer → must NOT appear
    in results even though it is closest. Test fails if it appears.

(c) base_rate_direction_sign — direction-adjustment convention: OUT episode
    with negative forward RS should produce a POSITIVE direction-adjusted mean
    (negative × −1 = positive).  IN episode with positive forward RS should
    produce a POSITIVE direction-adjusted mean.  Test FAILS if the sign is
    wrong in either direction.

(d) thin_cell_flag — a cell with n < 20 observations must carry thin=True;
    a cell with n >= 20 must carry thin=False.  Test FAILS if thin is not set.

(e) dtw_sanity — identical trajectories → DTW distance = 0; reversed
    trajectory > shifted trajectory.  Tests the _dtw_distance function
    directly.  Fails if the DTW implementation is broken.

(f) no_same_direction_cross — find_analogues must only return episodes with
    the same direction as the query (direction filter).  Test FAILS if an
    opposite-direction episode sneaks into results.

(g) leakage_boundary — an analogue at EXACTLY onset + leakage_buffer sessions
    is EXCLUDED; one at onset + leakage_buffer + 1 sessions IS included.
    Tests the ≤ vs < boundary in the eligibility filter.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.oracle.memory import (
    MEMORY_CFG,
    _dtw_distance,
    _direction_sign,
    build_base_rates,
    find_analogues,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_trading_dates(n: int, start: str = "2020-01-02") -> pd.DatetimeIndex:
    return pd.bdate_range(start, periods=n, name="date")


def _make_panel(nodes_and_dates: dict[str, list[float]]) -> pd.DataFrame:
    """Build a MultiIndex (node, date) panel with an 'rs' column."""
    frames = []
    for node, rs_values in nodes_and_dates.items():
        n = len(rs_values)
        dates = _make_trading_dates(n)
        idx = pd.MultiIndex.from_arrays(
            [np.full(n, node), dates], names=["node", "date"]
        )
        frames.append(pd.DataFrame({"rs": rs_values}, index=idx))
    return pd.concat(frames).sort_index()


def _make_episodes(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal episodes DataFrame from a list of row dicts."""
    defaults = {
        "episode_id": "?",
        "node": "TESTNODE",
        "direction": "in",
        "onset_date": pd.Timestamp("2020-01-01"),
        "confirmed_date": pd.Timestamp("2020-01-15"),
        "undeniable_date": None,
        "exhausted_date": None,
        "duration": 20,
        "peak_accel_z": 1.5,
        "breadth_at_onset": 0.6,
        "cohesion_at_onset": 0.4,
        "cohesion_chg_at_onset": 0.08,
        "regime_vix_pctile": 0.4,
        "regime_tlt_sign": -1,
        "regime_spy_above_200d": 1.0,
        "two_sided": False,
        "paired_episode_id": None,
        "survivorship_flagged": False,
        "pairing_unavailable": False,
        "outcome_rs_5d": 0.01,
        "outcome_rs_5d_confirmed": 0.012,
        "outcome_rs_5d_undeniable": 0.013,
        "outcome_mature_5d": True,
        "outcome_mature_5d_confirmed": True,
        "outcome_mature_5d_undeniable": True,
        "outcome_rs_21d": 0.02,
        "outcome_rs_21d_confirmed": 0.022,
        "outcome_rs_21d_undeniable": 0.023,
        "outcome_mature_21d": True,
        "outcome_mature_21d_confirmed": True,
        "outcome_mature_21d_undeniable": True,
        "outcome_rs_63d": 0.05,
        "outcome_rs_63d_confirmed": 0.052,
        "outcome_rs_63d_undeniable": 0.053,
        "outcome_mature_63d": True,
        "outcome_mature_63d_confirmed": True,
        "outcome_mature_63d_undeniable": True,
    }
    result_rows = []
    for row in rows:
        r = dict(defaults)
        r.update(row)
        result_rows.append(r)
    return pd.DataFrame(result_rows)


# ---------------------------------------------------------------------------
# (e) dtw_sanity — test DTW directly, before any integration tests
# ---------------------------------------------------------------------------

class TestDTWSanity:
    def test_identical_distance_zero(self):
        """Identical trajectories → distance 0."""
        a = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        b = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        assert _dtw_distance(a, b, band=4) == 0.0

    def test_reversed_greater_than_shifted(self):
        """Reversed trajectory should have larger DTW than a shifted one."""
        a = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        shifted = np.array([2.0, 3.0, 4.0, 5.0, 6.0])   # just offset, similar shape
        reversed_a = np.array([5.0, 4.0, 3.0, 2.0, 1.0])  # opposite shape
        d_shifted = _dtw_distance(a, shifted, band=4)
        d_reversed = _dtw_distance(a, reversed_a, band=4)
        assert d_reversed > d_shifted, (
            f"reversed ({d_reversed:.4f}) should > shifted ({d_shifted:.4f})"
        )

    def test_empty_distance_zero(self):
        """Empty arrays → distance 0 (graceful degrade)."""
        assert _dtw_distance(np.array([]), np.array([]), band=2) == 0.0

    def test_single_element(self):
        a = np.array([3.0])
        b = np.array([5.0])
        assert _dtw_distance(a, b, band=1) == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# (c) base_rate_direction_sign
# ---------------------------------------------------------------------------

class TestBaseRateDirectionSign:
    def _make_out_episodes_negative_rs(self) -> pd.DataFrame:
        """OUT episodes with negative forward RS (direction-adjusted should be positive)."""
        rows = []
        for i in range(25):
            rows.append({
                "episode_id": f"TEST_OUT::{i}",
                "node": "XLK",
                "direction": "out",
                "onset_date": pd.Timestamp("2020-01-01") + pd.Timedelta(days=i * 5),
                "outcome_rs_5d": -0.02,   # raw negative
                "outcome_mature_5d": True,
                "outcome_rs_21d": -0.03,
                "outcome_mature_21d": True,
                "outcome_rs_63d": -0.05,
                "outcome_mature_63d": True,
            })
        return _make_episodes(rows)

    def _make_in_episodes_positive_rs(self) -> pd.DataFrame:
        """IN episodes with positive forward RS (direction-adjusted should be positive)."""
        rows = []
        for i in range(25):
            rows.append({
                "episode_id": f"TEST_IN::{i}",
                "node": "XLK",
                "direction": "in",
                "onset_date": pd.Timestamp("2020-01-01") + pd.Timedelta(days=i * 5),
                "outcome_rs_5d": 0.02,   # raw positive
                "outcome_mature_5d": True,
                "outcome_rs_21d": 0.03,
                "outcome_mature_21d": True,
                "outcome_rs_63d": 0.05,
                "outcome_mature_63d": True,
            })
        return _make_episodes(rows)

    def test_out_negative_rs_positive_da(self):
        """OUT × negative raw RS → direction-adjusted POSITIVE."""
        eps_out = self._make_out_episodes_negative_rs()
        br = build_base_rates(eps_out, pd.DataFrame())
        out_cells = [
            t for t in br["tables"]
            if t["tier"] == "s"
            and t["direction"] == "out"
            and t["detection_tier"] == "onset"
            and t["regime"] == "all"
        ]
        assert out_cells, "No cell found for tier=s direction=out detection_tier=onset regime=all"
        cell = out_cells[0]
        assert cell["mean_da_21d"] is not None
        assert cell["mean_da_21d"] > 0, (
            f"OUT episode with negative raw RS should have POSITIVE DA mean; "
            f"got {cell['mean_da_21d']}"
        )

    def test_in_positive_rs_positive_da(self):
        """IN × positive raw RS → direction-adjusted POSITIVE."""
        eps_in = self._make_in_episodes_positive_rs()
        br = build_base_rates(eps_in, pd.DataFrame())
        in_cells = [
            t for t in br["tables"]
            if t["tier"] == "s"
            and t["direction"] == "in"
            and t["detection_tier"] == "onset"
            and t["regime"] == "all"
        ]
        assert in_cells
        cell = in_cells[0]
        assert cell["mean_da_21d"] > 0

    def test_in_negative_rs_negative_da(self):
        """IN × negative raw RS → direction-adjusted NEGATIVE (sanity check)."""
        rows = []
        for i in range(25):
            rows.append({
                "episode_id": f"IN_NEG::{i}",
                "node": "XLK",
                "direction": "in",
                "outcome_rs_21d": -0.04,
                "outcome_mature_21d": True,
            })
        eps = _make_episodes(rows)
        br = build_base_rates(eps, pd.DataFrame())
        cells = [
            t for t in br["tables"]
            if t["tier"] == "s"
            and t["direction"] == "in"
            and t["detection_tier"] == "onset"
            and t["regime"] == "all"
        ]
        assert cells[0]["mean_da_21d"] < 0


# ---------------------------------------------------------------------------
# (d) thin_cell_flag
# ---------------------------------------------------------------------------

class TestThinCellFlag:
    def test_n_below_20_is_thin(self):
        """n < 20 → thin=True."""
        rows = [
            {
                "episode_id": f"THIN::{i}",
                "direction": "in",
                "outcome_rs_21d": 0.01,
                "outcome_mature_21d": True,
            }
            for i in range(15)  # only 15 rows
        ]
        eps = _make_episodes(rows)
        br = build_base_rates(eps, pd.DataFrame())
        all_cells = [
            t for t in br["tables"]
            if t["tier"] == "s" and t["direction"] == "in"
            and t["detection_tier"] == "onset" and t["regime"] == "all"
        ]
        assert all_cells
        assert all_cells[0]["thin"] is True, "n=15 should be thin"
        assert all_cells[0]["n"] == 15

    def test_n_at_20_is_not_thin(self):
        """n == 20 → thin=False (boundary at <20)."""
        rows = [
            {
                "episode_id": f"FAT::{i}",
                "direction": "in",
                "outcome_rs_21d": 0.01,
                "outcome_mature_21d": True,
            }
            for i in range(20)
        ]
        eps = _make_episodes(rows)
        br = build_base_rates(eps, pd.DataFrame())
        all_cells = [
            t for t in br["tables"]
            if t["tier"] == "s" and t["direction"] == "in"
            and t["detection_tier"] == "onset" and t["regime"] == "all"
        ]
        assert all_cells
        assert all_cells[0]["thin"] is False, "n=20 should NOT be thin"

    def test_n_above_20_is_not_thin(self):
        """n == 30 → thin=False."""
        rows = [
            {"episode_id": f"FAT::{i}", "direction": "in", "outcome_rs_21d": 0.01, "outcome_mature_21d": True}
            for i in range(30)
        ]
        eps = _make_episodes(rows)
        br = build_base_rates(eps, pd.DataFrame())
        cells = [
            t for t in br["tables"]
            if t["tier"] == "s" and t["direction"] == "in"
            and t["detection_tier"] == "onset" and t["regime"] == "all"
        ]
        assert cells[0]["thin"] is False


# ---------------------------------------------------------------------------
# (b) leakage_guard — the test that MUST FAIL on a broken filter
# ---------------------------------------------------------------------------

class TestLeakageGuard:
    """The leakage guard test.

    An analogue with onset only 10 sessions before the query (well within the
    63-session leakage buffer) is EXCLUDED even if it is the closest possible
    match.  If the eligibility filter is missing, this test fails.
    """

    def _make_catalog_and_query(self) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
        """
        Plant 50 normal analogues (well before leakage buffer) + 1 "perfect"
        analogue that is just 10 sessions before the query onset.
        The perfect analogue should be closest by all scalar features.
        """
        trading_dates = _make_trading_dates(250)
        # Query onset at session 200
        query_onset = trading_dates[200]

        rows = []

        # 50 valid analogues: onset at sessions 0..49 (all > 63 sessions before query)
        for i in range(50):
            onset = trading_dates[i]
            rows.append({
                "episode_id": f"VALID::{i}",
                "node": "XLK",
                "direction": "in",
                "onset_date": onset,
                "exhausted_date": onset + pd.Timedelta(days=30),
                "peak_accel_z": 1.5 + float(i) * 0.01,  # varying
                "cohesion_at_onset": 0.4,
                "breadth_at_onset": 0.5,
                "regime_vix_pctile": 0.35,
                "regime_spy_above_200d": 1.0,
                "outcome_rs_21d": 0.02,
                "outcome_mature_21d": True,
            })

        # 1 LEAKY "perfect" analogue: onset at session 190 (10 before query@200)
        leaky_onset = trading_dates[190]
        rows.append({
            "episode_id": "LEAKY::0",
            "node": "XLK",
            "direction": "in",
            "onset_date": leaky_onset,
            "exhausted_date": None,  # open, making it "current"
            "peak_accel_z": 1.5,    # same as query
            "cohesion_at_onset": 0.4,
            "breadth_at_onset": 0.5,
            "regime_vix_pctile": 0.35,
            "regime_spy_above_200d": 1.0,
            "outcome_rs_21d": 0.02,
            "outcome_mature_21d": True,
        })

        catalog = _make_episodes(rows)

        # Build panel so the session-counting can work
        rs_vals = list(np.linspace(0, 0.1, 250))
        panel = _make_panel({"XLK": rs_vals})

        query = {
            "episode_id": "QUERY::0",
            "node": "XLK",
            "direction": "in",
            "onset_date": query_onset,
            "cohesion_at_onset": 0.4,
            "breadth_at_onset": 0.5,
            "regime_vix_pctile": 0.35,
            "regime_spy_above_200d": 1.0,
        }
        return catalog, query, panel

    def test_leaky_episode_excluded(self):
        """The episode 10 sessions before query must NOT appear in analogues."""
        catalog, query, panel = self._make_catalog_and_query()
        result = find_analogues(query, catalog, panel=panel, k=7)

        returned_ids = [a["episode_id"] for a in result["analogues"]]
        assert "LEAKY::0" not in returned_ids, (
            "LEAKY episode (10 sessions before query) appeared in analogues "
            "— leakage filter is missing or broken."
        )

    def test_valid_episodes_appear(self):
        """Valid episodes (well before leakage buffer) DO appear."""
        catalog, query, panel = self._make_catalog_and_query()
        result = find_analogues(query, catalog, panel=panel, k=7)

        returned_ids = {a["episode_id"] for a in result["analogues"]}
        valid_count = sum(1 for ep_id in returned_ids if ep_id.startswith("VALID::"))
        assert valid_count > 0, "No valid analogues returned at all"

    def test_leakage_excluded_count_positive(self):
        """The leakage_excluded count must be at least 1 (the LEAKY episode)."""
        catalog, query, panel = self._make_catalog_and_query()
        result = find_analogues(query, catalog, panel=panel, k=7)
        assert result["leakage_excluded"] >= 1, (
            f"leakage_excluded should be >=1; got {result['leakage_excluded']}"
        )


# ---------------------------------------------------------------------------
# (a) twin_analogue — planted identical twin → top-1
# ---------------------------------------------------------------------------

class TestTwinAnalogue:
    """An episode with identical feature vector and RS trajectory to the query
    should be the top-1 analogue (distance closest to 0)."""

    def _make_twin_catalog_and_query(self) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
        """
        Query at session 150. Twin at session 50 (well before leakage buffer).
        30 other episodes with different features.
        """
        trading_dates = _make_trading_dates(300)
        query_onset = trading_dates[150]
        twin_onset = trading_dates[50]

        # Use a specific RS trajectory for both query node and twin node
        # The trajectory is the same pattern of RS values at their respective onsets
        rs_pattern = [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08,
                      0.09, 0.10, 0.09, 0.08, 0.07, 0.06, 0.05, 0.04,
                      0.03, 0.02, 0.01, 0.00]  # 20 values

        # For query at session 150: rs[131..150] = rs_pattern
        rs_query = np.zeros(300)
        rs_query[131:151] = rs_pattern
        # For twin at session 50: rs[31..50] = rs_pattern
        rs_twin = np.zeros(300)
        rs_twin[31:51] = rs_pattern

        panel = _make_panel({"QUERY_NODE": list(rs_query), "TWIN_NODE": list(rs_twin)})

        rows = []

        # Twin episode: same scalars, onset at session 50
        rows.append({
            "episode_id": "TWIN::0",
            "node": "TWIN_NODE",
            "direction": "in",
            "onset_date": twin_onset,
            "exhausted_date": twin_onset + pd.Timedelta(days=30),
            "peak_accel_z": 2.0,
            "cohesion_at_onset": 0.55,
            "breadth_at_onset": 0.62,
            "regime_vix_pctile": 0.45,
            "regime_spy_above_200d": 1.0,
            "outcome_rs_21d": 0.03,
            "outcome_mature_21d": True,
        })

        # 30 diverse episodes with different scalars
        for i in range(30):
            ep_onset = trading_dates[i]
            rows.append({
                "episode_id": f"OTHER::{i}",
                "node": "TWIN_NODE",
                "direction": "in",
                "onset_date": ep_onset,
                "exhausted_date": ep_onset + pd.Timedelta(days=20),
                "peak_accel_z": 0.5 + float(i) * 0.1,   # very different from 2.0
                "cohesion_at_onset": 0.1 + float(i) * 0.01,
                "breadth_at_onset": 0.2,
                "regime_vix_pctile": 0.8,    # opposite regime
                "regime_spy_above_200d": 0.0,
                "outcome_rs_21d": -0.01,
                "outcome_mature_21d": True,
            })

        catalog = _make_episodes(rows)

        query = {
            "episode_id": "QUERY::0",
            "node": "QUERY_NODE",
            "direction": "in",
            "onset_date": query_onset,
            "cohesion_at_onset": 0.55,
            "breadth_at_onset": 0.62,
            "regime_vix_pctile": 0.45,
            "regime_spy_above_200d": 1.0,
        }
        return catalog, query, panel

    def test_twin_is_top1(self):
        """Planted identical twin must be the top-1 analogue."""
        catalog, query, panel = self._make_twin_catalog_and_query()
        result = find_analogues(query, catalog, panel=panel, k=7)

        assert result["analogues"], "No analogues returned"
        top1 = result["analogues"][0]
        assert top1["episode_id"] == "TWIN::0", (
            f"Expected TWIN::0 as top-1 analogue, got {top1['episode_id']} "
            f"(distance={top1['distance']:.4f})"
        )

    def test_twin_not_excluded_by_leakage(self):
        """The twin at session 50 (100 sessions before query at 150) is eligible."""
        catalog, query, panel = self._make_twin_catalog_and_query()
        result = find_analogues(query, catalog, panel=panel, k=7)
        returned_ids = [a["episode_id"] for a in result["analogues"]]
        assert "TWIN::0" in returned_ids, "Twin was unexpectedly excluded by leakage filter"


# ---------------------------------------------------------------------------
# (f) no_same_direction_cross — direction filter
# ---------------------------------------------------------------------------

class TestDirectionFilter:
    def test_only_same_direction_returned(self):
        """find_analogues must only return same-direction episodes."""
        trading_dates = _make_trading_dates(200)
        query_onset = trading_dates[150]

        rows = []
        # 5 IN episodes (valid, well before query)
        for i in range(5):
            rows.append({
                "episode_id": f"IN::{i}",
                "node": "XLK",
                "direction": "in",
                "onset_date": trading_dates[i],
                "exhausted_date": trading_dates[i] + pd.Timedelta(days=20),
                "outcome_rs_21d": 0.02,
                "outcome_mature_21d": True,
            })
        # 5 OUT episodes (should NOT appear for an IN query)
        for i in range(5):
            rows.append({
                "episode_id": f"OUT::{i}",
                "node": "XLE",
                "direction": "out",
                "onset_date": trading_dates[i + 5],
                "exhausted_date": trading_dates[i + 5] + pd.Timedelta(days=20),
                "outcome_rs_21d": -0.02,
                "outcome_mature_21d": True,
            })

        catalog = _make_episodes(rows)
        query = {
            "episode_id": "QUERY::0",
            "node": "XLK",
            "direction": "in",
            "onset_date": query_onset,
        }

        result = find_analogues(query, catalog, panel=None, k=10)
        for a in result["analogues"]:
            assert not a["episode_id"].startswith("OUT::"), (
                f"OUT episode {a['episode_id']} appeared in IN query analogues"
            )


# ---------------------------------------------------------------------------
# (g) leakage_boundary — exact boundary test
# ---------------------------------------------------------------------------

class TestLeakageBoundary:
    """Tests the exact boundary of the leakage filter.

    onset + 63 sessions = query_onset  → EXCLUDED (not strictly less than)
    onset + 64 sessions < query_onset → INCLUDED
    """

    def _setup(self) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
        """Query at session 100. Two episodes: one at session 37 (100-63=37,
        exactly at boundary → excluded) and one at session 36 (100-64=36,
        one before boundary → included)."""
        trading_dates = _make_trading_dates(200)
        query_onset = trading_dates[100]

        rows = []
        # At boundary: onset at session 37 → onset + 63 = session 100 = query → EXCLUDED
        rows.append({
            "episode_id": "BOUNDARY_EXACT::0",
            "node": "XLK",
            "direction": "in",
            "onset_date": trading_dates[37],
            "exhausted_date": trading_dates[37] + pd.Timedelta(days=20),
            "outcome_rs_21d": 0.02,
            "outcome_mature_21d": True,
        })
        # One before boundary: onset at session 36 → onset + 63 = 99 < 100 = query → INCLUDED
        rows.append({
            "episode_id": "BOUNDARY_BEFORE::0",
            "node": "XLK",
            "direction": "in",
            "onset_date": trading_dates[36],
            "exhausted_date": trading_dates[36] + pd.Timedelta(days=20),
            "outcome_rs_21d": 0.02,
            "outcome_mature_21d": True,
        })

        catalog = _make_episodes(rows)
        panel = _make_panel({"XLK": list(np.zeros(200))})

        query = {
            "episode_id": "QUERY::0",
            "node": "XLK",
            "direction": "in",
            "onset_date": query_onset,
        }
        return catalog, query, panel

    def test_boundary_exact_excluded(self):
        """onset + 63 sessions == query → excluded."""
        catalog, query, panel = self._setup()
        result = find_analogues(query, catalog, panel=panel, k=5)
        returned_ids = [a["episode_id"] for a in result["analogues"]]
        assert "BOUNDARY_EXACT::0" not in returned_ids, (
            "Episode at exact boundary (onset+63==query) should be excluded"
        )

    def test_boundary_before_included(self):
        """onset + 64 sessions < query → included."""
        catalog, query, panel = self._setup()
        result = find_analogues(query, catalog, panel=panel, k=5)
        returned_ids = [a["episode_id"] for a in result["analogues"]]
        assert "BOUNDARY_BEFORE::0" in returned_ids, (
            "Episode one session before boundary (onset+64 < query) should be included"
        )


# ---------------------------------------------------------------------------
# Additional: aggregate description carries R4 disclaimer
# ---------------------------------------------------------------------------

class TestR4Compliance:
    def test_aggregate_description(self):
        """Aggregate description must contain 'descriptive' and 'not a forecast'."""
        rows = [
            {"episode_id": f"EP::{i}", "direction": "in",
             "onset_date": pd.Timestamp("2019-01-01") + pd.Timedelta(days=i * 5),
             "exhausted_date": pd.Timestamp("2019-01-01") + pd.Timedelta(days=i * 5 + 20),
             "outcome_rs_21d": 0.01, "outcome_mature_21d": True}
            for i in range(10)
        ]
        catalog = _make_episodes(rows)
        query = {
            "episode_id": "Q::0",
            "node": "XLK",
            "direction": "in",
            "onset_date": pd.Timestamp("2025-01-01"),
        }
        result = find_analogues(query, catalog, panel=None, k=5)
        desc = result.get("aggregate", {}).get("description", "")
        assert "descriptive" in desc.lower(), f"Missing 'descriptive' in: {desc}"
        assert "not a forecast" in desc.lower(), f"Missing 'not a forecast' in: {desc}"

    def test_base_rates_r4_meta(self):
        """Base rates meta must carry R4 compliance note."""
        eps = _make_episodes([{"episode_id": "E::0", "direction": "in"}])
        br = build_base_rates(eps, pd.DataFrame())
        meta = br.get("meta", {})
        assert "r4_compliance" in meta, "Missing r4_compliance in base_rates meta"
        assert "not a forecast" in str(br).lower() or "descriptive" in str(br).lower()
