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
# SGA-2 (v2) constants — ATR extension, SATA composite, stage_detailed taxonomy.
# These reproduce the EquityDesk yardstick columns (atr_ext, sata_score,
# stage_detailed) from OUR OHLCV. Everything is DISPLAY-TIER / context-only.
#
# Calibration provenance (data/stage_analysis/backfill/stage_daily.parquet,
# 6,536 rows): atr_ext == (close - sma_30w) / atr_14w reproduced at r=1.0,
# MAE ~8e-10 on our reconstructed weekly ATR. sata_score is their proprietary
# 0-10 quality integer; strongest drivers are atr_ext (r=.85), mansfield_rs
# (r=.75) and the stage. We reproduce it with a deterministic trend-quality
# composite quantile-mapped to their 0-10 marginal (Spearman ~.92 on their own
# features; see tests for the reproduce-from-our-OHLCV calibration).
#
# HONESTY on the two DIFFERENT agreement metrics (do NOT foreground only the
# strong ones): the COARSE stage_flag (1..4) reproduces at ~73% agreement, but
# the FINE stage_detailed TOP-LABEL agreement is only ~0.40 — their taxonomy has
# ~16 labels (e.g. 2B_steady_trend, 3B_rs_divergence, 3X_catch_down_above_ma) to
# our 9, so many of our reads land on a neighbouring detailed label with the same
# coarse stage. The screener/board calibration.note discloses BOTH, not just the
# SATA/atr_ext strengths.
# ---------------------------------------------------------------------------
ATR_WEEKS = 14                # 14-week ATR (Wilder TR, simple mean of weekly TR)

# SATA composite weights (fit offline to stage_daily; do not change without a
# re-fit against the seed table and a test update).
_SATA_STAGE_BASE = {2: 6.5, 1: 4.0, 3: 3.2, 4: 1.6, 0: 0.4}
_SATA_W_ATR_EXT = 0.7         # atr_ext (clipped ±6) weight
_SATA_W_MANSFIELD = 0.01      # mansfield_rs (clipped ±60) weight
_SATA_W_STAGE = 0.6           # stage-base weight
_SATA_ATR_CLIP = 6.0
_SATA_MRS_CLIP = 60.0
# Quantile cutpoints mapping the continuous composite -> integer 0..10, fit to
# reproduce the EquityDesk sata_score marginal distribution. cut[k] is the
# upper edge of bucket k (a composite <= cut[k] and > cut[k-1] scores k).
_SATA_CUTS = (-1.072, -0.180, 0.448, 1.347, 3.948,
              4.444, 4.830, 5.236, 6.476, 8.177)

# stage_detailed decision thresholds (fit to the per-label feature profiles in
# stage_daily: median atr_ext / weeks / mansfield_rs per label).
_SD_S2_STRONG_ATR = 1.9       # 2A/2D strong-extension floor (their medians ~2.1-2.4)
_SD_S2_CATCH_ATR = 0.9        # 2X_catch low-extension ceiling (their median ~0.46)
_SD_S3_BLOWOFF_ATR = -0.8     # 3C blowoff: rolled below the line with weak RS
_SD_S4_STEADY_WEEKS = 7       # 4B steady-decline minimum age (else 4X fallback)

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
        # SGA-2 yardstick fields (null on the too-young path).
        "atr_14w": None,
        "atr_ext": None,
        "atr_pct_price": None,
        "sata_score": None,
        "sata_change_1w": None,
        "stage_detailed": None,
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


def weekly_atr14(high: pd.Series | None,
                 low: pd.Series | None,
                 close: pd.Series,
                 index: pd.DatetimeIndex) -> pd.Series:
    """14-week ATR (Wilder True Range, simple mean) aligned to `index`.

    Reproduces the EquityDesk `atr_14w` column (r=1.0 on our reconstruction):
    weekly TR = max(H-L, |H-Cprev|, |L-Cprev|) on W-FRI-resampled OHLC, then a
    simple 14-week rolling mean. If high/low are missing we fall back to a
    close-only TR (|Cprev - C|) so the field is still populated (degraded but
    monotone). Fail-open: returns an all-NaN Series aligned to `index` on any
    error, so extension fields simply null out rather than crashing a build.
    """
    nan = pd.Series(np.nan, index=index)
    try:
        c = pd.Series(close).dropna()
        if c.empty:
            return nan
        if not isinstance(c.index, pd.DatetimeIndex):
            c.index = pd.to_datetime(c.index)
        c = c[~c.index.duplicated(keep="last")].sort_index()
        last_obs = c.index.max()
        wc = c.resample("W-FRI").last()

        if high is not None and low is not None and len(high) and len(low):
            h = pd.Series(high).dropna()
            lo = pd.Series(low).dropna()
            if not isinstance(h.index, pd.DatetimeIndex):
                h.index = pd.to_datetime(h.index)
            if not isinstance(lo.index, pd.DatetimeIndex):
                lo.index = pd.to_datetime(lo.index)
            h = h[~h.index.duplicated(keep="last")].sort_index()
            lo = lo[~lo.index.duplicated(keep="last")].sort_index()
            wh = h.resample("W-FRI").max()
            wl = lo.resample("W-FRI").min()
        else:
            # Close-only degraded TR: treat each weekly close as its own H/L.
            wh = wc
            wl = wc

        prev_c = wc.shift(1)
        tr = pd.concat(
            [wh - wl, (wh - prev_c).abs(), (wl - prev_c).abs()], axis=1
        ).max(axis=1)
        tr = tr[tr.index <= last_obs]
        atr = tr.rolling(ATR_WEEKS, min_periods=ATR_WEEKS).mean()
        return atr.reindex(index)
    except Exception:  # noqa: BLE001 — extension fields are context-only
        return nan


def _sata_from(stage: int | None, atr_ext: float | None,
               mansfield_rs: float | None) -> int | None:
    """Deterministic 0-10 SATA reproduction (calibrated to EquityDesk).

    Composite = stage-base + w·atr_ext(clipped) + w·mansfield_rs(clipped), then
    quantile-mapped through _SATA_CUTS to their 0-10 marginal. Fail-open: a null
    atr_ext OR mansfield falls back to 0 for that term so a partial record still
    scores; a null stage returns None (not stageable -> no SATA).
    """
    if stage in (None, 0):
        return None
    base = _SATA_STAGE_BASE.get(int(stage), 3.0) * _SATA_W_STAGE
    ae = 0.0
    if atr_ext is not None and np.isfinite(atr_ext):
        ae = float(np.clip(atr_ext, -_SATA_ATR_CLIP, _SATA_ATR_CLIP)) * _SATA_W_ATR_EXT
    mrs = 0.0
    if mansfield_rs is not None and np.isfinite(mansfield_rs):
        mrs = float(np.clip(mansfield_rs, -_SATA_MRS_CLIP, _SATA_MRS_CLIP)) * _SATA_W_MANSFIELD
    comp = base + ae + mrs
    for k, cut in enumerate(_SATA_CUTS):
        if comp <= cut:
            return k
    return 10


def _stage_detailed(stage: int | None, weeks: int, atr_ext: float | None,
                    mansfield_rs: float | None, event: str | None,
                    fresh: bool) -> str | None:
    """Map (stage, events, extension, RS, age) onto the EquityDesk 9-label
    stage_detailed taxonomy. Fail-open: an unstageable name -> None.

    Labels (their exact strings):
      1X_fallback_base, 2A_strong_breakout, 2D_extended_run,
      2X_catch_price_above_ma, 2X_fallback_bullish, 3A_sideways_exhaustion,
      3C_volatility_blowoff, 4B_steady_decline, 4X_fallback_bearish.
    """
    if stage in (None, 0):
        return None
    ae = atr_ext if (atr_ext is not None and np.isfinite(atr_ext)) else 0.0
    mrs = mansfield_rs if (mansfield_rs is not None and np.isfinite(mansfield_rs)) else 0.0

    if stage == 1:
        return "1X_fallback_base"

    if stage == 2:
        # Fresh breakout week on volume -> 2A_strong_breakout.
        if event == "breakout":
            return "2A_strong_breakout"
        # Fresh recapture / low-extension, weak-to-neutral RS name that has just
        # reclaimed the line -> 2X_catch_price_above_ma ("2X Catch"). Their
        # catch cohort: atr_ext median ~0.46, mansfield_rs median ~-6.
        if ae <= _SD_S2_CATCH_ATR and mrs <= 5.0:
            return "2X_catch_price_above_ma"
        # Strongly extended above the line: young + RS-strong reads as a fresh
        # strong breakout (2A); otherwise it is an aged extended run (2D).
        if ae >= _SD_S2_STRONG_ATR:
            if fresh and mrs >= 10.0:
                return "2A_strong_breakout"
            return "2D_extended_run"
        # Established, still above the line -> 2X_fallback_bullish ("2X Bullish").
        return "2X_fallback_bullish"

    if stage == 3:
        # Rolled below with weak RS / negative extension = volatility blowoff.
        if ae <= _SD_S3_BLOWOFF_ATR or mrs <= -25.0:
            return "3C_volatility_blowoff"
        return "3A_sideways_exhaustion"

    # stage == 4: aged, steeply-below-the-line decline is a "steady decline"
    # (4B); everything else falls back to the deep-bear default (4X, the
    # dominant class ~2,888/3,197 of their stage-4 names).
    if weeks >= _SD_S4_STEADY_WEEKS and ae <= -1.8:
        return "4B_steady_decline"
    return "4X_fallback_bearish"


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
             bench_close: pd.Series,
             high: pd.Series | None = None,
             low: pd.Series | None = None) -> dict:
    """Classify a name's CURRENT Weinstein stage (last completed week).

    Returns the last-bar dict per SGA-R1 / masterplan §2, EXTENDED (SGA-2) with
    the EquityDesk yardstick fields: atr_14w, atr_ext, atr_pct_price, sata_score,
    sata_change_1w, stage_detailed. Fail-open: a short or unusable series returns
    a too-young dict; missing volume nulls the vol fields; missing high/low falls
    back to a close-only ATR (the extension fields degrade, never crash).
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

    # --- SGA-2 extension fields (atr_14w / atr_ext / atr_pct_price) ---
    atr = weekly_atr14(high, low, close, wf.index)
    atr_14w = _last_val(atr)
    atr_ext = None
    atr_pct_price = None
    if (atr_14w is not None and atr_14w > 0
            and wclose is not None and ma30 is not None):
        atr_ext = (wclose - ma30) / atr_14w
        if wclose != 0:
            atr_pct_price = atr_14w / wclose

    # trailing (iso_week_date, stage) for the last HISTORY_WEEKS weeks
    idx = wf.index
    hist_start = max(0, len(wf) - HISTORY_WEEKS)
    history = [
        (idx[j].date().isoformat(), int(stages[j]))
        for j in range(hist_start, len(wf))
    ]

    fresh = bool(stage == 2 and wis <= 10)

    # --- SGA-2 SATA + stage_detailed (+ 1-week SATA change) ---
    sata = _sata_from(stage, atr_ext, mansfield)
    sata_change_1w = None
    if sata is not None and last >= 1:
        # SATA one week ago: recompute from the prior completed week's fields.
        prev = last - 1
        prev_stage = stages[prev]
        p_ma = wf["ma30"].to_numpy(dtype=float)[prev]
        p_wc = wf["wclose"].to_numpy(dtype=float)[prev]
        p_atr = atr.to_numpy(dtype=float)[prev] if len(atr) > prev else np.nan
        p_ext = None
        if np.isfinite(p_atr) and p_atr > 0 and np.isfinite(p_wc) and np.isfinite(p_ma):
            p_ext = (p_wc - p_ma) / p_atr
        p_mrs = wf["mansfield_rs"].to_numpy(dtype=float)[prev]
        p_mrs = float(p_mrs) if np.isfinite(p_mrs) else None
        prev_sata = _sata_from(prev_stage, p_ext, p_mrs)
        if prev_sata is not None:
            sata_change_1w = sata - prev_sata

    stage_detailed = _stage_detailed(stage, wis, atr_ext, mansfield, event, fresh)

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
        # SGA-2 EquityDesk yardstick fields (display-tier / context-only):
        "atr_14w": round(atr_14w, 4) if atr_14w is not None else None,
        "atr_ext": round(atr_ext, 4) if atr_ext is not None else None,
        "atr_pct_price": round(atr_pct_price, 5) if atr_pct_price is not None else None,
        "sata_score": sata,
        "sata_change_1w": sata_change_1w,
        "stage_detailed": stage_detailed,
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
