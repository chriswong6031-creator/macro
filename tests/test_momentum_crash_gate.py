"""Momentum crash gate (engine/momentum_crash_gate.py).

A gate is a sizing decision, so the failure modes that matter are the quiet ones: a
percentile that peeks forward (making every backtest look prescient), an exposure that
is applied on the same bar it was computed, and a missing input silently voting 0.5 so
a two-condition gate reads as if all six had spoken.
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

from engine import momentum_crash_gate as mcg  # noqa: E402

N = 1500
IDX = pd.bdate_range("2015-01-01", periods=N)


def _ret(seed: int = 5, scale: float = 0.01) -> pd.Series:
    return pd.Series(np.random.default_rng(seed).normal(0, scale, N), index=IDX)


class TestCausalPercentile:
    def test_appending_future_data_cannot_change_past_readings(self):
        """The causality pin. An expanding percentile must be identical on a truncated
        series — a `.rank(pct=True)` over the WHOLE series would silently fail this and
        make every gate backtest look clairvoyant."""
        s = _ret(1)
        full = mcg.causal_pctile(s, min_history=252)
        trunc = mcg.causal_pctile(s.iloc[:900], min_history=252)
        both = full.iloc[:900].notna() & trunc.notna()
        assert both.sum() > 400
        assert np.allclose(full.iloc[:900][both], trunc[both], atol=1e-12)

    def test_readings_are_blank_until_min_history(self):
        s = _ret(2)
        out = mcg.causal_pctile(s, min_history=500)
        assert out.iloc[:499].isna().all(), "an early, thinly-ranked reading must be absent"
        assert out.iloc[600:].notna().any()

    def test_output_is_a_percentile_in_unit_range(self):
        out = mcg.causal_pctile(_ret(3), min_history=252).dropna()
        assert len(out) > 100
        assert out.min() >= 0.0 and out.max() <= 1.0

    def test_a_record_high_reads_near_one(self):
        s = pd.Series(np.linspace(0, 1, N), index=IDX)      # every bar a new high
        out = mcg.causal_pctile(s, min_history=252).dropna()
        assert out.iloc[-1] == pytest.approx(1.0, abs=1e-9)


class TestConditions:
    def test_a_missing_input_is_absent_not_neutral(self):
        """A condition with no input must not appear at all. Filling 0.5 would let two
        live conditions masquerade as a six-condition consensus."""
        cond = mcg.conditions(_ret(4), market_ret=None, panel_ret=None)
        assert "mom_vol" in cond.columns
        for absent in ("rebound", "xs_corr", "loser_run", "breadth_rev", "extension"):
            assert absent not in cond.columns

    def test_no_inputs_returns_an_empty_frame(self):
        assert mcg.conditions(None).empty

    def test_rising_sleeve_volatility_raises_the_mom_vol_reading(self):
        """The reading must spike WHEN vol explodes. It is expected to decay later:
        an expanding percentile ranks against all prior history, so after hundreds of
        high-vol bars, high vol is no longer unusual. That decay is the design — a
        reading pinned at 1.0 forever would gate the sleeve off permanently."""
        calm = np.random.default_rng(8).normal(0, 0.004, N // 2)
        wild = np.random.default_rng(9).normal(0, 0.030, N // 2)
        s = pd.Series(np.concatenate([calm, wild]), index=IDX)
        out = mcg.conditions(s, min_history=252)["mom_vol"]
        just_after = out.iloc[N // 2 + 70:N // 2 + 150].max()
        assert just_after > 0.95, "a volatility explosion must read as high stress"
        assert out.dropna().iloc[-1] < just_after, "the reading should renormalize"

    def test_rebound_only_fires_inside_a_drawdown(self):
        """A fast advance at an all-time high is a bull market, not a bear-market
        rebound. Gating on it would cut exposure exactly where momentum works best."""
        up = pd.Series(np.full(N, 0.0015), index=IDX)        # steady grind, never in DD
        cond = mcg.conditions(_ret(10), market_ret=up, min_history=252)
        assert cond["rebound"].dropna().max() == pytest.approx(0.0), \
            "rebound fired without any drawdown to rebound from"

    def test_rebound_fires_after_a_crash_and_snapback(self):
        """Repeated crash/snapback cycles, so the conditional series accumulates enough
        in-drawdown history to rank against."""
        r = np.full(N, 0.0002)
        for start in range(400, 1400, 200):
            r[start:start + 60] = -0.02                       # crash
            r[start + 60:start + 100] = +0.03                 # violent snapback
        cond = mcg.conditions(_ret(11), market_ret=pd.Series(r, index=IDX),
                              min_history=252, cond_min_history=60)
        assert cond["rebound"].iloc[1260:1300].max() > 0.5

    def test_rebound_distinguishes_no_drawdown_from_unmeasurable(self):
        """Three distinct answers, not two: 0.0 outside a drawdown (no rebound risk
        exists), NaN inside one before enough conditional history accrues."""
        r = np.full(N, 0.0002)
        r[1200:1260] = -0.02                                  # one late crash only
        cond = mcg.conditions(_ret(12), market_ret=pd.Series(r, index=IDX),
                              min_history=252, cond_min_history=60)
        reb = cond["rebound"]
        assert reb.iloc[600:1100].max() == pytest.approx(0.0), "no drawdown -> zero stress"
        assert reb.iloc[1200:1280].isna().any(), \
            "in a drawdown with too little history the reading must be ABSENT, not calm"

    def test_xs_corr_rises_when_the_panel_moves_as_one(self):
        rng = np.random.default_rng(12)
        common = rng.normal(0, 0.02, N)
        indep = pd.DataFrame({f"T{i}": rng.normal(0, 0.02, N) for i in range(20)}, index=IDX)
        together = indep.copy()
        together.iloc[N // 2:] = (indep.iloc[N // 2:].to_numpy() * 0.2
                                  + common[N // 2:, None] * 0.9)
        a = mcg.conditions(_ret(13), panel_ret=indep, min_history=252)["xs_corr"].dropna()
        b = mcg.conditions(_ret(13), panel_ret=together, min_history=252)["xs_corr"].dropna()
        assert b.iloc[-1] > a.iloc[-1]

    def test_losers_outperforming_raises_loser_run(self):
        winner = pd.Series(np.full(N, 0.0005), index=IDX)
        loser = pd.Series(np.full(N, 0.0005), index=IDX)
        loser.iloc[-60:] = 0.02                               # losers rip
        out = mcg.conditions(_ret(14), loser_ret=loser, winner_ret=winner,
                             min_history=252)["loser_run"].dropna()
        assert out.iloc[-1] > 0.9


class TestExposure:
    def _cond(self, stress: float, n_cols: int = 4) -> pd.DataFrame:
        return pd.DataFrame({f"c{i}": np.full(N, stress) for i in range(n_cols)}, index=IDX)

    def test_exposure_is_lagged_so_it_cannot_trade_on_same_bar_information(self):
        """Stress at bar t is known only at t's close, so the position it implies can
        only be held from t+1. Without the shift the backtest is an artifact."""
        cond = self._cond(0.2)
        cond.iloc[:100] = 0.9
        exp = mcg.exposure(cond, lag=1)
        unlagged = (1.0 - cond.mean(axis=1)).clip(0, 1)
        assert np.allclose(exp.iloc[1:].to_numpy(), unlagged.iloc[:-1].to_numpy())

    def test_high_stress_cuts_exposure_and_low_stress_keeps_it(self):
        assert mcg.exposure(self._cond(0.9)).dropna().iloc[-1] == pytest.approx(0.1)
        assert mcg.exposure(self._cond(0.1)).dropna().iloc[-1] == pytest.approx(0.9)

    def test_exposure_is_monotone_decreasing_in_stress(self):
        vals = [mcg.exposure(self._cond(s)).dropna().iloc[-1] for s in (0.1, 0.3, 0.6, 0.9)]
        assert vals == sorted(vals, reverse=True)

    def test_floor_and_cap_are_respected(self):
        e = mcg.exposure(self._cond(0.95), floor=0.25, cap=0.8).dropna()
        assert e.min() >= 0.25 and e.max() <= 0.8

    def test_a_single_live_condition_is_not_a_crash_gate(self):
        """One condition is a volatility filter wearing a crash gate's name."""
        one = pd.DataFrame({"mom_vol": np.full(N, 0.5)}, index=IDX)
        assert mcg.exposure(one, min_conditions=2).isna().all()
        assert mcg.exposure(one, min_conditions=1).dropna().notna().any()

    def test_empty_conditions_give_an_empty_exposure(self):
        assert mcg.exposure(pd.DataFrame()).empty


class TestGateSeries:
    def test_gated_sleeve_reduces_exposure_in_the_stressed_half(self):
        calm = np.random.default_rng(15).normal(0.0004, 0.004, N // 2)
        wild = np.random.default_rng(16).normal(-0.002, 0.030, N // 2)
        mom = pd.Series(np.concatenate([calm, wild]), index=IDX)
        mkt = pd.Series(np.concatenate([np.full(N // 2, 0.0004),
                                        np.full(N // 2, -0.001)]), index=IDX)
        panel = pd.DataFrame({f"T{i}": np.random.default_rng(i).normal(0, 0.02, N)
                              for i in range(15)}, index=IDX)
        out = mcg.gate_series(mom, market_ret=mkt, panel_ret=panel, min_history=252)
        exp = out["exposure"].dropna()
        assert len(exp) > 100
        first, second = exp.iloc[:len(exp) // 2].mean(), exp.iloc[len(exp) // 2:].mean()
        assert second < first, "the gate did not de-risk into the stressed regime"

    def test_gated_returns_are_bounded_by_the_ungated_sleeve(self):
        """Exposure lives in [0,1], so gating can only scale a day's return toward
        zero — never amplify or flip it."""
        mom = _ret(17, 0.02)
        panel = pd.DataFrame({f"T{i}": np.random.default_rng(i).normal(0, 0.02, N)
                              for i in range(12)}, index=IDX)
        out = mcg.gate_series(mom, market_ret=_ret(18), panel_ret=panel, min_history=252)
        g, u = out["gated"], mom
        assert (g.abs() <= u.abs() + 1e-12).all()
        same = g[(g != 0) & u.notna()]
        assert (np.sign(same) == np.sign(u.reindex(same.index))).all()


class TestLiveRead:
    def test_live_read_names_which_conditions_actually_voted(self):
        mom = _ret(19, 0.015)
        panel = pd.DataFrame({f"T{i}": np.random.default_rng(i).normal(0, 0.02, N)
                              for i in range(12)}, index=IDX)
        cond = mcg.conditions(mom, panel_ret=panel, min_history=252)
        read = mcg.live_read(cond, mcg.exposure(cond))
        assert read is not None
        assert set(read["conditions_live"]) == {"mom_vol", "xs_corr"}
        assert "rebound" in read["conditions_absent"]
        assert 0.0 <= read["exposure"] <= 1.0

    def test_live_read_is_none_before_the_gate_opens(self):
        short = pd.DataFrame({"mom_vol": [np.nan] * 10}, index=IDX[:10])
        assert mcg.live_read(short, pd.Series([np.nan] * 10, index=IDX[:10])) is None
