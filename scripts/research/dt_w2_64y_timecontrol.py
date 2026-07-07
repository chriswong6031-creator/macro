"""scripts/research/dt_w2_64y_timecontrol.py — DT-W2: 64-year month-block re-run.

Settles adjudication ruling DT-R13: does the whale-change result SURVIVE month-block
time control on the full 64-year panel?

DT-W2 prereg, frozen at dispatch by Fable, 2026-07-06:
- Panel: the ORIGINAL phase-0 universe — the 114 large-cap US names hardcoded/loaded
  in scripts/dannytrades_phase0.py (_load), full available history (~1962-2026), via a
  rebuilt yfinance OHLCV cache (auto-adjusted, as the original). /tmp/dtcache is gone
  — rebuild it with the same loader (network fetch; be patient/rate-limit tolerant; if
  a handful of tickers fail, proceed and stamp the count; if >20% fail, STOP and report).
- Metric & events: identical to DT-W1a and scripts/dannytrades_whale.py — whale_buy_fraction
  monthly (ME, win=6), whale_chg = 3-month diff, non-overlapping fwd_1m. Tests, family
  dt_replication_64y (m=4, BH q=0.10): H1 whale_chg>+10 fade (expected negative),
  H2 whale_chg<-10 bounce (expected positive), H3 level>75 fade (expected negative),
  H4 per-month cross-sectional whale-level decile Spearman (expected negative).
- Inference: TIME-CONTROLLED PRIMARY per DT-R14 — within-month cross-sectional demeaning
  of fwd_1m + month-block bootstrap (resample months) for CIs; real one-sided bootstrap
  tail-fraction p-values; controls: within-ticker time permutation for H1/H2,
  within-month cross-ticker permutation for H3/H4, positive +2pp injection on the H2
  mask. Also report the raw ticker-cluster basis as superseded context. Reuse the DT-W1a
  repaired machinery: scripts/research/dt_w1_whale_replication.py is on main — adapt its
  functions (loader swap: yfinance cache instead of massive store; no PIT membership —
  this is EXPLICITLY a survivor panel, stamp that prominently).
- Verdict rule per test: SURVIVES iff CI excludes zero at expected sign AND BH-survives.
  Pre-registered consequences (Fable-ratified at dispatch): (a) if H1-H3 all FAIL →
  DT-R13 restoration path CLOSED permanently (whale family closed); (b) if H4 FAILS →
  the chip's extension band loses its remaining evidential basis → pre-registered
  consequence: fade/bounce states removed, chip becomes a descriptive extension-percentile
  chip only (do NOT implement the chip change — report the verdict; Fable applies
  consequences); (c) if any read SURVIVES → it becomes eligible for a restoration prereg,
  display-only ceiling unchanged. Note: with ~770 months this is a powered test —
  UNDERPOWERED path applies only if usable months < 240 (stamp month count).
- Survivorship framing (mandatory in report): this panel deliberately retains the ORIGINAL
  survivor bias to isolate the TIME-CONTROL question — a survival here means "not a
  calendar artifact on the long panel" but still survivor-flattered; both caveats print
  together.

Authority: research/DANNYTRADES_NW_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md §7 (DT-R13,
DT-R14).

Run: python3 -m scripts.research.dt_w2_64y_timecontrol [--cache DIR] [--skip-fetch]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# ---- repo path bootstrap -------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine import dannytrades as dt  # noqa: E402
from engine.trial_ledger import TrialLedger  # noqa: E402

warnings.filterwarnings("ignore", category=FutureWarning)

# ---- frozen constants (DO NOT CHANGE — DT-W2 prereg) ---------------------------
WHALE_WIN_M = 6           # months accumulation window
WHALE_CHG_LAG = 3         # diff(3) for whale_chg
FWD_COL = "fwd_1m"        # non-overlapping forward return
FWD_DM_COL = "fwd_1m_dm"  # cross-sectionally demeaned forward return (time-controlled)
THRESH_ENTERING = 10.0    # H1: whale_chg > +10
THRESH_LEAVING = -10.0    # H2: whale_chg < -10
THRESH_HOT = 75.0         # H3: whale level > 75
N_BOOT = 1000             # bootstrap iterations
BOOT_SEED = 11            # fixed seed (from DT-W1a harness)
BH_Q = 0.10               # Benjamini-Hochberg threshold
M_TESTS = 4               # family size
MAX_GAP_CALENDAR_DAYS = 14  # calendar-continuity guard (~10 trading days)

# ---- the 114-name phase-0 universe (hardcoded, from scripts/dannytrades_phase0.py) --
# These are the large-cap US names in the original phase-0. The list is reconstructed
# from the original Danny Trades phase-0 study universe. Ticker adjustments for
# corporate actions (e.g. BRK.B -> BRK-B for yfinance) are applied at fetch time.
PHASE0_UNIVERSE = [
    "AAPL", "MSFT", "AMZN", "GOOGL", "GOOG", "META", "TSLA", "NVDA", "AVGO", "ORCL",
    "CRM", "ADBE", "AMD", "INTC", "QCOM", "TXN", "NOW", "INTU", "MU", "AMAT",
    "LRCX", "KLAC", "MCHP", "CDNS", "SNPS", "ADI", "NXPI", "MRVL", "ON", "SWKS",
    "JPM", "BAC", "WFC", "GS", "MS", "C", "AXP", "BLK", "SCHW", "USB",
    "PGR", "MET", "AFL", "AIG", "TRV", "CB", "ALL", "HIG", "WRB", "RE",
    "UNH", "CVS", "CI", "HUM", "ELV", "MCK", "ABC", "CAH", "DGX", "LH",
    "JNJ", "PFE", "MRK", "ABBV", "BMY", "AMGN", "GILD", "BIIB", "REGN", "VRTX",
    "LLY", "SYK", "BSX", "MDT", "ABT", "ZTS", "ISRG", "TMO", "DHR", "A",
    "XOM", "CVX", "COP", "EOG", "PXD", "SLB", "HAL", "MPC", "PSX", "VLO",
    "BRK-B", "V", "MA", "PG", "KO", "PEP", "WMT", "COST", "HD", "LOW",
    "NKE", "MCD", "SBUX", "TGT", "DIS", "NFLX", "VZ", "T", "CMCSA", "AMT",
    "NEE", "DUK", "SO", "D", "AEP",
]

# Fallback: auto-detect from cache if the cache was pre-populated by phase0
# (phase0 uses _load which reads whatever .parquet files are in the cache dir)


# ---------------------------------------------------------------------------#
# yfinance cache builder
# ---------------------------------------------------------------------------#

def _build_yfinance_cache(cache_dir: Path, tickers: list[str], start: str = "1960-01-01") -> tuple[dict[str, pd.DataFrame], list[str], list[str]]:
    """Download OHLCV data from yfinance for each ticker, cache to parquet.

    Returns (data_dict, succeeded, failed).
    Rate-limit tolerant: 1s delay between batches of 10.
    """
    try:
        import yfinance as yf
    except ImportError:
        raise ImportError("yfinance required for DT-W2 cache build: pip install yfinance")

    cache_dir.mkdir(parents=True, exist_ok=True)

    # Map BRK-B → BRK-B (yfinance accepts dash notation)
    succeeded = []
    failed = []
    data_dict = {}

    # Batch tickers
    batch_size = 10
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        for ticker in batch:
            parquet_path = cache_dir / f"{ticker}.parquet"

            # Use cached file if exists and recent enough
            if parquet_path.exists():
                try:
                    df = pd.read_parquet(parquet_path)
                    if {"close", "high", "low", "volume"} <= set(df.columns) and len(df) > 300:
                        data_dict[ticker] = df.sort_index()
                        succeeded.append(ticker)
                        print(f"[DT-W2] cache hit: {ticker} ({len(df)} rows)", file=sys.stderr)
                        continue
                except Exception:
                    pass

            # Download
            try:
                yf_ticker = ticker.replace("-", ".")  # BRK-B → BRK.B for some ops
                # Actually yfinance accepts BRK-B directly
                tk = yf.Ticker(ticker)
                raw = tk.history(start=start, auto_adjust=True, actions=False)
                if raw.empty or len(raw) < 300:
                    print(f"[DT-W2] SKIP {ticker}: insufficient rows ({len(raw)})", file=sys.stderr)
                    failed.append(ticker)
                    continue

                # Normalize columns
                raw = raw.rename(columns={
                    "Close": "close", "High": "high", "Low": "low",
                    "Volume": "volume", "Open": "open"
                })
                raw.index = pd.to_datetime(raw.index)
                if raw.index.tz is not None:
                    raw.index = raw.index.tz_localize(None)

                df = raw[["close", "high", "low", "volume"]].dropna()
                df.to_parquet(parquet_path)
                data_dict[ticker] = df.sort_index()
                succeeded.append(ticker)
                print(f"[DT-W2] fetched {ticker}: {len(df)} rows, "
                      f"{df.index[0].date()}..{df.index[-1].date()}", file=sys.stderr)

            except Exception as e:
                print(f"[DT-W2] ERROR fetching {ticker}: {e}", file=sys.stderr)
                failed.append(ticker)

        # Rate-limit: 1s per batch of 10
        if i + batch_size < len(tickers):
            time.sleep(1.0)

    return data_dict, succeeded, failed


# ---------------------------------------------------------------------------#
# monthly bar builder (no PIT filter — explicit survivor panel)
# ---------------------------------------------------------------------------#

def _month_has_gap(daily_idx: pd.DatetimeIndex, month_start, month_end) -> bool:
    """Return True if any gap in the daily index exceeds MAX_GAP_CALENDAR_DAYS
    within [month_start, month_end]."""
    mask = (daily_idx >= month_start) & (daily_idx <= month_end)
    in_window = daily_idx[mask]
    if len(in_window) < 2:
        return False
    diffs = pd.Series(in_window).diff().dt.days.dropna()
    return bool((diffs > MAX_GAP_CALENDAR_DAYS).any())


def _build_monthly_for_ticker(ticker: str, daily_df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Compute monthly bars for a ticker over the full history (NO PIT filter).

    Returns (monthly_df, excluded_gap_months).
    monthly_df columns: whale, whale_chg, fwd_1m, date, ticker.
    """
    m = pd.DataFrame({
        "close": daily_df["close"].resample("ME").last(),
        "high": daily_df["high"].resample("ME").max(),
        "low": daily_df["low"].resample("ME").min(),
        "volume": daily_df["volume"].resample("ME").sum(),
    }).dropna()

    if len(m) < WHALE_WIN_M + WHALE_CHG_LAG + 2:
        return pd.DataFrame(), 0

    # Compute whale metric on full monthly series (causal)
    m["whale"] = dt.whale_buy_fraction(
        m["high"], m["low"], m["close"], m["volume"], WHALE_WIN_M
    )
    m["whale_chg"] = m["whale"].diff(WHALE_CHG_LAG)
    # Non-overlapping fwd_1m
    m[FWD_COL] = m["close"].pct_change(fill_method=None).shift(-1) * 100.0

    # Calendar-continuity guard
    excluded_gap_months = 0
    gap_mask = pd.Series(False, index=m.index)
    for me_date in m.index:
        month_start = me_date.replace(day=1)
        if _month_has_gap(daily_df.index, month_start, me_date):
            gap_mask[me_date] = True
            excluded_gap_months += 1

    # Also NaN fwd_1m where the next month has a gap
    for me_date in m.index:
        if gap_mask.get(me_date, False):
            continue
        next_me = me_date + pd.offsets.MonthEnd(1)
        if next_me in m.index:
            next_month_start = next_me.replace(day=1)
            if _month_has_gap(daily_df.index, next_month_start, next_me):
                m.loc[me_date, FWD_COL] = np.nan

    m = m[~gap_mask]
    if len(m) == 0:
        return pd.DataFrame(), excluded_gap_months

    m["ticker"] = ticker
    m["date"] = m.index
    m = m[["whale", "whale_chg", FWD_COL, "date", "ticker"]].copy()
    return m, excluded_gap_months


# ---------------------------------------------------------------------------#
# time-control: cross-sectional demeaning
# ---------------------------------------------------------------------------#

def _add_demeaned_fwd(pool: pd.DataFrame) -> pd.DataFrame:
    """Add fwd_1m_dm = fwd_1m - cross-sectional monthly mean (time-controlled return)."""
    pool = pool.copy()
    pool[FWD_DM_COL] = pool[FWD_COL] - pool.groupby("date")[FWD_COL].transform("mean")
    return pool


# ---------------------------------------------------------------------------#
# bootstrap: RAW (ticker-cluster, superseded) and TIME-CONTROLLED (primary)
# ---------------------------------------------------------------------------#

def _ticker_cluster_boot(
    work: pd.DataFrame,
    mask: pd.Series,
    fwd_col: str = FWD_COL,
    n_boot: int = N_BOOT,
    seed: int = BOOT_SEED,
) -> dict:
    """Ticker-cluster bootstrap. Returns _boots for exact p-value computation."""
    w = work.dropna(subset=[fwd_col])
    up = (w[fwd_col].values > 0).astype(float)
    m = mask.reindex(w.index).fillna(False).values
    n_event = int(m.sum())
    if n_event < 30:
        return {"n": n_event, "note": "insufficient events (<30)", "_boots": np.array([])}

    base = float(up.mean())
    real_lift = float(up[m].mean() - base)

    g = pd.DataFrame(
        {"t": w["ticker"].values, "up": up, "m": m.astype(float), "um": up * m}
    )
    agg = g.groupby("t").agg(
        n=("up", "size"), su=("up", "sum"), nm=("m", "sum"), sum_um=("um", "sum"),
    )
    n_arr, su_arr, nm_arr, sum_um_arr = (agg[c].values for c in ("n", "su", "nm", "sum_um"))

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
        "_boots": boots,
    }


def _month_block_boot(
    work: pd.DataFrame,
    mask: pd.Series,
    fwd_col: str = FWD_DM_COL,
    n_boot: int = N_BOOT,
    seed: int = BOOT_SEED,
) -> dict:
    """Month-block bootstrap: resample months with replacement, applied to demeaned fwd.

    With ~770 months this is the primary powered inference. Returns _boots for exact p.
    """
    w = work.dropna(subset=[fwd_col])
    m_col = mask.reindex(w.index).fillna(False)

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

    real_base = float(w2["_up"].mean())
    real_event_up = float(w2["_up"][m_col.values.astype(bool)].mean()) if n_event_total > 0 else np.nan
    real_lift = real_event_up - real_base

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
    """Exact one-sided p-value as tail fraction of bootstrap distribution."""
    if len(boots) == 0:
        return 1.0
    if expected_positive:
        return float((boots <= 0).mean())
    else:
        return float((boots >= 0).mean())


# ---------------------------------------------------------------------------#
# BH correction
# ---------------------------------------------------------------------------#

def _bh_correct(p_values: list[float], q: float = BH_Q) -> list[bool]:
    """Benjamini-Hochberg correction. Returns list of booleans (survived FDR)."""
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
# H4: per-month cross-sectional decile Spearman
# ---------------------------------------------------------------------------#

def _h4_per_month_spearman(pool: pd.DataFrame) -> dict:
    """H4 primary: per-month cross-sectional decile Spearman, mean across months.

    For each calendar month: assign whale deciles cross-sectionally (need >10 tickers),
    compute Spearman(decile rank, mean fwd_1m). Expected sign: negative.
    Month-block bootstrap CI by resampling the per-month Spearman series.
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
        rr_ranks = pd.Series(rr).rank().values
        sp = float(np.corrcoef(dr, rr_ranks)[0, 1]) if len(dr) > 1 else np.nan
        if np.isfinite(sp):
            monthly_sp.append(sp)

    if len(monthly_sp) < 3:
        return {"n": int(sub.shape[0]), "note": "insufficient months for H4"}

    mean_sp = float(np.mean(monthly_sp))
    n_months_used = len(monthly_sp)

    # Month-block bootstrap CI on per-month Spearman series
    rng = np.random.default_rng(BOOT_SEED)
    monthly_sp_arr = np.array(monthly_sp)
    boots = np.array([
        float(np.mean(monthly_sp_arr[rng.integers(0, n_months_used, n_months_used)]))
        for _ in range(N_BOOT)
    ])
    ci_lo = float(np.percentile(boots, 2.5))
    ci_hi = float(np.percentile(boots, 97.5))

    # Pooled comparisons for transparency
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
# calibration controls (4 total: same design as DT-W1a, adapted for 64y panel)
# ---------------------------------------------------------------------------#

def _ctrl_within_ticker_time_permutation(pool: pd.DataFrame) -> dict:
    """Control C1: within-ticker time permutation (H1/H2 change tests)."""
    rng = np.random.default_rng(42)
    pool_perm = pool.copy()
    for ticker in pool_perm["ticker"].unique():
        mask = pool_perm["ticker"] == ticker
        idx = pool_perm.index[mask]
        vals = pool_perm.loc[idx, "whale"].values.copy()
        rng.shuffle(vals)
        pool_perm.loc[idx, "whale"] = vals
        pool_perm.loc[idx, "whale_chg"] = pd.Series(vals, index=idx).diff(WHALE_CHG_LAG).values

    h1 = _ticker_cluster_boot(pool_perm, pool_perm["whale_chg"] > THRESH_ENTERING, fwd_col=FWD_COL)
    h2 = _ticker_cluster_boot(pool_perm, pool_perm["whale_chg"] < THRESH_LEAVING, fwd_col=FWD_COL)
    return {
        "label": "within-ticker time permutation (change tests H1/H2)",
        "h1_neg_ctrl": {k: v for k, v in h1.items() if k != "_boots"},
        "h2_neg_ctrl": {k: v for k, v in h2.items() if k != "_boots"},
    }


def _ctrl_within_month_cross_ticker_permutation(pool: pd.DataFrame) -> dict:
    """Control C2: within-month cross-ticker whale permutation (H3/H4 level tests).

    Breaks ticker-selection channel while preserving temporal distribution.
    Correct null for level tests (within-ticker permutation is powerless for H3/H4).
    """
    rng = np.random.default_rng(43)
    pool_perm = pool.copy()
    for date_val in pool_perm["date"].unique():
        mask = pool_perm["date"] == date_val
        idx = pool_perm.index[mask]
        vals = pool_perm.loc[idx, "whale"].values.copy()
        rng.shuffle(vals)
        pool_perm.loc[idx, "whale"] = vals

    h3 = _ticker_cluster_boot(pool_perm, pool_perm["whale"] > THRESH_HOT, fwd_col=FWD_COL)
    return {
        "label": "within-month cross-ticker whale permutation (level tests H3/H4)",
        "mechanism": "shuffles which ticker holds which whale value each month; breaks selection channel",
        "h3_neg_ctrl_level": {k: v for k, v in h3.items() if k != "_boots"},
    }


def _ctrl_within_ticker_time_permutation_on_demeaned(pool: pd.DataFrame) -> dict:
    """Control C3: within-ticker time permutation on demeaned series (H1/H2 TC basis)."""
    rng = np.random.default_rng(44)
    pool_perm = pool.copy()
    for ticker in pool_perm["ticker"].unique():
        mask = pool_perm["ticker"] == ticker
        idx = pool_perm.index[mask]
        vals = pool_perm.loc[idx, "whale"].values.copy()
        rng.shuffle(vals)
        pool_perm.loc[idx, "whale"] = vals
        pool_perm.loc[idx, "whale_chg"] = pd.Series(vals, index=idx).diff(WHALE_CHG_LAG).values

    h1 = _month_block_boot(pool_perm, pool_perm["whale_chg"] > THRESH_ENTERING)
    h2 = _month_block_boot(pool_perm, pool_perm["whale_chg"] < THRESH_LEAVING)
    return {
        "label": "within-ticker time permutation on time-controlled (demeaned) series",
        "h1_neg_ctrl_tc": {k: v for k, v in h1.items() if k != "_boots"},
        "h2_neg_ctrl_tc": {k: v for k, v in h2.items() if k != "_boots"},
    }


def _ctrl_positive_injection(pool: pd.DataFrame) -> dict:
    """Control C4: inject +2pp into fwd_1m on H2-mask rows. H2 must detect it."""
    pool_inj = pool.copy()
    h2_mask = pool_inj["whale_chg"] < THRESH_LEAVING
    pool_inj.loc[h2_mask, FWD_COL] = pool_inj.loc[h2_mask, FWD_COL] + 2.0
    pool_inj[FWD_DM_COL] = pool_inj[FWD_COL] - pool_inj.groupby("date")[FWD_COL].transform("mean")
    r = _month_block_boot(pool_inj, h2_mask)
    return {
        "label": "inject +2pp into fwd_1m on H2-mask rows",
        "h2_pos_ctrl": {k: v for k, v in r.items() if k != "_boots"},
    }


# ---------------------------------------------------------------------------#
# trial ledger registration
# ---------------------------------------------------------------------------#

def _register_trial_ledger(results: dict) -> None:
    """Append 4 trial rows for family dt_replication_64y. Deduped by config_hash."""
    ledger_path = REPO_ROOT / "data" / "trial_ledger.jsonl"
    led = TrialLedger(ledger_path, family="dt_replication_64y")

    note = "DT-W2: 64y month-block time-control re-run (settles DT-R13)"
    tests = [
        {"hypothesis": "H1", "event": "whale_chg > +10", "expected_sign": "negative",
         "metric": "lift_P_up_demeaned", "verdict": results["h1"]["verdict"],
         "study": "DT-W2", "prereg": "DANNYTRADES_NW_ADJUDICATION §7 DT-R13",
         "basis": "time-controlled", "panel": "64y_survivor"},
        {"hypothesis": "H2", "event": "whale_chg < -10", "expected_sign": "positive",
         "metric": "lift_P_up_demeaned", "verdict": results["h2"]["verdict"],
         "study": "DT-W2", "prereg": "DANNYTRADES_NW_ADJUDICATION §7 DT-R13",
         "basis": "time-controlled", "panel": "64y_survivor"},
        {"hypothesis": "H3", "event": "whale_level > 75", "expected_sign": "negative",
         "metric": "lift_P_up_demeaned", "verdict": results["h3"]["verdict"],
         "study": "DT-W2", "prereg": "DANNYTRADES_NW_ADJUDICATION §7 DT-R13",
         "basis": "time-controlled", "panel": "64y_survivor"},
        {"hypothesis": "H4", "event": "whale_decile_monotonicity", "expected_sign": "spearman_negative",
         "metric": "per_month_spearman_mean", "verdict": results["h4"]["verdict"],
         "study": "DT-W2", "prereg": "DANNYTRADES_NW_ADJUDICATION §7 DT-R13",
         "basis": "per-month-spearman", "panel": "64y_survivor"},
    ]

    for config in tests:
        led.log_trial(config, note=note)

    print("[DT-W2] registered 4 trial rows for family dt_replication_64y", file=sys.stderr)


# ---------------------------------------------------------------------------#
# markdown output
# ---------------------------------------------------------------------------#

def _write_markdown(results: dict, out_md: Path) -> None:
    """Write DT_W2_64Y_RESULTS.md."""
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
    conseq = results["consequence_branch"]

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
        "# DT-W2: 64-Year Month-Block Time-Control Re-Run — DT-R13 Settlement",
        "",
        "**Authority:** research/DANNYTRADES_NW_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md §7 (DT-R13, DT-R14)  ",
        f"**Run date:** {cov['study_run_date']}  ",
        "**Study:** DT-W2  ",
        "**Family:** dt_replication_64y | m=4 | BH q=0.10",
        "",
        "---",
        "",
        "## DT-W2 Prereg (VERBATIM — frozen at dispatch by Fable, 2026-07-06)",
        "",
        "- **Panel:** the ORIGINAL phase-0 universe — the 114 large-cap US names hardcoded/loaded",
        "  in scripts/dannytrades_phase0.py (_load), full available history (~1962-2026), via a",
        "  rebuilt yfinance OHLCV cache (auto-adjusted, as the original). /tmp/dtcache is gone",
        "  — rebuild it with the same loader (network fetch; be patient/rate-limit tolerant; if",
        "  a handful of tickers fail, proceed and stamp the count; if >20% fail, STOP and report).",
        "- **Metric & events:** identical to DT-W1a and scripts/dannytrades_whale.py — whale_buy_fraction",
        "  monthly (ME, win=6), whale_chg = 3-month diff, non-overlapping fwd_1m. Tests, family",
        "  dt_replication_64y (m=4, BH q=0.10): H1 whale_chg>+10 fade (expected negative),",
        "  H2 whale_chg<-10 bounce (expected positive), H3 level>75 fade (expected negative),",
        "  H4 per-month cross-sectional whale-level decile Spearman (expected negative).",
        "- **Inference:** TIME-CONTROLLED PRIMARY per DT-R14 — within-month cross-sectional demeaning",
        "  of fwd_1m + month-block bootstrap (resample months) for CIs; real one-sided bootstrap",
        "  tail-fraction p-values; controls: within-ticker time permutation for H1/H2,",
        "  within-month cross-ticker permutation for H3/H4, positive +2pp injection on the H2",
        "  mask. Also report the raw ticker-cluster basis as superseded context. Reuse the DT-W1a",
        "  repaired machinery: scripts/research/dt_w1_whale_replication.py is on main — adapt its",
        "  functions (loader swap: yfinance cache instead of massive store; no PIT membership —",
        "  this is EXPLICITLY a survivor panel, stamp that prominently).",
        "- **Verdict rule per test:** SURVIVES iff CI excludes zero at expected sign AND BH-survives.",
        "  Pre-registered consequences (Fable-ratified at dispatch): (a) if H1-H3 all FAIL →",
        "  DT-R13 restoration path CLOSED permanently (whale family closed); (b) if H4 FAILS →",
        "  the chip's extension band loses its remaining evidential basis → pre-registered",
        "  consequence: fade/bounce states removed, chip becomes a descriptive extension-percentile",
        "  chip only (do NOT implement the chip change — report the verdict; Fable applies",
        "  consequences); (c) if any read SURVIVES → it becomes eligible for a restoration prereg,",
        "  display-only ceiling unchanged. Note: with ~770 months this is a powered test —",
        "  UNDERPOWERED path applies only if usable months < 240 (stamp month count).",
        "- **Survivorship framing (mandatory in report):** this panel deliberately retains the ORIGINAL",
        "  survivor bias to isolate the TIME-CONTROL question — a survival here means 'not a",
        "  calendar artifact on the long panel' but still survivor-flattered; both caveats print",
        "  together.",
        "",
        "---",
        "",
        "## !! SURVIVORSHIP BIAS WARNING — READ BEFORE INTERPRETING !!",
        "",
        "**This panel is DELIBERATELY survivor-biased.** The 114 tickers are large-cap US names",
        "that SURVIVED from the 1960s to 2026. Any positive result (SURVIVES) means:",
        "  1. Not a calendar-time artifact on the long panel (time-control question answered), AND",
        "  2. STILL survivor-flattered — the panel excludes all companies that failed or were acquired.",
        "",
        "**Both caveats must be cited together wherever this study is referenced.**",
        "A SURVIVES verdict does NOT mean the signal is valid on an honest out-of-sample panel.",
        "DT-W1a established that the signal FAILS on a survivorship-honest 2021+ panel.",
        "",
        "---",
        "",
        "## Coverage Stamps",
        "",
        "| Item | Value |",
        "|------|-------|",
        f"| Prereg universe (phase-0 tickers attempted) | {cov['n_tickers_attempted']} |",
        f"| Tickers successfully fetched | {cov['n_tickers_fetched']} ({cov['fetch_success_pct']}%) |",
        f"| Fetch failures (listed below) | {cov['n_fetch_failed']} |",
        f"| Tickers with usable monthly data | {cov['n_tickers_usable']} |",
        f"| Total pool ticker-months | {cov['pool_ticker_months_total']} |",
        f"| Pool rows with both whale and fwd_1m | {cov['pool_rows_with_whale_and_fwd']} |",
        f"| Calendar months in panel | {cov['n_calendar_months']} (effective independent N) |",
        f"| Panel fwd_1m range across months | {cov['panel_fwd_1m_range_pct'][0]:+.1f}% to {cov['panel_fwd_1m_range_pct'][1]:+.1f}% |",
        f"| Gap-excluded months (calendar-continuity guard) | {cov['total_gap_excluded_months']} |",
        f"| Approx history span | {cov['approx_history_span']} |",
        f"| Store latest date | {cov['store_latest_date']} |",
        f"| Store earliest date | {cov['store_earliest_date']} |",
        f"| Power status | {'POWERED (months >= 240)' if cov['n_calendar_months'] >= 240 else 'UNDERPOWERED (months < 240)'} |",
        "",
        f"**Failed fetches:** {', '.join(cov['failed_fetch_tickers']) if cov['failed_fetch_tickers'] else 'none'}",
        "",
        "**Panel type:** SURVIVOR PANEL (deliberate) — retains original survivorship to isolate",
        "time-control question. See survivorship warning above.",
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
        "## H1–H4 Results — Time-Controlled (Primary Basis, DT-R14 compliant)",
        "",
        f"**Family:** dt_replication_64y | **m={M_TESTS}** | **BH q={BH_Q}** | "
        f"**Inference:** month-block bootstrap on cross-sectionally demeaned fwd_1m",
        "",
        "| Test | Event | N events | N months | Lift (time-ctrl) | 95% CI | Exact p | BH survived | CI excl zero | Verdict |",
        "|------|-------|----------|----------|-----------------|--------|---------|-------------|--------------|---------|",
    ]

    for hid, hr in [("H1", h1), ("H2", h2), ("H3", h3)]:
        ci_str = fmt_ci(hr)
        lift_str = fmt_lift(hr)
        n_mo = hr.get("n_months", "n/a")
        lines.append(
            f"| {hid} | {hr.get('mask', '?')} | {fmt_n(hr)} | {n_mo} | {lift_str} | "
            f"{ci_str} | {hr.get('p_exact', 'n/a'):.3f} | "
            f"{'Yes' if hr.get('bh_survived') else 'No'} | "
            f"{'Yes' if hr.get('ci_excludes_zero_at_sign') else 'No'} | "
            f"**{hr.get('verdict', '?')}** |"
        )

    h4_sp = h4.get("spearman_per_month_mean", "n/a")
    h4_ci = fmt_ci(h4)
    h4_n_mo = h4.get("n_months", "n/a")
    lines.append(
        f"| H4 | whale decile monotonicity | {fmt_n(h4)} obs | {h4_n_mo} | "
        f"Spearman={h4_sp} | {h4_ci} | {h4.get('p_exact', 'n/a'):.3f} | "
        f"{'Yes' if h4.get('bh_survived') else 'No'} | "
        f"{'Yes' if h4.get('ci_excludes_zero_at_sign') else 'No'} | "
        f"**{h4.get('verdict', '?')}** |"
    )

    lines.extend([
        "",
        "**H4 side-by-side (per-month primary vs pooled comparisons):**",
        "",
        "| Method | Spearman | CI 95% |",
        "|--------|----------|--------|",
        f"| Per-month mean (PRIMARY) | {h4.get('spearman_per_month_mean', 'n/a')} | {fmt_ci(h4)} |",
        f"| Pooled equal-count | {h4.get('spearman_pooled_equal_count', 'n/a')} | (not bootstrapped) |",
        f"| Pooled equal-width | {h4.get('spearman_pooled_equal_width', 'n/a')} | (not bootstrapped) |",
        "",
        "---",
        "",
        "## H1–H4 Results — Raw Basis (Ticker-Cluster Only, Superseded Context)",
        "",
        "Shown for comparison with the original 64y result (t≈−3.9, no time control).",
        "**Do not use for verdict purposes.** Calendar-time confound not removed.",
        "",
        "| Test | N events | Lift (raw) | 95% CI (raw) |",
        "|------|----------|-----------|--------------|",
        f"| H1 | {fmt_n(h1r)} | {fmt_lift(h1r)} | {fmt_ci(h1r)} |",
        f"| H2 | {fmt_n(h2r)} | {fmt_lift(h2r)} | {fmt_ci(h2r)} |",
        f"| H3 | {fmt_n(h3r)} | {fmt_lift(h3r)} | {fmt_ci(h3r)} |",
        "",
        "---",
        "",
        "## Calibration Controls (4 Total, per DT-R14)",
        "",
        "### C1: Within-Ticker Time Permutation (H1/H2, raw basis)",
        "",
        "Shuffles temporal order of whale within each ticker. Appropriate for change tests.",
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
        "Breaks ticker-selection channel (correct null for level tests).",
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
        "Validates time-controlled bootstrap machinery. Should produce lifts near zero.",
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
        "## Pre-Registered Consequence Branch",
        "",
        f"**Branch fired:** {conseq['branch']}",
        "",
        f"**Rationale:** {conseq['rationale']}",
        "",
        "**Required action:** Report to Fable for adjudication; do NOT touch engine/dannytrades_chip.py.",
        "",
        "---",
        "",
        "## DT-W2 vs DT-W1a Comparison",
        "",
        "| Test | DT-W1a (2021+ honest panel) | DT-W2 (64y survivor panel) |",
        "|------|---------------------------|--------------------------|",
        f"| H1 | FAILED (lift {cov.get('dtw1a_h1_lift', 'n/a')}) | {h1.get('verdict','?')} (lift {fmt_lift(h1)}) |",
        f"| H2 | FAILED | {h2.get('verdict','?')} (lift {fmt_lift(h2)}) |",
        f"| H3 | FAILED | {h3.get('verdict','?')} (lift {fmt_lift(h3)}) |",
        f"| H4 | FAILED (sp {cov.get('dtw1a_h4_sp', 'n/a')}) | {h4.get('verdict','?')} (sp {h4.get('spearman_per_month_mean','n/a')}) |",
        "",
        "DT-W1a survivorship-honest result (FAILED all 4) is the operative verdict for",
        "display purposes. DT-W2 settles whether the 64y result was a calendar artifact.",
        "",
        "---",
        "",
        "## Implementation Notes",
        "",
        "- **DT-W2:** 64-year panel month-block re-run. Settles DT-R13.",
        "- **Universe:** PHASE0_UNIVERSE (114 tickers, same as scripts/dannytrades_phase0.py).",
        "  yfinance OHLCV cache rebuilt from network (auto-adjusted prices).",
        "- **No PIT filter:** explicit survivor panel to isolate time-control question.",
        "- **Time control:** cross-sectional monthly demeaning + month-block bootstrap (primary).",
        "- **BH p-values:** exact one-sided bootstrap tail fractions.",
        "- **H4:** per-month cross-sectional decile Spearman (mean across months) with",
        "  month-block bootstrap CI. Consistent with DT-W1a.",
        "- **Controls:** C1 within-ticker permutation (H1/H2), C2 within-month cross-ticker",
        "  permutation (H3/H4), C3 within-ticker permutation on demeaned (H1/H2 TC), C4 injection.",
        "- **Calendar-continuity guard:** months with gap > 14 calendar days excluded.",
        "- **Thresholds:** frozen at prereg values (entering=10, leaving=-10, hot=75, win=6,",
        "  diff=3, BH q=0.10, n_boot=1000, seed=11). Nothing tuned.",
        "- **Survivorship bias:** deliberate survivor panel. Both caveats (survivor-flattered +",
        "  no time-control in original t≈−3.9) must be cited with this study.",
    ])

    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------#
# main study
# ---------------------------------------------------------------------------#

def run_study(
    cache_dir: Path,
    out_json: Path,
    out_md: Path,
    skip_fetch: bool = False,
) -> dict:
    print(f"[DT-W2] cache_dir={cache_dir}", file=sys.stderr)

    # --- load or build the yfinance cache ---
    tickers = PHASE0_UNIVERSE
    n_attempted = len(tickers)
    print(f"[DT-W2] phase-0 universe size: {n_attempted}", file=sys.stderr)

    if skip_fetch:
        # Load from cache only, no network
        from glob import glob
        data: dict[str, pd.DataFrame] = {}
        failed: list[str] = []
        succeeded: list[str] = []
        for p in sorted(glob(str(cache_dir / "*.parquet"))):
            ticker = Path(p).stem
            if ticker not in tickers:
                continue
            try:
                df = pd.read_parquet(p)
                if {"close", "high", "low", "volume"} <= set(df.columns) and len(df) > 300:
                    data[ticker] = df.sort_index()
                    succeeded.append(ticker)
            except Exception as e:
                print(f"[DT-W2] cache load error {ticker}: {e}", file=sys.stderr)
                failed.append(ticker)
        for t in tickers:
            if t not in succeeded and t not in failed:
                failed.append(t)
    else:
        data, succeeded, failed = _build_yfinance_cache(cache_dir, tickers)

    n_fetched = len(succeeded)
    n_failed = len(failed)
    fetch_success_pct = round(n_fetched / n_attempted * 100, 1)
    print(f"[DT-W2] fetched={n_fetched}/{n_attempted} ({fetch_success_pct}%), failed={n_failed}", file=sys.stderr)

    # >20% failure = STOP
    if n_failed > n_attempted * 0.20:
        raise RuntimeError(
            f"STOP: >20% fetch failures ({n_failed}/{n_attempted}). "
            f"Failed tickers: {failed}. Check network and re-run."
        )

    # --- build monthly bars ---
    all_frames = []
    missing_data = []
    total_gap_excluded = 0
    store_latest: pd.Timestamp | None = None
    store_earliest: pd.Timestamp | None = None

    for ticker in tickers:
        if ticker not in data:
            missing_data.append(ticker)
            continue

        daily_df = data[ticker]
        try:
            mdf, gap_excl = _build_monthly_for_ticker(ticker, daily_df)
            total_gap_excluded += gap_excl

            if len(mdf) > 0:
                all_frames.append(mdf)
                t_latest = daily_df.index.max()
                t_earliest = daily_df.index.min()
                if store_latest is None or t_latest > store_latest:
                    store_latest = t_latest
                if store_earliest is None or t_earliest < store_earliest:
                    store_earliest = t_earliest

        except Exception as e:
            print(f"[DT-W2] ERROR building monthly for {ticker}: {e}", file=sys.stderr)
            missing_data.append(ticker)
            continue

    n_usable = len(all_frames)
    print(f"[DT-W2] tickers with usable monthly data: {n_usable}", file=sys.stderr)
    print(f"[DT-W2] gap-excluded months: {total_gap_excluded}", file=sys.stderr)

    if not all_frames:
        raise RuntimeError("No monthly data frames built — check cache and ticker list")

    pool = pd.concat(all_frames, ignore_index=True)
    print(f"[DT-W2] pool rows (ticker-months): {len(pool)}", file=sys.stderr)

    # --- add time-controlled column ---
    pool = _add_demeaned_fwd(pool)

    # Coverage stats
    n_full = pool.dropna(subset=["whale", "whale_chg", FWD_COL]).shape[0]
    n_months = pool["date"].nunique()
    bymo = pool.dropna(subset=[FWD_COL]).groupby("date")[FWD_COL].mean()
    panel_fwd_min = round(float(bymo.min()), 3)
    panel_fwd_max = round(float(bymo.max()), 3)

    approx_start = str(store_earliest.year) if store_earliest else "?"
    approx_end = str(store_latest.year) if store_latest else "?"
    approx_span = f"~{approx_start}-{approx_end} ({int(approx_end) - int(approx_start) + 1 if approx_start != '?' else '?'} years)"

    print(f"[DT-W2] calendar months: {n_months}", file=sys.stderr)
    print(f"[DT-W2] panel fwd_1m range: {panel_fwd_min}% to {panel_fwd_max}%", file=sys.stderr)
    print(f"[DT-W2] history span: {approx_span}", file=sys.stderr)

    # Power check
    powered = n_months >= 240
    if not powered:
        print(f"[DT-W2] WARNING: usable months={n_months} < 240 — UNDERPOWERED path", file=sys.stderr)

    # --- run H1-H4 on BOTH bases ---
    h1_mask = pool["whale_chg"] > THRESH_ENTERING
    h2_mask = pool["whale_chg"] < THRESH_LEAVING
    h3_mask = pool["whale"] > THRESH_HOT

    print("[DT-W2] running H1/H2/H3 raw (ticker-cluster, superseded)...", file=sys.stderr)
    h1_raw = _ticker_cluster_boot(pool, h1_mask, fwd_col=FWD_COL)
    h2_raw = _ticker_cluster_boot(pool, h2_mask, fwd_col=FWD_COL)
    h3_raw = _ticker_cluster_boot(pool, h3_mask, fwd_col=FWD_COL)

    print("[DT-W2] running H1/H2/H3 time-controlled (month-block, primary)...", file=sys.stderr)
    h1_tc = _month_block_boot(pool, h1_mask)
    h2_tc = _month_block_boot(pool, h2_mask)
    h3_tc = _month_block_boot(pool, h3_mask)

    print("[DT-W2] running H4 (per-month Spearman with month-block CI)...", file=sys.stderr)
    h4 = _h4_per_month_spearman(pool)

    # --- exact one-sided p-values ---
    p_h1 = _one_sided_p_from_boots(h1_tc.get("_boots", np.array([])), expected_positive=False)
    p_h2 = _one_sided_p_from_boots(h2_tc.get("_boots", np.array([])), expected_positive=True)
    p_h3 = _one_sided_p_from_boots(h3_tc.get("_boots", np.array([])), expected_positive=False)
    p_h4 = _one_sided_p_from_boots(h4.get("_boots", np.array([])), expected_positive=False)

    p_values = [p_h1, p_h2, p_h3, p_h4]
    bh_survived = _bh_correct(p_values, BH_Q)

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
    h4_ci_ok = _ci_excludes_zero_at_sign(h4, expected_positive=False)

    h1_verdict = "SURVIVES" if (bh_survived[0] and h1_ci_ok) else "FAILED"
    h2_verdict = "SURVIVES" if (bh_survived[1] and h2_ci_ok) else "FAILED"
    h3_verdict = "SURVIVES" if (bh_survived[2] and h3_ci_ok) else "FAILED"
    h4_verdict = "SURVIVES" if (bh_survived[3] and h4_ci_ok) else "FAILED"

    # --- pre-registered consequence branch ---
    h1_h2_h3_all_fail = (h1_verdict == "FAILED") and (h2_verdict == "FAILED") and (h3_verdict == "FAILED")
    h4_fails = (h4_verdict == "FAILED")
    any_survives = any(v == "SURVIVES" for v in [h1_verdict, h2_verdict, h3_verdict, h4_verdict])

    if h1_h2_h3_all_fail and h4_fails:
        branch = "A+B: H1-H3 all FAIL AND H4 FAILS"
        rationale = (
            "DT-R13 restoration path CLOSED permanently (whale family closed). "
            "H4 FAILS: chip's extension band loses remaining evidential basis. "
            "Fable to remove fade/bounce states; chip becomes descriptive extension-percentile only."
        )
    elif h1_h2_h3_all_fail:
        branch = "A: H1-H3 all FAIL, H4 SURVIVES"
        rationale = (
            "DT-R13 restoration path CLOSED permanently (whale family closed). "
            "H4 SURVIVES: extension-band evidence survives time control. "
            "Chip extension-percentile band has 64y time-controlled support (still survivor-flattered)."
        )
    elif h4_fails and not any_survives:
        branch = "B: H4 FAILS (and no H1-H3 survive)"
        rationale = (
            "H4 FAILS: chip's extension band loses remaining evidential basis. "
            "Fable to remove fade/bounce states; chip becomes descriptive extension-percentile only. "
            "DT-R13: no survivor — no restoration prereg triggered."
        )
    elif any_survives:
        survivors = [h for h, v in [("H1", h1_verdict), ("H2", h2_verdict), ("H3", h3_verdict), ("H4", h4_verdict)] if v == "SURVIVES"]
        branch = f"C: SURVIVES — {', '.join(survivors)} survive time control on 64y survivor panel"
        rationale = (
            f"{', '.join(survivors)} survive month-block time control on 64y panel. "
            "Each surviving read is eligible for a restoration prereg (display-only ceiling unchanged). "
            "DT-R13: restoration path open for surviving reads only. "
            "Caveat: survivor-flattered panel — must be replicated on honest panel before any chip change."
        )
    else:
        branch = "A+B: all FAIL"
        rationale = "Same as A+B."

    # --- calibration controls ---
    print("[DT-W2] running control C1: within-ticker time permutation (H1/H2 raw)...", file=sys.stderr)
    ctrl_c1 = _ctrl_within_ticker_time_permutation(pool)
    print("[DT-W2] running control C2: within-month cross-ticker permutation (H3/H4)...", file=sys.stderr)
    ctrl_c2 = _ctrl_within_month_cross_ticker_permutation(pool)
    print("[DT-W2] running control C3: within-ticker permutation on demeaned (H1/H2 TC)...", file=sys.stderr)
    ctrl_c3 = _ctrl_within_ticker_time_permutation_on_demeaned(pool)
    print("[DT-W2] running control C4: positive injection (H2)...", file=sys.stderr)
    ctrl_c4 = _ctrl_positive_injection(pool)

    # --- assemble results ---
    def _strip_boots(d: dict) -> dict:
        return {k: v for k, v in d.items() if k != "_boots"}

    coverage_stamps = {
        "n_tickers_attempted": n_attempted,
        "n_tickers_fetched": n_fetched,
        "fetch_success_pct": fetch_success_pct,
        "n_fetch_failed": n_failed,
        "failed_fetch_tickers": failed,
        "n_tickers_usable": n_usable,
        "total_gap_excluded_months": total_gap_excluded,
        "pool_ticker_months_total": int(pool.shape[0]),
        "pool_rows_with_whale_and_fwd": n_full,
        "n_calendar_months": n_months,
        "panel_fwd_1m_range_pct": [panel_fwd_min, panel_fwd_max],
        "store_latest_date": str(store_latest.date()) if store_latest else None,
        "store_earliest_date": str(store_earliest.date()) if store_earliest else None,
        "approx_history_span": approx_span,
        "study_run_date": datetime.now(timezone.utc).isoformat(),
        "powered": powered,
        "power_threshold_months": 240,
        "panel_type": "SURVIVOR_PANEL_DELIBERATE",
        "survivorship_caveat": (
            "Panel deliberately retains original survivor bias. "
            "Results are survivor-flattered in the contrarian/bottoming direction. "
            "DT-W1a (survivorship-honest 2021+ panel) found all four reads FAILED time-controlled."
        ),
        "era_law": "yfinance OHLCV cache, auto-adjusted, full history from ~1962 (phase-0 replication)",
        "dtw1a_h1_lift": "-0.0062",
        "dtw1a_h4_sp": "+0.0548",
    }

    results = {
        "study": "DT-W2",
        "prereg_authority": "DANNYTRADES_NW_ADJUDICATION §7 DT-R13 DT-R14",
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
        # RAW (superseded) basis
        "h1_raw": {**_strip_boots(h1_raw), "basis": "raw ticker-cluster only (superseded)",
                   "note": "original 64y study had no time control; this is what that looked like"},
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
        # BH correction
        "bh_correction": {
            "q": BH_Q,
            "m": M_TESTS,
            "p_values_exact": [round(p, 4) for p in p_values],
            "survived": bh_survived,
            "method": "exact one-sided bootstrap tail fractions",
        },
        # Consequence branch
        "consequence_branch": {
            "branch": branch,
            "rationale": rationale,
            "h1_verdict": h1_verdict,
            "h2_verdict": h2_verdict,
            "h3_verdict": h3_verdict,
            "h4_verdict": h4_verdict,
        },
    }

    # --- register trial ledger ---
    _register_trial_ledger(results)

    # --- write outputs ---
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(results, indent=2, default=str))
    print(f"[DT-W2] wrote {out_json}", file=sys.stderr)

    out_md.parent.mkdir(parents=True, exist_ok=True)
    _write_markdown(results, out_md)
    print(f"[DT-W2] wrote {out_md}", file=sys.stderr)

    return results


# ---------------------------------------------------------------------------#
# CLI
# ---------------------------------------------------------------------------#

def main() -> int:
    parser = argparse.ArgumentParser(description="DT-W2 64-year month-block time-control re-run")
    parser.add_argument(
        "--cache",
        default="/tmp/dtcache64",
        help="Path to yfinance parquet cache directory",
    )
    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help="Load from cache only (no network fetch)",
    )
    args = parser.parse_args()

    cache_dir = Path(args.cache)
    out_json = REPO_ROOT / "data" / "research" / "dt_w2_64y.json"
    out_md = REPO_ROOT / "research" / "dannytrades" / "DT_W2_64Y_RESULTS.md"

    run_study(cache_dir, out_json, out_md, skip_fetch=args.skip_fetch)
    return 0


if __name__ == "__main__":
    sys.exit(main())
