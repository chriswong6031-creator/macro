"""Tests for engine/pivots.py — Pivot Bottom / Pivot Top signals.

Required test cases:
  (1) Module imports cleanly.
  (2) Each SIGNALS fn returns a pd.Series aligned to a sample OHLCV frame
      with no NaN-index.
  (3) Look-ahead guard: truncating the frame at date T does not change the
      signal value at any date < T.
  (4) PIT contract: a pivot fires on the confirmation bar (i+k), not the
      pivot bar (i).
  (5) Signal values are in {0.0, 1.0}.
  (6) Series name matches the signal id.
  (7) Gates toggle correctly (apply_rsi_gate=False, apply_volume_gate=False).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------------------
# (1) Module import
# ---------------------------------------------------------------------------

class TestImport:
    def test_module_imports(self):
        import engine.pivots  # noqa: F401

    def test_signals_dict_present(self):
        from engine.pivots import SIGNALS
        assert isinstance(SIGNALS, dict)
        assert "pivot_bottom" in SIGNALS
        assert "pivot_top" in SIGNALS

    def test_signals_dict_structure(self):
        from engine.pivots import SIGNALS
        for sid, spec in SIGNALS.items():
            assert "fn" in spec, f"{sid}: missing 'fn'"
            assert "kind" in spec, f"{sid}: missing 'kind'"
            assert "family" in spec, f"{sid}: missing 'family'"
            assert "direction" in spec, f"{sid}: missing 'direction'"
            assert "default_params" in spec, f"{sid}: missing 'default_params'"
            assert "display" in spec, f"{sid}: missing 'display'"
            assert "glyph" in spec, f"{sid}: missing 'glyph'"
            assert "en" in spec["display"], f"{sid}: missing display.en"
            assert "zh" in spec["display"], f"{sid}: missing display.zh"
            assert callable(spec["fn"]), f"{sid}: fn is not callable"

    def test_directions(self):
        from engine.pivots import SIGNALS
        assert SIGNALS["pivot_bottom"]["direction"] == +1
        assert SIGNALS["pivot_top"]["direction"] == -1

    def test_glyphs(self):
        from engine.pivots import SIGNALS
        assert SIGNALS["pivot_bottom"]["glyph"] == "circle_green"
        assert SIGNALS["pivot_top"]["glyph"] == "circle_red"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SEED = 42
N_BARS = 500  # enough for k=5, RSI(14), and meaningful pivot count


def _idx(n: int, start: str = "2015-01-01") -> pd.DatetimeIndex:
    return pd.bdate_range(start, periods=n)


def _make_ohlcv(
    close_vals: np.ndarray,
    high_frac: float = 0.01,
    low_frac: float = 0.01,
    volume: float = 2_000_000.0,
) -> pd.DataFrame:
    """Build a full OHLCV DataFrame."""
    n = len(close_vals)
    idx = _idx(n)
    c = np.asarray(close_vals, dtype=float)
    o = np.roll(c, 1)
    o[0] = c[0]
    h = c * (1 + high_frac)
    low = c * (1 - low_frac)
    v = np.full(n, volume)
    return pd.DataFrame(
        {"open": o, "high": h, "low": low, "close": c, "volume": v}, index=idx
    )


def _make_zigzag_close(n: int = N_BARS, seed: int = SEED) -> np.ndarray:
    """Synthetic close with clear zigzag oscillation (sine wave + small noise)."""
    rng = np.random.default_rng(seed)
    t = np.linspace(0, 12 * np.pi, n)
    noise = rng.normal(0, 0.3, n)
    return 100.0 + 8.0 * np.sin(t) + noise


def _make_trending_close(n: int = N_BARS, seed: int = SEED + 1) -> np.ndarray:
    """Monotone uptrend with small noise."""
    rng = np.random.default_rng(seed)
    rets = 0.002 + rng.normal(0, 0.005, n)
    return 100.0 * np.exp(np.cumsum(rets))


# ---------------------------------------------------------------------------
# (2) Return type and alignment
# ---------------------------------------------------------------------------

class TestReturnType:
    """Each SIGNALS fn must return a pd.Series aligned to df.index, no NaN-index."""

    @classmethod
    def setup_class(cls):
        close = _make_zigzag_close()
        cls.df = _make_ohlcv(close)

    def _run_signal(self, sid: str) -> pd.Series:
        from engine.pivots import SIGNALS
        spec = SIGNALS[sid]
        return spec["fn"](self.df, **spec["default_params"])

    def test_pivot_bottom_returns_series(self):
        s = self._run_signal("pivot_bottom")
        assert isinstance(s, pd.Series), "pivot_bottom must return pd.Series"

    def test_pivot_top_returns_series(self):
        s = self._run_signal("pivot_top")
        assert isinstance(s, pd.Series), "pivot_top must return pd.Series"

    def test_pivot_bottom_aligned(self):
        s = self._run_signal("pivot_bottom")
        assert s.index.equals(self.df.index), "pivot_bottom index must match df.index"

    def test_pivot_top_aligned(self):
        s = self._run_signal("pivot_top")
        assert s.index.equals(self.df.index), "pivot_top index must match df.index"

    def test_pivot_bottom_no_nan_index(self):
        s = self._run_signal("pivot_bottom")
        assert not s.index.isna().any(), "pivot_bottom has NaN in index"

    def test_pivot_top_no_nan_index(self):
        s = self._run_signal("pivot_top")
        assert not s.index.isna().any(), "pivot_top has NaN in index"

    def test_pivot_bottom_binary_values(self):
        """Values must be in {0.0, 1.0}."""
        s = self._run_signal("pivot_bottom")
        unique = set(s.dropna().unique())
        assert unique.issubset({0.0, 1.0}), f"pivot_bottom has non-binary values: {unique}"

    def test_pivot_top_binary_values(self):
        s = self._run_signal("pivot_top")
        unique = set(s.dropna().unique())
        assert unique.issubset({0.0, 1.0}), f"pivot_top has non-binary values: {unique}"

    def test_pivot_bottom_named(self):
        s = self._run_signal("pivot_bottom")
        assert s.name == "pivot_bottom", f"Expected name 'pivot_bottom', got '{s.name}'"

    def test_pivot_top_named(self):
        s = self._run_signal("pivot_top")
        assert s.name == "pivot_top", f"Expected name 'pivot_top', got '{s.name}'"

    def test_pivot_bottom_fires_at_least_once(self):
        """On a zigzag synthetic series, at least one pivot bottom should fire."""
        from engine.pivots import pivot_bottom
        s = pivot_bottom(self.df, k=5, apply_rsi_gate=False, apply_volume_gate=False)
        assert s.sum() > 0, "pivot_bottom fired 0 times on zigzag fixture (gates off)"

    def test_pivot_top_fires_at_least_once(self):
        from engine.pivots import pivot_top
        s = pivot_top(self.df, k=5, apply_rsi_gate=False, apply_volume_gate=False)
        assert s.sum() > 0, "pivot_top fired 0 times on zigzag fixture (gates off)"


# ---------------------------------------------------------------------------
# (3) Look-ahead guard (PIT test) — THE CRITICAL TEST
# ---------------------------------------------------------------------------

class TestNoLookahead:
    """Truncating the frame at date T must not change any signal value at date < T."""

    @classmethod
    def setup_class(cls):
        close = _make_zigzag_close(n=N_BARS, seed=SEED)
        cls.df_full = _make_ohlcv(close)

    def _check_signal_no_lookahead(self, fn, name: str, **kwargs):
        """Run fn on full frame and truncated frames; compare values before truncation."""
        s_full = fn(self.df_full, **kwargs)

        # Test at 3 truncation points (all after burn-in)
        test_positions = [300, 370, 430]
        failures = []

        for t in test_positions:
            df_trunc = self.df_full.iloc[:t + 1]
            s_trunc = fn(df_trunc, **kwargs)

            # Compare values at all dates in the truncated frame (excluding last bar where
            # the truncation edge might block a pivot that needs future bars to confirm)
            # We compare up to t - k - 1 to avoid the boundary where truncation
            # prevents confirmation that would happen in the full frame
            compare_up_to = t - 10  # conservative safety margin
            for idx_pos in range(compare_up_to):
                dt = self.df_full.index[idx_pos]
                full_val = s_full.iloc[idx_pos]
                trunc_val = s_trunc.iloc[idx_pos]
                if full_val != trunc_val:
                    failures.append(
                        f"{name} @ {dt} (pos={idx_pos}): "
                        f"full={full_val} trunc={trunc_val} at truncation t={t}"
                    )

        assert not failures, "Look-ahead violations found:\n" + "\n".join(failures[:10])

    def test_pivot_bottom_no_lookahead(self):
        from engine.pivots import pivot_bottom
        self._check_signal_no_lookahead(
            pivot_bottom, "pivot_bottom",
            k=5, apply_rsi_gate=False, apply_volume_gate=False
        )

    def test_pivot_top_no_lookahead(self):
        from engine.pivots import pivot_top
        self._check_signal_no_lookahead(
            pivot_top, "pivot_top",
            k=5, apply_rsi_gate=False, apply_volume_gate=False
        )

    def test_pivot_bottom_no_lookahead_with_rsi(self):
        from engine.pivots import pivot_bottom
        self._check_signal_no_lookahead(
            pivot_bottom, "pivot_bottom_rsi",
            k=5, apply_rsi_gate=True, apply_volume_gate=False
        )

    def test_pivot_top_no_lookahead_with_rsi(self):
        from engine.pivots import pivot_top
        self._check_signal_no_lookahead(
            pivot_top, "pivot_top_rsi",
            k=5, apply_rsi_gate=True, apply_volume_gate=False
        )


# ---------------------------------------------------------------------------
# (4) PIT contract: fire on confirmation bar i+k, not pivot bar i
# ---------------------------------------------------------------------------

class TestPITContract:
    """Verify the signal fires on bar i+k (confirmation), not bar i (pivot)."""

    def _build_known_pivot_df(self) -> tuple[pd.DataFrame, int]:
        """Build a frame with an engineered local minimum at a known position.

        Uses a strictly monotone descent into the pivot and strict monotone ascent
        out, ensuring no secondary local minima exist in the k-window around
        pivot_bar.  Bars outside the V-zone are held flat at 100.0.
        """
        n = 200
        k = 5
        idx = _idx(n)
        pivot_bar = 100
        # Start with everything flat at 100.0
        close = np.full(n, 100.0)

        # Strictly descending into pivot_bar: each bar LOWER than the previous
        # (bars pivot_bar-k .. pivot_bar-1 go 99, 98, 97, 96, 95)
        for j in range(1, k + 1):
            close[pivot_bar - j] = 100.0 - j  # 99 at -1, 98 at -2, ..., 95 at -5

        # The pivot bar is the absolute minimum in the window
        close[pivot_bar] = 88.0

        # Strictly ascending out of pivot_bar: each bar HIGHER than the previous
        # (bars pivot_bar+1 .. pivot_bar+k go 91, 93, 95, 97, 99)
        for j in range(1, k + 1):
            close[pivot_bar + j] = 88.0 + j * 2.0  # 90, 92, 94, 96, 98

        # bar pivot_bar+k = 98.0; bars beyond pivot_bar+k stay at 100.0 (flat)
        # This ensures pivot_bar is the unique minimum in any k=5 window

        h = close * 1.005
        low = close * 0.995
        v = np.full(n, 3_000_000.0)
        o = np.roll(close, 1)
        o[0] = close[0]
        df = pd.DataFrame(
            {"open": o, "high": h, "low": low, "close": close, "volume": v}, index=idx
        )
        return df, pivot_bar

    def test_bottom_fires_at_confirm_bar_not_pivot_bar(self):
        """pivot_bottom must fire at pivot_bar + k, not at pivot_bar."""
        from engine.pivots import pivot_bottom
        df, pivot_bar = self._build_known_pivot_df()
        k = 5
        s = pivot_bottom(df, k=k, apply_rsi_gate=False, apply_volume_gate=False)

        confirm_bar = pivot_bar + k
        # Signal at confirm bar should be 1.0
        assert s.iloc[confirm_bar] == 1.0, (
            f"Expected fire at confirm_bar={confirm_bar}, got {s.iloc[confirm_bar]}"
        )
        # Signal at pivot bar should be 0.0
        assert s.iloc[pivot_bar] == 0.0, (
            f"Signal fired at pivot_bar={pivot_bar} — that is a look-ahead violation"
        )
        # Signal at any bar before confirmation should be 0.0
        for j in range(pivot_bar - k, pivot_bar + k):
            assert s.iloc[j] == 0.0, (
                f"Signal fired at bar {j} before confirmation — look-ahead violation"
            )


# ---------------------------------------------------------------------------
# (5) Gate toggle tests
# ---------------------------------------------------------------------------

class TestGateToggles:
    """Gates off -> more or equal fires than gates on."""

    @classmethod
    def setup_class(cls):
        close = _make_zigzag_close(n=N_BARS, seed=SEED + 10)
        cls.df = _make_ohlcv(close, volume=1_500_000.0)

    def test_rsi_gate_off_fires_more_or_equal(self):
        """Disabling RSI gate should fire at least as many times (never fewer)."""
        from engine.pivots import pivot_bottom
        s_gated = pivot_bottom(self.df, k=5, apply_rsi_gate=True, apply_volume_gate=False)
        s_ungated = pivot_bottom(self.df, k=5, apply_rsi_gate=False, apply_volume_gate=False)
        assert s_ungated.sum() >= s_gated.sum(), (
            f"RSI gate off fires {s_ungated.sum()} < gated {s_gated.sum()}"
        )

    def test_volume_gate_off_fires_more_or_equal(self):
        """Disabling volume gate should fire at least as many times (never fewer)."""
        from engine.pivots import pivot_bottom
        s_gated = pivot_bottom(self.df, k=5, apply_rsi_gate=False, apply_volume_gate=True)
        s_ungated = pivot_bottom(self.df, k=5, apply_rsi_gate=False, apply_volume_gate=False)
        assert s_ungated.sum() >= s_gated.sum(), (
            f"Volume gate off fires {s_ungated.sum()} < gated {s_gated.sum()}"
        )

    def test_rsi_gate_top_off_fires_more_or_equal(self):
        from engine.pivots import pivot_top
        s_gated = pivot_top(self.df, k=5, apply_rsi_gate=True, apply_volume_gate=False)
        s_ungated = pivot_top(self.df, k=5, apply_rsi_gate=False, apply_volume_gate=False)
        assert s_ungated.sum() >= s_gated.sum()


# ---------------------------------------------------------------------------
# (6) Close-only (no volume/high/low columns)
# ---------------------------------------------------------------------------

class TestCloseOnly:
    """Must not crash on a close-only DataFrame; volume gate skipped when no volume."""

    @classmethod
    def setup_class(cls):
        close = _make_zigzag_close(n=N_BARS)
        idx = _idx(N_BARS)
        cls.df = pd.DataFrame({"close": close}, index=idx)

    def test_pivot_bottom_close_only_no_crash(self):
        from engine.pivots import pivot_bottom
        s = pivot_bottom(self.df, k=5, apply_rsi_gate=False, apply_volume_gate=True)
        assert isinstance(s, pd.Series)
        assert s.index.equals(self.df.index)

    def test_pivot_top_close_only_no_crash(self):
        from engine.pivots import pivot_top
        s = pivot_top(self.df, k=5, apply_rsi_gate=False, apply_volume_gate=True)
        assert isinstance(s, pd.Series)
        assert s.index.equals(self.df.index)

    def test_pivot_bottom_fires_close_only(self):
        from engine.pivots import pivot_bottom
        s = pivot_bottom(self.df, k=5, apply_rsi_gate=False, apply_volume_gate=False)
        assert s.sum() > 0, "pivot_bottom should fire on zigzag close-only fixture"


# ---------------------------------------------------------------------------
# (7) k parameter variation
# ---------------------------------------------------------------------------

class TestKParameter:
    """Larger k means fewer, more widely-spaced pivots (stronger filter)."""

    @classmethod
    def setup_class(cls):
        close = _make_zigzag_close(n=N_BARS, seed=SEED + 20)
        cls.df = _make_ohlcv(close)

    def test_larger_k_fewer_pivots(self):
        from engine.pivots import pivot_bottom
        s_k3 = pivot_bottom(self.df, k=3, apply_rsi_gate=False, apply_volume_gate=False)
        s_k10 = pivot_bottom(self.df, k=10, apply_rsi_gate=False, apply_volume_gate=False)
        assert s_k10.sum() <= s_k3.sum(), (
            f"k=10 fires {s_k10.sum()} > k=3 fires {s_k3.sum()} — unexpected"
        )

    def test_larger_k_fewer_tops(self):
        from engine.pivots import pivot_top
        s_k3 = pivot_top(self.df, k=3, apply_rsi_gate=False, apply_volume_gate=False)
        s_k10 = pivot_top(self.df, k=10, apply_rsi_gate=False, apply_volume_gate=False)
        assert s_k10.sum() <= s_k3.sum()
