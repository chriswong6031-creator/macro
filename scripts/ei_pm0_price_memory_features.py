"""
EI-PM0 Price-Memory Feature Builder
====================================
Outcome-blind feature builder for the PM0 Price-Memory Bundle study.
Pre-registration: research/entry_intel/PM0_PRICE_MEMORY_BUNDLE_PREREG.md (APPROVED 2026-07-06 r3)
Execution spec:  research/entry_intel/pm0_runs/EI_PM0_price_memory/EXECUTION_SPEC.md

OUTCOME BLINDNESS GUARANTEE: This script reads ONLY {ticker, signal_date, episode_id,
survivor_bias, verdict_type, verdict_grade, horizon_censored} from the replay.
Never any state_*, fwd_*, mdd_*, mfe_* column. Grepping 'state_' or 'fwd_' in this file
must return zero matches outside this header comment block.

Usage:
  python scripts/ei_pm0_price_memory_features.py --build
  python scripts/ei_pm0_price_memory_features.py --qa
  python scripts/ei_pm0_price_memory_features.py --smoke 5 --out /tmp/pm0_smoke.parquet
"""

import os
import sys
import json
import hashlib
import argparse
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ── sys.path: ensure scripts/ and engine/ importable from repo root or worktree ──
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO = _SCRIPT_DIR.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.replay_standout_pipeline import split_adjust, SPLIT_LOG_THRESHOLD

# ── Paths ──────────────────────────────────────────────────────────────────────
_DEFAULT_DATA_ROOT = "/Users/chriswong/Documents/Cluade/Macro Dashboard/data"
DATA_ROOT = Path(os.environ.get("MAIN_DATA", _DEFAULT_DATA_ROOT))
REPLAY_PATH = DATA_ROOT / "replay" / "replay_boarded.parquet"
MSD_DIR = DATA_ROOT / "massive_stock_day"
EDGAR_PATH = DATA_ROOT / "edgar" / "statements_quarterly.parquet"
OUT_DIR = Path(__file__).parents[1] / "research" / "entry_intel" / "pm0_runs" / "EI_PM0_price_memory"

# ── Constants (from spec §2.2) ──────────────────────────────────────────────────
W_BARS = 250          # trailing window length
W_FLOOR = 200         # minimum bars for pm1–pm4 (pm3 also requires this)
PM3_GAP_FENCE = 0.25  # gap size > 25% => artifact-suspect, ignored
PM3_REACH_BAND = 0.10 # overhead gap lower edge must be in (close_s, close_s * 1.10]
PM2_BAND = 0.03       # shelf band: |tp/close_s - 1| <= 0.03
SO_STALE_DAYS = 270   # max staleness for shares outstanding
SO_SANITY_MAX = 1e11  # shares sanity upper bound
POC_WIN = 126         # rolling VWAP window (poc_dist_126)
POC_MIN_PERIODS = max(20, POC_WIN // 4)  # = 31

# ── Replay columns to load (OUTCOME-BLIND) ─────────────────────────────────────
REPLAY_COLS = [
    "ticker", "signal_date", "episode_id",
    "survivor_bias", "verdict_type", "verdict_grade", "horizon_censored",
]

# ─────────────────────────────────────────────────────────────────────────────
# Feature computation helpers
# ─────────────────────────────────────────────────────────────────────────────

def _compute_split_factor(raw_close: np.ndarray, adj_close: np.ndarray) -> np.ndarray:
    """Per-bar factor_t = raw_close_t / adjusted_close_t (exact by construction)."""
    # split_adjust() drops NaNs; a shorter return series would silently
    # misalign the element-wise division below.
    assert len(raw_close) == len(adj_close), (
        f"split_adjust length mismatch: raw={len(raw_close)} adj={len(adj_close)} "
        "(NaN closes in the store?)"
    )
    with np.errstate(divide="ignore", invalid="ignore"):
        f = np.where(adj_close != 0, raw_close / adj_close, 1.0)
    return f


def _has_split_suspect_unadjusted(raw_close: np.ndarray, factor: np.ndarray) -> bool:
    """Return True if any bar inside the window has |log(raw_r)| > SPLIT_LOG_THRESHOLD
    AND factor is unchanged across that bar (tolerance-free comparison).
    Such a bar indicates an unadjusted split-suspect jump that split_adjust did not snap.
    """
    if len(raw_close) < 2:
        return False
    log_r = np.abs(np.log(raw_close[1:] / np.where(raw_close[:-1] != 0, raw_close[:-1], np.nan)))
    for i in range(len(log_r)):
        if np.isnan(log_r[i]):
            continue
        if log_r[i] > SPLIT_LOG_THRESHOLD:
            # factor at bar i and bar i+1 must be equal for it to be "not snapped"
            if factor[i] == factor[i + 1]:
                return True
    return False


def compute_pm1(adj_c, adj_tp, adj_vol, n_bars) -> tuple:
    """AVWAP distance. Returns (pm1, anchor_age_bars, reason)."""
    if n_bars < W_FLOOR:
        return np.nan, np.nan, "short_window"
    # Anchor = index of min adjusted close, most recent bar if tied (last argmin)
    # np.argmin returns first; we need last argmin
    min_val = np.min(adj_c)
    # all positions of minimum
    min_positions = np.where(adj_c == min_val)[0]
    a = int(min_positions[-1])  # most recent (last index with minimum)
    s = n_bars - 1  # signal bar index
    # AVWAP from anchor to signal bar (inclusive)
    seg_tp = adj_tp[a:]
    seg_vol = adj_vol[a:]
    denom = seg_vol.sum()
    if denom == 0 or np.isnan(denom):
        return np.nan, int(s - a), "zero_vol"
    avwap = (seg_tp * seg_vol).sum() / denom
    if avwap == 0 or np.isnan(avwap):
        return np.nan, int(s - a), "zero_avwap"
    pm1 = float(adj_c[s] / avwap - 1.0)
    anchor_age = int(s - a)
    return pm1, anchor_age, "ok"


def compute_pm2(adj_tp, adj_dv, close_s, n_bars) -> tuple:
    """Volume-at-price shelf density. Returns (pm2, reason)."""
    if n_bars < W_FLOOR:
        return np.nan, "short_window"
    total_dv = adj_dv.sum()
    if total_dv == 0 or np.isnan(total_dv):
        return np.nan, "zero_dv"
    with np.errstate(invalid="ignore"):
        shelf_mask = np.abs(adj_tp / close_s - 1.0) <= PM2_BAND
    pm2 = float(adj_dv[shelf_mask].sum() / total_dv)
    return pm2, "ok"


def compute_pm3(adj_o, adj_h, adj_l, adj_c, close_s, n_bars) -> tuple:
    """Unfilled overhead breakaway gap flag. Returns (pm3, n_gaps_ignored, reason)."""
    if n_bars < W_FLOOR:
        return np.nan, 0, "short_window"
    n_gaps_ignored = 0
    # Scan t=1..n_bars-1; t-1 and t must both be inside window (index 0..n_bars-1)
    for t in range(1, n_bars):
        # Down-gap: high_t < low_{t-1}
        high_t = adj_h[t]
        low_t_prev = adj_l[t - 1]
        if high_t >= low_t_prev:
            continue
        # Gap found: zone = [high_t, low_{t-1}]
        gap_size = low_t_prev / high_t - 1.0
        if gap_size > PM3_GAP_FENCE:
            n_gaps_ignored += 1
            continue
        # Unfilled at s iff no u in (t, n_bars-1] has high_u >= low_{t-1}
        future_h = adj_h[t + 1:n_bars]
        if len(future_h) > 0 and np.any(future_h >= low_t_prev):
            continue  # filled
        # Unfilled: check if lower edge (high_t) is within reach
        if close_s < high_t <= close_s * (1.0 + PM3_REACH_BAND):
            return 1, n_gaps_ignored, "ok"
    return 0, n_gaps_ignored, "ok"


def compute_pm4(adj_tp, adj_dv, close_s, n_bars) -> tuple:
    """Overhead supply fraction. Returns (pm4, reason)."""
    if n_bars < W_FLOOR:
        return np.nan, "short_window"
    total_dv = adj_dv.sum()
    if total_dv == 0 or np.isnan(total_dv):
        return np.nan, "zero_dv"
    overhead_dv = adj_dv[adj_tp > close_s].sum()
    pm4 = float(overhead_dv / total_dv)
    return pm4, "ok"


def compute_poc_dist_126(adj_c_full, adj_vol_full, n_bars) -> tuple:
    """Close-weighted rolling VWAP (126 bar) distance. Returns (poc_dist_126, reason).
    Uses the last min(126, available) bars before and including signal bar.
    min_periods = 31 (= max(20, 126//4)).
    NOT subject to the 200-bar floor (spec §2.2 EX-3).
    """
    n = n_bars
    win = min(POC_WIN, n)
    if win < POC_MIN_PERIODS:
        return np.nan, "poc_short"
    seg_c = adj_c_full[n - win:n]
    seg_v = adj_vol_full[n - win:n]
    sum_v = seg_v.sum()
    if sum_v == 0 or np.isnan(sum_v):
        return np.nan, "poc_zero_vol"
    poc = (seg_c * seg_v).sum() / sum_v
    if poc == 0 or np.isnan(poc):
        return np.nan, "poc_zero"
    poc_dist = float(adj_c_full[n - 1] / poc - 1.0)
    return poc_dist, "ok"


def compute_pm5(
    raw_vol_upto: np.ndarray,
    raw_c_full: np.ndarray,
    factor_full: np.ndarray,
    idx_signal: int,
    signal_date_str: str,
    ticker: str,
    stmts_ticker: pd.DataFrame,
    store_dates: pd.DatetimeIndex,
) -> tuple:
    """Float turnover proxy (FLOAT-PROXY, data_blocked — context only).

    raw_vol_upto: RAW volume array for bars [0..idx_signal] (full-history
    prefix). Volume is converted to signal-date share units by anchoring the
    split factor at the signal bar (factor_t / factor_s = split multiplier over
    (t, s]) — a factor from a post-signal split cancels in the ratio, keeping
    the value identical between full-series and truncated-at-signal inputs.
    Returns (pm5, so_staleness_days, so_shares_raw, reason).
    """
    n = idx_signal + 1  # bars up to and including signal
    if n < 63:
        return np.nan, np.nan, np.nan, "pm5_short_window"

    signal_ts = pd.Timestamp(signal_date_str)

    # Filter statements: non-null shares, filed <= signal_date
    if stmts_ticker is None or len(stmts_ticker) == 0:
        return np.nan, np.nan, np.nan, "so_missing"

    valid = stmts_ticker[
        stmts_ticker["shares"].notna() &
        (stmts_ticker["filed"] <= signal_date_str)
    ]
    if len(valid) == 0:
        return np.nan, np.nan, np.nan, "so_missing"

    # Pick latest filed row
    row = valid.sort_values("filed").iloc[-1]
    filed_str = row["filed"]
    shares_raw = float(row["shares"])
    period_end_str = row.get("period_end", None)

    # Staleness check
    filed_ts = pd.Timestamp(filed_str)
    staleness_days = (signal_ts - filed_ts).days
    if staleness_days > SO_STALE_DAYS:
        return np.nan, staleness_days, shares_raw, "so_stale"

    # Sanity fence
    if not (0 < shares_raw < SO_SANITY_MAX):
        return np.nan, staleness_days, shares_raw, "so_corrupt"

    # period_end check
    if period_end_str is None or pd.isna(period_end_str):
        return np.nan, staleness_days, shares_raw, "so_missing"

    period_end_ts = pd.Timestamp(period_end_str)

    # First store bar date
    store_first = store_dates[0]
    if period_end_ts < store_first:
        return np.nan, staleness_days, shares_raw, "so_prehistory"

    # Split multiplier over (period_end, signal_date]
    # Need raw close from period_end to signal_date to detect splits
    pe_idx = store_dates.searchsorted(period_end_ts, side="right")
    sig_idx = idx_signal  # inclusive
    f_sig = factor_full[sig_idx]
    if f_sig <= 0:
        return np.nan, staleness_days, shares_raw, "so_corrupt"

    # If pe_idx > sig_idx, no bars in range
    if pe_idx > sig_idx:
        # No bars after period_end before signal — no splits to detect
        multiplier = 1.0
    else:
        # Scan from the last bar at-or-before period_end through the signal bar
        # so a snap INTO the first post-period_end bar is inspected/counted.
        pe0 = max(0, pe_idx - 1)
        seg_raw = raw_c_full[pe0:sig_idx + 1]
        seg_factor = factor_full[pe0:sig_idx + 1]
        if _has_split_suspect_unadjusted(seg_raw, seg_factor):
            return np.nan, staleness_days, shares_raw, "so_split_suspect"
        # multiplier = Π snaps in (period_end, s] = factor[pe0]/factor[sig]
        # (factor_t = raw/adj = Π snaps after t; any post-signal split factor
        # is common to both and cancels). Shares scale UP by the multiplier.
        multiplier = factor_full[pe0] / f_sig

    so_pit = shares_raw * multiplier
    if so_pit <= 0:
        return np.nan, staleness_days, shares_raw, "so_corrupt"

    # Numerator: last 63 bars' RAW volume converted to signal-date share units
    # (factor_t / factor_s = split multiplier over (t, s]; post-signal splits
    # cancel, so full-series and truncated inputs give identical values).
    seg_vol = raw_vol_upto[idx_signal - 62: idx_signal + 1]
    seg_f = factor_full[idx_signal - 62: idx_signal + 1]
    num_vol = float(np.sum(seg_vol * (seg_f / f_sig)))
    pm5 = float(num_vol / so_pit)
    return pm5, staleness_days, shares_raw, "ok"


# ─────────────────────────────────────────────────────────────────────────────
# Per-ticker feature computation
# ─────────────────────────────────────────────────────────────────────────────

def compute_features_for_ticker(
    ticker: str,
    rows: pd.DataFrame,   # rows for this ticker (signal_date, episode_id, verdict_type, verdict_grade)
    stmts_ticker: pd.DataFrame,
) -> list:
    """Compute all features for all rows of a ticker. Returns list of dicts."""
    store_path = MSD_DIR / f"{ticker}.parquet"
    results = []

    if not store_path.exists():
        for _, r in rows.iterrows():
            results.append(_nan_row(ticker, r, "no_store"))
        return results

    try:
        store_df = pd.read_parquet(store_path)
    except Exception:
        for _, r in rows.iterrows():
            results.append(_nan_row(ticker, r, "no_store"))
        return results

    # Ensure DatetimeIndex
    if not isinstance(store_df.index, pd.DatetimeIndex):
        store_df.index = pd.to_datetime(store_df.index)
    store_df = store_df.sort_index()

    store_dates = store_df.index
    raw_close_full = store_df["close"].values.astype(float)
    raw_open_full = store_df["open"].values.astype(float)
    raw_high_full = store_df["high"].values.astype(float)
    raw_low_full = store_df["low"].values.astype(float)
    raw_vol_full = store_df["volume"].values.astype(float)

    # split_adjust on full close series
    adj_close_series = split_adjust(pd.Series(raw_close_full, index=store_dates))
    adj_close_full = adj_close_series.values.astype(float)
    factor_full = _compute_split_factor(raw_close_full, adj_close_full)

    for _, r in rows.iterrows():
        signal_date_str = r["signal_date"]
        episode_id = r["episode_id"]
        verdict_type = r["verdict_type"]
        verdict_grade = bool(r["verdict_grade"])
        survivor_bias = bool(r["survivor_bias"])

        # Locate signal date in store
        signal_ts = pd.Timestamp(signal_date_str)
        pos_arr = store_dates.searchsorted(signal_ts)
        if pos_arr >= len(store_dates) or store_dates[pos_arr] != signal_ts:
            results.append(_nan_row(ticker, r, "no_signal_bar"))
            continue

        idx_signal = int(pos_arr)

        # Window: last min(250, available) bars ending at idx_signal inclusive
        n_avail = idx_signal + 1
        n_bars = min(W_BARS, n_avail)
        w_start = idx_signal - n_bars + 1

        # Slices (W window)
        raw_c = raw_close_full[w_start:idx_signal + 1]
        adj_c = adj_close_full[w_start:idx_signal + 1]
        factor_w = factor_full[w_start:idx_signal + 1]
        raw_o = raw_open_full[w_start:idx_signal + 1]
        raw_h = raw_high_full[w_start:idx_signal + 1]
        raw_l = raw_low_full[w_start:idx_signal + 1]
        raw_vol = raw_vol_full[w_start:idx_signal + 1]

        # Adjusted ohlv
        adj_o = raw_o / factor_w
        adj_h = raw_h / factor_w
        adj_l = raw_l / factor_w
        adj_vol = raw_vol * factor_w
        adj_tp = (adj_h + adj_l + adj_c) / 3.0
        adj_dv = adj_tp * adj_vol

        close_s = float(adj_c[-1])

        # Split fence: check for unadjusted split-suspect jumps in W
        split_suspect = _has_split_suspect_unadjusted(raw_c, factor_w)

        # n_bars_avail
        n_bars_avail = n_bars

        if split_suspect:
            sr = "split_suspect"
            pm1 = pm2 = pm4 = poc_dist_126 = np.nan
            anchor_age_bars = np.nan
            pm1_reason = pm2_reason = pm4_reason = poc_reason = sr
            pm3 = np.nan
            pm3_reason = sr
            n_gaps_ignored = 0
            pm5 = so_staleness_days = so_shares_raw = np.nan
            pm5_reason = sr
        else:
            # PM1
            pm1, anchor_age_bars, pm1_reason = compute_pm1(adj_c, adj_tp, adj_vol, n_bars)
            # PM2
            pm2, pm2_reason = compute_pm2(adj_tp, adj_dv, close_s, n_bars)
            # PM3
            pm3, n_gaps_ignored, pm3_reason = compute_pm3(adj_o, adj_h, adj_l, adj_c, close_s, n_bars)
            # PM4
            pm4, pm4_reason = compute_pm4(adj_tp, adj_dv, close_s, n_bars)
            # poc_dist_126 (uses full adj arrays up to idx_signal)
            poc_dist_126, poc_reason = compute_poc_dist_126(
                adj_close_full[:idx_signal + 1],
                raw_vol_full[:idx_signal + 1] * factor_full[:idx_signal + 1],
                n_avail,
            )
            # PM5
            pm5, so_staleness_days, so_shares_raw, pm5_reason = compute_pm5(
                raw_vol_full[:idx_signal + 1], raw_close_full[:idx_signal + 1],
                factor_full[:idx_signal + 1],
                idx_signal, signal_date_str, ticker,
                stmts_ticker, store_dates,
            )

        results.append({
            "ticker": ticker,
            "signal_date": signal_date_str,
            "episode_id": episode_id,
            "verdict_type": verdict_type,
            "verdict_grade": verdict_grade,
            "survivor_bias": survivor_bias,
            "pm1": pm1,
            "pm2": pm2,
            "pm3": float(pm3) if not np.isnan(pm3 if pm3 is not None else float("nan")) else np.nan,
            "pm4": pm4,
            "pm5": pm5,
            "poc_dist_126": poc_dist_126,
            "pm1_reason": pm1_reason,
            "pm2_reason": pm2_reason,
            "pm3_reason": pm3_reason if pm3_reason else "ok",
            "pm4_reason": pm4_reason,
            "pm5_reason": pm5_reason,
            "poc_reason": poc_reason,
            "n_bars_avail": int(n_bars_avail),
            "anchor_age_bars": float(anchor_age_bars) if not pd.isna(anchor_age_bars) else np.nan,
            "n_gaps_ignored": int(n_gaps_ignored) if n_gaps_ignored is not None else 0,
            "so_staleness_days": float(so_staleness_days) if not pd.isna(so_staleness_days) else np.nan,
            "so_shares_raw": float(so_shares_raw) if not pd.isna(so_shares_raw) else np.nan,
        })

    return results


def _nan_row(ticker: str, r, reason: str) -> dict:
    return {
        "ticker": ticker,
        "signal_date": r["signal_date"],
        "episode_id": r["episode_id"],
        "verdict_type": r["verdict_type"],
        "verdict_grade": bool(r["verdict_grade"]),
        "survivor_bias": bool(r["survivor_bias"]),
        "pm1": np.nan, "pm2": np.nan, "pm3": np.nan,
        "pm4": np.nan, "pm5": np.nan, "poc_dist_126": np.nan,
        "pm1_reason": reason, "pm2_reason": reason,
        "pm3_reason": reason, "pm4_reason": reason,
        "pm5_reason": reason, "poc_reason": reason,
        "n_bars_avail": 0,
        "anchor_age_bars": np.nan,
        "n_gaps_ignored": 0,
        "so_staleness_days": np.nan,
        "so_shares_raw": np.nan,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main build function
# ─────────────────────────────────────────────────────────────────────────────

def _load_population() -> pd.DataFrame:
    """Load the population (fires + verdict-grade near-misses) from replay."""
    print(f"Loading replay from: {REPLAY_PATH}")
    df = pd.read_parquet(REPLAY_PATH, columns=REPLAY_COLS)
    print(f"  Full shape: {df.shape}")
    # Population: verdict_type=='fire' OR (verdict_type=='near_miss' AND verdict_grade==True)
    pop = df[
        (df["verdict_type"] == "fire") |
        ((df["verdict_type"] == "near_miss") & (df["verdict_grade"] == True))
    ].copy()
    print(f"  Population rows: {len(pop):,} ({pop.verdict_type.value_counts().to_dict()})")
    # Duplicate check: exact duplicate (ticker, signal_date, episode_id) must not exist
    dup_mask = pop.duplicated(subset=["ticker", "signal_date", "episode_id"], keep=False)
    if dup_mask.any():
        n_dups = dup_mask.sum()
        print(f"HALT: {n_dups} exact duplicate (ticker, signal_date, episode_id) rows found.")
        sys.exit(1)
    return pop


def _load_statements() -> dict:
    """Load statements_quarterly, return dict ticker -> DataFrame with needed columns."""
    print(f"Loading statements from: {EDGAR_PATH}")
    stmts = pd.read_parquet(EDGAR_PATH, columns=["ticker", "shares", "filed", "period_end"])
    # Keep only rows with non-null filed
    stmts = stmts[stmts["filed"].notna()].copy()
    # Group by ticker
    stmts_by_ticker = {}
    for ticker, grp in stmts.groupby("ticker"):
        stmts_by_ticker[ticker] = grp.reset_index(drop=True)
    print(f"  Statements tickers: {len(stmts_by_ticker):,}")
    return stmts_by_ticker


def build_features(
    pop: pd.DataFrame,
    stmts_by_ticker: dict,
    progress_every: int = 100,
) -> pd.DataFrame:
    """Build feature artifact for all tickers in population."""
    tickers = sorted(pop["ticker"].unique())
    print(f"Building features for {len(tickers):,} tickers...")
    all_results = []
    for i, ticker in enumerate(tickers):
        if i > 0 and i % progress_every == 0:
            print(f"  [{i:,}/{len(tickers):,}] tickers processed...")
        ticker_rows = pop[pop["ticker"] == ticker].copy()
        stmts_t = stmts_by_ticker.get(ticker, pd.DataFrame())
        results = compute_features_for_ticker(ticker, ticker_rows, stmts_t)
        all_results.extend(results)
    print(f"  Done. {len(all_results):,} rows computed.")
    feat_df = pd.DataFrame(all_results)
    return feat_df


def compute_medians_vg_fires(feat_df: pd.DataFrame) -> dict:
    """Compute medians over verdict-grade fire rows (outcome-blind: feature values only)."""
    vg_fires_mask = (feat_df["verdict_type"] == "fire") & (feat_df["verdict_grade"] == True)
    vg = feat_df[vg_fires_mask]
    medians = {}
    for col in ["pm2", "pm4", "pm5"]:
        defined = vg[col].dropna()
        medians[f"{col}_median"] = float(defined.median()) if len(defined) > 0 else None
        medians[f"{col}_n_defined"] = int(defined.count())
    return medians


# ─────────────────────────────────────────────────────────────────────────────
# §4.4 QA Gates
# ─────────────────────────────────────────────────────────────────────────────

def qa_pit_spot_audit(feat_df: pd.DataFrame, stmts_by_ticker: dict) -> dict:
    """Gate 1: PIT spot-audit. 60 rows sampled with rng(606), independently reloaded.
    Returns dict with pass/fail and any mismatches."""
    rng = np.random.default_rng(606)
    idx = rng.choice(len(feat_df), size=min(60, len(feat_df)), replace=False)
    sample = feat_df.iloc[idx].copy()

    mismatches = []
    float_cols = ["pm1", "pm2", "pm3", "pm4", "pm5", "poc_dist_126",
                  "anchor_age_bars", "so_staleness_days", "so_shares_raw"]
    str_cols = ["pm1_reason", "pm2_reason", "pm3_reason",
                "pm4_reason", "pm5_reason", "poc_reason"]

    for _, row in sample.iterrows():
        ticker = row["ticker"]
        signal_date_str = row["signal_date"]
        episode_id = row["episode_id"]

        # Independent reload: hard-truncate store at signal_date
        store_path = MSD_DIR / f"{ticker}.parquet"
        if not store_path.exists():
            # Original should also be no_store
            expected_reason = row["pm1_reason"]
            if expected_reason != "no_store":
                mismatches.append(f"{ticker} {signal_date_str}: expected no_store reason, got {expected_reason}")
            continue

        try:
            store_df = pd.read_parquet(store_path)
        except Exception:
            if row["pm1_reason"] != "no_store":
                mismatches.append(f"{ticker} {signal_date_str}: store load failed but reason != no_store")
            continue

        if not isinstance(store_df.index, pd.DatetimeIndex):
            store_df.index = pd.to_datetime(store_df.index)
        store_df = store_df.sort_index()

        # Hard truncate at signal_date
        signal_ts = pd.Timestamp(signal_date_str)
        store_df = store_df[store_df.index <= signal_ts]

        if len(store_df) == 0:
            if row["pm1_reason"] != "no_signal_bar":
                mismatches.append(f"{ticker} {signal_date_str}: empty after truncate but reason={row['pm1_reason']}")
            continue

        # Build a synthetic row for recomputation
        fake_row = pd.Series({
            "signal_date": signal_date_str,
            "episode_id": episode_id,
            "verdict_type": row["verdict_type"],
            "verdict_grade": row["verdict_grade"],
            "survivor_bias": row["survivor_bias"],
        })
        fake_df = pd.DataFrame([fake_row])

        # Write temporary store-like object via a monkeypatch approach:
        # recompute by calling compute_features_for_ticker on truncated data
        store_path_orig = MSD_DIR / f"{ticker}.parquet"
        # We cannot patch the file, so we recompute manually
        store_dates = store_df.index
        raw_close_full = store_df["close"].values.astype(float)
        raw_open_full = store_df["open"].values.astype(float)
        raw_high_full = store_df["high"].values.astype(float)
        raw_low_full = store_df["low"].values.astype(float)
        raw_vol_full = store_df["volume"].values.astype(float)

        adj_close_series = split_adjust(pd.Series(raw_close_full, index=store_dates))
        adj_close_full = adj_close_series.values.astype(float)
        factor_full = _compute_split_factor(raw_close_full, adj_close_full)

        # Locate signal bar
        pos_arr = store_dates.searchsorted(signal_ts)
        if pos_arr >= len(store_dates) or store_dates[pos_arr] != signal_ts:
            if row["pm1_reason"] not in ("no_signal_bar",):
                mismatches.append(f"{ticker} {signal_date_str}: signal bar missing after truncate")
            continue

        idx_signal = int(pos_arr)
        n_avail = idx_signal + 1
        n_bars = min(W_BARS, n_avail)
        w_start = idx_signal - n_bars + 1

        raw_c = raw_close_full[w_start:idx_signal + 1]
        adj_c = adj_close_full[w_start:idx_signal + 1]
        factor_w = factor_full[w_start:idx_signal + 1]
        raw_o = raw_open_full[w_start:idx_signal + 1]
        raw_h = raw_high_full[w_start:idx_signal + 1]
        raw_l = raw_low_full[w_start:idx_signal + 1]
        raw_vol_w = raw_vol_full[w_start:idx_signal + 1]

        adj_o = raw_o / factor_w
        adj_h = raw_h / factor_w
        adj_l = raw_l / factor_w
        adj_vol = raw_vol_w * factor_w
        adj_tp = (adj_h + adj_l + adj_c) / 3.0
        adj_dv = adj_tp * adj_vol
        close_s = float(adj_c[-1])

        split_suspect = _has_split_suspect_unadjusted(raw_c, factor_w)

        # Recompute features
        if split_suspect:
            recomp = {
                "pm1": np.nan, "pm2": np.nan, "pm3": np.nan, "pm4": np.nan,
                "pm5": np.nan, "poc_dist_126": np.nan,
                "pm1_reason": "split_suspect", "pm2_reason": "split_suspect",
                "pm3_reason": "split_suspect", "pm4_reason": "split_suspect",
                "pm5_reason": "split_suspect", "poc_reason": "split_suspect",
                "anchor_age_bars": np.nan, "so_staleness_days": np.nan,
                "so_shares_raw": np.nan,
            }
        else:
            pm1_v, aab, pm1_r = compute_pm1(adj_c, adj_tp, adj_vol, n_bars)
            pm2_v, pm2_r = compute_pm2(adj_tp, adj_dv, close_s, n_bars)
            pm3_v, _, pm3_r = compute_pm3(adj_o, adj_h, adj_l, adj_c, close_s, n_bars)
            pm4_v, pm4_r = compute_pm4(adj_tp, adj_dv, close_s, n_bars)
            poc_v, poc_r = compute_poc_dist_126(
                adj_close_full[:idx_signal + 1],
                raw_vol_full[:idx_signal + 1] * factor_full[:idx_signal + 1],
                n_avail,
            )
            stmts_t = stmts_by_ticker.get(ticker, pd.DataFrame())
            # Independent statements PIT truncation (spec §2.3 gate 1): the
            # audit hard-truncates the panel at filed <= signal_date itself,
            # rather than trusting compute_pm5's internal filter.
            if len(stmts_t) > 0:
                stmts_t = stmts_t[stmts_t["filed"] <= signal_date_str]
            pm5_v, so_stale, so_shares, pm5_r = compute_pm5(
                raw_vol_full[:idx_signal + 1], raw_close_full[:idx_signal + 1],
                factor_full[:idx_signal + 1],
                idx_signal, signal_date_str, ticker,
                stmts_t, store_dates,
            )
            recomp = {
                "pm1": pm1_v, "pm2": pm2_v,
                "pm3": float(pm3_v) if not np.isnan(pm3_v if pm3_v is not None else float("nan")) else np.nan,
                "pm4": pm4_v, "pm5": pm5_v, "poc_dist_126": poc_v,
                "pm1_reason": pm1_r, "pm2_reason": pm2_r,
                "pm3_reason": pm3_r if pm3_r else "ok",
                "pm4_reason": pm4_r, "pm5_reason": pm5_r, "poc_reason": poc_r,
                "anchor_age_bars": float(aab) if not pd.isna(aab) else np.nan,
                "so_staleness_days": float(so_stale) if not pd.isna(so_stale) else np.nan,
                "so_shares_raw": float(so_shares) if not pd.isna(so_shares) else np.nan,
            }

        # Compare
        for col in float_cols:
            orig_v = row[col]
            recomp_v = recomp[col]
            orig_nan = pd.isna(orig_v)
            recomp_nan = pd.isna(recomp_v)
            if orig_nan and recomp_nan:
                continue
            if orig_nan != recomp_nan:
                mismatches.append(
                    f"{ticker} {signal_date_str} {col}: orig={'NaN' if orig_nan else orig_v} recomp={'NaN' if recomp_nan else recomp_v}"
                )
                continue
            if not np.isclose(float(orig_v), float(recomp_v), equal_nan=True, rtol=0, atol=0):
                mismatches.append(
                    f"{ticker} {signal_date_str} {col}: orig={orig_v} recomp={recomp_v} (not bit-equal)"
                )

        for col in str_cols:
            orig_v = str(row[col])
            recomp_v = str(recomp[col])
            if orig_v != recomp_v:
                mismatches.append(
                    f"{ticker} {signal_date_str} {col}: orig={orig_v} recomp={recomp_v}"
                )

    return {
        "gate": "pit_spot_audit",
        "n_sampled": len(sample),
        "n_mismatches": len(mismatches),
        "pass": len(mismatches) == 0,
        "mismatches": mismatches[:20],  # cap for JSON
    }


def qa_fence_census(feat_df: pd.DataFrame) -> dict:
    """Gate 2: Split-fence census."""
    census = {}
    for col in ["pm1", "pm2", "pm3", "pm4", "poc_dist_126"]:
        reason_col = col.replace("poc_dist_126", "poc") + "_reason"
        if reason_col.startswith("poc_dist_126"):
            reason_col = "poc_reason"
        if reason_col not in feat_df.columns:
            reason_col = col + "_reason"
        if reason_col not in feat_df.columns:
            census[col] = {"split_suspect": 0}
            continue
        vc = feat_df[reason_col].value_counts().to_dict()
        census[col] = {k: int(v) for k, v in vc.items()}

    n_gaps_ignored_total = int(feat_df["n_gaps_ignored"].sum())
    n_so_split_suspect = int((feat_df["pm5_reason"] == "so_split_suspect").sum())
    n_so_prehistory = int((feat_df["pm5_reason"] == "so_prehistory").sum())
    n_so_corrupt = int((feat_df["pm5_reason"] == "so_corrupt").sum())
    n_so_stale = int((feat_df["pm5_reason"] == "so_stale").sum())
    n_so_missing = int((feat_df["pm5_reason"] == "so_missing").sum())

    return {
        "gate": "fence_census",
        "per_feature": census,
        "n_gaps_ignored_total": n_gaps_ignored_total,
        "so_split_suspect": n_so_split_suspect,
        "so_prehistory": n_so_prehistory,
        "so_corrupt": n_so_corrupt,
        "so_stale": n_so_stale,
        "so_missing": n_so_missing,
        "pass": True,  # census is informational only
    }


def qa_coverage_table(feat_df: pd.DataFrame) -> dict:
    """Gate 3: Coverage table per feature per population."""
    masks = {
        "vg_fires": (feat_df["verdict_type"] == "fire") & (feat_df["verdict_grade"] == True),
        "all_fires": feat_df["verdict_type"] == "fire",
        "vg_near_miss": (feat_df["verdict_type"] == "near_miss") & (feat_df["verdict_grade"] == True),
    }
    table = {}
    for pop_name, mask in masks.items():
        sub = feat_df[mask]
        n_total = len(sub)
        pop_cov = {}
        for col in ["pm1", "pm2", "pm3", "pm4", "pm5", "poc_dist_126"]:
            n_defined = int(sub[col].notna().sum())
            pct = float(n_defined / n_total) if n_total > 0 else 0.0
            pop_cov[col] = {"n_defined": n_defined, "n_total": n_total, "pct": round(pct, 4)}
        table[pop_name] = pop_cov

    # PM5 floor check: 60% floor on vg_fires
    pm5_pct = table["vg_fires"]["pm5"]["pct"]
    pm5_floor_pass = pm5_pct >= 0.60

    return {
        "gate": "coverage_table",
        "table": table,
        "pm5_vg_fire_pct": pm5_pct,
        "pm5_floor_60pct": pm5_floor_pass,
        "pm5_floor_note": "PRE-DECLARED data_blocked (expected fail; < 60% is the blocked condition)",
        "pass": True,  # coverage is informational; pm5 was pre-declared data_blocked
    }


def qa_anchor_sanity(feat_df: pd.DataFrame) -> dict:
    """Gate 4: PM1 anchor-age distribution."""
    vg_fires = feat_df[(feat_df["verdict_type"] == "fire") & (feat_df["verdict_grade"] == True)]
    ages = vg_fires["anchor_age_bars"].dropna()
    n_degenerate = int((ages == 0).sum())
    dist = {
        "min": float(ages.min()) if len(ages) > 0 else None,
        "p25": float(ages.quantile(0.25)) if len(ages) > 0 else None,
        "median": float(ages.median()) if len(ages) > 0 else None,
        "p75": float(ages.quantile(0.75)) if len(ages) > 0 else None,
        "max": float(ages.max()) if len(ages) > 0 else None,
    }
    return {
        "gate": "anchor_sanity",
        "n_defined": int(len(ages)),
        "n_degenerate_anchor": n_degenerate,
        "distribution": dist,
        "pass": True,  # informational
    }


def qa_determinism(feat_df: pd.DataFrame, stmts_by_ticker: dict) -> dict:
    """Gate 5: Determinism check on 200 rows resampled with rng(202)."""
    rng = np.random.default_rng(202)
    idx = rng.choice(len(feat_df), size=min(200, len(feat_df)), replace=False)
    sample = feat_df.iloc[idx].copy()

    # Reconstruct minimal population frame for these rows
    pop_sample = sample[["ticker", "signal_date", "episode_id",
                          "verdict_type", "verdict_grade", "survivor_bias"]].copy()

    stmts_reduced = {t: stmts_by_ticker[t]
                     for t in pop_sample["ticker"].unique()
                     if t in stmts_by_ticker}

    recomp_list = []
    for ticker, grp in pop_sample.groupby("ticker"):
        stmts_t = stmts_reduced.get(ticker, pd.DataFrame())
        results = compute_features_for_ticker(ticker, grp, stmts_t)
        recomp_list.extend(results)

    recomp_df = pd.DataFrame(recomp_list)
    # Align by (ticker, signal_date, episode_id)
    recomp_df = recomp_df.set_index(["ticker", "signal_date", "episode_id"])
    sample_idx = sample.set_index(["ticker", "signal_date", "episode_id"])

    float_cols = ["pm1", "pm2", "pm3", "pm4", "pm5", "poc_dist_126", "anchor_age_bars"]
    str_cols = ["pm1_reason", "pm2_reason", "pm3_reason",
                "pm4_reason", "pm5_reason", "poc_reason"]

    mismatches = []
    for key in sample_idx.index:
        if key not in recomp_df.index:
            mismatches.append(f"Key {key} missing from recomputation")
            continue
        orig_row = sample_idx.loc[key]
        recomp_row = recomp_df.loc[key]

        for col in float_cols:
            ov = orig_row[col]
            rv = recomp_row[col]
            if pd.isna(ov) and pd.isna(rv):
                continue
            if pd.isna(ov) != pd.isna(rv):
                mismatches.append(f"{key} {col}: NaN mismatch orig={ov} recomp={rv}")
                continue
            # Bit-identical check via np.array_equal
            if not np.array_equal(
                np.array([float(ov)], dtype=np.float64),
                np.array([float(rv)], dtype=np.float64),
                equal_nan=True
            ):
                mismatches.append(f"{key} {col}: orig={ov} recomp={rv}")

        for col in str_cols:
            if str(orig_row[col]) != str(recomp_row[col]):
                mismatches.append(f"{key} {col}: orig={orig_row[col]} recomp={recomp_row[col]}")

    return {
        "gate": "determinism",
        "n_sampled": len(sample),
        "n_mismatches": len(mismatches),
        "pass": len(mismatches) == 0,
        "mismatches": mismatches[:20],
    }


def run_qa(feat_df: pd.DataFrame, stmts_by_ticker: dict, out_dir: Path) -> dict:
    """Run all 5 QA gates. Blocking gates exit non-zero on failure."""
    print("\n" + "=" * 72)
    print("QA GATES (§4.4)")
    print("=" * 72)

    results = {}

    print("\n[1/5] PIT spot-audit (seed 606, 60 rows)...")
    g1 = qa_pit_spot_audit(feat_df, stmts_by_ticker)
    results["gate1_pit_audit"] = g1
    status = "PASS" if g1["pass"] else "FAIL"
    print(f"  Result: {status}  mismatches={g1['n_mismatches']}")
    if not g1["pass"]:
        for m in g1["mismatches"]:
            print(f"  MISMATCH: {m}")

    print("\n[2/5] Split-fence census...")
    g2 = qa_fence_census(feat_df)
    results["gate2_fence_census"] = g2
    print(f"  Result: PASS (informational)")
    print(f"  n_gaps_ignored_total: {g2['n_gaps_ignored_total']:,}")
    print(f"  so_split_suspect: {g2['so_split_suspect']:,}  so_corrupt: {g2['so_corrupt']:,}")

    print("\n[3/5] Coverage table...")
    g3 = qa_coverage_table(feat_df)
    results["gate3_coverage"] = g3
    print(f"  Result: PASS (informational)")
    for pop_name, pop_cov in g3["table"].items():
        print(f"  {pop_name}:")
        for col, info in pop_cov.items():
            print(f"    {col}: {info['n_defined']:,}/{info['n_total']:,} = {info['pct']:.1%}")
    print(f"  PM5 coverage on vg_fires: {g3['pm5_vg_fire_pct']:.1%} (floor 60% -> pre-declared data_blocked)")

    print("\n[4/5] Anchor sanity (PM1)...")
    g4 = qa_anchor_sanity(feat_df)
    results["gate4_anchor_sanity"] = g4
    print(f"  Result: PASS (informational)")
    print(f"  n_defined: {g4['n_defined']:,}  n_degenerate: {g4['n_degenerate_anchor']:,}")
    d = g4["distribution"]
    print(f"  age bars: min={d['min']} p25={d['p25']} median={d['median']} p75={d['p75']} max={d['max']}")

    print("\n[5/5] Determinism (seed 202, 200 rows)...")
    g5 = qa_determinism(feat_df, stmts_by_ticker)
    results["gate5_determinism"] = g5
    status = "PASS" if g5["pass"] else "FAIL"
    print(f"  Result: {status}  mismatches={g5['n_mismatches']}")
    if not g5["pass"]:
        for m in g5["mismatches"]:
            print(f"  MISMATCH: {m}")

    # Medians (builder-logged, outcome-blind)
    medians = compute_medians_vg_fires(feat_df)
    results["medians_vg_fires"] = medians
    print("\n  Medians (verdict-grade fires, outcome-blind):")
    for k, v in medians.items():
        print(f"    {k}: {v}")

    # Overall pass/fail: gates 1 and 5 are blocking
    blocking_pass = g1["pass"] and g5["pass"]
    results["overall_pass"] = blocking_pass

    # Write qa_report.json
    qa_path = out_dir / "qa_report.json"
    def _jsonify(obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating, float)):
            fv = float(obj)
            return None if np.isnan(fv) else fv
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, bool):
            return bool(obj)
        return obj

    import json as _json
    with open(qa_path, "w") as fh:
        _json.dump(results, fh, indent=2, default=_jsonify)
    print(f"\nQA report written to: {qa_path}")

    if not blocking_pass:
        print("\nBLOCKER: One or more blocking QA gates FAILED. Study cannot proceed.")
        if not g1["pass"]:
            print("  Gate 1 (PIT audit) FAILED — lookahead suspected in feature computation.")
        if not g5["pass"]:
            print("  Gate 5 (Determinism) FAILED — non-deterministic feature computation.")
        sys.exit(1)

    print("\nAll blocking QA gates PASSED.")
    return results


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="EI-PM0 Price-Memory Feature Builder")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--build", action="store_true",
                       help="Build full feature artifact to <data_root>/replay/pm0_features.parquet")
    group.add_argument("--qa", action="store_true",
                       help="Load artifact and run all 5 QA gates")
    group.add_argument("--smoke", type=int, metavar="N",
                       help="Build only N tickers' rows to --out path for testing")
    parser.add_argument("--out", type=str, default=None,
                        help="Output path override (for --smoke and --build)")
    args = parser.parse_args()

    default_artifact = DATA_ROOT / "replay" / "pm0_features.parquet"
    artifact_path = Path(args.out) if args.out else default_artifact

    if args.build:
        # Full build
        pop = _load_population()
        stmts_by_ticker = _load_statements()
        feat_df = build_features(pop, stmts_by_ticker)
        feat_df.to_parquet(artifact_path, index=False)
        print(f"\nArtifact written: {artifact_path}  ({len(feat_df):,} rows)")
        # Also compute medians
        medians = compute_medians_vg_fires(feat_df)
        print("Medians (vg fires, outcome-blind):")
        for k, v in medians.items():
            print(f"  {k}: {v}")
        # Write medians to qa_report.json skeleton (QA runs separately)
        qa_path = OUT_DIR / "qa_report.json"
        import json as _json
        _json.dump({"medians_vg_fires": medians}, open(qa_path, "w"), indent=2)
        print(f"Medians written to: {qa_path}")

    elif args.qa:
        # QA mode: load existing artifact
        if not artifact_path.exists():
            print(f"BLOCKER: artifact not found at {artifact_path}")
            sys.exit(1)
        print(f"Loading artifact from: {artifact_path}")
        feat_df = pd.read_parquet(artifact_path)
        print(f"  Shape: {feat_df.shape}")
        stmts_by_ticker = _load_statements()
        run_qa(feat_df, stmts_by_ticker, OUT_DIR)

    elif args.smoke is not None:
        # Smoke test: N tickers only
        N = args.smoke
        pop = _load_population()
        tickers_sample = sorted(pop["ticker"].unique())[:N]
        pop_sample = pop[pop["ticker"].isin(tickers_sample)].copy()
        print(f"Smoke test: {N} tickers, {len(pop_sample)} rows")
        stmts_by_ticker = _load_statements()
        stmts_sample = {t: stmts_by_ticker[t]
                        for t in tickers_sample if t in stmts_by_ticker}
        feat_df = build_features(pop_sample, stmts_sample, progress_every=10)
        feat_df.to_parquet(artifact_path, index=False)
        print(f"\nSmoke artifact written: {artifact_path}  ({len(feat_df):,} rows)")
        print("\nSample feature values:")
        for col in ["pm1", "pm2", "pm3", "pm4", "pm5", "poc_dist_126"]:
            defined = feat_df[col].dropna()
            if len(defined) > 0:
                print(f"  {col}: n={len(defined)} mean={defined.mean():.4f} "
                      f"min={defined.min():.4f} max={defined.max():.4f}")
            else:
                print(f"  {col}: all NaN")
        print("\nReason code distribution:")
        for col in ["pm1_reason", "pm2_reason", "pm3_reason",
                    "pm4_reason", "pm5_reason", "poc_reason"]:
            vc = feat_df[col].value_counts().to_dict()
            print(f"  {col}: {vc}")
        print("\nFirst 3 rows:")
        print(feat_df.head(3).to_string())


if __name__ == "__main__":
    main()
