"""Quiver Quantitative alt-data collectors (Trader plan).

The repo's `store.upsert` is built for DATE-INDEXED numeric series (one row per
date). Quiver feeds are CROSS-SECTIONAL EVENT STREAMS — many rows per day (every
congress trade, every government contract, every insider Form-4). Routing those
through `validate()`/`upsert()` would normalize the index to a date and collapse a
whole day's events to a single row. So each adapter here:

  * writes its OWN append-only, key-deduped event table to
    `data/quiver/<dataset>.parquet`. Dedup is `keep="first"` => point-in-time
    integrity: the original values and a `_first_seen` timestamp survive forever;
    later corrections never overwrite the PIT record. `_first_seen` is the latency
    edge the reasoning brain cares about — "when did WE first observe this".
  * returns ONLY a tiny date-indexed ingest-log series (`<dataset>__ingest`) so the
    circuit-breaker runner still records status / rows / last_date in run_status.json.

Auth: Trader-plan token via `Authorization: Bearer <QUIVER_API_KEY>` against
`https://api.quiverquant.com/beta/live/<dataset>`. A missing key reports `blocked`,
never a hard failure (graceful degradation, like every other adapter).

Storage discipline note: these tables are EVENT logs, not time series — do not read
them with `lib.store.read` (which assumes a datetime index). The engine
(`engine/altdata.py`) reads them with plain `pd.read_parquet`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


class QuiverAdapter(Adapter):
    """Base for one Quiver dataset. Subclasses set the class attributes below."""

    group = "quiver"
    stale_after_days = 10  # most feeds report with a lag; some weekly/quarterly

    dataset: str = ""              # data/quiver/<dataset>.parquet + label
    endpoint: str = ""             # e.g. /beta/live/congresstrading
    key_cols: tuple[str, ...] = () # natural composite key for append-only dedup
    snapshot: bool = False         # feed carries no event-date -> stamp _collected
    data_key: str | None = None    # some endpoints wrap rows: {"data": [...]} etc.
    query: dict | None = None      # optional query params (page_size, latest, ...)

    def __init__(self) -> None:
        cfg = config.load().get("quiver", {})
        self.base_url = str(cfg.get("base_url", "https://api.quiverquant.com")).rstrip("/")
        self.timeout = int(cfg.get("timeout", 60))
        self.retries = int(cfg.get("retries", 3))
        self.api_key = config.secret("QUIVER_API_KEY")
        if not self.api_key:
            self.expected_failure = "QUIVER_API_KEY not set"

    # -- storage ---------------------------------------------------------------
    def _table_path(self):
        p = config.data_dir() / self.group / f"{self.dataset}.parquet"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def _merge(self, new: pd.DataFrame) -> tuple[int, int]:
        """Append-only, key-deduped merge. Returns (rows_added, total_rows)."""
        new = new.copy()
        new["_first_seen"] = datetime.now(timezone.utc).isoformat()
        if self.snapshot:
            new["_collected"] = _today()
        path = self._table_path()
        if path.exists():
            old = pd.read_parquet(path)
            before = len(old)
            combined = pd.concat([old, new], ignore_index=True)
        else:
            before = 0
            combined = new
        keys = [k for k in self.key_cols if k in combined.columns]
        # keep="first" preserves the original point-in-time record + _first_seen
        combined = combined.drop_duplicates(subset=keys or None, keep="first")
        combined = combined.reset_index(drop=True)
        combined.to_parquet(path)
        return len(combined) - before, len(combined)

    # -- fetch -----------------------------------------------------------------
    def _get(self, endpoint: str, params: dict | None = None) -> list:
        r = self.http_get(
            f"{self.base_url}{endpoint}",
            retries=self.retries,
            timeout=self.timeout,
            headers={"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"},
            params=params or {},
        )
        data = r.json()
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            if self.data_key and isinstance(data.get(self.data_key), list):
                return data[self.data_key]
            for k in ("data", "ownership", "results"):
                if isinstance(data.get(k), list):
                    return data[k]
        return []

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        if not self.api_key:
            raise RuntimeError("QUIVER_API_KEY not set")
        rows = self._get(self.endpoint, self.query)
        if not rows:
            raise RuntimeError(f"quiver/{self.dataset}: empty response from {self.endpoint}")
        df = pd.DataFrame(rows)
        added, total = self._merge(df)
        log.info("quiver/%s: +%d new (%d total) from %d fetched",
                 self.dataset, added, total, len(df))
        ingest = pd.DataFrame(
            {"new_rows": [added], "total_rows": [total], "fetched": [len(df)]},
            index=[pd.Timestamp(_today())],
        )
        return {f"{self.dataset}__ingest": ingest}


# ---------------------------------------------------------------------------
# Concrete datasets (Trader plan, confirmed live 2026-06-19)
# ---------------------------------------------------------------------------
class CongressAdapter(QuiverAdapter):
    name = "quiver_congress"; dataset = "congress"
    endpoint = "/beta/live/congresstrading"
    key_cols = ("BioGuideID", "Ticker", "TransactionDate", "Transaction", "Amount")


class SenateAdapter(QuiverAdapter):
    name = "quiver_senate"; dataset = "senate"
    endpoint = "/beta/live/senatetrading"
    key_cols = ("BioGuideID", "Ticker", "Date", "Transaction", "Amount")


class HouseAdapter(QuiverAdapter):
    name = "quiver_house"; dataset = "house"
    endpoint = "/beta/live/housetrading"
    key_cols = ("BioGuideID", "Ticker", "Date", "Transaction", "Amount", "Range")


class LobbyingAdapter(QuiverAdapter):
    name = "quiver_lobbying"; dataset = "lobbying"
    endpoint = "/beta/live/lobbying"
    key_cols = ("Date", "Client", "Registrant", "Ticker", "Amount")


class GovContractsAdapter(QuiverAdapter):
    name = "quiver_govcontracts"; dataset = "govcontracts"
    endpoint = "/beta/live/govcontractsall"
    key_cols = ("Ticker", "Date", "Agency", "Amount", "Description")


class OffExchangeAdapter(QuiverAdapter):
    name = "quiver_offexchange"; dataset = "offexchange"
    endpoint = "/beta/live/offexchange"
    key_cols = ("Ticker", "Date")


class InsidersAdapter(QuiverAdapter):
    name = "quiver_insiders"; dataset = "insiders"
    endpoint = "/beta/live/insiders"
    key_cols = ("Ticker", "Date", "Name", "TransactionCode", "Shares", "fileDate")


class FlightsAdapter(QuiverAdapter):
    name = "quiver_flights"; dataset = "flights"
    endpoint = "/beta/live/flights"
    stale_after_days = 60  # corporate-jet feed runs well behind real time
    key_cols = ("Ticker", "Date", "DepartureCity", "ArrivalCity")


class PatentsAdapter(QuiverAdapter):
    name = "quiver_patents"; dataset = "patents"
    endpoint = "/beta/live/allpatents"
    key_cols = ("Date", "Title", "IPC")


class WallStreetBetsAdapter(QuiverAdapter):
    name = "quiver_wsb"; dataset = "wallstreetbets"
    endpoint = "/beta/live/wallstreetbets"
    snapshot = True  # no event-date field -> _collected stamps the day
    key_cols = ("Ticker", "_collected")


class TwitterAdapter(QuiverAdapter):
    name = "quiver_twitter"; dataset = "twitter"
    endpoint = "/beta/live/twitter"
    key_cols = ("Ticker", "Date")


class Sec13FAdapter(QuiverAdapter):
    name = "quiver_sec13f"; dataset = "sec13f"
    endpoint = "/beta/live/sec13f"
    key_cols = ("Ticker", "Fund", "ReportPeriod", "Shares", "Value")


class Sec13FChangesAdapter(QuiverAdapter):
    name = "quiver_sec13f_changes"; dataset = "sec13f_changes"
    endpoint = "/beta/live/sec13fchanges"
    key_cols = ("Ticker", "Fund", "ReportPeriod", "Change_Share")


class CnbcAdapter(QuiverAdapter):
    name = "quiver_cnbc"; dataset = "cnbc"
    endpoint = "/beta/live/cnbc"
    key_cols = ("Ticker", "Date", "Traders", "Direction", "Upload_Time")


class SpacsAdapter(QuiverAdapter):
    name = "quiver_spacs"; dataset = "spacs"
    endpoint = "/beta/live/spacs"
    key_cols = ("Ticker", "Time")


class TrumpTradesAdapter(QuiverAdapter):
    """Donald Trump stock trades — bulk endpoint (no 'live' variant exists)."""
    name = "quiver_trump"; dataset = "trump"
    endpoint = "/beta/bulk/trumpstocktrades"
    key_cols = ("Company", "Ticker", "Transaction", "Amount", "Filed", "Traded")


class CorporateDonorsAdapter(QuiverAdapter):
    """Company-PAC donations to politicians (campaign-finance linkage)."""
    name = "quiver_corpdonors"; dataset = "corpdonors"
    endpoint = "/beta/bulk/corporatedonors"
    data_key = "data"
    query = {"page": 1, "page_size": 5000}
    key_cols = ("BioGuideID", "Ticker", "CompanyCMTEID", "Cycle", "TransactionAmount", "TransactionDate")


class QuiverNewsAdapter(QuiverAdapter):
    """Quiver news feed — ticker-tagged headlines + summaries (brain input)."""
    name = "quiver_news"; dataset = "news"
    endpoint = "/beta/live/quivernews"
    data_key = "data"
    query = {"page": 1, "page_size": 500}
    key_cols = ("url",)


class CongressHoldingsAdapter(QuiverAdapter):
    """Current aggregate congressional holdings per politician (snapshot)."""
    name = "quiver_congressholdings"; dataset = "congressholdings"
    endpoint = "/beta/live/congressholdings"
    snapshot = True
    key_cols = ("Politician", "_collected")


class BillSummariesAdapter(QuiverAdapter):
    """Recent legislation summaries (policy catalysts)."""
    name = "quiver_bills"; dataset = "bills"
    endpoint = "/beta/live/bill_summaries"
    query = {"page": 1, "page_size": 200}
    key_cols = ("billType", "number", "congress")


class AppRatingsAdapter(QuiverAdapter):
    """App-store ratings per ticker (consumer-demand proxy)."""
    name = "quiver_appratings"; dataset = "appratings"
    endpoint = "/beta/live/appratings"
    key_cols = ("Ticker", "App", "Time")
