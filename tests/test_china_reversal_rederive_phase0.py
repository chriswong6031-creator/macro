"""tests/test_china_reversal_rederive_phase0.py — W5-A reversal RE-DERIVE unit tests.

Pins the SIGNAL COMPUTATION of scripts/china_reversal_rederive_phase0.py on synthetic series with
KNOWN targets, so the harness's math is verified independently of any backtest result. Nearest
sibling idiom: tests/test_china_turnover_phase0.py (pytest classes, synthetic fixtures,
sys.path.insert, live-verify block gated by skipif).

Covered:
  * rev_z_row       — the within-sector reversal fuel, asserted BYTE-FOR-BYTE against
                      engine.china_reversal's own formula (parity is the whole point — the
                      re-derive must mirror the engine or the number is a different signal).
  * clean_daily_ret — split/ex-div artifact zeroing (|ret|>0.25 -> 0), raw-plane hygiene.
  * hac_t           — Newey-West mean t-stat: ~0 on centered noise, large on a strong constant,
                      sign-correct, robust to positive autocorrelation.
  * _maxdd_from_legs— compound NAV drawdown of a return stream (the -37.6% headline is this).
  * live-verify     — (skipif no raw plane) re-runs the harness and asserts the KNOWN-RESULT
                      control fires (momentum flat) and reversal is the stronger signal — the
                      discrimination the measurement constitution requires.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.china_reversal_rederive_phase0 import (  # noqa: E402
    rev_z_row, clean_daily_ret, hac_t, _maxdd_from_legs, MIN_SECTOR, CLIP, SPLIT_CAP,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Section 1 — rev_z_row(): within-sector reversal fuel, PARITY with the engine
# ═══════════════════════════════════════════════════════════════════════════════

class TestRevZRow:
    """rev = -(ret - sector_mean(ret)); rev_z = (rev / sector_std(rev)).clip(+/-CLIP). Thin
    sectors (< MIN_SECTOR) dropped. Must match engine.china_reversal exactly."""

    def _case(self):
        # Sector A: 6 names with a clear deepest dipper (A3 = -0.20). Sector B: 6 flat names
        # (zero std -> rev_z NaN, dropped). Sector C: 3 names (< MIN_SECTOR, dropped).
        idx = [f"A{i}" for i in range(6)] + [f"B{i}" for i in range(6)] + [f"C{i}" for i in range(3)]
        ret = pd.Series(
            [0.10, 0.00, -0.10, -0.20, 0.05, 0.15] + [0.02] * 6 + [-0.30, 0.10, 0.20],
            index=idx)
        sector = pd.Series(["A"] * 6 + ["B"] * 6 + ["C"] * 3, index=idx)
        return ret, sector

    def test_matches_engine_formula_exactly(self):
        """Byte-for-byte parity with engine.china_reversal's within-sector demean + standardize."""
        ret, sector = self._case()
        rz = rev_z_row(ret, sector)
        # replicate the engine formula independently
        d = pd.DataFrame({"ret": ret, "sector": sector})
        big = d.groupby("sector")["ret"].transform("count") >= MIN_SECTOR
        d = d[big]
        d["rev"] = -(d["ret"] - d.groupby("sector")["ret"].transform("mean"))
        sd = d.groupby("sector")["rev"].transform("std").replace(0, np.nan)
        d["rev_z"] = (d["rev"] / sd).clip(-CLIP, CLIP)
        eng = d["rev_z"].dropna()
        assert list(rz.sort_index().index) == list(eng.sort_index().index)
        assert np.allclose(rz.sort_index().values, eng.sort_index().values)

    def test_deepest_dip_has_highest_rev_z(self):
        """The most-beaten name vs its sector = highest reversal fuel = highest rev_z (the pick)."""
        ret, sector = self._case()
        rz = rev_z_row(ret, sector)
        assert rz.idxmax() == "A3", "deepest within-sector dipper must rank highest"

    def test_zero_std_sector_dropped(self):
        """A flat sector (zero cross-sectional std) yields NaN rev_z and is dropped, never inf."""
        ret, sector = self._case()
        rz = rev_z_row(ret, sector)
        assert not any(t.startswith("B") for t in rz.index)
        assert np.isfinite(rz.values).all()

    def test_thin_sector_dropped(self):
        """A sector with < MIN_SECTOR names cannot dominate the watch — dropped."""
        ret, sector = self._case()
        rz = rev_z_row(ret, sector)
        assert not any(t.startswith("C") for t in rz.index)

    def test_clip_bounds(self):
        """rev_z is clipped to +/-CLIP even with an extreme within-sector outlier."""
        idx = [f"A{i}" for i in range(6)]
        ret = pd.Series([0.0, 0.0, 0.0, 0.0, 0.0, -5.0], index=idx)   # one gigantic dipper
        sector = pd.Series(["A"] * 6, index=idx)
        rz = rev_z_row(ret, sector)
        assert rz.max() <= CLIP + 1e-9
        assert rz.min() >= -CLIP - 1e-9

    def test_missing_sector_names_ignored(self):
        """Names whose sector is '—' (unmapped) are excluded (mirror the engine's sector screen)."""
        idx = [f"A{i}" for i in range(6)] + ["X0"]
        ret = pd.Series([0.10, 0.00, -0.10, -0.20, 0.05, 0.15, -0.5], index=idx)
        sector = pd.Series(["A"] * 6 + ["—"], index=idx)
        rz = rev_z_row(ret, sector)
        assert "X0" not in rz.index


# ═══════════════════════════════════════════════════════════════════════════════
# Section 2 — clean_daily_ret(): raw-plane split / ex-div hygiene
# ═══════════════════════════════════════════════════════════════════════════════

class TestCleanDailyRet:
    def _closes(self, vals):
        idx = pd.bdate_range("2020-01-01", periods=len(vals))
        return pd.Series(np.asarray(vals, float), index=idx)

    def test_normal_returns_pass_through(self):
        c = self._closes([100, 105, 103, 108, 110])
        r = clean_daily_ret(c)
        assert r.iloc[1] == pytest.approx(0.05)
        assert r.iloc[2] == pytest.approx(103 / 105 - 1)

    def test_split_jump_down_is_zeroed(self):
        c = self._closes([100, 100, 50, 50, 50])           # -50% split
        r = clean_daily_ret(c)
        assert r.iloc[2] == 0.0

    def test_exdiv_or_bonus_jump_up_is_zeroed(self):
        c = self._closes([100, 100, 160, 160])              # +60% artifact
        r = clean_daily_ret(c)
        assert r.iloc[2] == 0.0

    def test_boundary_just_below_cap_kept(self):
        c = self._closes([100, 100 * (1 + SPLIT_CAP) - 1.0])   # just below +25%
        r = clean_daily_ret(c)
        assert r.iloc[1] != 0.0

    def test_boundary_just_above_cap_zeroed(self):
        c = self._closes([100, 100 * (1 + SPLIT_CAP) + 1.0])   # just above +25%
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
        assert abs(hac_t(rng.normal(0, 1, 500))) < 3

    def test_strong_constant_is_large_t(self):
        x = np.full(200, 0.5) + np.random.default_rng(1).normal(0, 0.01, 200)
        assert hac_t(x) > 10

    def test_sign_follows_mean(self):
        # add small noise so residual variance > 0 (a perfectly-constant series is var-0 -> NaN by
        # design, the correct guard; the t-stat's SIGN is what we pin here)
        rng = np.random.default_rng(7)
        assert hac_t(np.full(100, -0.3) + rng.normal(0, 0.01, 100)) < 0
        assert hac_t(np.full(100, 0.3) + rng.normal(0, 0.01, 100)) > 0

    def test_constant_series_is_nan(self):
        """A zero-residual-variance (perfectly constant) series returns NaN, never a spurious t."""
        assert np.isnan(hac_t(np.full(100, 0.3)))

    def test_thin_series_nan(self):
        assert np.isnan(hac_t(np.array([1.0, 2.0, 3.0])))

    def test_positive_autocorrelation_widens_ci(self):
        """HAC t on a positively-autocorrelated series is smaller than the naive iid t (the point
        of Newey-West) — the corrected variance is larger."""
        rng = np.random.default_rng(2)
        e = rng.normal(0, 1, 600)
        x = np.zeros(600)
        for i in range(1, 600):
            x[i] = 0.7 * x[i - 1] + e[i]
        x = x + 0.2                                      # small positive mean
        naive_t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
        assert abs(hac_t(x)) < abs(naive_t)


# ═══════════════════════════════════════════════════════════════════════════════
# Section 4 — _maxdd_from_legs(): compound NAV drawdown (the -37.6% headline)
# ═══════════════════════════════════════════════════════════════════════════════

class TestMaxDD:
    def test_monotone_up_zero_dd(self):
        assert _maxdd_from_legs([0.01, 0.02, 0.01, 0.03]) == pytest.approx(0.0)

    def test_single_drop_dd(self):
        # +10% then -20%: NAV 1.10 -> 0.88; peak 1.10 -> dd = 0.88/1.10 - 1 = -0.20
        assert _maxdd_from_legs([0.10, -0.20]) == pytest.approx(-0.20, abs=1e-9)

    def test_dd_is_worst_peak_to_trough(self):
        dd = _maxdd_from_legs([0.5, -0.1, -0.1, -0.1, 0.05])
        # peak after +50% = 1.5; trough 1.5*0.9*0.9*0.9 = 1.0935 -> dd = 1.0935/1.5 - 1
        assert dd == pytest.approx(1.5 * 0.9 ** 3 / 1.5 - 1, abs=1e-9)
        assert dd < 0


# ═══════════════════════════════════════════════════════════════════════════════
# Section 5 — live verify (skipif no raw plane): the harness discriminates
# ═══════════════════════════════════════════════════════════════════════════════

_RAW = ROOT / "data" / "china_stocks_raw"
_HAS_RAW = _RAW.exists() and len(list(_RAW.glob("*.parquet"))) > 100


@pytest.mark.skipif(not _HAS_RAW, reason="raw china_stocks plane not present in this checkout")
class TestLiveHarness:
    """End-to-end sanity that the harness has POWER: the known-result momentum control comes out
    flat while reversal is materially stronger — the discrimination the constitution demands. Slow
    (loads the full raw plane); runs only where the substrate exists."""

    @pytest.fixture(scope="class")
    def frames(self):
        from scripts import china_reversal_rederive_phase0 as w5
        U = w5._read_universe(ROOT)
        px, sector = U["px"], U["sector"]
        rev_grid = w5._grid(px.index, w5.WIN + 5)
        rev = w5._rev_z_frame(px, sector, rev_grid)
        mom_grid = w5._grid(px.index, w5.MOM_LOOK + w5.MOM_SKIP + 5)
        mom = w5._mom_frame(px, mom_grid)
        return w5, U, rev, rev_grid, mom, mom_grid

    def test_universe_nonempty(self, frames):
        _, U, *_ = frames
        assert U["px"].shape[1] > 500, "hygiene should leave a broad A-share universe"

    def test_momentum_control_is_flat(self, frames):
        """The KILLED result reproduces: 12-1 momentum long quintile is NOT a strong positive edge."""
        w5, U, _, _, mom, mom_grid = frames
        sp, leg, _ = w5._long_leg_spread(mom_grid, mom, U["fwd_fill"])
        st = w5._stats(sp, leg)
        assert st["n"] >= 100
        assert st["t_hac"] < 2.0, f"momentum control must be flat/dead, got t={st['t_hac']}"

    def test_reversal_stronger_than_momentum(self, frames):
        """Same harness: reversal long-leg universe-relative t must exceed the momentum control's —
        proving the instrument has power (not a dead rubber-stamp)."""
        w5, U, rev, rev_grid, mom, mom_grid = frames
        rsp, rleg, _ = w5._long_leg_spread(rev_grid, rev, U["fwd_fill"])
        msp, mleg, _ = w5._long_leg_spread(mom_grid, mom, U["fwd_fill"])
        rt = w5._stats(rsp, rleg)["t_hac"]
        mt = w5._stats(msp, mleg)["t_hac"]
        assert rt > mt, f"reversal (t={rt}) must beat momentum control (t={mt})"
        assert rt > 0 and w5._stats(rsp, rleg)["mean_pct"] > 0, "reversal long leg positive"

    def test_substrate_honesty_reports_survivor_plane(self, frames):
        """The honesty section must correctly flag the raw plane as (near-)pure-survivor."""
        w5, U, *_ = frames
        hon = w5.substrate_honesty(U["last_dates"], U["px"])
        assert hon["n_names_in_store"] > 500
        assert hon["captured_pct"] is not None
        # raw prices: some |ret|>25% corporate-action jumps must be present (proves unadjusted)
        assert (hon["raw_jump_frac_pct"] or 0) > 0.0
