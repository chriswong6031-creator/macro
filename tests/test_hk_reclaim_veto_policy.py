"""The HK `reclaim_veto=False` admission policy (operator ruling 2026-08-03).

WHAT THIS PINS.  `engine.signal_quality._buy_filter` gained a keyword-only
``reclaim_veto`` flag.  Default True = the validated US/CN behaviour; HK passes False
(``scripts.build_hk_library.HK_RECLAIM_VETO``) to drop ONE leg — the requirement that a
name both below its 200-day average AND weekly-down close back above that average within
2 bars.

WHY THE LEG WENT.  It is unsatisfiable by construction for a deep drawdown: a name 17%
below its 200-day line cannot close above it inside two sessions, so every buy signal it
fires is auto-blocked until it has already recovered — i.e. until the move is over.  It
produced 68% of HK rejections and blocked 0700/9988/1810/3690/2318 into +8.7%..+44% runs.
Measured on the committed HK panel, flipping the flag turns 6 of the 9 witness July
markers from `block` to `take` at their original signal dates.

The tests below are deliberately built on SYNTHETIC series rather than the live panel:
the panel moves nightly, and a pin that drifts with the data cannot fail for the right
reason.  Each case constructs the exact branch it means to exercise.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine import signal_gate, signal_quality as sq


# --------------------------------------------------------------------------- #
# A hand-built frame: we drive _buy_filter directly so each leg is isolated.
# --------------------------------------------------------------------------- #

def _frame(*, above200, weekly_bull, closes) -> pd.DataFrame:
    """Minimal signal-frame stand-in carrying only what _buy_filter reads."""
    n = len(closes)
    return pd.DataFrame({
        "close": pd.Series(closes, dtype=float),
        "above200": pd.Series([above200] * n, dtype=bool),
        "w_bull": pd.Series([weekly_bull] * n, dtype=bool),
    })


COUNTER_TREND = dict(above200=False, weekly_bull=False)   # the branch the flag governs


def test_counter_trend_name_that_follows_through_is_admitted_only_under_the_hk_policy():
    """THE headline case — Xiaomi-shaped: below its 200-day line, weekly-down, and the
    next bar closes higher.  Under the default it is blocked for not reclaiming a line it
    cannot reach; under the HK policy the next-bar follow-through is enough."""
    sig = _frame(closes=[100.0, 101.0, 101.5, 102.0], **COUNTER_TREND)

    hk_ok, hk_reason = sq._buy_filter(0, sig, False, len(sig), reclaim_veto=False)
    assert hk_ok is True
    assert "counter-trend" in hk_reason and "200" not in hk_reason, (
        "the loosened branch must not claim a reclaim it never tested")

    us_ok, us_reason = sq._buy_filter(0, sig, False, len(sig), reclaim_veto=True)
    assert us_ok is False
    assert us_reason == "counter-trend, no 200-reclaim/hold"


def test_the_hk_policy_still_requires_next_bar_follow_through():
    """Dropping the reclaim leg is NOT 'admit everything'.  A counter-trend name whose
    next bar closes LOWER stays blocked — BYD's real 07-06 case, which is why it did not
    join the unblocked six."""
    sig = _frame(closes=[100.0, 99.0, 99.5, 100.5], **COUNTER_TREND)
    ok, reason = sq._buy_filter(0, sig, False, len(sig), reclaim_veto=False)
    assert ok is False
    assert reason == "failed next-bar hold"


def test_the_bearish_divergence_veto_survives_both_policies():
    """The other veto is a different mechanism and was never what the operator pointed
    at — every blocked reason on the board read '200-day average'.  It must be untouched."""
    sig = _frame(closes=[100.0, 101.0, 101.5, 102.0], **COUNTER_TREND)
    for policy in (True, False):
        ok, reason = sq._buy_filter(0, sig, True, len(sig), reclaim_veto=policy)
        assert ok is False, f"divergence veto leaked with reclaim_veto={policy}"
        assert reason == "veto: bearish divergence"


@pytest.mark.parametrize("above200,weekly_bull", [(True, True), (True, False), (False, True)])
def test_non_counter_trend_branches_are_identical_under_both_policies(above200, weekly_bull):
    """The flag governs ONE branch.  Every name that is not both below-200 AND weekly-down
    must behave the same under either policy — otherwise the blast radius is wider than
    the ruling authorised."""
    sig = _frame(closes=[100.0, 101.0, 101.5, 102.0],
                 above200=above200, weekly_bull=weekly_bull)
    assert (sq._buy_filter(0, sig, False, len(sig), reclaim_veto=True)
            == sq._buy_filter(0, sig, False, len(sig), reclaim_veto=False))


# --------------------------------------------------------------------------- #
# The default must stay the default — US/CN ride on it.
# --------------------------------------------------------------------------- #

def test_every_entry_point_defaults_to_the_validated_policy():
    """`signal_quality` is imported by ~12 modules and `signal_gate.gate` is the US and CN
    inclusion gate.  If any of these defaults ever flips, two working boards change
    silently — so the default is pinned at every layer, not just the innermost one."""
    import inspect
    for fn in (sq._buy_filter, sq.analyze, signal_gate.gate):
        p = inspect.signature(fn).parameters["reclaim_veto"]
        assert p.default is True, f"{fn.__qualname__} no longer defaults to the validated policy"
        assert p.kind is inspect.Parameter.KEYWORD_ONLY, (
            f"{fn.__qualname__}.reclaim_veto must stay keyword-only — a positional flag "
            "would be silently settable by argument order")


def test_the_default_path_is_byte_identical_to_the_unparameterised_behaviour():
    """MUTATION-VISIBLE GUARD.  A real series through the whole stack: calling with no
    flag, with the explicit default, and the marker stream itself must agree.  If someone
    'simplifies' the branch so the default drifts, this fails."""
    # A WASHOUT shape, not a rising one: 260 bars up, then a sustained ~35% slide that
    # drags price under its own 200-day average with the weekly trend down, then a choppy
    # base.  That third act is the counter-trend branch this flag governs — a plain
    # uptrending fixture never enters it, and the assertion at the end of this test is
    # what catches that mistake.
    n_up, n_dn, n_base = 260, 150, 160
    t_up = np.arange(n_up)
    up = 100 + 0.22 * t_up + 3 * np.sin(t_up / 6)
    t_dn = np.arange(n_dn)
    dn = up[-1] - 0.42 * t_dn + 3.5 * np.sin(t_dn / 5)
    t_b = np.arange(n_base)
    base = dn[-1] + 4.5 * np.sin(t_b / 9) + 0.04 * t_b
    close = pd.Series(np.concatenate([up, dn, base]),
                      index=pd.bdate_range("2023-01-02", periods=n_up + n_dn + n_base))

    implicit = sq.analyze("SYNTH", close)
    explicit = sq.analyze("SYNTH", close, reclaim_veto=True)
    assert implicit == explicit

    loose = sq.analyze("SYNTH", close, reclaim_veto=False)
    # …and the loose policy must actually DO something on a series that contains the
    # branch, else these tests would pass on a no-op implementation.
    assert loose != implicit, (
        "reclaim_veto=False changed nothing on a 420-bar series — either the flag is not "
        "wired through analyze() or this fixture no longer exercises the counter-trend branch")


def test_hk_builder_is_the_only_caller_that_opts_out():
    """The opt-out is a named constant at one site, so the policy is greppable and its
    blast radius auditable."""
    from scripts import build_hk_library
    assert build_hk_library.HK_RECLAIM_VETO is False


def test_the_hk_era_stamp_moved_with_the_admission_change():
    """An admission change makes the old and new boards different products; the forward
    ledger must not pool them.  The stamp is the fence."""
    from engine import hk_board_rank
    assert hk_board_rank.BOARD_DEFINITION == "hk_prophet_v2"
