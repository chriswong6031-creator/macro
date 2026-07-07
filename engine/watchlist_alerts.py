"""engine/watchlist_alerts.py — Thin loader for alert_triage.

Reads the committed data/alerts/watchlist_alerts.jsonl produced by
scripts/run_watchlist_sentinel.py and exposes a load_events() function
matching the contract expected by engine/alert_triage._jsonl_raw().

This module contains ZERO logic — it is purely a file reader.
The sentinel logic lives in engine/watchlist_sentinel.py.
"""
from __future__ import annotations

import json
from pathlib import Path

from lib import config


def _path() -> Path:
    return config.data_dir() / "alerts" / "watchlist_alerts.jsonl"


def load_events() -> list[dict]:
    """Return all watchlist buy-zone-enter events from the committed JSONL.

    Returns [] when the file is absent (sentinel never ran) or on parse error.
    """
    p = _path()
    if not p.exists():
        return []
    out: list[dict] = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out
