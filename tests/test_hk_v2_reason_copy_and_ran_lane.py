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

WHY THE BLOCK-REASON INVENTORY IS TAKEN BY EXECUTION, NOT BY GREP.  The first cut of
this suite scraped ``inspect.getsource(_buy_filter)`` with a ``"([^"]+)"`` regex.  The
function's docstring is itself triple-quoted, so the regex paired quotes ACROSS it and
the extractor returned an EMPTY set — the missing-copy test passed on zero reasons and
would have kept passing through the very defect it was written for.  The inventory is
now built by DRIVING ``_buy_filter`` down every branch and collecting what it actually
returns, with an explicit non-vacuity floor.
"""
from __future__ import annotations

import inspect

import pandas as pd
import pytest

from engine import hk_board_rank, signal_quality as sq, us_board_rank


BOARD_ASOF = "2026-08-03"


# --------------------------------------------------------------------------- #
# 1 + 2 — every reason the engine can emit for a BLOCKED marker has plain copy
# --------------------------------------------------------------------------- #
def _frame(*, above200: bool, weekly_bull: bool, closes) -> pd.DataFrame:
    n = len(closes)
    return pd.DataFrame({
        "close": pd.Series(closes, dtype=float),
        "above200": pd.Series([above200] * n, dtype=bool),
        "w_bull": pd.Series([weekly_bull] * n, dtype=bool),
    })


# Both `held` outcomes on every (above200, weekly_bull) corner, under both policies,
# plus the divergence veto and the two short-frame pending paths.  `_buy_filter` has no
# other exit, so this is the exhaustive reason inventory.
_UP = [100.0, 101.0, 101.5, 102.0]      # next bar closes HIGHER -> held
_DOWN = [100.0, 99.0, 99.5, 100.5]      # next bar closes LOWER  -> not held


def _reclaiming_frame(*, closes) -> pd.DataFrame:
    """A counter-trend frame whose `above200` FLIPS TRUE at bar i+1 — i.e. the name
    reclaims its 200-day line after the signal.

    Needed because `_frame` holds `above200` constant, so `reclaim = a[i+1] or a[i+2]`
    could only ever be the same value as `a[i]`.  With a constant frame the counter-trend
    branch can never return its 'reclaimed but did not hold' outcome, and the inventory
    below would silently miss a reason the engine really does emit in production (29 rows
    in the CN_RECLAIM_HOLD_AUDIT year).  A missing reason is a missing copy requirement,
    so the fixture's blind spot would have become the map's blind spot."""
    n = len(closes)
    return pd.DataFrame({
        "close": pd.Series(closes, dtype=float),
        "above200": pd.Series([False] + [True] * (n - 1), dtype=bool),
        "w_bull": pd.Series([False] * n, dtype=bool),
    })


def _emitted_reasons() -> dict[str, list[bool | None]]:
    """{reason: [every `take` value it was returned with]} across all branches."""
    seen: dict[str, list[bool | None]] = {}

    def record(take, reason):
        seen.setdefault(reason, []).append(take)

    for above200 in (True, False):
        for weekly_bull in (True, False):
            for closes in (_UP, _DOWN):
                sig = _frame(above200=above200, weekly_bull=weekly_bull,
                             closes=closes)
                for veto in (True, False):
                    record(*sq._buy_filter(0, sig, False, len(sig),
                                           reclaim_veto=veto))
                # the bearish-divergence veto, and the two short-frame pending paths
                record(*sq._buy_filter(0, sig, True, len(sig)))
                record(*sq._buy_filter(0, sig, False, 1))            # i+1 >= n
                record(*sq._buy_filter(0, sig, False, 2, reclaim_veto=True))
    # the counter-trend branch's reclaim-succeeded outcomes (both hold results)
    for closes in (_UP, _DOWN):
        sig = _reclaiming_frame(closes=closes)
        record(*sq._buy_filter(0, sig, False, len(sig), reclaim_veto=True))
    return seen


def _block_reasons() -> set[str]:
    """Reasons `_buy_filter` returns alongside take=False — i.e. a `block` marker.

    A reason is a BLOCK reason if it is ever emitted with ``take is False``.  That is
    the same test :func:`hk_board_rank.veto_admits` applies (``quality == "block"``),
    so the two cannot drift apart on a definition.
    """
    return {r for r, takes in _emitted_reasons().items() if False in takes}


def test_the_reason_inventory_is_not_vacuous():
    """The guard on the guard.  If this extractor ever returns nothing, every
    missing-copy assertion below becomes an unconditional pass — which is exactly how
    the regex-scraping first draft of this file would have shipped green."""
    blocks = _block_reasons()
    assert len(blocks) >= 5, blocks
    assert {"failed next-bar hold",
            "counter-trend, no 200-reclaim/hold",
            "counter-trend, held but no 200-reclaim",
            "counter-trend, reclaimed 200 but no next-bar hold",
            "veto: bearish divergence"} <= blocks, sorted(blocks)
    # RETIRED 2026-08-04 — the engine must NOT emit it any more, and this is the pin that
    # says so.  Its copy key deliberately outlives it (hk_board_rank.RETIRED_VETO_REASONS).
    assert "failed reclaim-and-hold" not in blocks, (
        "the main branch is again naming a reclaim it never tests — "
        "research/cn_prophet_audit/CN_RECLAIM_HOLD_AUDIT.md §11")


def test_every_block_reason_the_engine_emits_has_plain_word_copy():
    missing = sorted(r for r in _block_reasons()
                     if r not in hk_board_rank.VETO_REASON_COPY)
    assert not missing, (
        f"these block reasons fall through to the contentless fallback: {missing}. "
        "A vetoed row that cannot say WHY is worse than no row.")


def test_the_copy_map_carries_no_key_the_vetoed_lane_can_never_render():
    """`veto_reason_copy` is reached from ONE place — `build_vetoed_rows`, which admits
    `quality == "block"` only.  A take/pending key would be unreachable copy, and a test
    asserting its wording would be pinning dead code.  (An earlier cut of this fix added
    `held confirmation (counter-trend)`, a TAKE reason, for exactly that reason.)

    A RETIRED key is the one legitimate exception: the engine has stopped emitting it but
    stored rows still carry it, so its sentence must survive or every historical vetoed row
    goes blank.  That exemption is declared in code (`RETIRED_VETO_REASONS`), never inferred
    here — otherwise this guard would quietly accept any dead key someone forgot to remove."""
    strays = sorted(set(hk_board_rank.VETO_REASON_COPY)
                    - _block_reasons()
                    - hk_board_rank.RETIRED_VETO_REASONS)
    assert not strays, (
        f"{strays} can never reach the vetoed lane — the map is block-only")


def test_every_retired_key_is_really_retired_and_still_has_copy():
    """The other half of the exemption.  A key parked in `RETIRED_VETO_REASONS` while the
    engine still emits it would exempt a LIVE reason from the reachability guard; one
    without copy would leave historical rows on the contentless fallback."""
    assert hk_board_rank.RETIRED_VETO_REASONS, "the retired set is the exemption's receipt"
    live = _block_reasons()
    for key in hk_board_rank.RETIRED_VETO_REASONS:
        assert key not in live, (
            f"{key!r} is marked retired but the engine still emits it")
        assert key in hk_board_rank.VETO_REASON_COPY, (
            f"{key!r} is retired without copy — every stored row carrying it goes blank")


@pytest.mark.parametrize("reason", ["failed next-bar hold", "failed reclaim-and-hold"])
def test_the_next_bar_hold_copy_is_exact_in_both_languages(reason):
    copy = hk_board_rank.VETO_REASON_COPY[reason]
    assert copy["en"] == (
        "The next 3-day bar closed lower, so the entry never confirmed")
    assert copy["zh"] == "信号后的下一根 3 日K线收低，入场未获确认"


def test_the_confirmation_bar_is_described_in_the_units_the_engine_measures():
    """`signal_frame` resamples to "3B" before `_buy_filter` reads i+1, so the
    confirmation bar is a 3-DAY bar, not a session.  "The next session closed lower"
    would be a smaller copy of the same false-narrative defect this file removes."""
    src = inspect.getsource(sq.signal_frame)
    assert '"3B"' in src, "the frame is no longer 3-day — the copy's units must move"
    for reason in ("failed next-bar hold", "failed reclaim-and-hold"):
        assert "3-day bar" in hk_board_rank.VETO_REASON_COPY[reason]["en"]


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


def test_the_main_branch_names_the_hold_it_tests_and_no_reclaim():
    """Was `test_the_engine_literal_is_deliberately_unrenamed`, which pinned the misleading
    `failed reclaim-and-hold` on the grounds that renaming it would change US/CN §7 bytes to
    fix a copy defect.  `research/cn_prophet_audit/CN_RECLAIM_HOLD_AUDIT.md` §10/§11 measured
    what leaving it cost: 1,094 blocks in the audit year named a reclaim that never ran, and
    002155.SZ — 5.2% ABOVE its 200-day mean at its buy bar, so the counter-trend branch was
    never entered — was misread by two separate investigations off that string.  The rename
    landed; the old test's own instruction was that the copy key must move with it, and
    `RETIRED_VETO_REASONS` is where it moved to.

    The main branch is reached whenever a name is NOT both below-200 and weekly-down.  It
    resolves on `held` alone, so its failure may name the hold and nothing else."""
    for above200, weekly_bull in ((True, True), (True, False), (False, True)):
        sig = _frame(above200=above200, weekly_bull=weekly_bull, closes=_DOWN)
        take, reason = sq._buy_filter(0, sig, False, len(sig))
        assert take is False
        assert reason == sq.HOLD_FAIL == "failed next-bar hold", (
            f"above200={above200} weekly_bull={weekly_bull}: {reason!r}")
        assert "reclaim" not in reason and "200" not in reason, (
            f"the main branch is naming a 200-day test it never ran: {reason!r}")


def test_the_counter_trend_branch_names_which_of_its_two_legs_refused():
    """The branch that DOES test both legs must say which one failed.  Collapsing all three
    outcomes into one string is why only 40.2% of the rows reading 'no 200-reclaim' were
    actually relieved by dropping the reclaim rule (CN_RECLAIM_HOLD_AUDIT.md §11)."""
    ct = {"above200": False, "weekly_bull": False}
    # neither leg: reclaim never happens, hold fails -> the legacy sentence, earned
    assert sq._buy_filter(0, _frame(closes=_DOWN, **ct), False, 4) == (
        False, "counter-trend, no 200-reclaim/hold")
    # held, never reclaimed
    assert sq._buy_filter(0, _frame(closes=_UP, **ct), False, 4) == (
        False, "counter-trend, held but no 200-reclaim")
    # reclaimed, did not hold
    assert sq._buy_filter(0, _reclaiming_frame(closes=_DOWN), False, 4) == (
        False, "counter-trend, reclaimed 200 but no next-bar hold")
    # both legs pass -> unchanged take copy
    assert sq._buy_filter(0, _reclaiming_frame(closes=_UP), False, 4) == (
        True, "reclaimed 200 & held")


# --------------------------------------------------------------------------- #
# the rendered rows — the map being right is not the surface being right
# --------------------------------------------------------------------------- #
_DATES = [f"2026-07-{d:02d}" for d in (1, 2, 3, 6, 7, 8, 9, 10)]
_CLOSES = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 120.0]


def _blocked_verdict(reason: str) -> dict:
    return {"eligible": False, "weekly_bull": True, "fresh_bars": 4,
            "last": {"type": "buy", "quality": "block", "date": "2026-07-03",
                     "reason": reason}}


def _vetoed_row(reason: str) -> dict:
    rows = hk_board_rank.build_vetoed_rows(
        {"A": _blocked_verdict(reason)}, meta_by={"A": {"name": "A Co"}},
        close_of=lambda t: (_DATES, _CLOSES), board_asof=BOARD_ASOF)
    assert len(rows) == 1
    return rows[0]


@pytest.mark.parametrize("reason", ["failed next-bar hold", "failed reclaim-and-hold"])
def test_a_vetoed_row_renders_the_exact_next_bar_copy(reason):
    row = _vetoed_row(reason)
    assert row["blocked_reason_en"] == (
        "The next 3-day bar closed lower, so the entry never confirmed")
    assert row["blocked_reason_zh"] == "信号后的下一根 3 日K线收低，入场未获确认"
    # the engine's own wording still rides along for the detail view, unaltered
    assert row["reason_raw"] == reason


def test_no_vetoed_row_can_render_the_generic_fallback_for_a_known_engine_reason():
    """THE regression this whole file exists for: 10 of the 12 rows on the first v2
    board printed "The entry gate refused this signal", which tells a reader nothing.
    Driven through the real row builder, not the map, because the map being complete
    and the surface being right are two different claims."""
    for reason in sorted(_block_reasons()):
        row = _vetoed_row(reason)
        assert row["blocked_reason_en"] != hk_board_rank.VETO_REASON_FALLBACK["en"], (
            f"{reason!r} still renders the contentless fallback")
        assert row["blocked_reason_zh"] != hk_board_rank.VETO_REASON_FALLBACK["zh"]


def test_the_fallback_still_fires_for_a_reason_the_engine_does_not_emit():
    """The fallback is not dead code — it is the fail-soft for a reason string that
    reaches this lane from somewhere else.  A test suite that deleted it would have
    nothing to catch the NEXT unmapped reason."""
    row = _vetoed_row("some reason invented after this test was written")
    assert row["blocked_reason_en"] == hk_board_rank.VETO_REASON_FALLBACK["en"]


# --------------------------------------------------------------------------- #
# 3 — the ran lane's above200 door
# --------------------------------------------------------------------------- #
def _recovering_verdict(**over):
    """A washout-bounce name: cross lapsed, weekly structure up, still BELOW its
    200-day line because it fell 40% before bouncing (1810.HK-shaped)."""
    v = {"eligible": False, "ticks": 8, "above200": False, "weekly_bull": True,
         "fresh_bars": 4, "last": {"type": "buy", "date": "2026-07-03"}}
    v.update(over)
    return v


def test_us_policy_still_excludes_a_below_200_name_from_the_ran_lane():
    """DEFAULT is unchanged behaviour — US/CN must be byte-identical."""
    assert us_board_rank.ran_admits(_recovering_verdict(), {"dir": "up"}) is False


def test_hk_policy_admits_the_recovering_name_the_us_policy_cannot_see():
    assert us_board_rank.ran_admits(
        _recovering_verdict(), {"dir": "up"}, require_above200=False) is True


def test_the_two_policies_disagree_on_exactly_this_row():
    """The parameterisation is only real if the SAME row lands differently.  A test
    that never shows the disagreement cannot tell a wired flag from a dead one."""
    row, verdict = {"dir": "up"}, _recovering_verdict()
    assert us_board_rank.ran_admits(verdict, row, require_above200=False) is not \
        us_board_rank.ran_admits(verdict, row, require_above200=True)


def test_an_above200_name_is_admitted_under_both_policies():
    """Relaxing the door must not change the answer for a row that already cleared it —
    otherwise the flag is doing something other than what it says."""
    verdict = _recovering_verdict(above200=True)
    for policy in (True, False):
        assert us_board_rank.ran_admits(
            verdict, {"dir": "up"}, require_above200=policy) is True


def test_dropping_above200_does_not_drop_the_other_guards():
    """The relaxed lane still refuses: a live signal, an out-of-window age, a
    non-bullish weekly, and a marked-down row.  Loosening one door must not open
    the rest — that would turn the lane into an unfiltered dump."""
    kw = {"require_above200": False}
    row = {"dir": "up"}
    assert us_board_rank.ran_admits(_recovering_verdict(eligible=True), row, **kw) is False
    assert us_board_rank.ran_admits(_recovering_verdict(eligible=None), row, **kw) is False
    assert us_board_rank.ran_admits(_recovering_verdict(ticks=1), row, **kw) is False
    assert us_board_rank.ran_admits(_recovering_verdict(ticks=99), row, **kw) is False
    assert us_board_rank.ran_admits(_recovering_verdict(ticks=None), row, **kw) is False
    assert us_board_rank.ran_admits(_recovering_verdict(weekly_bull=False), row, **kw) is False
    assert us_board_rank.ran_admits(_recovering_verdict(weekly_bull=None), row, **kw) is False
    assert us_board_rank.ran_admits(_recovering_verdict(), {"dir": "down"}, **kw) is False


def _ran_rows(builder, **kw):
    return builder({"A": _recovering_verdict()}, meta_by={"A": {"name": "A", "dir": "up"}},
                   close_of=lambda t: (_DATES, _CLOSES), board_asof=BOARD_ASOF, **kw)


def test_the_hk_row_builder_surfaces_the_recovering_name():
    """Through the real HK lane builder, not just the predicate."""
    assert _ran_rows(hk_board_rank.build_ran_rows) == []
    rows = _ran_rows(hk_board_rank.build_ran_rows, require_above200=False)
    assert [r["ticker"] for r in rows] == ["A"]
    assert rows[0]["stage"] == hk_board_rank.STAGE_RAN
    assert rows[0]["display_only"] is True
    assert rows[0]["stance"] == hk_board_rank.RAN_STANCE
    # still a context row: no entry claim rides in on the relaxed door
    assert "entry_signal" not in rows[0] and "prophet" not in rows[0]


def test_the_us_row_builder_is_unchanged_on_the_same_row():
    assert _ran_rows(us_board_rank.build_ran_rows) == []


# --------------------------------------------------------------------------- #
# the defaults themselves — the mutation surface
# --------------------------------------------------------------------------- #
_PARAMETERISED = [
    (us_board_rank.ran_admits, "require_above200"),
    (us_board_rank.build_ran_rows, "require_above200"),
    (hk_board_rank.build_ran_rows, "require_above200"),
]


def _ids(value):
    """`us_board_rank.build_ran_rows` and `hk_board_rank.build_ran_rows` share a
    qualname, so a qualname-only id renders them as `..._0`/`..._1` and a mutation
    report cannot say which module went red.  Qualify by module."""
    if callable(value):
        return f"{value.__module__.rsplit('.', 1)[-1]}.{value.__qualname__}"
    return value


@pytest.mark.parametrize("fn,name", _PARAMETERISED, ids=_ids)
def test_the_new_flag_defaults_to_todays_behaviour(fn, name):
    """US/CN ride on the DEFAULT.  Flip any of these to False and every US/CN board
    silently changes membership — so the default is pinned here as well as being
    exercised by the behaviour tests above.  This is the assertion the mutation run
    targets: flipping a default must turn this red."""
    p = inspect.signature(fn).parameters[name]
    assert p.default is True, f"{fn.__qualname__}.{name} default moved off True"


@pytest.mark.parametrize("fn,name", _PARAMETERISED, ids=_ids)
def test_the_new_flag_stays_keyword_only(fn, name):
    """Same discipline `reclaim_veto` carries: a positional policy flag is one
    argument-order slip away from silently re-gating a board."""
    p = inspect.signature(fn).parameters[name]
    assert p.kind is inspect.Parameter.KEYWORD_ONLY, (
        f"{fn.__qualname__}.{name} must stay keyword-only")


def test_the_hk_builder_actually_passes_the_relaxed_policy():
    """The parameter is worthless if the call site never sets it — the class of
    defect where half a board runs the old rule."""
    from scripts import build_hk_library

    assert build_hk_library.HK_RAN_REQUIRE_ABOVE200 is False
    src = inspect.getsource(build_hk_library.compute_hk_standouts)
    assert "require_above200=HK_RAN_REQUIRE_ABOVE200" in src, (
        "the HK ran-lane call site does not pass the policy constant")


def test_the_two_hk_policy_constants_stay_separate_switches():
    """`HK_RECLAIM_VETO` (the buy-filter's 2-bar reclaim leg) and
    `HK_RAN_REQUIRE_ABOVE200` (the display lane's static level test) are two different
    gates that happen to share an operator rationale.  They are pinned as two constants
    at two call sites so that re-arming the buy-filter leg — which a measurement could
    well justify — does not silently re-gate the display lane along with it.
    """
    from scripts import build_hk_library

    src = inspect.getsource(build_hk_library.compute_hk_standouts)
    assert "reclaim_veto=HK_RECLAIM_VETO" in src
    assert "require_above200=HK_RAN_REQUIRE_ABOVE200" in src
    # neither constant may be defined in terms of the other
    defs = [ln.strip() for ln in inspect.getsource(build_hk_library).splitlines()
            if ln.startswith(("HK_RECLAIM_VETO", "HK_RAN_REQUIRE_ABOVE200"))]
    assert defs == ["HK_RECLAIM_VETO = False", "HK_RAN_REQUIRE_ABOVE200 = False"], defs


# --------------------------------------------------------------------------- #
# 4 — the cap, not the trend test, is what actually hid the mega-caps
# --------------------------------------------------------------------------- #
def _ran_row(ticker: str) -> dict:
    return {"ticker": ticker}


def test_cohort_members_keep_their_seat_when_the_lane_is_oversubscribed():
    """Opening the above200 door takes HK ran admits from 13 to 64 for 12 slots, and
    the lane sorts freshest-cross-first — so every mega-cap lands at rank 14-56 and is
    truncated away.  Measured 2026-08-04: the door alone surfaced NONE of the named
    names AND evicted 3690.HK, which the stricter lane had been showing.  Cohort-first
    is the rule build_vetoed_rows already applies for exactly this reason."""
    rows = [_ran_row(f"FRESH{i}.HK") for i in range(12)] + [
        _ran_row("1810.HK"), _ran_row("9988.HK")]
    members = {"1810.HK", "9988.HK"}
    kept = hk_board_rank._cohort_first(rows, members, 12)
    tickers = [r["ticker"] for r in kept]
    assert len(kept) == 12
    assert tickers[:2] == ["1810.HK", "9988.HK"], tickers
    assert "FRESH11.HK" not in tickers, "a non-cohort row should yield the slot"


def test_cohort_first_admits_nobody_new_and_is_a_noop_under_the_cap():
    """It re-orders, it never widens: every row it can return already passed
    ran_admits.  Under the cap it must not touch the order at all."""
    rows = [_ran_row("A.HK"), _ran_row("1810.HK"), _ran_row("B.HK")]
    out = hk_board_rank._cohort_first(rows, {"1810.HK"}, 12)
    assert [r["ticker"] for r in out] == ["A.HK", "1810.HK", "B.HK"]
    assert len(hk_board_rank._cohort_first(rows, {"1810.HK"}, 2)) == 2


def test_more_cohort_members_than_slots_still_respects_the_cap():
    rows = [_ran_row(f"C{i}.HK") for i in range(20)]
    members = {f"C{i}.HK" for i in range(20)}
    assert len(hk_board_rank._cohort_first(rows, members, 12)) == 12


def test_the_hk_ran_call_site_passes_the_cohort():
    """_cohort_first is a NO-OP without members, so an unpassed cohort would make the
    whole fix dead in production while every unit test above still passed — the same
    dead-parameter class the require_above200 pin guards."""
    import re
    from scripts import build_hk_library

    src = inspect.getsource(build_hk_library)
    call = re.search(r"ran = hk_board_rank\.build_ran_rows\((.*?)\n    \)", src, re.S)
    assert call, "could not locate the HK ran-lane call site"
    assert "cohort=" in call.group(1), "the ran lane is built without a cohort"
    assert "require_above200=HK_RAN_REQUIRE_ABOVE200" in call.group(1)
