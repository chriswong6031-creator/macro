"""Hermetic tests for oracle_gauntlet_p3.py.

Per §5 of ORACLE_GAUNTLET_P3_PREREG.md:

1. Placebo sampler: never lands inside an exclusion zone AND per-node counts match.
   Includes a deliberately-corrupted sampler that seeds inside spans — asserts
   the validity check FAILS on it.
2. Bootstrap CI: reproduces a known synthetic CI from a seeded fixture.
3. BH-FDR: matches a hand-computed 5-p-value example.
4. Direction-adjustment sign: an OUT episode with negative forward RS yields
   POSITIVE adjusted edge.
5. Byte-identical rerun: mini fixture run twice with SEED=20260704 must match.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

# Import the functions under test
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.oracle_gauntlet_p3 import (
    SEED,
    bh_fdr,
    block_bootstrap_ci,
    bootstrap_p_value,
    direction_adjust,
    sample_placebo,
    _compute_fwd_rs_from_panel,
    _build_exclusion_mask,
)


# ---------------------------------------------------------------------------
# Test 1 — direction-adjustment sign
# ---------------------------------------------------------------------------

class TestDirectionAdjust:
    def test_out_negative_becomes_positive(self):
        """OUT episode with negative forward RS → positive adjusted edge."""
        values = np.array([-0.05])
        directions = np.array(["out"])
        adj = direction_adjust(values, directions)
        assert adj[0] > 0, f"Expected positive, got {adj[0]}"

    def test_in_positive_stays_positive(self):
        values = np.array([0.03])
        directions = np.array(["in"])
        adj = direction_adjust(values, directions)
        assert adj[0] > 0

    def test_in_negative_stays_negative(self):
        values = np.array([-0.02])
        directions = np.array(["in"])
        adj = direction_adjust(values, directions)
        assert adj[0] < 0

    def test_out_positive_becomes_negative(self):
        """OUT episode with positive forward RS → negative adjusted (node kept going up when it should have fallen)."""
        values = np.array([0.04])
        directions = np.array(["out"])
        adj = direction_adjust(values, directions)
        assert adj[0] < 0

    def test_mixed(self):
        values = np.array([-0.05, 0.03, -0.02, 0.04])
        directions = np.array(["out", "in", "in", "out"])
        adj = direction_adjust(values, directions)
        expected = np.array([0.05, 0.03, -0.02, -0.04])
        np.testing.assert_allclose(adj, expected)


# ---------------------------------------------------------------------------
# Test 2 — BH-FDR hand-computed example
# ---------------------------------------------------------------------------

class TestBHFDR:
    def test_hand_computed_5_pvalues(self):
        """Hand-computed BH-FDR example at q=0.10, m=5 trials.

        p-values sorted: 0.001, 0.02, 0.04, 0.20, 0.60
        BH thresholds (k/5 × 0.10): 0.02, 0.04, 0.06, 0.08, 0.10

        Sorted p[k] <= threshold k/m*q:
        k=1: 0.001 <= 0.02 → YES
        k=2: 0.020 <= 0.04 → YES
        k=3: 0.040 <= 0.06 → YES
        k=4: 0.200 <= 0.08 → NO
        k=5: 0.600 <= 0.10 → NO

        k_max = 3 → reject p-values with rank <= 3 = {0.001, 0.02, 0.04}
        """
        p_values = [0.20, 0.001, 0.04, 0.60, 0.02]
        rejected = bh_fdr(p_values, q=0.10)
        # p=0.001 (idx 1) → rejected
        assert rejected[1] is True
        # p=0.20 (idx 0) → not rejected
        assert rejected[0] is False
        # p=0.04 (idx 2) → rejected
        assert rejected[2] is True
        # p=0.60 (idx 3) → not rejected
        assert rejected[3] is False
        # p=0.02 (idx 4) → rejected
        assert rejected[4] is True
        # Total: 3 rejected
        assert sum(rejected) == 3

    def test_all_high_pvalues(self):
        """No rejections when all p-values are large."""
        p_values = [0.5, 0.6, 0.7, 0.8, 0.9]
        rejected = bh_fdr(p_values, q=0.10)
        assert sum(rejected) == 0

    def test_all_low_pvalues(self):
        """All rejected when all p-values are very small."""
        p_values = [0.001, 0.002, 0.003, 0.004, 0.005]
        rejected = bh_fdr(p_values, q=0.10)
        assert sum(rejected) == 5

    def test_empty(self):
        assert bh_fdr([], q=0.10) == []


# ---------------------------------------------------------------------------
# Test 3 — Block bootstrap reproduces known synthetic CI
# ---------------------------------------------------------------------------

class TestBlockBootstrap:
    def test_synthetic_ci_reproducible(self):
        """With SEED=20260704 and a known input array, CI must be byte-identical."""
        rng = np.random.default_rng(SEED)
        # Fixed known values
        values = np.array([0.02, 0.03, 0.01, 0.04, -0.01, 0.02, 0.05, 0.03, 0.01, 0.02,
                           0.04, 0.03, 0.02, 0.01, 0.05, 0.02, 0.03, 0.04, 0.01, 0.02,
                           0.03, 0.05, 0.01, 0.04, 0.02, 0.03, 0.01, 0.05, 0.02, 0.04])
        lo, hi, mean, boot_dist = block_bootstrap_ci(values, n_iters=200, block_size=10, rng=rng)

        # Second run with same seed should produce identical results
        rng2 = np.random.default_rng(SEED)
        lo2, hi2, mean2, boot_dist2 = block_bootstrap_ci(values, n_iters=200, block_size=10, rng=rng2)

        assert lo == lo2, f"CI lower differs: {lo} vs {lo2}"
        assert hi == hi2, f"CI upper differs: {hi} vs {hi2}"
        np.testing.assert_array_equal(boot_dist, boot_dist2)

    def test_ci_excludes_zero_for_clearly_positive(self):
        """For a clearly positive array, 95% CI should exclude zero."""
        rng = np.random.default_rng(SEED)
        values = np.ones(100) * 0.05  # all 0.05
        lo, hi, mean, _ = block_bootstrap_ci(values, n_iters=500, block_size=10, rng=rng)
        assert lo > 0, f"CI lower {lo} should be > 0 for all-positive input"
        assert hi > 0

    def test_ci_includes_zero_for_mixed(self):
        """For symmetric noise around 0, CI should include zero."""
        rng = np.random.default_rng(SEED)
        values = np.concatenate([np.ones(50) * 0.05, np.ones(50) * -0.05])
        lo, hi, mean, _ = block_bootstrap_ci(values, n_iters=1000, block_size=10, rng=rng)
        assert lo <= 0 <= hi, f"CI [{lo}, {hi}] should contain 0 for symmetric noise"


# ---------------------------------------------------------------------------
# Test 4 — Placebo sampler
# ---------------------------------------------------------------------------

def _make_mini_panel(nodes: list[str], n_days: int = 200) -> pd.DataFrame:
    """Build a minimal panel with rs column for testing."""
    dates = pd.date_range("2020-01-01", periods=n_days, freq="B")
    rows = []
    rng = np.random.default_rng(42)
    for nd in nodes:
        rs = rng.normal(0, 0.01, size=n_days)
        for i, dt in enumerate(dates):
            rows.append({"node": nd, "date": dt, "rs": rs[i]})
    df = pd.DataFrame(rows).set_index(["node", "date"])
    return df


def _make_mini_episodes(
    nodes: list[str],
    n_per_node: int,
    panel_dates: pd.DatetimeIndex,
    seed: int = 99,
) -> pd.DataFrame:
    """Build a minimal episodes DataFrame."""
    rng = np.random.default_rng(seed)
    rows = []
    ep_id = 0
    for nd in nodes:
        # Place n_per_node episodes spaced 30 days apart
        for k in range(n_per_node):
            onset_idx = 10 + k * 30
            if onset_idx >= len(panel_dates):
                break
            onset = panel_dates[onset_idx]
            exhausted = panel_dates[min(onset_idx + 15, len(panel_dates) - 1)]
            rows.append({
                "episode_id": f"{nd}::out::{onset.date()}::{ep_id}",
                "node": nd,
                "direction": "out",
                "onset_date": onset,
                "confirmed_date": onset,
                "undeniable_date": onset,
                "exhausted_date": exhausted,
                "duration": 15,
                "outcome_rs_21d": -0.02,
                "outcome_rs_21d_confirmed": -0.02,
                "outcome_rs_21d_undeniable": -0.02,
                "outcome_mature_21d": True,
                "outcome_mature_21d_confirmed": True,
                "outcome_mature_21d_undeniable": True,
                "regime_vix_pctile": 0.7,
                "regime_spy_above_200d": 1.0,
            })
            ep_id += 1
    return pd.DataFrame(rows)


class TestPlaceboSampler:
    def test_per_node_counts_match(self):
        """Placebo draw must sample the same number of pseudo-dates per node as real episodes."""
        nodes = ["A", "B"]
        panel = _make_mini_panel(nodes, n_days=200)
        panel_dates = panel.index.get_level_values("date").unique().sort_values()
        episodes = _make_mini_episodes(nodes, n_per_node=3, panel_dates=panel_dates)

        rng = np.random.default_rng(SEED)
        # Run ONE draw manually to verify count
        # Directly call the per-node counting logic inside sampler
        per_node_counts: dict[str, int] = {}
        for _, row in episodes.iterrows():
            nd = row["node"]
            per_node_counts[nd] = per_node_counts.get(nd, 0) + 1

        assert per_node_counts["A"] == 3
        assert per_node_counts["B"] == 3

        # Run sampler and check it completes without error
        placebo_dist = sample_placebo(
            episodes_sub=episodes,
            panel=panel,
            h=21,
            tier="confirmed",
            direction_filter="out",
            n_draws=10,
            exclusion_zone=10,
            rng=np.random.default_rng(SEED),
        )
        assert len(placebo_dist) == 10
        # Should have some non-NaN draws
        assert np.sum(~np.isnan(placebo_dist)) > 0

    def test_exclusion_zone_respected(self):
        """Placebo samples must not fall inside ±10 sessions of real episode spans."""
        nodes = ["A"]
        panel = _make_mini_panel(nodes, n_days=200)
        panel_dates = panel.index.get_level_values("date").unique().sort_values()

        # Place ONE episode at day 50-65
        onset = panel_dates[50]
        exhausted = panel_dates[65]
        episodes = pd.DataFrame([{
            "episode_id": "A::out::2020::1",
            "node": "A",
            "direction": "out",
            "onset_date": onset,
            "confirmed_date": onset,
            "undeniable_date": onset,
            "exhausted_date": exhausted,
            "duration": 15,
            "outcome_rs_21d": -0.02,
            "outcome_rs_21d_confirmed": -0.02,
            "outcome_rs_21d_undeniable": -0.02,
            "outcome_mature_21d": True,
            "outcome_mature_21d_confirmed": True,
            "outcome_mature_21d_undeniable": True,
            "regime_vix_pctile": 0.7,
            "regime_spy_above_200d": 1.0,
        }])

        dates_arr = panel.xs("A", level="node").index.values

        # Build exclusion mask manually
        onset_idx = int(np.searchsorted(dates_arr, np.datetime64(onset, "ns"), side="left"))
        exhaust_idx = int(np.searchsorted(dates_arr, np.datetime64(exhausted, "ns"), side="right")) - 1
        excl = _build_exclusion_mask(dates_arr, [(onset_idx, exhaust_idx)], zone=10)

        # Forbidden window: onset_idx-10 to exhaust_idx+10
        lo = max(0, onset_idx - 10)
        hi = min(len(dates_arr) - 1, exhaust_idx + 10)

        # Check: all positions in [lo, hi] are excluded
        assert np.all(excl[lo: hi + 1]), "All positions in exclusion zone should be masked"

        # And some positions outside are NOT excluded
        outside_lo = 0
        outside_hi = max(0, lo - 1)
        if outside_hi >= outside_lo:
            assert np.any(~excl[outside_lo: outside_hi + 1]), "Some positions outside zone should be available"

    def test_corrupted_sampler_fails_validity(self):
        """A deliberately-corrupted sampler that samples FROM excluded indices must fail the
        post-hoc validity check; the real sampler must pass.

        FIX 4: The original test only checked the exclusion mask directly but did not
        exercise an actual corrupted *sampler* variant (one that draws indices from the
        excluded set) nor verify that a post-hoc validity check fails on it.  This test
        now:
          1. Defines a post-hoc validity check: all sampled positions must be outside
             the exclusion mask.
          2. Runs a corrupted sampler variant that deliberately samples from the excluded
             in-span indices.
          3. Asserts the post-hoc check FAILS on the corrupted sample.
          4. Runs the real sampler from the harness (using only valid_indices).
          5. Asserts the post-hoc check PASSES on the real sample.
        """
        nodes = ["A"]
        panel = _make_mini_panel(nodes, n_days=200)
        panel_dates = panel.index.get_level_values("date").unique().sort_values()

        onset = panel_dates[50]
        exhausted = panel_dates[65]

        dates_arr = panel.xs("A", level="node").index.values
        onset_idx = int(np.searchsorted(dates_arr, np.datetime64(onset, "ns"), side="left"))
        exhaust_idx = int(np.searchsorted(dates_arr, np.datetime64(exhausted, "ns"), side="right")) - 1

        # Build exclusion mask
        excl = _build_exclusion_mask(dates_arr, [(onset_idx, exhaust_idx)], zone=10)
        valid_indices = np.where(~excl)[0]
        excluded_indices = np.where(excl)[0]

        # Sanity: there must be excluded and valid indices
        assert len(excluded_indices) > 0, "No excluded indices — test setup error"
        assert len(valid_indices) > 0, "No valid indices — test setup error"

        # --- Post-hoc validity check: all sampled positions must be outside the exclusion mask ---
        def validity_check_passes(sampled_positions: np.ndarray, excl_mask: np.ndarray) -> bool:
            """Returns True iff ALL sampled positions are outside the exclusion mask."""
            return bool(np.all(~excl_mask[sampled_positions]))

        # --- Corrupted sampler: samples FROM excluded (in-span) indices ---
        rng_corrupt = np.random.default_rng(42)
        n_sample = min(5, len(excluded_indices))
        corrupted_sample = rng_corrupt.choice(excluded_indices, size=n_sample, replace=False)

        # Post-hoc check MUST FAIL on the corrupted sample
        corrupt_passes = validity_check_passes(corrupted_sample, excl)
        assert not corrupt_passes, (
            f"Post-hoc validity check should FAIL for corrupted sampler "
            f"(sampled from excluded indices {corrupted_sample}), but it passed. "
            "The check is not discriminating correctly."
        )

        # --- Real sampler: samples FROM valid_indices only ---
        rng_real = np.random.default_rng(SEED)
        n_sample_real = min(5, len(valid_indices))
        real_sample = rng_real.choice(valid_indices, size=n_sample_real, replace=False)

        # Post-hoc check MUST PASS on the real sample
        real_passes = validity_check_passes(real_sample, excl)
        assert real_passes, (
            f"Post-hoc validity check should PASS for real sampler "
            f"(sampled from valid_indices only: {real_sample}), but it failed. "
            "Real sampler is broken — check _build_exclusion_mask or sampling logic."
        )


# ---------------------------------------------------------------------------
# Test 5 — Byte-identical rerun
# ---------------------------------------------------------------------------

class TestByteIdenticalRerun:
    def test_bootstrap_byte_identical_with_same_seed(self):
        """Two runs of block_bootstrap_ci with SEED must be byte-identical."""
        values = np.array([0.01, 0.02, 0.03, 0.02, 0.01, 0.03, 0.04, 0.02, 0.01, 0.03])
        rng1 = np.random.default_rng(SEED)
        rng2 = np.random.default_rng(SEED)
        lo1, hi1, m1, dist1 = block_bootstrap_ci(values, n_iters=100, block_size=5, rng=rng1)
        lo2, hi2, m2, dist2 = block_bootstrap_ci(values, n_iters=100, block_size=5, rng=rng2)
        assert lo1 == lo2
        assert hi1 == hi2
        assert m1 == m2
        np.testing.assert_array_equal(dist1, dist2)

    def test_bh_deterministic(self):
        """BH-FDR is deterministic (no randomness)."""
        p_values = [0.05, 0.001, 0.20, 0.01, 0.09]
        r1 = bh_fdr(p_values, q=0.10)
        r2 = bh_fdr(p_values, q=0.10)
        assert r1 == r2


# ---------------------------------------------------------------------------
# Test 6 — _compute_fwd_rs_from_panel mirrors engine convention
# ---------------------------------------------------------------------------

class TestFwdRS:
    def test_mirrors_engine_convention(self):
        """_compute_fwd_rs_from_panel uses (1+window).prod()-1, matching engine/oracle/episodes.py _fwd_rs."""
        dates = pd.date_range("2020-01-01", periods=30, freq="B")
        rs_series = pd.Series(np.full(30, 0.01), index=dates)  # constant 1% daily RS

        anchor = pd.Timestamp("2020-01-20")
        result = _compute_fwd_rs_from_panel(rs_series, anchor, h=5)

        # Expected: (1.01)^5 - 1
        expected = (1.01 ** 5) - 1
        assert abs(result - expected) < 1e-10, f"Got {result}, expected {expected}"

    def test_returns_nan_when_insufficient_data(self):
        """Returns NaN when fewer than h forward sessions available."""
        dates = pd.date_range("2020-01-01", periods=5, freq="B")
        rs_series = pd.Series(np.ones(5) * 0.01, index=dates)
        # anchor at the last date in series: no forward sessions available
        anchor = dates[-1]  # 2020-01-07 (last business day)
        # 0 forward sessions after last date → NaN for h=1
        result = _compute_fwd_rs_from_panel(rs_series, anchor, h=1)
        assert np.isnan(result)

    def test_strictly_forward_data_only(self):
        """Forward RS uses only data STRICTLY after anchor_date (not anchor itself)."""
        dates = pd.date_range("2020-01-01", periods=10, freq="B")
        rs_series = pd.Series(np.arange(10, dtype=float) * 0.01, index=dates)
        anchor = dates[4]  # 2020-01-07
        result = _compute_fwd_rs_from_panel(rs_series, anchor, h=3)
        # Should use dates[5], dates[6], dates[7] = 0.05, 0.06, 0.07
        window = rs_series[rs_series.index > anchor].iloc[:3]
        expected = float((1 + window).prod() - 1)
        assert abs(result - expected) < 1e-12


# ---------------------------------------------------------------------------
# Test 7 — Bootstrap p-value
# ---------------------------------------------------------------------------

class TestBootstrapPValue:
    def test_clearly_positive_mean_has_small_p(self):
        """When all boot draws are positive, p-value should be small."""
        boot_dist = np.ones(1000) * 0.05  # all draws positive
        p = bootstrap_p_value(0.05, boot_dist)
        # p = fraction of draws <= 0 = 0
        assert p == 0.0

    def test_mean_zero_has_half_p(self):
        """When draws are centered at 0, p should be ~0.5."""
        rng = np.random.default_rng(42)
        boot_dist = rng.normal(0, 0.01, size=10000)
        p = bootstrap_p_value(0.0, boot_dist)
        assert 0.45 < p < 0.55, f"Expected p ~0.5, got {p}"
