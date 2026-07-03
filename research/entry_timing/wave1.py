"""wave1.py — Durable-Bottom Entry Timing Study, Wave 1

Spec: research/signal_engine/DURABLE_BOTTOM_FRAMEWORK.md §A-§G
Charter: research/signal_engine/CHARTER.md

Implements:
  A. Panel selection (>=1500 bars, eval from 2012-01-01, >=126 forward bars)
  B. Fire generation (base3d, m2d_s3d, m2d_s3d_early) + oracle (base3d only)
  C. Durable-bottom / trap event labeling (hindsight, evaluation only)
  D. Per-fire outcome metrics (stop5, clean15, dead_money, mae63, mfe63, days_to_10,
     plus secondary low_stop5)
  E. Feature computation (H1-H6, strictly causal at bar i)
  F. Output files (fires_<variant>.parquet, events.parquet, wave1_tables.json)
  G. Smoke test (run with --tickers AAPL,MSFT,JNJ,NVDA,WMT,XOM,KO,CAT)

Usage:
  python3 research/entry_timing/wave1.py [--tickers AAPL,MSFT,...] [--out research/entry_timing/_out]
"""
from __future__ import annotations

import sys
import time
import json
import argparse
import warnings
import logging
from pathlib import Path

import numpy as np
import pandas as pd

if __name__ == "__main__":
    # CLI-only silencers.  logging.disable() is PROCESS-GLOBAL state: at module level it
    # leaks out of any import of this file and mutes every logger for the rest of the
    # process (order-dependent pytest flakes; bitten twice — see walk_forward.py and
    # tests/test_no_module_level_logging_disable.py).
    warnings.filterwarnings("ignore")
    logging.disable(logging.CRITICAL)

# --- path bootstrap so we can import tuning_harness from anywhere ---
ROOT = Path(__file__).resolve().parents[2]
SIG_ENG = ROOT / "research" / "signal_engine"
sys.path.insert(0, str(SIG_ENG))

import tuning_harness as TH  # noqa: E402

DATA = ROOT / "data" / "stocks"
YAHOO = ROOT / "data" / "yahoo"
BREADTH = ROOT / "data" / "breadth"

# ─────────────────────────── constants ──────────────────────────────────────
MIN_BARS = 1500          # §A minimum close bars
EVAL_START = pd.Timestamp("2012-01-01")   # §A evaluation start
FWD_REQ = 126            # §A minimum forward bars after fill
DD_MIN = 0.15            # §C drawout precondition (B15)
DD_B30 = 0.30            # §C B30 label
DURABLE_HOLD = 0.97      # §C durability floor: no close < P0*0.97
LIFTOFF_126 = 1.20       # §C liftoff target within 126d
TROUGH_W = 10            # §C local minimum window
MIN_TROUGH_SEP = 15      # §C dedup threshold
CAPTURE = (-5, 15)       # §C capture window in trading days relative to t0
STOP5 = 0.95             # §D stop barrier (fill * 0.95)
CLEAN15 = 1.15           # §D clean-liftoff barrier
DEAD_MONEY_BAND = 0.08   # §D dead-money band (±8%)
DEAD_MONEY_CAP = 0.05    # §D dead-money 63d cap (<5%)
OUTCOME_W = 126          # §D forward window
MFE_MAE_W = 63           # §D MFE/MAE window

# H1 washout thresholds
H1_D_DEEP_THRESH = 25    # w2_deep / wk_deep: D < 25
H1_D3_THRESH = 30        # d3_frac60 threshold for D(3D) < 30
H1_D3_LOOKBACK = 60      # bars back for d3_frac60
H1_FRAC60_THRESH = 0.5   # d3_frac60 >= 0.5 => T

# H2 thresholds
H2_CAPIT_AGE = 15        # capit_age >= 15 bars
H2_ATR_CRUSH = 0.60      # atr_crush <= 0.6

# H3 swing low window
H3_SWING_W = 5           # confirmed swing lows window (w=5)
H3_LOOKBACK = 120        # bars back for swing low search

# H4 thresholds
H4_VOL_MIN = 252         # minimum non-null volume
H4_VOL_Z = 2.0           # capitulation spike z-score
H4_CAPIT_WINDOW = 10     # ±10 bars around capit_idx
H4_DRYUP = 0.80          # 20d / 126d volume ratio <= 0.80
H4_UPDOWN = 1.30         # updown10 >= 1.3

# H5 thresholds
H5_ENTRENCHED = 0.70     # fraction of 252d bars below 200MA
H5_FAILED_WINDOW = 180   # bars back for failed-fire count
H6_COHORT_MIN_PEERS = 5  # minimum peers for cohort
H6_COHORT_THRESH = 0.40  # fraction of peers with weekly D < 30

VARIANTS = ["base3d", "m2d_s3d", "m2d_s3d_early"]


# ══════════════════════════════════════════════════════════════════════════════
# §C: Durable-bottom / trap event labeling
# ══════════════════════════════════════════════════════════════════════════════

def label_events(daily: pd.Series) -> pd.DataFrame:
    """Find durable-bottom and trap events in `daily` (dividend-adjusted closes).

    Returns a DataFrame with columns:
      ticker, t0 (DatetimeIndex), p0, label, b30, dd_at_trough
    Only events with >= FWD_REQ forward bars are included (so we can apply
    liftoff / durability checks).

    Procedure (spec §C):
    1. Compute dd = close / close.rolling(126).max() - 1 (drawdown from 126d high)
    2. Find episodes = contiguous runs where dd <= -DD_MIN
    3. Within each episode find CONFIRMED local minima of close with window w=10
       (close[j] == min(close[j-10:j+11]))  — only j where j+10 < len is safe
    4. Dedup candidates < MIN_TROUGH_SEP bars apart keeping the lower close
    5. For each trough t0 with >= FWD_REQ forward bars compute durable/trap label
    """
    n = len(daily)
    c = daily.to_numpy()
    idx = daily.index

    # rolling 126-day max for drawdown (need 126 prior bars)
    roll126 = pd.Series(c, index=idx).rolling(126).max().to_numpy()
    dd = c / roll126 - 1  # negative values = drawdown

    # episodes: contiguous regions where dd <= -DD_MIN
    in_episode = dd <= -DD_MIN
    # find all confirmed local minima within episode regions
    W = TROUGH_W  # window half-width
    candidates = []
    for j in range(W, n - W):
        if not in_episode[j]:
            continue
        window = c[j - W: j + W + 1]
        if c[j] == window.min():
            candidates.append(j)

    if not candidates:
        return pd.DataFrame(columns=["t0", "p0", "label", "b30", "dd_at_trough"])

    # dedup: keep lower close when candidates < MIN_TROUGH_SEP apart
    deduped = [candidates[0]]
    for j in candidates[1:]:
        if j - deduped[-1] < MIN_TROUGH_SEP:
            # keep the lower close
            if c[j] < c[deduped[-1]]:
                deduped[-1] = j
        else:
            deduped.append(j)

    rows = []
    for j in deduped:
        # need >= FWD_REQ forward bars
        if j + FWD_REQ >= n:
            continue
        p0 = c[j]
        t0 = idx[j]
        dd_at = dd[j]

        # durability: no close < p0 * DURABLE_HOLD in the following FWD_REQ bars
        fwd = c[j + 1: j + FWD_REQ + 1]
        durable = bool(np.nanmin(fwd) >= p0 * DURABLE_HOLD)
        # liftoff: max close >= p0 * LIFTOFF_126 within FWD_REQ bars
        liftoff = bool(np.nanmax(c[j: j + FWD_REQ + 1]) >= p0 * LIFTOFF_126)

        label = "durable" if (durable and liftoff) else "trap"
        b30 = bool(dd_at <= -DD_B30)

        rows.append({
            "t0": t0,
            "p0": float(p0),
            "label": label,
            "b30": b30,
            "dd_at_trough": float(dd_at),
        })

    return pd.DataFrame(rows)


# ══════════════════════════════════════════════════════════════════════════════
# §D: Per-fire outcome computation
# ══════════════════════════════════════════════════════════════════════════════

def compute_outcomes(fill_idx: int, p: float, close_arr: np.ndarray,
                     high_arr: np.ndarray, low_arr: np.ndarray) -> dict:
    """Compute all §D outcome metrics for one fire.

    fill_idx: integer position in close_arr where fill occurs (i+1)
    p: fill price = close_arr[fill_idx]
    close_arr, high_arr, low_arr: full arrays (numpy, aligned)

    Returns dict including:
      resolution_idx: the bar index (in close_arr) at which stop5 resolved (i.e. the first bar
        where close <= stop_barrier OR close >= p*1.05, within fill_idx+1..fill_idx+OUTCOME_W).
        Set to fill_idx + OUTCOME_W if neither barrier was reached (exhaustion).
        Used by compute_features to ensure prior-fire failures resolved STRICTLY before bar i.
    """
    n = len(close_arr)
    stop_barrier = p * STOP5      # 0.95p
    clean_barrier = p * CLEAN15   # 1.15p

    # Walk f+1 .. f+OUTCOME_W (spec: strictly forward)
    stop5 = 0
    clean15 = 0
    stalled = 0
    days_to_10 = None
    target10 = p * 1.10

    # stop5 resolution: track the bar where the barrier race concluded
    stop5_resolution_idx = fill_idx + OUTCOME_W  # default: exhaustion at window end
    for k in range(fill_idx + 1, min(fill_idx + OUTCOME_W + 1, n)):
        cl = close_arr[k]
        # stop5: close <= stop_barrier STRICTLY before close >= p*1.05
        # tie on same bar -> stop (conservative, per spec)
        if cl <= stop_barrier:
            stop5 = 1
            stop5_resolution_idx = k
            break
        if cl >= p * 1.05:
            # reached +5% without hitting stop => stop5 stays 0
            stop5_resolution_idx = k
            break

    # clean15: close >= p*1.15 STRICTLY before close <= p*0.95
    for k in range(fill_idx + 1, min(fill_idx + OUTCOME_W + 1, n)):
        cl = close_arr[k]
        if cl >= clean_barrier:
            clean15 = 1
            break
        if cl <= stop_barrier:
            break

    # stalled: neither stop nor +5% within OUTCOME_W
    # (recompute from scratch to avoid dependency on above loop termination)
    hit_stop = False
    hit_plus5 = False
    for k in range(fill_idx + 1, min(fill_idx + OUTCOME_W + 1, n)):
        cl = close_arr[k]
        if cl <= stop_barrier:
            hit_stop = True
            break
        if cl >= p * 1.05:
            hit_plus5 = True
            break
    stalled = int(not hit_stop and not hit_plus5)

    # dead_money: over f+1..f+63 no close beyond ±8% AND close[f+63]/p < 1.05
    end63 = min(fill_idx + MFE_MAE_W + 1, n)
    window63 = close_arr[fill_idx + 1: end63]
    if len(window63) >= MFE_MAE_W:
        dead_upper = p * (1 + DEAD_MONEY_BAND)
        dead_lower = p * (1 - DEAD_MONEY_BAND)
        band_breached = bool(np.any(window63 >= dead_upper) or np.any(window63 <= dead_lower))
        ret63 = window63[-1] / p - 1
        dead_money = int((not band_breached) and (ret63 < DEAD_MONEY_CAP))
    else:
        dead_money = 0  # not enough data

    # mae63, mfe63 on f+1..f+63
    if len(window63) > 0:
        mae63 = float(np.nanmin(window63)) / p - 1
        mfe63 = float(np.nanmax(window63)) / p - 1
    else:
        mae63 = np.nan
        mfe63 = np.nan

    # days_to_10: first bar where close >= p*1.10 within OUTCOME_W
    for k in range(fill_idx + 1, min(fill_idx + OUTCOME_W + 1, n)):
        if close_arr[k] >= target10:
            days_to_10 = k - fill_idx
            break

    # secondary: low_stop5 — daily LOW <= stop_barrier STRICTLY before daily HIGH >= p*1.05
    low_stop5 = 0
    for k in range(fill_idx + 1, min(fill_idx + OUTCOME_W + 1, n)):
        lo_k = low_arr[k] if not np.isnan(low_arr[k]) else close_arr[k]
        hi_k = high_arr[k] if not np.isnan(high_arr[k]) else close_arr[k]
        if lo_k <= stop_barrier:
            low_stop5 = 1
            break
        if hi_k >= p * 1.05:
            break

    return {
        "stop5": stop5,
        "resolution_idx": stop5_resolution_idx,  # FIX-1: bar where stop5 race resolved (causal gate for H5)
        "clean15": clean15,
        "stalled": stalled,
        "dead_money": dead_money,
        "mae63": mae63,
        "mfe63": mfe63,
        "days_to_10": days_to_10,
        "low_stop5": low_stop5,
    }


# ══════════════════════════════════════════════════════════════════════════════
# §E: Feature computation (all causal at bar i)
# ══════════════════════════════════════════════════════════════════════════════

def build_tf_grids(daily: pd.Series, high: pd.Series, low: pd.Series,
                   spy_ratio: pd.Series | None):
    """Pre-compute all TF grids once per name. Returns a dict of arrays/series
    aligned to daily.index for O(1) feature lookup at each fire bar i."""
    idx = daily.index
    n = len(idx)
    c = daily.to_numpy()

    # ─── 3D TF ───────────────────────────────────────────────────────────────
    s3d, kn3d = TH.tf_bars(daily, 3)
    k3d, d3d = TH.stoch_rsi_kd(s3d)
    m3d, sig3d = TH.rsi_macd(s3d)
    d3d_daily = TH.to_daily(d3d, kn3d, idx, "ffill")   # D(3D) daily-mapped
    m3d_daily = TH.to_daily(m3d, kn3d, idx, "ffill")   # macd line
    sig3d_daily = TH.to_daily(sig3d, kn3d, idx, "ffill")

    # ─── 2D TF ───────────────────────────────────────────────────────────────
    s2d, kn2d = TH.tf_bars(daily, 2)
    k2d, d2d = TH.stoch_rsi_kd(s2d)
    m2d, sig2d = TH.rsi_macd(s2d)

    # ─── Weekly TF (W-FRI) ───────────────────────────────────────────────────
    sw = daily.resample("W-FRI").last().dropna()
    known_w = daily.resample("W-FRI").apply(
        lambda x: x.dropna().index.max()
    ).reindex(sw.index).dropna()
    sw = sw.reindex(known_w.index)
    kw, dw = TH.stoch_rsi_kd(sw)
    known_w_dt = pd.Series(pd.to_datetime(known_w.values), index=known_w.index)
    dw_daily = TH.to_daily(dw, known_w_dt, idx, "ffill")   # D(W) daily-mapped
    # FIX-2: rolling(6).min() on the TF-native weekly series BEFORE to_daily mapping,
    # so the 6-bar window spans exactly 6 weekly bars (~30 trading days), not 6 daily positions.
    dw_min6_tf = dw.rolling(6, min_periods=1).min()
    dw_min6_daily = TH.to_daily(dw_min6_tf, known_w_dt, idx, "ffill")  # min over 6 W-bars, daily-mapped

    # ─── 2-Week TF (2W-FRI) ──────────────────────────────────────────────────
    s2w = daily.resample("2W-FRI").last().dropna()
    known_2w = daily.resample("2W-FRI").apply(
        lambda x: x.dropna().index.max()
    ).reindex(s2w.index).dropna()
    s2w = s2w.reindex(known_2w.index)
    k2w, d2w = TH.stoch_rsi_kd(s2w)
    known_2w_dt = pd.Series(pd.to_datetime(known_2w.values), index=known_2w.index)
    d2w_daily = TH.to_daily(d2w, known_2w_dt, idx, "ffill")   # D(2W) daily-mapped
    # FIX-2: rolling(6).min() on the TF-native 2W series BEFORE to_daily mapping,
    # so the 6-bar window spans exactly 6 two-week bars (~60 trading days), not 6 daily positions.
    d2w_min6_tf = d2w.rolling(6, min_periods=1).min()
    d2w_min6_daily = TH.to_daily(d2w_min6_tf, known_2w_dt, idx, "ffill")  # min over 6 2W-bars, daily-mapped

    # ─── Monthly TF (ME) ─────────────────────────────────────────────────────
    sm = daily.resample("ME").last().dropna()
    known_m = daily.resample("ME").apply(
        lambda x: x.dropna().index.max()
    ).reindex(sm.index).dropna()
    sm = sm.reindex(known_m.index)
    mm, sigm = TH.rsi_macd(sm)
    known_m_dt = pd.Series(pd.to_datetime(known_m.values), index=known_m.index)
    mm_daily = TH.to_daily(mm, known_m_dt, idx, "ffill")   # monthly macd line
    sigm_daily = TH.to_daily(sigm, known_m_dt, idx, "ffill")  # monthly signal

    # ─── ATR% ────────────────────────────────────────────────────────────────
    # tr = max(high-low, |high-prev_close|, |low-prev_close|)
    hi_arr = high.reindex(idx).to_numpy()
    lo_arr = low.reindex(idx).to_numpy()
    prev_c = np.roll(c, 1)
    prev_c[0] = c[0]
    hl = np.where(np.isnan(hi_arr) | np.isnan(lo_arr), np.abs(np.diff(c, prepend=c[0])),
                  hi_arr - lo_arr)
    hpc = np.where(np.isnan(hi_arr), 0.0, np.abs(hi_arr - prev_c))
    lpc = np.where(np.isnan(lo_arr), 0.0, np.abs(lo_arr - prev_c))
    tr = np.maximum(hl, np.maximum(hpc, lpc))
    tr_s = pd.Series(tr, index=idx)
    atr = tr_s.ewm(alpha=1 / 14, min_periods=14).mean()
    atrp = (atr / daily).to_numpy()  # ATR as fraction of price

    # ─── 200-day MA ──────────────────────────────────────────────────────────
    ma200 = daily.rolling(200).mean().to_numpy()

    # ─── OBV (only if volume available) ──────────────────────────────────────
    vol = None
    obv = None
    if "volume" in daily.index.names:
        pass  # volume is a separate series, handled in caller

    return {
        # raw daily arrays
        "c": c,
        "hi_arr": hi_arr,
        "lo_arr": lo_arr,
        "idx": idx,
        "n": n,
        # 3D
        "d3d_daily": d3d_daily.to_numpy(),
        "m3d_daily": m3d_daily.to_numpy(),
        "sig3d_daily": sig3d_daily.to_numpy(),
        # W
        "dw_daily": dw_daily.to_numpy(),
        "dw_min6_daily": dw_min6_daily.to_numpy(),    # FIX-2: min over 6 W-bars, daily-mapped
        # 2W
        "d2w_daily": d2w_daily.to_numpy(),
        "d2w_min6_daily": d2w_min6_daily.to_numpy(),  # FIX-2: min over 6 2W-bars, daily-mapped
        # monthly
        "mm_daily": mm_daily.to_numpy(),
        "sigm_daily": sigm_daily.to_numpy(),
        # ATR%
        "atrp": atrp,
        # 200MA
        "ma200": ma200,
        # SPY ratio for H5 rs_low
        "spy_ratio": spy_ratio.reindex(idx, method="ffill").to_numpy() if spy_ratio is not None else None,
    }


def build_sector_d_matrix(panel_files: list[str], sector_map: dict[str, str]) -> dict:
    """Pre-compute per-ticker weekly D(W) daily-mapped arrays for H6 cohort feature.
    Returns {ticker: (daily_index, dw_arr)} dict.
    Only load tickers that have a sector in sector_map.
    """
    out = {}
    for fp in panel_files:
        t = Path(fp).stem
        try:
            df = pd.read_parquet(fp)
            daily = df["close"].dropna()
            if len(daily) < MIN_BARS:
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


def get_cohort_frac(ticker: str, bar_date: pd.Timestamp,
                    sector_map: dict[str, str],
                    sector_d_matrix: dict) -> float | None:
    """Return fraction of same-sector peers with weekly D < 30 at bar_date.
    Returns None if fewer than H6_COHORT_MIN_PEERS peers have data.
    """
    my_sector = sector_map.get(ticker)
    if my_sector is None:
        return None
    peers = [t for t, sec in sector_map.items() if sec == my_sector and t != ticker
             and t in sector_d_matrix]
    vals = []
    for p in peers:
        pidx, pdw = sector_d_matrix[p]
        # find last known value at or before bar_date
        pos = pidx.searchsorted(bar_date, side="right") - 1
        if pos < 0:
            continue
        v = pdw[pos]
        if not np.isnan(v):
            vals.append(v)
    if len(vals) < H6_COHORT_MIN_PEERS:
        return None
    return float(np.mean(np.array(vals) < 30))


def compute_features(i: int, grids: dict, vol_arr: np.ndarray | None,
                     variant_fires_before: list[dict]) -> dict:
    """Compute all H1-H6 features for fire at signal bar index i.

    All references are to data with timestamp <= grids['idx'][i] (causal).
    variant_fires_before: list of outcome dicts for THIS variant's prior fires on this name
                          (used for H5 failed_180 feature). Each dict has keys: fill_idx, stop5.
    """
    c = grids["c"]
    n = grids["n"]
    idx = grids["idx"]
    hi_arr = grids["hi_arr"]
    lo_arr = grids["lo_arr"]
    d3d = grids["d3d_daily"]
    m3d = grids["m3d_daily"]
    sig3d = grids["sig3d_daily"]
    dw = grids["dw_daily"]
    d2w = grids["d2w_daily"]
    mm = grids["mm_daily"]
    sigm = grids["sigm_daily"]
    atrp = grids["atrp"]
    ma200 = grids["ma200"]
    spy_ratio = grids["spy_ratio"]

    feat: dict = {}

    # ── H1: Multi-TF washout state ─────────────────────────────────────────
    # FIX-2: w2_d_min6 is now drawn from d2w_min6_daily — a rolling(6).min() computed
    # on the TF-native 2W series before to_daily mapping.  Each position in this array
    # already reflects the minimum D(2W) over the trailing 6 two-week bars (≈60 trading
    # days), so a simple point-in-time lookup at [i] is correct and causal.
    d2w_min6_arr = grids["d2w_min6_daily"]
    d2w_min6 = float(d2w_min6_arr[i]) if not np.isnan(d2w_min6_arr[i]) else np.nan

    feat["w2_d_min6"] = d2w_min6
    feat["w2_deep"] = bool(not np.isnan(d2w_min6) and d2w_min6 < H1_D_DEEP_THRESH)

    # FIX-2: wk_d_min6 likewise drawn from dw_min6_daily — rolling(6).min() on the
    # TF-native weekly series; each position spans ≈30 trading days (6 weekly bars).
    dw_min6_arr = grids["dw_min6_daily"]
    dw_min6 = float(dw_min6_arr[i]) if not np.isnan(dw_min6_arr[i]) else np.nan

    feat["wk_d_min6"] = dw_min6
    feat["wk_deep"] = bool(not np.isnan(dw_min6) and dw_min6 < H1_D_DEEP_THRESH)

    # d3_frac60: fraction of last 60 daily bars where D(3D) < 30
    start60 = max(0, i - H1_D3_LOOKBACK + 1)
    window60 = d3d[start60: i + 1]
    valid60 = window60[~np.isnan(window60)]
    feat["d3_frac60"] = float(np.mean(valid60 < H1_D3_THRESH)) if len(valid60) > 0 else np.nan

    # washout_depth: mean of (100-D)/100 across 2W, W, 3D at i
    d2w_i = d2w[i]
    dw_i = dw[i]
    d3d_i = d3d[i]
    legs = []
    for v in [d2w_i, dw_i, d3d_i]:
        if not np.isnan(v):
            legs.append((100 - v) / 100)
    feat["washout_depth"] = float(np.mean(legs)) if legs else np.nan

    # ── H2: Washout age + basing calm ─────────────────────────────────────
    # capit_idx = argmin(close[i-90:i+1])
    start90 = max(0, i - 90)
    window90 = c[start90: i + 1]
    local_argmin = int(np.argmin(window90))
    capit_idx = start90 + local_argmin
    capit_age = i - capit_idx
    feat["capit_age"] = capit_age

    # dd_at_capit: requires 126 bars before capit_idx
    if capit_idx >= 126:
        prior_max = np.nanmax(c[capit_idx - 126: capit_idx])
        dd_at_capit = c[capit_idx] / prior_max - 1 if prior_max > 0 else np.nan
    else:
        dd_at_capit = None
    feat["dd_at_capit"] = dd_at_capit

    in_washout_ctx = bool(dd_at_capit is not None and dd_at_capit <= -DD_MIN)
    feat["in_washout_ctx"] = in_washout_ctx

    # ATR crush: atrp[i] / max(atrp[capit_idx:i+1])
    if capit_idx <= i:
        atrp_window = atrp[capit_idx: i + 1]
        atrp_max = np.nanmax(atrp_window) if len(atrp_window) > 0 else np.nan
        atr_crush = atrp[i] / atrp_max if (not np.isnan(atrp_max) and atrp_max > 0) else np.nan
    else:
        atr_crush = np.nan
    feat["atr_crush"] = atr_crush

    h2_good = bool(
        in_washout_ctx
        and capit_age >= H2_CAPIT_AGE
        and not np.isnan(atr_crush)
        and atr_crush <= H2_ATR_CRUSH
    )
    feat["h2_good"] = h2_good

    # ── H3: Bullish momentum divergence ────────────────────────────────────
    # Confirmed swing lows on daily close with w=5:
    # low j confirmed only when i >= j+5
    # Spec: among confirmed lows with j in [i-120, i], take last two L1 (earlier), L2 (later)
    w_sw = H3_SWING_W
    sw_lo_candidates = []
    start_h3 = max(w_sw, i - H3_LOOKBACK)
    # confirmed means we need j+w_sw <= i
    for j in range(start_h3, i - w_sw + 1):
        lo_j = c[j - w_sw: j + w_sw + 1]
        if len(lo_j) < 2 * w_sw + 1:
            continue
        if c[j] == lo_j.min():
            sw_lo_candidates.append(j)

    bull_div = False
    bull_div_macd = False
    bull_div_stoch = False
    feat["L1_date"] = None
    feat["L2_date"] = None

    if len(sw_lo_candidates) >= 2:
        L1 = sw_lo_candidates[-2]
        L2 = sw_lo_candidates[-1]
        feat["L1_date"] = str(idx[L1].date())
        feat["L2_date"] = str(idx[L2].date())

        # bull_div_macd: close LL AND 3D macd line HL at L1 vs L2
        if c[L2] < c[L1]:
            bull_div_macd = bool(m3d[L2] > m3d[L1])
            bull_div_stoch = bool(d3d[L2] > d3d[L1])
            bull_div = bool(bull_div_macd or bull_div_stoch)

    feat["bull_div"] = bull_div
    feat["bull_div_macd"] = bull_div_macd
    feat["bull_div_stoch"] = bull_div_stoch

    # ── H4: Volume / participation ─────────────────────────────────────────
    has_vol = (vol_arr is not None and np.sum(~np.isnan(vol_arr[:i + 1])) >= H4_VOL_MIN)

    feat["capit_spike"] = None
    feat["dryup"] = None
    feat["updown10"] = None
    feat["updown_good"] = None
    feat["obv_div"] = None

    if has_vol:
        v = vol_arr  # aligned to daily index

        # vol_z on trailing 63-day window
        v_roll_mean = pd.Series(v).rolling(63).mean().to_numpy()
        v_roll_std = pd.Series(v).rolling(63).std().to_numpy()

        # capit_spike: any vol_z >= 2 within [capit_idx-10, min(capit_idx+10, i)]
        spike_start = max(0, capit_idx - H4_CAPIT_WINDOW)
        spike_end = min(capit_idx + H4_CAPIT_WINDOW, i) + 1
        capit_spike = False
        for k in range(spike_start, spike_end):
            if k >= len(v) or np.isnan(v[k]) or np.isnan(v_roll_mean[k]) or np.isnan(v_roll_std[k]):
                continue
            std_k = v_roll_std[k]
            if std_k > 0:
                z = (v[k] - v_roll_mean[k]) / std_k
                if z >= H4_VOL_Z:
                    capit_spike = True
                    break
        feat["capit_spike"] = capit_spike

        # FIX-3: dryup per spec framework line 228: 20d MEDIAN volume PERCENTILE < 40
        # vs the 126d volume distribution.  That is: what percentile of the 126d volume
        # distribution does the 20d median fall at?  If that percentile < 40 => dry-up.
        # The old code used mean(v20)/mean(v126) <= 0.80, which is a different statistic.
        v20_start = max(0, i - 20)
        v126_start = max(0, i - 126)
        v20 = v[v20_start: i + 1]
        v126 = v[v126_start: i + 1]
        v20_valid = v20[~np.isnan(v20)]
        v126_valid = v126[~np.isnan(v126)]
        if len(v20_valid) > 0 and len(v126_valid) >= 10:
            med20 = float(np.median(v20_valid))
            # percentile rank of med20 within the 126d distribution (fraction below)
            pct_rank = float(np.mean(v126_valid < med20))
            feat["dryup"] = bool(pct_rank < 0.40)
        else:
            feat["dryup"] = None

        # updown10: dollar volume ratio (up-close vs down-close days in last 10 bars)
        dv = v * c  # dollar volume array
        up_dv = 0.0
        dn_dv = 0.0
        for k in range(max(0, i - 9), i + 1):
            if k == 0 or np.isnan(v[k]) or np.isnan(c[k]):
                continue
            if c[k] > c[k - 1]:
                up_dv += dv[k]
            else:
                dn_dv += dv[k]
        updown10 = up_dv / dn_dv if dn_dv > 0 else np.nan
        feat["updown10"] = float(updown10) if not np.isnan(updown10) else None
        feat["updown_good"] = bool(not np.isnan(updown10) and updown10 >= H4_UPDOWN)

        # OBV: cumsum(sign(close.diff())*vol)
        diff_c = np.diff(c, prepend=c[0])
        sign_c = np.sign(diff_c)
        sign_c[0] = 0
        obv_arr = np.nancumsum(sign_c * np.where(np.isnan(v), 0, v))

        # obv_div at L1/L2: close LL AND OBV HL
        obv_div = False
        if len(sw_lo_candidates) >= 2:
            L1 = sw_lo_candidates[-2]
            L2 = sw_lo_candidates[-1]
            if c[L2] < c[L1]:
                obv_div = bool(obv_arr[L2] > obv_arr[L1])
        feat["obv_div"] = obv_div

    # ── H5: Trap context ─────────────────────────────────────────────────────
    # trap_m: monthly RSI-MACD below signal AND falling
    mm_i = mm[i]
    sigm_i = sigm[i]
    # need to find the prior MONTHLY bar's macd value
    # Since mm is daily-mapped (ffill), we need to look back to the previous monthly bar boundary
    # The spec says "one MONTHLY bar earlier" - find the last change in mm_daily
    mm_prev = np.nan
    for k in range(i - 1, max(0, i - 30) - 1, -1):
        if mm[k] != mm_i and not np.isnan(mm[k]):
            mm_prev = mm[k]
            break

    trap_m = bool(
        not np.isnan(mm_i) and not np.isnan(sigm_i)
        and mm_i < sigm_i
        and not np.isnan(mm_prev)
        and mm_i < mm_prev
    )
    feat["trap_m"] = trap_m

    # pct_below200_252: fraction of last 252 bars with close < ma200
    start_252 = max(0, i - 251)
    window_252 = c[start_252: i + 1]
    ma200_252 = ma200[start_252: i + 1]
    valid_mask = ~np.isnan(ma200_252)
    if np.sum(valid_mask) > 0:
        pct_below200_252 = float(np.mean(window_252[valid_mask] < ma200_252[valid_mask]))
    else:
        pct_below200_252 = np.nan
    feat["pct_below200_252"] = pct_below200_252
    feat["entrenched"] = bool(not np.isnan(pct_below200_252) and pct_below200_252 >= H5_ENTRENCHED)

    # ma200_dn: ma200[i] < ma200[i-20]
    if i >= 20 and not np.isnan(ma200[i]) and not np.isnan(ma200[i - 20]):
        feat["ma200_dn"] = bool(ma200[i] < ma200[i - 20])
    else:
        feat["ma200_dn"] = None

    # FIX-1: failed_180 — number of THIS variant's own fires in the last 180 bars
    # that hit stop5, with the additional guard that the stop5 barrier race RESOLVED
    # strictly before bar i.  Without this guard, fires whose stop5 resolution falls
    # at or after bar i contribute future-information to the count (the prior version
    # only checked fill_idx < i, but resolution can be fill_idx + up to OUTCOME_W bars
    # later, which is fully forward-looking).  The guard is: vf['resolution_idx'] < i.
    failed_180 = 0
    for vf in variant_fires_before:
        lag = i - vf["fill_idx"]
        if (0 < lag <= H5_FAILED_WINDOW
                and vf["stop5"] == 1
                and vf["resolution_idx"] < i):   # causal: resolution known before bar i
            failed_180 += 1
    feat["failed_180"] = failed_180
    feat["failed2"] = bool(failed_180 >= 2)

    # rs_low: close/SPY ratio made a 126d low within last 10 bars
    rs_low = False
    if spy_ratio is not None:
        spy_ratio_i = spy_ratio[i]
        if not np.isnan(spy_ratio_i):
            rs_start = max(0, i - 126)
            rs_window = spy_ratio[rs_start: i + 1]
            rs_min = np.nanmin(rs_window)
            # check if the 126d low was hit within last 10 bars
            for k in range(max(0, i - 9), i + 1):
                if not np.isnan(spy_ratio[k]) and spy_ratio[k] <= rs_min * 1.001:
                    rs_low = True
                    break
    feat["rs_low"] = rs_low

    # trap_state: trap_m AND (entrenched OR ma200_dn)
    feat["trap_state"] = bool(
        trap_m
        and (feat["entrenched"] or (feat["ma200_dn"] is True))
    )

    return feat


# ══════════════════════════════════════════════════════════════════════════════
# §B + §D + §E: Per-name fire generation
# ══════════════════════════════════════════════════════════════════════════════

def process_name(ticker: str, fp: str,
                 spy_ratio: pd.Series | None,
                 sector_map: dict[str, str],
                 sector_d_matrix: dict,
                 variants: list[str]) -> dict:
    """Process one ticker: generate fires for all variants, compute outcomes + features.

    Returns:
      {variant_name: [fire_row_dict, ...], "events": [event_row_dict, ...]}
    """
    df = pd.read_parquet(fp)
    daily = df["close"].dropna()
    if len(daily) < MIN_BARS:
        return {}

    hi = df["high"].reindex(daily.index) if "high" in df.columns else pd.Series(np.nan, index=daily.index)
    lo = df["low"].reindex(daily.index) if "low" in df.columns else pd.Series(np.nan, index=daily.index)
    vol = df["volume"].reindex(daily.index) if "volume" in df.columns else None

    c = daily.to_numpy()
    hi_arr = hi.to_numpy()
    lo_arr = lo.to_numpy()
    vol_arr = vol.to_numpy() if vol is not None else None
    idx = daily.index
    n = len(c)

    # §C: label events
    events_df = label_events(daily)
    events_df["ticker"] = ticker

    # Precompute capture window index ranges per event
    # capture window: [t0-5, t0+15] trading days
    event_windows = []
    for _, ev in events_df.iterrows():
        t0 = ev["t0"]
        t0_pos = idx.searchsorted(t0, side="left")
        w_start = t0_pos + CAPTURE[0]
        w_end = t0_pos + CAPTURE[1]
        event_windows.append({
            "t0_pos": t0_pos,
            "w_start": w_start,
            "w_end": w_end,
            "label": ev["label"],
            "p0": ev["p0"],
            "b30": ev["b30"],
            "dd_at_trough": ev["dd_at_trough"],
        })

    # Build TF grids once
    grids = build_tf_grids(daily, hi, lo, spy_ratio)

    # Compute SPY ratio for rs_low (already in grids["spy_ratio"])
    # (spy_ratio is passed in aligned to daily.index)

    result = {"events": events_df.to_dict("records")}

    for variant_name in variants:
        cfg = TH.VARIANTS[variant_name]
        frame = TH.build_signals(daily, cfg, hi, lo)
        raw_fires = frame.index[frame["buy"]].tolist()

        # oracle (base3d only): forward-peeking keeper-selected subset
        oracle_take_set = set()
        if variant_name == "base3d":
            oracle_series = TH.daily_filter(frame)
            oracle_take_set = set(frame.index[oracle_series].tolist())

        fire_rows = []
        # track prior fires for H5 failed_180 feature
        variant_fires_before: list[dict] = []

        for sig_date in raw_fires:
            i = idx.get_loc(sig_date)

            # §A eval filter: fill date >= EVAL_START AND >= FWD_REQ forward bars
            fill_idx = i + 1
            if fill_idx >= n:
                continue
            fill_date = idx[fill_idx]
            if fill_date < EVAL_START:
                # still track prior fires for failed_180 (even pre-EVAL_START)
                variant_fires_before.append({
                    "fill_idx": fill_idx,
                    "sig_idx": i,
                    "stop5": 0,          # placeholder, will be computed for pre-eval fires too
                    "resolution_idx": fill_idx + OUTCOME_W,  # FIX-1: default to exhaustion
                })
                # compute outcomes even for pre-eval fires for failed_180 tracking
                if fill_idx + FWD_REQ < n:
                    out_pre = compute_outcomes(fill_idx, c[fill_idx], c, hi_arr, lo_arr)
                    variant_fires_before[-1]["stop5"] = out_pre["stop5"]
                    variant_fires_before[-1]["resolution_idx"] = out_pre["resolution_idx"]  # FIX-1
                continue

            if fill_idx + FWD_REQ >= n:
                continue  # not enough forward bars

            p = c[fill_idx]
            if np.isnan(p):
                continue

            # §D: outcomes
            outcomes = compute_outcomes(fill_idx, p, c, hi_arr, lo_arr)

            # §E: features (causal at bar i)
            features = compute_features(i, grids, vol_arr, variant_fires_before)

            # §H6 cohort (added here from precomputed matrix)
            h6_cohort = get_cohort_frac(ticker, sig_date, sector_map, sector_d_matrix)
            features["h6_cohort"] = h6_cohort

            # Event linkage: is fire bar i in any event's capture window?
            captured = False
            ev_label = None
            premium = None
            lead = None
            for ew in event_windows:
                if ew["w_start"] <= i <= ew["w_end"]:
                    captured = True
                    ev_label = ew["label"]
                    premium = p / ew["p0"] - 1 if ew["p0"] > 0 else None
                    lead = i - ew["t0_pos"]
                    break  # first matching event

            row = {
                "ticker": ticker,
                "sig_date": sig_date,
                "fill_date": fill_date,
                "p": p,
                # outcomes
                **outcomes,
                # features
                **features,
                # event linkage
                "captured": captured,
                "ev_label": ev_label,
                "premium": premium,
                "lead": lead,
            }

            if variant_name == "base3d":
                row["oracle_take"] = bool(sig_date in oracle_take_set)

            fire_rows.append(row)

            # update prior fires list for failed_180 tracking
            variant_fires_before.append({
                "fill_idx": fill_idx,
                "sig_idx": i,
                "stop5": outcomes["stop5"],
                "resolution_idx": outcomes["resolution_idx"],  # FIX-1: causal gate for H5
            })

        result[variant_name] = fire_rows

    return result


# ══════════════════════════════════════════════════════════════════════════════
# §F: Rate computation helpers
# ══════════════════════════════════════════════════════════════════════════════

def pct(x: float | None) -> float:
    """Round to 2 decimal places as a percentage."""
    if x is None or np.isnan(x):
        return float("nan")
    return round(float(x) * 100, 2)


def rate(series: pd.Series, col: str) -> float:
    """Mean of a boolean/0-1 column as a percentage."""
    if len(series) == 0:
        return float("nan")
    vals = series[col].dropna()
    if len(vals) == 0:
        return float("nan")
    return round(float(vals.mean()) * 100, 2)


def med(series: pd.Series, col: str) -> float:
    """Median of a numeric column."""
    if len(series) == 0:
        return float("nan")
    vals = series[col].dropna()
    if len(vals) == 0:
        return float("nan")
    return round(float(vals.median()), 4)


def compute_headline(fires: pd.DataFrame, events: pd.DataFrame,
                     variant_name: str) -> dict:
    """Compute §F headline block for one variant."""
    n_fires = len(fires)

    # Recall: % of durable B15 events with >=1 fire in their window
    # "B15" = all durable events (the label already requires dd <= -15%)
    dur_events = events[events["label"] == "durable"]
    trap_events = events[events["label"] == "trap"]

    def event_has_fire(ev_label_filter: pd.DataFrame) -> float:
        if len(ev_label_filter) == 0:
            return float("nan")
        hit = 0
        for _, ev in ev_label_filter.iterrows():
            ticker = ev["ticker"]
            t0 = ev["t0"]
            t0_pos_in_fires = fires[
                (fires["ticker"] == ticker)
                & (fires["captured"])
                & (fires["ev_label"] == ev["label"])
            ]
            # Rough: check if any fire from this ticker is "captured" near this event
            # More precise: check capture window overlap directly
            ticker_fires = fires[fires["ticker"] == ticker]
            t0_idx_approx = None  # We'll do it by checking ev_label match
            # Simpler: a fire is captured by THIS event if its lead/premium would
            # match. We trust the linkage already done in process_name.
            # Actually per the spec capture is first-match, so we just need to count
            # events that have at least one fire in [t0-5, t0+15].
            # We use the full fires data (which includes captures across all events).
            # Build from the raw: re-check capture for this specific event.
            cap_fires_for_ev = fires[
                (fires["ticker"] == ticker)
                & (fires["ev_label"] == ev["label"])
                & (fires["captured"])
            ]
            # Filter by sig_date within capture window of THIS t0
            # We need the t0 position in the daily index — approximate via date comparison
            cap_fires_for_ev_t = cap_fires_for_ev[
                (cap_fires_for_ev["sig_date"] >= t0 - pd.Timedelta(days=10))
                & (cap_fires_for_ev["sig_date"] <= t0 + pd.Timedelta(days=25))
            ]
            if len(cap_fires_for_ev_t) > 0:
                hit += 1
        return hit / len(ev_label_filter)

    recall_B15 = event_has_fire(dur_events)
    recall_B30 = event_has_fire(dur_events[dur_events["b30"]])
    trap_fire_rate = event_has_fire(trap_events)

    # precision: % of fires captured by a durable event window
    if n_fires > 0:
        precision = round(float((fires["captured"] & (fires["ev_label"] == "durable")).mean()) * 100, 2)
    else:
        precision = float("nan")

    # median premium and lead for captured durable fires
    captured_dur = fires[fires["captured"] & (fires["ev_label"] == "durable")]
    med_premium = med(captured_dur, "premium")
    med_lead = med(captured_dur, "lead")

    # stop5, low_stop5, clean15, dead_money, stalled
    stop5 = rate(fires, "stop5")
    low_stop5 = rate(fires, "low_stop5")
    clean15 = rate(fires, "clean15")
    dead_money = rate(fires, "dead_money")
    stalled = rate(fires, "stalled")

    return {
        "n_fires": n_fires,
        "recall_B15": round(recall_B15 * 100, 2) if not np.isnan(recall_B15) else float("nan"),
        "recall_B30": round(recall_B30 * 100, 2) if not np.isnan(recall_B30) else float("nan"),
        "precision": precision,
        "trap_fire_rate": round(trap_fire_rate * 100, 2) if not np.isnan(trap_fire_rate) else float("nan"),
        "med_premium": round(med_premium * 100, 2) if not np.isnan(med_premium) else float("nan"),
        "med_lead": med_lead,
        "stop5": stop5,
        "low_stop5": low_stop5,
        "clean15": clean15,
        "dead_money": dead_money,
        "stalled": stalled,
    }


def stratum_row(df: pd.DataFrame, label: str, events_for_recall: pd.DataFrame | None = None,
                events_for_trap: pd.DataFrame | None = None) -> dict:
    """Build a per-stratum row from a fires sub-dataframe."""
    n = len(df)
    if n == 0:
        return {"n": 0, "label": label}

    row = {
        "label": label,
        "n": n,
        "stop5": rate(df, "stop5"),
        "low_stop5": rate(df, "low_stop5"),
        "clean15": rate(df, "clean15"),
        "dead_money": rate(df, "dead_money"),
        "med_mfe63": round(float(df["mfe63"].dropna().median()) * 100, 2) if len(df["mfe63"].dropna()) > 0 else float("nan"),
        "med_mae63": round(float(df["mae63"].dropna().median()) * 100, 2) if len(df["mae63"].dropna()) > 0 else float("nan"),
        "med_days_to_10": float(df["days_to_10"].dropna().median()) if len(df["days_to_10"].dropna()) > 0 else float("nan"),
    }

    # recall and trap_fire_rate: if events are provided, compute recall for this stratum
    # (fires_in_stratum: if a durable event has >=1 fire in this stratum within its window)
    # Simplified: "recall_B15_if_only_this_stratum" = fraction of durable events that
    # have at least one fire in this stratum's rows
    if events_for_recall is not None and len(events_for_recall) > 0:
        hit = 0
        for _, ev in events_for_recall.iterrows():
            ticker = ev["ticker"]
            t0 = ev["t0"]
            strat_t = df[
                (df["ticker"] == ticker)
                & (df["captured"])
                & (df["ev_label"] == "durable")
                & (df["sig_date"] >= t0 - pd.Timedelta(days=10))
                & (df["sig_date"] <= t0 + pd.Timedelta(days=25))
            ]
            if len(strat_t) > 0:
                hit += 1
        row["recall_B15_if_only_this_stratum"] = round(hit / len(events_for_recall) * 100, 2)
    else:
        row["recall_B15_if_only_this_stratum"] = float("nan")

    if events_for_trap is not None and len(events_for_trap) > 0:
        hit = 0
        for _, ev in events_for_trap.iterrows():
            ticker = ev["ticker"]
            t0 = ev["t0"]
            strat_t = df[
                (df["ticker"] == ticker)
                & (df["captured"])
                & (df["ev_label"] == "trap")
                & (df["sig_date"] >= t0 - pd.Timedelta(days=10))
                & (df["sig_date"] <= t0 + pd.Timedelta(days=25))
            ]
            if len(strat_t) > 0:
                hit += 1
        row["trap_fire_rate_if_only_this_stratum"] = round(hit / len(events_for_trap) * 100, 2)
    else:
        row["trap_fire_rate_if_only_this_stratum"] = float("nan")

    return row


def compute_strata(fires: pd.DataFrame, events: pd.DataFrame,
                   variant_name: str) -> list[dict]:
    """Compute per-stratum rows (spec §F(2))."""
    dur_events = events[events["label"] == "durable"]
    trap_events = events[events["label"] == "trap"]

    strata = []

    # ALL
    strata.append(stratum_row(fires, "ALL", dur_events, trap_events))

    # oracle_take (base3d only)
    if variant_name == "base3d" and "oracle_take" in fires.columns:
        strata.append(stratum_row(fires[fires["oracle_take"]], "oracle (forward-peeking)",
                                  dur_events, trap_events))

    # w2_deep T/F
    for val, lbl in [(True, "w2_deep=T"), (False, "w2_deep=F")]:
        strata.append(stratum_row(fires[fires["w2_deep"] == val], lbl, dur_events, trap_events))

    # wk_deep T/F
    for val, lbl in [(True, "wk_deep=T"), (False, "wk_deep=F")]:
        strata.append(stratum_row(fires[fires["wk_deep"] == val], lbl, dur_events, trap_events))

    # d3_frac60 >= 0.5 T/F
    frac_mask = fires["d3_frac60"].notna()
    strata.append(stratum_row(fires[frac_mask & (fires["d3_frac60"] >= 0.5)],
                              "d3_frac60>=0.5=T", dur_events, trap_events))
    strata.append(stratum_row(fires[frac_mask & (fires["d3_frac60"] < 0.5)],
                              "d3_frac60>=0.5=F", dur_events, trap_events))

    # in_washout_ctx T/F
    for val, lbl in [(True, "in_washout_ctx=T"), (False, "in_washout_ctx=F")]:
        strata.append(stratum_row(fires[fires["in_washout_ctx"] == val], lbl, dur_events, trap_events))

    # h2_good vs (in_washout_ctx AND NOT h2_good) vs NOT in_washout_ctx
    strata.append(stratum_row(fires[fires["h2_good"]], "h2_good=T", dur_events, trap_events))
    strata.append(stratum_row(
        fires[fires["in_washout_ctx"] & ~fires["h2_good"]],
        "in_washout_ctx AND NOT h2_good", dur_events, trap_events
    ))
    strata.append(stratum_row(fires[~fires["in_washout_ctx"]], "NOT in_washout_ctx", dur_events, trap_events))

    # bull_div T/F
    for val, lbl in [(True, "bull_div=T"), (False, "bull_div=F")]:
        strata.append(stratum_row(fires[fires["bull_div"] == val], lbl, dur_events, trap_events))

    # volume features (may be None)
    vol_notna = fires["capit_spike"].notna()
    for col, lbl in [("capit_spike", "capit_spike=T"), ("dryup", "dryup=T"),
                     ("updown_good", "updown_good=T"), ("obv_div", "obv_div=T")]:
        notna = fires[col].notna()
        strata.append(stratum_row(fires[notna & (fires[col] == True)], lbl, dur_events, trap_events))  # noqa: E712
        strata.append(stratum_row(fires[notna & (fires[col] == False)], f"{col}=F", dur_events, trap_events))  # noqa: E712

    # trap_state T/F
    for val, lbl in [(True, "trap_state=T"), (False, "trap_state=F")]:
        strata.append(stratum_row(fires[fires["trap_state"] == val], lbl, dur_events, trap_events))

    # failed2 T/F
    for val, lbl in [(True, "failed2=T"), (False, "failed2=F")]:
        strata.append(stratum_row(fires[fires["failed2"] == val], lbl, dur_events, trap_events))

    # rs_low T/F
    for val, lbl in [(True, "rs_low=T"), (False, "rs_low=F")]:
        strata.append(stratum_row(fires[fires["rs_low"] == val], lbl, dur_events, trap_events))

    # h6_cohort T/F/None (only among in_washout_ctx fires)
    wc_fires = fires[fires["in_washout_ctx"]]
    h6_notna = wc_fires["h6_cohort"].notna()
    h6_t = wc_fires[h6_notna & (wc_fires["h6_cohort"] >= H6_COHORT_THRESH)]
    h6_f = wc_fires[h6_notna & (wc_fires["h6_cohort"] < H6_COHORT_THRESH)]
    strata.append(stratum_row(h6_t, "h6_cohort=T (in_washout)", dur_events, trap_events))
    strata.append(stratum_row(h6_f, "h6_cohort=F (in_washout)", dur_events, trap_events))
    strata.append(stratum_row(wc_fires[~h6_notna], "h6_cohort=None (in_washout)", dur_events, trap_events))

    return strata


def compute_split_checks(fires: pd.DataFrame, strata_labels: list[str],
                         ticker_list: list[str]) -> list[dict]:
    """Compute clean15 spread sign-agreement across ticker and time halves (spec §F(3))."""
    # Ticker halves: even/odd of sorted ticker list
    sorted_tickers = sorted(ticker_list)
    half_a = set(sorted_tickers[::2])
    half_b = set(sorted_tickers[1::2])
    fires_a = fires[fires["ticker"].isin(half_a)]
    fires_b = fires[fires["ticker"].isin(half_b)]

    # Time halves: fill_date < 2020-01-01 vs >=
    time_cut = pd.Timestamp("2020-01-01")
    fires_pre = fires[fires["fill_date"] < time_cut]
    fires_post = fires[fires["fill_date"] >= time_cut]

    # For each stratum pair (favorable, unfavorable), compute spread on both halves
    # We'll match stratum labels by convention:
    # pairs = [(fav_label, unfav_label), ...]
    split_rows = []

    # Hardcoded pairs from the spec
    pairs = [
        ("w2_deep=T", "w2_deep=F"),
        ("wk_deep=T", "wk_deep=F"),
        ("d3_frac60>=0.5=T", "d3_frac60>=0.5=F"),
        ("in_washout_ctx=T", "in_washout_ctx=F"),
        ("h2_good=T", "in_washout_ctx AND NOT h2_good"),
        ("bull_div=T", "bull_div=F"),
        ("capit_spike=T", "capit_spike=F"),
        ("dryup=T", "dryup=F"),
        ("updown_good=T", "updown_good=F"),
        ("obv_div=T", "obv_div=F"),
        ("trap_state=F", "trap_state=T"),  # favorable = no trap
        ("failed2=F", "failed2=T"),
        ("rs_low=T", "rs_low=F"),
        ("h6_cohort=T (in_washout)", "h6_cohort=F (in_washout)"),
    ]

    def get_mask(df: pd.DataFrame, label: str) -> pd.Series:
        """Reconstruct mask for a stratum label from fires columns."""
        if label == "w2_deep=T":
            return df["w2_deep"] == True  # noqa: E712
        elif label == "w2_deep=F":
            return df["w2_deep"] == False  # noqa: E712
        elif label == "wk_deep=T":
            return df["wk_deep"] == True  # noqa: E712
        elif label == "wk_deep=F":
            return df["wk_deep"] == False  # noqa: E712
        elif label == "d3_frac60>=0.5=T":
            return df["d3_frac60"].notna() & (df["d3_frac60"] >= 0.5)
        elif label == "d3_frac60>=0.5=F":
            return df["d3_frac60"].notna() & (df["d3_frac60"] < 0.5)
        elif label == "in_washout_ctx=T":
            return df["in_washout_ctx"] == True  # noqa: E712
        elif label == "in_washout_ctx=F":
            return df["in_washout_ctx"] == False  # noqa: E712
        elif label == "h2_good=T":
            return df["h2_good"] == True  # noqa: E712
        elif label == "in_washout_ctx AND NOT h2_good":
            return df["in_washout_ctx"] & ~df["h2_good"]
        elif label == "bull_div=T":
            return df["bull_div"] == True  # noqa: E712
        elif label == "bull_div=F":
            return df["bull_div"] == False  # noqa: E712
        elif label == "capit_spike=T":
            return df["capit_spike"].notna() & (df["capit_spike"] == True)  # noqa: E712
        elif label == "capit_spike=F":
            return df["capit_spike"].notna() & (df["capit_spike"] == False)  # noqa: E712
        elif label == "dryup=T":
            return df["dryup"].notna() & (df["dryup"] == True)  # noqa: E712
        elif label == "dryup=F":
            return df["dryup"].notna() & (df["dryup"] == False)  # noqa: E712
        elif label == "updown_good=T":
            return df["updown_good"].notna() & (df["updown_good"] == True)  # noqa: E712
        elif label == "updown_good=F":
            return df["updown_good"].notna() & (df["updown_good"] == False)  # noqa: E712
        elif label == "obv_div=T":
            return df["obv_div"].notna() & (df["obv_div"] == True)  # noqa: E712
        elif label == "obv_div=F":
            return df["obv_div"].notna() & (df["obv_div"] == False)  # noqa: E712
        elif label == "trap_state=T":
            return df["trap_state"] == True  # noqa: E712
        elif label == "trap_state=F":
            return df["trap_state"] == False  # noqa: E712
        elif label == "failed2=T":
            return df["failed2"] == True  # noqa: E712
        elif label == "failed2=F":
            return df["failed2"] == False  # noqa: E712
        elif label == "rs_low=T":
            return df["rs_low"] == True  # noqa: E712
        elif label == "rs_low=F":
            return df["rs_low"] == False  # noqa: E712
        elif label == "h6_cohort=T (in_washout)":
            return df["in_washout_ctx"] & df["h6_cohort"].notna() & (df["h6_cohort"] >= H6_COHORT_THRESH)
        elif label == "h6_cohort=F (in_washout)":
            return df["in_washout_ctx"] & df["h6_cohort"].notna() & (df["h6_cohort"] < H6_COHORT_THRESH)
        return pd.Series(False, index=df.index)

    def clean15_rate(df: pd.DataFrame) -> float:
        if len(df) == 0:
            return np.nan
        return float(df["clean15"].mean())

    for fav, unfav in pairs:
        # Full panel spread
        fav_rate = clean15_rate(fires[get_mask(fires, fav)])
        unfav_rate = clean15_rate(fires[get_mask(fires, unfav)])
        spread_full = fav_rate - unfav_rate if (not np.isnan(fav_rate) and not np.isnan(unfav_rate)) else np.nan

        # Ticker-half A
        fav_a = clean15_rate(fires_a[get_mask(fires_a, fav)])
        unfav_a = clean15_rate(fires_a[get_mask(fires_a, unfav)])
        spread_a = fav_a - unfav_a if (not np.isnan(fav_a) and not np.isnan(unfav_a)) else np.nan

        # Ticker-half B
        fav_b = clean15_rate(fires_b[get_mask(fires_b, fav)])
        unfav_b = clean15_rate(fires_b[get_mask(fires_b, unfav)])
        spread_b = fav_b - unfav_b if (not np.isnan(fav_b) and not np.isnan(unfav_b)) else np.nan

        # Time pre
        fav_pre = clean15_rate(fires_pre[get_mask(fires_pre, fav)])
        unfav_pre = clean15_rate(fires_pre[get_mask(fires_pre, unfav)])
        spread_pre = fav_pre - unfav_pre if (not np.isnan(fav_pre) and not np.isnan(unfav_pre)) else np.nan

        # Time post
        fav_post = clean15_rate(fires_post[get_mask(fires_post, fav)])
        unfav_post = clean15_rate(fires_post[get_mask(fires_post, unfav)])
        spread_post = fav_post - unfav_post if (not np.isnan(fav_post) and not np.isnan(unfav_post)) else np.nan

        # Sign agreement booleans
        ticker_agree = bool(
            not np.isnan(spread_a) and not np.isnan(spread_b)
            and np.sign(spread_a) == np.sign(spread_b)
        )
        time_agree = bool(
            not np.isnan(spread_pre) and not np.isnan(spread_post)
            and np.sign(spread_pre) == np.sign(spread_post)
        )

        split_rows.append({
            "pair": f"{fav} vs {unfav}",
            "spread_full": round(spread_full * 100, 2) if not np.isnan(spread_full) else float("nan"),
            "spread_ticker_A": round(spread_a * 100, 2) if not np.isnan(spread_a) else float("nan"),
            "spread_ticker_B": round(spread_b * 100, 2) if not np.isnan(spread_b) else float("nan"),
            "spread_time_pre2020": round(spread_pre * 100, 2) if not np.isnan(spread_pre) else float("nan"),
            "spread_time_post2020": round(spread_post * 100, 2) if not np.isnan(spread_post) else float("nan"),
            "ticker_halves_agree": ticker_agree,
            "time_halves_agree": time_agree,
        })

    return split_rows


# ══════════════════════════════════════════════════════════════════════════════
# Main pipeline
# ══════════════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description="Wave-1 durable-bottom entry timing study")
    ap.add_argument("--tickers", default="", help="Comma-separated ticker subset (default: all)")
    ap.add_argument("--out", default="research/entry_timing/_out",
                    help="Output directory for parquets + JSON")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── Resolve file list ──────────────────────────────────────────────────
    all_files = sorted(DATA.glob("*.parquet"))
    if args.tickers:
        wanted = {t.strip() for t in args.tickers.split(",") if t.strip()}
        all_files = [f for f in all_files if f.stem in wanted]

    print(f"Panel: {len(all_files)} files found")

    # Pre-filter to >=1500 bars
    panel_files = []
    for fp in all_files:
        try:
            df = pd.read_parquet(fp)
            daily = df["close"].dropna()
            if len(daily) >= MIN_BARS:
                panel_files.append(fp)
        except Exception:
            pass
    print(f"Panel after >=1500 bar filter: {len(panel_files)} names")

    # ── Load SPY for rs_low feature ────────────────────────────────────────
    spy_path = DATA / "SPY.parquet"
    if not spy_path.exists():
        spy_path = YAHOO / "SPY.parquet"
    spy_close = None
    if spy_path.exists():
        spy_df = pd.read_parquet(spy_path)
        spy_close = spy_df["close"].dropna()
        print(f"SPY loaded from {spy_path}: {len(spy_close)} bars")
    else:
        print("Warning: SPY not found; rs_low feature will be None for all fires")

    # ── Load sector map ────────────────────────────────────────────────────
    const_path = BREADTH / "constituents.parquet"
    sector_map: dict[str, str] = {}
    if const_path.exists():
        const_df = pd.read_parquet(const_path)
        for sym, row in const_df.iterrows():
            sector_map[sym] = row["sector"]
    print(f"Sector map: {len(sector_map)} tickers")

    # ── Pre-compute sector D-matrix for H6 ────────────────────────────────
    print("Building sector weekly-D matrix for H6 cohort feature...")
    sector_d_matrix = build_sector_d_matrix([str(f) for f in panel_files], sector_map)
    print(f"Sector D-matrix: {len(sector_d_matrix)} tickers")

    # ── Process each name ─────────────────────────────────────────────────
    all_fires: dict[str, list[dict]] = {v: [] for v in VARIANTS}
    all_events: list[dict] = []
    ticker_list: list[str] = []
    total_t0 = time.time()

    for fp in panel_files:
        ticker = fp.stem
        t0 = time.time()

        # Build SPY ratio for this ticker
        if spy_close is not None:
            try:
                df_t = pd.read_parquet(fp)
                daily_t = df_t["close"].dropna()
                spy_aligned = spy_close.reindex(daily_t.index, method="ffill")
                spy_ratio = (daily_t / spy_aligned).replace([np.inf, -np.inf], np.nan)
            except Exception:
                spy_ratio = None
        else:
            spy_ratio = None

        try:
            result = process_name(
                ticker, str(fp), spy_ratio, sector_map, sector_d_matrix, VARIANTS
            )
        except Exception as e:
            print(f"  ERROR {ticker}: {e}")
            continue

        elapsed = time.time() - t0

        for vname in VARIANTS:
            rows = result.get(vname, [])
            all_fires[vname].extend(rows)

        ev_rows = result.get("events", [])
        all_events.extend(ev_rows)
        ticker_list.append(ticker)

        n_fires_base = len(result.get("base3d", []))
        n_ev = len(ev_rows)
        print(f"  {ticker:6s}  bars={len(pd.read_parquet(fp)['close'].dropna()):5d}"
              f"  events={n_ev}  fires_base3d={n_fires_base}  {elapsed:.1f}s")

    total_elapsed = time.time() - total_t0
    n_names = len(ticker_list)
    print(f"\nTotal: {n_names} names, {total_elapsed:.1f}s ({total_elapsed/max(n_names,1):.1f}s/name)")
    print(f"Projected 223-name runtime: {total_elapsed/max(n_names,1)*223/60:.1f} min")

    # ── Build DataFrames ───────────────────────────────────────────────────
    events_df = pd.DataFrame(all_events)
    if "t0" in events_df.columns:
        events_df["t0"] = pd.to_datetime(events_df["t0"])

    fires_dfs: dict[str, pd.DataFrame] = {}
    for vname in VARIANTS:
        rows = all_fires[vname]
        if rows:
            df_v = pd.DataFrame(rows)
            df_v["sig_date"] = pd.to_datetime(df_v["sig_date"])
            df_v["fill_date"] = pd.to_datetime(df_v["fill_date"])
            fires_dfs[vname] = df_v
        else:
            fires_dfs[vname] = pd.DataFrame()

    # ── Save parquets ──────────────────────────────────────────────────────
    events_df.to_parquet(out_dir / "events.parquet", index=False)
    for vname in VARIANTS:
        fires_dfs[vname].to_parquet(out_dir / f"fires_{vname}.parquet", index=False)
    print(f"\nSaved parquets to {out_dir}")

    # ── Build wave1_tables.json ────────────────────────────────────────────
    tables = {}
    for vname in VARIANTS:
        fires = fires_dfs[vname]
        if len(fires) == 0:
            tables[vname] = {"headline": {}, "strata": [], "split_checks": []}
            continue

        headline = compute_headline(fires, events_df, vname)
        strata = compute_strata(fires, events_df, vname)
        split_checks = compute_split_checks(fires, [s["label"] for s in strata], ticker_list)

        tables[vname] = {
            "headline": headline,
            "strata": strata,
            "split_checks": split_checks,
        }

    tables_path = out_dir / "wave1_tables.json"
    with open(tables_path, "w") as f:
        json.dump(tables, f, indent=2, default=str)
    print(f"Saved wave1_tables.json to {tables_path}")

    # ── Print compact summary ──────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("WAVE-1 SUMMARY")
    print("=" * 70)
    n_events = len(events_df)
    n_durable = int((events_df["label"] == "durable").sum()) if n_events > 0 else 0
    n_trap = int((events_df["label"] == "trap").sum()) if n_events > 0 else 0
    print(f"Events: total={n_events}  durable={n_durable}  trap={n_trap}")

    for vname in VARIANTS:
        h = tables[vname]["headline"]
        print(f"\n--- {vname} ---")
        print(f"  fires={h.get('n_fires',0)}")
        print(f"  recall_B15={h.get('recall_B15','?')}%  recall_B30={h.get('recall_B30','?')}%")
        print(f"  precision={h.get('precision','?')}%  trap_fire_rate={h.get('trap_fire_rate','?')}%")
        print(f"  med_premium={h.get('med_premium','?')}%  med_lead={h.get('med_lead','?')}d")
        print(f"  stop5={h.get('stop5','?')}%  low_stop5={h.get('low_stop5','?')}%")
        print(f"  clean15={h.get('clean15','?')}%  dead_money={h.get('dead_money','?')}%  stalled={h.get('stalled','?')}%")

        # Top strata by clean15 spread vs ALL
        strata = tables[vname]["strata"]
        all_row = next((s for s in strata if s["label"] == "ALL"), None)
        if all_row and not np.isnan(all_row.get("clean15", float("nan"))):
            base_c15 = all_row["clean15"]
            ranked = sorted(
                [s for s in strata if s["label"] not in ("ALL", "oracle (forward-peeking)")
                 and s.get("n", 0) >= 30],
                key=lambda s: (s.get("clean15", float("nan")) or 0) - base_c15,
                reverse=True
            )[:5]
            print("  Top strata by clean15 lift vs ALL (n>=30):")
            for s in ranked:
                lift = (s.get("clean15", float("nan")) or 0) - base_c15
                print(f"    {s['label']:45s} n={s['n']:4d}  c15={s.get('clean15','?')}%  "
                      f"lift={lift:+.2f}pp  stop5={s.get('stop5','?')}%")

    print("=" * 70)

    return tables, events_df, fires_dfs


# ── §G: Smoke test helper ─────────────────────────────────────────────────────

def run_smoke(tables: dict, events_df: pd.DataFrame, fires_dfs: dict):
    """Assert smoke-test conditions and report. Raises AssertionError if any fails."""
    print("\n" + "=" * 70)
    print("SMOKE TEST ASSERTIONS")
    print("=" * 70)

    errors = []

    # 1. >0 events with both durable and trap labels
    n_durable = int((events_df["label"] == "durable").sum()) if len(events_df) > 0 else 0
    n_trap = int((events_df["label"] == "trap").sum()) if len(events_df) > 0 else 0
    print(f"[1] Events: durable={n_durable}, trap={n_trap}")
    if n_durable == 0:
        errors.append("No durable events found!")
    if n_trap == 0:
        errors.append("No trap events found!")

    # 2. >0 fires per variant
    for vname in VARIANTS:
        nf = len(fires_dfs[vname])
        print(f"[2] Fires {vname}: {nf}")
        if nf == 0:
            errors.append(f"No fires for variant {vname}!")

    # 3. Features not degenerate (w2_deep, bull_div, in_washout_ctx, trap_state have BOTH T and F)
    for vname in VARIANTS:
        fires = fires_dfs[vname]
        if len(fires) == 0:
            continue
        for feat in ["w2_deep", "bull_div", "in_washout_ctx", "trap_state"]:
            if feat not in fires.columns:
                errors.append(f"{vname}/{feat}: column missing!")
                continue
            vals = fires[feat].dropna().unique()
            has_t = any(bool(v) == True for v in vals)  # noqa: E712
            has_f = any(bool(v) == False for v in vals)  # noqa: E712
            print(f"[3] {vname}/{feat}: T={has_t}, F={has_f}")
            if not has_t or not has_f:
                errors.append(f"{vname}/{feat} is degenerate (only one value)!")

    # 4. Volume features non-null for these names (smoke names have volume)
    for vname in VARIANTS:
        fires = fires_dfs[vname]
        if len(fires) == 0:
            continue
        n_capit = fires["capit_spike"].notna().sum()
        print(f"[4] {vname}/capit_spike non-null: {n_capit}/{len(fires)}")
        if n_capit == 0:
            errors.append(f"{vname}: volume features all null (expected non-null for smoke tickers)!")

    # 5. oracle stop5 <= all-fires stop5 on base3d (directional sanity)
    fires_b = fires_dfs.get("base3d", pd.DataFrame())
    if len(fires_b) > 0 and "oracle_take" in fires_b.columns:
        oracle_fires = fires_b[fires_b["oracle_take"]]
        all_stop5 = fires_b["stop5"].mean()
        oracle_stop5 = oracle_fires["stop5"].mean() if len(oracle_fires) > 0 else float("nan")
        print(f"[5] base3d oracle_stop5={oracle_stop5:.3f} vs all_stop5={all_stop5:.3f}")
        if not np.isnan(oracle_stop5) and oracle_stop5 > all_stop5:
            errors.append(
                f"Oracle stop5 ({oracle_stop5:.3f}) > all-fires stop5 ({all_stop5:.3f}) — directional fail!"
            )
    else:
        print("[5] Skipping oracle check (no oracle_take column or no base3d fires)")

    # Print result
    if errors:
        print("\nSMOKE TEST FAILURES:")
        for e in errors:
            print(f"  FAIL: {e}")
        raise AssertionError(f"{len(errors)} smoke assertion(s) failed")
    else:
        print("\nAll smoke assertions PASSED.")


if __name__ == "__main__":
    tables, events_df, fires_dfs = main()
    # Run smoke assertions at the end of every run
    run_smoke(tables, events_df, fires_dfs)
