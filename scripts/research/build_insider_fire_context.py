"""Entry-Stack Amendment 2 T1a — per-fire insider context panel builder.

Spec: research/ENTRY_STACK_EXPANSION_AMENDMENT2_BY_FABLE.md §B RUL-22/23/26,
      §C4, §D T1.

This is an OFF-PATH research script — NOT wired into the nightly pipeline.
Run manually to produce:
  data/research/insider_fire_context_deep.parquet
  data/research/insider_fire_context_baskets.parquet
  data/research/insider_fire_context_meta.json

PIT discipline (RUL-23): all insider windows are keyed on FILING_DATE ≤ t.
The legal Form-4 filing lag is ≤2 business days after the trade, so
filing_date is the earliest public-knowledge anchor — never trans_date.

Forms computed per fire (ticker, date t):
  ins_computable        bool: ticker in panel with ≥1 filing in trailing 3y at t
  washout_flag          bool: min close/126d_high − 1 ≤ −0.20 over [t-45, t]
  ins_buyers_45d        int:  distinct open-market buyers (code=P) in [t-45, t]
  ins_cluster_washout   bool: I1 — washout_flag AND ins_buyers_45d ≥ 2 (filing_date ≤ t)
  ins_cluster_washout_3 bool: I1 sensitivity — same with ≥3 buyers (RUL-26)
  ins_cluster_pre20     bool: I2 — distinct buyers in [t-20, t] ≥ 2 (PIT)
  ins_cluster_post15    int:  DESCRIPTIVE ONLY — buyers in (t, t+15] (study-time,
                               NOT a PIT stratum; pit_at_entry=false in meta)
  ins_netusd_mcap_sn_p80 bool: I3 — trailing 6-month net_usd/mcap sector-neutral
                                pctile ≥ 80; negative-IC opportunistic filter EXCLUDED
  ins_i3_sector_neutral  bool: True = sector-neutral pctile used, False = universe-wide

Usage:
    cd /path/to/repo
    python scripts/research/build_insider_fire_context.py
    python scripts/research/build_insider_fire_context.py --panel deep
    python scripts/research/build_insider_fire_context.py --smoke    # first 500 fires each
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Path bootstrap
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_DATA           = _REPO_ROOT / "data"
_FIRES_DEEP     = _DATA / "research" / "gate_fires_deep.parquet"
_FIRES_BASKETS  = _DATA / "research" / "gate_fires_baskets.parquet"
_PANEL_DIR      = _DATA / "sec_insider" / "panel"
_FLAT_PANEL     = _DATA / "sec_insider" / "insider_panel.parquet"
_OUT_DEEP       = _DATA / "research" / "insider_fire_context_deep.parquet"
_OUT_BASKETS    = _DATA / "research" / "insider_fire_context_baskets.parquet"
_OUT_META       = _DATA / "research" / "insider_fire_context_meta.json"
_STOCKS_DIR     = _DATA / "stocks"
_BASKETS_OHLCV  = _DATA / "baskets" / "ohlcv"

# ---------------------------------------------------------------------------
# Frozen thresholds (RUL-26; no alternative tested before read)
# ---------------------------------------------------------------------------
_WASHOUT_LOOKBACK_TD  = 45      # trading days back from t for washout window
_WASHOUT_HIGH_WINDOW  = 126     # rolling window for 126d high
_WASHOUT_THRESHOLD    = -0.20   # ≤ −20% drawdown from 126d high = washout_flag
_CLUSTER_WINDOW_45    = 45      # I1: buyer window (filing_date within [t-45, t])
_CLUSTER_WINDOW_20    = 20      # I2: buyer window (filing_date within [t-20, t])
_CLUSTER_POST15       = 15      # descriptive: (t, t+15] — NOT PIT
_CLUSTER_MIN_BUYERS   = 2       # I1/I2 threshold (≥2 distinct buyers)
_CLUSTER_MIN_BUYERS_3 = 3       # I1 sensitivity (≥3 distinct buyers)
_COMPUTABLE_3Y_TD     = 756     # ≈3 years of trading days
_I3_NET_USD_MONTHS    = 6       # trailing 6-month net_usd window for I3
_I3_PERCENTILE        = 80      # sector-neutral pctile ≥ 80 (I3)

# Definition version stamped in output meta
_DEFINITION_VERSION = "v1"

# Program eras for coverage reporting (RUL-26)
_PROGRAM_ERAS = {
    "2012-2015": (pd.Timestamp("2012-01-01"), pd.Timestamp("2015-12-31")),
    "2016-2019": (pd.Timestamp("2016-01-01"), pd.Timestamp("2019-12-31")),
    "2020-2022": (pd.Timestamp("2020-01-01"), pd.Timestamp("2022-12-31")),
    "2023-2026": (pd.Timestamp("2023-01-01"), pd.Timestamp("2026-12-31")),
}


# ---------------------------------------------------------------------------
# Panel loader — concat panel/ dir; fall back to gitignored flat if fresher
# ---------------------------------------------------------------------------

def _load_insider_panel() -> pd.DataFrame:
    """Load the per-transaction insider panel.

    Preferred source: concat data/sec_insider/panel/*.parquet DIRECTLY.
    This is the only source available on a fresh worktree (the flat
    insider_panel.parquet is gitignored). If the flat file exists and is
    newer than the newest per-quarter file (i.e. it includes an in-progress
    quarter not yet flushed to its own file), use the flat file instead.
    """
    if not _PANEL_DIR.exists():
        raise FileNotFoundError(f"Panel dir not found: {_PANEL_DIR}")

    quarter_files = sorted(_PANEL_DIR.glob("*.parquet"))
    if not quarter_files:
        raise FileNotFoundError(f"No per-quarter parquets under {_PANEL_DIR}")

    # Check if flat file is fresher (intra-quarter data not yet in a per-quarter file)
    if _FLAT_PANEL.exists():
        flat_mtime = _FLAT_PANEL.stat().st_mtime
        newest_q_mtime = max(p.stat().st_mtime for p in quarter_files)
        if flat_mtime > newest_q_mtime:
            log.info("Using flat insider_panel.parquet (fresher than per-quarter files)")
            return pd.read_parquet(_FLAT_PANEL)

    log.info("Concatenating %d per-quarter parquets from %s", len(quarter_files), _PANEL_DIR)
    parts = []
    for p in quarter_files:
        try:
            df = pd.read_parquet(p)
            if not df.empty:
                parts.append(df)
        except Exception as exc:  # noqa: BLE001
            log.warning("Skipping %s: %s", p.name, exc)

    if not parts:
        raise ValueError("No rows loaded from per-quarter panel files")

    panel = pd.concat(parts, ignore_index=True).sort_values("filing_date").reset_index(drop=True)
    log.info("Panel loaded: %d rows, %d tickers, %s → %s",
             len(panel), panel["ticker"].nunique(),
             panel["filing_date"].min().date(), panel["filing_date"].max().date())
    return panel


# ---------------------------------------------------------------------------
# Price loader (reusing _get_closes pattern from W1-STS runner)
# ---------------------------------------------------------------------------

def _load_closes_deep() -> dict[str, pd.Series]:
    """Load close prices from data/stocks/*.parquet (deep panel)."""
    closes: dict[str, pd.Series] = {}
    if not _STOCKS_DIR.exists():
        log.warning("stocks dir absent: %s", _STOCKS_DIR)
        return closes
    for path in sorted(_STOCKS_DIR.glob("*.parquet")):
        ticker = path.stem
        try:
            df = pd.read_parquet(path, columns=["close"])
            s = df["close"].dropna().sort_index()
            if len(s) >= 50:
                closes[ticker] = s
        except Exception as exc:  # noqa: BLE001
            log.debug("Failed to load %s: %s", path, exc)
    log.info("Deep closes loaded: %d tickers", len(closes))
    return closes


def _load_closes_baskets() -> dict[str, pd.Series]:
    """Load close prices from data/baskets/ohlcv/*.parquet."""
    closes: dict[str, pd.Series] = {}
    if not _BASKETS_OHLCV.exists():
        log.warning("baskets ohlcv dir absent: %s", _BASKETS_OHLCV)
        return closes
    for path in sorted(_BASKETS_OHLCV.glob("*.parquet")):
        ticker = path.stem
        try:
            df = pd.read_parquet(path)
            col = "close" if "close" in df.columns else df.columns[0]
            s = df[col].dropna().sort_index()
            if len(s) >= 50:
                closes[ticker] = s
        except Exception as exc:  # noqa: BLE001
            log.debug("Failed to load %s: %s", path, exc)
    log.info("Baskets closes loaded: %d tickers", len(closes))
    return closes


# ---------------------------------------------------------------------------
# Sector map (reuse entry_strata_phase0 builder)
# ---------------------------------------------------------------------------

def _load_sector_map() -> dict[str, str]:
    try:
        from scripts.research.entry_strata_phase0 import _build_sector_map
        return _build_sector_map()
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not load sector map: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# Washout flag computation (vectorised per-ticker, searchsorted lookup)
# ---------------------------------------------------------------------------

def _build_washout_cache(
    fires: pd.DataFrame,
    closes: dict[str, pd.Series],
) -> pd.Series:
    """Compute washout_flag for each fire (PIT: only prior bars used).

    washout_flag = 1 if min over d ∈ [t-45td, t] of
                       (close_d / rolling_126d_high_strictly_prior_d − 1) ≤ −0.20.
    Uses the close price up to and including bar t.
    Rolling 126d high is computed strictly on bars prior to each bar d
    (i.e., high = max of close[d-126:d], not including d itself — this is a
    strict look-back, consistent with the "overhead supply" framing).
    """
    cache: dict[str, pd.Series] = {}

    # Precompute the rolling-126d-high series per ticker (shifted by 1 so it
    # never includes the current bar in the high).
    for ticker, close in closes.items():
        c = close.dropna().sort_index()
        if len(c) < _WASHOUT_HIGH_WINDOW + 1:
            continue
        # rolling(126).max() at bar i = max of [i-126, i-1] when we shift by 1
        roll_high = c.shift(1).rolling(_WASHOUT_HIGH_WINDOW, min_periods=_WASHOUT_HIGH_WINDOW).max()
        drawdown = (c / roll_high) - 1.0
        cache[ticker] = drawdown  # indexed by date; NaN where < 126 bars history

    results = []
    for _, row in fires.iterrows():
        ticker = str(row["ticker"])
        t = pd.Timestamp(row["date"])
        dd = cache.get(ticker)
        if dd is None:
            results.append(None)
            continue
        # Window [t-45td, t] in calendar proximity
        # We take strictly-prior bars by searching the drawdown index
        loc_t = dd.index.searchsorted(t, side="right") - 1
        if loc_t < 0:
            results.append(None)
            continue
        loc_start = max(0, loc_t - _WASHOUT_LOOKBACK_TD + 1)
        window_dd = dd.iloc[loc_start: loc_t + 1]
        valid = window_dd.dropna()
        if len(valid) == 0:
            results.append(None)
            continue
        results.append(bool(float(valid.min()) <= _WASHOUT_THRESHOLD))

    return pd.Series(results, index=fires.index, name="washout_flag")


# ---------------------------------------------------------------------------
# Insider signal helpers (filing_date-keyed, PIT)
# ---------------------------------------------------------------------------

def _build_ticker_index(panel: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Pre-index the panel by ticker for O(1) per-ticker access."""
    log.info("Indexing panel by ticker...")
    idx: dict[str, pd.DataFrame] = {}
    for ticker, grp in panel.groupby("ticker", sort=False):
        idx[str(ticker)] = grp.reset_index(drop=True)
    log.info("Ticker index built: %d tickers", len(idx))
    return idx


def _ins_buyers_in_window(
    ticker_panel: pd.DataFrame,
    t: pd.Timestamp,
    window_start_offset: int,
    window_end_offset: int,
    *,
    include_end: bool = True,
) -> int:
    """Count distinct buyer CIKs (code=P) with filing_date in [t+start, t+end] td.

    Offsets are in CALENDAR days (using timedelta), matching the spec's
    [t-45, t] phrasing for approximate trading-day windows. For the purpose of
    this script 'trading days' ~ calendar days when done via timedelta on dates
    that are business days.

    PIT: only filing_date ≤ t is used for past windows (start_offset < 0, end_offset = 0).
    Post-entry window (start_offset=1, end_offset=15) is DESCRIPTIVE ONLY.
    """
    if ticker_panel is None or ticker_panel.empty:
        return 0
    # Convert calendar day offsets to Timestamps
    t_start = t + pd.Timedelta(days=window_start_offset)
    t_end = t + pd.Timedelta(days=window_end_offset)

    fd = ticker_panel["filing_date"]
    buys = ticker_panel[ticker_panel["code"] == "P"]
    if include_end:
        mask = (buys["filing_date"] >= t_start) & (buys["filing_date"] <= t_end)
    else:
        mask = (buys["filing_date"] >= t_start) & (buys["filing_date"] < t_end)
    window_buys = buys[mask]
    return int(window_buys["rptownercik"].nunique())


# ---------------------------------------------------------------------------
# I3: trailing 6-month net_usd/mcap sector-neutral percentile
# ---------------------------------------------------------------------------

def _compute_i3_net_usd_mcap(
    fires: pd.DataFrame,
    panel: pd.DataFrame,
    closes: dict[str, pd.Series],
    sector_map: dict[str, str],
) -> tuple[pd.Series, pd.Series]:
    """Compute I3: trailing 6-month net_usd/mcap sector-neutral pctile ≥ 80.

    Construction (FDR-survivor from insider_phase0 — reuses insider_factor logic):
      net_usd_6m = buy_usd (code=P) − sell_usd (code=S) over [t-6m, t] by filing_date ≤ t
      mcap = trailing month-end close × shares_outstanding
           → We approximate mcap as close at t (full shares unavailable off-path;
             this is documented in meta)
      net_usd_mcap = net_usd_6m / close_at_t
      Sector-neutral pctile: rank within the sector of all fires at the same date;
        fall back to universe-wide pctile if sector unmapped for ≥50% of fires at date.

    Returns (ins_netusd_mcap_sn_p80, ins_i3_sector_neutral).

    Note: We do NOT apply the negative-IC opportunistic filter (CMP) — excluded per RUL-26.
    """
    ticker_idx = _build_ticker_index(panel)

    # Per fire: compute raw net_usd_mcap_6m
    net_vals: list[float | None] = []
    for _, row in fires.iterrows():
        ticker = str(row["ticker"])
        t = pd.Timestamp(row["date"])
        tp = ticker_idx.get(ticker)
        if tp is None:
            net_vals.append(None)
            continue
        # Window: [t - 6 months, t] by filing_date
        t_start_6m = t - pd.DateOffset(months=_I3_NET_USD_MONTHS)
        mask = (tp["filing_date"] >= t_start_6m) & (tp["filing_date"] <= t)
        win = tp[mask]
        if win.empty:
            net_vals.append(None)
            continue
        buys = win[win["code"] == "P"]["usd"].sum()
        sells = win[win["code"] == "S"]["usd"].sum()
        net_usd = buys - sells
        # Market-cap proxy: close at t
        close = closes.get(ticker)
        if close is None or close.empty:
            net_vals.append(None)
            continue
        c = close.dropna().sort_index()
        loc = c.index.searchsorted(t, side="right") - 1
        if loc < 0:
            net_vals.append(None)
            continue
        close_t = float(c.iloc[loc])
        if close_t <= 0:
            net_vals.append(None)
            continue
        net_vals.append(net_usd / close_t)

    net_series = pd.Series(net_vals, index=fires.index, name="net_usd_mcap_6m")

    # Sector-neutral percentile at each fire date
    fires_with_net = fires.copy()
    fires_with_net["_net"] = net_series
    fires_with_net["_sector"] = fires_with_net["ticker"].map(sector_map).fillna("")

    sn_p80: list[bool | None] = []
    sn_flag: list[bool | None] = []

    for date, grp in fires_with_net.groupby("date"):
        grp_valid = grp[grp["_net"].notna()]
        if len(grp_valid) == 0:
            for _ in range(len(grp)):
                sn_p80.append(None)
                sn_flag.append(None)
            continue

        # Determine if sector-neutral is usable (>50% of fires have a sector)
        n_sectored = int((grp_valid["_sector"] != "").sum())
        use_sn = n_sectored / max(len(grp_valid), 1) >= 0.5

        for idx, row in grp.iterrows():
            net_val = row["_net"]
            if net_val is None or (isinstance(net_val, float) and np.isnan(net_val)):
                sn_p80.append(None)
                sn_flag.append(None)
                continue

            if use_sn and row["_sector"]:
                # Rank within sector on this date
                sector_peers = grp_valid[grp_valid["_sector"] == row["_sector"]]["_net"]
                if len(sector_peers) < 3:
                    # Too few sector peers: fall back to universe-wide
                    pctile = float(np.mean(grp_valid["_net"] <= net_val))
                    sn_p80.append(pctile >= _I3_PERCENTILE / 100.0)
                    sn_flag.append(False)
                else:
                    pctile = float(np.mean(sector_peers <= net_val))
                    sn_p80.append(pctile >= _I3_PERCENTILE / 100.0)
                    sn_flag.append(True)
            else:
                # Universe-wide percentile
                pctile = float(np.mean(grp_valid["_net"] <= net_val))
                sn_p80.append(pctile >= _I3_PERCENTILE / 100.0)
                sn_flag.append(False)

    # Rebuild series aligned to fires.index (groupby changes order)
    # Re-iterate in fires order
    sn_p80_series = pd.Series(dtype=object)
    sn_flag_series = pd.Series(dtype=object)

    # Use the iteration order of groupby to rebuild: recompute in fires index order
    sn_p80_d: dict[Any, bool | None] = {}
    sn_flag_d: dict[Any, bool | None] = {}
    ptr = 0
    for date in fires_with_net.groupby("date").groups:
        grp = fires_with_net[fires_with_net["date"] == date]
        for idx in grp.index:
            sn_p80_d[idx] = sn_p80[ptr]
            sn_flag_d[idx] = sn_flag[ptr]
            ptr += 1

    out_sn_p80 = pd.Series(sn_p80_d, name="ins_netusd_mcap_sn_p80").reindex(fires.index)
    out_sn_flag = pd.Series(sn_flag_d, name="ins_i3_sector_neutral").reindex(fires.index)
    return out_sn_p80, out_sn_flag


# ---------------------------------------------------------------------------
# Main per-fire context builder
# ---------------------------------------------------------------------------

def build_context(
    fires: pd.DataFrame,
    panel: pd.DataFrame,
    closes: dict[str, pd.Series],
    sector_map: dict[str, str],
) -> pd.DataFrame:
    """Compute all per-fire insider context columns.

    All windows are filing_date-keyed (RUL-23). Post-entry column is
    descriptive only (pit_at_entry=false in meta).
    """
    fires = fires.copy()
    log.info("Building context for %d fires...", len(fires))

    # ------------------------------------------------------------------
    # Step 1: ins_computable — ticker in panel with ≥1 filing in 3y at t
    # ------------------------------------------------------------------
    log.info("  Computing ins_computable...")
    ticker_idx = _build_ticker_index(panel)
    computable: list[bool] = []
    for _, row in fires.iterrows():
        ticker = str(row["ticker"])
        t = pd.Timestamp(row["date"])
        tp = ticker_idx.get(ticker)
        if tp is None:
            computable.append(False)
            continue
        t_3y = t - pd.Timedelta(days=_COMPUTABLE_3Y_TD)
        has_filing = bool(
            ((tp["filing_date"] >= t_3y) & (tp["filing_date"] <= t)).any()
        )
        computable.append(has_filing)

    fires["ins_computable"] = computable
    log.info("  ins_computable: %d / %d fires have ≥1 filing", sum(computable), len(fires))

    # ------------------------------------------------------------------
    # Step 2: washout_flag
    # ------------------------------------------------------------------
    log.info("  Computing washout_flag...")
    fires["washout_flag"] = _build_washout_cache(fires, closes)
    n_washout = int(fires["washout_flag"].sum())
    log.info("  washout_flag: %d fires (%.1f%%)", n_washout, 100.0 * n_washout / max(len(fires), 1))

    # ------------------------------------------------------------------
    # Step 3: ins_buyers_45d — distinct buyers in [t-45, t] by filing_date
    # ------------------------------------------------------------------
    log.info("  Computing ins_buyers_45d and cluster columns...")
    buyers_45d: list[int | None] = []
    buyers_20d: list[int | None] = []
    buyers_post15: list[int | None] = []

    for _, row in fires.iterrows():
        ticker = str(row["ticker"])
        t = pd.Timestamp(row["date"])
        tp = ticker_idx.get(ticker)
        if tp is None or not row["ins_computable"]:
            buyers_45d.append(None)
            buyers_20d.append(None)
            buyers_post15.append(None)
            continue

        # [t-45, t] in calendar days — filing_date ≤ t (PIT)
        t_45 = t - pd.Timedelta(days=_CLUSTER_WINDOW_45)
        buys = tp[tp["code"] == "P"]
        mask_45 = (buys["filing_date"] >= t_45) & (buys["filing_date"] <= t)
        buyers_45d.append(int(buys[mask_45]["rptownercik"].nunique()))

        # [t-20, t] — PIT
        t_20 = t - pd.Timedelta(days=_CLUSTER_WINDOW_20)
        mask_20 = (buys["filing_date"] >= t_20) & (buys["filing_date"] <= t)
        buyers_20d.append(int(buys[mask_20]["rptownercik"].nunique()))

        # (t, t+15] — DESCRIPTIVE ONLY, NOT PIT
        t_p15 = t + pd.Timedelta(days=_CLUSTER_POST15)
        mask_post = (buys["filing_date"] > t) & (buys["filing_date"] <= t_p15)
        buyers_post15.append(int(buys[mask_post]["rptownercik"].nunique()))

    fires["ins_buyers_45d"] = buyers_45d
    fires["_buyers_20d"] = buyers_20d
    fires["_buyers_post15"] = buyers_post15

    # ------------------------------------------------------------------
    # Step 4: I1 — ins_cluster_washout (washout_flag AND buyers_45d ≥ 2)
    # ------------------------------------------------------------------
    w = fires["washout_flag"].fillna(False)
    b45 = fires["ins_buyers_45d"]
    fires["ins_cluster_washout"] = (
        w & b45.notna() & (b45 >= _CLUSTER_MIN_BUYERS)
    )
    fires["ins_cluster_washout_3"] = (
        w & b45.notna() & (b45 >= _CLUSTER_MIN_BUYERS_3)
    )

    # ------------------------------------------------------------------
    # Step 5: I2 — ins_cluster_pre20 (buyers in [t-20, t] ≥ 2, PIT)
    # ------------------------------------------------------------------
    b20 = fires["_buyers_20d"]
    fires["ins_cluster_pre20"] = (
        b20.notna() & (b20 >= _CLUSTER_MIN_BUYERS)
    )

    # ------------------------------------------------------------------
    # Step 6: ins_cluster_post15 — DESCRIPTIVE ONLY (pit_at_entry=false)
    # Column comment embedded in output meta; marked not-PIT throughout.
    # ------------------------------------------------------------------
    fires["ins_cluster_post15"] = fires["_buyers_post15"]

    # ------------------------------------------------------------------
    # Step 7: I3 — ins_netusd_mcap_sn_p80
    # ------------------------------------------------------------------
    log.info("  Computing I3 (net_usd_mcap sector-neutral pctile)...")
    sn_p80, sn_flag = _compute_i3_net_usd_mcap(fires, panel, closes, sector_map)
    fires["ins_netusd_mcap_sn_p80"] = sn_p80
    fires["ins_i3_sector_neutral"] = sn_flag

    # ------------------------------------------------------------------
    # Drop helper columns, keep spec columns only
    # ------------------------------------------------------------------
    drop_cols = [c for c in ["_buyers_20d", "_buyers_post15"] if c in fires.columns]
    fires = fires.drop(columns=drop_cols)

    return fires


# ---------------------------------------------------------------------------
# Coverage / count report
# ---------------------------------------------------------------------------

def print_coverage_report(panel_name: str, result: pd.DataFrame) -> dict[str, Any]:
    """Print and return coverage statistics."""
    total = len(result)
    n_computable = int(result["ins_computable"].sum())
    pct_computable = 100.0 * n_computable / max(total, 1)

    # Count positive fires for each form (computable fires only)
    comp = result[result["ins_computable"].fillna(False)]

    def count(col: str) -> int:
        s = comp[col] if col in comp.columns else pd.Series(dtype=bool)
        return int(s.fillna(False).sum())

    n_i1    = count("ins_cluster_washout")
    n_i1_3  = count("ins_cluster_washout_3")
    n_i2    = count("ins_cluster_pre20")
    n_i3    = count("ins_netusd_mcap_sn_p80")
    n_post15 = count("ins_cluster_post15") if "ins_cluster_post15" in comp.columns else (
        int((comp["ins_cluster_post15"] > 0).sum()) if "ins_cluster_post15" in comp.columns else 0
    )

    print(f"\n{'='*60}")
    print(f"Panel: {panel_name.upper()}")
    print(f"{'='*60}")
    print(f"Total fires:          {total:>8,}")
    print(f"ins_computable:       {n_computable:>8,}  ({pct_computable:.1f}%)")
    print(f"I1 (≥2 buyers, wash): {n_i1:>8,}  ({100.0*n_i1/max(total,1):.1f}%)")
    print(f"I1_3 (≥3 buyers):     {n_i1_3:>8,}  ({100.0*n_i1_3/max(total,1):.1f}%)")
    print(f"I2 (≥2 buyers pre20): {n_i2:>8,}  ({100.0*n_i2/max(total,1):.1f}%)")
    print(f"I3 (SN net≥p80):      {n_i3:>8,}  ({100.0*n_i3/max(total,1):.1f}%)")
    print(f"post15 (descr.):      — (descriptive only, not PIT stratum)")
    print()

    # Per-era breakdown
    era_rows: list[dict[str, Any]] = []
    print(f"{'Era':<12} {'N':>7} {'Comp%':>7} {'I1':>7} {'I1_3':>7} {'I2':>7} {'I3':>7}")
    print("-" * 60)
    dates = pd.to_datetime(result["date"])
    for era_name, (era_start, era_end) in _PROGRAM_ERAS.items():
        era_mask = (dates >= era_start) & (dates <= era_end)
        era_fires = result[era_mask]
        if len(era_fires) == 0:
            continue
        era_comp = era_fires[era_fires["ins_computable"].fillna(False)]
        e_n = len(era_fires)
        e_comp_pct = 100.0 * len(era_comp) / max(e_n, 1)
        e_i1 = int(era_comp["ins_cluster_washout"].fillna(False).sum())
        e_i1_3 = int(era_comp["ins_cluster_washout_3"].fillna(False).sum())
        e_i2 = int(era_comp["ins_cluster_pre20"].fillna(False).sum())
        e_i3 = int(era_comp["ins_netusd_mcap_sn_p80"].fillna(False).sum())
        print(f"{era_name:<12} {e_n:>7,} {e_comp_pct:>6.1f}% {e_i1:>7,} {e_i1_3:>7,} {e_i2:>7,} {e_i3:>7,}")
        era_rows.append({
            "era": era_name,
            "n_fires": e_n,
            "pct_computable": round(e_comp_pct, 2),
            "n_i1": e_i1,
            "n_i1_3": e_i1_3,
            "n_i2": e_i2,
            "n_i3": e_i3,
        })

    print("=" * 60)

    return {
        "panel": panel_name,
        "total_fires": total,
        "n_computable": n_computable,
        "pct_computable": round(pct_computable, 2),
        "n_i1": n_i1,
        "n_i1_3": n_i1_3,
        "n_i2": n_i2,
        "n_i3": n_i3,
        "era_breakdown": era_rows,
    }


# ---------------------------------------------------------------------------
# Feature meta JSON (RUL-23 triples)
# ---------------------------------------------------------------------------

def _build_meta(deep_stats: dict, baskets_stats: dict, runtime_deep: float, runtime_baskets: float) -> dict:
    return {
        "definition_version": _DEFINITION_VERSION,
        "built_date": pd.Timestamp.now().isoformat(),
        "frozen_thresholds": {
            "washout_lookback_td": _WASHOUT_LOOKBACK_TD,
            "washout_high_window_td": _WASHOUT_HIGH_WINDOW,
            "washout_threshold": _WASHOUT_THRESHOLD,
            "cluster_window_45d": _CLUSTER_WINDOW_45,
            "cluster_window_20d": _CLUSTER_WINDOW_20,
            "cluster_post15d": _CLUSTER_POST15,
            "cluster_min_buyers_i1_i2": _CLUSTER_MIN_BUYERS,
            "cluster_min_buyers_i1_3": _CLUSTER_MIN_BUYERS_3,
            "i3_net_usd_months": _I3_NET_USD_MONTHS,
            "i3_percentile": _I3_PERCENTILE,
            "computable_3y_td": _COMPUTABLE_3Y_TD,
        },
        "columns": {
            "ins_computable": {
                "source_event_date": "filing_date",
                "known_date": "filing_date",
                "pit_basis": "filing_date_leq_t",
                "pit_at_entry": True,
                "description": "Ticker present in Form-4 panel with ≥1 filing of any kind in trailing 3y at t. Computable_mask basis (Amendment 2 §C2).",
            },
            "washout_flag": {
                "source_event_date": "price_date",
                "known_date": "price_date",
                "pit_basis": "close_history_leq_t",
                "pit_at_entry": True,
                "description": "Min (close/rolling126d_high − 1) over [t-45td, t] ≤ −0.20. Uses strictly prior bars for the 126d high (no current-bar lookahead).",
            },
            "ins_buyers_45d": {
                "source_event_date": "trans_date",
                "known_date": "filing_date",
                "pit_basis": "filing_date_leq_t",
                "pit_at_entry": True,
                "description": "Distinct buyer CIKs (code=P) with filing_date in [t-45, t].",
            },
            "ins_cluster_washout": {
                "source_event_date": "filing_date",
                "known_date": "filing_date",
                "pit_basis": "filing_date_leq_t",
                "pit_at_entry": True,
                "description": "I1: washout_flag AND ins_buyers_45d ≥ 2. Threshold frozen at registration (RUL-26).",
            },
            "ins_cluster_washout_3": {
                "source_event_date": "filing_date",
                "known_date": "filing_date",
                "pit_basis": "filing_date_leq_t",
                "pit_at_entry": True,
                "description": "I1 sensitivity: washout_flag AND ins_buyers_45d ≥ 3 (RUL-26 pre-registered sensitivity).",
            },
            "ins_cluster_pre20": {
                "source_event_date": "filing_date",
                "known_date": "filing_date",
                "pit_basis": "filing_date_leq_t",
                "pit_at_entry": True,
                "description": "I2 PIT stratum: distinct buyers in [t-20, t] ≥ 2 (filing_date window).",
            },
            "ins_cluster_post15": {
                "source_event_date": "filing_date",
                "known_date": "filing_date",
                "pit_basis": "NOT_PIT_study_time_only",
                "pit_at_entry": False,
                "description": "DESCRIPTIVE ONLY — distinct buyers in (t, t+15] by filing_date. This is a STUDY-TIME DESCRIPTIVE, NOT a PIT stratum. The Codex −20/+15 window is not knowable at entry. NEVER use as a stratum in r1_estimate/grade_fires.",
            },
            "ins_netusd_mcap_sn_p80": {
                "source_event_date": "filing_date",
                "known_date": "filing_date",
                "pit_basis": "filing_date_leq_t",
                "pit_at_entry": True,
                "description": "I3: trailing 6-month net_usd/mcap (FDR-survivor construction), sector-neutral percentile ≥ 80 at t. CMP opportunistic filter EXCLUDED (negative-IC prior, RUL-26). mcap proxy = close_at_t (shares unavailable off-path; documented).",
            },
            "ins_i3_sector_neutral": {
                "source_event_date": "filing_date",
                "known_date": "filing_date",
                "pit_basis": "filing_date_leq_t",
                "pit_at_entry": True,
                "description": "Bool: True = sector-neutral pctile used for I3; False = universe-wide fallback (sector unmapped or fewer than 3 sector peers at date).",
            },
        },
        "panels": {
            "deep": {
                "runtime_seconds": round(runtime_deep, 1),
                **deep_stats,
            },
            "baskets": {
                "runtime_seconds": round(runtime_baskets, 1),
                **baskets_stats,
            },
        },
    }


# ---------------------------------------------------------------------------
# Panel runner
# ---------------------------------------------------------------------------

def run_panel(
    panel_name: str,
    fires_path: Path,
    closes: dict[str, pd.Series],
    panel: pd.DataFrame,
    sector_map: dict[str, str],
    out_path: Path,
    *,
    smoke: int | None = None,
) -> tuple[dict[str, Any], float]:
    """Build context for one panel; return (stats_dict, runtime_seconds)."""
    if not fires_path.exists():
        log.error("Fire tape not found: %s", fires_path)
        return {"error": f"fires not found: {fires_path}"}, 0.0

    fires = pd.read_parquet(fires_path)
    log.info("Panel %s: %d fires loaded", panel_name, len(fires))

    if smoke:
        fires = fires.head(smoke)
        log.info("Smoke mode: using first %d fires only", len(fires))

    t0 = time.time()
    result = build_context(fires, panel, closes, sector_map)
    elapsed = time.time() - t0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(out_path, index=False)
    log.info("Wrote %s (%d rows) in %.1fs", out_path, len(result), elapsed)

    stats = print_coverage_report(panel_name, result)
    print(f"  Runtime: {elapsed:.1f}s")

    if elapsed > 1200 and not smoke:
        log.warning("Runtime %.1fs > 20 min warning threshold", elapsed)

    return stats, elapsed


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Entry-Stack Amendment 2 T1a — insider fire context panel builder.",
    )
    parser.add_argument(
        "--panel", nargs="+", choices=["deep", "baskets"],
        default=None,
        help="Restrict to named panel(s); default runs all.",
    )
    parser.add_argument(
        "--smoke", type=int, default=None, metavar="N",
        help="Smoke mode: run on first N fires only (default: 500 if --smoke without value).",
    )
    parser.add_argument(
        "--smoke-default", action="store_true",
        help="Quick smoke: first 500 fires per panel.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )

    smoke_n: int | None = None
    if args.smoke_default:
        smoke_n = 500
    elif args.smoke is not None:
        smoke_n = args.smoke

    panels_to_run = args.panel or ["deep", "baskets"]

    # Load shared resources once
    log.info("Loading insider panel...")
    panel = _load_insider_panel()

    log.info("Loading sector map...")
    sector_map = _load_sector_map()

    panel_configs = []
    if "deep" in panels_to_run:
        log.info("Loading deep close prices...")
        closes_deep = _load_closes_deep()
        panel_configs.append(("deep", _FIRES_DEEP, closes_deep, _OUT_DEEP))
    if "baskets" in panels_to_run:
        log.info("Loading baskets close prices...")
        closes_baskets = _load_closes_baskets()
        panel_configs.append(("baskets", _FIRES_BASKETS, closes_baskets, _OUT_BASKETS))

    deep_stats: dict[str, Any] = {}
    baskets_stats: dict[str, Any] = {}
    runtime_deep = 0.0
    runtime_baskets = 0.0

    for panel_name, fires_path, closes, out_path in panel_configs:
        stats, rt = run_panel(
            panel_name, fires_path, closes, panel, sector_map, out_path,
            smoke=smoke_n,
        )
        if panel_name == "deep":
            deep_stats, runtime_deep = stats, rt
        else:
            baskets_stats, runtime_baskets = stats, rt

    # Write meta JSON
    meta = _build_meta(deep_stats, baskets_stats, runtime_deep, runtime_baskets)
    _OUT_META.write_text(json.dumps(meta, indent=2, default=str))
    log.info("Wrote meta: %s", _OUT_META)

    log.info("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
