"""W-F — the flip-isolation construction behind the US reclaim-veto decision packet.

WHAT THIS PINS.  `research/prophet_us_audit/reclaim_veto_packet.py` claims that every row
it reports was refused SOLELY by the 200-day reclaim leg.  That claim rests on a two-part
predicate — the veto-ON stream BLOCKED the bar with the counter-trend reclaim reason AND
the veto-OFF stream TOOK the same bar — and the whole packet is worthless if either half
is wrong or redundant.  These tests exercise the REAL `engine.signal_quality._buy_filter`
for each physical case, so the predicate can never drift into a paraphrase of the engine
that agrees with itself.

THE TRAP THIS SUITE EXISTS FOR.  A name that fails the next-bar HOLD returns the SAME
string as one that fails the reclaim — both read "counter-trend, no 200-reclaim/hold" under
the default policy (see the `ok = held and reclaim` branch).  So filtering on the block
reason ALONE would silently sweep failed-hold bars into a packet that claims they were
refused by the reclaim leg.  The veto-OFF `take` half is what excludes them, and
`test_a_failed_hold_shares_the_block_reason...` below is the test that makes that half
load-bearing rather than decorative.

Sibling: tests/test_hk_reclaim_veto_policy.py pins the FLAG (defaults, blast radius, the
HK opt-out).  This file pins the MEASUREMENT built on top of it.  Synthetic series only —
no repo data, no network: a pin that drifts with the nightly panel cannot fail for the
right reason.

Run: python3 -m pytest tests/test_us_reclaim_veto_packet.py -q
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from engine import signal_quality as sq  # noqa: E402


def _load_packet():
    """Import the packet by path (it lives outside any package)."""
    cwd = os.getcwd()
    spec = importlib.util.spec_from_file_location(
        "reclaim_veto_packet",
        REPO / "research" / "prophet_us_audit" / "reclaim_veto_packet.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)          # module chdir()s to REPO at import
    os.chdir(cwd)
    return mod


PKT = _load_packet()


# --------------------------------------------------------------------------- #
# Part 1 — the three physical cases, driven through the REAL _buy_filter.
# `above200` varies per bar here (the HK sibling's frame is constant), because
# whether the name RECLAIMS is exactly a per-bar property of that column.
# --------------------------------------------------------------------------- #
def _frame(closes, above200_by_bar) -> pd.DataFrame:
    """Minimal signal-frame stand-in carrying only what _buy_filter reads.
    weekly_bull is False throughout: with above200[i] False that is the counter-trend
    branch — the only branch the reclaim leg governs."""
    return pd.DataFrame({
        "close": pd.Series(closes, dtype=float),
        "above200": pd.Series(above200_by_bar, dtype=bool),
        "w_bull": pd.Series([False] * len(closes), dtype=bool),
    })


def _both(sig, i=0, bear=False):
    """(_buy_filter under the shipped policy, under the loosened one)."""
    n = len(sig)
    return (sq._buy_filter(i, sig, bear, n, reclaim_veto=True),
            sq._buy_filter(i, sig, bear, n, reclaim_veto=False))


def test_holds_but_cannot_reclaim_in_two_bars_is_COUNTED():
    """THE case the packet is about: below the 200-day line, weekly-down, next bar closes
    higher (the hold passes) — and the line is still overhead at i+1 and i+2, so the
    reclaim cannot happen. Shipped policy refuses it; loosened policy takes it."""
    sig = _frame([100.0, 101.0, 101.5, 102.0], [False, False, False, False])
    (on_ok, on_reason), (off_ok, off_reason) = _both(sig)

    assert on_ok is False and on_reason == PKT.BLOCK_REASON, (
        "the packet's BLOCK_REASON constant no longer matches what the engine returns — "
        "the refusal filter would silently match nothing")
    assert off_ok is True, "the loosened policy must admit a counter-trend name that held"
    assert "200" not in off_reason, "the loosened branch must not claim a reclaim it never tested"

    # …and therefore the predicate counts it.
    on_m = [{"date": "2026-04-13", "quality": "block", "reason": on_reason}]
    off_m = [{"date": "2026-04-13", "quality": "take", "reason": off_reason}]
    assert PKT.reclaim_only_refusals(on_m, off_m) == ["2026-04-13"]


def test_a_name_that_reclaims_within_two_bars_is_NOT_counted():
    """Reclaiming at i+1 or i+2 satisfies the leg, so both policies TAKE the bar and there
    is no flip to report. Both reclaim positions are exercised — the engine ORs them, and a
    packet that counted either would be reporting an admission as a refusal."""
    for reclaim_at in (1, 2):
        above = [False, False, False, False]
        above[reclaim_at] = True
        sig = _frame([100.0, 101.0, 101.5, 102.0], above)
        (on_ok, on_reason), (off_ok, _) = _both(sig)

        assert on_ok is True, f"reclaim at i+{reclaim_at} must satisfy the shipped policy"
        assert on_reason == "reclaimed 200 & held"
        assert off_ok is True

        on_m = [{"date": "D", "quality": "take", "reason": on_reason}]
        off_m = [{"date": "D", "quality": "take", "reason": "held confirmation (counter-trend)"}]
        assert PKT.reclaim_only_refusals(on_m, off_m) == [], (
            f"an admitted name (reclaim at i+{reclaim_at}) leaked into the refusal set")


def test_a_failed_hold_shares_the_block_reason_so_the_reason_alone_is_not_the_isolation():
    """THE TRAP. `ok = held and reclaim` collapses BOTH failures into one string, so a name
    that failed the next-bar HOLD is refused with the identical reason. It must NOT enter a
    packet claiming the reclaim leg was the sole cause — the veto-OFF `take` half is what
    excludes it, and this test is what makes that half load-bearing."""
    sig = _frame([100.0, 99.0, 99.5, 100.5], [False, False, False, False])
    (on_ok, on_reason), (off_ok, off_reason) = _both(sig)

    assert on_ok is False
    assert on_reason == PKT.BLOCK_REASON, (
        "the failed-hold branch no longer shares the reclaim-failure string; if the engine "
        "now distinguishes them this test should be re-pointed, not deleted")
    assert off_ok is False and off_reason == "failed next-bar hold", (
        "dropping the reclaim leg is not 'admit everything' — the hold still gates")

    on_m = [{"date": "D", "quality": "block", "reason": on_reason}]
    off_m = [{"date": "D", "quality": "block", "reason": off_reason}]
    assert PKT.reclaim_only_refusals(on_m, off_m) == [], (
        "a failed HOLD was counted as a reclaim-leg refusal — the packet would overstate "
        "the veto's cost with bars the veto did not decide")


def test_the_bearish_divergence_veto_is_not_counted():
    """The other veto returns the same verdict under both policies, so it cannot produce a
    flip. Pinned anyway: it is the one other way a buy bar becomes a block."""
    sig = _frame([100.0, 101.0, 101.5, 102.0], [False, False, False, False])
    (on_ok, on_reason), (off_ok, off_reason) = _both(sig, bear=True)
    assert (on_ok, on_reason) == (off_ok, off_reason) == (False, "veto: bearish divergence")
    assert PKT.reclaim_only_refusals(
        [{"date": "D", "quality": "block", "reason": on_reason}],
        [{"date": "D", "quality": "block", "reason": off_reason}]) == []


def test_a_bar_too_near_the_end_is_pending_not_a_refusal():
    """With no bar i+2 the shipped policy cannot evaluate the reclaim and returns pending,
    so the last bars of a series can never be mistaken for refusals."""
    sig = _frame([100.0, 101.0], [False, False])
    on_ok, on_reason = sq._buy_filter(0, sig, False, len(sig), reclaim_veto=True)
    assert on_ok is None and on_reason == "pending confirmation"
    assert PKT.reclaim_only_refusals(
        [{"date": "D", "quality": "pending", "reason": on_reason}],
        [{"date": "D", "quality": "take", "reason": "held confirmation (counter-trend)"}]) == []


# --------------------------------------------------------------------------- #
# Part 2 — the predicate's own edges.
# --------------------------------------------------------------------------- #
def test_a_block_with_an_unrelated_reason_is_not_counted():
    """Only the counter-trend reclaim string qualifies. A block that flipped to take for
    some OTHER reason would mean the two runs differ by more than the one leg — that is a
    broken counterfactual, not a refusal, so it must not be silently absorbed."""
    assert PKT.reclaim_only_refusals(
        [{"date": "D", "quality": "block", "reason": "failed reclaim-and-hold"}],
        [{"date": "D", "quality": "take", "reason": "held confirmation"}]) == []


def test_dates_are_matched_pairwise_not_positionally():
    """The two marker streams can differ in length and ordering (a flip changes quality,
    and downstream sell/cut markers can shift). Matching must be by DATE."""
    on = [{"date": "A", "quality": "block", "reason": PKT.BLOCK_REASON},
          {"date": "B", "quality": "sell"},
          {"date": "C", "quality": "block", "reason": PKT.BLOCK_REASON}]
    off = [{"date": "C", "quality": "take", "reason": "held confirmation (counter-trend)"},
           {"date": "A", "quality": "block", "reason": PKT.BLOCK_REASON}]
    assert PKT.reclaim_only_refusals(on, off) == ["C"]


# --------------------------------------------------------------------------- #
# Part 3 — end to end through the real analyze(), and the no-look-ahead anchor.
# --------------------------------------------------------------------------- #
def _washout_series() -> pd.Series:
    """A washout shape that provably reaches the counter-trend branch: 260 bars up, a
    sustained ~35% slide that drags price under its own 200-day average with the weekly
    trend down, then a choppy base. Same construction as the HK sibling's fixture."""
    n_up, n_dn, n_base = 260, 150, 160
    t_up = np.arange(n_up)
    up = 100 + 0.22 * t_up + 3 * np.sin(t_up / 6)
    t_dn = np.arange(n_dn)
    dn = up[-1] - 0.42 * t_dn + 3.5 * np.sin(t_dn / 5)
    t_b = np.arange(n_base)
    base = dn[-1] + 4.5 * np.sin(t_b / 9) + 0.04 * t_b
    return pd.Series(np.concatenate([up, dn, base]),
                     index=pd.bdate_range("2023-01-02", periods=n_up + n_dn + n_base))


def test_end_to_end_the_predicate_finds_real_flips_and_every_one_is_a_true_flip():
    """Drives the REAL analyze() twice on one series. Two assertions that must BOTH hold:
    the predicate is not vacuous (it finds something on a series containing the branch),
    and everything it finds really is block-under-shipped / take-under-loosened."""
    close = _washout_series()
    on = sq.analyze("SYNTH", close, reclaim_veto=True)
    off = sq.analyze("SYNTH", close, reclaim_veto=False)
    flips = PKT.reclaim_only_refusals(on["markers"], off["markers"])

    assert flips, (
        "no flips on a 570-bar washout series — either the predicate is broken or this "
        "fixture no longer reaches the counter-trend branch (a vacuous packet)")

    on_by, off_by = {m["date"]: m for m in on["markers"]}, {m["date"]: m for m in off["markers"]}
    for d in flips:
        assert on_by[d]["quality"] == "block" and on_by[d]["reason"] == PKT.BLOCK_REASON
        assert off_by[d]["quality"] == "take"


def test_the_forward_anchor_is_never_the_marker_date():
    """MARKER-DATE GRADING IS FORBIDDEN (engine/signal_quality.py analyze docstring): the
    refusal needs the reclaim to have failed at BOTH i+1 and i+2, so it is knowable only at
    the close of 3D bar i+2. The anchor must therefore sit strictly after the marker — a
    packet anchored on the signal bar would book look-ahead as the veto's cost."""
    close = _washout_series()
    anchors = PKT.confirmation_anchors(close)
    assert anchors, "the anchor map came back empty — every fire would be dropped"

    labels = sorted(anchors)
    for label in labels:
        assert anchors[label] > label, (
            f"anchor {anchors[label].date()} is not strictly after marker bar {label.date()}")

    # …and it is the i+2 bar specifically, not merely "later": two 3D bars ahead is at
    # least 4 business days of separation, which a same-bar or i+1 anchor cannot reach.
    seps = [(anchors[d] - d).days for d in labels]
    assert min(seps) >= 4, f"anchor separation {min(seps)}d is too short to be the i+2 bar"


def test_the_packet_does_not_change_the_shipped_policy():
    """The whole instrument is decision INPUT. If assembling it ever flips a default, the
    board's admissions move on the strength of a research file — pinned here as well as in
    the HK sibling, because this module is the one that would be tempted to."""
    import inspect
    for fn in (sq._buy_filter, sq.analyze):
        assert inspect.signature(fn).parameters["reclaim_veto"].default is True
    src = (REPO / "research" / "prophet_us_audit" / "reclaim_veto_packet.py").read_text()
    assert "reclaim_veto=False" in src, "the packet must build the counterfactual"
    assert "signal_quality" in src and "def _buy_filter" not in src, (
        "the packet must CALL the engine, never reimplement the filter")
