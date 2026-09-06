"""collectors/ofac_sdn.py — fetch OFAC's public SDN / consolidated sanctions
list and persist a raw snapshot for engine.sanctions_map to read.

Public source only (US Treasury OFAC). Off the render path — invoked by the
nightly pipeline (or by hand), never by scripts/build_sanctions_map.py, which
only reads the store.
"""
from __future__ import annotations

import csv
import io
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

OFAC_SDN_CSV_URL = "https://www.treasury.gov/ofac/downloads/sdn.csv"
STORE_DIR = Path("data/sanctions_ofac")
STORE_FILE = STORE_DIR / "sdn_snapshot.csv"
META_FILE = STORE_DIR / "meta.json"


def fetch_sdn_csv(timeout: int = 30) -> str:
    """Fetch the raw OFAC SDN CSV text. Raises on network failure — the
    caller decides whether to keep the last good snapshot."""
    import requests

    resp = requests.get(OFAC_SDN_CSV_URL, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def persist_snapshot(csv_text: str, list_published_date: str | None = None) -> dict:
    """Write the raw CSV plus source_url / list_published_date / fetched_at
    metadata."""
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    STORE_FILE.write_text(csv_text, encoding="utf-8")
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
    emitted separately. (Verified against a live fetch 2026-09-05 —
    column 7 was wrong and produced garbage tokens.)"""
    codes: list[str] = []
    reader = csv.reader(io.StringIO(csv_text))
    for row in reader:
        if len(row) > 3 and row[3].strip():
            raw = row[3].strip()
            if raw == "-0-":
                continue
            for part in raw.split("] ["):
                code = part.strip().strip("[]").strip()
                if code:
                    codes.append(code)
    return codes


def run() -> dict:
    """Nightly entry point. Never raises — a failed fetch leaves the last
    good snapshot in place and prints a GitHub annotation."""
    try:
        csv_text = fetch_sdn_csv()
    except Exception as exc:  # noqa: BLE001 - network/collector boundary
        print(f"::warning title=ofac_sdn_fetch_failed::{exc}", flush=True)
        return {"ok": False, "error": str(exc)}
    meta = persist_snapshot(csv_text)
    meta["ok"] = True
    meta["n_codes"] = len(extract_program_codes(csv_text))
    return meta


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
