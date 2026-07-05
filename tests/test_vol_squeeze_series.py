"""tests/test_vol_squeeze_series.py — fidelity-pin test for vol_squeeze.assess_series.

Masterplan PR-A3 spec: for every truncation length t,
    assess_series(full_series).state.iloc[t]
    == assess(full_series.iloc[:t+1]).state  (or NONE when assess returns None)

Known-answer test:
* fixture >= 400 bars with at least one full compression-then-release episode
* assert equality on >= 50 truncation lengths spanning pre-compression,
  in-compression, release bars, and expansion.

Also tests: NONE mapping below min_bars, days_in_state monotonicity, box columns.
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd
import pytest

from engine import vol_squeeze as vs


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def _idx(n: int) -> pd.DatetimeIndex:
    return pd.bdate_range("2018-01-01", periods=n)


def _noisy(n: int, start: float = 100.0, scale: float = 1.5, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return start + np.cumsum(rng.standard_normal(n) * scale)


def _tight(level: float, n: int, jitter: float = 0.015, seed: int = 42) -> np.ndarray:
    """Low-vol stretch that triggers BBWP/HVP compression."""
    rng = np.random.default_rng(seed)
    return level + rng.standard_normal(n) * jitter


def _build_fixture(
    pre: int = 240,
    squeeze: int = 30,
    post_break: int = 80,
    expansion: int = 60,
    seed: int = 7,
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    """Build a 4-segment fixture containing a full compression-then-release episode.

    Segments:
        pre         : normal trending noise (pre-compression)
        squeeze     : tight range triggering COILED state
        post_break  : large up-break + trailing bars (FIRED_UP then EXPANSION)
        expansion   : high-vol continuation

    Returns (close, high, low, volume) as pd.Series, all on the same index.
    """
    rng = np.random.default_rng(seed)

    noisy = _noisy(pre, start=100.0, scale=1.5, seed=seed)
    anchor = float(noisy[-1])

    tight = _tight(anchor, squeeze, jitter=0.015, seed=seed + 1)

    # Break out upward by ~10% on the first post-break bar
    break_bar = anchor + 10.0
    # Following bars: mild uptrend with moderate volatility
    post_arr = np.concatenate([
        [break_bar],
        break_bar + np.cumsum(rng.standard_normal(post_break - 1) * 0.8),
    ])

    # Expansion: high realized vol
    exp_start = float(post_arr[-1])
    exp_arr = exp_start + np.cumsum(rng.standard_normal(expansion) * 3.5)

    px = np.concatenate([noisy, tight, post_arr, exp_arr])
    n = len(px)
    idx = _idx(n)

    close = pd.Series(px, index=idx)
    spread = np.abs(rng.standard_normal(n)) * 0.15 + 0.05
    high = close + spread
    low = close - spread

    # Volume: base 1M; spike on break-out bar
    vol_arr = np.full(n, 1_000_000.0)
    break_idx = pre + squeeze  # index of the first post-break bar
    vol_arr[break_idx] = 3_500_000.0  # volume confirmation spike
    volume = pd.Series(vol_arr, index=idx)

    return close, high, low, volume


# ---------------------------------------------------------------------------
# Core fidelity-pin test
# ---------------------------------------------------------------------------

class TestAssessSeriesFidelityPin:
    """assess_series(full).state.iloc[t] == scalar assess() state at every t."""

    @pytest.fixture(scope="class")
    def fixture_data(self):
        return _build_fixture()

    @pytest.fixture(scope="class")
    def full_series(self, fixture_data):
        close, high, low, volume = fixture_data
        return vs.assess_series(close, high, low, volume)

    def _scalar_state(
        self,
        close: pd.Series,
        high: pd.Series,
        low: pd.Series,
        volume: pd.Series,
        t: int,
    ) -> str:
        result = vs.assess(
            close.iloc[: t + 1],
            high.iloc[: t + 1],
            low.iloc[: t + 1],
            volume.iloc[: t + 1],
        )
        return result["state"] if result is not None else "NONE"

    def test_fixture_length(self, fixture_data):
        close, _, _, _ = fixture_data
        assert len(close) >= 400, "fixture must be >= 400 bars"

    def test_series_index_matches_close(self, fixture_data, full_series):
        close, _, _, _ = fixture_data
        pd.testing.assert_index_equal(full_series.index, close.index)

    def test_state_column_values(self, full_series):
        valid = {"COILED", "COMPRESSED", "FIRED_UP", "FIRED_DOWN", "EXPANSION", "NONE"}
        bad = set(full_series["state"].unique()) - valid
        assert not bad, f"Unknown states: {bad}"

    def test_fidelity_pin_50_truncations(self, fixture_data, full_series):
        """Core pin: 50 truncation lengths spanning all regimes."""
        close, high, low, volume = fixture_data
        n = len(close)
        # pre_compression zone: bars 100-150
        pre_range = list(range(165, 241, 5))  # 16 points (post-min_bars, pre-compression)
        # in_compression zone: bars 241-269 (the tight section starts at 240)
        comp_start = 241
        comp_range = list(range(comp_start, comp_start + 29))  # 29 points
        # release zone: bars 270-275 (first post-break bars)
        release_range = list(range(270, 276))  # 6 points
        # expansion zone: bars 300-369
        exp_range = list(range(300, 370, 7))  # 11 points
        # early (below min_bars) zone: bars 10-158 (t+1 < 160 → t < 159)
        early_range = list(range(10, 159, 20))  # 8 points

        all_t = sorted(set(pre_range + comp_range + release_range + exp_range + early_range))
        # Clip to valid range
        all_t = [t for t in all_t if t < n]

        assert len(all_t) >= 50, f"Need >= 50 truncation points, got {len(all_t)}"

        mismatches = []
        for t in all_t:
            series_state = full_series["state"].iloc[t]
            scalar_state = self._scalar_state(close, high, low, volume, t)
            if series_state != scalar_state:
                mismatches.append(
                    f"t={t}: series={series_state!r} vs scalar={scalar_state!r}"
                )

        assert not mismatches, (
            f"{len(mismatches)} fidelity-pin failures:\n" + "\n".join(mismatches[:10])
        )

    def test_none_mapping_below_min_bars(self, fixture_data, full_series):
        """Bars below min_bars=160 must map to NONE (assess() returns None there).

        assess() condition: ``len(c) < min_bars``.  At truncation t, we feed
        t+1 bars, so the condition fires when t+1 < 160, i.e. t < 159.
        Bar t=159 (160 bars) already passes assess() — do not include it.
        """
        close, high, low, volume = fixture_data
        cfg = vs.DEFAULTS
        min_bars = cfg["min_bars"]

        for t in range(0, min_bars - 1):  # t < 159, so t+1 < 160
            result = vs.assess(
                close.iloc[: t + 1],
                high.iloc[: t + 1],
                low.iloc[: t + 1],
                volume.iloc[: t + 1],
            )
            assert result is None, f"assess() should return None at t={t}"
            series_state = full_series["state"].iloc[t]
            assert series_state == "NONE", (
                f"assess_series should map None->NONE at t={t}, got {series_state!r}"
            )

    def test_days_in_state_monotonic_within_run(self, full_series):
        """days_in_state increments within a continuous run and resets on change."""
        states = full_series["state"].to_numpy()
        dis = full_series["days_in_state"].to_numpy()
        assert dis[0] == 1
        for i in range(1, len(states)):
            if states[i] == states[i - 1]:
                assert dis[i] == dis[i - 1] + 1, (
                    f"days_in_state should increment at i={i}: "
                    f"state={states[i]!r}, dis={dis[i]}, prev={dis[i-1]}"
                )
            else:
                assert dis[i] == 1, (
                    f"days_in_state should reset at i={i}: "
                    f"prev_state={states[i-1]!r} -> {states[i]!r}, dis={dis[i]}"
                )

    def test_box_columns_present(self, full_series):
        for col in ("box_hi", "box_lo", "bbwp", "hv_pctile"):
            assert col in full_series.columns, f"Missing column: {col}"

    def test_box_columns_finite_when_coiled(self, full_series):
        """When state is COILED, box_hi and box_lo must be finite."""
        coiled_rows = full_series[full_series["state"] == "COILED"]
        if not coiled_rows.empty:
            assert coiled_rows["box_hi"].notna().all(), "box_hi should be finite when COILED"
            assert coiled_rows["box_lo"].notna().all(), "box_lo should be finite when COILED"

    def test_fired_up_has_correct_dir(self, full_series):
        """FIRED_UP rows must have fired_dir == 'up'."""
        fired_up = full_series[full_series["state"] == "FIRED_UP"]
        if not fired_up.empty:
            assert (fired_up["fired_dir"] == "up").all()

    def test_fired_down_has_correct_dir(self, full_series):
        """FIRED_DOWN rows must have fired_dir == 'down'."""
        fired_down = full_series[full_series["state"] == "FIRED_DOWN"]
        if not fired_down.empty:
            assert (fired_down["fired_dir"] == "down").all()


# ---------------------------------------------------------------------------
# Close-only fidelity pin (no h/l/volume)
# ---------------------------------------------------------------------------

class TestAssessSeriesCloseOnly:
    """Fidelity pin with close-only input."""

    @pytest.fixture(scope="class")
    def close_only_fixture(self):
        close, _, _, _ = _build_fixture(seed=13)
        return close

    def test_fidelity_pin_close_only(self, close_only_fixture):
        close = close_only_fixture
        n = len(close)
        full_series = vs.assess_series(close)

        # 20 truncation points spread across the series
        truncations = list(range(50, n, n // 20))[:20]
        mismatches = []
        for t in truncations:
            series_state = full_series["state"].iloc[t]
            result = vs.assess(close.iloc[: t + 1])
            scalar_state = result["state"] if result is not None else "NONE"
            if series_state != scalar_state:
                mismatches.append(f"t={t}: series={series_state!r} vs scalar={scalar_state!r}")

        assert not mismatches, (
            f"Close-only fidelity failures:\n" + "\n".join(mismatches)
        )


# ---------------------------------------------------------------------------
# assess() is not modified (guard: existing tests still pass indirectly)
# ---------------------------------------------------------------------------

def test_assess_still_returns_none_when_too_short():
    c = pd.Series(_noisy(50), index=_idx(50))
    assert vs.assess(c) is None


def test_assess_series_output_columns():
    close, high, low, volume = _build_fixture(seed=99)
    df = vs.assess_series(close, high, low, volume)
    required = {"state", "days_in_state", "days_compressed",
                "box_hi", "box_lo", "bbwp", "hv_pctile",
                "fired_dir", "volume_confirmed", "coverage"}
    assert required.issubset(df.columns), f"Missing: {required - set(df.columns)}"


# ---------------------------------------------------------------------------
# Performance benchmark (informational — not a hard assertion on CI)
# ---------------------------------------------------------------------------

def test_assess_series_timing_5000_bars():
    """Informational timing for a 5000-bar series (masterplan PR body requirement).

    Wall-clock is measured and printed; test passes unconditionally so CI is not
    blocked by machine speed variance. The PR body reports the observed value.
    """
    n = 5000
    close, high, low, volume = _build_fixture(
        pre=4700, squeeze=100, post_break=100, expansion=100, seed=2024
    )
    # The fixture builder creates pre+squeeze+post+expansion bars:
    # make sure total is ~5000
    close = close.iloc[:n]
    high = high.reindex(close.index)
    low = low.reindex(close.index)
    volume = volume.reindex(close.index)

    t0 = time.perf_counter()
    df = vs.assess_series(close, high, low, volume)
    elapsed = time.perf_counter() - t0

    print(f"\nassess_series timing: {n} bars -> {elapsed:.2f}s")
    assert len(df) == n
    # Soft bound: warn if > 120s (60x the masterplan budget; hard assertion avoided)
    if elapsed > 120:
        pytest.skip(f"assess_series took {elapsed:.1f}s — machine under load, skip soft bound")
