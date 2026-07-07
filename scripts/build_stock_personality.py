"""On-demand PIT personality-label series builder — stock-personality W3.

NOT a nightly job. The nightly path is the ``build_stock_library`` per-ticker
loop (R-SP9 of the masterplan). This CLI is used exclusively for the W3 retro
backfill: computing full-history PIT ``chart_personality`` + ``microstructure``
label series for the deep/massive corpus so the compat study can join them.

Output: ``data/research/personality_pit_labels.parquet``
Schema (per ticker × date):
    ticker              str
    date                datetime
    chart_labels        str   ("|"-joined list or null)
    chart_primary       str   (first label or null)
    micro_labels        str   ("|"-joined list or null)
    micro_primary       str   (first label or null)
    archetype           str   (PIT join; null when no row with asof_date <= date)
    archetype_asof      datetime
    archetype_fy        int

PIT archetype join rule (R-SP12): attach the row with the greatest
``asof_date <= date`` from ``data/archetypes/history.parquet``.
``asof_date = period_end + 120d`` is the conservative synthetic filing-lag
proxy consistent with the EDGAR PIT law.

Lineage: research/STOCK_PERSONALITY_MASTERPLAN_BY_FABLE.md §3.1, R-SP12
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Repo root & logging
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("build_stock_personality")

# ---------------------------------------------------------------------------
# Thin adapters to engine thresholds (never modify engine thresholds here)
# ---------------------------------------------------------------------------
# Import the frozen cascade constants from engine/stock_personality.py so
# the only source of truth is the engine module.  We call the private
# _classify_chart / _classify_microstructure functions via the public
# adapter functions below (snapshot-dict -> labels).  This is the "thin
# adapter" pattern specified in the brief.
from engine.stock_personality import (  # noqa: E402
    _classify_chart,           # type: ignore[attr-defined]
    _classify_microstructure,  # type: ignore[attr-defined]
)
from engine.path_personality import feature_series as _feature_series  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_DATA_DIR = _REPO_ROOT / "data"
_ARCHETYPE_PATH = _DATA_DIR / "archetypes" / "history.parquet"
_STOCKS_DEEP_DIR = _DATA_DIR / "stocks"
_STOCKS_MASSIVE_DIR = _DATA_DIR / "stocks_massive"
_OUT_PATH = _DATA_DIR / "research" / "personality_pit_labels.parquet"

# Minimum bars for feature_series to be meaningful
_MIN_BARS = 300


# ---------------------------------------------------------------------------
# Archetype PIT join
# ---------------------------------------------------------------------------
def _load_archetype_history(path: Path) -> pd.DataFrame:
    """Load archetype history with sorted DatetimeIndex on asof_date."""
    df = pd.read_parquet(path)
    df["asof_date"] = pd.to_datetime(df["asof_date"])
    df = df.sort_values(["ticker", "asof_date"]).reset_index(drop=True)
    return df


def _build_archetype_lookup(hist: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Per-ticker sorted archetype history for fast PIT join."""
    result: dict[str, pd.DataFrame] = {}
    for tk, g in hist.groupby("ticker"):
        result[str(tk)] = g.reset_index(drop=True)
    return result


def _archetype_at(ticker_hist: pd.DataFrame | None, date: pd.Timestamp) -> dict[str, Any]:
    """Return (archetype, asof_date, fy) for the PIT row with greatest asof_date <= date.

    Returns {"archetype": None, "archetype_asof": None, "archetype_fy": None}
    when no attachable row exists (pre-FY2009 or ticker not in history).
    """
    null = {"archetype": None, "archetype_asof": None, "archetype_fy": None}
    if ticker_hist is None or ticker_hist.empty:
        return null
    # greatest asof_date <= date (R-SP12 join rule)
    mask = ticker_hist["asof_date"] <= date
    if not mask.any():
        return null
    row = ticker_hist[mask].iloc[-1]
    return {
        "archetype": str(row["archetype"]) if pd.notna(row["archetype"]) else None,
        "archetype_asof": row["asof_date"],
        "archetype_fy": int(row["fy"]) if pd.notna(row["fy"]) else None,
    }


# ---------------------------------------------------------------------------
# Per-ticker PIT label series
# ---------------------------------------------------------------------------
def _load_ohlcv(ticker: str, panel: str) -> pd.DataFrame | None:
    """Load OHLCV for a ticker from the appropriate panel directory."""
    if panel == "deep":
        p = _STOCKS_DEEP_DIR / f"{ticker}.parquet"
    elif panel == "massive":
        p = _STOCKS_MASSIVE_DIR / f"{ticker}.parquet"
    else:
        raise ValueError(f"Unknown panel: {panel}")
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    # Normalise index name
    df.index = pd.to_datetime(df.index)
    df.index.name = "date"
    # Lowercase columns
    df.columns = [c.lower() for c in df.columns]
    return df.sort_index()


def _chart_micro_series_for_ticker(
    ticker: str,
    ohlcv: pd.DataFrame,
) -> pd.DataFrame:
    """Compute PIT chart+micro label series using engine cascades.

    Note: data/stocks has no 'open' column — gap features that require
    open (event_gap_contrib_252, gap_share_252) will be NaN. This is a
    known limitation documented in the report (gap-features-unavailable
    on deep corpus).
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            feat_df = _feature_series(ohlcv)
        except Exception as exc:
            log.warning("feature_series failed for %s: %s", ticker, exc)
            return pd.DataFrame()

    rows = []
    for i, (dt, feat_row) in enumerate(feat_df.iterrows()):
        path_features_dict: dict[str, Any] = dict(feat_row)
        # _pf_n_bars reads from path_features["coverage"]["n_bars"] per engine convention
        path_features_dict["coverage"] = {"n_bars": i + 1}  # bars available up to this row

        chart_labels, _, _ = _classify_chart(path_features_dict, tech=None)
        micro_labels, _, _ = _classify_microstructure(path_features_dict)

        chart_str = "|".join(chart_labels) if chart_labels else None
        chart_primary = chart_labels[0] if chart_labels else None
        micro_str = "|".join(micro_labels) if micro_labels else None
        micro_primary = micro_labels[0] if micro_labels else None

        rows.append({
            "date": dt,
            "chart_labels": chart_str,
            "chart_primary": chart_primary,
            "micro_labels": micro_str,
            "micro_primary": micro_primary,
        })

    if not rows:
        return pd.DataFrame()

    result = pd.DataFrame(rows)
    result["ticker"] = ticker
    return result[["ticker", "date", "chart_labels", "chart_primary", "micro_labels", "micro_primary"]]


def _process_ticker(
    ticker: str,
    panel: str,
    archetype_lookup: dict[str, pd.DataFrame],
    start: pd.Timestamp | None,
    end: pd.Timestamp | None,
) -> pd.DataFrame:
    """Full PIT label pipeline for one ticker."""
    ohlcv = _load_ohlcv(ticker, panel)
    if ohlcv is None or len(ohlcv) < _MIN_BARS:
        log.debug("Skipping %s: insufficient bars", ticker)
        return pd.DataFrame()

    # Date filter
    if start is not None:
        ohlcv = ohlcv[ohlcv.index >= start]
    if end is not None:
        ohlcv = ohlcv[ohlcv.index <= end]
    if len(ohlcv) < _MIN_BARS:
        return pd.DataFrame()

    # Chart + micro series
    label_df = _chart_micro_series_for_ticker(ticker, ohlcv)
    if label_df.empty:
        return pd.DataFrame()

    # Archetype PIT join (one join per row, using vectorized searchsorted)
    ticker_hist = archetype_lookup.get(ticker)
    arch_data = {"archetype": [], "archetype_asof": [], "archetype_fy": []}
    for dt in label_df["date"]:
        a = _archetype_at(ticker_hist, dt)
        arch_data["archetype"].append(a["archetype"])
        arch_data["archetype_asof"].append(a["archetype_asof"])
        arch_data["archetype_fy"].append(a["archetype_fy"])

    label_df["archetype"] = arch_data["archetype"]
    label_df["archetype_asof"] = arch_data["archetype_asof"]
    label_df["archetype_fy"] = arch_data["archetype_fy"]

    return label_df


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _resolve_tickers(args: argparse.Namespace) -> list[str]:
    """Resolve --tickers or enumerate from --panel directory."""
    panel = args.panel
    panel_dir = _STOCKS_DEEP_DIR if panel == "deep" else _STOCKS_MASSIVE_DIR

    if args.tickers:
        return [t.strip().upper() for t in args.tickers.split(",") if t.strip()]

    if not panel_dir.exists():
        log.error("Panel directory not found: %s", panel_dir)
        sys.exit(1)

    return sorted(
        p.stem for p in panel_dir.glob("*.parquet")
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build PIT personality label series for the retro compat study."
    )
    parser.add_argument("--tickers", help="Comma-separated ticker list (default: all in panel)")
    parser.add_argument("--panel", choices=["deep", "massive"], default="deep",
                        help="Data panel to use (default: deep)")
    parser.add_argument("--start", help="Start date YYYY-MM-DD (default: all history)")
    parser.add_argument("--end", help="End date YYYY-MM-DD (default: all history)")
    parser.add_argument("--out", help=f"Output path (default: {_OUT_PATH})")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    logging.getLogger().setLevel(args.log_level)

    start = pd.Timestamp(args.start) if args.start else None
    end = pd.Timestamp(args.end) if args.end else None
    out_path = Path(args.out) if args.out else _OUT_PATH
    out_path.parent.mkdir(parents=True, exist_ok=True)

    tickers = _resolve_tickers(args)
    log.info("Panel: %s | Tickers: %d | Date range: %s → %s",
             args.panel, len(tickers),
             args.start or "all", args.end or "all")

    if not _ARCHETYPE_PATH.exists():
        log.error("Archetype history not found: %s", _ARCHETYPE_PATH)
        sys.exit(1)

    log.info("Loading archetype history...")
    arch_hist = _load_archetype_history(_ARCHETYPE_PATH)
    archetype_lookup = _build_archetype_lookup(arch_hist)
    log.info("Archetype history: %d tickers, %d rows", len(archetype_lookup), len(arch_hist))

    all_frames: list[pd.DataFrame] = []
    n_ok = n_skip = n_err = 0

    for i, ticker in enumerate(tickers, 1):
        if i % 20 == 0 or i == len(tickers):
            log.info("Progress: %d/%d (ok=%d skip=%d err=%d)",
                     i, len(tickers), n_ok, n_skip, n_err)
        try:
            df = _process_ticker(ticker, args.panel, archetype_lookup, start, end)
            if df.empty:
                n_skip += 1
            else:
                all_frames.append(df)
                n_ok += 1
        except Exception as exc:
            log.warning("Error processing %s: %s", ticker, exc)
            n_err += 1

    if not all_frames:
        log.error("No output produced. Check inputs.")
        sys.exit(1)

    result = pd.concat(all_frames, ignore_index=True)
    result["date"] = pd.to_datetime(result["date"])

    result.to_parquet(out_path, index=False)
    log.info(
        "Wrote %s: %d rows, %d tickers (ok=%d skip=%d err=%d)",
        out_path, len(result), result["ticker"].nunique(), n_ok, n_skip, n_err,
    )


if __name__ == "__main__":
    main()
