"""China A-share prices via yfinance — Plane A of the China dashboard.

Stores EOD adjusted close (+ volume) per ticker under data/china/, exactly like
collectors/yahoo.py does for the US universe (the US data/yahoo/ namespace is left
untouched). Universe = headline indices + the mainland sector-ETF complex + FX,
all from config["china"]["yahoo"]. The curated constituent stocks are pulled
separately by collectors/china_breadth.py (they power breadth + the search library).

yfinance handles .SS/.SZ symbols cleanly (verified 2026-06-12: Shanghai Composite
000001.SS -> 1997, sector ETFs ~2019-21->). Unofficial API, replaceable by design.
"""
from __future__ import annotations

import logging
import time

import pandas as pd
import yfinance as yf

from collectors.base import Adapter
from lib import config, store

log = logging.getLogger(__name__)


class ChinaPriceAdapter(Adapter):
    name = "china_prices"
    group = "china"

    def __init__(self) -> None:
        self.cfg = config.load()["china"]["yahoo"]

    def all_tickers(self) -> list[str]:
        out: list[str] = list(self.cfg["indices"].keys())
        out += list(self.cfg["sector_etfs"].keys())
        out += list(self.cfg.get("allocation_etfs", {}).keys())
        out += list(self.cfg["fx"].keys())
        return list(dict.fromkeys(out))

    def _fetch_plan(self, tickers: list[str], full_history: bool) -> dict[str, list[str]]:
        """Map yfinance period -> tickers. On an incremental run a NEWLY-ADDED ticker
        (no parquet, or a shallow one — e.g. a fresh allocation_etf that has only ever
        seen the 1-month window) is pulled with period='max' so it is BACKFILLED from
        inception; everything already deep on disk takes the cheap 1-month window.
        store.upsert dedups by date, so re-pulling 'max' over a shallow series just
        completes the history (no duplication)."""
        if full_history:
            return {"max": tickers}
        deep, shallow = [], []
        for t in tickers:
            df = store.read(self.group, t)
            (deep if (df is not None and len(df) >= 250) else shallow).append(t)
        return {"1mo": deep, "max": shallow}

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        tickers = self.all_tickers()
        frames: dict[str, pd.DataFrame] = {}
        rebase: list[str] = []
        tol = float(self.cfg.get("upsert_basis_tol", 1e-3))
        bs = self.cfg["batch_size"]
        for period, tks in self._fetch_plan(tickers, full_history).items():
            for i in range(0, len(tks), bs):
                batch = tks[i:i + bs]
                if not batch:
                    continue
                df = self._download(batch, period)
                for t in batch:
                    sub = self._extract(df, t)
                    if sub is None:
                        continue
                    # Adjustment-basis guard (store.basis_shifted, same contract as
                    # collectors/yahoo.py): a 1mo window that disagrees with stored
                    # closes on the overlap dates was re-adjusted by Yahoo (ex-div/
                    # split) since the last pull — splicing would strand every
                    # pre-window row on the stale basis.
                    if period == "1mo" and store.basis_shifted(self.group, t, sub, tol=tol):
                        rebase.append(t)  # discard the window; re-pull full history below
                        continue
                    frames[t] = sub
        self._refetch_rebased(rebase, frames)
        if len(frames) < len(tickers) * 0.7:
            raise RuntimeError(f"china_prices returned only {len(frames)}/{len(tickers)} tickers")
        return frames

    def _extract(self, df: pd.DataFrame, t: str) -> pd.DataFrame | None:
        try:
            sub = df[t] if isinstance(df.columns, pd.MultiIndex) else df
            sub = sub[["Close", "Volume"]].rename(
                columns={"Close": "close", "Volume": "volume"}).dropna(subset=["close"])
            return sub if not sub.empty else None
        except KeyError:
            log.warning("china_prices: no data for %s", t)
            return None

    def _refetch_rebased(self, rebase: list[str], frames: dict[str, pd.DataFrame]) -> None:
        """Re-pull basis-shifted names period='max' so the whole store rebases in one
        upsert. A name whose re-pull fails is DROPPED from this run — never spliced —
        leaving the store untouched so the guard re-flags it the next night."""
        if not rebase:
            return
        log.info("china_prices: %d name(s) on a re-adjusted basis — refetching "
                 "period='max': %s", len(rebase), rebase[:12])
        bs = self.cfg["batch_size"]
        for i in range(0, len(rebase), bs):
            batch = rebase[i:i + bs]
            try:
                df = self._download(batch, "max")
            except Exception as e:  # noqa: BLE001 — skip tonight; the guard re-flags next run
                log.warning("china_prices: basis refetch failed for %d name(s) (%s) — "
                            "kept out of this run", len(batch), e)
                continue
            for t in batch:
                sub = self._extract(df, t)
                if sub is not None:
                    frames[t] = sub

    def _download(self, batch: list[str], period: str) -> pd.DataFrame:
        last_exc: Exception | None = None
        for attempt in range(self.cfg["retries"]):
            try:
                df = yf.download(batch, period=period, auto_adjust=True,
                                 progress=False, group_by="ticker", threads=True)
                if df is None or df.empty:
                    raise RuntimeError("empty yfinance response")
                return df
            except Exception as e:  # noqa: BLE001
                last_exc = e
                wait = self.cfg["backoff_base_s"] * (2 ** attempt)
                log.warning("china_prices batch failed (%s); retry in %.0fs", e, wait)
                time.sleep(wait)
        raise last_exc  # type: ignore[misc]
