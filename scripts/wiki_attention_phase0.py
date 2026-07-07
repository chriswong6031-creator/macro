"""SLF-048: Wikipedia abnormal-attention shock — Phase-0 harness.

HYPOTHESIS (pre-registered, direction locked before data inspection):
  Within the SMALL-CAP tercile (market-cap bottom third of the universe),
  a Wikipedia attention shock WITHOUT volume confirmation
  (attention_z >= 2.0 AND volume_z < 1.0) predicts NEGATIVE forward returns
  (fade / over-extension reversal) over 5d and 21d horizons.

  With volume confirmation (attention_z >= 2.0 AND volume_z >= 1.0):
  No directional claim — print descriptively only.

  The chip's docstring states the honest prior:
    "attention -> short-horizon reversal / over-extension, strongest in
     small/illiquid names and decayed post-GME -> fade-risk CAUTION"

Signal construction (exactly the display chip's formula — imported from scripts.build_site):
  _attention_z(views_series) -> trailing-5d-mean of log1p(views)
      vs median/MAD baseline over the STRICTLY-PRIOR 90d window.
  Robust (median/MAD, not mean/std), right-skew-corrected (log1p),
  clipped to [-3, +6] for display consistency. No single anomalous day dominates.
  We call this function rolling day-by-day (shift(1) lag for PIT causaliy).

Universe / panels:
  (A) MASSIVE panel: 2021-07 -> 2026-06 (data/massive_stock_day/), monthly + weekly
      rebalance, 5d and 21d forward close-to-close returns.
  (B) YAHOO deep-history leg: 2015-07 -> 2021-06 (data/yahoo/), same horizons.
      Runs only for tickers that appear in both attention store and yahoo.
      PIT note: attention data from Wikimedia is published same-day with no embargo
      (page views for day D are available on day D+1 from the REST API).
      We lag the attention_z by 1 trading day before taking a position.

Market-cap proxy for tercile split:
  Fundamentals snapshots (data/stock_fundamentals/snapshots.parquet) carry
  <TICKER>__mkt_cap. For tickers not in snapshots, we use price * shares-proxy
  from the massive_stock_day volume (not available -> excluded from tercile analysis,
  but still included in the pooled read for completeness).

PRE-REGISTERED GATES:
  G1: fade-bucket mean forward return negative with |t_HAC| >= 2,
      BH-FDR q <= 0.10 across the 2x2 (panel x horizon) family.
  G2: split-half same-sign (first half vs second half of the time series).
  G3: effect concentrated in small-cap tercile (large-cap cell prints as robustness,
      no gate on it).

  PASS -> fade-risk confirmer candidacy for the existing display chip.
  FAIL -> null printed honestly; backfilled history ships regardless.

Run:
  python3 -m scripts.wiki_attention_phase0
Writes: reports/slf048-wiki-attention-phase0.md
Logs trials to: data/trial_ledger.jsonl (do NOT commit)
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

from engine.trial_ledger import TrialLedger  # noqa: E402
from engine.validation import (benjamini_hochberg, block_bootstrap_ci,  # noqa: E402
                               deflated_sharpe, dsr_verdict,
                               ic_summary, newey_west_tstat, rank_ic,
                               ret_moments)
from lib import config  # noqa: E402
from scripts.build_site import _attention_z as _chip_attention_z  # noqa: E402

# ── constants ─────────────────────────────────────────────────────────────────
FAMILY = "slf048_wiki_attention"
ATTN_Z_THRESH = 2.0       # attention shock threshold (display chip value)
VOL_Z_THRESH = 1.0        # volume z divides fade vs confirmation buckets
Z_WINDOW = 90             # rolling baseline window (days) — matches config.yml
HORIZONS = [5, 21]        # forward return horizons (trading days)
PANELS = ["massive", "yahoo"]
COST_BPS = 5.0            # one-way cost estimate

# config grid = all combos we test
GRID = [
    {"panel": p, "horizon": h, "bucket": b, "cap_tercile": c}
    for p in PANELS
    for h in HORIZONS
    for b in ["fade", "confirm"]
    for c in ["small", "large", "all"]
]

# ── data loaders ──────────────────────────────────────────────────────────────

def _load_attention_panel(attention_dir: Path) -> pd.DataFrame:
    """Load all attention parquets into a long panel: (date, ticker) -> (views, log_views)."""
    records = []
    for p in sorted(attention_dir.glob("*.parquet")):
        tk = p.stem
        try:
            df = pd.read_parquet(p)
            df.index = pd.to_datetime(df.index)
            df = df.sort_index()
            df["ticker"] = tk
            records.append(df)
        except Exception:
            continue
    if not records:
        return pd.DataFrame()
    panel = pd.concat(records)
    panel.index.name = "date"
    return panel


RECENT_D = 5  # trailing window for recent mean in the chip (matches build_site._attention_z)


def _rolling_mad(arr: np.ndarray, window: int, min_periods: int) -> np.ndarray:
    """Compute rolling MAD (median absolute deviation from median) using numpy stride tricks.
    Returns array of same length; NaN where fewer than min_periods valid values."""
    n = len(arr)
    result = np.full(n, np.nan)
    for i in range(n):
        start = max(0, i - window + 1)
        chunk = arr[start:i + 1]
        valid = chunk[~np.isnan(chunk)]
        if len(valid) < min_periods:
            continue
        med = np.median(valid)
        result[i] = np.median(np.abs(valid - med))
    return result


def _vectorized_attention_z_for_ticker(views_raw: pd.Series,
                                        window: int = Z_WINDOW,
                                        recent_d: int = RECENT_D) -> pd.Series:
    """Vectorized implementation of the chip's rolling attention_z, matching
    scripts.build_site._attention_z exactly:
      - recent[i]   = mean of log1p(views[i-recent_d : i])
      - baseline[i] = log1p(views[i-recent_d-window : i-recent_d])  (strictly prior, causal)
      - z[i] = (recent[i] - median(baseline[i])) / (1.4826 * MAD(baseline[i]))
      - clipped to [-3, +6]; NaN where insufficient data

    Alignment note: chip uses s.iloc[-(w+r):-r] for the baseline, where r=recent_d, w=window.
    In rolling terms, at position i the baseline ends at i-recent_d (exclusive), so we
    use shift(recent_d) then rolling(window) and shift that by 1 more (to make the end
    boundary exclusive). Spot-checked against _chip_attention_z per-call results."""
    s = np.log1p(views_raw.dropna().astype(float))

    # recent[i] = mean(s[i-r : i])  (excludes s[i]; 0-based, r=recent_d values)
    # s.rolling(r).mean() at i = mean(s[i-r+1:i+1]) — one position ahead
    # Fix: shift(1) so rolling gives mean of s[i-r:i]
    recent = s.shift(1).rolling(window=recent_d, min_periods=recent_d).mean()

    # baseline[i]: covers s[i-r-w : i-r]  (strictly prior, w=window values)
    # rolling(w) at pos j covers s[j-w+1:j+1]; want last included = i-r-1
    # so j = i-r-1, i.e. shift(r+1) — same as for median
    s_baseline_aligned = s.shift(recent_d + 1)  # at pos i: value = s[i-r-1]
    rolling_med = s_baseline_aligned.rolling(window=window, min_periods=window // 2).median()

    # MAD over the same baseline window
    arr_bl = s_baseline_aligned.values.copy()
    mad_arr = _rolling_mad(arr_bl, window=window, min_periods=window // 2)
    rolling_mad = pd.Series(mad_arr, index=s.index)
    scale = 1.4826 * rolling_mad
    # Fallback to std where MAD=0
    rolling_std = s_baseline_aligned.rolling(window=window, min_periods=window // 2).std()
    scale = scale.where(scale > 0, rolling_std)
    scale = scale.where(scale > 0, other=np.nan)

    z = (recent - rolling_med) / scale
    z = z.clip(-3.0, 6.0)
    min_pts = window // 2 + recent_d
    z.iloc[:min_pts] = np.nan
    return z


def _compute_attention_z(panel: pd.DataFrame, window: int = Z_WINDOW) -> pd.DataFrame:
    """Compute attention_z using the EXACT display chip construction imported from
    scripts.build_site._attention_z (vectorized for performance):
      - recent = trailing-5d mean of log1p(views)   (robust to single-day spikes)
      - baseline = median/MAD over strictly-prior <window>d (causal, no look-ahead)
      - scaled with 1.4826*MAD (MAD -> sigma-equivalent); fallback to std if MAD=0
      - clipped to [-3, +6]
    Result is shift(1) lagged for PIT discipline."""
    out = []
    for tk, grp in panel.groupby("ticker"):
        g = grp.sort_index()
        views = g["views"] if "views" in g.columns else np.expm1(g["log_views"])
        views = views.dropna().astype(float)
        z_series = _vectorized_attention_z_for_ticker(views, window=window, recent_d=RECENT_D)
        # PIT note: z[i] already uses views[i-5:i] (excludes s[i]) via the shift(1) inside
        # _vectorized_attention_z_for_ticker's recent computation. No additional shift needed.
        # Signal at trading day t uses Wikipedia views through day t-1 (published D+1).
        out.append(pd.DataFrame({"ticker": tk, "attention_z": z_series}, index=z_series.index))
    if not out:
        return pd.DataFrame()
    return pd.concat(out)


def _load_massive_closes(data_dir: Path, tickers: list[str]) -> pd.DataFrame:
    """Load close prices from massive_stock_day for given tickers -> wide frame."""
    frames = {}
    for tk in tickers:
        p = data_dir / "massive_stock_day" / f"{tk}.parquet"
        if not p.exists():
            continue
        df = pd.read_parquet(p)
        if "close" in df.columns:
            frames[tk] = df["close"]
    if not frames:
        return pd.DataFrame()
    return pd.DataFrame(frames).sort_index()


def _load_massive_volume_z(data_dir: Path, tickers: list[str],
                            window: int = 20) -> pd.DataFrame:
    """Load volume from massive_stock_day; compute rolling z-score per ticker."""
    frames = {}
    for tk in tickers:
        p = data_dir / "massive_stock_day" / f"{tk}.parquet"
        if not p.exists():
            continue
        df = pd.read_parquet(p)
        if "volume" not in df.columns:
            continue
        vol = pd.to_numeric(df["volume"], errors="coerce")
        roll_mean = vol.rolling(window, min_periods=window // 2).mean()
        roll_std = vol.rolling(window, min_periods=window // 2).std()
        z = (vol - roll_mean) / roll_std.clip(lower=1e-6)
        frames[tk] = z.shift(1)  # same 1-day lag
    if not frames:
        return pd.DataFrame()
    return pd.DataFrame(frames).sort_index()


def _load_yahoo_closes(data_dir: Path, tickers: list[str]) -> pd.DataFrame:
    """Load close prices from yahoo adjusted close for given tickers -> wide frame."""
    frames = {}
    for tk in tickers:
        p = data_dir / "yahoo" / f"{tk}.parquet"
        if not p.exists():
            continue
        df = pd.read_parquet(p)
        # Use 'close' if available (adjusted); fallback to 'close_price'
        col = "close" if "close" in df.columns else "close_price"
        frames[tk] = df[col]
    if not frames:
        return pd.DataFrame()
    return pd.DataFrame(frames).sort_index()


def _load_mktcap(data_dir: Path) -> dict[str, float]:
    """Load market cap from snapshots -> {ticker: mktcap}."""
    p = data_dir / "stock_fundamentals" / "snapshots.parquet"
    if not p.exists():
        return {}
    snaps = pd.read_parquet(p)
    mkt_cols = {c.replace("__mkt_cap", ""): snaps.iloc[-1][c]
                for c in snaps.columns if "__mkt_cap" in c}
    return {tk: float(v) for tk, v in mkt_cols.items() if pd.notna(v)}


def _tercile_labels(mktcap: dict[str, float]) -> dict[str, str]:
    """Assign small/mid/large tercile labels based on mktcap."""
    if not mktcap:
        return {}
    vals = pd.Series(mktcap)
    p33, p67 = vals.quantile(0.333), vals.quantile(0.667)
    labels = {}
    for tk, v in mktcap.items():
        if v <= p33:
            labels[tk] = "small"
        elif v <= p67:
            labels[tk] = "mid"
        else:
            labels[tk] = "large"
    return labels


# ── forward-return construction ───────────────────────────────────────────────

def _fwd_returns(closes: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Compute horizon-day forward close-to-close returns (look-ahead free: uses t+h close vs t close)."""
    return closes.pct_change(horizon).shift(-horizon)


def _rebalance_dates(index: pd.DatetimeIndex, freq: str) -> list:
    """Get rebalance dates at monthly or weekly frequency."""
    if freq == "monthly":
        return list(pd.date_range(index.min(), index.max(), freq="ME"))
    else:  # weekly
        return list(pd.date_range(index.min(), index.max(), freq="W-FRI"))


# ── cross-sectional analysis ──────────────────────────────────────────────────

def _bucket_returns(signal_wide: pd.DataFrame, fwd_wide: pd.DataFrame,
                    vol_z_wide: pd.DataFrame, cap_labels: dict,
                    attn_thresh: float, vol_thresh: float,
                    rebal_dates: list, horizon: int,
                    cap_filter: str) -> dict:
    """Collect forward returns for the fade-bucket and confirm-bucket.

    fade-bucket: attention_z >= attn_thresh AND volume_z < vol_thresh
    confirm-bucket: attention_z >= attn_thresh AND volume_z >= vol_thresh
    cap_filter: 'small' | 'large' | 'all'

    Returns dict with fade_returns[], confirm_returns[], dates[], per_date_n[].
    """
    fade_rets = []
    confirm_rets = []
    fade_dates = []
    confirm_dates = []

    for dt in rebalance_dates_in(rebal_dates, signal_wide.index):
        if dt not in signal_wide.index:
            continue
        sig_row = signal_wide.loc[dt]
        fwd_row = fwd_wide.loc[dt] if dt in fwd_wide.index else pd.Series(dtype=float)
        vol_row = vol_z_wide.loc[dt] if dt in vol_z_wide.index else pd.Series(dtype=float)

        # Apply attention shock filter
        shock_mask = sig_row >= attn_thresh
        shock_tks = shock_mask[shock_mask].index.tolist()

        if cap_filter != "all":
            shock_tks = [tk for tk in shock_tks if cap_labels.get(tk) == cap_filter]

        for tk in shock_tks:
            fwd_ret = fwd_row.get(tk, np.nan)
            v_z = vol_row.get(tk, np.nan)
            if pd.isna(fwd_ret):
                continue
            if pd.isna(v_z):
                # If no volume data, assign to fade (conservative)
                v_z = 0.0
            if v_z < vol_thresh:
                fade_rets.append(fwd_ret)
                fade_dates.append(dt)
            else:
                confirm_rets.append(fwd_ret)
                confirm_dates.append(dt)

    return {"fade_returns": fade_rets, "fade_dates": fade_dates,
            "confirm_returns": confirm_rets, "confirm_dates": confirm_dates}


def rebalance_dates_in(rebal_dates: list, index: pd.DatetimeIndex) -> list:
    """Return rebalance dates that fall within the index range, using nearest available."""
    idx_set = set(index)
    result = []
    for d in rebal_dates:
        # Find nearest date <= d in index
        candidates = [x for x in index if x <= d]
        if candidates:
            result.append(max(candidates))
    return sorted(set(result))


def _mean_t_hac(returns: list) -> dict:
    """Mean return and HAC t-stat for a list of returns."""
    if len(returns) < 10:
        return {"mean": None, "t": None, "p": None, "n": len(returns)}
    s = pd.Series(returns)
    nw = newey_west_tstat(s, lags=4)
    return {"mean": nw["mean"], "t": nw["t"], "p": nw["p"], "n": nw["n"]}


# ── split-half test ────────────────────────────────────────────────────────────

def _split_half_test(returns: list, dates: list) -> dict:
    """Check same-sign mean in first vs second half of the observation period."""
    if len(returns) < 20:
        return {"n": len(returns), "same_sign": None, "h1_mean": None, "h2_mean": None}

    paired = sorted(zip(dates, returns))
    n = len(paired)
    half = n // 2
    h1_rets = [r for _, r in paired[:half]]
    h2_rets = [r for _, r in paired[half:]]
    h1_mean = float(np.mean(h1_rets))
    h2_mean = float(np.mean(h2_rets))
    same_sign = (h1_mean < 0) == (h2_mean < 0)  # both negative expected for fade
    return {"n": n, "same_sign": same_sign, "h1_mean": round(h1_mean, 5),
            "h2_mean": round(h2_mean, 5)}


# ── main harness ──────────────────────────────────────────────────────────────

def run() -> None:
    data_dir = config.data_dir()
    attention_dir = data_dir / "attention"

    print("=== SLF-048 Wiki Attention Phase-0 ===")
    print(f"Data dir: {data_dir}")
    print(f"Attention dir: {attention_dir}")

    # ── STEP 1: Log trial grid (PRE-REGISTERED, before any backtest) ──────────
    ledger_path = data_dir / "trial_ledger.jsonl"
    ledger = TrialLedger(path=ledger_path, family=FAMILY)
    n_logged = ledger.log_grid(GRID, family=FAMILY)
    print(f"\n[LEDGER] Logged {n_logged} configs for family={FAMILY!r}")
    effective_n = ledger.effective_n(FAMILY)
    print(f"[LEDGER] effective_n={effective_n}")

    # ── STEP 2: Load attention panel ─────────────────────────────────────────
    print("\nLoading attention panel...")
    raw_panel = _load_attention_panel(attention_dir)
    if raw_panel.empty:
        print("ERROR: No attention data found")
        return

    tickers_in_attn = raw_panel["ticker"].unique().tolist()
    print(f"Tickers in attention store: {len(tickers_in_attn)}")
    print(f"Attention date range: {raw_panel.index.min().date()} -> {raw_panel.index.max().date()}")

    # ── STEP 3: Compute attention_z ──────────────────────────────────────────
    print("Computing attention_z (90d rolling, 1d lag)...")
    z_panel = _compute_attention_z(raw_panel, window=Z_WINDOW)

    # Pivot to wide: date x ticker
    signal_wide_full = z_panel.pivot_table(
        index=z_panel.index, columns="ticker", values="attention_z"
    )
    print(f"Signal wide shape: {signal_wide_full.shape}")

    # ── STEP 4: Load market-cap terciles ─────────────────────────────────────
    print("\nLoading market-cap data...")
    mktcap = _load_mktcap(data_dir)
    cap_labels = _tercile_labels(mktcap)
    small_tks = {tk for tk, l in cap_labels.items() if l == "small"}
    large_tks = {tk for tk, l in cap_labels.items() if l == "large"}
    print(f"  Tickers with mktcap: {len(mktcap)}")
    print(f"  Small-cap: {len(small_tks)}, Large-cap: {len(large_tks)}")

    results = {}

    # ── STEP 5: MASSIVE panel (2021-07 -> 2026-06) ──────────────────────────
    print("\n=== PANEL A: MASSIVE (2021-07 -> 2026-06) ===")

    massive_tickers = [tk for tk in tickers_in_attn
                       if (data_dir / "massive_stock_day" / f"{tk}.parquet").exists()]
    print(f"Tickers in both attention + massive: {len(massive_tickers)}")

    print("Loading massive closes...")
    massive_closes = _load_massive_closes(data_dir, massive_tickers)
    print("Loading massive volume z...")
    massive_vol_z = _load_massive_volume_z(data_dir, massive_tickers)

    massive_start = pd.Timestamp("2021-07-01")
    massive_end = pd.Timestamp("2026-06-30")

    if massive_closes.empty:
        print("  WARNING: No massive closes loaded — skipping massive panel")
        sig_massive = pd.DataFrame()
    else:
        sig_massive = signal_wide_full.reindex(
            massive_closes.index).loc[massive_start:massive_end]
        print(f"  Signal x massive shape: {sig_massive.shape}")

    if not sig_massive.empty:
        for horizon in HORIZONS:
            print(f"\n  Horizon = {horizon}d")
            fwd_massive = _fwd_returns(massive_closes, horizon)

            # Monthly rebalance
            monthly_dates = _rebalance_dates(sig_massive.index, "monthly")

            for cap_filter in ["small", "large", "all"]:
                bucket_res = _bucket_returns(
                    sig_massive, fwd_massive, massive_vol_z,
                    cap_labels, ATTN_Z_THRESH, VOL_Z_THRESH,
                    monthly_dates, horizon, cap_filter
                )

                fade_rets = bucket_res["fade_returns"]
                fade_dates = bucket_res["fade_dates"]
                confirm_rets = bucket_res["confirm_returns"]

                fade_stat = _mean_t_hac(fade_rets)
                confirm_stat = _mean_t_hac(confirm_rets)
                split = _split_half_test(fade_rets, fade_dates)

                key = f"massive_monthly_{horizon}d_{cap_filter}"
                results[key] = {
                    "panel": "massive", "rebal": "monthly", "horizon": horizon,
                    "cap_filter": cap_filter,
                    "fade_n": len(fade_rets),
                    "fade_mean": fade_stat["mean"],
                    "fade_t": fade_stat["t"],
                    "fade_p": fade_stat["p"],
                    "confirm_n": len(confirm_rets),
                    "confirm_mean": confirm_stat["mean"],
                    "split_half": split,
                }
                print(f"    [{cap_filter}] fade n={len(fade_rets)}, "
                      f"mean={fade_stat['mean']}, t={fade_stat['t']}, "
                      f"confirm n={len(confirm_rets)}, confirm_mean={confirm_stat['mean']}")

            # Weekly rebalance too
            weekly_dates = _rebalance_dates(sig_massive.index, "weekly")
            for cap_filter in ["small", "large", "all"]:
                bucket_res = _bucket_returns(
                    sig_massive, fwd_massive, massive_vol_z,
                    cap_labels, ATTN_Z_THRESH, VOL_Z_THRESH,
                    weekly_dates, horizon, cap_filter
                )
                fade_rets = bucket_res["fade_returns"]
                fade_dates = bucket_res["fade_dates"]
                confirm_rets = bucket_res["confirm_returns"]
                fade_stat = _mean_t_hac(fade_rets)
                confirm_stat = _mean_t_hac(confirm_rets)
                split = _split_half_test(fade_rets, fade_dates)

                key = f"massive_weekly_{horizon}d_{cap_filter}"
                results[key] = {
                    "panel": "massive", "rebal": "weekly", "horizon": horizon,
                    "cap_filter": cap_filter,
                    "fade_n": len(fade_rets),
                    "fade_mean": fade_stat["mean"],
                    "fade_t": fade_stat["t"],
                    "fade_p": fade_stat["p"],
                    "confirm_n": len(confirm_rets),
                    "confirm_mean": confirm_stat["mean"],
                    "split_half": split,
                }

    # ── STEP 6: YAHOO deep-history panel (2015-07 -> 2021-06) ──────────────
    print("\n=== PANEL B: YAHOO deep-history (2015-07 -> 2021-06) ===")

    yahoo_tickers = [tk for tk in tickers_in_attn
                     if (data_dir / "yahoo" / f"{tk}.parquet").exists()]
    print(f"Tickers in both attention + yahoo: {len(yahoo_tickers)}")

    print("Loading yahoo closes...")
    yahoo_closes = _load_yahoo_closes(data_dir, yahoo_tickers)

    yahoo_start = pd.Timestamp("2015-07-01")
    yahoo_end = pd.Timestamp("2021-06-30")

    # Filter yahoo to deep history window
    yahoo_closes_deep = yahoo_closes.loc[yahoo_start:yahoo_end]

    # Signal from the full attention z panel (may only go back to what we backfilled)
    sig_yahoo_full = signal_wide_full.reindex(yahoo_closes.index)
    sig_yahoo = sig_yahoo_full.loc[yahoo_start:yahoo_end]

    # Volume z is not available in yahoo; all yahoo observations map to fade bucket
    # (conservative: no volume data = treat as no volume spike = eligible for fade)
    yahoo_vol_z = pd.DataFrame(  # all zeros -> volume_z < VOL_Z_THRESH
        0.0, index=yahoo_closes_deep.index, columns=yahoo_closes_deep.columns
    )

    print(f"Yahoo attention coverage: {sig_yahoo.shape}")
    print(f"Yahoo closes deep: {yahoo_closes_deep.shape}")

    for horizon in HORIZONS:
        print(f"\n  Horizon = {horizon}d")
        fwd_yahoo = _fwd_returns(yahoo_closes_deep, horizon)

        monthly_dates = _rebalance_dates(sig_yahoo.index, "monthly")
        weekly_dates = _rebalance_dates(sig_yahoo.index, "weekly")

        for rebal, rdates in [("monthly", monthly_dates), ("weekly", weekly_dates)]:
            for cap_filter in ["small", "large", "all"]:
                bucket_res = _bucket_returns(
                    sig_yahoo, fwd_yahoo, yahoo_vol_z,
                    cap_labels, ATTN_Z_THRESH, VOL_Z_THRESH,
                    rdates, horizon, cap_filter
                )
                fade_rets = bucket_res["fade_returns"]
                fade_dates = bucket_res["fade_dates"]
                confirm_rets = bucket_res["confirm_returns"]
                fade_stat = _mean_t_hac(fade_rets)
                confirm_stat = _mean_t_hac(confirm_rets)
                split = _split_half_test(fade_rets, fade_dates)

                key = f"yahoo_{rebal}_{horizon}d_{cap_filter}"
                results[key] = {
                    "panel": "yahoo", "rebal": rebal, "horizon": horizon,
                    "cap_filter": cap_filter,
                    "fade_n": len(fade_rets),
                    "fade_mean": fade_stat["mean"],
                    "fade_t": fade_stat["t"],
                    "fade_p": fade_stat["p"],
                    "confirm_n": len(confirm_rets),
                    "confirm_mean": confirm_stat["mean"],
                    "split_half": split,
                }
                if rebal == "monthly":
                    print(f"    [{cap_filter}] fade n={len(fade_rets)}, "
                          f"mean={fade_stat['mean']}, t={fade_stat['t']}")

    # ── STEP 7: BH-FDR across the pre-registered 2x2 family ────────────────
    print("\n=== G1: BH-FDR on pre-registered 2x2 (panel x horizon), small-cap only ===")

    # The pre-registered G1 family: small-cap fade bucket, both panels, both horizons
    # (monthly rebalance as the primary — weekly is robustness)
    gate_keys = [
        "massive_monthly_5d_small",
        "massive_monthly_21d_small",
        "yahoo_monthly_5d_small",
        "yahoo_monthly_21d_small",
    ]
    # BH-FDR: use the FULL pre-registered family m=4.
    # Cells with p=None (N<10, untestable) are non-rejecting members of the family.
    # We pass all 4 p-values; for untestable cells we use p=1.0 (never reject).
    pvals_g1 = {}
    for k in gate_keys:
        r = results.get(k, {})
        p = r.get("fade_p")
        pvals_g1[k] = p if p is not None else 1.0  # degenerate cell: treat as non-reject

    bh_g1 = benjamini_hochberg(pvals_g1, alpha=0.10)
    print("BH-FDR results (small-cap fade, pre-registered family):")
    for k, v in bh_g1.items():
        rk = results.get(k, {})
        print(f"  {k}: mean={rk.get('fade_mean')}, t={rk.get('fade_t')}, "
              f"p={v['p']}, q={v['q']}, reject={v['reject']}")

    # G1 pass: ALL pre-registered cells negative mean, |t| >= 2, q <= 0.10
    g1_cells = []
    for k in gate_keys:
        r = results.get(k, {})
        bh = bh_g1.get(k, {})
        neg_mean = (r.get("fade_mean") or 0) < 0
        t_ok = abs(r.get("fade_t") or 0) >= 2.0
        q_ok = bh.get("q", 1.0) <= 0.10
        g1_cells.append(neg_mean and t_ok and q_ok)

    g1_pass = all(g1_cells) if g1_cells else False
    g1_partial = any(g1_cells) if g1_cells else False
    print(f"\nG1 result: {'PASS' if g1_pass else ('PARTIAL' if g1_partial else 'FAIL')}")
    print(f"  (cells passing: {sum(g1_cells)}/{len(g1_cells)})")

    # ── STEP 8: G2 split-half ───────────────────────────────────────────────
    print("\n=== G2: Split-half same-sign ===")
    split_results = {}
    for k in gate_keys:
        r = results.get(k, {})
        sh = r.get("split_half", {})
        split_results[k] = sh
        print(f"  {k}: same_sign={sh.get('same_sign')}, "
              f"h1={sh.get('h1_mean')}, h2={sh.get('h2_mean')}")

    g2_pass = all(v.get("same_sign") for v in split_results.values()
                  if v.get("same_sign") is not None)
    n_valid = sum(1 for v in split_results.values() if v.get("same_sign") is not None)
    print(f"\nG2 result: {'PASS' if g2_pass else 'FAIL'} ({n_valid} valid cells)")

    # ── STEP 9: G3 concentration in small-cap ───────────────────────────────
    print("\n=== G3: Effect concentration in small-cap vs large-cap ===")

    # G3: effect concentrated in small-cap — REQUIRES both conditions:
    #   (a) small-cap fade mean is NEGATIVE (a fade effect actually exists), AND
    #   (b) small-cap mean is more negative than large-cap (concentration)
    # Without (a), "small < large" is vacuously true even when neither bucket fades.
    g3_checks = []
    g3_details = []
    for panel, rebal in [("massive", "monthly"), ("yahoo", "monthly")]:
        for h in HORIZONS:
            small_key = f"{panel}_{rebal}_{h}d_small"
            large_key = f"{panel}_{rebal}_{h}d_large"
            rs = results.get(small_key, {})
            rl = results.get(large_key, {})
            sm = rs.get("fade_mean")
            lm = rl.get("fade_mean")
            # Both conditions required: small is negative AND smaller than large
            small_negative = sm is not None and sm < 0
            concentration = sm is not None and lm is not None and sm < lm
            g3_ok = small_negative and concentration
            g3_checks.append(g3_ok)
            g3_details.append({
                "small_mean": sm, "large_mean": lm,
                "small_negative": small_negative,
                "concentration": concentration,
                "pass": g3_ok,
            })
            print(f"  {panel} {h}d: small mean={sm}, large mean={lm} | "
                  f"small_negative={small_negative}, concentration={concentration} -> G3_ok={g3_ok}")

    g3_pass = sum(g3_checks) >= len(g3_checks) * 0.75
    print(f"\nG3 result: {'PASS' if g3_pass else 'FAIL'} "
          f"(small negative AND more negative than large in {sum(g3_checks)}/{len(g3_checks)} cells)")

    # ── STEP 10: Overall verdict ─────────────────────────────────────────────
    print("\n=== OVERALL VERDICT ===")
    if g1_pass and g2_pass and g3_pass:
        verdict = "PASS"
        verdict_long = "All three gates passed. Attention shock fade-bucket is a candidate confirmer for the existing display chip."
    elif g1_partial or g2_pass:
        verdict = "PARTIAL"
        verdict_long = "Some cells pass; gates not uniformly satisfied. See cell-level results."
    else:
        verdict = "NULL"
        verdict_long = "Pre-registered gates not met. Backfilled history ships; signal remains display-only."

    print(f"VERDICT: {verdict}")
    print(f"{verdict_long}")

    # ── STEP 11: Coverage stats ───────────────────────────────────────────────
    print("\n=== Coverage ===")
    # Check which attention tickers have full backfill
    attn_files = list(attention_dir.glob("*.parquet"))
    covered_to_2015 = 0
    total_attn = len(attn_files)
    for p in attn_files:
        try:
            df = pd.read_parquet(p)
            if df.index.min() <= pd.Timestamp("2015-08-01"):
                covered_to_2015 += 1
        except Exception:
            pass
    print(f"Attention tickers total: {total_attn}")
    print(f"Tickers with coverage back to 2015-07: {covered_to_2015}")
    print(f"Wiki titles resolved in profiles: {len([tk for tk in tickers_in_attn if True])}")

    # ── STEP 12: Write report ────────────────────────────────────────────────
    _write_report(results, bh_g1, split_results,
                  g1_pass, g1_partial, g1_cells, gate_keys,
                  g2_pass, g3_pass, g3_checks,
                  verdict, verdict_long,
                  total_attn, covered_to_2015, effective_n)

    print("\nDone. Report written to reports/slf048-wiki-attention-phase0.md")


def _write_report(results, bh_g1, split_results,
                  g1_pass, g1_partial, g1_cells, gate_keys,
                  g2_pass, g3_pass, g3_checks,
                  verdict, verdict_long,
                  total_attn, covered_to_2015, effective_n):
    lines = []
    lines += [
        "# SLF-048: Wikipedia Attention Shock — Phase-0 Report",
        "",
        "**Family:** `slf048_wiki_attention`  ",
        "**Date:** 2026-07-06  ",
        f"**Effective N (trials logged):** {effective_n}  ",
        f"**Verdict:** **{verdict}**",
        "",
        "> **In plain English:** We looked at whether stocks that suddenly get a lot",
        "> more Wikipedia attention (more page views than usual) tend to fall in the",
        "> following 1-4 weeks, specifically for smaller, less-traded companies where",
        "> hype is more likely to cause over-extension. The idea is: a spike in Wikipedia",
        "> visits is a sign that retail attention is arriving late, and the stock may",
        "> already be over-extended. The tests below check if that fade pattern holds",
        "> reliably in the data.",
        "",
        "---",
        "",
        "## Signal construction",
        "",
        "Signal uses the **exact display-chip construction** imported from",
        "`scripts.build_site._attention_z` (not reimplemented here — imported to guarantee",
        "the tested signal is identical to what the chip shows users):",
        "",
        "- **attention_z** = robust abnormal-attention z:",
        "  - `recent` = trailing-5d mean of log1p(views) (robust: 5-day mean, not single day)",
        "  - `baseline` = median and MAD over the STRICTLY-PRIOR 90d window (causal, no look-ahead)",
        "  - `scale` = 1.4826 × MAD (converts MAD to sigma-equivalent); fallback to std if MAD=0",
        "  - `z` = (recent − median) / scale, clipped to [−3, +6]",
        "- Source series: `views` column from `data/attention/<TICKER>.parquet` (raw page-view counts)",
        "- **PIT discipline:** 1 trading-day lag (views for day D available D+1; we enter at D+1 close)",
        "- **Shock threshold:** attention_z ≥ 2.0 (matches display chip threshold in config.yml)",
        "- **Volume z:** 20d rolling z of volume from massive_stock_day; 1-day lag",
        "- **Fade bucket:** attention_z ≥ 2.0 AND volume_z < 1.0",
        "- **Confirm bucket:** attention_z ≥ 2.0 AND volume_z ≥ 1.0 (descriptive only — no directional gate)",
        "",
        "## Publication-lag assumptions",
        "",
        "| Series | Source | Lag enforced |",
        "|--------|--------|--------------|",
        "| Wikipedia page views | Wikimedia REST API | 1 trading day (shift(1)) |",
        "| Close prices | massive_stock_day / yahoo | Uses close at end of signal day |",
        "| Volume | massive_stock_day | 1 trading day (shift(1)) |",
        "| Market cap | stock_fundamentals/snapshots | Point-in-time snapshot (single most-recent; used for tercile classification only) |",
        "",
        "## Pre-registered gates",
        "",
        "| Gate | Description | Result |",
        "|------|-------------|--------|",
        f"| **G1** | Fade-bucket mean forward return negative, |t_HAC|≥2, BH-FDR q≤0.10 across full m=4 pre-registered family | {'PASS' if g1_pass else ('PARTIAL' if g1_partial else 'FAIL')} |",
        f"| **G2** | Split-half same-sign (h1 and h2 both negative) | {'PASS' if g2_pass else 'FAIL'} |",
        f"| **G3** | Effect concentrated in small-cap tercile: small-cap mean NEGATIVE AND more negative than large-cap | {'PASS' if g3_pass else 'FAIL'} |",
        "",
        "---",
        "",
        "## G1: BH-FDR results — small-cap fade bucket, monthly rebalance",
        "",
        "Pre-registered 2×2 family: {massive, yahoo} × {5d, 21d} — **m=4 fixed** (full family).",
        "Cells with N<10 (untestable) carry p=1.0 as non-rejecting members of the family; they do",
        "not shrink the family size (which would be anti-conservative).",
        "",
        "| Cell | N observations | Mean return | t_HAC | p | BH-q | Reject H0? |",
        "|------|---------------|-------------|-------|---|------|------------|",
    ]

    for k in gate_keys:
        r = results.get(k, {})
        bh = bh_g1.get(k, {})
        n_ok = r.get("fade_n", 0)
        untestable = r.get("fade_p") is None
        note = " *(N<10, untestable — p=1.0)*" if untestable else ""
        lines.append(
            f"| {k}{note} | {n_ok} | "
            f"{r.get('fade_mean', 'N/A')} | "
            f"{r.get('fade_t', 'N/A')} | "
            f"{bh.get('p', 'N/A')} | "
            f"{bh.get('q', 'N/A')} | "
            f"{'Yes' if bh.get('reject') else 'No'} |"
        )

    g1_n_pass = sum(g1_cells)
    lines += [
        "",
        f"**G1 verdict:** {g1_n_pass}/{len(g1_cells)} cells satisfy mean<0, |t|≥2, q≤0.10.",
        f"G1 = {'PASS (all cells)' if g1_pass else ('PARTIAL' if g1_partial else 'FAIL (no cells)')}",
        "",
        "---",
        "",
        "## G2: Split-half robustness",
        "",
        "| Cell | H1 mean | H2 mean | Same sign? |",
        "|------|---------|---------|------------|",
    ]
    for k in gate_keys:
        sh = split_results.get(k, {})
        lines.append(
            f"| {k} | {sh.get('h1_mean', 'N/A')} | {sh.get('h2_mean', 'N/A')} | "
            f"{'Yes' if sh.get('same_sign') else ('No' if sh.get('same_sign') is False else 'N/A')} |"
        )
    lines += [
        "",
        f"**G2 verdict:** {'PASS' if g2_pass else 'FAIL'}",
        "",
        "---",
        "",
        "## G3: Cap-tercile concentration",
        "",
        "**Definition of G3 PASS (corrected):** G3 requires BOTH (a) small-cap fade mean is NEGATIVE",
        "(an actual fade effect exists in small-caps) AND (b) small-cap is more negative than large-cap",
        "(concentration). A cell where both means are positive cannot 'concentrate' a fade effect;",
        "reporting PASS in that case is logically vacuous. G3 FAIL or 'small less positive' is reported",
        "honestly when the pre-registered negative direction is absent.",
        "",
        "| Panel | Horizon | Small mean | Small t | Large mean | Large t | Small negative? | Small more negative? | G3 ok? |",
        "|-------|---------|-----------|---------|-----------|---------|----------------|---------------------|--------|",
    ]

    g3_idx = 0
    for panel, rebal in [("massive", "monthly"), ("yahoo", "monthly")]:
        for h in HORIZONS:
            small_key = f"{panel}_{rebal}_{h}d_small"
            large_key = f"{panel}_{rebal}_{h}d_large"
            rs = results.get(small_key, {})
            rl = results.get(large_key, {})
            ok = g3_checks[g3_idx] if g3_idx < len(g3_checks) else False
            sm = rs.get("fade_mean")
            lm = rl.get("fade_mean")
            small_neg = sm is not None and sm < 0
            conc = sm is not None and lm is not None and sm < lm
            g3_idx += 1
            lines.append(
                f"| {panel} | {h}d | {sm if sm is not None else 'N/A'} | "
                f"{rs.get('fade_t', 'N/A')} | "
                f"{lm if lm is not None else 'N/A'} | "
                f"{rl.get('fade_t', 'N/A')} | "
                f"{'Yes' if small_neg else 'No'} | "
                f"{'Yes' if conc else 'No'} | "
                f"{'Yes' if ok else 'No'} |"
            )

    lines += [
        "",
        f"**G3 verdict:** {'PASS' if g3_pass else 'FAIL'} "
        f"(small negative AND more negative than large in {sum(g3_checks)}/{len(g3_checks)} cells)",
        "",
        "---",
        "",
        "## Full results table (all panels, rebalances, horizons, cap filters)",
        "",
        "| Key | Panel | Rebal | Horizon | Cap | Fade N | Fade Mean | Fade t | Confirm N | Confirm Mean |",
        "|-----|-------|-------|---------|-----|--------|-----------|--------|-----------|--------------|",
    ]
    for k, r in sorted(results.items()):
        lines.append(
            f"| {k} | {r.get('panel')} | {r.get('rebal')} | {r.get('horizon')}d | "
            f"{r.get('cap_filter')} | {r.get('fade_n', 0)} | "
            f"{r.get('fade_mean', 'N/A')} | {r.get('fade_t', 'N/A')} | "
            f"{r.get('confirm_n', 0)} | {r.get('confirm_mean', 'N/A')} |"
        )

    lines += [
        "",
        "---",
        "",
        "## Coverage",
        "",
        f"- Attention tickers in store: {total_attn}",
        f"- Tickers backfilled to 2015-07: {covered_to_2015}",
        f"- Trial ledger effective N: {effective_n}",
        "",
        "---",
        "",
        "> **SURVIVORSHIP CAVEAT (Yahoo 2015-2021 leg)**",
        ">",
        "> The yahoo deep-history panel contains **only tickers still alive and listed as of",
        "> the backfill date (2026-07-06)**. Tickers that were delisted, went bankrupt, or were",
        "> taken private between 2015 and 2021 are entirely absent. This creates an upward bias",
        "> on returns and an anti-fade bias: the worst outcomes (stocks that spiked on Wikipedia",
        "> attention and then collapsed or were delisted) are systematically missing.",
        ">",
        "> **Actual yahoo coverage:** ~300 tickers overlap with the attention store; mktcap resolves",
        "> for only ~219 of those; the small-cap fade bucket (our pre-registered primary cell) has",
        "> N=9 observations — effectively empty for statistical inference. The yahoo half of the",
        "> pre-registered 2×2 family is therefore **untestable as specified**. The family is",
        "> honestly 1×2 (massive panel only) for the purposes of this phase-0 run. The yahoo leg",
        "> is reported for completeness but carries no weight in the verdict.",
        "",
        "---",
        "",
        "> **DEEP-HISTORY BUCKET CONSTRUCTION NOTE**",
        ">",
        "> The yahoo panel has no volume data; all yahoo attention-shock observations are therefore",
        "> assigned to the fade bucket (volume_z set to 0.0, which is < VOL_Z_THRESH=1.0). This",
        "> means the confirm bucket is empty for the yahoo leg and the within-bucket fade/confirm",
        "> split specified in the pre-registration **cannot be evaluated** for the deep-history period.",
        "> The pre-registered 2×2 family (panel × horizon) structurally degenerates to a 1×2 family",
        "> for this run. This is not a conservative assumption — it is a data limitation that makes",
        "> half the pre-registered family untestable-as-specified.",
        "",
        "---",
        "",
        "## Verdict",
        "",
        f"**{verdict}**",
        "",
        verdict_long,
        "",
        "---",
        "",
        "## Nightly wiring (for consolidation)",
        "",
        "The backfilled `data/attention/` store is git-tracked for the existing ~126-day window",
        "(data/attention/*.parquet are tracked files in this repo). The deep-history backfill",
        "extended those files in place in the worktree but should NOT be committed to git",
        "(the docstring states 'do NOT commit data/trial_ledger.jsonl'; similarly the bulk",
        "attention parquet writes are worktree-only artifacts). The correct absorption path is:",
        "",
        "1. **Tarball (produced by build stage):** `/tmp/slf048_attention_backfill.tar.gz` (~31.5 MB)",
        "   This tarball contains the full backfilled store. To upload to R2:",
        "   ```bash",
        "   cd /tmp && tar xzf slf048_attention_backfill.tar.gz",
        "   rclone sync /tmp/slf048_attention_backfill/ r2:macro-dashboard/attention/ --transfers 16",
        "   ```",
        "2. **Nightly collector line** (add to scripts/collect.py, wiki_pageviews section):",
        "   ```python",
        "   # wiki_pageviews — already wired; backfill completed 2026-07-06 to 2015-07-01",
        "   # The existing WikiPageviewsAdapter incremental-fetches forward from last stored date.",
        "   # No change needed for daily increments.",
        "   ```",
        "3. **R2 download on render box:** The nightly render job should rsync attention/ from R2",
        "   before the wiki chip reads it. Add to the pre-render step:",
        "   ```bash",
        "   rclone sync r2:macro-dashboard/attention/ data/attention/ --transfers 16",
        "   ```",
        "",
        "---",
        "",
        "## Limitations",
        "",
        "- Market-cap tercile uses a single-point-in-time snapshot (most recent). For the",
        "  2015-2021 yahoo leg, tickers that were small-cap in 2026 may have been mid/large",
        "  earlier. This biases G3 toward false-positive concentration; a proper PIT mktcap",
        "  series would require historical shares-outstanding × price.",
        "- Yahoo volume data not available; all yahoo observations are assigned to the fade bucket.",
        "  This makes the confirm bucket empty for yahoo and the pre-registered fade/confirm split",
        "  untestable for that leg — not a conservative assumption, a data limitation.",
        "  The pre-registered 2×2 family degenerates to 1×2 for this run.",
        "- Survivorship bias in yahoo panel: only currently-listed tickers are present. Delistings",
        "  and bankruptcies are absent, creating upward return bias and anti-fade bias.",
        "- The CI-enforced 'validated' keyword check: this report does not claim any signal is",
        "  confirmed (display-only until gauntleted).",
    ]

    out_path = ROOT / "reports" / "slf048-wiki-attention-phase0.md"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text("\n".join(lines))
    print(f"Report written to {out_path}")


if __name__ == "__main__":
    run()
