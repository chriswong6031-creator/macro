"""ETF holdings tracker for the active/thematic watchlist.

Daily snapshot per fund under data/holdings/<TICKER>/<YYYY-MM-DD>.parquet.
The engine diffs consecutive snapshots with flow normalization:

    expected_shares(t) = shares(t-1) * SO(t)/SO(t-1)
    active_decision(t) = actual_shares(t) - expected_shares(t)

which isolates manager decisions from creation/redemption pass-through.
N-PORT (EDGAR, ~60d lag) is a quarterly validation check only, never a live
signal. Per-sponsor fragility is documented in LIMITATIONS.md.
"""
from __future__ import annotations

import io
import logging
from datetime import date

import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)


class HoldingsAdapter(Adapter):
    name = "holdings"
    group = "holdings"

    def __init__(self) -> None:
        self.cfg = config.load()["holdings"]
        self.dir = config.ROOT / config.load()["storage"]["holdings_dir"]

    # holdings snapshots are written directly (one file per fund per day),
    # so fetch() returns {} and reports via raising on total failure.
    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        results, errors = {}, []
        for ticker, spec in self.cfg["watchlist"].items():
            try:
                snap = self._fetch_fund(ticker, spec)
                if snap is not None and not snap.empty:
                    self._write_snapshot(ticker, snap)
                    results[ticker] = len(snap)
            except Exception as e:  # noqa: BLE001 — one fund must not kill the rest
                errors.append(f"{ticker}: {e}")
                log.warning("holdings %s failed: %s", ticker, e)
        if not results:
            raise RuntimeError(f"all watchlist funds failed: {errors}")
        # return a tiny summary series so the runner records freshness
        s = pd.DataFrame({"funds_ok": [len(results)]},
                         index=[pd.Timestamp(date.today())])
        return {"holdings_runs": s}

    def _write_snapshot(self, ticker: str, snap: pd.DataFrame) -> None:
        d = self.dir / ticker
        d.mkdir(parents=True, exist_ok=True)
        snap_date = snap["as_of"].iloc[0] if "as_of" in snap.columns else str(date.today())
        snap.to_parquet(d / f"{snap_date}.parquet")

    def _fetch_fund(self, ticker: str, spec: dict) -> pd.DataFrame | None:
        sponsor = spec["sponsor"]
        fn = getattr(self, f"_fetch_{sponsor}", None)
        if fn is None:
            raise ValueError(f"no adapter for sponsor '{sponsor}'")
        return fn(ticker, spec)

    # --- sponsor adapters -------------------------------------------------------
    def _fetch_ark(self, ticker: str, spec: dict) -> pd.DataFrame:
        r = self.http_get(spec["url"], retries=self.cfg["retries"])
        df = pd.read_csv(io.StringIO(r.text))
        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
        df = df.dropna(subset=["ticker"]) if "ticker" in df.columns else df
        keep = [c for c in ["date", "fund", "company", "ticker", "cusip",
                            "shares", "market_value_($)", "market_value",
                            "weight_(%)", "weight"] if c in df.columns]
        df = df[keep].rename(columns={"market_value_($)": "market_value",
                                      "weight_(%)": "weight"})
        df["shares"] = pd.to_numeric(
            df["shares"].astype(str).str.replace(",", ""), errors="coerce")
        df["as_of"] = str(pd.to_datetime(df["date"].iloc[0]).date()) \
            if "date" in df.columns else str(date.today())
        return df

    def _fetch_coinshares(self, ticker: str, spec: dict) -> pd.DataFrame:
        # URL resolved by recon (see config holdings.watchlist.WGMI.url).
        url = spec.get("url", "")
        if not url:
            raise RuntimeError("WGMI holdings URL not configured yet")
        r = self.http_get(url, retries=self.cfg["retries"])
        df = pd.read_csv(io.StringIO(r.text))
        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
        share_col = next((c for c in df.columns if "share" in c or "quantity" in c), None)
        tick_col = next((c for c in df.columns if "ticker" in c or "symbol" in c), None)
        if not share_col or not tick_col:
            raise ValueError(f"unrecognized WGMI csv columns: {list(df.columns)}")
        df = df.rename(columns={share_col: "shares", tick_col: "ticker"})
        df["shares"] = pd.to_numeric(
            df["shares"].astype(str).str.replace(",", ""), errors="coerce")
        df["as_of"] = str(date.today())
        return df.dropna(subset=["shares"])


def active_changes(ticker: str, window_d: int | None = None) -> pd.DataFrame | None:
    """Flow-normalized manager decisions over the last N snapshots."""
    cfg = config.load()["holdings"]
    window_d = window_d or cfg["active_change_window_d"]
    d = config.ROOT / config.load()["storage"]["holdings_dir"] / ticker
    if not d.exists():
        return None
    snaps = sorted(d.glob("*.parquet"))[-(window_d + 1):]
    if len(snaps) < 2:
        return None
    first = pd.read_parquet(snaps[0]).set_index("ticker")["shares"]
    last = pd.read_parquet(snaps[-1]).set_index("ticker")["shares"]
    # fund-level SO ratio proxied by total share growth of common positions
    common = first.index.intersection(last.index)
    if common.empty:
        return None
    so_ratio = last[common].sum() / first[common].sum()
    expected = first * so_ratio
    diff = (last.reindex(expected.index) - expected).dropna()
    pct = 100 * diff / expected.replace(0, pd.NA)
    out = pd.DataFrame({"active_share_chg": diff, "active_chg_pct": pct})
    out["window_start"], out["window_end"] = snaps[0].stem, snaps[-1].stem
    return out.sort_values("active_chg_pct")
