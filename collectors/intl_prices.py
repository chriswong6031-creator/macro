"""International indices / vol / FX via yfinance — Plane A of the International
comparative dashboard (Japan / South Korea / Taiwan / UK / Eurozone).

Stores EOD adjusted close (+ volume) per ticker under group `intl`, exactly like
collectors/canada_prices.py. Universe = every country's primary + secondary equity
index, its (best-effort) volatility index, and its FX pair vs USD — all from
config["intl"]["countries"]. Coverage is gated only on the must-have CORE tickers
(each country's primary index + FX); secondary indices and vol indices are
best-effort (a missing Nikkei-VI / VSTOXX symbol must not fail the plane).

yfinance handles ^N225 / ^KS11 / ^TWII / ^FTSE / ^STOXX and the =X FX pairs cleanly.
Unofficial API, replaceable by design.
"""
from __future__ import annotations

import logging
import time

import pandas as pd
import yfinance as yf

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)


class IntlPriceAdapter(Adapter):
    name = "intl_prices"
    group = "intl"

    def __init__(self) -> None:
        self.cfg = config.load()["intl"]
        self.ycfg = self.cfg["yahoo"]
        self.countries = self.cfg["countries"]

    def _ticker_sets(self) -> tuple[list[str], list[str]]:
        """(core, optional). core = primary index + FX per country (gated);
        optional = secondary indices + vol indices (best-effort)."""
        core: list[str] = []
        optional: list[str] = []
        for c in self.countries.values():
            core.append(c["index"])
            core.append(c["fx"])
            for t in (c.get("indices") or {}):
                if t != c["index"]:
                    optional.append(t)
            if c.get("vol"):
                optional.append(c["vol"])
        core = list(dict.fromkeys(core))
        optional = [t for t in dict.fromkeys(optional) if t not in core]
        return core, optional

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        core, optional = self._ticker_sets()
        tickers = core + optional
        period = "max" if full_history else "1mo"
        frames: dict[str, pd.DataFrame] = {}
        bs = self.ycfg["batch_size"]
        for i in range(0, len(tickers), bs):
            batch = tickers[i:i + bs]
            df = self._download(batch, period)
            if df is None:
                continue
            for t in batch:
                try:
                    sub = df[t] if isinstance(df.columns, pd.MultiIndex) else df
                    sub = sub[["Close", "Volume"]].rename(
                        columns={"Close": "close", "Volume": "volume"}).dropna(subset=["close"])
                    if not sub.empty:
                        frames[t] = sub
                except KeyError:
                    log.warning("intl_prices: no data for %s", t)
        got_core = sum(1 for t in core if t in frames)
        if got_core < len(core) * 0.7:
            raise RuntimeError(f"intl_prices: core coverage too low {got_core}/{len(core)}")
        log.info("intl_prices: %d/%d tickers (core %d/%d)", len(frames), len(tickers),
                 got_core, len(core))
        return frames

    def _download(self, batch: list[str], period: str) -> pd.DataFrame | None:
        for attempt in range(self.ycfg["retries"]):
            try:
                df = yf.download(batch, period=period, auto_adjust=True,
                                 progress=False, group_by="ticker", threads=True)
                if df is None or df.empty:
                    raise RuntimeError("empty yfinance response")
                return df
            except Exception as e:  # noqa: BLE001 — degrade; gate enforces core coverage
                wait = self.ycfg["backoff_base_s"] * (2 ** attempt)
                log.warning("intl_prices batch failed (%s); retry in %.0fs", e, wait)
                time.sleep(wait)
        return None
