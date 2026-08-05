"""Unit tests for the US label-grading battery's veto-day classifier.

Synthetic series only — no repo data, no network. One test per label family, plus the
two traps the handoff memo names explicitly:

  * a leg that NEVER fires must be exposed by the fire-count diagnostic (a silently
    dead leg is the defect that makes a battery print plausible nulls);
  * ``x is True`` on a numpy bool is ALWAYS False, so a gate written with ``is True``
    silently rejects every numpy-typed input (memory:
    numpy-bool-is-true-deadens-a-feature-leg).
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


def _load():
    """Import the battery by path (it lives outside any package)."""
    cwd = os.getcwd()
    spec = importlib.util.spec_from_file_location(
        "label_grading_battery", Path(__file__).resolve().parent / "label_grading_battery.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)          # module chdir()s to REPO at import
    os.chdir(cwd)
    return mod


LGB = _load()


# --------------------------------------------------------------- fixtures --
def _walk(n=520, drift=0.0025, vol=0.012, seed=1, start_px=100.0,
          start="2022-01-03") -> pd.Series:
    """A drifting random walk — the minimum realistic fixture.

    A NOISELESS ramp is degenerate here and must not be used: with no down-moves the
    Wilder RSI pins to a constant, so StochRSI's (r-lo)/(hi-lo) divides by zero and
    every oscillator leg goes NaN. That produces an all-dead panel that looks exactly
    like a broken classifier, which is the opposite of what these tests are for.
    """
    rng = np.random.default_rng(seed)
    r = drift + vol * rng.standard_normal(n)
    idx = pd.bdate_range(start, periods=n)
    return pd.Series(start_px * np.exp(np.cumsum(r)), index=idx)


def _ramp(n=520, seed=1) -> pd.Series:
    """Uptrend: RSI runs hot (cap + overbought legs fire), price holds above its 200d."""
    return _walk(n=n, drift=0.0025, vol=0.012, seed=seed)


def _decline(n=520, seed=2) -> pd.Series:
    """Downtrend: the bearish legs fire; the RSI cap and above200 never do."""
    return _walk(n=n, drift=-0.0030, vol=0.010, seed=seed, start_px=300.0)


def _panels_for(series_by_ticker: dict[str, pd.Series]):
    idx = sorted(set().union(*[set(s.index) for s in series_by_ticker.values()]))
    px = pd.DataFrame({t: s.reindex(idx) for t, s in series_by_ticker.items()},
                      index=pd.DatetimeIndex(idx))
    return px, LGB.build_label_panels(px)


# ------------------------------------------------------------------ tests --
class TestVetoDayClassifier:
    """One case per label family, driven through the real panel builder."""

    def test_uptrend_fires_the_overbought_and_rsi_cap_labels(self):
        _px, (panels, diag) = _panels_for({"UP": _ramp()})
        assert panels["stoch_ob"].to_numpy().sum() > 0, "overbought leg must fire in a trend"
        assert panels["rsi_ge_cap"].to_numpy().sum() > 0, "RSI cap must fire in a trend"
        assert panels["above200"].to_numpy().sum() > 0
        assert panels["weekly_bull"].to_numpy().sum() > 0

    def test_downtrend_fires_bearish_legs_and_never_the_rsi_cap(self):
        _px, (panels, diag) = _panels_for({"DN": _decline()})
        assert panels["macd_bear"].to_numpy().sum() > 0, "macd_bear must fire on a decline"
        assert panels["stoch_bear"].to_numpy().sum() > 0, "stoch_bear must fire on a decline"
        # a sustained decline never lifts RSI14 to the 65 cap, and price never regains
        # its own 200d — both are the label's genuine absence, not a broken leg
        assert panels["rsi_ge_cap"].to_numpy().sum() == 0
        assert panels["above200"].to_numpy().sum() == 0

    def test_freshness_label_needs_a_cross_and_a_lapsed_window(self):
        """freshness_expired = a 3D cross exists AND its age exceeds FRESH_TICKS.
        A series with no cross at all must produce no freshness prints."""
        _px, (panels, diag) = _panels_for({"DN": _decline()})
        has_cross = panels["has_cross"].to_numpy()
        ticks = panels["cross_ticks"].to_numpy()
        expired = has_cross & (ticks > LGB.FRESH_TICKS)
        # where there is no cross the age must be NaN, never a number that could be
        # compared into a label
        assert np.isnan(ticks[~has_cross]).all()
        assert not expired[~has_cross].any()

        # a series that DOES cross produces both fresh and expired days
        turn = pd.concat([_walk(260, drift=-0.003, vol=0.010, seed=5, start_px=200.0),
                          _walk(260, drift=+0.003, vol=0.010, seed=6, start_px=120.0,
                                start="2023-01-02")])
        turn.index = pd.bdate_range("2022-01-03", periods=len(turn))
        _px2, (p2, _d2) = _panels_for({"UPDN": turn})
        t2 = p2["cross_ticks"].to_numpy()
        hc2 = p2["has_cross"].to_numpy()
        assert hc2.sum() > 0, "a turn must produce at least one 3D cross"
        assert (hc2 & (t2 <= LGB.FRESH_TICKS)).sum() > 0, "some days must be fresh"
        assert (hc2 & (t2 > LGB.FRESH_TICKS)).sum() > 0, "some days must be expired"

    def test_inline_legs_reproduce_tier_stream_not_topped(self):
        """The replication pin: the inline legs must equal the production stream's
        not_topped on every in-range cell."""
        _px, (panels, diag) = _panels_for({"UP": _ramp(), "DN": _decline()})
        chk = diag["equality_spot_check"]
        assert chk["cells"] > 0
        assert chk["mismatches"] == 0, f"leg replication drifted: {chk}"


class TestDeadLegDiagnostic:
    """The handoff's own trap: a leg that never fires must be VISIBLE, not inferred."""

    def test_dead_leg_is_reported_when_a_leg_never_fires(self):
        """THE test the handoff memo asks for. On an all-declining universe the RSI cap
        and above200 labels genuinely never fire; the diagnostic must SAY so rather than
        let the battery print an empty cohort that reads like a measured null."""
        _px, (panels, diag) = _panels_for({"DN": _decline(seed=2), "DN2": _decline(seed=3)})
        assert diag["fire_counts_name_days"]["rsi_ge_cap"] == 0
        assert diag["fire_counts_name_days"]["above200"] == 0
        assert "rsi_ge_cap" in diag["dead_legs"], (
            "a leg with zero fires must be named in dead_legs — this is the diagnostic "
            "that catches a silently dead feature leg")
        assert "above200" in diag["dead_legs"]
        # and the legs that DO fire must not be swept into the alarm
        assert "macd_bear" not in diag["dead_legs"]

    def test_no_dead_legs_on_a_mixed_universe(self):
        _px, (panels, diag) = _panels_for({"UP": _ramp(), "DN": _decline()})
        assert diag["dead_legs"] == [], f"unexpected dead legs: {diag['dead_legs']}"

    def test_weekly_leg_computability_is_tracked_not_assumed(self):
        """A too-short series yields an all-NaN weekly leg. fillna(False) would render
        that as 'not bullish' — indistinguishable from a real bearish read — so the
        battery must count the name as NOT COMPUTABLE instead."""
        short = _ramp(n=290)          # ~58 W-FRI bars: below _rsi_macd's 74-bar warm-up
        _px, (panels, diag) = _panels_for({"UP": _ramp(), "SHORT": short})
        assert bool(panels["weekly_computable"]["UP"]) is True
        assert bool(panels["weekly_computable"]["SHORT"]) is False
        assert diag["weekly_leg_computability"]["names_not_computable"] >= 1
        assert diag["weekly_leg_computability"]["names_computable"] >= 1


class TestNumpyBoolTrap:
    """`x is True` on a numpy bool is ALWAYS False. The ran gate is written with
    `is True`, so this pins BOTH halves: the trap is real, and production is safe
    because engine/signal_quality.py:287 wraps the flags in bool()."""

    def test_numpy_bool_defeats_an_is_true_gate(self):
        from engine import us_board_rank as ubr
        base = {"eligible": False, "ticks": 5, "above200": True, "weekly_bull": True}
        assert ubr.ran_admits(base, {}) is True

        trapped = dict(base, above200=np.bool_(True))
        assert trapped["above200"] == True                      # noqa: E712 — equality holds
        assert (trapped["above200"] is True) is False           # identity does NOT
        assert ubr.ran_admits(trapped, {}) is False, (
            "a numpy bool must fail an `is True` gate — if this ever passes, the trap "
            "has been fixed upstream and the battery's bool() wrapping can be revisited")

    def test_battery_passes_python_bools_into_the_gate(self):
        """The battery reconstructs verdicts with bool()/int(), so the gate sees the
        same types production hands it."""
        from engine import us_board_rank as ubr
        v = {"eligible": bool(np.bool_(False)), "ticks": int(np.int64(5)),
             "above200": bool(np.bool_(True)), "weekly_bull": bool(np.bool_(True))}
        assert ubr.ran_admits(v, {}) is True

    def test_ticks_window_bounds_are_respected(self):
        from engine import us_board_rank as ubr
        for t, want in ((ubr.RAN_TICKS_MIN - 1, False), (ubr.RAN_TICKS_MIN, True),
                        (ubr.RAN_TICKS_MAX, True), (ubr.RAN_TICKS_MAX + 1, False)):
            v = {"eligible": False, "ticks": int(t), "above200": True, "weekly_bull": True}
            assert ubr.ran_admits(v, {}) is want, f"ticks={t}"


class TestStatsGuards:
    """The stat helpers must never silently drop a guard."""

    def test_stats_block_flags_thin_cells(self):
        ex = np.array([1.0, 2.0, -5.0])
        blk = LGB.stats_block(ex, ex, ["A", "B", "C"])
        assert blk["n"] == 3
        assert blk.get("thin") is True
        assert "thin_note" in blk

    def test_loser_threshold_is_the_stated_minus_3pp(self):
        ex = np.array([-3.5, -2.5, 10.0, 0.5])       # exactly one below -3pp
        blk = LGB.stats_block(ex, ex, list("ABCD"))
        assert blk["loser_rate_pct"] == 25.0
        assert LGB.LOSER_PP == -3.0

    def test_per_name_first_median_differs_from_pooled_when_a_name_repeats(self):
        # one name contributes 3 losing rows; pooled is dragged down, per-name is not
        ex = np.array([-10.0, -10.0, -10.0, 6.0, 8.0])
        tk = ["DUP", "DUP", "DUP", "B", "C"]
        blk = LGB.stats_block(ex, ex, tk)
        assert blk["median_excess_spy_pp"] == -10.0
        assert blk["per_name_first_median_pp"] == 6.0
        assert blk["names"] == 3

    def test_forfeiture_cost_prices_winners_removed_not_just_losers(self):
        base = np.array([-8.0, -6.0, 12.0, 1.0, -1.0])
        hit = np.array([True, True, True, False, False])
        c = LGB.forfeiture_cost("demo", base, hit)
        assert c["n_removed"] == 3
        assert c["losers_removed"] == 2
        assert c["winners_removed_gt0"] == 1, (
            "a filter's forfeited winners must be priced — the G0.7 idiom exists so a "
            "filter is never sold on its removed losers alone")
        assert c["kept_n"] == 2

    def test_half_split_returns_both_halves(self):
        dates = pd.bdate_range("2026-01-01", periods=8)
        ex = np.arange(8, dtype=float)
        hs = LGB.half_split(dates, ex, ex, list("ABCDEFGH"))
        assert hs["first_half"]["n"] + hs["second_half"]["n"] == 8

    def test_stats_block_handles_an_empty_cell(self):
        blk = LGB.stats_block(np.array([]), np.array([]), [])
        assert blk["n"] == 0 and blk["thin"] is True


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
