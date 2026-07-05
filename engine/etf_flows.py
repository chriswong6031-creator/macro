"""engine/etf_flows.py — Sector SPDR ETF creation/redemption proxy store.

**Design note — relationship to collectors.sponsors**

``collectors.sponsors`` already contains ``flows_table()`` and
``sector_flow_periods()`` which compute the identical delta(SO)×NAV
creation/redemption proxy and are consumed by ``scripts/build_sector_central.py``
to render the live "Where sector-ETF money is flowing" board.  This module
does NOT reimplement that math; ``flows_wide()`` delegates directly to
``collectors.sponsors.flows_table()`` as the single source of truth.

What this module adds on top is a **persisted wide parquet store**
(``data/flows/etf_flow_proxy.parquet``) so that downstream P3.1 tile builders
can load one file instead of joining 11 per-ticker parquets, and a
``proxy_json()`` API shaped for that tile (1D/5D/21D windows, net_flow_1d).
The ``sector_flow_periods()`` API (1D/3D/1W/2W/1M multi-window) remains
canonical for the sector-central board; the two paths read the same underlying
data and will not drift.

**Note on spec deviation**: the P1.7 roadmap referenced day-aggregate SO from
the massive store as the source; that source is infeasible (massive is
OHLCV-only, no shares-outstanding column).  The SSGA fundfinder SO used here
(AUM/NAV, same as-of date) is exact and was substituted accordingly.

Schema of etf_flow_proxy.parquet:
  index: date (datetime64[ns])
  columns: one per fund, named "<TICKER>_flow_mn"   (float64, NaN on day-0 row)

This module is DISPLAY-DATA only — it never feeds a score or allocation path.
Calling rebuild() is idempotent; re-runs upsert (date wins over existing row).
Call from scripts/build_site.py or a dedicated cron after the collect lane lands.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

_FLOWS_DIR = Path(__file__).parent.parent / "data" / "flows"
_PROXY_PATH = _FLOWS_DIR / "etf_flow_proxy.parquet"

SECTOR_TICKERS = ("XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY")


def _load_so(ticker: str, flows_dir: Path | None = None) -> pd.DataFrame | None:
    """Load raw SO snapshot for one ticker from data/flows/<TICKER>.parquet.

    Used by tests and by _derive_flow; production callers should prefer
    flows_wide() which delegates to collectors.sponsors.flows_table().
    Returns None if file absent or missing required columns.
    """
    p = (flows_dir or _FLOWS_DIR) / f"{ticker}.parquet"
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    if "so_mn" not in df.columns or "nav" not in df.columns:
        log.warning("etf_flows: %s missing required columns, skipping", ticker)
        return None
    return df.sort_index()


def _derive_flow(df: pd.DataFrame) -> pd.Series:
    """delta(so_mn) x nav(t) — creation/redemption proxy in $mn.

    This is the same formula used by collectors.sponsors.flows_table().
    Kept here so unit tests can exercise the math directly against synthetic
    DataFrames without requiring the full collectors stack.
    """
    return (df["so_mn"].diff() * df["nav"]).rename("flow_mn")


def flows_wide(tickers: tuple[str, ...] = SECTOR_TICKERS,
               _flows_dir: Path | None = None) -> pd.DataFrame | None:
    """Return wide frame: index=date, columns=<TICKER>_flow_mn. None if no data.

    **Delegates to collectors.sponsors.flows_table()** as the canonical
    delta(SO)×NAV computation so the two live consumers (sector-central board
    and P3.1 tile) share a single derive path and cannot drift.

    The ``_flows_dir`` parameter is accepted only to support unit tests that
    inject synthetic per-ticker parquets; it bypasses the sponsors path so that
    tests do not require the full collect stack.
    """
    if _flows_dir is not None:
        # Test-injection path: read synthetic files directly (no sponsors import)
        cols = {}
        for t in tickers:
            df = _load_so(t, flows_dir=_flows_dir)
            if df is None or len(df) < 2:
                continue
            s = _derive_flow(df)
            cols[f"{t}_flow_mn"] = s
        if not cols:
            return None
        wide = pd.DataFrame(cols)
        wide.index.name = "date"
        return wide.sort_index()

    # Production path: delegate to the canonical sponsors engine
    try:
        from collectors.sponsors import flows_table
    except ImportError:
        log.warning("etf_flows: collectors.sponsors unavailable; falling back to direct read")
        return _flows_wide_direct(tickers)

    ft = flows_table()
    if ft is None:
        return None
    # flows_table() already returns "<TICKER>_flow_mn" columns; filter to wanted set
    if tickers:
        wanted_cols = [f"{t}_flow_mn" for t in tickers]
        ft = ft[[c for c in wanted_cols if c in ft.columns]]
    ft.index.name = "date"
    return ft.sort_index() if not ft.empty else None


def _flows_wide_direct(tickers: tuple[str, ...]) -> pd.DataFrame | None:
    """Fallback: read raw parquets directly when sponsors is unavailable."""
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

    In production, flows_wide() delegates to collectors.sponsors.flows_table()
    (the canonical derive path shared with build_sector_central.py).  When
    flows_dir is supplied (test injection), flows_wide() reads synthetic files
    directly instead.

    Upserts: existing rows for dates not in the new frame are preserved; new
    dates overwrite (date dedup: latest write wins). Returns the output path on
    success, None if no data is available yet.
    """
    _fdir = flows_dir or _FLOWS_DIR
    _ppath = proxy_path or _PROXY_PATH

    wide = flows_wide(tickers, _flows_dir=flows_dir)
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
