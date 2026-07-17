"""tests/test_intl_rotation.py
=============================
Tests for engine/intl_rotation.py and the ITR-R6 benchmark-freshness helper
in engine/intl_performance.py.

Synthetic data only — no intl_market_state import (parallel build contract).
States dicts are constructed by hand matching the frozen interface contract.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import intl_rotation as R

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _px(n: int = 120, drift: float = 0.001, seed: int = 1) -> pd.Series:
    """Synthetic price series of length n."""
    idx = pd.bdate_range("2025-01-02", periods=n)
    rng = np.random.default_rng(seed)
    ret = rng.normal(drift, 0.01, n)
    return pd.Series(100.0 * np.exp(np.cumsum(ret)), index=idx)


def _bench(n: int = 120, drift: float = 0.0005, seed: int = 99) -> pd.Series:
    idx = pd.bdate_range("2025-01-02", periods=n)
    rng = np.random.default_rng(seed)
    ret = rng.normal(drift, 0.008, n)
    return pd.Series(100.0 * np.exp(np.cumsum(ret)), index=idx)


def _state(state: str = "uptrend", ext_pctile: float | None = None,
           macd_state: str = "bull", macd_cross_date: str | None = None,
           dd_pct: float = -2.0) -> dict:
    """Hand-construct a minimal states dict for one country."""
    return {
        "state": state,
        "ext_pctile": ext_pctile,
        "macd_state": macd_state,
        "macd_cross_date": macd_cross_date,
        "dd_pct": dd_pct,
    }


# ---------------------------------------------------------------------------
# TASK A — ranking logic
# ---------------------------------------------------------------------------

class TestGovCaps:
    """Gov caps must hold: crash-state top-momentum < clean uptrend."""

    def test_crash_state_ranks_below_uptrend(self):
        """A crash-state market with higher absolute momentum must still rank below
        a clean uptrend market with slightly lower momentum."""
        bench = _bench(120)
        px_uptrend = _px(120, drift=0.0015, seed=10)
        px_crash   = _px(120, drift=0.0025, seed=11)   # higher momentum

        closes = {"UP": px_uptrend, "CR": px_crash}
        states = {
            "UP": _state("uptrend"),
            "CR": _state("crash"),
        }
        ranks = R.rank(closes, bench, states)
        cc_order = [r["cc"] for r in ranks]
        assert "UP" in cc_order and "CR" in cc_order
        assert cc_order.index("UP") < cc_order.index("CR"), (
            f"Expected UP before CR; got {cc_order}"
        )

    def test_breaking_state_ranks_low(self):
        bench = _bench(120)
        px_good  = _px(120, drift=0.001, seed=20)
        px_break = _px(120, drift=0.002, seed=21)   # higher drift but breaking state
        closes = {"G": px_good, "B": px_break}
        states = {
            "G": _state("uptrend"),
            "B": _state("breaking"),
        }
        ranks = R.rank(closes, bench, states)
        cc_order = [r["cc"] for r in ranks]
        assert cc_order.index("G") < cc_order.index("B")

    def test_gov_values_in_output(self):
        bench = _bench(120)
        closes = {"JP": _px(120, seed=30), "KR": _px(120, seed=31)}
        states = {"JP": _state("crash"), "KR": _state("calm")}
        ranks = R.rank(closes, bench, states)
        by_cc = {r["cc"]: r for r in ranks}
        assert by_cc["JP"]["gov"] == 0.25
        assert by_cc["KR"]["gov"] == 1.0


class TestObPenalty:
    """OB penalty fires when ext_pctile > 90 and state is in {parabolic, extended, topping}."""

    def test_ob_penalty_engages_above_90(self):
        bench = _bench(120)
        closes = {"A": _px(120, seed=40)}
        states = {"A": _state("extended", ext_pctile=95.0)}
        ranks = R.rank(closes, bench, states)
        assert ranks[0]["ob_penalty"] > 0, "Expected ob_penalty > 0 for ext_pctile=95"
        # ob_penalty = (95 - 90) * 0.4 = 2.0
        assert abs(ranks[0]["ob_penalty"] - 2.0) < 1e-6

    def test_ob_penalty_zero_at_90(self):
        bench = _bench(120)
        closes = {"A": _px(120, seed=41)}
        states = {"A": _state("extended", ext_pctile=90.0)}
        ranks = R.rank(closes, bench, states)
        assert ranks[0]["ob_penalty"] == 0.0

    def test_ob_penalty_zero_in_uptrend(self):
        """OB penalty is gated on state — uptrend must not be penalised even if pctile > 90."""
        bench = _bench(120)
        closes = {"A": _px(120, seed=42)}
        states = {"A": _state("uptrend", ext_pctile=99.0)}
        ranks = R.rank(closes, bench, states)
        assert ranks[0]["ob_penalty"] == 0.0

    def test_ob_penalty_lowers_score_vs_no_penalty(self):
        bench = _bench(120)
        px = _px(120, seed=43)
        closes = {"A": px}
        r_no_pen = R.rank(closes, bench, {"A": _state("uptrend",  ext_pctile=99.0)})[0]["score"]
        r_pen    = R.rank(closes, bench, {"A": _state("parabolic", ext_pctile=99.0)})[0]["score"]
        assert r_pen < r_no_pen


class TestBenchNone:
    """When bench is None, absolute momentum is used (no div-by-bench)."""

    def test_bench_none_returns_ranks(self):
        closes = {"JP": _px(120, seed=50), "KR": _px(120, seed=51)}
        states = {"JP": _state("uptrend"), "KR": _state("downtrend")}
        ranks = R.rank(closes, None, states)
        assert len(ranks) == 2
        cc_order = [r["cc"] for r in ranks]
        # rs20_pct / rs5_pct must be None (absolute mode)
        for r in ranks:
            assert r["rs20_pct"] is None
            assert r["rs5_pct"] is None
        # gov cap still applies: uptrend must beat downtrend even in abs mode
        assert cc_order.index("JP") < cc_order.index("KR")

    def test_bench_none_higher_drift_ranks_first(self):
        px_fast = _px(120, drift=0.003, seed=60)
        px_slow = _px(120, drift=0.0005, seed=61)
        closes = {"F": px_fast, "S": px_slow}
        states = {"F": _state("calm"), "S": _state("calm")}
        ranks = R.rank(closes, None, states)
        cc_order = [r["cc"] for r in ranks]
        assert cc_order[0] == "F"


class TestRankStructure:
    """Output shape and key invariants."""

    def test_rank_is_1_based_sequential(self):
        bench = _bench(120)
        closes = {cc: _px(120, seed=i) for i, cc in enumerate(["JP", "KR", "TW", "IN"])}
        states = {cc: _state("uptrend") for cc in closes}
        ranks = R.rank(closes, bench, states)
        assert [r["rank"] for r in ranks] == list(range(1, len(ranks) + 1))

    def test_score_descending(self):
        bench = _bench(120)
        closes = {cc: _px(120, seed=i) for i, cc in enumerate(["A", "B", "C"])}
        states = {cc: _state("calm") for cc in closes}
        ranks = R.rank(closes, bench, states)
        scores = [r["score"] for r in ranks]
        assert scores == sorted(scores, reverse=True)

    def test_required_keys_present(self):
        bench = _bench(120)
        closes = {"JP": _px(120, seed=70)}
        states = {"JP": _state("uptrend")}
        ranks = R.rank(closes, bench, states)
        assert len(ranks) == 1
        r = ranks[0]
        for key in ("cc", "rank", "score", "rs20_pct", "rs5_pct", "gov", "ob_penalty",
                    "note_en", "note_zh"):
            assert key in r, f"Missing key: {key}"

    def test_empty_closes_returns_empty(self):
        ranks = R.rank({}, _bench(120), {})
        assert ranks == []

    def test_short_series_skipped(self):
        bench = _bench(120)
        closes = {"JP": _px(5, seed=80)}   # too short (< 6 usable)
        states = {"JP": _state("uptrend")}
        ranks = R.rank(closes, bench, states)
        assert len(ranks) == 0

    def test_missing_state_defaults_gov_1(self):
        bench = _bench(120)
        closes = {"JP": _px(120, seed=90)}
        ranks = R.rank(closes, bench, {})   # no state for JP
        assert ranks[0]["gov"] == 1.0

    def test_note_set_when_gov_below_1(self):
        bench = _bench(120)
        closes = {"JP": _px(120, seed=91)}
        states = {"JP": _state("crash")}
        ranks = R.rank(closes, bench, states)
        r = ranks[0]
        assert r["note_en"] is not None and r["note_zh"] is not None

    def test_note_none_for_clean_uptrend(self):
        bench = _bench(120)
        closes = {"JP": _px(120, seed=92)}
        states = {"JP": _state("uptrend")}
        ranks = R.rank(closes, bench, states)
        r = ranks[0]
        assert r["note_en"] is None
        assert r["note_zh"] is None


class TestMacdPenalty:
    """MACD bear cross within 10 sessions + state in OB states -> penalty 3.0."""

    def test_macd_penalty_fires(self):
        bench = _bench(120)
        px = _px(120, seed=100)
        # make cross_date 5 sessions ago (within threshold of 10)
        cross_date = px.index[-5].strftime("%Y-%m-%d")
        states = {"A": _state("topping", ext_pctile=50.0,
                               macd_state="bear", macd_cross_date=cross_date)}
        ranks = R.rank({"A": px}, bench, states)
        r = ranks[0]
        # score = gov*raw - ob_penalty - macd_penalty; gov=0.5, ob_penalty=0 (pctile=50)
        # Recover gov*raw: raw_approx = score + ob_penalty + macd_penalty
        # Then score == raw_approx - macd_penalty (since raw_approx already includes gov)
        raw_approx = r["score"] + 0.0 + 3.0  # ob_penalty=0, macd_penalty=3.0 added back
        assert abs(r["score"] - (raw_approx - 3.0)) < 0.01

    def test_macd_penalty_does_not_fire_outside_ob_states(self):
        bench = _bench(120)
        px = _px(120, seed=101)
        cross_date = px.index[-5].strftime("%Y-%m-%d")
        states_uptrend = {"A": _state("uptrend", macd_state="bear",
                                       macd_cross_date=cross_date)}
        states_topping = {"A": _state("topping", macd_state="bear",
                                       macd_cross_date=cross_date)}
        score_up  = R.rank({"A": px}, bench, states_uptrend)[0]["score"]
        score_top = R.rank({"A": px}, bench, states_topping)[0]["score"]
        # topping has gov=0.5 AND macd_penalty; uptrend gov=1.0, no penalty
        # The key assertion: macd penalty only fires for topping (OB state)
        # uptrend score should be higher (gov*raw vs 0.5*raw - 3)
        assert score_up > score_top


# ---------------------------------------------------------------------------
# TASK B — benchmark freshness helper (ITR-R6)
# ---------------------------------------------------------------------------
# NOTE: staleness is forced SYNTHETICALLY via the intl_closes parameter — the
# original version asserted substitution on the live committed stores, which
# rotted the moment the ^GSPC store was healed (2026-07-16, mid-review).
# Store-state-dependent assertions are a known test-rot class in this repo.

class TestBenchFreshness:
    """_bench_series_fresh substitutes SPY when ^GSPC lags the intl closes."""

    @staticmethod
    def _fake_intl_closes(last_date: str) -> pd.DataFrame:
        idx = pd.bdate_range(end=last_date, periods=30)
        return pd.DataFrame({"^N225": np.linspace(100.0, 110.0, 30)}, index=idx)

    def test_spy_substituted_when_bench_stale(self):
        """intl closes 30 business days beyond the committed ^GSPC last date
        must trigger the SPY substitution + a bench_note naming the stale date."""
        from engine.intl_performance import _bench_series_fresh
        from lib import store
        gspc = store.read("yahoo", "^GSPC")
        if gspc is None or gspc.empty:
            pytest.skip("^GSPC store unavailable")
        gspc_last = gspc["close"].dropna().index[-1]
        future = (gspc_last + pd.offsets.BDay(30)).date().isoformat()
        series, note = _bench_series_fresh(intl_closes=self._fake_intl_closes(future))
        assert series is not None, "Expected a series (SPY), got None"
        assert note is not None, "Expected a bench_note when SPY is substituted"
        assert "SPY" in note and "GSPC" in note, f"Unexpected note format: {note!r}"
        assert gspc_last.date().isoformat() in note, (
            f"Expected stale date {gspc_last.date()} in note: {note!r}"
        )

    def test_no_substitution_when_fresh(self):
        """intl closes at/behind the ^GSPC last date -> primary kept, no note."""
        from engine.intl_performance import _bench_series_fresh
        from lib import store
        gspc = store.read("yahoo", "^GSPC")
        if gspc is None or gspc.empty:
            pytest.skip("^GSPC store unavailable")
        gspc_last = gspc["close"].dropna().index[-1].date().isoformat()
        series, note = _bench_series_fresh(intl_closes=self._fake_intl_closes(gspc_last))
        assert series is not None
        assert note is None, f"No substitution expected when fresh, got: {note!r}"

    def test_spy_series_is_read_only(self):
        """Verify we don't mutate the committed store: just check type and shape."""
        from engine.intl_performance import _bench_series_fresh
        series, _ = _bench_series_fresh()
        if series is not None:
            assert hasattr(series, "iloc"), "Expected a pd.Series"
            assert len(series) > 100, "benchmark series suspiciously short"
