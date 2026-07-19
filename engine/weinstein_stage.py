"""Weinstein 4-stage classifier (SGA-R1) — pure, fail-open, NaN-safe.

Stan Weinstein's stage analysis on **completed W-FRI weekly bars**:
  Stage 1 — basing (flat, arriving from decline/unknown)
  Stage 2 — advancing (close > 30-week SMA, SMA rising)
  Stage 3 — topping (flat, arriving from an advance)
  Stage 4 — declining (close < 30-week SMA, SMA falling)

Ruling SGA-R1 (research/STAGE_ANALYSIS_MASTERPLAN.md §1) pins every constant
and the deterministic state machine with hysteresis. Constants below may ONLY
change with a ruling amendment there.

Design notes:
- The weekly grid reuses `engine.cycles._w_fri_completed` (IHM-R1 PIT gate): a
  W-FRI bucket whose Friday label is after the last observed daily date is still
  in progress and is dropped. This is the single canonical completed-week rule.
- `ma30` = 30-week SMA of the weekly close (NOT a 150-day daily SMA — trap §7).
- Slope is measured over 5 weeks: (ma30[t] - ma30[t-5]) / ma30[t-5].
- Mansfield RS (SGA-R2) is context only, never a gate.
- Everything is fail-open: a missing/short/NaN input returns a well-formed
  "too young" / null-field dict rather than raising, so a nightly build over
  ~2.8k names never crashes on one bad series.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine.cycles import _w_fri_completed

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SGA-R1 pinned constants (amend only via a ruling in the masterplan).
# ---------------------------------------------------------------------------
MA_WEEKS = 30                 # 30-week SMA of the weekly close (the Weinstein line)
SLOPE_LOOKBACK_W = 5          # slope measured over 5 completed weeks
FLAT_SLOPE_PCT = 0.75         # |slope| < 0.75% per 5wk (~0.15%/wk) => FLAT
RS_MEAN_WEEKS = 52            # Mansfield RS uses a 52-week mean of the raw ratio
VOL_SHORT_W = 4               # short-window average weekly volume
VOL_LONG_W = 30              # long-window average weekly volume
BREAKOUT_HIGH_W = 10          # weekly close must exceed the prior 10-week high
BREAKOUT_VOL_RATIO = 1.5      # breakout needs vol_ratio >= 1.5 (volume surge)
PULLBACK_LOW_W = 3            # pullback_resume needs a >=3-week low above ma30
MIN_COMPLETED_WEEKS = 45      # SGA-R3: fewer completed weeks => "too young to stage"
HISTORY_WEEKS = 104           # trailing (iso_week, stage) pairs returned (2 years)

# arc_pos: position along the idealized 4-stage cycle arc for the page glyph.
# Each stage owns a quarter band; weeks_in_stage saturates the offset within it.
_ARC_BAND = 0.25
_ARC_SATURATE_WEEKS = 20.0    # weeks after which a stage's arc offset is ~full band


def _empty_result(too_young: bool = True, n_weeks: int = 0) -> dict:
    """A well-formed null result (never raises downstream).

    n_weeks carries the count of completed weekly bars even on a too-young /
    unclassifiable path (0 when the weekly frame is empty), so the
    stage_analysis too-young guard (n_weeks < MIN_WEEKS) stays honest.
    """
    return {
        "stage": 0,
        "weeks_in_stage": 0,
        "fresh": False,
        "n_weeks": int(n_weeks),
        "ma30": None,
        "ma30_slope_pct5w": None,
        "pct_vs_ma30": None,
        "mansfield_rs": None,
        "vol_ratio": None,
        "event": None,
        "arc_pos": 0.0,
        "too_young": bool(too_young),
        "history": [],
    }


def _slope_pct5w(ma: pd.Series) -> pd.Series:
    """(ma[t] - ma[t-5]) / ma[t-5] * 100, aligned to ma's index. NaN-safe."""
    prev = ma.shift(SLOPE_LOOKBACK_W)
    with np.errstate(divide="ignore", invalid="ignore"):
        sl = (ma - prev) / prev * 100.0
    return sl.replace([np.inf, -np.inf], np.nan)


def weekly_frame(close: pd.Series,
                 volume: pd.Series | None,
                 bench_close: pd.Series) -> pd.DataFrame:
    """Build the completed-week weekly frame for the stage machine.

    Columns: wclose, ma30, slope_5w (pct), mansfield_rs, vol_4w, vol_30w,
    vol_ratio. Index = completed W-FRI Fridays. Returns an EMPTY frame (with
    the right columns) on unusable input — the caller treats that as too-young.
    """
    cols = ["wclose", "ma30", "slope_5w", "mansfield_rs",
            "vol_4w", "vol_30w", "vol_ratio"]
    if close is None or len(close) == 0:
        return pd.DataFrame(columns=cols)

    c = pd.Series(close).dropna()
    if c.empty or not isinstance(c.index, pd.DatetimeIndex):
        # Coerce a non-datetime index defensively; if that fails, bow out.
        try:
            c.index = pd.to_datetime(c.index)
        except Exception:  # pragma: no cover - defensive
            return pd.DataFrame(columns=cols)
    c = c[~c.index.duplicated(keep="last")].sort_index()

    wclose = _w_fri_completed(c)
    if wclose.empty:
        return pd.DataFrame(columns=cols)

    ma30 = wclose.rolling(MA_WEEKS, min_periods=MA_WEEKS).mean()
    slope = _slope_pct5w(ma30)

    # Mansfield RS (SGA-R2): rs = wclose / bench_wclose (aligned on the weekly
    # grid), then (rs / rs.rolling(52).mean() - 1) * 100.
    mansfield = pd.Series(np.nan, index=wclose.index)
    try:
        b = pd.Series(bench_close).dropna()
        if not b.empty:
            if not isinstance(b.index, pd.DatetimeIndex):
                b.index = pd.to_datetime(b.index)
            b = b[~b.index.duplicated(keep="last")].sort_index()
            bw = _w_fri_completed(b)
            bw = bw.reindex(wclose.index, method="ffill")
            with np.errstate(divide="ignore", invalid="ignore"):
                rs = wclose / bw
            rs = rs.replace([np.inf, -np.inf], np.nan)
            rs_mean = rs.rolling(RS_MEAN_WEEKS, min_periods=RS_MEAN_WEEKS).mean()
            with np.errstate(divide="ignore", invalid="ignore"):
                mansfield = (rs / rs_mean - 1.0) * 100.0
            mansfield = mansfield.replace([np.inf, -np.inf], np.nan)
    except Exception:  # pragma: no cover - RS is context-only; never fatal
        mansfield = pd.Series(np.nan, index=wclose.index)

    # Weekly volume = sum over the completed week; averages over 4w / 30w.
    vol_4w = pd.Series(np.nan, index=wclose.index)
    vol_30w = pd.Series(np.nan, index=wclose.index)
    vol_ratio = pd.Series(np.nan, index=wclose.index)
    if volume is not None and len(volume) > 0:
        try:
            v = pd.Series(volume).dropna()
            if not v.empty:
                if not isinstance(v.index, pd.DatetimeIndex):
                    v.index = pd.to_datetime(v.index)
                v = v[~v.index.duplicated(keep="last")].sort_index()
                last_obs = v.index.max()
                wvol = v.resample("W-FRI").sum()
                wvol = wvol[wvol.index <= last_obs]
                wvol = wvol.reindex(wclose.index)
                vol_4w = wvol.rolling(VOL_SHORT_W, min_periods=1).mean()
                vol_30w = wvol.rolling(VOL_LONG_W, min_periods=VOL_SHORT_W).mean()
                with np.errstate(divide="ignore", invalid="ignore"):
                    vol_ratio = vol_4w / vol_30w
                vol_ratio = vol_ratio.replace([np.inf, -np.inf], np.nan)
        except Exception:  # pragma: no cover - volume is optional
            vol_4w = pd.Series(np.nan, index=wclose.index)
            vol_30w = pd.Series(np.nan, index=wclose.index)
            vol_ratio = pd.Series(np.nan, index=wclose.index)

    return pd.DataFrame({
        "wclose": wclose,
        "ma30": ma30,
        "slope_5w": slope,
        "mansfield_rs": mansfield,
        "vol_4w": vol_4w,
        "vol_30w": vol_30w,
        "vol_ratio": vol_ratio,
    })


def _classify_row(wclose: float, ma30: float, slope: float,
                  prev_stage: int) -> int:
    """SGA-R1 single-bar rule with hysteresis (prev_stage disambiguates 1 vs 3).

    Returns 0 if the row is not yet classifiable (NaN ma30/slope) — the caller
    inherits the previous stage for ambiguous cells.
    """
    if not (np.isfinite(wclose) and np.isfinite(ma30) and np.isfinite(slope)):
        return 0  # not classifiable yet -> inherit prev
    flat = abs(slope) < FLAT_SLOPE_PCT
    above = wclose > ma30
    if not flat:
        rising = slope > 0
        if above and rising:
            return 2
        if (not above) and (not rising):
            return 4
        # ambiguous non-flat cell (e.g. close above but slope falling):
        # inherit the previous stage per SGA-R1.
        return prev_stage if prev_stage else 0
    # flat slope: Stage 3 if we arrived from an advance, else Stage 1.
    if prev_stage in (2, 3):
        return 3
    if prev_stage in (1, 4):
        return 1
    # unknown prior with a flat slope: side with position vs the line.
    return 1


def _run_machine(wf: pd.DataFrame) -> tuple[list[int], list[int]]:
    """Run the hysteresis state machine; return (stage_per_week, weeks_in_stage)."""
    n = len(wf)
    stages = [0] * n
    weeks = [0] * n
    wc = wf["wclose"].to_numpy(dtype=float)
    ma = wf["ma30"].to_numpy(dtype=float)
    sl = wf["slope_5w"].to_numpy(dtype=float)
    prev = 0
    prev_weeks = 0
    for i in range(n):
        st = _classify_row(wc[i], ma[i], sl[i], prev)
        if st == 0:
            # inherit previous stage (ambiguous / not-yet-classifiable cell)
            st = prev
        if st == prev and st != 0:
            prev_weeks += 1
        else:
            prev_weeks = 1 if st != 0 else 0
        stages[i] = st
        weeks[i] = prev_weeks
        prev = st
    return stages, weeks


def _arc_pos(stage: int, weeks_in_stage: int) -> float:
    """Position along the idealized cycle arc (masterplan §2). [0,1)."""
    if stage not in (1, 2, 3, 4):
        return 0.0
    base = (stage - 1) * _ARC_BAND
    frac = min(max(weeks_in_stage, 0) / _ARC_SATURATE_WEEKS, 0.999)
    return round(base + frac * _ARC_BAND, 4)


def _detect_event(wf: pd.DataFrame, stages: list[int], i: int) -> str | None:
    """Event chip for bar i (SGA-R1). Volume-dependent events skip if vol is NaN."""
    if i <= 0:
        return None
    wc = wf["wclose"].to_numpy(dtype=float)
    ma = wf["ma30"].to_numpy(dtype=float)
    vr = wf["vol_ratio"].to_numpy(dtype=float)
    st = stages[i]
    prev_st = stages[i - 1]

    # breakout: S1->S2 with weekly close > prior 10-week high on vol_ratio >= 1.5.
    if st == 2 and prev_st == 1:
        lo = max(0, i - BREAKOUT_HIGH_W)
        prior_high = np.nanmax(wc[lo:i]) if i > lo else np.nan
        vol_ok = np.isfinite(vr[i]) and vr[i] >= BREAKOUT_VOL_RATIO
        if (np.isfinite(wc[i]) and np.isfinite(prior_high)
                and wc[i] > prior_high and vol_ok):
            return "breakout"

    # trendline_recapture: within S2, weekly close recrosses above a rising ma30.
    if st == 2:
        rising = (np.isfinite(ma[i]) and np.isfinite(ma[i - 1])
                  and ma[i] > ma[i - 1])
        crossed_up = (np.isfinite(wc[i]) and np.isfinite(ma[i])
                      and np.isfinite(wc[i - 1]) and np.isfinite(ma[i - 1])
                      and wc[i] > ma[i] and wc[i - 1] <= ma[i - 1])
        if rising and crossed_up:
            return "trendline_recapture"

    # pullback_resume: in S2, price made a >=3wk low that held above ma30, then
    # closes up. We flag the up-week that follows the local low.
    if st == 2 and i >= PULLBACK_LOW_W:
        lo = i - PULLBACK_LOW_W
        # local low over the window ending last week, all above ma30
        window = wc[lo:i]  # weeks [i-3 .. i-1]
        mawin = ma[lo:i]
        if len(window) >= PULLBACK_LOW_W and np.all(np.isfinite(window)):
            all_above = np.all(np.isfinite(mawin) & (window > mawin))
            up_week = (np.isfinite(wc[i]) and np.isfinite(wc[i - 1])
                       and wc[i] > wc[i - 1])
            close_above = np.isfinite(ma[i]) and wc[i] > ma[i]
            if all_above and up_week and close_above:
                return "pullback_resume"
    return None


def _last_val(series: pd.Series) -> float | None:
    if series is None or len(series) == 0:
        return None
    v = series.iloc[-1]
    return float(v) if pd.notna(v) else None


def classify(close: pd.Series,
             volume: pd.Series | None,
             bench_close: pd.Series) -> dict:
    """Classify a name's CURRENT Weinstein stage (last completed week).

    Returns the last-bar dict per SGA-R1 / masterplan §2. Fail-open: a short
    or unusable series returns a too-young dict; missing volume nulls the vol
    fields and skips volume-dependent events.
    """
    wf = weekly_frame(close, volume, bench_close)
    if wf.empty or len(wf) < MIN_COMPLETED_WEEKS:
        return _empty_result(too_young=True, n_weeks=int(len(wf)))

    stages, weeks = _run_machine(wf)
    last = len(wf) - 1
    stage = stages[last]
    wis = weeks[last]

    if stage == 0:
        # Could not classify even at the last bar (all-NaN ma30 tail): too young.
        return _empty_result(too_young=True, n_weeks=int(len(wf)))

    event = _detect_event(wf, stages, last)

    ma30 = _last_val(wf["ma30"])
    wclose = _last_val(wf["wclose"])
    pct_vs_ma30 = None
    if ma30 is not None and wclose is not None and ma30 != 0:
        pct_vs_ma30 = round((wclose / ma30 - 1.0) * 100.0, 2)

    slope = _last_val(wf["slope_5w"])
    mansfield = _last_val(wf["mansfield_rs"])
    vol_ratio = _last_val(wf["vol_ratio"])

    # trailing (iso_week_date, stage) for the last HISTORY_WEEKS weeks
    idx = wf.index
    hist_start = max(0, len(wf) - HISTORY_WEEKS)
    history = [
        (idx[j].date().isoformat(), int(stages[j]))
        for j in range(hist_start, len(wf))
    ]

    fresh = bool(stage == 2 and wis <= 10)

    return {
        "stage": int(stage),
        "weeks_in_stage": int(wis),
        "fresh": fresh,
        "n_weeks": int(len(wf)),
        "ma30": round(ma30, 4) if ma30 is not None else None,
        "ma30_slope_pct5w": round(slope, 4) if slope is not None else None,
        "pct_vs_ma30": pct_vs_ma30,
        "mansfield_rs": round(mansfield, 2) if mansfield is not None else None,
        "vol_ratio": round(vol_ratio, 3) if vol_ratio is not None else None,
        "event": event,
        "arc_pos": _arc_pos(stage, wis),
        "too_young": False,
        "history": history,
    }


def stage_series(close: pd.Series,
                 volume: pd.Series | None,
                 bench_close: pd.Series) -> pd.Series:
    """Per-week integer stage (1..4; 0 where not yet classifiable).

    Index = completed W-FRI weekly Fridays. Empty Series on unusable input.
    """
    wf = weekly_frame(close, volume, bench_close)
    if wf.empty:
        return pd.Series([], dtype="int64")
    stages, _ = _run_machine(wf)
    return pd.Series(stages, index=wf.index, dtype="int64")
