"""Top-10 holdings per sector SPDR + their stock prices + light fundamentals.

- Holdings: SSGA's daily holdings XLSX per fund (public investor documents).
  Top 10 by weight, upserted into one history parquet per sector.
- Stock prices: yahoo batch for the union of all top-10 tickers (~80-100
  names), stored under data/stocks/ — full history on backfill (the cycle
  calibration needs it), incremental daily afterwards.
- Fundamentals: best-effort yfinance info fields, weekly cadence, LOW
  CONFIDENCE by design (unofficial API, sparse fields).
"""
from __future__ import annotations

import io
import logging
import time
from datetime import date

import pandas as pd

from collectors.base import Adapter
from lib import config, store

log = logging.getLogger(__name__)

SSGA_XLSX = ("https://www.ssga.com/us/en/intermediary/etfs/library-content/"
             "products/fund-data/etfs/us/holdings-daily-us-en-{fund}.xlsx")


class SectorHoldingsAdapter(Adapter):
    """Daily top-10 holdings snapshots for the 11 sector SPDRs."""

    name = "sector_holdings"
    group = "sector_holdings"

    def __init__(self) -> None:
        self.cfg = config.load()["sponsors"]

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        # 10 rows share one date, so these tables bypass the store's
        # one-row-per-date upsert and are merged here instead
        ok, errors = 0, []
        for fund in self.cfg["sector_funds"]:
            try:
                snap = self._fetch_fund(fund)
                self._merge_write(fund, snap)
                ok += 1
                time.sleep(0.5)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{fund}: {e}")
        if not ok:
            raise RuntimeError(f"all sector holdings failed: {errors}")
        if errors:
            log.warning("sector_holdings partial: %s", errors)
        s = pd.DataFrame({"funds_ok": [ok]}, index=[pd.Timestamp(date.today())])
        return {"holdings_runs": s}

    def _merge_write(self, fund: str, snap: pd.DataFrame) -> None:
        d = config.data_dir() / self.group
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{fund}.parquet"
        if p.exists():
            old = pd.read_parquet(p)
            old.index = pd.to_datetime(old.index)
            old = old[old.index != snap.index[0]]  # replace same-day snapshot
            snap = pd.concat([old, snap]).sort_index()
        snap.to_parquet(p)

    def _fetch_fund(self, fund: str) -> pd.DataFrame:
        r = self.http_get(SSGA_XLSX.format(fund=fund.lower()), retries=3, timeout=60,
                          headers={"User-Agent": "Mozilla/5.0 (research)"})
        raw = pd.read_excel(io.BytesIO(r.content), header=None)
        # find the header row ("Name", "Ticker", ...) and the as-of date above it
        hdr_idx = raw.index[raw.iloc[:, 0].astype(str).str.strip() == "Name"]
        if not len(hdr_idx):
            raise ValueError("holdings header row not found")
        asof = str(date.today())
        for i in range(hdr_idx[0]):
            cell = str(raw.iloc[i, 1])
            if "As of" in cell:
                asof = str(pd.to_datetime(cell.replace("As of", "").strip()).date())
        df = raw.iloc[hdr_idx[0] + 1:].copy()
        df.columns = [str(c).strip().lower().replace(" ", "_") for c in raw.iloc[hdr_idx[0]]]
        df = df.rename(columns={"weight": "weight_pct"})
        wcol = next((c for c in df.columns if "weight" in c), None)
        if wcol is None or "ticker" not in df.columns:
            raise ValueError(f"unexpected columns: {list(df.columns)[:6]}")
        df["weight_pct"] = pd.to_numeric(df[wcol], errors="coerce")
        df = (df.dropna(subset=["weight_pct", "ticker"])
                .query("ticker != '-'")
                .nlargest(10, "weight_pct"))
        out = pd.DataFrame({
            "ticker": df["ticker"].astype(str).str.strip(),
            "name": df["name"].astype(str).str.strip() if "name" in df.columns else "",
            "weight_pct": df["weight_pct"].round(2),
            "rank": range(1, len(df) + 1),
        })
        out.index = pd.to_datetime([asof] * len(out))
        return out

def top10_union() -> list[str]:
    """Union of current top-10 tickers across all sectors (for the price feed)."""
    d = config.data_dir() / "sector_holdings"
    if not d.exists():
        return []
    tickers: set[str] = set()
    for p in d.glob("*.parquet"):
        df = pd.read_parquet(p)
        if "ticker" not in df.columns or df.empty:
            continue
        df.index = pd.to_datetime(df.index)
        last_day = df.index.max()
        tickers |= set(df.loc[[last_day], "ticker"].astype(str))
    # yahoo notation: BRK.B -> BRK-B
    return sorted(t.replace(".", "-") for t in tickers if t and t != "nan")


def latest_top10(fund: str) -> pd.DataFrame | None:
    df = store.read("sector_holdings", fund)
    if df is None or df.empty:
        return None
    return df.loc[[df.index.max()]].sort_values("rank")


class StockPriceAdapter(Adapter):
    """Daily closes for the union of top-10 holdings (cycle engine fuel)."""

    name = "stock_prices"
    group = "stocks"

    def __init__(self) -> None:
        self.ycfg = config.load()["yahoo"]

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        import yfinance as yf
        tickers = top10_union()
        if not tickers:
            raise RuntimeError("no holdings stored yet — run sector_holdings first")
        period = "max" if full_history else "1mo"
        frames: dict[str, pd.DataFrame] = {}
        bs = self.ycfg["batch_size"]
        for i in range(0, len(tickers), bs):
            batch = tickers[i:i + bs]
            for attempt in range(self.ycfg["retries"]):
                try:
                    df = yf.download(batch, period=period, auto_adjust=True,
                                     progress=False, group_by="ticker", threads=True)
                    break
                except Exception as e:  # noqa: BLE001
                    if attempt == self.ycfg["retries"] - 1:
                        raise
                    time.sleep(self.ycfg["backoff_base_s"] * (2 ** attempt))
            for t in batch:
                try:
                    cols = [c for c in ["Close", "High", "Low", "Volume"] if c in df[t].columns]
                    sub = df[t][cols].rename(columns={"Close": "close", "High": "high",
                                                      "Low": "low", "Volume": "volume"})
                    sub = sub.dropna(subset=["close"])
                    if not sub.empty:
                        frames[t] = sub
                except KeyError:
                    log.warning("stocks: no data for %s", t)
        if len(frames) < len(tickers) * 0.7:
            raise RuntimeError(f"stocks: only {len(frames)}/{len(tickers)} returned")
        return frames


class StockFundamentalsAdapter(Adapter):
    """Best-effort valuation/quality snapshot per holding. Weekly cadence,
    LOW CONFIDENCE (unofficial yfinance fields, often missing)."""

    name = "stock_fundamentals"
    group = "stock_fundamentals"
    stale_after_days = 12

    FIELDS = {"forwardPE": "fwd_pe", "trailingPE": "pe",
              "profitMargins": "profit_margin", "revenueGrowth": "rev_growth",
              "returnOnEquity": "roe", "dividendYield": "div_yield",
              "marketCap": "mkt_cap"}

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        import yfinance as yf
        tickers = top10_union()
        if not tickers:
            raise RuntimeError("no holdings stored yet")
        rows = []
        today = pd.Timestamp(date.today())
        for t in tickers:
            rec: dict = {"ticker": t}
            try:
                info = yf.Ticker(t).info or {}
                for src, dst in self.FIELDS.items():
                    rec[dst] = info.get(src)
                time.sleep(0.2)
            except Exception as e:  # noqa: BLE001
                log.debug("fundamentals %s: %s", t, e)
            rows.append(rec)
        df = pd.DataFrame(rows).set_index("ticker")
        if df.drop(columns=["mkt_cap"], errors="ignore").notna().sum().sum() < len(tickers):
            log.warning("fundamentals very sparse this run")
        wide = df.unstack().to_frame().T
        wide.index = [today]
        wide.columns = [f"{t}__{f}" for f, t in wide.columns]
        return {"snapshots": wide}


def latest_fundamentals(ticker: str) -> dict:
    df = store.read("stock_fundamentals", "snapshots")
    if df is None or df.empty:
        return {}
    row = df.iloc[-1]
    out = {}
    for col, v in row.items():
        t, _, f = str(col).partition("__")
        if t == ticker and pd.notna(v):
            out[f] = v
    return out
