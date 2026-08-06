"""Multi-window multi-factor residual momentum (engine/residual_momentum.py).

The tests that matter here are the ones a plausible-looking refactor would break
SILENTLY: causality (a residual that peeks forward still looks like a residual), the
factor-leg stripping actually removing the factor (not just changing numbers), and the
window de-duplication that keeps one construction from being counted twice in the
multiple-testing correction.
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

from engine import residual_momentum as rm  # noqa: E402

WIN = 252


def _panel(n_days: int = 1200, n_names: int = 30, seed: int = 7):
    """Synthetic panel with a KNOWN market beta and a KNOWN factor loading that varies
    WITHIN sector — heterogeneous on purpose, so the sector leg cannot absorb the factor
    and the factor leg has something real to strip."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2018-01-01", periods=n_days)
    market = pd.Series(rng.normal(0, 0.01, n_days), index=idx)
    leg = pd.Series(rng.normal(0, 0.009, n_days), index=idx)
    cols, sect, betas = {}, {}, {}
    for i in range(n_names):
        sec = "A" if i < n_names // 2 else "B"
        bf = rng.uniform(-1.5, 1.5)
        r = market + bf * leg + pd.Series(rng.normal(0, 0.006, n_days), index=idx)
        cols[f"T{i}"] = (1 + r).cumprod() * 100.0
        sect[f"T{i}"], betas[f"T{i}"] = sec, bf
    return pd.DataFrame(cols), market, sect, leg, pd.Series(betas)


class TestWindows:
    def test_the_five_requested_windows_collapse_to_four_distinct(self):
        """'12-1 months' and '12 months excluding the last 21 days' are the SAME
        construction. The duplicate must be visible, not silently double-counted."""
        assert len(rm.WINDOWS) == 5
        assert len(rm.distinct_windows()) == 4
        assert rm.duplicate_windows() == {"w12_ex21": "w12_1"}
        assert rm.WINDOWS["w12_ex21"] == rm.WINDOWS["w12_1"]

    def test_distinct_windows_keeps_the_first_key(self):
        assert "w12_1" in rm.distinct_windows()
        assert "w12_ex21" not in rm.distinct_windows()

    def test_window_specs_match_the_request(self):
        assert rm.WINDOWS["w3_1"] == (63, 21)
        assert rm.WINDOWS["w6_1"] == (126, 21)
        assert rm.WINDOWS["w12_1"] == (252, 21)
        assert rm.WINDOWS["w6_ex5"] == (126, 5)


class TestResiduals:
    def test_market_beta_is_stripped(self):
        closes, market, sect, _, _ = _panel()
        eps = rm.residuals(closes, market, sect, WIN, 1.0, None)
        tail = eps.iloc[WIN + 50:]
        corr = tail.corrwith(market.reindex(tail.index)).abs().mean()
        assert corr < 0.10, f"market beta survived the residual (|corr| {corr:.3f})"

    def test_factor_leg_is_stripped_only_when_supplied(self):
        """The discriminating test: WITHOUT the leg the residual still carries the
        factor; WITH it, the exposure collapses. A refactor that wires the leg in but
        never subtracts it would pass a mere 'runs without error' check."""
        closes, market, sect, leg, _ = _panel()
        two = rm.residuals(closes, market, sect, WIN, 1.0, None)
        three = rm.residuals(closes, market, sect, WIN, 1.0, {"value": leg})
        t = slice(WIN + 50, None)
        c2 = two.iloc[t].corrwith(leg.reindex(two.iloc[t].index)).abs().mean()
        c3 = three.iloc[t].corrwith(leg.reindex(three.iloc[t].index)).abs().mean()
        assert c2 > 0.20, f"the synthetic factor was not actually loaded (|corr| {c2:.3f})"
        assert c3 < 0.10, f"the factor leg was not stripped (|corr| {c3:.3f})"
        assert c3 < c2 / 3.0

    def test_stripping_a_real_common_factor_shrinks_residual_vol(self):
        closes, market, sect, leg, _ = _panel()
        two = rm.residuals(closes, market, sect, WIN, 1.0, None)
        three = rm.residuals(closes, market, sect, WIN, 1.0, {"value": leg})
        t = slice(WIN + 50, None)
        assert three.iloc[t].std().mean() < two.iloc[t].std().mean()

    def test_no_lookahead_truncating_the_future_cannot_change_the_past(self):
        """The causality pin. Residuals computed on a truncated panel must equal the
        same bars computed on the full panel — if any beta used forward data, the
        overlapping rows would disagree."""
        closes, market, sect, leg, _ = _panel()
        cut = 900
        full = rm.residuals(closes, market, sect, WIN, 0.66, {"value": leg})
        trunc = rm.residuals(closes.iloc[:cut], market.iloc[:cut], sect, WIN, 0.66,
                             {"value": leg.iloc[:cut]})
        a, b = full.iloc[:cut], trunc
        both = a.notna() & b.notna()
        assert both.to_numpy().sum() > 1000, "test panel produced too few comparable cells"
        assert np.allclose(a.to_numpy()[both.to_numpy()], b.to_numpy()[both.to_numpy()],
                           atol=1e-10), "residual changed when the future was removed"

    def test_empty_legs_reduce_to_the_shipped_two_leg_construction(self):
        """None and {} must agree — otherwise the deep panel (no legs) and the live
        panel would be running quietly different constructions."""
        closes, market, sect, _, _ = _panel()
        a = rm.residuals(closes, market, sect, WIN, 0.66, None)
        b = rm.residuals(closes, market, sect, WIN, 0.66, {})
        pd.testing.assert_frame_equal(a, b)

    def test_matches_the_shipped_residual_alpha_engine_when_legs_are_absent(self):
        """Cross-engine agreement: with no factor legs this module must reproduce
        `engine.residual_alpha.residuals`, which is what makes the new deep-panel
        numbers comparable to the shipped leg's prior measurements."""
        from engine import residual_alpha as ra
        closes, market, sect, _, _ = _panel()
        new = rm.residuals(closes, market, sect, WIN, 0.66, None)
        old = ra.residuals(closes, market, sect, WIN, 0.66)
        both = new.notna() & old.notna()
        assert both.to_numpy().sum() > 1000
        assert np.allclose(new.to_numpy()[both.to_numpy()], old.to_numpy()[both.to_numpy()],
                           atol=1e-10)


class TestOrthogonalBasis:
    def test_basis_decorrelates_the_legs(self):
        n = 1500
        idx = pd.bdate_range("2017-01-01", periods=n)
        rng = np.random.default_rng(11)
        a = pd.Series(rng.normal(0, 0.01, n), index=idx)
        b = 0.8 * a + pd.Series(rng.normal(0, 0.004, n), index=idx)   # heavily overlapping
        basis = rm.orthogonal_basis([a, b], WIN, WIN // 2)
        t = slice(WIN + 50, None)
        raw = abs(a.iloc[t].corr(b.iloc[t]))
        orth = abs(basis[0].iloc[t].corr(basis[1].iloc[t]))
        assert raw > 0.8
        assert orth < 0.15, f"legs stayed collinear after Gram-Schmidt ({orth:.3f})"

    def test_first_leg_is_untouched(self):
        n = 600
        idx = pd.bdate_range("2020-01-01", periods=n)
        rng = np.random.default_rng(5)
        a = pd.Series(rng.normal(0, 0.01, n), index=idx)
        b = pd.Series(rng.normal(0, 0.01, n), index=idx)
        basis = rm.orthogonal_basis([a, b], 252, 126)
        pd.testing.assert_series_equal(basis[0], a.astype(float), check_names=False)


class TestWindowSignals:
    def test_mom_res_is_the_literal_residual_sum_over_the_window(self):
        """Pins the request's formula: sum of epsilon over [t-form, t-skip]."""
        n, form, skip = 400, 63, 21
        idx = pd.bdate_range("2022-01-01", periods=n)
        eps = pd.DataFrame({"X": np.arange(n, dtype=float) * 0.0001}, index=idx)
        R = eps.copy()
        got = rm.window_signals(R, eps, form, skip)["mom_res"].iloc[-1]["X"]
        expect = eps["X"].shift(skip).iloc[-form:].sum()
        assert got == pytest.approx(expect, rel=1e-9)

    def test_ir_res_is_the_sum_form_scaled_by_dispersion(self):
        n, form, skip = 400, 63, 21
        idx = pd.bdate_range("2022-01-01", periods=n)
        rng = np.random.default_rng(2)
        eps = pd.DataFrame({"X": rng.normal(0, 0.01, n)}, index=idx)
        sig = rm.window_signals(eps.copy(), eps, form, skip)
        w = eps["X"].shift(skip).iloc[-form:]
        assert sig["ir_res"].iloc[-1]["X"] == pytest.approx(w.mean() / w.std(), rel=1e-9)

    def test_skip_actually_excludes_the_recent_window(self):
        """A spike inside the skipped tail must NOT reach the signal — that is the
        whole point of skipping the last month (short-term reversal)."""
        n, form, skip = 500, 126, 21
        idx = pd.bdate_range("2022-01-01", periods=n)
        base = pd.DataFrame({"X": np.zeros(n)}, index=idx)
        spiked = base.copy()
        spiked.iloc[-5, 0] = 5.0                      # inside the skipped tail
        a = rm.window_signals(base.copy(), base, form, skip)["mom_res"].iloc[-1]["X"]
        b = rm.window_signals(spiked.copy(), spiked, form, skip)["mom_res"].iloc[-1]["X"]
        assert a == pytest.approx(b), "a spike in the skipped window leaked into the signal"

    def test_shorter_window_uses_fewer_days(self):
        n = 600
        idx = pd.bdate_range("2022-01-01", periods=n)
        eps = pd.DataFrame({"X": np.ones(n) * 0.001}, index=idx)
        s3 = rm.window_signals(eps.copy(), eps, 63, 21)["mom_res"].iloc[-1]["X"]
        s12 = rm.window_signals(eps.copy(), eps, 252, 21)["mom_res"].iloc[-1]["X"]
        assert s12 == pytest.approx(4.0 * s3, rel=1e-6)


class TestComputeReadout:
    def test_injected_panel_reports_absent_legs_rather_than_zeroing_them(self):
        closes, market, sect, _, _ = _panel()
        out = rm.compute_residual_momentum(closes, market, sect, win=WIN, shrink=0.66,
                                           min_names=10, with_factor_legs=False)
        assert out is not None
        assert out["factor_legs_live"] == []
        assert set(out["factor_legs_absent"]) == set(rm.FACTOR_LEGS)
        assert out["duplicate_windows"] == {"w12_ex21": "w12_1"}
        assert set(out["windows"]) <= set(rm.distinct_windows())
        for block in out["windows"].values():
            assert "mom_res" in block and "ir_res" in block

    def test_too_few_names_returns_none_not_a_thin_ranking(self):
        closes, market, sect, _, _ = _panel(n_names=6)
        assert rm.compute_residual_momentum(closes, market, sect, win=WIN,
                                            min_names=20, with_factor_legs=False) is None
