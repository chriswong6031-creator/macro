"""tests/test_rank_momentum_signals.py — Tests for engine/rank_momentum_signals.py.

Fixtures: monotonic-up, monotonic-down, flat, zero-range, gap, reversal tapes.

Per-signal assertions:
  (a) formula correctness on hand-computable cases
  (b) causality: signal.iloc[:k] == signal computed on df.iloc[:k], for multiple k
  (c) events are 0/1 integers and fire on expected bars
  (d) no NaN in output

MM_DATA_GUARD: tests NEVER read or write data/ or site/ — all fixtures are
synthetic in-memory DataFrames.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine.rank_momentum_signals import (
    SIGNALS,
    _connors_rsi,
    _percent_rank,
    _rsi_safe,
    _spearman_n,
    _streak,
    crsi_ob_exit,
    crsi_os_entry,
    crsi_os_exit,
    sprm_strong_dn,
    sprm_strong_up,
    sprm_zero_dn,
    sprm_zero_up,
)

# ---------------------------------------------------------------------------
# Fixture builders (all in-memory; no data/ or site/ access)
# ---------------------------------------------------------------------------

def _dates(n: int, start: str = "2020-01-02") -> pd.DatetimeIndex:
    return pd.date_range(start, periods=n, freq="B")


def _make_df(close_arr, high_arr=None, low_arr=None, start: str = "2020-01-02") -> pd.DataFrame:
    """Build a minimal OHLCV DataFrame (no 'open' column — spec has no open)."""
    close = np.asarray(close_arr, dtype=float)
    n = len(close)
    high = np.asarray(high_arr, dtype=float) if high_arr is not None else close * 1.005
    low = np.asarray(low_arr, dtype=float) if low_arr is not None else close * 0.995
    return pd.DataFrame(
        {"close": close, "high": high, "low": low, "volume": 1_000_000.0},
        index=_dates(n, start),
    )


def _monotonic_up(n: int = 300, start: float = 10.0, step: float = 0.5) -> pd.DataFrame:
    close = np.linspace(start, start + step * (n - 1), n)
    return _make_df(close)


def _monotonic_down(n: int = 300, start: float = 160.0, step: float = 0.5) -> pd.DataFrame:
    close = np.linspace(start, start - step * (n - 1), n)
    return _make_df(close)


def _flat(n: int = 300, price: float = 100.0) -> pd.DataFrame:
    return _make_df(np.full(n, price))


def _zero_range(n: int = 200) -> pd.DataFrame:
    """High == Low == Close on every bar."""
    close = np.linspace(50.0, 150.0, n)
    return pd.DataFrame(
        {"close": close, "high": close, "low": close, "volume": 1_000_000.0},
        index=_dates(n),
    )


def _gap_tape(n: int = 250, gap_idx: int = 120) -> pd.DataFrame:
    """Uptrend with a price gap at gap_idx (jump of 10%)."""
    close = np.linspace(100.0, 150.0, n)
    close[gap_idx:] *= 1.10
    return _make_df(close)


def _reversal_tape_down_then_up(n: int = 300) -> pd.DataFrame:
    """First half falls, second half rises — so Spearman crosses 0 going UP."""
    half = n // 2
    down = np.linspace(200.0, 80.0, half)
    up = np.linspace(80.0, 200.0, n - half)
    close = np.concatenate([down, up])
    return _make_df(close)


def _reversal_tape_up_then_down(n: int = 300) -> pd.DataFrame:
    """First half rises, second half falls — so Spearman crosses 0 going DOWN."""
    half = n // 2
    up = np.linspace(100.0, 200.0, half)
    down = np.linspace(200.0, 80.0, n - half)
    close = np.concatenate([up, down])
    return _make_df(close)


def _crsi_crossover_tape() -> pd.DataFrame:
    """Tape with a down phase then a recovery, so CRSI crosses both thresholds."""
    # 150 bar up, then 100 bar down sharp, then 150 bar recovery
    up1 = np.linspace(100.0, 200.0, 150)
    dn = np.linspace(200.0, 50.0, 100)
    up2 = np.linspace(50.0, 180.0, 150)
    close = np.concatenate([up1, dn, up2])
    return _make_df(close)


# ---------------------------------------------------------------------------
# Helper: assert no NaN in output
# ---------------------------------------------------------------------------

def _assert_no_nan(sig: pd.Series, name: str) -> None:
    assert not sig.isna().any(), f"{name} contains NaN values"


# ---------------------------------------------------------------------------
# Helper: causality check
# ---------------------------------------------------------------------------

def _causality_check(fn, df: pd.DataFrame, ks=(120, 180, 220), **kwargs) -> None:
    """signal.iloc[:k] must equal signal computed on df.iloc[:k]."""
    full = fn(df, **kwargs)
    for k in ks:
        if k > len(df):
            continue
        partial = fn(df.iloc[:k], **kwargs)
        pd.testing.assert_series_equal(
            full.iloc[:k].reset_index(drop=True),
            partial.reset_index(drop=True),
            check_names=False,
            obj=f"causality at k={k}",
        )


# ===========================================================================
# Tests for _rsi_safe
# ===========================================================================

class TestRsiSafe:
    def test_monotonic_up_returns_100(self):
        """On a monotonic-up tape, RSI(close) should be 100 (no down moves)."""
        close = pd.Series(np.linspace(10.0, 60.0, 50))
        rsi = _rsi_safe(close, n=3)
        # After warm-up (3 bars), monotonic up → RSI = 100
        assert np.allclose(rsi.dropna().values, 100.0)

    def test_monotonic_down_returns_0(self):
        """On a monotonic-down tape, RSI(close) should be 0 (no up moves)."""
        close = pd.Series(np.linspace(60.0, 10.0, 50))
        rsi = _rsi_safe(close, n=3)
        assert np.allclose(rsi.dropna().values, 0.0)

    def test_flat_tape_returns_50(self):
        """On a flat tape (no moves), RSI uses neutral 50 for the up==dn==0 case."""
        close = pd.Series(np.full(30, 100.0))
        rsi = _rsi_safe(close, n=3)
        assert np.allclose(rsi.dropna().values, 50.0)

    def test_range_0_100(self):
        """RSI output must be in [0, 100]."""
        close = pd.Series(np.random.default_rng(42).normal(100, 2, 100).cumsum() + 1000)
        rsi = _rsi_safe(close, n=14)
        valid = rsi.dropna()
        assert (valid >= 0.0).all() and (valid <= 100.0).all()


# ===========================================================================
# Tests for _streak
# ===========================================================================

class TestStreak:
    def test_up_streak(self):
        """Rising prices build a positive streak."""
        close = pd.Series([100.0, 101.0, 102.0, 103.0, 104.0])
        s = _streak(close)
        assert s.iloc[0] == 0.0
        assert s.iloc[1] == 1.0
        assert s.iloc[2] == 2.0
        assert s.iloc[3] == 3.0

    def test_down_streak(self):
        """Falling prices build a negative streak."""
        close = pd.Series([104.0, 103.0, 102.0, 101.0])
        s = _streak(close)
        assert s.iloc[0] == 0.0
        assert s.iloc[1] == -1.0
        assert s.iloc[2] == -2.0
        assert s.iloc[3] == -3.0

    def test_unchanged_resets(self):
        """An unchanged close resets the streak to 0."""
        close = pd.Series([100.0, 101.0, 101.0, 102.0])
        s = _streak(close)
        assert s.iloc[2] == 0.0   # unchanged
        assert s.iloc[3] == 1.0   # new up streak starts

    def test_direction_flip_resets(self):
        """Switching direction resets to +1 / -1, not continuing the old count."""
        close = pd.Series([100.0, 101.0, 102.0, 101.5])
        s = _streak(close)
        assert s.iloc[2] == 2.0
        assert s.iloc[3] == -1.0  # flip resets to -1

    def test_flat_tape(self):
        """All-flat tape — streak stays 0 after bar 0."""
        close = _flat()["close"]
        s = _streak(close)
        assert (s.iloc[1:] == 0.0).all()


# ===========================================================================
# Tests for _percent_rank
# ===========================================================================

class TestPercentRank:
    def test_hand_case_all_below(self):
        """PercentRank with n=5: today=10, window=[1,2,3,4,5] → all 5 strictly below → 100."""
        vals = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 10.0])
        pr = _percent_rank(vals, n=5)
        # at index 5: window=[1,2,3,4,5], all < 10 → 5/5*100 = 100
        assert pr.iloc[5] == pytest.approx(100.0)

    def test_none_below(self):
        """If today is the minimum, percent rank = 0."""
        vals = pd.Series([5.0, 6.0, 7.0, 8.0, 9.0, 1.0])
        pr = _percent_rank(vals, n=5)
        # window=[5,6,7,8,9], none < 1 → 0/5*100 = 0
        assert pr.iloc[5] == pytest.approx(0.0)

    def test_strictly_less_than(self):
        """Ties (equal values) are NOT counted — strictly less than."""
        vals = pd.Series([5.0, 5.0, 5.0, 5.0, 5.0, 5.0])
        pr = _percent_rank(vals, n=5)
        # window=[5,5,5,5,5], none strictly < 5 → 0
        assert pr.iloc[5] == pytest.approx(0.0)

    def test_warmup_nan(self):
        """Output is NaN for the first n bars (warm-up)."""
        vals = pd.Series(np.arange(20, dtype=float))
        pr = _percent_rank(vals, n=10)
        assert pr.iloc[:10].isna().all()
        assert pr.iloc[10:].notna().all()

    def test_monotonic_up_gives_zero(self):
        """Constant-step up: each today's ROC == prior ROCs (equal step) → none strictly below → 0."""
        # constant step => all ROCs identical => prank = 0
        close = pd.Series(np.linspace(10.0, 20.0, 120))
        roc = close.pct_change() * 100.0
        pr = _percent_rank(roc, n=100)
        # After warm-up, all ROCs in window are identical to today → 0
        assert np.allclose(pr.dropna().values, 0.0)


# ===========================================================================
# Tests for Connors RSI component
# ===========================================================================

class TestConnorsRSI:
    def test_range(self):
        """CRSI must be in [0, 100] where defined."""
        df = _crsi_crossover_tape()
        crsi = _connors_rsi(df)
        valid = crsi.dropna()
        assert (valid >= 0.0).all()
        assert (valid <= 100.0).all()

    def test_monotonic_up_crsi_value(self):
        """On monotonic up: RSI(close)=100, RSI(streak)=100, prank=0 → CRSI=66.67."""
        df = _monotonic_up(250)
        crsi = _connors_rsi(df)
        # Expected: (100 + 100 + 0) / 3 = 66.67
        valid = crsi.dropna()
        assert np.allclose(valid.values, 200.0 / 3.0, atol=1e-4)

    def test_monotonic_down_crsi_low(self):
        """On a long monotonic fall, CRSI should reach low values (near 0)."""
        df = _monotonic_down(250)
        crsi = _connors_rsi(df)
        # RSI(close)=0, RSI(streak)=0, prank=0 (constant step) → CRSI=0
        valid = crsi.dropna()
        assert np.allclose(valid.values, 0.0, atol=1e-4)

    def test_no_nan_after_warmup(self):
        """After the warm-up period (prank_n + a few bars), CRSI must not be NaN."""
        df = _crsi_crossover_tape()
        crsi = _connors_rsi(df)
        # Warm-up ~ 102 bars (prank needs 100 bars of ROC + 1 diff bar + rsi warm-up)
        assert not crsi.iloc[110:].isna().any()

    def test_flat_tape_produces_no_valid(self):
        """Flat tape: all ROCs = 0, all streaks = 0.
        prank(roc=0 vs window=[0..0]) = 0 (none strictly below);
        CRSI is defined after warm-up since rsi_safe handles flat with 50."""
        df = _flat(250)
        crsi = _connors_rsi(df)
        valid = crsi.dropna()
        # Should have valid values: rsi_safe(flat)=50, rsi_safe(streak=0)=50, prank=0
        # CRSI = (50 + 50 + 0) / 3 = 33.33
        assert len(valid) > 0


# ===========================================================================
# Tests for crsi_os_entry
# ===========================================================================

class TestCrsiOsEntry:
    def test_output_binary(self):
        """Output must be 0 or 1 only."""
        df = _crsi_crossover_tape()
        sig = crsi_os_entry(df)
        assert set(sig.unique()).issubset({0, 1})

    def test_no_nan(self):
        _assert_no_nan(crsi_os_entry(_crsi_crossover_tape()), "crsi_os_entry")

    def test_causality(self):
        df = _crsi_crossover_tape()
        _causality_check(crsi_os_entry, df, ks=[200, 280, 350])

    def test_fires_on_crossover_tape(self):
        """A tape with a sharp down phase should generate at least one os_entry."""
        df = _crsi_crossover_tape()
        sig = crsi_os_entry(df)
        assert sig.sum() >= 1, "Expected at least one oversold entry on crossover tape"

    def test_no_fire_on_pure_up_tape(self):
        """Monotonic up tape: CRSI stays at 66.67, never crosses below 10."""
        df = _monotonic_up(250)
        sig = crsi_os_entry(df)
        assert sig.sum() == 0

    def test_flat_tape_no_fire(self):
        """Flat tape: CRSI ~33.33, never crosses below 10."""
        df = _flat(250)
        sig = crsi_os_entry(df)
        assert sig.sum() == 0

    def test_zero_range_bars(self):
        """Zero-range bars (high==low==close) must not raise and produce valid output."""
        df = _zero_range(250)
        sig = crsi_os_entry(df)
        assert set(sig.unique()).issubset({0, 1})
        _assert_no_nan(sig, "crsi_os_entry zero-range")

    def test_gap_tape(self):
        """Gap tape must not raise; output is binary and NaN-free."""
        df = _gap_tape(250)
        sig = crsi_os_entry(df)
        assert set(sig.unique()).issubset({0, 1})
        _assert_no_nan(sig, "crsi_os_entry gap")

    def test_fires_only_once_per_cross(self):
        """os_entry is an event — fires exactly once per downward cross, not persistently."""
        df = _crsi_crossover_tape()
        crsi = _connors_rsi(df)
        sig = crsi_os_entry(df)
        # Each fire must be on a bar where CRSI < 10 AND prior CRSI >= 10
        os_level = 10.0
        for i in range(1, len(sig)):
            if sig.iloc[i] == 1:
                assert crsi.iloc[i] < os_level
                # prior must be >= os_level (or NaN — edge of warm-up)
                if pd.notna(crsi.iloc[i - 1]):
                    assert crsi.iloc[i - 1] >= os_level


# ===========================================================================
# Tests for crsi_os_exit
# ===========================================================================

class TestCrsiOsExit:
    def test_output_binary(self):
        df = _crsi_crossover_tape()
        sig = crsi_os_exit(df)
        assert set(sig.unique()).issubset({0, 1})

    def test_no_nan(self):
        _assert_no_nan(crsi_os_exit(_crsi_crossover_tape()), "crsi_os_exit")

    def test_causality(self):
        df = _crsi_crossover_tape()
        _causality_check(crsi_os_exit, df, ks=[200, 300, 370])

    def test_exit_follows_entry(self):
        """On a crossover tape, if there is an os_entry, there should eventually be an os_exit."""
        df = _crsi_crossover_tape()
        entries = crsi_os_entry(df)
        exits = crsi_os_exit(df)
        if entries.sum() > 0:
            first_entry_idx = entries.to_numpy().nonzero()[0][0]
            exits_after = exits.iloc[first_entry_idx:].sum()
            assert exits_after >= 1, "Expected at least one os_exit after an os_entry"

    def test_flat_tape(self):
        df = _flat(250)
        sig = crsi_os_exit(df)
        _assert_no_nan(sig, "crsi_os_exit flat")
        assert set(sig.unique()).issubset({0, 1})

    def test_fires_on_crossover_tape(self):
        df = _crsi_crossover_tape()
        sig = crsi_os_exit(df)
        assert sig.sum() >= 1


# ===========================================================================
# Tests for crsi_ob_exit
# ===========================================================================

class TestCrsiObExit:
    def test_output_binary(self):
        df = _crsi_crossover_tape()
        sig = crsi_ob_exit(df)
        assert set(sig.unique()).issubset({0, 1})

    def test_no_nan(self):
        _assert_no_nan(crsi_ob_exit(_crsi_crossover_tape()), "crsi_ob_exit")

    def test_causality(self):
        df = _crsi_crossover_tape()
        _causality_check(crsi_ob_exit, df, ks=[200, 300, 370])

    def test_fires_on_reversal(self):
        """A crossover tape should trigger ob_exit during the up-then-down phase."""
        df = _crsi_crossover_tape()
        sig = crsi_ob_exit(df)
        assert sig.sum() >= 1

    def test_flat_tape(self):
        df = _flat(250)
        sig = crsi_ob_exit(df)
        _assert_no_nan(sig, "crsi_ob_exit flat")
        assert set(sig.unique()).issubset({0, 1})

    def test_zero_range_bars(self):
        df = _zero_range(250)
        sig = crsi_ob_exit(df)
        assert set(sig.unique()).issubset({0, 1})
        _assert_no_nan(sig, "crsi_ob_exit zero-range")


# ===========================================================================
# Tests for Spearman rho
# ===========================================================================

class TestSpearmanN:
    def test_perfect_up_rho(self):
        """Monotonic-up tape: Spearman rho should be +100 at every full window."""
        df = _monotonic_up(50)
        rho = _spearman_n(df["close"], n=10)
        # After warm-up (bar 9+), every window is perfectly ordered → rho = 100
        assert np.allclose(rho.iloc[9:].values, 100.0, atol=1e-6)

    def test_perfect_down_rho(self):
        """Monotonic-down tape: Spearman rho should be -100 at every full window."""
        df = _monotonic_down(50)
        rho = _spearman_n(df["close"], n=10)
        assert np.allclose(rho.iloc[9:].values, -100.0, atol=1e-6)

    def test_range(self):
        """rho must be in [-100, 100]."""
        df = _reversal_tape_up_then_down()
        rho = _spearman_n(df["close"], n=10)
        valid = rho.dropna()
        assert (valid.values >= -100.0 - 1e-9).all()
        assert (valid.values <= 100.0 + 1e-9).all()

    def test_warmup_nan(self):
        """First n-1 bars are NaN."""
        df = _monotonic_up(50)
        rho = _spearman_n(df["close"], n=10)
        assert rho.iloc[:9].isna().all()
        assert rho.iloc[9:].notna().all()

    def test_flat_zero(self):
        """Flat tape: all prices tied → rho = 0 (denominator = 0 branch)."""
        df = _flat(30)
        rho = _spearman_n(df["close"], n=10)
        valid = rho.dropna()
        assert np.allclose(valid.values, 0.0, atol=1e-9)

    def test_hand_case_n3(self):
        """n=3: ascending [1,2,3]: time_ranks=[1,2,3], price_ranks=[1,2,3] → rho=1.0 → 100."""
        close = pd.Series([1.0, 2.0, 3.0])
        rho = _spearman_n(close, n=3)
        assert rho.iloc[2] == pytest.approx(100.0, abs=1e-6)


# ===========================================================================
# Tests for sprm signals
# ===========================================================================

class TestSprm:
    def test_zero_up_binary(self):
        df = _reversal_tape_down_then_up(300)
        sig = sprm_zero_up(df)
        assert set(sig.unique()).issubset({0, 1})

    def test_zero_up_no_nan(self):
        _assert_no_nan(sprm_zero_up(_reversal_tape_down_then_up(300)), "sprm_zero_up")

    def test_zero_dn_binary(self):
        df = _reversal_tape_up_then_down(300)
        sig = sprm_zero_dn(df)
        assert set(sig.unique()).issubset({0, 1})

    def test_zero_dn_no_nan(self):
        _assert_no_nan(sprm_zero_dn(_reversal_tape_up_then_down(300)), "sprm_zero_dn")

    def test_strong_up_binary(self):
        df = _monotonic_up(200)
        sig = sprm_strong_up(df)
        assert set(sig.unique()).issubset({0, 1})

    def test_strong_up_no_nan(self):
        _assert_no_nan(sprm_strong_up(_monotonic_up(200)), "sprm_strong_up")

    def test_strong_dn_binary(self):
        df = _monotonic_down(200)
        sig = sprm_strong_dn(df)
        assert set(sig.unique()).issubset({0, 1})

    def test_strong_dn_no_nan(self):
        _assert_no_nan(sprm_strong_dn(_monotonic_down(200)), "sprm_strong_dn")

    def test_strong_up_fires_on_uptrend(self):
        """Monotonic up tape: sprm_strong_up should be 1 throughout (after warm-up).
        rho=100 > 80 → state=1."""
        df = _monotonic_up(200)
        sig = sprm_strong_up(df)
        # After warm-up (n=10 bars), state=1
        assert sig.iloc[10:].sum() == len(sig.iloc[10:])

    def test_strong_dn_fires_on_downtrend(self):
        """Monotonic down tape: sprm_strong_dn should be 1 throughout (after warm-up).
        rho=-100 < -80 → state=1."""
        df = _monotonic_down(200)
        sig = sprm_strong_dn(df)
        assert sig.iloc[10:].sum() == len(sig.iloc[10:])

    def test_zero_up_fires_on_down_then_up_reversal(self):
        """Down-then-up tape: smoothed Spearman crosses zero from below → fires."""
        df = _reversal_tape_down_then_up(300)
        sig = sprm_zero_up(df)
        assert sig.sum() >= 1

    def test_zero_dn_fires_on_up_then_down_reversal(self):
        """Up-then-down tape: smoothed Spearman crosses zero from above → fires."""
        df = _reversal_tape_up_then_down(300)
        sig = sprm_zero_dn(df)
        assert sig.sum() >= 1

    def test_causality_zero_up(self):
        df = _reversal_tape_down_then_up(300)
        _causality_check(sprm_zero_up, df, ks=[120, 180, 240])

    def test_causality_zero_dn(self):
        df = _reversal_tape_up_then_down(300)
        _causality_check(sprm_zero_dn, df, ks=[120, 180, 240])

    def test_causality_strong_up(self):
        df = _monotonic_up(200)
        _causality_check(sprm_strong_up, df, ks=[50, 100, 160])

    def test_causality_strong_dn(self):
        df = _monotonic_down(200)
        _causality_check(sprm_strong_dn, df, ks=[50, 100, 160])

    def test_flat_tape(self):
        """Flat tape: rho=0, both strong_up and strong_dn stay 0."""
        df = _flat(200)
        assert sprm_strong_up(df).sum() == 0
        assert sprm_strong_dn(df).sum() == 0

    def test_zero_range_bars(self):
        """Zero-range (H==L==C) must not raise."""
        df = _zero_range(200)
        for fn in (sprm_zero_up, sprm_zero_dn, sprm_strong_up, sprm_strong_dn):
            sig = fn(df)
            assert set(sig.unique()).issubset({0, 1})
            _assert_no_nan(sig, fn.__name__)

    def test_gap_tape(self):
        """Gap tape must not raise and produce binary output."""
        df = _gap_tape(250)
        for fn in (sprm_zero_up, sprm_zero_dn, sprm_strong_up, sprm_strong_dn):
            sig = fn(df)
            assert set(sig.unique()).issubset({0, 1})
            _assert_no_nan(sig, fn.__name__)

    def test_zero_up_event_cross_condition(self):
        """Each zero_up fire must be on a bar where smoothed_rho > 0 and prior <= 0."""
        df = _reversal_tape_down_then_up(300)
        from engine.rank_momentum_signals import _spearman_n, _SPRM_N, _SPRM_SIG
        rho = _spearman_n(df["close"], n=_SPRM_N)
        smooth = rho.rolling(_SPRM_SIG, min_periods=_SPRM_SIG).mean()
        sig = sprm_zero_up(df)
        for i in range(1, len(sig)):
            if sig.iloc[i] == 1:
                assert smooth.iloc[i] > 0.0
                if pd.notna(smooth.iloc[i - 1]):
                    assert smooth.iloc[i - 1] <= 0.0


# ===========================================================================
# Tests for SIGNALS registry
# ===========================================================================

class TestSignalsRegistry:
    REQUIRED_KEYS = {
        "fn", "kind", "family", "direction", "default_params", "display", "glyph",
        # new metadata keys
        "dependency_family", "role", "entry_stack_blocked", "challenger_only",
        "provenance", "actionable_lag",
    }
    EXPECTED_IDS = {
        "crsi_os_entry", "crsi_os_exit", "crsi_ob_exit",
        "sprm_zero_up", "sprm_zero_dn", "sprm_strong_up", "sprm_strong_dn",
    }

    def test_all_ids_present(self):
        assert set(SIGNALS.keys()) == self.EXPECTED_IDS

    def test_required_keys(self):
        for sig_id, entry in SIGNALS.items():
            missing = self.REQUIRED_KEYS - set(entry.keys())
            assert not missing, f"{sig_id} missing keys: {missing}"

    def test_display_bilingual(self):
        for sig_id, entry in SIGNALS.items():
            disp = entry["display"]
            assert "en" in disp, f"{sig_id} missing 'en' display"
            assert "zh" in disp, f"{sig_id} missing 'zh' display"
            assert disp["en"], f"{sig_id} has empty 'en' display"
            assert disp["zh"], f"{sig_id} has empty 'zh' display"

    def test_kind_valid(self):
        for sig_id, entry in SIGNALS.items():
            assert entry["kind"] in ("event", "state"), f"{sig_id} bad kind"

    def test_direction_valid(self):
        for sig_id, entry in SIGNALS.items():
            assert entry["direction"] in (-1, 0, +1), f"{sig_id} bad direction"

    def test_crsi_dependency_family(self):
        for sig_id in ("crsi_os_entry", "crsi_os_exit", "crsi_ob_exit"):
            assert SIGNALS[sig_id]["dependency_family"] == "rsi_mean_reversion"

    def test_crsi_entry_stack_blocked(self):
        for sig_id in ("crsi_os_entry", "crsi_os_exit", "crsi_ob_exit"):
            assert SIGNALS[sig_id]["entry_stack_blocked"] is True

    def test_sprm_entry_stack_not_blocked(self):
        for sig_id in ("sprm_zero_up", "sprm_zero_dn", "sprm_strong_up", "sprm_strong_dn"):
            assert SIGNALS[sig_id]["entry_stack_blocked"] is False

    def test_sprm_dependency_family(self):
        for sig_id in ("sprm_zero_up", "sprm_zero_dn", "sprm_strong_up", "sprm_strong_dn"):
            assert SIGNALS[sig_id]["dependency_family"] == "rank_trend"

    def test_fn_callable(self):
        for sig_id, entry in SIGNALS.items():
            assert callable(entry["fn"]), f"{sig_id} fn not callable"

    def test_fn_runs_on_flat_tape(self):
        """Every signal function must run without error on flat tape."""
        df = _flat(250)
        for sig_id, entry in SIGNALS.items():
            sig = entry["fn"](df)
            assert len(sig) == len(df), f"{sig_id} wrong length"
            _assert_no_nan(sig, sig_id)

    def test_events_are_integer(self):
        """Event signals must return integer dtype (0/1)."""
        df = _crsi_crossover_tape()
        for sig_id, entry in SIGNALS.items():
            if entry["kind"] == "event":
                sig = entry["fn"](df)
                assert sig.dtype in (np.dtype("int64"), np.dtype("int32"), np.dtype("int8")), \
                    f"{sig_id} event is not integer dtype (got {sig.dtype})"
                assert set(sig.unique()).issubset({0, 1}), f"{sig_id} event has values outside {{0,1}}"

    def test_crsi_roles(self):
        assert SIGNALS["crsi_os_entry"]["role"] == "setup"
        assert SIGNALS["crsi_os_exit"]["role"] == "trigger"
        assert SIGNALS["crsi_ob_exit"]["role"] == "trigger"

    def test_sprm_states_role(self):
        for sig_id in ("sprm_strong_up", "sprm_strong_dn"):
            assert SIGNALS[sig_id]["role"] == "context"

    def test_sprm_events_role(self):
        for sig_id in ("sprm_zero_up", "sprm_zero_dn"):
            assert SIGNALS[sig_id]["role"] == "trigger"

    def test_challenger_only_false_for_all(self):
        for sig_id, entry in SIGNALS.items():
            assert entry["challenger_only"] is False

    def test_actionable_lag_zero(self):
        for sig_id, entry in SIGNALS.items():
            assert entry["actionable_lag"] == 0
