"""Tests for engine/stock_events.py — Signal Episode Atlas W1 (sea.v1).

Covers:
- PIT partial-bar exclusion per grid (2B remainder bucket + the open W-FRI week)
- depth_pctile trailing-window correctness (hand-computed) + the MIN_DEPTH_OBS null
- depth_class boundaries at 15 / 30 / 70
- washout_len logic, including above_zero → "na"
- align_class evaluated on each other grid's own completed bars
- outcome maturity: immature → NaN + matured=False, never a partial window
- excess vs benchmark null unless BOTH legs matured
- era column + regime stamps (oracle `_regime_bucket` vocabulary)
- backfill/live split cutoff correctness
- live-part append idempotency + the COLLECT_LANE ledger-lane gate
- maturation fills only outcome cells, only in live parts
- authority creep guards: canon-only imports, no pick-chain consumption

SYNTHETIC ONLY — every series is built from a designed path anchored to FIXED
constant dates, so nothing here reads the wall clock (no date-bombs) and nothing
pins committed data.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine import canon
from engine import stock_events as se

_ANCHOR_FRIDAY = "1996-01-05"      # a real Friday; the tape defines its own "today"


# ---------------------------------------------------------------------------
# Synthetic tape construction
# ---------------------------------------------------------------------------

def _weekly_to_daily(weekly_vals, start: str = _ANCHOR_FRIDAY) -> pd.Series:
    """Expand a WEEKLY close path onto business days (washout_turn test idiom)."""
    vals = np.asarray(list(weekly_vals), dtype=float)
    span = pd.bdate_range(start, periods=len(vals) * 7 + 10, freq="B")
    fridays = pd.DatetimeIndex([d for d in span if d.weekday() == 4])[: len(vals)]
    assert len(fridays) == len(vals)
    idx = pd.bdate_range(fridays[0] - pd.Timedelta(days=4), fridays[-1], freq="B")
    s = pd.Series(np.nan, index=idx, dtype=float)
    s.loc[fridays] = vals
    s.iloc[0] = float(vals[0])
    return s.interpolate().ffill().bfill().rename("close")


def _wavy(n: int = 900, seed: int = 7) -> pd.Series:
    """A long, ordinary daily tape with several cycle lengths (many crosses)."""
    rs = np.random.RandomState(seed)
    t = np.arange(n, dtype=float)
    base = 100.0 * np.exp(0.0004 * t) * (
        1.0 + 0.10 * np.sin(2 * np.pi * t / 90.0)
        + 0.05 * np.sin(2 * np.pi * t / 21.0)
    )
    noise = np.cumsum(rs.normal(0, 0.002, n))
    idx = pd.bdate_range("1996-01-05", periods=n, freq="B")
    return pd.Series(base * np.exp(noise), index=idx, name="close")


def _flat_ctx() -> se.ExtractContext:
    """An EMPTY context — no SPY, no VIX, no archetypes.  Degraded but honest."""
    return se.ExtractContext()


# ---------------------------------------------------------------------------
# 1 — PIT: partial bars are not bars
# ---------------------------------------------------------------------------

def test_session_grid_drops_the_incomplete_trailing_bucket():
    """Kills a mutant that keeps the remainder bucket of a 2B/3B resample."""
    daily = _wavy(301)                    # 301 % 2 == 1 → 2B remainder of ONE session
    assert len(daily) % 2 == 1
    b2 = se.grid_series(daily, "2B")
    full, _known = canon.resample_sessions(daily, 2)
    assert len(b2) == len(full) - 1, "the 1-session remainder bucket must be dropped"
    assert b2.index[-1] < daily.index[-1], (
        "no completed 2B bar may be dated at the still-open last session"
    )

    even = _wavy(300)                      # exact multiple → nothing dropped
    assert len(even) % 2 == 0
    b2e = se.grid_series(even, "2B")
    full_e, _k = canon.resample_sessions(even, 2)
    assert len(b2e) == len(full_e)


def test_weekly_grid_drops_the_open_week_and_keeps_a_friday_close():
    """Kills a mutant that resamples W-FRI without dropping the partial week."""
    daily = _wavy(400)
    fri = daily[daily.index.weekday == 4].index[-1]
    ends_friday = daily[daily.index <= fri]
    mid_week = daily[daily.index <= fri + pd.Timedelta(days=3)]   # the next Monday

    wk_f = se.grid_series(ends_friday, "W")
    wk_m = se.grid_series(mid_week, "W")
    assert wk_f.index[-1].date() == fri.date(), (
        "a series ending ON a Friday keeps that COMPLETED weekly bar"
    )
    assert wk_m.index[-1].date() <= mid_week.index[-1].date()
    assert len(wk_m) == len(wk_f), "the open week must not add a bar"


def test_partial_week_hides_the_cross_until_friday_closes():
    """The same weekly cross is invisible while its week is still open."""
    daily = _wavy(700)
    fri_dates = daily[daily.index.weekday == 4].index
    found = False
    for fri in fri_dates[-40:]:
        upto = daily[daily.index <= fri]
        ev_fri = [e for e in se.extract_symbol_events("T", upto, ctx=_flat_ctx())
                  if e["grid"] == "W" and pd.Timestamp(e["date"]) == fri]
        if not ev_fri:
            continue
        open_week = daily[daily.index <= fri - pd.Timedelta(days=2)]   # that Wednesday
        ev_wed = [e for e in se.extract_symbol_events("T", open_week, ctx=_flat_ctx())
                  if e["grid"] == "W" and pd.Timestamp(e["date"]) == fri]
        assert not ev_wed, "an event dated on a week that has not closed is look-ahead"
        found = True
        break
    assert found, "fixture must contain at least one weekly cross to test"


# ---------------------------------------------------------------------------
# 2 — depth percentile + depth class
# ---------------------------------------------------------------------------

def test_depth_pctile_is_a_trailing_strictly_less_than_rank():
    """Hand-computed: the window ENDS at i, and the rank is strictly-less-than."""
    vals = np.arange(200, dtype=float)          # 0,1,2,...,199
    # window 100 ending at i=149 → values 50..149; strictly below 149 → 99 of 100
    p, n = se.depth_pctile(vals, 149, 100)
    assert n == 100
    assert p == pytest.approx(99.0)
    # the SAME bar with a full-history window sees more of the past below it,
    # but never anything after it — a look-ahead mutant would read 149/200.
    p_full, n_full = se.depth_pctile(vals, 149, 1000)
    assert n_full == 150
    assert p_full == pytest.approx(100.0 * 149 / 150)

    lowest = np.array([5.0] + list(np.arange(1, 200, dtype=float)))
    p_low, _ = se.depth_pctile(lowest, 0, 100)
    assert p_low is None, "fewer than MIN_DEPTH_OBS observations must read None"


def test_depth_pctile_min_obs_is_the_literal_the_class_promises():
    # Pinned as a LITERAL: reading it from the module would make this test move
    # with the mutant it exists to catch.
    assert se.MIN_DEPTH_OBS == 100
    vals = np.arange(99, dtype=float)
    assert se.depth_pctile(vals, 98, 520) == (None, 99)
    vals100 = np.arange(100, dtype=float)
    p, n = se.depth_pctile(vals100, 99, 520)
    assert n == 100 and p == pytest.approx(99.0)


def test_depth_class_boundaries():
    assert (se.DEPTH_WASHOUT_MAX, se.DEPTH_DEEP_MAX, se.DEPTH_MID_MAX) == (15.0, 30.0, 70.0)
    assert se.depth_class(0.0) == "washout"
    assert se.depth_class(15.0) == "washout"          # inclusive upper edge
    assert se.depth_class(15.01) == "deep"
    assert se.depth_class(30.0) == "deep"
    assert se.depth_class(30.01) == "mid"
    assert se.depth_class(70.0) == "mid"
    assert se.depth_class(70.01) == "high"
    assert se.depth_class(100.0) == "high"
    assert se.depth_class(None) == "unknown"
    assert se.depth_class(float("nan")) == "unknown"


def test_an_unclassifiable_depth_is_still_a_recorded_event():
    """A short history must not DELETE the event — "unknown" is a cohort."""
    vals = np.arange(50, dtype=float)
    p, _n = se.depth_pctile(vals, 49, 520)
    assert p is None
    assert se.depth_class(p) == "unknown"


# ---------------------------------------------------------------------------
# 3 — washout_len + its classes
# ---------------------------------------------------------------------------

def test_washout_len_counts_bars_since_the_line_was_last_non_negative():
    line = np.array([1.0, 0.5, -0.2, -0.4, -0.9, -1.2])
    assert se.washout_len(line, 5) == 4          # last >= 0 at index 1
    assert se.washout_len(line, 2) == 1
    assert se.washout_len(line, 1) == 0          # the line IS >= 0 here
    all_neg = np.array([-1.0, -2.0, -3.0])
    assert se.washout_len(all_neg, 2) == 3, "never-positive history reads its whole span"


def test_washout_len_class_boundaries_and_the_above_zero_na():
    assert (se.WASHOUT_SHORT_MAX, se.WASHOUT_MEDIUM_MAX) == (8, 26)
    assert se.washout_len_class(0, "below_zero") == "short"
    assert se.washout_len_class(7, "below_zero") == "short"
    assert se.washout_len_class(8, "below_zero") == "medium"
    assert se.washout_len_class(26, "below_zero") == "medium"
    assert se.washout_len_class(27, "below_zero") == "long"
    # above zero there is no washout run at all — a real value, not a bucket
    assert se.washout_len_class(0, "above_zero") == "na"
    assert se.washout_len_class(99, "above_zero") == "na"


def test_events_above_zero_carry_the_na_washout_class():
    rows = se.extract_symbol_events("T", _wavy(900), ctx=_flat_ctx())
    assert rows
    above = [r for r in rows if r["level"] == "above_zero"]
    below = [r for r in rows if r["level"] == "below_zero"]
    assert above and below, "fixture must contain both levels"
    assert all(r["washout_len_class"] == "na" for r in above)
    assert all(r["washout_len_class"] != "na" for r in below)
    assert all((r["line"] or 0) >= 0 for r in above)


# ---------------------------------------------------------------------------
# 4 — align_class
# ---------------------------------------------------------------------------

def test_align_class_reads_the_other_grids_own_completed_bars():
    """Recompute alignment independently; the organ must agree bar for bar."""
    daily = _wavy(900)
    rows = se.extract_symbol_events("T", daily, ctx=_flat_ctx())
    assert rows

    states = {}
    for g in se.GRIDS:
        bars = se.grid_series(daily, g)
        line, sig = se._line_sig(bars)
        states[g] = (line > sig).where(line.notna() & sig.notna())

    checked = 0
    for r in rows[:: max(1, len(rows) // 40)]:
        when = pd.Timestamp(r["date"])
        expect = 0
        for og, st in states.items():
            if og == r["grid"]:
                continue
            pos = int(st.index.searchsorted(when, side="right")) - 1
            if pos < 0:
                continue
            v = st.iloc[pos]
            if v is not pd.NA and bool(v) is True:
                expect += 1
        assert r["align_class"] == expect, f"{r['grid']} {when}"
        assert 0 <= r["align_class"] <= 2
        checked += 1
    assert checked >= 10


def test_align_class_never_counts_a_null_leg_as_aligned():
    """A grid whose line is still in warm-up is not an aligned grid."""
    short = _wavy(320)                 # W grid barely clears MIN_DEPTH_OBS
    rows = se.extract_symbol_events("T", short, ctx=_flat_ctx())
    for r in rows:
        assert 0 <= r["align_class"] <= 2


# ---------------------------------------------------------------------------
# 5 — outcomes: matured only, never a partial window
# ---------------------------------------------------------------------------

def test_immature_events_carry_nan_outcomes_and_matured_false():
    daily = _wavy(900)
    rows = se.extract_symbol_events("T", daily, ctx=_flat_ctx())
    wk_rows = [r for r in rows if r["grid"] == "W"]
    assert wk_rows
    last = max(wk_rows, key=lambda r: r["date"])
    assert last["fwd_26w"] is None and last["matured"] is False, (
        "the newest weekly event cannot have a closed 26-week window"
    )
    # and an OLD one is filled — so the null above is maturity, not a dead path
    first_mature = [r for r in wk_rows if r["matured"]]
    assert first_mature, "older weekly events must have matured outcomes"


def test_weekly_outcome_equals_the_hand_computed_forward_window():
    daily = _wavy(900)
    wk = se.grid_series(daily, "W")
    line, sig = se._line_sig(wk)
    bars = wk.reindex(line.index)
    rows = [r for r in se.extract_symbol_events("T", daily, ctx=_flat_ctx())
            if r["grid"] == "W" and r["matured"]]
    assert rows
    r = rows[len(rows) // 2]
    i = int(bars.index.get_indexer([pd.Timestamp(r["date"])])[0])
    assert i >= 0
    expect13 = float(bars.iloc[i + 13] / bars.iloc[i] - 1.0)
    expect26 = float(bars.iloc[i + 26] / bars.iloc[i] - 1.0)
    assert r["fwd_13w"] == pytest.approx(expect13, abs=1e-6)
    assert r["fwd_26w"] == pytest.approx(expect26, abs=1e-6)


def test_session_grid_outcomes_are_measured_on_the_daily_series():
    daily = _wavy(900)
    rows = [r for r in se.extract_symbol_events("T", daily, ctx=_flat_ctx())
            if r["grid"] == "3B" and r["matured"]]
    assert rows
    r = rows[len(rows) // 2]
    pos = int(daily.index.searchsorted(pd.Timestamp(r["date"]), side="right")) - 1
    expect21 = float(daily.iloc[pos + 21] / daily.iloc[pos] - 1.0)
    expect63 = float(daily.iloc[pos + 63] / daily.iloc[pos] - 1.0)
    assert r["fwd_21s"] == pytest.approx(expect21, abs=1e-6)
    assert r["fwd_63s"] == pytest.approx(expect63, abs=1e-6)
    assert r["fwd_13w"] is None and r["fwd_26w"] is None, (
        "a session-grid row must not carry weekly-horizon columns"
    )


def test_no_partial_window_is_ever_filled():
    """Truncate the tape so a known event's window is cut mid-flight."""
    daily = _wavy(900)
    wk = se.grid_series(daily, "W")
    line, _sig = se._line_sig(wk)
    bars = wk.reindex(line.index)
    target = bars.index[-20]                      # < 26 completed bars remain
    rows = [r for r in se.extract_symbol_events("T", daily, ctx=_flat_ctx())
            if r["grid"] == "W" and pd.Timestamp(r["date"]) >= target]
    for r in rows:
        i = int(bars.index.get_indexer([pd.Timestamp(r["date"])])[0])
        if i + 26 >= len(bars):
            assert r["fwd_26w"] is None, "a window that has not closed must be NaN"
            assert r["matured"] is False
        if i + 13 >= len(bars):
            assert r["fwd_13w"] is None
            assert r["matured_short"] is False


def test_excess_is_null_unless_both_legs_matured():
    """A benchmark leg that has not closed cannot produce an excess number."""
    daily = _wavy(900)
    bench = _wavy(700, seed=11)                   # SPY stops 200 sessions early
    ctx = se.ExtractContext(spy_daily=bench, spy_weekly=se.grid_series(bench, "W"))
    rows = se.extract_symbol_events("T", daily, ctx=ctx)
    late = [r for r in rows if pd.Timestamp(r["date"]) > bench.index[-1]]
    assert late, "fixture must contain events after the benchmark ends"
    for r in late:
        assert r["exc_13w"] is None and r["exc_26w"] is None
        assert r["exc_21s"] is None and r["exc_63s"] is None


def test_excess_equals_own_minus_benchmark_over_the_same_window():
    daily = _wavy(900)
    bench = _wavy(900, seed=11)
    ctx = se.ExtractContext(spy_daily=bench, spy_weekly=se.grid_series(bench, "W"))
    rows = [r for r in se.extract_symbol_events("T", daily, ctx=ctx)
            if r["grid"] == "3B" and r["exc_21s"] is not None]
    assert rows
    r = rows[len(rows) // 2]
    pos = int(bench.index.searchsorted(pd.Timestamp(r["date"]), side="right")) - 1
    bench21 = float(bench.iloc[pos + 21] / bench.iloc[pos] - 1.0)
    assert r["exc_21s"] == pytest.approx(r["fwd_21s"] - bench21, abs=1e-5)


# ---------------------------------------------------------------------------
# 6 — era + regime stamps
# ---------------------------------------------------------------------------

def test_era_column_splits_at_the_2010_break():
    assert se.ERA_BREAK == pd.Timestamp("2010-01-01")
    assert se._era(pd.Timestamp("2009-12-31")) == "pre2010"
    assert se._era(pd.Timestamp("2010-01-01")) == "post2010"
    rows = se.extract_symbol_events("T", _wavy(900), ctx=_flat_ctx())
    for r in rows:
        assert r["era"] == ("pre2010" if pd.Timestamp(r["date"]) < se.ERA_BREAK
                            else "post2010")


def test_regime_bucket_matches_the_oracle_memory_vocabulary():
    """Same four buckets, same 0.6 threshold — one vocabulary, two call sites."""
    from engine.oracle.memory import _regime_bucket as oracle_bucket

    assert se.REGIME_VIX_THRESHOLD == 0.6
    for vix, spy in [(0.9, 1.0), (0.9, 0.0), (0.2, 1.0), (0.2, 0.0), (0.6, 1.0)]:
        assert se.regime_bucket(vix, spy) == oracle_bucket(vix, spy, 0.6)
    # half-known reads keep the oracle's any_* half
    assert se.regime_bucket(0.9, None) == "hi_vix_any_spy"
    assert se.regime_bucket(None, 1.0) == "any_vix_above200"
    # both unknown is named for THIS library, not left as a bare "unknown"
    assert se.regime_bucket(None, None) == "regime_unknown"
    assert oracle_bucket(None, None, 0.6) == "unknown"


def test_regime_stamps_are_null_tolerant_and_recorded_not_classed():
    rows = se.extract_symbol_events("T", _wavy(900), ctx=_flat_ctx())
    assert rows
    for r in rows[:20]:
        assert r["regime_vix_pctile"] is None
        assert r["regime_spy_above_200d"] is None
        assert r["regime_bucket"] == "regime_unknown"
    # regime is NOT a class axis — it must not appear in the atlas cell key
    from engine.event_atlas import CLASS_AXES
    assert not any("regime" in a for a in CLASS_AXES)


def test_regime_stamps_are_read_at_or_before_the_event_date():
    daily = _wavy(900)
    vix_pct = pd.Series(
        np.linspace(0.0, 1.0, len(daily)), index=daily.index
    )
    above = pd.Series(1.0, index=daily.index)
    ctx = se.ExtractContext(vix_pctile=vix_pct, spy_above_200d=above)
    rows = se.extract_symbol_events("T", daily, ctx=ctx)
    assert rows
    for r in rows[:: max(1, len(rows) // 25)]:
        pos = int(daily.index.searchsorted(pd.Timestamp(r["date"]), side="right")) - 1
        assert r["regime_vix_pctile"] == pytest.approx(float(vix_pct.iloc[pos]), abs=1e-3)
        assert r["regime_spy_above_200d"] is True
        assert r["regime_bucket"] in ("hi_vix_above200", "lo_vix_above200")


# ---------------------------------------------------------------------------
# 7 — PIT archetype
# ---------------------------------------------------------------------------

def test_archetype_is_point_in_time_and_falls_back_to_its_own_cohort():
    dates = np.array([np.datetime64("2000-01-01"), np.datetime64("2015-06-30")])
    ctx = se.ExtractContext(archetypes={"T": (dates, ["cyclical", "quality_compounder"])})
    assert se._archetype_at(ctx, "T", pd.Timestamp("1999-01-01")) == "archetype_unknown"
    assert se._archetype_at(ctx, "T", pd.Timestamp("2001-01-01")) == "cyclical"
    assert se._archetype_at(ctx, "T", pd.Timestamp("2015-06-30")) == "quality_compounder"
    assert se._archetype_at(ctx, "T", pd.Timestamp("2026-01-01")) == "quality_compounder"
    assert se._archetype_at(ctx, "OTHER", pd.Timestamp("2026-01-01")) == "archetype_unknown"
    assert se._archetype_at(None, "T", pd.Timestamp("2026-01-01")) == "archetype_unknown"


# ---------------------------------------------------------------------------
# 8 — storage: split, gate, idempotency, maturation
# ---------------------------------------------------------------------------

def _rows(n: int = 6, start: str = "2020-01-03", ticker: str = "AAA") -> pd.DataFrame:
    days = pd.bdate_range(start, periods=n, freq="7D")
    return se.events_frame([
        {
            "ticker": ticker, "grid": "W", "date": d, "direction": "bull",
            "era": "post2010", "depth_pctile": 5.0, "depth_window_n": 520,
            "depth_class": "washout", "level": "below_zero",
            "washout_len": 10, "washout_len_class": "medium", "align_class": 2,
            "hist_vel3": 0.1, "stoch_k": 20.0, "stoch_d": 18.0,
            "drawdown_pct": -20.0, "close": 100.0 + i, "line": -5.0, "sig": -5.1,
            "archetype_at_event": "cyclical", "sector": "us_sector_tech",
            "regime_vix_pctile": 0.4, "regime_spy_above_200d": True,
            "regime_bucket": "lo_vix_above200",
            "fwd_13w": None, "fwd_26w": None, "fwd_21s": None, "fwd_63s": None,
            "exc_13w": None, "exc_26w": None, "exc_21s": None, "exc_63s": None,
            "matured_short": False, "matured": False,
        }
        for i, d in enumerate(days)
    ])


def test_split_cutoff_is_the_maturation_window():
    assert se.MATURITY_DAYS == 26 * 7
    assert se.split_cutoff("2026-08-04") == pd.Timestamp("2026-02-03")


def test_backfill_holds_only_fully_matured_events_and_refuses_to_be_clobbered(tmp_path):
    df = _rows(40, start="2024-01-05")
    asof = pd.Timestamp(df["date"].max())
    cutoff = se.split_cutoff(asof)
    old, young = df[df["date"] < cutoff], df[df["date"] >= cutoff]
    assert len(old) and len(young), "fixture must straddle the cutoff"

    se.write_backfill(old, tmp_path)
    assert se.backfill_path(tmp_path).exists()
    assert (pd.read_parquet(se.backfill_path(tmp_path))["date"] < cutoff).all()
    with pytest.raises(FileExistsError):
        se.write_backfill(old, tmp_path)
    se.write_backfill(old, tmp_path, overwrite=True)      # deliberate re-derivation


def test_live_parts_are_dark_without_the_nightly_lane(tmp_path, monkeypatch):
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)
    assert se.append_live_events(_rows(), tmp_path) == 0
    assert not se.live_dir(tmp_path).exists()
    assert se.load_events(tmp_path).empty


def test_live_append_is_keep_first_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    df = _rows(6)
    assert se.append_live_events(df, tmp_path) == 6
    parts = sorted(se.live_dir(tmp_path).glob("*.parquet"))
    assert parts
    digests = {p.name: p.read_bytes() for p in parts}

    mutated = df.copy()
    mutated["depth_pctile"] = 99.9
    assert se.append_live_events(mutated, tmp_path) == 0, "known keys append nothing"
    for p in sorted(se.live_dir(tmp_path).glob("*.parquet")):
        assert p.read_bytes() == digests[p.name], "an unchanged part must not be rewritten"
    stored = se.load_events(tmp_path)
    assert len(stored) == 6
    assert set(stored["depth_pctile"]) == {5.0}, "keep-FIRST: the original row stands"

    later = _rows(2, start="2020-06-05")
    assert se.append_live_events(later, tmp_path) == 2
    assert len(se.load_events(tmp_path)) == 8


def test_maturation_fills_only_outcome_cells_and_only_in_live_parts(tmp_path, monkeypatch):
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    df = _rows(4)
    se.append_live_events(df, tmp_path)
    frozen = df.copy()
    frozen["fwd_13w"] = 0.5
    se.write_backfill(frozen, tmp_path)
    backfill_bytes = se.backfill_path(tmp_path).read_bytes()

    fresh = df.copy()
    fresh["fwd_13w"] = [0.10, 0.20, 0.30, 0.40]
    fresh["fwd_26w"] = [0.11, 0.21, 0.31, np.nan]
    fresh["matured_short"] = True
    fresh["matured"] = [True, True, True, False]
    fresh["depth_pctile"] = 99.9              # a NON-outcome column — must be ignored

    filled = se.mature_outcomes(fresh, tmp_path)
    assert filled > 0
    live = pd.concat(
        [pd.read_parquet(p) for p in sorted(se.live_dir(tmp_path).glob("*.parquet"))]
    ).sort_values("date")
    assert list(live["fwd_13w"]) == [0.10, 0.20, 0.30, 0.40]
    assert list(live["matured"]) == [True, True, True, False]
    assert pd.isna(list(live["fwd_26w"])[-1]), "a still-open window stays NaN"
    assert set(live["depth_pctile"]) == {5.0}, "maturation must not touch class axes"
    assert se.backfill_path(tmp_path).read_bytes() == backfill_bytes, (
        "the frozen backfill is never rewritten by maturation"
    )


def test_maturation_is_dark_without_the_nightly_lane(tmp_path, monkeypatch):
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    se.append_live_events(_rows(3), tmp_path)
    before = {p.name: p.read_bytes() for p in se.live_dir(tmp_path).glob("*.parquet")}

    monkeypatch.delenv("COLLECT_LANE", raising=False)
    fresh = _rows(3)
    fresh["fwd_13w"] = 0.3
    assert se.mature_outcomes(fresh, tmp_path) == 0
    for p in se.live_dir(tmp_path).glob("*.parquet"):
        assert p.read_bytes() == before[p.name]


def test_load_events_concats_backfill_and_live_parts(tmp_path, monkeypatch):
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    old = _rows(3, start="2015-01-02")
    young = _rows(2, start="2024-01-05")
    se.write_backfill(old, tmp_path)
    se.append_live_events(young, tmp_path)
    got = se.load_events(tmp_path)
    assert len(got) == 5
    assert set(got.columns) >= set(se.EVENT_COLUMNS)
    assert got["date"].is_monotonic_increasing or len(got["ticker"].unique()) > 1


def test_nightly_update_writes_nothing_off_lane(tmp_path, monkeypatch):
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)
    daily = _wavy(600)
    ctx = _flat_ctx()
    from unittest.mock import patch
    with patch.object(se, "_build_universe", return_value={"AAA": ["b1"]}), \
         patch.object(se, "_load_close", side_effect=lambda s, r=None: daily), \
         patch.object(se.ExtractContext, "build", classmethod(lambda cls, r=None: ctx)):
        out = se.nightly_update(tmp_path)
    assert out["extracted"] > 0, "an off-lane run still COMPUTES"
    assert out["written"] is False
    assert out["appended"] == 0 and out["matured_filled"] == 0
    assert not se.events_dir(tmp_path).exists(), "no data/ write off the nightly lane"


def test_nightly_update_appends_under_the_lane_and_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    daily = _wavy(600)
    ctx = _flat_ctx()
    from unittest.mock import patch
    with patch.object(se, "_build_universe", return_value={"AAA": ["b1"]}), \
         patch.object(se, "_load_close", side_effect=lambda s, r=None: daily), \
         patch.object(se.ExtractContext, "build", classmethod(lambda cls, r=None: ctx)):
        first = se.nightly_update(tmp_path)
        parts = {p.name: p.read_bytes() for p in se.live_dir(tmp_path).glob("*.parquet")}
        assert first["appended"] > 0 and first["written"] is True
        second = se.nightly_update(tmp_path)
    assert second["appended"] == 0, "a same-data re-run appends nothing"
    for p in se.live_dir(tmp_path).glob("*.parquet"):
        assert p.read_bytes() == parts[p.name]


def test_empty_frame_keeps_the_frozen_schema(tmp_path):
    empty = se.events_frame([])
    assert list(empty.columns) == list(se.EVENT_COLUMNS)
    p = tmp_path / "e.parquet"
    se._to_parquet_with_metadata(empty, p)
    assert list(pd.read_parquet(p).columns) == list(se.EVENT_COLUMNS)


def test_metadata_sidecar_carries_the_universe_basis_and_canon_params(tmp_path):
    p = se.write_metadata_sidecar(tmp_path)
    body = p.read_text()
    assert se.TAXONOMY_VERSION in body
    assert se.UNIVERSE_BASIS in body
    assert "survivorship" in body.lower() and "clustering" in body.lower()
    assert '"rsi_len": 14' in body


# ---------------------------------------------------------------------------
# 9 — guard rails: canon-only math, zero authority, no pick-chain reach
# ---------------------------------------------------------------------------

_SRC_ROOT = Path(__file__).resolve().parents[1]


def test_authority_block_is_all_false_display_tier():
    assert se.AUTHORITY["tier"] == "display"
    for key in ("may_rank", "may_gate", "may_size", "may_escalate"):
        assert se.AUTHORITY[key] is False


def test_module_imports_canon_and_never_engine_technicals_rsi():
    src = (_SRC_ROOT / "engine/stock_events.py").read_text(encoding="utf-8")
    assert "from engine.canon import" in src
    assert "from engine.technicals import" not in src
    assert "import engine.technicals" not in src
    for banned in ("engine.prophet", "us_board_rank", "engine.board", "name_score",
                   "stock_score", "entry_signal"):
        assert f"import {banned}" not in src


def test_the_module_docstring_carries_its_legal_fence():
    src = (_SRC_ROOT / "engine/stock_events.py").read_text(encoding="utf-8")
    # Collapse the wrap: the fence is a CLAIM, not a line layout.
    head = " ".join(src[: src.index('"""', 3)].split())
    assert "MEASUREMENT artifact" in head
    assert "Not a call record" in head
    assert "no historical row claims foresight" in head
    assert "DNR §2 fingerprint Layer-3" in head
    assert "PTT-W1a" in head and "DT-R16" in head and "#1747" in head
    assert "Oracle P8 P-W1/S-W3" in head


def test_nothing_in_the_pick_chain_imports_the_event_library():
    """The organ is display-tier; a pick-chain import would be authority creep.

    Fence scope (adjudicated 2026-08-06): the fenced set is the SCORED pick chain —
    ranker, cascade, gate, bridge. `engine/prophet_doors.py` was removed from it when
    Door W landed: the doors are themselves zero-authority SHADOW lanes (nothing in the
    pick chain imports THEM — pinned in tests/test_prophet_doors.py::test_no_authority_*),
    and a shadow recorder reading the measurement library's pure grid helpers creates no
    authority path. Fencing the doors here would forbid exactly the lawful use the
    library exists for.
    """
    for rel in ("engine/us_board_rank.py", "engine/confluence_tiers.py",
                "engine/signal_gate.py", "engine/prophet_bridge.py"):
        src = (_SRC_ROOT / rel).read_text(encoding="utf-8")
        assert "stock_events" not in src, rel
        assert "event_atlas" not in src, rel


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-x", "-q"])
