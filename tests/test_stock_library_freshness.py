"""Scan-side feed-freshness demotion (scripts/build_stock_library.py::_feed_freshness /
_apply_feed_demotion) — research/ADJUDICATION_20260803_UNIVERSE_SIDE_STORE_FRESHNESS.md
rulings R1/R2.

A full rec whose own `asof` lags the library's own max tip by more than the SAME
7-calendar-day law the ledger admission gate already enforces
(engine.name_score_grader._MAX_BAR_LAG_DAYS) loses scoring authority but keeps its
page — CTRA/TPH/TCNNF/CWEN-A were frozen for weeks and still stamped as live
authority before this gate existed. No network; every rec here is a hand-built dict.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import build_stock_library as bsl  # noqa: E402


def _full(ticker: str, asof: str, *, score: int = 55) -> dict:
    """A minimal FULL rec — enough for _feed_freshness + _apply_feed_demotion +
    _collect_potential_calls to all operate on it."""
    return {
        "ticker": ticker,
        "asof": asof,
        "tech": {"price": 42.5},
        "conviction": {"potential": {
            "score": score, "tier": "setting_up",
            "call": {"ticker": ticker, "score": score, "tier": "setting_up",
                     "fuel": 0.6, "trigger": 0.9},
        }},
    }


def _limited(ticker: str, asof: str) -> dict:
    return {"ticker": ticker, "asof": asof, "limited": True, "ladder": {"state": "LIMITED"}}


# ---------------------------------------------------------------------------
# _feed_freshness
# ---------------------------------------------------------------------------

def test_seven_days_kept_eight_days_demoted():
    """The boundary is STRICT >7 — exactly 7 calendar days behind stays live (the
    real NYSE-calendar worst case, per _MAX_BAR_LAG_DAYS's own docstring), 8 demotes."""
    recs = [
        _full("LIB", "2026-08-05"),   # sets the library tip
        _full("SEVEN", "2026-07-29"),  # exactly 7 days behind -> kept
        _full("EIGHT", "2026-07-28"),  # 8 days behind -> demoted
    ]
    # pad with fresh recs so the single demotion stays under the 20% breaker
    recs += [_full(f"FRESH{i}", "2026-08-05") for i in range(6)]
    lib_asof, demoted, n_dark = bsl._feed_freshness(recs)
    assert lib_asof == "2026-08-05"
    assert "SEVEN" not in demoted
    assert demoted == {"EIGHT": 8}
    assert n_dark == 0


def test_crypto_led_max_tip_is_the_reference():
    """A 24/7 crypto tip a couple of days ahead of the equity pack becomes lib_asof —
    equities on the same weekday close then read as (correctly) a bit behind it,
    but still well inside the 7-day window."""
    recs = [
        _full("BTC-USD", "2026-08-05"),   # weekend tip, leads the pack
        _full("AAPL", "2026-08-03"),      # Friday close, 2 days behind -> kept
    ]
    lib_asof, demoted, n_dark = bsl._feed_freshness(recs)
    assert lib_asof == "2026-08-05"
    assert demoted == {}
    assert n_dark == 0


def test_unparseable_asof_is_fail_open_and_counted_dark():
    recs = [
        _full("LIB", "2026-08-05"),
        {**_full("GARBAGE", "not-a-date")},
        {**_full("MISSING", None)},
    ]
    lib_asof, demoted, n_dark = bsl._feed_freshness(recs)
    assert lib_asof == "2026-08-05"
    assert "GARBAGE" not in demoted and "MISSING" not in demoted
    assert n_dark == 2


def test_limited_recs_are_never_considered():
    """A LIMITED rec has no comparable asof depth (R1 invariant I4) — it must never
    move lib_asof and must never itself demote, however stale its own asof is."""
    recs = [
        _full("LIB", "2026-08-05"),
        _limited("BRANDNEW", "2020-01-01"),   # wildly "behind" but exempt
        None,                                  # a failed _one_task() entry
    ]
    lib_asof, demoted, n_dark = bsl._feed_freshness(recs)
    assert lib_asof == "2026-08-05"
    assert demoted == {}
    assert n_dark == 0


def test_circuit_breaker_disarms_above_20pct_and_warns(capsys):
    """21 full recs, 5 demoted (5/21 = 23.8% > 20%) -> gate disarms, empty map, and
    the disarm is disclosed with a bare ::warning naming the fraction (CSP-R1: a
    universe-wide freeze reads as a collector outage, not per-name staleness)."""
    recs = [_full("LIB", "2026-08-05")]
    for i in range(15):
        recs.append(_full(f"FRESH{i}", "2026-08-04"))   # 1 day behind -> kept
    for i in range(5):
        recs.append(_full(f"STALE{i}", "2026-07-20"))   # 16 days behind -> would demote
    assert len(recs) == 21
    lib_asof, demoted, n_dark = bsl._feed_freshness(recs)
    assert lib_asof == "2026-08-05"
    assert demoted == {}, "breaker must return an EMPTY map, never a partial one"
    out = capsys.readouterr().out
    lines = [ln for ln in out.splitlines() if ln.startswith("::")]
    assert lines, "circuit breaker must print a bare ::warning"
    assert any("warning" in ln and "disarm" in ln.lower() for ln in lines)
    assert any("5/21" in ln for ln in lines) and any("24%" in ln for ln in lines)


def test_circuit_breaker_stays_armed_at_exactly_20pct():
    """20/100 demoting is AT the threshold, not over it — `> 0.20` must not trip
    on equality (an off-by-one here would disarm the gate one name early forever)."""
    recs = [_full("LIB", "2026-08-05")]
    for i in range(80):
        recs.append(_full(f"FRESH{i}", "2026-08-04"))
    for i in range(20):
        recs.append(_full(f"STALE{i}", "2026-07-20"))
    _, demoted, _ = bsl._feed_freshness(recs)
    assert len(demoted) == 20


# ---------------------------------------------------------------------------
# _apply_feed_demotion
# ---------------------------------------------------------------------------

def test_apply_feed_demotion_sets_feed_stale_and_strips_potential():
    rec = _full("CTRA", "2026-05-07")
    bsl._apply_feed_demotion(rec, 90, "2026-08-05")
    assert rec["feed_stale"] == {"behind_days": 90, "lib_asof": "2026-08-05"}
    assert "potential" not in rec["conviction"]
    # the rest of the rec (page-facing chips) is untouched (I1)
    assert rec["tech"]["price"] == 42.5
    assert rec["ticker"] == "CTRA"


def test_demoted_rec_yields_no_potential_calls():
    """I3: after demotion, _collect_potential_calls must emit nothing for the name —
    the grader's own bar_asof gate is only the SECOND line of defense."""
    rec = _full("TPH", "2026-05-13")
    bsl._apply_feed_demotion(rec, 84, "2026-08-05")
    live = _full("FRESH", "2026-08-05")
    calls = bsl._collect_potential_calls([("tph", rec), ("fresh", live)])
    tickers = {c["ticker"] for c in calls}
    assert "TPH" not in tickers
    assert "FRESH" in tickers
