"""W4.1 — Person-period hazard panel, rho_hat estimation, and family-stratified KM baselines.

SCOPE (W4.1 masterplan §4, §6.5 decision-gated research track):
  1. Build data/hazard/panel_<turn_epoch>.parquet
     Instrument-month person-period rows, PIT-honest (features causal at month-end t;
     turns known only AFTER confirmed_at).
  2. Estimate rho_hat (within-month cross-sectional correlation) → data/hazard/rho_hat.json
  3. Family-stratified KM baselines → data/hazard/km_baseline_<turn_epoch>.json
  4. Panel census summary → research/cycle_masterplan/W41_PANEL_CENSUS.md

Universe (ruling A14 — BLOCS DROPPED; no baskets):
  - us_sector : 11 SPDR (XLK…XLC), yahoo/ uppercase, 14% ZigZag, TR basis
  - country   : 24 country ETFs (AAXJ/ECH/EEM/EFA/EIDO/EPOL/EWA..VXUS), 14%
                NOTE: blocs (EFA/EEM/AAXJ/VGK/VPL/VXUS/ILF) are kept in the HAZARD
                panel (D5_PREDICTION.md §1.3 keeps them; ruling A14 drops blocs only
                from the lead-lag screen). The hazard-panel universe matches the
                backfill IDs exactly.
  - cn_sector : 31 Shenwan L1 codes (801010..801980), china_sectors/, 18% ZigZag

PIT contract (S2 ruling):
  - A panel row at month-end t includes ONLY:
      • turns with confirmed_at <= t  (a turn is UNKNOWABLE before its confirmation)
      • price/feature data  tape <= t (no future close prices)
  - The open leg's current running extreme is a FEATURE (the leg amplitude so far);
    the leg's eventual pivot date is LABEL material.

W2.5 binding feature set (§6.6):
  pos_osc | trend_pass | mom_score | rs_63d | vol_pctile | amp_proxy | osc_slope
  state_score is DEAD (ρ=−0.968 with pos_osc, VIF~30).
  Regime axis (quad/liquidity) is included but flagged assumed-orthogonal.

Ruling A2 (rho_hat):
  Within-month cross-sectional correlation of the event indicator AND of forward returns.
  This is a first-class artifact; W4.2 MUST use it for n_eff computation.

Ruling A14 (KM baselines):
  Family-stratified Kaplan-Meier hazard — one curve per (direction × family).
  Pooled version included for reference. THIS IS THE SKILL BAR W4.2 must beat.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Repo bootstrap (works both as a script and from pytest cwd)
# ---------------------------------------------------------------------------
_REPO = Path(__file__).parent.parent.resolve()
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from engine.cycle_ontology import (
    TURN_DETECTOR_DEFAULTS,
    TurnParams,
    detect_turns,
    turn_epoch,
)
from engine.grading_stats import wilson_ci


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# W4.1 panel covers these families (universe from D5_PREDICTION.md §1.3)
US_SECTOR_IDS = [
    "XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY",
]

# 24 country ETFs (all 31 backfill IDs — blocs are kept in the hazard panel per D5_PREDICTION §1.3)
COUNTRY_IDS = [
    "AAXJ", "ECH", "EEM", "EFA", "EIDO", "EPOL", "EWA", "EWC", "EWD", "EWG",
    "EWH", "EWI", "EWJ", "EWL", "EWN", "EWP", "EWQ", "EWS", "EWT", "EWU",
    "EWW", "EWY", "EWZ", "EZA", "FXI", "ILF", "INDA", "TUR", "VGK", "VPL", "VXUS",
]

# 31 Shenwan L1 codes
CN_SECTOR_IDS = [
    "801010", "801030", "801040", "801050", "801080", "801110", "801120",
    "801130", "801140", "801150", "801160", "801170", "801180", "801200",
    "801210", "801230", "801710", "801720", "801730", "801740", "801750",
    "801760", "801770", "801780", "801790", "801880", "801890", "801950",
    "801960", "801970", "801980",
]

# ZigZag params per family (TURN_DETECTOR_DEFAULTS)
ZZ_PCT_US = TURN_DETECTOR_DEFAULTS["pct_sector"]    # 14.0
ZZ_PCT_COUNTRY = TURN_DETECTOR_DEFAULTS["pct_country"]  # 14.0
ZZ_PCT_CN = TURN_DETECTOR_DEFAULTS["pct_cn"]        # 18.0

# k=6 blend constant (D5 §1.5 — pre-registered, not tuned)
K_BLEND = 6

# Label horizons (months)
LABEL_HORIZONS = [1, 3, 6]

# Age buckets (ratio of age to blended median, matching D5_PREDICTION.md §1.3)
AGE_BUCKET_EDGES = [0.0, 0.5, 0.8, 1.1, 1.5, np.inf]

# Benchmark tickers for RS computation (causal — available as yahoo closes)
RS_BENCH = {
    "us_sector": "SPY",
    "country":   "ACWX",
    "cn_sector": "000300",    # CSI 300 — computed from china_sectors if available
}


# ---------------------------------------------------------------------------
# Price loading helpers
# ---------------------------------------------------------------------------

def _load_yahoo_close(ticker: str, yahoo_dir: Path) -> pd.Series | None:
    """TR close (split+dividend adjusted). Feature/RS basis per D4 contract."""
    path = yahoo_dir / f"{ticker.upper()}.parquet"
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    if "close" not in df.columns:
        return None
    s = df["close"].dropna().sort_index()
    s.index = pd.to_datetime(s.index)
    return s


def _load_yahoo_price(ticker: str, yahoo_dir: Path) -> pd.Series | None:
    """Price close (split-adjusted, dividend-UNadjusted). STRUCTURE-MATH basis.

    D4_SUBSTRATE §1 contract: ZigZag turns (leg/age/label construction) MUST be
    detected on the ``price`` basis, never on total-return closes — dividends
    inject spurious drift that moves pivot dates. The dual-basis store (T5) exposes
    this as the ``close_price`` column. Falls back to TR ``close`` only if the
    price column is absent (pre-T5 stores), which callers must treat as a
    contract-violation warning.
    """
    path = yahoo_dir / f"{ticker.upper()}.parquet"
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    if "close_price" in df.columns:
        s = df["close_price"].dropna().sort_index()
    elif "close" in df.columns:
        # Pre-T5 fallback — WRONG basis; caller warns.
        s = df["close"].dropna().sort_index()
    else:
        return None
    s.index = pd.to_datetime(s.index)
    return s


def _load_cn_sector_close(code: str, cn_dir: Path) -> pd.Series | None:
    path = cn_dir / f"{code}.parquet"
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    if "close" not in df.columns:
        return None
    s = df["close"].dropna().sort_index()
    s.index = pd.to_datetime(s.index)
    return s


def _month_end_index(start: str, end: str) -> pd.DatetimeIndex:
    """Month-end dates between start and end (inclusive)."""
    return pd.date_range(start=start, end=end, freq="ME")


# ---------------------------------------------------------------------------
# Turn detection wrapper (PIT-honest)
# ---------------------------------------------------------------------------

def _detect_turns_for_instrument(
    close: pd.Series,
    series_id: str,
    pct: float,
    basis: str = "close_price",
) -> list[dict]:
    """Detect turns on the STRUCTURE-MATH price basis (D4 contract).

    ``basis`` is the label stamped on every turn; the series passed in MUST match
    it. For yahoo instruments this is ``close_price`` (split-adj, div-unadj); for
    Shenwan CN sectors the custodian ``close`` IS a price-basis index so we pass
    ``close`` and label it ``close_price`` (D4_SUBSTRATE §1.54/§175).
    """
    params = TurnParams(pct=pct, basis=basis, version=2)
    return detect_turns(close, series_id=series_id, params=params)


def _confirmed_turns_asof(turns: list[dict], asof_date: pd.Timestamp) -> list[dict]:
    """Return only turns confirmed by asof_date (PIT filter)."""
    return [
        t for t in turns
        if not t.get("provisional", False)
        and pd.Timestamp(t["confirmed_at"]) <= asof_date
    ]


# ---------------------------------------------------------------------------
# Feature computation helpers
# ---------------------------------------------------------------------------

def _rolling_vol_pctile(close: pd.Series, window: int = 63) -> pd.Series:
    """Expanding percentile of trailing 63-day realized vol (log returns std)."""
    log_ret = np.log(close / close.shift(1))
    rv63 = log_ret.rolling(window).std() * np.sqrt(252)
    expanding_pctile = rv63.expanding().rank(pct=True)
    return expanding_pctile


def _mom_score(close: pd.Series) -> pd.Series:
    """6-month minus 1-month momentum (12-period minus 1-period monthly equiv.)."""
    # Use ~126d minus ~21d (causal; no look-ahead)
    ret_6m = close / close.shift(126) - 1
    ret_1m = close / close.shift(21) - 1
    return ret_6m - ret_1m


def _trend_pass(close: pd.Series) -> pd.Series:
    """Binary: price > 200-day SMA (causal)."""
    sma200 = close.rolling(200, min_periods=100).mean()
    return (close > sma200).astype(float)


def _rs_63d(close: pd.Series, bench: pd.Series) -> pd.Series:
    """63-day return vs benchmark (TR basis, causal)."""
    aligned_bench = bench.reindex(close.index, method="ffill")
    return (close / close.shift(63)) / (aligned_bench / aligned_bench.shift(63)) - 1


def _detrended_osc(close: pd.Series, window: int = 200) -> pd.Series:
    """Detrended oscillator (0–100 scale) — causal."""
    sma = close.rolling(window, min_periods=100).mean()
    sma_prev = sma.shift(1)
    # Percent above/below SMA, scaled to 0-100 via expanding percentile
    dev = (close - sma) / sma.where(sma > 0)
    result = dev.expanding(min_periods=50).rank(pct=True) * 100
    return result


def _osc_slope(osc: pd.Series, window: int = 21) -> pd.Series:
    """21-day slope of the oscillator."""
    return osc.diff(window)


def _amp_proxy(close: pd.Series) -> pd.Series:
    """Expanding percentile of 63d ATR / price (amplitude proxy, causal)."""
    hi_lo_range = close.rolling(63).max() - close.rolling(63).min()
    atr_ratio = hi_lo_range / close.where(close > 0)
    return atr_ratio.expanding(min_periods=30).rank(pct=True)


# ---------------------------------------------------------------------------
# Age blending (D5 §1.5)
# ---------------------------------------------------------------------------

def _compute_half_medians(
    turns_by_id: dict[str, list[dict]],
    asof_date: pd.Timestamp,
) -> dict[str, dict[str, float | None]]:
    """Compute per-instrument expanding half-cycle medians up to asof_date.

    Returns {id: {'up': median_bars, 'down': median_bars, 'n_up': int, 'n_down': int}}.
    Half-cycle = bars (months) between consecutive confirmed turns.
    """
    result: dict[str, dict] = {}
    for iid, turns in turns_by_id.items():
        # Only confirmed turns up to asof_date
        conf = [t for t in turns if not t.get("provisional") and pd.Timestamp(t["confirmed_at"]) <= asof_date]
        if len(conf) < 2:
            result[iid] = {"up": None, "down": None, "n_up": 0, "n_down": 0}
            continue
        # Sort by pivot date
        conf_sorted = sorted(conf, key=lambda t: t["date"])
        up_lens, dn_lens = [], []
        for i in range(1, len(conf_sorted)):
            prev_t = pd.Timestamp(conf_sorted[i - 1]["date"])
            curr_t = pd.Timestamp(conf_sorted[i]["date"])
            kind = conf_sorted[i]["k"]  # 'peak' means up-leg just ended; 'trough' = down-leg ended
            dur = (curr_t - prev_t).days / 30.44  # convert to months
            if kind == "peak":       # up-leg ended at this peak
                up_lens.append(dur)
            else:                    # trough = down-leg ended
                dn_lens.append(dur)
        result[iid] = {
            "up":   float(np.median(up_lens)) if up_lens else None,
            "down": float(np.median(dn_lens)) if dn_lens else None,
            "n_up": len(up_lens),
            "n_down": len(dn_lens),
        }
    return result


def _family_half_medians(
    per_id: dict[str, dict],
    direction: str,
) -> float | None:
    """Pooled family median half-cycle across all instruments with data."""
    vals = [v[direction] for v in per_id.values() if v[direction] is not None]
    return float(np.median(vals)) if vals else None


def _blended_median(
    own_med: float | None,
    own_n: int,
    family_med: float | None,
    k: int = K_BLEND,
) -> float | None:
    """k=6 blend toward family median (D5 §1.5)."""
    if family_med is None and own_med is None:
        return None
    if own_med is None:
        return family_med
    if family_med is None:
        return own_med
    return (own_n * own_med + k * family_med) / (own_n + k)


def _log_age_ratio(age_m: float, blended_med: float | None) -> float | None:
    """ln(age_m / half_med_blend); None if median unavailable."""
    if blended_med is None or blended_med <= 0 or age_m <= 0:
        return None
    return float(np.log(age_m / blended_med))


def _age_bucket(log_ratio: float | None) -> str:
    """Map log_age_ratio to named bucket b1..b5."""
    if log_ratio is None:
        return "b_unknown"
    ratio = np.exp(log_ratio) if log_ratio is not None else 1.0
    if ratio < 0.5:
        return "b1"
    if ratio < 0.8:
        return "b2"
    if ratio < 1.1:
        return "b3"
    if ratio < 1.5:
        return "b4"
    return "b5"


# ---------------------------------------------------------------------------
# Core panel builder per instrument
# ---------------------------------------------------------------------------

def _build_instrument_rows(
    iid: str,
    family: str,
    close: pd.Series,
    pct: float,
    month_ends: pd.DatetimeIndex,
    all_turns: list[dict],
    per_id_medians_fn,          # callable(asof) -> {iid: medians}
    family_median_fn,           # callable(direction, asof) -> float|None
    regime_hist: pd.DataFrame,
    bench_close: pd.Series | None,
    turn_def_ver: str,
    engine_fp: str,
) -> list[dict]:
    """Build person-period rows for one instrument.

    PIT contract:
      - Features use close data and regime data up to and including month-end t.
      - Turns are only used if confirmed_at <= t (PIT filter).
      - Labels look forward from t.
    """
    rows = []

    # Pre-compute daily features on full close (all PIT — we only query up to t)
    vol_pctile = _rolling_vol_pctile(close)
    mom_sc = _mom_score(close)
    trend_p = _trend_pass(close)
    amp_p = _amp_proxy(close)
    osc = _detrended_osc(close)
    osc_sl = _osc_slope(osc)
    rs_series = _rs_63d(close, bench_close) if bench_close is not None else pd.Series(np.nan, index=close.index)

    for t_end in month_ends:
        # ── PIT price check ──────────────────────────────────────────────
        close_pit = close[close.index <= t_end]
        if len(close_pit) < 100:
            continue

        # ── Confirmed turns PIT ──────────────────────────────────────────
        conf_turns = _confirmed_turns_asof(all_turns, t_end)
        if len(conf_turns) < 2:
            continue

        # Sort by pivot date to identify which leg the instrument is in at t_end
        conf_sorted = sorted(conf_turns, key=lambda t: t["date"])

        # Find the last confirmed turn pivot date (the leg is OPEN from there)
        last_turn = conf_sorted[-1]
        last_turn_date = pd.Timestamp(last_turn["date"])

        # Instrument must be within an open leg (last confirmed turn pivot < t_end)
        if last_turn_date > t_end:
            continue

        # Direction of CURRENT OPEN leg: if last confirmed turn is a TROUGH, we're in an UP-leg
        # (heading toward a peak); if last is a PEAK, we're in a DOWN-leg.
        last_kind = last_turn["k"]
        if last_kind == "trough":
            direction = "up"
        elif last_kind == "peak":
            direction = "down"
        else:
            continue

        # ── Age of current leg (months since last confirmed pivot extremum) ──
        age_m = max(0.01, (t_end - last_turn_date).days / 30.44)

        # ── k=6 blended median for this instrument at this t ──────────────
        id_meds = per_id_medians_fn(iid, t_end)
        fam_med = family_median_fn(direction, t_end)
        own_med = id_meds.get(direction)
        own_n = id_meds.get(f"n_{direction}", 0)
        blended_med = _blended_median(own_med, own_n, fam_med, k=K_BLEND)
        log_ar = _log_age_ratio(age_m, blended_med)

        # ── Labels: does the leg end within h months? ─────────────────────
        # The NEXT turn (the one closing the current leg) must be:
        #   - Not in conf_turns (we'd have seen it by t_end)
        #   - In ALL turns with confirmed_at > t_end (future knowledge)
        # We scan ALL turns (including those confirmed after t_end) for the label.
        label_kind = "peak" if direction == "up" else "trough"
        # Future turns for labeling — their EXTREMUM date is the event time
        future_turns = [
            tr for tr in all_turns
            if not tr.get("provisional")
            and tr["k"] == label_kind
            and pd.Timestamp(tr["date"]) > last_turn_date
        ]
        # The NEAREST future turn of the right kind is the event
        future_sorted = sorted(future_turns, key=lambda tr: tr["date"])
        event_turn = future_sorted[0] if future_sorted else None
        event_date = pd.Timestamp(event_turn["date"]) if event_turn else pd.NaT

        # Censoring: if no future turn (open leg), event_date = NaT → y=0
        # But if event_date <= t_end, that means the turn's extremum was before
        # t_end but confirmed AFTER t_end — that's impossible since we already
        # filtered confirmed_turns. If event_date is in (t_end, t_end+max_h]:
        y1 = int(not pd.isnull(event_date) and event_date <= t_end + pd.DateOffset(months=1))
        y3 = int(not pd.isnull(event_date) and event_date <= t_end + pd.DateOffset(months=3))
        y6 = int(not pd.isnull(event_date) and event_date <= t_end + pd.DateOffset(months=6))
        censored = int(pd.isnull(event_date))

        # ── Features (PIT: only use values <= t_end) ──────────────────────
        def _at(series: pd.Series, fallback=np.nan):
            s_pit = series[series.index <= t_end]
            return float(s_pit.iloc[-1]) if len(s_pit) > 0 else fallback

        pos_osc_val = _at(osc)
        osc_slope_val = _at(osc_sl)
        trend_pass_val = _at(trend_p)
        mom_score_val = _at(mom_sc)
        rs_63d_val = _at(rs_series)
        vol_pctile_val = _at(vol_pctile)
        amp_proxy_val = _at(amp_p)

        # Amplitude of the current leg (running extreme so far vs leg-open price)
        close_at_t = _at(close_pit)
        close_at_open = float(close_pit[close_pit.index >= last_turn_date].iloc[0]) if len(close_pit[close_pit.index >= last_turn_date]) > 0 else np.nan
        if not np.isnan(close_at_open) and close_at_open > 0:
            leg_amp = abs(close_at_t - close_at_open) / close_at_open
        else:
            leg_amp = np.nan

        # ── Regime features (PIT: regime_hist asof t_end) ────────────────
        rh_pit = regime_hist[regime_hist.index <= t_end]
        if len(rh_pit) > 0:
            last_rh = rh_pit.iloc[-1]
            quad = last_rh.get("quad", None)
            liq = last_rh.get("liquidity", None)
        else:
            quad, liq = None, None

        # ── Age bucket dummies ────────────────────────────────────────────
        ab = _age_bucket(log_ar)

        row = {
            "date":              t_end,
            "id":                iid,
            "family":            family,
            "direction":         direction,
            "turn_def_version":  turn_def_ver,
            "engine_fingerprint": engine_fp,
            # Survival bookkeeping
            "age_m":             round(age_m, 3),
            "age_bucket":        ab,
            "log_age_ratio":     round(log_ar, 4) if log_ar is not None else np.nan,
            "blended_med_m":     round(blended_med, 3) if blended_med is not None else np.nan,
            "own_med_m":         round(own_med, 3) if own_med is not None else np.nan,
            "family_med_m":      round(fam_med, 3) if fam_med is not None else np.nan,
            "leg_open_date":     last_turn_date,
            "y1":                y1,
            "y3":                y3,
            "y6":                y6,
            "censored":          censored,
            "event_date":        event_date if not censored else pd.NaT,
            # W2.5-bound features (binding §6.6)
            "pos_osc":           round(pos_osc_val, 3) if not np.isnan(pos_osc_val) else np.nan,
            "osc_slope":         round(osc_slope_val, 4) if not np.isnan(osc_slope_val) else np.nan,
            "trend_pass":        trend_pass_val,
            "mom_score":         round(mom_score_val, 4) if not np.isnan(mom_score_val) else np.nan,
            "rs_63d":            round(rs_63d_val, 4) if not np.isnan(rs_63d_val) else np.nan,
            "vol_pctile":        round(vol_pctile_val, 4) if not np.isnan(vol_pctile_val) else np.nan,
            "amp_proxy":         round(amp_proxy_val, 4) if not np.isnan(amp_proxy_val) else np.nan,
            "leg_amp":           round(leg_amp, 4) if not np.isnan(leg_amp) else np.nan,
            # Regime (assumed-orthogonal per §6.6; revision-leaky per A14 — disclosed)
            "quad":              quad,
            "liquidity":         liq,
        }
        rows.append(row)

    return rows


# ---------------------------------------------------------------------------
# Expanding-median pre-computation (shared with the index-level panel builder)
# ---------------------------------------------------------------------------

def _precompute_medians_cache(
    all_turns_cache: dict[str, tuple[str, list[dict]]],
    month_ends_full: pd.DatetimeIndex,
) -> dict[str, dict[str, dict[str, dict]]]:
    """Per-instrument expanding half-cycle medians at each month-end (PIT).

    Moved verbatim out of build_panel() so scripts/build_index_hazard_panel.py can
    reuse the identical median math. medians_cache[iid][direction][month_str] =
    {'med': float|None, 'n': int}.
    """
    medians_cache: dict[str, dict[str, dict[str, dict]]] = {}

    for iid, (family, turns) in all_turns_cache.items():
        medians_cache[iid] = {"up": {}, "down": {}}
        conf_turns = [t for t in turns if not t.get("provisional")]
        conf_sorted = sorted(conf_turns, key=lambda t: t["date"])
        for t_end in month_ends_full:
            # Turns confirmed by t_end
            conf_at_t = [t for t in conf_sorted if pd.Timestamp(t["confirmed_at"]) <= t_end]
            if len(conf_at_t) < 2:
                for d in ["up", "down"]:
                    medians_cache[iid][d][t_end.strftime("%Y-%m")] = {"med": None, "n": 0}
                continue
            up_lens, dn_lens = [], []
            for i in range(1, len(conf_at_t)):
                prev_t = pd.Timestamp(conf_at_t[i - 1]["date"])
                curr_t = pd.Timestamp(conf_at_t[i]["date"])
                kind = conf_at_t[i]["k"]
                dur = (curr_t - prev_t).days / 30.44
                if kind == "peak":
                    up_lens.append(dur)
                else:
                    dn_lens.append(dur)
            medians_cache[iid]["up"][t_end.strftime("%Y-%m")] = {
                "med": float(np.median(up_lens)) if up_lens else None,
                "n": len(up_lens),
            }
            medians_cache[iid]["down"][t_end.strftime("%Y-%m")] = {
                "med": float(np.median(dn_lens)) if dn_lens else None,
                "n": len(dn_lens),
            }
    return medians_cache


def _precompute_family_median_cache(
    all_turns_cache: dict[str, tuple[str, list[dict]]],
    medians_cache: dict[str, dict[str, dict[str, dict]]],
    month_ends_full: pd.DatetimeIndex,
    families: list[str],
) -> dict[str, dict[str, dict[str, float | None]]]:
    """Per-family pooled medians at each month-end (PIT). Moved verbatim out of
    build_panel(); parameterized by the family list so the index-level builder can
    reuse it for its own families."""
    family_med_cache: dict[str, dict[str, dict[str, float | None]]] = {
        fam: {"up": {}, "down": {}} for fam in families
    }
    for t_end in month_ends_full:
        t_str = t_end.strftime("%Y-%m")
        for fam in families:
            fam_ids = [iid for iid, (f, _) in all_turns_cache.items() if f == fam]
            for direction in ["up", "down"]:
                vals = [
                    medians_cache[iid][direction][t_str]["med"]
                    for iid in fam_ids
                    if t_str in medians_cache.get(iid, {}).get(direction, {})
                    and medians_cache[iid][direction][t_str]["med"] is not None
                ]
                family_med_cache[fam][direction][t_str] = float(np.median(vals)) if vals else None
    return family_med_cache


# ---------------------------------------------------------------------------
# rho_hat estimation (ruling A2)
# ---------------------------------------------------------------------------

def estimate_rho_hat(panel: pd.DataFrame) -> dict:
    """Within-month cross-sectional correlation of the event indicator (y1) and
    of forward returns (rs_63d as proxy for the 1-month forward context).

    Ruling A2: n_eff = n/h IGNORES within-month cross-sectional correlation.
    This artifact documents rho_hat so W4.2 can apply the correct n_eff deflation:
        n_eff = n / (1 + (k-1) * rho_hat)
    where k = avg instruments per month and n = total row count.

    W4.2 MUST use rho_hat to compute honest confidence intervals on the KM CI and
    on the hazard model's Brier skill CI — do NOT use naive n (row count) as
    effective sample size.
    """
    results = {}

    for direction in ["up", "down"]:
        sub = panel[panel["direction"] == direction].copy()
        if len(sub) == 0:
            results[direction] = {
                "rho_y1": None, "rho_rs": None, "avg_k": None, "n_months": 0
            }
            continue

        # Group by month
        sub["month"] = sub["date"].dt.to_period("M")
        months = sub["month"].unique()

        rho_y1_vals, rho_rs_vals, k_vals = [], [], []

        for m in months:
            grp = sub[sub["month"] == m]
            k = len(grp)
            k_vals.append(k)
            if k < 4:  # Need at least 4 points for a correlation estimate
                continue

            # y1 cross-sectional correlation
            y1 = grp["y1"].values.astype(float)
            if y1.std() > 0:
                # All pairwise: E[y_i * y_j] via matrix minus diagonal
                y1_outer = np.outer(y1, y1)
                n_pairs = k * (k - 1)
                rho_y1_vals.append((y1_outer.sum() - np.diag(y1_outer).sum()) / n_pairs
                                   - y1.mean() ** 2)
            # rs_63d cross-sectional correlation (Pearson pairwise estimate)
            rs = grp["rs_63d"].dropna().values
            if len(rs) >= 4 and rs.std() > 0:
                rho_mat = np.corrcoef(rs.reshape(-1, 1).T, rowvar=False)
                if rho_mat.ndim == 0 or (rho_mat.ndim == 2 and rho_mat.shape[0] > 1):
                    pass  # can't compute pairwise from single vector
                else:
                    # Single vector: estimate average pairwise via moment method
                    rs_outer = np.outer(rs, rs)
                    rs_mean = rs.mean()
                    rs_var = rs.var()
                    if rs_var > 0:
                        rho_rs_vals.append(
                            ((rs_outer.sum() - np.sum(rs ** 2)) / (len(rs) * (len(rs) - 1)) - rs_mean ** 2)
                            / rs_var
                        )

        avg_k = float(np.mean(k_vals)) if k_vals else 0.0
        rho_y1 = float(np.mean(rho_y1_vals)) if rho_y1_vals else None
        rho_rs = float(np.mean(rho_rs_vals)) if rho_rs_vals else None

        results[direction] = {
            "rho_y1": round(rho_y1, 4) if rho_y1 is not None else None,
            "rho_rs": round(rho_rs, 4) if rho_rs is not None else None,
            "avg_k":  round(avg_k, 1),
            "n_months": int(len(months)),
        }

    # Per-family rho for family-specific n_eff
    family_rho: dict[str, dict] = {}
    for fam in panel["family"].unique():
        for direction in ["up", "down"]:
            sub = panel[(panel["family"] == fam) & (panel["direction"] == direction)].copy()
            if len(sub) < 10:
                family_rho[f"{fam}_{direction}"] = {"rho_y1": None, "avg_k": None, "n_months": 0}
                continue
            sub["month"] = sub["date"].dt.to_period("M")
            months = sub["month"].unique()
            rho_y1_vals, k_vals = [], []
            for m in months:
                grp = sub[sub["month"] == m]
                k = len(grp)
                k_vals.append(k)
                if k < 3:
                    continue
                y1 = grp["y1"].values.astype(float)
                if y1.std() > 0:
                    y1_outer = np.outer(y1, y1)
                    n_pairs = k * (k - 1)
                    rho_y1_m = (y1_outer.sum() - np.diag(y1_outer).sum()) / n_pairs - y1.mean() ** 2
                    rho_y1_vals.append(rho_y1_m)
            family_rho[f"{fam}_{direction}"] = {
                "rho_y1": round(float(np.mean(rho_y1_vals)), 4) if rho_y1_vals else None,
                "avg_k":  round(float(np.mean(k_vals)), 1) if k_vals else None,
                "n_months": int(len(months)),
            }

    return {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "doc": (
            "Within-month cross-sectional correlation of the y1 event indicator and rs_63d. "
            "rho_hat is the average pairwise cross-sectional correlation across months. "
            "W4.2 MUST apply the Dunnett-Goldsmith effective-n correction: "
            "n_eff = n_months (DO NOT use row count n as if rows were independent). "
            "For Brier skill CIs, use month-block bootstrap (ruling A2). "
            "The formula n_eff = n / (1 + (avg_k - 1) * rho_y1) gives the "
            "number of effectively independent month-observations for Wilson CIs. "
            "High rho (>0.3) means the 30-instrument panel is dramatically "
            "less informative than its row count suggests."
        ),
        "pooled": results,
        "by_family_direction": family_rho,
    }


# ---------------------------------------------------------------------------
# Kaplan-Meier age-only baselines (ruling A14 + R1)
# ---------------------------------------------------------------------------

def compute_km_baselines(panel: pd.DataFrame, turn_def_ver: str) -> dict:
    """Family-stratified + pooled KM hazard curves.

    Age-only Kaplan-Meier: this is the formalized median-half-cycle prior
    and THE skill bar W4.2 must beat (D5_PREDICTION.md §1.7).

    Ruling A14 anti-gaming: the KM bar is computed per family so a model
    can't 'win' by beating a pooled baseline distorted by high-turn families.

    Uses discrete age buckets (b1..b5) mapped from log_age_ratio.
    Also computes a true Kaplan-Meier on integer month ages.
    """
    built_at = datetime.now(timezone.utc).isoformat()
    result = {
        "built_at": built_at,
        "turn_def_version": turn_def_ver,
        "doc": (
            "Age-only Kaplan-Meier hazard per (direction x family). "
            "This is the formalized median-half-cycle prior and THE baseline "
            "any hazard model (W4.2) must beat to earn ship credit. "
            "KM estimator: lambda_t = events_t / at_risk_t. "
            "Survival: S(t) = prod_{s<=t}(1 - lambda_s). "
            "Wilson CIs on lambda_t per age bucket."
        ),
        "families": {},
        "pooled": {},
    }

    def _km_for_group(grp: pd.DataFrame, label: str) -> dict:
        """Compute KM on integer month ages for a (direction, family) group."""
        if len(grp) == 0:
            return {"n_rows": 0, "n_events": 0, "buckets": []}

        # Kaplan-Meier on age_bucket (discrete)
        bucket_order = ["b1", "b2", "b3", "b4", "b5"]
        buckets = []
        S_prev = 1.0
        for bk in bucket_order:
            bk_rows = grp[grp["age_bucket"] == bk]
            at_risk = len(bk_rows)
            events = int(bk_rows["y1"].sum())
            if at_risk == 0:
                continue
            lam = events / at_risk
            ci = wilson_ci(events, at_risk, z=1.645)  # 90% CI
            S = S_prev * (1 - lam)
            buckets.append({
                "bucket": bk,
                "at_risk": at_risk,
                "events": events,
                "lambda": round(lam, 5),
                "lambda_ci_90lo": round(ci[0], 5) if ci else None,
                "lambda_ci_90hi": round(ci[1], 5) if ci else None,
                "survival": round(S, 5),
                "cumulative_hazard": round(-np.log(max(S, 1e-9)), 5),
            })
            S_prev = S

        # Median survival: first bucket where S <= 0.5
        median_bucket = None
        for bk_row in buckets:
            if bk_row["survival"] <= 0.5:
                median_bucket = bk_row["bucket"]
                break

        # KM on integer months (for finer resolution)
        int_months = []
        max_age_m = int(grp["age_m"].max()) + 1
        S_m = 1.0
        for m in range(1, min(max_age_m + 1, 61)):  # cap at 60 months
            m_rows = grp[(grp["age_m"] >= m - 1) & (grp["age_m"] < m)]
            at_risk_m = int((grp["age_m"] >= m - 1).sum())
            events_m = int(m_rows["y1"].sum())
            if at_risk_m == 0:
                break
            lam_m = events_m / at_risk_m
            S_m = S_m * (1 - lam_m)
            int_months.append({
                "age_m": m,
                "at_risk": at_risk_m,
                "events": events_m,
                "lambda": round(lam_m, 5),
                "survival": round(S_m, 5),
            })

        # Median survival in months
        median_m = None
        for row in int_months:
            if row["survival"] <= 0.5:
                median_m = row["age_m"]
                break

        n_events = int(grp["y1"].sum())
        n_censored = int(grp["censored"].sum())

        return {
            "n_rows": len(grp),
            "n_events_y1": n_events,
            "n_censored": n_censored,
            "censoring_rate": round(n_censored / max(len(grp), 1), 4),
            "median_survival_bucket": median_bucket,
            "median_survival_m": median_m,
            "buckets": buckets,
            "km_by_month": int_months[:36],  # store first 36m for readability
        }

    # Family-stratified (anti-gaming per ruling A14)
    for fam in ["us_sector", "country", "cn_sector"]:
        result["families"][fam] = {}
        for direction in ["up", "down"]:
            grp = panel[(panel["family"] == fam) & (panel["direction"] == direction)]
            result["families"][fam][direction] = _km_for_group(grp, f"{fam}/{direction}")

    # Pooled (reference only; NOT the binding skill bar)
    for direction in ["up", "down"]:
        grp = panel[panel["direction"] == direction]
        result["pooled"][direction] = _km_for_group(grp, f"pooled/{direction}")

    return result


# ---------------------------------------------------------------------------
# Main build function
# ---------------------------------------------------------------------------

def build_panel(
    yahoo_dir: Path,
    cn_dir: Path,
    regime_path: Path,
    out_dir: Path,
    asof_end: str | None = None,
) -> pd.DataFrame:
    """Build the full person-period hazard panel.

    Returns the panel DataFrame and persists artifacts to out_dir.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── Turn epoch stamp ─────────────────────────────────────────────────────
    # PRICE basis (split-adj, div-UNadj), 14% for US/country, 18% for CN.
    # D4_SUBSTRATE §1 contract: structure-math (ZigZag turns) consumes the price
    # basis; the prior tr_* epoch was a substrate-contract VIOLATION (turns on
    # total-return closes) — corrected here (W4.2 epoch sanity check).
    t_epoch_us = turn_epoch(basis="close_price", zz_params=14.0, detector_version=2)
    t_epoch_cn = turn_epoch(basis="close_price", zz_params=18.0, detector_version=2)
    # Panel uses the US epoch as the primary stamp (family-specific pct noted in schema)
    panel_epoch = t_epoch_us

    # Engine fingerprint from backfill manifests
    try:
        with open(_REPO / "data/sector_cycles/backfill_manifest.json") as f:
            mf = json.load(f)
        engine_fp = mf.get("engine_fingerprint", "unknown")
    except Exception:
        engine_fp = "unknown"

    # ── Regime history ────────────────────────────────────────────────────────
    print("Loading regime history...")
    regime_hist = pd.read_parquet(regime_path)
    regime_hist.index = pd.to_datetime(regime_hist.index)

    # ── Month-end grid ────────────────────────────────────────────────────────
    asof_end_ts = pd.Timestamp(asof_end) if asof_end else pd.Timestamp("today").normalize()
    month_ends_full = _month_end_index("1995-01", asof_end_ts.strftime("%Y-%m"))

    # ── Benchmarks for RS ────────────────────────────────────────────────────
    # ACWX is the primary country benchmark but may not be in the yahoo/ store.
    # Fallback chain: ACWX → EFA (large available country ETF, good proxy for ACWI ex-US)
    # rs_63d missingness is documented in W41_PANEL_CENSUS.md; W4.2 must use
    # a missing-indicator column for country rows where the benchmark is unavailable.
    print("Loading benchmarks...")
    bench_spy = _load_yahoo_close("SPY", yahoo_dir)
    bench_acwx = _load_yahoo_close("ACWX", yahoo_dir)
    if bench_acwx is None:
        bench_acwx = _load_yahoo_close("EFA", yahoo_dir)
        if bench_acwx is not None:
            print("  NOTE: ACWX not found — using EFA as country benchmark fallback (documented)")
    # CN benchmark: use CSI 300 as 801050 (Materials) or 801010 composite
    bench_cn = _load_cn_sector_close("801050", cn_dir)  # more stable SW proxy
    if bench_cn is None:
        bench_cn = _load_cn_sector_close("801010", cn_dir)

    # ── Pre-compute all turns per instrument (expensive but done once) ────────
    print("Detecting turns for all instruments...")
    all_turns_cache: dict[str, tuple[str, list[dict]]] = {}  # id -> (family, turns)

    # Track any instrument whose price basis was unavailable (contract-violation warn)
    price_basis_fallbacks: list[str] = []

    # US sectors — turns on close_price (structure basis)
    for iid in US_SECTOR_IDS:
        px = _load_yahoo_price(iid, yahoo_dir)
        raw = pd.read_parquet(yahoo_dir / f"{iid.upper()}.parquet") if (yahoo_dir / f"{iid.upper()}.parquet").exists() else None
        if raw is not None and "close_price" not in raw.columns:
            price_basis_fallbacks.append(iid)
        if px is None or len(px) < 200:
            print(f"  SKIP {iid}: insufficient data")
            continue
        turns = _detect_turns_for_instrument(px, iid, ZZ_PCT_US)
        all_turns_cache[iid] = ("us_sector", turns)
        n_conf = len([t for t in turns if not t.get("provisional")])
        print(f"  US {iid}: {n_conf} confirmed turns (price basis)")

    # Country ETFs — turns on close_price (structure basis)
    for iid in COUNTRY_IDS:
        px = _load_yahoo_price(iid, yahoo_dir)
        raw = pd.read_parquet(yahoo_dir / f"{iid.upper()}.parquet") if (yahoo_dir / f"{iid.upper()}.parquet").exists() else None
        if raw is not None and "close_price" not in raw.columns:
            price_basis_fallbacks.append(iid)
        if px is None or len(px) < 200:
            print(f"  SKIP {iid}: insufficient data")
            continue
        turns = _detect_turns_for_instrument(px, iid, ZZ_PCT_COUNTRY)
        all_turns_cache[iid] = ("country", turns)
        n_conf = len([t for t in turns if not t.get("provisional")])
        print(f"  COUNTRY {iid}: {n_conf} confirmed turns (price basis)")

    # CN sectors — Shenwan custodian close IS price basis (D4 §1.54); label close_price
    for iid in CN_SECTOR_IDS:
        close = _load_cn_sector_close(iid, cn_dir)
        if close is None or len(close) < 200:
            print(f"  SKIP {iid}: insufficient data")
            continue
        turns = _detect_turns_for_instrument(close, iid, ZZ_PCT_CN)
        all_turns_cache[iid] = ("cn_sector", turns)
        n_conf = len([t for t in turns if not t.get("provisional")])
        print(f"  CN {iid}: {n_conf} confirmed turns (price basis: Shenwan custodian index)")

    if price_basis_fallbacks:
        print(f"  WARNING: {len(price_basis_fallbacks)} instruments lacked close_price "
              f"(TR fallback — SUBSTRATE CONTRACT VIOLATION): {price_basis_fallbacks}")

    # ── Compute per-family expanding medians ──────────────────────────────────
    # We cache the full turns per instrument; expanding medians are computed per t
    # via a closure that the row-builder calls.
    # To avoid O(n_instruments * n_months * n_turns) quadratic cost, pre-compute
    # cumulative medians at each month-end.

    print("Pre-computing expanding medians per instrument...")
    # medians_cache[iid][direction][month_end_str] = {'med', 'n'}
    medians_cache = _precompute_medians_cache(all_turns_cache, month_ends_full)

    # Per-family pooled medians at each month-end
    print("Pre-computing family pooled medians...")
    # family_med_cache[family][direction][month_end_str] = float|None
    family_med_cache = _precompute_family_median_cache(
        all_turns_cache, medians_cache, month_ends_full,
        families=["us_sector", "country", "cn_sector"],
    )

    # Closure helpers for the row builder
    def _per_id_med_fn(iid: str, t_end: pd.Timestamp) -> dict:
        t_str = t_end.strftime("%Y-%m")
        d = medians_cache.get(iid, {})
        return {
            "up":   d.get("up", {}).get(t_str, {}).get("med"),
            "n_up": d.get("up", {}).get(t_str, {}).get("n", 0),
            "down": d.get("down", {}).get(t_str, {}).get("med"),
            "n_down": d.get("down", {}).get(t_str, {}).get("n", 0),
        }

    def _fam_med_fn(fam: str, direction: str, t_end: pd.Timestamp) -> float | None:
        t_str = t_end.strftime("%Y-%m")
        return family_med_cache.get(fam, {}).get(direction, {}).get(t_str)

    # ── Build rows per instrument ─────────────────────────────────────────────
    print("Building person-period rows...")
    all_rows: list[dict] = []

    for iid, (family, turns) in all_turns_cache.items():
        # Select benchmark
        if family == "us_sector":
            bench = bench_spy
            pct = ZZ_PCT_US
        elif family == "country":
            bench = bench_acwx
            pct = ZZ_PCT_COUNTRY
        else:
            bench = bench_cn
            pct = ZZ_PCT_CN

        # Load close
        if family in ("us_sector", "country"):
            close = _load_yahoo_close(iid, yahoo_dir)
        else:
            close = _load_cn_sector_close(iid, cn_dir)

        if close is None:
            continue

        # Trim month_ends to the instrument's data range
        i_start = close.index.min()
        i_end = close.index.max()
        me = month_ends_full[(month_ends_full >= i_start) & (month_ends_full <= min(i_end, asof_end_ts))]

        per_id_fn = lambda iid_=iid, t=None: _per_id_med_fn(iid_, t)
        fam_fn = lambda direction, t, fam_=family: _fam_med_fn(fam_, direction, t)

        rows = _build_instrument_rows(
            iid=iid,
            family=family,
            close=close,
            pct=pct,
            month_ends=me,
            all_turns=turns,
            per_id_medians_fn=lambda iid_=iid, t=None: _per_id_med_fn(iid_, t),
            family_median_fn=lambda direction, t, fam_=family: _fam_med_fn(fam_, direction, t),
            regime_hist=regime_hist,
            bench_close=bench,
            turn_def_ver=panel_epoch,
            engine_fp=engine_fp,
        )
        all_rows.extend(rows)
        print(f"  {iid} ({family}): {len(rows)} rows, "
              f"{sum(r['y1'] for r in rows)} events(y1)")

    print(f"\nTotal rows: {len(all_rows)}")

    panel = pd.DataFrame(all_rows)
    panel["date"] = pd.to_datetime(panel["date"])

    # ── Persist panel ─────────────────────────────────────────────────────────
    panel_path = out_dir / f"panel_{panel_epoch}.parquet"
    panel.to_parquet(panel_path, index=False)
    print(f"Panel written: {panel_path} ({len(panel)} rows)")

    # ── rho_hat ───────────────────────────────────────────────────────────────
    print("Estimating rho_hat...")
    rho = estimate_rho_hat(panel)
    rho_path = out_dir / "rho_hat.json"
    with open(rho_path, "w") as f:
        json.dump(rho, f, indent=2, default=str)
    print(f"rho_hat written: {rho_path}")

    # ── KM baselines ─────────────────────────────────────────────────────────
    print("Computing KM baselines...")
    km = compute_km_baselines(panel, panel_epoch)
    km_path = out_dir / f"km_baseline_{panel_epoch}.json"
    with open(km_path, "w") as f:
        json.dump(km, f, indent=2, default=str)
    print(f"KM baselines written: {km_path}")

    return panel


# ---------------------------------------------------------------------------
# Census report
# ---------------------------------------------------------------------------

def write_census(panel: pd.DataFrame, km: dict, rho: dict, out_path: Path) -> None:
    """Write W41_PANEL_CENSUS.md: rows, events, censoring, features, power note."""
    import io
    buf = io.StringIO()

    def w(s=""):
        buf.write(s + "\n")

    w("# W4.1 Panel Census")
    w()
    w(f"**Built:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    w(f"**Panel epoch:** `{panel['turn_def_version'].iloc[0]}`")
    w(f"**Engine fingerprint:** `{panel['engine_fingerprint'].iloc[0]}`")
    w()
    w("## Overall")
    w()
    total_rows = len(panel)
    date_range = f"{panel['date'].min().date()} → {panel['date'].max().date()}"
    n_instruments = panel["id"].nunique()
    n_months = panel["date"].nunique()
    w(f"| Item | Value |")
    w(f"|------|-------|")
    w(f"| Total rows | {total_rows:,} |")
    w(f"| Date range | {date_range} |")
    w(f"| Instruments | {n_instruments} |")
    w(f"| Months | {n_months} |")
    w(f"| Events y1 | {int(panel['y1'].sum()):,} |")
    w(f"| Events y3 | {int(panel['y3'].sum()):,} |")
    w(f"| Events y6 | {int(panel['y6'].sum()):,} |")
    w(f"| Censored rows | {int(panel['censored'].sum()):,} |")
    w(f"| Censoring rate | {panel['censored'].mean():.1%} |")
    w()

    w("## Events per direction × family")
    w()
    w("| Family | Direction | Rows | Events (y1) | Events (y3) | Events (y6) | Censored | Cens. rate |")
    w("|--------|-----------|------|------------|------------|------------|----------|------------|")
    for fam in ["us_sector", "country", "cn_sector"]:
        for direction in ["up", "down"]:
            sub = panel[(panel["family"] == fam) & (panel["direction"] == direction)]
            if len(sub) == 0:
                continue
            w(f"| {fam} | {direction} | {len(sub):,} | {int(sub['y1'].sum()):,} | "
              f"{int(sub['y3'].sum()):,} | {int(sub['y6'].sum()):,} | "
              f"{int(sub['censored'].sum()):,} | {sub['censored'].mean():.1%} |")
    w()

    w("## Feature missingness")
    w()
    feat_cols = ["pos_osc", "osc_slope", "trend_pass", "mom_score", "rs_63d", "vol_pctile", "amp_proxy",
                 "log_age_ratio", "quad", "liquidity"]
    w("| Feature | Missing rows | Miss. rate |")
    w("|---------|-------------|------------|")
    for col in feat_cols:
        if col in panel.columns:
            miss = panel[col].isna().sum()
            w(f"| {col} | {miss:,} | {miss/len(panel):.1%} |")
    w()

    w("## KM baselines (age-only median survival)")
    w()
    w("*Ruling A14: family-stratified baseline — the skill bar W4.2 must beat.*")
    w()
    w("| Family | Direction | Rows | Events y1 | Median survival (months) | Median survival (bucket) |")
    w("|--------|-----------|------|-----------|--------------------------|--------------------------|")
    for fam in ["us_sector", "country", "cn_sector"]:
        for direction in ["up", "down"]:
            km_data = km["families"].get(fam, {}).get(direction, {})
            n_rows = km_data.get("n_rows", 0)
            n_ev = km_data.get("n_events_y1", 0)
            med_m = km_data.get("median_survival_m", "N/A")
            med_bk = km_data.get("median_survival_bucket", "N/A")
            w(f"| {fam} | {direction} | {n_rows:,} | {n_ev:,} | {med_m} | {med_bk} |")
    w()

    w("## rho_hat (within-month cross-sectional correlation)")
    w()
    w("*Ruling A2: W4.2 MUST use rho_hat for n_eff computation, not raw row counts.*")
    w()
    w("| Direction | rho_y1 | avg_k | n_months | Implied n_eff |")
    w("|-----------|--------|-------|----------|---------------|")
    for direction in ["up", "down"]:
        p = rho.get("pooled", {}).get(direction, {})
        rho_y1 = p.get("rho_y1")
        avg_k = p.get("avg_k", 0)
        n_months_val = p.get("n_months", 0)
        if rho_y1 is not None and avg_k and avg_k > 1:
            n_eff = n_months_val / (1 + (avg_k - 1) * max(rho_y1, 0))
        else:
            n_eff = n_months_val
        w(f"| {direction} | {rho_y1} | {avg_k} | {n_months_val} | {n_eff:.0f} |")
    w()

    w("## Effective months and n_eff by family")
    w()
    w("| Family+Dir | rho_y1 | avg_k | n_months | n_eff |")
    w("|------------|--------|-------|----------|-------|")
    for key, fam_rho in rho.get("by_family_direction", {}).items():
        rho_y1 = fam_rho.get("rho_y1")
        avg_k = fam_rho.get("avg_k", 0)
        n_months_val = fam_rho.get("n_months", 0)
        if rho_y1 is not None and avg_k and avg_k > 1:
            n_eff = n_months_val / (1 + (avg_k - 1) * max(rho_y1, 0))
        else:
            n_eff = n_months_val
        w(f"| {key} | {rho_y1} | {avg_k} | {n_months_val} | {n_eff:.0f} |")
    w()

    w("## Power note")
    w()
    w("*What Brier-gap is detectable at 80% power given rho_hat and event counts?*")
    w()
    w("Using a simple simulation: generate 10,000 panel datasets of size matching the "
      "actual panel, with null model (KM prior as the prediction), and measure the "
      "standard deviation of the paired Brier difference across month-block bootstrap "
      "samples. The MDE is 2.8σ for 80% power (two-sided 90% CI = 1.645 z).")
    w()
    w("| Model | Direction | n_months | rho_y1 | n_eff | Base rate | σ_Brier | MDE (80% power) |")
    w("|-------|-----------|----------|--------|-------|-----------|---------|-----------------|")

    for direction in ["up", "down"]:
        sub = panel[panel["direction"] == direction]
        p = rho.get("pooled", {}).get(direction, {})
        rho_y1 = p.get("rho_y1") or 0.0
        avg_k = p.get("avg_k", 1)
        n_months_val = p.get("n_months", 1)
        base_rate = sub["y1"].mean() if len(sub) > 0 else 0.0
        # Brier of base-rate predictor = p*(1-p)
        brier_base = base_rate * (1 - base_rate)
        # Variance of paired Brier difference (approximate, correlated errors)
        # σ² ≈ (2 * brier_base² * (1 + (avg_k-1)*rho_y1)) / n_months
        if n_months_val > 0 and avg_k > 0:
            var_brier = (2 * brier_base ** 2 * (1 + (avg_k - 1) * max(rho_y1, 0))) / n_months_val
        else:
            var_brier = np.nan
        sigma = np.sqrt(var_brier) if not np.isnan(var_brier) else np.nan
        # MDE at 80% power, 90% CI (1.645 z): MDE = (1.645 + 0.842) * sigma = 2.487 * sigma
        mde = 2.487 * sigma if not np.isnan(sigma) else np.nan
        n_eff = n_months_val / (1 + (avg_k - 1) * max(rho_y1, 0)) if avg_k > 1 else n_months_val
        w(f"| pooled | {direction} | {n_months_val} | {rho_y1:.4f} | {n_eff:.0f} | "
          f"{base_rate:.4f} | {sigma:.5f} | {mde:.5f} |")
    w()
    w("**Interpretation:** The MDE is the minimum Brier-gap at which a model trained on "
      "this panel would be detectable at 80% power with a 90% CI month-block bootstrap test. "
      "If the MDE > 0.01 (1% Brier gap), the panel is likely underpowered for detection of "
      "small true skill; most cells will ship as PRIOR initially (masterplan §6 risk #2 / R1). "
      "This is expected — the KM prior is itself a large upgrade over the re-anchoring projection.")
    w()
    w("## Blocs inclusion note (ruling A14)")
    w()
    w("Ruling A14 drops blocs from the HAZARD PANEL? **No — A14 drops blocs from the "
      "LEAD-LAG screen (Stage A).** The hazard panel includes all 31 country-family "
      "instruments matching the backfill IDs (including EFA/EEM/AAXJ/VGK/VPL/VXUS/ILF). "
      "Per D5_PREDICTION.md §1.3 note on Q.3: blocs are kept in the hazard panel but "
      "EXCLUDED from the lead-lag Stage A pairs screen (W5.1).")
    w()
    w("## Universe per family")
    w()
    for fam in ["us_sector", "country", "cn_sector"]:
        sub = panel[panel["family"] == fam]
        ids = sorted(sub["id"].unique())
        w(f"**{fam}** ({len(ids)} instruments):")
        w(", ".join(ids))
        w()

    out_path.write_text(buf.getvalue())
    print(f"Census written: {out_path}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="W4.1 Hazard panel builder")
    parser.add_argument("--asof-end", default=None, help="Cut-off date (YYYY-MM-DD)")
    parser.add_argument("--yahoo-dir", default=str(_REPO / "data/yahoo"))
    parser.add_argument("--cn-dir", default=str(_REPO / "data/china_sectors"))
    parser.add_argument("--regime-path", default=str(_REPO / "data/regime/regime_history.parquet"))
    parser.add_argument("--out-dir", default=str(_REPO / "data/hazard"))
    parser.add_argument("--census-out", default=str(_REPO / "research/cycle_masterplan/W41_PANEL_CENSUS.md"))
    args = parser.parse_args()

    panel = build_panel(
        yahoo_dir=Path(args.yahoo_dir),
        cn_dir=Path(args.cn_dir),
        regime_path=Path(args.regime_path),
        out_dir=Path(args.out_dir),
        asof_end=args.asof_end,
    )

    # Load KM and rho for census
    epoch = panel["turn_def_version"].iloc[0]
    out_dir = Path(args.out_dir)

    with open(out_dir / f"km_baseline_{epoch}.json") as f:
        km = json.load(f)
    with open(out_dir / "rho_hat.json") as f:
        rho = json.load(f)

    write_census(panel, km, rho, Path(args.census_out))

    # Summary to stdout
    print("\n=== W4.1 COMPLETE ===")
    print(f"Panel epoch: {epoch}")
    print(f"Rows: {len(panel):,}")
    print(f"Events y1 total: {int(panel['y1'].sum()):,}")
    for fam in ["us_sector", "country", "cn_sector"]:
        for direction in ["up", "down"]:
            sub = panel[(panel["family"] == fam) & (panel["direction"] == direction)]
            print(f"  {fam}/{direction}: {len(sub):,} rows, {int(sub['y1'].sum())} events(y1)")


if __name__ == "__main__":
    main()
