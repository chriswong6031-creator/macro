"""Targeted tests for the EARNINGS IGNITION cohort logic (ANTICIPATION §6.8(e)).

Scope, stated: this pins the DERIVED pieces — the knowability convention and the
loser/win arithmetic — because those are the instrument's load-bearing methodological
choices, not incidental plumbing. `signal_date` does not exist on this base, so the
"a marker's date is its 3D bucket's OPEN label, and it is actionable only at that
bucket's LAST session" rule is derived here; if it silently breaks, every cohort
boundary in the receipt moves and nothing else in CI would notice.

These tests are mutation-checked: each asserts a value that CHANGES if the convention
is altered (e.g. open-label instead of bucket-close), not merely that a call returns.

v0.1 (2026-08-09) adds the corrections an adversarial re-read found, each pinned at the
point where it could regress:
  * the forward excess must be anchored on the REACTION session, not the report session
    (F1) -- pinned through `build_report_row`, the real call site, not through the helper
    it calls, so reverting the anchor reds the test instead of passing on indirection;
  * EDGAR's own filing_date roll must not be applied a second time (F4);
  * the ET hour must never smuggle a previous-day evening into a negative number (F5);
  * dispersion and the pairwise contrast must exist and must not fabricate bounds (F3).
Until v0.1 this file was never run by CI at all (F13) -- it is now wired into the
research-resident guards step in `.github/ci/legacy-jobs.yml`.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
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


def test_et_hour_never_returns_a_negative_hour(): # F5
    """A UTC stamp before 04:00 is the PREVIOUS ET day's evening. v0 returned it as a
    negative hour (01:00Z -> -3.0), which its `hour < 9.5` branch then read as
    'pre-open' -- losing the day entirely. The day now lives in the datetime."""
    assert mod._et_hour("2024-05-01T01:00:00Z") == pytest.approx(21.0)
    assert mod._et_datetime("2024-05-01T01:00:00Z").date().isoformat() == "2024-04-30"
    assert mod._et_hour("2024-05-01T20:05:00Z") == pytest.approx(16.0833, abs=1e-3)


def test_edgar_roll_is_not_applied_twice(): # F4
    """THE BUG THIS PINS: SEC advances `filing_date` to the next business day when
    acceptance lands after its cutoff, so a post-close acceptance arrives ALREADY dated
    to the session that reads it. v0 classified on the hour alone and rolled AGAIN,
    putting the reaction one session late on 794 of 16,720 in-universe rows.

    Same acceptance instant, two filing_dates -- and that is the whole difference."""
    acc = "2024-05-01T20:05:00Z"                       # 16:05 ET on 2024-05-01
    assert mod.classify_window(acc, "2024-05-01") == "after_close"   # not yet rolled
    assert mod.classify_window(acc, "2024-05-02") == "pre_open"      # EDGAR already rolled


def test_classify_window_reads_the_clock_when_filing_date_matches():
    assert mod.classify_window("2024-05-01T11:00:00Z", "2024-05-01") == "pre_open"
    assert mod.classify_window("2024-05-01T18:00:00Z", "2024-05-01") == "intraday"
    assert mod.classify_window(None, "2024-05-01") == "unknown"
    assert mod.classify_window("not-a-timestamp", "2024-05-01") == "unknown"


def test_reaction_position_shifts_only_for_after_close():
    assert mod.reaction_position(100, "after_close") == 101
    for w in ("pre_open", "intraday", "unknown"):
        assert mod.reaction_position(100, w) == 100


# --------------------------------------------------- F1: ONE anchor, not two (the big one)

def _flat_then_jump(ref, rp, jump_at, before=100.0, after=130.0):
    """A price series that is FLAT except for one step, so any cell that contains the
    step is unmistakable and any cell that does not is exactly 0."""
    idx = ref[rp - 20: rp + 40]
    vals = [before if d < ref[jump_at] else after for d in idx]
    return pd.Series(vals, index=idx, dtype=float)


def test_after_close_forward_excess_is_anchored_after_the_print(sessions):
    """THE F1 REGRESSION PIN, asserted at the real call site.

    v0 derived the reaction session from the announcement window, used it for
    `reaction_pct`, then anchored the forward excess at the REPORT session -- for an
    after-close print that is the close BEFORE the market has read the report, so H=5 and
    H=10 excess swallowed the reaction jump itself on ~39% of report-anchored rows.

    Here the whole move happens on the reaction session. A correctly anchored forward cell
    therefore sees NOTHING (the series is flat after the step) while the reaction sees all
    of it. Re-anchoring `build_report_row` at `report_pos` puts the +30 back into
    excess_h5 and reds this test -- which is the point: the helper alone cannot pin it.
    """
    ref, _ = sessions
    rp = 2000                       # interior position; deliberately not a date literal
    px = _flat_then_jump(ref, rp, jump_at=rp + 1)
    spy = pd.Series(100.0, index=ref[rp - 20: rp + 40], dtype=float)
    rec = {"date": str(ref[rp])[:10], "src": "edgar_8k", "window": "after_close"}

    row = mod.build_report_row("TEST", rp, rec, px, spy, ref)
    assert row["reaction_date"] == str(ref[rp + 1])[:10]
    assert row["reaction_pct"] == pytest.approx(30.0)      # the print IS the reaction
    assert row["excess_h5"] == pytest.approx(0.0)          # and is NOT in the forward cell
    assert row["excess_h10"] == pytest.approx(0.0)


def test_pre_open_forward_excess_starts_at_the_same_session(sessions):
    """The mirror case, so the fix cannot degenerate into 'always shift by one'. A
    pre-open print is read on session T, so a step on T+1 is genuinely AHEAD of the
    anchor and MUST appear in the forward cell."""
    ref, _ = sessions
    rp = 2000
    px = _flat_then_jump(ref, rp, jump_at=rp + 1)
    spy = pd.Series(100.0, index=ref[rp - 20: rp + 40], dtype=float)
    rec = {"date": str(ref[rp])[:10], "src": "edgar_8k", "window": "pre_open"}

    row = mod.build_report_row("TEST", rp, rec, px, spy, ref)
    assert row["reaction_date"] == str(ref[rp])[:10]
    assert row["reaction_pct"] == pytest.approx(0.0)       # nothing happened on T itself
    assert row["excess_h5"] == pytest.approx(30.0)         # the step is genuinely forward


# ------------------------------------------------------------- F3: dispersion + contrast

def test_summarize_prints_dispersion_and_never_fabricates_it():
    """A null with no interval cannot be told from an underpowered cell. A single
    observation has no dispersion at all, and printing 0.0 there would be a fabricated
    certainty -- it must stay null."""
    cell = mod.summarize(_rows([1.0, 2.0, 3.0, 4.0]), "x")
    assert cell["se"] == pytest.approx(np.std([1.0, 2.0, 3.0, 4.0], ddof=1) / 2.0, abs=1e-3)
    assert cell["ci95"][0] < cell["mean"] < cell["ci95"][1]
    assert cell["win_rate_ci95"][0] <= cell["win_rate"] <= cell["win_rate_ci95"][1]
    lone = mod.summarize(_rows([1.0]), "x")
    assert lone["se"] is None and lone["ci95"] is None


def test_wilson_interval_stays_inside_the_unit_interval():
    """Why Wilson and not the normal approximation: at the n<20 the quality and quarter
    splits actually run, a normal interval on a rate near 0 or 100 leaves [0, 100] and
    prints a bound that cannot exist."""
    lo, hi = mod.wilson_ci95(0, 5)
    assert lo >= 0.0 and hi <= 100.0
    lo, hi = mod.wilson_ci95(5, 5)
    assert lo >= 0.0 and hi <= 100.0
    assert mod.wilson_ci95(0, 0) is None


def test_contrast_calls_a_spanning_interval_indistinguishable():
    """The v0 defect this closes: 'reads slightly worse' stated as a bare point estimate,
    which cannot be falsified. Identical cohorts must read as indistinguishable, and a
    separated pair must not."""
    same = mod.contrast(_rows([1.0, 2.0, 3.0] * 10), _rows([1.0, 2.0, 3.0] * 10),
                        "x", "A", "B")
    assert same["diff"] == pytest.approx(0.0)
    assert same["ci95_diff"][0] <= 0 <= same["ci95_diff"][1]
    assert same["separation"].startswith("indistinguishable")
    apart = mod.contrast(_rows([10.0, 11.0, 12.0] * 10), _rows([1.0, 2.0, 3.0] * 10),
                         "x", "A", "B")
    assert apart["separation"] == "separated at 95%"


def test_mde_is_larger_than_the_interval_half_width():
    """MDE is the reason a null is readable: it must be the 80%-power floor, strictly
    wider than the 95% half-width, or it would understate what the cell could miss."""
    c = mod.contrast(_rows([1.0, 2.0, 3.0] * 10), _rows([1.0, 2.0, 3.0] * 10), "x", "A", "B")
    half_width = (c["ci95_diff"][1] - c["ci95_diff"][0]) / 2.0
    assert c["mde_80pct"] > half_width


def test_contrast_refuses_a_verdict_on_an_empty_cohort():
    empty = mod.contrast([], _rows([1.0, 2.0, 3.0]), "x", "A", "B")
    assert empty["diff"] is None and empty["separation"] is None and empty["thin"] is True
