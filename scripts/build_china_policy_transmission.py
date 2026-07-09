"""Build china_policy_transmission artifacts.

Writes:
  data/china_policy_transmission/events.jsonl  — append-only event ledger
  site/chinastatedata/policy_transmission.json — latest snapshot for UI

NIGHTLY APPEND SEMANTICS:
  events.jsonl is append-only; each run reads the existing file, computes the
  full seeded event list, and appends only NEW hashes (idempotent dedup key =
  _hash column).  The file is never truncated.

ASIA-CLOSE LANE:
  This script is called from the asia-close workflow.  Lane-gating is handled
  by the workflow script; the builder itself does not gate on CN_LANE.

USAGE:
  python -m scripts.build_china_policy_transmission
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

_EVENTS_JSONL = "data/china_policy_transmission/events.jsonl"
_SITE_JSON = "site/chinastatedata/policy_transmission.json"


def _root() -> Path:
    from lib import config
    return config.ROOT


def _events_path() -> Path:
    return _root() / _EVENTS_JSONL


def _site_path() -> Path:
    return _root() / _SITE_JSON


def _load_existing_hashes() -> set[str]:
    """Read hashes already in the events.jsonl ledger."""
    p = _events_path()
    if not p.exists():
        return set()
    hashes: set[str] = set()
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                h = row.get("_hash")
                if h:
                    hashes.add(h)
            except json.JSONDecodeError:
                pass
    except Exception as e:  # noqa: BLE001
        log.warning("events.jsonl read error (%s); starting fresh dedup set", e)
    return hashes


def append_events(events: list[dict]) -> int:
    """Append new events (by hash) to events.jsonl.  Returns count of new rows."""
    existing = _load_existing_hashes()
    new_events = [e for e in events if e.get("_hash") not in existing]
    if not new_events:
        return 0
    p = _events_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        for ev in new_events:
            fh.write(json.dumps(ev, ensure_ascii=False, default=str) + "\n")
    return len(new_events)


def build() -> dict | None:
    """Run the full W4 build: seed + append events, write site JSON."""
    from engine import china_policy_transmission as pt

    # 1. Seed events and append new rows to the append-only ledger.
    try:
        events = pt.seed_events()
        n_new = append_events(events)
        log.info("events.jsonl: %d new rows appended (%d total seeded)", n_new, len(events))
    except Exception as e:  # noqa: BLE001
        log.error("event ledger append failed (%s); continuing to snapshot", e)

    # 2. Build the site snapshot.
    snap = pt.snapshot()
    if snap is None:
        log.warning("policy_transmission snapshot returned None; site JSON not written")
        return None

    # Write site/chinastatedata/policy_transmission.json
    site_p = _site_path()
    site_p.parent.mkdir(parents=True, exist_ok=True)
    site_p.write_text(
        json.dumps(snap, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    log.info("wrote %s", site_p)
    return snap


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = build()
    if result is None:
        log.warning("build returned None — check data stores")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
