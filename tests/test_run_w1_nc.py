"""Unit tests for scripts/research/run_w1_nc.py.

Covers findings from the W1 NC opus review:
  (1) Bug fix: datetime64 unit invariance — _fast_make_blocks must not collapse
      blocks when dates are in datetime64[us] (microseconds) vs datetime64[ns].
  (2) Bug fix: index misalignment — fast_r1_estimate must read sector/_date_ts
      from columns INSIDE work (not df.loc[work.index, ...]) after reset_index.
  (5) Test coverage: _fast_make_blocks block segmentation; fast_r1_estimate
      index alignment under row drops + agreement with W0 harness r1 estimator.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.research.run_w1_nc import (
    _fast_make_blocks,
    fast_r1_estimate,
)
import scripts.research.entry_strata_phase0 as ph


# ---------------------------------------------------------------------------
# Helpers for building non-singleton FE frames
# ---------------------------------------------------------------------------

def _make_repeated_dates_frame(
    n_dates: int,
    rows_per_date: int,
    rng_seed: int = 0,
    outcome_nan_first_k: int = 0,
    sector_label: str = "sector_A",
) -> pd.DataFrame:
    """Build a DataFrame with n_dates unique dates, each repeated rows_per_date times.

    Non-singleton FE cells (rows_per_date > 1) allow the FE estimator to work.
    outcome_nan_first_k: set the first k rows to NaN outcome (simulate dropped leading rows).
    """
    rng = np.random.default_rng(rng_seed)
    n = n_dates * rows_per_date

    # n_dates unique dates spaced ~5 business days apart
    dates_unique = pd.bdate_range("2015-01-05", periods=n_dates, freq="5B")
    dates = dates_unique.repeat(rows_per_date)
    dates_ns = dates.values.astype("datetime64[ns]").astype(np.int64)

    outcome = rng.integers(0, 2, size=n).astype(float)
    if outcome_nan_first_k > 0:
        outcome[:outcome_nan_first_k] = np.nan

    stratum = rng.integers(0, 2, size=n).astype(float)
    fe_vals = dates.strftime("%Y-%m-%d").tolist()
    sector = [sector_label] * n

    return pd.DataFrame({
        "outcome": outcome,
        "stratum": stratum,
        "_fe": fe_vals,
        "sector": sector,
        "_date_ts": dates_ns,
    })


# ---------------------------------------------------------------------------
# Finding (1): datetime64 unit-invariance test for _fast_make_blocks
# ---------------------------------------------------------------------------

class TestFastMakeBlocksUnitInvariance:
    """Two dates 20 calendar days apart must land in different blocks,
    regardless of whether the integer timestamp is in nanoseconds or
    microseconds (after correct conversion to ns before calling).

    This is the BUG CHECK from finding (1): before the fix,
    datetime64[us].astype(np.int64) values were 1000x smaller than
    nanosecond values, so a 14-day radius (in ns) would cover the entire
    data span and collapse all fires into a single block.
    """

    def _ns(self, ts_str: str) -> int:
        return int(pd.Timestamp(ts_str).value)

    def _us(self, ts_str: str) -> int:
        return int(pd.Timestamp(ts_str).value // 1000)

    def test_ns_dates_20d_apart_produce_two_blocks(self):
        """Two dates 20 days apart (ns encoding, 14d radius) → 2 separate blocks."""
        dates = np.array([self._ns("2020-01-01"), self._ns("2020-01-21")], dtype=np.int64)
        sectors = np.array([0, 0], dtype=np.int64)
        blocks = _fast_make_blocks(dates, sectors, block_radius_days=14)
        assert len(blocks) == 2, (
            f"Expected 2 blocks for dates 20d apart (14d radius), got {len(blocks)}."
        )

    def test_us_dates_wrongly_collapse_to_one_block(self):
        """Microsecond-encoded dates WITHOUT ns-cast → collapse to 1 block (the pre-fix bug).

        Documents the original bug: us timestamps are 1000x smaller than ns,
        making the 14-day ns radius enormous relative to the us difference.
        """
        dates = np.array([self._us("2020-01-01"), self._us("2020-01-21")], dtype=np.int64)
        sectors = np.array([0, 0], dtype=np.int64)
        blocks = _fast_make_blocks(dates, sectors, block_radius_days=14)
        assert len(blocks) == 1, (
            "Pre-fix behavior: microsecond timestamps should collapse to 1 block. "
            "If this assertion fails, _fast_make_blocks now handles unit detection "
            "internally — update this test accordingly."
        )

    def test_ns_cast_from_us_produces_two_blocks(self):
        """After BUG FIX: .astype('datetime64[ns]').astype(int64) → 2 blocks."""
        arr_us = np.array(["2020-01-01", "2020-01-21"], dtype="datetime64[us]")
        dates_fixed = arr_us.astype("datetime64[ns]").astype(np.int64)
        sectors = np.array([0, 0], dtype=np.int64)
        blocks = _fast_make_blocks(dates_fixed, sectors, block_radius_days=14)
        assert len(blocks) == 2, (
            f"Expected 2 blocks after ns-cast fix for dates 20d apart, got {len(blocks)}."
        )

    def test_same_day_dates_one_block(self):
        """Two dates on the same day → 1 block (within 14-day radius)."""
        d = self._ns("2020-06-15")
        dates = np.array([d, d], dtype=np.int64)
        sectors = np.array([0, 0], dtype=np.int64)
        blocks = _fast_make_blocks(dates, sectors, block_radius_days=14)
        assert len(blocks) == 1, f"Expected 1 block for same-day dates, got {len(blocks)}"

    def test_multi_year_span_many_blocks(self):
        """Multi-year span of monthly dates (>14d apart) → one block per date."""
        dates_ts = pd.date_range("2018-01-01", periods=24, freq="ME")
        dates_ns = dates_ts.values.astype("datetime64[ns]").astype(np.int64)
        sectors = np.zeros(len(dates_ns), dtype=np.int64)
        blocks = _fast_make_blocks(dates_ns, sectors, block_radius_days=14)
        # Monthly (~30d) > 14d radius → each date is its own block
        assert len(blocks) == 24, (
            f"Expected 24 blocks for 24 monthly dates (30d > 14d radius), got {len(blocks)}"
        )

    def test_two_sector_groups_independent(self):
        """Same dates in two sectors → 2 blocks per sector = 4 total."""
        d0 = self._ns("2020-01-01")
        d1 = self._ns("2020-01-21")  # 20 days later
        dates = np.array([d0, d1, d0, d1], dtype=np.int64)
        sectors = np.array([0, 0, 1, 1], dtype=np.int64)
        blocks = _fast_make_blocks(dates, sectors, block_radius_days=14)
        assert len(blocks) == 4, (
            f"Expected 4 blocks (2 per sector for 2 sectors), got {len(blocks)}"
        )


# ---------------------------------------------------------------------------
# Finding (2): index-alignment test for fast_r1_estimate
# ---------------------------------------------------------------------------

class TestFastR1EstimateIndexAlignment:
    """fast_r1_estimate must receive the correct sector and _date_ts for
    survivor rows, even when the parent frame's leading rows are dropped.

    Before the fix, df.loc[work.index, sector_col] label-indexed the PARENT
    frame with positional indices from reset_index(drop=True) work frame —
    returning the LEADING rows instead of the survivor rows.
    """

    def test_survivors_sector_is_correct(self):
        """Block builder sees survivors' sector label after leading-row drops.

        Sector_Z leads (NaN outcome → dropped). Sector_A is survivors-only.
        The pre-fix bug would inject sector_Z into the first 2 survivor rows,
        creating a 2-sector block structure. We assert n_blocks matches the
        survivors-only (sector_A) structure computed from _fast_make_blocks.
        """
        n_lead = 2   # 2 leading NaN rows (will be dropped)
        n_dates = 15
        rpr = 4  # rows per date

        rng = np.random.default_rng(7)
        n = n_dates * rpr
        dates_unique = pd.bdate_range("2015-01-05", periods=n_dates, freq="5B")
        dates = dates_unique.repeat(rpr)
        dates_ns = dates.values.astype("datetime64[ns]").astype(np.int64)

        outcome = rng.integers(0, 2, size=n).astype(float)
        outcome[:n_lead] = np.nan  # leading rows have NaN → will be filtered out

        stratum = rng.integers(0, 2, size=n).astype(float)
        fe_vals = dates.strftime("%Y-%m-%d").tolist()

        # Leading rows: sector_Z (should NOT appear in block building after fix)
        # Survivor rows: sector_A
        sector = ["sector_Z"] * n_lead + ["sector_A"] * (n - n_lead)

        df = pd.DataFrame({
            "outcome": outcome,
            "stratum": stratum,
            "_fe": fe_vals,
            "sector": sector,
            "_date_ts": dates_ns,
        })

        result = fast_r1_estimate(
            df, "outcome", "stratum",
            fe_col="_fe",
            sector_col="sector",
            n_bootstrap=50,
            rng_seed=0,
        )

        assert result["n_total"] > 0, "Expected non-empty result for survivors"
        assert result["n_blocks"] > 0, (
            f"Expected >0 blocks for survivors; got n_blocks={result['n_blocks']}."
        )

        # --- STRUCTURAL ASSERTION: block count must match survivors-only structure ---
        # Survivors all have sector_A → single-sector block structure.
        # The buggy code (df.loc[work.index, sector_col]) injects sector_Z into
        # the first 2 survivor rows, producing a 2-sector structure.
        survivor_dates_ns = dates_ns[n_lead:]
        survivor_sec_ids = np.zeros(len(survivor_dates_ns), dtype=np.intp)
        expected_blocks = _fast_make_blocks(
            survivor_dates_ns, survivor_sec_ids, block_radius_days=14
        )
        n_blocks_expected = len(expected_blocks)

        buggy_sec_ids = np.array(
            [1] * n_lead + [0] * (n - n_lead), dtype=np.intp
        )
        buggy_blocks = _fast_make_blocks(
            dates_ns, buggy_sec_ids, block_radius_days=14
        )
        n_blocks_buggy = len(buggy_blocks)

        if n_blocks_expected != n_blocks_buggy:
            assert result["n_blocks"] == n_blocks_expected, (
                f"n_blocks={result['n_blocks']} should match survivors-only "
                f"count={n_blocks_expected}; buggy count={n_blocks_buggy}. "
                f"sector_Z was injected into the survivor frame (pre-fix bug)."
            )

    def test_agrees_with_w0_harness_r1_on_small_frame(self):
        """fast_r1_estimate and W0 harness r1_estimate agree on a known frame.

        Both compute the same FE OLS coefficient. Tolerance: 1e-4.
        Uses 10 unique dates × 8 rows each to avoid singleton FE cells.
        """
        rng = np.random.default_rng(42)
        n_dates = 10
        rpr = 8
        n = n_dates * rpr

        dates_unique = pd.bdate_range("2020-01-06", periods=n_dates, freq="5B")
        dates = dates_unique.repeat(rpr)
        dates_ns = dates.values.astype("datetime64[ns]").astype(np.int64)

        outcome = rng.integers(0, 2, size=n).astype(float)
        stratum = rng.integers(0, 2, size=n).astype(float)
        fe_col_vals = dates.strftime("%Y-%m-%d").tolist()

        df = pd.DataFrame({
            "outcome": outcome,
            "stratum": stratum,
            "_fe": fe_col_vals,
            "_date_ts": dates_ns,
            "date": dates,
            "gradable": np.ones(n, dtype=bool),
            # Columns needed by w0 harness _prepare_binary_outcomes:
            "state_rot": ["CUSHIONED"] * n,
            "state_pos": ["CUSHIONED"] * n,
            "stop5": outcome,
            "mae63": rng.uniform(-0.1, 0.0, size=n),
            "mfe63": rng.uniform(0.0, 0.1, size=n),
            "cushion_rot": np.zeros(n, dtype=float),
        })

        # fast_r1_estimate (run_w1_nc)
        res_fast = fast_r1_estimate(
            df, "outcome", "stratum",
            fe_col="_fe",
            sector_col=None,
            n_bootstrap=50,
            rng_seed=0,
        )

        # W0 harness r1_estimate (entry_strata_phase0)
        res_w0 = ph.r1_estimate(
            df, "outcome", "stratum",
            fe_granularity="date",
            sector_col=None,
            n_bootstrap=50,
            rng_seed=0,
        )

        coef_fast = res_fast.get("coef")
        coef_w0   = res_w0.get("coef")
        assert coef_fast is not None, f"fast_r1_estimate returned None coef: {res_fast}"
        assert coef_w0   is not None, f"w0 r1_estimate returned None coef: {res_w0}"

        assert abs(float(coef_fast) - float(coef_w0)) < 1e-4, (
            f"fast_r1_estimate coef {coef_fast:.6f} differs from "
            f"w0 r1_estimate coef {coef_w0:.6f} by more than 1e-4."
        )

    def test_no_crash_on_empty_sector_col(self):
        """fast_r1_estimate handles missing sector gracefully."""
        rng = np.random.default_rng(1)
        n_dates = 8
        rpr = 5
        n = n_dates * rpr
        dates = pd.bdate_range("2021-01-04", periods=n_dates, freq="5B").repeat(rpr)
        df = pd.DataFrame({
            "outcome": rng.integers(0, 2, size=n).astype(float),
            "stratum": rng.integers(0, 2, size=n).astype(float),
            "_fe": dates.strftime("%Y-%m-%d").tolist(),
            "_date_ts": dates.values.astype("datetime64[ns]").astype(np.int64),
        })
        result = fast_r1_estimate(
            df, "outcome", "stratum",
            fe_col="_fe",
            sector_col=None,
            n_bootstrap=30,
        )
        assert isinstance(result, dict)
        assert "coef" in result

    def test_n_total_is_post_drop_estimation_sample(self):
        """n_total in result is post-singleton-drop N; n_pre_drop is pre-drop.

        Finding (6): n_total must reflect the estimation sample (post-drop),
        not the raw input N. n_pre_drop is separately reported.
        """
        rng = np.random.default_rng(99)
        n_dates = 10
        rpr = 10
        n = n_dates * rpr
        dates = pd.bdate_range("2019-01-02", periods=n_dates, freq="5B").repeat(rpr)
        df = pd.DataFrame({
            "outcome": rng.integers(0, 2, size=n).astype(float),
            "stratum": rng.integers(0, 2, size=n).astype(float),
            "_fe": dates.strftime("%Y-%m-%d").tolist(),
            "_date_ts": dates.values.astype("datetime64[ns]").astype(np.int64),
        })
        result = fast_r1_estimate(
            df, "outcome", "stratum",
            fe_col="_fe",
            n_bootstrap=30,
        )
        assert "n_pre_drop" in result, "n_pre_drop key missing from result (finding 6)"
        assert "n_total" in result, "n_total key missing from result"
        # Estimation-sample N cannot exceed pre-drop N
        assert result["n_total"] <= result["n_pre_drop"], (
            f"n_total {result['n_total']} > n_pre_drop {result['n_pre_drop']}; "
            "post-drop N cannot exceed pre-drop N."
        )


# ---------------------------------------------------------------------------
# Regression: dropped rows do not corrupt the block structure
# ---------------------------------------------------------------------------

class TestDroppedRowsRegression:
    """Regression test: when leading rows are dropped, the block builder
    receives the survivors' sectors, not the leading rows' sectors.

    This is the 'distinct-sector survivors' regression from finding (2).
    Uses non-singleton FE cells (multiple rows per date).
    """

    def test_distinct_sector_survivors_not_leading(self):
        """Drop 2 leading rows; assert block builder sees only survivors' sector.

        The pre-fix bug (df.loc[work.index, sector_col] with positional labels
        from reset_index) would inject BAD_SECTOR into the first two survivor
        rows. This creates a 2-sector block structure (BAD_SECTOR + GOOD_SECTOR)
        with more total blocks than the survivors-only (GOOD_SECTOR) structure.
        We compute the expected n_blocks from the survivors-only frame directly
        via _fast_make_blocks and assert the estimator matches, not the mixed
        structure that the buggy code would produce.
        """
        n_lead = 2
        n_dates = 12
        rpr = 5
        n = n_dates * rpr

        rng = np.random.default_rng(55)
        dates_unique = pd.bdate_range("2017-03-01", periods=n_dates, freq="5B")
        dates = dates_unique.repeat(rpr)
        dates_ns = dates.values.astype("datetime64[ns]").astype(np.int64)

        outcome = rng.integers(0, 2, size=n).astype(float)
        outcome[:n_lead] = np.nan  # leading rows dropped

        stratum = rng.integers(0, 2, size=n).astype(float)
        fe_vals = dates.strftime("%Y-%m-%d").tolist()

        # Leading rows: BAD_SECTOR; survivors: GOOD_SECTOR
        sector = ["BAD_SECTOR"] * n_lead + ["GOOD_SECTOR"] * (n - n_lead)

        df = pd.DataFrame({
            "outcome": outcome,
            "stratum": stratum,
            "_fe": fe_vals,
            "sector": sector,
            "_date_ts": dates_ns,
        })

        result = fast_r1_estimate(
            df, "outcome", "stratum",
            fe_col="_fe",
            sector_col="sector",
            n_bootstrap=50,
            rng_seed=3,
        )

        # Survivors span n_dates unique dates → n_blocks > 0
        assert result["n_total"] > 0, "Expected non-empty result"
        assert result["n_blocks"] > 0, (
            f"Expected >0 blocks for {n - n_lead} survivors; "
            f"got n_blocks={result['n_blocks']}."
        )
        # n_total should not exceed the survivor count
        n_survivors = n - n_lead
        assert result["n_total"] <= n_survivors, (
            f"n_total {result['n_total']} > survivor count {n_survivors}"
        )

        # --- STRUCTURAL ASSERTION: n_blocks must match survivors-only structure ---
        # Compute the expected block count from survivors only (all GOOD_SECTOR).
        # The buggy code would inject BAD_SECTOR into the first 2 survivor rows,
        # producing a 2-sector block structure with MORE blocks than expected.
        # After singleton FE-cell drops, survivors are the n_dates * rpr - n_lead rows.
        # All survivors share GOOD_SECTOR → sector_id = 0 for all.
        survivor_dates_ns = dates_ns[n_lead:]
        survivor_sector_ids = np.zeros(len(survivor_dates_ns), dtype=np.intp)
        expected_blocks_survivors = _fast_make_blocks(
            survivor_dates_ns, survivor_sector_ids, block_radius_days=14
        )
        n_blocks_survivors = len(expected_blocks_survivors)

        # The buggy code would produce a 2-sector structure with a different
        # (typically larger) block count because BAD_SECTOR dates land in
        # separate blocks from GOOD_SECTOR dates.
        buggy_sector_ids = np.array(
            [1] * n_lead + [0] * (n - n_lead), dtype=np.intp
        )
        buggy_blocks = _fast_make_blocks(
            dates_ns, buggy_sector_ids, block_radius_days=14
        )
        n_blocks_buggy = len(buggy_blocks)

        # The two structures should differ (otherwise the test is not sensitive).
        # Only assert survivors match if they're distinguishable.
        if n_blocks_survivors != n_blocks_buggy:
            assert result["n_blocks"] == n_blocks_survivors, (
                f"n_blocks={result['n_blocks']} does not match survivors-only "
                f"block count={n_blocks_survivors}; buggy (mixed-sector) count "
                f"would be={n_blocks_buggy}. This indicates BAD_SECTOR was "
                f"injected into the survivor frame (the pre-fix bug)."
            )


# ---------------------------------------------------------------------------
# Finding (4): fast_r1_estimate vs W0 harness parity with sector column
# ---------------------------------------------------------------------------

class TestFastVsHarnessSectoredParity:
    """fast_r1_estimate and W0 harness r1_estimate agree on n_blocks and coef
    when a sector column is present.

    The unsectored agreement test (TestFastR1EstimateIndexAlignment.
    test_agrees_with_w0_harness_r1_on_small_frame) only checks the
    sector_col=None path. This class verifies that _fast_make_blocks and
    harness _make_blocks produce identical overlapping-block structure when a
    sector_col is supplied, so divergence in the sectored path is caught.
    """

    def test_sectored_coef_and_n_blocks_parity(self):
        """fast_r1_estimate and W0 harness agree on coef and n_blocks with sector."""
        rng = np.random.default_rng(77)
        n_dates = 10
        rpr = 8
        n = n_dates * rpr

        dates_unique = pd.bdate_range("2020-03-02", periods=n_dates, freq="5B")
        dates = dates_unique.repeat(rpr)
        dates_ns = dates.values.astype("datetime64[ns]").astype(np.int64)

        outcome = rng.integers(0, 2, size=n).astype(float)
        stratum = rng.integers(0, 2, size=n).astype(float)
        fe_vals = dates.strftime("%Y-%m-%d").tolist()

        # Two sectors alternating across rows to exercise sector-split blocks.
        sector = ["sector_A" if i % 2 == 0 else "sector_B" for i in range(n)]

        df = pd.DataFrame({
            "outcome": outcome,
            "stratum": stratum,
            "_fe": fe_vals,
            "sector": sector,
            "_date_ts": dates_ns,
            # W0 harness _prepare_binary_outcomes columns:
            "date": dates,
            "gradable": np.ones(n, dtype=bool),
            "state_rot": ["CUSHIONED"] * n,
            "state_pos": ["CUSHIONED"] * n,
            "stop5": outcome,
            "mae63": rng.uniform(-0.1, 0.0, size=n),
            "mfe63": rng.uniform(0.0, 0.1, size=n),
            "cushion_rot": np.zeros(n, dtype=float),
        })

        res_fast = fast_r1_estimate(
            df, "outcome", "stratum",
            fe_col="_fe",
            sector_col="sector",
            n_bootstrap=50,
            rng_seed=42,
        )

        res_w0 = ph.r1_estimate(
            df, "outcome", "stratum",
            fe_granularity="date",
            sector_col="sector",
            n_bootstrap=50,
            rng_seed=42,
        )

        coef_fast = res_fast.get("coef")
        coef_w0 = res_w0.get("coef")
        assert coef_fast is not None, f"fast_r1_estimate coef is None: {res_fast}"
        assert coef_w0 is not None, f"w0 r1_estimate coef is None: {res_w0}"

        assert abs(float(coef_fast) - float(coef_w0)) < 1e-4, (
            f"Sectored fast coef {coef_fast:.6f} differs from w0 coef "
            f"{coef_w0:.6f} by more than 1e-4. _fast_make_blocks and "
            f"harness _make_blocks may diverge under sector_col."
        )

        n_blk_fast = res_fast.get("n_blocks", 0)
        n_blk_w0 = res_w0.get("n_blocks", 0)
        assert n_blk_fast > 0, f"fast n_blocks={n_blk_fast} is zero"
        assert n_blk_w0 > 0, f"w0 n_blocks={n_blk_w0} is zero"
        assert n_blk_fast == n_blk_w0, (
            f"Sectored n_blocks differ: fast={n_blk_fast}, w0={n_blk_w0}. "
            f"Block construction diverges between fast and harness paths "
            f"when sector_col is supplied."
        )
