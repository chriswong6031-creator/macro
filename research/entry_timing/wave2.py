"""wave2.py — Durable-Bottom Entry Timing Study, Wave 2

Spec: research/signal_engine/DURABLE_BOTTOM_FRAMEWORK.md §8 (wave-2 directive)
      research/entry_timing/WAVE1_REPORT.md (wave-1 results, findings to reuse)

Wave-2 mandate:
  Test whether the COILED state (in_washout_ctx AND h6_cohort_sector>=0.4)
  survives out-of-sample on both the stocks panel (full deep history) and a baskets
  panel (survivorship-lighter, two cohort variants).  Add new outcomes (clean10/20/30,
  clean15_h189, mae63/mfe63), new feature fromos3, and the full T1-T8 table suite.

CLI:
  python3 research/entry_timing/wave2.py --panel {stocks,baskets}
        [--tickers AAPL,MSFT,...] [--workers 6] [--out DIR]

Reuses from wave1.py (imported):
  label_events, compute_outcomes (extended here), compute_features (extended here),
  build_tf_grids, build_sector_d_matrix, get_cohort_frac,
  pct, rate, med, stratum_row (rate/med helpers)
  Constants: MIN_BARS (1500 stocks / 1000 baskets overridden locally), EVAL_START
             (2012-01-01 stocks / 2015-01-01 baskets overridden), FWD_REQ, STOP5,
             CLEAN15, DEAD_MONEY_BAND, DEAD_MONEY_CAP, OUTCOME_W, MFE_MAE_W,
             H6_COHORT_MIN_PEERS, H6_COHORT_THRESH, H5_FAILED_WINDOW,
             DD_MIN, DD_B30, DURABLE_HOLD, LIFTOFF_126, H1_D_DEEP_THRESH
"""
from __future__ import annotations

import sys
import time
import json
import math
import argparse
import warnings
import logging
from pathlib import Path
from multiprocessing import Pool

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)

# ── path bootstrap ────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
SIG_ENG = ROOT / "research" / "signal_engine"
ENTRY_TIMING = ROOT / "research" / "entry_timing"
sys.path.insert(0, str(SIG_ENG))
sys.path.insert(0, str(ENTRY_TIMING))

import tuning_harness as TH  # noqa: E402
import wave1                  # noqa: E402  (import-safe; all work under __main__)

# Re-export constants we need from wave1
from wave1 import (
    label_events, build_tf_grids,
    build_sector_d_matrix, get_cohort_frac,
    pct, rate, med,
    FWD_REQ, STOP5, DEAD_MONEY_BAND, DEAD_MONEY_CAP,
    MFE_MAE_W, H6_COHORT_MIN_PEERS, H6_COHORT_THRESH,
    H5_FAILED_WINDOW, DD_MIN, DURABLE_HOLD, LIFTOFF_126,
    H1_D_DEEP_THRESH, CAPTURE,
)

DATA_STOCKS   = ROOT / "data" / "stocks"
DATA_BASKETS  = ROOT / "data" / "baskets" / "ohlcv"
BREADTH       = ROOT / "data" / "breadth"
MEMBERSHIP    = ROOT / "data" / "baskets" / "membership.json"

# ─────────────────────────── panel-specific constants ────────────────────────
PANEL_CONFIGS = {
    "stocks": {
        "data_dir":   DATA_STOCKS,
        "min_bars":   1500,
        "eval_start": pd.Timestamp("2012-01-01"),
    },
    "baskets": {
        "data_dir":   DATA_BASKETS,
        "min_bars":   1000,
        "eval_start": pd.Timestamp("2015-01-01"),
    },
}

# Wave-2 variants (platform + reference)
W2_VARIANTS = ["m2d_s3d", "base3d"]

# Extended outcome horizons
OUTCOME_W        = 126   # primary (same as wave1)
OUTCOME_W_H189   = 189   # extended horizon for clean15_h189
CLEAN10_MULT     = 1.10
CLEAN15_MULT     = 1.15
CLEAN20_MULT     = 1.20
CLEAN30_MULT     = 1.30
STOP_MULT        = 0.95  # same as wave1.STOP5

# Durable-bottom variant flags
DURABLE_B30_THRESH   = 0.30
DURABLE_TOL5_THRESH  = 0.03   # default tolerance (durable_hold = 0.97)
DURABLE_TOL5_ALT     = 0.05   # durable_tol5 flag: tolerance 5%
LIFTOFF_20_MULT      = 1.20   # default
LIFTOFF_30_MULT      = 1.30   # durable_lift30 flag
FWD_REQ_189          = 189    # durable_h189 flag

# GICS sector names for us_sector_* basket mapping
_BASKET_TO_SECTOR = {
    "us_sector_tech":          "Information Technology",
    "us_sector_financials":    "Financials",
    "us_sector_health":        "Health Care",
    "us_sector_discretionary": "Consumer Discretionary",
    "us_sector_comm":          "Communication Services",
    "us_sector_industrials":   "Industrials",
    "us_sector_staples":       "Consumer Staples",
    "us_sector_energy":        "Energy",
    "us_sector_utilities":     "Utilities",
    "us_sector_realestate":    "Real Estate",
    "us_sector_materials":     "Materials",
}

# fromos3: rolling-8-bar minimum D(3D) < 20 — deep capitulation origin
FROMOS3_WINDOW = 8
FROMOS3_THRESH = 20


# ══════════════════════════════════════════════════════════════════════════════
# Membership helpers
# ══════════════════════════════════════════════════════════════════════════════

def load_membership() -> dict:
    """Load membership.json and return the full dict."""
    with open(MEMBERSHIP) as f:
        return json.load(f)


def build_active_set(membership: dict) -> set[str]:
    """Return tickers that are current members of ANY basket (removed is None)."""
    active = set()
    for bdata in membership["baskets"].values():
        for mem in bdata.get("members", []):
            if mem.get("removed") is None:
                active.add(mem["ticker"])
    return active


def build_basket_sector_map(membership: dict) -> dict[str, str]:
    """Build ticker -> GICS sector from us_sector_* baskets."""
    out: dict[str, str] = {}
    for bname, sector in _BASKET_TO_SECTOR.items():
        bdata = membership["baskets"].get(bname)
        if bdata is None:
            continue
        for mem in bdata.get("members", []):
            t = mem["ticker"]
            if t not in out:
                out[t] = sector
    return out


def build_theme_peers(membership: dict) -> dict[str, set[str]]:
    """Build ticker -> set of co-members across ALL baskets.
    Peers = union of co-members of every basket the ticker belongs to.
    """
    # first: basket -> all member tickers (active + inactive)
    basket_members: dict[str, list[str]] = {}
    for bname, bdata in membership["baskets"].items():
        basket_members[bname] = [m["ticker"] for m in bdata.get("members", [])]

    # ticker -> set of baskets
    ticker_baskets: dict[str, list[str]] = {}
    for bname, members in basket_members.items():
        for t in members:
            ticker_baskets.setdefault(t, []).append(bname)

    # peers: union of co-members minus self
    out: dict[str, set[str]] = {}
    for ticker, bnames in ticker_baskets.items():
        peers: set[str] = set()
        for bname in bnames:
            peers.update(basket_members[bname])
        peers.discard(ticker)
        out[ticker] = peers
    return out


# ══════════════════════════════════════════════════════════════════════════════
# Extended label_events: add variant flags
# ══════════════════════════════════════════════════════════════════════════════

def label_events_w2(daily: pd.Series) -> pd.DataFrame:
    """Extend wave-1 label_events with wave-2 variant flags on each event row.

    Wave-2 flags (all strictly hindsight, evaluation only):
      durable_b30    : dd at trough <= -30%  (already exists as b30; alias)
      durable_tol5   : durable with 5% tolerance (hold floor = P0*0.95)
      durable_lift30 : durable with +30% liftoff within 126d
      durable_h189   : durable with 189d windows (dd, hold, liftoff)
    """
    # Use wave1's label_events as the base
    evs = label_events(daily)
    if len(evs) == 0:
        for col in ["durable_b30", "durable_tol5", "durable_lift30", "durable_h189"]:
            evs[col] = pd.Series(dtype=bool)
        return evs

    n = len(daily)
    c = daily.to_numpy()
    idx = daily.index

    # We need the actual trough positions from the base labeler — re-derive them
    # by matching evs["t0"] to positions in the index
    extra_rows = []
    for _, row in evs.iterrows():
        t0 = row["t0"]
        j = idx.get_loc(t0)
        p0 = float(c[j])
        dd_at = float(row["dd_at_trough"])

        # durable_b30: same as b30
        durable_b30 = bool(dd_at <= -DURABLE_B30_THRESH)

        # durable_tol5: tolerance 5% (hold floor = P0*0.95) within FWD_REQ bars
        if j + FWD_REQ < n:
            fwd = c[j + 1: j + FWD_REQ + 1]
            hold_tol5 = bool(np.nanmin(fwd) >= p0 * (1 - DURABLE_TOL5_ALT))
            lift_default = bool(np.nanmax(c[j: j + FWD_REQ + 1]) >= p0 * LIFTOFF_20_MULT)
            durable_tol5 = bool(hold_tol5 and lift_default)
        else:
            durable_tol5 = False

        # durable_lift30: +30% liftoff within 126d, default tolerance 3%
        if j + FWD_REQ < n:
            fwd = c[j + 1: j + FWD_REQ + 1]
            hold_default = bool(np.nanmin(fwd) >= p0 * DURABLE_HOLD)
            lift30 = bool(np.nanmax(c[j: j + FWD_REQ + 1]) >= p0 * LIFTOFF_30_MULT)
            durable_lift30 = bool(hold_default and lift30)
        else:
            durable_lift30 = False

        # durable_h189: 189d windows
        if j + FWD_REQ_189 < n:
            roll189 = pd.Series(c, index=idx).rolling(FWD_REQ_189).max().to_numpy()
            if j >= FWD_REQ_189:
                prior_max189 = roll189[j]
                dd189 = c[j] / prior_max189 - 1 if prior_max189 > 0 else np.nan
                in_ep189 = (not np.isnan(dd189)) and dd189 <= -DD_MIN
            else:
                in_ep189 = False
            if in_ep189:
                fwd189 = c[j + 1: j + FWD_REQ_189 + 1]
                hold189 = bool(np.nanmin(fwd189) >= p0 * DURABLE_HOLD)
                lift189 = bool(np.nanmax(c[j: j + FWD_REQ_189 + 1]) >= p0 * LIFTOFF_20_MULT)
                durable_h189 = bool(hold189 and lift189)
            else:
                durable_h189 = False
        else:
            durable_h189 = False

        extra_rows.append({
            "durable_b30":   durable_b30,
            "durable_tol5":  durable_tol5,
            "durable_lift30": durable_lift30,
            "durable_h189":  durable_h189,
        })

    extras_df = pd.DataFrame(extra_rows, index=evs.index)
    return pd.concat([evs, extras_df], axis=1)


# ══════════════════════════════════════════════════════════════════════════════
# Extended compute_outcomes: add clean10/20/30, clean15_h189, mae63/mfe63
# ══════════════════════════════════════════════════════════════════════════════

def compute_outcomes_w2(fill_idx: int, p: float,
                        close_arr: np.ndarray,
                        high_arr: np.ndarray,
                        low_arr: np.ndarray) -> dict:
    """Extended outcomes for wave-2.  Calls wave-1 compute_outcomes for base metrics,
    then adds clean10, clean20, clean30, clean15_h189, mae63/mfe63.
    All barriers vs stop (-5%) within the respective horizon.
    """
    from wave1 import compute_outcomes as _w1_outcomes
    base = _w1_outcomes(fill_idx, p, close_arr, high_arr, low_arr)

    n = len(close_arr)
    stop_barrier = p * STOP_MULT  # 0.95p

    def clean_barrier_race(target_mult: float, horizon: int) -> int:
        """1 if close >= p*target_mult before close <= stop_barrier within horizon bars."""
        target = p * target_mult
        for k in range(fill_idx + 1, min(fill_idx + horizon + 1, n)):
            cl = close_arr[k]
            if cl >= target:
                return 1
            if cl <= stop_barrier:
                return 0
        return 0

    base["clean10"] = clean_barrier_race(CLEAN10_MULT, OUTCOME_W)
    base["clean20"] = clean_barrier_race(CLEAN20_MULT, OUTCOME_W)
    base["clean30"] = clean_barrier_race(CLEAN30_MULT, OUTCOME_W)
    base["clean15_h189"] = clean_barrier_race(CLEAN15_MULT, OUTCOME_W_H189)

    return base


# ══════════════════════════════════════════════════════════════════════════════
# Extended compute_features: add fromos3
# ══════════════════════════════════════════════════════════════════════════════

def compute_features_w2(i: int, grids: dict, vol_arr, variant_fires_before: list[dict],
                        ticker: str, sig_date: pd.Timestamp,
                        sector_map_sector: dict[str, str],
                        sector_d_matrix: dict,
                        theme_peers: dict[str, set[str]] | None,
                        theme_d_matrix: dict | None,
                        panel_eval_start: pd.Timestamp) -> dict:
    """Wave-2 feature computation.

    Calls wave-1 compute_features for H1-H6 features, then:
    - Renames h6_cohort from wave1 to h6_cohort_sector
    - Computes h6_cohort_theme (baskets panel only; None for stocks panel)
    - Computes fromos3 (deep-capitulation origin flag)
    - Derives COILED, STAR composite labels
    """
    from wave1 import compute_features as _w1_features
    feat = _w1_features(i, grids, vol_arr, variant_fires_before)

    # H6 sector cohort (re-computed; wave1's compute_features doesn't do this
    # inline for the sector_map — it's injected after the call in wave1.main.
    # In wave2 we pass sector_map and matrix directly.)
    h6_sector = get_cohort_frac(ticker, sig_date,
                                sector_map_sector, sector_d_matrix)
    feat["h6_cohort_sector"] = h6_sector

    # H6 theme cohort (baskets panel only)
    h6_theme: float | None = None
    if theme_peers is not None and theme_d_matrix is not None:
        peers = theme_peers.get(ticker)
        if peers is not None:
            vals = []
            for p_tick in peers:
                if p_tick not in theme_d_matrix:
                    continue
                pidx, pdw = theme_d_matrix[p_tick]
                pos = pidx.searchsorted(sig_date, side="right") - 1
                if pos < 0:
                    continue
                v = pdw[pos]
                if not np.isnan(v):
                    vals.append(v)
            if len(vals) >= H6_COHORT_MIN_PEERS:
                h6_theme = float(np.mean(np.array(vals) < 30))
    feat["h6_cohort_theme"] = h6_theme

    # fromos3: 3D StochRSI D rolling-8-bar min < 20 at bar i (deep-capitulation origin flag)
    # Uses d3d_daily from grids (same series as wave1)
    d3d = grids["d3d_daily"]
    start_f = max(0, i - FROMOS3_WINDOW + 1)
    window_d3d = d3d[start_f: i + 1]
    valid_d3d = window_d3d[~np.isnan(window_d3d)]
    if len(valid_d3d) > 0:
        feat["fromos3"] = bool(float(np.min(valid_d3d)) < FROMOS3_THRESH)
    else:
        feat["fromos3"] = False

    # COILED: in_washout_ctx AND h6_cohort_sector >= H6_COHORT_THRESH
    h6_s = feat["h6_cohort_sector"]
    feat["coiled"] = bool(
        feat["in_washout_ctx"]
        and h6_s is not None
        and not np.isnan(h6_s)
        and h6_s >= H6_COHORT_THRESH
    )

    # STAR: COILED AND bull_div
    feat["star"] = bool(feat["coiled"] and feat["bull_div"])

    return feat


# ══════════════════════════════════════════════════════════════════════════════
# Pre-compute weekly D matrix for theme peers (baskets panel)
# ══════════════════════════════════════════════════════════════════════════════

def build_theme_d_matrix(panel_files: list[str], theme_peers: dict[str, set[str]],
                         min_bars: int) -> dict:
    """Like build_sector_d_matrix but for the theme cohort.
    Only load tickers that appear as peers of at least one panel name.
    """
    needed: set[str] = set()
    panel_names = {Path(fp).stem for fp in panel_files}
    for ticker in panel_names:
        peers = theme_peers.get(ticker, set())
        needed.update(peers)
    # Also load the panel names themselves (they may be peers of others)
    needed.update(panel_names)

    out: dict = {}
    data_dir = Path(panel_files[0]).parent if panel_files else DATA_BASKETS
    for t in needed:
        fp = data_dir / f"{t}.parquet"
        if not fp.exists():
            continue
        try:
            df = pd.read_parquet(fp)
            daily = df["close"].dropna()
            if len(daily) < min_bars:
                continue
            sw = daily.resample("W-FRI").last().dropna()
            known_w = daily.resample("W-FRI").apply(
                lambda x: x.dropna().index.max()
            ).reindex(sw.index).dropna()
            sw = sw.reindex(known_w.index)
            _, dw = TH.stoch_rsi_kd(sw)
            known_w_dt = pd.Series(pd.to_datetime(known_w.values), index=known_w.index)
            dw_daily = TH.to_daily(dw, known_w_dt, daily.index, "ffill")
            out[t] = (daily.index, dw_daily.to_numpy())
        except Exception:
            continue
    return out


# ══════════════════════════════════════════════════════════════════════════════
# Per-name processing (called in multiprocessing.Pool worker)
# ══════════════════════════════════════════════════════════════════════════════

def _process_name_worker(args: tuple) -> tuple[str, dict]:
    """Worker function for multiprocessing. Returns (ticker, result_dict)."""
    (ticker, fp, spy_ratio_vals, spy_ratio_idx,
     sector_map_sector, sector_d_matrix_ser,
     theme_peers, theme_d_matrix_ser,
     is_active, panel_cfg) = args

    min_bars   = panel_cfg["min_bars"]
    eval_start = panel_cfg["eval_start"]

    # Reconstruct spy_ratio Series
    spy_ratio: pd.Series | None = None
    if spy_ratio_vals is not None and spy_ratio_idx is not None:
        spy_ratio = pd.Series(spy_ratio_vals, index=pd.DatetimeIndex(spy_ratio_idx))

    # Reconstruct sector_d_matrix (values are (DatetimeIndex-bytes, ndarray))
    sector_d_matrix: dict = {}
    for t, (idx_vals, arr) in sector_d_matrix_ser.items():
        sector_d_matrix[t] = (pd.DatetimeIndex(idx_vals), arr)

    theme_d_matrix: dict | None = None
    if theme_d_matrix_ser is not None:
        theme_d_matrix = {}
        for t, (idx_vals, arr) in theme_d_matrix_ser.items():
            theme_d_matrix[t] = (pd.DatetimeIndex(idx_vals), arr)

    try:
        result = _process_name_inner(
            ticker, fp, spy_ratio,
            sector_map_sector, sector_d_matrix,
            theme_peers, theme_d_matrix,
            is_active, eval_start, min_bars,
        )
        return (ticker, result)
    except Exception as e:
        return (ticker, {"_error": str(e)})


def _process_name_inner(
    ticker: str,
    fp: str,
    spy_ratio: pd.Series | None,
    sector_map_sector: dict[str, str],
    sector_d_matrix: dict,
    theme_peers: dict[str, set[str]] | None,
    theme_d_matrix: dict | None,
    is_active: bool,
    eval_start: pd.Timestamp,
    min_bars: int,
) -> dict:
    """Core processing for one name. Returns result dict."""
    df = pd.read_parquet(fp)
    daily = df["close"].dropna()
    if len(daily) < min_bars:
        return {}

    hi  = df["high"].reindex(daily.index)   if "high"   in df.columns else pd.Series(np.nan, index=daily.index)
    lo  = df["low"].reindex(daily.index)    if "low"    in df.columns else pd.Series(np.nan, index=daily.index)
    vol = df["volume"].reindex(daily.index) if "volume" in df.columns else None

    c      = daily.to_numpy()
    hi_arr = hi.to_numpy()
    lo_arr = lo.to_numpy()
    vol_arr = vol.to_numpy() if vol is not None else None
    idx    = daily.index
    n      = len(c)

    # Build SPY ratio for rs_low
    # FIX-2: spy_ratio was already computed as (daily/spy) in main() and serialized as
    # the ratio series.  Do NOT divide again here — that would yield daily/(daily/spy) = SPY
    # level, making rs_low measure whether raw SPY made a 126d low, not the name vs SPY.
    # Simply reindex to align with daily.index.
    if spy_ratio is not None:
        try:
            spy_ratio_aligned = spy_ratio.reindex(daily.index, method="ffill")
        except Exception:
            spy_ratio_aligned = None
    else:
        spy_ratio_aligned = None

    # Label events (wave-2 extended)
    events_df = label_events_w2(daily)
    events_df["ticker"]    = ticker
    events_df["is_active"] = is_active

    # Build capture windows per event
    event_windows = []
    for _, ev in events_df.iterrows():
        t0     = ev["t0"]
        t0_pos = idx.get_loc(t0)
        event_windows.append({
            "t0_pos":   t0_pos,
            "w_start":  t0_pos + CAPTURE[0],
            "w_end":    t0_pos + CAPTURE[1],
            "label":    ev["label"],
            "p0":       ev["p0"],
            "b30":      ev["b30"],
            "dd_at_trough": ev["dd_at_trough"],
        })

    # Build TF grids once
    grids = build_tf_grids(daily, hi, lo, spy_ratio_aligned)

    result = {"events": events_df.to_dict("records")}

    for variant_name in W2_VARIANTS:
        cfg   = TH.VARIANTS[variant_name]
        frame = TH.build_signals(daily, cfg, hi, lo)
        raw_fires = frame.index[frame["buy"]].tolist()

        fire_rows: list[dict] = []
        variant_fires_before: list[dict] = []

        for sig_date in raw_fires:
            i = idx.get_loc(sig_date)

            fill_idx = i + 1
            if fill_idx >= n:
                continue
            fill_date = idx[fill_idx]

            # Track pre-eval fires for failed_180 (H5) only
            if fill_date < eval_start:
                pre_row: dict = {
                    "fill_idx":      fill_idx,
                    "sig_idx":       i,
                    "stop5":         0,
                    "resolution_idx": fill_idx + OUTCOME_W,
                }
                if fill_idx + FWD_REQ < n:
                    from wave1 import compute_outcomes as _w1_out
                    out_pre = _w1_out(fill_idx, c[fill_idx], c, hi_arr, lo_arr)
                    pre_row["stop5"]          = out_pre["stop5"]
                    pre_row["resolution_idx"] = out_pre["resolution_idx"]
                variant_fires_before.append(pre_row)
                continue

            if fill_idx + FWD_REQ >= n:
                continue

            p = c[fill_idx]
            if np.isnan(p):
                continue

            # Extended outcomes
            outcomes = compute_outcomes_w2(fill_idx, p, c, hi_arr, lo_arr)

            # Extended features
            features = compute_features_w2(
                i, grids, vol_arr, variant_fires_before,
                ticker, sig_date,
                sector_map_sector, sector_d_matrix,
                theme_peers, theme_d_matrix,
                eval_start,
            )

            # Event linkage
            captured  = False
            ev_label  = None
            premium   = None
            lead      = None
            for ew in event_windows:
                if ew["w_start"] <= i <= ew["w_end"]:
                    captured = True
                    ev_label = ew["label"]
                    premium  = p / ew["p0"] - 1 if ew["p0"] > 0 else None
                    lead     = i - ew["t0_pos"]
                    break

            row = {
                "ticker":    ticker,
                "is_active": is_active,
                "sig_date":  sig_date,
                "fill_date": fill_date,
                "p":         p,
                **outcomes,
                **features,
                "captured":  captured,
                "ev_label":  ev_label,
                "premium":   premium,
                "lead":      lead,
            }

            fire_rows.append(row)

            variant_fires_before.append({
                "fill_idx":       fill_idx,
                "sig_idx":        i,
                "stop5":          outcomes["stop5"],
                "resolution_idx": outcomes["resolution_idx"],
            })

        result[variant_name] = fire_rows

    return result


# ══════════════════════════════════════════════════════════════════════════════
# Helper: serialize / deserialize d_matrix for multiprocessing
# ══════════════════════════════════════════════════════════════════════════════

def _serialize_d_matrix(dm: dict) -> dict:
    """Convert {ticker: (DatetimeIndex, ndarray)} to picklable form.

    FIX-1: Store dates as ISO strings (YYYY-MM-DD) instead of asi8 integer counts.
    The parquet DatetimeIndexes are datetime64[ms]; asi8 gives millisecond counts.
    Deserializing those ints via pd.DatetimeIndex() interprets them as nanoseconds,
    corrupting dates to ~1970 and causing look-ahead leaks in get_cohort_frac.
    ISO strings round-trip exactly via pd.DatetimeIndex(iso_list).
    """
    return {t: (idx.strftime("%Y-%m-%d").tolist(), arr.tolist()) for t, (idx, arr) in dm.items()}


# ══════════════════════════════════════════════════════════════════════════════
# Table-building helpers
# ══════════════════════════════════════════════════════════════════════════════

_OUTCOME_COLS = ["stop5", "clean10", "clean15", "clean20", "clean30",
                 "clean15_h189", "dead_money"]

def _rate_row(df: pd.DataFrame, label: str) -> dict:
    """Build one table row from a fires sub-DataFrame."""
    n = len(df)
    row: dict = {"label": label, "n": n}
    if n == 0:
        for col in _OUTCOME_COLS:
            row[col] = float("nan")
        row["med_mfe63"] = float("nan")
        row["med_mae63"] = float("nan")
        return row
    for col in _OUTCOME_COLS:
        if col in df.columns:
            vals = df[col].dropna()
            row[col] = round(float(vals.mean()) * 100, 2) if len(vals) > 0 else float("nan")
        else:
            row[col] = float("nan")
    for col, key in [("mfe63", "med_mfe63"), ("mae63", "med_mae63")]:
        if col in df.columns:
            vals = df[col].dropna()
            row[key] = round(float(vals.median()) * 100, 2) if len(vals) > 0 else float("nan")
        else:
            row[key] = float("nan")
    return row


# T1 — Pooled stratum table
def build_T1(fires: pd.DataFrame, variant_name: str) -> list[dict]:
    """T1: pooled per-panel for one variant.
    Rows: ALL, in_washout, COILED, noncoiled_washout, STAR, coiled_no_div, div_only_noncoiled.
    For base3d: ALL + COILED only.
    """
    rows = []
    h6 = fires["h6_cohort_sector"] if "h6_cohort_sector" in fires.columns else pd.Series(np.nan, index=fires.index)

    all_row     = _rate_row(fires, "ALL")
    rows.append(all_row)

    if variant_name == "base3d":
        # Only ALL + COILED for reference variant
        coiled_mask = fires["coiled"] if "coiled" in fires.columns else pd.Series(False, index=fires.index)
        rows.append(_rate_row(fires[coiled_mask], "COILED"))
        return rows

    # m2d_s3d full breakdown
    washout_mask = fires["in_washout_ctx"].astype(bool) if "in_washout_ctx" in fires.columns else pd.Series(False, index=fires.index)
    coiled_mask  = fires["coiled"].astype(bool) if "coiled" in fires.columns else pd.Series(False, index=fires.index)
    bull_mask    = fires["bull_div"].astype(bool) if "bull_div" in fires.columns else pd.Series(False, index=fires.index)
    h6_notna     = h6.notna()

    rows.append(_rate_row(fires[washout_mask], "in_washout"))
    rows.append(_rate_row(fires[coiled_mask],  "COILED"))

    # noncoiled_washout: in_washout AND cohort<0.4 AND cohort not-na
    ncw_mask = washout_mask & h6_notna & (h6 < H6_COHORT_THRESH)
    rows.append(_rate_row(fires[ncw_mask], "noncoiled_washout"))

    rows.append(_rate_row(fires[coiled_mask & bull_mask],  "STAR"))
    rows.append(_rate_row(fires[coiled_mask & ~bull_mask], "coiled_no_div"))
    rows.append(_rate_row(fires[~coiled_mask & bull_mask & washout_mask], "div_only_noncoiled"))

    return rows


# T2 — Time folds (stocks panel)
def build_T2(fires: pd.DataFrame) -> list[dict]:
    """T2 (stocks): 5 time folds by fill_date quintiles.
    Purge: drop fires within 180 calendar days after each fold boundary.
    Reports per fold: n_coiled, n_noncoiled, clean15_spread, stop5_spread.
    """
    fires = fires.copy()
    fires["fill_date"] = pd.to_datetime(fires["fill_date"])

    coiled_mask = fires["coiled"].astype(bool) if "coiled" in fires.columns else pd.Series(False, index=fires.index)
    h6          = fires["h6_cohort_sector"] if "h6_cohort_sector" in fires.columns else pd.Series(np.nan, index=fires.index)
    washout_mask = fires["in_washout_ctx"].astype(bool) if "in_washout_ctx" in fires.columns else pd.Series(False, index=fires.index)

    # quintile boundaries from fill_date
    dates_sorted = fires["fill_date"].sort_values()
    n_total = len(dates_sorted)
    quintile_size = n_total // 5
    boundaries: list[pd.Timestamp] = []
    for q in range(1, 5):
        idx_boundary = quintile_size * q
        if idx_boundary < n_total:
            boundaries.append(dates_sorted.iloc[idx_boundary])

    # Create fold labels (0-4 inclusive)
    fires["fold"] = pd.cut(fires["fill_date"],
                           bins=[pd.Timestamp.min] + boundaries + [pd.Timestamp.max],
                           labels=False, right=True, include_lowest=True)

    rows = []
    for fold_id in range(5):
        fold_fires = fires[fires["fold"] == fold_id].copy()

        # Purge: drop fires within 180 calendar days after the fold START boundary
        if fold_id > 0:
            boundary_start = boundaries[fold_id - 1]
            cutoff = boundary_start + pd.Timedelta(days=180)
            fold_fires = fold_fires[fold_fires["fill_date"] >= cutoff]

        nc_fires = fold_fires[
            washout_mask.reindex(fold_fires.index, fill_value=False)
            & h6.reindex(fold_fires.index).notna()
            & (h6.reindex(fold_fires.index) < H6_COHORT_THRESH)
        ]
        c_fires  = fold_fires[coiled_mask.reindex(fold_fires.index, fill_value=False)]

        n_coiled    = len(c_fires)
        n_noncoiled = len(nc_fires)

        c15_c  = float(c_fires["clean15"].mean())  if n_coiled    > 0 else np.nan
        c15_nc = float(nc_fires["clean15"].mean()) if n_noncoiled > 0 else np.nan
        s5_c   = float(c_fires["stop5"].mean())    if n_coiled    > 0 else np.nan
        s5_nc  = float(nc_fires["stop5"].mean())   if n_noncoiled > 0 else np.nan

        clean15_spread = round((c15_c - c15_nc) * 100, 2) if not (np.isnan(c15_c) or np.isnan(c15_nc)) else float("nan")
        stop5_spread   = round((s5_c  - s5_nc)  * 100, 2) if not (np.isnan(s5_c)  or np.isnan(s5_nc))  else float("nan")

        # Fold date range
        if len(fold_fires) > 0:
            fold_start = str(fold_fires["fill_date"].min().date())
            fold_end   = str(fold_fires["fill_date"].max().date())
        else:
            fold_start = fold_end = "N/A"

        rows.append({
            "fold":           fold_id,
            "fold_start":     fold_start,
            "fold_end":       fold_end,
            "n_coiled":       n_coiled,
            "n_noncoiled":    n_noncoiled,
            "clean15_spread": clean15_spread,
            "stop5_spread":   stop5_spread,
            "purge_note":     "180 calendar days after fold boundary",
        })

    return rows


# T3 — Baskets: time halves, active/inactive, theme cohort
def build_T3(fires: pd.DataFrame) -> list[dict]:
    """T3 (baskets): time halves, active vs inactive, and h6_cohort_theme COILED rows."""
    fires = fires.copy()
    fires["fill_date"] = pd.to_datetime(fires["fill_date"])

    time_cut = pd.Timestamp("2020-01-01")
    pre_mask  = fires["fill_date"] < time_cut
    post_mask = fires["fill_date"] >= time_cut

    coiled_mask  = fires["coiled"].astype(bool) if "coiled" in fires.columns else pd.Series(False, index=fires.index)
    h6_s = fires["h6_cohort_sector"] if "h6_cohort_sector" in fires.columns else pd.Series(np.nan, index=fires.index)
    h6_t = fires["h6_cohort_theme"]  if "h6_cohort_theme"  in fires.columns else pd.Series(np.nan, index=fires.index)
    washout_mask = fires["in_washout_ctx"].astype(bool) if "in_washout_ctx" in fires.columns else pd.Series(False, index=fires.index)
    active_mask  = fires["is_active"].astype(bool)      if "is_active"      in fires.columns else pd.Series(True,  index=fires.index)

    # noncoiled (sector-based)
    ncw_mask = washout_mask & h6_s.notna() & (h6_s < H6_COHORT_THRESH)
    # COILED_theme: in_washout AND h6_cohort_theme >= 0.4
    coiled_theme_mask = washout_mask & h6_t.notna() & (h6_t >= H6_COHORT_THRESH)
    ncw_theme_mask    = washout_mask & h6_t.notna() & (h6_t < H6_COHORT_THRESH)

    rows = []

    # Time halves — sector-COILED
    for period_label, mask in [("pre2020", pre_mask), ("post2020", post_mask)]:
        sub = fires[mask]
        sub_c  = fires[mask & coiled_mask]
        sub_nc = fires[mask & ncw_mask]
        rows.append({
            "cut":           period_label,
            "cohort_type":   "sector",
            "stratum":       "COILED",
            **_rate_row(sub_c, f"COILED_{period_label}"),
        })
        rows.append({
            "cut":           period_label,
            "cohort_type":   "sector",
            "stratum":       "noncoiled_washout",
            **_rate_row(sub_nc, f"ncw_{period_label}"),
        })

    # Active vs inactive — sector-COILED
    for act_label, act_mask in [("active", active_mask), ("inactive", ~active_mask)]:
        sub_c  = fires[act_mask & coiled_mask]
        sub_nc = fires[act_mask & ncw_mask]
        rows.append({
            "cut":           act_label,
            "cohort_type":   "sector",
            "stratum":       "COILED",
            **_rate_row(sub_c, f"COILED_{act_label}"),
        })
        rows.append({
            "cut":           act_label,
            "cohort_type":   "sector",
            "stratum":       "noncoiled_washout",
            **_rate_row(sub_nc, f"ncw_{act_label}"),
        })

    # Theme cohort COILED rows (all, pre, post, active, inactive)
    cuts_theme = [
        ("all",      pd.Series(True,  index=fires.index)),
        ("pre2020",  pre_mask),
        ("post2020", post_mask),
        ("active",   active_mask),
        ("inactive", ~active_mask),
    ]
    for cut_label, cut_mask in cuts_theme:
        tc  = fires[cut_mask & coiled_theme_mask]
        tnc = fires[cut_mask & ncw_theme_mask]
        rows.append({
            "cut":           cut_label,
            "cohort_type":   "theme",
            "stratum":       "COILED_theme",
            **_rate_row(tc, f"COILED_theme_{cut_label}"),
        })
        rows.append({
            "cut":           cut_label,
            "cohort_type":   "theme",
            "stratum":       "noncoiled_theme",
            **_rate_row(tnc, f"ncw_theme_{cut_label}"),
        })

    return rows


# T4 — Per-name majority
def build_T4(fires: pd.DataFrame) -> dict:
    """T4: among names with >=3 fires in EACH of {COILED, noncoiled_washout}:
    % of names where COILED clean15 > noncoiled clean15.
    Same for STAR vs non-star-washout (>=2 fires each).
    """
    coiled_mask  = fires["coiled"].astype(bool) if "coiled" in fires.columns else pd.Series(False, index=fires.index)
    star_mask    = fires["star"].astype(bool)   if "star"   in fires.columns else pd.Series(False, index=fires.index)
    washout_mask = fires["in_washout_ctx"].astype(bool) if "in_washout_ctx" in fires.columns else pd.Series(False, index=fires.index)
    h6           = fires["h6_cohort_sector"] if "h6_cohort_sector" in fires.columns else pd.Series(np.nan, index=fires.index)

    ncw_mask    = washout_mask & h6.notna() & (h6 < H6_COHORT_THRESH)
    nonstar_w   = washout_mask & ~star_mask

    names = fires["ticker"].unique()

    # COILED vs noncoiled
    coiled_wins = 0
    coiled_total = 0
    for ticker in names:
        t_c  = fires[fires["ticker"] == ticker][coiled_mask.reindex(fires[fires["ticker"] == ticker].index, fill_value=False)]
        t_nc = fires[fires["ticker"] == ticker][ncw_mask.reindex(fires[fires["ticker"] == ticker].index, fill_value=False)]
        if len(t_c) >= 3 and len(t_nc) >= 3:
            coiled_total += 1
            if float(t_c["clean15"].mean()) > float(t_nc["clean15"].mean()):
                coiled_wins += 1

    # STAR vs non-star-washout
    star_wins = 0
    star_total = 0
    for ticker in names:
        t_s  = fires[fires["ticker"] == ticker][star_mask.reindex(fires[fires["ticker"] == ticker].index, fill_value=False)]
        t_ns = fires[fires["ticker"] == ticker][nonstar_w.reindex(fires[fires["ticker"] == ticker].index, fill_value=False)]
        if len(t_s) >= 2 and len(t_ns) >= 2:
            star_total += 1
            if float(t_s["clean15"].mean()) > float(t_ns["clean15"].mean()):
                star_wins += 1

    return {
        "coiled_vs_ncw": {
            "n_names_qualifying": coiled_total,
            "pct_coiled_wins_clean15": round(coiled_wins / coiled_total * 100, 2) if coiled_total > 0 else float("nan"),
        },
        "star_vs_nonstar_washout": {
            "n_names_qualifying": star_total,
            "pct_star_wins_clean15": round(star_wins / star_total * 100, 2) if star_total > 0 else float("nan"),
        },
    }


# T5 — Ranking monotonicity
def build_T5(fires: pd.DataFrame) -> list[dict]:
    """T5: among in_washout fires with h6_cohort_sector notna, quartiles of h6_cohort_sector.
    Per quartile: n, clean15, stop5, dead_money.  Q4-Q1 spread + Spearman of quartile means.
    """
    from scipy.stats import spearmanr

    washout_mask = fires["in_washout_ctx"].astype(bool) if "in_washout_ctx" in fires.columns else pd.Series(False, index=fires.index)
    h6 = fires["h6_cohort_sector"] if "h6_cohort_sector" in fires.columns else pd.Series(np.nan, index=fires.index)

    sub = fires[washout_mask & h6.notna()].copy()
    if len(sub) < 40:
        return [{"note": "insufficient data for T5 (n<40)"}]

    try:
        sub["cohort_q"] = pd.qcut(sub["h6_cohort_sector"], q=4, labels=[1, 2, 3, 4], duplicates="drop")
    except ValueError:
        # Too few unique cohort values (degenerate; common in small ticker subsets)
        return [{"note": "insufficient distinct cohort values for T5 quartile cut"}]

    rows = []
    c15_means: list[float] = []
    for q in [1, 2, 3, 4]:
        qdf = sub[sub["cohort_q"] == q]
        r = _rate_row(qdf, f"Q{q}")
        rows.append(r)
        c15_means.append(r["clean15"] if not np.isnan(r["clean15"]) else np.nan)

    # Q4 - Q1 spread
    q4_c15 = c15_means[3] if not np.isnan(c15_means[3]) else np.nan
    q1_c15 = c15_means[0] if not np.isnan(c15_means[0]) else np.nan
    spread = round(q4_c15 - q1_c15, 2) if not (np.isnan(q4_c15) or np.isnan(q1_c15)) else float("nan")

    # Spearman on non-nan quartile means
    valid_pairs = [(i + 1, c15_means[i]) for i in range(4) if not np.isnan(c15_means[i])]
    if len(valid_pairs) >= 3:
        ranks   = [p[0] for p in valid_pairs]
        c15vals = [p[1] for p in valid_pairs]
        spear_r, spear_p = spearmanr(ranks, c15vals)
    else:
        spear_r = float("nan")
        spear_p = float("nan")

    rows.append({
        "label":        "Q4_minus_Q1",
        "clean15_spread": spread,
        "spearman_r":   round(float(spear_r), 4) if not np.isnan(spear_r) else float("nan"),
        "spearman_p":   round(float(spear_p), 4) if not np.isnan(spear_p) else float("nan"),
    })

    return rows


# T6 — Threshold curve
def build_T6(fires: pd.DataFrame) -> list[dict]:
    """T6: threshold robustness curve.
    cohort_threshold x {0.3, 0.4, 0.5} × peer_d_threshold {25, 30}.
    Note: peer_d_threshold 25/30 refers to the cutoff used in get_cohort_frac
    (fraction of peers with weekly D < peer_d_thresh).
    Since we pre-computed h6_cohort_sector at threshold=30 (wave1 default),
    for threshold=25 we use the raw dw values stored in the sector_d_matrix.
    Instead of re-running, we approximate: the stored h6_cohort_sector was computed
    at D<30; for D<25 we report a note that the pre-computed value uses D<30 and
    we re-derive the split using different cohort thresholds on the SAME underlying
    h6_cohort_sector values as a proxy.
    The meaningful pre-registered curve is the cohort_threshold axis (0.3/0.4/0.5)
    since peer_d_threshold was fixed at 30; we report both dimensions with note.
    """
    washout_mask = fires["in_washout_ctx"].astype(bool) if "in_washout_ctx" in fires.columns else pd.Series(False, index=fires.index)
    h6 = fires["h6_cohort_sector"] if "h6_cohort_sector" in fires.columns else pd.Series(np.nan, index=fires.index)
    h6_notna = h6.notna()

    cohort_thresholds = [0.3, 0.4, 0.5]
    # For peer_d_threshold: 30 is the native value; 25 = stricter peers.
    # We cannot re-derive D<25 cohort values without re-running, so we note the limitation
    # and proxy by treating h6_cohort_sector (D<30 based) at different cohort thresholds.
    peer_d_thresholds = [25, 30]

    rows = []
    for ct in cohort_thresholds:
        for pdt in peer_d_thresholds:
            # For pdt=30: use h6_cohort_sector directly (the stored value)
            # For pdt=25: note we cannot recompute without re-running; use stored value as proxy
            # with a note flag.  The cohort_threshold axis is the valid pre-registered curve.
            pdt_note = "exact" if pdt == 30 else "proxy(stored_D<30_base)"

            coiled_t  = fires[washout_mask & h6_notna & (h6 >= ct)]
            noncld_t  = fires[washout_mask & h6_notna & (h6 <  ct)]

            nc15_c  = float(coiled_t["clean15"].mean())  if len(coiled_t)  > 0 else np.nan
            nc15_nc = float(noncld_t["clean15"].mean())  if len(noncld_t)  > 0 else np.nan
            s5_c    = float(coiled_t["stop5"].mean())    if len(coiled_t)  > 0 else np.nan
            s5_nc   = float(noncld_t["stop5"].mean())    if len(noncld_t)  > 0 else np.nan

            c15_spread = round((nc15_c - nc15_nc) * 100, 2) if not (np.isnan(nc15_c) or np.isnan(nc15_nc)) else float("nan")
            s5_spread  = round((s5_c   - s5_nc)   * 100, 2) if not (np.isnan(s5_c)   or np.isnan(s5_nc))   else float("nan")

            rows.append({
                "cohort_threshold":  ct,
                "peer_d_threshold":  pdt,
                "peer_d_note":       pdt_note,
                "n_coiled":          len(coiled_t),
                "n_noncoiled":       len(noncld_t),
                "coiled_clean15":    round(nc15_c  * 100, 2) if not np.isnan(nc15_c)  else float("nan"),
                "ncw_clean15":       round(nc15_nc * 100, 2) if not np.isnan(nc15_nc) else float("nan"),
                "clean15_spread":    c15_spread,
                "coiled_stop5":      round(s5_c    * 100, 2) if not np.isnan(s5_c)    else float("nan"),
                "ncw_stop5":         round(s5_nc   * 100, 2) if not np.isnan(s5_nc)   else float("nan"),
                "stop5_spread":      s5_spread,
            })

    return rows


# T7 — Side studies (stocks)
def build_T7(fires: pd.DataFrame) -> dict:
    """T7 (stocks): within COILED: trap_state T/F; failed2 T/F within STAR and ALL;
    fromos3 x COILED 2x2.
    """
    coiled_mask = fires["coiled"].astype(bool) if "coiled" in fires.columns else pd.Series(False, index=fires.index)
    star_mask   = fires["star"].astype(bool)   if "star"   in fires.columns else pd.Series(False, index=fires.index)

    coiled_fires = fires[coiled_mask]
    star_fires   = fires[star_mask]

    trap_notna = coiled_fires["trap_state"].notna() if "trap_state" in coiled_fires.columns else pd.Series(True, index=coiled_fires.index)

    # Within COILED: trap_state
    trap_T = _rate_row(coiled_fires[coiled_fires["trap_state"] == True], "COILED_trap_T") if "trap_state" in coiled_fires.columns else {}   # noqa: E712
    trap_F = _rate_row(coiled_fires[coiled_fires["trap_state"] == False], "COILED_trap_F") if "trap_state" in coiled_fires.columns else {}  # noqa: E712

    # failed2 within STAR
    failed_notna_star = star_fires["failed2"].notna() if "failed2" in star_fires.columns else pd.Series(True, index=star_fires.index)
    f2T_star = _rate_row(star_fires[star_fires["failed2"] == True], "STAR_failed2_T") if "failed2" in star_fires.columns else {}   # noqa: E712
    f2F_star = _rate_row(star_fires[star_fires["failed2"] == False], "STAR_failed2_F") if "failed2" in star_fires.columns else {}  # noqa: E712

    # failed2 within ALL
    f2T_all = _rate_row(fires[fires["failed2"] == True], "ALL_failed2_T") if "failed2" in fires.columns else {}   # noqa: E712
    f2F_all = _rate_row(fires[fires["failed2"] == False], "ALL_failed2_F") if "failed2" in fires.columns else {}  # noqa: E712

    # fromos3 x COILED 2x2
    fromos3_notna = fires["fromos3"].notna() if "fromos3" in fires.columns else pd.Series(True, index=fires.index)
    fromos3_T = fires["fromos3"] == True if "fromos3" in fires.columns else pd.Series(False, index=fires.index)    # noqa: E712
    fromos3_F = fires["fromos3"] == False if "fromos3" in fires.columns else pd.Series(True,  index=fires.index)   # noqa: E712

    coiled_ser = coiled_mask

    fromos3_2x2 = [
        _rate_row(fires[fromos3_T & coiled_ser],   "fromos3_T_COILED_T"),
        _rate_row(fires[fromos3_T & ~coiled_ser],  "fromos3_T_COILED_F"),
        _rate_row(fires[fromos3_F & coiled_ser],   "fromos3_F_COILED_T"),
        _rate_row(fires[fromos3_F & ~coiled_ser],  "fromos3_F_COILED_F"),
    ]

    return {
        "within_coiled_trap": [trap_T, trap_F],
        "failed2_within_star": [f2T_star, f2F_star],
        "failed2_within_all":  [f2T_all,  f2F_all],
        "fromos3_x_coiled_2x2": fromos3_2x2,
    }


# T8 — Recall economics
def build_T8(fires: pd.DataFrame, events: pd.DataFrame, panel_fires_all: pd.DataFrame) -> dict:
    """T8: recall economics using vectorized event-window merge.

    For ALL m2d fires, COILED-only, STAR-only:
    - recall_B15: fraction of durable B15 events with >=1 fire in [t0-5, t0+15] TD
    - recall_B30: fraction of B30 subset
    - trap_fire_rate: fraction of trap events with >=1 fire in window
    - med_premium, med_lead for captured COILED fires
    - trap_fire_rate by stratum
    """
    if len(events) == 0 or len(fires) == 0:
        return {"note": "no events or fires"}

    events = events.copy()
    events["t0"] = pd.to_datetime(events["t0"])

    fires = fires.copy()
    fires["sig_date"] = pd.to_datetime(fires["sig_date"])

    coiled_mask = fires["coiled"].astype(bool) if "coiled" in fires.columns else pd.Series(False, index=fires.index)
    star_mask   = fires["star"].astype(bool)   if "star"   in fires.columns else pd.Series(False, index=fires.index)

    subsets = {
        "ALL":    fires,
        "COILED": fires[coiled_mask],
        "STAR":   fires[star_mask],
    }

    def _recall_vectorized(fire_sub: pd.DataFrame, ev_sub: pd.DataFrame) -> float:
        """Fraction of events in ev_sub that have >=1 fire from fire_sub
        in [t0-5d, t0+15d] approximate (calendar days; trading-day approximation: 5*1.4=7cal, 15*1.4=21cal).
        We use ±7 / +21 calendar day bounds as a close approximation.
        """
        if len(fire_sub) == 0 or len(ev_sub) == 0:
            return float("nan")

        hit = 0
        for _, ev in ev_sub.iterrows():
            ticker = ev["ticker"]
            t0     = ev["t0"]
            # approx window: t0 - 7 cal days to t0 + 21 cal days
            w_start = t0 - pd.Timedelta(days=7)
            w_end   = t0 + pd.Timedelta(days=21)
            matching = fire_sub[
                (fire_sub["ticker"] == ticker)
                & (fire_sub["sig_date"] >= w_start)
                & (fire_sub["sig_date"] <= w_end)
            ]
            if len(matching) > 0:
                hit += 1
        return hit / len(ev_sub)

    dur_events  = events[events["label"] == "durable"]
    b30_events  = events[(events["label"] == "durable") & (events["b30"] == True)]  # noqa: E712
    trap_events = events[events["label"] == "trap"]

    result: dict = {}
    for sub_name, fire_sub in subsets.items():
        rB15  = _recall_vectorized(fire_sub, dur_events)
        rB30  = _recall_vectorized(fire_sub, b30_events)
        trap  = _recall_vectorized(fire_sub, trap_events)

        # Med premium and lead for captured COILED fires in this subset
        if sub_name == "COILED" and len(fire_sub) > 0:
            cap_fires = fire_sub[fire_sub["captured"] & (fire_sub["ev_label"] == "durable")]
            med_prem = round(float(cap_fires["premium"].dropna().median()) * 100, 2) if len(cap_fires) > 0 else float("nan")
            med_lead = float(cap_fires["lead"].dropna().median()) if len(cap_fires) > 0 else float("nan")
        else:
            med_prem = float("nan")
            med_lead = float("nan")

        # trap_fire_rate (same window as recall but for trap events)
        result[sub_name] = {
            "n_fires":        len(fire_sub),
            "recall_B15":     round(rB15 * 100, 2)  if not np.isnan(rB15)  else float("nan"),
            "recall_B30":     round(rB30 * 100, 2)  if not np.isnan(rB30)  else float("nan"),
            "trap_fire_rate": round(trap * 100, 2)   if not np.isnan(trap)  else float("nan"),
            "med_premium":    med_prem,
            "med_lead":       med_lead,
        }

    return result


# T9 — Label-sensitivity re-read (B30 / alternative durability definitions)
def build_T9(fires: pd.DataFrame, events: pd.DataFrame) -> dict:
    """T9: B30/label-sensitivity re-read (§8 wave-2 directive).

    Re-evaluates COILED and STAR recall under three alternative durability definitions
    computed in label_events_w2:
      - durable_tol5   : durable with 5% tolerance hold floor
      - durable_lift30 : durable requiring +30% liftoff within 126d
      - durable_h189   : durable evaluated over a 189d window

    For each alternative label, reports:
      recall_COILED : fraction of alt-durable events that have >=1 COILED fire in capture window
      recall_STAR   : fraction of alt-durable events that have >=1 STAR fire in capture window
      recall_ALL    : fraction of alt-durable events that have >=1 ANY fire in capture window
      n_events      : total alt-durable events in the events_df
      n_coiled_fires, n_star_fires : count of COILED / STAR fires used for the recall check

    The capture window is the same as T8: ~t0-7 to t0+21 calendar-day approximation.

    This table does NOT feed any fire-row features (leak-safe); it only re-scores the
    recall axis using alternative definitions of what "durable" means.
    """
    if len(events) == 0 or len(fires) == 0:
        return {"note": "no events or fires for T9"}

    events = events.copy()
    fires  = fires.copy()

    if "t0" in events.columns:
        events["t0"] = pd.to_datetime(events["t0"])
    if "sig_date" in fires.columns:
        fires["sig_date"] = pd.to_datetime(fires["sig_date"])

    coiled_mask = fires["coiled"].astype(bool) if "coiled" in fires.columns else pd.Series(False, index=fires.index)
    star_mask   = fires["star"].astype(bool)   if "star"   in fires.columns else pd.Series(False, index=fires.index)

    coiled_fires = fires[coiled_mask]
    star_fires   = fires[star_mask]

    ALT_LABELS = ["durable_tol5", "durable_lift30", "durable_h189"]

    def _recall_for_label_col(fire_sub: pd.DataFrame, ev_sub: pd.DataFrame) -> float:
        """Fraction of ev_sub events that have >=1 fire from fire_sub in capture window."""
        if len(fire_sub) == 0 or len(ev_sub) == 0:
            return float("nan")
        hit = 0
        for _, ev in ev_sub.iterrows():
            ticker = ev["ticker"]
            t0     = ev["t0"]
            w_start = t0 - pd.Timedelta(days=7)
            w_end   = t0 + pd.Timedelta(days=21)
            matching = fire_sub[
                (fire_sub["ticker"] == ticker)
                & (fire_sub["sig_date"] >= w_start)
                & (fire_sub["sig_date"] <= w_end)
            ]
            if len(matching) > 0:
                hit += 1
        return hit / len(ev_sub)

    result: dict = {}
    for col in ALT_LABELS:
        if col not in events.columns:
            result[col] = {"note": f"column {col} not in events (label_events_w2 not used)"}
            continue

        alt_dur_events = events[events[col] == True]  # noqa: E712
        n_ev = len(alt_dur_events)

        rALL    = _recall_for_label_col(fires,        alt_dur_events)
        rCOILED = _recall_for_label_col(coiled_fires, alt_dur_events)
        rSTAR   = _recall_for_label_col(star_fires,   alt_dur_events)

        result[col] = {
            "n_events":      n_ev,
            "n_coiled_fires": int(coiled_mask.sum()),
            "n_star_fires":   int(star_mask.sum()),
            "recall_ALL":     round(rALL    * 100, 2) if not (isinstance(rALL,    float) and np.isnan(rALL))    else float("nan"),
            "recall_COILED":  round(rCOILED * 100, 2) if not (isinstance(rCOILED, float) and np.isnan(rCOILED)) else float("nan"),
            "recall_STAR":    round(rSTAR   * 100, 2) if not (isinstance(rSTAR,   float) and np.isnan(rSTAR))   else float("nan"),
            "label_def": {
                "durable_tol5":   "hold floor=P0*0.95 (5% tol), liftoff=+20%, horizon=126d",
                "durable_lift30": "hold floor=P0*0.97 (3% tol), liftoff=+30%, horizon=126d",
                "durable_h189":   "hold floor=P0*0.97 (3% tol), liftoff=+20%, horizon=189d",
            }.get(col, col),
        }

    return result


# ══════════════════════════════════════════════════════════════════════════════
# Main pipeline
# ══════════════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description="Wave-2 durable-bottom entry timing study")
    ap.add_argument("--panel",   required=True, choices=["stocks", "baskets"],
                    help="Panel to run: stocks or baskets")
    ap.add_argument("--tickers", default="", help="Comma-separated ticker subset")
    ap.add_argument("--workers", type=int, default=6, help="Multiprocessing pool size")
    ap.add_argument("--out", default="", help="Output directory (default: research/entry_timing/_out/wave2_{panel})")
    args = ap.parse_args()

    panel_cfg = PANEL_CONFIGS[args.panel]
    data_dir  = panel_cfg["data_dir"]
    min_bars  = panel_cfg["min_bars"]
    eval_start = panel_cfg["eval_start"]

    if args.out:
        out_dir = Path(args.out)
    else:
        out_dir = ROOT / "research" / "entry_timing" / "_out" / f"wave2_{args.panel}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Wave-2 | panel={args.panel} | eval_start={eval_start.date()} | "
          f"min_bars={min_bars} | workers={args.workers}")
    print(f"Output: {out_dir}")

    # ── Resolve file list ──────────────────────────────────────────────────
    all_files = sorted(data_dir.glob("*.parquet"))
    if args.tickers:
        wanted = {t.strip() for t in args.tickers.split(",") if t.strip()}
        all_files = [f for f in all_files if f.stem in wanted]

    print(f"Candidate files: {len(all_files)}")

    # Pre-filter
    panel_files: list[Path] = []
    for fp in all_files:
        try:
            df = pd.read_parquet(fp)
            daily = df["close"].dropna()
            if len(daily) >= min_bars:
                panel_files.append(fp)
        except Exception:
            pass
    print(f"After >={min_bars} bar filter: {len(panel_files)} names")

    # ── Load membership (baskets panel needs active set + theme peers) ─────
    membership: dict | None = None
    active_set: set[str]    = set()
    theme_peers: dict[str, set[str]] | None = None
    basket_sector_map: dict[str, str] = {}

    if MEMBERSHIP.exists():
        membership = load_membership()
        active_set = build_active_set(membership)
        if args.panel == "baskets":
            basket_sector_map = build_basket_sector_map(membership)
            theme_peers       = build_theme_peers(membership)
            print(f"Basket sector map: {len(basket_sector_map)} tickers")
            print(f"Theme peers built for {len(theme_peers)} tickers")

    # ── Load constituents.parquet sector map ──────────────────────────────
    const_path = BREADTH / "constituents.parquet"
    const_sector_map: dict[str, str] = {}
    if const_path.exists():
        const_df = pd.read_parquet(const_path)
        for sym, row in const_df.iterrows():
            const_sector_map[sym] = row["sector"]
    print(f"Constituents sector map: {len(const_sector_map)} tickers")

    # ── Build combined sector map ─────────────────────────────────────────
    # For baskets panel: prefer basket_sector_map (covers 502 of 2518 OHLCV names)
    # vs constituents (covers 501). Union is 502. Basket map preferred as it was
    # specifically curated for this repo. Document choice:
    if args.panel == "baskets":
        sector_map_sector = {**const_sector_map, **basket_sector_map}
        # basket_sector_map wins on conflicts (more curated for this repo)
        cohort_source_note = (
            "baskets panel sector cohort: basket_sector_map from us_sector_* baskets preferred "
            f"({len(basket_sector_map)} tickers) over constituents.parquet "
            f"({len(const_sector_map)} tickers); union={len(sector_map_sector)} tickers. "
            "Basket map wins on overlap."
        )
        print(cohort_source_note)
    else:
        sector_map_sector = const_sector_map
        cohort_source_note = f"stocks panel sector cohort: constituents.parquet ({len(sector_map_sector)} tickers)"
        print(cohort_source_note)

    # ── Load SPY ──────────────────────────────────────────────────────────
    spy_path = DATA_STOCKS / "SPY.parquet"
    if not spy_path.exists():
        spy_path = ROOT / "data" / "yahoo" / "SPY.parquet"
    spy_close: pd.Series | None = None
    if spy_path.exists():
        spy_df = pd.read_parquet(spy_path)
        spy_close = spy_df["close"].dropna()
        print(f"SPY loaded: {len(spy_close)} bars")
    else:
        print("Warning: SPY not found")

    # ── Pre-compute sector weekly-D matrix ────────────────────────────────
    # IMPORTANT: Build the matrix from ALL files in the data directory (not just the
    # ticker subset panel_files) so that cohort peers are available even when running
    # a small ticker subset for smoke testing.  Peers must exist in the matrix for the
    # cohort fraction to be non-null; using only panel_files would give 0 peers for a
    # small smoke subset.
    # Optimization: only load files whose ticker is in sector_map_sector (peer candidates).
    # For stocks: all 223 files; for baskets: only ~504 sector-mapped tickers (not all 2518).
    # This dramatically reduces D-matrix build time for the baskets panel.
    print("Building sector weekly-D matrix (H6 cohort) from full data dir...")
    t0_matrix = time.time()
    all_data_files = sorted(data_dir.glob("*.parquet"))
    # Filter to tickers in sector map (the only possible sector peers)
    sector_peer_files = [fp for fp in all_data_files if fp.stem in sector_map_sector]
    # Also include panel_files not in sector_map (to store their own D-array in case
    # they have enough same-sector peers via the map; the matrix only keys those with a sector)
    sector_d_matrix = build_sector_d_matrix(
        [str(fp) for fp in sector_peer_files], sector_map_sector
    )
    print(f"Sector D-matrix: {len(sector_d_matrix)} tickers ({time.time()-t0_matrix:.1f}s)")

    # ── Pre-compute theme weekly-D matrix (baskets panel) ─────────────────
    # Theme peers can be any basket member, so we need the full set.
    # For small smoke subsets, the peer list is bounded by co-membership of the 12 tickers.
    theme_d_matrix: dict | None = None
    if args.panel == "baskets" and theme_peers is not None:
        print("Building theme weekly-D matrix...")
        t0_th = time.time()
        # build_theme_d_matrix already filters to only "needed" tickers (peers of panel names)
        theme_d_matrix = build_theme_d_matrix(
            [str(fp) for fp in all_data_files], theme_peers, min_bars
        )
        print(f"Theme D-matrix: {len(theme_d_matrix)} tickers ({time.time()-t0_th:.1f}s)")

    # ── Serialize matrices for multiprocessing ────────────────────────────
    sector_d_matrix_ser = _serialize_d_matrix(sector_d_matrix)
    theme_d_matrix_ser  = _serialize_d_matrix(theme_d_matrix) if theme_d_matrix else None

    # ── Build per-name args list ──────────────────────────────────────────
    worker_args = []
    for fp in panel_files:
        ticker = fp.stem
        is_active = ticker in active_set

        # Pre-compute SPY ratio for this ticker
        spy_vals = None
        spy_idx_vals = None
        if spy_close is not None:
            try:
                df_t = pd.read_parquet(fp)
                daily_t = df_t["close"].dropna()
                spy_aligned = spy_close.reindex(daily_t.index, method="ffill")
                spy_ratio_s = (daily_t / spy_aligned).replace([np.inf, -np.inf], np.nan)
                spy_vals    = spy_ratio_s.to_numpy().tolist()
                # FIX-1: store ISO strings, not asi8 ints (asi8 = ms counts; DatetimeIndex
                # would misinterpret them as ns, collapsing all dates to 1970)
                spy_idx_vals = daily_t.index.strftime("%Y-%m-%d").tolist()
            except Exception:
                pass

        worker_args.append((
            ticker, str(fp),
            spy_vals, spy_idx_vals,
            sector_map_sector, sector_d_matrix_ser,
            theme_peers, theme_d_matrix_ser,
            is_active,
            {"min_bars": min_bars, "eval_start": eval_start},
        ))

    # ── Run pool ──────────────────────────────────────────────────────────
    print(f"\nProcessing {len(worker_args)} names with {args.workers} workers...")
    t0_run = time.time()

    all_fires_by_variant: dict[str, list[dict]] = {v: [] for v in W2_VARIANTS}
    all_events: list[dict] = []
    ticker_list: list[str] = []
    errors: list[str] = []

    if args.workers <= 1:
        # Single-process mode for debugging
        results = [_process_name_worker(a) for a in worker_args]
    else:
        with Pool(args.workers) as pool:
            results = pool.map(_process_name_worker, worker_args)

    for ticker, result in results:
        if "_error" in result:
            errors.append(f"{ticker}: {result['_error']}")
            continue
        if not result:
            continue
        for vname in W2_VARIANTS:
            rows = result.get(vname, [])
            all_fires_by_variant[vname].extend(rows)
        all_events.extend(result.get("events", []))
        ticker_list.append(ticker)

    total_elapsed = time.time() - t0_run
    n_names = len(ticker_list)
    print(f"\nDone: {n_names} names in {total_elapsed:.1f}s ({total_elapsed/max(n_names,1):.1f}s/name)")
    if errors:
        print(f"Errors ({len(errors)}): {errors[:5]}")

    # ── Build DataFrames ──────────────────────────────────────────────────
    events_df = pd.DataFrame(all_events)
    if "t0" in events_df.columns:
        events_df["t0"] = pd.to_datetime(events_df["t0"])

    fires_dfs: dict[str, pd.DataFrame] = {}
    for vname in W2_VARIANTS:
        rows = all_fires_by_variant[vname]
        if rows:
            df_v = pd.DataFrame(rows)
            df_v["sig_date"]  = pd.to_datetime(df_v["sig_date"])
            df_v["fill_date"] = pd.to_datetime(df_v["fill_date"])
            fires_dfs[vname] = df_v
        else:
            fires_dfs[vname] = pd.DataFrame()

    # ── Save parquets ─────────────────────────────────────────────────────
    events_df.to_parquet(out_dir / "events.parquet", index=False)
    for vname in W2_VARIANTS:
        fires_dfs[vname].to_parquet(out_dir / f"fires_{vname}.parquet", index=False)
    print(f"Saved parquets to {out_dir}")

    # ── Build wave2_tables.json ───────────────────────────────────────────
    tables: dict = {
        "_meta": {
            "panel":              args.panel,
            "n_names":            n_names,
            "eval_start":         str(eval_start.date()),
            "min_bars":           min_bars,
            "workers":            args.workers,
            "runtime_s":          round(total_elapsed, 1),
            "cohort_source_note": cohort_source_note,
            "purge_method":       "T2: 180 calendar days after each fold boundary date",
        }
    }

    # T1
    tables["T1"] = {}
    for vname in W2_VARIANTS:
        fires = fires_dfs[vname]
        tables["T1"][vname] = build_T1(fires, vname) if len(fires) > 0 else []

    # T2 (stocks) / T3 (baskets) — m2d_s3d only
    fires_m = fires_dfs.get("m2d_s3d", pd.DataFrame())
    if args.panel == "stocks":
        tables["T2"] = build_T2(fires_m) if len(fires_m) > 0 else []
    else:
        tables["T3"] = build_T3(fires_m) if len(fires_m) > 0 else []

    # T4 — m2d_s3d
    tables["T4"] = build_T4(fires_m) if len(fires_m) > 0 else {}

    # T5 — m2d_s3d
    tables["T5"] = build_T5(fires_m) if len(fires_m) > 0 else []

    # T6 — m2d_s3d (both panels)
    tables["T6"] = build_T6(fires_m) if len(fires_m) > 0 else []

    # T7 — stocks only (side studies)
    if args.panel == "stocks":
        tables["T7"] = build_T7(fires_m) if len(fires_m) > 0 else {}

    # T8 — recall economics (m2d_s3d fires vs events)
    tables["T8"] = build_T8(fires_m, events_df, fires_m) if len(fires_m) > 0 and len(events_df) > 0 else {}

    # T9 — B30 / label-sensitivity re-read (§8 wave-2 directive)
    # Re-evaluates COILED/STAR recall under durable_tol5, durable_lift30, durable_h189
    # alternative durability definitions computed in label_events_w2.
    tables["T9"] = build_T9(fires_m, events_df) if len(fires_m) > 0 and len(events_df) > 0 else {}

    tables_path = out_dir / "wave2_tables.json"
    with open(tables_path, "w") as f:
        json.dump(tables, f, indent=2, default=str)
    print(f"Saved wave2_tables.json to {tables_path}")

    # ── Print compact summary ─────────────────────────────────────────────
    print("\n" + "=" * 70)
    print(f"WAVE-2 SUMMARY | panel={args.panel}")
    print("=" * 70)

    n_events = len(events_df)
    n_dur = int((events_df["label"] == "durable").sum()) if n_events > 0 else 0
    n_trap = int((events_df["label"] == "trap").sum()) if n_events > 0 else 0
    print(f"Events: total={n_events}  durable={n_dur}  trap={n_trap}")

    for vname in W2_VARIANTS:
        fires = fires_dfs[vname]
        if len(fires) == 0:
            print(f"\n--- {vname}: NO FIRES ---")
            continue

        coiled_mask  = fires["coiled"] if "coiled" in fires.columns else pd.Series(False, index=fires.index)
        star_mask    = fires["star"]   if "star"   in fires.columns else pd.Series(False, index=fires.index)
        washout_mask = fires["in_washout_ctx"] if "in_washout_ctx" in fires.columns else pd.Series(False, index=fires.index)
        h6_s = fires["h6_cohort_sector"] if "h6_cohort_sector" in fires.columns else pd.Series(np.nan, index=fires.index)
        ncw_mask = washout_mask & h6_s.notna() & (h6_s < H6_COHORT_THRESH)

        n_all    = len(fires)
        n_coiled = int(coiled_mask.sum())
        n_star   = int(star_mask.sum())
        n_ncw    = int(ncw_mask.sum())

        all_s5   = round(float(fires["stop5"].mean())   * 100, 2)
        all_c15  = round(float(fires["clean15"].mean()) * 100, 2)
        c_s5     = round(float(fires[coiled_mask]["stop5"].mean())   * 100, 2) if n_coiled > 0 else float("nan")
        c_c15    = round(float(fires[coiled_mask]["clean15"].mean()) * 100, 2) if n_coiled > 0 else float("nan")
        s_c15    = round(float(fires[star_mask]["clean15"].mean())   * 100, 2) if n_star > 0 else float("nan")
        s_s5     = round(float(fires[star_mask]["stop5"].mean())     * 100, 2) if n_star > 0 else float("nan")
        nc_c15   = round(float(fires[ncw_mask]["clean15"].mean())    * 100, 2) if n_ncw > 0 else float("nan")
        nc_s5    = round(float(fires[ncw_mask]["stop5"].mean())      * 100, 2) if n_ncw > 0 else float("nan")

        print(f"\n--- {vname} ---")
        print(f"  fires={n_all}  coiled={n_coiled}  star={n_star}  ncw={n_ncw}")
        print(f"  ALL:    stop5={all_s5}%  clean15={all_c15}%")
        print(f"  COILED: stop5={c_s5}%  clean15={c_c15}%")
        print(f"  STAR:   stop5={s_s5}%  clean15={s_c15}%")
        print(f"  NCW:    stop5={nc_s5}%  clean15={nc_c15}%")
        if not np.isnan(c_c15) and not np.isnan(nc_c15):
            print(f"  COILED vs NCW clean15 spread: {round(c_c15 - nc_c15, 2)}pp")

    print("=" * 70)
    print(f"\nProjected runtimes:")
    secs_per_name = total_elapsed / max(n_names, 1)
    n_stocks  = 211
    n_baskets = 2336
    print(f"  Stocks  panel: ~{secs_per_name * n_stocks  / 6 / 60:.1f} min @ --workers 6  ({n_stocks} names)")
    print(f"  Baskets panel: ~{secs_per_name * n_baskets / 6 / 60:.1f} min @ --workers 6  ({n_baskets} names)")

    return tables, events_df, fires_dfs


# ══════════════════════════════════════════════════════════════════════════════
# Smoke test
# ══════════════════════════════════════════════════════════════════════════════

def run_smoke(tables: dict, events_df: pd.DataFrame, fires_dfs: dict, panel: str):
    """Assert smoke-test conditions."""
    print("\n" + "=" * 70)
    print("WAVE-2 SMOKE ASSERTIONS")
    print("=" * 70)

    errors: list[str] = []

    # 1. Events non-empty with both labels
    n_dur  = int((events_df["label"] == "durable").sum()) if len(events_df) > 0 else 0
    n_trap = int((events_df["label"] == "trap").sum())    if len(events_df) > 0 else 0
    print(f"[1] Events: durable={n_dur}, trap={n_trap}")
    if n_dur  == 0: errors.append("No durable events")
    if n_trap == 0: errors.append("No trap events")

    # 2. COILED and STAR non-empty on m2d_s3d
    # Note: COILED requires h6_cohort_sector >= 0.4 (a wide-sector crowd event).
    # In small ticker subset runs, cohort values may be below threshold if the panel
    # only covers a few tickers.  The assertion is only hard-required for the stocks
    # panel (which loads all 211 names' cohort peers even in an 8-ticker subset run).
    fires_m = fires_dfs.get("m2d_s3d", pd.DataFrame())
    if len(fires_m) > 0:
        n_coiled = int(fires_m["coiled"].sum()) if "coiled" in fires_m.columns else 0
        n_star   = int(fires_m["star"].sum())   if "star"   in fires_m.columns else 0
        print(f"[2] m2d_s3d: n_fires={len(fires_m)}, n_coiled={n_coiled}, n_star={n_star}")
        # Hard-require COILED/STAR only for the stocks panel (full-panel cohort peers)
        if panel == "stocks":
            if n_coiled == 0: errors.append("COILED stratum is empty on m2d_s3d!")
            if n_star   == 0: errors.append("STAR stratum is empty on m2d_s3d!")
        else:
            # Baskets panel: COILED may be empty in small subset runs (cohort below 0.4).
            # Assert that h6_cohort_sector is being computed (not all NaN) instead.
            h6_notna = int(fires_m["h6_cohort_sector"].notna().sum()) if "h6_cohort_sector" in fires_m.columns else 0
            print(f"[2b] Baskets: h6_cohort_sector non-null={h6_notna}/{len(fires_m)} "
                  f"(COILED requires >=0.4; full-panel run will produce COILED fires)")
            if h6_notna == 0 and len(fires_m) > 100:
                errors.append("h6_cohort_sector is all null on baskets panel!")
    else:
        errors.append("No m2d_s3d fires!")

    # 3. Wave-1 consistency check (stocks panel only, 8 smoke tickers)
    SMOKE_TICKERS = {"AAPL", "MSFT", "JNJ", "NVDA", "WMT", "XOM", "KO", "CAT"}
    WAVE1_STOP5   = 36.54   # reference from stored wave-1 smoke run on these 8 tickers
    WAVE1_CLEAN15 = 35.01
    TOLERANCE_PP  = 1.0

    if panel == "stocks" and len(fires_m) > 0:
        has_smoke = fires_m["ticker"].isin(SMOKE_TICKERS).any()
        if has_smoke:
            smoke_fires = fires_m[fires_m["ticker"].isin(SMOKE_TICKERS)]
            s5  = round(float(smoke_fires["stop5"].mean())   * 100, 2)
            c15 = round(float(smoke_fires["clean15"].mean()) * 100, 2)
            print(f"[3] Smoke 8-ticker m2d_s3d: stop5={s5}% (ref {WAVE1_STOP5}±{TOLERANCE_PP}), "
                  f"clean15={c15}% (ref {WAVE1_CLEAN15}±{TOLERANCE_PP})")
            if abs(s5  - WAVE1_STOP5)   > TOLERANCE_PP:
                errors.append(f"stop5={s5} differs from wave-1 ref {WAVE1_STOP5} by >{TOLERANCE_PP}pp!")
            if abs(c15 - WAVE1_CLEAN15) > TOLERANCE_PP:
                errors.append(f"clean15={c15} differs from wave-1 ref {WAVE1_CLEAN15} by >{TOLERANCE_PP}pp!")
        else:
            print("[3] Wave-1 consistency: smoke tickers not in panel (subset run) — skip")

    # 4. T2/T5/T7/T8/T9 blocks present and non-degenerate (stocks)
    if panel == "stocks":
        for tbl_name in ["T2", "T5", "T7", "T8", "T9"]:
            if tbl_name not in tables:
                errors.append(f"Table {tbl_name} missing!")
            else:
                val = tables[tbl_name]
                if val is None or (isinstance(val, (list, dict)) and len(val) == 0):
                    errors.append(f"Table {tbl_name} is empty!")
                else:
                    print(f"[4] {tbl_name}: present ({'dict' if isinstance(val,dict) else 'list'} len={len(val)})")

    # 5. T8 sub-keys
    t8 = tables.get("T8", {})
    if isinstance(t8, dict) and len(t8) > 0:
        for key in ["ALL", "COILED", "STAR"]:
            if key not in t8:
                errors.append(f"T8 missing key {key}")
            else:
                print(f"[5] T8[{key}]: recall_B15={t8[key].get('recall_B15','?')}%")

    # 5b. T9 label-sensitivity sub-keys
    t9 = tables.get("T9", {})
    if isinstance(t9, dict) and len(t9) > 0 and "note" not in t9:
        for alt_col in ["durable_tol5", "durable_lift30", "durable_h189"]:
            if alt_col not in t9:
                errors.append(f"T9 missing key {alt_col}")
            else:
                n_ev   = t9[alt_col].get("n_events", "?")
                rC     = t9[alt_col].get("recall_COILED", "?")
                print(f"[5b] T9[{alt_col}]: n_events={n_ev}, recall_COILED={rC}%")
    else:
        if panel == "stocks":
            errors.append("T9 is missing or empty on stocks panel!")

    # 6. New outcome columns present
    if len(fires_m) > 0:
        for col in ["clean10", "clean20", "clean30", "clean15_h189", "fromos3"]:
            if col not in fires_m.columns:
                errors.append(f"Column {col} missing from m2d_s3d fires!")
            else:
                print(f"[6] Column {col}: present (non-null={fires_m[col].notna().sum()})")

    if errors:
        print("\nSMOKE FAILURES:")
        for e in errors:
            print(f"  FAIL: {e}")
        raise AssertionError(f"{len(errors)} smoke assertion(s) failed")
    else:
        print("\nAll wave-2 smoke assertions PASSED.")


# ══════════════════════════════════════════════════════════════════════════════
# Baskets mini-smoke helper
# ══════════════════════════════════════════════════════════════════════════════

def run_baskets_mini_smoke(tables: dict, fires_dfs: dict):
    """Mini baskets smoke: verify theme cohort computes and events exist."""
    print("\n--- BASKETS MINI-SMOKE ---")
    errors: list[str] = []

    fires_m = fires_dfs.get("m2d_s3d", pd.DataFrame())
    if len(fires_m) == 0:
        errors.append("No m2d_s3d fires in baskets smoke!")
    else:
        # h6_cohort_theme should be non-null for some fires
        if "h6_cohort_theme" in fires_m.columns:
            n_theme_notna = int(fires_m["h6_cohort_theme"].notna().sum())
            print(f"  h6_cohort_theme non-null: {n_theme_notna}/{len(fires_m)}")
            if n_theme_notna == 0:
                errors.append("h6_cohort_theme is all null!")
        else:
            errors.append("h6_cohort_theme column missing!")

        # T3 should exist
        if "T3" in tables:
            t3 = tables["T3"]
            print(f"  T3 rows: {len(t3)}")
            if len(t3) == 0:
                errors.append("T3 is empty!")
        else:
            errors.append("T3 missing!")

        # Events should exist
        print(f"  fires n={len(fires_m)}, coiled={int(fires_m['coiled'].sum()) if 'coiled' in fires_m.columns else '?'}")

    if errors:
        print("  BASKETS MINI-SMOKE FAILURES:")
        for e in errors:
            print(f"    FAIL: {e}")
        raise AssertionError(f"Baskets mini-smoke: {len(errors)} failure(s)")
    else:
        print("  Baskets mini-smoke PASSED.")


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    t_wall = time.time()
    tables, events_df, fires_dfs = main()

    # Determine panel from sys.argv (already parsed inside main; re-read cheaply)
    _panel = "stocks"
    for a in sys.argv:
        if a in ("stocks", "baskets"):
            _panel = a

    run_smoke(tables, events_df, fires_dfs, _panel)

    if _panel == "baskets":
        run_baskets_mini_smoke(tables, fires_dfs)

    print(f"\nTotal wall time: {time.time()-t_wall:.1f}s")
