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


#: The verdict text the production gate actually emits for the §2.7 block —
#: engine/signal_gate.py:144 wraps engine/signal_quality.py:220.
BLOCKED = "buy blocked by filter: counter-trend, no 200-reclaim/hold"


# ---------------------------------------------------------------------------
# 0. the reason strings are the ENGINE's, not this module's invention
# ---------------------------------------------------------------------------

def test_block_markers_match_the_live_buy_filter_strings():
    """If signal_quality re-words its reasons, this cohort silently empties.

    Pinning the real source strings makes that a red test rather than a lane
    that quietly logs nothing for months.
    """
    src = signal_quality._buy_filter.__code__.co_consts  # noqa: SLF001
    literals = [c for c in src if isinstance(c, str)]
    assert "counter-trend, no 200-reclaim/hold" in literals
    assert "failed reclaim-and-hold" in literals
    for text in ("counter-trend, no 200-reclaim/hold", "failed reclaim-and-hold"):
        assert ccw.is_trend_blocked({"eligible": False, "reason": text}), text


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
