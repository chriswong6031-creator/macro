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

**RLT-R3 addition: broad-market index ETF proxy**

``rebuild_broad()`` (RLT-R3) produces ``data/flows/broad_flow_proxy.parquet``
for the 5 broad-market index ETFs (SPY, QQQ, IWM, RSP, DIA).  Schema:

  index: (unnamed integer range)
  columns: date (datetime64[ns]), ticker (str), flow_mn (float64), flow_z60 (float64)

The long/tall format is chosen because consumers (RLT-R2 classifier, flow-
continuity cohort surface) iterate over tickers rather than reading wide
columns; it avoids the sparse-NaN pattern that arises in a wide frame when
tickers have different history lengths.

``flow_z60``: z-score of ``flow_mn`` versus its trailing 60-session window
(causal — uses only past data; minimum 2 observations required, else NaN).
The 60-session window matches the 3-month look-back used in the existing
flow-continuity cohort engine.

``SO jump guard``: single-day |delta(SO_mn)| > 25 % of the prior-day SO_mn is
clamped to NaN for ``flow_mn`` (labelled with a WARNING log).  This matches
the spirit of split-seam self-healing in other stores (breadth-cache-split-
seam-selfheal memory) and guards against corporate-action SO jumps from the
yfinance point-in-time feed.  The guard only fires on genuinely implausible
moves (> 25 % single-day change) — normal large creation events (a few % of
SO) pass through.

Authority block (all callers must respect):
  may_rank: false  |  may_gate: false  |  may_size: false

This module is DISPLAY-DATA only — it never feeds a score or allocation path.
Calling rebuild() / rebuild_broad() is idempotent; re-runs upsert (date wins
over existing row).
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

_FLOWS_DIR = Path(__file__).parent.parent / "data" / "flows"
_PROXY_PATH = _FLOWS_DIR / "etf_flow_proxy.parquet"
_BROAD_PROXY_PATH = _FLOWS_DIR / "broad_flow_proxy.parquet"

# RLT-R3: 5 broad-market index ETFs added alongside the 11 sector SPDRs.
# Their per-ticker SO parquets live in the same data/flows/ directory and use
# the same schema (nav, aum_mn, so_mn) written by BroadFlowAdapter.
SECTOR_TICKERS = ("XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY")
BROAD_ETFS = ("SPY", "QQQ", "IWM", "RSP", "DIA")

# Single-day SO jump guard threshold (RLT-R3): |delta(SO_mn)| / prior_so_mn.
# > 25% is almost certainly a data artifact (split, corporate action, or stale
# point-in-time yfinance snapshot) rather than real creation/redemption.
_SO_JUMP_GUARD_FRAC = 0.25


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


def _derive_flow_guarded(df: pd.DataFrame, ticker: str = "") -> pd.Series:
    """delta(so_mn) x nav(t) with SO-jump guard (RLT-R3).

    Entries where |delta(SO_mn)| / prior_so_mn > _SO_JUMP_GUARD_FRAC are
    clamped to NaN to suppress data-artifact spikes from splits or stale
    point-in-time SO snapshots.  The underlying SO series is NOT modified.
    """
    delta_so = df["so_mn"].diff()
    flow = (delta_so * df["nav"]).rename("flow_mn")
    # Guard: flag implausible single-day SO jumps
    prior_so = df["so_mn"].shift(1)
    jump_frac = delta_so.abs() / prior_so.abs().replace(0, pd.NA)
    mask = jump_frac > _SO_JUMP_GUARD_FRAC
    if mask.any():
        flagged = df.index[mask].tolist()
        log.warning(
            "etf_flows: %s SO jump >%d%% on %s — clamping flow_mn to NaN",
            ticker or "?", int(_SO_JUMP_GUARD_FRAC * 100), flagged,
        )
        flow = flow.where(~mask)
    return flow


def _z60_causal(s: pd.Series) -> pd.Series:
    """Rolling 60-session z-score of s, using only past observations (causal).

    min_periods=2 so the first non-NaN z is available as soon as we have a
    mean and std (avoids waiting for 60 full rows).  Returns NaN where std=0
    (flat series) or where history < 2 rows.
    """
    roll = s.rolling(window=60, min_periods=2)
    mu = roll.mean()
    sigma = roll.std(ddof=1)
    return ((s - mu) / sigma.replace(0, pd.NA)).rename("flow_z60")


def broad_flows_wide(tickers: tuple[str, ...] = BROAD_ETFS,
                     _flows_dir: Path | None = None) -> pd.DataFrame | None:
    """Return wide frame: index=date, columns=<TICKER>_flow_mn (guarded).

    The _flows_dir parameter is accepted for test injection (bypasses live
    data/flows/ directory).  Production callers rely on the default path.
    """
    fdir = _flows_dir or _FLOWS_DIR
    cols: dict[str, pd.Series] = {}
    for t in tickers:
        df = _load_so(t, flows_dir=fdir)
        if df is None or len(df) < 2:
            continue
        s = _derive_flow_guarded(df, ticker=t)
        cols[f"{t}_flow_mn"] = s
    if not cols:
        return None
    wide = pd.DataFrame(cols)
    wide.index.name = "date"
    return wide.sort_index()


def rebuild_broad(tickers: tuple[str, ...] = BROAD_ETFS,
                  flows_dir: Path | None = None,
                  proxy_path: Path | None = None) -> Path | None:
    """Rebuild broad_flow_proxy.parquet (RLT-R3).

    Output schema (long/tall):
      date      datetime64[ns]
      ticker    str
      flow_mn   float64   — delta(SO_mn) x NAV; NaN on day-0 or SO-jump rows
      flow_z60  float64   — causal 60-session z-score of flow_mn; NaN < 2 obs

    Authority block: may_rank=false, may_gate=false, may_size=false.
    Upserts existing store (last write wins on duplicate dates per ticker).
    Returns the output path on success, None if no data is available yet.
    """
    _fdir = flows_dir or _FLOWS_DIR
    _ppath = proxy_path or _BROAD_PROXY_PATH

    wide = broad_flows_wide(tickers, _flows_dir=_fdir)
    if wide is None:
        log.warning("etf_flows: no broad SO data found — skipping broad proxy build")
        return None

    # Melt wide → long and compute per-ticker causal z60
    records = []
    for col in wide.columns:
        ticker = col.replace("_flow_mn", "")
        s = wide[col].rename("flow_mn")
        z = _z60_causal(s)
        chunk = pd.DataFrame({"date": s.index, "ticker": ticker,
                               "flow_mn": s.values, "flow_z60": z.values})
        records.append(chunk)

    if not records:
        log.warning("etf_flows: broad_flows_wide returned empty — skipping")
        return None

    new_df = pd.concat(records, ignore_index=True)
    new_df["date"] = pd.to_datetime(new_df["date"])

    # Upsert: merge with existing store (last write wins on date+ticker)
    if _ppath.exists():
        existing = pd.read_parquet(_ppath)
        existing["date"] = pd.to_datetime(existing["date"])
        merged = pd.concat([existing, new_df], ignore_index=True)
        merged = (merged
                  .drop_duplicates(subset=["date", "ticker"], keep="last")
                  .sort_values(["ticker", "date"])
                  .reset_index(drop=True))
    else:
        merged = (new_df
                  .sort_values(["ticker", "date"])
                  .reset_index(drop=True))

    _ppath.parent.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(_ppath, index=False)
    log.info("etf_flows: wrote %s rows (%s tickers) -> %s",
             len(merged), merged["ticker"].nunique(), _ppath)
    return _ppath


def load_broad_proxy(proxy_path: Path | None = None) -> pd.DataFrame | None:
    """Load the persisted broad proxy store. Returns None if file absent."""
    p = proxy_path or _BROAD_PROXY_PATH
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
