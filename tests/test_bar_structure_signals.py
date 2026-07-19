"""tests/test_bar_structure_signals.py — Bar structure grammar + TheSTRAT signals.

Covers:
  - Formula correctness on hand-computable synthetic tapes
  - Causality: signal[:k] identical when computed on df[:k]
  - Events are 0/1 integers; states are 0/1 integers
  - No NaN in output
  - SIGNALS dict shape (required keys present)
  - Fixture coverage: monotonic-up, monotonic-down, flat, zero-range, gap, reversal
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine.bar_structure_signals import (
    SIGNALS,
    ib_setup,
    ob_expansion,
    obib_coil,
    triple_ib_coil,
    strat_212_bull,
    strat_212_bear,
    strat_rev_bull,
    strat_rev_bear,
    strat_312_bull,
    strat_312_bear,
)

# ---------------------------------------------------------------------------
# Synthetic tape builders
# ---------------------------------------------------------------------------

def _make_df(highs, lows, closes=None, volumes=None):
    """Build a minimal OHLCV DataFrame from high/low arrays (no open column)."""
    n = len(highs)
    highs = np.asarray(highs, dtype=float)
    lows = np.asarray(lows, dtype=float)
    if closes is None:
        closes = (highs + lows) / 2.0
    else:
        closes = np.asarray(closes, dtype=float)
    if volumes is None:
        volumes = np.ones(n) * 1e6
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.DataFrame(
        {"high": highs, "low": lows, "close": closes, "volume": volumes},
        index=idx,
    )


def _mono_up(n=20):
    """Monotonically rising tape: each bar makes a higher high and higher low."""
    highs = np.arange(1.0, n + 1) + 1.0   # 2, 3, 4, ...
    lows  = np.arange(1.0, n + 1)          # 1, 2, 3, ...
    return _make_df(highs, lows)


def _mono_dn(n=20):
    """Monotonically falling tape: each bar makes a lower high and lower low."""
    base = np.arange(float(n), 0.0, -1.0)   # n, n-1, ..., 1
    highs = base + 1.0
    lows  = base
    return _make_df(highs, lows)


def _flat(n=20):
    """Flat tape: every bar has the same high and low (all inside bars after bar 0,
    technically equal so they do NOT qualify as strict inside bars per the
    definition H < prevH AND L > prevL)."""
    highs = np.ones(n) * 10.0
    lows  = np.ones(n) * 9.0
    return _make_df(highs, lows)


def _zero_range(n=10):
    """Zero-range bars: high == low (doji-like)."""
    price = np.ones(n) * 5.0
    return _make_df(price, price)


def _gap_tape():
    """Tape with a gap bar: bar 3 has a high far above bar 2."""
    highs  = [10, 11, 12, 20, 13, 14, 15]
    lows   = [ 9, 10, 11, 18, 12, 13, 14]
    return _make_df(highs, lows)


def _reversal_tape():
    """A tape that goes up then reverses sharply down."""
    highs = [10, 11, 12, 13, 14,  8, 7, 6, 5, 4]
    lows  = [ 9, 10, 11, 12, 13,  6, 5, 4, 3, 2]
    return _make_df(highs, lows)


# ---------------------------------------------------------------------------
# Helper: all registered signal IDs
# ---------------------------------------------------------------------------
ALL_SIGNAL_IDS = list(SIGNALS.keys())

EXPECTED_SIGNALS = [
    "ib_setup", "ob_expansion", "obib_coil", "triple_ib_coil",
    "strat_212_bull", "strat_212_bear",
    "strat_rev_bull", "strat_rev_bear",
    "strat_312_bull", "strat_312_bear",
]


# ---------------------------------------------------------------------------
# Registration / SIGNALS dict shape
# ---------------------------------------------------------------------------

def test_all_signals_present():
    assert set(EXPECTED_SIGNALS) == set(ALL_SIGNAL_IDS), (
        f"Missing: {set(EXPECTED_SIGNALS) - set(ALL_SIGNAL_IDS)}, "
        f"Extra: {set(ALL_SIGNAL_IDS) - set(EXPECTED_SIGNALS)}"
    )


@pytest.mark.parametrize("sid", EXPECTED_SIGNALS)
def test_signal_dict_required_keys(sid):
    entry = SIGNALS[sid]
    required = {
        "fn", "kind", "family", "direction", "default_params",
        "display", "glyph",
        # new metadata keys
        "dependency_family", "role", "entry_stack_blocked",
        "challenger_only", "provenance", "actionable_lag",
    }
    missing = required - set(entry.keys())
    assert not missing, f"{sid} missing keys: {missing}"


@pytest.mark.parametrize("sid", EXPECTED_SIGNALS)
def test_signal_family(sid):
    assert SIGNALS[sid]["family"] == "bar_structure"
    assert SIGNALS[sid]["dependency_family"] == "pattern_structure"


@pytest.mark.parametrize("sid", EXPECTED_SIGNALS)
def test_signal_display_bilingual(sid):
    disp = SIGNALS[sid]["display"]
    assert "en" in disp and "zh" in disp
    assert disp["en"] and disp["zh"]


def test_directions():
    bull_events = {"strat_212_bull", "strat_rev_bull", "strat_312_bull"}
    bear_events = {"strat_212_bear", "strat_rev_bear", "strat_312_bear"}
    neutral = {"ib_setup", "ob_expansion", "obib_coil", "triple_ib_coil"}
    for sid in bull_events:
        assert SIGNALS[sid]["direction"] == +1, sid
    for sid in bear_events:
        assert SIGNALS[sid]["direction"] == -1, sid
    for sid in neutral:
        assert SIGNALS[sid]["direction"] == 0, sid


def test_kinds():
    states = {"ib_setup", "ob_expansion"}
    events = {
        "obib_coil", "triple_ib_coil",
        "strat_212_bull", "strat_212_bear",
        "strat_rev_bull", "strat_rev_bear",
        "strat_312_bull", "strat_312_bear",
    }
    for sid in states:
        assert SIGNALS[sid]["kind"] == "state", sid
    for sid in events:
        assert SIGNALS[sid]["kind"] == "event", sid


# ---------------------------------------------------------------------------
# Output shape + 0/1 constraint + no NaN
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sid", EXPECTED_SIGNALS)
@pytest.mark.parametrize("df_fn", [_mono_up, _mono_dn, _flat, _zero_range,
                                    _gap_tape, _reversal_tape])
def test_output_shape_no_nan_binary(sid, df_fn):
    df = df_fn() if callable(df_fn) else df_fn
    fn = SIGNALS[sid]["fn"]
    out = fn(df)
    assert len(out) == len(df), f"{sid} length mismatch"
    assert not out.isna().any(), f"{sid} contains NaN"
    assert set(out.unique()) <= {0, 1}, f"{sid} not binary: {set(out.unique())}"


# ---------------------------------------------------------------------------
# Causality: signal[:k] == fn(df[:k])[:k] for multiple k
# ---------------------------------------------------------------------------

def _causal_df():
    """A longer mixed tape for causality checks."""
    rng = np.random.default_rng(42)
    n = 50
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    noise = rng.uniform(0.3, 1.5, n)
    high = close + noise
    low  = close - noise
    return _make_df(high, low, closes=close)


@pytest.mark.parametrize("sid", EXPECTED_SIGNALS)
@pytest.mark.parametrize("k", [5, 15, 30])
def test_causality(sid, k):
    df = _causal_df()
    fn = SIGNALS[sid]["fn"]
    full = fn(df)
    prefix = fn(df.iloc[:k])
    # The first k values of the full signal must match the prefix computation
    pd.testing.assert_series_equal(
        full.iloc[:k].reset_index(drop=True),
        prefix.reset_index(drop=True),
        check_names=False,
        rtol=0,
    )


# ---------------------------------------------------------------------------
# ib_setup — correctness
# ---------------------------------------------------------------------------

def test_ib_setup_fires_on_inside_bars():
    # bar0: H=10, L=5   reference
    # bar1: H=9,  L=6   inside vs bar0 (9<10, 6>5)             -> ib_setup=1
    # bar2: H=11, L=4   outside vs bar1 (11>9, 4<6)            -> ib_setup=0
    # bar3: H=10, L=5   inside vs bar2 (10<11, 5>4)            -> ib_setup=1
    # bar4: H=12, L=5   two_up vs bar3 (12>10, L==prevL=5)     -> ib_setup=0
    # bar5: H=12, L=3   outside vs bar4                        -> ib_setup=0
    highs  = [10,  9, 11, 10, 12, 12]
    lows   = [ 5,  6,  4,  5,  5,  3]
    df = _make_df(highs, lows)
    s = ib_setup(df)
    assert s.iloc[0] == 0, "bar0 has no prior bar — must be 0"
    assert s.iloc[1] == 1, "bar1 is inside vs bar0 — must be 1"
    assert s.iloc[2] == 0, "bar2 is outside — must be 0"
    assert s.iloc[3] == 1, "bar3 is inside vs bar2 — must be 1"
    assert s.iloc[4] == 0, "bar4 is two_up (L==prevL, not strict) — must be 0"
    assert s.iloc[5] == 0, "bar5 is outside — must be 0"


def test_ib_setup_monotonic_up_no_inside():
    """On a monotonically rising tape each bar sets a new high/low — never inside."""
    df = _mono_up(20)
    s = ib_setup(df)
    assert s.sum() == 0


def test_ib_setup_flat_no_inside():
    """Equal high/low don't satisfy the STRICT inequalities."""
    df = _flat(10)
    s = ib_setup(df)
    assert s.sum() == 0


# ---------------------------------------------------------------------------
# ob_expansion — correctness
# ---------------------------------------------------------------------------

def test_ob_expansion_fires_on_outside_bars():
    highs  = [10, 9, 11, 10, 9]
    lows   = [ 5, 6,  4,  5, 4]
    df = _make_df(highs, lows)
    s = ob_expansion(df)
    assert s.iloc[0] == 0
    assert s.iloc[1] == 0   # inside bar
    assert s.iloc[2] == 1   # outside bar
    assert s.iloc[3] == 0
    assert s.iloc[4] == 0


def test_ob_monotonic_no_outside():
    """On a monotonically rising tape there are never outside bars (only two_up)."""
    df = _mono_up(20)
    assert ob_expansion(df).sum() == 0


# ---------------------------------------------------------------------------
# obib_coil — correctness
# ---------------------------------------------------------------------------

def test_obib_coil_fires_on_ob_then_ib():
    # bar0: H=10, L=5   (reference)
    # bar1: H=12, L=3   outside vs bar0  -> ob_expansion
    # bar2: H=11, L=4   inside vs bar1  (11<12, 4>3) -> obib_coil fires here
    # bar3: H=9,  L=5   inside vs bar2  (9<11, 5>4) -> NOT obib (prior was inside, not OB)
    highs  = [10, 12, 11,  9]
    lows   = [ 5,  3,  4,  5]
    df = _make_df(highs, lows)
    s = obib_coil(df)
    assert s.iloc[0] == 0
    assert s.iloc[1] == 0
    assert s.iloc[2] == 1, "bar2 is IB after OB — OBIB must fire"
    assert s.iloc[3] == 0, "bar3 is IB after IB — no OBIB"


def test_obib_requires_ob_prior():
    """An inside bar after a non-outside bar must NOT fire OBIB."""
    highs  = [10, 11, 10]   # bar1: two_up, bar2: inside (10<11, prev L)
    lows   = [ 5,  5,  6]   # bar1: L==prevL -> two_up not outside
    df = _make_df(highs, lows)
    s = obib_coil(df)
    assert s.sum() == 0


# ---------------------------------------------------------------------------
# triple_ib_coil — correctness
# ---------------------------------------------------------------------------

def test_triple_ib_coil_fires_on_third_consecutive_ib():
    # Design tape: bar0 reference, bars 1/2/3 all inside relative to prior
    # bar0: H=20, L=10
    # bar1: H=19, L=11  inside bar0
    # bar2: H=18, L=12  inside bar1
    # bar3: H=17, L=13  inside bar2  -> triple_ib_coil fires here
    # bar4: H=21, L=9   outside bar3 -> resets
    # bar5: H=20, L=10  inside bar4
    # bar6: H=19, L=11  inside bar5
    # -> triple not yet (only 2 consecutive)
    highs  = [20, 19, 18, 17, 21, 20, 19]
    lows   = [10, 11, 12, 13,  9, 10, 11]
    df = _make_df(highs, lows)
    s = triple_ib_coil(df)
    assert s.iloc[3] == 1, "bar3 is the 3rd consecutive IB — must fire"
    # bars 5,6 are only 2 consecutive IBs — should not fire
    assert s.iloc[5] == 0
    assert s.iloc[6] == 0


def test_triple_ib_coil_on_mono_up_zero():
    assert triple_ib_coil(_mono_up(20)).sum() == 0


# ---------------------------------------------------------------------------
# strat_212_bull — correctness
# ---------------------------------------------------------------------------

def test_strat_212_bull_fires_correctly():
    # Design tape:
    # bar0: H=10, L=5   reference
    # bar1: H=11, L=5   two_up (H>prevH=10, L==prevL=5 -> not lower)
    # bar2: H=10, L=6   inside bar1 (10<11, 6>5)
    # bar3: H=12, L=6   break above bar2 high (12 > 10) -> strat_212_bull fires
    highs  = [10, 11, 10, 12]
    lows   = [ 5,  5,  6,  6]
    df = _make_df(highs, lows)
    s = strat_212_bull(df)
    assert s.iloc[3] == 1, "bar3 breaks IB high after two_up→inside → must fire"
    assert s.iloc[0] == 0
    assert s.iloc[1] == 0
    assert s.iloc[2] == 0


def test_strat_212_bull_requires_break():
    # Same setup but bar3 does NOT break bar2 high
    # bar3: H=10 (== IB high, not strict break)
    highs  = [10, 11, 10, 10]
    lows   = [ 5,  5,  6,  6]
    df = _make_df(highs, lows)
    assert strat_212_bull(df).sum() == 0


# ---------------------------------------------------------------------------
# strat_212_bear — correctness
# ---------------------------------------------------------------------------

def test_strat_212_bear_fires_correctly():
    # bar0: H=10, L=5
    # bar1: H=10, L=4   two_dn (L<prevL=5, H<=prevH=10)
    # bar2: H=9,  L=5   inside bar1 (9<10, 5>4)
    # bar3: H=9,  L=3   break below bar2 low (3 < 5) -> strat_212_bear fires
    highs  = [10, 10,  9,  9]
    lows   = [ 5,  4,  5,  3]
    df = _make_df(highs, lows)
    s = strat_212_bear(df)
    assert s.iloc[3] == 1, "bar3 breaks IB low after two_dn→inside → must fire"
    assert s.iloc[0] == 0
    assert s.iloc[1] == 0
    assert s.iloc[2] == 0


# ---------------------------------------------------------------------------
# strat_rev_bull — correctness
# ---------------------------------------------------------------------------

def test_strat_rev_bull_fires_correctly():
    # bar0: H=10, L=5
    # bar1: H=10, L=4   two_dn
    # bar2: H=9,  L=5   inside bar1
    # bar3: H=12, L=5   break ABOVE IB high (12>9) -> strat_rev_bull fires
    highs  = [10, 10,  9, 12]
    lows   = [ 5,  4,  5,  5]
    df = _make_df(highs, lows)
    s = strat_rev_bull(df)
    assert s.iloc[3] == 1, "bar3 breaks IB high after two_dn→inside → reversal bull"


# ---------------------------------------------------------------------------
# strat_rev_bear — correctness
# ---------------------------------------------------------------------------

def test_strat_rev_bear_fires_correctly():
    # bar0: H=10, L=5
    # bar1: H=11, L=5   two_up
    # bar2: H=10, L=6   inside bar1
    # bar3: H=10, L=3   break BELOW IB low (3<6) -> strat_rev_bear fires
    highs  = [10, 11, 10, 10]
    lows   = [ 5,  5,  6,  3]
    df = _make_df(highs, lows)
    s = strat_rev_bear(df)
    assert s.iloc[3] == 1, "bar3 breaks IB low after two_up→inside → reversal bear"


# ---------------------------------------------------------------------------
# strat_312_bull — correctness
# ---------------------------------------------------------------------------

def test_strat_312_bull_fires_correctly():
    # bar0: H=10, L=5
    # bar1: H=12, L=3   outside (H>10, L<5)
    # bar2: H=11, L=4   inside bar1 (11<12, 4>3)
    # bar3: H=13, L=4   break above bar2 high (13>11) -> strat_312_bull fires
    highs  = [10, 12, 11, 13]
    lows   = [ 5,  3,  4,  4]
    df = _make_df(highs, lows)
    s = strat_312_bull(df)
    assert s.iloc[3] == 1, "bar3 breaks IB high after outside→inside → 312 bull"
    assert s.iloc[0] == 0
    assert s.iloc[1] == 0
    assert s.iloc[2] == 0


# ---------------------------------------------------------------------------
# strat_312_bear — correctness
# ---------------------------------------------------------------------------

def test_strat_312_bear_fires_correctly():
    # bar0: H=10, L=5
    # bar1: H=12, L=3   outside
    # bar2: H=11, L=4   inside bar1
    # bar3: H=11, L=2   break below bar2 low (2<4) -> strat_312_bear fires
    highs  = [10, 12, 11, 11]
    lows   = [ 5,  3,  4,  2]
    df = _make_df(highs, lows)
    s = strat_312_bear(df)
    assert s.iloc[3] == 1, "bar3 breaks IB low after outside→inside → 312 bear"


# ---------------------------------------------------------------------------
# Mutual exclusivity: 212_bull and 212_bear cannot fire on same bar
# ---------------------------------------------------------------------------

def test_212_bull_bear_mutually_exclusive():
    df = _causal_df()
    bull = strat_212_bull(df)
    bear = strat_212_bear(df)
    overlap = ((bull == 1) & (bear == 1)).sum()
    assert overlap == 0, f"212 bull and bear both fired on {overlap} bars"


def test_rev_bull_bear_mutually_exclusive():
    df = _causal_df()
    bull = strat_rev_bull(df)
    bear = strat_rev_bear(df)
    assert ((bull == 1) & (bear == 1)).sum() == 0


def test_312_bull_bear_mutually_exclusive():
    df = _causal_df()
    bull = strat_312_bull(df)
    bear = strat_312_bear(df)
    assert ((bull == 1) & (bear == 1)).sum() == 0


# ---------------------------------------------------------------------------
# ib_setup and ob_expansion mutually exclusive
# ---------------------------------------------------------------------------

def test_ib_ob_mutually_exclusive():
    df = _causal_df()
    assert ((ib_setup(df) == 1) & (ob_expansion(df) == 1)).sum() == 0


# ---------------------------------------------------------------------------
# Zero-range bars — no crash; inside bar definition requires STRICT inequalities
# ---------------------------------------------------------------------------

def test_zero_range_no_crash():
    df = _zero_range(10)
    for sid in EXPECTED_SIGNALS:
        out = SIGNALS[sid]["fn"](df)
        assert len(out) == len(df)
        assert not out.isna().any()


def test_zero_range_all_zero_states():
    """Zero-range bars cannot be inside (equal == not strict) or outside."""
    df = _zero_range(10)
    assert ib_setup(df).sum() == 0
    assert ob_expansion(df).sum() == 0


# ---------------------------------------------------------------------------
# Gap tape — no crash; gap bar becomes an outside bar most likely
# ---------------------------------------------------------------------------

def test_gap_tape_no_crash():
    df = _gap_tape()
    for sid in EXPECTED_SIGNALS:
        out = SIGNALS[sid]["fn"](df)
        assert len(out) == len(df)
        assert not out.isna().any()


# ---------------------------------------------------------------------------
# Reversal tape — events fire; no crash
# ---------------------------------------------------------------------------

def test_reversal_tape_no_crash():
    df = _reversal_tape()
    for sid in EXPECTED_SIGNALS:
        out = SIGNALS[sid]["fn"](df)
        assert len(out) == len(df)
        assert not out.isna().any()


# ---------------------------------------------------------------------------
# Events must be 0 on bar 0 (no prior bar)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sid", EXPECTED_SIGNALS)
def test_no_fire_on_first_bar(sid):
    df = _causal_df()
    out = SIGNALS[sid]["fn"](df)
    assert out.iloc[0] == 0, f"{sid} fired on first bar (no prior available)"


# ---------------------------------------------------------------------------
# Minimum-length DataFrame (2 bars) — no crash
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sid", EXPECTED_SIGNALS)
def test_two_bar_df_no_crash(sid):
    df = _make_df([10, 9], [5, 6])
    out = SIGNALS[sid]["fn"](df)
    assert len(out) == 2
    assert not out.isna().any()
