"""Canada / TSX SEARCH universe — the broad name set behind the TSX Analyzer search
box (site/canadastockdata/) and the residual-alpha cross-section.

DECOUPLED from collectors/canada_breadth.py on purpose. canada_breadth is the curated
~74-name large-cap BREADTH/calibration gauge and must stay stable (the regime engine is
tuned on it). This collector imports the FULL S&P/TSX Composite so "not every TSX name can
be searched" stops being true — and so the sector-neutral residual-alpha cross-section has
the ~200+ names it wants — WITHOUT perturbing the calibrated engine. Mirrors the US design
(breadth = S&P 500; search = the broader caches) and collectors/china_universe.py.

Data planes (both free / keyless, verified 2026-06-15):
  * Universe + proper company names + GICS sector + index weight : the iShares XIC ETF
      holdings CSV (XIC tracks the S&P/TSX Capped Composite). One request — gives ticker +
      name + sector + weight, so NO yfinance get_info enrichment loop is needed.
  * Close history (5y, for the cycle/ladder + residual-alpha engine) : yfinance (.TO), batched.

Outputs (committed — small; gives the engine CI job the data via git pull, no fragile
cross-job actions/cache):
  data/canada_search/closes.parquet   wide [date x ticker] adjusted closes
  data/canada_search/members.parquet  index=ticker; name / sector / weight
  data/canada_search/coverage.parquet 1-row daily series (n_stocks) for run_status

build_canada_library reads these FIRST (broad names win over the breadth cache).
"""
from __future__ import annotations

import io
import logging
import re
import time

import pandas as pd
import yfinance as yf

from collectors.base import Adapter
from collectors.breadth import repair_seams
from lib import config

log = logging.getLogger(__name__)

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def _to_ticker(raw: str) -> str | None:
    """iShares TSX ticker -> yfinance symbol. RY -> RY.TO ; GIB.A -> GIB-A.TO ;
    RCI.B -> RCI-B.TO ; REI.UN -> REI-UN.TO. Cash/derivative rows -> None."""
    t = (raw or "").strip().upper()
    if not t or t in ("CAD", "--", "-", "USD", "NAN", "NONE"):   # cash / blank rows
        return None
    if not re.match(r"^[A-Z0-9]+(\.[A-Z]+)?$", t):   # skip futures/options/weird symbols
        return None
    return t.replace(".", "-") + ".TO"


class CanadaUniverseAdapter(Adapter):
    name = "canada_universe"
    group = "canada_search"
    stale_after_days = 7

    def __init__(self) -> None:
        cn = config.load()["canada"]
        self.cfg = cn["search_universe"]
        self.ycfg = cn["yahoo"]                 # batch_size / retries / backoff_base_s
        self.dir = config.data_dir() / "canada_search"
        self.closes_path = self.dir / "closes.parquet"
        self.members_path = self.dir / "members.parquet"

    # -- universe (iShares XIC holdings CSV) -----------------------------------
    def _ishares_holdings(self) -> pd.DataFrame:
        """Top-N Composite names by index weight: DataFrame[ticker, name, sector, weight]."""
        ish = self.cfg["ishares"]
        r = self.http_get(ish["url"], params=ish.get("params"), retries=self.ycfg["retries"],
                          backoff_base=self.ycfg["backoff_base_s"], timeout=40,
                          headers={"User-Agent": _UA})
        lines = r.text.splitlines()
        hdr = next((i for i, ln in enumerate(lines)
                    if ln.split(",")[0].strip().strip('"') == "Ticker"), None)
        if hdr is None:
            raise ValueError("XIC holdings: no 'Ticker' header row found")
        df = pd.read_csv(io.StringIO("\n".join(lines[hdr:])), thousands=",")

        def col(sub: str) -> str | None:
            return next((c for c in df.columns if sub in c.lower()), None)
        tcol, ncol, scol = col("ticker"), col("name"), col("sector")
        acol, wcol = col("asset class"), col("weight")
        if not all((tcol, ncol, wcol)):
            raise ValueError(f"XIC holdings: unexpected columns {list(df.columns)}")
        if acol is not None:
            df = df[df[acol].astype(str).str.strip().str.lower() == "equity"]
        df["_w"] = pd.to_numeric(df[wcol], errors="coerce")
        rows = []
        for _, x in df.iterrows():
            t = _to_ticker(str(x[tcol]))
            w = x["_w"]
            if t is None or pd.isna(w) or w <= 0:
                continue
            rows.append({"ticker": t, "name": str(x[ncol]).strip().title(),
                         "sector": (str(x[scol]).strip() if scol else "—") or "—",
                         "weight": round(float(w), 4)})
        out = (pd.DataFrame(rows).drop_duplicates(subset="ticker")
               .sort_values("weight", ascending=False).head(int(self.cfg.get("size", 250))))
        if len(out) < 100:
            raise RuntimeError(f"XIC universe too small: {len(out)} rows (expected ~225)")
        log.info("canada_universe: iShares XIC returned %d weighted Composite names", len(out))
        return out.set_index("ticker")

    # -- closes (yfinance) -----------------------------------------------------
    def _download_closes(self, tickers: list[str], period: str) -> pd.DataFrame:
        bs = int(self.ycfg["batch_size"])
        parts: list[pd.DataFrame] = []
        for i in range(0, len(tickers), bs):
            batch = tickers[i:i + bs]
            for attempt in range(self.ycfg["retries"]):
                try:
                    df = yf.download(batch, period=period, auto_adjust=True,
                                     progress=False, group_by="column", threads=True)
                    if df is None or df.empty:
                        break
                    closes = df["Close"] if "Close" in df.columns.get_level_values(0) else df
                    parts.append(closes)
                    break
                except Exception as e:  # noqa: BLE001
                    wait = self.ycfg["backoff_base_s"] * (2 ** attempt)
                    log.warning("canada_universe closes batch %d failed (%s); retry in %.0fs",
                                i // bs, e, wait)
                    time.sleep(wait)
            time.sleep(1)
        if not parts:
            raise RuntimeError("canada_universe: no closes downloaded")
        wide = pd.concat(parts, axis=1)
        return wide.loc[:, ~wide.columns.duplicated()].sort_index()

    def _merge_refreshed(self, fresh: pd.DataFrame, prev: pd.DataFrame) -> pd.DataFrame:
        """``fresh.combine_first(prev)`` + split-seam repair (2026-07-10 KLAC class).

        yfinance auto_adjust back-adjusts only the freshly downloaded window, so
        after a split the combine_first tail refresh leaves prev rows BEFORE the
        fresh window on the pre-split basis — a permanent fake ±N00% day at the
        seam. Flagged tickers are re-pulled over the full window and replaced
        wholesale; never fatal (see collectors.breadth.repair_seams)."""
        merged = fresh.combine_first(prev)
        merged, _ = repair_seams(merged, fresh, prev, self._download_closes,
                                 name=self.name)
        return merged

    # -- main ------------------------------------------------------------------
    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        if not self.cfg.get("enabled", True):
            raise RuntimeError("canada_universe disabled in config")
        self.dir.mkdir(parents=True, exist_ok=True)

        uni = self._ishares_holdings()
        tickers = uni.index.tolist()
        period = self.cfg.get("history_period", "5y")

        prev_closes = pd.read_parquet(self.closes_path) if self.closes_path.exists() else None
        if full_history:
            closes = self._download_closes(tickers, "max")
        elif prev_closes is not None and not prev_closes.empty:
            age = (pd.Timestamp.utcnow().tz_localize(None) - prev_closes.index.max()).days
            new = [t for t in tickers if t not in prev_closes.columns]
            fresh = self._download_closes(tickers, "1mo" if age <= 21 else period)
            closes = self._merge_refreshed(fresh, prev_closes)
            if new:                                       # backfill deep history for new entrants
                closes = self._download_closes(new, period).combine_first(closes)
        else:
            closes = self._download_closes(tickers, period)
        closes = closes[[t for t in tickers if t in closes.columns]].dropna(axis=1, how="all")

        live = closes.shape[1]
        log.info("canada_universe coverage: %d/%d names have closes (%.0f%%)",
                 live, len(tickers), 100 * live / max(1, len(tickers)))
        if live < len(tickers) * float(self.cfg.get("min_coverage", 0.6)):
            raise RuntimeError(f"canada_universe closes too sparse: {live}/{len(tickers)}")

        members = uni.loc[[t for t in uni.index if t in closes.columns]]
        if not full_history:
            closes.to_parquet(self.closes_path)
        members[["name", "sector", "weight"]].to_parquet(self.members_path)

        cov = pd.DataFrame({"n_stocks": [len(members)]},
                           index=pd.DatetimeIndex([closes.index.max()], name="date"))
        return {"coverage": cov}
