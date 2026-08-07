"""W8 ignition constructions — port fidelity against the FROZEN research instrument.

`engine/ignition_features.py` re-implements the detectors that
`research/prophet_us_audit/ignition_standins.py` measured (PR #4564). The research file is a
frozen artifact and is NOT edited to import the engine module, so the two are independent
implementations of one construction — a fork risk answered here rather than in a docstring.

Covered:
  1. PORT FIDELITY — elementwise identity with the frozen instrument, on panels where the
     detectors actually fire (an all-False agreement would prove nothing).
  2. Constant parity — every measurement constant equals the frozen instrument's value.
  3. The history floors, which exist because these detectors return BOOLEANS: a cold bar reads
     `False`, not NaN, so a short series silently reports "not compressed" / "quiet".
  4. Thrust semantics — the event de-bounce that keeps the recorded population equal to the
     population #4564 graded.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine import ignition_features as ig

REPO = Path(__file__).resolve().parents[1]
STANDIN = REPO / "research" / "prophet_us_audit" / "ignition_standins.py"


def _frozen():
    """Import the frozen W8 battery read-only.

    It is a SCRIPT, not a library: `os.chdir(REPO)` and `sys.path.insert` run at import time.
    The cwd is saved and restored around the import so one comparison cannot silently relocate
    the whole pytest process (tmp_path-based tests elsewhere would then read the wrong tree).
    """
    assert STANDIN.exists(), f"the frozen W8 instrument is missing: {STANDIN}"
    cwd = os.getcwd()
    try:
        spec = importlib.util.spec_from_file_location("_w8_standins_readonly", STANDIN)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        os.chdir(cwd)


# --------------------------------------------------------------------------- #
# builders — deterministic, no RNG (repo idiom: a fixture must be reproducible)
# --------------------------------------------------------------------------- #
def coil_tape(n: int = 340, quiet: int = 45, *, loud_amp: float = 0.030,
              quiet_step: float = 0.0015, loud_w: float = 0.020,
              quiet_w: float = 0.0004, col: str = "X",
              start: str = "2024-01-01") -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """A tape that goes QUIET at the end: `quiet` sessions of tiny steady drift after a loud
    alternating-return regime.

    The loud phase fills the 252-session ATR reference window with big true ranges, so the
    quiet phase's ATR ranks under p25; the steady drift puts price above a rising 50dMA. Both
    S-COIL legs then hold, deterministically. `quiet=0` is the never-compressed control.
    """
    rets = [loud_amp * (1 if i % 2 == 0 else -1) for i in range(n - quiet)] + [quiet_step] * quiet
    close = pd.DataFrame({col: 100.0 * np.exp(np.cumsum(rets))},
                         index=pd.bdate_range(start, periods=n))
    w = np.array([loud_w] * (n - quiet) + [quiet_w] * quiet)
    return close, close * (1 + w[:, None]), close * (1 - w[:, None])


def _mixed_panel(n: int = 340) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """A multi-name panel mixing compressed and never-compressed tapes, so a comparison over it
    exercises both branches of every leg."""
    frames = {}
    for i, q in enumerate((0, 25, 45, 60, 90, 0, 45)):
        c, h, lo = coil_tape(n=n, quiet=q, col=f"M{i}",
                             loud_amp=0.030 + 0.002 * i, quiet_step=0.0015)
        frames[f"M{i}"] = (c[f"M{i}"], h[f"M{i}"], lo[f"M{i}"])
    close = pd.DataFrame({k: v[0] for k, v in frames.items()})
    high = pd.DataFrame({k: v[1] for k, v in frames.items()})
    low = pd.DataFrame({k: v[2] for k, v in frames.items()})
    return close, high, low


class TestPortFidelity:
    """The engine port must be elementwise identical to the frozen instrument."""

    def test_coil_compression_matches_the_frozen_instrument(self):
        close, high, low = _mixed_panel()
        mine = ig.coil_compression(close, high, low)
        theirs = _frozen().coil_compression(close, high, low)
        # NOT VACUOUS: the panel must contain both compressed and uncompressed cells, or two
        # all-False frames would "agree" while proving nothing about the construction.
        n_true = int(mine.to_numpy().sum())
        assert 0 < n_true < mine.size, f"fixture exercises only one branch (True cells={n_true})"
        assert mine.equals(theirs)

    def test_above_20d_high_matches_the_frozen_instrument(self):
        close, high, _ = _mixed_panel()
        mine = ig.above_20d_high(close, high)
        theirs = _frozen().above_20d_high(close, high)
        n_true = int(mine.to_numpy().sum())
        assert 0 < n_true < mine.size, f"fixture exercises only one branch (True cells={n_true})"
        assert mine.equals(theirs)

    def test_true_range_matches_the_frozen_instrument(self):
        close, high, low = _mixed_panel()
        assert ig.true_range(high, low, close).equals(_frozen().true_range(high, low, close))

    @pytest.mark.parametrize("name", ["ATR_WIN", "PCT_WIN", "PCT_MAX", "MA_WIN", "MA_SLOPE",
                                      "COMP_LOOKBACK", "COMP_MIN", "HIGH20", "THRUST_LO",
                                      "THRUST_HI", "THRUST_WIN"])
    def test_measurement_constants_equal_the_frozen_values(self, name):
        """These are MEASUREMENT constants, not tunables: a drifted one makes every recorded
        feature incomparable with the #4564 numbers it exists to test."""
        assert getattr(ig, name) == getattr(_frozen(), name), name

    def test_member_floor_equals_the_frozen_value(self):
        assert ig.THRUST_MIN_MEMBERS == _frozen().MIN_MEMBERS

    def test_thrust_condition_matches_the_frozen_inner_block(self):
        """`thrust_fired` is lifted out of `thrust_lag_events`'s loop, so it is compared against
        that block's arithmetic rather than against a callable the frozen file does not expose."""
        m = _frozen()
        frac = pd.Series([0.1] * 10 + [0.2, 0.6, 0.7, 0.1, 0.8, 0.9],
                         index=pd.bdate_range("2025-01-01", periods=16))
        theirs_lo = (frac < m.THRUST_LO).rolling(m.THRUST_WIN).max().shift(1)
        theirs = (frac > m.THRUST_HI) & (theirs_lo == 1.0)
        theirs = theirs & ~(theirs.shift(1).fillna(False).astype(bool))
        mine = ig.thrust_fired(frac)
        assert int(mine.sum()) > 0, "fixture must fire at least once"
        assert mine.equals(theirs)


class TestCoilConstruction:
    def test_a_compressed_tape_reads_compressed(self):
        close, high, low = coil_tape(quiet=45)
        comp = ig.coil_compression(close, high, low)
        assert bool(comp["X"].iloc[-1]) is True
        assert int(ig.compressed_bars(comp)["X"].iloc[-1]) == 21

    def test_a_never_compressed_tape_reads_uncompressed(self):
        close, high, low = coil_tape(quiet=0)
        comp = ig.coil_compression(close, high, low)
        assert bool(comp["X"].iloc[-1]) is False
        assert int(ig.compressed_bars(comp)["X"].iloc[-1]) == 0

    def test_partial_run_counts_bars_rather_than_saturating(self):
        """A 0/21 count would also be produced by a broken detector; a fixture whose count is
        strictly between the bounds pins that the field is a real count."""
        close, high, low = coil_tape(quiet=30)
        bars = int(ig.compressed_bars(ig.coil_compression(close, high, low))["X"].iloc[-1])
        assert 0 < bars < ig.COMP_LOOKBACK, bars

    def test_cold_bars_read_False_not_null(self):
        """WHY the history floors exist. `coil_compression` is a boolean AND, so a warming-up
        ATR percentile yields False, never NaN. A caller that skipped the floor would record a
        confident 'not compressed' for a name with no measurable history."""
        close, high, low = coil_tape(quiet=45)
        short = ig.coil_compression(close.head(60), high.head(60), low.head(60))
        assert short["X"].notna().all(), "boolean frame: cold bars do NOT surface as NaN"
        assert not bool(short["X"].iloc[-1])

    def test_the_floor_is_where_a_truncated_read_stops_lying(self):
        """Below the floor, truncation changes the answer; at and above it, the tail read equals
        the full-history read."""
        close, high, low = coil_tape(n=700, quiet=45)
        full = ig.compressed_bars(ig.coil_compression(close, high, low))["X"].iloc[-1]
        disagree = []
        for L in range(270, ig.COIL_MIN_SESSIONS + 6):
            b = ig.compressed_bars(
                ig.coil_compression(close.tail(L), high.tail(L), low.tail(L)))["X"].iloc[-1]
            if b != full:
                disagree.append(L)
        assert disagree, "vacuous: truncation never changed the answer on this fixture"
        assert max(disagree) < ig.COIL_MIN_SESSIONS, (
            f"COIL_MIN_SESSIONS={ig.COIL_MIN_SESSIONS} does not clear the corrupting tail "
            f"lengths {disagree[-3:]}")


class TestThrustConstruction:
    IDX = pd.bdate_range("2025-01-01", periods=60)

    def _basket(self, k: int, *, jump: bool) -> tuple[pd.DataFrame, pd.DataFrame]:
        """`k` members flat at 100 (nobody above their 20d high), optionally all stepping up on
        the FINAL bar so the above-20d-high fraction crosses 0 -> 1.0."""
        cols = {}
        for i in range(k):
            v = np.full(len(self.IDX), 100.0)
            if jump:
                v[-1] = 130.0
            cols[f"M{i}"] = v
        close = pd.DataFrame(cols, index=self.IDX)
        return close, close.copy()

    def test_a_thrusting_basket_fires_on_the_thrust_bar(self):
        close, high = self._basket(8, jump=True)
        frac = ig.above_20d_high(close, high).sum(axis=1) / 8.0
        assert float(frac.iloc[-1]) == 1.0
        assert bool(ig.thrust_fired(frac).iloc[-1]) is True

    def test_a_quiet_basket_does_not_fire(self):
        close, high = self._basket(8, jump=False)
        frac = ig.above_20d_high(close, high).sum(axis=1) / 8.0
        assert float(frac.iloc[-1]) == 0.0
        assert bool(ig.thrust_fired(frac).iloc[-1]) is False

    def test_the_second_bar_of_a_thrust_is_debounced_to_quiet(self):
        """The de-bounce is deliberate: #4564 graded coiled members ON the thrust bar, so a
        standing 'fraction is high' state would accrue a population it never measured."""
        idx = pd.bdate_range("2025-01-01", periods=40)
        frac = pd.Series([0.0] * 30 + [0.1, 0.1, 0.1, 0.1, 0.1, 0.9, 0.9, 0.9, 0.9, 0.9],
                         index=idx)
        fired = ig.thrust_fired(frac)
        first = int(np.argmax(fired.to_numpy()))
        assert bool(fired.iloc[first]) is True
        assert not bool(fired.iloc[first + 1]), "the run's second bar must de-bounce to quiet"
        assert int(fired.sum()) == 1

    def test_a_fraction_that_never_dipped_low_does_not_fire(self):
        """Both legs are required: high NOW is not a thrust without the recent low."""
        frac = pd.Series([0.6] * 40, index=pd.bdate_range("2025-01-01", periods=40))
        assert int(ig.thrust_fired(frac).sum()) == 0
