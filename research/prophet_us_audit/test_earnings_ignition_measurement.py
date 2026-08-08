"""Targeted tests for the EARNINGS IGNITION cohort logic (ANTICIPATION §6.8(e)).

Scope, stated: this pins the DERIVED pieces — the knowability convention and the
loser/win arithmetic — because those are the instrument's load-bearing methodological
choices, not incidental plumbing. `signal_date` does not exist on this base, so the
"a marker's date is its 3D bucket's OPEN label, and it is actionable only at that
bucket's LAST session" rule is derived here; if it silently breaks, every cohort
boundary in the receipt moves and nothing else in CI would notice.

These tests are mutation-checked: each asserts a value that CHANGES if the convention
is altered (e.g. open-label instead of bucket-close), not merely that a call returns.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

_SPEC = importlib.util.spec_from_file_location(
    "earnings_ignition_measurement",
    Path(__file__).resolve().parent / "earnings_ignition_measurement.py",
)
mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mod)


@pytest.fixture(scope="module")
def sessions():
    return mod.load_sessions()


# ------------------------------------------------------------------ knowability rule

def test_knowability_is_the_bucket_last_session_not_the_open_label(sessions):
    """The whole cohort boundary rests on this. A marker labelled at a bucket's OPEN
    is knowable only at that bucket's CLOSE — so knowable >= label, always."""
    ref, pos_of = sessions
    for label in ("2015-01-21", "2019-10-17", "2026-07-31"):
        kp = mod.knowable_pos(label, pos_of, ref)
        assert kp is not None
        known = pd.Timestamp(str(ref[kp])[:10])
        assert known >= pd.Timestamp(label), f"{label} knowable earlier than its own label"


def test_three_consecutive_sessions_share_one_knowability_date(sessions):
    """A 3D bucket is exactly three sessions wide and they resolve together. If this
    ever returns three distinct dates the grid is no longer the 3D grid the markers
    were drawn on, and cohort membership is measuring a different instrument."""
    ref, pos_of = sessions
    start = int(ref.searchsorted(pd.Timestamp("2024-03-04"), side="left"))
    start -= start % mod.BUCKET_N  # align to a bucket open
    labels = [str(ref[start + i])[:10] for i in range(mod.BUCKET_N)]
    resolved = {str(ref[mod.knowable_pos(d, pos_of, ref)])[:10] for d in labels}
    assert len(resolved) == 1, f"{labels} -> {resolved}, expected one shared bucket close"
    assert resolved.pop() == str(ref[start + mod.BUCKET_N - 1])[:10]


def test_next_bucket_resolves_later_than_the_previous_one(sessions):
    """Adjacent buckets must not collapse — otherwise a lead-5 and a lead-0 marker
    would land in the same cohort cell."""
    ref, pos_of = sessions
    start = int(ref.searchsorted(pd.Timestamp("2024-03-04"), side="left"))
    start -= start % mod.BUCKET_N
    a = mod.knowable_pos(str(ref[start])[:10], pos_of, ref)
    b = mod.knowable_pos(str(ref[start + mod.BUCKET_N])[:10], pos_of, ref)
    assert b == a + mod.BUCKET_N


# --------------------------------------------------------------- cohort arithmetic

def _rows(vals, ticker="AAA"):
    return [{"ticker": ticker, "x": v, "anchor_date": f"2020-01-{i + 1:02d}"}
            for i, v in enumerate(vals)]


def test_loser_and_win_rates_use_the_stated_thresholds():
    """loser := excess <= -3pp (STATED); win := excess > 0. Boundary values are the
    test: -3.0 IS a loser (<=), 0.0 is NOT a win (>)."""
    cell = mod.summarize(_rows([-3.0, -2.9, 0.0, 0.1, 5.0]), "x")
    assert cell["n"] == 5
    assert cell["loser_rate_le_neg3pp"] == 20.0   # only -3.0
    assert cell["loser_rate_le_0"] == 60.0        # -3.0, -2.9, 0.0
    assert cell["win_rate"] == 40.0               # 0.1, 5.0


def test_thin_flag_trips_below_the_stated_floor():
    assert mod.summarize(_rows([1.0] * (mod.THIN_N - 1)), "x")["thin"] is True
    assert mod.summarize(_rows([1.0] * mod.THIN_N), "x")["thin"] is False


def test_per_name_first_is_not_the_pooled_mean():
    """One busy name must not carry a cohort. Pooled leans to the 3-row name; the
    per-name-first mean weights the two names equally."""
    rows = _rows([10.0, 10.0, 10.0], "BUSY") + _rows([0.0], "QUIET")
    cell = mod.summarize(rows, "x")
    assert cell["mean"] == 7.5
    assert cell["per_name_first_mean"] == 5.0
    assert cell["n_names"] == 2


def test_nulls_are_counted_not_silently_dropped():
    rows = _rows([1.0, 2.0]) + [{"ticker": "AAA", "x": None, "anchor_date": "2020-02-01"}]
    cell = mod.summarize(rows, "x")
    assert cell["n"] == 2 and cell["n_missing"] == 1


def test_empty_cell_reports_nulls_not_zeros():
    """A null must never render as 0.0 — that is a fabricated verdict."""
    cell = mod.summarize([], "x")
    assert cell["n"] == 0
    for k in ("mean", "median", "win_rate", "loser_rate_le_neg3pp", "per_name_first_mean"):
        assert cell[k] is None


def test_half_split_detects_a_sign_flip():
    flipped = mod.half_split(_rows([-5.0, -5.0, 5.0, 5.0]), "x")
    assert flipped["sign_stable"] is False
    stable = mod.half_split(_rows([2.0, 3.0, 4.0, 5.0]), "x")
    assert stable["sign_stable"] is True


def test_pct_guards_a_zero_base():
    assert mod.pct(100.0, 110.0) == pytest.approx(10.0)
    assert mod.pct(0.0, 10.0) is None
    assert mod.pct(None, 10.0) is None


# ------------------------------------------------------- announcement-window convention

def test_after_close_reports_shift_the_reaction_session():
    """An after-close print is read on T+1; a pre-open print on T. Collapsing the two
    would mis-sign roughly half of all reactions in the receipt."""
    assert mod._et_hour("2024-05-01T20:05:00Z") >= 16.0    # 16:05 ET -> after close
    assert mod._et_hour("2024-05-01T11:00:00Z") < 9.5      # 07:00 ET -> pre open
    assert 9.5 <= mod._et_hour("2024-05-01T18:00:00Z") < 16.0  # 14:00 ET -> intraday
    assert mod._et_hour("not-a-timestamp") is None
