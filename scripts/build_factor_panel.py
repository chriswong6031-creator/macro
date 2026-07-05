"""Factor Intelligence panel builder — Block-A attribution + Block-B percentiles + Twin.

OFF-RENDER-PATH PLACEMENT: this script is a standalone nightly step that runs
BEFORE build_site.py in CI.  It writes data/factordata/panel/YYYY-MM/panel.parquet
(snappy-compressed, one partition per calendar month).  build_site.py reads the
pre-computed panel; it does not recompute factor betas inline.

JOIN CONTRACT: studies join this panel against the replay artifact
(data/replay/standout_replay.parquet) on (ticker, date) where date == signal_date.
No other program may write to data/factordata/panel/.  No panel column may be added
without a v2 version stamp.

V1 FREEZE: all Block-A, Block-B, and Twin parameters are frozen as of the
adjudication rulings 2026-07-04 (P1-A) and 2026-07-05 (P1-B).
See research/FACTOR_INTELLIGENCE_MASTERPLAN_BY_FABLE.md §3 for the authoritative
spec.  Any parameter change requires a v2 stamp.

SCOPE (P1-A + P1-B — see masterplan §7):
  - Block-A: per-(ticker,date) rolling attribution vs ordered orthogonal streams
  - Block-B: trailing cross-sectional percentiles of equity_factors legs
  - alpha_z_house read-through from site/factordata/alpha.json (nightly residual_alpha)
  - Panel schema + partitioning + version stamp
  - Twin computation (P1-B): twin_rel_20d, twin_bleed_flag, twin_n_peers, twin_fallback

OUT OF SCOPE FOR THIS PR (added by later PRs):
  - Style-regime classifier (P1-C): dna_class, style_regime, style_regime_pending
  - Pair G detector / factor_attention reflex (P1-D)

TWIN COMPUTATION (P1-B — masterplan §3.5 + RULING-1 + RULING-2):

  INDUSTRY FIELD — SECTOR-PROXY DEVIATION (flagged for Fable ruling before merge):
    The masterplan §3.5 specifies twins grouped by GICS industry (sub-sector level).
    However, local caches (data/{breadth,smallcap_breadth,midcap_breadth}/constituents.parquet
    and site/factordata/factors.json) contain ONLY the 'sector' field (GICS sector
    level, 11 categories).  NO GICS industry field exists in any local cache.
    Therefore, twin grouping uses SECTOR as the proxy for industry.
    This is flagged as SECTOR-PROXY throughout the twin code and run log.
    A proper GICS industry mapping (4-digit code + label) is required to implement
    the spec as written.  That mapping must be sourced externally (e.g. EDGAR GICS
    classification files or the index provider's mapping table) and will be supplied
    in the pre-P3 follow-up that also handles per-date mktcap for historical backfill.

    FABLE RULING 2026-07-05: sector-proxy twins are display-tier v1 interim.
    PREREG H4's clock does NOT start on sector-proxy twins — H4 requires GICS-industry
    grouping (locked text).  Industry mapping (EDGAR SIC or Polygon reference) joins the
    pre-P3 follow-up; twins switch to industry grouping from the first freeze month after
    it lands, and H4 accrual starts there.

  NULL-BACKFILL (RULING-2, 2026-07-05):
    Twin columns (twin_rel_20d, twin_bleed_flag, twin_n_peers, twin_fallback) are
    computed ONLY for build dates in the CURRENT freeze month (the calendar month
    whose first-trading-day freeze uses the live factors.json mktcap snapshot for
    the size-tercile filter).  All earlier (backfill) dates receive None — same R3
    semantics as Block-B.  Historical twin backfill joins the pre-P3 follow-up that
    supplies per-date mktcap via equity_factors backtest mode.

  twin_bleed_flag definition (RULING-1, PREREG H4 governs over masterplan §3.5):
    True iff BOTH:
      (a) twin basket 20d return < 0
      (b) twin basket drawdown-from-20d-high at evaluation date t >
          median of the PRIOR 60 TRADING observations of 20d-drawdown-from-20d-high
          (the 60 rows of the drawdown series strictly before t; one observation per
          trading day, computed from twin basket daily returns up to and including t).
    The masterplan §3.5 parenthetical originally said "prior 252d"; corrected below
    to match the locked PREREG H4.

  Freeze schedule: membership is frozen on the first trading day of each calendar
    month (first_bday_of_month).  The same frozen membership is used for all
    evaluation dates in that calendar month.

  Correlation window for member selection: [freeze_date - 253, freeze_date - 1]
    (252 business days of residual returns ending the day before the freeze date).

  Minimum peers: 8 after sector + size-tercile filter.  If fewer than 8, fall back
    to sector EW (all sector members, self-excluded), twin_fallback=True.

NOTE (F3 ruling 2026-07-05): trailing-252d study breakpoints (alibi Q80, alpha_z
quintiles) are STUDY-TIME derivations from accumulated panel history — Block-A
history is price-only and PIT-backfillable via --start; no dedicated breakpoint
columns are emitted by design.

STREAM WARMUP COVERAGE (F-A disclosure 2026-07-05): the sequential causal orth
chain consumes ~127 leading rows PER STREAM, so late-priority streams have low
fill on short histories.  Measured on a 790-bday cache: beta_dollar 53.6%,
beta_ai_theme 0.2%, beta_china 0.0% non-null.  The production nightly and any
study-facing backfill must run with deep history (--start 2020-01-01 or earlier)
so all Block-A streams reach full coverage before P3 studies consume them.

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

# R4 — FIXED SCHEMA: frozen 52-column v1 set (48 from P1-A + 4 twin from P1-B).
# Every partition is reindexed to exactly these columns (missing → None) before
# writing.  China contrib columns are always present; non-china tickers have None.
# Twin columns are always present; backfill dates (pre-current-month) have None.
# P1-B NOTE: the four twin columns are §3.6-listed v1 columns delivered by their
# scheduled PR (P1-B).  The "no new columns without v2" clause is satisfied because
# twin columns were listed in the v1 schema in §3.6 from the original spec;
# P1-A shipped without them only because they were scoped to the next PR.
# Adding any FURTHER column requires a v2 version stamp and a new migration PR.
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
    # ── Twin outputs (P1-B, §3.5 — PIT: current-freeze-month dates only) ──────
    # NULL-BACKFILL (RULING-2): prior months get None.  Historical backfill
    # joins the pre-P3 follow-up (per-date mktcap via equity_factors backtest).
    "twin_rel_20d",      # name 20d return − twin EW 20d return (signed)
    "twin_bleed_flag",   # bool: twin deteriorating at entry (RULING-1 / PREREG H4)
    "twin_n_peers",      # int: number of peers in the twin basket
    "twin_fallback",     # bool: True if fell back to sector EW (< 8 valid peers)
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
    # F2(b): min-variance floor — near-zero var (< 1e-12) collapses to NaN,
    # not a degenerate huge coefficient.  .replace(0, nan) is insufficient
    # for near-zero values (e.g. sector == mkt stream degeneracy → var ~5e-35).
    beta = (cov / var.where(var >= 1e-12)).shift(1)
    return beta


def _vasicek_shrink(beta_raw: pd.DataFrame, w: float) -> pd.DataFrame:
    """Vasicek shrinkage: beta_shrunk = w * beta_raw + (1-w) * cross_sectional_mean.

    Applied row-wise (same-day cross-section), matching engine/residual_alpha._shrink.
    w >= 1 → no-op.

    F2(c) — frozen v1 guard: raw betas are clipped to [-10, +10] before computing
    the cross-sectional mean.  This prevents degenerate near-infinite betas (arising
    from near-zero variance streams, e.g. SPY-fallback sector == mkt stream) from
    poisoning the cross-sectional mean and corrupting every ticker on that date.
    The clip band [-10, +10] is a frozen v1 parameter — any change requires a v2 stamp.
    """
    if w is None or w >= 1.0:
        return beta_raw
    # F2(c): clip betas to frozen band before cross-sectional mean (frozen v1 guard).
    beta_clipped = beta_raw.clip(lower=-10.0, upper=10.0)
    cs_mean = beta_clipped.mean(axis=1)
    return beta_clipped.mul(w).add(cs_mean.mul(1.0 - w), axis=0)


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
        # F2(b): min-variance floor — near-zero var (< 1e-12) → NaN coefficient,
        # preventing degenerate near-infinite coefficients when streams are collinear.
        coef = (cov_rp / var_p.where(var_p >= 1e-12)).shift(1)
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
                           etf_cache: dict[str, pd.Series | None]) -> tuple[pd.Series | None, bool]:
    """Fetch (and cache) the SPDR sector ETF return series for a GICS sector.

    Returns (series_or_None, is_spy_fallback).  is_spy_fallback is True when
    the sector is unmapped (not in GICS_ETF) and SPY was the fallback — the caller
    must skip the sector stream in that case (F2(a): SPY == mkt stream → collinear).
    """
    is_spy_fallback = sector not in GICS_ETF
    etf = GICS_ETF.get(sector, "SPY")
    if etf not in etf_cache:
        s = _read_yahoo(data_root, etf)
        etf_cache[etf] = s
    return etf_cache[etf], is_spy_fallback


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
        sector_ret, is_spy_fallback = _get_sector_etf_return(data_root, sector, etf_cache)
        if sector_ret is None:
            # ETF data unavailable — skip sector stream
            streams_to_use = [k for k in streams_to_use if k != "sector"]
        elif is_spy_fallback:
            # F2(a): sector is unmapped ('—' or missing) → resolved to SPY fallback.
            # SPY == mkt stream → sector stream is collinear with mkt → near-zero orth
            # variance → degenerate beta_sector (~1e14) → Vasicek mean poisoned for all
            # tickers that date.  Skip sector stream entirely for this ticker.
            streams_to_use = [k for k in streams_to_use if k != "sector"]
            sector_ret = None

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


# ── Twin constants (frozen v1, masterplan §3.5 + RULING-1 + RULING-2) ────────

# Correlation window for twin member selection (business days before freeze_date):
TWIN_CORR_WIN = 252      # window = [freeze_date-253, freeze_date-1]
TWIN_CORR_MINP = 126     # min_periods for Pearson correlation (same as BETA_WIN halving)
TWIN_TOP_N = 12          # take top-12 peers by 252d residual-return correlation
TWIN_MIN_PEERS = 8       # minimum peers after sector+size filter → else fallback

# RULING-1 (PREREG H4 governs): twin_bleed_flag uses prior 60d of 20d-drawdown-from-20d-high
# observations.  (Masterplan §3.5 originally said "prior 252d"; corrected here to match
# the locked PREREG H4 text; see also §3.5 correction note below.)
TWIN_BLEED_LOOKBACK = 60  # trading days of 20d-drawdown observations for the pullback median

# Size-tercile filter: ±1 tercile of the name within its sector group.
# Terciles are computed from factors.json mktcap_bn (current snapshot, RULING-2).
# Tercile labels: 0=small, 1=mid, 2=large (qcut with 3 buckets).
TWIN_SIZE_TERCILE_TOLERANCE = 1   # ±1 tercile

# Return from the same breadth closes cache (total-return adjusted) used by Block-A.
TWIN_RET_WIN = 20  # 20d compounded return for twin_rel_20d and twin_bleed inputs


def _get_first_bday_of_month(year: int, month: int,
                              bday_index: pd.DatetimeIndex) -> pd.Timestamp | None:
    """Return the first business day of (year, month) present in bday_index.

    Used for freeze-date determination.  Returns None if no dates in that
    month are present in bday_index.
    """
    month_mask = (bday_index.year == year) & (bday_index.month == month)
    candidates = bday_index[month_mask]
    return candidates[0] if len(candidates) > 0 else None


def _compute_size_terciles(factors_df: pd.DataFrame, sector_map: dict[str, str]
                            ) -> dict[str, int]:
    """Compute within-sector size tercile (0=small, 1=mid, 2=large) per ticker.

    Uses factors_df['mktcap_bn'] (current snapshot per RULING-2).
    Terciles are computed within each GICS sector group.

    SECTOR-PROXY: groups by 'sector' (GICS sector level) because 'industry'
    (GICS sub-sector) is NOT available in local caches.  This is a frozen v1
    deviation flagged for Fable ruling before merge.

    Returns {ticker: tercile_label (0/1/2)} for all tickers with valid mktcap.
    Missing or NaN mktcap → excluded (not in output dict).
    """
    if factors_df is None or "mktcap_bn" not in factors_df.columns:
        return {}

    # Build (ticker, sector, mktcap_bn) frame:
    rows = []
    for ticker in factors_df.index:
        mktcap = factors_df.at[ticker, "mktcap_bn"]
        if pd.isna(mktcap) or mktcap <= 0:
            continue
        # Prefer sector from factors_df; fall back to sector_map.
        sector = None
        if "sector" in factors_df.columns:
            sector = str(factors_df.at[ticker, "sector"]) if not pd.isna(
                factors_df.at[ticker, "sector"]) else None
        if not sector or sector == "nan":
            sector = sector_map.get(ticker, ("", "—"))[1] if isinstance(
                sector_map.get(ticker), tuple) else "—"
        rows.append({"ticker": ticker, "sector": sector, "mktcap_bn": float(mktcap)})

    if not rows:
        return {}

    df = pd.DataFrame(rows).set_index("ticker")
    tercile_map: dict[str, int] = {}

    for sector_name, grp in df.groupby("sector"):
        if len(grp) < 3:
            # Too few for tercile — assign all to middle (1)
            for t in grp.index:
                tercile_map[t] = 1
            continue
        try:
            labels = pd.qcut(grp["mktcap_bn"], q=3, labels=[0, 1, 2], duplicates="drop")
            for t, lbl in labels.items():
                if not pd.isna(lbl):
                    tercile_map[t] = int(lbl)
        except Exception:
            # qcut failed (e.g. all same mktcap) — assign all to middle
            for t in grp.index:
                tercile_map[t] = 1

    return tercile_map


def _build_twin_membership(
    freeze_date: pd.Timestamp,
    ticker: str,
    sector: str,
    size_tercile: int | None,
    all_resid_1d: dict[str, pd.Series],  # {ticker: resid_ret_1d series, index=dates}
    size_tercile_map: dict[str, int],
    ns: dict[str, tuple[str, str]],  # {ticker: (name, sector)}
    bday_index: pd.DatetimeIndex,
) -> tuple[list[str], bool]:
    """Determine twin basket membership at freeze_date for one ticker.

    Steps (masterplan §3.5 + RULING-2):
    1. Candidate pool: same sector as ticker, within ±1 size tercile, self-excluded.
       SECTOR-PROXY: uses 'sector' (GICS sector level, 11 categories) because
       'industry' (GICS industry level) is NOT in local caches.
    2. Rank candidates by 252d Pearson correlation of residual-return series,
       window = [freeze_date-253, freeze_date-1] (PIT: data <= freeze_date-1 only).
    3. Take top-12 by correlation.
    4. If <TWIN_MIN_PEERS survivors: fall back to sector EW (all sector members,
       self-excluded), twin_fallback=True.

    Returns (member_tickers, twin_fallback_flag).
    """
    # ── 1. Candidate pool ─────────────────────────────────────────────────────
    # SECTOR-PROXY: group by sector (not GICS industry — see module docstring)
    same_sector = [
        t for t, (_, s) in ns.items()
        if s == sector and t != ticker and t in all_resid_1d
    ]

    if size_tercile is not None:
        # Filter ±1 size tercile within sector:
        filtered = [
            t for t in same_sector
            if abs(size_tercile_map.get(t, size_tercile) - size_tercile) <= TWIN_SIZE_TERCILE_TOLERANCE
        ]
    else:
        filtered = same_sector

    # ── 2. Correlation ranking: window [freeze_date-253, freeze_date-1] ───────
    # PIT: enforced by the correlation window ending at freeze_date-1 (window exclusion:
    # bday_index[win_start_idx: win_end_idx] is exclusive of freeze_date itself).
    # Returns are contemporaneous (no shift applied here); betas are shift(1)-causal
    # but resid_ret_1d is already a return series — no additional shift is applied.
    win_end_idx = bday_index.get_loc(freeze_date) if freeze_date in bday_index else None
    if win_end_idx is None or win_end_idx < 1:
        # Can't compute correlation window — fall back to sector EW
        fallback_members = [t for t in same_sector if t != ticker and t in all_resid_1d]
        return fallback_members, True

    # Window is [win_end_idx - TWIN_CORR_WIN, win_end_idx - 1] (252 bdays ending at t-1)
    win_start_idx = max(0, win_end_idx - TWIN_CORR_WIN)
    win_dates = bday_index[win_start_idx: win_end_idx]  # exclusive of freeze_date itself

    if len(win_dates) < TWIN_CORR_MINP or ticker not in all_resid_1d:
        fallback_members = [t for t in same_sector if t != ticker and t in all_resid_1d]
        return fallback_members, True

    ref_series = all_resid_1d[ticker].reindex(win_dates).dropna()
    if len(ref_series) < TWIN_CORR_MINP:
        fallback_members = [t for t in same_sector if t != ticker and t in all_resid_1d]
        return fallback_members, True

    # Compute correlations for each candidate (vectorized per candidate):
    corr_pairs: list[tuple[float, str]] = []
    for cand in filtered:
        if cand not in all_resid_1d:
            continue
        cand_series = all_resid_1d[cand].reindex(win_dates).dropna()
        # Align on common non-null dates:
        common_idx = ref_series.index.intersection(cand_series.index)
        if len(common_idx) < TWIN_CORR_MINP:
            continue
        r = ref_series.reindex(common_idx).values
        c = cand_series.reindex(common_idx).values
        # Pearson correlation (same as np.corrcoef row 0,1):
        r_std = r.std()
        c_std = c.std()
        if r_std < 1e-12 or c_std < 1e-12:
            continue
        corr_val = float(np.corrcoef(r, c)[0, 1])
        if np.isnan(corr_val):
            continue
        corr_pairs.append((corr_val, cand))

    # ── 3. Top-12 by correlation ───────────────────────────────────────────────
    corr_pairs.sort(key=lambda x: x[0], reverse=True)
    top_members = [t for _, t in corr_pairs[:TWIN_TOP_N]]

    # ── 4. Min-peers check / fallback ─────────────────────────────────────────
    if len(top_members) >= TWIN_MIN_PEERS:
        return top_members, False
    else:
        # Fall back to all same-sector names (self-excluded):
        fallback_members = [t for t in same_sector if t != ticker and t in all_resid_1d]
        return fallback_members, True


def _compute_twin_ew_returns(
    member_tickers: list[str],
    closes: pd.DataFrame,
    date_index: pd.DatetimeIndex,
) -> pd.Series:
    """Compute equal-weight twin basket daily return series from closes.

    Uses the same total-return-adjusted close cache as Block-A.
    Returns a daily return series aligned to date_index.
    """
    if not member_tickers:
        return pd.Series(np.nan, index=date_index, name="twin_ew")

    member_rets = []
    for t in member_tickers:
        if t not in closes.columns:
            continue
        ret = closes[t].astype(float).pct_change(fill_method=None)
        member_rets.append(ret)

    if not member_rets:
        return pd.Series(np.nan, index=date_index, name="twin_ew")

    # Equal-weight mean of daily returns:
    ew = pd.concat(member_rets, axis=1).mean(axis=1, skipna=True)
    return ew.reindex(date_index).rename("twin_ew")


def _compute_twin_bleed_flag(
    twin_ew_rets: pd.Series,
    eval_date: pd.Timestamp,
) -> bool | None:
    """Compute twin_bleed_flag at eval_date using RULING-1 / PREREG H4 definition.

    RULING-1 (PREREG H4 governs, 2026-07-05):
    twin_bleed_flag = True iff:
      (a) twin basket 20d return at eval_date < 0
      (b) twin basket drawdown-from-20d-high at eval_date >
          median of the prior 60 TRADING observations of 20d-drawdown-from-20d-high
          (the 60 rows of the drawdown series strictly before eval_date, rolling 20d
          drawdown from 20d high, computed from twin basket returns up to and including t).

    NOTE: Masterplan §3.5 originally said "prior 252d"; this has been corrected
    to match the locked PREREG H4 text: prior 60d of observations.
    Correction note: "(corrected 2026-07-05 to match locked PREREG H4; drift caught in P1-B)"

    Returns True/False, or None if data is insufficient.

    PIT guard: all inputs must be data <= eval_date.  The twin_ew_rets series
    must be pre-filtered to dates <= eval_date before calling.
    """
    # Filter to data <= eval_date (PIT):
    hist = twin_ew_rets[twin_ew_rets.index <= eval_date].dropna()

    if len(hist) < TWIN_RET_WIN + 1:
        return None  # Not enough data for 20d return or 20d high

    # (a) 20d compounded return at eval_date:
    twin_20d_ret = float(((1 + hist.tail(TWIN_RET_WIN)).prod() - 1))

    if twin_20d_ret >= 0:
        # Condition (a) fails — flag is False
        return False

    # (b) Drawdown-from-20d-high at eval_date and the prior 60d distribution:
    # Build a price series (rebased to 1.0 at start of available history):
    price = (1 + hist).cumprod()

    # Rolling 20d high (using at least 1 period):
    rolling_high = price.rolling(TWIN_RET_WIN, min_periods=1).max()

    # 20d-drawdown-from-20d-high series: drawdown = (price / rolling_20d_high) - 1
    # This is <= 0 by construction.  We take abs() to get a non-negative pullback depth.
    drawdown_series = ((price / rolling_high) - 1).abs()  # non-negative pullback depth

    # Current drawdown (at eval_date):
    if eval_date not in drawdown_series.index:
        return None
    current_drawdown = float(drawdown_series.loc[eval_date])

    # Prior 60 TRADING observations: the 60 rows strictly before eval_date
    # (positional slice — RULING-1 uses trading days, not calendar days).
    prior_dd = drawdown_series[drawdown_series.index < eval_date].tail(
        TWIN_BLEED_LOOKBACK
    ).dropna()

    if len(prior_dd) < 1:
        return None  # No prior observations for the distribution

    median_pullback = float(prior_dd.median())

    return bool(current_drawdown > median_pullback)


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

    # ── 4. Load Block-B factors snapshot (also used for twin size-tercile) ───────
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
    # F2(a): collect tickers whose sector is unmapped → SPY fallback → sector stream skipped.
    skipped_sector_tickers: list[str] = []
    for i, ticker in enumerate(closes.columns):
        if (i + 1) % 100 == 0:
            log.info("  betas: %d / %d tickers done", i + 1, len(closes.columns))
        ticker_ret = closes[ticker].astype(float).pct_change(fill_method=None)
        sector = ns.get(ticker, (ticker, "—"))[1]
        is_china = sector in CHINA_SECTORS
        # F2(a): detect SPY-fallback tickers before calling the block-A function.
        if sector not in GICS_ETF:
            skipped_sector_tickers.append(ticker)
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

    # F2(a): log all skipped-sector tickers once per build.
    if skipped_sector_tickers:
        log.info(
            "F2(a) SPY-fallback sector skip: %d ticker(s) with unmapped sector "
            "(beta_sector/contrib_sector_* → None): %s",
            len(skipped_sector_tickers), skipped_sector_tickers,
        )
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

    # ── 8b. Twin pre-computation (P1-B, RULING-2) ────────────────────────────
    # Determine the "current freeze month": the calendar month of factors_as_of
    # (the live mktcap snapshot).  Twin columns are emitted ONLY for build dates
    # in this month; all earlier dates receive None (NULL-BACKFILL, RULING-2).
    #
    # SECTOR-PROXY deviation: twin groups by 'sector' (GICS sector level, 11 cats)
    # because GICS 'industry' (sub-sector) is NOT present in local caches.
    # Flagged for Fable ruling; logged prominently in run log.
    log.info(
        "SECTOR-PROXY WARNING: twin groups by GICS sector (not industry) — "
        "no 'industry' field exists in local caches "
        "(breadth/constituents.parquet + factors.json have only 'sector'). "
        "This is a DEVIATION from masterplan §3.5.  Flagged for Fable ruling before merge."
    )

    twin_freeze_month: tuple[int, int] | None = None  # (year, month) of current freeze
    if factors_as_of is not None:
        twin_freeze_month = (factors_as_of.year, factors_as_of.month)
        log.info("twin current freeze month: %04d-%02d (factors_as_of=%s)",
                 twin_freeze_month[0], twin_freeze_month[1], factors_as_of.date())
    else:
        log.warning("twin: no factors_as_of — twin columns will be null for all dates")

    # Determine freeze dates for each calendar month in build_dates:
    # The freeze date is the first business day of the month (first_bday_of_month).
    # We only compute twin for the current_freeze_month; other months → None.
    all_bday_index = all_dates  # pd.DatetimeIndex of all business days in closes

    # Build per-ticker resid_ret_1d series for twin correlation:
    # We use the SAME resid_ret_1d as already computed in the attribution block
    # (not yet computed here — we'll compute it on-the-fly per ticker using the
    # shrunk betas).  For efficiency, build a full resid_1d series per ticker
    # from the Block-A betas (post-shrinkage).
    #
    # PERFORMANCE NOTE: we compute all_resid_1d for all tickers, over all_dates,
    # using the existing shrunk_betas.  This is vectorized per ticker (O(n_dates)
    # per ticker).  The twin correlation ranking is then O(n_tickers × n_sector_peers)
    # per freeze date — one freeze per month, so ~12 freeze computations/year.
    log.info("building resid_ret_1d series for twin correlation...")
    all_resid_1d: dict[str, pd.Series] = {}
    for ticker in closes.columns:
        if ticker not in shrunk_betas:
            continue
        ret_1d_series = closes[ticker].astype(float).pct_change(fill_method=None)
        sector_tk = ns.get(ticker, (ticker, "—"))[1]
        etf_sym_tk = GICS_ETF.get(sector_tk, "SPY")
        # Compute explained_1d for every date in one vectorized pass:
        explained_cols: list[pd.Series] = []
        for beta_col, beta_series in shrunk_betas[ticker].items():
            stream_key = beta_col.replace("beta_", "")
            if stream_key == "sector":
                stream_s = etf_cache.get(etf_sym_tk)
            else:
                stream_s = stream_raw.get(stream_key)
            if stream_s is None:
                continue
            contrib = beta_series.shift(0) * stream_s  # both already aligned to all_dates
            explained_cols.append(contrib)
        if explained_cols:
            # skipna=True: if a stream's beta is NaN (e.g. ai_theme insufficient history),
            # that stream's contribution is treated as 0 rather than poisoning the entire
            # explained_total for every date where ANY beta is NaN.
            # This is correct for twin correlation: use available betas, skip absent ones.
            # Fable-blessed 2026-07-05: ranking-only leniency (absent late-stream betas
            # treated as 0 contribution for peer-correlation ranking); the attribution
            # path's skipna=False is unchanged and canonical.
            explained_total = pd.concat(explained_cols, axis=1, sort=False).sum(axis=1, skipna=True)
            resid = ret_1d_series - explained_total
        else:
            resid = ret_1d_series.copy()
        all_resid_1d[ticker] = resid

    # Twin size-tercile map (from current factors.json snapshot per RULING-2):
    size_tercile_map: dict[str, int] = {}
    if factors_df is not None and factors_as_of is not None:
        # Build sector_map for _compute_size_terciles: {ticker: (name, sector)}
        size_tercile_map = _compute_size_terciles(factors_df, ns)
        log.info("twin size-tercile map: %d tickers", len(size_tercile_map))
    else:
        log.warning("twin: no factors.json — size-tercile filter disabled (all ±1 = all)")

    # Precompute freeze-date twin memberships (one per freeze date in build window):
    # Key = (year, month) of a build date → (freeze_date, {ticker: ([members], fallback)})
    # Only compute for the current_freeze_month (RULING-2 null-backfill).
    twin_memberships: dict[tuple[int, int], dict[str, tuple[list[str], bool]]] = {}

    if twin_freeze_month is not None:
        # Find the freeze date for the current_freeze_month:
        freeze_date_cur = _get_first_bday_of_month(
            twin_freeze_month[0], twin_freeze_month[1], all_bday_index
        )
        if freeze_date_cur is not None:
            log.info("twin freeze date for current month: %s", freeze_date_cur.date())
            # Compute membership for every ticker in the universe:
            month_membership: dict[str, tuple[list[str], bool]] = {}
            for ticker in closes.columns:
                sector_tk = ns.get(ticker, (ticker, "—"))[1]
                size_tercile_tk = size_tercile_map.get(ticker)
                try:
                    members, fallback = _build_twin_membership(
                        freeze_date=freeze_date_cur,
                        ticker=ticker,
                        sector=sector_tk,
                        size_tercile=size_tercile_tk,
                        all_resid_1d=all_resid_1d,
                        size_tercile_map=size_tercile_map,
                        ns=ns,
                        bday_index=all_bday_index,
                    )
                    month_membership[ticker] = (members, fallback)
                except Exception as e:
                    log.warning("twin membership failed for %s: %s", ticker, e)
                    month_membership[ticker] = ([], True)
            twin_memberships[twin_freeze_month] = month_membership
            n_fallback = sum(1 for _, (_, fb) in month_membership.items() if fb)
            n_valid = len(month_membership) - n_fallback
            log.info(
                "twin membership: %d tickers total, %d with ≥8-peer twin, "
                "%d fallback-to-sector (SECTOR-PROXY)",
                len(month_membership), n_valid, n_fallback
            )
        else:
            log.warning("twin: could not find first bday of freeze month %s-%02d",
                        twin_freeze_month[0], twin_freeze_month[1])

    # Precompute twin EW return series per ticker (for current-freeze-month only):
    # {ticker: pd.Series of twin basket daily EW returns, aligned to all_dates}
    twin_ew_series: dict[str, pd.Series] = {}
    if twin_freeze_month in twin_memberships:
        month_membership = twin_memberships[twin_freeze_month]
        for ticker, (members, _fallback) in month_membership.items():
            twin_ew = _compute_twin_ew_returns(members, closes, all_bday_index)
            twin_ew_series[ticker] = twin_ew
        log.info("twin EW return series built for %d tickers", len(twin_ew_series))

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

            # F1: stamp Vasicek-shrunk betas into row (betas_t keys are already
            # "beta_{stream}" matching PANEL_COLUMNS — e.g. "beta_mkt", "beta_sector").
            for col, val in betas_t.items():
                row[col] = val

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

            # Twin outputs — RULING-2 NULL-BACKFILL:
            # Emit ONLY for build dates in the current freeze month.
            # All other dates receive None (same R3 semantics as Block-B).
            date_month = (date.year, date.month)
            twin_in_freeze_month = (
                twin_freeze_month is not None
                and date_month == twin_freeze_month
                and ticker in twin_ew_series
            )
            if twin_in_freeze_month:
                members, fallback = twin_memberships[twin_freeze_month].get(
                    ticker, ([], True)
                )
                twin_ew = twin_ew_series[ticker]

                # twin_rel_20d: name 20d return − twin EW 20d return at date (PIT):
                # Name 20d return (already computed in name_roll):
                name_20d = name_roll[ticker][20].get(date)
                # Twin EW 20d return (from twin_ew daily returns, compounded):
                twin_hist_to_date = twin_ew[twin_ew.index <= date].dropna()
                if (name_20d is not None and not np.isnan(name_20d)
                        and len(twin_hist_to_date) >= TWIN_RET_WIN):
                    twin_20d = float(
                        (1 + twin_hist_to_date.tail(TWIN_RET_WIN)).prod() - 1
                    )
                    row["twin_rel_20d"] = float(name_20d) - twin_20d
                else:
                    row["twin_rel_20d"] = None

                # twin_bleed_flag (RULING-1 / PREREG H4):
                try:
                    bleed = _compute_twin_bleed_flag(twin_ew, date)
                    row["twin_bleed_flag"] = bleed
                except Exception as e:
                    log.warning("twin_bleed_flag failed for %s at %s: %s", ticker, date_str, e)
                    row["twin_bleed_flag"] = None

                row["twin_n_peers"] = int(len(members))
                row["twin_fallback"] = bool(fallback)
            else:
                # Not in current freeze month → NULL-BACKFILL (RULING-2):
                row["twin_rel_20d"] = None
                row["twin_bleed_flag"] = None
                row["twin_n_peers"] = None
                row["twin_fallback"] = None

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

    # ── 10b. Twin coverage report ─────────────────────────────────────────────
    if twin_freeze_month is not None:
        twin_panel = pd.DataFrame(rows) if rows else pd.DataFrame()
        if not twin_panel.empty and "twin_n_peers" in twin_panel.columns:
            cur_month_mask = (
                pd.to_datetime(twin_panel["date"]).dt.year == twin_freeze_month[0]
            ) & (
                pd.to_datetime(twin_panel["date"]).dt.month == twin_freeze_month[1]
            )
            twin_rows = twin_panel[cur_month_mask]
            if len(twin_rows) > 0:
                # Unique-ticker counts (not row counts) to avoid double-counting
                # across multiple eval dates in the freeze month:
                per_ticker = twin_rows.groupby("ticker").first().reset_index()
                n_total_tickers = len(per_ticker)
                has_twin_mask = per_ticker["twin_n_peers"].notna()
                n_with_twin_tickers = int(has_twin_mask.sum())
                n_fallback_tickers = int(
                    per_ticker.loc[has_twin_mask, "twin_fallback"].sum()
                ) if n_with_twin_tickers > 0 else 0
                n_valid_twin = n_with_twin_tickers - n_fallback_tickers
                n_excluded = n_total_tickers - n_with_twin_tickers

                # For rate/distribution: use all rows in freeze month (multi-day):
                has_twin_rows = twin_rows["twin_n_peers"].notna()
                bleed_col = twin_rows.loc[has_twin_rows, "twin_bleed_flag"]
                bleed_rate = (float(bleed_col.mean())
                              if has_twin_rows.any() and bleed_col.notna().any()
                              else float("nan"))
                rel20_col = twin_rows.loc[
                    has_twin_rows & twin_rows["twin_rel_20d"].notna(), "twin_rel_20d"
                ]

                log.info(
                    "=== twin coverage (freeze month %04d-%02d) ===",
                    twin_freeze_month[0], twin_freeze_month[1]
                )
                log.info(
                    "  names with valid twin (≥8 peers): %d  "
                    "fallback-to-sector (SECTOR-PROXY): %d  "
                    "excluded (no peers/data): %d  (total unique tickers: %d)",
                    n_valid_twin, n_fallback_tickers, n_excluded, n_total_tickers
                )
                log.info(
                    "  twin_bleed_flag fire rate: %.1f%%  "
                    "(prereg power table: ~10-20%% of fires)",
                    bleed_rate * 100 if not np.isnan(bleed_rate) else float("nan")
                )
                if len(rel20_col) > 0:
                    log.info(
                        "  twin_rel_20d distribution (n=%d rows): "
                        "p5=%.3f  p25=%.3f  p50=%.3f  p75=%.3f  p95=%.3f",
                        len(rel20_col),
                        float(rel20_col.quantile(0.05)),
                        float(rel20_col.quantile(0.25)),
                        float(rel20_col.quantile(0.50)),
                        float(rel20_col.quantile(0.75)),
                        float(rel20_col.quantile(0.95)),
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
