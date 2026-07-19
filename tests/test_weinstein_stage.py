"""Tests for the Weinstein 4-stage classifier (SGA-R1).

Synthetic weekly-shaped price paths are built on daily Friday-anchored dates so
the completed-week W-FRI resample keeps every bar. Each path exercises one
ruling clause: the clean 1->2->3->4 round trip, hysteresis (flat after S2 = S3,
flat after S4 = S1), freshness, the volume-gated breakout event, the too-young
and missing-volume paths, NaN robustness, arc_pos banding, and weeks_in_stage.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine import weinstein_stage as ws


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _weekly_index(n: int) -> pd.DatetimeIndex:
    """n consecutive Fridays (W-FRI grid points)."""
    return pd.date_range("2015-01-02", periods=n, freq="W-FRI")


def _series(vals) -> pd.Series:
    vals = list(vals)
    return pd.Series(vals, index=_weekly_index(len(vals)), dtype=float)


def _flat_bench(n: int, level: float = 100.0) -> pd.Series:
    """A benchmark that drifts gently up (so Mansfield RS is well-defined)."""
    return _series(level + 0.05 * np.arange(n))


def _round_trip_close() -> pd.Series:
    """A clean 1->2->3->4 cycle: base, advance, top, decline.

    ~50 weeks per phase so the 30w SMA and 5w slope have room to develop the
    flat/rising/falling regimes the machine keys on.
    """
    seg = 60
    base = np.full(seg, 100.0) + np.random.default_rng(0).normal(0, 0.05, seg)
    advance = np.linspace(100.0, 200.0, seg)          # strong uptrend
    top = np.full(seg, 200.0) + np.random.default_rng(1).normal(0, 0.05, seg)
    decline = np.linspace(200.0, 110.0, seg)          # downtrend
    return _series(np.concatenate([base, advance, top, decline]))


# ---------------------------------------------------------------------------
# 1. clean 4-stage round trip visits 1,2,3,4 in order
# ---------------------------------------------------------------------------
def test_round_trip_visits_all_stages_in_order():
    close = _round_trip_close()
    n = len(close)
    ss = ws.stage_series(close, None, _flat_bench(n))
    seq = [int(s) for s in ss.tolist() if s != 0]
    # first appearance order of each stage
    order = []
    for s in seq:
        if s not in order:
            order.append(s)
    # must contain the full cycle in ascending order (possibly starting at 1)
    assert order == [1, 2, 3, 4] or order == [2, 3, 4] or order[:4] == [1, 2, 3, 4]
    assert set(seq) >= {1, 2, 3, 4}


def test_round_trip_final_stage_is_four():
    close = _round_trip_close()
    n = len(close)
    res = ws.classify(close, None, _flat_bench(n))
    assert res["too_young"] is False
    assert res["stage"] == 4
    assert res["pct_vs_ma30"] is not None and res["pct_vs_ma30"] < 0


# ---------------------------------------------------------------------------
# 2. hysteresis — flat after S2 = S3
# ---------------------------------------------------------------------------
def test_flat_after_stage2_is_stage3():
    seg = 60
    advance = np.linspace(100.0, 200.0, seg)
    plateau = np.full(seg, 200.0)  # ma30 catches up, slope goes flat, close ~= ma30
    close = _series(np.concatenate([advance, plateau]))
    n = len(close)
    ss = ws.stage_series(close, None, _flat_bench(n))
    # the last bar should be Stage 3 (flat arriving from an advance)
    assert int(ss.iloc[-1]) == 3
    res = ws.classify(close, None, _flat_bench(n))
    assert res["stage"] == 3


# ---------------------------------------------------------------------------
# 3. hysteresis — flat after S4 = S1
# ---------------------------------------------------------------------------
def test_flat_after_stage4_is_stage1():
    seg = 60
    decline = np.linspace(200.0, 110.0, seg)
    base = np.full(seg, 110.0)  # ma30 catches down, slope flattens below-then-at price
    close = _series(np.concatenate([decline, base]))
    n = len(close)
    ss = ws.stage_series(close, None, _flat_bench(n))
    assert int(ss.iloc[-1]) == 1
    res = ws.classify(close, None, _flat_bench(n))
    assert res["stage"] == 1


# ---------------------------------------------------------------------------
# 4. freshness — a young Stage 2 (<=10wk) is fresh; a mature one is not
# ---------------------------------------------------------------------------
def test_fresh_stage2_flag():
    # long base, then a short, strong advance so weeks_in_stage stays small
    base = np.full(70, 100.0)
    advance = np.linspace(100.0, 140.0, 12)  # ~12 weeks up
    close = _series(np.concatenate([base, advance]))
    n = len(close)
    res = ws.classify(close, None, _flat_bench(n))
    assert res["stage"] == 2
    assert res["weeks_in_stage"] <= 10
    assert res["fresh"] is True


def test_mature_stage2_not_fresh():
    base = np.full(60, 100.0)
    advance = np.linspace(100.0, 260.0, 60)  # 60 weeks of advance
    close = _series(np.concatenate([base, advance]))
    n = len(close)
    res = ws.classify(close, None, _flat_bench(n))
    assert res["stage"] == 2
    assert res["weeks_in_stage"] > 10
    assert res["fresh"] is False


# ---------------------------------------------------------------------------
# 5. breakout event fires ONLY with a volume surge
# ---------------------------------------------------------------------------
def _breakout_close() -> pd.Series:
    """Flat base making a fresh 10-week high right as it turns up from S1."""
    base = np.full(70, 100.0)
    # slow drift then a sharp new high to trip S1->S2 with wclose > 10w high
    advance = np.linspace(100.5, 150.0, 14)
    return _series(np.concatenate([base, advance]))


def test_breakout_requires_volume_surge():
    close = _breakout_close()
    n = len(close)
    # flat volume -> vol_ratio ~ 1.0, no breakout chip
    flat_vol = _series(np.full(n, 1_000_000.0))
    res_novol = ws.classify(close, flat_vol, _flat_bench(n))
    # a surge in the last weeks lifts vol_ratio above 1.5
    surge = np.full(n, 1_000_000.0)
    surge[-6:] = 4_000_000.0
    res_surge = ws.classify(close, _series(surge), _flat_bench(n))

    # find the S1->S2 transition bar and check event on the surge path
    ss = ws.stage_series(close, _series(surge), _flat_bench(n))
    stages = [int(x) for x in ss.tolist()]
    assert 2 in stages  # a Stage-2 entry exists
    # with the surge, at least one path bar should be a breakout; without vol it can't
    assert res_novol["event"] != "breakout"


def test_breakout_event_present_with_surge():
    close = _breakout_close()
    n = len(close)
    # surge sustained across the whole advance so the vol_ratio is >=1.5 at the
    # exact S1->S2 breakout week (the surge and the price breakout must coincide).
    surge = np.full(n, 1_000_000.0)
    surge[-14:] = 5_000_000.0
    wf = ws.weekly_frame(close, _series(surge), _flat_bench(n))
    stages, _ = ws._run_machine(wf)
    events = [ws._detect_event(wf, stages, i) for i in range(len(wf))]
    assert "breakout" in events
    # the breakout must sit on an S1->S2 transition bar
    bi = events.index("breakout")
    assert stages[bi] == 2 and stages[bi - 1] == 1


# ---------------------------------------------------------------------------
# 6. too-young path (< 45 completed weeks)
# ---------------------------------------------------------------------------
def test_too_young_returns_stage_zero():
    close = _series(np.linspace(100.0, 120.0, 30))  # only 30 weeks
    res = ws.classify(close, None, _flat_bench(30))
    assert res["stage"] == 0
    assert res["too_young"] is True
    assert res["history"] == []
    assert res["arc_pos"] == 0.0


# ---------------------------------------------------------------------------
# 7. missing volume path — vol fields None, volume-gated events skipped
# ---------------------------------------------------------------------------
def test_missing_volume_nulls_vol_fields():
    close = _round_trip_close()
    n = len(close)
    res = ws.classify(close, None, _flat_bench(n))
    assert res["vol_ratio"] is None
    # breakout needs volume; with none, no bar may emit a breakout chip
    wf = ws.weekly_frame(close, None, _flat_bench(n))
    stages, _ = ws._run_machine(wf)
    events = [ws._detect_event(wf, stages, i) for i in range(len(wf))]
    assert "breakout" not in events


# ---------------------------------------------------------------------------
# 8. NaN robustness — leading NaNs and interior gaps don't crash
# ---------------------------------------------------------------------------
def test_nan_robustness():
    close = _round_trip_close()
    vals = close.to_numpy().copy()
    vals[:5] = np.nan          # leading NaNs
    vals[80:83] = np.nan       # interior gap
    close_nan = pd.Series(vals, index=close.index)
    n = len(close_nan)
    res = ws.classify(close_nan, None, _flat_bench(n))
    # still classifies to a real stage without raising
    assert res["stage"] in (1, 2, 3, 4)
    assert isinstance(res["history"], list)


def test_all_nan_is_too_young():
    close = pd.Series([np.nan] * 80, index=_weekly_index(80))
    res = ws.classify(close, None, _flat_bench(80))
    assert res["too_young"] is True
    assert res["stage"] == 0


# ---------------------------------------------------------------------------
# 9. arc_pos band correctness — each stage lands in its quarter band
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("stage,lo,hi", [
    (1, 0.0, 0.25),
    (2, 0.25, 0.5),
    (3, 0.5, 0.75),
    (4, 0.75, 1.0),
])
def test_arc_pos_band(stage, lo, hi):
    for weeks in (1, 5, 15, 40):
        pos = ws._arc_pos(stage, weeks)
        assert lo <= pos < hi, f"stage {stage} weeks {weeks} -> {pos}"


def test_arc_pos_saturates_and_monotone():
    a = ws._arc_pos(2, 1)
    b = ws._arc_pos(2, 10)
    c = ws._arc_pos(2, 30)
    assert a < b <= c < 0.5
    assert ws._arc_pos(0, 3) == 0.0  # unclassified => 0


def test_classify_arc_pos_matches_stage():
    close = _round_trip_close()
    n = len(close)
    res = ws.classify(close, None, _flat_bench(n))
    lo = (res["stage"] - 1) * 0.25
    assert lo <= res["arc_pos"] < lo + 0.25


# ---------------------------------------------------------------------------
# 10. weeks_in_stage counting resets on transition and increments within a stage
# ---------------------------------------------------------------------------
def test_weeks_in_stage_counts():
    close = _round_trip_close()
    n = len(close)
    wf = ws.weekly_frame(close, None, _flat_bench(n))
    stages, weeks = ws._run_machine(wf)
    # wherever the stage stays the same across a bar, weeks increments by 1;
    # wherever it changes, weeks resets to 1.
    for i in range(1, len(stages)):
        if stages[i] == 0:
            continue
        if stages[i] == stages[i - 1] and stages[i - 1] != 0:
            assert weeks[i] == weeks[i - 1] + 1
        else:
            assert weeks[i] == 1


def test_weeks_in_stage_matches_classify():
    close = _round_trip_close()
    n = len(close)
    wf = ws.weekly_frame(close, None, _flat_bench(n))
    stages, weeks = ws._run_machine(wf)
    res = ws.classify(close, None, _flat_bench(n))
    assert res["weeks_in_stage"] == weeks[-1]
    assert res["stage"] == stages[-1]


# ---------------------------------------------------------------------------
# 11. weekly_frame contract — columns, completed-week gate, mansfield present
# ---------------------------------------------------------------------------
def test_weekly_frame_columns_and_mansfield():
    close = _round_trip_close()
    n = len(close)
    wf = ws.weekly_frame(close, _series(np.full(n, 1e6)), _flat_bench(n))
    assert list(wf.columns) == ["wclose", "ma30", "slope_5w", "mansfield_rs",
                                "vol_4w", "vol_30w", "vol_ratio"]
    # ma30 is NaN for the first 29 weeks (min_periods=30), defined after
    assert wf["ma30"].iloc[:29].isna().all()
    assert wf["ma30"].iloc[40:].notna().any()
    # mansfield RS defined once the 52-week mean has enough history
    assert wf["mansfield_rs"].iloc[60:].notna().any()
    # vol_ratio finite once populated
    assert wf["vol_ratio"].dropna().shape[0] > 0


def test_empty_and_short_inputs_are_safe():
    assert ws.weekly_frame(pd.Series([], dtype=float), None,
                           pd.Series([], dtype=float)).empty
    assert ws.stage_series(pd.Series([], dtype=float), None,
                           pd.Series([], dtype=float)).empty
    # a handful of bars -> too young, not a crash
    close = _series(np.linspace(100, 101, 10))
    res = ws.classify(close, None, _flat_bench(10))
    assert res["too_young"] is True


# ---------------------------------------------------------------------------
# 12. FLAT threshold — a gently rising line under 0.75%/5wk reads as flat (S1/S3)
# ---------------------------------------------------------------------------
def test_flat_threshold_gentle_drift_not_stage2():
    # rise ~0.1%/week over 90 weeks -> ~0.5%/5wk < 0.75% => flat => not S2
    close = _series(100.0 * (1.0 + 0.001) ** np.arange(90))
    n = len(close)
    res = ws.classify(close, None, _flat_bench(n))
    assert res["stage"] in (1, 3)  # flat regime, never Stage 2
    slope = res["ma30_slope_pct5w"]
    assert slope is not None and abs(slope) < ws.FLAT_SLOPE_PCT


def test_steep_uptrend_is_stage2():
    close = _series(np.linspace(100.0, 400.0, 90))
    n = len(close)
    res = ws.classify(close, None, _flat_bench(n))
    assert res["stage"] == 2
    assert res["ma30_slope_pct5w"] > ws.FLAT_SLOPE_PCT


# ---------------------------------------------------------------------------
# 13. n_weeks contract — completed weekly bars, present on every path.
# ---------------------------------------------------------------------------
def test_n_weeks_normal_path_matches_frame_length():
    """A normally-classified name reports n_weeks == the weekly-frame length."""
    close = _round_trip_close()
    n = len(close)
    wf = ws.weekly_frame(close, None, _flat_bench(n))
    res = ws.classify(close, None, _flat_bench(n))
    assert "n_weeks" in res
    assert res["n_weeks"] == len(wf)
    # The frame must clear the SGA history floor for a real classification.
    assert res["n_weeks"] >= ws.MIN_COMPLETED_WEEKS
    assert res["too_young"] is False


def test_n_weeks_too_young_path_present_and_below_floor():
    """A too-young name still carries n_weeks (the actual completed-week count,
    below the floor), so the stage_analysis too-young guard stays live."""
    close = _series(np.linspace(100.0, 120.0, 30))  # only ~30 completed weeks
    wf = ws.weekly_frame(close, None, _flat_bench(30))
    res = ws.classify(close, None, _flat_bench(30))
    assert res["too_young"] is True
    assert "n_weeks" in res
    assert res["n_weeks"] == len(wf)
    assert res["n_weeks"] < ws.MIN_COMPLETED_WEEKS


def test_n_weeks_empty_input_is_zero():
    """Empty input → too-young with n_weeks == 0 (empty weekly frame)."""
    res = ws.classify(pd.Series([], dtype=float), None, pd.Series([], dtype=float))
    assert res["too_young"] is True
    assert res["n_weeks"] == 0
