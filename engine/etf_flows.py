"""engine/etf_flows.py — Sector SPDR ETF creation/redemption proxy store.

Reads the raw SO snapshots accumulated by collectors.sponsors.SectorFlowAdapter
(data/flows/<TICKER>.parquet, columns: nav, aum_mn, so_mn) and derives a daily
**creation/redemption proxy** column:

    flow_mn = delta(so_mn) x nav(t)   [$millions, signed]

Positive = net creation (inflows); negative = net redemption (outflows).

The derived wide frame is persisted to data/flows/etf_flow_proxy.parquet so
downstream tile builders can load a single file rather than joining 11 parquets.

Schema of etf_flow_proxy.parquet:
  index: date (datetime64[ns], UTC midnight)
  columns: one per fund, named "<TICKER>_flow_mn"   (float64, NaN on day-0 row)

This module is DISPLAY-DATA only — it never feeds a score or allocation path.
Calling rebuild() is idempotent; re-runs upsert (date wins over existing row).
Call from scripts/build_site.py or a dedicated cron after the collect lane lands.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

_FLOWS_DIR = Path(__file__).parent.parent / "data" / "flows"
_PROXY_PATH = _FLOWS_DIR / "etf_flow_proxy.parquet"

SECTOR_TICKERS = ("XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY")


def _load_so(ticker: str) -> pd.Series | None:
    """Load so_mn series for one ticker. Returns None if file absent."""
    p = _FLOWS_DIR / f"{ticker}.parquet"
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    if "so_mn" not in df.columns or "nav" not in df.columns:
        log.warning("etf_flows: %s missing required columns, skipping", ticker)
        return None
    df = df.sort_index()
    return df


def _derive_flow(df: pd.DataFrame) -> pd.Series:
    """delta(so_mn) x nav(t) — creation/redemption proxy in $mn."""
    return (df["so_mn"].diff() * df["nav"]).rename("flow_mn")


def flows_wide(tickers: tuple[str, ...] = SECTOR_TICKERS) -> pd.DataFrame | None:
    """Return wide frame: index=date, columns=<TICKER>_flow_mn. None if no data."""
    cols = {}
    for t in tickers:
        df = _load_so(t)
        if df is None or len(df) < 2:
            continue
        s = _derive_flow(df)
        cols[f"{t}_flow_mn"] = s
    if not cols:
        return None
    wide = pd.DataFrame(cols)
    wide.index.name = "date"
    return wide.sort_index()


def rebuild(tickers: tuple[str, ...] = SECTOR_TICKERS,
            flows_dir: Path | None = None,
            proxy_path: Path | None = None) -> Path | None:
    """Rebuild etf_flow_proxy.parquet from the per-ticker SO snapshots.

    Upserts: existing rows for dates not in the new frame are preserved; new
    dates overwrite (date dedup: latest write wins). Returns the output path on
    success, None if no data is available yet.
    """
    _fdir = flows_dir or _FLOWS_DIR
    _ppath = proxy_path or _PROXY_PATH

    wide = flows_wide(tickers)
    if wide is None:
        log.warning("etf_flows: no SO data found — skipping proxy build")
        return None

    # Merge with existing store (upsert by date)
    if _ppath.exists():
        existing = pd.read_parquet(_ppath)
        # Align columns: union, fill missing with NaN
        all_cols = existing.columns.union(wide.columns)
        existing = existing.reindex(columns=all_cols)
        wide = wide.reindex(columns=all_cols)
        merged = pd.concat([existing, wide])
        merged = merged[~merged.index.duplicated(keep="last")].sort_index()
    else:
        merged = wide

    merged.index.name = "date"
    _ppath.parent.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(_ppath)
    log.info("etf_flows: wrote %s rows x %s cols -> %s",
             len(merged), len(merged.columns), _ppath)
    return _ppath


def load_proxy(proxy_path: Path | None = None) -> pd.DataFrame | None:
    """Load the persisted proxy store. Returns None if file absent."""
    p = proxy_path or _PROXY_PATH
    if not p.exists():
        return None
    return pd.read_parquet(p)


def proxy_json(n_days: int = 21,
               proxy_path: Path | None = None) -> dict | None:
    """Return display-ready JSON payload for the P3.1 tile.

    ``{asof, depth, funds: [{ticker, flow_1d, flow_5d, flow_21d}], net_flow_1d}``
    All flow values in $mn (float). None until the proxy store exists.
    """
    df = load_proxy(proxy_path)
    if df is None or df.empty:
        return None
    df = df.dropna(how="all").sort_index()
    if len(df) < 2:
        return None
    funds = []
    net_1d = 0.0
    for col in df.columns:
        ticker = col.replace("_flow_mn", "")
        s = df[col].dropna()
        if s.empty:
            continue
        f1d = float(s.iloc[-1]) if len(s) >= 1 else None
        f5d = float(s.tail(5).sum()) if len(s) >= 2 else None
        f21d = float(s.tail(21).sum()) if len(s) >= 2 else None
        if f1d is not None:
            net_1d += f1d
        funds.append({"ticker": ticker, "flow_1d": f1d, "flow_5d": f5d, "flow_21d": f21d})
    return {
        "asof": str(df.index.max().date()),
        "depth": int(len(df)),
        "funds": funds,
        "net_flow_1d": round(net_1d, 2),
        "label": "creation/redemption proxy",
    }
