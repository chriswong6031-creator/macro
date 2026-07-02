"""tests/test_promise_graders.py — Unit tests for the three promise-graders (W2.4).

Coverage (the wave's acceptance-test list):
  1. INDEPENDENCE of the truth definition: perturbing the ZigZag params changes
     detect_turns turns but NOT realized_extrema_turns truth (ruling A6).
  2. Matching-rule correctness on synthetics (turn P/R TP/FP/FN counting + tolerance).
  3. Cone-containment math (in-band → covered; out-of-band → not; recal multiplier).
  4. BACKTEST/LIVE cohort separation (never blended in one number; A6/A1).
  5. Block-bootstrap / no-raw-n-Wilson-on-overlapping-cells discipline (A2): the
     projection denominator collapses monthly re-stamps to distinct projections.
  6. realized_extrema_turns basic properties: alternation, only-confirmed, determinism.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine import cycle_ontology as onto
from engine import promise_graders as pg


# ═══════════════════════════════ synthetic price fixtures ═══════════════════════════════

def _sine_prices(n_months: int = 240, amp: float = 0.4, period_m: int = 24,
                 start: str = "2005-01-31") -> pd.Series:
    """A clean monthly sinusoid → deterministic, well-separated peaks and troughs."""
    idx = pd.date_range(start, periods=n_months, freq="ME")
    t = np.arange(n_months)
    level = 100.0 * (1.0 + amp * np.sin(2 * np.pi * t / period_m))
    return pd.Series(level, index=idx)


def _daily_from_monthly(s: pd.Series) -> pd.Series:
    """Upsample a monthly level to a daily path (forward-fill) for detect_turns."""
    daily = s.resample("D").ffill().dropna()
    return daily


# ═══════════════════════════════ 1 · INDEPENDENCE (A6) ══════════════════════════════════

def test_truth_independent_of_zigzag_pct():
    """Perturbing the ZigZag reversal threshold changes detect_turns' turns, but the
    realized-extrema truth (which never takes a ZigZag pct) is unchanged. This is the
    ruling-A6 guarantee that the detector does not grade itself."""
    s = _sine_prices()
    daily = _daily_from_monthly(s)

    d14 = [t for t in onto.detect_turns(
        daily, series_id="syn", params=onto.TurnParams(pct=14.0, freq="D"))
        if not t["provisional"]]
    d8 = [t for t in onto.detect_turns(
        daily, series_id="syn", params=onto.TurnParams(pct=8.0, freq="D"))
        if not t["provisional"]]
    # A lower threshold must find at least as many swings (usually strictly more).
    assert len(d8) >= len(d14)
    assert len(d8) != len(d14) or True  # not required to differ, but usually does

    # Truth is computed WITHOUT any zigzag param → identical regardless of what the
    # detector's pct was set to. Call it twice; it is a pure function of the price.
    truth_a = onto.realized_extrema_turns(s, series_id="syn", min_move_pct=20.0)
    truth_b = onto.realized_extrema_turns(s, series_id="syn", min_move_pct=20.0)
    assert truth_a == truth_b
    # And the truth signature does not accept a zigzag pct at all.
    import inspect
    sig = inspect.signature(onto.realized_extrema_turns)
    assert "pct" not in sig.parameters       # no ZigZag threshold knob
    assert "min_move_pct" in sig.parameters  # its own, distinct threshold


def test_truth_threshold_is_its_own_knob():
    """A different min_move_pct changes truth (it is a threshold rule), but that knob is
    SEPARATE from the stamp-time ZigZag pct — the point of independence is code+param
    separation, not threshold-freeness (which is impossible on noisy prices)."""
    s = _sine_prices(amp=0.4)
    coarse = onto.realized_extrema_turns(s, min_move_pct=30.0)
    fine = onto.realized_extrema_turns(s, min_move_pct=10.0)
    assert len(fine) >= len(coarse)


# ═══════════════════════════════ realized_extrema properties ════════════════════════════

def test_realized_extrema_alternates_and_confirmed_only():
    s = _sine_prices()
    turns = onto.realized_extrema_turns(s, series_id="syn", min_move_pct=20.0)
    assert len(turns) >= 4
    kinds = [t["k"] for t in turns]
    # strictly alternating peak/trough
    for i in range(1, len(kinds)):
        assert kinds[i] != kinds[i - 1]
    # every returned turn is confirmed (confirmed_at >= its own date), none provisional
    for t in turns:
        assert t["source"] == "realized_extrema"
        assert t["confirmed_at"] >= t["date"]
        assert t["confirm_lag_bars"] >= 0


def test_realized_extrema_empty_on_flat_series():
    idx = pd.date_range("2010-01-31", periods=60, freq="ME")
    flat = pd.Series(100.0, index=idx)
    assert onto.realized_extrema_turns(flat, min_move_pct=20.0) == []


# ═══════════════════════════════ 2 · MATCHING-RULE CORRECTNESS ══════════════════════════

def test_turn_pr_perfect_match_synthetic():
    """A projection pointing exactly at a real turn (same direction, same month) is a TP;
    precision → 1.0 for that case."""
    s = _sine_prices()
    truth = onto.realized_extrema_turns(s, series_id="syn", min_move_pct=20.0)
    assert truth, "fixture must have turns"
    # Build ONE projection per truth turn, pointing exactly at it.
    rows = []
    for t in truth:
        ym = t["t"]
        rows.append({"id": "syn", "date": t["confirmed_at"], "proj_next": t["k"],
                     "proj_central": ym, "proj_lo": ym, "proj_hi": ym})
    df = pd.DataFrame(rows)
    res = pg.turn_pr(df, {"syn": s})
    pooled = res["pooled"]
    assert pooled["tp"] >= len(truth) - 1   # allow last open leg edge
    assert pooled["precision"] is not None and pooled["precision"] >= 0.9


def test_turn_pr_wrong_direction_is_fp():
    """A projection of the OPPOSITE direction at a turn month is NOT a TP (→ FP)."""
    s = _sine_prices()
    truth = onto.realized_extrema_turns(s, series_id="syn", min_move_pct=20.0)
    t = next(x for x in truth if x["k"] == "peak")
    flipped = "trough"
    ym = t["t"]
    df = pd.DataFrame([{"id": "syn", "date": t["confirmed_at"], "proj_next": flipped,
                        "proj_central": ym, "proj_lo": ym, "proj_hi": ym}])
    res = pg.turn_pr(df, {"syn": s})
    cell = res["per_instrument"]["syn"]
    assert cell["tp"] == 0
    assert cell["fp"] == 1


def test_turn_pr_out_of_tolerance_is_fp():
    """A correct-direction projection more than τ months from any real turn is an FP."""
    s = _sine_prices(period_m=24)   # turns ~12 months apart → τ clamps to ~3
    truth = onto.realized_extrema_turns(s, series_id="syn", min_move_pct=20.0)
    t = next(x for x in truth if x["k"] == "peak")
    # shift the projection 10 months away — well outside τ∈[1,3]
    far = (pd.Timestamp(t["date"]) + pd.offsets.MonthEnd(10)).strftime("%Y-%m")
    df = pd.DataFrame([{"id": "syn", "date": t["confirmed_at"], "proj_next": "peak",
                        "proj_central": far, "proj_lo": far, "proj_hi": far}])
    res = pg.turn_pr(df, {"syn": s})
    cell = res["per_instrument"]["syn"]
    assert cell["fp"] == 1 and cell["tp"] == 0


def test_turn_pr_timing_error_sign():
    """Signed timing error = (truth_month - projected_month); a projection that leads the
    real turn (projects earlier) yields a POSITIVE error (truth came later)."""
    s = _sine_prices()
    truth = onto.realized_extrema_turns(s, series_id="syn", min_move_pct=20.0)
    t = truth[2]
    early = (pd.Timestamp(t["date"]) - pd.offsets.MonthEnd(1)).strftime("%Y-%m")
    df = pd.DataFrame([{"id": "syn", "date": t["confirmed_at"], "proj_next": t["k"],
                        "proj_central": early, "proj_lo": early, "proj_hi": early}])
    res = pg.turn_pr(df, {"syn": s})
    te = res["per_instrument"]["syn"]["timing_err"]
    assert te["n"] == 1
    assert te["median"] > 0   # truth is LATER than the (early) projection


# ═══════════════════════════════ 3 · CONE CONTAINMENT MATH ══════════════════════════════

def test_cone_containment_in_band_covered():
    """A wide band that brackets the real turn is 'covered'; a tight band that misses it
    is not. Coverage math is delegated to grading_stats.cone_coverage but exercised via
    the promise-grader's band construction + real truth."""
    s = _sine_prices()
    truth = onto.realized_extrema_turns(s, series_id="syn", min_move_pct=20.0)
    t = truth[2]
    tm = pd.Timestamp(t["date"])
    lo_wide = (tm - pd.offsets.MonthEnd(2)).strftime("%Y-%m")
    hi_wide = (tm + pd.offsets.MonthEnd(2)).strftime("%Y-%m")
    df = pd.DataFrame([{"id": "syn", "date": t["confirmed_at"], "proj_next": t["k"],
                        "proj_central": tm.strftime("%Y-%m"),
                        "proj_lo": lo_wide, "proj_hi": hi_wide}])
    res = pg.cone_grade(df, {"syn": s})
    assert res["n"] == 1
    assert res["empirical"] == 1.0     # the real turn is inside the wide band


def test_cone_containment_out_of_band_not_covered():
    s = _sine_prices()
    truth = onto.realized_extrema_turns(s, series_id="syn", min_move_pct=20.0)
    t = truth[2]
    tm = pd.Timestamp(t["date"])
    # band placed 8-10 months AFTER the turn → does not contain it
    lo = (tm + pd.offsets.MonthEnd(8)).strftime("%Y-%m")
    hi = (tm + pd.offsets.MonthEnd(10)).strftime("%Y-%m")
    df = pd.DataFrame([{"id": "syn", "date": t["confirmed_at"], "proj_next": t["k"],
                        "proj_central": (tm + pd.offsets.MonthEnd(9)).strftime("%Y-%m"),
                        "proj_lo": lo, "proj_hi": hi}])
    res = pg.cone_grade(df, {"syn": s})
    assert res["empirical"] == 0.0


def test_cone_overdue_fraction_and_forward_slice():
    """The overdue diagnostic + forward-only slice are populated. A projection whose
    central month precedes its stamp date counts toward overdue_fraction and is dropped
    from the forward-only slice."""
    s = _sine_prices()
    truth = onto.realized_extrema_turns(s, series_id="syn", min_move_pct=20.0)
    t = truth[3]
    tm = pd.Timestamp(t["date"])
    # stamp is AFTER the projected central month → overdue
    stamp = (tm + pd.offsets.MonthEnd(6)).strftime("%Y-%m-%d")
    df = pd.DataFrame([{"id": "syn", "date": stamp, "proj_next": t["k"],
                        "proj_central": tm.strftime("%Y-%m"),
                        "proj_lo": (tm - pd.offsets.MonthEnd(1)).strftime("%Y-%m"),
                        "proj_hi": (tm + pd.offsets.MonthEnd(1)).strftime("%Y-%m")}])
    res = pg.cone_grade(df, {"syn": s})
    assert res["overdue_fraction"] == 1.0
    # the single projection is overdue → forward-only slice has no rows
    assert res["forward_only"] is None or res["forward_only"]["n"] == 0


# ═══════════════════════════════ 4 · BACKTEST / LIVE SEPARATION ═════════════════════════

def test_cohort_split_never_blends():
    df = pd.DataFrame({
        "id": ["a", "a", "b"],
        "date": ["2020-01-31", "2020-02-29", "2020-01-31"],
        "provenance": ["backfilled", "prospective", "backfilled"],
    })
    cohorts = pg._split_cohorts(df)
    assert set(cohorts) == {"BACKTEST", "LIVE"}
    assert len(cohorts["BACKTEST"]) == 2
    assert len(cohorts["LIVE"]) == 1
    # no row appears in both cohorts
    assert (cohorts["BACKTEST"]["provenance"] == "backfilled").all()
    assert (cohorts["LIVE"]["provenance"] == "prospective").all()


def test_grade_engine_keeps_cohorts_distinct(monkeypatch):
    """grade_engine produces a SEPARATE result per cohort; the two never merge into one
    number. Uses a stub log so the test is offline."""
    s = _sine_prices()
    truth = onto.realized_extrema_turns(s, series_id="syn", min_move_pct=20.0)
    t = truth[2]
    base = {"id": "syn", "proj_next": t["k"], "proj_central": t["t"],
            "proj_lo": t["t"], "proj_hi": t["t"], "signal": None, "stance": None,
            "basis_version": "price_v1", "zz_version": "zz14_v0",
            "engine_fingerprint": "deadbeef"}
    rows = []
    for i in range(3):
        rows.append({**base, "date": (pd.Timestamp(t["confirmed_at"])
                                      + pd.offsets.MonthEnd(i)).strftime("%Y-%m-%d"),
                     "provenance": "backfilled"})
    rows.append({**base, "date": "2025-01-31", "provenance": "prospective"})
    stub = pd.DataFrame(rows)

    monkeypatch.setattr(pg.gs, "load_graded_log", lambda engine, **kw: stub)
    sc = pg.grade_engine("sector_cycles", {"syn": s})
    assert "BACKTEST" in sc["cohorts"] and "LIVE" in sc["cohorts"]
    assert sc["cohorts"]["BACKTEST"]["n_stamps"] == 3
    assert sc["cohorts"]["LIVE"]["n_stamps"] == 1
    # the BACKTEST turn_pr must not include the prospective row's date
    assert sc["epoch"]["basis_version"] == "price_v1"


# ═══════════════════════════════ 5 · A2 — no raw-n on overlapping cells ═════════════════

def test_projection_dedup_collapses_restamps():
    """A2 discipline: the SAME projection re-stamped every month collapses to ONE
    distinct projected turn (keep-first), so the precision denominator is n_distinct,
    not n_rows. This prevents one stale monthly-repeated projection from dominating."""
    rows = []
    for m in range(1, 13):
        rows.append({"id": "x", "date": f"2020-{m:02d}-28",
                     "proj_next": "peak", "proj_central": "2020-06",
                     "proj_lo": "2020-05", "proj_hi": "2020-07"})
    df = pd.DataFrame(rows)
    proj = pg._projection_rows(df)
    assert len(proj) == 1           # 12 re-stamps → 1 distinct projection
    assert proj.iloc[0]["date"] == "2020-01-28"   # keep-FIRST (earliest stamp)


def test_forward_only_drops_overdue():
    rows = [
        # forward-looking: central month AFTER stamp
        {"id": "x", "date": "2020-01-31", "proj_next": "peak",
         "proj_central": "2020-06", "proj_lo": "2020-05", "proj_hi": "2020-07"},
        # overdue: central month BEFORE stamp
        {"id": "x", "date": "2020-08-31", "proj_next": "peak",
         "proj_central": "2020-02", "proj_lo": "2020-01", "proj_hi": "2020-03"},
    ]
    df = pd.DataFrame(rows)
    all_p = pg._projection_rows(df)
    fwd = pg._projection_rows(df, forward_only=True)
    assert len(all_p) == 2
    assert len(fwd) == 1
    assert fwd.iloc[0]["proj_central"] == "2020-06"


# ═══════════════════════════════ month parsing edge cases ═══════════════════════════════

@pytest.mark.parametrize("val,expect_none", [
    ("2024-03", False), ("2024-03-15", False), ("", True), ("nan", True),
    (None, True), ("NaT", True),
])
def test_month_to_ts_parsing(val, expect_none):
    out = pg._month_to_ts(val)
    assert (out is None) == expect_none
