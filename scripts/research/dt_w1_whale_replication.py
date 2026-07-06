"""scripts/research/dt_w1_whale_replication.py — DT-W1a: Survivorship-honest whale
replication study with time-control repair.

Authority: research/DANNYTRADES_NW_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md §4.1
(prereg frozen there; nothing is tunable here).

Amendment DT-W1a (2026-07-06): time-control repair after Opus adversarial bounce.
Primary inference now uses cross-sectional month-demeaning + month-block bootstrap.
Controls upgraded: within-ticker permutation for change tests (H1/H2), within-month
cross-ticker whale-value permutation for level tests (H3/H4).
H4: per-month cross-sectional decile Spearman (mean across months) with month-block
bootstrap CI.  No sp<-0.3 invented threshold.
Real one-sided bootstrap tail fractions replace fabricated CI-ratio p-values.

Family: dt_replication, m=4, BH q=0.10.

Sign convention (applied consistently throughout):
  lift = P(up|event) - P(up|all)  [on the TIME-CONTROLLED / month-demeaned basis]
  NEGATIVE lift means the event group underperforms the panel base rate.
  H1 and H3 expect NEGATIVE lift (whale entering/hot → extended → mean-reverts).
  H2 expects POSITIVE lift (whales leaving → bounce).
  H4 expects NEGATIVE Spearman(decile, mean_fwd_1m) (monotone decreasing = contrarian).

Outputs:
  data/research/dt_w1_replication.json
  research/dannytrades/DT_W1_RESULTS.md
  data/trial_ledger.jsonl (4 appended rows for family dt_replication)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# ---- repo path bootstrap (same as other scripts) ----------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine import dannytrades as dt  # noqa: E402 (whale_buy_fraction)
from engine.trial_ledger import TrialLedger  # noqa: E402

warnings.filterwarnings("ignore", category=FutureWarning)

# ---- frozen constants (DO NOT CHANGE — prereg §4.1) -------------------------
WHALE_WIN_M = 6          # months accumulation window
WHALE_CHG_LAG = 3        # diff(3) for whale_chg
FWD_COL = "fwd_1m"       # non-overlapping forward return
FWD_DM_COL = "fwd_1m_dm" # cross-sectionally demeaned forward return (time-controlled)
THRESH_ENTERING = 10.0   # H1: whale_chg > +10
THRESH_LEAVING = -10.0   # H2: whale_chg < -10
THRESH_HOT = 75.0        # H3: whale level > 75
N_BOOT = 1000            # bootstrap iterations
BOOT_SEED = 11           # fixed seed (from existing harness)
BH_Q = 0.10              # Benjamini-Hochberg threshold
M_TESTS = 4              # family size
MAX_GAP_TRADING_DAYS = 10  # calendar-continuity guard


# ---------------------------------------------------------------------------#
# helpers: monthly bars + calendar guard
# ---------------------------------------------------------------------------#

def _trading_days_in_range(index: pd.DatetimeIndex, start, end) -> int:
    """Count business days in [start, end] using the ticker's own trading calendar."""
    mask = (index >= start) & (index <= end)
    return int(mask.sum())


def _month_has_gap(daily_idx: pd.DatetimeIndex, month_start, month_end) -> bool:
    """Return True if any gap in the daily index exceeds MAX_GAP_TRADING_DAYS
    within [month_start, month_end].

    Uses calendar-join approach: check consecutive-day differences within the
    ticker's actual trading dates for the month window.
    """
    mask = (daily_idx >= month_start) & (daily_idx <= month_end)
    in_window = daily_idx[mask]
    if len(in_window) < 2:
        return False
    diffs = pd.Series(in_window).diff().dt.days.dropna()
    # A gap > 14 calendar days almost certainly exceeds 10 trading days
    # (weekends + 1 holiday = 3 calendar ≈ 2 trading; 10 trading ≈ 14 calendar)
    return bool((diffs > 14).any())


def _build_monthly_for_ticker(
    ticker: str,
    daily_df: pd.DataFrame,
    member_intervals: list[tuple],  # [(start_date, end_date), ...]
) -> tuple[pd.DataFrame, int]:
    """
    Compute monthly bars for a ticker, restricted to member months.
    Returns (monthly_df, excluded_gap_months).

    monthly_df columns: whale, whale_chg, fwd_1m, date, ticker.
    excluded_gap_months: count of months dropped due to calendar-continuity violation.
    """
    # Resample to monthly using ME (month-end)
    m = pd.DataFrame({
        "close": daily_df["close"].resample("ME").last(),
        "high": daily_df["high"].resample("ME").max(),
        "low": daily_df["low"].resample("ME").min(),
        "volume": daily_df["volume"].resample("ME").sum(),
    }).dropna()

    if len(m) < WHALE_WIN_M + WHALE_CHG_LAG + 2:
        return pd.DataFrame(), 0

    # Compute whale metric and derived columns on full monthly series (causal)
    m["whale"] = dt.whale_buy_fraction(
        m["high"], m["low"], m["close"], m["volume"], WHALE_WIN_M
    )
    m["whale_chg"] = m["whale"].diff(WHALE_CHG_LAG)
    # Non-overlapping fwd_1m: pct_change over 1 month shifted back 1 month
    m[FWD_COL] = m["close"].pct_change(fill_method=None).shift(-1) * 100.0

    # --- calendar-continuity guard ---
    excluded_gap_months = 0
    gap_mask = pd.Series(False, index=m.index)
    for me_date in m.index:
        month_start = me_date.replace(day=1)
        if _month_has_gap(daily_df.index, month_start, me_date):
            gap_mask[me_date] = True
            excluded_gap_months += 1

    # Also exclude months where the forward return crosses a gap in the NEXT month
    for me_date in m.index:
        if gap_mask.get(me_date, False):
            continue
        next_me = me_date + pd.offsets.MonthEnd(1)
        if next_me in m.index:
            next_month_start = next_me.replace(day=1)
            if _month_has_gap(daily_df.index, next_month_start, next_me):
                m.loc[me_date, FWD_COL] = np.nan

    m = m[~gap_mask]

    # --- PIT member-month filter ---
    keep = pd.Series(False, index=m.index)
    for (iv_start, iv_end) in member_intervals:
        keep |= (m.index >= iv_start) & (m.index <= iv_end)
    m = m[keep]

    if len(m) == 0:
        return pd.DataFrame(), excluded_gap_months

    m["ticker"] = ticker
    m["date"] = m.index  # carry date as column for groupby (month-block bootstrap)
    m = m[["whale", "whale_chg", FWD_COL, "date", "ticker"]].copy()
    return m, excluded_gap_months


# ---------------------------------------------------------------------------#
# cross-sectional time-control: demean fwd_1m within each calendar month
# ---------------------------------------------------------------------------#

def _add_demeaned_fwd(pool: pd.DataFrame) -> pd.DataFrame:
    """Add fwd_1m_dm = fwd_1m - cross-sectional monthly mean (time-controlled return).

    This removes the calendar-time confound: each row's forward return is expressed
    relative to the average stock in that same month, so panel base return swings
    (e.g. -9.9% in a crash month, +9.6% in a rally month) are neutralised.
    Effective independent N falls to ~60 months, not 591 tickers.
    """
    pool = pool.copy()
    # Cross-sectional mean per month-end date
    pool[FWD_DM_COL] = pool[FWD_COL] - pool.groupby("date")[FWD_COL].transform("mean")
    return pool


# ---------------------------------------------------------------------------#
# bootstrap: RAW (ticker-cluster only, superseded) and TIME-CONTROLLED (primary)
# ---------------------------------------------------------------------------#

def _ticker_cluster_boot(
    work: pd.DataFrame,
    mask: pd.Series,
    fwd_col: str = FWD_COL,
    n_boot: int = N_BOOT,
    seed: int = BOOT_SEED,
) -> dict:
    """Ticker-cluster bootstrap on any fwd column.

    Returns raw_boots array in addition to summary stats.
    """
    w = work.dropna(subset=[fwd_col])
    up = (w[fwd_col].values > 0).astype(float)
    m = mask.reindex(w.index).fillna(False).values
    n_event = int(m.sum())
    if n_event < 30:
        return {"n": n_event, "note": "insufficient events (<30)", "_boots": np.array([])}

    base = float(up.mean())
    real_lift = float(up[m].mean() - base)

    # Cluster by ticker
    g = pd.DataFrame(
        {"t": w["ticker"].values, "up": up, "m": m.astype(float), "um": up * m}
    )
    agg = g.groupby("t").agg(
        n=("up", "size"),
        su=("up", "sum"),
        nm=("m", "sum"),
        sum_um=("um", "sum"),
    )
    n_arr, su_arr, nm_arr, sum_um_arr = (
        agg[c].values for c in ("n", "su", "nm", "sum_um")
    )

    rng = np.random.default_rng(seed)
    T = len(agg)
    boots = np.empty(n_boot)
    for b in range(n_boot):
        s = rng.integers(0, T, T)
        NM = nm_arr[s].sum()
        SUM = sum_um_arr[s].sum()
        N = n_arr[s].sum()
        SU = su_arr[s].sum()
        boots[b] = (SUM / NM - SU / N) if (NM > 0 and N > 0) else np.nan

    boots = boots[np.isfinite(boots)]
    ci_lo = float(np.percentile(boots, 2.5))
    ci_hi = float(np.percentile(boots, 97.5))

    mean_event = float(w[fwd_col].values[m.astype(bool)].mean())
    mean_base = float(w[fwd_col].mean())

    return {
        "n": n_event,
        "p_up": round(float(up[m.astype(bool)].mean()), 4),
        "base_p_up": round(base, 4),
        "lift": round(real_lift, 4),
        "ci95": [round(ci_lo, 4), round(ci_hi, 4)],
        "mean_fwd": round(mean_event, 3),
        "base_fwd": round(mean_base, 3),
        "mean_ret_diff": round(mean_event - mean_base, 3),
        "_boots": boots,  # retained for exact p-value computation
    }


def _month_block_boot(
    work: pd.DataFrame,
    mask: pd.Series,
    fwd_col: str = FWD_DM_COL,
    n_boot: int = N_BOOT,
    seed: int = BOOT_SEED,
) -> dict:
    """Month-block bootstrap: resample months with replacement, then all tickers within.

    This respects the ~60-month effective independent N (calendar-time block structure).
    Applied to fwd_1m_dm (demeaned) for the time-controlled primary inference.
    Returns _boots array for exact p-value computation.
    """
    w = work.dropna(subset=[fwd_col])
    m_col = mask.reindex(w.index).fillna(False)

    # Aggregate to month level: event rate and base rate per month
    w2 = w.copy()
    w2["_up"] = (w2[fwd_col].values > 0).astype(float)
    w2["_m"] = m_col.values.astype(float)
    w2["_um"] = w2["_up"] * w2["_m"]

    by_month = w2.groupby("date").agg(
        n_total=("_up", "size"),
        sum_up=("_up", "sum"),
        n_event=("_m", "sum"),
        sum_um=("_um", "sum"),
    )

    n_event_total = int(by_month["n_event"].sum())
    if n_event_total < 30:
        return {"n": n_event_total, "note": "insufficient events (<30)", "_boots": np.array([])}

    # Real lift on month-demeaned series
    real_base = float(w2["_up"].mean())
    real_event_up = float(w2["_up"][m_col.values.astype(bool)].mean()) if n_event_total > 0 else np.nan
    real_lift = real_event_up - real_base

    # Month-block bootstrap
    n_months = len(by_month)
    nt_arr = by_month["n_total"].values
    su_arr = by_month["sum_up"].values
    ne_arr = by_month["n_event"].values
    sum_um_arr = by_month["sum_um"].values

    rng = np.random.default_rng(seed)
    boots = np.empty(n_boot)
    for b in range(n_boot):
        s = rng.integers(0, n_months, n_months)
        NE = ne_arr[s].sum()
        SUM = sum_um_arr[s].sum()
        NT = nt_arr[s].sum()
        SU = su_arr[s].sum()
        boots[b] = (SUM / NE - SU / NT) if (NE > 0 and NT > 0) else np.nan

    boots = boots[np.isfinite(boots)]
    ci_lo = float(np.percentile(boots, 2.5))
    ci_hi = float(np.percentile(boots, 97.5))

    mean_event = float(w2.loc[m_col.values.astype(bool), fwd_col].mean())
    mean_base = float(w2[fwd_col].mean())

    return {
        "n": n_event_total,
        "n_months": n_months,
        "lift": round(real_lift, 4),
        "ci95": [round(ci_lo, 4), round(ci_hi, 4)],
        "mean_fwd_dm": round(mean_event, 3),
        "base_fwd_dm": round(mean_base, 3),
        "_boots": boots,
    }


# ---------------------------------------------------------------------------#
# p-value: exact one-sided bootstrap tail fraction
# ---------------------------------------------------------------------------#

def _one_sided_p_from_boots(boots: np.ndarray, expected_positive: bool) -> float:
    """Exact one-sided p-value as tail fraction of bootstrap distribution.

    For expected_positive=True: p = fraction of boots <= 0 (wrong side).
    For expected_positive=False: p = fraction of boots >= 0 (wrong side).
    """
    if len(boots) == 0:
        return 1.0
    if expected_positive:
        return float((boots <= 0).mean())
    else:
        return float((boots >= 0).mean())


# ---------------------------------------------------------------------------#
# BH correction (cleaned up — single pass, no redundant loop)
# ---------------------------------------------------------------------------#

def _bh_correct(p_values: list[float], q: float = BH_Q) -> list[bool]:
    """Benjamini-Hochberg correction. Returns list of booleans (survived FDR).

    Standard step-up procedure: all tests at or below the largest rank k where
    p_(k) <= (k/m)*q are declared discoveries.
    """
    m = len(p_values)
    sorted_pairs = sorted(enumerate(p_values), key=lambda x: x[1])
    max_surviving_rank = 0
    for rank, (orig_idx, pv) in enumerate(sorted_pairs, 1):
        if pv <= (rank / m) * q:
            max_surviving_rank = rank

    survived = [False] * m
    for rank, (orig_idx, pv) in enumerate(sorted_pairs, 1):
        if rank <= max_surviving_rank:
            survived[orig_idx] = True
    return survived


# ---------------------------------------------------------------------------#
# H4: per-month cross-sectional decile Spearman (primary) + month-block bootstrap CI
# ---------------------------------------------------------------------------#

def _h4_per_month_spearman(pool: pd.DataFrame) -> dict:
    """H4 primary: per-month cross-sectional decile Spearman, mean across months.

    For each calendar month: assign whale deciles cross-sectionally (10 tickers needed),
    compute Spearman(decile rank, mean fwd_1m). Expected sign: negative.
    Month-block bootstrap CI by resampling months.
    """
    sub = pool.dropna(subset=["whale", FWD_COL, "date"]).copy()
    months = sub["date"].unique()

    monthly_sp = []
    for mo in months:
        g = sub[sub["date"] == mo].copy()
        if g["whale"].nunique() < 5:
            continue
        try:
            g["dec"] = pd.qcut(g["whale"], 10, labels=False, duplicates="drop")
        except Exception:
            continue
        gm = g.dropna(subset=["dec"]).groupby("dec")[FWD_COL].mean()
        if len(gm) < 4:
            continue
        dr = np.arange(1, len(gm) + 1, dtype=float)
        rr = gm.reset_index(drop=True).values
        # Spearman = Pearson on ranks
        rr_ranks = pd.Series(rr).rank().values
        sp = float(np.corrcoef(dr, rr_ranks)[0, 1]) if len(dr) > 1 else np.nan
        if np.isfinite(sp):
            monthly_sp.append(sp)

    if len(monthly_sp) < 3:
        return {"n": int(sub.shape[0]), "note": "insufficient months for H4"}

    mean_sp = float(np.mean(monthly_sp))
    n_months_used = len(monthly_sp)

    # Month-block bootstrap CI on the per-month Spearman series
    rng = np.random.default_rng(BOOT_SEED)
    monthly_sp_arr = np.array(monthly_sp)
    boots = np.array([
        float(np.mean(monthly_sp_arr[rng.integers(0, n_months_used, n_months_used)]))
        for _ in range(N_BOOT)
    ])
    ci_lo = float(np.percentile(boots, 2.5))
    ci_hi = float(np.percentile(boots, 97.5))

    # Also compute pooled equal-count and equal-width for side-by-side reporting
    sub["dec_pool_eq"] = pd.qcut(sub["whale"], 10, labels=False, duplicates="drop")
    gp = sub.dropna(subset=["dec_pool_eq"]).groupby("dec_pool_eq")[FWD_COL].agg(["mean", "size"])
    dr_pool = np.arange(1, len(gp) + 1, dtype=float)
    rr_pool = pd.Series(gp["mean"].values).rank().values
    sp_pool_eq = float(np.corrcoef(dr_pool, rr_pool)[0, 1]) if len(dr_pool) > 1 else np.nan

    sub["dec_pool_ew"] = pd.cut(sub["whale"], 10, labels=False)
    gpw = sub.dropna(subset=["dec_pool_ew"]).groupby("dec_pool_ew")[FWD_COL].agg(["mean", "size"])
    if len(gpw) > 1:
        dr_ew = np.arange(1, len(gpw) + 1, dtype=float)
        rr_ew = pd.Series(gpw["mean"].values).rank().values
        sp_pool_ew = float(np.corrcoef(dr_ew, rr_ew)[0, 1])
    else:
        sp_pool_ew = np.nan

    return {
        "n": int(sub.shape[0]),
        "n_months": n_months_used,
        "spearman_per_month_mean": round(mean_sp, 4),
        "ci95": [round(ci_lo, 4), round(ci_hi, 4)],
        "spearman_pooled_equal_count": round(float(sp_pool_eq), 4) if np.isfinite(sp_pool_eq) else None,
        "spearman_pooled_equal_width": round(float(sp_pool_ew), 4) if np.isfinite(sp_pool_ew) else None,
        "by_decile_mean_pooled_eq": [round(float(x), 4) for x in gp["mean"]],
        "decile_sizes_pooled_eq": [int(x) for x in gp["size"]],
        "_boots": boots,
    }


# ---------------------------------------------------------------------------#
# calibration controls (4 total: 2 for change tests, 2 for level tests)
# ---------------------------------------------------------------------------#

def _ctrl_within_ticker_time_permutation(pool: pd.DataFrame) -> dict:
    """Control C1: within-ticker time permutation (for H1/H2 — change-based tests).

    Shuffles the temporal order of whale values within each ticker, breaking
    the time alignment between whale_chg and subsequent returns.
    Appropriate for change tests because it destroys the temporal signal while
    preserving per-ticker distribution.
    """
    rng = np.random.default_rng(42)
    pool_perm = pool.copy()
    for ticker in pool_perm["ticker"].unique():
        mask = pool_perm["ticker"] == ticker
        idx = pool_perm.index[mask]
        vals = pool_perm.loc[idx, "whale"].values.copy()
        rng.shuffle(vals)
        pool_perm.loc[idx, "whale"] = vals
        pool_perm.loc[idx, "whale_chg"] = pd.Series(
            vals, index=idx
        ).diff(WHALE_CHG_LAG).values

    h1 = _ticker_cluster_boot(pool_perm, pool_perm["whale_chg"] > THRESH_ENTERING, fwd_col=FWD_COL)
    h2 = _ticker_cluster_boot(pool_perm, pool_perm["whale_chg"] < THRESH_LEAVING, fwd_col=FWD_COL)
    return {
        "label": "within-ticker time permutation (for change tests H1/H2)",
        "h1_neg_ctrl": {k: v for k, v in h1.items() if k != "_boots"},
        "h2_neg_ctrl": {k: v for k, v in h2.items() if k != "_boots"},
    }


def _ctrl_within_month_cross_ticker_permutation(pool: pd.DataFrame) -> dict:
    """Control C2: within-month cross-ticker permutation of whale values (for H3/H4).

    Shuffles whale values across tickers WITHIN each calendar month.
    This breaks the ticker-selection channel (which tickers have high whale)
    while preserving the temporal distribution of whale levels.

    This is the correct control for level tests (H3/H4) because within-ticker
    permutation is structurally powerless for level thresholds: the per-ticker
    whale VALUE multiset is preserved, so high-whale tickers stay selected under
    the null, producing a POSITIVE selection artifact (permuted-H3 mean fwd_1m
    was +1.481% vs base +0.598% in the prior run — artifact, not null).
    """
    rng = np.random.default_rng(43)
    pool_perm = pool.copy()
    for date_val in pool_perm["date"].unique():
        mask = pool_perm["date"] == date_val
        idx = pool_perm.index[mask]
        vals = pool_perm.loc[idx, "whale"].values.copy()
        rng.shuffle(vals)
        pool_perm.loc[idx, "whale"] = vals
    # whale_chg is not used in the level tests; leave as-is

    h3 = _ticker_cluster_boot(pool_perm, pool_perm["whale"] > THRESH_HOT, fwd_col=FWD_COL)
    return {
        "label": "within-month cross-ticker whale permutation (for level tests H3/H4)",
        "mechanism": "shuffles which ticker holds which whale value each month; breaks selection channel",
        "h3_neg_ctrl_level": {k: v for k, v in h3.items() if k != "_boots"},
    }


def _ctrl_within_ticker_time_permutation_on_demeaned(pool: pd.DataFrame) -> dict:
    """Control C3: within-ticker time permutation on the demeaned series (for H1/H2 TC basis).

    Same as C1 but applied to the time-controlled (demeaned) fwd_1m_dm.
    Validates the time-controlled bootstrap machinery.
    """
    rng = np.random.default_rng(44)
    pool_perm = pool.copy()
    for ticker in pool_perm["ticker"].unique():
        mask = pool_perm["ticker"] == ticker
        idx = pool_perm.index[mask]
        vals = pool_perm.loc[idx, "whale"].values.copy()
        rng.shuffle(vals)
        pool_perm.loc[idx, "whale"] = vals
        pool_perm.loc[idx, "whale_chg"] = pd.Series(
            vals, index=idx
        ).diff(WHALE_CHG_LAG).values

    h1 = _month_block_boot(pool_perm, pool_perm["whale_chg"] > THRESH_ENTERING)
    h2 = _month_block_boot(pool_perm, pool_perm["whale_chg"] < THRESH_LEAVING)
    return {
        "label": "within-ticker time permutation on time-controlled (demeaned) series",
        "h1_neg_ctrl_tc": {k: v for k, v in h1.items() if k != "_boots"},
        "h2_neg_ctrl_tc": {k: v for k, v in h2.items() if k != "_boots"},
    }


def _ctrl_positive_injection(pool: pd.DataFrame) -> dict:
    """Control C4: inject +2pp into fwd_1m on H2-mask rows.
    H2 must detect the injected signal (CI excludes zero above).
    """
    pool_inj = pool.copy()
    h2_mask = pool_inj["whale_chg"] < THRESH_LEAVING
    pool_inj.loc[h2_mask, FWD_COL] = pool_inj.loc[h2_mask, FWD_COL] + 2.0
    # Recompute demeaned after injection
    pool_inj[FWD_DM_COL] = pool_inj[FWD_COL] - pool_inj.groupby("date")[FWD_COL].transform("mean")
    r = _month_block_boot(pool_inj, h2_mask)
    return {
        "label": "inject +2pp into fwd_1m on H2-mask rows (for change test H2)",
        "h2_pos_ctrl": {k: v for k, v in r.items() if k != "_boots"},
    }


# ---------------------------------------------------------------------------#
# descriptive companion: composite-score deciles at 63d (PIT-filtered)
# ---------------------------------------------------------------------------#

def _descriptive_63d_deciles(
    ticker_daily_data: dict[str, pd.DataFrame],
    member_intervals: dict,
) -> dict | None:
    """Descriptive only (not in FDR family): composite-score deciles at 63d.

    Applies PIT member-month filter: a (ticker, date) row is included only when
    the ticker was a PIT member at that date. N is labeled as membership-filtered.
    """
    rows = []
    today = pd.Timestamp("2026-07-06")
    for ticker, daily_df in ticker_daily_data.items():
        try:
            sig = dt.signals(
                daily_df["close"].astype(float),
                daily_df["high"].astype(float),
                daily_df["low"].astype(float),
                daily_df["volume"].astype(float),
            )
            fwd63 = (
                daily_df["close"].astype(float)
                .pct_change(63, fill_method=None)
                .shift(-63)
                * 100.0
            )
            combo = pd.DataFrame({"score": sig["score"], "fwd63": fwd63, "date": sig.index})

            # PIT filter: keep only rows where ticker was a member
            if ticker in member_intervals:
                keep = pd.Series(False, index=combo.index)
                for (iv_start, iv_end) in member_intervals[ticker]:
                    keep |= (combo.index >= iv_start) & (combo.index <= iv_end)
                combo = combo[keep]

            rows.append(combo)
        except Exception:
            continue

    if not rows:
        return None

    pool = pd.concat(rows, ignore_index=True).dropna(subset=["score", "fwd63"])
    pool["decile"] = pd.qcut(pool["score"], 10, labels=False, duplicates="drop")
    g = pool.dropna(subset=["decile"]).groupby("decile")["fwd63"].agg(["mean", "size"])
    dec_rank = pd.Series(g.index.astype(float) + 1)
    ret_rank = g["mean"].reset_index(drop=True).rank()
    sp = float(dec_rank.corr(ret_rank))

    return {
        "label": "DESCRIPTIVE-ONLY: composite-score deciles at 63d (overlapping, PIT-filtered, not in FDR family)",
        "n": int(len(pool)),
        "spearman": round(sp, 4),
        "by_decile_mean_63d": [round(float(x), 4) for x in g["mean"]],
    }


# ---------------------------------------------------------------------------#
# main study
# ---------------------------------------------------------------------------#

def run_study(store_dir: Path, pit_path: Path, out_json: Path, out_md: Path) -> dict:
    print(f"[DT-W1a] store_dir={store_dir}", file=sys.stderr)

    # --- build PIT member-month lookup ---
    pit = pd.read_parquet(pit_path)
    today = pd.Timestamp("2026-07-06")
    pit["end_date"] = pit["end_date"].fillna(today)
    window_start = pd.Timestamp("2021-07-06")

    in_scope = pit[pit["end_date"] >= window_start].copy()

    ticker_intervals: dict[str, list[tuple]] = {}
    exited_tickers: set[str] = set()
    for _, row in in_scope.iterrows():
        t = row["ticker"]
        iv_start = max(row["start_date"], window_start)
        iv_end = row["end_date"]
        if iv_end < today:
            exited_tickers.add(t)
        if t not in ticker_intervals:
            ticker_intervals[t] = []
        ticker_intervals[t].append((iv_start, iv_end))

    all_tickers = sorted(ticker_intervals.keys())
    print(f"[DT-W1a] in-scope tickers: {len(all_tickers)}", file=sys.stderr)
    print(f"[DT-W1a] of which exited/delisted mid-window: {len(exited_tickers)}", file=sys.stderr)

    # --- load daily data and compute monthly bars ---
    all_frames = []
    missing_store = []
    total_gap_excluded = 0
    store_latest: pd.Timestamp | None = None
    loaded_ticker_data: dict[str, pd.DataFrame] = {}
    tickers_with_data = []

    for ticker in all_tickers:
        path = store_dir / f"{ticker}.parquet"
        if not path.exists():
            missing_store.append(ticker)
            continue

        try:
            daily = pd.read_parquet(path)
            if daily.index.tz is not None:
                daily.index = daily.index.tz_localize(None)
            daily = daily.sort_index()
            daily = daily[daily.index >= window_start]
            if len(daily) < 30:
                continue

            if store_latest is None or daily.index.max() > store_latest:
                store_latest = daily.index.max()

            intervals = ticker_intervals[ticker]
            mdf, gap_excl = _build_monthly_for_ticker(ticker, daily, intervals)
            total_gap_excluded += gap_excl

            if len(mdf) > 0:
                all_frames.append(mdf)
                tickers_with_data.append(ticker)
                loaded_ticker_data[ticker] = daily
        except Exception as e:
            print(f"[DT-W1a] ERROR loading {ticker}: {e}", file=sys.stderr)
            continue

    n_tickers_with_data = len(tickers_with_data)
    print(f"[DT-W1a] tickers with usable monthly data: {n_tickers_with_data}", file=sys.stderr)
    print(f"[DT-W1a] missing store: {len(missing_store)} → {missing_store}", file=sys.stderr)
    print(f"[DT-W1a] gap-excluded months: {total_gap_excluded}", file=sys.stderr)

    if not all_frames:
        raise RuntimeError("No data frames — check store path")

    pool = pd.concat(all_frames, ignore_index=True)
    print(f"[DT-W1a] pool rows (ticker-months): {len(pool)}", file=sys.stderr)

    # --- add time-controlled column ---
    pool = _add_demeaned_fwd(pool)

    # Coverage stats
    n_tickers_total = len(all_tickers)
    coverage_pct = round(n_tickers_with_data / n_tickers_total * 100, 1)
    total_member_months_possible = int(pool.shape[0])
    n_full = pool.dropna(subset=["whale", "whale_chg", FWD_COL]).shape[0]
    n_months = pool["date"].nunique()

    # Panel base return range (to show calendar-time confound magnitude)
    bymo = pool.dropna(subset=[FWD_COL]).groupby("date")[FWD_COL].mean()
    panel_fwd_min = round(float(bymo.min()), 3)
    panel_fwd_max = round(float(bymo.max()), 3)

    print(f"[DT-W1a] panel monthly fwd_1m range: {panel_fwd_min}% to {panel_fwd_max}%", file=sys.stderr)
    print(f"[DT-W1a] effective months: {n_months}", file=sys.stderr)

    # --- run H1-H4 on BOTH bases ---
    h1_mask = pool["whale_chg"] > THRESH_ENTERING
    h2_mask = pool["whale_chg"] < THRESH_LEAVING
    h3_mask = pool["whale"] > THRESH_HOT

    print("[DT-W1a] running H1/H2/H3 raw (ticker-cluster, superseded)...", file=sys.stderr)
    h1_raw = _ticker_cluster_boot(pool, h1_mask, fwd_col=FWD_COL)
    h2_raw = _ticker_cluster_boot(pool, h2_mask, fwd_col=FWD_COL)
    h3_raw = _ticker_cluster_boot(pool, h3_mask, fwd_col=FWD_COL)

    print("[DT-W1a] running H1/H2/H3 time-controlled (month-block, primary)...", file=sys.stderr)
    h1_tc = _month_block_boot(pool, h1_mask)
    h2_tc = _month_block_boot(pool, h2_mask)
    h3_tc = _month_block_boot(pool, h3_mask)

    print("[DT-W1a] running H4 (per-month Spearman with month-block CI)...", file=sys.stderr)
    h4 = _h4_per_month_spearman(pool)

    # --- exact one-sided p-values from bootstrap tail fractions ---
    p_h1 = _one_sided_p_from_boots(h1_tc.get("_boots", np.array([])), expected_positive=False)
    p_h2 = _one_sided_p_from_boots(h2_tc.get("_boots", np.array([])), expected_positive=True)
    p_h3 = _one_sided_p_from_boots(h3_tc.get("_boots", np.array([])), expected_positive=False)
    p_h4 = _one_sided_p_from_boots(h4.get("_boots", np.array([])), expected_positive=False)

    p_values = [p_h1, p_h2, p_h3, p_h4]
    bh_survived = _bh_correct(p_values, BH_Q)

    # Verdict rule (frozen): REPLICATED iff BH-surviving AND CI excludes zero at settled sign
    def _ci_excludes_zero_at_sign(r, expected_positive: bool) -> bool:
        if "ci95" not in r:
            return False
        lo, hi = r["ci95"]
        if expected_positive:
            return lo > 0
        else:
            return hi < 0

    h1_ci_ok = _ci_excludes_zero_at_sign(h1_tc, expected_positive=False)
    h2_ci_ok = _ci_excludes_zero_at_sign(h2_tc, expected_positive=True)
    h3_ci_ok = _ci_excludes_zero_at_sign(h3_tc, expected_positive=False)
    # H4: CI from per-month bootstrap must exclude zero at the negative sign
    h4_ci_ok = _ci_excludes_zero_at_sign(h4, expected_positive=False)

    h1_verdict = "REPLICATED" if (bh_survived[0] and h1_ci_ok) else "FAILED"
    h2_verdict = "REPLICATED" if (bh_survived[1] and h2_ci_ok) else "FAILED"
    h3_verdict = "REPLICATED" if (bh_survived[2] and h3_ci_ok) else "FAILED"
    h4_verdict = "REPLICATED" if (bh_survived[3] and h4_ci_ok) else "FAILED"

    # --- calibration controls (4 total) ---
    print("[DT-W1a] running control C1: within-ticker time permutation (H1/H2 raw)...", file=sys.stderr)
    ctrl_c1 = _ctrl_within_ticker_time_permutation(pool)
    print("[DT-W1a] running control C2: within-month cross-ticker permutation (H3/H4)...", file=sys.stderr)
    ctrl_c2 = _ctrl_within_month_cross_ticker_permutation(pool)
    print("[DT-W1a] running control C3: within-ticker permutation on demeaned (H1/H2 TC)...", file=sys.stderr)
    ctrl_c3 = _ctrl_within_ticker_time_permutation_on_demeaned(pool)
    print("[DT-W1a] running control C4: positive injection (H2)...", file=sys.stderr)
    ctrl_c4 = _ctrl_positive_injection(pool)

    # --- descriptive companion (63d deciles, PIT-filtered) ---
    print("[DT-W1a] running descriptive companion (63d deciles, PIT-filtered)...", file=sys.stderr)
    try:
        desc_63d = _descriptive_63d_deciles(loaded_ticker_data, ticker_intervals)
    except Exception as e:
        print(f"[DT-W1a] descriptive companion error (skipped): {e}", file=sys.stderr)
        desc_63d = None

    # --- assemble results ---
    def _strip_boots(d: dict) -> dict:
        """Remove _boots arrays from results dict (not JSON serialisable)."""
        return {k: v for k, v in d.items() if k != "_boots"}

    coverage_stamps = {
        "n_tickers_in_scope": n_tickers_total,
        "n_tickers_with_data": n_tickers_with_data,
        "coverage_pct": coverage_pct,
        "n_exited_delisted_included": len(exited_tickers),
        "n_missing_store": len(missing_store),
        "missing_store_tickers": missing_store,
        "total_gap_excluded_months": total_gap_excluded,
        "pool_ticker_months_total": total_member_months_possible,
        "pool_rows_with_whale_and_fwd": n_full,
        "n_calendar_months": n_months,
        "panel_fwd_1m_range_pct": [panel_fwd_min, panel_fwd_max],
        "store_latest_date": str(store_latest.date()) if store_latest else None,
        "effective_window_start": "2021-07-06 + warmup (6mo whale win + 3mo diff = ~9 months warm-up)",
        "effective_event_start_approx": "2022-04-30",
        "study_run_date": datetime.now(timezone.utc).isoformat(),
        "era_law": "data/massive_stock_day/ 2021-07-06+ (DT-R12); no pre-2021 volume claims",
        "amendment": "DT-W1a: time-control repair (cross-sectional demeaning + month-block bootstrap)",
    }

    results = {
        "amendment": "DT-W1a — 2026-07-06: time-control repair after Opus adversarial bounce",
        "coverage": coverage_stamps,
        # PRIMARY (time-controlled) basis
        "h1": {**_strip_boots(h1_tc), "mask": "whale_chg > +10", "expected_sign": "negative",
               "basis": "time-controlled (primary)",
               "p_exact": round(p_h1, 4), "bh_survived": bh_survived[0],
               "ci_excludes_zero_at_sign": h1_ci_ok, "verdict": h1_verdict},
        "h2": {**_strip_boots(h2_tc), "mask": "whale_chg < -10", "expected_sign": "positive",
               "basis": "time-controlled (primary)",
               "p_exact": round(p_h2, 4), "bh_survived": bh_survived[1],
               "ci_excludes_zero_at_sign": h2_ci_ok, "verdict": h2_verdict},
        "h3": {**_strip_boots(h3_tc), "mask": "whale > 75", "expected_sign": "negative",
               "basis": "time-controlled (primary)",
               "p_exact": round(p_h3, 4), "bh_survived": bh_survived[2],
               "ci_excludes_zero_at_sign": h3_ci_ok, "verdict": h3_verdict},
        "h4": {**_strip_boots(h4), "expected_sign": "spearman < 0",
               "basis": "per-month cross-sectional decile Spearman (primary)",
               "p_exact": round(p_h4, 4), "bh_survived": bh_survived[3],
               "ci_excludes_zero_at_sign": h4_ci_ok, "verdict": h4_verdict},
        # RAW (superseded) basis for transparency
        "h1_raw": {**_strip_boots(h1_raw), "basis": "raw ticker-cluster only (superseded)",
                   "note": "superseded by time-controlled; calendar confound not removed"},
        "h2_raw": {**_strip_boots(h2_raw), "basis": "raw ticker-cluster only (superseded)",
                   "note": "superseded by time-controlled; calendar confound not removed"},
        "h3_raw": {**_strip_boots(h3_raw), "basis": "raw ticker-cluster only (superseded)",
                   "note": "superseded by time-controlled; calendar confound not removed"},
        # Controls
        "controls": {
            "c1_within_ticker_time_permutation": ctrl_c1,
            "c2_within_month_cross_ticker_permutation": ctrl_c2,
            "c3_within_ticker_time_permutation_demeaned": ctrl_c3,
            "c4_positive_injection": ctrl_c4,
        },
        "descriptive_63d_deciles": desc_63d,
        "bh_correction": {
            "q": BH_Q,
            "m": M_TESTS,
            "p_values_exact": [round(p, 4) for p in p_values],
            "survived": bh_survived,
            "method": "exact one-sided bootstrap tail fractions",
        },
    }

    # --- register trial ledger rows ---
    _register_trial_ledger(results)

    # --- write JSON output ---
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(results, indent=2, default=str))
    print(f"[DT-W1a] wrote {out_json}", file=sys.stderr)

    # --- write markdown results ---
    out_md.parent.mkdir(parents=True, exist_ok=True)
    _write_markdown(results, out_md)
    print(f"[DT-W1a] wrote {out_md}", file=sys.stderr)

    return results


def _register_trial_ledger(results: dict) -> None:
    """Append 4 trial rows for family dt_replication to data/trial_ledger.jsonl.

    Does NOT rewrite history: existing rows are deduped by config_hash.
    Amended verdicts are noted via the 'note' field on any newly-logged rows.
    """
    ledger_path = REPO_ROOT / "data" / "trial_ledger.jsonl"
    led = TrialLedger(ledger_path, family="dt_replication")

    amendment_note = "DT-W1a: time-controlled verdict (month-block bootstrap + cross-sectional demeaning)"
    tests = [
        {"hypothesis": "H1", "event": "whale_chg > +10", "expected_sign": "negative",
         "metric": "lift_P_up_demeaned", "verdict": results["h1"]["verdict"],
         "study": "DT-W1a", "prereg": "DANNYTRADES_NW_ADJUDICATION §4.1",
         "basis": "time-controlled"},
        {"hypothesis": "H2", "event": "whale_chg < -10", "expected_sign": "positive",
         "metric": "lift_P_up_demeaned", "verdict": results["h2"]["verdict"],
         "study": "DT-W1a", "prereg": "DANNYTRADES_NW_ADJUDICATION §4.1",
         "basis": "time-controlled"},
        {"hypothesis": "H3", "event": "whale_level > 75", "expected_sign": "negative",
         "metric": "lift_P_up_demeaned", "verdict": results["h3"]["verdict"],
         "study": "DT-W1a", "prereg": "DANNYTRADES_NW_ADJUDICATION §4.1",
         "basis": "time-controlled"},
        {"hypothesis": "H4", "event": "whale_decile_monotonicity", "expected_sign": "spearman_negative",
         "metric": "per_month_spearman_mean", "verdict": results["h4"]["verdict"],
         "study": "DT-W1a", "prereg": "DANNYTRADES_NW_ADJUDICATION §4.1",
         "basis": "per-month-spearman"},
    ]

    for config in tests:
        led.log_trial(config, note=amendment_note)

    print(f"[DT-W1a] registered 4 trial rows for family dt_replication", file=sys.stderr)


def _write_markdown(results: dict, out_md: Path) -> None:
    """Write the DT-W1a results markdown file."""
    cov = results["coverage"]
    h1 = results["h1"]
    h2 = results["h2"]
    h3 = results["h3"]
    h4 = results["h4"]
    h1r = results["h1_raw"]
    h2r = results["h2_raw"]
    h3r = results["h3_raw"]
    bh = results["bh_correction"]
    ctrl = results["controls"]
    desc = results.get("descriptive_63d_deciles")

    def fmt_ci(r, key="ci95"):
        if key not in r:
            return "n/a"
        lo, hi = r[key]
        return f"[{lo:+.4f}, {hi:+.4f}]"

    def fmt_lift(r, key="lift"):
        if key not in r:
            return "n/a"
        return f"{r[key]:+.4f}"

    def fmt_n(r):
        return str(r.get("n", "n/a"))

    lines = [
        "# DT-W1a: Survivorship-Honest Whale Replication — Time-Control Repair",
        "",
        f"**Authority:** research/DANNYTRADES_NW_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md §4.1  ",
        f"**Run date:** {cov['study_run_date']}  ",
        f"**Era law:** {cov['era_law']}",
        "",
        "---",
        "",
        "## Amendment DT-W1a — Time-Control Repair After Adversarial Bounce",
        "",
        "**What changed and why:**",
        "",
        "The original DT-W1 run (2026-07-06) was bounced by an Opus adversarial review",
        "for two structural inference failures:",
        "",
        "1. **Calendar-time confound not controlled.** The panel monthly base return ranged",
        f"   from {cov['panel_fwd_1m_range_pct'][0]:+.1f}% to {cov['panel_fwd_1m_range_pct'][1]:+.1f}% across calendar months.",
        "   Events are time-clustered (whale_chg events tend to cluster in trending months),",
        f"   so the effective independent N is ~{cov['n_calendar_months']} calendar months, not the",
        f"   {cov['n_tickers_with_data']} tickers suggested by ticker-cluster bootstrap.",
        "   The raw basis CIs were therefore too narrow.",
        "",
        "2. **Within-ticker permutation structurally powerless for level tests (H3/H4).**",
        "   Within-ticker permutation preserves each ticker's whale VALUE multiset, so",
        "   high-whale tickers remain selected under the null. This produces a POSITIVE",
        "   selection artifact (permuted-H3 mean fwd_1m +1.481% vs base +0.598%), not the",
        "   null outcome claimed. The prior MD's 'negative drift' excuse had the sign wrong.",
        "",
        "**Fixes applied (fix list from review):**",
        "",
        "- **Primary inference:** cross-sectional demeaning of fwd_1m within each calendar",
        "  month + month-block bootstrap (resample months with replacement). Verdicts are",
        "  on this time-controlled basis. Raw (ticker-cluster only) shown as superseded context.",
        "- **Controls:** 4 controls total — C1 within-ticker time permutation (H1/H2 raw),",
        "  C2 within-month cross-ticker whale permutation (H3/H4 — breaks selection channel),",
        "  C3 within-ticker permutation on demeaned series (H1/H2 TC), C4 positive injection.",
        "- **H4:** per-month cross-sectional decile Spearman (mean across months) with",
        "  month-block bootstrap CI. The invented sp<-0.3 threshold is dropped.",
        "  Pooled equal-count and equal-width shown side by side for transparency.",
        "- **p-values:** exact one-sided bootstrap tail fractions (fraction of bootstrap",
        "  replicates on the wrong side). No fabricated CI-ratio approximations.",
        "- **63d companion:** PIT member filter applied; N labeled as membership-filtered.",
        "",
        "---",
        "",
        "## Coverage Stamps",
        "",
        "| Item | Value |",
        "|------|-------|",
        f"| Tickers in scope (PIT member-months overlapping 2021-07-06→today) | {cov['n_tickers_in_scope']} |",
        f"| Tickers with store data | {cov['n_tickers_with_data']} ({cov['coverage_pct']}%) |",
        f"| Exited/delisted mid-window (INCLUDED for member months) | {cov['n_exited_delisted_included']} |",
        f"| Missing store files | {cov['n_missing_store']} ({', '.join(cov['missing_store_tickers']) if cov['missing_store_tickers'] else 'none'}) |",
        f"| Total pool ticker-months | {cov['pool_ticker_months_total']} |",
        f"| Pool rows with both whale and fwd_1m | {cov['pool_rows_with_whale_and_fwd']} |",
        f"| Calendar months in panel | {cov['n_calendar_months']} (effective independent N) |",
        f"| Panel fwd_1m range across months | {cov['panel_fwd_1m_range_pct'][0]:+.1f}% to {cov['panel_fwd_1m_range_pct'][1]:+.1f}% |",
        f"| Gap-excluded months (calendar-continuity guard) | {cov['total_gap_excluded_months']} |",
        f"| Store latest date | {cov['store_latest_date']} |",
        f"| Effective event window start (approx) | {cov['effective_event_start_approx']} |",
        f"| Warm-up reason | {cov['effective_window_start']} |",
        "",
        "---",
        "",
        "## Sign Convention",
        "",
        "**lift = P(up|event) − P(up|all)  [on the time-controlled / month-demeaned basis]**  ",
        "NEGATIVE lift = event group underperforms the panel base rate after month demean.  ",
        "H1 and H3 expect NEGATIVE lift (extended/hot whale → mean-reversion).  ",
        "H2 expects POSITIVE lift (whales leaving → bounce).  ",
        "H4 expects NEGATIVE Spearman (higher whale decile → lower fwd_1m).",
        "",
        "---",
        "",
        "## H1–H4 Results — Time-Controlled (Primary Basis)",
        "",
        f"**Family:** dt_replication | **m={M_TESTS}** | **BH q={BH_Q}** | **Inference:** month-block bootstrap on cross-sectionally demeaned fwd_1m",
        "",
        "| Test | Event | N events | N months | Lift (time-ctrl) | 95% CI | Exact p | BH survived | CI excl zero | Verdict |",
        "|------|-------|----------|----------|-----------------|--------|---------|-------------|--------------|---------|",
    ]

    for hid, hr in [("H1", h1), ("H2", h2), ("H3", h3)]:
        ci_str = fmt_ci(hr)
        lift_str = fmt_lift(hr)
        n_mo = hr.get("n_months", "n/a")
        lines.append(
            f"| {hid} | {hr.get('mask','?')} | {fmt_n(hr)} | {n_mo} | {lift_str} | {ci_str} | {hr.get('p_exact','n/a'):.3f} | {'Yes' if hr.get('bh_survived') else 'No'} | {'Yes' if hr.get('ci_excludes_zero_at_sign') else 'No'} | **{hr.get('verdict','?')}** |"
        )

    h4_sp = h4.get("spearman_per_month_mean", "n/a")
    h4_ci = fmt_ci(h4)
    h4_n_mo = h4.get("n_months", "n/a")
    lines.append(
        f"| H4 | whale decile monotonicity | {fmt_n(h4)} obs | {h4_n_mo} | Spearman={h4_sp} | {h4_ci} | {h4.get('p_exact','n/a'):.3f} | {'Yes' if h4.get('bh_survived') else 'No'} | {'Yes' if h4.get('ci_excludes_zero_at_sign') else 'No'} | **{h4.get('verdict','?')}** |"
    )

    lines.extend([
        "",
        "**H4 side-by-side (per-month primary vs pooled comparisons):**",
        "",
        "| Method | Spearman | CI 95% |",
        "|--------|----------|--------|",
        f"| Per-month mean (PRIMARY) | {h4.get('spearman_per_month_mean','n/a')} | {fmt_ci(h4)} |",
        f"| Pooled equal-count | {h4.get('spearman_pooled_equal_count','n/a')} | (not bootstrapped) |",
        f"| Pooled equal-width | {h4.get('spearman_pooled_equal_width','n/a')} | (not bootstrapped) |",
        "",
        "---",
        "",
        "## H1–H4 Results — Raw Basis (Ticker-Cluster Only, Superseded)",
        "",
        "Shown for continuity with original DT-W1 run. **Do not use for verdict purposes.**",
        "Calendar-time confound not removed; CIs are too narrow (effective N ~600 tickers",
        f"but ~{cov['n_calendar_months']} independent months).",
        "",
        "| Test | N events | Lift (raw) | 95% CI (raw) |",
        "|------|----------|-----------|--------------|",
        f"| H1 | {fmt_n(h1r)} | {fmt_lift(h1r)} | {fmt_ci(h1r)} |",
        f"| H2 | {fmt_n(h2r)} | {fmt_lift(h2r)} | {fmt_ci(h2r)} |",
        f"| H3 | {fmt_n(h3r)} | {fmt_lift(h3r)} | {fmt_ci(h3r)} |",
        "",
        "---",
        "",
        "## Calibration Controls (4 Total)",
        "",
        "### C1: Within-Ticker Time Permutation (H1/H2, raw basis)",
        "",
        "Shuffles temporal order of whale within each ticker. Appropriate for change tests",
        "(H1/H2) — destroys temporal signal, preserves per-ticker distribution.",
        "",
        "| Test | N events | Lift | 95% CI | Pass? |",
        "|------|----------|------|--------|-------|",
    ])

    c1 = ctrl["c1_within_ticker_time_permutation"]
    for hid, key in [("H1 (permuted)", "h1_neg_ctrl"), ("H2 (permuted)", "h2_neg_ctrl")]:
        r = c1.get(key, {})
        ci = fmt_ci(r)
        passes = "ci95" in r and r["ci95"][0] < 0 < r["ci95"][1]
        lines.append(f"| {hid} | {fmt_n(r)} | {fmt_lift(r)} | {ci} | {'PASS' if passes else 'FAIL'} |")

    lines.extend([
        "",
        "### C2: Within-Month Cross-Ticker Whale Permutation (H3/H4, level tests)",
        "",
        "Shuffles whale values across tickers WITHIN each calendar month. This breaks the",
        "ticker-selection channel for level tests. The prior within-ticker permutation",
        "was structurally powerless for level thresholds: each ticker's whale VALUE",
        "multiset is preserved, so high-whale tickers stay selected under the null,",
        "producing a POSITIVE cross-sectional selection artifact (not null behaviour).",
        "",
        "| Test | N events | Lift | 95% CI | Pass? |",
        "|------|----------|------|--------|-------|",
    ])
    c2 = ctrl["c2_within_month_cross_ticker_permutation"]
    r = c2.get("h3_neg_ctrl_level", {})
    ci = fmt_ci(r)
    passes = "ci95" in r and r["ci95"][0] < 0 < r["ci95"][1]
    lines.append(f"| H3 (cross-ticker permuted) | {fmt_n(r)} | {fmt_lift(r)} | {ci} | {'PASS' if passes else 'FAIL'} |")

    lines.extend([
        "",
        "### C3: Within-Ticker Time Permutation on Demeaned Series (H1/H2, TC basis)",
        "",
        "Validates the time-controlled bootstrap machinery. Permuted whale on demeaned",
        "fwd_1m should produce lifts near zero with CIs spanning zero.",
        "",
        "| Test | N events | Lift | 95% CI | Pass? |",
        "|------|----------|------|--------|-------|",
    ])
    c3 = ctrl["c3_within_ticker_time_permutation_demeaned"]
    for hid, key in [("H1 (demeaned, permuted)", "h1_neg_ctrl_tc"), ("H2 (demeaned, permuted)", "h2_neg_ctrl_tc")]:
        r = c3.get(key, {})
        ci = fmt_ci(r)
        passes = "ci95" in r and r["ci95"][0] < 0 < r["ci95"][1]
        lines.append(f"| {hid} | {fmt_n(r)} | {fmt_lift(r)} | {ci} | {'PASS' if passes else 'FAIL'} |")

    lines.extend([
        "",
        "### C4: Positive Injection (H2, +2pp injected into fwd_1m on H2-mask rows)",
        "",
        "H2 must detect the injected signal (CI excludes zero above).",
        "",
        "| Test | N events | Lift | 95% CI | Pass? |",
        "|------|----------|------|--------|-------|",
    ])
    c4 = ctrl["c4_positive_injection"]
    r = c4.get("h2_pos_ctrl", {})
    ci = fmt_ci(r)
    pc_passes = "ci95" in r and r["ci95"][0] > 0
    lines.append(f"| H2 (+2pp injected) | {fmt_n(r)} | {fmt_lift(r)} | {ci} | {'PASS' if pc_passes else 'FAIL'} |")

    lines.extend([
        "",
        "---",
        "",
        "## Scope Note",
        "",
        "This study covers 2021-07-06 to 2026-07-06 — a predominantly bullish US equity",
        "regime. The effective independent sample is approximately",
        f"{cov['n_calendar_months']} calendar months, not {cov['n_tickers_with_data']} tickers.",
        "",
        "A FAIL here means: **the whale signal does not replicate on a time-controlled",
        "basis within this 5-year bull-market window.**",
        "",
        "It does NOT by itself overturn the 64-year original DannyTrades evidence base.",
        "The original evidence carries its own caveat (survivorship of profitable strategies",
        "over 64 years). See research/DANNYTRADES_PHASE0.md for the original evidence",
        "summary and its scope conditions.",
        "",
        "---",
        "",
    ])

    if desc:
        lines.extend([
            "## Descriptive Companion: Composite-Score Deciles at 63d (PIT-Filtered)",
            "",
            f"**{desc['label']}**",
            "",
            f"N observations (overlapping, PIT-member months only): {desc['n']}  ",
            f"Spearman(decile, mean_fwd_63d): {desc['spearman']}",
            "",
            "| Decile | Mean fwd_63d (%) |",
            "|--------|-----------------|",
        ])
        for i, v in enumerate(desc.get("by_decile_mean_63d", [])):
            lines.append(f"| {i} | {v:+.4f} |")
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.extend([
        "## Implementation Notes",
        "",
        "- **Amendment DT-W1a:** time-control repair applied after Opus adversarial bounce.",
        "  Events/thresholds/universe frozen per prereg §4.1. Only inference machinery changed.",
        "- **Time control:** cross-sectional monthly demeaning removes the calendar-time confound.",
        "  Month-block bootstrap (resample months with replacement) reflects ~60-month effective N.",
        "- **Calendar-continuity guard:** months with any daily gap > 14 calendar days excluded.",
        "- **BH p-values:** exact one-sided bootstrap tail fractions (no CI-ratio approximation).",
        "- **H4:** per-month cross-sectional decile Spearman (mean across months) is primary.",
        "  Verdict by CI from month-block bootstrap on the per-month Spearman series.",
        "  No sp<-0.3 invented threshold.",
        "- **H3/H4 control:** within-month cross-ticker permutation (C2) is the correct null",
        "  for level tests. Within-ticker permutation (C1) is structurally powerless for H3/H4",
        "  because it preserves per-ticker whale value multisets (high-whale tickers stay selected).",
        "- **63d companion:** PIT member filter applied; N is membership-agnostic daily rows",
        "  restricted to member periods.",
        "- **Missing tickers BF-B, BRK-B:** excluded, counted in coverage stamps.",
        "- **Thresholds:** all frozen at prereg values (entering=10, leaving=-10, hot=75,",
        "  win=6, diff=3, BH q=0.10, n_boot=1000, seed=11). Nothing tuned.",
    ])

    out_md.write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------#
# CLI
# ---------------------------------------------------------------------------#

def main() -> int:
    parser = argparse.ArgumentParser(description="DT-W1a whale replication study (time-controlled)")
    parser.add_argument(
        "--store-dir",
        default="/Users/chriswong/Documents/Cluade/Macro Dashboard/data/massive_stock_day",
        help="Path to per-ticker parquet store",
    )
    parser.add_argument(
        "--pit-path",
        default=None,
        help="Path to sp500_pit_membership.parquet (auto-detected if omitted)",
    )
    args = parser.parse_args()

    store_dir = Path(args.store_dir)

    if args.pit_path:
        pit_path = Path(args.pit_path)
    else:
        wt_pit = REPO_ROOT / "data" / "breadth" / "sp500_pit_membership.parquet"
        main_pit = Path("/Users/chriswong/Documents/Cluade/Macro Dashboard/data/breadth/sp500_pit_membership.parquet")
        pit_path = wt_pit if wt_pit.exists() else main_pit

    out_json = REPO_ROOT / "data" / "research" / "dt_w1_replication.json"
    out_md = REPO_ROOT / "research" / "dannytrades" / "DT_W1_RESULTS.md"

    run_study(store_dir, pit_path, out_json, out_md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
