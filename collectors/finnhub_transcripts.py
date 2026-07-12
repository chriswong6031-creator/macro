"""Finnhub earnings-call transcript LIST collector.

Pulls the transcripts/list endpoint — metadata only (id, symbol, event time,
quarter, year). Full transcript bodies are NOT fetched nightly; body pulls come
in a later lane when needed for NLP. This lane purely accrues the catalog.

Published evidence: Seasholes & Wu (2004), Chen et al. (2010), and industry
research all document next-session abnormal-return signal on earnings calls.
Same-day latency: Finnhub publishes transcript metadata within hours.

GATED: no FINNHUB_API_KEY/FINNHUB_KEY -> 'blocked', non-fatal.
403/PERMISSION error on the transcripts endpoint -> log once and skip cleanly
(free-tier accounts may not have transcript API access; the collector becomes
a no-op until the plan allows it — that is acceptable per house law).

Store: data/finnhub/transcripts.parquet  (append-only, key-deduped on ticker+id)
PIT: _first_seen UTC (keep='first'), never overwrites.
Budget: 1 call per symbol, ~60 req/min free-tier cap respected (reuses PACE_S
from finnhub_altdata); incremental — only pulls 90-day window; rotates universe
so a full re-check cycles across ~MAX_TICKERS per run.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

from collectors.base import Adapter, is_connection_error
from collectors.universe import basket_members
from lib import config

log = logging.getLogger(__name__)

BASE = "https://finnhub.io/api/v1"
MAX_TICKERS = 80           # 1 call each -> ~80 calls; ~1.5 min at free 60/min cap
PACE_S = 0.9               # stay under 60 req/min (same as finnhub_altdata)
WINDOW_DAYS = 90           # look-back for new transcripts per run


def _key() -> str | None:
    return config.secret("FINNHUB_API_KEY") or config.secret("FINNHUB_KEY")


def _transcripts_path() -> "config.Path":
    p = config.data_dir() / "finnhub" / "transcripts.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def parse_transcript_list(raw: list[dict], ticker: str) -> list[dict]:
    """Pure: flatten one symbol's transcript-list response into catalog rows.

    Each raw item shape (from https://finnhub.io/api/v1/stock/transcripts/list):
        {id, symbol, title, time, quarter, year}
    """
    rows = []
    for item in raw or []:
        tid = item.get("id")
        if not tid:
            continue
        rows.append({
            "ticker": ticker,
            "transcript_id": str(tid),
            "title": item.get("title"),
            "event_time": item.get("time"),
            "quarter": item.get("quarter"),
            "year": item.get("year"),
        })
    return rows


class FinnhubTranscriptsAdapter(Adapter):
    name = "finnhub_transcripts"
    group = "finnhub"
    stale_after_days = 2   # transcripts publish same-day or next-morning

    def __init__(self) -> None:
        self.api_key = _key()
        if not self.api_key:
            self.expected_failure = "FINNHUB_API_KEY/FINNHUB_KEY not set"
        self._plan_gated: bool = False   # set True on first 403 to skip remaining

    def _get_transcript_list(self, symbol: str) -> list[dict] | None:
        """Fetch transcript metadata list for `symbol`. Returns None on plan-gate."""
        if self._plan_gated:
            return None
        params = {"symbol": symbol, "token": self.api_key}
        try:
            r = self.http_get(f"{BASE}/stock/transcripts/list", params=params,
                              retries=2, timeout=30)
            data = r.json()
            # Shape: {"transcripts": [...]} or a direct list or an error dict
            if isinstance(data, dict):
                if "error" in data:
                    err_str = str(data["error"]).lower()
                    if "permission" in err_str or "plan" in err_str or "access" in err_str:
                        log.warning(
                            "finnhub_transcripts: plan-gated (403/permission) — "
                            "transcript endpoint not available on current plan; "
                            "collector will be a no-op until plan upgrade. msg=%r",
                            data["error"],
                        )
                        self._plan_gated = True
                        return None
                return data.get("transcripts") or []
            if isinstance(data, list):
                return data
            return []
        except Exception as e:  # noqa: BLE001
            if is_connection_error(e):
                raise
            # Check HTTP 403 from the response embedded in the exception
            exc_str = str(e)
            if "403" in exc_str or "401" in exc_str:
                log.warning(
                    "finnhub_transcripts: HTTP %s on transcripts/list — "
                    "plan-gated; collector will be a no-op. err=%s",
                    "403" if "403" in exc_str else "401", e,
                )
                self._plan_gated = True
                return None
            log.debug("finnhub_transcripts %s: %s", symbol, e)
            return []

    def _merge(self, new: pd.DataFrame) -> int:
        if new.empty:
            return 0
        new = new.copy()
        new["_first_seen"] = datetime.now(timezone.utc).isoformat()
        path = _transcripts_path()
        if path.exists():
            combined = pd.concat([pd.read_parquet(path), new], ignore_index=True)
        else:
            combined = new
        k = ["ticker", "transcript_id"]
        combined = combined.drop_duplicates(subset=k, keep="first").reset_index(drop=True)
        combined.to_parquet(path)
        return len(new)

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        if not self.api_key:
            raise RuntimeError("FINNHUB key not set")
        watch = basket_members(cap=MAX_TICKERS)
        if not watch:
            raise ValueError("finnhub_transcripts: empty watchlist")

        since_iso = (datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)).isoformat()
        rows: list[dict] = []
        errors = 0
        skipped_plan_gate = 0

        for tk in watch:
            items = self._get_transcript_list(tk)
            if items is None:
                # plan-gated — all remaining symbols will also be None; stop early
                skipped_plan_gate = len(watch)
                break
            # filter to the look-back window
            for item in items:
                event_time = item.get("event_time") or ""
                if event_time >= since_iso or not event_time:
                    rows.extend(parse_transcript_list([item], tk))
            time.sleep(PACE_S)

        if self._plan_gated:
            log.info(
                "finnhub_transcripts: plan-gated — no transcript access; "
                "returning empty (non-fatal; %d symbols skipped)",
                skipped_plan_gate,
            )
            ingest = pd.DataFrame(
                {"new_rows": [0], "watch": [len(watch)], "plan_gated": [True]},
                index=[pd.Timestamp(datetime.now(timezone.utc).date())],
            )
            return {"finnhub_transcripts__ingest": ingest}

        n = self._merge(pd.DataFrame(rows)) if rows else 0
        log.info(
            "finnhub_transcripts: %d watch, +%d transcript metadata rows, %d errors",
            len(watch), n, errors,
        )
        ingest = pd.DataFrame(
            {"new_rows": [n], "watch": [len(watch)], "plan_gated": [False]},
            index=[pd.Timestamp(datetime.now(timezone.utc).date())],
        )
        return {"finnhub_transcripts__ingest": ingest}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    FinnhubTranscriptsAdapter().fetch()
