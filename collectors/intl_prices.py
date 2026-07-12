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
from lib import config, store

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

    @staticmethod
    def _safe(t: str) -> str:
        """Match lib.store._path's filename sanitisation so config tickers can be
        compared against stored_series() stems (^N225 -> _N225, EURUSD=X -> EURUSD_X)."""
        return t.replace("^", "_").replace("=", "_").replace("/", "_").replace(" ", "_")

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        core, optional = self._ticker_sets()
        tickers = core + optional
        # Cold-start auto-seed: a fresh deploy (or any run where the `intl` store is
        # empty) must backfill DEEP history, not just the 1mo incremental window — the
        # regime engine needs trailing growth/inflation/momentum windows or every
        # country_record() comes back empty and build_intl skips the page. Once seeded,
        # store.upsert merges the daily 1mo window onto the archive. (intl_macro fetches
        # full FRED history every run, so only this price plane needs the cold check.)
        stored = set(self.stored_series())
        cold_start = not stored
        period = "max" if (full_history or cold_start) else "1mo"
        if cold_start and not full_history:
            log.info("intl_prices: cold store — seeding full history (period=max)")
        # New configured series (a market just added to config on an already-warm
        # store) must ALSO deep-seed — the 1mo incremental window is too shallow for
        # the regime engine, so a new market would otherwise never accumulate enough
        # history to build. Mirrors intl_universe's new-ticker handling.
        new = [] if (cold_start or full_history) else [t for t in tickers
                                                       if self._safe(t) not in stored]
        if new:
            log.info("intl_prices: %d new series — seeding full history: %s",
                     len(new), ",".join(new))

        frames: dict[str, pd.DataFrame] = {}
        rebase: list[str] = []
        self._collect(tickers, period, frames,
                      rebase=rebase if period == "1mo" else None)
        if new:                       # re-fetch the new series deep, overwriting the shallow window
            self._collect(new, "max", frames)
        if rebase:
            # Adjustment-basis guard heal: re-pull flagged names period='max' so the
            # whole store rebases in one upsert. A failed batch just leaves the names
            # out tonight (store untouched, re-flagged next run) — never spliced.
            log.info("intl_prices: %d name(s) on a re-adjusted basis — refetching "
                     "period='max': %s", len(rebase), rebase[:12])
            self._collect(rebase, "max", frames)
        got_core = sum(1 for t in core if t in frames)
        if got_core < len(core) * 0.7:
            raise RuntimeError(f"intl_prices: core coverage too low {got_core}/{len(core)}")
        log.info("intl_prices: %d/%d tickers (core %d/%d)", len(frames), len(tickers),
                 got_core, len(core))
        return frames

    def _collect(self, tickers: list[str], period: str,
                 frames: dict[str, pd.DataFrame],
                 rebase: list[str] | None = None) -> None:
        """Batch-download `tickers` for `period` and merge close/volume into frames.

        With a `rebase` list (the incremental 1mo pass only), a name whose window
        disagrees with stored closes on the overlap dates (store.basis_shifted —
        Yahoo re-adjusted the series after an ex-div/split since the last pull) is
        appended there and kept OUT of frames: splicing would strand every
        pre-window row on the stale basis. The caller re-pulls it period='max'."""
        tol = float(self.ycfg.get("upsert_basis_tol", 1e-3))
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
                    if sub.empty:
                        continue
                    if rebase is not None and store.basis_shifted(self.group, t, sub, tol=tol):
                        rebase.append(t)  # discard the window; the caller re-pulls period='max'
                        continue
                    frames[t] = sub
                except KeyError:
                    log.warning("intl_prices: no data for %s", t)

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
