"""BTC macro-regime P5: Farside per-fund ETF flow reader — DISPLAY-ONLY context.

Optionally scrapes farside.co.uk/bitcoin-etf-flow-all-data for daily net flows
per fund (IBIT, FBTC, GBTC, ARKB, BITB, HODL, BRRR, EZBC, BTCO, DEFI, etc.),
appends to data/etf/perfund.parquet with a _first_seen timestamp, and computes
IBIT concentration share (IBIT flow / total absolute flow, a demand-quality
signal: IBIT dominance = institutional vs. GBTC = outflow-driven).

NOTE on mid-2025 in-kind creation rule change:
  The SEC approved in-kind creation/redemption for spot BTC ETFs around
  mid-2025. Before that date flows were cash-settled; after, primary-market
  flow mechanics changed so the same net-AUM change may show a different cash
  flow pattern.  Farside's raw $/day data is comparable across the break for
  display purposes, but any forward-return IC research must split the sample.

Feature-flagged: set btc_etf_perfund.scrape_enabled: true in config.yml to
activate network fetch (default OFF). The dashboard always calls read_perfund()
which reads the parquet if present and never touches the network.

Config keys (under btc_etf_perfund:):
  scrape_enabled: false   # master scrape switch (default OFF)
  url: "https://farside.co.uk/bitcoin-etf-flow-all-data"
  timeout_s: 30
  lookback_d: 5           # default rolling window for aggregates

Dependencies (stdlib + requests which is already in the repo):
  requests, html.parser (stdlib), lxml optional (falls back to html.parser).
  pandas + numpy already present.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from lib import config, store

log = logging.getLogger(__name__)

_PARQUET_GROUP = "etf"
_PARQUET_NAME = "perfund"

# Known fund tickers in the order Farside typically presents them
_KNOWN_FUNDS = [
    "IBIT", "FBTC", "BITB", "ARKB", "BTCO", "EZBC", "BRRR", "HODL",
    "DEFI", "GBTC",
]


def _f(v):
    try:
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# Pure reader — no network, no side effects
# --------------------------------------------------------------------------- #
def read_perfund(lookback_d: int | None = None) -> dict:
    """Read the persisted per-fund parquet and return a render-ready dict.

    Never touches the network. Returns {"ok": False, "reason": ...} when the
    parquet does not exist or is unreadable.

    Parameters
    ----------
    lookback_d:
        Rolling window for flow aggregates (defaults to config value, then 5).
    """
    try:
        cfg = config.load().get("btc_etf_perfund", {})
        lb = int(lookback_d or cfg.get("lookback_d", 5))

        df = store.read(_PARQUET_GROUP, _PARQUET_NAME)
        if df is None or df.empty:
            return {
                "ok": False,
                "reason": "data/etf/perfund.parquet not found; run scrape first",
            }

        # Drop metadata columns for the flow computation
        flow_cols = [c for c in df.columns if c not in ("_first_seen",)
                     and not c.startswith("_")]
        if not flow_cols:
            return {"ok": False, "reason": "no fund columns in perfund.parquet"}

        flow = df[flow_cols].copy()
        flow = flow.apply(pd.to_numeric, errors="coerce")
        latest = flow.iloc[-1]

        # Per-fund last-day flows (USD mn)
        per_fund = {
            k: (_f(v) if pd.notna(v) else None)
            for k, v in latest.items()
        }

        # Total flow and IBIT concentration share (rolling lb days)
        rolling = flow.iloc[-lb:]
        total_5d = _f(rolling.sum(skipna=True).sum())  # scalar total across all funds
        ibit_5d = _f(rolling["IBIT"].sum()) if "IBIT" in rolling.columns else None
        total_abs_5d = _f(rolling.abs().sum(skipna=True).sum())
        ibit_share = None
        if ibit_5d is not None and total_abs_5d and total_abs_5d > 0:
            ibit_share = round(ibit_5d / total_abs_5d, 3)

        asof = str(flow.index[-1].date())

        return {
            "ok": True,
            "display_only": True,
            "asof": asof,
            "ibit_share": ibit_share,
            "total_flow_5d": round(total_5d, 1) if total_5d is not None else None,
            "per_fund": per_fund,
            "note": (
                "Display-only. Per-fund ETF flows from Farside. "
                "IBIT share = IBIT flow / total-abs-flow over the lookback window. "
                "Mid-2025 in-kind creation change: flow mechanics shifted; "
                "use caution for cross-period IC studies."
            ),
        }
    except Exception as e:
        return {"ok": False, "reason": f"{type(e).__name__}: {e}"}


# --------------------------------------------------------------------------- #
# Scraper — feature-flagged, ALL network/parse in try/except
# --------------------------------------------------------------------------- #
def _parse_farside_html(html: str) -> pd.DataFrame:
    """Parse Farside ETF flow HTML into a date-indexed DataFrame.

    Farside uses a plain HTML table. Columns are fund names; rows are dates.
    Values are numeric (USD mn). Returns empty DataFrame on any parse failure.
    """
    try:
        tables = pd.read_html(html, flavor="lxml")
    except Exception:
        try:
            tables = pd.read_html(html)
        except Exception as e:
            log.warning("etf_perfund: HTML parse failed: %s", e)
            return pd.DataFrame()

    if not tables:
        return pd.DataFrame()

    # Pick the widest table (most fund columns)
    tbl = max(tables, key=lambda t: t.shape[1])
    if tbl.empty or tbl.shape[1] < 2:
        return pd.DataFrame()

    # Normalise: first column is the date
    tbl.columns = [str(c).strip() for c in tbl.columns]
    date_col = tbl.columns[0]
    tbl = tbl.rename(columns={date_col: "date"})
    tbl["date"] = pd.to_datetime(tbl["date"], errors="coerce")
    tbl = tbl.dropna(subset=["date"])
    if tbl.empty:
        return pd.DataFrame()

    tbl = tbl.set_index("date").sort_index()

    # Coerce fund columns to numeric (Farside sometimes has footnote text)
    fund_cols = [c for c in tbl.columns if c not in ("Total",)]
    for col in fund_cols:
        tbl[col] = pd.to_numeric(tbl[col].astype(str).str.replace(",", ""),
                                 errors="coerce")
    return tbl[fund_cols]


def scrape_and_append() -> dict:
    """Fetch Farside, parse, append to parquet. Returns a status dict.

    Wraps ALL network and parse logic in try/except — never raises.
    Returns {"ok": False, "reason": ...} on any failure.
    """
    try:
        cfg = config.load().get("btc_etf_perfund", {})
        if not cfg.get("scrape_enabled", False):
            return {
                "ok": False,
                "reason": "scrape disabled (btc_etf_perfund.scrape_enabled: false)",
            }

        url = cfg.get("url", "https://farside.co.uk/bitcoin-etf-flow-all-data")
        timeout = int(cfg.get("timeout_s", 30))

        import requests
        user_agent = config.load().get("sponsors", {}).get(
            "user_agent", "MacroDashboard/1.0 research"
        )
        resp = requests.get(url, timeout=timeout,
                            headers={"User-Agent": user_agent})
        if resp.status_code != 200:
            return {
                "ok": False,
                "reason": f"HTTP {resp.status_code} fetching {url}",
            }

        new_df = _parse_farside_html(resp.text)
        if new_df.empty:
            return {"ok": False, "reason": "HTML parse returned empty DataFrame"}

        # Append _first_seen
        now_str = datetime.now(timezone.utc).isoformat()
        new_df["_first_seen"] = now_str

        merged = store.upsert(_PARQUET_GROUP, _PARQUET_NAME, new_df,
                               normalize_index=True)
        rows_new = len(new_df)
        asof = str(merged.index.max().date())
        return {
            "ok": True,
            "rows_appended": rows_new,
            "asof": asof,
            "note": "Farside per-fund ETF flows scraped and appended",
        }
    except Exception as e:
        return {"ok": False, "reason": f"{type(e).__name__}: {e}"}
