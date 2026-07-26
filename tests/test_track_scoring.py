"""Pins for engine/track_scoring.py — the honest episode scorer behind the four
Track-record desks.

These tests exist because the module replaces a scorer that was wrong in ways that all
flattered the desk, and because the most attractive alternative design is subtly WORSE
than the one it replaced. Each test names the specific failure it prevents.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import track_scoring as ts  # noqa: E402

_IDX = pd.bdate_range("2026-01-01", periods=60)


def _series(vals) -> pd.Series:
    return pd.Series(vals, index=_IDX[:len(vals)], dtype=float)


def _flat_then(vals) -> pd.Series:
    """Enough leading history to make any index position addressable."""
    return _series([100.0] * 5 + list(vals))


# =========================================================================== #
# build_episodes — contiguous runs, re-entry
# =========================================================================== #
class TestBuildEpisodes:
    def test_contiguous_run_is_one_episode(self):
        days = {"d1": {"A"}, "d2": {"A"}, "d3": {"A"}}
        eps = ts.build_episodes(days)
        assert len(eps) == 1
        assert eps[0] == {"ticker": "A", "entry_date": "d1", "exit_date": None}

    def test_reentry_opens_a_second_episode(self):
        """The bug this replaces: keying on a ticker's FIRST-EVER appearance meant a
        name that left and came back kept its original anchor forever. On the live US
        board that showed WAB as one in-flight pick marked +12.2% from a June date,
        when WAB had been on the board a single day in June and only returned in late
        July — the gain was earned while the name was OFF the board."""
        days = {"d1": {"A"}, "d2": set(), "d3": {"A"}}
        eps = ts.build_episodes(days)
        assert len(eps) == 2
        assert [e["entry_date"] for e in eps] == ["d1", "d3"]
        assert eps[0]["exit_date"] == "d2"
        assert eps[1]["exit_date"] is None

    def test_open_run_has_no_exit(self):
        eps = ts.build_episodes({"d1": {"A", "B"}, "d2": {"A"}})
        by = {e["ticker"]: e for e in eps}
        assert by["A"]["exit_date"] is None
        assert by["B"]["exit_date"] == "d2"

    def test_empty_history(self):
        assert ts.build_episodes({}) == []


# =========================================================================== #
# score_episode — fill realism and the return contract
# =========================================================================== #
class TestScoreEpisode:
    def test_entry_is_the_next_bar_never_the_signal_bar(self):
        """The signal bar's close is unbuyable: the board is computed FROM it and
        published that evening. Entering on it was worth +5.5pp of win rate and 69% of
        the reported average return on the live US board."""
        s = _flat_then([200.0, 210.0] + [210.0] * 12)
        sc = ts.score_episode(s, _IDX[5], horizon=2)
        assert sc["entry"] == 210.0                      # bar AFTER the signal bar
        assert sc["entry_date"] == str(_IDX[6].date())

    def test_fill_pending_is_distinct_from_unpriceable(self):
        """Conflating them reported 22 liquid names (DE, F, ...) as delisted."""
        s = _series([100.0, 101.0])
        pending = ts.score_episode(s, _IDX[1], horizon=5)   # signal on the last bar
        assert pending is not None and pending["fill_pending"] is True
        missing = ts.score_episode(s, "2099-01-01", horizon=5)
        assert missing is None                              # genuinely unlocatable

    def test_unmatured_returns_no_pnl(self):
        s = _flat_then([100.0, 101.0, 102.0])
        sc = ts.score_episode(s, _IDX[5], horizon=10)
        assert sc["matured"] is False
        assert sc["pnl"] is None and sc["excess"] is None
        assert sc["mark"] is not None                       # live mark still shown


# =========================================================================== #
# RULE 1 — the forced verdict
# =========================================================================== #
class TestForcedVerdict:
    # Fixture geometry: _flat_then puts vals[0] at index 5. Signalling on _IDX[4]
    # makes the fill vals[0] (index 5) and the forward window vals[1:] (index 6+).
    def test_rule_exit_may_shorten_the_hold(self):
        s = _flat_then([100.0, 101.0, 106.0, 101.0, 101.0, 101.0, 101.0])
        hot = pd.Series(False, index=s.index)
        hot.iloc[7] = True                                  # overbought on bar 2 of the window
        sc = ts.score_episode(s, _IDX[4], horizon=5, early_exit=hot)
        assert sc["entry"] == 100.0
        assert sc["exit_reason"] == "target"
        assert sc["held"] == 2 and sc["exit"] == 106.0

    def test_rule_exit_may_never_extend_past_the_horizon(self):
        """Rule 1. If the target never fires the verdict still lands at H — this is what
        stops winners from self-resolving fast while losers wait forever."""
        s = _flat_then([100.0] + [99.0] * 20)
        hot = pd.Series(False, index=s.index)               # never fires
        sc = ts.score_episode(s, _IDX[4], horizon=5, early_exit=hot)
        assert sc["exit_reason"] == "horizon"
        assert sc["held"] == 5

    def test_stop_takes_precedence_and_ends_the_episode(self):
        s = _flat_then([100.0, 80.0, 120.0, 120.0, 120.0, 120.0])
        sc = ts.score_episode(s, _IDX[4], horizon=5, stop_level=90.0)
        assert sc["entry"] == 100.0
        assert sc["exit_reason"] == "stop"
        assert sc["held"] == 1
        assert sc["pnl"] == pytest.approx(-20.0)            # the later rally is NOT credited

    def test_no_outcome_conditioned_denominator(self):
        """The design this rejects: 'resolve when the thesis resolves — overbought=win,
        stop=loss, else still in flight'. It reported 83.6% win / 5.05 profit factor on
        the live US board and was an artefact: the overbought leg fires WHEN PRICE
        RALLIES, so winners self-resolved in days and losers sat unresolved forever
        (resolved rows carried a +1.66% mean mark vs −1.14% for unresolved).

        Here: a name that never triggers either leg must STILL be scored, as a loss.
        """
        s = _flat_then([100.0] + [97.0] * 20)               # drifts down, never stops out
        hot = pd.Series(False, index=s.index)
        sc = ts.score_episode(s, _IDX[4], horizon=5, early_exit=hot, stop_level=50.0)
        assert sc["matured"] is True
        assert sc["exit_reason"] == "horizon"
        assert sc["pnl"] < 0                                # counted, not parked


# =========================================================================== #
# RULE 2 — the symmetric maturity gate
# =========================================================================== #
class TestMaturityGate:
    def test_summary_counts_only_matured(self):
        scored = [
            {"matured": True, "pnl": 5.0, "held": 3, "mfe": 6.0, "mae": -1.0, "board_date": "d1"},
            {"matured": True, "pnl": -3.0, "held": 5, "mfe": 1.0, "mae": -4.0, "board_date": "d2"},
            {"matured": False, "pnl": None, "held": 2, "mfe": None, "mae": None, "board_date": "d3"},
        ]
        s = ts.summarize(scored, metric="pnl", n_inflight=1)
        assert s["n_matured"] == 2
        assert s["n_inflight"] == 1
        assert s["win_pct"] == 50.0

    def test_no_dead_band(self):
        """The ±2% flat bucket with flats dropped from the denominator turned 86 up /
        57 down / 72 flat into '60% win' where every resolved episode gives 40%."""
        scored = [{"matured": True, "pnl": p, "held": 1, "mfe": abs(p), "mae": -abs(p),
                   "board_date": f"d{i}"} for i, p in enumerate([0.5, 0.5, -0.5, -0.5])]
        s = ts.summarize(scored, metric="pnl")
        assert s["n_matured"] == 4                          # nothing dropped for being small
        assert s["win_pct"] == 50.0

    def test_profit_factor_is_null_not_infinite_without_losers(self):
        scored = [{"matured": True, "pnl": 5.0, "held": 1, "mfe": 5.0, "mae": 0.0,
                   "board_date": f"d{i}"} for i in range(3)]
        s = ts.summarize(scored, metric="pnl")
        assert s["profit_factor"] is None                    # a ratio here would be a lie

    def test_metric_selects_absolute_or_excess(self):
        scored = [{"matured": True, "pnl": 5.0, "excess": -1.0, "held": 1, "mfe": 5.0,
                   "mae": 0.0, "board_date": "d1"},
                  {"matured": True, "pnl": -5.0, "excess": 2.0, "held": 1, "mfe": 0.0,
                   "mae": -5.0, "board_date": "d2"}]
        assert ts.summarize(scored, metric="pnl")["win_pct"] == 50.0
        assert ts.summarize(scored, metric="excess")["win_pct"] == 50.0
        assert ts.summarize(scored, metric="pnl")["expectancy_pct"] == 0.0
        assert ts.summarize(scored, metric="excess")["expectancy_pct"] == 0.5


# =========================================================================== #
# RULE 3 — date-blocked confidence intervals
# =========================================================================== #
class TestDateBlockCI:
    def test_ci_is_wider_than_treating_episodes_as_independent(self):
        """Episodes surfaced on one board night share the market's move — they are one
        bet. Wilson-on-raw-n treated 840 overlapping CN rows from 15 nights as 840
        independent draws and published a 50.5–57.3% interval off it."""
        rng = np.random.default_rng(0)
        # 6 board days; within a day outcomes are perfectly correlated (the extreme
        # case that makes the point) — 4 winning days, 2 losing.
        pairs = []
        for d in range(6):
            good = d < 4
            for _ in range(30):
                pairs.append((f"d{d}", 1.0 if good else -1.0))
        blocked_lo, blocked_hi = ts.date_block_ci(pairs, ts._win_pct, n_boot=1500)
        vals = np.array([v for _, v in pairs])
        iid = np.array([ts._win_pct(vals[rng.integers(0, len(vals), len(vals))])
                        for _ in range(1500)])
        iid_lo, iid_hi = np.percentile(iid, [2.5, 97.5])
        assert (blocked_hi - blocked_lo) > (iid_hi - iid_lo) * 3

    def test_returns_none_with_fewer_than_two_blocks(self):
        """One board day cannot support an interval; fabricating one would be worse
        than printing nothing."""
        assert ts.date_block_ci([("d1", 1.0), ("d1", -1.0)], ts._win_pct) == (None, None)
        assert ts.date_block_ci([], ts._win_pct) == (None, None)

    def test_is_deterministic_across_calls(self):
        """A wandering interval would churn the committed JSON every render."""
        pairs = [(f"d{i%5}", float(i % 7) - 3) for i in range(80)]
        assert ts.date_block_ci(pairs, ts._win_pct) == ts.date_block_ci(pairs, ts._win_pct)

    def test_summary_reports_board_days_not_row_count(self):
        scored = [{"matured": True, "pnl": 1.0, "held": 1, "mfe": 1.0, "mae": 0.0,
                   "board_date": "d1"} for _ in range(50)]
        s = ts.summarize(scored, metric="pnl")
        assert s["n_matured"] == 50
        assert s["n_board_days"] == 1                       # the number that matters


# =========================================================================== #
# publish_state
# =========================================================================== #
class TestPublishState:
    def test_thin_sample_stays_accruing_on_either_gate(self):
        base = {"win_pct": 60.0, "n_matured": 100, "n_board_days": 40}
        assert ts.publish_state(base) == "scored"
        assert ts.publish_state({**base, "n_matured": 5}) == "accruing"
        assert ts.publish_state({**base, "n_board_days": 2}) == "accruing"
        assert ts.publish_state({**base, "win_pct": None}) == "accruing"


# =========================================================================== #
# include_fill_bar — the cross-desk comparability guard
# =========================================================================== #
def test_include_fill_bar_shifts_the_window_by_exactly_one():
    """CN fills at the T+1 OPEN, so that session's close is a valid day-one exit; the
    US fills AT a close and must not treat the same bar as its own exit. Getting this
    wrong makes one desk hold a bar longer than the other at the same nominal horizon.
    """
    s = _flat_then([100.0, 101.0, 102.0, 103.0, 104.0, 105.0])
    excl = ts.score_from_fill(s, _IDX[5], 100.0, horizon=3, include_fill_bar=False)
    incl = ts.score_from_fill(s, _IDX[5], 100.0, horizon=3, include_fill_bar=True)
    assert excl["exit"] == 103.0       # bars 6,7,8 → third is 103
    assert incl["exit"] == 102.0       # bars 5,6,7 → third is 102
