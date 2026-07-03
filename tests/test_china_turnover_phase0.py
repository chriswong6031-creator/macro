"""tests/test_china_turnover_phase0.py — W3-A abnormal-turnover signal unit tests.

Pins the SIGNAL COMPUTATION of scripts/china_turnover_phase0.py on synthetic volume series
with KNOWN abnormal windows, so the harness's math is verified independently of any backtest
result. Nearest sibling idiom: tests/test_china_alpha_w2a.py (pytest classes, synthetic
fixtures, sys.path.insert, live-verify block gated by skipif).

Covered:
  * abn_turn        — the pre-registered proxy ln(mean(vol,21d)/mean(vol,252d skip 21)) on
                      constructed spike / dry-up / flat / step series with hand-computed targets.
  * clean_daily_ret — split/ex-div artifact zeroing (|ret|>0.25 -> 0).
  * hac_t           — Newey-West mean t-stat: ~0 on centered noise, large on a strong constant,
                      sign-correct, robust to positive autocorrelation.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.china_turnover_phase0 import (  # noqa: E402
    abn_turn, clean_daily_ret, hac_t, BASE_LOOK, REC_LOOK,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Section 1 — abn_turn(): the pre-registered volume proxy
# ═══════════════════════════════════════════════════════════════════════════════

class TestAbnTurn:
    """abn_turn = ln( mean(vol, last 21d) / mean(vol, trailing 252d skip last 21d) )."""

    def _series(self, vals) -> pd.Series:
        idx = pd.bdate_range("2018-01-01", periods=len(vals))
        return pd.Series(np.asarray(vals, float), index=idx)

    def test_flat_volume_gives_zero(self):
        """Constant volume => recent mean == baseline mean => ln(1) == 0."""
        n = BASE_LOOK + REC_LOOK + 40
        s = self._series([1000.0] * n)
        at = abn_turn(s)
        last = at.iloc[-1]
        assert np.isfinite(last)
        assert abs(last) < 1e-9, f"flat volume must give abn_turn 0, got {last}"

    def test_nan_until_baseline_available(self):
        """No value until baseline window (>= base/2, min 60) + shift(rec) is satisfiable."""
        n = BASE_LOOK + REC_LOOK + 5
        s = self._series([1000.0] * n)
        at = abn_turn(s)
        # first REC_LOOK-1 recent-means are NaN; and baseline needs shift(REC_LOOK)+min_periods
        assert at.iloc[:REC_LOOK - 1].isna().all()
        # by the end there is a value
        assert np.isfinite(at.iloc[-1])

    def test_recent_spike_is_positive_and_matches_hand_value(self):
        """Baseline volume 1000 for a year, then last 21 days at 3000.

        recent mean (last 21d) = 3000. baseline = mean of the 252d ENDING 21 days ago = 1000.
        => abn_turn = ln(3000/1000) = ln 3 ≈ 1.0986.
        """
        base = [1000.0] * (BASE_LOOK + 40)
        spike = [3000.0] * REC_LOOK
        s = self._series(base + spike)
        at = abn_turn(s)
        last = at.iloc[-1]
        assert last == pytest.approx(np.log(3.0), abs=1e-6), f"expected ln3≈1.0986, got {last}"
        assert last > 0

    def test_recent_dryup_is_negative_and_matches_hand_value(self):
        """Baseline 1000, last 21 days at 250 => ln(250/1000) = ln 0.25 ≈ -1.386 (negative)."""
        base = [1000.0] * (BASE_LOOK + 40)
        dry = [250.0] * REC_LOOK
        s = self._series(base + dry)
        at = abn_turn(s)
        last = at.iloc[-1]
        assert last == pytest.approx(np.log(0.25), abs=1e-6), f"expected ln0.25≈-1.386, got {last}"
        assert last < 0

    def test_baseline_excludes_the_recent_window(self):
        """Critical: the baseline must NOT include the recent spike (skip last REC_LOOK).

        If the baseline erroneously included the recent 21 high days, the ratio would be
        pulled toward 1 and abn_turn would be materially smaller than ln3. We assert it is
        exactly ln3, which is only true if the recent window is excluded from the baseline.
        """
        base = [1000.0] * (BASE_LOOK + 40)
        spike = [3000.0] * REC_LOOK
        s = self._series(base + spike)
        last = abn_turn(s).iloc[-1]
        # if baseline included the recent window it would be > ln3-shrunk (i.e. < ln3)
        assert last == pytest.approx(np.log(3.0), abs=1e-6)

    def test_partial_spike_magnitude_ordering(self):
        """A bigger recent spike => strictly larger abn_turn (monotone in the recent ratio)."""
        base = [1000.0] * (BASE_LOOK + 40)
        small = abn_turn(self._series(base + [1500.0] * REC_LOOK)).iloc[-1]
        big = abn_turn(self._series(base + [4000.0] * REC_LOOK)).iloc[-1]
        assert small < big
        assert small == pytest.approx(np.log(1.5), abs=1e-6)
        assert big == pytest.approx(np.log(4.0), abs=1e-6)

    def test_zero_baseline_maps_to_nan_not_inf(self):
        """A degenerate zero-volume baseline must yield NaN (never +/-inf into a rank)."""
        base = [0.0] * (BASE_LOOK + 40)
        s = self._series(base + [1000.0] * REC_LOOK)
        last = abn_turn(s).iloc[-1]
        assert not np.isinf(last)
        assert np.isnan(last)

    def test_output_index_aligned_to_input(self):
        n = BASE_LOOK + REC_LOOK + 30
        s = self._series([1000.0] * n)
        at = abn_turn(s)
        assert list(at.index) == list(s.index)


# ═══════════════════════════════════════════════════════════════════════════════
# Section 2 — clean_daily_ret(): split / ex-div artifact hygiene
# ═══════════════════════════════════════════════════════════════════════════════

class TestCleanDailyRet:
    """Daily returns with |ret| > 0.25 (beyond the A-share ±20% limit envelope) are zeroed."""

    def _closes(self, vals):
        idx = pd.bdate_range("2020-01-01", periods=len(vals))
        return pd.Series(np.asarray(vals, float), index=idx)

    def test_normal_returns_pass_through(self):
        c = self._closes([100, 105, 103, 108, 110])   # all |ret| < 25%
        r = clean_daily_ret(c)
        assert r.iloc[1] == pytest.approx(0.05)
        assert r.iloc[2] == pytest.approx(103 / 105 - 1)

    def test_split_jump_down_is_zeroed(self):
        """A 2:1 split halves the raw price (-50% one-day 'return') => zeroed, not -0.5."""
        c = self._closes([100, 100, 50, 50, 50])       # -50% jump at index 2
        r = clean_daily_ret(c)
        assert r.iloc[2] == 0.0, "split -50% jump must be zeroed"
        assert r.iloc[3] == 0.0  # 50->50 flat

    def test_exdiv_or_bonus_jump_up_is_zeroed(self):
        c = self._closes([100, 100, 160, 160])          # +60% jump => artifact
        r = clean_daily_ret(c)
        assert r.iloc[2] == 0.0

    def test_boundary_just_below_cap_kept(self):
        """+24% (below the 0.25 cap) is a real limit-adjacent move — kept."""
        c = self._closes([100, 124.0])
        r = clean_daily_ret(c)
        assert r.iloc[1] == pytest.approx(0.24)

    def test_boundary_just_above_cap_zeroed(self):
        c = self._closes([100, 126.0])                  # +26% > cap
        r = clean_daily_ret(c)
        assert r.iloc[1] == 0.0

    def test_first_value_nan_preserved(self):
        c = self._closes([100, 101])
        r = clean_daily_ret(c)
        assert np.isnan(r.iloc[0])


# ═══════════════════════════════════════════════════════════════════════════════
# Section 3 — hac_t(): Newey-West mean t-stat
# ═══════════════════════════════════════════════════════════════════════════════

class TestHacT:
    def test_centered_noise_is_small_t(self):
        rng = np.random.default_rng(0)
        x = rng.normal(0, 1, 500)
        t = hac_t(x)
        assert abs(t) < 3, f"centered noise should not be significant, got t={t}"

    def test_strong_positive_constant_is_large_positive_t(self):
        rng = np.random.default_rng(1)
        x = 0.5 + rng.normal(0, 0.1, 300)              # mean far from 0, low noise
        t = hac_t(x)
        assert t > 10, f"strong positive mean must give large +t, got {t}"

    def test_sign_flips_with_mean_sign(self):
        rng = np.random.default_rng(2)
        x = -0.3 + rng.normal(0, 0.1, 300)
        t = hac_t(x)
        assert t < -10

    def test_too_few_points_returns_nan(self):
        assert np.isnan(hac_t(np.array([0.1, 0.2, 0.3])))

    def test_hac_widens_se_under_positive_autocorrelation(self):
        """With positive serial correlation the HAC t must be SMALLER (larger SE) than the
        naive iid t — the whole point of the Newey-West correction."""
        rng = np.random.default_rng(3)
        e = rng.normal(0, 1, 600)
        # AR(1) with strong positive rho around a small positive mean
        x = np.empty(600)
        x[0] = e[0]
        for i in range(1, 600):
            x[i] = 0.7 * x[i - 1] + e[i]
        x = x + 0.15
        hac = hac_t(x, lags=8)
        naive = float(x.mean() / (x.std(ddof=0) / np.sqrt(len(x))))
        assert abs(hac) < abs(naive), (
            f"HAC t ({hac:.2f}) must be smaller in magnitude than naive iid t ({naive:.2f}) "
            "under positive autocorrelation")

    def test_nan_values_dropped(self):
        """Interior NaNs are dropped; the t is computed on the finite subset (which must vary,
        else the variance is 0 and the t is legitimately undefined)."""
        rng = np.random.default_rng(7)
        x = 0.4 + rng.normal(0, 0.1, 30)
        x[3] = np.nan
        x[10] = np.nan
        t = hac_t(x)
        assert np.isfinite(t) and t > 0


# ═══════════════════════════════════════════════════════════════════════════════
# Section 4 — Live smoke test (requires the raw plane); asserts the signal builds
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(
    not (ROOT / "data" / "china_stocks_raw").exists(),
    reason="requires local data/china_stocks_raw",
)
class TestLiveSignalBuilds:
    def test_abn_turn_builds_on_a_real_name(self):
        f = sorted((ROOT / "data" / "china_stocks_raw").glob("*.parquet"))[0]
        vol = pd.read_parquet(f)["volume"]
        at = abn_turn(vol)
        # last value must be finite for a liquid deep-history name
        assert np.isfinite(at.iloc[-1]), "abn_turn must resolve on a real long-history name"
        # the signal is a within-name volume ratio => most values in a sane band
        finite = at.dropna()
        assert len(finite) > 1000
        assert finite.abs().median() < 2.0, "typical |abn_turn| should be modest (< ln7)"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
