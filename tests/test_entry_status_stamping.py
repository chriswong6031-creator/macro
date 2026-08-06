"""entry_status disclosure law — no freshly-graded ledger row carries a silent null.

Battery §1 (research/prophet_us_audit, PR #4547) found 177/403 matured buy-lane
rows (43.9%) in retro_grades.parquet with NO entry_status — and that unstamped
cohort was the worst-performing cell (35.0% loser rate vs 25.8% base). Root
cause: the three pre-instrumentation boards (2026-06-15..17) predate the entry
gauge shipping to board rows, and the grader resolved their absence to a silent
None. The law this file pins:

  every row grade_boards emits carries entry_status non-null OR
  entry_status_reason non-null — never both null.

The guarantee is FAIL-CLOSED at the grader: even a board row with neither the
gauge nor a writer-stamped reason grades with reason="unstamped_at_publish".
Writer-side stamps (engine.entry_signal.null_reason, the ran-lane
"lane_not_stamped") only sharpen the reason — their absence can never
reintroduce a silent null.

Historical rows are exempt by design (schema-union nulls; PIT law — entry_status
is never backfilled, and the reason column describes the frozen artifact, never
a recomputed label).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import entry_signal  # noqa: E402
from scripts.grade_us_board import (  # noqa: E402
    _board_to_record,
    _row_features,
    _v2_board_to_record,
    grade_boards,
)

# ── fixed synthetic market (no wall-clock: dates are pinned, maturity is eternal) ──
_DATES = pd.bdate_range("2026-01-02", periods=130)
_RNG = np.random.default_rng(7)


def _series(drift: float = 0.0005) -> pd.Series:
    steps = _RNG.normal(drift, 0.01, len(_DATES))
    return pd.Series(100.0 * np.exp(np.cumsum(steps)), index=_DATES)


# --------------------------------------------------------------------------- #
# 1. engine.entry_signal.null_reason mirrors assess()'s self-gates exactly
# --------------------------------------------------------------------------- #
def test_null_reason_names_the_no_ladder_gate():
    close = _series()
    rec: dict = {}  # no ladder at all
    assert entry_signal.assess(close, None, rec) is None
    assert entry_signal.null_reason(close, rec) == "no_cycle_ladder"
    rec = {"ladder": {"state": None}}  # ladder present, state missing
    assert entry_signal.assess(close, None, rec) is None
    assert entry_signal.null_reason(close, rec) == "no_cycle_ladder"


def test_null_reason_names_the_short_history_gate():
    close = _series().tail(30)  # < 60 closes
    rec = {"ladder": {"state": "UPTREND", "entry": {"urgency": "hold"}}}
    assert entry_signal.assess(close, None, rec) is None
    assert entry_signal.null_reason(close, rec) == "short_history"


def test_assess_gates_are_exhaustive_so_not_assessed_stays_unreachable():
    # ladder state present + >=60 closes => assess returns a dict with a status;
    # if this ever returns None, assess grew a self-gate the null_reason mirror
    # does not name — rows would fall to "not_assessed" (still disclosed), and
    # this test fails to force the mirror update.
    close = _series()
    rec = {"ladder": {"state": "UPTREND", "entry": {"urgency": "hold"},
                      "eq_score": 10, "eq_grade": "C", "bottom_confidence": 40}}
    out = entry_signal.assess(close, None, rec)
    assert isinstance(out, dict) and out.get("status")


# --------------------------------------------------------------------------- #
# 2. _row_features: reason resolution priority + the invariant at extraction
# --------------------------------------------------------------------------- #
def test_row_features_status_present_means_no_reason():
    feat = _row_features({"ticker": "AAA", "entry_signal": {"status": "buy_now"}})
    assert feat["entry_status"] == "buy_now"
    assert feat["entry_status_reason"] is None


def test_row_features_writer_reason_wins_over_fallback():
    feat = _row_features({"ticker": "BBB",
                          "entry_signal_null_reason": "short_history"})
    assert feat["entry_status"] is None
    assert feat["entry_status_reason"] == "short_history"
    feat = _row_features({"ticker": "RAN",
                          "entry_signal_null_reason": "lane_not_stamped"})
    assert feat["entry_status_reason"] == "lane_not_stamped"


def test_row_features_bare_row_falls_back_to_unstamped_at_publish():
    # the pre-instrumentation shape (boards 2026-06-15..17): no gauge, no reason
    feat = _row_features({"ticker": "CCC"})
    assert feat["entry_status"] is None
    assert feat["entry_status_reason"] == "unstamped_at_publish"
    # malformed gauge without a status is still a disclosed null, never silent
    feat = _row_features({"ticker": "DDD", "entry_signal": {}})
    assert feat["entry_status"] is None
    assert feat["entry_status_reason"] == "unstamped_at_publish"


def test_board_to_record_rows_all_satisfy_status_or_reason():
    board = {
        "as_of": "2026-07-01",
        "buy": [{"ticker": "AAA", "entry_signal": {"status": "partial"}},
                {"ticker": "BBB", "entry_signal_null_reason": "short_history"},
                {"ticker": "CCC"}],
        "ran": [{"ticker": "RRR", "entry_signal_null_reason": "lane_not_stamped"}],
        "laggard": [{"ticker": "LLL"}],
    }
    rec = _board_to_record(board)
    assert rec and len(rec["rows"]) == 5
    for feat in rec["rows"]:
        assert (feat["entry_status"] is not None) or (
            feat["entry_status_reason"] is not None), feat["ticker"]


def test_v2_board_rows_share_the_same_invariant():
    rec = _v2_board_to_record({
        "as_of": "2026-07-01",
        "lanes": {"entry_open": [{"ticker": "AAA",
                                  "entry_signal": {"status": "buy_now"}},
                                 {"ticker": "BBB"}]},
    })
    assert rec and len(rec["rows"]) == 2
    for feat in rec["rows"]:
        assert (feat["entry_status"] is not None) or (
            feat["entry_status_reason"] is not None), feat["ticker"]


# --------------------------------------------------------------------------- #
# 3. the law itself: every row grade_boards emits carries status-or-reason
# --------------------------------------------------------------------------- #
def test_every_freshly_graded_row_carries_entry_status_or_reason():
    names = pd.DataFrame({"TSA": _series(), "TSB": _series(), "TSC": _series()})
    etfs = pd.DataFrame({"SPY": _series(0.0003)})
    as_of = _DATES[-30].date().isoformat()  # 5/10/21d mature, 63d never
    board = _board_to_record({
        "as_of": as_of,
        "buy": [{"ticker": "TSA", "entry_signal": {"status": "hold"}},
                {"ticker": "TSB"}],  # pre-instrumentation shape
        "ran": [{"ticker": "TSC",
                 "entry_signal_null_reason": "lane_not_stamped"}],
    })
    df = grade_boards([board], names, etfs, _stored_df=None)
    assert not df.empty, "synthetic board produced no matured rows"
    assert "entry_status_reason" in df.columns
    silent = df[df["entry_status"].isna() & df["entry_status_reason"].isna()]
    assert silent.empty, f"silent entry_status nulls: {silent[['ticker', 'horizon']]}"
    # stamped rows carry no reason; unstamped rows carry the right one
    tsa = df[df["ticker"] == "TSA"]
    assert (tsa["entry_status"] == "hold").all() and tsa["entry_status_reason"].isna().all()
    tsb = df[df["ticker"] == "TSB"]
    assert (tsb["entry_status_reason"] == "unstamped_at_publish").all()
    tsc = df[df["ticker"] == "TSC"]
    assert (tsc["entry_status_reason"] == "lane_not_stamped").all()
    assert (tsc["lane"] == "ran").all()
