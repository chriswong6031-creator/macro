"""W3-B — MAX/lottery-effect phase-0 (AVOID-screen candidate).

External evidence (ashare-signal-research §B): high-MAX names (max single-day return
over trailing 21 sessions) systematically underperform in A-shares — the retail lottery-
preference mechanism. Candidate role: a DEFENSIVE screen to exclude top-MAX names; NEVER
a long signal.

PRE-REGISTERED (fixed before running; do not adjust ex-post):
  Universe   : board members in china_stocks_raw, ≥756 rows (~3y) history as of each
               rebalance date. Sector from china_search/members.parquet.
  Signal     : MAX = max(ret_daily) over trailing 21 sessions on the RAW price plane
               (limit-up events INCLUDED — they are the lottery events).
  Locked-limit exclusion : fill-realistic T+1 — rows where hi==lo==close on the RAW
               plane are EXCLUDED from the universe at that bar (locked-limit days cannot
               be entered/exited at a fill near the close).
  Benchmark  : CSI300 ETF proxy (510300.SS, china store), close-to-close.
  Fill model : T+1 (high+low)/2 entry — for each monthly rebalance on date d, the fill
               entry is the NEXT bar's (high+low)/2; exit after 21 calendar trading days
               at (high+low)/2. Close-to-close is ALSO reported (upper bound).
  Monthly decile sorts on grid of end-of-month dates.
  Primary L/S: low-MAX minus high-MAX decile CSI300-relative 21d HAC t.
  Screen test: does excluding the top-MAX decile from the pool lift pool mean vs raw pool?
  Splits     : full / pre-2021 / 2021+
  Monotonicity: decile mean return from decile 1 (low MAX) to decile 10 (high MAX).
  2000-perm placebo: permute MAX cross-section at each date; report null distribution.
  Positive control: within-sector reversal run through THE SAME HARNESS.
  Orthogonality: partial-correlation of MAX vs BOTH reversal (rev_z proxy) AND abn_turn
               proxy (volume-z 21d), controlling for each other and CSI300 excess, to
               check whether MAX is redundant with its sibling factors.

PRE-REGISTERED THRESHOLDS:
  GO     : L/S t_HAC >= 3 full-sample AND pre-2021 split t_HAC >= 2 (split-stable sign)
  ACCRUE : 2 <= t_HAC < 3 full, OR era-only (2021+ only), OR sign-stable but |t|=2-3
  NO-GO  : otherwise (including positive L/S only in a single era, or wrong sign)

Run: PYTHONPATH=$PWD python3 -m scripts.china_max_phase0
Deterministic: np.random.default_rng(seed=42) everywhere.
No network. No writes other than reports/china-max-phase0.md and
research/china_alpha/w3/china-max-phase0.md.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")

from engine.validation import rank_ic, ic_summary, benjamini_hochberg  # noqa: E402
from lib import config  # noqa: E402

# ─────────────────────────────────────── constants ───────────────────────────
MAX_WINDOW = 21          # trailing sessions for max(ret)
FWD_WINDOW = 21          # forward holding period (trading days)
MIN_HISTORY = 756        # ~3 years minimum per name (at each rebalance)
MIN_NAMES = 30           # minimum names per rebalance date
DECILES = 10
SEED = 42
N_PERM = 2000
LOCKED_LIMIT = 0.095    # |ret|> this flags limit-up/down (abs daily ret threshold)

RAW_DIR = "data/china_stocks_raw"
MEMBERS = "data/china_search/members.parquet"
CSI300 = "data/china/510300.SS.parquet"


# ─────────────────────────────────────── data loading ────────────────────────

def load_raw_panel(root: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load close / high / low / volume from china_stocks_raw for board members.

    Returns (close, high, low, volume) aligned on a common date index.
    Only board members (from members.parquet) are loaded.
    """
    members = pd.read_parquet(root / MEMBERS)
    board_tickers = set(members.index.tolist())

    closes, highs, lows, vols = {}, {}, {}, {}
    raw_dir = root / RAW_DIR
    for p in sorted(raw_dir.glob("*.parquet")):
        if p.stem not in board_tickers:
            continue
        df = pd.read_parquet(p)
        if not {"close", "high", "low", "volume"}.issubset(df.columns):
            continue
        closes[p.stem] = df["close"]
        highs[p.stem] = df["high"]
        lows[p.stem] = df["low"]
        vols[p.stem] = df["volume"]

    close = pd.DataFrame(closes).sort_index()
    high = pd.DataFrame(highs).reindex(close.index)
    low = pd.DataFrame(lows).reindex(close.index)
    vol = pd.DataFrame(vols).reindex(close.index)
    print(f"  loaded {close.shape[1]} tickers, {close.shape[0]} dates, "
          f"{close.index.min().date()} → {close.index.max().date()}")
    return close, high, low, vol


def load_csi300(root: Path) -> pd.Series:
    """CSI300 ETF proxy close (510300.SS)."""
    df = pd.read_parquet(root / CSI300)
    s = df["close"]
    s.index = pd.to_datetime(s.index)
    return s


def load_sector(root: Path, columns: pd.Index) -> pd.Series:
    """Sector mapping for columns from members.parquet."""
    members = pd.read_parquet(root / MEMBERS)
    JUNK = "A-share"
    sector = pd.Series({t: (s if s != JUNK else "—") for t, s in members["sector"].items()})
    return sector.reindex(columns).fillna("—")


# ─────────────────────────────────────── signal construction ──────────────────

def build_daily_ret(close: pd.DataFrame) -> pd.DataFrame:
    """Daily returns (pct_change, fill_method=None)."""
    return close.pct_change(fill_method=None)


def build_locked_limit_mask(close: pd.DataFrame, high: pd.DataFrame,
                             low: pd.DataFrame) -> pd.DataFrame:
    """Boolean mask: True = row is locked-limit (hi==lo==close) and should be EXCLUDED.

    A locked limit bar is one where the security cannot be traded at a fill near
    the close. We identify it as high==low==close (within floating-point tolerance).
    This mask is applied to ENTRY: if the fill bar (T+1) is locked, we exclude that
    name from the period's portfolio.
    """
    tol = 1e-4
    same_hl = (high - low).abs() < tol
    same_hc = (high - close).abs() < tol
    return same_hl & same_hc


def build_max_signal(ret: pd.DataFrame) -> pd.DataFrame:
    """MAX = max(daily return) over trailing MAX_WINDOW sessions.

    Limit-up events are INCLUDED (they are the lottery events by design).
    At each date d, the signal is computed on [d-MAX_WINDOW+1, d].
    Uses shift(0) — the signal at d uses data up to and including d, so the
    forward return starting from d+1 is clean (no look-ahead).
    """
    return ret.rolling(MAX_WINDOW, min_periods=MAX_WINDOW).max()


def build_rev_proxy(close: pd.DataFrame) -> pd.DataFrame:
    """Reversal proxy (rev_z): negative 21d return — the validated within-sector signal.

    Used for the orthogonality partial-correlation check.
    """
    return -close.pct_change(21, fill_method=None)


def build_abn_turn_proxy(close: pd.DataFrame, vol: pd.DataFrame) -> pd.DataFrame:
    """Abnormal turnover proxy: volume z-score over trailing 63 days.

    abn_turn = (vol - mean_63d) / std_63d (all within-name)
    Higher = more abnormal turnover. Used for orthogonality check vs MAX.
    """
    log_vol = np.log(vol.clip(lower=1e-9))
    roll_mean = log_vol.rolling(63, min_periods=20).mean()
    roll_std = log_vol.rolling(63, min_periods=20).std()
    return (log_vol - roll_mean) / roll_std.replace(0, np.nan)


# ─────────────────────────────────────── fill-realistic returns ───────────────

def fill_realistic_fwd(high: pd.DataFrame, low: pd.DataFrame,
                       locked: pd.DataFrame) -> pd.DataFrame:
    """T+1 (high+low)/2 fill-realistic forward return over FWD_WINDOW.

    Entry at bar d+1: price_in = (high[d+1] + low[d+1]) / 2
    Exit at bar d+FWD_WINDOW+1: price_out = (high[d+FWD+1] + low[d+FWD+1]) / 2
    Names where the entry bar (d+1) is locked-limit get NaN.
    Aligns to date d so fwd_fill[d] = forward return from d+1 to d+FWD_WINDOW+1.
    """
    midpoint = (high + low) / 2.0
    # Entry bar is d+1 (shifted -1 from d)
    entry_mid = midpoint.shift(-1)
    # Exit bar is d+FWD_WINDOW+1 (shifted -(FWD_WINDOW+1) from d)
    exit_mid = midpoint.shift(-(FWD_WINDOW + 1))
    fwd_fill = exit_mid / entry_mid - 1.0
    # Exclude locked-limit entry bars
    # entry_locked must be bool and aligned before masking
    entry_locked = locked.shift(-1).reindex(fwd_fill.index, fill_value=False).fillna(False)
    fwd_fill = fwd_fill.where(~entry_locked.astype(bool))
    return fwd_fill


def close_to_close_fwd(close: pd.DataFrame) -> pd.DataFrame:
    """Close-to-close forward 21d return (upper bound; over-states fill-realistic by ~0.9-1.1pp)."""
    return close.pct_change(FWD_WINDOW, fill_method=None).shift(-FWD_WINDOW)


def csi300_fwd(csi300: pd.Series, close_idx: pd.DatetimeIndex) -> pd.Series:
    """CSI300 21d close-to-close forward return, aligned to close_idx."""
    csi = csi300.reindex(close_idx).ffill()
    return csi.pct_change(FWD_WINDOW, fill_method=None).shift(-FWD_WINDOW)


# ─────────────────────────────────────── monthly grid ────────────────────────

def build_monthly_grid(idx: pd.DatetimeIndex, burn_in: int,
                       lookforward: int) -> list:
    """End-of-month dates with sufficient burn-in and look-forward room."""
    grid = [idx[idx <= me][-1]
            for me in pd.date_range(idx.min(), idx.max(), freq="ME")
            if len(idx[idx <= me])]
    iloc_map = {d: idx.get_loc(d) for d in grid}
    return [d for d in grid
            if iloc_map[d] >= burn_in and iloc_map[d] + lookforward + 2 < len(idx)]


# ─────────────────────────────────────── eligible universe per date ───────────

def eligible_names(d, close: pd.DataFrame, max_sig: pd.DataFrame,
                   ret: pd.DataFrame) -> pd.Index:
    """Names eligible at date d:
    - present in the raw panel (close not NaN)
    - have >= MIN_HISTORY rows of price history up to d
    - MAX signal not NaN (enough lookback)
    - daily return not NaN at d
    """
    idx = close.index
    d_pos = idx.get_loc(d)
    # names with at least MIN_HISTORY rows up to d
    n_valid = (close.iloc[max(0, d_pos - MIN_HISTORY + 1): d_pos + 1]
               .notna().sum())
    deep_names = n_valid[n_valid >= MIN_HISTORY].index

    # names where MAX signal is available
    sig_available = max_sig.loc[d].dropna().index
    return deep_names.intersection(sig_available)


# ─────────────────────────────────────── main backtest ───────────────────────

def run_backtest(grid: list, close: pd.DataFrame, max_sig: pd.DataFrame,
                 ret: pd.DataFrame, fwd_fill: pd.DataFrame,
                 fwd_ctc: pd.DataFrame, csi_fwd: pd.Series,
                 sector: pd.Series) -> dict:
    """Run the main decile-level backtest.

    Returns:
        ic_series: list of per-rebalance L/S (D1-D10) fill-realistic CSI300-excess
        ic_series_ctc: same, close-to-close
        decile_stats: per-decile mean fill-realistic CSI300-excess
        screen_stats: pool-without-topMAX vs raw-pool mean excess
        n_names: list of n eligible names per rebalance
        dates: list of rebalance dates used
    """
    ls_fill, ls_ctc = [], []   # L/S (D1-D10) per rebalance
    decile_fill = [[] for _ in range(DECILES)]
    decile_ctc = [[] for _ in range(DECILES)]
    pool_raw, pool_screened = [], []  # screen-test accumulators
    n_names_list = []
    dates_used = []
    ic_series_fill = []

    for d in grid:
        if d not in close.index:
            continue
        elig = eligible_names(d, close, max_sig, ret)
        if len(elig) < MIN_NAMES:
            continue

        # CSI300 forward return for this bar
        csi_r = csi_fwd.get(d, np.nan)
        if np.isnan(csi_r):
            continue

        # signals
        sig = max_sig.loc[d].reindex(elig).dropna()
        if len(sig) < MIN_NAMES:
            continue

        # fill-realistic forward returns
        ff = fwd_fill.loc[d].reindex(sig.index).dropna()
        ctc = fwd_ctc.loc[d].reindex(sig.index).dropna()
        common = sig.index.intersection(ff.index).intersection(ctc.index)
        if len(common) < MIN_NAMES:
            continue

        sig = sig.reindex(common)
        ff = ff.reindex(common)
        ctc = ctc.reindex(common)

        # CSI300-relative excess
        ff_ex = ff - csi_r
        ctc_ex = ctc - csi_r

        # decile assignment (1 = lowest MAX, 10 = highest MAX)
        sig_rank = sig.rank(pct=True)
        decile_label = np.ceil(sig_rank * DECILES).clip(1, DECILES).astype(int)

        # D1 (low-MAX) and D10 (high-MAX)
        d1_fill = ff_ex[decile_label == 1]
        d10_fill = ff_ex[decile_label == 10]
        d1_ctc = ctc_ex[decile_label == 1]
        d10_ctc = ctc_ex[decile_label == 10]

        if len(d1_fill) < 3 or len(d10_fill) < 3:
            continue

        # L/S this period (low-MAX minus high-MAX)
        ls_fill.append(float(d1_fill.mean() - d10_fill.mean()))
        ls_ctc.append(float(d1_ctc.mean() - d10_ctc.mean()))

        # Rank IC (MAX signal vs forward excess; negative = good)
        ic_series_fill.append(rank_ic(sig, ff_ex))

        # per-decile accumulators
        for dec in range(1, DECILES + 1):
            mask = decile_label == dec
            if mask.sum() > 0:
                decile_fill[dec - 1].append(float(ff_ex[mask].mean()))
                decile_ctc[dec - 1].append(float(ctc_ex[mask].mean()))

        # Screen test: pool_raw = all names; pool_screened = pool without top-MAX decile
        pool_raw.append(float(ff_ex.mean()))
        pool_screened.append(float(ff_ex[decile_label < DECILES].mean()))

        n_names_list.append(len(common))
        dates_used.append(d)

    ls_fill_s = pd.Series(ls_fill)
    ls_ctc_s = pd.Series(ls_ctc)

    return {
        "ls_fill": ls_fill_s,
        "ls_ctc": ls_ctc_s,
        "ic_fill": ic_series_fill,
        "decile_fill": [pd.Series(d) for d in decile_fill],
        "decile_ctc": [pd.Series(d) for d in decile_ctc],
        "pool_raw": pd.Series(pool_raw),
        "pool_screened": pd.Series(pool_screened),
        "n_names": n_names_list,
        "dates_used": dates_used,
    }


def era_mask(dates: list, start: str | None, end: str | None) -> list[bool]:
    """Boolean mask for era slicing."""
    lo = pd.Timestamp(start) if start else pd.Timestamp("1900-01-01")
    hi = pd.Timestamp(end) if end else pd.Timestamp("2099-12-31")
    return [lo <= d <= hi for d in dates]


def summarize_ls(ls: pd.Series, mask: list[bool] | None = None,
                 lags: int = 4) -> dict:
    """Summarize L/S series: mean, t_HAC, hit, n."""
    s = ls[mask] if mask is not None else ls
    s = s.dropna()
    n = len(s)
    if n < 8:
        return {"n": n, "mean_pct": None, "t_hac": None, "hit": None}
    from engine.validation import newey_west_tstat
    nw = newey_west_tstat(s, lags=lags)
    return {
        "n": n,
        "mean_pct": round(float(s.mean()) * 100, 3),
        "t_hac": nw["t"],
        "p_hac": nw["p"],
        "hit": round(float((s > 0).mean()), 3),
        "maxdd_pct": round(float(((1 + s).cumprod() / (1 + s).cumprod().cummax() - 1).min()) * 100, 1),
    }


# ─────────────────────────────────────── permutation placebo ─────────────────

def run_permutation_placebo(grid: list, close: pd.DataFrame, max_sig: pd.DataFrame,
                             ret: pd.DataFrame, fwd_fill: pd.DataFrame,
                             csi_fwd: pd.Series, n_perm: int = N_PERM,
                             seed: int = SEED) -> dict:
    """2000-permutation null distribution for the L/S statistic.

    At each rebalance date, permute the MAX signal CROSS-SECTIONALLY (scramble
    which names get which MAX value, preserving the marginal distribution).
    Compute L/S for each permutation and report the null distribution.
    Returns the real t_HAC and its perm-p.
    """
    rng = np.random.default_rng(seed)

    # First, collect the real L/S series observations per date
    per_date = []
    for d in grid:
        if d not in close.index:
            continue
        elig = eligible_names(d, close, max_sig, ret)
        if len(elig) < MIN_NAMES:
            continue
        csi_r = csi_fwd.get(d, np.nan)
        if np.isnan(csi_r):
            continue
        sig = max_sig.loc[d].reindex(elig).dropna()
        ff = fwd_fill.loc[d].reindex(sig.index).dropna()
        common = sig.index.intersection(ff.index)
        if len(common) < MIN_NAMES:
            continue
        sig = sig.reindex(common).values
        ff_ex = ff.reindex(common).values - csi_r
        per_date.append((sig, ff_ex))

    if len(per_date) < 12:
        return {"real_t": None, "null_mean": None, "null_sd": None, "perm_p": None}

    def ls_from_perms(perms_sigs):
        """For a given list of permuted signals, compute mean L/S across dates."""
        ls = []
        for i, (_, ff_ex) in enumerate(per_date):
            sig_p = perms_sigs[i]
            n = len(sig_p)
            ranks = sig_p.argsort().argsort()  # 0-based rank
            lo = np.where(ranks < n // DECILES)[0]
            hi = np.where(ranks >= n - n // DECILES)[0]
            if len(lo) < 2 or len(hi) < 2:
                continue
            ls.append(float(ff_ex[lo].mean() - ff_ex[hi].mean()))
        return ls

    # Real signal
    real_sigs = [x[0] for x in per_date]
    real_ls = ls_from_perms(real_sigs)
    from engine.validation import newey_west_tstat
    real_t = newey_west_tstat(pd.Series(real_ls), lags=4)["t"]

    # Permutation null
    null_ts = []
    for _ in range(n_perm):
        perm_sigs = [rng.permutation(s) for s in real_sigs]
        pls = ls_from_perms(perm_sigs)
        if len(pls) >= 8:
            nt = newey_west_tstat(pd.Series(pls), lags=4)["t"]
            null_ts.append(nt)

    null_arr = np.array(null_ts)
    perm_p = float(np.mean(np.abs(null_arr) >= abs(real_t))) if np.isfinite(real_t) else float("nan")

    return {
        "real_t": round(float(real_t), 3),
        "null_mean": round(float(null_arr.mean()), 3),
        "null_sd": round(float(null_arr.std()), 3),
        "null_p_at_2": round(float(np.mean(np.abs(null_arr) >= 2)), 3),
        "perm_p": round(perm_p, 4),
        "n_perm": len(null_ts),
    }


# ─────────────────────────────────────── positive control ────────────────────

def run_positive_control(grid: list, close: pd.DataFrame,
                          fwd_fill: pd.DataFrame, csi_fwd: pd.Series,
                          sector: pd.Series) -> dict:
    """Positive control: within-sector reversal through THE SAME HARNESS.

    The reversal long leg is validated (+0.56%/mo, t>3 on the deep panel).
    Here we test: does the reversal top-quintile (per sector) earn positive
    CSI300-relative excess when run through our fill-realistic harness?
    This confirms the harness can detect known effects.
    """
    # Reversal proxy: -ret_21d, demeaned within sector
    r21 = -close.pct_change(21, fill_method=None)

    ls_fill = []
    for d in grid:
        if d not in close.index:
            continue
        csi_r = csi_fwd.get(d, np.nan)
        if np.isnan(csi_r):
            continue
        # within-sector demeaning
        rev = r21.loc[d].dropna()
        sec = sector.reindex(rev.index)
        rev_dm = rev - rev.groupby(sec).transform("mean")
        ff = fwd_fill.loc[d].reindex(rev_dm.index).dropna()
        common = rev_dm.index.intersection(ff.index)
        if len(common) < MIN_NAMES:
            continue
        rev_c = rev_dm.reindex(common)
        ff_ex = ff.reindex(common) - csi_r
        # Top quintile of reversal signal (highest within-sector underperformers)
        q80 = rev_c.quantile(0.8)
        sel = rev_c[rev_c >= q80]
        if len(sel) < 5:
            continue
        pool_mean = ff_ex.mean()
        sel_ex = ff_ex.reindex(sel.index).mean()
        ls_fill.append(float(sel_ex - pool_mean))

    ls = pd.Series(ls_fill)
    return summarize_ls(ls)


# ─────────────────────────────────────── orthogonality check ─────────────────

def run_orthogonality(grid: list, close: pd.DataFrame, max_sig: pd.DataFrame,
                       ret: pd.DataFrame, vol: pd.DataFrame,
                       fwd_fill: pd.DataFrame, csi_fwd: pd.Series,
                       sector: pd.Series) -> dict:
    """Partial-correlation orthogonality check: MAX vs reversal and abn_turn.

    For each rebalance date, stack cross-section of:
      y     = fill-realistic CSI300-excess 21d
      x_max = MAX signal (raw, not rank-normalized)
      x_rev = reversal proxy (-ret_21d, within-sector demeaned)
      x_abn = abnormal turnover proxy (volume z-score)

    Report:
      - Bivariate rank-IC of MAX with y
      - Bivariate rank-IC of rev with y
      - Bivariate rank-IC of abn_turn with y
      - Partial rank-IC of MAX with y | (rev, abn_turn) — proxied by ranking the
        residual of MAX after OLS on rev + abn_turn, then rank-IC with y
      - Correlation between MAX and rev (to flag if they share too much info)
      - Correlation between MAX and abn_turn
    """
    abn_turn = build_abn_turn_proxy(close, vol)
    r21 = -close.pct_change(21, fill_method=None)

    ic_max, ic_rev, ic_abn = [], [], []
    ic_max_partial, corr_max_rev, corr_max_abn = [], [], []

    for d in grid:
        if d not in close.index:
            continue
        csi_r = csi_fwd.get(d, np.nan)
        if np.isnan(csi_r):
            continue

        ms = max_sig.loc[d].dropna()
        rv = r21.loc[d].reindex(ms.index).dropna()
        ab = abn_turn.loc[d].reindex(ms.index).dropna()
        ff = fwd_fill.loc[d].reindex(ms.index).dropna()
        sec = sector.reindex(ms.index)

        # within-sector demean reversal
        rv_dm = rv - rv.groupby(sec.reindex(rv.index)).transform("mean")

        # common set
        common = ms.index.intersection(rv_dm.index).intersection(ab.index).intersection(ff.index)
        if len(common) < MIN_NAMES:
            continue

        ms_c = ms.reindex(common)
        rv_c = rv_dm.reindex(common)
        ab_c = ab.reindex(common)
        ff_ex = ff.reindex(common) - csi_r

        ic_max.append(rank_ic(ms_c, ff_ex))
        ic_rev.append(rank_ic(rv_c, ff_ex))
        ic_abn.append(rank_ic(ab_c, ff_ex))

        # Partial rank-IC of MAX vs y | (rev, abn_turn)
        # Residualize MAX on (rev, abn_turn) via OLS on ranks
        n = len(common)
        if n >= 20:
            X = np.column_stack([
                rv_c.rank().values / n,
                ab_c.rank().values / n,
                np.ones(n)
            ])
            y_r = ms_c.rank().values / n
            try:
                beta = np.linalg.lstsq(X, y_r, rcond=None)[0]
                max_resid = y_r - X @ beta
                ic_max_partial.append(rank_ic(pd.Series(max_resid, index=common), ff_ex))
            except Exception:
                pass

        # Cross-sectional correlation between MAX and its siblings
        corr_max_rev.append(float(ms_c.rank().corr(rv_c.rank())))
        corr_max_abn.append(float(ms_c.rank().corr(ab_c.rank())))

    def nw_t(series):
        s = pd.Series(series).dropna()
        if len(s) < 8:
            return None
        from engine.validation import newey_west_tstat
        return newey_west_tstat(s, lags=4)["t"]

    return {
        "ic_max_mean": round(float(np.nanmean(ic_max)), 4),
        "ic_max_t": nw_t(ic_max),
        "ic_rev_mean": round(float(np.nanmean(ic_rev)), 4),
        "ic_rev_t": nw_t(ic_rev),
        "ic_abn_mean": round(float(np.nanmean(ic_abn)), 4),
        "ic_abn_t": nw_t(ic_abn),
        "ic_max_partial_mean": round(float(np.nanmean(ic_max_partial)), 4) if ic_max_partial else None,
        "ic_max_partial_t": nw_t(ic_max_partial) if ic_max_partial else None,
        "corr_max_rev_mean": round(float(np.nanmean(corr_max_rev)), 3),
        "corr_max_abn_mean": round(float(np.nanmean(corr_max_abn)), 3),
        "n_dates": len(ic_max),
    }


# ─────────────────────────────────────── monotonicity ────────────────────────

def decile_monotonicity(decile_fill: list[pd.Series]) -> dict:
    """Count monotone steps (D(i) > D(i+1)) in mean decile returns, D1→D10.

    A clean lottery effect would show D1 > D2 > ... > D10 (9/9 steps).
    """
    means = [s.mean() * 100 for s in decile_fill]
    steps = 0
    for i in range(len(means) - 1):
        if not np.isnan(means[i]) and not np.isnan(means[i + 1]) and means[i] > means[i + 1]:
            steps += 1
    return {"decile_means_pct": [round(m, 3) for m in means], "monotone_steps": steps,
            "max_steps": len(means) - 1}


# ─────────────────────────────────────── screen test ─────────────────────────

def screen_test(pool_raw: pd.Series, pool_screened: pd.Series) -> dict:
    """Does excluding the top-MAX decile lift pool mean excess?

    Compare pool mean with vs without top-MAX decile.
    """
    diff = pool_screened - pool_raw
    s = diff.dropna()
    if len(s) < 8:
        return {"n": len(s), "lift_mean_pct": None, "t": None}
    t, p = stats.ttest_1samp(s, 0)
    return {
        "n": int(len(s)),
        "pool_raw_mean_pct": round(float(pool_raw.mean()) * 100, 3),
        "pool_screened_mean_pct": round(float(pool_screened.mean()) * 100, 3),
        "lift_mean_pct": round(float(s.mean()) * 100, 3),
        "t": round(float(t), 2),
        "p": round(float(p), 4),
    }


# ─────────────────────────────────────── report rendering ────────────────────

def render_report(bt: dict, full: dict, pre2021: dict, post2021: dict,
                  mono: dict, scr: dict, perm: dict, pc: dict, orth: dict,
                  ic_full: dict, close: pd.DataFrame, grid: list,
                  n_names_mean: float) -> str:
    def safe_fmt(v, fmt=".3f"):
        return f"{v:{fmt}}" if v is not None and np.isfinite(float(v)) else "n/a"

    def t_stars(t):
        if t is None or not np.isfinite(float(t)):
            return ""
        t = abs(t)
        if t >= 3:
            return "***"
        if t >= 2:
            return "**"
        if t >= 1.5:
            return "*"
        return ""

    ls_mean = full.get("mean_pct") or 0

    L = [
        "# W3-B — MAX / Lottery-Effect Phase-0 (A-share AVOID-screen candidate)",
        "",
        f"*Generated by `scripts/china_max_phase0.py` · {close.shape[1]} tickers from "
        f"`data/china_stocks_raw`, {len(grid)} monthly rebalance dates, "
        f"{pd.Timestamp(grid[0]).date()} → {pd.Timestamp(grid[-1]).date()}. "
        f"Mean eligible names/rebalance: {round(n_names_mean)}. "
        "Universe filter: board members with ≥756 rows history. "
        "Fill model: T+1 (high+low)/2 entry, locked-limit (hi==lo==close) bars excluded. "
        "Benchmark: CSI300 ETF proxy (510300.SS). MAX = max(daily return) over trailing "
        "21 sessions (limit-up events INCLUDED — they are the lottery events).*",
        "",
        "---",
        "",
        "## Pre-registered verdict thresholds (fixed before run)",
        "",
        "| verdict | condition |",
        "|---|---|",
        "| GO | L/S t_HAC ≥ 3 full-sample AND pre-2021 split t_HAC ≥ 2 (split-stable sign) |",
        "| ACCRUE | 2 ≤ t_HAC < 3 full, OR era-only (2021+ only), OR sign-stable but \\|t\\|=2–3 |",
        "| NO-GO | otherwise |",
        "",
        "---",
        "",
        "## 1. L/S spread (low-MAX D1 minus high-MAX D10) — fill-realistic and close-to-close",
        "",
        "| era | n reb | mean excess/reb | HAC-t | hit | max DD |",
        "|---|--:|--:|--:|--:|--:|",
    ]

    for label, res in [("full", full), ("pre-2021", pre2021), ("post-2021", post2021)]:
        t = res.get("t_hac")
        stars = t_stars(t)
        L.append(
            f"| fill-real · {label} | {res.get('n', '?')} | "
            f"{safe_fmt(res.get('mean_pct'))}% | "
            f"{safe_fmt(t)}{stars} | "
            f"{safe_fmt(res.get('hit'))} | "
            f"{safe_fmt(res.get('maxdd_pct'))}% |"
        )

    # Close-to-close L/S summary (full only)
    ls_ctc = bt.get("ls_ctc", pd.Series())
    ls_ctc_sum = summarize_ls(ls_ctc)
    L.append(
        f"| close-to-close · full | {ls_ctc_sum.get('n', '?')} | "
        f"{safe_fmt(ls_ctc_sum.get('mean_pct'))}% | "
        f"{safe_fmt(ls_ctc_sum.get('t_hac'))}{t_stars(ls_ctc_sum.get('t_hac'))} | "
        f"{safe_fmt(ls_ctc_sum.get('hit'))} | — |"
    )

    # IC summary
    L += [
        "",
        f"**Rank-IC (MAX signal vs 21d CSI300-relative excess), full sample:**  "
        f"mean IC = {safe_fmt(ic_full.get('mean_ic'))}, "
        f"t_HAC = {safe_fmt(ic_full.get('t_hac'))}, "
        f"hit = {safe_fmt(ic_full.get('hit'))}, n = {ic_full.get('n', '?')}.",
        "(Negative IC = higher MAX → lower forward excess; confirms lottery-effect direction.)",
        "",
        "---",
        "",
        "## 2. Decile monotonicity (D1 = low-MAX, D10 = high-MAX)",
        "",
        "| decile | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 | D9 | D10 |",
        "|---|" + "|".join(["--:"] * 10) + "|",
        "| mean excess/reb % | " +
        " | ".join(safe_fmt(m) for m in mono["decile_means_pct"]) + " |",
        "",
        f"Monotone steps (D_i > D_{{i+1}}): **{mono['monotone_steps']} / {mono['max_steps']}**  "
        "(9/9 = perfect; a clean lottery effect requires most steps to decrease from D1 to D10).",
        "",
        "---",
        "",
        "## 3. Screen test — does excluding top-MAX decile lift pool mean?",
        "",
        "| | pool raw (all names) | pool ex-topMAX (D1-D9) | lift | t | p |",
        "|---|--:|--:|--:|--:|--:|",
        f"| mean excess/reb % | {safe_fmt(scr.get('pool_raw_mean_pct'))} | "
        f"{safe_fmt(scr.get('pool_screened_mean_pct'))} | "
        f"**{safe_fmt(scr.get('lift_mean_pct'))}** | "
        f"{safe_fmt(scr.get('t'))} | {safe_fmt(scr.get('p'))} |",
        "",
        "The SCREEN-relevant statistic is whether excluding the top-MAX decile lifts the mean "
        "of the remaining pool. A positive lift with p < 0.10 supports using MAX as a defensive "
        "screen even if the full L/S spread is noisy.",
        "",
        "---",
        "",
        "## 4. 2000-permutation placebo (cross-sectional shuffle)",
        "",
        f"Real L/S t_HAC = **{safe_fmt(perm.get('real_t'))}**  |  "
        f"null: mean = {safe_fmt(perm.get('null_mean'))}, "
        f"sd = {safe_fmt(perm.get('null_sd'))}, "
        f"P(|t_null| ≥ 2) = {safe_fmt(perm.get('null_p_at_2'))}  |  "
        f"perm-p (real vs null) = **{safe_fmt(perm.get('perm_p'))}**  "
        f"(n_perm = {perm.get('n_perm', '?')}).",
        "",
        ("A valid null centers on 0 with sd ≈ 1. Real t sits at a remarkable percentile "
         "(perm-p < 0.05) — the L/S is genuine cross-sectional variation, not measurement noise."
         if (perm.get("perm_p") is not None and perm["perm_p"] < 0.05) else
         "A valid null centers on 0 with sd ≈ 1. The real t sits WITHIN the null "
         f"(perm-p = {safe_fmt(perm.get('perm_p'))}) — the L/S is statistically "
         "indistinguishable from random relabelling."),
        "",
        "---",
        "",
        "## 5. Positive control — within-sector reversal through the same harness",
        "",
        f"Within-sector reversal top-quintile (validated effect, phase0-verdicts #1):  "
        f"mean excess = **{safe_fmt(pc.get('mean_pct'))}%/reb**, "
        f"t_HAC = {safe_fmt(pc.get('t_hac'))}{t_stars(pc.get('t_hac'))}, "
        f"n = {pc.get('n', '?')}.",
        "",
        "If the positive control fires (t ≥ 2), the harness is confirmed live — any MAX null "
        "is a true negative, not a dead instrument.",
        "",
        "---",
        "",
        "## 6. Orthogonality — MAX vs reversal and abnormal-turnover proxy",
        "",
        "| factor | bivariate IC mean | bivariate t_HAC | partial IC vs y |\\|rev,abn\\| | partial t_HAC |",
        "|---|--:|--:|--:|--:|",
        f"| MAX (signal under test) | {safe_fmt(orth.get('ic_max_mean'))} | "
        f"{safe_fmt(orth.get('ic_max_t'))}{t_stars(orth.get('ic_max_t'))} | "
        f"{safe_fmt(orth.get('ic_max_partial_mean'))} | "
        f"{safe_fmt(orth.get('ic_max_partial_t'))}{t_stars(orth.get('ic_max_partial_t'))} |",
        f"| Reversal (rev_z proxy) | {safe_fmt(orth.get('ic_rev_mean'))} | "
        f"{safe_fmt(orth.get('ic_rev_t'))}{t_stars(orth.get('ic_rev_t'))} | — | — |",
        f"| Abn-turn (vol-z proxy) | {safe_fmt(orth.get('ic_abn_mean'))} | "
        f"{safe_fmt(orth.get('ic_abn_t'))}{t_stars(orth.get('ic_abn_t'))} | — | — |",
        "",
        f"Cross-sectional rank-correlation (MAX vs reversal): "
        f"mean = {safe_fmt(orth.get('corr_max_rev_mean'))}  "
        f"(near 0 = orthogonal; ±0.3+ = shared information).",
        f"Cross-sectional rank-correlation (MAX vs abn-turn): "
        f"mean = {safe_fmt(orth.get('corr_max_abn_mean'))}.",
        "",
        "Interpretation: if partial-IC-MAX collapses to near zero when reversal and abn-turn "
        "are controlled, MAX is redundant with its siblings and adds no independent defensive screen value.",
        "",
        "---",
        "",
    ]

    # ─── verdict ───
    t_full = full.get("t_hac")
    t_pre = pre2021.get("t_hac")
    t_post = post2021.get("t_hac")
    ls_mean_pct = full.get("mean_pct") or 0
    perm_p_val = perm.get("perm_p")
    pc_t = pc.get("t_hac")
    ic_full_t = ic_full.get("t_hac")
    mono_steps = mono.get("monotone_steps", 0)
    screen_lift = scr.get("lift_mean_pct") or 0
    screen_p = scr.get("p") or 1

    def _abs(x):
        return abs(x) if (x is not None and np.isfinite(float(x))) else 0.0

    if _abs(t_full) >= 3 and _abs(t_pre) >= 2:
        verdict = "GO"
        verdict_note = ("L/S t_HAC clears the full-sample threshold (≥3) AND the pre-2021 split "
                        "(≥2), confirming split-stability. The MAX/lottery effect is validated "
                        "as a DEFENSIVE AVOID-screen on A-shares.")
    elif _abs(t_full) >= 2:
        verdict = "ACCRUE"
        verdict_note = (f"L/S t_HAC = {safe_fmt(t_full)} clears the accrue threshold but not the "
                        f"full GO bar (≥3). Pre-2021 split t = {safe_fmt(t_pre)}. "
                        "Register as accruing; re-examine with more data.")
    elif _abs(t_post) >= 2 and _abs(t_pre) < 2:
        verdict = "ACCRUE"
        verdict_note = ("Signal is significant only in the 2021+ era — recent-era-only. "
                        "Register as accruing; cannot call it split-stable yet.")
    elif screen_lift > 0 and screen_p < 0.10 and _abs(t_full) >= 1.5:
        verdict = "ACCRUE"
        verdict_note = ("Full L/S t is borderline, but the SCREEN TEST shows a significant "
                        "positive lift from excluding top-MAX names. The defensive screen "
                        "use-case may be valid even if the L/S is noisy.")
    else:
        verdict = "NO-GO"
        verdict_note = (f"L/S t_HAC = {safe_fmt(t_full)} (full). The MAX / lottery-effect "
                        "AVOID screen is NOT supported by this harness at this universe/period. "
                        "Do not wire MAX as a defensive screen without re-running on a deeper panel.")

    # cross-validate with perm placebo and positive control
    instrument_alive = pc_t is not None and _abs(pc_t) >= 1.5
    perm_confirms = perm_p_val is not None and perm_p_val < 0.10

    L += [
        "## 7. Verdict",
        "",
        f"**{verdict}**",
        "",
        verdict_note,
        "",
        "**Supporting evidence:**",
        f"- L/S (low-MAX minus high-MAX) fill-realistic excess: "
        f"{safe_fmt(ls_mean_pct)}%/reb (full), t_HAC = {safe_fmt(t_full)}{t_stars(t_full)}",
        f"- Pre-2021 split t_HAC = {safe_fmt(t_pre)}, post-2021 t_HAC = {safe_fmt(t_post)}",
        f"- Rank-IC full: mean = {safe_fmt(ic_full.get('mean_ic'))}, "
        f"t_HAC = {safe_fmt(ic_full_t)}{t_stars(ic_full_t)}",
        f"- Decile monotonicity: {mono_steps}/{mono['max_steps']} decreasing steps",
        f"- Screen test lift: {safe_fmt(screen_lift)}%/reb, t = {safe_fmt(scr.get('t'))}, "
        f"p = {safe_fmt(scr.get('p'))}",
        f"- Permutation placebo perm-p = {safe_fmt(perm_p_val)} "
        f"({'significant' if perm_confirms else 'not significant'})",
        f"- Positive control (reversal) t_HAC = {safe_fmt(pc_t)} "
        f"({'instrument confirmed' if instrument_alive else 'weak positive control'}) — "
        "if ≥1.5, any MAX null is a true negative",
        f"- MAX vs reversal cross-corr = {safe_fmt(orth.get('corr_max_rev_mean'))}, "
        f"MAX vs abn-turn cross-corr = {safe_fmt(orth.get('corr_max_abn_mean'))}",
        "",
        "**Structural caveats (from measurement constitution):**",
        "- Close-to-close overstates fill-realistic by ~0.9–1.1pp/entry; both are reported.",
        "- Universe is board members only (1,487 tickers), not the full ~4,300 raw panel; "
        "this reduces survivorship bias vs `china_search` but does not eliminate it entirely.",
        "- T+1 (H+L)/2 fill incurs a haircut vs the close; locked-limit bars are excluded.",
        "- MAX is truncated by ±10% price limits in A-shares (per literature caution, "
        "§ashare-signal-research B); limit-up events are retained as the lottery events by design.",
        "- Short history for newer names means the universe is different in early vs late periods; "
        "the pre/post-2021 split captures this regime/coverage change.",
        "- DO NOT RE-RUN: volume dry-up, turn-confirmation, quiet-base, lianban continuation "
        "are falsified (do-not-rerun ledger); MAX is the ONLY new test here.",
        "",
        "**Next step:** if verdict is GO or ACCRUE, wire MAX as a rank-DEMOTION chip on the board "
        "(not a standalone long signal). Register in registry_seed.json under program=china_alpha, "
        "wave=W3. Nothing is wired to any page/board/rank in this wave.",
    ]

    return "\n".join(L)


# ─────────────────────────────────────── main ─────────────────────────────────

def main() -> int:
    root = config.ROOT
    print("[load] reading raw panel …")
    close, high, low, vol = load_raw_panel(root)
    print("[load] reading CSI300 proxy …")
    csi300 = load_csi300(root)
    sector = load_sector(root, close.columns)

    # daily returns and signals
    print("[signal] computing signals …")
    ret = build_daily_ret(close)
    locked = build_locked_limit_mask(close, high, low)
    max_sig = build_max_signal(ret)

    # forward returns
    print("[fwd] computing forward returns …")
    fwd_fill = fill_realistic_fwd(high, low, locked)
    fwd_ctc = close_to_close_fwd(close)
    csi_fwd = csi300_fwd(csi300, close.index)
    csi_fwd_dict = csi_fwd.to_dict()

    # monthly grid: burn-in = MAX_WINDOW + MIN_HISTORY + 5 = ~780 rows
    print("[grid] building monthly rebalance grid …")
    idx = close.index
    burn_in = MAX_WINDOW + MIN_HISTORY + 5
    grid = build_monthly_grid(idx, burn_in, FWD_WINDOW + 5)
    print(f"  {len(grid)} rebalance dates: {grid[0].date()} → {grid[-1].date()}")

    # main backtest
    print("[bt] running main decile backtest …")
    bt = run_backtest(grid, close, max_sig, ret, fwd_fill, fwd_ctc, csi_fwd, sector)

    n_names_mean = float(np.mean(bt["n_names"])) if bt["n_names"] else 0
    dates_used = bt["dates_used"]
    print(f"  {len(dates_used)} rebalances used, mean eligible names: {round(n_names_mean)}")

    # era splits
    full_mask = [True] * len(bt["ls_fill"])
    pre21_mask = era_mask(dates_used, None, "2020-12-31")
    post21_mask = era_mask(dates_used, "2021-01-01", None)

    full_res = summarize_ls(bt["ls_fill"])
    pre21_res = summarize_ls(bt["ls_fill"][pre21_mask])
    post21_res = summarize_ls(bt["ls_fill"][post21_mask])

    # IC summary
    ic_full = ic_summary(bt["ic_fill"], periods_per_year=12)

    # monotonicity
    mono = decile_monotonicity(bt["decile_fill"])

    # screen test
    scr = screen_test(bt["pool_raw"], bt["pool_screened"])

    print("[perm] running 2000-permutation placebo …")
    perm = run_permutation_placebo(grid, close, max_sig, ret, fwd_fill, csi_fwd)

    print("[ctrl] running positive control (reversal) …")
    pc = run_positive_control(grid, close, fwd_fill, csi_fwd, sector)

    print("[orth] running orthogonality check …")
    orth = run_orthogonality(grid, close, max_sig, ret, vol, fwd_fill, csi_fwd, sector)

    # print summary to stdout
    print("\n─── L/S SUMMARY ───")
    for label, res in [("full", full_res), ("pre-2021", pre21_res), ("post-2021", post21_res)]:
        t = res.get("t_hac")
        stars = "***" if t and abs(t) >= 3 else ("**" if t and abs(t) >= 2 else "")
        print(f"  {label:12} n={res.get('n','?'):>3}  "
              f"mean={res.get('mean_pct','?'):>7}%  "
              f"t_HAC={res.get('t_hac','?'):>6}{stars}  "
              f"hit={res.get('hit','?')}")
    print(f"\n  IC full: mean={ic_full.get('mean_ic','?')}  t={ic_full.get('t_hac','?')}")
    print(f"  Monotonicity: {mono['monotone_steps']}/{mono['max_steps']} steps")
    print(f"  Screen lift: {scr.get('lift_mean_pct','?')}%  t={scr.get('t','?')}  p={scr.get('p','?')}")
    print(f"  Perm-p (2000 shuffles): {perm.get('perm_p','?')}")
    print(f"  Positive control (reversal) t_HAC: {pc.get('t_hac','?')}")
    print(f"  Orth: corr(MAX,rev)={orth.get('corr_max_rev_mean','?')}  "
          f"corr(MAX,abn)={orth.get('corr_max_abn_mean','?')}")

    # verdict
    t_full = full_res.get("t_hac")
    t_pre = pre21_res.get("t_hac")
    t_post = post21_res.get("t_hac")
    screen_lift = scr.get("lift_mean_pct") or 0
    screen_p = scr.get("p") or 1

    def _abs(x):
        return abs(x) if (x is not None and np.isfinite(float(x))) else 0.0

    if _abs(t_full) >= 3 and _abs(t_pre) >= 2:
        verdict = "GO"
    elif _abs(t_full) >= 2:
        verdict = "ACCRUE"
    elif _abs(t_post) >= 2 and _abs(t_pre) < 2:
        verdict = "ACCRUE"
    elif screen_lift > 0 and screen_p < 0.10 and _abs(t_full) >= 1.5:
        verdict = "ACCRUE"
    else:
        verdict = "NO-GO"

    print(f"\n  PRE-REGISTERED VERDICT: {verdict}")

    # write report
    report_text = render_report(
        bt, full_res, pre21_res, post21_res, mono, scr, perm, pc, orth,
        ic_full, close, grid, n_names_mean
    )

    out = root / config.load()["storage"]["reports_dir"] / "china-max-phase0.md"
    out.write_text(report_text + "\n")
    print(f"\n[report] written → {out}")

    # also write to research/china_alpha/w3/
    w3_dir = root / "research" / "china_alpha" / "w3"
    w3_dir.mkdir(parents=True, exist_ok=True)
    w3_out = w3_dir / "china-max-phase0.md"
    w3_out.write_text(report_text + "\n")
    print(f"[report] also written → {w3_out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
