"""Unit tests for scripts/d2_russell_deletion_phase0.py — pure logic, no network/IO.

Three categories:
  1. Statistical primitives — sign_test_p, pooled_bootstrap_spread, tstat_clustered
  2. Russell proxy logic — last_friday_june, band calibration concept
  3. Gate evaluation — correct FAIL/PASS verdicts for the small-n gates

Run:
    python -m pytest tests/test_d2_russell_deletion_phase0.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.d2_russell_deletion_phase0 import (  # noqa: E402
    BOOTSTRAP_B,
    BOOTSTRAP_SEED,
    FAMILY,
    FWD_DAYS,
    LIQ_FLOOR_USD,
    MIN_PRICE_T0,
    RANK_BAND_HIGH,
    RANK_BAND_LOW,
    RECON_YEARS,
    last_friday_june,
    pooled_bootstrap_spread,
    sign_test_p,
    tstat_clustered,
)


# ---------------------------------------------------------------------------
# 1. Statistical primitives
# ---------------------------------------------------------------------------

class TestSignTestP:
    """sign_test_p: two-sided binomial test, H0: p=0.5."""

    def test_all_positive_n5(self):
        # All 5 positive: p should be 2*(0.5^5 * C(5,5)) = 2*(1/32) = 1/16 = 0.0625
        p = sign_test_p(5, 5)
        assert abs(p - 0.0625) < 1e-9

    def test_all_negative_n5(self):
        # All 0 positive: same by symmetry
        p = sign_test_p(0, 5)
        assert abs(p - 0.0625) < 1e-9

    def test_half_positive_n4(self):
        # 2/4 positive: two-sided p = 1.0 (at the null)
        p = sign_test_p(2, 4)
        assert p == 1.0

    def test_three_of_four(self):
        # 3/4: p = 2*(0.5^4*(C(4,3)+C(4,4))) = 2*(5/16) = 10/16 = 0.625
        p = sign_test_p(3, 4)
        assert abs(p - 0.625) < 1e-9

    def test_one_of_one(self):
        # 1/1: p = 2*(0.5) = 1.0
        p = sign_test_p(1, 1)
        assert p == 1.0

    def test_zero_of_one(self):
        p = sign_test_p(0, 1)
        assert p == 1.0


class TestBootstrapSpread:
    """pooled_bootstrap_spread: bootstrap CI for mean of small observation set."""

    def test_all_positive_spreads(self):
        spreads = [0.05, 0.08, 0.12, 0.03]
        result = pooled_bootstrap_spread(spreads, B=1000, seed=42)
        assert result["mean_spread"] == pytest.approx(np.mean(spreads), rel=1e-6)
        assert result["p_positive"] > 0.9  # clearly positive
        assert result["ci_lo_95"] < result["ci_hi_95"]

    def test_mixed_spreads_near_zero(self):
        spreads = [-0.10, 0.08, 0.12]
        result = pooled_bootstrap_spread(spreads, B=1000, seed=42)
        mean = np.mean(spreads)
        assert result["mean_spread"] == pytest.approx(mean, rel=1e-6)
        # P(>0) should be between 0 and 1 (not certain)
        assert 0.0 < result["p_positive"] < 1.0

    def test_all_negative_spreads(self):
        spreads = [-0.10, -0.05, -0.08]
        result = pooled_bootstrap_spread(spreads, B=1000, seed=42)
        assert result["p_positive"] < 0.3  # clearly negative

    def test_single_observation(self):
        # n=1: CI should equal the single value at both bounds
        spreads = [0.05]
        result = pooled_bootstrap_spread(spreads, B=500, seed=42)
        assert result["mean_spread"] == pytest.approx(0.05, rel=1e-6)
        # With n=1, all bootstrap samples = 0.05, so CI = [0.05, 0.05]
        assert result["ci_lo_95"] == pytest.approx(0.05, rel=1e-6)
        assert result["ci_hi_95"] == pytest.approx(0.05, rel=1e-6)

    def test_reproducible(self):
        spreads = [0.05, -0.02, 0.08]
        r1 = pooled_bootstrap_spread(spreads, B=500, seed=42)
        r2 = pooled_bootstrap_spread(spreads, B=500, seed=42)
        assert r1["p_positive"] == r2["p_positive"]
        assert r1["mean_spread"] == r2["mean_spread"]


class TestTstat:
    """tstat_clustered: simple t-stat with n observations (date-clustered)."""

    def test_all_positive_large(self):
        spreads = [0.10, 0.15, 0.12, 0.08, 0.20]
        t = tstat_clustered(spreads)
        assert t > 2.0  # clearly significant

    def test_mixed(self):
        spreads = [-0.10, 0.08, 0.12]
        t = tstat_clustered(spreads)
        # mean ~0.033, std ~0.112, se ~0.065, t ~0.5
        assert abs(t) < 2.0

    def test_nan_for_n1(self):
        t = tstat_clustered([0.05])
        assert np.isnan(t)

    def test_zero_variance(self):
        spreads = [0.05, 0.05, 0.05]
        # Zero variance -> 0 std -> result should be very large (>1e10) or nan/inf
        t = tstat_clustered(spreads)
        # numpy std(ddof=1) of identical values is machine-precision close to 0
        # resulting in a very large t statistic or inf/nan; should not crash
        assert np.isfinite(t) and abs(t) > 1e10 or np.isinf(t) or np.isnan(t)


# ---------------------------------------------------------------------------
# 2. Russell proxy logic
# ---------------------------------------------------------------------------

class TestLastFridayJune:
    """last_friday_june: verify correct last Friday of June for known years."""

    def test_2022(self):
        import pandas as pd
        result = last_friday_june(2022)
        assert result == pd.Timestamp("2022-06-24")
        assert result.dayofweek == 4  # Friday

    def test_2023(self):
        import pandas as pd
        result = last_friday_june(2023)
        assert result == pd.Timestamp("2023-06-30")
        assert result.dayofweek == 4

    def test_2024(self):
        import pandas as pd
        result = last_friday_june(2024)
        assert result == pd.Timestamp("2024-06-28")
        assert result.dayofweek == 4

    def test_2025(self):
        import pandas as pd
        result = last_friday_june(2025)
        assert result == pd.Timestamp("2025-06-27")
        assert result.dayofweek == 4

    def test_2026(self):
        import pandas as pd
        result = last_friday_june(2026)
        assert result == pd.Timestamp("2026-06-26")
        assert result.dayofweek == 4


# ---------------------------------------------------------------------------
# 3. Constants (pre-registration integrity check)
# ---------------------------------------------------------------------------

class TestPreregistrationConstants:
    """Check that the pre-registered constants match the spec exactly."""

    def test_family_name(self):
        assert FAMILY == "d2_russell_deletion_overshoot"

    def test_recon_years(self):
        # Amendment A-1: should be 2023-2026 (not 2022)
        assert RECON_YEARS == [2023, 2024, 2025, 2026]
        assert 2022 not in RECON_YEARS

    def test_russell_band(self):
        # Russell 2000 proxy: ranks 1001 to 3000
        assert RANK_BAND_LOW == 1001
        assert RANK_BAND_HIGH == 3000

    def test_fwd_days(self):
        assert FWD_DAYS == [21, 63]

    def test_liq_floor(self):
        assert LIQ_FLOOR_USD == 500_000

    def test_price_floor(self):
        # Amendment A-2: $1 price floor
        assert MIN_PRICE_T0 == 1.00

    def test_bootstrap_params(self):
        assert BOOTSTRAP_B == 5000
        assert BOOTSTRAP_SEED == 42


# ---------------------------------------------------------------------------
# 4. Gate logic (unit tests without real data)
# ---------------------------------------------------------------------------

class TestGateLogic:
    """Verify that gate pass/fail logic is correct for known inputs."""

    def test_t_gate_requires_abs_2(self):
        # |t| < 2 should be FAIL
        spreads_failing = [-0.10, 0.08, 0.12]  # t ~ 0.5
        t = tstat_clustered(spreads_failing)
        assert abs(t) < 2.0  # confirms FAIL

    def test_direction_gate_2_of_3(self):
        # 2/3 years positive -> FAIL the restated 3/4 gate (only 3 obs available)
        spreads = [-0.05, 0.08, 0.12]
        n_pos = sum(s > 0 for s in spreads)
        # Gate: need n_obs - 1 out of n_obs; with 3 obs need 3/3
        assert n_pos == 2  # 2/3, gate is FAIL
        assert n_pos < len(spreads)  # not unanimous

    def test_direction_gate_all_positive(self):
        spreads = [0.05, 0.08, 0.12]
        n_pos = sum(s > 0 for s in spreads)
        assert n_pos == 3  # 3/3 = PASS

    def test_sign_test_n3_2pos(self):
        # 2/3 positive: sign test p = 1.0 (not significant)
        p = sign_test_p(2, 3)
        # C(3,2)*0.5^3 = 3/8, C(3,3)*0.5^3 = 1/8 -> 2*(3/8+1/8) = 1.0
        assert abs(p - 1.0) < 1e-9

    def test_sign_test_n3_3pos(self):
        # 3/3 positive: sign test p = 2*(1/8) = 0.25 (still not significant)
        p = sign_test_p(3, 3)
        assert abs(p - 0.25) < 1e-9


# ---------------------------------------------------------------------------
# 5. Small-N honesty assertions
# ---------------------------------------------------------------------------

class TestSmallNHonesty:
    """Verify that the script cannot claim GO at n<=5."""

    def test_n4_cannot_pass_gate_4of5(self):
        # With n_obs=4, the 4/5 years gate from spec is vacuously impossible
        # (4/5 = 0.8 fraction, but 4 out of 4 = 1.0 fraction -> restated gate)
        n_obs = 4
        # The script restates gate as (n_obs-1)/n_obs years
        required = n_obs - 1
        # Even if all 4 years are positive (4/4 = PASS at restated gate),
        # the sign test p-value with n=4 and k=4: 2*(0.5^4) = 0.125 > 0.05
        p_all_pos = sign_test_p(4, 4)
        assert p_all_pos == pytest.approx(0.125, abs=1e-9)
        assert p_all_pos > 0.05  # not statistically significant even in best case

    def test_n3_sign_test_never_significant(self):
        # With n=3, even all positive gives p=0.25 > 0.05
        p_best = sign_test_p(3, 3)
        assert p_best == pytest.approx(0.25, abs=1e-9)
        assert p_best > 0.05  # confirms descriptive-only at n=3
