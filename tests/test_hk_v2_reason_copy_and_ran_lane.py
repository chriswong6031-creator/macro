"""hk_prophet_v2 follow-ups: honest block copy + the ran lane's above200 door.

Found by opening the FIRST hk_prophet_v2 artifact (site/factordata/hk_standouts.json,
as_of 2026-08-03) rather than trusting the green merge:

1. ``failed next-bar hold`` — a reason string the engine only started emitting once
   ``reclaim_veto=False`` shipped — had no entry in ``VETO_REASON_COPY``, so **10 of 12
   vetoed rows rendered the contentless fallback** "The entry gate refused this signal".
2. ``failed reclaim-and-hold`` rendered as "Reclaimed the 200-day average, then lost it
   again" on a branch of ``_buy_filter`` that tests ``held`` ALONE and never evaluates a
   reclaim — a specific, false narrative on a disclosure surface.
3. The ran lane required ``above200``, which a name recovering from a deep drawdown
   cannot satisfy by construction — the same impossible condition the removed veto
   imposed, re-entering through a different door.
"""
from __future__ import annotations

import inspect
import re

from engine import hk_board_rank, signal_quality, us_board_rank


# --------------------------------------------------------------------------- #
# 1 + 2 — every reason the engine can emit for a BLOCKED marker has plain copy
# --------------------------------------------------------------------------- #
def _block_reasons_from_engine() -> set[str]:
    """Reason literals `_buy_filter` returns alongside a FALSE take (= a block).

    Read off the source so a new engine reason string cannot be added without this
    test seeing it — the exact failure that shipped the contentless fallback.
    """
    src = inspect.getsource(signal_quality._buy_filter)
    literals = set(re.findall(r'"([^"]+)"', src))
    # take/pending outcomes are not block reasons
    drop = {"reclaimed 200 & held", "held confirmation", "pending confirmation",
            "held confirmation (counter-trend)"}
    return {s for s in literals
            if s not in drop and (s.startswith(("failed", "counter-trend", "veto:")))}


def test_every_block_reason_the_engine_emits_has_plain_word_copy():
    missing = sorted(r for r in _block_reasons_from_engine()
                     if r not in hk_board_rank.VETO_REASON_COPY)
    assert not missing, (
        f"these block reasons fall through to the contentless fallback: {missing}. "
        "A vetoed row that cannot say WHY is worse than no row.")


def test_the_new_counter_trend_reasons_are_covered():
    """The two strings `reclaim_veto=False` introduced — the ones that shipped bare."""
    for reason in ("failed next-bar hold", "held confirmation (counter-trend)"):
        assert reason in hk_board_rank.VETO_REASON_COPY, reason
        copy = hk_board_rank.VETO_REASON_COPY[reason]
        assert copy["en"] and copy["zh"]
        assert copy["en"] != hk_board_rank.VETO_REASON_FALLBACK["en"]


def test_no_block_copy_narrates_a_200day_event_its_branch_never_tested():
    """`failed reclaim-and-hold` and `failed next-bar hold` are returned by branches
    that test the NEXT-BAR HOLD only.  Neither may claim a 200-day round trip."""
    for reason in ("failed reclaim-and-hold", "failed next-bar hold"):
        en = hk_board_rank.VETO_REASON_COPY[reason]["en"].lower()
        zh = hk_board_rank.VETO_REASON_COPY[reason]["zh"]
        assert "reclaim" not in en and "200" not in en, (
            f"{reason!r} copy claims a reclaim its branch never evaluated: {en!r}")
        assert "200" not in zh and "收复" not in zh, zh


def test_the_reason_that_does_test_the_200day_line_still_says_so():
    """Guard the inverse: the counter-trend reason (reclaim_veto=True, the US/CN
    default) genuinely tests the 200-day average, so its copy must keep naming it —
    otherwise this suite would pass by stripping every mention everywhere."""
    en = hk_board_rank.VETO_REASON_COPY["counter-trend, no 200-reclaim/hold"]["en"]
    assert "200-day" in en, en


# --------------------------------------------------------------------------- #
# 3 — the ran lane's above200 door
# --------------------------------------------------------------------------- #
def _recovering_verdict(**over):
    """A washout-bounce name: cross lapsed, weekly structure up, still BELOW its
    200-day line because it fell 40% before bouncing (1810.HK-shaped)."""
    v = {"eligible": False, "ticks": 8, "above200": False, "weekly_bull": True}
    v.update(over)
    return v


def test_us_policy_still_excludes_a_below_200_name_from_the_ran_lane():
    """DEFAULT is unchanged behaviour — US/CN must be byte-identical."""
    assert us_board_rank.ran_admits(_recovering_verdict(), {"dir": "up"}) is False


def test_hk_policy_admits_the_recovering_name_the_us_policy_cannot_see():
    assert us_board_rank.ran_admits(
        _recovering_verdict(), {"dir": "up"}, require_above200=False) is True


def test_dropping_above200_does_not_drop_the_other_guards():
    """The relaxed lane still refuses: a live signal, an out-of-window age, a
    non-bullish weekly, and a marked-down row.  Loosening one door must not open
    the rest — that would turn the lane into an unfiltered dump."""
    kw = {"require_above200": False}
    row = {"dir": "up"}
    assert us_board_rank.ran_admits(_recovering_verdict(eligible=True), row, **kw) is False
    assert us_board_rank.ran_admits(_recovering_verdict(ticks=1), row, **kw) is False
    assert us_board_rank.ran_admits(_recovering_verdict(ticks=99), row, **kw) is False
    assert us_board_rank.ran_admits(_recovering_verdict(weekly_bull=False), row, **kw) is False
    assert us_board_rank.ran_admits(_recovering_verdict(weekly_bull=None), row, **kw) is False
    assert us_board_rank.ran_admits(_recovering_verdict(), {"dir": "down"}, **kw) is False


def test_the_hk_builder_actually_passes_the_relaxed_policy():
    """The parameter is worthless if the call site never sets it — the class of
    defect where half a board runs the old rule."""
    from scripts import build_hk_library

    assert build_hk_library.HK_RAN_REQUIRE_ABOVE200 is False
    src = inspect.getsource(build_hk_library)
    assert "require_above200=HK_RAN_REQUIRE_ABOVE200" in src, (
        "the HK ran-lane call site does not pass the policy constant")
