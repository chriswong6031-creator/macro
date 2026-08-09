"""CN continuation-watch cohort (engine.china_continuation_watch + its ledger stamp).

CN Prophet masterplan §2.7: 17 of the top-150 era runners (11%) were NEVER
eligible — the shallowest charts, blocked by the buy-filter's counter-trend /
no-200-reclaim leg — and their median era return was +18.7%.  §5 W-C charters a
shadow ledger for that cohort so a forward record accrues before anyone proposes
a door.

These pin the four things a shadow lane can get wrong:
  1. the CANDIDATE RULE — all three legs required, and the block reason is the
     §2.7 family rather than any ineligibility;
  2. the CAP and its ordering (trail-63 desc);
  3. the DEFINITION STAMP reaching the parquet;
  4. the WATCH EXCLUSION — the cohort can never own the headline grade, no
     matter what order it was appended in.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine import china_continuation_watch as ccw
from engine import china_standout_track as cst
from engine import signal_gate, signal_quality
from lib import config

# ---------------------------------------------------------------------------
# Series helpers
# ---------------------------------------------------------------------------

def _series(values) -> pd.Series:
    idx = pd.bdate_range("2025-06-02", periods=len(values))
    return pd.Series(np.asarray(values, dtype=float), index=idx)


def _rising(n: int = 140, start: float = 10.0, step: float = 0.05) -> pd.Series:
    """A steady uptrend: close above its 50d mean, trail-63 clearly positive."""
    return _series([start + step * i for i in range(n)])


def _falling(n: int = 140, start: float = 20.0, step: float = 0.05) -> pd.Series:
    return _series([start - step * i for i in range(n)])


def _row(ticker: str, reason: str, *, eligible: bool = False, **extra) -> dict:
    return {"ticker": ticker, "name": f"N-{ticker}", "sector": "Tech",
            "signal": {"eligible": eligible, "reason": reason}, **extra}


#: The verdict text the production gate actually emits for the §2.7 block:
#: ``signal_gate.verdict`` wraps the filter's reason as "buy blocked by
#: filter: ...".  Derived from the constant rather than retyped, so the cases
#: below keep exercising the string the engine currently ships — a hardcoded
#: copy would go on passing against a spelling that had been retired.
BLOCKED = f"buy blocked by filter: {signal_quality.CT_BOTH_FAIL}"


# ---------------------------------------------------------------------------
# 0. the reason strings are the ENGINE's, not this module's invention
# ---------------------------------------------------------------------------

def _filter_frame(closes, above200, w_bull) -> dict:
    """The three columns ``_buy_filter``'s confirmation legs read, as a frame."""
    idx = pd.bdate_range("2026-06-01", periods=len(closes))
    return {"close": pd.Series(closes, index=idx, dtype=float),
            "above200": pd.Series(above200, index=idx),
            "w_bull": pd.Series(w_bull, index=idx)}


#: Bar 0 of each frame is BOTH below-200 and weekly-down, which is what selects
#: the counter-trend branch; bars 1-2 then choose which of its three failures
#: fires.  Every §2.7 block shape, driven out of the live filter.
_COUNTER_TREND_BLOCKS = {
    "both legs fail":     _filter_frame([10, 9, 9, 9],    [False] * 4,               [False] * 4),
    "held, no reclaim":   _filter_frame([10, 11, 11, 11], [False] * 4,               [False] * 4),
    "reclaimed, no hold": _filter_frame([10, 9, 9, 9],    [False, True, True, True], [False] * 4),
}


def _emitted_reason(frame: dict, *, reclaim_veto: bool = True) -> str:
    """What ``_buy_filter`` ACTUALLY returns for ``frame`` (bear=False, bar 0)."""
    take, reason = signal_quality._buy_filter(  # noqa: SLF001
        0, frame, False, 4, reclaim_veto=reclaim_veto)
    assert take is False, f"expected a block, got {take!r}/{reason!r}"
    return reason


def _gate_verdict(reason: str) -> dict:
    """A blocked buy carried through the REAL verdict mapper, as the lane sees it."""
    return signal_gate.verdict({
        "markers": [{"type": "buy", "quality": "block", "reason": reason,
                     "date": "2026-07-01"}],
        "state": "down", "above200": False, "weekly_bull": False,
        "early_now": False, "asof": "2026-07-02",
    })


def test_block_markers_match_the_live_buy_filter_strings():
    """If signal_quality re-words its reasons, this cohort silently empties.

    Pinning the real source strings makes that a red test rather than a lane
    that quietly logs nothing for months.

    The strings are RUN out of the engine rather than read off its bytecode.
    #4583 moved them into module constants (``CT_*``), and a function that
    references a module global does not carry the value in its own
    ``co_consts`` — so the first version of this test, which read
    ``_buy_filter.__code__.co_consts``, stopped being able to see them at all.
    Driving the filter pins the value that actually ships, through the same
    verdict mapper the nightly builder feeds ``select`` from.
    """
    emitted = {shape: _emitted_reason(f) for shape, f in _COUNTER_TREND_BLOCKS.items()}

    # Non-vacuity: three DISTINCT strings, or the sweep below pins one thrice.
    assert len(set(emitted.values())) == 3, emitted
    # ...and they are exactly the module's counter-trend constants, so a fourth
    # shape added upstream is a red test here rather than an unswept branch.
    assert set(emitted.values()) == {
        v for k, v in vars(signal_quality).items() if k.startswith("CT_")
    }, emitted

    # THE CONTRACT: every one of them still reaches the cohort.
    for shape, reason in emitted.items():
        v = _gate_verdict(reason)
        assert v["eligible"] is False, shape
        assert ccw.is_trend_blocked(v), f"{shape}: {v['reason']!r} matches no marker"


def test_a_hold_only_block_is_not_the_counter_trend_cohort():
    """§2.7 is the counter-trend block, so failing ONLY the next-bar hold is not it.

    Load-bearing rather than incidental.  Before #4583 the main branch emitted
    ``failed reclaim-and-hold`` — naming a reclaim it never evaluated — which
    ``BLOCK_REASON_MARKERS`` matches, so had the correction not landed this lane
    would have swept in every plain hold failure (1,094 in the audit year;
    research/cn_prophet_audit/CN_RECLAIM_HOLD_AUDIT.md §10/§11).  Both branches
    that can emit the corrected string must stay out.
    """
    main_branch = _filter_frame([10, 9, 9, 9], [True] * 4, [True] * 4)
    counter_trend_no_veto = _COUNTER_TREND_BLOCKS["both legs fail"]

    for shape, reason in (
        ("main branch", _emitted_reason(main_branch)),
        ("counter-trend, reclaim_veto=False",
         _emitted_reason(counter_trend_no_veto, reclaim_veto=False)),
    ):
        assert reason == signal_quality.HOLD_FAIL, shape
        assert ccw.is_trend_blocked(_gate_verdict(reason)) is False, shape


def test_the_retired_reason_string_is_no_longer_emitted():
    """``reclaim-and-hold`` survives in BLOCK_REASON_MARKERS but matches nothing.

    That is only safe while the engine cannot emit it: the string named a
    hold-only block, which the test above establishes is NOT a member of this
    cohort.  If a re-wording ever brings the spelling back, that dead marker
    silently starts admitting the wrong population — so pin the retirement here
    rather than trusting it to stay retired.
    """
    frames = [*_COUNTER_TREND_BLOCKS.values(),
              _filter_frame([10, 9, 9, 9], [True] * 4, [True] * 4),    # main, blocked
              _filter_frame([10, 11, 11, 11], [True] * 4, [True] * 4)]  # main, passing
    reasons = {signal_quality._buy_filter(0, f, bear, 4, reclaim_veto=veto)[1]  # noqa: SLF001
               for f in frames for bear in (False, True) for veto in (False, True)}
    assert len(reasons) >= 5, sorted(reasons)   # every branch, passes included
    assert not any("reclaim-and-hold" in r for r in reasons), sorted(reasons)


def test_gate_verdict_for_a_blocked_buy_carries_the_family_reason():
    """End-to-end through the real verdict mapper, not a hand-written string."""
    v = signal_gate.verdict({
        "markers": [{"type": "buy", "quality": "block",
                     "reason": "counter-trend, no 200-reclaim/hold",
                     "date": "2026-07-01"}],
        "state": "down", "above200": False, "weekly_bull": False,
        "early_now": False, "asof": "2026-07-02",
    })
    assert v["eligible"] is False
    assert ccw.is_trend_blocked(v), v["reason"]


# ---------------------------------------------------------------------------
# 1. candidate rule
# ---------------------------------------------------------------------------

def test_all_three_legs_are_required():
    closes = {"A.SZ": _rising(), "B.SZ": _rising(), "C.SZ": _falling(), "D.SZ": _rising()}
    rows = [
        _row("A.SZ", BLOCKED),                                   # qualifies
        _row("B.SZ", "buy blocked by filter: veto: bearish divergence"),  # wrong reason
        _row("C.SZ", BLOCKED),                                   # downtrend: fails MA + trail
        _row("D.SZ", BLOCKED, eligible=True),                    # ELIGIBLE — has a real lane
    ]
    out = ccw.select(rows, closes)
    assert [r["ticker"] for r in out] == ["A.SZ"]


def test_an_eligible_counter_trend_pass_is_never_admitted():
    """_buy_filter's PASSING string also contains 'counter-trend'. Reading the
    reason before the eligibility flag would put a live buy-shelf row into a
    watch cohort."""
    v = {"eligible": True, "reason": "held confirmation (counter-trend)"}
    assert ccw.is_trend_blocked(v) is False
    assert ccw.select([_row("A.SZ", v["reason"], eligible=True)], {"A.SZ": _rising()}) == []


def test_a_name_below_its_50d_mean_is_not_a_continuation():
    """Rising over 63 sessions but rolling over now: the trail-63 leg passes and
    the MA leg must still reject it. One leg alone is not the shape."""
    vals = [10.0 + 0.10 * i for i in range(120)] + [22.0 - 0.35 * i for i in range(30)]
    closes = {"A.SZ": _series(vals)}
    m = ccw.measure(closes["A.SZ"])
    assert m is None
    assert ccw.select([_row("A.SZ", BLOCKED)], closes) == []


def test_a_flat_name_with_zero_trailing_return_is_excluded():
    closes = {"A.SZ": _series([10.0] * 140)}
    assert ccw.measure(closes["A.SZ"]) is None
    assert ccw.select([_row("A.SZ", BLOCKED)], closes) == []


def test_a_name_with_too_little_history_is_skipped_not_crashed():
    assert ccw.measure(_rising(n=40)) is None
    assert ccw.select([_row("A.SZ", BLOCKED)], {"A.SZ": _rising(n=40)}) == []


def test_a_name_with_no_close_series_is_skipped():
    assert ccw.select([_row("A.SZ", BLOCKED)], {}) == []


def test_measure_reports_the_geometry_it_screened_on():
    m = ccw.measure(_rising())
    assert m["trail_63"] > 0
    assert m["vs_ma50"] > 0
    assert m["price"] > m["ma50"]


# ---------------------------------------------------------------------------
# 2. cap + ordering
# ---------------------------------------------------------------------------

def test_capped_at_30_and_ranked_by_trailing_63_desc():
    rows, closes = [], {}
    for i in range(45):
        tk = f"T{i:02d}.SZ"
        # Steeper step => larger trail-63. i=44 is the strongest.
        closes[tk] = _rising(step=0.02 + 0.002 * i)
        rows.append(_row(tk, BLOCKED))
    out = ccw.select(rows, closes)
    assert len(out) == ccw.CAP == 30
    trails = [r["continuation"]["trail_63"] for r in out]
    assert trails == sorted(trails, reverse=True)
    assert out[0]["ticker"] == "T44.SZ"
    assert "T00.SZ" not in {r["ticker"] for r in out}


def test_cap_is_overridable_for_a_caller_but_defaults_to_the_charter():
    rows = [_row(f"T{i}.SZ", BLOCKED) for i in range(5)]
    closes = {f"T{i}.SZ": _rising(step=0.02 + 0.01 * i) for i in range(5)}
    assert len(ccw.select(rows, closes, cap=2)) == 2
    assert len(ccw.select(rows, closes)) == 5


# ---------------------------------------------------------------------------
# 3. definition stamp reaches the store
# ---------------------------------------------------------------------------

@pytest.fixture
def cn_store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    import lib.store as lstore
    monkeypatch.setattr(lstore, "read_status", lambda: {})   # settled session
    return tmp_path


def test_rows_are_stamped_with_the_watch_definition(cn_store):
    rows = ccw.select([_row("A.SZ", BLOCKED)], {"A.SZ": _rising()})
    assert rows[0]["board_definition"] == "cn_continuation_watch_v1"
    assert rows[0]["lane"] == ccw.LANE

    cst.append_board(rows, asof="2026-08-04", lane="asia")
    df = pd.read_parquet(cn_store / "china_standout_track" / "board.parquet")
    assert set(df["board_definition"]) == {"cn_continuation_watch_v1"}
    assert set(df["lane"]) == {"continuation_watch"}


def test_the_cohort_never_persists_from_a_render_lane(cn_store):
    rows = ccw.select([_row("A.SZ", BLOCKED)], {"A.SZ": _rising()})
    assert cst.append_board(rows, asof="2026-08-04", lane="render") == 0
    assert not (cn_store / "china_standout_track" / "board.parquet").exists()


def test_a_name_on_both_shelves_keeps_one_row_per_definition(cn_store):
    """append_board's keep-first key includes board_definition, which is what
    lets the watch cohort share the store without colliding with the board."""
    cst.append_board([{"ticker": "A.SZ", "board_definition": "cn_prophet_v2",
                       "lane": "featured", "price": 12.0}],
                     asof="2026-08-04", lane="asia")
    cst.append_board(ccw.select([_row("A.SZ", BLOCKED)], {"A.SZ": _rising()}),
                     asof="2026-08-04", lane="asia")
    df = pd.read_parquet(cn_store / "china_standout_track" / "board.parquet")
    a = df[df["ticker"] == "A.SZ"]
    assert len(a) == 2
    assert set(a["board_definition"]) == {"cn_prophet_v2", "cn_continuation_watch_v1"}


# ---------------------------------------------------------------------------
# 4. WATCH exclusion from the headline grade
# ---------------------------------------------------------------------------

def test_the_definition_is_registered_as_a_watch_cohort():
    assert ccw.BOARD_DEFINITION in cst.WATCH_DEFINITIONS


def test_appending_the_cohort_last_cannot_flip_the_headline_definition(cn_store):
    """The failure this guards: _latest_definition_frame resolves the headline by
    newest date then APPEND ORDER, so a watch cohort appended after the board on
    the same date would take the grade if it were not excluded.  This lane is
    appended last by design, so the exclusion is what makes that safe."""
    cst.append_board([{"ticker": "A.SZ", "board_definition": "cn_prophet_v2",
                       "lane": "featured", "price": 12.0}],
                     asof="2026-08-04", lane="asia")
    cst.append_board(ccw.select([_row("B.SZ", BLOCKED)], {"B.SZ": _rising()}),
                     asof="2026-08-04", lane="asia")
    df = pd.read_parquet(cn_store / "china_standout_track" / "board.parquet")
    frame, definition = cst._latest_definition_frame(df)  # noqa: SLF001
    assert definition == "cn_prophet_v2"
    assert "cn_continuation_watch_v1" not in set(frame["board_definition"])


def test_a_store_holding_only_the_watch_cohort_resolves_no_headline(cn_store):
    """The degenerate case: with nothing but watch rows the grader must find no
    headline definition rather than promoting the only cohort present."""
    cst.append_board(ccw.select([_row("A.SZ", BLOCKED)], {"A.SZ": _rising()}),
                     asof="2026-08-04", lane="asia")
    df = pd.read_parquet(cn_store / "china_standout_track" / "board.parquet")
    _frame, definition = cst._latest_definition_frame(df)  # noqa: SLF001
    assert definition is None
