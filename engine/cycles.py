"""Cycle analysis + multi-timeframe technicals + the entry/exit signal ladder.

Methodology (graddhy.com, thefinancialtap.com — see DECISIONS):
- Daily cycle (DC): trough-to-trough, equities typically 36-42 trading days;
  the timing band catches ~70% of lows (that miss rate is displayed, never
  hidden). DCL = daily cycle low.
- Investor cycle (IC): 16-26 weeks, typically containing ~4-6 daily cycles.
- Swing low = price takes out the high of the candle that made the low;
  cycle-low confirmation adds: close back above the 10-day MA, and the 10-day
  MA turning up.
- Translation: where the cycle's crest fell relative to its midpoint.
  Right-translated = bullish structure; left-translated usually means the
  larger cycle has topped.
- Failed cycle: price breaks below the low that BIRTHED the current cycle —
  the single most reliable bearish tell in the framework (~80% per source).

Multi-timeframe indicators: daily, 3-day and weekly MACD(12,26,9), RSI(14),
RSI(5) and StochRSI(14) with cross detection plus *approaching-cross*
proximity (histogram trajectory), so the ladder can say "close to a turn",
not just "turned".

The ladder's per-state forward stats are measured by calibrate_ladder() and
shipped with the UI — trust levels are printed, not implied.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine.technicals import macd_hist, rsi
from lib import config

log = logging.getLogger(__name__)

DC_BAND = (36, 42)        # equity daily cycle, trading days (timing band)
DC_EARLY = 12             # "new cycle" window after a DCL
IC_BAND_W = (16, 26)      # investor cycle, weeks
TROUGH_WINDOW = 10        # local-minimum half-window for trough detection
TROUGH_MIN_GAP = 18       # merge troughs closer than this (days)

# Per-asset-class cycle clock. Crypto trades 7 days/week with no gaps, so its
# daily cycle runs MUCH longer in calendar days than an equity's (the cycle-
# analyst convention — graddhy / thefinancialtap — is ~8-10 weeks for BTC vs
# 36-42 trading days for equities/gold). Applying the equity band to BTC made
# it read as "stretched / bottoming" far too early, and `3B` (3 business days)
# silently mishandles weekend bars — crypto uses 3-CALENDAR-day bars instead.
CYCLE_PRESETS = {
    # cand_depth_bars: how many bars before the candidate low to scan for the prior
    # swing high, used to measure the depth of the pullback.  Equity DC is ~36-42
    # trading days so ~15 bars captures roughly one-third of the cycle (the typical
    # correction leg).  Crypto DC is ~56-70 CALENDAR days, nearly double, so 30
    # bars is the proportional equivalent.  FX DC is close to equity (30-44 days),
    # so 15 bars is appropriate there too.
    "equity": {"dc_band": (36, 42), "dc_early": 12, "ic_band_w": (16, 26), "tf3": "3B",
               "cand_depth_bars": 15},
    "crypto": {"dc_band": (56, 70), "dc_early": 18, "ic_band_w": (24, 40), "tf3": "3D",
               "cand_depth_bars": 30},
    # FX MEASURED (research/FOREX_DASHBOARD.md): across the G10 majors the daily
    # cycle low recurs ~35 trading days apart (median; IQR 25-47) — close to equities
    # but shorter and NOISIER, so a wider band; the intermediate cycle is ~34 weeks
    # (vs ~16-26 for equities), nearly double. FX trades business days (3B, not 3D).
    "fx": {"dc_band": (30, 44), "dc_early": 11, "ic_band_w": (26, 42), "tf3": "3B",
           "cand_depth_bars": 15},
}

# ── Fitted-band override (W2.8 cycles-core-2) ────────────────────────────────
# Loaded lazily from data/regime/cycle_bands_fit.json on the first _preset() call.
# When present, dc_band and ic_band_w override the hand-constants above per class.
# All other preset fields (dc_early, tf3, cand_depth_bars) come from CYCLE_PRESETS.
# On any load error the hand-constants are the unaffected fallback — never fatal.
_FITTED_BANDS: dict = {}
_FITTED_BANDS_LOADED: bool = False
_FITTED_BANDS_LOGGED: set = set()   # track which kinds have been logged (once)


def _load_fitted_bands() -> dict:
    """Load cycle_bands_fit.json. Returns {} on any error (fallback to CYCLE_PRESETS)."""
    try:
        p = config.data_dir() / "regime" / "cycle_bands_fit.json"
        if not p.exists():
            return {}
        import json as _json
        d = _json.loads(p.read_text(encoding="utf-8"))
        log.info("cycles: loaded fitted bands from %s", p)
        return d
    except Exception as e:  # noqa: BLE001
        log.debug("cycles: fitted bands unavailable (%s) — using CYCLE_PRESETS constants", e)
        return {}


# ── W4.6 risk-channel binding calibration (data/regime/ladder_risk_calibration.json) ──
# Additive SIZE multiplier per (ladder state x family) — NEVER a directional score.
# Loaded lazily on the first ladder_state() call. When ABSENT the multiplier is 1.0 for
# every state (byte-identical to today). When PRESENT it binds ONLY the cells that earned
# a weight != 1.0 (FDR-survived, CI excludes null); everything else is 1.0. Per the W4.6
# verdict the artifact currently ships ALL 1.0 (no risk-sizing signal survived) — so the
# binding is presently a numeric no-op. The DIRECTIONAL LADDER_SCORE stays UNTOUCHED this
# wave: direction was never validated and the axis-flip is W4.7's question.
_RISK_CALIB: dict = {}
_RISK_CALIB_LOADED: bool = False
_RISK_CALIB_LOGGED: set = set()   # (family, state) pairs whose non-1.0 override was logged


def _load_risk_calib() -> dict:
    """Load ladder_risk_calibration.json -> {family: {state: mult}}. Returns {} on any
    error (fallback to all-1.0). Mirrors _load_fitted_bands (W2.8)."""
    try:
        p = config.data_dir() / "regime" / "ladder_risk_calibration.json"
        if not p.exists():
            return {}
        import json as _json
        d = _json.loads(p.read_text(encoding="utf-8"))
        rsm = d.get("risk_size_mult") or {}
        clamp = d.get("mult_clamp") or [0.5, 1.5]
        out: dict = {}
        for fam, states in rsm.items():
            out[fam] = {}
            for st, cell in states.items():
                m = cell.get("risk_size_mult", 1.0) if isinstance(cell, dict) else float(cell)
                out[fam][st] = float(min(max(m, clamp[0]), clamp[1]))
        log.info("cycles: loaded ladder risk calibration from %s (validated=%s, any_bound=%s)",
                 p, d.get("validated"), d.get("any_cell_bound"))
        return out
    except Exception as e:  # noqa: BLE001
        log.debug("cycles: ladder risk calibration unavailable (%s) — using 1.0 for all states", e)
        return {}


# engine hazard-pool family tags -> calibration family keys (the artifact is keyed on the
# keystone families us_sector/country). Unmapped families (basket/flagship) have no fitted
# cells and fall through to 1.0.
_RISK_FAMILY_ALIAS = {"sector": "us_sector", "us_sector": "us_sector",
                      "country": "country", "equity": "us_sector"}


def risk_size_mult(state: str, family: str | None) -> float:
    """Fitted SIZE multiplier in [0.5,1.5] for (state, family). 1.0 when no artifact, no
    family, or the cell did not earn a weight (null-cell discipline). Additive to sizing,
    NEVER to the directional score. One-time log per non-1.0 (state,family)."""
    global _RISK_CALIB, _RISK_CALIB_LOADED  # noqa: PLW0603
    if not _RISK_CALIB_LOADED:
        _RISK_CALIB = _load_risk_calib()
        _RISK_CALIB_LOADED = True
    fam = _RISK_FAMILY_ALIAS.get(family or "", family)
    if not fam or fam not in _RISK_CALIB:
        return 1.0
    m = _RISK_CALIB[fam].get(state, 1.0)
    if m != 1.0 and (fam, state) not in _RISK_CALIB_LOGGED:
        log.info("cycles: %s/%s risk_size_mult override -> %.3fx (fitted, W4.6)", fam, state, m)
        _RISK_CALIB_LOGGED.add((fam, state))
    return m


def _preset(kind: str) -> dict:
    """Return preset for `kind`, with dc_band / ic_band_w overridden by the fitted
    artifact when available. All other fields come from CYCLE_PRESETS.  Falls back
    to the equity preset for unknown kinds."""
    global _FITTED_BANDS, _FITTED_BANDS_LOADED  # noqa: PLW0603
    if not _FITTED_BANDS_LOADED:
        _FITTED_BANDS = _load_fitted_bands()
        _FITTED_BANDS_LOADED = True

    base = dict(CYCLE_PRESETS.get(kind, CYCLE_PRESETS["equity"]))

    fitted = _FITTED_BANDS.get(kind)
    if fitted:
        fdc = fitted.get("dc_band")
        fic = fitted.get("ic_band_w")
        if fdc and len(fdc) == 2 and fdc[0] > 0 and fdc[1] > fdc[0]:
            if kind not in _FITTED_BANDS_LOGGED:
                log.info("cycles: %s dc_band override %s → %s (fitted)", kind,
                         base["dc_band"], tuple(fdc))
                _FITTED_BANDS_LOGGED.add(kind)
            base["dc_band"] = tuple(fdc)
        if fic and len(fic) == 2 and fic[0] > 0 and fic[1] > fic[0]:
            if (kind + "_ic") not in _FITTED_BANDS_LOGGED:
                log.info("cycles: %s ic_band_w override %s → %s (fitted)", kind,
                         base["ic_band_w"], tuple(fic))
                _FITTED_BANDS_LOGGED.add(kind + "_ic")
            base["ic_band_w"] = tuple(fic)

    return base


# ------------------------------------------------------------ indicators ----

def stoch_rsi(close: pd.Series, n: int = 14, k: int = 3) -> pd.Series:
    r = rsi(close, n)
    lo = r.rolling(n).min()
    hi = r.rolling(n).max()
    raw = (r - lo) / (hi - lo).replace(0, np.nan) * 100
    return raw.rolling(k).mean()


def macd_parts(close: pd.Series) -> pd.DataFrame:
    ema12 = close.ewm(span=12, min_periods=12).mean()
    ema26 = close.ewm(span=26, min_periods=26).mean()
    line = ema12 - ema26
    sig = line.ewm(span=9, min_periods=9).mean()
    return pd.DataFrame({"line": line, "signal": sig, "hist": line - sig})


# Linear extrapolation of a 3-bar MACD-histogram slope only carries information
# a few bars out; past this horizon the cross isn't "approaching", the histogram
# is just drifting near zero. Beyond the cap we drop the ETA rather than surface
# a saturated, meaningless number (the old clip-to-99 produced "≈99 bars/days to
# cross" for a near-flat slope).
_MACD_APPROACH_MAX_BARS = 6


def _tf_state(close: pd.Series) -> dict:
    """Indicator snapshot for one timeframe (already-resampled close)."""
    if len(close) < 40:
        return {}
    m = macd_parts(close)
    hist = m["hist"]
    r14 = rsi(close, 14)
    r5 = rsi(close, 5)
    srsi = stoch_rsi(close)
    cross_up = bool(hist.iloc[-1] > 0 and (hist.iloc[-4:-1] <= 0).any())
    cross_dn = bool(hist.iloc[-1] < 0 and (hist.iloc[-4:-1] >= 0).any())
    # approaching: histogram still negative but rising 3 bars in a row —
    # estimate bars to the zero cross from its current slope
    h = hist.dropna()
    approaching_up = approaching_dn = False
    macd_curl_up = macd_curl_dn = False
    bars_to_cross = None
    if len(h) >= 4:
        slope = (h.iloc[-1] - h.iloc[-4]) / 3
        rising = bool(h.iloc[-1] > h.iloc[-2] > h.iloc[-3])
        falling = bool(h.iloc[-1] < h.iloc[-2] < h.iloc[-3])
        if h.iloc[-1] < 0 and rising and slope > 0:
            eta = -h.iloc[-1] / slope
            if eta <= _MACD_APPROACH_MAX_BARS:
                approaching_up = True
                bars_to_cross = float(max(eta, 0.5))
        elif h.iloc[-1] > 0 and falling and slope < 0:
            eta = h.iloc[-1] / -slope
            if eta <= _MACD_APPROACH_MAX_BARS:
                approaching_dn = True
                bars_to_cross = float(max(eta, 0.5))
        # histogram trough/peak turn — Aspray's earliest pre-cross flag: a local
        # min in the histogram while still below zero (1 confirming up-bar)
        macd_curl_up = bool(h.iloc[-1] < 0 and h.iloc[-1] > h.iloc[-2] <= h.iloc[-3])
        macd_curl_dn = bool(h.iloc[-1] > 0 and h.iloc[-1] < h.iloc[-2] >= h.iloc[-3])

    # StochRSI popping out of oversold/overbought — the earliest oscillator heads-up
    sclean = srsi.dropna()
    stoch_cross_up = bool(len(sclean) >= 4 and sclean.iloc[-1] >= 20
                          and (sclean.iloc[-4:-1] < 20).any())
    stoch_cross_dn = bool(len(sclean) >= 4 and sclean.iloc[-1] <= 80
                          and (sclean.iloc[-4:-1] > 80).any())
    def _spark(s: pd.Series, n: int = 20, dec: int = 1) -> list:
        return [round(float(x), dec) for x in s.dropna().iloc[-n:]]

    return {
        "macd_pos": bool(hist.iloc[-1] > 0),
        "macd_cross_up": cross_up, "macd_cross_dn": cross_dn,
        "macd_approaching_up": approaching_up, "macd_approaching_dn": approaching_dn,
        "macd_curl_up": macd_curl_up, "macd_curl_dn": macd_curl_dn,
        "macd_bars_to_cross": round(bars_to_cross, 1) if bars_to_cross else None,
        "stoch_cross_up": stoch_cross_up, "stoch_cross_dn": stoch_cross_dn,
        "rsi14": round(float(r14.iloc[-1]), 0) if pd.notna(r14.iloc[-1]) else None,
        "rsi5": round(float(r5.iloc[-1]), 0) if pd.notna(r5.iloc[-1]) else None,
        "stoch": round(float(srsi.iloc[-1]), 0) if pd.notna(srsi.iloc[-1]) else None,
        # compact recent series for client-side sparklines (gauges + histogram)
        "spark_rsi": _spark(r14), "spark_stoch": _spark(srsi),
        "spark_hist": _spark(hist, dec=3),
    }


def _w_fri_completed(daily: pd.Series) -> pd.Series:
    """Return the W-FRI resampled series keeping ONLY completed weekly bars.

    IHM-R1 PIT gate (mirrored from engine/index_momentum.py _resample_to_grid):
    a W-FRI bar whose label (the next Friday) is AFTER the last observed daily
    date is still in progress — drop it.  This is the same rule that index_momentum
    uses; see ruling R3b (RISK_SCORING_REVAMP_MASTERPLAN_BY_FABLE.md §2).
    """
    last_obs = daily.index.max()
    b = daily.resample("W-FRI").last().dropna()
    return b[b.index <= last_obs]


def mtf_snapshot(close: pd.Series, kind: str = "equity",
                 completed_only: bool = False) -> dict:
    """Daily / 3-day / weekly indicator states. The 3-day bar respects the
    asset's trading calendar (business days for equities, calendar days for
    24/7 crypto).

    completed_only=True: the W timeframe uses ONLY completed weekly bars
    (IHM-R1 PIT gate — drops the trailing in-progress W-FRI bucket).
    Default False preserves existing behaviour for all callers.
    Only market_state.trend opts in; every other caller is byte-identical.

    W availability gate: IDENTICAL to the default path — gated on
    len(daily) > 300, not on len(w_series).  The ONLY difference between
    the two paths is which weekly series feeds _tf_state (completed vs live
    partial).  A medium-history index (<= 300 daily bars) gets {} for W
    whether completed_only is True or False.
    """
    daily = close.dropna()
    tf3 = _preset(kind)["tf3"]
    if completed_only:
        w_state = _tf_state(_w_fri_completed(daily)) if len(daily) > 300 else {}
    else:
        w_state = _tf_state(daily.resample("W-FRI").last().dropna()) if len(daily) > 300 else {}
    out = {
        "D": _tf_state(daily),
        "3D": _tf_state(daily.resample(tf3).last().dropna()) if len(daily) > 150 else {},
        "W": w_state,
        # Monthly — for the multi-timeframe Bottom-Confidence confluence. Needs
        # ~40 month-end bars for the MACD/RSI math (_tf_state bows out under 40),
        # i.e. ~900 trading days; thin-history names simply omit it.
        "M": _tf_state(daily.resample("ME").last().dropna()) if len(daily) > 900 else {},
    }
    # The MACD cross ETA is computed in *bars of each timeframe*; a 3-day or
    # weekly bar is not one day. Surface it in trading days so the "d to cross"
    # label reads honestly across cards (1 daily bar = 1d, 1 three-day bar = 3d).
    for tf, bar_days in (("D", 1), ("3D", 3), ("W", 5), ("M", 21)):
        st = out.get(tf) or {}
        btc = st.get("macd_bars_to_cross")
        if btc:
            st["macd_days_to_cross"] = int(round(btc * bar_days))
    return out


# ---------------------------------------------------------------- cycles ----

def find_troughs(close: pd.Series, window: int = TROUGH_WINDOW,
                 min_gap: int = TROUGH_MIN_GAP) -> list[pd.Timestamp]:
    """Cycle troughs: local minima confirmed by both sides, merged when too
    close (keep the lower). The most recent <window> days can't confirm yet."""
    c = close.dropna()
    if len(c) < window * 3:
        return []
    arr = c.to_numpy()
    idx = []
    for i in range(window, len(arr) - window):
        seg = arr[i - window: i + window + 1]
        if arr[i] == seg.min():
            idx.append(i)
    # merge near-duplicates
    merged: list[int] = []
    for i in idx:
        if merged and (i - merged[-1]) < min_gap:
            if arr[i] < arr[merged[-1]]:
                merged[-1] = i
        else:
            merged.append(i)
    return [c.index[i] for i in merged]


def cycle_state(close: pd.Series, high: pd.Series | None = None,
                kind: str = "equity") -> dict:
    """Daily + investor cycle position for one instrument."""
    c = close.dropna()
    if len(c) < 260:
        return {}
    p = _preset(kind)
    dc_band, dc_early, ic_band_w = p["dc_band"], p["dc_early"], p["ic_band_w"]
    troughs = find_troughs(c)
    if not troughs:
        return {}
    last_dcl = troughs[-1]
    dc_day = int(len(c.loc[last_dcl:]) - 1)
    dcl_price = float(c.loc[last_dcl])

    # candidate for the NEXT cycle low: the lowest bar of the recent decline.
    # Only meaningful once the cycle is old enough that a new low is due.
    cand_day = cand_price = cand_swing = cand_age = cand_depth_pct = None
    if dc_day >= dc_band[0] - 10:
        recent = c.iloc[-25:]
        cand_ts = recent.idxmin()
        cand_price = float(recent.min())
        cand_age = int(len(c.loc[cand_ts:]) - 1)
        cand_day = str(cand_ts.date())
        ref = (high if high is not None else close).dropna()
        if cand_ts in ref.index and cand_age >= 1:
            bar_high = float(ref.loc[cand_ts])
            cand_swing = bool((c.loc[cand_ts:].iloc[1:] > bar_high).any())
        else:
            cand_swing = False
        # depth of the candidate pullback = decline from the local swing-high in the
        # ~3 weeks BEFORE the low to the low itself. A genuine daily-cycle low is a
        # real correction (several %); a 1-2% wobble near the highs is a continuation,
        # not a fresh cycle — this depth lets the ladder tell the two apart so a
        # stretched up-trend can't masquerade as a "fresh buy" (the TTWO/ECG case).
        pre = c.loc[:cand_ts]
        if len(pre) >= 2:
            cand_depth_bars = p.get("cand_depth_bars", 15)
            swing_hi = float(pre.iloc[-cand_depth_bars:].max())
            if swing_hi > 0:
                cand_depth_pct = round(100.0 * (swing_hi - cand_price) / swing_hi, 1)

    # translation of the LAST COMPLETED cycle
    translation = None
    if len(troughs) >= 2:
        seg = c.loc[troughs[-2]:troughs[-1]]
        if len(seg) > 10:
            crest_pos = seg.to_numpy().argmax() / (len(seg) - 1)
            translation = ("right" if crest_pos > 0.55 else
                           "left" if crest_pos < 0.45 else "middle")

    failed = bool(c.iloc[-1] < dcl_price)
    # how long the failure has been in force: bars since price first closed
    # below the low that birthed this cycle (drives the "failed N days ago" line)
    failed_age = None
    if failed:
        seg = c.loc[last_dcl:]
        below = seg[seg < dcl_price]
        if len(below):
            failed_age = int(len(seg.loc[below.index[0]:]) - 1)

    # swing low off the lowest candle of the current decline (uses highs if given)
    swing_low = None
    lowest_day = c.loc[last_dcl:].idxmin()
    ref = (high if high is not None else close)
    ref = ref.dropna()
    if lowest_day in ref.index:
        bar_high = float(ref.loc[lowest_day])
        after = c.loc[lowest_day:].iloc[1:]
        swing_low = bool((after > bar_high).any()) if len(after) else False

    ma10 = c.rolling(10).mean()
    above_ma10 = bool(c.iloc[-1] > ma10.iloc[-1])
    ma10_rising = bool(ma10.iloc[-1] > ma10.iloc[-3])

    # investor cycle from weekly bars
    w = c.resample("W-FRI").last().dropna()
    wt = find_troughs(w, window=6, min_gap=8)
    ic_week = int(len(w.loc[wt[-1]:]) - 1) if wt else None
    ic_failed = bool(wt and w.iloc[-1] < float(w.loc[wt[-1]])) if wt else False

    if dc_day < dc_early:
        dc_phase = "new"
    elif dc_day < dc_band[0] - 8:
        dc_phase = "mid"
    elif dc_day < dc_band[0]:
        dc_phase = "approaching_band"
    elif dc_day <= dc_band[1]:
        dc_phase = "in_band"
    else:
        dc_phase = "stretched"

    ic_phase = None
    if ic_week is not None:
        ic_late = round(ic_band_w[1] * 0.5)
        ic_phase = ("early" if ic_week <= 6 else "mid" if ic_week <= ic_late else
                    "late" if ic_week <= ic_band_w[1] else "overdue")

    return {
        "dc_day": dc_day, "dc_band": dc_band, "dc_early": dc_early, "dc_phase": dc_phase,
        "last_dcl": str(last_dcl.date()), "dcl_price": round(dcl_price, 2),
        "cand_dcl": cand_day, "cand_price": round(cand_price, 2) if cand_price else None,
        "cand_swing": cand_swing, "cand_age": cand_age, "cand_depth_pct": cand_depth_pct,
        "translation": translation, "failed_cycle": failed, "failed_age": failed_age,
        "swing_low": swing_low, "above_ma10": above_ma10, "ma10_rising": ma10_rising,
        "ic_week": ic_week, "ic_band": ic_band_w, "ic_phase": ic_phase, "ic_failed": ic_failed,
        "n_troughs": len(troughs),
    }


# --------------------------------------------------- pre-emptive detection ----

def _pivots(s: np.ndarray, k: int, kind: str) -> list[int]:
    """Confirmed pivot indices: extremum of k bars each side. The last k bars
    can't confirm yet (no look-ahead)."""
    out = []
    for i in range(k, len(s) - k):
        seg = s[i - k: i + k + 1]
        if (kind == "low" and s[i] == seg.min()) or (kind == "high" and s[i] == seg.max()):
            out.append(i)
    return out


def rsi_divergence(close: pd.Series, k: int = 5, min_dist: int = 13,
                   max_dist: int = 60, mag: float = 4.0) -> dict:
    """Regular RSI(14) divergence between the two most recent confirmed pivots,
    with the junk filters the research flagged as load-bearing: both legs near
    the oscillator extreme, a minimum RSI magnitude, and a min/max pivot spacing.
    Bullish = price lower-low while RSI higher-low (mirror for bearish)."""
    c = close.dropna()
    if len(c) < k * 3 + 30:
        return {}
    r = rsi(c, 14)
    arr, rv = c.to_numpy(), r.to_numpy()
    out: dict = {}
    last = len(c) - 1

    plo = _pivots(arr, k, "low")
    if len(plo) >= 2:
        p1, p2 = plo[-2], plo[-1]
        if (min_dist <= p2 - p1 <= max_dist and last - p2 <= max_dist
                and arr[p2] < arr[p1] and rv[p2] > rv[p1] + mag
                and rv[p1] < 40 and rv[p2] < 48):
            out["bull"] = True
            out["bull_bars_ago"] = int(last - p2)

    phi = _pivots(arr, k, "high")
    if len(phi) >= 2:
        p1, p2 = phi[-2], phi[-1]
        if (min_dist <= p2 - p1 <= max_dist and last - p2 <= max_dist
                and arr[p2] > arr[p1] and rv[p2] < rv[p1] - mag
                and rv[p1] > 60 and rv[p2] > 52):
            out["bear"] = True
            out["bear_bars_ago"] = int(last - p2)
    return out


def early_signals(close: pd.Series, cyc: dict, mtf: dict) -> dict:
    """Anticipatory tier — the pre-emptive layer that fires BEFORE full cycle
    confirmation. Gated by cycle context so it can't scream 'buy' in free-fall:
    bullish signals only count when a low is plausibly near (in/after the timing
    band, or short-term washed out); bearish only when extended/late. Returned as
    explicit named signals + a tier, never as a standalone buy. Calibrated
    separately (see calibrate_ladder) so its real edge is measured, not assumed."""
    d = mtf.get("D", {})
    if not d or not cyc:
        return {}
    div = rsi_divergence(close)
    late = cyc.get("dc_phase") in ("approaching_band", "in_band", "stretched")
    washed = (d.get("rsi5") or 50) < 25 or (d.get("stoch") or 50) < 12
    extended = cyc.get("dc_phase") in ("mid", "approaching_band", "in_band", "stretched") \
        and cyc.get("above_ma10")
    overbought = (d.get("rsi14") or 50) > 70 or (d.get("stoch") or 50) > 88

    bull, bear = [], []
    if (late or washed) and not cyc.get("failed_cycle"):
        if div.get("bull"):
            bull.append("RSI bullish divergence (price made a lower low, momentum didn't)")
        if d.get("macd_curl_up"):
            bull.append("MACD histogram turned up off a trough (pre-cross)")
        if d.get("stoch_cross_up"):
            bull.append("StochRSI popped out of oversold")
    if extended and overbought:
        if div.get("bear"):
            bear.append("RSI bearish divergence (price made a higher high, momentum didn't)")
        if d.get("macd_curl_dn"):
            bear.append("MACD histogram rolled over off a peak (pre-cross)")
        if d.get("stoch_cross_dn"):
            bear.append("StochRSI dropped out of overbought")

    if bull and not bear:
        tier = "anticipated" if (div.get("bull") or len(bull) >= 2) else "heads-up"
        return {"dir": "up", "tier": tier, "signals": bull, "n": len(bull)}
    if bear and not bull:
        tier = "anticipated" if (div.get("bear") or len(bear) >= 2) else "heads-up"
        return {"dir": "down", "tier": tier, "signals": bear, "n": len(bear)}
    return {}


# ----------------------------------------------------------- signal ladder ----

LADDER = ["DECLINE", "BOTTOM WATCH", "TURN SIGNALED", "FRESH BUY",
          "RALLY ON", "TOP WATCH", "ROLLING OVER", "COUNTERTREND BOUNCE",
          "CONFIRMING TURN"]

LADDER_SCORE = {"DECLINE": -80, "ROLLING OVER": -40, "TOP WATCH": -10,
                "BOTTOM WATCH": 10, "TURN SIGNALED": 45, "FRESH BUY": 80,
                "RALLY ON": 55, "COUNTERTREND BOUNCE": -25,
                # -15: softening reroute from COUNTERTREND BOUNCE (-25) — softer than its parent,
                # still caution-tier/weekly-unconfirmed, so strictly negative.
                "CONFIRMING TURN": -15}

# Liquidity conviction modifier — the US net-liquidity regime (engine.regime.
# liquidity_overlay) is the repo's strongest adversarially-validated ORTHOGONAL
# factor. Measured on the ACTUAL ladder buy setups (scripts/research_liquidity_
# ladder.py, 141-instrument walk-forward): liquidity-EXPANDING vs CONTRACTING
# lifts the forward hit-rate on FRESH BUY / TURN SIGNALED by ~+6pp (21d) / ~+8pp
# (63d) and shaves ~2.3pp off the bad-case drawdown — surviving split-half +
# ex-2020-21-QE + by asset class, equities strongest (crypto tracks it too). It is
# an ODDS edge, not a bigger expected gain, so it only NUDGES the conviction SCORE
# on buy setups — never the calibrated state key (calibration JSON keeps matching).
# Contracting is the slightly larger move (the caution side is the actionable one).
LIQ_TAILWIND = 8        # expanding-liquidity bonus on a buy setup
LIQ_HEADWIND = 12       # contracting-liquidity penalty on a buy setup
LIQ_NUDGE_STATES = ("FRESH BUY", "TURN SIGNALED")   # the measured buy states

# Plain, direction-explicit display for every internal state. The bottom and
# top "turns" are deliberately named as mirror images (BOTTOMING = buy setup,
# TOPPING = sell setup) so the symmetry is obvious. Internal keys above stay
# fixed so the calibration JSON keeps matching. action = one-word call.
STATE_DISPLAY = {
    "DECLINE":       {"label": "DOWNTREND",     "action": "AVOID",        "dir": "down",
                      "label_zh": "下跌趋势", "action_zh": "回避"},
    "BOTTOM WATCH":  {"label": "NEARING A LOW",  "action": "GET READY",    "dir": "down",
                      "label_zh": "接近低点", "action_zh": "准备"},
    "TURN SIGNALED": {"label": "BOTTOMING",      "action": "BUY SETUP",    "dir": "up",
                      "label_zh": "筑底中", "action_zh": "买入预备"},
    "FRESH BUY":     {"label": "BUY ZONE",       "action": "BUY",          "dir": "up",
                      "label_zh": "买入区", "action_zh": "买入"},
    "RALLY ON":      {"label": "UPTREND",        "action": "HOLD",         "dir": "up",
                      "label_zh": "上涨趋势", "action_zh": "持有"},
    # NEARING A HIGH is a late-cycle "take profits / don't chase" read, so its
    # alert TONE is caution (amber), NOT a green up-signal — even though price is
    # rising. `dir` here drives the alert-feed colour (af-pin card + timeline dot,
    # see site/theme.css .af-pin.dir-caution); it is a signal-tone, not a price
    # arrow, which is why COUNTERTREND BOUNCE also uses "caution". Matches the
    # existing .st-TOP_WATCH / .urg-caution -> --warn mapping (verdict bar & pills).
    "TOP WATCH":     {"label": "NEARING A HIGH", "action": "TAKE PROFITS", "dir": "caution",
                      "label_zh": "接近高点", "action_zh": "止盈"},
    "ROLLING OVER":  {"label": "TOPPING",        "action": "SELL SETUP",   "dir": "down",
                      "label_zh": "做顶中", "action_zh": "卖出预备"},
    # daily bottoming setup INSIDE a bearish higher-timeframe regime — an
    # UNCONFIRMED TURN: short-term up while the weekly/investor cycle hasn't
    # confirmed. Because weekly confirmation lags price, this same reading covers
    # BOTH bounces that fail AND the first leg of a genuine new cycle, so it's a
    # risk/size signal (high-risk, nimble-only), never a confirmed "buy". The
    # internal KEY stays "COUNTERTREND BOUNCE" so the calibration JSON keeps matching.
    "COUNTERTREND BOUNCE": {"label": "UNCONFIRMED TURN",
                            "action": "HIGH-RISK · NIMBLE ONLY", "dir": "caution",
                            "label_zh": "未确认转向", "action_zh": "高风险 · 仅限灵活操作"},
    # HK-specific: daily bottoming setup with three evidence witnesses (southbound
    # persistence, RSI reclaim from oversold, above rising MA10) — a PARTIAL turn
    # supported by on-the-ground context. Weekly hasn't confirmed; caution dir is
    # honest. NOT a confirmed buy; NOT in _ALIGN_BAD_STATES so it enters the near
    # backfill strip for screen visibility.
    "CONFIRMING TURN": {"label": "TURN IN PROGRESS",
                        "action": "WATCH — DON'T CHASE", "dir": "caution",
                        "label_zh": "转向进行中", "action_zh": "观察 — 勿追高"},
}

# Daily-cycle phase -> plain-language descriptor (answers "are we overextended?")
DC_PHASE_PLAIN = {
    "new": "fresh — a new cycle just started",
    "mid": "mid-cycle — trending",
    "approaching_band": "approaching the window where lows usually form",
    "in_band": "inside the typical low-timing window — a dip is more likely from here, though the trend can keep running",
    "stretched": "overdue — past the typical window, so a low could form any day",
}
IC_PHASE_PLAIN = {
    "early": "early — lots of room left in the bigger up-leg",
    "mid": "mid — the bigger up-leg is maturing",
    "late": "late — the bigger cycle is getting old",
    "overdue": "overdue — the bigger cycle is stretched, expect more volatility",
}

# Parallel Chinese phase descriptors (same keys; English fallback at call sites).
DC_PHASE_PLAIN_ZH = {
    "new": "全新——新周期刚刚启动",
    "mid": "周期中段——趋势运行中",
    "approaching_band": "接近低点通常形成的时间窗口",
    "in_band": "处于典型的低点时间窗口内——从此处回调概率更高，但趋势仍可能延续",
    "stretched": "逾期——已超过典型窗口，低点随时可能形成",
}
IC_PHASE_PLAIN_ZH = {
    "early": "早期——更大的上行段仍有充足空间",
    "mid": "中期——更大的上行段正在成熟",
    "late": "晚期——更大的周期已趋于老化",
    "overdue": "逾期——更大的周期已被拉伸，预计波动加剧",
}


def cycle_plain(cyc: dict) -> dict:
    """Human-readable daily vs weekly cycle context — kept distinct so users
    always know which clock they're reading."""
    lo, hi = cyc.get("dc_band", DC_BAND)
    out = {
        "daily_line": f"Daily cycle: day {cyc.get('dc_day', '?')} of a typical {lo}–{hi} trading days",
        "daily_phase": DC_PHASE_PLAIN.get(cyc.get("dc_phase"), ""),
        "daily_line_zh": f"日线周期：第 {cyc.get('dc_day', '?')} 天，典型周期为 {lo}–{hi} 个交易日",
        "daily_phase_zh": DC_PHASE_PLAIN_ZH.get(cyc.get("dc_phase"),
                                                DC_PHASE_PLAIN.get(cyc.get("dc_phase"), "")),
    }
    if cyc.get("ic_week") is not None:
        ic_lo, ic_hi = cyc.get("ic_band", IC_BAND_W)
        out["weekly_line"] = (f"Weekly (investor) cycle: week {cyc['ic_week']} of a typical "
                              f"{ic_lo}–{ic_hi} weeks")
        out["weekly_phase"] = IC_PHASE_PLAIN.get(cyc.get("ic_phase"), "")
        out["weekly_line_zh"] = (f"周线（投资者）周期：第 {cyc['ic_week']} 周，典型周期为 "
                                 f"{ic_lo}–{ic_hi} 周")
        out["weekly_phase_zh"] = IC_PHASE_PLAIN_ZH.get(cyc.get("ic_phase"),
                                                       IC_PHASE_PLAIN.get(cyc.get("ic_phase"), ""))
    tr = cyc.get("translation")
    if tr == "left":
        out["translation"] = ("The last cycle peaked in its FIRST half ('left-translated') — "
                              "weak cycles top early, so this hints the bigger trend is tiring.")
        out["translation_zh"] = ("上一周期在前半段见顶（“左移”）——弱周期见顶偏早，"
                                 "这暗示更大的趋势正在走弱。")
    elif tr == "right":
        out["translation"] = ("The last cycle peaked in its SECOND half ('right-translated') — "
                              "strong cycles top late, a healthy-uptrend sign.")
        out["translation_zh"] = ("上一周期在后半段见顶（“右移”）——强周期见顶偏晚，"
                                 "属于健康上涨趋势的信号。")
    elif tr == "middle":
        out["translation"] = "The last cycle peaked mid-way — a neutral, balanced structure."
        out["translation_zh"] = "上一周期在中段见顶——结构中性、均衡。"
    return out


def entry_timing(state: str, cyc: dict, mtf: dict) -> dict:
    """Actionable timing call + a rough days-to-entry estimate from cycle
    position and the MACD cross trajectory. Clearly an estimate, ranged."""
    d = mtf.get("D", {})
    _d3, _wk = mtf.get("3D", {}), mtf.get("W", {})
    # belt-and-suspenders cycle-top guard: a higher-timeframe momentum down-cross
    # (3-day/weekly) means even a daily TURN SIGNALED is NOT a 'now' half-buy — it
    # is a wait. The state machine already routes most tops to TOP WATCH; this keeps
    # entry_timing self-consistent for any TURN SIGNALED that still reaches here.
    htf_rollover = bool(_d3.get("macd_cross_dn") or _wk.get("macd_cross_dn"))
    lo_band, hi_band = cyc.get("dc_band", DC_BAND)
    dc = cyc.get("dc_day", 0)
    btc = d.get("macd_bars_to_cross")

    if state == "COUNTERTREND BOUNCE":
        inval = cyc.get("cand_price") or cyc.get("dcl_price")
        return {"tag": "UNCONFIRMED — HIGH RISK", "tag_zh": "未确认 — 高风险", "urgency": "caution",
                "lane_hint": "avoid",
                "text": f"Daily low forming, but the bigger trend is still bearish. Small size only; stop below {inval}.",
                "text_zh": f"日线低点正在形成，但大趋势仍偏空。只适合小仓位；止损设于 {inval} 下方。"}
    if state == "FRESH BUY":
        if cyc.get("dc_phase") == "stretched":
            # the count is stretched well past the band — an UNCONFIRMED new cycle, not a
            # fresh low to chase 'now'. Buy on confirmation (the ECG day-93 case).
            return {"tag": "BUY SOON", "tag_zh": "即将买入", "urgency": "imminent", "days_lo": 1, "days_hi": 5,
                    "text": ("A daily turn fired off a real pullback, but the cycle count is stretched "
                             "well past its usual window — treat it as an unconfirmed new cycle and buy "
                             "on confirmation (a higher low holding + the weekly turning up), not here."),
                    "text_zh": ("日线已在一次真实回调后转向，但周期天数已远超通常窗口——"
                                "应视为未确认的新周期，请在确认后买入（更高低点站稳 + 周线转向），而非此处。")}
        return {"tag": "BUY NOW", "tag_zh": "立即买入", "urgency": "now",
                "text": "Confirmed cycle low — the entry window is open now, "
                        f"with a clear exit if it closes back below {cyc.get('cand_price') or cyc.get('dcl_price')}.",
                "text_zh": "周期低点已确认——入场窗口现已开启，"
                           f"若收盘重新跌破 {cyc.get('cand_price') or cyc.get('dcl_price')} 则明确离场。"}
    if state == "TURN SIGNALED":
        # TURN SIGNALED is reached two ways. (b) Price has ALREADY reclaimed the
        # 10-day average (the daily turn is in) but the weekly hasn't confirmed →
        # a partial-conviction entry available now, NOT a pending trigger. The old
        # "buy soon once it closes back above the average" copy contradicts itself
        # here (it's already above), which is the lag the SNDK case exposed.
        # (a) Swing low printed but not yet reclaimed → the genuine "buy on the
        # reclaim" case, where that copy is correct.
        if cyc.get("above_ma10") and htf_rollover:
            return {"tag": "WAIT", "tag_zh": "等待", "urgency": "soon",
                    "text": ("The daily turn is in, but a higher timeframe (3-day/weekly) "
                             "momentum just crossed down — don't add into a rolling-over higher "
                             "timeframe. Wait for it to stabilise or for the next daily cycle low."),
                    "text_zh": ("日线已转向，但更高周期（3 日/周线）动量刚刚向下交叉——"
                                "不要在更高周期掉头时加仓。等待其企稳，或等待下一个日线周期低点。")}
        if cyc.get("above_ma10") and cyc.get("dc_phase") == "stretched":
            # a reclaim THIS far past the cycle band is an unconfirmed new cycle, not a
            # 'now' buy — the daily count is too stretched to trust the low yet, so call
            # it on-confirmation (BUY SOON) rather than half-size now (the ECG day-93 case).
            return {"tag": "BUY SOON", "tag_zh": "即将买入", "urgency": "imminent", "days_lo": 1, "days_hi": 5,
                    "text": ("The daily turn is in off a real pullback, but the cycle count is "
                             "stretched well past its usual window — so this is an UNCONFIRMED new "
                             "cycle, not a fresh low yet. Buy on confirmation (a higher low + the "
                             "weekly turning up), not here."),
                    "text_zh": ("日线已在一次真实回调后转向，但周期天数已远超通常窗口——"
                                "因此这是未确认的新周期，尚非全新低点。请在确认后买入"
                                "（更高的低点 + 周线转向），而非此处。")}
        if cyc.get("above_ma10") and not htf_rollover:
            cl = cyc.get("cand_price") or cyc.get("dcl_price")
            age = cyc.get("cand_age")
            ago = f" ~{age} day(s) ago" if age else ""
            ago_zh = f"约 {age} 天前" if age else "近期"
            ref = f" @ {cl}" if cl else ""
            return {"tag": "HALF SIZE", "tag_zh": "半仓", "urgency": "now",
                    "text": (f"The daily turn is already in — a low formed{ago}{ref} and price is "
                             "back above the 10-day average. What's missing is the weekly timeframe "
                             "confirming, so this is a partial-conviction entry available now, not a "
                             "pending trigger: take a half position here, or wait for the weekly to turn."),
                    "text_zh": (f"日线转向已经完成——低点于{ago_zh}形成{ref}，且价格已重新站上 10 日均线。"
                                "尚缺的是周线周期的确认，因此这是当下可用的部分信心入场，而非待触发信号："
                                "可在此建半仓，或等待周线转向。")}
        lo, hi = (1, max(2, round(btc))) if btc else (1, 3)
        return {"tag": "BUY SOON", "tag_zh": "即将买入", "urgency": "imminent", "days_lo": lo, "days_hi": hi,
                "text": f"Setup almost complete — likely buy trigger in ~{lo}–{hi} trading days "
                        "if it closes back above its 10-day average.",
                "text_zh": f"形态接近完成——若收盘重新站上 10 日均线，预计将在约 {lo}–{hi} 个交易日内"
                           "出现买入触发。"}
    if state == "BOTTOM WATCH":
        if cyc.get("dc_phase") in ("approaching_band", "in_band", "stretched"):
            lo = max(lo_band - dc, 0)
            hi = max(hi_band - dc, lo + 2)
            if btc:
                hi = min(hi, round(btc) + 3)
                lo = min(lo, max(round(btc) - 1, 1))
            rng = f"~{lo}–{hi}" if lo != hi else f"~{hi}"
            return {"tag": "WATCH", "tag_zh": "观察", "urgency": "soon", "days_lo": lo, "days_hi": hi,
                    "text": f"A cycle low is due in roughly {rng} trading days — watch for the "
                            "turn, don't front-run it.",
                    "text_zh": f"周期低点预计在约 {rng} 个交易日内出现——等待转向，切勿抢跑。"}
        # early/mid-cycle dip below the 10-day average — NOT the cycle low yet
        far = max(lo_band - dc, 2)
        return {"tag": "WAIT", "tag_zh": "等待", "urgency": "later", "days_lo": far, "days_hi": hi_band - dc,
                "text": f"A normal mid-cycle dip below the 10-day average — the real cycle low "
                        f"isn't due for ~{far}+ trading days. Wait for support to hold, or for "
                        "the next low to set up.",
                "text_zh": f"这是跌破 10 日均线的正常周期中段回调——真正的周期低点要到约 {far}+ "
                           "个交易日后才会到来。等待支撑站稳，或等下一个低点构筑成形。"}
    if state == "RALLY ON":
        late = dc >= lo_band - 8
        return {"tag": "HOLD", "tag_zh": "持有", "urgency": "hold",
                "text": ("Trend intact — hold. Late in the cycle, so don't add here; a pullback is due."
                         if late else "Trend intact — hold; add on dips toward the 10-day average."),
                "text_zh": ("趋势完好——持有。已处周期晚期，此处不宜加仓；回调即将到来。"
                            if late else "趋势完好——持有；可在回调至 10 日均线附近时加仓。")}
    if state == "TOP WATCH":
        return {"tag": "TAKE PROFITS", "tag_zh": "止盈", "urgency": "caution",
                "lane_hint": "take_profits",
                "text": "Stretched/late — protect gains and don't start new positions; "
                        "let the next low set up first.",
                "text_zh": "已拉伸／晚期——保护利润，不要新开仓；先等下一个低点构筑成形。"}
    if state == "ROLLING OVER":
        return {"tag": "SELL / REDUCE", "tag_zh": "卖出／减仓", "urgency": "exit",
                "text": "Momentum rolled over and the 10-day average is lost — reduce or tighten stops.",
                "text_zh": "动量已掉头向下且失守 10 日均线——减仓或收紧止损。"}
    return {"tag": "AVOID", "tag_zh": "回避", "urgency": "avoid",
            "text": "Downtrend — stand aside until a new cycle low forms and confirms.",
            "text_zh": "下跌趋势——观望，直至新的周期低点形成并确认。"}


REGIME_DISPLAY = {
    "bull": {"label": "BULLISH", "word": "with-trend",
             "label_zh": "看多", "word_zh": "顺势"},
    "neutral": {"label": "MIXED", "word": "no clear trend",
                "label_zh": "混合", "word_zh": "趋势不明"},
    "bear": {"label": "BEARISH", "word": "counter-trend",
             "label_zh": "看空", "word_zh": "逆势"},
}


def regime_state(cyc: dict, mtf: dict) -> dict:
    """The DOMINANT higher-timeframe context — bull / neutral / bear — built
    from the weekly + 3-day MACD and the investor-cycle health. This is the
    'regime' the daily-timeframe 'tactical' signal lives inside: a daily buy
    setup means very different things in a bull vs a bear regime. Kept separate
    so the UI can say 'short-term up, bigger picture down' instead of collapsing
    a genuinely two-dimensional read into one misleading label."""
    if not cyc:
        return {"regime": "neutral", "score": 0.0, "why": "", "why_zh": ""}
    w, t3 = mtf.get("W", {}), mtf.get("3D", {})
    why = []
    why_zh = []
    s = 0.0
    # weekly momentum dominates
    if w:
        if w.get("macd_cross_dn"):
            s -= 2.0; why.append("weekly momentum just crossed down")
            why_zh.append("周线动量刚刚向下交叉")
        elif w.get("macd_cross_up"):
            s += 2.0; why.append("weekly momentum just crossed up")
            why_zh.append("周线动量刚刚向上交叉")
        elif w.get("macd_pos"):
            s += 1.0; why.append("weekly momentum positive")
            why_zh.append("周线动量为正")
            if w.get("macd_approaching_dn"):
                s -= 0.5; why.append("but rolling toward a weekly cross-down")
                why_zh.append("但正趋向周线向下交叉")
        elif w.get("macd_approaching_up"):
            s += 0.5; why.append("weekly momentum curling up")
            why_zh.append("周线动量开始上翘")
        else:
            s -= 1.0; why.append("weekly momentum negative")
            why_zh.append("周线动量为负")
    # 3-day confirms / tempers
    if t3:
        if t3.get("macd_cross_dn"):
            s -= 1.0; why.append("3-day crossed down")
            why_zh.append("3 日线向下交叉")
        elif t3.get("macd_cross_up"):
            s += 1.0; why.append("3-day crossed up")
            why_zh.append("3 日线向上交叉")
        elif t3.get("macd_pos"):
            s += 0.5
        else:
            s -= 0.5
    # investor cycle health is the structural backbone
    if cyc.get("ic_failed"):
        s -= 2.0; why.append("investor cycle failed (broke its start low)")
        why_zh.append("投资者周期失败（跌破起始低点）")
    icp = cyc.get("ic_phase")
    if icp == "early":
        s += 1.0
    elif icp == "late":
        s -= 1.0
    elif icp == "overdue":
        s -= 1.5; why.append("investor cycle overdue")
        why_zh.append("投资者周期已逾期")
    if cyc.get("translation") == "left":
        s -= 1.0; why.append("last cycle left-translated (topped early)")
        why_zh.append("上一周期左移（见顶偏早）")
    elif cyc.get("translation") == "right":
        s += 0.5

    regime = "bear" if s <= -1.5 else "bull" if s >= 1.5 else "neutral"
    return {"regime": regime, "score": round(s, 1),
            "label": REGIME_DISPLAY[regime]["label"],
            "why": "; ".join(why), "why_zh": "；".join(why_zh)}


def ladder_state(cyc: dict, mtf: dict, early: dict | None = None,
                 liquidity: str | None = None,
                 macro_drag: float | None = None, macro_beta: float = 0.0,
                 vol_regime: dict | None = None, family: str | None = None,
                 confirm: dict | None = None) -> dict:
    """Combine cycle position + multi-timeframe indicators into one state,
    with a plain next-step line. The higher-timeframe regime (weekly + 3-day +
    investor cycle) gates and can RE-LABEL the daily signal: a daily buy setup
    inside a bearish regime is a counter-trend bounce, not a buy.

    `liquidity` is the live US net-liquidity regime
    ("expanding"/"contracting"/"neutral"; from engine.regime.liquidity_overlay) —
    an orthogonal macro tailwind/headwind that surfaces as context on every state
    and nudges the conviction score on buy setups only (see LIQ_TAILWIND).

    `confirm` (optional, HK path only) is a per-name evidence dict:
        {sb_persist: bool, rsi_reclaim: bool, above_rising_ma10: bool}
    When all three are True AND the tactical state resolved to FRESH BUY or TURN
    SIGNALED before the regime gate would reroute to COUNTERTREND BOUNCE AND
    hard_fail is False, the reroute resolves to "CONFIRMING TURN" instead.
    hard_fail always wins. Callers that omit confirm (default None) are
    byte-identical to before — no behavior change."""
    if not cyc or not mtf.get("D"):
        return {}
    early = early or {}
    d, w = mtf["D"], mtf.get("W", {})
    regime = regime_state(cyc, mtf)
    # full conviction only in a bull regime; otherwise the daily setup is partial
    weekly_ok = regime["regime"] == "bull"

    lo_b, hi_b = cyc.get("dc_band", DC_BAND)
    dc_early = cyc.get("dc_early", DC_EARLY)
    state, why, nxt = None, "", ""
    why_zh, nxt_zh = "", ""
    late = cyc["dc_phase"] in ("approaching_band", "in_band", "stretched")
    # a late-cycle decline hunts the NEXT low via the candidate trough
    cand_confirmed = bool(late and cyc.get("cand_swing") and cyc["above_ma10"])

    # ── Cycle-top guard (engine v2): multi-timeframe momentum-rollover signal ────
    # The macd_curl_dn / macd_cross_dn / macd_approaching_dn flags (D/3D/W) were
    # COMPUTED but never read by the buy logic, so a late name whose momentum was
    # already rolling over still printed FRESH BUY / BUY NOW (HWM day-35, RSI 62,
    # daily curl-down — 62% of live 'now' calls were late/stretched). This boolean
    # feeds the extension/late-cross gate below, which reroutes such names to TOP
    # WATCH ('don't chase'). Kept as a single chokepoint so the rich gate copy and
    # the extended_gate=True entry flag stay consistent.
    _d3, _wk = mtf.get("3D", {}), mtf.get("W", {})
    _rsi_d = d.get("rsi14") or 50
    htf_rollover = bool(_d3.get("macd_cross_dn") or _wk.get("macd_cross_dn"))
    # HTF momentum CURLING down (histogram declining, no completed cross yet).
    # Kept separate from htf_rollover so the below-MA10 de-escalation gate can
    # distinguish "curl only" from "full cross" in its diagnostic copy.
    _htf_curl_dn = bool(_d3.get("macd_curl_dn") or _wk.get("macd_curl_dn"))
    daily_rollover = bool(d.get("macd_cross_dn") or d.get("macd_curl_dn")
                          or d.get("macd_approaching_dn"))
    # Balanced veto (user-tuned): a real momentum turn-down that should stop a fresh
    # 'now' buy — a higher-TF down-cross, a confirmed daily down-cross with a firm RSI,
    # or any daily roll-over while the name is already late in its cycle.
    rollover_veto = bool(htf_rollover
                         or (d.get("macd_cross_dn") and _rsi_d >= 60)
                         or (daily_rollover and late))

    if cyc["failed_cycle"] and not cyc["above_ma10"]:
        state = "DECLINE"
        why = ("Failed cycle — price broke below the low that started this cycle, "
               "which historically means the larger trend is rolling over (~80% of cases).")
        nxt = "Stand aside until a new daily cycle low forms and confirms."
        why_zh = ("失败周期——价格跌破了启动本周期的低点，"
                  "历史上这通常意味着更大的趋势正在掉头向下（约 80% 的情形）。")
        nxt_zh = "观望，直至新的日线周期低点形成并确认。"
    elif cand_confirmed and (d.get("macd_cross_up") or d.get("macd_pos")
                             or d.get("macd_approaching_up")):
        state = "FRESH BUY" if weekly_ok else "TURN SIGNALED"
        why = (f"A new cycle low likely formed {cyc['cand_age']} day(s) ago "
               f"({cyc['cand_dcl']} @ {cyc['cand_price']}): swing low in, price back "
               "above the 10-day average"
               + (" — and the weekly timeframe agrees." if weekly_ok else
                  " — but the weekly timeframe hasn't turned yet, so conviction is partial."))
        why_zh = (f"新的周期低点可能已在 {cyc['cand_age']} 天前形成 "
                  f"（{cyc['cand_dcl']} @ {cyc['cand_price']}）：摆动低点已现，价格重新"
                  "站上 10 日均线"
                  + ("——且周线周期也一致确认。" if weekly_ok else
                     "——但周线周期尚未转向，因此信心仅为部分。"))
        nxt = (f"The cleanest setup cycle logic offers — entry with a defined exit: "
               f"invalidation = a close below {cyc['cand_price']}.") if weekly_ok else \
              "Either wait for the weekly to turn, or size half until it does."
        nxt_zh = (f"周期逻辑所能给出的最干净形态——入场并设有明确离场："
                  f"失效点 = 收盘跌破 {cyc['cand_price']}。") if weekly_ok else \
                 "可等待周线转向，或在其转向前先建半仓。"
    elif late and cyc.get("cand_swing") and not cyc["above_ma10"]:
        state = "TURN SIGNALED"
        why = (f"Buyers rejected the {cyc['cand_dcl']} low (swing low printed) but price "
               "hasn't reclaimed its 10-day average — first box ticked, not all.")
        why_zh = (f"买方拒绝了 {cyc['cand_dcl']} 的低点（摆动低点已现），但价格"
                  "尚未收复 10 日均线——第一项条件达成，并非全部。")
        nxt = "Confirmation = a close above the 10-day average with the average turning up."
        nxt_zh = "确认 = 收盘站上 10 日均线且均线开始向上。"
        if d.get("macd_approaching_up") and d.get("macd_bars_to_cross"):
            nxt += f" Daily momentum is ~{d['macd_bars_to_cross']:.0f} bars from its bullish cross."
            nxt_zh += f" 日线动量距其看多交叉约 {d['macd_bars_to_cross']:.0f} 根 K 线。"
    elif late and not cyc["above_ma10"]:
        state = "BOTTOM WATCH"
        why = (f"Day {cyc['dc_day']} of a typical {lo_b}-{hi_b}-day cycle — "
               "inside the window where lows usually form"
               + (", and short-term momentum is washed out" if (d.get("rsi5") or 50) < 30 else "")
               + ". No confirmed turn yet.")
        why_zh = (f"典型 {lo_b}-{hi_b} 天周期的第 {cyc['dc_day']} 天——"
                  "处于低点通常形成的窗口内"
                  + ("，且短期动量已被洗净" if (d.get("rsi5") or 50) < 30 else "")
                  + "。尚无确认的转向。")
        nxt = ("Wait for the turn: a move above the low candle's high, then a close back "
               "above the 10-day average.")
        nxt_zh = "等待转向：先上破低点 K 线的高点，再收盘重新站上 10 日均线。"
        if d.get("macd_approaching_up") and d.get("macd_bars_to_cross"):
            nxt += f" Daily momentum is ~{d['macd_bars_to_cross']:.0f} bars from a bullish cross."
            nxt_zh += f" 日线动量距看多交叉约 {d['macd_bars_to_cross']:.0f} 根 K 线。"
    elif d.get("macd_cross_dn") and not cyc["above_ma10"] and cyc["dc_day"] > dc_early:
        state = "ROLLING OVER"
        why = "Daily momentum just crossed down and price lost its 10-day average mid-cycle."
        why_zh = "日线动量刚刚向下交叉，且价格在周期中段失守 10 日均线。"
        nxt = ("Trim or tighten stops; next likely support is the daily-cycle timing band "
               f"(~day {lo_b}-{hi_b}, now day {cyc['dc_day']}).")
        nxt_zh = ("减仓或收紧止损；下一个可能的支撑是日线周期的时间窗口 "
                  f"（约第 {lo_b}-{hi_b} 天，现为第 {cyc['dc_day']} 天）。")
    elif cyc["swing_low"] and cyc["dc_day"] <= dc_early and cyc["above_ma10"] \
            and (d.get("macd_cross_up") or d.get("macd_pos")):
        # even a fresh daily low is only a PARTIAL buy when a higher timeframe is
        # rolling over (3-day/weekly down-cross) — demote to TURN SIGNALED, not 'now'.
        state = "FRESH BUY" if (weekly_ok and not htf_rollover) else "TURN SIGNALED"
        why = (f"New daily cycle, day {cyc['dc_day']}: swing low in, price back above the "
               "10-day average, daily momentum positive"
               + (" — and the weekly timeframe agrees." if weekly_ok else
                  " — but the weekly timeframe hasn't turned yet, so conviction is partial."))
        why_zh = (f"新的日线周期，第 {cyc['dc_day']} 天：摆动低点已现，价格重新站上 "
                  "10 日均线，日线动量为正"
                  + ("——且周线周期也一致确认。" if weekly_ok else
                     "——但周线周期尚未转向，因此信心仅为部分。"))
        nxt = ("The highest-odds window by cycle logic; invalidation = a close below "
               f"the cycle low ({cyc['dcl_price']}).") if weekly_ok else \
              "Either wait for the weekly to turn, or size half until it does."
        nxt_zh = ("按周期逻辑胜率最高的窗口；失效点 = 收盘跌破"
                  f"周期低点（{cyc['dcl_price']}）。") if weekly_ok else \
                 "可等待周线转向，或在其转向前先建半仓。"
    elif cyc["above_ma10"] and cyc["ma10_rising"] and not late:
        # "Short-term overbought" is gated on RSI(14) — the standard 0-100 gauge.
        # StochRSI SATURATES at 100 on any healthy momentum thrust (it measures
        # where RSI sits within its own recent range, so the first leg up off a
        # base pins it to 100), so used as a STANDALONE trigger it mislabels
        # strong young uptrends as "nearing a high / take profits" — e.g. the
        # MCD/JNJ June-2026 misfire read RSI 55 / 67 (mid-range, NOT overbought)
        # yet StochRSI 100. So StochRSI may only CORROBORATE an already-overbought
        # RSI here; on its own it can't flip a rising mid-cycle name off RALLY ON.
        rsi14 = d.get("rsi14") or 50
        if rsi14 > 70:
            hot = [f"RSI {rsi14:.0f}"]
            if (d.get("stoch") or 50) > 90:
                hot.append(f"StochRSI {d.get('stoch'):.0f}")
            state = "TOP WATCH"
            why = (f"Mid-cycle (day {cyc['dc_day']}) and short-term overbought "
                   f"({', '.join(hot)}).")
            why_zh = (f"周期中段（第 {cyc['dc_day']} 天）且短期超买 "
                      f"（{', '.join(hot)}）。")
            nxt = ("Not a short signal — just don't add here; pullbacks to the 10-day "
                   "average are normal.")
            nxt_zh = "并非做空信号——只是此处不宜加仓；回调至 10 日均线属于正常现象。"
        else:
            state = "RALLY ON"
            why = (f"Day {cyc['dc_day']} of the cycle, trend intact above a rising 10-day average"
                   + (", weekly aligned." if weekly_ok else ", weekly still mixed."))
            why_zh = (f"周期第 {cyc['dc_day']} 天，趋势完好并位于向上的 10 日均线之上"
                      + ("，周线一致。" if weekly_ok else "，周线仍为混合。"))
            nxt = ("Hold; first warning would be losing the 10-day average, bigger warning is a "
                   "daily momentum cross down.")
            nxt_zh = "持有；首个预警是失守 10 日均线，更大的预警是日线动量向下交叉。"
    elif late and cyc["above_ma10"]:
        state = "TOP WATCH"
        why = (f"Late in the daily cycle (day {cyc['dc_day']} of ~{lo_b}-{hi_b}) — "
               "odds favor a dip into the next cycle low from here even with the trend intact.")
        why_zh = (f"处于日线周期晚期（约 {lo_b}-{hi_b} 天中的第 {cyc['dc_day']} 天）——"
                  "即便趋势完好，从此处概率上仍倾向于回落至下一个周期低点。")
        nxt = "Let the next daily cycle low form before adding; watch for the swing-low setup."
        nxt_zh = "在加仓前先让下一个日线周期低点形成；留意摆动低点形态。"
    else:
        state = "RALLY ON" if cyc["above_ma10"] else "BOTTOM WATCH"
        why = "Mixed structure."
        why_zh = "结构混合。"
        nxt = "Watch the 10-day average and cycle-day count."
        nxt_zh = "关注 10 日均线与周期天数。"

    # ── Regime gate ─────────────────────────────────────────────────────────
    # A bullish daily setup INSIDE a bearish higher-timeframe regime is a
    # counter-trend bounce, not a buy. A failed daily cycle AND a failed
    # investor cycle hard-caps it regardless of the regime score — a failed
    # cycle can produce a bounce, never an investment buy.
    #
    # HK evidence bypass: when the caller supplies a `confirm` dict with three
    # per-name witnesses (sb_persist, rsi_reclaim, above_rising_ma10) AND all
    # three are True AND hard_fail is False, the reroute resolves to the softer
    # "CONFIRMING TURN" instead of "COUNTERTREND BOUNCE". hard_fail always wins.
    bullish_tactical = state in ("FRESH BUY", "TURN SIGNALED")
    hard_fail = bool(cyc.get("failed_cycle") and cyc.get("ic_failed"))
    _confirm = confirm or {}
    evidence_ok = bool(
        not hard_fail
        and bullish_tactical
        and _confirm.get("sb_persist")
        and _confirm.get("rsi_reclaim")
        and _confirm.get("above_rising_ma10")
    )
    if bullish_tactical and (regime["regime"] == "bear" or hard_fail):
        inval = cyc.get("cand_price") or cyc.get("dcl_price")
        if evidence_ok:
            # Three witnesses present + no hard fail → softer CONFIRMING TURN
            state = "CONFIRMING TURN"
            why = ("A daily bottoming setup is forming and three on-the-ground witnesses are "
                   "present: southbound flow has been persistently positive (mainland buyers "
                   "are adding), RSI(14) washed out below 32 and has recovered into the "
                   "40–60 range, and price is back above a rising 10-day average. The weekly "
                   "timeframe has not yet confirmed ("
                   + (regime["why"] or "weekly / investor timeframe still pointing down")
                   + "). Southbound persistence is context — who the marginal buyer is — "
                     "not a confirmer. The weekly hasn't turned; watch, don't chase.")
            why_zh = ("日线筑底形态正在形成，且三项实地证据指标同时具备：南向资金持续净买入（内地"
                      "买家持续加仓）、RSI(14) 已从超卖区（低于 32）回升至 40–60 区间、价格重新"
                      "站上向上的 10 日均线。周线周期尚未确认（"
                      + (regime["why_zh"] or regime["why"] or "周线 / 投资者周期仍指向下方")
                      + "）。南向资金流向是背景信息——显示边际买家是谁——而非确认信号；"
                        "周线尚未转向，观察勿追高。")
            nxt = ("Watch, don't chase. The weekly hasn't turned — size small and wait for "
                   f"the weekly to confirm before adding. Invalidation = a close below {inval}.")
            nxt_zh = ("观察，勿追高。周线尚未转向——保持小仓位，等待周线确认后再加仓。"
                      f"失效点 = 收盘跌破 {inval}。")
        else:
            state = "COUNTERTREND BOUNCE"
            why = ("A daily bottoming setup is forming (swing low in, momentum turned up) — but the "
                   "higher timeframes haven't confirmed it: the bigger picture is still bearish ("
                   + (regime["why"] or "weekly / investor timeframe pointing down")
                   + "). This is an UNCONFIRMED TURN, not a confirmed buy. Weekly confirmation lags "
                     "price, so this exact reading covers BOTH bounces that fail AND the first leg of "
                     "a genuine new cycle — you can't tell which in real time, so treat it as a "
                     "risk/size signal, not a direction call. Measured: weekly-unconfirmed bottoming "
                     "setups held the low ~49% of the time vs ~68% once the weekly turns up."
                   + (" The daily cycle has also failed (broke its own start low), which tilts the "
                      "odds toward failure here." if cyc.get("failed_cycle") else ""))
            why_zh = ("正在形成日线筑底形态（摆动低点已现、动量转向上行）——但更高周期尚未确认："
                      "大局仍偏空（"
                      + (regime["why_zh"] or regime["why"] or "周线 / 投资者周期向下")
                      + "）。这是「未确认转向」，并非已确认的买入。周线确认滞后于价格，因此同样的"
                        "读数既涵盖最终失败的反弹，也涵盖真正新周期的第一段——实时无法判定属于哪一种，"
                        "故应将其视为风险/仓位信号，而非方向判断。实测：周线未确认的筑底形态约 49% 守住"
                        "低点，周线转向后升至约 68%。"
                      + ("日线周期同样已经失败（跌破其自身起始低点），此处概率更偏向失败。"
                         if cyc.get("failed_cycle") else ""))
            nxt = ("Nimble traders only — small size, defined stop below "
                   f"{inval}. Not an investment buy yet. What would upgrade it: weekly momentum "
                   "turning up, a reclaim of the investor-cycle low, or the first daily cycle "
                   "right-translating — add on confirmation, not ahead of it.")
            nxt_zh = ("仅限灵活交易者——小仓位、止损设于 "
                      f"{inval} 下方。暂非投资性买入。何种情形会升级：周线动量转为向上、"
                      "收复投资者周期低点、或首个日线周期呈右移结构——在确认之后加仓，而非提前。")

    # ── Extension / late-cross gate ──────────────────────────────────────────
    # A daily buy setup is only a BOTTOMING entry while price is still near the
    # low. A MACD signal-line cross is a LAGGING confirmation: after a vertical
    # run it only fires once price is already extended and overbought, so the
    # "fresh buy" is really a chase — the actual low was days ago. This mirrors
    # the RALLY ON→TOP WATCH RSI>70 gate below; the buy branches sit ABOVE it in
    # the elif chain and so skip it, which let an overbought name that prints a
    # swing low + momentum cross be mislabeled BUY instead of "don't chase, wait
    # for the pullback" (the SNDK case: day-68 stretched, +48% off the low, daily
    # RSI 71 / 3-day 82 / weekly 81, yet read TURN SIGNALED on the lagging cross).
    # Routes to the already-calibrated TOP WATCH, not a new state.
    extended_gate = False
    t3 = mtf.get("3D", {})
    rsi_d = d.get("rsi14") or 50
    rsi_3 = t3.get("rsi14") or 50
    rsi_w = w.get("rsi14") or 50
    overbought_late = rsi_d > 70 or (rsi_3 > 70 and rsi_w > 70)
    if state in ("FRESH BUY", "TURN SIGNALED", "CONFIRMING TURN") and cyc.get("above_ma10") \
            and (overbought_late or rollover_veto):
        extended_gate = True
        state = "TOP WATCH"
        cl = cyc.get("cand_price") or cyc.get("dcl_price")
        age = cyc.get("cand_age")
        ago = f" ~{age} day(s) ago" if age else ""
        ago_zh = f"约 {age} 天前" if age else "近期"
        ref = f" @ {cl}" if cl else ""
        # adapt the caveat to WHY the chase fired: overbought, or momentum rolling over
        # (the HWM case: late in the cycle with the daily MACD already curling down).
        if overbought_late:
            hot = f"daily RSI {rsi_d:.0f}"
            hot_zh = f"日线 RSI {rsi_d:.0f}"
            if rsi_3 > 70 and rsi_w > 70:
                hot += f", 3-day {rsi_3:.0f} & weekly {rsi_w:.0f}"
                hot_zh += f"、3 日 {rsi_3:.0f} 与周线 {rsi_w:.0f}"
            caveat, caveat_zh = f"overbought ({hot})", f"已超买（{hot_zh}）"
        else:
            tf_word = ("the 3-day/weekly momentum has crossed down" if htf_rollover
                       else "the daily momentum is already rolling over")
            tf_word_zh = ("3 日/周线动量已向下交叉" if htf_rollover
                          else "日线动量已开始掉头向下")
            caveat = f"momentum is fading — {tf_word}"
            caveat_zh = f"动量正在衰竭——{tf_word_zh}"
        why = (f"A daily bottoming setup did fire (swing low in, momentum turned up), but it's "
               f"LATE — price is already extended above the cycle low (formed{ago}{ref}) and "
               f"{caveat}. A momentum cross is a LAGGING confirmation: after a vertical "
               "run it only triggers once the move is mature, so the bottoming entry has already "
               "passed. This is a chase, not a fresh buy.")
        why_zh = (f"日线筑底形态确实已经触发（摆动低点出现、动量转向上行），但为时已晚——"
                  f"价格已显著高于周期低点（{ago_zh}形成{ref}）且{caveat_zh}。"
                  "动量交叉属于滞后确认：在垂直拉升之后，只有当走势已经成熟时才会触发，"
                  "因此筑底入场早已错过。这是追高，而非新的买入。")
        nxt = ("Don't initiate here. Wait for a pullback toward the 10-day average — or the next "
               "daily-cycle low to set up — for a lower-risk entry; hold if you're already long.")
        nxt_zh = ("此处不宜建仓。等待回调至 10 日均线附近——或下一个日线周期低点构筑成形——"
                  "以获得风险更低的入场；若已持有则可继续持有。")

    # ── Fresh weekly (investor-cycle) cross-up VETO on TOP WATCH ─────────────────
    # TOP WATCH ("nearing a high / take profits") is a DAILY-cycle judgment — daily
    # overbought (RSI>70), or late in the daily cycle. But the WEEKLY MACD is the
    # INVESTOR cycle: when it has JUST crossed up AND the weekly itself isn't yet
    # overbought, that is the START of a new multi-month up-leg, so a daily-overbought
    # print is the launch thrust, NOT a top. Taking profits into a fresh weekly cross is
    # the documented failure mode (XLV 2026-06: daily RSI 72 / fresh daily cross, but the
    # WEEKLY just crossed up at weekly RSI 63 — the rotation leader read TAKE PROFITS).
    # Reroute to RALLY ON (hold/ride the new leg) — never sell strength early in the
    # bigger cycle. Mirrors engine.sector_cycles._classify_phase, which already weights a
    # fresh weekly cross. Narrow by design (a weekly signal-line cross is infrequent), so
    # it only catches names genuinely turning up on the investor clock while daily-extended.
    weekly_fresh_up = bool(w.get("macd_cross_up"))
    weekly_not_hot = (w.get("rsi14") or 50) < 70
    weekly_cross_rescue = False
    if state == "TOP WATCH" and weekly_fresh_up and weekly_not_hot \
            and cyc.get("above_ma10") and early.get("dir") != "down":
        state = "RALLY ON"
        extended_gate = False
        weekly_cross_rescue = True   # a fresh weekly cross makes an overbought daily buy a new-leg
                                # HOLD, not a chase — clear the gate so entry reads HOLD not "DON'T CHASE"
        why = ("The weekly (investor-cycle) momentum just crossed UP while price holds its "
               "10-day average — the start of a new multi-month up-leg. A daily-overbought print "
               "here is the launch thrust, not a top, so this is a HOLD / ride, not a take-profit. "
               "The daily can still dip to its 10-day average (normal) — but the bigger investor "
               "cycle is early, with room left.")
        why_zh = ("周线（投资者周期）动量刚刚向上交叉，且价格守住 10 日均线——这是新的多月上行段的起点。"
                  "此处日线超买只是启动推力、并非见顶，因此应持有 / 顺势，而非止盈。"
                  "日线仍可能回踩 10 日均线（属正常）——但更大的投资者周期尚处早期，仍有空间。")
        nxt = ("Hold / ride the fresh weekly up-leg; add on pullbacks toward the 10-day average "
               "rather than chasing the thrust. First warning would be the weekly momentum "
               "rolling back over.")
        nxt_zh = ("持有 / 顺应新的周线上行段；在回踩 10 日均线时加仓，而非追高推力。"
                  "首个预警将是周线动量重新掉头向下。")

    score = LADDER_SCORE[state]
    if cyc.get("translation") == "left":
        score -= 10
        why += " Last cycle was left-translated (topped early) — a bearish structural tell."
        why_zh += " 上一周期为左移结构（见顶偏早）——属于看空的结构性信号。"
    if state in ("FRESH BUY", "RALLY ON") and cyc.get("translation") == "right":
        score += 5

    # pre-emptive (anticipatory) layer: enriches messaging in the watch states
    # without changing the calibrated state. A bullish early read in BOTTOM WATCH
    # nudges the score and re-frames the action toward "watch closely".
    early_note = ""
    early_note_zh = ""
    if early.get("dir") == "up" and state in ("BOTTOM WATCH", "TURN SIGNALED",
                                              "DECLINE", "COUNTERTREND BOUNCE",
                                              "CONFIRMING TURN"):
        score += 12 if early.get("tier") == "anticipated" else 6
        early_note = ("⚡ Early reversal building (" + early["tier"] + "): "
                      + "; ".join(early["signals"]) + ". These anticipate a low BEFORE "
                      "full confirmation — earlier entry, but a higher false-alarm rate, so "
                      "treat as a heads-up to watch closely, not a trigger yet.")
        early_note_zh = ("⚡ 反转正在提前酝酿（" + early["tier"] + "）："
                         + "; ".join(early["signals"]) + "。这些信号会在完全确认之前"
                         "预判低点——入场更早，但误报率更高，因此应视为密切关注的"
                         "提示，而非触发信号。")
    elif early.get("dir") == "down" and state in ("TOP WATCH", "RALLY ON"):
        score -= 12 if early.get("tier") == "anticipated" else 6
        early_note = ("⚡ Early topping signs (" + early["tier"] + "): "
                      + "; ".join(early["signals"]) + ". These anticipate a high BEFORE "
                      "confirmation — a heads-up to protect gains, not a sell trigger yet.")
        early_note_zh = ("⚡ 提前出现的做顶迹象（" + early["tier"] + "）："
                         + "; ".join(early["signals"]) + "。这些信号会在确认之前预判"
                         "高点——属于保护利润的提示，而非卖出触发信号。")

    # ── Liquidity regime (macro conviction modifier) ─────────────────────────
    # Orthogonal to trend/vol and the repo's strongest validated factor. An ODDS
    # edge: surfaced as context on every state, it only nudges the conviction
    # SCORE on buy setups (expanding = tailwind, contracting = caution). US net
    # liquidity drives crypto too (BTC tracks it). See LIQ_TAILWIND for the record.
    liq_regime = liquidity if liquidity in ("expanding", "contracting", "neutral") else None
    liq_effect = None
    liq_line = liq_line_zh = ""
    if liq_regime:
        buy_setup = state in LIQ_NUDGE_STATES
        if liq_regime == "expanding":
            if buy_setup:
                score += LIQ_TAILWIND
            liq_effect = "tailwind" if buy_setup else "supportive"
            liq_line = ("Macro tailwind: US net liquidity is expanding — buy setups have "
                        "historically had better odds (~+6pp hit at 21d) and shallower dips "
                        "in this regime. An odds edge, not a bigger expected gain.")
            liq_line_zh = ("宏观顺风：美国净流动性正在扩张——在该环境下买入形态历史上"
                           "胜率更高（21 日约 +6 个百分点）、回撤更浅。这是概率优势，"
                           "并非更大的预期收益。")
        elif liq_regime == "contracting":
            if buy_setup:
                score -= LIQ_HEADWIND
            liq_effect = "headwind" if buy_setup else "cautionary"
            liq_line = ("Macro headwind: US net liquidity is contracting — buy setups have "
                        "historically had worse odds and deeper drawdowns here, so demand "
                        "extra confirmation and smaller size. An odds edge, not a forecast.")
            liq_line_zh = ("宏观逆风：美国净流动性正在收缩——在此环境下买入形态历史上"
                           "胜率更低、回撤更深，因此应要求更多确认并降低仓位。"
                           "这是概率优势，并非预测。")
        else:  # neutral
            liq_effect = "neutral"
            liq_line = "US net liquidity is neutral right now — no macro tilt either way on the odds."
            liq_line_zh = "美国净流动性目前中性——对概率没有方向性影响。"

    # ── Macro-risk regime (risk-OFF conviction modifier) ─────────────────────
    # Aggregate macro risk (engine.conditions MRS, 0..1) scaled by this name's
    # SECTOR sensitivity (macro_beta). SUBTRACT-ONLY and buy-setup-only — it
    # mirrors the liquidity-nudge envelope: a high macro-risk reading shaves
    # conviction on FRESH BUY / TURN SIGNALED for macro-sensitive (cyclical) names;
    # defensives (beta<=0) are untouched. Net liquidity is also one of MRS's legs,
    # so on a contracting day a cyclical here sees the uniform LIQ_HEADWIND above
    # PLUS a small (~1pt) sector-scaled macro share — that overlap is intentional
    # (it adds sector differentiation to the liquidity signal), bounded, and the
    # validated cyclical/defensive split depends on it. Drawdown/sizing caution, not
    # alpha. See research/MACRO_RISK_INTEGRATION.md.
    macro_effect = None
    macro_pen = 0
    macro_line = macro_line_zh = ""
    _mo = config.load()["engine"].get("macro_overlay") or {}
    macro_on = bool(macro_drag is not None and _mo.get("enabled", True))
    if macro_on and state in LIQ_NUDGE_STATES and macro_beta > 0:
        _mhead = float(_mo.get("macro_headwind", 7))
        macro_pen = int(round(_mhead * float(macro_drag) * float(macro_beta)))
        if macro_pen > 0:
            score -= macro_pen
            macro_effect = "headwind"
            macro_line = ("Macro-risk headwind: aggregate macro risk is elevated and this is "
                          "a macro-sensitive (cyclical) name — buy setups here have "
                          "historically taken deeper drawdowns, so demand extra confirmation "
                          "and smaller size. A risk/sizing caution, not a forecast.")
            macro_line_zh = ("宏观风险逆风：总体宏观风险偏高，且该标的对宏观较敏感（周期性）——"
                             "在此环境下买入形态历史上回撤更深，因此应要求更多确认并降低仓位。"
                             "这是风险/仓位提示，并非预测。")

    # ── Index vol-regime (risk-OFF sizing caution) ───────────────────────────
    # When the validated INDEX vol-regime (engine.vol_regime -> site/vol/regime.json) is in a
    # risk-off KILL-SWITCH state (warning / backwardation-stress: VIX/VIX3M backwardation +
    # bond-vol stress + a thin vol-risk-premium), shave conviction on FRESH BUY / TURN SIGNALED
    # only. UNIFORM (index-level, like LIQ_HEADWIND — every name shares the same market vol
    # regime), SUBTRACT-ONLY, buy-setup-only. The continuous SCORED composite deepens the cut
    # only when its gate is open (vol_regime['scored_active']); otherwise the published STATE
    # label alone drives a bounded caution. Drawdown/sizing caution, NOT a forecast.
    vr_effect = None
    vr_pen = 0
    vr_line = vr_line_zh = ""
    _vr = vol_regime if isinstance(vol_regime, dict) else None
    _vro = (config.load()["engine"].get("vol_regime_overlay") or {})
    # VALIDATE-BEFORE-WEIGHT (audit #30): the regime-state caution failed its additive-value gate
    # over the mechanical vol-target (basket_overlay_gate.json regime_marginal_over_voltarget=false),
    # so it may NOT bind a real ladder SCORE. The headwind penalty applies ONLY when the caution
    # leg is gated-on; otherwise the caution stays as a display-only line (no score change).
    try:
        from engine import vol_regime as _vrm
        _caution_scored = _vrm.regime_caution_scored()
    except Exception:  # noqa: BLE001 — never break the ladder build
        _caution_scored = False
    vr_on = bool(_vr and _vro.get("enabled", True))
    vr_state = (_vr or {}).get("regime")
    if (vr_on and _caution_scored and state in LIQ_NUDGE_STATES
            and vr_state in ("warning", "backwardation-stress")):
        _rhead = float(_vro.get("ladder_headwind", 7))
        sev = 1.0 if vr_state == "backwardation-stress" else 0.6     # warning is the milder state
        # gate-open scored composite (risk-off) deepens the caution, capped so it never exceeds 1.5x
        sc = (_vr or {}).get("scored_score")
        if (_vr or {}).get("scored_active") and sc is not None and float(sc) < 0:
            sev = min(sev * (1.0 + abs(float(sc))), 1.5)
        vr_pen = int(round(_rhead * sev))
        if vr_pen > 0:
            score -= vr_pen
            vr_effect = "headwind"
            _sn = "backwardation-stress" if vr_state == "backwardation-stress" else "warning"
            vr_line = ("Vol-regime headwind: the index vol-regime is risk-off "
                       f"({_sn} — term-structure backwardation / bond-vol stress), so market-wide "
                       "drawdown risk is elevated. Buy setups here have historically taken deeper "
                       "dips — demand extra confirmation and smaller size. A risk/sizing caution, "
                       "not a forecast.")
            vr_line_zh = ("波动率状态逆风：指数波动率处于风险偏离状态"
                          f"（{_sn}——期限结构倒挂/债券波动率承压），全市场回撤风险升高。"
                          "此环境下买入形态历史上回撤更深——应要求更多确认并降低仓位。"
                          "这是风险/仓位提示，并非预测。")
    elif (vr_on and not _caution_scored and state in LIQ_NUDGE_STATES
            and vr_state in ("warning", "backwardation-stress")):
        # DISPLAY-ONLY caution: risk-off regime is shown as context but does NOT dock the score
        # (its additive-value gate over vol-target is closed). No vr_pen, no vr_effect.
        _sn = "backwardation-stress" if vr_state == "backwardation-stress" else "warning"
        vr_line = ("Vol-regime context (display-only): the index vol-regime is risk-off "
                   f"({_sn}). This caution failed its additive-value test over mechanical "
                   "vol-targeting, so it does NOT dock this setup's score — shown as awareness "
                   "only. Size via the mechanical vol-target, not this label.")
        vr_line_zh = ("波动率状态（仅供参考）：指数波动率处于风险偏离状态"
                      f"（{_sn}）。此提示未通过相对机械式波动率目标的增量价值检验，"
                      "因此不扣减本形态评分——仅作提示。请以机械式波动率目标控制仓位。")

    disp = STATE_DISPLAY[state]
    plain = cycle_plain(cyc)
    entry = entry_timing(state, cyc, mtf)
    if extended_gate:
        # routed off a buy setup by the extension gate — the headline tag should
        # read "don't chase", not the generic TOP WATCH "take profits"
        entry = {"tag": "DON'T CHASE", "tag_zh": "勿追高", "urgency": "caution",
                 "lane_hint": "on_the_run",
                 "text": ("You missed the bottoming entry — the low already formed and price is now "
                          f"extended ({caveat}). Don't chase; wait for a pullback to the "
                          "10-day average or the next cycle low. Hold if already long."),
                 "text_zh": (f"已错过筑底入场——低点已经形成，目前价格已拉伸（{caveat_zh}）。"
                             "不要追高；等待回调至 10 日均线或下一个周期低点。若已持有则继续持有。")}

    # ── Below-MA10 TURN SIGNALED de-escalation gate ──────────────────────────
    # The branch at ~line 929 fires when price is LATE in the cycle, a swing low
    # is printed, but price has NOT reclaimed the 10-day average (above_ma10=False).
    # This produces state=TURN SIGNALED + entry.urgency="imminent" (BUY SOON).
    # The upstream extension gate (line 1083) is gated on `above_ma10` so it skips
    # this branch entirely, even when rollover_veto is True (daily MACD near/at a
    # bearish cross, late) or when oscillators flag the move as overextended.
    # De-escalation ONLY (house law): when the buy-side state landed here AND
    # rollover_veto OR _htf_curl_dn OR oscillator overextension is True, downgrade
    # urgency to "caution" (bucketer → take_profits / hold).
    # State label is kept as-is (TURN SIGNALED / BOTTOMING). Never escalates.
    #
    # 2026-07-14: China semis ETF 512760.SS, -12% rolloff (below 10dma AND 200dma,
    # lower highs), 3D MACD curling down (macd_curl_dn=True) with no completed
    # 3D/W down-cross yet — rollover_veto stayed False, gate did not fire, and the
    # below-MA10 BUY SOON (urgency=imminent) printed. Below-MA10 late-cycle BUY SOON
    # during fading higher-TF momentum must read as UNCONFIRMED-WAIT regardless of
    # whether the cross has completed.
    if (state in ("FRESH BUY", "TURN SIGNALED")
            and not cyc.get("above_ma10")
            and (rollover_veto or _htf_curl_dn or _overextended(mtf))
            and entry.get("urgency") in ("now", "imminent", "soon")):
        if _overextended(mtf):
            # Oscillators genuinely overbought — price has run too far, not a safe entry.
            entry = {"tag": "BOTTOMING · EXTENDED — WAIT",
                     "tag_zh": "筑底 · 已过热 — 等待",
                     "urgency": "caution",
                     "lane_hint": "buy_soon",
                     "text": ("The bottoming setup is not yet confirmed (price still below the 10-day "
                              "average) and oscillators are already extended/overbought — not a safe "
                              "entry. Wait for price to reclaim the 10-day average with momentum "
                              "stabilising before sizing in."),
                     "text_zh": ("筑底形态尚未确认（价格仍位于 10 日均线下方），且摆动指标已过热——"
                                 "此处入场风险较高。等待价格收复 10 日均线且动量趋于稳定后再考虑建仓。")}
        else:
            # Fired via rollover_veto or _htf_curl_dn — higher-TF momentum is rolling
            # over (completed cross) or curling down (no cross yet), but oscillators are
            # not overbought. Three-case discriminant for diagnostic copy:
            #   1. htf_rollover  → completed 3-day/weekly down-cross
            #   2. _htf_curl_dn  → histogram turning, cross not yet complete
            #   3. else          → daily-only rollover
            tf_word = ("the 3-day/weekly momentum has crossed down" if htf_rollover
                       else "the 3-day/weekly momentum is rolling over" if _htf_curl_dn
                       else "the daily momentum is already rolling over")
            tf_word_zh = ("3 日/周线动量已向下交叉" if htf_rollover
                          else "3 日/周线动量已开始掉头向下" if _htf_curl_dn
                          else "日线动量已开始掉头向下")
            entry = {"tag": "BOTTOMING · UNCONFIRMED — WAIT",
                     "tag_zh": "筑底 · 未确认 — 等待",
                     "urgency": "caution",
                     "lane_hint": "buy_soon",
                     "text": ("The bottoming setup is not yet confirmed (price still below the 10-day "
                              f"average) and {tf_word} — momentum is fading before the setup has "
                              "completed. Wait for price to reclaim the 10-day average with momentum "
                              "stabilising before sizing in."),
                     "text_zh": (f"筑底形态尚未确认（价格仍位于 10 日均线下方），且{tf_word_zh}——"
                                 "动量在形态完成前已开始衰竭。等待价格收复 10 日均线且动量趋于稳定后再考虑建仓。")}

    # ── Two-axis summary: TACTICAL (this daily state) vs REGIME (bigger picture),
    # plus how long the current move has been running ("ongoing" context).
    reg = regime["regime"]
    reg_word = REGIME_DISPLAY[reg]["word"]
    reg_word_zh = REGIME_DISPLAY[reg].get("word_zh", reg_word)
    reg_label_zh = REGIME_DISPLAY[reg].get("label_zh", REGIME_DISPLAY[reg]["label"])
    bits = []
    bits_zh = []
    if cyc.get("ic_week") is not None:
        bits.append(f"investor cycle week {cyc['ic_week']}")
        bits_zh.append(f"投资者周期第 {cyc['ic_week']} 周")
    if cyc.get("ic_failed"):
        bits.append("failed")
        bits_zh.append("已失败")
    if cyc.get("failed_age"):
        bits.append(f"daily cycle broke its start low {cyc['failed_age']}d ago")
        bits_zh.append(f"日线周期于 {cyc['failed_age']} 天前跌破其起始低点")
    elif cyc.get("dc_day") is not None:
        bits.append(f"daily cycle day {cyc['dc_day']}")
        bits_zh.append(f"日线周期第 {cyc['dc_day']} 天")
    dur = " · ".join(bits)
    dur_zh = " · ".join(bits_zh)
    regime_line = (f"Bigger picture: {REGIME_DISPLAY[reg]['label']}"
                   + (f" — {regime['why']}" if regime.get("why") else "")
                   + (f" ({dur})." if dur else "."))
    regime_line_zh = (f"大局：{reg_label_zh}"
                      + (f" — {regime['why_zh']}" if regime.get("why_zh") else "")
                      + (f"（{dur_zh}）。" if dur_zh else "。"))
    tactical_label = disp["label"]
    tactical_label_zh = disp.get("label_zh", tactical_label)
    summary_line = (f"Short-term (daily): {tactical_label.lower()}. "
                    f"Bigger picture ({reg_word}): {REGIME_DISPLAY[reg]['label'].lower()}.")
    summary_line_zh = (f"短期（日线）：{tactical_label_zh}。"
                       f"大局（{reg_word_zh}）：{reg_label_zh}。")

    # Plain two-timeframe SYNTHESIS sentence — the glance-level reconciliation that resolves the
    # "daily looks hot, weekly just turned" tension (surfaced under the verdict bar). Emitted on
    # the weekly-cross rescue so the daily overbought/late chips can't read as a contradiction.
    synthesis_line = synthesis_line_zh = ""
    if weekly_cross_rescue:
        _rsi = d.get("rsi14")
        _band_hi = (cyc.get("dc_band") or [None, None])[1]
        _day = (f"day {cyc.get('dc_day')}" + (f"/{_band_hi}" if _band_hi else "")) \
            if cyc.get("dc_day") is not None else ""
        _daily = "Daily is hot (" + (f"RSI {_rsi:.0f}" if _rsi is not None else "extended") \
            + (f", {_day}" if _day else "") + " — a dip is normal soon)"
        synthesis_line = (_daily + ", but the weekly investor cycle just turned up — so this is "
                          "HOLD / ride a new up-leg, not take-profits.")
        synthesis_line_zh = ("日线偏热（" + (f"RSI {_rsi:.0f}" if _rsi is not None else "已拉伸")
                             + (f"，周期第 {cyc.get('dc_day')} 天" if cyc.get("dc_day") is not None else "")
                             + "——短期回调属正常），但周线投资者周期刚刚向上转向——"
                               "因此应持有 / 顺势新上行段，而非止盈。")

    # concise bullet points (the headline facts); full prose lives in `why`
    points = []
    points_zh = []
    points.append(f"Bigger picture is {REGIME_DISPLAY[reg]['label'].lower()} "
                  f"({reg_word} for a daily long)")
    points_zh.append(f"大局为{reg_label_zh}（对日线多头而言属{reg_word_zh}）")
    if liq_effect:
        _liq_word = {"expanding": "expanding", "contracting": "contracting",
                     "neutral": "neutral"}[liq_regime]
        _liq_word_zh = {"expanding": "扩张", "contracting": "收缩", "neutral": "中性"}[liq_regime]
        _eff = {"tailwind": "a tailwind", "headwind": "a headwind",
                "supportive": "supportive backdrop", "cautionary": "caution",
                "neutral": "no macro tilt"}[liq_effect]
        _eff_zh = {"tailwind": "顺风", "headwind": "逆风", "supportive": "偏支持",
                   "cautionary": "需谨慎", "neutral": "无方向性影响"}[liq_effect]
        points.append(f"Macro: US net liquidity {_liq_word} — {_eff} on the odds")
        points_zh.append(f"宏观：美国净流动性{_liq_word_zh}——对概率属{_eff_zh}")
    if macro_effect == "headwind":
        points.append("Macro-risk: aggregate macro risk elevated for a macro-sensitive name "
                      "— caution on the odds")
        points_zh.append("宏观风险：总体宏观风险偏高且标的对宏观敏感——对概率需谨慎")
    if cyc.get("failed_cycle"):
        age = f" ({cyc['failed_age']}d ago)" if cyc.get("failed_age") else ""
        age_zh = f"（{cyc['failed_age']} 天前）" if cyc.get("failed_age") else ""
        points.append(f"⚠ Failed cycle — price broke below the low that began this cycle{age}")
        points_zh.append(f"⚠ 失败周期——价格跌破了启动本周期的低点{age_zh}")
    if cyc.get("swing_low") or cyc.get("cand_swing"):
        points.append("Swing low printed (buyers rejected the low)")
        points_zh.append("摆动低点已现（买方拒绝了该低点）")
    points.append(("Back above" if cyc.get("above_ma10") else "Still below")
                  + " the 10-day average"
                  + (", and it's turning up" if cyc.get("ma10_rising") and cyc.get("above_ma10") else ""))
    points_zh.append(("重新站上" if cyc.get("above_ma10") else "仍位于")
                     + " 10 日均线"
                     + ("之上，且均线开始向上" if cyc.get("ma10_rising") and cyc.get("above_ma10")
                        else ("之上" if cyc.get("above_ma10") else "之下")))
    if d.get("macd_cross_up"):
        points.append("Daily momentum just crossed up")
        points_zh.append("日线动量刚刚向上交叉")
    elif d.get("macd_cross_dn"):
        points.append("Daily momentum just crossed down")
        points_zh.append("日线动量刚刚向下交叉")
    elif d.get("macd_approaching_up") and d.get("macd_bars_to_cross"):
        points.append(f"Daily momentum ~{d['macd_bars_to_cross']:.0f} bars from turning up")
        points_zh.append(f"日线动量距转为向上约 {d['macd_bars_to_cross']:.0f} 根 K 线")
    if plain.get("translation") and cyc.get("translation") == "left" and not weekly_cross_rescue:
        # a fresh weekly up-cross overrides a PRIOR-cycle left-translation "tiring" hint —
        # it describes the completed cycle, not the new leg, so it would contradict the verdict
        points.append("Prior cycle topped early (a tiring-trend hint)")
        points_zh.append("上一周期见顶偏早（趋势走弱的暗示）")

    return {"state": state, "label": disp["label"], "action": disp["action"],
            "dir": disp["dir"], "score": int(np.clip(score, -100, 100)),
            "why": why, "next": nxt, "weekly_ok": weekly_ok,
            "regime": reg, "regime_label": REGIME_DISPLAY[reg]["label"],
            "regime_why": regime.get("why", ""), "regime_score": regime.get("score"),
            "regime_line": regime_line, "summary_line": summary_line,
            "synthesis_line": synthesis_line, "synthesis_line_zh": synthesis_line_zh,
            "points": points, "entry": entry, "cycle_plain": plain,
            "early_note": early_note,
            "early_tier": early.get("tier") if early_note else None,
            "early_dir": early.get("dir") if early_note else None,
            "why_zh": why_zh or why, "next_zh": nxt_zh or nxt,
            "regime_line_zh": regime_line_zh, "summary_line_zh": summary_line_zh,
            "points_zh": points_zh, "early_note_zh": early_note_zh,
            "liq_regime": liq_regime, "liq_effect": liq_effect,
            "liq_line": liq_line, "liq_line_zh": liq_line_zh,
            "macro_effect": macro_effect, "macro_pen": macro_pen,
            "macro_drag": (round(float(macro_drag), 3) if macro_on else None),
            "macro_beta": (float(macro_beta) if macro_on else 0.0),
            "macro_line": macro_line, "macro_line_zh": macro_line_zh,
            "vol_regime_state": (vr_state if vr_on else None),
            "vol_regime_effect": vr_effect, "vol_regime_pen": vr_pen,
            "vol_regime_scored_active": bool((_vr or {}).get("scored_active")),
            "vol_regime_line": vr_line, "vol_regime_line_zh": vr_line_zh,
            # W4.6: fitted RISK-channel SIZE multiplier (additive to sizing, never to the
            # directional score). 1.0 when no artifact / no family / null cell — currently
            # 1.0 for every cell (no risk-sizing signal survived the FDR gate).
            "risk_size_mult": risk_size_mult(state, family)}


# ----------------------------------------------------- signal age / strength ----

SIGNAL_AGE_LOOKBACK = 45   # trading days we look back for the last state change


def signal_age(close: pd.Series, current_state: str, high: pd.Series | None = None,
               kind: str = "equity", max_lookback: int = SIGNAL_AGE_LOOKBACK) -> dict:
    """How many trading days ago the signal last 'crossed' into `current_state`.

    Re-runs the ladder backward over the SAME trailing 600-day window used by
    calibrate_ladder, stopping at the first earlier day whose state differs from
    today's headline state — so a freshly-flipped signal costs ~1-2 evals and only
    a long-stable trend pays the full lookback. The current state is passed in
    (the live, full-history one shown in the UI) and every past day is compared
    against it, so the answer can never contradict the displayed label.

    Deliberately kept OUT of ladder_state() — and thus out of the calibration
    walk-forward — so it's computed exactly once per instrument, from analyze().

    Returns {"days": int, "capped": bool, "prev_state": str|None, "date": str|None}:
      days       trading days the signal has been in force (0 = it flipped today);
      capped     True when it has held for the whole lookback (so "≥ max_lookback");
      prev_state the state it replaced (None when capped / unknown);
      date       approx calendar date the signal turned on (None when capped).
    """
    c = close.dropna()
    n = len(c)
    if n < 300 or not current_state:
        return {}
    h = high.dropna() if high is not None else None

    def state_at(end: int) -> str | None:
        sub = c.iloc[max(0, end - 600): end + 1]
        if len(sub) < 260:
            return None
        hsub = h.reindex(sub.index) if h is not None else None
        cyc = cycle_state(sub, hsub, kind)
        if not cyc:
            return None
        mtf = mtf_snapshot(sub, kind)
        early = early_signals(sub, cyc, mtf)
        return (ladder_state(cyc, mtf, early) or {}).get("state")

    days_ago = None
    prev_state = None
    for i in range(1, max_lookback + 1):
        st = state_at(n - 1 - i)
        if st is None:              # ran out of usable window — can't see further back
            break
        if st != current_state:
            days_ago = i - 1        # the first `current_state` bar is i-1 days before today
            prev_state = st
            break
    capped = days_ago is None
    if capped:
        days_ago = max_lookback
    first_idx = n - 1 - days_ago
    when = str(c.index[first_idx].date()) if (not capped and 0 <= first_idx < n) else None
    return {"days": int(days_ago), "capped": bool(capped),
            "prev_state": prev_state, "date": when}


def _strength_word(score: int) -> tuple[str, str]:
    """Qualitative read of the (transparent, already-calibrated) ladder score —
    its MAGNITUDE is how decisive the signal is, regardless of direction."""
    a = abs(int(score))
    if a >= 70:
        return ("strong", "强")
    if a >= 40:
        return ("moderate", "中等")
    if a >= 15:
        return ("mild", "温和")
    return ("faint", "微弱")


def signal_age_fields(state: str, score: int, age: dict) -> dict:
    """Plain-language 'when did this signal cross / how strong is it' lines
    (EN + ZH) plus a compact badge, built from signal_age() + the ladder score."""
    disp = STATE_DISPLAY.get(state, {})
    label = disp.get("label", state)
    label_zh = disp.get("label_zh", label)
    days = age["days"]
    capped = age["capped"]
    when = age.get("date")
    prev = age.get("prev_state")
    prev_label = STATE_DISPLAY.get(prev, {}).get("label", prev) if prev else None
    prev_label_zh = STATE_DISPLAY.get(prev, {}).get("label_zh", prev_label) if prev else None
    sword, sword_zh = _strength_word(score)

    if capped:
        wk = max(1, round(days / 5))
        en = (f"⏱ This {label} reading has held for {days}+ trading days "
              f"(over ~{wk} weeks) — an established trend, not a fresh signal.")
        zh = (f"⏱ 当前的{label_zh}读数已持续 {days} 个交易日以上"
              f"（约 {wk} 周以上）——属于既定趋势，并非新出现的信号。")
        short, short_zh = f"{days}d+", f"{days}天+"
    elif days == 0:
        en = f"⏱ {label} signal just triggered today (fresh cross"
        zh = f"⏱ {label_zh}信号于今日刚刚触发（全新交叉"
        if prev_label:
            en += f" from {prev_label}"
            zh += f"，自{prev_label_zh}翻转"
        en += ")."
        zh += "）。"
        short, short_zh = "today", "今日"
    else:
        unit = "trading day" if days == 1 else "trading days"
        en = f"⏱ {label} signal triggered {days} {unit} ago"
        zh = f"⏱ {label_zh}信号于 {days} 个交易日前触发"
        if when:
            en += f" (~{when})"
            zh += f"（约 {when}）"
        if prev_label:
            en += f", switching from {prev_label}"
            zh += f"，自{prev_label_zh}切换而来"
        en += "."
        zh += "。"
        short, short_zh = f"{days}d ago", f"{days}天前"

    en += f" Signal strength: {sword} (score {int(score):+d}/100)."
    zh += f" 信号强度：{sword_zh}（评分 {int(score):+d}/100）。"
    return {"age_days": days, "age_capped": capped, "prev_state": prev,
            "signal_date": when, "strength": sword, "strength_zh": sword_zh,
            "age_line": en, "age_line_zh": zh,
            "age_short": short, "age_short_zh": short_zh}


# ----------------------------------------------------- entry-quality score ----
# A SIGNED −100..+100 "how good is THIS moment to enter" score (buy-setup
# positive / sell-setup negative). It is NOT an alpha/return predictor — a 54k-
# sample backtest (research/ENTRY_QUALITY.md, scripts.research_conviction) showed
# buying near the cycle low CONTROLS RISK (forward drawdown ≈30% smaller near the
# low vs chasers far above it, >25%) but does NOT beat buying strength on return (trend
# persistence wins at 1-3mo). So this scores ENTRY QUALITY / RISK-TIMING:
# near the pivot + a fresh momentum turn + the low actually holding + with-trend.
# Weights are evidence-led — proximity dominates, freshness is a staleness
# guardrail, the "holding" filter stops it rewarding a falling knife.

EQ_W_PROX, EQ_W_FRESH, EQ_W_MOM = 0.52, 0.30, 0.18


def _eq_ramp(x: float, x0: float, x1: float, y0: float = 0.0, y1: float = 1.0) -> float:
    if x1 == x0:
        return y1 if x >= x1 else y0
    return y0 + (y1 - y0) * float(np.clip((x - x0) / (x1 - x0), 0.0, 1.0))


def _macd_cross_ages(hist: pd.Series) -> tuple[int | None, int | None]:
    """Trading days since the most recent up-cross (≤0→>0) and down-cross."""
    h = hist.dropna().to_numpy()
    if len(h) < 3:
        return None, None
    pos = h > 0
    up = dn = None
    for k in range(len(h) - 1, 0, -1):
        if up is None and pos[k] and not pos[k - 1]:
            up = len(h) - 1 - k
        if dn is None and not pos[k] and pos[k - 1]:
            dn = len(h) - 1 - k
        if up is not None and dn is not None:
            break
    return up, dn


def _eq_proximity(pct: float, up: bool) -> float:
    """Closeness to the pivot. Long: best just above the low (lifted, not chasing),
    knife-discounted below it. Mirror (distance below the high) for the short side."""
    p = pct if up else -pct
    if p < -0.06:
        return 0.15                                  # deep below the pivot — falling knife
    if p < -0.03:
        return _eq_ramp(p, -0.06, -0.03, 0.15, 0.5)  # ramp the knife discount in (continuous)
    if p < 0.0:
        return _eq_ramp(p, -0.03, 0.0, 0.5, 0.9)
    if p < 0.03:
        return _eq_ramp(p, 0.0, 0.03, 0.9, 1.0)      # the sweet spot
    if p < 0.06:
        return _eq_ramp(p, 0.03, 0.06, 1.0, 0.85)
    return _eq_ramp(p, 0.06, 0.18, 0.85, 0.2)        # decays as it runs away


def _eq_freshness(d: dict, cross_age: int | None, early_match: bool, up: bool,
                  pct: float = 0.0) -> float:
    """Flat for ~2 weeks after the cross, decays once stale (>~3-4 wks were the
    worst band), with anticipation credit before the cross. A *late* cross — one
    that only prints once price is already extended past the pivot — is a chase,
    not an early turn, so the post-cross credit is scaled by distance from the
    pivot (`pct`, signed like proximity): full near the low, decaying to 0.4 once
    extended. Measured (research/ENTRY_QUALITY.md): among fresh up-crosses the
    forward 63d drawdown worsens −6.8%→−10.9% as distance grows, so freshness
    must not exempt the chaser — without this a fresh-but-extended cross scored
    full freshness and washed out the proximity penalty (the SNDK +48% case)."""
    crossed = d.get("macd_pos") if up else (not d.get("macd_pos"))
    if crossed:
        a = cross_age if cross_age is not None else 4
        if a <= 12:
            base = 1.0
        elif a <= 30:
            base = 1.0 - 0.65 * (a - 12) / 18
        else:
            base = 0.35
        p = pct if up else -pct       # distance ABOVE the low (mirror: below the high)
        return base * _eq_ramp(p, 0.03, 0.18, 1.0, 0.4)
    appr = d.get("macd_approaching_up") if up else d.get("macd_approaching_dn")
    curl = d.get("macd_curl_up") if up else d.get("macd_curl_dn")
    btc = d.get("macd_bars_to_cross")
    if appr and btc:
        return 0.5 + 0.3 * _eq_ramp(btc, 8, 0)       # closer to the cross → higher
    if curl or early_match:
        return 0.45
    return 0.0


def _eq_momentum(d: dict, up: bool) -> float:
    r = d.get("rsi14")
    r = 50 if r is None else r   # genuine RSI 0 (max oversold) must NOT be coerced to neutral
    if up:
        return 0.5 * float(bool(d.get("macd_pos"))) + 0.5 * float(40 <= r <= 62)
    return 0.5 * float(not d.get("macd_pos")) + 0.5 * float(38 <= r <= 60)


# the ladder owns DIRECTION; entry_quality only scores how good that entry is —
# so its sign is anchored to the state, never allowed to flip against it.
_EQ_BULLISH = {"FRESH BUY", "TURN SIGNALED", "RALLY ON", "BOTTOM WATCH",
               "COUNTERTREND BOUNCE", "CONFIRMING TURN"}
_EQ_BEARISH = {"TOP WATCH", "ROLLING OVER", "DECLINE"}


def entry_quality(close: pd.Series, cyc: dict, mtf: dict, early: dict,
                  regime: dict, state: str | None = None) -> dict:
    """Signed entry-quality score in [-100, +100] (buy-setup positive). Cheap,
    point-in-time — no backward walk. See the module banner for what it measures.
    `state` is the ladder state: it anchors the SIGN so the score can never
    contradict the displayed call (a TOP WATCH is never a 'buy-setup')."""
    d = (mtf or {}).get("D", {})
    if not d or not cyc:
        return {}
    c = close.dropna()
    if len(c) < 60:
        return {}
    price = float(c.iloc[-1])
    hist = macd_parts(c)["hist"]
    up_age, dn_age = _macd_cross_ages(hist)

    low = cyc.get("cand_price") or cyc.get("dcl_price") or price
    pct_low = price / low - 1.0 if low else 0.0
    look = max(25, int(cyc.get("dc_day") or 25))
    hi = float(c.iloc[-look:].max())
    pct_hi = price / hi - 1.0 if hi else 0.0

    reg = (regime or {}).get("regime", "neutral")

    # LONG (buy-setup) ----------------------------------------------------------
    up_raw = (EQ_W_PROX * _eq_proximity(pct_low, True)
              + EQ_W_FRESH * _eq_freshness(d, up_age, early.get("dir") == "up", True, pct_low)
              + EQ_W_MOM * _eq_momentum(d, True))
    up_hold = np.clip(0.5 * float(bool(cyc.get("swing_low") or cyc.get("cand_swing")))
                      + 0.3 * float(bool(cyc.get("above_ma10")))
                      + 0.2 * float(bool(cyc.get("ma10_rising"))), 0, 1)
    up_gate = {"bull": 1.0, "neutral": 0.8, "bear": 0.45}.get(reg, 0.8)
    if cyc.get("failed_cycle"):
        up_gate *= 0.3
    if cyc.get("ic_failed"):
        up_gate *= 0.6
    long_eq = up_gate * (0.55 + 0.45 * up_hold) * up_raw

    # SHORT (sell/exit-setup) ---------------------------------------------------
    dn_raw = (EQ_W_PROX * _eq_proximity(pct_hi, False)
              + EQ_W_FRESH * _eq_freshness(d, dn_age, early.get("dir") == "down", False, pct_hi)
              + EQ_W_MOM * _eq_momentum(d, False))
    dn_hold = np.clip(0.5 * float(not cyc.get("above_ma10"))
                      + 0.3 * float(not cyc.get("ma10_rising"))
                      + 0.2 * float(early.get("dir") == "down"), 0, 1)
    dn_gate = {"bear": 1.0, "neutral": 0.8, "bull": 0.45}.get(reg, 0.8)
    short_eq = dn_raw * dn_gate * (0.55 + 0.45 * dn_hold)

    # anchor the SIGN to the ladder's direction; magnitude = entry quality
    if state in _EQ_BEARISH:
        score = -short_eq * 100
    elif state in _EQ_BULLISH:
        score = long_eq * 100
    else:                                     # unknown/neutral — let the stronger side speak
        score = (long_eq - short_eq) * 100
    # a counter-trend bounce is explicitly high-risk ("NIMBLE ONLY") — never let it
    # present as a strong/solid buy; cap its magnitude into the "light" band.
    if state == "COUNTERTREND BOUNCE":
        score = float(np.clip(score, -30, 30))
    score = float(np.clip(score, -100, 100))
    # a NaN anywhere in the inputs (bad tape, non-finite pivot price) propagates
    # here — omit the badge entirely rather than hand NaN to entry_quality_fields
    # (int(round(nan)) raises and would drop the whole record upstream)
    if not all(np.isfinite(v) for v in (score, long_eq, short_eq, pct_low)):
        return {}
    return {"score": round(score, 1), "long": round(long_eq * 100, 1),
            "short": round(short_eq * 100, 1),
            "pct_from_low": round(pct_low * 100, 1)}


# qualitative grade for the signed score's magnitude (direction set by sign)
def _eq_grade(score: float) -> tuple[str, str]:
    a = abs(score)
    if a >= 60:
        return ("strong", "强")
    if a >= 35:
        return ("solid", "稳健")
    if a >= 15:
        return ("light", "偏弱")
    return ("minimal", "微弱")


def entry_quality_fields(eq: dict, state: str | None = None) -> dict:
    """Concise badge text + one-line honest tooltip (EN+ZH). Direction wording is
    state-aware so a watch/high-risk state never reads as a flat 'buy now', and
    every display field is driven off the SAME rounded integer (`sr`) so the
    arrow, grade, badge and label can never disagree at a boundary."""
    s = eq["score"]
    sr = int(round(s))
    grade, grade_zh = _eq_grade(sr)
    if sr >= 15:
        arrow = "▲"
        if state == "COUNTERTREND BOUNCE":
            dirn, dirn_zh = "unconfirmed turn", "未确认转向"
        elif state in ("BOTTOM WATCH", "TURN SIGNALED"):
            dirn, dirn_zh = "buy setting up", "买入构筑中"
        else:
            dirn, dirn_zh = "buy-setup", "买入形态"
    elif sr <= -15:
        arrow = "▼"
        if state == "TOP WATCH":
            dirn, dirn_zh = "exit setting up", "离场构筑中"
        else:
            dirn, dirn_zh = "sell/exit-setup", "卖出/离场形态"
    else:
        arrow, dirn, dirn_zh = "·", "no clean setup", "无明确形态"
    badge = f"{arrow} {sr:+d}"
    label = f"Entry quality: {grade} {dirn} ({sr:+d})"
    label_zh = f"入场质量：{grade_zh}{dirn_zh}（{sr:+d}）"
    tip = ("How well-timed & low-risk THIS entry is — near the cycle "
           f"{'low' if sr >= 0 else 'high'}, a fresh momentum turn, and with-trend. "
           "Measured: entries near the pivot drew ~30% smaller drawdowns than chasers "
           "far above it — risk control, NOT a return forecast.")
    tip_zh = ("衡量当前入场的时机与风险——贴近周期"
              f"{'低点' if sr >= 0 else '高点'}、动量新近转向、且顺势。"
              "实测：贴近枢轴的入场，其回撤比远离枢轴的追高者约小 30%——这是风险控制，并非收益预测。")
    return {"eq_score": s, "eq_grade": grade, "eq_grade_zh": grade_zh,
            "eq_dir": "up" if sr >= 15 else "down" if sr <= -15 else "flat",
            "eq_badge": badge, "eq_label": label, "eq_label_zh": label_zh,
            "eq_tip": tip, "eq_tip_zh": tip_zh,
            "eq_pct_from_low": eq.get("pct_from_low")}


# ------------------------------------------------- bottom confidence (multi-TF) ----
# Surfaced 0-100 "Bottom Confidence" for the buy-side / bottoming states. It does
# NOT replace entry_quality — it EXTENDS it. Measured (research/BOTTOM_CONFIDENCE.md,
# 68,916 walk-forward evals over 109 deep-history names): the two axes are
# orthogonal — entry_quality's proximity-to-the-low governs DRAWDOWN DEPTH (tail
# halves across its range), while multi-timeframe confluence governs DURABILITY
# (the "cycle low held" rate climbs 30%->75%). WEEKLY confirmation is the strong
# lever (+19pp held-rate vs +4pp monthly), so it dominates the confluence weight.
# Conservative by design: confluence only DISCOUNTS the (drawdown-calibrated) entry
# quality when the higher timeframes haven't confirmed the turn — never inflates it.

# States where "is this a durable bottom?" is the live question (the measured pop).
_BC_STATES = {"DECLINE", "BOTTOM WATCH", "TURN SIGNALED", "FRESH BUY",
              "COUNTERTREND BOUNCE"}
# Confluence weights — weekly dominant per the measured held-rate lift.
_BC_TF_WEIGHTS = {"D": 0.20, "3D": 0.20, "W": 0.45, "M": 0.15}
_BC_TF_KEY = {"D": "daily", "3D": "three_day", "W": "weekly", "M": "monthly"}


def _tf_turning_up(s: dict) -> bool:
    """A timeframe is 'turning up' if its MACD just crossed up, curled up off a
    histogram trough, is approaching an up-cross, or StochRSI popped out of
    oversold — the bottoming-confluence primitive from research/BOTTOM_CONFIDENCE.md."""
    if not s:
        return False
    return bool(s.get("macd_cross_up") or s.get("macd_curl_up")
                or s.get("macd_approaching_up") or s.get("stoch_cross_up"))


# ----- multi-timeframe BOTTOMING ALIGNMENT (the standout-strip selection gate) ----
# This is the SELECTION gate for the standout boards (US/CA/CN/HK). Its job is a
# low-risk SWING entry (1-3 month horizon), so it REWARDS EARLINESS + an OVERSOLD
# ORIGIN and EXCLUDES the extended chase — the opposite of the prior version, whose
# _ALIGN_PHASE_VAL peaked at `rising` (already-running) and so put the LATE, mid-rally
# names at the top of the board. The states, ranked best-first:
#   * PRIME (the prize): weekly STILL in its bear leg but RECOVERING (histogram curling
#     back up from below zero = `bear_recovering`), OR basing/turning, + the 3-day just
#     turning up FROM A LOW + the daily just crossing. The "best combination."
#   * ARMED: a fresh 3-day turn-from-low + a daily trigger, but the weekly has already
#     turned up (rising) — a good entry, just later than PRIME.
#   * APPROACHING (= `near`, backfill only, never a confirmed buy): weekly OK and ONE
#     lower timeframe turning, but not all three confirmed. Fills the strip when fresh
#     entries are thin so it is never bare — clearly tagged, still no falling knife.
#   * EXCLUDED -> watch: weekly still falling / a deep knife / a bad cycle state, or
#     OVEREXTENDED (3D/daily StochRSI overbought, daily RSI hot, or far above the 200dma)
#     — the "already ran" names, surfaced honestly as "wait for a pullback".
# The 3-day "fresh from oversold" leg uses StochRSI crossing up from < stoch_oversold
# (default 25, the user's line) recomputed from the 3-day spark_stoch — NOT the engine's
# hardwired 20-line stoch_cross_up primitive, which other consumers depend on. Display-
# tier: a calibrated cycle read, never a validated probability; it gates WHICH names show.

# Tunables live in config.yml engine.entry_gate; the constants here are the fallbacks
# (so a missing block can never crash a legacy caller). Read once at import.
def _entry_gate_cfg() -> dict:
    try:
        return (config.load().get("engine") or {}).get("entry_gate") or {}
    except Exception:  # noqa: BLE001 — config unavailable at import in some test paths
        return {}


_EG = _entry_gate_cfg()
_EG_STOCH_OS = float(_EG.get("stoch_oversold", 25.0))               # 3D StochRSI "from oversold" line
_EG_STOCH_OB = float(_EG.get("stoch_overbought", 80.0))            # 3D/daily StochRSI overbought = chase
_EG_DAILY_RSI_MAX = float(_EG.get("daily_rsi_extension_cap", 62.0))  # daily RSI14 hotter than this = too late
_EG_STRETCH_BLOCK = float(_EG.get("stretch_block_pct", 30.0))     # % over 200dma = overextended chase
_EG_APPROACH_DAYS = int(_EG.get("approach_days", 2))               # 3D "about to cross" ETA cap (trading days)
_EG_OSC_EXEMPT_BELOW = float(_EG.get("overextended_osc_exempt_below_pct", -10.0))
# When price is this far BELOW the 200dma, the oscillator legs (StochRSI/RSI14) are
# suppressed: post-washout the look-back range is compressed so any bounce pins
# StochRSI > 80 (range-compression noise, not extension). The stretch leg
# (ext_pct >= +30%) is unreachable at such distances and is unaffected.

# how good each leg is, for the in-tier rank (earliness/oversold-origin weighted, NOT
# lateness): a weekly bear-recovering + a 3D StochRSI-from-oversold turn score highest.
_WEEKLY_PHASE_VAL = {"bear_recovering": 1.0, "basing": 0.85, "turning": 0.7,
                     "rising": 0.35, "rolling": 0.1, "falling": 0.0, "unknown": 0.0}
_T3_TRIG_VAL = {"stoch_os": 1.0, "macd_trough": 0.85, "approaching": 0.55, None: 0.0}
_DAILY_TRIG_VAL = {"crossed": 1.0, "imminent": 0.8, "early": 0.45, None: 0.0}
# tier offsets keep PRIME above ARMED above APPROACHING when sorting the strip by score
_TIER_BASE = {"PRIME": 200.0, "ARMED": 100.0, "APPROACHING": 0.0}
_WEEKLY_PRIME = {"bear_recovering", "basing", "turning"}            # early-enough for PRIME
_WEEKLY_OK = {"bear_recovering", "basing", "turning", "rising"}     # eligible at all (not falling/topping)
# ladder states that are structurally NOT a bottoming entry (a falling knife or a top)
# — excluded from alignment regardless of a one-bar daily up-tick.
# Cross-ref: engine/stock_score.py _CYCLE_BLOCK_STATES gates the buy verb / entry-axis cap.
# The two sets intentionally diverge on COUNTERTREND BOUNCE: _ALIGN_BAD_STATES includes it
# (no alignment signal — the bounce is noise-level), while _CYCLE_BLOCK_STATES does NOT
# (the stock is scoreable; the name just can't be ranked into the buy strip).  Update both
# sets together whenever the cycle ontology changes.
_ALIGN_BAD_STATES = {"DECLINE", "ROLLING OVER", "TOP WATCH", "COUNTERTREND BOUNCE"}
_ALIGN_KNIFE_BLOCK = 0.7        # washout knife severity that HARD-excludes a name
_ALIGN_DAILY_MAX_DAYS = 2       # "daily about to cross in 1-2 days"
_ALIGN_RSI_EXTENDED = 68.0      # _daily_trigger "early" ceiling (overextension handled separately)


def _hist_falling(spark, bars: int = 3) -> bool:
    """True if a MACD histogram is strictly DECLINING over the last `bars` steps —
    the 'below zero AND still dropping' bear-leg tell that the realized/approaching
    down-cross flags miss (those only fire above zero). `spark` = a _tf_state
    spark_hist (most-recent last)."""
    h = [x for x in (spark or []) if x is not None]
    if len(h) < bars + 1:
        return False
    seg = h[-(bars + 1):]
    return all(seg[i] < seg[i - 1] for i in range(1, len(seg)))


def _weekly_bear_recovering(w: dict) -> bool:
    """The user's "best combination" weekly leg: MACD STILL bearish (histogram below
    zero) but RECOVERING — curling up off the trough, approaching the zero-cross, or the
    histogram rising while still negative ("about to re-enter / already re-entering").
    macd_curl_up / macd_approaching_up already encode "below zero and turning up"; the
    spark arm catches a multi-bar recovery the single-bar flags can miss."""
    if not w or w.get("macd_pos") or w.get("macd_cross_dn"):
        return False
    if w.get("macd_curl_up") or w.get("macd_approaching_up"):
        return True
    sp = [x for x in (w.get("spark_hist") or []) if x is not None]
    return bool(len(sp) >= 3 and sp[-1] < 0 and sp[-1] > sp[-2] > sp[-3])


def _tf_phase(s: dict, weekly: bool = False) -> str:
    """Classify one timeframe's MACD posture for the bottoming screen:
    ``rising`` (above zero, healthy) · ``rolling`` (above zero but topping) ·
    ``turning`` (below zero, first hint of an up-turn) · ``basing`` (below zero,
    flat near a low) · ``falling`` (below zero AND still dropping, or a fresh
    down-cross) · ``unknown`` (no data).

    With ``weekly=True`` a below-zero-but-RECOVERING weekly returns ``bear_recovering``
    (the earliest, best swing-entry context — see _weekly_bear_recovering); every other
    call is unchanged, so the daily/3-day classification and existing callers are byte-
    identical."""
    if not s:
        return "unknown"
    if s.get("macd_pos"):
        return "rolling" if (s.get("macd_cross_dn") or s.get("macd_curl_dn")) else "rising"
    if s.get("macd_cross_dn"):
        return "falling"
    if weekly and _weekly_bear_recovering(s):
        return "bear_recovering"
    if (s.get("macd_cross_up") or s.get("macd_curl_up")
            or s.get("macd_approaching_up") or s.get("stoch_cross_up")):
        return "turning"
    if _hist_falling(s.get("spark_hist")):
        return "falling"
    return "basing"


def _daily_trigger(d: dict) -> str | None:
    """The daily entry trigger: ``crossed`` (just crossed up) / ``imminent`` (<=N
    days to a bullish cross) / ``early`` (already crossed and rising but NOT
    extended) / None. Encodes "just crossed or about to in 1-2 days, ok if a bit
    started"."""
    if not d:
        return None
    if d.get("macd_cross_up"):
        return "crossed"
    dtc = d.get("macd_days_to_cross")          # 0 is a valid ETA (crosses ~this bar), not "missing"
    if d.get("macd_approaching_up") and dtc is not None and dtc <= _ALIGN_DAILY_MAX_DAYS:
        return "imminent"
    rsi = d.get("rsi14")                        # guard falsy-zero: an absent RSI is unknown, not 50
    if (d.get("macd_pos") and not d.get("macd_cross_dn") and not d.get("macd_curl_dn")
            and (rsi is None or rsi <= _ALIGN_RSI_EXTENDED)):
        return "early"
    return None


def _three_day_fresh(t3: dict) -> str | None:
    """The 3-day ENTRY trigger — a fresh turn up FROM A LOW (the user's core rule).
    Returns the strongest matching reason or None:
      * ``macd_trough`` — MACD just crossed / curled up from below zero;
      * ``stoch_os``    — StochRSI just popped up from < stoch_oversold (default 25),
                          recomputed from the 3-day spark_stoch (NOT the 20-line primitive);
      * ``approaching`` — MACD about to cross up (still below zero) — "right about to cross".
    None when the 3-day is NOT turning up from a low (e.g. already rising mid-rally), so
    an extended name can never read as a fresh entry."""
    if not t3:
        return None
    if t3.get("macd_cross_up") or t3.get("macd_curl_up"):
        return "macd_trough"
    sp = [x for x in (t3.get("spark_stoch") or []) if x is not None]
    if len(sp) >= 2 and sp[-1] >= _EG_STOCH_OS and any(v < _EG_STOCH_OS for v in sp[-4:-1]):
        return "stoch_os"
    if t3.get("macd_approaching_up") and not t3.get("macd_pos"):
        return "approaching"
    return None


def _overextended(mtf: dict, ext_pct: float | None = None) -> bool:
    """True when the move has ALREADY run — the "awful entry" the board must exclude:
    3-day OR daily StochRSI overbought (> stoch_overbought), daily RSI14 hotter than the
    extension cap, or price far above the 200-day (ext_pct >= stretch_block). ext_pct (%
    over the 200dma) is supplied by analyze(); the oscillator legs work without it, so
    callers that don't pass it still get the StochRSI/RSI brakes.

    OSC EXEMPT BELOW guard (mirrors the RALLY ON→TOP WATCH fix at line 1006-1014):
    When ext_pct is not None AND ext_pct <= _EG_OSC_EXEMPT_BELOW (default −10%), the
    two oscillator legs (StochRSI overbought + RSI14 cap) are SUPPRESSED. Post-washout
    the short look-back range is compressed — any bounce pins StochRSI > 80 without the
    stock being remotely extended; e.g. 600519.SS 2026-07-10 D.stoch=83 / pct_vs_200dma
    −12.5 → misfired as "extended → entry_confirm × 0.50". The stretch leg
    (ext_pct >= +30%) is unreachable when price is deep below the 200dma and is unchanged.
    When ext_pct is None (close-only callers: ladder_state's de-escalation gate at
    line 1400), behavior is UNCHANGED — osc legs fire as before."""
    d = mtf.get("D") or {}
    # oscillator legs are suppressed when price is far below the 200dma (range-compression
    # saturation); the stretch leg is structurally unreachable there and is unaffected.
    osc_exempt = ext_pct is not None and ext_pct <= _EG_OSC_EXEMPT_BELOW
    if not osc_exempt:
        for tf in (d, mtf.get("3D") or {}):
            st = tf.get("stoch")
            if st is not None and st > _EG_STOCH_OB:
                return True
        rsi = d.get("rsi14")
        if rsi is not None and rsi > _EG_DAILY_RSI_MAX:
            return True
    return bool(ext_pct is not None and ext_pct >= _EG_STRETCH_BLOCK)


def mtf_alignment(mtf: dict, cyc: dict | None = None, lad: dict | None = None,
                  wo: dict | None = None, ext_pct: float | None = None) -> dict:
    """Weekly + 3-Day + Daily bottoming-ALIGNMENT verdict for the standout strip.

    Tiers, best-first (``tier``; ``aligned``/``near`` kept for the existing
    setups.alignment_gate contract — aligned == PRIME|ARMED, near == APPROACHING):
      * ``PRIME`` — weekly bear_recovering/basing/turning + a FRESH 3-day turn from a low
        (_three_day_fresh) + a daily trigger, not overextended/blocked. The best entry.
      * ``ARMED`` — same fresh 3-day + daily, but the weekly has already turned up (rising).
      * ``APPROACHING`` (=near, BACKFILL only) — weekly OK + one lower timeframe turning,
        not all three confirmed; fills the strip when fresh entries are thin.
      * excluded -> watch: weekly falling / deep knife / bad cycle state / OVEREXTENDED.

    ``score`` = tier offset + a 0-100 ``quality`` (earliness/oversold-origin weighted,
    knife-tempered) so PRIME > ARMED > APPROACHING when the strip sorts by score.
    Returns {} when there is no daily timeframe."""
    D = mtf.get("D") or {}
    if not D:
        return {}
    W, T3 = mtf.get("W") or {}, mtf.get("3D") or {}
    wph, t3ph, dph = _tf_phase(W, weekly=True), _tf_phase(T3), _tf_phase(D)
    have_tf = bool(W) and bool(T3)             # need weekly + 3-day to judge alignment

    t3_trig = _three_day_fresh(T3)             # fresh turn from a low (None = already running)
    t3_fresh = t3_trig is not None
    trigger = _daily_trigger(D)
    daily_ok = trigger is not None
    weekly_ok = wph in _WEEKLY_OK
    over = _overextended(mtf, ext_pct)

    knife = float((wo or {}).get("knife", 0.0))
    state = (lad or {}).get("state")
    blocked = ((knife >= _ALIGN_KNIFE_BLOCK) or (state in _ALIGN_BAD_STATES)
               or (wph == "falling"))

    tier = None
    if have_tf and not blocked and not over:
        if weekly_ok and t3_fresh and daily_ok:
            tier = "PRIME" if wph in _WEEKLY_PRIME else "ARMED"
        elif weekly_ok and (t3_fresh or daily_ok):
            tier = "APPROACHING"
    # CONFIRMING TURN is capped at APPROACHING (near) — weekly unconfirmed, so
    # it should not surface as a PRIME/ARMED (aligned) entry on the strip.
    if state == "CONFIRMING TURN" and tier in ("PRIME", "ARMED"):
        tier = "APPROACHING"
    aligned = tier in ("PRIME", "ARMED")
    near = tier == "APPROACHING"

    quality = round(100.0 * (0.42 * _WEEKLY_PHASE_VAL.get(wph, 0.0)
                             + 0.30 * _T3_TRIG_VAL[t3_trig]
                             + 0.28 * _DAILY_TRIG_VAL[trigger])
                    * (1.0 - 0.45 * min(knife, 1.0)), 1)
    score = round(_TIER_BASE.get(tier, 0.0) + quality, 1)

    # human-readable entry label + a one-line "why" (EN + 中文)
    _t3_en = {"stoch_os": "3D StochRSI crossed up from oversold",
              "macd_trough": "3D MACD turned up from below zero",
              "approaching": "3D MACD about to cross up", None: None}
    _t3_zh = {"stoch_os": "3日 StochRSI 从超卖上穿",
              "macd_trough": "3日 MACD 在零轴下方上拐", "approaching": "3日 MACD 临近上穿", None: None}
    _wk_en = {"bear_recovering": "weekly histogram recovering (still bearish)",
              "basing": "weekly basing", "turning": "weekly turning up",
              "rising": "weekly uptrend", "rolling": "weekly rolling over",
              "falling": "weekly still falling", "unknown": ""}
    _wk_zh = {"bear_recovering": "周线柱状图回升（仍偏熊）", "basing": "周线筑底",
              "turning": "周线转向", "rising": "周线上行", "rolling": "周线走弱",
              "falling": "周线仍下行", "unknown": ""}
    if over:
        entry_tier, entry_tier_zh = "Extended — wait", "已过热 — 等回调"
        reason = "Already extended (overbought / far above the 200-day) — wait for a pullback"
        reason_zh = "已过热（超买／远高于200日均线）— 等待回调"
    elif tier:
        entry_tier = {"PRIME": "Prime entry", "ARMED": "Entry armed",
                      "APPROACHING": "Approaching — early"}[tier]
        entry_tier_zh = {"PRIME": "黄金入场", "ARMED": "入场就绪",
                         "APPROACHING": "临近 — 偏早"}[tier]
        reason = "; ".join(x for x in (_t3_en.get(t3_trig), _wk_en.get(wph)) if x) or None
        reason_zh = "；".join(x for x in (_t3_zh.get(t3_trig), _wk_zh.get(wph)) if x) or None
    else:
        entry_tier = entry_tier_zh = reason = reason_zh = None

    dtxt = {"crossed": "crossed up", "imminent": "≈ cross", "early": "rising",
            None: "—"}[trigger]
    t3txt = {"stoch_os": "oversold↑", "macd_trough": "turn↑",
             "approaching": "≈cross", None: "·"}[t3_trig]
    line = f"Weekly {wph.replace('_', ' ')} · 3-Day {t3txt} · Daily {dtxt}"
    line_zh = (f"周线{_wk_zh.get(wph) or '—'} · "
               f"3日{ {'stoch_os':'超卖上穿','macd_trough':'上拐','approaching':'临近','·':'·'}.get(t3txt, t3txt) } · "
               f"日线{ {'crossed up':'已上穿','≈ cross':'临近上穿','rising':'上行','—':'—'}[dtxt] }")
    return {
        "aligned": aligned, "near": near, "tier": tier, "score": score, "quality": quality,
        "entry_tier": entry_tier, "entry_tier_zh": entry_tier_zh,
        "reason": reason, "reason_zh": reason_zh,
        "weekly": wph, "three_day": t3ph, "daily": dph,
        "weekly_ok": weekly_ok, "three_day_ok": t3_fresh, "three_day_trigger": t3_trig,
        "daily_ok": daily_ok, "daily_trigger": trigger, "overextended": over,
        "days_to_cross": D.get("macd_days_to_cross"),
        "knife": round(knife, 2), "have_tf": have_tf, "blocked": blocked,
        "line": line, "line_zh": line_zh,
    }


# ----- washout / knife-risk (Phase 2) -----
# MEASURED, counter-intuitively (research/BOTTOM_CONFIDENCE.md, 68,916 evals): a
# deep stretch BELOW the 200-day + a VIX panic is NOT a higher-confidence bottom —
# it's a falling KNIFE. Forward hold-rate FALLS (62%>>37% the deeper below the
# 200-day) and the drawdown tail BLOWS OUT (−10.5%→−22.5%); the big forward
# *return* is just the violent bounce, not durability. So washout TEMPERS (never
# boosts) bottom_confidence — a good-looking cycle low inside a broken primary
# trend that's still falling is knife-risk. The discount eases once price reclaims.
WASHOUT_MAX_PENALTY = 0.45        # max fraction shaved off bc at full knife severity
_WO_DEPTH_LO, _WO_DEPTH_HI = 0.08, 0.25   # % below 200dma: 0 knife at 8%, full at 25%


def market_vix_context(vix: "pd.Series | None") -> dict:
    """Market panic/washout context from VIX, computed ONCE (build-time) and
    threaded to every name like the liquidity regime. {pct: 1y percentile,
    panic: pct>=0.85, fading: rolling off a spike}. {} when VIX unavailable."""
    if vix is None:
        return {}
    v = vix.dropna()
    if len(v) < 60:
        return {}
    now = float(v.iloc[-1])
    pct = float((v.iloc[-252:] <= now).mean())
    fading = len(v) >= 6 and now < float(v.iloc[-6])
    return {"pct": round(pct, 2), "panic": bool(pct >= 0.85), "fading": bool(fading)}


def washout(close: pd.Series, cyc: dict, vix_ctx: dict | None = None) -> dict:
    """Per-stock knife-risk read: how stretched price is BELOW its 200-day (broken
    primary trend), gated by whether it's still falling vs reclaiming, amplified by
    a market VIX panic. 0..1 `knife` severity (orthogonal to cycle position)."""
    c = close.dropna()
    if len(c) < 200 or not cyc:
        return {}
    price = float(c.iloc[-1])
    sma200 = float(c.iloc[-200:].mean())
    d200 = price / sma200 - 1.0 if sma200 else 0.0          # negative = below
    depth = _eq_ramp(-d200, _WO_DEPTH_LO, _WO_DEPTH_HI)     # 0..1 how far below
    reclaim = bool(cyc.get("above_ma10"))                  # the reversal that matters
    # deep + still falling = acute knife; deep + reclaiming = much milder (measured:
    # deep&falling held 29.6% vs deep&reversing 55.7%)
    knife = depth * (0.35 if reclaim else 1.0)
    vp = vix_ctx or {}
    if vp.get("panic"):
        knife = min(1.0, knife * 1.25)                     # market panic worsens it
    knife = float(np.clip(knife, 0.0, 1.0))
    level = ("high" if knife >= 0.7 else "elevated" if knife >= 0.4
             else "watch" if knife >= 0.12 else "none")
    return {"knife": round(knife, 2), "pct_below_200d": round(100 * d200, 1),
            "depth": round(depth, 2), "reclaim": reclaim,
            "vix_panic": bool(vp.get("panic", False)), "level": level}


def bottom_confidence(mtf: dict, eq: dict, state: str | None,
                      wo: dict | None = None) -> dict:
    """0-100 confidence this is a DURABLE, low-drawdown bottom (buy-side states
    only). = entry_quality's LONG magnitude (proximity = the drawdown-depth axis)
    DISCOUNTED when (a) higher timeframes haven't confirmed the turn (durability
    axis; weekly heaviest) and (b) price is deeply washed out below its 200-day
    (knife risk; Phase 2). Both are discounts — confluence/washout never inflate.
    Returns {} for non-bottoming states."""
    if not eq or state not in _BC_STATES:
        return {}
    long_eq = float(eq.get("long", 0.0)) / 100.0                 # 0..1 (depth axis)
    tf = {_BC_TF_KEY[k]: _tf_turning_up(mtf.get(k, {})) for k in _BC_TF_WEIGHTS}
    have_m = bool(mtf.get("M"))
    # weighted confluence in [0,1]; if monthly is unavailable (thin history) drop
    # its weight and renormalise so a missing bar can't silently cap the score.
    wts = {k: w for k, w in _BC_TF_WEIGHTS.items() if k != "M" or have_m}
    wsum = sum(wts.values()) or 1.0
    tf_score = sum(w * float(tf[_BC_TF_KEY[k]]) for k, w in wts.items()) / wsum
    knife = float((wo or {}).get("knife", 0.0))
    washout_factor = 1.0 - WASHOUT_MAX_PENALTY * knife           # <=1, knife-risk temper
    bc = long_eq * (0.55 + 0.45 * tf_score) * washout_factor * 100.0
    if state == "COUNTERTREND BOUNCE":          # high-risk bounce, never a confident bottom
        bc = min(bc, 30.0)
    return {"score": round(float(np.clip(bc, 0, 100)), 1),
            "tf": tf, "tf_score": round(tf_score, 2), "monthly_avail": have_m,
            "knife": round(knife, 2), "wo_level": (wo or {}).get("level", "none"),
            "pct_below_200d": (wo or {}).get("pct_below_200d")}


def bottom_confidence_fields(bc: dict) -> dict:
    """Per-timeframe breakdown line + honest tooltip (EN+ZH) for the UI."""
    if not bc:
        return {}
    sr = int(round(bc["score"]))
    grade, grade_zh = _eq_grade(sr)                     # reuse strong/solid/light/minimal bands
    tf = bc["tf"]
    mk = lambda v: "✓" if v else "✗"
    mmark = mk(tf["monthly"]) if bc.get("monthly_avail") else "—"
    line = (f"Daily {mk(tf['daily'])} · 3-Day {mk(tf['three_day'])} · "
            f"Weekly {mk(tf['weekly'])} · Monthly {mmark}")
    line_zh = (f"日线 {mk(tf['daily'])} · 3日 {mk(tf['three_day'])} · "
               f"周线 {mk(tf['weekly'])} · 月线 {mmark}")
    tip = ("Confidence this is a DURABLE, low-drawdown bottom: how near price is to "
           "the cycle low (the drawdown-depth axis) discounted when higher "
           "timeframes haven't confirmed the turn. Measured: weekly confirmation "
           "lifted the 'cycle-low held' rate ~19pp — a higher score held far more "
           "often. Risk/durability, NOT a return forecast.")
    tip_zh = ("衡量当前是否为「持久、低回撤」底部的信心：价格距周期低点的远近（回撤深度轴），"
              "并在更高周期尚未确认转向时打折。实测：周线确认使「周期低点守住」的比例提升约 "
              "19 个百分点——分数越高，低点守住的概率越大。这是风险/持久性，并非收益预测。")
    out = {"bc_score": sr, "bc_grade": grade, "bc_grade_zh": grade_zh,
           "bc_line": line, "bc_line_zh": line_zh,
           "bc_weekly": tf["weekly"], "bc_monthly": tf["monthly"],
           "bc_tip": tip, "bc_tip_zh": tip_zh}
    # Phase 2 — knife-risk caution when price is deeply washed out below its 200-day
    lvl = bc.get("wo_level", "none")
    if lvl in ("elevated", "high"):
        below = bc.get("pct_below_200d")
        belowtxt = f"{abs(below):.0f}% below its 200-day" if below is not None else "far below its 200-day"
        out["bc_knife"] = lvl
        out["bc_knife_line"] = (
            f"⚠ Deep washout — price is {belowtxt}, a broken primary trend. "
            "Measured: setups this stretched below the 200-day held the cycle low "
            "only ~37% of the time and drew a ~−22% tail (violent bounces, rarely "
            "the durable low). Treat as knife-risk — wait for it to reclaim the "
            "10-day average and size small. The score above is already tempered for this.")
        out["bc_knife_line_zh"] = (
            f"⚠ 深度超卖——价格较 200 日均线低约 {abs(below):.0f}%（主趋势已破）。"
            "实测：如此远低于 200 日线的形态，仅约 37% 守住周期低点，且回撤尾部约 −22%"
            "（反弹猛烈，但很少是持久低点）。视为「接飞刀」风险——等其收复 10 日均线后再小仓参与。"
            "上方分数已据此打折。")
    return out


def analyze(close: pd.Series, high: pd.Series | None = None,
            kind: str = "equity", liquidity: str | None = None,
            macro_drag: float | None = None, macro_beta: float = 0.0,
            vix_ctx: dict | None = None, vol_regime: dict | None = None,
            price: pd.Series | None = None, family: str | None = None) -> dict:
    """`liquidity` = live US net-liquidity regime ("expanding"/"contracting"/
    "neutral", from engine.regime.liquidity_overlay), threaded into the ladder as
    an orthogonal macro conviction modifier. None => no liquidity context (keeps
    every existing caller working unchanged).

    `macro_drag` (MRS, 0..1; engine.conditions.macro_risk_score) × `macro_beta`
    (this name's sector sensitivity, engine.conditions.sector_macro_beta) add a
    risk-OFF, subtract-only, buy-setup-only conviction penalty for macro-sensitive
    names. `vix_ctx` = market panic context (engine.cycles.market_vix_context) used
    by the Phase-2 washout knife-risk temper on Bottom Confidence.

    `vol_regime` = the published INDEX vol-regime snapshot (engine.vol_regime.published_snapshot:
    {regime, scored_score, scored_active, vol_target_scalar, ...}). In a risk-off kill-switch
    regime it adds a UNIFORM, subtract-only, buy-setup-only sizing caution (deepened only when its
    validation gate is open). Defaults keep every existing caller unchanged.

    `price` (W2.2 substrate seam, ruling A13 — D4-owned, D1-reviewed) = the STRUCTURE-MATH
    basis series (split-adjusted, dividend-UNadjusted `close_price`).  When supplied, the
    structure-sensitive pieces — trough/pivot detection, DCL invalidation levels, the
    failed-cycle test (`cycle_state`, `signal_age`), and the drawdown-from-200d washout
    read — run on `price`, while the MACD / StochRSI / RSI momentum stats (`mtf_snapshot`,
    `early_signals`) stay on the passed `close` (the TR series, so a return/momentum stat
    keeps dividend fidelity).  This is D4 §7's structure-vs-momentum split.

    Default `price=None` reproduces the CURRENT behaviour BYTE-IDENTICALLY: everything runs
    on `close`.  This is the substrate seam ONLY — the split is a basis change, not an algo
    change; the momentum functions are unaffected and every structure function is called
    exactly as before, just on a different series.  D1 owns cycles.py conceptually; this
    change adds a substrate parameter and its wiring, nothing more."""
    # STRUCTURE basis: price when supplied (structure math is dividend-un-inflated), else
    # close (byte-identical legacy path).  MOMENTUM always runs on `close` (the TR series).
    struct = price if price is not None else close
    cyc = cycle_state(struct, high, kind)
    mtf = mtf_snapshot(close, kind)
    early = early_signals(close, cyc, mtf)
    lad = ladder_state(cyc, mtf, early, liquidity=liquidity,
                       macro_drag=macro_drag, macro_beta=macro_beta, vol_regime=vol_regime,
                       family=family)
    wo = washout(struct, cyc, vix_ctx) if cyc else {}
    if lad:
        age = signal_age(struct, lad["state"], high, kind)
        if age:
            lad.update(signal_age_fields(lad["state"], lad["score"], age))
        regime = {"regime": lad.get("regime", "neutral")}
        eq = entry_quality(close, cyc, mtf, early, regime, state=lad["state"])
        if eq:
            lad.update(entry_quality_fields(eq, state=lad["state"]))
            bc = bottom_confidence(mtf, eq, lad["state"], wo=wo)
            if bc:
                lad.update(bottom_confidence_fields(bc))
                lad["bottom_confidence"] = bc["score"]
        # multi-timeframe bottoming-alignment gate — the standout-strip SELECTION
        # filter (weekly bear-recovering/basing + 3-day fresh-from-oversold + daily just-
        # crossed/about), excluding the overextended chase, so a mid-weekly-bear falling
        # knife OR an already-run leader can no longer be surfaced as a buy card.
        # ext_pct is a 200d-DISTANCE (a structure / drawdown read) → use the structure basis.
        cc = struct.dropna()
        ext_pct = None
        if len(cc) >= 200:
            sma200 = float(cc.iloc[-200:].mean())
            if sma200:
                ext_pct = (float(cc.iloc[-1]) / sma200 - 1.0) * 100.0
        lad["alignment"] = mtf_alignment(mtf, cyc, lad, wo=wo, ext_pct=ext_pct)
    return {"cycle": cyc, "mtf": mtf, "early": early, "ladder": lad}


# ------------------------------------------------------------- calibration ----

def calibrate_ladder(price_panel: dict[str, pd.Series], fwd: int = 21,
                     step: int = 5, dd_bad: float = -0.10) -> dict:
    """Per-state forward record by ladder state. price_panel: name -> close.
    Tracks BOTH endpoint return AND forward DRAWDOWN (max adverse excursion over
    the next `fwd` days) — the drawdown lens is the honest one for risk states
    (D43: avg return is U-shaped/misleading; the path matters), and is what
    actually quantifies a counter-trend-bounce knife-catch. Heavy-ish
    (re-evaluates state along history); cached to ladder_calibration.json."""
    # extra buckets isolate the pre-emptive layer's measured edge: the same
    # BOTTOM-WATCH context with vs without an early bullish read.
    extra = ["BOTTOM WATCH +early-bull", "BOTTOM WATCH no-early"]
    # each bucket holds (endpoint_return, forward_drawdown) pairs
    buckets: dict[str, list[tuple[float, float]]] = {s: [] for s in LADDER + extra}
    for name, close in price_panel.items():
        c = close.dropna()
        if len(c) < 600:
            continue
        fwd_ret = c.pct_change(fwd).shift(-fwd)
        cv = c.to_numpy()
        # walk weekly through history; a trailing 600-day window is all the
        # cycle/indicator math needs and keeps the walk-forward tractable
        for i in range(300, len(c) - fwd, step):
            sub = c.iloc[max(0, i - 600):i + 1]
            try:
                cyc = cycle_state(sub)
                mtf = {"D": _tf_state(sub),
                       "3D": _tf_state(sub.resample("3B").last().dropna()),
                       "W": _tf_state(sub.resample("W-FRI").last().dropna())}
                early = early_signals(sub, cyc, mtf)
                st = ladder_state(cyc, mtf, early)
            except Exception:  # noqa: BLE001
                continue
            if not st.get("state"):
                continue
            v = fwd_ret.iloc[i]
            if pd.isna(v):
                continue
            # forward max-drawdown = worst close-to-low over the next `fwd` days
            dd = float(cv[i + 1: i + 1 + fwd].min() / cv[i] - 1.0)
            rec = (float(v), dd)
            buckets[st["state"]].append(rec)
            if st["state"] == "BOTTOM WATCH":
                key = "BOTTOM WATCH +early-bull" if early.get("dir") == "up" \
                    else "BOTTOM WATCH no-early"
                buckets[key].append(rec)
    out = {}
    for s, vals in buckets.items():
        if len(vals) >= 40:
            a = np.array([r for r, _ in vals])
            dds = np.array([d for _, d in vals])
            out[s] = {"n": len(a), "hit_pct": round(100 * (a > 0).mean(), 1),
                      "avg_fwd_pct": round(100 * a.mean(), 2),
                      # drawdown lens: typical dip, bad-case (10th pctile) dip,
                      # and how often the next month draws down past dd_bad
                      "dd_med_pct": round(100 * float(np.median(dds)), 2),
                      "dd_p10_pct": round(100 * float(np.percentile(dds, 10)), 2),
                      "dd_bad_pct": round(100 * float((dds <= dd_bad).mean()), 1)}
    return out
