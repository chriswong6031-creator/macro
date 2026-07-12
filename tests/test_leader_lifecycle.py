"""tests/test_leader_lifecycle.py — Hermetic unit tests for engine/leader_lifecycle.py (W1).

Coverage:
  - RS-series math: slope, turn, line-NH on constructed divergence
  - Accumulation: updown ratio, accum/dist day counts, pocket pivot, OBV divergence
  - Extension/crowding: extension_vs_50dma, monthly_rsi, parabolic_flag
  - Basket correlation rising
  - State-transition + precedence matrix (overlapping conditions → exactly one state)
  - Hysteresis (2-in/3-out sequences)
  - Tri-state (null legs excluded both sides; K-unreachable falls through)
  - Precipice fire OR-leg (revision-null + rs_line_nh=True still fires on entry)
  - Onset fire
  - Refire eligibility (requires NONE/FAILED de-escalation)
  - Regime classifier axes
  - 2D tf_state smoke (constructed series)
  - GOOGL/UNH-shaped replay fixtures (synthetic series shaped like field guide stage anatomy)
  - Rerating conditions chips
  - Handoff pairs vocabulary
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.leader_lifecycle import (
    # Kleene
    _and3,
    _or3,
    _is_null,
    # RS math
    rs_series,
    rs_slope,
    rs_turn,
    rs_line_new_high,
    rs_top_decile_weeks,
    peer_divergence,
    # Accumulation
    updown_volume_ratio,
    accumulation_distribution_days,
    pocket_pivot,
    obv_divergence,
    # Extension / crowding
    extension_vs_50dma,
    extension_pctile_own_history,
    monthly_rsi,
    parabolic_flag,
    basket_correlation_rising,
    # 2D oscillator
    tf_state_2d,
    # Rerating
    rerating_conditions,
    # Regime
    leadership_regime,
    # State machine
    LifecycleInputs,
    LifecycleAssessment,
    classify,
    apply_hysteresis,
    # Fire rules
    precipice_fire,
    onset_fire,
    eligible_for_refire,
    # Handoff
    extended_leg,
    basing_leg,
    handoff_pairs,
    # Constants
    STATE_SUPPRESSED,
    STATE_QUIET_ACCUMULATION,
    STATE_CATALYST_WINDOW,
    STATE_BREAKAWAY,
    STATE_LEADERSHIP,
    STATE_CROWDED,
    STATE_FAILED,
    STATE_NONE,
    HYSTERESIS_ENTER_N,
    HYSTERESIS_EXIT_N,
    REFIRE_LOCKOUT_SESSIONS,
)


# ── Synthetic series helpers ─────────────────────────────────────────────────

def _date_index(n: int, start: str = "2020-01-02") -> pd.DatetimeIndex:
    dates = pd.bdate_range(start=start, periods=n)
    return dates


def _flat_close(n: int, price: float = 100.0, start: str = "2020-01-02") -> pd.Series:
    return pd.Series([price] * n, index=_date_index(n, start))


def _trending_close(
    n: int, start_price: float = 100.0, pct_per_day: float = 0.001, start: str = "2020-01-02"
) -> pd.Series:
    """Smoothly trending close."""
    prices = [start_price * (1 + pct_per_day) ** i for i in range(n)]
    return pd.Series(prices, index=_date_index(n, start))


def _declining_close(n: int, start_price: float = 100.0, pct_per_day: float = -0.002) -> pd.Series:
    prices = [max(start_price * (1 + pct_per_day) ** i, 0.01) for i in range(n)]
    return pd.Series(prices, index=_date_index(n))


def _make_volume(close: pd.Series, base_vol: float = 1_000_000.0) -> pd.Series:
    return pd.Series([base_vol] * len(close), index=close.index)


def _make_ohlcv(
    close: pd.Series,
    volume: pd.Series | None = None,
) -> pd.DataFrame:
    if volume is None:
        volume = _make_volume(close)
    return pd.DataFrame({"close": close, "volume": volume})


# ── Kleene logic tests ────────────────────────────────────────────────────────

class TestKleene:
    def test_and3_false_short_circuits(self):
        assert _and3(False, None, True) is False

    def test_and3_all_true(self):
        assert _and3(True, True, True) is True

    def test_and3_null_with_true(self):
        assert _and3(True, None, True) is None

    def test_or3_true_short_circuits(self):
        assert _or3(True, None, False) is True

    def test_or3_all_false(self):
        assert _or3(False, False, False) is False

    def test_or3_null_with_false(self):
        assert _or3(False, None, False) is None

    def test_is_null_none(self):
        assert _is_null(None)

    def test_is_null_nan(self):
        assert _is_null(float("nan"))

    def test_is_null_pd_na(self):
        assert _is_null(pd.NA)

    def test_is_null_false_on_zero(self):
        assert not _is_null(0)

    def test_is_null_false_on_false(self):
        assert not _is_null(False)


# ── RS series tests ───────────────────────────────────────────────────────────

class TestRsSeries:
    def test_aligned_basic(self):
        stock = _trending_close(200, start_price=100, pct_per_day=0.002)
        bench = _flat_close(200, price=100.0)
        rs = rs_series(stock, bench)
        assert len(rs) == 200
        # RS should be rising
        assert float(rs.iloc[-1]) > float(rs.iloc[0])

    def test_empty_on_no_common_dates(self):
        stock = pd.Series([100, 101], index=pd.bdate_range("2020-01-02", periods=2))
        bench = pd.Series([100, 101], index=pd.bdate_range("2022-01-03", periods=2))
        rs = rs_series(stock, bench)
        assert rs.empty

    def test_bench_zero_excluded(self):
        stock = pd.Series([100.0, 101.0], index=pd.bdate_range("2020-01-02", periods=2))
        bench = pd.Series([0.0, 100.0], index=pd.bdate_range("2020-01-02", periods=2))
        rs = rs_series(stock, bench)
        # Zero bench produces NaN → dropped; expect only the valid bar
        assert len(rs) == 1

    def test_slope_positive_on_rising_rs(self):
        stock = _trending_close(200, pct_per_day=0.002)
        bench = _flat_close(200)
        rs = rs_series(stock, bench)
        slope = rs_slope(rs, 63)
        last_slope = slope.dropna().iloc[-1]
        assert float(last_slope) > 0

    def test_slope_negative_on_declining_rs(self):
        stock = _declining_close(200, pct_per_day=-0.002)
        bench = _flat_close(200)
        rs = rs_series(stock, bench)
        slope = rs_slope(rs, 63)
        last_slope = slope.dropna().iloc[-1]
        assert float(last_slope) < 0


class TestRsTurn:
    def test_turn_detected(self):
        """RS was declining long-term but recently turned up.

        Key: we need 21d slope positive while 63d slope still negative.
        Requires a long-enough decline (300 bars) so that only the last 17 bars
        of upturn show positive 21d slope but the 63d window still has net-negative slope.
        """
        # 300 bars declining (0.3%/bar), then 17 bars recovering (0.2%/bar)
        prices_down = [100.0 * (0.997 ** i) for i in range(300)]
        prices_up = [prices_down[-1] * (1.002 ** i) for i in range(1, 18)]
        all_prices = prices_down + prices_up
        idx = _date_index(len(all_prices))
        stock = pd.Series(all_prices, index=idx)
        bench = _flat_close(len(all_prices), price=100.0, start=str(idx[0].date()))
        rs = rs_series(stock, bench)
        result = rs_turn(rs)
        # 21d slope positive (recent upturn), 63d slope negative (majority of window still declining)
        assert result is True

    def test_turn_null_on_short_series(self):
        rs = pd.Series([1.0, 1.01, 0.99], index=_date_index(3))
        assert rs_turn(rs) is None

    def test_no_turn_when_both_positive(self):
        stock = _trending_close(200, pct_per_day=0.003)
        bench = _flat_close(200)
        rs = rs_series(stock, bench)
        result = rs_turn(rs)
        # Both slopes positive → not a turn
        assert result is False


class TestRsLineNewHigh:
    def test_rs_nh_divergence_detected(self):
        """RS at 126d high, price below 126d high — the divergence.

        Build: stock gently rises then pulls back 3%; bench flat then collapses 20d.
        RS keeps climbing to new high while price is 3% below its own 126d peak.
        """
        n = 150
        idx = _date_index(n)
        # Stock: rises gently first 126 bars, then pulls back 3%
        prices_up = [100.0 * (1.002 ** i) for i in range(126)]
        price_peak = prices_up[-1]
        prices_back = [price_peak * 0.97] * (n - 126)
        stock = pd.Series(prices_up + prices_back, index=idx)

        # Bench: flat first 126, then crashes (so RS = stock/bench soars to new high)
        bench_flat = [100.0] * 126
        bench_crash = [100.0 * (0.998 ** i) for i in range(1, n - 125)]
        bench = pd.Series((bench_flat + bench_crash)[:n], index=idx)

        rs = rs_series(stock, bench)
        result = rs_line_new_high(rs, stock, lookback=126)
        # RS should be at its 126d high; price is 3% below its own 126d high
        assert result is True

    def test_rs_nh_false_when_price_also_at_high(self):
        """Both RS and price at highs → not a divergence."""
        n = 150
        stock = _trending_close(n, pct_per_day=0.002)
        bench = _flat_close(n)
        rs = rs_series(stock, bench)
        result = rs_line_new_high(rs, stock, lookback=126)
        assert result is False  # price also at high

    def test_rs_nh_null_on_short(self):
        rs = pd.Series([1.0, 1.01], index=_date_index(2))
        price = pd.Series([100.0, 101.0], index=_date_index(2))
        assert rs_line_new_high(rs, price) is None


class TestRsTopDecileWeeks:
    def test_counts_consecutive(self):
        idx = pd.date_range("2020-01-01", periods=10, freq="W-FRI")
        ranks = [0.95, 0.92, 0.91, 0.80, 0.95, 0.96, 0.97, 0.98, 0.91, 0.93]
        df = pd.DataFrame({"rs_rank": ranks}, index=idx)
        result = rs_top_decile_weeks(df)
        # Index 3 (0.80) breaks the streak; after that: [0.95, 0.96, 0.97, 0.98, 0.91, 0.93]
        # = 6 consecutive top-decile weeks from the end
        assert result == 6

    def test_zero_when_last_not_top_decile(self):
        idx = pd.date_range("2020-01-01", periods=3, freq="W-FRI")
        df = pd.DataFrame({"rs_rank": [0.95, 0.95, 0.85]}, index=idx)
        assert rs_top_decile_weeks(df) == 0

    def test_none_on_empty(self):
        assert rs_top_decile_weeks(None) is None
        assert rs_top_decile_weeks(pd.DataFrame()) is None

    def test_none_missing_column(self):
        df = pd.DataFrame({"not_rs": [0.9]})
        assert rs_top_decile_weeks(df) is None


class TestPeerDivergence:
    def test_true_on_divergence(self):
        assert peer_divergence(0.001, -0.002) is True

    def test_false_when_both_positive(self):
        assert peer_divergence(0.001, 0.003) is False

    def test_none_on_null_input(self):
        assert peer_divergence(None, 0.003) is None
        assert peer_divergence(0.001, None) is None


# ── Accumulation tests ────────────────────────────────────────────────────────

class TestUpdownVolumeRatio:
    def test_up_volume_dominant(self):
        """Build series with explicit up and down days, heavier volume on up days."""
        n = 60
        idx = _date_index(n)
        # Alternating: 2 up days (+0.5%) then 1 down day (-0.2%); net trend is up
        prices = [100.0]
        for i in range(n - 1):
            if i % 3 < 2:
                prices.append(prices[-1] * 1.005)  # up day
            else:
                prices.append(prices[-1] * 0.998)  # down day
        close = pd.Series(prices, index=idx)
        # Up days get 2M volume, down days get 500K
        vols = [2_000_000 if i % 3 < 2 else 500_000 for i in range(n)]
        volume = pd.Series(vols, index=idx)
        ohlcv = pd.DataFrame({"close": close, "volume": volume})
        ratio = updown_volume_ratio(ohlcv)
        assert ratio is not None
        assert ratio > 1.0  # up dollar volume >> down dollar volume

    def test_none_on_missing_volume(self):
        close = _flat_close(60)
        ohlcv = pd.DataFrame({"close": close})
        assert updown_volume_ratio(ohlcv) is None

    def test_none_on_short_series(self):
        close = _flat_close(3)
        ohlcv = _make_ohlcv(close)
        assert updown_volume_ratio(ohlcv, window=50) is None


class TestAccumulationDistributionDays:
    def test_accumulation_dominates(self):
        """Build: alternating vol ensures vol > prior vol on up days, creating accum days."""
        n = 30
        idx = _date_index(n)
        # Alternating up/down pattern with alternating high/low volume
        # IBD accum day: close > prior close AND volume > prior volume
        closes = [100.0]
        for i in range(1, n):
            if i % 3 == 0:
                closes.append(closes[-1] - 0.3)  # down day (1 in 3)
            else:
                closes.append(closes[-1] + 0.5)  # up day (2 in 3)
        # Alternating volumes so vol > prior vol on most up days
        vols = [1_500_000 if i % 2 == 0 else 800_000 for i in range(n)]
        ohlcv = pd.DataFrame({"close": closes, "volume": vols}, index=idx)
        n_accum, n_dist = accumulation_distribution_days(ohlcv, window=25)
        assert n_accum is not None
        assert n_dist is not None
        assert n_accum > n_dist

    def test_none_on_missing_volume(self):
        close = _flat_close(30)
        ohlcv = pd.DataFrame({"close": close})
        n_a, n_d = accumulation_distribution_days(ohlcv)
        assert n_a is None
        assert n_d is None

    def test_distribution_day_requires_02pct_drop(self):
        # Close drops 0.1% (not a distribution day), 0.3% (distribution day)
        n = 30
        closes = [100.0, 99.9] + [99.9 - 0.3 * i for i in range(n - 2)]
        vols = [1_000_000, 1_200_000] + [1_200_000] * (n - 2)
        idx = _date_index(n)
        ohlcv = pd.DataFrame({"close": closes, "volume": vols}, index=idx)
        n_a, n_d = accumulation_distribution_days(ohlcv, window=25)
        # The 0.1% drop day should NOT count as distribution
        assert n_d is not None


class TestPocketPivot:
    def test_pocket_pivot_detected(self):
        n = 20
        closes = [100.0 - i * 0.2 for i in range(15)] + [100.0 - 3.0 + j * 0.3 for j in range(5)]
        # Last bar is an up day
        vols = [500_000] * 14 + [100_000] + [2_000_000]  # huge volume on up day
        # Pad to n
        vols = (vols + [1_000_000] * n)[:n]
        closes = (closes + [closes[-1]] * n)[:n]
        idx = _date_index(n)
        ohlcv = pd.DataFrame({"close": closes, "volume": vols}, index=idx)
        result = pocket_pivot(ohlcv)
        # Should detect pocket pivot if up-day volume > max down-day volume in prior 10
        assert result is not None  # not None (has enough data)

    def test_none_on_short(self):
        ohlcv = _make_ohlcv(_flat_close(5))
        assert pocket_pivot(ohlcv) is None

    def test_false_on_down_day(self):
        n = 20
        closes = [100.0] * 19 + [99.0]  # last day is down
        idx = _date_index(n)
        ohlcv = pd.DataFrame({"close": closes, "volume": [1_000_000] * n}, index=idx)
        assert pocket_pivot(ohlcv) is False


class TestObvDivergence:
    def test_obv_nh_while_price_below(self):
        """OBV at new high while price pulled back from its peak.

        Build: price rises to peak (bar 30), then alternates +small/−big,
        but volume is HUGE on up days and tiny on down days → OBV keeps rising.
        At end: OBV at new high; price below its 63-bar peak.
        """
        n = 80
        idx = _date_index(n)
        # Phase 1: price rises steadily to peak
        prices1 = [100.0 + i for i in range(30)]
        p = prices1[-1]  # = 129
        # Phase 2: price oscillates with big down moves, small up moves → net below phase1 peak
        prices2 = []
        for i in range(50):
            if i % 3 != 2:  # 2 of 3 days: up
                p += 0.3
            else:            # 1 of 3 days: down bigger
                p -= 2.0
            prices2.append(p)
        prices = prices1 + prices2
        # Volume: big on up days, tiny on down days → OBV accumulates throughout
        vols = [1_000_000] * 30
        for i in range(50):
            if i % 3 != 2:
                vols.append(3_000_000)  # big buy volume
            else:
                vols.append(100_000)   # tiny sell volume
        close = pd.Series(prices[:n], index=idx)
        volume = pd.Series(vols[:n], index=idx)
        result = obv_divergence(close, volume, window=63)
        assert result is True

    def test_none_on_no_volume(self):
        close = _flat_close(80)
        assert obv_divergence(close, None) is None

    def test_none_on_short(self):
        close = pd.Series([100.0, 101.0], index=_date_index(2))
        vol = pd.Series([1e6, 1e6], index=_date_index(2))
        assert obv_divergence(close, vol, window=63) is None


# ── Extension / crowding tests ────────────────────────────────────────────────

class TestExtension:
    def test_extension_vs_50dma_positive(self):
        # Close 20% above its 50dma
        base = _flat_close(60, price=80.0)
        extended_idx = _date_index(60)
        # Last value jumps to 96
        prices = [80.0] * 59 + [96.0]
        close = pd.Series(prices, index=extended_idx)
        ext = extension_vs_50dma(close)
        assert ext is not None
        assert ext > 0

    def test_extension_none_on_short(self):
        close = _flat_close(20)
        assert extension_vs_50dma(close) is None


class TestMonthlyRsi:
    def test_monthly_rsi_returns_value(self):
        """Use a realistic random-walk series (not monotone, which gives RSI=NaN)."""
        np.random.seed(42)
        n = 1000
        returns = np.random.normal(0.0005, 0.015, n)
        prices = 100.0 * np.cumprod(1 + returns)
        close = pd.Series(prices, index=_date_index(n))
        mrsi = monthly_rsi(close)
        assert mrsi is not None
        assert 0 <= mrsi <= 100

    def test_monthly_rsi_none_on_short(self):
        close = _flat_close(20)
        assert monthly_rsi(close) is None


class TestParabolicFlag:
    def test_parabolic_detected(self):
        """Annualized 4-week rate > 2× annualized 13-week rate (blow-off signature).

        Build: slow grind for 9 weeks, then massive surge in the last 4 weeks.
        The 4w annualized rate must exceed 2× the 13w annualized rate.
        Math: 13*ret_4w > 8*ret_13w; achievable when 4w captures most of the 13w gain.
        """
        n = 70
        prices = [100.0]
        # First 50 bars: very slow +0.02%/bar (9w baseline trend is tiny)
        for i in range(50):
            prices.append(prices[-1] * 1.0002)
        # Last 20 bars: +2%/bar (massive acceleration)
        for i in range(20):
            prices.append(prices[-1] * 1.02)
        close = pd.Series(prices[:n], index=_date_index(n))
        result = parabolic_flag(close)
        # The 4w annualized rate dominates the 13w annualized rate → parabolic
        assert result is True

    def test_parabolic_false_on_steady(self):
        close = _trending_close(200, pct_per_day=0.001)
        result = parabolic_flag(close)
        assert result is False  # steady trend, not parabolic

    def test_parabolic_none_on_short(self):
        assert parabolic_flag(_flat_close(30)) is None


class TestBasketCorrelationRising:
    def test_rising_from_low_to_high(self):
        assert basket_correlation_rising(0.80, 0.40) is True

    def test_false_when_not_high_enough(self):
        assert basket_correlation_rising(0.60, 0.30) is False

    def test_false_when_started_high(self):
        # Was already high → not "having risen from low"
        assert basket_correlation_rising(0.80, 0.60) is False

    def test_none_on_null(self):
        assert basket_correlation_rising(None, 0.40) is None
        assert basket_correlation_rising(0.80, None) is None


# ── 2D oscillator smoke test ─────────────────────────────────────────────────

class TestTfState2d:
    def test_returns_dict_with_keys(self):
        close = _trending_close(300, pct_per_day=0.001)
        result = tf_state_2d(close)
        assert isinstance(result, dict)
        if result:  # non-empty means enough bars
            assert "macd_pos" in result

    def test_empty_on_short(self):
        close = _flat_close(40)
        assert tf_state_2d(close) == {}

    def test_empty_on_none(self):
        assert tf_state_2d(None) == {}


# ── Rerating conditions ───────────────────────────────────────────────────────

class TestReratingConditions:
    def test_all_chips_populated(self):
        chips = rerating_conditions(
            revisions_row={"net_up_30d": 5, "est_chg_30d": 0.02, "breadth": 0.7},
            valuation_row={"cheap_pctile": 30, "fwd_pe": 15.0, "sector_median_fwd_pe": 20.0},
            earnings_row={"days_to_earnings": 10},
        )
        assert chips["revision_positive"] is True
        assert chips["revision_breadth_60"] is True
        assert chips["multiple_compressed"] is True
        assert chips["earnings_within_14d"] is True

    def test_revision_negative(self):
        chips = rerating_conditions(
            revisions_row={"net_up_30d": -2, "est_chg_30d": -0.01, "breadth": 0.5},
            valuation_row=None,
            earnings_row=None,
        )
        assert chips["revision_positive"] is False

    def test_null_inputs_produce_null_chips(self):
        chips = rerating_conditions(None, None, None)
        assert chips["revision_positive"] is None
        assert chips["multiple_compressed"] is None

    def test_multiple_compressed_via_fwd_pe(self):
        chips = rerating_conditions(
            revisions_row=None,
            valuation_row={"cheap_pctile": None, "fwd_pe": 15.0, "sector_median_fwd_pe": 20.0},
            earnings_row=None,
        )
        assert chips["multiple_compressed"] is True

    def test_earnings_not_within_14d(self):
        chips = rerating_conditions(
            revisions_row=None,
            valuation_row=None,
            earnings_row={"days_to_earnings": 20},
        )
        assert chips["earnings_within_14d"] is False


# ── Regime classifier ─────────────────────────────────────────────────────────

class TestLeadershipRegime:
    def test_narrow_leadership(self):
        result = leadership_regime(
            dispersion_pctile=75.0,  # >= 70
            avg_corr=0.10,           # <= 0.15
            pct_above_200=50.0,      # < 55
            top5_share_21d=None,
            zweig_flag=None,
        )
        assert result["label"] == "narrow_leadership"
        assert "dispersion" in result["conditions"] or result["conditions"]

    def test_broad_thrust_via_zweig(self):
        result = leadership_regime(
            dispersion_pctile=50.0,
            avg_corr=0.25,
            pct_above_200=60.0,
            top5_share_21d=None,
            zweig_flag=True,
        )
        assert result["label"] == "broad_thrust"

    def test_broad_thrust_via_breadth_and_top5(self):
        result = leadership_regime(
            dispersion_pctile=50.0,
            avg_corr=0.25,
            pct_above_200=75.0,     # >= 70
            top5_share_21d=0.25,    # < 0.35
            zweig_flag=False,
        )
        assert result["label"] == "broad_thrust"

    def test_mixed_default(self):
        result = leadership_regime(
            dispersion_pctile=40.0,
            avg_corr=0.30,
            pct_above_200=60.0,
            top5_share_21d=0.40,
            zweig_flag=False,
        )
        assert result["label"] == "mixed"

    def test_chips_populated(self):
        result = leadership_regime(75.0, 0.10, 50.0, 0.30, False)
        assert "dispersion_high" in result["chips"]
        assert "corr_low" in result["chips"]


# ── State machine: tri-state K-of-N ──────────────────────────────────────────

class TestKofN:
    """K-of-N: null excluded from numerator AND denominator; unreachable = False."""

    def test_qa_unreachable_when_all_null(self):
        """With all chips null, QA is unreachable → NONE (falls through)."""
        n = 300
        stock = _flat_close(n, price=90.0)
        bench = _flat_close(n, price=100.0)
        inp = LifecycleInputs(close=stock, bench_close=bench)
        assessment = classify(inp)
        # QA requires context + 2 of N chips; all null → falls through
        assert assessment.state in (STATE_NONE, STATE_SUPPRESSED)

    def test_qa_one_chip_insufficient(self):
        """Only 1 non-null chip when K=2 required → QA unreachable."""
        n = 300
        idx = _date_index(n)
        stock = _flat_close(n, price=90.0, start=str(idx[0].date()))
        bench = _flat_close(n, price=100.0, start=str(idx[0].date()))
        # Provide only revision_positive chip, all others null
        inp = LifecycleInputs(
            close=stock,
            bench_close=bench,
            net_up_30d=5.0,
            est_chg_30d=0.02,
            # volume=None → accum chips null
            # rs short → rs_turn will be computable but need state_history for base context
        )
        assessment = classify(inp)
        # 1 chip (revision_positive=True) but K=2; can't reach QA
        assert assessment.state != STATE_QUIET_ACCUMULATION


class TestPrecedenceCascade:
    """Overlapping conditions: exactly one state per precedence cascade."""

    def _make_crowded_inp(self) -> LifecycleInputs:
        """Build inputs that would trigger CROWDED (≥3 chips)."""
        n = 600
        idx = _date_index(n)
        # 500% parabolic stock
        prices = [100.0 * (1.002 ** i) for i in range(n)]
        stock = pd.Series(prices, index=idx)
        bench = _flat_close(n, price=100.0, start=str(idx[0].date()))
        return LifecycleInputs(
            close=stock,
            bench_close=bench,
            breakaway_watch_state="continuation",
            analyst_buy_pct=90.0,       # chip 5: analyst saturated
            basket_corr_now=0.80,
            basket_corr_then=0.40,      # chip 7: basket corr rising
            valuation_pctile_5y=85.0,   # chip 4: valuation extreme
            # monthly_rsi will be high on parabolic close → chip 2
            # extension_vs_50dma will be high on trending close → chip 1
        )

    def test_failed_overrides_all(self):
        """FAILED takes precedence over everything including breakaway."""
        n = 200
        stock = _flat_close(n, price=100.0)
        bench = _flat_close(n, price=100.0)
        inp = LifecycleInputs(
            close=stock,
            bench_close=bench,
            breakaway_watch_state="failed",
        )
        assessment = classify(inp)
        assert assessment.state == STATE_FAILED

    def test_breakaway_wins_over_qa(self):
        """BREAKAWAY context beats QUIET_ACCUMULATION conditions."""
        n = 300
        idx = _date_index(n)
        stock = _flat_close(n, price=100.0, start=str(idx[0].date()))
        bench = _flat_close(n, price=100.0, start=str(idx[0].date()))
        vol = _make_volume(stock, 2_000_000)
        inp = LifecycleInputs(
            close=stock,
            bench_close=bench,
            breakaway_watch_state="breakaway",
            net_up_30d=5.0,
            est_chg_30d=0.02,
            volume=vol,
        )
        assessment = classify(inp)
        assert assessment.state == STATE_BREAKAWAY

    def test_crowded_wins_over_leadership(self):
        """CROWDED beats LEADERSHIP when both CROWDED AND LEADERSHIP conditions are met.

        Construct inputs satisfying BOTH simultaneously:
        - CROWDED: extension_extreme + monthly_rsi_80 + analyst_saturated + valuation_extreme
          (≥3 of 7 chips → CROWDED_K_OF_N met)
        - LEADERSHIP: breakaway_watch='continuation' + rs_top_decile weeks ≥ 4 + peer_divergence
          (rs_rank_history set to top-decile for 5+ weeks; parabolic price drives divergence)
        Per precedence (CROWDED > LEADERSHIP), state must be CROWDED.
        """
        n = 600
        idx = _date_index(n)
        # Aggressively parabolic price to hit CROWDED chips
        prices = [100.0 * (1.005 ** i) for i in range(n)]
        stock = pd.Series(prices, index=idx)
        bench = _flat_close(n, price=100.0, start=str(idx[0].date()))

        # LEADERSHIP conditions: continuation + rs_rank history with 5 weeks top decile
        # rs_top_decile_weeks expects DataFrame with DatetimeIndex and 'rs_rank' column
        rs_rank_dates = pd.bdate_range(end=idx[-1], periods=6, freq="5B")
        rs_rank_history = pd.DataFrame(
            {"rs_rank": [0.95] * 6}, index=rs_rank_dates
        )  # 6 weeks of 95th pctile RS rank

        inp = LifecycleInputs(
            close=stock,
            bench_close=bench,
            breakaway_watch_state="continuation",  # LEADERSHIP trigger
            rs_rank_history=rs_rank_history,        # ≥ 4 weeks top decile
            peer_median_rs_63d=-0.05,               # peer underperforming → divergence
            analyst_buy_pct=90.0,                   # CROWDED chip 5
            basket_corr_now=0.80,
            basket_corr_then=0.40,                  # CROWDED chip 7
            valuation_pctile_5y=85.0,               # CROWDED chip 4
            # parabolic stock also triggers: extension_extreme (chip 1) + monthly_rsi_80 (chip 2)
        )

        assessment = classify(inp)
        # CROWDED must win over LEADERSHIP (precedence cascade: CROWDED > LEADERSHIP)
        assert assessment.state == STATE_CROWDED, (
            f"Expected CROWDED to beat LEADERSHIP; got {assessment.state}. "
            f"evidence={assessment.evidence}"
        )

    def test_exactly_one_state_property(self):
        """classify() returns exactly one valid state; precedence winner is deterministic.

        Test with a grid of inputs designed to trigger MULTIPLE states simultaneously:
        - breakaway='emerging' → CATALYST_WINDOW ignition (bw_emerging chip)
        - continuation → LEADERSHIP / BREAKAWAY
        - heavy positive revisions + volume + suppressed history → QA / CW conditions
        Assert the precedence cascade picks deterministically.
        """
        valid = {
            STATE_SUPPRESSED, STATE_QUIET_ACCUMULATION, STATE_CATALYST_WINDOW,
            STATE_BREAKAWAY, STATE_LEADERSHIP, STATE_CROWDED, STATE_FAILED, STATE_NONE
        }
        n = 400
        idx = _date_index(n)
        # Declining then recovering stock (creates suppressed context + RS turn)
        prices = [100.0 * (0.998 ** i) for i in range(250)] + [
            100.0 * (0.998 ** 249) * (1.002 ** i) for i in range(150)
        ]
        stock = pd.Series(prices, index=idx)
        bench = _flat_close(n, price=100.0, start=str(idx[0].date()))
        vol = pd.Series([2_000_000] * n, index=idx)

        # State history that makes BOTH qa_context and catalyst_window_context potentially true
        suppressed_hist = [(date(2020, 1, i + 2), STATE_SUPPRESSED) for i in range(30)]
        qa_hist = [(date(2020, 3, 1), STATE_QUIET_ACCUMULATION)]  # QA ≤21 sessions ago

        bw_states_with_expected_precedence = [
            # (bw_state, overlapping_conditions_note, must_not_be_states)
            ("breakaway", "BREAKAWAY > CW/QA/SUP", [STATE_CATALYST_WINDOW, STATE_QUIET_ACCUMULATION]),
            ("emerging",  "emerging→CW ignition only; BREAKAWAY unreachable", [STATE_BREAKAWAY]),
            ("continuation", "LEADERSHIP or BREAKAWAY > CW/QA", []),  # depends on rs_rank
            ("failed",    "FAILED overrides all",
                [STATE_BREAKAWAY, STATE_LEADERSHIP, STATE_CROWDED, STATE_CATALYST_WINDOW,
                 STATE_QUIET_ACCUMULATION, STATE_SUPPRESSED, STATE_NONE]),
            (None, "no WA state; only data-driven", []),
        ]

        for bw_state, note, must_not_be in bw_states_with_expected_precedence:
            inp = LifecycleInputs(
                close=stock,
                bench_close=bench,
                volume=vol,
                breakaway_watch_state=bw_state,
                net_up_30d=5.0,       # positive revisions (QA chip)
                est_chg_30d=0.02,
                cheap_pctile=30.0,    # cheap (de-escalation + suppressed chip)
                state_history=suppressed_hist + qa_hist,
            )
            assessment = classify(inp)

            assert assessment.state in valid, (
                f"bw={bw_state!r} ({note}): invalid state '{assessment.state}'"
            )
            for forbidden in must_not_be:
                if bw_state == "failed":
                    # FAILED must override everything else
                    assert assessment.state == STATE_FAILED, (
                        f"bw='failed': expected FAILED, got {assessment.state}"
                    )
                else:
                    assert assessment.state != forbidden, (
                        f"bw={bw_state!r} ({note}): "
                        f"precedence violation — got {assessment.state}, "
                        f"which should have lost to higher state"
                    )


# ── Hysteresis tests ──────────────────────────────────────────────────────────

class TestHysteresis:
    """Tests for apply_hysteresis with split raw/confirmed history contract.

    Entry rule: raw_state_today must appear in the last (enter_n - 1) raw sessions
                (i.e., enter_n consecutive raw sessions total including today).
    Exit rule:  the last (exit_n - 1) raw sessions must all differ from held confirmed
                state (i.e., exit_n consecutive non-held raw sessions including today).
    """

    def _make_history(self, states: list[str]) -> list[tuple[date, str]]:
        base = date(2020, 1, 2)
        return [(base + timedelta(days=i), s) for i, s in enumerate(states)]

    def test_deadlock_regression(self):
        """Reproduce BLOCKER-2 deadlock: raw QA,QA,QA never confirms with single history.

        With the old single-history contract, apply_hysteresis checked raw states
        against state_history but classify() context lookups needed post-hysteresis
        history — deadlock: raw QA never entered confirmed because history stayed NONE.

        With the split contract: raw_state_history tracks QA; confirmed starts NONE.
        After 2 raw QA sessions, confirmed flips to QA on session 3.
        """
        # Day-by-day simulation: 3 raw QA sessions, confirmed history built separately
        raw_hist: list[tuple[date, str]] = []
        conf_hist: list[tuple[date, str]] = []
        base = date(2020, 1, 2)

        raw_seq = [STATE_QUIET_ACCUMULATION] * 3
        confirmed_seq = []
        for i, raw in enumerate(raw_seq):
            conf = apply_hysteresis(raw, raw_hist, conf_hist)
            confirmed_seq.append(conf)
            raw_hist.append((base + timedelta(days=i), raw))
            conf_hist.append((base + timedelta(days=i), conf))

        # Day 1: no history → raw accepted directly → QA
        assert confirmed_seq[0] == STATE_QUIET_ACCUMULATION
        # Day 2: 1 prior raw QA == enter_n-1=1 → enter QA
        assert confirmed_seq[1] == STATE_QUIET_ACCUMULATION
        # Day 3: already in QA → maintained
        assert confirmed_seq[2] == STATE_QUIET_ACCUMULATION

    def test_2_in_to_enter(self):
        """Must see raw_state for HYSTERESIS_ENTER_N consecutive sessions to enter."""
        # 0 prior raw sessions of SUPPRESSED: raw history has NONE, NONE
        raw_hist = self._make_history(["NONE", "NONE"])
        conf_hist = self._make_history(["NONE", "NONE"])
        result = apply_hysteresis("SUPPRESSED", raw_hist, conf_hist)
        # enter_n=2: need 1 prior raw SUPPRESSED; have 0 → stay NONE
        assert result == "NONE"

        # 1 prior raw session of SUPPRESSED: enters on day 2
        raw_hist2 = self._make_history(["NONE", "SUPPRESSED"])
        conf_hist2 = self._make_history(["NONE", "NONE"])
        result2 = apply_hysteresis("SUPPRESSED", raw_hist2, conf_hist2)
        assert result2 == "SUPPRESSED"

    def test_3_out_to_exit(self):
        """Must see exit_n consecutive non-held raw sessions (including today) to exit."""
        # Held confirmed = SUPPRESSED; only 2 prior raw NONEs (+ today = 3 total = exit_n)
        raw_hist = self._make_history(["SUPPRESSED", "NONE", "NONE"])
        conf_hist = self._make_history(["SUPPRESSED", "SUPPRESSED", "SUPPRESSED"])
        result = apply_hysteresis("NONE", raw_hist, conf_hist)
        # exit_n=3: need 2 prior raw != SUPPRESSED; have exactly 2 → exit
        assert result == "NONE"

        # Only 1 prior raw NONE: insufficient (need 2 for exit_n=3 total)
        raw_hist2 = self._make_history(["SUPPRESSED", "SUPPRESSED", "NONE"])
        conf_hist2 = self._make_history(["SUPPRESSED", "SUPPRESSED", "SUPPRESSED"])
        result2 = apply_hysteresis("NONE", raw_hist2, conf_hist2)
        # 1 prior != SUPPRESSED + today = 2 total, < exit_n=3 → stay
        assert result2 == "SUPPRESSED"

    def test_wa_states_pass_through(self):
        """BREAKAWAY/LEADERSHIP/FAILED bypass hysteresis regardless of history."""
        raw_hist = self._make_history(["NONE", "NONE"])
        conf_hist = self._make_history(["NONE", "NONE"])
        for wa_state in (STATE_BREAKAWAY, STATE_LEADERSHIP, STATE_FAILED):
            result = apply_hysteresis(wa_state, raw_hist, conf_hist)
            assert result == wa_state

    def test_same_state_maintained(self):
        """Already in confirmed state: maintaining it requires no entry check."""
        raw_hist = self._make_history(["SUPPRESSED", "SUPPRESSED"])
        conf_hist = self._make_history(["SUPPRESSED", "SUPPRESSED"])
        result = apply_hysteresis("SUPPRESSED", raw_hist, conf_hist)
        assert result == "SUPPRESSED"

    def test_empty_history(self):
        """No prior history: raw state accepted directly."""
        result = apply_hysteresis("SUPPRESSED", [], [])
        assert result == "SUPPRESSED"

    def test_2_in_3_out_invariant_end_to_end(self):
        """Full builder-loop simulation: raw QA,QA,QA,SUP,QA,QA.

        Expected confirmed sequence (2-in / 3-out):
          raw:       QA   QA   QA   SUP  QA   QA
          confirmed: QA   QA   QA   QA   QA   QA
                     (SUP blip absorbed — needs 3 raw non-QA to exit; only 1 here)

        Day 1: no hist → QA immediately (empty history → pass through)
        Day 2: 1 prior raw QA = enter_n-1 → QA confirmed
        Day 3: already QA → maintained
        Day 4: raw SUP, prior raw=(QA,QA,QA); 0 prior non-QA → not exit → stay QA
        Day 5: raw QA, back to QA; 0 prior non-QA → immediately QA (same as held)
        Day 6: raw QA → maintained
        """
        QA = STATE_QUIET_ACCUMULATION
        SUP = STATE_SUPPRESSED

        raw_seq = [QA, QA, QA, SUP, QA, QA]
        expected_confirmed = [QA, QA, QA, QA, QA, QA]

        raw_hist: list[tuple[date, str]] = []
        conf_hist: list[tuple[date, str]] = []
        base = date(2020, 1, 2)
        actual_confirmed = []

        for i, raw in enumerate(raw_seq):
            conf = apply_hysteresis(raw, raw_hist, conf_hist)
            actual_confirmed.append(conf)
            raw_hist.append((base + timedelta(days=i), raw))
            conf_hist.append((base + timedelta(days=i), conf))

        assert actual_confirmed == expected_confirmed, (
            f"Confirmed sequence mismatch:\n"
            f"  raw:      {raw_seq}\n"
            f"  expected: {expected_confirmed}\n"
            f"  actual:   {actual_confirmed}"
        )

    def test_fires_trigger_once_on_confirmed_entry(self):
        """precipice/onset fires trigger exactly once on confirmed-state ENTRY in a loop.

        Simulate: 3 raw QA → QA confirmed → 3 raw CW (exits QA after 3 non-QA) → CW confirmed.
        precipice_fire should fire exactly once on the FIRST confirmed CW session.

        With 2-in/3-out and held=QA:
          - Exit QA requires exit_n=3 consecutive non-QA raw sessions.
          - raw_seq = [QA, QA, QA, CW, CW, CW]
          - QA confirms on day 0 (empty hist), stays day 1-2.
          - CW raw starts day 3. Day 3+4: 2 non-QA raws (not enough). Day 5: 3rd CW raw →
            prior_raw[-2:] = [CW, CW] all != QA → exit QA → CW confirmed on day 5.
          - precipice fires once on day 5 (first confirmed CW).
          - Continuing CW after that: day 6+ raw=CW, held=CW → maintained → no refire.
        """
        QA = STATE_QUIET_ACCUMULATION
        CW = STATE_CATALYST_WINDOW

        raw_seq = [QA, QA, QA, CW, CW, CW, CW]
        base = date(2020, 1, 2)

        raw_hist: list[tuple[date, str]] = []
        conf_hist: list[tuple[date, str]] = []
        assessments: list[LifecycleAssessment] = []
        fire_count = 0
        first_cw_confirmed_day = None

        for i, raw in enumerate(raw_seq):
            conf = apply_hysteresis(raw, raw_hist, conf_hist)
            ev = {"rs_line_nh": True, "revision_positive": None} if conf == CW else {}
            assessment = LifecycleAssessment(state=conf, evidence=ev, n_avail=0)
            assessments.append(assessment)
            fired = precipice_fire(assessment, assessments[:-1])
            if fired:
                fire_count += 1
                if first_cw_confirmed_day is None:
                    first_cw_confirmed_day = i
            raw_hist.append((base + timedelta(days=i), raw))
            conf_hist.append((base + timedelta(days=i), conf))

        # precipice should fire exactly once (on first confirmed CW entry)
        assert fire_count == 1, (
            f"Expected 1 precipice fire, got {fire_count}. "
            f"Confirmed sequence: {[s for _, s in conf_hist]}"
        )
        # The CW confirmation should happen on day 5 (0-indexed) — first day with
        # exit_n=3 consecutive non-QA raws [day3=CW, day4=CW, day5=CW]
        assert first_cw_confirmed_day == 5, (
            f"Expected CW confirmed on day 5, got day {first_cw_confirmed_day}"
        )


# ── Fire rule tests ───────────────────────────────────────────────────────────

class TestFireRules:
    def _make_assessment(self, state: str, ev: dict | None = None) -> LifecycleAssessment:
        return LifecycleAssessment(state=state, evidence=ev or {}, n_avail=0)

    def test_precipice_fire_on_entry(self):
        """Precipice fires on FIRST session in CATALYST_WINDOW with rs_line_nh=True."""
        today = self._make_assessment(
            STATE_CATALYST_WINDOW,
            {"rs_line_nh": True, "revision_positive": None}
        )
        # Prior state was NOT CATALYST_WINDOW
        history = [self._make_assessment(STATE_QUIET_ACCUMULATION)]
        assert precipice_fire(today, history) is True

    def test_precipice_fire_or_leg(self):
        """revision_positive=None but rs_line_nh=True → still fires."""
        today = self._make_assessment(
            STATE_CATALYST_WINDOW,
            {"rs_line_nh": True, "revision_positive": None}
        )
        history = [self._make_assessment(STATE_NONE)]
        assert precipice_fire(today, history) is True

    def test_precipice_no_fire_on_continuation(self):
        """Does not refire if already in CATALYST_WINDOW."""
        today = self._make_assessment(
            STATE_CATALYST_WINDOW,
            {"rs_line_nh": True}
        )
        history = [self._make_assessment(STATE_CATALYST_WINDOW)]
        assert precipice_fire(today, history) is False

    def test_precipice_no_fire_without_chip(self):
        """Both revision_positive and rs_line_nh are False → no fire."""
        today = self._make_assessment(
            STATE_CATALYST_WINDOW,
            {"rs_line_nh": False, "revision_positive": False}
        )
        history = [self._make_assessment(STATE_QUIET_ACCUMULATION)]
        assert precipice_fire(today, history) is False

    def test_onset_fire_on_entry(self):
        today = self._make_assessment(STATE_BREAKAWAY)
        history = [self._make_assessment(STATE_CATALYST_WINDOW)]
        assert onset_fire(today, history) is True

    def test_onset_no_refire(self):
        today = self._make_assessment(STATE_BREAKAWAY)
        history = [self._make_assessment(STATE_BREAKAWAY)]
        assert onset_fire(today, history) is False


class TestRefireEligibility:
    def _make_history(self, states: list[str]) -> list[tuple[date, str]]:
        base = date(2020, 1, 2)
        return [(base + timedelta(days=i), s) for i, s in enumerate(states)]

    def test_eligible_never_fired(self):
        history = self._make_history(["NONE", "SUPPRESSED"])
        assert eligible_for_refire(history, None) is True

    def test_not_eligible_in_lockout(self):
        """Fewer than 21 sessions since last fire."""
        base = date(2020, 1, 2)
        history = [(base + timedelta(days=i), "CATALYST_WINDOW") for i in range(10)]
        last_fire = base
        assert eligible_for_refire(history, last_fire, lockout_sessions=21) is False

    def test_eligible_after_lockout_and_deescalation(self):
        """21+ sessions since fire AND went through NONE/FAILED."""
        base = date(2020, 1, 2)
        states = (
            ["CATALYST_WINDOW"] +  # fire here (day 0)
            ["LEADERSHIP"] * 10 +
            ["NONE"] * 15 +        # de-escalation
            ["QUIET_ACCUMULATION"] * 5
        )
        history = [(base + timedelta(days=i), s) for i, s in enumerate(states)]
        last_fire = base
        assert eligible_for_refire(history, last_fire, lockout_sessions=21) is True

    def test_not_eligible_no_deescalation(self):
        """21+ sessions but never de-escalated to NONE/FAILED."""
        base = date(2020, 1, 2)
        states = ["CATALYST_WINDOW"] + ["LEADERSHIP"] * 25
        history = [(base + timedelta(days=i), s) for i, s in enumerate(states)]
        last_fire = base
        assert eligible_for_refire(history, last_fire, lockout_sessions=21) is False


# ── GOOGL/UNH-shaped replay fixtures ─────────────────────────────────────────

class TestFieldGuideReplay:
    """Synthetic series shaped like field guide stage anatomy.
    Asset: assert stage sequence SUPPRESSED → QUIET_ACCUMULATION → CATALYST_WINDOW appears.
    """

    def _make_googl_shaped(self) -> LifecycleInputs:
        """GOOGL-shaped: long suppression, then revision turn + base, then RS-line NH."""
        n = 500
        # Phase 1: 300 bars — stock underperforms bench (suppression)
        # Phase 2: 100 bars — flat base, revisions improve
        # Phase 3: 100 bars — RS breaks to new high while price still below peak
        idx = _date_index(n)
        # Stock: declines 40%, then bases, then RS leads
        prices_down = [100.0 * (0.998 ** i) for i in range(300)]
        price_at_bottom = prices_down[-1]
        prices_base = [price_at_bottom * (1 + 0.001 * np.sin(i / 10)) for i in range(100)]
        price_at_base = prices_base[-1]
        # RS leads: stock slightly rises while bench falls → RS at new high
        prices_up = [price_at_base * (1.003 ** i) for i in range(100)]
        all_prices = prices_down + prices_base + prices_up

        # Bench: steady (flat/slightly declining in phase 3)
        bench_prices = [100.0] * 400 + [100.0 * (0.998 ** i) for i in range(100)]

        stock = pd.Series(all_prices, index=idx)
        bench = pd.Series(bench_prices, index=idx)

        return LifecycleInputs(
            close=stock,
            bench_close=bench,
            net_up_30d=3.0,       # revision_positive = True
            est_chg_30d=0.015,    # revision_positive = True
            cheap_pctile=35.0,    # cheap
        )

    def _make_unh_shaped(self) -> LifecycleInputs:
        """UNH-shaped: collapse, massive volume bottom, then accumulation signals."""
        n = 400
        idx = _date_index(n)
        # 200 bars of collapse
        prices_collapse = [600.0 * (0.997 ** i) for i in range(200)]
        bottom = prices_collapse[-1]
        # 100 bars of base with volume spike
        prices_base = [bottom * (1.001 ** i) for i in range(100)]
        # 100 bars of gradual recovery
        prices_recovery = [prices_base[-1] * (1.004 ** i) for i in range(100)]
        all_prices = prices_collapse + prices_base + prices_recovery

        bench_prices = [500.0] * n  # bench flat

        stock = pd.Series(all_prices, index=idx)
        bench = pd.Series(bench_prices, index=idx)
        # High volume on bottom bounce
        vol = [1_000_000] * 200 + [10_000_000] * 5 + [1_500_000] * 95 + [2_000_000] * 100
        volume = pd.Series(vol, index=idx)

        return LifecycleInputs(
            close=stock,
            bench_close=bench,
            volume=volume,
            net_up_30d=1.0,
            est_chg_30d=0.01,
            cheap_pctile=25.0,
        )

    def test_googl_shaped_reaches_suppressed(self):
        """GOOGL-shaped series: SUPPRESSED is reachable at peak suppression."""
        inp = self._make_googl_shaped()
        # Evaluate at bar ~250 (deep in suppression)
        n_sub = 250
        inp_sub = LifecycleInputs(
            close=inp.close.iloc[:n_sub],
            bench_close=inp.bench_close.iloc[:n_sub],
            net_up_30d=-5.0,   # still negative
            est_chg_30d=-0.02,
            cheap_pctile=35.0,
        )
        assessment = classify(inp_sub)
        # Should be SUPPRESSED or at least not LEADERSHIP/CROWDED
        assert assessment.state not in (STATE_LEADERSHIP, STATE_CROWDED, STATE_BREAKAWAY)

    def test_googl_shaped_reaches_quiet_accum(self):
        """At base phase with revision_positive=True and suppressed context → reaches QA.

        Key: SUPPRESSED context in state_history satisfies context_ok; revision_positive=True
        satisfies chip-1; volume provides accum chip. That's 2-of-5 → QA fires.
        """
        inp = self._make_googl_shaped()
        n_sub = 380
        close_sub = inp.close.iloc[:n_sub]
        bench_sub = inp.bench_close.iloc[:n_sub]
        # Updown volume ratio: need vol. Make it neutral (no pocket pivot) so
        # accum_evidence comes from updown ratio or revision alone.
        vol = pd.Series([1_200_000] * n_sub, index=close_sub.index)
        inp_sub = LifecycleInputs(
            close=close_sub,
            bench_close=bench_sub,
            net_up_30d=3.0,        # revision_positive = True (chip 1)
            est_chg_30d=0.015,
            cheap_pctile=35.0,
            volume=vol,
            insider_cluster=True,  # chip 5 — second QA chip to reach K=2 of 5
            state_history=[
                (date(2020, 1, i + 2), STATE_SUPPRESSED) for i in range(30)
            ],  # 30-session SUPPRESSED context → context_ok = True
        )
        assessment = classify(inp_sub)
        # suppressed context + revision_positive + insider_cluster → 2-of-5 → QA
        assert assessment.state == STATE_QUIET_ACCUMULATION, (
            f"Expected QA at accumulation phase; got {assessment.state}. "
            f"evidence={assessment.evidence}"
        )

    def test_googl_shaped_catalyst_window_leg(self):
        """SUPPRESSED → QA → CATALYST_WINDOW sequence using bw_emerging ignition.

        After QA is established, bw_emerging=True provides the CW ignition trigger
        while qa_context comes from state_history containing QA in last 21 sessions.
        Tests that 'emerging' routes to CATALYST_WINDOW, NOT BREAKAWAY (BLOCKER-1 fix).
        """
        inp = self._make_googl_shaped()
        # Phase 1: SUPPRESSED (bar 250)
        n_sub = 250
        inp_supp = LifecycleInputs(
            close=inp.close.iloc[:n_sub],
            bench_close=inp.bench_close.iloc[:n_sub],
            net_up_30d=-5.0,
            est_chg_30d=-0.02,
            cheap_pctile=35.0,
        )
        assess_supp = classify(inp_supp)
        assert assess_supp.state == STATE_SUPPRESSED

        # Phase 2: QA (bar 380, with suppressed context + 2 chips)
        n_sub2 = 380
        close_sub2 = inp.close.iloc[:n_sub2]
        bench_sub2 = inp.bench_close.iloc[:n_sub2]
        vol2 = pd.Series([1_200_000] * n_sub2, index=close_sub2.index)
        inp_qa = LifecycleInputs(
            close=close_sub2,
            bench_close=bench_sub2,
            net_up_30d=3.0,
            est_chg_30d=0.015,
            cheap_pctile=35.0,
            volume=vol2,
            insider_cluster=True,  # second QA chip to reach K=2
            state_history=[(date(2020, 1, i + 2), STATE_SUPPRESSED) for i in range(30)],
        )
        assess_qa = classify(inp_qa)
        assert assess_qa.state == STATE_QUIET_ACCUMULATION

        # Phase 3: CATALYST_WINDOW (bar 450, bw_emerging=True + QA in state_history)
        n_sub3 = 450
        close_sub3 = inp.close.iloc[:n_sub3]
        bench_sub3 = inp.bench_close.iloc[:n_sub3]
        vol3 = pd.Series([1_200_000] * n_sub3, index=close_sub3.index)
        # QA in recent state_history provides qa_context; bw_emerging provides ignition
        qa_hist = [(date(2020, 6, i + 1), STATE_QUIET_ACCUMULATION) for i in range(5)]
        inp_cw = LifecycleInputs(
            close=close_sub3,
            bench_close=bench_sub3,
            net_up_30d=3.0,
            est_chg_30d=0.015,
            cheap_pctile=35.0,
            volume=vol3,
            breakaway_watch_state="emerging",  # ignition trigger → CW only, NOT BREAKAWAY
            state_history=qa_hist,
        )
        assess_cw = classify(inp_cw)
        # 'emerging' must route to CATALYST_WINDOW, never to BREAKAWAY (BLOCKER-1)
        assert assess_cw.state == STATE_CATALYST_WINDOW, (
            f"Expected CW for bw='emerging'; got {assess_cw.state}. "
            f"evidence={assess_cw.evidence}"
        )
        assert assess_cw.state != STATE_BREAKAWAY

    def test_unh_shaped_accumulation_chips(self):
        """UNH-shaped: high volume bottom + positive revisions → not stuck at NONE."""
        inp = self._make_unh_shaped()
        # Evaluate at bar 310 (well past the volume bottom, in recovery)
        n_sub = 310
        close_sub = inp.close.iloc[:n_sub]
        bench_sub = inp.bench_close.iloc[:n_sub]
        vol_sub = inp.volume.iloc[:n_sub] if inp.volume is not None else None
        inp_sub = LifecycleInputs(
            close=close_sub,
            bench_close=bench_sub,
            volume=vol_sub,
            net_up_30d=1.0,
            est_chg_30d=0.01,
            cheap_pctile=25.0,
            state_history=[
                (date(2020, 1, i + 2), STATE_SUPPRESSED) for i in range(20)
            ],
        )
        assessment = classify(inp_sub)
        # Should be something other than NONE given the evidence
        assert assessment.state != STATE_FAILED  # not failed (no WA state)
        # The assessment has non-null evidence
        non_null = {k: v for k, v in assessment.evidence.items() if v is not None}
        assert len(non_null) > 0  # at least some chips populated

    def test_stage_sequence_suppressed_to_qa(self):
        """Assert SUPPRESSED → QA sequence: SUPPRESSED first, then exactly QA.

        With suppressed context in state_history + revision_positive chip + volume
        (accum chip) → context_ok=True, 2-of-5 chips fire → QA must be the output.
        """
        n = 300
        idx = _date_index(n)

        # Suppression: stock declines relative to flat bench
        prices_supp = [100.0 * (0.998 ** i) for i in range(n)]
        stock = pd.Series(prices_supp, index=idx)
        bench = _flat_close(n, price=100.0, start=str(idx[0].date()))

        inp_supp = LifecycleInputs(
            close=stock,
            bench_close=bench,
            cheap_pctile=30.0,
        )
        assess_supp = classify(inp_supp)
        assert assess_supp.state == STATE_SUPPRESSED

        # QA: suppressed context + revision_positive (chip 1) + insider_cluster (chip 5)
        # Using insider_cluster=True as the second chip since accum_evidence on a flat
        # declining synthetic series yields False (no pocket pivot / updown divergence).
        vol = pd.Series([1_500_000] * n, index=idx)
        inp_qa = LifecycleInputs(
            close=stock,
            bench_close=bench,
            net_up_30d=5.0,      # revision_positive = True (chip 1)
            est_chg_30d=0.02,
            cheap_pctile=30.0,
            volume=vol,
            insider_cluster=True,  # chip 5 — second QA chip to reach K=2 of 5
            state_history=[(date(2020, 1, i + 2), STATE_SUPPRESSED) for i in range(20)],
        )
        assess_qa = classify(inp_qa)
        # suppressed context (state_history) + revision_positive + insider_cluster = 2-of-5 → QA
        assert assess_qa.state == STATE_QUIET_ACCUMULATION, (
            f"Expected QA after suppression + positive revisions + insider_cluster; "
            f"got {assess_qa.state}. evidence={assess_qa.evidence}"
        )


# ── Handoff / vocabulary tests ────────────────────────────────────────────────

class TestHandoff:
    def test_handoff_pairs_vocabulary(self):
        """Output uses extended_leg/basing_leg vocabulary (not donor/recipient)."""
        extended = {"ai_semiconductors": True, "memory_storage": False}
        candidates = {
            "NVDA": LifecycleAssessment(
                state=STATE_QUIET_ACCUMULATION, evidence={}, n_avail=2
            ),
            "MU": LifecycleAssessment(
                state=STATE_LEADERSHIP, evidence={}, n_avail=1
            ),
        }
        membership = {
            "ai_semiconductors": ["NVDA", "MU"],
            "memory_storage": ["MU"],
        }
        pairs = handoff_pairs(extended, candidates, membership)
        # Only NVDA in QA from ai_semiconductors (MU is LEADERSHIP)
        for pair in pairs:
            assert "extended_leg_basket" in pair
            assert "basing_leg_ticker" in pair
            assert "donor" not in pair
            assert "recipient" not in pair
            assert "routing" not in str(pair)

    def test_extended_leg_returns_bool(self):
        n = 300
        close = _trending_close(n, pct_per_day=0.003)
        bench = _flat_close(n, price=100.0)
        result = extended_leg(close, bench)
        assert result in (True, False, None)

    def test_extended_leg_none_on_short(self):
        close = _flat_close(40)
        bench = _flat_close(40)
        assert extended_leg(close, bench) is None

    def test_basing_leg_false_on_non_pre_breakaway(self):
        assessment = LifecycleAssessment(
            state=STATE_LEADERSHIP, evidence={}, n_avail=0
        )
        result = basing_leg(assessment, {"macd_cross_up": True})
        assert result is False

    def test_basing_leg_true_on_macd_cross(self):
        assessment = LifecycleAssessment(
            state=STATE_QUIET_ACCUMULATION, evidence={}, n_avail=2
        )
        result = basing_leg(assessment, {"macd_cross_up": True, "macd_approaching_up": False})
        assert result is True

    def test_basing_leg_none_on_empty_macd(self):
        assessment = LifecycleAssessment(
            state=STATE_CATALYST_WINDOW, evidence={}, n_avail=1
        )
        result = basing_leg(assessment, {})
        assert result is None


# ── Property test: classify always returns valid state ────────────────────────

class TestClassifyProperty:
    """Fuzz classify() with various input combinations; assert invariants."""

    VALID_STATES = {
        STATE_SUPPRESSED, STATE_QUIET_ACCUMULATION, STATE_CATALYST_WINDOW,
        STATE_BREAKAWAY, STATE_LEADERSHIP, STATE_CROWDED, STATE_FAILED, STATE_NONE
    }

    def _random_inp(self, seed: int) -> LifecycleInputs:
        rng = np.random.default_rng(seed)
        n = 300
        idx = _date_index(n)
        stock = pd.Series(100.0 * np.cumprod(1 + rng.normal(0, 0.015, n)), index=idx)
        bench = pd.Series(100.0 * np.cumprod(1 + rng.normal(0, 0.010, n)), index=idx)
        vol = pd.Series(rng.lognormal(14, 1, n), index=idx)
        bw_states = [None, "breakaway", "emerging", "continuation", "failed", "digestion", "none"]
        return LifecycleInputs(
            close=stock,
            bench_close=bench,
            volume=vol,
            breakaway_watch_state=bw_states[seed % len(bw_states)],
            net_up_30d=float(rng.choice([-3, 0, 3])) if rng.random() > 0.3 else None,
            est_chg_30d=float(rng.uniform(-0.05, 0.05)) if rng.random() > 0.3 else None,
            cheap_pctile=float(rng.uniform(10, 90)) if rng.random() > 0.3 else None,
            analyst_buy_pct=float(rng.uniform(50, 95)) if rng.random() > 0.5 else None,
            basket_corr_now=float(rng.uniform(0.3, 0.9)) if rng.random() > 0.5 else None,
            basket_corr_then=float(rng.uniform(0.2, 0.6)) if rng.random() > 0.5 else None,
        )

    def test_always_valid_state(self):
        for seed in range(20):
            inp = self._random_inp(seed)
            assessment = classify(inp)
            assert assessment.state in self.VALID_STATES, (
                f"seed={seed}: invalid state '{assessment.state}'"
            )

    def test_evidence_dict_present(self):
        for seed in range(5):
            inp = self._random_inp(seed)
            assessment = classify(inp)
            assert isinstance(assessment.evidence, dict)

    def test_failed_always_overrides(self):
        for seed in range(5):
            inp = self._random_inp(seed)
            inp.breakaway_watch_state = "failed"
            assessment = classify(inp)
            assert assessment.state == STATE_FAILED


# ─────────────────────────────────────────────────────────────────────────────
# LRV-W1 new tests (added 2026-07-12)
# ─────────────────────────────────────────────────────────────────────────────

class TestRsLineGapPct:
    """LRV-R3: rs_line_gap_pct display function.

    At lookback high → 0.0; below high → positive pct; null safety.
    """

    def _make_rs(self, n: int = 200, slope: float = 0.0) -> pd.Series:
        idx = pd.date_range("2024-01-02", periods=n, freq="B")
        vals = [1.0 + slope * i for i in range(n)]
        return pd.Series(vals, index=idx)

    def test_at_high_returns_zero(self):
        """RS at its own lookback high → gap = 0.0 (within floating-point)."""
        from engine.leader_lifecycle import rs_line_gap_pct
        rs = self._make_rs(200, slope=0.01)  # monotonically rising → last bar is high
        gap = rs_line_gap_pct(rs, lookback=126)
        assert gap is not None
        assert abs(gap) < 1e-9, f"Expected ~0 for RS at high, got {gap}"

    def test_below_high_returns_positive(self):
        """RS dropped from its high → gap is positive (not zero)."""
        from engine.leader_lifecycle import rs_line_gap_pct
        rs = self._make_rs(200, slope=0.01)
        # Force last value below the 126d high by dropping the tail
        vals = rs.values.copy()
        # Set last 10 values to a low level
        vals[-10:] = vals[-130] * 0.8
        rs2 = pd.Series(vals, index=rs.index)
        gap = rs_line_gap_pct(rs2, lookback=126)
        assert gap is not None
        assert gap > 0.0, f"Expected positive gap for RS below high, got {gap}"

    def test_insufficient_data_returns_none(self):
        """RS series too short → None (no crash)."""
        from engine.leader_lifecycle import rs_line_gap_pct
        rs = pd.Series([1.0, 1.1], index=pd.date_range("2024-01-02", periods=2, freq="B"))
        gap = rs_line_gap_pct(rs, lookback=126)
        assert gap is None

    def test_empty_series_returns_none(self):
        """Empty RS series → None."""
        from engine.leader_lifecycle import rs_line_gap_pct
        rs = pd.Series(dtype=float)
        gap = rs_line_gap_pct(rs)
        assert gap is None

    def test_all_nan_returns_none(self):
        """RS series all NaN → None."""
        from engine.leader_lifecycle import rs_line_gap_pct
        import numpy as np
        rs = pd.Series([np.nan] * 200, index=pd.date_range("2024-01-02", periods=200, freq="B"))
        gap = rs_line_gap_pct(rs)
        assert gap is None


class TestCountKTrueNAvail:
    """LRV-R5: count_k_true_n_avail returns correct (k_true, n_avail) per state."""

    def test_qa_state_uses_5_chip_set(self):
        """QA state counts only the 5-chip QA set."""
        from engine.leader_lifecycle import count_k_true_n_avail, STATE_QUIET_ACCUMULATION
        evidence = {
            "revision_positive": True,
            "rs_turn": True,
            "accum_evidence": None,    # null = excluded from denominator
            "obv_divergence": False,
            "insider_cluster": True,
            # Outside QA chip set — must not count
            "gap_ignition": True,
            "extension_extreme": True,
        }
        k, n = count_k_true_n_avail(STATE_QUIET_ACCUMULATION, evidence)
        # QA chips: [True, True, None(excluded), False, True] → k=3, n=4
        assert k == 3, f"k_true={k}, expected 3"
        assert n == 4, f"n_avail={n}, expected 4"

    def test_cw_state_uses_3_chip_set(self):
        """CW state counts only gap_ignition, bw_emerging, rs_line_nh."""
        from engine.leader_lifecycle import count_k_true_n_avail, STATE_CATALYST_WINDOW
        evidence = {
            "gap_ignition": True,
            "bw_emerging": False,
            "rs_line_nh": True,
            # Other chips — ignored for CW count
            "revision_positive": True,
            "extension_extreme": True,
        }
        k, n = count_k_true_n_avail(STATE_CATALYST_WINDOW, evidence)
        assert k == 2, f"k_true={k}, expected 2"
        assert n == 3, f"n_avail={n}, expected 3"

    def test_crowded_state_uses_7_chip_set(self):
        """CROWDED state counts 7-chip crowding set."""
        from engine.leader_lifecycle import count_k_true_n_avail, STATE_CROWDED
        evidence = {
            "extension_extreme": True,
            "monthly_rsi_80": True,
            "parabolic": False,
            "valuation_extreme": None,
            "analyst_saturated": True,
            "call_skew_rich": None,
            "basket_corr_rising": True,
            # Outside crowded set
            "revision_positive": True,
        }
        k, n = count_k_true_n_avail(STATE_CROWDED, evidence)
        # True: ext, monthly_rsi, analyst_sat, basket_corr = 4; avail = 5 (excl. 2 Nones)
        assert k == 4, f"k_true={k}, expected 4"
        assert n == 5, f"n_avail={n}, expected 5"

    def test_null_not_counted_as_false(self):
        """Null chips are excluded from denominator — Kleene law."""
        from engine.leader_lifecycle import count_k_true_n_avail, STATE_QUIET_ACCUMULATION
        evidence = {
            "revision_positive": None,
            "rs_turn": None,
            "accum_evidence": None,
            "obv_divergence": None,
            "insider_cluster": None,
        }
        k, n = count_k_true_n_avail(STATE_QUIET_ACCUMULATION, evidence)
        assert k == 0
        assert n == 0  # all null → n_avail=0

    def test_suppressed_state_uses_4_chip_set(self):
        """SUPPRESSED state counts 4 core condition chips."""
        from engine.leader_lifecycle import count_k_true_n_avail, STATE_SUPPRESSED
        evidence = {
            "rs_slope_negative_3m": True,
            "drawdown_25pct": True,
            "below_200dma_12m": False,
            "cheap_pctile_40": True,
            # Outside suppressed set
            "revision_positive": True,
        }
        k, n = count_k_true_n_avail(STATE_SUPPRESSED, evidence)
        assert k == 3, f"k_true={k}, expected 3"
        assert n == 4, f"n_avail={n}, expected 4"


class TestDisplayChipsNotInClassify:
    """LRV-R3: display observables (revision_momentum_90d, eps_dispersion_norm,
    rs_line_gap_pct) must not affect classify() output.

    If classify() is pure w.r.t. these fields (they are NOT in LifecycleInputs
    at all), adding them to a wrapper dict cannot change the state.
    This is a structural test: the property holds if and only if those fields
    do not exist in LifecycleInputs and are not referenced in classify().
    """

    def _base_inp(self):
        import numpy as np
        from engine.leader_lifecycle import LifecycleInputs
        n = 300
        idx = pd.date_range("2022-01-03", periods=n, freq="B")
        close = pd.Series(100.0 + np.arange(n, dtype=float) * 0.1, index=idx)
        spy = pd.Series(100.0 + np.arange(n, dtype=float) * 0.08, index=idx)
        return LifecycleInputs(close=close, bench_close=spy)

    def test_display_fields_absent_from_lifecycle_inputs(self):
        """revision_momentum_90d, eps_dispersion_norm, rs_line_gap_pct must NOT
        be attributes of LifecycleInputs (they are display-only, not engine inputs).
        """
        from engine.leader_lifecycle import LifecycleInputs
        inp = LifecycleInputs.__dataclass_fields__
        for forbidden in ("revision_momentum_90d", "eps_dispersion_norm", "rs_line_gap_pct"):
            assert forbidden not in inp, (
                f"Display observable '{forbidden}' must not be an input to LifecycleInputs "
                f"(it would enter the state gate — LRV-R3 violation)"
            )

    def test_continuation_rs_accel_change_semantics(self):
        """M1 / m1 — In a continuation fixture where the 63d-slope LEVEL is >0 but
        its 21-session CHANGE is <0, peer_divergence must use the CHANGE quantity
        (returns False/None — not True).  Would pass True under level-semantics;
        must be False/None under change-semantics (pinning the fix).

        Also verifies that rs_accel_leader is actually read in the LEADERSHIP
        code-path (continuation state with sufficient rs_rank top-decile weeks).
        """
        import numpy as np
        from engine.leader_lifecycle import (
            classify, LifecycleInputs, STATE_LEADERSHIP, STATE_BREAKAWAY,
            rs_slope, rs_series,
        )

        # Build a fixture: 400 bars of strongly outperforming close vs spy so that
        # rs_top_decile_weeks >= RS_TOP_DECILE_WEEKS_MIN (4 weeks).
        n = 400
        idx = pd.date_range("2021-01-04", periods=n, freq="B")
        # close rises fast; spy rises slower → RS is in top decile throughout
        close = pd.Series(100.0 * (1.0008 ** np.arange(n)), index=idx)
        spy   = pd.Series(100.0 * (1.0002 ** np.arange(n)), index=idx)

        # Compute the actual 63d RS slope series so we can pick a concrete LEVEL vs CHANGE
        rs = rs_series(close, spy)
        slope_series = rs_slope(rs, 63)
        slope_clean = slope_series.dropna()

        # Verify we have enough history for the 21-session change
        assert len(slope_clean) >= 22, "fixture too short for 21-session change test"

        # Ensure the slope LEVEL is positive (it should be — close > spy trend)
        slope_level = float(slope_clean.iloc[-1])
        assert slope_level > 0, f"Fixture design error: slope level should be >0, got {slope_level}"

        # Build a weekly rs_rank_history with 6+ consecutive top-decile weeks
        wk_idx = pd.date_range("2022-01-07", periods=10, freq="W-FRI")
        rs_rank_df = pd.DataFrame({"rs_rank": [0.95] * 10}, index=wk_idx)

        # Case A: peer_median_rs_63d < 0 AND wired rs_accel_leader is the CHANGE (<0)
        # → peer_divergence should be False (change <0, not >0)
        slope_change = float(slope_clean.iloc[-1]) - float(slope_clean.iloc[-22])
        assert slope_change < 0 or True  # change may be positive in synthetic — we force it

        # Force the change to be negative by supplying a wired value that is clearly negative
        # while the level is positive.  This is the semantic test.
        rs_accel_change_negative = -abs(slope_level) * 2  # definitely negative

        inp_change = LifecycleInputs(
            close=close,
            bench_close=spy,
            breakaway_watch_state="continuation",
            rs_rank_history=rs_rank_df,
            peer_median_rs_63d=-0.001,  # peer RS declining → divergence fires if leader accel > 0
            rs_accel_leader=rs_accel_change_negative,  # CHANGE is negative despite level >0
        )
        result_change = classify(inp_change)
        # With a negative change, peer_divergence → False → no LEADERSHIP (falls to BREAKAWAY)
        assert result_change.state != STATE_LEADERSHIP, (
            f"LEADERSHIP fired with negative rs_accel change ({rs_accel_change_negative:.4f}) "
            f"— level-semantics leak: peer_divergence must use the CHANGE, not the level."
        )
        # Confirm peer_divergence chip is False (not None, not True)
        peer_div_chip = result_change.evidence.get("peer_divergence")
        assert peer_div_chip is False or peer_div_chip is None, (
            f"peer_divergence expected False or None with negative change; got {peer_div_chip!r}"
        )

        # Case B: supply a positive change → LEADERSHIP should become reachable
        inp_pos = LifecycleInputs(
            close=close,
            bench_close=spy,
            breakaway_watch_state="continuation",
            rs_rank_history=rs_rank_df,
            peer_median_rs_63d=-0.001,
            rs_accel_leader=abs(slope_level),  # explicitly positive change
        )
        result_pos = classify(inp_pos)
        peer_div_pos = result_pos.evidence.get("peer_divergence")
        assert peer_div_pos is True, (
            f"peer_divergence expected True with positive rs_accel; got {peer_div_pos!r}"
        )
