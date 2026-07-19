"""tests/test_fractal_pivot_signals.py — unit tests for engine/fractal_pivot_signals.py.

ISOLATION CONTRACT
------------------
All fixtures are synthetic in-memory DataFrames. No data/ or site/ files are
read or written.  MM_DATA_GUARD will kill any test that reaches those paths.

KEY PROPERTY TESTED
-------------------
Causality / no-repaint: for every signal function, computing on df.iloc[:k]
must produce the identical prefix as computing on the full df.  This is the
classic Williams Fractal repaint trap — the confirmation-bar design exists
specifically to satisfy it, and these tests confirm it.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine.fractal_pivot_signals import (
    SIGNALS,
    _confirmed_fractals,
    fractal_break_dn,
    fractal_break_up,
    fractal_high_confirm,
    fractal_low_confirm,
    swing_downtrend,
    swing_uptrend,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_df(
    close: list[float],
    high: list[float] | None = None,
    low: list[float] | None = None,
) -> pd.DataFrame:
    """Build a minimal OHLCV DataFrame (no open column)."""
    n = len(close)
    c = np.array(close, dtype=float)
    h = np.array(high, dtype=float) if high is not None else c + 0.5
    l = np.array(low, dtype=float) if low is not None else c - 0.5
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    return pd.DataFrame({"close": c, "high": h, "low": l}, index=idx)


def _all_signals():
    return [
        fractal_low_confirm,
        fractal_high_confirm,
        swing_uptrend,
        swing_downtrend,
        fractal_break_up,
        fractal_break_dn,
    ]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def monotonic_up():
    """Strictly rising close (and high/low)."""
    closes = [float(i) for i in range(1, 31)]
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]
    return _make_df(closes, highs, lows)


@pytest.fixture
def monotonic_down():
    """Strictly falling close (and high/low)."""
    closes = [float(30 - i) for i in range(30)]
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]
    return _make_df(closes, highs, lows)


@pytest.fixture
def flat_tape():
    """All bars identical — zero-volatility tape."""
    closes = [10.0] * 30
    highs = [10.5] * 30
    lows = [9.5] * 30
    return _make_df(closes, highs, lows)


@pytest.fixture
def zero_range_bars():
    """High == Low == Close — zero-range (doji) bars."""
    closes = [10.0 + 0.1 * i for i in range(30)]
    return _make_df(closes, high=closes, low=closes)


@pytest.fixture
def gap_tape():
    """Tape with a large upward gap in the middle."""
    pre = [10.0 + 0.1 * i for i in range(15)]
    post = [20.0 + 0.1 * i for i in range(15)]
    closes = pre + post
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]
    return _make_df(closes, highs, lows)


@pytest.fixture
def reversal_tape():
    """Up-trend followed by a sharp down-trend with clear fractal pivots.

    Bars (0-indexed):
        0..9:  rising  (close = 10, 11, ..., 19)
        10:    peak at 25  (fractal high centre at bar 10, confirmed at bar 12)
        11:    19
        12:    18
        13..22: falling (close = 17, 16, ..., 8)
        23:    trough at 2  (fractal low centre at bar 23, confirmed at bar 25)
        24:    8
        25:    9
        26..29: rising  (close = 10, 11, 12, 13)
    """
    closes = (
        [10.0 + i for i in range(10)]   # bars 0-9 rising
        + [25.0, 19.0, 18.0]             # bars 10-12  peak at 10
        + [17.0 - i for i in range(10)]  # bars 13-22 falling
        + [2.0, 8.0, 9.0]                # bars 23-25  trough at 23
        + [10.0, 11.0, 12.0, 13.0]       # bars 26-29 rising
    )
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]
    # Fix the peak and trough highs/lows so fractals are unambiguous
    highs[10] = 25.5   # highest high at centre
    lows[23] = 1.5     # lowest low at centre
    return _make_df(closes, highs, lows)


# ---------------------------------------------------------------------------
# Basic property tests — all fixtures, all signals
# ---------------------------------------------------------------------------

ALL_TAPES = ["monotonic_up", "monotonic_down", "flat_tape", "zero_range_bars",
             "gap_tape", "reversal_tape"]


@pytest.mark.parametrize("tape_name", ALL_TAPES)
@pytest.mark.parametrize("fn", _all_signals(), ids=lambda f: f.__name__)
def test_no_nan(tape_name, fn, request):
    """No NaN values in any signal output."""
    df = request.getfixturevalue(tape_name)
    result = fn(df)
    assert not result.isna().any(), f"{fn.__name__} has NaN on {tape_name}"


@pytest.mark.parametrize("tape_name", ALL_TAPES)
@pytest.mark.parametrize("fn", _all_signals(), ids=lambda f: f.__name__)
def test_binary_values(tape_name, fn, request):
    """All signal outputs are in {0, 1} (int8 or int)."""
    df = request.getfixturevalue(tape_name)
    result = fn(df)
    unique = set(result.unique())
    assert unique <= {0, 1}, (
        f"{fn.__name__} on {tape_name}: unexpected values {unique - {0, 1}}"
    )


@pytest.mark.parametrize("tape_name", ALL_TAPES)
@pytest.mark.parametrize("fn", _all_signals(), ids=lambda f: f.__name__)
def test_index_aligned(tape_name, fn, request):
    """Signal output index matches input DataFrame index exactly."""
    df = request.getfixturevalue(tape_name)
    result = fn(df)
    assert result.index.equals(df.index), f"{fn.__name__} index mismatch on {tape_name}"


# ---------------------------------------------------------------------------
# Causality / no-repaint tests (the critical property)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fn", _all_signals(), ids=lambda f: f.__name__)
def test_causality_reversal_tape(fn, reversal_tape):
    """Truncation prefix: fn(df.iloc[:k]) == fn(df).iloc[:k] for several k values.

    This is the core repaint-free guarantee.  Williams Fractals computed naively
    on bar i require bars i+1 and i+2 (the right wings) — so a naive implementation
    would place the fire at bar i and recalculate when more bars arrive.  Our
    implementation places the fire at bar i+2 (the confirmation bar), so truncation
    never changes the prefix.
    """
    df = reversal_tape
    full = fn(df)
    for k in [5, 10, 15, 20, 25, len(df)]:
        prefix = fn(df.iloc[:k])
        assert prefix.iloc[:k].equals(full.iloc[:k]), (
            f"{fn.__name__}: prefix mismatch at k={k}\n"
            f"  full[:k]   = {list(full.iloc[:k])}\n"
            f"  prefix[:k] = {list(prefix.iloc[:k])}"
        )


@pytest.mark.parametrize("fn", _all_signals(), ids=lambda f: f.__name__)
def test_causality_monotonic_up(fn, monotonic_up):
    """Causality holds on monotonic-up tape."""
    df = monotonic_up
    full = fn(df)
    for k in [8, 16, 25]:
        prefix = fn(df.iloc[:k])
        assert prefix.iloc[:k].equals(full.iloc[:k])


# ---------------------------------------------------------------------------
# Fractal detection: hand-verifiable formula tests
# ---------------------------------------------------------------------------

def _minimal_fh_df():
    """Minimal 9-bar tape with a single obvious fractal HIGH at bar 4.

    Bars:   0    1    2    3    4    5    6    7    8
    High:  10   11   12   13   15   12   11   10    9
    Low:    9   10   11   12   14   11   10    9    8
    Close: 9.5 10.5 11.5 12.5 14.5 11.5 10.5  9.5  8.5

    Bar 4 high=15 > max(12,13)=13 AND 15 > max(12,11)=12 => fractal HIGH at bar 4.
    Confirmation bar = 4 + 2 = 6.
    """
    highs  = [10, 11, 12, 13, 15, 12, 11, 10,  9]
    lows   = [ 9, 10, 11, 12, 14, 11, 10,  9,  8]
    closes = [9.5, 10.5, 11.5, 12.5, 14.5, 11.5, 10.5, 9.5, 8.5]
    return _make_df(closes, highs, lows)


def _minimal_fl_df():
    """Minimal 9-bar tape with a single obvious fractal LOW at bar 4.

    Bars:   0    1    2    3    4    5    6    7    8
    High:  15   14   13   12   10   12   13   14   15
    Low:   14   13   12   11    9   11   12   13   14
    Close: 14.5 13.5 12.5 11.5  9.5 11.5 12.5 13.5 14.5

    Bar 4 low=9 < min(12,11)=11 AND 9 < min(11,12)=11 => fractal LOW at bar 4.
    Confirmation bar = 4 + 2 = 6.
    """
    highs  = [15, 14, 13, 12, 10, 12, 13, 14, 15]
    lows   = [14, 13, 12, 11,  9, 11, 12, 13, 14]
    closes = [14.5, 13.5, 12.5, 11.5, 9.5, 11.5, 12.5, 13.5, 14.5]
    return _make_df(closes, highs, lows)


def test_fractal_high_fires_at_confirmation_bar():
    """fractal_high_confirm must fire at bar 6 (= pivot bar 4 + 2)."""
    df = _minimal_fh_df()
    result = fractal_high_confirm(df)
    # Bar 6 should be 1; all others should be 0
    assert result.iloc[6] == 1, f"Expected fire at bar 6, got {list(result)}"
    assert result.iloc[:6].sum() == 0, f"Pre-confirmation fires: {list(result[:6])}"
    assert result.iloc[7:].sum() == 0, f"Post-confirmation fires: {list(result[7:])}"


def test_fractal_low_fires_at_confirmation_bar():
    """fractal_low_confirm must fire at bar 6 (= pivot bar 4 + 2)."""
    df = _minimal_fl_df()
    result = fractal_low_confirm(df)
    assert result.iloc[6] == 1, f"Expected fire at bar 6, got {list(result)}"
    assert result.iloc[:6].sum() == 0
    assert result.iloc[7:].sum() == 0


def test_fractal_high_tie_breaks_false():
    """Ties on the pivot centre must NOT form a fractal (strict > required)."""
    # Bar 4 high == bar 3 high (tie on the left) — should NOT be a fractal
    highs  = [10, 11, 13, 13, 13, 12, 11, 10,  9]
    lows   = [ 9, 10, 12, 12, 12, 11, 10,  9,  8]
    closes = [9.5, 10.5, 12.5, 12.5, 12.5, 11.5, 10.5, 9.5, 8.5]
    df = _make_df(closes, highs, lows)
    result = fractal_high_confirm(df)
    assert result.sum() == 0, f"Tie should suppress fractal; got fires at {list(result.nonzero()[0])}"


def test_fractal_low_tie_breaks_false():
    """Ties on the pivot centre must NOT form a fractal (strict < required)."""
    highs  = [15, 14, 12, 12, 12, 12, 13, 14, 15]
    lows   = [14, 13, 11, 11, 11, 11, 12, 13, 14]
    closes = [14.5, 13.5, 11.5, 11.5, 11.5, 11.5, 12.5, 13.5, 14.5]
    df = _make_df(closes, highs, lows)
    result = fractal_low_confirm(df)
    assert result.sum() == 0, f"Tie should suppress fractal; got fires at {list(result.nonzero()[0])}"


# ---------------------------------------------------------------------------
# Warm-up / short-tape edge cases
# ---------------------------------------------------------------------------

def test_short_tape_no_fire():
    """A tape of 4 bars is too short to confirm any fractal (need >=5 bars)."""
    df = _make_df([10.0, 11.0, 10.0, 9.0],
                  high=[10.5, 12.0, 10.5, 9.5],
                  low=[9.5, 10.5, 9.5, 8.5])
    for fn in _all_signals():
        result = fn(df)
        assert result.sum() == 0, f"{fn.__name__} fired on 4-bar tape"


def test_exactly_5_bars():
    """Exactly 5 bars: only bar index 4 can be a confirmation bar (pivot at 2)."""
    # Fractal HIGH at bar 2: high[2] > max(high[0],high[1]) AND high[2] > max(high[3],high[4])
    highs  = [10, 11, 15, 12, 11]
    lows   = [ 9, 10, 14, 11, 10]
    closes = [9.5, 10.5, 14.5, 11.5, 10.5]
    df = _make_df(closes, highs, lows)
    result = fractal_high_confirm(df)
    assert result.iloc[4] == 1, f"Expected fire at bar 4, got {list(result)}"
    assert result.iloc[:4].sum() == 0


# ---------------------------------------------------------------------------
# Monotonic tapes: no events expected
# ---------------------------------------------------------------------------

def test_monotonic_up_no_fractal_high(monotonic_up):
    """Strictly rising highs cannot produce any fractal HIGH."""
    result = fractal_high_confirm(monotonic_up)
    assert result.sum() == 0


def test_monotonic_up_no_fractal_low(monotonic_up):
    """Strictly rising lows cannot produce any fractal LOW (monotonic lows too)."""
    result = fractal_low_confirm(monotonic_up)
    assert result.sum() == 0


def test_monotonic_down_no_fractal_low(monotonic_down):
    """Strictly falling lows cannot produce any fractal LOW."""
    result = fractal_low_confirm(monotonic_down)
    assert result.sum() == 0


def test_monotonic_down_no_fractal_high(monotonic_down):
    """Strictly falling highs cannot produce any fractal HIGH."""
    result = fractal_high_confirm(monotonic_down)
    assert result.sum() == 0


# ---------------------------------------------------------------------------
# Flat tape: no fractals (ties suppress)
# ---------------------------------------------------------------------------

def test_flat_tape_no_events(flat_tape):
    """Flat tape has all bars equal — ties suppress all fractals."""
    for fn in [fractal_low_confirm, fractal_high_confirm]:
        result = fn(flat_tape)
        assert result.sum() == 0, f"{fn.__name__} fired on flat tape"


# ---------------------------------------------------------------------------
# Swing structure state tests
# ---------------------------------------------------------------------------

def _hh_hl_tape():
    """Tape engineered to produce classic HH/HL (uptrend) confirmed structure.

    Two fractal lows (rising) and two fractal highs (rising).

    Fractal LOW 1: centre at bar 2  => confirmed at bar 4
    Fractal HIGH 1: centre at bar 6 => confirmed at bar 8
    Fractal LOW 2: centre at bar 10 => confirmed at bar 12
    Fractal HIGH 2: centre at bar 14 => confirmed at bar 16

    Swing uptrend should be 1 from bar 16 onward.
    """
    #          0     1     2     3     4     5     6     7     8     9    10    11    12    13    14    15    16    17    18    19
    highs  = [12.0, 11.0,  8.0, 10.5, 11.0, 13.0, 16.0, 15.0, 14.0, 15.0, 11.0, 13.0, 14.0, 17.0, 20.0, 18.0, 17.0, 18.0, 19.0, 20.0]
    lows   = [11.0, 10.0,  7.0,  9.5, 10.0, 12.0, 15.0, 14.0, 13.0, 14.0, 10.0, 12.0, 13.0, 16.0, 19.0, 17.0, 16.0, 17.0, 18.0, 19.0]
    closes = [11.5, 10.5,  7.5, 10.0, 10.5, 12.5, 15.5, 14.5, 13.5, 14.5, 10.5, 12.5, 13.5, 16.5, 19.5, 17.5, 16.5, 17.5, 18.5, 19.5]
    return _make_df(closes, highs, lows)


def test_swing_uptrend_fires_after_second_pair():
    """swing_uptrend must be 1 only after two HH+HL pairs are confirmed."""
    df = _hh_hl_tape()
    result = swing_uptrend(df)
    # Must be 0 before both pairs confirmed (before bar 16)
    assert result.iloc[:16].sum() == 0, (
        f"Early uptrend fires: bars {list(np.where(result.iloc[:16])[0])}"
    )
    # Must be 1 from bar 16 onward (HH+HL confirmed)
    assert result.iloc[16] == 1, f"swing_uptrend not 1 at bar 16"


def test_swing_downtrend_not_active_on_uptrend_tape():
    """swing_downtrend must be 0 throughout an uptrend tape."""
    df = _hh_hl_tape()
    result = swing_downtrend(df)
    assert result.sum() == 0, f"swing_downtrend fired on uptrend tape at bars {list(np.where(result)[0])}"


# ---------------------------------------------------------------------------
# Fractal break events
# ---------------------------------------------------------------------------

def test_fractal_break_up_fires_once_per_level():
    """fractal_break_up fires exactly once per confirmed fractal HIGH level."""
    # Fractal HIGH at bar 4 (high=15), confirmed at bar 6 (price=15).
    # Bars 7,8 both close above 15 — but only bar 7 should fire (first cross).
    highs  = [10, 11, 12, 13, 15, 14, 13, 16, 17]
    lows   = [ 9, 10, 11, 12, 14, 13, 12, 15, 16]
    closes = [9.5, 10.5, 11.5, 12.5, 14.5, 13.5, 12.5, 16.0, 17.0]
    df = _make_df(closes, highs, lows)

    result = fractal_break_up(df)
    fires = list(np.where(result)[0])
    assert len(fires) == 1, f"Expected 1 fire, got fires at bars {fires}"
    # The first bar above the level (15) after confirmation (bar 6) is bar 7
    assert fires[0] == 7, f"Expected fire at bar 7, got {fires}"


def test_fractal_break_dn_fires_once_per_level():
    """fractal_break_dn fires exactly once per confirmed fractal LOW level."""
    # Fractal LOW at bar 4 (low=5), confirmed at bar 6.
    # Bars 7,8 both close below 5 — only bar 7 should fire.
    highs  = [15, 14, 13, 12, 10, 12, 13, 14, 15]
    lows   = [14, 13, 12, 11,  5, 11, 12,  4,  3]
    closes = [14.5, 13.5, 12.5, 11.5, 5.5, 11.5, 12.5, 4.0, 3.0]
    df = _make_df(closes, highs, lows)

    result = fractal_break_dn(df)
    fires = list(np.where(result)[0])
    assert len(fires) == 1, f"Expected 1 fire, got fires at bars {fires}"
    assert fires[0] == 7, f"Expected fire at bar 7, got {fires}"


def test_fractal_break_up_no_fire_before_confirmation():
    """fractal_break_up must not fire before the confirmation bar."""
    # Fractal HIGH at bar 4 confirmed at bar 6; bar 5 might close above the level,
    # but that bar precedes confirmation so it should not fire.
    highs  = [10, 11, 12, 13, 15, 12, 11, 16, 17]
    lows   = [ 9, 10, 11, 12, 14, 11, 10, 15, 16]
    closes = [9.5, 10.5, 11.5, 12.5, 14.5, 16.0, 12.5, 16.0, 17.0]
    df = _make_df(closes, highs, lows)

    result = fractal_break_up(df)
    # Before confirmation bar (bar 6), no fire allowed
    assert result.iloc[:6].sum() == 0, (
        f"fractal_break_up fired before confirmation: {list(np.where(result.iloc[:6])[0])}"
    )


# ---------------------------------------------------------------------------
# SIGNALS registry completeness
# ---------------------------------------------------------------------------

def test_signals_keys():
    """SIGNALS dict must contain all 6 specified keys."""
    expected = {
        "fractal_low_confirm",
        "fractal_high_confirm",
        "swing_uptrend",
        "swing_downtrend",
        "fractal_break_up",
        "fractal_break_dn",
    }
    assert set(SIGNALS.keys()) == expected


def test_signals_required_fields():
    """Every SIGNALS entry must have all required fields."""
    required_legacy = {"fn", "kind", "family", "direction", "default_params", "display", "glyph"}
    required_new = {"dependency_family", "role", "entry_stack_blocked", "challenger_only",
                    "provenance", "actionable_lag"}
    for name, meta in SIGNALS.items():
        missing_legacy = required_legacy - meta.keys()
        assert not missing_legacy, f"{name} missing legacy keys: {missing_legacy}"
        missing_new = required_new - meta.keys()
        assert not missing_new, f"{name} missing new metadata keys: {missing_new}"


def test_signals_display_bilingual():
    """Every display dict must have 'en' and 'zh' keys with non-empty strings."""
    for name, meta in SIGNALS.items():
        disp = meta["display"]
        assert "en" in disp and disp["en"], f"{name} missing English display"
        assert "zh" in disp and disp["zh"], f"{name} missing Chinese display"


def test_signals_directions():
    """Check the direction values match the spec."""
    assert SIGNALS["fractal_low_confirm"]["direction"] == +1
    assert SIGNALS["fractal_high_confirm"]["direction"] == -1
    assert SIGNALS["swing_uptrend"]["direction"] == +1
    assert SIGNALS["swing_downtrend"]["direction"] == -1
    assert SIGNALS["fractal_break_up"]["direction"] == +1
    assert SIGNALS["fractal_break_dn"]["direction"] == -1


def test_signals_kinds():
    """Events are 'event', states are 'state'."""
    assert SIGNALS["fractal_low_confirm"]["kind"] == "event"
    assert SIGNALS["fractal_high_confirm"]["kind"] == "event"
    assert SIGNALS["swing_uptrend"]["kind"] == "state"
    assert SIGNALS["swing_downtrend"]["kind"] == "state"
    assert SIGNALS["fractal_break_up"]["kind"] == "event"
    assert SIGNALS["fractal_break_dn"]["kind"] == "event"


def test_signals_actionable_lag():
    """All entries must declare actionable_lag == 2."""
    for name, meta in SIGNALS.items():
        assert meta["actionable_lag"] == 2, f"{name} has wrong actionable_lag"


def test_signals_challenger_only_false():
    """challenger_only must be False for all entries."""
    for name, meta in SIGNALS.items():
        assert meta["challenger_only"] is False, f"{name} has challenger_only=True"


# ---------------------------------------------------------------------------
# Reversal tape: end-to-end integration
# ---------------------------------------------------------------------------

def test_reversal_tape_fractal_high_confirm(reversal_tape):
    """On the reversal tape, fractal HIGH at bar 10 confirms at bar 12."""
    result = fractal_high_confirm(reversal_tape)
    # Bar 10 is the peak (high=25.5); bar 12 is the confirmation bar
    assert result.iloc[12] == 1, (
        f"Expected fractal_high_confirm at bar 12, got {list(result)}"
    )


def test_reversal_tape_fractal_low_confirm(reversal_tape):
    """On the reversal tape, fractal LOW at bar 23 confirms at bar 25."""
    result = fractal_low_confirm(reversal_tape)
    assert result.iloc[25] == 1, (
        f"Expected fractal_low_confirm at bar 25, got {list(result)}"
    )


def test_reversal_tape_causality_critical(reversal_tape):
    """Critical causality check on reversal tape: prefix at k=13 must equal full prefix.

    This specifically verifies that the confirmation at bar 12 does NOT appear if we
    truncate before bar 12 (k <= 12).  It also verifies that once bar 12 is included
    (k=13), the fire is stable and does not vanish on extension.
    """
    df = reversal_tape

    # Truncating to k=12 means bar 12 is not in the window: no fire should appear
    partial_12 = fractal_high_confirm(df.iloc[:12])
    assert partial_12.sum() == 0, (
        f"Fractal HIGH fired before confirmation bar on k=12 prefix: {list(partial_12)}"
    )

    # Including bar 12 (k=13): fire appears at index 12
    partial_13 = fractal_high_confirm(df.iloc[:13])
    assert partial_13.iloc[12] == 1, (
        f"Fractal HIGH at bar 12 missing on k=13 prefix: {list(partial_13)}"
    )

    # Full computation agrees with partial at k=13
    full = fractal_high_confirm(df)
    assert full.iloc[:13].equals(partial_13.iloc[:13])
