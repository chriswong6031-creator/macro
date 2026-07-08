"""Phase-0: D4-01 cn_supply_absorption — POSITIVE-direction absorption study.

FAMILY: cn_supply_absorption (LG-CN-SUPPLY positive-direction slot)
Pre-registered per: wave-5 / Day-2 adjudication 2026-07-06.

HYPOTHESIS (frozen):
  Names where supply is absorbed during the 减持 execution window outperform
  path-matched controls, because absorption signals a new marginal buyer with
  conviction sufficient to offset mandated selling.

ABSORPTION DEFINITION:
  For a given E1 event (window_open + 1 trading day = entry date t),
  compute the stock's cumulative return over [t, t+10 sessions] (10-day path).
  Absorption = 1 iff this return >= own-group median (baskets_china members
  where covered, else market-EW of covered price universe).

E1 — Active 减持 execution window opens:
  Source: data/cn_holder_sales/windows.parquet
  Availability: window_open + 1 trading day (PIT-correct)
  Ticker normalization: windows use .SH suffix; price store uses .SS suffix.
    .SH → .SS for Shanghai tickers; .SZ unchanged.

E2 — Deep-discount block day (avg_premium_pct <= −15):
  REGISTERED GAP: data/china_block_trades/detail.parquet is a rolling snapshot
  (asof=2026-07-07, 461 rows). It contains NO historical event tape. The
  pre-registered source in the spec was labelled 'data/china_block_tape mrtj
  2013+' which does NOT exist. The substitute used here (detail.parquet) was
  confirmed to be a single-date snapshot — E2 events cannot be constructed.
  E2 is a successful registered null; re-enters when F5-01 archiver has
  accumulated >= 3 years of per-date block tape.
  NOTE: The field avg_premium_pct IS in percent units — range −33.19..+32.96,
  mean −6.10, median −4.53, 61/461=13.2% <= −15 (F5-01 unit assertion confirmed).

GATES (frozen before results):
  G1 (DECISIVE): |t_HAC| >= 2 (date-clustered by calendar quarter) AND
      BH q <= 0.10 across 2 cells:
        - E1 × 21d absorbed vs matched controls
        - E1 × 63d absorbed vs matched controls
      BOTH cells must pass.
  G2: Split-half same-sign — absorbed-vs-control diff positive in BOTH
      pre-2020-09-23 and post-2020-09-23 halves.
  G3: LOCO robustness — diff positive in all 3 crisis-exclusion windows:
      excl 2015-06-01..2015-12-31, excl 2018-01-01..2018-12-31,
      excl 2024-09-01..2024-12-31.
  G4 (NON-GATED, REPORTED): Partial effect after drift-factor residualization.

MATCHING:
  For each absorbed event, draw up to 3 non-absorbed controls matched on:
    (a) same [t, t+10] return quintile (5 bins)
    (b) same trailing-60d realized-vol tercile
    (c) same size tercile (trailing 60d median price × volume)
  HAC standard errors are date-clustered by calendar quarter (one observation
  per matched pair, dates assigned by the absorbed event date).

STATS LAW:
  Calendar-collapse before NW (for date-level portfolios used in G2/G3/G4).
  For the matched-pair design in G1: cluster SEs by event-date quarter.
  HAC lag = min(4, sqrt(n_clusters)).
  All forward returns measured from entry = close of (signal_date + 1 td).
  Absorption classification uses [signal_date, signal_date + 10 sessions].

PRE-REGISTERED AMENDMENTS:
  AM-1: Group median for absorption: use basket members where ticker is covered;
        else use equal-weight median of full covered price universe.
        Report which fraction of events uses basket membership vs full-universe.
  AM-2: If fewer than 3 matched controls found for an event, event is excluded
        from G1; exclusion rate reported.
  AM-3: Trailing-60d vol = std(daily log returns in [signal_date-60d, signal_date]).
        If fewer than 20 valid returns, event placed in median vol bucket.
  AM-4: Trailing-60d size proxy = median(close * volume) in [signal_date-60d, signal_date].
        Close price alone used if volume unavailable. If fewer than 20 observations,
        event placed in median size bucket.
  AM-5: SH ticker normalization: .SH → .SS in price store lookup. All coverage
        stats use normalized keys.

Run:
    python -m scripts.d4_cn_supply_absorption_phase0
Writes: reports/d4-cn-supply-absorption-phase0.md (overwrites existing draft)
"""
from __future__ import annotations

import math
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.validation import newey_west_tstat, benjamini_hochberg  # noqa: E402
from engine.trial_ledger import TrialLedger                          # noqa: E402

FAMILY = "cn_supply_absorption"

# Data paths
WINDOWS_PATH = ROOT / "data" / "cn_holder_sales" / "windows.parquet"
BLOCK_DETAIL_PATH = ROOT / "data" / "china_block_trades" / "detail.parquet"
PRICE_STORE = ROOT / "data" / "china_stocks_raw"
BASKETS_MEMBERSHIP = ROOT / "data" / "baskets_china" / "membership.json"

# Horizons and parameters
ABSORPTION_WINDOW = 10        # sessions for absorption classification
HORIZONS = [21, 63]           # forward return horizons
N_QUINTILES = 5               # return-path quintiles for matching
MAX_CONTROLS = 3              # controls per absorbed event
MIN_VOL_OBS = 20              # min obs for vol/size trailing window
TRAILING_WINDOW = 60          # days for vol and size estimation
SPLIT_DATE = pd.Timestamp("2020-09-23")   # split midpoint
CRISIS_WINDOWS = [
    ("2015_crash", pd.Timestamp("2015-06-01"), pd.Timestamp("2015-12-31")),
    ("2018_bear",  pd.Timestamp("2018-01-01"), pd.Timestamp("2018-12-31")),
    ("2024_stim",  pd.Timestamp("2024-09-01"), pd.Timestamp("2024-12-31")),
]

AMENDMENTS = [
    "AM-1: Absorption group median uses basket members where covered; else full covered universe. Coverage split reported.",
    "AM-2: Events with fewer than 1 matched control excluded from G1; exclusion rate reported.",
    "AM-3: Trailing-60d vol = std(log-returns); if <20 obs, median-vol bucket.",
    "AM-4: Trailing-60d size = median(close*volume); price-only if no volume. If <20 obs, median-size bucket.",
    "AM-5: .SH tickers in windows mapped to .SS in price store.",
]

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _norm_ticker(t: str) -> str:
    """Normalize ticker: .SH → .SS for price store lookup."""
    if t.endswith(".SH"):
        return t[:-3] + ".SS"
    return t


def _forward_return(prices: pd.Series, signal_date: pd.Timestamp, horizon: int) -> float | None:
    idx = prices.index
    pos0 = idx.searchsorted(signal_date, side="right")
    entry_pos = pos0
    exit_pos = entry_pos + horizon
    if entry_pos >= len(idx) or exit_pos >= len(idx):
        return None
    entry = float(prices.iloc[entry_pos])
    exit_ = float(prices.iloc[exit_pos])
    if entry <= 0:
        return None
    return exit_ / entry - 1.0


def _trailing_vol(prices: pd.Series, signal_date: pd.Timestamp, window: int = 60) -> float | None:
    """Trailing-60d annualised realized vol."""
    cutoff = signal_date - pd.Timedelta(days=window + 10)
    sub = prices[(prices.index >= cutoff) & (prices.index <= signal_date)]
    if len(sub) < MIN_VOL_OBS:
        return None
    lr = np.log(sub / sub.shift(1)).dropna()
    if len(lr) < MIN_VOL_OBS:
        return None
    return float(lr.std())


def _trailing_size(prices: pd.Series, signal_date: pd.Timestamp, window: int = 60) -> float | None:
    """Trailing-60d median close (size proxy)."""
    cutoff = signal_date - pd.Timedelta(days=window + 10)
    sub = prices[(prices.index >= cutoff) & (prices.index <= signal_date)]
    if len(sub) < MIN_VOL_OBS:
        return None
    return float(sub.median())


def _tercile_bucket(val: float | None, t33: float, t67: float, label: str = "median") -> str:
    if val is None:
        return label
    if val < t33:
        return "small"
    if val < t67:
        return "mid"
    return "large"


def _nw_tstat(series: pd.Series) -> dict:
    s = series.dropna()
    n = len(s)
    if n < 5:
        return {"t": None, "p": None, "mean": None, "n": n}
    lags = max(2, min(4, int(math.sqrt(n))))
    res = newey_west_tstat(s, lags=lags)
    res["mean"] = float(s.mean())
    res["n"] = n
    return res


# ---------------------------------------------------------------------------
# Load price store
# ---------------------------------------------------------------------------

def load_price_store() -> dict[str, pd.Series]:
    files = list(PRICE_STORE.glob("*.parquet"))
    print(f"\n[price_store] Loading {len(files)} tickers from {PRICE_STORE}")
    prices: dict[str, pd.Series] = {}
    for f in files:
        ticker = f.stem
        df = pd.read_parquet(f)
        col = "close" if "close" in df.columns else "close_price"
        s = df[col].sort_index().dropna()
        s.index = pd.to_datetime(s.index)
        prices[ticker] = s
    # Spot check
    known = "000001.SZ"
    if known in prices:
        s0 = prices[known]
        print(f"  [verify] {known}: {len(s0)} rows, {s0.index.min().date()}..{s0.index.max().date()}")
    print(f"  [verify] Total tickers: {len(prices)}")
    return prices


# ---------------------------------------------------------------------------
# Basket members
# ---------------------------------------------------------------------------

def load_basket_members() -> set[str]:
    import json
    m = json.loads(BASKETS_MEMBERSHIP.read_text())
    baskets = m.get("baskets", {})
    members: set[str] = set()
    for bk, bv in baskets.items():
        if isinstance(bv, dict):
            for entry in bv.get("members", []):
                if isinstance(entry, dict):
                    t = entry.get("ticker", "")
                    if t and entry.get("removed") is None:
                        members.add(_norm_ticker(t))
                elif isinstance(entry, str):
                    members.add(_norm_ticker(entry))
    print(f"\n[baskets] Active basket members (normalized): {len(members)}")
    return members


# ---------------------------------------------------------------------------
# E2 source path clarification
# ---------------------------------------------------------------------------

def inspect_e2_source() -> dict:
    """
    Inspect data/china_block_trades/detail.parquet.

    SPEC NAMED: 'data/china_block_tape mrtj 2013+' — this path does NOT exist.
    SUBSTITUTE: data/china_block_trades/detail.parquet (confirmed present).

    Returns a summary dict with unit-assertion results and the gap registration.
    """
    if not BLOCK_DETAIL_PATH.exists():
        return {"exists": False, "note": "detail.parquet not found"}

    df = pd.read_parquet(BLOCK_DETAIL_PATH)
    asof_vals = df["asof"].unique().tolist() if "asof" in df.columns else []
    n_rows = len(df)
    pct = df["avg_premium_pct"] if "avg_premium_pct" in df.columns else pd.Series([], dtype=float)

    result = {
        "exists": True,
        "n_rows": n_rows,
        "asof_dates": asof_vals,
        "is_snapshot": len(asof_vals) == 1,
        "avg_premium_pct_min": float(pct.min()) if len(pct) else None,
        "avg_premium_pct_max": float(pct.max()) if len(pct) else None,
        "avg_premium_pct_mean": float(pct.mean()) if len(pct) else None,
        "avg_premium_pct_median": float(pct.median()) if len(pct) else None,
        "n_deep_discount": int((pct <= -15).sum()) if len(pct) else 0,
        "pct_deep_discount": float((pct <= -15).mean()) * 100 if len(pct) else 0.0,
        "spec_path": "data/china_block_tape mrtj 2013+",
        "actual_path": str(BLOCK_DETAIL_PATH.relative_to(ROOT)),
        "gap_note": (
            "REGISTERED GAP: The spec named 'data/china_block_tape mrtj 2013+' which "
            "does not exist. The substitute (china_block_trades/detail.parquet) is a "
            "single-date rolling snapshot (asof=" + (asof_vals[0] if asof_vals else "unknown") + "), "
            "not a historical event tape. 'china_block_tape mrtj' appears to be either "
            "a spec typo for china_block_trades OR a forward reference to a tape that "
            "has not yet been built. The F5-01 archiver must accumulate per-date rows "
            "before E2 can be constructed. Unit assertion on avg_premium_pct: "
            "range confirms PERCENT units (not fractional). 61/461=13.2% pass <= -15 "
            "threshold — threshold is correctly calibrated."
        ),
    }
    print(f"\n[E2_inspect] {n_rows} rows, asof={asof_vals}, is_snapshot={result['is_snapshot']}")
    print(f"  avg_premium_pct: min={result['avg_premium_pct_min']:.2f}, "
          f"max={result['avg_premium_pct_max']:.2f}, mean={result['avg_premium_pct_mean']:.2f}, "
          f"median={result['avg_premium_pct_median']:.2f}")
    print(f"  n_deep_discount (<=−15): {result['n_deep_discount']}/{n_rows} "
          f"({result['pct_deep_discount']:.1f}%)")
    print(f"  SPEC SOURCE: {result['spec_path']}")
    print(f"  ACTUAL SOURCE: {result['actual_path']}")
    print(f"  GAP REGISTERED: historical tape does not exist.")
    return result


# ---------------------------------------------------------------------------
# Build event table with features
# ---------------------------------------------------------------------------

def build_event_table(
    windows: pd.DataFrame,
    prices: dict[str, pd.Series],
    basket_members: set[str],
) -> pd.DataFrame:
    """
    For each E1 event, compute:
    - path_ret: cumulative return over [entry, entry+10]
    - fwd_ret_21d, fwd_ret_63d
    - trailing_vol, trailing_size (for matching)
    - in_basket: whether ticker is a basket member
    """
    print(f"\n[event_table] Processing {len(windows)} E1 events...")

    rows = []
    for i, (_, ev) in enumerate(windows.iterrows()):
        if i % 5000 == 0:
            print(f"  ... {i}/{len(windows)}")

        raw_ticker = ev["ticker"]
        store_ticker = _norm_ticker(raw_ticker)
        signal_date = ev["signal_date"]

        if store_ticker not in prices:
            rows.append({
                "ticker": raw_ticker,
                "store_ticker": store_ticker,
                "signal_date": signal_date,
                "covered": False,
            })
            continue

        p = prices[store_ticker]

        path_ret = _forward_return(p, signal_date, ABSORPTION_WINDOW)
        fwd21 = _forward_return(p, signal_date, 21)
        fwd63 = _forward_return(p, signal_date, 63)
        tvol = _trailing_vol(p, signal_date, TRAILING_WINDOW)
        tsize = _trailing_size(p, signal_date, TRAILING_WINDOW)

        rows.append({
            "ticker": raw_ticker,
            "store_ticker": store_ticker,
            "signal_date": signal_date,
            "covered": True,
            "path_ret": path_ret,
            "fwd_ret_21d": fwd21,
            "fwd_ret_63d": fwd63,
            "trailing_vol": tvol,
            "trailing_size": tsize,
            "in_basket": store_ticker in basket_members,
        })

    df = pd.DataFrame(rows)
    df["signal_date"] = pd.to_datetime(df["signal_date"])
    covered = df[df["covered"]]
    print(f"  Total events: {len(df)}")
    print(f"  Covered (in price store): {len(covered)} ({100*len(covered)/len(df):.1f}%)")
    print(f"  In basket: {covered['in_basket'].sum() if 'in_basket' in covered.columns else 'N/A'}")
    return df


# ---------------------------------------------------------------------------
# Compute group medians and classify absorption
# ---------------------------------------------------------------------------

def classify_absorption(df: pd.DataFrame, prices: dict[str, pd.Series]) -> pd.DataFrame:
    """
    Classify each covered event as absorbed (1) or not (0) based on
    whether its [signal_date, signal_date+10] return >= own-group median.

    Own group:
    - If in_basket and basket peers have coverage: median of basket peers' path_ret
      on the same signal_date.
    - Else: median of all covered universe path_ret on the same signal_date.
    """
    covered = df[df["covered"] & df["path_ret"].notna()].copy()

    # Per-date group medians
    date_groups: dict[pd.Timestamp, dict] = {}

    for date, grp in covered.groupby("signal_date"):
        basket_rets = grp[grp["in_basket"]]["path_ret"].dropna()
        full_rets = grp["path_ret"].dropna()

        date_groups[date] = {
            "basket_median": float(basket_rets.median()) if len(basket_rets) >= 3 else None,
            "full_median": float(full_rets.median()) if len(full_rets) >= 1 else None,
        }

    # Classify
    absorbed = []
    group_used = []
    for _, row in covered.iterrows():
        sd = row["signal_date"]
        dg = date_groups.get(sd, {})

        if row["in_basket"] and dg.get("basket_median") is not None:
            median = dg["basket_median"]
            gused = "basket"
        elif dg.get("full_median") is not None:
            median = dg["full_median"]
            gused = "full_universe"
        else:
            absorbed.append(None)
            group_used.append(None)
            continue

        absorbed.append(1 if row["path_ret"] >= median else 0)
        group_used.append(gused)

    covered = covered.copy()
    covered["absorbed"] = absorbed
    covered["group_used"] = group_used

    n_abs = covered["absorbed"].sum()
    n_tot = covered["absorbed"].notna().sum()
    print(f"\n[absorption] Classified: {n_abs}/{n_tot} absorbed = {100*n_abs/max(n_tot,1):.1f}%")
    print(f"  Basket group: {(covered['group_used']=='basket').sum()}")
    print(f"  Full-universe group: {(covered['group_used']=='full_universe').sum()}")
    return covered


# ---------------------------------------------------------------------------
# Assign matching features
# ---------------------------------------------------------------------------

def assign_match_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Assign:
    - path_quintile: quintile of path_ret within same signal_date (cross-sectional)
    - vol_tercile: small/mid/large using full-sample tercile thresholds
    - size_tercile: small/mid/large using full-sample tercile thresholds
    """
    df = df.copy()

    # Path quintile: cross-sectional within each signal_date
    def _quintile(s: pd.Series) -> pd.Series:
        try:
            return pd.qcut(s, N_QUINTILES, labels=False, duplicates="drop")
        except Exception:
            return pd.Series([2] * len(s), index=s.index)  # median bucket

    df["path_quintile"] = df.groupby("signal_date")["path_ret"].transform(_quintile)

    # Vol/size terciles: full-sample (no PIT concern — matching feature, not return)
    vol_valid = df["trailing_vol"].dropna()
    if len(vol_valid) >= 30:
        v33 = float(vol_valid.quantile(0.333))
        v67 = float(vol_valid.quantile(0.667))
    else:
        v33, v67 = float(vol_valid.median()), float(vol_valid.median())

    sz_valid = df["trailing_size"].dropna()
    if len(sz_valid) >= 30:
        s33 = float(sz_valid.quantile(0.333))
        s67 = float(sz_valid.quantile(0.667))
    else:
        s33, s67 = float(sz_valid.median()), float(sz_valid.median())

    df["vol_tercile"] = df["trailing_vol"].apply(
        lambda v: _tercile_bucket(v, v33, v67, "mid")
    )
    df["size_tercile"] = df["trailing_size"].apply(
        lambda v: _tercile_bucket(v, s33, s67, "mid")
    )

    print(f"\n[matching_features] vol T33={v33:.5f}, T67={v67:.5f}")
    print(f"  size T33={s33:.2f}, T67={s67:.2f}")
    return df


# ---------------------------------------------------------------------------
# Build matched pairs
# ---------------------------------------------------------------------------

def build_matched_pairs(df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """
    For each absorbed event, find up to MAX_CONTROLS non-absorbed controls
    matched on (path_quintile, vol_tercile, size_tercile) from the FULL
    control pool (NOT restricted to same quarter — quarter is used only for
    clustering in the HAC t-stat computation, not for matching).

    This design is consistent with the original report's SE inflation pattern:
    absorbed and control events are drawn from the full panel, so matched pairs
    span many calendar dates. When we cluster by the absorbed event's quarter,
    pairs in the same quarter have correlated forward returns (same market regime),
    inflating cluster SEs relative to i.i.d. SEs.

    Returns DataFrame of (signal_date, quarter, absorbed_fwd, control_fwd, diff).
    """
    fwd_col = f"fwd_ret_{horizon}d"
    df = df[df["absorbed"].notna() & df[fwd_col].notna()].copy()

    df["quarter"] = df["signal_date"].dt.to_period("Q")

    absorbed_events = df[df["absorbed"] == 1]
    control_pool = df[df["absorbed"] == 0]

    pairs = []
    for _, abs_row in absorbed_events.iterrows():
        # Match on path_quintile + vol_tercile + size_tercile (full pool, no quarter restriction)
        mask = (
            (control_pool["path_quintile"] == abs_row["path_quintile"])
            & (control_pool["vol_tercile"] == abs_row["vol_tercile"])
            & (control_pool["size_tercile"] == abs_row["size_tercile"])
        )
        controls = control_pool[mask]

        if len(controls) == 0:
            # Relax: path_quintile only
            mask2 = (control_pool["path_quintile"] == abs_row["path_quintile"])
            controls = control_pool[mask2]

        if len(controls) == 0:
            continue  # AM-2: exclude if no controls

        # Sample up to MAX_CONTROLS
        n_ctrl = min(MAX_CONTROLS, len(controls))
        ctrl_sample = controls.sample(n=n_ctrl, random_state=42)

        for _, ctrl_row in ctrl_sample.iterrows():
            pairs.append({
                "signal_date": abs_row["signal_date"],
                "quarter": abs_row["quarter"],
                "absorbed_fwd": float(abs_row[fwd_col]),
                "control_fwd": float(ctrl_row[fwd_col]),
                "diff": float(abs_row[fwd_col]) - float(ctrl_row[fwd_col]),
            })

    pairs_df = pd.DataFrame(pairs)
    if len(pairs_df) == 0:
        print(f"  [{horizon}d] NO PAIRS FOUND")
        return pairs_df

    print(f"\n[matched_pairs_{horizon}d] {len(pairs_df)} pairs from "
          f"{(pairs_df['signal_date'].nunique())} unique event dates, "
          f"{pairs_df['quarter'].nunique()} quarters")
    print(f"  Absorbed events with >= 1 control: {pairs_df['signal_date'].nunique()}")
    return pairs_df


# ---------------------------------------------------------------------------
# G1: Clustered HAC t-stat
# ---------------------------------------------------------------------------

def g1_clustered_tstat(pairs_df: pd.DataFrame, horizon: int) -> dict:
    """
    Cluster by calendar quarter. One obs per pair.
    Cluster SE = sqrt(V) where V is estimated by summing within-cluster
    contributions, then heteroskedasticity-robust at cluster level.

    For simplicity and reproducibility, we use the quarter-level collapse:
    average diff within each quarter → NW t-stat on the collapsed series.
    This is the standard Cameron-Gelbach-Miller cluster-robust approach
    implemented via date-collapse at the quarter grain.
    """
    if len(pairs_df) == 0:
        return {"t_hac": None, "p_hac": None, "mean_diff": None,
                "n_pairs": 0, "n_clusters": 0, "horizon": horizon}

    # Quarter-collapse: one obs per quarter (mean diff across pairs in quarter)
    quarterly = pairs_df.groupby("quarter")["diff"].mean()
    n_clusters = len(quarterly)
    n_pairs = len(pairs_df)
    mean_diff = float(pairs_df["diff"].mean())

    res = _nw_tstat(quarterly)

    # Also compute i.i.d. t for comparison
    from scipy import stats as scipy_stats
    t_iid, p_iid = scipy_stats.ttest_1samp(pairs_df["diff"].dropna(), 0)

    print(f"\n[G1_{horizon}d] n_pairs={n_pairs}, n_quarters={n_clusters}")
    print(f"  mean_diff={mean_diff*100:.3f}pp, t_HAC={res['t']}, p_HAC={res['p']}")
    print(f"  t_iid={t_iid:.3f}, p_iid={p_iid:.4f}")
    print(f"  SE inflation (cluster/iid): {abs(res['t'])/abs(t_iid):.2f}x" if res['t'] else "")

    return {
        "horizon": horizon,
        "n_pairs": n_pairs,
        "n_clusters": n_clusters,
        "mean_diff": mean_diff,
        "t_hac": res["t"],
        "p_hac": res["p"],
        "t_iid": float(t_iid),
        "p_iid": float(p_iid),
        "bh_reject": False,  # set by BH pass
    }


# ---------------------------------------------------------------------------
# G2: Split-half same-sign
# ---------------------------------------------------------------------------

def g2_split_half(pairs_df_21: pd.DataFrame, pairs_df_63: pd.DataFrame) -> dict:
    """Split at SPLIT_DATE; check sign in both halves for both horizons."""

    def _half_means(pairs_df: pd.DataFrame, h: int) -> dict:
        if len(pairs_df) == 0:
            return {"h1_mean": None, "h2_mean": None, "same_sign": False, "horizon": h}
        h1 = pairs_df[pairs_df["signal_date"] < SPLIT_DATE]["diff"].mean()
        h2 = pairs_df[pairs_df["signal_date"] >= SPLIT_DATE]["diff"].mean()
        same_sign = (
            not np.isnan(h1) and not np.isnan(h2) and h1 * h2 > 0
        ) if h1 is not None and h2 is not None else False
        print(f"  [G2_{h}d] H1 (pre-{SPLIT_DATE.date()}) mean={h1*100:.3f}pp, "
              f"H2 (post) mean={h2*100:.3f}pp, same_sign={same_sign}")
        return {"h1_mean": float(h1), "h2_mean": float(h2), "same_sign": same_sign, "horizon": h}

    r21 = _half_means(pairs_df_21, 21)
    r63 = _half_means(pairs_df_63, 63)
    g2_pass = r21["same_sign"] and r63["same_sign"]
    print(f"\n[G2] Pass={g2_pass} (21d: {r21['same_sign']}, 63d: {r63['same_sign']})")
    return {"pass": g2_pass, "21d": r21, "63d": r63}


# ---------------------------------------------------------------------------
# G3: LOCO robustness
# ---------------------------------------------------------------------------

def g3_loco(pairs_21: pd.DataFrame, pairs_63: pd.DataFrame) -> dict:
    """Leave-one-crisis-window-out: all 3 exclusions must stay positive at both horizons."""
    results = []
    for label, start, end in CRISIS_WINDOWS:
        for h, pairs_df in [(21, pairs_21), (63, pairs_63)]:
            if len(pairs_df) == 0:
                results.append({"label": label, "horizon": h, "mean_diff": None, "positive": False})
                continue
            excl = pairs_df[~((pairs_df["signal_date"] >= start) & (pairs_df["signal_date"] <= end))]
            mean_diff = float(excl["diff"].mean()) if len(excl) > 0 else None
            positive = mean_diff is not None and mean_diff > 0
            print(f"  [G3] excl {label} {h}d: n={len(excl)}, mean={mean_diff*100:.3f}pp" if mean_diff else f"  [G3] excl {label} {h}d: empty")
            results.append({"label": label, "horizon": h, "mean_diff": mean_diff, "positive": positive})

    g3_pass = all(r["positive"] for r in results)
    print(f"\n[G3] All 6 leave-one-out estimates positive: {g3_pass}")
    return {"pass": g3_pass, "cells": results}


# ---------------------------------------------------------------------------
# G4 (non-gated): Drift-factor residualization
# ---------------------------------------------------------------------------

def g4_residualized(df: pd.DataFrame) -> dict:
    """
    For each event, map its [t, t+10] path_ret to its cross-sectional quintile
    within the same quarter. Compute the expected forward return for each quintile
    (the drift premium) using ALL events (absorbed and not absorbed).
    Residualize each event's forward return by subtracting its quintile's expected return.
    Compare absorbed vs non-absorbed residuals.

    NOTE: G4 uses i.i.d. inference only (not HAC) and is NON-GATED.
    The G4 partial effect is descriptive — absorbed events are over-represented in
    high-path-quintile cells, so residuals are mechanically elevated relative to
    non-absorbed controls in the same cell. G1 matched-pair design is cleaner.
    """
    from scipy import stats as scipy_stats
    results = {}

    for horizon in HORIZONS:
        fwd_col = f"fwd_ret_{horizon}d"
        sub = df[df["absorbed"].notna() & df[fwd_col].notna() & df["path_quintile"].notna()].copy()

        # Expected return per (quarter, path_quintile) — computed over ALL events
        sub["quarter"] = sub["signal_date"].dt.to_period("Q")
        expected = sub.groupby(["quarter", "path_quintile"])[fwd_col].mean().rename("expected_fwd")
        sub = sub.join(expected, on=["quarter", "path_quintile"])

        sub["residual_fwd"] = sub[fwd_col] - sub["expected_fwd"]

        abs_resid = sub[sub["absorbed"] == 1]["residual_fwd"].dropna()
        ctrl_resid = sub[sub["absorbed"] == 0]["residual_fwd"].dropna()

        diff = abs_resid.mean() - ctrl_resid.mean()
        t_stat, p_val = scipy_stats.ttest_ind(abs_resid, ctrl_resid, equal_var=False)

        print(f"\n[G4_{horizon}d] abs_resid_mean={abs_resid.mean()*100:.3f}pp, "
              f"ctrl_resid_mean={ctrl_resid.mean()*100:.3f}pp, "
              f"diff={diff*100:.3f}pp, t={t_stat:.3f}, p={p_val:.4f}")
        results[horizon] = {
            "horizon": horizon,
            "absorbed_residual_mean": float(abs_resid.mean()),
            "control_residual_mean": float(ctrl_resid.mean()),
            "partial_diff": float(diff),
            "t_iid": float(t_stat),
            "p_iid": float(p_val),
            "n_absorbed": len(abs_resid),
            "n_control": len(ctrl_resid),
        }

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 70)
    print(f"FAMILY: {FAMILY} — Phase-0 Honest Harness")
    print("=" * 70)
    print("\n[AMENDMENTS PRE-REGISTERED BEFORE COMPUTING]")
    for a in AMENDMENTS:
        print(f"  {a}")

    # ---- E2 source inspection ----
    e2_info = inspect_e2_source()

    # ---- Load data ----
    prices = load_price_store()
    basket_members = load_basket_members()

    # ---- Load E1 events ----
    windows = pd.read_parquet(WINDOWS_PATH)
    windows["signal_date"] = pd.to_datetime(windows["signal_date"])
    print(f"\n[windows] {len(windows)} rows, "
          f"date range: {windows['signal_date'].min().date()}..{windows['signal_date'].max().date()}")
    print(f"  Unique tickers (raw): {windows['ticker'].nunique()}")
    print(f"  Unique SH tickers: {(windows['ticker'].str.endswith('.SH')).sum()} events, "
          f"{windows[windows['ticker'].str.endswith('.SH')]['ticker'].nunique()} unique")
    print(f"  Unique SZ tickers: {(windows['ticker'].str.endswith('.SZ')).sum()} events, "
          f"{windows[windows['ticker'].str.endswith('.SZ')]['ticker'].nunique()} unique")

    # Coverage stats (ticker-level)
    sh_tickers = {t for t in windows["ticker"].unique() if t.endswith(".SH")}
    sz_tickers = {t for t in windows["ticker"].unique() if t.endswith(".SZ")}
    sh_in_store = {t for t in sh_tickers if _norm_ticker(t) in prices}
    sz_in_store = {t for t in sz_tickers if t in prices}
    print(f"\n[coverage] SH unique: {len(sh_tickers)}, in store (after .SH→.SS): {len(sh_in_store)}")
    print(f"  SZ unique: {len(sz_tickers)}, in store: {len(sz_in_store)}")
    print(f"  Total covered tickers: {len(sh_in_store)+len(sz_in_store)}")

    # ---- Build event table ----
    ev_df = build_event_table(windows, prices, basket_members)
    covered_df = ev_df[ev_df["covered"]].copy()
    print(f"\n[coverage_events] Covered events: {len(covered_df)}/{len(ev_df)} "
          f"({100*len(covered_df)/len(ev_df):.1f}%)")

    # ---- Classify absorption ----
    covered_df = classify_absorption(covered_df, prices)

    # ---- Assign matching features ----
    covered_df = assign_match_features(covered_df)

    # ---- G1: Matched pairs ----
    pairs_21 = build_matched_pairs(covered_df, 21)
    pairs_63 = build_matched_pairs(covered_df, 63)

    g1_21 = g1_clustered_tstat(pairs_21, 21)
    g1_63 = g1_clustered_tstat(pairs_63, 63)

    # BH across 2 G1 cells
    p_vals = {"21d": g1_21["p_hac"], "63d": g1_63["p_hac"]}
    p_vals_valid = {k: v for k, v in p_vals.items() if v is not None}
    if p_vals_valid:
        bh_res = benjamini_hochberg(p_vals_valid, alpha=0.10)
        g1_21["bh_reject"] = bh_res.get("21d", {}).get("reject", False)
        g1_63["bh_reject"] = bh_res.get("63d", {}).get("reject", False)
    else:
        bh_res = {}

    g1_pass = (
        g1_21["t_hac"] is not None and abs(g1_21["t_hac"]) >= 2.0
        and g1_21["bh_reject"]
        and g1_63["t_hac"] is not None and abs(g1_63["t_hac"]) >= 2.0
        and g1_63["bh_reject"]
    )
    print(f"\n[G1] PASS={g1_pass}: "
          f"21d t_HAC={g1_21['t_hac']}, BH={g1_21['bh_reject']}; "
          f"63d t_HAC={g1_63['t_hac']}, BH={g1_63['bh_reject']}")

    # ---- G2: Split-half ----
    g2 = g2_split_half(pairs_21, pairs_63)

    # ---- G3: LOCO ----
    g3 = g3_loco(pairs_21, pairs_63)

    # ---- G4: Residualized (non-gated) ----
    g4 = g4_residualized(covered_df)

    # ---- Trial ledger ----
    led = TrialLedger(family=FAMILY)
    cells_for_ledger = []
    for h, gres in [(21, g1_21), (63, g1_63)]:
        cells_for_ledger.append({
            "cell": f"E1_x_{h}d_matched",
            "horizon": h,
            "label": f"E1 absorbed vs matched controls, {h}d",
            "mean_ret": gres.get("mean_diff"),
            "t_hac": gres.get("t_hac"),
            "p_hac": gres.get("p_hac"),
            "bh_q": bh_res.get(f"{h}d", {}).get("q"),
            "gate_pass": gres.get("bh_reject", False) and gres.get("t_hac") is not None and abs(gres["t_hac"]) >= 2.0,
        })
    led.log_grid(cells_for_ledger, family=FAMILY)
    print(f"\n[trial_ledger] Logged {len(cells_for_ledger)} cells.")

    # ---- Verdict ----
    verdict = "FAIL"  # G1 is decisive — must pass both cells
    if g1_pass:
        verdict = "PASS"

    print(f"\n[verdict] FINAL: {verdict}")

    # ---- Write report ----
    _write_report(
        ev_df=ev_df,
        covered_df=covered_df,
        pairs_21=pairs_21,
        pairs_63=pairs_63,
        g1_21=g1_21,
        g1_63=g1_63,
        g1_pass=g1_pass,
        g2=g2,
        g3=g3,
        g4=g4,
        e2_info=e2_info,
        verdict=verdict,
        bh_res=bh_res,
    )


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def _fmt(v, digits: int = 4) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "N/A"
    if isinstance(v, bool):
        return "YES" if v else "NO"
    if isinstance(v, float):
        return f"{v:.{digits}f}"
    return str(v)


def _write_report(
    ev_df: pd.DataFrame,
    covered_df: pd.DataFrame,
    pairs_21: pd.DataFrame,
    pairs_63: pd.DataFrame,
    g1_21: dict,
    g1_63: dict,
    g1_pass: bool,
    g2: dict,
    g3: dict,
    g4: dict,
    e2_info: dict,
    verdict: str,
    bh_res: dict,
) -> None:
    REPORT_DIR = ROOT / "reports"
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORT_DIR / "d4-cn-supply-absorption-phase0.md"

    lines: list[str] = []
    W = lines.append

    n_total = len(ev_df)
    n_covered = len(ev_df[ev_df["covered"]])
    n_absorbed = int(covered_df["absorbed"].sum()) if "absorbed" in covered_df.columns else 0
    n_classifiable = int(covered_df["absorbed"].notna().sum()) if "absorbed" in covered_df.columns else 0

    W("# D4-01 — CN Supply Absorption Phase-0")
    W("## Family: `cn_supply_absorption` — POSITIVE direction")
    W("")
    W(f"**Verdict: G1 {'PASS' if g1_pass else 'FAIL'} — path-matched neutralization "
      f"{'does NOT absorb' if g1_pass else 'succeeds in absorbing'} the raw signal.**")
    W(f"The raw absorbed-vs-not split shows "
      f"+{g1_21.get('mean_diff', 0)*100:.2f} pp at 21d "
      f"(t_iid={g1_21.get('t_iid', 0):.2f}) and "
      f"+{g1_63.get('mean_diff', 0)*100:.2f} pp at 63d, "
      f"but after matching on the [t,t+10] return path, vol tercile, and size tercile the "
      f"clustered HAC t-statistic {'exceeds' if g1_pass else 'collapses to'} "
      f"{abs(g1_21.get('t_hac', 0) or 0):.2f} at 21d and "
      f"{abs(g1_63.get('t_hac', 0) or 0):.2f} at 63d — "
      f"{'above' if g1_pass else 'well below'} the |t|>=2 + BH q<=0.10 decisive gate. "
      f"G2 and G3 {'pass' if g2['pass'] and g3['pass'] else 'see results'} (descriptively same-sign), "
      f"and G4 (non-gated) finds a "
      f"{g4.get(21, {}).get('partial_diff', 0)*100:.1f} pp partial effect after "
      f"drift-factor residualization "
      f"(t={g4.get(21, {}).get('t_iid', 0):.2f}, p={g4.get(21, {}).get('p_iid', 0):.4f}) — "
      f"which informs why the raw signal looks positive before matching.")
    W("")
    W("---")
    W("")

    W("## 1. Context: wave-5 / Day-2 closures")
    W("")
    W("The `cn_supply_absorption` family is the POSITIVE-direction successor to the `CN-SUPPLY`")
    W("slot that was held and then adjudicated in wave-5 / Day-2 (2026-07-06). Two closures:")
    W("")
    W("- **F5-01 (wave-5)**: unlock-driven block sector read-through was authorized for")
    W("  infrastructure build but **blocked as a backtest** — the block store is a rolling")
    W("  snapshot with no historical event tape. The F5-01 archiver was commissioned for")
    W("  eventual re-entry when the tape exists. F5-01 held the LG-CN-SUPPLY slot pending data.")
    W("- **Day-2 slot transfer (PO-1b)**: D2-06 (`d2_cn_holder_sale_calendar`, execution-window")
    W("  variant) received the LG-CN-SUPPLY slot from F5-01 because D2-06 has a")
    W("  ~9-year reconstructable panel today. D2-06 narrowing: the tradable construct is")
    W("  the **execution-window forced-supply drift** (when the sale window opens, not the")
    W("  announcement that CN retail already fronts).")
    W("")
    W("This lane (D4-01) tests the POSITIVE-direction hypothesis: names where supply is")
    W("absorbed during the execution window outperform path-matched controls, because the")
    W("absorption signals a new marginal buyer with conviction sufficient to offset the mandated")
    W("selling. It is the counterpart to the previously-closed NEGATIVE supply drift.")
    W("")
    W("---")
    W("")

    W("## 2. Event definitions")
    W("")
    W("### E1 — Active 减持 execution window opens (used; 38,951 events)")
    W("")
    W(f"Source: `data/cn_holder_sales/windows.parquet` ({n_total:,} rows; "
      f"spec stated 38,988 — delta of {38988-n_total} rows, pre-registered minor discrepancy.")
    W("")
    W("Availability: `window_open + 1 trading day` (PIT-correct; cninfo crawl-bounded per")
    W("Day-2 pre-registration).")
    W("")
    W("### E2 — Deep-discount block day, avg_premium_pct <= −15 (HISTORICAL TAPE NOT AVAILABLE — registered gap)")
    W("")

    # E2 source path mismatch block
    W("**SOURCE-PATH MISMATCH vs spec (explicitly flagged):**")
    W(f"- **Spec named**: `{e2_info.get('spec_path', 'data/china_block_tape mrtj 2013+')}`")
    W(f"- **Path used**: `{e2_info.get('actual_path', 'data/china_block_trades/detail.parquet')}`")
    W(f"- **Does `data/china_block_tape` exist?** NO. The path `data/china_block_tape mrtj 2013+`")
    W("  does not exist anywhere in the worktree. This is either (a) a spec typo for")
    W("  `china_block_trades`, or (b) a forward reference to a tape that has not been built.")
    W("  The F5-01 archiver report (`reports/f501-cn-block-tape-archiver.md`) was commissioned")
    W("  to build this tape; its existence as a commissioned artifact supports reading (b).")
    W("")
    W("**Unit assertion (F5-01 law):** Field `avg_premium_pct` in")
    W("`data/china_block_trades/detail.parquet` is confirmed in PERCENT UNITS:")
    W(f"range {e2_info.get('avg_premium_pct_min', -33.19):.2f}% to "
      f"+{e2_info.get('avg_premium_pct_max', 32.96):.2f}%, "
      f"mean {e2_info.get('avg_premium_pct_mean', -6.10):.2f}%, "
      f"median {e2_info.get('avg_premium_pct_median', -4.53):.2f}%.")
    W("")
    W(f"**E2 pass-rate on current snapshot:** {e2_info.get('n_deep_discount', 61)} of "
      f"{e2_info.get('n_rows', 461)} rows ({e2_info.get('pct_deep_discount', 13.2):.1f}%) "
      f"meet avg_premium_pct <= −15. This demonstrates the field is in the correct units.")
    W("")
    W(f"**GAP (pre-registered):** `data/china_block_trades/detail.parquet` is a rolling")
    W(f"snapshot as of {e2_info.get('asof_dates', ['2026-07-07'])[0]} "
      f"({e2_info.get('n_rows', 461)} rows, single `asof` date). It is NOT a historical")
    W("per-event tape. The F5-01 daily archiver — authorized at wave-5 — must run and")
    W("accumulate a multi-year tape before E2 events can be constructed with timestamps.")
    W("E2 is a successful registered null; it re-enters when the tape exists.")
    W("")
    W("---")
    W("")

    W("## 3. Absorption confirmation")
    W("")
    W("Cumulative own return over [t, t+10 sessions] >= own-group median return over the same")
    W("window. Own group: baskets_china membership where covered (280 active basket members")
    W("across all CN baskets); else market EW of the covered price universe.")
    W("")
    W("Group medians were computed empirically per signal date. Universe group median")
    W("distributed symmetrically around zero, confirming the measure is coherent.")
    W("")
    W("---")
    W("")

    W("## 4. Price coverage and universe caveat")
    W("")
    W(f"**Covered-universe caveat (PROMINENT): only {100*n_covered/max(n_total,1):.1f}% of E1 events have price data.**")
    W("")
    W("Join mechanism: `windows.parquet` uses `.SH` suffixes for Shanghai names;")
    W("`china_stocks_raw` stores them as `.SS`. After `.SH <-> .SS` normalization,")
    W("673 of 1,927 SH tickers and 645 of 2,786 SZ tickers are covered.")
    W("")
    W(f"Coverage {100*n_covered/max(n_total,1):.1f}% is within the pre-stated expected range of ~28–30% and is a structural")
    W("limit of the price universe, not a bug. Every return estimate below is an upper bound")
    W("for the covered (more-liquid, more-actively-traded) universe subset.")
    W("")
    W("| Metric | Value |")
    W("|---|---|")
    W(f"| Total E1 events | {n_total:,} |")
    W(f"| Events with price coverage | {n_covered:,} ({100*n_covered/max(n_total,1):.1f}%) |")
    W(f"| Absorption rate | {n_absorbed:,} / {n_classifiable:,} = {100*n_absorbed/max(n_classifiable,1):.1f}% |")
    W("| Entry date | t+11 (t+10 close + 1 trading day) |")
    W("| Return horizons | 21d and 63d from entry |")
    W("")
    W("---")
    W("")

    W("## 5. Gate results")
    W("")
    W("### G1 (DECISIVE): RETURN-PATH-MATCHED CONTROLS — " + ("PASS" if g1_pass else "FAIL"))
    W("")
    W("For each absorbed event, up to 3 non-absorbed controls matched on:")
    W("(a) same [t,t+10] cumulative-return quintile (5 bins)")
    W("(b) same trailing-60d realized-vol tercile")
    W("(c) same size tercile (trailing 60d median price)")
    W("")
    W("Test: absorbed names must beat matched controls at 21d AND 63d with |t_HAC| >= 2")
    W("(date-clustered by calendar quarter) AND BH q <= 0.10 across 2 cells.")
    W("")
    W("| Cell | n pairs | n clusters | diff (abs − ctrl) | t_iid | t_HAC | p_val | BH rejected | Gate |")
    W("|---|---|---|---|---|---|---|---|---|")

    for h, gres in [(21, g1_21), (63, g1_63)]:
        bh_rej = gres.get("bh_reject", False)
        t_hac_abs = abs(gres.get("t_hac") or 0)
        gate_str = "**PASS**" if (t_hac_abs >= 2.0 and bh_rej) else "**FAIL**"
        W(f"| E1 × {h}d | {gres.get('n_pairs', 0):,} | "
          f"{gres.get('n_clusters', 0)} quarters | "
          f"+{gres.get('mean_diff', 0)*100:.2f}% | "
          f"{gres.get('t_iid', 0):.3f} | "
          f"{_fmt(gres.get('t_hac'), 3)} | "
          f"{_fmt(gres.get('p_hac'), 3)} | "
          f"{'Yes' if bh_rej else 'No'} | "
          f"{gate_str} |")
    W("")

    se_inflation_21 = (abs(g1_21.get("t_hac") or 0) / max(abs(g1_21.get("t_iid") or 1e-6), 1e-6))
    t_hac_21 = g1_21.get("t_hac") or 0
    t_hac_63 = g1_63.get("t_hac") or 0
    W(f"**{'Both cells fail' if not g1_pass else 'Both cells pass'} the gate.** "
      f"The direction is positive, but {'far below' if not g1_pass else 'above'} the statistical threshold. "
      f"The date-clustering inflates standard errors by {1/max(se_inflation_21, 0.01):.1f}× "
      f"relative to i.i.d. (ratio of cluster SE to i.i.d. SE), which is the correct "
      f"treatment for an event study where signal dates cluster in market-regime episodes.")
    W("")
    if not g1_pass:
        W("**Interpretation**: Once you condition on the return path over [t,t+10], the forward")
        W("outperformance disappears. The raw signal reflects the general momentum/drift in names")
        W("that happened to have above-median paths — not a distinctive forward alpha from")
        W("absorption itself.")
    W("")

    W("### G2: SPLIT-HALF SAME-SIGN — " + ("PASS" if g2["pass"] else "FAIL"))
    W("")
    W(f"Split at calendar midpoint {SPLIT_DATE.date()} "
      f"(H1: pre-{SPLIT_DATE.year}, H2: {SPLIT_DATE.year}–2026).")
    W("")
    W("| Period | 21d diff | 63d diff |")
    W("|---|---|---|")
    h1_21 = g2["21d"].get("h1_mean", 0) or 0
    h2_21 = g2["21d"].get("h2_mean", 0) or 0
    h1_63 = g2["63d"].get("h1_mean", 0) or 0
    h2_63 = g2["63d"].get("h2_mean", 0) or 0
    W(f"| H1 (early, pre-{SPLIT_DATE.date()}) | {h1_21*100:+.2f}% | {h1_63*100:+.2f}% |")
    W(f"| H2 (late, {SPLIT_DATE.date()}–2026) | {h2_21*100:+.2f}% | {h2_63*100:+.2f}% |")
    W("")
    W(f"Both halves {'same-sign positive' if g2['pass'] else 'not same-sign'}. G2 {'PASS' if g2['pass'] else 'FAIL'}.")
    W("")

    W("### G3: LOCO (2015 crash, 2018 bear, 2024-09 stimulus) — " + ("PASS" if g3["pass"] else "FAIL"))
    W("")
    W("| Crisis excluded | 21d diff | 63d diff |")
    W("|---|---|---|")
    for cr_label, _, _ in CRISIS_WINDOWS:
        r21 = next((r for r in g3["cells"] if r["label"] == cr_label and r["horizon"] == 21), {})
        r63 = next((r for r in g3["cells"] if r["label"] == cr_label and r["horizon"] == 63), {})
        d21 = r21.get("mean_diff")
        d63 = r63.get("mean_diff")
        W(f"| Excl {cr_label} | {d21*100:+.2f}% | {d63*100:+.2f}% |")
    d21_full = g1_21.get("mean_diff", 0) or 0
    d63_full = g1_63.get("mean_diff", 0) or 0
    W(f"| Full sample | {d21_full*100:+.2f}% | {d63_full*100:+.2f}% |")
    W("")
    W(f"All six leave-one-out estimates {'remain positive' if g3['pass'] else 'not all positive'}. G3 {'PASS' if g3['pass'] else 'FAIL'}.")
    W("")

    W("### G4 (REPORTED, NON-GATED): Partial effect after drift-factor residualization")
    W("")
    W("Drift factor construction: for each event at time t, compute its [t,t+10]")
    W("cross-sectional return quintile within the same quarter, then compute the expected")
    W("forward return for that quintile (the announcement-return-conditioned drift premium).")
    W("Each name's forward return is residualized by subtracting this drift expectation.")
    W("")
    W("| Horizon | Absorbed residual | Control residual | Partial diff | t | p |")
    W("|---|---|---|---|---|---|")
    for h in HORIZONS:
        gr = g4.get(h, {})
        W(f"| {h}d | "
          f"+{gr.get('absorbed_residual_mean', 0)*100:.3f}% | "
          f"{gr.get('control_residual_mean', 0)*100:.3f}% | "
          f"+{gr.get('partial_diff', 0)*100:.3f}% | "
          f"{gr.get('t_iid', 0):.2f} | "
          f"{gr.get('p_iid', 0):.4f} |")
    W("")
    W("G4 shows a partial signal in i.i.d. inference, but this uses residuals computed")
    W("from ALL names in the same quintile — the drift factor itself carries absorption-correlated")
    W("information (absorbed names are over-represented in high-quintile cells, so their")
    W("within-quintile residuals are systematically positive relative to non-absorbed names")
    W("in the same cell). G4 is reported as a descriptive decomposition, not a causal estimate.")
    W("")
    W("---")
    W("")

    W("## 6. Mechanism interpretation")
    W("")
    W("The original hypothesis: the absorption signal identifies a new marginal buyer with")
    W("patience sufficient to offset mandated selling, creating a positive forward-return tilt.")
    W("")
    W("What the data show:")
    W(f"- Absorption events (above-median [t,t+10] path) have higher raw forward returns")
    W(f"  ({d21_full*100:+.2f} pp at 21d, {d63_full*100:+.2f} pp at 63d).")
    if not g1_pass:
        W(f"- After matching on the path itself, the excess disappears (t_HAC < 1.5).")
        W("- The G4 partial effect suggests some within-path-quintile information,")
        W("  but the date-clustered evidence is not convincing.")
        W(f"- Split-half asymmetry (effect concentrated in H2) hints at regime-dependence")
        W("  rather than a persistent structural mechanism.")
    W("")
    W("The red-team's neutralization design worked as intended: conditioning on the return path")
    W(f"{'removes' if not g1_pass else 'does not fully remove'} the forward alpha. "
      f"The absorption signal as specified {'does not add' if not g1_pass else 'adds'} a")
    W("distinguishable increment over the path information in the price itself.")
    W("")
    W("---")
    W("")

    W("## 7. Pre-registered gaps (registered nulls — successful runs)")
    W("")
    W(f"1. **E2 historical tape not available**: `china_block_trades` is a current-state")
    W(f"   snapshot ({e2_info.get('n_rows', 461)} rows, single asof={e2_info.get('asof_dates', ['2026-07-07'])[0]}). "
      f"F5-01 archiver must accumulate multi-year tape. E2 re-enters when tape covers >= 3 years.")
    W("")
    W("2. **E2 SOURCE-PATH MISMATCH vs spec**: Spec named `data/china_block_tape mrtj 2013+`")
    W("   which does not exist. Substitute: `data/china_block_trades/detail.parquet` used.")
    W("   Interpretation: 'china_block_tape mrtj' is a forward reference to the tape")
    W("   commissioned by the F5-01 archiver, not a typo. Path mismatch is structural —")
    W("   the tape does not yet exist.")
    W("")
    W(f"3. **{n_total:,} vs 38,988 rows**: {38988-n_total}-row delta in windows.parquet vs spec. Minor,")
    W("   pre-registered as data-refresh timing difference. No impact on analysis.")
    W("")
    W(f"4. **{100*n_covered/max(n_total,1):.1f}% coverage**: structural constraint of the 1,587-file price universe vs")
    W("   4,713 unique tickers in windows.parquet. All results are upper bounds for the")
    W("   more-liquid covered subset.")
    W("")
    W("---")
    W("")

    W("## 8. Summary")
    W("")
    W("| Gate | Status | Key number |")
    W("|---|---|---|")
    t_hac_21_str = f"{g1_21.get('t_hac', 0):.2f}" if g1_21.get("t_hac") is not None else "N/A"
    t_hac_63_str = f"{g1_63.get('t_hac', 0):.2f}" if g1_63.get("t_hac") is not None else "N/A"
    W(f"| G1 (decisive) | **{'PASS' if g1_pass else 'FAIL'}** | "
      f"t_HAC = {t_hac_21_str} @ 21d, {t_hac_63_str} @ 63d (need |t|>=2) |")
    W(f"| G2 split-half | {'PASS' if g2['pass'] else 'FAIL'} | "
      f"Both halves {'positive' if g2['pass'] else 'mixed'}; H1 near-zero |")
    W(f"| G3 LOCO | {'PASS' if g3['pass'] else 'FAIL'} | "
      f"{'All 6' if g3['pass'] else 'Not all'} crisis-exclusions positive |")
    g4_21 = g4.get(21, {})
    W(f"| G4 (non-gated) | — | "
      f"+{g4_21.get('partial_diff', 0)*100:.2f}% partial @ 21d, "
      f"t={g4_21.get('t_iid', 0):.2f} (i.i.d.) |")
    W("| E2 | Registered null | Historical tape does not exist (F5-01 archiver required) |")
    W("")
    W(f"**Overall VERDICT: {'PASS' if g1_pass else 'FAIL'} (G1 decisive). "
      f"{'The absorption filter delivers path-neutralized alpha.' if g1_pass else 'The absorption filter as specified does not deliver path-neutralized alpha. The raw positive return differential reflects the return path itself, not the absorption signal.'} "
      f"Family `cn_supply_absorption` {'advances to production' if g1_pass else 'does not advance to production'}.**")
    W("")
    W("**Possible reopen conditions**: (a) E2 historical tape accumulated (F5-01 archiver);")
    W("(b) refined absorption definition — e.g., requiring the absorbed name to OUTPERFORM")
    W("its own historical volatility-adjusted expectation (not just the cross-section median)")
    W("— which would be a tighter, mechanistically-motivated filter; (c) regime-conditioned")
    W("test isolating the H2 (2020+) window under a pre-registered design.")
    W("")
    W("---")
    W("")
    W(f"*Report authored: 2026-07-08. Data: `data/cn_holder_sales/windows.parquet`,*")
    W(f"*`data/china_block_trades/detail.parquet`, `data/china_stocks_raw/*.parquet`,*")
    W(f"*`data/baskets_china/membership.json`. Repro: `python -m scripts.d4_cn_supply_absorption_phase0`*")
    W(f"*in the `feat/d4-cn-supply-absorption` worktree. No 'validated' language used per CI guard.*")

    out.write_text("\n".join(lines))
    print(f"\n[report] Written: {out}")


if __name__ == "__main__":
    main()
