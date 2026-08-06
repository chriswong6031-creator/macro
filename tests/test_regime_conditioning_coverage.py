"""Tests for engine/regime_conditioning_coverage.py — the regime-conditioning estimability meter.

All fixtures are SYNTHETIC and in-memory. Each test pins a specific way a regime-conditional
claim can look supported while being unsupportable; the meter exists to refuse exactly these.

Reference: reports/regime-reliability-phase0.md.
"""
from __future__ import annotations

import pandas as pd
import pytest

from engine import regime_conditioning_coverage as RCC


def _frame(states, months, n_per=50, axis="quad_hard_label", extra_rows=0):
    """Build a record where `states` are spread over `months` distinct months."""
    rows = []
    for i, st in enumerate(states):
        for m in range(months[i] if isinstance(months, list) else months):
            for k in range(n_per):
                rows.append({"date": pd.Timestamp("2020-01-01") + pd.DateOffset(months=m),
                             axis: st})
    for _ in range(extra_rows):                      # unstamped rows dilute coverage
        rows.append({"date": pd.Timestamp("2020-01-01"), axis: None})
    return pd.DataFrame(rows)


def test_single_state_axis_is_not_estimable():
    """THE core defect: one observed state is a constant, not a condition. A table built on
    it reads as a comparison while E[outcome | regime] is undefined off that cell."""
    df = _frame(["normalizing"], 60)          # 60 months, huge n, but ONE state
    r = RCC.assess_axis(df, "quad_hard_label")
    assert r["verdict"] == "single_state"
    assert r["estimable"] is False
    assert r["n_states"] == 1
    assert "undefined" in r["reason"]


def test_months_not_rows_are_the_independent_unit():
    """A 10,000-row axis confined to one month must FAIL. Same-day/same-month signals share
    one market; row count is not evidence. This is the 2,282-rows/18-days trap."""
    df = _frame(["Q1", "Q2"], months=1, n_per=5000)
    r = RCC.assess_axis(df, "quad_hard_label")
    assert r["n_rows_stamped"] == 10000          # plenty of rows ...
    assert r["verdict"] == "insufficient_contrast"   # ... and still not estimable
    assert r["estimable"] is False
    assert r["min_state_months"] == 1


def test_insufficient_coverage_fails_even_with_many_states():
    """An axis stamped on a sliver of the record cannot describe the record."""
    df = _frame(["Q1", "Q2", "Q3"], months=24, n_per=1, extra_rows=5000)
    r = RCC.assess_axis(df, "quad_hard_label")
    assert r["coverage"] < RCC.MIN_COVERAGE
    assert r["verdict"] == "insufficient_coverage"
    assert r["estimable"] is False


def test_estimable_axis_passes_all_three_gates():
    df = _frame(["bull", "bear", "choppy"], months=36, n_per=10)
    r = RCC.assess_axis(df, "quad_hard_label")
    assert r["verdict"] == "estimable"
    assert r["estimable"] is True
    assert r["n_states"] == 3
    assert r["min_state_months"] >= RCC.MIN_MONTHS_STATE


def test_thinnest_state_binds_not_the_average():
    """A comparison needs BOTH sides. One fat state cannot carry a starved counterpart."""
    df = pd.concat([_frame(["bull"], months=60, n_per=20),
                    _frame(["bear"], months=3, n_per=20)], ignore_index=True)
    r = RCC.assess_axis(df, "quad_hard_label")
    assert r["months_total"] >= 60           # the axis overall looks rich ...
    assert r["min_state_months"] == 3        # ... but the comparison side is starved
    assert r["verdict"] == "insufficient_contrast"
    assert "bear" in r["reason"]


@pytest.mark.parametrize("token", ["unknown", "", "none", "NaN", "n/a", "  "])
def test_placeholder_tokens_do_not_manufacture_contrast(token):
    """An 'unknown' row is an unstamped row wearing a label. Counting it as a second state
    would turn a single-state axis into a passing two-state axis."""
    df = pd.concat([_frame(["normalizing"], months=60, n_per=10),
                    _frame([token], months=60, n_per=10)], ignore_index=True)
    r = RCC.assess_axis(df, "quad_hard_label")
    assert r["n_states"] == 1, f"token {token!r} was counted as a real state"
    assert r["verdict"] == "single_state"


def test_missing_column_and_empty_frame_degrade_without_raising():
    df = _frame(["Q1", "Q2"], months=24)
    r = RCC.assess_axis(df, "no_such_axis")
    assert r["estimable"] is False and "absent" in r["reason"]

    r2 = RCC.assess_axis(df.iloc[0:0], "quad_hard_label")
    assert r2["estimable"] is False

    r3 = RCC.assess_axis(pd.DataFrame({"quad_hard_label": ["Q1"]}), "quad_hard_label")
    assert r3["estimable"] is False and "date" in r3["reason"]


def test_assess_reports_only_passing_axes_as_estimable():
    df = _frame(["bull", "bear"], months=36, n_per=10, axis="regime_at_entry")
    df["vol_regime"] = "normalizing"                     # single state
    rep = RCC.assess(df, axes=("regime_at_entry", "vol_regime"))
    assert rep["status"] == "ok"
    assert rep["estimable_axes"] == ["regime_at_entry"]
    assert rep["any_estimable"] is True
    assert rep["axes"]["vol_regime"]["verdict"] == "single_state"


def test_no_estimable_axis_is_reported_honestly():
    """When nothing is estimable the report must say so — the live 2026-08 state for every
    axis the external proposal specifies."""
    df = _frame(["Q1", "Q2"], months=1, n_per=100)
    df["vol_regime"] = "normalizing"
    rep = RCC.assess(df, axes=("quad_hard_label", "vol_regime"))
    assert rep["estimable_axes"] == []
    assert rep["any_estimable"] is False


def test_format_report_marks_pass_and_fail_distinctly():
    df = _frame(["bull", "bear"], months=36, n_per=10, axis="regime_at_entry")
    df["vol_regime"] = "normalizing"
    txt = RCC.format_report(RCC.assess(df, axes=("regime_at_entry", "vol_regime")))
    assert "[PASS] regime_at_entry" in txt
    assert "[----] vol_regime" in txt
    assert "single_state" in txt


def test_gate_constants_are_frozen():
    """These are pre-registered thresholds, not tunables. A silent loosening would let a
    starved axis publish a conditional claim."""
    assert (RCC.MIN_COVERAGE, RCC.MIN_STATES, RCC.MIN_MONTHS_STATE) == (0.20, 2, 12)
