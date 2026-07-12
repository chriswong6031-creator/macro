"""Hong Kong prices via yfinance — Plane A of the HK / Hang Seng dashboard.

Stores EOD adjusted close (+ volume) per ticker under data/hk/, exactly like
collectors/china_prices.py does for the Mainland (the data/yahoo/ and data/china/
namespaces are left untouched). Universe = Hang Seng indices + HS-TECH/HSI ETF
proxies + USD/HKD (peg distance) + EEM (the one global-risk factor not already in
the store). The curated constituent stocks are pulled separately by
collectors/hk_breadth.py (they power breadth + the synthetic sector baskets + the
search library).

yfinance handles .HK symbols and ^HSI/^HSCE/^HSCC cleanly (verified 2026-06-13:
^HSI -> 1986, constituents -> 2000-2006). ^HSTECH is NOT on Yahoo, so the CSOP
HS TECH ETF (3033.HK, 2020->) stands in for the tech-growth tilt. Unofficial API,
replaceable by design. See research/HK_DATA_AUDIT.md.
"""
from __future__ import annotations

import logging
import time

import pandas as pd
import yfinance as yf

from collectors.base import Adapter
from lib import config, store

log = logging.getLogger(__name__)


class HkPriceAdapter(Adapter):
    name = "hk_prices"
    group = "hk"

    def __init__(self) -> None:
        self.cfg = config.load()["hk"]["yahoo"]

    def all_tickers(self) -> list[str]:
        out: list[str] = list(self.cfg["indices"].keys())
        out += list(self.cfg.get("etf_proxies", {}).keys())
        out += list(self.cfg.get("fx", {}).keys())
        out += list(self.cfg.get("extras", {}).keys())
        return list(dict.fromkeys(out))

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        tickers = self.all_tickers()
        period = "max" if full_history else "1mo"
        frames: dict[str, pd.DataFrame] = {}
        rebase: list[str] = []
        tol = float(self.cfg.get("upsert_basis_tol", 1e-3))
        bs = self.cfg["batch_size"]
        for i in range(0, len(tickers), bs):
            batch = tickers[i:i + bs]
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
            raise RuntimeError(f"hk_prices returned only {len(frames)}/{len(tickers)} tickers")
        return frames

    def _extract(self, df: pd.DataFrame, t: str) -> pd.DataFrame | None:
        try:
            sub = df[t] if isinstance(df.columns, pd.MultiIndex) else df
            sub = sub[["Close", "Volume"]].rename(
                columns={"Close": "close", "Volume": "volume"}).dropna(subset=["close"])
            return sub if not sub.empty else None
        except KeyError:
            log.warning("hk_prices: no data for %s", t)
            return None

    def _refetch_rebased(self, rebase: list[str], frames: dict[str, pd.DataFrame]) -> None:
        """Re-pull basis-shifted names period='max' so the whole store rebases in one
        upsert. A name whose re-pull fails is DROPPED from this run — never spliced —
        leaving the store untouched so the guard re-flags it the next night."""
        if not rebase:
            return
        log.info("hk_prices: %d name(s) on a re-adjusted basis — refetching "
                 "period='max': %s", len(rebase), rebase[:12])
        bs = self.cfg["batch_size"]
        for i in range(0, len(rebase), bs):
            batch = rebase[i:i + bs]
            try:
                df = self._download(batch, "max")
            except Exception as e:  # noqa: BLE001 — skip tonight; the guard re-flags next run
                log.warning("hk_prices: basis refetch failed for %d name(s) (%s) — "
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
                log.warning("hk_prices batch failed (%s); retry in %.0fs", e, wait)
                time.sleep(wait)
        raise last_exc  # type: ignore[misc]
