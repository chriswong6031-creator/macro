"""Long-Hold Thesis Layer — LT-3b: Insider Sponsor feature panel builder.

Pre-registration: research/long_hold/INSIDER_SPONSOR_LH_FAMILY_PREREG.md (LOCKED).
Family id: long_hold.insider_sponsor_lh (F4, m=3).
Program: LT External Foundation — LT-3 Sponsorship lane.

This is an OFF-PATH research script — NOT wired into the nightly pipeline.
Run manually to produce:
  data/research/insider_lh_panel.parquet
  data/research/insider_lh_panel_manifest.json

PIT discipline: all insider windows are keyed on filing_date <= fire_date.
Mcap: close(fire_date) × shares from most recent fundamentals_panel row with
      asof_date <= fire_date. Missing mcap → IS-1 set to NaN (prereg law, no fallback).
Sector neutralization: ticker_sectors.parquet if present; else market-wide with
      benchmark='market' stamp.

Features computed (prereg §2):
  IS-1  insider_net_usd_mcap_6m_pct   cont  trailing 126-session net open-market
                                             insider dollars / mcap, sector-neutral
                                             cross-sectional percentile
  IS-2  cluster_buy_pre_fire           bin   >=2 distinct CIKs each >=25k P buys in
                                             [fire_date - 63 sessions, fire_date]
  IS-3  officer_buy_flag               bin   >=1 is_officer P buy >=25k in same window

Reuses panel-loading helpers from build_insider_fire_context.py:
  _load_insider_panel, _build_ticker_index, _build_union_calendar, _td_offset,
  _build_i3_universe_cache (vectorised mcap normalisation).

Fires: data/research/long_hold_labels.parquet (ALL fire dates, not label-filtered here).
Outcomes: NEVER joined into the output panel.

Usage:
    cd /path/to/repo
    python scripts/research/build_insider_lh_panel.py
    python scripts/research/build_insider_lh_panel.py --smoke   # first 500 fires
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
_DATA             = _REPO_ROOT / "data"
_LABELS_PATH      = _DATA / "research" / "long_hold_labels.parquet"
_PANEL_DIR        = _DATA / "sec_insider" / "panel"
_FLAT_PANEL       = _DATA / "sec_insider" / "insider_panel.parquet"
_FUNDAMENTALS     = _DATA / "edgar" / "fundamentals_panel.parquet"
_TICKER_SECTORS   = _DATA / "breadth" / "ticker_sectors.parquet"
_BASKETS_OHLCV    = _DATA / "baskets" / "ohlcv"
_OUT_PARQUET      = _DATA / "research" / "insider_lh_panel.parquet"
_OUT_MANIFEST     = _DATA / "research" / "insider_lh_panel_manifest.json"

# ---------------------------------------------------------------------------
# Frozen thresholds (INSIDER_SPONSOR_LH_FAMILY_PREREG.md §2)
# ---------------------------------------------------------------------------
_IS2_WINDOW_SESSIONS = 63        # IS-2/IS-3: [fire_date - 63 sessions, fire_date]
_IS2_MIN_BUYERS      = 2         # IS-2: >=2 distinct CIKs
_IS2_MIN_USD         = 25_000.0  # IS-2/IS-3: >=25k per buyer
_IS3_MIN_USD         = 25_000.0  # IS-3: >=25k per officer buy
_IS1_WINDOW_SESSIONS = 126       # IS-1: trailing 126-session (≈6-month) net USD

_DEFINITION_VERSION   = "v1.0"
_SCHEMA_VERSION       = "insider_lh_panel.v1"


# ---------------------------------------------------------------------------
# Reuse helpers from build_insider_fire_context ——————————————————————————
# We import the stable utility functions directly; windows/definitions
# come from this prereg, NOT from the ESX prereg.
# ---------------------------------------------------------------------------

def _load_insider_panel() -> pd.DataFrame:
    """Load the per-transaction insider panel (same loader as build_insider_fire_context)."""
    if not _PANEL_DIR.exists():
        raise FileNotFoundError(f"Panel dir not found: {_PANEL_DIR}")
    quarter_files = sorted(_PANEL_DIR.glob("*.parquet"))
    if not quarter_files:
        raise FileNotFoundError(f"No per-quarter parquets under {_PANEL_DIR}")
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
    panel = (
        pd.concat(parts, ignore_index=True)
        .sort_values("filing_date")
        .reset_index(drop=True)
    )
    log.info(
        "Panel loaded: %d rows, %d tickers, %s → %s",
        len(panel), panel["ticker"].nunique(),
        panel["filing_date"].min().date(), panel["filing_date"].max().date(),
    )
    return panel


def _build_ticker_index(panel: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Pre-index the panel by ticker for O(1) per-ticker access."""
    log.info("Indexing panel by ticker...")
    idx: dict[str, pd.DataFrame] = {}
    for ticker, grp in panel.groupby("ticker", sort=False):
        idx[str(ticker)] = grp.reset_index(drop=True)
    log.info("Ticker index built: %d tickers", len(idx))
    return idx


def _build_union_calendar(closes: dict[str, pd.Series]) -> pd.DatetimeIndex:
    """Return union of all trading-day indices across loaded tickers."""
    if not closes:
        return pd.DatetimeIndex([])
    all_dates: set = set()
    for s in closes.values():
        all_dates.update(s.dropna().index.tolist())
    return pd.DatetimeIndex(sorted(all_dates))


def _td_offset(
    t: pd.Timestamp,
    n_td: int,
    price_index: pd.DatetimeIndex | None,
    fallback_calendar: pd.DatetimeIndex,
    *,
    direction: int = -1,
) -> pd.Timestamp:
    """Return the date n_td trading days before/after t."""
    cal = price_index if (price_index is not None and len(price_index) > 0) else fallback_calendar
    if len(cal) == 0:
        return t + pd.Timedelta(days=int(n_td * 1.4 * direction))
    pos = cal.searchsorted(t, side="right") - 1
    if pos < 0:
        pos = 0
    target_pos = pos + direction * n_td
    target_pos = max(0, min(target_pos, len(cal) - 1))
    return cal[target_pos]


def _to_us(arr_or_ts) -> np.ndarray:
    """Convert datetime array or pd.Timestamp to int64 microseconds."""
    if isinstance(arr_or_ts, pd.Timestamp):
        return np.array([arr_or_ts.value // 1000], dtype=np.int64)
    a = np.asarray(arr_or_ts)
    if np.issubdtype(a.dtype, np.datetime64):
        return a.astype("datetime64[us]").astype("int64")
    return a.astype("int64")


# ---------------------------------------------------------------------------
# Close price loader (basket ohlcv — covers ~2,519 tickers)
# ---------------------------------------------------------------------------

def _load_closes() -> dict[str, pd.Series]:
    """Load close prices from data/baskets/ohlcv/*.parquet."""
    closes: dict[str, pd.Series] = {}
    if not _BASKETS_OHLCV.exists():
        log.warning("baskets ohlcv dir absent: %s", _BASKETS_OHLCV)
        return closes
    for path in sorted(_BASKETS_OHLCV.glob("*.parquet")):
        ticker = path.stem
        try:
            df = pd.read_parquet(path, columns=["close"])
            s = df["close"].dropna().sort_index()
            if len(s) >= 50:
                closes[ticker] = s
        except Exception as exc:  # noqa: BLE001
            log.debug("Failed to load %s: %s", path, exc)
    log.info("Closes loaded: %d tickers from baskets/ohlcv", len(closes))
    return closes


# ---------------------------------------------------------------------------
# Shares panel loader
# ---------------------------------------------------------------------------

def _load_shares_panel() -> pd.DataFrame | None:
    """Load shares from data/edgar/fundamentals_panel.parquet."""
    if not _FUNDAMENTALS.exists():
        log.warning("fundamentals_panel absent: %s", _FUNDAMENTALS)
        return None
    try:
        fp = pd.read_parquet(_FUNDAMENTALS, columns=["ticker", "asof_date", "shares"])
        fp = fp[fp["shares"].notna() & (fp["shares"] > 0)].copy()
        fp = fp.sort_values(["ticker", "asof_date"])
        log.info("Shares panel: %d rows, %d tickers", len(fp), fp["ticker"].nunique())
        return fp
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not load shares panel: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Sector map loader
# ---------------------------------------------------------------------------

def _load_sector_map() -> tuple[dict[str, str], str]:
    """Load sector map; return (map, benchmark_stamp).

    Preferred: data/breadth/ticker_sectors.parquet (populated by LT-1).
    Fallback: entry_strata_phase0._build_sector_map() (503 tickers).
    If neither available: empty map → market-wide percentile (benchmark='market').
    """
    if _TICKER_SECTORS.exists():
        try:
            df = pd.read_parquet(_TICKER_SECTORS)
            col = "sector" if "sector" in df.columns else df.columns[-1]
            mapping = dict(zip(df["ticker"], df[col]))
            log.info("Sector map loaded from ticker_sectors.parquet: %d entries", len(mapping))
            return mapping, "sector_neutral"
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not load ticker_sectors.parquet: %s", exc)

    try:
        from scripts.research.entry_strata_phase0 import _build_sector_map
        mapping = _build_sector_map()
        log.info("Sector map from entry_strata_phase0: %d entries", len(mapping))
        return mapping, "sector_neutral"
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not load sector map via entry_strata: %s", exc)

    log.info("No sector map available; using market-wide percentile (benchmark='market')")
    return {}, "market"


# ---------------------------------------------------------------------------
# IS-1: insider_net_usd_mcap_6m_pct — vectorised cross-sectional percentile
# ---------------------------------------------------------------------------

def _build_is1_panel(
    fires: pd.DataFrame,
    panel: pd.DataFrame,
    shares_panel: pd.DataFrame | None,
    closes: dict[str, pd.Series],
    sector_map: dict[str, str],
    benchmark_stamp: str,
) -> pd.Series:
    """Compute IS-1 (insider_net_usd_mcap_6m_pct) for each fire.

    Definition: trailing 126-session net open-market insider dollars (ΣP − ΣS)
    / mcap at fire_date, sector-neutral cross-sectional percentile.
    Missing mcap → NaN (prereg law, no fallback).
    Only direct open-market P/S transactions (direct=True, code ∈ {P, S}).

    Implementation: vectorised per-ticker across all fire dates.
    """
    from scipy.stats import rankdata  # for midrank percentile

    _US_PER_DAY = 24 * 3600 * 1_000_000
    _6M_US = int(183 * _US_PER_DAY)  # approximate 126 sessions ≈ 6 months

    # Filter to direct open-market only
    sub = panel[panel["code"].isin(["P", "S"]) & (panel["direct"] == True)].copy()
    sub["signed_usd"] = sub["usd"] * sub["code"].map({"P": 1.0, "S": -1.0})

    # Aggregate to (ticker, filing_date) → net_usd
    net_by_tfd = (
        sub.groupby(["ticker", "filing_date"])["signed_usd"]
        .sum()
    )

    # Build per-ticker sorted arrays of (filing_date_us, net_usd)
    sorted_events: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for ticker, grp in net_by_tfd.groupby(level=0):
        dates_us = _to_us(grp.index.get_level_values("filing_date").values)
        nets = grp.values.astype("float64")
        order = np.argsort(dates_us, stable=True)
        sorted_events[str(ticker)] = (dates_us[order], nets[order])

    # Build shares lookup
    pit_shares_map: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    if shares_panel is not None and not shares_panel.empty:
        for ticker, grp in shares_panel.groupby("ticker"):
            grp = grp.sort_values("asof_date")
            pit_shares_map[str(ticker)] = (
                _to_us(grp["asof_date"].values),
                grp["shares"].values.astype("float64"),
            )

    # Build close cache
    close_cache: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for ticker, s in closes.items():
        c = s.dropna().sort_index()
        if len(c) > 0:
            close_cache[ticker] = (
                _to_us(c.index.values),
                c.values.astype("float64"),
            )

    # Unique fire dates
    unique_dates = sorted(set(fires["fire_date"].tolist()))
    fire_dates_us = np.array([int(_to_us(d)[0]) for d in unique_dates], dtype=np.int64)

    # For each unique fire date, compute net_usd_6m/mcap per ticker
    cache_list: list[dict[str, float]] = [{} for _ in range(len(unique_dates))]
    t_6m_us_arr = fire_dates_us - _6M_US

    for ticker, (date_arr, net_arr) in sorted_events.items():
        if len(date_arr) == 0:
            continue
        # Window [t-6m, t] using filing_date
        hi_arr = np.searchsorted(date_arr, fire_dates_us, side="right")
        lo6_arr = np.searchsorted(date_arr, t_6m_us_arr, side="left")
        has_data = hi_arr > lo6_arr
        if not np.any(has_data):
            continue

        cum_net = np.concatenate(([0.0], np.cumsum(net_arr)))
        net_usd_arr = cum_net[hi_arr] - cum_net[lo6_arr]

        # PIT close
        if ticker not in close_cache:
            continue
        d_arr_c, c_arr_c = close_cache[ticker]
        close_pos = np.searchsorted(d_arr_c, fire_dates_us, side="right") - 1
        valid_close = close_pos >= 0
        combined = has_data & valid_close
        if not np.any(combined):
            continue

        close_vals = np.where(combined, c_arr_c[np.maximum(close_pos, 0)], 0.0)
        combined = combined & (close_vals > 0)
        if not np.any(combined):
            continue

        # PIT shares → mcap = close × shares (or just close if no shares)
        if ticker in pit_shares_map:
            asof_arr_s, shares_arr_s = pit_shares_map[ticker]
            sp = np.searchsorted(asof_arr_s, fire_dates_us, side="right") - 1
            valid_shares = sp >= 0
            shares_vals = np.where(
                valid_shares,
                shares_arr_s[np.maximum(sp, 0)],
                np.nan,
            )
            has_shares = valid_shares & (shares_vals > 0)
            denom_arr = np.where(
                has_shares & combined,
                close_vals * shares_vals,
                np.nan,  # missing mcap → NaN per prereg law
            )
        else:
            # No shares at all → mcap unknown → NaN
            denom_arr = np.full(len(fire_dates_us), np.nan)

        valid_denom = combined & (denom_arr > 0)
        if not np.any(valid_denom):
            continue

        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.where(
                valid_denom,
                net_usd_arr / np.where(denom_arr != 0, denom_arr, np.nan),
                np.nan,
            )

        for di in np.where(valid_denom)[0]:
            cache_list[di][ticker] = float(ratio[di])

    date_to_idx = {d: i for i, d in enumerate(unique_dates)}

    # Build cross-sectional sector-neutral percentile per fire
    results: list[float | None] = []
    for _, row in fires.iterrows():
        ticker = str(row["ticker"])
        t = pd.Timestamp(row["fire_date"])
        di = date_to_idx.get(t)
        if di is None:
            results.append(None)
            continue
        universe = cache_list[di]  # {ticker: net_usd_mcap_ratio}
        if ticker not in universe:
            results.append(None)
            continue
        own_val = universe[ticker]

        # Sector-neutral or market-wide comparison pool
        if sector_map:
            own_sector = sector_map.get(ticker)
            if own_sector is not None:
                peer_vals = np.array(
                    [v for t2, v in universe.items() if sector_map.get(t2) == own_sector],
                    dtype=float,
                )
            else:
                peer_vals = np.array(list(universe.values()), dtype=float)
        else:
            peer_vals = np.array(list(universe.values()), dtype=float)

        peer_vals = peer_vals[np.isfinite(peer_vals)]
        if len(peer_vals) == 0:
            results.append(None)
            continue

        # Midrank percentile (same as I3 in build_insider_fire_context v1.2)
        ranks = rankdata(peer_vals, method="average")
        own_rank = float(rankdata(np.append(peer_vals[peer_vals != own_val], [own_val]), method="average")[-1])
        # Re-rank own_val in the full pool (self-inclusive)
        all_vals = peer_vals
        if own_val not in all_vals:
            all_vals = np.append(all_vals, own_val)
        all_ranks = rankdata(all_vals, method="average")
        # Find own position
        own_idx = np.where(all_vals == own_val)[0]
        if len(own_idx) == 0:
            results.append(None)
            continue
        own_rank_final = float(all_ranks[own_idx[-1]])
        pct = float((own_rank_final - 1) / max(len(all_vals) - 1, 1) * 100.0)
        results.append(pct)

    return pd.Series(results, index=fires.index, name="insider_net_usd_mcap_6m_pct")


# ---------------------------------------------------------------------------
# IS-2 and IS-3: binary cluster buy / officer buy flags (vectorised)
# ---------------------------------------------------------------------------

def _build_is2_is3_panel(
    fires: pd.DataFrame,
    panel: pd.DataFrame,
    closes: dict[str, pd.Series],
    union_cal: pd.DatetimeIndex,
) -> tuple[pd.Series, pd.Series]:
    """Compute IS-2 (cluster_buy_pre_fire) and IS-3 (officer_buy_flag).

    IS-2: >=2 distinct insider CIKs each with >=25k open-market P buys,
          filing_date within [fire_date - 63 sessions, fire_date].
    IS-3: >=1 is_officer open-market P buy >=25k in same window.

    PIT: filing_date <= fire_date (strict <=).
    """
    # Filter to direct open-market P only (both IS-2 and IS-3 use P buys)
    buys = panel[
        (panel["code"] == "P") & (panel["direct"] == True)
    ][["ticker", "filing_date", "rptownercik", "is_officer", "usd"]].copy()

    # Build per-ticker sorted arrays for fast window queries
    buy_by_ticker: dict[str, pd.DataFrame] = {}
    for ticker, grp in buys.groupby("ticker", sort=False):
        buy_by_ticker[str(ticker)] = grp.sort_values("filing_date").reset_index(drop=True)

    # Build close index per ticker for trading-day offset
    close_index_by_ticker: dict[str, pd.DatetimeIndex] = {}
    for ticker, s in closes.items():
        c = s.dropna().sort_index()
        if len(c) > 0:
            close_index_by_ticker[ticker] = c.index

    is2_results: list[bool | None] = []
    is3_results: list[bool | None] = []

    for _, row in fires.iterrows():
        ticker = str(row["ticker"])
        t = pd.Timestamp(row["fire_date"])

        grp = buy_by_ticker.get(ticker)
        if grp is None or len(grp) == 0:
            # Ticker has no P buys at all — both flags False (computable as 0)
            is2_results.append(False)
            is3_results.append(False)
            continue

        # Window start: fire_date - 63 trading sessions
        price_idx = close_index_by_ticker.get(ticker)
        window_start = _td_offset(t, _IS2_WINDOW_SESSIONS, price_idx, union_cal, direction=-1)

        # Filter to window: filing_date in [window_start, fire_date]
        mask = (grp["filing_date"] >= window_start) & (grp["filing_date"] <= t)
        window_buys = grp[mask]

        # IS-3: >=1 officer buy >=25k
        officer_buys = window_buys[
            (window_buys["is_officer"] == True) & (window_buys["usd"] >= _IS3_MIN_USD)
        ]
        is3_results.append(len(officer_buys) > 0)

        # IS-2: >=2 distinct CIKs each with >=25k
        qualifying_buys = window_buys[window_buys["usd"] >= _IS2_MIN_USD]
        distinct_buyers = qualifying_buys.groupby("rptownercik")["usd"].sum()
        qualifying_ciks = (distinct_buyers >= _IS2_MIN_USD).sum()
        is2_results.append(int(qualifying_ciks) >= _IS2_MIN_BUYERS)

    return (
        pd.Series(is2_results, index=fires.index, name="cluster_buy_pre_fire"),
        pd.Series(is3_results, index=fires.index, name="officer_buy_flag"),
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_panel(fires: pd.DataFrame, smoke: bool = False) -> pd.DataFrame:
    """Build insider_lh_panel for all fires (or first 500 in smoke mode)."""
    if smoke:
        fires = fires.head(500).copy()
        log.info("SMOKE MODE: using first %d fires", len(fires))

    # Load data
    panel = _load_insider_panel()
    shares_panel = _load_shares_panel()
    closes = _load_closes()
    sector_map, benchmark_stamp = _load_sector_map()
    union_cal = _build_union_calendar(closes)

    log.info(
        "Building IS-1 (insider_net_usd_mcap_6m_pct) for %d fires...", len(fires)
    )
    t0 = time.monotonic()
    is1 = _build_is1_panel(fires, panel, shares_panel, closes, sector_map, benchmark_stamp)
    log.info("IS-1 done in %.1fs; non-null: %d / %d", time.monotonic() - t0, is1.notna().sum(), len(fires))

    log.info("Building IS-2 (cluster_buy_pre_fire) and IS-3 (officer_buy_flag)...")
    t0 = time.monotonic()
    is2, is3 = _build_is2_is3_panel(fires, panel, closes, union_cal)
    log.info("IS-2/IS-3 done in %.1fs", time.monotonic() - t0)

    # Assemble output — outcome columns are NEVER included
    out = fires[["ticker", "fire_date"]].copy()
    out["insider_net_usd_mcap_6m_pct"] = is1.values
    out["cluster_buy_pre_fire"] = is2.values
    out["officer_buy_flag"] = is3.values
    out["benchmark"] = benchmark_stamp
    out["horizon_role"] = "hold_thesis"
    out["_display_only"] = True
    out["definition_version"] = _DEFINITION_VERSION
    out["fdr_family"] = "long_hold.insider_sponsor_lh"

    # Coverage stats
    is1_cov = float(out["insider_net_usd_mcap_6m_pct"].notna().mean())
    is2_cov = float(out["cluster_buy_pre_fire"].notna().mean())
    is3_cov = float(out["officer_buy_flag"].notna().mean())
    log.info(
        "Coverage: IS-1 %.1f%%, IS-2 %.1f%%, IS-3 %.1f%%",
        is1_cov * 100, is2_cov * 100, is3_cov * 100,
    )

    return out


def write_manifest(
    out: pd.DataFrame,
    benchmark_stamp: str,
    smoke: bool,
) -> dict:
    """Build and return manifest dict."""
    n_fires = len(out)
    n_is1 = int(out["insider_net_usd_mcap_6m_pct"].notna().sum())
    n_is2_true = int(out["cluster_buy_pre_fire"].sum(skipna=True))
    n_is3_true = int(out["officer_buy_flag"].sum(skipna=True))

    manifest = {
        "schema": _SCHEMA_VERSION,
        "definition_version": _DEFINITION_VERSION,
        "family": "long_hold.insider_sponsor_lh",
        "fdr_family": "long_hold",
        "horizon_role": "hold_thesis",
        "_display_only": True,
        "benchmark": benchmark_stamp,
        "smoke_mode": smoke,
        "n_fires": int(n_fires),
        "feature_coverage": {
            "IS-1_insider_net_usd_mcap_6m_pct": {
                "n_non_null": int(n_is1),
                "coverage_frac": float(n_is1 / max(n_fires, 1)),
            },
            "IS-2_cluster_buy_pre_fire": {
                "n_non_null": int(out["cluster_buy_pre_fire"].notna().sum()),
                "n_true": int(n_is2_true),
                "coverage_frac": float(out["cluster_buy_pre_fire"].notna().mean()),
            },
            "IS-3_officer_buy_flag": {
                "n_non_null": int(out["officer_buy_flag"].notna().sum()),
                "n_true": int(n_is3_true),
                "coverage_frac": float(out["officer_buy_flag"].notna().mean()),
            },
        },
        "fire_date_range": {
            "min": str(out["fire_date"].min().date()),
            "max": str(out["fire_date"].max().date()),
        },
        "unique_tickers": int(out["ticker"].nunique()),
        "scored_path_surfaces": [],
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
    }
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser(description="Build insider_lh_panel.parquet")
    ap.add_argument("--smoke", action="store_true", help="Run on first 500 fires only")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    log.info("Loading fires from %s", _LABELS_PATH)
    fires = pd.read_parquet(_LABELS_PATH, columns=["ticker", "fire_date"])
    log.info("Fires: %d rows, %d unique tickers", len(fires), fires["ticker"].nunique())

    # Load sector map for manifest stamp
    _, benchmark_stamp = _load_sector_map()

    out = build_panel(fires, smoke=args.smoke)

    _OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(_OUT_PARQUET, index=False)
    log.info("Wrote %s (%d rows)", _OUT_PARQUET, len(out))

    manifest = write_manifest(out, benchmark_stamp, args.smoke)
    _OUT_MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log.info("Wrote manifest %s", _OUT_MANIFEST)

    # Summary
    print("\n=== insider_lh_panel build summary ===")
    print(f"Fires processed : {manifest['n_fires']:,}")
    print(f"Unique tickers  : {manifest['unique_tickers']:,}")
    print(f"Benchmark       : {benchmark_stamp}")
    for feat, cov in manifest["feature_coverage"].items():
        print(f"{feat:<45} coverage={cov['coverage_frac']:.1%}", end="")
        if "n_true" in cov:
            print(f"  n_true={cov['n_true']:,}")
        else:
            print()
    print()


if __name__ == "__main__":
    main()
