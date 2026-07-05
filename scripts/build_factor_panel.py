"""Factor Intelligence panel builder — Block-A attribution + Block-B percentiles.

OFF-RENDER-PATH PLACEMENT: this script is a standalone nightly step that runs
BEFORE build_site.py in CI.  It writes data/factordata/panel/YYYY-MM/panel.parquet
(snappy-compressed, one partition per calendar month).  build_site.py reads the
pre-computed panel; it does not recompute factor betas inline.

JOIN CONTRACT: studies join this panel against the replay artifact
(data/replay/standout_replay.parquet) on (ticker, date) where date == signal_date.
No other program may write to data/factordata/panel/.  No panel column may be added
without a v2 version stamp.

V1 FREEZE: all Block-A and Block-B parameters are frozen as of the adjudication
ruling 2026-07-04.  See research/FACTOR_INTELLIGENCE_MASTERPLAN_BY_FABLE.md §3
for the authoritative spec.  Any parameter change requires a v2 stamp.

SCOPE (P1-A only — see masterplan §7):
  - Block-A: per-(ticker,date) rolling attribution vs ordered orthogonal streams
  - Block-B: trailing cross-sectional percentiles of equity_factors legs
  - alpha_z_house read-through from site/factordata/alpha.json (nightly residual_alpha)
  - Panel schema + partitioning + version stamp

OUT OF SCOPE FOR THIS PR (added by later PRs):
  - Twin computation (P1-B): twin_rel_20d, twin_bleed_flag, twin_n_peers, twin_fallback
  - Style-regime classifier (P1-C): dna_class, style_regime, style_regime_pending
  - Pair G detector / factor_attention reflex (P1-D)

PIT SEMANTICS (R3 ruling 2026-07-04):
  Block-B *_pct columns (value_pct, profitability_pct, quality_pct, payout_pct,
  low_vol_pct) and alpha_z_house are SINGLE-DAY SNAPSHOT values sourced from
  factors.json and alpha.json respectively.  Stamping them onto historical build
  dates is lookahead.  RULING: these columns are emitted ONLY for build dates
  matching the snapshot's own as_of date; all other (backfill) dates receive None.

  Historical backfill of these columns is a separate follow-up (equity_factors
  backtest mode asof=date + residual_alpha recompute) required BEFORE P3
  H3/H2-stratification runs on history.  This limitation is documented here and
  in the run log.

CAUSAL ORTHOGONALIZATION (R1 ruling 2026-07-04):
  _orthogonalize_series uses ROLLING causal coefficients (252d window, shift(1))
  rather than static full-history Gram-Schmidt.  This prevents future data from
  leaking into historical orthogonalization values.  Mirrors the convention in
  engine/residual_alpha.py _causal_beta (lines 55-58).

Usage:
    python -m scripts.build_factor_panel [--data-root PATH] [--start YYYY-MM-DD]
        [--end YYYY-MM-DD] [--tickers SYM,SYM,...] [--out-root PATH]

    --data-root   Path to the repo root whose data/ caches to read.
                  Default: the repo root this script lives in.
                  For dev sample runs: '/Users/chriswong/Documents/Cluade/Macro Dashboard'
    --start       First date to build (inclusive).  Default: 1 year back.
    --end         Last date to build (inclusive).   Default: latest available date.
    --tickers     Comma-separated subset, e.g. AAPL,MSFT.  Default: all breadth names.
    --out-root    Root under which data/factordata/panel/ is written.
                  Default: same as --data-root.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

# ── path bootstrap ───────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("build_factor_panel")

# ── frozen v1 constants ──────────────────────────────────────────────────────
FACTOR_MODEL = "v1"

# Block-A: ordered stream keys and their Yahoo / data source identifiers.
# Priority order for Gram-Schmidt orthogonalization.
STREAM_ORDER = ["mkt", "sector", "size", "growth", "rates", "dollar", "ai_theme", "china"]

# Streams that use a fixed-ticker Yahoo parquet.
STREAM_YAHOO: dict[str, str] = {
    "mkt":    "SPY",
    "size":   "IWM",
    "growth": "QQQ",
    "rates":  "TLT",
    "dollar": "DX-Y.NYB",
    "china":  "FXI",
}

# GICS sector → SPDR sector ETF map (from scripts/grade_us_board.py lines 111-117).
GICS_ETF: dict[str, str] = {
    "Energy": "XLE",
    "Information Technology": "XLK",
    "Technology": "XLK",
    "Financials": "XLF",
    "Health Care": "XLV",
    "Industrials": "XLI",
    "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP",
    "Utilities": "XLU",
    "Materials": "XLB",
    "Real Estate": "XLRE",
    "Communication Services": "XLC",
    "Communications": "XLC",
}

# Block-A estimation parameters (frozen from engine/residual_alpha.py conventions
# and masterplan §3.1):
BETA_WIN = 252          # rolling window
MIN_PERIODS = 126       # max(252//2, 15)
VASICEK_W = 0.66        # Vasicek shrinkage weight (toward cross-sectional mean)
# R7: no local winsorization — winsorization is inherited upstream (factors.json
# z-scores are already _winsor_z'd in equity_factors.py); no local winsor applied here by design.

# Attribution windows (masterplan §3.1):
ATT_WINDOWS = [5, 20, 60]

# Zero-return guard threshold:
ZERO_RET_THRESH = 1e-6

# Block-B legs (subset of equity_factors FACTOR_LABELS per masterplan §3.2):
BLOCK_B_LEGS = ["value", "profitability", "quality", "payout", "low_vol"]

# China-exposed sectors for the china stream (masterplan §3.1).
# A name is china-eligible if its sector is in this set OR if it is manually
# flagged (not implemented in P1-A — sector gate only).
# R9: This is a FROZEN V1 PROXY CHOICE — manual ADR flag deferred to P1-B.
# The exact set is printed in the run log at startup.
CHINA_SECTORS: frozenset[str] = frozenset({
    "Information Technology", "Technology",
    "Communication Services", "Communications",
    "Consumer Discretionary",
    "Materials",
    "Industrials",
})

# R4 — FIXED SCHEMA: frozen 40-column v1 set.  Every partition is reindexed to
# exactly these columns (missing → None) before writing.  China contrib columns
# are always present; non-china tickers have None for those columns.
# Adding a column requires a v2 version stamp and a new migration PR.
PANEL_COLUMNS: list[str] = [
    # ── identity ──────────────────────────────────────────────────────────────
    "ticker",
    "date",
    "factor_model",
    # ── Block-A betas (shrunk, causal rolling 252d) ───────────────────────────
    "beta_mkt",
    "beta_sector",
    "beta_size",
    "beta_growth",
    "beta_rates",
    "beta_dollar",
    "beta_ai_theme",
    "beta_china",
    # ── Block-A attribution — 5d window ───────────────────────────────────────
    "contrib_mkt_5d",
    "contrib_sector_5d",
    "contrib_size_5d",
    "contrib_growth_5d",
    "contrib_rates_5d",
    "contrib_dollar_5d",
    "contrib_ai_theme_5d",
    "contrib_china_5d",
    "resid_ret_5d",
    "alibi_share_5d",
    # ── Block-A attribution — 20d window ──────────────────────────────────────
    "contrib_mkt_20d",
    "contrib_sector_20d",
    "contrib_size_20d",
    "contrib_growth_20d",
    "contrib_rates_20d",
    "contrib_dollar_20d",
    "contrib_ai_theme_20d",
    "contrib_china_20d",
    "resid_ret_20d",
    "alibi_share_20d",
    # ── Block-A attribution — 60d window ──────────────────────────────────────
    "contrib_mkt_60d",
    "contrib_sector_60d",
    "contrib_size_60d",
    "contrib_growth_60d",
    "contrib_rates_60d",
    "contrib_dollar_60d",
    "contrib_ai_theme_60d",
    "contrib_china_60d",
    "resid_ret_60d",
    "alibi_share_60d",
    # ── Block-A single-day residual ───────────────────────────────────────────
    "resid_ret_1d",
    # ── Block-B cross-sectional percentiles (PIT: snapshot as_of date only) ───
    "value_pct",
    "profitability_pct",
    "quality_pct",
    "payout_pct",
    "low_vol_pct",
    # ── Residual alpha read-through (PIT: snapshot as_of date only) ───────────
    "alpha_z_house",
]


# ── helpers ──────────────────────────────────────────────────────────────────
def _read_yahoo(data_root: Path, symbol: str) -> pd.Series | None:
    """Load close series from data/yahoo/<symbol>.parquet, return daily pct_change."""
    p = data_root / "data" / "yahoo" / f"{symbol}.parquet"
    if not p.exists():
        log.warning("missing yahoo parquet: %s", p)
        return None
    df = pd.read_parquet(p)
    if "close" not in df.columns:
        log.warning("no 'close' column in %s", p)
        return None
    s = df["close"].astype(float)
    s.index = pd.to_datetime(s.index)
    return s.sort_index().pct_change(fill_method=None)


def _read_breadth_closes(data_root: Path) -> pd.DataFrame:
    """Combined S&P 1500 breadth close matrix (from engine/equity_factors._closes logic)."""
    groups = ["breadth", "smallcap_breadth", "midcap_breadth"]
    frames = []
    for grp in groups:
        p = data_root / "data" / grp / "_closes_cache.parquet"
        if p.exists():
            frames.append(pd.read_parquet(p))
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, axis=1, sort=False)  # R8: explicit sort=False
    return out.loc[:, ~out.columns.duplicated()].sort_index()


def _read_constituents(data_root: Path) -> dict[str, tuple[str, str]]:
    """Return {ticker: (name, sector)} from breadth constituents parquets."""
    groups = ["breadth", "smallcap_breadth", "midcap_breadth"]
    out: dict[str, tuple[str, str]] = {}
    for grp in groups:
        p = data_root / "data" / grp / "constituents.parquet"
        if p.exists():
            meta = pd.read_parquet(p)
            for t, row in meta.iterrows():
                out.setdefault(str(t), (str(row.get("name", t)), str(row.get("sector", "—"))))
    return out


def _read_ai_infra_returns(data_root: Path) -> pd.Series | None:
    """Load the ai_infra basket EW return series from site/basketdata/baskets.json.

    The JSON stores cumulative index levels; we convert to daily pct_change.
    Key path: baskets_json["chart"]["baskets"]["ai_infra"] (list of floats/None,
    aligned to baskets_json["chart"]["dates"]).
    """
    p = data_root / "site" / "basketdata" / "baskets.json"
    if not p.exists():
        log.warning("missing baskets.json at %s", p)
        return None
    try:
        d = json.loads(p.read_text())
        dates = d["chart"]["dates"]
        levels = d["chart"]["baskets"]["ai_infra"]
    except (KeyError, json.JSONDecodeError) as e:
        log.warning("baskets.json parse error: %s", e)
        return None
    idx = pd.to_datetime(dates)
    s = pd.Series(data=[float(v) if v is not None else float("nan") for v in levels],
                  index=idx, name="ai_theme")
    return s.sort_index().pct_change(fill_method=None)


def _read_alpha_z(data_root: Path) -> tuple[dict[str, float] | None, pd.Timestamp | None]:
    """Read site/factordata/alpha.json per_ticker alpha z-scores (alpha_z_house).

    R3 RULING (2026-07-04): Returns (alpha_z_map, as_of_date).  alpha_z_house is
    emitted ONLY for build dates matching as_of_date; other dates get None.
    as_of_date is taken from the 'as_of' field in the JSON (falls back to today
    if absent).

    The 'alpha' key in per_ticker is the sector-neutral residual-momentum z per
    engine/residual_alpha.compute_residual_alpha (the headline SECTOR-NEUTRAL z).
    """
    p = data_root / "site" / "factordata" / "alpha.json"
    if not p.exists():
        log.warning("missing alpha.json — alpha_z_house will be null")
        return None, None
    try:
        d = json.loads(p.read_text())
        per_ticker = d.get("per_ticker", {})
        az_map = {t: float(v["alpha"]) for t, v in per_ticker.items()
                  if v.get("alpha") is not None}
        as_of_raw = d.get("as_of")
        if as_of_raw:
            as_of = pd.Timestamp(as_of_raw)
            log.info("alpha.json as_of: %s (used for R3 PIT gate)", as_of.date())
        else:
            as_of = pd.Timestamp.today().normalize()
            log.warning("alpha.json has no 'as_of' field — using today (%s) for R3 PIT gate",
                        as_of.date())
        return az_map, as_of
    except Exception as e:
        log.warning("alpha.json parse error: %s", e)
        return None, None


def _read_factors_json(data_root: Path) -> tuple[pd.DataFrame | None, pd.Timestamp | None]:
    """Read site/factordata/factors.json table for Block-B factor z-scores.

    R3 RULING (2026-07-04): Returns (factors_df, as_of_date).  Block-B *_pct
    columns are emitted ONLY for build dates matching as_of_date; other dates
    get None.  as_of_date is taken from the 'as_of' field (falls back to today
    if absent).

    factors.json is the nightly equity_factors.compute_factors() output — we read
    the pre-computed z-scores and convert to trailing cross-sectional percentiles
    at build time per the PIT guard (PREREG §2.5).
    """
    p = data_root / "site" / "factordata" / "factors.json"
    if not p.exists():
        log.warning("missing factors.json — Block-B will be null")
        return None, None
    try:
        d = json.loads(p.read_text())
        table = d.get("table", [])
        if not table:
            return None, None
        df = pd.DataFrame(table)
        if "ticker" in df.columns:
            df = df.set_index("ticker")
        as_of_raw = d.get("as_of")
        if as_of_raw:
            as_of = pd.Timestamp(as_of_raw)
            log.info("factors.json as_of: %s (used for R3 PIT gate)", as_of.date())
        else:
            as_of = pd.Timestamp.today().normalize()
            log.warning("factors.json has no 'as_of' field — using today (%s) for R3 PIT gate",
                        as_of.date())
        return df, as_of
    except Exception as e:
        log.warning("factors.json parse error: %s", e)
        return None, None


# ── Block-A core functions ───────────────────────────────────────────────────
def _causal_rolling_beta(y: pd.Series, x: pd.Series,
                         win: int, minp: int) -> pd.Series:
    """Rolling cov(y,x)/var(x) with 1-day lag (causal — uses [t-win, t-1] data only).

    Copies engine/residual_alpha._causal_beta exactly:
        return (y.rolling(win, min_periods=minp).cov(x)
                .div(x.rolling(win, min_periods=minp).var(), axis=0)).shift(1)

    The .shift(1) ensures that the beta used at row t was estimated from data ending
    at t-1 — no look-ahead.
    """
    cov = y.rolling(win, min_periods=minp).cov(x)
    var = x.rolling(win, min_periods=minp).var()
    beta = (cov / var.replace(0, float("nan"))).shift(1)
    return beta


def _vasicek_shrink(beta_raw: pd.DataFrame, w: float) -> pd.DataFrame:
    """Vasicek shrinkage: beta_shrunk = w * beta_raw + (1-w) * cross_sectional_mean.

    Applied row-wise (same-day cross-section), matching engine/residual_alpha._shrink.
    w >= 1 → no-op.
    """
    if w is None or w >= 1.0:
        return beta_raw
    cs_mean = beta_raw.mean(axis=1)
    return beta_raw.mul(w).add(cs_mean.mul(1.0 - w), axis=0)


def _orthogonalize_series(v: pd.Series, prior_orth_streams: list[pd.Series]) -> pd.Series:
    """Causal rolling Gram-Schmidt: residualize v against each prior causal-orth stream.

    R1 RULING (2026-07-04): replaces the static full-history Gram-Schmidt with a
    ROLLING CAUSAL coefficient, matching engine/residual_alpha.py _causal_beta
    convention (lines 55-58).

    For each prior causally-orthogonalized stream p (in STREAM_ORDER priority order):
        coef_p[t] = rolling_cov(v, p, 252d) / rolling_var(p, 252d)  [.shift(1)]
        v_orth[t] -= coef_p[t] * p[t]

    The .shift(1) on coef_p ensures the coefficient used at t was estimated from
    data ending at t-1 (no look-ahead at any historical row).  orth_p passed in is
    already causally orthogonalized (caller's responsibility — mirrors the s̃ ⟂ m
    construction in residual_alpha.residuals).

    Returns: the causally-orthogonalized series (same index as v).
    """
    result = v.copy().astype(float)
    for p in prior_orth_streams:
        # Rolling causal coefficient: cov(result, p) / var(p), lagged 1 day.
        cov_rp = result.rolling(BETA_WIN, min_periods=MIN_PERIODS).cov(p)
        var_p = p.rolling(BETA_WIN, min_periods=MIN_PERIODS).var()
        coef = (cov_rp / var_p.replace(0, float("nan"))).shift(1)
        result = result - coef * p
    return result


def _build_stream_returns(data_root: Path, tkr_sector: dict[str, tuple[str, str]],
                          date_index: pd.DatetimeIndex) -> dict[str, pd.Series]:
    """Build raw (pre-orthogonalized) daily return series for all streams.

    Returns {stream_key: pd.Series of daily returns, index=dates}.
    Streams requiring per-ticker handling (sector, china) are returned as
    single representative series here; the per-ticker logic is handled in
    _compute_block_a_for_ticker.
    """
    streams: dict[str, pd.Series] = {}

    # Fixed-ticker Yahoo streams:
    for key, sym in STREAM_YAHOO.items():
        s = _read_yahoo(data_root, sym)
        if s is not None:
            streams[key] = s.reindex(date_index)
        else:
            log.warning("stream %s (%s) unavailable — will be skipped", key, sym)

    # ai_theme: basket returns
    ai = _read_ai_infra_returns(data_root)
    if ai is not None:
        streams["ai_theme"] = ai.reindex(date_index)
    else:
        log.warning("ai_theme stream unavailable — will be skipped")

    # Sector stream returns are ETF-per-ticker — not stored here as a single series.
    # The 'sector' key is populated per-ticker inside _compute_block_a_for_ticker.

    return streams


def _get_sector_etf_return(data_root: Path, sector: str,
                           etf_cache: dict[str, pd.Series | None]) -> pd.Series | None:
    """Fetch (and cache) the SPDR sector ETF return series for a GICS sector."""
    etf = GICS_ETF.get(sector, "SPY")  # SPY fallback per masterplan §3.1
    if etf not in etf_cache:
        s = _read_yahoo(data_root, etf)
        etf_cache[etf] = s
    return etf_cache[etf]


def _compute_block_a_for_ticker(
    ticker: str,
    ticker_returns: pd.Series,
    sector: str,
    stream_raw: dict[str, pd.Series],
    etf_cache: dict[str, pd.Series | None],
    data_root: Path,
    is_china_exposed: bool,
) -> pd.DataFrame:
    """Compute Block-A beta time-series for one ticker.

    Returns a DataFrame indexed by date with columns:
        beta_{stream}   for each stream applicable to this ticker

    Steps:
    1. Causal rolling orthogonalization (R1 ruling): each raw stream is
       residualized against all higher-priority causally-orthogonalized streams
       using a rolling 252d coefficient with .shift(1) — same convention as
       engine/residual_alpha._causal_beta.  No future data leaks into any
       historical orth value.
    2. Compute causal rolling betas (252d, min_periods=126, shift(1)) on the
       causally-orthogonalized streams.
    3. Apply Vasicek shrinkage cross-sectionally (caller handles cross-
       sectional mean — here we return raw betas; shrinkage is applied in
       the outer loop after collecting all tickers on the same date).
    """
    # Determine applicable streams for this ticker:
    streams_to_use = [k for k in STREAM_ORDER if k != "china"]
    if is_china_exposed:
        streams_to_use.append("china")

    # Build sector return series for this ticker:
    sector_ret = None
    if "sector" in streams_to_use:
        sector_ret = _get_sector_etf_return(data_root, sector, etf_cache)
        if sector_ret is None:
            # Fallback: SPY already in mkt; skip sector stream
            streams_to_use = [k for k in streams_to_use if k != "sector"]

    # Assemble aligned raw return matrix for the streams we have:
    raw: dict[str, pd.Series] = {}
    for key in streams_to_use:
        if key == "sector":
            raw[key] = sector_ret
        elif key in stream_raw:
            raw[key] = stream_raw[key]
        else:
            # Stream data unavailable — skip it
            pass

    # Only process streams we actually have data for:
    avail_streams = [k for k in streams_to_use if k in raw and raw[k] is not None]

    # Causal rolling orthogonalization (R1): each stream is residualized against
    # all higher-priority causally-orthogonalized streams using rolling 252d
    # coefficients with .shift(1) — no future data leaks into any historical row.
    orth: dict[str, pd.Series] = {}
    orth_list: list[pd.Series] = []  # ordered list of causally-orthogonalized streams
    for key in STREAM_ORDER:
        if key not in avail_streams:
            continue
        v = raw[key].copy().astype(float)
        # Orthogonalize against all prior streams:
        v_orth = _orthogonalize_series(v, orth_list)
        orth[key] = v_orth
        orth_list.append(v_orth)

    # Compute rolling causal betas for each orthogonalized stream:
    y = ticker_returns.astype(float)
    beta_cols: dict[str, pd.Series] = {}
    for key, x_orth in orth.items():
        b = _causal_rolling_beta(y, x_orth, BETA_WIN, MIN_PERIODS)
        beta_cols[f"beta_{key}"] = b

    if not beta_cols:
        return pd.DataFrame()
    return pd.DataFrame(beta_cols)


def _compute_attribution(betas_t: dict[str, float],
                         stream_rets: dict[str, float],
                         realized_ret: float,
                         window: int) -> dict[str, float | None]:
    """Compute per-stream contribution shares and alibi_share for one (ticker,date,window).

    masterplan §3.1:
        contrib_{stream}_W = beta_{stream} × stream_return_W / abs(realized_return_W)
            clipped to [-2, +2]
        alibi_share_W = Σ|contrib_W| / (Σ|contrib_W| + |resid_ret_W|)
            bounded [0,1] by construction — no clip
        resid_ret_W = realized_return_W - Σ(beta_{stream} × stream_return_W)

    Zero-return guard: if |realized_return_W| < 1e-6, all shares and alibi_share = None.
    """
    suffix = f"_{window}d"
    out: dict[str, float | None] = {}

    if abs(realized_ret) < ZERO_RET_THRESH:
        # Zero-return guard — all shares None
        for key in betas_t:
            stream_key = key.replace("beta_", "")
            out[f"contrib_{stream_key}{suffix}"] = None
        out[f"resid_ret{suffix}"] = None
        out[f"alibi_share{suffix}"] = None
        return out

    # Raw contributions (beta × stream_return, in return units):
    contrib_raw: dict[str, float] = {}
    for key, beta in betas_t.items():
        stream_key = key.replace("beta_", "")
        sr = stream_rets.get(stream_key, 0.0)
        if sr is None or np.isnan(sr) or np.isnan(beta):
            contrib_raw[stream_key] = float("nan")
        else:
            contrib_raw[stream_key] = float(beta) * float(sr)

    # Residual return:
    valid_contribs = [v for v in contrib_raw.values() if not np.isnan(v)]
    total_explained = sum(valid_contribs)
    resid_ret = float(realized_ret) - total_explained
    out[f"resid_ret{suffix}"] = resid_ret

    # Contribution shares (normalized by |realized_return|, clipped to [-2, +2]):
    for stream_key, cr in contrib_raw.items():
        if np.isnan(cr):
            share = None
        else:
            share = float(np.clip(cr / abs(realized_ret), -2.0, 2.0))
        out[f"contrib_{stream_key}{suffix}"] = share

    # Alibi share: Σ|contrib_raw| / (Σ|contrib_raw| + |resid_ret|)
    # Uses raw contribution magnitudes (scale-invariant by construction):
    sum_abs_contrib = sum(abs(v) for v in valid_contribs)
    denom = sum_abs_contrib + abs(resid_ret)
    if denom > 0:
        alibi = sum_abs_contrib / denom
        # R6: never abort the nightly on one row — log + clip instead of bare assert.
        if not (0.0 <= alibi <= 1.0 + 1e-10):
            log.warning("alibi_share out of bounds (fp anomaly): %s — clipping to [0,1]", alibi)
        alibi = float(np.clip(alibi, 0.0, 1.0))  # defensive clip for fp edge cases
    else:
        alibi = None
    out[f"alibi_share{suffix}"] = alibi

    return out


def _compute_block_b_percentiles(factors_df: pd.DataFrame,
                                  ticker: str) -> dict[str, float | None]:
    """Compute Block-B cross-sectional percentiles (1-99) for one ticker.

    Trailing cross-sectional percentile as of the latest available date in
    the factors_df (which is the nightly equity_factors output — a single
    cross-section snapshot).

    PIT guard (PREREG §2.5): breakpoints are computed on the cross-section
    available at the panel build date, never panel-global.

    R3 RULING (2026-07-04): this function is ONLY called for the snapshot's
    own as_of date.  Historical (backfill) build dates receive None for all
    Block-B columns — they are NOT filled from this snapshot.  Historical
    backfill of Block-B columns is a separate follow-up task (equity_factors
    backtest mode asof=date + residual_alpha recompute) required BEFORE P3
    H3/H2-stratification runs on history.  The caller enforces this gate via
    the factors_pit_ok guard in build_panel().
    """
    out: dict[str, float | None] = {}
    if ticker not in factors_df.index:
        for leg in BLOCK_B_LEGS:
            out[f"{leg}_pct"] = None
        return out

    for leg in BLOCK_B_LEGS:
        if leg not in factors_df.columns:
            out[f"{leg}_pct"] = None
            continue
        col = factors_df[leg].dropna()
        val = factors_df.at[ticker, leg]
        if pd.isna(val) or len(col) < 5:
            out[f"{leg}_pct"] = None
            continue
        # Cross-sectional percentile rank (1-99):
        n = len(col)
        rank = float((col < val).sum() + 0.5 * (col == val).sum()) / n
        pct = float(np.clip(rank * 98.0 + 1.0, 1.0, 99.0))
        out[f"{leg}_pct"] = round(pct, 2)
    return out


# ── main build function ──────────────────────────────────────────────────────
def build_panel(
    data_root: Path,
    out_root: Path,
    start_date: pd.Timestamp | None = None,
    end_date: pd.Timestamp | None = None,
    tickers: list[str] | None = None,
) -> pd.DataFrame:
    """Build the factor panel for [start_date, end_date] and the given tickers.

    Writes monthly partitions to out_root/data/factordata/panel/YYYY-MM/panel.parquet.
    Returns the full panel DataFrame.
    """
    t0 = time.time()
    log.info("=== build_factor_panel v1 start ===")
    log.info("data_root=%s  out_root=%s", data_root, out_root)
    # R9: log china-eligible sectors (frozen v1 proxy; manual ADR flag deferred to P1-B):
    log.info("CHINA_SECTORS (v1 proxy, frozen): %s", sorted(CHINA_SECTORS))

    # ── 1. Load universe ─────────────────────────────────────────────────────
    ns = _read_constituents(data_root)
    closes = _read_breadth_closes(data_root)
    if closes.empty:
        log.error("no breadth closes found — aborting")
        return pd.DataFrame()

    closes.index = pd.to_datetime(closes.index)
    closes = closes.sort_index()

    if tickers is not None:
        closes = closes[[t for t in tickers if t in closes.columns]]
    if closes.empty:
        log.error("no tickers in closes after filter — aborting")
        return pd.DataFrame()

    log.info("universe: %d tickers, %d dates", len(closes.columns), len(closes))

    # ── 2. Determine date range ───────────────────────────────────────────────
    # We need at least BETA_WIN days of history before start_date to compute betas.
    all_dates = closes.index
    if end_date is None:
        end_date = all_dates[-1]
    else:
        end_date = pd.Timestamp(end_date)
    if start_date is None:
        # Default: 1 year back from end
        start_date = end_date - pd.DateOffset(years=1)
    else:
        start_date = pd.Timestamp(start_date)

    # We need pre-history for beta estimation — load full history for orthogonalization:
    build_dates = all_dates[(all_dates >= start_date) & (all_dates <= end_date)]
    if len(build_dates) == 0:
        log.error("no dates in [%s, %s]", start_date, end_date)
        return pd.DataFrame()
    log.info("build dates: %d  (%s to %s)", len(build_dates),
             build_dates[0].date(), build_dates[-1].date())

    # ── 3. Load stream returns (global, pre-orth) ─────────────────────────────
    log.info("loading stream return series...")
    stream_raw = _build_stream_returns(data_root, ns, all_dates)
    # Sector ETF cache (loaded lazily per sector key):
    etf_cache: dict[str, pd.Series | None] = {}

    # ── 4. Load Block-B factors snapshot ─────────────────────────────────────
    log.info("loading Block-B factors snapshot...")
    factors_df, factors_as_of = _read_factors_json(data_root)
    if factors_df is None:
        log.warning("no factors.json — Block-B percentiles will be null")

    # ── 5. Load alpha_z_house ─────────────────────────────────────────────────
    log.info("loading alpha_z_house from alpha.json...")
    alpha_z_map, alpha_as_of = _read_alpha_z(data_root)
    if alpha_z_map is None:
        log.warning("no alpha_z_house data — column will be null")

    # R3 PIT gate: Block-B and alpha_z_house emitted ONLY for build dates
    # matching their respective snapshot as_of dates.  Other (backfill) dates
    # receive None.  Historical backfill of these columns is deferred to the
    # equity_factors backtest mode asof=date + residual_alpha recompute pass
    # required before P3 H3/H2-stratification runs on history.
    log.info("R3 PIT gate: Block-B emitted only for %s, alpha_z_house only for %s",
             factors_as_of.date() if factors_as_of is not None else "N/A",
             alpha_as_of.date() if alpha_as_of is not None else "N/A")

    # ── 6. Compute Block-A betas per ticker ───────────────────────────────────
    log.info("computing Block-A betas for %d tickers...", len(closes.columns))
    all_betas: dict[str, pd.DataFrame] = {}
    for i, ticker in enumerate(closes.columns):
        if (i + 1) % 100 == 0:
            log.info("  betas: %d / %d tickers done", i + 1, len(closes.columns))
        ticker_ret = closes[ticker].astype(float).pct_change(fill_method=None)
        sector = ns.get(ticker, (ticker, "—"))[1]
        is_china = sector in CHINA_SECTORS
        try:
            bdf = _compute_block_a_for_ticker(
                ticker=ticker,
                ticker_returns=ticker_ret,
                sector=sector,
                stream_raw=stream_raw,
                etf_cache=etf_cache,
                data_root=data_root,
                is_china_exposed=is_china,
            )
            if not bdf.empty:
                all_betas[ticker] = bdf
        except Exception as e:
            log.warning("beta computation failed for %s: %s", ticker, e)

    log.info("betas computed for %d tickers", len(all_betas))

    # ── 7. Vasicek shrinkage (cross-sectional, per beta column) ───────────────
    # Collect betas into a date × ticker frame per column, then shrink row-wise.
    log.info("applying Vasicek shrinkage across cross-section...")
    # Determine all beta columns:
    all_beta_cols: set[str] = set()
    for bdf in all_betas.values():
        all_beta_cols.update(bdf.columns)
    all_beta_cols_sorted = sorted(all_beta_cols)

    # Build cross-sectional frames and shrink:
    shrunk_betas: dict[str, dict[str, pd.Series]] = {
        ticker: {} for ticker in all_betas
    }
    for col in all_beta_cols_sorted:
        # Build date × ticker DataFrame for this beta column:
        col_frames: dict[str, pd.Series] = {}
        for ticker, bdf in all_betas.items():
            if col in bdf.columns:
                col_frames[ticker] = bdf[col]
        if not col_frames:
            continue
        beta_mat = pd.DataFrame(col_frames).reindex(all_dates)
        # Apply Vasicek shrinkage row-wise (cross-sectional):
        shrunk_mat = _vasicek_shrink(beta_mat, VASICEK_W)
        # Store back per-ticker:
        for ticker in shrunk_mat.columns:
            shrunk_betas[ticker][col] = shrunk_mat[ticker]

    log.info("Vasicek shrinkage done")

    # ── 8. Compute rolling window returns for attribution ─────────────────────
    # Pre-compute rolling returns for all streams and all tickers:
    log.info("computing rolling returns for attribution windows...")

    # Stream rolling returns (from raw series, NOT orthogonalized — the attribution
    # uses realized stream returns, not the orth residuals):
    stream_roll: dict[str, dict[int, pd.Series]] = {}
    for key, ret_series in stream_raw.items():
        stream_roll[key] = {}
        for W in ATT_WINDOWS:
            stream_roll[key][W] = ret_series.rolling(W, min_periods=1).apply(
                lambda x: (1 + x).prod() - 1, raw=True)

    # Sector ETF rolling returns (per-ETF):
    sector_etf_roll: dict[str, dict[int, pd.Series]] = {}
    for etf, ret_series in etf_cache.items():
        if ret_series is None:
            continue
        sector_etf_roll[etf] = {}
        for W in ATT_WINDOWS:
            sector_etf_roll[etf][W] = ret_series.rolling(W, min_periods=1).apply(
                lambda x: (1 + x).prod() - 1, raw=True)

    # Name rolling returns:
    name_roll: dict[str, dict[int, pd.Series]] = {}
    ticker_returns_all: dict[str, pd.Series] = {}
    for ticker in closes.columns:
        ret = closes[ticker].astype(float).pct_change(fill_method=None)
        ticker_returns_all[ticker] = ret
        name_roll[ticker] = {}
        for W in ATT_WINDOWS:
            name_roll[ticker][W] = ret.rolling(W, min_periods=1).apply(
                lambda x: (1 + x).prod() - 1, raw=True)

    # ── 9. Assemble panel rows ────────────────────────────────────────────────
    log.info("assembling panel rows for %d build dates...", len(build_dates))
    rows: list[dict] = []

    alibi_distributions: dict[int, list[float]] = {W: [] for W in ATT_WINDOWS}

    for date in build_dates:
        date_str = str(date.date())

        for ticker in closes.columns:
            if ticker not in shrunk_betas:
                continue
            betas_t_raw = shrunk_betas[ticker]
            # Get scalar betas at this date:
            betas_t: dict[str, float] = {}
            for col, ser in betas_t_raw.items():
                v = ser.get(date) if date in ser.index else float("nan")
                if v is not None and not np.isnan(v):
                    betas_t[col] = float(v)

            if not betas_t:
                continue

            # Sector for this ticker:
            sector = ns.get(ticker, (ticker, "—"))[1]
            etf_sym = GICS_ETF.get(sector, "SPY")

            # Build stream_rets_t dict for each window:
            row: dict = {
                "ticker": ticker,
                "date": date_str,
                "factor_model": FACTOR_MODEL,
            }

            # Attribution per window:
            for W in ATT_WINDOWS:
                # Realized return for this ticker and window:
                realized = name_roll[ticker][W].get(date)
                if realized is None or np.isnan(realized):
                    # No return data — all None
                    for key in betas_t:
                        stream_key = key.replace("beta_", "")
                        row[f"contrib_{stream_key}_{W}d"] = None
                    row[f"resid_ret_{W}d"] = None
                    row[f"alibi_share_{W}d"] = None
                    continue

                # Stream realized returns for this window:
                stream_rets_W: dict[str, float] = {}
                for key in betas_t:
                    stream_key = key.replace("beta_", "")
                    if stream_key == "sector":
                        sr_series = sector_etf_roll.get(etf_sym, {}).get(W)
                    else:
                        sr_series = stream_roll.get(stream_key, {}).get(W)

                    if sr_series is not None and date in sr_series.index:
                        v = sr_series.get(date)
                        stream_rets_W[stream_key] = float(v) if v is not None and not np.isnan(v) else float("nan")
                    else:
                        stream_rets_W[stream_key] = float("nan")

                att = _compute_attribution(betas_t, stream_rets_W, float(realized), W)
                row.update(att)

                # Collect alibi for distribution logging:
                alibi_key = f"alibi_share_{W}d"
                if att.get(alibi_key) is not None:
                    alibi_distributions[W].append(att[alibi_key])

            # resid_ret_1d (single-day residual return):
            ret_1d = ticker_returns_all[ticker].get(date)
            if ret_1d is not None and not np.isnan(ret_1d):
                # 1d realized return for beta × stream computation:
                stream_rets_1d: dict[str, float] = {}
                for key in betas_t:
                    stream_key = key.replace("beta_", "")
                    if stream_key == "sector":
                        sr_series = stream_raw.get("sector")  # may be None
                        # sector stream is per-ticker, use the ETF:
                        sr_s = etf_cache.get(etf_sym)
                    else:
                        sr_s = stream_raw.get(stream_key)
                    v = sr_s.get(date) if sr_s is not None and date in sr_s.index else float("nan")
                    stream_rets_1d[stream_key] = float(v) if not np.isnan(v) else float("nan")

                explained_1d = sum(
                    betas_t.get(f"beta_{sk}", float("nan")) * sr
                    for sk, sr in stream_rets_1d.items()
                    if not np.isnan(sr) and not np.isnan(betas_t.get(f"beta_{sk}", float("nan")))
                )
                row["resid_ret_1d"] = float(ret_1d) - explained_1d
            else:
                row["resid_ret_1d"] = None

            # Block-B percentiles — R3 PIT gate: emit ONLY on as_of date.
            # Historical backfill of these columns requires equity_factors backtest
            # mode asof=date + residual_alpha recompute (deferred to pre-P3 follow-up).
            date_normalized = date.normalize() if hasattr(date, "normalize") else pd.Timestamp(date)
            factors_pit_ok = (
                factors_df is not None
                and factors_as_of is not None
                and date_normalized == factors_as_of.normalize()
            )
            if factors_pit_ok:
                bb = _compute_block_b_percentiles(factors_df, ticker)
                row.update(bb)
            else:
                for leg in BLOCK_B_LEGS:
                    row[f"{leg}_pct"] = None

            # alpha_z_house — R3 PIT gate: emit ONLY on as_of date.
            alpha_pit_ok = (
                alpha_z_map is not None
                and alpha_as_of is not None
                and date_normalized == alpha_as_of.normalize()
            )
            row["alpha_z_house"] = (
                float(alpha_z_map[ticker])
                if alpha_pit_ok and ticker in alpha_z_map
                else None
            )

            rows.append(row)

    if not rows:
        log.error("no rows produced")
        return pd.DataFrame()

    panel = pd.DataFrame(rows)
    elapsed = time.time() - t0
    log.info("=== panel build done: %d rows, %d cols, %.1fs ===",
             len(panel), len(panel.columns), elapsed)

    # ── 10. Log alibi_share distributions ─────────────────────────────────────
    for W in ATT_WINDOWS:
        vals = alibi_distributions[W]
        if vals:
            arr = np.array(vals)
            log.info(
                "alibi_share_%dd distribution (n=%d): "
                "p5=%.3f  p25=%.3f  p50=%.3f  p75=%.3f  p95=%.3f",
                W, len(arr),
                np.percentile(arr, 5), np.percentile(arr, 25),
                np.percentile(arr, 50), np.percentile(arr, 75),
                np.percentile(arr, 95),
            )

    # ── 11. Write monthly partitions ──────────────────────────────────────────
    log.info("writing monthly partitions to %s...", out_root)
    panel["date"] = pd.to_datetime(panel["date"])
    panel["month"] = panel["date"].dt.to_period("M")
    panel_dir = out_root / "data" / "factordata" / "panel"

    partition_sizes: list[tuple[str, int]] = []
    for month, group in panel.groupby("month"):
        month_str = str(month)
        month_dir = panel_dir / month_str
        month_dir.mkdir(parents=True, exist_ok=True)
        out_path = month_dir / "panel.parquet"
        group_out = group.drop(columns=["month"])
        group_out["date"] = group_out["date"].dt.strftime("%Y-%m-%d")
        # R4: reindex to frozen PANEL_COLUMNS schema (missing columns → None):
        group_out = group_out.reindex(columns=PANEL_COLUMNS)
        group_out.to_parquet(out_path, compression="snappy", index=False)
        size_bytes = out_path.stat().st_size
        partition_sizes.append((month_str, size_bytes))
        log.info("  wrote %s: %d rows, %.1f KB", month_str, len(group_out),
                 size_bytes / 1024)

    # ── 12. R2-rule verdict ───────────────────────────────────────────────────
    log.info("=== R2-rule assessment ===")
    for month_str, size_bytes in partition_sizes:
        mb = size_bytes / 1e6
        verdict = "R2-REQUIRED (>5MB)" if mb > 5.0 else "git-ok (<5MB)"
        log.info("  partition %s: %.2f MB — %s", month_str, mb, verdict)
    total_mb = sum(s for _, s in partition_sizes) / 1e6
    log.info("  total panel: %.2f MB across %d partitions", total_mb, len(partition_sizes))

    # Extrapolated nightly runtime (full S&P 1500 ≈ 1500 tickers):
    n_tickers = len(closes.columns)
    n_dates = len(build_dates)
    per_ticker_ms = (elapsed / max(n_tickers, 1)) * 1000
    full_universe_est = (per_ticker_ms * 1500 / 1000)
    log.info("runtime: %.1fs for %d tickers × %d dates (%.1f ms/ticker)",
             elapsed, n_tickers, n_dates, per_ticker_ms)
    log.info("extrapolated full S&P 1500 nightly (1d): %.0fs (%.1f min)",
             full_universe_est, full_universe_est / 60)

    return panel


# ── CLI ──────────────────────────────────────────────────────────────────────
def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-root", type=Path, default=ROOT,
                    help="Repo root whose data/ caches to read (default: this repo)")
    ap.add_argument("--out-root", type=Path, default=None,
                    help="Root under which data/factordata/panel/ is written "
                         "(default: same as --data-root)")
    ap.add_argument("--start", type=str, default=None, metavar="YYYY-MM-DD",
                    help="First date to build (inclusive)")
    ap.add_argument("--end", type=str, default=None, metavar="YYYY-MM-DD",
                    help="Last date to build (inclusive)")
    ap.add_argument("--tickers", type=str, default=None,
                    help="Comma-separated ticker subset (default: all breadth names)")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    data_root = args.data_root.resolve()
    out_root = (args.out_root or data_root).resolve()

    start = pd.Timestamp(args.start) if args.start else None
    end = pd.Timestamp(args.end) if args.end else None
    tickers = [t.strip() for t in args.tickers.split(",")] if args.tickers else None

    panel = build_panel(
        data_root=data_root,
        out_root=out_root,
        start_date=start,
        end_date=end,
        tickers=tickers,
    )

    if panel.empty:
        log.error("panel build produced no rows — check logs above")
        return 1

    log.info("DONE: %d rows × %d columns", len(panel), len(panel.columns))
    log.info("columns: %s", sorted(panel.columns.tolist()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
