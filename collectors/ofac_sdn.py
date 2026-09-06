"""collectors/ofac_sdn.py — fetch OFAC's public SDN / consolidated sanctions
list and persist a raw snapshot for engine.sanctions_map to read.

Public source only (US Treasury OFAC). Off the render path — invoked by the
nightly / closing-bell pipeline (or by hand), never by
scripts/build_sanctions_map.py, which only reads the store.
"""
from __future__ import annotations

import csv
import gzip
import io
import json
import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from collectors.base import Adapter

log = logging.getLogger(__name__)

OFAC_SDN_CSV_URL = "https://www.treasury.gov/ofac/downloads/sdn.csv"
STORE_DIR = Path("data/sanctions_ofac")
STORE_FILE = STORE_DIR / "sdn_snapshot.csv.gz"
META_FILE = STORE_DIR / "meta.json"


def fetch_sdn_csv(timeout: int = 30) -> tuple[str, str | None]:
    """Fetch the raw OFAC SDN CSV text plus an optional list-published date
    derived from the HTTP ``Last-Modified`` header. Raises on network failure
    — the caller decides whether to keep the last good snapshot."""
    import requests

    resp = requests.get(OFAC_SDN_CSV_URL, timeout=timeout)
    resp.raise_for_status()
    published: str | None = None
    last_mod = resp.headers.get("Last-Modified")
    if last_mod:
        try:
            published = parsedate_to_datetime(last_mod).date().isoformat()
        except (TypeError, ValueError, IndexError, OverflowError):
            published = None
    return resp.text, published


def persist_snapshot(csv_text: str, list_published_date: str | None = None) -> dict:
    """Write the raw CSV (gzip-compressed — the OFAC SDN list is ~5.5 MB of
    plaintext and this is a nightly-rewritten tracked artifact; gzip cuts it
    by roughly 85-90%) plus source_url / list_published_date / fetched_at
    metadata."""
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    STORE_FILE.write_bytes(gzip.compress(csv_text.encode("utf-8")))
    meta = {
        "source_url": OFAC_SDN_CSV_URL,
        "list_published_date": list_published_date,
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    META_FILE.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def extract_program_codes(csv_text: str) -> list[str]:
    """Programme codes from the SDN CSV's 'program' column (field 4,
    0-indexed 3, per OFAC's published SDN.CSV format; no header row).
    A single field may pack multiple codes as ``[A] [B]`` — each is
    emitted separately. Uses the shared splitter in engine.sanctions_map so
    whitespace variants cannot diverge."""
    from engine.sanctions_map import split_program_field

    codes: list[str] = []
    reader = csv.reader(io.StringIO(csv_text))
    for row in reader:
        if len(row) > 3 and row[3].strip():
            codes.extend(split_program_field(row[3]))
    return codes


def run() -> dict:
    """Nightly entry point. Never raises — a failed fetch leaves the last
    good snapshot in place and prints a GitHub annotation."""
    try:
        csv_text, published = fetch_sdn_csv()
    except Exception as exc:  # noqa: BLE001 - network/collector boundary
        print(f"::warning title=ofac_sdn_fetch_failed::{exc}", flush=True)
        return {"ok": False, "error": str(exc)}
    meta = persist_snapshot(csv_text, list_published_date=published)
    meta["ok"] = True
    meta["n_codes"] = len(extract_program_codes(csv_text))
    return meta


class OfacSdnAdapter(Adapter):
    """Nightly OFAC SDN snapshot for the Sanctions Map page. Keyless public
    CSV; writes ``data/sanctions_ofac/`` directly (not the parquet store), and
    returns a one-row meta frame so the collect runner records a healthy
    fetch with an advancing as-of date."""

    name = "ofac_sdn"
    group = "sanctions_ofac"
    stale_after_days = 3

    def fetch(self, full_history: bool = False) -> dict[str, "pd.DataFrame"]:
        import pandas as pd

        result = run()
        if not result.get("ok"):
            raise RuntimeError(result.get("error") or "ofac_sdn fetch failed")
        as_of = result.get("list_published_date") or result.get("fetched_at", "")[:10]
        idx = pd.DatetimeIndex([as_of], name="date")
        frame = pd.DataFrame(
            {"n_codes": [int(result.get("n_codes") or 0)],
             "source_url": [result.get("source_url") or OFAC_SDN_CSV_URL]},
            index=idx,
        )
        return {"sdn_meta": frame}


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
