"""SEC EDGAR full-text-search collector for Trump-family / administration filings.

The GENUINELY-EARLY channel. Quiver's trade feeds carry a 30-45d reporting lag and the
news feed follows the media narrative; an 8-K / S-4 / 425 / EX-99 hits EDGAR at FILING
TIME — which is when the ABTC -> Hut 8 chain was actually knowable, before the
'loves bitcoin' framing. This collector full-text-searches EDGAR for the curated
Trump-linked entity names and records every recent filing that mentions one, so the
TrumpFlow graph + page can surface "a new filing just named one of these entities".

Keyless (SEC only requires a descriptive User-Agent). Append-only, key-deduped by the
EDGAR file id (accession:filename) with a _first_seen latency stamp — exactly like the
Quiver collectors. data/trumpflow/edgar_filings.parquet.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)

_FTS = "https://efts.sec.gov/LATEST/search-index"
_TICKER_RE = re.compile(r"\(([A-Z][A-Z.\-]{0,6})\)")


class EdgarTrumpflowAdapter(Adapter):
    name = "edgar_trumpflow"
    group = "trumpflow"
    stale_after_days = 21          # filings are lumpy; absence of a new one is normal

    LOOKBACK_DAYS = 150
    # EDGAR FTS silently returns 0 for a multi-form `forms` filter that includes spaced
    # forms (e.g. 'SC 13D/A'), so we DON'T filter server-side — we pull all hits and keep
    # the deal-relevant forms client-side.
    RELEVANT_FORMS = {"8-K", "S-4", "425", "S-1", "S-1/A", "8-A12B", "SC 13D", "SC 13D/A",
                      "SC 13G", "SC 13G/A", "424B4", "424B5", "DEFM14A", "6-K", "F-1"}
    # Curated specific entity names (people names are too noisy in EDGAR FTS).
    QUERIES = [
        "American Bitcoin", "Hut 8", "World Liberty Financial",
        "Trump Media", "American Data Centers", "Dominari",
    ]

    def _table_path(self):
        p = config.data_dir() / self.group / "edgar_filings.parquet"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def _merge(self, new: pd.DataFrame) -> tuple[int, int]:
        new = new.copy()
        new["_first_seen"] = datetime.now(timezone.utc).isoformat()
        path = self._table_path()
        if path.exists():
            old = pd.read_parquet(path)
            before = len(old)
            combined = pd.concat([old, new], ignore_index=True)
        else:
            before = 0
            combined = new
        combined = combined.drop_duplicates(subset=["_id"], keep="first").reset_index(drop=True)
        combined.to_parquet(path)
        return len(combined) - before, len(combined)

    def _search(self, query: str, start: str, end: str) -> list:
        params = {"q": f'"{query}"', "startdt": start, "enddt": end}
        r = self.http_get(_FTS, retries=3, timeout=40,
                          headers={"User-Agent": config.load()["sponsors"]["user_agent"],
                                   "Accept": "application/json"},
                          params=params)
        data = r.json()
        return (data.get("hits", {}) or {}).get("hits", []) or []

    @staticmethod
    def _parse(hit: dict, query: str) -> dict | None:
        s = hit.get("_source", {}) or {}
        fid = hit.get("_id", "")
        if not fid:
            return None
        display = (s.get("display_names") or [""])[0]
        m = _TICKER_RE.search(display)
        cik = (s.get("ciks") or [None])[0]
        acc, _, fname = fid.partition(":")
        url = None
        if cik and acc and fname:
            url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{fname}"
        return {
            "_id": fid, "accession": s.get("adsh") or acc,
            "form": s.get("form"), "file_type": s.get("file_type"),
            "file_date": s.get("file_date"),
            "company": display.split("(")[0].strip() or None,
            "ticker": m.group(1) if m else None,
            "cik": str(cik) if cik else None,
            "items": ",".join(s.get("items", []) or []),
            "query": query, "url": url,
        }

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        today = datetime.now(timezone.utc).date()
        start = (today - timedelta(days=self.LOOKBACK_DAYS)).isoformat()
        end = today.isoformat()
        rows = []
        for q in self.QUERIES:
            try:
                for h in self._search(q, start, end):
                    row = self._parse(h, q)
                    if row and row.get("form") in self.RELEVANT_FORMS:
                        rows.append(row)
            except Exception as e:  # noqa: BLE001 — one bad query never kills the rest
                log.warning("edgar_trumpflow query %r failed: %s", q, e)
            time.sleep(0.4)        # be polite to EDGAR
        if not rows:
            raise RuntimeError("edgar_trumpflow: no filings returned")
        df = pd.DataFrame(rows)
        added, total = self._merge(df)
        log.info("edgar_trumpflow: +%d new (%d total) from %d hits", added, total, len(df))
        ingest = pd.DataFrame({"new_rows": [added], "total_rows": [total], "fetched": [len(df)]},
                              index=[pd.Timestamp(today)])
        return {"edgar_trumpflow__ingest": ingest}
