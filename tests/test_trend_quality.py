"""Residual trend-quality battery (engine/trend_quality.py).

The battery exists to answer one question — "a stock rising 20% on two gap days should
rank differently from one rising 20% through persistent accumulation" — so the headline
test is exactly that discrimination, on paths constructed to have the SAME total move.
The rest pin the traps: the killed measure must stay out of the composite, sign
alignment must actually flip the negated measures, and an absent input must produce an
absent measure rather than a neutral-looking number.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")

from engine import trend_quality as tq  # noqa: E402

N = 126


def _series(eps: np.ndarray):
    idx = pd.bdate_range("2025-01-01", periods=len(eps))
    e = pd.Series(eps, index=idx)
    close = (1 + e).cumprod() * 100.0
    return e, close, close * 1.01, close * 0.99


TOTAL = np.log(1.20)          # both paths are constructed to sum to EXACTLY this


def _gappy(seed: int = 3):
    """+20% from two giant days on an otherwise flat, noisy path."""
    rng = np.random.default_rng(seed)
    e = rng.normal(0, 0.004, N)
    e -= e.mean()                          # zero-mean noise, so the gaps carry it all
    e[40] += TOTAL / 2
    e[95] += TOTAL / 2
    return e


def _steady(seed: int = 3):
    """The same +20%, accumulated persistently."""
    rng = np.random.default_rng(seed)
    e = rng.normal(0, 0.004, N)
    e -= e.mean()
    return e + TOTAL / N


class TestTheMotivatingCase:
    """Same total move, different construction — the battery must separate them."""

    def setup_method(self):
        self.g, self.s = _gappy(), _steady()
        assert self.g.sum() == pytest.approx(self.s.sum(), abs=1e-12), \
            "the whole point is that the two paths have the SAME total move"
        self.mg = tq.measures(*_series(self.g)[:2], high=_series(self.g)[2],
                              low=_series(self.g)[3])
        self.ms = tq.measures(*_series(self.s)[:2], high=_series(self.s)[2],
                              low=_series(self.s)[3])

    def test_concentration_flags_the_gappy_path(self):
        assert self.mg["top3_share"] > 3 * self.ms["top3_share"]

    def test_steady_path_has_the_stronger_trend_tstat(self):
        assert self.ms["slope_t"] > self.mg["slope_t"]

    def test_steady_path_has_more_positive_days(self):
        assert self.ms["pos_days"] > self.mg["pos_days"]

    def test_steady_path_has_the_shallower_drawdown(self):
        assert self.ms["max_dd"] > self.mg["max_dd"]      # both <= 0; larger = shallower

    def test_composite_ranks_steady_above_gappy(self):
        """The end-to-end claim: sign alignment + z-scoring must put the accumulator
        ahead of the gapper, not merely produce different numbers."""
        panel = pd.DataFrame({"GAP": self.mg, "STEADY": self.ms}).T
        comp = tq.composite(panel, min_measures=3)
        assert comp["STEADY"] > comp["GAP"]


class TestMeasures:
    def test_slope_t_scales_with_trend_cleanliness_not_size(self):
        """Two paths with the SAME slope but different noise must not score the same —
        that is what dividing by the standard error buys."""
        n = 120
        x = np.arange(n, dtype=float)
        clean = tq._slope_t(0.01 * x + np.random.default_rng(1).normal(0, 0.01, n))
        noisy = tq._slope_t(0.01 * x + np.random.default_rng(1).normal(0, 0.5, n))
        assert clean > noisy * 3

    def test_impulse_legs_counts_distinct_pushes(self):
        """One clean advance is 1 leg; a stair-step of separate pushes counts more."""
        one = np.linspace(0, 1, 200)
        legs_one = tq._impulse_legs(one, thresh=0.05)
        stair = np.concatenate([np.linspace(0, 1, 50), np.linspace(1, 0.7, 20),
                                np.linspace(0.7, 1.8, 50), np.linspace(1.8, 1.5, 20),
                                np.linspace(1.5, 2.6, 50)])
        legs_stair = tq._impulse_legs(stair, thresh=0.05)
        assert legs_one == 1
        assert legs_stair >= 3
        assert legs_stair > legs_one

    def test_top3_share_denominator_is_absolute_movement(self):
        """A near-zero NET return must not blow the ratio up — the denominator is the
        sum of |daily move|, so the measure stays in [0,1] on a round-trip path."""
        e = np.array([0.10, -0.10, 0.09, -0.09] * 10)
        assert 0.0 <= tq._top3_share(e) <= 1.0

    def test_top3_share_is_one_when_three_days_are_everything(self):
        e = np.zeros(60)
        e[[5, 20, 40]] = [0.1, 0.1, 0.1]
        assert tq._top3_share(e) == pytest.approx(1.0)

    def test_max_dd_is_zero_on_a_monotone_path_and_negative_otherwise(self):
        assert tq._max_dd(np.linspace(0, 1, 50)) == pytest.approx(0.0)
        assert tq._max_dd(np.array([0.0, 1.0, 0.4, 0.9])) == pytest.approx(-0.6)

    def test_ud_vol_is_symmetric_in_log_space(self):
        e = np.array([0.01, -0.01] * 30)
        heavy_up = np.where(e > 0, 2e6, 1e6)
        heavy_dn = np.where(e > 0, 1e6, 2e6)
        assert tq._ud_vol(e, heavy_up) == pytest.approx(-tq._ud_vol(e, heavy_dn), rel=1e-9)
        assert tq._ud_vol(e, heavy_up) > 0

    def test_atr_dist_grows_with_distance_from_origin(self):
        e, close, hi, lo = _series(_steady())
        near = tq.measures(e.iloc[:40], close.iloc[:40], high=hi.iloc[:40], low=lo.iloc[:40])
        far = tq.measures(e, close, high=hi, low=lo)
        assert far["atr_dist"] > near["atr_dist"]


class TestAbsenceIsAbsence:
    def test_missing_volume_leaves_ud_vol_nan_not_neutral(self):
        e, close, hi, lo = _series(_steady())
        m = tq.measures(e, close, high=hi, low=lo, volume=None)
        assert np.isnan(m["ud_vol"]), "an unmeasured factor must not get a value"

    def test_missing_high_low_leaves_atr_dist_nan(self):
        e, close, _, _ = _series(_steady())
        assert np.isnan(tq.measures(e, close)["atr_dist"])

    def test_too_short_a_window_returns_all_nan(self):
        e, close, _, _ = _series(_steady())
        m = tq.measures(e.iloc[:5], close.iloc[:5])
        assert all(np.isnan(v) for v in m.values())

    def test_resid_vs_hist_excludes_the_window_being_scored(self):
        """If the window leaked into its own baseline the measure would be biased
        toward zero by construction."""
        idx = pd.bdate_range("2024-01-01", periods=400)
        eps = pd.Series(np.concatenate([np.zeros(300), np.full(100, 0.01)]), index=idx)
        win = eps.iloc[-100:]
        m = tq.measures(win, (1 + win).cumprod() * 100, hist_eps=eps)
        # history (the flat 300) has zero mean and zero std -> undefined, must be NaN
        assert np.isnan(m["resid_vs_hist"])
        noisy = pd.Series(np.concatenate([
            np.random.default_rng(4).normal(0, 0.005, 300), np.full(100, 0.01)]), index=idx)
        w2 = noisy.iloc[-100:]
        m2 = tq.measures(w2, (1 + w2).cumprod() * 100, hist_eps=noisy)
        assert m2["resid_vs_hist"] > 1.0, "a strong recent run should read high vs history"


class TestKilledMeasureStaysOut:
    def test_resid_accel_is_not_in_the_quality_set(self):
        assert "resid_accel" not in tq.QUALITY_MEASURES
        assert "resid_accel" in tq.DIAGNOSTIC_MEASURES

    def test_composite_refuses_a_diagnostic_measure(self):
        """A caller trying to rank on the killed measure must fail loudly. Silently
        dropping it would let the kill be undone by a typo."""
        panel = pd.DataFrame({"A": {"slope_t": 1.0, "resid_accel": 0.5},
                              "B": {"slope_t": 2.0, "resid_accel": 0.1}}).T
        with pytest.raises(ValueError, match="diagnostic-only"):
            tq.composite(panel, measures_used=("slope_t", "resid_accel"), min_measures=1)

    def test_resid_accel_is_still_computed_for_diagnosis(self):
        e, close, _, _ = _series(_steady())
        assert np.isfinite(tq.measures(e, close)["resid_accel"])


class TestComposite:
    @staticmethod
    def _panel_varying(measure: str, values: np.ndarray, seed: int) -> pd.DataFrame:
        """Cross-section where ONLY `measure` carries signal; the rest are independent
        noise. Varying two measures together would let their contributions cancel and
        hide a sign error."""
        rng = np.random.default_rng(seed)
        n = len(values)
        base = {"slope_t": rng.normal(0, 1, n), "pos_days": rng.uniform(0.4, 0.6, n),
                "max_dd": -rng.uniform(0.01, 0.5, n), "top3_share": rng.uniform(0.05, 0.9, n)}
        base[measure] = values
        return pd.DataFrame(base, index=[f"T{i}" for i in range(n)])

    def test_more_top3_concentration_lowers_quality(self):
        conc = np.linspace(0.05, 0.9, 40)
        comp = tq.composite(self._panel_varying("top3_share", conc, 21), min_measures=4)
        assert comp.corr(pd.Series(conc, index=comp.index)) < -0.3, \
            "higher top-3-day concentration must LOWER trend quality"

    def test_shallower_drawdown_raises_quality(self):
        """`max_dd` is already oriented (shallow = larger = better). Negating it would
        flip this correlation while still producing plausible-looking numbers."""
        dd = np.linspace(-0.5, -0.01, 40)
        comp = tq.composite(self._panel_varying("max_dd", dd, 22), min_measures=4)
        assert comp.corr(pd.Series(dd, index=comp.index)) > 0.3, \
            "a shallower drawdown must RAISE trend quality"

    def test_min_measures_blanks_a_thinly_measured_name(self):
        """A realistic cross-section (a 2-name panel cannot z-score at all), with one
        name measured on a single leg — it must come back absent, not ranked."""
        rng = np.random.default_rng(6)
        rows = {f"T{i}": {"slope_t": rng.normal(), "pos_days": rng.uniform(0.3, 0.7),
                          "max_dd": -rng.uniform(0.01, 0.3),
                          "top3_share": rng.uniform(0.05, 0.6)} for i in range(20)}
        rows["THIN"] = {"slope_t": 2.0, "pos_days": np.nan, "max_dd": np.nan,
                        "top3_share": np.nan}
        comp = tq.composite(pd.DataFrame(rows).T, min_measures=4)
        assert np.isfinite(comp["T0"])
        assert np.isnan(comp["THIN"])

    def test_sector_neutral_demeans_within_sector(self):
        panel = pd.DataFrame({
            "A1": {"slope_t": 3.0, "pos_days": 0.7, "max_dd": -0.01, "top3_share": 0.05},
            "A2": {"slope_t": 2.5, "pos_days": 0.65, "max_dd": -0.02, "top3_share": 0.06},
            "B1": {"slope_t": -2.0, "pos_days": 0.3, "max_dd": -0.20, "top3_share": 0.40},
            "B2": {"slope_t": -2.5, "pos_days": 0.35, "max_dd": -0.25, "top3_share": 0.45},
        }).T
        sec = pd.Series({"A1": "A", "A2": "A", "B1": "B", "B2": "B"})
        sn = tq.composite(panel, min_measures=4, sectors=sec)
        assert sn.groupby(sec).mean().abs().max() < 1e-9
        assert sn["A1"] > sn["A2"] and sn["B1"] > sn["B2"]


class TestPanel:
    def test_panel_scores_the_same_window_the_momentum_signal_uses(self):
        """Quality must describe the trend momentum ranked — a different window would
        answer a different question."""
        idx = pd.bdate_range("2022-01-01", periods=500)
        rng = np.random.default_rng(9)
        eps = pd.DataFrame({f"T{i}": rng.normal(0, 0.006, 500) for i in range(15)}, index=idx)
        closes = (1 + eps).cumprod() * 100
        spike = eps.copy()
        spike.iloc[-10:, :] += 0.05                 # entirely inside the skipped tail
        a = tq.panel(eps, closes, form=252, skip=21)
        b = tq.panel(spike, (1 + spike).cumprod() * 100, form=252, skip=21)
        assert not a.empty and not b.empty
        assert np.allclose(a["slope_t"].to_numpy(), b["slope_t"].to_numpy(), atol=1e-9), \
            "a move inside the skipped window leaked into the scored window"

    def test_panel_returns_empty_when_history_is_too_short(self):
        idx = pd.bdate_range("2025-01-01", periods=60)
        eps = pd.DataFrame({f"T{i}": np.zeros(60) for i in range(15)}, index=idx)
        assert tq.panel(eps, (1 + eps).cumprod() * 100, form=252, skip=21).empty
